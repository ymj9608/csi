# 커밋 변경 비교와 보안 리뷰

검사 상세의 **코드 변경 리뷰**에서 수정 전후 코드를 나란히 보고, 변경 파일별 선언 요약과 정적 보안 후보의 신규·유지·미탐지를 확인합니다. 기존의 ‘같은 브랜치 이전 완료 검사’ 비교와 별개입니다. 완료된 과거 보고서는 소급 변경하지 않습니다.

## 데이터와 판정

- GitHub Push는 `github.event.before`와 `github.sha`의 두 Git 트리를 같은 버전의 승인된 Semgrep 규칙으로 검사합니다. 수동 실행은 부모 커밋을 기준으로 사용합니다. 최초 Push/기준 미제공은 `NO_BASE`, 기준 객체를 찾을 수 없으면 `BASE_UNAVAILABLE`이며 임의의 비교를 만들지 않습니다.
- `git cat-file`로 커밋의 Java/Python blob을 읽습니다. 대상 코드·빌드 스크립트·Git filter를 실행하지 않습니다. symlink/submodule, 비지원 경로·언어는 비교 대상에서 제외합니다.
- diff는 실제 변경 구간과 앞뒤 두 줄입니다. 문자열·주석·7자리 이상 연속 숫자는 전송 전에 마스킹합니다. 리터럴만 바뀌어 마스킹 후 양쪽 내용이 같아도 변경 행으로 표시합니다. 마스킹된 코드를 원본 코드로 오해하면 안 됩니다.
- 변경 요약은 `STATIC_FACTS`입니다. Python 함수 선언과 지원하는 `Signup`, `ProfileUpdate`, `User`, `CsiSignupProfile` 클래스의 필드 선언 추가/삭제를 추출합니다. Java는 diff·행 수·연결된 탐지 결과를 제공하지만 기능 선언 요약은 지원하지 않습니다. 이름 변경은 추가/삭제로 나타날 수 있고 함수 내용 변경만으로 새로운 업무 기능을 추정하지 않습니다.
- 보안 리뷰는 `LINKED_FINDING_ANALYSIS`입니다. 같은 파일의 실제 Finding과 AI 리뷰를 연결하고, 수정 후 변경 라인과 탐지 위치의 겹침을 표시합니다. 변경 파일에 존재하지만 변경 행과 겹치지 않는 후보는 별도로 설명합니다.
- 신규/유지/미탐지는 fingerprint 비교입니다. 위치·이름 변경이나 규칙의 탐지 한계에도 영향을 받으므로 변경의 인과관계, 취약점 악용 가능성, 수정 완료를 증명하지 않습니다. **미탐지와 RESOLVED는 다릅니다.**

## 실행 경로

`Actions 또는 로컬 CLI → 서명된 findings + changeSet → Spring Boot 검증/scan_changes 저장 → Kafka scan.request → LangGraph → business-mcp.get_scan_changes → 기존 정책/RAG 조사 → C1 변경 사실을 포함한 Red/Blue 리뷰 → scan.result → 검증된 changeReview 저장 → SSE 갱신 → Vue`

Backend는 head SHA 일치, 파일 경로, 행 번호/유형, 크기 및 참조를 검증합니다. 결과의 Finding ID·미탐지 fingerprint가 실제 저장 데이터와 정확히 일치해야 합니다. `GET /api/scans/{id}/changes`는 인증된 화면용 API이며 business-mcp는 `/internal/scans/{id}/changes`를 사용합니다. 변경 근거가 없는 구버전 검사는 `NOT_PROVIDED`로 표시합니다.

Agent는 초기 근거 수집에서 `get_scan_changes`를 호출합니다. 이 호출은 Harness가 수행하는 필수 읽기 단계이며 모델이 선택한 도구라고 표시하지 않습니다. 이후 정책/검색 도구 선택 루프는 기존과 같습니다. 현재 Finding이 없어도 기준 커밋에 후보가 있으면 해당 규칙의 문서 근거를 조회합니다. 현재 후보가 없을 때 LLM 취약점 문장을 지어내지 않습니다.

**전후 코드와 전체 diff는 OpenAI 입력에 넣지 않습니다.** 모델에는 허용된 필드·정적 저장 사실·정책 발췌와 함께 C1(기준에도 후보가 있었는지, 변경 행과 겹치는지)만 전달합니다. UI에서 C1이 존재하는 것과 모델이 `citedFactIds`로 C1을 실제 인용한 것은 구분합니다.

## 한도

