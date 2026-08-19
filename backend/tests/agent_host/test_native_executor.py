from __future__ import annotations

import threading
from types import SimpleNamespace


def test_native_executor_translates_sdk_events_and_completes_turn(monkeypatch):
    from app.agent_host.native_executor import NativeAgentExecutor

    events = []
    persisted = []
    finished = []
    captured = {}

    class FakeRuntime:
        def __init__(self, *_args, driver, on_event, **_kwargs):
            self.driver = driver
            self.on_event = on_event

        def submit_turn(self, request):
            captured["request"] = request
            assert request["input"]["text"] == "hello"
            assert request["input"]["attachments"] == [{"type": "text", "content": "ctx-asset"}]
            assert request["input"]["context_refs"] == [{"type": "whiteboard_selection"}]
            assert request["history"] == [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "previous"},
            ]
            assert request["messages"] == [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "previous"},
                {"role": "user", "content": "hello"},
            ]
            assert request["tools"] and isinstance(request["tools"][0].get("name"), str)
            assert request["input"]["tools"] == request["tools"]
            assert request["model_override"] == {
                "provider_id": "demo-provider",
                "model_name": "demo",
            }
            response = self.driver({
                "kind": "model.stream",
                "payload": {"messages": request["messages"]},
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
            assert _request["messages"] == [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "previous"},
                {"role": "user", "content": "hello"},
            ]
            assert _request["input"]["context_refs"] == [{"type": "whiteboard_selection"}]
            assert _request["context_refs"] == [{"type": "whiteboard_selection"}]
            assert _request["tools"]
            assert _request["model"] == {
                "provider_id": "demo-provider",
                "model_name": "demo",
                "context_window_tokens": 4096,
                "capabilities": {
                    "supports_vision": False,
                    "supports_stream": True,
                    "supports_tool_calling": None,
                },
            }
            assert "api_key" not in str(_request["model"]).lower()
            return {"ok": True, "content": "hi", "tool_calls": [], "finish_reason": "stop", "usage": {}}

    monkeypatch.setattr("app.agent_host.native_executor.get_agent_sdk_host", lambda: FakeHost())
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.get_turn", lambda _turn_id: {"status": "running"})
    monkeypatch.setattr("app.agent_host.native_executor.create_models", lambda: object())
    monkeypatch.setattr("app.agent_host.native_executor.NoteMeldModelDriver", FakeModelDriver)
    monkeypatch.setattr(
        "app.agent_host.native_executor._resolve_saved_model",
        lambda _name: (object(), SimpleNamespace(provider_id="demo-provider", name="demo")),
    )
    monkeypatch.setattr("app.agent_host.native_executor.append_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.agent_host.native_executor.agent_store.append_event",
        lambda _turn, event, **kwargs: persisted.append((event, kwargs)),
    )
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.transition_turn", lambda *args, **kwargs: finished.append((args, kwargs)))

    executor = NativeAgentExecutor(event_sink=events.append)
    monkeypatch.setattr(
        "app.agent_host.native_executor.ConversationHistoryStore.load_history",
        lambda _self, _session_id: [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "previous"},
        ],
    )
    executor.run_sync("turn-1", "session-1", "hello", model_name="demo", asset_content="ctx-asset", context_refs=[{"type": "whiteboard_selection"}])

    assert [event["type"] for event in events] == ["message.delta", "turn.succeeded"], finished
    assert [kwargs["event_type"] for _event, kwargs in persisted] == ["message.delta"]
    assert persisted[0][0] == {"delta": "hi"}
    assert finished[-1][0][1] == "succeeded"
    assert captured["request"]["history"] == [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "previous"},
    ]


