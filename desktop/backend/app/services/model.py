from __future__ import annotations



from app.db.model_dao import (
    ModelDuplicateError,
    delete_model_with_capability,
    get_all_models,
    get_model_by_provider_and_name,
    insert_model,
    set_default_model,
    upsert_models_batch,
)
from app.db.provider_dao import get_enabled_providers
from app.enmus.exception import ProviderErrorEnum
from app.exceptions.provider import ProviderError
from app.gpt.gpt_factory import GPTFactory
from app.gpt.provider.OpenAI_compatible_provider import OpenAICompatibleProvider
from app.gpt.provider.anthropic_messages_provider import AnthropicMessagesProvider
from app.gpt.provider.ollama_provider import OllamaProvider
from app.models.model_config import ModelConfig
from app.services import vendor_registry
from app.services.model_capability import ModelCapabilityService
from app.services.provider import ProviderService
from app.utils.logger import get_logger

logger=get_logger(__name__)


class ModelServiceError(ValueError):
    """Base error for explicit API-safe saved-model business failures."""


class ModelProviderNotFoundError(ModelServiceError):
    pass


class ModelAlreadyExistsError(ModelServiceError):
    pass


class ModelNotFoundError(ModelServiceError):
    pass


class ModelService:
    @staticmethod
    def _requires_api_key(provider: dict) -> bool:
        if not provider:
            return True
        # 协议优先（v1 两级模型配置）
        protocol = str(provider.get("protocol") or "").strip().lower()
        if protocol == "ollama":
            return False
        vendor_id = str(provider.get("vendor_id") or "").strip().lower()
        if vendor_id == "ollama":
            return False

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

        if not ModelService._requires_api_key(provider):
            # Some OpenAI SDK versions reject an empty api_key even when the
            # target server is a local Ollama-compatible endpoint.
            return "ollama"

        return ""

    @staticmethod
    def _build_model_config(provider: dict) -> ModelConfig:
        return ModelConfig(
            api_key=ModelService._resolve_api_key(provider),
            base_url=provider["base_url"],
            provider=provider["id"],
            model_name='',
            name=provider["name"],
        )

    @staticmethod
    def build_saved_model_config(
        provider: dict,
        model_name: str,
        usage_context: dict | None = None,
    ) -> ModelConfig:
        """从 Provider 和完整保存模型行构造权威运行配置。"""
        saved_model = ModelService.get_saved_model(str(provider["id"]), str(model_name))
        if not saved_model:
            raise ModelNotFoundError(
                f"模型 {model_name} 未添加到供应商 {provider['id']}"
            )
        return ModelConfig(
            api_key=ModelService._resolve_api_key(provider),
            base_url=provider["base_url"],
            model_name=model_name,
            provider=provider["id"],
            name=provider["name"],
            usage_context=usage_context or {},
            context_window_tokens=int(saved_model["context_window_tokens"]),
            supports_vision=bool(saved_model["supports_vision"]),
            supports_stream=bool(saved_model["supports_stream"]),
        )

    # ---------- 协议 v1：三协议远端模型列表 / 连接测试 ----------

    @staticmethod
    def fetch_remote_models(protocol: str, base_url: str, api_key: str = "") -> list[dict]:
        """按协议拉取远端模型目录，返回 [{id, context_window}]；失败抛 RuntimeError（中文脱敏信息）。"""
        protocol = (protocol or "openai-compatible").strip()
        if not vendor_registry.get_protocol(protocol):
            raise RuntimeError("请选择协议类型")
        normalized_url = vendor_registry.trim_url(base_url)
        if not normalized_url:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API 地址")
        if protocol == "ollama":
            return OllamaProvider.list_models(normalized_url)
        if protocol == "anthropic-messages":
            return AnthropicMessagesProvider.list_models()
        # openai-compatible：浏览器不直连第三方，桌面后端代拉
        if not (api_key or "").strip():
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API Key")
        try:
            client = OpenAICompatibleProvider(
                api_key=api_key, base_url=normalized_url
            ).get_client
            raw = client.models.list()
        except Exception:
            raise RuntimeError("获取模型列表失败") from None
        result: list[dict] = []
        for item in getattr(raw, "data", []) or []:
            model_id = getattr(item, "id", None) or (item.get("id") if isinstance(item, dict) else None)
            if model_id:
                result.append({"id": str(model_id), "context_window": vendor_registry.DEFAULT_CONTEXT})
        if not result:
            raise RuntimeError("未获取到模型，请检查服务地址或手动添加")
        return result

    @staticmethod
    def get_model_list(provider_id: int, verbose: bool = False):
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            return []

        protocol = provider.get("protocol") or "openai-compatible"
        if protocol in {"ollama", "anthropic-messages"}:
            try:
                models = ModelService.fetch_remote_models(
                    protocol, provider["base_url"], provider.get("api_key") or ""
                )
                if verbose:
                    print(f"[{provider['name']}] 模型列表: {models}")
                return models
            except Exception as e:
                print(f"[{provider['name']}] 获取模型失败: {e}")
                return []

        try:
            config = ModelService._build_model_config(provider)
            gpt = GPTFactory().from_config(config)
            models = gpt.list_models()
            if verbose:
                print(f"[{provider['name']}] 模型列表: {models}")
            return models
        except Exception as e:
            print(f"[{provider['name']}] 获取模型失败: {e}")
            return []

    @staticmethod
    def get_all_models(verbose: bool = False):
        try:
            raw_models = get_all_models()
            if verbose:
                print(f"所有模型列表: {raw_models}")
            return ModelService._format_models(raw_models)
        except Exception as e:
            print(f"获取所有模型失败: {e}")
            return []
    @staticmethod
    def get_all_models_safe(verbose: bool = False):
        try:
            raw_models = get_all_models()
            if verbose:
                print(f"所有模型列表: {raw_models}")
            return ModelService._format_models(raw_models)
        except Exception as e:
            print(f"获取所有模型失败: {e}")
            return []
    @staticmethod
    def _format_models(raw_models: list) -> list:
        """
        格式化模型列表
        """
        formatted = []
        for model in raw_models:
            formatted.append({
                "id": model.get("id"),
                "provider_id": model.get("provider_id"),
                "model_name": model.get("model_name"),
                "model_id": model.get("model_id") or model.get("model_name"),
                "display_name": model.get("display_name") or model.get("model_name"),
                "context_window_tokens": model.get("context_window_tokens"),
                "max_input_tokens": model.get("max_input_tokens"),
                "max_output_tokens": model.get("max_output_tokens"),
                "supports_vision": model.get("supports_vision"),
                "supports_stream": model.get("supports_stream"),
                "enabled": int(model.get("enabled") if model.get("enabled") is not None else 1),
                "is_default": int(model.get("is_default") if model.get("is_default") is not None else 0),
                "test_status": model.get("test_status") or "unknown",
                "created_at": model.get("created_at", None),  # 如果有created_at字段
                "capabilities": ModelCapabilityService.get(
                    str(model.get("provider_id")),
                    str(model.get("model_name")),
                ),
            })
        return formatted
    @staticmethod
    def get_enabled_models_by_provider( provider_id: str|int,):
        from app.db.model_dao import get_models_by_provider

        all_models = get_models_by_provider(provider_id)
        return ModelService._format_models(all_models)
    @staticmethod
    def get_model_list_by_config(api_key: str, base_url: str, name: str = "",
                                 protocol: str = "openai-compatible", verbose: bool = False):
        protocol = (protocol or "openai-compatible").strip()
        if protocol in {"ollama", "anthropic-messages"}:
            return ModelService.fetch_remote_models(protocol, base_url, api_key or "")

        provider = {
            "id": "temp",
            "name": name or "custom",
            "api_key": api_key or "",
            "base_url": base_url or "",
            "protocol": protocol,
        }

        if not base_url:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API 地址")

        if ModelService._requires_api_key(provider) and not api_key:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API Key")

        try:
            config = ModelService._build_model_config(provider)
            gpt = GPTFactory().from_config(config)
            models = gpt.list_models()
            if verbose:
                print(f"[{provider['name']}] 模型列表: {models}")
            return models
        except Exception as e:
            print(f"[{provider['name']}] 获取模型失败: {e}")
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message=f"获取模型列表失败: {e}")

    @staticmethod
    def get_model_list_saved(provider_id: str) -> list[dict]:
        """编辑态：用库内 Fernet 密钥拉取远端模型目录，前端不接触明文 Key。"""
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ProviderError(code=ProviderErrorEnum.NOT_FOUND.code, message="模型供应商不存在")
        protocol = provider.get("protocol") or "openai-compatible"
        base_url = provider.get("base_url") or ""
        api_key = ModelService._resolve_api_key(provider) if ModelService._requires_api_key(provider) else ""
        if protocol in {"ollama", "anthropic-messages"}:
            try:
                return ModelService.fetch_remote_models(protocol, base_url, api_key)
            except RuntimeError as exc:
                raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message=str(exc))
        if not base_url:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API 地址")
        if ModelService._requires_api_key(provider) and not api_key:
            raise ProviderError(code=ProviderErrorEnum.NOT_FOUND.code, message=ProviderErrorEnum.NOT_FOUND.message)
        try:
            config = ModelService._build_model_config(provider)
            gpt = GPTFactory().from_config(config)
            response = gpt.list_models()
            return [m.dict() for m in response.data]
        except Exception as e:
            print(f"[{provider.get('name')}] 获取模型失败: {e}")
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message=f"获取模型列表失败: {e}")

    @staticmethod
    def get_all_models_by_id(provider_id: str, verbose: bool = False):
        try:
            provider = ProviderService.get_provider_by_id(provider_id)

            models = ModelService.get_model_list(provider["id"], verbose=verbose)
            # ollama / anthropic 协议直接返回 list[dict]；openai 兼容路径返回 GPTResponse
            if isinstance(models, list):
                serializable_models = models
            else:
                serializable_models = [m.dict() for m in models.data]
            model_list = {
                "models": serializable_models
            }

            logger.info(f"[{provider['name']}] 获取模型成功")
            return model_list
        except Exception as e:
            # print(f"[{provider_id}] 获取模型失败: {e}")
            logger.error(f"[{provider_id}] 获取模型失败: {e}")
            return []
    @staticmethod
    def _test_provider_connection(provider: dict, model_id: str = "") -> bool:
        """三协议最小连接测试；provider 为内部明文 dict。"""
        protocol = provider.get("protocol") or "openai-compatible"
        base_url = provider.get("base_url") or ""
        api_key = ModelService._resolve_api_key(provider) if ModelService._requires_api_key(provider) else ""
        if protocol == "ollama":
            return OllamaProvider.test_connection(base_url)
        if protocol == "anthropic-messages":
            return AnthropicMessagesProvider.test_connection(api_key, base_url, model_id)
        return OpenAICompatibleProvider.test_chat_connection(api_key, base_url, model_id)

    @staticmethod
    def connect_test(id: str, model_id: str = "") -> bool:

        provider = ProviderService.get_provider_by_id(id)

        if provider:
            if ModelService._requires_api_key(provider) and not provider.get('api_key'):
                raise ProviderError(code=ProviderErrorEnum.NOT_FOUND.code, message=ProviderErrorEnum.NOT_FOUND.message)
            try:
                result = ModelService._test_provider_connection(provider, model_id)
            except RuntimeError as exc:
                raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message=str(exc))
            if result:
                return True
            else:
                raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code,message=ProviderErrorEnum.WRONG_PARAMETER.message)

        raise ProviderError(code=ProviderErrorEnum.NOT_FOUND.code, message=ProviderErrorEnum.NOT_FOUND.message)

    @staticmethod
    def connect_test_by_config(api_key: str, base_url: str,
                               protocol: str = "openai-compatible",
                               model_id: str = "") -> bool:
        provider = {
            "id": "",
            "name": "",
            "vendor_id": "",
            "api_key": api_key or "",
            "base_url": base_url or "",
            "protocol": (protocol or "openai-compatible").strip(),
        }

        if not base_url:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API 地址")

        if ModelService._requires_api_key(provider) and not api_key:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API Key")

        try:
            result = ModelService._test_provider_connection(provider, model_id)
        except RuntimeError as exc:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message=str(exc))
        if result:
            return True

        raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message=ProviderErrorEnum.WRONG_PARAMETER.message)



    # ---------- 协议 v1：批量保存 / 默认模型 / 分享 ----------

    @staticmethod
    def save_models_batch(provider_id: str, models: list[dict],
                          default_model_id: str | None = None) -> dict:
        """按多选结果批量保存模型；context_window 校验 512–4,000,000。"""
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ModelProviderNotFoundError(f"供应商ID {provider_id} 不存在")
        if not isinstance(models, list) or not models:
            raise ModelServiceError("请至少选择或添加一个模型")

        items: list[dict] = []
        for raw in models:
            if not isinstance(raw, dict):
                raise ModelServiceError("模型参数格式不正确")
            model_id = str(raw.get("model_id") or raw.get("id") or "").strip()
            if not model_id:
                raise ModelServiceError("模型 ID 不能为空")
            ctx = raw.get("context_window_tokens", raw.get("context_window", vendor_registry.DEFAULT_CONTEXT))
            if isinstance(ctx, bool) or not isinstance(ctx, int) or not (
                vendor_registry.CONTEXT_MIN <= ctx <= vendor_registry.CONTEXT_MAX
            ):
                raise ModelServiceError(
                    f"「{model_id}」上下文需为 {vendor_registry.CONTEXT_MIN:,}–{vendor_registry.CONTEXT_MAX:,} 的整数"
                )
            items.append({
                "model_id": model_id,
                "display_name": str(raw.get("display_name") or raw.get("model_name") or model_id).strip() or model_id,
                "context_window_tokens": ctx,
                "supports_vision": raw.get("supports_vision", False),
                "supports_stream": raw.get("supports_stream", True),
                "enabled": int(raw.get("enabled", 1)),
                "test_status": raw.get("test_status", "unknown"),
            })

        try:
            return upsert_models_batch(provider_id, items, default_model_id=default_model_id)
        except ModelDuplicateError as error:
            raise ModelAlreadyExistsError(str(error)) from error

    @staticmethod
    def set_default_model(provider_id: str, model_id: str) -> bool:
        if not ProviderService.get_provider_by_id(provider_id):
            raise ModelProviderNotFoundError(f"供应商ID {provider_id} 不存在")
        if not model_id:
            raise ModelServiceError("请选择默认模型")
        if not set_default_model(provider_id, model_id):
            raise ModelNotFoundError(f"供应商下不存在模型 {model_id}，请先保存")
        return True

    @staticmethod
    def build_model_share(provider_id: str, model_ids: list[str]) -> str:
        """生成 notemeld://model-add?d=... 分享链接；永不包含 API Key。"""
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ModelProviderNotFoundError(f"供应商ID {provider_id} 不存在")
        saved = [m for m in get_all_models() if str(m.get("provider_id")) == str(provider_id)]
        if model_ids:
            wanted = {str(mid) for mid in model_ids}
            saved = [m for m in saved if str(m.get("model_id")) in wanted]
        if not saved:
            raise ModelServiceError("请选择至少一个已保存模型用于分享")
        models = [
            {
                "id": m["model_id"],
                "display_name": m.get("display_name") or m["model_id"],
                "context_window": m.get("context_window_tokens") or vendor_registry.DEFAULT_CONTEXT,
            }
            for m in saved
        ]
        payload = vendor_registry.build_share_payload(
            vendor_id=provider.get("vendor_id"),
            display_name=provider.get("display_name") or provider["name"],
            protocol=provider.get("protocol") or "openai-compatible",
            base_url=provider.get("base_url") or "",
            models=models,
        )
        return vendor_registry.encode_share(payload)

    @staticmethod
    def decode_model_share(text: str) -> dict:
        """解析分享载荷（不触网、拒绝 api_key、拒绝配对码）。"""
        decoded = vendor_registry.decode_share(text)
        if not decoded:
            raise ModelServiceError("分享内容无效（模型分享与设备配对码不可混用）")
        return decoded

    @staticmethod
    def delete_model_by_id(model_id: int) -> dict:
        deleted_model = delete_model_with_capability(model_id)
        if deleted_model is None:
            raise ModelNotFoundError("模型不存在")
        return deleted_model

    @staticmethod
    def add_new_model(
        provider_id: str,
        model_name: str,
        context_window_tokens: int,
        supports_vision: bool,
        supports_stream: bool,
        max_input_tokens: int = 3072,
        max_output_tokens: int = 1024,
        model_id: str | None = None,
        display_name: str | None = None,
        enabled: int = 1,
        is_default: int = 0,
        test_status: str = "unknown",
    ) -> dict:
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ModelProviderNotFoundError(f"供应商ID {provider_id} 不存在")

        existing = get_model_by_provider_and_name(provider_id, model_name)
        if existing:
            raise ModelAlreadyExistsError(f"模型 {model_name} 已存在于供应商ID {provider_id} 下")

        try:
            return insert_model(
                provider_id=provider_id,
                model_name=model_name,
                context_window_tokens=context_window_tokens,
                max_input_tokens=max_input_tokens,
                max_output_tokens=max_output_tokens,
                supports_vision=supports_vision,
                supports_stream=supports_stream,
                model_id=model_id,
                display_name=display_name,
                enabled=enabled,
                is_default=is_default,
                test_status=test_status,
            )
        except ModelDuplicateError as error:
            raise ModelAlreadyExistsError(str(error)) from error

    @staticmethod
    def get_saved_model(provider_id: str, model_name: str) -> dict | None:
        return get_model_by_provider_and_name(provider_id, model_name)

if __name__ == '__main__':
    # 单个 Provider 测试
    print(ModelService.get_model_list(1, verbose=True))

    # 所有 Provider 模型测试
    # print(ModelService.get_all_models(verbose=True))
