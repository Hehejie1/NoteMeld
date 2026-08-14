"""P3-T5: MCP 客户端适配器（第三方 MCP server tools → AgentTool）。

设计要点（spec B.6 P3-T5）::

    class MCPClientAdapter:
        async def discover_tools(self, server_config: dict) -> list[AgentTool]:
            # 支持 stdio / HTTP / SSE transport
            # 每个 tool 的 execute 调 tools/call
            # auth 单独存用户配置，不在日志打 headers

实现策略：
- **不依赖** 官方 ``mcp`` Python SDK（项目未列入 requirements），手写最小 JSON-RPC 客户端。
- 三种 transport：
    - ``stdio``：``asyncio.create_subprocess_exec`` 启动子进程，stdin/stdout 走
      JSON-RPC 2.0；子进程生命周期 = adapter 生命周期（首次 RPC 时 lazy 启动，
      ``close()`` 时 kill）。
    - ``http``：直接 POST JSON-RPC envelope 到 ``url``，同步等待响应。
    - ``sse``：先 GET ``url`` 接收 SSE 事件，MCP 规范约定 server 通过 ``endpoint``
      事件告知 POST 端点；之后每次 RPC 走 POST + 监听 SSE 响应。本实现做最小化：
      一次 SSE 连接复用，按 ``id`` 匹配响应。
- **安全**：
    - settings 默认关闭（``enabled=False``），用户必须显式 opt-in。
    - ``auth`` 字段（headers/token/cookie）仅用于构造请求；任何日志只打
      ``server_id`` / ``method`` / ``tool_name`` / 错误类型，绝不打 headers。
- **超时降级**：``tools/list`` 或 ``tools/call`` 超时 → 返回空列表 / error ToolResult，
  不抛异常打断 Agent loop。
- **错误隔离**：单个 MCP server 故障不影响其他 server；adapter 内部捕获所有异常
  并 log warning。

server_config schema（存储在 ``note_results/settings/mcp_servers.json``）::

    {
      "server_id": {
        "name": "Example MCP",            # 展示名
        "transport": "stdio" | "http" | "sse",
        "enabled": true,                  # opt-in
        "timeout_seconds": 60,            # 单次 RPC 超时；缺省 60
        # stdio-only
        "command": "python",
        "args": ["-m", "my_mcp_server"],
        "env": {"FOO": "bar"},
        "cwd": "/path/to/dir",
        # http / sse
        "url": "https://example.com/mcp",
        "headers": {"Authorization": "Bearer xxx"},  # 不入日志
        "auth": {                                     # 不入日志
          "type": "bearer",
          "token": "..."
        }
      }
    }
"""
from __future__ import annotations

import asyncio
import json
import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from app.agent.core.signal import AbortSignal
from app.agent.core.tool import AgentTool, ToolResult
from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir

logger = get_logger(__name__)


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

#: 单次 RPC 默认超时（秒）。
DEFAULT_RPC_TIMEOUT = 60.0

#: 初始化握手超时（秒）。
INITIALIZE_TIMEOUT = 30.0

#: MCP 协议版本（initialize 请求用）。
_MCP_PROTOCOL_VERSION = "2024-11-05"

#: server_id 安全字符。
_SERVER_ID_RE = re.compile(r"^[A-Za-z0-9_\-]{1,64}$")
_MCP_CONFIG_WRITE_LOCK = threading.Lock()

#: 客户端名称/版本（initialize payload）。
_CLIENT_NAME = "notemeld-agent"
_CLIENT_VERSION = "1.0.0"


class MCPClientError(RuntimeError):
    """MCP 客户端错误（用于内部异常，不会冒泡到 Agent loop）。"""


# ---------------------------------------------------------------------------
# settings 文件路径
# ---------------------------------------------------------------------------


def settings_root() -> Path:
    """settings 根目录：``<note_output_dir>/settings``。"""
    return (note_output_dir() / "settings").resolve()


def mcp_servers_config_path() -> Path:
    """第三方 MCP server 配置文件路径。"""
    return (settings_root() / "mcp_servers.json").resolve()


