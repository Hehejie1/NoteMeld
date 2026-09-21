from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from app.services.note_import_service import ImportNoteRequest


class ConversationImportRequest(BaseModel):
    import_mode: str
    conversation_id: Optional[str] = None
    title: Optional[str] = None
    content: str
    format: str = "markdown"
    file_name: Optional[str] = None
    source_url: Optional[str] = None
    source_type: str = "manual"
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationImportResult(BaseModel):
    conversation_id: str
    conversation_title: str
    import_mode: str
    asset_id: str = ""
    note_id: str = ""
    document_task_id: str = ""
    message_id: str = ""
    status: str = "imported"
    wiki_status: str = "pending"


def _default_asset_store():
    from app.services.conversation_asset_store import ConversationAssetStore

    return ConversationAssetStore()


def _default_conversation_upserter(payload: dict[str, Any]) -> dict:
    from app.services.conversation_store import upsert_conversation

    return upsert_conversation(payload)


def _default_note_importer():
    from app.services.note_import_service import NoteImportService

    return NoteImportService()


def _default_note_result_appender(conversation_id: str, task_id: str, payload: dict[str, Any]) -> dict:
    from app.services.conversation_store import append_message

    return append_message(
        conversation_id,
        {
            "id": payload["message_id"],
            "role": "assistant",
            "message_type": "note_result",
            "content": payload["content"],
            "status": payload.get("status", "success"),
            "meta": {
                "task_id": task_id,
                "title": payload.get("title", ""),
                "source_url": payload.get("source_url", ""),
                "platform": payload.get("platform", ""),
                "import_kind": payload.get("import_kind", ""),
            },
        },
    )


def _default_task_conversation_register(task_id: str, conversation_id: str, source_url: Optional[str] = None) -> None:
    from app.services.task_status_writer import register_task_conversation

    register_task_conversation(task_id, conversation_id, source_url=source_url)


def _default_note_document_upserter(payload: dict[str, Any]) -> dict:
    from app.services.note_document_store import upsert_note_document

    return upsert_note_document(payload)


class ConversationImportService:
    def __init__(self, asset_store: Any = None, conversation_upserter: Optional[Callable[[dict[str, Any]], dict]] = None, note_importer: Any = None, note_result_appender: Optional[Callable[[str, str, dict[str, Any]], dict]] = None, note_document_upserter: Optional[Callable[[dict[str, Any]], dict]] = None, task_conversation_register: Optional[Callable[..., None]] = None):
        self.asset_store = asset_store or _default_asset_store()
        self.conversation_upserter = conversation_upserter or _default_conversation_upserter
        self.note_importer = note_importer or _default_note_importer()
        self.note_result_appender = note_result_appender or _default_note_result_appender
        self.note_document_upserter = note_document_upserter or _default_note_document_upserter
        self.task_conversation_register = task_conversation_register or _default_task_conversation_register

    def import_markdown(self, request: ConversationImportRequest) -> ConversationImportResult:
        import_mode = (request.import_mode or "").strip()
        if import_mode not in {"chat_asset", "note"}:
            raise ValueError("unsupported import_mode")

        content = request.content.strip()
        if not content:
            raise ValueError("content is required")

        title = self._resolve_title(request, content)
        conversation_id = (request.conversation_id or "").strip() or f"conv_{uuid.uuid4().hex}"
        if import_mode == "chat_asset":
            return self._import_chat_asset(request, conversation_id, title, content)
        return self._import_note(request, conversation_id, title, content)

    def _import_chat_asset(self, request: ConversationImportRequest, conversation_id: str, title: str, content: str) -> ConversationImportResult:
        self.conversation_upserter({"id": conversation_id, "mode": "chat", "title": title, "status": "SUCCESS"})
        asset = self.asset_store.create_asset({"conversation_id": conversation_id, "title": title, "content": content, "format": request.format, "file_name": request.file_name or "", "source_url": request.source_url or "", "source_type": request.source_type, "tags": request.tags, "metadata": request.metadata})
        return ConversationImportResult(conversation_id=conversation_id, conversation_title=title, import_mode="chat_asset", asset_id=asset["asset_id"], wiki_status="skipped")

    def _import_note(self, request: ConversationImportRequest, conversation_id: str, title: str, content: str) -> ConversationImportResult:
        self.conversation_upserter(
            {
                "id": conversation_id,
                "mode": "note",
                "title": title,
                "status": "PENDING",
                "noteState": "generating",
                "message": "",
            }
        )
        try:
            result = self.note_importer.import_note(
                ImportNoteRequest(
                    title=title,
                    content=content,
                    format=request.format,
                    source_url=request.source_url,
                    source_type=request.source_type,
                    tags=request.tags,
                    metadata=request.metadata,
                ),
                conversation_id=conversation_id,
            )
        except Exception as exc:
            self.conversation_upserter(
                {
                    "id": conversation_id,
                    "mode": "note",
                    "title": title,
                    "status": "FAILED",
                    "noteState": "failed",
                    "message": str(exc),
                }
            )
            raise
        message_id = f"note-result-{uuid.uuid4().hex}"
        self.conversation_upserter({"id": conversation_id, "mode": "note", "title": title, "status": "SUCCESS", "linkedNoteTaskId": result.note_id, "noteState": "ready"})
        self.note_document_upserter({"task_id": result.note_id, "conversation_id": conversation_id, "title": title, "content": content, "source_url": request.source_url or "", "platform": request.source_type, "model_name": "import", "style": request.format, "status": "SUCCESS", "wiki_status": result.wiki_status})
        self.task_conversation_register(result.note_id, conversation_id, request.source_url)
        self.note_result_appender(conversation_id, result.note_id, {"message_id": message_id, "content": "笔记已导入", "title": title, "source_url": request.source_url or "", "platform": request.source_type, "status": "success", "import_kind": "imported_note"})
        return ConversationImportResult(conversation_id=conversation_id, conversation_title=title, import_mode="note", note_id=result.note_id, document_task_id=result.note_id, message_id=message_id, status=result.status, wiki_status=result.wiki_status)

    @staticmethod
    def _resolve_title(request: ConversationImportRequest, content: str) -> str:
        normalized_title = (request.title or "").strip()
        if normalized_title:
            return normalized_title
        for line in content.splitlines():
            line = line.strip()
            if line.startswith("# "):
                return line[2:].strip() or "未命名笔记"
        if request.file_name:
            return Path(request.file_name).stem or "未命名笔记"
        return "未命名笔记"