def test_native_executor_loads_async_tool_descriptors_when_tool_driver_not_provided(monkeypatch):
    from app.agent_host.native_executor import NativeAgentExecutor

    calls = []
    descriptors_seen = {}

    class FakeRuntime:
        def __init__(self, *_args, driver, on_event, **_kwargs):
            self.driver = driver
            self.on_event = on_event

        def submit_turn(self, request):
            descriptors_seen["request"] = request
            assert isinstance(request.get("tools"), list) and request["tools"], "tools should be discovered before submit"
            tool_names = [item.get("name") for item in request.get("tools", [])]
            assert "article_lookup" in tool_names or any(item.startswith("knowledge:") for item in tool_names if isinstance(item, str))
            response = self.driver({
                "kind": "model.stream",
                "payload": {"messages": request["messages"], "tools": request["tools"]},
            })
            assert response["ok"] is True
            self.on_event({"schema_version": "1", "type": "turn.succeeded", "payload": {}})
            return 1

        def wait(self, _token, _timeout):
            return None

    class FakeHost:
        def submit(self, _turn_id, request, *, driver, on_event):
            self.runtime = FakeRuntime(driver=driver, on_event=on_event)
            self.runtime.submit_turn(request)
            return type("Token", (), {"token": 1})

        def forget(self, _turn_id):
            return None

    class FakeModelDriver:
        def __init__(self, *_args, **_kwargs):
            pass

        async def stream(self, request):
            calls.append(request)
            return {"ok": True, "content": "", "tool_calls": [], "finish_reason": "stop", "usage": {}}

    monkeypatch.setattr("app.agent_host.native_executor.get_agent_sdk_host", lambda: FakeHost())
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.get_turn", lambda _turn_id: {"status": "running"})
    monkeypatch.setattr("app.agent_host.native_executor._resolve_saved_model", lambda _name: (object(), type("m", (), {"provider_id": "demo-provider", "name": "demo"})()))
    monkeypatch.setattr("app.agent_host.native_executor.create_models", lambda: object())
    monkeypatch.setattr("app.agent_host.native_executor.NoteMeldModelDriver", FakeModelDriver)
    monkeypatch.setattr("app.agent_host.native_executor.append_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.transition_turn", lambda *args, **kwargs: None)

    monkeypatch.setattr(
        "app.agent_host.native_executor.ConversationHistoryStore.load_history",
        lambda _self, _session_id: [],
    )

    executor = NativeAgentExecutor()
    executor.run_sync("turn-1", "session-1", "hello", model_name="demo")

    assert "request" in descriptors_seen
    assert descriptors_seen["request"]["input"]["tools"]
    call = calls[0]
    assert call["messages"] == [{"role": "user", "content": "hello"}]
    assert call["tools"] == descriptors_seen["request"]["tools"]


def test_native_executor_enriches_every_sdk_model_round(monkeypatch):
    from app.agent_host.native_executor import NativeAgentExecutor

    driver_rounds = []
    finished = []

    class FakeModelDriver:
        def __init__(self, *_args, **_kwargs):
            pass

        async def stream(self, request):
            driver_rounds.append(request)
            return {"ok": True, "content": "ok", "tool_calls": [], "finish_reason": "stop", "usage": {}}

    class FakeHost:
        def submit(self, _turn_id, request, *, driver, on_event):
            first_messages = [
                {"role": "system", "content": "system"},
                {"role": "user", "content": "old"},
                {"role": "assistant", "content": "old answer"},
                {"role": "user", "content": {
                    "text": "current",
                    "attachments": [],
                    "context_refs": [{"type": "note_selection", "snapshot": "reference"}],
                }},
            ]
            first = driver({"kind": "model.stream", "payload": {"messages": first_messages}})
            assert first["ok"] is True
            second_messages = [
                *first_messages,
                {"role": "assistant", "content": {
                    "content": "",
                    "tool_calls": [{
                        "call_id": "call-1",
                        "tool_name": "knowledge:evidence_search",
                        "arguments": {"query": "current"},
                    }],
                }},
                {"role": "tool", "content": {"call_id": "call-1", "content": {"results": []}}},
            ]
            second = driver({"kind": "model.stream", "payload": {"messages": second_messages}})
            assert second["ok"] is True
            on_event({"schema_version": "1", "type": "turn.succeeded", "payload": {}})
            return SimpleNamespace(token=1)

        def forget(self, _turn_id):
            return None

        class runtime:
            @staticmethod
            def wait(_token, _timeout):
                return None

    model = SimpleNamespace(
        provider_id="provider-1",
        name="model-1",
        context_window_tokens=8192,
        supports_vision=True,
        supports_stream=True,
        capabilities=SimpleNamespace(supports_tool_calling=True),
    )
    monkeypatch.setattr("app.agent_host.native_executor.get_agent_sdk_host", lambda: FakeHost())
    monkeypatch.setattr("app.agent_host.native_executor._resolve_saved_model", lambda _name: (object(), model))
    monkeypatch.setattr("app.agent_host.native_executor.NoteMeldModelDriver", FakeModelDriver)
    monkeypatch.setattr("app.agent_host.native_executor.append_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.get_turn", lambda _turn_id: {"status": "running"})
    monkeypatch.setattr(
        "app.agent_host.native_executor.agent_store.transition_turn",
        lambda *args, **kwargs: finished.append((args, kwargs)),
    )
    monkeypatch.setattr(
        "app.agent_host.native_executor.ConversationHistoryStore.load_history",
        lambda _self, _session_id: [
            {"role": "system", "content": "system"},
            {"role": "user", "content": "old"},
            {"role": "assistant", "content": "old answer"},
        ],
    )

    executor = NativeAgentExecutor()
    executor.run_sync(
        "turn-1",
        "session-1",
        "current",
        model_name="model-1",
        context_refs=[{"type": "note_selection", "snapshot": "reference"}],
    )

    assert len(driver_rounds) == 2
    assert [message["role"] for message in driver_rounds[0]["messages"]] == [
        "system", "user", "assistant", "user",
    ]
    assert [message["role"] for message in driver_rounds[1]["messages"]][-2:] == ["assistant", "tool"]
    for request in driver_rounds:
        assert request["context_refs"] == [{"type": "note_selection", "snapshot": "reference"}]
        assert request["tools"]
        assert request["model"]["provider_id"] == "provider-1"
        assert request["model"]["context_window_tokens"] == 8192
        assert request["model"]["capabilities"]["supports_tool_calling"] is True
        assert "api_key" not in request["model"]
    assert finished[-1][0][1] == "succeeded"


