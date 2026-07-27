import pathlib
import sys
import unittest
from contextlib import asynccontextmanager
from unittest.mock import patch

from fastapi.testclient import TestClient


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app import _default_cors_origins  # noqa: E402
from app.core.runtime_mode import resolve_runtime_settings  # noqa: E402
from app.routers import migration  # noqa: E402


@asynccontextmanager
async def _lifespan(_app):
    yield


class TestCoreSecurityContracts(unittest.TestCase):
    def test_runtime_defaults_bind_backend_to_loopback(self):
        with patch.dict("os.environ", {}, clear=True):
            settings = resolve_runtime_settings()

        self.assertEqual(settings["backend_host"], "127.0.0.1")

    def test_default_cors_allows_only_expected_local_frontend_and_tauri_origins(self):
        with patch.dict("os.environ", {"FRONTEND_PORT": "3015"}, clear=True):
            from fastapi import FastAPI
            from fastapi.middleware.cors import CORSMiddleware

            app = FastAPI()
            app.add_middleware(
                CORSMiddleware,
                allow_origins=_default_cors_origins(),
                allow_credentials=True,
                allow_methods=["*"],
                allow_headers=["*"],
            )
            app.include_router(migration.router, prefix="/api")
            client = TestClient(app)

            allowed = client.options(
                "/api/migration/export",
                headers={
                    "Origin": "http://127.0.0.1:3015",
                    "Access-Control-Request-Method": "POST",
                },
            )
            disallowed_extension = client.options(
                "/api/migration/export",
                headers={
                    "Origin": "chrome-extension://abcdef",
                    "Access-Control-Request-Method": "POST",
                },
            )
            disallowed_null = client.options(
                "/api/migration/export",
                headers={
                    "Origin": "null",
                    "Access-Control-Request-Method": "POST",
                },
            )
            disallowed_random_port = client.options(
                "/api/migration/export",
                headers={
                    "Origin": "http://127.0.0.1:9999",
                    "Access-Control-Request-Method": "POST",
                },
            )

        self.assertEqual(allowed.status_code, 200)
        self.assertEqual(allowed.headers.get("access-control-allow-origin"), "http://127.0.0.1:3015")
        self.assertNotIn("access-control-allow-origin", disallowed_extension.headers)
        self.assertNotIn("access-control-allow-origin", disallowed_null.headers)
        self.assertNotIn("access-control-allow-origin", disallowed_random_port.headers)

    def test_main_does_not_reintroduce_wide_cors_regex(self):
        main_source = (ROOT / "backend" / "main.py").read_text(encoding="utf-8")

        self.assertNotIn("allow_origin_regex", main_source)
        self.assertNotIn("chrome-extension://", main_source)
        self.assertNotIn("|^null$", main_source)

    def test_migration_routes_require_desktop_session_token_when_configured(self):
        app = TestClient(self._migration_test_app())
        with patch.dict("os.environ", {"NOTEMELD_DESKTOP_SESSION_TOKEN": "desktop-secret"}, clear=True):
            missing = app.post("/api/migration/export", json={"package_name": "backup"})
            wrong = app.post(
                "/api/migration/export",
                json={"package_name": "backup"},
                headers={"X-NoteMeld-Session": "wrong"},
            )
            with patch("app.routers.migration.MigrationExportService") as service_cls:
                service_cls.return_value.start_export.return_value = {"job_id": "job-export-1"}
                ok = app.post(
                    "/api/migration/export",
                    json={"package_name": "backup"},
                    headers={"X-NoteMeld-Session": "desktop-secret"},
                )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(wrong.status_code, 401)
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.json()["data"], {"job_id": "job-export-1"})

    def test_tauri_runtime_generates_and_passes_session_token(self):
        lib_source = (ROOT / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")

        self.assertIn("session_token", lib_source)
        self.assertIn("NOTEMELD_DESKTOP_SESSION_TOKEN", lib_source)
        self.assertIn("generate_session_token", lib_source)

    @staticmethod
    def _migration_test_app():
        from fastapi import FastAPI

        app = FastAPI()
        app.include_router(migration.router, prefix="/api")
        return app


if __name__ == "__main__":
    unittest.main()
