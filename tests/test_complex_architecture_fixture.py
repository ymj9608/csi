"""Behavioral checks for the generated corpus; no network/model execution."""
from __future__ import annotations

import ast
import importlib
import importlib.util
import json
from pathlib import Path
import sqlite3
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("complex_fixture_builder", ROOT / "scripts/build_complex_architecture_fixture.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


@pytest.fixture(scope="module")
def corpus(tmp_path_factory):
    temporary = tmp_path_factory.mktemp("complex-fixture")
    repository, metadata = temporary / "repository", temporary / "metadata"
    manifest = builder.build(repository, metadata)
    sys.path.insert(0, str(repository))
    try:
        yield repository, metadata, manifest
    finally:
        sys.path.remove(str(repository))
        for key in list(sys.modules):
            if key in {"services", "jobs"} or key.startswith(("services.", "jobs.")):
                del sys.modules[key]


class Logger:
    def __init__(self):
        self.lines = []

    def info(self, template, *values):
        self.lines.append(template % values)


class Bus:
    def __init__(self):
        self.events = []

    def publish(self, topic, envelope):
        self.events.append((topic, envelope))


class Transport:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return {"status": "accepted"}


def module(service, filename):
    return importlib.import_module(f"services.{service}.{filename}")


def database(corpus):
    repository, _, _ = corpus
    connection = sqlite3.connect(":memory:")
    connection.row_factory = sqlite3.Row
    connection.executescript((repository / "services/customer_profile/schema.sql").read_text())
    return connection


def profile_input():
    return {"record_id": "profile_demo", "owner_ref": "user_demo", "telephone": "SYNTHETIC_CONTACT_A"}


def actor():
    return {"subject": "user_demo", "scopes": ["update_contact"], "roles": []}


def test_generated_data_is_reproducible_and_matches_checked_manifest(corpus, tmp_path):
    _, _, manifest = corpus
    repeated = builder.build(tmp_path / "copy", tmp_path / "metadata")
    checked = json.loads((builder.DEST / "manifest.json").read_text())
    assert manifest == repeated == checked
    assert manifest["serviceCount"] == 24
    assert manifest["sourceFileCount"] == 320
    assert manifest["sourceBytes"] == 150114
    assert manifest["seed"] == 20261022


def test_all_generated_python_and_sql_parse(corpus):
    repository, _, manifest = corpus
    for entry in manifest["files"]:
        path = repository / entry["path"]
        source = path.read_text()
        if path.suffix == ".py":
            ast.parse(source, filename=entry["path"])
        elif path.suffix == ".sql":
            with sqlite3.connect(":memory:") as connection:
                connection.executescript(source)
    assert not (repository / "ground_truth.json").exists()
    assert not (repository / "graph.json").exists()


def test_phone_persists_and_reaches_each_positive_without_network(corpus):
    logger, bus, transport = Logger(), Bus(), Transport()
    with database(corpus) as connection:
        result = module("customer_profile", "service").execute(profile_input(), actor(), connection, bus, logger)
        assert result["status"] == "updated"
        row = connection.execute("SELECT telephone FROM profile_records").fetchone()
        assert row["telephone"] == "SYNTHETIC_CONTACT_A"
        assert "SYNTHETIC_CONTACT_A" in logger.lines[-1]
        module("contact_events", "bridge").relay(bus.events[-1][1], bus)
        module("notification_dispatch", "consumer").handle(bus.events[-1][1], bus, logger)
        assert "SYNTHETIC_CONTACT_A" in logger.lines[-1]
        module("sms_gateway", "consumer").handle(bus.events[-1][1], bus, transport, logger)
        assert transport.calls[-1][0].startswith("http://")
        assert transport.calls[-1][1]["json"]["to"] == "SYNTHETIC_CONTACT_A"
        assert importlib.import_module("jobs.legacy_export").export_snapshot(connection, transport) == 1
        assert transport.calls[-1][0] == "http://archive-partner.example.invalid/contact-export"
        assert transport.calls[-1][1]["json"] == [{"id": "profile_demo", "contact": "SYNTHETIC_CONTACT_A"}]


def test_three_matched_controls_avoid_targeted_leaks(corpus):
    logger, transport = Logger(), Transport()
    module("customer_profile", "service").record_completion(logger, "profile_demo")
    module("notification_dispatch", "consumer").record_outcome(logger, "event_demo", "accepted")
    assert all("SYNTHETIC_CONTACT_A" not in message for message in logger.lines)
    module("sms_gateway", "provider").deliver_private(
        {"destination": "SYNTHETIC_CONTACT_A", "template": "service_change"}, transport)
    assert transport.calls[0][0].startswith("https://")
    assert transport.calls[0][1]["verify"] is True


def test_cross_owner_update_does_not_store_publish_or_log(corpus):
    logger, bus = Logger(), Bus()
    unauthorized = dict(actor(), subject="different_demo")
    with database(corpus) as connection:
        with pytest.raises(PermissionError, match="owner mismatch"):
            module("customer_profile", "service").execute(profile_input(), unauthorized, connection, bus, logger)
        assert connection.execute("SELECT COUNT(*) FROM profile_records").fetchone()[0] == 0
    assert logger.lines == []
    assert bus.events == []


def test_graph_routes_have_inspectable_configuration(corpus):
    repository, metadata, _ = corpus
    graph = json.loads((metadata / "graph.json").read_text())
    truth = json.loads((metadata / "ground_truth.json").read_text())
    services = {domain[0] for domain in builder.DOMAINS}
    for edge in graph["edges"]:
        source, target = edge["from"], edge["to"]
        if edge["mode"] == "sync" and source in services and target in services:
            assert target in builder.HTTP_ROUTES[source].values()
        elif edge["mode"] == "async" and source in services and target in services:
            assert set(builder.TOPICS[source][1]).intersection(builder.TOPICS[target][0])
    assert len(graph["nodes"]) == 28
    assert len(graph["edges"]) == 26
    assert "legacy_export" not in {node["id"] for node in graph["nodes"]}
    assert (repository / "jobs/legacy_export.yaml").exists()
    assert sum(not row["diagram_visible"] for row in truth["positives"]) == 1
    assert len(truth["positives"]) == 4
    assert len(truth["negatives"]) == 3
    assert all(row["path"] in {entry["path"] for entry in truth["required_context_paths"]}
               for row in truth["positives"])


def test_truth_requires_contact_and_http_evidence_beyond_generic_sinks(corpus):
    repository, metadata, _ = corpus
    truth = json.loads((metadata / "ground_truth.json").read_text())
    checked = json.loads((builder.DEST / "ground_truth.json").read_text())
    assert truth == checked
    positives = {row["id"]: row for row in truth["positives"]}
    expected = {
        "PHONE-LOG-1": [("services/customer_profile/service.py", 12)],
        "PHONE-LOG-2": [("services/notification_dispatch/consumer.py", 7),
                        ("services/customer_profile/service.py", 13)],
        "PHONE-HTTP-1": [("services/sms_gateway/provider.py", 6),
                         ("services/sms_gateway/provider.py", 2),
                         ("services/sms_gateway/provider.py", 7)],
        "PHONE-HTTP-2": [("jobs/legacy_export.py", 8),
                         ("jobs/legacy_export.py", 2),
                         ("jobs/legacy_export.py", 6)],
    }
    for identifier, references in expected.items():
        actual = positives[identifier]["required_evidence"]
        assert [(ref["path"], ref["line_start"]) for ref in actual] == references
        assert all(ref["line_start"] == ref["line_end"] for ref in actual)
        assert all((repository / path).read_text().splitlines()[line - 1].strip() for path, line in references)


@pytest.mark.parametrize("service,check", [
    ("edge_gateway", lambda m: m.select_route("/profiles/one?trace=x", "GET", {"/profiles": "profile"}) == "profile"),
    ("identity_access", lambda m: m.effective_scopes(["read", "admin"], ["read"]) == {"read"}),
    ("consent_registry", lambda m: m.permitted([{"owner_ref": "u", "purpose": "marketing", "recorded_at": 1,
        "sequence": 1, "decision": "granted", "expires_at": 10}], "u", "marketing", 3)),
    ("customer_profile", lambda m: m.contact_patch({"version": 2, "telephone": "OLD"}, {"telephone": " NEW "}, 2)["telephone"] == "NEW"),
    ("contact_events", lambda m: m.validate_sequence(2, 4) == "gap"),
    ("notification_dispatch", lambda m: m.next_delivery_hour(23) == 8),
    ("sms_gateway", lambda m: m.message_segments("x" * 161) == 2),
    ("audit_archive", lambda m: m.expire_partitions(["2025-01", "2025-02"], "2025-03", {"2025-02"}) == ["2025-01"]),
    ("product_catalog", lambda m: str(m.quoted_price("10", "0.15")) == "8.50"),
    ("inventory_reservation", lambda m: m.allocate([{"id": "b", "available": 5, "received_at": 2},
        {"id": "a", "available": 2, "received_at": 1}], 3) == [{"bin_id": "a", "units": 2}, {"bin_id": "b", "units": 1}]),
    ("order_fulfillment", lambda m: m.advance("paid", "ship") == "shipped"),
    ("shipment_tracking", lambda m: m.current_stage([{"milestone": "delivered"}, {"milestone": "packed"}]) == "delivered"),
    ("billing_ledger", lambda m: str(m.invoice_totals([{"unit_price": "10", "quantity": 2}], "0.1")["total"]) == "22.00"),
    ("payment_settlement", lambda m: m.reconcile([{"payment_id": "p", "amount": 10, "currency": "KRW"}],
        [{"payment_id": "p", "amount": 10, "currency": "KRW"}]) == {"matched": ["p"], "exceptions": []}),
    ("fraud_review", lambda m: m.assess({"amount": 1000001, "device_changed": True}, 0)["decision"] == "hold"),
    ("merchant_registry", lambda m: m.missing_documents("wholesale", ["registration", "bank_proof"]) == ["trade_permit"]),
    ("returns_case", lambda m: m.eligible({"status": "delivered", "delivery_day": 1}, 8, "changed_mind")),
    ("support_case", lambda m: m.sla_deadline(10, "urgent") == 12),
    ("loyalty_rewards", lambda m: m.earned_points(1000, "gold", 200) == 24),
    ("marketing_campaign", lambda m: m.eligible_audience([{"owner_ref": "u", "marketing_consent": True,
        "consent_expires_at": 20}], "marketing", 10) == ["u"]),
    ("analytics_rollup", lambda m: m.suppress_small_groups([{"count": 2}, {"count": 5}]) == [{"count": 5}]),
    ("search_index", lambda m: m.tokenize("Red red Shoe") == ["red", "shoe"]),
    ("document_archive", lambda m: m.deletion_candidates([{"id": "d", "retention_class": "legal_hold", "created_day": 0}], 1000) == []),
    ("partner_webhook", lambda m: m.accept_delivery("done", {"done"}, lambda _: pytest.fail("duplicate executed"), b"{}") == "duplicate"),
])
def test_distinct_domain_behaviors(corpus, service, check):
    assert check(module(service, "domain"))


def test_failed_event_handler_does_not_mark_delivery_done(corpus):
    processed = set()

    def fail(_):
        raise RuntimeError("injected downstream failure")

    with pytest.raises(RuntimeError):
        module("partner_webhook", "domain").accept_delivery("new", processed, fail, b"{}")
    assert processed == set()


def test_optimistic_profile_update_rejects_stale_version(corpus):
    with pytest.raises(ValueError, match="stale profile"):
        module("customer_profile", "domain").contact_patch({"version": 3}, {"telephone": "DEMO"}, 2)
