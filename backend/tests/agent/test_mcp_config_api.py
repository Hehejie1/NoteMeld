from __future__ import annotations

import json
from unittest.mock import patch

from app.routers import config


def _payload(response) -> dict:
    return json.loads(response.body.decode("utf-8"))


def _private_server() -> dict:
    return {
        "name": "Private MCP",
        "transport": "http",
        "enabled": True,
        "url": "https://mcp.example.test/api",
        "headers": {
            "Authorization": "Bearer header-secret",
            "X-Tenant-Token": "tenant-secret",
        },
        "auth": {"type": "bearer", "token": "auth-secret"},
        "env": {"API_KEY": "env-secret"},
    }


def test_mcp_config_responses_never_expose_auth_headers_or_env() -> None:
    servers = {"private": _private_server()}

    with patch.object(config, "load_mcp_servers", return_value=servers), patch.object(
        config, "list_enabled_mcp_servers", return_value=servers
    ):
        listed = _payload(config.list_mcp_servers())
        enabled = _payload(config.get_enabled_mcp_servers())

    rendered = json.dumps([listed, enabled], ensure_ascii=False)
    assert "auth-secret" not in rendered
    assert "header-secret" not in rendered
    assert "tenant-secret" not in rendered
    assert "env-secret" not in rendered
    listed_config = listed["data"]["servers"]["private"]
    assert "auth" not in listed_config
    assert set(listed_config["headers"].values()) == {"***"}
    assert set(listed_config["env"].values()) == {"***"}


def test_mcp_update_preserves_redacted_credentials_and_returns_safe_config() -> None:
    servers = {"private": _private_server()}
    saved: dict[str, dict] = {}
    payload = config.McpServerConfigPayload(
        name="Private MCP renamed",
        transport="http",
        enabled=False,
        url="https://mcp.example.test/api",
        headers={
            "Authorization": "***",
            "X-Tenant-Token": "***",
            "X-Region": "cn",
        },
    )

    with patch.object(config, "load_mcp_servers", return_value=servers), patch.object(
        config, "save_mcp_servers", side_effect=lambda value: saved.update(value)
    ):
        response = _payload(config.upsert_mcp_server("private", payload))

    stored = saved["private"]
    assert stored["auth"] == {"type": "bearer", "token": "auth-secret"}
    assert stored["headers"]["Authorization"] == "Bearer header-secret"
    assert stored["headers"]["X-Tenant-Token"] == "tenant-secret"
    assert stored["headers"]["X-Region"] == "cn"
    rendered = json.dumps(response, ensure_ascii=False)
    assert "auth-secret" not in rendered
    assert "header-secret" not in rendered
    assert "tenant-secret" not in rendered


def test_mcp_save_error_does_not_echo_local_path_or_sensitive_payload() -> None:
    payload = config.McpServerConfigPayload(
        name="Private MCP",
        transport="stdio",
        command="private-command",
    )

    with patch.object(config, "load_mcp_servers", return_value={}), patch.object(
        config,
        "save_mcp_servers",
        side_effect=RuntimeError("/Users/private/.config/token-secret"),
    ):
        response = _payload(config.upsert_mcp_server("private", payload))

    rendered = json.dumps(response, ensure_ascii=False)
    assert response["code"] == 500
    assert "/Users/private" not in rendered
    assert "token-secret" not in rendered
