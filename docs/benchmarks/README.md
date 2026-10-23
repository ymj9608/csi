# 아키텍처 비교 실험 읽는 순서

1. 프런트엔드에서 수집할 값은 [수집 항목과 책임](../ARCHITECTURE_COLLECTION.md), 현재 요청·응답은 [v1 API](../ARCHITECTURE_API.md)를 확인합니다.
2. [합성 데이터와 Lichu 실측 결과](ARCHITECTURE_RESULTS.md)는 전체 소스 입력과 이미지 해석 후 선별 입력을 비교합니다. Lichu에는 전체 정답 라벨이 없으며, 토큰 감소를 정확도 유지로 해석하지 않습니다.
3. [공개 프로젝트 전화번호 실험](TELEPHONE_CONTEXT_RESULTS.md)은 전체 범위·코드 인덱스·저장된 비전 맥락+같은 인덱스를 비교합니다. 파일 검색의 이점과 비전의 추가 기여를 분리합니다.
4. [복잡한 목데이터 비교](complex-mock/README.md)는 24개 서비스·320개 파일과 대응하는 구조 이미지를 직접 만들어 전체 코드·코드 인덱스·비전·구조 JSON 네 방식을 비교합니다. 이미지와 목코드 ZIP, 입력·정답·측정 로그를 함께 제공합니다.
5. [설계도 개선과 Qwen3-VL 비교](complex-mock/readable-v2/README.md)는 동일한 구조를 교차 없는 연결 목록으로 다시 그리고, Qwen으로 기존/개선 그림을 각각 2회 인식합니다. 완벽 인식을 가정한 원본 구조 JSON 대조군의 후속 코드 검토도 실측합니다.
6. [Apache Flink 실제 코드 변경 실험](flink/RESULTS.md)은 고정한 공개 소스에 문제 5개와 안전한 대조 3개를 넣고 기존 CSI 규칙, OpenAI, 로컬 Qwen3-VL을 비교합니다. 전체 저장소 검사 실패와 모델 연결·근거 오류도 함께 기록합니다.
7. [Flink 실제 패치 품질 비교 v2](flink/patch-v2/README.md)는 동일 Ministral로 세 방식의 패치를 생성하고 보안·기능 회귀 테스트로 비교하도록 개선한 실행기입니다. 로컬 반복 실행은 시간·메모리 요청으로 중단했고, [OpenAI 빠른 실측](flink/openai-quick/RESULTS.md)에서 같은 모델로 세 조건을 각 1회 비교했습니다. 실패도 포함합니다.

## 데이터·원시 측정·재집계

| 실험 | 데이터 설명 | 원시 측정 | 집계 명령 |
| --- | --- | --- | --- |
| 합성 보안 후보 4개·대조 4개 | [고정 fixture](../ARCHITECTURE_BENCHMARK_DATA.md) | [3회 비교](architecture-synthetic.jsonl) | `.venv/bin/python scripts/summarize_architecture_benchmark.py` |
| Lichu 고정 커밋 | [파일별 해시](lichu-source-inventory.json) | [실제 저장소 비교](architecture-lichu.jsonl), [첫 실패 기록](architecture-lichu-preflight.jsonl) | 위 명령과 동일 |
| Spring Petclinic 마이크로서비스 | [출처·범위·정답 정의](PUBLIC_PROJECT_DATA.md), [고정 절차](petclinic-protocol.json) | [전화번호 비교](telephone-context.jsonl), [원본 그림 해석](petclinic-original-vision.json) | `.venv/bin/python scripts/summarize_telephone_context.py` |
| 복잡한 합성 서비스 24개 | [데이터 설명](complex-mock/DATASET.md), [소스 ZIP](complex-mock/source-code.zip), [구조 이미지](complex-mock/architecture.png), [고정 절차](complex-mock/protocol.json) | [네 방식 비교](complex-mock/measurements.jsonl) | `.venv/bin/python scripts/summarize_complex_architecture.py` |
| Apache Flink 공개 코드 + 합성 변경 | [고정 커밋·범위](flink/protocol.json), [주입 패치](flink/synthetic-mutations.patch) | [CSI 검사](flink/measurements.jsonl), [모델 비교](flink/comparison.json) | `.venv/bin/python scripts/summarize_flink_benchmark.py` |

명령은 CSI 루트에서 실행합니다. 집계 명령은 모델을 다시 호출하지 않습니다. 사용한 모델·장비는 [실행 환경](environment.json), 구현의 자동화 검증은 [테스트 기록](../testing/architecture-validation.json)에 있습니다. 실제 모델 품질과 소프트웨어 테스트 통과는 별개입니다.

각 실험은 고정한 입력 범위에서만 해석해야 합니다. 비전이 항상 빠르다는 결론이나 기업 운영 환경 전체의 보안 정확도는 입증하지 않았습니다. 공개 프로젝트의 전체 방식도 저장소의 모든 파일이 아닌 명시한 백엔드·테스트·설정 범위입니다. [프로토콜 작성 시점](petclinic-protocol-chronology.json)과 캐시·호출 순서·배치 간 근거 분리 한계도 함께 공개합니다.

팀원 공유용 모델·데이터 수집 설명: [Perception & Reasoning](../PERCEPTION_REASONING.md).
