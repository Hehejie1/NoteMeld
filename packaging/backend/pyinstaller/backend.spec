# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules


ROOT_DIR = Path(os.environ.get("NOTEMELD_ROOT_DIR", Path.cwd())).resolve()
BACKEND_DIR = ROOT_DIR / "backend"
DESKTOP_ENTRY = BACKEND_DIR / "desktop_entry.py"
APP_RESOURCES_DIR = BACKEND_DIR / "app" / "resources"
APP_RESOURCE_DATAS = []
STYLE_PREVIEW_STANDARD = APP_RESOURCES_DIR / "style_preview_standard.md"
if STYLE_PREVIEW_STANDARD.exists():
    APP_RESOURCE_DATAS.append((str(STYLE_PREVIEW_STANDARD), "app/resources"))
MODEL_RUNTIME_CATALOG = APP_RESOURCES_DIR / "model_runtime_catalog.json"
if MODEL_RUNTIME_CATALOG.exists():
    APP_RESOURCE_DATAS.append((str(MODEL_RUNTIME_CATALOG), "app/resources"))

hiddenimports = collect_submodules("app")

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
