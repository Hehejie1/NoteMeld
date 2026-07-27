from __future__ import annotations

from app.gpt.base import GPT
from app.gpt.prompt_builder import generate_base_prompt
from app.models.gpt_model import GPTSource
import os
import hashlib
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from app.gpt.prompt import BASE_PROMPT, AI_SUM, SCREENSHOT, LINK, MERGE_PROMPT
from app.gpt.provider_runtime import normalize_model_error, resolve_provider_runtime_config
from app.gpt.utils import fix_markdown
from app.gpt.request_chunker import RequestChunker
from app.db.usage_dao import insert_usage_record
from app.models.transcriber_model import TranscriptSegment
from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir
from datetime import timedelta
from typing import List


logger = get_logger(__name__)


class UniversalGPT(GPT):
    def __init__(
        self,
        client,
        model: str,
        temperature: float = 0.7,
        usage_context: dict | None = None,
        provider_id: str | None = None,
        provider_name: str | None = None,
        base_url: str | None = None,
    ):
        self.client = client
        self.model = model
        self.temperature = temperature
        self.usage_context = usage_context or {}
        self.screenshot = False
        self.link = False
        runtime_config = resolve_provider_runtime_config(
            provider_id=provider_id or self.usage_context.get("provider_id"),
            provider_name=provider_name or self.usage_context.get("provider_name"),
            base_url=base_url,
        )
        self.max_request_bytes = runtime_config.max_request_bytes
        self.request_timeout = runtime_config.request_timeout
        self.checkpoint_dir = note_output_dir()
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        # 初始化时缓存重试配置，避免每次请求重复读取环境变量
        self._max_retry_attempts = max(1, int(os.getenv("OPENAI_RETRY_ATTEMPTS", "3")))
        self._retry_base_backoff = float(os.getenv("OPENAI_RETRY_BACKOFF_SECONDS", "1.5"))

    def _format_time(self, seconds: float) -> str:
        return str(timedelta(seconds=int(seconds)))[2:]

    def _build_segment_text(self, segments: List[TranscriptSegment]) -> str:
        return "\n".join(
            f"{self._format_time(seg.start)} - {seg.text.strip()}"
            for seg in segments
        )

    def ensure_segments_type(self, segments) -> List[TranscriptSegment]:
        return [TranscriptSegment(**seg) if isinstance(seg, dict) else seg for seg in segments]

    def create_messages(self, segments: List[TranscriptSegment], **kwargs):

        content_text = generate_base_prompt(
            title=kwargs.get('title'),
            segment_text=self._build_segment_text(segments),
            tags=kwargs.get('tags'),
            _format=kwargs.get('_format'),
            style=kwargs.get('style'),
            extras=kwargs.get('extras'),
        )

        video_img_urls = kwargs.get('video_img_urls', [])

        content: list[dict] | str
        if video_img_urls:
            # 有截图时走 OpenAI 多模态 content 数组（text + image_url）
            content = [{"type": "text", "text": content_text}]
            for url in video_img_urls:
                content.append({
                    "type": "image_url",
                    "image_url": {
                        "url": url,
                        "detail": "auto"
                    }
                })
        else:
            # 纯文本场景退回 string content：DeepSeek deepseek-chat 等非多模态模型
            # 不识别 [{"type":"text",...}] 数组形态，会返回 invalid_request_error
            # （issue #282）。OpenAI 规范本身也允许 content 为 string。
            content = content_text

        messages = [{
            "role": "user",
            "content": content
        }]

        return messages

    def list_models(self):
        return self.client.models.list()

    def _estimate_messages_bytes(self, messages: list) -> int:
        import json
        return len(json.dumps(messages, ensure_ascii=False).encode("utf-8"))

    def set_usage_context(self, usage_context: dict | None) -> None:
        self.usage_context = usage_context or {}

    def _build_usage_payload(
        self,
        started_at: datetime,
        finished_at: datetime,
        usage=None,
        status: str = "success",
        error_message: str | None = None,
    ) -> dict:
        request_meta = self.usage_context.get("request_meta") or {}
        return {
            "task_id": self.usage_context.get("task_id"),
            "provider_id": self.usage_context.get("provider_id") or "unknown",
            "provider_name": self.usage_context.get("provider_name") or "unknown",
            "model_name": self.model,
            "phase": self.usage_context.get("phase") or "summarize",
            "platform": self.usage_context.get("platform"),
            "video_id": self.usage_context.get("video_id"),
            "video_title": self.usage_context.get("video_title"),
            "prompt_tokens": getattr(usage, "prompt_tokens", None) if usage else None,
            "completion_tokens": getattr(usage, "completion_tokens", None) if usage else None,
            "total_tokens": getattr(usage, "total_tokens", None) if usage else None,
            "status": status,
            "error_message": error_message,
            "request_started_at": started_at,
            "request_finished_at": finished_at,
            "duration_ms": max(0, int((finished_at - started_at).total_seconds() * 1000)),
            "request_meta_json": json.dumps(request_meta, ensure_ascii=False),
        }

    def _record_usage(self, payload: dict) -> None:
        try:
            insert_usage_record(payload)
        except Exception as exc:
            logger.warning(f"写入 token 记录失败: {exc}")

    def _build_merge_messages(self, partials: list) -> list:
        merge_text = MERGE_PROMPT + "\n\n" + "\n\n---\n\n".join(partials)
        # 合并阶段没有图片，直接用 string content 兼容非多模态模型（issue #282）
        return [{
            "role": "user",
            "content": merge_text
        }]

    def _checkpoint_path(self, checkpoint_key: str) -> Path:
        safe_key = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in checkpoint_key)
        return self.checkpoint_dir / f"{safe_key}.gpt.checkpoint.json"

    def _build_source_signature(self, source: GPTSource) -> str:
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "max_request_bytes": self.max_request_bytes,
            "title": source.title,
            "tags": source.tags,
            "format": source._format,
            "style": source.style,
            "extras": source.extras,
            "video_img_urls": source.video_img_urls or [],
            "segments": [
                {
                    "start": getattr(seg, "start", None),
                    "end": getattr(seg, "end", None),
                    "text": getattr(seg, "text", "")
                }
                for seg in source.segment
            ],
        }
        raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _load_checkpoint(self, checkpoint_key: str, source_signature: str) -> dict | None:
        path = self._checkpoint_path(checkpoint_key)
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("source_signature") != source_signature:
                path.unlink(missing_ok=True)
                return None
            return data
        except Exception:
            path.unlink(missing_ok=True)
            return None

    def _save_checkpoint(self, checkpoint_key: str, source_signature: str, partials: list, phase: str) -> None:
        path = self._checkpoint_path(checkpoint_key)
        data = {
            "version": 1,
            "source_signature": source_signature,
            "phase": phase,
            "partials": partials,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp_path.replace(path)

    def _clear_checkpoint(self, checkpoint_key: str) -> None:
        self._checkpoint_path(checkpoint_key).unlink(missing_ok=True)

    @staticmethod
    def _is_insufficient_quota_error(exc: Exception) -> bool:
        raw = str(exc)
        return (
            "insufficient_user_quota" in raw
            or "预扣费额度失败" in raw
            or "insufficient quota" in raw.lower()
        )

    @staticmethod
    def _is_retryable_error(exc: Exception) -> bool:
        raw = str(exc).lower()
        retryable_tokens = (
            "返回了空",
            "error code: 524",
            "bad_response_status_code",
            "timed out",
            "timeout",
            "rate limit",
            "error code: 429",
            "error code: 500",
            "error code: 502",
            "error code: 503",
            "error code: 504",
            "apiconnectionerror",
            "connection error",
            "service unavailable",
        )
        if any(token in raw for token in retryable_tokens):
            return True

        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        return status in {408, 409, 429, 500, 502, 503, 504, 524}

    def create_chat_completion(
        self,
        messages: list,
        phase_label: str = "摘要",
        response_format: dict | None = None,
        request_meta: dict | None = None,
        timeout: float | None = None,
        max_tokens: int | None = None,
    ):
        last_exc = None
        for attempt in range(self._max_retry_attempts):
            started_at = datetime.now(timezone.utc)
            response_format_label = (response_format or {}).get("type") or "default"
            stage = (request_meta or {}).get("stage") or self.usage_context.get("phase") or phase_label
            provider_id = self.usage_context.get("provider_id") or "unknown"
            provider_name = self.usage_context.get("provider_name") or "unknown"
            original_usage_context = self.usage_context
            request_usage_context = self.usage_context
            if request_meta:
                request_usage_context = {
                    **self.usage_context,
                    "phase": stage,
                    "request_meta": {
                        **(self.usage_context.get("request_meta") or {}),
                        **request_meta,
                        "response_format": response_format_label,
                    },
                }
            try:
                request_payload = {
                    "model": self.model,
                    "messages": messages,
                    "temperature": self.temperature,
                }
                if response_format is not None:
                    request_payload["response_format"] = response_format
                effective_timeout = timeout if timeout is not None else self.request_timeout
                if effective_timeout is not None:
                    request_payload["timeout"] = effective_timeout
                if max_tokens is not None:
                    request_payload["max_tokens"] = max_tokens

                logger.info(
                    "LLM 请求开始: provider=%s/%s model=%s stage=%s response_format=%s timeout=%s max_tokens=%s attempt=%s/%s",
                    provider_id,
                    provider_name,
                    self.model,
                    stage,
                    response_format_label,
                    timeout,
                    max_tokens,
                    attempt + 1,
                    self._max_retry_attempts,
                )
                client = self.client.with_options(max_retries=0) if hasattr(self.client, "with_options") else self.client
                response = client.chat.completions.create(**request_payload)
                finished_at = datetime.now(timezone.utc)
                elapsed_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
                self.usage_context = request_usage_context
                try:
                    self._record_usage(self._build_usage_payload(started_at, finished_at, usage=getattr(response, "usage", None)))
                finally:
                    self.usage_context = original_usage_context
                self._extract_message_content(response, phase_label)
                logger.info(
                    "LLM 请求成功: provider=%s/%s model=%s stage=%s response_format=%s timeout=%s max_tokens=%s duration_ms=%s",
                    provider_id,
                    provider_name,
                    self.model,
                    stage,
                    response_format_label,
                    timeout,
                    max_tokens,
                    elapsed_ms,
                )
                return response
            except Exception as exc:
                finished_at = datetime.now(timezone.utc)
                elapsed_ms = max(0, int((finished_at - started_at).total_seconds() * 1000))
                self.usage_context = request_usage_context
                try:
                    self._record_usage(
                        self._build_usage_payload(
                            started_at,
                            finished_at,
                            usage=None,
                            status="failed",
                            error_message=normalize_model_error(exc),
                        )
                    )
                finally:
                    self.usage_context = original_usage_context
                last_exc = exc
                if attempt == self._max_retry_attempts - 1 or not self._is_retryable_error(exc):
                    logger.error(
                        "LLM 请求失败: provider=%s/%s model=%s stage=%s response_format=%s timeout=%s max_tokens=%s duration_ms=%s error=%s",
                        provider_id,
                        provider_name,
                        self.model,
                        stage,
                        response_format_label,
                        timeout,
                        max_tokens,
                        elapsed_ms,
                        exc,
                    )
                    raise
                sleep_seconds = self._retry_base_backoff * (2 ** attempt)
                logger.warning(
                    "LLM 请求失败，准备第 %s 次重试: provider=%s/%s model=%s stage=%s response_format=%s timeout=%s max_tokens=%s duration_ms=%s error=%s",
                    attempt + 2,
                    provider_id,
                    provider_name,
                    self.model,
                    stage,
                    response_format_label,
                    timeout,
                    max_tokens,
                    elapsed_ms,
                    exc,
                )
                time.sleep(sleep_seconds)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("chat completion failed without exception")

    def _chat_completion_create(self, messages: list, phase_label: str = "摘要"):
        return self.create_chat_completion(messages=messages, phase_label=phase_label)

    def _extract_message_content(self, response, phase_label: str) -> str:
        choices = getattr(response, "choices", None) or []
        first_choice = choices[0] if choices else None
        message = getattr(first_choice, "message", None)
        content = getattr(message, "content", None)

        if not isinstance(content, str) or not content.strip():
            finish_reason = getattr(first_choice, "finish_reason", None)
            error_message = (
                f"模型 {self.model} 返回了空{phase_label}内容"
                f"（finish_reason={finish_reason or 'unknown'}）"
            )
            logger.error(error_message)
            raise RuntimeError(error_message)

        return content.strip()

    def _merge_partials(self, partials: list, checkpoint_key: str | None, source_signature: str | None) -> str:
        if not partials:
            raise RuntimeError("没有可用于生成摘要的文本片段")

        def build_messages(texts, *_args, **_kwargs):
            return self._build_merge_messages(texts)

        merge_chunker = RequestChunker(
            lambda *_args, **_kwargs: [],
            self.max_request_bytes,
            self._estimate_messages_bytes
        )

        current_partials = list(partials)
        while len(current_partials) > 1:
            groups = merge_chunker.group_texts_by_budget(current_partials, build_messages)
            new_partials = []
            for group_idx, group in enumerate(groups):
                messages = build_messages(group)
                try:
                    response = self._chat_completion_create(messages, "合并摘要")
                except Exception as exc:
                    if checkpoint_key and source_signature:
                        self._save_checkpoint(checkpoint_key, source_signature, current_partials, "merge")
                    raise

                new_partials.append(self._extract_message_content(response, "合并摘要"))

                if checkpoint_key and source_signature:
                    remaining_partials = []
                    for remaining_group in groups[group_idx + 1:]:
                        remaining_partials.extend(remaining_group)
                    resumable_partials = new_partials + remaining_partials
                    self._save_checkpoint(checkpoint_key, source_signature, resumable_partials, "merge")

            current_partials = new_partials

        return current_partials[0]

    def summarize(self, source: GPTSource) -> str:
        self.screenshot = source.screenshot
        self.link = source.link
        source.segment = self.ensure_segments_type(source.segment)
        checkpoint_key = source.checkpoint_key
        source_signature = self._build_source_signature(source) if checkpoint_key else None

        def message_builder(segments, image_urls, **kwargs):
            return self.create_messages(segments, video_img_urls=image_urls, **kwargs)

        chunker = RequestChunker(message_builder, self.max_request_bytes, self._estimate_messages_bytes)

        try:
            chunks = chunker.chunk(
                source.segment,
                source.video_img_urls or [],
                title=source.title,
                tags=source.tags,
                _format=source._format,
                style=source.style,
                extras=source.extras
            )
        except ValueError:
            chunks = chunker.chunk(
                source.segment,
                [],
                title=source.title,
                tags=source.tags,
                _format=source._format,
                style=source.style,
                extras=source.extras
            )

        partials = []
        if checkpoint_key and source_signature:
            checkpoint = self._load_checkpoint(checkpoint_key, source_signature)
            if checkpoint and isinstance(checkpoint.get("partials"), list):
                partials = checkpoint["partials"]

        if len(partials) > len(chunks):
            partials = []

        for chunk in chunks[len(partials):]:
            messages = self.create_messages(
                chunk.segments,
                title=source.title,
                tags=source.tags,
                video_img_urls=chunk.image_urls,
                _format=source._format,
                style=source.style,
                extras=source.extras
            )
            try:
                response = self._chat_completion_create(messages, "摘要")
            except Exception as exc:
                if checkpoint_key and source_signature:
                    self._save_checkpoint(checkpoint_key, source_signature, partials, "summarize")
                raise

            partials.append(self._extract_message_content(response, "摘要"))
            if checkpoint_key and source_signature:
                self._save_checkpoint(checkpoint_key, source_signature, partials, "summarize")

        if len(partials) == 1:
            if checkpoint_key:
                self._clear_checkpoint(checkpoint_key)
            return partials[0]
        if not partials:
            raise RuntimeError("没有可用于生成摘要的文本片段")
        merged = self._merge_partials(partials, checkpoint_key, source_signature)
        if checkpoint_key:
            self._clear_checkpoint(checkpoint_key)
        return merged
