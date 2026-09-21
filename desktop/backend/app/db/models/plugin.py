from sqlalchemy import Column, DateTime, Integer, String, Text, func

from app.db.engine import Base


class PluginInstallation(Base):
    __tablename__ = "plugin_installations"

    plugin_id = Column(String, primary_key=True)
    active_version = Column(String, nullable=True)
    enabled = Column(Integer, nullable=False, default=0)
    runtime_status = Column(String, nullable=False, default="disabled")
    runtime_pid = Column(Integer, nullable=True)
    requested_permissions_json = Column(Text, nullable=False, default="[]")
    granted_permissions_json = Column(Text, nullable=False, default="[]")
    manifest_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class PluginVersion(Base):
    __tablename__ = "plugin_versions"

    id = Column(String, primary_key=True)
    plugin_id = Column(String, nullable=False, index=True)
    version = Column(String, nullable=False)
    sha256 = Column(String, nullable=False)
    path = Column(String, nullable=False)
    license = Column(String, nullable=False)
    sdk_version = Column(String, nullable=False)
    manifest_json = Column(Text, nullable=False, default="{}")
    installed_at = Column(DateTime, server_default=func.now())


class PluginAuditEvent(Base):
    __tablename__ = "plugin_audit_events"

    id = Column(String, primary_key=True)
    plugin_id = Column(String, nullable=False, index=True)
    action = Column(String, nullable=False)
    actor = Column(String, nullable=False, default="user")
    version = Column(String, nullable=True)
    detail_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())


class PluginMigration(Base):
    __tablename__ = "plugin_migrations"

    migration_id = Column(String, primary_key=True)
    applied_at = Column(DateTime, server_default=func.now())
