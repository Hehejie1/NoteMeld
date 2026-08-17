from __future__ import annotations

from app.routers import agent, chat


def test_agent_v1_is_only_chat_execution_router():
    agent_paths = {route.path for route in agent.router.routes}
    chat_paths = {route.path for route in chat.router.routes}

    assert "/agent/v1/sessions/{session_id}/turns" in agent_paths
    assert "/agent/v1/turns/{turn_id}/events" in agent_paths
    assert "/chat/free" not in chat_paths
    assert "/chat/free/stream" not in chat_paths
    assert "/chat/ask" not in chat_paths
