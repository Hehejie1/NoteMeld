#!/usr/bin/env python3
"""Small host client used by ``notemeld agent`` until the native CLI artifact is installed."""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import time
import urllib.error
import urllib.request
from typing import Any, Callable


BASE = f"http://127.0.0.1:{os.getenv('NOTEMELD_BACKEND_PORT', '8483')}/api/agent/v1"
EVENT_POLL_TIMEOUT_SECONDS = 30.0
EVENT_POLL_INTERVAL_SECONDS = 0.5
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
        with urllib.request.urlopen(req, timeout=EVENT_POLL_TIMEOUT_SECONDS) as response:
            if not hasattr(response, "readline"):
                frames = response.read().decode().split("\n\n")
            else:
                frames = []
                frame: list[str] = []
                while True:
                    raw_line = response.readline()
                    if not raw_line:
                        if frame:
                            frames.append("\n".join(frame))
                        break
                    line = raw_line.decode(errors="replace").rstrip("\r\n")
                    if line:
                        frame.append(line)
                        continue
                    if not frame:
                        continue
                    current = "\n".join(frame)
                    frames.append(current)
                    frame = []
                    data = next((item[6:] for item in current.splitlines() if item.startswith("data: ")), None)
                    if data:
                        try:
                            event = json.loads(data)
                        except json.JSONDecodeError:
                            event = {}
                        if event.get("type") in TERMINAL_EVENT_TYPES or event.get("type") == "approval.required":
                            break
            for raw in frames:
                data = next((line[6:] for line in raw.splitlines() if line.startswith("data: ")), None)
                if data:
                    try:
                        values.append(json.loads(data))
                    except json.JSONDecodeError:
                        continue
    except urllib.error.HTTPError as error:
        raise RuntimeError("agent event request failed") from error
    except urllib.error.URLError as error:
        if isinstance(error.reason, (socket.timeout, TimeoutError)):
            return values
        raise RuntimeError("agent event connection failed") from error
    except (TimeoutError, socket.timeout, OSError) as error:
        raise RuntimeError("agent event connection failed") from error
    return values


def events(
    turn_id: str,
    *,
    after_sequence: int = -1,
    on_approval: Callable[[dict[str, Any]], None] | None = None,
) -> list[dict[str, Any]]:
    """Replay a turn and return its event envelopes.

    The API is the only source of truth for CLI output.  Keeping replay and
    rendering separate also makes the machine-readable modes deterministic and
    prevents progress text from leaking into JSON stdout.
    """
    result: list[dict[str, Any]] = []
    seen_sequences: set[int] = set()
    after_sequence = after_sequence

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
        batch = _event_batch(turn_id, after_sequence)
        if collect(batch):
            return result
        approvals = [value for value in batch if value.get("type") == "approval.required"]
        if approvals:
            if on_approval is None:
                return result
            for approval in approvals:
                on_approval(approval)
            continue

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


def create_related_note(title: str, content: str, parent_note_id: str | None, output_format: str) -> None:
    arguments: dict[str, Any] = {"title": title, "content": content}
    if parent_note_id:
        arguments["parent_note_id"] = parent_note_id
    result = unwrap(request("POST", "/capabilities/note:create", {
        "arguments": arguments,
        "actor_id": "cli",
    }))
    print_value(result, output_format)


def submit_turn(session: str, text: str, model: str | None, output_format: str, after_sequence: int = -1) -> None:
    payload: dict[str, Any] = {"input": text}
    if model:
        payload["model"] = model
    turn = unwrap(request("POST", f"/sessions/{session}/turns", payload))

    def decide(event: dict[str, Any]) -> None:
        approval = event.get("payload") if isinstance(event.get("payload"), dict) else {}
        approval_id = str(approval.get("approval_id") or "")
        if not approval_id:
            raise RuntimeError("approval event is missing approval_id")
        summary = str(approval.get("summary") or "Agent 请求执行受保护操作")
        risk = str(approval.get("risk") or "unknown")
        approved = input(f"\n{summary}（风险：{risk}）\n批准继续？[y/N] ").strip().lower() in {"y", "yes"}
        request("POST", f"/approvals/{approval_id}", {"decision": "approve" if approved else "deny"})

    render_events(
        events(
            str(turn["turn_id"]),
            after_sequence=after_sequence,
            on_approval=decide if output_format == "text" else None,
        ),
        output_format,
    )


def main() -> int:
    parser = argparse.ArgumentParser(prog="notemeld-agent")
    parser.add_argument("-p", "--prompt", dest="prompt", help="submit one prompt and exit")
    parser.add_argument("--after-sequence", type=int, default=-1, help="resume turn event stream from this sequence")
    parser.add_argument("--conversation", "--session", dest="session", help="conversation/session ID to resume")
    parser.add_argument("--model", help="override the saved Agent model for this session")
    parser.add_argument("--output", "--format", dest="output_format", choices=("text", "json", "jsonl"), default="text")
    parser.add_argument("--approve", metavar="APPROVAL_ID", help="approve a paused Agent turn")
    parser.add_argument("--deny", metavar="APPROVAL_ID", help="deny a paused Agent turn")
    parser.add_argument("--turn", dest="turn_id", help="continue consuming one existing turn")
    parser.add_argument("--create-note-title", help="create a Note through the Agent Host")
    parser.add_argument("--create-note-content", help="Markdown content for --create-note-title")
    parser.add_argument("--parent-note-id", help="associate the created Note with an existing Note")
    parser.add_argument("positional_prompt", nargs="?", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.approve and args.deny:
        parser.error("--approve and --deny are mutually exclusive")
    approval_id = args.approve or args.deny
    if approval_id:
        decision = "approve" if args.approve else "deny"
        resolved = unwrap(request("POST", f"/approvals/{approval_id}", {"decision": decision}))
        if not args.turn_id:
            print_value(resolved, args.output_format)
    if args.turn_id:
        render_events(events(args.turn_id, after_sequence=args.after_sequence), args.output_format)
        return 0
    if args.create_note_title:
        if not args.create_note_content:
            parser.error("--create-note-content is required with --create-note-title")
        create_related_note(args.create_note_title, args.create_note_content, args.parent_note_id, args.output_format)
        return 0
    if approval_id:
        return 0
    prompt = args.prompt if args.prompt is not None else args.positional_prompt
    session = args.session or create_session()
    if prompt:
        submit_turn(session, prompt, args.model, args.output_format, args.after_sequence)
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
            submit_turn(session, text, model, args.output_format, args.after_sequence)
            if args.output_format == "text":
                print()
        except RuntimeError as error:
            print(f"error: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
