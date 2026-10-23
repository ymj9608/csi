"""Shared action validation and execution for HTTP and Socket Mode."""
import asyncio
import logging
from uuid import UUID
import httpx
from . import config, poller
from .backend_client import default_client as backend

log = logging.getLogger(__name__)
ACTION_TO_DECISION = {"approve": "APPROVED", "reject": "REJECTED"}


def parse_action(payload):
    if not isinstance(payload, dict) or payload.get('type') != 'block_actions':
        return None
    if payload.get('user', {}).get('id') not in config.SLACK_ADMIN_USER_IDS:
        raise PermissionError('Slack user is not an authorized reviewer')
    actions = payload.get('actions', [])
    if len(actions) != 1 or actions[0].get('action_id') not in ACTION_TO_DECISION:
        return None
    action = actions[0]
    return str(UUID(action['value'])), ACTION_TO_DECISION[action['action_id']]


async def decide(approval_id, decision):
    try:
        reply = await asyncio.to_thread(backend.decide, approval_id, decision)
        status = reply['status']
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code != 409:
            log.warning('Approval decision failed for %s; retry in CSI or Slack', approval_id)
            return
        try:
            approvals = await asyncio.to_thread(backend.list_approvals)
            status = next(a['status'] for a in approvals if a['id'] == approval_id
                          and a['action'] == 'CREATE_SECURITY_REVIEW_ISSUE')
        except Exception:
            log.warning('Approval decision refresh failed for %s', approval_id)
            return
    except Exception:
        log.warning('Approval decision failed for %s; retry in CSI or Slack', approval_id)
        return
    if status in {'APPROVED', 'REJECTED', 'EXECUTED'}:
        await poller.mark_decided(approval_id, status)
