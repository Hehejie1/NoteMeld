from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.services import agent_store


class SessionBusyError(RuntimeError):
    code = "session_busy"


@dataclass
class ActiveTurn:
    session_id: str
    turn_id: str


class TurnManager:
    def __init__(self) -> None:
        self._active: dict[str, ActiveTurn] = {}
        self._lock = Lock()

    def active_turn(self, session_id: str) -> str | None:
        with self._lock:
            active = self._active.get(session_id)
            return active.turn_id if active else None

    def start_turn(self, session_id: str, content: str, *, model_name: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        with self._lock:
            if session_id in self._active:
                raise SessionBusyError("session already has an active turn")
            turn = agent_store.create_turn(session_id, model_name=model_name, idempotency_key=idempotency_key)
            if turn.pop("_replayed", False):
                turn["replayed"] = True
                return turn
            self._active[session_id] = ActiveTurn(session_id, turn["turn_id"])
        # Durable user/message persistence belongs to AgentSdkHost's Store
        # adapter. Keeping it out of this coordination shim prevents duplicate
        # Conversation rows and lets unit callers use a fake store.
        turn["replayed"] = False
        return turn

    def finish_turn(self, session_id: str, turn_id: str, status: str, event: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        result = agent_store.transition_turn(turn_id, status=status, terminal_event=event, **kwargs)
        with self._lock:
            active = self._active.get(session_id)
            if active and active.turn_id == turn_id:
                self._active.pop(session_id, None)
        return result
