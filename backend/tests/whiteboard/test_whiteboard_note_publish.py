from __future__ import annotations

from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
import threading
import time

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.engine import Base
from app.routers import whiteboard
from app.services.note_import_service import NoteImportService
from app.services.whiteboard_note_publish_service import WhiteboardNotePublishService
from app.services.whiteboard_repository import (
    WhiteboardRepository,
    WhiteboardRevisionConflict,
)


class MemoryDocuments:
    def __init__(self) -> None:
        self.rows: dict[str, dict] = {}

    def write(self, payload: dict) -> dict:
        self.rows[payload["task_id"]] = deepcopy(payload)
        return deepcopy(payload)

    def read(self, task_id: str) -> dict | None:
        value = self.rows.get(task_id)
        return deepcopy(value) if value is not None else None

    def compensate(self, task_id: str, previous: dict | None) -> None:
        if previous is None:
            self.rows.pop(task_id, None)
        else:
            self.rows[task_id] = deepcopy(previous)


class VectorStore:
    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.calls: list[str] = []

    def index_task(self, task_id: str) -> None:
        self.calls.append(task_id)
        if self.fail:
            raise RuntimeError("vector unavailable")


def card(card_id: str, title: str, *, x=0, y=0, card_type="markdown", content=None, sources=None):
    if content is None:
        content = {"markdown": f"## {title}\n\nBody for {title}"}
    return {
        "id": card_id,
        "type": card_type,
        "title": title,
        "description": f"Description for {title}",
        "content": content,
        "source_refs": sources or [],
        "position": {"x": x, "y": y},
        "size": {"width": 300, "height": 170},
        "z_index": 0,
        "collapsed": True,
    }


def relation(relation_id: str, source: str, target: str, *, sources=None):
    return {
        "id": relation_id,
        "source_card_id": source,
        "target_card_id": target,
        "relation_type": "supports",
        "label": "supports conclusion",
        "description": "Evidence increases confidence",
        "line_type": "bezier",
        "direction": "forward",
        "source_refs": sources or [],
        "style": {},
    }


