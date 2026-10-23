"""A finished experiment must retain unsuccessful outputs and hidden needs."""
import hashlib
import json

import pytest

from scripts.audit_complex_architecture_responses import ARMS, build_audit, parsed_output


def make_experiment(tmp_path):
    directory, raw_directory = tmp_path / "public", tmp_path / "raw"
    directory.mkdir()
    raw_directory.mkdir()
    protocol = {"synthetic": True, "arms": list(ARMS), "hashes": {}}
    protocol_raw = json.dumps(protocol).encode()
    (directory / "protocol.json").write_bytes(protocol_raw)
    manifest = tmp_path / "manifest.json"
    manifest.write_text(json.dumps({"files": [{"path": "a.py"}, {"path": "b.py"}]}))
    rows = [{"event": "metadata", "protocolSha256": hashlib.sha256(protocol_raw).hexdigest(), "model": {"name": "mock-model"}}]
    for arm in ARMS:
        calls = []
        for batch in range(1, 3 if arm == "code_index" else 2):
            metrics = {"batch": batch, "followup": batch == 2, "doneReason": "stop",
                       "prompt_eval_count": 50, "eval_count": 20, "total_duration": 80,
                       "load_duration": 10, "prompt_eval_duration": 20, "eval_duration": 50,
                       "wallDurationMs": 1.0, "requestSha256": "fixed-test-request"}
            data = {"findings": [], "needs": ["b.py", "../../.env"] if batch == 2 else [], "uncertainties": []}
            raw = {key: metrics[key] for key in ("prompt_eval_count", "eval_count", "total_duration", "load_duration", "prompt_eval_duration", "eval_duration")}
            raw.update({"model": "mock-model", "done_reason": "stop", "message": {"content": json.dumps(data)}})
            (raw_directory / f"{arm}-{batch}.json").write_text(json.dumps(raw))
            calls.append(metrics)
            rows.append({"event": "call", "arm": arm, "metrics": metrics})
        rows.append({"event": "trial", "arm": arm, "complete": True,
                     "calls": calls, "errors": [], "effectivePaths": ["a.py", "b.py"],
                     "unresolvedNeeds": [], "rejectedNeeds": [],
                     "findings": [{"filePath": "a.py", "line": 1, "evidenceValid": True,
                                   "support": [{"filePath": "b.py", "line": 2, "evidenceValid": False}]}]})
    rows.append({"event": "finished"})
    (directory / "measurements.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    return directory, raw_directory, manifest


def test_valid_followup_needs_discarded_by_runner_remain_visible(tmp_path):
    paths = make_experiment(tmp_path)
    report, export = build_audit(*paths)
    arm = report["arms"]["code_index"]
    assert report["complete"] is True
    assert report["rawResponseCount"] == 5
    assert arm["discardedValidFollowupNeeds"] == [{"batch": 2, "path": "b.py", "inManifest": True,
        "inEffectiveSelection": True, "runnerAccepted": True}]
    assert len(arm["followupResponseNeeds"]) == 2
    assert arm["hasDiscardedValidFollowupNeeds"]
    assert arm["invalidSupportEvidenceCount"] == 1
    assert arm["invalidPrimaryEvidenceCount"] == 0
    assert report["rawResponsesSha256"] == hashlib.sha256(export.encode()).hexdigest()
    exported = [json.loads(line) for line in export.splitlines()]
    raw = json.loads((paths[1] / "code_index-2.json").read_text())
    response = next(row for row in exported if row.get("arm") == "code_index" and row.get("batch") == 2)
    assert response["content"] == raw["message"]["content"]


def test_unfinished_stream_is_not_published(tmp_path):
    paths = make_experiment(tmp_path)
    log = paths[0] / "measurements.jsonl"
    log.write_text("\n".join(log.read_text().splitlines()[:-1]) + "\n")
    with pytest.raises(ValueError, match="MEASUREMENT_NOT_FINISHED"):
        build_audit(*paths)


def test_missing_or_extra_raw_response_rejects_complete_claim(tmp_path):
    paths = make_experiment(tmp_path)
    extra = paths[1] / "unlogged.json"
    extra.write_text("{}")
    with pytest.raises(ValueError, match="RAW_RESPONSE_COUNT_OR_NAMES_MISMATCH"):
        build_audit(*paths)
    extra.unlink()
    (paths[1] / "full_code-1.json").unlink()
    with pytest.raises(FileNotFoundError):
        build_audit(*paths)


def test_metric_mismatch_rejects_wrong_response_file(tmp_path):
    paths = make_experiment(tmp_path)
    path = paths[1] / "full_code-1.json"
    raw = json.loads(path.read_text())
    raw["eval_count"] = 999
    path.write_text(json.dumps(raw))
    with pytest.raises(ValueError, match="RAW_RESPONSE_METRICS_MISMATCH"):
        build_audit(*paths)


def test_non_synthetic_data_cannot_be_exported(tmp_path):
    paths = make_experiment(tmp_path)
    path = paths[0] / "protocol.json"
    protocol = json.loads(path.read_text())
    protocol["synthetic"] = False
    path.write_text(json.dumps(protocol))
    with pytest.raises(ValueError, match="SYNTHETIC_FOUR_ARM_PROTOCOL_REQUIRED"):
        build_audit(*paths)


def test_truncated_response_is_retained_with_issues(tmp_path):
    paths = make_experiment(tmp_path)
    path = paths[1] / "full_code-1.json"
    raw = json.loads(path.read_text())
    raw["done_reason"] = "length"
    raw["message"]["content"] = '{"findings": ['
    path.write_text(json.dumps(raw))
    log = paths[0] / "measurements.jsonl"
    rows = [json.loads(line) for line in log.read_text().splitlines()]
    for row in rows:
        if row.get("arm") == "full_code":
            if row["event"] == "call":
                row["metrics"]["doneReason"] = "length"
            if row["event"] == "trial":
                row["calls"][0]["doneReason"] = "length"
                row["complete"] = False
                row["errors"] = [{"batch": 1, "code": "OUTPUT_INCOMPLETE"}]
    log.write_text("".join(json.dumps(row) + "\n" for row in rows))
    report, export = build_audit(*paths)
    assert report["complete"] is True
    assert report["allTrialsComplete"] is False
    assert report["arms"]["full_code"]["responseIssues"][0]["issues"] == ["INVALID_JSON", "OUTPUT_INCOMPLETE"]
    assert any(json.loads(line).get("content") == raw["message"]["content"] for line in export.splitlines())


def test_extra_keys_and_invalid_needs_are_reported_without_hiding_raw_output():
    data, issues = parsed_output('{"findings": [], "needs": "missing.py", "uncertainties": [], "extra": "value"}')
    assert data["extra"] == "value"
    assert "UNEXPECTED_OUTPUT_KEYS" in issues
    assert "NEEDS_SCHEMA_INVALID" in issues


def test_malformed_nested_findings_are_reported_without_crashing_audit():
    _, issues = parsed_output(json.dumps({"findings": [{"category": {}, "support": [None]}],
                                          "needs": [], "uncertainties": []}))
    assert "FINDING_0_CATEGORY_INVALID" in issues
    assert "FINDING_0_REFERENCE_INVALID" in issues
