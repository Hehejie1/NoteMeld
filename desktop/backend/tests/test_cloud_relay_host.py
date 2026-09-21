from __future__ import annotations

import asyncio
from dataclasses import replace
import json
import sys
import types

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


class _BlockingSocket(_Socket):
    def __init__(self):
        super().__init__([])
        self.release = asyncio.Event()

    async def __anext__(self):
        await self.release.wait()
        raise StopAsyncIteration

    async def close(self):
        self.release.set()


def test_relay_host_decrypts_first_post_handshake_command_and_returns_sequence_two_receipt():
    key = b"k" * 32
    sender = SessionCipher(key, last_sent_sequence=1, last_received_sequence=1)
    frame = sender.encrypt_frame(RemoteFrame(
        session_id="session-a", sender_device_id="controller", recipient_device_id="host",
        sequence=2, ciphertext="", frame_id="frame-a", authority_epoch=1, nonce="",
    ), b"opaque")
    authorization = LanPeerAuthorization(
        session_id="session-a", controller_device_id="controller", host_device_id="host",
        grant_id="grant-a", role="standard", scopes=frozenset({"message.send"}),
        workspace_id="workspace-a", authority_epoch=1, valid_until=9999999999,
    )
    socket = _Socket([frame.to_json()])
    host_cipher = SessionCipher(key, last_sent_sequence=1, last_received_sequence=1)
    session = RelayHostSession(
        cloud_base_url="https://cloud.example.test",
        token="device-token",
        host_device_id="host",
        session_id="session-a",
        authorize_frame=lambda _frame: authorization,
        frame_handler=lambda _frame, _authorization: {"type": "received", "frame_id": "frame-a", "queue_sequence": 1, "queue_status": "queued"},
        cipher_resolver=lambda _authorization: host_cipher,
        connector=lambda *_args, **_kwargs: socket,
    )
    asyncio.run(session.run())
    assert session.url == "wss://cloud.example.test/v1/relay/connect/session-a?device_id=host"
    assert len(socket.sent) == 1
    receipt = RemoteFrame.from_json(socket.sent[0])
    payload = sender.decrypt(receipt.sequence, receipt.nonce, receipt.ciphertext, receipt.associated_data())
    assert json.loads(payload)["status"] == "received"
    assert receipt.frame_type == "receipt"
    assert receipt.sequence == 2


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
    socket = _Socket([json.dumps({"type": "relay_ready", "next_sequence": 6}), request.to_json()])
    observed_sequences = []
    session = RelayHostSession(
        cloud_base_url="https://cloud.example.test",
        token="device-token",
        host_device_id="host",
        session_id="session-a",
        authorize_frame=lambda _frame: authorization,
        frame_handler=lambda *_args: {"type": "received"},
        cipher_resolver=lambda _authorization: (_ for _ in ()).throw(AssertionError("cipher resolver must not run for handshake")),
        handshake_handler=lambda _frame, _authorization, next_sequence: observed_sequences.append(next_sequence) or replace(response, sequence=next_sequence),
        connector=lambda *_args, **_kwargs: socket,
    )
    asyncio.run(session.run())
    assert RemoteFrame.from_json(socket.sent[0]).frame_type == "handshake"
    assert RemoteFrame.from_json(socket.sent[0]).sequence == 6
    assert observed_sequences == [6]


def test_relay_host_schedules_encrypted_agent_events_on_active_socket():
    socket = _BlockingSocket()
    session = RelayHostSession(
        cloud_base_url="https://cloud.example.test",
        token="device-token",
        host_device_id="host",
        session_id="session-a",
        authorize_frame=lambda _frame: (_ for _ in ()).throw(AssertionError("no inbound frame expected")),
        frame_handler=lambda *_args: {"type": "received"},
        cipher_resolver=lambda _authorization: SessionCipher(b"k" * 32),
        connector=lambda *_args, **_kwargs: socket,
    )
    event = SessionCipher(b"k" * 32).encrypt_frame(RemoteFrame(
        session_id="session-a", sender_device_id="host", recipient_device_id="controller",
        sequence=1, ciphertext="", frame_id="event-a", authority_epoch=1, nonce="", frame_type="event",
    ), b'{"event":{"type":"turn.succeeded"}}')

    async def scenario():
        task = asyncio.create_task(session.run())
        for _ in range(10):
            if session.send_frame_nowait(event):
                break
            await asyncio.sleep(0)
        else:
            raise AssertionError("Relay socket did not become active")
        await asyncio.sleep(0)
        await session.stop()
        await task

    asyncio.run(scenario())
    assert RemoteFrame.from_json(socket.sent[0]).frame_type == "event"


def test_relay_host_default_connector_uses_websockets_asyncio_api(monkeypatch):
    import websockets.asyncio.client

    socket = _Socket([])
    calls = []

    def legacy_connector(*_args, **_kwargs):
        raise AssertionError("deprecated websockets.client connector was used")

    def asyncio_connector(*args, **kwargs):
        calls.append((args, kwargs))
        return socket

    legacy_module = types.ModuleType("websockets.client")
    legacy_module.connect = legacy_connector
    monkeypatch.setitem(sys.modules, "websockets.client", legacy_module)
    monkeypatch.setattr(websockets.asyncio.client, "connect", asyncio_connector)
    session = RelayHostSession(
        cloud_base_url="https://cloud.example.test",
        token="device-token",
        host_device_id="host",
        session_id="session-a",
        authorize_frame=lambda _frame: (_ for _ in ()).throw(AssertionError("no inbound frame expected")),
        frame_handler=lambda *_args: {"type": "received"},
        cipher_resolver=lambda _authorization: SessionCipher(b"k" * 32),
    )

    asyncio.run(session.run())

    assert len(calls) == 1
    assert calls[0][1]["additional_headers"] == {"Authorization": "Bearer device-token"}
