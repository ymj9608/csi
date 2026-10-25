"""Read-only model function selection with scan-bound argument validation."""
import json
from collections import Counter
from .harness import completion, prompt, MAX_TOOL_REPEATS
from .analysis import RULES

READ_TOOLS = {
    'get_privacy_policy': ('business', 'Read the immutable privacy policy for the current scan.'),
    'compare_policy_with_findings': ('business', 'Compare each field with the policy inventory; separate approvals remain unverified.'),
    'get_scan_history': ('business', 'Inspect prior scan status/count summaries if history is needed.'),
    'search_internal_privacy_policy': ('rag', 'Search internal policy for a rule; use a focused query when evidence is missing.'),
    'search_security_guidelines': ('rag', 'Search external reference guidelines for a rule using a focused query.'),
    'get_guideline_details': ('rag', 'Fetch both internal and external guideline evidence for a rule.'),
}


def missing_requirements(s):
    missing=[]
    if not s.get('policy'):missing.append('get_privacy_policy')
    if 'POL-01' in s['rules'] and not s.get('comparison'):missing.append('compare_policy_with_findings')
    for rule in s['rules']:
        types={r['documentType'] for r in s.get('references',{}).get(rule,[])}
        for kind in ['INTERNAL_POLICY','EXTERNAL_REFERENCE']:
            if kind not in types:missing.append(rule+':'+kind)
    return missing


def definitions(rules, counts=None):
    tools=[]
    counts=counts or {}
    for name,(_,description) in READ_TOOLS.items():
        if counts.get(name,0)>=MAX_TOOL_REPEATS:continue
        if not rules and (name.startswith('search_') or name=='get_guideline_details'):continue
        props={}
        if name.startswith('search_') or name=='get_guideline_details':
            props['rule_id']={'type':'string','enum':rules}
        if name.startswith('search_'):props['query']={'type':'string','minLength':1,'maxLength':300}
        tools.append({'type':'function','function':{'name':name,'description':description,
            'parameters':{'type':'object','properties':props,'required':list(props),'additionalProperties':False}}})
    tools.append({'type':'function','function':{'name':'finish_analysis','description':'Finish only when missingRequirements is empty.',
        'parameters':{'type':'object','properties':{},'required':[],'additionalProperties':False}}})
    return tools


def validate_action(name,args,rules):
    if name not in {*READ_TOOLS,'finish_analysis'} or not isinstance(args,dict):raise ValueError('TOOL_NOT_ALLOWED')
    expected=set()
    if name.startswith('search_') or name=='get_guideline_details':expected.add('rule_id')
    if name.startswith('search_'):expected.add('query')
    if set(args)!=expected:raise ValueError('TOOL_ARGUMENTS')
    if 'rule_id' in args and args['rule_id'] not in rules:raise ValueError('RULE_OUT_OF_SCOPE')
    if 'query' in args and (not isinstance(args['query'],str) or not 1<=len(args['query'])<=300):raise ValueError('QUERY_LIMIT')
    return {'name':name,'args':args}


def observation(name,result):
    # Local state retains full results; the model receives compact, sanitized summaries only.
    if name=='get_privacy_policy':
        return {k:result.get(k) for k in ['version','approvedFields','restrictedFields','bcryptMinCost']}
    if name=='compare_policy_with_findings':
        return {'counts':dict(Counter(x['inventoryStatus'] for x in result.get('items',[])))}
    if name=='get_scan_history':
        return {'count':len(result),'statuses':dict(Counter(x.get('status','UNKNOWN') for x in result))}
    refs=result.get('internal',[])+result.get('external',[]) if isinstance(result,dict) else result
    return {'documents':[{'id':r['chunkId'],'type':r['documentType'],'section':r['sectionId'],
                         'excerpt':r['content'][:350]} for r in refs[:6]]}


async def choose_action(s,ledger):
    payload={'rules':s['rules'],'findingCounts':dict(Counter(f['ruleId'] for f in s['findings'])),
             'changeContext':{'status':s.get('changes',{}).get('status','NOT_PROVIDED'),'files':len(s.get('changes',{}).get('files',[]))},
             'turn':s.get('turn',0)+1,'missingRequirements':missing_requirements(s),
             'toolCallCounts':s.get('toolCounts',{}),
             'previousActions':s.get('trace',[])[-12:],
             'evidenceCoverage':{rule:sorted({x['documentType'] for x in refs}) for rule,refs in s.get('references',{}).items()}}
    messages=[{'role':'system','content':prompt('planner')},{'role':'user','content':json.dumps(payload,ensure_ascii=False)}]
    if s.get('action') and s.get('observation'):
        previous=s['action'];call_id='call_turn_'+str(s.get('turn',0))
        messages.append({'role':'assistant','content':None,'tool_calls':[{'id':call_id,'type':'function',
                         'function':{'name':previous['name'],'arguments':json.dumps(previous['args'])}}]})
        messages.append({'role':'tool','tool_call_id':call_id,'content':json.dumps(s['observation'],ensure_ascii=False)})
    offered=definitions(s['rules'],s.get('toolCounts',{}))
    message=await completion(messages,ledger,tools=offered,output_tokens=700)
    calls=message.get('tool_calls') or []
    if len(calls)!=1 or calls[0].get('type')!='function':raise ValueError('ONE_TOOL_REQUIRED')
    fn=calls[0]['function']
    if fn['name'] not in {tool['function']['name'] for tool in offered}:raise ValueError('TOOL_EXHAUSTED_OR_UNAVAILABLE')
    return validate_action(fn['name'],json.loads(fn['arguments']),s['rules'])


def fallback_action(s):
    """Explicit deterministic recovery; never represented as model tool selection."""
    missing=missing_requirements(s)
    if not missing:return {'name':'finish_analysis','args':{}}
    counts=s.get('toolCounts',{})
    attempted={(x['tool'],x.get('ruleId')) for x in s.get('trace',[])}
    for requirement in missing:
        if requirement in {'get_privacy_policy','compare_policy_with_findings'}:
            if counts.get(requirement,0)<MAX_TOOL_REPEATS:
                return {'name':requirement,'args':{}}
            if requirement=='get_privacy_policy':
                # Never substitute an empty/default policy for an unavailable scan snapshot.
                raise RuntimeError('Required scan policy unavailable after bounded retries')
            continue
        rule,kind=requirement.split(':')
        # Repeating the same empty lookup starves other rules. Try its alternative,
        # then continue to the remaining rules while respecting the global budgets.
        if counts.get('get_guideline_details',0)<MAX_TOOL_REPEATS and ('get_guideline_details',rule) not in attempted:
            return {'name':'get_guideline_details','args':{'rule_id':rule}}
        name='search_internal_privacy_policy' if kind=='INTERNAL_POLICY' else 'search_security_guidelines'
        if counts.get(name,0)<MAX_TOOL_REPEATS and (name,rule) not in attempted:
            return {'name':name,'args':{'rule_id':rule,'query':RULES[rule][1]}}
    # The graph records every missing requirement before publishing a limited report.
    return {'name':'finish_analysis','args':{}}
