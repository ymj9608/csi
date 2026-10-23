"""Shared code routing baseline and bounded, advisory diagram expansion."""
import copy

import pytest

from architecture_agent.context import ContextError
from architecture_agent.routing import plan_routed_context


ANCHOR = "services/profile/service.py"
WORKER = "services/notify/consumer.py"
ARCHIVE = "services/archive/export.py"
SOURCE = {
    ANCHOR: "from services.profile.models import Contact\ndef save(telephone): return Contact(telephone)\n",
    "services/profile/models.py": "class Contact:\n    def __init__(self, telephone): self.telephone = telephone\n",
    "services/profile/schema.sql": "CREATE TABLE contacts (id INTEGER, telephone TEXT);\n",
    "services/profile/deployment.yaml": "service: profile\ndatabase: profile_db\nproduces: [contact.changed]\n",
    WORKER: "def receive(message, logger): logger.info('delivery=%s', message['destination'])\n",
    "services/notify/deployment.yaml": "service: notify\nconsumes: [contact.changed]\n",
    ARCHIVE: "def send(row, http): http.post('/archive', json=row)\n",
    "services/archive/deployment.yaml": "service: archive\n",
    "services/catalog/service.py": "def item(sku): return {'sku': sku}\n",
    "infra/routes.yaml": "routes:\n  /contacts: profile\n  /catalog: catalog\n",
}


def architecture(flows=None, components=None):
    return {
        "diagramType": "ARCHITECTURE",
        "components": components or [
            {"id": "p", "label": "profile", "kind": "api"},
            {"id": "n", "label": "notify", "kind": "worker"},
            {"id": "a", "label": "archive", "kind": "worker"},
            {"id": "c", "label": "catalog", "kind": "api"}],
        "flows": flows if flows is not None else [
            {"from": "p", "to": "n", "data": "contact", "protection": "UNKNOWN"},
            {"from": "n", "to": "a", "data": "delivery", "protection": "UNKNOWN"}],
        "codeHints": [], "trustBoundaries": [], "assumptions": [],
        "uncertainties": [], "summary": "Service connections; verify the actual code.",
    }


def plan(sources=None, **kwargs):
    return plan_routed_context(SOURCE if sources is None else sources,
                               {"filePath": ANCHOR, "field": "telephone"}, **kwargs)


def test_code_only_follows_topics_imports_schema_and_gateway_without_diagram():
    result = plan()
    assert result["status"] == "READY"
    assert WORKER in result["selectedPaths"]
    assert "services/profile/models.py" in result["selectedPaths"]
    assert "services/profile/schema.sql" in result["selectedPaths"]
    assert "infra/routes.yaml" in result["selectedPaths"]
    assert ARCHIVE not in result["selectedPaths"]
    assert "services/catalog/service.py" not in result["selectedPaths"]
    assert any(edge["reason"] == "CONFIG_TOPIC" for edge in result["coverage"]["routeEvidence"])
    assert result["decision"] == {"useVisionContext": False, "reason": "DISABLED"}


def test_architecture_adds_only_anchor_neighbors_not_every_visible_service():
    result = plan(architecture=architecture(), use_vision_context=True)
    assert ARCHIVE in result["selectedPaths"]
    assert "services/catalog/service.py" not in result["selectedPaths"]
    assert result["decision"]["useVisionContext"]
    assert result["mappingCount"] == {"matched": 4, "unmatched": 0, "ambiguous": 0, "total": 4}
    assert result["coverage"]["freshness"] == "UNVERIFIED"
    assert result["coverage"]["fullRepositorySecurityCoverage"] is False


def test_architecture_hop_budget_is_respected_and_no_gain_reuses_same_order():
    result = plan(architecture=architecture(), use_vision_context=True, max_hops=1)
    assert ARCHIVE not in result["selectedPaths"]
    assert result["selectedPaths"] == result["codeOnlySelection"]["selectedPaths"]
    assert result["decision"] == {"useVisionContext": False, "reason": "NO_SELECTION_GAIN"}


def test_disabling_vision_preserves_identical_code_baseline():
    assert plan(architecture=architecture())["selectedPaths"] == plan()["selectedPaths"]


def test_actual_service_route_map_adds_target_without_vision():
    sources = dict(SOURCE)
    sources["services/profile/deployment.yaml"] += "routes:\n  /archive: archive\n"
    result = plan(sources)
    assert ARCHIVE in result["selectedPaths"]
    assert any(edge["reason"] == "CONFIG_ROUTE" for edge in result["coverage"]["routeEvidence"])


