"""Model-selected tool sequences with real Git fixtures; no external inference or billing."""
import copy
import json
import httpx
import pytest
from coding_agent import engine, orchestrator
from coding_agent.openai_vlm import ResponsesClient, ENDPOINT
from coding_agent.repository import Rejected
from coding_agent.profile import TARGET
from test_coding_agent import repo, context, response, chat, report, BEFORE, AFTER
from test_coding_handoff import ARCH, TEXT


def call(name, args, number=1):
    return {'status': 'completed', 'output': [{'type': 'function_call', 'call_id': f'call-{number}',
            'name': name, 'arguments': json.dumps(args)}],
            'usage': {'input_tokens': 100, 'output_tokens': 50,
                      'input_tokens_details': {'cached_tokens': 20}, 'output_tokens_details': {'reasoning_tokens': 10}}}


READ = ('read_code', {'path': TARGET, 'start_line': 1, 'end_line': 100})
EVIDENCE = ('get_policy_evidence', {'reference_ids': ['ref-1']})
DELEGATE = ('delegate_coding', {'instruction': TEXT, 'evidence_ids': ['finding-1', 'ref-1']})
VERIFY = ('run_verification', {})
FINISH = ('finish_review', {'summary': '격리 테스트 통과를 확인했습니다. 기존 데이터 정리와 관리자 승인은 별도로 필요합니다.', 'evidence_ids': ['finding-1', 'ref-1']})
BLOCK = ('block', {'reason': '확인된 근거가 부족하여 수정안 생성을 보류합니다.'})


def job(repo):
    value = context(repo)
    value.update(architectureId=ARCH['id'], architecture={**ARCH, 'sourceCommitSha': value['commitSha']})
    return value


def scripted(actions, captured):
    sequence = iter(actions)
    def model(payload):
        captured.append(copy.deepcopy(payload))
        name, args = next(sequence)
        return call(name, args, len(captured))
    return model


def run(repo, actions, *, coder=None, checks=None):
    captured, code_calls, validations = [], [], []
    def code(payload):
        code_calls.append(copy.deepcopy(payload))
        return coder(payload) if coder else chat(response())
    def verify(tree):
        validations.append((tree / TARGET).read_text())
        return checks(len(validations)) if checks else report(len(validations) > 1)
    value = engine.generate(repo, job(repo), vlm_chat=scripted(actions, captured), chat=code, verifier=verify)
    return value, captured, code_calls, validations


def test_vlm_drives_reads_coder_verifier_and_final_review(repo):
    result, vlm, coder, checks = run(repo, [('list_code_paths', {'prefix': 'backend/app/'}), READ, EVIDENCE, DELEGATE, VERIFY, FINISH])
    assert result['status'] == 'READY' and result['engineVersion'] == '4'
    assert len(vlm) == 6 and len(coder) == 1 and checks == [BEFORE, AFTER]
    assert vlm[0]['model'] == 'gpt-5.4-mini-2026-03-17' and vlm[0]['store'] is False
    assert vlm[0]['input'][0]['content'][1]['type'] == 'input_image'
    assert 'sourceFiles' not in vlm[0]['input'][0]['content'][0]['text']
    assert 'PRIVATE_FIXTURE' not in json.dumps(vlm + coder)
    assert coder[0]['messages'][-1]['content'].endswith(TEXT)
    handoff = result['handoff']
    assert handoff['metrics']['inputTokens'] == 600 and handoff['metrics']['outputTokens'] == 300
    assert handoff['metrics']['reasoningTokens'] == 60
    assert handoff['readPaths'] == [TARGET] and handoff['referenceIds'] == ['ref-1']
    assert handoff['trace'][-1]['tool'] == 'finish_review'
    assert 'imageBase64' not in json.dumps(result) and (repo / TARGET).read_text() == BEFORE


