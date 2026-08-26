"""NoteMeld host adapter for the portable official link plugin."""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from typing import Any

from app.services.note import NoteGenerator
from app.services.web_note import WebNoteGenerator


PLUGIN_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "plugins"
    / "official-link-note"
    / "src"
    / "official_link_note.py"
)


def _load_plugin_type():
    spec = importlib.util.spec_from_file_location("notemeld_official_link_note", PLUGIN_SOURCE)
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
