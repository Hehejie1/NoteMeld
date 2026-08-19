from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace

from app.agent_host.drivers.model import NoteMeldModelDriver, map_provider_error
from app.ai.errors import (
    ProviderAuthError,
    ProviderCapabilityError,
    ProviderNetworkError,
    ProviderRateLimitError,
)


class FakeModels:
    async def stream(self, model, ctx, options=None, signal=None):
        yield type("Event", (), {"type": "text_delta", "delta": "hello"})()
        yield type("Event", (), {"type": "done", "usage": None})()


def test_model_driver_maps_stream_chunks_and_completion():
    driver = NoteMeldModelDriver(FakeModels(), model=object())
    chunks = []
    result = asyncio.run(driver.stream(
        {"messages": [{"role": "user", "content": "hi"}]},
        chunks.append,
    ))

    assert chunks == [{"type": "content_delta", "delta": "hello"}]
    assert result["content"] == "hello"
    assert result["chunks"] == [{"type": "content_delta", "delta": "hello"}]
    assert result["usage"] == {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_tokens": 0,
        "cache_write_tokens": 0,
    }


def test_model_driver_translates_sdk_tool_descriptors_to_provider_envelope():
    seen = []

    class Models:
        async def stream(self, model, ctx, options=None, signal=None):
            seen.append(ctx.tools)
            yield type("Event", (), {"type": "done", "usage": None})()

    result = asyncio.run(NoteMeldModelDriver(Models(), model=object()).stream({
        "messages": [{"role": "user", "content": "search"}],
        "tools": [{
            "name": "wiki:search",
            "description": "search wiki",
            "input_schema": {"type": "object", "properties": {"query": {"type": "string"}}},
        }],
    }))
    assert result["ok"] is True
    assert seen == [[{
        "type": "function",
        "function": {
            "name": "wiki:search",
            "description": "search wiki",
            "parameters": {"type": "object", "properties": {"query": {"type": "string"}}},
        },
    }]]


def test_provider_error_mapping_is_stable_and_safe():
    error = map_provider_error(RuntimeError("provider payload api_key=secret"))
    assert error["code"] == "model_unavailable"
    assert "secret" not in error["message"]
    assert "api_key" not in error["message"]


def test_model_driver_does_not_turn_provider_error_into_empty_success():
    class ErrorModels:
        async def stream(self, model, ctx, options=None, signal=None):
            yield type("Event", (), {"type": "error", "error": RuntimeError("upstream")})()

    result = asyncio.run(NoteMeldModelDriver(ErrorModels(), model=object()).stream({
        "messages": [{"role": "user", "content": "hi"}],
    }))
    assert result["ok"] is False
    assert result["error"]["code"] == "model_unavailable"


def test_model_driver_parses_toolcall_arguments_from_json_string():
    class Tools:
        async def stream(self, model, ctx, options=None, signal=None):
            yield type("Event", (), {
                "type": "toolcall_end",
                "tool_call_id": "call-1",
                "tool_name": "wiki:search",
                "arguments": '{"query":"note"}',
            })()
            yield type("Event", (), {"type": "done", "usage": None})()

    result = asyncio.run(NoteMeldModelDriver(Tools(), model=object()).stream({"messages": [{"role": "user", "content": "hi"}]}))
    tool_calls = result["tool_calls"]
    assert tool_calls == [{
        "type": "tool_call",
        "call_id": "call-1",
        "tool_name": "wiki:search",
        "arguments": {"query": "note"},
    }]


