from pathlib import Path
import base64
import hashlib
import threading
import time
from concurrent.futures import ThreadPoolExecutor
import pytest

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
        assert response.json()["data"]["audience"] == "cloud-api" and response.json()["data"]["scopes"] == ["*"]


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


def test_same_account_device_registration_is_idempotent(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        payload = {"device_id": "idempotent-device", "platform": "desktop", "display_name": "Old"}
        assert http.post("/v1/devices", headers=headers, json=payload).status_code == 200
        payload["display_name"] = "New"
        assert http.post("/v1/devices", headers=headers, json=payload).status_code == 200
        assert http.get("/v1/devices", headers=headers).json()["data"][0]["display_name"] == "New"


def test_device_key_rotation_replaces_public_key(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert http.post("/v1/devices", headers=headers, json={"device_id": "rotating-device", "platform": "desktop", "display_name": "Desktop", "public_key": PUBLIC_KEY}).status_code == 200
        rotated_key = base64.urlsafe_b64encode(b"r" * 32).decode()
        assert http.post("/v1/devices/rotating-device/rotate-key", headers=headers, json={"public_key": rotated_key}).status_code == 200
        device = http.get("/v1/devices", headers=headers).json()["data"][0]
        assert device["public_key"] == rotated_key


def test_device_proof_challenge_binds_private_key(tmp_path):
    Ed25519PrivateKey = pytest.importorskip("cryptography.hazmat.primitives.asymmetric.ed25519").Ed25519PrivateKey

    private = Ed25519PrivateKey.generate()
    public = private.public_key().public_bytes_raw()
    public_b64 = base64.urlsafe_b64encode(public).decode().rstrip("=")
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        device_id = "proof-device-unique"
        assert http.post("/v1/devices/register", headers=headers, json={"device_id": device_id, "platform": "ios", "display_name": "Phone", "public_key": public_b64}).status_code == 200
        challenge = http.post(f"/v1/devices/{device_id}/challenge", headers=headers).json()["data"]["challenge"]
        message = b"notemeld-device-proof-v1\0" + device_id.encode() + b"\0" + challenge.encode()
        signature = base64.urlsafe_b64encode(private.sign(message)).decode().rstrip("=")
        proof = http.post(f"/v1/devices/{device_id}/challenge/verify", headers=headers, json={"challenge": challenge, "signature": signature})
        assert proof.status_code == 200
        assert http.post(f"/v1/devices/{device_id}/challenge/verify", headers=headers, json={"challenge": challenge, "signature": signature}).status_code == 401


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


def test_grant_default_scopes_match_standard_control_policy(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("default-controller", "default-host"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        assert http.post("/v1/grants", headers=headers, json={"controller_device_id": "default-controller", "host_device_id": "default-host"}).status_code == 200
        grant = http.get("/v1/grants", headers=headers).json()["data"][0]
        assert grant["scopes"] == ["message.send", "context.select", "model.select", "tool.invoke"]


def test_pairing_cannot_take_device_id_from_another_account(tmp_path):
    with client(tmp_path) as http:
        admin = login(http, "admin", "admin-password-123")
        admin_headers = {"Authorization": f"Bearer {admin}"}
        user = http.post("/v1/admin/users", headers=admin_headers, json={"username": "pair-owner", "password": "pair-owner-password-123"}).json()["data"]
        owner_headers = {"Authorization": f"Bearer {login(http, 'pair-owner', 'pair-owner-password-123')}"}
        assert http.post("/v1/devices", headers=owner_headers, json={"device_id": "owned-device", "platform": "test", "display_name": "Owned"}).status_code == 200
        pairing = http.post("/v1/pairings/start", headers=admin_headers).json()["data"]["code"]
        response = http.post("/v1/pairings/confirm", headers=admin_headers, json={"code": pairing, "device_id": "owned-device", "platform": "test", "display_name": "Hijack"})
        assert response.status_code == 409


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


def test_cloud_model_registry_never_returns_provider_secret(tmp_path):
    pytest.importorskip("cryptography")
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        created = http.post("/v1/models", headers=headers, json={"name": "OpenAI", "provider": "openai", "model": "gpt-test", "base_url": "https://example.invalid/v1", "api_key": "sk-private", "is_default": True})
        assert created.status_code == 200
        model = created.json()["data"]
        assert model["has_api_key"] is True
        assert "api_key" not in model and "ciphertext" not in str(model).lower()
        listed = http.get("/v1/models", headers=headers).json()["data"]
        assert listed[0]["has_api_key"] is True
        assert "api_key_ciphertext" not in listed[0]
        assert http.put(f"/v1/models/{model['id']}", headers=headers, json={"is_default": False}).status_code == 200
        assert http.delete(f"/v1/models/{model['id']}", headers=headers).status_code == 200


def test_cloud_commands_are_serial_per_session(tmp_path):
    from cloud.agent import AgentResult

    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123")
    app = create_app(settings)
    active = 0
    maximum = 0
    state_lock = threading.Lock()

    class SlowRunner:
        def complete(self, *, input_text, messages, **kwargs):
            del kwargs
            nonlocal active, maximum
            with state_lock:
                active += 1
                maximum = max(maximum, active)
            time.sleep(0.05)
            with state_lock:
                active -= 1
            return AgentResult(content=f"answer:{input_text}", model="test")

    app.state.agent_runner = SlowRunner()
    with TestClient(app) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]

        def send(index):
            return http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json={"request_id": f"parallel-{index}", "input": f"message-{index}"})

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(send, range(2)))
        assert all(response.status_code == 200 for response in responses)
        assert maximum == 1


def test_cloud_provider_failure_is_persisted_as_failed_command(tmp_path):
    from cloud.agent import CloudAgentError

    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123")
    app = create_app(settings)

    class BrokenRunner:
        def complete(self, *, input_text, messages):
            raise CloudAgentError("provider payload must stay private")

    app.state.agent_runner = BrokenRunner()
    with TestClient(app) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        failed = http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json={"request_id": "provider-failure", "input": "hello"})
        assert failed.status_code == 502
        commands = http.get(f"/v1/sessions/{session['id']}/commands", headers=headers).json()["data"]
        assert commands[0]["status"] == "failed"
        snapshot = http.get(f"/v1/sessions/{session['id']}/snapshot", headers=headers).json()["data"]
        assert snapshot["events"][-1]["event_type"] == "turn.failed"
        assert "provider payload" not in snapshot["events"][-1]["payload"].get("error", {}).get("message", "")


