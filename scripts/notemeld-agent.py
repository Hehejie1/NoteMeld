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


def request(method: str, path: str, payload: dict | None = None) -> dict:
    body = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(BASE + path, data=body, method=method, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            return json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        detail = error.read().decode(errors="replace")
        raise RuntimeError(detail[:400]) from error


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
    parser.add_argument("--session")
    parser.add_argument("--format", choices=("text", "json", "jsonl"), default="text")
    parser.add_argument("prompt", nargs="?")
    args = parser.parse_args()
    session = args.session or request("POST", "/sessions", {"title": "CLI Agent"})["data"]["id"]
    if args.prompt:
        turn = request("POST", f"/sessions/{session}/turns", {"input": args.prompt})["data"]
        events(turn["turn_id"], args.format)
        return 0
    print(f"NoteMeld Agent session: {session}")
    print("输入 /exit 退出；/new 新建会话；其它内容提交到当前会话。")
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
        try:
            turn = request("POST", f"/sessions/{session}/turns", {"input": text})["data"]
            events(turn["turn_id"], args.format)
            if args.format == "text":
                print()
        except RuntimeError as error:
            print(f"error: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
