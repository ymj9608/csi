"""Summary integrity tests use private synthetic log rows, never model calls."""
import copy
import json

import pytest

from scripts.summarize_complex_architecture import ARMS, load_report, render_markdown, sha


def experiment(tmp_path, *, finished=True):
    protocol = {"arms": list(ARMS), "sourceFiles": 1, "sourceBytes": 80, "sourceLines": 10,
                "hashes": {}, "repeats": 1}
    protocol_path = tmp_path / "protocol.json"
    protocol_path.write_text(json.dumps(protocol))
    truth = {"positives": [{"id": "P", "path": "service.py", "line_start": 3, "line_end": 3}],
             "negatives": [{"id": "N", "path": "service.py", "line_start": 8, "line_end": 9}],
             "required_context_paths": [{"path": "service.py"}], "diagram_omissions": ["jobs/example.py"]}
    manifest = {"datasetId": "unit-fixture", "serviceCount": 1, "files": [{"path": "service.py", "bytes": 80}]}
    truth_path, manifest_path = tmp_path / "truth.json", tmp_path / "manifest.json"
    truth_path.write_text(json.dumps(truth))
    manifest_path.write_text(json.dumps(manifest))
    rows = [{"event": "metadata", "protocolSha256": sha(protocol_path.read_bytes())},
            {"event": "vision_call", "metrics": {"prompt_eval_count": 200, "eval_count": 50, "wallDurationMs": 3000}},
            {"event": "vision_result", "complete": True, "components": 2, "flows": 1},
            {"event": "vision_quality", "quality": {"componentsExpected": 2, "componentsReturned": 2,
                "componentIdentitiesMatched": 2, "componentInstancesMatched": 2, "edgesExpected": 1,
                "edgesReturned": 1, "edgesMatched": 1, "unexpectedMappedEdges": [], "missingEdges": []}}]
    for arm in ARMS:
        rows.append({"event": "trial", "arm": arm, "complete": True,
                     "initialPaths": ["service.py"], "effectivePaths": ["service.py"], "initialBytes": 80,
                     "calls": [{"requestSha256": "same-request"}],
                     "totals": {"prompt_eval_count": 100, "eval_count": 20, "wallDurationMs": 2000},
                     "planningWallMs": 10, "endToEndWallMs": 2010,
                     "findings": [{"filePath": "service.py", "line": 3, "evidenceValid": True}],
                     "quality": {"expected": 1, "candidateMatches": ["P"], "verifiedMatches": ["P"],
                                 "requiredSelected": 1, "requiredTotal": 1, "missingRequiredContext": [],
                                 "extraCandidates": 0, "invalidEvidence": 0},
                     "unresolvedNeeds": [], "rejectedNeeds": [], "errors": [], "plan": None})
    if finished:
        rows.append({"event": "finished"})
    write_rows(tmp_path, rows)
    write_audit(tmp_path)
    return truth_path, manifest_path, rows


def write_rows(directory, rows):
    (directory / "measurements.jsonl").write_text("".join(json.dumps(row) + "\n" for row in rows))
    audit_path = directory / "response-audit.json"
    if audit_path.exists():
        audit = json.loads(audit_path.read_text())
        audit["measurementSha256"] = sha((directory / "measurements.jsonl").read_bytes())
        audit_path.write_text(json.dumps(audit))


def write_audit(directory):
    raw = directory / "model-responses.jsonl"
    raw.write_text('{"unitTest":"no model was invoked"}\n')
    audit = {"complete": True,
             "protocolSha256": sha((directory / "protocol.json").read_bytes()),
             "measurementSha256": sha((directory / "measurements.jsonl").read_bytes()),
             "rawResponsesSha256": sha(raw.read_bytes()),
             "arms": {arm: {"discardedValidFollowupNeeds": [], "invalidSupportEvidenceCount": 0,
                            "responseIssues": []} for arm in ARMS}}
    (directory / "response-audit.json").write_text(json.dumps(audit))


def test_incomplete_stream_cannot_become_a_finished_report(tmp_path):
    truth, manifest, _ = experiment(tmp_path, finished=False)
    with pytest.raises(ValueError, match="MEASUREMENT_NOT_FINISHED"):
        load_report(tmp_path, truth, manifest)


def test_same_file_normal_control_and_first_image_cost_are_scored_separately(tmp_path):
    truth, manifest, rows = experiment(tmp_path)
    result = load_report(tmp_path, truth, manifest)
    assert result["arms"]["vision_index"]["quality"]["functionLevelNegativeFlags"] == []
    assert result["firstVisionCombined"]["inputTokens"] == 300
    assert result["firstVisionCombined"]["outputTokens"] == 70
    assert result["firstVisionCombined"]["wallMs"] == 5010
    assert result["visionExtraction"]["graphQuality"]["edgesMatched"] == 1
    assert result["dataset"]["diagramOmissions"] == ["jobs/example.py"]
    assert result["allMeasuredChecksPass"]
    assert all(pair["identicalOrderedModelRequests"] for pair in result["pairwiseComparisons"])
    markdown = render_markdown(result)
    assert "모델 요청이 동일" in markdown
    assert "로컬 파일에서 다시 읽어" in markdown
    assert "컴포넌트 ID 일치 **2 / 2**" in markdown

    changed = copy.deepcopy(rows)
    trial = next(row for row in changed if row.get("arm") == "vision_index")
    trial["findings"].append({"filePath": "service.py", "line": 8, "evidenceValid": True})
    trial["quality"]["extraCandidates"] = 1
    write_rows(tmp_path, changed)
    result = load_report(tmp_path, truth, manifest)
    assert result["arms"]["vision_index"]["quality"]["functionLevelNegativeFlags"] == ["N"]
    assert not result["allMeasuredChecksPass"]


