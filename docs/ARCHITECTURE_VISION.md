# 아키텍처 비전 분석 검증과 연동

## 결론과 범위

아키텍처 이미지를 한 번 해석해 구조화된 맥락을 재사용하는 방식은 **코드를 찾는 순서와 범위를 정하는 보조 단계**로 적합합니다. 그림만으로 비밀번호 해시, 실제 로그 내용, 인가 조건, 개인정보 전송 구현의 안전성을 확정할 수 없습니다. 이미지가 오래되었거나 컴포넌트가 빠진 경우 선별 과정에서 취약한 코드까지 제외할 수 있습니다.

권장 흐름은 `이미지 등록 → 버전별 구조 해석·불확실성 저장 → 변경 파일 + 전체 정적 검사 결과 + 구조의 경로 힌트로 후보 선택 → 필요한 호출 경로·설정·정책 RAG 확인 → 코드 근거가 있는 리뷰 → 수정안 검증·승인`입니다. **전체 정적 검사를 유지하면서 LLM에 보내는 코드를 줄이는 것**이 목적입니다. 정적 분석이 저장소를 읽는 비용과 모든 코드를 LLM 토큰으로 입력하는 비용은 다릅니다.

현재 CSI는 이미 Semgrep 결과·마스킹된 근거·RAG를 바탕으로 리뷰합니다. `coding_agent/engine.py`도 제한된 파일과 호출 계약을 입력합니다. 따라서 아래 전체 코드 방식은 비교용 기준선이며, 기존 CSI가 전체 코드를 매번 모델에 보내고 있었다는 뜻이 아닙니다. 비전이 기존 CSI보다 더 효율적인지는 실제 워크로드에서 추가 비교해야 합니다.

사용자가 제공한 `image.png`는 서비스 업무 흐름도입니다. 컴포넌트의 실행 위치, 실제 데이터 저장소, 외부 전송 경계, 소스 경로를 모두 나타내는 배포 구조도와 구분했습니다. 그림에 있는 Slack 승인·커밋·PR 생성은 이번 작업에서 실행하지 않았습니다.

## 구현된 연결 지점

- `backend/.../ArchitectureContexts.java`, V7 migration: 프로젝트별 이미지 등록·조회·재시도, 버전/해시/기준 커밋, 작업 claim/lease와 멱등 결과 수신. 이미지 원본은 MVP 범위에서 PostgreSQL에 저장합니다.
- `architecture_agent/vision.py`: 로컬 Ollama 비전 해석, 구조화된 JSON 검증, 실제 사용량/시간 기록. 그림의 문구는 명령이 아닌 데이터로 취급합니다.
- `architecture_agent/worker.py`: 로컬 Mac이 작업을 받아 처리합니다. 결과 전달이 실패하면 디스크에 저장한 같은 결과를 재전송하여 이미지 추론을 불필요하게 반복하지 않습니다.
- `frontend/src/lib/architecture.ts`: 팀원 업로드 페이지에서 호출할 TypeScript API. 페이지 UI는 수정하지 않았습니다.
- `architecture_agent/context.py`: 스캐너·변경 파일을 필수로 유지하고, Java/Python 코드 인덱스와 확인 가능한 구조 힌트로 입력을 선별하는 독립 모듈입니다. 오래된 그림·업무 흐름도·매핑 실패 시 코드 기반 선별을 유지합니다. [선별 계약](../architecture_agent/CONTEXT.md)을 참고하세요.
- `scripts/benchmark_architecture.py`: 전체 코드 대 비전+선별 코드의 재현 가능한 비교 실험입니다. 파일 선택은 manifest에 있는 경로만 사용하며, 그림 문자열을 파일 경로나 명령어로 바로 실행하지 않습니다.

상세 요청/응답과 에러 처리는 [API 계약](ARCHITECTURE_API.md)을 참고하세요. 업로드 후 QUEUED/RUNNING 동안 3~5초 간격으로 상태를 조회하고, READY는 **이미지 해석 완료·코드 검증 필요**로 표시합니다. WORKFLOW/UNKNOWN을 전체 배포 구조 확인 완료로 표시하지 마세요. 내부 Bearer 토큰은 프런트엔드에 전달하지 않습니다.

팀원이 수집할 값과 AI·서버·사람의 책임은 [아키텍처 수집 항목](ARCHITECTURE_COLLECTION.md)에 정리했습니다. 현재 v1에 없는 요소별 bbox·그룹·검토 이력·확정된 코드 모듈 매핑은 후속 계약으로 구분합니다.

현재는 업로드→비전 결과 저장→조회까지의 독립 경로입니다. 기존 리뷰 Agent가 이 정보를 자동으로 불러와 범위를 좁히도록 연결하지 않았습니다. 이후 통합 때 변경 파일·스캐너 탐지 파일을 이미지 힌트보다 우선하고, 힌트가 없거나 오래되었으면 기존 리뷰 경로를 유지하세요. 이미지가 바뀌지 않아도 구조 변경 커밋·모델 가중치·프롬프트 변경 때 최신성을 재검토해야 합니다.

## 실행

이 브랜치의 backend/frontend 이미지를 빌드하고 Ollama를 실행한 상태에서:

```bash
# csi 저장소 루트
docker compose --project-directory . --env-file .env \
  -f compose.yml up -d --build backend frontend
.venv/bin/python -m pip install -r architecture_agent/requirements.txt
.venv/bin/python -m architecture_agent.worker --help
.venv/bin/python -m architecture_agent.worker --backend http://127.0.0.1:8080 --env-file .env
```

