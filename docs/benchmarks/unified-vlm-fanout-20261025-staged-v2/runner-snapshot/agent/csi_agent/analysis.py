"""Evidence-bound report generation; LLM cannot add findings or reference IDs."""
import json,os,re
import httpx
from .harness import Ledger, completion, prompt, token_bound, MAX_INPUT_TOKENS, BudgetExceeded, TruncatedOutput
from pydantic import BaseModel,ConfigDict,Field
from mcp_servers.policy_review import compare_findings
RULES={
 'SEC-01':('T1 · 오프라인 비밀번호 추측','평문 비밀번호 저장 후보가 탐지되었습니다. 저장소에 원문이 남으면 노출 시 비밀번호가 직접 드러날 수 있습니다.','실제 저장 호출과 encode 적용 경로를 확인하고 사내 승인된 비밀번호 해시를 사용하세요.'),
 'SEC-02':('T1 · 오프라인 비밀번호 추측','비밀번호로 명명된 값에 빠른 범용 해시를 적용한 후보입니다. 저장에 사용된다면 유출 후 추측 비용이 낮아질 수 있습니다.','체크섬 용도인지 구분하고, 비밀번호 저장 경로에는 Argon2id 또는 정책에 맞는 bcrypt를 사용하세요.'),
 'SEC-03':('T2 · 사전 계산 결과 재사용','고정 문자열 Salt 후보가 발견되었습니다. 사용자별 고유 Salt가 없으면 동일 입력의 계산 결과가 재사용될 수 있습니다.','비밀번호 해싱 라이브러리가 생성하는 사용자별 무작위 Salt를 사용하세요. Salt 변수의 실제 사용 경로를 검토하세요.'),
 'SEC-04':('T1 · 오프라인 비밀번호 추측','bcrypt 설정의 비용이 사내 정책 기준에 미달하는 후보입니다. 비용이 낮으면 해시 추측 비용도 낮아질 수 있습니다.','사내 POL-04.1 최소 비용 12와 현재 부하를 검증하고 재해시 이관 계획을 수립하세요.'),
 'SEC-05':('T3 · 로그를 통한 비밀정보 유출','민감정보로 명명된 값이 로그 인자로 전달됩니다. 원문이라면 로그 접근자가 인증 비밀이나 개인정보를 얻을 수 있습니다.','민감한 로그 인자를 제거하고 이벤트 유형·결과·trace ID로 대체하세요. 마스킹 함수와 인자의 실제 내용을 확인하세요.'),
 'POL-01':('T4 · 미승인 개인정보 처리','승인된 개인정보 목록과 불일치할 수 있는 필드가 발견되었습니다. 필드 존재만으로 수집이나 위법을 판단할 수 없습니다.','DTO → Controller → Service → 저장·전송 경로와 수집 목적을 확인하고 필요한 정책 변경은 CPO의 별도 승인을 받으세요.')}
