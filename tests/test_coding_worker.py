"""Result transport retries must not discard successful, immutable generation."""
import json
import stat
from pathlib import Path

import httpx
import pytest

from coding_agent import worker
from coding_agent.repository import Rejected

JOB_ID='11111111-1111-4111-8111-111111111111'
JOB={'id':JOB_ID,'leaseToken':'22222222-2222-4222-8222-222222222222','repository':'ymj9608/Lichu'}
RESULT={'status':'READY','durationMs':62000,'repository':'ymj9608/Lichu','files':[]}


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(worker.time,'sleep',lambda _:None)


def api(handler):
    return httpx.Client(base_url='http://localhost:8080',transport=httpx.MockTransport(handler))


def generated(monkeypatch):
    calls=[]
    def generate(*args,**kwargs):
        calls.append(args)
        return RESULT.copy()
    monkeypatch.setattr(worker,'generate',generate)
    return calls


def test_lost_ack_retries_identical_result_without_failure(monkeypatch,tmp_path):
    generations=generated(monkeypatch);requests=[]
    def handler(request):
        requests.append(request)
        if len(requests)==1:
            # The server may already have committed before the response is lost.
            raise httpx.ReadTimeout('ack lost',request=request)
        return httpx.Response(200,json={'status':'READY','replayed':True})
    assert worker.process(api(handler),Path('.'),JOB,tmp_path,'http://localhost:11434')
    assert len(generations)==1 and len(requests)==2
    assert requests[0].content==requests[1].content
    assert all(r.url.path.endswith('/result') for r in requests)
    assert json.loads((tmp_path/(JOB_ID+'.json')).read_text())==RESULT
    assert stat.S_IMODE((tmp_path/(JOB_ID+'.json')).stat().st_mode)==0o600
    assert not (tmp_path/(JOB_ID+'.pending.json')).exists()


def test_outage_preserves_result_and_restart_resumes_without_inference(monkeypatch,tmp_path):
    generations=generated(monkeypatch);requests=[]
    def unavailable(request):
        requests.append(request)
        return httpx.Response(503,json={'error':'unavailable'})
    assert not worker.process(api(unavailable),Path('.'),JOB,tmp_path,'http://localhost:11434')
    assert len(requests)==3 and all(r.url.path.endswith('/result') for r in requests)
    pending=tmp_path/(JOB_ID+'.pending.json')
    assert stat.S_IMODE(pending.stat().st_mode)==0o600
    assert (tmp_path/(JOB_ID+'.json')).exists()
    delivered=[]
    def available(request):
        delivered.append(json.loads(request.content))
        return httpx.Response(200,json={'status':'READY'})
    assert worker.resume_deliveries(api(available),tmp_path,JOB['repository'])
    assert delivered==[{'leaseToken':JOB['leaseToken'],'result':RESULT}]
    assert len(generations)==1 and not pending.exists()


@pytest.mark.parametrize('status',[400,401,403,404,409,413])
def test_permanent_rejection_does_not_retry_or_send_failure(monkeypatch,tmp_path,status):
    generated(monkeypatch);requests=[]
    def rejected(request):
        requests.append(request)
        return httpx.Response(status,json={'error':'rejected'})
    assert not worker.process(api(rejected),Path('.'),JOB,tmp_path,'http://localhost:11434')
    assert len(requests)==1 and requests[0].url.path.endswith('/result')
    assert (tmp_path/(JOB_ID+'.json')).exists()
    assert not (tmp_path/(JOB_ID+'.pending.json')).exists()
    assert json.loads((tmp_path/(JOB_ID+'.delivery.json')).read_text())['httpStatus']==status


def test_pending_delivery_is_bound_to_backend_and_repository(monkeypatch,tmp_path):
    generated(monkeypatch)
    assert not worker.process(api(lambda _:httpx.Response(503)),Path('.'),JOB,tmp_path,'http://localhost:11434')
    client=api(lambda _:pytest.fail('must not upload to a different backend/repository'))
    assert worker.resume_deliveries(client,tmp_path,'another/repository')
    client.base_url='http://localhost:8081'
    assert worker.resume_deliveries(client,tmp_path,JOB['repository'])
    assert (tmp_path/(JOB_ID+'.pending.json')).exists()


def test_generation_failure_still_reports_safe_error_code(monkeypatch,tmp_path):
    def fail(*args,**kwargs):
        raise Rejected('BASELINE_NOT_SUPPORTED')
    monkeypatch.setattr(worker,'generate',fail);requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,json={'status':'FAILED'})
    assert not worker.process(api(handler),Path('.'),JOB,tmp_path,'http://localhost:11434')
    assert len(requests)==1 and requests[0].url.path.endswith('/failure')
    assert json.loads(requests[0].content)['errorCode']=='BASELINE_NOT_SUPPORTED'
    assert not list(tmp_path.glob('*.pending.json'))


def test_replay_ack_after_admin_decision_is_accepted_without_regeneration(monkeypatch,tmp_path):
    generations=generated(monkeypatch)
    assert worker.process(api(lambda _:httpx.Response(200,json={'status':'APPROVED','replayed':True})),
                          Path('.'),JOB,tmp_path,'http://localhost:11434')
    assert len(generations)==1 and not list(tmp_path.glob('*.pending.json'))


def test_malformed_ack_is_retried_and_does_not_disclose_private_payload(monkeypatch,tmp_path,capsys):
    result={**RESULT,'files':[{'content':'PRIVATE_SOURCE_SENTINEL'}]}
    monkeypatch.setattr(worker,'generate',lambda *args,**kwargs:result)
    requests=[]
    def handler(request):
        requests.append(request)
        return httpx.Response(200,text='not JSON') if len(requests)==1 else httpx.Response(200,json={'status':'READY'})
    assert worker.process(api(handler),Path('.'),JOB,tmp_path,'http://localhost:11434')
    assert len(requests)==2
    logs=capsys.readouterr().out
    assert JOB['leaseToken'] not in logs and 'PRIVATE_SOURCE_SENTINEL' not in logs