로컬 Worker는 `.env`의 기존 `CSI_INTERNAL_TOKEN`을 사용합니다. 모델 기본값은 `ministral-3:8b-instruct-2512-q4_K_M`입니다. 서버와 Worker의 모델·프롬프트 버전이 같아야 작업을 받을 수 있습니다. 이미지 업로드 API에는 기존 로그인과 CSRF가 필요합니다. 서버 배포 시 backend V7 migration과 nginx의 6 MiB 요청 제한도 함께 반영하세요.

이번 검증에서 현재 실행 중인 CSI 컨테이너나 프로젝트 데이터를 교체하지 않았습니다. PostgreSQL 검증은 임시 스키마에서 실행한 뒤 해당 스키마만 정리했습니다. 팀원 페이지가 준비되면 위 명령으로 새 서버를 반영하고 TypeScript API를 연결하세요.

## 비교 실험

[데이터 설명](ARCHITECTURE_BENCHMARK_DATA.md), [측정 결과](benchmarks/ARCHITECTURE_RESULTS.md), 원시 JSONL 로그를 함께 봐야 합니다.

공개 Spring Petclinic 마이크로서비스의 원본 그림과 실제 전화번호 처리 코드를 사용하는 별도 비교도 제공합니다. [공개 데이터 범위](benchmarks/PUBLIC_PROJECT_DATA.md)와 [고정한 평가 절차](ARCHITECTURE_EVALUATION_PROTOCOL.md)를 참고하세요. 이 비교에는 전체 코드와 비전 외에 **코드 인덱스만 사용하는 기준선**을 추가하여, 파일 선별의 효과와 비전의 추가 효과를 구분합니다.

[공개 프로젝트 최종 결과](benchmarks/TELEPHONE_CONTEXT_RESULTS.md)에서는 전체 111개 파일 입력이 69,539 토큰을 사용했지만 한 배치가 출력 한도를 넘어 미완료였습니다. 코드 선별 두 방식은 동일한 12개 파일·9,522 입력 토큰을 사용했습니다. 원본 그림의 구성요소 14개가 현재 정확 일치 규칙으로 모듈과 연결되지 않아, 비전 방식도 코드 인덱스로 돌아갔습니다. 두 방식의 요청 내용이 같으므로 관측 시간 차이를 비전 이득으로 계산하지 않습니다. 최초 이미지 해석 비용은 별도로 91.514초입니다.

두 선별 방식은 알려진 로그 위치 2개를 찾았지만 원문 연결 근거는 1개만 검증됐고, 필요한 맥락은 12개 중 8개만 회수했습니다. 따라서 현재 선별기를 보안 수정의 충분한 맥락 확보 수단으로 단독 적용할 수 없습니다. **검토된 구성요소↔코드 모듈 매핑, DB 스키마·외부 호출의 추가 조회, 누락 시 검토 중단/범위 확장**을 연결한 다음 새 프로토콜로 평가해야 합니다. 이번 실험은 비전이 복잡한 코드에서 항상 효율적이라는 주장을 뒷받침하지 않습니다. 실험별 파일은 [벤치마크 안내](benchmarks/README.md)에 모았습니다.

```bash
.venv/bin/python scripts/build_architecture_fixture.py --render
.venv/bin/python tests/fixtures/architecture_benchmark/verify_fixture.py
.venv/bin/python scripts/benchmark_architecture.py \
  --output .runtime/architecture-benchmark/reproduction \
  --public-log docs/benchmarks/architecture-reproduction.jsonl

# 실제 Lichu: 정답 라벨 없는 보조 비교, Git HEAD의 추적 소스만 읽음
.venv/bin/python scripts/benchmark_architecture.py --repo ../Lichu \
  --image docs/benchmarks/lichu-architecture.png --repeats 1 \
  --output .runtime/architecture-benchmark/lichu-reproduction \
  --public-log docs/benchmarks/lichu-reproduction.jsonl
```

로그 경로가 이미 존재하면 덮어쓰지 않습니다. 모델 출력 원문은 `.runtime`에 저장하며 공개 로그에는 파일 해시·위치·증거 정합 여부와 측정값을 남깁니다. 합성 데이터의 정답 JSON은 모델 입력에 들어가지 않습니다. 실제 Lichu 코드 원문이나 `.env`도 보고서에 복사하지 않습니다.

입력/출력 토큰은 Ollama의 `prompt_eval_count`/`eval_count`이며 이미지 토큰만 별도로 계산한 수치가 아닙니다. Ollama 처리 시간은 ns, 클라이언트 경과 시간은 ms입니다. 첫 이미지 해석 비용과 저장된 결과 재사용 시 코드 리뷰 비용을 따로 표시합니다. 토큰 감소가 곧 지연 감소나 정확도 유지라는 뜻은 아닙니다. 장문 코드는 파일/줄 단위 배치로 나누며, 누락하거나 임의 요약해 전체 코드라고 부르지 않습니다. 단, 배치 간 호출 관계를 완전히 추론하는 전체 프로그램 분석은 아닙니다.

정답은 고정된 네 가지 코드 위험과 네 가지 대조 사례에 대한 소규모 검증입니다. 개인정보보호법 전체의 준수율, 실제 운영 탐지율, 대규모 저장소 성능, 사용자 만족도를 측정한 것이 아닙니다. 이미지의 경로 표기는 선별 검색에 유리한 조건입니다. 실제 사용자 그림에 경로가 없다면 사람이 컴포넌트와 디렉터리를 연결하거나 별도 manifest 검색 단계가 필요합니다.

## 참고한 공식 문서

- [Mistral Vision](https://docs.mistral.ai/studio/conversations/vision): Ministral 3 8B 이미지 입력 지원.
- [Ollama Vision](https://docs.ollama.com/capabilities/vision): REST 이미지 base64 입력.
- [Ollama Usage](https://docs.ollama.com/api/usage): 입력/출력 토큰 및 ns 단위 처리 시간 정의.
