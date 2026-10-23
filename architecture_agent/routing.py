"""Select source evidence using code routes and optional architecture neighbors.

This is an advisory, in-memory planner. It never opens a path supplied by a
diagram, runs repository code, calls a model, or treats selection as a security
verdict. Both arms use the same lexical/code/configuration index and budgets.
"""
import ast
from collections import defaultdict, deque
from pathlib import PurePosixPath
import re

import yaml

from .context import ContextError, _field_names, _module_roots, _normalize, plan_context
from .vision import ArchitectureError, CONTEXT_KEYS, validate_context


CONFIG_SUFFIXES = {".yaml", ".yml", ".json", ".properties", ".toml", ".sql"}
MAX_CONFIG_BYTES = 1_000_000


def _infrastructure_kind(kind):
    value = kind.lower()
    if re.search(r"\b(database|storage|bucket|db|postgresql|postgres|mysql|redis|cache)\b", value):
        return "DATASTORE"
    if re.search(r"\b(broker|queue|kafka|message bus|event bus)\b", value):
        return "BROKER"
    return None


def _topic_label(value):
    """Only explicit topic names can connect two arrows through a broker."""
    value = value.strip()
    explicit = re.fullmatch(r"(?i:topic)\s*[:=]\s*([A-Za-z0-9_.-]+)", value)
    if explicit:
        return explicit.group(1)
    return value if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*(?:[.-][A-Za-z0-9_]+)+", value) else None


def _distances(graph, seeds, hops):
    result = {}
    queue = deque((seed, 0) for seed in sorted(seeds))
    while queue:
        node, distance = queue.popleft()
        if node in result:
            continue
        result[node] = distance
        if distance < hops:
            queue.extend((other, distance + 1) for other in sorted(graph.get(node, ())))
    return result


def _scalars(value):
    """Walk bounded safe-loaded data without following alias cycles repeatedly."""
    queue = [value]
    seen = set()
    count = 0
    while queue:
        value = queue.pop()
        count += 1
        if count > 10_000:
            raise ValueError("CONFIG_NODE_BUDGET")
        if isinstance(value, (dict, list)):
            if id(value) in seen:
                continue
            seen.add(id(value))
            queue.extend(list(value.keys()) + list(value.values()) if isinstance(value, dict) else value)
        elif isinstance(value, str):
            yield value


def _strings(value, keys=("topic", "name", "service", "target")):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [item for member in value if isinstance(member, (str, dict))
                for item in _strings(member, keys)]
    if isinstance(value, dict):
        return [value[key] for key in keys if isinstance(value.get(key), str)]
    return []


