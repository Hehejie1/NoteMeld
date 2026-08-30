from __future__ import annotations

import hashlib
import json
import os
import re
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy.exc import IntegrityError

from app.applications.manifest import default_application_package_root, runtime_kind_for_platform, validate_manifest
from app.applications.models import Application, ApplicationArtifact, ApplicationData, ApplicationInstance, ApplicationJob, ApplicationJobEvent, ApplicationPermission, ApplicationRun, ApplicationSetting
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
        self.package_root = (package_root or default_application_package_root()).resolve()
        self.manifests = manifests if manifests is not None else self._discover()

    def _discover(self) -> dict[str, dict[str, Any]]:
        discovered: dict[str, dict[str, Any]] = {}
        if self.package_root.is_dir():
            for manifest_path in sorted(self.package_root.glob("*/manifest.json")):
                try:
                    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
                    validated = validate_manifest(manifest)
                    package_dir = manifest_path.parent
                    ui_entry = package_dir / validated["ui"]["entry"]
                    if not ui_entry.is_file():
                        continue
                    runtime_entry = (validated.get("runtime") or {}).get("entry")
                    if runtime_entry and not (package_dir / runtime_entry).is_file():
                        continue
                    discovered[validated["id"]] = validated
                except (OSError, ValueError, json.JSONDecodeError):
                    continue
        return discovered if discovered or self.package_root.exists() else self.BUILTIN

    def list(self) -> list[dict[str, Any]]:
        return [validate_manifest(item) for item in self.manifests.values()]

    def get(self, app_id: str) -> dict[str, Any] | None:
        item = self.manifests.get(app_id)
        return validate_manifest(item) if item else None

    def asset_path(self, app_id: str, asset_path: str) -> Path:
        manifest = self.get(app_id)
        if manifest is None:
            raise ApplicationError("application_not_found", "application not found", 404)
        relative = Path(asset_path)
        if relative.is_absolute() or ".." in relative.parts or not relative.parts:
            raise ApplicationError("invalid_application_asset", "application asset path is invalid", 400)
        package_dir = (self.package_root / app_id).resolve()
        target = (package_dir / relative).resolve()
        try:
            target.relative_to(package_dir)
        except ValueError as exc:
            raise ApplicationError("application_asset_denied", "application asset is outside the package", 403) from exc
        if not target.is_file():
            raise ApplicationError("application_asset_not_found", "application asset not found", 404)
        return target


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

    def external_read_roots(self, db) -> list[Path]:
        setting = db.query(ApplicationSetting).filter_by(app_id=None, key="external_read_roots").one_or_none()
        if not setting:
            return []
        try:
            values = json.loads(setting.value_json).get("roots", [])
            return [Path(value).expanduser().resolve() for value in values if isinstance(value, str) and Path(value).expanduser().is_absolute()]
        except (ValueError, TypeError, OSError):
            return []


class WikiCapabilityAdapter:
    capability = "wiki.read"

    def __init__(self, store: WikiStore | None = None):
        self.store = store or WikiStore(base_dir=note_output_dir() / "wiki")

    def read_graph(self) -> dict[str, Any]:
        return self.store.read_graph()

    def read_article(self, source_id: str) -> dict[str, Any] | None:
        return self.store.get_article(source_id)


