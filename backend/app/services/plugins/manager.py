from __future__ import annotations

import json
import os
import subprocess
import uuid
from typing import Any

from sqlalchemy import desc

from app.db.engine import SessionLocal
from app.db.models.plugin import PluginAuditEvent, PluginInstallation, PluginVersion
from app.services.plugins.release_resolver import ReleaseResolver
from app.services.plugins.verifier import PluginVerificationError, promote_staged, stage_and_verify
from app.utils.storage_paths import plugin_active_pointer, plugins_root_dir


PERMISSION_AUTHORITY = {"note.read", "note.write", "network", "workspace.read", "workspace.write"}


def authorize_permissions(requested: set[str], granted: set[str]) -> None:
    if not requested.issubset(PERMISSION_AUTHORITY) or not requested.issubset(granted):
        raise PluginVerificationError("requested permissions are not granted by the user")


class PluginManager:
    def __init__(self, resolver: ReleaseResolver | None = None):
        self.resolver = resolver or ReleaseResolver()

    @staticmethod
    def _audit(db, plugin_id: str, action: str, *, version: str | None = None, detail: dict | None = None):
        db.add(PluginAuditEvent(id=uuid.uuid4().hex, plugin_id=plugin_id, action=action, version=version,
                                detail_json=json.dumps(detail or {}, sort_keys=True)))

    @staticmethod
    def _pointer(plugin_id: str, version: str | None) -> None:
        pointer = plugin_active_pointer(plugin_id)
        pointer.parent.mkdir(parents=True, exist_ok=True)
        temp = pointer.with_name(f".{pointer.name}.{uuid.uuid4().hex}.tmp")
        temp.write_text(version or "", encoding="utf-8")
        os.replace(temp, pointer)

    def install(self, source_url: str, *, expected_sha256: str | None = None, plugin_id: str | None = None,
                version: str | None = None, granted_permissions: list[str] | None = None) -> dict[str, Any]:
        artifact = self.resolver.resolve(source_url, plugin_id=plugin_id or "", version=version or "")
        staging, manifest, digest = stage_and_verify(artifact.content, expected_sha256=expected_sha256,
                                                     expected_plugin_id=plugin_id, expected_version=version)
        requested = set(manifest.get("requested_permissions", []))
        granted = set(granted_permissions or [])
        authorize_permissions(requested, granted)
        pid, ver = manifest["id"], manifest["version"]
        db = SessionLocal()
        try:
            if db.get(PluginVersion, f"{pid}:{ver}"):
                raise PluginVerificationError("plugin version already registered")
            target = promote_staged(staging, pid, ver, plugins_root_dir() / "versions")
            db.add(PluginVersion(id=f"{pid}:{ver}", plugin_id=pid, version=ver, sha256=digest, path=str(target),
                                 license=manifest["license"], sdk_version=manifest["sdk_version"], manifest_json=json.dumps(manifest, sort_keys=True)))
            installation = db.get(PluginInstallation, pid)
            first_install = installation is None or not installation.active_version
            if installation is None:
                installation = PluginInstallation(plugin_id=pid, requested_permissions_json=json.dumps(sorted(requested)),
                                                  granted_permissions_json=json.dumps(sorted(granted)), manifest_json=json.dumps(manifest, sort_keys=True))
                db.add(installation)
            else:
                installation.requested_permissions_json = json.dumps(sorted(requested))
                installation.granted_permissions_json = json.dumps(sorted(granted))
                installation.manifest_json = json.dumps(manifest, sort_keys=True)
            if first_install:
                self._pointer(pid, ver)
                installation.active_version = ver
            self._audit(db, pid, "installed", version=ver, detail={"sha256": digest, "provider": artifact.provider})
            db.commit()
            return self.serialize_installation(db.get(PluginInstallation, pid), db)
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def set_enabled(self, plugin_id: str, enabled: bool) -> dict[str, Any]:
        db = SessionLocal()
        try:
            installation = db.get(PluginInstallation, plugin_id)
            if not installation or not installation.active_version:
                raise PluginVerificationError("plugin has no active version")
            try:
                if enabled:
                    self._start_runtime(installation, db)
                else:
                    self._stop_runtime(installation, db)
            except PluginVerificationError:
                if installation.runtime_status == "crashed":
                    self._audit(db, plugin_id, "crashed", version=installation.active_version)
                    db.commit()
                raise
            installation.enabled = int(enabled)
            installation.runtime_status = "running" if enabled else "disabled"
            self._audit(db, plugin_id, "enabled" if enabled else "disabled", version=installation.active_version)
            db.commit()
            return self.serialize_installation(installation, db)
        finally:
            db.close()

    def activate(self, plugin_id: str, version: str) -> dict[str, Any]:
        db = SessionLocal()
        try:
            installation = db.get(PluginInstallation, plugin_id)
            target = db.get(PluginVersion, f"{plugin_id}:{version}")
            if not installation or not target:
                raise PluginVerificationError("plugin version is not installed")
            if installation.enabled:
                self._stop_runtime(installation, db)
            self._pointer(plugin_id, version)
            installation.active_version = version
            installation.runtime_status = "disabled"
            installation.runtime_pid = None
            self._audit(db, plugin_id, "activated", version=version)
            db.commit()
            return self.serialize_installation(installation, db)
        finally:
            db.close()

    def rollback(self, plugin_id: str, version: str) -> dict[str, Any]:
        result = self.activate(plugin_id, version)
        db = SessionLocal()
        try:
            self._audit(db, plugin_id, "rolled_back", version=version)
            db.commit()
        finally:
            db.close()
        return result

    def list(self) -> list[dict[str, Any]]:
        db = SessionLocal()
        try:
            return [self.serialize_installation(item, db) for item in db.query(PluginInstallation).all()]
        finally:
            db.close()

    def audit(self, plugin_id: str) -> list[dict[str, Any]]:
        db = SessionLocal()
        try:
            return [{"action": row.action, "actor": row.actor, "version": row.version,
                     "detail": json.loads(row.detail_json), "created_at": row.created_at.isoformat() if row.created_at else None}
                    for row in db.query(PluginAuditEvent).filter_by(plugin_id=plugin_id).order_by(desc(PluginAuditEvent.created_at)).all()]
        finally:
            db.close()

    @staticmethod
    def serialize_installation(item: PluginInstallation, db) -> dict[str, Any]:
        versions = db.query(PluginVersion).filter_by(plugin_id=item.plugin_id).order_by(PluginVersion.installed_at).all()
        return {"plugin_id": item.plugin_id, "active_version": item.active_version, "enabled": bool(item.enabled),
                "runtime_status": item.runtime_status, "requested_permissions": json.loads(item.requested_permissions_json),
                "granted_permissions": json.loads(item.granted_permissions_json),
                "versions": [{"version": v.version, "sha256": v.sha256, "license": v.license, "sdk_version": v.sdk_version} for v in versions]}

    @staticmethod
    def _start_runtime(installation: PluginInstallation, db) -> None:
        manifest = json.loads(installation.manifest_json)
        runtime_kind = str((manifest.get("runtime") or {}).get("kind") or "")
        transport_kind = str((manifest.get("transport") or {}).get("kind") or "")
        if runtime_kind in {"host-port", "process-jsonl", "stdin-stdout-jsonl"} or transport_kind in {"host-port", "process-jsonl", "stdin-stdout-jsonl"}:
            # These runtimes are started per invocation or owned by the Host.
            # There is no persistent process for the control plane to supervise.
            installation.runtime_status = "running"
            installation.runtime_pid = None
            return
        command = (manifest.get("runtime") or {}).get("command")
        if not isinstance(command, list) or not command or not all(isinstance(item, str) and item for item in command):
            raise PluginVerificationError("plugin runtime command is missing")
        version = db.get(PluginVersion, f"{installation.plugin_id}:{installation.active_version}")
        process = subprocess.Popen(command, cwd=version.path, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                   stderr=subprocess.DEVNULL, close_fds=True)
        if process.poll() is not None:
            installation.runtime_status = "crashed"
            installation.runtime_pid = None
            raise PluginVerificationError("plugin runtime crashed during startup")
        installation.runtime_pid = process.pid

    @staticmethod
    def _stop_runtime(installation: PluginInstallation, _db) -> None:
        if installation.runtime_pid:
            try:
                os.kill(installation.runtime_pid, 15)
            except ProcessLookupError:
                pass
        installation.runtime_pid = None
