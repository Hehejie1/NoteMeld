from __future__ import annotations

import base64
import json
import time

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.cloud_sync.lan_auth import LanPeerAuthenticator, LanPeerAuthorization
from app.cloud_sync.e2ee import SessionCipher
from app.cloud_sync.lan_transport import (
    EncryptedRemoteHostHandler,
    LAN_PROTOCOL_VERSION,
    LanDirectFrameError,
    LanDirectService,
    install_lan_direct_service,
    router,
)
from app.cloud_sync.protocol import RemoteFrame
from app.cloud_sync.queue import DurableSessionMailbox
from app.cloud_sync.remote_host import RemoteHostAuthority


def test_lan_websocket_authenticates_device_and_delivers_opaque_frame():
    private_key = Ed25519PrivateKey.generate()
    public_key = base64.urlsafe_b64encode(
        private_key.public_key().public_bytes_raw()
    ).decode().rstrip("=")
    delivered = []

    def authorize(session_id, controller_device_id, host_device_id):
        return {
            "session_id": session_id,
            "controller_device_id": controller_device_id,
            "host_device_id": host_device_id,
            "controller_public_key": public_key,
            "grant_id": "grant-a",
            "role": "standard",
            "scopes": ["message.send"],
            "workspace_id": "project-a",
            "authority_epoch": 2,
            "valid_until": int(time.time()) + 60,
            "ttl_seconds": 60,
        }

    def handle_frame(frame, authorization):
        delivered.append((frame, authorization))
        return {"type": "received", "frame_id": frame.frame_id}

    authenticator = LanPeerAuthenticator("host-device", authorize)
    service = LanDirectService(
        authenticator,
        handle_frame,
        peer_address=lambda _: "127.0.0.1",
    )
    app = FastAPI()
    install_lan_direct_service(app, service)
    app.include_router(router)

    with TestClient(app) as http:
        with http.websocket_connect(
            "/v1/lan/connect/session-a", subprotocols=[LAN_PROTOCOL_VERSION]
        ) as socket:
            socket.send_json(
                {
                    "type": "hello",
                    "protocol_version": LAN_PROTOCOL_VERSION,
                    "controller_device_id": "controller-device",
                }
            )
            challenge = socket.receive_json()
            proof_message = authenticator.proof_message(
                "session-a",
                "controller-device",
                "host-device",
                challenge["challenge_id"],
                challenge["challenge"],
            )
            signature = base64.urlsafe_b64encode(
                private_key.sign(proof_message)
            ).decode().rstrip("=")
            socket.send_json(
                {
                    "type": "proof",
                    "challenge_id": challenge["challenge_id"],
                    "challenge": challenge["challenge"],
                    "signature": signature,
                }
            )
            authorized = socket.receive_json()
            assert authorized["type"] == "authorized"
            frame = RemoteFrame(
                session_id="session-a",
                sender_device_id="controller-device",
                recipient_device_id="host-device",
                sequence=1,
                ciphertext="opaque-ciphertext",
                frame_id="frame-a",
                authority_epoch=2,
                nonce=base64.urlsafe_b64encode(b"n" * 12).decode().rstrip("="),
            )
            socket.send_text(frame.to_json())
            assert socket.receive_json() == {"type": "received", "frame_id": "frame-a"}

    assert len(delivered) == 1
    assert delivered[0][0].ciphertext == "opaque-ciphertext"


