"""Provider 抽象 + OpenAICompatibleProvider 实现。

Provider 负责与具体 LLM 平台通信，产出统一的 StreamEvent 流和 CompleteResult。

当前实现：
- ``OpenAICompatibleProvider``：复用现有 ``openai.AsyncOpenAI`` SDK，兼容所有
  OpenAI 协议兼容的 provider（DeepSeek/Qwen/Ollama 等）。

扩展点（本期不实现，只留接口）：
- ``AnthropicProvider``：Anthropic 原生 API + thinking 模式
- ``GeminiProvider``：Google Gemini 原生 API
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any, AsyncIterator, Optional, Protocol, runtime_checkable

import httpx
from openai import AsyncOpenAI, OpenAI

from app.ai.errors import (
    ProviderAuthError,
    ProviderCapabilityError,
    ProviderNetworkError,
    ProviderRateLimitError,
)
from app.ai.stream import CompleteResult, StreamEvent
from app.ai.tool import Tool
from app.ai.usage import Usage
from app.utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class LLMContext:
    """LLM 调用上下文，映射到 OpenAI API 参数。

    Attributes:
        messages: 消息列表，格式与 OpenAI Chat Completions API 一致。
        tools: 工具定义列表（Tool 对象或 OpenAI function calling dict）。
        temperature: 采样温度，默认 None 由 provider 决定。
        max_tokens: 最大输出 token 数。
        response_format: 响应格式，如 ``{"type": "json_object"}``。
        timeout: 单次 Provider 请求超时秒数；None 使用 SDK 默认值。
        system_prompt: 系统提示词。如果提供，会作为 messages[0] 插入。
    """

    messages: list[dict] = field(default_factory=list)
    tools: list[Tool] | list[dict] | None = None
    temperature: float | None = None
    max_tokens: int | None = None
    response_format: dict | None = None
    timeout: float | None = None
    system_prompt: str | None = None

    def to_openai_messages(self) -> list[dict]:
        """转换为 OpenAI API 的 messages 参数。

        如果设置了 ``system_prompt``，会在最前面插入 system 消息。
        """
        msgs = []
        if self.system_prompt:
            msgs.append({"role": "system", "content": self.system_prompt})
        msgs.extend(self.messages)
        return msgs

    def to_openai_tools(self) -> list[dict] | None:
        """转换为 OpenAI API 的 tools 参数。

        Tool 对象通过 ``to_openai_function()`` 转换；dict 直接透传。
        """
        if not self.tools:
            return None
        result = []
        for t in self.tools:
            if isinstance(t, Tool):
                result.append(t.to_openai_function())
            else:
                result.append(t)
        return result or None


@dataclass
class ProviderConfig:
    """Provider 配置，从 ``providers`` 表读取。

    Attributes:
        provider_id: provider 表主键。
        provider_name: provider 展示名。
        api_key: API Key（已解析，Ollama 场景为占位符 "ollama"）。
        base_url: API 基础 URL。
    """

    provider_id: str
    provider_name: str
    api_key: str
    base_url: str


@runtime_checkable
class Provider(Protocol):
    """Provider 协议：负责与具体 LLM 平台通信。"""

    provider_id: str
    provider_name: str

    async def stream(
        self,
        model: str,
        ctx: LLMContext,
        signal: asyncio.Event | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式调用 LLM，产出 StreamEvent 序列。

        流末产出 ``done`` 事件（含 Usage），或 ``error`` 事件。
        """
        ...

    async def complete(
        self,
        model: str,
        ctx: LLMContext,
        signal: asyncio.Event | None = None,
    ) -> CompleteResult:
        """非流式调用 LLM，返回 CompleteResult。"""
        ...


def _create_async_httpx_client(base_url: str) -> httpx.AsyncClient | None:
    """创建异步 httpx 客户端，本地 Ollama 禁用 HTTP/2。

    复用现有 ``OpenAI_compatible_provider._create_httpx_client`` 的逻辑，
    但用 ``httpx.AsyncClient`` 适配 AsyncOpenAI。
    """
    normalized_url = base_url.lower()
    if "127.0.0.1:11434" in normalized_url or "localhost:11434" in normalized_url:
        transport = httpx.AsyncHTTPTransport(http2=False)
        return httpx.AsyncClient(transport=transport)
    return None


