# 전화번호 등 특정 필드의 검토 입력 범위를 구성하는 계획기

`context.py`는 전체 소스를 LLM에 보내기 전에 로컬에서 Python/Java 파일을 인덱싱하고, 위험 항목과 연결된 검토 후보를 제한된 입력 묶음으로 구성합니다. 이미지 자체로 취약점을 판정하거나 기존 정적 분석을 생략하지 않습니다. 현재 기존 리뷰 파이프라인에 자동 연결하지 않은 재사용 가능한 모듈입니다.

```python
from architecture_agent.context import plan_context

# 실제 Git manifest에 있는 커밋 고정 파일만 읽어서 전달합니다.
sources = {"customers-service/src/OwnerResource.java": source_text}
plan = plan_context(
    sources,
    {"filePath": "customers-service/src/OwnerResource.java", "field": "telephone"},
    architecture=cached_result,       # analyze_image의 검증된 결과 또는 None
    expected_commit=current_commit,
    context_commit=diagram_commit,
    changed_paths=changed_files,
    scanner_paths=reported_files,
    max_files=12,
    max_bytes=48_000,
)
if plan["status"] == "READY":
    selected_sources = {path: sources[path] for path in plan["selectedPaths"]}
    # 호출자가 검증된 맥락과 해당 소스만 기존 리뷰 모델에 전달합니다.
```

`sources`는 저장소 상대 경로 → 파일 문자열 mapping입니다. 선택적인 `manifest=["path", ...]`를 주면 그 목록과 sources에 모두 있는 파일만 대상으로 삼습니다. 모듈은 디스크 파일을 열거나 저장소 코드를 import/실행하거나 모델을 호출하지 않습니다. 선택한 소스를 보내는 LLM에서도 소스·이미지 문자열을 지시가 아닌 데이터로 취급하는 프롬프트와 근거 검증이 필요합니다.

## 결정 과정

1. finding의 `filePath`, scanner가 보고한 경로, 변경 파일은 필수로 남깁니다. 이미지에 없더라도 제외하지 않습니다.
2. Python AST import와 Java의 실제 import·package·타입 선언/참조를 이용해 보수적인 양방향 의존 후보를 구성합니다. 기본 두 번의 연결까지만 탐색합니다. 코드에 등장하는 `telephone`, `getTelephone`, `setTelephone`, `isTelephone` 같은 정확한 식별자도 후보로 추가합니다. 주석이나 일반 문자열에만 등장하는 단어는 이 일치에 사용하지 않습니다.
3. 현재 커밋 표시와 일치하는 캐시 `ARCHITECTURE` 결과만 후보 추가·우선순위에 활용합니다. 경로가 없는 다이어그램도 `Customers Service`처럼 적힌 component label을 실제 manifest의 module 이름과 정규화 후 정확히 대조합니다. 예를 들어 실제 형제 모듈 이름이 `spring-petclinic-customers-service`, `spring-petclinic-genai-service`라면 공통 프로젝트 접두사를 제외한 `customersservice`, `genaiservice` 별칭을 만듭니다. 두 모듈 이상에 일치하면 `AMBIGUOUS`로 기록하고 임의로 고르지 않습니다.
4. `codeHints`는 manifest에 있는 파일명과 정확히 같은 경우에만 사용합니다. 경로 추측·glob 확장·디스크 접근은 하지 않습니다. 매칭 실패 경로와 component label은 결과에 남깁니다.
5. 필수 파일 다음으로 실제 필드 식별자·코드 의존 후보를 우선하고, 그 다음 다이어그램으로 추가된 모듈 후보를 배치합니다. 후보마다 선택 근거를 기록하며 파일 수/바이트 한도에서 빠진 항목도 `omittedCandidates`에 기록합니다.

같은 인덱스와 필수 경로를 쓰면서 `use_vision_context=False`로 실행하면 코드 매핑만 사용하는 비교 기준이 됩니다. 비전 방식만 유리하도록 코드 전용 경로 탐색을 생략하면 안 됩니다.

## 비용과 결과 상태

- 캐시가 없으면 `NO_CACHED_CONTEXT`이며 새 비전 추론을 자동 실행하지 않습니다. 전화번호처럼 코드만으로 좁힐 수 있는 작업에 매번 이미지 비용을 더하지 않습니다.
- 코드 후보가 이미 모든 이미지 대상 경로를 포함하면 `ALREADY_COVERED_BY_CODE_GRAPH`로 추가 비전 맥락을 생략합니다. 추정 토큰/시간으로 절감률을 만들어내지 않습니다.
- 다이어그램이 후보만 늘리고 예산 적용 후 선택 파일과 순서가 코드 전용 결과와 같으면 `NO_SELECTION_GAIN`으로 모델에 추가 비전 맥락을 넣지 않습니다. 추가되었지만 예산에서 제외된 후보는 기록에 그대로 남습니다. 이 비교는 동일한 로컬 인덱스를 재사용하며 코드 파싱이나 모델 추론을 두 번 실행하지 않습니다.
- `READY`는 필수 경로가 모두 존재하고 선택한 **소스 바이트/파일 수**가 한도 내라는 뜻입니다. 모델 프롬프트·이미지·출력 토큰을 포함한 context window 한도를 보장하지 않으므로 실제 전송 전에 별도 확인해야 합니다.
- 필수 파일 자체가 한도를 넘으면 버리지 않고 `NEEDS_BATCHING`으로 돌려줍니다. 이 결과를 그대로 단일 요청으로 보내지 말고 호출자가 분할하거나 명시적으로 한도를 변경해야 합니다.
- 필수 파일이 manifest 또는 sources에서 없으면 `MISSING_MANDATORY`입니다. `unresolvedMandatory`와 `coverage.unavailableManifestPaths`를 확인하고 소스를 보완해야 합니다.
- `decision.addedCandidateCount`, `selectedAdditionalPaths`를 통해 비전이 후보만 늘렸는지 실제 선택 파일도 늘렸는지 구별합니다. 파일 선택 계획의 로컬 계산 시간과 실제 LLM 추론 시간은 따로 측정해야 합니다.

