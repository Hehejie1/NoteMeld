from fastapi import APIRouter
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field, StrictBool
from typing import Any

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
    supports_vision: StrictBool
    supports_stream: StrictBool


class ModelRuntimeDefaultsRequest(BaseModel):
    model_name: Any = None


class ProbeModelRequest(BaseModel):
    provider_id: str
    model_name: str


class ModelListByConfigRequest(BaseModel):
    api_key: str | None = None
    base_url: str
    name: str | None = None

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
        )
        serializable_models = [m.dict() for m in models.data]
        return R.success({"models": serializable_models}, msg="获取模型列表成功")
    except Exception as e:
        return R.error(str(e))


@router.post("/models")
def create_model(data: CreateModelRequest):
    try:
        saved_model = ModelService.add_new_model(
            data.provider_id,
            data.model_name,
            data.context_window_tokens,
            data.supports_vision,
            data.supports_stream,
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
