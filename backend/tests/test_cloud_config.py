from pathlib import Path
import pytest
from cloud.config import CloudSettings


def base(tmp_path: Path, **changes):
    values = {"data_dir": tmp_path / "data", "admin_username": "admin", "admin_password": "admin-password-123"}
    values.update(changes)
    return CloudSettings(**values)


def test_settings_reject_unsafe_production_values(tmp_path: Path):
    with pytest.raises(ValueError, match="CORS"):
        base(tmp_path, cors_origins=("*",)).validate()
    with pytest.raises(ValueError, match="HTTPS"):
        base(tmp_path, agent_base_url="http://agent.example.com").validate()


def test_settings_allow_local_agent_and_validate_limits(tmp_path: Path):
    base(tmp_path, agent_base_url="http://127.0.0.1:9000").validate()
    with pytest.raises(ValueError, match="limits"):
        base(tmp_path, max_request_bytes=0).validate()
    with pytest.raises(ValueError, match="max retries"):
        base(tmp_path, agent_max_retries=4).validate()
    with pytest.raises(ValueError, match="relay frame"):
        base(tmp_path, relay_max_frame_bytes=0).validate()


def test_settings_reject_non_positive_operation_timeouts(tmp_path: Path):
    with pytest.raises(ValueError, match="timeouts"):
        base(tmp_path, agent_timeout_seconds=0).validate()
    with pytest.raises(ValueError, match="timeouts"):
        base(tmp_path, command_wait_seconds=-1).validate()
