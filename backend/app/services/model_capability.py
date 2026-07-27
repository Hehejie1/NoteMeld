from __future__ import annotations

import json
import os
from datetime import datetime, timedelta, timezone

from openai import OpenAI

from app.db.model_capability_dao import get_model_capability, upsert_model_capability
from app.services.provider import ProviderService
from app.utils.logger import get_logger


logger = get_logger(__name__)


class ModelCapabilityService:
    JSON_MODE_PROBE_TIMEOUT_SECONDS = float(os.getenv("MODEL_CAPABILITY_PROBE_TIMEOUT_SECONDS", "8"))
    CAPABILITY_TTL_DAYS = int(os.getenv("MODEL_CAPABILITY_TTL_DAYS", "7"))

    @staticmethod
    def _requires_api_key(provider: dict) -> bool:
        provider_id = str(provider.get("id", "")).lower()
        provider_name = str(provider.get("name", "")).lower()
        base_url = str(provider.get("base_url", "")).lower()
        if provider_id == "ollama" or provider_name == "ollama":
            return False
        if "127.0.0.1:11434" in base_url or "localhost:11434" in base_url:
            return False
        return True

    @staticmethod
    def _resolve_api_key(provider: dict) -> str:
        api_key = provider.get("api_key") or ""
        if api_key:
            return api_key
        if not ModelCapabilityService._requires_api_key(provider):
            return "ollama"
        return ""

    @staticmethod
    def get(provider_id: str, model_name: str) -> dict:
        return get_model_capability(provider_id, model_name) or {}

    @staticmethod
    def supports_json_mode(provider_id: str, model_name: str) -> bool | None:
        row = get_model_capability(provider_id, model_name)
        if not row:
            return None
        return row.get("supports_json_mode")

    @staticmethod
    def supports_vision(provider_id: str, model_name: str) -> bool | None:
        row = get_model_capability(provider_id, model_name)
        if not row:
            return None
        return row.get("supports_vision")

    @staticmethod
    def _is_json_mode_capability_stale(row: dict) -> bool:
        checked_at = row.get("json_mode_checked_at")
        if checked_at is None:
            return True
        if isinstance(checked_at, str):
            try:
                checked_at = datetime.fromisoformat(checked_at.replace("Z", "+00:00"))
            except ValueError:
                return True
        if checked_at.tzinfo is None:
            checked_at = checked_at.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) - checked_at > timedelta(days=ModelCapabilityService.CAPABILITY_TTL_DAYS)

    @staticmethod
    def ensure_json_mode_capability(provider_id: str, model_name: str) -> bool | None:
        row = get_model_capability(provider_id, model_name)
        if row and row.get("supports_json_mode") is not None and not ModelCapabilityService._is_json_mode_capability_stale(row):
            return row.get("supports_json_mode")

        try:
            provider = ProviderService.get_provider_by_id(provider_id)
        except Exception as exc:
            logger.warning("模型能力读取 provider 失败: provider_id=%s model=%s error=%s", provider_id, model_name, exc)
            return None

        if not provider:
            return None
        result = ModelCapabilityService.probe_json_mode_safe(provider, model_name)
        if "supports_json_mode" not in result:
            return None
        return result["supports_json_mode"]

    @staticmethod
    def probe_json_mode(provider: dict, model_name: str) -> dict:
        provider_id = str(provider["id"])
        try:
            client = OpenAI(
                api_key=ModelCapabilityService._resolve_api_key(provider),
                base_url=provider["base_url"],
                timeout=ModelCapabilityService.JSON_MODE_PROBE_TIMEOUT_SECONDS,
            )
            response = client.chat.completions.create(
                model=model_name,
                messages=[
                    {"role": "system", "content": "Return only JSON."},
                    {"role": "user", "content": 'Return {"ok": true}.'},
                ],
                temperature=0,
                max_tokens=32,
                response_format={"type": "json_object"},
            )
            content = response.choices[0].message.content or ""
            json.loads(content)
            result = upsert_model_capability(
                provider_id=provider_id,
                model_name=model_name,
                supports_json_mode=True,
                last_probe_error="",
            )
            logger.info("模型能力探测成功: provider_id=%s model=%s supports_json_mode=True", provider_id, model_name)
            return result
        except Exception as exc:
            error = str(exc)[:1000]
            result = upsert_model_capability(
                provider_id=provider_id,
                model_name=model_name,
                supports_json_mode=False,
                last_probe_error=error,
            )
            logger.warning(
                "模型能力探测失败: provider_id=%s model=%s supports_json_mode=False error=%s",
                provider_id,
                model_name,
                error,
            )
            return result

    @staticmethod
    def probe_json_mode_safe(provider: dict, model_name: str) -> dict:
        try:
            return ModelCapabilityService.probe_json_mode(provider, model_name)
        except Exception as exc:
            logger.warning("模型能力探测异常但不阻断主流程: provider=%s model=%s error=%s", provider, model_name, exc)
            return {}

    @staticmethod
    def reprobe_json_mode(provider_id: str, model_name: str) -> dict:
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ValueError("Provider not found")
        return ModelCapabilityService.probe_json_mode(provider, model_name)
