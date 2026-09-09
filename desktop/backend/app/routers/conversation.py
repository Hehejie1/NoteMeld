from typing import Any, Optional

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.services.conversation_store import (
    append_message,
    delete_conversation_note_document,
    get_conversation,
    get_conversation_note_task_ids,
    list_conversations,
    soft_delete_conversation,
    update_message,
    upsert_conversation,
)
from app.services.note_document_store import delete_note_task_artifacts
from app.services.note_task_store import cancel_note_task
from app.services.conversation_context_refs import (
    MAX_CONTEXT_REFS,
    MAX_SOURCE_IDS,
    MAX_WHITEBOARD_SNAPSHOT,
    resolve_context_refs,
    sanitize_context_ref_shape,
)
from app.utils.response import ResponseWrapper as R

router = APIRouter()

_CONTEXT_REFS_AUTHORITY_VERSION = 1

_TRUSTED_CONTEXT_REF_FIELDS = {
    "note_selection": (
        "id",
        "type",
        "document_task_id",
        "canvas_id",
        "node_id",
        "label",
        "snapshot",
        "source_ids",
    ),
    "whiteboard_node": (
        "id",
        "type",
        "document_task_id",
        "canvas_id",
        "whiteboard_id",
        "node_id",
        "label",
        "snapshot",
        "source_ids",
    ),
    "whiteboard_selection": (
        "id",
        "type",
        "whiteboard_id",
        "revision",
        "card_ids",
        "relation_ids",
        "label",
        "snapshot",
        "source_ids",
    ),
}


def _context_ref_locator(reference: Any) -> tuple[Any, ...] | None:
    shaped = sanitize_context_ref_shape([reference])
    if not shaped:
        return None
    item = shaped[0]
    if item["type"] == "whiteboard_selection":
        return (
            item["type"],
            item["id"],
            item["whiteboard_id"],
            item["revision"],
            tuple(item["card_ids"]),
            tuple(item["relation_ids"]),
        )
    return (
        item["type"],
        item["id"],
        item["document_task_id"],
        item["canvas_id"],
        item.get("whiteboard_id", ""),
        item["node_id"],
    )


def _trusted_context_ref_copy(reference: Any) -> dict[str, Any] | None:
    if not isinstance(reference, dict):
        return None
    shaped = sanitize_context_ref_shape([reference])
    if not shaped:
        return None
    trusted = shaped[0]
    ref_type = trusted["type"]
    if ref_type == "whiteboard_selection":
        snapshot = str(reference.get("snapshot") or "").strip()
        if not snapshot:
            return None
        trusted["snapshot"] = snapshot[:MAX_WHITEBOARD_SNAPSHOT]
        trusted["source_ids"] = []
        seen_source_ids: set[str] = set()
        raw_source_ids = reference.get("source_ids")
        if isinstance(raw_source_ids, list):
            for raw_source_id in raw_source_ids:
                source_id = str(raw_source_id or "").strip()[:200]
                if not source_id or source_id in seen_source_ids:
                    continue
                trusted["source_ids"].append(source_id)
                seen_source_ids.add(source_id)
                if len(trusted["source_ids"]) >= MAX_SOURCE_IDS:
                    break
    return {
        field: trusted[field]
        for field in _TRUSTED_CONTEXT_REF_FIELDS[ref_type]
        if field in trusted
    }


def _resolve_message_context_refs(
    conversation_id: str,
    raw: Any,
    trusted_existing: Any,
) -> list[dict[str, Any]]:
    trusted_by_locator: dict[tuple[Any, ...], dict[str, Any]] = {}
    if isinstance(trusted_existing, list):
        for reference in trusted_existing[:MAX_CONTEXT_REFS]:
            trusted = _trusted_context_ref_copy(reference)
            locator = _context_ref_locator(trusted)
            if locator is not None and trusted is not None:
                trusted_by_locator[locator] = trusted

    if not isinstance(raw, list):
        return []
    resolved: list[dict[str, Any]] = []
    for reference in raw[:MAX_CONTEXT_REFS]:
        locator = _context_ref_locator(reference)
        if locator is not None and locator in trusted_by_locator:
            resolved.append(trusted_by_locator[locator])
        else:
            resolved.extend(resolve_context_refs(conversation_id, [reference]))
    return resolved[:MAX_CONTEXT_REFS]


