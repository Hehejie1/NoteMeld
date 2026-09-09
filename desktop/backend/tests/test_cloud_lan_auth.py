from __future__ import annotations

import base64

import pytest
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.cloud_sync.lan_auth import LanAuthError, LanPeerAuthenticator


def _assertion(private_key: Ed25519PrivateKey, *, valid_until: int = 1060):
    return {
        "session_id": "session-a",
        "controller_device_id": "controller-device",
        "host_device_id": "host-device",
        "controller_public_key": base64.urlsafe_b64encode(
            private_key.public_key().public_bytes_raw()
        ).decode().rstrip("="),
        "grant_id": "grant-a",
        "role": "standard",
        "scopes": ["message.send", "tool.invoke"],
        "workspace_id": "project-a",
        "authority_epoch": 3,
        "valid_until": valid_until,
        "ttl_seconds": max(1, valid_until - 1000),
    }


def test_lan_peer_proof_is_one_time_and_returns_bounded_authorization():
    now = [1000]
    private_key = Ed25519PrivateKey.generate()
    calls = []

    def authorize(session_id, controller_device_id, host_device_id):
        calls.append((session_id, controller_device_id, host_device_id))
        return _assertion(private_key)

    authenticator = LanPeerAuthenticator(
        "host-device", authorize, clock=lambda: now[0]
    )
    challenge = authenticator.issue(
        "session-a", "controller-device", "192.168.1.20"
    )
    message = authenticator.proof_message(
        "session-a",
        "controller-device",
        "host-device",
        challenge.challenge_id,
        challenge.challenge,
    )
    signature = base64.urlsafe_b64encode(private_key.sign(message)).decode().rstrip("=")

    authorization = authenticator.verify(
        challenge.challenge_id,
        challenge.challenge,
        signature,
        "192.168.1.20",
    )
    assert authorization.authority_epoch == 3
    assert authorization.scopes == frozenset({"message.send", "tool.invoke"})
    assert calls == [("session-a", "controller-device", "host-device")]

    with pytest.raises(LanAuthError, match="invalid_challenge"):
        authenticator.verify(
            challenge.challenge_id,
            challenge.challenge,
            signature,
            "192.168.1.20",
        )


def test_lan_peer_challenge_is_bound_to_network_peer_and_expires():
    now = [1000]
    private_key = Ed25519PrivateKey.generate()
    authenticator = LanPeerAuthenticator(
        "host-device", lambda *_: _assertion(private_key), clock=lambda: now[0]
    )
    challenge = authenticator.issue(
        "session-a", "controller-device", "192.168.1.20"
    )
    with pytest.raises(LanAuthError, match="invalid_challenge"):
        authenticator.verify(
            challenge.challenge_id,
            challenge.challenge,
            "invalid",
            "192.168.1.21",
        )

    challenge = authenticator.issue(
        "session-a", "controller-device", "192.168.1.20"
    )
    now[0] = challenge.expires_at
    with pytest.raises(LanAuthError, match="invalid_challenge"):
        authenticator.verify(
            challenge.challenge_id,
            challenge.challenge,
            "invalid",
            "192.168.1.20",
        )


def test_lan_peer_rejects_invalid_signature_and_stale_cloud_assertion():
    now = [1000]
    private_key = Ed25519PrivateKey.generate()
    wrong_key = Ed25519PrivateKey.generate()
    assertion = _assertion(private_key)
    authenticator = LanPeerAuthenticator(
        "host-device", lambda *_: assertion, clock=lambda: now[0]
    )
    challenge = authenticator.issue(
        "session-a", "controller-device", "10.0.0.2"
    )
    message = authenticator.proof_message(
        "session-a",
        "controller-device",
        "host-device",
        challenge.challenge_id,
        challenge.challenge,
    )
    signature = base64.urlsafe_b64encode(wrong_key.sign(message)).decode().rstrip("=")
    with pytest.raises(LanAuthError, match="invalid_device_proof"):
        authenticator.verify(
            challenge.challenge_id, challenge.challenge, signature, "10.0.0.2"
        )

    assertion["ttl_seconds"] = 0
    challenge = authenticator.issue(
        "session-a", "controller-device", "10.0.0.2"
    )
    message = authenticator.proof_message(
        "session-a",
        "controller-device",
        "host-device",
        challenge.challenge_id,
        challenge.challenge,
    )
    signature = base64.urlsafe_b64encode(private_key.sign(message)).decode().rstrip("=")
    with pytest.raises(LanAuthError, match="invalid_authorization"):
        authenticator.verify(
            challenge.challenge_id, challenge.challenge, signature, "10.0.0.2"
        )


def test_lan_authentication_limits_pending_and_verification_attempts():
    private_key = Ed25519PrivateKey.generate()
    authenticator = LanPeerAuthenticator(
        "host-device",
        lambda *_: _assertion(private_key),
        max_pending=1,
        max_pending_per_peer=1,
        max_verifications_per_minute=1,
        clock=lambda: 1000,
    )
    first = authenticator.issue("session-a", "controller-device", "127.0.0.1")
    with pytest.raises(LanAuthError, match="challenge_rate_limited"):
        authenticator.issue("session-a", "controller-device", "127.0.0.1")
    with pytest.raises(LanAuthError, match="invalid_challenge"):
        authenticator.verify(first.challenge_id, "wrong", "invalid", "127.0.0.1")
    second = authenticator.issue("session-a", "controller-device", "127.0.0.1")
    with pytest.raises(LanAuthError, match="verification_rate_limited"):
        authenticator.verify(second.challenge_id, second.challenge, "invalid", "127.0.0.1")


def test_lan_authentication_rejects_public_peer_addresses():
    for address in ("8.8.8.8", "192.0.2.1", "0.0.0.0"):
        with pytest.raises(LanAuthError, match="invalid_peer_address"):
            LanPeerAuthenticator("host-device", lambda *_: {}).issue(
                "session-a", "controller-device", address
            )