class ApplicationService:
    _jobs = ThreadPoolExecutor(max_workers=4, thread_name_prefix="notemeld-app-job")
    _DATA_VALUE_LIMIT = 1024 * 1024
    _DATA_TOTAL_LIMIT = 10 * 1024 * 1024
    DEFAULT_PERMISSIONS = {"workspace.read", "workspace.write"}
    def __init__(self, session_factory=SessionLocal, registry=None, runtime=None, workspace=None, wiki=None):
        self.session_factory = session_factory
        self.registry = registry or ApplicationRegistry()
        self.runtime = runtime or ApplicationRuntime(package_root=self.registry.package_root)
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
        manifest = cls._manifest(row)
        return {
            "id": row.id,
            "version": row.version,
            "name": row.name,
            "enabled": bool(row.enabled),
            "status": row.status,
            "manifest": manifest,
            "protocol": manifest.get("protocol"),
            "description": manifest.get("description", ""),
            "ui": manifest.get("ui"),
            "runtime": manifest.get("runtime"),
            "platforms": manifest.get("platforms"),
            "capabilities": manifest.get("capabilities", []),
            "permissions": manifest.get("permissions", []),
            "manifest_sha256": row.manifest_sha256,
        }

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
            platform = os.getenv("NOTEMELD_PLATFORM", "desktop")
            runtime_kind = runtime_kind_for_platform(manifest, platform)
            row = ApplicationRun(run_id=run_id, app_id=app_id, instance_id=instance_id, request_id=request_id, payload_hash=payload_hash, runtime_kind=runtime_kind, status="queued")
            db.add(row)
            db.flush()
            try:
                result = self.runtime.start(manifest, RuntimeContext(app_id, instance_id, run_id, platform))
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
            if row.status in {"queued", "running", "waiting_user"}:
                app = db.get(Application, row.app_id)
                if app is not None and self.runtime.status(row.run_id) == "interrupted":
                    row.status = "interrupted"
                    row.error_code, row.error_message = "runtime_exited", "application process exited unexpectedly"
                    row.finished_at = datetime.now(timezone.utc)
                    db.commit()
            return self._run(row)
        finally:
            db.close()

    def recover_nonterminal_runs(self):
        """Converge runs from a previous Host process to a safe terminal state.

        Runtime adapters are Host-owned and their in-memory transport state is
        not durable across a backend restart.  Until a worker provider offers
        durable resume, an orphaned run must not remain deceptively active.
        """
        db = self.session_factory()
        try:
            rows = db.query(ApplicationRun).filter(ApplicationRun.status.in_(("queued", "running", "waiting_user"))).all()
            recovered = []
            now = datetime.now(timezone.utc)
            for row in rows:
                row.status = "interrupted"
                row.error_code, row.error_message = "host_restarted", "application Host restarted before the run reached a terminal state"
                row.finished_at = now
                recovered.append(row.run_id)
            if recovered:
                db.commit()
            return recovered
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

    def invoke_run(self, run_id, method, input_data):
        db = self.session_factory()
        try:
            row = db.get(ApplicationRun, run_id)
            if row is None:
                raise ApplicationError("run_not_found", "application run not found", 404)
            if row.status not in {"queued", "running", "waiting_user"}:
                raise ApplicationError("run_not_active", "application run is not active", 409)
            app = db.get(Application, row.app_id)
            if app is None:
                raise ApplicationError("application_not_found", "application not found", 404)
            platform = os.getenv("NOTEMELD_PLATFORM", "desktop")
            try:
                return self.runtime.invoke(
                    self._manifest(app),
                    RuntimeContext(row.app_id, row.instance_id, row.run_id, platform),
                    method,
                    input_data,
                )
            except ApplicationRuntimeError as exc:
                raise ApplicationError(exc.code, exc.message, 409) from exc
        finally:
            db.close()

    def start_runtime_job(self, run_id, method, input_data):
        db = self.session_factory()
        try:
            row, _, _ = self._check_app_context(db, run_id)
            job = ApplicationJob(job_id=uuid.uuid4().hex, app_id=row.app_id, instance_id=row.instance_id, run_id=row.run_id, method=f"application.runtime:{method}", input_json=json.dumps(input_data, ensure_ascii=False))
            db.add(job)
            db.add(ApplicationJobEvent(id=uuid.uuid4().hex, job_id=job.job_id, sequence=1, event_type="accepted", data_json=json.dumps({"status": "queued"})))
            db.commit()
            self._jobs.submit(self._execute_runtime_job, job.job_id)
            return {"mode": "async", "job_id": job.job_id, "status": "queued"}
        finally:
            db.close()

    def _execute_runtime_job(self, job_id):
        db = self.session_factory()
        try:
            job = db.get(ApplicationJob, job_id)
            if not job:
                return
            job.status = "running"
            db.add(ApplicationJobEvent(id=uuid.uuid4().hex, job_id=job_id, sequence=2, event_type="started", data_json="{}"))
            db.commit()
            result = self.invoke_run(job.run_id, job.method.split(":", 1)[1], json.loads(job.input_json))
            db.close()
            db = self.session_factory()
            job = db.get(ApplicationJob, job_id)
            job.status, job.result_json = "completed", json.dumps(result, ensure_ascii=False)
            db.add(ApplicationJobEvent(id=uuid.uuid4().hex, job_id=job_id, sequence=3, event_type="completed", data_json="{}"))
            db.commit()
        except (ApplicationError, ApplicationRuntimeError) as exc:
            db.rollback()
            job = db.get(ApplicationJob, job_id)
            if job:
                job.status, job.error_code, job.error_message = "failed", getattr(exc, "code", "job_failed"), getattr(exc, "message", str(exc))
                db.add(ApplicationJobEvent(id=uuid.uuid4().hex, job_id=job_id, sequence=3, event_type="failed", data_json=json.dumps({"code": job.error_code})))
                db.commit()
        finally:
            db.close()

    def _permission_granted(self, db, app_id, permission, manifest):
        requested = set(manifest.get("permissions", []))
        if permission not in requested and permission not in self.DEFAULT_PERMISSIONS:
            return False
        row = db.query(ApplicationPermission).filter_by(app_id=app_id, permission=permission).one_or_none()
        return bool(row.granted) if row is not None else permission in self.DEFAULT_PERMISSIONS

    def set_permissions(self, app_id, grants):
        if not isinstance(grants, dict):
            raise ApplicationError("invalid_permissions", "permissions must be an object")
        db = self.session_factory()
        try:
            app = db.get(Application, app_id)
            if app is None:
                raise ApplicationError("application_not_found", "application not found", 404)
            manifest = self._manifest(app)
            allowed = {"workspace.read", "workspace.write", "network.egress", "agent.run", "plugin.invoke"}
            if set(grants) - allowed:
                raise ApplicationError("invalid_permissions", "unsupported permission")
            requested = set(manifest.get("permissions", [])) | {"workspace.read", "workspace.write"}
            if set(grants) - requested:
                raise ApplicationError("permission_not_requested", "application did not request this permission", 403)
            for permission, granted in grants.items():
                if not isinstance(granted, bool):
                    raise ApplicationError("invalid_permissions", "permission values must be boolean")
                row = db.query(ApplicationPermission).filter_by(app_id=app_id, permission=permission).one_or_none()
                if row is None:
                    row = ApplicationPermission(id=uuid.uuid4().hex, app_id=app_id, permission=permission)
                    db.add(row)
                row.granted = int(granted)
            db.commit()
            return self.get_permissions(app_id)
        finally:
            db.close()

    def get_permissions(self, app_id):
        db = self.session_factory()
        try:
            app = db.get(Application, app_id)
            if app is None:
                raise ApplicationError("application_not_found", "application not found", 404)
            manifest = self._manifest(app)
            requested = set(manifest.get("permissions", [])) | {"workspace.read", "workspace.write"}
            stored = {item.permission: bool(item.granted) for item in db.query(ApplicationPermission).filter_by(app_id=app_id).all()}
            return {permission: {"requested": permission in set(manifest.get("permissions", [])), "granted": stored.get(permission, permission in self.DEFAULT_PERMISSIONS)} for permission in sorted(requested)}
        finally:
            db.close()

    def _check_app_context(self, db, run_id):
        row = db.get(ApplicationRun, run_id)
        if row is None:
            raise ApplicationError("run_not_found", "application run not found", 404)
        if row.status not in {"queued", "running", "waiting_user"}:
            raise ApplicationError("run_not_active", "application run is not active", 409)
        app = db.get(Application, row.app_id)
        if app is None:
            raise ApplicationError("application_not_found", "application not found", 404)
        if not app.enabled:
            raise ApplicationError("application_disabled", "application is disabled", 409)
        return row, app, self._manifest(app)

    @staticmethod
    def _validate_key(key):
        if not isinstance(key, str) or not key.strip() or len(key) > 200 or key.startswith(".") or ".." in key:
            raise ApplicationError("invalid_data_key", "data key is invalid")

    def _app_data(self, db, row, app, method, input_data):
        if method not in {"get", "put", "list", "delete"}:
            raise ApplicationError("capability_unavailable", "application data method is not available", 501)
        if method == "list":
            return {"keys": [item.key for item in db.query(ApplicationData).filter_by(app_id=app.id, instance_id=row.instance_id).order_by(ApplicationData.key).all()]}
        key = input_data.get("key") if isinstance(input_data, dict) else None
        self._validate_key(key)
        item = db.query(ApplicationData).filter_by(app_id=app.id, instance_id=row.instance_id, key=key).one_or_none()
        if method == "delete":
            if item is not None:
                db.delete(item)
                db.commit()
            return {"key": key, "deleted": item is not None}
        if method == "get":
            return {"key": key, "value": json.loads(item.value_json) if item else None, "exists": item is not None}
        if "value" not in input_data:
            raise ApplicationError("invalid_invocation", "value is required")
        encoded = json.dumps(input_data["value"], ensure_ascii=False, separators=(",", ":"))
        if len(encoded.encode()) > self._DATA_VALUE_LIMIT:
            raise ApplicationError("data_quota_exceeded", "application data value exceeds the limit", 413)
        total = sum(len(item.value_json.encode()) for item in db.query(ApplicationData).filter_by(app_id=app.id, instance_id=row.instance_id).all())
        if item:
            total -= len(item.value_json.encode())
        if total + len(encoded.encode()) > self._DATA_TOTAL_LIMIT:
            raise ApplicationError("data_quota_exceeded", "application data quota exceeded", 413)
        if item is None:
            item = ApplicationData(id=uuid.uuid4().hex, app_id=app.id, instance_id=row.instance_id, key=key)
            db.add(item)
        item.value_json = encoded
        db.commit()
        return {"key": key, "value": input_data["value"], "exists": True}

    def _artifact(self, db, row, method, input_data):
        if method == "create":
            if not isinstance(input_data, dict) or not isinstance(input_data.get("kind"), str) or not input_data["kind"].strip():
                raise ApplicationError("invalid_invocation", "artifact kind is required")
            data = input_data.get("data")
            encoded = json.dumps(data, ensure_ascii=False, separators=(",", ":"))
            if len(encoded.encode()) > 16 * 1024 * 1024:
                raise ApplicationError("artifact_too_large", "artifact exceeds the limit", 413)
            artifact = ApplicationArtifact(artifact_id=uuid.uuid4().hex, app_id=row.app_id, instance_id=row.instance_id, run_id=row.run_id, kind=input_data["kind"], summary=str(input_data.get("summary", "")), data_json=encoded)
            db.add(artifact)
            db.commit()
            return {"artifact_id": artifact.artifact_id, "kind": artifact.kind, "summary": artifact.summary, "download_url": f"/api/applications/artifacts/{artifact.artifact_id}/download"}
        if method == "read":
            artifact = db.get(ApplicationArtifact, input_data.get("artifact_id") if isinstance(input_data, dict) else None)
            if artifact is None or artifact.app_id != row.app_id or artifact.instance_id != row.instance_id:
                raise ApplicationError("artifact_not_found", "application artifact not found", 404)
            return {"artifact_id": artifact.artifact_id, "kind": artifact.kind, "summary": artifact.summary, "data": json.loads(artifact.data_json)}
        raise ApplicationError("capability_unavailable", "artifact method is not available", 501)

    def _agent_run(self, row, input_data):
        prompt = input_data.get("input") if isinstance(input_data, dict) else None
        if not isinstance(prompt, str) or not prompt.strip():
            raise ApplicationError("invalid_invocation", "agent input is required")
        try:
            from app.agent_host.entry import get_agent_host_entry
            from app.routers.agent import _executor
            entry = get_agent_host_entry()
            session_id = f"application:{row.app_id}:{row.instance_id}"
            entry.create_session(session_id=session_id, title=f"Application {row.app_id}")
            turn = entry.create_turn(session_id, model_name=input_data.get("model"), idempotency_key=input_data.get("idempotency_key"))
            _executor.start(session_id=session_id, turn_id=turn["turn_id"], content=prompt, model_name=input_data.get("model"))
            return {"turn_id": turn["turn_id"], "session_id": session_id, "status": "queued"}
        except ApplicationError:
            raise
        except Exception as exc:
            raise ApplicationError("agent_unavailable", "NoteMeld Agent could not accept the application request", 503) from exc

    def download_artifact(self, artifact_id):
        db = self.session_factory()
        try:
            artifact = db.get(ApplicationArtifact, artifact_id)
            if artifact is None:
                raise ApplicationError("artifact_not_found", "application artifact not found", 404)
            return {"artifact_id": artifact.artifact_id, "kind": artifact.kind, "summary": artifact.summary, "data": json.loads(artifact.data_json)}
        finally:
            db.close()

    def _workspace_file(self, db, row, method, input_data):
        if not isinstance(input_data, dict) or not isinstance(input_data.get("path"), str):
            raise ApplicationError("invalid_invocation", "path is required")
        if method == "read_external":
            external = Path(input_data["path"]).expanduser().resolve()
            if not external.is_file() or not any(external == root or root in external.parents for root in self.workspace.external_read_roots(db)):
                raise ApplicationError("external_file_denied", "external file is not authorized", 403)
            if external.stat().st_size > 16 * 1024 * 1024:
                raise ApplicationError("file_too_large", "external file exceeds the limit", 413)
            return {"name": external.name, "content": external.read_text(encoding="utf-8")}
        path = Path(input_data["path"])
        if path.is_absolute() or ".." in path.parts or not path.parts or "" in path.parts:
            raise ApplicationError("invalid_workspace_path", "workspace path must be relative and safe")
        target = (self.workspace.instance_path(db, row.app_id, row.instance_id) / path).resolve()
        root = self.workspace.instance_path(db, row.app_id, row.instance_id).resolve()
        try:
            target.relative_to(root)
        except ValueError as exc:
            raise ApplicationError("workspace_access_denied", "workspace path is outside the application workspace", 403) from exc
        if method == "list":
            if not target.is_dir():
                raise ApplicationError("workspace_file_not_found", "workspace directory not found", 404)
            return {"entries": sorted(item.relative_to(root).as_posix() for item in target.iterdir())}
        if method == "read":
            if not target.is_file():
                raise ApplicationError("workspace_file_not_found", "workspace file not found", 404)
            if target.stat().st_size > 16 * 1024 * 1024:
                raise ApplicationError("file_too_large", "workspace file exceeds the limit", 413)
            return {"path": path.as_posix(), "content": target.read_text(encoding="utf-8")}
        if method == "write":
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(str(input_data.get("content", "")), encoding="utf-8")
            return {"path": path.as_posix(), "bytes": target.stat().st_size}
        if method == "delete":
            if not target.is_file():
                raise ApplicationError("workspace_file_not_found", "workspace file not found", 404)
            target.unlink()
            return {"path": path.as_posix(), "deleted": True}
        raise ApplicationError("capability_unavailable", "workspace file method is not available", 501)

    def invoke_capability(self, run_id, capability, method, input_data, mode="sync"):
        db = self.session_factory()
        try:
            row, app, manifest = self._check_app_context(db, run_id)
            if capability not in manifest.get("capabilities", []):
                aliases = {"app.data": {"app.data.get", "app.data.put", "app.data.list", "app.data.delete"}, "workspace.file": {"workspace.file.read", "workspace.file.write", "workspace.file.list", "workspace.file.delete", "workspace.file.read_external"}, "artifact": {"artifact.create", "artifact.read"}}
                if not aliases.get(capability, set()).intersection(manifest.get("capabilities", [])):
                    raise ApplicationError("capability_denied", "application capability is not declared", 403)
            capability_name = "app.data" if capability.startswith("app.data") else "workspace.file" if capability.startswith("workspace.file") else "artifact" if capability.startswith("artifact") else "agent" if capability.startswith("agent") else capability
            required = {"workspace.file.read": "workspace.read", "workspace.file.read_external": "workspace.read", "workspace.file.list": "workspace.read", "workspace.file.write": "workspace.write", "workspace.file.delete": "workspace.write", "agent.run": "agent.run"}.get(f"{capability_name}.{method}")
            if required and not self._permission_granted(db, app.id, required, manifest):
                raise ApplicationError("permission_denied", f"permission required: {required}", 403)
            if mode not in {"sync", "async"}:
                raise ApplicationError("invalid_invocation", "mode must be sync or async")
            if mode == "async":
                job = ApplicationJob(job_id=uuid.uuid4().hex, app_id=row.app_id, instance_id=row.instance_id, run_id=row.run_id, method=f"{capability}:{method}", input_json=json.dumps(input_data, ensure_ascii=False))
                db.add(job)
                db.add(ApplicationJobEvent(id=uuid.uuid4().hex, job_id=job.job_id, sequence=1, event_type="accepted", data_json=json.dumps({"status": "queued"})))
                db.commit()
                self._jobs.submit(self._execute_capability_job, job.job_id)
                return {"mode": "async", "job_id": job.job_id, "status": "queued"}
            if capability_name == "wiki.read":
                if method == "graph":
                    return self.wiki.read_graph()
                if method == "article":
                    source_id = input_data.get("source_id") if isinstance(input_data, dict) else None
                    if not isinstance(source_id, str) or not source_id:
                        raise ApplicationError("invalid_invocation", "source_id is required")
                    article = self.wiki.read_article(source_id)
                    if article is None:
                        raise ApplicationError("wiki_article_not_found", "Wiki article not found", 404)
                    return article
            if capability_name == "app.data":
                return self._app_data(db, row, app, method, input_data)
            if capability_name == "workspace.file":
                return self._workspace_file(db, row, method, input_data)
            if capability_name == "artifact":
                return self._artifact(db, row, method, input_data)
            if capability_name == "agent":
                if method != "run":
                    raise ApplicationError("capability_unavailable", "agent method is not available", 501)
                return self._agent_run(row, input_data)
            raise ApplicationError("capability_unavailable", "application capability is not available", 501)
        finally:
            db.close()

    def _execute_capability_job(self, job_id):
        db = self.session_factory()
        try:
            job = db.get(ApplicationJob, job_id)
            if job is None:
                return
            job.status = "running"
            job.updated_at = datetime.now(timezone.utc)
            db.add(ApplicationJobEvent(id=uuid.uuid4().hex, job_id=job_id, sequence=2, event_type="started", data_json="{}"))
            db.commit()
            capability, method = job.method.split(":", 1)
            result = self.invoke_capability(job.run_id, capability, method, json.loads(job.input_json), mode="sync")
            db.close()
            db = self.session_factory()
            job = db.get(ApplicationJob, job_id)
            job.status, job.result_json = "completed", json.dumps(result, ensure_ascii=False)
            db.add(ApplicationJobEvent(id=uuid.uuid4().hex, job_id=job_id, sequence=3, event_type="completed", data_json=json.dumps({"status": "completed"})))
            db.commit()
        except ApplicationError as exc:
            db.rollback()
            job = db.get(ApplicationJob, job_id)
            if job:
                job.status, job.error_code, job.error_message = "failed", exc.code, exc.message
                db.add(ApplicationJobEvent(id=uuid.uuid4().hex, job_id=job_id, sequence=3, event_type="failed", data_json=json.dumps({"code": exc.code}, ensure_ascii=False)))
                db.commit()
        finally:
            db.close()

    def get_job(self, job_id):
        db = self.session_factory()
        try:
            job = db.get(ApplicationJob, job_id)
            if job is None:
                raise ApplicationError("job_not_found", "application job not found", 404)
            return {"job_id": job.job_id, "run_id": job.run_id, "status": job.status, "result": json.loads(job.result_json) if job.result_json else None, "error": {"code": job.error_code, "message": job.error_message} if job.error_code else None}
        finally:
            db.close()

    def run_logs(self, run_id):
        db = self.session_factory()
        try:
            if db.get(ApplicationRun, run_id) is None:
                raise ApplicationError("run_not_found", "application run not found", 404)
            return {"run_id": run_id, "lines": self.runtime.logs(run_id)}
        finally:
            db.close()

    def job_events(self, job_id, after_sequence=0):
        db = self.session_factory()
        try:
            if db.get(ApplicationJob, job_id) is None:
                raise ApplicationError("job_not_found", "application job not found", 404)
            return [{"job_id": event.job_id, "sequence": event.sequence, "type": event.event_type, "data": json.loads(event.data_json)} for event in db.query(ApplicationJobEvent).filter(ApplicationJobEvent.job_id == job_id, ApplicationJobEvent.sequence > after_sequence).order_by(ApplicationJobEvent.sequence).all()]
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
                "external_read_roots": [str(path) for path in self.workspace.external_read_roots(db)],
            }
        finally:
            db.close()

    def set_external_read_roots(self, roots):
        if not isinstance(roots, list) or not all(isinstance(root, str) and Path(root).expanduser().is_absolute() and ".." not in Path(root).parts for root in roots):
            raise ApplicationError("invalid_external_roots", "external read roots must be absolute safe paths")
        db = self.session_factory()
        try:
            setting = db.query(ApplicationSetting).filter_by(app_id=None, key="external_read_roots").one_or_none()
            if setting is None:
                setting = ApplicationSetting(id="global:external_read_roots", app_id=None, key="external_read_roots")
                db.add(setting)
            setting.value_json = json.dumps({"roots": [str(Path(root).expanduser().resolve()) for root in roots]}, ensure_ascii=False)
            db.commit()
            return {"external_read_roots": [str(path) for path in self.workspace.external_read_roots(db)]}
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
