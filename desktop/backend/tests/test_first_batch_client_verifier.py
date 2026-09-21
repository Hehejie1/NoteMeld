from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess

import pytest


SCRIPT = Path(__file__).resolve().parents[3] / "scripts" / "release" / "verify_first_batch_clients.py"
SPEC = importlib.util.spec_from_file_location("verify_first_batch_clients", SCRIPT)
assert SPEC and SPEC.loader
verifier = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(verifier)

RC_COMMIT = "a" * 40
SIGNED_APK_BYTES = b"signed-first-batch-android-rc"
SIGNED_APK_SHA256 = verifier.hashlib.sha256(SIGNED_APK_BYTES).hexdigest()


def android_a01_evidence() -> dict:
    return {
        "evidence_schema": "notemeld.first-batch-live-evidence.v1",
        "bound_gate_ids": ["A-01"],
        "release_checks": {"a_01": "PASS"},
        "rc_version": "0.0.4",
        "version_name": "0.0.4",
        "rc_commit": RC_COMMIT,
        "build_commit": RC_COMMIT,
        "source_sha256": "d" * 64,
        "installed_package": {
            "apk_sha256": SIGNED_APK_SHA256,
            "signer_sha256": "b" * 64,
        },
    }


def test_desktop_verifier_requires_windows_x64_real_model_and_unique_terminal():
    challenge = "NM-X64-test"

    def request(_base_url, method, path, *, payload=None, session_token=None):
        assert session_token == "session-secret"
        if path == "/api/sys_health":
            return None
        if path == "/api/model_list":
            return [{"id": "model-a", "model_name": "provider/model-a"}]
        if path == "/api/agent/v1/sessions":
            return {"id": "session-a"}
        if path.endswith("/turns"):
            assert payload["model"] == "model-a"
            assert challenge in payload["input"]
            return {"turn_id": "turn-a"}
        if path.endswith("/diagnostics"):
            return {
                "turn": {"status": "succeeded"},
                "events": [
                    {"sequence": 0, "type": "message.delta", "payload": {"delta": challenge}},
                    {"sequence": 1, "type": "turn.succeeded", "payload": {}},
                ],
            }
        raise AssertionError((method, path, payload))

    result = verifier.run_desktop(
        "http://127.0.0.1:8483",
        "model-a",
        1,
        session_token="session-secret",
        request_fn=request,
        challenge=challenge,
        system_fn=lambda: "Windows",
        machine_fn=lambda: "AMD64",
        expected_version="1.2.3",
        installed_exe="C:/Program Files/NoteMeld/NoteMeld.exe",
        executable_inspector=lambda path, version: {
            "version": version,
            "sha256": "a" * 64,
            "signer_thumbprint": "b" * 40,
        },
    )

    assert result["release_checks"] == {"windows_local_agent_runtime": "PASS"}
    assert result["installed_package"]["version"] == "1.2.3"
    assert result["terminal_event"] == "turn.succeeded"
    assert challenge not in str(result)
    assert "session-secret" not in str(result)


def test_desktop_verifier_fails_closed_off_windows_or_without_model():
    with pytest.raises(verifier.VerificationError, match="Windows x64"):
        verifier.run_desktop(
            "http://127.0.0.1:8483", "model-a", 1,
            request_fn=lambda *_args, **_kwargs: None,
            system_fn=lambda: "Darwin", machine_fn=lambda: "arm64",
        )
    with pytest.raises(verifier.VerificationError, match="real local model"):
        verifier.run_desktop(
            "http://127.0.0.1:8483", "deterministic-test", 1,
            request_fn=lambda *_args, **_kwargs: None,
            system_fn=lambda: "Windows", machine_fn=lambda: "AMD64",
        )


def test_windows_package_inspector_requires_running_signed_x64_pe(tmp_path):
    executable = tmp_path / "NoteMeld.exe"
    image = bytearray(512)
    image[:2] = b"MZ"
    image[0x3C:0x40] = (128).to_bytes(4, "little")
    image[128:132] = b"PE\0\0"
    image[132:134] = (0x8664).to_bytes(2, "little")
    executable.write_bytes(image)

    def runner(command, **kwargs):
        assert command[-1] == str(executable.resolve())
        assert kwargs["timeout"] == 30 and kwargs["check"] is False
        return subprocess.CompletedProcess(
            command,
            0,
            '{"status":"Valid","version":"1.2.3.0","running":true,"thumbprint":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA"}',
            "",
        )

    result = verifier._inspect_windows_executable(str(executable), "1.2.3", runner=runner)

    assert result["version"] == "1.2.3.0"
    assert result["signer_thumbprint"] == "a" * 40
    assert len(result["sha256"]) == 64


def test_desktop_verifier_requires_complete_package_arguments_for_runtime_evidence():
    with pytest.raises(verifier.VerificationError, match="requires both"):
        verifier.run_desktop(
            "http://127.0.0.1:8483", "model-a", 1,
            expected_version="1.2.3",
            system_fn=lambda: "Windows",
            machine_fn=lambda: "AMD64",
        )


