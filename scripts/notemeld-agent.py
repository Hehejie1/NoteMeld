#!/usr/bin/env python3
"""Small host client used by ``notemeld agent`` until the native CLI artifact is installed."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any


BASE = f"http://127.0.0.1:{os.getenv('NOTEMELD_BACKEND_PORT', '8483')}/api/agent/v1"
EVENT_POLL_TIMEOUT_SECONDS = 30.0
EVENT_POLL_INTERVAL_SECONDS = 0.1
TERMINAL_EVENT_TYPES = frozenset({"turn.succeeded", "turn.failed", "turn.interrupted", "turn.cancelled"})
TERMINAL_STATUSES = frozenset({"succeeded", "failed", "interrupted", "cancelled"})


def request(method: str, path: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(detail[:400]) from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError("agent request connection failed") from error


def _event_batch(turn_id: str, after_sequence: int) -> list[dict[str, Any]]:
    event_path = f"/turns/{turn_id}/events"
    if after_sequence >= 0:
        event_path += f"?after_sequence={after_sequence}"
    req = urllib.request.Request(
        BASE + event_path,
        method="GET",
        headers={"Accept": "text/event-stream"},
    )
    values: list[dict[str, Any]] = []
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            for raw in response.read().decode().split("\n\n"):
                data = next((line[6:] for line in raw.splitlines() if line.startswith("data: ")), None)
                if data:
                    values.append(json.loads(data))
    except urllib.error.HTTPError as error:
        raise RuntimeError("agent event request failed") from error
    except (urllib.error.URLError, TimeoutError, OSError) as error:
        raise RuntimeError("agent event connection failed") from error
    return values


def events(turn_id: str) -> list[dict[str, Any]]:
    """Replay a turn and return its event envelopes.

    The API is the only source of truth for CLI output.  Keeping replay and
    rendering separate also makes the machine-readable modes deterministic and
    prevents progress text from leaking into JSON stdout.
    """
    result: list[dict[str, Any]] = []
    seen_sequences: set[int] = set()
    after_sequence = -1
    deadline = time.monotonic() + EVENT_POLL_TIMEOUT_SECONDS

    def collect(values: list[dict[str, Any]]) -> bool:
        nonlocal after_sequence
        terminal = False
        for value in values:
            try:
                sequence = int(value.get("sequence", -1))
            except (TypeError, ValueError):
                sequence = -1
            if sequence >= 0:
                if sequence in seen_sequences:
                    continue
                seen_sequences.add(sequence)
                after_sequence = max(after_sequence, sequence)
            result.append(value)
            terminal = terminal or value.get("type") in TERMINAL_EVENT_TYPES
        return terminal

    while True:
        if collect(_event_batch(turn_id, after_sequence)):
            return result

        try:
            turn = unwrap(request("GET", f"/turns/{turn_id}"))
        except (RuntimeError, KeyError, TypeError) as error:
            raise RuntimeError("agent turn status request failed") from error
        if isinstance(turn, dict) and str(turn.get("status", "")).lower() in TERMINAL_STATUSES:
            # A terminal status can become visible just before its journal
            # event. Replay once more at the current cursor before falling
            # back to a synthetic terminal envelope.
            if collect(_event_batch(turn_id, after_sequence)):
                return result
            status = str(turn.get("status", "")).lower()
            terminal_type = f"turn.{status}"
            payload: dict[str, Any] = {}
            if turn.get("error_code") or turn.get("error_message"):
                payload["error"] = {
                    "code": turn.get("error_code") or "agent_turn_failed",
                    "message": turn.get("error_message") or "Agent turn failed",
                }
            result.append({"sequence": after_sequence + 1, "type": terminal_type, "payload": payload})
            return result
        if time.monotonic() >= deadline:
            raise RuntimeError("timed out waiting for agent turn")
        time.sleep(EVENT_POLL_INTERVAL_SECONDS)


def render_events(values: list[dict[str, Any]], output_format: str) -> None:
    if output_format == "jsonl":
        for value in values:
            print(json.dumps(value, ensure_ascii=False))
        return
    if output_format == "json":
        print(json.dumps(values, ensure_ascii=False))
        return
    for value in values:
        event_type = value.get("type", "event")
        payload = value.get("payload", {})
        if event_type == "message.delta":
            print(payload.get("delta", ""), end="", flush=True)
        elif event_type.startswith("turn."):
            print(f"\n[{event_type}]")


def unwrap(value: dict[str, Any]) -> Any:
    return value.get("data", value)


def create_session() -> str:
    value = unwrap(request("POST", "/sessions", {"title": "CLI Agent"}))
    return str(value["id"])


def print_value(value: Any, output_format: str) -> None:
    if output_format == "jsonl":
        if isinstance(value, list):
            for item in value:
                print(json.dumps(item, ensure_ascii=False))
        else:
            print(json.dumps(value, ensure_ascii=False))
    elif output_format == "json":
        print(json.dumps(value, ensure_ascii=False))
    else:
        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    print(f"{item.get('id', '')}\t{item.get('title', '')}")
                else:
                    print(item)
        else:
            print(value)


def submit_turn(session: str, text: str, model: str | None, output_format: str) -> None:
    payload: dict[str, Any] = {"input": text}
    if model:
        payload["model"] = model
    turn = unwrap(request("POST", f"/sessions/{session}/turns", payload))
    render_events(events(str(turn["turn_id"])), output_format)


def main() -> int:
    parser = argparse.ArgumentParser(prog="notemeld-agent")
    parser.add_argument("-p", "--prompt", dest="prompt", help="submit one prompt and exit")
    parser.add_argument("--conversation", "--session", dest="session", help="conversation/session ID to resume")
    parser.add_argument("--model", help="override the saved Agent model for this session")
    parser.add_argument("--output", "--format", dest="output_format", choices=("text", "json", "jsonl"), default="text")
    parser.add_argument("positional_prompt", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args()
    prompt = args.prompt if args.prompt is not None else args.positional_prompt
    session = args.session or create_session()
    if prompt:
        submit_turn(session, prompt, args.model, args.output_format)
        return 0

    if args.output_format == "text":
        print(f"NoteMeld Agent session: {session}")
        print("输入 /exit 退出；/new 新建会话；/resume ID 继续会话；/sessions 查看会话；/model NAME 切换模型。")
    model = args.model
    while True:
        try:
            text = input("agent> ").strip()
        except EOFError:
            print()
            return 0
        if not text:
            continue
        if text == "/exit":
            return 0
        if text == "/new":
            session = create_session()
            if args.output_format == "text":
                print(f"session: {session}")
            else:
                print_value({"type": "session.created", "id": session}, args.output_format)
            continue
        if text == "/sessions":
            try:
                print_value(unwrap(request("GET", "/sessions")), args.output_format)
            except RuntimeError as error:
                print(f"error: {error}", file=sys.stderr)
            continue
        if text == "/model" or text.startswith("/model "):
            requested = text[6:].strip()
            try:
                if requested:
                    preference = unwrap(request("PUT", f"/sessions/{session}/model-preference", {"default_model_id": requested, "fallback_models": []}))
                    model = requested
                else:
                    preference = unwrap(request("GET", f"/sessions/{session}/model-preference"))
                    model = preference.get("default_model_id") if isinstance(preference, dict) else model
                print_value({"type": "model", "model": model, "preference": preference}, args.output_format)
            except RuntimeError as error:
                print(f"error: {error}", file=sys.stderr)
            continue
        if text.startswith("/resume "):
            requested = text[8:].strip()
            if not requested:
                print("error: /resume requires a session ID", file=sys.stderr)
                continue
            try:
                request("GET", f"/sessions/{requested}")
                session = requested
                if args.output_format == "text":
                    print(f"session: {session}")
                else:
                    print_value({"type": "session.resumed", "id": session}, args.output_format)
            except RuntimeError as error:
                print(f"error: {error}", file=sys.stderr)
            continue
        if text == "/cancel":
            print("当前 CLI turn 已由同步事件回放完成；如需取消，请通过 Agent v1 API 提交 cancel。", file=sys.stderr)
            continue
        try:
            submit_turn(session, text, model, args.output_format)
            if args.output_format == "text":
                print()
        except RuntimeError as error:
            print(f"error: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
