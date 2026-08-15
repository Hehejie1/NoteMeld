from __future__ import annotations

import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import textwrap
import zipfile

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github" / "workflows" / "agent-sdk.yml"
SCRIPTS = ROOT / "agent-sdk" / "scripts"
VALIDATOR = SCRIPTS / "verify-artifact-manifest.py"

EXPECTED_TARGETS = {
    "x86_64-apple-darwin",
    "aarch64-apple-darwin",
    "x86_64-pc-windows-msvc",
    "x86_64-unknown-linux-gnu",
    "aarch64-unknown-linux-gnu",
    "aarch64-apple-ios",
    "aarch64-apple-ios-sim",
    "aarch64-linux-android",
    "armv7-linux-androideabi",
    "i686-linux-android",
    "x86_64-linux-android",
    "aarch64-unknown-linux-ohos",
}

EXPECTED_NATIVE_MATRIX = {
    ("macos-latest", "x86_64-apple-darwin"),
    ("macos-latest", "aarch64-apple-darwin"),
    ("windows-latest", "x86_64-pc-windows-msvc"),
    ("ubuntu-latest", "x86_64-unknown-linux-gnu"),
    ("ubuntu-24.04-arm", "aarch64-unknown-linux-gnu"),
}


def _workflow() -> tuple[dict, str]:
    source = WORKFLOW.read_text(encoding="utf-8")
    parsed = yaml.load(source, Loader=yaml.BaseLoader)
    assert isinstance(parsed, dict)
    return parsed, source


def _cargo_graph_fixture(directory: Path) -> tuple[Path, Path, dict[str, object]]:
    directory.mkdir(parents=True, exist_ok=True)
    lock = directory / "Cargo.lock"
    lock.write_text(
        'version = 4\n\n[[package]]\nname = "agent-ffi"\nversion = "0.1.0"\n',
        encoding="utf-8",
    )
    package_id = "path+file:///workspace/agent-ffi#0.1.0"
    metadata = directory / "cargo-metadata.json"
    metadata.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "id": package_id,
                        "name": "agent-ffi",
                        "version": "0.1.0",
                        "license": "MIT",
                    }
                ],
                "resolve": {
                    "nodes": [
                        {"id": package_id, "dependencies": [], "deps": []}
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    resolve_summary = json.dumps(
        [{"component": "agent-ffi@0.1.0", "dependencies": []}],
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    inventory = {
        "format_version": 1,
        "cargo_lock_sha256": hashlib.sha256(lock.read_bytes()).hexdigest(),
        "root_package": "agent-ffi@0.1.0",
        "resolve_sha256": hashlib.sha256(resolve_summary).hexdigest(),
        "packages": [{"component": "agent-ffi@0.1.0", "license": "MIT"}],
    }
    return metadata, lock, inventory


def _run_validator(root: Path, *expected_targets: str) -> subprocess.CompletedProcess[str]:
    metadata, lock, _ = _cargo_graph_fixture(root / ".validator-expected")
    command = [
        sys.executable,
        str(VALIDATOR),
        "verify",
        "--artifact-root",
        str(root),
        "--sdk-version",
        "0.1.0",
        "--schema-version",
        "1",
        "--binding-version",
        "0.1.0",
        "--expected-cargo-metadata",
        str(metadata),
        "--expected-cargo-lock",
        str(lock),
        "--root-package",
        "agent-ffi",
    ]
    for target in expected_targets:
        command.extend(("--expected-target", target))
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _entry(path: str, payload: bytes, target: str) -> dict[str, object]:
    return {
        "path": path,
        "kind": "native-library",
        "sdk_version": "0.1.0",
        "schema_version": "1",
        "target_triple": target,
        "binding_version": "0.1.0",
        "sha256": hashlib.sha256(payload).hexdigest(),
    }


def _write_manifest(root: Path, entries: list[dict[str, object]]) -> Path:
    manifest = root / "artifact-manifest.json"
    manifest.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "license_inventory": [
                    {"component": "notemeld-agent-sdk", "license": "MIT"}
                ],
                "artifacts": entries,
            }
        ),
        encoding="utf-8",
    )
    return manifest


