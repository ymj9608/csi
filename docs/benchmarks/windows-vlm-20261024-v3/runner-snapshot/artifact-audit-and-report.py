"""Post-run artifact checks and Korean report; no model calls."""
import hashlib
import importlib.metadata
import json
import platform
import shutil
import sys
from pathlib import Path

ROOT = Path.cwd()
sys.path.insert(0, str(ROOT))
from scripts import benchmark_windows_vlm as run
from scripts.analyze_windows_vlm import analyze
from scripts.summarize_windows_vlm import summarize

out = ROOT / 'docs/benchmarks/windows-vlm-20261024-v3'
execution = json.loads((out / 'execution.json').read_text(encoding='utf-8'))
assert execution['phase'] == 'COMPLETE', execution
protocol = run.check_frozen(out)
summary = summarize(out)
diagnostics = analyze(out)
assert summary['completedConditions'] == summary['plannedConditions'] == 16
assert summary['interruptedConditions'] == summary['runningConditions'] == 0
cases = {c['id']: c for c in run.cases()}
call_count = 0
missing_usage = 0
timeouts = 0
tests_checked = 0
for row in summary['conditions']:
    folder = out / 'pilot' / row['case'] / row['arm']
    result = json.loads((folder / 'result.json').read_text(encoding='utf-8'))
    assert result['case'] == row['case'] and result['arm'] == row['arm']
    assert result['status'] in {'PASSED', 'FAILED'}
    assert set(result['readPaths']) <= set(cases[row['case']]['sources'])
    if result['status'] == 'PASSED':
        assert result['verification']['exitCode'] == 0
        assert result['verification']['passed'] == result['verification']['total'] == 8
    for path in (folder / 'calls').glob('*.json'):
        value = json.loads(path.read_text(encoding='utf-8'))
        if path.name.endswith('-input.json'):
            images = [h for m in value['messages'] for h in m.get('imageHashes', [])]
            expected = [protocol['caseHashes'][row['case']]['image']] if (
                row['arm'] == 'image_search' and path.name.startswith('action-')) else []
            assert images == expected, path
        else:
            call_count += 1
            assert value['status'] in {'COMPLETED', 'FAILED'}, path
            missing_usage += any(value.get(k) is None for k in ['inputTokens', 'outputTokens'])
            timeouts += 'ReadTimeout' in value.get('error', '')
    for path in folder.glob('candidate-*/test_contract.py'):
        assert path.read_text(encoding='utf-8') == cases[row['case']]['tests'], path
        tests_checked += 1

snapshot = out / 'runner-snapshot'
snapshot.mkdir(exist_ok=True)
for name in [*protocol['runnerHashes'], 'scripts/analyze_windows_vlm.py',
             'scripts/summarize_windows_vlm.py', 'scripts/replay_architecture_mapping.py',
             'scripts/score_windows_perception.py']:
    target = snapshot / name
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and name in protocol['runnerHashes']:
        assert hashlib.sha256(target.read_bytes()).hexdigest() == protocol['runnerHashes'][name]
    shutil.copyfile(ROOT / name, target)
if Path(__file__).resolve() != (snapshot / 'artifact-audit-and-report.py').resolve():
    shutil.copyfile(Path(__file__), snapshot / 'artifact-audit-and-report.py')
audit = {
    'kind': 'POST_RUN_ARTIFACT_CHECKS', 'conditions': 16, 'modelCalls': call_count,
    'modelCallTimeouts': timeouts, 'callsWithoutUsage': missing_usage,
    'candidateTestFilesUnchanged': tests_checked, 'frozenCoreAndCasesMatch': True,
    'imageOnlyInImageArm': True, 'noPendingCallRecords': True,
    'python': sys.version, 'platform': platform.platform(),
    'packages': {p: importlib.metadata.version(p) for p in ['httpx', 'jsonschema', 'Pillow', 'wasmtime']},
    'snapshotSha256': {str(p.relative_to(snapshot)): hashlib.sha256(p.read_bytes()).hexdigest()
                       for p in snapshot.rglob('*.py')},
}
run.write(out / 'artifact-validation.json', audit)

