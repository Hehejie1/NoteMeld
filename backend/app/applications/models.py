from __future__ import annotations

from sqlalchemy import Column, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint, func

from app.db.engine import Base


class Application(Base):
    __tablename__ = "applications"
    id = Column(String, primary_key=True)
    version = Column(String, nullable=False)
    name = Column(String, nullable=False)
    manifest_json = Column(Text, nullable=False, default="{}")
    manifest_sha256 = Column(String, nullable=False)
    enabled = Column(Integer, nullable=False, default=1)
    status = Column(String, nullable=False, default="installed")
    installed_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApplicationInstance(Base):
    __tablename__ = "application_instances"
    id = Column(String, primary_key=True)
    app_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    title = Column(String, nullable=False, default="")
    workspace_ref = Column(String, nullable=False)
    status = Column(String, nullable=False, default="ready")
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApplicationRun(Base):
    __tablename__ = "application_runs"
    __table_args__ = (Index("uq_application_runs_request_id", "app_id", "instance_id", "request_id", unique=True),)
    run_id = Column(String, primary_key=True)
    app_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    instance_id = Column(String, ForeignKey("application_instances.id"), nullable=False, index=True)
    request_id = Column(String, nullable=True)
    payload_hash = Column(String, nullable=False)
    runtime_kind = Column(String, nullable=False)
    status = Column(String, nullable=False, default="queued")
    cancel_requested = Column(Integer, nullable=False, default=0)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApplicationArtifact(Base):
    __tablename__ = "application_artifacts"
    artifact_id = Column(String, primary_key=True)
    app_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    instance_id = Column(String, ForeignKey("application_instances.id"), nullable=False, index=True)
    run_id = Column(String, ForeignKey("application_runs.run_id"), nullable=True, index=True)
    kind = Column(String, nullable=False)
    summary = Column(Text, nullable=False, default="")
    data_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())


class ApplicationSetting(Base):
    __tablename__ = "application_settings"
    __table_args__ = (UniqueConstraint("app_id", "key", name="uq_application_settings_app_key"),)
    id = Column(String, primary_key=True)
    app_id = Column(String, nullable=True, index=True)
    key = Column(String, nullable=False)
    value_json = Column(Text, nullable=False, default="{}")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApplicationMigration(Base):
    __tablename__ = "application_app_migrations"
    migration_id = Column(String, primary_key=True)
    applied_at = Column(DateTime, server_default=func.now())


__all__ = ["Application", "ApplicationArtifact", "ApplicationInstance", "ApplicationMigration", "ApplicationRun", "ApplicationSetting"]
