"""Run real static scanning and submit signed synthetic fixtures through the actual pipeline."""
import argparse,json,os,time,hashlib
from pathlib import Path
import httpx
from scan import scan
from submit import submit
ROOT=Path(__file__).resolve().parents[1]
def env():
    for line in (ROOT/'.env').read_text().splitlines():
        if '=' in line:
            k,v=line.split('=',1);os.environ.setdefault(k,v)
def login(base):
    c=httpx.Client(base_url=base,timeout=15)
    csrf=c.get('/api/auth/csrf').json()['token']
    r=c.post('/api/auth/login',json={'username':os.environ.get('CSI_ADMIN_USERNAME','reviewer'),'password':os.environ['CSI_ADMIN_PASSWORD']},headers={'X-CSRF-TOKEN':csrf});r.raise_for_status()
    c.headers['X-CSRF-TOKEN']=c.get('/api/auth/csrf').json()['token']
    return c
def run(fixture,base='http://127.0.0.1:8080',wait=True):
    env();os.environ['CSI_LOCAL_DEMO']='1';os.environ.setdefault('SEMGREP_BIN',str(ROOT/'.scanner-venv/bin/semgrep'));os.environ.setdefault('SEMGREP_LOG_FILE',str(ROOT/'.runtime/semgrep.log'));os.environ.setdefault('SEMGREP_SETTINGS_FILE',str(ROOT/'.runtime/semgrep.yml'))
    findings=scan(ROOT/'fixtures'/fixture);c=login(base)
    if not any(p['repository']=='local/csi-demo' for p in c.get('/api/projects').json()):
        c.post('/api/projects',json={'repository':'local/csi-demo','defaultBranch':'develop'}).raise_for_status()
    sha=hashlib.sha1((ROOT/'fixtures'/fixture/'AccountService.java').read_bytes()).hexdigest()
    payload=dict(repository='local/csi-demo',branch='develop',commitSha=sha,workflowRunId=str(time.time_ns()),runAttempt=1,triggerType='LOCAL_DEMO',scannerSuccess=True,findings=findings)
    response=submit(payload,base,os.environ['CSI_INTEGRATION_SECRET']);sid=response['scanId']
    duplicate=submit(payload,base,os.environ['CSI_INTEGRATION_SECRET']);assert duplicate['scanId']==sid and duplicate['duplicate']
    print(json.dumps({'fixture':fixture,'scanId':sid,'staticFindings':len(findings),'duplicateDelivery':'PASS'}),flush=True)
    if wait:
        for _ in range(180):
            s=c.get('/api/scans/'+sid).json()
            if s['status'] in {'COMPLETED','FAILED'}:
                print(json.dumps({'status':s['status'],'analysisMode':s['analysisMode'],'scanId':sid}),flush=True)
                assert s['status']=='COMPLETED','Analysis failed; inspect /api/scans/{id}/logs'
                fs=c.get('/api/scans/'+sid+'/findings').json()
                if findings:assert all(f['analysis'].get('references') for f in fs)
                return sid
            time.sleep(1)
        raise TimeoutError('Scan deadline exceeded')
    return sid
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('fixture',choices=['vulnerable','fixed']);p.add_argument('--base',default='http://127.0.0.1:8080');a=p.parse_args();run(a.fixture,a.base)
