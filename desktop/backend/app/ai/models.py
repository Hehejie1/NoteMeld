"""Models 集合：notemeld-ai 的统一入口。

对外暴露 ``Models`` 类和 ``Model`` 对象，提供 ``stream()`` / ``complete()`` 双入口。

核心职责：
1. ``get_model()``：从 DB 读取 provider 配置，创建 Provider 实例 + 加载能力
2. ``stream()``：流式调用 LLM，自动写 usage，产出 StreamEvent 序列
3. ``complete()``：非流式调用 LLM，自动写 usage，返回 CompleteResult

设计要点：
- Provider 实例按 provider_id 缓存，避免重复创建 OpenAI client
- capability check 在调用前执行：不支持 tools 的模型主动报错
- usage 写入复用 ``UsageWriter`` → ``record_usage()``，字段 100% 兼容
- 异常场景写 ``status=failed`` usage 记录
"""

from __future__ import annotations

import asyncio
import copy
from datetime import datetime, timezone
from typing import Any, AsyncIterator, Optional

from app.ai.catalog import CapabilityCatalog, ModelCapabilities
from app.ai.errors import ProviderCapabilityError, ProviderError
from app.ai.provider import (
    LLMContext,
    OpenAICompatibleProvider,
    Provider,
    ProviderConfig,
)
from app.ai.stream import CompleteResult, StreamEvent, StreamEventType
from app.ai.tool import Tool
from app.ai.usage import Usage, UsageContext, UsageWriter
from app.gpt.token_budget import (
    build_token_budget,
    count_message_images,
    trim_messages_to_budget,
)
from app.services.model import ModelService
from app.services.provider import ProviderService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class Model:
    """Model 对象：封装 provider + model_name + capabilities。

    由 ``Models.get_model()`` 创建，调用方不直接构造。
    """

    def __init__(
        self,
        provider: Provider,
        name: str,
        capabilities: ModelCapabilities,
        provider_id: str,
        provider_name: str,
        context_window_tokens: int = 4096,
        supports_vision: bool = False,
        supports_stream: bool = True,
    ):
        self._provider = provider
        self.name = name
        self.capabilities = capabilities
        self.provider_id = provider_id
        self.provider_name = provider_name
        self.context_window_tokens = context_window_tokens
        self.supports_vision = supports_vision
        self.supports_stream = supports_stream

    @property
    def provider(self) -> Provider:
        return self._provider


