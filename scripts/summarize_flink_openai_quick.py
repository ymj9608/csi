"""Summarize actual quick-run artifacts without calling models or changing grades."""
import json
from pathlib import Path
from benchmark_flink_openai_quick import OUT
from flink_patch_protocol import ARMS
from flink_patch_validation import SECURITY_TESTS


def cost(call):
    u=call['usage']; cached=u.get('input_tokens_details',{}).get('cached_tokens',0)
    return ((u['input_tokens']-cached)*.75+cached*.075+u['output_tokens']*4.5)/1e6


def main(out=OUT):
    prior=out.parent/'patch-v2-run'
    image=json.loads((prior/'calls/architecture.json').read_text())
    cache=json.loads((out/'architecture-cache.json').read_text())
    rows=[]
    for arm in ARMS:
        r=json.loads((out/arm/'result.json').read_text())
        c=json.loads((out/'calls'/f'{arm}.json').read_text())
        plan=json.loads((out/arm/'selection.json').read_text())
        v=r.get('verification',{}); cases=v.get('cases',{})
        security=sum(s=='PASSED' and k.split('#')[-1] in SECURITY_TESTS for k,s in cases.items())
        functional=sum(s=='PASSED' and k.split('#')[-1] not in SECURITY_TESTS for k,s in cases.items())
        rows.append({**r,'files':len(plan['selectedPaths']),'inputTokens':c['inputTokens'],
            'outputTokens':c['outputTokens'],'cachedInputTokens':c['usage'].get('input_tokens_details',{}).get('cached_tokens',0),
            'securityPassed':security if cases else None,'functionalPassed':functional if cases else None,
            'failedTests':[k for k,s in cases.items() if s=='FAILED'],
            'apiMs':c['wallMs'],'validationMs':v.get('wallMs'),
            'firstUseModelMs':c['wallMs']+(cache['setupWallMs'] if arm=='vision_index' else 0),
            'apiCostUsd':cost(c)+(cost(image) if arm=='vision_index' else 0)})
    labels=['비전 없음·전체 범위','비전 없음·코드 검색','비전 있음·검색+그림']
    def line(label, values):return '| '+label+' | '+' | '.join(map(str,values))+' |'
    report=['# OpenAI 빠른 비교: 실제 코드 수정안', '',
        '후속: [컴파일 오류 한 곳 교정 후 재검증](compile-repair/RESULTS.md). 아래는 교정 전 AI 첫 생성 결과로 보존합니다.', '',
        '2026-10-23 · OpenAI `gpt-5.4-mini-2026-03-17` · 각 조건 1회 · 동일 61개 테스트.', '',
        '이번 실행에서 비전 조건의 보안 테스트 통과 수는 전체 입력의 4/5에서 5/5로 늘었습니다. '
        '하지만 안전한 기존 로그 계약이 깨져 **전체 품질 통과는 세 조건 모두 0/1**입니다. '
        '따라서 아직 “품질 저하 없이 효율 개선”을 입증한 결과는 아닙니다.', '',
        '시간·메모리 제한 요청에 따라 로컬 반복 실험을 중단하고 별도 파일에 기록한 파일럿입니다. '
        '각 조건에 같은 OpenAI 모델을 사용해 직접 패치를 한 번 생성했습니다. '
        '원래 로컬 모델의 배치 검토 루프와 달라 모델 간 속도 배수 비교로 해석하지 않습니다.', '',
        line('항목',labels),line('---',['---:']*3),
        line('선택 파일',[r['files'] for r in rows]),
        line('보안 테스트 / 5',[f"{r['securityPassed']}/5" if r['securityPassed'] is not None else '컴파일 실패·미실행' for r in rows]),
        line('기능·로그 계약 테스트 / 56',[f"{r['functionalPassed']}/56" if r['functionalPassed'] is not None else '미실행' for r in rows]),
        line('전체 품질 통과',[f"{int(r['accepted'])}/1" for r in rows]),
        line('코드 생성 API 시간(초)',[f"{r['apiMs']/1000:.2f}" for r in rows]),
        line('최초 그림 분석 포함 모델 시간(초)',[f"{r['firstUseModelMs']/1000:.2f}" for r in rows]),
        line('격리 빌드·테스트(초)',[f"{r['validationMs']/1000:.2f}" if r['validationMs'] else '미실행' for r in rows]),
        line('입력 토큰',[f"{r['inputTokens']:,}" for r in rows]),
        line('그중 제공자 캐시 입력 토큰',[f"{r['cachedInputTokens']:,}" for r in rows]),
        line('출력 토큰',[f"{r['outputTokens']:,}" for r in rows]),
        line('추정 API 비용(USD)',[f"${r['apiCostUsd']:.5f}" for r in rows]),'',
        '비전 최초 분석은 이전에 실제 실행한 입력 1,115 / 출력 1,229토큰, 약 9.31초를 재사용했습니다. '
        '위 표의 비전 비용에는 이 한 번의 약 $0.00637을 포함합니다. 새 코드 API 호출은 총 3회이며 그림 비용을 다시 청구한 것으로 합산하지 않습니다. '
        '최초 그림 포함 입력은 비전 코드 입력에 1,115토큰을 더한 값입니다.', '',
        '## 해석과 실패 이유', '',
        f"전체 입력 대비 비전 조건의 코드 입력은 {100*(1-rows[2]['inputTokens']/rows[0]['inputTokens']):.1f}% 감소했고, "
        f"코드 API 시간은 {100*(1-rows[2]['apiMs']/rows[0]['apiMs']):.1f}% 짧았습니다. "
        '이 감소에는 코드 검색의 효과가 포함됩니다. 코드 검색만 한 경우와 비교하면 선택 파일은 동일한 9개이며 비전 설명 때문에 입력이 오히려 증가했습니다. '
        '최초 그림 분석까지 포함하면 비전 모델 시간은 15.10초로 전체 입력의 8.21초보다 깁니다.', '',
        '- 전체 입력: 키스토어 비밀번호 노출을 놓쳤습니다. 안전한 바이트 수 로그는 유지했으나 메시지를 바꿔 고정 로그 계약 테스트도 실패했습니다. 이를 로그 자체를 없앤 것과 혼동하면 안 됩니다.',
        '- 코드 검색: 존재하지 않는 `SecurityOptions.isRestSSLHostnameVerificationEnabled`를 호출해 컴파일되지 않았습니다. 보안 테스트 점수는 0점이 아니라 미측정입니다.',
        '- 비전: 보안 결과와 별개로 기존 INFO 수준의 `[REDACTED]` 진단 로그를 DEBUG 이벤트로 바꿨습니다. 안전한 기존 로그 계약 보존 여부는 고정 테스트로 판정합니다.', '',
        '통과 여부는 모든 보안·기능·로그 계약을 만족해야 합니다. 빠르게 실패한 경로를 효율 개선으로 보지 않습니다. '
        '단일 실행, 고정 순서, 서로 다른 제공자 캐시 적중량이므로 작은 지연 차이를 비전의 순수 효과나 통계적 성능 향상으로 확정하지 않습니다.', '',
        '그림은 Flink 공식 일반 구조도여서 S3·TLS 파일 경로를 명시하지 않습니다. '
        '검색 결과를 보존하는 비전 경로에 추가 맥락을 전달한 실험이며 전체 저장소 자동 탐색이나 운영 CSI 종단간 적용의 검증은 아닙니다.', '',
        '## 데이터·메모리·재현', '',
        '- 고정 커밋 `8d01380ff5bf9892462ef9808b1b56fd9723f54d`, 모델 선언 범위 Java 20개·173,112 bytes. 합성 결함 5개를 주입했으며 upstream 취약점 주장과 구분합니다.',
        '- 새 소스·의존성 복사본, 네트워크 차단 Docker, 4GiB 메모리, swap 금지, 2 CPU, Maven heap 1536MiB. 검증은 순차 실행하고 로컬 LLM은 올리지 않았습니다.',
        '- 검증기 교정은 기존 주입본 5개 실패·참조본 61개 통과 기록을 사용했습니다. 이번에는 같은 fixture와 테스트에 더 낮은 자원 한도를 사용했습니다.',
        '- 모델 시간은 실제 HTTP 응답 시간입니다. 빌드 시간은 소스·캐시 복사와 검증을 포함합니다. 도구 개발·환경 설치·사전 교정은 제외합니다. 세 후보를 먼저 생성하고 순서대로 검증했으므로 전체 사용자 대기 시간을 단순한 모델 지연으로 표시하지 않았습니다.',
        '- [고정 프로토콜](protocol.json), [원시 결과](measurements.jsonl), [상세 비교](comparison.json), 각 조건 폴더의 `candidate.patch` 및 `validation/maven.log`.',
        '- [데이터 수집·팀원 설명](../../../PERCEPTION_REASONING.md). 재집계: `.venv/bin/python scripts/summarize_flink_openai_quick.py`.',
        '- 비용은 실제 usage와 [공식 표준 가격](https://developers.openai.com/api/docs/models/gpt-5.4-mini)을 사용한 추정입니다. 장비·전력·세금·환율 비용은 포함하지 않았습니다.', '']
    (out/'RESULTS.md').write_text('\n'.join(report))
    (out/'comparison.json').write_text(json.dumps({'rows':rows,'visionSetupCostUsd':cost(image),
        'statisticalClaim':False,'allQualityGatesPassed':all(r['accepted'] for r in rows)},ensure_ascii=False,indent=2)+'\n')
    print(json.dumps([{k:r[k] for k in ('arm','status','securityPassed','functionalPassed','apiMs','inputTokens','apiCostUsd')} for r in rows]))


if __name__=='__main__':main()
