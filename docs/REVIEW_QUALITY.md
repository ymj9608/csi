# 근거 기반 정책 리뷰

기존 규칙 설명을 반복하는 대신, Finding별 정적 사실·정책 비교·미확인 사항을 분리합니다. 기존 검사는 수정하지 않으며 개선된 결과는 새 검사에 저장합니다.

## 입력과 비교

- `scripts/evidence_context.py`: Python AST만 읽습니다. 지원 클래스는 Signup, ProfileUpdate, User, CsiSignupProfile이며, 선언과 명시적인 생성자 → db.add 호출을 추적합니다. 인접한 대입과 model_dump(exclude=상수 목록) 패턴만 지원합니다. 코드 실행·전체 프로그램 데이터 흐름 분석·실제 DB 저장 검증은 수행하지 않습니다.
- 전화번호 저장 호출이 `if settings.csi_lab_mode`의 참 분기에 있으면 이를 별도 사실로 남깁니다. 확인하지 못한 경로는 UNKNOWN이며 안전하다는 의미가 아닙니다.
- business-mcp는 필드명을 정규화해 해당 검사에 저장된 정책 목록과 비교합니다. LISTED / NOT_LISTED / RESTRICTED / UNKNOWN을 구분합니다. 별도 승인 기록은 조회하지 않아 NOT_CHECKED입니다.
- 이전 버전 스캐너의 결과도 접수할 수 있습니다. 추가 코드 문맥이 없으면 마스킹된 선언에서 지원 필드명만 추출하고 클래스·저장 경로는 알 수 없음으로 남깁니다.

## LLM과 화면

LLM에는 실제 evidenceStatus, 제한된 필드·클래스 식별자, 구조화된 정적 사실, 필요한 검색 조항 발췌를 전달합니다. API 키·개인정보 값·소스 원문·파일 경로·PDF 전체는 전송하지 않습니다. 사실과 검색 문서는 지시사항으로 취급하지 않습니다.

보고서는 변경 불가능한 사실 목록, 별도 승인·런타임 등 미확인 사항, LLM의 설명 및 인용 ID를 함께 보존합니다. 존재하지 않는 Finding·사실·문서 ID와 인용 누락은 LLM_FALLBACK으로 처리합니다. 자연어 문장 전체의 정확성을 자동 증명하지는 않으며 검토가 필요합니다.

화면에는 확인된 사실과 위치, LLM이 인용한 사실/문서, 추가 확인 사항, 정책 필드별 관련 위치 수를 표시합니다. 기존 MEDIUM은 정적 규칙의 기본값임을 설명하며 정확도 확률로 표현하지 않습니다.

후속 개선에서는 읽기 도구 선택을 모델의 반복 조사 경로로 바꾸고 지시문을 `agent/prompts/`로 분리했습니다. 리뷰 입력은 인용 사전을 공유하는 최대 4개 Finding 배치로 처리하며, 입력·출력·검사별 예산을 제한합니다. 한 배치 실패로 다른 성공 리뷰를 덮어쓰지 않습니다. 선택 trace와 fallback 이유도 화면에 표시합니다. 세부 제한과 테스트는 [Agent Harness](AGENT_HARNESS.md)를 참고하세요.

## 검증 및 배포

```sh
.venv/bin/python -m pytest tests -q
cd frontend
npm run build
```

Spring Boot 테스트는 `docker compose build backend`에 포함됩니다. 정책 포함/제한/미등록/정보 부족, 별칭, 선언만 존재하는 경우, 지원 저장 경로 및 실습 분기, 증거 수준 보존, 허위 인용 거절을 테스트합니다.

로컬 통합은 `scripts/scan_repository.py`로 Lichu를 재검사합니다. 이는 LOCAL_DEMO로 기록되며 GitHub Push 검사로 표시하지 않습니다.

GitHub Runner도 새 코드 문맥을 전송하려면 CSI 저장소에 변경을 배포한 후 Lichu의 `CSI_SCANNER_REF`를 검증한 CSI 커밋의 전체 SHA로 갱신해야 합니다. Agent/MCP/Backend/Frontend 이미지도 함께 반영해야 합니다. 과거의 완료된 검사는 자동으로 재작성하지 않습니다.

## 이번 검증 기록

Python 20개, Spring 5개 테스트와 Vue 빌드가 통과했습니다. Lichu 소스를 LOCAL_DEMO로 검사한 `ea606b30-344b-4ca3-aa74-e831c9abb92f`는 COMPLETED / LLM (gpt-4.1-mini), POL-01 후보 5곳으로 완료됐습니다. User/Signup의 이름 저장 호출, 실습 분기 안의 전화번호 저장 호출, 경로를 확인하지 못한 ProfileUpdate 선언이 각각 다른 리뷰로 작성됐습니다. 사실·문서 인용과 증거 수준 보존을 확인했습니다. 코드 위치 후보 5곳은 개인정보 필드 2종으로 화면에 요약됩니다. 이는 새 GitHub Push 검증 기록이 아닙니다.
