from __future__ import annotations

import asyncio
import uuid
from typing import Any

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field, model_validator

from app.agent_host.event_broker import EventBroker
from app.agent_host.capabilities import NoteMeldCapabilityRegistry
from app.agent_host.drivers.tools import NoteMeldToolDriver
from app.agent_host.native_executor import NativeAgentExecutor
from app.agent_host.preferences import ModelConfigurationRequired
from app.agent_host.preferences import select_model
from app.agent_host.host import get_agent_sdk_host
from app.db.model_dao import get_all_models
from app.services import agent_store
from app.services.conversation_store import get_conversation, list_conversations, upsert_conversation

router = APIRouter(prefix="/agent/v1", tags=["agent"])
_events = EventBroker()


def _finish_turn_callback(
    _session_id: str,
    turn_id: str,
    status: str,
    event: dict[str, Any],
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    terminal_event_type: str = "terminal",
) -> dict[str, Any]:
    return agent_store.transition_turn(
        turn_id,
        status,
        error_code=error_code,
        error_message=error_message,
        terminal_event=event,
        terminal_event_type=terminal_event_type,
    )


_executor = NativeAgentExecutor(
    finish_turn=_finish_turn_callback,
    tool_driver=NoteMeldToolDriver(NoteMeldCapabilityRegistry()),
)


def _ok(data):
    return {"code": "ok", "msg": "", "data": data}


class SessionRequest(BaseModel):
    session_id: str | None = None
    title: str = ""


class TurnRequest(BaseModel):
    input: Any
    model: str | None = None
    idempotency_key: str | None = None
    linked_task_id: str | None = None
    asset_content: str | None = None
    context_refs: list[dict] = Field(default_factory=list)


class PreferenceRequest(BaseModel):
    default_model_id: str | None = None
    fallback_models: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    decision: str | None = Field(default=None, pattern="^(approve|deny)$")
    approved: bool | None = None

    @model_validator(mode="after")
    def _normalize(self) -> "ApprovalRequest":
        if self.decision is None:
            if self.approved is None:
                raise ValueError("approval payload must include decision or approved")
            self.decision = "approve" if self.approved else "deny"
        return self


def _normalize_refs(raw_refs: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_refs, list):
        return []
    return [item for item in raw_refs if isinstance(item, dict)]


def _normalize_attachments(raw_attachments: Any) -> list[dict[str, Any]]:
    if not isinstance(raw_attachments, list):
        return []
    result: list[dict[str, Any]] = []
    for item in raw_attachments:
        if isinstance(item, dict):
            result.append(item)
    return result


def _normalize_turn_input(payload: TurnRequest) -> tuple[str, list[dict[str, Any]], list[dict[str, Any]]]:
    if isinstance(payload.input, str):
        text = payload.input.strip()
        if not text:
            raise ValueError("input text cannot be empty")
        attachments: list[dict[str, Any]] = []
        context_refs = _normalize_refs(payload.context_refs)
        return text, attachments, context_refs

    if isinstance(payload.input, dict):
        raw_text = payload.input.get("text")
        text = "" if raw_text is None else str(raw_text).strip()
        context_refs = _normalize_refs(payload.input.get("context_refs"))
        attachments = _normalize_attachments(payload.input.get("attachments"))
        if payload.context_refs:
            context_refs.extend(_normalize_refs(payload.context_refs))
        if not (text or attachments or context_refs):
            raise ValueError("input.text/attachments/context_refs cannot be all empty")
        return text, attachments, context_refs

    raise ValueError("input must be a string or input object")


@router.post("/sessions")
def create_session(payload: SessionRequest):
    session_id = payload.session_id or str(uuid.uuid4())
    return _ok(upsert_conversation({"id": session_id, "title": payload.title, "mode": "chat"}))


@router.get("/sessions")
def get_sessions():
    return _ok(list_conversations())


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    value = get_conversation(session_id)
    if value is None:
        raise HTTPException(status_code=404, detail={"code": "session_not_found"})
    return _ok(value)


@router.post("/sessions/{session_id}/turns", status_code=202)
def create_turn(session_id: str, payload: TurnRequest):
    try:
        selected_model = select_model(
            payload.model,
            session_id,
            [str(row.get("model_name") or "") for row in get_all_models()],
        )
        normalized_input, attachments, context_refs = _normalize_turn_input(payload)
        turn = agent_store.create_turn(
            session_id,
            model_name=selected_model,
            idempotency_key=payload.idempotency_key,
        )
    except agent_store.SessionBusyError as error:
        raise HTTPException(status_code=409, detail={"code": error.code, "message": str(error)}) from error
    except ModelConfigurationRequired as error:
        raise HTTPException(status_code=400, detail={"code": error.code, "message": str(error)}) from error
    except ValueError as error:
        raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": str(error)}) from error
    except agent_store.TurnNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": str(error)}) from error
    user_message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"notemeld:{turn['turn_id']}:user"))
    assistant_message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"notemeld:{turn['turn_id']}:assistant"))
    if turn.pop("_replayed", False):
        return _ok({
            **turn,
            "replayed": True,
            "user_message_id": user_message_id,
            "assistant_message_id": assistant_message_id,
            "events_url": f"/api/agent/v1/turns/{turn['turn_id']}/events",
        })
    _executor.start(
        session_id=session_id,
        turn_id=turn["turn_id"],
        content=normalized_input,
        model_name=selected_model,
        user_message_id=user_message_id,
        assistant_message_id=assistant_message_id,
        asset_content=payload.asset_content,
        attachments=attachments,
        context_refs=context_refs,
        event_sink=lambda payload: _events.publish_sync(turn["turn_id"], payload),
    )
    turn = {**turn, "user_message_id": user_message_id, "assistant_message_id": assistant_message_id,
            "events_url": f"/api/agent/v1/turns/{turn['turn_id']}/events", "replayed": False}
    return _ok(turn)


