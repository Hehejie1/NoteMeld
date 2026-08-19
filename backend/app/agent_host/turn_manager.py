from __future__ import annotations

from typing import Any

from app.services import agent_store


SessionBusyError = agent_store.SessionBusyError


class TurnManager:
    def __init__(self) -> None:
        pass

    def active_turn(self, session_id: str) -> str | None:
        return None

    def start_turn(self, session_id: str, content: str, *, model_name: str | None = None, idempotency_key: str | None = None) -> dict[str, Any]:
        turn = agent_store.create_turn(session_id, model_name=model_name, idempotency_key=idempotency_key)
        # Keep compatibility with existing callers that expect a replay marker.
        if turn.pop("_replayed", False):
            turn["replayed"] = True
            return turn
        turn["replayed"] = False
        return turn

    def finish_turn(self, session_id: str, turn_id: str, status: str, event: dict[str, Any], **kwargs: Any) -> dict[str, Any]:
        return agent_store.transition_turn(turn_id, status=status, terminal_event=event, **kwargs)
