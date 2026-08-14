"""P3-T5: mcp_client 单测 — 配置读写 + opt-in 安全 + discover_all_tools（mock transport）。

覆盖：
- settings_root / mcp_servers_config_path 路径
- load_mcp_servers：空配置/无文件/合法 JSON/损坏 JSON/非法 server_id 过滤
- save_mcp_servers → load_mcp_servers 往返一致
- list_enabled_mcp_servers：只返回 enabled=True（opt-in 安全）
- _build_transport：未知 transport / http 缺 url
- _parse_tool_call_result：content list / isError / 字符串包裹 / 无 content 序列化
- discover_all_tools：空 servers / mock transport 发现工具 / 工具名加 mcp_{sid}_ 前缀

不连真 MCP server、不联网；transport 用 fake 替身。
"""
from __future__ import annotations

import asyncio
import json
import os
import pathlib
import sys
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.core.signal import AbortSignal
from app.agent.core.tool import AgentTool, ToolResult
from app.agent.mcp_client import (
    MCPClientAdapter,
    MCPClientError,
    discover_all_tools,
    list_enabled_mcp_servers,
    load_mcp_servers,
    mcp_servers_config_path,
    save_mcp_servers,
    settings_root,
)
from app.agent.mcp_client import _build_transport, _parse_tool_call_result
from app.utils.storage_paths import note_output_dir


class _BaseTmpDirTest(unittest.TestCase):
    """NOTE_OUTPUT_DIR → tmp 目录，隔离配置文件。"""

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        os.environ["NOTE_OUTPUT_DIR"] = str(self._tmp.name)

    def tearDown(self) -> None:
        os.environ.pop("NOTE_OUTPUT_DIR", None)
        self._tmp.cleanup()


# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------


class McpConfigPathTest(_BaseTmpDirTest):
    def test_settings_root_under_note_output(self):
        self.assertEqual(settings_root(), (note_output_dir() / "settings").resolve())

    def test_mcp_servers_config_path(self):
        self.assertEqual(
            mcp_servers_config_path(),
            (note_output_dir() / "settings" / "mcp_servers.json").resolve(),
        )


# ---------------------------------------------------------------------------
# load_mcp_servers
# ---------------------------------------------------------------------------


class LoadMcpServersTest(_BaseTmpDirTest):
    def test_no_file_returns_empty(self):
        self.assertEqual(load_mcp_servers(), {})

    def test_empty_json_object_returns_empty(self):
        path = mcp_servers_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
        self.assertEqual(load_mcp_servers(), {})

    def test_valid_config_returns_servers(self):
        servers = {
            "srv1": {"name": "S1", "transport": "stdio", "enabled": True, "command": "python"},
            "srv2": {"name": "S2", "transport": "http", "enabled": False, "url": "http://x"},
        }
        save_mcp_servers(servers)
        loaded = load_mcp_servers()
        self.assertEqual(set(loaded.keys()), {"srv1", "srv2"})
        self.assertEqual(loaded["srv1"]["transport"], "stdio")

    def test_corrupted_json_returns_empty(self):
        path = mcp_servers_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{not valid json", encoding="utf-8")
        self.assertEqual(load_mcp_servers(), {})

    def test_filters_invalid_server_ids(self):
        # 非法 server_id（含空格/特殊字符）应被过滤
        servers = {
            "good-id": {"name": "G", "transport": "stdio", "enabled": True, "command": "x"},
            "bad id!": {"name": "B", "transport": "stdio", "enabled": True, "command": "x"},
        }
        save_mcp_servers(servers)
        loaded = load_mcp_servers()
        self.assertEqual(set(loaded.keys()), {"good-id"})

    def test_non_dict_servers_returns_empty(self):
        path = mcp_servers_config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "servers": []}), encoding="utf-8")
        self.assertEqual(load_mcp_servers(), {})


# ---------------------------------------------------------------------------
# save / load 往返
# ---------------------------------------------------------------------------


