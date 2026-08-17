from __future__ import annotations

import asyncio

from app.agent_host.drivers.model import NoteMeldModelDriver, map_provider_error


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


def test_provider_error_mapping_is_stable_and_safe():
    error = map_provider_error(RuntimeError("provider payload api_key=secret"))
    assert error["code"] == "model_unavailable"
    assert "secret" not in error["message"]
    assert "api_key" not in error["message"]


def test_model_driver_does_not_turn_provider_error_into_empty_success():
    class ErrorModels:
        async def stream(self, model, ctx, options=None, signal=None):
            yield type("Event", (), {"type": "error", "error": RuntimeError("upstream")})()

    result = asyncio.run(NoteMeldModelDriver(ErrorModels(), model=object()).stream({"messages": []}))
    assert result["ok"] is False
    assert result["error"]["code"] == "model_unavailable"
