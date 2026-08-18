import json
import os
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.utils import storage_paths  # noqa: E402


class TestCoreRuntimeContracts(unittest.TestCase):
    def test_desktop_runtime_and_bundle_resources_are_wired(self):
        lib_rs = (ROOT / "desktop" / "src-tauri" / "src" / "lib.rs").read_text(encoding="utf-8")
        runtime_ts = (ROOT / "frontend" / "src" / "utils" / "runtime.ts").read_text(encoding="utf-8")
        windows_conf = json.loads(
            (ROOT / "desktop" / "src-tauri" / "tauri.windows.conf.json").read_text(encoding="utf-8")
        )

        self.assertIn("NOTEMELD_RUNTIME_MODE", lib_rs)
        self.assertIn("NOTEMELD_DATA_DIR", lib_rs)
        self.assertIn('join("vector_db")', lib_rs)
        self.assertNotIn('command.env("NOTE_OUTPUT_DIR"', lib_rs)
        self.assertNotIn('command.env("OUT_DIR"', lib_rs)
        self.assertIn("FFMPEG_BIN_PATH", lib_rs)
        self.assertIn("notemeld-backend.exe", lib_rs)
        self.assertIn("window.__NOTEMELD_RUNTIME__", lib_rs)
        self.assertIn("desktop_runtime_bootstrap", lib_rs)
        self.assertIn("document.createElement('a')", runtime_ts)
        self.assertEqual(
            windows_conf.get("bundle", {}).get("resources", {}).get("bin/backend/notemeld-backend.exe"),
            "bin/backend/notemeld-backend.exe",
        )
        self.assertEqual(
            windows_conf.get("bundle", {}).get("resources", {}).get("resources/ffmpeg/ffmpeg-runtime-windows.zip"),
            "ffmpeg/ffmpeg-runtime.zip",
        )

    def test_storage_paths_follow_notemeld_data_dir(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = pathlib.Path(tmp_dir).resolve()
            with patch.dict(os.environ, {"NOTEMELD_DATA_DIR": str(data_root)}, clear=True):
                self.assertEqual(storage_paths.data_root(), data_root)
                self.assertEqual(storage_paths.note_output_dir(), data_root / "note_results")
                self.assertEqual(storage_paths.vector_store_dir(), data_root / "chroma")
                self.assertEqual(storage_paths.database_path(), data_root / "notemeld.db")
                self.assertEqual(storage_paths.model_root_dir(), data_root / "models")
                self.assertEqual(storage_paths.app_data_dir(), data_root / "data")
                self.assertEqual(storage_paths.frame_output_dir(), data_root / "data" / "output_frames")
                self.assertEqual(storage_paths.upload_dir(), data_root / "uploads")
                self.assertEqual(storage_paths.static_dir(), data_root / "static")
                self.assertEqual(storage_paths.screenshot_dir(), data_root / "static" / "screenshots")
                self.assertEqual(storage_paths.temp_dir(), data_root / "tmp")

    def test_legacy_subdirectory_environment_variables_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            data_root = pathlib.Path(tmp_dir).resolve()
            legacy_root = pathlib.Path(tmp_dir) / "legacy"
            with patch.dict(
                os.environ,
                {
                    "NOTEMELD_DATA_DIR": str(data_root),
                    "NOTE_OUTPUT_DIR": str(legacy_root / "notes"),
                    "VECTOR_DB_DIR": str(legacy_root / "chroma"),
                    "STATIC_DIR": str(legacy_root / "static"),
                    "OUT_DIR": str(legacy_root / "screenshots"),
                    "UPLOAD_DIR": str(legacy_root / "uploads"),
                    "DATA_DIR": str(legacy_root / "data"),
                },
                clear=True,
            ):
                self.assertTrue(storage_paths.note_output_dir().is_relative_to(data_root))
                self.assertTrue(storage_paths.vector_store_dir().is_relative_to(data_root))
                self.assertTrue(storage_paths.screenshot_dir().is_relative_to(data_root))
                self.assertTrue(storage_paths.upload_dir().is_relative_to(data_root))


if __name__ == "__main__":
    unittest.main()
