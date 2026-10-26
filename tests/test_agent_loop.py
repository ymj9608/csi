import json
import time
from types import SimpleNamespace
import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from agent.csi_agent import legacy_graph as module
from agent.csi_agent import planner
from agent.csi_agent.harness import Ledger, BudgetExceeded, MAX_INPUT_TOKENS, token_bound
from agent.csi_agent.analysis import base_report, bounded_batches, enrich

EVENT={'scanId':'current-scan','repository':'local/test','commitSha':'a'*40}
FINDING={'id':'a','ruleId':'POL-01','maskedCodeEvidence':'name: str','evidenceStatus':'INSUFFICIENT_EVIDENCE'}
POLICY={'version':'test','approvedFields':['email'],'restrictedFields':['phoneNumber'],'inventorySection':'POL-02','inventoryPage':3}
INTERNAL={'chunkId':'i','sectionId':'POL-02','sectionTitle':'Inventory','documentType':'INTERNAL_POLICY','pageNumber':3,'content':'Approved fields email'}
EXTERNAL=dict(INTERNAL,chunkId='e',documentType='EXTERNAL_REFERENCE')


def setup_graph(monkeypatch, choices, fail_first_lookup=False, changes=None, findings=None):
    from mcp_servers.policy_review import compare_findings
    monkeypatch.setenv('CSI_INTERNAL_TOKEN','test-token')
    monkeypatch.setenv('LLM_MODE','enabled')
    calls=[];events=[];observations=[]
    class Client:
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def call_tool(self,name,args):
            calls.append((name,args))
            if name=='get_scan_context':v=dict(EVENT,status='QUEUED',hasChanges=changes is not None)
            elif name=='get_scan_findings':v=[FINDING] if findings is None else findings
            elif name=='get_scan_changes':v=changes
            elif name=='get_privacy_policy':v=POLICY
            elif name=='compare_policy_with_findings':v=compare_findings([FINDING],POLICY)
            elif name=='get_guideline_details':
                if fail_first_lookup:raise RuntimeError('simulated retrieval outage')
                v={'internal':[INTERNAL],'external':[EXTERNAL]}
            elif name=='search_internal_privacy_policy':v=[INTERNAL]
            elif name=='search_security_guidelines':v=[EXTERNAL]
            elif name=='request_security_review':v={'id':'approval'}
            elif name=='create_security_issue':v={'id':'issue'}
            else:raise AssertionError(name)
            return SimpleNamespace(is_error=False,data=v)
    async def choose(s,ledger):
        observations.append(s.get('observation',{}))
        index=min(len(observations)-1,len(choices)-1)
        name,args=choices[index];return {'name':name,'args':args}
    async def report(r,f,ledger):
        for x in r:x['analysis']['mode']='LLM'
        return r,'LLM'
    async def emit(topic,event,event_type,**kwargs):events.append((event_type,kwargs))
    monkeypatch.setattr(module,'Client',Client);monkeypatch.setattr(module,'choose_action',choose);monkeypatch.setattr(module,'enrich',report)
    graph=module.build_graph(InMemorySaver(),emit)
    return graph,calls,events,observations


@pytest.mark.asyncio
async def test_dynamic_order_observation_replan_and_approval_resume(monkeypatch):
    choices=[('finish_analysis',{}),('get_guideline_details',{'rule_id':'POL-01'}),
             ('search_internal_privacy_policy',{'rule_id':'POL-01','query':'inventory'}),
             ('search_security_guidelines',{'rule_id':'POL-01','query':'privacy'}),
             ('compare_policy_with_findings',{}),('get_privacy_policy',{}),('finish_analysis',{})]
    graph,calls,events,observations=setup_graph(monkeypatch,choices,fail_first_lookup=True)
    config={'configurable':{'thread_id':'scan'},'recursion_limit':60}
    await graph.ainvoke({'event':EVENT},config)
    snapshot=await graph.aget_state(config)
    assert snapshot.next==('approval_interrupt',)
    assert observations[1]['status']=='MISSING_EVIDENCE'
    assert observations[2]['status']=='TOOL_ERROR'
    names=[n for n,_ in calls]
    assert names.index('search_internal_privacy_policy')<names.index('get_privacy_policy')
    assert 'create_security_issue' not in names
    assert snapshot.values['turn']==7
    assert snapshot.values['selectorMode']=='LLM'
    assert all(args=={'scan_id':EVENT['scanId']} for name,args in calls if name in {'get_privacy_policy','compare_policy_with_findings'})
    await graph.ainvoke(Command(resume={'approvalId':'approval','status':'APPROVED'}),config)
    assert [n for n,_ in calls].count('create_security_issue')==1
    assert not (await graph.aget_state(config)).next


