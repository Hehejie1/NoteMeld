from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Mapping

from app.ai.errors import (
    ProviderAuthError,
    ProviderCapabilityError,
    ProviderNetworkError,
    ProviderRateLimitError,
)
from app.ai.provider import LLMContext
from app.ai.stream import StreamEventType
from app.utils.logger import get_logger


logger = get_logger(__name__)


def map_provider_error(error: Exception) -> dict[str, Any]:
    if isinstance(error, ProviderAuthError):
        code = "model_not_configured"
        message = "模型凭证未配置或无效"
    elif isinstance(error, ProviderRateLimitError):
        code = "model_unavailable"
        message = "模型服务暂时不可用"
    elif isinstance(error, ProviderNetworkError):
        code = "model_unavailable"
        message = "模型服务连接失败"
    elif isinstance(error, ProviderCapabilityError):
        code = "invalid_input"
        message = "当前模型不支持所需能力"
    else:
        code = "model_unavailable"
        message = "模型调用失败"
    return {"code": code, "message": message, "details": {}}


class NoteMeldModelDriver:
    """Translate notemeld-ai streaming into the SDK driver envelope."""

    def __init__(self, models: Any, model: Any = None, *, options: Mapping[str, Any] | None = None):
        self.models = models
        self.model = model
        self.options = dict(options or {})

    async def stream(
        self,
        request: Mapping[str, Any],
        emit: Callable[[dict[str, Any]], Any] | None = None,
    ) -> dict[str, Any]:
        messages = list(request.get("messages") or [])
        ctx = LLMContext(messages=messages, tools=list(request.get("tools") or []) or None)
        chunks: list[str] = []
        usage_payload: dict[str, int] = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_tokens": 0,
            "cache_write_tokens": 0,
        }
        tool_calls: list[dict[str, Any]] = []
        emit = emit or (lambda _event: None)

        async def send(event: dict[str, Any]) -> None:
            result = emit(event)
            if asyncio.iscoroutine(result):
                await result

        try:
            async for event in self.models.stream(
                self.model,
                ctx,
                options=self.options,
                signal=request.get("signal"),
            ):
                event_type = getattr(event, "type", None)
                event_type = getattr(event_type, "value", event_type)
                if event_type == StreamEventType.TEXT_DELTA.value or event_type == "text_delta":
                    delta = str(getattr(event, "delta", "") or "")
                    chunks.append(delta)
                    await send({"type": "content_delta", "delta": delta})
                elif event_type == StreamEventType.TOOLCALL_END.value or event_type == "toolcall_end":
                    tool_call = {
                        "type": "tool_call",
                        "call_id": str(getattr(event, "tool_call_id", "") or ""),
                        "tool_name": str(getattr(event, "tool_name", "") or ""),
                        "arguments": getattr(event, "arguments", "") or "{}",
                    }
                    tool_calls.append(tool_call)
                    await send(tool_call)
                elif event_type == StreamEventType.DONE.value or event_type == "done":
                    usage = getattr(event, "usage", None)
                    usage_payload.update({
                        "input_tokens": int(getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None) or 0),
                        "output_tokens": int(getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None) or 0),
                    })
                    usage_payload["cache_read_tokens"] = int(getattr(usage, "cache_read_tokens", None) or 0)
                    usage_payload["cache_write_tokens"] = int(getattr(usage, "cache_write_tokens", None) or 0)
                elif event_type == StreamEventType.ERROR.value or event_type == "error":
                    provider_error = getattr(event, "error", None)
                    if isinstance(provider_error, BaseException):
                        raise provider_error
                    raise RuntimeError("model provider stream failed")
            return {
                "ok": True,
                "content": "".join(chunks),
                "chunks": [{"type": "content_delta", "delta": chunk} for chunk in chunks],
                "tool_calls": tool_calls,
                "finish_reason": "tool_calls" if tool_calls else "stop",
                "usage": usage_payload,
            }
        except Exception as error:  # noqa: BLE001 - map provider boundary
            logger.exception("Agent SDK model provider failed")
            return {"ok": False, "error": map_provider_error(error)}
