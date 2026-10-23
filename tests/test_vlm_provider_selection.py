import json
import httpx
import pytest
from coding_agent.openai_vlm import model_name, provider_name
from coding_agent.local_vlm import LocalActionsClient
from coding_agent.orchestrator import TOOLS, validate_args
from coding_agent.repository import Rejected
from coding_agent import engine
from test_coding_agent import repo, context, report, chat, response


def test_provider_defaults_and_cross_provider_model_rejection(monkeypatch):
    monkeypatch.delenv('CSI_VLM_MODEL', raising=False)
    monkeypatch.setenv('CSI_VLM_PROVIDER', 'ollama')
    assert model_name() == 'qwen3-vl:8b'
    monkeypatch.setenv('CSI_VLM_MODEL', 'gpt-5.4-mini')
    with pytest.raises(Rejected, match='VLM_MODEL_UNSUPPORTED'):
        model_name()
    monkeypatch.setenv('CSI_VLM_PROVIDER', 'unknown')
    with pytest.raises(Rejected, match='VLM_PROVIDER_UNSUPPORTED'):
        provider_name()


def test_local_adapter_preserves_image_and_releases_model():
    def handle(request):
        body = json.loads(request.content)
        assert body['keep_alive'] == 0 and body['think'] is False
        assert body['messages'][1]['images'] == ['aGVsbG8=']
        assert request.headers.get('authorization') is None
        return httpx.Response(200, json={'done_reason':'stop', 'prompt_eval_count':100, 'eval_count':20,
            'message':{'content':json.dumps({'name':'block','arguments':json.dumps({'reason':'Insufficient evidence'})})}})
    client=LocalActionsClient(transport=httpx.MockTransport(handle))
    raw=client({'instructions':'rules','model':'qwen3-vl:8b','tools':TOOLS,
                'input':[{'role':'user','content':[{'type':'input_text','text':'evidence'},
                          {'type':'input_image','image_url':'data:image/png;base64,aGVsbG8='}]}]})
    assert validate_args(raw['output'][0]) == {'reason':'Insufficient evidence'}
    assert raw['usage']['input_tokens'] == 100


def test_no_architecture_uses_code_policy_without_api_key(repo, monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    checks=[]; payloads=[]
    def verify(_):
        checks.append(1)
        return report(len(checks)>1)
    def coder(payload):
        payloads.append(payload)
        return chat(response())
    result=engine.generate(repo,context(repo),verifier=verify,chat=coder,
                           vlm_chat=lambda _:pytest.fail('no diagram must not require VLM'))
    assert result['status']=='READY' and result['engineVersion']=='3'
    assert payloads[0]['keep_alive']==0 and len(checks)==2
