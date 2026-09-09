from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.engine import get_db
from app.db.models.conversation import Conversation, ConversationMessage
from app.utils.storage_paths import note_output_dir


def _db() -> Session:
    return next(get_db())


def _json_loads(value: str | None, default: Any):
    if not value:
        return default
    try:
        return json.loads(value)
    except Exception:
        return default


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _now_dt() -> datetime:
    return datetime.now(timezone.utc)


def _extract_title_from_markdown(markdown: str | list[dict] | None) -> str:
    content = ""
    if isinstance(markdown, str):
        content = markdown
    elif isinstance(markdown, list):
        content = next((item.get("content", "") for item in markdown if item.get("content")), "")
    for line in content.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def _hydrate_conversation_payload(conversation: Conversation) -> dict:
    payload = {
        "id": conversation.id,
        "mode": conversation.mode,
        "title": conversation.title or "",
        "status": conversation.status,
        "message": conversation.message or "",
        "platform": conversation.platform or "",
        "linkedNoteTaskId": conversation.linked_note_task_id or "",
        "noteState": conversation.note_state,
        "formData": _json_loads(conversation.form_data_json, {}),
        "transcript": _json_loads(conversation.transcript_json, {}),
        "audioMeta": _json_loads(conversation.audio_meta_json, {}),
        "markdown": _json_loads(conversation.markdown_json, ""),
        "researchSpaceId": getattr(conversation, "research_space_id", None) or None,
        "createdAt": conversation.created_at.isoformat() if conversation.created_at else _now_iso(),
        "updatedAt": conversation.updated_at.isoformat() if conversation.updated_at else _now_iso(),
        "messages": [],
        "documents": [],
        "activeDocumentTaskId": conversation.linked_note_task_id or "",
    }

    if not payload["title"]:
        payload["title"] = (
            _extract_title_from_markdown(payload["markdown"])
            or payload["audioMeta"].get("title", "")
            or payload["formData"].get("video_url", "")
            or "未命名对话"
        )
    return payload


def _message_to_dict(
    row: ConversationMessage,
    *,
    include_context_ref_authority: bool = False,
) -> dict:
    payload = {
        "id": row.id,
        "role": row.role,
        "message_type": row.message_type,
        "content": row.content,
        "status": row.status,
        "meta": _json_loads(row.meta_json, {}),
        "sources": _json_loads(row.sources_json, []),
        "error": bool(row.error),
        "createdAt": row.created_at,
        "updatedAt": row.updated_at,
    }
    if include_context_ref_authority:
        payload["context_refs_authority_version"] = int(
            row.context_refs_authority_version or 0
        )
    return payload


def _messages_for_conversation(
    db: Session,
    conversation_id: str,
    *,
    include_context_ref_authority: bool = False,
) -> list[dict]:
    rows = (
        db.query(ConversationMessage)
        .filter(ConversationMessage.conversation_id == conversation_id)
        .order_by(ConversationMessage.created_at.asc())
        .all()
    )
    return [
        _message_to_dict(
            row,
            include_context_ref_authority=include_context_ref_authority,
        )
        for row in rows
    ]


def _storage_root() -> Path:
    return Path(note_output_dir())


