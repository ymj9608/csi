#!/usr/bin/env python3
"""Summarize a finished complex synthetic experiment without invoking a model.

Incomplete streams are rejected. Failed trials remain visible, and image
extraction costs are never hidden inside a purported free cached comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "docs/benchmarks/complex-mock"
DATA = ROOT / "tests/fixtures/complex_architecture"
ARMS = ("full_code", "code_index", "vision_index", "structure_json_index")
LABELS = {"full_code": "전체 코드", "code_index": "코드·설정 인덱스",
          "vision_index": "저장된 비전 구조 + 같은 인덱스",
          "structure_json_index": "구조 JSON + 같은 인덱스"}


def read_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def required_paths(truth):
    entries = truth.get("required_context_paths", truth.get("requiredContextPaths", []))
    return {item if isinstance(item, str) else item["path"] for item in entries}


def line_range(item):
    return (item.get("line_start", item.get("lineStart")),
            item.get("line_end", item.get("lineEnd")))


def false_controls(findings, truth):
    """Normal functions can share files with real findings; score their lines."""
    matches = set()
    for control in truth.get("negatives", []):
        begin, end = line_range(control)
        if not isinstance(begin, int) or not isinstance(end, int):
            continue
        for finding in findings:
            line = finding.get("line")
            if finding.get("filePath") == control["path"] and isinstance(line, int) and begin <= line <= end:
                matches.add(control["id"])
    return sorted(matches)


def same_requests(left, right, *, initial=False):
    key = "initialModelRequestSha256" if initial else "requestSha256"
    a, b = left[key], right[key]
    return bool(a) and bool(b) and all(a) and all(b) and a == b


def response_audit(directory, protocol_sha, measurement_sha):
    """Only a complete audit bound to the exact responses may settle omissions."""
    path = directory / "response-audit.json"
    if not path.exists():
        return None
    audit = read_json(path)
    if audit.get("protocolSha256") != protocol_sha:
        raise ValueError("RESPONSE_AUDIT_PROTOCOL_HASH_MISMATCH")
    if audit.get("measurementSha256") != measurement_sha:
        raise ValueError("RESPONSE_AUDIT_MEASUREMENT_HASH_MISMATCH")
    raw_path = directory / "model-responses.jsonl"
    if not raw_path.exists() or audit.get("rawResponsesSha256") != sha(raw_path.read_bytes()):
        raise ValueError("RESPONSE_AUDIT_RAW_RESPONSES_HASH_MISMATCH")
    if audit.get("complete") is not True or set(audit.get("arms", {})) != set(ARMS):
        raise ValueError("RESPONSE_AUDIT_INCOMPLETE")
    for arm in ARMS:
        item = audit["arms"][arm]
        invalid = item.get("invalidSupportEvidenceCount")
        if not isinstance(item.get("discardedValidFollowupNeeds"), list) or not isinstance(invalid, int) or isinstance(invalid, bool) or invalid < 0:
            raise ValueError("RESPONSE_AUDIT_INVALID_ARM: " + arm)
    return audit


def load_report(directory=PUBLIC, ground_truth=DATA / "ground_truth.json", manifest_path=DATA / "manifest.json"):
    directory = Path(directory)
    protocol_path = directory / "protocol.json"
    protocol_raw = protocol_path.read_bytes()
    protocol = json.loads(protocol_raw)
    log_path = directory / "measurements.jsonl"
    rows = [json.loads(line) for line in log_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    if not rows or rows[-1].get("event") != "finished" or sum(row.get("event") == "finished" for row in rows) != 1:
        raise ValueError("MEASUREMENT_NOT_FINISHED: a final finished event is required")
    metadata_rows = [row for row in rows if row.get("event") == "metadata"]
    if len(metadata_rows) != 1:
        raise ValueError("EXPECTED_ONE_METADATA_EVENT")
    metadata = metadata_rows[0]
    if metadata.get("protocolSha256") != sha(protocol_raw):
        raise ValueError("PROTOCOL_HASH_MISMATCH")
    if tuple(protocol.get("arms", ())) != ARMS:
        raise ValueError("UNEXPECTED_EXPERIMENT_ARMS")
    truth, manifest = read_json(ground_truth), read_json(manifest_path)
    for path in (Path(ground_truth), Path(manifest_path)):
        try:
            relative = str(path.resolve().relative_to(ROOT))
        except ValueError:
            continue  # Explicit fixture paths are supported for unit tests.
        frozen = protocol.get("hashes", {}).get(relative)
        if frozen is not None and frozen != sha(path.read_bytes()):
            raise ValueError("EVALUATION_INPUT_HASH_MISMATCH: " + relative)
    trials = [row for row in rows if row.get("event") == "trial"]
    if len(trials) != len(ARMS) or {row.get("arm") for row in trials} != set(ARMS):
        raise ValueError("EXPECTED_EXACTLY_ONE_TRIAL_PER_ARM")
    audit = response_audit(directory, metadata["protocolSha256"], sha(log_path.read_bytes()))
    expected = {item["id"] for item in truth["positives"]}
    required = required_paths(truth)
    bytes_by_path = {item["path"]: item["bytes"] for item in manifest["files"]}
    summaries = {}
    for name in ARMS:
        trial = next(row for row in trials if row["arm"] == name)
        plan = trial.get("plan")
        plan_path = directory / f"{name}-plan.json"
        if plan_path.exists() and read_json(plan_path) != plan:
            raise ValueError("PLAN_SNAPSHOT_MISMATCH: " + name)
        initial = trial.get("initialPaths", (plan or {}).get("selectedPaths", []))
        effective = trial.get("effectivePaths", initial)
        if any(path not in bytes_by_path for path in set(initial) | set(effective)):
            raise ValueError("SELECTED_PATH_OUTSIDE_MANIFEST: " + name)
        quality = trial.get("quality")
        calls = trial.get("calls", [])
        totals = trial.get("totals", {})
        flags = false_controls(trial.get("findings", []), truth)
        arm_audit = audit["arms"][name] if audit else None
        discarded_needs = arm_audit["discardedValidFollowupNeeds"] if arm_audit else None
        invalid_support = arm_audit["invalidSupportEvidenceCount"] if arm_audit else None
        if quality is not None:
            quality = {**quality, "candidateCount": len(quality["candidateMatches"]),
                       "verifiedCount": len(quality["verifiedMatches"]),
                       "missingCandidateIds": sorted(expected - set(quality["candidateMatches"])),
                       "missingVerifiedIds": sorted(expected - set(quality["verifiedMatches"])),
                       "initialRequiredSelected": len(required & set(initial)),
                       "initialMissingRequiredContext": sorted(required - set(initial)),
                       "functionLevelNegativeFlags": flags,
                       "negativeControlTotal": len(truth.get("negatives", []))}
            quality["authoredLabelChecksPass"] = bool(
                trial.get("complete") and quality["verifiedCount"] == len(expected)
                and quality["requiredSelected"] == len(required) and not flags
                and quality.get("extraCandidates", 0) == 0 and quality.get("invalidEvidence", 0) == 0)
            quality["retrievalAuditAvailable"] = arm_audit is not None
            quality["retrievalRequestsComplete"] = bool(arm_audit is not None and not discarded_needs
                and not trial.get("unresolvedNeeds") and not trial.get("rejectedNeeds"))
            quality["allMeasuredChecksPass"] = bool(quality["authoredLabelChecksPass"]
                and quality["retrievalRequestsComplete"] and invalid_support == 0)
        summaries[name] = {
            "label": LABELS[name], "complete": trial.get("complete", False),
            "initialFiles": len(set(initial)), "initialBytes": trial.get("initialBytes", sum(bytes_by_path[path] for path in set(initial))),
            "effectiveFiles": len(set(effective)),
            "effectiveBytes": sum(bytes_by_path[path] for path in set(effective)),
            "initialPaths": initial, "effectivePaths": effective,
            "modelCalls": len(calls), "initialModelCalls": sum(not call.get("followup", False) for call in calls),
            "followupCalls": trial.get("followupCalls", 0),
            "inputTokens": totals.get("prompt_eval_count"), "outputTokens": totals.get("eval_count"),
            "reviewCallsWallMs": totals.get("wallDurationMs"),
            "planningWallMs": trial.get("planningWallMs"),
            "endToEndWallMs": trial.get("endToEndWallMs"),
            "requestSha256": [call.get("requestSha256") for call in calls],
            "initialModelRequestSha256": [call.get("requestSha256") for call in calls if not call.get("followup", False)],
            "quality": quality, "errors": trial.get("errors", []),
            "trialError": trial.get("error"), "unresolvedNeeds": trial.get("unresolvedNeeds", []),
            "rejectedNeeds": trial.get("rejectedNeeds", []),
            "responseAuditAvailable": arm_audit is not None,
            "discardedValidFollowupNeeds": discarded_needs,
            "invalidSupportEvidenceCount": invalid_support,
            "responseIssues": arm_audit.get("responseIssues", []) if arm_audit else None,
            "routing": None if plan is None else {
                "status": plan["status"], "decision": plan.get("decision"),
                "mappingCount": plan.get("mappingCount"), "unmatched": plan.get("unmatched", []),
                "selectedModules": plan.get("selectedModules", []),
                "omittedCandidateCount": len(plan.get("omittedCandidates", [])),
                "coverage": plan.get("coverage", {})},
        }
    vision_calls = [row["metrics"] for row in rows if row.get("event") == "vision_call"]
    vision_results = [row for row in rows if row.get("event") == "vision_result"]
    vision_quality = [row["quality"] for row in rows if row.get("event") == "vision_quality"]
    if len(vision_results) != 1 or len(vision_calls) > 1 or len(vision_quality) > 1:
        raise ValueError("UNEXPECTED_VISION_EVENTS")
    vision_metrics = vision_calls[0] if vision_calls else None
    vision = {"complete": vision_results[0].get("complete", False),
              "error": vision_results[0].get("error"), "metrics": vision_metrics,
              "components": vision_results[0].get("components"), "flows": vision_results[0].get("flows"),
              "graphQuality": vision_quality[0] if vision_quality else None,
              "costScope": "One measured extraction. The vision review arm includes reading the persisted JSON context file in planning time. Cache DB/API lookup and image authoring are not measured."}
    combined = None
    vtrial = summaries["vision_index"]
    if vision_metrics and vtrial["endToEndWallMs"] is not None:
        combined = {"inputTokens": vision_metrics["prompt_eval_count"] + vtrial["inputTokens"],
                    "outputTokens": vision_metrics["eval_count"] + vtrial["outputTokens"],
                    "wallMs": vision_metrics["wallDurationMs"] + vtrial["endToEndWallMs"],
                    "complete": vision["complete"] and vtrial["complete"],
                    "method": "Sum of measured image-call time and measured review-arm time; not a separate end-to-end API request."}
    comparisons = []
    for left_index, left_name in enumerate(ARMS):
        for right_name in ARMS[left_index + 1:]:
            left, right = summaries[left_name], summaries[right_name]
            comparisons.append({"left": left_name, "right": right_name,
                                "sameInitialPathSet": set(left["initialPaths"]) == set(right["initialPaths"]),
                                "sameEffectivePathSet": set(left["effectivePaths"]) == set(right["effectivePaths"]),
                                "identicalInitialModelRequests": same_requests(left, right, initial=True),
                                "identicalOrderedModelRequests": same_requests(left, right)})
    return {"schemaVersion": 1, "finished": True,
            "allTrialsComplete": all(row["complete"] for row in summaries.values()),
            "allMeasuredChecksPass": all(row["quality"] and row["quality"]["allMeasuredChecksPass"] for row in summaries.values()),
            "metadata": {"timestamp": metadata.get("timestamp"), "model": metadata.get("model"),
                         "ollamaVersion": metadata.get("ollamaVersion"), "platform": metadata.get("platform"),
                         "protocolSha256": metadata["protocolSha256"], "logSha256": sha(log_path.read_bytes()),
                         "collectionWallMs": metadata.get("collectionWallMs")},
            "dataset": {"synthetic": True, "datasetId": manifest.get("datasetId"),
                        "services": manifest.get("serviceCount"), "files": protocol["sourceFiles"],
                        "bytes": protocol["sourceBytes"], "lines": protocol.get("sourceLines"),
                        "sourceSha256": manifest.get("sourceSha256"), "knownPositiveCount": len(expected),
                        "requiredContextCount": len(required), "negativeControlCount": len(truth.get("negatives", [])),
                        "diagramOmissions": truth.get("diagram_omissions", truth.get("diagramOmissions", []))},
            "protocol": {key: protocol.get(key) for key in ("model", "options", "visionOptions", "budget", "batchBytes", "maxFollowupCalls", "repeats", "limits")},
            "visionExtraction": vision, "arms": summaries, "firstVisionCombined": combined,
            "responseAudit": {"available": audit is not None,
                "sha256": sha((directory / "response-audit.json").read_bytes()) if audit else None,
                "measurementSha256": audit["measurementSha256"] if audit else None,
                "rawResponsesSha256": audit["rawResponsesSha256"] if audit else None},
            "pairwiseComparisons": comparisons,
            "limits": ["Template-generated scaffolds are not equivalent to independent production services.",
                       "One fixed-order run per arm; cache is not cleared. Timing differences do not establish causality.",
                       "No generated patch, compilation, deployment, or complete privacy-compliance validation.",
                       "Required context coverage measures retrieval, not whether all supplied lines were correctly understood.",
                       "Independent source batches do not share previous findings; cross-service evidence may be split across calls.",
                       "Literal directed-edge mismatch includes abstractions such as an omitted broker hop, not just semantic errors.",
                       "Known positives and negative functions cover only the authored behaviors, not all possible flaws.",
                       "An architecture can omit background code; code evidence and fallback retrieval remain necessary."]}


def number(value):
    return "미측정" if value is None else f"{value:,.0f}"


def seconds(value):
    return "미측정" if value is None else f"{value / 1000:,.2f}초"


def render_markdown(report):
    dataset, arms = report["dataset"], report["arms"]
    lines = ["# 복잡한 합성 아키텍처 비교 실험", "",
             "실제 공개 프로젝트 대신 생성한 예시 코드와 아키텍처 이미지로 네 가지 입력 방식을 비교했습니다. "
             "아래 수치는 로컬 모델을 실제 호출한 로그의 집계이며, 정답 라벨은 모델 입력에서 제외했습니다.", "",
             f"데이터는 **{dataset['services']}개 서비스 · {dataset['files']:,}개 소스/설정 파일 · "
             f"{dataset['bytes']:,} bytes · {number(dataset['lines'])}줄**입니다. "
             "서비스별 템플릿과 합성 업무 로직을 사용했으므로 같은 크기의 실제 운영 코드가 가진 복잡도나 성능을 대표하지 않습니다.", ""]
    vision_decision = (arms["vision_index"]["routing"] or {}).get("decision") or {}
    if not report["visionExtraction"]["complete"]:
        lines.extend(["**이번 이미지 인식 결과는 유효한 구조로 검증되지 않았습니다. 후속 코드 리뷰의 결과를 비전 인식 성공이나 효율 향상의 증거로 사용할 수 없습니다.**", ""])
    elif vision_decision.get("reason") == "NO_SELECTION_GAIN" and not vision_decision.get("useVisionContext"):
        lines.extend(["**비전 구조를 코드와 연결했지만 추가 파일 선택 효과가 없어(`NO_SELECTION_GAIN`) 코드 인덱스의 선택으로 대체했습니다. "
                      "구조 맥락도 모델 리뷰 입력에서 제외했습니다. 후속 조회나 실행 시간이 달라도 초기 파일 선택에서 비전의 추가 이득이 생긴 것은 아닙니다. 최초 이미지 인식 비용은 더해집니다.**", ""])
    elif same_requests(arms["code_index"], arms["vision_index"]):
        lines.extend(["**코드 인덱스와 비전+인덱스의 모델 요청이 동일했습니다. 이번 데이터에서 비전이 코드 인덱스보다 추가로 입력을 줄였다고 볼 수 없으며, 최초 이미지 인식 비용이 더해집니다.**", ""])
    else:
        lines.extend(["**비전의 추가 가치는 전체 코드와의 차이뿐 아니라 코드 인덱스·구조 JSON과의 차이, 초기 이미지 비용, 같은 근거 품질을 함께 보고 판단해야 합니다. 단일 합성 실행으로 항상 더 효율적이라고 결론내리지 않습니다.**", ""])
    lines.extend(["## 실측 비교", "",
             "| 방식 | 최초 → 추가 조회 후 파일 | 모델 호출 | 입력 토큰 | 출력 토큰 | 계획·리뷰 시간 | 실행 |",
             "|---|---:|---:|---:|---:|---:|---|"])
    for row in arms.values():
        status = "완료" if row["complete"] else "불완전/실패"
        lines.append(f"| {row['label']} | {row['initialFiles']} → {row['effectiveFiles']} | {row['modelCalls']} | "
                     f"{number(row['inputTokens'])} | {number(row['outputTokens'])} | {seconds(row['endToEndWallMs'])} | {status} |")
    lines.extend(["", "전체 코드는 manifest에 포함된 모든 소스를 배치로 전달합니다. 나머지 세 방식은 같은 코드·설정 인덱스, "
                  "파일/바이트 예산, 후속 조회 한도를 사용합니다. 비전 방식은 조회 계획에서 이미지 추출 구조를 재사용하며, "
                  "선택 이득이 없으면 코드 인덱스로 대체하고 구조 맥락을 리뷰 입력에 넣지 않습니다. "
                  "구조 JSON 방식은 같은 그림을 생성한 원본 구조를 직접 제공합니다. 구조 JSON에는 취약점 정답이나 파일 경로가 없습니다.", "",
                  f"전체 코드의 최초 입력은 **{arms['full_code']['initialModelCalls']}개 독립 배치**입니다. 이전 배치의 판단을 다음 배치에 전달하지 않으므로 "
                  "서비스 간 데이터 출처와 사용 지점이 다른 배치로 나뉘면 근거를 함께 확인하지 못할 수 있습니다. "
                  "이는 모든 소스를 한 번에 이해하는 전체 프로그램 분석과 다릅니다.", "",
                  "입력 토큰은 Ollama가 각 호출에 보고한 값을 더했습니다. 출력 한도에 도달하거나 요청이 실패한 실행도 숨기지 않습니다. "
                  "계획·리뷰 시간에는 해당 방식의 파일 선택과 모델 호출이 포함되지만 최초 이미지 인식은 아래에 분리했습니다.", "",
                  "**불완전/실패 실행의 토큰·시간은 그 시도에서 소모한 비용입니다. 성공한 작업을 끝내는 데 걸린 시간이나 성공 처리량으로 해석하면 안 됩니다.**", "",
                  "## 최초 이미지 인식과 재사용 비용", ""])
    vision = report["visionExtraction"]
    metrics = vision["metrics"]
    if metrics:
        lines.append(f"이미지 1회 인식: 입력 **{number(metrics.get('prompt_eval_count'))}토큰**, 출력 "
                     f"**{number(metrics.get('eval_count'))}토큰**, **{seconds(metrics.get('wallDurationMs'))}**. "
                     f"JSON 형식 검증: **{'성공' if vision['complete'] else '실패'}**. 구조 내용의 정확도를 보장하는 판정은 아닙니다.")
    else:
        lines.append("이미지 인식 호출이 정상 응답하지 않아 토큰·추론 시간 집계가 없습니다. 이를 0 비용으로 해석하면 안 됩니다.")
    combined = report["firstVisionCombined"]
    if combined:
        lines.extend(["", f"첫 사용의 비용 합계는 이미지 인식 + 비전 방식 계획·리뷰를 더해 "
                      f"입력 **{number(combined['inputTokens'])}토큰**, 출력 **{number(combined['outputTokens'])}토큰**, "
                      f"**{seconds(combined['wallMs'])}**입니다. 이는 별도의 통합 API 요청을 잰 값이 아니라 두 실측 단계의 합입니다."])
    lines.extend(["", "표의 비전 방식은 저장된 `vision-context.json`을 로컬 파일에서 다시 읽어 재사용한 실제 코드 리뷰 실행입니다. "
                  "이 파일 읽기는 계획 시간에 포함됩니다. "
                  "DB/API 캐시 조회 지연, 최초 추출 맥락 검증·캐시 저장, 사람이 이미지를 작성한 시간, 공통 소스 수집, 예열 비용은 이 표에 포함되지 않습니다. "
                  "초기 인식 실패 후 코드 인덱스로 대체된 경우에는 비전의 효과로 해석하지 않습니다.", "",
                  "## 정답과 근거 품질", "",
                  "| 방식 | 알려진 위험 후보 | 원문 근거까지 일치 | 필수 맥락 파일 | 정상 함수 오탐 | 추가 후보 | 잘못된 본문 인용 | 잘못된 보조 인용 |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"])
    for row in arms.values():
        q = row["quality"]
        if q is None:
            lines.append(f"| {row['label']} | 평가 없음 | 평가 없음 | 평가 없음 | 평가 없음 | 평가 없음 | 평가 없음 | 평가 없음 |")
            continue
        lines.append(f"| {row['label']} | {q['candidateCount']} / {dataset['knownPositiveCount']} | "
                     f"{q['verifiedCount']} / {dataset['knownPositiveCount']} | {q['requiredSelected']} / {dataset['requiredContextCount']} | "
                     f"{len(q['functionLevelNegativeFlags'])} / {dataset['negativeControlCount']} | "
                     f"{q.get('extraCandidates', 0)} | {q.get('invalidEvidence', 0)} | "
                     f"{row['invalidSupportEvidenceCount'] if row['responseAuditAvailable'] else '미확인'} |")
    lines.extend(["", "후보 일치는 정답 파일·유형·행 범위가 맞는 경우입니다. 원문 검증은 해당 호출에 실제로 제공된 "
                  "원문 행의 인용과 필요한 보조 근거까지 맞아야 통과합니다. 정상 대조 사례는 파일 전체가 아니라 함수의 행 범위로 "
                  "판정합니다. 취약 함수와 정상 함수가 같은 파일에 있어도 서로 혼동하지 않습니다.", "",
                  "필수 맥락 파일의 포함 여부는 검색 범위 지표입니다. 모든 줄을 모델이 올바르게 이해했다는 뜻은 아닙니다. "
                  "로그에는 모르는 경로, 후속 조회 거절, 출력 중단도 남겨 두었습니다. 전체 보안 탐지율이나 개인정보보호법 준수율로 일반화할 수 없습니다.", ""])
    lines.extend(["집계 JSON의 `authoredLabelChecksPass`는 실행 완료·작성된 정답·인용·필수 맥락·정상 대조 사례를 확인합니다. "
                  "`allMeasuredChecksPass`는 여기에 원문 응답 감사가 완료되고, 미해결·거절·후속 응답에서 버려진 추가 조회와 잘못된 보조 인용이 없어야 통과합니다. "
                  "잘못된 경로를 안전하게 거절했더라도 조회 요구를 충족한 것으로 세지 않습니다.", ""])
    if not report["responseAudit"]["available"]:
        lines.extend(["**원문 응답 감사 파일이 없어 후속 응답에서 누락된 조회와 보조 인용 오류는 미확인입니다. "
                      "러너의 대기열이 비어 있어도 모든 조회 요구가 완료되었다고 판단하지 않습니다.**", ""])
    missing_any = False
    for row in arms.values():
        q = row["quality"]
        if q is None:
            continue
        if q["missingVerifiedIds"] or q["missingRequiredContext"]:
            missing_any = True
            lines.append(f"- **{row['label']}**: 근거까지 확인하지 못한 위험 `{', '.join(q['missingVerifiedIds']) or '없음'}`; "
                         f"누락 맥락 `{', '.join(q['missingRequiredContext']) or '없음'}`.")
    if not missing_any and report["allTrialsComplete"] and all(row["quality"] is not None for row in arms.values()):
        lines.append("모든 방식에서 알려진 위험의 근거와 필수 맥락이 확인되었습니다. 이 결과도 작성한 정답 범위에 한정됩니다.")
    elif not missing_any:
        lines.append("실패 또는 평가 누락이 있는 실행은 위험·필수 맥락을 모두 확인한 것으로 해석하지 않습니다.")
    lines.extend(["", "## 이미지와 코드 연결", "",
                  f"추출된 컴포넌트: **{number(vision.get('components'))}개**, 연결: **{number(vision.get('flows'))}개**. "
                  "이 개수 자체를 구조 인식 정확도로 해석하지 않습니다.", ""])
    graph_quality = vision.get("graphQuality")
    if graph_quality:
        lines.extend([f"원본 합성 그래프와 비교하면 컴포넌트 ID 일치 **{number(graph_quality.get('componentIdentitiesMatched'))} / "
                      f"{number(graph_quality.get('componentsExpected'))}**, 방향을 포함한 연결 일치 "
                      f"**{number(graph_quality.get('edgesMatched'))} / {number(graph_quality.get('edgesExpected'))}**입니다. "
                      f"매핑된 추가 연결 **{len(graph_quality.get('unexpectedMappedEdges', []))}개**, "
                      f"누락 연결 **{len(graph_quality.get('missingEdges', []))}개**입니다.", "",
                      "컴포넌트 ID 또는 화면에 보이는 식별자 토큰을 정확히 대조한 결과입니다. "
                      "역할 해석·데이터 내용·보호 수단의 의미까지 맞았다는 정확도는 아닙니다. "
                      "예를 들어 브로커를 거치는 두 연결을 서비스 사이의 직접 연결로 요약하면 정확한 방향·끝점 대조에서는 불일치입니다. "
                      "이런 추상화와 의미상 잘못된 연결을 같은 오류라고 단정할 수 없습니다. "
                      "매핑되지 않은 끝점을 가진 연결은 위 추가 연결 개수에 포함되지 않으므로 전체 오탐 개수로 해석하지 않습니다.", ""])
    else:
        lines.extend(["원본 그래프와의 ID·연결 대조 결과는 기록되지 않았습니다. 추출된 개수만으로 정확도를 계산하지 않습니다.", ""])
    for name in ("vision_index", "structure_json_index"):
        routing = arms[name]["routing"]
        if routing:
            mapping = routing.get("mappingCount") or {}
            decision = routing.get("decision") or {}
            lines.append(f"- **{LABELS[name]}**: 코드 모듈 연결 {mapping.get('matched', 0)} / {mapping.get('total', 0)}, "
                         f"모호함 {mapping.get('ambiguous', 0)}, 연결 불가 {mapping.get('unmatched', 0)}. "
                         f"선택 판단 `{decision.get('reason', 'UNKNOWN')}`, 구조 맥락 전달 `{decision.get('useVisionContext', False)}`.")
    lines.extend(["", "DB·메시지 브로커·외부 서비스는 대응하는 코드 모듈이 없을 수 있으므로 연결 불가를 모두 인식 오류로 세지 않습니다. "
                  "그림에 없는 `jobs/legacy_export.py`도 코드에는 남겨 두어 누락 위험을 확인했습니다.", "",
                  "## 같은 입력인지 확인", ""])
    equal_requests = [pair for pair in report["pairwiseComparisons"] if pair["identicalOrderedModelRequests"]]
    if equal_requests:
        for pair in equal_requests:
            lines.append(f"- **{LABELS[pair['left']]} ↔ {LABELS[pair['right']]}**: 요청별 SHA256가 순서까지 같습니다. "
                         "리뷰 입력이 같은 실행의 시간 차이를 비전의 추가 효과로 설명할 수 없습니다.")
    else:
        lines.append("모든 호출을 합친 요청 SHA256 시퀀스가 같은 쌍은 없습니다. 후속 조회가 달라졌기 때문일 수 있으므로 이 사실만으로 초기 입력 방식에 차별적인 효과가 있었다고 해석하지 않습니다.")
    initial_only_equal = [pair for pair in report["pairwiseComparisons"] if pair["identicalInitialModelRequests"] and not pair["identicalOrderedModelRequests"]]
    for pair in initial_only_equal:
        lines.append(f"- **{LABELS[pair['left']]} ↔ {LABELS[pair['right']]}**: 최초 모델 요청 SHA256는 순서까지 같지만 "
                     "후속 요청을 포함한 전체 시퀀스는 다릅니다. 이후 생성 응답·추가 조회 과정에서 생긴 차이를 초기 비전 파일 선택의 효과로 해석하지 않습니다.")
    selected_equal = [pair for pair in report["pairwiseComparisons"] if pair["sameInitialPathSet"] and not pair["identicalInitialModelRequests"]]
    for pair in selected_equal:
        lines.append(f"- **{LABELS[pair['left']]} ↔ {LABELS[pair['right']]}**: 최초 선택 파일 집합은 같습니다. "
                     "맥락 텍스트 또는 후속 조회 요청이 달라졌을 수 있으므로 요청 해시와 추가 조회를 함께 보세요.")
    lines.extend(["", "실행 순서는 전체 코드 → 코드 인덱스 → 비전+인덱스 → 구조 JSON+인덱스로 고정했고, "
                  "모델 예열 후 캐시를 강제 초기화하지 않았습니다. 각 방식 1회이므로 캐시·순서·시스템 부하 영향을 분리한 평균 latency나 SLA가 아닙니다.", "",
                  "같은 최초 요청에서도 생성 응답과 그에 따른 후속 조회가 달라질 수 있습니다. "
                  "고정 seed를 사용했다는 사실만으로 생성·시간 변동을 제거한 비교라고 주장하지 않습니다. "
                  "특히 같은 코드 선택으로 대체된 방식의 단일 실행 시간 차이는 비전의 추가 성능을 입증하지 않습니다.", "",
                  "## 오류·미확인 사항", ""])
    for row in arms.values():
        routing = row["routing"] or {}
        coverage = routing.get("coverage") or {}
        lines.append(f"- **{row['label']}**: 실행 오류 {len(row['errors'])}, 미해결 추가 조회 {len(row['unresolvedNeeds'])}, "
                     f"거절된 추가 조회 {len(row['rejectedNeeds'])}, 인덱스 문제 {len(coverage.get('indexIssues', []))}, "
                     f"미해결 설정 경로 {len(coverage.get('unresolvedRoutes', []))}. "
                     f"상세 오류: `{row['trialError'] or ', '.join(str(e.get('code', 'UNKNOWN')) for e in row['errors']) or '없음'}`.")
        discarded = row["discardedValidFollowupNeeds"]
        if discarded is None:
            lines.append("  후속 응답에서 러너가 버린 유효한 조회와 보조 인용 오류: **감사 없음·미확인**.")
        else:
            paths = sorted({item["path"] for item in discarded})
            lines.append(f"  후속 응답에서 러너가 버린 유효한 조회 **{len(discarded)}건**, "
                         f"잘못된 보조 인용 **{row['invalidSupportEvidenceCount']}건**. "
                         f"누락 조회 경로: `{', '.join(paths) or '없음'}`.")
    lines.extend(["", "이 실험은 코드 리뷰와 맥락 선택을 측정했습니다. 수정 패치 생성·실행, 컴파일, 배포, 실제 개인정보, "
                  "프로덕션 규모의 독립 서비스 운영을 검증하지 않았습니다. 모델·프롬프트·예산·파일 해시는 protocol에 고정되어 있습니다.", "",
                  "## 재현과 원본", "",
                  "- [고정 프로토콜](protocol.json), [원시 호출·결과 로그](measurements.jsonl), [집계 JSON](summary.json)",
                  "- [아키텍처 이미지](architecture.png), [SVG 원본](architecture.svg), [렌더링 해시](architecture.render.json)",
                  "- [코드 인덱스 선택](code_index-plan.json), [비전 구조 선택](vision_index-plan.json), [구조 JSON 선택](structure_json_index-plan.json)",
                  "", "재집계: `.venv/bin/python scripts/summarize_complex_architecture.py`. 모델을 다시 호출하지 않습니다. "
                  "마지막 `finished` 이벤트가 없는 로그는 완료 보고서로 집계하지 않습니다."])
    if report["responseAudit"]["available"]:
        lines.extend(["", "원문 응답 감사: [응답 감사 결과](response-audit.json), [모델 응답 원문](model-responses.jsonl). "
                      "집계 시 프로토콜·측정 로그·응답 원문 해시를 대조했습니다."])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=PUBLIC)
    parser.add_argument("--ground-truth", type=Path, default=DATA / "ground_truth.json")
    parser.add_argument("--manifest", type=Path, default=DATA / "manifest.json")
    args = parser.parse_args()
    try:
        report = load_report(args.directory, args.ground_truth, args.manifest)
    except (ValueError, KeyError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    args.directory.mkdir(parents=True, exist_ok=True)
    (args.directory / "summary.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (args.directory / "RESULTS.md").write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"arms": {name: {key: row[key] for key in ("complete", "initialFiles", "effectiveFiles", "inputTokens", "outputTokens", "endToEndWallMs", "quality")}
                               for name, row in report["arms"].items()},
                      "visionExtraction": report["visionExtraction"], "firstVisionCombined": report["firstVisionCombined"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
