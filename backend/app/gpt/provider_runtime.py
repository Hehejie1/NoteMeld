from __future__ import annotations

import os
import re
from dataclasses import dataclass


FOUR_MB = 4 * 1024 * 1024
DEFAULT_REQUEST_BYTES = 45 * 1024 * 1024
GATEWAY_TIMEOUT_MESSAGE = "模型服务超时，请减少视频理解或切换模型"
REQUEST_TOO_LARGE_MESSAGE = "模型请求内容过大，请减少视频理解或切换模型"


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


def normalize_model_error(exc: BaseException | str | None) -> str:
    raw = "" if exc is None else str(exc)
    lowered = raw.lower()
    html_like = bool(re.search(r"<\s*html|<\s*body|<\s*h1", lowered))

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
