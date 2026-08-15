from __future__ import annotations

import json
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator
from urllib.parse import urlparse

from pydantic import TypeAdapter
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session, sessionmaker

from app.db.models.whiteboard import (
    Whiteboard as WhiteboardRow,
    WhiteboardCard as WhiteboardCardRow,
    WhiteboardNoteLink as WhiteboardNoteLinkRow,
    WhiteboardRelation as WhiteboardRelationRow,
)
from app.models.whiteboard import (
    CardCreateOp,
    CardDeleteOp,
    CardMoveResizeOp,
    CardUpdateOp,
    RelationCreateOp,
    RelationDeleteOp,
    RelationUpdateOp,
    ViewportUpdateOp,
    WhiteboardCard,
    WhiteboardMutationResult,
    WhiteboardNoteLink,
    WhiteboardOperation,
    WhiteboardRelation,
    WhiteboardSnapshot,
    WhiteboardSummary,
    WhiteboardViewport,
)
from app.services.conversation_asset_store import ConversationAssetStore
from app.utils.storage_paths import upload_dir


_OPERATIONS_ADAPTER = TypeAdapter(list[WhiteboardOperation])


class WhiteboardRevisionConflict(ValueError):
    def __init__(self, current_revision: int):
        self.current_revision = current_revision
        super().__init__(f"whiteboard revision conflict; current revision is {current_revision}")


class ConversationFileAssetResolver:
    def __init__(
        self,
        asset_store: ConversationAssetStore | None = None,
        uploads_root: str | Path | None = None,
    ) -> None:
        self._asset_store = asset_store if asset_store is not None else ConversationAssetStore()
        self._uploads_root = Path(
            uploads_root if uploads_root is not None else upload_dir()
        ).resolve()

    def __call__(self, conversation_id: str, upload_id: str) -> bool:
        owned_asset = any(
            self._upload_id_from_source_url(str(asset.get("source_url") or ""))
            == upload_id
            for asset in self._asset_store.list_assets(conversation_id)
        )
        if not owned_asset or not self._uploads_root.is_dir():
            return False
        return any(
            candidate.is_file()
            and (
                candidate.name == upload_id
                or candidate.name.startswith(f"{upload_id}.")
            )
            for candidate in self._uploads_root.iterdir()
        )

    @staticmethod
    def _upload_id_from_source_url(source_url: str) -> str | None:
        path = urlparse(source_url.strip()).path
        for prefix in ("/api/note/uploads/", "/api/uploads/"):
            if not path.startswith(prefix):
                continue
            upload_id = path[len(prefix) :].strip("/")
            if upload_id and "/" not in upload_id:
                return upload_id
        return None


