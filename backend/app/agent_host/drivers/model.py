from __future__ import annotations

import asyncio
import json
from typing import Any, Awaitable, Callable, Mapping

from app.ai.errors import (
    ProviderAuthError,
    ProviderCapabilityError,
    ProviderError,
    ProviderNetworkError,
    ProviderRateLimitError,
)
from app.ai.provider import LLMContext
from app.ai.stream import StreamEventType
from app.utils.logger import get_logger


logger = get_logger(__name__)


def _compose_user_message(input_payload: Mapping[str, Any]) -> str:
    text = str(input_payload.get("text") or "")
    attachments = input_payload.get("attachments") or []
    context_refs = input_payload.get("context_refs") or []
    if attachments or context_refs:
        return json.dumps(
            {
                "text": text,
                "attachments": attachments,
                "context_refs": context_refs,
            },
            ensure_ascii=False,
        )
    return text


def _coerce_tool_arguments(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        if isinstance(parsed, Mapping):
            return dict(parsed)
    return {}


def _serialize_content(value: Any) -> str:
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return "" if value is None else str(value)


def _normalize_tool_calls(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        function = item.get("function") if isinstance(item.get("function"), Mapping) else {}
        call_id = str(item.get("id") or item.get("call_id") or "").strip()
        name = str(function.get("name") or item.get("tool_name") or item.get("name") or "").strip()
        if not call_id or not name:
            continue
        arguments = function.get("arguments", item.get("arguments", {}))
        if not isinstance(arguments, str):
            arguments = json.dumps(arguments, ensure_ascii=False)
        output.append({
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": arguments},
        })
    return output


def _normalize_history_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    output: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        role = str(item.get("role") or "")
        if role not in {"system", "user", "assistant", "tool"}:
            continue
        content = item.get("content")
        embedded_tool_calls: Any = None
        embedded_call_id: Any = None
        if isinstance(content, Mapping) and role == "assistant" and "tool_calls" in content:
            embedded_tool_calls = content.get("tool_calls")
            content = content.get("content", "")
        elif isinstance(content, Mapping) and role == "tool" and "call_id" in content:
            embedded_call_id = content.get("call_id")
            content = content.get("content", "")
        if content is None and role not in {"assistant", "tool"}:
            continue
        normalized = {"role": role, "content": _serialize_content(content)}
        tool_calls = _normalize_tool_calls(item.get("tool_calls", embedded_tool_calls))
        if tool_calls:
            normalized["tool_calls"] = tool_calls
        tool_call_id = item.get("tool_call_id", embedded_call_id)
        if tool_call_id is not None:
            normalized["tool_call_id"] = str(tool_call_id)
        output.append(normalized)
    return output


def _apply_current_input_context(
    messages: list[dict[str, Any]],
    input_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    if not input_payload.get("attachments") and not input_payload.get("context_refs"):
        return messages
    composed = _compose_user_message(input_payload)
    plain_text = str(input_payload.get("text") or "")
    for item in reversed(messages):
        if item.get("role") != "user":
            continue
        if item.get("content") == plain_text:
            item["content"] = composed
        break
    return messages


def _model_tools(raw_tools: Any) -> list[dict[str, Any]] | None:
    """Translate SDK descriptors to the provider's OpenAI tool envelope."""
    if not raw_tools:
        return None
    result: list[dict[str, Any]] = []
    for descriptor in raw_tools:
        if not isinstance(descriptor, Mapping):
            continue
        name = str(descriptor.get("name") or "").strip()
        if not name:
            continue
        parameters = descriptor.get("input_schema")
        if not isinstance(parameters, Mapping):
            parameters = descriptor.get("parameters")
        result.append({
            "type": "function",
            "function": {
                "name": name,
                "description": str(descriptor.get("description") or ""),
                "parameters": parameters if isinstance(parameters, Mapping) else {"type": "object"},
            },
        })
    return result or None


def map_provider_error(error: Exception) -> dict[str, Any]:
    error_code = str(getattr(error, "code", "") or "")
    if error_code in {"context_budget_exceeded", "context_limit_exceeded"}:
        code = "context_budget_exceeded"
        message = "模型上下文预算不足"
    elif isinstance(error, ProviderAuthError):
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
    elif isinstance(error, ProviderError):
        code = "model_unavailable"
        message = "模型服务暂时不可用"
    else:
        code = "model_unavailable"
        message = "模型调用失败"
    return {"code": code, "message": message, "details": {}}


def _generation_value(config: Mapping[str, Any], key: str, expected: type) -> Any:
    value = config.get(key)
    if value is None or isinstance(value, bool):
        return None
    if expected is float and isinstance(value, (int, float)):
        return float(value)
    if expected is int and isinstance(value, int):
        return value
    if expected is dict and isinstance(value, Mapping):
        return dict(value)
    return None


def _usage_token(value: Any) -> int:
    try:
        return max(0, int(value or 0))
    except (TypeError, ValueError):
        return 0


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
        messages = _normalize_history_records(request.get("messages"))
        if not messages:
            messages = _normalize_history_records(request.get("history"))
            raw_input = request.get("input")
            input_fallback = raw_input if isinstance(raw_input, Mapping) else {}
            user_message = _compose_user_message(input_fallback)
            if user_message:
                messages.append({"role": "user", "content": user_message})
        if not messages:
            return {
                "ok": False,
                "error": {"code": "invalid_input", "message": "模型请求缺少消息上下文", "details": {}},
            }
        input_payload = request.get("input") if isinstance(request.get("input"), Mapping) else {}
        messages = _apply_current_input_context(messages, input_payload)
        generation = request.get("generation_config")
        if not isinstance(generation, Mapping):
            generation = {}
        system_prompt = request.get("system_prompt")
        if any(item.get("role") == "system" for item in messages):
            system_prompt = None
        ctx = LLMContext(
            messages=messages,
            tools=_model_tools(request.get("tools")),
            temperature=_generation_value(generation, "temperature", float),
            max_tokens=_generation_value(generation, "max_tokens", int),
            response_format=_generation_value(generation, "response_format", dict),
            timeout=_generation_value(generation, "timeout", float),
            system_prompt=str(system_prompt) if system_prompt else None,
        )
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
                        "arguments": _coerce_tool_arguments(getattr(event, "arguments", "")),
                    }
                    tool_calls.append(tool_call)
                    await send(tool_call)
                elif event_type == StreamEventType.DONE.value or event_type == "done":
                    usage = getattr(event, "usage", None)
                    usage_payload.update({
                        "input_tokens": _usage_token(getattr(usage, "input_tokens", None) or getattr(usage, "prompt_tokens", None)),
                        "output_tokens": _usage_token(getattr(usage, "output_tokens", None) or getattr(usage, "completion_tokens", None)),
                    })
                    usage_payload["cache_read_tokens"] = _usage_token(getattr(usage, "cache_read_tokens", None))
                    usage_payload["cache_write_tokens"] = _usage_token(getattr(usage, "cache_write_tokens", None))
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
        except asyncio.CancelledError:
            logger.info("Agent SDK model provider cancelled")
            return {
                "ok": False,
                "error": {"code": "cancelled", "message": "模型调用已取消", "details": {}},
            }
        except Exception as error:  # noqa: BLE001 - map provider boundary
            safe_error = map_provider_error(error)
            logger.warning(
                "Agent SDK model provider failed: category=%s code=%s",
                type(error).__name__,
                safe_error["code"],
            )
            return {"ok": False, "error": safe_error}