def _sanitize_message_meta(
    role: str | None,
    meta: dict[str, Any] | None,
    *,
    conversation_id: str = "",
    trusted_existing_context_refs: Any = None,
) -> dict[str, Any] | None:
    if meta is None:
        return None
    result = dict(meta)
    if role == "user" and "context_refs" in result:
        result["context_refs"] = _resolve_message_context_refs(
            conversation_id,
            result["context_refs"],
            trusted_existing_context_refs,
        )
    return result


class ConversationPayload(BaseModel):
    id: str
    mode: str = "chat"
    title: str | None = None
    status: str | None = None
    message: str | None = None
    platform: str | None = None
    linkedNoteTaskId: str | None = None
    noteState: str | None = None
    formData: dict[str, Any] = Field(default_factory=dict)
    transcript: dict[str, Any] = Field(default_factory=dict)
    audioMeta: dict[str, Any] = Field(default_factory=dict)
    markdown: Any = ""


class ConversationPatchPayload(BaseModel):
    mode: str | None = None
    title: str | None = None
    status: str | None = None
    message: str | None = None
    platform: str | None = None
    linkedNoteTaskId: str | None = None
    noteState: str | None = None
    formData: dict[str, Any] | None = None
    transcript: dict[str, Any] | None = None
    audioMeta: dict[str, Any] | None = None
    markdown: Any | None = None


class ConversationMessagePayload(BaseModel):
    id: str
    role: str
    message_type: str = "assistant_text"
    content: str
    status: str | None = None
    meta: dict[str, Any] = Field(default_factory=dict)
    createdAt: str | None = None
    updatedAt: str | None = None
    sources: list[dict[str, Any]] = Field(default_factory=list)
    error: bool = False


class ConversationMessagePatchPayload(BaseModel):
    role: str | None = None
    message_type: str | None = None
    content: str | None = None
    status: str | None = None
    meta: dict[str, Any] | None = None
    updatedAt: str | None = None
    sources: list[dict[str, Any]] | None = None
    error: bool | None = None


@router.get("/conversations")
def get_conversations():
    return R.success(list_conversations())


@router.get("/conversations/{conversation_id}")
def get_conversation_detail(conversation_id: str):
    item = get_conversation(conversation_id)
    if item is None:
        return R.error("会话不存在", code=404)
    return R.success(item)


@router.put("/conversations/{conversation_id}")
def put_conversation(conversation_id: str, data: ConversationPayload):
    payload = data.model_dump()
    payload["id"] = conversation_id
    return R.success(upsert_conversation(payload))


@router.patch("/conversations/{conversation_id}")
def patch_conversation(conversation_id: str, data: ConversationPatchPayload):
    current = get_conversation(conversation_id)
    if current is None:
        return R.error("会话不存在", code=404)

    payload = {
        "id": conversation_id,
        "mode": current.get("mode", "chat"),
        "title": current.get("title"),
        "status": current.get("status"),
        "message": current.get("message"),
        "platform": current.get("platform"),
        "linkedNoteTaskId": current.get("linkedNoteTaskId"),
        "noteState": current.get("noteState"),
        "formData": current.get("formData") or {},
        "transcript": current.get("transcript") or {},
        "audioMeta": current.get("audioMeta") or {},
        "markdown": current.get("markdown", ""),
    }
    updates = data.model_dump(exclude_unset=True)
    for field in ("formData", "transcript", "audioMeta"):
        if field in updates and isinstance(updates[field], dict):
            payload[field] = {
                **(payload.get(field) or {}),
                **updates.pop(field),
            }
    payload.update(updates)
    return R.success(upsert_conversation(payload))


