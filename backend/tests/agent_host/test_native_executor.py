from __future__ import annotations

import threading
from types import SimpleNamespace


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
            assert request["model_override"] == {
                "provider_id": "demo-provider",
                "model_name": "demo",
            }
            response = self.driver({
                "kind": "model.stream",
                "payload": {"messages": [{"role": "user", "content": "hello"}]},
            })
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

    class FakeHost:
        def submit(self, _turn_id, request, *, driver, on_event):
            self.runtime = FakeRuntime(driver=driver, on_event=on_event)
            self.runtime.submit_turn(request)
            return SimpleNamespace(token=1)

        def forget(self, _turn_id):
            return None

    class FakeModelDriver:
        def __init__(self, *_args, **_kwargs):
            pass

        async def stream(self, _request):
            assert _request["messages"] == [{"role": "user", "content": "hello"}]
            return {"ok": True, "content": "hi", "tool_calls": [], "finish_reason": "stop", "usage": {}}

    monkeypatch.setattr("app.agent_host.native_executor.get_agent_sdk_host", lambda: FakeHost())
    monkeypatch.setattr("app.agent_host.native_executor.get_conversation", lambda _session_id: {})
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.get_turn", lambda _turn_id: {"status": "running"})
    monkeypatch.setattr("app.agent_host.native_executor.create_models", lambda: object())
    monkeypatch.setattr("app.agent_host.native_executor.NoteMeldModelDriver", FakeModelDriver)
    monkeypatch.setattr(
        "app.agent_host.native_executor._resolve_saved_model",
        lambda _name: (object(), SimpleNamespace(provider_id="demo-provider", name="demo")),
    )
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.append_event", lambda _turn, event, **_kw: persisted.append(event))
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.transition_turn", lambda *args, **kwargs: finished.append((args, kwargs)))

    executor = NativeAgentExecutor(event_sink=events.append)
    executor.run_sync("turn-1", "session-1", "hello", model_name="demo")

    assert [event["type"] for event in events] == ["message.delta", "turn.succeeded"], finished
    assert [event["type"] for event in persisted] == ["message.delta"]
    assert finished[-1][0][1] == "succeeded"


def test_native_executor_routes_tool_calls_to_product_driver(monkeypatch):
    from app.agent_host.native_executor import NativeAgentExecutor

    requested = []
    finished = []

    class FakeRuntime:
        def __init__(self, *_args, driver, on_event, **_kwargs):
            self.driver = driver
            self.on_event = on_event

        def submit_turn(self, _request):
            result = self.driver({
                "kind": "tool.invoke",
                "payload": {
                    "call_id": "call-1",
                    "tool_name": "wiki:search",
                    "arguments": {"query": "agent"},
                    "session_id": "session-1",
                    "turn_id": "turn-1",
                },
            })
            assert result == {"schema_version": "1", "ok": True, "result": {"output": {"items": []}}}
            self.on_event({"schema_version": "1", "type": "turn.succeeded", "payload": {}})
            return 1

        def wait(self, _token, _timeout):
            return None

    class FakeHost:
        def submit(self, _turn_id, _request, *, driver, on_event):
            self.runtime = FakeRuntime(driver=driver, on_event=on_event)
            self.runtime.submit_turn(_request)
            return SimpleNamespace(token=1)

        def forget(self, _turn_id):
            return None

    class FakeToolDriver:
        async def invoke(self, call, context, on_progress=None):
            requested.append((call, context))
            return {"items": []}

    monkeypatch.setattr("app.agent_host.native_executor.get_agent_sdk_host", lambda: FakeHost())
    monkeypatch.setattr("app.agent_host.native_executor.get_conversation", lambda _session_id: {})
    monkeypatch.setattr(
        "app.agent_host.native_executor._resolve_saved_model",
        lambda _name: (object(), SimpleNamespace(provider_id="demo-provider", name="demo")),
    )
    monkeypatch.setattr("app.agent_host.native_executor.NoteMeldModelDriver", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.get_turn", lambda _turn_id: {"status": "running"})
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.transition_turn", lambda *args, **kwargs: finished.append((args, kwargs)))

    executor = NativeAgentExecutor(tool_driver=FakeToolDriver())
    executor.run_sync("turn-1", "session-1", "hello", model_name="demo")

    assert requested == [({
        "call_id": "call-1",
        "tool_name": "wiki:search",
        "arguments": {"query": "agent"},
    }, {"session_id": "session-1", "turn_id": "turn-1"})]
    assert finished[-1][0][1] == "succeeded"




def test_native_executor_runs_in_background(monkeypatch):
    from app.agent_host.native_executor import NativeAgentExecutor

    done = threading.Event()
    monkeypatch.setattr("app.agent_host.native_executor.NativeAgentExecutor.run_sync", lambda self, *_args, **_kwargs: done.set())
    NativeAgentExecutor().start("turn-1", "session-1", "hello", model_name="demo")
    assert done.wait(1)
