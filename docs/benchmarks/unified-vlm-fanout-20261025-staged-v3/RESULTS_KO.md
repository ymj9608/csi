# 통합 VLM · 동시 전송 소규모 실험

동일한 가상 서비스(Python 4개 + 설정 JSON 1개)에 8개 고정 테스트를 적용했습니다. 코드 검색 조건은 제외했습니다.
별도 보안 리뷰 모델 없이 VLM 판단 → 저장된 자연어 지시 → Coding Agent 최대 2회 → WASI 검증 흐름입니다. 동일한 VLM의 구조·보안·지시 3단계를 실행하며 실패한 단계부터 한 번 재개합니다.
조건별 1회 실행이며, 아래 표는 최대 두 수정안 중 가장 많이 통과한 실제 검증 후보입니다. 실험의 통과 기준은 8/8이며 운영 제공 승인을 의미하지 않습니다.

| 검증 항목 | 전체 코드 | 코드 + 구조화 텍스트 | 코드 + 이미지 |
|---|---|---|---|
| 내부 SMS | 통과 | 통과 | 통과 |
| 정상 경로 유출 차단 | 실패 | 실패 | 실패 |
| 실패 경로 유출 차단 | 실패 | 통과 | 통과 |
| 회원 정보 보존 | 통과 | 통과 | 통과 |
| 복구 기록 보존 | 통과 | 통과 | 통과 |
| 정상 전송 유지 | 통과 | 통과 | 통과 |
| 장애 진단 유지 | 통과 | 통과 | 통과 |
| 직접 호출·원본 보존 | 실패 | 실패 | 실패 |
| **통과 수** | 5/8 | 6/8 | 6/8 |

| 입력 조건 | VLM 판단(초) | 코드 생성(초) | 검증(초) | 전체(초) | 생성 횟수 | 실험 기준 충족 |
|---|---:|---:|---:|---:|---:|---|
| 전체 코드 | 643.4 | 218.7 | 11.1 | 873.4 | 2 | 미충족 |
| 코드 + 구조화 텍스트 | 571.8 | 228.3 | 8.7 | 809.0 | 2 | 미충족 |
| 코드 + 이미지 | 898.3 | 230.1 | 8.7 | 1137.3 | 2 | 미충족 |

## 조건과 해석

- VLM: `qwen3-vl:8b-instruct-q4_K_M`, Coding Agent: `ministral-3:8b-instruct-2512-q4_K_M`.
- 모델 응답 시간: 제한 없음. VLM 문맥 32768 토큰, seed 42, temperature 0.7.
- 모든 조건에 동일한 전체 코드·설정·정책 발췌를 제공했습니다. 추가 구조 JSON/이미지만 다릅니다.
- 수정 전 취약 원본 5/8, 정답 대조군 8/8. 모델에는 정답 코드와 테스트 소스를 제공하지 않았습니다.
- RAG는 고정된 저장소 문서 발췌입니다. 실시간 검색 품질이나 법적 준수 여부를 평가하지 않습니다.
- 기존 16조건 결과와 실행 프롬프트·코드 제공 방식·예산이 달라 직접적인 개선 전후 수치 비교가 불가능합니다.
- 동일 사례 1회 결과로 Vision 일반 성능이나 통계적 우위를 주장할 수 없습니다.

단계 분리: 운영과 동일한 LangGraph·프롬프트·검증기를 사용합니다. 이미지/구조 입력은 1단계, 정책·RAG는 2단계, 자연어 지시는 3단계에서 처리합니다. 단계별 출력 한도와 반복 억제 옵션은 protocol.json에 기록했습니다. 새 구조·프롬프트·파라미터를 함께 적용했으므로 단일 변경의 인과 효과로 해석하지 않습니다.

## VLM 지시 및 실패 기록

### 전체 코드

[VLM 실제 출력 기록](full_code/vlm-stage-calls.json) · [실행 결과](full_code/result.json)

- VLM visual_architecture-1: COMPLETED · 283.0초
  [단계/재시도 출력](full_code/visual_architecture-1-partial.txt)
- VLM visual_security-1: COMPLETED · 238.2초
  [단계/재시도 출력](full_code/visual_security-1-partial.txt)
