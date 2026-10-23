"""Build advisory, budgeted code-review bundles from a local source manifest.

This module never reads the filesystem, imports repository code, invokes a model,
or treats an architecture image as evidence of a vulnerability.
"""
import ast
from collections import defaultdict, deque
from collections.abc import Mapping
import hashlib
import io
import re
import tokenize
from pathlib import PurePosixPath

from .vision import ArchitectureError, CONTEXT_KEYS, validate_context


class ContextError(ValueError):
    pass


def _path(value):
    if (not isinstance(value, str) or not value or len(value) > 1000 or value.startswith(("/", "~"))
            or "\\" in value or ":" in value or any(ord(c) < 32 for c in value)
            or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ContextError("INVALID_MANIFEST_PATH")
    return value


def _normalize(value):
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _java_code(source):
    # Strip comments and literals while retaining line boundaries and identifiers.
    # Java text blocks are handled before ordinary strings. This is lexical, not a compiler.
    pattern = r'"""[\s\S]*?"""|"(?:\\.|[^"\\])*"|\'(?:\\.|[^\'\\])*\'|//[^\n]*|/\*[\s\S]*?\*/'
    return re.sub(pattern, lambda m: re.sub(r"[^\n]", " ", m.group()), source)


def _python_identifiers(source):
    try:
        return {token.string for token in tokenize.generate_tokens(io.StringIO(source).readline)
                if token.type == tokenize.NAME}
    except (tokenize.TokenError, IndentationError, SyntaxError):
        return set()


def _field_names(finding):
    supplied = finding.get("fields", [])
    if not isinstance(supplied, list) or len(supplied) > 32:
        raise ContextError("INVALID_FINDING_FIELDS")
    values = supplied + ([finding["field"]] if finding.get("field") else [])
    result = set()
    for value in values:
        if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,100}", value):
            raise ContextError("INVALID_FINDING_FIELDS")
        result.add(value)
        title = value[0].upper() + value[1:]
        result.update({"get" + title, "set" + title, "is" + title})
    return result


def _index(sources, fields):
    graph = {path: set() for path in sources}
    reasons = defaultdict(set)
    python_modules = defaultdict(set)
    java_types = defaultdict(set)
    java_packages = {}
    records = {}
    issues = []
    field_matches = set()
    for path, source in sources.items():
        suffix = PurePosixPath(path).suffix
        if suffix == ".py":
            parts = path[:-3].split("/")
            if parts[-1] == "__init__":
                parts.pop()
            for offset in range(len(parts)):
                python_modules[".".join(parts[offset:])].add(path)
            identifiers = _python_identifiers(source)
            try:
                tree = ast.parse(source)
                records[path] = ("python", tree)
            except (SyntaxError, ValueError, RecursionError):
                records[path] = ("unsupported", None)
                issues.append({"path": path, "reason": "PYTHON_PARSE_FAILED"})
        elif suffix == ".java":
            code = _java_code(source)
            identifiers = set(re.findall(r"\b[A-Za-z_$][\w$]*\b", code))
            package = re.search(r"\bpackage\s+([\w.]+)\s*;", code)
            package = package.group(1) if package else ""
            java_packages[path] = package
            declarations = re.findall(r"\b(?:class|interface|enum|record)\s+([A-Za-z_$][\w$]*)", code)
            for declaration in declarations:
                java_types[(package + "." if package else "") + declaration].add(path)
            records[path] = ("java", (code, identifiers))
        else:
            identifiers = set()
            records[path] = ("unsupported", None)
        if fields & identifiers:
            field_matches.add(path)

    def link(source, targets, why, symbol):
        targets = targets - {source}
        if len(targets) > 1:
            issues.append({"path": source, "reason": "AMBIGUOUS_SYMBOL", "symbol": symbol,
                           "candidates": sorted(targets)})
            return
        for target in targets:
            graph[source].add(target)
            graph[target].add(source)
            reasons[(source, target)].add(why)
            reasons[(target, source)].add(why)

    for path, (language, data) in records.items():
        if language == "python":
            for node in ast.walk(data):
                modules = []
                if isinstance(node, ast.Import):
                    modules = [item.name for item in node.names]
                elif isinstance(node, ast.ImportFrom):
                    if node.level:
                        package = path.split("/")[:-1]
                        if node.level > len(package):
                            issues.append({"path": path, "reason": "UNRESOLVED_RELATIVE_IMPORT"})
                            continue
                        prefix = package[:len(package) - node.level + 1]
                        module = ".".join(prefix + ([node.module] if node.module else []))
                    else:
                        module = node.module or ""
                    modules = [module] + [module + "." + item.name for item in node.names if item.name != "*"]
                elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "__import__":
                    issues.append({"path": path, "reason": "DYNAMIC_IMPORT_UNRESOLVED"})
                elif (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                      and node.func.attr == "import_module"):
                    issues.append({"path": path, "reason": "DYNAMIC_IMPORT_UNRESOLVED"})
                for module in modules:
                    link(path, python_modules.get(module, set()), "PYTHON_IMPORT", module)
        elif language == "java":
            code, identifiers = data
            package = java_packages[path]
            imported = {}
            wildcards = []
            for static, name in re.findall(r"\bimport\s+(static\s+)?([\w.*]+)\s*;", code):
                if static:
                    owner = name.rsplit(".", 1)[0]
                    link(path, java_types.get(owner, set()), "JAVA_STATIC_IMPORT", owner)
                elif name.endswith(".*"):
                    wildcards.append(name[:-2])
                else:
                    imported[name.rsplit(".", 1)[-1]] = name
                    link(path, java_types.get(name, set()), "JAVA_IMPORT", name)
            for identifier in identifiers:
                qualified = imported.get(identifier)
                if qualified:
                    candidates = java_types.get(qualified, set())
                else:
                    qualified = (package + "." if package else "") + identifier
                    candidates = set(java_types.get(qualified, set()))
                    for wildcard in wildcards:
                        candidates.update(java_types.get(wildcard + "." + identifier, set()))
                link(path, candidates, "JAVA_TYPE_REFERENCE", identifier)
            for qualified in re.findall(r"\b(?:[a-z_]\w*\.)+[A-Z][\w$]*\b", code):
                link(path, java_types.get(qualified, set()), "JAVA_QUALIFIED_TYPE", qualified)
    return graph, reasons, field_matches, records, issues


