"""Pull CSI jobs and run inference locally; upload the reviewed file proposal and proof."""
import argparse
import json
import os
import tempfile
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse
import httpx
from dotenv import dotenv_values
from .engine import generate
from .profile import TARGET
from .repository import Rejected, commit, digest, git, read
from .validation import validate_code

def backend_url(value):
    u=urlparse(value)
    if u.username or u.password or u.query or u.fragment or u.path not in {'','/'} or not u.hostname:
        raise Rejected('BACKEND_URL')
    if u.scheme!='https' and not (u.scheme=='http' and u.hostname in {'localhost','127.0.0.1','::1'}):
        raise Rejected('HTTPS_BACKEND_REQUIRED')
    return value.rstrip('/')

def client(args):
    token=os.environ.get('CSI_INTERNAL_TOKEN') or dotenv_values(args.env_file).get('CSI_INTERNAL_TOKEN','')
    if len(token)<32:raise Rejected('INTERNAL_TOKEN_REQUIRED')
    return httpx.Client(base_url=backend_url(args.backend),headers={'Authorization':'Bearer '+token},timeout=20,trust_env=False)

def post(api,path,payload):
    r=api.post(path,json=payload);r.raise_for_status();return r.json()

def write_private(path,value):
    """Persist recoverable results without a world-readable intermediate file."""
    path.parent.mkdir(parents=True,exist_ok=True)
    descriptor,temporary_name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    temporary=Path(temporary_name)  # mkstemp creates a fresh file with mode 0600.
    try:
        with os.fdopen(descriptor,'w',encoding='utf-8') as stream:
            json.dump(value,stream,ensure_ascii=False,indent=2)
            stream.flush();os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)

def deliver_result(api,output,job_id,lease_token,result):
    """Retry an immutable result; a transport failure must not fail the generation."""
    pending=output/(job_id+'.pending.json')
    for attempt in range(1,4):
        try:
            reply=post(api,f'/internal/coding-proposals/{job_id}/result',{'leaseToken':lease_token,'result':result})
            if not isinstance(reply,dict) or reply.get('status') not in {'READY','BLOCKED','APPROVED','REJECTED'}:
                raise ValueError('Unrecognized delivery acknowledgement')
        except (httpx.HTTPError,ValueError) as exc:
            status=exc.response.status_code if isinstance(exc,httpx.HTTPStatusError) else None
            retryable=status is None or status in {408,429} or status>=500
            if not retryable:
                # A stale lease or rejected payload is never claimed again or overwritten.
                write_private(output/(job_id+'.delivery.json'),{'status':'REJECTED','httpStatus':status})
                pending.unlink(missing_ok=True)
                print(json.dumps({'proposalId':job_id,'status':'RESULT_DELIVERY_REJECTED','httpStatus':status}),flush=True)
                return False
            if attempt<3:
                print(json.dumps({'proposalId':job_id,'status':'RESULT_DELIVERY_RETRYING','attempt':attempt}),flush=True)
                time.sleep(attempt)
                continue
            print(json.dumps({'proposalId':job_id,'status':'RESULT_DELIVERY_PENDING',
                              'errorCode':'BACKEND_RESULT_UNAVAILABLE'}),flush=True)
            return False
        pending.unlink(missing_ok=True)
        print(json.dumps({'proposalId':job_id,'status':reply.get('status',result['status']),
                          'durationMs':result['durationMs']}),flush=True)
        return True

def resume_deliveries(api,output,repository):
    """Resume only this backend/repository's pending uploads, without model inference."""
    complete=True
    for pending in sorted(output.glob('*.pending.json')):
        try:
            job_id=str(uuid.UUID(pending.name.removesuffix('.pending.json')))
            receipt=json.loads(pending.read_text())
            if receipt['backend']!=str(api.base_url) or receipt['repository']!=repository:
                continue
            result=json.loads((output/(job_id+'.json')).read_text())
            if result.get('repository')!=repository:
                raise ValueError('Pending result repository differs')
            deliver_result(api,output,job_id,receipt['leaseToken'],result)
            complete=complete and not pending.exists()
        except (ValueError,KeyError,OSError):
            # Do not transmit corrupt/partial local files or print their contents.
            print(json.dumps({'status':'LOCAL_RESULT_UNREADABLE','file':pending.name}),flush=True)
            complete=False
    return complete

