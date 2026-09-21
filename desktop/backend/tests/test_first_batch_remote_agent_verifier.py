from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_remote_agent.py"
COMMIT = "a" * 40
DIGEST = "sha256:" + "b" * 64
SPEC = importlib.util.spec_from_file_location("verify_first_batch_remote_agent", SCRIPT)
assert SPEC and SPEC.loader
remote_tool = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remote_tool)


class FakeHostRelaySocket:
    def __init__(self, host_id: str, host_signing_private: bytes, *, duplicate_terminal: bool = False, grant_active=lambda: True, device_active=lambda: True, approval_decision: str | None = None):
        self.host_id = host_id
        self.host_signing_private = host_signing_private
        self.inbox = [json.dumps({"type": "relay_ready", "next_sequence": 3})]
        self.host_cipher = None
        self.host_sequence = 8
        self.duplicate_terminal = duplicate_terminal
        self.grant_active = grant_active
        self.device_active = device_active
        self.approval_decision = approval_decision

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return None

    def send(self, raw: str):
        frame = remote_tool.RemoteFrame.from_json(raw)
        if not self.grant_active() or not self.device_active():
            self.inbox.append(json.dumps({"type": "rejected", "error": "invalid_envelope"}))
            return
        if frame.frame_type == "handshake":
            controller = remote_tool.HandshakeEnvelope.from_dict(json.loads(remote_tool._unb64(frame.ciphertext)))
            host_ephemeral_private, host_ephemeral_public = remote_tool.generate_ephemeral()
            host = remote_tool.create_handshake_envelope(
                self.host_signing_private,
                frame.session_id,
                self.host_id,
                frame.sender_device_id,
                host_ephemeral_public,
            )
            key = remote_tool.derive_handshake_session_key(host_ephemeral_private, host, controller)
            self.host_cipher = remote_tool.SessionCipher(
                key,
                last_sent_sequence=self.host_sequence,
                last_received_sequence=frame.sequence,
            )
            response = remote_tool.RemoteFrame(
                session_id=frame.session_id,
                sender_device_id=self.host_id,
                recipient_device_id=frame.sender_device_id,
                sequence=self.host_sequence,
                ciphertext=remote_tool._b64(json.dumps(host.as_dict(), separators=(",", ":")).encode()),
                frame_id=frame.frame_id,
                authority_epoch=frame.authority_epoch,
                nonce=remote_tool._b64(b"h" * 12),
                frame_type="handshake",
            )
            self.inbox.extend(
                [
                    json.dumps({"type": "relay_accepted", "frame_id": frame.frame_id}),
                    response.to_json(),
                ]
            )
            return

        assert self.host_cipher is not None
        plaintext = self.host_cipher.decrypt(frame.sequence, frame.nonce, frame.ciphertext, frame.associated_data())
        command = json.loads(plaintext)
        self.inbox.append(json.dumps({"type": "relay_accepted", "frame_id": frame.frame_id}))
        self._enqueue_encrypted(
            frame,
            "receipt",
            frame.frame_id,
            {
                "type": "received",
                "status": "received",
                "frame_id": frame.frame_id,
                "request_id": command["request_id"],
                "session_id": frame.session_id,
                "queue_sequence": 4,
                "queue_status": "queued",
            },
        )
        if command["request_id"].startswith("rc-approval-"):
            assert self.approval_decision in {"deny", "expired"}
            approval_id = "approval-field-test"
            call_id = "dangerous-call"
            self._enqueue_encrypted(
                frame,
                "event",
                "event-approval-required",
                {
                    "request_id": command["request_id"],
                    "event": {"type": "approval.required", "payload": {"approval_id": approval_id, "call_id": call_id, "risk": "write"}},
                },
            )
            self._enqueue_encrypted(
                frame,
                "event",
                "event-approval-resolved",
                {
                    "request_id": command["request_id"],
                    "event": {"type": "approval.resolved", "payload": {"approval_id": approval_id, "decision": self.approval_decision}},
                },
            )
            terminal_type = "turn.failed" if self.approval_decision == "expired" else "turn.succeeded"
            terminal_payload = {"error": {"code": "approval_expired"}} if self.approval_decision == "expired" else {}
            self._enqueue_encrypted(
                frame,
                "event",
                "event-approval-terminal",
                {
                    "request_id": command["request_id"],
                    "event": {"type": terminal_type, "payload": terminal_payload},
                },
            )
            return
        challenge = command["input"].rsplit(": ", 1)[1]
        if self.duplicate_terminal:
            self._enqueue_encrypted(
                frame,
                "event",
                "event-terminal-duplicate",
                {
                    "frame_id": "event-terminal-duplicate",
                    "request_id": command["request_id"],
                    "event": {"type": "turn.succeeded", "payload": {}},
                },
            )
        self._enqueue_encrypted(
            frame,
            "event",
            "event-delta",
            {
                "frame_id": "event-delta",
                "request_id": command["request_id"],
                "event": {"type": "message.delta", "payload": {"delta": challenge}},
            },
        )
        self._enqueue_encrypted(
            frame,
            "event",
            "event-terminal",
            {
                "frame_id": "event-terminal",
                "request_id": command["request_id"],
                "event": {"type": "turn.succeeded", "payload": {}},
            },
        )

    def _enqueue_encrypted(self, request, frame_type: str, frame_id: str, payload: dict):
        sequence = self.host_cipher.last_sent_sequence + 1
        pending = remote_tool.RemoteFrame(
            session_id=request.session_id,
            sender_device_id=self.host_id,
            recipient_device_id=request.sender_device_id,
            sequence=sequence,
            ciphertext="",
            frame_id=frame_id,
            authority_epoch=request.authority_epoch,
            nonce="",
            frame_type=frame_type,
        )
        encrypted = self.host_cipher.encrypt_frame(pending, json.dumps(payload, separators=(",", ":")).encode())
        self.inbox.append(encrypted.to_json())

    def recv(self, timeout: float):
        assert timeout > 0
        if not self.inbox:
            raise TimeoutError
        return self.inbox.pop(0)


