# 통합 VLM 보안 분석 · 2026-10-25

## 실행 계약

1. 프로젝트 등록 시 필수 아키텍처 이미지를 저장한다. 등록만으로 코드 검사는 시작하지 않는다.
2. Push/CLI 검사 접수 시 커밋, 정책, 이미지 원본·SHA-256을 고정한다 (`scan_visual_reviews`, Flyway V13).
3. LangGraph 호스트가 MCP로 코드 근거·diff·사내/외부 문서 발췌를 수집한다. 별도 보안 리뷰 모델은 실행하지 않는다.
4. 동일한 로컬 VLM이 LangGraph 하위 그래프에서 구조·데이터 흐름 → 정책·취약점 → 자연어 수정 지시 순서로 분석한다. 각 단계 결과를 검증한 뒤 기존 `architecture`, `findings`, `instructions` 계약으로 합친다. 자연어 지시도 JSON 응답의 문자열 필드로 운반한다. JSON 저장과 자연어 지시는 서로 배타적이지 않다.
   사실 ID와 문서 ID의 허용 목록을 응답 schema에 각각 명시하여 ID 혼동을 막는다. 진단 설명·자연어 지시의 원래 길이와 내용 범위는 줄이지 않는다.
5. 호스트가 Finding/인용/사실 ID와 이미지·커밋을 검증한 뒤 화면용 구성 요소와 검사별 지시를 저장한다. 더 최신 이미지의 분석을 과거 검사 결과로 덮어쓰지 않는다.
6. 사용자 수정안 요청 시 프로젝트 검증 프로필과 저장된 지시를 고정한다. Coding Worker는 이미지나 보안 리뷰를 다시 추론하지 않고 코드를 생성한다.
7. 고정 기능·보안 테스트를 실행한다. 실패하면 이전 수정안과 실패 피드백을 포함해 최대 한 번 추가 생성한다. 검증 미통과 코드는 승인 가능한 패치로 제공하지 않는다.
8. 승인 결정과 원본 반영은 별도다. 기존 내부 이슈·Slack 처리 계약을 유지한다. 첨부 흐름도의 커밋·PR 자동 생성은 `PHASE 2 목표 설계`이며 이 변경의 구현 완료 범위가 아니다.

## 운영 전환

- Backend/Agent/Frontend를 갱신하고 V13 마이그레이션을 적용한다. DB 초기화는 필요 없다.
- 기존 완료 검사와 코딩 작업은 과거 경로로 조회·처리한다. 실행 중인 구형 분석 작업은 종료한 후 전환하고 새 검사로 검증한다.
- 통합 분석은 Ollama가 필요하다. `CSI_REVIEW_VLM_MODEL` 기본값은 `qwen3-vl:8b-instruct`다.
- 신규 검사에는 별도 `architecture_agent` 실행이나 코딩 이미지 재선택이 필요 없다. `local_automation --standalone-architecture`는 구형 이미지 전용 분석을 사용할 때만 지정한다.
- 이미지가 QUEUED이면 다음 코드 검사를 기다리는 상태다. 실패 후 재시도 버튼으로 새 이미지 작업 ID를 준비하고 새 검사를 접수한다.
- 입력 부족·시간 초과·잘못된 JSON/인용은 명시적으로 실패 처리한다. 규칙 기반 성공이나 임의의 패치를 대신 제공하지 않는다.

## 검증 구분

### 상세 흐름 전달 변경 (2026-10-26)

새 분석은 자연어 지시 외에 `visualReview.flowContext`를 저장한다. 버전은 `schemaVersion: 1`이며,
`flows`의 `source`, `target`, `condition`, `data`, `boundary`, `state`와 `uncertainties`를
구조 분석 단계의 검증된 결과 그대로 보존한다. 빈 흐름도 명시적으로 저장하며 없는 경로를 만들어내지 않는다.