트리당 파일 2,000개·총 20MB, 파일당 1MB, 전/후 후보 각각 300개, 변경 파일 20개, 파일당 diff 100행·행 400자·선언 요약 20개입니다. 표시 제한은 `truncated`로 노출합니다. 전체 전송은 950KB 이하이며 초과하면 전송하지 않고 실패합니다. 파일 이름 변경은 삭제+추가로 취급합니다. 한글/공백 경로와 Java/Python 이외 파일은 현재 허용 경로 범위 밖입니다. 코드 읽기만 수행하며 런타임 `BUSINESS_CONTEXT` 로그를 자동 수집하지 않습니다.

## 실행과 확인

```sh
# 저장소 루트에서
SSL_CERT_FILE=/etc/ssl/cert.pem .venv/bin/python -m pytest tests -q
docker compose build backend rag-index frontend
docker compose up -d backend business-mcp rag-mcp agent frontend

# 두 실제 40자리 Git SHA를 지정; LOCAL_DEMO로 기록됨
.venv/bin/python scripts/scan_repository.py ../Lichu \
  --repository ymj9608/Lichu --branch dev \
  --base-sha BASE_FULL_SHA --head-sha HEAD_FULL_SHA
```

출력된 scanId로 `/scans/{scanId}`를 열고 코드 변경 리뷰의 파일을 선택합니다. 실행 로그에서 `mcp_start / mcp_complete · get_scan_changes`와 `REPORT_SAVED`를 확인합니다. 기존 완료 검사 화면에는 diff가 새로 생기지 않으므로 새 검사를 실행해야 합니다.

GitHub 자동 검사에는 다음 두 변경이 함께 필요합니다.

1. CSI의 새 스캐너 커밋을 Push하고 Lichu Repository의 **Settings → Secrets and variables → Actions → Variables → CSI_SCANNER_REF**를 그 전체 SHA로 지정합니다.
2. Lichu workflow에 target `fetch-depth: 0`, `CSI_BASE_SHA: ${{ github.event.before }}`, `scan_changes.py ... --output scan.json`, `CSI_SCAN_FILE: scan.json`을 적용합니다. `CSI_BACKEND_URL`과 서명 Secret은 기존 설정을 사용합니다. Hosted Runner가 접근할 HTTPS 수신 주소가 켜져 있어야 합니다.

## MCP와 Agent 구성

| 구성 | 실제 역할 |
|---|---|
| business-mcp (FastMCP) | 검사/변경 근거, 사내 정책, 필드 비교, 이력 조회; 승인 요청과 승인 후 내부 검토 이슈 생성. 업무 DB에 직접 쓰지 않고 Spring `/internal/**` 호출 |
| rag-mcp (FastMCP) | 실제 색인된 PrivacyGuard 사내 정책·외부 참조집의 검색/조항 조회, `security://guidelines/{rule_id}` Resource. OWASP 원문을 직접 색인한 corpus는 아님 |
| FastAPI Worker + LangGraph Agent | 검사 소비, 조건 분기, 모델 도구 선택→실행→관측 루프, Red/Blue 근거 검토, 보고서 저장, PostgreSQL checkpoint 및 HITL 재개 |

Red와 Blue는 **한 LangGraph Agent 안의 분석 단계**입니다. 별도 자율 Agent 두 개를 실행하는 구조가 아닙니다. 모델은 `.env`의 `LLM_MODEL` 설정을 사용하며 `LLM`, `RULE_BASED`, `LLM_FALLBACK`을 실제 실행 결과에 따라 구분합니다.

## 2026-10-20 실제 검증

- Python 40개, Spring Boot 8개 테스트 통과; Vue TypeScript/Vite 빌드 통과; 실제 API에 연결한 Chrome E2E 2개 통과(데스크톱/모바일, diff, 연결 리뷰, 미탐지, 구버전 검사).
- 추가 전후 `7f3d1b1 → baa9093`: scan `28625101-f272-4708-8056-3ee6ede7577b`, COMPLETED / LLM, 변경 파일 10개, 후보 10개. 전화번호 필드 두 선언의 추가와 후보별 C1 실제 인용을 확인했습니다.
- 보안 수정 `baa9093 → 3744e9b`: scan `07b12e38-de62-4bea-95ed-3ee009d457a1`, COMPLETED / LLM, 후보 10→5개. SEC-02/SEC-03/SEC-05 5개 미탐지와 POL-01 5개 잔존, 미탐지 후보의 문서 근거 12개 저장을 확인했습니다.
- 위 두 검사는 실제 Semgrep·Kafka·MCP·Qdrant·OpenAI를 사용한 LOCAL_DEMO입니다. GitHub Push 실행과 구분합니다. `get_scan_changes`의 호출/완료 이벤트와 `REPORT_SAVED`를 실제 API에서 확인했습니다.
- 첫 4규칙 조사 시 소진된 검색 도구 재선택으로 실패한 검사는 FAILED 상태로 보존했습니다. 소진된 도구를 모델의 선택 목록에서 제외하고 선택 응답도 검증하도록 보완한 후 위 재검사가 완료되었습니다.