def test_windows_package_inspector_rejects_unsigned_or_non_x64_binary(tmp_path):
    executable = tmp_path / "NoteMeld.exe"
    image = bytearray(512)
    image[:2] = b"MZ"
    image[0x3C:0x40] = (128).to_bytes(4, "little")
    image[128:132] = b"PE\0\0"
    image[132:134] = (0x014C).to_bytes(2, "little")
    executable.write_bytes(image)
    with pytest.raises(verifier.VerificationError, match="not x86_64"):
        verifier._inspect_windows_executable(str(executable), "1.2.3", runner=lambda *_args, **_kwargs: None)

    image[132:134] = (0x8664).to_bytes(2, "little")
    executable.write_bytes(image)
    invalid = subprocess.CompletedProcess([], 0, '{"status":"NotSigned","version":"1.2.3","running":true,"thumbprint":""}', "")
    with pytest.raises(verifier.VerificationError, match="valid Authenticode"):
        verifier._inspect_windows_executable(str(executable), "1.2.3", runner=lambda *_args, **_kwargs: invalid)


def test_android_runtime_verifier_cold_launches_and_redacts_device_id():
    serial = "physical-device-secret"
    commit = "a" * 40

    def runner(command, **_kwargs):
        joined = " ".join(command)
        outputs = {
            "adb devices -l": f"List of devices attached\n{serial} device product:test\n",
            f"adb -s {serial} shell pm path com.notemeld.mobile": "package:/data/app/notemeld.apk\n",
            f"adb -s {serial} shell getprop ro.build.version.release": "14\n",
            f"adb -s {serial} shell getprop ro.product.cpu.abi": "arm64-v8a\n",
            f"adb -s {serial} shell getprop ro.kernel.qemu": "0\n",
            f"adb -s {serial} shell dumpsys package com.notemeld.mobile": "  versionName=0.0.4\n",
            f"adb -s {serial} shell am force-stop com.notemeld.mobile": "",
            f"adb -s {serial} shell am start -W -n com.notemeld.mobile/.MainActivity": "Status: ok\nTotalTime: 100\n",
            f"adb -s {serial} shell pidof com.notemeld.mobile": "4242\n",
            f"adb -s {serial} logcat -d --pid 4242 -t 200": "I NoteMeld: ready\n",
            f"adb -s {serial} shell uiautomator dump /data/local/tmp/notemeld-first-batch-ui.xml": "UI hierarchy dumped\n",
            f"adb -s {serial} exec-out cat /data/local/tmp/notemeld-first-batch-ui.xml": f'<hierarchy><node content-desc="notemeld-build-commit:{commit}" /></hierarchy>',
        }
        assert joined in outputs
        return subprocess.CompletedProcess(command, 0, outputs[joined], "")

    result = verifier.run_android_runtime("adb", None, "com.notemeld.mobile", "0.0.4", expected_commit=commit, runner=runner, sleep_fn=lambda _seconds: None)

    assert result["release_checks"] == {"android_runtime_smoke": "PASS"}
    assert result["process_alive"] is True
    assert result["build_commit"] == commit
    assert serial not in str(result)


def test_android_runtime_verifier_rejects_invalid_commit_before_adb():
    with pytest.raises(verifier.VerificationError, match="full 40-character SHA"):
        verifier.run_android_runtime(
            "adb", None, "com.notemeld.mobile", "0.0.4", expected_commit="short",
            runner=lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("adb must not run")),
        )


def test_android_release_apk_verifier_binds_signed_artifact_to_installed_bytes(tmp_path):
    expected = tmp_path / "notemeld-release.apk"
    expected.write_bytes(b"signed-rc-apk")
    signer = "ab" * 32

    def runner(command, **_kwargs):
        if command[0] == "apksigner":
            return subprocess.CompletedProcess(
                command,
                0,
                f"Verified using v2 scheme (APK Signature Scheme v2): true\n"
                f"Signer #1 certificate SHA-256 digest: {signer}\n",
                "",
            )
        if command[:5] == ["adb", "-s", "physical-device", "pull", "/data/app/notemeld.apk"]:
            Path(command[-1]).write_bytes(expected.read_bytes())
            return subprocess.CompletedProcess(command, 0, "1 file pulled\n", "")
        raise AssertionError(command)

    result = verifier._verify_installed_android_apk(
        "adb",
        "physical-device",
        "/data/app/notemeld.apk",
        str(expected),
        signer,
        "apksigner",
        runner=runner,
    )

    assert result == {
        "apk_sha256": verifier.hashlib.sha256(expected.read_bytes()).hexdigest(),
        "signer_sha256": signer,
    }


