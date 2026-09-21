from __future__ import annotations

import base64
import asyncio
import json

from app.cloud_sync.e2ee import (
    HandshakeEnvelope,
    SessionCipher,
    create_handshake_envelope,
    derive_handshake_session_key,
    generate_ephemeral,
    generate_identity,
)
from app.cloud_sync.e2ee_handshake import accept_handshake
from app.cloud_sync.lan_auth import LanPeerAuthorization


class _Socket:
    def __init__(self, incoming: str):
        self.incoming = incoming
        self.sent = []

    async def receive_text(self):
        return self.incoming

    async def send_json(self, value):
        self.sent.append(value)


def test_host_accepts_signed_controller_offer_and_derives_same_key():
    controller_private, controller_public = generate_identity()
    host_private, host_public = generate_identity()
    controller_ephemeral, controller_ephemeral_public = generate_ephemeral()
    controller_offer = create_handshake_envelope(
        controller_private,
        "session-a",
        "controller",
        "host",
        controller_ephemeral_public,
    )
    authorization = LanPeerAuthorization(
        session_id="session-a",
        controller_device_id="controller",
        host_device_id="host",
        grant_id="grant-a",
        role="standard",
        scopes=frozenset({"message.send"}),
        workspace_id="workspace-a",
        authority_epoch=1,
        valid_until=9999999999,
        controller_public_key=base64.urlsafe_b64encode(controller_public).decode().rstrip("="),
    )
    socket = _Socket(json.dumps(controller_offer.as_dict()))
    host_cipher = asyncio.run(accept_handshake(
        socket,
        authorization,
        signing_private=host_private,
        signing_public=host_public,
    ))
    host_offer = HandshakeEnvelope.from_dict(socket.sent[0])
    controller_key = derive_handshake_session_key(
        controller_ephemeral,
        controller_offer,
        host_offer,
    )
    assert isinstance(host_cipher, SessionCipher)
    assert host_cipher.key == controller_key
