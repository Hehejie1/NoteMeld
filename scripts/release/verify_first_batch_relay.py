#!/usr/bin/env python3
"""Verify the first-batch production Relay with two proved E2EE clients.

The verifier creates short-lived test devices on an existing test account,
proves possession of both Ed25519 keys, verifies the explicit host-offline
failure, sends AES-256-GCM ciphertext in both directions over WSS, disconnects
both peers, and reconnects them using the Cloud-persisted monotonic cursors for
a second exchange. It prints only non-secret identifiers and hashes;
account/device tokens and plaintext challenges are never included in evidence.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from contextlib import ExitStack
from typing import Any, Callable
from urllib.parse import urlparse


class VerificationError(RuntimeError):
    pass


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VerificationError(f"{method} {path} returned HTTP {exc.code}: {detail[:300]}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{method} {path} failed: {exc}") from exc
    if not isinstance(decoded, dict) or decoded.get("code") != 0:
        raise VerificationError(f"{method} {path} returned an invalid API envelope")
    return decoded.get("data")


def _websocket_url(base_url: str, session_id: str, device_id: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise VerificationError("Cloud RC base URL must be an absolute HTTPS URL")
    path = f"{parsed.path.rstrip('/')}/v1/relay/connect/{urllib.parse.quote(session_id, safe='')}"
    query = urllib.parse.urlencode({"device_id": device_id})
    return urllib.parse.urlunparse(("wss", parsed.netloc, path, "", query, ""))


def _provision_device(
    base_url: str,
    account_token: str,
    device_id: str,
    platform: str,
    *,
    request_fn: Callable[..., Any],
) -> tuple[Any, str]:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:  # pragma: no cover - deployment environment check
        raise VerificationError("cryptography is required for device proof") from exc

    private_key = Ed25519PrivateKey.generate()
    public_key = _b64(private_key.public_key().public_bytes_raw())
    request_fn(
        base_url,
        "POST",
        "/v1/devices/register",
        token=account_token,
        payload={"device_id": device_id, "platform": platform, "display_name": f"RC verifier {platform}", "public_key": public_key},
    )
    challenge_data = request_fn(base_url, "POST", f"/v1/devices/{device_id}/challenge", token=account_token)
    if not isinstance(challenge_data, dict) or not isinstance(challenge_data.get("challenge"), str):
        raise VerificationError("device challenge response is invalid")
    challenge = challenge_data["challenge"]
    proof = b"notemeld-device-proof-v1\0" + device_id.encode() + b"\0" + challenge.encode()
    request_fn(
        base_url,
        "POST",
        f"/v1/devices/{device_id}/challenge/verify",
        token=account_token,
        payload={"challenge": challenge, "signature": _b64(private_key.sign(proof))},
    )
    issued = request_fn(
        base_url,
        "POST",
        f"/v1/devices/{device_id}/token",
        token=account_token,
        payload={
            "scopes": ["device.read", "device.write", "grant.read", "session.read"],
            "expires_in_seconds": 900,
            "revoke_source_token": False,
        },
    )
    if not isinstance(issued, dict) or not isinstance(issued.get("token"), str):
        raise VerificationError("device token exchange response is invalid")
    return private_key, issued["token"]


def _derive_session_key() -> bytes:
    try:
        from cryptography.hazmat.primitives.asymmetric.x25519 import X25519PrivateKey
        from cryptography.hazmat.primitives import hashes
        from cryptography.hazmat.primitives.kdf.hkdf import HKDF
    except ImportError as exc:  # pragma: no cover - deployment environment check
        raise VerificationError("cryptography is required for E2EE verification") from exc

    first = X25519PrivateKey.generate()
    second = X25519PrivateKey.generate()
    shared_first = first.exchange(second.public_key())
    shared_second = second.exchange(first.public_key())
    if shared_first != shared_second:
        raise VerificationError("X25519 peers did not derive the same secret")
    return HKDF(algorithm=hashes.SHA256(), length=32, salt=None, info=b"notemeld-first-batch-relay-verifier-v1").derive(shared_first)


def _aad(frame: dict[str, Any]) -> bytes:
    return json.dumps({key: value for key, value in frame.items() if key != "ciphertext"}, sort_keys=True, separators=(",", ":")).encode()


def _encrypted_frame(
    *,
    key: bytes,
    session_id: str,
    sender: str,
    recipient: str,
    sequence: int,
    frame_type: str,
    plaintext: bytes,
) -> dict[str, Any]:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as exc:  # pragma: no cover - deployment environment check
        raise VerificationError("cryptography is required for E2EE verification") from exc
    nonce = os.urandom(12)
    frame: dict[str, Any] = {
        "protocol_version": "notemeld.sync.v1",
        "session_id": session_id,
        "sender_device_id": sender,
        "recipient_device_id": recipient,
        "sequence": sequence,
        "frame_id": f"rc-{uuid.uuid4()}",
        "authority_epoch": 1,
        "nonce": _b64(nonce),
        "frame_type": frame_type,
    }
    frame["ciphertext"] = _b64(AESGCM(key).encrypt(nonce, plaintext, _aad(frame)))
    return frame


def _decrypt_frame(key: bytes, frame: dict[str, Any]) -> bytes:
    try:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        return AESGCM(key).decrypt(_unb64(frame["nonce"]), _unb64(frame["ciphertext"]), _aad(frame))
    except (ImportError, KeyError, ValueError, TypeError) as exc:
        raise VerificationError("received Relay frame could not be authenticated and decrypted") from exc


def _receive_json(socket: Any, label: str) -> dict[str, Any]:
    raw = socket.recv(timeout=15)
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{label} returned invalid JSON") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{label} returned a non-object frame")
    return value


def run(
    base_url: str,
    username: str,
    password: str,
    *,
    request_fn: Callable[..., Any] = request,
    connect_fn: Callable[..., Any] | None = None,
    verification_plaintext: bytes | None = None,
) -> dict[str, Any]:
    if urlparse(base_url).scheme != "https":
        raise VerificationError("Cloud RC base URL must use HTTPS")
    ready = request_fn(base_url, "GET", "/ready")
    build_commit = ready.get("build_commit") if isinstance(ready, dict) else None
    cloud_image_digest = ready.get("image_digest") if isinstance(ready, dict) else None
    if not isinstance(build_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", build_commit):
        raise VerificationError("Relay Cloud runtime has no immutable build commit")
    if not isinstance(cloud_image_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", cloud_image_digest):
        raise VerificationError("Relay Cloud runtime has no immutable image digest")
    if connect_fn is None:
        try:
            from websockets.sync.client import connect as connect_fn
        except ImportError as exc:  # pragma: no cover - deployment environment check
            raise VerificationError("websockets is required for live Relay verification") from exc

    login = request_fn(base_url, "POST", "/v1/auth/login", payload={"username": username, "password": password})
    if not isinstance(login, dict) or not isinstance(login.get("token"), str):
        raise VerificationError("Cloud login did not return an account token")
    account_token = login["token"]
    suffix = uuid.uuid4().hex[:12]
    controller_id = f"rc-controller-{suffix}"
    host_id = f"rc-host-{suffix}"
    session_id: str | None = None
    cleanup_paths: list[str] = []
    try:
        _controller_key, controller_token = _provision_device(base_url, account_token, controller_id, "verifier-controller", request_fn=request_fn)
        cleanup_paths.append(f"/v1/devices/{controller_id}")
        _host_key, host_token = _provision_device(base_url, account_token, host_id, "verifier-host", request_fn=request_fn)
        cleanup_paths.append(f"/v1/devices/{host_id}")
        grant = request_fn(
            base_url,
            "POST",
            "/v1/grants",
            token=account_token,
            payload={"controller_device_id": controller_id, "host_device_id": host_id, "scopes": ["message.send", "event.receive"]},
        )
        if not isinstance(grant, dict) or not isinstance(grant.get("grant_id"), str):
            raise VerificationError("Relay grant creation response is invalid")
        session = request_fn(base_url, "POST", "/v1/sessions", token=account_token, payload={"kind": "device_remote", "title": "first-batch Relay verification"})
        if not isinstance(session, dict) or not isinstance(session.get("id"), str):
            raise VerificationError("device-remote session creation response is invalid")
        session_id = session["id"]
        cleanup_paths.insert(0, f"/v1/sessions/{session_id}")
        key = _derive_session_key()
        plaintext = verification_plaintext or os.urandom(32)
        controller_url = _websocket_url(base_url, session_id, controller_id)
        host_url = _websocket_url(base_url, session_id, host_id)
        with ExitStack() as stack:
            controller = stack.enter_context(connect_fn(controller_url, additional_headers={"Authorization": f"Bearer {controller_token}"}, open_timeout=15, close_timeout=5))
            controller_ready = _receive_json(controller, "controller Relay cursor")
            controller_sequence = controller_ready.get("next_sequence")
            if controller_ready.get("type") != "relay_ready" or not isinstance(controller_sequence, int) or controller_sequence < 1:
                raise VerificationError(f"controller Relay cursor is invalid: {controller_ready}")
            offline_frame = _encrypted_frame(key=key, session_id=session_id, sender=controller_id, recipient=host_id, sequence=controller_sequence, frame_type="command", plaintext=os.urandom(16))
            controller.send(json.dumps(offline_frame, separators=(",", ":")))
            offline = _receive_json(controller, "offline Relay attempt")
            if offline.get("type") != "failed" or offline.get("error") != "host_offline":
                raise VerificationError(f"offline Relay did not fail closed: {offline}")

            host = stack.enter_context(connect_fn(host_url, additional_headers={"Authorization": f"Bearer {host_token}"}, open_timeout=15, close_timeout=5))
            host_ready = _receive_json(host, "host Relay cursor")
            host_sequence = host_ready.get("next_sequence")
            if host_ready.get("type") != "relay_ready" or not isinstance(host_sequence, int) or host_sequence < 1:
                raise VerificationError(f"host Relay cursor is invalid: {host_ready}")
            command = _encrypted_frame(key=key, session_id=session_id, sender=controller_id, recipient=host_id, sequence=controller_sequence + 1, frame_type="command", plaintext=plaintext)
            controller.send(json.dumps(command, separators=(",", ":")))
            accepted = _receive_json(controller, "controller Relay acknowledgement")
            if accepted.get("type") != "relay_accepted" or accepted.get("frame_id") != command["frame_id"]:
                raise VerificationError(f"controller Relay acknowledgement is invalid: {accepted}")
            delivered = _receive_json(host, "host Relay delivery")
            if delivered != command or _decrypt_frame(key, delivered) != plaintext:
                raise VerificationError("host did not receive the exact authenticated E2EE command")

            receipt_plaintext = hashlib.sha256(plaintext).digest()
            receipt = _encrypted_frame(key=key, session_id=session_id, sender=host_id, recipient=controller_id, sequence=host_sequence, frame_type="receipt", plaintext=receipt_plaintext)
            host.send(json.dumps(receipt, separators=(",", ":")))
            host_accepted = _receive_json(host, "host Relay acknowledgement")
            if host_accepted.get("type") != "relay_accepted" or host_accepted.get("frame_id") != receipt["frame_id"]:
                raise VerificationError(f"host Relay acknowledgement is invalid: {host_accepted}")
            returned = _receive_json(controller, "controller Relay receipt")
            if returned != receipt or _decrypt_frame(key, returned) != receipt_plaintext:
                raise VerificationError("controller did not receive the exact authenticated E2EE receipt")

        recovery_plaintext = os.urandom(32)
        with ExitStack() as recovery_stack:
            controller = recovery_stack.enter_context(connect_fn(controller_url, additional_headers={"Authorization": f"Bearer {controller_token}"}, open_timeout=15, close_timeout=5))
            controller_recovery_ready = _receive_json(controller, "reconnected controller Relay cursor")
            controller_recovery_sequence = controller_recovery_ready.get("next_sequence")
            expected_controller_sequence = command["sequence"] + 1
            if controller_recovery_ready.get("type") != "relay_ready" or controller_recovery_sequence != expected_controller_sequence:
                raise VerificationError("controller Relay cursor did not continue monotonically after reconnect")

            host = recovery_stack.enter_context(connect_fn(host_url, additional_headers={"Authorization": f"Bearer {host_token}"}, open_timeout=15, close_timeout=5))
            host_recovery_ready = _receive_json(host, "reconnected host Relay cursor")
            host_recovery_sequence = host_recovery_ready.get("next_sequence")
            expected_host_sequence = receipt["sequence"] + 1
            if host_recovery_ready.get("type") != "relay_ready" or host_recovery_sequence != expected_host_sequence:
                raise VerificationError("host Relay cursor did not continue monotonically after reconnect")

            recovery_command = _encrypted_frame(
                key=key,
                session_id=session_id,
                sender=controller_id,
                recipient=host_id,
                sequence=controller_recovery_sequence,
                frame_type="command",
                plaintext=recovery_plaintext,
            )
            controller.send(json.dumps(recovery_command, separators=(",", ":")))
            recovery_accepted = _receive_json(controller, "reconnected controller Relay acknowledgement")
            recovery_delivered = _receive_json(host, "reconnected host Relay delivery")
            if recovery_accepted.get("type") != "relay_accepted" or recovery_accepted.get("frame_id") != recovery_command["frame_id"]:
                raise VerificationError("reconnected controller Relay acknowledgement is invalid")
            if recovery_delivered != recovery_command or _decrypt_frame(key, recovery_delivered) != recovery_plaintext:
                raise VerificationError("Host did not receive the authenticated command after reconnect")

            recovery_receipt_plaintext = hashlib.sha256(recovery_plaintext).digest()
            recovery_receipt = _encrypted_frame(
                key=key,
                session_id=session_id,
                sender=host_id,
                recipient=controller_id,
                sequence=host_recovery_sequence,
                frame_type="receipt",
                plaintext=recovery_receipt_plaintext,
            )
            host.send(json.dumps(recovery_receipt, separators=(",", ":")))
            recovery_host_accepted = _receive_json(host, "reconnected host Relay acknowledgement")
            recovery_returned = _receive_json(controller, "reconnected controller Relay receipt")
            if recovery_host_accepted.get("type") != "relay_accepted" or recovery_host_accepted.get("frame_id") != recovery_receipt["frame_id"]:
                raise VerificationError("reconnected Host Relay acknowledgement is invalid")
            if recovery_returned != recovery_receipt or _decrypt_frame(key, recovery_returned) != recovery_receipt_plaintext:
                raise VerificationError("controller did not receive the authenticated receipt after reconnect")

        return {
            "release_checks": {"c_04": "PASS", "c_05_transport_recovery": "PASS"},
            "base_url": base_url.rstrip("/"),
            "build_commit": build_commit,
            "cloud_image_digest": cloud_image_digest,
            "protocol_version": "notemeld.sync.v1",
            "session_id": session_id,
            "grant_id": grant["grant_id"],
            "controller_device_id": controller_id,
            "host_device_id": host_id,
            "offline_error": "host_offline",
            "forward_transport": "relay",
            "forward_cipher": "AES-256-GCM",
            "key_agreement": "X25519+HKDF-SHA256",
            "challenge_sha256": hashlib.sha256(plaintext).hexdigest(),
            "command_frame_id": command["frame_id"],
            "receipt_frame_id": receipt["frame_id"],
            "recovery_challenge_sha256": hashlib.sha256(recovery_plaintext).hexdigest(),
            "recovery_command_frame_id": recovery_command["frame_id"],
            "recovery_receipt_frame_id": recovery_receipt["frame_id"],
            "controller_recovery_sequence": controller_recovery_sequence,
            "host_recovery_sequence": host_recovery_sequence,
        }
    finally:
        for path in cleanup_paths:
            try:
                request_fn(base_url, "DELETE", path, token=account_token)
            except Exception:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("NOTEMELD_CLOUD_BASE_URL"))
    parser.add_argument("--username", default=os.environ.get("NOTEMELD_CLOUD_ADMIN_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("NOTEMELD_CLOUD_ADMIN_PASSWORD"))
    args = parser.parse_args()
    if not args.base_url or not args.username or not args.password:
        parser.error("--base-url, --username, and --password (or matching environment variables) are required")
    try:
        result = run(args.base_url, args.username, args.password)
    except VerificationError as exc:
        print(f"first-batch Relay verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