def test_android_release_apk_verifier_rejects_installed_byte_mismatch(tmp_path):
    expected = tmp_path / "notemeld-release.apk"
    expected.write_bytes(b"signed-rc-apk")
    signer = "cd" * 32

    def runner(command, **_kwargs):
        if command[0] == "apksigner":
            return subprocess.CompletedProcess(
                command,
                0,
                f"Verified using v3 scheme (APK Signature Scheme v3): true\n"
                f"Signer #1 certificate SHA-256 digest: {signer}\n",
                "",
            )
        Path(command[-1]).write_bytes(b"different-installed-apk")
        return subprocess.CompletedProcess(command, 0, "1 file pulled\n", "")

    with pytest.raises(verifier.VerificationError, match="bytes do not match"):
        verifier._verify_installed_android_apk(
            "adb",
            "physical-device",
            "/data/app/notemeld.apk",
            str(expected),
            signer,
            "apksigner",
            runner=runner,
        )


def test_android_agent_artifact_evidence_requires_bound_a01_rc_identity():
    assert verifier._validate_android_artifact_evidence(
        "0.0.4", RC_COMMIT, android_a01_evidence()
    ) == {"apk_sha256": SIGNED_APK_SHA256, "source_sha256": "d" * 64}

    wrong_commit = android_a01_evidence()
    wrong_commit["rc_commit"] = "c" * 40
    with pytest.raises(verifier.VerificationError, match="commit does not match"):
        verifier._validate_android_artifact_evidence("0.0.4", RC_COMMIT, wrong_commit)


def test_android_agent_artifact_binding_rejects_replaced_installed_apk(tmp_path):
    def runner(command, **_kwargs):
        Path(command[-1]).write_bytes(b"replacement-debug-apk")
        return subprocess.CompletedProcess(command, 0, "1 file pulled\n", "")

    with pytest.raises(verifier.VerificationError, match="does not match the bound A-01 artifact"):
        verifier._verify_installed_android_apk_sha256(
            "adb",
            "physical-device",
            "/data/app/notemeld.apk",
            SIGNED_APK_SHA256,
            runner=runner,
        )


def test_android_runtime_verifier_requires_complete_release_artifact_arguments():
    with pytest.raises(verifier.VerificationError, match="requires APK, signer SHA-256, and apksigner"):
        verifier.run_android_runtime(
            "adb",
            "physical-device",
            "com.notemeld.mobile",
            "0.0.4",
            expected_apk="notemeld-release.apk",
            runner=lambda command, **_kwargs: subprocess.CompletedProcess(
                command,
                0,
                "List of devices attached\nphysical-device device\n",
                "",
            ),
        )


def test_android_runtime_verifier_rejects_fatal_log():
    def runner(command, **_kwargs):
        joined = " ".join(command)
        if joined == "adb devices -l":
            output = "List of devices attached\ndevice-a device\n"
        elif " pm path " in joined:
            output = "package:/data/app/notemeld.apk\n"
        elif "ro.build.version.release" in joined:
            output = "14\n"
        elif "ro.product.cpu.abi" in joined:
            output = "arm64-v8a\n"
        elif "ro.kernel.qemu" in joined:
            output = "0\n"
        elif "dumpsys package" in joined:
            output = "versionName=0.0.4\n"
        elif "am start" in joined:
            output = "Status: ok\n"
        elif "pidof" in joined:
            output = "10\n"
        elif "logcat" in joined:
            output = "FATAL EXCEPTION: main\n"
        else:
            output = ""
        return subprocess.CompletedProcess(command, 0, output, "")

    with pytest.raises(verifier.VerificationError, match="fatal exception"):
        verifier.run_android_runtime("adb", None, "com.notemeld.mobile", "0.0.4", runner=runner, sleep_fn=lambda _seconds: None)


def test_android_runtime_verifier_rejects_emulator():
    def runner(command, **_kwargs):
        joined = " ".join(command)
        if joined == "adb devices -l":
            output = "List of devices attached\nemulator-5554 device\n"
        else:
            output = ""
        return subprocess.CompletedProcess(command, 0, output, "")

    with pytest.raises(verifier.VerificationError, match="physical Android"):
        verifier.run_android_runtime("adb", None, "com.notemeld.mobile", "0.0.4", runner=runner, sleep_fn=lambda _seconds: None)


def test_android_runtime_verifier_rejects_wrong_installed_version():
    def runner(command, **_kwargs):
        joined = " ".join(command)
        if joined == "adb devices -l":
            output = "List of devices attached\ndevice-a device\n"
        elif " pm path " in joined:
            output = "package:/data/app/notemeld.apk\n"
        elif "ro.build.version.release" in joined:
            output = "14\n"
        elif "ro.product.cpu.abi" in joined:
            output = "arm64-v8a\n"
        elif "ro.kernel.qemu" in joined:
            output = "0\n"
        elif "dumpsys package" in joined:
            output = "versionName=0.0.3\n"
        else:
            raise AssertionError(joined)
        return subprocess.CompletedProcess(command, 0, output, "")

    with pytest.raises(verifier.VerificationError, match="does not match expected RC version"):
        verifier.run_android_runtime("adb", None, "com.notemeld.mobile", "0.0.4", runner=runner, sleep_fn=lambda _seconds: None)


