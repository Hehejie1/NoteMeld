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
    with pytest.raises(ValueError, match="warning percent"):
        base(tmp_path, workspace_warning_percent=101).validate()
    with pytest.raises(ValueError, match="limits"):
        base(tmp_path, max_workspace_read_bytes=0).validate()
    with pytest.raises(ValueError, match="limits"):
        base(tmp_path, max_backup_list_items=0).validate()


def test_settings_reject_non_positive_operation_timeouts(tmp_path: Path):
    with pytest.raises(ValueError, match="timeouts"):
        base(tmp_path, agent_timeout_seconds=0).validate()
    with pytest.raises(ValueError, match="timeouts"):
        base(tmp_path, command_wait_seconds=-1).validate()


def test_settings_reject_non_positive_token_ttl(tmp_path: Path):
    with pytest.raises(ValueError, match="token TTL"):
        base(tmp_path, token_ttl_seconds=0).validate()


def test_settings_require_secret_key_when_agent_api_key_is_configured(tmp_path: Path):
    with pytest.raises(ValueError, match="secret key"):
        base(tmp_path, agent_api_key="provider-key").validate()
    with pytest.raises(ValueError, match="secret key"):
        base(tmp_path, agent_api_key="provider-key", secret_key="short").validate()
    base(tmp_path, agent_api_key="provider-key", secret_key="a" * 16).validate()


def test_production_settings_fail_closed_without_real_runtime_dependencies(tmp_path: Path):
    with pytest.raises(ValueError, match="SMTP-backed OTP"):
        base(tmp_path, deployment_env="production").validate()

    with pytest.raises(ValueError, match="OpenAI-compatible agent provider"):
        base(
            tmp_path,
            deployment_env="production",
            otp_dev_mode=False,
            smtp_host="smtp.example.com",
            smtp_sender="no-reply@example.com",
            secret_key="s" * 32,
        ).validate()


def test_production_settings_accept_explicit_provider_storage_relay_and_origins(tmp_path: Path):
    base(
        tmp_path,
        deployment_env="production",
        otp_dev_mode=False,
        smtp_host="smtp.example.com",
        smtp_sender="no-reply@example.com",
        secret_key="s" * 32,
        agent_base_url="https://agent.example.com/v1",
        backup_storage_backend="s3",
        s3_bucket="notemeld-backups",
        relay_backend="redis",
        relay_url="rediss://redis.example.com:6380/0",
        require_device_proof=True,
        invite_base_url="https://app.example.com",
        cors_origins=("https://app.example.com",),
    ).validate()


def test_compose_forwards_production_runtime_configuration(tmp_path: Path):
    del tmp_path
    compose = (Path(__file__).resolve().parents[3] / "cloud" / "compose.yaml").read_text(encoding="utf-8")
    for variable in (
        "NOTEMELD_CLOUD_ENV",
        "NOTEMELD_CLOUD_OTP_DEV_MODE",
        "NOTEMELD_CLOUD_SMTP_HOST",
        "NOTEMELD_CLOUD_INVITE_BASE_URL",
        "NOTEMELD_CLOUD_BACKUP_STORAGE",
        "NOTEMELD_CLOUD_S3_BUCKET",
        "NOTEMELD_CLOUD_AGENT_BASE_URL",
        "NOTEMELD_CLOUD_REQUIRE_DEVICE_PROOF",
        "NOTEMELD_CLOUD_RELAY_BACKEND",
    ):
        assert variable in compose
