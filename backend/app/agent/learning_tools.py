from __future__ import annotations

import asyncio
import json
from typing import Any

from app.agent.core.signal import AbortSignal
from app.agent.core.tool import AgentTool, ToolResult
from app.services.learning_canvas_service import LearningCanvasService
from app.services.learning_canvas_store import LearningCanvasStore
from app.services.learning_session_service import LearningSessionService
from app.services.conversation_store import append_message
from app.services.research_search_config import ResearchSearchConfigManager


def create_learning_tools(
    conversation_id: str,
    *,
    canvas_service: LearningCanvasService | None = None,
    session_service: LearningSessionService | None = None,
    canvas_store: LearningCanvasStore | None = None,
    search_config_manager: ResearchSearchConfigManager | None = None,
) -> list[AgentTool]:
    service = canvas_service or LearningCanvasService(message_writer=append_message)
    sessions = session_service or LearningSessionService()
    store = canvas_store or getattr(service, "store", None) or LearningCanvasStore()
    config_manager = search_config_manager or ResearchSearchConfigManager()

    async def build(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:
        if signal.aborted:
            return _error(call_id, signal.reason or "aborted")
        goal = str(params.get("goal") or "").strip()
        if not goal:
            return _error(call_id, "goal 必填")
        try:
            requested_scopes = params.get("external_scopes")
            external_scopes = config_manager.get_learning_scopes(
                list(requested_scopes)
                if isinstance(requested_scopes, list)
                else None
            )
            canvas = await asyncio.to_thread(
                service.create_canvas,
                conversation_id,
                goal=goal,
                external_scopes=external_scopes,
                external_limit=int(params.get("external_limit") or 5),
            )
            return _text(call_id, canvas.model_dump_json())
        except Exception as exc:
            return _error(call_id, str(exc))

    async def read(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:
        try:
            canvas_id = str(params.get("canvas_id") or "").strip()
            if canvas_id:
                canvas = await asyncio.to_thread(store.load, conversation_id, canvas_id)
            else:
                canvas = await asyncio.to_thread(store.latest, conversation_id)
            return _text(call_id, canvas.model_dump_json())
        except Exception as exc:
            return _error(call_id, str(exc))

    async def start(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:
        try:
            node_id = str(params.get("node_id") or "")
            canvas, unit = await asyncio.to_thread(
                store.update,
                conversation_id,
                str(params.get("canvas_id") or ""),
                lambda current: sessions.start_unit(current, node_id),
            )
            return _text(
                call_id,
                json.dumps(
                    {
                        "unit": unit.model_dump(mode="json"),
                        "canvas": canvas.model_dump(mode="json"),
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            return _error(call_id, str(exc))

    async def submit(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:
        try:
            canvas_id = str(params.get("canvas_id") or "")
            node_id = str(params.get("node_id") or "")

            def mutate(current):
                return sessions.submit_evidence(
                    current,
                    node_id,
                    kind=str(params.get("kind") or "recall"),
                    answer=str(params.get("answer") or ""),
                    rubric_result=dict(params.get("rubric_result") or {}),
                )

            _, evidence = await asyncio.to_thread(
                store.update,
                conversation_id,
                canvas_id,
                mutate,
            )
            return _text(call_id, evidence.model_dump_json())
        except Exception as exc:
            return _error(call_id, str(exc))

    return [
        AgentTool(
            name="build_learning_canvas",
            description="基于本地 Wiki 优先构建持续学习空间；默认补充学术论文和 GitHub，配置网页提供方后也会补充 Web。",
            parameters={
                "type": "object",
                "properties": {
                    "goal": {"type": "string"},
                    "external_scopes": {
                        "type": "array",
                        "items": {"type": "string", "enum": ["web", "academic", "github"]},
                    },
                    "external_limit": {"type": "integer"},
                },
                "required": ["goal"],
            },
            execution_mode="serial",
            execute=build,
        ),
        AgentTool(
            name="read_learning_canvas",
            description="读取当前会话的学习空间、掌握证据和复习队列；省略 canvas_id 时恢复最近画布。",
            parameters={
                "type": "object",
                "properties": {
                    "canvas_id": {
                        "type": "string",
                        "description": "可选；省略时读取当前会话最近更新的学习空间",
                    }
                },
                "required": [],
            },
            execution_mode="parallel",
            execute=read,
        ),
        AgentTool(
            name="start_learning_unit",
            description="开始一个学习节点；只记录 exposed，不会直接标记已掌握。",
            parameters=_ids_schema("canvas_id", "node_id"),
            execution_mode="serial",
            execute=start,
        ),
        AgentTool(
            name="submit_learning_evidence",
            description=(
                "仅在学习者真实作答后，提交回忆、解释、应用、迁移或到期复习证据。"
                "先读取最近画布确认 current_node_id；rubric 必须给出可追溯摘要和具体反馈，"
                "阅读或展示本身不能作为通过证据。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "canvas_id": {"type": "string"},
                    "node_id": {"type": "string"},
                    "kind": {
                        "type": "string",
                        "enum": ["recall", "explain", "apply", "transfer", "review"],
                    },
                    "answer": {"type": "string"},
                    "rubric_result": {
                        "type": "object",
                        "properties": {
                            "rubric_version": {"type": "string"},
                            "score": {"type": "number", "minimum": 0, "maximum": 1},
                            "passed": {"type": "boolean"},
                            "feedback": {"type": "string"},
                            "answer_summary": {"type": "string"},
                        },
                        "required": [
                            "rubric_version",
                            "score",
                            "passed",
                            "feedback",
                            "answer_summary",
                        ],
                    },
                },
                "required": ["canvas_id", "node_id", "kind", "answer", "rubric_result"],
            },
            execution_mode="serial",
            execute=submit,
        ),
    ]


def _ids_schema(*names: str) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {name: {"type": "string"} for name in names},
        "required": list(names),
    }


def _text(call_id: str, content: str) -> ToolResult:
    return ToolResult(call_id=call_id, content=[{"type": "text", "text": content}])


def _error(call_id: str, message: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
        is_error=True,
    )
