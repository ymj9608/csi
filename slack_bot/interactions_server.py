import asyncio
import json

from fastapi import FastAPI, HTTPException, Request
from slack_sdk.signature import SignatureVerifier

from . import config, poller
from .backend_client import default_client as backend

app = FastAPI()
verifier = SignatureVerifier(config.SLACK_SIGNING_SECRET)

ACTION_TO_DECISION = {"approve": "APPROVED", "reject": "REJECTED"}


@app.get("/healthz")
async def healthz():
    return {"ok": True}


@app.post("/slack/interactions")
async def interactions(request: Request):
    body = await request.body()
    if not verifier.is_valid_request(body, dict(request.headers)):
        raise HTTPException(status_code=401, detail="invalid Slack signature")

    form = await request.form()
    payload = json.loads(form["payload"])
    action = payload["actions"][0]
    action_id = action["action_id"]

    if action_id not in ACTION_TO_DECISION:
        return {"ok": True}

    approval_id = action["value"]
    decision = ACTION_TO_DECISION[action_id]

    try:
        await asyncio.to_thread(backend.decide, approval_id, decision)
    except Exception as exc:
        print(f"[slack_bot.interactions] decide failed for {approval_id}: {exc}")
        return {"ok": False}

    await poller.mark_decided(approval_id, decision)
    return {"ok": True}