@pytest.mark.asyncio
async def test_finite_loop_even_when_model_repeats(monkeypatch):
    graph,calls,events,_=setup_graph(monkeypatch,[('get_privacy_policy',{})])
    with pytest.raises(RuntimeError,match='turn budget'):
        await graph.ainvoke({'event':EVENT},{'configurable':{'thread_id':'repeat'},'recursion_limit':60})
    assert [n for n,_ in calls].count('get_privacy_policy')==3
    assert not any(t=='SCAN_RESULT' for t,_ in events)


@pytest.mark.asyncio
async def test_llm_failure_uses_labelled_fallback_not_fake_model_selection(monkeypatch):
    graph,calls,events,_=setup_graph(monkeypatch,[])
    async def failed(*args):raise RuntimeError('API unavailable')
    monkeypatch.setattr(module,'choose_action',failed)
    config={'configurable':{'thread_id':'fallback'},'recursion_limit':60}
    await graph.ainvoke({'event':EVENT},config)
    state=(await graph.aget_state(config)).values
    assert state['selectorMode']=='LLM_FALLBACK' and state['mode']=='LLM_FALLBACK'
    assert state['planningDone']
    assert any(v.get('node')=='agent_fallback' for _,v in events)


@pytest.mark.asyncio
async def test_real_planner_contract_rejects_write_and_cross_scan(monkeypatch):
    s={'rules':['POL-01'],'findings':[FINDING]}
    for name,args in [('create_security_issue',{}),('get_privacy_policy',{'scan_id':'other'}),('get_guideline_details',{'rule_id':'SEC-99'})]:
        async def fake(messages,ledger,**kwargs):
            assert 'create_security_issue' not in json.dumps(kwargs['tools'])
            return {'tool_calls':[{'type':'function','function':{'name':name,'arguments':json.dumps(args)}}]}
        monkeypatch.setattr(planner,'completion',fake)
        with pytest.raises(ValueError):await planner.choose_action(s,Ledger())


def test_context_bound_and_shared_documents_with_300_findings():
    findings=[dict(FINDING,id=str(i)) for i in range(300)]
    refs={'POL-01':[dict(INTERNAL,content='정책 내용 '*1000),EXTERNAL]}
    report=base_report(findings,refs,POLICY)
    batches=list(bounded_batches(report,findings))
    assert [r['id'] for b,_ in batches for r in b]==[str(i) for i in range(300)]
    for batch,messages in batches:
        assert len(batch)<=4
        assert token_bound({'messages':messages,'tools':None})<=MAX_INPUT_TOKENS
        payload=json.loads(messages[-1]['content'])
        assert len(payload['references'])==2
        assert all(x['evidenceStatus']=='INSUFFICIENT_EVIDENCE' for x in payload['findings'])


def test_budget_caps_context_calls_and_deadline():
    with pytest.raises(BudgetExceeded):Ledger().reserve([{'content':'x'*25000}],None,6000)
    ledger=Ledger({'startedAt':time.time()-200,'calls':0,'reservedTokens':0,'actualTokens':0,'maxInputBound':0})
    with pytest.raises(BudgetExceeded,match='DEADLINE'):ledger.reserve([],None,1)
    ledger=Ledger({'startedAt':time.time(),'calls':32,'reservedTokens':0,'actualTokens':0,'maxInputBound':0})
    with pytest.raises(BudgetExceeded,match='SCAN_MODEL'):ledger.reserve([],None,1)