def test_android_ui_evidence_reads_only_marked_assistant_messages():
    xml = """<hierarchy>
      <node content-desc="notemeld-message-user" text="NMANDROIDUSER" bounds="[0,0][10,10]" />
      <node content-desc="notemeld-message-assistant" text="NM" bounds="[0,10][10,20]" />
      <node content-desc="notemeld-message-assistant" text="ANDROIDASSISTANT" bounds="[0,20][10,30]" />
    </hierarchy>"""

    assert verifier._ui_text(xml, "notemeld-message-assistant") == "NMANDROIDASSISTANT"
    assert "USER" not in verifier._ui_text(xml, "notemeld-message-assistant")


def test_android_field_verifier_requires_exactly_one_success_terminal_marker():
    prefix = "notemeld-agent-terminal:"
    success = '<hierarchy><node content-desc="notemeld-agent-terminal:turn.succeeded:1" /></hierarchy>'
    failed = '<hierarchy><node content-desc="notemeld-agent-terminal:turn.failed:1" /></hierarchy>'
    duplicate = '<hierarchy><node content-desc="notemeld-agent-terminal:turn.succeeded:2" /></hierarchy>'

    expected = ["notemeld-agent-terminal:turn.succeeded:1"]
    assert verifier._ui_descriptions_with_prefix(success, prefix) == expected
    assert verifier._ui_descriptions_with_prefix(failed, prefix) != expected
    assert verifier._ui_descriptions_with_prefix(duplicate, prefix) != expected


def test_android_agent_verifier_drives_physical_ui_and_redacts_challenge():
    serial = "physical-device-secret"
    challenge = "NMANDROIDTESTCODE"
    state = {"screen": "home", "permission": False, "answered": False}

    def hierarchy():
        if state["screen"] == "home":
            return f'<hierarchy><node content-desc="notemeld-build-commit:{RC_COMMIT}" /><node content-desc="notemeld-start-chat" text="start" bounds="[0,100][100,200]" /></hierarchy>'
        permission = "" if state["permission"] else '<node content-desc="notemeld-agent-permission" text="allow" bounds="[0,200][100,300]" />'
        answer = (
            f'<node content-desc="notemeld-message-user" text="Reply_exactly_{challenge}" bounds="[0,500][100,550]" />'
            f'<node content-desc="notemeld-message-assistant" text="{challenge}" bounds="[0,550][100,600]" />'
            '<node content-desc="notemeld-agent-terminal:turn.succeeded:1" text="" bounds="[0,600][1,601]" />'
            if state["answered"] else ""
        )
        return (
            f'<hierarchy>{permission}<node content-desc="notemeld-build-commit:{RC_COMMIT}" />'
            '<node content-desc="notemeld-agent-location-local" text="local" bounds="[0,250][100,300]" />'
            '<node content-desc="notemeld-agent-input" text="" bounds="[0,300][100,400]" />'
            '<node content-desc="notemeld-agent-send-idle" text="send" bounds="[0,400][100,500]" />'
            f'{answer}</hierarchy>'
        )

    def runner(command, **_kwargs):
        joined = " ".join(command)
        output = ""
        if joined == "adb devices -l":
            output = f"List of devices attached\n{serial} device product:test\n"
        elif joined.endswith("reverse --list"):
            output = ""
        elif "shell pm path" in joined:
            output = "package:/data/app/notemeld.apk\n"
        elif "ro.build.version.release" in joined:
            output = "14\n"
        elif "ro.product.cpu.abi" in joined:
            output = "arm64-v8a\n"
        elif "ro.kernel.qemu" in joined:
            output = "0\n"
        elif "dumpsys package" in joined:
            output = "versionName=0.0.4\n"
        elif "am start" in joined:
            state.update(screen="home", permission=False, answered=False)
            output = "Status: ok\n"
        elif joined.endswith("shell pidof com.notemeld.mobile"):
            output = "4242\n"
        elif "logcat -d --pid 4242" in joined:
            output = "I NoteMeld: Agent turn complete\n"
        elif "exec-out cat" in joined:
            output = hierarchy()
        elif " pull " in joined:
            Path(command[-1]).write_bytes(SIGNED_APK_BYTES)
            output = "1 file pulled\n"
        elif "shell input tap" in joined:
            y = int(command[-1])
            if y == 150:
                state["screen"] = "session"
            elif y == 250:
                state["permission"] = True
            elif y == 450:
                state["answered"] = True
        return subprocess.CompletedProcess(command, 0, output, "")

    def request(_base_url, method, path, **_kwargs):
        if (method, path) == ("GET", "/api/sys_health"):
            return None
        if (method, path) == ("GET", "/api/model_list"):
            return [{"id": 1, "model_name": "real-model"}]
        raise AssertionError((method, path))

    result = verifier.run_android_agent(
        "adb",
        None,
        "com.notemeld.mobile",
        "0.0.4",
        "real-model",
        1,
        runner=runner,
        request_fn=request,
        sleep_fn=lambda _seconds: None,
        challenge=challenge,
        expected_commit=RC_COMMIT,
        android_artifact_evidence=android_a01_evidence(),
    )

    assert result["release_checks"] == {}
    assert result["development_checks"] == {"android_local_host_smoke": "PASS"}
    assert result["release_evidence"] is False
    assert "adb reverse" in result["not_for_release_reason"]
    assert result["transport"] == "adb-reverse-loopback"
    assert result["a_01_evidence_sha256"] == "d" * 64
    assert challenge not in str(result)
    assert serial not in str(result)


