from __future__ import annotations

import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any

ALLOWED_DOC_TYPES = {
    "resume",
    "note",
    "article",
    "slide",
    "poster",
    "form",
    "table_sheet",
    "mixed",
}
ALLOWED_LAYOUT_TYPES = {
    "single-column",
    "two-column",
    "free-layout",
    "sidebar-content",
    "hero-sections",
}
ALLOWED_READING_ORDERS = {"top-to-bottom", "left-to-right", "mixed"}
ALLOWED_BLOCK_TYPES = {
    "page_title",
    "heading",
    "subheading",
    "paragraph",
    "bullet_list",
    "numbered_list",
    "checklist",
    "quote",
    "code_block",
    "table",
    "image",
    "diagram",
    "card",
    "callout",
    "divider",
    "footer_note",
}
DEFAULT_STYLE_TOKENS = {
    "text": None,
    "muted": None,
    "accent": None,
    "accent_soft": None,
    "line": None,
    "radius": None,
    "shadow": "none",
    "spacing_density": "comfortable",
    "title_style": "plain",
}
ALLOWED_RENDERER_PROFILES = {
    "resume_professional",
    "note_structured",
    "article_clean",
    "generic_document",
}
DEFAULT_TIMEOUT = 90
DEFAULT_MAX_TOKENS = 2200


def _image_to_data_url(file_path: str) -> str:
    mime_type = mimetypes.guess_type(file_path)[0] or "image/png"
    encoded = base64.b64encode(Path(file_path).read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def _strip_json_fence(raw: str) -> str:
    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, count=1)
        text = re.sub(r"\s*```$", "", text, count=1)
    return text.strip()


def _supports_vision_capability(provider_id: str, model_name: str) -> bool | None:
    from app.db.model_capability_dao import get_model_capability

    row = get_model_capability(provider_id, model_name)
    if not row:
        return None
    return row.get("supports_vision")


def _build_structure_prompt(user_instruction: str) -> str:
    extra_instruction = f"\n补充要求：{user_instruction.strip()}" if user_instruction.strip() else ""
    return (
        "请分析这张文档图片，输出结构语义 JSON，不要生成 HTML，不要输出 markdown 代码块。\n"
        "任务：\n"
        "1. 判断文档类型，只能从 resume/note/article/slide/poster/form/table_sheet/mixed 中选择。\n"
        "2. 判断整体布局，输出 columns、layout_type、reading_order。\n"
        "3. 识别页面主要 block。\n"
        "4. 对每个 block 输出 id、block_type、bbox、text、text_summary、hierarchy_level、parent_block_id、reading_order、confidence。\n"
        "5. block_type 只能从以下通用类型中选择：page_title, heading, subheading, paragraph, bullet_list, numbered_list, checklist, quote, code_block, table, image, diagram, card, callout, divider, footer_note。\n"
        "6. 额外输出 style_tokens，字段必须包含 text, muted, accent, accent_soft, line, radius, shadow, spacing_density, title_style。\n"
        "如果无法确定颜色，可以填 null；如果无法确定 bbox，可以填 null。"
        f"{extra_instruction}"
    )


def _build_typed_semantics_prompt(structure: dict[str, Any], user_instruction: str) -> str:
    extra_instruction = f"\n补充要求：{user_instruction.strip()}" if user_instruction.strip() else ""
    structure_json = json.dumps(
        {
            "doc_type": structure.get("doc_type"),
            "layout": structure.get("layout"),
            "blocks": structure.get("blocks"),
        },
        ensure_ascii=False,
    )


def _build_render_validation_prompt(user_instruction: str) -> str:
    extra_instruction = f"\n补充要求：{user_instruction.strip()}" if user_instruction.strip() else ""
    return (
        "你是文档模板回渲染校验器。第一张图是原始文档图片，第二张图是根据结构 schema 渲染出的预览。"
        "请比较两者，输出 JSON，不要输出 HTML。\n"
        "任务：\n"
        "1. 输出 warnings，描述结构、间距、颜色、标题层级等偏差。\n"
        "2. 输出 applied_corrections，列出建议修正的字段路径，例如 style_tokens.spacing_density。\n"
        "3. 如有必要，可输出 style_tokens 的局部修正值。\n"
        "4. 只能返回 JSON，不要返回 markdown 代码块。"
        f"{extra_instruction}"
    )
    return (
        "你是文档类型解释器。请基于给定的 doc_type、layout 和 blocks，输出类型化语义映射 JSON。"
        "不要生成 HTML，不要修改 block_type。\n"
        "任务：\n"
        "1. 输出 renderer_profile，只能从 resume_professional/note_structured/article_clean/generic_document 中选择。\n"
        "2. 输出 semantic_blocks，每项包含 block_id、semantic_role、semantic_hint。\n"
        "3. 如有不确定，可输出 warnings。\n"
        "输入结构如下：\n"
        f"{structure_json}"
        f"{extra_instruction}"
    )