def load_mcp_servers() -> dict[str, dict]:
    """读取 MCP server 配置（容错：缺失/损坏 → 空字典 + 警告）。

    Returns:
        ``{server_id: server_config_dict}``。
    """
    path = mcp_servers_config_path()
    if not path.exists():
        return {}
    try:
        raw = path.read_text(encoding="utf-8")
        payload = json.loads(raw)
    except Exception as exc:  # noqa: BLE001
        logger.warning("MCP server 配置文件损坏，使用空配置: %s (err=%s)", path, exc)
        return {}
    if not isinstance(payload, dict):
        return {}
    servers = payload.get("servers") if "servers" in payload else payload
    if not isinstance(servers, dict):
        return {}
    # 过滤掉非法 server_id
    return {sid: cfg for sid, cfg in servers.items() if _SERVER_ID_RE.match(sid or "") and isinstance(cfg, dict)}


def save_mcp_servers(servers: dict[str, dict]) -> None:
    """原子写 MCP server 配置。"""
    path = mcp_servers_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"version": 1, "updated_at": _now_iso(), "servers": servers}
    with _MCP_CONFIG_WRITE_LOCK:
        tmp_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=path.parent,
                prefix=f".{path.name}.",
                suffix=".tmp",
                delete=False,
            ) as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
                handle.flush()
                os.fsync(handle.fileno())
                tmp_name = handle.name
            Path(tmp_name).replace(path)
        finally:
            if tmp_name:
                Path(tmp_name).unlink(missing_ok=True)


def list_enabled_mcp_servers() -> dict[str, dict]:
    """返回所有 ``enabled=True`` 的 MCP server 配置。"""
    return {sid: cfg for sid, cfg in load_mcp_servers().items() if cfg.get("enabled") is True}


# ---------------------------------------------------------------------------
# JSON-RPC envelope
# ---------------------------------------------------------------------------


def _now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def _make_request(method: str, params: dict | None, request_id: int) -> dict:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "method": method,
        "params": params or {},
    }


def _make_notification(method: str, params: dict | None) -> dict:
    return {
        "jsonrpc": "2.0",
        "method": method,
        "params": params or {},
    }


def _parse_response(raw: dict) -> tuple[Any, Optional[dict]]:
    """解析 JSON-RPC 响应，返回 ``(result, error)``。

    error 为 None 表示成功；否则 error 是 ``{"code","message","data"}``。
    """
    if not isinstance(raw, dict):
        raise MCPClientError(f"非法 JSON-RPC 响应: {raw!r}")
    if "error" in raw and raw["error"] is not None:
        return None, raw["error"]
    return raw.get("result"), None


# ---------------------------------------------------------------------------
# Transport 抽象
# ---------------------------------------------------------------------------


class _Transport:
    """MCP transport 抽象基类。子类实现 ``rpc()`` 和 ``close()``。"""

    async def rpc(self, method: str, params: dict | None, *, timeout: float) -> Any:
        raise NotImplementedError

    async def close(self) -> None:
        pass


