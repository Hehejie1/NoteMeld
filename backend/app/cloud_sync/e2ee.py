"""Application-layer E2EE primitives for device-remote sessions.

The relay never imports this module or receives a session key. Platform
adapters use it after loading device private keys from platform secure storage.
"""
from __future__ import annotations

import base64
import binascii
import os
import re
from dataclasses import dataclass

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
from cryptography.hazmat.primitives.kdf.hkdf import HKDF


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
        ChaCha20Poly1305(key).encrypt(nonce, plaintext, associated_data)
    )


def decrypt(
    key: bytes, nonce: str, ciphertext: str, associated_data: bytes = b""
) -> bytes:
    return ChaCha20Poly1305(key).decrypt(
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
