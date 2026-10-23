# OpenAI VLM 총괄 경로 검증

검증일: 2026-10-23. 구현은 `vlm-orchestrator-v1`, 코딩 엔진은 v4입니다. 기본 총괄 모델은 `gpt-6.1-sol`, 하위 코딩 모델은 로컬 `ministral-3:8b-instruct-2512-q4_K_M`입니다.

## 이전과 이후

| 항목 | 이전 Qwen 직접 지시 | 현재 OpenAI 총괄 |
|---|---|---|
| VLM 역할 | 지시문 한 번 생성 | 도구 결과를 보고 다음 행동 선택 |
| 코드 탐색 | 프로필에서 정한 함수·파일만 전달 | 고정 커밋의 경로 목록·검색·범위 읽기를 VLM이 선택 |
| 정책 근거 | 발췌를 처음부터 일괄 전달 | 근거 목록을 보고 검사 RAG 스냅샷의 필요한 ID 조회 |
| 생성 실패·테스트 실패 | Python이 코딩 모델을 자동으로 한 번 재호출 | 실패를 VLM에 돌려주고 추가 조회·재위임·보류 결정 |
| 완료 | 첫 검증 통과 시 READY | VLM이 현재 검증 결과를 확인하고 finish_review 요청, 서버가 재확인 |
| 기록 | 지시문과 단일 호출 시간·토큰 | 도구 순서, 위임별 지시, 조회 경로·근거, 누적 API 시간·토큰·결론 |
| 승인·수정 권한 | 서버와 관리자 통제 | 동일. VLM은 승인·병합·배포 권한 없음 |

## 실행한 검증

| 검증 | 결과 | 데이터와 방식 |
|---|---:|---|
| Python | 95 통과 | 임시 Git 저장소, 합성 소스·그림·정책, 모의 OpenAI Responses/Ollama 응답·검증기 |
| Java | 35 통과 | CodingProposals·결과 재전송·ArchitectureContexts·권한 테스트. 모델/DB 동작은 해당 테스트의 mock 사용 |
| 브라우저 | 12 통과 | 별도 localhost Vite + Chrome + 모의 API. 실제 서비스 승인·업로드 없음 |
| 프론트 빌드 | 통과 | vue-tsc 및 Vite. 기존 번들 크기 경고 있음 |
| 실제 OpenAI → Ministral → Docker | 미실행 | 외부 전송·과금에 대한 자동 승인 검토 거절. 성능/토큰 실측값 없음 |

Python 검증은 VLM이 선택한 조회·위임·검증·완료 순서를 실제 엔진에 넣고 실행합니다. 테스트 실패 이후 VLM에 실패한 검사 목록이 전달되는지, 재수정하면 이전 검증이 무효화되는지, 코드 생성 없이 보류할 수 있는지를 확인했습니다. 실제 모델의 판단 품질·수정 성공률을 측정한 테스트는 아닙니다.

추가 차단 사례: `.env`/상위 경로/심볼릭 링크 조회, 미등록 도구·가짜 근거, 소스 조회 없는 위임, 검증 전 완료, 세 번째 코딩 호출, 턴·시간·토큰 초과, 중복 call_id, 잘린 응답, 사용량 누락, API 인증/한도/timeout 오류. API 오류 원문·키·암호화 reasoning은 공개 결과에 포함하지 않습니다. 브라우저에서는 지시문 속 HTML이 실행되지 않고 텍스트로 표시되는지도 확인했습니다.

기존 Qwen 실측 `vlm-direct-smoke.json`의 123.4초·성공 결과는 이전 구현의 기록입니다. 이번 OpenAI 경로가 같은 속도나 품질을 달성했다고 주장하지 않습니다. 실제 모델 호출 전 최초 로컬 시도는 샌드박스의 Docker 접근 제한으로 `VERIFIER_UNAVAILABLE`에 그쳤고, 외부 연결을 포함한 재시도는 자동 승인 검토에서 거절됐습니다.

## 재현

CSI 루트:

```sh
.venv/bin/python -m pytest -q tests/test_vlm_orchestrator.py tests/test_coding_agent.py tests/test_coding_handoff.py tests/test_coding_worker.py
```

백엔드:

```sh
mvn -q -Dtest=CodingProposalsTest,CodingProposalsDeliveryTest,ArchitectureContextsTest,ArchitectureContextsSecurityTest test
```

이번 JDK 환경은 Mockito 자동 attach가 차단되어 설치된 `mockito-core-5.23.0.jar`를 `-DargLine=-javaagent:/absolute/path/to/mockito-core-5.23.0.jar`로 명시했습니다. 실행 환경에 맞는 실제 jar 경로를 사용해야 합니다.

프론트엔드:

```sh
npm run build
npm run dev -- --port 5184 --strictPort
# 다른 터미널, frontend 디렉터리
CSI_E2E_BASE_URL=http://127.0.0.1:5184 npx playwright test e2e/coding-flow.spec.ts e2e/architecture-coding.spec.ts
```

실제 API 점검은 소스·정책·이미지의 외부 전송과 과금을 수반합니다. 그 실행이 승인된 뒤 아래 명령을 사용합니다.

```sh
.venv/bin/python scripts/smoke_vlm_coding.py --repo ../Lichu
```

이 스크립트는 실제 Lichu의 고정 실습 커밋, 코드에서 작성한 그림, 가상 실습 정책과 `smoke-*` 탐지 ID를 사용합니다. 운영 검사/RAG 검색 호출이나 백엔드 결과 전송은 포함하지 않습니다. 새 출력은 `.runtime/vlm-orchestrator-smoke/`에 기록하며 기존 Qwen 로그를 덮어쓰지 않습니다.

## 적용 범위

설정과 코드 변경까지 완료했으며 실행 중인 서비스·Worker는 재시작하지 않았습니다. 적용 시 진행 중 작업을 마친 뒤 백엔드·프론트엔드를 재빌드하고 native Worker를 다시 실행해야 합니다. VLM의 읽기 탐색은 확장됐지만 쓰기 범위는 여전히 Lichu 실습 파일 하나입니다. 기존 해시 전환·과거 로그 삭제·운영 환경 검증·범용 다중 파일 수정은 포함하지 않습니다. 중단된 VLM 턴의 자동 재개도 구현하지 않았습니다.

공식 API 계약 참고: [Responses 도구 호출](https://developers.openai.com/api/docs/guides/function-calling), [이미지 입력](https://developers.openai.com/api/docs/guides/images-vision), [기본 모델](https://developers.openai.com/api/docs/models/gpt-6.1-sol).
