from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.applications.manifest import validate_manifest
from app.applications.models import Application, ApplicationInstance, ApplicationRun, ApplicationSetting
from app.applications.runtime import ApplicationRuntime, ApplicationRuntimeError, RuntimeContext
from app.db.engine import SessionLocal
from app.services.wiki_store import WikiStore
from app.utils.storage_paths import application_workspaces_root, note_output_dir


class ApplicationError(RuntimeError):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


class ApplicationRegistry:
    BUILTIN = {
        "wiki": {
            "protocol": "notemeld.application.v1", "id": "wiki", "version": "1.0.0", "name": "Wiki",
            "ui": {"entry": "ui/index.html"}, "runtime": {"kind": "managed-worker", "entry": "backend/worker"},
            "platforms": {"desktop": "supported", "web": "supported", "mobile": "unsupported"},
            "capabilities": ["wiki.read"], "permissions": [],
            "storage": {"scope": "application-instance", "workspace": "default"},
        }
    }

    def __init__(self, manifests: dict[str, dict[str, Any]] | None = None, package_root: Path | None = None):
        self.package_root = package_root or Path(__file__).resolve().parents[3] / "applications"
        self.manifests = manifests if manifests is not None else self._discover()

    def _discover(self) -> dict[str, dict[str, Any]]:
        discovered: dict[str, dict[str, Any]] = {}
        if self.package_root.is_dir():
            for manifest_path in sorted(self.package_root.glob("*/manifest.json")):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    validated = validate_manifest(manifest)
                    discovered[validated["id"]] = validated
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
        return discovered or self.BUILTIN

    def list(self) -> list[dict[str, Any]]:
        return [validate_manifest(item) for item in self.manifests.values()]

    def get(self, app_id: str) -> dict[str, Any] | None:
        item = self.manifests.get(app_id)
        return validate_manifest(item) if item else None


class WorkspaceManager:
    _SAFE = re.compile(r"^[A-Za-z0-9._-]+$")

    def __init__(self, root_provider=application_workspaces_root):
        self.root_provider = root_provider

    def configured_root(self, db) -> Path:
        setting = db.query(ApplicationSetting).filter_by(app_id=None, key="default_workspace_root").one_or_none()
        if setting:
            try:
                value = json.loads(setting.value_json).get("path")
                if isinstance(value, str) and value.strip():
                    return Path(value).expanduser().resolve()
            except (OSError, ValueError, TypeError):
                pass
        return Path(self.root_provider()).resolve()

    def set_root(self, db, root: str) -> dict[str, Any]:
        if not isinstance(root, str) or not root.strip():
            raise ApplicationError("invalid_workspace_root", "workspace root is required")
        path = Path(root).expanduser()
        if not path.is_absolute() or ".." in path.parts:
            raise ApplicationError("invalid_workspace_root", "workspace root must be an absolute path")
        path.resolve().mkdir(parents=True, exist_ok=True)
        setting = db.query(ApplicationSetting).filter_by(app_id=None, key="default_workspace_root").one_or_none()
        if setting is None:
            setting = ApplicationSetting(id="global:default_workspace_root", app_id=None, key="default_workspace_root")
            db.add(setting)
        setting.value_json = json.dumps({"path": str(path.resolve())}, sort_keys=True)
        return {"workspace_ref": "workspace://default", "configured": True}

    def instance_path(self, db, app_id: str, instance_id: str) -> Path:
        if not self._SAFE.fullmatch(app_id) or not self._SAFE.fullmatch(instance_id):
            raise ApplicationError("invalid_workspace_reference", "workspace reference is invalid")
        root = self.configured_root(db)
        target = (root / app_id / instance_id).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ApplicationError("workspace_access_denied", "workspace reference is outside the application root") from exc
        target.mkdir(parents=True, exist_ok=True)
        return target


class WikiCapabilityAdapter:
    capability = "wiki.read"

    def __init__(self, store: WikiStore | None = None):
        self.store = store or WikiStore(base_dir=note_output_dir() / "wiki")

    def read_graph(self) -> dict[str, Any]:
        return self.store.read_graph()

    def read_article(self, source_id: str) -> dict[str, Any] | None:
        return self.store.get_article(source_id)