def _field_match(value, fields):
    return bool(fields & set(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", value)))


def _parse_configs(sources, fields, issues):
    configs = {}
    matches = set()
    for path, source in sources.items():
        suffix = PurePosixPath(path).suffix
        if suffix == ".py":
            # Dictionary/subscript keys also carry fields; comments do not.
            try:
                tree = ast.parse(source)
            except (SyntaxError, ValueError, RecursionError):
                continue
            if any(isinstance(node, ast.Constant) and isinstance(node.value, str)
                   and node.value in fields for node in ast.walk(tree)):
                matches.add(path)
        elif suffix in CONFIG_SUFFIXES:
            if len(source.encode()) > MAX_CONFIG_BYTES:
                issues.append({"path": path, "reason": "CONFIG_SIZE_BUDGET"})
                continue
            if suffix in {".yaml", ".yml", ".json"}:
                try:
                    value = yaml.safe_load(source)
                    scalars = list(_scalars(value))
                except (yaml.YAMLError, ValueError, RecursionError):
                    issues.append({"path": path, "reason": "CONFIG_PARSE_FAILED"})
                    continue
                if isinstance(value, dict):
                    configs[path] = value
                if any(_field_match(item, fields) for item in scalars):
                    matches.add(path)
            else:
                # Lexical evidence only. SQL/config syntax and runtime values are
                # not evaluated; comments are removed to reduce false candidates.
                text = re.sub(r"/\*[\s\S]*?\*/|--[^\n]*|(?m:^\s*[#!][^\n]*)", "", source)
                if _field_match(text, fields):
                    matches.add(path)
    return configs, matches


def _names(value, aliases):
    """Match complete labels or literal identifiers, never substring guesses."""
    if not isinstance(value, str):
        return []
    options = {_normalize(value)}
    options.update(_normalize(token) for token in re.findall(r"[A-Za-z_][A-Za-z0-9_-]*", value))
    return sorted({root for option in options for root in aliases.get(option, ())})


def plan_routed_context(sources, finding, *, architecture=None, use_vision_context=False,
                        max_files=80, max_bytes=64_000, max_hops=3,
                        scanner_paths=(), changed_paths=(), expected_commit=None,
                        context_commit=None):
    """Return deterministic paths from sources, preserving every mandatory file.

    READY means the bounded selection can be submitted, not that every relevant
    source or risk was found. NEEDS_BATCHING preserves oversized mandatory inputs.
    Commit metadata is checked when supplied; otherwise freshness is unverified.
    """
    if (not isinstance(use_vision_context, bool)
            or any(not isinstance(v, int) or isinstance(v, bool) or v < 1 for v in (max_files, max_bytes))
            or not isinstance(max_hops, int) or isinstance(max_hops, bool) or not 0 <= max_hops <= 4):
        raise ContextError("INVALID_ROUTING_INPUT")
    # The shared implementation validates all source paths, inputs and global
    # source budgets, and supplies the unchanged AST/import/identifier baseline.
    base = plan_context(sources, finding, scanner_paths=scanner_paths, changed_paths=changed_paths,
                        use_vision_context=False, max_files=20_000, max_bytes=64 * 1024 * 1024,
                        max_hops=max_hops)
    sources = dict(sorted(sources.items()))
    fields = _field_names(finding)
    modules, _ = _module_roots(sources)
    path_roots = {path: root for root, paths in modules.items() for path in paths}
    aliases = defaultdict(set)
    for root in modules:
        aliases[_normalize(PurePosixPath(root).name)].add(root)
    issues = list(base["coverage"]["indexIssues"])
    configs, extra_fields = _parse_configs(sources, fields, issues)
    for path, config in configs.items():
        root = path_roots.get(path)
        service = config.get("service")
        if root and isinstance(service, str) and re.fullmatch(r"[A-Za-z0-9_-]+", service):
            aliases[_normalize(service)].add(root)
    module_graph = defaultdict(set)
    route_evidence = []
    unresolved = []

    def connect(left, right, path, reason):
        if left != right:
            module_graph[left].add(right)
            module_graph[right].add(left)
            item = {"from": left, "to": right, "path": path, "reason": reason}
            if item not in route_evidence:
                route_evidence.append(item)

    for edge in base["dependencyEdges"]:
        left, right = path_roots.get(edge["from"]), path_roots.get(edge["to"])
        if left and right:
            connect(left, right, edge["from"], "CODE_IMPORT")

    publishers, subscribers, databases = defaultdict(set), defaultdict(set), defaultdict(set)
    route_references = []
    for path, config in configs.items():
        root = path_roots.get(path)
        if root:
            if isinstance(config.get("database"), str):
                databases[config["database"]].add((root, path))
            for key in ("publishes", "publish", "produces"):
                for topic in _strings(config.get(key)):
                    publishers[topic].add((root, path))
            for key in ("subscribes", "subscribe", "consumes"):
                for topic in _strings(config.get(key)):
                    subscribers[topic].add((root, path))
            for key in ("calls", "upstreams", "targets"):
                for target in _strings(config.get(key)):
                    matches = _names(target, aliases)
                    if len(matches) == 1:
                        connect(root, matches[0], path, "CONFIG_SERVICE_CALL")
                    else:
                        unresolved.append({"path": path, "target": target, "reason": "AMBIGUOUS_SERVICE" if matches else "UNKNOWN_SERVICE"})
        routes = config.get("routes", [])
        if isinstance(routes, dict):
            routes = [{"to": value} if isinstance(value, str) else value for value in routes.values()]
        if not isinstance(routes, list):
            continue
        for route in routes:
            if not isinstance(route, dict):
                continue
            origin = route.get("from", route.get("source", config.get("service")))
            destination = route.get("to", route.get("target", route.get("service")))
            # A shared gateway route map identifies endpoints, not a claim that
            # every backend calls every other backend through a synthetic hub.
            left = _names(origin, aliases) if origin else []
            right = _names(destination, aliases)
            if len(left) == len(right) == 1:
                connect(left[0], right[0], path, "CONFIG_ROUTE")
            elif not origin and len(right) == 1:
                route_references.append({"module": right[0], "path": path})
            elif origin or destination:
                unresolved.append({"path": path, "target": str(destination or origin), "reason": "UNRESOLVED_ROUTE"})
    for topic in sorted(set(publishers) & set(subscribers)):
        for publisher, ppath in sorted(publishers[topic]):
            for subscriber, spath in sorted(subscribers[topic]):
                connect(publisher, subscriber, ppath, "CONFIG_TOPIC")
                connect(publisher, subscriber, spath, "CONFIG_TOPIC")
    mandatory = base["mandatoryPaths"]
    anchors = {path_roots[path] for path in mandatory if path in path_roots}
    code_distances = _distances(module_graph, anchors, max_hops)
    # A common database is not a service call. Expand only databases used by a
    # mandatory anchor; never turn a shared DB into transitive all-to-all routes.
    database_neighbors = {}
    for database in sorted(databases):
        entries = sorted(databases[database])
        anchor_entries = [(root, path) for root, path in entries if root in anchors]
        if max_hops and anchor_entries:
            for root, path in entries:
                if root not in anchors:
                    database_neighbors[root] = 1
                    for origin, source_path in anchor_entries:
                        route_evidence.append({"from": origin, "to": root, "path": path,
                                               "reason": "CONFIG_SHARED_DATABASE_CANDIDATE"})
                        route_evidence.append({"from": origin, "to": root, "path": source_path,
                                               "reason": "CONFIG_SHARED_DATABASE_CANDIDATE"})
    reasons = defaultdict(set)
    for entry in base["files"]:
        reasons[entry["path"]].update(entry["reasons"])
    field_paths = set(base["coverage"]["fieldMatchPaths"]) | extra_fields
    for path in extra_fields:
        reasons[path].add("LITERAL_OR_CONFIG_FIELD")
    for root in code_distances:
        for path in modules[root]:
            reasons[path].add("ANCHOR_MODULE" if code_distances[root] == 0 else "CODE_ROUTE_MODULE")
    for root in database_neighbors:
        for path in modules[root]:
            reasons[path].add("SHARED_ANCHOR_DATABASE_CANDIDATE")
    for edge in route_evidence:
        if edge["from"] in code_distances or edge["to"] in code_distances:
            reasons[edge["path"]].add("CODE_ROUTE_CONFIG")
    for reference in route_references:
        if reference["module"] in code_distances:
            reasons[reference["path"]].add("CONFIG_GATEWAY_ROUTE")
    code_candidates = set(reasons)
    mapping = []
    unmatched = []
    diagram_issues = []
    vision_distances = {}
    vision_paths = set()
    decision = {"useVisionContext": False, "reason": "DISABLED" if not use_vision_context else "NO_CACHED_CONTEXT"}
    freshness = "MATCHED" if expected_commit and expected_commit == context_commit else "MISMATCH" if expected_commit or context_commit else "UNVERIFIED"
    if use_vision_context and architecture is not None:
        try:
            context = validate_context({key: architecture[key] for key in CONTEXT_KEYS})
        except (ArchitectureError, KeyError, TypeError):
            decision["reason"] = "INVALID_CACHED_CONTEXT"
        else:
            if context["diagramType"] != "ARCHITECTURE":
                decision["reason"] = "NOT_SYSTEM_ARCHITECTURE"
            elif freshness == "MISMATCH":
                decision["reason"] = "STALE_CONTEXT"
            else:
                component_modules = {}
                infrastructure = {}
                for component in context["components"]:
                    kind = _infrastructure_kind(component["kind"])
                    if kind:
                        infrastructure[component["id"]] = kind
                    matches = [] if kind else _names(component["label"], aliases)
                    status = "MATCHED" if len(matches) == 1 else "AMBIGUOUS" if matches else "UNMATCHED"
                    item = {"componentId": component["id"], "label": component["label"], "moduleRoots": matches, "status": status}
                    if kind:
                        item["reason"] = "NON_CODE_INFRASTRUCTURE_COMPONENT"
                    mapping.append(item)
                    if status == "MATCHED":
                        component_modules[component["id"]] = matches[0]
                    else:
                        unmatched.append(item)
                diagram_graph = defaultdict(set)
                broker_inputs = defaultdict(list)
                broker_outputs = defaultdict(list)
                for flow in context["flows"]:
                    origin, destination = flow["from"], flow["to"]
                    if origin not in infrastructure and destination not in infrastructure:
                        diagram_graph[origin].add(destination)
                        diagram_graph[destination].add(origin)
                    elif infrastructure.get(destination) == "BROKER" and origin not in infrastructure:
                        broker_inputs[destination].append((origin, _topic_label(flow["data"])))
                    elif infrastructure.get(origin) == "BROKER" and destination not in infrastructure:
                        broker_outputs[origin].append((destination, _topic_label(flow["data"])))
                    else:
                        diagram_issues.append({"from": origin, "to": destination, "reason": "DATASTORE_EDGE_NOT_A_SERVICE_CALL"})
                for broker in sorted(set(broker_inputs) | set(broker_outputs)):
                    for origin, incoming_topic in broker_inputs[broker]:
                        for destination, outgoing_topic in broker_outputs[broker]:
                            if incoming_topic and incoming_topic == outgoing_topic:
                                diagram_graph[origin].add(destination)
                                diagram_graph[destination].add(origin)
                            else:
                                diagram_issues.append({"from": origin, "to": destination,
                                                       "via": broker, "reason": "BROKER_TOPIC_UNVERIFIED"})
                seeds = {component for component, root in component_modules.items() if root in anchors}
                diagram_distances = _distances(diagram_graph, seeds, max_hops)
                for component, distance in diagram_distances.items():
                    root = component_modules.get(component)
                    if root:
                        vision_distances[root] = min(distance, vision_distances.get(root, max_hops + 1))
                        vision_paths.update(modules[root])
                decision["reason"] = "CACHED_ARCHITECTURE_NEIGHBORS" if seeds else "NO_MATCHING_ANCHOR_COMPONENT"
                # Literal hints do not bypass anchor-neighborhood relevance or
                # manifest membership. Report unmatched paths without opening any.
                for hint in context["codeHints"]:
                    if hint not in sources:
                        unmatched.append({"hint": hint, "status": "UNMATCHED_PATH"})
                for path in vision_paths:
                    reasons[path].add("ARCHITECTURE_NEIGHBOR_MODULE")
    candidates = code_candidates | vision_paths
    initial = [path for path in mandatory if path in sources]
    initial_bytes = sum(len(sources[path].encode()) for path in initial)
    mandatory_over = len(initial) > max_files or initial_bytes > max_bytes

    def choose(pool, use_architecture):
        def rank(path):
            root = path_roots.get(path)
            code_distance = min(code_distances.get(root, max_hops + 1),
                                database_neighbors.get(root, max_hops + 1))
            architecture_distance = vision_distances.get(root, max_hops + 1) if use_architecture else max_hops + 1
            # Never weaken code routes. Architecture adds independent proximity
            # and breaks ties, while exact field/import evidence stays visible.
            near = min(code_distance, architecture_distance)
            return (near, 0 if path in field_paths else 1,
                    0 if "LEXICAL_DEPENDENCY" in reasons[path] else 1,
                    architecture_distance if use_architecture else max_hops + 1, path)
        selected = list(initial)
        size = initial_bytes
        omitted = []
        for path in sorted(pool - set(initial), key=rank):
            length = len(sources[path].encode())
            why = "MANDATORY_OVER_BUDGET" if mandatory_over else "FILE_BUDGET" if len(selected) >= max_files else "BYTE_BUDGET" if size + length > max_bytes else None
            if why:
                omitted.append({"path": path, "bytes": length, "reason": why})
            else:
                selected.append(path)
                size += length
        return selected, size, omitted

    baseline, baseline_bytes, _ = choose(code_candidates, False)
    selected, selected_bytes, omitted = choose(candidates, bool(vision_distances))
    # A different ordering of the same evidence is not a selection gain. Reuse
    # the baseline request exactly so model-cache effects are not credited to AI.
    if vision_distances:
        if set(selected) == set(baseline):
            selected = baseline
            decision["reason"] = "NO_SELECTION_GAIN"
        else:
            decision["useVisionContext"] = True
    missing = base["unresolvedMandatory"]
    status = "MISSING_MANDATORY" if missing else "NEEDS_BATCHING" if mandatory_over else "READY"
    selected_modules = sorted({path_roots[path] for path in selected if path in path_roots})
    return {
        "schemaVersion": 1, "status": status, "selectedPaths": selected,
        "mandatoryPaths": mandatory, "unresolvedMandatory": missing,
        "selectedModules": selected_modules,
        "selectionReasons": {path: sorted(reasons[path]) for path in selected},
        "unmatched": unmatched, "mapping": mapping,
        "mappingCount": {"matched": sum(item["status"] == "MATCHED" for item in mapping),
                         "ambiguous": sum(item["status"] == "AMBIGUOUS" for item in mapping),
                         "unmatched": sum(item["status"] == "UNMATCHED" for item in mapping), "total": len(mapping)},
        "decision": decision, "omittedCandidates": omitted,
        "codeOnlySelection": {"selectedPaths": baseline, "selectedBytes": baseline_bytes},
        "totals": {"manifestFileCount": len(sources), "manifestBytes": sum(len(value.encode()) for value in sources.values()),
                   "selectedFileCount": len(selected), "selectedBytes": selected_bytes,
                   "maxFiles": max_files, "maxBytes": max_bytes, "withinBudget": not mandatory_over},
        "coverage": {"kind": "LEXICAL_AND_CONFIG_ROUTES_NOT_RUNTIME_DATAFLOW", "maxHops": max_hops,
                     "fieldIdentifiers": sorted(fields), "fieldMatchPaths": sorted(field_paths),
                     "codeReachableModules": sorted(code_distances), "architectureReachableModules": sorted(vision_distances),
                     "anchorDatabaseCandidateModules": sorted(database_neighbors),
                     "candidateCount": len(candidates), "omittedCandidateCount": len(omitted),
                     "unselectedManifestPaths": sorted(set(sources) - set(selected)),
                     "routeEvidence": route_evidence, "unresolvedRoutes": unresolved, "indexIssues": issues,
                     "diagramIssues": diagram_issues,
                     "freshness": freshness, "codeVerificationRequired": True, "fullRepositorySecurityCoverage": False,
                     "limitations": ["Module proximity and field presence are retrieval evidence, not proof of a runtime flow or vulnerability.",
                                     "Dynamic wiring, external configuration, reflection and generated sources may be absent.",
                                     "Diagram freshness is unverified when no matching commit metadata is supplied.",
                                     "Selected modules may still be incomplete when file or byte budgets omit candidates."]},
    }
