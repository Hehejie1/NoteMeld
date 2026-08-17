from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


class _AgentHandler(BaseHTTPRequestHandler):
    paths: list[str] = []

    def log_message(self, *_args):
        return

    def _json(self, payload: dict, status: int = 200):
        raw = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def do_POST(self):  # noqa: N802
        self.paths.append(self.path)
        if self.path.endswith("/sessions"):
            self._json({"code": "ok", "data": {"id": "session-cli"}})
        elif self.path.endswith("/turns"):
            self._json({"code": "ok", "data": {"turn_id": "turn-cli", "session_id": "session-cli"}})
        else:
            self._json({"code": "not_found"}, 404)

    def do_GET(self):  # noqa: N802
        self.paths.append(self.path)
        if self.path.endswith("/events"):
            body = (
                'id: 0\nevent: message.delta\ndata: {"type":"message.delta","payload":{"delta":"smoke"}}\n\n'
                'id: 1\nevent: turn.succeeded\ndata: {"type":"turn.succeeded","payload":{}}\n\n'
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            self._json({"code": "not_found"}, 404)


def test_product_cli_runs_one_shot_against_agent_v1_only(tmp_path):
    _AgentHandler.paths = []
    server = ThreadingHTTPServer(("127.0.0.1", 0), _AgentHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        root = Path(__file__).parents[3]
        env = {
            **os.environ,
            "NOTEMELD_BACKEND_PORT": str(server.server_port),
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        }
        result = subprocess.run(
            [sys.executable, str(root / "scripts/notemeld-agent.py"), "--format", "jsonl", "hello"],
            cwd=root,
            env=env,
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    finally:
        server.shutdown()
        thread.join(timeout=2)

    assert result.returncode == 0, result.stderr
    assert "smoke" in result.stdout
    assert all("/chat/" not in path for path in _AgentHandler.paths)
    assert any(path.endswith("/sessions") for path in _AgentHandler.paths)
    assert any(path.endswith("/turns") for path in _AgentHandler.paths)
    assert any(path.endswith("/events") for path in _AgentHandler.paths)
