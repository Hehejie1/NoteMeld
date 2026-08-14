"""P3-T2: 三层记忆 + transform_context 注入 + AgentTool。

三层记忆结构::

    层级 1（用户级）：     <data_dir>/note_results/memory/user_profile.json
        全局用户画像：兴趣、领域、习惯、长期偏好。

    层级 2（研究空间级）：<data_dir>/note_results/memory/research_spaces/{rs_id}.json
        某研究主题下的目标、产出、关键事实、masteries（领域熟练度）。

    层级 3（会话级）：    复用 conversation_messages（不重复造轮子）

设计要点：
- 容错：JSON 损坏 → 读取空默认 + 备份原文件到 ``*.corrupted-{ts}.json`` + warning log。
- masteries > 1000 条时截断 Top-20（按 score 降序）。
- ``build_system_prefix``：拼装 system prompt 前缀，供 hook 注入。
- AgentTool ``update_user_profile`` / ``manage_research_space``：Agent 主动维护记忆。
- 会话-研究空间绑定：``research_space_id`` 存 ``conversations.research_space_id`` 列
  （P3 阶段二新增），由上层业务 ``conversation_store`` 读写；本模块只负责文件读写与注入。
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from app.agent.core.signal import AbortSignal
from app.agent.core.tool import AgentTool, ToolResult
from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: masteries 最多保留条数（Top-N）。
MASTERIES_TOP_N = 20

#: research_space_id 必须匹配的安全字符。
_RS_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")


# ---------------------------------------------------------------------------
# 文件路径
# ---------------------------------------------------------------------------

def memory_root() -> Path:
    """记忆根目录：``<note_output_dir>/memory``。"""
    return (note_output_dir() / "memory").resolve()


def user_profile_path() -> Path:
    return (memory_root() / "user_profile.json").resolve()


def research_spaces_dir() -> Path:
    return (memory_root() / "research_spaces").resolve()


def research_space_path(rs_id: str) -> Path:
    """单个研究空间记忆文件路径。"""
    if not _RS_ID_RE.match(rs_id or ""):
        raise ValueError(f"非法 research_space_id: {rs_id!r}")
    return (research_spaces_dir() / f"{rs_id}.json").resolve()


# ---------------------------------------------------------------------------
# 默认结构
# ---------------------------------------------------------------------------

def _default_user_profile() -> dict:
    return {
        "version": 1,
        "display_name": "",
        "interests": [],          # [{"topic", "weight"}]
        "domains": [],            # [{"name", "level"}]
        "preferences": {},        # 任意键值
        "masteries": [],          # [{"subject", "score", "updated_at"}]
        "updated_at": "",
    }


def _default_research_space() -> dict:
    return {
        "version": 1,
        "rs_id": "",
        "title": "",
        "goal": "",
        "key_facts": [],          # [{"text", "source", "updated_at"}]
        "open_questions": [],     # [{"text", "raised_at"}]
        "outputs": [],            # [{"kind","ref","updated_at"}]
        "masteries": [],          # [{"subject","score","updated_at"}]
        "created_at": "",
        "updated_at": "",
    }


# ---------------------------------------------------------------------------
# 读写：容错 + 原子写
# ---------------------------------------------------------------------------

def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _read_json_safe(path: Path, default_factory) -> dict:
    """安全读取 JSON：损坏 → 默认值 + 备份原文件。"""
    if not path.exists():
        return default_factory()
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("not a dict")
        return payload
    except Exception as exc:
        # 备份损坏文件
        ts = time.strftime("%Y%m%d-%H%M%S", time.gmtime())
        backup = path.with_suffix(f".corrupted-{ts}.json")
        try:
            backup.write_bytes(path.read_bytes())
        except Exception as backup_exc:  # noqa: BLE001
            logger.error("备份损坏记忆文件失败 %s: %s", backup, backup_exc)
        logger.warning(
            "记忆文件损坏，已备份并使用默认值: %s (err=%s)", path, exc
        )
        return default_factory()


def _write_json_atomic(path: Path, payload: dict) -> None:
    """原子写：临时文件 + replace。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


# ---------------------------------------------------------------------------
# MemoryManager
# ---------------------------------------------------------------------------