@router.post("/conversations/{conversation_id}/messages")
def post_conversation_message(conversation_id: str, data: ConversationMessagePayload):
    try:
        payload = data.model_dump()
        payload["meta"] = _sanitize_message_meta(
            data.role,
            payload.get("meta"),
            conversation_id=conversation_id,
        ) or {}
        payload["context_refs_authority_version"] = (
            _CONTEXT_REFS_AUTHORITY_VERSION
            if data.role == "user" and "context_refs" in payload["meta"]
            else 0
        )
        return R.success(append_message(conversation_id, payload))
    except ValueError as exc:
        message = str(exc)
        if message == "conversation not found":
            return R.error("会话不存在", code=404)
        return R.error(message, code=400)


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
def patch_conversation_message(conversation_id: str, message_id: str, data: ConversationMessagePatchPayload):
    payload = data.model_dump(exclude_unset=True)
    current_message: dict[str, Any] = {}
    if "meta" in payload or payload.get("role") == "user":
        current = get_conversation(
            conversation_id,
            include_message_context_ref_authority=True,
        ) or {}
        current_message = next(
            (message for message in current.get("messages", []) if message.get("id") == message_id),
            {},
        )
    stored_role = current_message.get("role")
    role = payload["role"] if "role" in payload else stored_role
    current_meta = current_message.get("meta")
    if (
        role == "user"
        and stored_role != "user"
        and "meta" not in payload
        and isinstance(current_meta, dict)
    ):
        payload["meta"] = dict(current_meta)
    if "meta" in payload:
        current_meta = current_message.get("meta")
        trusted_context_refs = (
            current_meta.get("context_refs")
            if stored_role == "user"
            and role == "user"
            and current_message.get("context_refs_authority_version")
            == _CONTEXT_REFS_AUTHORITY_VERSION
            and isinstance(current_meta, dict)
            else None
        )
        payload["meta"] = _sanitize_message_meta(
            role,
            payload.get("meta"),
            conversation_id=conversation_id,
            trusted_existing_context_refs=trusted_context_refs,
        )
        payload["context_refs_authority_version"] = (
            _CONTEXT_REFS_AUTHORITY_VERSION
            if role == "user"
            and isinstance(payload["meta"], dict)
            and "context_refs" in payload["meta"]
            else 0
        )
    elif "role" in payload and role != "user":
        payload["context_refs_authority_version"] = 0
    payload["id"] = message_id
    try:
        return R.success(update_message(conversation_id, message_id, payload))
    except ValueError as exc:
        message = str(exc)
        if message == "message not found":
            return R.error("消息不存在", code=404)
        return R.error(message, code=400)


@router.delete("/conversations/{conversation_id}")
def delete_conversation(conversation_id: str):
    current = get_conversation(conversation_id)
    task_ids = get_conversation_note_task_ids(conversation_id)
    deleted = soft_delete_conversation(conversation_id)
    if not deleted:
        return R.error("会话不存在", code=404)
    for task_id in task_ids:
        delete_note_task_artifacts(task_id)
        cancel_note_task(task_id, "会话已删除，任务已取消")
    return R.success({"id": conversation_id})


@router.delete("/conversations/{conversation_id}/documents/{task_id}")
def delete_conversation_document(conversation_id: str, task_id: str):
    item = delete_conversation_note_document(conversation_id, task_id)
    if item is None:
        return R.error("文档不存在或会话不存在", code=404)
    return R.success(item)


# ---------------------------------------------------------------------------
# P3-T1: Workspace 只读接口
# ---------------------------------------------------------------------------

@router.get("/conversations/{conversation_id}/workspace/list")
def workspace_list(conversation_id: str, path: Optional[str] = None):
    """列出会话工作空间目录内容（只读）。"""
    from app.agent_host.workspace_adapter import WorkspaceAdapterError, list_directory

    try:
        return R.success(list_directory(conversation_id, path or ""))
    except WorkspaceAdapterError as exc:
        return R.error(str(exc), code=403)
    except FileNotFoundError as exc:
        return R.error(f"路径不存在: {exc}", code=404)


@router.get("/conversations/{conversation_id}/workspace/read")
def workspace_read(conversation_id: str, path: str):
    """读取会话工作空间内某文件（只读）。"""
    from app.agent_host.workspace_adapter import WorkspaceAdapterError, read_file

    if not path:
        return R.error("path 参数不能为空", code=400)
    try:
        return R.success(read_file(conversation_id, path))
    except WorkspaceAdapterError as exc:
        return R.error(str(exc), code=403)
    except FileNotFoundError:
        return R.error(f"文件不存在: {path}", code=404)


# ---------------------------------------------------------------------------
# P3-T4: 长任务取消接口
# ---------------------------------------------------------------------------


class CancelTaskPayload(BaseModel):
    card_id: str


@router.post("/conversations/{conversation_id}/workspace/cancel_task")
async def cancel_long_task(conversation_id: str, data: CancelTaskPayload):
    """取消长任务卡片。

    根据 ``card_id`` 反查 LongTaskManager，并校验卡片属于路径中的会话后触发取消。
    """
    if not data.card_id:
        return R.error("card_id 不能为空", code=400)
    # Long-task execution used to be owned by the removed Python Agent loop.
    # Until an SDK CapabilityProvider is registered, fail explicitly rather
    # than importing that second runtime on demand.
    return R.error("长任务能力尚未注册到 Agent SDK", code=501)
