from __future__ import annotations

import hashlib
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Callable

from app.models.learning_canvas import (
    LearningCanvas,
    LearningEdge,
    LearningNode,
    LearningPathStep,
    LearningSource,
)
from app.services.learning_canvas_store import LearningCanvasStore
from app.services.research_search import (
    ResearchSearchService,
    build_research_search_service,
)
from app.services.research_search_config import ResearchSearchConfigManager
from app.services.research_note_compiler import ResearchNoteCompiler, build_llm_research_compiler
from app.services.note_import_service import ImportNoteRequest, NoteImportService
from app.services.conversation_context_refs import sanitize_context_refs
from app.services.wiki_search import WikiSearch
from app.utils.storage_paths import note_output_dir


class LearningCanvasEmptyError(ValueError):
    pass


def _stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def build_learning_path(
    nodes: list[LearningNode], edges: list[LearningEdge]
) -> list[LearningPathStep]:
    node_by_id = {node.id: node for node in nodes}
    incoming: dict[str, set[str]] = {node.id: set() for node in nodes}
    outgoing: dict[str, set[str]] = {node.id: set() for node in nodes}
    for edge in edges:
        if edge.source not in node_by_id or edge.target not in node_by_id:
            continue
        incoming[edge.target].add(edge.source)
        outgoing[edge.source].add(edge.target)
    for node in nodes:
        for prerequisite in node.prerequisites:
            if prerequisite in node_by_id:
                incoming[node.id].add(prerequisite)
                outgoing[prerequisite].add(node.id)

    dependencies_by_node = {
        node_id: set(dependencies)
        for node_id, dependencies in incoming.items()
    }

    queue = deque(sorted(node_id for node_id, deps in incoming.items() if not deps))
    ordered: list[str] = []
    while queue:
        current = queue.popleft()
        ordered.append(current)
        for target in sorted(outgoing[current]):
            incoming[target].discard(current)
            if not incoming[target] and target not in ordered and target not in queue:
                queue.append(target)

    for node_id in sorted(node_by_id):
        if node_id not in ordered:
            ordered.append(node_id)

    step_by_node: dict[str, int] = {}
    steps: list[LearningPathStep] = []
    for index, node_id in enumerate(ordered, start=1):
        node = node_by_id[node_id]
        dependencies = sorted(
            step_by_node[item]
            for item in dependencies_by_node.get(node_id, set())
            if item in step_by_node
        )
        steps.append(
            LearningPathStep(
                step=index,
                node_ids=[node_id],
                label=node.user_label or node.label,
                difficulty="introductory" if index == 1 else "intermediate",
                minutes_estimate=10,
                depends_on=dependencies,
            )
        )
        step_by_node[node_id] = index
    return steps


