"""One-time device proof for credential-free LAN transport authentication."""
from __future__ import annotations

import base64
import binascii
import hmac
import ipaddress
import re
import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass
from typing import Any, Callable

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from .network import is_lan_address


_GRANT_SCOPES = frozenset(
    {
        "message.send",
        "context.select",
        "model.select",
        "tool.invoke",
        "event.receive",
        "workspace.read",
        "workspace.write",
        "dangerous.approve",
        "approval.remote.resolve",
        "session.permission.manage",
        "session.full_access",
        "full_access",
    }
)


class LanAuthError(ValueError):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class LanChallenge:
    challenge_id: str
    challenge: str
    expires_at: int


@dataclass(frozen=True)
class LanPeerAuthorization:
    session_id: str
    controller_device_id: str
    host_device_id: str
    grant_id: str
    role: str
    scopes: frozenset[str]
    workspace_id: str
    authority_epoch: int
    valid_until: int


@dataclass(frozen=True)
class _PendingChallenge:
    session_id: str
    controller_device_id: str
    peer_address: str
    challenge: str
    expires_at: int


class LanPeerAuthenticator:
    """Authenticate a LAN peer without sending a cloud bearer over plaintext WS.

    ``authorize`` must call the cloud control plane with the host's bound
    device token and return the short-lived `/v1/lan/authorize` assertion.
    """

    def __init__(
        self,
        host_device_id: str,
        authorize: Callable[[str, str, str], dict[str, Any]],
        *,
        challenge_ttl_seconds: int = 30,
        max_pending: int = 1024,
        max_pending_per_peer: int = 8,
        max_verifications_per_minute: int = 30,
        clock: Callable[[], float] = time.time,
    ):
        _validate_identity(host_device_id)
        if challenge_ttl_seconds < 5 or challenge_ttl_seconds > 120:
            raise ValueError("LAN challenge TTL must be between 5 and 120 seconds")
        if min(max_pending, max_pending_per_peer, max_verifications_per_minute) < 1:
            raise ValueError("LAN authentication limits must be positive")
        self.host_device_id = host_device_id
        self._authorize = authorize
        self._ttl = challenge_ttl_seconds
        self._max_pending = max_pending
        self._max_pending_per_peer = max_pending_per_peer
        self._max_verifications_per_minute = max_verifications_per_minute
        self._clock = clock
        self._pending: dict[str, _PendingChallenge] = {}
        self._verification_times: dict[str, deque[int]] = {}
        self._lock = threading.Lock()

    def issue(
        self,
        session_id: str,
        controller_device_id: str,
        peer_address: str,
    ) -> LanChallenge:
        _validate_identity(session_id)
        _validate_identity(controller_device_id)
        peer = _validate_peer_address(peer_address)
        now = int(self._clock())
        with self._lock:
            self._prune(now)
            peer_pending = sum(
                item.peer_address == peer for item in self._pending.values()
            )
            if len(self._pending) >= self._max_pending or peer_pending >= self._max_pending_per_peer:
                raise LanAuthError("challenge_rate_limited")
            challenge_id = secrets.token_urlsafe(18)
            challenge = secrets.token_urlsafe(32)
            expires_at = now + self._ttl
            self._pending[challenge_id] = _PendingChallenge(
                session_id=session_id,
                controller_device_id=controller_device_id,
                peer_address=peer,
                challenge=challenge,
                expires_at=expires_at,
            )
        return LanChallenge(challenge_id, challenge, expires_at)

    def verify(
        self,
        challenge_id: str,
        challenge: str,
        signature: str,
        peer_address: str,
    ) -> LanPeerAuthorization:
        peer = _validate_peer_address(peer_address)
        _validate_proof_value(challenge_id)
        _validate_proof_value(challenge)
        _validate_proof_value(signature, max_length=256)
        now = int(self._clock())
        with self._lock:
            self._prune(now)
            self._record_verification(peer, now)
            pending = self._pending.pop(challenge_id, None)
        if (
            pending is None
            or pending.peer_address != peer
            or pending.expires_at <= now
            or not hmac.compare_digest(pending.challenge, challenge)
        ):
            raise LanAuthError("invalid_challenge")
        try:
            assertion = self._authorize(
                pending.session_id,
                pending.controller_device_id,
                self.host_device_id,
            )
            authorization = _parse_assertion(
                assertion,
                pending.session_id,
                pending.controller_device_id,
                self.host_device_id,
                now,
            )
            public_key = Ed25519PublicKey.from_public_bytes(
                _decode_urlsafe(assertion["controller_public_key"], expected_length=32)
            )
            public_key.verify(
                _decode_urlsafe(signature, expected_length=64),
                _proof_message(
                    pending.session_id,
                    pending.controller_device_id,
                    self.host_device_id,
                    challenge_id,
                    challenge,
                ),
            )
        except LanAuthError:
            raise
        except (InvalidSignature, KeyError, TypeError, ValueError, binascii.Error):
            raise LanAuthError("invalid_device_proof") from None
        except Exception as exc:
            raise LanAuthError("authorization_unavailable") from exc
        return authorization

    @staticmethod
    def proof_message(
        session_id: str,
        controller_device_id: str,
        host_device_id: str,
        challenge_id: str,
        challenge: str,
    ) -> bytes:
        return _proof_message(
            session_id,
            controller_device_id,
            host_device_id,
            challenge_id,
            challenge,
        )

    def _record_verification(self, peer: str, now: int) -> None:
        attempts = self._verification_times.setdefault(peer, deque())
        while attempts and attempts[0] <= now - 60:
            attempts.popleft()
        if len(attempts) >= self._max_verifications_per_minute:
            raise LanAuthError("verification_rate_limited")
        attempts.append(now)

    def _prune(self, now: int) -> None:
        expired = [key for key, item in self._pending.items() if item.expires_at <= now]
        for key in expired:
            self._pending.pop(key, None)
        for peer, attempts in list(self._verification_times.items()):
            while attempts and attempts[0] <= now - 60:
                attempts.popleft()
            if not attempts:
                self._verification_times.pop(peer, None)


