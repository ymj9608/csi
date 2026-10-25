# 수정안 아키텍처 참고와 Slack 알림

`origin/dev`의 VLM 총괄·입력 계약 검사·결과 재전송 기능을 유지하면서 팀원 커밋
`65525c09f5504616b347dab828d86061f7d98e62`의 아키텍처 참고 단계와 Slack 알림을 통합했습니다.

## 저장된 아키텍처 조회

코딩 Worker가 작업을 claim할 때 Backend가 해당 scan의 `project_id`로
`architecture_diagrams`의 `EXTRACTED` 결과를 읽습니다. 수정안에 특정 이미지가
연결되어 있으면 `project_architectures`의 이미지 내용과 일치하는 분석만 사용합니다.
다른 프로젝트나 아직 분석 중인 결과는 전달하지 않습니다.

`coding_agent/architecture_context.py`는 finding의 경로·제목·분류와 추출된
컴포넌트의 이름·역할을 비교해 최대 3개의 관련 후보를 선택합니다.
그림 추출에는 파일 경로가 없으므로 이는 **어휘가 일치하는 후보**이며 실제 코드
소속·격리의 확정 근거가 아닙니다. diagram ID, 조회한 버전의 updatedAt,
추출 상태와 finding별 일치 어휘를 결과와 모델 입력에 함께 남깁니다.
자료 없음과 대응 후보 없음도 명시하며, 존재하지 않는 컴포넌트를 만들지 않습니다.
이미지가 지정되지 않은 경우 조회 시점의 프로젝트 분석을 참고하며, 검사 커밋의
아키텍처라고 보장하지 않습니다.

`ARCHITECTURE_CONTEXT` 단계의 4초 대기는 제거했습니다. Backend가
`progress.architectureNote`를 후속 단계에서도 유지하고 완료 결과에도 맥락이
저장되므로, 5초 폴링이 순간적인 단계를 놓쳐도 설명은 남습니다.
코드 생성의 기존 `lichu-signup-v1` 수정 범위·검증 계약은 유지합니다.
이번 변경이 임의 프로젝트의 코드 자동 수정을 지원한다는 뜻은 아닙니다.

## 승인과 알림 구분

Flyway `V10__approval_notifications.sql`은 기존 행을 보존하면서 scan 단일
UNIQUE 제약을 제거하고 다음 단위로 중복을 방지합니다.

| 종류 | 중복 방지 | 저장 상태 | 동작 |
|---|---|---|---|
| `CREATE_SECURITY_REVIEW_ISSUE` | scan + action, proposal 없음 | PENDING → APPROVED/REJECTED → EXECUTED | DM 승인·거절, 기존 Kafka/checkpoint 재개 |
| `CODING_PROPOSAL_APPROVED` | proposal ID + action | APPROVED | 수정안 승인 사실을 DM으로 알림, 상세 링크만 제공 |

기존 데모의 PENDING 수정안 알림은 APPROVED로 정정합니다. 해당 구버전 행은
수정안 ID를 추측해 연결하지 않고 이력을 보존합니다. 새 알림은 수정안 결정과
동일한 DB 트랜잭션에서 생성합니다. Agent 재개 조회와 이슈 생성은 보안 검토
action만 허용하므로 알림이 기존 승인 흐름을 가로채지 않습니다.
승인만으로 원본 파일 수정·배포를 수행하지 않습니다.

## 실행

Backend를 V10까지 마이그레이션한 뒤 별도 Python 프로세스로 실행합니다.
설정은 저장소 루트 `.env` 또는 환경변수에서 읽으며 실제 환경변수가 우선합니다.

```sh
python -m pip install -r slack_bot/requirements.txt
python -m slack_bot.main
```

기본값은 현재 Slack 앱 설정에 맞는 `SLACK_MODE=socket`입니다.

| 설정 | 용도 |
|---|---|
| `SLACK_BOT_TOKEN` | `chat:write` 권한이 있는 Bot OAuth token |
| `SLACK_APP_TOKEN` | Socket Mode의 `connections:write` App-Level token |
| `SLACK_ADMIN_USER_IDS` | DM 수신 및 버튼 처리 허용 사용자 ID, 쉼표 구분 |
| `CSI_BACKEND_URL` | 기본 `http://127.0.0.1:8080` |
| `CSI_FRONTEND_URL` | DM 검사 상세 링크, 기본 `http://127.0.0.1:5174` |
| `CSI_ADMIN_USERNAME`, `CSI_ADMIN_PASSWORD` | 기존 CSI 검토자 계정 |
| `SLACK_STATE_PATH` | 수신자별 전송 기록 SQLite 경로; 기본 `.runtime/slack-deliveries.sqlite3` |

