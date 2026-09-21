from pathlib import Path


SCRIPT = (
    Path(__file__).parents[3]
    / "scripts"
    / "release"
    / "verify_first_batch_windows_host_restart.ps1"
).read_text(encoding="utf-8")


def test_windows_host_restart_verifier_binds_rc_and_real_cloud_host_evidence():
    assert 'Assert-PassEvidence $CloudEvidence @("C-01", "C-02")' in SCRIPT
    assert 'Assert-PassEvidence $RemoteHostEvidence @("C-04", "X-06")' in SCRIPT
    assert "rc_commit" in SCRIPT
    assert "host_device_id" in SCRIPT
    assert "cloud_persisted_commands" in SCRIPT
    assert "cloud_persisted_events" in SCRIPT
    assert "$hostEvidence.cloud_image_digest -ne $cloud.cloud_image_digest" in SCRIPT
    assert "build_commit = $cloud.build_commit" in SCRIPT
    assert "cloud_image_digest = $cloud.cloud_image_digest" in SCRIPT


def test_windows_host_restart_verifier_requires_signed_installed_app_and_stable_os_identity():
    assert "Get-AuthenticodeSignature" in SCRIPT
    assert "0x8664" in SCRIPT
    assert "ProductVersion" in SCRIPT
    assert "notemeld-cloud-host:running:" in SCRIPT
    assert '"notemeld-build-commit:$ExpectedCommit"' in SCRIPT
    assert "CloseMainWindow" in SCRIPT
    assert "Start-Process -FilePath $InstalledExe" in SCRIPT
    assert "Windows restart changed the Credential Manager Host identity" in SCRIPT


def test_windows_host_restart_verifier_proves_cloud_visibility_without_emitting_token():
    assert 'GetEnvironmentVariable("NOTEMELD_CLOUD_ACCOUNT_TOKEN")' in SCRIPT
    assert 'Invoke-CloudGet $BaseUrl "/v1/devices" $Token' in SCRIPT
    assert "last_seen_at" in SCRIPT
    assert "Cloud heartbeat did not advance" in SCRIPT
    assert "pre_restart_remote_evidence_sha256" in SCRIPT
    output_block = SCRIPT.split("$result = [ordered]@{", 1)[1]
    assert "accountToken" not in output_block
    assert "x_03" in output_block
