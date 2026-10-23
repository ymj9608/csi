"""Deterministic context selection: mandatory evidence, bounds and honest coverage."""
import copy

import pytest

from architecture_agent.context import ContextError, plan_context


CUSTOMERS = "spring-petclinic-customers-service/src/main/java/example"
GENAI = "spring-petclinic-genai-service/src/main/java/example/ai"
OWNER = CUSTOMERS + "/web/OwnerResource.java"
DTO = CUSTOMERS + "/dto/Owner.java"
SERVICE = CUSTOMERS + "/service/OwnerService.java"
REPOSITORY = CUSTOMERS + "/repository/OwnerRepository.java"
CLIENT = GENAI + "/AiClient.java"
SOURCES = {
    OWNER: """package example.web;
import example.dto.Owner;
import example.service.OwnerService;
class OwnerResource { OwnerService service;
  void update(Owner owner) { service.save(owner.getTelephone()); }
}""",
    DTO: "package example.dto; public record Owner(String telephone) {}",
    SERVICE: """package example.service;
import example.repository.OwnerRepository;
class OwnerService { OwnerRepository repo; void save(String telephone) { repo.save(telephone); } }""",
    REPOSITORY: "package example.repository; public interface OwnerRepository { void save(String telephone); }",
    CLIENT: "package example.ai; class AiClient { void send(String contact) {} }",
    "docs/Notes.java": '// telephone should not cause field evidence\nclass Notes { String text = "telephone"; }',
}
ARCHITECTURE = {"diagramType": "ARCHITECTURE", "components": [
    {"id": "customers", "label": "Customers Service", "kind": "service"},
    {"id": "genai", "label": "GenAI-Service", "kind": "service"}],
    "flows": [{"from": "customers", "to": "genai", "data": "contact", "protection": "UNKNOWN"}],
    "codeHints": [], "trustBoundaries": [], "assumptions": [],
    "uncertainties": ["Actual implementation requires code verification"], "summary": "Visible service modules"}


def plan(sources=None, **kwargs):
    return plan_context(sources or SOURCES, {"filePath": OWNER, "field": "telephone"}, **kwargs)


def test_code_only_resolves_java_imports_types_and_field_without_image():
    result = plan()
    assert result["status"] == "READY"
    assert set(result["selectedPaths"]) == {OWNER, DTO, SERVICE, REPOSITORY}
    assert result["decision"]["reason"] == "NO_CACHED_CONTEXT"
    assert result["decision"]["requiresNewInference"] is False
    assert result["coverage"]["fullRepositorySecurityCoverage"] is False
    assert any("JAVA_IMPORT" in edge["reasons"] for edge in result["dependencyEdges"])


def test_no_path_diagram_maps_real_modules_and_adds_cross_service_candidate():
    result = plan(architecture=ARCHITECTURE, expected_commit="head", context_commit="head")
    assert result["decision"]["useVisionContext"] is True
    assert CLIENT in result["selectedPaths"]
    assert all(item["status"] == "MATCHED" for item in result["moduleMatches"])
    assert result["moduleMatches"][1]["moduleRoots"] == ["spring-petclinic-genai-service"]
    assert "DIAGRAM_MODULE_MATCH" in next(item for item in result["files"] if item["path"] == CLIENT)["reasons"]
    assert result["unmatchedHints"] == []


def test_same_planner_without_vision_provides_fair_code_mapping_baseline():
    disabled = plan(architecture=ARCHITECTURE, expected_commit="head", context_commit="head", use_vision_context=False)
    absent = plan()
    assert disabled["selectedPaths"] == absent["selectedPaths"]
    assert disabled["decision"]["reason"] == "DISABLED"


@pytest.mark.parametrize("expected,actual,reason", [("new", "old", "STALE_CONTEXT"), (None, "head", "CONTEXT_FRESHNESS_UNKNOWN"), ("head", None, "CONTEXT_FRESHNESS_UNKNOWN")])
def test_stale_or_unknown_context_never_narrows_or_expands_code_candidates(expected, actual, reason):
    result = plan(architecture=ARCHITECTURE, expected_commit=expected, context_commit=actual)
    assert result["selectedPaths"] == plan()["selectedPaths"]
    assert result["decision"]["reason"] == reason
    assert not result["decision"]["useVisionContext"]


