from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from typing import Any, List, Optional

from sqlalchemy import inspect, text
from sqlalchemy.orm import Session

from app.db.engine import engine, get_db
from app.db.models.note_style import NoteStyle
from app.services.note_style_schema import (
    DEFAULT_EXAMPLE_CONTENT,
    DEFAULT_OUTPUT_FORMATS,
    DEFAULT_RULE_CONFIG,
    DEFAULT_STYLE_CONSTRAINTS,
    NoteStylePayload,
    copy_default,
    selector_warnings,
)
from app.services.note_style_example_generator import generate_style_example_content
from app.utils.logger import get_logger

logger = get_logger(__name__)


def _builtin_skeleton(title: str) -> str:
    return (
        f'<article class="notemeld-note-style" data-template-title="{title}">'
        '<header class="note-summary" data-slot="summary"></header>'
        '<section class="note-body" data-slot="body"></section>'
        '<section class="note-actions" data-slot="actions"></section>'
        "</article>"
    )


def _sectioned_skeleton(title: str, sections: list[str]) -> str:
    body = "".join(
        f'<section class="note-section" data-slot="{index}"><h2>{section}</h2></section>'
        for index, section in enumerate(sections, start=1)
    )
    return (
        f'<article class="notemeld-note-style" data-template-title="{title}">'
        f'<header class="note-summary" data-slot="summary"><h1>{title}</h1></header>'
        f'{body}'
        "</article>"
    )


def _style(tone: str, sentence: str, visual: str, forbidden: list[str] | None = None) -> dict[str, Any]:
    return {
        "global": {
            "tone": tone,
            "sentence": sentence,
            "visual": visual,
            "forbidden": forbidden or [],
        }
    }


BUILTIN_STYLES: List[dict[str, Any]] = [
    {
        "id": "knowledge_card",
        "name": "知识卡片",
        "description": "默认风格，适合把视频、网页、语音、AI 对话整理成可回顾、可检索、可复用的知识资产。",
        "skeleton_html": _sectioned_skeleton(
            "知识卡片",
            ["核心结论", "关键发现", "知识整理", "可执行建议", "待追问"],
        ),
        "style_constraints": _style(
            "清晰、克制、知识化、结论先行",
            "短中句优先，每段只表达一个重点，避免口水化复述",
            "标题层级清晰，列表适度，保留可检索关键词",
            ["过度营销", "标题党", "空泛鸡汤", "强行总结行动项"],
        ),
        "rule_config": {
            "global": {
                "must_include": ["核心结论", "关键发现"],
                "optional_include": ["知识整理", "可执行建议", "待追问"],
                "max_heading_depth": 3,
                "max_paragraph_chars": 180,
            }
        },
    },
    {
        "id": "deep_research",
        "name": "深度研究",
        "description": "尽量完整记录视频、网页和文档内容，适合学习存档与深度研究。",
        "skeleton_html": _sectioned_skeleton(
            "深度研究",
            ["研究摘要", "背景与问题", "核心观点", "证据与案例", "延伸问题"],
        ),
        "style_constraints": _style("完整、清晰、解释充分", "允许中长句，但需要逻辑连接", "标题层级完整，保留论据和例子"),
        "rule_config": {"global": {"max_heading_depth": 4, "max_paragraph_chars": 240}},
    },
    {
        "id": "quick_summary",
        "name": "快速摘要",
        "description": "只保留结论、关键点和少量背景，适合快速回顾或临时备忘。",
        "skeleton_html": _sectioned_skeleton("快速摘要", ["一句话结论", "关键要点", "值得保留"]),
        "style_constraints": _style("直接、克制、结论先行", "短句优先，每段只表达一个重点", "列表密度高，减少装饰"),
        "rule_config": {"global": {"max_items": 5, "max_heading_depth": 2}},
    },
    {
        "id": "action_list",
        "name": "行动清单",
        "description": "把教程、项目规划、方法论转化为下一步行动，突出任务、验收标准和风险。",
        "skeleton_html": _sectioned_skeleton("行动清单", ["目标", "行动项", "验收标准", "风险与注意事项"]),
        "style_constraints": _style("目标明确、行动导向、可验收", "使用动词开头，避免抽象表述", "清单化展示，突出负责人、截止时间和验收标准"),
        "rule_config": {"global": {"must_include": ["行动项", "验收标准"], "list_depth": 2}},
    },
    {
        "id": "meeting_minutes",
        "name": "会议纪要",
        "description": "参会人、议题、决议与待办，结构化呈现。",
        "skeleton_html": _sectioned_skeleton("会议纪要", ["会议概览", "议题讨论", "决议", "行动项"]),
        "style_constraints": _style("客观、中立、记录准确", "短句记录事实，决议和待办分开", "固定分区展示参会人、议题、决议和行动项"),
        "rule_config": {"global": {"must_include": ["议题", "决议", "行动项"], "max_heading_depth": 3}},
    },
    {
        "id": "video_analysis",
        "name": "视频解析",
        "description": "面向视频内容，融合标题、字幕、画面、评论和弹幕线索，适合复盘观点与案例。",
        "skeleton_html": _sectioned_skeleton("视频解析", ["视频主旨", "关键片段", "画面与语境", "评论与弹幕线索", "个人知识沉淀"]),
        "style_constraints": _style("分析型、客观、抓重点", "先概括观点，再补充画面或语境证据", "按片段和主题组织，避免逐字复述"),
        "rule_config": {"global": {"must_include": ["视频主旨", "关键片段"], "max_heading_depth": 3}},
    },
    {
        "id": "web_digest",
        "name": "网页提炼",
        "description": "面向网页、博客、文档和资讯，提炼页面观点、引用线索与可追踪来源。",
        "skeleton_html": _sectioned_skeleton("网页提炼", ["页面摘要", "核心观点", "引用与链接线索", "适合沉淀的知识点"]),
        "style_constraints": _style("准确、可追踪、去噪", "保留页面中的关键术语和来源线索", "突出观点来源，弱化导航和广告信息"),
        "rule_config": {"global": {"must_include": ["页面摘要", "核心观点"], "citation_policy": "保留来源和链接线索"}},
    },
    {
        "id": "tool_website",
        "name": "工具网站",
        "description": "面向工具型网站，记录网站链接、可解决的问题、适用场景、使用限制和推荐触发词，方便后续按任务召回。",
        "skeleton_html": _sectioned_skeleton(
            "工具网站",
            ["原始链接", "它能做什么", "适合什么时候用", "不适合什么", "使用限制", "推荐触发词", "推荐使用方式"],
        ),
        "style_constraints": _style(
            "客观、简洁、任务召回导向",
            "用短句描述能力和适用任务，避免把官网营销语当结论",
            "以能力、场景、限制和触发词组织，保留可点击原始链接",
            ["泛泛介绍公司", "照搬官网口号", "夸大工具能力", "把工具网站写成资讯摘要"],
        ),
        "rule_config": {
            "global": {
                "must_include": ["原始链接", "它能做什么", "适合什么时候用", "推荐触发词"],
                "optional_include": ["不适合什么", "使用限制", "推荐使用方式"],
                "source_url_policy": "必须保留工具网站链接，便于召回后打开原站",
                "recommendation_policy": "触发词应覆盖用户可能说出的任务意图，而不是只写网站品牌词",
                "max_heading_depth": 3,
                "max_paragraph_chars": 160,
            }
        },
    },
    {
        "id": "ai_conversation",
        "name": "AI 对话沉淀",
        "description": "面向 ChatGPT、Claude、MCP 等 AI 对话记录，沉淀问题、决策、方案和后续任务。",
        "skeleton_html": _sectioned_skeleton("AI 对话沉淀", ["问题背景", "关键决策", "方案沉淀", "待执行任务", "可复用提示"]),
        "style_constraints": _style("结构化、决策导向、可复用", "区分用户目标、AI 建议和最终决策", "保留可复用方法、提示词和任务拆解"),
        "rule_config": {"global": {"must_include": ["问题背景", "关键决策", "方案沉淀"], "max_heading_depth": 3}},
    },
]