def test_shared_database_config_recovers_job_missing_from_diagram():
    sources = {**SOURCE, "jobs/export.py": "def run(rows): return list(rows)\n",
               "jobs/export.yaml": "job: exporter\ndatabase: profile_db\n"}
    result = plan(sources, architecture=architecture(), use_vision_context=True)
    assert "jobs/export.py" in result["selectedPaths"]
    assert any(edge["reason"] == "CONFIG_SHARED_DATABASE_CANDIDATE" for edge in result["coverage"]["routeEvidence"])


def test_shared_database_is_not_a_transitive_service_route():
    sources = {**SOURCE,
               "services/notify/deployment.yaml": "service: notify\nconsumes: [contact.changed]\ndatabase: common_db\n",
               "services/archive/deployment.yaml": "service: archive\ndatabase: common_db\n"}
    result = plan(sources)
    assert WORKER in result["selectedPaths"]
    assert ARCHIVE not in result["selectedPaths"]


def test_literal_dictionary_fields_and_sql_fields_work_without_python_identifier():
    sources = {**SOURCE,
               "services/legacy/export.py": "def export(row): return row['telephone']\n",
               "schema/history.sql": "CREATE TABLE history (telephone TEXT);\n",
               "config/audit.yaml": "fields: [telephone]\n",
               "docs/comments.py": "# telephone\nnote = 'unrelated'\n"}
    result = plan(sources)
    for path in ("services/legacy/export.py", "schema/history.sql", "config/audit.yaml"):
        assert path in result["selectedPaths"]
    assert "docs/comments.py" not in result["selectedPaths"]


def test_ambiguous_module_and_unknown_label_do_not_guess():
    sources = {**SOURCE, "apps/archive/job.py": "def execute(): pass\n"}
    value = architecture()
    value["components"].append({"id": "x", "label": "imaginary_service", "kind": "worker"})
    result = plan(sources, architecture=value, use_vision_context=True)
    assert ARCHIVE not in result["selectedPaths"]
    assert "apps/archive/job.py" not in result["selectedPaths"]
    assert result["mappingCount"]["ambiguous"] == 1
    assert result["mappingCount"]["unmatched"] == 1


def test_full_identifier_inside_display_label_matches_but_substrings_do_not():
    value = architecture()
    value["components"][0]["label"] = "profile | Python HTTP API"
    value["components"][2]["label"] = "archive_service_unknown"
    result = plan(architecture=value, use_vision_context=True)
    assert result["mapping"][0]["status"] == "MATCHED"
    assert result["mapping"][2]["status"] == "UNMATCHED"


@pytest.mark.parametrize("kind", ["WORKFLOW", "UNKNOWN"])
def test_non_architecture_falls_back_without_expansion(kind):
    value = {**architecture(), "diagramType": kind}
    result = plan(architecture=value, use_vision_context=True)
    assert result["selectedPaths"] == plan()["selectedPaths"]
    assert result["decision"]["reason"] == "NOT_SYSTEM_ARCHITECTURE"


def test_stale_context_and_invalid_paths_fall_back():
    result = plan(architecture=architecture(), use_vision_context=True,
                  expected_commit="new", context_commit="old")
    assert result["decision"]["reason"] == "STALE_CONTEXT"
    assert ARCHIVE not in result["selectedPaths"]
    value = {**architecture(), "codeHints": ["../../.env"]}
    result = plan(architecture=value, use_vision_context=True)
    assert result["decision"]["reason"] == "INVALID_CACHED_CONTEXT"
    assert result["selectedPaths"] == plan()["selectedPaths"]


def test_unknown_path_hint_never_becomes_selected_or_mandatory():
    value = {**architecture(), "codeHints": ["missing/private.py"]}
    result = plan(architecture=value, use_vision_context=True)
    assert "missing/private.py" not in result["selectedPaths"]
    assert "missing/private.py" not in result["mandatoryPaths"]
    assert {"hint": "missing/private.py", "status": "UNMATCHED_PATH"} in result["unmatched"]


