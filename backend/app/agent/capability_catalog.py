"""L0-L3 渐进式能力目录。

L0 只读取轻量索引元数据，L1 返回候选能力卡片，L2 仅展开被选中的
schema，L3 才执行真实能力，避免首次模型调用平铺全部工具或 Wiki 正文。
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app.agent.builtin_tools import create_builtin_tools
from app.agent.core.tool import AgentTool, ToolResult
from app.agent.mcp_client import list_enabled_mcp_servers
from app.agent.memory import create_memory_tools
from app.agent.learning_tools import create_learning_tools
from app.agent.skill_loader import load_skills
from app.agent.workspace import create_workspace_tools
from app.utils.logger import get_logger
from app.utils.storage_paths import note_output_dir

logger = get_logger(__name__)

_DEFAULT_L0_MAX_CHARS = 1200
_DEFAULT_RESULT_LIMIT = 8
_MAX_RESULT_LIMIT = 20


@dataclass
class CapabilityCard:
    capability_id: str
    kind: str
    name: str
    summary: str
    tool: Optional[AgentTool] = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_l1_dict(self) -> dict[str, Any]:
        return {
            "id": self.capability_id,
            "kind": self.kind,
            "name": self.name,
            "summary": self.summary,
        }

    def to_l2_dict(self) -> dict[str, Any]:
        payload = self.to_l1_dict()
        if self.tool is not None:
            payload["input_schema"] = self.tool.parameters
            payload["execution_mode"] = self.tool.execution_mode
        return payload


class CapabilityRegistry:
    """请求级能力目录；L0/L1 不执行能力。"""

    def __init__(
        self,
        *,
        use_wiki: bool,
        wiki_dir: str | Path | None,
        source_sink: list[dict],
        linked_task_id: str | None = None,
        mcp_servers: dict[str, dict] | None = None,
        wiki_search_factory: Any = None,
        wiki_store_factory: Any = None,
        mcp_discover: Any = None,
        **_: Any,
    ) -> None:
        self.use_wiki = bool(use_wiki)
        self.wiki_dir = Path(wiki_dir) if wiki_dir is not None else None
        self.source_sink = source_sink
        self.linked_task_id = linked_task_id
        self.mcp_servers = {
            str(server_id): dict(config)
            for server_id, config in (mcp_servers or {}).items()
            if isinstance(config, dict) and config.get("enabled") is True
        }
        self._wiki_search_factory = wiki_search_factory or _default_wiki_search_factory
        self._wiki_store_factory = wiki_store_factory or _default_wiki_store_factory
        self._mcp_discover = mcp_discover or _default_mcp_discover
        self._mcp_adapters: list[Any] = []
        self._discovered_mcp_servers: set[str] = set()
        self._mcp_discovery_locks: dict[str, asyncio.Lock] = {}
        self._cards: dict[str, CapabilityCard] = {}
        if self.use_wiki:
            self._register_wiki_search()
        self._register_mcp_servers()

    @property
    def capability_ids(self) -> list[str]:
        return sorted(self._cards)

    def register_tool(
        self,
        capability_id: str,
        kind: str,
        tool: AgentTool,
        summary: str | None = None,
    ) -> None:
        self._cards[capability_id] = CapabilityCard(
            capability_id=capability_id,
            kind=kind,
            name=tool.name,
            summary=(summary or tool.description or tool.name).strip(),
            tool=tool,
        )

    def build_l0_summary(
        self,
        question: str,
        max_chars: int = _DEFAULT_L0_MAX_CHARS,
    ) -> str:
        safe_max_chars = max(1, min(int(max_chars), _DEFAULT_L0_MAX_CHARS))
        parts = ["[能力地图 L0]"]
        if self.use_wiki:
            snapshot = self._wiki_snapshot()
            nodes = snapshot["nodes"]
            communities = snapshot["communities"]
            if nodes:
                parts.append(
                    f"个人 Wiki：{len(nodes)} 个节点、{len(communities)} 个主题；"
                    f"主要内容：{_community_labels(communities)}。"
                )
                hints = _match_wiki_hints(question, nodes)
                if hints:
                    parts.append(f"本轮候选：{'、'.join(hints)}。")
            else:
                parts.append("个人 Wiki 当前为空。")
        local_cards = [
            card
            for card in self._cards.values()
            if card.kind not in {"wiki", "mcp_server", "mcp"}
        ]
        if local_cards:
            parts.append(_local_capability_summary(local_cards))
        if self.mcp_servers:
            names = [
                str(config.get("name") or server_id).strip()
                for server_id, config in self.mcp_servers.items()
            ]
            parts.append(f"MCP：{len(names)} 个已启用服务（{'、'.join(names[:6])}）。")
        parts.append(
            "普通聊天或已有上下文足够时无需调用；涉及个人知识、来源、证据或候选主题时，"
            "按 L1 发现→L2 描述→L3 执行，且不得伪造来源。"
        )
        return "\n".join(parts)[:safe_max_chars]

    def discover(
        self,
        query: str,
        kinds: list[str] | None = None,
        limit: int = _DEFAULT_RESULT_LIMIT,
    ) -> list[dict[str, Any]]:
        allowed = {str(kind).strip() for kind in (kinds or []) if str(kind).strip()}
        cards = [
            card
            for card in self._cards.values()
            if not allowed or card.kind in allowed
        ]
        ranked = sorted(
            cards,
            key=lambda card: (-_score_card(card, query), card.capability_id),
        )
        safe_limit = max(1, min(int(limit or _DEFAULT_RESULT_LIMIT), _MAX_RESULT_LIMIT))
        return [card.to_l1_dict() for card in ranked[:safe_limit]]

    async def describe(
        self,
        capability_ids: list[str],
        query: str = "",  # noqa: ARG002 - MCP filtering is added with lazy discovery
        limit: int = _DEFAULT_RESULT_LIMIT,
    ) -> list[dict[str, Any]]:
        safe_limit = max(1, min(int(limit or _DEFAULT_RESULT_LIMIT), _MAX_RESULT_LIMIT))
        selected: list[dict[str, Any]] = []
        for capability_id in capability_ids:
            normalized_id = str(capability_id)
            if normalized_id.startswith("mcp-server:"):
                server_id = normalized_id.removeprefix("mcp-server:")
                await self._ensure_mcp_server(server_id)
                child_cards = [
                    card
                    for card in self._cards.values()
                    if card.kind == "mcp"
                    and card.metadata.get("mcp_server_id") == server_id
                ]
                child_cards.sort(
                    key=lambda card: (-_score_card(card, query), card.capability_id),
                )
                for child_card in child_cards:
                    selected.append(child_card.to_l2_dict())
                    if len(selected) >= safe_limit:
                        return selected
                continue
            card = self._cards.get(normalized_id)
            if card is None:
                continue
            selected.append(card.to_l2_dict())
            if len(selected) >= safe_limit:
                break
        return selected

    async def close(self) -> None:
        """Best-effort 关闭本请求在 L2/L3 中建立的 MCP 连接。"""
        adapters, self._mcp_adapters = self._mcp_adapters, []
        for adapter in reversed(adapters):
            close = getattr(adapter, "close", None)
            if close is None:
                continue
            try:
                result = close()
                if asyncio.iscoroutine(result):
                    await result
            except Exception:  # noqa: BLE001 - cleanup must not mask request result
                continue

    async def invoke(
        self,
        capability_id: str,
        arguments: dict,
        call_id: str,
        signal: Any,
        on_update: Any,
    ) -> ToolResult:
        normalized_id = str(capability_id or "").strip()
        if normalized_id.startswith("wiki:") and not self.use_wiki:
            return _error_result(call_id, "Wiki 能力已由 use_wiki=false 关闭")
        if normalized_id.startswith("mcp:") and normalized_id not in self._cards:
            parts = normalized_id.split(":", 2)
            if len(parts) == 3:
                try:
                    await self._ensure_mcp_server(parts[1])
                except Exception:  # noqa: BLE001 - remote errors may contain secrets/URLs
                    return _error_result(call_id, "MCP capability 发现失败")
        card = self._cards.get(normalized_id)
        if card is None or card.tool is None or card.tool.execute is None:
            return _error_result(call_id, f"未找到 capability: {normalized_id}")
        if getattr(signal, "aborted", False):
            return _error_result(call_id, f"capability 已取消: {normalized_id}")
        try:
            result = await card.tool.execute(
                call_id,
                dict(arguments or {}),
                signal,
                on_update,
            )
        except Exception:  # noqa: BLE001 - tool failure must not crash or leak payloads
            return _error_result(call_id, f"capability 执行失败: {normalized_id}")
        normalized_result = _normalize_tool_result(call_id, result)
        if card.kind == "mcp" and normalized_result.is_error:
            return _error_result(call_id, f"MCP capability 执行失败: {normalized_id}")
        return normalized_result

    def _register_wiki_search(self) -> None:
        async def execute(call_id, params, signal, on_update):  # noqa: ARG001
            query = str(params.get("query") or "").strip()
            if not query:
                return _error_result(call_id, "Wiki 搜索缺少 query 参数")
            if self.wiki_dir is None:
                return _error_result(call_id, "Wiki 目录不可用")
            limit = max(1, min(int(params.get("limit") or 6), _MAX_RESULT_LIMIT))
            from app.services.query_intent import classify_query_intent

            searcher = self._wiki_search_factory(self.wiki_dir)
            results = await asyncio.to_thread(
                searcher.search,
                query,
                limit,
                classify_query_intent(query),
                self.linked_task_id,
            )
            self._append_sources(results or [])
            return _text_result(
                call_id,
                json.dumps({
                    "capability_id": "wiki:search",
                    "query": query,
                    "total": len(results or []),
                    "results": results or [],
                }, ensure_ascii=False),
            )

        self.register_tool(
            "wiki:search",
            "wiki",
            AgentTool(
                name="wiki_search",
                description="搜索个人 Wiki 中的实体、概念、观点、证据和关系。",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "问题或关键词"},
                        "limit": {"type": "integer", "description": "结果上限，默认 6"},
                    },
                    "required": ["query"],
                },
                execution_mode="parallel",
                execute=execute,
            ),
        )

        async def execute_read_page(call_id, params, signal, on_update):  # noqa: ARG001
            page_type = str(params.get("page_type") or "").strip()
            page_id = str(params.get("page_id") or "").strip()
            if page_type not in {"source", "entity", "concept"} or not page_id:
                return _error_result(
                    call_id,
                    "Wiki 页面需要有效的 page_type(source/entity/concept) 和 page_id",
                )
            if self.wiki_dir is None:
                return _error_result(call_id, "Wiki 目录不可用")
            max_chars = max(1, min(int(params.get("max_chars") or 6000), 12000))
            store = self._wiki_store_factory(self.wiki_dir)
            page = await asyncio.to_thread(store.get_file_page, page_type, page_id)
            if not page:
                return _error_result(call_id, f"Wiki 页面不存在: {page_type}/{page_id}")
            bounded_page = dict(page)
            markdown = str(bounded_page.get("markdown") or "")[:max_chars]
            bounded_page["markdown"] = markdown
            source = {
                "id": f"wiki-{page_type}-{bounded_page.get('id') or page_id}",
                "type": f"wiki_{page_type}" if page_type != "source" else "wiki_claim",
                "source_type": "wiki",
                "title": str(bounded_page.get("title") or page_id),
                "text": markdown[:800],
                "snippet": markdown[:800],
                "page_type": page_type,
                "page_id": str(bounded_page.get("id") or page_id),
                "metadata": {
                    "wiki_type": page_type,
                    "page_id": str(bounded_page.get("id") or page_id),
                },
            }
            self._append_sources([source])
            return _json_result(call_id, {
                "capability_id": "wiki:read_page",
                "page": bounded_page,
            })

        self.register_tool(
            "wiki:read_page",
            "wiki",
            AgentTool(
                name="wiki_read_page",
                description="读取 Wiki 搜索结果指向的 source/entity/concept 页面正文。",
                parameters={
                    "type": "object",
                    "properties": {
                        "page_type": {
                            "type": "string",
                            "enum": ["source", "entity", "concept"],
                            "description": "Wiki 页面类型",
                        },
                        "page_id": {"type": "string", "description": "搜索结果中的 page_id"},
                        "max_chars": {"type": "integer", "description": "正文字符上限，默认 6000"},
                    },
                    "required": ["page_type", "page_id"],
                },
                execution_mode="parallel",
                execute=execute_read_page,
            ),
        )

    def _register_mcp_servers(self) -> None:
        for server_id, config in self.mcp_servers.items():
            name = str(config.get("name") or server_id).strip()
            self._cards[f"mcp-server:{server_id}"] = CapabilityCard(
                capability_id=f"mcp-server:{server_id}",
                kind="mcp_server",
                name=name,
                summary=f"已启用的 MCP 服务 {name}；选择后才发现其工具。",
                metadata={"mcp_server_id": server_id},
            )

    async def _ensure_mcp_server(self, server_id: str) -> None:
        if server_id in self._discovered_mcp_servers:
            return
        lock = self._mcp_discovery_locks.setdefault(server_id, asyncio.Lock())
        async with lock:
            if server_id in self._discovered_mcp_servers:
                return
            config = self.mcp_servers.get(server_id)
            if config is None:
                return
            created_adapters: list[Any] = []
            try:
                tools = await self._mcp_discover(
                    {server_id: config},
                    adapters_out=created_adapters,
                )
            finally:
                self._mcp_adapters.extend(created_adapters)
            prefix = f"mcp_{server_id}_"
            for tool in tools or []:
                external_name = (
                    tool.name[len(prefix):]
                    if str(tool.name).startswith(prefix)
                    else str(tool.name)
                )
                capability_id = f"mcp:{server_id}:{external_name}"
                self.register_tool(capability_id, "mcp", tool)
                self._cards[capability_id].metadata["mcp_server_id"] = server_id
            self._discovered_mcp_servers.add(server_id)

    def _append_sources(self, results: list[dict]) -> None:
        seen = {
            str(item.get("id") or "")
            for item in self.source_sink
            if isinstance(item, dict)
        }
        for item in results:
            if not isinstance(item, dict):
                continue
            source_id = str(item.get("id") or "")
            if source_id and source_id in seen:
                continue
            self.source_sink.append(dict(item))
            if source_id:
                seen.add(source_id)

    def _wiki_snapshot(self) -> dict[str, list[dict[str, Any]]]:
        if not self.use_wiki or self.wiki_dir is None:
            return {"nodes": [], "communities": []}
        graph_path = self.wiki_dir / "graph.json"
        try:
            mtime_ns = graph_path.stat().st_mtime_ns
        except OSError:
            return {"nodes": [], "communities": []}
        return _load_wiki_snapshot(str(graph_path.resolve()), mtime_ns)


def build_free_chat_registry(
    *,
    conversation_id: str | None,
    linked_task_id: str | None,
    use_wiki: bool,
    long_task_manager: Any,
    source_sink: list[dict],
    wiki_dir: str | Path | None = None,
    mcp_servers: dict[str, dict] | None = None,
) -> CapabilityRegistry:
    """把 free-chat 的真实能力注册为请求级目录，不直接暴露给 LLM。"""
    registry = CapabilityRegistry(
        use_wiki=use_wiki,
        wiki_dir=wiki_dir if wiki_dir is not None else note_output_dir() / "wiki",
        source_sink=source_sink,
        linked_task_id=linked_task_id,
        mcp_servers=(
            list_enabled_mcp_servers()
            if mcp_servers is None
            else mcp_servers
        ),
    )
    for tool in create_builtin_tools(linked_task_id):
        if tool.name != "search_knowledge":
            registry.register_tool(f"builtin:{tool.name}", "builtin", tool)
    for tool in create_memory_tools():
        registry.register_tool(f"memory:{tool.name}", "memory", tool)
    if conversation_id:
        for tool in create_workspace_tools(conversation_id):
            registry.register_tool(f"workspace:{tool.name}", "workspace", tool)
        for tool in create_learning_tools(conversation_id):
            registry.register_tool(f"learning:{tool.name}", "learning", tool)
    for tool in load_skills(long_task_manager=long_task_manager):
        registry.register_tool(f"skill:{tool.name}", "skill", tool)
    return registry


def create_progressive_tools(registry: CapabilityRegistry) -> list[AgentTool]:
    """创建固定的 L1/L2/L3 元工具；具体能力 schema 不进入初始上下文。"""

    async def execute_discover(call_id, params, signal, on_update):  # noqa: ARG001
        if getattr(signal, "aborted", False):
            return _error_result(call_id, "capability discovery 已取消")
        try:
            rows = registry.discover(
                str(params.get("query") or ""),
                kinds=params.get("kinds") if isinstance(params.get("kinds"), list) else None,
                limit=params.get("limit") or _DEFAULT_RESULT_LIMIT,
            )
            return _json_result(call_id, {"level": "L1", "capabilities": rows})
        except Exception:  # noqa: BLE001 - avoid leaking capability payload/config
            return _error_result(call_id, "capability discovery 失败")

    async def execute_describe(call_id, params, signal, on_update):  # noqa: ARG001
        if getattr(signal, "aborted", False):
            return _error_result(call_id, "capability describe 已取消")
        capability_ids = params.get("capability_ids")
        if not isinstance(capability_ids, list) or not capability_ids:
            return _error_result(call_id, "capability_describe 缺少 capability_ids")
        try:
            rows = await registry.describe(
                [str(value) for value in capability_ids],
                query=str(params.get("query") or ""),
                limit=params.get("limit") or _DEFAULT_RESULT_LIMIT,
            )
            return _json_result(call_id, {"level": "L2", "capabilities": rows})
        except Exception:  # noqa: BLE001 - MCP errors may include auth/url details
            return _error_result(call_id, "capability describe 失败")

    async def execute_invoke(call_id, params, signal, on_update):
        capability_id = str(params.get("capability_id") or "").strip()
        if not capability_id:
            return _error_result(call_id, "capability_invoke 缺少 capability_id")
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            return _error_result(call_id, "capability_invoke.arguments 必须是对象")
        return await registry.invoke(
            capability_id,
            arguments,
            call_id,
            signal,
            on_update,
        )

    return [
        AgentTool(
            name="capability_discover",
            label="发现能力",
            description=(
                "L1：按当前意图发现少量候选能力，只返回名称和摘要，不执行能力。"
                "已有上下文足够回答时无需调用。"
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "当前任务或检索意图"},
                    "kinds": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "可选能力类型过滤",
                    },
                    "limit": {"type": "integer", "description": "候选上限，默认 8"},
                },
                "required": ["query"],
            },
            execution_mode="parallel",
            execute=execute_discover,
        ),
        AgentTool(
            name="capability_describe",
            label="查看能力契约",
            description="L2：仅展开已选择能力的参数 schema；MCP 到此阶段才连接并发现工具。",
            parameters={
                "type": "object",
                "properties": {
                    "capability_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "L1 返回的能力 ID",
                    },
                    "query": {"type": "string", "description": "用于筛选 MCP 子工具的意图"},
                    "limit": {"type": "integer", "description": "描述上限，默认 8"},
                },
                "required": ["capability_ids"],
            },
            execution_mode="parallel",
            execute=execute_describe,
        ),
        AgentTool(
            name="capability_invoke",
            label="执行能力",
            description="L3：执行一个已经过 L2 确认参数契约的能力，并返回真实结果。",
            parameters={
                "type": "object",
                "properties": {
                    "capability_id": {"type": "string", "description": "待执行能力 ID"},
                    "arguments": {"type": "object", "description": "严格按 L2 schema 提供的参数"},
                },
                "required": ["capability_id", "arguments"],
            },
            execution_mode="serial",
            execute=execute_invoke,
        ),
    ]


@lru_cache(maxsize=8)
def _load_wiki_snapshot(
    graph_path_text: str,
    mtime_ns: int,  # noqa: ARG001 - cache key invalidates changed graph files
) -> dict[str, list[dict[str, Any]]]:
    graph_path = Path(graph_path_text)
    try:
        payload = json.loads(graph_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError, TypeError) as exc:
        logger.warning("Wiki L0 graph 读取失败 (%s)", type(exc).__name__)
        return {"nodes": [], "communities": []}
    if not isinstance(payload, dict):
        return {"nodes": [], "communities": []}
    nodes = [item for item in (payload.get("nodes") or []) if isinstance(item, dict)]
    communities = _normalize_communities(payload.get("communities"))
    return {"nodes": nodes, "communities": communities}


def _normalize_communities(value: Any) -> list[dict[str, Any]]:
    if isinstance(value, dict):
        items = value.values()
    elif isinstance(value, list):
        items = value
    else:
        return []
    return [item for item in items if isinstance(item, dict)]


def _community_labels(communities: list[dict[str, Any]], limit: int = 6) -> str:
    ranked = sorted(
        communities,
        key=lambda item: (-_as_int(item.get("size")), str(item.get("label") or "")),
    )
    labels = [str(item.get("label") or "").strip() for item in ranked]
    labels = [label for label in labels if label][:limit]
    return "、".join(labels) if labels else "尚未形成主题聚类"


def _local_capability_summary(cards: list[CapabilityCard]) -> str:
    labels = {
        "builtin": "笔记",
        "memory": "记忆",
        "workspace": "工作区",
        "learning": "学习",
        "skill": "Skill",
    }
    grouped: dict[str, list[str]] = {}
    for card in cards:
        grouped.setdefault(card.kind, []).append(card.name)
    parts = []
    for kind in ("learning", "skill", "builtin", "workspace", "memory"):
        names = sorted(dict.fromkeys(grouped.get(kind, [])))
        if names:
            suffix = "…" if len(names) > 6 else ""
            parts.append(f"{labels[kind]} {len(names)}（{'、'.join(names[:6])}{suffix}）")
    return f"本地能力：{'；'.join(parts)}。"


def _match_wiki_hints(
    question: str,
    nodes: list[dict[str, Any]],
    limit: int = 5,
) -> list[str]:
    normalized_question = (question or "").casefold()
    matches: list[tuple[int, int, str]] = []
    for node in nodes:
        label = str(node.get("label") or "").strip()
        if len(label) < 2 or label.casefold() not in normalized_question:
            continue
        matches.append((len(label), -_as_int(node.get("size")), label))
    matches.sort()
    return list(dict.fromkeys(label for _, _, label in matches))[:limit]


def _score_card(card: CapabilityCard, query: str) -> int:
    normalized_query = (query or "").casefold().strip()
    if not normalized_query:
        return 0
    haystack = f"{card.capability_id}\n{card.name}\n{card.summary}".casefold()
    score = 20 if normalized_query in haystack else 0
    terms = re.findall(r"[a-z0-9_\-]{2,}|[\u4e00-\u9fff]{2,}", normalized_query)
    score += sum(1 for term in terms if term in haystack)
    return score


def _as_int(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def _default_wiki_search_factory(wiki_dir: Path):
    from app.services.wiki_search import WikiSearch

    return WikiSearch(wiki_dir)


def _default_wiki_store_factory(wiki_dir: Path):
    from app.services.wiki_store import WikiStore

    return WikiStore(wiki_dir)


async def _default_mcp_discover(servers: dict[str, dict], *, adapters_out: list[Any]):
    from app.agent.mcp_client import discover_all_tools

    return await discover_all_tools(servers, adapters_out=adapters_out)


def _normalize_tool_result(call_id: str, result: Any) -> ToolResult:
    if isinstance(result, ToolResult):
        return result
    if isinstance(result, dict):
        return ToolResult(
            call_id=str(result.get("call_id") or call_id),
            content=result.get("content") or [],
            details=result.get("details") or {},
            is_error=bool(result.get("is_error", False)),
        )
    return _text_result(call_id, str(result))


def _text_result(call_id: str, text: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": text}],
        is_error=False,
    )


def _json_result(call_id: str, payload: dict[str, Any]) -> ToolResult:
    return _text_result(call_id, json.dumps(payload, ensure_ascii=False))


def _error_result(call_id: str, message: str) -> ToolResult:
    return ToolResult(
        call_id=call_id,
        content=[{"type": "text", "text": message}],
        is_error=True,
    )


__all__ = [
    "CapabilityCard",
    "CapabilityRegistry",
    "build_free_chat_registry",
    "create_progressive_tools",
]
