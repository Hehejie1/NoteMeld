# -*- mode: python ; coding: utf-8 -*-

import os
import importlib.util
from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules


ROOT_DIR = Path(os.environ.get("NOTEMELD_ROOT_DIR", Path.cwd())).resolve()
BACKEND_DIR = ROOT_DIR / "backend"
DESKTOP_ENTRY = BACKEND_DIR / "desktop_entry.py"
APP_RESOURCES_DIR = BACKEND_DIR / "app" / "resources"


def external_plugin_dir(plugin_name: str) -> Path | None:
    """Locate a plugin from the independent notemeld-plugins repository.

    The application repository must not carry plugin source. Packaging can
    still bundle a plugin when the release job provides the sibling repository
    (or sets NOTEMELD_PLUGINS_DIR explicitly).
    """
    configured = str(os.environ.get("NOTEMELD_PLUGINS_DIR") or "").strip()
    roots = [Path(configured).expanduser().resolve()] if configured else []
    roots.append(ROOT_DIR.parent / "notemeld-plugins")
    for root in roots:
        candidates = [root / "plugins" / plugin_name, root / plugin_name]
        for candidate in candidates:
            if candidate.is_dir():
                return candidate
    return None


OFFICIAL_LINK_PLUGIN_DIR = external_plugin_dir("official-link-note")
APP_RESOURCE_DATAS = []
STYLE_PREVIEW_STANDARD = APP_RESOURCES_DIR / "style_preview_standard.md"
if STYLE_PREVIEW_STANDARD.exists():
    APP_RESOURCE_DATAS.append((str(STYLE_PREVIEW_STANDARD), "app/resources"))
MODEL_RUNTIME_CATALOG = APP_RESOURCES_DIR / "model_runtime_catalog.json"
if MODEL_RUNTIME_CATALOG.exists():
    APP_RESOURCE_DATAS.append((str(MODEL_RUNTIME_CATALOG), "app/resources"))
if OFFICIAL_LINK_PLUGIN_DIR is not None:
    APP_RESOURCE_DATAS.append((str(OFFICIAL_LINK_PLUGIN_DIR), "plugins/official-link-note"))

hiddenimports = collect_submodules("app")
sdk_spec = importlib.util.find_spec("notemeld_agent_sdk")
if sdk_spec is not None:
    sdk_import_root = Path(sdk_spec.submodule_search_locations[0])
    if sdk_import_root.is_dir():
        # AgentSdkRuntime imports this package dynamically; the package must
        # come from the installed standalone SDK artifact.
        hiddenimports += collect_submodules("notemeld_agent_sdk")
        APP_RESOURCE_DATAS += collect_data_files("notemeld_agent_sdk", include_py_files=True)
        APP_RESOURCE_DATAS.append((str(sdk_import_root), "notemeld_agent_sdk"))
        if (sdk_import_root / "native").is_dir():
            APP_RESOURCE_DATAS.append((str(sdk_import_root / "native"), "notemeld_agent_sdk/native"))

a = Analysis(
    [str(DESKTOP_ENTRY)],
    pathex=[str(BACKEND_DIR)],
    binaries=[],
    datas=APP_RESOURCE_DATAS,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib.tests",
        "numpy.tests",
        "pandas.tests",
        "pytest",
        "tkinter",
    ],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="notemeld-backend",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=os.environ.get("NOTEMELD_TARGET_ARCH"),
    codesign_identity=None,
    entitlements_file=None,
)
