from pathlib import Path
import pytest
from cloud.config import CloudSettings


def settings(tmp_path: Path, **changes):
    values = {"data_dir": tmp_path / "data", "admin_username": "admin", "admin_password": "admin-password-123"}
    values.update(changes)
    return CloudSettings(**values)


def test_memory_relay_rejects_multiple_workers(tmp_path: Path):
    with pytest.raises(ValueError, match="multiple workers"):
        settings(tmp_path, worker_count=2).validate()


def test_unknown_relay_backend_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="unsupported relay"):
        settings(tmp_path, relay_backend="unknown").validate()
