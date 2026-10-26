# 아키텍처 이미지 분석 API 연동 계약

## 신규 검사 통합 분석 (2026-10-25)

새 검사는 별도 이미지 Worker 대신 LangGraph의 통합 VLM 분석을 사용합니다. 검사 접수 시 `scan_visual_reviews`에 이미지 원본·해시를 고정하고, 내부 Bearer API `GET /internal/scans/{id}/visual-input`으로 전달합니다. 커밋·이미지·사실/문서 인용을 검증한 결과만 저장합니다. 화면은 기존 `architecture_diagrams`의 구성 요소 JSON을 계속 사용합니다.

이미지 등록만으로 코드 검사는 시작하지 않습니다. `QUEUED` 상태에서 다음 Push/CLI 검사를 기다립니다. 실패 시 재시도 버튼으로 새 이미지 작업을 준비한 뒤 새 검사를 실행하세요. 최신 이미지나 더 최신 검사 결과를 과거 응답으로 덮어쓰지 않습니다. 아래 독립 Worker의 claim/progress/result API는 구형 호환 경로입니다. [통합 처리 계약](UNIFIED_VLM_REVIEW.md)을 참고하세요.

## 프로젝트 등록 시 필수 아키텍처 첨부

새 프로젝트는 `POST /api/projects`에 `multipart/form-data`로 `repository`,
`defaultBranch`, `architecture`를 함께 전달해야 합니다. 이미지 없는 기존 JSON
등록 요청은 HTTP 400으로 거절합니다. `architecture`는 실제 디코딩 가능한
PNG/JPEG이며 최대 5 MiB, 16 MP, 각 변 8192 px입니다.

프로젝트·정책·`architecture_diagrams`의 QUEUED 작업을 한 트랜잭션으로 저장합니다.
응답은 `{id, diagramId, architectureStatus: "QUEUED"}`이며, 저장 실패 시 등록 전체를
롤백합니다. 실제 모델 분석 완료를 의미하지 않으며 Worker와 Ollama가 필요합니다.
현재 자동 Worker 실행은 운영자가 설정한 저장소를 대상으로 합니다.

등록 화면은 첫 첨부를 분석 대상으로 사용합니다. PDF는 첫 페이지를 PNG로,
WebP/GIF는 첫 프레임을 PNG로 변환하고 서버 이미지 제한을 적용합니다.
원본 파일들은 브라우저의 프로젝트 폴더에 별도 보관합니다. 브라우저 저장 실패는
이미 완료된 서버 등록을 취소하지 않습니다. 기존 프로젝트에는 소급 강제하지 않습니다.
로컬 스캔 CLI도 콘솔에서 아키텍처를 첨부해 등록한 프로젝트를 사용합니다.

이 분석 등록은 코딩용 이미지 버전 선택과 별도입니다. 아래 버전형 API와
`select-for-coding` 경로는 그대로 유지합니다.

## 업로드 이미지 분석의 실패·재시도

프로젝트 화면의 `architecture_diagrams` 큐와 아래 버전형 `project_architectures` 큐는 별도입니다.

