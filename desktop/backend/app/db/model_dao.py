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
        "context_window_tokens": model.context_window_tokens,
        "supports_vision": model.supports_vision,
        "supports_stream": model.supports_stream,
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
) -> dict:
    db = next(get_db())
    try:
        model = Model(
            provider_id=provider_id,
            model_name=model_name,
            context_window_tokens=context_window_tokens,
            supports_vision=supports_vision,
            supports_stream=supports_stream,
        )
        db.add(model)
        try:
            db.commit()
        except IntegrityError as error:
            db.rollback()
            raise ModelDuplicateError("同一供应商下模型名已存在") from error
        db.refresh(model)
        return _serialize_model(model)
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
