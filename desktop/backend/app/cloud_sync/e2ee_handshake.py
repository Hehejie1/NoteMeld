"""Interactive Host side of the signed X25519 session handshake."""
from __future__ import annotations

import json
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ed25519

from .e2ee import (
    HandshakeEnvelope,
    SessionCipher,
    create_handshake_envelope,
    derive_handshake_session_key,
    generate_ephemeral,
    verify_handshake_envelope,
    _unb64,
)
from .lan_auth import LanPeerAuthorization


async def accept_handshake(
    websocket: Any,
    authorization: LanPeerAuthorization,
    *,
    signing_private: bytes,
    signing_public: bytes,
) -> SessionCipher:
    """Complete the Host half of E2EE after the LAN proof succeeds."""
    if not authorization.controller_public_key:
        raise ValueError("controller public key is required for E2EE handshake")
    private_key = ed25519.Ed25519PrivateKey.from_private_bytes(signing_private)
    derived_public = private_key.public_key().public_bytes(
        serialization.Encoding.Raw,
        serialization.PublicFormat.Raw,
    )
    if derived_public != signing_public:
        raise ValueError("host signing key pair does not match")
    peer = HandshakeEnvelope.from_dict(json.loads(await websocket.receive_text()))
    if (
        peer.session_id != authorization.session_id
        or peer.sender_device_id != authorization.controller_device_id
        or peer.recipient_device_id != authorization.host_device_id
    ):
        raise ValueError("handshake endpoint mismatch")
    verify_handshake_envelope(
        peer,
        _unb64(authorization.controller_public_key, expected_length=32),
    )
    local_private, local_public = generate_ephemeral()
    local = create_handshake_envelope(
        signing_private,
        authorization.session_id,
        authorization.host_device_id,
        authorization.controller_device_id,
        local_public,
    )
    await websocket.send_json(local.as_dict())
    return SessionCipher(derive_handshake_session_key(local_private, local, peer))