- `GET /api/projects/{projectId}/architecture`는 `id`, `status`, `components`, `summary`, `confirmed`, `errorCode`를 반환합니다. 상태는 `QUEUED → LOADING_MODEL → ANALYZING → EXTRACTED` 또는 `FAILED`입니다.
- Worker는 추론·조회·저장 오류를 `POST /internal/architecture/{diagramId}/failure`의 `{ "errorCode": "MODEL_TIMEOUT" }` 형식으로 보고합니다. 허용 코드는 `MODEL_TIMEOUT`, `MODEL_UNAVAILABLE`, `INVALID_RESULT`, `BACKEND_UNAVAILABLE`, `WORKER_ERROR`이며 원시 예외·모델 응답은 저장하지 않습니다. 통신 오류/5xx는 최대 3회 전송하고, 4xx는 반복하지 않습니다.
- Backend는 30초마다, 그리고 상태 조회 시 장기 진행 작업을 `FAILED / WORKER_TIMEOUT`으로 전환합니다. `CSI_ARCHITECTURE_JOB_TIMEOUT_SECONDS` 기본값은 2100초(60~7200초 범위)이며, 정상 모델 요청 제한과 전송 시간을 감안해 설정합니다. 대기 중인 `QUEUED`는 만료하지 않습니다.
- `POST /api/projects/{projectId}/architecture/retry` 입력은 `{ "diagramId": "현재 실패한 작업 UUID" }`입니다. Reviewer 세션·CSRF 인증을 사용하며 현재 실패한 작업만 재시도합니다. 저장된 이미지에 새 작업 ID를 부여하고 `QUEUED`로 돌립니다. 응답은 `{ "id": "새 UUID", "status": "QUEUED" }`입니다.
- 완료·실패·교체된 작업에 도착한 늦은 결과는 거절합니다. 실패 보고도 완료된 결과를 덮어쓸 수 없습니다. 자동화 서비스가 관리하는 프로젝트는 다음 확인 시 재시도 작업을 실행하며, 그 밖의 프로젝트는 아키텍처 Worker를 실행해야 합니다.
- 화면은 실패 이유와 **분석 다시 시도** 버튼을 표시하고 완료·실패 시 상태 폴링을 멈춥니다. 재시도하면 폴링을 재개합니다.

반영 시 Backend 재빌드·재시작으로 Flyway `V12__architecture_diagram_failures.sql`을 적용하고 Frontend·Worker도 새 버전으로 갱신합니다. 기존 DB 초기화는 필요 없습니다. 중단된 과거 진행 작업도 만료 대상입니다. Windows·Mac에서 같은 API와 Python Worker 코드를 사용하지만 Mac 실장비 추론은 별도 확인해야 합니다.

분석용 재업로드(`POST /api/projects/{projectId}/architecture`)도 등록과 같은 이미지 내용·크기 검사를 적용합니다. 잘못된 파일은 기존 이미지를 교체하지 않습니다. 화면의 재업로드와 코딩 연결 모두 PDF 첫 페이지·WebP/GIF를 PNG로 변환한 뒤 서버에 전달합니다.

이 업로드 큐의 추출 결과는 summary 1~180자, components 1~6개, name 1~60자, role 1~40자이며 isolationStatus와 state는 정의된 열거값만 허용합니다. 잘못된 결과는 400으로 거절합니다. 아래 버전형 맥락의 그래프 스키마와 구분합니다.

## 버전형 아키텍처 맥락 API

이미지 등록 때 비전 분석을 실행하고 구조화된 맥락을 보관하는 MVP API입니다. 이미지 해석은 **검증되지 않은 참고 정보**이며 코드 보안 검사 결과가 아닙니다. 기존 전체 정적 분석과 코드 근거 검증을 생략하거나 검사 상태를 변경하지 않습니다. 화면에서 명시적으로 코딩 이미지를 선택할 수 있으며, 분석 등록만으로 코딩 이미지가 자동 선택되지는 않습니다.

## 저장과 버전

- 프로젝트별 `version`이 증가합니다. PNG/JPEG 원본을 PostgreSQL `bytea`로 저장하며 이미지 5 MiB, 16 MP, 가로·세로 각각 8192 px까지 허용합니다. MIME뿐 아니라 실제 이미지 형식·헤더 크기·디코딩 가능 여부를 확인합니다. 비전 worker와 같은 크기 제한을 적용하여 긴 띠 형태 이미지도 업로드 단계에서 차단합니다.
- `(projectId, imageSha256, model, promptVersion, sourceCommitSha)`가 같으면 기존 작업을 돌려줍니다. 기존 `FAILED` 작업도 자동으로 재실행하지 않으며 명시적 재시도 API를 사용합니다.
- 서버 설정 `CSI_ARCHITECTURE_MODEL`의 기본값은 `ministral-3:8b-instruct-2512-q4_K_M`, `CSI_ARCHITECTURE_PROMPT_VERSION`의 기본값은 `architecture-v1`입니다. 이미지·모델 식별자·프롬프트 버전·기준 커밋 중 하나가 바뀌면 새 버전입니다. 같은 모델 태그의 가중치를 교체했다면 모델 식별자 또는 프롬프트 버전도 변경해야 합니다. 태그 동일성은 가중치 동일성 보증이 아닙니다.
- 최신 업로드가 대기·실패 상태라면 이전 성공 결과를 현재 결과처럼 돌려주지 않습니다. 오래된 버전은 개별 조회로 볼 수 있습니다. 예전 이미지를 재업로드해서 캐시가 반환되어도 최신 버전 선택이 바뀌지 않습니다.
- `sourceCommitSha`가 없으면 최신성은 `UNKNOWN`, 요청한 `commitSha`와 다르면 `COMMIT_MISMATCH`입니다. `MATCHED`도 실제 배포·코드·다이어그램 일치가 검증됐다는 의미는 아닙니다.

