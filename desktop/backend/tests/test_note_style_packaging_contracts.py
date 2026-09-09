import pathlib
import sys
import unittest
import json
import subprocess
import tempfile
from unittest.mock import patch


ROOT = pathlib.Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "desktop" / "backend"))

from app.services import note_style_example_generator  # noqa: E402
from app.db import note_style_dao  # noqa: E402


class TestNoteStylePackagingContracts(unittest.TestCase):
    def test_desktop_updater_is_registered_and_release_manifest_is_signed(self):
        config = json.loads((ROOT / "desktop" / "src-tauri" / "tauri.conf.json").read_text(encoding="utf-8"))
        package = json.loads((ROOT / "desktop" / "package.json").read_text(encoding="utf-8"))
        cargo = (ROOT / "desktop" / "src-tauri" / "Cargo.toml").read_text(encoding="utf-8")
        capability = json.loads((ROOT / "desktop" / "src-tauri" / "capabilities" / "default.json").read_text(encoding="utf-8"))
        workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")

        self.assertIn("tauri-plugin-updater", cargo)
        self.assertEqual(config["version"], package["version"])
        self.assertIn("updater:default", capability["permissions"])
        self.assertIn("updater", config["plugins"])
        self.assertTrue(config["plugins"]["updater"]["pubkey"])
        self.assertIn("releases/latest/download/latest.json", config["plugins"]["updater"]["endpoints"][0])
        self.assertIn('createUpdaterArtifacts":true', workflow)
        self.assertIn("generate-latest-json.py", workflow)
        self.assertIn("latest.json", workflow)
        self.assertIn("darwin-aarch64", workflow)
        self.assertIn("darwin-x86_64", workflow)
        self.assertIn("windows-x86_64", workflow)
        self.assertIn("release manifest is missing required platforms", workflow)
        self.assertIn("Verify public updater manifest and signed assets", workflow)
        self.assertIn("public updater manifest and assets verified", workflow)

    def test_legacy_release_publisher_defaults_to_signed_https_release_urls(self):
        script = (
            ROOT / "scripts" / "desktop" / "packaging" / "scripts" / "publish-desktop-release.sh"
        ).read_text(encoding="utf-8")

        self.assertIn("https://github.com/Hehejie1/NoteMeld/releases/download/v${VERSION}", script)
        self.assertNotIn("http://43.167.164.213", script)
        self.assertIn("NOTEMELD_RELEASE_BASE_URL", script)
        self.assertIn("NOTEMELD_RELEASE_REMOTE", script)

    def test_latest_manifest_generation_fails_closed_on_unsigned_updater_artifact(self):
        generator = ROOT / "scripts" / "desktop" / "packaging" / "scripts" / "generate-latest-json.py"
        with tempfile.TemporaryDirectory() as directory:
            stage = pathlib.Path(directory)
            artifact = stage / "NoteMeld_0.0.4_aarch64.app.tar.gz"
            artifact.write_bytes(b"signed archive placeholder")
            result = subprocess.run(
                [sys.executable, str(generator), str(stage), "0.0.4", "https://example.test/release"],
                text=True,
                capture_output=True,
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("missing signature", result.stderr)
            self.assertFalse((stage / "latest.json").exists())

    def test_builtin_tool_website_style_is_task_recall_oriented(self):
        style = note_style_dao.get_style_template("tool_website")

        self.assertIsNotNone(style)
        self.assertEqual(style["name"], "工具网站")
        self.assertIn("能做什么", style["skeleton_html"])
        self.assertIn("适合什么时候用", style["skeleton_html"])
        self.assertIn("推荐触发词", style["skeleton_html"])
        self.assertIn("原始链接", style["rule_config"]["global"]["must_include"])
        self.assertIn("工具网站链接", style["rule_config"]["global"]["source_url_policy"])

    def test_style_example_generator_falls_back_when_resource_missing(self):
        missing_path = ROOT / "desktop" / "backend" / "app" / "resources" / "missing-style-preview.md"
        template = {"name": "默认模板", "output_formats": ["markdown", "html"]}

        with patch.object(note_style_example_generator, "_RESOURCE_PATH", missing_path):
            content = note_style_example_generator.generate_style_example_content(template)

        self.assertIn("真正有价值的内容不应该只被总结一次", content["markdown"])
        self.assertIn("默认模板", content["html"])

    def test_backend_spec_packages_style_preview_resource(self):
        spec_text = (
            ROOT / "scripts" / "desktop" / "packaging" / "backend" / "pyinstaller" / "backend.spec"
        ).read_text(encoding="utf-8")

        self.assertIn('STYLE_PREVIEW_STANDARD = APP_RESOURCES_DIR / "style_preview_standard.md"', spec_text)
        self.assertIn('APP_RESOURCE_DATAS.append((str(STYLE_PREVIEW_STANDARD), "app/resources"))', spec_text)

    def test_backend_spec_packages_model_runtime_catalog_resource(self):
        spec_text = (
            ROOT / "scripts" / "desktop" / "packaging" / "backend" / "pyinstaller" / "backend.spec"
        ).read_text(encoding="utf-8")

        self.assertIn('MODEL_RUNTIME_CATALOG = APP_RESOURCES_DIR / "model_runtime_catalog.json"', spec_text)
        self.assertIn('APP_RESOURCE_DATAS.append((str(MODEL_RUNTIME_CATALOG), "app/resources"))', spec_text)

    def test_build_backend_macos_cleans_pyinstaller_outputs_before_rebuild(self):
        script_text = (
            ROOT / "scripts" / "desktop" / "packaging" / "scripts" / "build-backend-macos.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('rm -rf "${ROOT_DIR}/build"', script_text)
        self.assertIn('rm -f "${DIST_BIN}"', script_text)

    def test_build_backend_macos_supports_python_override(self):
        script_text = (
            ROOT / "scripts" / "desktop" / "packaging" / "scripts" / "build-backend-macos.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('PYTHON_BIN="${NOTEMELD_PYTHON_BIN:-${ROOT_DIR}/.venv/bin/python3}"', script_text)

    def test_build_desktop_macos_cleans_bundle_history_before_packaging(self):
        script_text = (
            ROOT / "scripts" / "desktop" / "packaging" / "scripts" / "build-desktop-macos.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('TARGET_DIR="${ROOT_DIR}/desktop/src-tauri/target"', script_text)
        self.assertIn('rm -rf "${TARGET_OUTPUT_DIR}/bundle"', script_text)
        self.assertIn('TARGET_ARCH="${NOTEMELD_TARGET_ARCH:-$("${ROOT_DIR}/.venv/bin/python3"', script_text)
        self.assertIn('TAURI_TARGET_TRIPLE="aarch64-apple-darwin"', script_text)
        self.assertIn('TAURI_TARGET_TRIPLE="x86_64-apple-darwin"', script_text)
        self.assertIn('TARGET_OUTPUT_DIR="${TARGET_DIR}/${TAURI_TARGET_TRIPLE}/release"', script_text)
        self.assertIn('corepack pnpm tauri build --no-bundle --target "${TAURI_TARGET_TRIPLE}"', script_text)
        self.assertIn('corepack pnpm tauri bundle --bundles app', script_text)
        self.assertIn('--target "${TAURI_TARGET_TRIPLE}"', script_text)
        self.assertIn('hdiutil create -volname NoteMeld', script_text)
        self.assertIn('hdiutil verify "${DMG_PATH}"', script_text)
        self.assertIn('TAURI_CONFIG_OVERRIDE_ARGS=(--config \'{"bundle":{"createUpdaterArtifacts":false}}\')', script_text)
        self.assertIn('createUpdaterArtifacts', script_text)

    def test_build_desktop_macos_logs_stages_and_verifies_artifacts(self):
        script_text = (
            ROOT / "scripts" / "desktop" / "packaging" / "scripts" / "build-desktop-macos.sh"
        ).read_text(encoding="utf-8")

        self.assertIn('LOG_DIR="${ROOT_DIR}/desktop/logs/packaging"', script_text)
        self.assertIn('LOCK_DIR="${TARGET_DIR}/.build-desktop-macos.lock"', script_text)
        self.assertIn('export PATH="${HOME}/.cargo/bin:${PATH}"', script_text)
        self.assertIn('if [[ -t 1 ]]; then', script_text)
        self.assertIn('exec > >(tee -a "${LOG_FILE}") 2>&1', script_text)
        self.assertIn('exec >> "${LOG_FILE}" 2>&1', script_text)
        self.assertIn('echo "[notemeld] updater-signing=disabled"', script_text)
        self.assertIn('echo "[notemeld] step=backend"', script_text)
        self.assertIn('echo "[notemeld] step=clean"', script_text)
        self.assertIn('echo "[notemeld] step=tauri-build"', script_text)
        self.assertIn('echo "[notemeld] step=tauri-bundle"', script_text)
        self.assertIn('echo "[notemeld] step=dmg"', script_text)
        self.assertIn('APP_PATH="${TARGET_OUTPUT_DIR}/bundle/macos/NoteMeld.app"', script_text)
        self.assertIn('DMG_DIR="${TARGET_OUTPUT_DIR}/bundle/dmg"', script_text)
        self.assertIn('DESKTOP_BIN="${TARGET_OUTPUT_DIR}/notemeld-desktop"', script_text)
        self.assertIn('DEFAULT_UPDATER_KEY="${HOME}/.tauri/notemeld-updater.key"', script_text)
        self.assertIn('export TAURI_SIGNING_PRIVATE_KEY_PATH="${DEFAULT_UPDATER_KEY}"', script_text)
        self.assertIn('export TAURI_SIGNING_PRIVATE_KEY="$(<"${DEFAULT_UPDATER_KEY}")"', script_text)
        self.assertIn('if [[ ! -d "${APP_PATH}" ]]; then', script_text)
        self.assertIn('if [[ ${#DMG_FILES[@]} -eq 0 ]]; then', script_text)


if __name__ == "__main__":
    unittest.main()
