import asyncio
import logging
from slack_sdk.socket_mode.aiohttp import SocketModeClient
from slack_sdk.socket_mode.response import SocketModeResponse
from slack_sdk.web.async_client import AsyncWebClient
from . import config
from .interactions import parse_action, decide

log = logging.getLogger(__name__)
_tasks = set()


async def handle(client, request):
    await client.send_socket_mode_response(SocketModeResponse(envelope_id=request.envelope_id))
    if request.type != 'interactive':
        return
    try:
        action = parse_action(request.payload)
    except (PermissionError, ValueError, KeyError, TypeError, AttributeError):
        log.warning('Rejected unauthorized or invalid Slack action')
        return
    if action:
        task = asyncio.create_task(decide(*action))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


async def run_forever():
    client = SocketModeClient(app_token=config.SLACK_APP_TOKEN,
                              web_client=AsyncWebClient(token=config.SLACK_BOT_TOKEN))
    try:
        client.socket_mode_request_listeners.append(handle)
        await client.connect()
        await asyncio.Event().wait()
    finally:
        if _tasks:
            await asyncio.gather(*list(_tasks), return_exceptions=True)
        await client.close()
