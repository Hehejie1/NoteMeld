"""NotemeldGPT: 适配器，让 UniversalGPT 的编排逻辑通过 notemeld-ai 调用模型。

T10 迁移目标：
- 继承 ``UniversalGPT``，只 override ``create_chat_completion``，复用 summarize/merge/
  checkpoint/retry 等编排逻辑（``note.py._summarize_text`` 调 ``gpt.summarize`` 走的就是
  这些编排）。
- ``create_chat_completion`` 内部走 ``notemeld-ai.Models.complete()``，自动写 usage
  （success/failed 各一条 per attempt），与旧路径每次 attempt 写一条一致。
- 保留 ``self.client``（同步 OpenAI client），供 ``list_models`` 等非 chat-completion
  路径兼容使用（``model.py`` 的 ``list_models`` 仍走 ``GPTFactory``，未迁移）。
- 保留 retry（3 次指数退避，复用 ``_is_retryable_error``）+ phase 3 级回退
  （``request_meta.stage`` > ``usage_context.phase`` > ``phase_label``），
  固化在 ``test_provider_compat.py::LegacyPhasePrecedenceTest``。
- 返回 OpenAI 形状 response（``SimpleNamespace``），兼容 ``_extract_message_content``
  和外部 caller。

T11 迁移范围（均已走 ``create_chat_completion``，不再直接用 ``gpt.client``）：
- ``wiki_page_merger`` → ``gpt.create_chat_completion()``
- ``web_note._get_gpt`` → ``NotemeldGPT.from_config()``
- ``routers/note.py::retry_wiki_extraction`` → ``NotemeldGPT.from_config()``
- ``summary_refine_engine`` → ``gpt.summarize()``（继承自 UniversalGPT，自动走 override）
- ``note_style`` 模板提取 / ``note_style_image_vlm_analyzer`` → ``NoteGenerator()._get_gpt()``
  （T10 已切到 NotemeldGPT，下游 ``create_chat_completion`` 自动走 notemeld-ai）

兼容补充：
- ``timeout`` 参数通过 ``LLMContext`` 透传给 OpenAI SDK，保留 Wiki merge 等调用点的
  单次请求超时边界。
- ``model.py`` 的 ``list_models`` 仍用 ``GPTFactory``（非 chat-completion 路径，不迁移）。
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timezone
from types import SimpleNamespace
from typing import Any

from app.ai import create_models
from app.ai.errors import ProviderCapabilityError
from app.ai.provider import LLMContext
from app.gpt.provider.OpenAI_compatible_provider import OpenAICompatibleProvider
from app.gpt.universal_gpt import UniversalGPT
from app.gpt.provider_runtime import context_limit_error, normalize_model_error
from app.models.model_config import ModelConfig
from app.utils.logger import get_logger

logger = get_logger(__name__)


class NotemeldGPT(UniversalGPT):
    """适配器：UniversalGPT 编排 + notemeld-ai LLM 调用。

    通过 ``from_config(config)`` 创建，签名与 ``GPTFactory.from_config`` 一致，
    便于 ``note.py._get_gpt()`` 平滑替换（回滚时换回 ``GPTFactory`` 即可）。
    """

    @classmethod
    def from_config(cls, config: ModelConfig) -> "NotemeldGPT":
        """与 ``GPTFactory.from_config`` 签名一致，创建适配器实例。

        保留同步 OpenAI client（``self.client``），供 ``list_models`` 等非 chat-completion
        路径兼容使用。T11 后所有 chat-completion 调用点均走 ``create_chat_completion``，
        不再直接用 ``gpt.client``。
        """
        client = OpenAICompatibleProvider(
            api_key=config.api_key, base_url=config.base_url
        ).get_client
        return cls(
            client=client,
            model=config.model_name,
            usage_context=config.usage_context or {},
            provider_id=config.provider,
            provider_name=config.name,
            base_url=config.base_url,
            context_window_tokens=config.context_window_tokens,
            supports_vision=config.supports_vision,
            supports_stream=config.supports_stream,
        )

    def create_chat_completion(
        self,
        messages: list,
        phase_label: str = "摘要",
        response_format: dict | None = None,
        request_meta: dict | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ):
        """Override：走 notemeld-ai ``Models.complete()``，保留 retry + phase 回退。

        与旧路径 ``UniversalGPT.create_chat_completion`` 的行为对齐：
        - 每次 attempt 调一次 ``models.complete()``，notemeld-ai 自动写 1 条 usage
          （success 写 1 条，failed 写 1 条 ``status=failed``），与旧路径每次 attempt
          写一条一致。
        - retry 逻辑复用继承的 ``_is_retryable_error``（3 次重试 + 指数退避）。
        - phase 3 级回退：``request_meta.stage`` > ``usage_context.phase`` > ``phase_label``。
        - 返回 OpenAI 形状 response（``SimpleNamespace``），兼容 ``_extract_message_content``。

        ``timeout`` 通过 ``LLMContext`` 透传到 Provider；None 时沿用 SDK 默认值。
        """
        if self._messages_include_images(messages) and not self.supports_vision:
            raise ProviderCapabilityError(
                f"model={self.model} (provider={self.provider_id}) 不支持 vision，"
                "请切换已保存为支持图像的模型",
                provider_id=self.provider_id,
                model_name=self.model,
                capability="vision",
            )

        last_exc: Exception | None = None
        response_format_label = (response_format or {}).get("type") or "default"

        for attempt in range(self._max_retry_attempts):
            started_at = datetime.now(timezone.utc)
            # phase 3 级回退（与旧路径一致，固化在 LegacyPhasePrecedenceTest）
            stage = (request_meta or {}).get("stage") or self.usage_context.get("phase") or phase_label
            provider_id = self.usage_context.get("provider_id") or self.provider_id
            provider_name = self.usage_context.get("provider_name") or self.provider_name

            # 合并 request_meta（与旧路径 _build_usage_payload 的合并逻辑一致）
            merged_request_meta = {
                **(self.usage_context.get("request_meta") or {}),
                **(request_meta or {}),
                "response_format": response_format_label,
            }

            logger.info(
                "LLM 请求开始 (notemeld-ai): provider=%s/%s model=%s stage=%s "
                "response_format=%s max_tokens=%s attempt=%s/%s",
                provider_id,
                provider_name,
                self.model,
                stage,
                response_format_label,
                max_tokens,
                attempt + 1,
                self._max_retry_attempts,
            )

            try:
                # 每次调用创建新 Models 实例 + 新 AsyncOpenAI client，避免跨 event loop
                # 复用报错。create_models / get_model / complete 全部在同一个
                # asyncio.run() 的 event loop 内执行。
                result = asyncio.run(
                    self._call_notemeld_ai(
                        messages=messages,
                        provider_id=provider_id,
                        stage=stage,
                        response_format=response_format,
                        timeout=timeout,
                        max_tokens=max_tokens,
                        merged_request_meta=merged_request_meta,
                    )
                )

                finished_at = datetime.now(timezone.utc)
                elapsed_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))

                logger.info(
                    "LLM 请求成功 (notemeld-ai): provider=%s/%s model=%s stage=%s "
                    "response_format=%s max_tokens=%s duration_ms=%s",
                    provider_id,
                    provider_name,
                    self.model,
                    stage,
                    response_format_label,
                    max_tokens,
                    elapsed_ms,
                )

                # 返回 OpenAI 形状 response，兼容 _extract_message_content 和外部 caller
                return self._to_openai_response(result)
            except Exception as exc:
                safe_context_exc = context_limit_error(
                    exc,
                    model_name=self.model,
                    context_window_tokens=self.context_window_tokens,
                )
                finished_at = datetime.now(timezone.utc)
                elapsed_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
                effective_exc = safe_context_exc or exc
                last_exc = effective_exc

                # notemeld-ai complete() 已写 1 条 status=failed usage，这里不重复写
                if attempt == self._max_retry_attempts - 1 or not self._is_retryable_error(effective_exc):
                    logger.error(
                        "LLM 请求失败 (notemeld-ai): provider=%s/%s model=%s stage=%s "
                        "response_format=%s max_tokens=%s duration_ms=%s error=%s",
                        provider_id,
                        provider_name,
                        self.model,
                        stage,
                        response_format_label,
                        max_tokens,
                        elapsed_ms,
                        normalize_model_error(effective_exc),
                    )
                    if safe_context_exc:
                        raise safe_context_exc from None
                    raise
                sleep_seconds = self._retry_base_backoff * (2 ** attempt)
                logger.warning(
                    "LLM 请求失败，准备第 %s 次重试 (notemeld-ai): provider=%s/%s model=%s "
                    "stage=%s response_format=%s max_tokens=%s duration_ms=%s error=%s",
                    attempt + 2,
                    provider_id,
                    provider_name,
                    self.model,
                    stage,
                    response_format_label,
                    max_tokens,
                    elapsed_ms,
                    normalize_model_error(effective_exc),
                )
                time.sleep(sleep_seconds)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("chat completion failed without exception")

    @staticmethod
    def _messages_include_images(messages: list) -> bool:
        for message in messages or []:
            content = message.get("content") if isinstance(message, dict) else None
            if not isinstance(content, list):
                continue
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
        return False

    async def _call_notemeld_ai(
        self,
        *,
        messages: list,
        provider_id: str,
        stage: str,
        response_format: dict | None,
        timeout: float | None,
        max_tokens: int | None,
        merged_request_meta: dict,
    ) -> Any:
        """在 event loop 内创建 Models + 调 complete()。

        每次 ``create_chat_completion`` attempt 调一次，确保 ``AsyncOpenAI`` client
        和 ``event loop`` 生命周期一致。
        """
        models = create_models()
        model = models.get_model(provider_id, self.model)
        if model is None:
            raise RuntimeError(
                f"notemeld-ai get_model 返回 None: provider_id={provider_id} model={self.model}"
            )

        ctx = LLMContext(
            messages=messages,
            temperature=self.temperature,
            max_tokens=max_tokens,
            response_format=response_format,
            timeout=timeout,
        )

        usage_context_for_options = {
            "phase": stage,
            "task_id": self.usage_context.get("task_id"),
            "platform": self.usage_context.get("platform"),
            "video_id": self.usage_context.get("video_id"),
            "video_title": self.usage_context.get("video_title"),
            "request_meta": merged_request_meta,
        }

        return await models.complete(
            model,
            ctx,
            options={"usage_context": usage_context_for_options},
        )

    @staticmethod
    def _to_openai_response(result: Any) -> SimpleNamespace:
        """将 ``CompleteResult`` 转为 OpenAI 形状 response。

        兼容 ``_extract_message_content``（读 ``choices[0].message.content``）和
        旧路径外部 caller（读 ``response.usage``）。
        """
        usage = getattr(result, "usage", None)
        usage_obj = SimpleNamespace(
            prompt_tokens=getattr(usage, "input_tokens", None) if usage else None,
            completion_tokens=getattr(usage, "output_tokens", None) if usage else None,
            total_tokens=getattr(usage, "total_tokens", None) if usage else None,
        )
        message = SimpleNamespace(
            content=result.content or "",
            reasoning_content=getattr(result, "thinking", None) or "",
            tool_calls=None,
        )
        choice = SimpleNamespace(
            message=message,
            finish_reason=getattr(result, "finish_reason", None),
        )
        return SimpleNamespace(choices=[choice], usage=usage_obj)
