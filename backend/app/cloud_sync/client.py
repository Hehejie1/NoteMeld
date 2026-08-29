from __future__ import annotations

from typing import Any
from urllib.parse import quote

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

    def __init__(self, base_url: str, token: str | None = None, device_id: str | None = None, client: httpx.Client | None = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.device_id = device_id
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

    def rotate_token(self) -> dict[str, Any]:
        data = self._request("POST", "/v1/auth/rotate")
        self.token = data["token"]
        return data

    def revoke_token(self) -> dict[str, Any]:
        data = self._request("POST", "/v1/auth/revoke")
        self.token = None
        return data

    def register_device(self, device_id: str, platform: str, display_name: str, public_key: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/devices", json={"device_id": device_id, "platform": platform, "display_name": display_name, "public_key": public_key})

    def list_devices(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/devices")

    def create_grant(self, controller_device_id: str, host_device_id: str, role: str = "standard", scopes: list[str] | None = None, workspace_refs: list[str] | None = None, expires_at: int | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/grants", json={"controller_device_id": controller_device_id, "host_device_id": host_device_id, "role": role, "scopes": scopes or [], "workspace_refs": workspace_refs or [], "expires_at": expires_at})

    def revoke_grant(self, grant_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/grants/{grant_id}/revoke")

    def heartbeat(self, device_id: str | None = None) -> dict[str, Any]:
        return self._request("POST", f"/v1/devices/{device_id or self.device_id}/heartbeat")

    def create_session(self, kind: str, title: str = "New session", workspace_id: str = "default") -> dict[str, Any]:
        return self._request("POST", "/v1/sessions", json={"kind": kind, "title": title, "workspace_id": workspace_id})

    def import_session(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/cloud/sessions/import", json=snapshot)

    def send_command(self, session_id: str, request_id: str, input_text: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/sessions/{session_id}/commands", json={"request_id": request_id, "input": input_text})

    def snapshot(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/sessions/{session_id}/snapshot")

    def list_sessions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/sessions")

    def archive_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/sessions/{session_id}/archive")

    def restore_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/sessions/{session_id}/restore")

    def copy_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/sessions/{session_id}/copy")

    def rotate_authority(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/sessions/{session_id}/authority/rotate")

    def acquire_authority_lease(self, session_id: str, owner: str, ttl_seconds: int = 30) -> dict[str, Any]:
        return self._request("POST", f"/v1/sessions/{session_id}/authority/lease", json={"owner": owner, "ttl_seconds": ttl_seconds})

    def release_authority_lease(self, session_id: str, owner: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/sessions/{session_id}/authority/lease", params={"owner": owner})

    def events(self, session_id: str, after: int = 0) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/sessions/{session_id}/events", params={"after": after})

    def read_workspace_file(self, workspace_id: str, path: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/workspaces/{workspace_id}/files/{quote(path, safe='/')}")

    def list_workspace_files(self, workspace_id: str, prefix: str = "") -> dict[str, Any]:
        return self._request("GET", f"/v1/workspaces/{workspace_id}/files", params={"prefix": prefix})

    def write_workspace_file(self, workspace_id: str, path: str, content: str) -> dict[str, Any]:
        return self._request("PUT", f"/v1/workspaces/{workspace_id}/files/{quote(path, safe='/')}", json={"content": content})

    def delete_workspace_file(self, workspace_id: str, path: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/workspaces/{workspace_id}/files/{quote(path, safe='/')}")

    def workspace_stats(self, workspace_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/workspaces/{workspace_id}/stats")

    def create_workspace_backup(self, workspace_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/workspaces/{workspace_id}/backups")

    def list_workspace_backups(self, workspace_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/workspaces/{workspace_id}/backups")

    def restore_workspace_backup(self, workspace_id: str, backup_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/workspaces/{workspace_id}/backups/restore", json={"backup_id": backup_id})

    def create_share_token(self, session_id: str, role: str = "viewer", scopes: list[str] | None = None, expires_at: int | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/share-tokens", json={"session_id": session_id, "role": role, "scopes": scopes or [], "expires_at": expires_at})

    def shared_snapshot(self, session_id: str, share_token: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/shared/{session_id}/snapshot", headers={"X-Share-Token": share_token})

    def shared_events(self, session_id: str, share_token: str, after: int = 0) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/shared/{session_id}/events", params={"after": after}, headers={"X-Share-Token": share_token})

    def shared_command(self, session_id: str, share_token: str, request_id: str, input_text: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/shared/{session_id}/commands", headers={"X-Share-Token": share_token}, json={"request_id": request_id, "input": input_text})

    def _request(self, method: str, path: str, **kwargs: Any) -> Any:
        headers = dict(kwargs.pop("headers", {}))
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.device_id:
            headers["X-Device-Id"] = self.device_id
        response = self._client.request(method, f"{self.base_url}{path}", headers=headers, **kwargs)
        try:
            body = response.json()
        except ValueError as exc:
            raise CloudClientError(response.status_code, "cloud returned invalid JSON") from exc
        if response.status_code >= 400 or body.get("code") not in (None, 0):
            raise CloudClientError(response.status_code, body.get("msg", "cloud request failed"))
        return body.get("data", body)
