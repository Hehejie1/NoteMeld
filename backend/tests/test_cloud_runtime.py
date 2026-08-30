from __future__ import annotations

import base64
import json
import time

from fastapi import FastAPI

from app.cloud_sync import CloudSyncHostRuntime, RemoteFrame, SessionCipher
from app.cloud_sync.lan_auth import LanPeerAuthorization


class _CloudStub:
    device_id = "host-device"

    def authorize_lan_peer(self, session_id, controller_device_id, host_device_id):
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
