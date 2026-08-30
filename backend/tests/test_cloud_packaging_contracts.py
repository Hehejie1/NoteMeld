from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def _requirements(path: Path) -> set[str]:
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.lstrip().startswith("#")
    }


def test_cloud_and_desktop_package_same_crypto_runtime() -> None:
    cloud = _requirements(ROOT / "cloud" / "requirements.txt")
    desktop = _requirements(ROOT / "packaging" / "backend" / "requirements-core.txt")
    cloud_pins = {item for item in cloud if item.startswith("cryptography==")}
    desktop_pins = {item for item in desktop if item.startswith("cryptography==")}

    assert len(cloud_pins) == 1
    assert cloud_pins == desktop_pins


def test_backend_spec_collects_cloud_sync_modules() -> None:
    spec = (ROOT / "packaging" / "backend" / "pyinstaller" / "backend.spec").read_text(
        encoding="utf-8"
    )

    assert 'hiddenimports = collect_submodules("app")' in spec


def test_client_e2ee_is_inside_packaged_backend_namespace() -> None:
    canonical = ROOT / "backend" / "app" / "cloud_sync" / "e2ee.py"
    assert canonical.is_file()
    assert "class SessionCipher" in canonical.read_text(encoding="utf-8")


def test_cloud_service_does_not_import_desktop_e2ee_module() -> None:
    cloud_sources = list((ROOT / "cloud").glob("*.py"))
    assert all(
        "backend.app" not in source.read_text(encoding="utf-8")
        for source in cloud_sources
    )
