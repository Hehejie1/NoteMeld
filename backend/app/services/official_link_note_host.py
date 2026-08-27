"""NoteMeld host adapter for the portable official link plugin."""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any

from app.services.note import NoteGenerator
from app.services.web_note import WebNoteGenerator
from app.db.engine import SessionLocal
from app.db.models.plugin import PluginInstallation, PluginVersion
from app.services.plugins.verifier import promote_staged, stage_and_verify
from app.utils.storage_paths import plugin_active_pointer, plugins_root_dir, project_root


PLUGIN_ID = "official.link-note"


def _bundled_fixture() -> Path:
    bundle_root = Path(getattr(sys, "_MEIPASS", project_root()))
    bundled = bundle_root / "plugins" / "official-link-note" / "release-fixture" / "official-link-note-1.0.0.zip"
    if bundled.is_file():
        return bundled
    configured = str(os.environ.get("NOTEMELD_PLUGINS_DIR") or "").strip()
    candidates = []
    if configured:
        configured_root = Path(configured).expanduser().resolve()
        candidates.append(configured_root / "plugins" / "official-link-note" / "release-fixture" / "official-link-note-1.0.0.zip")
        candidates.append(configured_root / "official-link-note" / "release-fixture" / "official-link-note-1.0.0.zip")
    candidates.append(project_root().parent / "notemeld-plugins" / "plugins" / "official-link-note" / "release-fixture" / "official-link-note-1.0.0.zip")
    return next((candidate for candidate in candidates if candidate.is_file()), candidates[0] if candidates else bundled)


def ensure_official_link_note_installed(session_factory=None) -> None:
    pointer = plugin_active_pointer(PLUGIN_ID)
    if pointer.is_file() and pointer.read_text(encoding="utf-8").strip():
        return
    fixture = _bundled_fixture()
    if not fixture.is_file():
        raise RuntimeError("official link plugin resource is unavailable")
    staging, manifest, digest = stage_and_verify(fixture.read_bytes(), expected_plugin_id=PLUGIN_ID)
    version = manifest["version"]
    target = promote_staged(staging, PLUGIN_ID, version, plugins_root_dir() / "versions")
    pointer.parent.mkdir(parents=True, exist_ok=True)
    temporary = pointer.with_name(f".{pointer.name}.{os.getpid()}.tmp")
    temporary.write_text(version, encoding="utf-8")
    os.replace(temporary, pointer)
    db = (session_factory or SessionLocal)()
    try:
        db.add(PluginVersion(id=f"{PLUGIN_ID}:{version}", plugin_id=PLUGIN_ID, version=version,
                             sha256=digest, path=str(target), license=manifest["license"],
                             sdk_version=manifest["sdk_version"], manifest_json=json.dumps(manifest, sort_keys=True)))
        db.add(PluginInstallation(plugin_id=PLUGIN_ID, active_version=version, enabled=1,
                                  runtime_status="running", requested_permissions_json=json.dumps(manifest["requested_permissions"]),
                                  granted_permissions_json=json.dumps(manifest["requested_permissions"]),
                                  manifest_json=json.dumps(manifest, sort_keys=True)))
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def _load_plugin_type():
    pointer = plugin_active_pointer(PLUGIN_ID)
    version = pointer.read_text(encoding="utf-8").strip() if pointer.is_file() else ""
    source = plugins_root_dir() / "versions" / PLUGIN_ID / version / "src" / "official_link_note.py"
    if not version or not source.is_file():
        raise RuntimeError("official link plugin is not installed")
    spec = importlib.util.spec_from_file_location("notemeld_official_link_note", source)
    if spec is None or spec.loader is None:
        raise RuntimeError("official link plugin is unavailable")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.OfficialLinkNotePlugin


class NoteMeldLinkNoteHost:
    """Translate host options into existing stable Note generation services."""

    def generate_video(self, *, task_id: str, video_url: str, platform: str, options: dict[str, Any]):
        return NoteGenerator().generate(
            video_url=video_url,
            platform=platform,
            task_id=task_id,
            quality=options["quality"],
            model_name=options["model_name"],
            provider_id=options["provider_id"],
            link=options.get("link", False),
            screenshot=options.get("screenshot", False),
            _format=options.get("format"),
            style=options.get("style"),
            extras=options.get("extras"),
            video_understanding=options.get("video_understanding", False),
            video_interval=options.get("video_interval", 0),
            grid_size=options.get("grid_size"),
            vision_mode=options.get("vision_mode"),
            max_sampling_points=options.get("max_sampling_points"),
            enable_refine_engine=options.get("enable_refine_engine", False),
            output_type=options.get("output_type", "note_markdown"),
        )

    def generate_web(self, *, task_id: str, web_url: str, options: dict[str, Any]):
        return WebNoteGenerator().generate(
            web_url=web_url,
            task_id=task_id,
            model_name=options["model_name"],
            provider_id=options["provider_id"],
            _format=options.get("format"),
            style=options.get("style"),
            extras=options.get("extras"),
            output_type=options.get("output_type", "note_markdown"),
        )


def create_official_link_note_plugin():
    return _load_plugin_type()(NoteMeldLinkNoteHost())


def validate_official_link(url: str, platform: str) -> str:
    return _load_plugin_type().validate_link(url, platform)