def test_cloud_agent_receives_only_readonly_workspace_tools(tmp_path):
    from cloud.agent import AgentResult

    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123")
    app = create_app(settings)
    captured = {}

    class ToolAwareRunner:
        def complete(self, *, input_text, messages, tools=None, tool_handler=None):
            captured["tools"] = tools
            assert tool_handler is not None
            listing = tool_handler("workspace.list", {"prefix": ""})
            assert listing["ok"] is True
            return AgentResult(content=f"files={listing['file_count'] if 'file_count' in listing else len(listing['files'])}", model="test")

    app.state.agent_runner = ToolAwareRunner()
    with TestClient(app) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        http.put(f"/v1/workspaces/{session['workspace_id']}/files/readme.md", headers=headers, json={"content": "hello"})
        result = http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json={"request_id": "tool-read", "input": "inspect workspace"})
        assert result.status_code == 200
        assert {"workspace.list", "workspace.read"}.issubset({tool["name"] for tool in captured["tools"]})
        assert {"workspace.write", "workspace.delete"}.issubset({tool["name"] for tool in captured["tools"]})


def test_cloud_agent_dangerous_workspace_tool_requires_approval(tmp_path):
    from cloud.agent import AgentResult

    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123")
    app = create_app(settings)

    class ToolAwareRunner:
        def complete(self, *, input_text, messages, tools=None, tool_handler=None):
            del input_text, messages, tools
            result = tool_handler("workspace.write", {"path": "notes.txt", "content": "safe pending"})
            assert result["requires_approval"] is True
            return AgentResult(content=result["error"]["message"], model="test")

    app.state.agent_runner = ToolAwareRunner()
    with TestClient(app) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        response = http.post(f"/v1/sessions/{session['id']}/commands", headers=headers, json={"request_id": "approval-1", "input": "write a note"})
        assert response.status_code == 200
        approvals = http.get(f"/v1/sessions/{session['id']}/approvals", headers=headers).json()["data"]
        assert len(approvals) == 1 and approvals[0]["status"] == "pending"
        approval_id = approvals[0]["id"]
        resolved = http.post(f"/v1/sessions/{session['id']}/approvals/{approval_id}/resolve", headers=headers, json={"status": "approved"})
        assert resolved.status_code == 200
        assert resolved.json()["data"]["status"] == "approved"
        assert http.get(f"/v1/workspaces/{session['workspace_id']}/files/notes.txt", headers=headers).json()["data"]["content"] == "safe pending"


