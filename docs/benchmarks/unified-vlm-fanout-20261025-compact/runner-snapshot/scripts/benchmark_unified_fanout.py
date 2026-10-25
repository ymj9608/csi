"""Three paired input ablations of the unified VLM handoff, with real local models.

Uses production assessment prompt/schema/validator; benchmark-only no-image ablations.
Frozen synthetic fixture, all source files in every arm, no security-review LLM,
one assessment, at most two coder calls, independent WASI verification.
This is not the production Docker/API end-to-end test.
"""
import argparse
import base64
import copy
import csv
import hashlib
import json
import random
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
import jsonschema
from agent.csi_agent import visual_review as vr
from scripts import benchmark_windows_vlm as old
from scripts.vlm_experiment_data import make_case, materialize
from scripts.experiment_wasi import verify

ARMS = ['full_code', 'structured_text', 'code_image']
VLM = 'qwen3-vl:8b-instruct-q4_K_M'
CODER = old.CODER
OPTIONS = {'temperature':0, 'seed':42, 'num_ctx':8192, 'num_thread':3}
VLM_OPTIONS = {**OPTIONS, 'num_ctx':32768}
TIMEOUT = 900
COMPACT_INPUT = False
REPETITION_GUARD = False
TESTS = [('test_internal_phone','내부 SMS'),('test_external_normal','정상 경로 유출 차단'),
         ('test_external_failure','실패 경로 유출 차단'),('test_store','회원 정보 보존'),
         ('test_replay','복구 기록 보존'),('test_deliveries','정상 전송 유지'),
         ('test_failure_diagnostics','장애 진단 유지'),('test_input_not_mutated','직접 호출·원본 보존')]
write = old.write
sha = old.sha


def evidence(case, image):
    catalog=json.loads((ROOT/'rag/catalog.json').read_text(encoding='utf-8'))
    refs=[next(r for r in catalog if r['sectionId']==section) for section in ['POL-06','REF-01']]
    findings=[{'id':'fanout-phone','ruleId':'POL-01','filePath':'dispatcher.py',
        'startLine':6,'endLine':6,'evidenceStatus':'SUSPECTED',
        'maskedCodeEvidence':'publish(channel, event)','codeContext':case['sources']['dispatcher.py']}]
    report=[{'id':'fanout-phone','analysis':{
        'facts':[{'id':'F1','text':'dispatcher.py passes the original signup event to each selected recipient.'}],
        'unknowns':['Recipient trust and failure behavior must be established from supplied evidence.'],
        'red':'Raw phone may reach external recipients.', 'blue':'Synthetic fixture; not a legal compliance judgment.',
        'remediation':'Repair the disclosure while preserving the supplied functional contract.',
        'references':refs}}]
    policy={'version':'synthetic-fanout-contract-v1','contract':case['task'],
            'referenceScope':'Frozen excerpts from the repository reference corpus; not fresh legal advice.'}
    content=json.loads(vr.prepare(report,findings,policy,{'status':'NOT_PROVIDED','reason':'Frozen synthetic source, no invented commit diff.'},image,image['commitSha']))
    content.update(sources=case['sources'],editable=case['editable'],task=case['task'])
    return content,report,refs


def compact_packet(packet):
    """Remove exact duplicate evidence only; retain every source, reference and contract."""
    packet=copy.deepcopy(packet)
    if packet.get('task') == packet.get('policy',{}).get('contract'):
        del packet['task']
    for item in packet.get('codeEvidence',[]):
        if item.get('codeContext') == packet.get('sources',{}).get(item.get('filePath')):
            item.pop('codeContext',None)
    return packet


def repeated_output(content):
    """Three consecutive copies of a long span indicate a loop, not a short answer."""
    match=re.search(r'(.{100,400}?)\1\1',content[-4096:],re.DOTALL)
    return match.group(1) if match else None


