from slack_sdk import WebClient

from . import config

client = WebClient(token=config.SLACK_BOT_TOKEN)

DECISION_LABEL = {
    "APPROVED": "✅ 승인됨",
    "REJECTED": "❌ 거부됨",
    "EXECUTED": "✅ 승인됨 (이슈 생성 완료)",
}


def _request_blocks(approval: dict) -> list[dict]:
    approval_id = approval["id"]
    repository = approval.get("repository", "알 수 없음")
    commit = (approval.get("commitSha") or "")[:8]
    created_at = approval.get("createdAt", "")
    detail_url = f"{config.CSI_FRONTEND_URL.rstrip('/')}/scans/{approval['scanId']}"

    # 이미 CSI 화면에서 결정된 코드 수정안 알림 — 여기선 승인/거부가 아니라 FYI 통지라
    # 버튼 없이 "자세히 보기"만 제공한다.
    if approval.get("action") == "CODING_PROPOSAL_APPROVED":
        return [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*🛠️ 코드 수정안이 승인되었습니다*\n"
                        f"저장소: `{repository}`\n"
                        f"커밋: `{commit}`\n"
                        f"승인 시각: {created_at}"
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "자세히 보기"},
                        "url": detail_url,
                        "action_id": "view",
                    },
                ],
            },
        ]

    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": (
                    "*🔐 보안 리뷰 승인 요청*\n"
                    f"저장소: `{repository}`\n"
                    f"커밋: `{commit}`\n"
                    f"요청 시각: {created_at}"
                ),
            },
        },
        {
            "type": "actions",
            "elements": [
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "승인"},
                    "style": "primary",
                    "action_id": "approve",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "거부"},
                    "style": "danger",
                    "action_id": "reject",
                    "value": approval_id,
                },
                {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "자세히 보기"},
                    "url": detail_url,
                    "action_id": "view",
                },
            ],
        },
    ]


def send_approval_dm(user_id: str, approval: dict) -> tuple[str, str]:
    text = (
        "코드 수정안이 승인되었습니다."
        if approval.get("action") == "CODING_PROPOSAL_APPROVED"
        else "새 보안 리뷰 승인 요청이 있습니다."
    )
    response = client.chat_postMessage(
        channel=user_id,
        text=text,
        blocks=_request_blocks(approval),
    )
    return response["channel"], response["ts"]


def update_as_decided(channel: str, ts: str, status: str) -> None:
    label = DECISION_LABEL.get(status, status)
    client.chat_update(
        channel=channel,
        ts=ts,
        text=f"보안 리뷰 승인 요청 — {label}",
        blocks=[
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*🔐 보안 리뷰 승인 요청*\n처리 결과: {label}"},
            }
        ],
    )
