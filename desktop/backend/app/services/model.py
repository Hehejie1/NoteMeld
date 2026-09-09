from __future__ import annotations



from app.db.model_dao import (
    ModelDuplicateError,
    delete_model_with_capability,
    get_all_models,
    get_model_by_provider_and_name,
    insert_model,
)
from app.db.provider_dao import get_enabled_providers
from app.enmus.exception import ProviderErrorEnum
from app.exceptions.provider import ProviderError
from app.gpt.gpt_factory import GPTFactory
from app.gpt.provider.OpenAI_compatible_provider import OpenAICompatibleProvider
from app.models.model_config import ModelConfig
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

    @staticmethod
    def get_model_list(provider_id: int, verbose: bool = False):
        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
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
                "context_window_tokens": model.get("context_window_tokens"),
                "supports_vision": model.get("supports_vision"),
                "supports_stream": model.get("supports_stream"),
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
    def get_model_list_by_config(api_key: str, base_url: str, name: str = "", verbose: bool = False):
        provider = {
            "id": "temp",
            "name": name or "custom",
            "api_key": api_key or "",
            "base_url": base_url or "",
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
    def get_all_models_by_id(provider_id: str, verbose: bool = False):
        try:
            provider = ProviderService.get_provider_by_id(provider_id)

            models = ModelService.get_model_list(provider["id"], verbose=verbose)
            print(type(models))
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
    def connect_test(id: str) -> bool:

        provider = ProviderService.get_provider_by_id(id)

        if provider:
            if ModelService._requires_api_key(provider) and not provider.get('api_key'):
                raise ProviderError(code=ProviderErrorEnum.NOT_FOUND.code, message=ProviderErrorEnum.NOT_FOUND.message)
            result =  OpenAICompatibleProvider.test_connection(
                api_key=ModelService._resolve_api_key(provider),
                base_url=provider.get('base_url')
            )
            if result:
                return True
            else:
                raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code,message=ProviderErrorEnum.WRONG_PARAMETER.message)

        raise ProviderError(code=ProviderErrorEnum.NOT_FOUND.code, message=ProviderErrorEnum.NOT_FOUND.message)

    @staticmethod
    def connect_test_by_config(api_key: str, base_url: str) -> bool:
        provider = {
            "id": "",
            "name": "",
            "api_key": api_key or "",
            "base_url": base_url or "",
        }

        if not base_url:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API 地址")

        if ModelService._requires_api_key(provider) and not api_key:
            raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message="请填写 API Key")

        result = OpenAICompatibleProvider.test_connection(
            api_key=ModelService._resolve_api_key(provider),
            base_url=base_url,
        )
        if result:
            return True

        raise ProviderError(code=ProviderErrorEnum.WRONG_PARAMETER.code, message=ProviderErrorEnum.WRONG_PARAMETER.message)



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
                supports_vision=supports_vision,
                supports_stream=supports_stream,
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