def request(folder, name, model, messages, schema, predict, option_overrides=None):
    payload={'model':model,'messages':messages,'format':schema,'stream':True,'think':False,
             'keep_alive':0,'options':{**(VLM_OPTIONS if model==VLM else OPTIONS),'num_predict':predict,**(option_overrides or {})}}
    cleaned=[{k:v for k,v in m.items() if k!='images'} | ({'imageHashes':[sha(base64.b64decode(x)) for x in m['images']]} if 'images' in m else {}) for m in messages]
    write(folder/(name+'-input.json'),{**payload,'messages':cleaned})
    row={'status':'FAILED','model':model}; start=time.perf_counter();content=[];last_checked=0
    try:
        # A missing model read deadline is explicit; connection failures remain bounded.
        timeout=httpx.Timeout(connect=30,read=TIMEOUT,write=60,pool=30)
        raw={};began=time.monotonic()
        with httpx.Client(base_url='http://127.0.0.1:11434',timeout=timeout,trust_env=False) as api:
            with (folder/(name+'-stream.jsonl')).open('w',encoding='utf-8') as log, (folder/(name+'-partial.txt')).open('w',encoding='utf-8') as partial:
                with api.stream('POST','/api/chat',json=payload) as response:
                    response.raise_for_status()
                    for line in response.iter_lines():
                        if TIMEOUT is not None and time.monotonic()-began>TIMEOUT:raise TimeoutError('MODEL_WALL_TIMEOUT')
                        if not line:continue
                        event=json.loads(line)
                        if event.get('error'):raise ValueError(event['error'])
                        value=event.get('message',{}).get('content','')
                        if value:content.append(value);partial.write(value);partial.flush()
                        # Keep final output and metrics, not private reasoning text.
                        clean={k:v for k,v in event.items() if k!='message'}
                        clean['content']=value;log.write(json.dumps(clean,ensure_ascii=False)+'\n');log.flush()
                        if REPETITION_GUARD and model==VLM:
                            combined=''.join(content)
                            if len(combined)-last_checked>=128 or event.get('done'):
                                last_checked=len(combined)
                                repeated=repeated_output(combined)
                                if repeated:
                                    row['repeatedSpan']=repeated
                                    raise ValueError('REPEATED_OUTPUT: three consecutive copies of a long passage')
                        if event.get('done'):raw=event
        raw['message']={'role':'assistant','content':''.join(content)}
        write(folder/(name+'-raw.json'),raw)
        row.update({k:raw.get(k) for k in ['prompt_eval_count','eval_count','load_duration','prompt_eval_duration','eval_duration','done_reason']})
        row['answerText']=raw.get('message',{}).get('content','')
        if raw.get('done_reason')!='stop':raise ValueError('OUTPUT_INCOMPLETE')
        answer=json.loads(row['answerText']);jsonschema.validate(answer,schema)
        if raw.get('prompt_eval_count',0)+raw.get('eval_count',0)>=payload['options']['num_ctx']:raise ValueError('CONTEXT_LIMIT')
        row.update(status='COMPLETED',answer=answer)
    except Exception as exc:
        row['error']=type(exc).__name__+': '+str(exc)[:400]
        row.setdefault('answerText',''.join(content))
    row['seconds']=round(time.perf_counter()-start,3);write(folder/(name+'.json'),row)
    print(json.dumps({'call':name,'model':model,'status':row['status'],'seconds':row['seconds'],'error':row.get('error')}),flush=True)
    return row