class SaveLoadRoundTripTest(_BaseTmpDirTest):
    def test_save_then_load_roundtrip(self):
        servers = {
            "alpha": {
                "name": "Alpha",
                "transport": "stdio",
                "enabled": True,
                "command": "python",
                "args": ["-m", "srv"],
                "timeout_seconds": 30,
            },
            "beta": {
                "name": "Beta",
                "transport": "http",
                "enabled": False,
                "url": "https://example.com/mcp",
            },
        }
        save_mcp_servers(servers)
        loaded = load_mcp_servers()
        self.assertEqual(loaded["alpha"]["command"], "python")
        self.assertEqual(loaded["alpha"]["args"], ["-m", "srv"])
        self.assertEqual(loaded["beta"]["url"], "https://example.com/mcp")
        self.assertFalse(loaded["beta"]["enabled"])

    def test_save_creates_parent_dirs(self):
        # 配置文件所在 settings 目录不存在时由 save 创建
        self.assertFalse(mcp_servers_config_path().parent.exists())
        save_mcp_servers({"s": {"transport": "stdio", "enabled": True, "command": "x"}})
        self.assertTrue(mcp_servers_config_path().exists())

    def test_parallel_saves_use_distinct_temporary_files(self):
        original_write_text = pathlib.Path.write_text
        write_barrier = threading.Barrier(2)

        def synchronized_write(path, *args, **kwargs):
            result = original_write_text(path, *args, **kwargs)
            if str(path).endswith(".tmp"):
                write_barrier.wait(timeout=2)
            return result

        with patch.object(pathlib.Path, "write_text", synchronized_write):
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures = [
                    pool.submit(
                        save_mcp_servers,
                        {name: {"transport": "stdio", "command": "x"}},
                    )
                    for name in ("alpha", "beta")
                ]
                errors = [future.exception() for future in futures]

        self.assertEqual(errors, [None, None])
        self.assertTrue(load_mcp_servers())


# ---------------------------------------------------------------------------
# list_enabled_mcp_servers（opt-in 安全）
# ---------------------------------------------------------------------------


class ListEnabledTest(_BaseTmpDirTest):
    def test_only_enabled_returned(self):
        servers = {
            "on": {"name": "On", "transport": "stdio", "enabled": True, "command": "x"},
            "off": {"name": "Off", "transport": "stdio", "enabled": False, "command": "x"},
            "unset": {"name": "Unset", "transport": "stdio", "command": "x"},  # 缺 enabled
        }
        save_mcp_servers(servers)
        enabled = list_enabled_mcp_servers()
        # 只返回 enabled=True 的；缺 enabled 视为未启用
        self.assertEqual(set(enabled.keys()), {"on"})

    def test_disabled_excluded(self):
        servers = {"only_off": {"name": "Off", "enabled": False}}
        save_mcp_servers(servers)
        self.assertEqual(list_enabled_mcp_servers(), {})


# ---------------------------------------------------------------------------
# _build_transport
# ---------------------------------------------------------------------------


class BuildTransportTest(unittest.TestCase):
    def test_unknown_transport_raises(self):
        with self.assertRaises(MCPClientError):
            _build_transport({"transport": "websocket", "name": "x"})

    def test_http_missing_url_raises(self):
        with self.assertRaises(MCPClientError):
            _build_transport({"transport": "http", "name": "x"})

    def test_sse_missing_url_raises(self):
        with self.assertRaises(MCPClientError):
            _build_transport({"transport": "sse", "name": "x"})


# ---------------------------------------------------------------------------
# _parse_tool_call_result
# ---------------------------------------------------------------------------


class ParseToolCallResultTest(unittest.TestCase):
    def test_content_list_passthrough(self):
        result = {"content": [{"type": "text", "text": "hello"}], "isError": False}
        tr = _parse_tool_call_result("c1", result)
        self.assertEqual(tr.call_id, "c1")
        self.assertFalse(tr.is_error)
        self.assertEqual(tr.content[0]["text"], "hello")

    def test_is_error_flag(self):
        result = {"content": [{"type": "text", "text": "boom"}], "isError": True}
        tr = _parse_tool_call_result("c2", result)
        self.assertTrue(tr.is_error)

    def test_string_content_wrapped(self):
        result = {"content": ["plain string"]}
        tr = _parse_tool_call_result("c3", result)
        self.assertEqual(tr.content[0], {"type": "text", "text": "plain string"})

    def test_no_content_serialized(self):
        result = {"isError": False, "extra": 1}
        tr = _parse_tool_call_result("c4", result)
        text = tr.content[0]["text"]
        self.assertIn("extra", text)

    def test_non_dict_result_as_text(self):
        tr = _parse_tool_call_result("c5", [1, 2, 3])  # type: ignore[arg-type]
        text = tr.content[0]["text"]
        self.assertIn("1", text)


# ---------------------------------------------------------------------------
# discover_tools / discover_all_tools（mock transport，不连真 server）
# ---------------------------------------------------------------------------


class _FakeTransport:
    """假 transport：按预设响应 tools/list 与 tools/call。"""

    def __init__(self, tools_list: list[dict]) -> None:
        self._tools_list = tools_list
        self.closed = False
        self.rpc_calls: list[tuple[str, dict]] = []

    async def rpc(self, method: str, params: dict | None, *, timeout: float):  # noqa: ARG002
        self.rpc_calls.append((method, params or {}))
        if method == "tools/list":
            return {"tools": self._tools_list}
        if method == "tools/call":
            return {"content": [{"type": "text", "text": "tool-output"}], "isError": False}
        return {}

    async def close(self) -> None:
        self.closed = True


