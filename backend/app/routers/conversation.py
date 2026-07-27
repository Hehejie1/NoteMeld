from typing import Any

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
from app.utils.response import ResponseWrapper as R

router = APIRouter()


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
        return R.success(append_message(conversation_id, data.model_dump()))
    except ValueError as exc:
        message = str(exc)
        if message == "conversation not found":
            return R.error("会话不存在", code=404)
        return R.error(message, code=400)


@router.patch("/conversations/{conversation_id}/messages/{message_id}")
def patch_conversation_message(conversation_id: str, message_id: str, data: ConversationMessagePatchPayload):
    payload = data.model_dump(exclude_unset=True)
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