def trial(out, arm, case, image, packet, original_report):
    folder=out/arm;folder.mkdir()
    old.reset_models()
    result={'arm':arm,'status':'BLOCKED','attempts':[],'vlmSeconds':0,'coderSeconds':0,'verificationSeconds':0}
    started=time.perf_counter()
    try:
        content=compact_packet(packet) if COMPACT_INPUT else copy.deepcopy(packet)
        if arm=='structured_text':content['architecture']=case['graph']
        user={'role':'user','content':json.dumps(content,ensure_ascii=False,separators=(',',':')) if COMPACT_INPUT else json.dumps(content,ensure_ascii=False)}
        if arm=='code_image':user['images']=[image['imageBase64']]
        system=vr.PROMPT+'\nBenchmark input ablation: use only the supplied modalities. If an image is absent, infer architecture from source/config and label it INFERRED. All supplied source files are complete.'
        assessment=request(folder,'assessment',VLM,[{'role':'system','content':system},user],vr.output_schema(original_report),6000)
        result['vlmSeconds']=assessment['seconds']
        result['assessmentAttempts']=[{'call':'assessment','status':assessment['status'],'seconds':assessment['seconds'],'error':assessment.get('error')}]
        if REPETITION_GUARD and 'REPEATED_OUTPUT' in assessment.get('error',''):
            # A separately recorded recovery; do not pass the repeated partial output to the coder.
            assessment=request(folder,'assessment-retry',VLM,[{'role':'system','content':system},user],vr.output_schema(original_report),6000,
                               option_overrides={'repeat_penalty':1.1,'repeat_last_n':256})
            result['vlmSeconds']+=assessment['seconds']
            result['assessmentAttempts'].append({'call':'assessment-retry','status':assessment['status'],'seconds':assessment['seconds'],'error':assessment.get('error'),
                                                'options':{'repeat_penalty':1.1,'repeat_last_n':256}})
        if assessment['status']!='COMPLETED':raise ValueError(assessment.get('error','ASSESSMENT_FAILED'))
        report=copy.deepcopy(original_report)
        bundle=vr.validate(assessment['answer'],report,image,image['commitSha'],VLM)
        # No-image controls must not be mistaken for production image assessments.
        bundle.update(benchmarkArm=arm,imageProvided=arm=='code_image')
        if arm!='code_image':bundle['imageSha256']=None;bundle['diagramId']=None
        write(folder/'assessment-bundle.json',bundle);write(folder/'security-report.json',report)
        instruction='\n'.join(i['text'] for i in bundle['instructions'])
        (folder/'instruction.txt').write_text(instruction+'\n',encoding='utf-8')
        previous=None;feedback=None
        for attempt in (1,2):
            messages,schema=old.coder_request(case,instruction,case['sources'],previous,feedback)
            coder=request(folder,f'coder-{attempt}',CODER,messages,schema,1800)
            result['coderSeconds']+=coder['seconds']
            record={'attempt':attempt,'status':'INVALID','verification':None}
            previous=coder.get('answerText')
            try:
                if coder['status']!='COMPLETED':raise ValueError(coder.get('error','CODER_FAILED'))
                patch=old.validate_patch(coder['answer'],case,case['sources'])
                candidate=folder/f'candidate-{attempt}';materialize(case,candidate,patch)
                validation=verify(candidate);write(candidate/'validation.json',validation)
                result['verificationSeconds']+=validation['seconds']
                record.update(status='VERIFIED',verification=validation)
                feedback={k:v for k,v in validation.items() if k!='log'}
                if validation['exitCode']!=0:feedback['failureDetails']=validation.get('log','')[-3500:]
                if validation['exitCode']==0 and validation['total']==8 and validation['passed']==8:
                    result['status']='PASSED';result['approvedCandidate']=attempt
            except Exception as exc:record['error']=str(exc);feedback={'error':str(exc)}
            result['attempts'].append(record)
            write(folder/'progress.json',result)
            if result['status']=='PASSED':break
        if result['status']!='PASSED':result['status']='FAILED'
    except Exception as exc:result['error']=type(exc).__name__+': '+str(exc)
    finally:
        result['totalSeconds']=round(time.perf_counter()-started,3)
        verified=[a for a in result['attempts'] if a['verification']]
        result['bestCandidate']=max(verified,key=lambda a:a['verification']['passed'])['attempt'] if verified else None
        result['finalCandidate']=result['attempts'][-1]['attempt'] if result['attempts'] else None
        write(folder/'result.json',result)
        print(json.dumps({'arm':arm,'status':result['status'],'seconds':result['totalSeconds']}),flush=True)
        old.reset_models()
    return result