class Models:
    """Models 集合：notemeld-ai 统一入口。

    通过 ``create_models()`` 工厂函数创建，内部使用 ModelService 读取 DB。
    """

    def __init__(self, model_service: type[ModelService] | ModelService):
        self._ms = model_service
        self._providers_cache: dict[str, Provider] = {}

    def get_model(
        self,
        provider_id: str,
        model_name: str,
    ) -> Model | None:
        """获取 Model 对象。

        Args:
            provider_id: provider 表主键。
            model_name: 模型名称。

        Returns:
            Model 对象，provider/model 不存在时返回 None（不抛异常）。
        """
        saved_model = self._ms.get_saved_model(provider_id, model_name)
        if not saved_model:
            return None

        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            return None

        provider_instance = self._get_or_create_provider(provider)
        supports_vision = bool(saved_model["supports_vision"])
        caps = CapabilityCatalog.get(str(provider["id"]), model_name).with_saved_vision(
            supports_vision,
        )

        return Model(
            provider=provider_instance,
            name=model_name,
            capabilities=caps,
            provider_id=str(provider["id"]),
            provider_name=provider["name"],
            context_window_tokens=int(saved_model["context_window_tokens"]),
            supports_vision=supports_vision,
            supports_stream=bool(saved_model["supports_stream"]),
        )

    def _get_or_create_provider(self, provider: dict) -> Provider:
        """获取或创建 Provider 实例（按 provider_id 缓存）。"""
        pid = str(provider["id"])
        if pid in self._providers_cache:
            return self._providers_cache[pid]

        config = ProviderConfig(
            provider_id=pid,
            provider_name=provider["name"],
            api_key=ModelService._resolve_api_key(provider),
            base_url=provider["base_url"],
        )
        instance = OpenAICompatibleProvider(config)
        self._providers_cache[pid] = instance
        return instance

    def _check_capabilities(
        self,
        model: Model,
        ctx: LLMContext,
    ) -> None:
        """能力检查：不支持 tools 的模型主动报错。

        验收标准 §7.3：不支持 tool calling 的模型传了 tools 参数 → 主动返回清晰错误。
        """
        if ctx.tools and model.capabilities.supports_tool_calling is False:
            raise ProviderCapabilityError(
                f"model={model.name} (provider={model.provider_id}) 不支持 tool calling，"
                f"请切换支持 function calling 的模型",
                provider_id=model.provider_id,
                model_name=model.name,
                capability="tool_calling",
            )

    def _build_usage_context(
        self,
        model: Model,
        options: dict | None,
    ) -> UsageContext:
        """从 options.usage_context 构建 UsageContext。"""
        uc = (options or {}).get("usage_context") or {}
        return UsageContext(
            provider_id=model.provider_id,
            provider_name=model.provider_name,
            model_name=model.name,
            phase=uc.get("phase", "chat"),
            task_id=uc.get("task_id"),
            platform=uc.get("platform"),
            video_id=uc.get("video_id"),
            video_title=uc.get("video_title"),
            request_meta=uc.get("request_meta"),
        )

    def _budget_context(self, model: Model, ctx: LLMContext) -> LLMContext:
        """Build a provider-bound context copy using the saved model window."""
        messages = ctx.to_openai_messages()
        budget = build_token_budget(model.context_window_tokens)
        trimmed = trim_messages_to_budget(messages, budget, tools=ctx.tools)
        retained_image_count = count_message_images(trimmed)
        effective_budget = build_token_budget(
            model.context_window_tokens,
            image_count=retained_image_count,
        )
        logger.info(
            "LLM context budget: model=%s context=%s max_input=%s images=%s",
            model.name,
            effective_budget.context_window_tokens,
            effective_budget.max_input_tokens,
            retained_image_count,
        )
        bounded = copy.copy(ctx)
        bounded.messages = trimmed
        bounded.system_prompt = None
        return bounded

    async def stream(
        self,
        model: Model,
        ctx: LLMContext,
        options: dict | None = None,
        signal: asyncio.Event | None = None,
    ) -> AsyncIterator[StreamEvent]:
        """流式调用 LLM。

        自动写 usage（成功/失败各一条），产出 StreamEvent 序列。

        Args:
            model: Model 对象（由 ``get_model()`` 创建）。
            ctx: LLM 调用上下文。
            options: 选项字典，支持 ``usage_context`` 键。
            signal: abort 信号（asyncio.Event）。

        Yields:
            StreamEvent 序列。
        """
        self._check_capabilities(model, ctx)
        bounded_ctx = self._budget_context(model, ctx)

        usage_ctx = self._build_usage_context(model, options)
        started_at = datetime.now(timezone.utc)

        try:
            if not model.supports_stream:
                result = await model.provider.complete(model.name, bounded_ctx, signal)

                yield StreamEvent.start()
                if result.thinking:
                    yield StreamEvent.thinking_start()
                    yield StreamEvent.thinking_delta(result.thinking)
                    yield StreamEvent.thinking_end()
                has_text = bool(result.content)
                if has_text:
                    yield StreamEvent.text_start()
                    yield StreamEvent.text_delta(result.content)
                for tool_call in result.tool_calls or []:
                    tool_call_id = str(tool_call.get("id") or "")
                    tool_name = str(tool_call.get("name") or "")
                    arguments = str(tool_call.get("arguments") or "")
                    yield StreamEvent.toolcall_start(tool_call_id, tool_name)
                    yield StreamEvent.toolcall_end(tool_call_id, tool_name, arguments)
                if has_text:
                    yield StreamEvent.text_end()

                finished_at = datetime.now(timezone.utc)
                usage_ctx.started_at = started_at
                usage_ctx.finished_at = finished_at
                usage = result.usage if isinstance(result.usage, Usage) else Usage()
                UsageWriter.write(usage, usage_ctx, status="success")
                yield StreamEvent.done(usage=usage)
                return

            async for event in model.provider.stream(model.name, bounded_ctx, signal):
                if event.type == StreamEventType.DONE:
                    # 流成功结束，写 usage
                    finished_at = datetime.now(timezone.utc)
                    usage_ctx.started_at = started_at
                    usage_ctx.finished_at = finished_at
                    usage = event.usage if isinstance(event.usage, Usage) else Usage()
                    UsageWriter.write(usage, usage_ctx, status="success")
                elif event.type == StreamEventType.ERROR:
                    # 流中出错，写 failed usage
                    finished_at = datetime.now(timezone.utc)
                    usage_ctx.started_at = started_at
                    usage_ctx.finished_at = finished_at
                    error_msg = str(event.error)[:1000] if event.error else "unknown error"
                    UsageWriter.write(Usage(), usage_ctx, status="failed", error_message=error_msg)
                yield event
        except ProviderError:
            # Provider 层已分类的异常，写 failed usage 后重新抛出
            finished_at = datetime.now(timezone.utc)
            usage_ctx.started_at = started_at
            usage_ctx.finished_at = finished_at
            UsageWriter.write(
                Usage(),
                usage_ctx,
                status="failed",
                error_message="provider error before stream started",
            )
            raise
        except Exception as exc:
            # 未分类异常，写 failed usage
            finished_at = datetime.now(timezone.utc)
            usage_ctx.started_at = started_at
            usage_ctx.finished_at = finished_at
            UsageWriter.write(
                Usage(),
                usage_ctx,
                status="failed",
                error_message=str(exc)[:1000],
            )
            raise

    async def complete(
        self,
        model: Model,
        ctx: LLMContext,
        options: dict | None = None,
        signal: asyncio.Event | None = None,
    ) -> CompleteResult:
        """非流式调用 LLM。

        自动写 usage（成功/失败各一条），返回 CompleteResult。

        Args:
            model: Model 对象。
            ctx: LLM 调用上下文。
            options: 选项字典，支持 ``usage_context`` 键。
            signal: abort 信号。

        Returns:
            CompleteResult 对象。
        """
        self._check_capabilities(model, ctx)
        bounded_ctx = self._budget_context(model, ctx)

        usage_ctx = self._build_usage_context(model, options)
        started_at = datetime.now(timezone.utc)

        try:
            result = await model.provider.complete(model.name, bounded_ctx, signal)
            finished_at = datetime.now(timezone.utc)
            usage_ctx.started_at = started_at
            usage_ctx.finished_at = finished_at
            UsageWriter.write(result.usage or Usage(), usage_ctx, status="success")
            return result
        except Exception as exc:
            finished_at = datetime.now(timezone.utc)
            usage_ctx.started_at = started_at
            usage_ctx.finished_at = finished_at
            UsageWriter.write(
                Usage(),
                usage_ctx,
                status="failed",
                error_message=str(exc)[:1000],
            )
            raise
