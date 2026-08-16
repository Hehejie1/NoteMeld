from __future__ import annotations

import pytest

from app.agent_host.drivers.model import NoteMeldModelDriver, map_provider_error


class FakeModels:
    async def stream(self, model, ctx, options=None, signal=None):
        yield type("Event", (), {"type": "text_delta", "delta": "hello"})()
        yield type("Event", (), {"type": "done", "usage": None})()


@pytest.mark.asyncio
async def test_model_driver_maps_stream_chunks_and_completion():
    driver = NoteMeldModelDriver(FakeModels(), model=object())
    chunks = []
    result = await driver.stream(
        {"messages": [{"role": "user", "content": "hi"}]},
        chunks.append,
    )

    assert chunks == [{"type": "content_delta", "delta": "hello"}]
    assert result["content"] == "hello"


def test_provider_error_mapping_is_stable_and_safe():
    error = map_provider_error(RuntimeError("provider payload api_key=secret"))
    assert error["code"] == "model_unavailable"
    assert "secret" not in error["message"]
    assert "api_key" not in error["message"]