def _write_complete_linux_bundle(root: Path) -> None:
    target = "x86_64-unknown-linux-gnu"
    _, lock_fixture, inventory_document = _cargo_graph_fixture(
        root / ".bundle-license-source"
    )
    lock = root / "Cargo.lock"
    shutil.copyfile(lock_fixture, lock)
    inventory = root / "license-inventory.json"
    inventory.write_text(json.dumps(inventory_document), encoding="utf-8")
    native = root / "libnotemeld_agent.so"
    native.write_bytes(b"\x7fELF" + b"\0" * 128)
    header = root / "notemeld_agent.h"
    header.write_text("const char *notemeld_agent_sdk_version(void);\n")
    abi = root / "abi-v1.json"
    abi.write_text(
        json.dumps({"abi_version": 1, "sdk_version": "0.1.0", "schema_version": "1"})
    )
    wheel = root / "notemeld_agent_sdk-0.1.0-py3-none-manylinux_2_28_x86_64.whl"
    _write_zip(
        wheel,
        {
            "notemeld_agent_sdk/notemeld-agent-sdk.json": _binding_marker(target),
            "notemeld_agent_sdk/native/libnotemeld_agent.so": native.read_bytes(),
            "notemeld_agent_sdk/runtime.py": 'SDK_VERSION = "0.1.0"\nSCHEMA_VERSION = "1"\n',
            "notemeld_agent_sdk-0.1.0.dist-info/METADATA": (
                "Metadata-Version: 2.1\nName: notemeld-agent-sdk\nVersion: 0.1.0\n"
            ),
        },
    )
    artifacts = [
        (native, "native-library"),
        (wheel, "python-wheel"),
        (header, "c-header"),
        (abi, "abi-contract"),
        (inventory, "license-inventory"),
        (lock, "cargo-lock"),
    ]
    entries = []
    for path, kind in artifacts:
        entry = _entry(path.name, path.read_bytes(), target)
        entry["kind"] = kind
        entries.append(entry)
    (root / "artifact-manifest.json").write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "cargo_lock_sha256": inventory_document["cargo_lock_sha256"],
                "license_inventory": inventory_document,
                "artifacts": entries,
            }
        ),
        encoding="utf-8",
    )


def _write_zip(path: Path, members: dict[str, bytes | str]) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        for name, payload in members.items():
            archive.writestr(name, payload)


def _binding_marker(*targets: str, sdk_version: str = "0.1.0") -> str:
    return json.dumps(
        {
            "sdk_version": sdk_version,
            "schema_version": "1",
            "binding_version": "0.1.0",
            "target_triples": list(targets),
        }
    )


def _assert_concrete_target_mappings(parsed: dict) -> None:
    jobs = parsed["jobs"]
    native = jobs["build-native"]["strategy"]["matrix"]["include"]
    assert {(entry["os"], entry["target"]) for entry in native} == EXPECTED_NATIVE_MATRIX

    native_upload = next(
        step for step in jobs["build-native"]["steps"]
        if step.get("uses") == "actions/upload-artifact@v4"
    )
    assert native_upload["with"]["path"] == "agent-sdk/dist/${{ matrix.target }}/"

    expected_uploads = {
        "build-swift": {
            "agent-sdk/dist/aarch64-apple-ios/",
            "agent-sdk/dist/aarch64-apple-ios-sim/",
        },
        "build-android": {
            "agent-sdk/dist/aarch64-linux-android/",
            "agent-sdk/dist/armv7-linux-androideabi/",
            "agent-sdk/dist/i686-linux-android/",
            "agent-sdk/dist/x86_64-linux-android/",
        },
        "build-harmony": {"agent-sdk/dist/aarch64-unknown-linux-ohos/"},
    }
    for job_name, expected in expected_uploads.items():
        upload = next(
            step for step in jobs[job_name]["steps"]
            if step.get("uses") == "actions/upload-artifact@v4"
        )
        assert set(upload["with"]["path"].splitlines()) == expected


