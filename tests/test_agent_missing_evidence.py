"""Missing RAG hits must not erase available scanner evidence or imply compliance."""
from collections import Counter
from types import SimpleNamespace

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from agent.csi_agent import graph as module
from agent.csi_agent.planner import fallback_action


EVENT={'scanId':'partial-evidence','repository':'local/test','commitSha':'a'*40}
POLICY={'version':'test','approvedFields':['email'],'restrictedFields':[], 'bcryptMinCost':12}
FINDINGS=[{'id':'password','ruleId':'SEC-02','filePath':'signup.py','startLine':1,'evidenceStatus':'CANDIDATE'},
          {'id':'logs','ruleId':'SEC-05','filePath':'signup.py','startLine':2,'evidenceStatus':'CANDIDATE'}]


def setup_graph(monkeypatch, *, missing_rules=(), fail_rag=False, fail_policy=False):
    monkeypatch.setenv('CSI_INTERNAL_TOKEN','test-token')
    monkeypatch.setenv('LLM_MODE','disabled')
    calls=[];events=[]
    class Client:
        def __init__(self,*args,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def call_tool(self,name,args):
            calls.append((name,args))
            if name=='get_scan_context':value=dict(EVENT,status='QUEUED',hasChanges=False)
            elif name=='get_scan_findings':value=FINDINGS
            elif name=='get_privacy_policy':
                if fail_policy:raise RuntimeError('policy unavailable')
                value=POLICY
            elif name=='request_security_review':value={'id':'review'}
            else:
                assert name in {'get_guideline_details','search_internal_privacy_policy','search_security_guidelines'}
                if fail_rag:raise RuntimeError('retrieval unavailable')
                rule=args['rule_id']
                internal={'chunkId':rule+'-internal','documentType':'INTERNAL_POLICY','sectionId':'POL-04',
                          'sectionTitle':'Policy','pageNumber':4,'content':'Retrieved test policy'}
                external=dict(internal,chunkId=rule+'-external',documentType='EXTERNAL_REFERENCE')
                empty=rule in missing_rules
                if name=='get_guideline_details':value={'internal':[] if empty else [internal],'external':[] if empty else [external]}
                elif name=='search_internal_privacy_policy':value=[] if empty else [internal]
                else:value=[] if empty else [external]
            return SimpleNamespace(is_error=False,data=value)
    async def emit(topic,event,event_type,**kwargs):events.append((event_type,kwargs))
    monkeypatch.setattr(module,'Client',Client)
    return module.build_graph(InMemorySaver(),emit),calls,events


def test_fallback_does_not_select_exhausted_search_or_starve_another_rule():
    state={'rules':['SEC-02','SEC-05'],'policy':POLICY,'references':{},
           'toolCounts':{'get_guideline_details':3,'search_internal_privacy_policy':3},
           'trace':[]}
    action=fallback_action(state)
    assert action=={'name':'search_security_guidelines','args':{'rule_id':'SEC-02','query':module.RULES['SEC-02'][1]}}
    state['trace']=[{'tool':action['name'],'ruleId':'SEC-02'}]
    assert fallback_action(state)['args']['rule_id']=='SEC-05'


@pytest.mark.asyncio
async def test_empty_rule_keeps_other_rule_evidence_and_reports_missing_sources(monkeypatch):
    graph,calls,events=setup_graph(monkeypatch,missing_rules={'SEC-02'})
    config={'configurable':{'thread_id':'empty'},'recursion_limit':60}
    await graph.ainvoke({'event':EVENT},config)
    state=(await graph.aget_state(config)).values
    result=next(v for kind,v in events if kind=='SCAN_RESULT')
    assert result['status']=='COMPLETED' and result['analysisMode']=='RULE_BASED'
    password,logs=result['findings']
    assert password['analysis']['references']==[]
    assert password['analysis']['evidenceCoverage']['missingRequirements']==['SEC-02:INTERNAL_POLICY','SEC-02:EXTERNAL_REFERENCE']
    assert any('판단은 보류' in x for x in password['analysis']['unknowns'])
    assert len(logs['analysis']['references'])==2
    assert 'evidenceCoverage' not in logs['analysis']
    assert all(x['analysis']['defenseAssessment']=='REVIEW_REQUIRED' for x in result['findings'])
    assert state['turn']<module.MAX_TURNS
    assert all(n<=module.MAX_TOOL_REPEATS for n in Counter(name for name,_ in calls).values())


@pytest.mark.asyncio
async def test_rag_outage_finishes_with_explicit_limits_instead_of_losing_findings(monkeypatch):
    graph,calls,events=setup_graph(monkeypatch,fail_rag=True)
    config={'configurable':{'thread_id':'outage'},'recursion_limit':60}
    await graph.ainvoke({'event':EVENT},config)
    result=next(v for kind,v in events if kind=='SCAN_RESULT')
    assert len(result['findings'])==2
    assert all(x['analysis']['references']==[] and x['analysis']['evidenceCoverage']['status']=='PARTIAL' for x in result['findings'])
    assert (await graph.aget_state(config)).values['turn']<=module.MAX_TURNS
    assert all(n<=module.MAX_TOOL_REPEATS for n in Counter(name for name,_ in calls).values())


@pytest.mark.asyncio
async def test_missing_policy_remains_bounded_hard_failure(monkeypatch):
    graph,calls,events=setup_graph(monkeypatch,fail_policy=True)
    with pytest.raises(RuntimeError,match='Required scan policy unavailable'):
        await graph.ainvoke({'event':EVENT},{'configurable':{'thread_id':'policy'},'recursion_limit':60})
    assert sum(name=='get_privacy_policy' for name,_ in calls)==module.MAX_TOOL_REPEATS
    assert not any(kind=='SCAN_RESULT' for kind,_ in events)


@pytest.mark.asyncio
@pytest.mark.parametrize('missing_rules',[set(),{'SEC-02'}])
async def test_last_turn_preserves_complete_or_partial_evidence(monkeypatch,missing_rules):
    monkeypatch.setattr(module,'MAX_TURNS',3)
    graph,_,events=setup_graph(monkeypatch,missing_rules=missing_rules)
    config={'configurable':{'thread_id':'last-turn'},'recursion_limit':60}
    await graph.ainvoke({'event':EVENT},config)
    result=next(v for kind,v in events if kind=='SCAN_RESULT')
    assert len(result['findings'])==2
    assert (await graph.aget_state(config)).values['turn']==3
    if missing_rules:
        assert all(x['analysis']['evidenceCoverage']['status']=='PARTIAL' for x in result['findings'])
    else:
        assert all(len(x['analysis']['references'])==2 for x in result['findings'])