def test_android_agent_verifier_rejects_model_not_selected_by_new_session():
    def request(_base_url, _method, path, **_kwargs):
        return None if path == "/api/sys_health" else [{"model_name": "other-real-model"}]

    with pytest.raises(verifier.VerificationError, match="not the host model"):
        verifier.run_android_agent(
            "adb", None, "com.notemeld.mobile", "0.0.4", "expected-real-model", 1,
            request_fn=request,
        )


def test_android_cloud_agent_verifier_binds_production_c02_evidence_and_ui_target():
    serial = "physical-cloud-device-secret"
    challenge = "NMANDROIDCLOUDTEST"
    base_url = "https://cloud.example.test"
    state = {"screen": "home", "cloud": False, "permission": False, "answered": False}
    commands = []

    def hierarchy():
        if state["screen"] == "home":
            return f'<hierarchy><node content-desc="notemeld-build-commit:{RC_COMMIT}" /><node content-desc="notemeld-start-chat" text="start" bounds="[0,100][100,200]" /></hierarchy>'
        permission = "" if state["permission"] else '<node content-desc="notemeld-agent-permission" text="allow" bounds="[0,200][100,250]" />'
        target = f'<node content-desc="notemeld-cloud-target" text="{base_url}" bounds="[0,300][100,325]" />' if state["cloud"] else ""
        answer = (
            f'<node content-desc="notemeld-message-assistant" text="{challenge}" bounds="[0,550][100,600]" />'
            '<node content-desc="notemeld-agent-terminal:turn.succeeded:1" text="" bounds="[0,600][1,601]" />'
            if state["answered"] else ""
        )
        return (
            f'<hierarchy>{permission}<node content-desc="notemeld-build-commit:{RC_COMMIT}" />'
            '<node content-desc="notemeld-agent-location-cloud" text="cloud" bounds="[0,250][100,300]" />'
            f'{target}'
            '<node content-desc="notemeld-agent-input" text="" bounds="[0,325][100,400]" />'
            '<node content-desc="notemeld-agent-send-idle" text="send" bounds="[0,400][100,500]" />'
            f'{answer}</hierarchy>'
        )

    def runner(command, **_kwargs):
        joined = " ".join(command)
        commands.append(joined)
        output = ""
        if joined == "adb devices -l":
            output = f"List of devices attached\n{serial} device product:test\n"
        elif "shell pm path" in joined:
            output = "package:/data/app/notemeld.apk\n"
        elif "ro.build.version.release" in joined:
            output = "14\n"
        elif "ro.product.cpu.abi" in joined:
            output = "arm64-v8a\n"
        elif "ro.kernel.qemu" in joined:
            output = "0\n"
        elif "dumpsys package" in joined:
            output = "versionName=0.0.4\n"
        elif "am start" in joined:
            state.update(screen="home", cloud=False, permission=False, answered=False)
            output = "Status: ok\n"
        elif joined.endswith("shell pidof com.notemeld.mobile"):
            output = "4242\n"
        elif "logcat -d --pid 4242" in joined:
            output = "I NoteMeld: Cloud Agent turn complete\n"
        elif "exec-out cat" in joined:
            output = hierarchy()
        elif " pull " in joined:
            Path(command[-1]).write_bytes(SIGNED_APK_BYTES)
            output = "1 file pulled\n"
        elif "shell input tap" in joined:
            y = int(command[-1])
            if y == 150:
                state["screen"] = "session"
            elif y == 275:
                state["cloud"] = True
            elif y == 225:
                state["permission"] = True
            elif y == 450:
                state["answered"] = True
        return subprocess.CompletedProcess(command, 0, output, "")

    ready = {
        "ready": True,
        "environment": "production",
        "agent_backend": "canonical-sdk",
        "checks": {key: "ok" for key in {
            "database", "workspace_root", "relay", "device_proof_crypto", "agent_provider_config",
            "backup_storage_config", "otp_delivery_config", "device_proof_config", "release_identity",
        }},
        "build_commit": RC_COMMIT,
        "image_digest": "sha256:" + "c" * 64,
    }
    evidence = {
        "release_checks": {"c_01": "PASS", "c_02": "PASS"},
        "base_url": base_url,
        "model": "cloud-real-model",
        "rc_commit": RC_COMMIT,
        "build_commit": RC_COMMIT,
        "cloud_image_digest": "sha256:" + "c" * 64,
    }

    result = verifier.run_android_cloud_agent(
        "adb",
        None,
        "com.notemeld.mobile",
        "0.0.4",
        base_url,
        "cloud-real-model",
        evidence,
        1,
        runner=runner,
        ready_fn=lambda _url: ready,
        sleep_fn=lambda _seconds: None,
        challenge=challenge,
        expected_commit=RC_COMMIT,
        android_artifact_evidence=android_a01_evidence(),
    )

    assert result["release_checks"] == {"a_03": "PASS"}
    assert result["cloud_model"] == "cloud-real-model"
    assert result["a_01_evidence_sha256"] == "d" * 64
    assert challenge not in str(result)
    assert serial not in str(result)
    assert not any(" reverse " in command for command in commands)


