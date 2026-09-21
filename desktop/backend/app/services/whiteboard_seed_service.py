from __future__ import annotations

import hashlib
import logging
import math
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.engine import SessionLocal
from app.db.models.conversation import NoteDocument
from app.db.models.whiteboard import (
    Whiteboard as WhiteboardRow,
    WhiteboardCard as WhiteboardCardRow,
    WhiteboardNoteLink as WhiteboardNoteLinkRow,
    WhiteboardRelation as WhiteboardRelationRow,
)
from app.models.learning_canvas import LearningCanvas, LearningEdge, LearningSource
from app.models.whiteboard import (
    WhiteboardCard,
    WhiteboardRelation,
    WhiteboardSnapshot,
    WhiteboardSourceRef,
)
from app.services.learning_canvas_store import LearningCanvasStore
from app.services.whiteboard_repository import WhiteboardRepository


logger = logging.getLogger(__name__)


class WhiteboardSeedService:
    def __init__(
        self,
        *,
        repository: WhiteboardRepository | None = None,
        store: LearningCanvasStore | None = None,
    ) -> None:
        self.repository = repository or WhiteboardRepository(SessionLocal)
        self.store = store or LearningCanvasStore()

    def ensure_from_learning_canvas(
        self,
        conversation_id: str,
        canvas_id: str,
    ) -> WhiteboardSnapshot:
        canvas = self.store.load(conversation_id, canvas_id)

        try:
            with self.repository._write_session() as session:
                self.repository._active_conversation(session, conversation_id)
                existing = session.scalar(
                    select(WhiteboardRow).where(
                        WhiteboardRow.legacy_canvas_id == canvas.canvas_id
                    )
                )
                if existing is not None:
                    return self._owned_snapshot(
                        session,
                        existing,
                        conversation_id=conversation_id,
                    )

                cards = self._cards_from_canvas(canvas)
                relations = self._relations_from_canvas(canvas, cards)
                title = self.repository._bounded_required(canvas.goal, "title", 200)
                description = self.repository._bounded_optional(
                    canvas.overview,
                    "description",
                    2_000,
                )
                board = WhiteboardRow(
                    id=f"wb_{self._digest(canvas.canvas_id)}",
                    conversation_id=conversation_id,
                    title=title,
                    description=description,
                    schema_version=1,
                    revision=1,
                    viewport_json=self.repository._dump_json(
                        {"x": 0.0, "y": 0.0, "zoom": 1.0}
                    ),
                    legacy_canvas_id=canvas.canvas_id,
                    status="active",
                )
                session.add(board)
                session.flush()

                for card in cards:
                    row = WhiteboardCardRow(id=card.id, whiteboard_id=board.id)
                    self.repository._write_card_row(row, card)
                    session.add(row)
                session.flush()

                for relation in relations:
                    row = WhiteboardRelationRow(
                        id=relation.id,
                        whiteboard_id=board.id,
                    )
                    self.repository._write_relation_row(row, relation)
                    session.add(row)

                if canvas.document_task_id:
                    owned_note = session.scalar(
                        select(NoteDocument).where(
                            NoteDocument.task_id == canvas.document_task_id,
                            NoteDocument.conversation_id == conversation_id,
                            NoteDocument.deleted_at.is_(None),
                        )
                    )
                    if owned_note is not None:
                        session.add(
                            WhiteboardNoteLinkRow(
                                whiteboard_id=board.id,
                                note_task_id=owned_note.task_id,
                                published_revision=1,
                            )
                        )

                session.flush()
                session.refresh(board)
                return self.repository._snapshot(session, board)
        except IntegrityError as exc:
            if not self._is_legacy_canvas_unique_conflict(exc):
                raise
            return self._load_existing(conversation_id, canvas.canvas_id)

    def _load_existing(
        self,
        conversation_id: str,
        canvas_id: str,
    ) -> WhiteboardSnapshot:
        with self.repository._session_factory() as session:
            existing = session.scalar(
                select(WhiteboardRow).where(
                    WhiteboardRow.legacy_canvas_id == canvas_id
                )
            )
            if existing is None:
                raise LookupError("whiteboard not found")
            return self._owned_snapshot(
                session,
                existing,
                conversation_id=conversation_id,
            )

    def _owned_snapshot(
        self,
        session,
        board: WhiteboardRow,
        *,
        conversation_id: str,
    ) -> WhiteboardSnapshot:
        self.repository._active_conversation(session, conversation_id)
        if (
            board.conversation_id != conversation_id
            or board.deleted_at is not None
            or board.status != "active"
        ):
            raise LookupError("whiteboard not found")
        return self.repository._snapshot(session, board)

    def _cards_from_canvas(self, canvas: LearningCanvas) -> list[WhiteboardCard]:
        source_by_id = {source.id: source for source in canvas.sources}
        count = len(canvas.nodes)
        columns = math.ceil(math.sqrt(count)) if count else 1
        cards: list[WhiteboardCard] = []
        for index, node in enumerate(canvas.nodes):
            title = str(node.user_label or node.label or "").strip()
            description = str(node.user_summary or node.summary or "").strip()
            cards.append(
                WhiteboardCard(
                    id=self._card_id(canvas.canvas_id, node.id),
                    type="markdown",
                    title=title,
                    description=description,
                    content={
                        "markdown": f"## {title}\n\n{description}".rstrip()
                    },
                    source_refs=self._source_refs(node.source_ids, source_by_id),
                    position={
                        "x": float((index % columns) * 340),
                        "y": float((index // columns) * 220),
                    },
                    size={"width": 300.0, "height": 170.0},
                    z_index=index,
                    collapsed=True,
                )
            )
        return cards

    def _relations_from_canvas(
        self,
        canvas: LearningCanvas,
        cards: list[WhiteboardCard],
    ) -> list[WhiteboardRelation]:
        card_id_by_node = {
            node.id: card.id for node, card in zip(canvas.nodes, cards)
        }
        relations: list[WhiteboardRelation] = []
        dropped = 0
        for index, edge in enumerate(canvas.edges):
            source_card_id = card_id_by_node.get(edge.source)
            target_card_id = card_id_by_node.get(edge.target)
            if (
                source_card_id is None
                or target_card_id is None
                or source_card_id == target_card_id
            ):
                dropped += 1
                continue
            relations.append(
                WhiteboardRelation(
                    id=self._relation_id(canvas.canvas_id, edge, index),
                    source_card_id=source_card_id,
                    target_card_id=target_card_id,
                    relation_type=self._relation_type(edge.type),
                    label=str(edge.type or "")[:160],
                    description="",
                    line_type="bezier",
                    direction="forward",
                    source_refs=[],
                    style={},
                )
            )
        if dropped:
            logger.warning(
                "LearningCanvas seed omitted %d invalid relation(s) for canvas %s",
                dropped,
                canvas.canvas_id,
            )
        return relations

    @staticmethod
    def _source_refs(
        source_ids: Iterable[str],
        source_by_id: dict[str, LearningSource],
    ) -> list[WhiteboardSourceRef]:
        refs: list[WhiteboardSourceRef] = []
        seen: set[str] = set()
        for source_id in source_ids:
            source = source_by_id.get(source_id)
            if source is None or source.id in seen:
                continue
            seen.add(source.id)
            refs.append(
                WhiteboardSourceRef(
                    source_id=source.id,
                    source_type=source.source_type,
                    title=source.title,
                    url=source.url,
                    task_id=source.local_task_id,
                )
            )
            if len(refs) == 20:
                break
        return refs

    @staticmethod
    def _relation_type(edge_type: str) -> str:
        normalized = str(edge_type or "").strip().lower()
        return {
            "prerequisite": "depends_on",
            "depends_on": "depends_on",
            "supports": "supports",
            "challenges": "challenges",
            "contains": "contains",
            "custom": "custom",
        }.get(normalized, "related")

    @classmethod
    def _card_id(cls, canvas_id: str, node_id: str) -> str:
        return f"card_{cls._digest(f'{canvas_id}:node:{node_id}')}"

    @classmethod
    def _relation_id(
        cls,
        canvas_id: str,
        edge: LearningEdge,
        index: int,
    ) -> str:
        return f"rel_{cls._digest(f'{canvas_id}:edge:{index}:{edge.source}:{edge.target}')}"

    @staticmethod
    def _digest(value: str) -> str:
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    @staticmethod
    def _is_legacy_canvas_unique_conflict(exc: IntegrityError) -> bool:
        message = str(exc.orig).lower()
        return (
            "unique constraint failed: whiteboards.legacy_canvas_id" in message
            or "uq_whiteboards_legacy_canvas_id" in message
        )