def _read_json_file(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    return payload if isinstance(payload, dict) else {}


def _conversation_message_exists(db: Session, conversation_id: str, task_id: str) -> bool:
    rows = (
        db.query(ConversationMessage)
        .filter(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.message_type == "note_result",
        )
        .all()
    )
    return any(_json_loads(row.meta_json, {}).get("task_id") == task_id for row in rows)


def bootstrap_conversations_from_storage() -> dict[str, int]:
    from app.services.note_document_store import upsert_note_document

    storage_root = _storage_root()
    mapping_dir = storage_root / "task_conversations"
    restored = {"conversations": 0, "messages": 0}
    if not mapping_dir.exists():
        return restored

    for mapping_path in sorted(mapping_dir.glob("*.json")):
        mapping = _read_json_file(mapping_path)
        task_id = str(mapping.get("task_id") or "").strip()
        conversation_id = str(mapping.get("conversation_id") or "").strip()
        if not task_id or not conversation_id:
            continue

        result_payload = _read_json_file(storage_root / f"{task_id}.json")
        markdown = result_payload.get("markdown", "")
        if not isinstance(markdown, str) or not markdown.strip():
            continue

        status_payload = _read_json_file(storage_root / f"{task_id}.status.json")
        status = str(status_payload.get("status") or "SUCCESS")
        message = str(status_payload.get("message") or "")
        source_url = str(
            mapping.get("source_url")
            or status_payload.get("source_url")
            or ""
        )
        extras = str(mapping.get("extras") or status_payload.get("extras") or "")
        transcript = result_payload.get("transcript", {})
        transcript = transcript if isinstance(transcript, dict) else {}
        audio_meta = result_payload.get("audio_meta", {})
        audio_meta = audio_meta if isinstance(audio_meta, dict) else {}
        title = (
            _extract_title_from_markdown(markdown)
            or str(audio_meta.get("title") or "")
            or "未命名笔记"
        )

        created_conversation = False
        db = _db()
        try:
            conversation = (
                db.query(Conversation)
                .filter(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
                .first()
            )
            if conversation is None:
                created_conversation = True
        finally:
            db.close()

        payload = upsert_conversation(
            {
                "id": conversation_id,
                "mode": "note",
                "title": title,
                "status": status,
                "message": message,
                "platform": str(audio_meta.get("platform") or ""),
                "linkedNoteTaskId": task_id,
                "noteState": "ready" if status == "SUCCESS" else "failed",
                "formData": {
                    "video_url": source_url,
                    "extras": extras,
                },
                "transcript": transcript,
                "audioMeta": audio_meta,
                "markdown": markdown,
            }
        )
        if created_conversation:
            restored["conversations"] += 1

        upsert_note_document(
            {
                "task_id": task_id,
                "conversation_id": conversation_id,
                "title": title,
                "content": markdown,
                "source_url": source_url,
                "platform": str(audio_meta.get("platform") or ""),
                "model_name": "",
                "style": "",
                "status": status,
                "wiki_status": "pending",
            }
        )

        db = _db()
        try:
            if _conversation_message_exists(db, conversation_id, task_id):
                continue
        finally:
            db.close()

        append_note_result_message(
            conversation_id,
            task_id,
            {
                "message_id": f"note-result-{task_id}",
                "content": message or title,
                "title": title,
                "source_url": source_url,
                "platform": str(audio_meta.get("platform") or ""),
                "status": "success" if status == "SUCCESS" else "failed",
            },
        )
        restored["messages"] += 1
    return restored


def list_conversations() -> list[dict]:
    db = _db()
    try:
        rows = (
            db.query(Conversation)
            .filter(Conversation.deleted_at.is_(None))
            .order_by(Conversation.updated_at.desc(), Conversation.created_at.desc())
            .all()
        )
        items = []
        for row in rows:
            payload = _hydrate_conversation_payload(row)
            payload["messages"] = []
            items.append(payload)
        return items
    finally:
        db.close()


def get_conversation(
    conversation_id: str,
    *,
    include_message_context_ref_authority: bool = False,
) -> dict | None:
    db = _db()
    try:
        row = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
            .first()
        )
        if not row:
            return None
        payload = _hydrate_conversation_payload(row)
        payload["messages"] = _messages_for_conversation(
            db,
            conversation_id,
            include_context_ref_authority=include_message_context_ref_authority,
        )
        try:
            from app.services.note_document_store import list_note_documents

            payload["documents"] = list_note_documents(conversation_id, include_content=True)
            active_document_task_id = payload.get("linkedNoteTaskId", "")
            if active_document_task_id and any(
                document.get("taskId") == active_document_task_id and document.get("content")
                for document in payload["documents"]
            ):
                payload["activeDocumentTaskId"] = active_document_task_id
            else:
                payload["activeDocumentTaskId"] = next(
                    (
                        document.get("taskId", "")
                        for document in payload["documents"]
                        if document.get("taskId") and document.get("content")
                    ),
                    active_document_task_id,
                )
        except Exception:
            payload["documents"] = []
            payload["activeDocumentTaskId"] = payload.get("linkedNoteTaskId", "")
        return payload
    finally:
        db.close()


def get_latest_message(
    conversation_id: str,
    role: str | None = None,
    message_type: str | None = None,
) -> dict | None:
    db = _db()
    try:
        query = db.query(ConversationMessage).filter(ConversationMessage.conversation_id == conversation_id)
        if role:
            query = query.filter(ConversationMessage.role == role)
        if message_type:
            query = query.filter(ConversationMessage.message_type == message_type)
        row = query.order_by(ConversationMessage.created_at.desc()).first()
        if row is None:
            return None
        return _message_to_dict(row)
    finally:
        db.close()


def get_conversation_research_space_id(conversation_id: str) -> str | None:
    """读取会话绑定的 research_space_id；容错返回 None。

    P3 阶段二：cid→rs_id 映射查询。任何异常（会话不存在 / 列缺失 / DB 错误）
    都返回 None，由调用方降级处理（不注入 rs 记忆前缀）。
    """
    if not conversation_id:
        return None
    db = _db()
    try:
        row = (
            db.query(Conversation)
            .filter(Conversation.id == conversation_id, Conversation.deleted_at.is_(None))
            .first()
        )
        if row is None:
            return None
        return getattr(row, "research_space_id", None) or None
    except Exception:  # noqa: BLE001 - 容错降级，避免影响主流程
        return None
    finally:
        db.close()


def get_latest_user_message(conversation_id: str) -> dict | None:
    return get_latest_message(conversation_id, role="user", message_type="user_input")


def get_conversation_note_task_ids(conversation_id: str) -> list[str]:
    db = _db()
    try:
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        task_ids: list[str] = []
        if conversation and conversation.linked_note_task_id:
            task_ids.append(conversation.linked_note_task_id)

        rows = (
            db.query(ConversationMessage)
            .filter(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.message_type.in_(["note_progress", "note_result"]),
            )
            .order_by(ConversationMessage.created_at.asc())
            .all()
        )
        for row in rows:
            meta = _json_loads(row.meta_json, {})
            task_id = meta.get("task_id")
            if task_id and task_id not in task_ids:
                task_ids.append(task_id)
        try:
            from app.services.note_document_store import get_note_document_task_ids

            for task_id in get_note_document_task_ids(conversation_id):
                if task_id and task_id not in task_ids:
                    task_ids.append(task_id)
        except Exception:
            pass
        return task_ids
    finally:
        db.close()


def _delete_note_messages_for_task(conversation_id: str, task_id: str) -> None:
    db = _db()
    try:
        rows = (
            db.query(ConversationMessage)
            .filter(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.message_type.in_(["note_progress", "note_result"]),
            )
            .all()
        )
        for row in rows:
            if _json_loads(row.meta_json, {}).get("task_id") == task_id:
                db.delete(row)
        db.commit()
    finally:
        db.close()


def delete_conversation_note_document(conversation_id: str, task_id: str) -> dict | None:
    from app.services.note_document_store import (
        delete_note_task_artifacts,
        list_note_documents,
    )
    from app.services.note_task_store import cancel_note_task

    current = get_conversation(conversation_id)
    if current is None:
        return None

    deleted = soft_delete_note_document_and_clear_whiteboard_links(
        conversation_id,
        task_id,
    )
    if not deleted:
        return None

    delete_note_task_artifacts(task_id)
    cancel_note_task(task_id, "笔记已删除，任务已取消")
    _delete_note_messages_for_task(conversation_id, task_id)
    remaining_documents = list_note_documents(conversation_id, include_content=True)

    if remaining_documents:
        active_document = remaining_documents[0]
        return upsert_conversation(
            {
                "id": conversation_id,
                "mode": "note",
                "status": "SUCCESS",
                "noteState": "ready",
                "linkedNoteTaskId": active_document["taskId"],
                "markdown": active_document.get("content", ""),
                "audioMeta": {
                    "title": active_document.get("title", ""),
                    "platform": active_document.get("platform", ""),
                },
                "transcript": {},
            }
        )

    return upsert_conversation(
        {
            "id": conversation_id,
            "mode": "note",
            "status": "SUCCESS",
            "noteState": "none",
            "linkedNoteTaskId": "",
            "markdown": "",
            "audioMeta": {},
            "transcript": {},
        }
    )


def soft_delete_note_document_and_clear_whiteboard_links(
    conversation_id: str,
    task_id: str,
) -> bool:
    if not conversation_id or not task_id:
        return False

    from app.db.models.conversation import NoteDocument
    from app.db.models.whiteboard import WhiteboardNoteLink

    db = _db()
    try:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        document = (
            db.query(NoteDocument)
            .filter(
                NoteDocument.conversation_id == conversation_id,
                NoteDocument.task_id == task_id,
            )
            .first()
        )
        if document is None:
            db.rollback()
            return False

        (
            db.query(WhiteboardNoteLink)
            .filter(WhiteboardNoteLink.note_task_id == task_id)
            .delete(synchronize_session=False)
        )
        now = _now_dt()
        if document.deleted_at is None:
            document.deleted_at = now
        document.updated_at = now
        db.commit()
        return True
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def clear_whiteboard_note_links_for_task(task_id: str) -> int:
    if not task_id:
        return 0

    from app.db.models.whiteboard import WhiteboardNoteLink

    db = _db()
    try:
        deleted = (
            db.query(WhiteboardNoteLink)
            .filter(WhiteboardNoteLink.note_task_id == task_id)
            .delete(synchronize_session=False)
        )
        db.commit()
        return int(deleted or 0)
    finally:
        db.close()


def soft_delete_whiteboards_by_conversation(
    conversation_id: str,
    *,
    db=None,
) -> int:
    if not conversation_id:
        return 0

    from app.db.models.whiteboard import Whiteboard

    owns_session = db is None
    session = db or _db()
    try:
        rows = (
            session.query(Whiteboard)
            .filter(
                Whiteboard.conversation_id == conversation_id,
                Whiteboard.deleted_at.is_(None),
            )
            .all()
        )
        now = datetime.now(timezone.utc)
        for board in rows:
            board.status = "archived"
            board.deleted_at = now
            board.updated_at = now
        if owns_session:
            session.commit()
        return len(rows)
    except Exception:
        if owns_session:
            session.rollback()
        raise
    finally:
        if owns_session:
            session.close()


def upsert_conversation(data: dict) -> dict:
    db = _db()
    try:
        row = db.query(Conversation).filter(Conversation.id == data["id"]).first()
        if row is None:
            row = Conversation(id=data["id"])
            db.add(row)
        elif row.deleted_at is not None:
            row.deleted_at = None
            row.title = None
            row.status = "SUCCESS"
            row.message = None
            row.platform = None
            row.linked_note_task_id = None
            row.note_state = "none"
            row.form_data_json = "{}"
            row.transcript_json = "{}"
            row.audio_meta_json = "{}"
            row.markdown_json = '""'
            # P3 阶段二：恢复时清空 research_space_id（与字段重置策略一致）
            if hasattr(row, "research_space_id"):
                row.research_space_id = None
            (
                db.query(ConversationMessage)
                .filter(ConversationMessage.conversation_id == row.id)
                .delete(synchronize_session=False)
            )
            try:
                from app.services.note_document_store import soft_delete_note_documents_by_conversation

                soft_delete_note_documents_by_conversation(row.id)
            except Exception:
                pass

        row.mode = data.get("mode", row.mode or "chat")
        row.title = data.get("title", row.title)
        row.status = data.get("status", row.status or "SUCCESS")
        row.message = data.get("message", row.message)
        row.platform = data.get("platform", row.platform)
        row.linked_note_task_id = data.get("linkedNoteTaskId", data.get("linked_note_task_id", row.linked_note_task_id))
        row.note_state = data.get("noteState", data.get("note_state", row.note_state or "none"))
        row.form_data_json = _json_dumps(data.get("formData", _json_loads(row.form_data_json, {})))
        row.transcript_json = _json_dumps(data.get("transcript", _json_loads(row.transcript_json, {})))
        row.audio_meta_json = _json_dumps(data.get("audioMeta", _json_loads(row.audio_meta_json, {})))
        row.markdown_json = _json_dumps(data.get("markdown", _json_loads(row.markdown_json, "")))
        # P3 阶段二：research_space_id（cid→rs_id 映射）。data 可不传，保持原值。
        if "researchSpaceId" in data:
            rs_val = data.get("researchSpaceId")
            if hasattr(row, "research_space_id"):
                row.research_space_id = rs_val or None
        row.deleted_at = None

        db.commit()
        return get_conversation(row.id) or {}
    finally:
        db.close()


def append_message(conversation_id: str, data: dict) -> dict:
    db = _db()
    try:
        row = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if row is None:
            raise ValueError("conversation not found")

        now_iso = data.get("createdAt") or _now_iso()
        message = ConversationMessage(
            id=data["id"],
            conversation_id=conversation_id,
            role=data["role"],
            message_type=data.get("message_type", "assistant_text"),
            content=data["content"],
            status=data.get("status"),
            meta_json=_json_dumps(data.get("meta", {})),
            sources_json=_json_dumps(data.get("sources", [])),
            context_refs_authority_version=int(
                data.get("context_refs_authority_version") or 0
            ),
            error=1 if data.get("error") else 0,
            created_at=now_iso,
            updated_at=data.get("updatedAt") or now_iso,
        )
        db.add(message)

        if not row.title and (data.get("message_type") == "user_input" or data.get("role") == "user"):
            row.title = data.get("content", "")[:24] or row.title
        row.updated_at = _now_dt()
        db.commit()
        return get_conversation(conversation_id) or {}
    finally:
        db.close()


def update_message(conversation_id: str, message_id: str, data: dict) -> dict:
    db = _db()
    try:
        row = (
            db.query(ConversationMessage)
            .filter(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.id == message_id,
            )
            .first()
        )
        if row is None:
            raise ValueError("message not found")

        if "role" in data:
            row.role = data["role"]
        if "message_type" in data:
            row.message_type = data["message_type"]
        if "content" in data:
            row.content = data["content"]
        if "status" in data:
            row.status = data["status"]
        if "meta" in data:
            row.meta_json = _json_dumps(data.get("meta", {}))
        if "sources" in data:
            row.sources_json = _json_dumps(data.get("sources", []))
        if "context_refs_authority_version" in data:
            row.context_refs_authority_version = int(
                data.get("context_refs_authority_version") or 0
            )
        if "error" in data:
            row.error = 1 if data.get("error") else 0
        row.updated_at = data.get("updatedAt") or _now_iso()

        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conversation is not None:
            conversation.updated_at = _now_dt()
        db.commit()
        return get_conversation(conversation_id) or {}
    finally:
        db.close()


def upsert_progress_message(conversation_id: str, task_id: str, payload: dict) -> dict:
    db = _db()
    try:
        conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if conversation is None:
            raise ValueError("conversation not found")

        rows = (
            db.query(ConversationMessage)
            .filter(
                ConversationMessage.conversation_id == conversation_id,
                ConversationMessage.message_type == "note_progress",
            )
            .order_by(ConversationMessage.created_at.asc())
            .all()
        )
        row = next(
            (item for item in rows if _json_loads(item.meta_json, {}).get("task_id") == task_id),
            None,
        )
        now_iso = payload.get("updatedAt") or payload.get("updated_at") or _now_iso()
        meta = {
            "task_id": task_id,
            "steps": payload.get("steps", []),
            "current_step": payload.get("current_step", ""),
            "detail": payload.get("detail", ""),
            "attempt_id": payload.get("attempt_id", ""),
            "attempt": payload.get("attempt", 0),
            "source_url": payload.get("source_url", ""),
            "extras": payload.get("extras", ""),
            "stage_timings": payload.get("stage_timings", {}),
            "stage_started_at": payload.get("stage_started_at", ""),
            "timing_updated_at": payload.get("updated_at", ""),
        }
        if row is None:
            row = ConversationMessage(
                id=payload["message_id"],
                conversation_id=conversation_id,
                role="assistant",
                message_type="note_progress",
                content=payload.get("content", ""),
                status=payload.get("status", "pending"),
                meta_json=_json_dumps(meta),
                sources_json="[]",
                error=0,
                created_at=payload.get("createdAt") or now_iso,
                updated_at=now_iso,
            )
            db.add(row)
        else:
            row.content = payload.get("content", row.content)
            row.status = payload.get("status", row.status)
            row.meta_json = _json_dumps(meta)
            row.updated_at = now_iso

        conversation.updated_at = _now_dt()
        db.commit()
        return get_conversation(conversation_id) or {}
    finally:
        db.close()


def append_note_result_message(conversation_id: str, task_id: str, payload: dict) -> dict:
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
                "title": payload["title"],
                "source_url": payload.get("source_url", ""),
                "platform": payload.get("platform", ""),
                "stage_timings": payload.get("stage_timings", {}),
                "total_duration_ms": payload.get("total_duration_ms", 0),
                "total_tokens": payload.get("total_tokens"),
            },
            "createdAt": payload.get("createdAt"),
            "updatedAt": payload.get("updatedAt"),
        },
    )


def soft_delete_conversation(conversation_id: str) -> bool:
    db = _db()
    try:
        if db.get_bind().dialect.name == "sqlite":
            db.execute(text("BEGIN IMMEDIATE"))
        row = db.query(Conversation).filter(Conversation.id == conversation_id).first()
        if row is None:
            return False
        row.deleted_at = datetime.now(timezone.utc)
        soft_delete_whiteboards_by_conversation(conversation_id, db=db)
        db.commit()
        try:
            from app.services.note_document_store import soft_delete_note_documents_by_conversation

            soft_delete_note_documents_by_conversation(conversation_id)
        except Exception:
            pass
        return True
    finally:
        db.close()