def test_six_rules_fit_fallback_turn_and_per_tool_budgets():
    from agent.csi_agent.analysis import RULES
    from agent.csi_agent.harness import MAX_TURNS, MAX_TOOL_REPEATS
    s={'rules':sorted(RULES),'findings':[],'references':{},'toolCounts':{}}
    for turn in range(MAX_TURNS):
        action=planner.fallback_action(s);name=action['name'];args=action['args']
        if name=='finish_analysis':
            assert not planner.missing_requirements(s)
            break
        s['toolCounts'][name]=s['toolCounts'].get(name,0)+1
        assert s['toolCounts'][name]<=MAX_TOOL_REPEATS
        if name=='get_privacy_policy':s['policy']=POLICY
        elif name=='compare_policy_with_findings':s['comparison']={'items':[]}
        else:
            refs=([INTERNAL,EXTERNAL] if name=='get_guideline_details' else
                  [INTERNAL] if name=='search_internal_privacy_policy' else [EXTERNAL])
            s['references'].setdefault(args['rule_id'],[]).extend(refs)
    else:
        pytest.fail('Six-rule coverage did not fit the turn budget')


@pytest.mark.asyncio
async def test_mcp_annotations_and_mutations_are_not_model_tools():
    from fastmcp import Client
    from mcp_servers.business import mcp
    async with Client(mcp) as client:tools=await client.list_tools()
    for tool in tools:
        write=tool.name in {'request_security_review','create_security_issue'}
        assert tool.annotations.readOnlyHint is (not write)
        assert tool.annotations.destructiveHint is write
        assert tool.annotations.idempotentHint
    assert set(planner.READ_TOOLS).isdisjoint({'request_security_review','create_security_issue'})


@pytest.mark.asyncio
async def test_bad_batch_keeps_other_successful_findings(monkeypatch):
    import agent.csi_agent.analysis as analysis
    monkeypatch.setenv('LLM_MODE','enabled')
    findings=[dict(FINDING,id=str(i)) for i in range(8)]
    async def fake(messages,ledger,**kwargs):
        data=json.loads(messages[-1]['content'])
        if data['findings'][0]['id']=='0':raise ValueError('malformed output')
        return {'content':json.dumps({'findings':[{'id':f['id'],'red':'r','blue':'b','remediation':'m','citationIds':['i'],'factIds':['F1']} for f in data['findings']]})}
    monkeypatch.setattr(analysis,'completion',fake)
    report,mode=await enrich(base_report(findings,{'POL-01':[INTERNAL]},POLICY),findings)
    assert len(report)==8 and mode=='LLM_FALLBACK'
    assert [x['analysis']['mode'] for x in report]==['LLM_FALLBACK']*4+['LLM']*4

@pytest.mark.asyncio
async def test_planner_observes_last_tool_error_as_tool_message(monkeypatch):
    s={'rules':['POL-01'],'findings':[FINDING],'turn':1,
       'action':{'name':'get_guideline_details','args':{'rule_id':'POL-01'}},
       'observation':{'tool':'get_guideline_details','status':'TOOL_ERROR','result':{'error':'Unavailable'}}}
    async def fake(messages,ledger,**kwargs):
        assert messages[-1]['role']=='tool' and 'TOOL_ERROR' in messages[-1]['content']
        assert messages[-2]['tool_calls'][0]['id']==messages[-1]['tool_call_id']
        return {'tool_calls':[{'type':'function','function':{'name':'search_internal_privacy_policy','arguments':'{"rule_id":"POL-01","query":"inventory"}'}}]}
    monkeypatch.setattr(planner,'completion',fake)
    assert (await planner.choose_action(s,Ledger()))['name']=='search_internal_privacy_policy'


