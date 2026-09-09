from kombu import uuid

from app.db.engine import get_db
from app.db.models.provider_templates import ProviderTemplate
from app.utils.logger import get_logger

logger = get_logger(__name__)


def list_provider_templates():
    db = next(get_db())
    try:
        return db.query(ProviderTemplate).order_by(ProviderTemplate.created_at.desc()).all()
    finally:
        db.close()


def upsert_provider_template(name: str, logo: str, base_url: str):
    db = next(get_db())
    try:
        template = db.query(ProviderTemplate).filter_by(name=name).first()
        if template is None:
            template = ProviderTemplate(
                id=uuid().lower(),
                name=name,
                logo=logo or "custom",
                base_url=base_url,
            )
            db.add(template)
        else:
            template.logo = logo or "custom"
            template.base_url = base_url
        db.commit()
        db.refresh(template)
        logger.info("Provider template saved successfully. name: %s", name)
        return template
    except Exception as e:
        db.rollback()
        logger.error("Failed to save provider template: %s", e)
        raise
    finally:
        db.close()
