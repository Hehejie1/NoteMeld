from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.db.engine import get_db
from app.db.models.conversation import Conversation, NoteDocument
from app.services.note_read_errors import NoteTitleAmbiguousError
from app.services.wiki_store import WikiStore
from app.utils.storage_paths import note_output_dir

logger = logging.getLogger(__name__)


def _db():
    return next(get_db())


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _document_to_dict(row: NoteDocument, include_content: bool = True) -> dict:
    payload = {
        "taskId": row.task_id,
        "title": row.title or "",
        "sourceUrl": row.source_url or "",
        "platform": row.platform or "",
        "modelName": row.model_name or "",
        "style": row.style or "",
        "status": row.status,
        "wikiStatus": row.wiki_status,
        "createdAt": row.created_at.isoformat() if row.created_at else "",
        "updatedAt": row.updated_at.isoformat() if row.updated_at else "",
    }
    if include_content:
        payload["content"] = row.content or ""
    return payload


def upsert_note_document(data: dict[str, Any]) -> dict:
    if not data.get("task_id") or not data.get("conversation_id"):
        raise ValueError("note document requires task_id and conversation_id")

    db = _db()
    try:
        row = db.query(NoteDocument).filter(NoteDocument.task_id == data["task_id"]).first()
        if row is None:
            row = NoteDocument(task_id=data["task_id"], conversation_id=data["conversation_id"])
            db.add(row)

        row.conversation_id = data["conversation_id"]
        row.title = data.get("title", row.title or "")
        row.content = data.get("content", row.content or "")
        row.source_url = data.get("source_url", row.source_url)
        row.platform = data.get("platform", row.platform)
        row.model_name = data.get("model_name", row.model_name)
        row.style = data.get("style", row.style)
        row.status = data.get("status", row.status or "SUCCESS")
        row.wiki_status = data.get("wiki_status", row.wiki_status or "pending")
        row.deleted_at = None
        row.updated_at = _now_dt()
        db.commit()
        db.refresh(row)
        return _document_to_dict(row)
    finally:
        db.close()


def list_note_documents(conversation_id: str, include_content: bool = True) -> list[dict]:
    db = _db()
    try:
        rows = (
            db.query(NoteDocument)
            .filter(NoteDocument.conversation_id == conversation_id, NoteDocument.deleted_at.is_(None))
            .order_by(NoteDocument.created_at.desc(), NoteDocument.updated_at.desc())
            .all()
        )
        return [_document_to_dict(row, include_content=include_content) for row in rows]
    finally:
        db.close()


def get_note_document_task_ids(conversation_id: str) -> list[str]:
    db = _db()
    try:
        rows = (
            db.query(NoteDocument.task_id)
            .filter(NoteDocument.conversation_id == conversation_id, NoteDocument.deleted_at.is_(None))
            .order_by(NoteDocument.created_at.asc(), NoteDocument.updated_at.asc())
            .all()
        )
        return [row[0] for row in rows if row[0]]
    finally:
        db.close()


def search_note_documents_by_title(query: str, limit: int = 10) -> list[dict]:
    normalized = (query or "").strip()
    if not normalized:
        return []

    db = _db()
    try:
        rows = (
            db.query(NoteDocument)
            .join(Conversation, Conversation.id == NoteDocument.conversation_id)
            .filter(
                NoteDocument.deleted_at.is_(None),
                Conversation.deleted_at.is_(None),
                NoteDocument.title.ilike(f"%{normalized}%"),
            )
            .order_by(NoteDocument.updated_at.desc(), NoteDocument.created_at.desc())
            .limit(max(1, min(int(limit or 10), 50)))
            .all()
        )
        return [_document_to_dict(row, include_content=True) for row in rows]
    finally:
        db.close()


def read_note_document_by_title(title: str) -> dict | None:
    normalized = (title or "").strip()
    if not normalized:
        return None

    db = _db()
    try:
        rows = (
            db.query(NoteDocument)
            .join(Conversation, Conversation.id == NoteDocument.conversation_id)
            .filter(
                NoteDocument.deleted_at.is_(None),
                Conversation.deleted_at.is_(None),
                NoteDocument.title == normalized,
            )
            .order_by(NoteDocument.updated_at.desc(), NoteDocument.created_at.desc())
            .limit(2)
            .all()
        )
        if not rows:
            return None
        if len(rows) > 1:
            raise NoteTitleAmbiguousError(f"标题“{normalized}”存在多篇笔记，请先重命名后再读取")
        return _document_to_dict(rows[0], include_content=True)
    finally:
        db.close()


def update_note_document_wiki_status(task_id: str, wiki_status: str) -> bool:
    if not task_id:
        return False

    db = _db()
    try:
        row = (
            db.query(NoteDocument)
            .filter(NoteDocument.task_id == task_id, NoteDocument.deleted_at.is_(None))
            .first()
        )
        if row is None:
            return False

        row.wiki_status = wiki_status
        row.updated_at = _now_dt()
        db.commit()
        return True
    finally:
        db.close()


def soft_delete_note_document(conversation_id: str, task_id: str) -> bool:
    db = _db()
    try:
        row = (
            db.query(NoteDocument)
            .filter(
                NoteDocument.conversation_id == conversation_id,
                NoteDocument.task_id == task_id,
                NoteDocument.deleted_at.is_(None),
            )
            .first()
        )
        if row is None:
            return False

        row.deleted_at = _now_dt()
        row.updated_at = _now_dt()
        db.commit()
        return True
    finally:
        db.close()


def soft_delete_note_documents_by_conversation(conversation_id: str) -> int:
    db = _db()
    try:
        rows = (
            db.query(NoteDocument)
            .filter(
                NoteDocument.conversation_id == conversation_id,
                NoteDocument.deleted_at.is_(None),
            )
            .all()
        )
        now = _now_dt()
        for row in rows:
            row.deleted_at = now
            row.updated_at = now
        db.commit()
        return len(rows)
    finally:
        db.close()


def delete_note_task_artifacts(task_id: str, output_dir: Path | None = None) -> dict:
    """Delete generated document artifacts and revoke its Wiki contribution."""
    if not task_id:
        return {"deleted_files": [], "wiki_removed": False}

    base_dir = output_dir or note_output_dir()
    deleted_files: list[str] = []
    for path in base_dir.glob(f"{task_id}*"):
        if path.is_file():
            path.unlink(missing_ok=True)
            deleted_files.append(str(path))

    mapping_path = base_dir / "task_conversations" / f"{task_id}.json"
    if mapping_path.exists():
        mapping_path.unlink(missing_ok=True)
        deleted_files.append(str(mapping_path))

    wiki_removed = False
    wiki_error = ""
    try:
        WikiStore(base_dir=base_dir / "wiki").remove_source(task_id)
        wiki_removed = True
    except Exception as exc:
        logger.exception("删除任务 Wiki 贡献失败: task_id=%s", task_id)
        wiki_error = str(exc)
        wiki_removed = False

    return {"deleted_files": deleted_files, "wiki_removed": wiki_removed, "wiki_error": wiki_error}
