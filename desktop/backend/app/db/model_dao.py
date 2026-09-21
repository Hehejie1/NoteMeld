from app.db.engine import get_db
from app.db.models.models import Model
from app.db.models.providers import Provider
from sqlalchemy.exc import IntegrityError


class ModelDuplicateError(ValueError):
    """Raised when the persisted provider/model identity is already occupied."""


def _serialize_model(model: Model) -> dict:
    return {
        "id": model.id,
        "provider_id": model.provider_id,
        "model_name": model.model_name,
        "model_id": model.model_id or model.model_name,
        "display_name": model.display_name or model.model_name,
        "context_window_tokens": model.context_window_tokens,
        "max_input_tokens": model.max_input_tokens,
        "max_output_tokens": model.max_output_tokens,
        "supports_vision": model.supports_vision,
        "supports_stream": model.supports_stream,
        "enabled": int(model.enabled if model.enabled is not None else 1),
        "is_default": int(model.is_default if model.is_default is not None else 0),
        "test_status": model.test_status or "unknown",
        "created_at": model.created_at,
    }


def get_model_by_provider_and_name(provider_id: str, model_name: str) -> dict | None:
    db = next(get_db())
    try:
        model = db.query(Model).filter_by(provider_id=provider_id, model_name=model_name).first()
        if model:
            return _serialize_model(model)
        return None
    finally:
        db.close()


def insert_model(
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
    db = next(get_db())
    try:
        model = Model(
            provider_id=provider_id,
            model_name=model_name,
            model_id=model_id or model_name,
            display_name=display_name or model_name,
            context_window_tokens=context_window_tokens,
            max_input_tokens=max_input_tokens,
            max_output_tokens=max_output_tokens,
            supports_vision=supports_vision,
            supports_stream=supports_stream,
            enabled=enabled,
            is_default=is_default,
            test_status=test_status,
        )
        db.add(model)
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise ModelDuplicateError("同一供应商下模型已存在") from error
        db.refresh(model)
        return _serialize_model(model)
    finally:
        db.close()


def upsert_models_batch(
    provider_id: str,
    items: list[dict],
    *,
    default_model_id: str | None = None,
) -> dict:
    """按 (provider_id, model_id) 幂等批量保存多选模型，同事务去重。

    items 每项：model_id、display_name?、context_window_tokens、supports_vision?、
    supports_stream?、max_input_tokens?、max_output_tokens?、test_status?。
    返回 {"inserted": n, "existed": m}。default_model_id 命中时设为设备级唯一默认。
    """
    db = next(get_db())
    try:
        inserted = 0
        existed = 0
        seen_ids: set[str] = set()
        for item in items:
            mid = (item.get("model_id") or item.get("model_name") or "").strip()
            if not mid or mid in seen_ids:
                continue
            seen_ids.add(mid)
            display_name = (item.get("display_name") or mid).strip() or mid
            model = db.query(Model).filter_by(provider_id=provider_id, model_id=mid).first()
            if model is None:
                # 旧唯一约束基于 model_name：以 model_id 兼容旧语义
                model = Model(
                    provider_id=provider_id,
                    model_name=mid,
                    model_id=mid,
                    display_name=display_name,
                    context_window_tokens=item.get("context_window_tokens", 128000),
                    max_input_tokens=item.get("max_input_tokens", 3072),
                    max_output_tokens=item.get("max_output_tokens", 1024),
                    supports_vision=bool(item.get("supports_vision", False)),
                    supports_stream=bool(item.get("supports_stream", True)),
                    enabled=int(item.get("enabled", 1)),
                    is_default=0,
                    test_status=item.get("test_status", "unknown"),
                )
                db.add(model)
                inserted += 1
            else:
                model.model_name = model.model_name or mid
                model.display_name = display_name
                model.context_window_tokens = item.get(
                    "context_window_tokens", model.context_window_tokens or 128000
                )
                model.enabled = int(item.get("enabled", model.enabled if model.enabled is not None else 1))
                if item.get("test_status"):
                    model.test_status = item["test_status"]
                existed += 1

        if default_model_id:
            db.query(Model).filter(Model.is_default == 1).update({Model.is_default: 0}, synchronize_session=False)
            target = db.query(Model).filter_by(provider_id=provider_id, model_id=default_model_id).first()
            if target is not None:
                target.is_default = 1
                target.enabled = 1

        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise ModelDuplicateError("同一供应商下模型已存在") from error
        return {"inserted": inserted, "existed": existed}
    finally:
        db.close()


def set_default_model(provider_id: str, model_id: str) -> bool:
    """设备级唯一默认：先清空全部默认标记，再置目标模型。"""
    db = next(get_db())
    try:
        model = db.query(Model).filter_by(provider_id=provider_id, model_id=model_id).first()
        if model is None:
            return False
        db.query(Model).filter(Model.is_default == 1).update({Model.is_default: 0}, synchronize_session=False)
        model.is_default = 1
        model.enabled = 1
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_models_by_provider(provider_id: str) -> list[dict]:
    db = next(get_db())
    try:
        models = db.query(Model).filter_by(provider_id=provider_id).all()
        return [_serialize_model(model) for model in models]
    finally:
        db.close()


def delete_model(model_id: int) -> dict | None:
    db = next(get_db())
    try:
        model = db.query(Model).filter_by(id=model_id).first()
        if model:
            deleted_model = {
                "id": model.id,
                "provider_id": model.provider_id,
                "model_name": model.model_name,
            }
            db.delete(model)
            db.commit()
            return deleted_model
        return None
    finally:
        db.close()


def delete_model_with_capability(model_id: int) -> dict | None:
    """Delete a saved model and only its matching probe cache atomically."""
    from app.db.models.models import ModelCapability

    db = next(get_db())
    try:
        model = db.query(Model).filter_by(id=model_id).first()
        if model is None:
            return None
        deleted_model = {
            "id": model.id,
            "provider_id": model.provider_id,
            "model_name": model.model_name,
        }
        db.query(ModelCapability).filter_by(
            provider_id=model.provider_id,
            model_name=model.model_name,
        ).delete(synchronize_session=False)
        db.delete(model)
        db.commit()
        return deleted_model
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def get_all_models() -> list[dict]:
    db = next(get_db())
    try:
        # 只查询启用状态供应商的模型
        models = db.query(Model).join(Provider, Model.provider_id == Provider.id).filter(Provider.enabled == 1).all()
        return [_serialize_model(model) for model in models]
    finally:
        db.close()