class WhiteboardRepository:
    def __init__(
        self,
        session_factory: sessionmaker,
        file_asset_resolver: Callable[[str, str], bool] | None = None,
    ):
        self._session_factory = session_factory
        self._file_asset_resolver = (
            file_asset_resolver
            if file_asset_resolver is not None
            else ConversationFileAssetResolver()
        )

    def create(
        self,
        conversation_id: str,
        title: str,
        description: str = "",
    ) -> WhiteboardSnapshot:
        conversation_id = self._bounded_required(conversation_id, "conversation_id", 200)
        title = self._bounded_required(title, "title", 200)
        description = self._bounded_optional(description, "description", 2_000)
        board = WhiteboardRow(
            id=f"wb_{uuid.uuid4().hex}",
            conversation_id=conversation_id,
            title=title,
            description=description,
            schema_version=1,
            revision=1,
            viewport_json=self._dump_json({"x": 0.0, "y": 0.0, "zoom": 1.0}),
            status="active",
        )
        with self._session_factory.begin() as session:
            session.add(board)
            session.flush()
            session.refresh(board)
            return self._snapshot(session, board)

    def list_for_conversation(self, conversation_id: str) -> list[WhiteboardSummary]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(WhiteboardRow)
                .where(
                    WhiteboardRow.conversation_id == conversation_id,
                    WhiteboardRow.deleted_at.is_(None),
                    WhiteboardRow.status == "active",
                )
                .order_by(WhiteboardRow.updated_at.desc(), WhiteboardRow.id.asc())
            ).all()
            return [self._summary(row) for row in rows]

    def get(self, conversation_id: str, whiteboard_id: str) -> WhiteboardSnapshot:
        with self._session_factory() as session:
            board = self._active_board(session, conversation_id, whiteboard_id)
            return self._snapshot(session, board)

    def apply_mutations(
        self,
        conversation_id: str,
        whiteboard_id: str,
        base_revision: int,
        operations: list[WhiteboardOperation] | list[dict[str, Any]],
    ) -> WhiteboardMutationResult:
        parsed_operations = _OPERATIONS_ADAPTER.validate_python(operations)
        if not parsed_operations:
            raise ValueError("at least one whiteboard operation is required")

        with self._write_session() as session:
            board = self._active_board(session, conversation_id, whiteboard_id)
            if board.revision != base_revision:
                raise WhiteboardRevisionConflict(board.revision)

            initial_cards = self._load_cards(session, board.id)
            initial_relations = self._load_relations(session, board.id)
            cards = {card_id: card.model_copy(deep=True) for card_id, card in initial_cards.items()}
            relations = {
                relation_id: relation.model_copy(deep=True)
                for relation_id, relation in initial_relations.items()
            }
            initial_viewport = WhiteboardViewport.model_validate(
                self._load_json(board.viewport_json)
            )
            viewport = initial_viewport.model_copy(deep=True)

            for operation in parsed_operations:
                if isinstance(operation, CardCreateOp):
                    self._simulate_card_create(session, board, cards, operation)
                elif isinstance(operation, CardUpdateOp):
                    self._simulate_card_update(session, board, cards, operation)
                elif isinstance(operation, CardDeleteOp):
                    self._simulate_card_delete(cards, relations, operation)
                elif isinstance(operation, CardMoveResizeOp):
                    self._simulate_card_move_resize(cards, operation)
                elif isinstance(operation, RelationCreateOp):
                    self._simulate_relation_create(session, cards, relations, operation)
                elif isinstance(operation, RelationUpdateOp):
                    self._simulate_relation_update(cards, relations, operation)
                elif isinstance(operation, RelationDeleteOp):
                    self._simulate_relation_delete(relations, operation)
                elif isinstance(operation, ViewportUpdateOp):
                    viewport = operation.as_viewport()

            changed_cards = {
                card_id
                for card_id, card in cards.items()
                if card_id not in initial_cards or card != initial_cards[card_id]
            }
            changed_relations = {
                relation_id
                for relation_id, relation in relations.items()
                if relation_id not in initial_relations or relation != initial_relations[relation_id]
            }
            deleted_card_ids = sorted(set(initial_cards) - set(cards))
            deleted_relation_ids = sorted(set(initial_relations) - set(relations))

            self._persist_state_diff(
                session,
                board,
                initial_cards,
                cards,
                initial_relations,
                relations,
                viewport,
            )
            session.flush()

            next_revision = base_revision + 1
            revision_update = session.execute(
                update(WhiteboardRow)
                .where(
                    WhiteboardRow.id == board.id,
                    WhiteboardRow.conversation_id == conversation_id,
                    WhiteboardRow.deleted_at.is_(None),
                    WhiteboardRow.revision == base_revision,
                )
                .values(revision=next_revision, updated_at=datetime.now(timezone.utc))
                .execution_options(synchronize_session=False)
            )
            if revision_update.rowcount != 1:
                current_revision = session.scalar(
                    select(WhiteboardRow.revision).where(WhiteboardRow.id == board.id)
                )
                raise WhiteboardRevisionConflict(int(current_revision or base_revision))

            return WhiteboardMutationResult(
                revision=next_revision,
                cards=sorted(
                    (cards[card_id] for card_id in changed_cards),
                    key=lambda card: (card.z_index, card.id),
                ),
                relations=sorted(
                    (relations[relation_id] for relation_id in changed_relations),
                    key=lambda relation: relation.id,
                ),
                deleted_card_ids=deleted_card_ids,
                deleted_relation_ids=deleted_relation_ids,
                viewport=viewport if viewport != initial_viewport else None,
            )

    def soft_delete(self, conversation_id: str, whiteboard_id: str) -> None:
        with self._write_session() as session:
            board = self._active_board(session, conversation_id, whiteboard_id)
            self._ensure_not_referenced_by_active_board(session, board)
            board.status = "archived"
            board.deleted_at = datetime.now(timezone.utc)
            board.updated_at = datetime.now(timezone.utc)

    @contextmanager
    def _write_session(self) -> Iterator[Session]:
        session = self._session_factory()
        try:
            if session.get_bind().dialect.name == "sqlite":
                session.execute(text("BEGIN IMMEDIATE"))
            else:
                session.begin()
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def _ensure_not_referenced_by_active_board(
        self,
        session: Session,
        board: WhiteboardRow,
    ) -> None:
        nested_rows = session.scalars(
            select(WhiteboardCardRow)
            .join(
                WhiteboardRow,
                WhiteboardCardRow.whiteboard_id == WhiteboardRow.id,
            )
            .where(
                WhiteboardRow.conversation_id == board.conversation_id,
                WhiteboardRow.deleted_at.is_(None),
                WhiteboardRow.status == "active",
                WhiteboardRow.id != board.id,
                WhiteboardCardRow.card_type == "whiteboard",
            )
        ).all()
        for nested_row in nested_rows:
            content = self._load_json(nested_row.content_json)
            if content.get("child_whiteboard_id") == board.id:
                raise ValueError("whiteboard is referenced by an active nested card")

    def _simulate_card_create(
        self,
        session: Session,
        board: WhiteboardRow,
        cards: dict[str, WhiteboardCard],
        operation: CardCreateOp,
    ) -> None:
        if operation.card.id in cards or session.get(WhiteboardCardRow, operation.card.id) is not None:
            raise ValueError(f"card already exists: {operation.card.id}")
        self._validate_file_asset(board.conversation_id, operation.card)
        cards[operation.card.id] = operation.card.model_copy(deep=True)
        if operation.card.type == "whiteboard":
            self._validate_nested_board_graph(session, board, cards)

    def _simulate_card_update(
        self,
        session: Session,
        board: WhiteboardRow,
        cards: dict[str, WhiteboardCard],
        operation: CardUpdateOp,
    ) -> None:
        current = cards.get(operation.card_id)
        if current is None:
            raise ValueError(f"card does not belong to whiteboard: {operation.card_id}")
        candidate = current.model_dump()
        candidate.update(operation.patch.model_dump(exclude_unset=True))
        updated_card = WhiteboardCard.model_validate(candidate)
        self._validate_file_asset(board.conversation_id, updated_card)
        cards[operation.card_id] = updated_card
        if current.type == "whiteboard" or updated_card.type == "whiteboard":
            self._validate_nested_board_graph(session, board, cards)

    def _validate_file_asset(
        self,
        conversation_id: str,
        card: WhiteboardCard,
    ) -> None:
        if card.type != "file":
            return
        try:
            is_valid = bool(
                self._file_asset_resolver(
                    conversation_id,
                    str(card.content["upload_id"]),
                )
            )
        except Exception:
            raise ValueError("file asset could not be verified") from None
        if not is_valid:
            raise ValueError("file asset is missing or belongs to another conversation")

    @staticmethod
    def _simulate_card_delete(
        cards: dict[str, WhiteboardCard],
        relations: dict[str, WhiteboardRelation],
        operation: CardDeleteOp,
    ) -> None:
        if operation.card_id not in cards:
            raise ValueError(f"card does not belong to whiteboard: {operation.card_id}")
        del cards[operation.card_id]
        for relation_id in [
            relation_id
            for relation_id, relation in relations.items()
            if operation.card_id in {relation.source_card_id, relation.target_card_id}
        ]:
            del relations[relation_id]

    @staticmethod
    def _simulate_card_move_resize(
        cards: dict[str, WhiteboardCard],
        operation: CardMoveResizeOp,
    ) -> None:
        for item in operation.items:
            current = cards.get(item.card_id)
            if current is None:
                raise ValueError(f"card does not belong to whiteboard: {item.card_id}")
            changes: dict[str, Any] = {}
            if item.position is not None:
                changes["position"] = item.position
            if item.size is not None:
                changes["size"] = item.size
            cards[item.card_id] = current.model_copy(update=changes, deep=True)

    @staticmethod
    def _validate_relation_endpoints(
        cards: dict[str, WhiteboardCard],
        relation: WhiteboardRelation,
    ) -> None:
        if relation.source_card_id not in cards or relation.target_card_id not in cards:
            raise ValueError("relation endpoints must belong to the current whiteboard")

    def _simulate_relation_create(
        self,
        session: Session,
        cards: dict[str, WhiteboardCard],
        relations: dict[str, WhiteboardRelation],
        operation: RelationCreateOp,
    ) -> None:
        if (
            operation.relation.id in relations
            or session.get(WhiteboardRelationRow, operation.relation.id) is not None
        ):
            raise ValueError(f"relation already exists: {operation.relation.id}")
        self._validate_relation_endpoints(cards, operation.relation)
        relations[operation.relation.id] = operation.relation.model_copy(deep=True)

    def _simulate_relation_update(
        self,
        cards: dict[str, WhiteboardCard],
        relations: dict[str, WhiteboardRelation],
        operation: RelationUpdateOp,
    ) -> None:
        current = relations.get(operation.relation_id)
        if current is None:
            raise ValueError(f"relation does not belong to whiteboard: {operation.relation_id}")
        candidate = current.model_dump()
        candidate.update(operation.patch.model_dump(exclude_unset=True))
        updated_relation = WhiteboardRelation.model_validate(candidate)
        self._validate_relation_endpoints(cards, updated_relation)
        relations[operation.relation_id] = updated_relation

    @staticmethod
    def _simulate_relation_delete(
        relations: dict[str, WhiteboardRelation],
        operation: RelationDeleteOp,
    ) -> None:
        if operation.relation_id not in relations:
            raise ValueError(f"relation does not belong to whiteboard: {operation.relation_id}")
        del relations[operation.relation_id]

    def _validate_nested_board_graph(
        self,
        session: Session,
        board: WhiteboardRow,
        current_cards: dict[str, WhiteboardCard],
    ) -> None:
        board_rows = session.scalars(
            select(WhiteboardRow).where(
                WhiteboardRow.conversation_id == board.conversation_id,
                WhiteboardRow.deleted_at.is_(None),
                WhiteboardRow.status == "active",
            )
        ).all()
        board_ids = {row.id for row in board_rows}
        adjacency: dict[str, set[str]] = {board_id: set() for board_id in board_ids}

        other_nested_cards = session.scalars(
            select(WhiteboardCardRow).where(
                WhiteboardCardRow.card_type == "whiteboard",
                WhiteboardCardRow.whiteboard_id.in_(board_ids - {board.id}),
            )
        ).all()
        for nested_card in other_nested_cards:
            content = self._load_json(nested_card.content_json)
            child_id = content.get("child_whiteboard_id")
            if child_id in board_ids:
                adjacency[nested_card.whiteboard_id].add(child_id)

        for card in current_cards.values():
            if card.type != "whiteboard":
                continue
            child_id = str(card.content["child_whiteboard_id"])
            if child_id not in board_ids:
                raise ValueError("nested whiteboard must belong to the same conversation")
            if child_id == board.id:
                raise ValueError("nested whiteboard cycle detected")
            adjacency[board.id].add(child_id)

        def reaches_current(start_id: str) -> bool:
            pending = [start_id]
            visited: set[str] = set()
            while pending:
                candidate = pending.pop()
                if candidate == board.id:
                    return True
                if candidate in visited:
                    continue
                visited.add(candidate)
                pending.extend(adjacency.get(candidate, ()))
            return False

        if any(reaches_current(child_id) for child_id in adjacency[board.id]):
            raise ValueError("nested whiteboard cycle detected")

    def _persist_state_diff(
        self,
        session: Session,
        board: WhiteboardRow,
        initial_cards: dict[str, WhiteboardCard],
        cards: dict[str, WhiteboardCard],
        initial_relations: dict[str, WhiteboardRelation],
        relations: dict[str, WhiteboardRelation],
        viewport: WhiteboardViewport,
    ) -> None:
        for relation_id in sorted(set(initial_relations) - set(relations)):
            relation_row = session.get(WhiteboardRelationRow, relation_id)
            if relation_row is not None and relation_row.whiteboard_id == board.id:
                session.delete(relation_row)

        for card_id in sorted(set(initial_cards) - set(cards)):
            card_row = session.get(WhiteboardCardRow, card_id)
            if card_row is not None and card_row.whiteboard_id == board.id:
                session.delete(card_row)

        for card_id, card in cards.items():
            if card_id in initial_cards and card == initial_cards[card_id]:
                continue
            row = session.get(WhiteboardCardRow, card_id)
            if row is None:
                row = WhiteboardCardRow(id=card_id, whiteboard_id=board.id)
                session.add(row)
            self._write_card_row(row, card)

        for relation_id, relation in relations.items():
            if relation_id in initial_relations and relation == initial_relations[relation_id]:
                continue
            row = session.get(WhiteboardRelationRow, relation_id)
            if row is None:
                row = WhiteboardRelationRow(id=relation_id, whiteboard_id=board.id)
                session.add(row)
            self._write_relation_row(row, relation)

        board.viewport_json = self._dump_json(viewport.model_dump())

    def _load_cards(self, session: Session, whiteboard_id: str) -> dict[str, WhiteboardCard]:
        rows = session.scalars(
            select(WhiteboardCardRow).where(WhiteboardCardRow.whiteboard_id == whiteboard_id)
        ).all()
        return {row.id: self._card_from_row(row) for row in rows}

    def _load_relations(
        self,
        session: Session,
        whiteboard_id: str,
    ) -> dict[str, WhiteboardRelation]:
        rows = session.scalars(
            select(WhiteboardRelationRow).where(
                WhiteboardRelationRow.whiteboard_id == whiteboard_id
            )
        ).all()
        return {row.id: self._relation_from_row(row) for row in rows}

    def _snapshot(self, session: Session, board: WhiteboardRow) -> WhiteboardSnapshot:
        cards = sorted(
            self._load_cards(session, board.id).values(),
            key=lambda card: (card.z_index, card.id),
        )
        relations = sorted(
            self._load_relations(session, board.id).values(),
            key=lambda relation: relation.id,
        )
        note_link_row = session.get(WhiteboardNoteLinkRow, board.id)
        note_link = None
        if note_link_row is not None:
            note_link = WhiteboardNoteLink(
                note_task_id=note_link_row.note_task_id,
                published_revision=note_link_row.published_revision,
                published_at=note_link_row.published_at,
                updated_at=note_link_row.updated_at,
            )
        return WhiteboardSnapshot(
            id=board.id,
            conversation_id=board.conversation_id,
            title=board.title,
            description=board.description or "",
            schema_version=board.schema_version,
            revision=board.revision,
            viewport=WhiteboardViewport.model_validate(self._load_json(board.viewport_json)),
            cards=cards,
            relations=relations,
            note_link=note_link,
            legacy_canvas_id=board.legacy_canvas_id,
        )

    @staticmethod
    def _summary(board: WhiteboardRow) -> WhiteboardSummary:
        return WhiteboardSummary(
            id=board.id,
            conversation_id=board.conversation_id,
            title=board.title,
            description=board.description or "",
            schema_version=board.schema_version,
            revision=board.revision,
            legacy_canvas_id=board.legacy_canvas_id,
            status=board.status,
            updated_at=board.updated_at,
        )

    @staticmethod
    def _active_board(
        session: Session,
        conversation_id: str,
        whiteboard_id: str,
    ) -> WhiteboardRow:
        board = session.scalar(
            select(WhiteboardRow).where(
                WhiteboardRow.id == whiteboard_id,
                WhiteboardRow.conversation_id == conversation_id,
                WhiteboardRow.deleted_at.is_(None),
                WhiteboardRow.status == "active",
            )
        )
        if board is None:
            raise LookupError("whiteboard not found")
        return board

    def _card_from_row(self, row: WhiteboardCardRow) -> WhiteboardCard:
        return WhiteboardCard(
            id=row.id,
            type=row.card_type,
            title=row.title,
            description=row.description or "",
            content=self._load_json(row.content_json),
            source_refs=self._load_json(row.source_refs_json),
            position={"x": row.x, "y": row.y},
            size={"width": row.width, "height": row.height},
            z_index=row.z_index,
            collapsed=row.collapsed,
        )

    def _relation_from_row(self, row: WhiteboardRelationRow) -> WhiteboardRelation:
        return WhiteboardRelation(
            id=row.id,
            source_card_id=row.source_card_id,
            target_card_id=row.target_card_id,
            relation_type=row.relation_type,
            label=row.label or "",
            description=row.description or "",
            line_type=row.line_type,
            direction=row.direction,
            source_refs=self._load_json(row.source_refs_json),
            style=self._load_json(row.style_json),
        )

    def _write_card_row(self, row: WhiteboardCardRow, card: WhiteboardCard) -> None:
        row.card_type = card.type
        row.title = card.title
        row.description = card.description
        row.content_json = self._dump_json(card.content)
        row.source_refs_json = self._dump_json(
            [source.model_dump(mode="json") for source in card.source_refs]
        )
        row.x = card.position.x
        row.y = card.position.y
        row.width = card.size.width
        row.height = card.size.height
        row.z_index = card.z_index
        row.collapsed = card.collapsed

    def _write_relation_row(
        self,
        row: WhiteboardRelationRow,
        relation: WhiteboardRelation,
    ) -> None:
        row.source_card_id = relation.source_card_id
        row.target_card_id = relation.target_card_id
        row.relation_type = relation.relation_type
        row.label = relation.label
        row.description = relation.description
        row.line_type = relation.line_type
        row.direction = relation.direction
        row.source_refs_json = self._dump_json(
            [source.model_dump(mode="json") for source in relation.source_refs]
        )
        row.style_json = self._dump_json(relation.style)

    @staticmethod
    def _load_json(raw: str) -> Any:
        return json.loads(raw)

    @staticmethod
    def _dump_json(value: Any) -> str:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)

    @staticmethod
    def _bounded_required(value: str, field_name: str, max_length: int) -> str:
        normalized = str(value or "").strip()
        if not normalized or len(normalized) > max_length:
            raise ValueError(f"{field_name} must contain 1 to {max_length} characters")
        return normalized

    @staticmethod
    def _bounded_optional(value: str, field_name: str, max_length: int) -> str:
        normalized = str(value or "")
        if len(normalized) > max_length:
            raise ValueError(f"{field_name} must not exceed {max_length} characters")
        return normalized
