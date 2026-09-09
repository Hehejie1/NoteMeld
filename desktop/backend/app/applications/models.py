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


class ApplicationData(Base):
    __tablename__ = "application_data"
    __table_args__ = (UniqueConstraint("app_id", "instance_id", "key", name="uq_application_data_key"),)
    id = Column(String, primary_key=True)
    app_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    instance_id = Column(String, ForeignKey("application_instances.id"), nullable=False, index=True)
    key = Column(String, nullable=False)
    value_json = Column(Text, nullable=False, default="null")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApplicationPermission(Base):
    __tablename__ = "application_permissions"
    __table_args__ = (UniqueConstraint("app_id", "permission", name="uq_application_permission"),)
    id = Column(String, primary_key=True)
    app_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    permission = Column(String, nullable=False)
    granted = Column(Integer, nullable=False, default=0)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApplicationJob(Base):
    __tablename__ = "application_jobs"
    __table_args__ = (Index("ix_application_jobs_run", "run_id", "created_at"),)
    job_id = Column(String, primary_key=True)
    app_id = Column(String, ForeignKey("applications.id"), nullable=False, index=True)
    instance_id = Column(String, ForeignKey("application_instances.id"), nullable=False, index=True)
    run_id = Column(String, ForeignKey("application_runs.run_id"), nullable=False, index=True)
    method = Column(String, nullable=False)
    input_json = Column(Text, nullable=False, default="{}")
    status = Column(String, nullable=False, default="queued")
    result_json = Column(Text, nullable=True)
    error_code = Column(String, nullable=True)
    error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class ApplicationJobEvent(Base):
    __tablename__ = "application_job_events"
    __table_args__ = (UniqueConstraint("job_id", "sequence", name="uq_application_job_event_sequence"),)
    id = Column(String, primary_key=True)
    job_id = Column(String, ForeignKey("application_jobs.job_id"), nullable=False, index=True)
    sequence = Column(Integer, nullable=False)
    event_type = Column(String, nullable=False)
    data_json = Column(Text, nullable=False, default="{}")
    created_at = Column(DateTime, server_default=func.now())


class ApplicationMigration(Base):
    __tablename__ = "application_app_migrations"
    migration_id = Column(String, primary_key=True)
    applied_at = Column(DateTime, server_default=func.now())


__all__ = ["Application", "ApplicationArtifact", "ApplicationData", "ApplicationInstance", "ApplicationJob", "ApplicationJobEvent", "ApplicationMigration", "ApplicationPermission", "ApplicationRun", "ApplicationSetting"]
