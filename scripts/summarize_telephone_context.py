#!/usr/bin/env python3
"""Render an honest telephone-context report from immutable JSONL measurements.

This script does not run models, change protocol/labels, or rewrite raw logs.
By default it refuses an unfinished run. Use --allow-incomplete for a clearly
marked progress snapshot, never a completed comparison.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIRECTORY = ROOT / "docs/benchmarks"
ARMS = ("full_backend_scope", "indexed_code", "cached_vision_index")
LABELS = {
    "full_backend_scope": "전체 백엔드 범위",
    "indexed_code": "코드 인덱스 선별",
    "cached_vision_index": "비전 캐시 + 코드 인덱스",
}


def number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value >= 0


def fmt(value, digits=0):
    return f"{value:,.{digits}f}" if number(value) else "미기록"


def seconds(value):
    return f"{value / 1000:,.3f}" if number(value) else "미기록"


def summed(*values):
    return sum(values) if all(number(value) for value in values) else None


def counts(row):
    quality = row.get("quality", {})
    return (
        len(set(quality.get("candidateMatches", []))),
        len(set(quality.get("sourceVerifiedMatches", []))),
        quality.get("expectedCandidates"),
        quality.get("requiredContextSelected"),
        quality.get("requiredContextTotal"),
    )


def passed(row):
    _, verified, expected, selected, required = counts(row)
    return (row.get("complete") is True and number(expected) and expected > 0
            and verified == expected and number(required) and required > 0 and selected == required)


def read_log(path, allow_incomplete=False):
    raw = path.read_bytes()
    rows = []
    for i, line in enumerate(raw.decode("utf-8").splitlines(), 1):
        if line.strip():
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"JSONL row {i} is incomplete or invalid; no report written") from exc
            if not isinstance(row, dict):
                raise ValueError(f"JSONL row {i} must be an object")
            rows.append(row)
    metadata = [row for row in rows if row.get("event") == "metadata"]
    if len(metadata) != 1:
        raise ValueError("Exactly one metadata row is required")
    trials = {}
    for row in rows:
        if row.get("event") != "trial":
            continue
        arm = row.get("arm")
        if arm not in ARMS:
            raise ValueError(f"Unknown trial arm: {arm}")
        if arm in trials:
            raise ValueError(f"Duplicate trial arm: {arm}; do not select a favorable repeat")
        trials[arm] = row
    finished = bool(rows and rows[-1].get("event") == "finished")
    if not allow_incomplete and (not finished or set(trials) != set(ARMS)):
        raise ValueError("Run is not finished; wait for all three arms and final event")
    return metadata[0], trials, finished, hashlib.sha256(raw).hexdigest()


def metric(row, key):
    return row.get("totals", {}).get(key)


def request_hashes(row):
    values = [call.get("requestSha256") for call in row.get("calls", [])]
    return values if values and all(isinstance(value, str) and value for value in values) else None


def render(metadata, trials, finished, log_sha, log_name="telephone-context.jsonl"):
    indexed = trials.get("indexed_code")
    vision = trials.get("cached_vision_index")
    full = trials.get("full_backend_scope")
    prior = metadata.get("visionOneTimeCost", {})
    plan = (vision or {}).get("plan") or {}
    decision = plan.get("decision", {})
    module_matches = plan.get("moduleMatches", [])
    matched = sum(item.get("status") == "MATCHED" for item in module_matches)
    same_sources = bool(indexed and vision and indexed.get("selectedPaths") == vision.get("selectedPaths"))
    ih, vh = request_hashes(indexed or {}), request_hashes(vision or {})
    same_requests = bool(ih and vh and ih == vh)
    lines = ["# 전화번호 맥락 선별 실험 결과", ""]
    if not finished or len(trials) != len(ARMS):
        lines += ["**실행 중간 기록입니다. 완료되지 않은 실험으로 성능 우열이나 품질 통과를 결론 내리지 않습니다.**", ""]
    if vision and decision.get("useVisionContext") is False:
        lines += [f"이번 비전 결합 요청은 `{decision.get('reason', 'UNKNOWN')}`로 **코드 인덱스 방식으로 돌아갔습니다**. "
                  f"다이어그램 구성요소와 저장소 모듈의 매칭은 {matched}/{len(module_matches)}개이며, 비전 맥락은 리뷰 프롬프트에 투입되지 않았습니다.", ""]
    if same_sources:
        lines += [f"두 선별군은 동일한 {len(indexed.get('selectedPaths', []))}개 파일, {fmt(indexed.get('selectedBytes'))} bytes를 선택했습니다. "
                  + ("배치별 요청 SHA-256도 모두 같습니다. " if same_requests else "요청 전체의 동일성은 별도로 확인해야 합니다. ")
                  + "따라서 두 군의 관측 latency 차이를 비전의 성능 향상으로 해석할 수 없습니다.", ""]
    failed_quality = [LABELS[arm] for arm in ARMS if arm in trials and not passed(trials[arm])]
    if failed_quality:
        lines += ["**품질 게이트 미충족: " + ", ".join(failed_quality) + ".** "
                  "토큰·시간 감소만으로 동일 품질의 효율 개선이나 안전한 수정안을 입증하지 못합니다.", ""]
    lines += ["## 데이터와 고정 조건", "",
              f"[공개 Petclinic 스냅샷](https://github.com/spring-petclinic/spring-petclinic-microservices/tree/{metadata.get('commit', '')})의 "
              f"백엔드 소스·테스트·설정 {fmt(metadata.get('sourceFiles'))}개, {fmt(metadata.get('sourceBytes'))} bytes를 사용했습니다. "
              "Java·SQL·YAML·XML·properties 범위이며 UI·이미지·생성 CSS·별도 설정 저장소는 포함하지 않습니다. "
              "고정된 교육용 마이크로서비스 예제 한 건이며, 초대형 기업 저장소의 성능을 검증한 실험이 아닙니다. "
              "HSQLDB 기본값/MySQL 선택 프로필이고 PostgreSQL 실험이 아닙니다.", "",
              f"모델은 `{metadata.get('model', '미기록')}`, 설정은 `{json.dumps(metadata.get('options', {}), ensure_ascii=False, sort_keys=True)}`입니다. "
              "하나의 고정 전화번호 과제를 군별 1회, 전체 → 코드 인덱스 → 비전 캐시 순서로 실행했습니다. "
              "모델은 이미 준비된 상태이며 호출 사이 캐시를 비우지 않았습니다. p95·통계적 유의성·운영 SLA를 측정한 결과가 아닙니다.", "",
              "이미지는 upstream 원본이며 경로·정답을 추가하지 않았습니다. 설명용 `public-architecture.png`는 측정에 사용하지 않았습니다. "
              "[프로토콜](petclinic-protocol.json), [프로토콜 작성 시점 설명](petclinic-protocol-chronology.json), "
              "[데이터 출처](PUBLIC_PROJECT_DATA.md), [검토자 정답](public-telephone-case.json)을 함께 확인하세요. "
              "프로토콜은 전화번호 리뷰 전에 고정됐지만 최초 이미지 해석은 그보다 먼저 시작됐습니다.", "",
              "## 측정 비용", "",
              "아래 토큰 수는 Ollama가 반환한 입력·출력 토큰입니다. 소스 bytes를 토큰으로 환산하지 않았습니다. "
              "리뷰 LLM 시간은 HTTP 호출 wall time 합계이며, 군별 처리 시간은 계획 수립과 리뷰 전체의 측정값입니다. "
              "미완료 군의 값은 실패를 포함해 소모한 비용이며, 성공한 검토의 완료 시간이나 동등한 산출물의 성능 비교가 아닙니다.", "",
              "| 방식 | 선택 파일 / bytes | 리뷰 호출 | 입력 토큰 | 출력 토큰 | 리뷰 LLM 합계(초) | 인덱스·선별(ms) | 군별 처리(초) |",
              "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |"]
    for arm in ARMS:
        row = trials.get(arm)
        if row is None:
            lines.append(f"| {LABELS[arm]} | 대기 | — | — | — | — | — | — |")
            continue
        label = LABELS[arm] + (" (미완료)" if not row.get("complete") else "")
        lines.append(f"| {label} | {len(row.get('selectedPaths', []))} / {fmt(row.get('selectedBytes'))} | "
                     f"{len(row.get('calls', []))} | {fmt(metric(row, 'prompt_eval_count'))} | {fmt(metric(row, 'eval_count'))} | "
                     f"{seconds(metric(row, 'wallDurationMs'))} | {fmt(row.get('planningWallMs'), 3)} | {seconds(row.get('endToEndWallMs'))} |")
    lines += ["", f"공통 원본 수집 시간은 **{fmt(metadata.get('collectionWallMs'), 3)} ms**입니다. "
              "고정 커밋의 파일을 읽고 SHA-256을 검사하는 이 단계는 실행 시작 때 한 번 수행되어 위 각 군의 처리 시간에는 포함되지 않습니다. "
              "현재 선별 구현도 전체 범위의 소스를 로컬에서 읽고 인덱싱합니다. 줄이는 것은 주로 LLM에 전달하는 코드량이며, 저장소 전체를 전혀 읽지 않는 방식은 아닙니다.", "",
              "인덱스 구축·후보 선별은 `planningWallMs`로 함께 측정했습니다. 이 둘을 나눈 개별 시간은 기록되지 않았습니다. "
              "비전 캐시 군의 같은 측정에는 실제 JSON 캐시 읽기도 포함됩니다. 네트워크 실패가 발생한 경우 LLM 합계에 누락된 시간은 군별 전체 시간·오류 목록과 함께 봐야 합니다.", ""]
    if full and indexed and number(metric(full, "prompt_eval_count")) and metric(full, "prompt_eval_count") > 0 and number(metric(indexed, "prompt_eval_count")):
        reduction = (1 - metric(indexed, "prompt_eval_count") / metric(full, "prompt_eval_count")) * 100
        lines += [f"코드 인덱스 군의 입력 토큰은 전체 범위 대비 {reduction:.2f}% 적었습니다. "
                  "이는 이번 선택 범위의 비용 비교이며, 아래 품질 게이트와 별개입니다. 비전 기여로 계산하지 않습니다.", ""]
    lines += ["## 최초 이미지 처리와 캐시 재사용", "",
              f"원본 이미지 해석 1회 비용은 **{seconds(prior.get('wallDurationMs'))}초**, "
              f"입력 **{fmt(prior.get('prompt_eval_count'))}토큰**, 출력 **{fmt(prior.get('eval_count'))}토큰**입니다. "
              "이 비용을 캐시 재사용 요청마다 다시 청구한 것으로 합산하지 않습니다.", "",
              "| 구간 | 시간(초) | 입력 토큰 | 출력 토큰 | 값의 의미 |",
              "| --- | ---: | ---: | ---: | --- |",
              f"| 이미지 최초 해석 | {seconds(prior.get('wallDurationMs'))} | {fmt(prior.get('prompt_eval_count'))} | {fmt(prior.get('eval_count'))} | 별도 실측 |"]
    if vision:
        cold_time = summed(metadata.get("collectionWallMs"), prior.get("wallDurationMs"), vision.get("endToEndWallMs"))
        lines += [f"| 캐시가 있는 후속 리뷰 | {seconds(vision.get('endToEndWallMs'))} | {fmt(metric(vision, 'prompt_eval_count'))} | {fmt(metric(vision, 'eval_count'))} | 캐시 읽기·계획·리뷰 실측; 공통 수집 제외 |",
                  f"| 최초 등록 + 수집 + 첫 리뷰 | {seconds(cold_time)} | {fmt(summed(prior.get('prompt_eval_count'), metric(vision, 'prompt_eval_count')))} | "
                  f"{fmt(summed(prior.get('eval_count'), metric(vision, 'eval_count')))} | 개별 실측 단계의 산술합; 하나의 최초 요청을 연속 측정한 값은 아님 |"]
    attribution = ("비전이 사용되지 않은 이번 실행은 비전 추가 비용을 상쇄하는 고유 이득을 입증하지 못합니다."
                   if vision and decision.get("useVisionContext") is False else
                   "이 반복 수와 과제 수만으로 비전 추가 비용을 상쇄하는 일반적인 손익분기를 입증할 수 없습니다.")
    lines += ["", "여기서 ‘최초’는 이미지 해석 비용을 처음 포함한다는 의미입니다. GPU·모델 콜드 스타트는 측정하지 않았습니다. "
              "동일 입력의 두 선별 요청에서 발생한 시간 차이로 손익분기 요청 횟수를 계산하지 않습니다. " + attribution, "",
              "## 품질 게이트", "",
              "후보 일치는 알려진 두 로그 위치와 일치했는지를 봅니다. 원문 근거 검증은 현재 배치에 제공된 정확한 행·인용과 "
              "`Owner.toString` 또는 record 전화번호 선언까지의 연결을 요구합니다. "
              "필요 맥락 회수는 검토자가 정한 경로 12개 중 선택된 수이며, 선택했다는 사실만으로 모델이 모두 이해했다는 뜻은 아닙니다.", "",
              "| 방식 | 실행 완료 | 후보 위치 | 교차 파일·원문 검증 | 필요 맥락 회수 | 근거 인용 실패 | 보수적 게이트 |",
              "| --- | --- | ---: | ---: | ---: | ---: | --- |"]
    for arm in ARMS:
        row = trials.get(arm)
        if row is None:
            lines.append(f"| {LABELS[arm]} | 대기 | — | — | — | — | 미판정 |")
            continue
        candidates, verified, expected, selected, required = counts(row)
        lines.append(f"| {LABELS[arm]} | {'완료' if row.get('complete') else '실패/불완전'} | "
                     f"{candidates}/{fmt(expected)} | {verified}/{fmt(expected)} | {fmt(selected)}/{fmt(required)} | "
                     f"{fmt(row.get('quality', {}).get('sourceEvidenceFailures'))} | {'통과' if passed(row) else '미충족'} |")
    lines += ["", "보수적 게이트는 실행 완료 + 알려진 후보 2개 모두의 원문·연결 근거 검증 + 필요 맥락 12개 회수를 요구합니다. "
              "이 게이트를 통과하더라도 수정 코드의 컴파일·테스트·배포나 법률 준수 검증을 대체하지 않습니다. "
              "후보 발견과 인용 실패를 혼동하지 않으며, 이 로그만으로 전역 오탐률·정밀도를 계산하지 않습니다.", ""]
    for arm in ARMS:
        row = trials.get(arm)
        if not row:
            continue
        missing = row.get("quality", {}).get("missingRequiredContext", [])
        if missing:
            lines += [f"**{LABELS[arm]}에서 빠진 필수 맥락:**", ""]
            lines += [f"- `{path}`" for path in missing]
            lines.append("")
        errors = row.get("errors", [])
        if errors or row.get("error"):
            lines += [f"**{LABELS[arm]} 오류:** `{json.dumps(errors or row.get('error'), ensure_ascii=False)}`", ""]
    lines += ["## 해석과 다음 검증", "",
              "전체 범위 군은 20,000-byte 기준의 독립 배치로 코드를 보냈습니다. 파일 간 근거가 서로 다른 배치에 분리될 수 있으며, "
              "별도의 교차 배치 통합 추론은 수행하지 않았습니다. 선별군은 같은 파일 수·바이트 예산을 사용했습니다. "
              "이 비교는 전체 범위를 무조건 보내는 전략과 제한된 맥락을 고르는 전략의 파일 배치 방식 차이도 포함합니다.", "",
              "관측한 결과를 유지한 채 다음 실험에서 원본 이미지의 서비스 이름을 저장소 모듈과 연결하는 규칙, SQL/설정·AI 호출 경로 회수, "
              "근거 누락 시 추가 조회를 검증해야 합니다. 이 실행이 끝난 뒤 선택 규칙을 바꾸고 같은 로그에 결과를 덮어쓰면 안 됩니다. "
              "추가 실험은 별도 프로토콜과 로그로 기록합니다.", "",
              "추천은 변경 계획이며 코드가 생성·적용·컴파일·실행된 결과가 아닙니다. 원본 DB 설정은 HSQLDB/MySQL이고 "
              "별도 외부 설정·실제 접근 권한·로그 보존·운영 트래픽은 확인하지 않았습니다.", "",
              "## 감사와 재현", "",
              f"- 원시 측정: [{log_name}]({log_name}), SHA-256 `{log_sha}`",
              f"- 리뷰 실행기 SHA-256: `{metadata.get('runnerSha256', '미기록')}`",
              f"- 선별기 SHA-256: `{metadata.get('plannerSha256', '미기록')}`",
              f"- 프로토콜 SHA-256: `{metadata.get('protocolSha256', '미기록')}`",
              "- 모델 원문 응답: `.runtime/architecture-benchmark/telephone/`의 군·배치별 JSON. 공개 요약에는 원문을 복사하지 않았습니다.",
              "- 모델 태그는 기록됐지만 이 로그만으로 가중치 digest와 하드웨어 전체 조건을 검증할 수는 없습니다.", "",
              "```bash", ".venv/bin/python scripts/summarize_telephone_context.py", "```", "",
              "생성기는 원시 JSONL을 읽기만 하며 완료 이벤트와 세 군의 기록이 없으면 기본적으로 보고서를 쓰지 않습니다. "
              "`--allow-incomplete`를 명시한 경우에만 실행 중임을 표시한 중간 문서를 만듭니다.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=DIRECTORY / "telephone-context.jsonl")
    parser.add_argument("--output", type=Path, default=DIRECTORY / "TELEPHONE_CONTEXT_RESULTS.md")
    parser.add_argument("--allow-incomplete", action="store_true")
    args = parser.parse_args()
    if args.log.resolve() == args.output.resolve():
        raise SystemExit("Output must not overwrite the measurement log")
    try:
        metadata, trials, finished, sha = read_log(args.log, args.allow_incomplete)
        report = render(metadata, trials, finished, sha, args.log.name)
    except (ValueError, OSError) as exc:
        raise SystemExit(str(exc)) from exc
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(report, encoding="utf-8")
    print(json.dumps({"output": str(args.output), "finished": finished, "arms": len(trials), "logSha256": sha}, ensure_ascii=False))


if __name__ == "__main__":
    main()
