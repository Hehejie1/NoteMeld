from __future__ import annotations

from fastapi.encoders import jsonable_encoder
from kombu import uuid

from app.db.models.providers import Provider
from app.db.provider_dao import (
    insert_provider,
    get_all_providers,
    get_provider_by_name,
    get_provider_by_id,
    update_provider,
    delete_provider, get_enabled_providers,
)
from app.gpt.gpt_factory import GPTFactory
from app.models.model_config import ModelConfig


class ProviderService:
    @staticmethod
    def _requires_api_key(name: str, base_url: str) -> bool:
        normalized_name = (name or '').strip().lower()
        normalized_base_url = (base_url or '').strip().lower()
        if normalized_name == 'ollama':
            return False
        if '127.0.0.1:11434' in normalized_base_url or 'localhost:11434' in normalized_base_url:
            return False
        return True

    @staticmethod
    def serialize_provider(row: Provider) -> dict:
        if not row:
            return None
        row = ProviderService.provider_to_dict(row)
        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "logo": row.get("logo"),
            "enabled": row.get("enabled"),
            "base_url": row.get("base_url"),
            "api_key": row.get("api_key"),
            "created_at": jsonable_encoder(row.get("created_at")),
        }
    @staticmethod
    def serialize_provider_safe(row: Provider) -> dict:
        if not row:
            return None
        row = ProviderService.provider_to_dict(row)

        return {
            "id": row.get("id"),
            "name": row.get("name"),
            "logo": row.get("logo"),
            "enabled": row.get("enabled"),
            "base_url": row.get("base_url"),
            "api_key":  ProviderService.mask_key(row.get("api_key")),
            "created_at": jsonable_encoder(row.get("created_at")),
        }
    @staticmethod
    def mask_key(key: str) -> str:
        if not key or len(key) < 8:
            return '*' * len(key)
        return key[:4] + '*' * (len(key) - 8) + key[-4:]
    @staticmethod
    def add_provider(name: str, api_key: str, base_url: str, logo: str, enabled: int = 1):
        try:
            existing = get_provider_by_name(name)
            if existing is not None:
                raise ValueError(f'供应商名称已存在: {name}')
            if ProviderService._requires_api_key(name, base_url) and not (api_key or '').strip():
                raise ValueError('请填写 API Key')
            id = uuid().lower()
            logo = logo or 'custom'
            insert_provider(id, name, api_key, base_url, logo, enabled=enabled)
            return ProviderService.serialize_provider(get_provider_by_id(id))
        except Exception as  e:
            print('创建模式失败',e)
            raise
    @staticmethod
    def provider_to_dict(p: Provider):
        return {
            "id": p.id,
            "name": p.name,
            "logo": p.logo,
            "api_key": p.api_key,
            "base_url": p.base_url,
            "enabled": p.enabled,
            "created_at": p.created_at,
        }
    @staticmethod
    def get_all_providers():
        rows = get_all_providers()
        if rows is None:
            return []

        return [ProviderService.serialize_provider(row) for row in rows] if rows else []
    @staticmethod
    def get_provider_by_name(name: str):
        row = get_provider_by_name(name)
        return ProviderService.serialize_provider(row)

    @staticmethod
    def get_provider_by_id(id: str):  # 已改为 str 类型
        row = get_provider_by_id(id)
        return ProviderService.serialize_provider(row)

    @staticmethod
    def get_provider_by_id_safe(id: str):  # 已改为 str 类型
        row = get_provider_by_id(id)
        return ProviderService.serialize_provider_safe(row)
            # all_models.extend(provider['models'])

    @staticmethod
    def update_provider(id: str, data: dict)->str | None:
        try:
        # 过滤掉空值
            filtered_data = {k: v for k, v in data.items() if v is not None and k not in {'id', 'type'}}
            current_provider = get_provider_by_id(id)
            if not current_provider:
                return None
            next_name = filtered_data.get('name') or current_provider.name
            next_base_url = filtered_data.get('base_url') or current_provider.base_url
            next_api_key = filtered_data.get('api_key')
            if next_api_key is None:
                next_api_key = current_provider.api_key
            if ProviderService._requires_api_key(next_name, next_base_url) and not (next_api_key or '').strip():
                raise ValueError('请填写 API Key')
            print('更新模型供应商',filtered_data)
            update_provider(id, **filtered_data)
            # 获取更新后的供应商信息
            updated_provider = get_provider_by_id(id)
            return {
                'id': id,
                'enabled': updated_provider.enabled,
            }

        except Exception as e:
            print('更新模型供应商失败：',e)
            return None

    @staticmethod
    def delete_provider(id: str):
        return delete_provider(id)
