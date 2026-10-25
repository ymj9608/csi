# Apache Flink 공개 코드: CSI 보안 진단 비교
최신 **AI 생성 패치** 비교는 [OpenAI 빠른 평가](openai-quick/RESULTS.md)를 확인하세요. 아래는 기존 보안 진단 실험이며 서로 다른 품질 지표를 합산하지 않습니다.

실험일: 2026-10-23. 공개 Flink의 실제 코드에 **의도적으로 주입한 문제**를 검사했다. 발견한 합성 문제를 Apache Flink 원본의 취약점으로 해석하면 안 된다.

현재 CSI는 일부 로그 노출을 탐지하지만, 이 데이터에서 모든 보안 문제를 잡지는 못했다. 그림으로 읽을 코드를 줄이는 것과 보안 진단 품질을 유지하는 것은 별도 검증이 필요하다.

## 데이터와 검증 범위

- 저장소: [apache/flink](https://github.com/apache/flink/tree/8d01380ff5bf9892462ef9808b1b56fd9723f54d), 고정 커밋 `8d01380ff5bf9892462ef9808b1b56fd9723f54d`.
- CSI 스냅샷 조건에 해당하는 Java/Python: **15,499개, 118,585,995바이트**. 테스트도 포함한 입력 목록이며, 전 파일이 실제 분석됐다는 뜻은 아니다.
- 모델 비교: 실제 보안 관련 **8개 Java 파일**. 저장소 전체를 모델에 입력한 실험이 아니다. 단일 질문에 필요한 범위를 연구자가 먼저 정한 데이터셋이므로 일반적인 파일 검색 성능도 입증하지 않는다.
- 공식 [구조 그림](architecture.png)은 같은 커밋의 `docs/static/fig/processes.svg`를 그대로 렌더링했다. Client·JobManager·TaskManager를 보여주지만 S3·TLS·소스 경로는 명시하지 않는다.
- 실제 4개 파일을 별도 overlay로 변경했다. 양성 5개와 안전한 대조군 3개를 모델 호출 전에 고정했다. [정답](ground-truth.json), [주입 패치](synthetic-mutations.patch), [복원 패치](remediation.patch).
- 보완본은 **원본 코드로 복원한 연구자 작성 패치**다. AI가 생성한 패치 또는 Flink 빌드·실행 검증 결과가 아니다.
- 장비: Apple M5, RAM 16GiB. Semgrep 1.168.0. 로컬 Qwen3-VL 8B Q4_K_M, Ollama 0.32.1.

## 원본 → 문제 주입 → 보완

| 변경 위치 | 주입한 문제 | 보완 방식 |
| --- | --- | --- |
| DelegationTokenReceiverRepository | Base64로 바꾼 위임 토큰 전체를 로그에 기록 | 새 로그 및 변환 코드를 제거 |
| AbstractS3DelegationTokenReceiver | AWS 세션 토큰을 로그에 기록 | 새 로그를 제거 |
| AbstractS3DelegationTokenProvider | 기존 마스킹 대신 AWS secretKey 출력 | 원래 마스킹 복원 |
| SSLUtils | keystore 비밀번호 출력, REST 호스트 검증 무조건 비활성화 | 비밀번호 로그 제거, 원래 설정 조건 복원 |

보완 후 네 파일은 원본과 바이트 단위로 같다. 따라서 원래 지원하던 동작으로 되돌렸다는 검증이며, 운영 보안 전체 또는 기능 회귀 테스트 통과를 뜻하지 않는다. [검증 기록](validation.json).

**TLS 조건:** 이 커밋의 `SecurityOptions.SSL_REST_VERIFY_HOSTNAME` 기본값은 `false`다. V4의 회귀는 옵션을 `true`로 명시해도 검증이 비활성화된다는 점이다. 원본 복원은 설정을 다시 존중하게 만들 뿐 검증을 기본 활성화하지 않는다. 실제 배포에서는 명시적 설정과 잘못된 호스트 인증서 연결 실패 테스트가 필요하다. 이 설정 파일은 8파일 모델 입력에 없었다. [추가 소스 확인](tls-context-audit.json).

## 기존 CSI 정적 분석

37파일 범위는 연구자가 미리 정한 `runtime/security`·`runtime/net` 폴더이고, 39파일 범위는 여기에 변경 파일을 합친 것이다. 이 두 범위는 VLM이 선택한 결과가 아니다. 기존 규칙과 서비스 코드는 변경하지 않았다.

| 상태 / 범위 | 입력 파일 | 탐지 양성 / 5 | 대조군 오탐 / 3 | 시간 | 완료 여부 |
| --- | ---: | ---: | ---: | ---: | --- |
| 원본 / 전체 직접 요청 | 15,499 | — | — | 1.45초 | 20MB 제한으로 중단 |
| 원본 / 전체 분할 | 15,499 | — | — | 21.59초 | 파싱 오류로 중단 |
| 원본 / runtime 보안 범위 | 37 | — | — | 0.98초 | 완료, 후보 0개 |
| 원본 / runtime + 변경 파일 | 39 | — | — | 1.04초 | 완료, 후보 0개 |
| 문제 주입 / 전체 분할 | 15,499 | — | — | 19.71초 | 파싱 오류로 중단 |
| 문제 주입 / runtime 보안 범위 | 37 | 2 | 1 | 1.82초 | 완료, 후보 3개 |
| 문제 주입 / runtime + 변경 파일 | 39 | 3 | 1 | 1.09초 | 완료, 후보 4개 |
| 보완 / 전체 분할 | 15,499 | — | — | 28.70초 | 파싱 오류로 중단 |
| 보완 / runtime 보안 범위 | 37 | — | — | 3.08초 | 완료, 후보 0개 |
| 보완 / runtime + 변경 파일 | 39 | — | — | 2.14초 | 완료, 후보 0개 |

기존 규칙은 V1·V2·V5를 탐지했다. V3의 `secretKey`는 규칙의 변수명 목록에 없고, V4의 TLS 검증 해제 규칙도 없다. N3는 `password`라는 이름 때문에 값이 `[REDACTED]`인데도 탐지했다. runtime만 선택하면 S3 파일이 빠져 V2까지 놓친다. 변경 파일 합집합이 선택 누락을 일부 회복한다.

전체 분할의 오류를 숨기지 않고 끝까지 진행한 별도 [원시 진단](raw-scanner-audit.json)은 60.84초가 걸렸다. Semgrep가 보고한 분석 대상은 9,858개이며 파싱 오류는 5개다. `${package}`를 포함한 Maven archetype 템플릿에서 발생했다. 입력 파일 수와 실제 분석 대상 수가 다르므로 전체 분석 성공으로 표시하면 안 된다.

원시 규칙 후보 137개 중 분포는 `{'POL-01': 129, 'SEC-05': 8}`다. 주입 위치 밖 후보는 정답 검토를 하지 않았으므로 실제 취약점이나 오탐으로 집계하지 않았다. 양성 5개·음성 3개에 한정한 기존 CSI 정밀도는 3/4=75%, 재현율은 3/5=60%다.

**보완 후 오탐 확인:** 원본 복원은 테스트용 안전 로그까지 제거하므로 후보 0개를 오탐 개선으로 해석하면 안 된다. 후속 대조 검사에서는 문제 5개만 제거하고 안전 로그 3개를 남겼다. 39파일을 다시 검사하자 N3 마스킹 로그 오탐 1개가 그대로 남았다. 즉, 보안 문제 제거와 탐지 규칙의 오탐 개선은 다르다. [후속 측정](controls-retained-scan.json), [안전 로그를 유지한 보완 패치](remediation-controls-retained.patch). 이 후속 검사는 사전 계획한 모델 품질 점수에 합산하지 않았다.

## OpenAI와 로컬 모델 실측

완료/실패로 기록된 각 조건은 1회 관측이며, 이전 실패·중단 호출도 별도로 공개한다. 먼저 그림+8개 후보 경로로 최대 4개 파일을 선택한다. OpenAI는 8개 파일 검토와 선택된 파일 검토를 각각 독립 요청했다. 로컬은 그림 선택 실패로 선별 검토를 실행하지 않고 독립적인 8파일 코드 검토를 수행했다. 정답 라벨과 사내 규정은 입력하지 않았다. 두 모델에 같은 질문·소스·이미지를 사용하되 제공자별 추론 및 출력 옵션은 다르다. 모델 시간은 HTTP 호출·응답 처리의 벽시계 시간이며 다운로드·소스 수집·PNG 변환은 제외한다. 정적 검사 시간에는 임시 파일 준비·스캐너 실행이 포함된다. 두 방식의 시간이 동일한 작업량을 뜻하지 않는다.

**후보 일치**는 정답 파일·행에 해당하는 문제를 지적한 수다. **근거 검증**은 그중 인용문까지 해당 행의 실제 문자열과 일치한 수다. 두 수치는 구분해야 한다. 틀린 파일 경로·줄 번호나 여러 줄을 한 줄처럼 바꾼 인용문은 자동 검증을 통과시키지 않았다.

| 모델 / 단계 | 코드 파일 | 후보 일치 / 5 | 근거 검증 / 5 | 입력 토큰 | 출력 토큰 | 시간 | 추정 API 비용 |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| gpt-5.4-mini / 그림·경로 선택 | — | — | — | 1,256 | 720 | 5.14초 | $0.00418 |
| gpt-5.4-mini / 8파일 코드 검토 | 8 | 4 | 2 | 13,186 | 887 | 7.68초 | $0.01388 |
| gpt-5.4-mini / 선별 코드 검토 | 4 | 3 | 0 | 10,102 | 780 | 5.54초 | $0.01109 |
| qwen3-vl:8b / 그림·경로 선택 (실패) | — | — | — | 1,615 | 2,800 | 159.17초 | $0.00000 |
| qwen3-vl:8b / 8파일 코드 검토 (실패) | 8 | — | — | 14,577 | 6,000 | 450.49초 | $0.00000 |
| qwen3-vl:8b / 복원 코드 검토 (실패) | 8 | — | — | 14,371 | 6,000 | 436.68초 | $0.00000 |

관측된 성공 응답의 OpenAI 비용 합계는 약 **$0.02915**다. 첫 그림 분석 비용까지 포함하며 실패 응답에는 usage가 없어 청구액을 추정하지 않았다.

**openai**: 선별 후 코드 입력 토큰은 23.4% 감소. 전달한 코드 원문은 47,901 → 35,327바이트다. 그림 결과를 재사용할 때 관측된 코드 검토 시간 변화는 27.9% 단축이다. 그림 분석을 처음 수행하면 총 10.67초로, 8파일 검토의 7.68초와 비교해야 한다.
선택 경로: `SSLUtils.java`, `AbstractS3DelegationTokenProvider.java`, `AbstractS3DelegationTokenReceiver.java`, `DynamicTemporaryAWSCredentialsProvider.java`.

openai: 호출 예산으로 실행하지 않은 단계: `['remediated_code']`. 보완 후 모델 검토를 통과했다고 주장하지 않는다.

**병행 사용의 관측:** 스캐너와 OpenAI 8파일 검토의 후보를 합치면 양성 5/5개가 모두 검토 대상으로 거론된다. 그러나 원문 인용 검증까지 통과한 합집합은 3/5개다. 후보 확보 개선을 자동 검증 완료나 보안 해결률 100%로 표현해서는 안 된다. N3 오탐도 단순 합집합만으로 제거되지 않는다.

**로컬 병목:** 8파일 검토의 입력 평가 시간은 55.68초, 출력 생성 시간은 393.97초로 전체 벽시계 시간의 약 87.5%다. 입력 토큰만 줄이는 것으로 이 병목을 해결한다고 단정할 수 없다. 출력 스키마·추론 모드·예산을 별도 검증해야 한다. 출력 토큰에는 내부 추론 생성이 포함될 수 있으며, 비공개 추론 내용은 로그에 저장하지 않았다.

## 실패·비용·해석상의 한계

- 현재 서비스 설정 `gpt-6.1-sol`은 이 계정에서 `403 model_not_found`를 반환했다. [실패 응답](openai-unavailable-architecture_route-result.json)을 보존하고, 모델 목록에서 확인된 `gpt-5.4-mini`로 실험했다. 반환 스냅샷은 `gpt-5.4-mini-2026-03-17`이다. 서비스 설정은 자동 변경하지 않았다.
- OpenAI는 실패 1회 + 성공 3회로 승인된 총 4회 한도를 지켰다. 응답의 실제 usage로 비용을 추정했다. 입력 $0.75, 캐시 입력 $0.075, 출력 $4.50 / 100만 토큰 기준이며 실제 청구서·세금·환율은 별도다. [공식 가격](https://developers.openai.com/api/docs/models/gpt-5.4-mini).
- 로컬의 API 과금은 $0이며 장비·전력 비용은 측정하지 않았다. 서로 다른 토크나이저의 토큰 수가 동일한 연산량을 뜻하지 않는다. 로딩 시간은 응답 로그에 따로 남겼다.
- 로컬 첫 구조화 호출은 최종 본문이 비어 있었다. [실패 로그](local-empty-architecture_route-result.json). 중단된 호출은 품질 측정에서 제외하고, 재시도 여부와 옵션 변경을 기록한다. 후속 그림 호출은 출력 2,800토큰에서 잘렸다. 코드 검토는 그림과 독립적으로 실행하며 로컬 출력 상한을 6,000토큰으로 늘렸다. OpenAI와 출력 상한이 다르므로 동일 설정의 모델 순위로 해석하지 않는다.
- 모델 오류를 보안 탐지 0점과 혼동하지 않는다. 완료된 응답에서의 근거 검증 실패와 API/형식 실패는 별도 항목이다.
- 코드 후보 이름으로도 선택할 수 있는 데이터이므로, 감소한 토큰을 **비전만의 인과적 효과**라고 주장할 수 없다. 이미지 없이 같은 인덱스를 사용한 대조군과 다수 프로젝트 반복이 추가로 필요하다.
- 아키텍처에 없는 파일을 누락시키지 않도록 변경 파일·스캐너 앵커·호출 관계를 반드시 합쳐야 한다. 이미지로만 파일을 걸러내는 경로는 이번 결과에서도 보안 진단 완전성을 보장하지 못했다.

## 현재 CSI 서비스 적용 판정

이번 실험은 **기존 CSI 스캐너 + 별도 모델 비교 harness**다. 운영 백엔드의 전체 RAG·승인·코드 수정 파이프라인을 Flink에 연결한 종단간 성공 실험은 아니다. 실제 코딩 엔진을 Flink 커밋으로 호출하면 `PROFILE_NOT_APPLICABLE`이며, 현재 오케스트레이터의 허용 경로에서 보이는 Flink 파일은 0개다.

| 우선순위 | 확인된 문제 | 적용할 개선 |
| --- | --- | --- |
| 1 | 설정된 OpenAI 모델에 계정 접근 불가 | 배포 전 모델 접근 사전 검사, 지원 모델 명시 |
| 1 | Flink 규모에서 크기 제한 및 템플릿 파싱 실패 | 모듈별 큐·명시적 템플릿 분류·부분 분석 상태와 실제 coverage 노출 |
| 1 | 비전 선별에서 토큰 처리 경로 누락 | 변경 파일·탐지 파일 강제 포함, 의존 경로 추가 조회 |
| 1 | 비밀값 별칭 누락·마스킹 로그 오탐·TLS 규칙 없음 | 데이터 흐름 기반 규칙과 TLS 검증 규칙을 별도 holdout으로 검증 |
| 1 | 모델의 잘못된 파일/행/인용 | 정확한 근거 검증 후 재조회, 실패 후보는 승인 대상에서 제외 |
| 2 | 코딩 프로필이 Lichu Python에 고정 | Java/Flink 읽기 범위·빌드·회귀 검증 계약을 별도 구현 |

결론은 **현재 CSI가 Flink 전반을 안정적으로 자동 수정할 준비가 됐다는 것이 아니다**. 범위를 좁히면 입력은 줄일 수 있지만, 누락 방지와 근거 검증을 함께 구현해야 실용적인 개선이 된다.

## 파일과 재현

- [프로토콜](protocol.json), [전체 소스 인벤토리와 SHA-256](source-inventory.json).
- [실험 도중 조정한 조건](protocol-amendments.json), [정적 측정 당시 실행기 원본](scanner-runner.snapshot.py.txt). 모델 접근 실패·출력 한도 문제 이후의 변경을 숨기지 않고 구분했다.
- [정적 검사 JSONL](measurements.jsonl), [통합 비교 JSON](comparison.json), [모델 측정 JSONL](model-measurements.jsonl), [OpenAI 원시 결과](openai-summary.json), 로컬 결과는 `local-*-result.json`. 비교 JSON/JSONL은 원시 응답에서 만든 집계 파일이다.
- `*-input.json`: 실제 공개 입력, 질문, 스키마. 이미지 본문은 `architecture.png`이며 입력에는 해시만 저장했다.
- 소스 내려받기: `git clone --depth 1 https://github.com/apache/flink.git .runtime/flink-benchmark/upstream`. HEAD가 다르면 `git fetch --depth 1 origin 8d01380ff5bf9892462ef9808b1b56fd9723f54d` 후 `git checkout --detach FETCH_HEAD`로 고정한다.
- 새 실행 폴더 지정: `export CSI_FLINK_BENCHMARK_OUTPUT=.runtime/flink-benchmark/runs/new-run` (기존 결과를 보존한다). 모든 실험 스크립트가 이 값을 사용한다.
- 준비: `.venv/bin/python scripts/benchmark_flink.py prepare`; 그림 변환: `node scripts/render_flink_architecture.mjs`; 스캔: `.venv/bin/python scripts/benchmark_flink.py scan`.
- 추가 원시 파싱 진단: `.venv/bin/python scripts/diagnose_flink_scan.py`.
- 안전 로그를 남긴 보완 검사: `.venv/bin/python scripts/check_flink_remediation_controls.py`.
- OpenAI 새 실험: `.venv/bin/python scripts/benchmark_flink_models.py --provider openai --allow-openai-public-data`.
- 로컬 새 실험: `.venv/bin/python scripts/benchmark_flink_models.py --provider local`.
- 저장된 원본 실험 결과표 재집계(과금 없음): `env -u CSI_FLINK_BENCHMARK_OUTPUT .venv/bin/python scripts/summarize_flink_benchmark.py`.
- 평가기 검증: `.venv/bin/python -m pytest tests/test_flink_benchmark.py -q` → 5개 통과.
- Flink 코드·그림은 Apache License 2.0. [원본 라이선스](APACHE-LICENSE), [NOTICE](APACHE-NOTICE)를 함께 보존했다.
