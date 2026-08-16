from __future__ import annotations

from typing import Any

from app.services.conversation_store import get_conversation


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
