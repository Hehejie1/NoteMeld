from pathlib import Path

from fastapi.testclient import TestClient

from cloud.app import create_app
from cloud.config import CloudSettings


def _client(tmp_path: Path) -> tuple[TestClient, dict[str, str]]:
    client = TestClient(create_app(CloudSettings(tmp_path / "data", "admin", "admin-password-123")))
    token = client.post("/v1/auth/login", json={"username": "admin", "password": "admin-password-123"}).json()["data"]["token"]
    return client, {"Authorization": f"Bearer {token}"}


def test_config_sync_is_revisioned_idempotent_and_tombstoned(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        assert client.get("/v1/config-sync/snapshot", headers=headers).json()["data"]["revision"] == 0
        change = {
            "workspace_id": "default",
            "base_revision": 0,
            "idempotency_key": "config-sync-test-1",
            "changes": [{"kind": "user_preference", "key": "theme", "operation": "set", "value": "dark"}],
        }
        first = client.post("/v1/config-sync/changes", headers=headers, json=change)
        assert first.status_code == 200
        assert client.post("/v1/config-sync/changes", headers=headers, json=change).json() == first.json()
        conflict = client.post("/v1/config-sync/changes", headers=headers, json={**change, "idempotency_key": "config-sync-test-2"})
        assert conflict.status_code == 409
        assert client.get("/v1/config-sync/snapshot?after_revision=0", headers=headers).json()["data"]["items"][0]["value"] == "dark"
        deleted = client.post("/v1/config-sync/changes", headers=headers, json={
            "workspace_id": "default", "base_revision": 1, "idempotency_key": "config-sync-test-3",
            "changes": [{"kind": "user_preference", "key": "theme", "operation": "delete"}],
        })
        assert deleted.status_code == 200
        assert client.get("/v1/config-sync/snapshot?after_revision=1", headers=headers).json()["data"]["deleted"][0]["key"] == "theme"


def test_config_sync_rejects_sensitive_keys(tmp_path):
    client, headers = _client(tmp_path)
    with client:
        response = client.post("/v1/config-sync/changes", headers=headers, json={
            "workspace_id": "default", "base_revision": 0, "idempotency_key": "config-sync-secret",
            "changes": [{"kind": "provider", "key": "api_key", "operation": "set", "value": "secret"}],
        })
        assert response.status_code == 422
