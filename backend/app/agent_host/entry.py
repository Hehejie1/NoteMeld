"""Single application boundary for Agent session and turn lifecycle commands.

The HTTP/source/desktop entry layers call this facade instead of writing the
Agent tables directly.  It intentionally owns no in-memory session or turn
state; the canonical Conversation and transactional Agent Store remain the
only durable lifecycle facts.
"""
from __future__ import annotations

import uuid
from typing import Any

from app.services import agent_store
from app.services.conversation_store import (
    get_conversation,
    list_conversations,
    upsert_conversation,
)


SessionBusyError = agent_store.SessionBusyError
TurnNotFoundError = agent_store.TurnNotFoundError
TurnTerminalError = agent_store.TurnTerminalError
PreferenceError = agent_store.PreferenceError


class AgentHostEntry:
    def create_session(
        self,
        *,
        session_id: str | None = None,
        title: str = "",
    ) -> dict[str, Any]:
        return upsert_conversation(
            {
                "id": session_id or str(uuid.uuid4()),
                "title": title,
                "mode": "chat",
            }
        )

    def list_sessions(self) -> list[dict[str, Any]]:
        return list_conversations()

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        return get_conversation(session_id)

    def create_turn(
        self,
        session_id: str,
        *,
        model_name: str | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        return agent_store.create_turn(
            session_id,
            model_name=model_name,
            idempotency_key=idempotency_key,
        )

    def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        return agent_store.get_turn(turn_id)

    def finish_turn(
        self,
        _session_id: str,
        turn_id: str,
        status: str,
        event: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        return agent_store.transition_turn(
            turn_id,
            status,
            terminal_event=event,
            **kwargs,
        )

    def mark_cancelling(self, turn_id: str) -> dict[str, Any]:
        return agent_store.transition_turn(
            turn_id,
            "cancelling",
            terminal_event={"type": "turn.cancelling"},
            terminal_event_type="turn.cancelling",
        )

    def is_terminal(self, turn: dict[str, Any]) -> bool:
        return str(turn.get("status")) in agent_store.TERMINAL_STATUSES

    def recover_nonterminal(self) -> list[str]:
        return agent_store.recover_nonterminal()

    def get_model_preference(self, session_id: str) -> dict[str, Any]:
        return agent_store.get_model_preference(session_id)

    def set_model_preference(
        self,
        session_id: str,
        *,
        default_model_id: str | None,
        fallback_models: list[str],
    ) -> dict[str, Any]:
        return agent_store.set_model_preference(
            session_id,
            default_model_id=default_model_id,
            fallback_models=fallback_models,
        )


_entry = AgentHostEntry()


def get_agent_host_entry() -> AgentHostEntry:
    return _entry


__all__ = [
    "AgentHostEntry",
    "PreferenceError",
    "SessionBusyError",
    "TurnNotFoundError",
    "TurnTerminalError",
    "get_agent_host_entry",
]
