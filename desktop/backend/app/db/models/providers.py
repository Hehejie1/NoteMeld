from sqlalchemy import Column, String, Integer, DateTime, func

from app.db.engine import Base


class Provider(Base):
    __tablename__ = "providers"

    id = Column(String, primary_key=True)
    name = Column(String, nullable=False)
    logo = Column(String, nullable=False)
    # 废弃的明文列：历史数据迁移时加密入 api_key_ciphertext 后清空内容，列保留以避免表重建。
    api_key = Column(String, nullable=False)
    base_url = Column(String, nullable=False)
    enabled = Column(Integer, default=1)
    created_at = Column(DateTime, server_default=func.now())
    # notemeld.model-add.v1 协议字段
    display_name = Column(String, nullable=True)
    vendor_id = Column(String, nullable=False, server_default="custom")
    protocol = Column(String, nullable=False, server_default="openai-compatible")
    auth_type = Column(String, nullable=False, server_default="api_key")
    api_key_ciphertext = Column(String, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