def test_failed_cost_and_unresolved_retrieval_do_not_count_as_complete_checks(tmp_path):
    truth, manifest, rows = experiment(tmp_path)
    failed = next(row for row in rows if row.get("arm") == "vision_index")
    failed["complete"] = False
    failed["errors"] = [{"code": "OUTPUT_INCOMPLETE"}]
    unresolved = next(row for row in rows if row.get("arm") == "code_index")
    unresolved["unresolvedNeeds"] = [["missing.py"]]
    write_rows(tmp_path, rows)
    result = load_report(tmp_path, truth, manifest)
    assert result["arms"]["vision_index"]["inputTokens"] == 100
    assert result["firstVisionCombined"]["wallMs"] == 5010
    assert not result["firstVisionCombined"]["complete"]
    assert result["arms"]["code_index"]["quality"]["authoredLabelChecksPass"]
    assert not result["arms"]["code_index"]["quality"]["retrievalRequestsComplete"]
    assert not result["allMeasuredChecksPass"]
    assert "성공한 작업을 끝내는 데 걸린 시간" in render_markdown(result)


def test_absent_response_audit_keeps_retrieval_completion_unknown(tmp_path):
    truth, manifest, _ = experiment(tmp_path)
    (tmp_path / "response-audit.json").unlink()
    result = load_report(tmp_path, truth, manifest)
    assert not result["responseAudit"]["available"]
    assert result["arms"]["vision_index"]["discardedValidFollowupNeeds"] is None
    assert result["arms"]["vision_index"]["invalidSupportEvidenceCount"] is None
    assert result["arms"]["vision_index"]["quality"]["authoredLabelChecksPass"]
    assert not result["arms"]["vision_index"]["quality"]["retrievalRequestsComplete"]
    assert not result["allMeasuredChecksPass"]
    assert "원문 응답 감사 파일이 없어" in render_markdown(result)


def test_discarded_followup_and_invalid_support_survive_the_summary(tmp_path):
    truth, manifest, _ = experiment(tmp_path)
    path = tmp_path / "response-audit.json"
    audit = json.loads(path.read_text())
    discarded = {"batch": 2, "path": "service.py", "inManifest": True,
                 "inEffectiveSelection": True, "runnerAccepted": True}
    audit["arms"]["vision_index"]["discardedValidFollowupNeeds"] = [discarded]
    audit["arms"]["code_index"]["invalidSupportEvidenceCount"] = 2
    path.write_text(json.dumps(audit))
    result = load_report(tmp_path, truth, manifest)
    assert result["arms"]["vision_index"]["discardedValidFollowupNeeds"] == [discarded]
    assert not result["arms"]["vision_index"]["quality"]["retrievalRequestsComplete"]
    assert result["arms"]["code_index"]["invalidSupportEvidenceCount"] == 2
    assert not result["arms"]["code_index"]["quality"]["allMeasuredChecksPass"]
    assert "러너가 버린 유효한 조회 **1건**" in render_markdown(result)


@pytest.mark.parametrize("key,error", [
    ("protocolSha256", "RESPONSE_AUDIT_PROTOCOL_HASH_MISMATCH"),
    ("measurementSha256", "RESPONSE_AUDIT_MEASUREMENT_HASH_MISMATCH"),
    ("rawResponsesSha256", "RESPONSE_AUDIT_RAW_RESPONSES_HASH_MISMATCH"),
])
def test_stale_response_audit_is_rejected(tmp_path, key, error):
    truth, manifest, _ = experiment(tmp_path)
    path = tmp_path / "response-audit.json"
    audit = json.loads(path.read_text())
    audit[key] = "different-artifact"
    path.write_text(json.dumps(audit))
    with pytest.raises(ValueError, match=error):
        load_report(tmp_path, truth, manifest)


def test_no_selection_gain_is_not_hidden_by_different_followup_requests(tmp_path):
    truth, manifest, rows = experiment(tmp_path)
    code = next(row for row in rows if row.get("arm") == "code_index")
    vision = next(row for row in rows if row.get("arm") == "vision_index")
    code["calls"].append({"requestSha256": "code-followup", "followup": True})
    vision["calls"].append({"requestSha256": "vision-followup", "followup": True})
    vision["plan"] = {"status": "READY", "selectedPaths": ["service.py"],
                      "decision": {"useVisionContext": False, "reason": "NO_SELECTION_GAIN"}}
    write_rows(tmp_path, rows)
    result = load_report(tmp_path, truth, manifest)
    pair = next(pair for pair in result["pairwiseComparisons"]
                if pair["left"] == "code_index" and pair["right"] == "vision_index")
    assert pair["identicalInitialModelRequests"]
    assert not pair["identicalOrderedModelRequests"]
    assert result["arms"]["vision_index"]["initialModelRequestSha256"] == ["same-request"]
    markdown = render_markdown(result)
    assert "추가 파일 선택 효과가 없어" in markdown
    assert "최초 모델 요청 SHA256는 순서까지 같지만" in markdown
    assert "초기 비전 파일 선택의 효과로 해석하지 않습니다" in markdown
