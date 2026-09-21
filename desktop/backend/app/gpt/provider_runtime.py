from __future__ import annotations

import os
import re
from dataclasses import dataclass


FOUR_MB = 4 * 1024 * 1024
DEFAULT_REQUEST_BYTES = 45 * 1024 * 1024
GATEWAY_TIMEOUT_MESSAGE = "模型服务超时，请减少视频理解或切换模型"
REQUEST_TOO_LARGE_MESSAGE = "模型请求内容过大，请减少视频理解或切换模型"
CONTEXT_LIMIT_MESSAGE = "模型上下文不足，请调低输入内容或在模型设置中确认实际上下文长度"


class ContextLimitExceededError(RuntimeError):
    """API-safe context failure without the provider's raw response payload."""

    code = "context_limit_exceeded"

    def __init__(
        self,
        *,
        model_name: str | None = None,
        context_window_tokens: int | None = None,
    ) -> None:
        self.model_name = model_name
        self.context_window_tokens = context_window_tokens
        super().__init__(CONTEXT_LIMIT_MESSAGE)


@dataclass(frozen=True)
class ProviderRuntimeConfig:
    max_request_bytes: int
    request_timeout: float | None = None


def _provider_identity(provider_id: str | None, provider_name: str | None, base_url: str | None) -> str:
    return " ".join(part for part in (provider_id, provider_name, base_url) if part).lower()


def resolve_provider_runtime_config(
    *,
    provider_id: str | None = None,
    provider_name: str | None = None,
    base_url: str | None = None,
) -> ProviderRuntimeConfig:
    identity = _provider_identity(provider_id, provider_name, base_url)
    default_max_bytes = int(os.getenv("OPENAI_MAX_REQUEST_BYTES", str(DEFAULT_REQUEST_BYTES)))
    default_timeout = os.getenv("OPENAI_REQUEST_TIMEOUT_SECONDS", "").strip()

    if "freemodel" in identity or "free model" in identity:
        max_bytes = int(os.getenv("FREEMODEL_MAX_REQUEST_BYTES", str(FOUR_MB)))
        timeout_raw = os.getenv("FREEMODEL_REQUEST_TIMEOUT_SECONDS", "90").strip()
        return ProviderRuntimeConfig(
            max_request_bytes=max_bytes,
            request_timeout=float(timeout_raw) if timeout_raw else None,
        )

    return ProviderRuntimeConfig(
        max_request_bytes=default_max_bytes,
        request_timeout=float(default_timeout) if default_timeout else None,
    )


def is_context_limit_error(exc: BaseException | str | None) -> bool:
    raw = "" if exc is None else str(exc)
    lowered = raw.lower()
    structured_codes = []
    if isinstance(exc, BaseException):
        structured_codes.append(getattr(exc, "code", None))
        body = getattr(exc, "body", None)
        if isinstance(body, dict):
            error = body.get("error")
            structured_codes.append(error.get("code") if isinstance(error, dict) else body.get("code"))
    if any(
        str(code or "").lower() in {"exceed_context_size_error", "context_length_exceeded", "context_limit_exceeded"}
        for code in structured_codes
    ):
        return True
    if "exceed_context_size_error" in lowered:
        return True
    if re.search(r"(?:available|maximum)\s+context\s+(?:length|size|window)", lowered):
        return True
    if re.search(r"context\s+(?:length|size|window)\s+(?:is\s+)?exceed(?:ed|s)", lowered):
        return True
    if re.search(r"request\s*\(\s*\d+\s*tokens?\s*\)\s*exceeds", lowered):
        return True

    prompt_match = re.search(r"n_prompt_tokens\s*[:=]\s*(\d+)", lowered)
    context_match = re.search(r"n_ctx\s*[:=]\s*(\d+)", lowered)
    if prompt_match and context_match:
        return int(prompt_match.group(1)) > int(context_match.group(1))
    return False


def context_limit_error(
    exc: BaseException | str | None,
    *,
    model_name: str | None = None,
    context_window_tokens: int | None = None,
) -> ContextLimitExceededError | None:
    if not is_context_limit_error(exc):
        return None
    return ContextLimitExceededError(
        model_name=model_name,
        context_window_tokens=context_window_tokens,
    )


def normalize_model_error(exc: BaseException | str | None) -> str:
    raw = "" if exc is None else str(exc)
    lowered = raw.lower()
    html_like = bool(re.search(r"<\s*html|<\s*body|<\s*h1", lowered))

    if is_context_limit_error(exc):
        return CONTEXT_LIMIT_MESSAGE

    if (
        "504" in lowered
        or "gateway time-out" in lowered
        or "gateway timeout" in lowered
        or "timed out" in lowered
        or "timeout" in lowered
    ) and (html_like or "gateway" in lowered or "timed out" in lowered or "timeout" in lowered):
        return GATEWAY_TIMEOUT_MESSAGE

    if (
        "413" in lowered
        or "request body exceeds" in lowered
        or "request_too_large" in lowered
        or "payload too large" in lowered
        or "limit_bytes" in lowered
    ):
        return REQUEST_TOO_LARGE_MESSAGE

    if html_like:
        return "模型服务返回异常，请稍后重试或切换模型"

    return raw or "模型服务异常，请稍后重试"