@pytest.mark.parametrize("diagram_type", ["WORKFLOW", "UNKNOWN"])
def test_workflow_is_not_technical_architecture(diagram_type):
    result = plan(architecture={**ARCHITECTURE, "diagramType": diagram_type}, expected_commit="head", context_commit="head")
    assert result["decision"]["reason"] == "NOT_SYSTEM_ARCHITECTURE"
    assert CLIENT not in result["selectedPaths"]


def test_finding_changed_and_scanner_files_are_mandatory_even_if_not_in_diagram():
    sources = {**SOURCES, "jobs/Undocumented.java": "class Undocumented {}", "other/Changed.java": "class Changed {}"}
    result = plan(sources, architecture=ARCHITECTURE, expected_commit="head", context_commit="head",
                  scanner_paths=["jobs/Undocumented.java"], changed_paths=["other/Changed.java"], max_files=3)
    assert set(result["selectedPaths"]) == {OWNER, "jobs/Undocumented.java", "other/Changed.java"}
    assert result["status"] == "READY"
    assert result["coverage"]["omittedCandidateCount"] > 0
    assert all(item["reason"] == "FILE_BUDGET" for item in result["omittedCandidates"])


def test_mandatory_over_budget_returns_batching_requirement_and_never_drops_evidence():
    result = plan(scanner_paths=[DTO, SERVICE], max_files=1, max_bytes=10)
    assert set(result["selectedPaths"]) == {OWNER, DTO, SERVICE}
    assert result["status"] == "NEEDS_BATCHING"
    assert result["totals"]["withinBudget"] is False
    assert result["totals"]["selectedBytes"] > result["totals"]["maxBytes"]
    assert all(item["reason"] == "MANDATORY_OVER_BUDGET" for item in result["omittedCandidates"])


def test_missing_mandatory_path_is_explicit_and_cannot_be_ready():
    result = plan(changed_paths=["missing/Source.java"])
    assert result["status"] == "MISSING_MANDATORY"
    assert result["unresolvedMandatory"] == ["missing/Source.java"]
    assert "missing/Source.java" in result["mandatoryPaths"]


def test_manifest_is_the_only_authorized_source_set():
    result = plan(manifest=[OWNER], scanner_paths=[DTO])
    assert result["status"] == "MISSING_MANDATORY"
    assert result["selectedPaths"] == [OWNER]
    assert result["totals"]["indexedFileCount"] == 1


def test_byte_budget_omissions_are_logged_and_not_sent():
    limit = len(SOURCES[OWNER].encode()) + 1
    result = plan(max_bytes=limit)
    assert result["selectedPaths"] == [OWNER]
    assert result["totals"]["selectedBytes"] <= limit
    assert all(item["reason"] == "BYTE_BUDGET" for item in result["omittedCandidates"])


def test_diagram_cannot_open_unmatched_paths_or_globs():
    architecture = {**ARCHITECTURE, "components": [], "flows": [], "codeHints": ["not-present/Secret.java", "**/*.java"]}
    result = plan(architecture=architecture, expected_commit="head", context_commit="head")
    assert result["decision"]["reason"] == "NO_MATCHING_MANIFEST_TARGETS"
    assert result["unmatchedHints"] == architecture["codeHints"]
    assert result["selectedPaths"] == plan()["selectedPaths"]


def test_invalid_cached_paths_fall_back_to_code_only_safely():
    result = plan(architecture={**ARCHITECTURE, "codeHints": ["../../.env"]}, expected_commit="head", context_commit="head")
    assert result["decision"]["reason"] == "INVALID_CACHED_CONTEXT"
    assert result["selectedPaths"] == plan()["selectedPaths"]


def test_redundant_diagram_context_is_skipped_without_cost_guess():
    architecture = {**ARCHITECTURE, "components": [], "flows": [], "codeHints": [DTO]}
    result = plan(architecture=architecture, expected_commit="head", context_commit="head")
    assert result["decision"]["reason"] == "ALREADY_COVERED_BY_CODE_GRAPH"
    assert not result["decision"]["useVisionContext"]
    assert result["decision"]["costBasis"] == "CACHED_CONTEXT_ONLY_NO_COST_ESTIMATE"


