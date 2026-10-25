import base64
import copy
import hashlib
import json
from types import SimpleNamespace

import httpx
import pytest
import jsonschema
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from agent.csi_agent import graph, visual_review, visual_stages
from agent.csi_agent.analysis import base_report

SHA='a'*40
PNG=base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII=')
IMAGE={'diagramId':'00000000-0000-4000-8000-000000000001','imageBase64':base64.b64encode(PNG).decode(),
       'imageSha256':hashlib.sha256(PNG).hexdigest(),'contentType':'image/png','commitSha':SHA}
FINDING={'id':'finding','ruleId':'SEC-05','filePath':'service.py','startLine':1,'endLine':1,
         'maskedCodeEvidence':'log.info("[REDACTED]", phone)','evidenceStatus':'SUSPECTED'}
POLICY={'version':'test','approvedFields':['email'],'restrictedFields':['phoneNumber']}
INTERNAL={'chunkId':'ref','sectionId':'POL-05','sectionTitle':'Logs','documentType':'INTERNAL_POLICY','pageNumber':1,'content':'Do not log contact data.'}
EXTERNAL={**INTERNAL,'chunkId':'ext','documentType':'EXTERNAL_REFERENCE'}


def report():
    return base_report([FINDING],{'SEC-05':[INTERNAL,EXTERNAL]},POLICY)


def answer():
    return {'architecture':{'summary':'API and external logging','components':[{
        'name':'API','role':'Requests','isolationStatus':'UNKNOWN','state':'OBSERVED'}]},
        'findings':[{'id':'finding','red':'Contact value may leak through logs.','blue':'Runtime destination is unknown.',
                     'remediation':'Remove contact data, retain operational events.','factIds':['F1'],'citationIds':['ref']}],
        'instructions':[{'findingId':'finding','text':'Remove phone data from log arguments. Preserve the event, internal records and validation.',
                         'referenceIds':['ref']}]}


def test_generation_schema_binds_id_namespaces_without_shortening_prose():
    schema=visual_review.output_schema(report())
    jsonschema.validate(answer(),schema)
    assert schema['$defs']['Instruction']['properties']['text']['maxLength']==3000
    assert schema['$defs']['LLMItem']['properties']['red']['maxLength']==1600
    bad=answer();bad['findings'][0]['factIds']=['ref']
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
    bad=answer();bad['instructions'][0]['referenceIds']=['F1']
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
    bad=answer();bad['findings'].append(copy.deepcopy(bad['findings'][0]))
    with pytest.raises(jsonschema.ValidationError):jsonschema.validate(bad,schema)
    empty={'architecture':answer()['architecture'],'findings':[],'instructions':[]}
    jsonschema.validate(empty,visual_review.output_schema([]))


@pytest.mark.asyncio
async def test_three_stages_keep_json_and_natural_instruction_contract():
    requests=[]
    replies=[{'architecture':answer()['architecture'],'flows':[],'uncertainties':['Runtime unknown']},
             {'findings':answer()['findings']},{'instructions':answer()['instructions']}]
    def handle(request):
        body=json.loads(request.content);requests.append(body)
        packet=json.loads(body['messages'][1]['content'])
        assert packet['codeEvidence'][0]['maskedCodeEvidence']==FINDING['maskedCodeEvidence']
        assert body['options']['repeat_penalty']==1.0
        assert body['options']['temperature']==0.7 and body['options']['presence_penalty']==1.5
        assert body['truncate'] is False and body['shift'] is False
        assert body['options']['num_predict']==2000
        if len(requests)==1:
            assert body['messages'][1]['images']==[IMAGE['imageBase64']]
            assert 'policy' not in packet and 'findings' not in packet
        elif len(requests)==2:
            assert 'images' not in body['messages'][1]
            assert packet['policy']==POLICY
            assert packet['findings'][0]['citations'][0]['id']=='ref'
        else:
            assert 'policy' not in packet and 'images' not in body['messages'][1]
            assert packet['security']['findings']==answer()['findings']
        return httpx.Response(200,json={'done':True,'done_reason':'stop',
            'prompt_eval_count':100,'eval_count':20,'total_duration':300,
            'message':{'content':json.dumps(replies[len(requests)-1])}})
    items=report()
    result=await visual_review.assess(items,[FINDING],POLICY,{'status':'NOT_PROVIDED'},IMAGE,SHA,transport=httpx.MockTransport(handle))
    assert len(requests)==3 and result['instructions'][0]['text']==answer()['instructions'][0]['text']
    assert items[0]['analysis']['mode']=='VLM' and result['architecture']==answer()['architecture']
    assert result['usage']=={'prompt_eval_count':300,'eval_count':60,'total_duration':900}
    assert result['mode']==visual_review.VERSION
    assert [t['tool'] for t in items[0]['analysis']['orchestration']['trace']]==list(visual_stages.STAGES)


@pytest.mark.parametrize('mutation',['reference','finding','duplicate','json_instruction','fact','long_role','extra','blank'])
def test_invalid_assessment_is_not_publishable(mutation):
    raw=answer()
    if mutation=='reference':raw['instructions'][0]['referenceIds']=['invented']
    if mutation=='finding':raw['findings'][0]['id']='other'
    if mutation=='duplicate':raw['instructions'].append(raw['instructions'][0])
    if mutation=='json_instruction':raw['instructions'][0]['text']='{"instructions":"not natural text"}'
    if mutation=='fact':raw['findings'][0]['factIds']=['invented']
    if mutation=='long_role':raw['architecture']['components'][0]['role']='x'*41
    if mutation=='extra':raw['architecture']['bypassApproval']=True
    if mutation=='blank':raw['architecture']['summary']='   '
    with pytest.raises(ValueError):visual_review.validate(raw,report(),IMAGE,SHA,'qwen3-vl:8b')


