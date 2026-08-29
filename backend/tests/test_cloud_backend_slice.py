from pathlib import Path
import base64

from fastapi.testclient import TestClient

from cloud.app import create_app
from cloud.config import CloudSettings


PUBLIC_KEY = base64.urlsafe_b64encode(b"k" * 32).decode()
NONCE = base64.urlsafe_b64encode(b"n" * 12).decode()


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


def test_login_supports_explicit_account_id(tmp_path):
    with client(tmp_path) as http:
        admin_token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        created = http.post("/v1/admin/users", headers=headers, json={"username": "label", "password": "label-password-123"}).json()["data"]
        response = http.post("/v1/auth/login", json={"account_id": created["id"], "password": "label-password-123"})
        assert response.status_code == 200 and response.json()["data"]["user_id"] == created["id"]


def test_duplicate_usernames_require_account_id(tmp_path):
    with client(tmp_path) as http:
        admin_token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {admin_token}"}
        first = http.post("/v1/admin/users", headers=headers, json={"username": "same-label", "password": "first-password-123"}).json()["data"]
        second = http.post("/v1/admin/users", headers=headers, json={"username": "same-label", "password": "second-password-123"}).json()["data"]
        assert first["id"] != second["id"]
        assert http.post("/v1/auth/login", json={"username": "same-label", "password": "first-password-123"}).status_code == 401
        assert http.post("/v1/auth/login", json={"account_id": second["id"], "password": "second-password-123"}).status_code == 200


def test_legacy_username_unique_schema_migrates(tmp_path):
    import sqlite3

    database = tmp_path / "legacy.db"
    with sqlite3.connect(database) as cx:
        cx.execute("CREATE TABLE users (id TEXT PRIMARY KEY, username TEXT NOT NULL UNIQUE, password_hash TEXT NOT NULL, role TEXT NOT NULL, disabled INTEGER NOT NULL DEFAULT 0, created_at INTEGER NOT NULL)")
        cx.execute("INSERT INTO users VALUES ('u1','same','hash','user',0,1)")
    from cloud.db import CloudDB

    CloudDB(database).init()
    with sqlite3.connect(database) as cx:
        cx.execute("INSERT INTO users VALUES ('u2','same','hash','user',0,2)")
        assert cx.execute("SELECT COUNT(*) FROM users WHERE username='same'").fetchone()[0] == 2


