"""Application-layer E2EE primitives for device-remote sessions.

The relay never imports this module or receives a session key. Platform
adapters use it after loading device private keys from platform secure storage.
"""
from __future__ import annotations

import base64
import binascii
import os
import re
from dataclasses import dataclass, replace
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .protocol import RemoteFrame


def generate_identity() -> tuple[bytes, bytes]:
    signing = ed25519.Ed25519PrivateKey.generate()
    return (
        signing.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        ),
        signing.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ),
    )


def generate_ephemeral() -> tuple[bytes, bytes]:
    private = x25519.X25519PrivateKey.generate()
    return (
        private.private_bytes(
            serialization.Encoding.Raw,
            serialization.PrivateFormat.Raw,
            serialization.NoEncryption(),
        ),
        private.public_key().public_bytes(
            serialization.Encoding.Raw,
            serialization.PublicFormat.Raw,
        ),
    )


def sign_handshake(
    signing_private: bytes,
    session_id: str,
    sender: str,
    recipient: str,
    ephemeral_public: bytes,
) -> str:
    key = ed25519.Ed25519PrivateKey.from_private_bytes(signing_private)
    return _b64(key.sign(_handshake_message(session_id, sender, recipient, ephemeral_public)))


def verify_handshake(
    signing_public: bytes,
    signature: str,
    session_id: str,
    sender: str,
    recipient: str,
    ephemeral_public: bytes,
) -> None:
    key = ed25519.Ed25519PublicKey.from_public_bytes(signing_public)
    key.verify(
        _unb64(signature, expected_length=64),
        _handshake_message(session_id, sender, recipient, ephemeral_public),
    )


@dataclass(frozen=True)
class HandshakeEnvelope:
    """Signed ephemeral-key offer exchanged directly by two devices."""

    session_id: str
    sender_device_id: str
    recipient_device_id: str
    ephemeral_public: str
    signature: str

    def __post_init__(self) -> None:
        _handshake_message(
            self.session_id,
            self.sender_device_id,
            self.recipient_device_id,
            _unb64(self.ephemeral_public, expected_length=32),
        )
        _unb64(self.signature, expected_length=64)

    def signing_bytes(self) -> bytes:
        return _handshake_message(
            self.session_id,
            self.sender_device_id,
            self.recipient_device_id,
            _unb64(self.ephemeral_public, expected_length=32),
        )

    def as_dict(self) -> dict[str, str]:
        return {
            "protocol_version": "notemeld.e2ee.handshake.v1",
            "session_id": self.session_id,
            "sender_device_id": self.sender_device_id,
            "recipient_device_id": self.recipient_device_id,
            "ephemeral_public": self.ephemeral_public,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, value: Any) -> "HandshakeEnvelope":
        if not isinstance(value, dict) or value.get("protocol_version") != "notemeld.e2ee.handshake.v1":
            raise ValueError("invalid handshake envelope")
        fields = ("session_id", "sender_device_id", "recipient_device_id", "ephemeral_public", "signature")
        if any(type(value.get(field)) is not str for field in fields):
            raise ValueError("invalid handshake envelope")
        return cls(*(value[field] for field in fields))


def create_handshake_envelope(
    signing_private: bytes,
    session_id: str,
    sender: str,
    recipient: str,
    ephemeral_public: bytes,
) -> HandshakeEnvelope:
    """Create a signed, JSON-safe handshake offer."""
    return HandshakeEnvelope(
        session_id=session_id,
        sender_device_id=sender,
        recipient_device_id=recipient,
        ephemeral_public=_b64(ephemeral_public),
        signature=sign_handshake(signing_private, session_id, sender, recipient, ephemeral_public),
    )


def verify_handshake_envelope(envelope: HandshakeEnvelope, signing_public: bytes) -> None:
    if not isinstance(envelope, HandshakeEnvelope):
        raise ValueError("invalid handshake envelope")
    verify_handshake(
        signing_public,
        envelope.signature,
        envelope.session_id,
        envelope.sender_device_id,
        envelope.recipient_device_id,
        _unb64(envelope.ephemeral_public, expected_length=32),
    )


def derive_handshake_session_key(
    local_ephemeral_private: bytes,
    local: HandshakeEnvelope,
    peer: HandshakeEnvelope,
) -> bytes:
    """Derive one symmetric key from two mutually addressed envelopes.

    The transcript orders the endpoints deterministically, so both sides
    derive the same key even though their sender/recipient directions differ.
    Callers must verify each envelope's Ed25519 signature before deriving.
    """
    if not isinstance(local, HandshakeEnvelope) or not isinstance(peer, HandshakeEnvelope):
        raise ValueError("invalid handshake envelope")
    if (
        local.session_id != peer.session_id
        or local.sender_device_id != peer.recipient_device_id
        or local.recipient_device_id != peer.sender_device_id
    ):
        raise ValueError("handshake endpoint mismatch")
    local_public = _unb64(local.ephemeral_public, expected_length=32)
    peer_public = _unb64(peer.ephemeral_public, expected_length=32)
    if local.sender_device_id < peer.sender_device_id:
        first_id, first_public, second_id, second_public = local.sender_device_id, local_public, peer.sender_device_id, peer_public
    else:
        first_id, first_public, second_id, second_public = peer.sender_device_id, peer_public, local.sender_device_id, local_public
    transcript = _handshake_transcript(local.session_id, first_id, first_public, second_id, second_public)
    private = x25519.X25519PrivateKey.from_private_bytes(local_ephemeral_private)
    shared = private.exchange(x25519.X25519PublicKey.from_public_bytes(peer_public))
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=transcript).derive(shared)


