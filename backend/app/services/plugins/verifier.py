from __future__ import annotations

import hashlib
import json
import os
import shutil
import stat
import uuid
import zipfile
from pathlib import Path, PurePosixPath

from app.services.plugins.release_resolver import MAX_RELEASE_BYTES
from app.utils.storage_paths import plugin_staging_dir


class PluginVerificationError(ValueError):
    pass


ALLOWED_LICENSES = {"MIT", "Apache-2.0", "BSD-2-Clause", "BSD-3-Clause", "MPL-2.0"}
FORBIDDEN_INSTALL_NAMES = {"install.sh", "install.py", "setup.py", "postinstall", "preinstall"}


def _validate_member(name: str, info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "" in path.parts:
        raise PluginVerificationError("zip contains an unsafe path")
    if stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
        raise PluginVerificationError("zip symlinks are not allowed")
    if path.name.lower() in FORBIDDEN_INSTALL_NAMES:
        raise PluginVerificationError("install scripts are not allowed")


def stage_and_verify(content: bytes, *, expected_sha256: str | None = None, expected_plugin_id: str | None = None,
                     expected_version: str | None = None, max_bytes: int = MAX_RELEASE_BYTES) -> tuple[Path, dict, str]:
    if len(content) > max_bytes:
        raise PluginVerificationError("package exceeds maximum size")
    digest = hashlib.sha256(content).hexdigest()
    if expected_sha256 and digest.lower() != expected_sha256.lower():
        raise PluginVerificationError("package sha256 does not match release metadata")
    root = plugin_staging_dir()
    root.mkdir(parents=True, exist_ok=True)
    staging = root / uuid.uuid4().hex
    staging.mkdir(mode=0o700)
    try:
        archive_path = staging / "package.zip"
        archive_path.write_bytes(content)
        with zipfile.ZipFile(archive_path) as archive:
            infos = archive.infolist()
            if not infos:
                raise PluginVerificationError("empty plugin package")
            for info in infos:
                _validate_member(info.filename, info)
            archive.extractall(staging / "payload")
        manifest_path = staging / "payload" / "plugin.json"
        if not manifest_path.is_file():
            raise PluginVerificationError("plugin.json is required")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if not isinstance(manifest, dict):
            raise PluginVerificationError("plugin manifest must be an object")
        plugin_id, version = manifest.get("id"), manifest.get("version")
        license_name, sdk_version = manifest.get("license"), manifest.get("sdk_version")
        if not all(isinstance(value, str) and value.strip() for value in (plugin_id, version, license_name, sdk_version)):
            raise PluginVerificationError("plugin id, version, sdk_version and license are required")
        if expected_plugin_id and plugin_id != expected_plugin_id:
            raise PluginVerificationError("plugin id does not match request")
        if expected_version and version != expected_version:
            raise PluginVerificationError("plugin version does not match request")
        if license_name not in ALLOWED_LICENSES:
            raise PluginVerificationError("plugin license is not allowed")
        if any(char in plugin_id for char in "/\\"):
            raise PluginVerificationError("invalid plugin id")
        manifest["requested_permissions"] = sorted(set(manifest.get("requested_permissions", [])))
        manifest["runtime"] = manifest.get("runtime") or {}
        runtime_command = manifest["runtime"].get("command")
        if isinstance(runtime_command, list) and any(PurePosixPath(str(item)).name.lower() in FORBIDDEN_INSTALL_NAMES for item in runtime_command):
            raise PluginVerificationError("install scripts are not allowed")
        return staging, manifest, digest
    except Exception:
        shutil.rmtree(staging, ignore_errors=True)
        raise


def promote_staged(staging: Path, plugin_id: str, version: str, versions_root: Path) -> Path:
    target_root = versions_root / plugin_id
    target_root.mkdir(parents=True, exist_ok=True)
    target = target_root / version
    if target.exists():
        raise PluginVerificationError("immutable plugin version already exists")
    os.replace(staging / "payload", target)
    shutil.rmtree(staging, ignore_errors=True)
    return target