def test_android_cloud_agent_verifier_rejects_mismatched_or_development_evidence():
    evidence = {"release_checks": {"c_01": "PASS", "c_02": "PASS"}, "base_url": "https://other.example", "model": "model-a"}
    ready = {"ready": True, "environment": "development", "agent_backend": "deterministic", "checks": {}}

    with pytest.raises(verifier.VerificationError, match="does not match"):
        verifier._validate_cloud_evidence("https://cloud.example", "model-a", evidence, ready)


@pytest.mark.parametrize(
    ("transport", "release_check"),
    (("lan", "a_04"), ("relay", "a_05")),
)
def test_android_remote_agent_verifier_binds_host_and_actual_transport(monkeypatch, transport, release_check):
    base_url = "https://cloud.example.test"
    cloud_model = "cloud-real-model"
    host_device_id = "desktop-host-secret-id"
    challenge = "NMANDROIDREMOTETEST"
    cloud_evidence = {
        "release_checks": {"c_01": "PASS", "c_02": "PASS"},
        "base_url": base_url,
        "model": cloud_model,
        "rc_commit": RC_COMMIT,
        "build_commit": RC_COMMIT,
        "cloud_image_digest": "sha256:" + "c" * 64,
    }
    remote_evidence = {
        "release_checks": {"c_04_real_host": "PASS", "x_06_remote_agent": "PASS"},
        "base_url": base_url,
        "host_device_id": host_device_id,
        "host_platform": "desktop",
        "cloud_persisted_commands": 0,
        "cloud_persisted_events": 0,
    }
    ready = {
        "ready": True,
        "environment": "production",
        "agent_backend": "canonical-sdk",
        "checks": {key: "ok" for key in {
            "database", "workspace_root", "relay", "device_proof_crypto", "agent_provider_config",
            "backup_storage_config", "otp_delivery_config", "device_proof_config", "release_identity",
        }},
        "build_commit": RC_COMMIT,
        "image_digest": "sha256:" + "c" * 64,
    }
    observed = {}
    runtime_observed = {}

    monkeypatch.setattr(verifier, "_resolve_android_device", lambda *_args: "physical-device-secret")
    def runtime(*_args, **kwargs):
        runtime_observed.update(kwargs)
        return {"release_checks": {"android_runtime_smoke": "PASS"}, "process_alive": True}

    monkeypatch.setattr(verifier, "run_android_runtime", runtime)

    def drive(*_args, **kwargs):
        observed.update(kwargs)
        return challenge, "<hierarchy>verified</hierarchy>"

    monkeypatch.setattr(verifier, "_drive_android_agent_ui", drive)
    monkeypatch.setattr(verifier, "_adb", lambda *_args, **_kwargs: "")

    result = verifier.run_android_remote_agent(
        "adb", None, "com.notemeld.mobile", "0.0.4", base_url, cloud_model,
        host_device_id, transport, cloud_evidence, remote_evidence, 1,
        ready_fn=lambda _url: ready,
        challenge=challenge,
        expected_commit=RC_COMMIT,
        android_artifact_evidence=android_a01_evidence(),
    )

    assert result["release_checks"] == {release_check: "PASS"}
    assert result["cloud_model"] == cloud_model
    assert result["transport"] == transport
    assert result["a_01_evidence_sha256"] == "d" * 64
    assert observed["expected_host_hash"] == verifier.hashlib.sha256(host_device_id.encode()).hexdigest()[:12]
    assert observed["expected_transport"] == transport
    assert runtime_observed["expected_installed_apk_sha256"] == SIGNED_APK_SHA256
    assert challenge not in str(result)
    assert host_device_id not in str(result)


def test_android_remote_agent_verifier_rejects_unbound_host_or_inferred_transport():
    evidence = {
        "release_checks": {"c_04_real_host": "PASS", "x_06_remote_agent": "PASS"},
        "base_url": "https://cloud.example.test",
        "host_device_id": "other-host",
        "host_platform": "desktop",
        "cloud_persisted_commands": 0,
        "cloud_persisted_events": 0,
    }

    with pytest.raises(verifier.VerificationError, match="does not match"):
        verifier._validate_remote_host_evidence("https://cloud.example.test", "expected-host", evidence)
    with pytest.raises(verifier.VerificationError, match="lan or relay"):
        verifier.run_android_remote_agent(
            "adb", None, "com.notemeld.mobile", "0.0.4", "https://cloud.example.test",
            "cloud-model", "expected-host", "auto", {}, {}, 1,
        )


