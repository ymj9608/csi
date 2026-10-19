"""Live security contract tests against the local CSI stack. Uses synthetic demo scans."""
import asyncio,hashlib,hmac,json,os,time,uuid,subprocess,inspect
import httpx,psycopg
from fastmcp import Client
from fastmcp.client.auth import BearerAuth
from demo import env,login,run
BASE='http://127.0.0.1:8080'
def wait_until(fn,timeout=45):
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        v=fn()
        if v:return v
        time.sleep(.5)
    raise TimeoutError('Expected state did not appear')
def db():return psycopg.connect(host='127.0.0.1',dbname='csi',user='csi',password=os.environ['DATABASE_PASSWORD'])
async def mcp_check():
    async with Client(os.environ.get('RAG_MCP_URL','http://127.0.0.1:8002/mcp'),auth=BearerAuth(os.environ['CSI_INTERNAL_TOKEN'])) as c:
        resources=await c.list_resource_templates();assert any('security://guidelines/' in str(r.uriTemplate) for r in resources)
        evidence=await c.read_resource('security://guidelines/SEC-04');assert 'REF-04' in str(evidence)
    try:
        async with Client(os.environ.get('RAG_MCP_URL','http://127.0.0.1:8002/mcp'),auth=BearerAuth('invalid')) as c:await c.list_tools()
    except Exception:pass
    else:raise AssertionError('MCP allowed invalid token')
def main():
    env();c=login(BASE);checks=[]
    for path in ['/dashboard/overview','/projects','/scans','/findings','/logs','/policies','/approvals']:
        response=c.get('/api'+path);assert response.status_code==200,path
    checks+=['all seven list/overview API endpoints return 200']
    assert httpx.get(BASE+'/api/projects').status_code==401
    assert httpx.get(BASE+'/internal/scans/'+str(uuid.uuid4())).status_code==401
    assert httpx.post(BASE+'/api/integrations/github/scan-results',content=b'{}').status_code==401
    assert c.post('/api/projects',headers={'X-CSRF-TOKEN':''},json={'repository':'local/x','defaultBranch':'develop'}).status_code==403
    assert c.post('/api/projects',json={'repository':'unauthorized/repo','defaultBranch':'develop'}).status_code==400
    checks+=['anonymous/internal access blocked','unsigned intake blocked','CSRF enforced','repository allowlist enforced']
    raw=b'{}';ts=str(int(time.time())-400);sig=hmac.new(os.environ['CSI_INTEGRATION_SECRET'].encode(),ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    assert httpx.post(BASE+'/api/integrations/github/scan-results',content=raw,headers={'X-CSI-Timestamp':ts,'X-CSI-Signature':sig}).status_code==401
    checks+=['expired HMAC rejected']
    vulnerable_id=run('vulnerable');fixed_id=run('fixed')
    vulnerable=c.get('/api/scans/'+vulnerable_id).json();fixed=c.get('/api/scans/'+fixed_id).json()
    assert vulnerable['findingCount']==8 and fixed['findingCount']==0
    comparison=c.get('/api/scans/'+fixed['id']+'/comparison').json();assert comparison['removed']==8 and comparison['added']==0
    findings=c.get('/api/scans/'+vulnerable['id']+'/findings').json();assert all(f['analysis']['references'] for f in findings)
    checks+=['fixed commit comparison: 8 removed','real RAG references on every finding']
    approvals=c.get('/api/approvals').json();approval=next(a for a in approvals if a['scanId']==vulnerable['id'])
    if approval['status']=='PENDING':
        response=c.post('/api/approvals/'+approval['id']+'/decision',json={'decision':'APPROVED'});assert response.status_code==200
    wait_until(lambda:any(a['id']==approval['id'] and a['status']=='EXECUTED' for a in c.get('/api/approvals').json()))
    assert c.post('/api/approvals/'+approval['id']+'/decision',json={'decision':'APPROVED'}).status_code==409
    with db() as conn:
        assert conn.execute('select count(*) from security_issues where approval_id=%s',(approval['id'],)).fetchone()[0]==1
        assert conn.execute('select count(*) from checkpoints where thread_id=%s',(vulnerable['id'],)).fetchone()[0]>0
    checks+=['HITL approved: checkpoint resumed and one internal issue created','duplicate decision rejected','Postgres checkpoints persisted']
    rejected_scan=run('vulnerable');rejected=wait_until(lambda:next((a for a in c.get('/api/approvals').json() if a['scanId']==rejected_scan),None))
    assert c.post('/api/approvals/'+rejected['id']+'/decision',json={'decision':'REJECTED'}).status_code==200
    wait_until(lambda:any(l['eventType']=='finalize' for l in c.get('/api/scans/'+rejected_scan+'/logs').json()))
    with db() as conn:
        assert conn.execute('select count(*) from security_issues where approval_id=%s',(rejected['id'],)).fetchone()[0]==0
        assert conn.execute('select state from agent_checkpoints where scan_id=%s',(rejected_scan,)).fetchone()[0]=='FINALIZED'
    checks+=['HITL rejected: no issue mutation']
    
    if os.environ.get('CSI_TEST_COMPOSE')=='1':
        code='import asyncio,os\nfrom fastmcp import Client\nfrom fastmcp.client.auth import BearerAuth\n'+inspect.getsource(mcp_check)+'\nasyncio.run(mcp_check())'
        subprocess.run(['docker','compose','exec','-T','agent','python','-'],input=code,text=True,check=True,capture_output=True)
    else:asyncio.run(mcp_check())
    checks+=['authenticated MCP resource returns real REF-04','MCP invalid token rejected']
    assert c.post('/api/auth/logout').status_code==204 and c.get('/api/auth/me').status_code==401
    checks+=['logout invalidates session']
    print(json.dumps({'passed':len(checks),'checks':checks},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