이 필드는 검사 결과 JSON → `executionPlan.unifiedReview` → Coding Agent 입력의 `vlmFlowContext`로
전달된다. 이름으로 고른 상위 컴포넌트 후보에 따라 흐름을 잘라내지 않는다. 정상·실패·직접 호출 경로와
내부·외부·UNKNOWN 경계를 함께 검토하도록 코딩 프롬프트에 명시하고, 재생성에도 같은 값을 전달한다.
구조 데이터는 근거이며 수정 권한이나 실행 명령이 아니다. 원본 코드·기능 계약·수정 범위·격리 검증이 우선한다.

결과의 `handoff.flowContext`는 고정 실행 계획과 정확히 일치해야 READY 결과를 수락한다.
잘못된 형식은 Backend와 Worker에서 차단한다. 기존 검사에 필드가 없으면 과거 자연어 지시 경로를 유지하며,
과거 기록을 추측으로 보완하지 않는다. 상세 흐름을 사용하려면 새 검사를 실행해야 한다. JSONB 확장이므로
새 DB 마이그레이션은 없다. Backend와 Agent를 함께 갱신하고 Coding Worker도 재시작한다.

코딩 요청에서는 중복된 소스를 제거하고 `truncate=false`, `shift=false`를 지정한다. 완료 토큰 집계가
문맥 한도에 도달하면 `CODING_CONTEXT_EXHAUSTED`로 차단한다. 이는 모든 서버 버전의 무손실 처리를
보증하거나 자연어 판단의 의미적 정확도를 검증하는 장치는 아니다. 아래 2026-10-25 실험 수치는 당시
모델 태그와 전달 방식의 기록으로 그대로 보존한다.

- Python/API 회귀 테스트는 모델 응답 대역으로 호출 횟수, 입력 전달, 인용 검증, 실패 차단과 지시 재사용을 검증한다. 실제 VLM 정확도 측정이 아니다.
- `scripts/benchmark_unified_fanout.py`는 실제 로컬 VLM/Coder를 사용한다. 동일한 합성 소규모 서비스·8개 테스트에서 전체 코드, 코드+구조화 텍스트, 코드+이미지를 비교한다.
- 단일 호출 실험은 원래 통합 프롬프트/schema/검증기와 VLM 문맥 32768·출력 상한 6000을 사용했다. `--staged` 재실험은 운영과 같은 3단계 그래프·프롬프트·검증기를 사용하며 단계별 출력 한도는 별도 protocol.json에 기록한다. 응답 축약·영어 강제를 제거하고 모델 응답 시간 제한 없이 실행한다. Coder의 완전한 파일 반환·WASI 검증을 사용하는 격리 실험으로 서버·Docker·Slack 전체 E2E와 구분한다.
- 기존 16조건과 7/8·5/8·6/8·8/8 수치는 이전 실행 경로의 기록이며 새 구조의 성능으로 재사용하지 않는다.

## 입력 중복·반복 생성 재실험

`--compact-input`은 벤치마크 패킷에 중복된 task/codeContext와 JSON 공백을 제거한다. 전체 소스·설정·동작 계약·문서 발췌는 유지한다. 문맥 용량 32768은 실제 입력 토큰 수가 아니며, 실제 수치는 완료 응답의 `prompt_eval_count`로 확인한다. KV 캐시 방식은 변경하지 않는다.