@pytest.mark.parametrize("kind", ["database", "PostgreSQL storage", "Kafka broker"])
def test_infrastructure_label_cannot_impersonate_matching_module(kind):
    value = architecture()
    value["components"][2]["kind"] = kind
    result = plan(architecture=value, use_vision_context=True)
    assert ARCHIVE not in result["selectedPaths"]
    assert result["mapping"][2]["status"] == "UNMATCHED"
    assert result["mapping"][2]["reason"] == "NON_CODE_INFRASTRUCTURE_COMPONENT"


def test_shared_datastore_is_not_a_diagram_service_hub():
    value = architecture(flows=[])
    value["components"].append({"id": "db", "label": "Shared DB", "kind": "database"})
    value["flows"] = [{"from": "p", "to": "db", "data": "contacts", "protection": "UNKNOWN"},
                      {"from": "a", "to": "db", "data": "contacts", "protection": "UNKNOWN"}]
    result = plan(architecture=value, use_vision_context=True)
    assert ARCHIVE not in result["selectedPaths"]
    assert result["coverage"]["diagramIssues"]


@pytest.mark.parametrize("incoming,outgoing,expected", [
    ("contact.changed", "contact.changed", True),
    ("topic: contact.changed", "topic: contact.changed", True),
    ("contact.changed", "order.created", False),
    ("UNKNOWN", "UNKNOWN", False),
    ("telephone", "telephone", False),
])
def test_broker_requires_matching_explicit_topic_before_service_expansion(incoming, outgoing, expected):
    value = architecture(flows=[])
    value["components"].append({"id": "broker", "label": "Event Bus", "kind": "broker"})
    value["flows"] = [{"from": "p", "to": "broker", "data": incoming, "protection": "UNKNOWN"},
                      {"from": "broker", "to": "a", "data": outgoing, "protection": "UNKNOWN"}]
    result = plan(architecture=value, use_vision_context=True)
    assert (ARCHIVE in result["selectedPaths"]) is expected


def test_mandatory_evidence_is_preserved_over_budget_and_missing_is_not_ready():
    result = plan(scanner_paths=[WORKER], changed_paths=[ARCHIVE], max_files=1, max_bytes=1)
    assert set(result["selectedPaths"]) == {ANCHOR, WORKER, ARCHIVE}
    assert result["status"] == "NEEDS_BATCHING"
    assert not result["totals"]["withinBudget"]
    assert all(item["reason"] == "MANDATORY_OVER_BUDGET" for item in result["omittedCandidates"])
    result = plan(changed_paths=["missing/changed.py"])
    assert result["status"] == "MISSING_MANDATORY"
    assert result["unresolvedMandatory"] == ["missing/changed.py"]


def test_optional_omissions_are_explicit_and_within_byte_budget():
    limit = len(SOURCE[ANCHOR].encode()) + 1
    result = plan(max_files=2, max_bytes=limit)
    assert result["selectedPaths"] == [ANCHOR]
    assert result["totals"]["selectedBytes"] <= limit
    assert result["omittedCandidates"]
    assert result["coverage"]["unselectedManifestPaths"]


def test_safe_yaml_rejects_object_tags_and_tolerates_alias_cycle():
    sources = {**SOURCE,
               "services/notify/bad.yaml": "!!python/object/apply:os.system ['do not execute']\n",
               "services/notify/cycle.yaml": "produces: &recursive [*recursive]\n"}
    result = plan(sources)
    assert {"path": "services/notify/bad.yaml", "reason": "CONFIG_PARSE_FAILED"} in result["coverage"]["indexIssues"]
    assert result["status"] == "READY"


def test_inputs_and_iteration_order_do_not_change_or_mutate_plan():
    original = architecture()
    untouched = copy.deepcopy(original)
    result = plan(architecture=original, use_vision_context=True)
    reversed_sources = dict(reversed(list(SOURCE.items())))
    other = plan(reversed_sources, architecture=original, use_vision_context=True)
    assert result == other
    assert original == untouched


@pytest.mark.parametrize("kwargs", [{"max_files": 0}, {"max_bytes": True}, {"max_hops": 9}, {"use_vision_context": "yes"}])
def test_invalid_budgets_fail_before_planning(kwargs):
    with pytest.raises(ContextError, match="INVALID_ROUTING_INPUT"):
        plan(**kwargs)


def test_manifest_path_traversal_rejected_before_loading_config():
    with pytest.raises(ContextError, match="INVALID_MANIFEST_PATH"):
        plan({**SOURCE, "../../.env": "never read"})