def derive_session_key(
    ephemeral_private: bytes,
    peer_ephemeral_public: bytes,
    session_id: str,
    sender: str,
    recipient: str,
) -> bytes:
    private = x25519.X25519PrivateKey.from_private_bytes(ephemeral_private)
    peer = x25519.X25519PublicKey.from_public_bytes(peer_ephemeral_public)
    return HKDF(
        algorithm=hashes.SHA256(),
        length=32,
        salt=None,
        info=_handshake_message(session_id, sender, recipient, b""),
    ).derive(private.exchange(peer))


def encrypt(
    key: bytes, plaintext: bytes, associated_data: bytes = b""
) -> tuple[str, str]:
    nonce = os.urandom(12)
    return _b64(nonce), _b64(
        AESGCM(key).encrypt(nonce, plaintext, associated_data)
    )


def decrypt(
    key: bytes, nonce: str, ciphertext: str, associated_data: bytes = b""
) -> bytes:
    return AESGCM(key).decrypt(
        _unb64(nonce, expected_length=12), _unb64(ciphertext), associated_data
    )


@dataclass
class SessionCipher:
    """Directional AEAD wrapper with monotonic process-local replay cursors."""

    key: bytes
    last_sent_sequence: int = 0
    last_received_sequence: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.key, bytes) or len(self.key) != 32:
            raise ValueError("session key must be exactly 32 bytes")

    def encrypt(
        self, sequence: int, plaintext: bytes, associated_data: bytes = b""
    ) -> tuple[str, str]:
        if (
            type(sequence) is not int
            or sequence < 1
            or sequence <= self.last_sent_sequence
        ):
            raise ValueError("outbound sequence must increase monotonically")
        nonce, ciphertext = encrypt(self.key, plaintext, associated_data)
        self.last_sent_sequence = sequence
        return nonce, ciphertext

    def decrypt(
        self,
        sequence: int,
        nonce: str,
        ciphertext: str,
        associated_data: bytes = b"",
    ) -> bytes:
        if (
            type(sequence) is not int
            or sequence < 1
            or sequence <= self.last_received_sequence
        ):
            raise ValueError("replayed inbound sequence")
        plaintext = decrypt(self.key, nonce, ciphertext, associated_data)
        self.last_received_sequence = sequence
        return plaintext

    def encrypt_frame(self, frame: RemoteFrame, plaintext: bytes) -> RemoteFrame:
        """Create a frame after nonce generation so canonical AAD can include it."""
        if frame.nonce or frame.ciphertext:
            raise ValueError("outbound frame must not contain nonce or ciphertext")
        if (
            type(frame.sequence) is not int
            or frame.sequence < 1
            or frame.sequence <= self.last_sent_sequence
        ):
            raise ValueError("outbound sequence must increase monotonically")
        nonce_bytes = os.urandom(12)
        pending = replace(frame, nonce=_b64(nonce_bytes), ciphertext="pending")
        pending.validate()
        ciphertext = AESGCM(self.key).encrypt(
            nonce_bytes,
            plaintext,
            pending.associated_data(),
        )
        self.last_sent_sequence = frame.sequence
        return replace(pending, ciphertext=_b64(ciphertext))


def derive_rekeyed_session_key(
    current_key: bytes,
    session_id: str,
    sender: str,
    recipient: str,
    epoch: int,
) -> bytes:
    if not isinstance(current_key, bytes) or len(current_key) != 32:
        raise ValueError("session key must be exactly 32 bytes")
    if type(epoch) is not int or epoch < 1:
        raise ValueError("key epoch must be positive")
    info = (
        b"notemeld-e2ee-rekey-v1\0"
        + str(epoch).encode()
        + b"\0"
        + _handshake_message(session_id, sender, recipient, b"")
    )
    return HKDF(
        algorithm=hashes.SHA256(), length=32, salt=current_key, info=info
    ).derive(current_key)


def _handshake_message(
    session_id: str,
    sender: str,
    recipient: str,
    ephemeral_public: bytes,
) -> bytes:
    identities = (session_id, sender, recipient)
    if any(
        not isinstance(value, str)
        or not value
        or len(value) > 4096
        or "\0" in value
        for value in identities
    ):
        raise ValueError("invalid handshake identity")
    if not isinstance(ephemeral_public, bytes) or len(ephemeral_public) not in {0, 32}:
        raise ValueError("invalid ephemeral public key")
    return (
        b"notemeld-e2ee-v1\0"
        + session_id.encode()
        + b"\0"
        + sender.encode()
        + b"\0"
        + recipient.encode()
        + b"\0"
        + ephemeral_public
    )


def _handshake_transcript(
    session_id: str,
    first_id: str,
    first_public: bytes,
    second_id: str,
    second_public: bytes,
) -> bytes:
    if (
        not isinstance(first_public, bytes)
        or len(first_public) != 32
        or not isinstance(second_public, bytes)
        or len(second_public) != 32
    ):
        raise ValueError("invalid handshake transcript key")
    return (
        b"notemeld-e2ee-transcript-v1\0"
        + _handshake_message(session_id, first_id, second_id, b"")
        + first_public
        + second_public
    )


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str, *, expected_length: int | None = None) -> bytes:
    if (
        not isinstance(value, str)
        or not value
        or len(value) > 8 * 1024 * 1024
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        raise ValueError("invalid base64 value")
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
        )
    except (ValueError, binascii.Error) as exc:
        raise ValueError("invalid base64 value") from exc
    if expected_length is not None and len(decoded) != expected_length:
        raise ValueError("invalid decoded length")
    return decoded
