# 1. Perception & Reasoning

**Perception**은 아키텍처 이미지에서 구성 요소와 연결을 읽는 단계입니다. **Reasoning**은 실제 코드·스캐너 결과·검색된 정책 근거를 함께 검토해 수정 작업과 검증 순서를 결정하는 단계입니다. 그림만으로 취약점이나 법률 준수를 확정하지 않습니다.

아키텍처는 선택 사항입니다. 없으면 **코드·정책 근거 → 수정안 → 격리 테스트 → 관리자 검토**로 진행합니다. 이미지가 연결되면 선택한 VLM의 구조 맥락을 추가합니다. 현재 서비스의 수정 프로필은 Lichu 회원가입 실습 범위이며 Flink 실험은 별도 평가 실행기입니다.

## 실험모델

| 역할 | 모델 | 이번 실행 |
| --- | --- | --- |
| 이미지 인식 | OpenAI `gpt-5.4-mini-2026-03-17` | 실제 추출 1회 결과를 해시 확인 후 재사용 |
| 빠른 코드 수정 비교 | 같은 OpenAI 모델 | 전체 20파일 / 코드 검색 / 검색+비전, 각 1회 |
| 서비스의 로컬 VLM 선택지 | `qwen3-vl:8b` | 연결·권한 처리 자동 테스트; 이번 메모리 절약 실행에서는 추론하지 않음 |
| 서비스의 코딩 모델 | Ministral 3 8B | 앞선 로컬 반복 실험은 사용자 요청으로 중단; 완료된 품질 비교로 주장하지 않음 |

세 조건에 같은 수정 지시·편집 허용 범위·고정 테스트를 사용합니다. **전체 입력 대비 개선은 검색과 비전의 합산 효과**, **코드 검색 대비 개선은 비전의 추가 효과**로 해석합니다. 1회 결과는 빠른 확인용이며 통계적 성능 보장이 아닙니다.

## 실험데이터 → 데이터셋 구축 방법

1. 공개 `apache/flink`를 내려받아 커밋 `8d01380ff5bf9892462ef9808b1b56fd9723f54d`로 고정했습니다. 라이선스·NOTICE를 함께 보존했습니다.
2. 같은 커밋의 공식 그림 `docs/static/fig/processes.svg`를 PNG로 렌더링했습니다. 별도 생성 그림으로 대체하지 않았습니다.
3. 원본 소스 경로·크기·SHA-256을 기록하고, 실제 모델 비교 범위는 보안·통신·S3·설정 관련 **Java 20개, 173,112 bytes**로 정했습니다. 전체 저장소를 모델에 모두 넣은 실험은 아닙니다.
4. 원본 저장소를 수정하지 않고 별도 복사본의 4개 파일에 **민감정보 로그 노출·TLS 설정 회귀 5개**와 정상 로그 대조군을 넣었습니다. 공개 Flink 자체의 취약점이라는 의미가 아닙니다.
5. 정답 라벨과 테스트는 모델 입력에서 제외했습니다. 보안 5개·기능 및 안전 로그 56개, 총 **61개 테스트**로 AI 생성 패치를 평가합니다. 참조 복원 패치는 검증기 교정에만 사용합니다.
6. 실제 요청·응답·토큰 usage·수정 diff·테스트 결과·소요 시간을 저장합니다. 실패·중단도 보존하며 서로 다른 실험 조건의 수치를 섞지 않습니다.

## 수집 파일 확인

현재 열어둔 [patch-v2/README.md](benchmarks/flink/patch-v2/README.md)는 **실험 설계·평가 절차 문서**입니다. GitHub 아키텍처·원본 소스 수집의 증빙 전체를 담은 단일 파일은 아닙니다. 이번 메시지에 별도 첨부 파일은 없으므로 이 README를 기준으로 검토했습니다.

| 확인할 내용 | 실제 파일 |
| --- | --- |
| GitHub 출처·고정 커밋·수집 조건 | [Flink 프로토콜](benchmarks/flink/protocol.json), [수집·합성 변경 스크립트](../scripts/benchmark_flink.py) |
| 수집한 원본 파일 목록·크기·해시 | [source-inventory.json](benchmarks/flink/source-inventory.json) |
| 공식 아키텍처 이미지와 렌더링 | [architecture.png](benchmarks/flink/architecture.png), [렌더링 스크립트](../scripts/render_flink_architecture.mjs) |
| 합성 결함과 정답 | [ground-truth.json](benchmarks/flink/ground-truth.json), [주입 diff](benchmarks/flink/synthetic-mutations.patch) |
| 실제 빠른 비교 입력·로그 | [OpenAI 빠른 실험](benchmarks/flink/openai-quick/RESULTS.md), [고정 입력 목록](benchmarks/flink/openai-quick/protocol.json) |
| 프런트엔드에서 수집해야 하는 항목 | [ARCHITECTURE_COLLECTION.md](ARCHITECTURE_COLLECTION.md) |

## VLM 선택과 메모리

백엔드와 Worker에 같은 설정을 사용합니다. `CSI_VLM_MODEL`을 비우면 제공자별 기본 모델을 선택합니다.

```dotenv
# OpenAI 선택
CSI_VLM_PROVIDER=openai
CSI_VLM_MODEL=gpt-5.4-mini-2026-03-17
# OPENAI_API_KEY는 Worker 환경에만 보관
```

로컬 선택은 `CSI_VLM_PROVIDER=ollama`, `CSI_VLM_MODEL=qwen3-vl:8b`입니다. Worker의 `--vlm-provider`·`--vlm-model` 인자로도 지정할 수 있으며 백엔드와 일치해야 합니다. 실제 로컬 모델의 도구 선택 품질은 추가 실측 대상입니다.

이미지를 연결하지 않은 작업은 VLM/API 키 없이 기존 코드·정책 기반 코딩 경로를 사용합니다. 연결한 이미지의 커밋·해시가 잘못된 경우에는 조용히 무시하지 않고 오류로 처리합니다.

로컬 VLM과 코딩 모델은 응답 후 `keep_alive=0`으로 해제하여 검증과 동시 상주하지 않게 했습니다. Flink 실험은 로컬 추론 없이 OpenAI를 사용하고, Docker를 **한 번에 1개·4GiB·2 CPU·swap 금지·Maven heap 1536MiB**로 제한합니다. `.runtime` 등 대규모 복사본은 VS Code 파일 감시·Java/Python 색인에서 제외했습니다. 이 조치는 메모리 압박을 줄이지만 VS Code의 모든 종료 원인이 확인되었다는 뜻은 아닙니다.