def _parse_assertion(
    value: dict[str, Any],
    session_id: str,
    controller_device_id: str,
    host_device_id: str,
    now: int,
) -> LanPeerAuthorization:
    if not isinstance(value, dict):
        raise LanAuthError("invalid_authorization")
    if (
        value.get("session_id") != session_id
        or value.get("controller_device_id") != controller_device_id
        or value.get("host_device_id") != host_device_id
        or type(value.get("authority_epoch")) is not int
        or value["authority_epoch"] < 1
        or type(value.get("valid_until")) is not int
        or type(value.get("ttl_seconds")) is not int
        or value["ttl_seconds"] < 1
        or value["ttl_seconds"] > 60
        or not isinstance(value.get("scopes"), list)
        or any(not isinstance(scope, str) or not scope for scope in value["scopes"])
        or len(set(value["scopes"])) != len(value["scopes"])
        or not set(value["scopes"]).issubset(_GRANT_SCOPES)
        or value.get("role") not in {"standard", "super_admin"}
    ):
        raise LanAuthError("invalid_authorization")
    for field in ("grant_id", "workspace_id", "controller_public_key"):
        if not isinstance(value.get(field), str) or not value[field]:
            raise LanAuthError("invalid_authorization")
    return LanPeerAuthorization(
        session_id=session_id,
        controller_device_id=controller_device_id,
        host_device_id=host_device_id,
        grant_id=value["grant_id"],
        role=value["role"],
        scopes=frozenset(value["scopes"]),
        workspace_id=value["workspace_id"],
        authority_epoch=value["authority_epoch"],
        valid_until=now + value["ttl_seconds"],
    )


def _proof_message(
    session_id: str,
    controller_device_id: str,
    host_device_id: str,
    challenge_id: str,
    challenge: str,
) -> bytes:
    values = (
        session_id,
        controller_device_id,
        host_device_id,
        challenge_id,
        challenge,
    )
    if any(not isinstance(value, str) or not value or "\0" in value for value in values):
        raise ValueError("invalid LAN proof field")
    return b"notemeld-lan-auth-v1\0" + b"\0".join(
        value.encode("utf-8") for value in values
    )


def _decode_urlsafe(value: str, *, expected_length: int) -> bytes:
    if (
        not isinstance(value, str)
        or not value
        or re.fullmatch(r"[A-Za-z0-9_-]+", value) is None
    ):
        raise ValueError("invalid URL-safe base64")
    decoded = base64.b64decode(
        value + "=" * (-len(value) % 4), altchars=b"-_", validate=True
    )
    if len(decoded) != expected_length:
        raise ValueError("invalid decoded length")
    return decoded


def _validate_identity(value: str) -> None:
    if not isinstance(value, str) or not value or len(value) > 4096 or "\0" in value:
        raise ValueError("invalid LAN identity")


def _validate_proof_value(value: str, *, max_length: int = 4096) -> None:
    if not isinstance(value, str) or not value or len(value) > max_length or "\0" in value:
        raise LanAuthError("invalid_challenge")


def _validate_peer_address(value: str) -> str:
    try:
        address = ipaddress.ip_address(value.split("%", 1)[0])
    except (AttributeError, ValueError) as exc:
        raise LanAuthError("invalid_peer_address") from exc
    if not is_lan_address(address):
        raise LanAuthError("invalid_peer_address")
    return value.lower()