Socket Mode와 Interactivity를 활성화하고 App-Level token을 설정합니다.
이 모드에서는 HTTP Request URL이 필요하지 않습니다.
[Slack 공식 Socket Mode 문서](https://docs.slack.dev/tools/python-slack-sdk/socket-mode/).

HTTP 방식이 필요한 환경은 Socket Mode를 끄고 `SLACK_MODE=http`,
`SLACK_SIGNING_SECRET`을 설정한 뒤 Slack Interactivity Request URL을
`https://<공개 주소>/slack/interactions`로 등록합니다. 로컬 서버는 기본
`127.0.0.1:8787`이며 역방향 프록시의 전달 대상입니다.

두 방식 모두 먼저 요청을 확인 응답하고 Backend 결정은 비동기로 처리합니다.
HTTP는 서명·timestamp를 확인하며, 두 방식 모두 허용 사용자와 승인 ID를 검사합니다.
동시 클릭의 409 응답은 Backend에 저장된 최종 상태를 다시 조회합니다.
CSI 로그인 이후 CSRF 토큰을 다시 받아 사용하고 세션 만료 시 재인증합니다.
Backend의 처리자 기록에는 봇이 사용하는 CSI 계정이 저장됩니다.

## 전송과 운영 범위

poller는 수신자별 성공 기록을 SQLite에 저장합니다. 일부 수신자 전송 실패는
다음 poll에서 재시도하고, 성공한 수신자는 재전송하지 않습니다. 재시작해도
같은 상태 파일을 유지해야 합니다. 보안 검토 승인·거절·이슈 생성 상태가
변하면 기존 DM을 갱신합니다. 상태 파일을 사용하는 봇 프로세스는 하나만 실행합니다.

Slack이 전송을 수락한 직후 로컬 기록 저장 전에 프로세스가 종료되면 중복 DM이
발생할 수 있습니다. Slack 전송과 로컬 DB를 하나의 트랜잭션으로 만들 수 없으므로
정확히 한 번 전달을 보장하지 않습니다. Backend 결정 실패 시 버튼은 남아 있어
다시 시도할 수 있고, 로그에 승인 ID와 실패 유형을 남깁니다.

## 검증

```sh
python -m pip install -r agent/requirements.lock.txt -r coding_agent/requirements.txt -r slack_bot/requirements.txt
python -m pytest tests/test_coding_architecture_context.py tests/test_slack_bot.py tests/test_coding_agent.py -q
mvn -f backend/pom.xml test
npm --prefix frontend ci
npm --prefix frontend run build
# frontend 개발 서버 실행 후, Chrome 사용; API는 각 spec에서 mock
cd frontend
npx playwright test e2e/coding-flow.spec.ts e2e/approvals.spec.ts
```

자동 테스트는 프로젝트 분리·관련 후보 선택·자료 없음·표시 길이·모델 입력 연결,
보안 검토와 수정안 알림의 구분, 세션/CSRF 재인증, HTTP 서명 및 사용자 검증,
Socket Mode 확인 응답과 버튼 처리, 중복 클릭, 부분 전송 실패와 재시작 복구를 다룹니다.
실제 Slack 앱 연결·DM 수신·실제 서비스의 버튼 승인은 별도의 통합 검증 대상입니다.

### 2026-10-24 검증 기록

- 관련 Python 테스트 55개 통과: 위 세 파일, 실제 모델 호출·Slack 전송 없음.
- Maven 백엔드 전체 60개 통과.
- Chrome Playwright `coding-flow.spec.ts`, `approvals.spec.ts` 15개 통과: API mock 사용.
- Vue 타입 검사·프로덕션 빌드 통과. 기존 대형 번들 경고는 남아 있습니다.
- PGlite 임시 DB에서 V1–V10 SQL 적용, 기존 승인 보존, 같은 scan의 독립 알림,
  중복 억제와 진행 설명 보존 확인. 운영 PostgreSQL/Flyway 기동 검증과는 구분합니다.
- Windows에서 Git symlink fixture를 index의 `120000` 모드로 구성하여 링크 거부를
  검증했습니다. POSIX `0600` mode bit 검사는 POSIX 환경에만 적용합니다.
- 현재 환경에 `SLACK_APP_TOKEN`이 없어 실제 Socket Mode 연결·DM 클릭은 실행하지 않았습니다.
