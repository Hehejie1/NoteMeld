from __future__ import annotations

import threading


def test_native_executor_translates_sdk_events_and_completes_turn(monkeypatch):
    from app.agent_host.native_executor import NativeAgentExecutor

    events = []
    persisted = []
    finished = []

    class FakeRuntime:
        def __init__(self, *_args, driver, on_event, **_kwargs):
            self.driver = driver
            self.on_event = on_event

        def submit_turn(self, request):
            assert request["input"]["text"] == "hello"
            response = self.driver({"kind": "model.stream", "messages": [{"role": "user", "content": "hello"}]})
            assert response["ok"] is True
            self.on_event({"schema_version": "1", "type": "message.delta", "payload": {"delta": "hi"}})
            self.on_event({"schema_version": "1", "type": "turn.succeeded", "payload": {"answer": "hi"}})
            return 1

        def wait(self, _token, _timeout):
            return None

        def close(self):
            return None

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            self.close()

    class FakeSdk:
        Runtime = FakeRuntime

    class FakeModelDriver:
        def __init__(self, *_args, **_kwargs):
            pass

        async def stream(self, _request):
            return {"ok": True, "content": "hi", "tool_calls": [], "finish_reason": "stop", "usage": {}}

    monkeypatch.setattr("app.agent_host.native_executor.AgentSdkRuntime.load", lambda **_kwargs: type("Loaded", (), {"binding": FakeSdk})())
    monkeypatch.setattr("app.agent_host.native_executor.create_models", lambda: object())
    monkeypatch.setattr("app.agent_host.native_executor.NoteMeldModelDriver", FakeModelDriver)
    monkeypatch.setattr("app.agent_host.native_executor._resolve_saved_model", lambda _name: (object(), object()))
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.append_event", lambda _turn, event, **_kw: persisted.append(event))
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.transition_turn", lambda *args, **kwargs: finished.append((args, kwargs)))

    executor = NativeAgentExecutor(event_sink=events.append)
    executor.run_sync("turn-1", "session-1", "hello", model_name="demo")

    assert [event["type"] for event in events] == ["message.delta", "turn.succeeded"], finished
    assert [event["type"] for event in persisted] == ["message.delta"]
    assert finished[-1][0][1] == "succeeded"


def test_native_executor_runs_in_background(monkeypatch):
    from app.agent_host.native_executor import NativeAgentExecutor

    done = threading.Event()
    monkeypatch.setattr("app.agent_host.native_executor.NativeAgentExecutor.run_sync", lambda self, *_args, **_kwargs: done.set())
    NativeAgentExecutor().start("turn-1", "session-1", "hello", model_name="demo")
    assert done.wait(1)
