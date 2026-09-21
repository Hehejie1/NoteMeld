from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import time
import re


def encrypt_secret(value: str, master_key: str) -> str:
    """Encrypt a provider credential for local cloud-database storage."""
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - deployment dependency
        raise RuntimeError("cryptography is required for secret storage") from exc
    key = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest())
    return Fernet(key).encrypt(value.encode()).decode()


def decrypt_secret(value: str, master_key: str) -> str:
    from cryptography.fernet import Fernet
    key = base64.urlsafe_b64encode(hashlib.sha256(master_key.encode()).digest())
    return Fernet(key).decrypt(value.encode()).decode()


def hash_password(password: str) -> str:
    if len(password) < 8:
        raise ValueError("password must contain at least 8 characters")
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)
    return "scrypt$16384$8$1$" + _b64(salt) + "$" + _b64(digest)


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt, expected = encoded.split("$")
        if algorithm != "scrypt":
            return False
        actual = hashlib.scrypt(password.encode(), salt=_unb64(salt), n=int(n), r=int(r), p=int(p))
        return hmac.compare_digest(actual, _unb64(expected))
    except (ValueError, TypeError):
        return False


def issue_token() -> tuple[str, str]:
    token_id = secrets.token_urlsafe(12)
    secret = secrets.token_urlsafe(32)
    raw = f"nmt_{token_id}.{secret}"
    return raw, token_digest(token_id, secret)


def parse_token(raw: str) -> tuple[str, str] | None:
    if not isinstance(raw, str) or len(raw) > 512 or not raw.startswith("nmt_") or "." not in raw[4:]:
        return None
    token_id, secret = raw[4:].split(".", 1)
    if (
        not token_id
        or not secret
        or len(token_id) > 128
        or len(secret) > 384
        or re.fullmatch(r"[A-Za-z0-9_-]+", token_id) is None
        or re.fullmatch(r"[A-Za-z0-9_-]+", secret) is None
    ):
        return None
    return token_id, secret


def token_digest(token_id: str, secret: str) -> str:
    return hashlib.sha256(f"{token_id}.{secret}".encode()).hexdigest()


def token_expiry(ttl_seconds: int) -> int:
    return int(time.time()) + ttl_seconds


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
