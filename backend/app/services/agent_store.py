from __future__ import annotations

import json
import uuid
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.engine import get_db
from app.db.models import AgentEvent, AgentPreference, AgentTurn
from app.db.models.conversation import Conversation


TERMINAL_STATUSES = frozenset({"succeeded", "failed", "interrupted", "cancelled"})


class AgentStoreError(ValueError):
    """Base error for agent persistence operations."""


class TurnNotFoundError(AgentStoreError):
    """Raised when a turn does not exist."""


class TurnTerminalError(AgentStoreError):
    """Raised when a terminal turn update is not valid."""


class TurnAlreadyExistsError(AgentStoreError):
    """Raised when non-null idempotency key is already used."""


class SessionBusyError(AgentStoreError):
    """Raised when the same session has an active non-terminal turn."""
    code = "session_busy"


class PreferenceError(AgentStoreError):
    """Raised when preference payload is invalid."""


def _db() -> Session:
    return next(get_db())


def _json_dumps(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    return json.dumps(payload or {}, ensure_ascii=False)


def _json_loads(payload: str | None) -> Any:
    if not payload:
        return None
    try:
        return json.loads(payload)
    except Exception:
        return None


def _ensure_session_exists(db: Session, session_id: str) -> None:
    if not session_id:
        raise TurnNotFoundError("会话ID不能为空")

    exists = (
        db.query(Conversation)
        .filter(Conversation.id == session_id, Conversation.deleted_at.is_(None))
        .first()
    )
    if exists is None:
        raise TurnNotFoundError(f"会话不存在: {session_id}")


def _serialize_turn(turn: AgentTurn) -> dict[str, Any]:
    return {
        "turn_id": turn.turn_id,
        "session_id": turn.session_id,
        "idempotency_key": turn.idempotency_key,
        "status": turn.status,
        "model_name": turn.model_name,
        "error_code": turn.error_code,
        "error_message": turn.error_message,
        "created_at": turn.created_at,
        "updated_at": turn.updated_at,
    }


def _serialize_event(event: AgentEvent) -> dict[str, Any]:
    return {
        "event_id": event.event_id,
        "turn_id": event.turn_id,
        "sequence": event.sequence,
        "event_type": event.event_type,
        "payload_json": _json_loads(event.payload_json),
        "created_at": event.created_at,
    }


def _serialize_preference(preference: AgentPreference) -> dict[str, Any]:
    fallback_models = _json_loads(preference.fallback_models_json) or []
    return {
        "session_id": preference.session_id,
        "default_model_id": preference.default_model_id,
        "fallback_models": fallback_models,
        "updated_at": preference.updated_at,
    }


def _is_sequence_conflict(error: IntegrityError) -> bool:
    message = str(error.orig)
    return (
        "uq_agent_events_turn_sequence" in message
        or "agent_events.turn_id, agent_events.sequence" in message
    )


def _is_idempotency_conflict(error: IntegrityError) -> bool:
    message = str(error.orig)
    return (
        "uq_agent_turns_session_idempotency_key" in message
        or "agent_turns.session_id, agent_turns.idempotency_key" in message
    )


def _next_event_sequence(session: Session, turn_id: str) -> int:
    row = (
        session.query(AgentEvent.sequence)
        .filter_by(turn_id=turn_id)
        .order_by(AgentEvent.sequence.desc())
        .with_for_update()
        .first()
    )
    return (row[0] + 1) if row else 0


def _is_terminal_status(status: str) -> bool:
    return status in TERMINAL_STATUSES


def _coerce_stored_event_payload(event_type: str, payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload

    if payload.get("type") == event_type and "payload" in payload:
        inner_payload = payload.get("payload")
        return {} if inner_payload is None else inner_payload

    return payload


def create_turn(
    session_id: str,
    *,
    turn_id: str | None = None,
    idempotency_key: str | None = None,
    status: str = "created",
    model_name: str | None = None,
) -> dict[str, Any]:
    db = _db()
    try:
        _ensure_session_exists(db, session_id)

        with db.begin():
            if idempotency_key is not None:
                existing = (
                    db.query(AgentTurn)
                    .filter_by(session_id=session_id, idempotency_key=idempotency_key)
                    .with_for_update()
                    .first()
                )
                if existing is not None:
                    value = _serialize_turn(existing)
                    # Internal marker consumed by HTTP projection;
                    # callers must not create another message pair or native turn.
                    value["_replayed"] = True
                    return value

            active = (
                db.query(AgentTurn)
                .filter(
                    AgentTurn.session_id == session_id,
                    ~AgentTurn.status.in_(tuple(TERMINAL_STATUSES)),
                )
                .with_for_update()
                .first()
            )
            if active is not None:
                raise SessionBusyError("同一会话当前已有活动 Turn")

            turn = AgentTurn(
                turn_id=turn_id or str(uuid.uuid4()),
                session_id=session_id,
                idempotency_key=idempotency_key,
                status=status,
                model_name=model_name,
            )
            db.add(turn)
            try:
                db.flush()
            except IntegrityError as error:
                if _is_idempotency_conflict(error):
                    raise TurnAlreadyExistsError("同一会话的幂等键已存在") from error
                raise

        db.refresh(turn)
        value = _serialize_turn(turn)
        value["_replayed"] = False
        return value
    finally:
        db.close()


def _append_event(
    db: Session,
    *,
    turn_id: str,
    event_type: str | None,
    payload: Any,
    sequence: int | None,
    event_id: str | None = None,
) -> dict[str, Any]:
    sequence = sequence if sequence is not None else _next_event_sequence(db, turn_id)
    event = AgentEvent(
        event_id=event_id or str(uuid.uuid4()),
        turn_id=turn_id,
        sequence=sequence,
        event_type=event_type,
        payload_json=_json_dumps(payload),
    )
    db.add(event)
    return _serialize_event(event)


def append_event(
    turn_id: str,
    payload: Any,
    *,
    event_type: str | None = None,
    sequence: int | None = None,
    event_id: str | None = None,
) -> dict[str, Any]:
    db = _db()
    try:
        with db.begin():
            turn = db.query(AgentTurn).filter_by(turn_id=turn_id).with_for_update().first()
            if turn is None:
                raise TurnNotFoundError(f"Turn 未找到: {turn_id}")
            if _is_terminal_status(turn.status):
                raise TurnTerminalError(f"已终态 Turn 不允许继续追加事件: {turn_id}")
            event_payload = _append_event(
                db,
                turn_id=turn_id,
                event_type=event_type,
                payload=payload,
                sequence=sequence,
                event_id=event_id,
            )
            return event_payload
    except IntegrityError as error:
        db.rollback()
        if _is_sequence_conflict(error):
            raise TurnStoreSequenceError("事件序列冲突") from error
        raise
    finally:
        db.close()


def transition_turn(
    turn_id: str,
    status: str,
    *,
    error_code: str | None = None,
    error_message: str | None = None,
    terminal_event: dict[str, Any] | None = None,
    terminal_event_type: str = "terminal",
) -> dict[str, Any]:
    db = _db()
    try:
        with db.begin():
            turn = db.query(AgentTurn).filter_by(turn_id=turn_id).with_for_update().first()
            if turn is None:
                raise TurnNotFoundError(f"Turn 未找到: {turn_id}")
            if _is_terminal_status(turn.status):
                raise TurnTerminalError(f"已终态 Turn 不允许变更状态: {turn_id}")

            if _is_terminal_status(status):
                if turn.status == status:
                    return _serialize_turn(turn)
                if terminal_event is None:
                    raise TurnTerminalError("终态变更需要透出 terminal 事件")
                _append_event(
                    db,
                    turn_id=turn_id,
                    event_type=terminal_event_type,
                    payload=_coerce_stored_event_payload(
                        terminal_event_type,
                        terminal_event,
                    ),
                    sequence=None,
                )
            elif terminal_event is not None:
                # Control-plane transitions such as ``cancelling`` are not
                # terminal, but still need an ordered event so reconnecting
                # UI/CLI clients observe the same intent as the native turn.
                _append_event(
                    db,
                    turn_id=turn_id,
                    event_type=terminal_event_type,
                    payload=_coerce_stored_event_payload(
                        terminal_event_type,
                        terminal_event,
                    ),
                    sequence=None,
                )

            turn.status = status
            turn.error_code = error_code
            turn.error_message = error_message

            db.flush()
            db.refresh(turn)
            return _serialize_turn(turn)
    except IntegrityError as error:
        db.rollback()
        if _is_sequence_conflict(error):
            raise TurnStoreSequenceError("事件序列冲突") from error
        raise
    finally:
        db.close()


def get_turn(turn_id: str) -> dict[str, Any] | None:
    db = _db()
    try:
        turn = db.query(AgentTurn).filter_by(turn_id=turn_id).first()
        if turn is None:
            return None
        return _serialize_turn(turn)
    finally:
        db.close()


def recover_nonterminal() -> list[str]:
    """Mark turns left active by a crashed process as interrupted exactly once."""
    db = _db()
    recovered: list[str] = []
    try:
        with db.begin():
            turns = (
                db.query(AgentTurn)
                .filter(~AgentTurn.status.in_(tuple(TERMINAL_STATUSES)))
                .with_for_update()
                .all()
            )
            for turn in turns:
                _append_event(
                    db,
                    turn_id=turn.turn_id,
                    event_type="turn.interrupted",
                    payload={"reason": "host_restart"},
                    sequence=None,
                )
                turn.status = "interrupted"
                turn.error_code = "interrupted"
                turn.error_message = "Agent Host restarted before the turn completed"
                recovered.append(turn.turn_id)
        return recovered
    finally:
        db.close()


def list_events(turn_id: str) -> list[dict[str, Any]]:
    db = _db()
    try:
        events = (
            db.query(AgentEvent)
            .filter_by(turn_id=turn_id)
            .order_by(AgentEvent.sequence.asc(), AgentEvent.created_at.asc())
            .all()
        )
        return [_serialize_event(event) for event in events]
    finally:
        db.close()


def get_model_preference(session_id: str) -> dict[str, Any]:
    db = _db()
    try:
        preference = db.query(AgentPreference).filter_by(session_id=session_id).first()
        if preference is None:
            return {
                "session_id": session_id,
                "default_model_id": None,
                "fallback_models": [],
            }
        return _serialize_preference(preference)
    finally:
        db.close()


def set_model_preference(
    session_id: str,
    *,
    default_model_id: str | None,
    fallback_models: list[str] | None = None,
) -> dict[str, Any]:
    if fallback_models is not None and not isinstance(fallback_models, list):
        raise PreferenceError("fallback_models 必须是字符串数组")
    if fallback_models is not None and any(not isinstance(model, str) for model in fallback_models):
        raise PreferenceError("fallback_models 必须是字符串数组")

    db = _db()
    try:
        _ensure_session_exists(db, session_id)
        preference = db.query(AgentPreference).filter_by(session_id=session_id).first()
        if preference is None:
            preference = AgentPreference(
                session_id=session_id,
                default_model_id=default_model_id,
                fallback_models_json=_json_dumps(fallback_models or []),
            )
            db.add(preference)
        else:
            preference.default_model_id = default_model_id
            preference.fallback_models_json = _json_dumps(fallback_models or [])

        db.commit()
        db.refresh(preference)
        return _serialize_preference(preference)
    except IntegrityError as error:
        db.rollback()
        if _is_idempotency_conflict(error):
            raise PreferenceError("无法写入模型偏好") from error
        raise
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


class TurnStoreSequenceError(AgentStoreError):
    """Raised when append/transition hit sequence uniqueness conflict."""


__all__ = [
    "AgentStoreError",
    "TurnAlreadyExistsError",
    "SessionBusyError",
    "TurnNotFoundError",
    "TurnStoreSequenceError",
    "TurnTerminalError",
    "PreferenceError",
    "append_event",
    "create_turn",
    "get_turn",
    "get_model_preference",
    "list_events",
    "recover_nonterminal",
    "set_model_preference",
    "transition_turn",
]
