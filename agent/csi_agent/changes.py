"""Link bounded commit evidence to existing reviews; never invent changed functionality."""
def relate(finding, changes):
    if changes.get('status')!='AVAILABLE':return None
    file=next((f for f in changes['files'] if f['filePath']==finding['filePath']),None)
    if not file:return None
    previous={f['fingerprint'] for f in changes['baselineFindings']}
    lines={r['newLine'] for r in file['rows'] if r['kind']!='CONTEXT' and r['newLine'] is not None}
    intersects=any(finding['startLine']<=line<=finding['endLine'] for line in lines)
    return {'changeId':file['changeId'],'baseSha':changes['baseSha'],'headSha':changes['headSha'],
            'status':'PERSISTING' if finding['fingerprint'] in previous else 'NEW',
            'relation':'CHANGED_LINES' if intersects else 'SAME_FILE',
            'partialDiff':changes['truncated'] or file['truncated']}


def attach_change_facts(report, findings, changes):
    source={f['id']:f for f in findings}
    for item in report:
        context=relate(source[item['id']],changes)
        if not context:continue
        a=item['analysis'];a['changeContext']=context
        status='기준 커밋에도 같은 정적 후보가 존재함' if context['status']=='PERSISTING' else '기준 커밋 검사에는 없던 정적 후보가 현재 검사에서 탐지됨'
        relation='제공된 변경 라인과 탐지 위치가 겹침' if context['relation']=='CHANGED_LINES' else '변경 파일 안에 있으나 제공된 변경 라인과 탐지 위치의 겹침은 확인되지 않음'
        a['facts'].append({'id':'C1','text':status+'. '+relation+'. 변경이 취약점의 원인이라는 인과관계는 확정하지 않음.'})
        if context['partialDiff']:a['unknowns'].append('변경 근거는 크기 제한으로 일부만 제공되어 전체 변경은 검토하지 않았습니다.')
        a['unknowns'].append('기준 커밋과 현재 커밋의 정적 결과 비교이며 런타임 악용이나 수정 완료를 검증하지 않았습니다.')
    return report


def review_changes(changes, findings, refs):
    if not changes:return None
    current_fp={f['fingerprint'] for f in findings};files=[];removed_rules=set()
    for file in changes.get('files',[]):
        current=[f['id'] for f in findings if f['filePath']==file['filePath']]
        removed=[f for f in changes['baselineFindings'] if f['filePath']==file['filePath'] and f['fingerprint'] not in current_fp]
        removed_rules.update(f['ruleId'] for f in removed)
        files.append({'changeId':file['changeId'],'currentFindingIds':current,
                      'removedFingerprints':[f['fingerprint'] for f in removed],
                      'verdict':'REVIEW_REQUIRED' if current else 'NO_CURRENT_STATIC_CANDIDATES'})
    references={r['chunkId']:r for rule in removed_rules for r in refs.get(rule,[])}
    return {'summaryMode':'STATIC_FACTS','riskMode':'LINKED_FINDING_ANALYSIS','files':files,'references':list(references.values())}
