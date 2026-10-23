# 아키텍처 이미지 로컬 worker

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
