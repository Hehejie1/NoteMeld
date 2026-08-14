"""L0-L3 渐进式能力目录契约测试。"""

from __future__ import annotations

import importlib
import asyncio
import json
import pathlib
import sys
import tempfile
import unittest
from unittest.mock import AsyncMock, patch


ROOT = pathlib.Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.agent.core.tool import AgentTool  # noqa: E402
from app.agent.core.signal import AbortSignal  # noqa: E402


def _tool(name: str, description: str = "工具说明") -> AgentTool:
    async def execute(call_id, params, signal, on_update):  # noqa: ARG001
        return {
            "call_id": call_id,
            "content": [{"type": "text", "text": json.dumps(params, ensure_ascii=False)}],
            "is_error": False,
        }

    return AgentTool(
        name=name,
        description=description,
        parameters={
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "视频链接"},
            },
            "required": ["url"],
        },
        execution_mode="serial",
        execute=execute,
    )


class CapabilityCatalogL0L1Test(unittest.TestCase):
    def _catalog_module(self):
        try:
            return importlib.import_module("app.agent.capability_catalog")
        except ModuleNotFoundError as exc:
            self.fail(f"渐进式能力目录尚未实现: {exc}")

    def test_l0_summary_uses_graph_metadata_and_adds_exact_query_hint(self):
        """缺少 graph 元数据总览或长尾名称 hint 会使模型漏掉个人知识。"""
        module = self._catalog_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki_dir = pathlib.Path(temp_dir)
            (wiki_dir / "graph.json").write_text(
                json.dumps({
                    "nodes": [
                        {"id": "concept:RAG", "label": "RAG", "type": "concept", "size": 8},
                        {"id": "entity:Agent", "label": "Agent", "type": "entity", "size": 5},
                    ],
                    "communities": {
                        "0": {"id": 0, "label": "知识库 / RAG", "size": 2},
                    },
                }),
                encoding="utf-8",
            )

            registry = module.CapabilityRegistry(
                use_wiki=True,
                wiki_dir=wiki_dir,
                source_sink=[],
            )
            summary = registry.build_l0_summary("我的知识库里什么是 RAG？")

        self.assertIn("2 个节点", summary)
        self.assertIn("知识库 / RAG", summary)
        self.assertIn("本轮候选：RAG", summary)
        self.assertLessEqual(len(summary), 1200)

    def test_l1_discovery_does_not_expose_unselected_tool_schema(self):
        """L1 若返回完整 schema，就会重新引入全工具提示词膨胀。"""
        module = self._catalog_module()
        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
        )
        registry.register_tool(
            "skill:compile_source",
            "skill",
            _tool("compile_source", "编译视频为结构化笔记"),
        )

        cards = registry.discover("编译视频", kinds=["skill"], limit=8)

        self.assertEqual(cards, [{
            "id": "skill:compile_source",
            "kind": "skill",
            "name": "compile_source",
            "summary": "编译视频为结构化笔记",
        }])
        serialized = json.dumps(cards, ensure_ascii=False)
        self.assertNotIn("input_schema", serialized)
        self.assertNotIn("properties", serialized)
        self.assertNotIn("markdown", serialized.lower())

    def test_l2_describe_only_returns_selected_capability_schema(self):
        """L2 不能把未选择 Skill 的参数契约一并带入模型上下文。"""
        module = self._catalog_module()
        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
        )
        registry.register_tool(
            "skill:compile_source",
            "skill",
            _tool("compile_source", "编译视频为结构化笔记"),
        )
        registry.register_tool(
            "skill:other",
            "skill",
            _tool("other", "执行另一个任务"),
        )

        rows = asyncio.run(registry.describe(["skill:compile_source"]))

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["id"], "skill:compile_source")
        self.assertEqual(
            rows[0]["input_schema"]["properties"]["url"]["type"],
            "string",
        )
        self.assertNotIn("skill:other", json.dumps(rows, ensure_ascii=False))

    def test_l3_wiki_search_appends_results_to_dynamic_source_sink(self):
        """L3 Wiki 结果若不进入 sources，用户无法验证 Agent 的知识依据。"""
        module = self._catalog_module()
        calls = []

        class FakeWikiSearch:
            def search(self, query, limit=5, intent=None, linked_task_id=None):
                calls.append({
                    "query": query,
                    "limit": limit,
                    "intent": intent,
                    "linked_task_id": linked_task_id,
                })
                return [{
                    "id": "wiki-concept-rag",
                    "type": "wiki_concept",
                    "title": "RAG",
                    "snippet": "RAG 将检索结果提供给生成模型。",
                    "text": "RAG 将检索结果提供给生成模型。",
                    "score": 8.0,
                    "metadata": {"wiki_type": "concept", "name": "RAG"},
                }]

        sources = []
        registry = module.CapabilityRegistry(
            use_wiki=True,
            wiki_dir=pathlib.Path("/tmp/not-used-by-fake"),
            source_sink=sources,
            linked_task_id="task-linked",
            wiki_search_factory=lambda _: FakeWikiSearch(),
        )

        result = asyncio.run(registry.invoke(
            "wiki:search",
            {"query": "什么是 RAG", "limit": 6},
            "call-wiki",
            AbortSignal(),
            None,
        ))

        self.assertFalse(result.is_error)
        self.assertEqual(calls[0]["query"], "什么是 RAG")
        self.assertEqual(calls[0]["limit"], 6)
        self.assertEqual(calls[0]["linked_task_id"], "task-linked")
        self.assertEqual(sources[0]["id"], "wiki-concept-rag")
        self.assertEqual(sources[0]["title"], "RAG")

    def test_l3_rejects_wiki_capability_when_use_wiki_is_false(self):
        """旧提示或缓存不能绕过 use_wiki 的硬关闭边界。"""
        module = self._catalog_module()
        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
        )

        result = asyncio.run(registry.invoke(
            "wiki:search",
            {"query": "RAG"},
            "call-disabled",
            AbortSignal(),
            None,
        ))

        self.assertTrue(result.is_error)
        self.assertIn("Wiki", result.content[0]["text"])

    def test_l3_wiki_read_page_returns_bounded_body_and_source(self):
        """搜索后的页面正文只应在 L3 读取，并继续进入可验证 sources。"""
        module = self._catalog_module()

        class FakeWikiStore:
            def get_file_page(self, page_type, page_id):
                return {
                    "type": page_type,
                    "id": page_id,
                    "title": "RAG",
                    "markdown": "# RAG\n" + ("正文" * 100),
                }

        sources = []
        registry = module.CapabilityRegistry(
            use_wiki=True,
            wiki_dir=pathlib.Path("/tmp/not-used-by-fake"),
            source_sink=sources,
            wiki_store_factory=lambda _: FakeWikiStore(),
        )

        result = asyncio.run(registry.invoke(
            "wiki:read_page",
            {"page_type": "concept", "page_id": "RAG", "max_chars": 40},
            "call-page",
            AbortSignal(),
            None,
        ))

        self.assertFalse(result.is_error)
        payload = json.loads(result.content[0]["text"])
        self.assertEqual(payload["page"]["id"], "RAG")
        self.assertLessEqual(len(payload["page"]["markdown"]), 40)
        self.assertEqual(sources[0]["id"], "wiki-concept-RAG")
        self.assertEqual(sources[0]["title"], "RAG")

    def test_mcp_server_is_only_discovered_at_l2_and_adapter_is_closed(self):
        """MCP 若在 L0/L1 连接或请求结束后不关闭，会增加延迟并泄漏连接。"""
        module = self._catalog_module()
        discovery_calls = []
        adapter = type("FakeAdapter", (), {})()
        adapter.close = AsyncMock()

        async def fake_discover(servers, *, adapters_out):
            discovery_calls.append(servers)
            adapters_out.append(adapter)
            return [_tool("mcp_issues_search_issue", "搜索问题追踪系统")]

        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
            mcp_servers={
                "issues": {
                    "name": "Issues",
                    "enabled": True,
                    "transport": "streamable_http",
                    "url": "https://mcp.example.test/api",
                    "headers": {"Authorization": "Bearer secret"},
                },
                "disabled": {
                    "name": "Disabled",
                    "enabled": False,
                    "transport": "stdio",
                    "command": "never-run",
                },
            },
            mcp_discover=fake_discover,
        )

        l0 = registry.build_l0_summary("帮我找 issue")
        l1 = registry.discover("issue")

        self.assertEqual(discovery_calls, [])
        self.assertIn("Issues", l0)
        self.assertNotIn("https://", l0)
        self.assertNotIn("secret", json.dumps(l1, ensure_ascii=False))
        self.assertIn("mcp-server:issues", [row["id"] for row in l1])
        self.assertNotIn("mcp-server:disabled", [row["id"] for row in l1])

        rows = asyncio.run(registry.describe(["mcp-server:issues"], query="搜索 issue"))

        self.assertEqual(len(discovery_calls), 1)
        self.assertEqual(rows[0]["id"], "mcp:issues:search_issue")
        self.assertIn("input_schema", rows[0])

        asyncio.run(registry.close())
        adapter.close.assert_awaited_once()

    def test_mcp_tool_can_lazy_discover_at_l3_from_capability_id(self):
        """模型已有稳定 capability id 时，L3 仍需安全补做单 server 发现。"""
        module = self._catalog_module()
        discovery_calls = []

        async def fake_discover(servers, *, adapters_out):  # noqa: ARG001
            discovery_calls.append(servers)
            return [_tool("mcp_issues_search_issue", "搜索问题追踪系统")]

        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
            mcp_servers={"issues": {"name": "Issues", "enabled": True}},
            mcp_discover=fake_discover,
        )

        result = asyncio.run(registry.invoke(
            "mcp:issues:search_issue",
            {"url": "ISSUE-42"},
            "call-mcp",
            AbortSignal(),
            None,
        ))

        self.assertFalse(result.is_error)
        self.assertEqual(len(discovery_calls), 1)
        self.assertIn("ISSUE-42", result.content[0]["text"])

    def test_parallel_mcp_describe_discovers_each_server_once(self):
        """并行 L2 请求不能为同一 server 重复建立 transport。"""
        module = self._catalog_module()
        discovery_calls = []

        async def fake_discover(servers, *, adapters_out):  # noqa: ARG001
            discovery_calls.append(servers)
            await asyncio.sleep(0.01)
            return [_tool("mcp_issues_search_issue", "搜索问题追踪系统")]

        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
            mcp_servers={"issues": {"name": "Issues", "enabled": True}},
            mcp_discover=fake_discover,
        )

        async def describe_twice():
            return await asyncio.gather(
                registry.describe(["mcp-server:issues"]),
                registry.describe(["mcp-server:issues"]),
            )

        rows = asyncio.run(describe_twice())

        self.assertEqual(len(discovery_calls), 1)
        self.assertEqual(rows[0][0]["id"], "mcp:issues:search_issue")
        self.assertEqual(rows[1][0]["id"], "mcp:issues:search_issue")

    def test_progressive_meta_tools_keep_initial_schema_set_fixed(self):
        """Agent 初始只能看到三个固定元工具，具体 Skill schema 必须等 L2。"""
        module = self._catalog_module()
        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
        )
        registry.register_tool(
            "skill:compile_source",
            "skill",
            _tool("compile_source", "编译视频为结构化笔记"),
        )

        tools = module.create_progressive_tools(registry)

        self.assertEqual(
            [tool.name for tool in tools],
            ["capability_discover", "capability_describe", "capability_invoke"],
        )
        initial_schema = json.dumps(
            [tool.to_openai_function() for tool in tools],
            ensure_ascii=False,
        )
        self.assertNotIn("compile_source", initial_schema)
        self.assertNotIn("视频链接", initial_schema)

        discover_result = asyncio.run(tools[0].execute(
            "call-discover",
            {"query": "编译视频", "kinds": ["skill"]},
            AbortSignal(),
            None,
        ))
        discover_text = discover_result.content[0]["text"]
        self.assertIn("skill:compile_source", discover_text)
        self.assertNotIn("input_schema", discover_text)

        describe_result = asyncio.run(tools[1].execute(
            "call-describe",
            {"capability_ids": ["skill:compile_source"]},
            AbortSignal(),
            None,
        ))
        self.assertIn("input_schema", describe_result.content[0]["text"])

        invoke_result = asyncio.run(tools[2].execute(
            "call-invoke",
            {
                "capability_id": "skill:compile_source",
                "arguments": {"url": "https://example.test/video"},
            },
            AbortSignal(),
            None,
        ))
        self.assertFalse(invoke_result.is_error)
        self.assertIn("https://example.test/video", invoke_result.content[0]["text"])

    def test_free_chat_builder_namespaces_capabilities_without_flattening_schemas(self):
        """Builder 必须保留能力来源命名空间，并让 L0 只给短名称地图。"""
        module = self._catalog_module()
        with patch.object(module, "create_builtin_tools", return_value=[
            _tool("search_knowledge", "旧聚合搜索"),
            _tool("read_note", "读取关联笔记"),
        ]), patch.object(module, "create_memory_tools", return_value=[
            _tool("update_user_profile", "更新用户画像"),
        ]), patch.object(module, "create_workspace_tools", return_value=[
            _tool("workspace_read", "读取会话工作空间"),
        ]), patch.object(module, "create_learning_tools", return_value=[
            _tool("build_learning_canvas", "构建可持续学习空间"),
        ]), patch.object(module, "load_skills", return_value=[
            _tool("compile_source", "编译视频为结构化笔记"),
        ]) as load_skills_mock:
            registry = module.build_free_chat_registry(
                conversation_id="cid-1",
                linked_task_id="task-1",
                use_wiki=True,
                long_task_manager="manager",
                source_sink=[],
                wiki_dir=pathlib.Path("/tmp/not-used"),
                mcp_servers={"issues": {"name": "Issues", "enabled": True}},
            )

        self.assertIn("wiki:search", registry.capability_ids)
        self.assertIn("builtin:read_note", registry.capability_ids)
        self.assertNotIn("builtin:search_knowledge", registry.capability_ids)
        self.assertIn("memory:update_user_profile", registry.capability_ids)
        self.assertIn("workspace:workspace_read", registry.capability_ids)
        self.assertIn("learning:build_learning_canvas", registry.capability_ids)
        self.assertIn("skill:compile_source", registry.capability_ids)
        self.assertIn("mcp-server:issues", registry.capability_ids)
        load_skills_mock.assert_called_once_with(long_task_manager="manager")

        l0 = registry.build_l0_summary("帮我编译一个视频")
        self.assertIn("compile_source", l0)
        self.assertIn("build_learning_canvas", l0)
        self.assertNotIn("properties", l0)
        self.assertLessEqual(len(l0), 1200)

    def test_l0_routing_hints_only_match_known_graph_names(self):
        """普通聊天不应被虚假 hint 推向搜索，明确实体名则应提示 Wiki 候选。"""
        module = self._catalog_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki_dir = pathlib.Path(temp_dir)
            (wiki_dir / "graph.json").write_text(json.dumps({
                "nodes": [
                    {"id": "concept:RAG", "label": "RAG", "type": "concept"},
                    {"id": "entity:Agent", "label": "Agent", "type": "entity"},
                ],
                "communities": {},
            }), encoding="utf-8")
            registry = module.CapabilityRegistry(
                use_wiki=True,
                wiki_dir=wiki_dir,
                source_sink=[],
            )
            scenarios = [
                ("你好", False),
                ("帮我润色这句话", False),
                ("我的知识库里 RAG 是什么", True),
                ("请给出 Agent 的来源证据", True),
            ]
            for question, expects_hint in scenarios:
                with self.subTest(question=question):
                    summary = registry.build_l0_summary(question)
                    self.assertEqual("本轮候选：" in summary, expects_hint)

    def test_wiki_off_and_mcp_summary_do_not_expose_sensitive_config(self):
        """Wiki 硬关闭且 L0/L1 只能显示 MCP 脱敏名称。"""
        module = self._catalog_module()
        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
            mcp_servers={"private": {
                "name": "Private MCP",
                "enabled": True,
                "url": "https://private.example/mcp",
                "headers": {"Authorization": "Bearer secret"},
                "env": {"API_KEY": "secret"},
            }},
        )

        self.assertFalse(any(
            capability_id.startswith("wiki:")
            for capability_id in registry.capability_ids
        ))
        rendered = registry.build_l0_summary("MCP") + json.dumps(
            registry.discover("MCP"), ensure_ascii=False,
        )
        self.assertIn("Private MCP", rendered)
        self.assertNotIn("secret", rendered)
        self.assertNotIn("https://private.example", rendered)

    def test_mcp_discovery_and_call_errors_are_sanitized(self):
        """远端异常文本可能包含 URL/header，不能原样回灌到模型上下文。"""
        module = self._catalog_module()

        async def failing_discover(servers, *, adapters_out):  # noqa: ARG001
            raise RuntimeError("https://private.example Bearer secret")

        registry = module.CapabilityRegistry(
            use_wiki=False,
            wiki_dir=None,
            source_sink=[],
            mcp_servers={"private": {"name": "Private", "enabled": True}},
            mcp_discover=failing_discover,
        )
        describe_tool = module.create_progressive_tools(registry)[1]
        discovery_error = asyncio.run(describe_tool.execute(
            "call-private",
            {"capability_ids": ["mcp-server:private"]},
            AbortSignal(),
            None,
        ))
        rendered_discovery = json.dumps(discovery_error.model_dump(), ensure_ascii=False)
        self.assertTrue(discovery_error.is_error)
        self.assertNotIn("secret", rendered_discovery)
        self.assertNotIn("https://", rendered_discovery)

        async def secret_error(call_id, params, signal, on_update):  # noqa: ARG001
            return {
                "call_id": call_id,
                "content": [{"type": "text", "text": "Bearer secret at https://private.example"}],
                "is_error": True,
            }

        registry.register_tool(
            "mcp:private:unsafe",
            "mcp",
            AgentTool(
                name="mcp_private_unsafe",
                description="远端工具",
                parameters={"type": "object", "properties": {}},
                execute=secret_error,
            ),
        )
        call_error = asyncio.run(registry.invoke(
            "mcp:private:unsafe", {}, "call-unsafe", AbortSignal(), None,
        ))
        rendered_call = json.dumps(call_error.model_dump(), ensure_ascii=False)
        self.assertTrue(call_error.is_error)
        self.assertNotIn("secret", rendered_call)
        self.assertNotIn("https://", rendered_call)

    def test_l0_is_bounded_and_graph_snapshot_is_cached_by_mtime(self):
        """大图不能放大 prompt，同一版本也不能每轮重复读取 graph.json。"""
        module = self._catalog_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            wiki_dir = pathlib.Path(temp_dir)
            graph_path = wiki_dir / "graph.json"
            graph_path.write_text(json.dumps({
                "nodes": [
                    {"id": f"concept:{index}", "label": f"topic-{index}"}
                    for index in range(10000)
                ],
                "communities": {},
            }), encoding="utf-8")
            registry = module.CapabilityRegistry(
                use_wiki=True,
                wiki_dir=wiki_dir,
                source_sink=[],
            )
            original_read_text = pathlib.Path.read_text
            with patch.object(
                pathlib.Path,
                "read_text",
                autospec=True,
                side_effect=original_read_text,
            ) as read_text:
                first = registry.build_l0_summary("topic-9999")
                registry.build_l0_summary("topic-1")

        graph_reads = [
            call
            for call in read_text.call_args_list
            if pathlib.Path(call.args[0]).name == "graph.json"
        ]
        self.assertLessEqual(len(first), 1200)
        self.assertIn("topic-9999", first)
        self.assertEqual(len(graph_reads), 1)


if __name__ == "__main__":
    unittest.main()