class FakeRelay:
    def __init__(self, host_id: str, host_signing_private: bytes, *, duplicate_terminal: bool = False, grant_active=lambda: True, device_active=lambda: True, approval_decision: str | None = None):
        self.host_id = host_id
        self.host_signing_private = host_signing_private
        self.duplicate_terminal = duplicate_terminal
        self.calls = []
        self.grant_active = grant_active
        self.device_active = device_active
        self.approval_decision = approval_decision

    def connect(self, url: str, **kwargs):
        self.calls.append((url, kwargs))
        if not self.device_active():
            raise RuntimeError("relay rejected revoked device")
        device_id = parse_qs(urlparse(url).query)["device_id"][0]
        assert device_id.startswith("rc-agent-controller-")
        return FakeHostRelaySocket(
            self.host_id,
            self.host_signing_private,
            duplicate_terminal=self.duplicate_terminal,
            grant_active=self.grant_active,
            device_active=self.device_active,
            approval_decision=self.approval_decision,
        )


def fake_api(host_public_key: str, *, persisted_payload: bool = False):
    calls = []
    state = {"grant_active": True}
    state["device_active"] = True
    state["grant_count"] = 0

    def request(_base_url, method, path, *, token=None, payload=None):
        calls.append((method, path, token, payload))
        if path == "/ready":
            return {"build_commit": COMMIT, "image_digest": DIGEST}
        if path == "/v1/auth/login":
            return {"token": "account-secret-token"}
        if path == "/v1/devices" and method == "GET":
            return [
                {
                    "id": "desktop-host-live",
                    "platform": "desktop",
                    "display_name": "Windows RC",
                    "public_key": host_public_key,
                   "online": True,
                    "last_seen_at": 1_789_000_000,
                   "revoked_at": None,
                }
            ]
        if path.endswith("/challenge"):
            return {"challenge": "device-proof-challenge"}
        if path.endswith("/token"):
            return {"token": "controller-secret-token"}
        if path == "/v1/grants":
            state["grant_active"] = True
            state["grant_count"] += 1
            return {"grant_id": "grant-live" if state["grant_count"] == 1 else "grant-restored"}
        if path == "/v1/grants/grant-live" and method == "DELETE":
            state["grant_active"] = False
            return {"revoked": True}
        if path.startswith("/v1/devices/rc-agent-controller-") and method == "DELETE":
            state["device_active"] = False
            state["grant_active"] = False
            return {"revoked": True}
        if path == "/v1/sessions":
            return {"id": "session-live"}
        if path.startswith("/v1/sessions/session-live/commands?"):
            return [{"id": "forbidden-cloud-command"}] if persisted_payload else []
        if path.startswith("/v1/sessions/session-live/events?"):
            return []
        return {"ok": True}

    request.state = state
    return request, calls


