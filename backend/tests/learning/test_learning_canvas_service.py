from __future__ import annotations

from app.models.learning_canvas import (
    LearningEdge,
    LearningNode,
    LearningSource,
)
from app.services.learning_canvas_service import (
    LearningCanvasEmptyError,
    LearningCanvasService,
    build_learning_path,
)
from app.services.learning_canvas_store import LearningCanvasStore
from app.services.research_search import (
    ResearchSearchBundle,
    ResearchSearchError,
)


class _NoteImporter:
    def __init__(self):
        self.requests = []

    def import_note(self, request, conversation_id=None):
        self.requests.append((request, conversation_id))
        return type("Result", (), {"note_id": "note_research", "wiki_status": "pending"})()


class _ExternalSearch:
    def __init__(self, bundle: ResearchSearchBundle):
        self.bundle = bundle

    def search(self, query: str, scopes: list[str], limit: int):
        return self.bundle


def local_results(_goal: str):
    return [
        {
            "id": "wiki-concept-decoding",
            "type": "wiki_concept",
            "title": "自回归解码",
            "text": "按 token 顺序生成。",
            "score": 8.0,
            "metadata": {"source_id": "task-local"},
        }
    ]


def test_create_canvas_orders_local_sources_before_external(tmp_path) -> None:
    external = LearningSource(
        id="arxiv:2608.1",
        source_type="academic",
        provider="arxiv",
        title="Learning decoding paper",
        snippet="token decoding research",
        url="https://arxiv.org/abs/2608.1",
    )
    service = LearningCanvasService(
        store=LearningCanvasStore(root=tmp_path),
        local_search=local_results,
        research_search=_ExternalSearch(ResearchSearchBundle(sources=[external])),
        note_importer=_NoteImporter(),
    )

    canvas = service.create_canvas(
        "conv_canvas",
        goal="学习解码",
        external_scopes=["academic"],
        external_limit=5,
        canvas_id="lc_canvas",
    )

    assert [source.source_type for source in canvas.sources] == ["local_wiki", "academic"]
    assert canvas.nodes[0].source_ids == ["wiki:task-local"]
    assert canvas.nodes[0].mastery == "unknown"
    assert service.store.load("conv_canvas", "lc_canvas").goal == "学习解码"


def test_external_failure_keeps_local_canvas_and_marks_error(tmp_path) -> None:
    service = LearningCanvasService(
        store=LearningCanvasStore(root=tmp_path),
        local_search=local_results,
        research_search=_ExternalSearch(
            ResearchSearchBundle(
                errors=[
                    ResearchSearchError(
                        provider="github", code="provider_down", message="offline"
                    )
                ]
            )
        ),
        note_importer=_NoteImporter(),
    )

    canvas = service.create_canvas(
        "conv_canvas",
        goal="学习解码",
        external_scopes=["github"],
        canvas_id="lc_canvas",
    )

    assert len(canvas.nodes) == 1
    assert canvas.external_errors[0]["provider"] == "github"
    assert canvas.nodes[0].status == "blocked_external"


def test_empty_local_and_external_results_create_evidence_gap_framework(tmp_path) -> None:
    service = LearningCanvasService(
        store=LearningCanvasStore(root=tmp_path),
        local_search=lambda _goal: [],
        research_search=_ExternalSearch(ResearchSearchBundle()),
        note_importer=_NoteImporter(),
    )
    canvas = service.create_canvas(
        "conv_canvas",
        goal="不存在的主题",
        external_scopes=["academic"],
        canvas_id="lc_canvas",
    )

    assert canvas.status == "ready"
    assert canvas.nodes[0].type == "topic"
    assert "证据不足" in canvas.nodes[0].summary


def test_learning_path_places_prerequisites_first() -> None:
    nodes = [
        LearningNode(id="a", label="A"),
        LearningNode(id="b", label="B", prerequisites=["a"]),
        LearningNode(id="c", label="C", prerequisites=["b"]),
    ]
    edges = [
        LearningEdge(source="a", target="b"),
        LearningEdge(source="b", target="c"),
    ]

    path = build_learning_path(nodes, edges)

    order = [step.node_ids[0] for step in path]
    assert order == ["a", "b", "c"]
    assert path[2].depends_on == [2]


