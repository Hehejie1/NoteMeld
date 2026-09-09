import hashlib
import io
import json
import pathlib
import sys
import zipfile
from types import SimpleNamespace
from unittest.mock import Mock, patch

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.services.plugins.release_resolver import RELEASE_TIMEOUT, ReleaseResolver, ReleaseResolverError
from app.services.plugins.manager import PluginManager, authorize_permissions
from app.services.plugins.verifier import PluginVerificationError, promote_staged, stage_and_verify


def package(manifest, files=None):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("plugin.json", json.dumps(manifest))
        for name, value in (files or {}).items():
            archive.writestr(name, value)
    return buffer.getvalue()


def valid_manifest(version="1.0.0"):
    return {"id": "fixture.plugin", "version": version, "sdk_version": "1", "license": "MIT", "requested_permissions": ["note.read"], "runtime": {"command": ["python", "-c", "pass"]}}


def test_verifier_checks_hash_license_version_and_creates_unique_staging(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.plugins.verifier.plugin_staging_dir", lambda: tmp_path / "staging")
    content = package(valid_manifest())
    staging, manifest, digest = stage_and_verify(content, expected_sha256=hashlib.sha256(content).hexdigest(), expected_plugin_id="fixture.plugin", expected_version="1.0.0")
    assert staging.name
    assert manifest["license"] == "MIT"
    assert digest == hashlib.sha256(content).hexdigest()
    with pytest.raises(PluginVerificationError, match="sha256"):
        stage_and_verify(content, expected_sha256="0" * 64)
    with pytest.raises(PluginVerificationError, match="license"):
        stage_and_verify(package({**valid_manifest(), "license": "NOPE"}))
    with pytest.raises(PluginVerificationError, match="version"):
        stage_and_verify(content, expected_version="2.0.0")


def test_verifier_rejects_zip_slip_and_install_scripts(tmp_path, monkeypatch):
    monkeypatch.setattr("app.services.plugins.verifier.plugin_staging_dir", lambda: tmp_path / "staging")
    with pytest.raises(PluginVerificationError, match="unsafe"):
        stage_and_verify(package(valid_manifest(), {"../escape.txt": "x"}))
    with pytest.raises(PluginVerificationError, match="install scripts"):
        stage_and_verify(package(valid_manifest(), {"install.sh": "echo bad"}))


def test_release_resolver_rejects_non_https_and_untrusted_redirect():
    with pytest.raises(ReleaseResolverError, match="HTTPS"):
        ReleaseResolver().resolve("http://github.com/a/b/releases/download/v1/a.zip")
    with pytest.raises(ReleaseResolverError, match="allowlisted"):
        ReleaseResolver().resolve("https://example.com/a.zip")


class FakeResponse:
    def __init__(self, status_code, content=b"x", headers=None):
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)

    def get(self, _url):
        return next(self.responses)


def test_release_resolver_limits_redirects_size_and_timeout():
    redirect = FakeResponse(302, headers={"location": "https://github.com/a/b/releases/download/v1/a.zip"})
    with pytest.raises(ReleaseResolverError, match="redirects"):
        ReleaseResolver(client=FakeClient([redirect] * 5)).resolve("https://github.com/a/b/releases/download/v1/a.zip")
    oversized = FakeResponse(200, content=b"123", headers={"content-length": "3", "content-type": "application/zip"})
    with pytest.raises(ReleaseResolverError, match="maximum size"):
        ReleaseResolver(client=FakeClient([oversized]), max_bytes=2).resolve("https://github.com/a/b/releases/download/v1/a.zip")
    assert RELEASE_TIMEOUT.read == 30.0


def test_permission_authority_is_user_granted_and_fail_closed():
    authorize_permissions({"note.read"}, {"note.read"})
    with pytest.raises(PluginVerificationError, match="permissions"):
        authorize_permissions({"network"}, set())
    with pytest.raises(PluginVerificationError, match="permissions"):
        authorize_permissions({"filesystem.root"}, {"filesystem.root"})


def test_version_directories_are_immutable_and_old_versions_remain(tmp_path):
    first = tmp_path / "staging-1"; first.mkdir(); (first / "payload").mkdir(); (first / "payload" / "plugin.json").write_text("{}")
    second = tmp_path / "staging-2"; second.mkdir(); (second / "payload").mkdir(); (second / "payload" / "plugin.json").write_text("{}")
    v1 = promote_staged(first, "fixture.plugin", "1.0.0", tmp_path / "versions")
    v2 = promote_staged(second, "fixture.plugin", "2.0.0", tmp_path / "versions")
    assert v1.is_dir() and v2.is_dir()
    with pytest.raises(PluginVerificationError, match="immutable"):
        duplicate = tmp_path / "staging-3"; duplicate.mkdir(); (duplicate / "payload").mkdir(); promote_staged(duplicate, "fixture.plugin", "1.0.0", tmp_path / "versions")


def test_runtime_crash_fails_closed_and_is_not_marked_running():
    installation = SimpleNamespace(plugin_id="fixture.plugin", active_version="1.0.0", runtime_status="disabled", runtime_pid=None, manifest_json=json.dumps({"runtime": {"command": ["fixture"]}}))
    db = Mock(); db.get.return_value = SimpleNamespace(path="/tmp/plugin")
    crashed = Mock(pid=123, poll=Mock(return_value=1))
    with patch("app.services.plugins.manager.subprocess.Popen", return_value=crashed):
        with pytest.raises(PluginVerificationError, match="crashed"):
            PluginManager._start_runtime(installation, db)
    assert installation.runtime_status == "crashed"


def test_process_jsonl_invoke_is_supervised_and_binds_request(tmp_path, monkeypatch):
    script = "import json,sys; value=json.loads(sys.stdin.readline()); print(json.dumps({'schema_version':'conversion-artifact.v1','request_id':value['request_id'],'status':'completed','result':{'operation':value['operation']}}))"
    installation = SimpleNamespace(
        plugin_id="fixture.plugin", active_version="1.0.0", enabled=1, runtime_status="running",
        manifest_json=json.dumps({"requested_permissions": ["workspace.read"], "capabilities": [{"id": "document.to_markdown"}], "runtime": {"kind": "process-jsonl", "command": [sys.executable, "-c", script]}, "transport": {"kind": "stdin-stdout-jsonl"}}),
        granted_permissions_json=json.dumps(["workspace.read"]),
    )
    version = SimpleNamespace(path=str(tmp_path))
    db = Mock()
    db.get.side_effect = [installation, version]
    monkeypatch.setattr("app.services.plugins.manager.SessionLocal", lambda: db)
    result = PluginManager().invoke("fixture.plugin", "document.to_markdown", {"input_path": "workspace://input"}, request_id="req-1")
    assert result["request_id"] == "req-1"
    assert result["result"]["operation"] == "document.to_markdown"
    db.commit.assert_called_once()