class _StdioTransport(_Transport):
    """stdio transport：spawn 子进程，stdin/stdout 走 JSON-RPC 2.0 行协议。

    生命周期：首次 ``rpc()`` lazy 启动子进程并完成 initialize 握手；
    ``close()`` kill 子进程。
    """

    def __init__(self, server_config: dict) -> None:
        self._config = server_config
        self._proc: Optional[asyncio.subprocess.Process] = None
        self._next_id: int = 1
        self._init_done: bool = False
        self._lock = asyncio.Lock()
        self._server_name = str(server_config.get("name") or "stdio")

    async def _ensure_started(self) -> None:
        if self._proc is not None and self._proc.returncode is None:
            return
        command = str(self._config.get("command") or "").strip()
        if not command:
            raise MCPClientError("stdio server 缺少 command")
        args = list(self._config.get("args") or [])
        env = dict(os.environ)
        cfg_env = self._config.get("env") or {}
        if isinstance(cfg_env, dict):
            for k, v in cfg_env.items():
                env[str(k)] = str(v)
        cwd = self._config.get("cwd") or None

        try:
            self._proc = await asyncio.create_subprocess_exec(
                command,
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env,
                cwd=cwd,
            )
        except FileNotFoundError as exc:
            raise MCPClientError(f"stdio MCP 启动失败（可执行文件不存在）: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise MCPClientError(f"stdio MCP 启动失败: {exc}") from exc

        logger.info("MCP stdio server 已启动: %s pid=%s", self._server_name, self._proc.pid)

        # initialize 握手
        await self._initialize()

    async def _initialize(self) -> None:
        if self._init_done:
            return
        params = {
            "protocolVersion": _MCP_PROTOCOL_VERSION,
            "capabilities": {},
            "clientInfo": {"name": _CLIENT_NAME, "version": _CLIENT_VERSION},
        }
        try:
            await self._rpc_raw("initialize", params, timeout=INITIALIZE_TIMEOUT)
            # initialized 通知（无 id，无响应）
            await self._send_notification(_make_notification("notifications/initialized", {}))
            self._init_done = True
        except Exception as exc:  # noqa: BLE001
            await self._kill()
            raise MCPClientError(f"stdio MCP initialize 失败: {exc}") from exc

    async def rpc(self, method: str, params: dict | None, *, timeout: float) -> Any:
        async with self._lock:
            await self._ensure_started()
            return await self._rpc_raw(method, params or {}, timeout=timeout)

    async def _rpc_raw(self, method: str, params: dict, *, timeout: float) -> Any:
        if self._proc is None or self._proc.returncode is not None:
            raise MCPClientError("stdio MCP 子进程已退出")
        request_id = self._next_id
        self._next_id += 1
        envelope = _make_request(method, params, request_id)
        await self._send_request(envelope)
        raw = await self._read_response(request_id, timeout=timeout)
        result, error = _parse_response(raw)
        if error is not None:
            raise MCPClientError(f"MCP {method} 返回错误: code={error.get('code')} message={error.get('message')}")
        return result

    async def _send_request(self, envelope: dict) -> None:
        assert self._proc and self._proc.stdin
        line = json.dumps(envelope, ensure_ascii=False) + "\n"
        try:
            self._proc.stdin.write(line.encode("utf-8"))
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            raise MCPClientError(f"stdio MCP stdin 写入失败: {exc}") from exc

    async def _send_notification(self, envelope: dict) -> None:
        assert self._proc and self._proc.stdin
        line = json.dumps(envelope, ensure_ascii=False) + "\n"
        try:
            self._proc.stdin.write(line.encode("utf-8"))
            await self._proc.stdin.drain()
        except (BrokenPipeError, ConnectionResetError) as exc:
            logger.warning("stdio MCP 通知发送失败: %s", exc)

    async def _read_response(self, expected_id: int, *, timeout: float) -> dict:
        assert self._proc and self._proc.stdout
        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise asyncio.TimeoutError()
            try:
                line_bytes = await asyncio.wait_for(self._proc.stdout.readline(), timeout=remaining)
            except asyncio.TimeoutError as exc:
                raise asyncio.TimeoutError(f"stdio MCP 等待响应超时 id={expected_id}") from exc
            if not line_bytes:
                # 子进程关闭 stdout
                stderr_tail = ""
                if self._proc.stderr:
                    try:
                        stderr_data = await asyncio.wait_for(self._proc.stderr.read(), timeout=1.0)
                        stderr_tail = (stderr_data or b"").decode("utf-8", errors="replace")[-512:]
                    except Exception:  # noqa: BLE001
                        pass
                raise MCPClientError(f"stdio MCP 子进程关闭 stdout (stderr_tail={stderr_tail!r})")
            try:
                raw = json.loads(line_bytes.decode("utf-8", errors="replace"))
            except json.JSONDecodeError:
                # 非 JSON 行（可能是 stderr 串到 stdout 的日志）→ 跳过
                continue
            if not isinstance(raw, dict):
                continue
            # 通知/无 id 的消息跳过
            if "id" not in raw:
                continue
            if raw["id"] != expected_id:
                # 期望之外的响应：跳过（不应该发生，因为我们串行）
                logger.warning("stdio MCP 收到非预期响应 id=%s expected=%s", raw.get("id"), expected_id)
                continue
            return raw

    async def _kill(self) -> None:
        proc = self._proc
        if proc is None:
            return
        try:
            if proc.returncode is None:
                try:
                    proc.terminate()
                except ProcessLookupError:
                    pass
                try:
                    await asyncio.wait_for(proc.wait(), timeout=2.0)
                except asyncio.TimeoutError:
                    try:
                        proc.kill()
                    except ProcessLookupError:
                        pass
        finally:
            self._proc = None
            self._init_done = False

    async def close(self) -> None:
        await self._kill()


class _HTTPTransport(_Transport):
    """HTTP transport：POST JSON-RPC envelope 到 ``url``，同步等待响应。

    最小实现：每次 RPC 一个 HTTP 请求；不维持 session。
    """

    def __init__(self, server_config: dict) -> None:
        self._config = server_config
        self._url = str(server_config.get("url") or "").strip()
        self._headers = self._build_headers(server_config)
        self._server_name = str(server_config.get("name") or "http")
        if not self._url:
            raise MCPClientError("http MCP server 缺少 url")

    @staticmethod
    def _build_headers(server_config: dict) -> dict[str, str]:
        headers: dict[str, str] = {"Content-Type": "application/json", "Accept": "application/json"}
        cfg_headers = server_config.get("headers") or {}
        if isinstance(cfg_headers, dict):
            for k, v in cfg_headers.items():
                headers[str(k)] = str(v)
        auth = server_config.get("auth") or {}
        if isinstance(auth, dict):
            auth_type = str(auth.get("type") or "").lower()
            if auth_type == "bearer" and auth.get("token"):
                headers["Authorization"] = f"Bearer {auth['token']}"
            elif auth_type == "basic" and auth.get("token"):
                import base64
                headers["Authorization"] = f"Basic {base64.b64encode(str(auth['token']).encode()).decode()}"
        return headers

    async def rpc(self, method: str, params: dict | None, *, timeout: float) -> Any:
        import httpx

        request_id = int(time.time() * 1000) % (1 << 31)
        envelope = _make_request(method, params or {}, request_id)
        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(self._url, json=envelope, headers=self._headers)
        except httpx.TimeoutException as exc:
            raise asyncio.TimeoutError(f"http MCP {method} 超时 {timeout}s") from exc
        except Exception as exc:  # noqa: BLE001
            raise MCPClientError(f"http MCP {method} 请求失败: {exc}") from exc

        if resp.status_code >= 400:
            raise MCPClientError(f"http MCP {method} HTTP {resp.status_code}")

        try:
            raw = resp.json()
        except Exception as exc:  # noqa: BLE001
            raise MCPClientError(f"http MCP {method} 响应非 JSON: {exc}") from exc

        result, error = _parse_response(raw)
        if error is not None:
            raise MCPClientError(f"MCP {method} 返回错误: code={error.get('code')} message={error.get('message')}")
        return result


class _SSETransport(_Transport):
    """SSE transport：GET ``url`` 监听 SSE，POST JSON-RPC 到 server 告知的 endpoint。

    最小实现：单连接复用，按 ``id`` 匹配响应。
    """

    def __init__(self, server_config: dict) -> None:
        self._config = server_config
        self._url = str(server_config.get("url") or "").strip()
        self._headers = _HTTPTransport._build_headers(server_config)
        self._server_name = str(server_config.get("name") or "sse")
        if not self._url:
            raise MCPClientError("sse MCP server 缺少 url")
        self._post_endpoint: Optional[str] = None
        self._client: Any = None  # httpx.AsyncClient
        self._response: Any = None  # httpx.Response stream
        self._next_id: int = 1
        self._init_done: bool = False
        self._lock = asyncio.Lock()

    async def _ensure_connected(self) -> None:
        if self._client is not None and self._response is not None:
            return
        import httpx

        try:
            self._client = httpx.AsyncClient(timeout=httpx.Timeout(connect=10.0, read=None, write=10.0, pool=10.0))
            # 流式打开 SSE
            self._response = await self._client.send(
                self._client.build_request("GET", self._url, headers=self._headers),
                stream=True,
            )
        except Exception as exc:  # noqa: BLE001
            await self._close_stream()
            raise MCPClientError(f"sse MCP 连接失败: {exc}") from exc

        # 等待 endpoint 事件
        try:
            await self._wait_for_endpoint(timeout=INITIALIZE_TIMEOUT)
        except Exception as exc:  # noqa: BLE001
            await self._close_stream()
            raise MCPClientError(f"sse MCP 等待 endpoint 失败: {exc}") from exc

    async def _wait_for_endpoint(self, *, timeout: float) -> None:
        assert self._response is not None
        deadline = time.monotonic() + timeout
        async for raw_line in self._response.aiter_lines():
            if time.monotonic() > deadline:
                raise asyncio.TimeoutError()
            line = raw_line.rstrip("\r\n")
            if not line.startswith("event:"):
                continue
            event_name = line[len("event:"):].strip()
            # 下一个 data: 行
            data_line = ""
            # aiter_lines 已经把行拆开了，我们再读一行
            # 简化：直接读 endpoint 数据
            if event_name == "endpoint":
                # 取下一行 data:
                async for nxt in self._response.aiter_lines():
                    if nxt.startswith("data:"):
                        data_line = nxt[len("data:"):].strip()
                        break
                    if not nxt.strip():
                        break
                if data_line:
                    # endpoint 可能是相对路径
                    if data_line.startswith("http://") or data_line.startswith("https://"):
                        self._post_endpoint = data_line
                    else:
                        from urllib.parse import urljoin
                        self._post_endpoint = urljoin(self._url, data_line)
                    logger.info("sse MCP endpoint: %s", self._post_endpoint)
                    return
        raise MCPClientError("sse MCP 未收到 endpoint 事件")

    async def rpc(self, method: str, params: dict | None, *, timeout: float) -> Any:
        async with self._lock:
            await self._ensure_connected()
            request_id = self._next_id
            self._next_id += 1
            envelope = _make_request(method, params or {}, request_id)
            # POST 请求
            try:
                post_resp = await self._client.post(self._post_endpoint, json=envelope, headers=self._headers, timeout=timeout)
            except Exception as exc:  # noqa: BLE001
                raise MCPClientError(f"sse MCP POST 失败: {exc}") from exc
            if post_resp.status_code >= 400:
                # 尝试解析 error
                try:
                    err_body = post_resp.json()
                except Exception:  # noqa: BLE001
                    err_body = post_resp.text[:200]
                raise MCPClientError(f"sse MCP POST HTTP {post_resp.status_code}: {err_body}")

            # 等待 SSE 响应（按 id 匹配）
            deadline = time.monotonic() + timeout
            async for raw_line in self._response.aiter_lines():
                if time.monotonic() > deadline:
                    raise asyncio.TimeoutError(f"sse MCP {method} 超时")
                line = raw_line.rstrip("\r\n")
                if not line.startswith("data:"):
                    continue
                data_str = line[len("data:"):].strip()
                if not data_str:
                    continue
                try:
                    raw = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                if not isinstance(raw, dict) or raw.get("id") != request_id:
                    continue
                result, error = _parse_response(raw)
                if error is not None:
                    raise MCPClientError(f"MCP {method} 返回错误: code={error.get('code')} message={error.get('message')}")
                return result
            raise MCPClientError(f"sse MCP 流关闭，未收到 id={request_id} 响应")

    async def _close_stream(self) -> None:
        if self._response is not None:
            try:
                await self._response.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._response = None
        if self._client is not None:
            try:
                await self._client.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._client = None
        self._post_endpoint = None
        self._init_done = False

    async def close(self) -> None:
        await self._close_stream()


# ---------------------------------------------------------------------------
# Transport 工厂
# ---------------------------------------------------------------------------


def _build_transport(server_config: dict) -> _Transport:
    transport = str(server_config.get("transport") or "stdio").lower().strip()
    if transport == "stdio":
        return _StdioTransport(server_config)
    if transport == "http":
        return _HTTPTransport(server_config)
    if transport == "sse":
        return _SSETransport(server_config)
    raise MCPClientError(f"不支持的 transport: {transport!r}")


# ---------------------------------------------------------------------------
# MCPClientAdapter
# ---------------------------------------------------------------------------


@dataclass
class MCPClientAdapter:
    """把第三方 MCP server 的 tools 转为 AgentTool。

    用法::

        adapter = MCPClientAdapter()
        try:
            tools = await adapter.discover_tools(server_config)
            # tools 可注册到 Agent
        finally:
            await adapter.close()

    Attributes:
        server_id: server 标识（仅用于日志）。
        server_config: 原始配置（含 auth，但日志不打 auth）。
    """

    server_id: str = ""
    server_config: dict = field(default_factory=dict)
    _transport: Optional[_Transport] = None
    _tools_cache: list[dict] = field(default_factory=list)

    async def discover_tools(self, server_config: dict) -> list[AgentTool]:
        """连 MCP server，调 tools/list，转 AgentTool。

        Args:
            server_config: server 配置（见模块 docstring schema）。

        Returns:
            AgentTool 列表；失败返回空列表（log warning）。
        """
        # 防御性：opt-in 检查
        if server_config.get("enabled") is False:
            logger.info("MCP server 未启用 (enabled=False)，跳过")
            return []

        try:
            self._transport = _build_transport(server_config)
        except MCPClientError as exc:
            logger.warning("MCP server %s transport 构建失败: %s", server_config.get("name", "?"), exc)
            return []

        timeout = float(server_config.get("timeout_seconds") or DEFAULT_RPC_TIMEOUT)
        try:
            raw_tools = await self._transport.rpc("tools/list", {}, timeout=timeout)
        except asyncio.TimeoutError:
            logger.warning("MCP server %s tools/list 超时（%ss）", server_config.get("name", "?"), timeout)
            await self._safe_close()
            return []
        except (MCPClientError, Exception) as exc:  # noqa: BLE001
            logger.warning("MCP server %s tools/list 失败: %s", server_config.get("name", "?"), exc)
            await self._safe_close()
            return []

        if not isinstance(raw_tools, dict):
            logger.warning("MCP server %s tools/list 响应非对象: %r", server_config.get("name", "?"), raw_tools)
            await self._safe_close()
            return []

        tool_defs = raw_tools.get("tools") or []
        if not isinstance(tool_defs, list):
            await self._safe_close()
            return []

        self._tools_cache = [t for t in tool_defs if isinstance(t, dict)]
        server_name = str(server_config.get("name") or server_config.get("transport") or "mcp")
        logger.info(
            "MCP server %s 发现 %d 个 tools: %s",
            server_name,
            len(self._tools_cache),
            [t.get("name") for t in self._tools_cache],
        )

        return [self._build_agent_tool(tool_def) for tool_def in self._tools_cache]

    def _build_agent_tool(self, tool_def: dict) -> AgentTool:
        tool_name = str(tool_def.get("name") or "").strip()
        description = str(tool_def.get("description") or tool_name)
        input_schema = tool_def.get("inputSchema") or {"type": "object", "properties": {}, "required": []}
        if not isinstance(input_schema, dict):
            input_schema = {"type": "object", "properties": {}, "required": []}

        # 工具名加 server 前缀避免冲突（除非已是合法 agent tool name）
        agent_tool_name = tool_name
        if not re.match(r"^[A-Za-z0-9_\-]{1,64}$", agent_tool_name):
            agent_tool_name = "mcp_tool"

        async def execute(call_id: str, params: dict, signal: AbortSignal, on_update) -> ToolResult:  # noqa: ARG001
            return await self._call_tool(tool_name, call_id, params, signal)

        return AgentTool(
            name=agent_tool_name,
            description=description,
            parameters=input_schema,
            label=tool_name,
            execution_mode="serial",  # MCP tool 默认串行，避免对端并发压力
            execute=execute,
        )

    async def _call_tool(
        self,
        tool_name: str,
        call_id: str,
        params: dict,
        signal: AbortSignal,
    ) -> ToolResult:
        if self._transport is None:
            return _error_result(call_id, f"MCP server 已关闭，无法调用 {tool_name}")
        if signal.aborted:
            return _error_result(call_id, f"调用 {tool_name} 前已被取消")

        timeout = float(self.server_config.get("timeout_seconds") or DEFAULT_RPC_TIMEOUT)
        call_params = {"name": tool_name, "arguments": params or {}}
        try:
            result = await self._transport.rpc("tools/call", call_params, timeout=timeout)
        except asyncio.TimeoutError:
            return _error_result(call_id, f"MCP {tool_name} 调用超时（{timeout}s）")
        except MCPClientError as exc:
            return _error_result(call_id, f"MCP {tool_name} 调用失败: {exc}")
        except Exception as exc:  # noqa: BLE001
            return _error_result(call_id, f"MCP {tool_name} 内部异常: {exc}")

        if signal.aborted:
            return _error_result(call_id, f"MCP {tool_name} 已被取消")

        return _parse_tool_call_result(call_id, result)

    async def close(self) -> None:
        await self._safe_close()

    async def _safe_close(self) -> None:
        if self._transport is not None:
            try:
                await self._transport.close()
            except Exception as exc:  # noqa: BLE001
                logger.warning("MCP transport close 失败: %s", exc)
            self._transport = None


# ---------------------------------------------------------------------------
# tools/call 结果解析
# ---------------------------------------------------------------------------


def _parse_tool_call_result(call_id: str, result: Any) -> ToolResult:
    """把 MCP tools/call 响应转为 ToolResult。

    MCP 响应::

        {
          "content": [{"type": "text", "text": "..."}],
          "isError": false  # 可选
        }
    """
    if not isinstance(result, dict):
        # 直接当作 text
        return _text_result(call_id, json.dumps(result, ensure_ascii=False))

    is_error = bool(result.get("isError") or result.get("is_error") or False)
    content = result.get("content")
    if isinstance(content, list) and content:
        # 直接复用 MCP content 数组（与 OpenAI tool message 兼容）
        # 仅做最低规范化：每项必须有 type
        norm: list[dict] = []
        for item in content:
            if isinstance(item, dict) and "type" in item:
                norm.append(item)
            elif isinstance(item, str):
                norm.append({"type": "text", "text": item})
            else:
                norm.append({"type": "text", "text": json.dumps(item, ensure_ascii=False)})
        return ToolResult(call_id=call_id, content=norm, is_error=is_error)

    # 无 content 字段：把整个 result 序列化为 text
    text = json.dumps(result, ensure_ascii=False, indent=2)
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": text}],
        is_error=is_error,
    )


