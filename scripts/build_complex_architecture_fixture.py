#!/usr/bin/env python3
"""Reproduce a synthetic 24-service code corpus without network or real PII.

The generated application is an executable collection of dependency-injected
domain functions, not a production deployment. Labels and the graph are kept
outside the code corpus and must never be sent to the review model as answers.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
from pathlib import Path
import textwrap

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "tests/fixtures/complex_architecture"
DEFAULT_REPOSITORY = ROOT / ".runtime/architecture-benchmark/complex/repository"
DATASET_ID = "complex-commerce-contact-v1"
SEED = 20261022

# Each service has a distinct business field, constraint, transition, and event.
# The shared skeleton models a conventional service template, not random padding.
DOMAINS = [
    ("edge_gateway", "Request admission", "edge", "request", "route_key", "route is required", "len(value) <= 100", "admitted", "admit"),
    ("identity_access", "Identity and sessions", "edge", "session", "scope", "unsupported scope", "value in {'read', 'write', 'admin'}", "authenticated", "authenticate"),
    ("consent_registry", "Contact preferences", "edge", "consent", "purpose", "unsupported purpose", "value in {'service', 'marketing'}", "recorded", "record_consent"),
    ("customer_profile", "Customer contact records", "edge", "profile", "telephone", "contact value is required", "0 < len(value) <= 32", "updated", "update_contact"),
    ("contact_events", "Contact change events", "messaging", "envelope", "event_type", "unsupported event", "value in {'contact.updated', 'contact.removed'}", "published", "publish_change"),
    ("notification_dispatch", "Delivery scheduling", "messaging", "delivery", "channel", "unsupported channel", "value in {'sms', 'email'}", "scheduled", "schedule_delivery"),
    ("sms_gateway", "SMS provider adapter", "messaging", "message", "template_key", "template is required", "value.startswith('service_')", "submitted", "submit_message"),
    ("audit_archive", "Event retention", "messaging", "audit_event", "event_kind", "event kind is required", "len(value) <= 64", "archived", "archive_event"),
    ("product_catalog", "Product publication", "commerce", "product", "sku", "invalid SKU", "value.isalnum() and len(value) <= 20", "published", "publish_product"),
    ("inventory_reservation", "Stock reservation", "commerce", "reservation", "warehouse", "unknown warehouse", "value in {'north', 'south', 'central'}", "reserved", "reserve_stock"),
    ("order_fulfillment", "Order orchestration", "commerce", "order", "fulfillment", "unsupported fulfillment", "value in {'ship', 'collect'}", "accepted", "accept_order"),
    ("shipment_tracking", "Carrier milestones", "commerce", "shipment", "milestone", "unsupported milestone", "value in {'packed', 'dispatched', 'delivered'}", "tracked", "track_shipment"),
    ("billing_ledger", "Invoice accounting", "finance", "invoice", "currency", "unsupported currency", "value in {'KRW', 'USD', 'EUR'}", "posted", "post_invoice"),
    ("payment_settlement", "Settlement batches", "finance", "settlement", "processor", "unsupported processor", "value in {'bank_a', 'bank_b'}", "reconciled", "reconcile_settlement"),
    ("fraud_review", "Transaction review", "finance", "review", "decision", "unsupported decision", "value in {'allow', 'hold', 'deny'}", "decided", "decide_review"),
    ("merchant_registry", "Merchant onboarding", "finance", "merchant", "business_type", "unsupported business type", "value in {'retail', 'wholesale', 'service'}", "registered", "register_merchant"),
    ("returns_case", "Return authorization", "engagement", "return_case", "reason", "unsupported return reason", "value in {'damaged', 'wrong_item', 'changed_mind'}", "authorized", "authorize_return"),
    ("support_case", "Support assignment", "engagement", "ticket", "priority", "unsupported priority", "value in {'low', 'normal', 'urgent'}", "assigned", "assign_ticket"),
    ("loyalty_rewards", "Reward accrual", "engagement", "reward", "tier", "unsupported tier", "value in {'basic', 'silver', 'gold'}", "accrued", "accrue_reward"),
    ("marketing_campaign", "Campaign planning", "engagement", "campaign", "audience", "unsupported audience", "value in {'opted_in', 'internal_test'}", "planned", "plan_campaign"),
    ("analytics_rollup", "Aggregate reporting", "data", "rollup", "period", "unsupported period", "value in {'hour', 'day', 'month'}", "aggregated", "aggregate_rollup"),
    ("search_index", "Product search", "data", "index_job", "operation", "unsupported operation", "value in {'upsert', 'delete'}", "indexed", "index_product"),
    ("document_archive", "Document lifecycle", "data", "document", "retention_class", "unsupported retention class", "value in {'short', 'standard', 'legal_hold'}", "stored", "store_document"),
    ("partner_webhook", "Partner callbacks", "data", "callback", "partner_key", "invalid partner key", "value.startswith('partner_')", "queued", "queue_callback"),
]

TOPICS = {
    "customer_profile": ([], ["contact.changed"]),
    "contact_events": (["contact.changed"], ["delivery.requested"]),
    "notification_dispatch": (["delivery.requested"], ["sms.requested"]),
    "sms_gateway": (["sms.requested"], ["delivery.completed"]),
    "audit_archive": (["delivery.completed", "order.accepted"], []),
    "product_catalog": ([], ["product.published"]),
    "search_index": (["product.published"], []),
    "order_fulfillment": ([], ["order.accepted"]),
    "inventory_reservation": (["order.accepted"], ["inventory.reserved"]),
    "shipment_tracking": (["inventory.reserved"], ["shipment.delivered"]),
    "billing_ledger": (["order.accepted"], ["invoice.posted"]),
    "payment_settlement": (["invoice.posted"], ["payment.settled"]),
    "fraud_review": (["payment.settled"], ["review.decided"]),
    "loyalty_rewards": (["shipment.delivered"], ["reward.accrued"]),
    "analytics_rollup": (["reward.accrued", "payment.settled"], []),
}

HTTP_ROUTES = {
    "edge_gateway": {"/profiles": "customer_profile", "/sessions": "identity_access", "/products": "product_catalog", "/orders": "order_fulfillment"},
    "customer_profile": {"/contact-purpose": "consent_registry"},
    "support_case": {"/returns": "returns_case"},
    "marketing_campaign": {"/audience-permission": "consent_registry"},
    "merchant_registry": {"/onboarding-documents": "document_archive"},
    "partner_webhook": {"/carrier-status": "shipment_tracking"},
}

# These operations differ in behavior, not only names. They are intentionally
# small and deterministic so the fixture can be checked without external tools.
BUSINESS_OPERATIONS = {
    "edge_gateway": '''
        from urllib.parse import urlsplit


        def select_route(raw_path, method, routes):
            path = urlsplit(raw_path).path
            if ".." in path.split("/") or method not in {"GET", "POST", "PUT", "DELETE"}:
                raise ValueError("unsupported request")
            matches = [(prefix, target) for prefix, target in routes.items()
                       if path == prefix or path.startswith(prefix + "/")]
            return max(matches, key=lambda entry: len(entry[0]))[1] if matches else None


        def admit(bucket, subject, now, capacity=20, window=60):
            previous = [stamp for stamp in bucket.get(subject, []) if now - stamp < window]
            allowed = len(previous) < capacity
            bucket[subject] = previous + ([now] if allowed else [])
            return allowed
    ''',
    "identity_access": '''
        import hmac


        def effective_scopes(requested, assigned, suspended=False):
            if suspended:
                return frozenset()
            return frozenset(requested).intersection(assigned)


        def valid_session(stored, presented_token_digest, now):
            if stored is None or stored["revoked"] or stored["expires_at"] <= now:
                return False
            return hmac.compare_digest(stored["token_digest"], presented_token_digest)


        def revoke_owner_sessions(sessions, owner_ref):
            return [dict(session, revoked=True) if session["owner_ref"] == owner_ref else dict(session)
                    for session in sessions]
    ''',
    "consent_registry": '''
        def permitted(events, owner_ref, purpose, now):
            matching = [event for event in events if event["owner_ref"] == owner_ref
                        and event["purpose"] == purpose and event["recorded_at"] <= now]
            if not matching:
                return False
            latest = max(matching, key=lambda event: (event["recorded_at"], event["sequence"]))
            return latest["decision"] == "granted" and latest["expires_at"] > now


        def append_decision(events, event):
            if event["decision"] not in {"granted", "revoked"}:
                raise ValueError("unknown consent decision")
            if any(previous["event_id"] == event["event_id"] for previous in events):
                return list(events)
            return [*events, dict(event)]
    ''',
    "customer_profile": '''
        def contact_patch(existing, incoming, expected_version):
            if existing["version"] != expected_version:
                raise ValueError("stale profile")
            unknown = set(incoming) - {"telephone", "display_name"}
            if unknown:
                raise ValueError("unsupported profile fields")
            updated = dict(existing)
            for key, value in incoming.items():
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("empty contact field")
                updated[key] = value.strip()
            updated["version"] += 1
            return updated


        def public_projection(record):
            return {key: record[key] for key in ("record_id", "display_name", "version") if key in record}
    ''',
    "contact_events": '''
        def changed_fields(before, after):
            return sorted(key for key in {"telephone", "display_name"} if before.get(key) != after.get(key))


        def accept_once(envelope, processed, publish):
            key = (envelope["id"], envelope["type"])
            if key in processed:
                return False
            publish(envelope)
            processed.add(key)
            return True


        def validate_sequence(last_version, incoming_version):
            if incoming_version <= last_version:
                return "duplicate"
            return "ready" if incoming_version == last_version + 1 else "gap"
    ''',
    "notification_dispatch": '''
        def next_delivery_hour(requested_hour, quiet_start=22, quiet_end=8):
            if not 0 <= requested_hour < 24 or not 0 <= quiet_end < quiet_start < 24:
                raise ValueError("invalid delivery window")
            return quiet_end if requested_hour >= quiet_start or requested_hour < quiet_end else requested_hour


        def schedule_batch(requests, already_sent, maximum=100):
            if not 1 <= maximum <= 100:
                raise ValueError("invalid batch size")
            result, seen = [], set(already_sent)
            for request in sorted(requests, key=lambda item: (item["priority"], item["created_at"])):
                if request["id"] not in seen:
                    result.append(dict(request))
                    seen.add(request["id"])
                if len(result) == maximum:
                    break
            return result
    ''',
    "sms_gateway": '''
        def message_segments(text):
            if not isinstance(text, str) or not text:
                raise ValueError("empty message")
            ascii_only = all(ord(character) < 128 for character in text)
            single, multipart = (160, 153) if ascii_only else (70, 67)
            return 1 if len(text) <= single else (len(text) + multipart - 1) // multipart


        def classify_response(status, retry_after=None):
            if 200 <= status < 300:
                return {"state": "accepted", "retry": False}
            if status == 429 or 500 <= status < 600:
                return {"state": "deferred", "retry": True, "delay": min(max(retry_after or 5, 1), 300)}
            return {"state": "rejected", "retry": False}
    ''',
    "audit_archive": '''
        def partition_for(event):
            date = event["occurred_on"]
            if len(date) != 10 or date[4] != "-" or date[7] != "-":
                raise ValueError("expected ISO date")
            return date[:7]


        def expire_partitions(partitions, cutoff_month, legal_holds):
            return sorted(name for name in partitions if name < cutoff_month and name not in legal_holds)


        def event_projection(event):
            allowed = ("event_id", "event_kind", "occurred_on", "status")
            return {key: event[key] for key in allowed if key in event}
    ''',
    "product_catalog": '''
        from decimal import Decimal, ROUND_HALF_UP


        def quoted_price(base, discount_rate):
            base, discount_rate = Decimal(str(base)), Decimal(str(discount_rate))
            if base < 0 or not 0 <= discount_rate <= 1:
                raise ValueError("invalid price")
            return (base * (1 - discount_rate)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


        def publishable(product):
            required = ("sku", "title", "category")
            return all(product.get(key) for key in required) and product.get("price", -1) >= 0


        def visible_variants(variants):
            return sorted((item for item in variants if item["active"]), key=lambda item: item["sku"])
    ''',
    "inventory_reservation": '''
        def allocate(bins, quantity):
            if quantity <= 0:
                raise ValueError("quantity must be positive")
            if sum(item["available"] for item in bins) < quantity:
                raise ValueError("insufficient stock")
            result, remaining = [], quantity
            for item in sorted(bins, key=lambda row: row["received_at"]):
                units = min(remaining, item["available"])
                if units:
                    result.append({"bin_id": item["id"], "units": units})
                    remaining -= units
                if remaining == 0:
                    break
            return result


        def release(reservation, now):
            return reservation["state"] == "held" and reservation["expires_at"] <= now
    ''',
    "order_fulfillment": '''
        def total_units(lines):
            if not lines or any(line["quantity"] <= 0 for line in lines):
                raise ValueError("invalid order lines")
            return sum(line["quantity"] for line in lines)


        def advance(current, event):
            transitions = {("new", "reserve"): "reserved", ("reserved", "pay"): "paid",
                           ("paid", "ship"): "shipped", ("new", "cancel"): "cancelled",
                           ("reserved", "cancel"): "cancelled"}
            if (current, event) not in transitions:
                raise ValueError("invalid order transition")
            return transitions[(current, event)]


        def shipment_groups(lines):
            groups = {}
            for line in lines:
                groups.setdefault(line["warehouse"], []).append(dict(line))
            return groups
    ''',
    "shipment_tracking": '''
        def apply_milestone(history, incoming):
            if any(item["event_id"] == incoming["event_id"] for item in history):
                return list(history)
            stages = ("packed", "dispatched", "delivered")
            if incoming["milestone"] not in stages:
                raise ValueError("unknown milestone")
            return sorted([*history, dict(incoming)], key=lambda item: item["occurred_at"])


        def current_stage(history):
            if not history:
                return "pending"
            stages = {"packed": 1, "dispatched": 2, "delivered": 3}
            return max(history, key=lambda item: stages[item["milestone"]])["milestone"]
    ''',
    "billing_ledger": '''
        from decimal import Decimal, ROUND_HALF_UP


        def invoice_totals(lines, tax_rate):
            rate = Decimal(str(tax_rate))
            if not 0 <= rate <= 1:
                raise ValueError("invalid tax rate")
            subtotal = sum((Decimal(str(line["unit_price"])) * line["quantity"] for line in lines), Decimal(0))
            if subtotal < 0:
                raise ValueError("negative invoice")
            tax = (subtotal * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            return {"subtotal": subtotal, "tax": tax, "total": subtotal + tax}


        def balanced(entries):
            return sum(entry["debit"] - entry["credit"] for entry in entries) == 0
    ''',
    "payment_settlement": '''
        def reconcile(expected, received):
            received_by_id = {item["payment_id"]: item for item in received}
            if len(received_by_id) != len(received):
                raise ValueError("duplicate processor row")
            matched, exceptions = [], []
            for row in expected:
                actual = received_by_id.pop(row["payment_id"], None)
                if actual and actual["amount"] == row["amount"] and actual["currency"] == row["currency"]:
                    matched.append(row["payment_id"])
                else:
                    exceptions.append({"payment_id": row["payment_id"], "reason": "amount_or_missing"})
            exceptions.extend({"payment_id": key, "reason": "unexpected"} for key in received_by_id)
            return {"matched": matched, "exceptions": exceptions}
    ''',
    "fraud_review": '''
        def assess(transaction, recent_attempts):
            reasons = []
            if transaction["amount"] > 1000000:
                reasons.append("high_value")
            if recent_attempts >= 5:
                reasons.append("velocity")
            if transaction.get("device_changed"):
                reasons.append("new_device")
            return {"decision": "hold" if len(reasons) >= 2 else "allow", "reasons": reasons}


        def resolve(review, decision, reviewer):
            if decision not in {"allow", "deny"} or not reviewer:
                raise ValueError("reviewer decision required")
            return dict(review, decision=decision, reviewer=reviewer)
    ''',
    "merchant_registry": '''
        def missing_documents(business_type, submitted):
            required = {"retail": {"registration", "bank_proof"},
                        "wholesale": {"registration", "bank_proof", "trade_permit"},
                        "service": {"registration", "bank_proof"}}
            if business_type not in required:
                raise ValueError("unsupported business type")
            return sorted(required[business_type] - set(submitted))


        def onboarding_state(record):
            if record.get("suspended"):
                return "suspended"
            return "active" if not missing_documents(record["business_type"], record["documents"]) else "pending"
    ''',
    "returns_case": '''
        def eligible(order, now_day, reason):
            if reason not in {"damaged", "wrong_item", "changed_mind"}:
                raise ValueError("unknown return reason")
            if order["status"] != "delivered" or order.get("returned"):
                return False
            window = 30 if reason in {"damaged", "wrong_item"} else 7
            return 0 <= now_day - order["delivery_day"] <= window


        def refund_amount(unit_price, returned_units, purchased_units):
            if not 0 < returned_units <= purchased_units:
                raise ValueError("invalid returned quantity")
            return unit_price * returned_units
    ''',
    "support_case": '''
        def assign_queue(ticket):
            if ticket["category"] == "payment":
                return "billing_specialists"
            if ticket["category"] in {"shipment", "return"}:
                return "fulfillment_support"
            return "general_support"


        def sla_deadline(created_hour, priority):
            targets = {"low": 72, "normal": 24, "urgent": 2}
            if priority not in targets:
                raise ValueError("unknown priority")
            return created_hour + targets[priority]


        def overdue(tickets, now_hour):
            return [item["id"] for item in tickets if item["state"] != "closed"
                    and sla_deadline(item["created_hour"], item["priority"]) < now_hour]
    ''',
    "loyalty_rewards": '''
        def earned_points(paid_units, tier, refunded_units=0):
            multipliers = {"basic": 1, "silver": 2, "gold": 3}
            if tier not in multipliers or not 0 <= refunded_units <= paid_units:
                raise ValueError("invalid reward input")
            return (paid_units - refunded_units) // 100 * multipliers[tier]


        def apply_reward(balance, amount, event_id, processed):
            if event_id in processed:
                return balance
            if balance + amount < 0:
                raise ValueError("insufficient reward balance")
            processed.add(event_id)
            return balance + amount
    ''',
    "marketing_campaign": '''
        def eligible_audience(records, purpose, now):
            if purpose != "marketing":
                raise ValueError("campaign purpose mismatch")
            return [row["owner_ref"] for row in records if row.get("marketing_consent")
                    and row["consent_expires_at"] > now and not row.get("suppressed")]


        def allocate_variants(owner_refs, variant_count):
            import hashlib
            if not 1 <= variant_count <= 10:
                raise ValueError("invalid experiment size")
            return {ref: int.from_bytes(hashlib.sha256(ref.encode()).digest()[:4], "big") % variant_count
                    for ref in sorted(set(owner_refs))}
    ''',
    "analytics_rollup": '''
        def aggregate(rows):
            totals = {}
            for row in rows:
                key = (row["period"], row["currency"])
                target = totals.setdefault(key, {"count": 0, "amount": 0})
                target["count"] += 1
                target["amount"] += row["amount"]
            return [{"period": key[0], "currency": key[1], **value} for key, value in sorted(totals.items())]


        def suppress_small_groups(rollups, minimum=5):
            if minimum < 2:
                raise ValueError("minimum aggregate size must exceed one")
            return [dict(row) for row in rollups if row["count"] >= minimum]
    ''',
    "search_index": '''
        import re


        def tokenize(title):
            return sorted(set(re.findall(r"[a-z0-9]{2,}", title.lower())))


        def build_document(product):
            return {"id": product["sku"], "tokens": tokenize(product["title"]),
                    "category": product["category"], "active": bool(product["active"])}


        def rank(query, documents):
            terms = set(tokenize(query))
            scored = [(len(terms.intersection(document["tokens"])), document["id"])
                      for document in documents if document["active"]]
            return [ident for score, ident in sorted(scored, key=lambda row: (-row[0], row[1])) if score]
    ''',
    "document_archive": '''
        import hashlib


        def content_digest(content):
            return hashlib.sha256(content).hexdigest()


        def deletion_candidates(records, now_day):
            lifetimes = {"short": 30, "standard": 365}
            return [record["id"] for record in records if record["retention_class"] in lifetimes
                    and now_day - record["created_day"] > lifetimes[record["retention_class"]]]


        def verify_download(content, expected_digest):
            import hmac
            return hmac.compare_digest(content_digest(content), expected_digest)
    ''',
    "partner_webhook": '''
        import hashlib
        import hmac


        def verify_signature(body, supplied, secret, timestamp, now):
            if abs(now - timestamp) > 300:
                return False
            signed = str(timestamp).encode() + b"." + body
            expected = hmac.new(secret, signed, hashlib.sha256).hexdigest()
            return hmac.compare_digest(expected, supplied)


        def accept_delivery(delivery_id, processed, handler, body):
            if delivery_id in processed:
                return "duplicate"
            handler(body)
            processed.add(delivery_id)
            return "accepted"
    ''',
}


def clean(value: str) -> str:
    return textwrap.dedent(value).strip() + "\n"


def service_sources(domain: tuple) -> dict[str, str]:
    service, role, group, entity, field, error, condition, state, action = domain
    table = entity + "_records"
    base = f"services/{service}/"
    imports = f"services.{service}"
    consumes, produces = TOPICS.get(service, ([], [entity + "." + state]))
    topic = produces[0] if produces else service + ".internal"
    files = {
        "domain.py": BUSINESS_OPERATIONS[service],
        "models.py": f'''
            """Domain record for {role.lower()}."""
            from dataclasses import dataclass


            @dataclass(frozen=True)
            class Record:
                record_id: str
                owner_ref: str
                {field}: str
                version: int = 1

                def as_mapping(self):
                    return {{"record_id": self.record_id, "owner_ref": self.owner_ref,
                            "{field}": self.{field}, "version": self.version}}
        ''',
        "validation.py": f'''
            """Validate {entity} input without performing network I/O."""
            from {imports}.models import Record


            def parse_record(body):
                value = body.get("{field}", "")
                if not isinstance(value, str) or not ({condition}):
                    raise ValueError("{error}")
                if not isinstance(body.get("record_id"), str) or not body["record_id"]:
                    raise ValueError("record_id is required")
                if not isinstance(body.get("owner_ref"), str) or not body["owner_ref"]:
                    raise ValueError("owner_ref is required")
                return Record(body["record_id"], body["owner_ref"], value)
        ''',
        "repository.py": f'''
            """Bound-parameter persistence for {table}; caller owns transaction."""


            def save(db, record):
                db.execute(
                    "INSERT INTO {table} (record_id, owner_ref, {field}, version) VALUES (?, ?, ?, ?) "
                    "ON CONFLICT(record_id) DO UPDATE SET {field}=excluded.{field}, version=version+1",
                    (record.record_id, record.owner_ref, record.{field}, record.version),
                )


            def find(db, record_id):
                return db.execute("SELECT * FROM {table} WHERE record_id = ?", (record_id,)).fetchone()


            def for_owner(db, owner_ref):
                return db.execute("SELECT record_id, version FROM {table} WHERE owner_ref = ?", (owner_ref,)).fetchall()
        ''',
        "policy.py": f'''
            """Authorization rules for {action}; not a legal compliance decision."""
            ACTION = "{action}"


            def authorize(actor, owner_ref):
                if not actor or ACTION not in actor.get("scopes", ()):
                    raise PermissionError("missing {action} scope")
                if actor.get("subject") != owner_ref and "operator" not in actor.get("roles", ()):
                    raise PermissionError("owner mismatch")


            def may_retry(attempts, transient):
                return transient and 0 <= attempts < 3
        ''',
        "service.py": f'''
            """Perform one {role.lower()} transition using injected ports."""
            from {imports}.policy import authorize
            from {imports}.repository import save
            from {imports}.events import publish
            from {imports}.validation import parse_record


            def execute(body, actor, db, bus, logger):
                record = parse_record(body)
                authorize(actor, record.owner_ref)
                save(db, record)
                publish(bus, record.record_id, {{"owner_ref": record.owner_ref}})
                logger.info("{entity} {state} id=%s", record.record_id)
                return {{"id": record.record_id, "status": "{state}"}}
        ''',
        "api.py": f'''
            """HTTP adapter contract for {role.lower()}; no server is started."""
            from {imports}.service import execute
            from {imports}.readmodel import detail


            def post(body, actor, ports):
                result = execute(body, actor, ports.db, ports.bus, ports.logger)
                return 202, result


            def get(record_id, actor, ports):
                result = detail(ports.db, actor, record_id)
                return (200, result) if result is not None else (404, {{"error": "not_found"}})
        ''',
        "events.py": f'''
            """Broker boundary for {service}; event body is an injected mapping."""
            TOPIC = "{topic}"
            CONSUMES = {consumes!r}


            def publish(bus, correlation_id, payload):
                envelope = {{"id": correlation_id, "type": TOPIC, "body": dict(payload)}}
                bus.publish(TOPIC, envelope)
                return envelope


            def accept(envelope):
                if envelope.get("type") not in CONSUMES:
                    raise ValueError("unsupported event type")
                return dict(envelope["body"])
        ''',
        "jobs.py": f'''
            """Bounded retry scheduler for {entity} work."""
            from {imports}.policy import may_retry


            def retry_failed(queue, handler, limit=20):
                if not 1 <= limit <= 100:
                    raise ValueError("invalid batch size")
                completed = 0
                for item in queue.take(limit):
                    if not may_retry(item.attempts, item.transient):
                        queue.park(item.id, "retry_exhausted")
                        continue
                    handler(item.payload)
                    queue.ack(item.id)
                    completed += 1
                return completed
        ''',
        "metrics.py": f'''
            """Low-cardinality operational metrics for {service}."""
            SERVICE = "{service}"
            ALLOWED_STATES = ("{state}", "rejected", "retry")


            def report(sink, state, elapsed_ms):
                if state not in ALLOWED_STATES or elapsed_ms < 0:
                    raise ValueError("invalid metric")
                sink.increment("operations", service=SERVICE, state=state)
                sink.observe("duration_ms", elapsed_ms, service=SERVICE)
        ''',
        "readmodel.py": f'''
            """Owner-scoped read projection for {entity} records."""
            from {imports}.repository import find
            from {imports}.policy import authorize


            def detail(db, actor, record_id):
                row = find(db, record_id)
                if row is None:
                    return None
                authorize(actor, row["owner_ref"])
                return {{"id": row["record_id"], "{field}": row["{field}"], "version": row["version"]}}
        ''',
        "schema.sql": f'''
            CREATE TABLE {table} (
                record_id TEXT PRIMARY KEY,
                owner_ref TEXT NOT NULL,
                {field} TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0)
            );
            CREATE INDEX {table}_owner ON {table}(owner_ref);
        ''',
        "deployment.yaml": f'''
            service: {service}
            role: {role}
            group: {group}
            runtime: python3
            transport: http
            listens_on: 8080
            database: {"profile_db" if service == "customer_profile" else "business_db"}
            consumes: {json.dumps(consumes)}
            produces: {json.dumps(produces)}
            routes: {json.dumps(HTTP_ROUTES.get(service, {}))}
            max_inflight: 16
            retry_limit: 3
            health_path: /health
        ''',
    }
    return {base + name: clean(source) for name, source in files.items()}


def specialized_sources() -> dict[str, str]:
    return {path: clean(source) for path, source in {
        "services/customer_profile/service.py": '''
            """Update contact data and publish the durable contact-change record."""
            from services.customer_profile.policy import authorize
            from services.customer_profile.repository import save
            from services.customer_profile.validation import parse_record
            from services.customer_profile.events import publish


            def execute(body, actor, db, bus, logger):
                record = parse_record(body)
                authorize(actor, record.owner_ref)
                save(db, record)
                logger.info("profile updated telephone=%s", record.telephone)
                publish(bus, record.record_id, {"destination": record.telephone,
                                               "owner_ref": record.owner_ref, "template": "service_change"})
                return {"id": record.record_id, "status": "updated"}


            def record_completion(logger, record_id):
                logger.info("profile update completed id=%s", record_id)
        ''',
        "services/contact_events/bridge.py": '''
            """Translate the contact-change contract into a delivery contract."""
            from services.contact_events.events import accept, publish


            def relay(envelope, bus):
                payload = accept(envelope)
                return publish(bus, envelope["id"], {
                    "destination": payload["destination"],
                    "template": payload["template"],
                    "owner_ref": payload["owner_ref"],
                })
        ''',
        "services/notification_dispatch/consumer.py": '''
            """Schedule a received delivery request; broker client is injected."""
            from services.notification_dispatch.events import accept, publish


            def handle(envelope, bus, logger):
                payload = accept(envelope)
                logger.info("dispatch payload=%s", payload)
                return publish(bus, envelope["id"], payload)


            def record_outcome(logger, envelope_id, outcome):
                if outcome not in ("accepted", "rejected"):
                    raise ValueError("invalid outcome")
                logger.info("dispatch id=%s outcome=%s", envelope_id, outcome)
        ''',
        "services/sms_gateway/provider.py": '''
            """External message adapter; injected transport is never invoked at import."""
            ENDPOINT = "http://sms-provider.example.invalid/v1/messages"


            def deliver(payload, transport):
                return transport.post(ENDPOINT, json={
                    "to": payload["destination"], "template": payload["template"]
                }, timeout=5)


            def deliver_private(payload, transport):
                endpoint = "https://sms-provider.example.invalid/v1/messages"
                return transport.post(endpoint, json={
                    "to": payload["destination"], "template": payload["template"]
                }, timeout=5, verify=True)
        ''',
        "services/sms_gateway/consumer.py": '''
            """Complete the event-driven delivery path."""
            from services.sms_gateway.events import accept, publish
            from services.sms_gateway.provider import deliver


            def handle(envelope, bus, transport, logger):
                payload = accept(envelope)
                result = deliver(payload, transport)
                logger.info("delivery completed id=%s", envelope["id"])
                publish(bus, envelope["id"], {"status": "submitted"})
                return result
        ''',
        "jobs/legacy_export.py": '''
            """Scheduled compatibility export; not connected to the broker routes."""
            ENDPOINT = "http://archive-partner.example.invalid/contact-export"


            def export_snapshot(db, transport):
                rows = db.execute("SELECT record_id, telephone FROM profile_records").fetchall()
                body = [{"id": row["record_id"], "contact": row["telephone"]} for row in rows]
                transport.post(ENDPOINT, json=body, timeout=10)
                return len(body)
        ''',
        "jobs/legacy_export.yaml": '''
            job: legacy_export
            schedule: nightly
            entrypoint: jobs.legacy_export:export_snapshot
            database: profile_db
            purpose: compatibility_archive
            retry_limit: 1
        ''',
        "infra/gateway_routes.yaml": '''
            routes:
              /profiles: customer_profile
              /sessions: identity_access
              /consents: consent_registry
              /products: product_catalog
              /orders: order_fulfillment
              /tickets: support_case
        ''',
        "infra/broker.yaml": '''
            broker: kafka
            delivery_semantics: at_least_once
            topic_configs:
              contact.changed: {partitions: 6, retention_hours: 24}
              delivery.requested: {partitions: 6, retention_hours: 24}
              sms.requested: {partitions: 6, retention_hours: 24}
              delivery.completed: {partitions: 3, retention_hours: 48}
              order.accepted: {partitions: 6, retention_hours: 48}
        ''',
    }.items()}


def graph_document() -> dict:
    labels = {"edge": "Customer and identity", "messaging": "Contact delivery",
              "commerce": "Commerce operations", "finance": "Finance and merchants",
              "engagement": "Customer engagement", "data": "Data products"}
    nodes = [{"id": d[0], "label": d[1], "kind": "SERVICE", "group": d[2], "technology": "Python API"}
             for d in DOMAINS]
    nodes += [
        {"id": "profile_db", "label": "Customer data", "kind": "DATABASE", "group": "edge", "technology": "SQL"},
        {"id": "kafka", "label": "Event broker", "kind": "MESSAGE_QUEUE", "group": "messaging", "technology": "Kafka"},
        {"id": "external_sms", "label": "External message provider", "kind": "EXTERNAL_SERVICE", "group": "messaging", "technology": "HTTP API"},
        {"id": "business_db", "label": "Business records", "kind": "DATABASE", "group": "commerce", "technology": "SQL"},
    ]
    raw = [
        ("edge_gateway", "customer_profile", "contact update", "sync"),
        ("edge_gateway", "identity_access", "session validation", "sync"),
        ("customer_profile", "consent_registry", "contact purpose", "sync"),
        ("customer_profile", "profile_db", "contact storage", "sync"),
        ("customer_profile", "contact_events", "contact.changed", "async"),
        ("contact_events", "kafka", "delivery.requested", "async"),
        ("kafka", "notification_dispatch", "delivery.requested", "async"),
        ("notification_dispatch", "sms_gateway", "sms.requested", "async"),
        ("sms_gateway", "external_sms", "message delivery", "sync"),
        ("sms_gateway", "audit_archive", "delivery.completed", "async"),
        ("edge_gateway", "product_catalog", "product browse", "sync"),
        ("edge_gateway", "order_fulfillment", "order request", "sync"),
        ("product_catalog", "search_index", "product.published", "async"),
        ("order_fulfillment", "inventory_reservation", "order.accepted", "async"),
        ("inventory_reservation", "shipment_tracking", "inventory.reserved", "async"),
        ("order_fulfillment", "billing_ledger", "order.accepted", "async"),
        ("billing_ledger", "payment_settlement", "invoice.posted", "async"),
        ("payment_settlement", "fraud_review", "payment.settled", "async"),
        ("payment_settlement", "analytics_rollup", "payment.settled", "async"),
        ("shipment_tracking", "loyalty_rewards", "shipment.delivered", "async"),
        ("loyalty_rewards", "analytics_rollup", "reward.accrued", "async"),
        ("order_fulfillment", "business_db", "order persistence", "sync"),
        ("support_case", "returns_case", "return authorization", "sync"),
        ("marketing_campaign", "consent_registry", "audience permission", "sync"),
        ("merchant_registry", "document_archive", "onboarding records", "sync"),
        ("partner_webhook", "shipment_tracking", "carrier status", "sync"),
    ]
    return {"schemaVersion": 1, "datasetId": DATASET_ID, "synthetic": True,
            "title": "Synthetic commerce platform — service and data flow",
            "groups": [{"id": key, "label": val} for key, val in labels.items()],
            "nodes": nodes, "edges": [{"from": a, "to": b, "label": label, "mode": mode} for a, b, label, mode in raw],
            "notes": ["Logical async edges may pass through the shared broker.",
                      "This diagram is not a security verdict or an exhaustive job inventory."]}


def function_span(source: str, name: str) -> tuple[int, int]:
    node = next(node for node in ast.walk(ast.parse(source)) if isinstance(node, ast.FunctionDef) and node.name == name)
    return node.lineno, node.end_lineno


def ground_truth(sources: dict[str, str]) -> dict:
    positives = [
        ("PHONE-LOG-1", "sensitive_logging", "services/customer_profile/service.py", "execute", "logger.info(\"profile updated telephone", True,
         "Contact update writes the complete telephone value to the logger."),
        ("PHONE-LOG-2", "sensitive_logging", "services/notification_dispatch/consumer.py", "handle", "logger.info(\"dispatch payload", True,
         "Consumer logs the entire delivery payload, including destination carried from telephone."),
        ("PHONE-HTTP-1", "plaintext_pii_export", "services/sms_gateway/provider.py", "deliver", "return transport.post(ENDPOINT", True,
         "The external provider endpoint is HTTP and the request contains the contact destination."),
        ("PHONE-HTTP-2", "plaintext_pii_export", "jobs/legacy_export.py", "export_snapshot", "transport.post(ENDPOINT", False,
         "An off-diagram scheduled job sends persisted telephone values to an external HTTP endpoint."),
    ]
    controls = [
        ("SAFE-LOG-1", "services/customer_profile/service.py", "record_completion", "Logs only the synthetic record identifier, not contact data."),
        ("SAFE-LOG-2", "services/notification_dispatch/consumer.py", "record_outcome", "Logs bounded outcome and event identifier, not the payload."),
        ("SAFE-TLS-1", "services/sms_gateway/provider.py", "deliver_private", "Uses HTTPS with certificate verification; destination handling alone is not a plaintext-transport finding."),
    ]
    supporting_requirements = {
        "PHONE-LOG-2": [
            ("services/customer_profile/service.py", '"destination": record.telephone'),
        ],
        "PHONE-HTTP-1": [
            ("services/sms_gateway/provider.py", 'ENDPOINT = "http://'),
            ("services/sms_gateway/provider.py", '"to": payload["destination"]'),
        ],
        "PHONE-HTTP-2": [
            ("jobs/legacy_export.py", 'ENDPOINT = "http://'),
            ("jobs/legacy_export.py", 'SELECT record_id, telephone FROM profile_records'),
        ],
    }
    positive_rows = []
    for ident, category, path, function, sink, visible, explanation in positives:
        start, end = function_span(sources[path], function)
        sink_line = next(i for i, line in enumerate(sources[path].splitlines(), 1) if sink in line)
        required = [{"path": path, "line_start": sink_line, "line_end": sink_line}]
        for evidence_path, fragment in supporting_requirements.get(ident, []):
            line_number = next(i for i, line in enumerate(sources[evidence_path].splitlines(), 1) if fragment in line)
            required.append({"path": evidence_path, "line_start": line_number, "line_end": line_number})
        positive_rows.append({"id": ident, "category": category, "path": path, "function": function,
                              "line_start": start, "line_end": end, "sink_line": sink_line,
                              "diagram_visible": visible, "evidence": explanation,
                              "required_evidence": required})
    negative_rows = []
    for ident, path, function, explanation in controls:
        start, end = function_span(sources[path], function)
        negative_rows.append({"id": ident, "path": path, "function": function,
                              "line_start": start, "line_end": end, "reason": explanation})
    return {"schemaVersion": 1, "datasetId": DATASET_ID, "evaluatorOnly": True,
            "scope": "Four contact logging/transport behaviors and three matched function controls, not all possible defects.",
            "positives": positive_rows, "negatives": negative_rows,
            "required_context_paths": [{"path": path} for path in [
                "services/customer_profile/api.py", "services/customer_profile/validation.py",
                "services/customer_profile/models.py", "services/customer_profile/service.py",
                "services/customer_profile/repository.py", "services/customer_profile/schema.sql",
                "services/customer_profile/events.py", "services/contact_events/bridge.py",
                "services/notification_dispatch/consumer.py", "services/sms_gateway/consumer.py",
                "services/sms_gateway/provider.py", "jobs/legacy_export.py"]],
            "diagram_omissions": ["jobs/legacy_export.py", "jobs/legacy_export.yaml"],
            "limitations": ["Generated service scaffolds share conventions; source volume alone is not production complexity.",
                           "No claim of complete legal compliance, production deployment, or benchmark generalization.",
                           "HTTP function calls are captured by fake transports; no network requests are executed.",
                           "Regular synchronous business links are design context; only the contact workflow has end-to-end behavior tests."]}


def build(repository: Path = DEFAULT_REPOSITORY, metadata_dir: Path = DEST) -> dict:
    sources = {}
    for domain in DOMAINS:
        sources.update(service_sources(domain))
    sources.update(specialized_sources())
    for path, source in sources.items():
        if path.endswith(".py"):
            ast.parse(source, filename=path)
    repository.mkdir(parents=True, exist_ok=True)
    expected = set(sources)
    existing = {str(p.relative_to(repository)) for p in repository.rglob("*") if p.is_file() and "__pycache__" not in p.parts}
    if existing - expected:
        raise ValueError("output contains files outside the fixture manifest; choose an empty output directory")
    digest = hashlib.sha256()
    entries = []
    for path, source in sorted(sources.items()):
        data = source.encode("utf-8")
        target = repository / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        digest.update(path.encode() + b"\0" + data + b"\0")
        entries.append({"path": path, "bytes": len(data), "lines": len(source.splitlines()), "sha256": hashlib.sha256(data).hexdigest()})
    manifest = {"schemaVersion": 1, "datasetId": DATASET_ID, "synthetic": True, "seed": SEED,
                "generator": "scripts/build_complex_architecture_fixture.py",
                "repository": ".runtime/architecture-benchmark/complex/repository",
                "serviceCount": len(DOMAINS), "sourceFileCount": len(entries),
                "sourceBytes": sum(e["bytes"] for e in entries), "sourceLines": sum(e["lines"] for e in entries),
                "sourceSha256": digest.hexdigest(),
                "sourceHashMethod": "SHA256 of sorted UTF8 path + NUL + file bytes + NUL",
                "modelInputExcludes": ["ground_truth.json", "graph.json", "manifest.json", "tests"],
                "files": entries}
    metadata_dir.mkdir(parents=True, exist_ok=True)
    for name, document in (("manifest.json", manifest), ("ground_truth.json", ground_truth(sources)), ("graph.json", graph_document())):
        (metadata_dir / name).write_text(json.dumps(document, ensure_ascii=False, indent=2) + "\n")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_REPOSITORY)
    parser.add_argument("--metadata-dir", type=Path, default=DEST)
    args = parser.parse_args()
    manifest = build(args.output, args.metadata_dir)
    print(json.dumps({key: manifest[key] for key in ("datasetId", "serviceCount", "sourceFileCount", "sourceBytes", "sourceLines", "sourceSha256")}, indent=2))


if __name__ == "__main__":
    main()
