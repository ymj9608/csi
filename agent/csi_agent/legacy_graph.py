"""Historical graph retained for regression checks; new scans use graph.py."""
import os,asyncio,time,json
from typing import TypedDict
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from langgraph.graph import StateGraph,START,END
from langgraph.types import interrupt
from .analysis import RULES,base_report,enrich
from .changes import attach_change_facts, review_changes
from .harness import Ledger, MAX_TURNS, MAX_TOOL_REPEATS
from .planner import READ_TOOLS, choose_action, fallback_action, missing_requirements, observation, validate_action
class State(TypedDict,total=False):
    hasChanges:bool
    changes:dict
    changeReview:dict
    event:dict
    skip:bool
    findings:list
    policy:dict
    references:dict
    rules:list
    report:list
    mode:str
    approval:dict
    decision:dict
    comparison:dict
    history:list
    turn:int
    action:dict
    trace:list
    observation:dict
    toolCounts:dict
    budget:dict
    selectorMode:str
    planningDone:bool
    incompleteEvidence:list

def build_graph(checkpointer,emit):
    async def log(s,node,**data):await emit('scan.log',s['event'],'SCAN_LOG',node=node,**data)
    async def tool(s,service,name,args):
        counts=dict(s.get('toolCounts',{}));counts[name]=counts.get(name,0)+1;s['toolCounts']=counts
        if counts[name]>MAX_TOOL_REPEATS:raise RuntimeError('Tool call budget exceeded')
        started=time.monotonic();await log(s,'mcp_start',toolName=name)
        url=os.environ.get('BUSINESS_MCP_URL','http://127.0.0.1:8001/mcp') if service=='business' else os.environ.get('RAG_MCP_URL','http://127.0.0.1:8002/mcp')
        async with asyncio.timeout(15):
            async with Client(url,auth=BearerAuth(os.environ['CSI_INTERNAL_TOKEN'])) as client:
                result=await client.call_tool(name,args)
                if result.is_error:raise RuntimeError('MCP tool failed')
        await log(s,'mcp_complete',toolName=name,elapsedMs=int((time.monotonic()-started)*1000))
        return result.data
    async def validate(s):
        await log(s,'validate_scan')
        context=await tool(s,'business','get_scan_context',{'scan_id':s['event']['scanId']})
        if context['commitSha']!=s['event']['commitSha'] or context['repository']!=s['event']['repository']:raise ValueError('Scan context mismatch')
        if context['status']=='FAILED':return {'skip':True}
        await emit('scan.progress',s['event'],'SCAN_PROGRESS');return {'skip':False,'hasChanges':bool(context.get('hasChanges')),'toolCounts':s.get('toolCounts',{}),'budget':Ledger(s.get('budget')).data}
    async def load(s):
        await log(s,'load_findings');f=await tool(s,'business','get_scan_findings',{'scan_id':s['event']['scanId']})
        if len(f)>300 or any(x['ruleId'] not in RULES for x in f):raise ValueError('Unsupported evidence')
        changes=await tool(s,'business','get_scan_changes',{'scan_id':s['event']['scanId']}) if s.get('hasChanges') else {}
        return {'findings':f,'changes':changes,'toolCounts':s.get('toolCounts',{})}
    async def select(s):
        await log(s,'select_analysis_tools')
        return {'rules':sorted({f['ruleId'] for f in s['findings']+s.get('changes',{}).get('baselineFindings',[])}),'references':{},'turn':0,
                'trace':[],'observation':{},'planningDone':False,'incompleteEvidence':[],
                'selectorMode':'LLM' if os.environ.get('LLM_MODE')=='enabled' else 'RULE_BASED'}
    async def plan(s):
        if s.get('turn',0)>=MAX_TURNS:raise RuntimeError('Agent turn budget exceeded')
        ledger=Ledger(s.get('budget'));mode=s['selectorMode']
        if mode=='LLM':
            try:action=await choose_action(s,ledger)
            except Exception:
                mode='LLM_FALLBACK';action=fallback_action(s)
                await log(s,'agent_fallback')
        else:action=fallback_action(s)
        action=validate_action(action['name'],action['args'],s['rules'])
        await log(s,'model_decision',toolName=action['name'],turn=s.get('turn',0)+1,selectionMode=mode,
                  reservedTokens=ledger.data['reservedTokens'])
        return {'action':action,'turn':s.get('turn',0)+1,'selectorMode':mode,'budget':ledger.data}
    async def execute(s):
        action=s['action'];name=action['name'];args=action['args'];result={};changes={}
        status='OK'
        if name=='finish_analysis':
            missing=missing_requirements(s)
            if missing and s.get('policy') and fallback_action(s)['name']=='finish_analysis':
                status='PARTIAL_EVIDENCE';result={'missingRequirements':missing}
                changes.update(planningDone=True,incompleteEvidence=missing)
            elif missing:status='MISSING_EVIDENCE';result={'missingRequirements':missing}
            else:changes['planningDone']=True
        else:
            try:
                if s.get('toolCounts',{}).get(name,0)>=MAX_TOOL_REPEATS:
                    raise RuntimeError('Tool repetition limit')
                bound_args=args if READ_TOOLS[name][0]=='rag' else {'scan_id':s['event']['scanId']}
                value=await tool(s,READ_TOOLS[name][0],name,bound_args)
                result=observation(name,value)
                if name=='get_privacy_policy':changes['policy']=value
                elif name=='compare_policy_with_findings':changes['comparison']=value
                elif name=='get_scan_history':changes['history']=value
                else:
                    refs=dict(s.get('references',{}));rule=args['rule_id']
                    docs=value.get('internal',[])+value.get('external',[]) if isinstance(value,dict) else value
                    merged={x['chunkId']:x for x in refs.get(rule,[])}
                    merged.update({x['chunkId']:x for x in docs});refs[rule]=list(merged.values());changes['references']=refs
            except Exception:
                status='TOOL_ERROR';result={'error':'Tool failed or budget exceeded. Select an alternative; do not invent evidence.'}
        trace=s.get('trace',[])+[{'turn':s['turn'],'tool':name,'ruleId':args.get('rule_id'),
                                'status':status,'mode':s['selectorMode']}]
        await log(s,'tool_observation',toolName=name,turn=s['turn'],selectionMode=s['selectorMode'])
        return dict(changes,trace=trace,observation={'tool':name,'status':status,'result':result},toolCounts=s.get('toolCounts',{}))
    async def assess(s):
        await log(s,'assess_evidence',turn=s['turn'])
        # A real retrieval attempt may consume the last turn without filling every
        # evidence slot. Keep available evidence, but explicitly withhold conclusions
        # that require the missing sources. A missing policy remains a hard failure.
        if (not s.get('planningDone') and s.get('policy') and s.get('turn',0)>=MAX_TURNS
                and any(x['tool'] in READ_TOOLS and READ_TOOLS[x['tool']][0]=='rag' for x in s.get('trace',[]))):
            missing=missing_requirements(s)
            return {'planningDone':True,'incompleteEvidence':missing}
        return {}
    async def red(s):
        await log(s,'red_risk_analysis')
        report=attach_change_facts(base_report(s['findings'],s['references'],s['policy'],s.get('comparison')),s['findings'],s.get('changes',{}))
        by_id={f['id']:f for f in s['findings']}
        for item in report:
            rule=by_id[item['id']]['ruleId']
            missing=[x for x in s.get('incompleteEvidence',[]) if x.startswith(rule+':') or (rule=='POL-01' and x=='compare_policy_with_findings')]
            if missing:
                analysis=item['analysis']
                analysis['evidenceCoverage']={'status':'PARTIAL','missingRequirements':missing}
                labels={'INTERNAL_POLICY':'사내 정책 검색 근거','EXTERNAL_REFERENCE':'외부 보안 지침 검색 근거',
                        'compare_policy_with_findings':'정책 대조 도구 결과'}
                names=[labels.get(x.split(':')[-1],x) for x in missing]
                analysis['unknowns'].append('조회 한도 내에 확보하지 못한 근거: '+', '.join(names)+'. 확보한 정적 사실과 정책 정보만 표시하며, 누락 근거에 의존하는 판단은 보류합니다.')
        return {'report':report}
    async def blue(s):
        await log(s,'blue_defense_verification');ledger=Ledger(s.get('budget'));report,mode=await enrich(s['report'],s['findings'],ledger) if s['findings'] else ([], 'RULE_BASED')
        if s.get('selectorMode')=='LLM_FALLBACK':mode='LLM_FALLBACK'
        await log(s,'context_budget',turn=s.get('turn',0),reservedTokens=ledger.data['reservedTokens'],actualTokens=ledger.data['actualTokens'])
        if mode=='LLM_FALLBACK':await log(s,'llm_fallback')
        for r in report:
            assert r['id'] in {f['id'] for f in s['findings']}
            assert r['analysis']['defenseAssessment']=='REVIEW_REQUIRED'
            r['analysis']['orchestration']={'selectionMode':s.get('selectorMode'),'turns':s.get('turn',0),'trace':s.get('trace',[])}
        return {'report':report,'mode':mode,'budget':ledger.data}
    async def generate(s):
        await log(s,'generate_security_report');return {'mode':s.get('mode','RULE_BASED'),'report':s.get('report',[]),'changeReview':review_changes(s.get('changes',{}),s['findings'],s.get('references',{}))}
    async def persist(s):
        await log(s,'persist_result');await emit('scan.result',s['event'],'SCAN_RESULT',status='COMPLETED',analysisMode=s['mode'],findings=s['report'],changeReview=s.get('changeReview'));return {}
    async def request_review(s):return {'approval':await tool(s,'business','request_security_review',{'scan_id':s['event']['scanId']})}
    async def approval(s):
        await log(s,'approval_interrupt');decision=interrupt({'approvalId':s['approval']['id'],'scanId':s['event']['scanId'],'action':'CREATE_SECURITY_REVIEW_ISSUE'})
        if decision.get('approvalId')!=s['approval']['id'] or decision.get('status') not in {'APPROVED','REJECTED'}:raise ValueError('Invalid resume decision')
        return {'decision':decision}
    async def finalize(s):
        if s.get('decision',{}).get('status')=='APPROVED':await tool(s,'business','create_security_issue',{'approval_id':s['approval']['id']})
        await log(s,'finalize')
        return {}
    g=StateGraph(State)
    nodes=[('validate_scan',validate),('load_findings',load),('select_analysis_tools',select),
           ('plan_analysis',plan),('execute_analysis_tool',execute),('assess_evidence',assess),
           ('red_risk_analysis',red),('blue_defense_verification',blue),('generate_security_report',generate),
           ('persist_result',persist),('request_review',request_review),('approval_interrupt',approval),('finalize',finalize)]
    for name,fn in nodes:g.add_node(name,fn)
    g.add_edge(START,'validate_scan')
    g.add_conditional_edges('validate_scan',lambda s:END if s.get('skip') else 'load_findings')
    g.add_edge('load_findings','select_analysis_tools')
    g.add_conditional_edges('select_analysis_tools',lambda s:'plan_analysis' if s['rules'] or s.get('changes',{}).get('files') else 'generate_security_report')
    g.add_edge('plan_analysis','execute_analysis_tool');g.add_edge('execute_analysis_tool','assess_evidence')
    g.add_conditional_edges('assess_evidence',lambda s:'red_risk_analysis' if s.get('planningDone') else 'plan_analysis')
    g.add_edge('red_risk_analysis','blue_defense_verification');g.add_edge('blue_defense_verification','generate_security_report')
    g.add_edge('generate_security_report','persist_result')
    g.add_conditional_edges('persist_result',lambda s:'request_review' if s['findings'] else 'finalize')
    g.add_edge('request_review','approval_interrupt');g.add_edge('approval_interrupt','finalize');g.add_edge('finalize',END)
    return g.compile(checkpointer=checkpointer)
