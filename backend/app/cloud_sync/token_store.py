"""Small encrypted token-at-rest store for platform adapters.

The key is deliberately supplied by the platform (Keychain/Keystore/Tauri
secure storage). This module never derives a key from a device id or password.
"""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.exceptions import InvalidTag


class TokenStoreError(ValueError):
    pass


class EncryptedTokenStore:
    VERSION = 1

    def __init__(self, path: str | Path, key: bytes):
        if len(key) != 32:
            raise TokenStoreError("token store key must be 32 bytes")
        self.path = Path(path)
        self._key = key

    def save(self, token: str) -> None:
        if not token or len(token) > 4096:
            raise TokenStoreError("invalid token")
        nonce = secrets.token_bytes(12)
        payload = AESGCM(self._key).encrypt(nonce, token.encode("utf-8"), b"notemeld-token-v1")
        envelope = {"version": self.VERSION, "nonce": nonce.hex(), "ciphertext": payload.hex()}
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_name(f".{self.path.name}.{os.getpid()}.tmp")
        with open(temp, "w", encoding="utf-8") as handle:
            os.chmod(temp, 0o600)
            json.dump(envelope, handle, separators=(",", ":"))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, self.path)
        os.chmod(self.path, 0o600)

    def load(self) -> str | None:
        if not self.path.exists():
            return None
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
            if envelope.get("version") != self.VERSION:
                raise TokenStoreError("unsupported token store version")
            nonce = bytes.fromhex(envelope["nonce"])
            ciphertext = bytes.fromhex(envelope["ciphertext"])
            return AESGCM(self._key).decrypt(nonce, ciphertext, b"notemeld-token-v1").decode("utf-8")
        except (KeyError, ValueError, TypeError, UnicodeError, InvalidTag) as exc:
            raise TokenStoreError("invalid or corrupted token store") from exc

    def clear(self) -> None:
        try:
            self.path.unlink()
        except FileNotFoundError:
            return
