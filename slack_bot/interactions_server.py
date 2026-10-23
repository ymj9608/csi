import json
from urllib.parse import parse_qs
from fastapi import BackgroundTasks, FastAPI, HTTPException, Request
from slack_sdk.signature import SignatureVerifier
from . import config
from .interactions import parse_action, decide

app = FastAPI()


@app.get('/healthz')
async def healthz():
    return {'ok': True}


@app.post('/slack/interactions')
async def interactions(request: Request, tasks: BackgroundTasks):
    body = await request.body()
    if not config.SLACK_SIGNING_SECRET or not SignatureVerifier(config.SLACK_SIGNING_SECRET).is_valid_request(body, dict(request.headers)):
        raise HTTPException(401, 'invalid Slack signature')
    try:
        payload = json.loads(parse_qs(body.decode())['payload'][0])
        action = parse_action(payload)
    except PermissionError:
        raise HTTPException(403, 'unauthorized Slack reviewer')
    except (ValueError, KeyError, TypeError, AttributeError):
        raise HTTPException(400, 'invalid Slack action')
    if action:
        tasks.add_task(decide, *action)
    return {'ok': True}
