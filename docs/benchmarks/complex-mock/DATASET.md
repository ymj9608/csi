# 복잡한 합성 서비스 데이터셋

이 실험은 실제 기업 코드 대신 **고정된 24개 업무 서비스와 아키텍처 그림**을 직접 생성합니다. 모델이 읽는 소스는 320개 파일, 150,114바이트, 4,208줄입니다. 서비스 수와 비동기 경계를 늘려 관련 코드 탐색을 검증하는 자료이며, 실제 기업 시스템의 복잡성이나 품질을 대표하는 벤치마크는 아닙니다.

## 생성 및 입력 경계

- 생성기: `scripts/build_complex_architecture_fixture.py`
- 고정 식별자: `complex-commerce-contact-v1`, seed `20261022`. 무작위 샘플링 없이 결정적인 순서로 생성합니다.
- 생성 소스: `.runtime/architecture-benchmark/complex/repository/`
- 공개 파일 목록·해시: `tests/fixtures/complex_architecture/manifest.json`
- 평가용 정답: `tests/fixtures/complex_architecture/ground_truth.json`
- 그림을 그리는 구조 명세: `tests/fixtures/complex_architecture/graph.json`
- 그림: `docs/benchmarks/complex-mock/architecture.png`, 원본 SVG도 같은 위치에 저장합니다.
- 코드 해시: `69a197f6491ab5d6f1f4b4b1aed17648923951a2d79bca8ca717b0f40f9afc1b`

코드·그림에는 실제 개인정보, 인증정보, API 키가 없습니다. 네트워크 목적지는 실행되지 않는 `.example.invalid` 예약 주소를 사용하며 동작 테스트는 가짜 전송 객체가 요청을 수집합니다. 함수 입력의 `SYNTHETIC_CONTACT_A`는 전화번호 형태도 아닌 합성 문자열입니다.

평가 정답의 취약점 ID·함수명·줄 번호는 모델에게 전달하지 않습니다. 그림에도 파일 경로와 문제 정답을 적지 않습니다. 구조 JSON을 별도 텍스트 대조군에 전달한다면 그림에 표시된 노드·역할·연결만 사용해야 합니다. 파일 목록은 코드 검색을 위한 색인으로 사용할 수 있지만 평가 정답과 섞어서는 안 됩니다.

## 업무와 연결 구조

| 그룹 | 서비스 | 서로 다른 업무 동작 예시 |
|---|---|---|
| 고객·인증 | `edge_gateway`, `identity_access`, `consent_registry`, `customer_profile` | 가장 구체적인 경로 선택, 세션 철회, 최신 동의 판정, 프로필 버전 충돌 검사 |
| 연락처 전달 | `contact_events`, `notification_dispatch`, `sms_gateway`, `audit_archive` | 이벤트 중복·순서 검사, 조용한 시간대 예약, 메시지 분할·재시도 분류, 보존 기간 처리 |
| 상거래 | `product_catalog`, `inventory_reservation`, `order_fulfillment`, `shipment_tracking` | 할인 금액 계산, FIFO 재고 할당, 주문 상태 전이, 배송 이력 중복 처리 |
| 재무 | `billing_ledger`, `payment_settlement`, `fraud_review`, `merchant_registry` | 세금·분개 균형, 정산 대조, 거래 검토 규칙, 사업 유형별 제출 문서 |
| 고객 업무 | `returns_case`, `support_case`, `loyalty_rewards`, `marketing_campaign` | 반품 기간, 지원 SLA, 포인트 중복 적립 방지, 동의한 대상 추출 |
| 데이터 | `analytics_rollup`, `search_index`, `document_archive`, `partner_webhook` | 소규모 집계 억제, 검색어 순위, 문서 보존 예외, 서명·재전송 검사 |

각 서비스는 `models`, `validation`, `repository`, `policy`, `service`, `api`, `events`, `jobs`, `metrics`, `readmodel`, `domain` Python 파일과 SQL 스키마·YAML 배포 설정으로 구성됩니다. 공통 서비스 틀을 재사용하므로 일부 코드가 반복됩니다. `domain.py` 24개는 이름만 바꾼 복제 대신 표에 있는 서로 다른 계산·검증·전이 로직을 제공합니다. 코드 길이를 맞추는 임의 문자열이나 무의미한 함수는 넣지 않았습니다.

그림에는 서비스 24개와 DB·브로커·외부 제공자 4개, 6개 그룹, 26개 연결이 있습니다. 논리적인 비동기 연결은 동일한 Kafka 브로커를 통과할 수 있습니다. 전화번호 업무는 다음과 같습니다.

