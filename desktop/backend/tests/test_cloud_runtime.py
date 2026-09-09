from __future__ import annotations

import base64
import json
import time

from fastapi import FastAPI
import pytest

from app.cloud_sync import CloudSyncHostRuntime, RemoteFrame, SessionCipher, attach_cloud_sync_runtime
from app.cloud_sync.e2ee import create_handshake_envelope, derive_handshake_session_key, generate_ephemeral, HandshakeEnvelope
from app.cloud_sync.lan_auth import LanPeerAuthorization
from app.cloud_sync.protocol import SessionCommand


class _CloudStub:
    device_id = "host-device"
    allow = True

    def heartbeat(self, device_id, lan_endpoints=None):
        return {"device_id": device_id, "lan_endpoints": lan_endpoints or []}

    def authorize_lan_peer(self, session_id, controller_device_id, host_device_id):
        if not self.allow:
            raise RuntimeError("revoked")
        return {
            "session_id": session_id,
            "controller_device_id": controller_device_id,
            "host_device_id": host_device_id,
            "controller_public_key": base64.urlsafe_b64encode(b"p" * 32).decode().rstrip("="),
            "grant_id": "grant-a",
            "role": "standard",
            "scopes": ["message.send"],
            "workspace_id": "project-a",
            "authority_epoch": 1,
            "valid_until": int(time.time()) + 60,
            "ttl_seconds": 60,
        }

    def close(self):
        pass


def test_host_runtime_wires_cloud_assertion_cipher_and_durable_mailbox(tmp_path):
    runtime = CloudSyncHostRuntime(
        cloud_client=_CloudStub(),  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: SessionCipher(b"k" * 32),
    )
    assertion = runtime._authorize_lan_peer(
        "session-a", "controller-device", "host-device"
    )
    authorization = LanPeerAuthorization(
        session_id="session-a",
        controller_device_id="controller-device",
        host_device_id="host-device",
        grant_id="grant-a",
        role="standard",
        scopes=frozenset({"message.send"}),
        workspace_id="project-a",
        authority_epoch=1,
        valid_until=assertion["valid_until"],
    )
    sender = SessionCipher(b"k" * 32)
    metadata = RemoteFrame(
        session_id="session-a",
        sender_device_id="controller-device",
        recipient_device_id="host-device",
        sequence=1,
        ciphertext="",
        frame_id="frame-a",
        authority_epoch=1,
        nonce="",
    )
    frame = sender.encrypt_frame(
        metadata,
        json.dumps({"request_id": "request-a", "input": "hello"}).encode(),
    )

    receipt = runtime._handle_frame(frame, authorization)
    assert receipt["type"] == "received"
    assert runtime.pending("session-a")[0].request_id == "request-a"
    assert runtime.status("session-a")["pending_count"] == 1
    assert runtime.pending_sessions() == [{"session_id": "session-a", "pending_count": 1, "attention_count": 0}]


def test_host_runtime_completes_relay_handshake_and_installs_cipher(tmp_path):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519

    controller_private = ed25519.Ed25519PrivateKey.generate()
    controller_private_raw = controller_private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    controller_public_raw = controller_private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    host_private = ed25519.Ed25519PrivateKey.generate()
    host_private_raw = host_private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption())
    host_public_raw = host_private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    runtime = CloudSyncHostRuntime(
        cloud_client=_CloudStub(),  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: (_ for _ in ()).throw(AssertionError("relay handshake must install a cipher")),
        host_signing_private=host_private_raw,
        host_signing_public=host_public_raw,
    )
    authorization = LanPeerAuthorization(
        session_id="session-a", controller_device_id="controller-device", host_device_id="host-device",
        grant_id="grant-a", role="standard", scopes=frozenset({"message.send"}), workspace_id="project-a",
        authority_epoch=1, valid_until=9999999999,
        controller_public_key=base64.urlsafe_b64encode(controller_public_raw).decode().rstrip("="),
    )
    controller_ephemeral_private, controller_ephemeral_public = generate_ephemeral()
    peer = create_handshake_envelope(controller_private_raw, "session-a", "controller-device", "host-device", controller_ephemeral_public)
    frame = RemoteFrame(
        session_id="session-a", sender_device_id="controller-device", recipient_device_id="host-device",
        sequence=1, ciphertext=base64.urlsafe_b64encode(json.dumps(peer.as_dict(), separators=(",", ":")).encode()).decode().rstrip("="),
        frame_id="handshake-a", authority_epoch=1, nonce=base64.urlsafe_b64encode(b"n" * 12).decode().rstrip("="), frame_type="handshake",
    )
    response = runtime._handle_relay_handshake(frame, authorization)
    host_peer = HandshakeEnvelope.from_dict(json.loads(base64.urlsafe_b64decode(response.ciphertext + "=" * ((4 - len(response.ciphertext) % 4) % 4)).decode()))
    expected = SessionCipher(derive_handshake_session_key(controller_ephemeral_private, peer, host_peer))
    installed = runtime._cipher_for(authorization)
    assert installed.key == expected.key


def test_host_runtime_uses_installed_session_cipher_and_can_revoke_it(tmp_path):
    runtime = CloudSyncHostRuntime(
        cloud_client=_CloudStub(),  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: (_ for _ in ()).throw(AssertionError("fallback resolver must not run")),
    )
    assertion = runtime._authorize_lan_peer("session-a", "controller-device", "host-device")
    authorization = LanPeerAuthorization(
        session_id="session-a", controller_device_id="controller-device", host_device_id="host-device",
        grant_id="grant-a", role="standard", scopes=frozenset({"message.send"}), workspace_id="project-a",
        authority_epoch=1, valid_until=assertion["valid_until"],
    )
    runtime.install_session_cipher("session-a", "controller-device", SessionCipher(b"k" * 32))
    sender = SessionCipher(b"k" * 32)
    frame = sender.encrypt_frame(RemoteFrame(
        session_id="session-a", sender_device_id="controller-device", recipient_device_id="host-device",
        sequence=1, ciphertext="", frame_id="frame-installed", authority_epoch=1, nonce="",
    ), json.dumps({"request_id": "request-installed", "input": "hello"}).encode())
    assert runtime._handle_frame(frame, authorization)["type"] == "received"
    assert runtime.remove_session_cipher("session-a", "controller-device") is True
    assert runtime.remove_session_cipher("session-a", "controller-device") is False


