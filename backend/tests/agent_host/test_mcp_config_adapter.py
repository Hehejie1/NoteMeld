from __future__ import annotations

from app.agent_host.mcp_config import list_enabled_mcp_servers, load_mcp_servers, save_mcp_servers


def test_mcp_config_adapter_is_atomic_and_filters_ids(monkeypatch, tmp_path):
    monkeypatch.setenv("NOTE_OUTPUT_DIR", str(tmp_path))
    save_mcp_servers({"safe-1": {"enabled": True}, "bad/id": {"enabled": True}})
    assert load_mcp_servers() == {"safe-1": {"enabled": True}}
    assert list_enabled_mcp_servers() == {"safe-1": {"enabled": True}}