def test_model_driver_projects_complete_sdk_context_and_stream_result():
    captured = {}
    selected_model = object()

    class Models:
        async def stream(self, model, ctx, options=None, signal=None):
            captured.update({"model": model, "ctx": ctx, "options": options, "signal": signal})
            yield SimpleNamespace(type="text_delta", delta="answer")
            yield SimpleNamespace(
                type="toolcall_end",
                tool_call_id="call-2",
                tool_name="note:read",
                arguments='{"title":"T"}',
            )
            yield SimpleNamespace(
                type="done",
                usage=SimpleNamespace(
                    input_tokens=21,
                    output_tokens=8,
                    cache_read_tokens=3,
                    cache_write_tokens=1,
                ),
            )

    request = {
        "messages": [
            {"role": "system", "content": "system rules"},
            {"role": "user", "content": "previous question"},
            {
                "role": "assistant",
                "content": {
                    "content": "",
                    "tool_calls": [{
                        "call_id": "call-1",
                        "tool_name": "wiki:search",
                        "arguments": {"query": "history"},
                    }],
                },
            },
            {"role": "tool", "content": {"call_id": "call-1", "content": {"items": ["evidence"]}}},
            {"role": "user", "content": "current question"},
        ],
        "input": {
            "text": "current question",
            "attachments": [],
            "context_refs": [{"type": "note_selection", "snapshot": "quoted material"}],
        },
        "tools": [{
            "name": "note:read",
            "description": "read note",
            "input_schema": {"type": "object", "properties": {"title": {"type": "string"}}},
        }],
        "generation_config": {
            "temperature": 0.2,
            "max_tokens": 512,
            "response_format": {"type": "json_object"},
            "timeout": 15,
        },
        "signal": object(),
    }
    options = {"usage_context": {"phase": "agent"}}
    result = asyncio.run(NoteMeldModelDriver(Models(), selected_model, options=options).stream(request))

    assert captured["model"] is selected_model
    assert captured["options"] == options
    assert captured["signal"] is request["signal"]
    ctx = captured["ctx"]
    assert [item["role"] for item in ctx.messages] == ["system", "user", "assistant", "tool", "user"]
    assert ctx.messages[0] == {"role": "system", "content": "system rules"}
    assert ctx.messages[2]["tool_calls"][0]["function"] == {
        "name": "wiki:search",
        "arguments": '{"query": "history"}',
    }
    assert ctx.messages[3]["tool_call_id"] == "call-1"
    assert json.loads(ctx.messages[-1]["content"])["context_refs"][0]["snapshot"] == "quoted material"
    assert ctx.tools[0]["function"]["name"] == "note:read"
    assert (ctx.temperature, ctx.max_tokens, ctx.response_format, ctx.timeout) == (
        0.2,
        512,
        {"type": "json_object"},
        15.0,
    )
    assert result["chunks"] == [{"type": "content_delta", "delta": "answer"}]
    assert result["tool_calls"][0]["tool_name"] == "note:read"
    assert result["usage"] == {
        "input_tokens": 21,
        "output_tokens": 8,
        "cache_read_tokens": 3,
        "cache_write_tokens": 1,
    }


def test_model_driver_rejects_empty_sdk_history_instead_of_faking_success():
    result = asyncio.run(NoteMeldModelDriver(FakeModels(), model=object()).stream({"messages": []}))
    assert result == {
        "ok": False,
        "error": {"code": "invalid_input", "message": "模型请求缺少消息上下文", "details": {}},
    }


def test_model_driver_projects_provider_cancellation():
    class CancelledModels:
        async def stream(self, model, ctx, options=None, signal=None):
            raise asyncio.CancelledError()
            yield  # pragma: no cover - keep this an async generator

    result = asyncio.run(NoteMeldModelDriver(CancelledModels(), model=object()).stream({
        "messages": [{"role": "user", "content": "cancel"}],
    }))
    assert result == {
        "ok": False,
        "error": {"code": "cancelled", "message": "模型调用已取消", "details": {}},
    }


def test_provider_error_categories_are_stable_and_redacted():
    cases = [
        (ProviderAuthError("api_key=secret"), "model_not_configured"),
        (ProviderRateLimitError("raw payload secret"), "model_unavailable"),
        (ProviderNetworkError("private host path"), "model_unavailable"),
        (ProviderCapabilityError("unsupported secret"), "invalid_input"),
    ]
    for error, expected_code in cases:
        projected = map_provider_error(error)
        assert projected["code"] == expected_code
        assert projected["details"] == {}
        assert "secret" not in projected["message"]

    context_error = RuntimeError("raw provider payload")
    context_error.code = "context_limit_exceeded"
    assert map_provider_error(context_error) == {
        "code": "context_budget_exceeded",
        "message": "模型上下文预算不足",
        "details": {},
    }