def test_host_runtime_projects_agent_event_as_encrypted_event_frame(tmp_path):
    runtime = CloudSyncHostRuntime(
        cloud_client=_CloudStub(),  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: SessionCipher(b"k" * 32),
    )
    assertion = runtime._authorize_lan_peer("session-a", "controller-device", "host-device")
    authorization = LanPeerAuthorization(
        session_id="session-a", controller_device_id="controller-device", host_device_id="host-device",
        grant_id="grant-a", role="standard", scopes=frozenset({"message.send"}),
        workspace_id="project-a", authority_epoch=1, valid_until=assertion["valid_until"],
    )
    cipher = SessionCipher(b"k" * 32)
    runtime.install_session_cipher("session-a", "controller-device", cipher)
    incoming = SessionCipher(b"k" * 32).encrypt_frame(RemoteFrame(
        session_id="session-a", sender_device_id="controller-device", recipient_device_id="host-device",
        sequence=1, ciphertext="", frame_id="frame-a", authority_epoch=1, nonce="",
    ), json.dumps({"request_id": "request-a", "input": "hello"}).encode())
    runtime._handle_frame(incoming, authorization)
    sent = []
    runtime.service.send_event_nowait = lambda *args: sent.append(args) or True  # type: ignore[method-assign]
    runtime._emit_remote_event(
        SessionCommand.create("session-a", "request-a", "hello", 1, 1),
        {"type": "message.delta", "payload": {"delta": "hi"}},
    )
    assert len(sent) == 1
    event_frame = sent[0][2]
    payload = SessionCipher(b"k" * 32).decrypt(event_frame.sequence, event_frame.nonce, event_frame.ciphertext, event_frame.associated_data())
    assert json.loads(payload)["request_id"] == "request-a"
    assert event_frame.frame_type == "event"


def test_host_runtime_install_is_explicit(tmp_path):
    runtime = CloudSyncHostRuntime(
        cloud_client=_CloudStub(),  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: SessionCipher(b"k" * 32),
    )
    app = FastAPI()
    runtime.install(app)
    assert app.state.lan_direct_service is runtime.service


def test_host_runtime_can_be_attached_once_for_backend_lifecycle(tmp_path):
    runtime = CloudSyncHostRuntime(
        cloud_client=_CloudStub(),  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: SessionCipher(b"k" * 32),
    )
    app = FastAPI()
    attach_cloud_sync_runtime(app, runtime)
    assert app.state.cloud_sync_runtime is runtime
    with pytest.raises(RuntimeError, match="already attached"):
        attach_cloud_sync_runtime(app, CloudSyncHostRuntime(
            cloud_client=_CloudStub(),  # type: ignore[arg-type]
            host_device_id="host-device",
            mailbox_path=tmp_path / "other.sqlite",
            cipher_resolver=lambda _: SessionCipher(b"k" * 32),
        ))


def test_host_runtime_close_is_idempotent(tmp_path):
    class Cloud(_CloudStub):
        close_count = 0

        def close(self):
            self.close_count += 1

    cloud = Cloud()
    runtime = CloudSyncHostRuntime(
        cloud_client=cloud,  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: SessionCipher(b"k" * 32),
    )
    runtime.close()
    runtime.close()
    assert cloud.close_count == 1


def test_host_runtime_exposes_explicit_presence_heartbeat(tmp_path):
    runtime = CloudSyncHostRuntime(
        cloud_client=_CloudStub(),  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: SessionCipher(b"k" * 32),
    )
    assert runtime.heartbeat(["192.168.1.10:8483"]) == {
        "device_id": "host-device",
        "lan_endpoints": ["192.168.1.10:8483"],
    }


def test_host_runtime_refreshes_cached_grant_and_fails_closed_on_revocation(tmp_path):
    cloud = _CloudStub()
    runtime = CloudSyncHostRuntime(
        cloud_client=cloud,  # type: ignore[arg-type]
        host_device_id="host-device",
        mailbox_path=tmp_path / "mailbox.sqlite",
        cipher_resolver=lambda _: SessionCipher(b"k" * 32),
        authorization_refresh_seconds=0.01,
    )
    assertion = runtime._authorize_lan_peer("session-a", "controller-device", "host-device")
    authorization = LanPeerAuthorization(
        session_id="session-a", controller_device_id="controller-device", host_device_id="host-device",
        grant_id="grant-a", role="standard", scopes=frozenset({"message.send"}),
        workspace_id="project-a", authority_epoch=1, valid_until=assertion["valid_until"],
    )
    sender = SessionCipher(b"k" * 32)
    frame = sender.encrypt_frame(RemoteFrame(
        session_id="session-a", sender_device_id="controller-device", recipient_device_id="host-device",
        sequence=1, ciphertext="", frame_id="frame-revoked", authority_epoch=1, nonce="",
    ), json.dumps({"request_id": "request-revoked", "input": "hello"}).encode())
    cloud.allow = False
    time.sleep(0.02)
    with pytest.raises(Exception, match="permission"):
        runtime._handle_frame(frame, authorization)
