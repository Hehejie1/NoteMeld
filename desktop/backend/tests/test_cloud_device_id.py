import pytest

from app.cloud_sync.device_id import make_device_id


def test_device_id_is_stable_namespaced_and_does_not_include_raw_identifier():
    value = make_device_id("iOS", "vendor-install-secret")
    assert value.startswith("ios-")
    assert len(value) == len("ios-") + 32
    assert "vendor-install-secret" not in value
    assert make_device_id("iOS", "vendor-install-secret") == value
    assert make_device_id("android", "vendor-install-secret") != value


def test_device_id_rejects_missing_or_invalid_platform_data():
    with pytest.raises(ValueError):
        make_device_id("", "id")
    with pytest.raises(ValueError):
        make_device_id("ios", "")