def _module_roots(sources):
    modules = defaultdict(set)
    for path in sources:
        parts = path.split("/")
        if "src" in parts[:-1] and parts.index("src") > 0:
            root = "/".join(parts[:parts.index("src")])
        elif parts[0] in {"services", "apps", "modules", "packages"} and len(parts) > 2:
            root = "/".join(parts[:2])
        elif len(parts) > 1:
            root = parts[0]
        else:
            continue
        modules[root].add(path)
    aliases = defaultdict(set)
    tokens = {root: re.findall(r"[a-z0-9]+", PurePosixPath(root).name.lower()) for root in modules}
    generic = {"service", "server", "worker", "app", "api", "backend", "frontend"}
    for root, parts in tokens.items():
        aliases[_normalize(PurePosixPath(root).name)].add(root)
        # A shared project prefix in actual sibling module names is explicit metadata,
        # e.g. spring-petclinic-{customers,genai}-service -> customersservice/genaiservice.
        for count in range(2, len(parts)):
            peers = [other for other, other_parts in tokens.items()
                     if other != root and PurePosixPath(other).parent == PurePosixPath(root).parent
                     and other_parts[:count] == parts[:count] and len(other_parts) > count]
            alias = "".join(parts[count:])
            if peers and alias not in generic:
                aliases[alias].add(root)
    return modules, aliases


def _staleness(expected, actual):
    if not expected or not actual:
        return "UNKNOWN"
    return "MATCHED" if expected == actual else "COMMIT_MISMATCH"