def test_lan_websocket_rejects_frame_outside_authorized_envelope():
    private_key = Ed25519PrivateKey.generate()
    public_key = base64.urlsafe_b64encode(
        private_key.public_key().public_bytes_raw()
    ).decode().rstrip("=")

    def authorize(session_id, controller_device_id, host_device_id):
        return {
            "session_id": session_id,
            "controller_device_id": controller_device_id,
            "host_device_id": host_device_id,
            "controller_public_key": public_key,
            "grant_id": "grant-a",
            "role": "standard",
            "scopes": ["message.send"],
            "workspace_id": "project-a",
            "authority_epoch": 2,
            "valid_until": int(time.time()) + 60,
            "ttl_seconds": 60,
        }

    authenticator = LanPeerAuthenticator("host-device", authorize)
    service = LanDirectService(
        authenticator,
        lambda *_: {"type": "received"},
        peer_address=lambda _: "127.0.0.1",
    )
    app = FastAPI()
    install_lan_direct_service(app, service)
    app.include_router(router)

    with TestClient(app) as http:
        with http.websocket_connect("/v1/lan/connect/session-a") as socket:
            socket.send_text(
                json.dumps(
                    {
                        "type": "hello",
                        "protocol_version": LAN_PROTOCOL_VERSION,
                        "controller_device_id": "controller-device",
                    }
                )
            )
            challenge = socket.receive_json()
            message = authenticator.proof_message(
                "session-a",
                "controller-device",
                "host-device",
                challenge["challenge_id"],
                challenge["challenge"],
            )
            socket.send_json(
                {
                    "type": "proof",
                    "challenge_id": challenge["challenge_id"],
                    "challenge": challenge["challenge"],
                    "signature": base64.urlsafe_b64encode(
                        private_key.sign(message)
                    ).decode().rstrip("="),
                }
            )
            assert socket.receive_json()["type"] == "authorized"
            frame = RemoteFrame(
                session_id="session-a",
                sender_device_id="another-controller",
                recipient_device_id="host-device",
                sequence=1,
                ciphertext="opaque",
                frame_id="bad-frame",
                authority_epoch=2,
                nonce=base64.urlsafe_b64encode(b"n" * 12).decode().rstrip("="),
            )
            socket.send_text(frame.to_json())
            assert socket.receive_json() == {
                "type": "rejected",
                "error": "invalid_envelope",
            }
            valid_frame = RemoteFrame(
                **{**frame.__dict__, "sender_device_id": "controller-device"}
            )
            socket.send_text(valid_frame.to_json())
            assert socket.receive_json() == {
                "type": "rejected",
                "error": "invalid_host_response",
            }


def test_lan_encrypted_host_handler_decrypts_before_durable_receipt(tmp_path):
    key = b"k" * 32
    sender = SessionCipher(key)
    receiver = SessionCipher(key)
    mailbox = DurableSessionMailbox(tmp_path / "lan-mailbox.sqlite")
    authority = RemoteHostAuthority(
        device_id="host-device",
        mailbox=mailbox,
        authorize=lambda session_id, controller_id, epoch: (
            session_id,
            controller_id,
            epoch,
        )
        == ("session-a", "controller-device", 2),
    )
    authorization = LanPeerAuthorization(
        session_id="session-a",
        controller_device_id="controller-device",
        host_device_id="host-device",
        grant_id="grant-a",
        role="standard",
        scopes=frozenset({"message.send"}),
        workspace_id="project-a",
        authority_epoch=2,
        valid_until=int(time.time()) + 60,
    )
    handler = EncryptedRemoteHostHandler(authority, lambda _: receiver)
    metadata = RemoteFrame(
        session_id="session-a",
        sender_device_id="controller-device",
        recipient_device_id="host-device",
        sequence=1,
        ciphertext="",
        frame_id="encrypted-frame",
        authority_epoch=2,
        nonce="",
    )
    plaintext = json.dumps(
        {"request_id": "request-a", "input": "run encrypted command"}
    ).encode()
    frame = sender.encrypt_frame(metadata, plaintext)

    receipt = handler(frame, authorization)
    assert receipt == {
        "type": "received",
        "frame_id": "encrypted-frame",
        "queue_sequence": 1,
        "queue_status": "queued",
    }
    assert mailbox.pending("session-a")[0].input_text == "run encrypted command"

    tampered = RemoteFrame(
        **{
            **frame.__dict__,
            "sequence": 2,
            "frame_id": "tampered-frame",
            "ciphertext": frame.ciphertext[:-1] + ("A" if frame.ciphertext[-1] != "A" else "B"),
        }
    )
    with pytest.raises(LanDirectFrameError, match="invalid_ciphertext"):
        handler(tampered, authorization)
    assert len(mailbox.pending("session-a")) == 1
