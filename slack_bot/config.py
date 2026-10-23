import os
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

SLACK_BOT_TOKEN = os.environ["SLACK_BOT_TOKEN"]
SLACK_SIGNING_SECRET = os.environ["SLACK_SIGNING_SECRET"]
SLACK_ADMIN_USER_IDS = [u.strip() for u in os.environ["SLACK_ADMIN_USER_IDS"].split(",") if u.strip()]

CSI_BACKEND_URL = os.environ.get("CSI_BACKEND_URL", "http://127.0.0.1:8080")
CSI_FRONTEND_URL = os.environ.get("CSI_FRONTEND_URL", "http://127.0.0.1:5174")
CSI_ADMIN_USERNAME = os.environ.get("CSI_ADMIN_USERNAME", "reviewer")
CSI_ADMIN_PASSWORD = os.environ["CSI_ADMIN_PASSWORD"]

POLL_INTERVAL_SECONDS = int(os.environ.get("SLACK_POLL_INTERVAL_SECONDS", "5"))
INTERACTIONS_PORT = int(os.environ.get("SLACK_INTERACTIONS_PORT", "8787"))