def test_cloud_startup_marks_running_commands_needs_attention(tmp_path):
    import uuid

    settings = CloudSettings(tmp_path / "data", "admin", "admin-password-123")
    app = create_app(settings)
    with TestClient(app) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        command_id = str(uuid.uuid4())
        with app.state.db.connect() as cx:
            cx.execute("UPDATE sessions SET status='running',next_sequence=2,next_event_sequence=2 WHERE id=?", (session["id"],))
            cx.execute("INSERT INTO commands(id,session_id,request_id,payload_hash,sequence,input_text,status,created_at) VALUES(?,?,?,?,?,?,?,?)", (command_id, session["id"], "crashed", "0" * 64, 1, "hello", "running", 1))
    recovered = create_app(settings)
    with TestClient(recovered) as http:
        token = login(http, "admin", "admin-password-123")
        snapshot = http.get(f"/v1/sessions/{session['id']}/snapshot", headers={"Authorization": f"Bearer {token}"}).json()["data"]
        assert snapshot["events"][-1]["event_type"] == "turn.needs_attention"
        assert snapshot["session"]["status"] == "idle"
        assert http.get(f"/v1/sessions/{session['id']}/commands/{command_id}", headers={"Authorization": f"Bearer {token}"}).json()["data"]["status"] == "needs_attention"
        headers = {"Authorization": f"Bearer {token}"}
        resumed = http.post(f"/v1/sessions/{session['id']}/commands/{command_id}/recover", headers=headers, json={"mode": "resume"})
        assert resumed.status_code == 200
        assert resumed.json()["data"]["status"] == "queued"
        deadline = time.time() + 2
        while time.time() < deadline:
            status = http.get(f"/v1/sessions/{session['id']}/commands/{command_id}", headers=headers).json()["data"]["status"]
            if status == "completed":
                break
            time.sleep(0.01)
        assert status == "completed"


