"""Serialized session/CSRF handling shared by polling and interaction threads."""
import threading
import httpx
from . import config


class BackendClient:
    def __init__(self, client=None):
        self._client = client or httpx.Client(base_url=config.CSI_BACKEND_URL, timeout=10.0, trust_env=False)
        self._csrf_token = None
        self._logged_in = False
        self._lock = threading.RLock()

    def _csrf(self):
        response = self._client.get("/api/auth/csrf")
        response.raise_for_status()
        self._csrf_token = response.json()["token"]

    def _login(self):
        self._logged_in = False
        self._csrf()
        response = self._client.post("/api/auth/login",
            json={"username": config.CSI_ADMIN_USERNAME, "password": config.CSI_ADMIN_PASSWORD},
            headers={"X-CSRF-TOKEN": self._csrf_token})
        response.raise_for_status()
        self._csrf()
        self._logged_in = True

    def _request(self, method, path, **kwargs):
        with self._lock:
            if not self._logged_in:
                self._login()
            for attempt in range(2):
                response = self._client.request(method, path,
                    headers={"X-CSRF-TOKEN": self._csrf_token}, **kwargs)
                if response.status_code in {401, 403} and attempt == 0:
                    self._login()
                    continue
                response.raise_for_status()
                return response.json()

    def list_approvals(self):
        return self._request("GET", "/api/approvals")

    def decide(self, approval_id, decision):
        return self._request("POST", f"/api/approvals/{approval_id}/decision", json={"decision": decision})


default_client = BackendClient()
