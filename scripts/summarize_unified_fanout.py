"""Summarize retained real-model runs; missing execution is never counted as 0/8."""
import csv
import json
import sys
from pathlib import Path

ARMS={'full_code':'전체 코드','structured_text':'코드 + 구조화 텍스트','code_image':'코드 + 이미지'}
TESTS=[('test_internal_phone','내부 SMS'),('test_external_normal','정상 경로 유출 차단'),
       ('test_external_failure','실패 경로 유출 차단'),('test_store','회원 정보 보존'),
       ('test_replay','복구 기록 보존'),('test_deliveries','정상 전송 유지'),
       ('test_failure_diagnostics','장애 진단 유지'),('test_input_not_mutated','직접 호출·원본 보존')]


def summarize(out):
    results={arm:json.loads((out/arm/'result.json').read_text(encoding='utf-8')) for arm in ARMS}
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf-8'))
    best={arm:next((a['verification'] for a in r['attempts'] if a['attempt']==r.get('bestCandidate') and (a['verification'] or {}).get('total')==8),None) for arm,r in results.items()}
    rows=[]
    for arm,r in results.items():
        final=r['attempts'][-1]['verification'] if r['attempts'] else None
        rows.append({'condition':arm,'vlm_seconds':r['vlmSeconds'],'coding_seconds':round(r['coderSeconds'],3),
                     'verification_seconds':r['verificationSeconds'],'total_seconds':r['totalSeconds'],
                     'attempts':len(r['attempts']),'best_passed':best[arm]['passed'] if best[arm] else '',
                     'final_passed':final['passed'] if final and final.get('total')==8 else '', 'eight_test_contract_passed':r['status']=='PASSED',
                     'production_approval':'NOT_EVALUATED',
                     'status':r['status'],'error':r.get('error','')})
    with (out/'comparison.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]));w.writeheader();w.writerows(rows)
    text=['# 통합 VLM · 동시 전송 소규모 실험','',
          '동일한 가상 서비스(Python 4개 + 설정 JSON 1개)에 8개 고정 테스트를 적용했습니다. 코드 검색 조건은 제외했습니다.',
          '별도 보안 리뷰 모델 없이 VLM 판단 → 저장된 자연어 지시 → Coding Agent 최대 2회 → WASI 검증 흐름입니다. 정상 분석은 1회이며, 반복 감지 옵션을 켠 경우 반복 출력에 한해 VLM을 한 번 더 시도합니다.',
          '조건별 1회 실행이며, 아래 표는 최대 두 수정안 중 가장 많이 통과한 실제 검증 후보입니다. 실험의 통과 기준은 8/8이며 운영 제공 승인을 의미하지 않습니다.','',
          '| 검증 항목 | 전체 코드 | 코드 + 구조화 텍스트 | 코드 + 이미지 |','|---|---|---|---|']
    for test,label in TESTS:
        values=[{'ok':'통과','FAIL':'실패','ERROR':'실행 오류'}.get((best[a] or {}).get('cases',{}).get(test),'미실행') for a in ARMS]
        text.append('| '+label+' | '+' | '.join(values)+' |')
    scores=[str(best[a]['passed'])+'/8' if best[a] else '미실행' for a in ARMS]
    text+=['| **통과 수** | '+' | '.join(scores)+' |','',
           '| 입력 조건 | VLM 판단(초) | 코드 생성(초) | 검증(초) | 전체(초) | 생성 횟수 | 실험 기준 충족 |',
           '|---|---:|---:|---:|---:|---:|---|']
    for row in rows:
        text.append(f"| {ARMS[row['condition']]} | {row['vlm_seconds']:.1f} | {row['coding_seconds']:.1f} | {row['verification_seconds']:.1f} | {row['total_seconds']:.1f} | {row['attempts']} | {'충족' if row['eight_test_contract_passed'] else '미충족'} |")
    text+=['','## 조건과 해석','',
           f"- VLM: `{protocol['vlm']}`, Coding Agent: `{protocol['coder']}`.",
           f"- 모델 응답 시간: {'제한 없음' if protocol['timeoutPerCallSeconds'] is None else str(protocol['timeoutPerCallSeconds'])+'초'}. VLM 문맥 {protocol.get('vlmOptions',protocol['options'])['num_ctx']} 토큰, seed 42, temperature {protocol.get('vlmOptions',protocol['options'])['temperature']}.",
           '- 모든 조건에 동일한 전체 코드·설정·정책 발췌를 제공했습니다. 추가 구조 JSON/이미지만 다릅니다.',
           '- 수정 전 취약 원본 5/8, 정답 대조군 8/8. 모델에는 정답 코드와 테스트 소스를 제공하지 않았습니다.',
           '- 원래 통합 프롬프트와 한국어 응답을 복원했습니다. 추가적인 문장·단어 수 축약이나 영어 응답 강제는 없습니다. 사실 ID와 인용 ID는 서로의 필드에 들어가지 않도록 생성 schema의 허용 목록을 명시했으며, 세 조건에 동일하게 적용했습니다. WASI 격리 실험으로 Docker/API E2E와 구분합니다.',
           '- RAG는 고정된 저장소 문서 발췌입니다. 실시간 검색 품질이나 법적 준수 여부를 평가하지 않습니다.',
           '- 사전 실행의 600/900초 시간 초과, 축약·영어 응답 설정, 사실/인용 ID 혼동으로 차단된 실행은 최종 비교와 분리했습니다. 인접 디렉터리의 ABORTED.json과 원시 응답에 사유를 보존했습니다. 최종 세 조건은 동일한 설정으로 새로 실행했습니다.',
           '- 기존 16조건 결과와 실행 프롬프트·코드 제공 방식·예산이 달라 직접적인 개선 전후 수치 비교가 불가능합니다.',
           '- 동일 사례 1회 결과로 Vision 일반 성능이나 통계적 우위를 주장할 수 없습니다.','', '## VLM 지시 및 실패 기록','']
    if protocol.get('compactInput'):
        index=text.index('## VLM 지시 및 실패 기록')
        text[index:index]=['입력 정리: 중복된 task/codeContext와 JSON 공백만 제거했습니다. 전체 소스·설정·이미지·문서 발췌·동작 요구사항은 보존했습니다. KV 캐시 방식과 문맥 용량은 바꾸지 않았습니다.','']
    if protocol.get('staged'):
        text=[line.replace('정상 분석은 1회이며, 반복 감지 옵션을 켠 경우 반복 출력에 한해 VLM을 한 번 더 시도합니다.', '동일한 VLM의 구조·보안·지시 3단계를 실행하며 실패한 단계부터 한 번 재개합니다.') for line in text]
        text=[line for line in text if not line.startswith('- 원래 통합 프롬프트') and not line.startswith('- 사전 실행의')]
        index=text.index('## VLM 지시 및 실패 기록')
        text[index:index]=['단계 분리: 운영과 동일한 LangGraph·프롬프트·검증기를 사용합니다. 이미지/구조 입력은 1단계, 정책·RAG는 2단계, 자연어 지시는 3단계에서 처리합니다. 단계별 출력 한도와 반복 억제 옵션은 protocol.json에 기록했습니다. 새 구조·프롬프트·파라미터를 함께 적용했으므로 단일 변경의 인과 효과로 해석하지 않습니다.','']
    if protocol.get('repetitionGuard') and not protocol.get('staged'):
        index=text.index('## VLM 지시 및 실패 기록')
        text[index:index]=['반복 제어: 긴 문자열의 연속 3회 반복을 감지하면 해당 응답을 실패 처리하고, 원문을 보존한 뒤 repeat_penalty=1.1 / repeat_last_n=256으로 한 번 재시도합니다. 기본 프롬프트·입력·출력 상한은 그대로입니다. 세 조건에 같은 규칙을 적용했습니다.','']
    for arm,r in results.items():
        text.append('### '+ARMS[arm]);text.append('')
        artifact='vlm-stage-calls.json' if protocol.get('staged') else 'assessment-partial.txt'
        text.append(f'[VLM 실제 출력 기록]({arm}/{artifact}) · [실행 결과]({arm}/result.json)')
        text.append('')
        for assessment in r.get('assessmentAttempts',[]):
            text.append(f"- VLM {assessment['call']}: {assessment['status']} · {assessment['seconds']:.1f}초"+((' · '+assessment['error']) if assessment.get('error') else ''))
            if assessment['call']!='assessment':text.append(f"  [단계/재시도 출력]({arm}/{assessment['call']}-partial.txt)")
        instruction=out/arm/'instruction.txt'
        if instruction.exists():text.append(instruction.read_text(encoding='utf-8').strip())
        else:
            text.append('Coding Agent에 전달되지 않음: '+r.get('error','결과 없음'))
            assessment=out/arm/'assessment.json'
            if assessment.exists():
                raw=json.loads(assessment.read_text(encoding='utf-8')).get('answer',{})
                for item in raw.get('instructions',[]):
                    text.append('\n검증 미통과 원시 지시(실행하지 않음): '+item.get('text',''))
        for a in r['attempts']:
            v=a['verification']
            if v and v.get('total')==8:
                detail=f"{v['passed']}/8 통과"
            elif v:
                detail='검증 완료 안 됨 (로딩·실행 오류; 0/8로 집계하지 않음)'
                lines=v.get('log','').strip().splitlines()
                if lines:detail+=': '+lines[-1]
            else:detail='검증 미실행: '+a.get('error','후보 없음')
            text.append(f"- {a['attempt']}차: "+detail)
        text.append('')
    all_pass=all(r['status']=='PASSED' for r in results.values())
    if all_pass:text+=['이번 실행에서는 세 입력 조건 모두 필수 검증을 통과했습니다. 이 사례에서 이미지 추가에 따른 최종 통과율 향상은 관찰하지 못했습니다.']
    elif not any(best.values()):text+=['세 조건 모두 8개 테스트의 검증 결과를 확보하지 못했습니다. 이 실행으로 Vision의 보안 수정 성과를 비교할 수 없습니다.']
    (out/'RESULTS_KO.md').write_text('\n'.join(text)+'\n',encoding='utf-8')


if __name__=='__main__':summarize(Path(sys.argv[1]))