def _normalize_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, (list, tuple)) or len(value) != 4:
        return None
    try:
        return [float(item) for item in value]
    except (TypeError, ValueError):
        return None


def _normalize_structure_payload(data: dict[str, Any]) -> dict[str, Any]:
    doc_type = str(data.get("doc_type") or "mixed").strip().lower()
    if doc_type not in ALLOWED_DOC_TYPES:
        doc_type = "mixed"

    raw_layout = data.get("layout") if isinstance(data.get("layout"), dict) else {}
    columns = raw_layout.get("columns")
    try:
        columns = int(columns)
    except (TypeError, ValueError):
        columns = 1
    columns = min(3, max(1, columns))

    layout_type = str(raw_layout.get("layout_type") or "single-column").strip().lower()
    if layout_type not in ALLOWED_LAYOUT_TYPES:
        layout_type = "single-column"

    reading_order = str(raw_layout.get("reading_order") or "top-to-bottom").strip().lower()
    if reading_order not in ALLOWED_READING_ORDERS:
        reading_order = "top-to-bottom"

    blocks: list[dict[str, Any]] = []
    for index, block in enumerate(data.get("blocks") or []):
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("block_type") or "paragraph").strip().lower()
        if block_type not in ALLOWED_BLOCK_TYPES:
            block_type = "paragraph"
        blocks.append(
            {
                "id": str(block.get("id") or f"block-{index}"),
                "block_type": block_type,
                "bbox": _normalize_bbox(block.get("bbox")),
                "text": str(block.get("text") or "").strip(),
                "text_summary": str(block.get("text_summary") or "").strip(),
                "hierarchy_level": int(block.get("hierarchy_level") or 0),
                "parent_block_id": block.get("parent_block_id"),
                "reading_order": int(block.get("reading_order") or index),
                "confidence": block.get("confidence"),
            }
        )
    if not blocks:
        blocks.append(
            {
                "id": "block-0",
                "block_type": "paragraph",
                "bbox": None,
                "text": "",
                "text_summary": "文档内容",
                "hierarchy_level": 0,
                "parent_block_id": None,
                "reading_order": 0,
                "confidence": None,
            }
        )

    style_tokens = {**DEFAULT_STYLE_TOKENS}
    for key, default_value in DEFAULT_STYLE_TOKENS.items():
        value = (data.get("style_tokens") or {}).get(key)
        style_tokens[key] = default_value if value in {"", []} else value

    warnings = [str(item).strip() for item in (data.get("warnings") or []) if str(item).strip()]
    return {
        "doc_type": doc_type,
        "layout": {
            "columns": columns,
            "layout_type": layout_type,
            "reading_order": reading_order,
        },
        "blocks": blocks,
        "style_tokens": style_tokens,
        "warnings": warnings,
    }


def _normalize_typed_semantics_payload(
    data: dict[str, Any], structure: dict[str, Any]
) -> dict[str, Any]:
    renderer_profile = str(data.get("renderer_profile") or "generic_document").strip()
    if renderer_profile not in ALLOWED_RENDERER_PROFILES:
        renderer_profile = "generic_document"
    block_ids = {str(block.get("id")) for block in (structure.get("blocks") or [])}
    semantic_blocks: list[dict[str, Any]] = []
    for index, item in enumerate(data.get("semantic_blocks") or []):
        if not isinstance(item, dict):
            continue
        block_id = str(item.get("block_id") or "")
        if block_id not in block_ids:
            continue
        semantic_blocks.append(
            {
                "block_id": block_id,
                "semantic_role": str(item.get("semantic_role") or "generic_block").strip() or "generic_block",
                "semantic_hint": str(item.get("semantic_hint") or "").strip(),
            }
        )
    if not semantic_blocks:
        semantic_blocks = [
            {
                "block_id": str(block.get("id") or f"block-{index}"),
                "semantic_role": "generic_block",
                "semantic_hint": str(block.get("text_summary") or block.get("text") or "").strip(),
            }
            for index, block in enumerate(structure.get("blocks") or [])
        ]
    warnings = [str(item).strip() for item in (data.get("warnings") or []) if str(item).strip()]
    return {
        "renderer_profile": renderer_profile,
        "semantic_blocks": semantic_blocks,
        "warnings": warnings,
    }


