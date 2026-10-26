# 아키텍처 이미지 로컬 worker

## 현재 경로: 등록 직후 자동 분석

프로젝트 등록 또는 서버 분석용 이미지 업로드가 완료되면 `QUEUED` 작업이 저장됩니다. `architecture-worker` 서비스가 `/internal/architecture/claim`에서 가장 오래된 대기 작업을 하나씩 가져가 `qwen3-vl:8b-instruct`로 분석합니다. 프로젝트 UUID 지정이나 GitHub Push는 필요하지 않습니다. 결과는 `EXTRACTED`, 오류는 `FAILED`로 표시하며 재시도 버튼도 같은 대기열을 사용합니다.

```bash
docker compose up -d --build backend architecture-worker frontend
# 컨테이너 대신 호스트에서 실행할 때 (둘 중 하나만 실행)
.venv/bin/python -m architecture_agent.diagram_worker --all --env-file .env
```

등록 시에는 **이미지 구조 분석**을 수행합니다. GitHub 저장소 이름의 등록 자체가 코드 다운로드나 보안 검사를 의미하지 않습니다. 실제 코드·정책을 포함한 통합 보안 분석은 Push/CLI 검사 접수 후 실행하며, 통합 보안 분석이 이미 진행 중인 이미지는 새 이미지 분석 작업에서 제외합니다.

아래는 이전 프로젝트 지정·별도 맥락 연결 방식의 설명입니다.

## 팀원 업로드 화면과 병합 후 로컬 실행

`feature/vlm-diagram-architecture-worker`의 프로젝트별 분석과 기존 코딩 이미지 연결은 서로 다른 API/저장소를 사용합니다. 화면의 분석 완료가 코딩 Agent 연결 완료를 의미하지는 않습니다.

1. 저장소 루트에서 `docker compose --env-file .env -f compose.yml up -d --build backend frontend`로 변경된 서버와 UI를 반영합니다. Docker Desktop과 Ollama가 실행 중이어야 합니다.
2. `http://localhost:5174`에서 프로젝트 → 아키텍처 → 이미지를 업로드합니다. 주소의 `project=` 값이 아래 프로젝트 UUID입니다.
3. 아래 워커를 실행하면 `QUEUED → LOADING_MODEL → ANALYZING → EXTRACTED` 순서로 분석하고 컴포넌트 카드가 표시됩니다.

```bash
.venv/bin/python -m pip install -r architecture_agent/requirements.txt
.venv/bin/python -m architecture_agent.worker \
  --project-id '<프로젝트 UUID>' \
  --backend http://127.0.0.1:8080 \
  --env-file .env \
  --model qwen3-vl:8b-instruct
```

모델이 설치되어 있지 않으면 먼저 `ollama pull qwen3-vl:8b-instruct`를 실행합니다. `--once`를 추가하면 대기 중인 작업 하나를 처리한 뒤 종료합니다. 결과 응답 후 모델을 메모리에서 해제하도록 설정했습니다. 상세 그림은 최대 600초의 응답 대기 시간이 있어, 코딩 워커와 동시에 실행하지 않는 편이 좋습니다.

Windows PowerShell에서는 다음 명령을 사용합니다. 프로젝트 분석은 핵심 구성요소 최대 6개를 요청하며, 토큰 제한으로 중단된 응답은 완료 처리하지 않습니다. 코딩 VLM에는 이 요약과 별개로 선택한 원본 이미지가 전달됩니다.

```powershell
.venv/Scripts/python.exe -m architecture_agent.worker --project-id '<프로젝트 UUID>' --backend http://127.0.0.1:8080 --env-file .env --model qwen3-vl:8b-instruct
```

UUID 복사 없이 `--project-id` 대신 `--repository owner/repository`를 사용할 수도 있습니다. `.env`의 CSI 로그인 계정으로 등록된 프로젝트를 조회하고, 일치하는 저장소의 UUID로 Worker를 시작합니다. 미등록·중복 프로젝트는 오류로 안내합니다. DB 초기화 후에는 프로젝트를 다시 등록하고 Worker를 재시작하면 새 UUID를 조회합니다.

