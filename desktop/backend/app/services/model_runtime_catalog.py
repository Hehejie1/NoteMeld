from __future__ import annotations

import json
import logging
import sys
from dataclasses import asdict, dataclass
from fnmatch import fnmatchcase
from functools import lru_cache
from pathlib import Path
from typing import Any


logger = logging.getLogger(__name__)

_FALLBACK = {
    "context_window_tokens": 4096,
    "supports_vision": False,
    "supports_stream": True,
}
_MIN_CONTEXT_WINDOW_TOKENS = 512
_MAX_CONTEXT_WINDOW_TOKENS = 4_000_000


def _resource_path(filename: str) -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "app" / "resources" / filename
    return Path(__file__).resolve().parents[1] / "resources" / filename


_CATALOG_PATH = _resource_path("model_runtime_catalog.json")


@dataclass(frozen=True)
class ModelRuntimeDefaults:
    model_name: str
    context_window_tokens: int
    supports_vision: bool
    supports_stream: bool
    source: str
    matched_rule: str | None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _normalize_model_name(model_name: str) -> str:
    return str(model_name).strip().lower()


def _is_runtime_rule(value: Any, *, has_match: bool) -> bool:
    required_fields = ("context_window_tokens", "supports_vision", "supports_stream")
    return (
        isinstance(value, dict)
        and (not has_match or (isinstance(value.get("match"), str) and bool(value["match"].strip())))
        and isinstance(value.get("context_window_tokens"), int)
        and not isinstance(value["context_window_tokens"], bool)
        and _MIN_CONTEXT_WINDOW_TOKENS <= value["context_window_tokens"] <= _MAX_CONTEXT_WINDOW_TOKENS
        and isinstance(value.get("supports_vision"), bool)
        and isinstance(value.get("supports_stream"), bool)
        and all(field in value for field in required_fields)
    )


@lru_cache(maxsize=1)
def _load_catalog() -> dict[str, Any] | None:
    try:
        payload = json.loads(_CATALOG_PATH.read_text(encoding="utf-8"))
        if (
            not isinstance(payload, dict)
            or not isinstance(payload.get("version"), int)
            or isinstance(payload.get("version"), bool)
            or not _is_runtime_rule(payload.get("fallback"), has_match=False)
            or not isinstance(payload.get("fallback"), dict)
            or not isinstance(payload.get("models"), list)
            or not all(_is_runtime_rule(rule, has_match=True) for rule in payload["models"])
        ):
            raise ValueError("catalog must contain fallback and models entries")
        return payload
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Unable to load model runtime catalog; using fallback defaults: %s", exc)
        return None


def _runtime_values(rule: dict[str, Any], fallback: dict[str, Any]) -> tuple[int, bool, bool]:
    return (
        int(rule.get("context_window_tokens", fallback["context_window_tokens"])),
        bool(rule.get("supports_vision", fallback["supports_vision"])),
        bool(rule.get("supports_stream", fallback["supports_stream"])),
    )


def resolve_model_runtime_defaults(model_name: str) -> ModelRuntimeDefaults:
    normalized_name = _normalize_model_name(model_name)
    catalog = _load_catalog()
    if catalog is None:
        return ModelRuntimeDefaults(normalized_name, **_FALLBACK, source="fallback", matched_rule=None)

    fallback = {**_FALLBACK, **catalog.get("fallback", {})}
    rules = [rule for rule in catalog["models"] if isinstance(rule, dict) and isinstance(rule.get("match"), str)]

    for rule in rules:
        match = rule["match"].strip().lower()
        if normalized_name == match:
            context_window_tokens, supports_vision, supports_stream = _runtime_values(rule, fallback)
            return ModelRuntimeDefaults(
                normalized_name,
                context_window_tokens,
                supports_vision,
                supports_stream,
                "catalog",
                rule["match"],
            )

    for rule in rules:
        match = rule["match"].strip().lower()
        if fnmatchcase(normalized_name, match):
            context_window_tokens, supports_vision, supports_stream = _runtime_values(rule, fallback)
            return ModelRuntimeDefaults(
                normalized_name,
                context_window_tokens,
                supports_vision,
                supports_stream,
                "catalog",
                rule["match"],
            )

    return ModelRuntimeDefaults(normalized_name, **fallback, source="fallback", matched_rule=None)
