import json
import io
import pathlib
import os
import sys
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.applications.models import Application, ApplicationArtifact, ApplicationData, ApplicationInstance, ApplicationJob, ApplicationJobEvent, ApplicationMigration, ApplicationPermission, ApplicationRun, ApplicationSetting
from app.applications.runtime import ApplicationRuntime, ApplicationRuntimeError, RuntimeContext
from app.applications.service import ApplicationRegistry, ApplicationService, WikiCapabilityAdapter
from app.db.application_migrations import ensure_application_migration_registry
from app.db.engine import Base


VALID_MANIFEST = {
    "protocol": "notemeld.application.v1",
    "id": "example.app",
    "version": "1.0.0",
    "name": "Example",
    "ui": {"entry": "ui/index.html"},
    "runtime": {"kind": "managed-worker", "entry": "backend/worker"},
    "platforms": {"desktop": "supported", "web": "supported", "mobile": "unsupported"},
    "capabilities": ["wiki.read"],
    "permissions": [],
    "storage": {"scope": "application-instance", "workspace": "default"},
}


class FakeWiki:
    def read_graph(self):
        return {"nodes": [{"id": "n1"}], "edges": [], "clusters": []}

    def get_article(self, source_id):
        return {"id": source_id, "title": "Article"} if source_id == "source-1" else None


@pytest.fixture
def service(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'applications.db'}")
    tables = [Application.__table__, ApplicationInstance.__table__, ApplicationRun.__table__, ApplicationArtifact.__table__, ApplicationSetting.__table__, ApplicationData.__table__, ApplicationPermission.__table__, ApplicationJob.__table__, ApplicationJobEvent.__table__, ApplicationMigration.__table__]
    Base.metadata.create_all(engine, tables=tables)
    factory = sessionmaker(bind=engine)
    package_root = ROOT.parent.parent / "notemeld-applications" / "apps"
    svc = ApplicationService(
        session_factory=factory,
        registry=ApplicationRegistry(package_root=package_root),
        wiki=WikiCapabilityAdapter(store=FakeWiki()),
    )
    svc.sync_registry()
    return svc, engine


def test_builtin_registry_and_manifest_validation(service):
    svc, _ = service
    app = svc.get("wiki")
    assert app["manifest"]["protocol"] == "notemeld.application.v1"
    assert "runtime" not in app["manifest"]
    assert svc.list()[0]["id"] == "wiki"


def test_builtin_registry_discovers_manifest_from_application_directory(service):
    svc, _ = service
    assert svc.registry.package_root.name == "apps"
    assert svc.registry.get("wiki")["ui"]["entry"] == "ui/index.html"


def test_application_package_requires_declared_ui_and_runtime_entries():
    from app.applications.manifest import ApplicationManifestError, validate_package

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("manifest.json", json.dumps(VALID_MANIFEST))
        package.writestr("ui/index.html", "<!doctype html>")
    with pytest.raises(ApplicationManifestError, match="runtime.entry"):
        validate_package(archive.getvalue())

    complete = io.BytesIO()
    with zipfile.ZipFile(complete, "w") as package:
        package.writestr("manifest.json", json.dumps(VALID_MANIFEST))
        package.writestr("ui/index.html", "<!doctype html>")
        package.writestr("backend/worker", "#!/usr/bin/env python3\n")
    manifest, digest = validate_package(complete.getvalue())
    assert manifest["id"] == "example.app"
    assert len(digest) == 64


