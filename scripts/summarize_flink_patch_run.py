"""Readable paired patch report from immutable raw measurements, no inference."""
import argparse
import json
from pathlib import Path
import statistics

from benchmark_flink_patches import summarize, OUT
from flink_patch_validation import SECURITY_TESTS


def main(out):
    summarize(out)
    comparison = json.loads((out / 'comparison.json').read_text())
    protocol = json.loads((out / 'protocol.json').read_text())
    calibration = json.loads((out / 'calibration.json').read_text())
    rows_path = out / 'measurements.jsonl'
    rows = [json.loads(s) for s in rows_path.read_text().splitlines()] if rows_path.exists() else []
    vision_path = out / 'calls/architecture.json'
    vision = json.loads(vision_path.read_text()) if vision_path.exists() else {}
    usage = vision.get('usage') or {}
    cached = (usage.get('input_tokens_details') or {}).get('cached_tokens', 0)
    # Standard snapshot pricing; usage comes from the actual provider response.
    vision_cost = ((usage['input_tokens'] - cached) * .75 + cached * .075
                   + usage['output_tokens'] * 4.5) / 1_000_000 if (
        protocol['visionProvider'] == 'openai' and 'input_tokens' in usage and 'output_tokens' in usage
    ) else 0 if protocol['visionProvider'] == 'ollama' else None
    labels = {'full_code': '비전 없음: 전체 선언 범위', 'code_index': '비전 없음: 코드 검색',
              'vision_index': '비전 있음: 코드 검색+그림'}
    table, details = [], {}
    for arm, name in labels.items():
        trials = [r for r in rows if r['arm'] == arm]
        stats = comparison['arms'][arm]
        verified = [r for r in trials if r.get('verification', {}).get('cases')]
        security = [sum(state == 'PASSED' for key, state in r['verification']['cases'].items()
                        if key.split('#')[-1] in SECURITY_TESTS) for r in verified]
        functions = [sum(state == 'PASSED' for key, state in r['verification']['cases'].items()
                        if key.split('#')[-1] not in SECURITY_TESTS) for r in verified]
        failures = [{k: r.get(k) for k in ('repeat', 'status', 'error')} for r in trials if not r.get('accepted')]
        output_counts = [r.get('outputTokens') for r in trials]
        selections = []
        for r in trials:
            path = out / 'trials' / f"{r['repeat']}-{arm}" / 'selection.json'
            if path.exists():
                p = json.loads(path.read_text())
                selections.append({'files': len(p['selectedPaths']), 'bytes': p['sourceBytes'],
                                   'extraVisionPaths': p['extraVisionPaths'] if arm == 'vision_index' else []})
        details[arm] = {**stats, 'verificationExecutedTrials': len(verified),
            'securityTestsPassedPerVerifiedTrial': security,
            'functionTestsPassedPerVerifiedTrial': functions,
            'medianRequestMs': statistics.median(r['wallMs'] for r in trials) if trials else None,
            'meanRequestMs': statistics.mean(r['wallMs'] for r in trials) if trials else None,
            'outputTokens': sum(output_counts) if output_counts and all(isinstance(n, int) for n in output_counts) else None,
            'selection': selections, 'failures': failures,
            'modelCalls': sum(r.get('modelCalls', 0) for r in trials),
            'stagesMs': {stage: sum(r.get(stage, 0) for r in trials)
                         for stage in ('selectionMs', 'inspectionMs', 'patchGenerationMs')},
            'validationMs': sum(r.get('verification', {}).get('wallMs', 0) for r in trials)}
        details[arm]['apiCostUsd'] = vision_cost if arm == 'vision_index' else 0
        details[arm]['meanInputTokens'] = (stats['inputTokens'] / len(trials)
            if trials and stats['inputTokens'] is not None else None)
        details[arm]['modelWallMs'] = sum(json.loads(p.read_text()).get('wallMs', 0)
            for r in trials for p in (out / 'calls').glob(f"{r['repeat']}-{arm}-*.json"))
        calls = [json.loads(p.read_text()) for r in trials
                 for p in (out / 'calls').glob(f"{r['repeat']}-{arm}-*.json") if not p.stem.endswith('-input')]
        details[arm]['localRuntimeMs'] = {stage: sum(c.get(stage, 0) or 0 for c in calls)/1_000_000
                                        for stage in ('loadNs', 'prefillNs', 'generationNs')}
        details[arm]['patchChurn'] = [{key: r.get('patch', {}).get(key)
            for key in ('changedPaths', 'addedLines', 'removedLines')} for r in trials]
    def display(value, scale=1):
        return '미측정' if value is None else f'{value / scale:,.2f}' if scale != 1 else f'{value:,}'
    columns = list(labels)
    def row(name, getter):
        table.append('| ' + name + ' | ' + ' | '.join(str(getter(details[a])) for a in columns) + ' |')
    row('실험 완료/계획', lambda r: f"{r['recorded']}/{r['scheduled']}")
    row('전체 품질 검증 통과 패치', lambda r: f"{r['accepted']}/{r['scheduled']}")
    row('실제 회귀 테스트 실행', lambda r: f"{r['verificationExecutedTrials']}/{r['scheduled']}")
    row('보안 5개 중 통과 수(실행별)', lambda r: ', '.join(map(str, r['securityTestsPassedPerVerifiedTrial'])) or '미측정')
    row('기능·안전 로그 56개 중 통과 수(실행별)', lambda r: ', '.join(map(str, r['functionTestsPassedPerVerifiedTrial'])) or '미측정')
    row('요청 완료 시간 중앙값(초)', lambda r: display(r['medianRequestMs'], 1000))
    row('요청 완료 시간 평균(초)', lambda r: display(r['meanRequestMs'], 1000))
    row('초기 그림 분석 포함 전체 합계(초)', lambda r: display(r['firstUseTotalMs'], 1000))
    row('코딩 모델 호출 수', lambda r: r['modelCalls'])
    row('코딩 모델 입력 토큰 합계', lambda r: display(r['inputTokens']))
    row('코딩 모델 출력 토큰 합계', lambda r: display(r['outputTokens']))
    row('최초 비전 입력 포함 토큰 합계', lambda r: display(r['firstUseInputTokens']))
    row('추정 API 비용(3회 합계, USD)', lambda r: '미측정' if r['apiCostUsd'] is None else f"${r['apiCostUsd']:.6f}")
    report = ['# Flink 실제 수정 코드: 비전 미도입·도입 비교', '',
        f"기준 커밋: `{protocol['commit']}`. 코드 범위 {len(protocol['paths'])}개·{protocol['sourceBytes']:,} bytes.",
        f"패치 생성: `{protocol['codingModel']}`. 비전: `{protocol['visionModel']}`.", '',
        '| 항목 | ' + ' | '.join(labels.values()) + ' |', '| --- | --- | --- | --- |', *table, '',
        '## 해석 기준', '',
        '전체 선언 범위 대비 차이는 검색과 비전의 합산 효과입니다. 코드 검색 대비 차이가 비전의 추가 효과입니다. '
        '생성 실패·패치 적용 실패도 전체 성공률 분모와 처리 시간에 포함합니다. 테스트를 실행하지 못한 패치를 보안 테스트 0점 또는 통과로 위장하지 않습니다.', '',
        '시간에는 실제 코드 선택·추가 조회·생성·격리 빌드/테스트를 포함합니다. '
        '환경 설치·공통 의존성 다운로드·검증기 교정은 별도 준비 작업입니다. '
        '누적 합계에는 비전 최초 분석을 한 번 포함하며, 캐시 요청 시간은 실제 파일 재조회부터 측정합니다. '
        '실패가 더 빨리 끝났다는 이유만으로 효율 향상이라고 판단하지 않습니다.', '',
        '## 시간 구성과 입력 범위', '',
        '| 항목(3회 합계) | ' + ' | '.join(labels.values()) + ' |', '| --- | --- | --- | --- |',
        '| 코드 모델 응답 시간(초) | ' + ' | '.join(f"{details[a]['modelWallMs']/1000:.2f}" for a in columns) + ' |',
        '| 격리 빌드·테스트 시간(초) | ' + ' | '.join(f"{details[a]['validationMs']/1000:.2f}" for a in columns) + ' |',
        '| 최초 선택 파일 수(반복별) | ' + ' | '.join(', '.join(str(s['files']) for s in details[a]['selection']) for a in columns) + ' |',
        '| 최초 선택 원문 bytes(반복별) | ' + ' | '.join(', '.join(f"{s['bytes']:,}" for s in details[a]['selection']) for a in columns) + ' |', '',
        f"최초 그림 해석: {comparison.get('visionSetupMs', 0)/1000:.2f}초, "
        f"입력 {comparison.get('visionSetupInputTokens')} / 출력 {comparison.get('visionSetupOutputTokens')} 토큰. "
        '세 번의 비전 요청에서 같은 커밋·이미지에 대한 추출 결과를 재사용했습니다. 선택 파일 수와 실제 추가 조회 수는 다를 수 있습니다.', '',
        '비용은 OpenAI 응답 usage에 [공식 표준 가격](https://developers.openai.com/api/docs/models/gpt-5.4-mini)'
        '(입력 $0.75, 캐시 입력 $0.075, 출력 $4.50 / 백만 토큰)을 적용한 추정값입니다. '
        '로컬 추론의 API 과금은 $0이며, 전력·장비 비용은 측정하지 않았습니다. '
        '서로 다른 모델의 토큰 합계는 청구 비용이나 동일한 연산량을 뜻하지 않습니다.', '',
        '## 실행별 결과', '', '| 반복 | 방식 | 상태 | 전체 품질 통과 | 소요 시간(초) | 오류 |',
        '| --- | --- | --- | --- | --- | --- |']
    for r in rows:
        report.append(f"| {r['repeat']} | {labels[r['arm']]} | {r['status']} | {'예' if r['accepted'] else '아니오'} | {r['wallMs']/1000:.2f} | {r.get('error', '')} |")
    report += ['', '## 자동 판정', '', *[f"- `{base}` 대비: `{verdict['conclusion']}`"
        for base, verdict in comparison['comparisons'].items()], '',
        '## 범위와 한계', '',
        '- 5개 합성 결함을 묶은 업무 1개의 반복 실험입니다. 공개 Flink의 실제 취약점 주장이나 통계적 비열등성 증명이 아닙니다.',
        '- 테스트는 정해진 토큰·로그·TLS 경로와 기존 관련 기능을 검증합니다. 전체 Flink 클러스터·배포 환경·법률 준수 전체를 검증하지 않습니다.',
        '- 모델 로드 시간과 호출 순서가 지연에 영향을 줄 수 있습니다. 원시 호출 로그에 load/prefill/생성 시간을 남겼습니다.',
        '- v1 결과를 본 뒤 설계한 개발용 평가입니다. 다른 프로젝트의 미사용 업무로 일반화 여부를 검증해야 합니다.', '',
        '근거: [고정 프로토콜](protocol.json), [검증기 교정](calibration.json), '
        '[원시 측정](measurements.jsonl), [상세 비교](evaluation.json).', '']
    if (out / 'amendment.json').exists():
        report += ['## 실행 환경 보정 이력', '',
            '첫 실행은 Ollama의 JSON 스키마 `maxLength: 8000` 문법 오류로 모든 로컬 요청이 거절됐습니다. '
            '응답 후 검사에서 같은 길이 제한을 유지하면서 제공자 스키마에서만 해당 제약을 제거했습니다. '
            '모델·데이터·평가 기준·예산은 유지했고, 패치 품질 결과를 보기 전에 보정했습니다. '
            '[변경 및 재사용 근거](amendment.json), [실패한 첫 실행](../patch-v2-run/EVALUATION.md).', '',
            '비전 분석은 첫 실행의 실제 성공 응답을 해시 검증 후 재사용했습니다. '
            '표의 최초 분석 시간·토큰·비용은 그 원래 측정치이며 추가 과금이나 새 이미지 호출은 없습니다. '
            '교정 역시 동일한 검증 코드·fixture·컨테이너 ID의 기록을 재사용했습니다. '
            '선행 호환성 확인이 모델을 예열했을 수 있으며 호출별 실제 load 시간은 공개합니다.', '']
    (out / 'EVALUATION.md').write_text('\n'.join(report))
    (out / 'evaluation.json').write_text(json.dumps({'arms': details, 'comparison': comparison,
        'calibrationStatus': calibration['status']}, ensure_ascii=False, indent=2) + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=OUT)
    main(parser.parse_args().output)