def test_real_host_verifier_proves_durable_remote_agent_flow_without_leaking_secrets():
    pytest.importorskip("cryptography")
    remote_tool._ensure_contracts()
    host_signing_private, host_signing_public = remote_tool.generate_identity()
    request, calls = fake_api(remote_tool._b64(host_signing_public))
    relay = FakeRelay("desktop-host-live", host_signing_private)
    challenge = "this-remote-answer-must-not-leak"

    result = remote_tool.run(
        "https://cloud.example.test/api",
        "admin",
        "password-secret",
        "desktop-host-live",
        request_fn=request,
        connect_fn=relay.connect,
        verification_challenge=challenge,
    )

    assert result["release_checks"] == {
        "c_04_real_host": "PASS",
        "x_06_remote_agent": "PASS",
        "e_01_cloud_command_event_storage": "PASS",
    }
    assert result["queue_status"] == "queued"
    assert result["queue_sequence"] == 4
    assert result["terminal_event"] == "turn.succeeded"
    assert result["event_count"] == 2
    assert result["receipt_frame_id"] == result["command_frame_id"]
    assert result["cipher"] == "AES-256-GCM"
    assert result["cloud_persisted_commands"] == 0
    assert result["cloud_persisted_events"] == 0
    assert result["build_commit"] == COMMIT
    assert result["cloud_image_digest"] == DIGEST
    serialized = json.dumps(result)
    assert challenge not in serialized
    assert "password-secret" not in serialized
    assert "account-secret-token" not in serialized
    assert "controller-secret-token" not in serialized
    assert len(relay.calls) == 1
    assert relay.calls[0][0].startswith("wss://cloud.example.test/api/v1/relay/connect/session-live")
    assert any(method == "DELETE" and path == "/v1/sessions/session-live" for method, path, *_ in calls)
    assert any(method == "DELETE" and path == "/v1/grants/grant-live" for method, path, *_ in calls)
    assert any(method == "DELETE" and path.startswith("/v1/devices/rc-agent-controller-") for method, path, *_ in calls)
    assert any(method == "GET" and path.startswith("/v1/sessions/session-live/commands?") for method, path, *_ in calls)
    assert any(method == "GET" and path.startswith("/v1/sessions/session-live/events?") for method, path, *_ in calls)


def test_real_host_verifier_fails_closed_for_non_desktop_or_offline_host():
    public_key = remote_tool._b64(b"p" * 32)
    with pytest.raises(remote_tool.VerificationError, match="not a desktop"):
        remote_tool._select_host(
            [{"id": "host", "platform": "android", "online": True, "revoked_at": None, "public_key": public_key}],
            "host",
        )
    with pytest.raises(remote_tool.VerificationError, match="not online"):
        remote_tool._select_host(
            [{"id": "host", "platform": "desktop", "online": False, "revoked_at": None, "public_key": public_key}],
            "host",
        )


def test_real_host_verifier_rejects_duplicate_terminal_events():
    pytest.importorskip("cryptography")
    remote_tool._ensure_contracts()
    host_signing_private, host_signing_public = remote_tool.generate_identity()
    request, _calls = fake_api(remote_tool._b64(host_signing_public))
    relay = FakeRelay("desktop-host-live", host_signing_private, duplicate_terminal=True)

    with pytest.raises(remote_tool.VerificationError, match="multiple terminal"):
        remote_tool.run(
            "https://cloud.example.test/api",
            "admin",
            "password-secret",
            "desktop-host-live",
            request_fn=request,
            connect_fn=relay.connect,
            verification_challenge="duplicate-terminal-challenge",
        )


def test_real_host_verifier_rejects_revoked_grant_on_existing_and_new_connections():
    pytest.importorskip("cryptography")
    remote_tool._ensure_contracts()
    host_signing_private, host_signing_public = remote_tool.generate_identity()
    request, calls = fake_api(remote_tool._b64(host_signing_public))
    relay = FakeRelay(
        "desktop-host-live",
        host_signing_private,
        grant_active=lambda: request.state["grant_active"],
        device_active=lambda: request.state["device_active"],
    )

    result = remote_tool.run(
        "https://cloud.example.test/api",
        "admin",
        "password-secret",
        "desktop-host-live",
        request_fn=request,
        connect_fn=relay.connect,
        verification_challenge="revocation-challenge",
        verify_revocation=True,
    )

    assert result["revocation"] == {
        "grant_revoked": True,
        "grant_existing_connection": "rejected",
        "grant_new_connection": "rejected",
        "device_revoked": True,
        "device_existing_connection": "rejected",
        "device_new_connection": "denied",
        "host_delivery": False,
    }
    assert len(relay.calls) == 4
    assert any(method == "DELETE" and path == "/v1/grants/grant-live" for method, path, *_ in calls)
    assert "e_02" not in result["release_checks"]