def process(api,repo,job,output,ollama_url):
    job_id=str(uuid.UUID(job['id']))
    try:
        def progress(value):
            print(json.dumps({'proposalId':job_id,**value}),flush=True)
            try:
                response=api.post(f'/internal/coding-proposals/{job_id}/progress',
                    json={'leaseToken':job['leaseToken'],**value},timeout=3)
                response.raise_for_status()
            except httpx.HTTPError:
                print(json.dumps({'proposalId':job_id,'status':'PROGRESS_UNAVAILABLE'}),flush=True)
        result=generate(repo,job,ollama_url=ollama_url,progress=progress,diagnostics_dir=output/job_id)
        write_private(output/(job_id+'.json'),result)
        write_private(output/(job_id+'.pending.json'),{'leaseToken':job['leaseToken'],
            'repository':job['repository'],'backend':str(api.base_url)})
    except Exception as exc:
        code=str(exc) if isinstance(exc,Rejected) else 'LOCAL_RESULT_STORAGE_FAILED' if isinstance(exc,OSError) else 'WORKER_FAILED'
        try:post(api,f'/internal/coding-proposals/{job_id}/failure',{'leaseToken':job['leaseToken'],'errorCode':code})
        except httpx.HTTPError:pass  # Lease expiry makes an unreachable worker visible in CSI.
        print(json.dumps({'proposalId':job_id,'status':'FAILED','errorCode':code}),flush=True)
        return False
    return deliver_result(api,output,job_id,job['leaseToken'],result) and result['status']=='READY'

def apply_approved(api,repo,proposal_id,destination,repository='ymj9608/Lichu'):
    """Explicit operator action: prepare an approved patch in a NEW local branch/worktree."""
    proposal_id=str(uuid.UUID(proposal_id))
    r=api.get('/internal/coding-proposals/'+proposal_id);r.raise_for_status();job=r.json()
    if job['status']!='APPROVED':raise Rejected('ADMIN_APPROVAL_REQUIRED')
    if job['repository']!=repository:raise Rejected('REPOSITORY_MISMATCH')
    result=job['result'];sha=commit(repo,job['commitSha'])
    if git(repo,'rev-parse','HEAD').decode().strip()!=sha or git(repo,'status','--porcelain'):
        raise Rejected('STALE_OR_DIRTY_CHECKOUT')
    files=result['files']
    if len(files)!=1 or files[0]['path']!=TARGET:raise Rejected('EDIT_SCOPE')
    item=files[0];before=read(repo,sha,TARGET)
    if digest(before)!=item['beforeSha256'] or digest(item['content'])!=item['afterSha256']:raise Rejected('CONTENT_DIGEST_MISMATCH')
    validate_code(before,item['content'])
    destination=destination.resolve()
    if destination.exists():raise Rejected('DESTINATION_EXISTS')
    branch='csi/coding-'+proposal_id
    git(repo,'worktree','add','-b',branch,str(destination),sha)
    (destination/TARGET).write_text(item['content'])
    # No hooks, commits, pushes, merges, or execution of the candidate occurs here.
    return {'branch':branch,'worktree':str(destination),'baseCommit':sha,'status':'PREPARED_FOR_REVIEW'}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--backend',default='http://127.0.0.1:8080');p.add_argument('--env-file',type=Path,default=Path('.env'))
    p.add_argument('--repository',default='ymj9608/Lichu');p.add_argument('--repo',type=Path,required=True)
    p.add_argument('--ollama-url',default='http://127.0.0.1:11434');p.add_argument('--once',action='store_true')
    p.add_argument('--output',type=Path,default=Path('.runtime/coding'))
    p.add_argument('--apply-approved',metavar='PROPOSAL_UUID');p.add_argument('--destination',type=Path)
    args=p.parse_args();repo=args.repo.resolve(strict=True)
    with client(args) as api:
        if args.apply_approved:
            if args.destination is None:p.error('--destination is required with --apply-approved')
            print(json.dumps(apply_approved(api,repo,args.apply_approved,args.destination,args.repository),ensure_ascii=False));return
        while True:
            try:
                if not resume_deliveries(api,args.output,args.repository):
                    if args.once:raise SystemExit(1)
                    time.sleep(5)
                    continue
                claim=post(api,'/internal/coding-proposals/claim',{'repository':args.repository})
                if claim['available']:
                    success=process(api,repo,claim['job'],args.output,args.ollama_url)
                    if args.once and not success:raise SystemExit(1)
            except httpx.HTTPError:
                print(json.dumps({'status':'BACKEND_UNAVAILABLE'}),flush=True)
                if args.once:raise SystemExit(1)
            if args.once:return
            time.sleep(5)

if __name__=='__main__':
    try:main()
    except KeyboardInterrupt:pass
    except Rejected as exc:raise SystemExit(str(exc))
