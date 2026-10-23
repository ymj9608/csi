import httpx

from . import config


class BackendClient:
    """Thin client for the CSI backend's /api/* approval endpoints.

    Spring Security requires a session (via /api/auth/login) and a CSRF
    token (via /api/auth/csrf) on every state-changing request under /api/**.
    """

    def __init__(self):
        self._client = httpx.Client(base_url=config.CSI_BACKEND_URL, timeout=10.0)
        self._csrf_token = None
        self._logged_in = False

    def _login(self):
        self._csrf_token = self._client.get("/api/auth/csrf").json()["token"]
        response = self._client.post(
            "/api/auth/login",
            json={"username": config.CSI_ADMIN_USERNAME, "password": config.CSI_ADMIN_PASSWORD},
            headers={"X-CSRF-TOKEN": self._csrf_token},
        )
        response.raise_for_status()
        self._logged_in = True

    def _ensure_login(self):
        if not self._logged_in:
            self._login()

    def list_approvals(self):
        self._ensure_login()
        response = self._client.get("/api/approvals")
        if response.status_code == 401:
            self._logged_in = False
            self._ensure_login()
            response = self._client.get("/api/approvals")
        response.raise_for_status()
        return response.json()

    def decide(self, approval_id: str, decision: str):
        self._ensure_login()
        response = self._client.post(
            f"/api/approvals/{approval_id}/decision",
            json={"decision": decision},
            headers={"X-CSRF-TOKEN": self._csrf_token},
        )
        if response.status_code == 401:
            self._logged_in = False
            self._ensure_login()
            response = self._client.post(
                f"/api/approvals/{approval_id}/decision",
                json={"decision": decision},
                headers={"X-CSRF-TOKEN": self._csrf_token},
            )
        response.raise_for_status()
        return response.json()


default_client = BackendClient()