def test_verification_failure_returns_to_vlm_for_replanning(repo):
    actions = [READ, EVIDENCE, DELEGATE, VERIFY, ('search_code', {'query': 'password'}), DELEGATE, VERIFY, FINISH]
    result, vlm, coder, checks = run(repo, actions, checks=lambda n: report(n == 3))
    assert result['status'] == 'READY' and len(coder) == 2 and len(checks) == 3
    failure = json.loads(vlm[4]['input'][-1]['output'])
    assert failure['status'] == 'FAILED' and failure['verification']['failed'] == 7
    assert result['attempts'][0]['error'] == 'TESTS_FAILED'
    assert result['handoff']['trace'][4]['tool'] == 'search_code'


def test_coder_validation_error_is_observed_by_vlm_before_second_delegation(repo):
    count = []
    def coder(_):
        count.append(1)
        return chat(response(AFTER + '\nimport os\n' if len(count) == 1 else AFTER))
    result, vlm, _, checks = run(repo, [READ, EVIDENCE, DELEGATE, DELEGATE, VERIFY, FINISH], coder=coder)
    assert result['status'] == 'READY' and len(checks) == 2
    assert json.loads(vlm[3]['input'][-1]['output'])['errorCode'] == 'IMPORT_NOT_ALLOWED'


@pytest.mark.parametrize('actions,code', [
    ([FINISH, BLOCK], 'VLM_EVIDENCE_MISSING'),
    ([EVIDENCE, FINISH, BLOCK], 'VLM_VERIFICATION_REQUIRED'),
    ([EVIDENCE, DELEGATE, BLOCK], 'VLM_SOURCE_READ_REQUIRED'),
    ([READ, EVIDENCE, DELEGATE, FINISH, BLOCK], 'VLM_VERIFICATION_REQUIRED'),
    ([READ, EVIDENCE, DELEGATE, VERIFY, DELEGATE, FINISH, BLOCK], 'VLM_VERIFICATION_REQUIRED'),
    ([('read_code', {'path': '.env', 'start_line': 1, 'end_line': 20}), BLOCK], 'VLM_SOURCE_SCOPE'),
    ([('read_code', {'path': '../.env', 'start_line': 1, 'end_line': 20}), BLOCK], 'VLM_SOURCE_SCOPE'),
    ([('get_policy_evidence', {'reference_ids': ['invented-law']}), BLOCK], 'VLM_EVIDENCE_MISSING'),
    ([('run_shell', {'command': 'do not execute'}), BLOCK], 'VLM_TOOL_NOT_ALLOWED'),
    ([READ, EVIDENCE, DELEGATE, DELEGATE, DELEGATE, BLOCK], 'VLM_CODING_BUDGET'),
])
def test_model_cannot_bypass_permissions_evidence_or_fresh_verification(repo, actions, code):
    result, _, _, _ = run(repo, actions)
    assert result['status'] == 'BLOCKED' and result['files'] == []
    assert code in [step.get('errorCode') for step in result['handoff']['trace']]


def test_turn_limit_stops_read_loop_without_patch(repo):
    result, vlm, coder, _ = run(repo, [READ] * orchestrator.MAX_TURNS)
    assert result['failureReason'] == 'VLM_TURN_BUDGET' and not coder
    assert len(vlm) == orchestrator.MAX_TURNS


def test_budget_stop_preserves_trace(repo, monkeypatch):
    monkeypatch.setattr(orchestrator, 'MAX_TOKENS', 12500)
    result, _, coder, _ = run(repo, [READ] * 14)
    assert result['failureReason'] == 'VLM_TOKEN_BUDGET' and not coder


@pytest.mark.parametrize('change,code', [
    (lambda r: r.update(status='incomplete'), 'VLM_OUTPUT_INCOMPLETE'),
    (lambda r: r.update(output=[]), 'VLM_SINGLE_TOOL_REQUIRED'),
    (lambda r: r['output'].append(r['output'][0]), 'VLM_SINGLE_TOOL_REQUIRED'),
    (lambda r: r.pop('usage'), 'VLM_USAGE_MISSING'),
])
def test_bad_provider_output_fails_closed(repo, change, code):
    raw = call(*READ)
    change(raw)
    result = engine.generate(repo, job(repo), verifier=lambda _: report(False), vlm_chat=lambda _: raw,
                             chat=lambda _: pytest.fail('coder must not run'))
    assert result['status'] == 'BLOCKED' and result['failureReason'] == code and result['files'] == []