def test_android_recovery_verifier_proves_offline_read_only_and_monotonic_cursor(monkeypatch):
    network = {"offline": False, "restores": 0}
    ui = {"busy": False}
    cursors = iter((7, 12))
    runtime_observed = {}
    monkeypatch.setattr(verifier, "_validate_cloud_evidence", lambda *_args: {"relay": "ok"})
    monkeypatch.setattr(verifier, "_validate_remote_host_evidence", lambda *_args: "host-hash")
    monkeypatch.setattr(verifier, "_resolve_android_device", lambda *_args: "physical-device")
    def runtime(*_args, **kwargs):
        runtime_observed.update(kwargs)
        return {"release_checks": {"android_runtime_smoke": "PASS"}}

    monkeypatch.setattr(verifier, "run_android_runtime", runtime)
    monkeypatch.setattr(verifier, "_android_network_radios", lambda *_args: {"wifi": True, "data": False})

    def set_radios(_adb, _serial, _state, _runner, *, offline):
        network["offline"] = offline
        if offline:
            ui["busy"] = False
        if not offline:
            network["restores"] += 1

    def drive(*args, **_kwargs):
        cursor = next(cursors)
        challenge = args[4]
        xml = f'<hierarchy><node content-desc="notemeld-remote-cursor"><node text="Relay cursor: {cursor}" /></node></hierarchy>'
        return f"answer-{challenge}", xml

    def dump(*_args):
        if network["offline"]:
            return '<hierarchy><node content-desc="notemeld-agent-offline-readonly" /><node content-desc="notemeld-agent-input" enabled="false" /><node content-desc="notemeld-agent-send-idle" /><node content-desc="notemeld-message-user"><node text="INTERRUPTED" /></node></hierarchy>'
        send_state = "busy" if ui["busy"] else "idle"
        return f'<hierarchy><node content-desc="notemeld-agent-input" enabled="true" /><node content-desc="notemeld-agent-send-{send_state}" /></hierarchy>'

    def tap(_runner, _adb, _serial, _xml, description):
        if description == "notemeld-agent-send-idle":
            ui["busy"] = True

    monkeypatch.setattr(verifier, "_set_android_network_radios", set_radios)
    monkeypatch.setattr(verifier, "_drive_android_agent_ui", drive)
    monkeypatch.setattr(verifier, "_dump_android_ui", dump)
    monkeypatch.setattr(verifier, "_tap_ui", tap)
    monkeypatch.setattr(verifier, "_adb", lambda *_args, **_kwargs: "")
    result = verifier.run_android_recovery(
        "adb", None, "com.notemeld.mobile", "0.0.4", "https://cloud.example", "model-a",
        "host-a", {"build_commit": RC_COMMIT, "cloud_image_digest": "sha256:" + "7" * 64}, {}, 1, ready_fn=lambda _url: {}, sleep_fn=lambda _seconds: None,
        challenges=("FIRST", "INTERRUPTED", "RECOVERED"),
        expected_commit=RC_COMMIT, android_artifact_evidence=android_a01_evidence(),
    )
    assert result["release_checks"] == {"a_06": "PASS"}
    assert result["cursor_before"] == 7 and result["cursor_after"] == 12
    assert result["offline_read_only"] is True
    assert result["a_01_evidence_sha256"] == "d" * 64
    assert result["build_commit"] == RC_COMMIT
    assert runtime_observed["expected_installed_apk_sha256"] == SIGNED_APK_SHA256
    assert network == {"offline": False, "restores": 1}
    assert "FIRST" not in str(result) and "INTERRUPTED" not in str(result) and "RECOVERED" not in str(result)


