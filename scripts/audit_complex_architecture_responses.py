#!/usr/bin/env python3
"""Export synthetic model responses and audit the frozen runner's omissions.

No model calls, source mutations, or changes to the original scoring are made.
An unfinished stream, missing raw response, or mismatching response metadata
prevents publication. This exporter is deliberately limited to the mock corpus.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "docs/benchmarks/complex-mock"
RAW = ROOT / ".runtime/architecture-benchmark/complex/run-v1"
MANIFEST = ROOT / "tests/fixtures/complex_architecture/manifest.json"
ARMS = ("full_code", "code_index", "vision_index", "structure_json_index")
METRIC_KEYS = ("prompt_eval_count", "eval_count", "total_duration", "load_duration",
               "prompt_eval_duration", "eval_duration", "prompt_eval_cached_count")


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def parsed_output(content):
    """Preserve invalid outputs too; these checks do not replace frozen scores."""
    try:
        data = json.loads(content)
    except (json.JSONDecodeError, TypeError):
        return None, ["INVALID_JSON"]
    if not isinstance(data, dict):
        return data, ["OUTPUT_NOT_OBJECT"]
    issues = []
    if set(data) != {"findings", "needs", "uncertainties"}:
        issues.append("UNEXPECTED_OUTPUT_KEYS")
    for key, limit, length in (("needs", 3, 220), ("uncertainties", 3, 120)):
        values = data.get(key)
        if (not isinstance(values, list) or len(values) > limit
                or any(not isinstance(value, str) or len(value) > length for value in values)):
            issues.append(key.upper() + "_SCHEMA_INVALID")
    findings = data.get("findings")
    if not isinstance(findings, list) or len(findings) > 4:
        issues.append("FINDINGS_SCHEMA_INVALID")
        return data, issues
    for index, finding in enumerate(findings):
        if not isinstance(finding, dict):
            issues.append(f"FINDING_{index}_NOT_OBJECT")
            continue
        if set(finding) != {"filePath", "line", "evidence", "category", "reason", "support"}:
            issues.append(f"FINDING_{index}_KEYS_INVALID")
        if (not isinstance(finding.get("category"), str)
                or finding["category"] not in {"sensitive_logging", "plaintext_pii_export"}):
            issues.append(f"FINDING_{index}_CATEGORY_INVALID")
        if not isinstance(finding.get("reason"), str) or len(finding["reason"]) > 120:
            issues.append(f"FINDING_{index}_REASON_INVALID")
        support = finding.get("support")
        if not isinstance(support, list) or len(support) > 3:
            issues.append(f"FINDING_{index}_SUPPORT_INVALID")
            support = []
        for ref in [finding] + support:
            if (not isinstance(ref, dict)
                    or not isinstance(ref.get("line"), int) or isinstance(ref["line"], bool) or ref["line"] < 1
                    or any(not isinstance(ref.get(key), str) or len(ref[key]) > 220 for key in ("filePath", "evidence"))):
                issues.append(f"FINDING_{index}_REFERENCE_INVALID")
    return data, issues


def build_audit(directory=PUBLIC, raw_directory=RAW, manifest_path=MANIFEST):
    directory, raw_directory, manifest_path = map(Path, (directory, raw_directory, manifest_path))
    protocol_raw = (directory / "protocol.json").read_bytes()
    protocol = json.loads(protocol_raw)
    if protocol.get("synthetic") is not True or tuple(protocol.get("arms", ())) != ARMS:
        raise ValueError("SYNTHETIC_FOUR_ARM_PROTOCOL_REQUIRED")
    measurement_raw = (directory / "measurements.jsonl").read_bytes()
    rows = [json.loads(line) for line in measurement_raw.decode().splitlines() if line.strip()]
    if (not rows or rows[-1].get("event") != "finished"
            or sum(row.get("event") == "finished" for row in rows) != 1):
        raise ValueError("MEASUREMENT_NOT_FINISHED")
    metadata_rows = [row for row in rows if row.get("event") == "metadata"]
    if len(metadata_rows) != 1 or metadata_rows[0].get("protocolSha256") != digest(protocol_raw):
        raise ValueError("METADATA_OR_PROTOCOL_MISMATCH")
    trials = [row for row in rows if row.get("event") == "trial"]
    if len(trials) != 4 or {row.get("arm") for row in trials} != set(ARMS):
        raise ValueError("FOUR_TRIALS_REQUIRED")
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    try:
        manifest_key = str(manifest_path.resolve().relative_to(ROOT))
    except ValueError:
        manifest_key = None
    expected = protocol.get("hashes", {}).get(manifest_key)
    if expected is not None and expected != digest(manifest_raw):
        raise ValueError("MANIFEST_HASH_MISMATCH")
    allowed_paths = {entry["path"] for entry in manifest["files"]}
    call_rows = [row for row in rows if row.get("event") == "call"]
    if any(row.get("arm") not in ARMS for row in call_rows):
        raise ValueError("UNEXPECTED_CALL_ARM")
    arms = {}
    for trial in trials:
        arm = trial["arm"]
        recorded = [row["metrics"] for row in call_rows if row["arm"] == arm]
        if recorded != trial.get("calls", []):
            raise ValueError("TRIAL_CALLS_MISMATCH: " + arm)
        findings = trial.get("findings", [])
        arms[arm] = {
            "trialComplete": trial.get("complete", False),
            "reviewResponseCount": 0, "followupResponseCount": 0,
            "followupResponseNeeds": [], "discardedValidFollowupNeeds": [],
            "hasDiscardedValidFollowupNeeds": False, "responseIssues": [],
            "invalidPrimaryEvidenceCount": sum(not finding.get("evidenceValid", False) for finding in findings),
            "invalidSupportEvidenceCount": sum(not ref.get("evidenceValid", False)
                                                for finding in findings for ref in finding.get("support", [])),
            "recordedFindingCount": len(findings),
            "runnerUnresolvedNeeds": trial.get("unresolvedNeeds", []),
            "runnerRejectedNeeds": trial.get("rejectedNeeds", []),
        }
    export = [{"event": "audit_metadata", "synthetic": True,
               "protocolSha256": digest(protocol_raw), "measurementSha256": digest(measurement_raw),
               "model": metadata_rows[0].get("model"),
               "contentScope": "Persisted outputs from this generated mock corpus, including invalid and incomplete responses. No source prompts or image bytes are exported."}]
    seen = set()
    for row in rows:
        event = row.get("event")
        if event not in {"call", "vision_call", "warmup"}:
            continue
        metrics = row["metrics"]
        arm = row.get("arm")
        batch = metrics.get("batch")
        if event == "call":
            if not isinstance(batch, int) or isinstance(batch, bool) or batch < 1:
                raise ValueError("INVALID_CALL_BATCH")
            filename = f"{arm}-{batch}.json"
        else:
            filename = "vision.json" if event == "vision_call" else "warmup.json"
        if filename in seen:
            raise ValueError("DUPLICATE_RAW_RESPONSE: " + filename)
        seen.add(filename)
        path = raw_directory / filename
        if path.is_symlink():
            raise ValueError("RAW_RESPONSE_SYMLINK")
        raw_bytes = path.read_bytes()
        raw = json.loads(raw_bytes)
        if any(raw.get(key) != metrics.get(key) for key in METRIC_KEYS) or raw.get("done_reason") != metrics.get("doneReason"):
            raise ValueError("RAW_RESPONSE_METRICS_MISMATCH: " + filename)
        content = raw.get("message", {}).get("content")
        if not isinstance(content, str):
            raise ValueError("RAW_RESPONSE_CONTENT_MISSING: " + filename)
        item = {"event": "model_response", "phase": "review" if event == "call" else "vision" if event == "vision_call" else "warmup",
                "arm": arm, "batch": batch, "followup": metrics.get("followup", False),
                "model": raw.get("model"), "createdAt": raw.get("created_at"),
                "doneReason": raw.get("done_reason"), "metrics": metrics,
                "rawFile": filename, "rawSha256": digest(raw_bytes), "content": content}
        export.append(item)
        if event != "call":
            continue
        trial = next(trial for trial in trials if trial["arm"] == arm)
        error_batches = {error.get("batch") for error in trial.get("errors", [])}
        accepted = batch not in error_batches and raw.get("done_reason") == "stop"
        data, issues = parsed_output(content)
        if raw.get("done_reason") != "stop":
            issues.append("OUTPUT_INCOMPLETE")
        result = arms[arm]
        result["reviewResponseCount"] += 1
        if issues or not accepted:
            result["responseIssues"].append({"batch": batch, "followup": item["followup"],
                                              "doneReason": raw.get("done_reason"),
                                              "runnerAccepted": accepted, "issues": issues})
        if not item["followup"]:
            continue
        result["followupResponseCount"] += 1
        needs = data.get("needs", []) if isinstance(data, dict) else []
        if isinstance(needs, list):
            for need in needs:
                if not isinstance(need, str):
                    continue  # Invalid shapes remain in responseIssues and raw content.
                entry = {"batch": batch, "path": need, "inManifest": need in allowed_paths,
                         "inEffectiveSelection": need in trial.get("effectivePaths", []),
                         "runnerAccepted": accepted}
                result["followupResponseNeeds"].append(entry)
                if accepted and entry["inManifest"]:
                    result["discardedValidFollowupNeeds"].append(entry)
        result["hasDiscardedValidFollowupNeeds"] = bool(result["discardedValidFollowupNeeds"])
    actual_raw = {path.name for path in raw_directory.glob("*.json")}
    if seen != actual_raw:
        raise ValueError("RAW_RESPONSE_COUNT_OR_NAMES_MISMATCH")
    export_text = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in export)
    report = {
        "schemaVersion": 1, "complete": True, "synthetic": True,
        "allTrialsComplete": all(trial.get("complete", False) for trial in trials),
        "protocolSha256": digest(protocol_raw), "measurementSha256": digest(measurement_raw),
        "manifestSha256": digest(manifest_raw), "rawResponsesSha256": digest(export_text.encode()),
        "rawResponseCount": len(seen), "arms": {arm: arms[arm] for arm in ARMS},
        "hasDiscardedValidFollowupNeeds": any(result["hasDiscardedValidFollowupNeeds"] for result in arms.values()),
        "limits": [
            "This audit does not alter or replace frozen model calls, protocol, planner, labels, or original scores.",
            "The frozen runner silently drops manifest-valid needs returned by a successful follow-up. They are separately preserved here.",
            "inEffectiveSelection does not establish that the requested file was present in the same follow-up call or understood by the model.",
            "Primary/support invalid counts use the frozen runner's recorded per-reference evidence flags; they are not a new semantic source review.",
            "Reference validation establishes a matching submitted line, not complete runtime dataflow or legal compliance.",
            "Raw response hashes are captured at audit time; original capture did not include a response-content hash in the measurement stream.",
            "Complete means every logged response was audited after four finished trials, not that every trial or quality check passed.",
        ],
    }
    return report, export_text


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=PUBLIC)
    parser.add_argument("--raw-directory", type=Path, default=RAW)
    parser.add_argument("--manifest", type=Path, default=MANIFEST)
    args = parser.parse_args()
    try:
        report, export = build_audit(args.directory, args.raw_directory, args.manifest)
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    (args.directory / "model-responses.jsonl").write_text(export, encoding="utf-8")
    (args.directory / "response-audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"complete": True, "rawResponseCount": report["rawResponseCount"],
                      "hasDiscardedValidFollowupNeeds": report["hasDiscardedValidFollowupNeeds"]}))


if __name__ == "__main__":
    main()