class LearningCanvasService:
    def __init__(
        self,
        *,
        store: LearningCanvasStore | None = None,
        local_search: Callable[[str], list[dict]] | None = None,
        research_search: ResearchSearchService | None = None,
        search_config_manager: ResearchSearchConfigManager | None = None,
        message_writer: Callable[[str, dict], object] | None = None,
        compiler: ResearchNoteCompiler | None = None,
        note_importer: NoteImportService | None = None,
    ):
        self.store = store or LearningCanvasStore()
        self.local_search = local_search or self._default_local_search
        self.research_search = research_search
        self.search_config_manager = search_config_manager or ResearchSearchConfigManager()
        self.message_writer = message_writer
        self.compiler = compiler or ResearchNoteCompiler(llm_compiler=build_llm_research_compiler())
        self.note_importer = note_importer or NoteImportService()

    def create_canvas(
        self,
        conversation_id: str,
        *,
        goal: str,
        external_scopes: list[str] | None = None,
        external_limit: int = 5,
        canvas_id: str | None = None,
        research_space_id: str | None = None,
        provider_id: str | None = None,
        model_name: str | None = None,
        context_refs: list[dict] | None = None,
    ) -> LearningCanvas:
        normalized_goal = str(goal or "").strip()
        if not normalized_goal:
            raise ValueError("goal 不能为空")
        local_results = self.local_search(normalized_goal)
        local_sources, local_nodes = self._from_local_results(local_results)
        for reference in sanitize_context_refs(context_refs):
            local_nodes.append(
                LearningNode(
                    id=_stable_id("context", reference["id"] or reference["snapshot"]),
                    label=reference["label"],
                    type="evidence",
                    summary=reference["snapshot"],
                    priority="high",
                    source_ids=reference["source_ids"],
                )
            )
        research_search = self.research_search or build_research_search_service(
            self.search_config_manager
        )
        bundle = research_search.search(
            normalized_goal,
            scopes=self.search_config_manager.get_learning_scopes(external_scopes),
            limit=max(1, min(int(external_limit), 20)),
        )
        compilation = self.compiler.compile(
            goal=normalized_goal,
            local_nodes=local_nodes,
            sources=bundle.sources,
            provider_id=provider_id,
            model_name=model_name,
        )
        nodes = compilation.nodes
        if bundle.errors and nodes:
            for node in nodes:
                node.status = "blocked_external"

        document_task_id = None
        if compilation.status == "ready":
            imported = self.note_importer.import_note(
                ImportNoteRequest(
                    title=compilation.title,
                    content=compilation.markdown,
                    format="markdown",
                    source_type="research",
                    metadata={
                        "goal": normalized_goal,
                        "source_ids": [source.id for source in compilation.sources],
                    },
                ),
                conversation_id=conversation_id,
            )
            document_task_id = imported.note_id

        now = datetime.now(timezone.utc)
        canvas = LearningCanvas(
            canvas_id=canvas_id or f"lc_{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            research_space_id=research_space_id,
            goal=normalized_goal,
            status=compilation.status,
            nodes=nodes,
            sources=[*local_sources, *compilation.sources],
            edges=compilation.edges,
            external_errors=[error.model_dump(mode="json") for error in bundle.errors],
            created_at=now,
            updated_at=now,
            document_task_id=document_task_id,
            overview=compilation.overview,
            clarification=(compilation.clarification.model_dump(mode="json") if compilation.clarification else None),
            suggested_actions=[action.model_dump(mode="json") for action in compilation.suggested_actions],
        )
        canvas.path = build_learning_path(canvas.nodes, canvas.edges)
        projection_saved = False
        try:
            self.store.save(canvas)
            projection_saved = True
        except Exception:
            if not canvas.document_task_id:
                raise
            canvas.external_errors.append(
                {
                    "provider": "notemeld",
                    "code": "projection_save_failed",
                    "message": "研究笔记已保存，白板暂时无法持久化",
                }
            )
        if self.message_writer is not None and projection_saved:
            source_types = list(
                dict.fromkeys(source.source_type for source in canvas.sources)
            )
            recommended_node = self._recommended_node(canvas)
            try:
                self.message_writer(
                    conversation_id,
                    {
                        "id": f"msg_{uuid.uuid4().hex}",
                        "role": "assistant",
                        "message_type": "learning_canvas",
                        "content": self._build_guide_content(
                            canvas,
                            source_types=source_types,
                            recommended_node=recommended_node,
                        ),
                        "status": "success",
                        "meta": {
                            "canvas_id": canvas.canvas_id,
                            "goal": canvas.goal,
                            "status": canvas.status,
                            "node_count": len(canvas.nodes),
                            "source_types": source_types,
                            "recommended_node_id": (
                                recommended_node.id if recommended_node else None
                            ),
                            "recommended_node_label": (
                                recommended_node.user_label or recommended_node.label
                                if recommended_node
                                else None
                            ),
                            "external_error_count": len(canvas.external_errors),
                            "document_task_id": canvas.document_task_id,
                            "overview": canvas.overview,
                            "clarification": canvas.clarification,
                            "suggested_actions": canvas.suggested_actions,
                        },
                    },
                )
            except Exception:
                if not canvas.document_task_id:
                    raise
                canvas.external_errors.append(
                    {
                        "provider": "notemeld",
                        "code": "guide_message_failed",
                        "message": "研究笔记已保存，对话摘要暂时无法写入",
                    }
                )
        return canvas

    @staticmethod
    def _recommended_node(canvas: LearningCanvas) -> LearningNode | None:
        if canvas.path and canvas.path[0].node_ids:
            first_node_id = canvas.path[0].node_ids[0]
            matched = next(
                (node for node in canvas.nodes if node.id == first_node_id), None
            )
            if matched is not None:
                return matched
        return canvas.nodes[0] if canvas.nodes else None

    @staticmethod
    def _build_guide_content(
        canvas: LearningCanvas,
        *,
        source_types: list[str],
        recommended_node: LearningNode | None,
    ) -> str:
        source_labels = {
            "local_wiki": "NoteMeld 本地内容",
            "local_note": "NoteMeld 笔记",
            "academic": "学术论文",
            "github": "GitHub 项目",
            "web": "普通网页",
        }
        rendered_sources = "、".join(
            source_labels.get(source_type, source_type)
            for source_type in source_types
        ) or "当前可用资料"
        if canvas.status == "clarifying" and canvas.clarification:
            return str(canvas.clarification.get("question") or "请先补充研究对象。")
        guide = f"已完成“{canvas.goal}”的研究概览，资料覆盖 {rendered_sources}。"
        if recommended_node is not None:
            label = recommended_node.user_label or recommended_node.label
            summary = str(
                recommended_node.user_summary or recommended_node.summary or ""
            ).strip()
            guide += f"可以先查看“{label}”。"
            if summary:
                guide += f"核心切入点：{summary[:180]}"
                if len(summary) > 180:
                    guide += "…"
                guide += "。"
        else:
            guide += "可以先从研究概览开始。"
        guide += "右侧可在笔记与白板之间切换，并选择下一步研究方向。"
        if canvas.external_errors:
            guide += f"有 {len(canvas.external_errors)} 个外部来源暂时不可用，本地学习内容仍可继续。"
        return guide

    @staticmethod
    def _default_local_search(goal: str) -> list[dict]:
        return WikiSearch(note_output_dir() / "wiki").search(goal, limit=20)

    @staticmethod
    def _from_local_results(
        results: list[dict],
    ) -> tuple[list[LearningSource], list[LearningNode]]:
        sources: list[LearningSource] = []
        nodes: list[LearningNode] = []
        source_ids: set[str] = set()
        for item in results:
            metadata = item.get("metadata") or {}
            raw_source_id = str(metadata.get("source_id") or item.get("page_id") or item.get("id") or "")
            source_id = f"wiki:{raw_source_id}"
            if source_id not in source_ids:
                sources.append(
                    LearningSource(
                        id=source_id,
                        source_type="local_wiki",
                        provider="notemeld_wiki",
                        title=str(item.get("title") or raw_source_id),
                        snippet=str(item.get("text") or item.get("snippet") or ""),
                        local_task_id=raw_source_id,
                        compile_status="local",
                    )
                )
                source_ids.add(source_id)
            score = float(item.get("score") or 0.0)
            nodes.append(
                LearningNode(
                    id=_stable_id("local", str(item.get("id") or item.get("title") or raw_source_id)),
                    label=str(item.get("title") or "本地知识"),
                    type=str(item.get("type") or "concept").replace("wiki_", ""),
                    summary=str(item.get("text") or item.get("snippet") or ""),
                    priority="high" if score >= 5 else "medium",
                    source_ids=[source_id],
                )
            )
        return sources, nodes

    @staticmethod
    def _node_from_external(source: LearningSource) -> LearningNode:
        return LearningNode(
            id=_stable_id(source.source_type, source.id),
            label=source.title,
            type="source",
            summary=source.snippet,
            priority="medium",
            source_ids=[source.id],
            status="candidate",
        )
