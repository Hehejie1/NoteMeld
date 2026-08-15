from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from app.db.engine import SessionLocal
from app.db.models.whiteboard import (
    Whiteboard as WhiteboardRow,
    WhiteboardNoteLink as WhiteboardNoteLinkRow,
)
from app.models.whiteboard import (
    WhiteboardCard,
    WhiteboardRelation,
    WhiteboardSnapshot,
    WhiteboardSourceRef,
)
from app.services.note_import_service import ImportNoteRequest, NoteImportService
from app.services.note_output_normalizer import normalize_note_output
from app.services.whiteboard_repository import (
    WhiteboardRepository,
    WhiteboardRevisionConflict,
)


PublishScope = Literal["all", "selection"]
_URL_PATTERN = re.compile(r"https?://[^\s<>()\]]+")
_WHOLE_DOCUMENT_FENCE = re.compile(
    r"\A```(?:markdown|md|html)?[ \t]*\r?\n[\s\S]*\r?\n```[ \t]*\Z",
    re.IGNORECASE,
)


class WhiteboardPublishResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    whiteboard_id: str
    note_task_id: str
    published_revision: int
    status: Literal["published", "partial"]
    wiki_status: str
    diagnostics: list[str] = Field(default_factory=list)
    retry_actions: list[dict[str, str]] = Field(default_factory=list)
    message: str


