import asyncio
import logging
from . import config, slack_client
from .backend_client import default_client as backend
from .delivery_store import DeliveryStore

log = logging.getLogger(__name__)
_store = None
_lock = asyncio.Lock()


def store():
    global _store
    if _store is None:
        _store = DeliveryStore(config.STATE_PATH)
    return _store


async def _apply_decision(approval_id, status):
    for user_id, channel, ts, previous in store().messages(approval_id):
        if previous == status:
            continue
        try:
            await asyncio.to_thread(slack_client.update_as_decided, channel, ts, status)
            store().save(approval_id, user_id, channel, ts, status)
        except Exception:
            log.warning("Slack message update failed for approval %s; will retry", approval_id)


async def poll_once():
    approvals = await asyncio.to_thread(backend.list_approvals)
    async with _lock:
        for approval in approvals:
            approval_id, status, action = approval['id'], approval['status'], approval['action']
            security = action == 'CREATE_SECURITY_REVIEW_ISSUE'
            notification = action == 'CODING_PROPOSAL_APPROVED'
            if not security and not notification:
                continue
            if (security and status == 'PENDING') or (notification and status == 'APPROVED'):
                for user_id in config.SLACK_ADMIN_USER_IDS:
                    if store().get(approval_id, user_id):
                        continue
                    try:
                        channel, ts = await asyncio.to_thread(slack_client.send_approval_dm, user_id, approval)
                        store().save(approval_id, user_id, channel, ts, status)
                    except Exception:
                        log.warning("Slack delivery failed for approval %s; will retry", approval_id)
            elif security and status in {'APPROVED', 'REJECTED', 'EXECUTED'}:
                await _apply_decision(approval_id, status)


async def mark_decided(approval_id, status):
    async with _lock:
        await _apply_decision(approval_id, status)


async def run_forever():
    while True:
        try:
            await poll_once()
        except Exception:
            log.warning("Approval polling failed; will retry")
        await asyncio.sleep(config.POLL_INTERVAL_SECONDS)