def test_cloud_session_spec_prefix_aliases(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/cloud/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        assert http.get("/v1/cloud/sessions", headers=headers).status_code == 200
        command = http.post(f"/v1/cloud/sessions/{session['id']}/commands", headers=headers, json={"request_id": "prefix-1", "input": "hello"})
        assert command.status_code == 200
        assert http.get(f"/v1/cloud/sessions/{session['id']}/snapshot", headers=headers).status_code == 200
        assert http.get(f"/v1/cloud/sessions/{session['id']}/events", headers=headers).status_code == 200
        assert http.post(f"/v1/cloud/sessions/{session['id']}/archive", headers=headers).status_code == 200
        assert http.post(f"/v1/cloud/sessions/{session['id']}/restore", headers=headers).status_code == 200
        assert http.delete(f"/v1/cloud/sessions/{session['id']}", headers=headers).status_code == 200


def test_device_and_grant_spec_aliases(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("alias-controller", "alias-host"):
            assert http.post("/v1/devices/register", headers=headers, json={"device_id": device, "platform": "test", "display_name": device, "public_key": PUBLIC_KEY}).status_code == 200
        grant = http.post("/v1/grants", headers=headers, json={"controller_device_id": "alias-controller", "host_device_id": "alias-host"}).json()["data"]["grant_id"]
        assert http.delete(f"/v1/grants/{grant}", headers=headers).status_code == 200
        assert http.delete("/v1/devices/alias-host", headers=headers).status_code == 200


def test_local_session_full_share_import_is_sanitized_atomic_and_idempotent(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        assert http.post("/v1/devices", headers=headers, json={"device_id": "desktop-import-source", "platform": "desktop", "display_name": "Desktop"}).status_code == 200
        content = b"# Imported workspace\n"
        payload = {
            "request_id": "import-request-1",
            "source_session_id": "local-session-1",
            "source_device_id": "desktop-import-source",
            "title": "Imported",
            "conversation": {"messages": [{"role": "user", "content": "hello"}]},
            "events": [{"event_type": "message.created", "payload": {"role": "user"}, "created_at": 123}],
            "compression": {"summary": "short"},
            "memory": {"items": ["remember"]},
            "model_descriptor": {"provider": "local", "model": "example", "context_window_tokens": 8192},
            "mcp_config": {"servers": [{"name": "safe", "enabled": True}]},
            "tool_records": [],
            "approval_records": [],
            "task_state": {"status": "idle"},
            "provenance": {"origin": "local"},
            "files": [{"path": "notes/imported.md", "content_base64": base64.urlsafe_b64encode(content).decode(), "sha256": hashlib.sha256(content).hexdigest(), "size": len(content), "mime_type": "text/markdown"}],
        }
        created = http.post("/v1/cloud/sessions/import", headers=headers, json=payload)
        assert created.status_code == 200
        data = created.json()["data"]
        assert data["kind"] == "cloud_native" and data["file_count"] == 1 and data["idempotent"] is False
        snapshot = http.get(f"/v1/sessions/{data['id']}/snapshot", headers=headers).json()["data"]
        assert snapshot["events"][0]["created_at"] == 123
        assert snapshot["imported_snapshot"]["conversation"] == payload["conversation"]
        assert "content_base64" not in snapshot["imported_snapshot"]["files"][0]
        assert http.get(f"/v1/workspaces/{data['workspace_id']}/files/notes/imported.md", headers=headers).json()["data"]["content"] == content.decode()
        retried = http.post("/v1/cloud/sessions/import", headers=headers, json=payload).json()["data"]
        assert retried["id"] == data["id"] and retried["idempotent"] is True
        conflicting = {**payload, "title": "Different"}
        assert http.post("/v1/cloud/sessions/import", headers=headers, json=conflicting).status_code == 409
        deleted = http.delete(f"/v1/sessions/{data['id']}", headers=headers)
        assert deleted.status_code == 200 and deleted.json()["data"]["workspace_purged"] is True
        assert http.get(f"/v1/workspaces/{data['workspace_id']}/files/notes/imported.md", headers=headers).status_code == 400


def test_full_share_import_rejects_secrets_packages_and_bad_file_hash(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        http.post("/v1/devices", headers=headers, json={"device_id": "desktop-import-guard", "platform": "desktop", "display_name": "Desktop"})
        base_payload = {"request_id": "guard-1", "source_session_id": "local-1", "source_device_id": "desktop-import-guard"}
        assert http.post("/v1/cloud/sessions/import", headers=headers, json={**base_payload, "model_descriptor": {"api_key": "must-not-upload"}}).status_code == 400
        assert http.post("/v1/cloud/sessions/import", headers=headers, json={**base_payload, "skills": [{"id": "forbidden"}]}).status_code == 422
        bad_file = {"path": "safe.txt", "content_base64": base64.urlsafe_b64encode(b"data").decode(), "sha256": "0" * 64, "size": 4, "mime_type": "text/plain"}
        assert http.post("/v1/cloud/sessions/import", headers=headers, json={**base_payload, "files": [bad_file]}).status_code == 400
        empty_file = {"path": "C:/ambiguous.txt", "content_base64": "", "sha256": hashlib.sha256(b"").hexdigest(), "size": 0, "mime_type": "text/plain"}
        assert http.post("/v1/cloud/sessions/import", headers=headers, json={**base_payload, "files": [empty_file]}).status_code == 400


def test_session_archive_delete_and_token_rotate(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        assert http.post(f"/v1/sessions/{session['id']}/archive", headers=headers).status_code == 200
        assert http.post(f"/v1/sessions/{session['id']}/archive", headers=headers).status_code == 200
        assert http.get("/v1/sessions", headers=headers).json()["data"][0]["archived_at"]
        with http.app.state.db.connect() as cx:
            assert cx.execute("SELECT COUNT(*) FROM session_archives WHERE session_id=?", (session["id"],)).fetchone()[0] == 1
        assert http.post(f"/v1/sessions/{session['id']}/restore", headers=headers).status_code == 200
        assert http.get("/v1/sessions", headers=headers).json()["data"][0]["archived_at"] is None
        rotated = http.post("/v1/auth/rotate", headers=headers)
        assert rotated.status_code == 200
        assert http.get("/v1/sessions", headers=headers).status_code == 401
        new_headers = {"Authorization": f"Bearer {rotated.json()['data']['token']}"}
        assert http.delete(f"/v1/sessions/{session['id']}", headers=new_headers).status_code == 200


def test_archive_isolated_by_device_header(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        for device in ("archive-device-a", "archive-device-b"):
            assert http.post("/v1/devices", headers=headers, json={"device_id": device, "platform": "test", "display_name": device}).status_code == 200
        session = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native"}).json()["data"]
        device_a = {**headers, "X-Device-Id": "archive-device-a"}
        device_b = {**headers, "X-Device-Id": "archive-device-b"}
        assert http.post(f"/v1/sessions/{session['id']}/archive", headers=device_a).status_code == 200
        assert http.get("/v1/sessions", headers=device_a).json()["data"][0]["archived_at"]
        assert http.get("/v1/sessions", headers=device_b).json()["data"][0]["archived_at"] is None


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
        assert http.get("/v1/workspaces/demo/files", headers=headers).json()["data"]["files"][0]["path"] == "notes/today.md"
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
        assert http.delete("/v1/workspaces/backup/files/a.txt", headers=headers).status_code == 200
        assert http.get("/v1/workspaces/backup/files/a.txt", headers=headers).status_code == 400


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


def test_personal_scoped_token_lifecycle(tmp_path):
    with client(tmp_path) as http:
        login_token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {login_token}"}
        created = http.post("/v1/auth/tokens", headers=headers, json={"scopes": ["session.read"]}).json()["data"]
        assert created["scopes"] == ["session.read"]
        scoped_headers = {"Authorization": f"Bearer {created['token']}"}
        assert http.get("/v1/sessions", headers=scoped_headers).status_code == 200
        assert http.post("/v1/sessions", headers=scoped_headers, json={"kind": "cloud_native"}).status_code == 403
        assert http.get("/v1/devices", headers=scoped_headers).status_code == 403
        listed = http.get("/v1/auth/tokens", headers=headers).json()["data"]
        assert any(item["id"] == created["jti"] for item in listed)
        assert http.post(f"/v1/auth/tokens/{created['jti']}/revoke", headers=headers).status_code == 200
        assert http.get("/v1/sessions", headers={"Authorization": f"Bearer {created['token']}"}).status_code == 401


def test_token_rotation_preserves_pat_scope(tmp_path):
    with client(tmp_path) as http:
        login_token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {login_token}"}
        created = http.post("/v1/auth/tokens", headers=headers, json={"scopes": ["session.read"]}).json()["data"]
        rotated = http.post("/v1/auth/rotate", headers={"Authorization": f"Bearer {created['token']}"})
        assert rotated.status_code == 200
        assert rotated.json()["data"]["scopes"] == ["session.read"]
        new_headers = {"Authorization": f"Bearer {rotated.json()['data']['token']}"}
        assert http.get("/v1/sessions", headers=new_headers).status_code == 200
        assert http.post("/v1/sessions", headers=new_headers, json={"kind": "cloud_native"}).status_code == 403


def test_admin_delete_user_removes_import_children(tmp_path):
    with client(tmp_path) as http:
        admin = login(http, "admin", "admin-password-123")
        admin_headers = {"Authorization": f"Bearer {admin}"}
        user = http.post("/v1/admin/users", headers=admin_headers, json={"username": "deletable", "password": "deletable-password-123"}).json()["data"]
        user_headers = {"Authorization": f"Bearer {login(http, 'deletable', 'deletable-password-123')}"}
        http.post("/v1/devices", headers=user_headers, json={"device_id": "deletable-device", "platform": "desktop", "display_name": "Desktop"})
        imported = http.post("/v1/cloud/sessions/import", headers=user_headers, json={"request_id": "delete-import", "source_session_id": "local", "source_device_id": "deletable-device"}).json()["data"]
        http.post(f"/v1/sessions/{imported['id']}/archive", headers=user_headers)
        assert http.delete(f"/v1/admin/users/{user['id']}", headers=admin_headers).status_code == 200
        assert http.get(f"/v1/sessions/{imported['id']}/snapshot", headers=admin_headers).status_code == 404


def test_session_copy_is_independent_with_provenance(tmp_path):
    with client(tmp_path) as http:
        token = login(http, "admin", "admin-password-123")
        headers = {"Authorization": f"Bearer {token}"}
        source = http.post("/v1/sessions", headers=headers, json={"kind": "cloud_native", "title": "source"}).json()["data"]
        http.put(f"/v1/workspaces/{source['workspace_id']}/files/context.txt", headers=headers, json={"content": "copied"})
        http.post(f"/v1/sessions/{source['id']}/commands", headers=headers, json={"request_id": "copy-1", "input": "hello"})
        http.post(f"/v1/sessions/{source['id']}/commands", headers=headers, json={"request_id": "copy-2", "input": "again"})
        copied = http.post(f"/v1/sessions/{source['id']}/copy", headers=headers)
        assert copied.status_code == 200
        target = copied.json()["data"]
        assert target["id"] != source["id"] and target["copied_from"] == source["id"]
        assert http.get(f"/v1/workspaces/{target['workspace_id']}/files/context.txt", headers=headers).json()["data"]["content"] == "copied"
        assert len(http.get(f"/v1/sessions/{target['id']}/commands", headers=headers).json()["data"]) == 2
        assert http.post(f"/v1/sessions/{target['id']}/commands", headers=headers, json={"request_id": "copy-3", "input": "independent"}).status_code == 200