def plan_context(sources, finding, *, architecture=None, manifest=None, changed_paths=(), scanner_paths=(), required_paths=(),
                 expected_commit=None, context_commit=None, use_vision_context=True,
                 max_files=12, max_bytes=48_000, max_hops=2):
    """Plan bounded evidence inputs; selectedPaths are keys in sources, not disk paths.

    Mandatory inputs are never discarded to meet budgets. NEEDS_BATCHING means
    callers must batch or raise the explicit budget before sending any bundle.
    """
    if (not isinstance(sources, Mapping) or not isinstance(finding, Mapping)
            or any(not isinstance(n, int) or isinstance(n, bool) or n < 1 for n in (max_files, max_bytes))
            or not isinstance(max_hops, int) or isinstance(max_hops, bool) or not 0 <= max_hops <= 4):
        raise ContextError("INVALID_CONTEXT_INPUT")
    if (isinstance(manifest, (str, bytes)) or isinstance(changed_paths, (str, bytes))
            or isinstance(scanner_paths, (str, bytes)) or isinstance(required_paths, (str, bytes))):
        raise ContextError("INVALID_PATH_COLLECTION")
    for path, source in sources.items():
        _path(path)
        if not isinstance(source, str):
            raise ContextError("INVALID_SOURCE_TEXT")
    allowed = set(sources) if manifest is None else {_path(path) for path in manifest}
    indexed = {path: source for path, source in sorted(sources.items()) if path in allowed}
    if sum(len(source.encode()) for source in indexed.values()) > 64 * 1024 * 1024 or len(indexed) > 20_000:
        raise ContextError("LOCAL_INDEX_BUDGET_EXCEEDED")
    mandatory_reasons = defaultdict(set)
    anchor = _path(finding.get("filePath"))
    mandatory_reasons[anchor].add("FINDING")
    for label, paths in (("SCANNER", scanner_paths), ("CHANGED", changed_paths), ("CONTRACT", required_paths)):
        for path in paths:
            mandatory_reasons[_path(path)].add(label)
    mandatory = sorted(mandatory_reasons)
    missing = [path for path in mandatory if path not in indexed]
    fields = _field_names(finding)
    graph, edges, field_matches, records, index_issues = _index(indexed, fields)
    distances = {}
    queue = deque((path, 0) for path in mandatory if path in indexed)
    while queue:
        path, depth = queue.popleft()
        if path in distances:
            continue
        distances[path] = depth
        if depth < max_hops:
            queue.extend((neighbor, depth + 1) for neighbor in sorted(graph[path]))
    candidates = set(distances) | field_matches
    code_only_candidates = set(candidates)
    reasons = defaultdict(set)
    for path in candidates:
        if path in field_matches:
            reasons[path].add("FIELD_IDENTIFIER_MATCH")
        if path in distances and distances[path]:
            reasons[path].add("LEXICAL_DEPENDENCY")
    for path, labels in mandatory_reasons.items():
        reasons[path].update(labels)
    stale = _staleness(expected_commit, context_commit)
    decision = {"useVisionContext": False, "reason": "NO_CACHED_CONTEXT", "requiresNewInference": False,
                "costBasis": "CACHED_CONTEXT_ONLY_NO_COST_ESTIMATE"}
    unmatched_hints = []
    module_matches = []
    vision_paths = set()
    context = None
    if not use_vision_context:
        decision["reason"] = "DISABLED"
    elif architecture is not None:
        try:
            context = validate_context({key: architecture[key] for key in CONTEXT_KEYS})
        except (ArchitectureError, KeyError, TypeError):
            decision["reason"] = "INVALID_CACHED_CONTEXT"
        else:
            if context["diagramType"] != "ARCHITECTURE":
                decision["reason"] = "NOT_SYSTEM_ARCHITECTURE"
            elif stale != "MATCHED":
                decision["reason"] = "STALE_CONTEXT" if stale == "COMMIT_MISMATCH" else "CONTEXT_FRESHNESS_UNKNOWN"
            else:
                for hint in context["codeHints"]:
                    if hint in indexed:
                        vision_paths.add(hint)
                        reasons[hint].add("DIAGRAM_LITERAL_PATH")
                    else:
                        unmatched_hints.append(hint)
                modules, aliases = _module_roots(indexed)
                for component in context["components"]:
                    matches = sorted(aliases.get(_normalize(component["label"]), set()))
                    module_matches.append({"componentId": component["id"], "label": component["label"],
                        "moduleRoots": matches, "status": "MATCHED" if len(matches) == 1 else "AMBIGUOUS" if matches else "UNMATCHED"})
                    if len(matches) == 1:
                        for path in modules[matches[0]]:
                            vision_paths.add(path)
                            reasons[path].add("DIAGRAM_MODULE_MATCH")
                if not vision_paths:
                    decision["reason"] = "NO_MATCHING_MANIFEST_TARGETS"
                elif vision_paths <= candidates:
                    decision["reason"] = "ALREADY_COVERED_BY_CODE_GRAPH"
                else:
                    decision.update(useVisionContext=True, reason="CACHED_ARCHITECTURE_ADDS_MANIFEST_TARGETS")
                    candidates.update(vision_paths)
    initial = [path for path in mandatory if path in indexed]
    initial_bytes = sum(len(indexed[path].encode()) for path in initial)
    mandatory_over_budget = len(initial) > max_files or initial_bytes > max_bytes
    def priority(path, vision):
        # Field evidence and real code dependencies always precede diagram-only guesses.
        return (0 if path in field_matches and path in distances else 1 if path in field_matches else 2 if path in distances else 3,
                0 if vision and path in vision_paths else 1,
                distances.get(path, max_hops + 1), path)
    def choose(candidate_set, vision):
        selected = list(initial)
        used = initial_bytes
        omitted = []
        for path in sorted(candidate_set - set(selected), key=lambda path: priority(path, vision)):
            size = len(indexed[path].encode())
            reason = "MANDATORY_OVER_BUDGET" if mandatory_over_budget else "FILE_BUDGET" if len(selected) >= max_files else "BYTE_BUDGET" if used + size > max_bytes else None
            if reason:
                omitted.append({"path": path, "bytes": size, "reason": reason, "candidateReasons": sorted(reasons[path])})
            else:
                selected.append(path)
                used += size
        return selected, used, omitted
    selected, used, omitted = choose(candidates, decision["useVisionContext"])
    baseline, baseline_bytes, _ = choose(code_only_candidates, False)
    if decision["useVisionContext"] and selected == baseline:
        decision.update(useVisionContext=False, reason="NO_SELECTION_GAIN")
    status = "MISSING_MANDATORY" if missing else "NEEDS_BATCHING" if mandatory_over_budget else "READY"
    selected_set = set(selected)
    decision.update(addedCandidateCount=len(candidates - code_only_candidates),
                    selectedAdditionalPaths=sorted(selected_set - code_only_candidates))
    unsupported = [path for path, (language, _) in records.items() if language == "unsupported"]
    selected_edges = [{"from": a, "to": b, "reasons": sorted(why)} for (a, b), why in sorted(edges.items())
                      if a < b and a in selected_set and b in selected_set]
    return {"schemaVersion": 1, "status": status, "selectedPaths": selected, "mandatoryPaths": mandatory,
        "unresolvedMandatory": missing,
        "files": [{"path": path, "bytes": len(indexed[path].encode()), "sha256": hashlib.sha256(indexed[path].encode()).hexdigest(),
                   "reasons": sorted(reasons[path])} for path in selected],
        "totals": {"manifestFileCount": len(allowed), "indexedFileCount": len(indexed),
                   "indexedBytes": sum(len(source.encode()) for source in indexed.values()),
                   "selectedFileCount": len(selected), "selectedBytes": used,
                   "maxFiles": max_files, "maxBytes": max_bytes, "withinBudget": not mandatory_over_budget},
        "decision": decision, "staleness": stale, "unmatchedHints": unmatched_hints,
        "codeOnlySelection": {"selectedPaths": baseline, "selectedBytes": baseline_bytes},
        "moduleMatches": module_matches, "omittedCandidates": omitted, "dependencyEdges": selected_edges,
        "coverage": {"kind": "LEXICAL_CANDIDATES_NOT_RUNTIME_DATAFLOW", "maxHops": max_hops,
            "fieldIdentifiers": sorted(fields), "fieldMatchPaths": sorted(field_matches),
            "candidateCount": len(candidates), "selectedCandidateCount": len(selected),
            "omittedCandidateCount": len(omitted), "unselectedManifestCount": len(set(indexed) - selected_set),
            "unavailableManifestPaths": sorted(allowed - set(indexed)),
            "unsupportedOrUnparsedPaths": unsupported, "indexIssues": index_issues,
            "codeVerificationRequired": True, "fullRepositorySecurityCoverage": False,
            "limitations": ["Imports and identifiers are lexical candidates, not proof of a runtime data flow.",
                "Reflection, generated code, dynamic dispatch, configuration wiring and external repositories may be absent.",
                "A selected or omitted file is never evidence of safety or vulnerability.",
                "Matching commit labels do not verify that the diagram matches deployed architecture."]}}
