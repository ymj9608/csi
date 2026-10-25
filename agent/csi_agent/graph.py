"""Evidence collection -> staged integrated VLM assessment -> persistence -> existing human approval.

LangGraph hosts the workflow; it no longer runs a separate security-review LLM.
"""
import asyncio
import json
import os
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from langgraph.graph import StateGraph, START, END
from langgraph.types import interrupt
from .analysis import RULES, base_report
from .changes import attach_change_facts, review_changes
from .visual_review import prepare
from .visual_stages import AnalysisState, MODEL, build_analysis_graph

class State(AnalysisState, total=False):
    event: dict
    skip: bool
    hasChanges: bool
    findings: list
    policy: dict
    changes: dict
    references: dict
    image: dict
    report: list
    visualReview: dict
    changeReview: dict
    approval: dict
    decision: dict

def build_graph(checkpointer, emit):
    async def log(s, node, **fields):
        await emit('scan.log',s['event'],'SCAN_LOG',node=node,**fields)

    async def tool(s, service, name, args):
        url = os.environ.get('BUSINESS_MCP_URL','http://127.0.0.1:8001/mcp') if service=='business' else os.environ.get('RAG_MCP_URL','http://127.0.0.1:8002/mcp')
        await log(s,'mcp_start',toolName=name)
        async with asyncio.timeout(20):
            async with Client(url,auth=BearerAuth(os.environ['CSI_INTERNAL_TOKEN'])) as client:
                result = await client.call_tool(name,args)
                if result.is_error: raise RuntimeError('EVIDENCE_TOOL_FAILED')
        await log(s,'mcp_complete',toolName=name)
        return result.data

    async def validate(s):
        await log(s,'validate_scan')
        context = await tool(s,'business','get_scan_context',{'scan_id':s['event']['scanId']})
        if context['commitSha']!=s['event']['commitSha'] or context['repository']!=s['event']['repository']:
            raise ValueError('SCAN_CONTEXT_MISMATCH')
        if context['status'] in {'FAILED','COMPLETED'}: return {'skip':True}
        await emit('scan.progress',s['event'],'SCAN_PROGRESS')
        return {'skip':False,'hasChanges':bool(context.get('hasChanges'))}

    async def collect(s):
        await log(s,'collect_evidence')
        args={'scan_id':s['event']['scanId']}
        findings=await tool(s,'business','get_scan_findings',args)
        if len(findings)>20 or any(f['ruleId'] not in RULES for f in findings):
            raise ValueError('VISUAL_FINDING_LIMIT')
        policy=await tool(s,'business','get_privacy_policy',args)
        changes=await tool(s,'business','get_scan_changes',args) if s.get('hasChanges') else {}
        image=await tool(s,'business','get_scan_visual_input',args)
        references={}
        rules=sorted({f['ruleId'] for f in findings+changes.get('baselineFindings',[])})
        for rule in rules:
            refs=await tool(s,'rag','get_guideline_details',{'rule_id':rule})
            docs=refs.get('internal',[])+refs.get('external',[]) if isinstance(refs,dict) else refs
            if not {'INTERNAL_POLICY','EXTERNAL_REFERENCE'} <= {r['documentType'] for r in docs}:
                raise ValueError('VISUAL_EVIDENCE_REQUIRED')
            references[rule]=docs
        return {'findings':findings,'policy':policy,'changes':changes,'image':image,'references':references}

    async def prepare_analysis(s):
        await log(s,'prepare_visual_analysis')
        # Deterministic factual packaging, without an additional model review.
        report=attach_change_facts(base_report(s['findings'],s['references'],s['policy']),s['findings'],s['changes'])
        packet=json.loads(prepare(report,s['findings'],s['policy'],s['changes'],s['image'],s['event']['commitSha']))
        return {'report':report,'packet':packet,'commit':s['event']['commitSha'],
                'model':os.environ.get('CSI_REVIEW_VLM_MODEL',MODEL),'stageTrace':[],
                'changeReview':review_changes(s['changes'],s['findings'],s['references'])}

    async def persist(s):
        await log(s,'persist_result')
        await emit('scan.result',s['event'],'SCAN_RESULT',status='COMPLETED',analysisMode='VLM',
                   findings=s['report'],visualReview=s['visualReview'],changeReview=s.get('changeReview'))
        return {}

    async def request_review(s):
        return {'approval':await tool(s,'business','request_security_review',{'scan_id':s['event']['scanId']})}

    async def approval(s):
        await log(s,'approval_interrupt')
        decision=interrupt({'approvalId':s['approval']['id'],'scanId':s['event']['scanId'],'action':'CREATE_SECURITY_REVIEW_ISSUE'})
        if decision.get('approvalId')!=s['approval']['id'] or decision.get('status') not in {'APPROVED','REJECTED'}:
            raise ValueError('APPROVAL_MISMATCH')
        return {'decision':decision}

    async def finalize(s):
        if s.get('decision',{}).get('status')=='APPROVED':
            await tool(s,'business','create_security_issue',{'approval_id':s['approval']['id']})
        await log(s,'finalize')
        return {}

    async def stage_log(stage, state):
        await log(state,stage)

    analysis_graph=build_analysis_graph(emit=stage_log)
    graph=StateGraph(State)
    for name, fn in [('validate_scan',validate),('collect_evidence',collect),('prepare_visual_analysis',prepare_analysis),('visual_analysis',analysis_graph),
                     ('persist_result',persist),('request_review',request_review),('approval_interrupt',approval),('finalize',finalize)]:
        graph.add_node(name,fn)
    graph.add_edge(START,'validate_scan')
    graph.add_conditional_edges('validate_scan',lambda s:END if s.get('skip') else 'collect_evidence')
    graph.add_edge('collect_evidence','prepare_visual_analysis')
    graph.add_edge('prepare_visual_analysis','visual_analysis')
    graph.add_edge('visual_analysis','persist_result')
    graph.add_conditional_edges('persist_result',lambda s:'request_review' if s['findings'] else 'finalize')
    graph.add_edge('request_review','approval_interrupt')
    graph.add_edge('approval_interrupt','finalize')
    graph.add_edge('finalize',END)
    return graph.compile(checkpointer=checkpointer)
