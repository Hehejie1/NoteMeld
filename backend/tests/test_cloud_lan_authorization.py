from __future__ import annotations

import base64
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cloud.app import create_app
from cloud.config import CloudSettings


Ed25519PrivateKey = pytest.importorskip(
    "cryptography.hazmat.primitives.asymmetric.ed25519"
).Ed25519PrivateKey


def _headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _register_device(
    http: TestClient,
    account_token: str,
    device_id: str,
) -> Ed25519PrivateKey:
    private_key = Ed25519PrivateKey.generate()
    public_key = base64.urlsafe_b64encode(
        private_key.public_key().public_bytes_raw()
    ).decode().rstrip("=")
    response = http.post(
        "/v1/devices/register",
        headers=_headers(account_token),
        json={
            "device_id": device_id,
            "platform": "test",
            "display_name": device_id,
            "public_key": public_key,
        },
    )
    assert response.status_code == 200
    return private_key


def _issue_device_token(
    http: TestClient,
    account_token: str,
    device_id: str,
    private_key: Ed25519PrivateKey,
) -> str:
    challenge = http.post(
        f"/v1/devices/{device_id}/challenge",
        headers=_headers(account_token),
    ).json()["data"]["challenge"]
    proof = (
        b"notemeld-device-proof-v1\0"
        + device_id.encode()
        + b"\0"
        + challenge.encode()
    )
    signature = base64.urlsafe_b64encode(private_key.sign(proof)).decode().rstrip("=")
    verified = http.post(
        f"/v1/devices/{device_id}/challenge/verify",
        headers=_headers(account_token),
        json={"challenge": challenge, "signature": signature},
    )
    assert verified.status_code == 200
    issued = http.post(
        f"/v1/devices/{device_id}/token",
        headers=_headers(account_token),
        json={"scopes": ["grant.read"], "revoke_source_token": False},
    )
    assert issued.status_code == 200
    return issued.json()["data"]["token"]


def _setup(tmp_path: Path):
    settings = CloudSettings(
        tmp_path / "data",
        "admin",
        "admin-password-123",
        secret_key="test-secret-key-not-for-production",
    )
    http = TestClient(create_app(settings))
    http.__enter__()
    account_token = http.post(
        "/v1/auth/login",
        json={"username": "admin", "password": "admin-password-123"},
    ).json()["data"]["token"]
    host_id = "desktop-host-device"
    controller_id = "mobile-controller-device"
    host_private = _register_device(http, account_token, host_id)
    _register_device(http, account_token, controller_id)
    session = http.post(
        "/v1/sessions",
        headers=_headers(account_token),
        json={"kind": "device_remote", "workspace_id": "project-a"},
    ).json()["data"]
    grant = http.post(
        "/v1/grants",
        headers=_headers(account_token),
        json={
            "controller_device_id": controller_id,
            "host_device_id": host_id,
            "workspace_refs": ["project-a"],
        },
    ).json()["data"]
    host_token = _issue_device_token(http, account_token, host_id, host_private)
    return http, account_token, host_token, host_id, controller_id, session, grant


def test_bound_host_receives_short_lived_lan_authorization(tmp_path: Path):
    http, account_token, host_token, host_id, controller_id, session, grant = _setup(
        tmp_path
    )
    try:
        before = int(time.time())
        payload = {
            "session_id": session["id"],
            "controller_device_id": controller_id,
            "host_device_id": host_id,
        }
        response = http.post(
            "/v1/lan/authorize", headers=_headers(host_token), json=payload
        )
        assert response.status_code == 200
        data = response.json()["data"]
        assert data["grant_id"] == grant["grant_id"]
        assert data["controller_public_key"]
        assert data["workspace_id"] == "project-a"
        assert data["authority_epoch"] == 1
        assert "message.send" in data["scopes"]
        assert before < data["valid_until"] <= before + 60
        assert 1 <= data["ttl_seconds"] <= 60
        assert "token" not in data and "private_key" not in data

        assert http.post(
            "/v1/lan/authorize", headers=_headers(account_token), json=payload
        ).status_code == 403
        assert http.post(
            "/v1/lan/authorize",
            headers=_headers(host_token),
            json={**payload, "host_device_id": controller_id},
        ).status_code == 403
    finally:
        http.__exit__(None, None, None)


def test_lan_authorization_fails_after_grant_revocation(tmp_path: Path):
    http, account_token, host_token, host_id, controller_id, session, grant = _setup(
        tmp_path
    )
    try:
        assert http.delete(
            f"/v1/grants/{grant['grant_id']}", headers=_headers(account_token)
        ).status_code == 200
        response = http.post(
            "/v1/lan/authorize",
            headers=_headers(host_token),
            json={
                "session_id": session["id"],
                "controller_device_id": controller_id,
                "host_device_id": host_id,
            },
        )
        assert response.status_code == 403
        assert response.json()["detail"] == "active LAN control grant not found"
    finally:
        http.__exit__(None, None, None)