class ApplicationService:
    def __init__(self, session_factory=SessionLocal, registry=None, runtime=None, workspace=None, wiki=None):
        self.session_factory = session_factory
        self.registry = registry or ApplicationRegistry()
        self.runtime = runtime or ApplicationRuntime()
        self.workspace = workspace or WorkspaceManager()
        self.wiki = wiki or WikiCapabilityAdapter()

    def sync_registry(self) -> None:
        db = self.session_factory()
        try:
            for manifest in self.registry.list():
                digest = hashlib.sha256(json.dumps(manifest, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
                row = db.get(Application, manifest["id"])
                if row is None:
                    db.add(Application(id=manifest["id"], version=manifest["version"], name=manifest["name"], manifest_json=json.dumps(manifest, sort_keys=True, ensure_ascii=False), manifest_sha256=digest, enabled=1, status="installed"))
                else:
                    row.version, row.name = manifest["version"], manifest["name"]
                    row.manifest_json, row.manifest_sha256 = json.dumps(manifest, sort_keys=True, ensure_ascii=False), digest
            db.commit()
        finally:
            db.close()

    @staticmethod
    def _manifest(row):
        try:
            return validate_manifest(json.loads(row.manifest_json))
        except (ValueError, json.JSONDecodeError) as exc:
            raise ApplicationError("invalid_manifest", "stored application manifest is invalid", 500) from exc

    @classmethod
    def _app(cls, row):
        return {"id": row.id, "version": row.version, "name": row.name, "enabled": bool(row.enabled), "status": row.status, "manifest": cls._manifest(row), "manifest_sha256": row.manifest_sha256}

    @staticmethod
    def _instance(row):
        return {"id": row.id, "app_id": row.app_id, "title": row.title, "workspace_ref": row.workspace_ref, "status": row.status}

    @staticmethod
    def _run(row):
        return {"run_id": row.run_id, "app_id": row.app_id, "instance_id": row.instance_id, "request_id": row.request_id, "runtime_kind": row.runtime_kind, "status": row.status, "cancel_requested": bool(row.cancel_requested), "error": {"code": row.error_code, "message": row.error_message} if row.error_code else None}

    def list(self):
        db = self.session_factory()
        try:
            return [self._app(row) for row in db.query(Application).order_by(Application.id).all()]
        finally:
            db.close()

    def get(self, app_id):
        db = self.session_factory()
        try:
            row = db.get(Application, app_id)
            if row is None:
                raise ApplicationError("application_not_found", "application not found", 404)
            return self._app(row)
        finally:
            db.close()

    def set_enabled(self, app_id, enabled):
        db = self.session_factory()
        try:
            row = db.get(Application, app_id)
            if row is None:
                raise ApplicationError("application_not_found", "application not found", 404)
            row.enabled, row.status = int(enabled), "installed" if enabled else "disabled"
            db.commit()
            return self._app(row)
        finally:
            db.close()

    def create_instance(self, app_id, title="", instance_id=None):
        db = self.session_factory()
        try:
            app = db.get(Application, app_id)
            if app is None:
                raise ApplicationError("application_not_found", "application not found", 404)
            if not app.enabled:
                raise ApplicationError("application_disabled", "application is disabled", 409)
            instance_id = instance_id or uuid.uuid4().hex
            self.workspace.instance_path(db, app_id, instance_id)
            row = ApplicationInstance(id=instance_id, app_id=app_id, title=title or app.name, workspace_ref=f"workspace://applications/{app_id}/instances/{instance_id}")
            db.add(row)
            db.commit()
            return self._instance(row)
        except IntegrityError as exc:
            db.rollback()
            raise ApplicationError("instance_conflict", "application instance already exists", 409) from exc
        finally:
            db.close()

    def instances(self, app_id):
        db = self.session_factory()
        try:
            if db.get(Application, app_id) is None:
                raise ApplicationError("application_not_found", "application not found", 404)
            return [self._instance(row) for row in db.query(ApplicationInstance).filter_by(app_id=app_id).order_by(ApplicationInstance.created_at).all()]
        finally:
            db.close()

    def start_run(self, app_id, instance_id, payload):
        db = self.session_factory()
        try:
            app, instance = db.get(Application, app_id), db.get(ApplicationInstance, instance_id)
            if app is None:
                raise ApplicationError("application_not_found", "application not found", 404)
            if instance is None or instance.app_id != app_id:
                raise ApplicationError("instance_not_found", "application instance not found", 404)
            if not app.enabled:
                raise ApplicationError("application_disabled", "application is disabled", 409)
            request_id = payload.get("request_id")
            payload_hash = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            if request_id:
                existing = db.query(ApplicationRun).filter_by(app_id=app_id, instance_id=instance_id, request_id=request_id).one_or_none()
                if existing:
                    if existing.payload_hash != payload_hash:
                        raise ApplicationError("idempotency_conflict", "request id was used with a different payload", 409)
                    return self._run(existing)
            run_id = uuid.uuid4().hex
            manifest = self._manifest(app)
            runtime_kind = (manifest.get("runtime") or {}).get("kind", "managed-worker")
            row = ApplicationRun(run_id=run_id, app_id=app_id, instance_id=instance_id, request_id=request_id, payload_hash=payload_hash, runtime_kind=runtime_kind, status="queued")
            db.add(row)
            db.flush()
            try:
                result = self.runtime.start(manifest, RuntimeContext(app_id, instance_id, run_id, os.getenv("NOTEMELD_PLATFORM", "desktop")))
            except ApplicationRuntimeError as exc:
                row.status = "needs_attention" if exc.code == "public_listener_denied" else "failed"
                row.error_code, row.error_message = exc.code, exc.message
                db.commit()
                raise ApplicationError(exc.code, exc.message, 409)
            row.status = result.get("status", "running")
            db.commit()
            return self._run(row)
        finally:
            db.close()

    def get_run(self, run_id):
        db = self.session_factory()
        try:
            row = db.get(ApplicationRun, run_id)
            if row is None:
                raise ApplicationError("run_not_found", "application run not found", 404)
            return self._run(row)
        finally:
            db.close()

    def cancel_run(self, run_id):
        db = self.session_factory()
        try:
            row = db.get(ApplicationRun, run_id)
            if row is None:
                raise ApplicationError("run_not_found", "application run not found", 404)
            if row.status in {"cancelled", "completed", "failed", "interrupted"}:
                return self._run(row)
            self.runtime.cancel(self._manifest(db.get(Application, row.app_id)), RuntimeContext(row.app_id, row.instance_id, row.run_id))
            row.cancel_requested, row.status = 1, "cancelled"
            row.finished_at = datetime.now(timezone.utc)
            db.commit()
            return self._run(row)
        finally:
            db.close()

    def workspace_config(self):
        db = self.session_factory()
        try:
            configured = db.query(ApplicationSetting).filter_by(app_id=None, key="default_workspace_root").one_or_none() is not None
            return {
                "workspace_ref": "workspace://default",
                "configured": configured,
                "root": str(self.workspace.configured_root(db)),
            }
        finally:
            db.close()

    def set_workspace_config(self, root):
        db = self.session_factory()
        try:
            result = self.workspace.set_root(db, root)
            db.commit()
            return {**result, "root": str(self.workspace.configured_root(db))}
        except Exception:
            db.rollback()
            raise
        finally:
            db.close()

    def wiki_graph(self, app_id):
        self._require_capability(app_id, "wiki.read")
        return self.wiki.read_graph()

    def wiki_article(self, app_id, source_id):
        self._require_capability(app_id, "wiki.read")
        article = self.wiki.read_article(source_id)
        if article is None:
            raise ApplicationError("wiki_article_not_found", "Wiki article not found", 404)
        return article

    def _require_capability(self, app_id, capability):
        app = self.get(app_id)
        if not app["enabled"]:
            raise ApplicationError("application_disabled", "application is disabled", 409)
        if capability not in app["manifest"].get("capabilities", []):
            raise ApplicationError("capability_denied", "application capability is not granted", 403)