@pytest.mark.parametrize('mutation',['commit','image','references','size'])
def test_invalid_or_oversized_input_blocked_before_model(mutation):
    image=copy.deepcopy(IMAGE);items=report();changes={}
    if mutation=='commit':image['commitSha']='b'*40
    if mutation=='image':image['imageSha256']='b'*64
    if mutation=='references':items[0]['analysis']['references']=[]
    if mutation=='size':changes={'diff':'x'*80001}
    with pytest.raises(ValueError):visual_review.prepare(items,[FINDING],POLICY,changes,image,SHA)


@pytest.mark.asyncio
@pytest.mark.parametrize('reply',[{'done_reason':'length','message':{'content':'{}'}},{'done_reason':'stop','message':{'content':'invalid'}}])
async def test_truncation_or_malformed_result_is_not_success(reply):
    with pytest.raises(ValueError):
        await visual_review.assess(report(),[FINDING],POLICY,{},IMAGE,SHA,transport=httpx.MockTransport(lambda _:httpx.Response(200,json=reply)))


def setup(monkeypatch, missing=False):
    events=[];calls=[];model=[]
    monkeypatch.setenv('CSI_INTERNAL_TOKEN','test-token')
    class Client:
        def __init__(self,*a,**kw):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def call_tool(self,name,args):
            calls.append(name)
            values={'get_scan_context':{'repository':'org/demo','commitSha':SHA,'status':'QUEUED'},
                    'get_scan_findings':[FINDING],'get_privacy_policy':POLICY,'get_scan_visual_input':IMAGE,
                    'get_guideline_details':{'internal':[INTERNAL],'external':[] if missing else [EXTERNAL]},
                    'request_security_review':{'id':'approval'},'create_security_issue':{'id':'issue'}}
            return SimpleNamespace(data=values[name],is_error=False)
    async def call_model(spec):
        model.append(spec['stage'])
        outputs=[{'architecture':answer()['architecture'],'flows':[],'uncertainties':[]},
                 {'findings':answer()['findings']},{'instructions':answer()['instructions']}]
        return {'answer':outputs[visual_stages.STAGES.index(spec['stage'])],'usage':{}}
    async def emit(topic,event,kind,**data):events.append((kind,data))
    monkeypatch.setattr(graph,'Client',Client);monkeypatch.setattr(visual_stages,'call_model',call_model)
    return graph.build_graph(InMemorySaver(),emit),events,calls,model


@pytest.mark.asyncio
async def test_scan_to_approval_has_no_intermediate_review_model(monkeypatch):
    flow,events,calls,model=setup(monkeypatch)
    config={'configurable':{'thread_id':'test'}}
    event={'scanId':'scan','repository':'org/demo','commitSha':SHA}
    await flow.ainvoke({'event':event},config)
    results=[data for kind,data in events if kind=='SCAN_RESULT']
    assert len(results)==1 and results[0]['analysisMode']=='VLM'
    assert results[0]['visualReview']['instructions'] and results[0]['visualReview']['architecture']
    assert model==list(visual_stages.STAGES) and 'compare_policy_with_findings' not in calls
    assert 'create_security_issue' not in calls
    await flow.ainvoke(Command(resume={'approvalId':'approval','status':'REJECTED'}),config)
    assert model==list(visual_stages.STAGES) and 'create_security_issue' not in calls
    assert not (await flow.aget_state(config)).next


@pytest.mark.asyncio
async def test_missing_rag_stops_before_model_and_result(monkeypatch):
    flow,events,calls,model=setup(monkeypatch,missing=True)
    with pytest.raises(ValueError,match='EVIDENCE_REQUIRED'):
        await flow.ainvoke({'event':{'scanId':'scan','repository':'org/demo','commitSha':SHA}}, {'configurable':{'thread_id':'test'}})
    assert not model and not any(kind=='SCAN_RESULT' for kind,_ in events)


@pytest.mark.asyncio
async def test_parent_graph_resumes_failed_subgraph_without_repeating_image(monkeypatch):
    flow,events,calls,model=setup(monkeypatch)
    original=visual_stages.call_model
    failed=False
    async def interrupted(spec):
        nonlocal failed
        if spec['stage']=='visual_security' and not failed:
            failed=True
            raise ValueError('VISUAL_REPEATED_OUTPUT')
        return await original(spec)
    monkeypatch.setattr(visual_stages,'call_model',interrupted)
    config={'configurable':{'thread_id':'subgraph-recovery'}}
    with pytest.raises(ValueError,match='REPEATED_OUTPUT'):
        await flow.ainvoke({'event':{'scanId':'scan','repository':'org/demo','commitSha':SHA}},config)
    assert not any(kind=='SCAN_RESULT' for kind,_ in events)
    await flow.ainvoke(None,config)
    assert model==list(visual_stages.STAGES)
    assert calls.count('get_scan_visual_input')==1
    assert len([1 for kind,_ in events if kind=='SCAN_RESULT'])==1
