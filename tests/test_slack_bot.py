import asyncio
import json
import time
from types import SimpleNamespace
from urllib.parse import urlencode
from unittest.mock import AsyncMock, Mock
from uuid import uuid4
import httpx
import pytest
from slack_sdk.signature import SignatureVerifier
from slack_bot import config, poller, interactions, interactions_server, socket_mode, slack_client
from slack_bot.backend_client import BackendClient
from slack_bot.delivery_store import DeliveryStore


@pytest.fixture(autouse=True)
def isolated_bot(monkeypatch, tmp_path):
    monkeypatch.setattr(config, 'SLACK_ADMIN_USER_IDS', ['UADMIN', 'USECOND'])
    monkeypatch.setattr(config, 'SLACK_SIGNING_SECRET', 'unit-test-signing-secret')
    receipt = DeliveryStore(tmp_path / 'receipts.sqlite3')
    monkeypatch.setattr(poller, '_store', receipt)
    monkeypatch.setattr(poller, '_lock', asyncio.Lock())
    # All network boundaries are mocked: tests never contact CSI or Slack.
    monkeypatch.setattr(poller, 'backend', Mock())
    monkeypatch.setattr(interactions, 'backend', Mock())
    monkeypatch.setattr(slack_client, 'send_approval_dm', Mock(return_value=('DADMIN', '1.0')))
    monkeypatch.setattr(slack_client, 'update_as_decided', Mock())
    yield receipt
    receipt.close()


def approval(action='CREATE_SECURITY_REVIEW_ISSUE', status='PENDING'):
    return {'id': str(uuid4()), 'scanId': str(uuid4()), 'status': status, 'action': action,
            'repository': 'example/project', 'commitSha': 'a' * 40}


def payload(key, user='UADMIN', action='approve'):
    return {'type': 'block_actions', 'user': {'id': user}, 'actions': [{'action_id': action, 'value': key}]}


async def test_both_approval_types_delivered_and_notification_has_no_decision_buttons():
    security, coding = approval(), approval('CODING_PROPOSAL_APPROVED', 'APPROVED')
    coding['scanId'] = security['scanId']
    poller.backend.list_approvals.return_value = [security, coding]
    await poller.poll_once()
    await poller.poll_once()
    assert slack_client.send_approval_dm.call_count == 4
    blocks = slack_client._request_blocks(coding)
    assert [b['action_id'] for b in blocks[1]['elements']] == ['view']
    assert blocks[1]['elements'][0]['url'].endswith('/scans/' + coding['scanId'])


async def test_partial_failure_retries_only_missing_recipient_and_receipts_survive_restart(tmp_path, monkeypatch):
    item = approval()
    poller.backend.list_approvals.return_value = [item]
    slack_client.send_approval_dm.side_effect = [('D1', '1'), RuntimeError('temporary'), ('D2', '2')]
    await poller.poll_once()
    await poller.poll_once()
    assert slack_client.send_approval_dm.call_count == 3
    reopened = DeliveryStore(tmp_path / 'receipts.sqlite3')
    monkeypatch.setattr(poller, '_store', reopened)
    await poller.poll_once()
    assert slack_client.send_approval_dm.call_count == 3
    reopened.close()


async def test_decisions_update_existing_messages_and_retry_failed_updates():
    item = approval()
    poller.backend.list_approvals.return_value = [item]
    await poller.poll_once()
    item['status'] = 'APPROVED'
    slack_client.update_as_decided.side_effect = [RuntimeError('temporary'), None, None]
    await poller.poll_once()
    await poller.poll_once()
    assert slack_client.update_as_decided.call_count == 3
    assert all(row[-1] == 'APPROVED' for row in poller.store().messages(item['id']))
    item['status'] = 'EXECUTED'
    slack_client.update_as_decided.side_effect = None
    await poller.poll_once()
    assert all(row[-1] == 'EXECUTED' for row in poller.store().messages(item['id']))


def signed(body, timestamp=None):
    timestamp = str(timestamp or int(time.time()))
    return {'content-type': 'application/x-www-form-urlencoded', 'x-slack-request-timestamp': timestamp,
            'x-slack-signature': SignatureVerifier(config.SLACK_SIGNING_SECRET).generate_signature(timestamp=timestamp, body=body)}


