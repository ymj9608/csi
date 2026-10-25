# qwen3-vl:8b 유지: 최종 본문 누락 원인 재검증

2026-10-23. 사용자 요청에 따라 Instruct 변형을 사용하지 않고 기존 `qwen3-vl:8b` 태그와 digest를 유지했다. 검토 중 Instruct 다운로드는 완료됐지만 추론 호출에는 사용하지 않았다. OpenAI 호출과 이미지 인식도 없다.

## 관측

| 실행 | 모델 태그 | 요청 | 입력/출력 토큰 | 최종 본문 | 시간 |
|---|---|---|---:|---:|---:|
| 첫 시도 | qwen3-vl:8b | think=false, JSON, 상한600 | 282/125 | 0자, stop | 12.48초 |
| 두 번째 | 동일 | think=false, 자연어, 상한600 | 293/600 | 0자, length | 28.30초 |
| 이번 | 동일 | think=true, 자연어, 상한1800 | 295/1800 | 0자, length | 81.87초 |

이번에는 thinkingPresent=true를 확인했다. 내부 추론 본문은 저장하지 않았다. load 3.21초, 생성78.08초이며 컨텍스트8192에 비해 입력295+출력1800이 작다. 컨텍스트 초과가 아니라 출력 예산에 도달한 것이다. 프로세스 충돌은 관측하지 않았다.

## 원인 판단

설치 메타데이터 parent_model은 `dhiltgen/qwen3-vl:8b-thinking-q4_K_M-llamacpp`, digest는 `9cf69da2b16d097f7def535917c4b55a95d6c7ee5700eb69ab86b01b3cfca487`다. 즉 일반 `:8b` 태그가 현재 Thinking 가중치를 가리킨다. 태그를 Instruct로 바꾸지 않았으며 이 사실은 모델 이름과 별개로 기록한다.

Ollama는 thinking과 final content를 분리한다. 이번 실행은 추론이 있는 상태에서 최종 응답 없이 출력 상한을 맞았다는 직접 증거다. 이전 think=false 요청이 왜 최종 본문을 생성하지 않았는지는 런타임의 renderer/parser와 모델 동작을 추가 분리해야 하므로 특정 Ollama 버그라고 단정하지 않는다. /api/show에는 thinking 제어 메타데이터가 없었다.

따라서 `think:false`로 추론을 확실히 끌 수 있다고 가정하고 600토큰으로 제한한 기존 구성은 이 설치 모델에서 검증되지 않은 가정이었다. 1800으로 늘려도 이번 과제에서 최종 답변을 얻지 못했다. 더 늘리면 성공할 수도 있지만 짧은 실행·안정성 요구를 만족한다고 입증되지 않았으므로 반복하지 않았다.

## 적용한 개선과 한계

- 모델 메타데이터/digest를 실행 로그에 보존한다.
- 최종 content 길이와 thinking 존재 여부만 기록하고 비공개 추론 내용은 저장하지 않는다.
- coding_agent/local_vlm.py에서 stop+빈 본문을 VLM_EMPTY_FINAL_CONTENT로 분류한다. 출력 길이 제한 VLM_OUTPUT_INCOMPLETE와 구분한다.
- 관련 단위 테스트6개 통과. keep_alive=0, 순차 실행, 컨텍스트8192 및 요청180초 제한 유지.
- 빈 본문/추론을 지시문으로 대신 사용하거나 사람/OpenAI 답변으로 대체하지 않는다.

이는 실패 식별·자원 관리 개선이며, 최종 지시문 생성 문제를 해결했다는 결과는 아니다. 이번 구조 조건은 선행 단계 실패로 코딩/보안 테스트 미실행이다. 이전 로컬 코드만8/10 결과를 새 실행으로 표시하지 않는다.

근거: calls/handoff-input.json, calls/handoff.json, local-protocol.json 및 이전 ../signup-events-local-v2/RESULTS.md.
공식 동작 설명: https://docs.ollama.com/capabilities/thinking (think=false는 모델이 허용하는 경우의 요청이며 thinking/content는 별도 필드).
