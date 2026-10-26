"""Find related components in the project's saved extraction, without inventing a code map.

The extractor has no file paths. Lexical overlap supplies candidates, not proof of
ownership or isolation. Keep that distinction in the model packet and UI.
"""
import re
from copy import deepcopy
from .repository import Rejected

STOP_WORDS = {'backend', 'frontend', 'app', 'core', 'src', 'main', 'python', 'java',
              'component', 'service', 'system', 'the', 'and', 'for', 'with', 'from'}


def validated_flow_context(value):
    """Full scan-bound flow evidence, independent of lexical component ranking.

    A missing field is handled by the caller for old reviews. A present malformed
    field must never silently become 'no architecture information'.
    """
    def require(ok):
        if not ok:
            raise Rejected('UNIFIED_FLOW_CONTEXT_INVALID')
    require(isinstance(value, dict) and set(value) == {'schemaVersion', 'flows', 'uncertainties'})
    require(type(value['schemaVersion']) is int and value['schemaVersion'] == 1)
    require(isinstance(value['flows'], list) and len(value['flows']) <= 16)
    require(isinstance(value['uncertainties'], list) and len(value['uncertainties']) <= 8)
    limits = {'source': 60, 'target': 60, 'condition': 180, 'data': 180}
    for flow in value['flows']:
        require(isinstance(flow, dict) and set(flow) == set(limits) | {'boundary', 'state'})
        for key, limit in limits.items():
            require(isinstance(flow[key], str) and bool(flow[key].strip()) and len(flow[key]) <= limit)
        require(flow['boundary'] in ('INTERNAL', 'EXTERNAL', 'UNKNOWN'))
        require(flow['state'] in ('OBSERVED', 'INFERRED', 'UNKNOWN'))
    for text in value['uncertainties']:
        require(isinstance(text, str) and bool(text.strip()) and len(text) <= 240)
    return deepcopy(value)


def tokens(text):
    text = re.sub(r'([a-z])([A-Z])', r'\1 \2', str(text))
    return {t for t in re.findall(r'[a-zA-Z]{3,}|[가-힣]{2,}', text.lower()) if t not in STOP_WORDS}


def bounded_note(text):
    # Backend validates Java String.length(), i.e. UTF-16 code units.
    return text.encode('utf-16-le')[:400].decode('utf-16-le', errors='ignore')


def resolve(context, findings):
    result = {'status': 'UNAVAILABLE', 'components': [],
              'note': '이 프로젝트에 사용할 수 있는 완료된 아키텍처 분석이 없습니다.'}
    diagram = context.get('architectureDiagram') or {}
    if not isinstance(diagram, dict) or diagram.get('status') != 'EXTRACTED':
        return result
    if not context.get('projectId') or diagram.get('projectId') != context['projectId']:
        return result
    result.update(diagramId=diagram.get('id'), updatedAt=diagram.get('updatedAt'),
                  confirmed=diagram.get('confirmed', False), matchMethod='LEXICAL_CANDIDATE',
                  limitation='컴포넌트 관련성은 이름·역할과 정적 근거의 어휘 일치 후보이며, 코드 소속이나 격리의 증명이 아닙니다.')
    ranked = []
    components = diagram.get('components')
    for component in components[:100] if isinstance(components, list) else []:
        if not isinstance(component, dict) or not all(isinstance(component.get(k), str) for k in ('name', 'role')):
            continue
        if component.get('state') not in {'OBSERVED', 'INFERRED'}:
            continue
        name_tokens = tokens(component['name'])
        role_tokens = tokens(component['role'])
        matches = []
        score = 0
        for finding in findings:
            terms = tokens(' '.join(str(finding.get(k, '')) for k in ('filePath', 'title', 'category')))
            overlap = terms & (name_tokens | role_tokens)
            if overlap:
                matches.append({'findingId': finding['id'], 'matchedTerms': sorted(overlap)})
                score += len(terms & name_tokens) * 2 + len(terms & role_tokens)
        if matches:
            ranked.append((score, {k: component.get(k) for k in ('name', 'role', 'state', 'isolationStatus')} | {'matches': matches}))
    ranked.sort(key=lambda item: (-item[0], item[1]['name']))
    result['components'] = [dict(c, name=c['name'][:200], role=c['role'][:500]) for _, c in ranked[:3]]
    result['status'] = 'MATCHED' if ranked else 'NO_MATCH'
    result['note'] = bounded_note('저장된 아키텍처 관련 후보: ' + ' · '.join(c['name'] for c in result['components'])
                                  if ranked else '저장된 아키텍처를 조회했지만 이 finding에 대응하는 컴포넌트 후보를 찾지 못했습니다.')
    return result