async def test_http_signature_authorization_valid_decision_and_expired_request(monkeypatch):
    decision = AsyncMock()
    monkeypatch.setattr(interactions_server, 'decide', decision)
    key = str(uuid4())
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=interactions_server.app), base_url='http://test') as client:
        body = urlencode({'payload': json.dumps(payload(key))})
        assert (await client.post('/slack/interactions', content=body)).status_code == 401
        assert (await client.post('/slack/interactions', content=body, headers=signed(body, int(time.time())-600))).status_code == 401
        denied = urlencode({'payload': json.dumps(payload(key, user='USTRANGER'))})
        assert (await client.post('/slack/interactions', content=denied, headers=signed(denied))).status_code == 403
        assert not decision.called
        assert (await client.post('/slack/interactions', content=body, headers=signed(body))).status_code == 200
        decision.assert_awaited_once_with(key, 'APPROVED')
        invalid = urlencode({'payload': '{'})
        assert (await client.post('/slack/interactions', content=invalid, headers=signed(invalid))).status_code == 400


async def test_socket_ack_precedes_slow_decision_and_checks_reviewer(monkeypatch):
    key = str(uuid4())
    calls = []
    async def ack(response): calls.append('ack')
    async def decide(*args): calls.append('decision')
    monkeypatch.setattr(socket_mode, 'decide', decide)
    client = SimpleNamespace(send_socket_mode_response=ack)
    request = SimpleNamespace(type='interactive', envelope_id='envelope', payload=payload(key))
    await socket_mode.handle(client, request)
    assert calls == ['ack']
    await asyncio.gather(*list(socket_mode._tasks))
    assert calls == ['ack', 'decision']
    request.payload = payload(key, user='USTRANGER')
    await socket_mode.handle(client, request)
    await asyncio.sleep(0)
    assert calls == ['ack', 'decision', 'ack']


@pytest.mark.parametrize('decision', ['APPROVED', 'REJECTED'])
async def test_button_decision_and_duplicate_use_persisted_backend_state(monkeypatch, decision):
    key = str(uuid4())
    updated = AsyncMock()
    monkeypatch.setattr(poller, 'mark_decided', updated)
    interactions.backend.decide.return_value = {'status': decision}
    await interactions.decide(key, decision)
    updated.assert_awaited_with(key, decision)
    response = httpx.Response(409, request=httpx.Request('POST', 'http://test/decision'))
    interactions.backend.decide.side_effect = httpx.HTTPStatusError('already decided', request=response.request, response=response)
    interactions.backend.list_approvals.return_value = [dict(approval(status='EXECUTED'), id=key)]
    await interactions.decide(key, decision)
    updated.assert_awaited_with(key, 'EXECUTED')


def test_backend_refreshes_csrf_after_login_and_recovers_expired_session():
    state = {'csrf': 0, 'decisions': 0, 'login': 0}
    def handler(request):
        if request.url.path.endswith('/csrf'):
            state['csrf'] += 1
            return httpx.Response(200, json={'token': str(state['csrf'])})
        if request.url.path.endswith('/login'):
            state['login'] += 1
            return httpx.Response(200, json={})
        state['decisions'] += 1
        assert request.headers['x-csrf-token'] == str(state['csrf'])
        assert state['csrf'] in {2, 4}
        return httpx.Response(403 if state['decisions'] == 1 else 200, json={'status': 'APPROVED'})
    with httpx.Client(base_url='http://test', transport=httpx.MockTransport(handler)) as client:
        assert BackendClient(client).decide(str(uuid4()), 'APPROVED') == {'status': 'APPROVED'}
    assert state == {'csrf': 4, 'decisions': 2, 'login': 2}


async def test_socket_transport_connects_and_closes_on_shutdown(monkeypatch):
    connected = asyncio.Event()
    client = SimpleNamespace(socket_mode_request_listeners=[], connect=AsyncMock(side_effect=connected.set), close=AsyncMock())
    monkeypatch.setattr(socket_mode, 'SocketModeClient', Mock(return_value=client))
    monkeypatch.setattr(socket_mode, 'AsyncWebClient', Mock())
    task = asyncio.create_task(socket_mode.run_forever())
    await asyncio.wait_for(connected.wait(), 1)
    assert client.socket_mode_request_listeners == [socket_mode.handle]
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    client.close.assert_awaited_once()