arm_labels = {'full_code': '전체 코드', 'code_search': '코드 검색 허용',
              'image_search': '이미지 + 검색 허용', 'text_search': '구조 텍스트 + 검색 허용'}
case_labels = {'retry-small': '재전송 / 8파일', 'retry-expanded': '재전송 / 56파일',
               'fanout-small': '다중 전송 / 5파일', 'fanout-expanded': '다중 전송 / 53파일'}
rows = []
for case in ['retry-small', 'fanout-small', 'retry-expanded', 'fanout-expanded']:
    for arm in ['full_code', 'code_search', 'image_search', 'text_search']:
        row = next(r for r in summary['conditions'] if r['case'] == case and r['arm'] == arm)
        d = next(r for r in diagnostics['conditions'] if r['case'] == case and r['arm'] == arm)
        if row.get('testsTotal') == 8:
            test = f"{row['testsPassed']}/8"
        elif row.get('testsTotal') == 0:
            test = '테스트 로딩 오류'
        else:
            test = '최종 후보 미검증/없음'
        note = ' / 호출 시간 초과 포함' if d['failedModelCalls'] else ''
        if 'INPUT_BYTE_LIMIT' in (d['error'] or ''):
            note += ' / 텍스트 입력 상한 초과'
        rows.append(f"{case_labels[case]} | {arm_labels[arm]} | {row['status']} | "
                    f"{test} | {row['wallSeconds']:.3f}초{note}")
passed = [f"{case_labels[r['case']]} · {arm_labels[r['arm']]} ({r['wallSeconds']:.3f}초)"
          for r in summary['conditions'] if r['status'] == 'PASSED']
