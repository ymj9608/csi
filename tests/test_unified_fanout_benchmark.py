"""Protocol checks, not model-quality results."""
import base64
import copy
import json
import httpx
import pytest
from scripts import benchmark_unified_fanout as run


def test_compaction_retains_complete_code_contract_and_citations():
    case=run.make_case('fanout',False)
    image={'diagramId':'test','imageBase64':base64.b64encode(b'image').decode(),
           'imageSha256':run.sha(b'image'),'contentType':'image/png','commitSha':'a'*40}
    packet,_,_=run.evidence(case,image)
    compact=run.compact_packet(packet)
    assert compact['sources']==case['sources']
    assert compact['policy']==packet['policy'] and compact['policy']['contract']==case['task']
    assert compact['findings']==packet['findings'] and compact['editable']==packet['editable']
    assert 'task' not in compact and 'codeContext' not in compact['codeEvidence'][0]
    assert packet['codeEvidence'][0]['codeContext']  # Original input remains immutable.
    assert len(json.dumps(compact))<len(json.dumps(packet))


def test_repetition_guard_rejects_loop_without_shortening_nonrepetitive_output(tmp_path,monkeypatch):
    sentence='Preserve internal delivery and remove only external phone fields while retaining event identity and required failure paths. '
    assert run.repeated_output(sentence*2) is None
    assert run.repeated_output(sentence*3)
    assert run.repeated_output(''.join(f'{i}: '+sentence for i in range(20))) is None
    monkeypatch.setattr(run,'REPETITION_GUARD',True)
    actual_client=httpx.Client
    def client(**kwargs):
        events=[{'message':{'content':sentence*3},'done':False}]
        return actual_client(**kwargs,transport=httpx.MockTransport(lambda _:httpx.Response(200,content='\n'.join(json.dumps(e) for e in events))))
    monkeypatch.setattr(run.httpx,'Client',client)
    row=run.request(tmp_path,'repeated',run.VLM,[],{'type':'object'},6000)
    assert row['status']=='FAILED' and 'REPEATED_OUTPUT' in row['error']
    assert row['answerText']==sentence*3
    assert (tmp_path/'repeated-partial.txt').read_text(encoding='utf-8')==sentence*3


def test_three_arms_share_sources_and_never_publish_partial_candidates(tmp_path,monkeypatch):
    case=run.make_case('fanout',False)
    image={'diagramId':'test','imageBase64':base64.b64encode(b'image').decode(),
           'imageSha256':run.sha(b'image'),'contentType':'image/png','commitSha':'a'*40}
    packet,report,refs=run.evidence(case,image)
    requests=[]
    def request(folder,name,model,messages,schema,predict):
        requests.append((folder.name,name,messages))
        if name=='assessment':
            answer={'architecture':{'summary':'Source-derived routes','components':[{'name':'dispatcher','role':'routing','state':'INFERRED','isolationStatus':'UNKNOWN'}]},
                'findings':[{'id':'fanout-phone','red':'External disclosure','blue':'Runtime unverified','remediation':'Preserve required routes',
                             'factIds':['F1'],'citationIds':[refs[0]['chunkId']]}],
                'instructions':[{'findingId':'fanout-phone','text':'Remove only external phone fields and preserve internal data and delivery behavior.',
                                 'referenceIds':[refs[0]['chunkId']]}]}
        else:answer={'files':[{'path':p,'source':s} for p,s in case['solution'].items()]}
        return {'status':'COMPLETED','answer':answer,'answerText':json.dumps(answer),'seconds':1}
    monkeypatch.setattr(run,'request',request);monkeypatch.setattr(run.old,'reset_models',lambda:None)
    monkeypatch.setattr(run,'verify',lambda folder:{'total':8,'passed':7,'exitCode':1,'cases':{},'log':'one failed','seconds':1})
    for arm in run.ARMS:
        result=run.trial(tmp_path,arm,case,image,packet,report)
        assert result['status']=='FAILED' and len(result['attempts'])==2 and 'approvedCandidate' not in result
    assessments=[(arm,msg[1]) for arm,name,msg in requests if name=='assessment']
    assert len(assessments)==3
    for arm,user in assessments:
        content=json.loads(user['content'])
        assert content['sources']==case['sources'] and content['policy']==packet['policy']
        assert ('images' in user)==(arm=='code_image')
        assert ('architecture' in content)==(arm=='structured_text')
        assert case['tests'] not in user['content'] and 'test_contract.py' not in user['content']
    assert report[0]['analysis'].get('mode') is None  # Each arm receives fresh report state.


@pytest.mark.parametrize('arm',run.ARMS)
def test_staged_trial_keeps_coder_tests_and_collects_all_stage_metrics(tmp_path,monkeypatch,arm):
    case=run.make_case('fanout',False)
    image={'diagramId':'test','imageBase64':base64.b64encode(b'image').decode(),
           'imageSha256':run.sha(b'image'),'contentType':'image/png','commitSha':'a'*40}
    packet,report,refs=run.evidence(case,image)
    instruction='Remove only external phone fields and preserve internal data and delivery behavior.'
    calls=[]
    def request(folder,name,model,messages,schema,predict,option_overrides=None):
        calls.append(name)
        if name.startswith('visual_'):
            data=json.loads(messages[1]['content'])
            assert data['sources']==case['sources'] and case['tests'] not in messages[1]['content']
            assert option_overrides['repeat_penalty']==1.0
            assert option_overrides['temperature']==0.7 and option_overrides['presence_penalty']==1.5
            if name.startswith('visual_architecture'):
                assert ('images' in messages[1])==(arm=='code_image')
                assert ('architecture' in data)==(arm=='structured_text')
                answer={'architecture':{'summary':'Routes','components':[{'name':'api','role':'events','state':'INFERRED','isolationStatus':'UNKNOWN'}]},'flows':[],'uncertainties':[]}
            elif name.startswith('visual_security'):
                answer={'findings':[{'id':'fanout-phone','red':'External disclosure','blue':'Runtime unverified',
                    'remediation':'Preserve routes','factIds':['F1'],'citationIds':[refs[0]['chunkId']]}]}
            else:
                answer={'instructions':[{'findingId':'fanout-phone','text':instruction,'referenceIds':[refs[0]['chunkId']]}]}
        else:
            assert model==run.CODER and predict==1800
            assert instruction in json.dumps(messages)
            answer={'files':[{'path':p,'source':s} for p,s in case['solution'].items()]}
        return {'status':'COMPLETED','answer':answer,'answerText':json.dumps(answer),'seconds':2,
                'prompt_eval_count':100,'eval_count':10}
    monkeypatch.setattr(run,'STAGED',True)
    monkeypatch.setattr(run,'request',request)
    monkeypatch.setattr(run.old,'reset_models',lambda:None)
    monkeypatch.setattr(run,'verify',lambda folder:{'total':8,'passed':8,'exitCode':0,'cases':{},'log':'','seconds':1})
    value=run.trial(tmp_path,arm,case,image,packet,report)
    assert value['status']=='PASSED' and value['approvedCandidate']==1
    assert value['vlmSeconds']==6 and value['coderSeconds']==2 and value['verificationSeconds']==1
    assert len(calls)==4 and value['bestCandidate']==value['finalCandidate']==1
    bundle=json.loads((tmp_path/arm/'assessment-bundle.json').read_text(encoding='utf-8'))
    assert bundle['usage']['prompt_eval_count']==300
    assert len(value['assessmentAttempts'])==3
