from __future__ import annotations

import re

from app.services.note_style_schema import DEFAULT_RULE_CONFIG, DEFAULT_STYLE_CONSTRAINTS, copy_default


def _title_from_text(text: str, source_name: str | None) -> str:
    for line in text.splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            return clean[:20]
    return (source_name or "导入模板")[:20]


def _safe_class_name(raw: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "-", raw).strip("-")
    return value or "section"


def _markdown_to_skeleton(text: str) -> str:
    sections: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            level = min(6, len(stripped) - len(stripped.lstrip("#")))
            title = _safe_class_name(stripped.lstrip("#").strip())
            sections.append(
                f'<section class="section-{title}" data-source-heading-level="{level}"></section>'
            )
    body = "".join(sections) or '<section class="note-body" data-slot="body"></section>'
    return f'<article class="imported-note-template">{body}</article>'


def extract_template_from_text(text: str, source_name: str | None = None) -> dict:
    name = _title_from_text(text, source_name)
    skeleton_html = _markdown_to_skeleton(text)
    return {
        "name": name,
        "description": f"从 {source_name or '导入内容'} 提取的笔记模板。",
        "skeleton_html": skeleton_html,
        "style_constraints": copy_default(DEFAULT_STYLE_CONSTRAINTS),
        "rule_config": copy_default(DEFAULT_RULE_CONFIG),
        "example_content": {
            "html": skeleton_html,
            "markdown": f"# {name}\n\n- 这是根据导入模板生成的示例要点。\n",
        },
        "output_formats": ["markdown"],
    }