def test_application_package_install_is_atomic_and_refreshes_registry(service, tmp_path):
    svc, _ = service
    package_root = tmp_path / "apps"
    svc.registry = ApplicationRegistry(package_root=package_root)
    svc.runtime.package_root = package_root
    manifest = {**VALID_MANIFEST, "id": "uploaded.app", "name": "Uploaded"}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("ui/index.html", "<main>uploaded</main>")
        package.writestr("backend/worker", "#!/usr/bin/env python3\n")

    installed = svc.install_package(archive.getvalue())

    assert installed["id"] == "uploaded.app"
    assert len(installed["package_sha256"]) == 64
    assert (package_root / "uploaded.app" / "ui/index.html").read_text() == "<main>uploaded</main>"
    assert svc.registry.get("uploaded.app")["name"] == "Uploaded"
    assert svc.get("uploaded.app")["version"] == "1.0.0"

    with pytest.raises(Exception, match="already installed"):
        svc.install_package(archive.getvalue())


def test_application_package_upload_route_stages_candidate(service, monkeypatch, tmp_path):
    svc, _ = service
    svc.registry = ApplicationRegistry(package_root=tmp_path / "apps")
    svc.runtime.package_root = tmp_path / "apps"
    import app.applications.router as applications_router
    class CandidateStub:
        def create(self, payload):
            return {"id": "candidate-1", "status": "staged", "artifact": payload["artifact"]}

    monkeypatch.setattr(applications_router, "service", svc)
    monkeypatch.setattr("app.applications.service.CandidateService", lambda: CandidateStub())
    monkeypatch.setattr("app.applications.service.data_root", lambda: tmp_path)
    app = FastAPI()
    app.include_router(applications_router.router, prefix="/api")
    client = TestClient(app)
    manifest = {**VALID_MANIFEST, "id": "route.app", "name": "Route App"}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("ui/index.html", "<main>route</main>")
        package.writestr("backend/worker", "#!/usr/bin/env python3\n")

    response = client.post(
        "/api/applications/packages",
        files={"package": ("route.zip", archive.getvalue(), "application/zip")},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending_approval"
    assert response.json()["data"]["candidate"]["id"] == "candidate-1"


def test_application_candidate_activation_requires_approval_and_installs_atomically(service, monkeypatch, tmp_path):
    svc, _ = service
    package_root = tmp_path / "apps"
    svc.registry = ApplicationRegistry(package_root=package_root)
    svc.runtime.package_root = package_root
    manifest = {**VALID_MANIFEST, "id": "approved.app", "name": "Approved App"}
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as package:
        package.writestr("manifest.json", json.dumps(manifest))
        package.writestr("ui/index.html", "<main>approved</main>")
        package.writestr("backend/worker", "#!/usr/bin/env python3\n")
    content = archive.getvalue()
    package_id = "a" * 32
    candidate = {
        "id": "candidate-approved",
        "kind": "application",
        "status": "approved",
        "artifact": {"package_id": package_id, "sha256": __import__("hashlib").sha256(content).hexdigest()},
    }
    class CandidateStub:
        def get(self, candidate_id):
            assert candidate_id == "candidate-approved"
            return candidate
    candidate_root = tmp_path / "application-candidates"
    candidate_root.mkdir()
    (candidate_root / f"{package_id}.zip").write_bytes(content)
    monkeypatch.setattr("app.applications.service.CandidateService", lambda: CandidateStub())
    monkeypatch.setattr("app.applications.service.data_root", lambda: tmp_path)
    assert svc.activate_candidate("candidate-approved")["status"] == "activated"
    assert (package_root / "approved.app" / "ui/index.html").read_text() == "<main>approved</main>"


@pytest.mark.parametrize("field,value", [("ui", {"entry": "../index.html"}), ("id", "../evil"), ("capabilities", ["wiki.read", "wiki.read"])])
def test_manifest_rejects_unsafe_or_duplicate_declarations(field, value):
    from app.applications.manifest import ApplicationManifestError, validate_manifest

    manifest = dict(VALID_MANIFEST)
    manifest[field] = value
    with pytest.raises(ApplicationManifestError):
        validate_manifest(manifest)


def test_application_api_core_lifecycle_workspace_and_wiki(service, monkeypatch, tmp_path):
    svc, _ = service
    import app.applications.router as applications_router

    app = FastAPI()
    app.include_router(applications_router.router, prefix="/api")
    monkeypatch.setattr(applications_router, "service", svc)
    client = TestClient(app)

    listed = client.get("/api/applications")
    assert listed.json()["code"] == 0
    assert listed.json()["data"][0]["id"] == "wiki"
    assert client.get("/api/applications/wiki").json()["data"]["name"] == "Wiki"
    assert client.post("/api/applications/wiki/disable").json()["data"]["status"] == "disabled"
    assert client.post("/api/applications/wiki/enable").json()["data"]["enabled"] is True

    configured = client.put("/api/applications/settings/workspace", json={"root": str(tmp_path / "workspace")})
    assert configured.json()["data"] == {"workspace_ref": "workspace://default", "configured": True, "root": str(tmp_path / "workspace")}
    assert client.get("/api/applications/settings/workspace").json()["data"]["root"] == str(tmp_path / "workspace")
    instance = client.post("/api/applications/wiki/instances", json={"instance_id": "one"}).json()["data"]
    assert instance["workspace_ref"] == "workspace://applications/wiki/instances/one"
    instance_two = client.post("/api/applications/wiki/instances", json={"instance_id": "two"}).json()["data"]
    assert instance_two["id"] != instance["id"]
    assert (tmp_path / "workspace" / "wiki" / "one").is_dir()
    assert (tmp_path / "workspace" / "wiki" / "two").is_dir()

    run = client.post("/api/applications/wiki/instances/one/runs", json={"request_id": "req-1"}).json()["data"]
    assert run["status"] == "running"
    capability = client.post(
        f"/api/applications/runs/{run['run_id']}/capability",
        json={"capability": "wiki.read", "method": "graph"},
    )
    assert capability.json()["data"]["nodes"] == [{"id": "n1"}]
    invoke = client.post(f"/api/applications/runs/{run['run_id']}/invoke", json={"method": "refresh"})
    assert invoke.json()["data"]["accepted"] is True
    article = client.post(
        f"/api/applications/runs/{run['run_id']}/capability",
        json={"capability": "wiki.read", "method": "article", "input": {"source_id": "source-1"}},
    )
    assert article.json()["data"]["id"] == "source-1"
    assert client.post(f"/api/applications/runs/{run['run_id']}/cancel").json()["data"]["status"] == "cancelled"
    assert client.post(f"/api/applications/runs/{run['run_id']}/cancel").json()["data"]["status"] == "cancelled"


def test_application_service_recovers_orphaned_runs(service):
    svc, engine = service
    factory = svc.session_factory
    db = factory()
    try:
        row = ApplicationRun(
            run_id="orphaned-run",
            app_id="wiki",
            instance_id="orphaned-instance",
            request_id=None,
            payload_hash="hash",
            runtime_kind="managed-worker",
            status="running",
        )
        db.add(ApplicationInstance(id="orphaned-instance", app_id="wiki", title="Orphaned", workspace_ref="workspace://applications/wiki/instances/orphaned-instance"))
        db.add(row)
        db.commit()
    finally:
        db.close()

    assert svc.recover_nonterminal_runs() == ["orphaned-run"]
    with engine.connect() as connection:
        recovered = connection.execute(text("SELECT status, error_code FROM application_runs WHERE run_id = 'orphaned-run'")).one()
    assert recovered == ("interrupted", "host_restarted")


def test_application_data_and_workspace_capabilities_are_isolated(service, tmp_path):
    svc, _ = service
    instance = svc.create_instance("wiki", instance_id="data-instance")
    run = svc.start_run("wiki", instance["id"], {})
    db = svc.session_factory()
    try:
        row = db.get(Application, "wiki")
        row.manifest_json = json.dumps({**VALID_MANIFEST, "capabilities": ["app.data", "workspace.file", "artifact.create", "artifact.read"]})
        db.commit()
    finally:
        db.close()
    assert svc.invoke_capability(run["run_id"], "app.data", "put", {"key": "draft", "value": {"ok": True}})["exists"] is True
    assert svc.invoke_capability(run["run_id"], "app.data", "get", {"key": "draft"})["value"] == {"ok": True}
    assert svc.invoke_capability(run["run_id"], "workspace.file", "write", {"path": "notes/a.txt", "content": "hello"})["bytes"] == 5
    assert svc.invoke_capability(run["run_id"], "workspace.file", "read", {"path": "notes/a.txt"})["content"] == "hello"
    artifact = svc.invoke_capability(run["run_id"], "artifact.create", "create", {"kind": "report", "data": {"ok": True}})
    assert svc.invoke_capability(run["run_id"], "artifact.read", "read", {"artifact_id": artifact["artifact_id"]})["data"] == {"ok": True}
    with pytest.raises(Exception, match="safe"):
        svc.invoke_capability(run["run_id"], "workspace.file", "read", {"path": "../secret"})
    external = tmp_path / "external-application-test.txt"
    external.write_text("external", encoding="utf-8")
    try:
        svc.set_external_read_roots([str(external.parent)])
        assert svc.invoke_capability(run["run_id"], "workspace.file", "read_external", {"path": str(external)})["content"] == "external"
    finally:
        external.unlink(missing_ok=True)


def test_permission_grant_and_async_job_contract(service):
    svc, _ = service
    instance = svc.create_instance("wiki", instance_id="permission-instance")
    run = svc.start_run("wiki", instance["id"], {})
    db = svc.session_factory()
    try:
        row = db.get(Application, "wiki")
        row.manifest_json = json.dumps({**VALID_MANIFEST, "capabilities": ["workspace.file"], "permissions": ["workspace.write"]})
        db.commit()
    finally:
        db.close()
    assert svc.get_permissions("wiki")["workspace.write"]["granted"] is True
    svc.set_permissions("wiki", {"workspace.write": False})
    with pytest.raises(Exception, match="permission required"):
        svc.invoke_capability(run["run_id"], "workspace.file", "write", {"path": "a.txt", "content": "x"})
    svc.set_permissions("wiki", {"workspace.write": True})
    job = svc.invoke_capability(run["run_id"], "workspace.file", "write", {"path": "a.txt", "content": "x"}, mode="async")
    assert job["mode"] == "async"
    import time
    status = svc.get_job(job["job_id"])
    for _ in range(20):
        if status["status"] not in {"queued", "running"}:
            break
        time.sleep(0.05)
        status = svc.get_job(job["job_id"])
    assert status["status"] == "completed"
    assert [event["type"] for event in svc.job_events(job["job_id"])] == ["accepted", "started", "completed"]


def test_plugin_capability_routes_through_host_permission(monkeypatch, service):
    svc, _ = service
    instance = svc.create_instance("wiki", instance_id="plugin-instance")
    run = svc.start_run("wiki", instance["id"], {})
    db = svc.session_factory()
    try:
        row = db.get(Application, "wiki")
        row.manifest_json = json.dumps({**VALID_MANIFEST, "capabilities": ["plugin.invoke"], "permissions": ["plugin.invoke"]})
        db.commit()
    finally:
        db.close()
    svc.set_permissions("wiki", {"plugin.invoke": True})
    called = {}

    def fake_invoke(self, plugin_id, capability_id, payload, *, request_id):
        called.update(plugin_id=plugin_id, capability_id=capability_id, payload=payload, request_id=request_id)
        return {"schema_version": "conversion-artifact.v1", "request_id": request_id, "status": "completed"}

    monkeypatch.setattr("app.applications.service.PluginManager.invoke", fake_invoke)
    result = svc.invoke_capability(run["run_id"], "plugin.invoke", "invoke", {"plugin_id": "official.document-to-markdown", "capability_id": "document.to_markdown", "request_id": "req-1", "input": {"input_path": "workspace://file"}})
    assert result["status"] == "completed"
    assert called == {"plugin_id": "official.document-to-markdown", "capability_id": "document.to_markdown", "payload": {"input_path": "workspace://file"}, "request_id": "req-1"}


def test_run_request_id_is_idempotent_and_conflicting_payload_is_denied(service):
    svc, _ = service
    instance = svc.create_instance("wiki", instance_id="one")
    first = svc.start_run("wiki", instance["id"], {"request_id": "same", "method": "start", "input": {"x": 1}})
    again = svc.start_run("wiki", instance["id"], {"request_id": "same", "method": "start", "input": {"x": 1}})
    assert again["run_id"] == first["run_id"]
    with pytest.raises(Exception, match="different payload"):
        svc.start_run("wiki", instance["id"], {"request_id": "same", "method": "start", "input": {"x": 2}})


def test_application_migration_registry_does_not_touch_other_registry_or_user_version(service):
    _, engine = service
    with engine.begin() as connection:
        connection.execute(text("PRAGMA user_version = 37"))
        connection.execute(text("CREATE TABLE plugin_app_migrations (version INTEGER PRIMARY KEY, marker TEXT)"))
        connection.execute(text("INSERT INTO plugin_app_migrations(version, marker) VALUES (9, 'keep')"))
    assert ensure_application_migration_registry(engine) == ("application-host-v1", "application-runtime-v2")
    with engine.connect() as connection:
        assert connection.execute(text("PRAGMA user_version")).scalar() == 37
        assert connection.execute(text("SELECT marker FROM plugin_app_migrations")).scalar() == "keep"
        assert connection.execute(text("SELECT migration_id FROM application_app_migrations")).scalar() == "application-host-v1"


def test_runtime_policy_rejects_unsupported_platform_and_public_listener():
    runtime = ApplicationRuntime()
    with pytest.raises(ApplicationRuntimeError, match="does not support"):
        runtime.start(VALID_MANIFEST, RuntimeContext("example.app", "i", "r", platform="mobile"))
    unsafe = {**VALID_MANIFEST, "runtime": {"kind": "managed-worker", "public_listener": True}}
    with pytest.raises(ApplicationRuntimeError, match="listener"):
        runtime.start(unsafe, RuntimeContext("example.app", "i", "r"))


def test_desktop_process_runtime_uses_private_jsonl_transport_and_reclaims_process(tmp_path):
    package = tmp_path / "example.app"
    package.mkdir()
    worker = package / "worker"
    worker.write_text(
        "#!/usr/bin/env python3\n"
        "import json, sys\n"
        "for line in sys.stdin:\n"
        " request = json.loads(line)\n"
        " response = {'protocol': request['protocol'], 'type': 'ready' if request['type'] == 'hello' else 'result', 'request_id': request['request_id'], 'app_id': request.get('app_id'), 'instance_id': request.get('instance_id'), 'run_id': request.get('run_id'), 'sdk_version': request.get('sdk_version'), 'ok': True}\n"
        " print(json.dumps(response), flush=True)\n",
        encoding="utf-8",
    )
    worker.chmod(worker.stat().st_mode | 0o111)
    manifest = {**VALID_MANIFEST, "id": "example.app", "runtime": {"kind": "process-jsonl", "entry": "worker"}}
    runtime = ApplicationRuntime(package_root=tmp_path)
    context = RuntimeContext("example.app", "instance", "run", platform="desktop")

    assert runtime.start(manifest, context)["runtime_kind"] == "process-jsonl"
    assert runtime.invoke(manifest, context, "ping", {})["ok"] is True
    process = runtime._processes[context.run_id]
    process.terminate()
    process.wait(timeout=2)
    assert runtime.status(context.run_id) == "interrupted"
    assert runtime.stop(manifest, context)["status"] == "stopped"
    with pytest.raises(ApplicationRuntimeError, match="not running"):
        runtime.invoke(manifest, context, "ping", {})