def test_workflow_has_contract_first_platform_matrix_and_final_verification() -> None:
    parsed, source = _workflow()
    jobs = parsed["jobs"]

    assert "contracts" in jobs
    build_jobs = {
        "build-native",
        "build-swift",
        "build-android",
        "build-harmony",
    }
    assert build_jobs <= jobs.keys()
    assert all(jobs[name].get("needs") == "contracts" for name in build_jobs)

    final = jobs["verify-manifests"]
    assert set(final["needs"]) == build_jobs
    assert "verify-artifact-manifest.py verify" in source
    assert "actions/download-artifact@v4" in source


def test_workflow_requires_every_platform_target_and_real_target_tooling() -> None:
    parsed, source = _workflow()

    _assert_concrete_target_mappings(parsed)
    for evidence in (
        "cargo build",
        "xcodebuild",
        "connectedAndroidTest",
        "assembleHar",
        "ohpm",
        "hvigor",
    ):
        assert evidence in source
    assert "chmod +x" in source
    assert "continue-on-error: true" not in source


def test_target_mapping_oracle_rejects_matrix_entry_removal() -> None:
    parsed, _ = _workflow()
    native = parsed["jobs"]["build-native"]["strategy"]["matrix"]["include"]
    parsed["jobs"]["build-native"]["strategy"]["matrix"]["include"] = [
        entry for entry in native
        if entry["target"] != "aarch64-unknown-linux-gnu"
    ]

    with pytest.raises(AssertionError):
        _assert_concrete_target_mappings(parsed)


@pytest.mark.parametrize(
    ("script_name", "tool_markers"),
    [
        ("build-python.sh", ("cargo build", "verify-artifact-manifest.py create")),
        ("build-swift.sh", ("cargo rustc", "xcodebuild", "swift build")),
        ("build-kotlin.sh", ("cargo ndk", "assembleRelease")),
        ("build-harmony.sh", ("cargo build", "ohpm", "assembleHar")),
    ],
)
def test_build_scripts_are_fail_closed_and_create_real_artifacts(
    script_name: str, tool_markers: tuple[str, ...]
) -> None:
    script = SCRIPTS / script_name
    source = script.read_text(encoding="utf-8")

    assert os.access(script, os.X_OK)
    assert "set -euo pipefail" in source
    assert "git rev-parse --show-toplevel" in source
    assert "touch " not in source
    assert "|| true" not in source
    assert "cargo metadata" in source
    assert "license-inventory.json" in source
    assert "SOURCE_DATE_EPOCH" in source
    for marker in tool_markers:
        assert marker in source


@pytest.mark.parametrize(
    "script_name",
    ["build-swift.sh", "build-kotlin.sh", "build-harmony.sh"],
)
def test_platform_archives_are_repacked_deterministically(script_name: str) -> None:
    source = (SCRIPTS / script_name).read_text(encoding="utf-8")

    assert "ZipInfo" in source
    assert "SOURCE_DATE_EPOCH" in source


def test_swift_packager_reads_cargo_rustc_staticlib_from_deps_directory() -> None:
    source = (SCRIPTS / "build-swift.sh").read_text(encoding="utf-8")

    assert "release/deps/libnotemeld_agent.a" in source