class WhiteboardNotePublishService:
    _publish_locks_guard = threading.Lock()
    _publish_locks: dict[str, threading.RLock] = {}

    def __init__(
        self,
        *,
        repository: WhiteboardRepository | None = None,
        note_importer: NoteImportService | None = None,
        llm_compiler: Callable[..., str] | None = None,
    ) -> None:
        self.repository = repository or WhiteboardRepository(SessionLocal)
        self.note_importer = note_importer or NoteImportService()
        self.llm_compiler = llm_compiler

    def publish(
        self,
        conversation_id: str,
        whiteboard_id: str,
        base_revision: int,
        scope: PublishScope,
        card_ids: list[str],
        relation_ids: list[str],
        provider_id: str | None,
        model_name: str | None,
    ) -> WhiteboardPublishResult:
        with self._publish_lock(whiteboard_id):
            return self._publish_locked(
                conversation_id,
                whiteboard_id,
                base_revision,
                scope,
                card_ids,
                relation_ids,
                provider_id,
                model_name,
            )

    def _publish_locked(
        self,
        conversation_id: str,
        whiteboard_id: str,
        base_revision: int,
        scope: PublishScope,
        card_ids: list[str],
        relation_ids: list[str],
        provider_id: str | None,
        model_name: str | None,
    ) -> WhiteboardPublishResult:
        board = self.repository.get(conversation_id, whiteboard_id)
        if board.revision != base_revision:
            raise WhiteboardRevisionConflict(board.revision)

        markdown = self.compile_markdown(
            board,
            scope=scope,
            card_ids=card_ids,
            relation_ids=relation_ids,
            provider_id=provider_id,
            model_name=model_name,
        )
        source_ids = self._source_ids_for_markdown(
            *self._resolve_scope(board, scope, card_ids, relation_ids)
        )
        previous_note_id = board.note_link.note_task_id if board.note_link else None
        imported = self.note_importer.publish_revision(
            ImportNoteRequest(
                title=board.title,
                content=markdown,
                format="markdown",
                source_url=f"notemeld://whiteboard/{board.id}",
                source_type="whiteboard",
                tags=["whiteboard"],
                metadata={
                    "whiteboard_id": board.id,
                    "revision": board.revision,
                    "scope": scope,
                    "source_ids": source_ids,
                },
            ),
            conversation_id,
            note_id=previous_note_id,
            commit_hook=lambda note_id: self._commit_note_link(
                conversation_id,
                whiteboard_id,
                base_revision,
                note_id,
            ),
        )
        return WhiteboardPublishResult(
            whiteboard_id=board.id,
            note_task_id=imported.note_id,
            published_revision=base_revision,
            status="partial" if imported.diagnostics else "published",
            wiki_status=imported.wiki_status,
            diagnostics=imported.diagnostics,
            retry_actions=imported.retry_actions,
            message=imported.message,
        )

    @classmethod
    def _publish_lock(cls, whiteboard_id: str) -> threading.RLock:
        with cls._publish_locks_guard:
            lock = cls._publish_locks.get(whiteboard_id)
            if lock is None:
                lock = threading.RLock()
                cls._publish_locks[whiteboard_id] = lock
            return lock

    def compile_markdown(
        self,
        board: WhiteboardSnapshot,
        *,
        scope: PublishScope,
        card_ids: list[str],
        relation_ids: list[str],
        provider_id: str | None = None,
        model_name: str | None = None,
    ) -> str:
        cards, relations = self._resolve_scope(
            board,
            scope,
            card_ids,
            relation_ids,
        )
        fallback = self._compile_fallback(board, cards, relations)
        if not provider_id or not model_name:
            return normalize_note_output(fallback, ["markdown"]).strip()

        try:
            if self.llm_compiler is not None:
                candidate = self.llm_compiler(
                    board=board,
                    cards=cards,
                    relations=relations,
                    fallback_markdown=fallback,
                    provider_id=provider_id,
                    model_name=model_name,
                )
            else:
                candidate = self._compile_with_saved_model(
                    board,
                    cards,
                    relations,
                    fallback,
                    provider_id,
                    model_name,
                )
            if self._valid_model_markdown(candidate, cards, relations):
                return normalize_note_output(candidate, ["markdown"]).strip()
        except Exception:
            pass
        return normalize_note_output(fallback, ["markdown"]).strip()

    @staticmethod
    def _resolve_scope(
        board: WhiteboardSnapshot,
        scope: PublishScope,
        card_ids: list[str],
        relation_ids: list[str],
    ) -> tuple[list[WhiteboardCard], list[WhiteboardRelation]]:
        if scope not in {"all", "selection"}:
            raise ValueError("unsupported publish scope")
        card_by_id = {card.id: card for card in board.cards}
        relation_by_id = {relation.id: relation for relation in board.relations}
        if scope == "all":
            selected_cards = list(board.cards)
            selected_relations = list(board.relations)
        else:
            requested_cards = list(dict.fromkeys(card_ids))
            requested_relations = list(dict.fromkeys(relation_ids))
            if len(requested_cards) > 20 or len(requested_relations) > 40:
                raise ValueError("whiteboard selection exceeds publish limits")
            missing_cards = [card_id for card_id in requested_cards if card_id not in card_by_id]
            missing_relations = [
                relation_id
                for relation_id in requested_relations
                if relation_id not in relation_by_id
            ]
            if missing_cards or missing_relations:
                raise ValueError("selected item does not belong to whiteboard")
            selected_card_ids = set(requested_cards)
            selected_relations = [relation_by_id[item] for item in requested_relations]
            for relation in selected_relations:
                selected_card_ids.add(relation.source_card_id)
                selected_card_ids.add(relation.target_card_id)
            if len(selected_card_ids) > 20:
                raise ValueError("whiteboard selection exceeds publish limits")
            selected_cards = [card_by_id[item] for item in selected_card_ids]
            if not selected_cards:
                raise ValueError("selection publish requires at least one card")

        if not selected_cards:
            raise ValueError("publish requires at least one card")

        selected_cards.sort(key=lambda card: (card.position.y, card.position.x, card.id))
        title_by_id = {card.id: card.title for card in selected_cards}
        selected_relations = [
            relation
            for relation in selected_relations
            if relation.source_card_id in title_by_id
            and relation.target_card_id in title_by_id
        ]
        selected_relations.sort(
            key=lambda relation: (
                title_by_id[relation.source_card_id],
                title_by_id[relation.target_card_id],
                relation.id,
            )
        )
        return selected_cards, selected_relations

    def _compile_fallback(
        self,
        board: WhiteboardSnapshot,
        cards: list[WhiteboardCard],
        relations: list[WhiteboardRelation],
    ) -> str:
        lines = [f"# {board.title}"]
        if board.description.strip():
            lines.extend(["", board.description.strip()])
        lines.extend(["", "## 白板内容"])
        for card in cards:
            lines.extend(["", f"## {card.title}"])
            if card.description.strip():
                lines.extend(["", card.description.strip()])
            lines.extend(["", self._card_content_markdown(card)])
            if card.source_refs:
                lines.extend(
                    ["", "来源：" + "、".join(source.source_id for source in card.source_refs)]
                )

        if relations:
            title_by_id = {card.id: card.title for card in cards}
            lines.extend(["", "## 关系与论证"])
            for relation in relations:
                annotation = relation.relation_type
                if relation.label.strip():
                    annotation += f"：{relation.label.strip()}"
                if relation.description.strip():
                    annotation += f"；{relation.description.strip()}"
                lines.append(
                    f"- {title_by_id[relation.source_card_id]} --[{annotation}]--> "
                    f"{title_by_id[relation.target_card_id]}"
                )

        sources = self._deduplicated_sources(cards, relations)
        lines.extend(["", "## 来源"])
        if not sources:
            lines.append("- 当前白板未标注来源。")
        for source in sources:
            suffix = f" — [{source.title}]({source.url})" if source.url else f" — {source.title}"
            lines.append(f"- `{source.source_id}`{suffix}")
        return "\n".join(lines).strip() + "\n"

    @staticmethod
    def _card_content_markdown(card: WhiteboardCard) -> str:
        if card.type == "markdown":
            return str(card.content["markdown"]).strip()
        if card.type == "web":
            url = str(card.content["url"])
            preview_title = str(card.content.get("preview_title") or card.title)
            return f"网页资源：[{preview_title}]({url})"
        if card.type == "file":
            return f"文件资源：`{card.content['upload_id']}`"
        child_id = str(card.content["child_whiteboard_id"])
        return f"子白板：[{card.title}](notemeld://whiteboard/{child_id})"

    @staticmethod
    def _deduplicated_sources(
        cards: list[WhiteboardCard],
        relations: list[WhiteboardRelation],
    ) -> list[WhiteboardSourceRef]:
        result: list[WhiteboardSourceRef] = []
        seen: set[str] = set()
        for owner in [*cards, *relations]:
            for source in owner.source_refs:
                if source.source_id in seen:
                    continue
                seen.add(source.source_id)
                result.append(source)
        return result

    @classmethod
    def _source_ids_for_markdown(
        cls,
        cards: list[WhiteboardCard],
        relations: list[WhiteboardRelation],
    ) -> list[str]:
        return [source.source_id for source in cls._deduplicated_sources(cards, relations)]

    @classmethod
    def _valid_model_markdown(
        cls,
        candidate: Any,
        cards: list[WhiteboardCard],
        relations: list[WhiteboardRelation],
    ) -> bool:
        if not isinstance(candidate, str):
            return False
        raw = candidate.strip()
        if not raw or _WHOLE_DOCUMENT_FENCE.fullmatch(raw):
            return False
        normalized = normalize_note_output(raw, ["markdown"]).strip()
        if not normalized or not re.search(r"(?m)^#\s+\S", normalized):
            return False
        sources = cls._deduplicated_sources(cards, relations)
        allowed_urls = {source.url.rstrip("/.,);]") for source in sources if source.url}
        seen_urls = {url.rstrip("/.,);]") for url in _URL_PATTERN.findall(normalized)}
        if not seen_urls.issubset(allowed_urls):
            return False
        return all(source.source_id in normalized for source in sources)

    @staticmethod
    def _compile_with_saved_model(
        board: WhiteboardSnapshot,
        cards: list[WhiteboardCard],
        relations: list[WhiteboardRelation],
        fallback_markdown: str,
        provider_id: str,
        model_name: str,
    ) -> str:
        from app.gpt.notemeld_gpt import NotemeldGPT
        from app.services.model import ModelService
        from app.services.provider import ProviderService

        provider = ProviderService.get_provider_by_id(provider_id)
        if not provider:
            raise ValueError("saved provider is unavailable")
        gpt = NotemeldGPT.from_config(
            ModelService.build_saved_model_config(
                provider,
                model_name,
                usage_context={
                    "phase": "whiteboard_note_publish",
                    "provider_id": provider["id"],
                },
            )
        )
        source_ids = WhiteboardNotePublishService._source_ids_for_markdown(cards, relations)
        response = gpt.create_chat_completion(
            phase_label="Whiteboard Note Publish",
            timeout=45,
            max_tokens=5000,
            request_meta={"stage": "whiteboard_publish"},
            messages=[
                {
                    "role": "system",
                    "content": (
                        "你是 NoteMeld 白板笔记编译器。只输出裸 Markdown，不要代码围栏。"
                        "必须保留输入 source id，不得补造来源、URL 或事实；关系要保留方向、名称和备注。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"允许的 source ids：{source_ids}\n"
                        "把下面确定性草稿整理为清晰笔记；不得删除可追溯来源：\n\n"
                        f"{fallback_markdown}"
                    ),
                },
            ],
        )
        return gpt._extract_message_content(response, "白板笔记编译")

    def _commit_note_link(
        self,
        conversation_id: str,
        whiteboard_id: str,
        base_revision: int,
        note_id: str,
    ) -> None:
        now = datetime.now(timezone.utc)
        with self.repository._write_session() as session:
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
            if board.revision != base_revision:
                raise WhiteboardRevisionConflict(board.revision)
            link = session.get(WhiteboardNoteLinkRow, whiteboard_id)
            if link is None:
                link = WhiteboardNoteLinkRow(
                    whiteboard_id=whiteboard_id,
                    note_task_id=note_id,
                    published_revision=base_revision,
                    published_at=now,
                    updated_at=now,
                )
                session.add(link)
            else:
                if link.note_task_id != note_id:
                    raise ValueError("whiteboard note link changed during publish")
                link.published_revision = base_revision
                link.updated_at = now
