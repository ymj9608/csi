import os,asyncio,time
from typing import TypedDict
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from langgraph.graph import StateGraph,START,END
from langgraph.types import interrupt
from .analysis import RULES,base_report,enrich
class State(TypedDict,total=False):
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

def build_graph(checkpointer,emit):
    calls={}
    async def log(s,node,**data):await emit('scan.log',s['event'],'SCAN_LOG',node=node,**data)
    async def tool(s,service,name,args):
        scan=s['event']['scanId'];key=(scan,name,str(args));calls[key]=calls.get(key,0)+1
        if calls[key]>3:raise RuntimeError('Repeated tool call budget exceeded')
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
        await emit('scan.progress',s['event'],'SCAN_PROGRESS');return {'skip':False}
    async def load(s):
        await log(s,'load_findings');f=await tool(s,'business','get_scan_findings',{'scan_id':s['event']['scanId']})
        if len(f)>300 or any(x['ruleId'] not in RULES for x in f):raise ValueError('Unsupported evidence')
        return {'findings':f}
    async def select(s):
        await log(s,'select_analysis_tools');return {'rules':sorted({f['ruleId'] for f in s['findings']}),'references':{}}
    async def policy(s):
        await log(s,'retrieve_internal_policy');p=await tool(s,'business','get_privacy_policy',{'scan_id':s['event']['scanId']})
        comparison=await tool(s,'business','compare_policy_with_findings',{'scan_id':s['event']['scanId']})
        return {'policy':p,'comparison':comparison}
    async def retrieve(s):
        await log(s,'retrieve_security_guidelines');refs={}
        for rule in s['rules']:
            query=RULES[rule][1]
            internal=await tool(s,'rag','search_internal_privacy_policy',{'rule_id':rule,'query':query})
            external=await tool(s,'rag','search_security_guidelines',{'rule_id':rule,'query':query})
            refs[rule]=internal+external
            if not internal or not external:raise ValueError('Required RAG evidence missing')
        history=await tool(s,'business','get_scan_history',{'scan_id':s['event']['scanId']}) if 'POL-01' in s['rules'] else []
        return {'references':refs,'history':history}
    async def red(s):
        await log(s,'red_risk_analysis');return {'report':base_report(s['findings'],s['references'],s['policy'],s.get('comparison'))}
    async def blue(s):
        await log(s,'blue_defense_verification');report,mode=await enrich(s['report'],s['findings'])
        if mode=='LLM_FALLBACK':await log(s,'llm_fallback')
        for r in report:
            assert r['id'] in {f['id'] for f in s['findings']}
            assert r['analysis']['defenseAssessment']=='REVIEW_REQUIRED'
        return {'report':report,'mode':mode}
    async def generate(s):
        await log(s,'generate_security_report');return {'mode':s.get('mode','RULE_BASED'),'report':s.get('report',[])}
    async def persist(s):
        await log(s,'persist_result');await emit('scan.result',s['event'],'SCAN_RESULT',status='COMPLETED',analysisMode=s['mode'],findings=s['report']);return {}
    async def request_review(s):return {'approval':await tool(s,'business','request_security_review',{'scan_id':s['event']['scanId']})}
    async def approval(s):
        await log(s,'approval_interrupt');decision=interrupt({'approvalId':s['approval']['id'],'scanId':s['event']['scanId'],'action':'CREATE_SECURITY_REVIEW_ISSUE'})
        if decision.get('approvalId')!=s['approval']['id'] or decision.get('status') not in {'APPROVED','REJECTED'}:raise ValueError('Invalid resume decision')
        return {'decision':decision}
    async def finalize(s):
        if s.get('decision',{}).get('status')=='APPROVED':await tool(s,'business','create_security_issue',{'approval_id':s['approval']['id']})
        await log(s,'finalize')
        # Invocation budgets are per active scan; completed threads do not retain counters.
        for key in [k for k in calls if k[0]==s['event']['scanId']]:del calls[key]
        return {}
    g=StateGraph(State)
    for name,fn in [('validate_scan',validate),('load_findings',load),('select_analysis_tools',select),('retrieve_internal_policy',policy),('retrieve_security_guidelines',retrieve),('red_risk_analysis',red),('blue_defense_verification',blue),('generate_security_report',generate),('persist_result',persist),('request_review',request_review),('approval_interrupt',approval),('finalize',finalize)]:g.add_node(name,fn)
    g.add_edge(START,'validate_scan');g.add_conditional_edges('validate_scan',lambda s:END if s.get('skip') else 'load_findings');g.add_edge('load_findings','select_analysis_tools');g.add_edge('select_analysis_tools','retrieve_internal_policy')
    g.add_conditional_edges('retrieve_internal_policy',lambda s:'retrieve_security_guidelines' if s['rules'] else 'generate_security_report')
    g.add_edge('retrieve_security_guidelines','red_risk_analysis');g.add_edge('red_risk_analysis','blue_defense_verification');g.add_edge('blue_defense_verification','generate_security_report');g.add_edge('generate_security_report','persist_result')
    g.add_conditional_edges('persist_result',lambda s:'request_review' if s['findings'] else 'finalize');g.add_edge('request_review','approval_interrupt');g.add_edge('approval_interrupt','finalize');g.add_edge('finalize',END)
    return g.compile(checkpointer=checkpointer)