@pytest.fixture
def publishing(tmp_path):
    engine = create_engine(
        f"sqlite:///{tmp_path / 'publish.db'}",
        connect_args={"check_same_thread": False},
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    repository = WhiteboardRepository(factory)
    documents = MemoryDocuments()
    vector = VectorStore()
    wiki_calls = []
    importer = NoteImportService(
        output_dir=tmp_path / "notes",
        document_writer=documents.write,
        document_by_id_reader=documents.read,
        document_compensator=documents.compensate,
        vector_store_factory=lambda: vector,
        wiki_scheduler=lambda **kwargs: wiki_calls.append(kwargs),
    )
    service = WhiteboardNotePublishService(
        repository=repository,
        note_importer=importer,
    )
    try:
        yield repository, service, documents, vector, wiki_calls
    finally:
        engine.dispose()


def seed_board(repository: WhiteboardRepository):
    child = repository.create("conv_1", "Nested topic")
    board = repository.create("conv_1", "Main topic", "Board overview")
    source_a = {
        "source_id": "note:alpha",
        "source_type": "local_note",
        "title": "Alpha source",
        "url": "https://example.com/alpha",
    }
    source_b = {
        "source_id": "paper:beta",
        "source_type": "academic",
        "title": "Beta paper",
        "url": "https://example.com/beta",
    }
    result = repository.apply_mutations(
        "conv_1",
        board.id,
        board.revision,
        [
            {"op": "card.create", "card": card("card_late", "Late", x=0, y=300, sources=[source_a])},
            {"op": "card.create", "card": card("card_right", "Right", x=300, y=0, sources=[source_b])},
            {"op": "card.create", "card": card("card_left", "Left", x=0, y=0, sources=[source_a])},
            {
                "op": "card.create",
                "card": card(
                    "card_nested",
                    "Nested",
                    x=600,
                    y=0,
                    card_type="whiteboard",
                    content={"child_whiteboard_id": child.id},
                ),
            },
            {
                "op": "relation.create",
                "relation": relation("rel_left_right", "card_left", "card_right", sources=[source_a]),
            },
        ],
    )
    return repository.get("conv_1", board.id), child, result


def test_deterministic_compiler_uses_spatial_order_relations_sources_and_nested_link(publishing):
    repository, service, *_ = publishing
    board, child, _ = seed_board(repository)

    markdown = service.compile_markdown(board, scope="all", card_ids=[], relation_ids=[])

    assert markdown.index("## Left") < markdown.index("## Right") < markdown.index("## Nested") < markdown.index("## Late")
    assert "Left --[supports：supports conclusion；Evidence increases confidence]--> Right" in markdown
    assert f"notemeld://whiteboard/{child.id}" in markdown
    assert markdown.count("note:alpha") >= 1
    sources_section = markdown.split("## 来源", 1)[1]
    assert sources_section.count("note:alpha") == 1
    assert sources_section.count("paper:beta") == 1
    assert "invented" not in markdown


@pytest.mark.parametrize(
    "model_output",
    [
        "",
        "```markdown\n# Fabricated\n```",
        "# Compiled\n\nSource: https://invented.invalid/item",
    ],
)
def test_invalid_llm_output_falls_back_without_inventing_sources(publishing, model_output):
    repository, _service, documents, vector, wiki_calls = publishing
    board, _child, _ = seed_board(repository)
    service = WhiteboardNotePublishService(
        repository=repository,
        note_importer=_service.note_importer,
        llm_compiler=lambda **_kwargs: model_output,
    )

    markdown = service.compile_markdown(
        board,
        scope="all",
        card_ids=[],
        relation_ids=[],
        provider_id="provider_1",
        model_name="model_1",
    )

    assert "# Main topic" in markdown
    assert "invented.invalid" not in markdown
    assert documents.rows == {}
    assert vector.calls == []
    assert wiki_calls == []


def test_selection_scope_is_resolved_from_authoritative_board(publishing):
    repository, service, *_ = publishing
    board, _child, _ = seed_board(repository)

    markdown = service.compile_markdown(
        board,
        scope="selection",
        card_ids=["card_left"],
        relation_ids=["rel_left_right"],
    )

    assert "## Left" in markdown
    assert "## Right" in markdown  # explicit relation closes over its endpoint
    assert "## Late" not in markdown
    with pytest.raises(ValueError, match="does not belong"):
        service.compile_markdown(
            board,
            scope="selection",
            card_ids=["card_missing"],
            relation_ids=[],
        )


def test_republish_keeps_note_id_and_advances_only_after_success(publishing):
    repository, service, documents, vector, wiki_calls = publishing
    board, _child, _ = seed_board(repository)

    first = service.publish("conv_1", board.id, board.revision, "all", [], [], None, None)
    repository.apply_mutations(
        "conv_1",
        board.id,
        first.published_revision,
        [{"op": "card.update", "card_id": "card_left", "patch": {"description": "Updated"}}],
    )
    second_revision = repository.get("conv_1", board.id).revision
    second = service.publish("conv_1", board.id, second_revision, "all", [], [], None, None)

    assert second.note_task_id == first.note_task_id
    assert second.published_revision == second_revision
    assert repository.get("conv_1", board.id).note_link.published_revision == second_revision
    assert len(documents.rows) == 1
    assert vector.calls == [first.note_task_id, first.note_task_id]
    assert [call["task_id"] for call in wiki_calls] == [first.note_task_id, first.note_task_id]


def test_same_board_publications_are_serialized_to_prevent_file_document_split(publishing):
    repository, base_service, _documents, _vector, _wiki_calls = publishing
    board, _child, _ = seed_board(repository)
    base_service.publish("conv_1", board.id, board.revision, "all", [], [], None, None)

    class TrackingImporter:
        def __init__(self, delegate):
            self.delegate = delegate
            self.active = 0
            self.max_active = 0
            self.lock = threading.Lock()

        def publish_revision(self, *args, **kwargs):
            with self.lock:
                self.active += 1
                self.max_active = max(self.max_active, self.active)
            try:
                time.sleep(0.05)
                return self.delegate.publish_revision(*args, **kwargs)
            finally:
                with self.lock:
                    self.active -= 1

    tracking = TrackingImporter(base_service.note_importer)
    service = WhiteboardNotePublishService(
        repository=repository,
        note_importer=tracking,
    )

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(
            executor.map(
                lambda _index: service.publish(
                    "conv_1",
                    board.id,
                    board.revision,
                    "all",
                    [],
                    [],
                    None,
                    None,
                ),
                range(2),
            )
        )

    assert tracking.max_active == 1
    assert len({result.note_task_id for result in results}) == 1


def test_stale_revision_rejects_without_note_or_postprocessing(publishing):
    repository, service, documents, vector, wiki_calls = publishing
    board, _child, _ = seed_board(repository)

    with pytest.raises(WhiteboardRevisionConflict):
        service.publish("conv_1", board.id, board.revision - 1, "all", [], [], None, None)

    assert documents.rows == {}
    assert vector.calls == []
    assert wiki_calls == []
    assert repository.get("conv_1", board.id).note_link is None


def test_empty_board_cannot_publish_an_empty_note(publishing):
    repository, service, documents, vector, wiki_calls = publishing
    board = repository.create("conv_1", "Empty")

    with pytest.raises(ValueError, match="at least one card"):
        service.publish("conv_1", board.id, board.revision, "all", [], [], None, None)

    assert documents.rows == {}
    assert vector.calls == []
    assert wiki_calls == []
    assert repository.get("conv_1", board.id).note_link is None


def test_note_link_commit_failure_compensates_note_and_does_not_advance(publishing, monkeypatch):
    repository, service, documents, vector, wiki_calls = publishing
    board, _child, _ = seed_board(repository)

    monkeypatch.setattr(
        service,
        "_commit_note_link",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("db failed")),
    )
    with pytest.raises(RuntimeError, match="db failed"):
        service.publish("conv_1", board.id, board.revision, "all", [], [], None, None)

    assert documents.rows == {}
    assert vector.calls == []
    assert wiki_calls == []
    assert repository.get("conv_1", board.id).note_link is None


