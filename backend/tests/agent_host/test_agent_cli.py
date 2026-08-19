from __future__ import annotations

import importlib.util
import json
from pathlib import Path


SCRIPT = Path(__file__).parents[3] / "scripts" / "notemeld-agent.py"
SPEC = importlib.util.spec_from_file_location("notemeld_agent_cli", SCRIPT)
assert SPEC and SPEC.loader
cli = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cli)


def test_one_shot_uses_agent_api_and_keeps_jsonl_stdout(monkeypatch, capsys):
    calls: list[tuple[str, str, dict | None]] = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if path == "/sessions/s-1/turns":
            return {"data": {"turn_id": "turn-1"}}
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(cli, "request", fake_request)
    monkeypatch.setattr(
        cli,
        "events",
        lambda turn_id, **_kwargs: [{"type": "message.delta", "payload": {"delta": "ok"}}, {"type": "turn.succeeded", "payload": {}}],
    )

    monkeypatch.setattr(cli.sys, "argv", ["notemeld-agent", "-p", "hello", "--conversation", "s-1", "--model", "gemma3:4b", "--output", "jsonl"])
    assert cli.main() == 0

    assert calls == [("POST", "/sessions/s-1/turns", {"input": "hello", "model": "gemma3:4b"})]
    lines = capsys.readouterr().out.splitlines()
    assert [json.loads(line)["type"] for line in lines] == ["message.delta", "turn.succeeded"]
    assert "NoteMeld Agent session" not in capsys.readouterr().err