```text
edge_gateway → customer_profile → profile_db
                        ↓ contact.changed
                  contact_events
                        ↓ delivery.requested / Kafka
               notification_dispatch
                        ↓ sms.requested
                    sms_gateway → external_sms
                        ↓ delivery.completed
                    audit_archive
```

## 코드만으로도 관계를 확인할 수 있는 이유

모든 군은 같은 저장소와 설정 파일에 접근합니다. 코드 전용 검색을 일부러 불리하게 만들지 않습니다.

`services/<id>/deployment.yaml`에는 다음 형식을 사용합니다.

```yaml
service: contact_events
consumes: ["contact.changed"]
produces: ["delivery.requested"]
database: business_db
routes: {}
```

생산자 `produces`와 소비자 `consumes`를 연결하면 비동기 호출 관계가 복원됩니다. 동기 서비스 연결은 `routes: {"/purpose": "target_service"}`에 있고, 추가 진입 경로는 `infra/gateway_routes.yaml`에 있습니다. 그림 밖 정기 작업도 `jobs/legacy_export.yaml`에 진입점과 `profile_db` 연결이 남아 있습니다. 일부 서비스의 일반 업무 연결은 설계 및 설정 수준이며, 모든 외부 HTTP 서버를 구현하거나 배포한 것은 아닙니다.

## 고정 과제와 정답

시작점은 `services/customer_profile/service.py`의 `execute`, 추적할 필드는 `telephone`입니다. 전화번호가 저장되면서 다른 서비스에서 `destination`, 외부 요청에서 `to`로 이름이 바뀌므로 단순히 같은 필드명만 찾는 방식으로는 전체 경로를 이해할 수 없습니다.

정답은 **원문 연락처 로그 2개, HTTP 외부 전송 2개**입니다. 이 중 `jobs/legacy_export.py`는 일부러 그림에 없는 정기 작업입니다. 그림이 완전하다는 잘못된 전제를 발견하기 위한 조건이며, 코드·설정에서는 숨기지 않았습니다. 안전 대조 함수 3개는 연락처 없는 이벤트 로그 2개와 인증서 검증을 사용하는 HTTPS 요청 1개입니다. 같은 파일 안에 위험 함수와 대조 함수가 함께 있어 파일 단위 판정만으로는 정확도를 평가할 수 없습니다.

`required_context_paths` 12개는 입력 검증, 스키마, 저장, 이벤트 변환, 소비자, 외부 전송, 그림 밖 작업을 포함합니다. 해당 경로를 선택했다는 사실과 그 내용을 올바르게 이해했다는 사실은 별도 지표입니다. 파일 수가 줄어도 정답이나 필수 경로를 놓치면 품질을 유지한 효율 개선으로 결론 내릴 수 없습니다.

인용 검증은 단순히 위험 함수의 줄 번호만 맞추는 방식보다 엄격합니다. 전체 `payload` 로그에는 프로필에서 `telephone`을 `destination`으로 전달한 줄, SMS 요청에는 HTTP 주소 정의와 요청 본문의 목적지 줄, 정기 작업에는 HTTP 주소 정의와 전화번호 조회 SQL을 추가로 요구합니다. 이는 정해진 근거 줄의 인용 검사이며, 전체 프로그램의 데이터 흐름을 형식적으로 증명하는 검증은 아닙니다.

## 검증과 재현

저장소 루트에서 실행합니다.

```bash
.venv/bin/python scripts/build_complex_architecture_fixture.py
.venv/bin/python -m pytest tests/test_complex_architecture_fixture.py -q
```

2026-10-22 기준 검증 테스트 **33개 통과**:

- 생성 결정성과 체크인된 해시·바이트·파일 목록 일치
- 모든 Python 문법 및 SQL 스키마 실행
- 전화번호 입력 → SQLite 저장 → 두 로그 → 외부 전송 → 정기 내보내기 경로를 가짜 버스·로거·전송 객체로 실행
- 세 가지 안전 대조 함수의 행동 확인
- 다른 사용자 프로필 수정 차단과 부작용 없음 확인
- 그림의 서비스 연결을 코드 설정에서 찾을 수 있음 확인
- 전화번호 전달·HTTP 주소·요청 본문·SQL 인용 요건이 실제 소스 줄과 일치하는지 확인
- 24개 서로 다른 업무 알고리즘, 이벤트 실패 시 미완료 유지, 프로필 버전 충돌

이 검증은 SQLite와 함수 호출 수준입니다. PostgreSQL 동시성, 실제 Kafka 전달, 배포 환경, 모든 서비스 API 연결, 보안·법률 준수 전체를 검증하지 않습니다. 소스는 벤치마크 입력으로만 사용하며 실행 서비스로 배포하지 않습니다.