@pytest.mark.parametrize("postprocessor", ["vector", "wiki"])
def test_postprocessing_failure_is_partial_and_published_revision_is_durable(
    publishing, postprocessor
):
    repository, _service, documents, vector, wiki_calls = publishing
    board, _child, _ = seed_board(repository)
    if postprocessor == "vector":
        vector.fail = True
        importer = _service.note_importer
    else:
        importer = NoteImportService(
            output_dir=_service.note_importer.output_dir,
            document_writer=documents.write,
            document_by_id_reader=documents.read,
            document_compensator=documents.compensate,
            vector_store_factory=lambda: vector,
            wiki_scheduler=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("wiki failed")),
        )
    service = WhiteboardNotePublishService(repository=repository, note_importer=importer)

    result = service.publish("conv_1", board.id, board.revision, "all", [], [], None, None)

    assert result.status == "partial"
    assert result.published_revision == board.revision
    assert repository.get("conv_1", board.id).note_link.published_revision == board.revision
    assert result.note_task_id in documents.rows
    assert result.retry_actions


def test_ordinary_mutation_never_publishes_or_schedules_wiki(publishing):
    repository, service, documents, vector, wiki_calls = publishing
    board, _child, _ = seed_board(repository)

    repository.apply_mutations(
        "conv_1",
        board.id,
        board.revision,
        [{"op": "viewport.update", "x": 1, "y": 2, "zoom": 1.1}],
    )

    assert documents.rows == {}
    assert vector.calls == []
    assert wiki_calls == []
    assert repository.get("conv_1", board.id).note_link is None


def test_publish_endpoint_uses_wrapper_and_safe_revision_conflict(publishing, monkeypatch):
    repository, service, *_ = publishing
    board, _child, _ = seed_board(repository)
    monkeypatch.setattr(whiteboard, "repository", repository)
    monkeypatch.setattr(whiteboard, "publish_service", service)
    app = FastAPI()
    app.include_router(whiteboard.router, prefix="/api")
    client = TestClient(app)

    success = client.post(
        f"/api/conversations/conv_1/whiteboards/{board.id}/publish-note",
        json={"base_revision": board.revision, "scope": "all"},
    ).json()
    assert success["code"] == 0
    assert success["data"]["note_task_id"]

    stale = client.post(
        f"/api/conversations/conv_1/whiteboards/{board.id}/publish-note",
        json={"base_revision": board.revision - 1, "scope": "all"},
    ).json()
    assert stale == {
        "code": 409,
        "msg": "白板已在其他窗口更新",
        "data": {"current_revision": board.revision},
    }
