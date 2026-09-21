from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]


def test_windows_remote_verifier_drives_accessible_installed_ui_and_redacts_evidence():
    script = (ROOT / "scripts" / "release" / "verify_first_batch_windows_remote.ps1").read_text(encoding="utf-8")
    for contract in (
        "Is64BitOperatingSystem",
        "InstalledExe",
        "Get-AuthenticodeSignature",
        "0x8664",
        "MainWindowHandle",
        "ProductVersion",
        "ExpectedCommit",
        'notemeld-remote-host:$HostDeviceId',
        'notemeld-remote-host-option:$HostDeviceId',
        "ExpandCollapsePattern",
        "SelectionItemPattern",
        "notemeld-remote-connect",
        'notemeld-remote-transport-$ExpectedTransport',
        "notemeld-remote-input",
        "notemeld-remote-send-idle",
        "notemeld-remote-assistant:",
        "notemeld-remote-terminal-turn.succeeded",
        "challenge_sha256",
        "answer_sha256",
        "host_device_sha256",
        'notemeld-build-commit:$ExpectedCommit',
    ):
        assert contract in script
    assert "challenge = $challenge" not in script
    assert "host_device_id = $HostDeviceId" not in script
    assert '$_.Path -eq $InstalledExe' in script


def test_windows_remote_verifier_binds_prior_cloud_and_real_host_evidence():
    script = (ROOT / "scripts" / "release" / "verify_first_batch_windows_remote.ps1").read_text(encoding="utf-8")
    assert 'Assert-PassEvidence $CloudEvidence @("C-01", "C-02")' in script
    assert 'Assert-PassEvidence $RemoteHostEvidence @("C-04", "X-06")' in script
    assert '$host.host_device_id -ne $HostDeviceId' in script
    assert '$host.cloud_persisted_commands -ne 0' in script
    assert '$cloud.rc_commit -ne $ExpectedCommit' in script
    assert "$cloud.base_url.TrimEnd('/') -ne $host.base_url.TrimEnd('/')" in script
    assert "$host.cloud_image_digest -ne $cloud.cloud_image_digest" in script
    assert "build_commit = $cloud.build_commit" in script
    assert "cloud_image_digest = $cloud.cloud_image_digest" in script
    assert 'if ($ExpectedTransport -eq "lan") { "x_04" } else { "x_05" }' in script