class DiscoverToolsTest(_BaseTmpDirTest):
    @staticmethod
    def _run(coro):
        return asyncio.run(coro)

    def test_discover_tools_builds_agent_tools(self):
        cfg = {"name": "FakeSrv", "transport": "stdio", "enabled": True, "command": "x"}
        fake = _FakeTransport([
            {"name": "search", "description": "search tool", "inputSchema": {"type": "object"}},
            {"name": "fetch", "description": "fetch tool"},
        ])
        adapter = MCPClientAdapter(server_id="fake", server_config=cfg)
        try:
            with patch("app.agent.mcp_client._build_transport", return_value=fake):
                tools = self._run(adapter.discover_tools(cfg))
        finally:
            self._run(adapter.close())

        self.assertEqual(len(tools), 2)
        self.assertEqual({t.name for t in tools}, {"search", "fetch"})
        for t in tools:
            self.assertIsInstance(t, AgentTool)
            self.assertEqual(t.execution_mode, "serial")
        self.assertTrue(fake.closed)

    def test_discover_tools_disabled_returns_empty(self):
        cfg = {"name": "Disabled", "transport": "stdio", "enabled": False, "command": "x"}
        adapter = MCPClientAdapter(server_config=cfg)
        tools = self._run(adapter.discover_tools(cfg))
        self.assertEqual(tools, [])

    def test_discover_tools_timeout_returns_empty(self):
        import asyncio as _asyncio

        class _TimeoutTransport:
            async def rpc(self, method, params, *, timeout):  # noqa: ARG002
                raise _asyncio.TimeoutError()

            async def close(self) -> None:
                pass

        cfg = {"name": "Slow", "transport": "stdio", "enabled": True, "command": "x"}
        adapter = MCPClientAdapter(server_config=cfg)
        with patch("app.agent.mcp_client._build_transport", return_value=_TimeoutTransport()):
            tools = self._run(adapter.discover_tools(cfg))
        self.assertEqual(tools, [])

    def test_discover_tool_execute_calls_transport(self):
        cfg = {"name": "FakeSrv", "transport": "stdio", "enabled": True, "command": "x", "timeout_seconds": 5}
        fake = _FakeTransport([{"name": "ping", "description": "ping"}])
        adapter = MCPClientAdapter(server_id="fake", server_config=cfg)
        with patch("app.agent.mcp_client._build_transport", return_value=fake):
            tools = self._run(adapter.discover_tools(cfg))
            self.assertEqual(len(tools), 1)
            tool = tools[0]
            sig = AbortSignal()
            result = self._run(tool.execute("call-1", {"q": "hi"}, sig, None))
        self.assertIsInstance(result, ToolResult)
        self.assertFalse(result.is_error)
        self.assertEqual(result.content[0]["text"], "tool-output")
        # tools/call 被调用且参数正确
        call_found = any(m == "tools/call" for m, _ in fake.rpc_calls)
        self.assertTrue(call_found)
        self._run(adapter.close())

    def test_discover_all_tools_empty_servers(self):
        self.assertEqual(self._run(discover_all_tools({})), [])
        self.assertEqual(self._run(discover_all_tools(None)), [])  # 读空配置文件

    def test_discover_all_tools_with_mock_transport(self):
        servers = {
            "alpha": {"name": "Alpha", "transport": "stdio", "enabled": True, "command": "x"},
        }
        fake = _FakeTransport([
            {"name": "tool_a", "description": "A"},
            {"name": "tool_b", "description": "B"},
        ])
        adapters_out: list = []
        with patch("app.agent.mcp_client._build_transport", return_value=fake):
            tools = self._run(discover_all_tools(servers, adapters_out=adapters_out))

        # 工具名加 mcp_{sid}_ 前缀
        names = sorted(t.name for t in tools)
        self.assertEqual(names, ["mcp_alpha_tool_a", "mcp_alpha_tool_b"])
        # adapter 收集到 adapters_out
        self.assertEqual(len(adapters_out), 1)
        # 关闭
        for a in adapters_out:
            self._run(a.close())

    def test_discover_all_tools_disabled_skipped(self):
        servers = {
            "off": {"name": "Off", "transport": "stdio", "enabled": False, "command": "x"},
        }
        fake = _FakeTransport([{"name": "should_not_appear"}])
        with patch("app.agent.mcp_client._build_transport", return_value=fake):
            tools = self._run(discover_all_tools(servers))
        self.assertEqual(tools, [])
        # discover_tools 内部因 enabled=False 直接返回空，不调 transport


if __name__ == "__main__":
    unittest.main()
