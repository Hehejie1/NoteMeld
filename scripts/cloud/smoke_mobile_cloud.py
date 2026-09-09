#!/usr/bin/env python3
"""Run the mobile Cloud-native session contract against a live Cloud server.

This intentionally uses only the Python standard library so it can run from CI,
an Android/iOS integration shell, or a developer machine without test-only
dependencies. It verifies the same HTTP sequence used by the native clients:
login -> create session -> submit command -> read command/events -> snapshot.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
import uuid
from typing import Any


def request(base_url: str, method: str, path: str, token: str | None = None, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=10) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"{method} {path} returned HTTP {exc.code}: {detail[:300]}") from exc
    if path == "/ready" and isinstance(decoded, dict):
        return decoded
    if not isinstance(decoded, dict) or decoded.get("code") != 0:
        raise RuntimeError(f"{method} {path} returned an invalid API envelope")
    return decoded


def run(base_url: str, username: str, password: str, timeout: float) -> dict[str, Any]:
    ready = request(base_url, "GET", "/ready")
    login = request(base_url, "POST", "/v1/auth/login", payload={"username": username, "password": password})
    token = login["data"]["token"]
    device_id = f"mobile-smoke-{uuid.uuid4()}"
    request(
        base_url,
        "POST",
        "/v1/devices/register",
        token=token,
        payload={"device_id": device_id, "platform": "smoke", "display_name": "NoteMeld mobile smoke"},
    )
    request(base_url, "POST", f"/v1/devices/{device_id}/heartbeat", token=token, payload={})
    session = request(base_url, "POST", "/v1/sessions", token=token, payload={"kind": "cloud_native", "title": "mobile smoke"})["data"]
    request_id = f"mobile-smoke-{uuid.uuid4()}"
    submitted = request(
        base_url,
        "POST",
        f"/v1/sessions/{session['id']}/commands",
        token=token,
        payload={"request_id": request_id, "input": "mobile cloud contract smoke"},
    )["data"]

    deadline = time.monotonic() + timeout
    command = submitted
    while command.get("status") not in {"completed", "failed", "cancelled", "needs_attention"}:
        if time.monotonic() >= deadline:
            raise RuntimeError(f"command {submitted.get('command_id')} did not reach a terminal state")
        time.sleep(0.05)
        command = request(base_url, "GET", f"/v1/sessions/{session['id']}/commands/{submitted['command_id']}", token=token)["data"]
    if command["status"] != "completed":
        raise RuntimeError(f"mobile smoke command ended in {command['status']}")

    events = request(base_url, "GET", f"/v1/sessions/{session['id']}/events?after=0", token=token)["data"]
    snapshot = request(base_url, "GET", f"/v1/sessions/{session['id']}/snapshot", token=token)["data"]
    if not events or snapshot["snapshot_seq"] < events[-1]["sequence"]:
        raise RuntimeError("event stream and snapshot sequence are inconsistent")
    event_types = [event["event_type"] for event in events]
    if "turn.completed" not in event_types:
        raise RuntimeError(f"turn.completed is missing from event stream: {event_types}")
    return {
        "ready": ready,
        "device_id": device_id,
        "session_id": session["id"],
        "command_status": command["status"],
        "snapshot_seq": snapshot["snapshot_seq"],
        "event_types": event_types,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("NOTEMELD_CLOUD_BASE_URL", "http://127.0.0.1:8583"))
    parser.add_argument("--username", default=os.environ.get("NOTEMELD_CLOUD_ADMIN_USERNAME", "hehejie"))
    parser.add_argument("--password", default=os.environ.get("NOTEMELD_CLOUD_ADMIN_PASSWORD"))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()
    if not args.password:
        parser.error("--password or NOTEMELD_CLOUD_ADMIN_PASSWORD is required")
    try:
        result = run(args.base_url, args.username, args.password, args.timeout)
    except (OSError, RuntimeError, KeyError, json.JSONDecodeError) as exc:
        print(f"cloud mobile smoke failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
