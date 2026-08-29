from pathlib import Path

from fastapi.testclient import TestClient

from cloud.app import create_app
from cloud.config import CloudSettings


def client(tmp_path: Path) -> TestClient:
    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123")
    return TestClient(create_app(settings))


def login(client: TestClient, username: str, password: str) -> str:
    response = client.post("/v1/auth/login", json={"username": username, "password": password})
    assert response.status_code == 200
    return response.json()["data"]["token"]


def test_bootstrap_admin_and_user_crud(tmp_path):
    with client(tmp_path) as http:
        admin_token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        created = http.post("/v1/admin/users", headers=headers, json={"username": "alice", "password": "alice-password-123"})
        assert created.status_code == 200
        users = http.get("/v1/admin/users", headers=headers).json()["data"]
        assert {user["username"] for user in users} == {"admin", "alice"}
        updated = http.put(f"/v1/admin/users/{created.json()['data']['id']}", headers=headers, json={"disabled": True})
        assert updated.status_code == 200
        assert http.delete(f"/v1/admin/users/{created.json()['data']['id']}", headers=headers).status_code == 200


def test_device_registration_and_revoke(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        response = http.post("/v1/devices", headers=headers, json={"device_id": "desktop-unique-1", "platform": "desktop", "display_name": "Mac"})
        assert response.status_code == 200
        assert http.get("/v1/devices", headers=headers).json()["data"][0]["id"] == "desktop-unique-1"
        assert http.post("/v1/devices/desktop-unique-1/revoke", headers=headers).status_code == 200


def test_pairing_grant_and_token_revoke(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        first = http.post("/v1/devices", headers=headers, json={"device_id": "desktop-unique-1", "platform": "desktop", "display_name": "Desktop"})
        second = http.post("/v1/pairings/start", headers=headers)
        code = second.json()["data"]["code"]
        paired = http.post("/v1/pairings/confirm", headers=headers, json={"code": code, "device_id": "phone-unique-1", "platform": "ios", "display_name": "Phone"})
        assert first.status_code == paired.status_code == 200
        grant = http.post("/v1/grants", headers=headers, json={"controller_device_id": "phone-unique-1", "host_device_id": "desktop-unique-1", "scopes": ["message.send"]})
        assert grant.status_code == 200
        assert http.post("/v1/auth/revoke", headers=headers).status_code == 200
        assert http.get("/v1/devices", headers=headers).status_code == 401


def test_session_command_idempotency_and_snapshot(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native", "title": "test"}).json()["data"]
        payload = {"request_id": "req-1", "input": "hello"}
        first = http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json=payload).json()["data"]
        second = http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json=payload).json()["data"]
        assert first["command_id"] == second["command_id"]
        assert second["idempotent"] is True
        conflict = http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json={"request_id": "req-1", "input": "different"})
        assert conflict.status_code == 409
        snapshot = http.get(f"/v1/sessions/{session['id']}/snapshot", headers=headers).json()["data"]
        assert snapshot["snapshot_seq"] == 2
        assert snapshot["events"][-1]["event_type"] == "turn.completed"


def test_session_archive_delete_and_token_rotate(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        assert http.post(f"/v1/sessions/{session['id']}/archive", headers=headers).status_code == 200
        assert http.get("/v1/sessions", headers=headers).json()["data"][0]["archived_at"]
        assert http.post(f"/v1/sessions/{session['id']}/restore", headers=headers).status_code == 200
        assert http.get("/v1/sessions", headers=headers).json()["data"][0]["archived_at"] is None
        rotated = http.post("/v1/auth/rotate", headers=headers)
        assert rotated.status_code == 200
        assert http.get("/v1/sessions", headers=headers).status_code == 401
        new_headers = {"Authorization": f"Bearer {rotated.json()['data']['token']}"}
        assert http.delete(f"/v1/sessions/{session['id']}", headers=new_headers).status_code == 200


def test_device_remote_cannot_execute_in_cloud(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "device_remote"}).json()["data"]
        response = http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json={"request_id": "remote-1", "input": "hello"})
        assert response.status_code == 409


def test_workspace_rejects_escape(tmp_path):
    from cloud.workspace import Workspace, WorkspaceError

    workspace = Workspace(tmp_path / "workspace")
    try:
        workspace.path("../outside")
    except WorkspaceError:
        pass
    else:
        raise AssertionError("path traversal was accepted")


def test_workspace_file_api_is_atomic_and_scoped(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        written = http.put("/v1/workspaces/demo/files/notes/today.md", headers=headers, json={"content": "hello"})
        assert written.status_code == 200
        assert written.json()["data"]["bytes_written"] == 5
        read = http.get("/v1/workspaces/demo/files/notes/today.md", headers=headers)
        assert read.status_code == 200 and read.json()["data"]["content"] == "hello"
        stats = http.get("/v1/workspaces/demo/stats", headers=headers).json()["data"]
        assert stats == {"workspace_id": "demo", "file_count": 1, "bytes_used": 5}
        assert http.put("/v1/workspaces/demo/files/../escape.txt", headers=headers, json={"content": "x"}).status_code in (400, 404)


def test_grant_listing_and_revocation(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("desktop-unique-1", "phone-unique-1"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device}).status_code == 200
        grant = http.post("/v1/grants", headers=headers, json={"controller_device_id": "phone-unique-1", "host_device_id": "desktop-unique-1"}).json()["data"]["grant_id"]
        assert http.get("/v1/grants", headers=headers).json()["data"][0]["id"] == grant
        assert http.post(f"/v1/grants/{grant}/revoke", headers=headers).status_code == 200
        assert http.post(f"/v1/grants/{grant}/revoke", headers=headers).status_code == 404
