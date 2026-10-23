# Flink 패치 비교 v2

상태: 실제 패치 실행 기록 있음

| 방식 | 계획/기록 | 검증 통과 | 실제 요청 합계(ms) | 초기 분석 포함 합계(ms) | 코드 모델 입력 토큰 |
| --- | --- | --- | --- | --- | --- |
| full_code | 3/3 | 0 | 17561.079 | 17561.079 | 미측정 |
| code_index | 3/3 | 0 | 3756.5260000000003 | 3756.5260000000003 | 미측정 |
| vision_index | 3/3 | 0 | 2531.641 | 11845.520209000333 | 미측정 |

품질 판단: {"full_code": {"observedQualityPreserved": false, "observedQualityImproved": false, "firstUseTimeImproved": true, "requestTokensReduced": false, "conclusion": "QUALITY_GATE_FAILED", "attributableToSuccessfulVisionPipeline": true}, "code_index": {"observedQualityPreserved": false, "observedQualityImproved": false, "firstUseTimeImproved": false, "requestTokensReduced": false, "conclusion": "QUALITY_GATE_FAILED", "attributableToSuccessfulVisionPipeline": true}}

로직 단위 테스트와 실제 모델 패치 품질은 별개입니다. 실패 실행도 분모와 비용에 포함합니다.
반복 3회는 같은 문제의 변동성 확인이며 통계적 비열등성 증명이 아닙니다.