def test_learning_path_keeps_dependencies_declared_only_by_edges() -> None:
    nodes = [
        LearningNode(id="a", label="A"),
        LearningNode(id="b", label="B"),
    ]

    path = build_learning_path(nodes, [LearningEdge(source="a", target="b")])

    assert [step.node_ids[0] for step in path] == ["a", "b"]
    assert path[1].depends_on == [1]


def test_create_canvas_writes_one_compact_conversation_message(tmp_path) -> None:
    messages: list[tuple[str, dict]] = []
    service = LearningCanvasService(
        store=LearningCanvasStore(root=tmp_path),
        local_search=local_results,
        research_search=_ExternalSearch(ResearchSearchBundle()),
        message_writer=lambda conversation_id, payload: messages.append(
            (conversation_id, payload)
        ),
        note_importer=_NoteImporter(),
    )

    canvas = service.create_canvas(
        "conv_canvas",
        goal="学习解码",
        external_scopes=[],
        canvas_id="lc_canvas",
    )

    assert len(messages) == 1
    conversation_id, payload = messages[0]
    assert conversation_id == "conv_canvas"
    assert payload["message_type"] == "learning_canvas"
    assert payload["meta"]["canvas_id"] == canvas.canvas_id
    assert payload["meta"]["goal"] == canvas.goal
    assert payload["meta"]["document_task_id"] == "note_research"
    assert payload["meta"]["recommended_node_label"] == "自回归解码"
    assert "nodes" not in payload["meta"]
    assert "可以先查看“自回归解码”" in payload["content"]
    assert "笔记与白板" in payload["content"]


def test_ready_research_imports_standard_note_and_binds_canvas(tmp_path) -> None:
    imported = []

    class NoteImporter:
        def import_note(self, request, conversation_id=None):
            imported.append((request, conversation_id))
            return type("Result", (), {"note_id": "note_research", "wiki_status": "pending"})()

    service = LearningCanvasService(
        store=LearningCanvasStore(root=tmp_path),
        local_search=local_results,
        research_search=_ExternalSearch(ResearchSearchBundle()),
        note_importer=NoteImporter(),
    )
    canvas = service.create_canvas("conv_canvas", goal="AI Agent 运行机制", canvas_id="lc_canvas")

    assert canvas.document_task_id == "note_research"
    assert imported[0][1] == "conv_canvas"
    assert "## 概览" in imported[0][0].content


def test_clarification_does_not_import_note(tmp_path) -> None:
    class ClarifyingCompiler:
        def compile(self, **_kwargs):
            from app.services.research_note_compiler import ResearchCompilation, ResearchClarification, ClarificationOption
            return ResearchCompilation(
                status="clarifying",
                clarification=ResearchClarification(
                    question="你指的是历史人物还是游戏角色？",
                    options=[
                        ClarificationOption(id="history", label="历史人物"),
                        ClarificationOption(id="game", label="游戏角色"),
                    ],
                ),
            )

    class NoteImporter:
        def import_note(self, *_args, **_kwargs):
            raise AssertionError("ambiguous goal must not create a note")

    service = LearningCanvasService(
        store=LearningCanvasStore(root=tmp_path),
        local_search=lambda _goal: [],
        research_search=_ExternalSearch(ResearchSearchBundle()),
        note_importer=NoteImporter(),
        compiler=ClarifyingCompiler(),
    )
    canvas = service.create_canvas("conv_canvas", goal="韩信", canvas_id="lc_canvas")

    assert canvas.status == "clarifying"
    assert canvas.document_task_id is None
    assert canvas.clarification is not None


def test_note_success_with_projection_failure_does_not_write_dangling_canvas_message(tmp_path) -> None:
    class FailingStore(LearningCanvasStore):
        def save(self, _canvas):
            raise OSError("disk projection failed")

    messages = []
    service = LearningCanvasService(
        store=FailingStore(root=tmp_path),
        local_search=local_results,
        research_search=_ExternalSearch(ResearchSearchBundle()),
        note_importer=_NoteImporter(),
        message_writer=lambda *args: messages.append(args),
    )

    canvas = service.create_canvas("conv_canvas", goal="AI Agent 运行机制", canvas_id="lc_canvas")

    assert canvas.document_task_id == "note_research"
    assert any(error["code"] == "projection_save_failed" for error in canvas.external_errors)
    assert messages == []
