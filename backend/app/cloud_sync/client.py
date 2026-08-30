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

    def __init__(self, base_url: str, token: str | None = None, device_id: str | None = None, client: httpx.Client | None = None, token_store: Any | None = None):
        self.base_url = base_url.rstrip("/")
        self.token_store = token_store
        self.token = token if token is not None else (token_store.load() if token_store is not None else None)
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
        self._persist_token()
        return data

    def capabilities(self) -> dict[str, Any]:
        return self._request("GET", "/v1/capabilities")

    def rotate_token(self) -> dict[str, Any]:
        data = self._request("POST", "/v1/auth/rotate")
        self.token = data["token"]
        self._persist_token()
        return data

    def revoke_token(self) -> dict[str, Any]:
        data = self._request("POST", "/v1/auth/revoke")
        self.token = None
        if self.token_store is not None:
            self.token_store.clear()
        return data

    def _persist_token(self) -> None:
        if self.token_store is not None and self.token is not None:
            self.token_store.save(self.token)

    def list_personal_tokens(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/auth/tokens")

    def create_personal_token(self, scopes: list[str] | None = None, expires_at: int | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {"scopes": ["*"] if scopes is None else scopes}
        if expires_at is not None:
            payload["expires_at"] = expires_at
        return self._request("POST", "/v1/auth/tokens", json=payload)

    def revoke_personal_token(self, token_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/auth/tokens/{quote(token_id, safe='')}/revoke")

    def list_users(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/admin/users")

    def create_user(self, username: str, password: str) -> dict[str, Any]:
        return self._request("POST", "/v1/admin/users", json={"username": username, "password": password})

    def update_user(self, user_id: str, **changes: Any) -> dict[str, Any]:
        return self._request("PUT", f"/v1/admin/users/{quote(user_id, safe='')}", json=changes)

    def delete_user(self, user_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/admin/users/{quote(user_id, safe='')}")

    def list_audits(self, limit: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/admin/audits", params={"limit": limit})

    def register_device(self, device_id: str, platform: str, display_name: str, public_key: str | None = None, lan_endpoints: list[str] | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/devices", json={"device_id": device_id, "platform": platform, "display_name": display_name, "public_key": public_key, "lan_endpoints": lan_endpoints or []})

    def list_devices(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/devices")

    def revoke_device(self, device_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/devices/{quote(device_id, safe='')}")

    def rotate_device_key(self, device_id: str, public_key: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/devices/{quote(device_id, safe='')}/rotate-key", json={"public_key": public_key})

    def create_grant(self, controller_device_id: str, host_device_id: str, role: str = "standard", scopes: list[str] | None = None, workspace_refs: list[str] | None = None, expires_at: int | None = None) -> dict[str, Any]:
        payload = {"controller_device_id": controller_device_id, "host_device_id": host_device_id, "role": role, "workspace_refs": workspace_refs or [], "expires_at": expires_at}
        if scopes is not None:
            payload["scopes"] = scopes
        return self._request("POST", "/v1/grants", json=payload)

    def revoke_grant(self, grant_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/grants/{quote(grant_id, safe='')}/revoke")

    def list_grants(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/grants")

    def heartbeat(self, device_id: str | None = None, lan_endpoints: list[str] | None = None) -> dict[str, Any]:
        payload = None if lan_endpoints is None else {"lan_endpoints": lan_endpoints}
        return self._request("POST", f"/v1/devices/{device_id or self.device_id}/heartbeat", json=payload)

    def request_device_challenge(self, device_id: str | None = None) -> dict[str, Any]:
        return self._request("POST", f"/v1/devices/{device_id or self.device_id}/challenge")

    def verify_device_challenge(self, challenge: str, signature: str, device_id: str | None = None) -> dict[str, Any]:
        return self._request("POST", f"/v1/devices/{device_id or self.device_id}/challenge/verify", json={"challenge": challenge, "signature": signature})

    def create_session(self, kind: str, title: str = "New session", workspace_id: str = "default", model_id: str | None = None) -> dict[str, Any]:
        return self._request("POST", "/v1/cloud/sessions", json={"kind": kind, "title": title, "workspace_id": workspace_id, "model_id": model_id})

    def list_models(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/models")

    def create_model(self, name: str, provider: str, model: str, *, base_url: str | None = None, api_key: str | None = None, enabled: bool = True, is_default: bool = False) -> dict[str, Any]:
        return self._request("POST", "/v1/models", json={"name": name, "provider": provider, "model": model, "base_url": base_url, "api_key": api_key, "enabled": enabled, "is_default": is_default})

    def update_model(self, model_id: str, **changes: Any) -> dict[str, Any]:
        return self._request("PUT", f"/v1/models/{model_id}", json=changes)

    def delete_model(self, model_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/models/{model_id}")

    def import_session(self, snapshot: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", "/v1/cloud/sessions/import", json=snapshot)

    def send_command(self, session_id: str, request_id: str, input_text: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/cloud/sessions/{session_id}/commands", json={"request_id": request_id, "input": input_text})

    def snapshot(self, session_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/cloud/sessions/{session_id}/snapshot")

    def list_sessions(self) -> list[dict[str, Any]]:
        return self._request("GET", "/v1/cloud/sessions")

    def archive_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/cloud/sessions/{session_id}/archive")

    def restore_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/cloud/sessions/{session_id}/restore")

    def copy_session(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/cloud/sessions/{session_id}/copy")

    def delete_session(self, session_id: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/cloud/sessions/{quote(session_id, safe='')}")

    def rotate_authority(self, session_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/cloud/sessions/{session_id}/authority/rotate")

    def acquire_authority_lease(self, session_id: str, owner: str, ttl_seconds: int = 30) -> dict[str, Any]:
        return self._request("POST", f"/v1/cloud/sessions/{session_id}/authority/lease", json={"owner": owner, "ttl_seconds": ttl_seconds})

    def release_authority_lease(self, session_id: str, owner: str) -> dict[str, Any]:
        return self._request("DELETE", f"/v1/cloud/sessions/{session_id}/authority/lease", params={"owner": owner})

    def events(self, session_id: str, after: int = 0) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/cloud/sessions/{session_id}/events", params={"after": after})

    def list_approvals(self, session_id: str) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/cloud/sessions/{session_id}/approvals")

    def resolve_approval(self, session_id: str, approval_id: str, status: str, note: str | None = None) -> dict[str, Any]:
        return self._request("POST", f"/v1/cloud/sessions/{session_id}/approvals/{approval_id}/resolve", json={"status": status, "note": note})

    def recover_command(self, session_id: str, command_id: str, mode: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/cloud/sessions/{session_id}/commands/{command_id}/recover", json={"mode": mode})

    def command_status(self, session_id: str, command_id: str) -> dict[str, Any]:
        return self._request("GET", f"/v1/cloud/sessions/{quote(session_id, safe='')}/commands/{quote(command_id, safe='')}")

    def list_commands(self, session_id: str, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        return self._request("GET", f"/v1/cloud/sessions/{quote(session_id, safe='')}/commands", params={"after": after, "limit": limit})

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

    def list_share_tokens(self, session_id: str | None = None) -> list[dict[str, Any]]:
        params = {"session_id": session_id} if session_id else None
        return self._request("GET", "/v1/share-tokens", params=params)

    def revoke_share_token(self, token_id: str) -> dict[str, Any]:
        return self._request("POST", f"/v1/share-tokens/{quote(token_id, safe='')}/revoke")

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
