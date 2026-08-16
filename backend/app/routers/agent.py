from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.agent_host.event_broker import EventBroker
from app.agent_host.preferences import ModelConfigurationRequired
from app.agent_host.turn_manager import SessionBusyError, TurnManager
from app.services import agent_store
from app.services.conversation_store import get_conversation, list_conversations, upsert_conversation

router = APIRouter(prefix="/agent/v1", tags=["agent"])
_turns = TurnManager()
_events = EventBroker()


class SessionRequest(BaseModel):
    session_id: str | None = None
    title: str = ""


class TurnRequest(BaseModel):
    input: str = Field(min_length=1)
    model: str | None = None
    idempotency_key: str | None = None


class PreferenceRequest(BaseModel):
    default_model_id: str | None = None
    fallback_models: list[str] = Field(default_factory=list)


@router.post("/sessions")
def create_session(payload: SessionRequest):
    session_id = payload.session_id or str(uuid.uuid4())
    return {"data": upsert_conversation({"id": session_id, "title": payload.title, "mode": "chat"})}


@router.get("/sessions")
def get_sessions():
    return {"data": list_conversations()}


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    value = get_conversation(session_id)
    if value is None:
        raise HTTPException(status_code=404, detail={"code": "session_not_found"})
    return {"data": value}


@router.post("/sessions/{session_id}/turns", status_code=202)
def create_turn(session_id: str, payload: TurnRequest):
    try:
        turn = _turns.start_turn(session_id, payload.input, model_name=payload.model, idempotency_key=payload.idempotency_key)
    except SessionBusyError as error:
        raise HTTPException(status_code=409, detail={"code": error.code, "message": str(error)}) from error
    except agent_store.TurnNotFoundError as error:
        raise HTTPException(status_code=404, detail={"code": "session_not_found", "message": str(error)}) from error
    return {"data": turn}


@router.get("/turns/{turn_id}")
def get_turn(turn_id: str):
    value = agent_store.get_turn(turn_id)
    if value is None:
        raise HTTPException(status_code=404, detail={"code": "turn_not_found"})
    return {"data": value}


@router.get("/turns/{turn_id}/events")
def get_turn_events(turn_id: str, after_sequence: int = -1):
    events = [event for event in agent_store.list_events(turn_id) if event["sequence"] > after_sequence]
    return {"data": events}


@router.get("/sessions/{session_id}/model-preference")
def get_preference(session_id: str):
    return {"data": agent_store.get_model_preference(session_id)}


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
    return {"data": value}