def summarize(out, results):
    rows=[];by_arm={r['arm']:r for r in results}
    for test,label in TESTS:
        row={'test':test,'label':label}
        for arm in ARMS:
            r=by_arm.get(arm,{})
            a=next((a for a in r.get('attempts',[]) if a['attempt']==r.get('bestCandidate')),None)
            row[arm]=a['verification']['cases'].get(test,'NOT_RUN') if a else 'NOT_RUN'
        rows.append(row)
    with (out/'test-matrix.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.DictWriter(f,fieldnames=['test','label',*ARMS]);w.writeheader();w.writerows(rows)
    write(out/'comparison.json',results)


def main():
    global TIMEOUT,COMPACT_INPUT,REPETITION_GUARD
    parser=argparse.ArgumentParser();parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--no-time-limit',action='store_true',help='No model response deadline; test isolation and token/attempt bounds remain.')
    parser.add_argument('--arms',nargs='+',choices=ARMS,default=ARMS)
    parser.add_argument('--compact-input',action='store_true',help='Remove exact duplicate task/code fields and JSON whitespace; keep all evidence.')
    parser.add_argument('--repetition-guard',action='store_true',help='Reject repeated output; retry once with explicit repeat penalty, preserving both attempts.')
    args=parser.parse_args()
    if args.no_time_limit:TIMEOUT=None
    COMPACT_INPUT=args.compact_input;REPETITION_GUARD=args.repetition_guard
    out=args.out.resolve();out.mkdir(parents=True,exist_ok=False)
    case=make_case('fanout',False)
    original=ROOT/'docs/benchmarks/windows-vlm-20261024-v3/cases/fanout-small/architecture.png'
    (out/'architecture.png').write_bytes(original.read_bytes())
    snapshot=sha(json.dumps(case['sources'],sort_keys=True))
    image={'diagramId':'benchmark-fanout-small','imageBase64':base64.b64encode(original.read_bytes()).decode(),
           'imageSha256':sha(original.read_bytes()),'contentType':'image/png','commitSha':snapshot}
    packet,report,refs=evidence(case,image)
    write(out/'common-input.json',packet);write(out/'references.json',refs);write(out/'architecture.json',case['graph'])
    order=list(dict.fromkeys(args.arms));random.Random(42).shuffle(order)
    files=['scripts/benchmark_unified_fanout.py','scripts/benchmark_windows_vlm.py','scripts/vlm_experiment_data.py','scripts/experiment_wasi.py','agent/csi_agent/visual_review.py','agent/csi_agent/analysis.py']
    with old.client() as api:models=api.get('/api/tags').json();version=api.get('/api/version').json()
    protocol={'createdAt':datetime.now(timezone.utc).isoformat(),'case':'fanout-small','flow':vr.VERSION,
        'vlm':VLM,'coder':CODER,'options':OPTIONS,'vlmOptions':VLM_OPTIONS,'timeoutPerCallSeconds':TIMEOUT,'vlmOutputLimit':6000,'coderOutputLimit':1800,
        'vlmCallsPerArm':1,'maxVlmCallsPerArm':2 if REPETITION_GUARD else 1,'compactInput':COMPACT_INPUT,'repetitionGuard':REPETITION_GUARD,
        'repetitionRecoveryOptions':{'repeat_penalty':1.1,'repeat_last_n':256} if REPETITION_GUARD else None,
        'maxCodingAttempts':2,'repetitions':1,'streaming':True,'outputLanguage':'Original production Korean prompt; no English override or additional brevity directive','order':order,'models':models,'ollama':version,
        'sourcesSha256':snapshot,'pythonFiles':4,'configurationFiles':1,'sources':{k:sha(v) for k,v in case['sources'].items()},
        'testsSha256':sha(case['tests']),'imageSha256':image['imageSha256'],'catalogSha256':sha((ROOT/'rag/catalog.json').read_bytes()),
        'primary':'Only an actual 8/8 verified candidate is releasable. First all-pass stops retries.',
        'secondary':'Best verified candidate among at most two; final attempt is separately retained, never conflated.',
        'limitations':['Synthetic single case; one run per input condition; no general causal or performance claim.',
            'Frozen document excerpts, not live RAG retrieval quality or legal compliance evaluation.',
            'Original production assessment prompt/schema/validation and VLM context/output limits; benchmark coder uses complete-source patches and WASI, not production edits/Docker integration.',
            'All source/config in every arm; only additional graph modality changes. Different from prior search-based arms.',
            'Production requires an image; no-image ablations exist only in this experiment.',
            'Old results remain historical; these are fresh calls, not cached proposals.'],
        'gitHead':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
        'runnerHashes':{p:sha((ROOT/p).read_bytes()) for p in files}}
    write(out/'protocol.json',protocol)
    for p in files:
        target=out/'runner-snapshot'/p;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes((ROOT/p).read_bytes())
    for name,patch in [('original',None),('known-correct',case['solution'])]:
        folder=out/'controls'/name;materialize(case,folder,patch);v=verify(folder);write(folder/'validation.json',v)
        if v['total']!=8 or v['passed']!=(5 if name=='original' else 8):raise ValueError('CONTROL_FAILED')
    results=[]
    for arm in order:
        print(json.dumps({'start':arm}),flush=True)
        results.append(trial(out,arm,case,image,packet,report));summarize(out,results)
    write(out/'completed.json',{'at':datetime.now(timezone.utc).isoformat()})


if __name__=='__main__':main()
