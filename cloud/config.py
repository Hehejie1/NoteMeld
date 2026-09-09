from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


@dataclass(frozen=True)
class CloudSettings:
    data_dir: Path
    admin_username: str
    admin_password: str
    admin_email: str | None = None
    otp_dev_mode: bool = True
    dev_otp_code: str = "888888"
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_username: str | None = None
    smtp_password: str | None = None
    smtp_sender: str | None = None
    smtp_starttls: bool = True
    invite_base_url: str = "http://localhost:3015"
    token_ttl_seconds: int = 30 * 24 * 60 * 60
    max_workspace_bytes: int = 1_000_000_000
    max_workspace_files: int = 10_000
    cors_origins: tuple[str, ...] = ()
    agent_base_url: str | None = None
    agent_model: str = "cloud-agent"
    agent_api_key: str | None = None
    agent_timeout_seconds: float = 120.0
    require_device_proof: bool = False
    command_wait_seconds: float = 20.0
    secret_key: str | None = None
    command_lease_seconds: int = 300
    max_request_bytes: int = 16 * 1024 * 1024
    approval_ttl_seconds: int = 900
    relay_backend: str = "memory"
    relay_url: str | None = None
    worker_count: int = 1
    device_online_ttl_seconds: int = 90
    agent_max_retries: int = 2
    relay_max_frame_bytes: int = 256 * 1024
    max_active_commands_per_user: int = 8
    workspace_warning_percent: int = 80
    max_workspace_read_bytes: int = 1_000_000
    max_workspace_list_items: int = 5_000
    max_backup_list_items: int = 1_000
    backup_storage_backend: str = "local"
    s3_endpoint_url: str | None = None
    s3_bucket: str | None = None
    s3_region: str | None = None
    s3_access_key_id: str | None = None
    s3_secret_access_key: str | None = None
    s3_prefix: str = "notemeld-backups"
    startup_backup_image: Path | None = None
    startup_backup_workspace: str = "default"
    deployment_env: str = "development"

    @property
    def database_path(self) -> Path:
        return self.data_dir / "cloud.db"

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    def validate(self) -> None:
        deployment_env = self.deployment_env.strip().lower()
        if deployment_env not in {"development", "test", "production"}:
            raise ValueError("deployment environment must be development, test, or production")
        if not self.admin_username.strip() or len(self.admin_password) < 8:
            raise ValueError("admin credentials are not strong enough")
        if self.admin_email is not None and ("@" not in self.admin_email or len(self.admin_email) > 320):
            raise ValueError("admin email is invalid")
        if not self.otp_dev_mode and (not self.smtp_host or not self.smtp_sender):
            raise ValueError("SMTP host and sender are required when development OTP mode is disabled")
        if not self.dev_otp_code.isdigit() or len(self.dev_otp_code) != 6:
            raise ValueError("development OTP code must be exactly six digits")
        if self.smtp_port < 1 or self.smtp_port > 65535:
            raise ValueError("SMTP port is invalid")
        parsed_invite_url = urlparse(self.invite_base_url)
        if parsed_invite_url.scheme not in {"http", "https"} or not parsed_invite_url.hostname:
            raise ValueError("invitation base URL must be an absolute HTTP(S) URL")
        if self.token_ttl_seconds <= 0:
            raise ValueError("token TTL must be positive")
        if self.max_workspace_bytes <= 0 or self.max_workspace_files <= 0 or self.max_request_bytes <= 0 or self.max_workspace_read_bytes <= 0 or self.max_workspace_list_items <= 0 or self.max_backup_list_items <= 0:
            raise ValueError("workspace and request limits must be positive")
        if self.agent_api_key and (not self.secret_key or len(self.secret_key) < 16):
            raise ValueError("cloud secret key is required for agent API key storage")
        if not 1 <= self.workspace_warning_percent <= 100:
            raise ValueError("workspace warning percent must be between 1 and 100")
        if "*" in self.cors_origins:
            raise ValueError("wildcard CORS is not allowed")
        if self.agent_base_url:
            parsed = urlparse(self.agent_base_url)
            local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if parsed.scheme != "https" and not local:
                raise ValueError("remote agent URL must use HTTPS")
        if self.relay_backend not in {"memory", "redis", "nats"}:
            raise ValueError("unsupported relay backend")
        if self.backup_storage_backend not in {"local", "s3"}:
            raise ValueError("unsupported backup storage backend")
        if self.backup_storage_backend == "s3" and not self.s3_bucket:
            raise ValueError("S3 bucket is required when S3 backup storage is enabled")
        if self.s3_endpoint_url:
            parsed = urlparse(self.s3_endpoint_url)
            if parsed.scheme not in {"http", "https"} or not parsed.hostname:
                raise ValueError("S3 endpoint must be an absolute HTTP(S) URL")
        if self.relay_backend == "redis":
            if not self.relay_url:
                raise ValueError("NOTEMELD_CLOUD_RELAY_URL is required for redis relay")
            parsed = urlparse(self.relay_url)
            if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
                raise ValueError("relay URL must use redis:// or rediss://")
            if parsed.scheme == "redis" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
                raise ValueError("remote relay URL must use rediss://")
        if self.worker_count < 1:
            raise ValueError("worker count must be positive")
        if self.device_online_ttl_seconds < 5:
            raise ValueError("device online TTL must be at least 5 seconds")
        if self.agent_timeout_seconds <= 0 or self.command_wait_seconds <= 0 or self.command_lease_seconds <= 0 or self.approval_ttl_seconds <= 0:
            raise ValueError("agent, command, lease and approval timeouts must be positive")
        if not 0 <= self.agent_max_retries <= 3:
            raise ValueError("agent max retries must be between 0 and 3")
        if self.relay_max_frame_bytes <= 0:
            raise ValueError("relay frame limit must be positive")
        if self.max_active_commands_per_user < 1:
            raise ValueError("active command limit must be positive")
        if self.relay_backend == "memory" and self.worker_count > 1:
            raise ValueError("memory relay cannot run with multiple workers")
        if deployment_env == "production":
            if self.otp_dev_mode:
                raise ValueError("production requires SMTP-backed OTP delivery")
            if not self.secret_key or len(self.secret_key) < 32:
                raise ValueError("production requires a 32-character cloud secret key")
            if not self.agent_base_url:
                raise ValueError("production requires an OpenAI-compatible agent provider")
            if self.backup_storage_backend != "s3":
                raise ValueError("production requires S3-compatible backup storage")
            if self.relay_backend == "memory":
                raise ValueError("production requires a durable relay backend")
            if not self.require_device_proof:
                raise ValueError("production requires device proof")
            if urlparse(self.invite_base_url).scheme != "https":
                raise ValueError("production invitation base URL must use HTTPS")
            if not self.cors_origins:
                raise ValueError("production requires explicit CORS origins")