def analyze_image_with_vlm(
    *,
    file_path: str,
    provider_id: str,
    model_name: str,
    user_instruction: str = "",
) -> dict[str, Any]:
    if not provider_id or not model_name:
        raise ValueError("图片导入需要选择支持图片理解的模型")
    vision_support = _supports_vision_capability(provider_id, model_name)
    if vision_support is False:
        raise ValueError("当前模型不支持图片理解，请更换视觉模型")

    from app.services.note import NoteGenerator

    gpt = NoteGenerator()._get_gpt(model_name, provider_id)
    response = gpt.create_chat_completion(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_structure_prompt(user_instruction)},
                    {"type": "image_url", "image_url": {"url": _image_to_data_url(file_path)}},
                ],
            }
        ],
        phase_label="图片结构分析",
        request_meta={"stage": "note_style_image_vlm"},
        timeout=DEFAULT_TIMEOUT,
        max_tokens=DEFAULT_MAX_TOKENS,
    )
    content = gpt._extract_message_content(response, "图片结构分析")
    payload = json.loads(_strip_json_fence(content))
    if not isinstance(payload, dict):
        raise ValueError("图片结构分析结果格式无效")
    return _normalize_structure_payload(payload)


def analyze_typed_semantics_with_vlm(
    *,
    provider_id: str,
    model_name: str,
    structure: dict[str, Any],
    user_instruction: str = "",
) -> dict[str, Any]:
    if not provider_id or not model_name:
        raise ValueError("语义解释需要选择模型")

    from app.services.note import NoteGenerator

    gpt = NoteGenerator()._get_gpt(model_name, provider_id)
    response = gpt.create_chat_completion(
        messages=[
            {
                "role": "user",
                "content": _build_typed_semantics_prompt(structure, user_instruction),
            }
        ],
        phase_label="图片语义解释",
        request_meta={"stage": "note_style_image_semantics_vlm"},
        timeout=DEFAULT_TIMEOUT,
        max_tokens=DEFAULT_MAX_TOKENS,
    )
    content = gpt._extract_message_content(response, "图片语义解释")
    payload = json.loads(_strip_json_fence(content))
    if not isinstance(payload, dict):
        raise ValueError("图片语义解释结果格式无效")
    return _normalize_typed_semantics_payload(payload, structure)


def validate_rendered_template_with_vlm(
    *,
    provider_id: str,
    model_name: str,
    original_image_path: str,
    render_preview_path: str,
    user_instruction: str = "",
) -> dict[str, Any]:
    if not provider_id or not model_name:
        raise ValueError("回渲染校验需要选择模型")

    from app.services.note import NoteGenerator

    gpt = NoteGenerator()._get_gpt(model_name, provider_id)
    response = gpt.create_chat_completion(
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": _build_render_validation_prompt(user_instruction)},
                    {"type": "image_url", "image_url": {"url": _image_to_data_url(original_image_path)}},
                    {"type": "image_url", "image_url": {"url": _image_to_data_url(render_preview_path)}},
                ],
            }
        ],
        phase_label="图片回渲染校验",
        request_meta={"stage": "note_style_render_validation_vlm"},
        timeout=DEFAULT_TIMEOUT,
        max_tokens=DEFAULT_MAX_TOKENS,
    )
    content = gpt._extract_message_content(response, "图片回渲染校验")
    payload = json.loads(_strip_json_fence(content))
    if not isinstance(payload, dict):
        raise ValueError("图片回渲染校验结果格式无效")
    warnings = [str(item).strip() for item in (payload.get("warnings") or []) if str(item).strip()]
    applied_corrections = [
        str(item).strip() for item in (payload.get("applied_corrections") or []) if str(item).strip()
    ]
    token_corrections = payload.get("token_corrections") if isinstance(payload.get("token_corrections"), dict) else {}
    if not token_corrections and isinstance(payload.get("style_tokens"), dict):
        token_corrections = payload.get("style_tokens") or {}
    layout_corrections = payload.get("layout_corrections") if isinstance(payload.get("layout_corrections"), dict) else {}
    block_corrections = payload.get("block_corrections") if isinstance(payload.get("block_corrections"), list) else []
    return {
        "warnings": warnings,
        "token_corrections": token_corrections,
        "layout_corrections": layout_corrections,
        "block_corrections": block_corrections,
        "applied_corrections": applied_corrections,
        "render_preview_path": render_preview_path,
    }