`--repetition-guard`는 긴 문자열이 연속 세 번 반복되면 응답을 실패 처리하고 원문을 보존한다. 같은 입력과 프롬프트에 `repeat_penalty=1.1`, `repeat_last_n=256`을 적용해 한 번만 재시도한다. 추가 단어 수 제한이나 수동 지시 수정은 하지 않는다. 재시도도 실패하면 코드 생성에 전달하지 않는다. 옵션의 의미는 [Ollama 공식 문서](https://docs.ollama.com/modelfile#valid-parameters-and-values)를 참고한다. 이는 기존 단일 호출 실험의 동작이다. 신규 운영 및 `--staged` 경로는 아래의 Qwen 권장 샘플링 설정과 같은 반복 검출기를 사용한다.

```powershell
.venv\Scripts\python.exe -X utf8 scripts/benchmark_unified_fanout.py --no-time-limit --compact-input --repetition-guard --arms structured_text code_image full_code --out docs/benchmarks/unified-vlm-fanout-20261025-compact
```

출력 폴더는 새 경로여야 한다. 기존 결과를 덮어쓰지 않는다. 기존의 16조건 실행기는 별도 보안 리뷰 Agent를 포함한 서비스 E2E가 아니라, VLM이 조회·수정·검증·재지시를 선택하던 독립 실험이었다. 신규 실험은 지시를 재사용하므로 실패 뒤 VLM 재판단 여부도 다르다. 따라서 결과 차이를 보안 리뷰 Agent 제거 하나의 효과로 해석하지 않는다.

## Repetition Loop 개선 · 단계별 통합 분석

외부 구조는 **통합 VLM → 자연어 지시 → Coding Agent**로 유지한다. `visual_analysis` 노드 내부에 같은 모델을 쓰는 3개 노드를 배치하고 기존 PostgreSQL 체크포인터를 상속한다. 별도 Agent·모델·테이블·프론트엔드 JSON 계약을 추가하지 않는다.

| 단계 | 입력 | 검증된 출력 |
|---|---|---|
| `visual_architecture` | 제공된 코드·diff·이미지 또는 구조화 텍스트·기능 계약 | 기존 화면용 architecture + 내부 데이터 흐름·불확실성 |
| `visual_security` | 구조 결과·실제 코드·정적 사실·정책·RAG 발췌 | 기존 finding별 위험·반대 근거·수정 방향, 사실/인용 ID |
| `visual_instruction` | 구조·보안 결론·대상 코드·수정 범위·기능 계약·인용 ID | 기존 `instructions[].text`의 자연어 지시 |

이미지는 1단계에만 제공하며, 2단계에는 실제 코드와 정책을 남겨 구조 추론을 재검토한다. 3단계는 전체 문서 발췌 대신 검증된 보안 결론과 인용 ID를 받는다. 중복 코드·계약 필드만 제거하며 소스와 정책을 임의로 잘라내지 않는다. 입력 한도 초과는 명시적 실패다. 자연어 지시를 JSON 객체나 수동 작성한 정답 지시로 대체하지 않는다.

- 정상 호출은 3회. 호스트는 전체 1800초 안에서 실패 시 한 번 재개하며 성공한 단계는 체크포인트에서 재사용한다. 단계별 응답 제한은 기본 600초다.
- `num_ctx=32768`, `temperature=0.7`, `top_p=0.8`, `top_k=20`, `repeat_penalty=1.0`, `presence_penalty=1.5`, `repeat_last_n=256`. 출력은 구조 2000, 보안·지시 단계는 각각 `min(6000, max(2000, Finding 수 × 1800))` 토큰이다. 기존 설명 필드·지시 길이 한도는 그대로다.
- 스트리밍 중 100~512자 구절의 연속 3회 반복을 감지하면 연결을 닫고 실패 처리한다. 이는 정확히 반복되는 구절에 대한 방어이며 의미가 비슷한 반복까지 모두 탐지하지는 않는다.
- 종료 신호 누락·출력 한도 도달·잘못된 JSON·빈 문장·존재하지 않는 인용/사실·Finding 누락은 다음 단계로 넘기지 않는다. 최종 결과는 기존 검증기를 한 번 더 통과해야 저장한다.
- 기존 `usage`는 성공한 3단계의 토큰/모델 시간을 합산한다. `analysis.orchestration.trace`는 성공한 단계별 시간·사용량을 남긴다. 중단 스트림의 토큰 수는 완료 메트릭이 없어 추정하지 않는다. 벤치마크는 실패 호출을 포함한 모든 호출 시간·원문을 별도로 보존한다.
- 실제 반복 증거: `unified-vlm-fanout-20261025-quality-v2/code_image/assessment-partial.txt`. 중복 입력 정리만으로 실패한 기록과 동일 입력 반복 억제 재시도 완료 기록은 `unified-vlm-fanout-20261025-compact/code_image/`에 보존했다. 단일 호출 compact 실행은 단계 분리 요청으로 중단했으며 완료 실험으로 취급하지 않는다.

세 입력 조건·모델·합성 데이터·8개 테스트·최대 두 수정안·최다 통과 후보/최종 후보의 구분은 그대로다. 새 프롬프트와 생성 파라미터가 함께 바뀌므로 결과가 좋아져도 LangGraph만의 인과 효과라고 해석하지 않는다. 실제 생성 품질과 호출 시간이 개선되었는지는 별도 실측으로 판단한다.

```powershell
.venv\Scripts\python.exe -X utf8 -m pytest tests/test_visual_stages.py tests/test_unified_visual_review.py tests/test_unified_fanout_benchmark.py tests/test_project_verification.py -q
.venv\Scripts\python.exe -X utf8 scripts/benchmark_unified_fanout.py --staged --no-time-limit --arms full_code structured_text code_image --out docs/benchmarks/unified-vlm-fanout-staged-run1
```

벤치마크의 `--no-time-limit`은 모델 응답 시간 제한만 해제하며 반복 감지·출력 한도·유한 재시도·격리 검증은 유지한다. 운영 timeout 설정은 바꾸지 않는다. 참고: [LangGraph 하위 그래프](https://docs.langchain.com/oss/python/langgraph/use-subgraphs), [Ollama 생성 파라미터](https://docs.ollama.com/modelfile#valid-parameters-and-values).

## 구현 회귀 검증 기록

2026-10-25 로컬 Windows에서 실행했다. Python 전체(스캐너 별도 마커 제외) **503 통과·3 건너뜀·2 제외**, Backend 단위 **80 통과**, 독립 PostgreSQL 스키마 연동 **4 통과**, 프론트엔드 빌드 성공, Playwright **29 통과**다. 단계별/저장 지시/Coding Worker/ACL 관련 집중 검사는 **112 통과·2 건너뜀**이다. 모델 응답 대역을 이용한 기능 테스트와 실제 모델 품질 평가를 구분한다.

처음 전체 실행의 Windows ACL 확인 6개 오류는 `icacls`의 시스템 코드 페이지 출력을 UTF-8로 읽던 테스트 코드에서 발생했다. ASCII 권한 표식을 원시 바이트로 확인하도록 고쳤으며 권한 조건을 완화하지 않았다. 이후 전체 실행이 통과했다. Docker 선택 통합 테스트와 스캐너 전용 검사는 이번 회귀 실행 범위에 포함하지 않았다.

기록: `.runtime/staged-python-full.xml`, `.runtime/staged-targeted.xml`, `.runtime/unified-backend-final.log`, `.runtime/unified-postgres.log`, `.runtime/unified-frontend-build.log`, `.runtime/unified-browser.log`. 로컬 실행 로그는 배포 코드나 실제 모델 정확도 증거로 대신하지 않는다.

### 실제 모델로 확인한 추가 원인 후보

단계 분리만 적용하고 `temperature=0`을 유지한 예비 실행에서도 3단계 자연어 지시 생성 중 반복이 재현되었다. 구조 분석 225.641초, 보안 판단 149.503초 뒤 지시 생성은 204.418초에 반복 검출로 중단했다. 잘못된 지시는 Coder에 전달하지 않았다. 즉, LangGraph 분리만으로 반복을 제거했다는 주장은 성립하지 않는다.

Qwen의 [Instruct 생성 권장값](https://huggingface.co/Qwen/Qwen3-VL-8B-Instruct#generation-hyperparameters)은 greedy=false, temperature=0.7, top_p=0.8, top_k=20, repetition_penalty=1.0, presence_penalty=1.5다. 새 `integrated-vlm-stages-v2`는 이 샘플링 값을 채택하되 기존 문맥 용량·단계 출력 상한·검증 계약을 유지한다. Ollama v0.40.10 API는 `presence_penalty`를 지원한다. 요청에 `truncate=false`, `shift=false`도 명시해 서버의 조용한 문맥 축소를 막는다. 원래의 temperature=0과 기본 반복 억제 값은 원인 후보이며, Q4 양자화·프롬프트·샘플링을 분리한 인과 실험은 아직 아니다.

단계 결과의 검증은 형식·ID·인용·빈 출력·반복 검증이다. 자연어 진단의 의미가 정확하다는 보증은 아니다. 예비 실행에서는 정상 경로를 누락하는 수정 설명도 관찰했으며, 후속 코드의 실제 기능·보안 테스트가 여전히 필요하다. Coder 설정과 평가 테스트는 변경하지 않았다.

샘플링 조정 후 단계·API·3입력 실험·Coding Agent 계약 검사를 다시 실행하여 **61 통과·1 건너뜀**을 확인했다 (`.runtime/staged-v2-targeted.xml`). 전체 회귀 503건은 이 샘플링 값 변경 전 실행이며 Backend/프론트엔드와 Coding Agent 로직은 이후 변경하지 않았다.

### 출력 형식의 프롬프트 명시

샘플링만 조정한 v2 예비 실행에서도 수정 지시 단계의 반복이 387.794초에 감지되었다. 이를 성공으로 간주하지 않고 해당 원문과 중단 기록을 보존했다. 출력에서 `red`에 규칙 ID만 들어가고 구성 요소 설명이 길이 상한에서 잘리는 현상도 관찰했다. 응답 schema를 `format`에만 넘기면 문법 제약은 적용되지만 필드의 의미를 모델에 충분히 설명하는 것과 같지는 않다.

`integrated-vlm-stages-v3`는 실제 요청 프롬프트에 해당 단계의 `responseSchema`를 함께 넣고, red/blue/remediation의 의미 및 JSON을 완결하고 종료할 조건을 명시한다. 길이 한도는 채워야 할 목표가 아니라 상한임을 설명한다. 다른 단계의 미사용 schema 정의와 중복 기능 계약은 제거한다. 기존 JSON 필드·허용 길이·사실 및 인용 검증은 유지한다. [Ollama 구조화 출력 가이드](https://docs.ollama.com/capabilities/structured-outputs)도 schema를 프롬프트에 함께 제공하도록 권장한다.

스키마 명시 전후의 동일 실패 입력 재생 실험은 `docs/benchmarks/unified-vlm-schema-grounding-20261025/`에 분리해 기록한다. 모델·생성 파라미터·코드 및 보안 판단 입력은 동일하게 유지하고 프롬프트의 출력 형식 설명만 보완하는 진단용 실행이며, 이를 3조건의 최종 성능 평가로 취급하지 않는다. 최신 단계·전달 계약 검사는 **62 통과·1 건너뜀**이다 (`.runtime/staged-v3-targeted.xml`).

동일 실패 입력 재생 결과: 기존 v2 지시 생성은 **387.794초에 반복 감지로 실패**, 출력 형식·필드 의미·종료 조건을 프롬프트에 명시한 재생은 **114.980초에 정상 종료**했다 (입력 1,681 / 출력 229토큰). 코드·구조/보안 판단 데이터와 생성 파라미터는 동일하게 유지했다. 이는 출력 형식 안내가 도움이 된 1회 관찰이며, schema 명시와 문장 안내를 따로 분리한 인과 실험이나 일반적인 정확도 보증은 아니다. 실제 수정 정확도는 별도의 3조건·8테스트 실행으로 평가한다.

문제가 발생했던 원본 스트림에도 검출기를 사후 재생했다. 최종 보관 원문에는 227자 구절이 35회 누적되어 있었으며, 운영과 같은 128바이트 검사 간격으로 **3회 연속 반복이 나타난 2,031자 지점**에서 감지했다. 이는 당시 모델 실행을 다시 수행한 결과가 아니라, 저장된 청크에 새 검출기를 적용한 회귀 확인이다. [재생 기록](benchmarks/repetition-guard-replay-20261025.json)에 원본 해시·감지 위치를 남겼다.

### 최종 3조건 실측

`integrated-vlm-stages-v3`를 고정해 세 조건을 새로 실행했다. **9개 VLM 단계 모두 종료 사유 `stop`으로 완료했고 반복 감지·재시도·출력 상한 도달은 없었다.** 실제 입력은 단계당 1,331~2,802토큰, 출력은 187~828토큰으로 기록됐다. 출력 상한은 모두 2,000토큰이다.

최고 후보는 전체 코드 **5/8**, 구조화 텍스트 **6/8**, 이미지 **6/8**이며 세 조건 모두 승인 기준 8/8 미달이다. 전체 코드와 구조화 텍스트의 최종 후보는 테스트 로딩 오류였다. 따라서 반복 안정성은 이번 실행에서 확인했지만 수정 정확도가 충분히 개선됐다고 결론 내리지 않는다. VLM의 정상 경로 누락·잘못된 대상 지시와 Coder의 존재하지 않는 모듈 import가 함께 관찰됐다. 이미지 고유의 성능 우위도 확인하지 못했다.

[최종 결과·지시문·정량 수치·수동 검토](benchmarks/unified-vlm-fanout-20261025-staged-v3/RESULTS_KO.md), [원래 평가 계약과의 동일성](benchmarks/unified-vlm-fanout-20261025-staged-v3/contract-preservation.json)을 참고한다. 모델 대역 회귀 테스트, 실제 모델의 형식적 완료, 실제 코드 테스트 통과를 서로 다른 지표로 관리한다.

최종 프롬프트를 포함한 전체 Python 회귀를 다시 실행해 **504 통과·3 건너뜀·2 제외**를 확인했다 (`.runtime/staged-v3-full.xml`, 89.91초). 위의 503건은 이전 중간 실행이며 최신 수치는 504건이다. Backend 80건·PostgreSQL 4건·Playwright 29건과 빌드 검증 이후 해당 코드에는 변경이 없다. [최종 기능 검증 기록](testing/unified-vlm-staged-validation.json)에 범위와 소스 해시를 남겼다.

### 이번 반복 개선의 주요 변경 파일

기존 로컬 통합 VLM 변경을 보존한 상태에서 추가한 범위다. 작업 트리 전체에는 이전 미푸시 통합 구현도 포함된다.

| 파일 | 변경 |
|---|---|
| `agent/csi_agent/visual_stages.py` | 3단계 하위 그래프, 필요한 문맥·schema 안내, 스트리밍·반복·종료·단계 결과 검증 |
| `agent/csi_agent/visual_review.py` | 기존 JSON·자연어 계약을 유지하는 호환 호출 경로 |
| `agent/csi_agent/graph.py` | 기존 `visual_analysis`에 하위 그래프 연결, 부모 체크포인터 재사용 |
| `agent/csi_agent/app.py` | 재시도까지 공유하는 전체 1800초 실행 예산 |
| `backend/.../KafkaPipeline.java`, `frontend/src/components/labels.ts` | 세 단계 진행 로그 허용·표시 |
| `.env.example`, `compose.yml` | 명시적 Instruct 모델 태그와 단계 응답 제한 기본값 |
| `scripts/benchmark_unified_fanout.py`, `scripts/summarize_unified_fanout.py` | 같은 운영 그래프를 이용하는 3조건 실행·단계 기록. 기존 Coder·8항목 점수 유지 |
| `tests/test_visual_stages.py`, `tests/test_unified_visual_review.py`, `tests/test_unified_fanout_benchmark.py` | 단계·체크포인트·자연어 전달·JSON·평가 계약 회귀 |
| `tests/test_coding_worker.py` | Windows ACL 출력 인코딩에 의존하지 않도록 테스트만 수정 |
| `README.md`, 이 문서, `docs/testing/unified-vlm-staged-validation.json` | 실제 관찰·한계·기능 회귀와 모델 품질을 구분해 기록 |

이 반복 개선에서 Coding Agent의 수정·테스트 로직, 평가 데이터 및 테스트 파일은 변경하지 않았다. 저장된 자연어 지시 재사용과 V13 저장소 등은 이전 통합 구현에 속한다. 사용자 `.env`, Lichu 소스, 개인 회고 파일은 이번 작업에서 수정하지 않았다.
