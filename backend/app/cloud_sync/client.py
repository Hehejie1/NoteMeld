from __future__ import annotations

from typing import Any

import httpx


class CloudClientError(RuntimeError):
    def __init__(self, status_code: int, message: str):
        super().__init__(message)
        self.status_code = status_code


class CloudClient:
    """Small transport adapter shared by local desktop/mobile hosts.

    It deliberately contains no Agent/session state machine; callers own
    local queue and event replay semantics.
    """

    def __init__(self, base_url: str, token: str | None = None, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self._client = client or httpx.Client(timeout=20.0)

    def close(self) -> None:
        self._client.close()

    def login(self, password: str, *, username: str | None = None, account_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, str] = {"password": password}
        if account_id:
            payload["account_id"] = account_id
        elif username:
            payload["username"] = username
        else:
            raise ValueError("username or account_id is required")
        data = self._request("POST", "/v1/auth/login", json=payload)
        self.token = data["token"]
        return data

    def create_session(self, kind: str, title: str = "New session", workspace_id: str = "default") -> dict[str, Any]:
        return self._request("POST", "/v1/sessions", json={"kind": kind, "title": title, "workspace_id": workspace_id})

    def send_command(self, session_id: str, request_id: str, input_text: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/sessions/{session_id}/commands", json={"request_id": request_id, "input": input_text})

    def snapshot(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/sessions/{session_id}/snapshot")

    def events(self, session_id: str, after: int = 0) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/sessions/{session_id}/events", params={"after": after})

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        response = self._client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        try:
            body = response.json()
        except ValueError as exc:
            raise CloudClientError(response.status_code, "cloud returned invalid JSON") from exc
        if response.status_code >= 400 or body.get("code") not in (None, 0):
            raise CloudClientError(response.status_code, body.get("msg", "cloud request failed"))
        return body.get("data", body)
