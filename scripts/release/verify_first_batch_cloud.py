#!/usr/bin/env python3
"""Fail-closed C-01/C-02 verification against a live NoteMeld Cloud RC.

The verifier deliberately rejects development instances, HTTP endpoints,
memory relays, deterministic Agent responses, and ambiguous terminal events.
It prints only non-secret evidence metadata; callers may redirect stdout into
the release evidence directory.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable
from urllib.parse import urlparse


TERMINAL_EVENTS = {"turn.completed", "turn.failed", "turn.needs_attention", "turn.cancelled"}
REQUIRED_READY_CHECKS = {
    "database",
    "workspace_root",
    "relay",
    "device_proof_crypto",
    "agent_provider_config",
    "backup_storage_config",
    "otp_delivery_config",
    "device_proof_config",
    "release_identity",
}


class VerificationError(RuntimeError):
    pass


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, Any] | None = None,
    timeout_seconds: float = 15,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_seconds) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise VerificationError(f"{method} {path} returned HTTP {exc.code}: {detail[:300]}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{method} {path} failed: {exc}") from exc
    if path == "/ready":
        return decoded
    if not isinstance(decoded, dict) or decoded.get("code") != 0:
        raise VerificationError(f"{method} {path} returned an invalid API envelope")
    return decoded.get("data")


def validate_ready(base_url: str, ready: Any, expected_commit: str, expected_image_digest: str) -> dict[str, str]:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise VerificationError("Cloud RC base URL must be an absolute HTTPS URL")
    if not isinstance(ready, dict) or ready.get("ready") is not True:
        raise VerificationError("Cloud RC is not ready")
    if ready.get("environment") != "production":
        raise VerificationError("Cloud RC does not report environment=production")
    if ready.get("agent_backend") != "canonical-sdk":
        raise VerificationError("Cloud RC does not report the canonical SDK Agent backend")
    if ready.get("build_commit") != expected_commit or ready.get("image_digest") != expected_image_digest:
        raise VerificationError("Cloud RC runtime identity does not match the candidate image")
    checks = ready.get("checks")
    if not isinstance(checks, dict):
        raise VerificationError("Cloud RC readiness checks are missing")
    missing = sorted(REQUIRED_READY_CHECKS.difference(checks))
    failed = sorted(key for key in REQUIRED_READY_CHECKS if checks.get(key) != "ok")
    if missing or failed:
        raise VerificationError(f"Cloud RC readiness checks are incomplete: missing={missing}, failed={failed}")
    return {key: str(checks[key]) for key in sorted(REQUIRED_READY_CHECKS)}


def validate_capabilities(capabilities: Any) -> dict[str, Any]:
    if not isinstance(capabilities, dict):
        raise VerificationError("Cloud capabilities are missing")
    expected = {
        "protocol_version": "notemeld.sync.v1",
        "device_proof_required": True,
        "e2ee_relay_envelope": True,
        "relay_persists_payload": False,
        "relay_backend": "redis",
        "relay_multi_worker": True,
    }
    mismatches = {key: {"expected": value, "actual": capabilities.get(key)} for key, value in expected.items() if capabilities.get(key) != value}
    if mismatches:
        raise VerificationError(f"Cloud RC capabilities are not release-safe: {json.dumps(mismatches, sort_keys=True)}")
    return {key: capabilities[key] for key in expected}


def validate_terminal_events(events: Any, challenge: str, expected_model: str) -> dict[str, Any]:
    if not isinstance(events, list):
        raise VerificationError("Cloud event stream is not a list")
    terminals = [event for event in events if isinstance(event, dict) and event.get("event_type") in TERMINAL_EVENTS]
    if len(terminals) != 1:
        raise VerificationError(f"Cloud Agent must emit exactly one terminal event, got {len(terminals)}")
    terminal = terminals[0]
    if terminal.get("event_type") != "turn.completed":
        raise VerificationError(f"Cloud Agent ended with {terminal.get('event_type')}")
    payload = terminal.get("payload")
    if not isinstance(payload, dict):
        raise VerificationError("Cloud Agent terminal payload is missing")
    output = payload.get("output")
    model = payload.get("model")
    if not isinstance(output, str) or challenge not in output:
        raise VerificationError("Cloud Agent response did not contain the unique verification challenge")
    if not isinstance(model, str) or not model or model.startswith("deterministic-"):
        raise VerificationError("Cloud Agent response does not prove a real Provider model")
    if model != expected_model:
        raise VerificationError(f"Cloud Agent used model {model!r}, expected {expected_model!r}")
    sequences = [event.get("sequence") for event in events if isinstance(event, dict)]
    if any(not isinstance(sequence, int) or sequence < 1 for sequence in sequences) or sequences != sorted(set(sequences)):
        raise VerificationError("Cloud event sequence is not positive, unique, and monotonic")
    return {"event_count": len(events), "terminal_event": terminal["event_type"], "model": model}


def run(
    base_url: str,
    username: str,
    password: str,
    timeout: float,
    expected_model: str,
    expected_commit: str,
    expected_image_digest: str,
    *,
    request_fn: Callable[..., Any] = request,
    challenge: str | None = None,
) -> dict[str, Any]:
    if timeout <= 0:
        raise VerificationError("Cloud Agent timeout must be positive")
    challenge = challenge or f"NM-RC-{uuid.uuid4()}"
    if re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None:
        raise VerificationError("Cloud RC expected commit must be a full lowercase SHA")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", expected_image_digest) is None:
        raise VerificationError("Cloud RC expected image digest must be immutable")
    ready_checks = validate_ready(base_url, request_fn(base_url, "GET", "/ready"), expected_commit, expected_image_digest)
    login = request_fn(base_url, "POST", "/v1/auth/login", payload={"username": username, "password": password})
    if not isinstance(login, dict) or not isinstance(login.get("token"), str):
        raise VerificationError("Cloud login did not return an account token")
    token = login["token"]
    capabilities = validate_capabilities(request_fn(base_url, "GET", "/v1/capabilities", token=token))
    session = request_fn(base_url, "POST", "/v1/cloud/sessions", token=token, payload={"kind": "cloud_native", "title": "first-batch RC verification"})
    if not isinstance(session, dict) or not isinstance(session.get("id"), str):
        raise VerificationError("Cloud session creation did not return a session id")
    session_id = session["id"]
    request_id = f"first-batch-{uuid.uuid4()}"
    submitted = request_fn(
        base_url,
        "POST",
        f"/v1/cloud/sessions/{session_id}/commands",
        token=token,
        payload={"request_id": request_id, "input": f"Reply with this verification code verbatim: {challenge}"},
        timeout_seconds=max(15.0, min(timeout + 5.0, 300.0)),
    )
    if not isinstance(submitted, dict) or not isinstance(submitted.get("command_id"), str):
        raise VerificationError("Cloud command submission did not return a command id")
    command_id = submitted["command_id"]
    command = submitted
    deadline = time.monotonic() + timeout
    while command.get("status") not in {"completed", "failed", "cancelled", "needs_attention"}:
        if time.monotonic() >= deadline:
            raise VerificationError(f"Cloud command {command_id} did not reach a terminal status")
        time.sleep(0.25)
        command = request_fn(base_url, "GET", f"/v1/cloud/sessions/{session_id}/commands/{command_id}", token=token)
        if not isinstance(command, dict):
            raise VerificationError("Cloud command status response is invalid")
    if command.get("status") != "completed":
        raise VerificationError(f"Cloud command ended in {command.get('status')}")
    events = request_fn(base_url, "GET", f"/v1/cloud/sessions/{session_id}/events?after=0", token=token)
    terminal = validate_terminal_events(events, challenge, expected_model)
    snapshot = request_fn(base_url, "GET", f"/v1/cloud/sessions/{session_id}/snapshot", token=token)
    if not isinstance(snapshot, dict) or not events or snapshot.get("snapshot_seq") != events[-1]["sequence"]:
        raise VerificationError("Cloud snapshot cursor does not match the event stream")
    request_fn(base_url, "POST", f"/v1/cloud/sessions/{session_id}/archive", token=token, payload={})
    return {
        "release_checks": {"c_01": "PASS", "c_02": "PASS"},
        "base_url": base_url.rstrip("/"),
        "build_commit": expected_commit,
        "cloud_image_digest": expected_image_digest,
        "ready_checks": ready_checks,
        "capabilities": capabilities,
        "session_id": session_id,
        "command_id": command_id,
        "request_id": request_id,
        "challenge_sha256": hashlib.sha256(challenge.encode("utf-8")).hexdigest(),
        "snapshot_seq": snapshot["snapshot_seq"],
        **terminal,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("NOTEMELD_CLOUD_BASE_URL"))
    parser.add_argument("--username", default=os.environ.get("NOTEMELD_CLOUD_ADMIN_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("NOTEMELD_CLOUD_ADMIN_PASSWORD"))
    parser.add_argument("--expected-model", default=os.environ.get("NOTEMELD_EXPECTED_CLOUD_MODEL"))
    parser.add_argument("--expected-commit", default=os.environ.get("NOTEMELD_EXPECTED_CLOUD_COMMIT"))
    parser.add_argument("--expected-image-digest", default=os.environ.get("NOTEMELD_EXPECTED_CLOUD_IMAGE_DIGEST"))
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    if not args.base_url or not args.username or not args.password or not args.expected_model or not args.expected_commit or not args.expected_image_digest:
        parser.error("Cloud URL, credentials, model, commit, and image digest are required")
    try:
        result = run(args.base_url, args.username, args.password, args.timeout, args.expected_model, args.expected_commit, args.expected_image_digest)
    except (VerificationError, KeyError, IndexError) as exc:
        print(f"first-batch Cloud verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