## 프론트엔드 API

기존 로그인 세션과 `SECURITY_REVIEWER` 권한을 사용합니다. POST에는 기존 CSRF 헤더가 필요합니다. 현재 CSI와 동일하게 프로젝트별 소유권 분리 없이 리뷰어 역할이 전체 프로젝트를 조회하는 MVP 권한 구조입니다.

| Method / path | 입력 | 출력 |
| --- | --- | --- |
| `POST /api/projects/{projectId}/architectures` | multipart `file`, 선택 `sourceCommitSha` | 작업 메타데이터 + `reused` |
| `GET /api/projects/{projectId}/architectures` | 없음 | `{items: [...], advisoryOnly: true}`; 최신 50개 |
| `GET /api/projects/{projectId}/architectures/{id}` | 없음 | 작업 메타데이터 |
| `GET /api/projects/{projectId}/architectures/{id}/image` | 없음 | 인증된 이미지 응답, `private, no-store` |
| `GET /api/projects/{projectId}/architecture-context?commitSha=...` | 선택 현재 커밋 | 아래 맥락 응답 |
| `POST /api/projects/{projectId}/architectures/{id}/retry` | 없음 | 실패 작업만 같은 버전으로 재대기 |

업로드는 `FormData`를 사용하고 `Content-Type`을 수동 지정하지 않아야 브라우저가 multipart boundary를 넣습니다. `QUEUED`와 `RUNNING` 동안 작업 조회를 3~5초 간격으로 polling합니다. 전용 SSE 이벤트는 아직 없습니다. 모델 실행 서버가 꺼져 있으면 `QUEUED`에 머무르며, worker가 수신한 뒤 종료되면 10분 lease 만료 시 `FAILED/WORKER_LEASE_EXPIRED`가 됩니다.

서버의 모델 또는 프롬프트 설정이 변경되어 더 이상 현재 worker가 수신할 수 없는 이전 `QUEUED` 작업은 30초 주기의 정리에서 `FAILED/MODEL_OR_PROMPT_CHANGED`로 종료합니다. 이때 예전 버전의 retry는 409로 거절합니다. **같은 이미지를 다시 업로드**하면 현재 모델·프롬프트로 새 버전이 생성됩니다. retry는 기존 버전의 설정을 변경하지 않습니다.

```json
{
  "available": true,
  "status": "READY",
  "advisoryOnly": true,
  "codeVerificationRequired": true,
  "sourceCommitMatches": false,
  "staleness": "COMMIT_MISMATCH",
  "architecture": {
    "id": "uuid",
    "projectId": "uuid",
    "repository": "owner/repository",
    "version": 1,
    "imageSha256": "64자리 sha256",
    "imageContentType": "image/png",
    "imageWidth": 1200,
    "imageHeight": 800,
    "model": "ministral-3:8b-instruct-2512-q4_K_M",
    "promptVersion": "architecture-v1",
    "sourceCommitSha": "40자리 git sha 또는 빈 문자열",
    "status": "READY",
    "result": {},
    "errorCode": null,
    "createdBy": "reviewer",
    "createdAt": "ISO 8601",
    "finishedAt": "ISO 8601"
  }
}
```

이미지가 없으면 `available: false`, `status: NOT_PROVIDED`, `architecture: null`입니다. `available`은 해석 결과의 존재 여부만 의미합니다. UI에는 `READY`를 “이미지 해석 완료 · 코드 검증 필요”로 표현하고 `diagramType: WORKFLOW/UNKNOWN`이면 배포 구조를 파악했다고 표시하지 마세요.

