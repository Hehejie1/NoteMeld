from __future__ import annotations

from typing import Any, Mapping

from app.services.conversation_store import get_conversation
from app.services import agent_store


UI_ONLY_MESSAGE_TYPES = frozenset(
    {
        "note_progress",
        "note_result",
        "task_card",
        "task_card_progress",
        "parameter_request",
        "parameter_response",
        "knowledge_board",
    }
)


class ConversationHistoryStore:
    """Load the existing Conversation history without creating a second source."""

    def load_history(self, conversation_id: str) -> list[dict[str, Any]]:
        conversation = get_conversation(conversation_id)
        if not conversation:
            raise KeyError(conversation_id)
        history: list[dict[str, Any]] = []
        for message in conversation.get("messages", []):
            if message.get("message_type") in UI_ONLY_MESSAGE_TYPES:
                continue
            role = message.get("role")
            if role == "toolResult":
                role = "tool"
            if role not in {"system", "user", "assistant", "tool"}:
                continue
            item = {"role": role, "content": message.get("content") or ""}
            meta = message.get("meta") or {}
            if meta.get("tool_calls"):
                item["tool_calls"] = meta["tool_calls"]
            if meta.get("tool_call_id"):
                item["tool_call_id"] = meta["tool_call_id"]
            history.append(item)
        return history


class ProductionAgentStore:
    """SDK Store protocol adapter backed by NoteMeld's durable stores.

    The adapter deliberately contains no turn state machine.  It translates
    SDK commands to the existing transactional persistence service and keeps
    product message history out of the native runtime.
    """

    def begin_turn(self, command: Mapping[str, Any]) -> dict[str, Any]:
        request = command.get("request") if isinstance(command.get("request"), Mapping) else command
        session_id = str(request.get("session_id") or command.get("session_id") or "")
        turn_id = str(request.get("turn_id") or command.get("turn_id") or "") or None
        idem = request.get("request_id") or command.get("request_id")
        model = request.get("model") or command.get("model")
        return agent_store.create_turn(session_id, turn_id=turn_id, idempotency_key=idem, model_name=model)

    def load_history(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        session_id = str(query.get("session_id") or query.get("conversation_id") or "")
        return ConversationHistoryStore().load_history(session_id)

    def append_events(self, batch: Mapping[str, Any]) -> list[dict[str, Any]]:
        turn_id = str(batch.get("turn_id") or "")
        events = batch.get("events") or []
        if not isinstance(events, list):
            raise ValueError("events must be an array")
        persisted = []
        for event in events:
            if not isinstance(event, Mapping):
                raise ValueError("event must be an object")
            # Persist the envelope fields once; do not nest the envelope in
            # payload_json, which keeps replay wire-compatible with the SDK.
            persisted.append(agent_store.append_event(
                turn_id,
                dict(event.get("payload") or {}),
                event_type=str(event.get("type") or "unknown"),
                sequence=event.get("sequence"),
                event_id=event.get("event_id"),
            ))
        return persisted

    def checkpoint_messages(self, batch: Mapping[str, Any]) -> None:
        # Conversation projection is intentionally delegated to the existing
        # service.  Message checkpointing is optional for event-only turns.
        return None

    def finish_turn(self, command: Mapping[str, Any]) -> dict[str, Any]:
        return agent_store.transition_turn(
            str(command.get("turn_id") or ""),
            str(command.get("status") or "failed"),
            error_code=command.get("error_code"),
            error_message=command.get("error_message"),
            terminal_event=dict(command.get("terminal_event") or {"type": "turn.failed"}),
            terminal_event_type=str(command.get("event_type") or "turn.failed"),
        )

    def replay_events(self, query: Mapping[str, Any]) -> list[dict[str, Any]]:
        after = int(query.get("after_sequence", -1))
        return [item for item in agent_store.list_events(str(query.get("turn_id") or "")) if int(item["sequence"]) > after]

    def recover_nonterminal(self) -> list[str]:
        # Recovery is performed by the service startup migration in the full
        # application; this adapter has no second in-memory state to recover.
        return []