def load_settings() -> CloudSettings:
    default_data_dir = Path(__file__).resolve().parent / "data"
    data_dir = Path(os.getenv("NOTEMELD_CLOUD_DATA_DIR", str(default_data_dir))).expanduser().resolve()
    return CloudSettings(
        data_dir=data_dir,
        admin_username=os.getenv("NOTEMELD_CLOUD_ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("NOTEMELD_CLOUD_ADMIN_PASSWORD", ""),
        admin_email=os.getenv("NOTEMELD_CLOUD_ADMIN_EMAIL") or None,
        otp_dev_mode=os.getenv("NOTEMELD_CLOUD_OTP_DEV_MODE", "1").strip().lower() in {"1", "true", "yes"},
        dev_otp_code=os.getenv("NOTEMELD_CLOUD_DEV_OTP_CODE", "888888"),
        smtp_host=os.getenv("NOTEMELD_CLOUD_SMTP_HOST") or None,
        smtp_port=int(os.getenv("NOTEMELD_CLOUD_SMTP_PORT", "587")),
        smtp_username=os.getenv("NOTEMELD_CLOUD_SMTP_USERNAME") or None,
        smtp_password=os.getenv("NOTEMELD_CLOUD_SMTP_PASSWORD") or None,
        smtp_sender=os.getenv("NOTEMELD_CLOUD_SMTP_SENDER") or None,
        smtp_starttls=os.getenv("NOTEMELD_CLOUD_SMTP_STARTTLS", "1").strip().lower() in {"1", "true", "yes"},
        invite_base_url=os.getenv("NOTEMELD_CLOUD_INVITE_BASE_URL", "http://localhost:3015").rstrip("/"),
        max_workspace_bytes=int(os.getenv("NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES", "1000000000")),
        max_workspace_files=int(os.getenv("NOTEMELD_CLOUD_MAX_WORKSPACE_FILES", "10000")),
        cors_origins=tuple(origin.strip() for origin in os.getenv("NOTEMELD_CLOUD_CORS_ORIGINS", "").split(",") if origin.strip()),
        agent_base_url=os.getenv("NOTEMELD_CLOUD_AGENT_BASE_URL") or None,
        agent_model=os.getenv("NOTEMELD_CLOUD_AGENT_MODEL", "cloud-agent"),
        agent_api_key=os.getenv("NOTEMELD_CLOUD_AGENT_API_KEY") or None,
        agent_timeout_seconds=float(os.getenv("NOTEMELD_CLOUD_AGENT_TIMEOUT_SECONDS", "120")),
        require_device_proof=os.getenv("NOTEMELD_CLOUD_REQUIRE_DEVICE_PROOF", "0").strip().lower() in {"1", "true", "yes"},
        command_wait_seconds=float(os.getenv("NOTEMELD_CLOUD_COMMAND_WAIT_SECONDS", "20")),
        secret_key=os.getenv("NOTEMELD_CLOUD_SECRET_KEY") or None,
        command_lease_seconds=int(os.getenv("NOTEMELD_CLOUD_COMMAND_LEASE_SECONDS", "300")),
        max_request_bytes=int(os.getenv("NOTEMELD_CLOUD_MAX_REQUEST_BYTES", str(16 * 1024 * 1024))),
        approval_ttl_seconds=int(os.getenv("NOTEMELD_CLOUD_APPROVAL_TTL_SECONDS", "900")),
        relay_backend=os.getenv("NOTEMELD_CLOUD_RELAY_BACKEND", "memory").strip().lower(),
        relay_url=os.getenv("NOTEMELD_CLOUD_RELAY_URL") or None,
        worker_count=int(os.getenv("WEB_CONCURRENCY", "1")),
        device_online_ttl_seconds=int(os.getenv("NOTEMELD_CLOUD_DEVICE_ONLINE_TTL_SECONDS", "90")),
        agent_max_retries=int(os.getenv("NOTEMELD_CLOUD_AGENT_MAX_RETRIES", "2")),
        relay_max_frame_bytes=int(os.getenv("NOTEMELD_CLOUD_RELAY_MAX_FRAME_BYTES", str(256 * 1024))),
        max_active_commands_per_user=int(os.getenv("NOTEMELD_CLOUD_MAX_ACTIVE_COMMANDS_PER_USER", "8")),
        workspace_warning_percent=int(os.getenv("NOTEMELD_CLOUD_WORKSPACE_WARNING_PERCENT", "80")),
        max_workspace_read_bytes=int(os.getenv("NOTEMELD_CLOUD_MAX_WORKSPACE_READ_BYTES", "1000000")),
        max_workspace_list_items=int(os.getenv("NOTEMELD_CLOUD_MAX_WORKSPACE_LIST_ITEMS", "5000")),
        max_backup_list_items=int(os.getenv("NOTEMELD_CLOUD_MAX_BACKUP_LIST_ITEMS", "1000")),
        backup_storage_backend=os.getenv("NOTEMELD_CLOUD_BACKUP_STORAGE", "local").strip().lower(),
        s3_endpoint_url=os.getenv("NOTEMELD_CLOUD_S3_ENDPOINT_URL") or None,
        s3_bucket=os.getenv("NOTEMELD_CLOUD_S3_BUCKET") or None,
        s3_region=os.getenv("NOTEMELD_CLOUD_S3_REGION") or None,
        s3_access_key_id=os.getenv("NOTEMELD_CLOUD_S3_ACCESS_KEY_ID") or None,
        s3_secret_access_key=os.getenv("NOTEMELD_CLOUD_S3_SECRET_ACCESS_KEY") or None,
        s3_prefix=os.getenv("NOTEMELD_CLOUD_S3_PREFIX", "notemeld-backups").strip("/") or "notemeld-backups",
        startup_backup_image=Path(os.getenv("NOTEMELD_CLOUD_STARTUP_BACKUP_IMAGE")).expanduser().resolve() if os.getenv("NOTEMELD_CLOUD_STARTUP_BACKUP_IMAGE") else None,
        startup_backup_workspace=os.getenv("NOTEMELD_CLOUD_STARTUP_BACKUP_WORKSPACE", "default"),
        deployment_env=os.getenv("NOTEMELD_CLOUD_ENV", "development").strip().lower(),
    )
