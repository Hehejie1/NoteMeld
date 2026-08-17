#!/usr/bin/env python3
"""Small host client used by ``notemeld agent`` until the native CLI artifact is installed."""

from __future__ import annotations

import json
import os
import sys
import argparse
import urllib.error
import urllib.request


BASE = f"http://127.0.0.1:{os.getenv('NOTEMELD_BACKEND_PORT', '8483')}/api/agent/v1"
API_BASE = BASE.removesuffix("/agent/v1")


def request(method: str, path: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    root = API_BASE if path.startswith("/model_list") else BASE
    req = urllib.request.Request(root + path, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(detail[:400]) from error


def model_list() -> list[dict]:
    """Read the product model catalog without opening SQLite from the CLI."""
    value = request("GET", "/model_list")
    data = value.get("data", value)
    return data if isinstance(data, list) else []


def events(turn_id: str, output_format: str) -> None:
    req = urllib.request.Request(BASE + f"/turns/{turn_id}/events", method="GET", headers={"Accept": "text/event-stream"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            for raw in response.read().decode().split("\n\n"):
                data = next((line[6:] for line in raw.splitlines() if line.startswith("data: ")), None)
                if not data:
                    continue
                value = json.loads(data)
                if output_format == "jsonl":
                    print(json.dumps(value, ensure_ascii=False))
                elif output_format == "json":
                    print(json.dumps(value, ensure_ascii=False))
                else:
                    event_type = value.get("type", "event")
                    payload = value.get("payload", {})
                    if event_type == "message.delta":
                        print(payload.get("delta", ""), end="", flush=True)
                    elif event_type.startswith("turn."):
                        print(f"\n[{event_type}]")
    except urllib.error.HTTPError as error:
        raise RuntimeError(error.read().decode(errors="replace")[:400]) from error


def main() -> int:
    parser = argparse.ArgumentParser(prog="notemeld-agent")
    parser.add_argument("--session", help="resume an existing conversation/session")
    parser.add_argument("--model", help="model override for this turn")
    parser.add_argument("--format", choices=("text", "json", "jsonl"), default="text")
    parser.add_argument("prompt", nargs="?")
    args = parser.parse_args()
    session = args.session or request("POST", "/sessions", {"title": "CLI Agent"})["data"]["id"]
    current_turn: str | None = None

    def submit(text: str) -> None:
        nonlocal current_turn
        payload: dict[str, object] = {"input": text}
        if args.model:
            payload["model"] = args.model
        turn = request("POST", f"/sessions/{session}/turns", payload)["data"]
        current_turn = str(turn["turn_id"])
        try:
            events(current_turn, args.format)
        finally:
            current_turn = None

    if args.prompt:
        submit(args.prompt)
        return 0
    print(f"NoteMeld Agent session: {session}")
    print("输入 /exit 退出；/new 新建会话；/resume <id> 恢复；/sessions 会话列表；/models 模型列表；/model <name> 切换；/cancel 取消当前轮。")
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
            session = request("POST", "/sessions", {"title": "CLI Agent"})["data"]["id"]
            print(f"session: {session}")
            continue
        if text == "/sessions":
            value = request("GET", "/sessions").get("data", [])
            print(json.dumps(value, ensure_ascii=False) if args.format != "text" else "\n".join(f"{row.get('id')}\t{row.get('title', '')}" for row in value))
            continue
        if text == "/models":
            value = request("GET", "/model_list").get("data", [])
            print(json.dumps(value, ensure_ascii=False) if args.format != "text" else "\n".join(str(row.get('model_name', row)) for row in value))
            continue
        if text.startswith("/model"):
            _, _, selected = text.partition(" ")
            if not selected.strip():
                print(f"model: {args.model or '(server default)'}")
            else:
                args.model = selected.strip()
                print(f"model: {args.model}")
            continue
        if text.startswith("/resume "):
            candidate = text.split(None, 1)[1].strip()
            request("GET", f"/sessions/{candidate}")
            session = candidate
            print(f"session: {session}")
            continue
        if text == "/cancel":
            if current_turn is None:
                print("当前没有运行中的 turn", file=sys.stderr)
            else:
                request("POST", f"/turns/{current_turn}/cancel")
            continue
        try:
            submit(text)
            if args.format == "text":
                print()
        except RuntimeError as error:
            print(f"error: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