LEGACY_BUILTIN_STYLE_ALIASES = {
    "minimal": "quick_summary",
    "detailed": "deep_research",
    "tutorial": "action_list",
    "academic": "deep_research",
    "xiaohongshu": "knowledge_card",
    "life_journal": "knowledge_card",
    "task_oriented": "action_list",
    "business": "deep_research",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_loads(value: str | None, fallback: Any) -> Any:
    if not value:
        return copy_default(fallback)
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return copy_default(fallback)


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _generated_example_for_payload(payload: NoteStylePayload) -> dict[str, str]:
    return generate_style_example_content(
        {
            "name": payload.name,
            "description": payload.description,
            "skeleton_html": payload.skeleton_html,
            "style_constraints": payload.style_constraints,
            "rule_config": payload.rule_config,
            "output_formats": payload.output_formats,
        }
    )


def ensure_note_style_columns() -> None:
    inspector = inspect(engine)
    if "note_styles" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("note_styles")}
    migrations = {
        "skeleton_html": "ALTER TABLE note_styles ADD COLUMN skeleton_html TEXT NOT NULL DEFAULT ''",
        "style_constraints": "ALTER TABLE note_styles ADD COLUMN style_constraints TEXT NOT NULL DEFAULT '{}'",
        "rule_config": "ALTER TABLE note_styles ADD COLUMN rule_config TEXT NOT NULL DEFAULT '{}'",
        "example_content": "ALTER TABLE note_styles ADD COLUMN example_content TEXT NOT NULL DEFAULT '{}'",
        "output_formats": "ALTER TABLE note_styles ADD COLUMN output_formats TEXT NOT NULL DEFAULT '[\"markdown\"]'",
    }
    with engine.begin() as conn:
        for column, statement in migrations.items():
            if column not in columns:
                conn.execute(text(statement))


