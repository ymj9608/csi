import asyncio

from . import config, slack_client
from .backend_client import default_client as backend

# approval_id -> {"status": str, "messages": [(channel, ts), ...]}
_state: dict[str, dict] = {}


async def poll_once() -> None:
    approvals = await asyncio.to_thread(backend.list_approvals)

    for approval in approvals:
        approval_id = approval["id"]
        status = approval["status"]
        tracked = _state.get(approval_id)

        if status == "PENDING" and tracked is None:
            messages = []
            for user_id in config.SLACK_ADMIN_USER_IDS:
                channel, ts = await asyncio.to_thread(slack_client.send_approval_dm, user_id, approval)
                messages.append((channel, ts))
            _state[approval_id] = {"status": "PENDING", "messages": messages}
            print(f"[slack_bot.poller] sent approval DM for {approval_id} to {len(messages)} admin(s)")

        elif tracked is not None and tracked["status"] == "PENDING" and status != "PENDING":
            await _apply_decision(approval_id, status)


async def _apply_decision(approval_id: str, status: str) -> None:
    tracked = _state.get(approval_id)
    if tracked is None or tracked["status"] != "PENDING":
        return
    for channel, ts in tracked["messages"]:
        await asyncio.to_thread(slack_client.update_as_decided, channel, ts, status)
    tracked["status"] = status
    print(f"[slack_bot.poller] updated DMs for {approval_id} -> {status}")


async def mark_decided(approval_id: str, status: str) -> None:
    """Called by interactions_server right after a button click, so the
    admin doesn't have to wait for the next poll cycle to see the update."""
    await _apply_decision(approval_id, status)


async def run_forever() -> None:
    while True:
        try:
            await poll_once()
        except Exception as exc:  # keep the loop alive across transient backend hiccups
            print(f"[slack_bot.poller] error: {exc}")
        await asyncio.sleep(config.POLL_INTERVAL_SECONDS)