## 정확도 범위

이 결과는 **정확한 런타임 데이터 흐름이나 전체 코드 보안 보증이 아닙니다**. Java 정적 타입 연결과 Python import는 후보 탐색입니다. 동적 dispatch, reflection, 설정 기반 DI, 코드 생성, 외부 서비스와 저장소, getter 내부 변환 등을 놓칠 수 있습니다. 같은 `telephone` 식별자라도 동일한 개인정보가 흐른다는 뜻은 아닙니다. 모듈 간 그림 화살표도 실제 요청·저장·암호화의 근거를 대신하지 않습니다.

`coverage`에는 파싱 실패, 지원하지 않는 언어, 모호한 심볼, 후보/미선택 수와 한계를 포함합니다. TypeScript 등 지원하지 않는 언어의 필수 파일도 제외하지 않지만 import/필드 탐색이 된 것처럼 표시하지 않습니다. `staleness: MATCHED`는 업로드 때 기록한 커밋 문자열이 같다는 의미로, 그림이 실제 배포 구조와 일치한다는 검증은 아닙니다. `WORKFLOW`, `UNKNOWN`, 오래됐거나 기준 커밋을 모르는 맥락은 코드 후보를 변경하지 않습니다.

```bash
.venv/bin/python -m pytest tests/test_architecture_context.py -q
```

테스트는 실제 모델 호출 없이 필수 근거 보존, Java/Python 연결, 전화번호 식별자, 이미지 경로 없는 module 매핑, 모호성·최신성·예산 초과·미선택 공개를 검증합니다.
# 코드 경로와 아키텍처 이웃을 함께 사용하는 선택기

`architecture_agent.routing.plan_routed_context(sources, finding, ...)`는 기존 `plan_context`를 변경하지 않고 확장한 별도 진입점입니다. 현재 실행 중인 코딩 Agent에 자동 연결되지는 않습니다.

- 두 비교군 모두 같은 Python/Java import·심볼 인덱스, Python dictionary 필드, SQL/설정 필드, YAML `produces`/`consumes`, 서비스 `routes`·`calls`를 사용합니다. gateway의 경로 목록은 서비스 위치 정보이며 모든 서비스가 서로 호출한다는 뜻으로 연결하지 않습니다.
- `database`가 같은 경우 필수 근거의 서비스와 직접 DB를 공유하는 모듈을 후보로 추가합니다. 이를 전이적 서비스 호출로 사용하지 않습니다. 외부 설정·실제 DB 테이블 접근 권한까지 확인한 결과가 아닙니다.
- 비전은 `use_vision_context=True`로 명시한 경우에만 사용합니다. 그림의 literal 서비스 식별자를 manifest 모듈에 매칭하고 필수 근거 모듈에서 최대 `max_hops`만큼 연결된 이웃을 후보로 추가합니다. 모호한 이름과 manifest에 없는 경로는 사용하지 않습니다.
- DB/storage/broker 구성요소를 코드 모듈로 매칭하지 않습니다. DB는 서비스 간 이동 경로가 아니며, broker를 거친 연결은 양쪽 화살표에 같은 명시적 topic이 있을 때만 인정합니다.
- 필수 근거는 파일·바이트 예산을 넘더라도 유지하고 `NEEDS_BATCHING`을 반환합니다. 선택되지 않은 후보와 이유는 `omittedCandidates`에 기록합니다. `READY`는 전달 가능한 선택 결과라는 뜻이며 전체 위험 확인 완료가 아닙니다.
- 비전 추가 후에도 선택된 파일 집합이 같으면 코드 방식의 순서를 그대로 사용하고 `decision.reason=NO_SELECTION_GAIN`, `useVisionContext=false`를 반환합니다. 호출자는 이 경우 비전 맥락을 리뷰 프롬프트에 추가하지 않습니다.
- `expected_commit`/`context_commit`를 제공하면 불일치 시 코드 방식으로 돌아갑니다. 둘 다 없는 경우 `coverage.freshness=UNVERIFIED`이며 최신성 검증 완료로 표시하면 안 됩니다.

기본 예산은 80 files / 64,000 source bytes / 3 hops이며 호출자가 명시적으로 설정할 수 있습니다. 모든 입력은 메모리 안의 manifest에서 선택되고 함수가 파일·네트워크·모델을 직접 실행하지 않습니다. `mapping`, `mappingCount`, `selectionReasons`, `coverage`를 함께 보관하여 선택 근거와 누락을 추적합니다.

