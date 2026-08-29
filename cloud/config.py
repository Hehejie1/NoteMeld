from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CloudSettings:
    data_dir: Path
    admin_username: str
    admin_password: str
    token_ttl_seconds: int = 30 * 24 * 60 * 60

    @property
    def database_path(self) -> Path:
        return self.data_dir / "cloud.db"

    @property
    def workspaces_dir(self) -> Path:
        return self.data_dir / "workspaces"


def load_settings() -> CloudSettings:
    data_dir = Path(os.getenv("NOTEMELD_CLOUD_DATA_DIR", "cloud_data")).expanduser().resolve()
    return CloudSettings(
        data_dir=data_dir,
        admin_username=os.getenv("NOTEMELD_CLOUD_ADMIN_USERNAME", "admin"),
        admin_password=os.getenv("NOTEMELD_CLOUD_ADMIN_PASSWORD", ""),
    )
