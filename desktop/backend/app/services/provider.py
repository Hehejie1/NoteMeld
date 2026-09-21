from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from kombu import uuid

from app.db.models.providers import Provider
from app.db.provider_dao import (
    insert_provider,
    get_all_providers,
    get_provider_by_name,
    get_provider_by_id,
    update_provider as dao_update_provider,
    delete_provider, get_enabled_providers,
)
from app.gpt.gpt_factory import GPTFactory
from app.models.model_config import ModelConfig
from app.security import model_secret

_PROTOCOL_NO_KEY = {"ollama"}


class ProviderService:
    @staticmethod
    def _requires_api_key(name: str, base_url: str, protocol: str | None = None) -> bool:
        # 显式协议优先：ollama 免 Key，其余协议一律需要 Key（切换协议时不得被历史名称/地址启发式绕过）
        normalized_protocol = (protocol or "").strip().lower()
        if normalized_protocol:
            return normalized_protocol not in _PROTOCOL_NO_KEY
        # 仅对没有协议标记的历史行沿用旧启发式
        normalized_name = (name or '').strip().lower()
        normalized_base_url = (base_url or '').strip().lower()
        if normalized_name == 'ollama':
            return False
        if '127.0.0.1:11434' in normalized_base_url or 'localhost:11434' in normalized_base_url:
            return False
        return True

    # ---------- 内部表示（含解密后的明文 key，仅供服务端内部链路使用，禁止进 HTTP 响应） ----------

    @staticmethod
    def provider_to_dict(p: Provider) -> dict:
        plaintext = ""
        if getattr(p, "api_key_ciphertext", None):
            plaintext = model_secret.decrypt(p.api_key_ciphertext)
        if not plaintext:
            # 迁移失败行保留的明文兜底
            plaintext = p.api_key or ""
        return {
            "id": p.id,
            "name": p.name,
            "logo": p.logo,
            "api_key": plaintext,
            "base_url": p.base_url,
            "enabled": p.enabled,
            "display_name": getattr(p, "display_name", None) or p.name,
            "vendor_id": getattr(p, "vendor_id", None) or "custom",
            "protocol": getattr(p, "protocol", None) or "openai-compatible",
            "auth_type": getattr(p, "auth_type", None) or "api_key",
            "has_api_key": bool(plaintext),
            "created_at": p.created_at,
        }

    @staticmethod
    def get_provider_by_id(id: str) -> dict | None:
        """内部使用：返回解密后的明文 api_key，禁止直接作为 HTTP 响应返回。"""
        row = get_provider_by_id(id)
        if not row:
            return None
        return ProviderService.provider_to_dict(row)

    @staticmethod
    def get_provider_by_name(name: str) -> dict | None:
        """内部使用：返回解密后的明文 api_key。"""
        row = get_provider_by_name(name)
        if not row:
            return None
        return ProviderService.provider_to_dict(row)

    @staticmethod
    def get_enabled_providers():
        return get_enabled_providers()

    # ---------- HTTP 出口表示（永不回显明文） ----------

    @staticmethod
    def mask_key(key: str) -> str:
        return model_secret.mask_key(key)

    @staticmethod
    def serialize_provider_safe(row: Provider | dict | None) -> dict | None:
        if not row:
            return None
        data = row if isinstance(row, dict) else ProviderService.provider_to_dict(row)
        plaintext = data.get("api_key") or ""
        return {
            "id": data.get("id"),
            "name": data.get("name"),
            "logo": data.get("logo"),
            "enabled": data.get("enabled"),
            "base_url": data.get("base_url"),
            "display_name": data.get("display_name") or data.get("name"),
            "vendor_id": data.get("vendor_id") or "custom",
            "protocol": data.get("protocol") or "openai-compatible",
            "auth_type": data.get("auth_type") or "api_key",
            "has_api_key": bool(data.get("has_api_key") or plaintext),
            "credential_status": "saved" if (data.get("has_api_key") or plaintext) else "missing",
            "api_key_masked": ProviderService.mask_key(plaintext),
            "created_at": jsonable_encoder(data.get("created_at")),
        }

    # 历史名称保留：serialize_provider 现在同样是安全出口（破坏性安全修复：不再回显明文）
    @staticmethod
    def serialize_provider(row: Provider | dict | None) -> dict | None:
        return ProviderService.serialize_provider_safe(row)

    @staticmethod
    def add_provider(
        name: str,
        api_key: str,
        base_url: str,
        logo: str,
        enabled: int = 1,
        *,
        display_name: str | None = None,
        vendor_id: str = "custom",
        protocol: str = "openai-compatible",
        auth_type: str = "api_key",
    ) -> dict:
        existing = get_provider_by_name(name)
        if existing is not None:
            raise ValueError(f'供应商名称已存在: {name}')
        if ProviderService._requires_api_key(name, base_url, protocol) and not (api_key or '').strip():
            raise ValueError('请填写 API Key')
        provider_id = uuid().lower()
        logo = logo or vendor_id or 'custom'
        plaintext = (api_key or "").strip()
        ciphertext = model_secret.encrypt(plaintext) if plaintext else ""
        insert_provider(
            provider_id,
            name,
            "",  # 明文列停止写入
            base_url,
            logo,
            enabled=enabled,
            api_key_ciphertext=ciphertext,
            display_name=display_name or name,
            vendor_id=vendor_id or "custom",
            protocol=protocol or "openai-compatible",
            auth_type=auth_type or "api_key",
        )
        return ProviderService.serialize_provider_safe(get_provider_by_id(provider_id))

    @staticmethod
    def get_all_providers() -> list[dict]:
        rows = get_all_providers()
        if not rows:
            return []
        return [ProviderService.serialize_provider_safe(row) for row in rows]

    @staticmethod
    def get_provider_by_id_safe(id: str) -> dict | None:
        row = get_provider_by_id(id)
        return ProviderService.serialize_provider_safe(row)

    @staticmethod
    def update_provider(id: str, data: dict) -> dict | None:
        current_row = get_provider_by_id(id)
        if not current_row:
            return None
        current = ProviderService.provider_to_dict(current_row)

        filtered = {
            k: v for k, v in data.items()
            if v is not None and k not in {'id', 'type', 'has_api_key', 'credential_status', 'api_key_masked'}
        }

        next_name = filtered.get('name') or current['name']
        next_base_url = filtered.get('base_url') or current['base_url']
        next_protocol = filtered.get('protocol') or current['protocol']

        submitted_key = filtered.pop('api_key', None)
        if submitted_key is not None:
            candidate = submitted_key.strip()
            # 空串或"等于当前掩码"的提交一律视为未修改，保留原密钥
            if candidate and candidate != ProviderService.mask_key(current['api_key']):
                filtered['api_key_ciphertext'] = model_secret.encrypt(candidate)
            # 明文列始终保持为空
            filtered['api_key'] = ""

        if ProviderService._requires_api_key(next_name, next_base_url, next_protocol):
            will_have_key = (
                'api_key_ciphertext' in filtered and bool(filtered['api_key_ciphertext'])
            ) or ('api_key_ciphertext' not in filtered and current['has_api_key'])
            if not will_have_key:
                raise ValueError('请填写 API Key')

        dao_update_provider(id, **filtered)
        updated = get_provider_by_id(id)
        safe = ProviderService.serialize_provider_safe(updated)
        return {'id': id, 'enabled': safe['enabled'], 'provider': safe}

    @staticmethod
    def delete_provider(id: str):
        return delete_provider(id)
