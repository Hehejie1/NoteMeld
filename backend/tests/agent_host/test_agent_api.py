from __future__ import annotations

from app.routers import agent


def test_agent_router_is_versioned_and_exposes_core_commands():
    paths = {route.path for route in agent.router.routes}
    assert "/agent/v1/sessions" in paths
    assert "/agent/v1/sessions/{session_id}/turns" in paths
    assert "/agent/v1/turns/{turn_id}/events" in paths
    assert "/agent/v1/sessions/{session_id}/model-preference" in paths