## 내부 worker API

모든 `/internal/**` 요청은 기존 `Authorization: Bearer <CSI_INTERNAL_TOKEN>`을 사용합니다. 리뷰어 세션은 worker 권한을 대신하지 않습니다. 토큰을 브라우저에 전달하지 마세요.

1. `POST /internal/architectures/claim`, body `{ "model": "...", "promptVersion": "architecture-v1" }`.
2. 작업이 없으면 `{ "available": false }`. 있으면 `{ "available": true, "job": {...} }`. 작업에는 공개 메타데이터와 `imageBase64`, `leaseToken`, `leaseUntil`이 포함됩니다. `FOR UPDATE SKIP LOCKED`로 한 worker만 수신합니다.
3. 결과는 `POST /internal/architectures/{id}/result`, body `{ "leaseToken": "uuid", "result": {...} }`로 전송합니다.
4. 성공 응답은 `{ "status": "READY", "replayed": false }`. 동일 lease와 동일 JSON 결과의 재전송은 `replayed: true`로 수신 확인만 합니다. 다른 결과 덮어쓰기와 만료된 lease는 409입니다.
5. 실패는 `POST /internal/architectures/{id}/failure`, body `{ "leaseToken": "uuid", "errorCode": "MODEL_FAILED" }`. 에러는 제한된 대문자 코드이며 원문 이미지나 모델 예외 본문을 저장하지 않습니다. 같은 실패 재전송도 멱등 처리합니다.
6. `GET /internal/architectures/{id}`로 결과 전달 상태를 확인할 수 있습니다. 분석 재사용을 위한 `GET /internal/projects/{projectId}/architecture-context?commitSha=...`도 지원합니다.

결과 구조는 아래 필드를 모두 포함하며 알 수 없는 필드는 거절합니다. 각 문자열은 비어 있지 않아야 하며, 모르는 정보는 “확인 불가”로 명시합니다. 배열은 비워둘 수 있습니다.

```json
{
  "schemaVersion": 1,
  "imageSha256": "업로드 이미지 SHA256",
  "model": "작업에 고정된 모델",
  "promptVersion": "architecture-v1",
  "diagramType": "ARCHITECTURE",
  "summary": "이미지에서 관찰한 구조 요약",
  "components": [
    { "id": "api", "label": "Backend", "kind": "service" },
    { "id": "db", "label": "Database", "kind": "storage" }
  ],
  "flows": [
    { "from": "api", "to": "db", "data": "회원 정보", "protection": "확인 불가" }
  ],
  "trustBoundaries": [],
  "codeHints": ["backend/app/core/csi_signup.py"],
  "assumptions": ["이미지가 최신 구현이라는 보장은 없음"],
  "uncertainties": ["비밀번호 해시 구현은 코드 검증 필요"],
  "metrics": { "wallDurationMs": 1200, "prompt_eval_count": 500 }
}
```

- `diagramType`: `ARCHITECTURE`, `WORKFLOW`, `UNKNOWN`.
- components 최대 64개, ID 64자·label 160자·kind 80자; 중복 ID 금지.
- flows 최대 128개, 실제 component ID만 참조; data/protection 각각 500자.
- summary 2,000자. trustBoundaries/assumptions/uncertainties 각각 64개 × 500자.
- codeHints 최대 64개 × 300자. 절대 경로, 상위 경로 이동, 역슬래시, URL 금지. 허용된 문자열이라도 저장소 manifest와 대조하기 전에는 파일 접근·검사 생략에 사용하면 안 됩니다.
- metrics 최대 30개, 값은 유한한 0 이상 숫자. 전체 JSON 150,000자 제한. 이미지 SHA·모델·프롬프트 버전은 작업과 일치해야 합니다.

## 검증과 운영 범위

`ArchitectureContextsTest`는 형식 위장/깨진 이미지/크기 폭탄, 업로드 캐시, 최신성 표시, 결과 스키마·경로, lease·재전송·재시도 조건을 검증합니다. `ArchitectureContextsSecurityTest`는 익명/잘못된 역할 차단, CSRF, worker bearer 분리를 검증합니다. Mockito와 MockMvc 테스트이며 실제 PostgreSQL 동시성 시험을 대체하지 않습니다.

