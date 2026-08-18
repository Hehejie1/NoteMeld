from __future__ import annotations

import asyncio
import uuid

import json

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.agent_host.event_broker import EventBroker
from app.agent_host.capabilities import NoteMeldCapabilityRegistry
from app.agent_host.drivers.tools import NoteMeldToolDriver
from app.agent_host.native_executor import NativeAgentExecutor
from app.agent_host.preferences import ModelConfigurationRequired
from app.agent_host.preferences import select_model
from app.agent_host.turn_manager import SessionBusyError, TurnManager
from app.agent_host.host import get_agent_sdk_host
from app.db.model_dao import get_all_models
from app.services import agent_store
from app.services.conversation_store import append_message, get_conversation, list_conversations, upsert_conversation

router = APIRouter(prefix="/agent/v1", tags=["agent"])
_turns = TurnManager()
_events = EventBroker()
_executor = NativeAgentExecutor(
    finish_turn=_turns.finish_turn,
    tool_driver=NoteMeldToolDriver(NoteMeldCapabilityRegistry()),
)


def _ok(data):
    return {"code": "ok", "msg": "", "data": data}


class SessionRequest(BaseModel):
    session_id: str | None = None
    title: str = ""


class TurnRequest(BaseModel):
    input: str = Field(min_length=1)
    model: str | None = None
    idempotency_key: str | None = None
    linked_task_id: str | None = None
    asset_content: str | None = None
    context_refs: list[dict] = Field(default_factory=list)


class PreferenceRequest(BaseModel):
    default_model_id: str | None = None
    fallback_models: list[str] = Field(default_factory=list)


class ApprovalRequest(BaseModel):
    decision: str = Field(pattern="^(approve|deny)$")


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
        turn = _turns.start_turn(session_id, payload.input, model_name=selected_model, idempotency_key=payload.idempotency_key)
    except SessionBusyError as error:
        raise HTTPException(status_code=409, detail={"code": error.code, "message": str(error)}) from error
    except ModelConfigurationRequired as error:
        raise HTTPException(status_code=400, detail={"code": error.code, "message": str(error)}) from error
    except agent_store.TurnNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": str(error)}) from error
    user_message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"notemeld:{turn['turn_id']}:user"))
    assistant_message_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"notemeld:{turn['turn_id']}:assistant"))
    if turn.get("replayed"):
        return _ok({**turn, "user_message_id": user_message_id,
                    "assistant_message_id": assistant_message_id,
                    "events_url": f"/api/agent/v1/turns/{turn['turn_id']}/events"})
    try:
        append_message(session_id, {
            "id": user_message_id,
            "role": "user",
            "message_type": "user_input",
            "content": payload.input,
            "status": "completed",
        })
        append_message(session_id, {
            "id": assistant_message_id,
            "role": "assistant",
            "message_type": "assistant_text",
            "content": "",
            "status": "streaming",
        })
    except Exception as error:  # noqa: BLE001 - durable projection failure
        raise HTTPException(status_code=500, detail={"code": "store_unavailable", "message": "无法创建 Agent 消息投影"}) from error
    _executor.start(
        session_id=session_id,
        turn_id=turn["turn_id"],
        content=payload.input,
        model_name=selected_model,
        assistant_message_id=assistant_message_id,
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
    cursor = request.headers.get("last-event-id")
    if cursor is not None:
        try:
            after_sequence = max(after_sequence, int(cursor))
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": "invalid_input", "message": "Last-Event-ID must be an integer"})
    async def stream():
        cursor = after_sequence
        idle_rounds = 0
        while idle_rounds < 3000:
            emitted = False
            for event in agent_store.list_events(turn_id):
                sequence = int(event["sequence"])
                if sequence <= cursor:
                    continue
                payload = {
                    "event_id": event["event_id"],
                    "turn_id": event["turn_id"],
                    "sequence": sequence,
                    "type": event.get("event_type") or (event.get("payload_json") or {}).get("type", "unknown"),
                    "payload": event.get("payload_json") if isinstance(event.get("payload_json"), dict) else {},
                }
                cursor = sequence
                emitted = True
                yield f"id: {sequence}\nevent: {payload['type']}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"
            turn = agent_store.get_turn(turn_id)
            if turn is None:
                return
            if str(turn.get("status")) in agent_store.TERMINAL_STATUSES:
                return
            idle_rounds = 0 if emitted else idle_rounds + 1
            await asyncio.sleep(0.1)

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
