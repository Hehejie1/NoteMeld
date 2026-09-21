from app.db.models.providers import Provider
from app.utils.logger import get_logger
from app.db.engine import get_db

logger = get_logger(__name__)


def insert_provider(
    id: str,
    name: str,
    api_key: str,
    base_url: str,
    logo: str,
    enabled: int = 1,
    api_key_ciphertext: str | None = None,
    display_name: str | None = None,
    vendor_id: str = "custom",
    protocol: str = "openai-compatible",
    auth_type: str = "api_key",
):
    db = next(get_db())
    try:
        provider = Provider(
            id=id,
            name=name,
            api_key=api_key,
            base_url=base_url,
            logo=logo,
            enabled=enabled,
            api_key_ciphertext=api_key_ciphertext,
            display_name=display_name or name,
            vendor_id=vendor_id,
            protocol=protocol,
            auth_type=auth_type,
        )
        db.add(provider)
        db.commit()
        logger.info(f"Provider inserted successfully. id: {id}, name: {name}")
        return id
    except Exception:
        db.rollback()
        logger.exception(f"Failed to insert provider. id: {id}")
        raise
    finally:
        db.close()


def get_enabled_providers():
    db = next(get_db())
    try:
        return db.query(Provider).filter_by(enabled=1).all()
    finally:
        db.close()


def get_provider_by_name(name: str):
    db = next(get_db())
    try:
        return db.query(Provider).filter_by(name=name).first()
    finally:
        db.close()


def get_provider_by_id(id: str):
    db = next(get_db())
    try:
        return db.query(Provider).filter_by(id=id).first()
    finally:
        db.close()


def get_all_providers():
    db = next(get_db())
    try:
        return db.query(Provider).all()
    finally:
        db.close()


def update_provider(id: str, **kwargs):
    db = next(get_db())
    try:
        provider = db.query(Provider).filter_by(id=id).first()
        if not provider:
            logger.warning(f"Provider {id} not found for update.")
            return None

        for key, value in kwargs.items():
            if hasattr(provider, key):
                setattr(provider, key, value)

        db.commit()
        # 日志只允许出现字段名，绝不打印值（值中可能含密钥/密文）
        logger.info(f"Provider updated successfully. id: {id}, updated_fields: {list(kwargs.keys())}")
        return id
    except Exception:
        db.rollback()
        logger.exception(f"Failed to update provider. id: {id}")
        raise
    finally:
        db.close()


def delete_provider(id: str):
    db = next(get_db())
    try:
        provider = db.query(Provider).filter_by(id=id).first()
        if provider:
            db.delete(provider)
            db.commit()
            logger.info(f"Provider deleted successfully. id: {id}")
            return id
        return None
    except Exception:
        db.rollback()
        logger.exception(f"Failed to delete provider. id: {id}")
        raise
    finally:
        db.close()