EXAMPLE='// 설명용 수정 예시 — 원본 패치가 아닙니다.\nPasswordEncoder encoder = new BCryptPasswordEncoder(12);\nString passwordHash = encoder.encode(rawPassword);'
PYTHON_EXAMPLE='# 설명용 수정 예시 — 원본 패치가 아닙니다.\nimport bcrypt\npassword_hash = bcrypt.hashpw(raw_password.encode(), bcrypt.gensalt(rounds=12)).decode()'
class LLMItem(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str
    red:str=Field(max_length=1600)
    blue:str=Field(max_length=1600)
    remediation:str=Field(max_length=1600)
    citationIds:list[str]=Field(max_length=8)
    factIds:list[str]=Field(min_length=1,max_length=12)
class LLMReport(BaseModel):
    model_config=ConfigDict(extra='forbid')
    findings:list[LLMItem]

def base_report(findings, refs, policy, comparison=None):
    comparisons = {x['findingId']: x for x in (comparison or compare_findings(findings, policy)).get('items', [])}
    report = []
    for f in findings:
        threat, red, remedy = RULES[f['ruleId']]
        citations = refs.get(f['ruleId'], [])
        facts = [{'id': 'F1', 'text': '정적 규칙 ' + f['ruleId'] + ' 패턴이 탐지됨. 증거 수준: ' + f.get('evidenceStatus', 'UNKNOWN'),
                  'filePath': f.get('filePath'), 'line': f.get('startLine')}]
        unknowns = ['실제 런타임 처리 및 운영 설정은 검증하지 않았습니다.']
        blue = '정적 분석 후보입니다. 실제 처리 경로와 설정을 확인해야 하며 법률 위반을 확정하지 않습니다.'
        review = comparisons.get(f['id'])
        if review:
            field, entity, status = review['field'] or '식별되지 않은 필드', review['entity'], review['inventoryStatus']
            label = {'LISTED': '정책 승인 목록에 포함', 'NOT_LISTED': '정책 승인 목록에 없음',
                     'RESTRICTED': '정책의 제한 항목에 해당', 'UNKNOWN': '정책 대조 불가'}[status]
            facts.append({'id': 'F2', 'text': f'{entity}.{field}: {label}.', 'section': review['section'], 'page': review['page']})
            for signal in review['signals']:
                facts.append({'id': f'F{len(facts)+1}',
                    'text': f"{signal['source']}.{field} 값을 {signal['target']} 생성자에 전달하여 db.add에 넘기는 정적 코드가 있음. " +
                            ('이 저장 호출은 settings.csi_lab_mode 조건의 참 분기 안에 있음.' if signal['labOnly'] else '이 저장 호출을 감싸는 실습 전용 조건은 확인되지 않음.'),
                    'filePath': signal['filePath'], 'line': signal['line']})
            unknowns += ['별도 수집 승인 기록과 실제 수집 목적은 확인하지 않았습니다.',
                         '지원 범위는 일부 Pydantic·SQLAlchemy 패턴입니다. 함수 간 전체 데이터 흐름을 증명하지 않습니다.']
            if not review['signals']:
                unknowns.append('이 선언과 연결된 저장 호출을 지원 패턴에서 찾지 못했습니다. 저장하지 않는다는 뜻은 아닙니다.')
            red = f'{entity}.{field}은(는) {label} 상태입니다. ' + ('저장 호출 코드가 연결되어 수집 목적과 승인 조건 확인이 필요합니다.' if review['signals'] else '현재 근거는 필드 선언이며 저장·전송 경로 확인이 필요합니다.')
            red += ' 필드 존재만으로 수집이나 위법을 판단할 수 없습니다.'
            blue = f"적용 정책 {review['policyVersion']}의 {review['section']} / {review['page']}페이지와 비교했습니다. " + ('승인 목록에 있어도 목적·로그·접근 조건 충족 여부는 별도 검토해야 합니다.' if status == 'LISTED' else '목록과의 차이는 별도 승인 부재 또는 법률 위반의 증명이 아닙니다.')
            remedy = f'{entity}.{field}의 수집 목적·보유기간·별도 승인 기록을 확인하세요. ' + ('목록에 포함된 목적과 저장·접근 조건을 검증하세요.' if status == 'LISTED' else '필수성이 없으면 입력·저장 경로에서 제거하고, 필요하다면 승인 절차에 따라 정책을 갱신하세요.')
            if any(s['labOnly'] for s in review['signals']):
                remedy += ' 실습 전용 저장 경로의 운영 비활성화와 합성 데이터 검증을 별도로 확인하세요.'
        if not citations:
            unknowns.append('검색된 정책 근거가 없어 정책 판단을 보류합니다.')
        report.append({'id': f['id'], 'analysis': {'threatProfile': threat, 'red': red, 'blue': blue,
            'remediation': remedy, 'references': citations, 'mode': 'RULE_BASED',
            'example': (PYTHON_EXAMPLE if f.get('filePath', '').endswith('.py') else EXAMPLE) if f['ruleId'] in {'SEC-01','SEC-02','SEC-04'} else '',
            'defenseAssessment': 'REVIEW_REQUIRED', 'facts': facts, 'unknowns': unknowns,
            'policyComparison': review, 'evidenceStatus': f.get('evidenceStatus', 'UNKNOWN'),
            'confidenceBasis': '정적 규칙의 기본 신뢰 수준이며 확률이나 LLM 점수가 아닙니다.',
            'groupKey': review['field'] if review and review['field'] else f['id'],
            'citedFactIds': [], 'citedReferenceIds': []}})
    return report


def llm_context(report, findings):
    by_id = {f['id']: f for f in findings}
    contexts = []
    for r in report:
        a = r['analysis']; f = by_id[r['id']]
        contexts.append({'id': r['id'], 'ruleId': f['ruleId'],
            'evidenceStatus': f.get('evidenceStatus', 'UNKNOWN'),
            'facts': [{'id': x['id'], 'text': x['text']} for x in a['facts']],
            'unknowns': a['unknowns'], 'red': a['red'], 'blue': a['blue'], 'remediation': a['remediation'],
            'citations': [{'id': x['chunkId'], 'section': x['sectionId'], 'title': x['sectionTitle'],
                           'documentType': x['documentType'], 'page': x['pageNumber'],
                           'excerpt': x['content'][:1800]} for x in a['references']]})
    return contexts


def review_messages(items, findings, excerpt_limit=900):
    """Deduplicate shared RAG chunks while retaining per-finding allowed citation IDs."""
    context = llm_context(items, findings)
    documents = {}
    for item in context:
        citations = item.pop('citations')
        item['citationIds'] = [c['id'] for c in citations]
        for c in citations:
            documents[c['id']] = dict(c, excerpt=c['excerpt'][:excerpt_limit])
    return [{'role':'system','content':prompt('reviewer')},
            {'role':'user','content':json.dumps({'findings':context,'references':documents},ensure_ascii=False)}]


def bounded_batches(report, findings):
    """Bound both expected output count and serialized input before making any API call."""
    pending = [report[i:i+4] for i in range(0, len(report), 4)]
    while pending:
        batch = pending.pop(0)
        messages = review_messages(batch, findings)
        if token_bound({'messages':messages,'tools':None}) <= MAX_INPUT_TOKENS:
            yield batch, messages
        elif len(batch) > 1:
            mid = len(batch)//2
            pending[0:0] = [batch[:mid], batch[mid:]]
        else:
            messages = review_messages(batch, findings, excerpt_limit=200)
            # If even one finding is oversized the caller marks only this item as fallback.
            yield batch, messages


def apply_review(message, batch):
    parsed = LLMReport.model_validate_json(message['content'])
    expected = {r['id'] for r in batch}
    if {x.id for x in parsed.findings} != expected or len(parsed.findings) != len(expected):
        raise ValueError('Finding identity mismatch')
    updates = {x.id:x for x in parsed.findings}
    for r in batch:
        update=updates[r['id']];a=r['analysis']
        available={x['chunkId'] for x in a['references']}
        if not set(update.citationIds).issubset(available) or (available and not update.citationIds):
            raise ValueError('Missing or invented citation')
        facts = {x['id'] for x in a['facts']}
        if not set(update.factIds).issubset(facts):
            raise ValueError('Invented fact')
        if 'C1' in facts and 'C1' not in update.factIds:
            raise ValueError('Missing change evidence citation')
    for r in batch:
        update=updates[r['id']]
        r['analysis'].update(red=update.red,blue=update.blue,remediation=update.remediation,mode='LLM',
            citedFactIds=update.factIds,citedReferenceIds=update.citationIds,model=os.environ.get('LLM_MODEL',''))


async def enrich(report, findings, ledger=None):
    if os.environ.get('LLM_MODE', 'disabled') != 'enabled':
        return report, 'RULE_BASED'
    ledger = ledger or Ledger()
    batches = list(bounded_batches(report, findings))
    while batches:
        batch, messages = batches.pop(0)
        reason = None
        try:
            message = await completion(messages, ledger, json_output=True)
            apply_review(message, batch)
        except TruncatedOutput:
            if len(batch) > 1:
                mid=len(batch)//2
                batches[0:0]=[(part,review_messages(part,findings)) for part in [batch[:mid],batch[mid:]]]
                continue
            reason='OUTPUT_LIMIT'
        except BudgetExceeded as exc:
            reason=str(exc)
        except httpx.HTTPStatusError:
            reason='LLM_HTTP_ERROR'
        except Exception:
            reason='LLM_RESPONSE_INVALID'
        if reason:
            for r in batch:
                r['analysis'].update(mode='LLM_FALLBACK',fallbackReason=reason)
    mode='LLM_FALLBACK' if any(r['analysis']['mode']!='LLM' for r in report) else 'LLM'
    for r in report:
        r['analysis']['contextBudget'] = dict(ledger.data, accounting='UTF8_BYTES_UPPER_BOUND_WITH_FRAMING')
    return report, mode
