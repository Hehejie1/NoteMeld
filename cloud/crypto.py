"""Application-layer E2EE primitives for device-remote sessions.

The cloud never calls decrypt; clients use these helpers with device keys. The
implementation deliberately delegates all cryptography to the maintained
``cryptography`` package.
"""
from __future__ import annotations

import base64
import os
from dataclasses import dataclass

try:
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519, x25519
    from cryptography.hazmat.primitives.ciphers.aead import ChaCha20Poly1305
    from cryptography.hazmat.primitives.kdf.hkdf import HKDF
except ImportError as exc:  # pragma: no cover - exercised in deployments without optional crypto dependency
    raise RuntimeError("cloud E2EE requires the cryptography package") from exc


def generate_identity() -> tuple[bytes, bytes]:
    signing = ed25519.Ed25519PrivateKey.generate()
    return (
        signing.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()),
        signing.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),
    )


def generate_ephemeral() -> tuple[bytes, bytes]:
    private = x25519.X25519PrivateKey.generate()
    return (
        private.private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw, serialization.NoEncryption()),
        private.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw),
    )


def sign_handshake(signing_private: bytes, session_id: str, sender: str, recipient: str, ephemeral_public: bytes) -> str:
    key = ed25519.Ed25519PrivateKey.from_private_bytes(signing_private)
    message = _handshake_message(session_id, sender, recipient, ephemeral_public)
    return _b64(key.sign(message))


def verify_handshake(signing_public: bytes, signature: str, session_id: str, sender: str, recipient: str, ephemeral_public: bytes) -> None:
    key = ed25519.Ed25519PublicKey.from_public_bytes(signing_public)
    key.verify(_unb64(signature), _handshake_message(session_id, sender, recipient, ephemeral_public))


def derive_session_key(ephemeral_private: bytes, peer_ephemeral_public: bytes, session_id: str, sender: str, recipient: str) -> bytes:
    private = x25519.X25519PrivateKey.from_private_bytes(ephemeral_private)
    peer = x25519.X25519PublicKey.from_public_bytes(peer_ephemeral_public)
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=_handshake_message(session_id, sender, recipient, b"")).derive(private.exchange(peer))


def encrypt(key: bytes, plaintext: bytes, associated_data: bytes = b"") -> tuple[str, str]:
    nonce = os.urandom(12)
    return _b64(nonce), _b64(ChaCha20Poly1305(key).encrypt(nonce, plaintext, associated_data))


def decrypt(key: bytes, nonce: str, ciphertext: str, associated_data: bytes = b"") -> bytes:
    return ChaCha20Poly1305(key).decrypt(_unb64(nonce), _unb64(ciphertext), associated_data)


@dataclass
class SessionCipher:
    """Directional AEAD session wrapper for platform adapters.

    The relay persists sequence cursors server-side, but clients must also
    reject a ciphertext that is replayed after it reaches the recipient. The
    sequence is authenticated by the caller's frame associated data and is
    only committed to the receive cursor after successful decryption.
    """

    key: bytes
    last_sent_sequence: int = 0
    last_received_sequence: int = 0

    def __post_init__(self) -> None:
        if not isinstance(self.key, bytes) or len(self.key) != 32:
            raise ValueError("session key must be exactly 32 bytes")

    def encrypt(self, sequence: int, plaintext: bytes, associated_data: bytes = b"") -> tuple[str, str]:
        if not isinstance(sequence, int) or sequence < 1 or sequence <= self.last_sent_sequence:
            raise ValueError("outbound sequence must increase monotonically")
        nonce, ciphertext = encrypt(self.key, plaintext, associated_data)
        self.last_sent_sequence = sequence
        return nonce, ciphertext

    def decrypt(self, sequence: int, nonce: str, ciphertext: str, associated_data: bytes = b"") -> bytes:
        if not isinstance(sequence, int) or sequence < 1 or sequence <= self.last_received_sequence:
            raise ValueError("replayed inbound sequence")
        plaintext = decrypt(self.key, nonce, ciphertext, associated_data)
        self.last_received_sequence = sequence
        return plaintext


def derive_rekeyed_session_key(current_key: bytes, session_id: str, sender: str, recipient: str, epoch: int) -> bytes:
    """Derive a fresh directional key for an explicit session epoch."""
    if not isinstance(current_key, bytes) or len(current_key) != 32:
        raise ValueError("session key must be exactly 32 bytes")
    if not isinstance(epoch, int) or epoch < 1:
        raise ValueError("key epoch must be positive")
    info = b"notemeld-e2ee-rekey-v1\0" + str(epoch).encode() + b"\0" + _handshake_message(session_id, sender, recipient, b"")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=current_key, info=info).derive(current_key)


def _handshake_message(session_id: str, sender: str, recipient: str, ephemeral_public: bytes) -> bytes:
    return b"notemeld-e2ee-v1\0" + session_id.encode() + b"\0" + sender.encode() + b"\0" + recipient.encode() + b"\0" + ephemeral_public


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