@pytest.mark.asyncio
async def test_output_truncation_splits_batch_once_until_singletons(monkeypatch):
    import agent.csi_agent.analysis as analysis
    from agent.csi_agent.harness import TruncatedOutput
    monkeypatch.setenv('LLM_MODE','enabled')
    findings=[dict(FINDING,id=str(i)) for i in range(4)]
    calls=[]
    async def fake(messages,ledger,**kwargs):
        items=json.loads(messages[-1]['content'])['findings'];calls.append(len(items))
        if len(items)>1:raise TruncatedOutput('OUTPUT_LIMIT')
        return {'content':json.dumps({'findings':[{'id':items[0]['id'],'red':'r','blue':'b','remediation':'m','citationIds':['i'],'factIds':['F1']}]})}
    monkeypatch.setattr(analysis,'completion',fake)
    report,mode=await enrich(base_report(findings,{'POL-01':[INTERNAL]},POLICY),findings)
    assert mode=='LLM' and len(report)==4 and len(calls)==7


@pytest.mark.asyncio
async def test_transient_retry_is_bounded_and_charged(monkeypatch):
    from agent.csi_agent import harness
    for k,v in {'LLM_BASE_URL':'https://llm.invalid/v1','LLM_API_KEY':'test','LLM_MODEL':'test'}.items():monkeypatch.setenv(k,v)
    calls=[]
    class Client:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,*args,**kwargs):
            calls.append(1)
            return SimpleNamespace(status_code=503 if len(calls)<3 else 200,raise_for_status=lambda:None,
                json=lambda:{'usage':{'total_tokens':7},'choices':[{'finish_reason':'stop','message':{'content':'ok'}}]})
    async def no_wait(_):pass
    monkeypatch.setattr(harness.httpx,'AsyncClient',Client);monkeypatch.setattr(harness.asyncio,'sleep',no_wait)
    ledger=Ledger();assert (await harness.completion([],ledger))['content']=='ok'
    assert ledger.data['calls']==3 and ledger.data['actualTokens']==7


@pytest.mark.asyncio
@pytest.mark.parametrize('has_current',[True,False])
async def test_change_context_flows_through_mcp_graph_and_result(monkeypatch,has_current):
    current=dict(FINDING,filePath='a.py',startLine=3,endLine=3,fingerprint='new')
    changes={'status':'AVAILABLE','baseSha':'b'*40,'headSha':EVENT['commitSha'],'truncated':False,
             'files':[{'changeId':'change1','filePath':'a.py','truncated':False,'rows':[{'kind':'ADDED','newLine':3}]}],
             'baselineFindings':[{'fingerprint':'old','filePath':'a.py','ruleId':'POL-01'}]}
    choices=[('get_privacy_policy',{}),('compare_policy_with_findings',{}),
             ('get_guideline_details',{'rule_id':'POL-01'}),('finish_analysis',{})]
    graph,calls,events,_=setup_graph(monkeypatch,choices,changes=changes,findings=[current] if has_current else [])
    config={'configurable':{'thread_id':'changes'},'recursion_limit':60}
    await graph.ainvoke({'event':EVENT},config)
    assert [n for n,_ in calls].count('get_scan_changes')==1
    result=next(v for t,v in events if t=='SCAN_RESULT')
    review=result['changeReview']['files'][0]
    assert review['removedFingerprints']==['old']
    assert review['currentFindingIds']==(['a'] if has_current else [])
    assert result['changeReview']['references']
    if has_current:
        analysis=result['findings'][0]['analysis']
        assert analysis['changeContext']['relation']=='CHANGED_LINES'
        assert 'C1' in {f['id'] for f in analysis['facts']}
    else:
        assert result['findings']==[] and result['analysisMode']=='RULE_BASED'
        assert not (await graph.aget_state(config)).next


@pytest.mark.asyncio
async def test_exhausted_tools_are_removed_and_cannot_be_selected(monkeypatch):
    s={'rules':['POL-01','SEC-02'],'findings':[], 'toolCounts':{'search_security_guidelines':3}}
    async def fake(messages,ledger,**kwargs):
        names={t['function']['name'] for t in kwargs['tools']}
        assert 'search_security_guidelines' not in names and 'get_guideline_details' in names
        return {'tool_calls':[{'type':'function','function':{'name':'search_security_guidelines','arguments':'{"rule_id":"POL-01","query":"privacy"}'}}]}
    monkeypatch.setattr(planner,'completion',fake)
    with pytest.raises(ValueError,match='TOOL_EXHAUSTED'):
        await planner.choose_action(s,Ledger())
