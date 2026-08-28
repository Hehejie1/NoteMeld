from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

PROTOCOL = "notemeld.application.v1"
SUPPORTED_RUNTIME_KINDS = {"process-jsonl", "managed-worker"}
SUPPORTED_PLATFORMS = {"desktop", "web", "mobile"}
CAPABILITIES = {"wiki.read", "workspace.file.read", "workspace.file.write", "app.data.get", "app.data.put", "app.data.list", "artifact.create", "artifact.read", "agent.run", "plugin.invoke"}
PERMISSIONS = {"workspace.read", "workspace.write", "network.egress", "agent.run", "plugin.invoke"}
MAX_PACKAGE_BYTES = 64 * 1024 * 1024
_ID_RE = re.compile(r"^[a-z][a-z0-9._-]{0,63}$")
_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")


def default_application_package_root() -> Path:
    """Resolve the trusted package root in source and PyInstaller layouts."""
    module_path = Path(__file__).resolve()
    candidates = (module_path.parents[3] / "applications", module_path.parents[2] / "applications")
    for candidate in candidates:
        if candidate.is_dir():
            return candidate
    return candidates[0]


class ApplicationManifestError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code, self.message = code, message


def _path(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ApplicationManifestError("invalid_manifest", f"{field} is required")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts or "" in path.parts or "\\" in value:
        raise ApplicationManifestError("unsafe_manifest_path", f"{field} must be a relative safe path")


def _strings(value: Any, field: str, allowed: set[str]) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise ApplicationManifestError("invalid_manifest", f"{field} must be a list of strings")
    if len(value) != len(set(value)):
        raise ApplicationManifestError("duplicate_manifest_value", f"{field} contains duplicates")
    if set(value) - allowed:
        raise ApplicationManifestError("unsupported_manifest_value", f"unsupported {field}")
    return value


def validate_manifest(manifest: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(manifest, dict):
        raise ApplicationManifestError("invalid_manifest", "application manifest must be an object")
    if manifest.get("protocol") != PROTOCOL:
        raise ApplicationManifestError("unsupported_protocol", "unsupported application protocol")
    if not isinstance(manifest.get("id"), str) or not _ID_RE.fullmatch(manifest["id"]):
        raise ApplicationManifestError("invalid_application_id", "application id is invalid")
    if not isinstance(manifest.get("version"), str) or not _VERSION_RE.fullmatch(manifest["version"]):
        raise ApplicationManifestError("invalid_application_version", "application version is invalid")
    if not isinstance(manifest.get("name"), str) or not manifest["name"].strip():
        raise ApplicationManifestError("invalid_manifest", "application name is required")
    ui = manifest.get("ui")
    if not isinstance(ui, dict):
        raise ApplicationManifestError("missing_ui_entry", "application ui entry is required")
    _path(ui.get("entry"), "ui.entry")
    runtime = manifest.get("runtime")
    if runtime is not None:
        if not isinstance(runtime, dict) or runtime.get("kind") not in SUPPORTED_RUNTIME_KINDS:
            raise ApplicationManifestError("unsupported_runtime", "application runtime is unsupported")
        for platform in ("desktop", "web"):
            platform_kind = runtime.get(f"{platform}_kind")
            if platform_kind is not None and platform_kind not in SUPPORTED_RUNTIME_KINDS:
                raise ApplicationManifestError("unsupported_runtime", f"{platform} application runtime is unsupported")
        if runtime.get("entry") is not None:
            _path(runtime.get("entry"), "runtime.entry")
        if runtime.get("public_listener") is True or runtime.get("listen"):
            raise ApplicationManifestError("public_listener_denied", "applications cannot expose a listener")
    platforms = manifest.get("platforms")
    if not isinstance(platforms, dict) or set(platforms) != SUPPORTED_PLATFORMS or any(value not in {"supported", "unsupported"} for value in platforms.values()):
        raise ApplicationManifestError("invalid_platforms", "desktop, web and mobile platform declarations are required")
    _strings(manifest.get("capabilities"), "capabilities", CAPABILITIES)
    _strings(manifest.get("permissions"), "permissions", PERMISSIONS)
    storage = manifest.get("storage")
    if not isinstance(storage, dict) or storage.get("scope") != "application-instance" or storage.get("workspace") != "default":
        raise ApplicationManifestError("invalid_storage", "application storage must use the application-instance default workspace")
    return json.loads(json.dumps(manifest, ensure_ascii=False))


def runtime_kind_for_platform(manifest: dict[str, Any], platform: str) -> str:
    runtime = manifest.get("runtime") or {}
    return runtime.get(f"{platform}_kind") or runtime.get("kind", "managed-worker")


def _zip_member(name: str, info: zipfile.ZipInfo) -> None:
    path = PurePosixPath(name)
    if path.is_absolute() or ".." in path.parts or "" in path.parts or stat.S_ISLNK((info.external_attr >> 16) & 0xFFFF):
        raise ApplicationManifestError("unsafe_package_path", "application package contains an unsafe path")


def _require_zip_entry(names: set[str], entry: str, field: str) -> None:
    if entry not in names:
        raise ApplicationManifestError("missing_package_entry", f"{field} points to a missing package entry")


def validate_package(content: bytes, *, max_bytes: int = MAX_PACKAGE_BYTES) -> tuple[dict[str, Any], str]:
    if not isinstance(content, bytes) or len(content) > max_bytes:
        raise ApplicationManifestError("package_too_large", "application package exceeds maximum size")
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            infos = archive.infolist()
            for info in infos:
                _zip_member(info.filename, info)
            item = next((item for item in infos if item.filename in {"manifest.json", "application.json"}), None)
            if item is None:
                raise ApplicationManifestError("missing_manifest", "manifest.json is required")
            manifest = json.loads(archive.read(item).decode("utf-8"))
            validated = validate_manifest(manifest)
            names = {info.filename for info in infos}
            _require_zip_entry(names, validated["ui"]["entry"], "ui.entry")
            runtime = validated.get("runtime") or {}
            if runtime.get("entry"):
                _require_zip_entry(names, runtime["entry"], "runtime.entry")
    except ApplicationManifestError:
        raise
    except (OSError, ValueError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ApplicationManifestError("invalid_package", "application package is invalid") from exc
    return validated, hashlib.sha256(content).hexdigest()
