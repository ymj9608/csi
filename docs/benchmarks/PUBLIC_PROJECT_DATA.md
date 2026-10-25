# 공개 Spring 프로젝트 비교 데이터와 판정 기준

## 원본과 범위

공식 Spring Petclinic 조직의 [spring-petclinic-microservices](https://github.com/spring-petclinic/spring-petclinic-microservices/tree/1d76b00d683e86b62867a6bf59530f8ab301244f)를 사용합니다. 고정 커밋은 `1d76b00d683e86b62867a6bf59530f8ab301244f`, 라이선스는 [Apache-2.0](https://github.com/spring-petclinic/spring-petclinic-microservices/blob/1d76b00d683e86b62867a6bf59530f8ab301244f/LICENSE)입니다. 원본 코드는 `.runtime/architecture-benchmark/public/spring-petclinic-microservices`에만 복제하며 CSI에 소스를 재배포하지 않습니다.

이 프로젝트는 실제 유지되는 **교육용 마이크로서비스 예제**입니다. 실제 기업의 운영 저장소로 표현하지 않습니다. API Gateway, Customers, Visits, Vets, GenAI, Config, Discovery, Admin의 Maven 모듈 8개가 있으며 임의로 서비스·코드·반복 데이터를 추가하지 않았습니다.

| 측정 대상 | 파일 | 원본 bytes | 줄 |
| --- | ---: | ---: | ---: |
| Java·SQL·YAML·XML·properties 전체(테스트 포함) | 111 | 174,891 | 5,191 |
| 같은 범위에서 테스트 제외 | 95 | 154,756 | 4,566 |
| Java만(테스트 포함) | 64 | 105,632 | 3,235 |
| 운영 Java 소스만 | 53 | 86,604 | 2,674 |

전체 비교의 고정 입력은 **첫 번째 행의 111개 파일**입니다. 이를 저장소의 모든 파일이라고 표현하지 않습니다. UI JavaScript/HTML, 이미지, 폰트, 스타일, `.github`, `.mvn`, 벡터 데이터, 셸 스크립트는 제외했습니다. Bootstrap과 합쳐진 생성 CSS를 넣어 전체 코드 비용을 부풀리지 않았습니다. 정확한 파일별 SHA-256과 집계 해시는 [public-project-manifest.json](public-project-manifest.json)에 있습니다. bytes는 토큰 수가 아닙니다.

이 스냅샷은 [원본 DB 설명](https://github.com/spring-petclinic/spring-petclinic-microservices/blob/1d76b00d683e86b62867a6bf59530f8ab301244f/README.md#database-configuration)에 따라 **HSQLDB 기본값과 MySQL 선택 프로필**을 제공합니다. PostgreSQL 환경을 검증한 실험이라고 말할 수 없습니다. 런타임 설정은 별도 `spring-petclinic-microservices-config` 저장소에서 받아오며 그 저장소는 이번 입력에 포함하지 않았습니다.

## 어떤 이미지로 비교하는가

측정에는 저장소에 원래 있던 [microservices-architecture-diagram.jpg](https://github.com/spring-petclinic/spring-petclinic-microservices/blob/1d76b00d683e86b62867a6bf59530f8ab301244f/docs/microservices-architecture-diagram.jpg)를 그대로 사용합니다. 코드 경로나 정답을 그림에 덧붙이지 않았습니다. 이 그림은 서비스와 DB, GenAI 호출 관계를 나타내지만 메서드·필드·로그 처리를 설명하지 않습니다. 그림의 `pets-service` 표기는 실제 모듈/라우팅의 `visits-service`와 다릅니다. 이런 불일치도 이미지 인식 결과를 저장소 목록과 대조해야 하는 이유입니다.

`public-architecture.svg/png`는 팀원 이해를 돕기 위해 소스를 읽고 새로 만든 **설명용 그림**입니다. 모듈 경로와 전화번호 데이터 역할이 포함되어 있어 검색에 유리하므로 실제 원본 이미지 비교 수치에는 사용하지 않습니다.

## 전화번호 변경 영향과 보안 검토 과제

과제는 `Owner.telephone` 처리 변경 시 입력 검증 → DTO/매핑 → 저장 → API 응답 → 로그 → 다른 서비스 소비 경로를 찾고, 근거가 있는 보완 방향과 확인할 내용을 제안하는 것입니다. 이미 존재하는 코드를 검토하며 인위적 취약점을 삽입하지 않습니다.

검토자 기준은 [public-telephone-case.json](public-telephone-case.json)에 있습니다. 아래 두 항목은 고정 커밋의 코드에서 추적한 **로그 노출 후보**이며, 법률 위반 확정이나 실제 운영 데이터 유출 확인을 뜻하지 않습니다.

1. Customers의 `OwnerResource.updateOwner()` 89행이 `Owner` 객체를 기록합니다. 같은 객체의 `Owner.toString()` 95행이 전화번호를 문자열에 포함합니다. 두 파일을 함께 읽어야 근거가 완성됩니다.
2. GenAI의 `PetclinicTools.addOwnerToPetclinic()` 49행이 `OwnerRequest` record를 기록합니다. 같은 파일 76~81행의 record에는 전화번호가 있습니다. Customers만 고르면 이 별도 입력·로그 경로를 놓칠 수 있습니다.

추가 맥락 기준에는 요청 DTO, 매퍼, JPA 엔티티·저장소, 두 DB 스키마, Gateway·GenAI 응답 DTO, AI 데이터 제공자·도구 등록이 포함됩니다. Vets·Visits·Discovery의 지정 파일은 이 전화번호 필드 처리 여부에 대한 좁은 대조군입니다. 방문 기록 등의 다른 개인정보 위험이 없다는 뜻은 아닙니다.

이 정답 파일과 manifest의 `reviewer_only_reference_facts`는 **모델에게 제공하지 않습니다**. 후보 위치 일치, 실제 행·인용 일치, 교차 파일 근거 연결, 필요한 맥락 회수율을 구분해서 확인합니다. 반환된 추천 코드가 실제로 동작하는지·회귀가 없는지는 별도의 수정 및 테스트 단계가 필요합니다.

## 재현

CSI 루트에서 원본을 내려받고 고정 커밋을 선택합니다.

```bash
git clone https://github.com/spring-petclinic/spring-petclinic-microservices.git \
  .runtime/architecture-benchmark/public/spring-petclinic-microservices
git -C .runtime/architecture-benchmark/public/spring-petclinic-microservices \
  checkout --detach 1d76b00d683e86b62867a6bf59530f8ab301244f
.venv/bin/python scripts/build_public_architecture.py
# 설명용 PNG 재생성: frontend Playwright와 Chrome 필요
.venv/bin/python scripts/build_public_architecture.py --render
```

생성기는 커밋이 다르면 중단하고, `git show`로 고정 소스와 행 위치를 검증합니다. 모델 추론이나 대상 애플리케이션 실행·수정은 하지 않습니다. 실제 비교 latency·토큰은 별도 실행 로그의 값이며, 이 데이터 설명서가 성능 향상을 미리 보장하지 않습니다.