def test_android_process_recovery_requires_durable_needs_attention_projection(monkeypatch):
    challenge = "PROCESS-RECOVERY"
    xmls = iter(
        [
            '<hierarchy><node content-desc="notemeld-agent-input" /><node content-desc="notemeld-agent-send-idle" /></hierarchy>',
            '<hierarchy><node content-desc="notemeld-agent-input" /><node content-desc="notemeld-agent-send-idle" /></hierarchy>',
            '<hierarchy><node content-desc="notemeld-agent-input" /><node content-desc="notemeld-agent-send-busy" /></hierarchy>',
            '<hierarchy><node content-desc="notemeld-agent-input" /><node content-desc="notemeld-agent-send-busy" /></hierarchy>',
            '<hierarchy><node content-desc="notemeld-agent-input" /><node content-desc="notemeld-agent-send-idle" /><node content-desc="notemeld-agent-terminal:turn.interrupted:needs_attention:1" /><node content-desc="notemeld-message-user"><node text="PROCESS-RECOVERY" /></node><node content-desc="notemeld-message-assistant"><node text="上次本机 Agent 会话在进程回收时中断；未知副作用未自动重放，请确认后重新发送。" /></node></hierarchy>',
        ]
    )
    commands = []
    monkeypatch.setattr(verifier, "_resolve_android_device", lambda *_args: "physical-device")
    monkeypatch.setattr(verifier, "run_android_runtime", lambda *_args, **_kwargs: {"process_alive": True})
    monkeypatch.setattr(verifier, "_dump_android_ui", lambda *_args: next(xmls))
    monkeypatch.setattr(verifier, "_tap_ui", lambda *_args: None)

    def adb(_runner, _adb, _serial, command):
        commands.append(command)
        if command[:4] == ["shell", "am", "start", "-W"]:
            return "Status: ok\n"
        if command[:2] == ["shell", "pidof"]:
            return "4242\n"
        return ""

    monkeypatch.setattr(verifier, "_adb", adb)
    result = verifier.run_android_process_recovery(
        "adb", "physical-device", "com.notemeld.mobile", "0.0.4", 1,
        expected_commit=RC_COMMIT,
        expected_installed_apk_sha256=SIGNED_APK_SHA256,
        runner=lambda *_args, **_kwargs: None,
        sleep_fn=lambda _seconds: None,
        challenge=challenge,
    )

    assert result["process_recovery"] is True
    assert result["process_recovery_user_count"] == 1
    assert result["process_recovery_terminal"] == "turn.interrupted:needs_attention"
    assert not any("reverse" in command for command in commands)


def test_android_recovery_verifier_rejects_cursor_reset_and_restores_radios(monkeypatch):
    network = {"offline": False, "restores": 0}
    ui = {"busy": False}
    cursors = iter((9, 9))
    monkeypatch.setattr(verifier, "_validate_cloud_evidence", lambda *_args: {})
    monkeypatch.setattr(verifier, "_validate_remote_host_evidence", lambda *_args: "host-hash")
    monkeypatch.setattr(verifier, "_resolve_android_device", lambda *_args: "physical-device")
    monkeypatch.setattr(verifier, "run_android_runtime", lambda *_args, **_kwargs: {})
    monkeypatch.setattr(verifier, "_android_network_radios", lambda *_args: {"wifi": True, "data": False})

    def set_radios(_adb, _serial, _state, _runner, *, offline):
        network["offline"] = offline
        if offline:
            ui["busy"] = False
        if not offline:
            network["restores"] += 1

    def drive(*_args, **_kwargs):
        cursor = next(cursors)
        return "answer", f'<hierarchy><node content-desc="notemeld-remote-cursor"><node text="{cursor}" /></node></hierarchy>'

    monkeypatch.setattr(verifier, "_set_android_network_radios", set_radios)
    monkeypatch.setattr(verifier, "_drive_android_agent_ui", drive)
    monkeypatch.setattr(verifier, "_dump_android_ui", lambda *_args: f'<hierarchy><node content-desc="notemeld-agent-input" enabled="true" /><node content-desc="notemeld-agent-send-{"busy" if ui["busy"] else "idle"}" /></hierarchy>' if not network["offline"] else '<hierarchy><node content-desc="notemeld-agent-offline-readonly" /><node content-desc="notemeld-agent-input" enabled="false" /><node content-desc="notemeld-agent-send-idle" /><node content-desc="notemeld-message-user"><node text="INTERRUPTED" /></node></hierarchy>')
    monkeypatch.setattr(verifier, "_tap_ui", lambda _runner, _adb, _serial, _xml, description: ui.update(busy=True) if description == "notemeld-agent-send-idle" else None)
    monkeypatch.setattr(verifier, "_adb", lambda *_args, **_kwargs: "")
    with pytest.raises(verifier.VerificationError, match="did not continue monotonically"):
        verifier.run_android_recovery(
            "adb", None, "com.notemeld.mobile", "0.0.4", "https://cloud.example", "model-a",
            "host-a", {}, {}, 1, ready_fn=lambda _url: {}, sleep_fn=lambda _seconds: None,
            challenges=("FIRST", "INTERRUPTED", "RECOVERED"),
            expected_commit=RC_COMMIT, android_artifact_evidence=android_a01_evidence(),
        )
    assert network == {"offline": False, "restores": 1}


def test_android_recovery_verifier_rejects_wireless_adb(monkeypatch):
    monkeypatch.setattr(verifier, "_validate_cloud_evidence", lambda *_args: {})
    monkeypatch.setattr(verifier, "_validate_remote_host_evidence", lambda *_args: "host-hash")
    monkeypatch.setattr(verifier, "_resolve_android_device", lambda *_args: "192.0.2.10:5555")
    with pytest.raises(verifier.VerificationError, match="requires USB adb"):
        verifier.run_android_recovery(
            "adb", None, "com.notemeld.mobile", "0.0.4", "https://cloud.example", "model-a",
            "host-a", {}, {}, 1, ready_fn=lambda _url: {},
            expected_commit=RC_COMMIT, android_artifact_evidence=android_a01_evidence(),
        )
