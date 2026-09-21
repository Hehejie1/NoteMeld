from __future__ import annotations

import json
import re
from typing import Any

from app.services.note_style_schema import (
    DEFAULT_EXAMPLE_CONTENT,
    DEFAULT_OUTPUT_FORMATS,
    DEFAULT_RULE_CONFIG,
    DEFAULT_STYLE_CONSTRAINTS,
    NoteStylePayload,
    copy_default,
)
from app.services.note_style_example_generator import with_standard_example_content


DEFAULT_SKELETON_HTML = '<article class="imported-note-template"><section class="note-body" data-slot="body"></section></article>'
DEFAULT_ANALYSIS_TIMEOUT = 120
DEFAULT_ANALYSIS_MAX_TOKENS = 2200
EDIT_TEMPLATE_SKELETON_LIMIT = 4000
CREATE_TEMPLATE_SKELETON_LIMIT = 2500
ANALYSIS_CHUNK_LIMIT = 2
ANALYSIS_CHUNK_PREVIEW_LIMIT = 2000


def _extract_json(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    match = re.search(r"\{[\s\S]*\}", text)
    return match.group(0) if match else text


def parse_template_json(raw: str) -> dict[str, Any]:
    data = json.loads(_extract_json(raw))
    return NoteStylePayload(**data).model_dump()


def parse_compact_template_json(raw: str, current_template: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.loads(_extract_json(raw))
    return materialize_template_payload(data, current_template=current_template)


def _trim_text(value: str, limit: int) -> str:
    text = (value or "").strip()
    if len(text) <= limit:
        return text
    return text[:limit].rstrip() + "\n<!-- truncated -->"


def build_compact_template_context(current_template: dict[str, Any] | None) -> dict[str, Any] | None:
    if not current_template:
        return None
    skeleton_limit = EDIT_TEMPLATE_SKELETON_LIMIT if current_template.get("skeleton_html") else CREATE_TEMPLATE_SKELETON_LIMIT
    return {
        "name": (current_template.get("name") or "").strip(),
        "description": (current_template.get("description") or "").strip(),
        "skeleton_html": _trim_text(current_template.get("skeleton_html") or "", skeleton_limit),
        "style_constraints": {"global": (current_template.get("style_constraints") or {}).get("global", {})},
        "rule_config": {"global": (current_template.get("rule_config") or {}).get("global", {})},
        "output_formats": current_template.get("output_formats") or DEFAULT_OUTPUT_FORMATS.copy(),
    }


def _build_analysis_source_excerpt(
    source: dict[str, Any],
    chunks: list[dict[str, Any]],
    user_instruction: str,
    generation_mode: str,
) -> str:
    source_kind = source.get("kind") or ""
    if generation_mode == "edit" and source_kind == "text":
        return user_instruction.strip() or "本次修改没有额外文本材料，仅根据用户要求调整当前模板。"

    chunk_preview = "\n\n".join(
        f"### chunk {chunk['index']}\n{(chunk.get('text') or '')[:ANALYSIS_CHUNK_PREVIEW_LIMIT]}"
        for chunk in chunks[:ANALYSIS_CHUNK_LIMIT]
    )
    return chunk_preview or (source.get("text") or "")[:ANALYSIS_CHUNK_PREVIEW_LIMIT] or "当前来源没有可直接读取文本，请根据文件类型和骨架提示推断。"


def build_template_analysis_request(prompt: str) -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": prompt}],
        "timeout": DEFAULT_ANALYSIS_TIMEOUT,
        "max_tokens": DEFAULT_ANALYSIS_MAX_TOKENS,
    }


def materialize_template_payload(data: dict[str, Any], current_template: dict[str, Any] | None = None) -> dict[str, Any]:
    current_template = current_template or {}
    name = ((data.get("name") or current_template.get("name") or "导入模板").strip() or "导入模板")[:20]
    skeleton_html = (
        data.get("skeleton_html")
        or current_template.get("skeleton_html")
        or DEFAULT_SKELETON_HTML
    )
    existing_example = current_template.get("example_content") or {}
    example_content = copy_default(DEFAULT_EXAMPLE_CONTENT)
    example_content["html"] = (existing_example.get("html") or "").strip() or skeleton_html
    example_content["markdown"] = (existing_example.get("markdown") or "").strip() or f"# {name}\n\n- 这是根据当前模板生成的示例要点。\n"

    payload = {
        "name": name,
        "description": (data.get("description") or current_template.get("description") or "").strip(),
        "skeleton_html": skeleton_html,
        "style_constraints": data.get("style_constraints") or current_template.get("style_constraints") or copy_default(DEFAULT_STYLE_CONSTRAINTS),
        "rule_config": data.get("rule_config") or current_template.get("rule_config") or copy_default(DEFAULT_RULE_CONFIG),
        "example_content": example_content,
        "output_formats": data.get("output_formats") or current_template.get("output_formats") or DEFAULT_OUTPUT_FORMATS.copy(),
    }
    return NoteStylePayload(**with_standard_example_content(payload)).model_dump()


def build_template_analysis_prompt(
    source: dict[str, Any],
    chunks: list[dict[str, Any]],
    user_instruction: str = "",
    current_template: dict[str, Any] | None = None,
    generation_mode: str = "create",
) -> str:
    compact_template = build_compact_template_context(current_template)
    source_excerpt = _build_analysis_source_excerpt(source, chunks, user_instruction, generation_mode)
    warnings = "\n".join(f"- {item}" for item in source.get("warnings", [])) or "- 无"
    current_template_block = (
        json.dumps(compact_template, ensure_ascii=False, indent=2)
        if compact_template
        else "无"
    )
    skeleton_hint = source.get("skeleton_hint", "")
    if compact_template and skeleton_hint == compact_template.get("skeleton_html", ""):
        skeleton_hint = ""
    skeleton_section = (
        f"## 骨架提示\n```html\n{skeleton_hint}\n```"
        if skeleton_hint
        else "## 骨架提示\n- 当前请求未附加额外骨架提示，请以当前模板摘要中的骨架为准。"
    )
    return f"""
你是 NoteMeld 的笔记风格模板分析器。请从导入材料中反推笔记模板，而不是生成普通笔记。

## 输入来源
- kind: {source.get("kind")}
- warnings:
{warnings}

## 用户补充要求
{user_instruction or "无"}

## 当前任务模式
- generation_mode: {generation_mode}
- rule: 如果 generation_mode=edit，必须基于“当前模板”进行增量修改，而不是重新创建全新模板。

## 当前模板
```json
{current_template_block}
```

{skeleton_section}

## 文本/OCR/VLM 分析片段
{source_excerpt}

## 输出要求
只返回紧凑 JSON，不要代码块，不要解释。字段必须是：
- name：不超过 20 个中文字符
- description：一段简介
- skeleton_html：HTML 骨架，保留结构、class、id、data 属性，不包含原文具体文案
- style_constraints：对象，必须包含 global，可包含 CSS selector
- rule_config：对象，必须包含 global
- output_formats：数组，只能包含 html、markdown

不要返回 example_content，案例内容由后端根据当前模板或默认规则补齐。

style_constraints 每个节点建议包含 tone、sentence、visual、forbidden。
rule_config 可以包含 max_heading_depth、list_depth、max_paragraph_chars、punctuation、quote_style 等机器规则。
""".strip()
