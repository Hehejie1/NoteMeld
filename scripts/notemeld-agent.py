#!/usr/bin/env python3
"""Small host client used by ``notemeld agent`` until the native CLI artifact is installed."""

from __future__ import annotations

import json
import os
import sys
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


def main() -> int:
    session = request("POST", "/sessions", {"title": "CLI Agent"})["data"]["id"]
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
            print(json.dumps(turn, ensure_ascii=False))
        except RuntimeError as error:
            print(f"error: {error}", file=sys.stderr)


if __name__ == "__main__":
    raise SystemExit(main())
