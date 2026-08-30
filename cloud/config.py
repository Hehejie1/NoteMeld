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

    @property
    def database_path(self) -> Path:
        return self.data_dir / "cloud.db"

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"

    def validate(self) -> None:
        if not self.admin_username.strip() or len(self.admin_password) < 12:
            raise ValueError("admin credentials are not strong enough")
        if self.max_workspace_bytes <= 0 or self.max_workspace_files <= 0 or self.max_request_bytes <= 0:
            raise ValueError("workspace and request limits must be positive")
        if "*" in self.cors_origins:
            raise ValueError("wildcard CORS is not allowed")
        if self.agent_base_url:
            parsed = urlparse(self.agent_base_url)
            local = parsed.hostname in {"localhost", "127.0.0.1", "::1"}
            if parsed.scheme != "https" and not local:
                raise ValueError("remote agent URL must use HTTPS")
        if self.relay_backend not in {"memory", "redis", "nats"}:
            raise ValueError("unsupported relay backend")
        if self.relay_backend == "redis":
            if not self.relay_url:
                raise ValueError("NOTEMELD_CLOUD_RELAY_URL is required for redis relay")
            parsed = urlparse(self.relay_url)
            if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
                raise ValueError("relay URL must use redis:// or rediss://")
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
        if self.relay_backend == "memory" and self.worker_count > 1:
            raise ValueError("memory relay cannot run with multiple workers")


def load_settings() -> CloudSettings:
    data_dir = Path(os.getenv("NOTEMELD_CLOUD_DATA_DIR", "cloud_data")).expanduser().resolve()
    return CloudSettings(
        data_dir=data_dir,
        admin_username=os.getenv("NOTEMELD_CLOUD_ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("NOTEMELD_CLOUD_ADMIN_PASSWORD", ""),
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
    )
