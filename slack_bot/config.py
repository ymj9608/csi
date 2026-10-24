import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

SLACK_BOT_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.environ.get("SLACK_SIGNING_SECRET", "")
SLACK_APP_TOKEN = os.environ.get("SLACK_APP_TOKEN", "")
SLACK_MODE = os.environ.get("SLACK_MODE", "socket")
SLACK_ADMIN_USER_IDS = list(dict.fromkeys(u.strip() for u in os.environ.get("SLACK_ADMIN_USER_IDS", "").split(",") if u.strip()))

CSI_BACKEND_URL = os.environ.get("CSI_BACKEND_URL", "http://127.0.0.1:8080")
CSI_FRONTEND_URL = os.environ.get("CSI_FRONTEND_URL", "http://127.0.0.1:5174")
CSI_ADMIN_USERNAME = os.environ.get("CSI_ADMIN_USERNAME", "reviewer")
CSI_ADMIN_PASSWORD = os.environ.get("CSI_ADMIN_PASSWORD", "")

POLL_INTERVAL_SECONDS = int(os.environ.get("SLACK_POLL_INTERVAL_SECONDS", "5"))
INTERACTIONS_PORT = int(os.environ.get("SLACK_INTERACTIONS_PORT", "8787"))
INTERACTIONS_HOST = os.environ.get("SLACK_INTERACTIONS_HOST", "127.0.0.1")
STATE_PATH = Path(os.environ.get("SLACK_STATE_PATH", str(ROOT_DIR / ".runtime/slack-deliveries.sqlite3")))


def validate():
    required = {"SLACK_BOT_TOKEN": SLACK_BOT_TOKEN, "SLACK_ADMIN_USER_IDS": SLACK_ADMIN_USER_IDS,
                "CSI_ADMIN_PASSWORD": CSI_ADMIN_PASSWORD}
    if SLACK_MODE not in {"socket", "http"}:
        raise ValueError("SLACK_MODE must be socket or http")
    required.update({"SLACK_APP_TOKEN": SLACK_APP_TOKEN} if SLACK_MODE == "socket"
                    else {"SLACK_SIGNING_SECRET": SLACK_SIGNING_SECRET})
    missing = [key for key, value in required.items() if not value]
    if missing:
        raise ValueError("Missing configuration: " + ", ".join(missing))
    if POLL_INTERVAL_SECONDS < 1:
        raise ValueError("SLACK_POLL_INTERVAL_SECONDS must be positive")