def test_model_history_filter_keeps_empty_tool_call_groups():
    from app.agent_host.native_executor import _is_model_history_item

    assert _is_model_history_item({
        "role": "assistant",
        "content": "",
        "tool_calls": [{"call_id": "call-1", "tool_name": "lookup", "arguments": {}}],
    })
    assert _is_model_history_item({"role": "tool", "content": "", "tool_call_id": "call-1"})
    assert not _is_model_history_item({"role": "assistant", "content": ""})


def test_native_executor_routes_tool_calls_to_product_driver(monkeypatch):
    from app.agent_host.native_executor import NativeAgentExecutor

    requested = []
    finished = []

    class FakeRuntime:
        def __init__(self, *_args, driver, on_event, **_kwargs):
            self.driver = driver
            self.on_event = on_event

        def submit_turn(self, _request):
            described = self.driver({
                "kind": "tool.describe",
                "payload": {"names": []},
            })
            assert described == {
                "schema_version": "1",
                "ok": True,
                "result": {"tools": [{"name": "wiki:search", "description": "search", "input_schema": {"type": "object"}}]},
            }
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
            assert result == {
                "schema_version": "1",
                "ok": True,
                "result": {"output": {"ok": True, "result": {"items": []}}},
            }
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
        class Registry:
            @staticmethod
            def describe(names):
                assert names == []
                return [{"name": "wiki:search", "description": "search", "input_schema": {"type": "object"}}]

        registry = Registry()

        async def describe(self, names):
            return self.registry.describe(names)

        async def invoke(self, call, context, on_progress=None):
            requested.append((call, context))
            return {
                "call_id": call["call_id"],
                "output": {"ok": True, "result": {"items": []}},
            }

    monkeypatch.setattr("app.agent_host.native_executor.get_agent_sdk_host", lambda: FakeHost())
    monkeypatch.setattr(
        "app.agent_host.native_executor._resolve_saved_model",
        lambda _name: (object(), SimpleNamespace(provider_id="demo-provider", name="demo")),
    )
    monkeypatch.setattr("app.agent_host.native_executor.append_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.NoteMeldModelDriver", lambda *_args, **_kwargs: object())
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.get_turn", lambda _turn_id: {"status": "running"})
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.transition_turn", lambda *args, **kwargs: finished.append((args, kwargs)))

    executor = NativeAgentExecutor(tool_driver=FakeToolDriver())
    monkeypatch.setattr(
        "app.agent_host.native_executor.ConversationHistoryStore.load_history",
        lambda _self, _session_id: [],
    )
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
