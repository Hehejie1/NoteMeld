from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, StrictBool
from typing import Any, List, Optional

from app.services.model_capability import ModelCapabilityService
from app.services.model import (
    ModelAlreadyExistsError,
    ModelNotFoundError,
    ModelProviderNotFoundError,
    ModelService,
    ModelServiceError,
)
from app.services.model_runtime_catalog import resolve_model_runtime_defaults
from app.utils.response import ResponseWrapper as R
router = APIRouter()
modelService = ModelService()
class CreateModelRequest(BaseModel):
    provider_id: str
    model_name: str
    context_window_tokens: int = Field(ge=512, le=4_000_000)
    max_input_tokens: int = Field(default=3072, ge=256, le=4_000_000)
    max_output_tokens: int = Field(default=1024, ge=256, le=4_000_000)
    supports_vision: StrictBool
    supports_stream: StrictBool
    model_id: Optional[str] = None
    display_name: Optional[str] = None
    enabled: int = 1
    is_default: int = 0
    test_status: str = "unknown"


class ModelRuntimeDefaultsRequest(BaseModel):
    model_name: Any = None


class ProbeModelRequest(BaseModel):
    provider_id: str
    model_name: str


class ModelListByConfigRequest(BaseModel):
    api_key: str | None = None
    base_url: str
    name: str | None = None
    protocol: str = "openai-compatible"


class BatchModelItem(BaseModel):
    model_id: str
    display_name: Optional[str] = None
    context_window_tokens: int = Field(default=128000, ge=512, le=4_000_000)
    supports_vision: StrictBool = False
    supports_stream: StrictBool = True
    enabled: int = 1
    test_status: str = "unknown"


class BatchModelsRequest(BaseModel):
    provider_id: str
    models: List[BatchModelItem]
    default_model_id: Optional[str] = None


class DefaultModelRequest(BaseModel):
    provider_id: str
    model_id: str


class ModelShareDecodeRequest(BaseModel):
    text: str

# 返回体：模型信息
class ModelItem(BaseModel):
    id: int
    model_name: str
@router.get("/model_list")
def model_list():
    try:
        return R.success(jsonable_encoder(modelService.get_all_models(True)), msg="获取模型列表成功")
    except Exception as e:
        return R.error(e)
@router.get("/models/delete/{model_id}")
def delete_model(model_id: int):
    try:
        modelService.delete_model_by_id(model_id)
        return R.success(msg="模型删除成功")
    except ModelNotFoundError as error:
        return R.error(error, code=404)
    except ModelServiceError as error:
        return R.error(error, code=400)
    except Exception:
        return R.error("删除模型失败")
@router.get("/model_list/{provider_id}")
def model_list(provider_id):

    return R.success(modelService.get_all_models_by_id(provider_id))


@router.post("/model_list_by_config")
def model_list_by_config(data: ModelListByConfigRequest):
    try:
        models = ModelService.get_model_list_by_config(
            api_key=data.api_key or "",
            base_url=data.base_url,
            name=data.name or "",
            protocol=data.protocol,
        )
        # ollama / anthropic 协议直接返回 [{id, context_window}]
        if data.protocol in {"ollama", "anthropic-messages"}:
            return R.success({"models": models}, msg="获取模型列表成功")
        serializable_models = [m.dict() for m in models.data]
        return R.success({"models": serializable_models}, msg="获取模型列表成功")
    except Exception as e:
        return R.error(str(e))


class SavedModelListRequest(BaseModel):
    provider_id: str


@router.post("/model_list_saved")
def model_list_saved(data: SavedModelListRequest):
    """编辑态用库内 Fernet 密钥拉取远端模型目录；响应不含明文密钥。"""
    models = ModelService.get_model_list_saved(data.provider_id)
    return R.success({"models": models}, msg="获取模型列表成功")


@router.post("/models/batch")
def create_models_batch(data: BatchModelsRequest):
    try:
        result = ModelService.save_models_batch(
            provider_id=data.provider_id,
            models=[item.model_dump() for item in data.models],
            default_model_id=data.default_model_id,
        )
        return R.success(jsonable_encoder(result), msg="模型批量保存成功")
    except ModelProviderNotFoundError as error:
        return R.error(error, code=404)
    except ModelAlreadyExistsError as error:
        return R.error(error, code=409)
    except ModelServiceError as error:
        return R.error(error, code=400)
    except Exception:
        return R.error("模型批量保存失败")


@router.post("/models/default")
def set_default_model(data: DefaultModelRequest):
    try:
        ModelService.set_default_model(data.provider_id, data.model_id)
        return R.success(msg="默认模型设置成功")
    except ModelProviderNotFoundError as error:
        return R.error(error, code=404)
    except ModelNotFoundError as error:
        return R.error(error, code=404)
    except ModelServiceError as error:
        return R.error(error, code=400)
    except Exception:
        return R.error("默认模型设置失败")


@router.post("/model_share/decode")
def decode_model_share(data: ModelShareDecodeRequest):
    try:
        decoded = ModelService.decode_model_share(data.text)
        return R.success(jsonable_encoder(decoded), msg="分享内容解析成功")
    except ModelServiceError as error:
        return R.error(error, code=400)
    except Exception:
        return R.error("分享内容解析失败", code=400)


@router.post("/models")
def create_model(data: CreateModelRequest):
    try:
        saved_model = ModelService.add_new_model(
            provider_id=data.provider_id,
            model_name=data.model_name,
            context_window_tokens=data.context_window_tokens,
            supports_vision=data.supports_vision,
            supports_stream=data.supports_stream,
            max_input_tokens=data.max_input_tokens,
            max_output_tokens=data.max_output_tokens,
            model_id=data.model_id,
            display_name=data.display_name,
            enabled=data.enabled,
            is_default=data.is_default,
            test_status=data.test_status,
        )
        return R.success(jsonable_encoder(saved_model), msg="模型添加成功")
    except ModelProviderNotFoundError as error:
        return R.error(error, code=404)
    except ModelAlreadyExistsError as error:
        return R.error(error, code=409)
    except ModelServiceError as error:
        return R.error(error, code=400)
    except Exception:
        return R.error("模型添加失败")


@router.post("/models/defaults")
def model_runtime_defaults(data: ModelRuntimeDefaultsRequest):
    if not isinstance(data.model_name, str) or not data.model_name.strip():
        return R.error("模型名称不能为空", code=400)
    return R.success(
        resolve_model_runtime_defaults(data.model_name).to_dict(),
        msg="获取模型默认配置成功",
    )


@router.post("/models/probe")
def probe_model_capability(data: ProbeModelRequest):
    try:
        return R.success(ModelCapabilityService.reprobe_json_mode(data.provider_id, data.model_name), msg="模型能力探测完成")
    except Exception as e:
        return R.error(f"模型能力探测失败: {e}")

@router.get("/model_enable/{provider_id}")
def get_enabled_models_by_provider(provider_id: str):
    try:
        models = modelService.get_enabled_models_by_provider(provider_id)
        return R.success(jsonable_encoder(models), msg="获取启用模型成功")
    except Exception as e:
        return R.error(f"获取启用模型失败: {e}")