선택 실행하는 `ArchitectureContextsPostgresIT`는 실제 PostgreSQL의 임의 이름 격리 스키마에 Flyway를 실행하고, bytea 왕복·중복 업로드·두 worker의 동시 claim·동일 결과 재전송·기준 커밋 불일치·프롬프트 버전 변경을 검증한 뒤 해당 스키마만 삭제합니다. `CSI_ARCHITECTURE_TEST_DATABASE_URL`(JDBC URL), `CSI_ARCHITECTURE_TEST_DATABASE_USER`, `CSI_ARCHITECTURE_TEST_DATABASE_PASSWORD`를 환경에 제공하고 `mvn -q test -Dtest=ArchitectureContextsPostgresIT`로 실행합니다. 이 환경값이 없으면 자동으로 건너뜁니다. 테스트 계정에는 해당 테스트 DB에서 스키마 생성·삭제 권한이 필요합니다.

2026-10-22 최종 검증 결과: 이미지 크기 경계와 모델·프롬프트 변경 처리까지 포함한 일반 백엔드 테스트 **40개 통과**, 위 실제 PostgreSQL 격리 스키마 테스트 **1개 통과**. 실제 DB 시험에서는 동시에 claim한 worker 2개 중 1개만 작업을 받았으며, 이미지 저장·캐시·결과 재전송·최신 버전 선택이 기대대로 동작했습니다. [전체 검증 기록](testing/architecture-validation.json)을 참고하세요. 소규모 로컬 시험 결과이며 운영 부하·다중 서버 장애 복구·장기 보존 성능을 검증한 결과는 아닙니다.

장기 운영 전에 이미지 개수·사용자별 업로드 빈도 제한, 보존/삭제, 암호화 객체 저장소, 프로젝트별 권한, 모델 digest 기반 식별, worker 감시와 감사 로그를 추가해야 합니다. MVP에서 업로드 한 건당 제한은 있지만 누적 저장량 제한은 없습니다. 분석 실패나 추측을 개인정보보호법 위반 확정으로 표시하지 않습니다.

## 코딩 Agent 직접 위임 연결

`POST /api/projects/{projectId}/architectures/{id}/select-for-coding`으로 등록한 이미지를 선택합니다. Reviewer 세션과 CSRF가 필요하고 다른 프로젝트 이미지 ID는 거절합니다. 응답은 `{ "architectureId": "UUID", "selected": true }`입니다. 그 후 기존 `POST /api/scans/{scanId}/coding-proposals`를 호출하면 선택 이미지가 작업에 고정됩니다. 구조 분석 상태가 QUEUED/FAILED여도 원본 이미지로 직접 VLM 작업 지시를 만들 수 있습니다.

내부 coding claim 응답에는 해당 프로젝트에 속하는 고정 이미지의 `id`, `version`, `imageSha256`, `sourceCommitSha`, `imageContentType`, `imageBase64`가 `architecture`로 추가됩니다. `vlmProvider`는 `openai` 또는 `ollama`이고, `vlmModel` 기본값은 각각 `gpt-5.4-mini-2026-03-17` / `qwen3-vl:8b`입니다. Worker 설정과 일치해야 합니다. 공개 수정안 목록에는 이미지 바이트를 포함하지 않습니다. 이미지가 연결된 새 작업은 선택한 VLM이 코드·정책 조회, 로컬 코딩 위임, 검증과 재지시를 선택하고 engine v4 / `vlm-orchestrator-v1` 결과를 반환합니다. 자세한 실행·한계는 [코딩 Agent 문서](CODING_AGENT.md#vlm-총괄-경로-vlm-orchestrator-v1)를 참고하세요.

아키텍처 미연결은 수정안 생성 차단 사유가 아닙니다. 이미지가 없으면 `architecture_id=null`로 등록하며 기존 코드·정책 기반 engine v3 경로를 사용합니다. 이미지가 연결된 경우 버전·커밋·해시 검증은 그대로 적용합니다.