- VLM visual_instruction-1: COMPLETED · 122.1초
  [단계/재시도 출력](full_code/visual_instruction-1-partial.txt)
dispatcher.py 파일의 publish_event 함수에서 fail=True일 때 r3 채널로 전송되는 로직을 제거하고, 이벤트의 phone 필드를 '<redacted>'로 익명화한 후 전송하도록 수정하세요. 기존 성공 경로 및 ARCHIVE 저장 기능은 그대로 유지하며, deployment.json의 수신자 경계와 무관하게 변경된 로직이 외부 수신자에게 raw phone을 노출하지 않도록 해야 합니다.
- 1차: 5/8 통과
- 2차: 검증 완료 안 됨 (로딩·실행 오류; 0/8로 집계하지 않음): ModuleNotFoundError: No module named 'deployment'

### 코드 + 구조화 텍스트

[VLM 실제 출력 기록](structured_text/vlm-stage-calls.json) · [실행 결과](structured_text/result.json)

- VLM visual_architecture-1: COMPLETED · 180.9초
  [단계/재시도 출력](structured_text/visual_architecture-1-partial.txt)
- VLM visual_security-1: COMPLETED · 276.4초
  [단계/재시도 출력](structured_text/visual_security-1-partial.txt)
- VLM visual_instruction-1: COMPLETED · 114.5초
  [단계/재시도 출력](structured_text/visual_instruction-1-partial.txt)
외부 수신자(r2, r3)로 전송되는 이벤트 내 전화번호 필드를 해시값으로 변환하여 보안 침해 위험을 줄이되, 내부 저장소(MEMBERS, ARCHIVE)는 원본 값을 유지하도록 하세요. dispatcher.py의 publish_event 함수에서 fail=True일 때만 해시된 전화번호를 사용하고, 그 외에는 원본 전화번호를 그대로 전달하도록 조건부 로직을 추가하세요.
- 1차: 6/8 통과
- 2차: 검증 완료 안 됨 (로딩·실행 오류; 0/8로 집계하지 않음): ModuleNotFoundError: No module named 'deployment'

### 코드 + 이미지

[VLM 실제 출력 기록](code_image/vlm-stage-calls.json) · [실행 결과](code_image/result.json)

- VLM visual_architecture-1: COMPLETED · 407.5초
  [단계/재시도 출력](code_image/visual_architecture-1-partial.txt)
- VLM visual_security-1: COMPLETED · 326.1초
  [단계/재시도 출력](code_image/visual_security-1-partial.txt)
- VLM visual_instruction-1: COMPLETED · 164.7초
  [단계/재시도 출력](code_image/visual_instruction-1-partial.txt)
broker.py에서 publish 함수는 deepcopy를 사용해 이벤트를 복제하여 MESSAGES 리스트에 저장하므로, 원본 raw phone은 변경되지 않으며 외부로 노출되지 않습니다. 그러나 실패 경로(r3: EXTERNAL Support)에서는 전송이 명시적으로 이루어지지 않으며, deployment.json의 boundary 설정과 실제 통신 방식이 일치하는지 확인 불가합니다. 따라서, broker.py에 복제된 이벤트의 phone 필드를 암호화된 문자열로 변환하는 로직을 추가하여 external recipient에서 raw phone을 처리하지 못하도록 하세요. 예: 이벤트 내 phone 필드를 AES-256으로 암호화한 값으로 교체하고, decrypt 로직은 전송 대상이 아닌 internal 경로에만 포함되도록 하세요. 코드 수정 시, fail 파라미터가 true일 경우만 암호화를 적용하고, public interface는 변경 없이 유지하세요.
- 1차: 검증 완료 안 됨 (로딩·실행 오류; 0/8로 집계하지 않음): ModuleNotFoundError: No module named 'cryptography'
- 2차: 6/8 통과


## 단계별 실제 생성 기록

