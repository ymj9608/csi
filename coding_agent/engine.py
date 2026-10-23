import difflib
import json
import os
import tempfile
import time
from pathlib import Path
from urllib.parse import urlparse
import httpx
from .profile import ARCHITECTURE_NOTE, CONTEXT_FILES, LEGACY_CONTRACT, MODEL, PROFILE, RULES, SYSTEM, TARGET, response_schema, repair_guidance, select_references
from .repository import Rejected, commit, digest, read, snapshot
from .validation import validate_response
from .verifier import passed, verify
from .verification.contract import BASELINE_FAILURES, complete_security_report
from .reporting import build_review, SCOPE

def patch(before, after):
    lines=difflib.unified_diff(before.splitlines(True),after.splitlines(True),
                              fromfile='a/'+TARGET,tofile='b/'+TARGET)
    return ''.join(line if line.endswith('\n') else line+'\n\\ No newline at end of file\n' for line in lines)

def local_url(url):
    u=urlparse(url)
    if u.scheme!='http' or u.hostname not in {'127.0.0.1','localhost','::1'} or u.username or u.password or u.query or u.fragment or u.path not in {'','/'}:
        raise Rejected('LOCAL_OLLAMA_URL_REQUIRED')
    return url.rstrip('/')

def generate(repo, context, *, ollama_url='http://127.0.0.1:11434', model=MODEL, verifier=verify, chat=None,
             progress=None, diagnostics_dir=None):
    """Bounded generation → validation → one repair. Does not change the repository."""
    started=time.monotonic()
    def notify(phase, attempt=0, note=None):
        if progress:
            payload={'phase':phase,'attempt':attempt,'elapsedMs':int((time.monotonic()-started)*1000)}
            if note:payload['note']=note
            progress(payload)
    url=local_url(ollama_url)
    if model!=MODEL:
        raise Rejected('UNVALIDATED_MODEL')
    sha=commit(repo,context['commitSha'])
    findings=sorted((f for f in context['findings'] if f['filePath']==TARGET and f['ruleId'] in RULES),key=lambda f:(f['ruleId'],f['id']))
    if not findings:
        raise Rejected('PROFILE_NOT_APPLICABLE')
    if context['policy'].get('bcryptMinCost')!=12:
        raise Rejected('PROFILE_POLICY_MISMATCH')
    refs={r['chunkId']:r for f in findings for r in f.get('analysis',{}).get('references',[])}
    if not refs:
        raise Rejected('RETRIEVED_EVIDENCE_REQUIRED')
    sources={path:read(repo,sha,path) for path in CONTEXT_FILES}
    if sum(len(s.encode()) for s in sources.values())>55_000:
        raise Rejected('CONTEXT_TOO_LARGE')
    before=sources[TARGET]
    # Give the actual caller and validation contract without sending the entire repository.
    user={'profile':PROFILE,'commitSha':sha,'policy':context['policy'],
          'findings':[{'id':f['id'],'ruleId':f['ruleId']} for f in findings],
          'references':[{'id':r['chunkId'],'section':r['sectionId'],'documentType':r['documentType'],
                         'excerpt':r['content'][:1200]} for r in select_references(refs)],
          'source':sources[TARGET],'securitySource':sources[CONTEXT_FILES[1]],'legacyVerificationContract':LEGACY_CONTRACT,
          'callerContract':'Lab signup calls validate_lab_signup, hash_signup_password, record_signup(password,email). The DTO rejects passwords over 72 UTF-8 bytes. Existing test expects after-fix version to use bcrypt $2b$12$ and not log password/email. Preserve legacy lab account verification. No production or legal compliance claim.'}
    allowed_refs={r['id'] for r in user['references']}
    messages=[{'role':'system','content':SYSTEM},{'role':'user','content':json.dumps(user,ensure_ascii=False)}]
    attempts=[]
    result={'schemaVersion':1,'profile':PROFILE,'repository':context['repository'],'commitSha':sha,
            'model':model,'engineVersion':'3','findingIds':[f['id'] for f in findings],'referenceIds':sorted(allowed_refs),
            'sourceHashes':{p:digest(s) for p,s in sources.items()},'attempts':attempts,
            'status':'BLOCKED','files':[],'limitations':list(SCOPE)}
    with tempfile.TemporaryDirectory(prefix='csi-coding-') as temp:
        tree=Path(temp)/'source';tree.mkdir()
        snapshot(repo,sha,tree)
        notify('ARCHITECTURE_CONTEXT',note=ARCHITECTURE_NOTE)
        time.sleep(4)  # 화면에서 "아키텍처 참고 중" 단계가 보일 정도로 머무른다 — 실제로는 거의 즉시 끝나는 조회라 지연 없이는 폴링(5초)이 절대 못 잡는다.
        notify('BASELINE')
        baseline=verifier(tree);result['baseline']=baseline
        if (not complete_security_report(baseline) or set(baseline.get('failedTests',[])) != BASELINE_FAILURES
                or baseline.get('failed') != len(BASELINE_FAILURES) or baseline.get('securityPassed') != 6
                or baseline.get('passed',0) < 33 or baseline.get('exitCode') != 1
                or baseline.get('isolation') != 'DOCKER_NETWORK_NONE'):
            raise Rejected('BASELINE_NOT_SUPPORTED')
        for number in range(1,3):
            attempt={'number':number};attempts.append(attempt)
            text=None
            payload={'model':model,'stream':False,'think':False,
                     'format':response_schema(allowed_refs | {f['id'] for f in findings}),'keep_alive':'3m',
                     'options':{'temperature':0,'seed':42,'num_ctx':8192,'num_predict':3000},'messages':messages}
            t=time.monotonic()
            try:
                notify('GENERATING',number)
                if chat:
                    response=chat(payload)
                else:
                    with httpx.Client(timeout=90,trust_env=False) as client:
                        response=client.post(url+'/api/chat',json=payload);response.raise_for_status();response=response.json()
                attempt['generationMs']=int((time.monotonic()-t)*1000)
                if response.get('done_reason')!='stop':raise Rejected('OUTPUT_TRUNCATED')
                text=response['message']['content']
                notify('VALIDATING',number)
                value=json.loads(text)
                after=validate_response(value,before,{f['id'] for f in findings},allowed_refs)
                if after==before:raise Rejected('NO_CHANGE')
                (tree/TARGET).write_text(after)
                notify('VERIFYING',number)
                check=verifier(tree);attempt['verification']=check
                result['lastVerification']=check
                result['review']=build_review(baseline,check,findings,[refs[key] for key in sorted(allowed_refs)])
                if not passed(check):raise Rejected('TESTS_FAILED')
                result.update(status='READY',reason=value['reason'],citedIds=value['evidence_ids'],
                    modelLimitations=value['limitations'],verification=check,
                    files=[{'path':TARGET,'beforeSha256':digest(before),'afterSha256':digest(after),'content':after,
                            'diff':patch(before,after)}])
                break
            except (Rejected,ValueError,KeyError,TypeError,httpx.HTTPError) as exc:
                code=str(exc) if isinstance(exc,Rejected) else 'MODEL_RESPONSE_FAILED'
                attempt.update(error=code,generationMs=attempt.get('generationMs',int((time.monotonic()-t)*1000)))
                if isinstance(exc,Rejected) and exc.details:
                    attempt['diagnostics']=exc.details
                # No free-form stack traces, source values or suggested commands become instructions.
                if number==1:
                    notify('RETRYING',number)
                    if text:messages.append({'role':'assistant','content':text[:24000]})
                    messages.append({'role':'user','content':json.dumps({'validationError':code,
                        'diagnostics':attempt.get('diagnostics',{}),
                        'failedTests':attempt.get('verification',{}).get('failedTests',[]),
                        'repairGuidance':repair_guidance(code,attempt.get('verification',{}).get('failedTests',[])),
                        'instruction':'Correct the candidate once. Preserve the original scope and all functions. Return the complete JSON contract; cite supplied finding and reference IDs.'})})
            finally:
                if diagnostics_dir is not None:
                    directory=Path(diagnostics_dir);directory.mkdir(mode=0o700,parents=True,exist_ok=True)
                    path=directory/f'attempt-{number}.json'
                    with os.fdopen(os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600),'w') as stream:
                        json.dump({'attempt':attempt,'modelResponse':text},stream,ensure_ascii=False,indent=2)
    if result['status']=='BLOCKED':
        result['failureReason']=attempts[-1].get('error','MODEL_RESPONSE_FAILED')
    result['durationMs']=int((time.monotonic()-started)*1000)
    return result