# ---------------------------------------------------------------------------
# 入口：discover_all_tools
# ---------------------------------------------------------------------------


async def discover_all_tools(
    servers: Optional[dict[str, dict]] = None,
    *,
    adapters_out: Optional[list[MCPClientAdapter]] = None,
) -> list[AgentTool]:
    """从 settings 加载所有 enabled MCP server，并发 discover_tools。

    Args:
        servers: server 配置 dict；None 则从 ``load_mcp_servers()`` 读取。
        adapters_out: 可选 list，调用方传入用于收集已创建的 adapter，
            以便后续 ``close()``。调用方负责关闭。

    Returns:
        合并后的 AgentTool 列表（按 server_id + tool_name 排序）。
    """
    if servers is None:
        servers = list_enabled_mcp_servers()
    if not servers:
        return []

    async def _safe_discover(sid: str, cfg: dict) -> tuple[str, list[AgentTool], Optional[MCPClientAdapter]]:
        adapter = MCPClientAdapter(server_id=sid, server_config=cfg)
        try:
            tools = await adapter.discover_tools(cfg)
        except Exception as exc:  # noqa: BLE001
            logger.warning("MCP server %s discover 异常 (%s)", sid, type(exc).__name__)
            try:
                await adapter.close()
            except Exception:  # noqa: BLE001
                pass
            return sid, [], None
        return sid, tools, adapter

    results = await asyncio.gather(*[_safe_discover(sid, cfg) for sid, cfg in servers.items()], return_exceptions=False)

    all_tools: list[AgentTool] = []
    for sid, tools, adapter in results:
        if adapter is not None and adapters_out is not None:
            adapters_out.append(adapter)
        # 加 server_id 前缀避免跨 server 工具名冲突
        for tool in tools:
            tool.name = f"mcp_{sid}_{tool.name}" if not tool.name.startswith(f"mcp_{sid}_") else tool.name
            all_tools.append(tool)

    # 按 name 排序
    all_tools.sort(key=lambda t: t.name)
    return all_tools


# ---------------------------------------------------------------------------
# ToolResult 构造助手（与其他 agent 模块一致风格）
# ---------------------------------------------------------------------------


def _text_result(call_id: str, text: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": text}],
        is_error=False,
    )


def _error_result(call_id: str, message: str, *, details: dict | None = None) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": json.dumps({"error": message}, ensure_ascii=False)}],
        is_error=True,
        details=details or {},
    )


__all__ = [
    "MCPClientAdapter",
    "MCPClientError",
    "DEFAULT_RPC_TIMEOUT",
    "mcp_servers_config_path",
    "load_mcp_servers",
    "save_mcp_servers",
    "list_enabled_mcp_servers",
    "discover_all_tools",
]