@dataclass
class MemoryManager:
    """三层记忆管理器。

    所有方法均为同步（文件 IO），上层调用可通过 ``asyncio.to_thread`` 包装。
    """

    def load_user_profile(self) -> dict:
        payload = _read_json_safe(user_profile_path(), _default_user_profile)
        return _normalize_user_profile(payload)

    def save_user_profile(self, data: dict) -> dict:
        normalized = _normalize_user_profile({**self.load_user_profile(), **data})
        normalized["updated_at"] = _now_iso()
        _truncate_masteries_in_place(normalized["masteries"])
        _write_json_atomic(user_profile_path(), normalized)
        return normalized

    def load_research_space(self, rs_id: str) -> dict:
        if not rs_id:
            raise ValueError("rs_id 不能为空")
        path = research_space_path(rs_id)
        payload = _read_json_safe(path, _default_research_space)
        return _normalize_research_space(payload, rs_id)

    def save_research_space(self, rs_id: str, data: dict) -> dict:
        if not rs_id:
            raise ValueError("rs_id 不能为空")
        existing = self.load_research_space(rs_id)
        merged = {**existing, **data}
        normalized = _normalize_research_space(merged, rs_id)
        normalized["updated_at"] = _now_iso()
        if not normalized["created_at"]:
            normalized["created_at"] = normalized["updated_at"]
        _truncate_masteries_in_place(normalized["masteries"])
        _write_json_atomic(research_space_path(rs_id), normalized)
        return normalized

    # ------------------------------------------------------------------ #
    # system prompt 注入
    # ------------------------------------------------------------------ #
    def build_system_prefix(self, rs_id: Optional[str] = None) -> str:
        """拼装 system prompt 前缀，供 hook 注入到 messages 列表头部。"""
        parts: list[str] = []

        profile = self.load_user_profile()
        if profile.get("display_name") or profile.get("interests") or profile.get("domains"):
            parts.append(self._format_user_profile(profile))

        if rs_id:
            try:
                rs = self.load_research_space(rs_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("load research space %s 失败: %s", rs_id, exc)
                rs = _default_research_space()
            if rs.get("title") or rs.get("goal") or rs.get("key_facts") or rs.get("open_questions"):
                parts.append(self._format_research_space(rs))

        if not parts:
            return ""
        return "# 长期记忆\n\n" + "\n\n".join(parts) + "\n\n---\n\n"

    # ------------------------------------------------------------------ #
    # 格式化助手
    # ------------------------------------------------------------------ #
    @staticmethod
    def _format_user_profile(profile: dict) -> str:
        lines = ["## 用户画像"]
        if profile.get("display_name"):
            lines.append(f"- 名称: {profile['display_name']}")
        interests = profile.get("interests") or []
        if interests:
            items = ", ".join(
                f"{it.get('topic','')}({it.get('weight','')})" for it in interests[:10]
            )
            lines.append(f"- 兴趣: {items}")
        domains = profile.get("domains") or []
        if domains:
            items = ", ".join(
                f"{d.get('name','')}({d.get('level','')})" for d in domains[:10]
            )
            lines.append(f"- 领域: {items}")
        masteries = profile.get("masteries") or []
        if masteries:
            items = ", ".join(
                f"{m.get('subject','')}={m.get('score','')}" for m in masteries[:10]
            )
            lines.append(f"- 熟练度: {items}")
        prefs = profile.get("preferences") or {}
        if prefs:
            items = ", ".join(f"{k}={v}" for k, v in list(prefs.items())[:10])
            lines.append(f"- 偏好: {items}")
        return "\n".join(lines)

    @staticmethod
    def _format_research_space(rs: dict) -> str:
        lines = [f"## 研究空间: {rs.get('title') or rs.get('rs_id','')}"]
        if rs.get("goal"):
            lines.append(f"- 目标: {rs['goal']}")
        facts = rs.get("key_facts") or []
        if facts:
            lines.append("- 关键事实:")
            for f in facts[:10]:
                lines.append(f"  - {f.get('text','')}")
        questions = rs.get("open_questions") or []
        if questions:
            lines.append("- 待回答问题:")
            for q in questions[:5]:
                lines.append(f"  - {q.get('text','')}")
        outputs = rs.get("outputs") or []
        if outputs:
            lines.append("- 已产出:")
            for o in outputs[:5]:
                lines.append(f"  - {o.get('kind','')}: {o.get('ref','')}")
        masteries = rs.get("masteries") or []
        if masteries:
            items = ", ".join(
                f"{m.get('subject','')}={m.get('score','')}" for m in masteries[:10]
            )
            lines.append(f"- 主题熟练度: {items}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# 归一化 + masteries 截断
# ---------------------------------------------------------------------------

def _normalize_user_profile(payload: dict) -> dict:
    base = _default_user_profile()
    base.update({k: v for k, v in payload.items() if k in base})
    if not isinstance(base["interests"], list):
        base["interests"] = []
    if not isinstance(base["domains"], list):
        base["domains"] = []
    if not isinstance(base["masteries"], list):
        base["masteries"] = []
    if not isinstance(base["preferences"], dict):
        base["preferences"] = {}
    _truncate_masteries_in_place(base["masteries"])
    return base


def _normalize_research_space(payload: dict, rs_id: str) -> dict:
    base = _default_research_space()
    base.update({k: v for k, v in payload.items() if k in base})
    base["rs_id"] = rs_id
    for key in ("key_facts", "open_questions", "outputs", "masteries"):
        if not isinstance(base[key], list):
            base[key] = []
    _truncate_masteries_in_place(base["masteries"])
    return base


def _truncate_masteries_in_place(masteries: list) -> None:
    """masteries > MASTERIES_TOP_N 时按 score 降序截断 Top-N。"""
    if len(masteries) <= MASTERIES_TOP_N:
        return
    try:
        masteries.sort(key=lambda m: float(m.get("score", 0)), reverse=True)
    except (TypeError, ValueError):
        pass
    del masteries[MASTERIES_TOP_N:]


# ---------------------------------------------------------------------------
# transform_context 注入 hook
# ---------------------------------------------------------------------------

@dataclass
class MemoryContextHook:
    """把 memory ``build_system_prefix`` 输出注入到 system prompt 前。

    使用方式：传入 ``ChatContextHooks`` 或自定义 hooks 的 ``transform_context``，
    将记忆前缀拼到 system 消息前面。本 Hook 仅做前缀拼接，不替换既有 system。
    """

    manager: MemoryManager
    rs_id: Optional[str] = None
    prefix: str = ""

    def __post_init__(self) -> None:
        if not self.prefix:
            try:
                self.prefix = self.manager.build_system_prefix(self.rs_id)
            except Exception as exc:  # noqa: BLE001
                logger.warning("memory prefix build 失败: %s", exc)
                self.prefix = ""

    def transform_context(self, messages, signal):  # noqa: ARG002
        if not self.prefix:
            return list(messages)
        from app.agent.core.message import AgentMessage
        out = list(messages)
        if out and out[0].role == "system":
            merged = AgentMessage(
                role="system",
                content=self.prefix + (out[0].content if isinstance(out[0].content, str) else ""),
            )
            out[0] = merged
        else:
            out.insert(0, AgentMessage(role="system", content=self.prefix))
        return out


def build_memory_hook(rs_id: Optional[str] = None) -> MemoryContextHook:
    """构造记忆注入 Hook（在 chat_adapter 之外叠加使用）。"""
    return MemoryContextHook(manager=MemoryManager(), rs_id=rs_id)


# ---------------------------------------------------------------------------
# AgentTool: update_user_profile / manage_research_space
# ---------------------------------------------------------------------------

_UPDATE_USER_PROFILE_PARAMS: dict = {
    "type": "object",
    "properties": {
        "display_name": {"type": "string", "description": "用户显示名"},
        "interests": {
            "type": "array",
            "description": "兴趣列表，每项 {topic, weight}",
            "items": {"type": "object"},
        },
        "domains": {
            "type": "array",
            "description": "领域列表，每项 {name, level}",
            "items": {"type": "object"},
        },
        "preferences": {
            "type": "object",
            "description": "偏好键值对",
        },
        "masteries": {
            "type": "array",
            "description": "熟练度列表，每项 {subject, score}。score 越高越熟练。",
            "items": {"type": "object"},
        },
    },
    "required": [],
}

_MANAGE_RESEARCH_SPACE_PARAMS: dict = {
    "type": "object",
    "properties": {
        "rs_id": {"type": "string", "description": "研究空间 id；不存在则创建"},
        "action": {
            "type": "string",
            "enum": ["upsert", "add_fact", "add_question", "add_output", "add_mastery", "delete"],
            "description": "操作类型",
        },
        "title": {"type": "string", "description": "标题（upsert）"},
        "goal": {"type": "string", "description": "目标（upsert）"},
        "fact": {"type": "object", "description": "key_fact 项（add_fact）"},
        "question": {"type": "object", "description": "open_question 项（add_question）"},
        "output": {"type": "object", "description": "output 项（add_output）"},
        "mastery": {"type": "object", "description": "mastery 项（add_mastery）"},
    },
    "required": ["rs_id", "action"],
}


def create_memory_tools() -> list[AgentTool]:
    """构造记忆两个 AgentTool。"""
    return [_build_update_user_profile(), _build_manage_research_space()]


def _build_update_user_profile() -> AgentTool:
    manager = MemoryManager()

    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        # 只取允许的字段，忽略其他
        patch: dict = {}
        for k in ("display_name", "interests", "domains", "preferences", "masteries"):
            if k in params:
                patch[k] = params[k]
        try:
            saved = await asyncio.to_thread(manager.save_user_profile, patch)
        except Exception as exc:  # noqa: BLE001
            return _error_result(call_id, f"保存用户画像失败: {exc}")
        return _text_result(call_id, json.dumps(saved, ensure_ascii=False))

    return AgentTool(
        name="update_user_profile",
        description=(
            "更新全局用户画像记忆。可更新 display_name/interests/domains/preferences/masteries。"
            "传入字段会与已有画像合并；masteries 超过 20 条时按 score 降序截断。"
        ),
        parameters=_UPDATE_USER_PROFILE_PARAMS,
        execution_mode="serial",
        execute=execute,
    )


def _build_manage_research_space() -> AgentTool:
    manager = MemoryManager()

    async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
        rs_id = str(params.get("rs_id") or "").strip()
        action = str(params.get("action") or "").strip()
        if not rs_id or not action:
            return _error_result(call_id, "rs_id 和 action 必填")

        try:
            if action == "delete":
                path = research_space_path(rs_id)
                if path.exists():
                    path.unlink()
                return _text_result(call_id, json.dumps({"rs_id": rs_id, "deleted": True}, ensure_ascii=False))

            if action == "upsert":
                patch: dict = {}
                for k in ("title", "goal"):
                    if k in params:
                        patch[k] = params[k]
                saved = await asyncio.to_thread(manager.save_research_space, rs_id, patch)
                return _text_result(call_id, json.dumps(saved, ensure_ascii=False))

            existing = await asyncio.to_thread(manager.load_research_space, rs_id)
            now = _now_iso()
            if action == "add_fact":
                item = params.get("fact") or {}
                if not isinstance(item, dict) or not item.get("text"):
                    return _error_result(call_id, "fact.text 必填")
                item.setdefault("updated_at", now)
                existing["key_facts"].append(item)
            elif action == "add_question":
                item = params.get("question") or {}
                if not isinstance(item, dict) or not item.get("text"):
                    return _error_result(call_id, "question.text 必填")
                item.setdefault("raised_at", now)
                existing["open_questions"].append(item)
            elif action == "add_output":
                item = params.get("output") or {}
                if not isinstance(item, dict) or not item.get("kind") or not item.get("ref"):
                    return _error_result(call_id, "output.kind / output.ref 必填")
                item.setdefault("updated_at", now)
                existing["outputs"].append(item)
            elif action == "add_mastery":
                item = params.get("mastery") or {}
                if not isinstance(item, dict) or not item.get("subject"):
                    return _error_result(call_id, "mastery.subject 必填")
                item.setdefault("score", 0)
                item.setdefault("updated_at", now)
                existing["masteries"].append(item)
            else:
                return _error_result(call_id, f"未知 action: {action}")

            saved = await asyncio.to_thread(manager.save_research_space, rs_id, existing)
            return _text_result(call_id, json.dumps(saved, ensure_ascii=False))
        except ValueError as exc:
            return _error_result(call_id, str(exc))
        except Exception as exc:  # noqa: BLE001
            return _error_result(call_id, f"管理研究空间失败: {exc}")

    return AgentTool(
        name="manage_research_space",
        description=(
            "管理研究空间记忆。action: upsert=更新标题/目标；"
            "add_fact/add_question/add_output/add_mastery=追加条目；delete=删除研究空间。"
            "rs_id 不存在时自动创建。"
        ),
        parameters=_MANAGE_RESEARCH_SPACE_PARAMS,
        execution_mode="serial",
        execute=execute,
    )


# ---------------------------------------------------------------------------
# ToolResult 构造助手
# ---------------------------------------------------------------------------

def _text_result(call_id: str, text: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": text}],
        is_error=False,
    )


def _error_result(call_id: str, message: str, *, details: dict | None = None) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
        is_error=True,
        details=details or {},
    )


__all__ = [
    "MemoryManager",
    "MemoryContextHook",
    "build_memory_hook",
    "create_memory_tools",
    "memory_root",
    "user_profile_path",
    "research_spaces_dir",
    "research_space_path",
    "MASTERIES_TOP_N",
]
