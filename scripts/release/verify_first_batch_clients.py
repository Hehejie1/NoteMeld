#!/usr/bin/env python3
"""Collect fail-closed evidence for first-batch Windows x64 and Android clients.

`desktop` runs a real local Agent turn through the canonical Agent v1 API and
requires a Windows x64 host plus an explicitly named configured model.
`android-runtime` cold-launches the installed Android package through adb and
checks that its process survives without a fatal exception in the captured log.
`android-agent` additionally drives that package's accessibility UI through a
temporary adb reverse rule and accepts the challenge only from assistant nodes.
`android-cloud-agent` drives a pre-authenticated package against the same live
production URL/model already proven by a C-01/C-02 evidence file.
`android-remote-agent` binds a physical package to prior Cloud and real desktop
Host evidence, then proves the UI-selected Host and the actual LAN/Relay path.

Only hashes and non-secret runtime metadata are printed. This verifier does not
replace the LAN/Relay two-machine field matrix in the release ledger.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
import uuid
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Callable, Sequence
from urllib.parse import urlparse


TERMINAL_EVENTS = {"turn.succeeded", "turn.failed", "turn.interrupted", "turn.cancelled"}
TERMINAL_STATUSES = {"succeeded", "failed", "interrupted", "cancelled"}


class VerificationError(RuntimeError):
    pass


def request(
    base_url: str,
    method: str,
    path: str,
    *,
    payload: dict[str, Any] | None = None,
    session_token: str | None = None,
) -> Any:
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {"Accept": "application/json"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if session_token:
        headers["X-NoteMeld-Session"] = session_token
    req = urllib.request.Request(f"{base_url.rstrip('/')}{path}", data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            decoded = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise VerificationError(f"{method} {path} returned HTTP {exc.code}") from exc
    except (OSError, json.JSONDecodeError) as exc:
        raise VerificationError(f"{method} {path} failed") from exc
    if not isinstance(decoded, dict) or decoded.get("code") != 0:
        raise VerificationError(f"{method} {path} returned an invalid API envelope")
    return decoded.get("data")


def _validate_loopback(base_url: str) -> str:
    parsed = urlparse(base_url)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.username or parsed.password:
        raise VerificationError("desktop verifier requires a loopback HTTP sidecar URL")
    return base_url.rstrip("/")


def _event_text(events: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for event in events:
        payload = event.get("payload")
        if not isinstance(payload, dict):
            continue
        for key in ("delta", "answer", "content", "output"):
            value = payload.get(key)
            if isinstance(value, str):
                parts.append(value)
    return "".join(parts)


def _inspect_windows_executable(
    executable: str,
    expected_version: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, Any]:
    if re.fullmatch(r"\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?", expected_version) is None:
        raise VerificationError("expected Windows RC version must be SemVer")
    path = Path(executable).resolve()
    if path.suffix.lower() != ".exe" or not path.is_file():
        raise VerificationError("installed Windows executable is missing")
    try:
        with path.open("rb") as stream:
            if stream.read(2) != b"MZ":
                raise VerificationError("installed Windows executable is not a PE image")
            stream.seek(0x3C)
            pe_offset_raw = stream.read(4)
            if len(pe_offset_raw) != 4:
                raise VerificationError("installed Windows executable has an invalid PE header")
            pe_offset = int.from_bytes(pe_offset_raw, "little")
            stream.seek(pe_offset)
            if stream.read(4) != b"PE\0\0" or int.from_bytes(stream.read(2), "little") != 0x8664:
                raise VerificationError("installed Windows executable is not x86_64")
    except OSError as exc:
        raise VerificationError("installed Windows executable could not be inspected") from exc

    powershell = (
        "$p=$args[0];$s=Get-AuthenticodeSignature -LiteralPath $p;"
        "$v=[Diagnostics.FileVersionInfo]::GetVersionInfo($p).ProductVersion;"
        "$r=@(Get-Process -ErrorAction SilentlyContinue|Where-Object{try{$_.Path -eq $p}catch{$false}}).Count -gt 0;"
        "$t=if($null -ne $s.SignerCertificate){$s.SignerCertificate.Thumbprint}else{''};"
        "@{status=[string]$s.Status;version=$v;running=$r;thumbprint=$t}|ConvertTo-Json -Compress"
    )
    completed = runner(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", powershell, str(path)],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if completed.returncode != 0:
        raise VerificationError("Windows Authenticode inspection failed")
    try:
        result = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise VerificationError("Windows Authenticode inspection returned invalid evidence") from exc
    version = str(result.get("version") or "") if isinstance(result, dict) else ""
    if not isinstance(result, dict) or result.get("status") != "Valid":
        raise VerificationError("installed Windows executable does not have a valid Authenticode signature")
    if version != expected_version and not version.startswith(f"{expected_version}."):
        raise VerificationError("installed Windows executable version does not match the RC")
    if result.get("running") is not True:
        raise VerificationError("the verified installed Windows executable is not running")
    thumbprint = str(result.get("thumbprint") or "").lower()
    if re.fullmatch(r"[0-9a-f]{40,128}", thumbprint) is None:
        raise VerificationError("Windows Authenticode signer thumbprint is invalid")
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        while chunk := stream.read(1024 * 1024):
            digest.update(chunk)
    return {
        "version": version,
        "sha256": digest.hexdigest(),
        "signer_thumbprint": thumbprint,
    }


def run_desktop(
    base_url: str,
    expected_model: str,
    timeout: float,
    *,
    session_token: str | None = None,
    request_fn: Callable[..., Any] = request,
    challenge: str | None = None,
    system_fn: Callable[[], str] = platform.system,
    machine_fn: Callable[[], str] = platform.machine,
    expected_version: str | None = None,
    installed_exe: str | None = None,
    executable_inspector: Callable[[str, str], dict[str, Any]] = _inspect_windows_executable,
) -> dict[str, Any]:
    base_url = _validate_loopback(base_url)
    system = system_fn()
    machine = machine_fn().lower()
    if system != "Windows" or machine not in {"amd64", "x86_64"}:
        raise VerificationError("X-02 must run inside the installed Windows x64 client")
    if not expected_model or expected_model.startswith("deterministic-"):
        raise VerificationError("an explicit real local model is required")
    if bool(expected_version) != bool(installed_exe):
        raise VerificationError("Windows package evidence requires both expected version and installed executable")
    package = executable_inspector(installed_exe, expected_version) if installed_exe and expected_version else None
    call = lambda method, path, payload=None: request_fn(  # noqa: E731
        base_url, method, path, payload=payload, session_token=session_token
    )
    call("GET", "/api/sys_health")
    models = call("GET", "/api/model_list")
    if not isinstance(models, list) or not models:
        raise VerificationError("Windows client has no enabled local model")
    available = {
        str(value)
        for model in models
        if isinstance(model, dict)
        for value in (model.get("id"), model.get("model_name"))
        if value
    }
    if expected_model not in available:
        raise VerificationError(f"expected model {expected_model!r} is not enabled")

    challenge = challenge or f"NM-X64-{uuid.uuid4()}"
    session = call("POST", "/api/agent/v1/sessions", {"title": "first-batch Windows x64 verification"})
    if not isinstance(session, dict) or not isinstance(session.get("id"), str):
        raise VerificationError("Agent session creation did not return an id")
    session_id = session["id"]
    turn = call(
        "POST",
        f"/api/agent/v1/sessions/{session_id}/turns",
        {"input": f"Reply with this verification code verbatim: {challenge}", "model": expected_model, "idempotency_key": f"first-batch-{uuid.uuid4()}"},
    )
    if not isinstance(turn, dict) or not isinstance(turn.get("turn_id"), str):
        raise VerificationError("Agent turn submission did not return a turn id")
    turn_id = turn["turn_id"]
    deadline = time.monotonic() + timeout
    diagnostics: Any = None
    while time.monotonic() < deadline:
        diagnostics = call("GET", f"/api/agent/v1/turns/{turn_id}/diagnostics")
        status = str(diagnostics.get("turn", {}).get("status", "")) if isinstance(diagnostics, dict) else ""
        if status in TERMINAL_STATUSES:
            break
        time.sleep(0.25)
    if not isinstance(diagnostics, dict):
        raise VerificationError("Agent diagnostics are unavailable")
    status = str(diagnostics.get("turn", {}).get("status", ""))
    if status != "succeeded":
        raise VerificationError(f"Windows local Agent ended in {status or 'non-terminal'}")
    events = diagnostics.get("events")
    if not isinstance(events, list) or not all(isinstance(event, dict) for event in events):
        raise VerificationError("Agent diagnostics event list is invalid")
    terminals = [event for event in events if event.get("type") in TERMINAL_EVENTS]
    if len(terminals) != 1 or terminals[0].get("type") != "turn.succeeded":
        raise VerificationError("Windows local Agent must emit exactly one successful terminal event")
    sequences = [event.get("sequence") for event in events]
    if any(type(value) is not int or value < 0 for value in sequences) or sequences != sorted(set(sequences)):
        raise VerificationError("Windows local Agent event sequence is not unique and monotonic")
    answer = _event_text(events)
    if challenge not in answer:
        raise VerificationError("Windows local Agent response did not contain the unique challenge")
    result = {
        "release_checks": {"windows_local_agent_runtime": "PASS"},
        "platform": "windows-x64",
        "base_url": base_url,
        "model": expected_model,
        "session_id": session_id,
        "turn_id": turn_id,
        "event_count": len(events),
        "terminal_event": "turn.succeeded",
        "challenge_sha256": hashlib.sha256(challenge.encode("utf-8")).hexdigest(),
        "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
    }
    if package is not None:
        result["installed_package"] = package
    return result


def _adb(runner: Callable[..., subprocess.CompletedProcess[str]], adb: str, serial: str | None, args: Sequence[str]) -> str:
    command = [adb]
    if serial:
        command += ["-s", serial]
    command += list(args)
    result = runner(command, capture_output=True, text=True, timeout=30, check=False)
    if result.returncode != 0:
        raise VerificationError(f"adb command failed: {' '.join(args[:3])}")
    return result.stdout.strip()


def _resolve_android_device(
    adb: str,
    serial: str | None,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> str:
    devices = _adb(runner, adb, None, ["devices", "-l"]).splitlines()[1:]
    online = [line.split()[0] for line in devices if len(line.split()) >= 2 and line.split()[1] == "device"]
    if serial:
        if serial not in online:
            raise VerificationError("requested Android device is not online")
    elif len(online) == 1:
        serial = online[0]
    else:
        raise VerificationError("connect exactly one Android device or pass --serial")
    if serial.startswith("emulator-"):
        raise VerificationError("Android field evidence requires a physical Android device")
    return serial


def run_android_runtime(
    adb: str,
    serial: str | None,
    package: str,
    expected_version: str,
    *,
    expected_commit: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleep_fn: Callable[[float], None] = time.sleep,
    expected_apk: str | None = None,
    expected_signer_sha256: str | None = None,
    apksigner: str | None = None,
    expected_installed_apk_sha256: str | None = None,
) -> dict[str, Any]:
    if expected_commit is not None:
        expected_commit = expected_commit.lower()
        if re.fullmatch(r"[0-9a-f]{40}", expected_commit) is None:
            raise VerificationError("Android RC commit must be a full 40-character SHA")
    artifact_requested = any((expected_apk, expected_signer_sha256, apksigner))
    if artifact_requested and not all((expected_apk, expected_signer_sha256, apksigner)):
        raise VerificationError("Android A-01 evidence requires APK, signer SHA-256, and apksigner")
    if expected_installed_apk_sha256 is not None:
        expected_installed_apk_sha256 = expected_installed_apk_sha256.lower()
        if re.fullmatch(r"[0-9a-f]{64}", expected_installed_apk_sha256) is None:
            raise VerificationError("expected installed Android APK SHA-256 is invalid")
    serial = _resolve_android_device(adb, serial, runner)
    package_paths = [line.removeprefix("package:") for line in _adb(runner, adb, serial, ["shell", "pm", "path", package]).splitlines() if line.startswith("package:")]
    if not package_paths:
        raise VerificationError("NoteMeld Android package is not installed")
    if len(package_paths) != 1:
        raise VerificationError("first-batch Android RC must be installed as one APK")
    android_version = _adb(runner, adb, serial, ["shell", "getprop", "ro.build.version.release"])
    abi = _adb(runner, adb, serial, ["shell", "getprop", "ro.product.cpu.abi"])
    if _adb(runner, adb, serial, ["shell", "getprop", "ro.kernel.qemu"]) == "1":
        raise VerificationError("A-01 runtime evidence requires a physical Android device")
    package_info = _adb(runner, adb, serial, ["shell", "dumpsys", "package", package])
    version_line = next((line.strip() for line in package_info.splitlines() if line.strip().startswith("versionName=")), "")
    installed_version = version_line.removeprefix("versionName=")
    if not expected_version or installed_version != expected_version:
        raise VerificationError(f"installed Android version {installed_version or 'unknown'!r} does not match expected RC version")
    _adb(runner, adb, serial, ["shell", "am", "force-stop", package])
    launch = _adb(runner, adb, serial, ["shell", "am", "start", "-W", "-n", f"{package}/.MainActivity"])
    if "Status: ok" not in launch:
        raise VerificationError("Android cold launch did not report Status: ok")
    sleep_fn(2)
    pid = _adb(runner, adb, serial, ["shell", "pidof", package])
    if not pid or not pid.split()[0].isdigit():
        raise VerificationError("Android process did not survive cold launch")
    logs = _adb(runner, adb, serial, ["logcat", "-d", "--pid", pid.split()[0], "-t", "200"])
    if "FATAL EXCEPTION" in logs:
        raise VerificationError("Android app emitted a fatal exception after launch")
    if expected_commit is not None:
        xml = _dump_android_ui(runner, adb, serial)
        if _ui_node(xml, f"notemeld-build-commit:{expected_commit}") is None:
            raise VerificationError("installed Android app build commit does not match the expected RC")
    artifact = _verify_installed_android_apk(
        adb,
        serial,
        package_paths[0],
        expected_apk,
        expected_signer_sha256,
        apksigner,
        runner=runner,
    ) if artifact_requested else None
    package_artifact = artifact
    if expected_installed_apk_sha256 is not None:
        current_digest = _verify_installed_android_apk_sha256(
            adb,
            serial,
            package_paths[0],
            expected_installed_apk_sha256,
            runner=runner,
        )
        if artifact is not None and artifact["apk_sha256"] != current_digest:
            raise VerificationError("A-01 evidence APK does not match the signed RC artifact")
        if artifact is None:
            package_artifact = {"apk_sha256": current_digest}
    result = {
        "release_checks": {"a_01": "PASS"} if artifact_requested else {"android_runtime_smoke": "PASS"},
        "package": package,
        "version_name": installed_version,
        "android_version": android_version,
        "abi": abi,
        "device_id_sha256": hashlib.sha256(serial.encode("utf-8")).hexdigest(),
        "process_alive": True,
        "fatal_exception": False,
    }
    if package_artifact is not None:
        result["installed_package"] = package_artifact
    if expected_commit is not None:
        result["build_commit"] = expected_commit
    return result


def _verify_installed_android_apk(
    adb: str,
    serial: str,
    installed_path: str,
    expected_apk: str,
    expected_signer_sha256: str,
    apksigner: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, str]:
    apk = Path(expected_apk).resolve()
    signer = expected_signer_sha256.lower().replace(":", "")
    if apk.suffix.lower() != ".apk" or not apk.is_file():
        raise VerificationError("expected signed Android RC APK is missing")
    if re.fullmatch(r"[0-9a-f]{64}", signer) is None:
        raise VerificationError("expected Android signer SHA-256 is invalid")

    def inspect(path: Path) -> str:
        completed = runner(
            [apksigner, "verify", "--verbose", "--print-certs", str(path)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        output = f"{completed.stdout}\n{completed.stderr}"
        if completed.returncode != 0 or not re.search(r"Verified using v[23] scheme.*:\s*true", output, re.IGNORECASE):
            raise VerificationError("Android APK signature verification failed")
        digests = re.findall(r"Signer #\d+ certificate SHA-256 digest:\s*([0-9a-f:]{64,95})", output, re.IGNORECASE)
        normalized = {value.lower().replace(":", "") for value in digests}
        if len(normalized) != 1:
            raise VerificationError("Android APK must have exactly one SHA-256 signer")
        return normalized.pop()

    expected_cert = inspect(apk)
    if expected_cert != signer:
        raise VerificationError("Android RC APK signer does not match the pinned certificate")
    with tempfile.TemporaryDirectory(prefix="notemeld-android-rc-") as directory:
        installed = Path(directory) / "installed.apk"
        _adb(runner, adb, serial, ["pull", installed_path, str(installed)])
        installed_cert = inspect(installed)
        if installed_cert != signer:
            raise VerificationError("installed Android package signer does not match the RC")
        expected_digest = _file_sha256(apk)
        installed_digest = _file_sha256(installed)
        if installed_digest != expected_digest:
            raise VerificationError("installed Android APK bytes do not match the signed RC artifact")
    return {"apk_sha256": expected_digest, "signer_sha256": signer}


def _verify_installed_android_apk_sha256(
    adb: str,
    serial: str,
    installed_path: str,
    expected_sha256: str,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> str:
    with tempfile.TemporaryDirectory(prefix="notemeld-android-installed-") as directory:
        installed = Path(directory) / "installed.apk"
        _adb(runner, adb, serial, ["pull", installed_path, str(installed)])
        installed_digest = _file_sha256(installed)
    if installed_digest != expected_sha256:
        raise VerificationError("currently installed Android APK does not match the bound A-01 artifact")
    return installed_digest


def _validate_android_artifact_evidence(
    expected_version: str,
    expected_commit: str | None,
    evidence: Any,
) -> dict[str, str]:
    if expected_commit is None or re.fullmatch(r"[0-9a-f]{40}", expected_commit.lower()) is None:
        raise VerificationError("Android Agent evidence requires a full RC commit")
    if not isinstance(evidence, dict):
        raise VerificationError("Android Agent evidence requires bound A-01 artifact evidence")
    if evidence.get("evidence_schema") != "notemeld.first-batch-live-evidence.v1":
        raise VerificationError("Android A-01 evidence is not bound to an RC")
    if evidence.get("bound_gate_ids") != ["A-01"] or evidence.get("release_checks") != {"a_01": "PASS"}:
        raise VerificationError("Android artifact evidence must prove only A-01")
    if evidence.get("rc_version") != expected_version or evidence.get("version_name") != expected_version:
        raise VerificationError("Android A-01 evidence version does not match this run")
    commit = expected_commit.lower()
    if evidence.get("rc_commit") != commit or evidence.get("build_commit") != commit:
        raise VerificationError("Android A-01 evidence commit does not match this run")
    package = evidence.get("installed_package")
    apk_sha256 = package.get("apk_sha256") if isinstance(package, dict) else None
    signer_sha256 = package.get("signer_sha256") if isinstance(package, dict) else None
    source_sha256 = evidence.get("source_sha256")
    if not isinstance(apk_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", apk_sha256) is None:
        raise VerificationError("Android A-01 evidence is missing the signed APK SHA-256")
    if not isinstance(signer_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", signer_sha256) is None:
        raise VerificationError("Android A-01 evidence is missing the pinned signer SHA-256")
    if not isinstance(source_sha256, str) or re.fullmatch(r"[0-9a-f]{64}", source_sha256) is None:
        raise VerificationError("Android A-01 evidence is missing its bound source SHA-256")
    return {"apk_sha256": apk_sha256, "source_sha256": source_sha256}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


_UI_DUMP_PATH = "/data/local/tmp/notemeld-first-batch-ui.xml"
_BOUNDS_PATTERN = re.compile(r"^\[(\d+),(\d+)\]\[(\d+),(\d+)\]$")


def _dump_android_ui(
    runner: Callable[..., subprocess.CompletedProcess[str]], adb: str, serial: str
) -> str:
    _adb(runner, adb, serial, ["shell", "uiautomator", "dump", _UI_DUMP_PATH])
    value = _adb(runner, adb, serial, ["exec-out", "cat", _UI_DUMP_PATH])
    try:
        ET.fromstring(value)
    except ET.ParseError as exc:
        raise VerificationError("Android accessibility hierarchy is invalid") from exc
    return value


def _ui_node(xml: str, description: str) -> ET.Element | None:
    root = ET.fromstring(xml)
    return next((node for node in root.iter("node") if node.attrib.get("content-desc") == description), None)


def _ui_text(xml: str, description: str) -> str:
    root = ET.fromstring(xml)
    chunks: list[str] = []
    for node in root.iter("node"):
        if node.attrib.get("content-desc") != description:
            continue
        for candidate in node.iter("node"):
            value = candidate.attrib.get("text", "")
            if value:
                chunks.append(value)
    return "".join(chunks)


def _ui_descriptions_with_prefix(xml: str, prefix: str) -> list[str]:
    root = ET.fromstring(xml)
    return [
        value
        for node in root.iter("node")
        if (value := node.attrib.get("content-desc", "")).startswith(prefix)
    ]


def _tap_ui(
    runner: Callable[..., subprocess.CompletedProcess[str]],
    adb: str,
    serial: str,
    xml: str,
    description: str,
) -> None:
    node = _ui_node(xml, description)
    if node is None:
        raise VerificationError(f"Android UI is missing required control {description}")
    match = _BOUNDS_PATTERN.fullmatch(node.attrib.get("bounds", ""))
    if match is None:
        raise VerificationError(f"Android UI control {description} has invalid bounds")
    left, top, right, bottom = (int(value) for value in match.groups())
    if right <= left or bottom <= top:
        raise VerificationError(f"Android UI control {description} is not visible")
    _adb(runner, adb, serial, ["shell", "input", "tap", str((left + right) // 2), str((top + bottom) // 2)])


def _drive_android_agent_ui(
    adb: str,
    serial: str,
    package: str,
    location: str,
    challenge: str,
    timeout: float,
    *,
    runner: Callable[..., subprocess.CompletedProcess[str]],
    sleep_fn: Callable[[float], None],
    expected_cloud_url: str | None = None,
    expected_host_hash: str | None = None,
    expected_transport: str | None = None,
) -> tuple[str, str]:
    xml = _dump_android_ui(runner, adb, serial)
    if _ui_node(xml, "notemeld-agent-input") is None:
        _tap_ui(runner, adb, serial, xml, "notemeld-start-chat")
        sleep_fn(0.5)
        xml = _dump_android_ui(runner, adb, serial)
    _tap_ui(runner, adb, serial, xml, f"notemeld-agent-location-{location}")
    sleep_fn(0.25)
    xml = _dump_android_ui(runner, adb, serial)
    if expected_cloud_url is not None:
        configured = _ui_text(xml, "notemeld-cloud-target").rstrip("/")
        if configured != expected_cloud_url.rstrip("/"):
            raise VerificationError("Android app is not configured for the verified Cloud RC URL")
    if expected_host_hash is not None and expected_host_hash not in _ui_text(xml, "notemeld-remote-host"):
        raise VerificationError("Android app did not select the expected verified desktop Host")
    if _ui_node(xml, "notemeld-agent-permission") is not None:
        _tap_ui(runner, adb, serial, xml, "notemeld-agent-permission")
        sleep_fn(0.25)
        xml = _dump_android_ui(runner, adb, serial)
    _tap_ui(runner, adb, serial, xml, "notemeld-agent-input")
    _adb(runner, adb, serial, ["shell", "input", "text", f"Reply_exactly_{challenge}"])
    _adb(runner, adb, serial, ["shell", "input", "keyevent", "111"])
    xml = _dump_android_ui(runner, adb, serial)
    _tap_ui(runner, adb, serial, xml, "notemeld-agent-send-idle")

    deadline = time.monotonic() + timeout
    answer = ""
    final_xml = ""
    while time.monotonic() < deadline:
        sleep_fn(0.5)
        final_xml = _dump_android_ui(runner, adb, serial)
        answer = _ui_text(final_xml, "notemeld-message-assistant")
        transport_ok = expected_transport is None or _ui_text(final_xml, "notemeld-remote-transport").endswith(expected_transport)
        terminals = _ui_descriptions_with_prefix(final_xml, "notemeld-agent-terminal:")
        terminal_ok = terminals == ["notemeld-agent-terminal:turn.succeeded:1"]
        if _ui_node(final_xml, "notemeld-agent-send-idle") is not None and challenge in answer and transport_ok and terminal_ok:
            break
    else:
        raise VerificationError(f"Android {location} Agent did not return the unique challenge before timeout")

    pids = _adb(runner, adb, serial, ["shell", "pidof", package]).split()
    if not pids or not pids[0].isdigit():
        raise VerificationError("Android process exited during Agent chat")
    logs = _adb(runner, adb, serial, ["logcat", "-d", "--pid", pids[0], "-t", "200"])
    if "FATAL EXCEPTION" in logs:
        raise VerificationError("Android app emitted a fatal exception during Agent chat")
    return answer, final_xml


def _fetch_cloud_ready(base_url: str) -> Any:
    try:
        with urllib.request.urlopen(f"{base_url.rstrip('/')}/ready", timeout=15) as response:
            return json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
        raise VerificationError("verified Cloud RC readiness request failed") from exc


def _validate_cloud_evidence(base_url: str, expected_model: str, evidence: Any, ready: Any) -> dict[str, str]:
    parsed = urlparse(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise VerificationError("Android Cloud Agent requires an absolute credential-free HTTPS RC URL")
    if not expected_model or expected_model.startswith("deterministic-"):
        raise VerificationError("an explicit real Cloud model is required")
    if not isinstance(evidence, dict) or evidence.get("release_checks") != {"c_01": "PASS", "c_02": "PASS"}:
        raise VerificationError("Android Cloud Agent requires prior C-01/C-02 PASS evidence")
    if str(evidence.get("base_url", "")).rstrip("/") != base_url.rstrip("/") or evidence.get("model") != expected_model:
        raise VerificationError("C-01/C-02 evidence does not match the Android Cloud target and model")
    if not isinstance(ready, dict) or ready.get("ready") is not True or ready.get("environment") != "production" or ready.get("agent_backend") != "canonical-sdk":
        raise VerificationError("Android Cloud target is not a ready production Provider deployment")
    checks = ready.get("checks")
    required = {"database", "workspace_root", "relay", "device_proof_crypto", "agent_provider_config", "backup_storage_config", "otp_delivery_config", "device_proof_config", "release_identity"}
    if not isinstance(checks, dict) or any(checks.get(key) != "ok" for key in required):
        raise VerificationError("Android Cloud target readiness checks are incomplete")
    build_commit = evidence.get("build_commit")
    image_digest = evidence.get("cloud_image_digest")
    if (
        not isinstance(build_commit, str)
        or evidence.get("rc_commit") != build_commit
        or ready.get("build_commit") != build_commit
        or not isinstance(image_digest, str)
        or ready.get("image_digest") != image_digest
    ):
        raise VerificationError("Android Cloud target does not run the C-01 candidate image")
    return {key: "ok" for key in sorted(required)}


def run_android_agent(
    adb: str,
    serial: str | None,
    package: str,
    expected_version: str,
    expected_model: str,
    timeout: float,
    *,
    expected_commit: str | None = None,
    android_artifact_evidence: Any = None,
    base_url: str = "http://127.0.0.1:8483",
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    request_fn: Callable[..., Any] = request,
    sleep_fn: Callable[[float], None] = time.sleep,
    challenge: str | None = None,
) -> dict[str, Any]:
    """Drive the signed client UI through a real USB-forwarded desktop Agent."""
    base_url = _validate_loopback(base_url)
    if urlparse(base_url).port != 8483:
        raise VerificationError("Android host Agent adapter requires loopback port 8483")
    if not expected_model or expected_model.startswith("deterministic-"):
        raise VerificationError("an explicit real host model is required")
    request_fn(base_url, "GET", "/api/sys_health")
    models = request_fn(base_url, "GET", "/api/model_list")
    if not isinstance(models, list) or not models or not isinstance(models[0], dict):
        raise VerificationError("Android host has no enabled local model")
    selected_model = str(models[0].get("model_name") or "")
    if selected_model != expected_model:
        raise VerificationError("expected model is not the host model selected by a new Android session")
    artifact_binding = _validate_android_artifact_evidence(expected_version, expected_commit, android_artifact_evidence)

    serial = _resolve_android_device(adb, serial, runner)
    reverse_rule = "tcp:8483 tcp:8483"
    reverse_rules = _adb(runner, adb, serial, ["reverse", "--list"])
    created_reverse = reverse_rule not in reverse_rules
    if created_reverse:
        _adb(runner, adb, serial, ["reverse", "tcp:8483", "tcp:8483"])
    challenge = challenge or f"NMANDROID{uuid.uuid4().hex.upper()}"
    prompt = f"Reply_exactly_{challenge}"
    final_xml = ""
    try:
        runtime = run_android_runtime(
            adb, serial, package, expected_version, expected_commit=expected_commit,
            expected_installed_apk_sha256=artifact_binding["apk_sha256"], runner=runner, sleep_fn=sleep_fn,
        )
        xml = _dump_android_ui(runner, adb, serial)
        if _ui_node(xml, "notemeld-agent-input") is None:
            _tap_ui(runner, adb, serial, xml, "notemeld-start-chat")
            sleep_fn(0.5)
            xml = _dump_android_ui(runner, adb, serial)
        permission = _ui_node(xml, "notemeld-agent-permission")
        if permission is not None:
            _tap_ui(runner, adb, serial, xml, "notemeld-agent-permission")
            sleep_fn(0.25)
            xml = _dump_android_ui(runner, adb, serial)
        _tap_ui(runner, adb, serial, xml, "notemeld-agent-location-local")
        sleep_fn(0.25)
        xml = _dump_android_ui(runner, adb, serial)
        _tap_ui(runner, adb, serial, xml, "notemeld-agent-input")
        _adb(runner, adb, serial, ["shell", "input", "text", prompt])
        _adb(runner, adb, serial, ["shell", "input", "keyevent", "111"])
        xml = _dump_android_ui(runner, adb, serial)
        _tap_ui(runner, adb, serial, xml, "notemeld-agent-send-idle")

        deadline = time.monotonic() + timeout
        answer = ""
        while time.monotonic() < deadline:
            sleep_fn(0.5)
            final_xml = _dump_android_ui(runner, adb, serial)
            answer = _ui_text(final_xml, "notemeld-message-assistant")
            finished = _ui_node(final_xml, "notemeld-agent-send-idle") is not None
            terminals = _ui_descriptions_with_prefix(final_xml, "notemeld-agent-terminal:")
            if finished and challenge in answer and terminals == ["notemeld-agent-terminal:turn.succeeded:1"]:
                break
        else:
            raise VerificationError("Android host Agent did not return the unique challenge before timeout")

        pids = _adb(runner, adb, serial, ["shell", "pidof", package]).split()
        if not pids or not pids[0].isdigit():
            raise VerificationError("Android process exited during Agent chat")
        pid = pids[0]
        logs = _adb(runner, adb, serial, ["logcat", "-d", "--pid", pid, "-t", "200"])
        if "FATAL EXCEPTION" in logs:
            raise VerificationError("Android app emitted a fatal exception during Agent chat")
        return {
            **runtime,
            # This helper intentionally exercises the local desktop adapter
            # through adb reverse.  That is useful for development smoke only
            # and is explicitly ineligible for the Android release gate.
            "release_checks": {},
            "development_checks": {"android_local_host_smoke": "PASS"},
            "release_evidence": False,
            "not_for_release_reason": "adb reverse loopback is forbidden by the Android release objective",
            "host_model": selected_model,
            "transport": "adb-reverse-loopback",
            "a_01_evidence_sha256": artifact_binding["source_sha256"],
            "challenge_sha256": hashlib.sha256(challenge.encode("utf-8")).hexdigest(),
            "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "ui_sha256": hashlib.sha256(final_xml.encode("utf-8")).hexdigest(),
        }
    finally:
        try:
            _adb(runner, adb, serial, ["shell", "rm", "-f", _UI_DUMP_PATH])
        except VerificationError:
            pass
        if created_reverse:
            try:
                _adb(runner, adb, serial, ["reverse", "--remove", "tcp:8483"])
            except VerificationError:
                pass


def run_android_process_recovery(
    adb: str,
    serial: str,
    package: str,
    expected_version: str,
    timeout: float,
    *,
    expected_commit: str | None = None,
    expected_installed_apk_sha256: str | None = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    sleep_fn: Callable[[float], None] = time.sleep,
    challenge: str | None = None,
) -> dict[str, Any]:
    """Prove an embedded LOCAL turn becomes needs_attention after process death."""
    serial = _resolve_android_device(adb, serial, runner)
    runtime = run_android_runtime(
        adb, serial, package, expected_version,
        expected_commit=expected_commit,
        expected_installed_apk_sha256=expected_installed_apk_sha256,
        runner=runner, sleep_fn=sleep_fn,
    )
    challenge = challenge or f"NMANDROIDPROCESS{uuid.uuid4().hex.upper()}"
    xml = _dump_android_ui(runner, adb, serial)
    if _ui_node(xml, "notemeld-agent-input") is None:
        _tap_ui(runner, adb, serial, xml, "notemeld-start-chat")
        sleep_fn(0.5)
        xml = _dump_android_ui(runner, adb, serial)
    _tap_ui(runner, adb, serial, xml, "notemeld-agent-location-local")
    sleep_fn(0.25)
    xml = _dump_android_ui(runner, adb, serial)
    if _ui_node(xml, "notemeld-agent-permission") is not None:
        _tap_ui(runner, adb, serial, xml, "notemeld-agent-permission")
        sleep_fn(0.25)
        xml = _dump_android_ui(runner, adb, serial)
    _tap_ui(runner, adb, serial, xml, "notemeld-agent-input")
    _adb(runner, adb, serial, ["shell", "input", "text", f"Reply_exactly_{challenge}"])
    _adb(runner, adb, serial, ["shell", "input", "keyevent", "111"])
    xml = _dump_android_ui(runner, adb, serial)
    _tap_ui(runner, adb, serial, xml, "notemeld-agent-send-idle")
    deadline = time.monotonic() + min(timeout, 10.0)
    while time.monotonic() < deadline:
        sleep_fn(0.1)
        xml = _dump_android_ui(runner, adb, serial)
        if _ui_node(xml, "notemeld-agent-send-busy") is not None:
            break
    else:
        raise VerificationError("Android LOCAL turn never entered the sending state before process recovery")

    _adb(runner, adb, serial, ["shell", "am", "force-stop", package])
    launch = _adb(runner, adb, serial, ["shell", "am", "start", "-W", "-n", f"{package}/.MainActivity"])
    if "Status: ok" not in launch:
        raise VerificationError("Android process recovery cold launch did not report Status: ok")
    deadline = time.monotonic() + min(timeout, 30.0)
    recovered_xml = ""
    while time.monotonic() < deadline:
        sleep_fn(0.5)
        recovered_xml = _dump_android_ui(runner, adb, serial)
        terminals = _ui_descriptions_with_prefix(recovered_xml, "notemeld-agent-terminal:")
        projected = _ui_text(recovered_xml, "notemeld-message-assistant")
        if (
            terminals == ["notemeld-agent-terminal:turn.interrupted:needs_attention:1"]
            and _ui_text(recovered_xml, "notemeld-message-user").count(challenge) == 1
            and "未知副作用未自动重放" in projected
            and challenge not in projected
            and _ui_node(recovered_xml, "notemeld-agent-send-idle") is not None
        ):
            break
    else:
        raise VerificationError("Android process recovery did not project one needs_attention interruption")
    pids = _adb(runner, adb, serial, ["shell", "pidof", package]).split()
    if not pids or not pids[0].isdigit():
        raise VerificationError("Android process exited after process recovery")
    logs = _adb(runner, adb, serial, ["logcat", "-d", "--pid", pids[0], "-t", "200"])
    if "FATAL EXCEPTION" in logs:
        raise VerificationError("Android app emitted a fatal exception during process recovery")
    return {
        "process_recovery": True,
        "process_recovery_user_count": 1,
        "process_recovery_terminal": "turn.interrupted:needs_attention",
        "process_recovery_ui_sha256": hashlib.sha256(recovered_xml.encode("utf-8")).hexdigest(),
        **runtime,
    }


def run_android_cloud_agent(
    adb: str,
    serial: str | None,
    package: str,
    expected_version: str,
    base_url: str,
    expected_model: str,
    cloud_evidence: Any,
    timeout: float,
    *,
    expected_commit: str | None = None,
    android_artifact_evidence: Any = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ready_fn: Callable[[str], Any] = _fetch_cloud_ready,
    sleep_fn: Callable[[float], None] = time.sleep,
    challenge: str | None = None,
) -> dict[str, Any]:
    """Drive a pre-authenticated Android RC through the verified production Cloud."""
    ready_checks = _validate_cloud_evidence(base_url, expected_model, cloud_evidence, ready_fn(base_url))
    artifact_binding = _validate_android_artifact_evidence(expected_version, expected_commit, android_artifact_evidence)
    serial = _resolve_android_device(adb, serial, runner)
    challenge = challenge or f"NMANDROIDCLOUD{uuid.uuid4().hex.upper()}"
    try:
        runtime = run_android_runtime(
            adb, serial, package, expected_version, expected_commit=expected_commit,
            expected_installed_apk_sha256=artifact_binding["apk_sha256"], runner=runner, sleep_fn=sleep_fn,
        )
        answer, final_xml = _drive_android_agent_ui(
            adb,
            serial,
            package,
            "cloud",
            challenge,
            timeout,
            runner=runner,
            sleep_fn=sleep_fn,
            expected_cloud_url=base_url,
        )
        return {
            **runtime,
            "release_checks": {"a_03": "PASS"},
            "cloud_base_url": base_url.rstrip("/"),
            "cloud_model": expected_model,
            "build_commit": cloud_evidence["build_commit"],
            "cloud_image_digest": cloud_evidence["cloud_image_digest"],
            "a_01_evidence_sha256": artifact_binding["source_sha256"],
            "ready_checks": ready_checks,
            "challenge_sha256": hashlib.sha256(challenge.encode("utf-8")).hexdigest(),
            "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "ui_sha256": hashlib.sha256(final_xml.encode("utf-8")).hexdigest(),
        }
    finally:
        try:
            _adb(runner, adb, serial, ["shell", "rm", "-f", _UI_DUMP_PATH])
        except VerificationError:
                pass


def _validate_remote_host_evidence(base_url: str, host_device_id: str, evidence: Any) -> str:
    if not host_device_id:
        raise VerificationError("an explicit desktop Host device id is required")
    checks = evidence.get("release_checks") if isinstance(evidence, dict) else None
    if not isinstance(checks, dict) or checks.get("c_04_real_host") != "PASS" or checks.get("x_06_remote_agent") != "PASS":
        raise VerificationError("Android remote Agent requires prior real Host PASS evidence")
    if str(evidence.get("base_url", "")).rstrip("/") != base_url.rstrip("/") or evidence.get("host_device_id") != host_device_id:
        raise VerificationError("real Host evidence does not match the Android remote target")
    if evidence.get("host_platform") != "desktop" or evidence.get("cloud_persisted_commands") != 0 or evidence.get("cloud_persisted_events") != 0:
        raise VerificationError("real Host evidence is not release-safe")
    return hashlib.sha256(host_device_id.encode("utf-8")).hexdigest()[:12]


def run_android_remote_agent(
    adb: str,
    serial: str | None,
    package: str,
    expected_version: str,
    base_url: str,
    expected_cloud_model: str,
    host_device_id: str,
    expected_transport: str,
    cloud_evidence: Any,
    remote_host_evidence: Any,
    timeout: float,
    *,
    expected_commit: str | None = None,
    android_artifact_evidence: Any = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ready_fn: Callable[[str], Any] = _fetch_cloud_ready,
    sleep_fn: Callable[[float], None] = time.sleep,
    challenge: str | None = None,
) -> dict[str, Any]:
    if expected_transport not in {"lan", "relay"}:
        raise VerificationError("expected Android remote transport must be lan or relay")
    ready_checks = _validate_cloud_evidence(base_url, expected_cloud_model, cloud_evidence, ready_fn(base_url))
    host_hash = _validate_remote_host_evidence(base_url, host_device_id, remote_host_evidence)
    artifact_binding = _validate_android_artifact_evidence(expected_version, expected_commit, android_artifact_evidence)
    serial = _resolve_android_device(adb, serial, runner)
    challenge = challenge or f"NMANDROIDREMOTE{uuid.uuid4().hex.upper()}"
    try:
        runtime = run_android_runtime(
            adb, serial, package, expected_version, expected_commit=expected_commit,
            expected_installed_apk_sha256=artifact_binding["apk_sha256"], runner=runner, sleep_fn=sleep_fn,
        )
        answer, final_xml = _drive_android_agent_ui(
            adb,
            serial,
            package,
            "remote",
            challenge,
            timeout,
            runner=runner,
            sleep_fn=sleep_fn,
            expected_host_hash=host_hash,
            expected_transport=expected_transport,
        )
        release_id = "a_04" if expected_transport == "lan" else "a_05"
        return {
            **runtime,
            "release_checks": {release_id: "PASS"},
            "cloud_base_url": base_url.rstrip("/"),
            "cloud_model": expected_cloud_model,
            "build_commit": cloud_evidence["build_commit"],
            "cloud_image_digest": cloud_evidence["cloud_image_digest"],
            "host_device_sha256": hashlib.sha256(host_device_id.encode("utf-8")).hexdigest(),
            "transport": expected_transport,
            "a_01_evidence_sha256": artifact_binding["source_sha256"],
            "ready_checks": ready_checks,
            "challenge_sha256": hashlib.sha256(challenge.encode("utf-8")).hexdigest(),
            "answer_sha256": hashlib.sha256(answer.encode("utf-8")).hexdigest(),
            "ui_sha256": hashlib.sha256(final_xml.encode("utf-8")).hexdigest(),
        }
    finally:
        try:
            _adb(runner, adb, serial, ["shell", "rm", "-f", _UI_DUMP_PATH])
        except VerificationError:
            pass


def _android_network_radios(
    adb: str,
    serial: str,
    runner: Callable[..., subprocess.CompletedProcess[str]],
) -> dict[str, bool | None]:
    values: dict[str, bool | None] = {}
    for name, setting in (("wifi", "wifi_on"), ("data", "mobile_data")):
        raw = _adb(runner, adb, serial, ["shell", "settings", "get", "global", setting]).strip()
        if raw in {"0", "1"}:
            values[name] = raw == "1"
        elif raw in {"", "null"}:
            values[name] = None
        else:
            raise VerificationError(f"Android {name} radio state is invalid")
    if not any(value is True for value in values.values()):
        raise VerificationError("Android recovery evidence requires an enabled USB-connected network radio")
    return values


def _set_android_network_radios(
    adb: str,
    serial: str,
    state: dict[str, bool | None],
    runner: Callable[..., subprocess.CompletedProcess[str]],
    *,
    offline: bool,
) -> None:
    for name in ("wifi", "data"):
        original = state.get(name)
        if original is None:
            continue
        enabled = False if offline else original
        _adb(runner, adb, serial, ["shell", "svc", name, "enable" if enabled else "disable"])


def _relay_cursor_from_ui(xml: str) -> int:
    value = _ui_text(xml, "notemeld-remote-cursor")
    match = re.search(r"(\d+)\s*$", value)
    if match is None or int(match.group(1)) < 1:
        raise VerificationError("Android UI did not expose a valid Relay cursor")
    return int(match.group(1))


def run_android_recovery(
    adb: str,
    serial: str | None,
    package: str,
    expected_version: str,
    base_url: str,
    expected_cloud_model: str,
    host_device_id: str,
    cloud_evidence: Any,
    remote_host_evidence: Any,
    timeout: float,
    *,
    expected_commit: str | None = None,
    android_artifact_evidence: Any = None,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
    ready_fn: Callable[[str], Any] = _fetch_cloud_ready,
    sleep_fn: Callable[[float], None] = time.sleep,
    challenges: tuple[str, str, str] | None = None,
    verify_process_recovery: bool = False,
) -> dict[str, Any]:
    """Prove Android Relay read-only offline state and monotonic recovery."""
    ready_checks = _validate_cloud_evidence(base_url, expected_cloud_model, cloud_evidence, ready_fn(base_url))
    host_hash = _validate_remote_host_evidence(base_url, host_device_id, remote_host_evidence)
    artifact_binding = _validate_android_artifact_evidence(expected_version, expected_commit, android_artifact_evidence)
    serial = _resolve_android_device(adb, serial, runner)
    if ":" in serial:
        raise VerificationError("Android recovery evidence requires USB adb so radios can be restored")
    runtime = run_android_runtime(
        adb, serial, package, expected_version, expected_commit=expected_commit,
        expected_installed_apk_sha256=artifact_binding["apk_sha256"], runner=runner, sleep_fn=sleep_fn,
    )
    first_challenge, interrupted_challenge, recovered_challenge = challenges or (
        f"NMANDROIDRECOVERYA{uuid.uuid4().hex.upper()}",
        f"NMANDROIDRECOVERYB{uuid.uuid4().hex.upper()}",
        f"NMANDROIDRECOVERYC{uuid.uuid4().hex.upper()}",
    )
    radios: dict[str, bool | None] | None = None
    restored = False
    try:
        first_answer, first_xml = _drive_android_agent_ui(
            adb, serial, package, "remote", first_challenge, timeout,
            runner=runner, sleep_fn=sleep_fn, expected_host_hash=host_hash, expected_transport="relay",
        )
        first_cursor = _relay_cursor_from_ui(first_xml)
        radios = _android_network_radios(adb, serial, runner)

        active_xml = _dump_android_ui(runner, adb, serial)
        _tap_ui(runner, adb, serial, active_xml, "notemeld-agent-input")
        _adb(runner, adb, serial, ["shell", "input", "text", f"Reply_exactly_{interrupted_challenge}"])
        _adb(runner, adb, serial, ["shell", "input", "keyevent", "111"])
        active_xml = _dump_android_ui(runner, adb, serial)
        _tap_ui(runner, adb, serial, active_xml, "notemeld-agent-send-idle")
        deadline = time.monotonic() + min(timeout, 10.0)
        while time.monotonic() < deadline:
            sleep_fn(0.1)
            active_xml = _dump_android_ui(runner, adb, serial)
            if _ui_node(active_xml, "notemeld-agent-send-busy") is not None:
                break
        else:
            raise VerificationError("Android interrupted command never entered the sending state")
        _set_android_network_radios(adb, serial, radios, runner, offline=True)
        offline_xml = ""
        deadline = time.monotonic() + min(timeout, 60.0)
        while time.monotonic() < deadline:
            sleep_fn(0.5)
            offline_xml = _dump_android_ui(runner, adb, serial)
            input_node = _ui_node(offline_xml, "notemeld-agent-input")
            if (
                _ui_node(offline_xml, "notemeld-agent-offline-readonly") is not None
                and input_node is not None
                and input_node.attrib.get("enabled") == "false"
                and _ui_node(offline_xml, "notemeld-agent-send-idle") is not None
            ):
                break
        else:
            raise VerificationError("Android did not enter network-offline read-only mode")
        if _ui_text(offline_xml, "notemeld-message-user").count(interrupted_challenge) != 1:
            raise VerificationError("Android interrupted command was not retained exactly once")
        if interrupted_challenge in _ui_text(offline_xml, "notemeld-message-assistant"):
            raise VerificationError("Android command completed before the network interruption")

        _set_android_network_radios(adb, serial, radios, runner, offline=False)
        restored = True
        deadline = time.monotonic() + min(timeout, 60.0)
        while time.monotonic() < deadline:
            sleep_fn(0.5)
            online_xml = _dump_android_ui(runner, adb, serial)
            if _ui_node(online_xml, "notemeld-agent-offline-readonly") is None:
                break
        else:
            raise VerificationError("Android network did not recover before timeout")

        recovered_answer, recovered_xml = _drive_android_agent_ui(
            adb, serial, package, "remote", recovered_challenge, timeout,
            runner=runner, sleep_fn=sleep_fn, expected_host_hash=host_hash, expected_transport="relay",
        )
        recovered_cursor = _relay_cursor_from_ui(recovered_xml)
        if recovered_cursor <= first_cursor:
            raise VerificationError("Android Relay cursor did not continue monotonically after recovery")
        if interrupted_challenge in _ui_text(recovered_xml, "notemeld-message-assistant"):
            raise VerificationError("Android replayed the interrupted command after recovery")
        process_recovery = run_android_process_recovery(
            adb,
            serial,
            package,
            expected_version,
            min(timeout, 120.0),
            expected_commit=expected_commit,
            expected_installed_apk_sha256=artifact_binding["apk_sha256"],
            runner=runner,
            sleep_fn=sleep_fn,
        ) if verify_process_recovery else {}
        return {
            **runtime,
            **process_recovery,
            "release_checks": {"a_06": "PASS"},
            "cloud_base_url": base_url.rstrip("/"),
            "cloud_model": expected_cloud_model,
            "build_commit": cloud_evidence["build_commit"],
            "cloud_image_digest": cloud_evidence["cloud_image_digest"],
            "host_device_sha256": hashlib.sha256(host_device_id.encode("utf-8")).hexdigest(),
            "transport": "relay",
            "a_01_evidence_sha256": artifact_binding["source_sha256"],
            "ready_checks": ready_checks,
            "cursor_before": first_cursor,
            "cursor_after": recovered_cursor,
            "offline_read_only": True,
            "interrupted_command_count": 1,
            "first_answer_sha256": hashlib.sha256(first_answer.encode("utf-8")).hexdigest(),
            "interrupted_challenge_sha256": hashlib.sha256(interrupted_challenge.encode("utf-8")).hexdigest(),
            "recovered_answer_sha256": hashlib.sha256(recovered_answer.encode("utf-8")).hexdigest(),
            "offline_ui_sha256": hashlib.sha256(offline_xml.encode("utf-8")).hexdigest(),
        }
    finally:
        if radios is not None and not restored:
            try:
                _set_android_network_radios(adb, serial, radios, runner, offline=False)
            except VerificationError:
                pass
        try:
            _adb(runner, adb, serial, ["shell", "rm", "-f", _UI_DUMP_PATH])
        except VerificationError:
            pass


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    desktop = subparsers.add_parser("desktop")
    desktop.add_argument("--base-url", default="http://127.0.0.1:8483")
    desktop.add_argument("--expected-model", default=os.environ.get("NOTEMELD_EXPECTED_LOCAL_MODEL"))
    desktop.add_argument("--session-token", default=os.environ.get("NOTEMELD_DESKTOP_SESSION_TOKEN"))
    desktop.add_argument("--expected-version")
    desktop.add_argument("--installed-exe")
    desktop.add_argument("--timeout", type=float, default=180.0)
    android = subparsers.add_parser("android-runtime")
    android.add_argument("--adb", default="adb")
    android.add_argument("--serial")
    android.add_argument("--package", default="com.notemeld.mobile")
    android.add_argument("--expected-version", required=True)
    android.add_argument("--expected-commit", required=True)
    android.add_argument("--expected-apk")
    android.add_argument("--expected-signer-sha256", default=os.environ.get("NOTEMELD_ANDROID_SIGNER_SHA256"))
    android.add_argument("--apksigner", default=os.environ.get("NOTEMELD_APKSIGNER"))
    android_agent = subparsers.add_parser("android-agent")
    android_agent.add_argument("--adb", default="adb")
    android_agent.add_argument("--serial")
    android_agent.add_argument("--package", default="com.notemeld.mobile")
    android_agent.add_argument("--expected-version", required=True)
    android_agent.add_argument("--expected-commit", required=True)
    android_agent.add_argument("--expected-model", default=os.environ.get("NOTEMELD_EXPECTED_LOCAL_MODEL"))
    android_agent.add_argument("--android-artifact-evidence", default=os.environ.get("NOTEMELD_ANDROID_A01_EVIDENCE"))
    android_agent.add_argument("--base-url", default="http://127.0.0.1:8483")
    android_agent.add_argument("--timeout", type=float, default=180.0)
    android_cloud = subparsers.add_parser("android-cloud-agent")
    android_cloud.add_argument("--adb", default="adb")
    android_cloud.add_argument("--serial")
    android_cloud.add_argument("--package", default="com.notemeld.mobile")
    android_cloud.add_argument("--expected-version", required=True)
    android_cloud.add_argument("--expected-commit", required=True)
    android_cloud.add_argument("--base-url", default=os.environ.get("NOTEMELD_CLOUD_BASE_URL"))
    android_cloud.add_argument("--expected-model", default=os.environ.get("NOTEMELD_EXPECTED_CLOUD_MODEL"))
    android_cloud.add_argument("--cloud-evidence", default=os.environ.get("NOTEMELD_CLOUD_C02_EVIDENCE"))
    android_cloud.add_argument("--android-artifact-evidence", default=os.environ.get("NOTEMELD_ANDROID_A01_EVIDENCE"))
    android_cloud.add_argument("--timeout", type=float, default=180.0)
    android_remote = subparsers.add_parser("android-remote-agent")
    android_remote.add_argument("--adb", default="adb")
    android_remote.add_argument("--serial")
    android_remote.add_argument("--package", default="com.notemeld.mobile")
    android_remote.add_argument("--expected-version", required=True)
    android_remote.add_argument("--expected-commit", required=True)
    android_remote.add_argument("--base-url", default=os.environ.get("NOTEMELD_CLOUD_BASE_URL"))
    android_remote.add_argument("--expected-cloud-model", default=os.environ.get("NOTEMELD_EXPECTED_CLOUD_MODEL"))
    android_remote.add_argument("--host-device-id", default=os.environ.get("NOTEMELD_REMOTE_HOST_DEVICE_ID"))
    android_remote.add_argument("--expected-transport", required=True, choices=("lan", "relay"))
    android_remote.add_argument("--cloud-evidence", default=os.environ.get("NOTEMELD_CLOUD_C02_EVIDENCE"))
    android_remote.add_argument("--remote-host-evidence", default=os.environ.get("NOTEMELD_REMOTE_HOST_EVIDENCE"))
    android_remote.add_argument("--android-artifact-evidence", default=os.environ.get("NOTEMELD_ANDROID_A01_EVIDENCE"))
    android_remote.add_argument("--timeout", type=float, default=180.0)
    android_recovery = subparsers.add_parser("android-recovery")
    android_recovery.add_argument("--adb", default="adb")
    android_recovery.add_argument("--serial")
    android_recovery.add_argument("--package", default="com.notemeld.mobile")
    android_recovery.add_argument("--expected-version", required=True)
    android_recovery.add_argument("--expected-commit", required=True)
    android_recovery.add_argument("--base-url", default=os.environ.get("NOTEMELD_CLOUD_BASE_URL"))
    android_recovery.add_argument("--expected-cloud-model", default=os.environ.get("NOTEMELD_EXPECTED_CLOUD_MODEL"))
    android_recovery.add_argument("--host-device-id", default=os.environ.get("NOTEMELD_REMOTE_HOST_DEVICE_ID"))
    android_recovery.add_argument("--cloud-evidence", default=os.environ.get("NOTEMELD_CLOUD_C02_EVIDENCE"))
    android_recovery.add_argument("--remote-host-evidence", default=os.environ.get("NOTEMELD_REMOTE_HOST_EVIDENCE"))
    android_recovery.add_argument("--android-artifact-evidence", default=os.environ.get("NOTEMELD_ANDROID_A01_EVIDENCE"))
    android_recovery.add_argument("--verify-process-recovery", action="store_true")
    android_recovery.add_argument("--timeout", type=float, default=180.0)
    args = parser.parse_args()
    try:
        if args.command == "desktop":
            if not args.expected_model:
                raise VerificationError("--expected-model or NOTEMELD_EXPECTED_LOCAL_MODEL is required")
            result = run_desktop(
                args.base_url,
                args.expected_model,
                args.timeout,
                session_token=args.session_token,
                expected_version=args.expected_version,
                installed_exe=args.installed_exe,
            )
        elif args.command == "android-runtime":
            result = run_android_runtime(
                args.adb,
                args.serial,
                args.package,
                args.expected_version,
                expected_commit=args.expected_commit,
                expected_apk=args.expected_apk,
                expected_signer_sha256=args.expected_signer_sha256,
                apksigner=args.apksigner,
            )
        elif args.command == "android-agent":
            if not args.expected_model or not args.android_artifact_evidence:
                raise VerificationError("--expected-model and --android-artifact-evidence are required")
            artifact_evidence = json.loads(Path(args.android_artifact_evidence).read_text(encoding="utf-8"))
            result = run_android_agent(
                args.adb,
                args.serial,
                args.package,
                args.expected_version,
                args.expected_model,
                args.timeout,
                expected_commit=args.expected_commit,
                android_artifact_evidence=artifact_evidence,
                base_url=args.base_url,
            )
        elif args.command == "android-cloud-agent":
            if not args.base_url or not args.expected_model or not args.cloud_evidence or not args.android_artifact_evidence:
                raise VerificationError("--base-url, --expected-model, --cloud-evidence, and --android-artifact-evidence are required")
            evidence = json.loads(Path(args.cloud_evidence).read_text(encoding="utf-8"))
            artifact_evidence = json.loads(Path(args.android_artifact_evidence).read_text(encoding="utf-8"))
            result = run_android_cloud_agent(
                args.adb,
                args.serial,
                args.package,
                args.expected_version,
                args.base_url,
                args.expected_model,
                evidence,
                args.timeout,
                expected_commit=args.expected_commit,
                android_artifact_evidence=artifact_evidence,
                verify_process_recovery=args.verify_process_recovery,
            )
        elif args.command == "android-remote-agent":
            required = (args.base_url, args.expected_cloud_model, args.host_device_id, args.cloud_evidence, args.remote_host_evidence, args.android_artifact_evidence)
            if not all(required):
                raise VerificationError("Android remote verification requires Cloud URL/model, Host id, Cloud/Host evidence, and Android A-01 evidence")
            cloud_evidence = json.loads(Path(args.cloud_evidence).read_text(encoding="utf-8"))
            remote_evidence = json.loads(Path(args.remote_host_evidence).read_text(encoding="utf-8"))
            artifact_evidence = json.loads(Path(args.android_artifact_evidence).read_text(encoding="utf-8"))
            result = run_android_remote_agent(
                args.adb,
                args.serial,
                args.package,
                args.expected_version,
                args.base_url,
                args.expected_cloud_model,
                args.host_device_id,
                args.expected_transport,
                cloud_evidence,
                remote_evidence,
                args.timeout,
                expected_commit=args.expected_commit,
                android_artifact_evidence=artifact_evidence,
            )
        else:
            required = (args.base_url, args.expected_cloud_model, args.host_device_id, args.cloud_evidence, args.remote_host_evidence, args.android_artifact_evidence)
            if not all(required):
                raise VerificationError("Android recovery verification requires Cloud URL/model, Host id, Cloud/Host evidence, and Android A-01 evidence")
            cloud_evidence = json.loads(Path(args.cloud_evidence).read_text(encoding="utf-8"))
            remote_evidence = json.loads(Path(args.remote_host_evidence).read_text(encoding="utf-8"))
            artifact_evidence = json.loads(Path(args.android_artifact_evidence).read_text(encoding="utf-8"))
            result = run_android_recovery(
                args.adb,
                args.serial,
                args.package,
                args.expected_version,
                args.base_url,
                args.expected_cloud_model,
                args.host_device_id,
                cloud_evidence,
                remote_evidence,
                args.timeout,
                expected_commit=args.expected_commit,
                android_artifact_evidence=artifact_evidence,
            )
    except (VerificationError, KeyError, TypeError, OSError, json.JSONDecodeError) as exc:
        print(f"first-batch client verification failed: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