def _to_dict(model: NoteStyle) -> dict:
    data = {
        "id": model.id,
        "name": model.name,
        "description": model.description or "",
        "skeleton_html": model.skeleton_html or "",
        "style_constraints": _json_loads(model.style_constraints, DEFAULT_STYLE_CONSTRAINTS),
        "rule_config": _json_loads(model.rule_config, DEFAULT_RULE_CONFIG),
        "example_content": _json_loads(model.example_content, DEFAULT_EXAMPLE_CONTENT),
        "output_formats": _json_loads(model.output_formats, DEFAULT_OUTPUT_FORMATS),
        "builtin": False,
        "created_at": model.created_at.isoformat() if model.created_at else None,
        "updated_at": model.updated_at.isoformat() if model.updated_at else None,
    }
    data["selector_warnings"] = selector_warnings(
        data["skeleton_html"],
        data["style_constraints"],
        data["rule_config"],
    )
    return data


def _builtin_dict(item: dict) -> dict:
    data = {
        "id": item["id"],
        "name": item["name"],
        "description": item["description"],
        "skeleton_html": item["skeleton_html"],
        "style_constraints": item.get("style_constraints") or copy_default(DEFAULT_STYLE_CONSTRAINTS),
        "rule_config": item.get("rule_config") or copy_default(DEFAULT_RULE_CONFIG),
        "example_content": item.get("example_content") or copy_default(DEFAULT_EXAMPLE_CONTENT),
        "output_formats": item.get("output_formats") or DEFAULT_OUTPUT_FORMATS.copy(),
        "builtin": True,
        "created_at": None,
        "updated_at": None,
    }
    data["example_content"] = generate_style_example_content(data)
    data["selector_warnings"] = selector_warnings(
        data["skeleton_html"],
        data["style_constraints"],
        data["rule_config"],
    )
    return data


def list_styles() -> List[dict]:
    ensure_note_style_columns()
    db: Session = next(get_db())
    try:
        rows = db.query(NoteStyle).order_by(NoteStyle.created_at.desc()).all()
        custom = [_to_dict(r) for r in rows]
        builtin = [_builtin_dict(item) for item in BUILTIN_STYLES]
        return builtin + custom
    finally:
        db.close()


def get_style_template(style_id: str) -> Optional[dict]:
    style_id = LEGACY_BUILTIN_STYLE_ALIASES.get(style_id, style_id)
    for item in BUILTIN_STYLES:
        if item["id"] == style_id:
            return _builtin_dict(item)
    ensure_note_style_columns()
    db: Session = next(get_db())
    try:
        row = db.query(NoteStyle).filter_by(id=style_id).first()
        return _to_dict(row) if row else None
    finally:
        db.close()


def get_style_prompt(style_id: str) -> Optional[str]:
    template = get_style_template(style_id)
    if not template:
        return None
    return json.dumps(template, ensure_ascii=False)


def create_style(payload: NoteStylePayload) -> dict:
    ensure_note_style_columns()
    db: Session = next(get_db())
    try:
        style = NoteStyle(
            id=str(uuid.uuid4()),
            name=payload.name.strip(),
            description=(payload.description or "").strip(),
            skeleton_html=payload.skeleton_html.strip(),
            style_constraints=_json_dumps(payload.style_constraints),
            rule_config=_json_dumps(payload.rule_config),
            example_content=_json_dumps(_generated_example_for_payload(payload)),
            output_formats=_json_dumps(payload.output_formats),
            builtin=0,
        )
        db.add(style)
        db.commit()
        db.refresh(style)
        return _to_dict(style)
    finally:
        db.close()


def update_style(style_id: str, payload: NoteStylePayload) -> Optional[dict]:
    if any(item["id"] == style_id for item in BUILTIN_STYLES):
        raise ValueError("内置风格模板不允许编辑")
    ensure_note_style_columns()
    db: Session = next(get_db())
    try:
        row = db.query(NoteStyle).filter_by(id=style_id).first()
        if not row:
            return None
        row.name = payload.name.strip()
        row.description = (payload.description or "").strip()
        row.skeleton_html = payload.skeleton_html.strip()
        row.style_constraints = _json_dumps(payload.style_constraints)
        row.rule_config = _json_dumps(payload.rule_config)
        row.example_content = _json_dumps(_generated_example_for_payload(payload))
        row.output_formats = _json_dumps(payload.output_formats)
        db.commit()
        db.refresh(row)
        return _to_dict(row)
    finally:
        db.close()


def delete_style(style_id: str) -> bool:
    if any(item["id"] == style_id for item in BUILTIN_STYLES):
        raise ValueError("内置风格模板不允许删除")
    ensure_note_style_columns()
    db: Session = next(get_db())
    try:
        row = db.query(NoteStyle).filter_by(id=style_id).first()
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True
    finally:
        db.close()