def test_diagram_only_adds_budget_omissions_so_model_context_is_not_expanded():
    result = plan(architecture=ARCHITECTURE, expected_commit="head", context_commit="head", max_files=4)
    baseline = plan(max_files=4)
    assert result["selectedPaths"] == baseline["selectedPaths"]
    assert result["decision"]["reason"] == "NO_SELECTION_GAIN"
    assert result["decision"]["useVisionContext"] is False
    assert result["decision"]["addedCandidateCount"] == 1
    assert result["decision"]["selectedAdditionalPaths"] == []
    assert any(item["path"] == CLIENT and item["reason"] == "FILE_BUDGET" for item in result["omittedCandidates"])
    assert result["codeOnlySelection"]["selectedPaths"] == baseline["selectedPaths"]


def test_real_extra_selection_keeps_cached_vision_context_enabled():
    result = plan(architecture=ARCHITECTURE, expected_commit="head", context_commit="head", max_files=5)
    assert result["decision"]["useVisionContext"] is True
    assert result["decision"]["selectedAdditionalPaths"] == [CLIENT]
    assert result["selectedPaths"] != result["codeOnlySelection"]["selectedPaths"]


def test_ambiguous_module_label_does_not_guess_between_roots():
    sources = {**SOURCES, "services/customer/src/Alpha.java": "class Alpha {}", "apps/customer/src/Beta.java": "class Beta {}"}
    architecture = {**ARCHITECTURE, "components": [{"id": "customer", "label": "Customer", "kind": "service"}], "flows": []}
    result = plan(sources, architecture=architecture, expected_commit="head", context_commit="head")
    assert result["moduleMatches"][0]["status"] == "AMBIGUOUS"
    assert "services/customer/src/Alpha.java" not in result["selectedPaths"]
    assert "apps/customer/src/Beta.java" not in result["selectedPaths"]


def test_comments_and_literals_are_not_java_field_references():
    result = plan()
    assert "docs/Notes.java" not in result["coverage"]["fieldMatchPaths"]
    assert "docs/Notes.java" not in result["selectedPaths"]


def test_python_relative_imports_and_field_identifiers_resolve_without_execution():
    sources = {
        "backend/app/routes.py": "from .models import Owner\ndef update(owner): return owner.telephone\n",
        "backend/app/models.py": "class Owner:\n    telephone: str\n",
        "backend/app/log.py": "# telephone\ntext = 'telephone'\n",
        "backend/app/dynamic.py": "import importlib\nimportlib.import_module('external')\n",
    }
    result = plan_context(sources, {"filePath": "backend/app/routes.py", "field": "telephone"})
    assert set(result["selectedPaths"]) == {"backend/app/routes.py", "backend/app/models.py"}
    assert result["dependencyEdges"][0]["reasons"] == ["PYTHON_IMPORT"]
    assert any(item["reason"] == "DYNAMIC_IMPORT_UNRESOLVED" for item in result["coverage"]["indexIssues"])


def test_parse_failure_and_unsupported_languages_remain_visible():
    sources = {"entry.py": "def incomplete(", "view.ts": "export const telephone = 1;"}
    result = plan_context(sources, {"filePath": "entry.py", "field": "telephone"}, scanner_paths=["view.ts"])
    assert set(result["selectedPaths"]) == set(sources)
    assert set(result["coverage"]["unsupportedOrUnparsedPaths"]) == set(sources)
    assert result["coverage"]["indexIssues"] == [{"path": "entry.py", "reason": "PYTHON_PARSE_FAILED"}]


@pytest.mark.parametrize("path", ["../../.env", "/etc/passwd", "C:/private", "a\\secret", "a//b"])
def test_invalid_manifest_paths_fail_before_index(path):
    with pytest.raises(ContextError, match="INVALID_MANIFEST_PATH"):
        plan_context({path: ""}, {"filePath": path})


def test_ambiguous_java_type_is_reported_without_inventing_dependency():
    sources = {"api/Entry.java": "package a; class Entry { Shared shared; }",
               "one/Shared.java": "package a; class Shared {}", "two/Shared.java": "package a; class Shared {}"}
    result = plan_context(sources, {"filePath": "api/Entry.java"})
    assert result["selectedPaths"] == ["api/Entry.java"]
    assert any(issue["reason"] == "AMBIGUOUS_SYMBOL" for issue in result["coverage"]["indexIssues"])


def test_input_order_does_not_change_selection_and_no_mutation():
    original = copy.deepcopy(ARCHITECTURE)
    forward = plan(architecture=original, expected_commit="head", context_commit="head")
    backward = plan(dict(reversed(list(SOURCES.items()))), architecture=original, expected_commit="head", context_commit="head")
    assert forward == backward
    assert original == ARCHITECTURE
