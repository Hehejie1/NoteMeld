#!/usr/bin/env python3
"""Verify a real desktop Host executes an E2EE Agent turn through Cloud Relay.

This verifier creates only a short-lived controller identity.  The target Host
must already be registered, online, and running the desktop Cloud Host runtime.
Cloud receives opaque handshake/command/event envelopes; the verifier proves a
durable receipt and a unique successful canonical Agent terminal event without
printing credentials, key material, prompts, or model output.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time
import types
import uuid
from typing import Any, Callable
from urllib.parse import urlparse


REPO_ROOT = Path(__file__).resolve().parents[2]
RELEASE_SCRIPTS_ROOT = Path(__file__).resolve().parent
if str(RELEASE_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(RELEASE_SCRIPTS_ROOT))


def _load_cloud_sync_contracts() -> tuple[Any, Any]:
    """Load the canonical protocol modules without initializing FastAPI."""
    package_name = "_notemeld_release_cloud_sync"
    package = types.ModuleType(package_name)
    package.__path__ = [str(REPO_ROOT / "desktop" / "backend" / "app" / "cloud_sync")]
    sys.modules.setdefault(package_name, package)
    loaded = []
    for module_name in ("protocol", "e2ee"):
        qualified = f"{package_name}.{module_name}"
        path = REPO_ROOT / "desktop" / "backend" / "app" / "cloud_sync" / f"{module_name}.py"
        spec = importlib.util.spec_from_file_location(qualified, path)
        if spec is None or spec.loader is None:
            raise RuntimeError(f"cannot load canonical cloud sync module: {module_name}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[qualified] = module
        spec.loader.exec_module(module)
        loaded.append(module)
    return loaded[0], loaded[1]


RemoteFrame: Any = None
HandshakeEnvelope: Any = None
SessionCipher: Any = None
create_handshake_envelope: Any = None
derive_handshake_session_key: Any = None
generate_ephemeral: Any = None
generate_identity: Any = None
verify_handshake_envelope: Any = None


def _ensure_contracts() -> None:
    global RemoteFrame, HandshakeEnvelope, SessionCipher
    global create_handshake_envelope, derive_handshake_session_key
    global generate_ephemeral, generate_identity, verify_handshake_envelope
    if RemoteFrame is not None:
        return
    try:
        protocol, e2ee = _load_cloud_sync_contracts()
    except ImportError as exc:
        raise VerificationError("cryptography is required for live remote Agent verification") from exc
    RemoteFrame = protocol.RemoteFrame
    HandshakeEnvelope = e2ee.HandshakeEnvelope
    SessionCipher = e2ee.SessionCipher
    create_handshake_envelope = e2ee.create_handshake_envelope
    derive_handshake_session_key = e2ee.derive_handshake_session_key
    generate_ephemeral = e2ee.generate_ephemeral
    generate_identity = e2ee.generate_identity
    verify_handshake_envelope = e2ee.verify_handshake_envelope

from verify_first_batch_relay import request, _websocket_url  # noqa: E402


class VerificationError(RuntimeError):
    pass


TERMINAL_EVENTS = {
    "turn.succeeded",
    "turn.failed",
    "turn.cancelled",
    "turn.interrupted",
}


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _provision_controller(
    base_url: str,
    account_token: str,
    device_id: str,
    *,
    request_fn: Callable[..., Any],
) -> tuple[bytes, str]:
    signing_private, signing_public = generate_identity()
    request_fn(
        base_url,
        "POST",
        "/v1/devices/register",
        token=account_token,
        payload={
            "device_id": device_id,
            "platform": "release-verifier",
            "display_name": "RC remote Agent verifier",
            "public_key": _b64(signing_public),
        },
    )
    challenge_data = request_fn(
        base_url,
        "POST",
        f"/v1/devices/{device_id}/challenge",
        token=account_token,
    )
    if not isinstance(challenge_data, dict) or not isinstance(challenge_data.get("challenge"), str):
        raise VerificationError("controller device challenge response is invalid")
    challenge = challenge_data["challenge"]
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    proof = b"notemeld-device-proof-v1\0" + device_id.encode() + b"\0" + challenge.encode()
    signature = Ed25519PrivateKey.from_private_bytes(signing_private).sign(proof)
    request_fn(
        base_url,
        "POST",
        f"/v1/devices/{device_id}/challenge/verify",
        token=account_token,
        payload={"challenge": challenge, "signature": _b64(signature)},
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
        raise VerificationError("controller device token exchange response is invalid")
    return signing_private, issued["token"]


def _select_host(devices: Any, host_device_id: str) -> dict[str, Any]:
    if not isinstance(devices, list):
        raise VerificationError("Cloud device list response is invalid")
    matches = [item for item in devices if isinstance(item, dict) and item.get("id") == host_device_id]
    if len(matches) != 1:
        raise VerificationError("target Host is not registered on the test account")
    host = matches[0]
    if host.get("platform") != "desktop":
        raise VerificationError("target Host is not a desktop device")
    if host.get("online") is not True or host.get("revoked_at") is not None:
        raise VerificationError("target desktop Host is not online")
    if not isinstance(host.get("last_seen_at"), (int, float)) or isinstance(host.get("last_seen_at"), bool):
        raise VerificationError("target desktop Host has no valid heartbeat timestamp")
    public_key = host.get("public_key")
    try:
        decoded = _unb64(public_key) if isinstance(public_key, str) else b""
    except (ValueError, TypeError):
        decoded = b""
    if len(decoded) != 32:
        raise VerificationError("target desktop Host has no valid Ed25519 public key")
    return host


def _receive_json(socket: Any, label: str, timeout: float, *, allow_timeout: bool = False) -> dict[str, Any] | None:
    try:
        raw = socket.recv(timeout=max(0.01, timeout))
    except TimeoutError:
        if allow_timeout:
            return None
        raise VerificationError(f"timed out while waiting for {label}") from None
    try:
        value = json.loads(raw)
    except Exception as exc:
        raise VerificationError(f"timed out or received invalid JSON while waiting for {label}") from exc
    if not isinstance(value, dict):
        raise VerificationError(f"{label} returned a non-object frame")
    return value


def _handshake_frame(
    *,
    session_id: str,
    controller_id: str,
    host_id: str,
    sequence: int,
    authority_epoch: int,
    envelope: HandshakeEnvelope,
) -> RemoteFrame:
    return RemoteFrame(
        session_id=session_id,
        sender_device_id=controller_id,
        recipient_device_id=host_id,
        sequence=sequence,
        ciphertext=_b64(json.dumps(envelope.as_dict(), separators=(",", ":")).encode()),
        frame_id=str(uuid.uuid4()),
        authority_epoch=authority_epoch,
        nonce=_b64(os.urandom(12)),
        frame_type="handshake",
    )


def _complete_handshake(
    socket: Any,
    *,
    session_id: str,
    controller_id: str,
    host_id: str,
    host_public_key: bytes,
    controller_signing_private: bytes,
    next_sequence: int,
    authority_epoch: int,
    timeout_seconds: float,
) -> tuple[SessionCipher, RemoteFrame, RemoteFrame]:
    deadline = time.monotonic() + timeout_seconds
    ephemeral_private, ephemeral_public = generate_ephemeral()
    offer = create_handshake_envelope(
        controller_signing_private,
        session_id,
        controller_id,
        host_id,
        ephemeral_public,
    )
    sent: RemoteFrame | None = None
    while time.monotonic() < deadline:
        sent = _handshake_frame(
            session_id=session_id,
            controller_id=controller_id,
            host_id=host_id,
            sequence=next_sequence,
            authority_epoch=authority_epoch,
            envelope=offer,
        )
        socket.send(sent.to_json())
        next_sequence += 1
        retry = False
        while time.monotonic() < deadline:
            message = _receive_json(socket, "desktop Host handshake", min(5.0, deadline - time.monotonic()))
            assert message is not None
            if message.get("type") == "failed" and message.get("error") == "host_offline":
                retry = True
                break
            if message.get("type") == "relay_accepted":
                continue
            try:
                response = RemoteFrame.from_json(json.dumps(message, separators=(",", ":")))
            except ValueError as exc:
                raise VerificationError("desktop Host returned an invalid handshake frame") from exc
            if (
                response.frame_type != "handshake"
                or response.session_id != session_id
                or response.sender_device_id != host_id
                or response.recipient_device_id != controller_id
                or response.frame_id != sent.frame_id
                or response.authority_epoch != authority_epoch
            ):
                raise VerificationError("desktop Host returned a mismatched handshake frame")
            try:
                peer = HandshakeEnvelope.from_dict(json.loads(_unb64(response.ciphertext)))
                verify_handshake_envelope(peer, host_public_key)
                key = derive_handshake_session_key(ephemeral_private, offer, peer)
            except Exception as exc:
                raise VerificationError("desktop Host handshake signature or transcript is invalid") from exc
            return (
                SessionCipher(
                    key,
                    last_sent_sequence=sent.sequence,
                    last_received_sequence=response.sequence,
                ),
                sent,
                response,
            )
        if retry:
            time.sleep(min(1.0, max(0.0, deadline - time.monotonic())))
            continue
    raise VerificationError("desktop Host did not join the Relay before the handshake deadline")


def _decrypt_payload(cipher: SessionCipher, frame: RemoteFrame) -> dict[str, Any]:
    try:
        plaintext = cipher.decrypt(frame.sequence, frame.nonce, frame.ciphertext, frame.associated_data())
        value = json.loads(plaintext)
    except Exception as exc:
        raise VerificationError("desktop Host response failed E2EE authentication") from exc
    if not isinstance(value, dict):
        raise VerificationError("desktop Host response plaintext is not an object")
    return value


def _run_agent_turn(
    socket: Any,
    cipher: SessionCipher,
    *,
    session_id: str,
    controller_id: str,
    host_id: str,
    authority_epoch: int,
    challenge: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    request_id = f"rc-remote-{uuid.uuid4()}"
    prompt = f"Reply with exactly this verification token and nothing else: {challenge}"
    command = RemoteFrame(
        session_id=session_id,
        sender_device_id=controller_id,
        recipient_device_id=host_id,
        sequence=cipher.last_sent_sequence + 1,
        ciphertext="",
        frame_id=str(uuid.uuid4()),
        authority_epoch=authority_epoch,
        nonce="",
        frame_type="command",
    )
    encrypted = cipher.encrypt_frame(
        command,
        json.dumps({"request_id": request_id, "input": prompt}, separators=(",", ":")).encode(),
    )
    socket.send(encrypted.to_json())

    deadline = time.monotonic() + timeout_seconds
    receipt: dict[str, Any] | None = None
    receipt_frame_id: str | None = None
    events: list[dict[str, Any]] = []
    event_plaintexts: list[bytes] = []
    terminal_seen_at: float | None = None
    while time.monotonic() < deadline:
        complete = receipt is not None and terminal_seen_at is not None
        timeout = min(deadline - time.monotonic(), 1.0) if complete else deadline - time.monotonic()
        message = _receive_json(
            socket,
            "durable receipt and Agent events",
            timeout,
            allow_timeout=complete,
        )
        if message is None:
            break
        if message.get("type") == "relay_accepted":
            if message.get("frame_id") != encrypted.frame_id:
                raise VerificationError("Cloud acknowledged an unexpected command frame")
            continue
        if message.get("type") in {"failed", "rejected"}:
            raise VerificationError(f"Cloud Relay rejected the remote Agent flow: {message.get('error') or message.get('reason') or 'unknown'}")
        try:
            frame = RemoteFrame.from_json(json.dumps(message, separators=(",", ":")))
        except ValueError as exc:
            raise VerificationError("desktop Host returned an invalid encrypted frame") from exc
        if frame.session_id != session_id or frame.sender_device_id != host_id or frame.recipient_device_id != controller_id:
            raise VerificationError("desktop Host response endpoints do not match the session")
        payload = _decrypt_payload(cipher, frame)
        raw_payload = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        if frame.frame_type == "receipt":
            if payload.get("request_id") != request_id or payload.get("frame_id") != encrypted.frame_id:
                raise VerificationError("durable receipt does not match the submitted command")
            if payload.get("status") != "received" or payload.get("queue_status") != "queued":
                raise VerificationError("desktop Host did not confirm durable command admission")
            if type(payload.get("queue_sequence")) is not int or payload["queue_sequence"] < 1:
                raise VerificationError("desktop Host durable queue sequence is invalid")
            receipt = payload
            receipt_frame_id = frame.frame_id
        elif frame.frame_type == "event":
            if payload.get("request_id") != request_id or not isinstance(payload.get("event"), dict):
                raise VerificationError("Agent event does not match the submitted command")
            event = payload["event"]
            events.append(event)
            event_plaintexts.append(raw_payload)
            if event.get("type") in TERMINAL_EVENTS:
                terminal_seen_at = time.monotonic()
        else:
            raise VerificationError("desktop Host returned an unexpected encrypted frame type")

        terminal_types = [str(event.get("type")) for event in events if event.get("type") in TERMINAL_EVENTS]
        if receipt is not None and terminal_types:
            if len(terminal_types) != 1:
                raise VerificationError("remote Agent turn emitted multiple terminal events")
            if terminal_types[0] != "turn.succeeded":
                raise VerificationError(f"remote Agent turn ended with {terminal_types[0]}")
    terminal_types = [str(event.get("type")) for event in events if event.get("type") in TERMINAL_EVENTS]
    if receipt is None or not terminal_types:
        raise VerificationError("timed out before durable receipt and successful Agent terminal event")
    if len(terminal_types) != 1:
        raise VerificationError("remote Agent turn emitted multiple terminal events")
    if terminal_types[0] != "turn.succeeded":
        raise VerificationError(f"remote Agent turn ended with {terminal_types[0]}")
    combined = b"\n".join(event_plaintexts)
    if challenge.encode() not in combined:
        raise VerificationError("successful remote Agent events did not contain the unique challenge")
    return {
        "request_id": request_id,
        "command_frame_id": encrypted.frame_id,
        "receipt_frame_id": receipt_frame_id,
        "queue_sequence": receipt["queue_sequence"],
        "queue_status": receipt["queue_status"],
        "event_count": len(events),
        "terminal_event": terminal_types[0],
        "answer_sha256": hashlib.sha256(combined).hexdigest(),
    }


def _run_approval_turn(
    socket: Any,
    cipher: SessionCipher,
    *,
    session_id: str,
    controller_id: str,
    host_id: str,
    authority_epoch: int,
    prompt: str,
    expected_decision: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    """Require one real Host approval pause and its fail-closed resolution."""
    if expected_decision not in {"deny", "expired"}:
        raise VerificationError("approval verification decision must be deny or expired")
    if not prompt.strip():
        raise VerificationError("dangerous approval prompt is required")
    request_id = f"rc-approval-{uuid.uuid4()}"
    command = RemoteFrame(
        session_id=session_id,
        sender_device_id=controller_id,
        recipient_device_id=host_id,
        sequence=cipher.last_sent_sequence + 1,
        ciphertext="",
        frame_id=str(uuid.uuid4()),
        authority_epoch=authority_epoch,
        nonce="",
        frame_type="command",
    )
    encrypted = cipher.encrypt_frame(
        command,
        json.dumps({"request_id": request_id, "input": prompt}, separators=(",", ":")).encode(),
    )
    socket.send(encrypted.to_json())

    deadline = time.monotonic() + timeout_seconds
    receipt_seen = False
    events: list[dict[str, Any]] = []
    terminal_seen_at: float | None = None
    while time.monotonic() < deadline:
        complete = receipt_seen and terminal_seen_at is not None
        wait_for = min(deadline - time.monotonic(), 1.0) if complete else deadline - time.monotonic()
        message = _receive_json(
            socket,
            "Host approval events",
            wait_for,
            allow_timeout=complete,
        )
        if message is None:
            break
        if message.get("type") == "relay_accepted":
            if message.get("frame_id") != encrypted.frame_id:
                raise VerificationError("Cloud acknowledged an unexpected approval command frame")
            continue
        if message.get("type") in {"failed", "rejected"}:
            raise VerificationError("Cloud Relay rejected the approval verification flow")
        try:
            frame = RemoteFrame.from_json(json.dumps(message, separators=(",", ":")))
        except ValueError as exc:
            raise VerificationError("desktop Host returned an invalid approval frame") from exc
        if frame.session_id != session_id or frame.sender_device_id != host_id or frame.recipient_device_id != controller_id:
            raise VerificationError("desktop Host approval frame endpoints do not match the session")
        payload = _decrypt_payload(cipher, frame)
        if frame.frame_type == "receipt":
            if payload.get("request_id") != request_id or payload.get("frame_id") != encrypted.frame_id:
                raise VerificationError("approval durable receipt does not match the submitted command")
            if payload.get("status") != "received" or payload.get("queue_status") != "queued":
                raise VerificationError("desktop Host did not durably admit the approval command")
            receipt_seen = True
            continue
        if frame.frame_type != "event" or payload.get("request_id") != request_id or not isinstance(payload.get("event"), dict):
            raise VerificationError("desktop Host approval event does not match the command")
        event = payload["event"]
        events.append(event)
        if event.get("type") in TERMINAL_EVENTS:
            terminal_seen_at = time.monotonic()

    required = [event for event in events if event.get("type") == "approval.required"]
    resolved = [event for event in events if event.get("type") == "approval.resolved"]
    terminal = [event for event in events if event.get("type") in TERMINAL_EVENTS]
    if not receipt_seen or len(required) != 1 or len(resolved) != 1 or len(terminal) != 1:
        raise VerificationError("approval flow did not emit one receipt, required, resolved, and terminal event")
    required_payload = required[0].get("payload")
    resolved_payload = resolved[0].get("payload")
    if not isinstance(required_payload, dict) or not isinstance(resolved_payload, dict):
        raise VerificationError("approval events have invalid payloads")
    approval_id = required_payload.get("approval_id")
    call_id = required_payload.get("call_id")
    if not isinstance(approval_id, str) or not approval_id or not isinstance(call_id, str) or not call_id:
        raise VerificationError("approval.required omitted its approval or call identifier")
    if resolved_payload.get("approval_id") != approval_id or resolved_payload.get("decision") != expected_decision:
        raise VerificationError("approval resolution does not match the expected fail-closed decision")
    dispatched = [
        event for event in events
        if event.get("type") == "tool.started"
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("call_id") == call_id
    ]
    if dispatched:
        raise VerificationError("denied or expired dangerous tool was dispatched")
    terminal_type = str(terminal[0].get("type"))
    if expected_decision == "expired":
        terminal_payload = terminal[0].get("payload")
        error = terminal_payload.get("error") if isinstance(terminal_payload, dict) else None
        if terminal_type != "turn.failed" or not isinstance(error, dict) or error.get("code") != "approval_expired":
            raise VerificationError("expired approval did not terminate with approval_expired")
    return {
        "decision": expected_decision,
        "approval_id_sha256": hashlib.sha256(approval_id.encode()).hexdigest(),
        "call_id_sha256": hashlib.sha256(call_id.encode()).hexdigest(),
        "dangerous_prompt_sha256": hashlib.sha256(prompt.encode()).hexdigest(),
        "terminal_event": terminal_type,
        "tool_dispatched": False,
        "event_count": len(events),
    }


def _revocation_probe_frame(
    *,
    session_id: str,
    controller_id: str,
    host_id: str,
    sequence: int,
    authority_epoch: int,
) -> RemoteFrame:
    """Build an opaque frame that must be rejected before Host delivery."""
    return RemoteFrame(
        session_id=session_id,
        sender_device_id=controller_id,
        recipient_device_id=host_id,
        sequence=sequence,
        ciphertext=_b64(os.urandom(32)),
        frame_id=str(uuid.uuid4()),
        authority_epoch=authority_epoch,
        nonce=_b64(os.urandom(12)),
        frame_type="command",
    )


def _require_revoked_probe_rejected(socket: Any, frame: RemoteFrame, label: str) -> None:
    socket.send(frame.to_json())
    response = _receive_json(socket, label, 15)
    if response != {"type": "rejected", "error": "invalid_envelope"}:
        raise VerificationError(f"revoked grant was not rejected on {label}")


def _require_revoked_device_connection_denied(
    connect_fn: Callable[..., Any], socket_url: str, controller_token: str
) -> None:
    try:
        with connect_fn(
            socket_url,
            additional_headers={"Authorization": f"Bearer {controller_token}"},
            open_timeout=15,
            close_timeout=5,
        ) as socket:
            response = _receive_json(socket, "revoked device connection", 15)
            if response is not None:
                raise VerificationError("revoked controller device established a new Relay connection")
    except VerificationError:
        raise
    except Exception:
        # A 4401 handshake/first-read close is the expected fail-closed result.
        return
    raise VerificationError("revoked controller device established a new Relay connection")


def run(
    base_url: str,
    username: str,
    password: str,
    host_device_id: str,
    *,
    request_fn: Callable[..., Any] = request,
    connect_fn: Callable[..., Any] | None = None,
    handshake_timeout_seconds: float = 45,
    agent_timeout_seconds: float = 180,
    verification_challenge: str | None = None,
    security_audit_database: Path | None = None,
    security_audit_log_paths: list[Path] | None = None,
    security_audit_redis_url: str | None = None,
    security_audit_provider_key: str | None = None,
    security_audit_fn: Callable[..., dict[str, Any]] | None = None,
    verify_revocation: bool = False,
    approval_scenario: str | None = None,
    dangerous_prompt: str | None = None,
) -> dict[str, Any]:
    if urlparse(base_url).scheme != "https":
        raise VerificationError("Cloud RC base URL must use HTTPS")
    if not host_device_id:
        raise VerificationError("target Host device ID is required")
    if approval_scenario not in {None, "deny", "expired"}:
        raise VerificationError("approval scenario must be deny or expired")
    if approval_scenario is not None and not str(dangerous_prompt or "").strip():
        raise VerificationError("approval scenario requires a dangerous prompt")
    audit_inputs = (
        security_audit_database,
        security_audit_log_paths,
        security_audit_redis_url,
        security_audit_provider_key,
    )
    if any(value is not None for value in audit_inputs) and not all(audit_inputs):
        raise VerificationError("security audit requires database, logs, Redis URL, and Provider key together")
    ready = request_fn(base_url, "GET", "/ready")
    build_commit = ready.get("build_commit") if isinstance(ready, dict) else None
    cloud_image_digest = ready.get("image_digest") if isinstance(ready, dict) else None
    if not isinstance(build_commit, str) or not re.fullmatch(r"[0-9a-f]{40}", build_commit):
        raise VerificationError("real Host Cloud runtime has no immutable build commit")
    if not isinstance(cloud_image_digest, str) or not re.fullmatch(r"sha256:[0-9a-f]{64}", cloud_image_digest):
        raise VerificationError("real Host Cloud runtime has no immutable image digest")
    _ensure_contracts()
    if connect_fn is None:
        try:
            from websockets.sync.client import connect as connect_fn
        except ImportError as exc:  # pragma: no cover - deployment environment check
            raise VerificationError("websockets is required for live remote Agent verification") from exc

    login = request_fn(base_url, "POST", "/v1/auth/login", payload={"username": username, "password": password})
    if not isinstance(login, dict) or not isinstance(login.get("token"), str):
        raise VerificationError("Cloud login did not return an account token")
    account_token = login["token"]
    host = _select_host(request_fn(base_url, "GET", "/v1/devices", token=account_token), host_device_id)
    controller_id = f"rc-agent-controller-{uuid.uuid4().hex[:12]}"
    cleanup_paths: list[str] = []
    session_id: str | None = None
    grant_id: str | None = None
    try:
        signing_private, controller_token = _provision_controller(
            base_url,
            account_token,
            controller_id,
            request_fn=request_fn,
        )
        cleanup_paths.append(f"/v1/devices/{controller_id}")
        grant = request_fn(
            base_url,
            "POST",
            "/v1/grants",
            token=account_token,
            payload={
                "controller_device_id": controller_id,
                "host_device_id": host_device_id,
                "role": "standard",
                "scopes": ["message.send", "event.receive"],
            },
        )
        if not isinstance(grant, dict) or not isinstance(grant.get("grant_id"), str):
            raise VerificationError("remote Agent grant creation response is invalid")
        grant_id = grant["grant_id"]
        cleanup_paths.insert(0, f"/v1/grants/{grant_id}")
        session = request_fn(
            base_url,
            "POST",
            "/v1/sessions",
            token=account_token,
            payload={"kind": "device_remote", "title": "first-batch remote Agent verification"},
        )
        if not isinstance(session, dict) or not isinstance(session.get("id"), str):
            raise VerificationError("device-remote session creation response is invalid")
        session_id = session["id"]
        cleanup_paths.insert(0, f"/v1/sessions/{session_id}")
        socket_url = _websocket_url(base_url, session_id, controller_id)
        challenge = verification_challenge or f"NMRC-{uuid.uuid4().hex}"
        revocation: dict[str, Any] | None = None
        approval: dict[str, Any] | None = None
        with connect_fn(
            socket_url,
            additional_headers={"Authorization": f"Bearer {controller_token}"},
            open_timeout=15,
            close_timeout=5,
        ) as socket:
            ready = _receive_json(socket, "controller Relay cursor", 15)
            assert ready is not None
            next_sequence = ready.get("next_sequence")
            if ready.get("type") != "relay_ready" or type(next_sequence) is not int or next_sequence < 1:
                raise VerificationError("controller Relay cursor is invalid")
            cipher, handshake, peer_handshake = _complete_handshake(
                socket,
                session_id=session_id,
                controller_id=controller_id,
                host_id=host_device_id,
                host_public_key=_unb64(host["public_key"]),
                controller_signing_private=signing_private,
                next_sequence=next_sequence,
                authority_epoch=1,
                timeout_seconds=handshake_timeout_seconds,
            )
            turn = _run_agent_turn(
                socket,
                cipher,
                session_id=session_id,
                controller_id=controller_id,
                host_id=host_device_id,
                authority_epoch=1,
                challenge=challenge,
                timeout_seconds=agent_timeout_seconds,
            )
            if approval_scenario is not None:
                approval = _run_approval_turn(
                    socket,
                    cipher,
                    session_id=session_id,
                    controller_id=controller_id,
                    host_id=host_device_id,
                    authority_epoch=1,
                    prompt=str(dangerous_prompt),
                    expected_decision=approval_scenario,
                    timeout_seconds=agent_timeout_seconds,
                )
            if verify_revocation:
                request_fn(base_url, "DELETE", f"/v1/grants/{grant_id}", token=account_token)
                active_probe = _revocation_probe_frame(
                    session_id=session_id,
                    controller_id=controller_id,
                    host_id=host_device_id,
                    sequence=cipher.last_sent_sequence + 1,
                    authority_epoch=1,
                )
                _require_revoked_probe_rejected(socket, active_probe, "existing Relay connection")
        if verify_revocation:
            with connect_fn(
                socket_url,
                additional_headers={"Authorization": f"Bearer {controller_token}"},
                open_timeout=15,
                close_timeout=5,
            ) as revoked_socket:
                revoked_ready = _receive_json(revoked_socket, "revoked grant Relay cursor", 15)
                revoked_next_sequence = revoked_ready.get("next_sequence") if revoked_ready else None
                if (
                    not isinstance(revoked_ready, dict)
                    or revoked_ready.get("type") != "relay_ready"
                    or type(revoked_next_sequence) is not int
                    or revoked_next_sequence < 1
                ):
                    raise VerificationError("revoked grant Relay cursor is invalid")
                reconnect_probe = _revocation_probe_frame(
                    session_id=session_id,
                    controller_id=controller_id,
                    host_id=host_device_id,
                    sequence=revoked_next_sequence,
                    authority_epoch=1,
                )
                _require_revoked_probe_rejected(revoked_socket, reconnect_probe, "new Relay connection")
            restored_grant = request_fn(
                base_url,
                "POST",
                "/v1/grants",
                token=account_token,
                payload={
                    "controller_device_id": controller_id,
                    "host_device_id": host_device_id,
                    "role": "standard",
                    "scopes": ["message.send", "event.receive"],
                },
            )
            if not isinstance(restored_grant, dict) or not isinstance(restored_grant.get("grant_id"), str):
                raise VerificationError("grant restoration before device revocation failed")
            cleanup_paths.insert(0, f"/v1/grants/{restored_grant['grant_id']}")
            with connect_fn(
                socket_url,
                additional_headers={"Authorization": f"Bearer {controller_token}"},
                open_timeout=15,
                close_timeout=5,
            ) as device_socket:
                device_ready = _receive_json(device_socket, "device revocation Relay cursor", 15)
                device_next_sequence = device_ready.get("next_sequence") if device_ready else None
                if (
                    not isinstance(device_ready, dict)
                    or device_ready.get("type") != "relay_ready"
                    or type(device_next_sequence) is not int
                    or device_next_sequence < 1
                ):
                    raise VerificationError("device revocation Relay cursor is invalid")
                request_fn(base_url, "DELETE", f"/v1/devices/{controller_id}", token=account_token)
                device_probe = _revocation_probe_frame(
                    session_id=session_id,
                    controller_id=controller_id,
                    host_id=host_device_id,
                    sequence=device_next_sequence,
                    authority_epoch=1,
                )
                _require_revoked_probe_rejected(device_socket, device_probe, "device-revoked Relay connection")
            _require_revoked_device_connection_denied(connect_fn, socket_url, controller_token)
            revocation = {
                "grant_revoked": True,
                "grant_existing_connection": "rejected",
                "grant_new_connection": "rejected",
                "device_revoked": True,
                "device_existing_connection": "rejected",
                "device_new_connection": "denied",
                "host_delivery": False,
            }
        persisted_commands = request_fn(
            base_url,
            "GET",
            f"/v1/sessions/{session_id}/commands?after=0&limit=100",
            token=account_token,
        )
        persisted_events = request_fn(
            base_url,
            "GET",
            f"/v1/sessions/{session_id}/events?after=0&limit=100",
            token=account_token,
        )
        if persisted_commands != [] or persisted_events != []:
            raise VerificationError("device-remote payload was persisted in Cloud command/event storage")
        security_audit: dict[str, Any] | None = None
        if security_audit_database is not None:
            if security_audit_fn is None:
                from verify_first_batch_security_audit import run as security_audit_fn
            try:
                security_audit = security_audit_fn(
                    security_audit_database,
                    security_audit_log_paths,
                    security_audit_redis_url,
                    {
                        "challenge": challenge,
                        "account_token": account_token,
                        "device_token": controller_token,
                        "session_key": _b64(cipher.key),
                        "provider_key": security_audit_provider_key,
                    },
                    session_id=session_id,
                )
            except Exception as exc:
                raise VerificationError("production Cloud storage/log/Redis security audit failed") from exc
        release_checks = {
            "c_04_real_host": "PASS",
            "x_06_remote_agent": "PASS",
            "e_01_cloud_command_event_storage": "PASS",
        }
        if security_audit is not None:
            release_checks["e_01_cloud_storage_logs_redis"] = "PASS"
        result = {
            "release_checks": release_checks,
            "base_url": base_url.rstrip("/"),
            "build_commit": build_commit,
            "cloud_image_digest": cloud_image_digest,
            "protocol_version": "notemeld.sync.v1",
            "session_id": session_id,
            "grant_id": grant_id,
            "controller_device_id": controller_id,
            "host_device_id": host_device_id,
            "host_platform": host["platform"],
            "host_last_seen_at": host["last_seen_at"],
            "transport": "relay",
            "cipher": "AES-256-GCM",
            "key_agreement": "signed-Ed25519+X25519+HKDF-SHA256",
            "handshake_frame_id": handshake.frame_id,
            "host_handshake_sequence": peer_handshake.sequence,
            "cloud_persisted_commands": 0,
            "cloud_persisted_events": 0,
            "challenge_sha256": hashlib.sha256(challenge.encode()).hexdigest(),
            **turn,
        }
        if security_audit is not None:
            result["security_audit"] = security_audit
        if revocation is not None:
            result["revocation"] = revocation
        if approval is not None:
            result["approval"] = approval
        return result
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
    parser.add_argument("--host-device-id", default=os.environ.get("NOTEMELD_REMOTE_HOST_DEVICE_ID"))
    parser.add_argument("--handshake-timeout", type=float, default=45)
    parser.add_argument("--agent-timeout", type=float, default=180)
    parser.add_argument("--approval-scenario", choices=("deny", "expired"))
    parser.add_argument("--dangerous-prompt-env", default="NOTEMELD_E02_DANGEROUS_PROMPT")
    parser.add_argument("--security-audit-database", type=Path)
    parser.add_argument("--security-audit-log", type=Path, action="append")
    parser.add_argument("--security-audit-redis-url-env", default="NOTEMELD_CLOUD_RELAY_URL")
    parser.add_argument("--security-audit-provider-key-env", default="NOTEMELD_CLOUD_AGENT_API_KEY")
    args = parser.parse_args()
    if not args.base_url or not args.username or not args.password or not args.host_device_id:
        parser.error("--base-url, --username, --password, and --host-device-id (or matching environment variables) are required")
    try:
        audit_requested = args.security_audit_database is not None or args.security_audit_log is not None
        result = run(
            args.base_url,
            args.username,
            args.password,
            args.host_device_id,
            handshake_timeout_seconds=args.handshake_timeout,
            agent_timeout_seconds=args.agent_timeout,
            security_audit_database=args.security_audit_database,
            security_audit_log_paths=args.security_audit_log,
            security_audit_redis_url=os.environ.get(args.security_audit_redis_url_env) if audit_requested else None,
            security_audit_provider_key=os.environ.get(args.security_audit_provider_key_env) if audit_requested else None,
            verify_revocation=True,
            approval_scenario=args.approval_scenario,
            dangerous_prompt=os.environ.get(args.dangerous_prompt_env) if args.approval_scenario else None,
        )
    except VerificationError as exc:
        print(f"first-batch remote Agent verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