def test_device_registration_and_revoke(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        response = http.post("/v1/devices", headers=headers, json={"device_id": "desktop-unique-1", "platform": "desktop", "display_name": "Mac"})
        assert response.status_code == 200
        assert http.get("/v1/devices", headers=headers).json()["data"][0]["id"] == "desktop-unique-1"
        assert http.post("/v1/devices/desktop-unique-1/revoke", headers=headers).status_code == 200


def test_device_key_rotation_replaces_public_key(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert http.post("/v1/devices", headers=headers, json={"device_id": "rotating-device", "platform": "desktop", "display_name": "Desktop", "public_key": PUBLIC_KEY}).status_code == 200
        rotated_key = base64.urlsafe_b64encode(b"r" * 32).decode()
        assert http.post("/v1/devices/rotating-device/rotate-key", headers=headers, json={"public_key": rotated_key}).status_code == 200
        device = http.get("/v1/devices", headers=headers).json()["data"][0]
        assert device["public_key"] == rotated_key


def test_device_revoke_also_revokes_grants(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("revoke-controller", "revoke-host"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        grant = http.post("/v1/grants", headers=headers, json={"controller_device_id": "revoke-controller", "host_device_id": "revoke-host"}).json()["data"]["grant_id"]
        assert http.post("/v1/devices/revoke-host/revoke", headers=headers).status_code == 200
        listed = next(item for item in http.get("/v1/grants", headers=headers).json()["data"] if item["id"] == grant)
        assert listed["revoked_at"] is not None


def test_device_heartbeat_updates_last_seen(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert http.post("/v1/devices", headers=headers, json={"device_id": "heartbeat-device", "platform": "test", "display_name": "Heartbeat"}).status_code == 200
        result = http.post("/v1/devices/heartbeat-device/heartbeat", headers=headers)
        assert result.status_code == 200 and result.json()["data"]["last_seen_at"]
        listed = http.get("/v1/devices", headers=headers).json()["data"][0]
        assert listed["last_seen_at"] == result.json()["data"]["last_seen_at"]


def test_cors_requires_explicit_origin_allowlist(tmp_path):
    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123", cors_origins=("https://web.example",))
    with TestClient(create_app(settings)) as http:
        response = http.options("/health", headers={"Origin": "https://web.example", "Access-Control-Request-Method": "GET"})
        assert response.status_code == 200
        assert response.headers["access-control-allow-origin"] == "https://web.example"


def test_readiness_checks_database_and_workspace(tmp_path):
    with client(tmp_path) as http:
        response = http.get("/ready")
        assert response.status_code == 200
        assert response.json()["ready"] is True
        assert response.json()["checks"] == {"database": "ok", "workspace_root": "ok"}


def test_pairing_grant_and_token_revoke(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        first = http.post("/v1/devices", headers=headers, json={"device_id": "desktop-unique-1", "platform": "desktop", "display_name": "Desktop", "public_key": PUBLIC_KEY})
        second = http.post("/v1/pairings/start", headers=headers)
        code = second.json()["data"]["code"]
        paired = http.post("/v1/pairings/confirm", headers=headers, json={"code": code, "device_id": "phone-unique-1", "platform": "ios", "display_name": "Phone", "public_key": PUBLIC_KEY})
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
        assert first["status"] == "completed"
        assert http.get(f"/v1/sessions/{session['id']}/commands/{first['command_id']}", headers=headers).json()["data"]["status"] == "completed"
        assert len(http.get(f"/v1/sessions/{session['id']}/commands", headers=headers).json()["data"]) == 1
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


def test_share_token_is_scoped_and_revocable(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json={"request_id": "share-1", "input": "hello"})
        created = http.post("/v1/share-tokens", headers=headers, json={"session_id": session["id"], "expires_at": None}).json()["data"]
        shared_headers = {"X-Share-Token": created["token"]}
        assert http.get(f"/v1/shared/{session['id']}/snapshot", headers=shared_headers).status_code == 200
        assert http.post(f"/v1/shared/{session['id']}/commands", headers=shared_headers, json={"request_id": "viewer-1", "input": "nope"}).status_code == 403
        control = http.post("/v1/share-tokens", headers=headers, json={"session_id": session["id"], "role": "standard", "scopes": ["message.send"]}).json()["data"]
        assert http.post(f"/v1/shared/{session['id']}/commands", headers={"X-Share-Token": control["token"]}, json={"request_id": "control-1", "input": "allowed"}).status_code == 200
        assert http.get("/v1/share-tokens", headers=headers).json()["data"][0]["id"] == created["id"]
        assert http.post(f"/v1/share-tokens/{created['id']}/revoke", headers=headers).status_code == 200
        assert http.get(f"/v1/shared/{session['id']}/snapshot", headers=shared_headers).status_code == 401


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
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        grant = http.post("/v1/grants", headers=headers, json={"controller_device_id": "phone-unique-1", "host_device_id": "desktop-unique-1"}).json()["data"]["grant_id"]
        assert http.get("/v1/grants", headers=headers).json()["data"][0]["id"] == grant
        assert http.post(f"/v1/grants/{grant}/revoke", headers=headers).status_code == 200
        assert http.post(f"/v1/grants/{grant}/revoke", headers=headers).status_code == 404


def test_grant_requires_device_public_keys(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("no-key-controller", "no-key-host"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device}).status_code == 200
        response = http.post("/v1/grants", headers=headers, json={"controller_device_id": "no-key-controller", "host_device_id": "no-key-host"})
        assert response.status_code == 409


def test_admin_delete_cleans_owned_relations(tmp_path):
    with client(tmp_path) as http:
        admin = login(http, "admin", "admin-password-123")
        admin_headers = {"Authorization": f"Bearer {admin}"}
        user_id = http.post("/v1/admin/users", headers=admin_headers, json={"username": "owner", "password": "owner-password-123"}).json()["data"]["id"]
        user_headers = {"Authorization": f"Bearer {login(http, 'owner', 'owner-password-123')}"}
        for device in ("owner-desktop", "owner-phone"):
            assert http.post("/v1/devices", headers=user_headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        session = http.post("/v1/sessions", headers=user_headers, json={"kind": "cloud_native"}).json()["data"]
        assert http.post("/v1/grants", headers=user_headers, json={"controller_device_id": "owner-phone", "host_device_id": "owner-desktop"}).status_code == 200
        assert http.post("/v1/share-tokens", headers=user_headers, json={"session_id": session["id"]}).status_code == 200
        assert http.delete(f"/v1/admin/users/{user_id}", headers=admin_headers).status_code == 200


def test_relay_rejects_replay_and_reports_offline_host(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("relay-controller", "relay-host"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        assert http.post("/v1/grants", headers=headers, json={"controller_device_id": "relay-controller", "host_device_id": "relay-host", "scopes": ["message.send"]}).status_code == 200
        session = http.post("/v1/sessions", headers=headers, json={"kind": "device_remote"}).json()["data"]
        frame = {"protocol_version": "notemeld.sync.v1", "session_id": session["id"], "sender_device_id": "relay-controller", "recipient_device_id": "relay-host", "sequence": 1, "frame_id": "frame-1", "authority_epoch": 1, "frame_type": "command", "nonce": NONCE, "ciphertext": "opaque"}
        with http.websocket_connect(f"/v1/relay/connect/{session['id']}?device_id=relay-controller", headers=headers) as socket:
            socket.send_json(frame)
            assert socket.receive_json()["error"] == "host_offline"
            socket.send_json(frame)
            assert socket.receive_json()["error"] == "invalid_envelope"


def test_relay_forwards_to_target_and_allows_host_receipt(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("controller-online", "host-online"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        assert http.post("/v1/grants", headers=headers, json={"controller_device_id": "controller-online", "host_device_id": "host-online", "scopes": ["message.send"]}).status_code == 200
        session = http.post("/v1/sessions", headers=headers, json={"kind": "device_remote"}).json()["data"]
        frame = {"protocol_version": "notemeld.sync.v1", "session_id": session["id"], "sender_device_id": "controller-online", "recipient_device_id": "host-online", "sequence": 1, "frame_id": "frame-online", "authority_epoch": 1, "frame_type": "command", "nonce": NONCE, "ciphertext": "opaque"}
        receipt = {**frame, "sender_device_id": "host-online", "recipient_device_id": "controller-online", "sequence": 1, "frame_id": "receipt-online", "frame_type": "receipt", "ciphertext": "received"}
        with http.websocket_connect(f"/v1/relay/connect/{session['id']}?device_id=controller-online", headers=headers) as controller, http.websocket_connect(f"/v1/relay/connect/{session['id']}?device_id=host-online", headers=headers) as host:
            controller.send_json(frame)
            assert controller.receive_json()["type"] == "relay_accepted"
            assert host.receive_json()["frame_id"] == "frame-online"
            host.send_json(receipt)
            assert host.receive_json()["type"] == "relay_accepted"
            assert controller.receive_json()["frame_id"] == "receipt-online"


def test_relay_command_requires_message_scope(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("scope-controller", "scope-host"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        assert http.post("/v1/grants", headers=headers, json={"controller_device_id": "scope-controller", "host_device_id": "scope-host"}).status_code == 200
        session = http.post("/v1/sessions", headers=headers, json={"kind": "device_remote"}).json()["data"]
        with http.websocket_connect(f"/v1/relay/connect/{session['id']}?device_id=scope-controller", headers=headers) as socket:
            socket.send_json({"protocol_version": "notemeld.sync.v1", "session_id": session["id"], "sender_device_id": "scope-controller", "recipient_device_id": "scope-host", "sequence": 1, "frame_id": "scope-frame", "frame_type": "command", "nonce": NONCE, "ciphertext": "opaque"})
            assert socket.receive_json()["error"] == "invalid_envelope"


def test_authority_rotation_invalidates_old_relay_epoch(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("epoch-controller", "epoch-host"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        assert http.post("/v1/grants", headers=headers, json={"controller_device_id": "epoch-controller", "host_device_id": "epoch-host", "scopes": ["message.send"]}).status_code == 200
        session = http.post("/v1/sessions", headers=headers, json={"kind": "device_remote"}).json()["data"]
        assert http.post(f"/v1/sessions/{session['id']}/authority/rotate", headers=headers).json()["data"]["authority_epoch"] == 2
        with http.websocket_connect(f"/v1/relay/connect/{session['id']}?device_id=epoch-controller", headers=headers) as socket:
            socket.send_json({"protocol_version": "notemeld.sync.v1", "session_id": session["id"], "sender_device_id": "epoch-controller", "recipient_device_id": "epoch-host", "sequence": 1, "frame_id": "old-epoch", "authority_epoch": 1, "frame_type": "command", "nonce": NONCE, "ciphertext": "opaque"})
            assert socket.receive_json()["error"] == "invalid_envelope"


def test_authority_lease_is_exclusive_until_expiry(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        assert http.post(f"/v1/sessions/{session['id']}/authority/lease", headers=headers, json={"owner": "worker-a"}).status_code == 200
        assert http.post(f"/v1/sessions/{session['id']}/authority/lease", headers=headers, json={"owner": "worker-b"}).status_code == 409
        assert http.post(f"/v1/sessions/{session['id']}/authority/lease", headers=headers, json={"owner": "worker-a", "ttl_seconds": 60}).status_code == 200
        assert http.delete(f"/v1/sessions/{session['id']}/authority/lease", headers=headers, params={"owner": "worker-b"}).status_code == 409
        assert http.delete(f"/v1/sessions/{session['id']}/authority/lease", headers=headers, params={"owner": "worker-a"}).status_code == 200


def test_workspace_quota_is_enforced(tmp_path):
    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123", max_workspace_bytes=4)
    with TestClient(create_app(settings)) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert http.put("/v1/workspaces/quota/files/a.txt", headers=headers, json={"content": "1234"}).status_code == 200
        assert http.put("/v1/workspaces/quota/files/b.txt", headers=headers, json={"content": "5"}).status_code == 413


def test_workspace_backup_list_and_restore(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert http.put("/v1/workspaces/backup/files/a.txt", headers=headers, json={"content": "before"}).status_code == 200
        backup = http.post("/v1/workspaces/backup/backups", headers=headers).json()["data"]
        assert http.put("/v1/workspaces/backup/files/a.txt", headers=headers, json={"content": "after"}).status_code == 200
        assert http.get("/v1/workspaces/backup/backups", headers=headers).json()["data"][0]["backup_id"] == backup["backup_id"]
        restored = http.post("/v1/workspaces/backup/backups/restore", headers=headers, json={"backup_id": backup["backup_id"]})
        assert restored.status_code == 200
        assert http.get("/v1/workspaces/backup/files/a.txt", headers=headers).json()["data"]["content"] == "before"


def test_admin_audits_are_sanitized(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        http.post("/v1/admin/users", headers=headers, json={"username": "audited", "password": "audited-password-123"})
        audits = http.get("/v1/admin/audits", headers=headers).json()["data"]
        assert any(item["action"] == "admin.user.create" for item in audits)
        assert all("password" not in item["metadata"] and "token" not in item["metadata"] for item in audits)


def test_login_bruteforce_limit(tmp_path):
    with client(tmp_path) as http:
        for _ in range(5):
            assert http.post("/v1/auth/login", json={"username": "admin", "password": "wrong-password-123"}).status_code == 401
        assert http.post("/v1/auth/login", json={"username": "admin", "password": "wrong-password-123"}).status_code == 429


def test_password_change_revokes_existing_tokens(tmp_path):
    with client(tmp_path) as http:
        admin = login(http, "admin", "admin-password-123")
        admin_headers = {"Authorization": f"Bearer {admin}"}
        created = http.post("/v1/admin/users", headers=admin_headers, json={"username": "rotate-password", "password": "old-password-123"}).json()["data"]
        user_token = login(http, "rotate-password", "old-password-123")
        response = http.put(f"/v1/admin/users/{created['id']}", headers=admin_headers, json={"password": "new-password-123"})
        assert response.status_code == 200
        assert http.get("/v1/devices", headers={"Authorization": f"Bearer {user_token}"}).status_code == 401
        assert http.post("/v1/auth/login", json={"account_id": created["id"], "password": "new-password-123"}).status_code == 200


def test_session_copy_is_independent_with_provenance(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        source = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native", "title": "source"}).json()["data"]
        http.put(f"/v1/workspaces/{source['workspace_id']}/files/context.txt", headers=headers, json={"content": "copied"})
        http.post(f"/v1/sessions/{source['id']}/commands", headers=headers, json={"request_id": "copy-1", "input": "hello"})
        copied = http.post(f"/v1/sessions/{source['id']}/copy", headers=headers)
        assert copied.status_code == 200
        target = copied.json()["data"]
        assert target["id"] != source["id"] and target["copied_from"] == source["id"]
        assert http.get(f"/v1/workspaces/{target['workspace_id']}/files/context.txt", headers=headers).json()["data"]["content"] == "copied"
        assert http.post(f"/v1/sessions/{target['id']}/commands", headers=headers, json={"request_id": "copy-2", "input": "independent"}).status_code == 200