def _classify_openai_error(
    exc: Exception,
    *,
    provider_id: str,
    provider_name: str,
    model_name: str,
) -> Exception:
    """将 OpenAI SDK 异常映射到 notemeld-ai 标准化异常。

    映射规则（参考需求 §10 边界场景）：
    - 401/403 → ProviderAuthError
    - 429 → ProviderRateLimitError
    - timeout/connection/DNS → ProviderNetworkError
    - 其他 → 原样返回（上层处理）
    """
    raw = str(exc)
    lowered = raw.lower()
    status = getattr(exc, "status_code", None) or getattr(exc, "status", None)

    # Context limit is a request-shape failure even when a gateway wraps it in
    # a 5xx/timeout string. Classify it before transient network errors and do
    # not retain the provider's raw payload.
    from app.gpt.provider_runtime import context_limit_error

    safe_context_exc = context_limit_error(exc, model_name=model_name)
    if safe_context_exc:
        return safe_context_exc

    # Auth errors
    if status in (401, 403) or "invalid_api_key" in lowered or "authentication" in lowered:
        return ProviderAuthError(
            f"provider={provider_name}({provider_id}) model={model_name} 认证失败: {raw[:500]}",
            provider_id=provider_id,
            model_name=model_name,
        )

    # Rate limit
    if status == 429 or "rate limit" in lowered or "rate_limit" in lowered:
        return ProviderRateLimitError(
            f"provider={provider_name}({provider_id}) model={model_name} 限流: {raw[:500]}",
            provider_id=provider_id,
            model_name=model_name,
        )

    # Network errors
    network_tokens = ("timed out", "timeout", "connection error", "connection reset",
                      "apiconnectionerror", "service unavailable", "dns", "name resolution")
    if status in (408, 502, 503, 504, 524) or any(t in lowered for t in network_tokens):
        return ProviderNetworkError(
            f"provider={provider_name}({provider_id}) model={model_name} 网络错误: {raw[:500]}",
            provider_id=provider_id,
            model_name=model_name,
            cause=exc,
        )

    return exc