| 입력 조건 | 단계 | 결과 | 시간(초) | 입력 토큰 | 출력 토큰 | 출력 상한 |
|---|---|---|---:|---:|---:|---:|
| 전체 코드 | 구조 분석 | COMPLETED | 283.0 | 1331 | 757 | 2000 |
| 전체 코드 | 보안 판단 | COMPLETED | 238.2 | 2788 | 410 | 2000 |
| 전체 코드 | 자연어 지시 | COMPLETED | 122.1 | 2102 | 187 | 2000 |
| 코드 + 구조화 텍스트 | 구조 분석 | COMPLETED | 180.9 | 1487 | 462 | 2000 |
| 코드 + 구조화 텍스트 | 보안 판단 | COMPLETED | 276.4 | 2517 | 525 | 2000 |
| 코드 + 구조화 텍스트 | 자연어 지시 | COMPLETED | 114.5 | 1946 | 190 | 2000 |
| 코드 + 이미지 | 구조 분석 | COMPLETED | 407.5 | 2397 | 828 | 2000 |
| 코드 + 이미지 | 보안 판단 | COMPLETED | 326.1 | 2802 | 600 | 2000 |
| 코드 + 이미지 | 자연어 지시 | COMPLETED | 164.7 | 2306 | 294 | 2000 |

완료된 응답의 실제 토큰 수이며, 문맥 용량 32,768을 입력 토큰 수로 집계하지 않았습니다. 시간에는 로컬 모델 로딩과 추론이 포함됩니다.

[계약 보존 확인](contract-preservation.json): 이전 실행과 소스·테스트·이미지·문서 해시, 모델명, Coder 설정, 최대 2회 생성 및 최고/최종 후보 평가 기준이 같습니다.

단계 분리·샘플링·프롬프트 안내를 함께 변경한 조건별 1회 실행입니다. 반복이 관찰되지 않더라도 재발 확률이 0이라는 의미는 아니며, LangGraph 하나의 효과로 분리할 수 없습니다.

## 지시와 후보 코드의 수동 검토

이 검토는 고정 8개 테스트의 점수를 변경하지 않습니다. 자연어 내용의 정확성과 테스트 범위 밖 한계를 별도로 확인했습니다.

| 입력 조건 | 실제 지시의 문제 | 후보에서 확인한 결과 |
|---|---|---|
| 전체 코드 | 실패 시 r3 전송을 제거하라는 지시는 장애 진단 보존 계약과 충돌하며, 정상 r2 경로를 구체적으로 다루지 않음 | 1차는 r3만 마스킹하여 r2의 정상·실패 유출과 직접 호출에 실패(5/8). 2차는 존재하지 않는 `deployment.load_deployment`를 import하여 테스트 로딩 실패 |
| 구조화 텍스트 | 외부 r2/r3를 식별했지만 `fail=True`일 때만 해시하도록 지시하여 정상 경로를 누락 | 1차는 지시대로 실패 경로에서만 SHA-256을 적용(6/8). 2차는 존재하지 않는 `deployment.get_recipient_boundary`를 import하여 테스트 로딩 실패 |
| 이미지 | deepcopy면 외부에 노출되지 않는다고 잘못 해석. 수정 허용 범위 밖 `broker.py`를 대상으로 제시하고, 암호화도 실패 경로에만 한정 | 실제 수정 파일은 허용된 `dispatcher.py`. 1차는 표준 라이브러리 조건을 어긴 `cryptography` import로 로딩 실패. 2차는 실패 경로에만 HMAC 기반 변환을 적용하여 정상·직접 호출 유출에 실패(6/8) |

이미지와 구조화 텍스트의 6/8은 모두 실패 경로 유출 차단이 추가로 통과한 결과이며, 정상 경로·직접 호출은 해결하지 못했습니다. 이번에는 이미지가 구조화 텍스트보다 높은 점수를 얻지 않았습니다. 실패에는 VLM의 불완전한 지시와 Coder의 코드·의존성 오류가 함께 관여했습니다.

추가 한계: 인용 ID가 실제 문서에 존재하더라도 인용 내용의 해석이 정확하다는 보증은 아닙니다. 전체 코드 조건은 조항 의미를 혼동하고 위법 여부를 단정한 문장을 생성했습니다. 또한 생성 코드의 SHA-256/HMAC 변환을 안전한 익명화나 암호화로 승인하지 않습니다. 이 평가의 개인정보 항목은 원문 전화번호가 외부 결과에 남는지만 검사하며, 재식별 가능성·키 관리·법률 준수는 평가하지 않습니다.
