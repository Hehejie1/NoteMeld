from __future__ import annotations

import asyncio
import json

from app.cloud_sync.e2ee import SessionCipher
from app.cloud_sync.lan_auth import LanPeerAuthorization
from app.cloud_sync.protocol import RemoteFrame
from app.cloud_sync.relay_host import RelayHostSession


class _Socket:
    def __init__(self, messages):
        self.messages = messages
        self.sent = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def __aiter__(self):
        return self

    async def __anext__(self):
        if not self.messages:
            raise StopAsyncIteration
        return self.messages.pop(0)

    async def send(self, value):
        self.sent.append(value)

    async def close(self):
        return None


def test_relay_host_decrypts_command_and_returns_encrypted_receipt():
    key = b"k" * 32
    sender = SessionCipher(key)
    frame = sender.encrypt_frame(RemoteFrame(
        session_id="session-a", sender_device_id="controller", recipient_device_id="host",
        sequence=1, ciphertext="", frame_id="frame-a", authority_epoch=1, nonce="",
    ), b"opaque")
    authorization = LanPeerAuthorization(
        session_id="session-a", controller_device_id="controller", host_device_id="host",
        grant_id="grant-a", role="standard", scopes=frozenset({"message.send"}),
        workspace_id="workspace-a", authority_epoch=1, valid_until=9999999999,
    )
    socket = _Socket([frame.to_json()])
    session = RelayHostSession(
        cloud_base_url="https://cloud.example.test",
        token="device-token",
        host_device_id="host",
        session_id="session-a",
        authorize_frame=lambda _frame: authorization,
        frame_handler=lambda _frame, _authorization: {"type": "received", "frame_id": "frame-a", "queue_sequence": 1, "queue_status": "queued"},
        cipher_resolver=lambda _authorization: SessionCipher(key),
        connector=lambda *_args, **_kwargs: socket,
    )
    asyncio.run(session.run())
    assert session.url == "wss://cloud.example.test/v1/relay/connect/session-a?device_id=host"
    assert len(socket.sent) == 1
    receipt = RemoteFrame.from_json(socket.sent[0])
    payload = SessionCipher(key).decrypt(receipt.sequence, receipt.nonce, receipt.ciphertext, receipt.associated_data())
    assert json.loads(payload)["status"] == "received"
    assert receipt.frame_type == "receipt"


def test_relay_host_routes_handshake_before_cipher_resolution():
    authorization = LanPeerAuthorization(
        session_id="session-a", controller_device_id="controller", host_device_id="host",
        grant_id="grant-a", role="standard", scopes=frozenset({"message.send"}),
        workspace_id="workspace-a", authority_epoch=1, valid_until=9999999999,
    )
    request = RemoteFrame(
        session_id="session-a", sender_device_id="controller", recipient_device_id="host",
        sequence=1, ciphertext="cGF5bG9hZA", frame_id="handshake-a", authority_epoch=1,
        nonce="bm" * 8, frame_type="handshake",
    )
    response = RemoteFrame(
        session_id="session-a", sender_device_id="host", recipient_device_id="controller",
        sequence=1, ciphertext="cmVzcG9uc2U", frame_id="handshake-a", authority_epoch=1,
        nonce="bm" * 8, frame_type="handshake",
    )
    socket = _Socket([request.to_json()])
    session = RelayHostSession(
        cloud_base_url="https://cloud.example.test",
        token="device-token",
        host_device_id="host",
        session_id="session-a",
        authorize_frame=lambda _frame: authorization,
        frame_handler=lambda *_args: {"type": "received"},
        cipher_resolver=lambda _authorization: (_ for _ in ()).throw(AssertionError("cipher resolver must not run for handshake")),
        handshake_handler=lambda _frame, _authorization: response,
        connector=lambda *_args, **_kwargs: socket,
    )
    asyncio.run(session.run())
    assert RemoteFrame.from_json(socket.sent[0]).frame_type == "handshake"