@router.get("/turns/{turn_id}")
def get_turn(turn_id: str):
    value = agent_store.get_turn(turn_id)
    if value is None:
        raise HTTPException(status_code=404, detail={"code": "turn_not_found"})
    return _ok(value)


@router.get("/turns/{turn_id}/events")
def get_turn_events(request: Request, turn_id: str, after_sequence: int = -1):
    """Replay persisted events and follow the turn until a terminal status."""
    if agent_store.get_turn(turn_id) is None:
        raise HTTPException(status_code=404, detail={"code": "turn_not_found"})
    cursor = request.headers.get("last-event-id")
    if cursor is not None:
        try:
            after_sequence = max(after_sequence, int(cursor))
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": "Last-Event-ID must be an integer"})
    async def stream():
        cursor = after_sequence
        async for event in _events.subscribe(turn_id, after_sequence=cursor):
            payload = {
                "event_id": event["event_id"],
                "turn_id": event.get("turn_id") or turn_id,
                "sequence": int(event.get("sequence", -1)),
                "schema_version": str(event.get("schema_version") or "1"),
                "type": event.get("type") or event.get("event_type") or "agent.event",
                "payload": event.get("payload") if isinstance(event.get("payload"), dict) else {},
            }
            cursor = int(payload["sequence"])
            yield f"id: {cursor}\nevent: {payload['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
                
    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.post("/turns/{turn_id}/cancel")
def cancel_turn(turn_id: str):
    try:
        turn = agent_store.get_turn(turn_id)
        if turn is None:
            raise agent_store.TurnNotFoundError(f"Turn 未找到: {turn_id}")
        if str(turn.get("status")) in agent_store.TERMINAL_STATUSES:
            raise agent_store.TurnTerminalError(f"已终态 Turn 不允许取消: {turn_id}")
        try:
            get_agent_sdk_host().cancel(turn_id)
        except KeyError:
            # The native registration can race with the HTTP command. Mark
            # the durable turn as cancelling; the executor retries cancel
            # immediately after registration and only the SDK emits terminal.
            pass
        if str(turn.get("status")) != "cancelling":
            turn = agent_store.transition_turn(
                turn_id,
                "cancelling",
                terminal_event={"type": "turn.cancelling"},
                terminal_event_type="turn.cancelling",
            )
        return _ok({"turn_id": turn_id, "accepted": True, "status": "cancelling"})
    except agent_store.TurnNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "turn_not_found"}) from error
    except agent_store.TurnTerminalError as error:
        raise HTTPException(status_code=409, detail={"code": "turn_terminal", "message": str(error)}) from error


@router.post("/turns/{turn_id}/steer")
def steer_turn(turn_id: str, payload: dict | None = None):
    if agent_store.get_turn(turn_id) is None:
        raise HTTPException(status_code=404, detail={"code": "turn_not_found"})
    try:
        get_agent_sdk_host().steer(turn_id, payload or {})
    except KeyError as error:
        raise HTTPException(status_code=409, detail={"code": "steer_unsupported", "message": "native turn is not active"}) from error
    return _ok({"turn_id": turn_id, "accepted": True})


@router.post("/approvals/{approval_id}")
def resolve_approval(approval_id: str, payload: ApprovalRequest):
    try:
        get_agent_sdk_host().resolve_approval(approval_id, payload.decision)
    except KeyError as error:
        raise HTTPException(status_code=404, detail={"code": "approval_not_found"}) from error
    except Exception as error:  # noqa: BLE001 - map native control boundary
        code = getattr(error, "code", None)
        if code == -3:
            raise HTTPException(status_code=404, detail={"code": "approval_not_found"}) from error
        raise HTTPException(status_code=409, detail={"code": "approval_unavailable", "message": "审批控制不可用"}) from error
    return _ok({"approval_id": approval_id, "decision": payload.decision, "accepted": True})


@router.get("/sessions/{session_id}/model-preference")
def get_preference(session_id: str):
    return _ok(agent_store.get_model_preference(session_id))


@router.put("/sessions/{session_id}/model-preference")
def put_preference(session_id: str, payload: PreferenceRequest):
    try:
        value = agent_store.set_model_preference(
            session_id,
            default_model_id=payload.default_model_id,
            fallback_models=payload.fallback_models,
        )
    except (agent_store.PreferenceError, agent_store.TurnNotFoundError) as error:
        raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": str(error)}) from error
    return _ok(value)
