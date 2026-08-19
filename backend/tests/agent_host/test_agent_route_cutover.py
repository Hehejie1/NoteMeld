from __future__ import annotations

from pathlib import Path

from app.routers import agent, chat


ROOT = Path(__file__).parents[3]


def test_agent_v1_is_only_chat_execution_router():
    agent_paths = {route.path for route in agent.router.routes}
    chat_paths = {route.path for route in chat.router.routes}

    assert "/agent/v1/sessions/{session_id}/turns" in agent_paths
    assert "/agent/v1/turns/{turn_id}/events" in agent_paths
    assert "/chat/free" not in chat_paths
    assert "/chat/free/stream" not in chat_paths
    assert "/chat/ask" not in chat_paths


def test_web_tauri_and_cli_share_the_agent_v1_http_entry():
    frontend_agent = (ROOT / "frontend/src/services/agent.ts").read_text(encoding="utf-8")
    composer = (ROOT / "frontend/src/pages/HomePage/components/ChatComposer.tsx").read_text(encoding="utf-8")
    compatibility_chat = (ROOT / "frontend/src/services/chat.ts").read_text(encoding="utf-8")
    cli = (ROOT / "scripts/notemeld-agent.py").read_text(encoding="utf-8")
    desktop_entry = (ROOT / "backend/desktop_entry.py").read_text(encoding="utf-8")
    app_factory = (ROOT / "backend/app/__init__.py").read_text(encoding="utf-8")
    tauri_config = (ROOT / "desktop/src-tauri/tauri.conf.json").read_text(encoding="utf-8")

    assert "`/agent/v1/sessions/${sessionId}/turns`" in frontend_agent
    assert "'/agent/v1/sessions'" in frontend_agent
    assert "/api/agent/v1" in cli
    assert "startAgentTurn(" in composer
    assert "startAgentTurn(" in compatibility_chat
    assert "/chat/free/stream" not in composer
    assert "/chat/free/stream" not in compatibility_chat
    assert "from main import app" in desktop_entry
    assert 'app.include_router(agent.router, prefix="/api")' in app_factory
    assert '"frontendDist": "../../frontend/dist"' in tauri_config


def test_http_router_delegates_agent_writes_to_host_entry():
    source = (ROOT / "backend/app/routers/agent.py").read_text(encoding="utf-8")
    assert "get_agent_host_entry" in source
    assert "from app.services import agent_store" not in source
    assert "from app.services.conversation_store" not in source
    assert "agent_store.create_turn" not in source
    assert "agent_store.transition_turn" not in source
