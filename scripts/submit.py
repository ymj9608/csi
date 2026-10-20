import hashlib,hmac,json,os,time,urllib.request,urllib.parse
from pathlib import Path

def submit(payload,url,secret):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme!='https' and not(os.environ.get('CSI_LOCAL_DEMO')=='1' and parsed.hostname in {'127.0.0.1','localhost'}):raise ValueError('HTTPS required except explicit loopback local demo')
    raw=json.dumps(payload,separators=(',',':'),ensure_ascii=False).encode();ts=str(int(time.time()))
    sig=hmac.new(secret.encode(),ts.encode()+b'.'+raw,hashlib.sha256).hexdigest()
    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self,*args,**kwargs):return None
    request=urllib.request.Request(url+'/api/integrations/github/scan-results',data=raw,headers={'Content-Type':'application/json','X-CSI-Timestamp':ts,'X-CSI-Signature':sig})
    with urllib.request.build_opener(NoRedirect).open(request,timeout=20) as response:
        if response.status!=202:raise RuntimeError('Backend did not accept scan')
        return json.load(response)
if __name__=='__main__':
    payload=dict(repository=os.environ['GITHUB_REPOSITORY'],branch=os.environ['GITHUB_REF_NAME'],commitSha=os.environ['GITHUB_SHA'],workflowRunId=os.environ['GITHUB_RUN_ID'],runAttempt=int(os.environ['GITHUB_RUN_ATTEMPT']),triggerType='WORKFLOW_DISPATCH' if os.environ.get('GITHUB_EVENT_NAME')=='workflow_dispatch' else 'GITHUB_PUSH',scannerSuccess=True,findings=json.loads(Path(os.environ['CSI_FINDINGS_FILE']).read_text()) if os.environ.get('CSI_FINDINGS_FILE') else [])
    if os.environ.get('CSI_SCAN_FILE'):
        collected=json.loads(Path(os.environ['CSI_SCAN_FILE']).read_text())
        payload['findings']=collected['findings'];payload['changeSet']=collected['changeSet']
    result=submit(payload,os.environ['CSI_BACKEND_URL'].rstrip('/'),os.environ['CSI_INTEGRATION_SECRET']);print('Accepted scan:',result['scanId'])
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        from uuid import UUID
        scan_id=str(UUID(result['scanId']))
        with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as summary:
            summary.write(f'## CSI scan accepted\n\nScan ID: `{scan_id}`\n\n'
                          f'Static findings: **{len(payload["findings"])}**\n\n'
                          'HTTP 202 means the scan was queued, not that AI analysis completed or security passed. '
                          'Open CSI Scan History and check COMPLETED / FAILED and the findings.\n')
