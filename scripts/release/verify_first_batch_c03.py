#!/usr/bin/env python3
"""Verify Cloud C-03 with a real process restart and two queued Agent commands.

The operator supplies a JSON argv array used to abruptly restart the target
Cloud worker or single-instance deployment.  No shell is involved.  The
verifier proves that the interrupted command becomes needs_attention without
another attempt, explicitly abandons it, and only then allows the queued
command to complete with the configured real Provider model.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import uuid
from typing import Any, Callable, Sequence
from urllib.parse import urlparse


TERMINAL_EVENTS = {"turn.completed", "turn.failed", "turn.needs_attention", "turn.cancelled"}


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


def _login(request_fn: Callable[..., Any], base_url: str, username: str, password: str) -> str:
    result = request_fn(base_url, "POST", "/v1/auth/login", payload={"username": username, "password": password})
    token = result.get("token") if isinstance(result, dict) else None
    if not isinstance(token, str) or not token:
        raise VerificationError("Cloud login did not return an account token")
    return token


def _validate_ready(base_url: str, ready: Any) -> tuple[str, str]:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname:
        raise VerificationError("C-03 requires an absolute production HTTPS Cloud URL")
    if not isinstance(ready, dict) or ready.get("ready") is not True or ready.get("environment") != "production":
        raise VerificationError("C-03 target is not a ready production Cloud deployment")
    if ready.get("agent_backend") != "canonical-sdk":
        raise VerificationError("C-03 requires the canonical SDK Agent backend")
    commit, digest = ready.get("build_commit"), ready.get("image_digest")
    if not isinstance(commit, str) or len(commit) != 40 or any(char not in "0123456789abcdef" for char in commit):
        raise VerificationError("C-03 Cloud runtime has no immutable build commit")
    if not isinstance(digest, str) or len(digest) != 71 or not digest.startswith("sha256:") or any(char not in "0123456789abcdef" for char in digest[7:]):
        raise VerificationError("C-03 Cloud runtime has no immutable image digest")
    return commit, digest


def _commands_by_request_id(value: Any, request_ids: set[str]) -> dict[str, dict[str, Any]]:
    if not isinstance(value, list):
        raise VerificationError("Cloud command list is invalid")
    result = {
        str(item.get("request_id")): item
        for item in value
        if isinstance(item, dict) and item.get("request_id") in request_ids
    }
    return result


def _wait_for(
    probe: Callable[[], Any],
    predicate: Callable[[Any], bool],
    description: str,
    timeout: float,
    *,
    sleep_fn: Callable[[float], None],
    monotonic_fn: Callable[[], float],
) -> Any:
    deadline = monotonic_fn() + timeout
    last: Any = None
    while monotonic_fn() < deadline:
        try:
            last = probe()
        except VerificationError:
            last = None
        if predicate(last):
            return last
        sleep_fn(0.25)
    raise VerificationError(f"timed out waiting for {description}")


def _default_restart(command: Sequence[str]) -> None:
    completed = subprocess.run(list(command), capture_output=True, text=True, timeout=180, check=False)
    if completed.returncode != 0:
        raise VerificationError("operator restart command failed")


def _event_for(events: Any, event_type: str, command_id: str) -> list[dict[str, Any]]:
    if not isinstance(events, list):
        raise VerificationError("Cloud event list is invalid")
    return [
        event for event in events
        if isinstance(event, dict)
        and event.get("event_type") == event_type
        and isinstance(event.get("payload"), dict)
        and event["payload"].get("command_id") == command_id
    ]


def run(
    base_url: str,
    username: str,
    password: str,
    expected_model: str,
    restart_command: Sequence[str],
    timeout: float,
    *,
    request_fn: Callable[..., Any] = request,
    restart_fn: Callable[[Sequence[str]], None] = _default_restart,
    sleep_fn: Callable[[float], None] = time.sleep,
    monotonic_fn: Callable[[], float] = time.monotonic,
    challenges: tuple[str, str] | None = None,
) -> dict[str, Any]:
    if timeout <= 0:
        raise VerificationError("C-03 timeout must be positive")
    if not expected_model or expected_model.startswith("deterministic-"):
        raise VerificationError("C-03 requires an explicit real Provider model")
    if not restart_command or any(not isinstance(part, str) or not part for part in restart_command):
        raise VerificationError("restart command must be a non-empty JSON argv array")
    build_commit, cloud_image_digest = _validate_ready(base_url, request_fn(base_url, "GET", "/ready"))
    token = _login(request_fn, base_url, username, password)
    session = request_fn(
        base_url,
        "POST",
        "/v1/cloud/sessions",
        token=token,
        payload={"kind": "cloud_native", "title": "first-batch C-03 restart verification"},
    )
    session_id = session.get("id") if isinstance(session, dict) else None
    if not isinstance(session_id, str):
        raise VerificationError("C-03 session creation failed")
    challenge_a, challenge_b = challenges or (
        f"NMC03A{uuid.uuid4().hex.upper()}",
        f"NMC03B{uuid.uuid4().hex.upper()}",
    )
    request_prompts = {
        f"first-batch-c03-{uuid.uuid4()}": f"Reply with this code verbatim: {challenge_a}",
        f"first-batch-c03-{uuid.uuid4()}": f"Reply with this code verbatim: {challenge_b}",
    }
    request_ids = set(request_prompts)
    submission_errors: list[str] = []

    def submit(request_id: str, prompt: str) -> None:
        try:
            request_fn(
                base_url,
                "POST",
                f"/v1/cloud/sessions/{session_id}/commands",
                token=token,
                payload={"request_id": request_id, "input": prompt},
                timeout_seconds=max(30.0, min(timeout, 300.0)),
            )
        except Exception as exc:
            submission_errors.append(type(exc).__name__)

    threads = [threading.Thread(target=submit, args=item, daemon=True) for item in request_prompts.items()]
    for thread in threads:
        thread.start()
    try:
        def command_probe() -> dict[str, dict[str, Any]]:
            listed = request_fn(base_url, "GET", f"/v1/cloud/sessions/{session_id}/commands?after=0&limit=10", token=token)
            return _commands_by_request_id(listed, request_ids)

        before = _wait_for(
            command_probe,
            lambda rows: isinstance(rows, dict)
            and len(rows) == 2
            and sorted(row.get("status") for row in rows.values()) == ["queued", "running"],
            "one running and one queued Cloud command",
            timeout,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
        running = next(row for row in before.values() if row.get("status") == "running")
        queued = next(row for row in before.values() if row.get("status") == "queued")
        if running.get("attempt_count") != 1 or queued.get("attempt_count") != 0:
            raise VerificationError("pre-restart command attempts do not prove a single active worker")
        running_id = running.get("id")
        queued_id = queued.get("id")
        if not isinstance(running_id, str) or not isinstance(queued_id, str):
            raise VerificationError("pre-restart command ids are invalid")
        queued_request_id = str(queued["request_id"])
        queued_challenge = challenge_a if challenge_a in request_prompts[queued_request_id] else challenge_b

        restart_fn(restart_command)
        _wait_for(
            lambda: request_fn(base_url, "GET", "/ready"),
            lambda ready: isinstance(ready, dict) and ready.get("ready") is True,
            "Cloud readiness after restart",
            timeout,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
        token = _login(request_fn, base_url, username, password)
        after = _wait_for(
            command_probe,
            lambda rows: isinstance(rows, dict)
            and rows.get(str(running["request_id"]), {}).get("status") == "needs_attention"
            and rows.get(queued_request_id, {}).get("status") == "queued",
            "interrupted command attention without queued replay",
            timeout,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
        interrupted_after = after[str(running["request_id"])]
        queued_after = after[queued_request_id]
        if interrupted_after.get("attempt_count") != 1 or queued_after.get("attempt_count") != 0:
            raise VerificationError("Cloud replayed a command before operator recovery")
        events = request_fn(base_url, "GET", f"/v1/cloud/sessions/{session_id}/events?after=0", token=token)
        attention = _event_for(events, "turn.needs_attention", running_id)
        if len(attention) != 1 or attention[0]["payload"].get("error", {}).get("code") != "process_restarted":
            raise VerificationError("Cloud did not emit one process_restarted needs_attention event")
        if _event_for(events, "turn.completed", running_id) or _event_for(events, "turn.failed", running_id):
            raise VerificationError("interrupted Cloud command reached another terminal before recovery")

        recovered = request_fn(
            base_url,
            "POST",
            f"/v1/cloud/sessions/{session_id}/commands/{running_id}/recover",
            token=token,
            payload={"mode": "abandon"},
        )
        if not isinstance(recovered, dict) or recovered.get("status") != "abandoned":
            raise VerificationError("operator abandon did not resolve the interrupted command")
        completed = _wait_for(
            command_probe,
            lambda rows: isinstance(rows, dict) and rows.get(queued_request_id, {}).get("status") == "completed",
            "queued command completion after abandon",
            timeout,
            sleep_fn=sleep_fn,
            monotonic_fn=monotonic_fn,
        )
        if completed[str(running["request_id"])].get("status") != "abandoned":
            raise VerificationError("interrupted command did not remain abandoned")
        if completed[str(running["request_id"])].get("attempt_count") != 1 or completed[queued_request_id].get("attempt_count") != 1:
            raise VerificationError("post-recovery command attempt counts are invalid")
        events = request_fn(base_url, "GET", f"/v1/cloud/sessions/{session_id}/events?after=0", token=token)
        if len(_event_for(events, "command.abandoned", running_id)) != 1:
            raise VerificationError("Cloud did not audit the explicit abandon decision")
        queued_terminals = [
            event for event in events
            if isinstance(event, dict)
            and event.get("event_type") in TERMINAL_EVENTS
            and isinstance(event.get("payload"), dict)
            and event["payload"].get("command_id") == queued_id
        ]
        if len(queued_terminals) != 1 or queued_terminals[0].get("event_type") != "turn.completed":
            raise VerificationError("queued Cloud command did not emit exactly one successful terminal")
        payload = queued_terminals[0]["payload"]
        if payload.get("model") != expected_model or queued_challenge not in str(payload.get("output", "")):
            raise VerificationError("queued Cloud command did not complete with the expected real Provider")
        return {
            "release_checks": {"c_03": "PASS"},
            "base_url": base_url.rstrip("/"),
            "build_commit": build_commit,
            "cloud_image_digest": cloud_image_digest,
            "model": expected_model,
            "session_id_sha256": hashlib.sha256(session_id.encode()).hexdigest(),
            "interrupted_command_sha256": hashlib.sha256(running_id.encode()).hexdigest(),
            "queued_command_sha256": hashlib.sha256(queued_id.encode()).hexdigest(),
            "queued_challenge_sha256": hashlib.sha256(queued_challenge.encode()).hexdigest(),
            "restart_command_sha256": hashlib.sha256(json.dumps(list(restart_command), separators=(",", ":")).encode()).hexdigest(),
            "interrupted_status_before": "running",
            "interrupted_status_after_restart": "needs_attention",
            "interrupted_status_after_recovery": "abandoned",
            "interrupted_attempt_count": 1,
            "queued_status_before": "queued",
            "queued_status_after_restart": "queued",
            "queued_status_after_recovery": "completed",
            "queued_attempt_count": 1,
            "terminal_event": "turn.completed",
        }
    finally:
        for thread in threads:
            thread.join(timeout=0.1)
        try:
            request_fn(base_url, "POST", f"/v1/cloud/sessions/{session_id}/archive", token=token, payload={})
        except Exception:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("NOTEMELD_CLOUD_BASE_URL"))
    parser.add_argument("--username", default=os.environ.get("NOTEMELD_CLOUD_ADMIN_USERNAME"))
    parser.add_argument("--password", default=os.environ.get("NOTEMELD_CLOUD_ADMIN_PASSWORD"))
    parser.add_argument("--expected-model", default=os.environ.get("NOTEMELD_EXPECTED_CLOUD_MODEL"))
    parser.add_argument("--restart-command-json", required=True, help="JSON argv array; executed directly without a shell")
    parser.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    if not args.base_url or not args.username or not args.password or not args.expected_model:
        parser.error("Cloud URL, account credentials, and expected model are required")
    try:
        restart_command = json.loads(args.restart_command_json)
        if not isinstance(restart_command, list):
            raise VerificationError("restart command must be a JSON array")
        result = run(args.base_url, args.username, args.password, args.expected_model, restart_command, args.timeout)
    except (json.JSONDecodeError, VerificationError, KeyError, TypeError) as exc:
        print(f"first-batch C-03 verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