@pytest.mark.parametrize(
    ("decision", "terminal"),
    [("deny", "turn.succeeded"), ("expired", "turn.failed")],
)
def test_real_host_verifier_proves_approval_denial_and_expiry_without_dispatch(decision, terminal):
    pytest.importorskip("cryptography")
    remote_tool._ensure_contracts()
    host_signing_private, host_signing_public = remote_tool.generate_identity()
    request, _calls = fake_api(remote_tool._b64(host_signing_public))
    relay = FakeRelay("desktop-host-live", host_signing_private, approval_decision=decision)
    prompt = "Use note:create for the E02 field gate"

    result = remote_tool.run(
        "https://cloud.example.test/api",
        "admin",
        "password-secret",
        "desktop-host-live",
        request_fn=request,
        connect_fn=relay.connect,
        verification_challenge="approval-baseline-challenge",
        approval_scenario=decision,
        dangerous_prompt=prompt,
    )

    assert result["approval"]["decision"] == decision
    assert result["approval"]["terminal_event"] == terminal
    assert result["approval"]["tool_dispatched"] is False
    assert result["approval"]["approval_id_sha256"] == remote_tool.hashlib.sha256(b"approval-field-test").hexdigest()
    assert prompt not in json.dumps(result)
    assert "e_02" not in result["release_checks"]


def test_real_host_verifier_rejects_device_remote_payload_in_cloud_storage():
    pytest.importorskip("cryptography")
    remote_tool._ensure_contracts()
    host_signing_private, host_signing_public = remote_tool.generate_identity()
    request, calls = fake_api(remote_tool._b64(host_signing_public), persisted_payload=True)
    relay = FakeRelay("desktop-host-live", host_signing_private)

    with pytest.raises(remote_tool.VerificationError, match="persisted in Cloud"):
        remote_tool.run(
            "https://cloud.example.test/api",
            "admin",
            "password-secret",
            "desktop-host-live",
            request_fn=request,
            connect_fn=relay.connect,
            verification_challenge="cloud-persistence-challenge",
        )
    assert any(method == "DELETE" and path == "/v1/sessions/session-live" for method, path, *_ in calls)


def test_real_host_verifier_passes_in_memory_secrets_to_optional_production_audit(tmp_path):
    pytest.importorskip("cryptography")
    remote_tool._ensure_contracts()
    host_signing_private, host_signing_public = remote_tool.generate_identity()
    request, _calls = fake_api(remote_tool._b64(host_signing_public))
    relay = FakeRelay("desktop-host-live", host_signing_private)
    captured = {}

    def audit(database, logs, redis_url, audit_needles, *, session_id):
        captured.update({"database": database, "logs": logs, "redis_url": redis_url, "needles": audit_needles, "session_id": session_id})
        return {
            "release_checks": {"e_01_cloud_storage_logs_redis": "PASS"},
            "needle_sha256": {key: "a" * 64 for key in audit_needles},
        }

    result = remote_tool.run(
        "https://cloud.example.test/api",
        "admin",
        "password-secret",
        "desktop-host-live",
        request_fn=request,
        connect_fn=relay.connect,
        verification_challenge="integrated-audit-challenge",
        security_audit_database=tmp_path / "cloud.db",
        security_audit_log_paths=[tmp_path / "logs"],
        security_audit_redis_url="rediss://redis.example.test/0",
        security_audit_provider_key="provider-secret-value",
        security_audit_fn=audit,
    )

    assert result["release_checks"]["e_01_cloud_storage_logs_redis"] == "PASS"
    assert captured["session_id"] == "session-live"
    assert captured["needles"]["challenge"] == "integrated-audit-challenge"
    assert captured["needles"]["account_token"] == "account-secret-token"
    assert captured["needles"]["device_token"] == "controller-secret-token"
    assert captured["needles"]["provider_key"] == "provider-secret-value"
    assert len(remote_tool._unb64(captured["needles"]["session_key"])) == 32
    serialized = json.dumps(result)
    assert "integrated-audit-challenge" not in serialized
    assert "provider-secret-value" not in serialized


def test_real_host_verifier_rejects_partial_security_audit_configuration(tmp_path):
    with pytest.raises(remote_tool.VerificationError, match="requires database"):
        remote_tool.run(
            "https://cloud.example.test/api",
            "admin",
            "password-secret",
            "desktop-host-live",
            security_audit_database=tmp_path / "cloud.db",
        )


def test_real_host_verifier_rejects_non_https_before_loading_runtime_dependencies():
    with pytest.raises(remote_tool.VerificationError, match="HTTPS"):
        remote_tool.run("http://127.0.0.1:8583", "admin", "password", "host")
