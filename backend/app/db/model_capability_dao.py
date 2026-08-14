from datetime import datetime
from typing import Optional

from app.db.engine import get_db
from app.db.models.models import ModelCapability


def _to_dict(row: Optional[ModelCapability]) -> Optional[dict]:
    if row is None:
        return None

    def serialize_datetime(value):
        return value.isoformat() if value is not None else None

    return {
        "id": row.id,
        "provider_id": row.provider_id,
        "model_name": row.model_name,
        "supports_json_mode": row.supports_json_mode,
        "supports_vision": row.supports_vision,
        "json_mode_checked_at": serialize_datetime(row.json_mode_checked_at),
        "vision_checked_at": serialize_datetime(row.vision_checked_at),
        "last_probe_error": row.last_probe_error or "",
        "updated_at": serialize_datetime(row.updated_at),
        "created_at": serialize_datetime(row.created_at),
    }


def get_model_capability(provider_id: str, model_name: str) -> Optional[dict]:
    db = next(get_db())
    try:
        row = db.query(ModelCapability).filter_by(provider_id=provider_id, model_name=model_name).first()
        return _to_dict(row)
    finally:
        db.close()


def delete_model_capability(provider_id: str, model_name: str) -> bool:
    """Remove only the disposable capability-probe cache for a saved model."""
    db = next(get_db())
    try:
        row = db.query(ModelCapability).filter_by(provider_id=provider_id, model_name=model_name).first()
        if row is None:
            return False
        db.delete(row)
        db.commit()
        return True
    finally:
        db.close()


def upsert_model_capability(
    provider_id: str,
    model_name: str,
    supports_json_mode: Optional[bool] = None,
    supports_vision: Optional[bool] = None,
    last_probe_error: str = "",
) -> dict:
    db = next(get_db())
    try:
        row = db.query(ModelCapability).filter_by(provider_id=provider_id, model_name=model_name).first()
        now = datetime.utcnow()
        if row is None:
            row = ModelCapability(provider_id=provider_id, model_name=model_name)
            db.add(row)

        if supports_json_mode is not None:
            row.supports_json_mode = supports_json_mode
            row.json_mode_checked_at = now
        if supports_vision is not None:
            row.supports_vision = supports_vision
            row.vision_checked_at = now
        row.last_probe_error = last_probe_error or ""
        row.updated_at = now

        db.commit()
        db.refresh(row)
        return _to_dict(row)
    finally:
        db.close()