def test_harmony_build_configures_real_sysroot_and_sdk_consumer_gate() -> None:
    source = (SCRIPTS / "build-harmony.sh").read_text(encoding="utf-8")
    _, workflow = _workflow()

    assert 'OHOS_SDK_ROOT="${OHOS_SDK_ROOT:?' in source
    assert 'SYSROOT="$OHOS_SDK_NATIVE/sysroot"' in source
    assert '--sysroot=' in source
    assert '-D__MUSL__=1' in source
    assert "local.properties" in source
    assert "hwsdk.dir=" in source
    assert "HOS_SDK_HOME" in source
    assert "apiVersion" in source
    assert "compileSdkVersion" in source
    assert "compatibleSdkVersion" in source
    assert "for sdk_component in ets native toolchains" in source
    assert '"$OHOS_SDK_ROOT/$sdk_component"' in source
    assert "harmony-har-consumer" in source
    assert source.count("assembleHar") >= 2
    assert "OHOS_SDK_ROOT" in workflow
    assert "*-linux-*.zip" in workflow
    for variable in (
        "OPENHARMONY_SDK_URL",
        "OPENHARMONY_COMMANDLINE_TOOLS_URL",
        "OPENHARMONY_SDK_SHA256",
        "OPENHARMONY_COMMANDLINE_TOOLS_SHA256",
    ):
        assert variable in workflow


def test_swift_release_is_self_contained_and_links_both_ios_consumers() -> None:
    source = (SCRIPTS / "build-swift.sh").read_text(encoding="utf-8")
    parsed, _ = _workflow()
    swift_steps = "\n".join(
        str(step.get("run", "")) for step in parsed["jobs"]["build-swift"]["steps"]
    )

    assert ".binaryTarget(" in source
    assert "NoteMeldAgentNative.xcframework" in source
    assert "notemeld_agent.h" in source
    assert "module.modulemap" in source
    assert "swift-release-consumer" in source
    assert "generic/platform=iOS" in source
    assert "generic/platform=iOS Simulator" in source
    assert "build-swift.sh" in swift_steps


def test_native_job_does_not_invoke_uninstalled_pytest() -> None:
    parsed, _ = _workflow()
    commands = "\n".join(
        str(step.get("run", "")) for step in parsed["jobs"]["build-native"]["steps"]
    )

    assert "python -m pytest" not in commands or "pip install" in commands


def test_android_runtime_gate_consumes_repacked_aar() -> None:
    parsed, _ = _workflow()
    source = (SCRIPTS / "build-kotlin.sh").read_text(encoding="utf-8")
    emulator = next(
        step for step in parsed["jobs"]["build-android"]["steps"]
        if step.get("uses") == "reactivecircus/android-emulator-runner@v2"
    )

    assert "android-aar-consumer" in emulator["with"]["script"]
    assert "android-aar-consumer" in source
    assert "implementation(files(" in source
    assert "libnotemeld_agent_jni.so" in source


def test_python_release_uses_packaged_native_clean_venv_and_manylinux() -> None:
    parsed, workflow = _workflow()
    source = (SCRIPTS / "build-python.sh").read_text(encoding="utf-8")

    runtime_source = (
        ROOT / "agent-sdk" / "bindings" / "python" / "notemeld_agent_sdk" / "runtime.py"
    ).read_text(encoding="utf-8")
    assert "importlib.resources" in runtime_source or "from importlib import resources" in runtime_source
    assert "venv" in source
    assert "pip install" in source
    assert "Runtime(driver=" in source
    assert "auditwheel repair" in source
    assert "manylinux_2_28_x86_64" in workflow
    assert "manylinux_2_28_aarch64" in workflow
    assert parsed["jobs"]["build-native"]["needs"] == "contracts"


