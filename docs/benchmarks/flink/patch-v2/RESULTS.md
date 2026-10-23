# Flink 패치 비교 v2

상태: **모델 패치 실험 미실행**

| 방식 | 계획/기록 | 검증 통과 | 실제 요청 합계(ms) | 초기 분석 포함 합계(ms) | 코드 모델 입력 토큰 |
| --- | --- | --- | --- | --- | --- |
| full_code | 3/0 | 0 | 미측정 | 미측정 | 미측정 |
| code_index | 3/0 | 0 | 미측정 | 미측정 | 미측정 |
| vision_index | 3/0 | 0 | 미측정 | 미측정 | 미측정 |

품질 판단: {"full_code": {"observedQualityPreserved": false, "firstUseTimeImproved": null, "requestTokensReduced": null, "conclusion": "INCOMPLETE", "attributableToSuccessfulVisionPipeline": false}, "code_index": {"observedQualityPreserved": false, "firstUseTimeImproved": null, "requestTokensReduced": null, "conclusion": "INCOMPLETE", "attributableToSuccessfulVisionPipeline": false}}

로직 단위 테스트와 실제 모델 패치 품질은 별개입니다. 실패 실행도 분모와 비용에 포함합니다.
반복 3회는 같은 문제의 변동성 확인이며 통계적 비열등성 증명이 아닙니다.
