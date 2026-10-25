# 아키텍처 VLM 컨텍스트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 프로젝트당 아키텍처 다이어그램 1장을 업로드하면 VLM(Qwen3-VL, 로컬 Ollama)이 컴포넌트 이름·역할·격리/프로덕션 여부를 추출하고, 사람이 확인(CONFIRMED)한 뒤, 보안 리뷰 Agent가 finding을 설명할 때 이 맥락을 배경 정보로 참고하게 만든다.

**Architecture:** 백엔드(Spring)가 다이어그램 저장·상태 머신을 관리하고, 로컬에서 도는 별도 Python Worker(`architecture_agent/`, `coding_agent/`와 같은 레이아웃)가 이미지를 가져와 Qwen3-VL로 분석해 결과를 백엔드에 돌려준다. 스캔 접수 시점에 CONFIRMED 컴포넌트 텍스트를 `scans` 테이블에 스냅샷하고, `agent/csi_agent`가 새 MCP 도구로 그 스냅샷을 무조건(강제) 조회해 리뷰 프롬프트의 배경 설명으로만 쓴다 — 기존 fact/citation 엄격 검증 대상에는 포함하지 않는다.

**Tech Stack:** Spring Boot(Java) 백엔드, PostgreSQL(Flyway), Python Worker(httpx, 로컬 Ollama HTTP API), FastMCP(`mcp_servers`), LangGraph(`agent/csi_agent`), Vue 3(`frontend`).

**Spec:** `docs/superpowers/specs/2026-10-23-architecture-vlm-context-worker-design.md`

## Global Constraints

- 프로젝트당 다이어그램은 정확히 1장 (최신 것으로 교체, 버전 병합 없음).
- VLM은 업로드 시 1회만 돈다. 스캔마다 재실행하지 않는다.
- VLM 추출 결과는 컴포넌트 이름·역할·격리(ISOLATED/PRODUCTION/UNKNOWN) 여부·상태(OBSERVED/INFERRED/UNKNOWN)까지만 — 파일 경로는 절대 포함하지 않는다.
- CONFIRMED(사람이 확인)되지 않은 컴포넌트는 리뷰 Agent에 노출되지 않는다.
- 이 기능은 `LLM_MODE=enabled`일 때만 효과가 있다 (RULE_BASED 경로는 안 건드림, 실패하지 않고 조용히 비활성).
- `coding_agent/`는 이 작업에서 전혀 수정하지 않는다.
- 다이어그램 업로드는 기존 `ArchitectureUpload.vue`(개인 사진첩, "브라우저에만 저장" 문구)와 별도의 새 UI 동작이다 — 기존 UI/문구는 건드리지 않는다.
- 리뷰 Agent에 들어가는 아키텍처 텍스트는 `analysis.py`의 fact/citation 무결성 검증 대상이 아니다 (citationIds/factIds 서브셋 체크를 우회해야 함 — 즉 별도 필드로 프롬프트에 주입하고, facts 리스트에는 추가하지 않는다).
- Worker(`architecture_agent/`)는 Docker 밖, 로컬 Ollama가 있는 머신에서 실행한다.

## Review Focus

- **다이어그램이 아직 없거나 CONFIRMED 안 된 프로젝트의 스캔**: 아키텍처 컨텍스트가 비어있어도 스캔이 실패하거나 리뷰가 막혀서는 안 된다 — 빈 문자열/없음으로 조용히 통과.
- **`LLM_MODE=disabled`(RULE_BASED)인 스캔**: 아키텍처 컨텍스트 조회·주입 로직이 아예 실행되지 않거나, 실행돼도 아무 효과가 없어야 한다 — 에러가 나면 안 된다.
- **동시에 두 번 업로드되거나 Worker가 중복으로 claim하는 경우**: 같은 다이어그램을 두 Worker가 동시에 처리하려고 하면 하나만 성공해야 한다 (원자적 claim).
- **VLM이 깨진/스키마에 안 맞는 JSON을 반환하는 경우**: Worker가 그걸 그대로 "EXTRACTED"로 저장하면 안 되고, 검증 실패로 처리해야 한다.
- **아직 CONFIRMED 안 된 상태에서 PATCH(확인) 요청이 오는 경우(예: EXTRACTED 전에 확인 시도)**: 적절한 에러로 거부해야 한다, 빈 상태를 CONFIRMED로 만들면 안 된다.

---

## Task 1: 백엔드 — 다이어그램 저장 + 업로드/조회 API

**Files:**
- Create: `backend/src/main/resources/db/migration/V7__architecture.sql`
- Create: `backend/src/main/java/com/csi/ArchitectureController.java`
- Test: `backend/src/test/java/com/csi/ArchitectureControllerTest.java`

