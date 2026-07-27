from fastapi import APIRouter
from pydantic import BaseModel

from app.services.model_capability import ModelCapabilityService
from app.services.model import ModelService
from app.utils.response import ResponseWrapper as R
router = APIRouter()
modelService = ModelService()
class CreateModelRequest(BaseModel):
    provider_id: str
    model_name: str


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
        return R.success(modelService.get_all_models(True),msg="获取模型列表成功")
    except Exception as e:
        return R.error(e)
@router.get("/models/delete/{model_id}")
def delete_model(model_id: int):
    try:
        success = modelService.delete_model_by_id(model_id)
        if success:
            return R.success(msg="模型删除成功")
        else:
            return R.error("模型不存在或删除失败")
    except Exception as e:
        return R.error(f"删除模型失败: {e}")
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
    success = ModelService.add_new_model(data.provider_id, data.model_name)
    if not success:
        return R.error("模型添加失败")
    return R.success(msg="模型添加成功")


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
        return R.success(models, msg="获取启用模型成功")
    except Exception as e:
        return R.error(f"获取启用模型失败: {e}")
