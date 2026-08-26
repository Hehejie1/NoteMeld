#!/usr/bin/env python3
"""Generate the current URL-to-Note capability inventory without importing app code."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend" / "app"
TESTS = ROOT / "backend" / "tests"
OUTPUT = ROOT / "backend" / "tests" / "fixtures" / "n01-url-capability-baseline.json"


def _source(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _literal_dict(path: Path, name: str) -> dict[str, object]:
    tree = ast.parse(_source(path), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == name for target in node.targets
        ):
            value = ast.literal_eval(node.value)
            if isinstance(value, dict):
                return value
    raise RuntimeError(f"could not find literal {name} in {path}")


def _class_for_import(module_path: Path, class_name: str) -> str:
    tree = ast.parse(_source(module_path), filename=str(module_path))
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            return ast.get_source_segment(_source(module_path), node) or ""
    return ""


def _platform_patterns() -> dict[str, str]:
    return {key: str(value) for key, value in _literal_dict(
        BACKEND / "validators" / "video_url_validator.py", "SUPPORTED_PLATFORMS"
    ).items()}


def build_baseline() -> dict[str, object]:
    registry_path = BACKEND / "services" / "constant.py"
    registry = _source(registry_path)
    router_source = _source(BACKEND / "routers" / "note.py")
    collector_source = _source(BACKEND / "services" / "multisource_video_collector.py")
    note_source = _source(BACKEND / "services" / "note.py")
    web_source = _source(BACKEND / "services" / "web_note.py")
    imports = dict(re.findall(
        r"from app\.downloaders\.([\w_]+) import (\w+)", registry
    ))
    registry_tree = ast.parse(registry, filename=str(registry_path))
    support = next(
        node.value for node in ast.walk(registry_tree)
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "SUPPORT_PLATFORM_MAP" for target in node.targets)
    )
    platforms = []
    patterns = _platform_patterns()
    for key_node, value_node in zip(support.keys, support.values):
        key = ast.literal_eval(key_node)
        if not isinstance(key, str) or not isinstance(value_node, ast.Call):
            raise RuntimeError("SUPPORT_PLATFORM_MAP contains a non-constructor entry")
        # Resolve the constructor from the original AST, preserving registry order.
        constructor = ast.unparse(value_node.func)
        class_name = constructor.split(".")[-1]
        module_name = next((module for module, imported in imports.items() if imported == class_name), "")
        module_path = BACKEND / "downloaders" / f"{module_name}.py"
        class_source = _class_for_import(module_path, class_name)
        platforms.append({
            "platform": key,
            "url_pattern": patterns.get(key, "<registry-only>"),
            "downloader": f"app.downloaders.{module_name}:{class_name}",
            "capabilities": {
                "subtitle_first": "download_subtitles" in class_source or "subtitle" in class_source.lower(),
                "download": "download_video" in class_source or "download(" in class_source,
                "video_info": "fetch_video_info" in class_source,
                "screenshot": True,
                "web_fallback": True,
            },
        })

    test_files = sorted(
        str(path.relative_to(ROOT))
        for path in TESTS.rglob("test_*.py")
        if any(token in path.name.lower() for token in ("downloader", "multisource", "web_note", "note_task"))
    )
    return {
        "schema_version": "n01-url-capability-baseline.v1",
        "generated_from": [
            "backend/app/services/constant.py",
            "backend/app/validators/video_url_validator.py",
            "backend/app/routers/note.py",
            "backend/app/services/multisource_video_collector.py",
            "backend/app/services/web_note.py",
            "backend/tests/**/test_*downloader*.py",
            "backend/tests/**/test_multisource*.py",
            "backend/tests/**/test_web_note*.py",
        ],
        "pipeline": {
            "subtitle_first": "download_subtitles" in (registry + note_source),
            "download": "download_video" in (registry + note_source),
            "transcription": "transcri" in (collector_source + note_source),
            "screenshots": "screenshot" in (router_source + collector_source + note_source),
            "web_fallback": "web_fallback" in (router_source + note_source + web_source),
            "task_state": "backend/app/services/task_status_writer.py",
            "error_classification": "backend/app/enmus/exception.py",
        },
        "platforms": platforms,
        "regression_tests": test_files,
    }


def main() -> None:
    result = json.dumps(build_baseline(), ensure_ascii=False, indent=2) + "\n"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    if OUTPUT.exists() and OUTPUT.read_text(encoding="utf-8") == result:
        return
    OUTPUT.write_text(result, encoding="utf-8")


if __name__ == "__main__":
    main()