def test_python_package_resource_discovery_finds_platform_native(
    tmp_path: Path,
) -> None:
    source_package = (
        ROOT / "agent-sdk" / "bindings" / "python" / "notemeld_agent_sdk"
    )
    package = tmp_path / "notemeld_agent_sdk"
    shutil.copytree(source_package, package)
    native = package / "native"
    native.mkdir()
    library_name = (
        "notemeld_agent.dll" if sys.platform == "win32"
        else "libnotemeld_agent.dylib" if sys.platform == "darwin"
        else "libnotemeld_agent.so"
    )
    expected = native / library_name
    expected.write_bytes(b"native payload")
    probe = textwrap.dedent(
        """
        from pathlib import Path
        from notemeld_agent_sdk.runtime import _packaged_native_library
        discovered = _packaged_native_library()
        assert discovered is not None
        assert Path(str(discovered)).resolve() == Path(__import__('sys').argv[1]).resolve()
        """
    )

    result = subprocess.run(
        [sys.executable, "-c", probe, str(expected)],
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_manifest_validator_accepts_complete_matching_artifact(tmp_path: Path) -> None:
    _write_complete_linux_bundle(tmp_path)

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["targets"] == ["x86_64-unknown-linux-gnu"]
    assert summary["artifact_count"] == 6


def test_license_inventory_is_derived_from_cargo_metadata(tmp_path: Path) -> None:
    metadata = tmp_path / "cargo-metadata.json"
    cargo_lock = tmp_path / "Cargo.lock"
    output = tmp_path / "license-inventory.json"
    ffi_id = "path+file:///workspace/agent-ffi#0.1.0"
    serde_id = "registry+https://github.com/rust-lang/crates.io-index#serde@1.0.229"
    metadata.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "id": serde_id,
                        "name": "serde",
                        "version": "1.0.229",
                        "license": "MIT OR Apache-2.0",
                    },
                    {
                        "id": ffi_id,
                        "name": "agent-ffi",
                        "version": "0.1.0",
                        "license": "MIT",
                    },
                ],
                "resolve": {
                    "nodes": [
                        {"id": ffi_id, "dependencies": [serde_id], "deps": []},
                        {"id": serde_id, "dependencies": [], "deps": []},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    cargo_lock.write_text(
        """# generated\nversion = 4\n\n[[package]]\nname = "agent-ffi"\nversion = "0.1.0"\n\n[[package]]\nname = "serde"\nversion = "1.0.229"\n""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "licenses",
            "--cargo-metadata",
            str(metadata),
            "--cargo-lock",
            str(cargo_lock),
            "--root-package",
            "agent-ffi",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(output.read_text(encoding="utf-8"))
    expected_resolve = json.dumps(
        [
            {
                "component": "agent-ffi@0.1.0",
                "dependencies": ["serde@1.0.229"],
            },
            {"component": "serde@1.0.229", "dependencies": []},
        ],
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    assert inventory == {
        "format_version": 1,
        "cargo_lock_sha256": hashlib.sha256(cargo_lock.read_bytes()).hexdigest(),
        "root_package": "agent-ffi@0.1.0",
        "resolve_sha256": hashlib.sha256(expected_resolve).hexdigest(),
        "packages": [
            {"component": "agent-ffi@0.1.0", "license": "MIT"},
            {"component": "serde@1.0.229", "license": "MIT OR Apache-2.0"},
        ],
    }


def test_license_inventory_is_limited_to_agent_ffi_resolve_closure(
    tmp_path: Path,
) -> None:
    metadata = tmp_path / "cargo-metadata.json"
    cargo_lock = tmp_path / "Cargo.lock"
    output = tmp_path / "license-inventory.json"
    ffi_id = "path+file:///workspace/agent-ffi#0.1.0"
    serde_id = "registry+https://github.com/rust-lang/crates.io-index#serde@1.0.229"
    unrelated_id = "path+file:///workspace/agent-reference#0.1.0"
    metadata.write_text(
        json.dumps(
            {
                "packages": [
                    {
                        "id": ffi_id,
                        "name": "agent-ffi",
                        "version": "0.1.0",
                        "license": "MIT",
                    },
                    {
                        "id": serde_id,
                        "name": "serde",
                        "version": "1.0.229",
                        "license": "MIT OR Apache-2.0",
                    },
                    {
                        "id": unrelated_id,
                        "name": "agent-reference",
                        "version": "0.1.0",
                        "license": "MIT",
                    },
                ],
                "resolve": {
                    "nodes": [
                        {"id": ffi_id, "dependencies": [serde_id], "deps": []},
                        {"id": serde_id, "dependencies": [], "deps": []},
                        {"id": unrelated_id, "dependencies": [], "deps": []},
                    ]
                },
            }
        ),
        encoding="utf-8",
    )
    cargo_lock.write_text(
        """version = 4

[[package]]
name = "agent-ffi"
version = "0.1.0"

[[package]]
name = "agent-reference"
version = "0.1.0"

[[package]]
name = "serde"
version = "1.0.229"
""",
        encoding="utf-8",
    )

    result = subprocess.run(
        [
            sys.executable,
            str(VALIDATOR),
            "licenses",
            "--cargo-metadata",
            str(metadata),
            "--cargo-lock",
            str(cargo_lock),
            "--root-package",
            "agent-ffi",
            "--output",
            str(output),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    inventory = json.loads(output.read_text(encoding="utf-8"))
    assert inventory["root_package"] == "agent-ffi@0.1.0"
    assert [entry["component"] for entry in inventory["packages"]] == [
        "agent-ffi@0.1.0",
        "serde@1.0.229",
    ]
    assert len(inventory["resolve_sha256"]) == 64


def test_final_verifier_attests_checkout_lock_and_resolve_closure() -> None:
    parsed, source = _workflow()

    assert "cargo metadata" in source
    assert "--locked" in source
    assert "--expected-cargo-lock agent-sdk/Cargo.lock" in source
    assert "--expected-cargo-metadata" in source
    assert "--root-package agent-ffi" in source
    assert any(
        step.get("uses") == "dtolnay/rust-toolchain@master"
        for step in parsed["jobs"]["verify-manifests"]["steps"]
    )


def test_manifest_validator_rejects_duplicate_target_manifests(tmp_path: Path) -> None:
    for directory_name in ("first", "second"):
        directory = tmp_path / directory_name
        directory.mkdir()
        _write_complete_linux_bundle(directory)

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "duplicate target manifest" in result.stderr.lower()


def test_manifest_validator_rejects_placeholder_only_bundle(tmp_path: Path) -> None:
    payload = b"placeholder"
    (tmp_path / "agent.bin").write_bytes(payload)
    _write_manifest(
        tmp_path,
        [_entry("agent.bin", payload, "x86_64-unknown-linux-gnu")],
    )

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "placeholder" in result.stderr.lower()


@pytest.mark.parametrize(
    ("kind", "target", "marker_path", "suffix"),
    [
        (
            "python-wheel",
            "x86_64-unknown-linux-gnu",
            "notemeld_agent_sdk/notemeld-agent-sdk.json",
            ".whl",
        ),
        (
            "kotlin-aar",
            "x86_64-linux-android",
            "META-INF/notemeld-agent-sdk.json",
            ".aar",
        ),
        (
            "swift-xcframework",
            "aarch64-apple-ios",
            "notemeld-agent-sdk.json",
            ".zip",
        ),
        (
            "openharmony-har",
            "aarch64-unknown-linux-ohos",
            "notemeld-agent-sdk.json",
            ".har",
        ),
    ],
)
def test_manifest_validator_rejects_internal_container_version_drift(
    tmp_path: Path,
    kind: str,
    target: str,
    marker_path: str,
    suffix: str,
) -> None:
    container = tmp_path / f"bundle{suffix}"
    _write_zip(container, {marker_path: _binding_marker(target, sdk_version="9.9.9")})
    payload = container.read_bytes()
    entry = _entry(container.name, payload, target)
    entry["kind"] = kind
    _write_manifest(tmp_path, [entry])

    result = _run_validator(tmp_path, target)

    assert result.returncode != 0
    assert "container sdk_version mismatch" in result.stderr.lower()


def test_manifest_validator_rejects_wrong_artifact_kind(tmp_path: Path) -> None:
    payload = b"\x7fELF" + b"\0" * 64
    (tmp_path / "libnotemeld_agent.so").write_bytes(payload)
    entry = _entry("libnotemeld_agent.so", payload, "x86_64-unknown-linux-gnu")
    entry["kind"] = "release-bundle"
    _write_manifest(tmp_path, [entry])

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "artifact kind" in result.stderr.lower()


def test_manifest_validator_requires_one_license_artifact(tmp_path: Path) -> None:
    payload = b"\x7fELF" + b"\0" * 64
    (tmp_path / "libnotemeld_agent.so").write_bytes(payload)
    _write_manifest(
        tmp_path,
        [_entry("libnotemeld_agent.so", payload, "x86_64-unknown-linux-gnu")],
    )

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "license-inventory artifact" in result.stderr.lower()


def test_manifest_validator_rejects_duplicate_license_artifacts(tmp_path: Path) -> None:
    entries = []
    for name in ("licenses-one.json", "licenses-two.json"):
        payload = b'[{"component":"agent-ffi@0.1.0","license":"MIT"}]'
        (tmp_path / name).write_bytes(payload)
        entry = _entry(name, payload, "x86_64-unknown-linux-gnu")
        entry["kind"] = "license-inventory"
        entries.append(entry)
    _write_manifest(tmp_path, entries)

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "exactly one license-inventory" in result.stderr.lower()


def test_manifest_validator_rejects_malformed_abi_json(tmp_path: Path) -> None:
    payload = b"{not-json"
    (tmp_path / "abi-v1.json").write_bytes(payload)
    entry = _entry("abi-v1.json", payload, "x86_64-unknown-linux-gnu")
    entry["kind"] = "abi-contract"
    _write_manifest(tmp_path, [entry])

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "invalid abi contract" in result.stderr.lower()


def test_manifest_validator_rejects_android_aar_missing_jni_bridge(
    tmp_path: Path,
) -> None:
    target = "x86_64-linux-android"
    aar = tmp_path / "notemeld-agent.aar"
    members = {"META-INF/notemeld-agent-sdk.json": _binding_marker(target)}
    for abi in ("armeabi-v7a", "arm64-v8a", "x86", "x86_64"):
        members[f"jni/{abi}/libnotemeld_agent.so"] = b"\x7fELF" + b"\0" * 64
    _write_zip(aar, members)
    entry = _entry(aar.name, aar.read_bytes(), target)
    entry["kind"] = "kotlin-aar"
    _write_manifest(tmp_path, [entry])

    result = _run_validator(tmp_path, target)

    assert result.returncode != 0
    assert "libnotemeld_agent_jni.so" in result.stderr


def test_manifest_validator_rejects_swift_package_with_empty_xcframework(
    tmp_path: Path,
) -> None:
    target = "aarch64-apple-ios"
    package = tmp_path / "NoteMeldAgentSwiftPackage.zip"
    _write_zip(
        package,
        {
            "notemeld-agent-sdk.json": _binding_marker(
                "aarch64-apple-ios", "aarch64-apple-ios-sim"
            ),
            "Package.swift": (
                '.binaryTarget(name: "CNotemeldAgent", '
                'path: "NoteMeldAgentNative.xcframework")'
            ),
            "NoteMeldAgentNative.xcframework/Info.plist": "empty",
        },
    )
    entry = _entry(package.name, package.read_bytes(), target)
    entry["kind"] = "swift-package"
    _write_manifest(tmp_path, [entry])

    result = _run_validator(tmp_path, target)

    assert result.returncode != 0
    assert "embedded xcframework is missing" in result.stderr.lower()


def test_manifest_validator_rejects_lock_digest_drift(tmp_path: Path) -> None:
    lock = tmp_path / "Cargo.lock"
    lock.write_text('version = 4\n[[package]]\nname="agent-ffi"\nversion="0.1.0"\n')
    inventory = tmp_path / "license-inventory.json"
    inventory.write_text(
        json.dumps(
                {
                    "format_version": 1,
                    "cargo_lock_sha256": "0" * 64,
                    "root_package": "agent-ffi@0.1.0",
                    "resolve_sha256": "1" * 64,
                    "packages": [{"component": "agent-ffi@0.1.0", "license": "MIT"}],
                }
        )
    )
    entries = []
    for path, kind in ((lock, "cargo-lock"), (inventory, "license-inventory")):
        entry = _entry(path.name, path.read_bytes(), "x86_64-unknown-linux-gnu")
        entry["kind"] = kind
        entries.append(entry)
    _write_manifest(tmp_path, entries)

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "cargo lock digest mismatch" in result.stderr.lower()


def test_manifest_validator_rejects_consistently_substituted_artifact_lock(
    tmp_path: Path,
) -> None:
    _write_complete_linux_bundle(tmp_path)
    lock = tmp_path / "Cargo.lock"
    lock.write_text(
        lock.read_text(encoding="utf-8")
        + '\n[[package]]\nname = "substituted"\nversion = "9.9.9"\n',
        encoding="utf-8",
    )
    inventory_path = tmp_path / "license-inventory.json"
    inventory = json.loads(inventory_path.read_text(encoding="utf-8"))
    inventory["cargo_lock_sha256"] = hashlib.sha256(lock.read_bytes()).hexdigest()
    inventory_path.write_text(json.dumps(inventory), encoding="utf-8")
    manifest_path = tmp_path / "artifact-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["license_inventory"] = inventory
    manifest["cargo_lock_sha256"] = inventory["cargo_lock_sha256"]
    for entry in manifest["artifacts"]:
        artifact = tmp_path / entry["path"]
        entry["sha256"] = hashlib.sha256(artifact.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "checkout cargo resolve closure" in result.stderr.lower()


def test_manifest_validator_rejects_symlink_artifact(tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside-native.so"
    outside.write_bytes(b"\x7fELF" + b"\0" * 64)
    linked = tmp_path / "linked.so"
    linked.symlink_to(outside)
    entry = _entry("linked.so", outside.read_bytes(), "x86_64-unknown-linux-gnu")
    _write_manifest(tmp_path, [entry])

    result = _run_validator(tmp_path, "x86_64-unknown-linux-gnu")

    assert result.returncode != 0
    assert "symlink" in result.stderr.lower() or "escapes" in result.stderr.lower()


@pytest.mark.parametrize(
    ("mutation", "expected_error"),
    [
        ("missing_field", "missing field"),
        ("duplicate", "duplicate artifact path"),
        ("escape", "escapes artifact root"),
        ("checksum", "checksum mismatch"),
        ("target", "unexpected target"),
        ("version", "sdk_version mismatch"),
        ("missing_target", "missing expected target"),
    ],
)
def test_manifest_validator_rejects_invalid_or_incomplete_manifests(
    tmp_path: Path, mutation: str, expected_error: str
) -> None:
    _write_complete_linux_bundle(tmp_path)
    manifest_path = tmp_path / "artifact-manifest.json"
    document = json.loads(manifest_path.read_text(encoding="utf-8"))
    entries = document["artifacts"]
    entry = entries[0]
    expected_targets = ["x86_64-unknown-linux-gnu"]

    if mutation == "missing_field":
        del entry["binding_version"]
    elif mutation == "duplicate":
        entries.append(dict(entry))
    elif mutation == "escape":
        outside = tmp_path.parent / "outside.bin"
        outside.write_bytes((tmp_path / entry["path"]).read_bytes())
        entry["path"] = "../outside.bin"
    elif mutation == "checksum":
        entry["sha256"] = "0" * 64
    elif mutation == "target":
        entry["target_triple"] = "unknown-target"
    elif mutation == "version":
        entry["sdk_version"] = "9.9.9"
    elif mutation == "missing_target":
        expected_targets.append("aarch64-unknown-linux-gnu")

    manifest_path.write_text(json.dumps(document), encoding="utf-8")
    result = _run_validator(tmp_path, *expected_targets)

    assert result.returncode != 0
    assert expected_error in result.stderr.lower()