retrieval = [r for r in diagnostics['conditions'] if r['arm'] != 'full_code']
decided = [r for r in retrieval if r['actions']]
new_read = sum(bool(r['newlyReadPaths']) for r in decided)
searches = sum(r['actions'].get('search', 0) for r in decided)
total_seconds = sum(r['wallSeconds'] for r in summary['conditions'])
paired = sum(r['bothPassed'] for r in summary['pairedComparisons'])
report = f'''Windows 로컬 VLM 오케스트레이션 실험 결과
실행일: 2026-10-24 / 브랜치: experiment/windows-vlm-orchestration

1. 핵심 결과

계획한 16개 조건을 모두 실행했고 {summary['passedConditions']}개 조건이 전체 검증과 완료 판단을 통과했다.
성공 조건: {', '.join(passed) or '없음'}
조건별 실행 시간 합계: {total_seconds:.3f}초 ({total_seconds / 60:.1f}분).
이는 모델 설치, 실험 데이터·그림 제작, 실행기 사전 테스트 시간을 제외한 값이다.
각 조건의 모델 로딩·전환·판단·코드 생성·검증·재수정은 포함한다.

코드 검색 조건과 이미지 조건이 모두 성공한 쌍은 {paired}/4개다.
따라서 동등한 검증 품질을 유지하면서 비전이 시간을 단축했다고 판단할 근거가 없다.
실패한 조건이 일찍 종료된 시간을 속도 개선으로 계산하지 않았다.

작은 다중 전송 작업에서는 이미지 조건이 통과하고 다른 세 조건이 실패했다.
작은 규모에서도 이미지 추가가 도움이 될 가능성을 보여주는 한 번의 관찰이다.
동일 작업의 파일 수 확장 버전에서는 이미지 조건이 7/8 검증에 그쳤다.
파일 수를 늘리면 비전의 효과가 증폭된다는 가설은 이번 결과로 확인되지 않았다.
현재 모델·예산에서 우선 해결할 문제는 추가 근거 탐색과 수정 코드의 안정성이다.

2. 실제 측정값

작업 | 조건 | 전체 작업 상태 | 마지막 후보 검증 | 총 시간
{chr(10).join(rows)}

PASSED는 현재 후보가 고정된 8개 기능·보안 검증을 모두 통과하고,
오케스트레이터가 완료를 요청한 경우다. 일부 테스트 통과는 완료가 아니다.
0/8은 테스트가 실행됐으나 모두 통과하지 못한 경우이고, 로딩 오류는
테스트 모듈을 불러오지 못한 경우다. 검증 전 종료와도 구분했다.
이전 후보가 더 높은 점수를 받았더라도 최종 후보 대신 집계하지 않았다.
각 후보의 결과와 오류는 diagnostics.json 및 candidate-*/validation.json에 남아 있다.

3. 관찰한 병목

검색 허용 조건 12개 중 실제 판단을 반환한 {len(decided)}개에서
추가 원본 파일 조회가 발생한 조건은 {new_read}개, search 도구 호출은 {searches}회였다.
초기 판단 자체가 끝나지 않은 조건은 이 행동 집계에서 따로 제외했다.
이미 제공된 deployment.json을 다시 읽거나, 누출 경로를 더 확인하지 않고
가입 함수 수정을 지시하는 행동이 반복됐다. 재전송 작업의 검색 조건에서는
수정에 필요한 relay.py를 확보하지 못했다. 전체 코드 조건은 그 파일을
이미 받았지만 수정과 검증을 완성하지 못했다.

코딩 모델은 존재하지 않는 deployment 모듈/함수, 누락된 import,
내부 전화번호 삭제, 중복·누락 전송 등의 오류를 만들었다.
일부 누출 검증 통과만으로 충분하지 않아 정상 기능 보존도 함께 검사했다.
모델 호출 {call_count}회 중 시간 초과는 {timeouts}회였다.
확장된 다중 전송의 전체 코드 조건은 마지막 후보 7/8 검증 이후,
다음 판단 요청 전에 누적 텍스트 입력이 20,000바이트 상한을 넘어 종료됐다.
이 제한은 실행기의 예산이며 모델의 원래 context 한도와 구분해야 한다.
사용량이 반환되지 않은 호출은 {missing_usage}회다. 입력·출력 토큰 합은
반환된 값만 더한 하한이며, 미측정 사용량을 실제 0으로 해석하면 안 된다.
토큰 수를 정확도의 지표로 사용하지 않았다.

4. 실험 조건과 한계

Windows 10 Home, i5-7500, RAM 16GB, GTX 1060 3GB에서 직접 실행했다.
Ollama 0.40.10, Qwen3-VL 8B Instruct Q4_K_M 오케스트레이터,
Ministral 3 8B Instruct Q4_K_M 코딩 모델을 모든 조건에 동일하게 사용했다.
context 8192, temperature 0, seed 42, thread 3, 코딩 시도 최대 2회다.
요청별 텍스트 입력은 20,000바이트까지 허용하고, 출력 한도는
오케스트레이터 700토큰, 코딩 모델 1000토큰이다.
모델 호출 제한은 300초이며 루프의 1200초 예산은 턴 사이에서 확인한다.
동시에 모델 하나만 적재하고 조건 사이에 모델을 내렸다. 조건 안에서는
최대 2분 유지 정책을 공통 적용했다. OS 디스크 캐시를 강제로 비우지는 않았다.
실행 중 전체 데스크톱의 최소 가용 RAM 표본은 {diagnostics['minimumAvailableRamGiB']}GiB였다.

두 합성 작업을 각각 작은 버전과 무관한 catalog 파일 48개 추가 버전으로
구성한 것이다. 네 독립 프로젝트나 엔터프라이즈 아키텍처가 아니다.
수정 허용 목록과 import/function 인덱스도 공통 제공했다. 확장 파일은
허용 목록 밖이며 import 그래프에서 분리돼 있다. 실제 대형 저장소에서
알려지지 않은 취약 모듈을 찾아내는 난이도를 재현하지 않았다.
각 조건은 1회 실행했으므로 통계적 비열등성·일반 모델 순위는 주장하지 않는다.

이미지와 텍스트 조건은 같은 구조 사실을 제공한다. 그림은 코드 이름과
경로를 명시한 작은 합성 개요도다. 오래되거나 누락된 실제 운영 그림,
큰 구조도, 그림 생성·유지 비용은 평가하지 않았다.
알려진 원문 전화번호 누출의 수정 과제이며, 새 취약점 발견률을 측정하지 않았다.
검증은 읽기 전용·네트워크 없는 WASI Python 3.12.0 / Wasmtime 50.0.1에서
수행했다. 실제 CSI/Lichu 서비스, Docker, Java, 배포의 E2E 검증은 포함하지 않는다.
테스트 통과는 고정된 이 계약의 결과이며 전체 애플리케이션 보안 보증이 아니다.

5. 코드 변경과 별도 검증

architecture_agent/routing.py에서 표시명뿐 아니라 정확히 일치하는 컴포넌트
ID도 코드 모듈 매핑 후보로 사용하도록 수정했다. 서로 충돌하는 ID/표시명은
모호함으로 유지하고 인프라 노드를 코드 모듈로 잘못 연결하지 않도록 했다.
기존 응답을 재생한 320파일 사례에서 매핑은 0/27에서 23/27로 늘었지만,
필수 경로 확보는 10/12로 같았다. 새로운 탐지 성능 향상으로 계산하지 않았다.
이 재생은 새 모델 추론이 아니며 과거 응답을 사용한 코드 검증이다.

공통 실행기, 격리 검증기, 비교 데이터, 결과 집계 도구를 추가했다.
권한·수정 범위 일치, 이전 수정안과 실패 진단을 전달하는 재시도,
새 후보 생성 시 이전 검증 무효화, 동일 입력 조건 등을 검증했다.
관련 회귀 검증 86개는 비교 추론 전에 통과했다. 정답 대조 수정안은
네 구성 모두 8/8을 통과하고 원래 취약 코드는 실패했다.
대조 수정안의 통과를 모델 성능으로 집계하지 않았다.

V1/V2는 실행기 계약 문제를 수정하는 과정에서 중단했다. 원시 결과와
소스 스냅샷을 보존했고 V3의 성공/실패와 합치지 않았다. V3 도중에는
고정한 모델 호출·데이터·검증기 코드를 바꾸지 않았다.
호환성 검사는 원래 실행에서 가져온 기록이며 출처와 해시를 명시했다.
단순 그림의 노드 ID 대신 상자 전체 라벨을 반환한 경우의 별도 판독 진단은
사후 분석으로 구분하고 원래 엄격한 ID 점수를 그대로 보존했다.

6. 다음 개선 우선순위

먼저 VLM이 수정 지시 전에 실제 경로·함수·호출 연결의 근거를 확보하도록
만들고, 코딩 모델의 존재하지 않는 import/식별자와 기능 손상을 줄이는
일반적인 검증·재시도 방식을 보완하는 것이 우선이다. 이번 과제의 정답
파일이나 수정 코드를 하드코딩해 성공시키는 방식은 적절하지 않다.
그다음 고정 커밋의 실제 저장소, 여러 독립 과제, 정상 대조군,
그림 누락/오래됨 조건과 반복 실행으로 확대해야 한다. 파일 수뿐 아니라
서비스 경계·비동기 경로·배포 정보 의존성으로 난이도를 나누는 것이 좋다.

기록 위치
  summary.json / comparison.csv: 전체 조건, 실패 포함
  diagnostics.json: 단계별 사용량·시간·조회 행동·후보별 오류
  protocol.json: 사전 고정 조건과 입력 해시
  artifact-validation.json: 완료 후 기록·입력·테스트 파일 무결성 확인
  runner-validation.json: 사전 회귀 검증 결과
  runner-snapshot/: 실제 실행 코드와 집계 코드 보존본
  README.txt: 범위, 방법, 재현 명령
  MODEL_CONTEXT.txt: Hugging Face 공식 모델 카드와 실행 설정의 차이
'''
(out / 'RESULTS_KO.txt').write_text(report, encoding='utf-8')
print(json.dumps({'completed': 16, 'passed': summary['passedConditions'], 'modelCalls': call_count,
                  'timeouts': timeouts, 'trialWallMinutes': round(total_seconds/60, 2),
                  'report': str(out / 'RESULTS_KO.txt')}, ensure_ascii=False))