def test_positional_prompt_remains_compatible_and_json_is_a_single_document(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(cli, "create_session", lambda: "created")

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        return {"data": {"turn_id": "turn-2"}}

    monkeypatch.setattr(cli, "request", fake_request)
    monkeypatch.setattr(cli, "events", lambda turn_id, **_kwargs: [{"type": "turn.succeeded", "payload": {"answer": "done"}}])
    monkeypatch.setattr(cli.sys, "argv", ["notemeld-agent", "hello", "--format", "json"])

    assert cli.main() == 0
    assert calls == [("POST", "/sessions/created/turns", {"input": "hello"})]
    assert json.loads(capsys.readouterr().out) == [{"type": "turn.succeeded", "payload": {"answer": "done"}}]


def test_repl_supports_session_and_model_commands(monkeypatch, capsys):
    calls: list[tuple[str, str, dict | None]] = []
    inputs = iter(["/new", "/resume resumed", "/sessions", "/model", "/model qwen2:latest", "/exit"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(inputs))

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if method == "POST" and path == "/sessions":
            return {"data": {"id": "new-session"}}
        if method == "GET" and path == "/sessions/resumed":
            return {"data": {"id": "resumed"}}
        if method == "GET" and path == "/sessions":
            return {"data": [{"id": "resumed", "title": "Saved"}]}
        if method == "GET" and path.endswith("/model-preference"):
            return {"data": {"default_model_id": "gemma3:4b", "fallback_models": []}}
        if method == "PUT" and path.endswith("/model-preference"):
            return {"data": {"default_model_id": payload["default_model_id"], "fallback_models": []}}
        raise AssertionError((method, path, payload))

    monkeypatch.setattr(cli, "request", fake_request)
    monkeypatch.setattr(cli.sys, "argv", ["notemeld-agent", "--conversation", "initial", "--output", "jsonl"])

    assert cli.main() == 0
    assert calls == [
        ("POST", "/sessions", {"title": "CLI Agent"}),
        ("GET", "/sessions/resumed", None),
        ("GET", "/sessions", None),
        ("GET", "/sessions/resumed/model-preference", None),
        ("PUT", "/sessions/resumed/model-preference", {"default_model_id": "qwen2:latest", "fallback_models": []}),
    ]
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert output[0] == {"type": "session.created", "id": "new-session"}
    assert output[1] == {"type": "session.resumed", "id": "resumed"}
    assert output[2] == {"id": "resumed", "title": "Saved"}
    assert [item["type"] for item in output[3:]] == ["model", "model"]


def test_events_poll_empty_replay_then_delta_and_terminal_without_real_sleep(monkeypatch):
    class FakeResponse:
        def __init__(self, body: str):
            self.body = body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.body

    batches = [
        "",
        'id: 0\nevent: message.delta\ndata: {"sequence": 0, "type": "message.delta", "payload": {"delta": "hi"}}\n\n',
        'id: 0\nevent: message.delta\ndata: {"sequence": 0, "type": "message.delta", "payload": {"delta": "hi"}}\n\n'
        'id: 1\nevent: turn.succeeded\ndata: {"sequence": 1, "type": "turn.succeeded", "payload": {}}\n\n',
    ]
    urls: list[str] = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        return FakeResponse(batches.pop(0))

    statuses = iter(["running", "running"])
    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(cli, "request", lambda method, path, payload=None: {"data": {"status": next(statuses)}})
    monkeypatch.setattr(cli.time, "sleep", lambda _seconds: None)

    values = cli.events("turn-1")

    assert [value["type"] for value in values] == ["message.delta", "turn.succeeded"]
    assert "after_sequence=-1" not in urls[0]
    assert "after_sequence=0" in urls[2]


def test_events_replays_terminal_after_terminal_status_race(monkeypatch):
    class FakeResponse:
        def __init__(self, body: str):
            self.body = body.encode()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return self.body

    batches = [
        "",
        'id: 0\nevent: turn.succeeded\ndata: {"sequence": 0, "type": "turn.succeeded", "payload": {"answer": "done"}}\n\n',
    ]
    urls: list[str] = []

    def fake_urlopen(request, timeout):
        urls.append(request.full_url)
        return FakeResponse(batches.pop(0))

    monkeypatch.setattr(cli.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(cli, "request", lambda method, path, payload=None: {"data": {"status": "succeeded"}})

    values = cli.events("turn-race")

    assert values == [{"sequence": 0, "type": "turn.succeeded", "payload": {"answer": "done"}}]
    assert len(urls) == 2
    assert all("after_sequence=-1" not in url for url in urls)


def test_event_batch_returns_immediately_at_approval_pause(monkeypatch):
    class StreamingResponse:
        def __init__(self):
            self.lines = iter([
                b'id: 0\n',
                b'event: approval.required\n',
                b'data: {"sequence":0,"type":"approval.required","payload":{"approval_id":"approval-1"}}\n',
                b'\n',
                b'id: 1\n',
                b'event: turn.succeeded\n',
                b'data: {"sequence":1,"type":"turn.succeeded","payload":{}}\n',
                b'\n',
            ])

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def readline(self):
            return next(self.lines, b'')

    monkeypatch.setattr(cli.urllib.request, "urlopen", lambda *_args, **_kwargs: StreamingResponse())
    values = cli._event_batch("turn-1", -1)
    assert [value["type"] for value in values] == ["approval.required"]


def test_text_cli_resolves_approval_and_continues_same_turn(monkeypatch, capsys):
    calls = []

    def fake_request(method, path, payload=None):
        calls.append((method, path, payload))
        if path == "/sessions/s-1/turns":
            return {"data": {"turn_id": "turn-1"}}
        if path == "/approvals/approval-1":
            return {"data": {"accepted": True}}
        raise AssertionError((method, path, payload))

    def fake_events(turn_id, *, after_sequence=-1, on_approval=None):
        assert turn_id == "turn-1"
        assert on_approval is not None
        on_approval({
            "type": "approval.required",
            "payload": {"approval_id": "approval-1", "summary": "write", "risk": "high"},
        })
        return [{"type": "turn.succeeded", "payload": {}}]

    monkeypatch.setattr(cli, "request", fake_request)
    monkeypatch.setattr(cli, "events", fake_events)
    monkeypatch.setattr("builtins.input", lambda _prompt: "y")
    cli.submit_turn("s-1", "continue", None, "text")

    assert calls == [
        ("POST", "/sessions/s-1/turns", {"input": "continue"}),
        ("POST", "/approvals/approval-1", {"decision": "approve"}),
    ]
    assert "turn.succeeded" in capsys.readouterr().out


def test_cli_can_resolve_from_another_entry_then_continue_existing_turn(monkeypatch, capsys):
    calls = []
    monkeypatch.setattr(
        cli,
        "request",
        lambda method, path, payload=None: calls.append((method, path, payload))
        or {"data": {"approval_id": "approval-1", "accepted": True}},
    )
    monkeypatch.setattr(
        cli,
        "events",
        lambda turn_id, **kwargs: [{"type": "turn.succeeded", "payload": {"turn_id": turn_id}}],
    )
    monkeypatch.setattr(
        cli.sys,
        "argv",
        ["notemeld-agent", "--approve", "approval-1", "--turn", "turn-ui", "--output", "jsonl"],
    )

    assert cli.main() == 0
    assert calls == [("POST", "/approvals/approval-1", {"decision": "approve"})]
    output = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert len(output) == 1
    assert output[-1]["payload"]["turn_id"] == "turn-ui"
