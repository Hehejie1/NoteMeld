from __future__ import annotations

import threading
import uuid
from types import SimpleNamespace

import pytest

from app.agent_host.capabilities import NoteMeldCapabilityRegistry
from app.agent_host.drivers.tools import NoteMeldToolDriver
from app.agent_host.host import AgentSdkHost
from app.agent_host.native_executor import NativeAgentExecutor
from app.agent_host.runtime import AgentSdkUnavailable


_USAGE = {
    "input_tokens": 1,
    "output_tokens": 1,
    "cache_read_tokens": 0,
    "cache_write_tokens": 0,
}


def _available_native_host() -> AgentSdkHost:
    host = AgentSdkHost()
    try:
        host.start()
    except AgentSdkUnavailable as error:
        pytest.skip(f"standalone Agent SDK artifact unavailable: {type(error).__name__}")
    return host


def _patch_executor_boundaries(monkeypatch, host, model_driver, finished):
    monkeypatch.setattr("app.agent_host.native_executor.get_agent_sdk_host", lambda: host)
    monkeypatch.setattr(
        "app.agent_host.native_executor._resolve_saved_model",
        lambda _name: (
            object(),
            SimpleNamespace(provider_id="demo-provider", name="demo"),
        ),
    )
    monkeypatch.setattr("app.agent_host.native_executor.NoteMeldModelDriver", model_driver)
    monkeypatch.setattr(
        "app.agent_host.native_executor.ConversationHistoryStore.load_history",
        lambda _self, _session_id: [],
    )
    monkeypatch.setattr("app.agent_host.native_executor.append_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.update_message", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("app.agent_host.native_executor.agent_store.append_event", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(
        "app.agent_host.native_executor.agent_store.get_turn",
        lambda _turn_id: {"status": "running"},
    )
    monkeypatch.setattr(
        "app.agent_host.native_executor.agent_store.transition_turn",
        lambda *args, **kwargs: finished.append((args, kwargs)),
    )


def test_sdk_scheduler_returns_capability_tool_result_to_next_model_round(monkeypatch):
    host = _available_native_host()
    model_requests = []
    capability_calls = []
    finished = []

    class FakeModelDriver:
        def __init__(self, *_args, options=None, **_kwargs):
            self.session_id = options["usage_context"]["request_meta"]["session_id"]

        async def stream(self, request):
            model_requests.append(request)
            tool_messages = [item for item in request["messages"] if item.get("role") == "tool"]
            if not tool_messages:
                return {
                    "ok": True,
                    "content": "",
                    "chunks": [],
                    "tool_calls": [{
                        "call_id": "call-normal",
                        "tool_name": "wiki:search",
                        "arguments": {"query": "agent sdk", "limit": 2},
                    }],
                    "finish_reason": "tool_calls",
                    "usage": dict(_USAGE),
                }
            return {
                "ok": True,
                "content": "工具结果已用于回答",
                "chunks": [],
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": dict(_USAGE),
            }

    monkeypatch.setattr(
        "app.agent_host.capabilities.WikiSearch.search",
        lambda _self, query, limit: capability_calls.append((query, limit))
        or [{"title": query, "limit": limit}],
    )
    _patch_executor_boundaries(monkeypatch, host, FakeModelDriver, finished)

    try:
        executor = NativeAgentExecutor(
            tool_driver=NoteMeldToolDriver(NoteMeldCapabilityRegistry()),
        )
        executor.run_sync(
            str(uuid.uuid4()),
            "session-normal",
            "请查询 Agent SDK",
            model_name="demo",
        )
    finally:
        host.close()

    assert capability_calls == [("agent sdk", 2)]
    assert len(model_requests) == 2
    second_tool = next(item for item in model_requests[1]["messages"] if item["role"] == "tool")
    assert second_tool["content"]["call_id"] == "call-normal"
    assert second_tool["content"]["content"]["ok"] is True
    assert second_tool["content"]["content"]["result"] == [{"title": "agent sdk", "limit": 2}]
    assert finished[-1][0][1] == "succeeded"


@pytest.mark.parametrize(
    ("tool_name", "arguments", "expected_code", "raise_product_error"),
    [
        ("missing:tool", {}, "unknown_tool", False),
        ("wiki:search", {}, "invalid_arguments", False),
        ("wiki:search", {"query": "SENSITIVE_ARGUMENT"}, "tool_execution_error", True),
    ],
)
def test_sdk_scheduler_returns_classified_tool_failures_to_next_model_round(
    monkeypatch,
    tool_name,
    arguments,
    expected_code,
    raise_product_error,
):
    host = _available_native_host()
    finished = []
    second_tool_messages = []

    class FakeModelDriver:
        def __init__(self, *_args, **_kwargs):
            pass

        async def stream(self, request):
            tool_messages = [item for item in request["messages"] if item.get("role") == "tool"]
            if not tool_messages:
                return {
                    "ok": True,
                    "content": "",
                    "chunks": [],
                    "tool_calls": [{
                        "call_id": "call-error",
                        "tool_name": tool_name,
                        "arguments": arguments,
                    }],
                    "finish_reason": "tool_calls",
                    "usage": dict(_USAGE),
                }
            second_tool_messages.extend(tool_messages)
            return {
                "ok": True,
                "content": "已处理工具错误",
                "chunks": [],
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": dict(_USAGE),
            }

    def search(_self, _query, _limit):
        if raise_product_error:
            raise RuntimeError("SENSITIVE_PROVIDER_PAYLOAD")
        raise AssertionError("product service should not run for invalid tool requests")

    monkeypatch.setattr("app.agent_host.capabilities.WikiSearch.search", search)
    _patch_executor_boundaries(monkeypatch, host, FakeModelDriver, finished)
    try:
        NativeAgentExecutor(
            tool_driver=NoteMeldToolDriver(NoteMeldCapabilityRegistry()),
        ).run_sync(
            str(uuid.uuid4()),
            "session-error",
            "trigger tool error",
            model_name="demo",
        )
    finally:
        host.close()

    assert len(second_tool_messages) == 1
    output = second_tool_messages[0]["content"]["content"]
    assert output["ok"] is False
    assert output["error"]["code"] == expected_code
    assert "SENSITIVE" not in str(output)
    assert finished[-1][0][1] == "succeeded"


def test_shared_sdk_host_keeps_concurrent_session_tool_results_isolated(monkeypatch):
    host = _available_native_host()
    finished = []
    second_rounds = {}
    state_lock = threading.Lock()
    capability_barrier = threading.Barrier(2)

    class FakeModelDriver:
        def __init__(self, *_args, options=None, **_kwargs):
            self.session_id = options["usage_context"]["request_meta"]["session_id"]

        async def stream(self, request):
            tool_messages = [item for item in request["messages"] if item.get("role") == "tool"]
            if not tool_messages:
                return {
                    "ok": True,
                    "content": "",
                    "chunks": [],
                    "tool_calls": [{
                        "call_id": f"call-{self.session_id}",
                        "tool_name": "wiki:search",
                        "arguments": {"query": self.session_id, "limit": 1},
                    }],
                    "finish_reason": "tool_calls",
                    "usage": dict(_USAGE),
                }
            with state_lock:
                second_rounds[self.session_id] = tool_messages[0]
            return {
                "ok": True,
                "content": f"done-{self.session_id}",
                "chunks": [],
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": dict(_USAGE),
            }

    def search(_self, query, limit):
        capability_barrier.wait(timeout=5)
        return [{"session_marker": query, "limit": limit}]

    monkeypatch.setattr("app.agent_host.capabilities.WikiSearch.search", search)
    _patch_executor_boundaries(monkeypatch, host, FakeModelDriver, finished)
    executor = NativeAgentExecutor(
        tool_driver=NoteMeldToolDriver(NoteMeldCapabilityRegistry()),
    )
    threads = [
        threading.Thread(
            target=executor.run_sync,
            args=(str(uuid.uuid4()), session_id, f"query {session_id}"),
            kwargs={"model_name": "demo"},
        )
        for session_id in ("session-a", "session-b")
    ]

    try:
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=15)
    finally:
        host.close()

    assert all(not thread.is_alive() for thread in threads)
    assert set(second_rounds) == {"session-a", "session-b"}
    for session_id, tool_message in second_rounds.items():
        other_session = "session-b" if session_id == "session-a" else "session-a"
        assert tool_message["content"]["call_id"] == f"call-{session_id}"
        assert tool_message["content"]["content"]["result"] == [{"session_marker": session_id, "limit": 1}]
        assert other_session not in str(tool_message)
    assert sorted(item[0][1] for item in finished) == ["succeeded", "succeeded"]
