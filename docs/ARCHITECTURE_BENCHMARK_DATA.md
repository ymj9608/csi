# 아키텍처 비교 실험 데이터

## 합성 데이터의 출처와 목적

`tests/fixtures/architecture_benchmark/`는 **Lichu의 실제 코드 복사본이 아닌 합성 실험 데이터**입니다. Lichu의 FastAPI 라우트 → 서비스 → 저장소 → DB 분리, 회원가입·로그인, 사내 라이선스 신청·승인 도메인을 참고해 새로 작성했습니다. 실제 계정·개인정보·설정·비밀키를 포함하지 않습니다. 합성 저장소는 별도 HTTP 서버 없이 Python 표준 라이브러리와 SQLite 메모리 DB로 검증합니다.

| 구성 | 내용 |
| --- | --- |
| `repository/` | 모델에게 전달하는 Python 소스 15개, 11,731 bytes |
| `architecture.svg`, `architecture.png` | 같은 합성 저장소의 웹 애플리케이션 구조, 구성요소·경로·데이터 흐름 |
| `ground_truth.json` | 사람이 정의한 양성 4개·음성 대조군 4개의 경로·함수·행 번호·판정 근거 |
| `manifest.json` | 파일별 SHA-256, 정확한 바이트 수·행 수·데이터셋 전체 해시 |
| `verify_fixture.py` | 양성·음성 동작과 해시를 확인하는 결정적 검사 12개 |

전체 소스 해시: `87314cfbb54cf11772cc3a55671ad13861fcfc85178215680dcc64d7eee1982f`.

## 측정할 정답과 누락 조건

| ID | 정답 | 구현 위치 |
| --- | --- | --- |
| V1 | 비밀번호에 빠른 SHA-256 + 공통 고정 salt 사용 후 DB 저장 | `backend/app/core/passwords.py` |
| V2 | 회원가입 비밀번호 원문과 이메일 전체를 로그에 기록 | `backend/app/core/audit.py` |
| V3 | 디렉터리 검색어를 SQL 문자열에 직접 삽입 | `backend/app/repositories/users.py` |
| V4 | 별도 작업이 이름·이메일·전화번호를 외부 HTTP로 전송 | `backend/jobs/directory_sync.py` |

V4는 **의도적으로 다이어그램에서 제외**했습니다. 다이어그램에는 웹 애플리케이션 관점이며 모든 실행 작업을 포함하지 않는다고 명시했습니다. 문서 밖의 위험을 놓치는지를 검사하기 위한 조건이며, 그림에 없는 코드를 안전하다고 간주하면 안 됩니다. 정답이나 취약 알고리즘은 그림에 쓰지 않았습니다.

음성 대조군은 파일 체크섬용 SHA-256, 비밀번호·연락처가 없는 이벤트 로그, 바인딩된 SQL 검색어, 임의 salt와 반복 횟수가 있는 PBKDF2입니다. 이는 **해당 취약 유형의 음성 대조군**이며 프로젝트 전체가 안전하다는 의미는 아닙니다. 예를 들어 이벤트 식별자에도 접근 제어와 보존 기간 정책이 필요할 수 있습니다.

`ground_truth.json`, 이 설명서, 검증 스크립트, 파일별 정답은 **모델 프롬프트에 넣지 않습니다**. 모델에 제공할 입력은 `repository/`의 소스 또는 `architecture.png` 및 선택된 소스로 제한합니다.

## 재현 방법

CSI 루트에서 실행합니다.

```bash
.venv/bin/python scripts/build_architecture_fixture.py
# PNG까지 다시 만들려면 frontend 의존성과 Chrome이 필요합니다.
.venv/bin/python scripts/build_architecture_fixture.py --render
.venv/bin/python tests/fixtures/architecture_benchmark/verify_fixture.py
```

생성기는 동일한 소스·정답·SVG·manifest를 생성합니다. PNG는 로컬 Chrome/Playwright로 SVG를 렌더링하며 외부 이미지 생성 API를 사용하지 않습니다. 렌더러 버전에 따라 PNG 바이트가 달라질 수 있으므로 원본 SVG 해시도 저장합니다. 실제 모델 실행의 토큰·시간·탐지 결과는 별도 벤치마크 로그를 확인해야 합니다. 소스 바이트 수를 모델 토큰으로 간주하지 않습니다.

## 해석의 범위

작은 저장소 한 종류에서 네 개의 알려진 위험과 네 개의 대조군을 측정한 결과입니다. Lichu 실제 코드의 취약점 진단 결과, 법률 준수 인증, 복잡한 대규모 저장소의 일반적 성능 수치로 확대 해석하면 안 됩니다. 전체 코드 방식도 모델 입력 한도를 넘으면 청크 분할과 집계 비용을 함께 기록해야 합니다. 비전 방식은 이미지 해석 비용을 최초 요청에 포함하고, 이미지 내용·모델·프롬프트 버전이 같아 캐시를 재사용한 경우를 따로 기록해야 합니다.

## 실제 Lichu 보조 실험용 구조 그림

`docs/benchmarks/lichu-architecture.png`는 Lichu 커밋 `95345dbd8ba45fe77ea8cd926c84e40e4d16f83a`의 소스를 읽어 **이번 실험용으로 사람이 요약한 그림**입니다. 사용자가 첨부한 서비스 업무 흐름 그림도, 기존 Lichu 설계 문서도 아닙니다. 프론트엔드 API 클라이언트·인증 상태, FastAPI 라우트·스키마, 역할 확인, 서비스, 조건부 회원가입 실습 모듈, 저장소·모델·DB 세션을 나타냅니다.

`lichu-architecture-manifest.json`에는 구조를 요약할 때 참조한 14개 소스의 커밋 기준 해시를 기록했습니다. 실제 소스 내용이나 비밀 값은 이 폴더에 복사하지 않았습니다. 테스트·마이그레이션·배포 구성·외부 서비스는 생략했습니다. 경로를 그림에 명시했기 때문에, 경로가 없는 기존 운영 다이어그램보다 검색에 유리한 조건입니다. 따라서 그림의 경로 매핑 성능을 일반화해서는 안 됩니다.

```bash
.venv/bin/python scripts/build_lichu_architecture.py --repository ../Lichu --render
```

소스 커밋이 달라지면 생성기가 중단됩니다. 실제 코드를 다시 검토한 다음 매핑과 고정 커밋을 갱신해야 합니다. 비교 실행에서 이 그림의 수동 작성 시간은 모델 latency에 포함되지 않으므로 별도 준비 비용으로 밝혀야 합니다. Lichu 보조 실험에서 합성 정답 V1~V4를 그대로 적용해 정확도를 계산하면 안 됩니다.
