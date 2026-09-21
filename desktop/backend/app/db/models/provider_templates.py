from sqlalchemy import Column, DateTime, String, func

from app.db.engine import Base


class ProviderTemplate(Base):
    __tablename__ = "provider_templates"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False, unique=True)
    logo = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