**Interfaces:**
- Produces: `POST /api/projects/{id}/architecture` (multipart `file`) → `201 {"id": uuid, "status": "QUEUED"}`
- Produces: `GET /api/projects/{id}/architecture` → `200 {"status": "QUEUED"|"LOADING_MODEL"|"ANALYZING"|"EXTRACTED", "components": [...] | null, "summary": string | null, "confirmed": bool}` 또는 다이어그램 없으면 `404` — `status`는 업로드→완료까지 단계별 진행 상황이며, 프론트가 이 값으로 "Qwen 모델 로드 중" / "아키텍처 인식 중" / "인식 완료" 같은 문구를 보여준다 (coding_agent Worker가 `phase`를 보고하는 것과 같은 패턴 — 새 phase 테이블/필드 없이 기존 `status` 컬럼 값을 그대로 단계로 씀)

**Steps:**

- [ ] **Step 1: 마이그레이션 작성**

```sql
CREATE TABLE architecture_diagrams (
  id UUID PRIMARY KEY,
  project_id UUID NOT NULL UNIQUE REFERENCES projects(id),
  image BYTEA NOT NULL,
  content_type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'QUEUED',
  components JSONB,
  summary TEXT,
  confirmed BOOLEAN NOT NULL DEFAULT false,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 2: `ArchitectureControllerTest`에 실패하는 테스트 작성** — `postArchitecture_storesQueuedDiagram()`: PNG 바이트를 멀티파트로 업로드 → 응답 `status=QUEUED` 확인. `getArchitecture_returns404WhenNone()`: 업로드 없는 프로젝트 조회 → 404.

- [ ] **Step 3: 테스트 실행, 실패 확인** — `cd backend && mvn -Dtest=ArchitectureControllerTest test` → `ArchitectureController` 없어서 컴파일 실패 확인.

- [ ] **Step 4: `ArchitectureController` 구현** — 기존 `ApiController`의 `db.jdbc`/`db.one`/`db.list` 헬퍼, `ON CONFLICT(project_id) DO UPDATE` upsert(1프로젝트-1다이어그램 제약 반영)로 저장. `GET`은 `components`/`status`/`confirmed`만 반환(이미지 바이트 제외).

- [ ] **Step 5: 테스트 실행, 통과 확인**

- [ ] **Step 6: Commit** — `git add backend/src/main/resources/db/migration/V7__architecture.sql backend/src/main/java/com/csi/ArchitectureController.java backend/src/test/java/com/csi/ArchitectureControllerTest.java && git commit -m "feat: add architecture diagram upload/read endpoints"`

---

## Task 2: 백엔드 — Worker용 내부 API (이미지 조회, 결과 제출, claim)

**Files:**
- Modify: `backend/src/main/java/com/csi/ArchitectureController.java`
- Modify: `backend/src/test/java/com/csi/ArchitectureControllerTest.java`

**Interfaces:**
- Consumes: Task 1의 `architecture_diagrams` 테이블
- Produces: `POST /internal/projects/{id}/architecture/claim` → `200 {"diagramId": uuid}` (status를 `QUEUED`→`LOADING_MODEL`로 원자적 전환, `SELECT ... WHERE status='QUEUED' FOR UPDATE SKIP LOCKED` 패턴) 또는 claim할 게 없으면 `204`
- Produces: `POST /internal/architecture/{diagramId}/progress` (body: `{"phase": "ANALYZING"}`) → `status`를 그 값으로 전환. `LOADING_MODEL` 상태에서만 `ANALYZING`으로 전환 허용(그 외 상태 전이는 `409`) — Worker가 모델 로드 끝내고 Qwen 호출 직전에 호출
- Produces: `GET /internal/architecture/{diagramId}/image` → raw bytes, `Content-Type` 헤더
- Produces: `POST /internal/architecture/{diagramId}/result` (body: `{"components": [{"name","role","isolationStatus","state"}, ...], "summary": string}`) → `components`·`summary` 저장, `status`를 `EXTRACTED`로 전환. 잘못된 스키마(필수 필드 누락)면 `400`.

**Steps:**

- [ ] **Step 1: 실패하는 테스트 작성** — `claim_transitionsQueuedToLoadingModel()`, `claim_returns204WhenNoneQueued()`, `progress_transitionsLoadingModelToAnalyzing()`, `progress_rejects409FromWrongState()`, `postResult_setsExtractedAndStoresComponentsAndSummary()`, `postResult_rejects400OnMissingFields()`

- [ ] **Step 2: 테스트 실행, 실패 확인**

- [ ] **Step 3: 엔드포인트 구현** — `coding_agent`가 쓰는 `/internal/**` + `Bearer CSI_INTERNAL_TOKEN` 인증 패턴을 그대로 따름 (기존 `Intake.java`/`ApiController`의 internal 엔드포인트와 같은 Security 설정 재사용).

- [ ] **Step 4: 테스트 실행, 통과 확인**

- [ ] **Step 5: Commit**

---

## Task 3: 백엔드 — 확인(CONFIRM) API + scans 스냅샷

**Files:**
- Create: `backend/src/main/resources/db/migration/V8__scan_architecture_snapshot.sql`
- Modify: `backend/src/main/java/com/csi/ArchitectureController.java`
- Modify: `backend/src/main/java/com/csi/Intake.java`
- Modify: `backend/src/test/java/com/csi/ArchitectureControllerTest.java`

**Interfaces:**
- Produces: `PATCH /api/projects/{id}/architecture` (body: `{"components": [...], "summary": string}`) → `confirmed=true`로 저장 (관리자가 컴포넌트뿐 아니라 요약 문장도 고쳐서 확정할 수 있음). `status != 'EXTRACTED'`면 `409`.
- Produces: `GET /internal/scans/{id}/architecture` → `200 {"context": "텍스트" | ""}` — scan 접수 시점에 스냅샷된 값
- Modifies: `Intake.java`의 스캔 insert 로직 — 해당 프로젝트의 `architecture_diagrams`가 `confirmed=true`면 `summary` + `components`를 사람이 읽을 텍스트로 직렬화(예: 요약 문단 먼저, 그다음 컴포넌트별 줄바꿈 목록)해 `scans.architecture_context`에 같이 저장, 아니면 null

**Steps:**

- [ ] **Step 1: 마이그레이션** — `ALTER TABLE scans ADD COLUMN architecture_context TEXT;`

- [ ] **Step 2: 실패하는 테스트 작성** — `patchArchitecture_requiresExtractedStatus()`(QUEUED 상태에서 PATCH → 409), `patchArchitecture_setsConfirmed()`, `intake_snapshotsConfirmedArchitectureIntoScan()`(confirmed=true인 프로젝트로 스캔 접수 → `scans.architecture_context`에 텍스트 있음), `intake_leavesNullWhenNotConfirmed()`

- [ ] **Step 3: 테스트 실행, 실패 확인**

- [ ] **Step 4: 구현** — `Intake.java`의 기존 `policy_version`/`policy` 스냅샷 로직 바로 옆에 같은 패턴으로 추가 (기존 INSERT 문에 컬럼만 추가).

- [ ] **Step 5: 테스트 실행, 통과 확인**

- [ ] **Step 6: Commit**

---

## Task 4: Worker — `architecture_agent/` 스캐폴드 + Qwen3-VL 추출

**Files:**
- Create: `architecture_agent/__init__.py`
- Create: `architecture_agent/schema.py`
- Create: `architecture_agent/extractor.py`
- Create: `architecture_agent/worker.py`
- Create: `architecture_agent/requirements.txt`
- Test: `tests/test_architecture_extractor.py`

**Interfaces:**
- Consumes: Task 2의 `/internal/projects/{id}/architecture/claim`, `/internal/architecture/{id}/progress`, `/internal/architecture/{id}/image`, `/internal/architecture/{id}/result`
- Produces: `extractor.extract(image_bytes: bytes) -> dict` — `{"components": [{"name": str, "role": str, "isolationStatus": "ISOLATED"|"PRODUCTION"|"UNKNOWN", "state": "OBSERVED"|"INFERRED"|"UNKNOWN"}, ...], "summary": str}` — `summary`는 전체 아키텍처를 1~3문장으로 설명하는 자유 텍스트(파일 경로 언급 금지, 컴포넌트 목록과 같은 "크게만" 원칙)
- Produces: `worker.run_once(project_id: str, backend_url: str) -> bool` — claim할 게 없으면 `False`, 처리했으면 `True`. claim 직후 `progress` 엔드포인트로 `LOADING_MODEL`은 claim 응답 자체가 이미 반영하므로 별도 호출 불필요, Ollama 호출 직전에 `progress(phase="ANALYZING")` 호출

**Steps:**

- [ ] **Step 1: `schema.py`에 검증 함수 실패하는 테스트 작성** — `test_validate_rejects_missing_role()`, `test_validate_accepts_well_formed_list()`, `test_validate_rejects_unknown_isolation_status()`, `test_validate_requires_summary_string()`

- [ ] **Step 2: 테스트 실행, 실패 확인**

- [ ] **Step 3: `schema.py`에 `validate_result(raw: dict) -> dict` 구현** (`{"components": [...], "summary": str}` 형태 검증, 잘못되면 `ValueError`)

- [ ] **Step 4: 테스트 실행, 통과 확인**

- [ ] **Step 5: `extractor.py`에 실패하는 테스트 작성** — `test_extract_calls_ollama_with_image_and_parses_result()`: Ollama HTTP 호출을 모킹, 응답 JSON을 파싱해 `schema.validate_result`를 통과하는 `{"components": [...], "summary": "..."}` 딕셔너리를 반환하는지 확인. 프롬프트에 "파일 경로"라는 단어가 없는지 확인하는 `test_prompt_never_asks_for_file_paths()`, 프롬프트가 요약(summary) 작성도 요청하는지 확인하는 `test_prompt_requests_summary()`도 추가.

- [ ] **Step 6: 테스트 실행, 실패 확인**

- [ ] **Step 7: `extractor.py`에 `extract(image_bytes: bytes, model: str = "qwen3-vl:8b") -> dict` 구현** — `coding_agent/engine.py`의 로컬 Ollama HTTP 호출 패턴을 그대로 따름(`ollama.com/api/chat` 로 base64 이미지 포함 요청). 프롬프트는 Global Constraints의 "파일 경로 금지" 원칙을 명시하고, 컴포넌트 목록과 전체 요약(summary) 둘 다 요청.

- [ ] **Step 8: 테스트 실행, 통과 확인**

- [ ] **Step 9: `worker.py`에 `run_once` 구현** — `coding_agent/worker.py`의 claim→process→result 전송 구조를 그대로 따름. claim 성공(`status=LOADING_MODEL`) 직후 모델 로드 자체는 Ollama가 처음 호출될 때 알아서 하므로 Worker가 별도로 "로드 완료"를 기다릴 필요 없음 — `extractor.extract()` 호출 직전에 `POST .../progress {"phase":"ANALYZING"}` 한 번 호출 후 바로 `extract()` 실행. `--once`/`--project-id`/`--backend` CLI 인자(`argparse`, `coding_agent/worker.py`와 동일 스타일).

- [ ] **Step 10: Commit**

---

## Task 5: MCP 도구 — `get_confirmed_architecture`

**Files:**
- Modify: `mcp_servers/business.py`
- Test: `tests/test_mcp_business_architecture.py`

**Interfaces:**
- Consumes: Task 3의 `GET /internal/scans/{id}/architecture`
- Produces: `get_confirmed_architecture(scan_id: str) -> str` (MCP tool) — 빈 문자열 포함 항상 string 반환, 예외를 던지지 않음

**Steps:**

- [ ] **Step 1: 실패하는 테스트 작성** — `test_get_confirmed_architecture_returns_context_text()`, `test_get_confirmed_architecture_returns_empty_string_when_none()` (백엔드 호출 모킹)

- [ ] **Step 2: 테스트 실행, 실패 확인**

- [ ] **Step 3: 구현** — `business.py`의 `get_privacy_policy`와 완전히 동일한 패턴(`@mcp.tool(readOnlyHint=True, ...)`, `request(f'/scans/{UUID(scan_id)}/architecture')`), 반환값에서 `context` 필드만 추출.

- [ ] **Step 4: 테스트 실행, 통과 확인**

- [ ] **Step 5: Commit**

---

## Task 6: 리뷰 Agent 연동 — `graph.py` / `analysis.py`

**Files:**
- Modify: `agent/csi_agent/graph.py`
- Modify: `agent/csi_agent/analysis.py`
- Test: `tests/test_agent_architecture_context.py`

**Interfaces:**
- Consumes: Task 5의 `get_confirmed_architecture(scan_id)`
- Modifies: `analysis.py`의 `enrich(report, ..., architecture_context: str = "")` — 시그니처에 새 파라미터 추가, 프롬프트에 "배경 설명" 섹션으로 포함하되 `facts`/`citationIds` 리스트에는 추가하지 않음

**Steps:**

- [ ] **Step 1: 실패하는 테스트 작성** — `test_enrich_includes_architecture_context_in_prompt_not_facts()`: `architecture_context="Isolated CSI Lab Mode — 격리된 연습 환경"`를 넘겨서 `enrich()` 호출 → 생성된 프롬프트 문자열에 그 텍스트가 포함되지만, 결과 리뷰의 `factIds`/`citationIds` 검증 로직엔 영향 없음을 확인. `test_enrich_works_with_empty_architecture_context()`: 빈 문자열이어도 에러 없이 기존처럼 동작(현재 동작 regression 테스트).

- [ ] **Step 2: 테스트 실행, 실패 확인**

- [ ] **Step 3: `graph.py`에 `get_scan_context`와 같은 자리에 무조건 호출되는 아키텍처 컨텍스트 조회 추가** — planner의 `READ_TOOLS` 루프에 넣지 않음(Global Constraints 참고). `analysis.enrich()` 호출부에 결과 전달.

- [ ] **Step 4: `analysis.py`의 `enrich()` 수정** — 파라미터 추가, 프롬프트 템플릿에 배경 설명 섹션 삽입.

- [ ] **Step 5: 테스트 실행, 통과 확인**

- [ ] **Step 6: 기존 Agent 테스트 전체 재실행해서 회귀 없는지 확인** — `.venv/bin/python -m pytest tests/ -q`

- [ ] **Step 7: Commit**

---

## Task 7: 프론트엔드 — 다이어그램 등록 + 확인 화면

**Files:**
- Create: `frontend/src/components/ArchitectureDiagramRegister.vue`
- Create: `frontend/src/lib/architectureDiagram.ts`
- Modify: `frontend/src/views/Console.vue`
- Test: `frontend/e2e/architecture-diagram-register.spec.ts`

**Interfaces:**
- Consumes: Task 1/3의 `POST /api/projects/{id}/architecture`, `GET /api/projects/{id}/architecture`, `PATCH /api/projects/{id}/architecture`
- Produces: `architectureDiagram.ts`의 `uploadDiagram(projectId: string, file: File): Promise<void>`, `getDiagramStatus(projectId: string): Promise<{status, components, summary, confirmed}>`, `confirmComponents(projectId: string, components: Component[], summary: string): Promise<void>`

**Steps:**

- [ ] **Step 1: `architectureDiagram.ts` API 래퍼 작성** — 기존 `frontend/src/lib/api.ts`의 `api()` 헬퍼 재사용. `status` 값별 한국어 문구 매핑 상수도 여기 둠: `QUEUED`→"대기 중", `LOADING_MODEL`→"Qwen 모델 로드 중", `ANALYZING`→"아키텍처 인식 중", `EXTRACTED`→"인식 완료".

- [ ] **Step 2: `ArchitectureDiagramRegister.vue` 작성** — 새 업로드 버튼(기존 `ArchitectureUpload.vue`와 별도, 새 동의 문구: "이 이미지는 아키텍처 분석을 위해 서버로 전송됩니다"), 업로드 후 2초 간격 폴링으로 `status` 확인하며 Step 1의 문구를 진행 표시로 보여줌(QUEUED→LOADING_MODEL→ANALYZING 순서로 바뀌는 걸 그대로 노출, 코딩 Agent 수정안 화면의 단계 표시와 같은 패턴), `EXTRACTED`면 전체 요약(summary) 텍스트(편집 가능) + 컴포넌트 카드 목록(OBSERVED/INFERRED/UNKNOWN 뱃지, 이름/역할/격리여부 편집 가능) + "전체 확인" 버튼.

- [ ] **Step 3: `Console.vue`에 새 컴포넌트 연결** — 프로젝트 상세 화면에 탭/섹션으로 추가.

- [ ] **Step 4: E2E 테스트 작성** — `test('업로드 후 EXTRACTED 상태에서 컴포넌트 확인하면 CONFIRMED로 바뀐다')`, 기존 `frontend/e2e/architecture.spec.ts`의 테스트 패턴(Playwright) 참고.

- [ ] **Step 5: 빌드 + E2E 실행 확인** — `cd frontend && npm run build && npx playwright test e2e/architecture-diagram-register.spec.ts`

- [ ] **Step 6: Commit**

---

## Self-Review Notes

- **Spec coverage**: 목표 1~5(업로드, 1회 추출, 확인 화면, 리뷰 반영, 심각도 맥락 구분) 각각 Task 1·4·7 / Task 4 / Task 7 / Task 5·6 / Task 6에서 다룸. 비목표(coding_agent 변경, 새 탐지 규칙, 파일 매핑, OpenAI, Slack)는 어떤 Task에도 없음 — 의도대로.
- **Review Focus 반영**: 빈 컨텍스트 graceful (Task 6 Step 1), RULE_BASED 무해 (Task 6은 `enrich()`에만 들어가므로 RULE_BASED 경로 자체를 안 건드림 — 추가 테스트 불필요, Global Constraints로 충분), 중복 claim (Task 2 Step 1), 깨진 VLM JSON (Task 4 Step 1), 미확인 상태 PATCH (Task 3 Step 2) — 모두 커버됨.
