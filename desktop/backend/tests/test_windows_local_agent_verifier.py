from pathlib import Path


SCRIPT = (
    Path(__file__).parents[3]
    / "scripts"
    / "release"
    / "verify_first_batch_windows_local_agent.ps1"
).read_text(encoding="utf-8")


def test_windows_local_agent_ui_verifier_requires_bound_runtime_subcheck():
    assert 'Assert-PassEvidence $RuntimeEvidence @("WINDOWS-LOCAL-AGENT-RUNTIME")' in SCRIPT
    assert "runtime.installed_package.version" in SCRIPT
    assert "runtime.model" in SCRIPT
    assert "runtime_evidence_sha256" in SCRIPT


def test_windows_local_agent_ui_verifier_binds_signed_running_x64_executable():
    assert "Get-AuthenticodeSignature" in SCRIPT
    assert "ExpectedInstaller" in SCRIPT
    assert "windows_installer_sha256" in SCRIPT
    assert "Installer and running executable use different Authenticode signers" in SCRIPT
    assert "0x8664" in SCRIPT
    assert "ProductVersion" in SCRIPT
    assert "runtime.installed_package.sha256" in SCRIPT
    assert "MainWindowHandle -ne 0" in SCRIPT
    assert 'Find-ElementExact $root "notemeld-build-commit:$ExpectedCommit"' in SCRIPT


def test_windows_local_agent_ui_verifier_drives_model_input_and_unique_answer():
    for marker in (
        "notemeld-local-agent-model:",
        "notemeld-local-agent-model-option:",
        "notemeld-local-agent-input",
        "notemeld-local-agent-send-idle",
        "notemeld-local-agent-assistant:turn.succeeded:1:",
    ):
        assert marker in SCRIPT
    assert "answerMatches.Count -gt 1" in SCRIPT
    assert 'release_checks = @{ x_01 = "PASS"; x_02 = "PASS" }' in SCRIPT
    output = SCRIPT.split("$result = [ordered]@{", 1)[1]
    assert "challenge_sha256" in output
    assert "challenge =" not in output.lower()
    assert "ui_driven = $true" in output