프로젝트별 Worker 실행까지 자동화하려면 [로컬 프로젝트 등록 자동화](../docs/PROJECT_VERIFICATION_DESIGN.md#로컬-프로젝트-등록-자동화)를 설정합니다. 준비된 검증 프로필과 일치하는 등록 프로젝트를 조회해 프로필을 연결하고 업로드된 이미지의 대기 작업을 실행합니다.

코딩 오케스트레이터도 로컬 Qwen을 사용하려면 `.env`에 `CSI_VLM_PROVIDER=ollama`, `CSI_VLM_MODEL=qwen3-vl:8b-instruct`를 설정하고 백엔드와 코딩 Worker를 재시작합니다. 이미지 연결은 아래 4번 단계가 별도로 필요하며, 기존에 생성된 수정안에는 소급 적용되지 않습니다.

업로드 분석은 프로젝트당 한 장입니다. 이미 `EXTRACTED` 결과가 있으면 추가 이미지를 앨범에 넣어도 자동 재분석하지 않습니다. 이 신규 워커는 기존 워커의 lease/디스크 재전송 기능과 별개입니다. 처리 도중 종료되면 진행 상태가 남을 수 있으며 자동 복구는 아직 없습니다.

4. 코딩 수정안에도 이미지를 쓰려면 이미지 뷰어의 **코딩 Agent에 연결**을 누릅니다(5 MiB 이하 PNG/JPEG). 이후 위험 항목에서 새 수정안을 요청하고 기존 코딩 워커를 실행합니다. 단순 업로드만으로 코딩 작업이 실행되지는 않습니다.

`--project-id` 없이 실행하면 아래에 설명된 기존 `/internal/architectures/*` 작업 큐를 처리합니다. 프로젝트별 신규 분석은 `/internal/projects/{id}/architecture/claim`과 `/internal/architecture/{id}/*`를 사용합니다.

DB 마이그레이션은 기존 V7(contexts)·V8(coding handoff)을 보존하고 신규 diagrams 테이블을 **V9**로 배치했습니다. 팀원 브랜치의 원래 V7(diagrams)을 이미 적용한 다른 DB는 이력 차이가 있으므로 그대로 혼용하지 마세요. 현재 병합은 기존 CSI V7/V8 이력을 기준으로 합니다.

**Slack 상태:** 이 브랜치에는 Slack 알림/승인 API, Bot 설정, 이벤트 수신기가 없습니다. `.venv-slack/`은 Git 제외 경로일 뿐 연동 구현이 아닙니다. 팀원 설계 문서에도 Slack 승인과 GitHub 자동 PR은 비목표로 명시되어 있습니다. 현재 검토·승인 테스트는 CSI 웹에서 수행합니다. Slack 알림 및 승인 연동은 별도 구현이 필요합니다.

## 기존 아키텍처 맥락 워커

프로젝트에 등록한 이미지를 로컬 Ollama로 해석해 구조화된 참고 맥락으로 저장합니다. 이 worker는 코드를 수정하거나 보안 검사를 생략하지 않습니다. 이미지에 없는 암호화·인증 구현은 확인 불가로 남기며 사용자 흐름도와 시스템 구조도를 구분합니다.

CSI 저장소 루트에서 실행합니다. 기존 `.env`의 `CSI_INTERNAL_TOKEN`과 백엔드 설정이 같아야 합니다. `.env` 또는 토큰을 팀 공유 문서나 브라우저에 넣지 마세요.

```bash
.venv/bin/python -m pip install -r architecture_agent/requirements.txt
# 설치된 모델의 vision 지원 여부는 worker가 /api/show로 확인합니다.
.venv/bin/python -m architecture_agent.worker \
  --backend http://127.0.0.1:8080 \
  --ollama-url http://127.0.0.1:11434
```

작업 하나만 처리하고 끝내려면 `--once`를 붙입니다. 작업이 없으면 성공 종료합니다. 별도 머신의 CSI 백엔드는 `--backend https://...`로 연결할 수 있지만 이미지 추론은 localhost Ollama만 사용합니다. GPU가 공유되는 코딩 worker와 동시 추론 시 지연이 늘 수 있으므로 MVP 시연에서는 작업을 순차 실행하세요.

백엔드 업로드 → `QUEUED` → worker claim → `RUNNING` → 유효한 JSON 저장 → `READY` 순서입니다. 모델 실행을 비롯한 실패는 `FAILED`로 보고합니다. 재시도는 API의 명시적 retry 작업이며 worker가 모델 추론을 반복해서 시도하지 않습니다. 이미지·모델·프롬프트·기준 커밋에 대한 재사용은 백엔드가 담당합니다.

결과와 실패 전송은 `.runtime/architecture`에 권한 `0600` 파일로 먼저 기록합니다. 백엔드 오류나 응답 유실 시 같은 내용을 세 번 전송하고 다음 루프 또는 재시작에서 재개하므로 전송 실패 때문에 모델을 다시 실행하지 않습니다. 영구적인 HTTP 거절은 재시도하지 않고 전달 상태를 별도 파일에 남깁니다. worker 자체 종료 후 lease 만료는 백엔드에서 처리하며 새 작업으로 자동 재실행하지 않습니다. 로컬 결과 파일에는 구조 요약이 있으므로 `.runtime`은 Git에서 제외합니다.

깨졌거나 읽을 수 없는 로컬 전달 파일은 같은 디렉터리의 `quarantine-*.corrupt`로 원자적으로 이동하고 재처리하지 않습니다. 원문 대신 격리 파일명만 기록하며 일반 파일 권한은 `0600`입니다. 따라서 손상된 파일 하나 때문에 정상 결과 전송과 새 작업 수신이 계속 멈추지 않습니다. 정상 결과의 일시적인 백엔드 전송 실패는 기존 pending 파일을 유지하고 복구를 기다립니다. 격리 자체가 실패하거나 정상 전달 확인 기록을 저장할 수 없는 파일 시스템 장애는 새 작업 수신을 보류합니다.

재사용 가능한 추론 함수:

```python
from pathlib import Path
from architecture_agent.vision import analyze_image

result = analyze_image(Path("architecture.png").read_bytes())
```

- `metrics.prompt_eval_count`, `eval_count`는 Ollama가 보고한 입력·출력 토큰 수입니다. 텍스트만 별도로 토큰화한 계산값이 아닙니다.
- `total_duration`, `load_duration`, `prompt_eval_duration`, `eval_duration` 단위는 **나노초**입니다. `wallDurationMs`는 모델 기능 조회부터 응답 스키마 검증까지 실제 클라이언트 경과 시간이며 **밀리초**입니다.
- `prompt_eval_cached_count`는 Ollama가 실제 반환한 경우만 보존합니다. 없을 때 캐시 사용을 0으로 가정하지 않습니다.
- 필수 사용량 누락, 생성 길이 초과, 잘못된 구조/참조/상대 경로는 성공 처리하지 않습니다. 구조화된 JSON도 모델 관찰이 사실이라는 보장은 아니므로 코드와 확인해야 합니다.
- 이미지 내 텍스트는 지시가 아닌 데이터로 취급합니다. 프롬프트와 스키마 검증은 의미적인 모든 잘못된 추론이나 프롬프트 주입을 차단한다는 보장이 아닙니다.

프론트엔드 계약은 [ARCHITECTURE_API.md](../docs/ARCHITECTURE_API.md), 준비된 TypeScript client는 `frontend/src/lib/architecture.ts`입니다. 현재는 업로드 API와 조회 준비 단계이며 기존 리뷰 파이프라인의 자동 입력으로 연결하지 않았습니다.

```bash
.venv/bin/python -m pytest tests/test_architecture_agent.py -q
```

테스트는 가짜 HTTP transport를 사용합니다. 실제 모델 성능 측정 결과와 혼동하지 마세요.