class OpenAICompatibleProvider:
    """OpenAI 兼容协议 Provider。

    复用 ``openai`` SDK（AsyncOpenAI），兼容 DeepSeek/Qwen/Ollama 等。

    保留与现有 ``OpenAICompatibleProvider`` 一致的 httpx 客户端逻辑（Ollama HTTP/2 禁用）。
    """

    def __init__(self, config: ProviderConfig):
        self.provider_id = config.provider_id
        self.provider_name = config.provider_name
        self._base_url = config.base_url
        self._api_key = config.api_key

        httpx_client = _create_async_httpx_client(config.base_url)
        if httpx_client:
            self._client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
                http_client=httpx_client,
            )
        else:
            self._client = AsyncOpenAI(
                api_key=config.api_key,
                base_url=config.base_url,
            )

    async def stream(
        self,
        model: str,
        ctx: LLMContext,
        signal: asyncio.Event | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式调用 OpenAI Chat Completions API。

        产出 StreamEvent 序列，流末产出 ``done``（含 Usage）或 ``error``。
        """
        request_payload = self._build_request_payload(model, ctx, stream=True)

        try:
            stream = await self._client.chat.completions.create(**request_payload)
        except Exception as exc:
            classified = _classify_openai_error(
                exc,
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                model_name=model,
            )
            yield StreamEvent.error(classified)
            return

        yield StreamEvent.start()

        usage_obj = None
        current_tool_calls: dict[int, dict] = {}  # index → {id, name, arguments}

        try:
            async for chunk in stream:
                # 检查 abort
                if signal is not None and signal.is_set():
                    yield StreamEvent.error(asyncio.CancelledError("aborted"))
                    return

                # 提取 usage（流末 chunk 可能携带）
                chunk_usage = getattr(chunk, "usage", None)
                if chunk_usage is not None:
                    usage_obj = chunk_usage

                choices = getattr(chunk, "choices", None) or []
                if not choices:
                    continue

                delta = getattr(choices[0], "delta", None)
                if delta is None:
                    continue

                # 文本内容
                content = getattr(delta, "content", None)
                if content:
                    yield StreamEvent.text_delta(content)

                # 工具调用
                tool_calls = getattr(delta, "tool_calls", None)
                if tool_calls:
                    for tc in tool_calls:
                        idx = getattr(tc, "index", 0)
                        if idx not in current_tool_calls:
                            tc_id = getattr(tc, "id", None) or f"call_{idx}"
                            fn = getattr(tc, "function", None)
                            tc_name = getattr(fn, "name", "") if fn else ""
                            current_tool_calls[idx] = {
                                "id": tc_id,
                                "name": tc_name,
                                "arguments": "",
                            }
                            yield StreamEvent.toolcall_start(tc_id, tc_name)

                        fn = getattr(tc, "function", None)
                        args_delta = getattr(fn, "arguments", "") if fn else ""
                        if args_delta:
                            current_tool_calls[idx]["arguments"] += args_delta
                            yield StreamEvent.toolcall_delta(
                                current_tool_calls[idx]["id"], args_delta
                            )

            # 流结束
            for idx in sorted(current_tool_calls.keys()):
                tc = current_tool_calls[idx]
                yield StreamEvent.toolcall_end(tc["id"], tc["name"], tc["arguments"])

            yield StreamEvent.text_end()

            usage = Usage.from_openai_usage(usage_obj)
            yield StreamEvent.done(usage=usage)

        except Exception as exc:
            classified = _classify_openai_error(
                exc,
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                model_name=model,
            )
            yield StreamEvent.error(classified)

    async def complete(
        self,
        model: str,
        ctx: LLMContext,
        signal: asyncio.Event | None = None,
    ) -> CompleteResult:
        """非流式调用 OpenAI Chat Completions API。"""
        request_payload = self._build_request_payload(model, ctx, stream=False)

        try:
            if signal is not None and signal.is_set():
                raise asyncio.CancelledError("aborted")

            response = await self._client.chat.completions.create(**request_payload)
        except Exception as exc:
            classified = _classify_openai_error(
                exc,
                provider_id=self.provider_id,
                provider_name=self.provider_name,
                model_name=model,
            )
            raise classified from exc

        usage = Usage.from_openai_usage(getattr(response, "usage", None))

        choices = getattr(response, "choices", None) or []
        first_choice = choices[0] if choices else None
        message = getattr(first_choice, "message", None) if first_choice else None

        content = getattr(message, "content", "") if message else ""
        thinking = None
        if message:
            thinking = getattr(message, "reasoning_content", None)
            if thinking is None:
                thinking = getattr(message, "reasoning", None)
        finish_reason = getattr(first_choice, "finish_reason", None) if first_choice else None
        tool_calls_raw = getattr(message, "tool_calls", None) if message else None

        tool_calls: list[dict] = []
        if tool_calls_raw:
            for tc in tool_calls_raw:
                fn = getattr(tc, "function", None)
                tool_calls.append({
                    "id": getattr(tc, "id", ""),
                    "name": getattr(fn, "name", "") if fn else "",
                    "arguments": getattr(fn, "arguments", "") if fn else "",
                })

        return CompleteResult(
            content=content or "",
            tool_calls=tool_calls,
            usage=usage,
            thinking=str(thinking) if thinking else None,
            finish_reason=str(finish_reason) if finish_reason else None,
        )

    def _build_request_payload(
        self,
        model: str,
        ctx: LLMContext,
        *,
        stream: bool,
    ) -> dict:
        """构建 OpenAI API 请求参数。"""
        payload: dict[str, Any] = {
            "model": model,
            "messages": ctx.to_openai_messages(),
        }
        if ctx.temperature is not None:
            payload["temperature"] = ctx.temperature
        if ctx.max_tokens is not None:
            payload["max_tokens"] = ctx.max_tokens
        if ctx.response_format is not None:
            payload["response_format"] = ctx.response_format
        if ctx.timeout is not None:
            payload["timeout"] = ctx.timeout

        tools = ctx.to_openai_tools()
        if tools:
            payload["tools"] = tools

        if stream:
            payload["stream"] = True

        return payload