def test_stateless_reasoning_is_roundtripped_but_not_published(repo):
    captured = []
    def model(payload):
        captured.append(copy.deepcopy(payload))
        raw = call(*(READ if len(captured) == 1 else BLOCK), number=len(captured))
        if len(captured) == 1:
            raw['output'].insert(0, {'type': 'reasoning', 'id': 'reasoning-1', 'encrypted_content': 'PRIVATE_CIPHER', 'summary': []})
        return raw
    result = engine.generate(repo, job(repo), verifier=lambda _: report(False), vlm_chat=model)
    assert 'PRIVATE_CIPHER' in json.dumps(captured[1]) and 'PRIVATE_CIPHER' not in json.dumps(result)


def test_openai_transport_uses_fixed_endpoint_and_redacts_errors(monkeypatch):
    monkeypatch.delenv('OPENAI_API_KEY', raising=False)
    with pytest.raises(Rejected, match='OPENAI_API_KEY_REQUIRED'):
        ResponsesClient()
    def transport(request):
        assert str(request.url) == ENDPOINT and request.headers['authorization'] == 'Bearer test-key'
        return httpx.Response(401, json={'error': 'PRIVATE_PROVIDER_DETAIL'})
    with pytest.raises(Rejected, match='^VLM_AUTH_FAILED$'):
        ResponsesClient('test-key', httpx.MockTransport(transport))({'model': 'gpt-6.1-sol'})


@pytest.mark.parametrize('status,code', [(403,'VLM_AUTH_FAILED'),(429,'VLM_RATE_LIMITED'),(500,'VLM_UNAVAILABLE')])
def test_provider_errors_do_not_retry_or_leak_details(status, code):
    requests = []
    def handle(request):
        requests.append(request)
        return httpx.Response(status, json={'error': {'message': 'PRIVATE_PROVIDER_DETAIL'}})
    with pytest.raises(Rejected, match='^'+code+'$'):
        ResponsesClient('test', httpx.MockTransport(handle))({'model': 'gpt-6.1-sol'})
    assert len(requests) == 1


def test_provider_timeout_is_reported_without_raw_exception():
    def handle(request):
        raise httpx.ReadTimeout('PRIVATE_URL_AND_CONTEXT', request=request)
    with pytest.raises(Rejected, match='^VLM_TIMEOUT$'):
        ResponsesClient('test', httpx.MockTransport(handle))({})


def test_time_budget_stops_before_inference(repo, monkeypatch):
    monkeypatch.setattr(orchestrator,'MAX_SECONDS',0)
    result = engine.generate(repo, job(repo), verifier=lambda _: report(False),
                             vlm_chat=lambda _: pytest.fail('deadline must stop inference'))
    assert result['failureReason'] == 'VLM_TIME_BUDGET' and result['files'] == []


def test_repeated_call_id_cannot_execute_coder_twice(repo):
    requests = []
    def model(payload):
        requests.append(payload)
        return call(*READ)  # same call_id on the next turn
    result = engine.generate(repo, job(repo), verifier=lambda _: report(False), vlm_chat=model)
    assert len(requests) == 2 and result['failureReason'] == 'VLM_DUPLICATE_CALL'


def test_source_tool_uses_commit_and_ignores_symlinks(repo):
    from coding_agent.repository import git
    (repo / 'backend/app/leak.py').symlink_to('/etc/passwd')
    git(repo, 'add', '.')
    git(repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-qm', 'symlink')
    sources = orchestrator.SourceTools(repo, context(repo)['commitSha'])
    assert 'backend/app/leak.py' not in sources.paths and '.env' not in sources.paths
    (repo / TARGET).write_text('uncommitted content')
    assert sources.execute('read_code', READ[1])['content'] == BEFORE.rstrip('\n')
