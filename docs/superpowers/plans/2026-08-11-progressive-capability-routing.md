# L0–L3 Progressive Capability Routing Implementation Plan

**执行状态：Completed（2026-08-11）**  
验证证据：[`docs/superpowers/tests/2026-08-11-progressive-capability-routing.md`](../tests/2026-08-11-progressive-capability-routing.md)。下方 checklist 保留为原始 TDD 执行配方，实际完成情况以验证证据和 canonical requirement 状态为准。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让 Agent free-chat 只接收固定的 L0–L3 元工具入口，由 LLM 按需发现、描述和执行 Wiki、Skill、MCP 等能力，不再在首次 LLM 调用前默认执行完整 Wiki 搜索。

**Architecture:** 新增请求级 `CapabilityRegistry`，把本地 AgentTool、Skill、Wiki 合成能力和 enabled MCP server 统一映射为带 namespace 的 capability。首轮 system prompt 只注入缓存的 L0 Wiki/工具概览与 query hints；LLM 通过三个固定元工具完成 L1 discover、L2 describe、L3 invoke。MCP 只在 L2/L3 延迟发现，Wiki L3 结果动态写回原有 `sources` list。

**Tech Stack:** Python 3.11、FastAPI、现有 notemeld-agent `AgentTool`/`ToolResult`、现有 `WikiSearch`/`WikiStore`、现有 MCP client adapter、pytest/unittest、React contract tests。

## Global Constraints

- 不修改 `/api/chat/free`、`/api/chat/free/stream` 请求字段、response wrapper 或既有 SSE 事件语义。
- `use_wiki=false` 必须同时阻止 Wiki 目录披露和 L3 执行。
- L0/L1 不读取 Wiki Markdown 正文、不连接 MCP、不新增 LLM 调用。
- L0 最长 1200 字符；query hints 最多 5 个；L1/L2 默认最多 8 条。
- 不新增数据库表、字段、持久化目录或第三方依赖。
- 不输出 MCP auth/header/env/url、Provider API Key、用户本地路径或原始敏感 payload。
- 保留 `AGENT_CHAT_ENABLED=false` legacy 回退。
- 当前 worktree 含大量用户未提交改动；只修改本 Plan/Spec 列出的文件，不执行 git commit，使用 `git diff --check` 作为任务检查点。

---

## File Structure

- Create `backend/app/agent/capability_catalog.py`：请求级能力注册表、Wiki L0 快照缓存、L1/L2/L3 元工具、MCP 延迟发现与关闭。
- Create `backend/tests/agent/test_capability_catalog.py`：目录层级、信息边界、Wiki sources、Skill/MCP lazy lifecycle 契约。
- Modify `backend/app/services/chat_service.py`：为 `_prepare_free_chat_context` 增加仅 Agent 使用的 `prefetch_wiki` kw-only 开关，legacy 默认值保持 `True`。
- Modify `backend/app/agent/chat_adapter.py`：Agent free-chat 使用 `prefetch_wiki=False`。
- Modify `backend/app/agent/agent_service.py`：构造 registry、注入 L0、只注册三个元工具、finally 关闭 MCP adapter。
- Modify `backend/tests/agent/test_agent_service_p3_integration.py`：从“直接注册 workspace/memory/skill”更新为“注册固定元工具并可通过 registry 渐进访问”。
- Modify `backend/tests/agent/test_chat_compat.py`：增加 Agent 不预搜与 legacy 仍预搜的兼容断言。
- Modify `docs/system/current-architecture.md`、`product-rules.md`、`api-inventory.md`、`known-pitfalls.md`：写回渐进式路由事实、`use_wiki` 语义和回归防线。
- Create `docs/superpowers/tests/2026-08-11-progressive-capability-routing.md`：最终验证命令、结果和指标。

### Task 1: Capability L0/L1 Contract Tests

**Files:**
- Create: `backend/tests/agent/test_capability_catalog.py`
- Test: `backend/tests/agent/test_capability_catalog.py`

**Interfaces:**
- Consumes: `AgentTool`, `ToolResult`, `AbortSignal`。
- Produces: 对 `CapabilityRegistry`、`create_progressive_tools`、`build_free_chat_registry` 的可执行契约。

- [ ] **Step 1: Write failing L0 snapshot tests**

```python
def test_l0_summary_uses_graph_only_and_includes_query_hint(tmp_path):
    graph = {
        "nodes": [
            {"id": "concept:RAG", "label": "RAG", "type": "concept", "size": 8},
            {"id": "entity:Agent", "label": "Agent", "type": "entity", "size": 5},
        ],
        "communities": {"0": {"label": "知识库 / RAG", "size": 2}},
    }
    (tmp_path / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    registry = CapabilityRegistry(use_wiki=True, wiki_dir=tmp_path, source_sink=[])
    summary = registry.build_l0_summary("什么是 RAG")
    assert "RAG" in summary
    assert "2 个节点" in summary
    assert len(summary) <= 1200
```

- [ ] **Step 2: Write failing L1 information-boundary tests**

```python
def test_discover_returns_cards_without_schema_or_markdown(registry_with_skill):
    cards = registry_with_skill.discover("编译视频", kinds=["skill"], limit=8)
    assert cards[0]["id"] == "skill:compile_source"
    assert "summary" in cards[0]
    assert "input_schema" not in cards[0]
    assert "parameters" not in cards[0]
    assert "markdown" not in json.dumps(cards, ensure_ascii=False).lower()
```

- [ ] **Step 3: Run tests and verify RED**

Run: `cd backend && python3 -m pytest tests/agent/test_capability_catalog.py -q`

Expected: FAIL during import because `app.agent.capability_catalog` does not exist.

- [ ] **Step 4: Checkpoint**

Run: `git diff --check -- backend/tests/agent/test_capability_catalog.py`

Expected: no whitespace errors.

### Task 2: CapabilityRegistry L0/L1 Minimal Implementation

**Files:**
- Create: `backend/app/agent/capability_catalog.py`
- Modify: `backend/tests/agent/test_capability_catalog.py`

**Interfaces:**
- Produces:
  - `CapabilityCard(id: str, kind: str, name: str, summary: str, tool: AgentTool | None, metadata: dict)`
  - `CapabilityRegistry(use_wiki: bool, wiki_dir: Path | None, source_sink: list[dict], linked_task_id: str | None = None, mcp_servers: dict | None = None, wiki_search_factory: Callable = WikiSearch, mcp_discover: Callable = discover_all_tools)`
  - `CapabilityRegistry.register_tool(capability_id: str, kind: str, tool: AgentTool, summary: str | None = None) -> None`
  - `CapabilityRegistry.build_l0_summary(question: str, max_chars: int = 1200) -> str`
  - `CapabilityRegistry.discover(query: str, kinds: list[str] | None = None, limit: int = 8) -> list[dict]`

- [ ] **Step 1: Implement cached graph snapshot**

```python
@lru_cache(maxsize=8)
def _load_wiki_snapshot(graph_path_text: str, mtime_ns: int) -> dict:
    path = Path(graph_path_text)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"nodes": [], "communities": []}
    return {
        "nodes": list(payload.get("nodes") or []),
        "communities": _normalize_communities(payload.get("communities")),
    }
```

- [ ] **Step 2: Implement bounded L0 summary and exact-name query hints**

```python
def build_l0_summary(self, question: str, max_chars: int = 1200) -> str:
    parts = ["[能力地图 L0]"]
    if self.use_wiki:
        snapshot = self._wiki_snapshot()
        hints = _match_wiki_hints(question, snapshot["nodes"], limit=5)
        parts.append(_render_wiki_overview(snapshot, hints))
    parts.append(self._render_local_tool_overview())
    parts.append(self._render_mcp_overview())
    parts.append("普通聊天无需调用；涉及个人知识、来源、证据或候选主题时按 L1发现→L2描述→L3执行。")
    return "\n".join(parts)[:max_chars]
```

- [ ] **Step 3: Implement L1 cards without schemas**

```python
def discover(self, query: str, kinds: list[str] | None = None, limit: int = 8) -> list[dict]:
    allowed = set(kinds or [])
    cards = [card for card in self._cards.values() if not allowed or card.kind in allowed]
    ranked = sorted(cards, key=lambda card: (-_score_card(card, query), card.id))
    return [card.to_l1_dict() for card in ranked[:_bounded_limit(limit)]]
```

- [ ] **Step 4: Run L0/L1 tests**

Run: `cd backend && python3 -m pytest tests/agent/test_capability_catalog.py -q`

Expected: L0/L1 tests PASS; L2/L3 tests added later may still be absent.

- [ ] **Step 5: Checkpoint**

Run: `git diff --check -- backend/app/agent/capability_catalog.py backend/tests/agent/test_capability_catalog.py`

Expected: no whitespace errors.

### Task 3: L2/L3, Wiki Sources, Skill and MCP Lifecycle

**Files:**
- Modify: `backend/tests/agent/test_capability_catalog.py`
- Modify: `backend/app/agent/capability_catalog.py`

**Interfaces:**
- Produces:
  - `async CapabilityRegistry.describe(capability_ids: list[str], query: str = "", limit: int = 8) -> list[dict]`
  - `async CapabilityRegistry.invoke(capability_id: str, arguments: dict, call_id: str, signal: AbortSignal, on_update: Any) -> ToolResult`
  - `async CapabilityRegistry.close() -> None`
  - `create_progressive_tools(registry: CapabilityRegistry) -> list[AgentTool]`

- [ ] **Step 1: Write failing L2 selected-schema test**

```python
async def test_describe_only_returns_selected_schema(registry_with_two_tools):
    rows = await registry_with_two_tools.describe(["skill:compile_source"])
    assert [row["id"] for row in rows] == ["skill:compile_source"]
    assert rows[0]["input_schema"]["properties"]["url"]["type"] == "string"
    assert "skill:other" not in json.dumps(rows)
```

- [ ] **Step 2: Write failing Wiki L3 source-sink test**

```python
async def test_invoke_wiki_search_appends_dynamic_sources(fake_wiki_search, tmp_path):
    sources = []
    registry = CapabilityRegistry(
        use_wiki=True,
        wiki_dir=tmp_path,
        source_sink=sources,
        wiki_search_factory=lambda _: fake_wiki_search,
    )
    result = await registry.invoke(
        "wiki:search", {"query": "RAG", "limit": 6}, "call-1", AbortSignal(), None
    )
    assert result.is_error is False
    assert sources[0]["type"] == "wiki_concept"
    assert sources[0]["title"] == "RAG"
```

- [ ] **Step 3: Write failing MCP lazy-discovery/close test**

```python
async def test_mcp_is_lazy_until_describe_and_closed(fake_discover):
    adapter = SimpleNamespace(close=AsyncMock())

    async def discover(servers, *, adapters_out):
        adapters_out.append(adapter)
        return [build_agent_tool("mcp_issues_search_issue")]

    registry = CapabilityRegistry(
        use_wiki=False,
        wiki_dir=None,
        source_sink=[],
        mcp_servers={"issues": {"name": "Issues", "enabled": True}},
        mcp_discover=discover,
    )
    registry.build_l0_summary("你好")
    registry.discover("Issue")
    assert adapter.close.await_count == 0
    rows = await registry.describe(["mcp-server:issues"], query="search issue")
    assert len(rows) == 1
    assert rows[0]["id"].startswith("mcp:issues:")
    await registry.close()
    adapter.close.assert_awaited_once()
```

- [ ] **Step 4: Run new tests and verify RED**

Run: `cd backend && python3 -m pytest tests/agent/test_capability_catalog.py -q`

Expected: FAIL because `describe`, `invoke`, `close`, and meta tools are not implemented.

- [ ] **Step 5: Implement L2/L3 and three fixed meta tools**

```python
def create_progressive_tools(registry: CapabilityRegistry) -> list[AgentTool]:
    return [
        AgentTool(name="capability_discover", description="L1：按需发现候选能力，不返回完整 schema 或正文。", parameters=DISCOVER_SCHEMA, execute=discover),
        AgentTool(name="capability_describe", description="L2：只读取已选 capability 的输入契约。", parameters=DESCRIBE_SCHEMA, execute=describe),
        AgentTool(name="capability_invoke", description="L3：执行已选 capability。", parameters=INVOKE_SCHEMA, execute=invoke),
    ]
```

Implementation requirements:

- `wiki:search` and `wiki:read_page` only register when `use_wiki=True`.
- `invoke` rechecks `use_wiki` before any Wiki I/O.
- Wiki `limit` is clamped to `1..20`; sources dedupe by `id`.
- `describe(mcp-server:<sid>)` calls existing `discover_all_tools` with one server, records adapters, filters by query, and returns only selected tool schemas.
- `invoke(mcp:<sid>:<tool>)` lazily discovers the server if needed.
- `close()` attempts to close every adapter even if one close fails.
- Meta-tool failures return `_error_result(call_id, message)` rather than raising into the loop.

- [ ] **Step 6: Run capability tests**

Run: `cd backend && python3 -m pytest tests/agent/test_capability_catalog.py -q`

Expected: all PASS.

- [ ] **Step 7: Checkpoint**

Run: `git diff --check -- backend/app/agent/capability_catalog.py backend/tests/agent/test_capability_catalog.py`

Expected: no whitespace errors.

### Task 4: Build the Free-Chat Registry

**Files:**
- Modify: `backend/app/agent/capability_catalog.py`
- Modify: `backend/tests/agent/test_capability_catalog.py`

**Interfaces:**
- Consumes: `create_builtin_tools`, `create_memory_tools`, `create_workspace_tools`, `load_skills`, `list_enabled_mcp_servers`.
- Produces: `build_free_chat_registry(conversation_id, linked_task_id, use_wiki, long_task_manager, source_sink) -> CapabilityRegistry`.

- [ ] **Step 1: Write failing namespace and fixed-tool-count tests**

```python
def test_builder_namespaces_tools_and_does_not_flatten_skills(fake_skill):
    registry = build_free_chat_registry(
        conversation_id="cid-1",
        linked_task_id="task-1",
        use_wiki=True,
        long_task_manager=None,
        source_sink=[],
    )
    assert "skill:compile_source" in registry.capability_ids
    assert "memory:update_user_profile" in registry.capability_ids
    assert "workspace:workspace_read" in registry.capability_ids
    assert [tool.name for tool in create_progressive_tools(registry)] == [
        "capability_discover", "capability_describe", "capability_invoke"
    ]
```

- [ ] **Step 2: Implement builder with origin namespaces**

```python
def build_free_chat_registry(
    *,
    conversation_id,
    linked_task_id,
    use_wiki,
    long_task_manager,
    source_sink,
    wiki_dir=None,
    mcp_servers=None,
):
    registry = CapabilityRegistry(
        use_wiki=use_wiki,
        wiki_dir=wiki_dir or note_output_dir() / "wiki",
        source_sink=source_sink,
        linked_task_id=linked_task_id,
        mcp_servers=mcp_servers,
    )
    for tool in create_builtin_tools(linked_task_id):
        if tool.name != "search_knowledge":
            registry.register_tool(f"builtin:{tool.name}", "builtin", tool)
    for tool in create_memory_tools():
        registry.register_tool(f"memory:{tool.name}", "memory", tool)
    if conversation_id:
        for tool in create_workspace_tools(conversation_id):
            registry.register_tool(f"workspace:{tool.name}", "workspace", tool)
    for tool in load_skills(long_task_manager=long_task_manager):
        registry.register_tool(f"skill:{tool.name}", "skill", tool)
    return registry
```

- [ ] **Step 3: Run builder tests**

Run: `cd backend && python3 -m pytest tests/agent/test_capability_catalog.py -q`

Expected: PASS.

- [ ] **Step 4: Checkpoint**

Run: `git diff --check -- backend/app/agent/capability_catalog.py backend/tests/agent/test_capability_catalog.py`

### Task 5: Disable Agent Wiki Prefetch and Integrate Registry

**Files:**
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/app/agent/chat_adapter.py`
- Modify: `backend/app/agent/agent_service.py`
- Modify: `backend/tests/agent/test_agent_service_p3_integration.py`
- Modify: `backend/tests/agent/test_chat_compat.py`

**Interfaces:**
- Consumes: `build_free_chat_registry`, `create_progressive_tools`.
- Changes: `_prepare_free_chat_context(question, linked_task_id, use_wiki, *, prefetch_wiki=True) -> QueryContext`.
- Preserves: `run_free_chat*` public signatures and `/api/chat/free*` contract.

- [ ] **Step 1: Write failing no-prefetch test**

```python
def test_agent_free_chat_hook_disables_wiki_prefetch():
    with patch("app.services.chat_service.WikiSearch") as search_cls:
        hooks = build_free_chat_hooks("你好", None, True, None, None)
    search_cls.assert_not_called()
    assert "Wiki" not in hooks.system_prompt or "正文" not in hooks.system_prompt
```

- [ ] **Step 2: Write failing fixed-meta-tools and close tests**

```python
def test_run_free_chat_registers_only_progressive_meta_tools():
    captured = []
    registry = MagicMock()
    registry.build_l0_summary.return_value = "[能力地图 L0]"
    registry.close = AsyncMock()
    meta_tools = [build_agent_tool(name) for name in (
        "capability_discover", "capability_describe", "capability_invoke"
    )]

    def capture_agent(initial_state, **kwargs):
        captured.extend(initial_state.tools)
        return Agent(initial_state=initial_state, **kwargs)

    with patch("app.agent.agent_service.build_free_chat_registry", return_value=registry), \
         patch("app.agent.agent_service.create_progressive_tools", return_value=meta_tools), \
         patch("app.agent.agent_service.Agent", side_effect=capture_agent):
        self._run(run_free_chat("hi", [], "prov", "model"))

    self.assertEqual([tool.name for tool in captured], [
        "capability_discover", "capability_describe", "capability_invoke"
    ])

def test_run_free_chat_closes_registry_on_model_error():
    registry = MagicMock()
    registry.build_l0_summary.return_value = "[能力地图 L0]"
    registry.close = AsyncMock()
    models = FakeModels(turns=[RuntimeError("model failed")])
    with patch("app.agent.agent_service._resolve_model", return_value=(models, FakeModel())), \
         patch("app.agent.agent_service.build_free_chat_registry", return_value=registry), \
         patch("app.agent.agent_service.create_progressive_tools", return_value=[]):
        with self.assertRaises(RuntimeError):
            self._run(run_free_chat("hi", [], "prov", "model"))
    registry.close.assert_awaited_once()
```

- [ ] **Step 3: Run integration tests and verify RED**

Run: `cd backend && python3 -m pytest tests/agent/test_agent_service_p3_integration.py tests/agent/test_chat_compat.py -q`

Expected: FAIL because free-chat still prefetches and directly registers tools.

- [ ] **Step 4: Add kw-only prefetch guard while preserving legacy default**

```python
def _prepare_free_chat_context(question, linked_task_id, use_wiki, *, prefetch_wiki=True):
    intent = classify_query_intent(question)
    note_chunks = []
    if linked_task_id and intent.scope in ("current_note", "mixed"):
        try:
            note_chunks = VectorStoreManager().query(
                linked_task_id,
                question,
                n_results=6,
                quotas=build_vector_quotas(intent),
            )
        except Exception as exc:
            logger.warning("关联笔记检索失败，降级为 Wiki/普通聊天: %s", exc)
    wiki_sources = []
    if use_wiki and prefetch_wiki and intent.scope in (
        "global_wiki", "mixed", "current_note"
    ):
        wiki_sources = WikiSearch(note_output_dir() / "wiki").search(
            question,
            limit=8,
            intent=intent,
            linked_task_id=linked_task_id,
        )
    return build_query_context(question, intent, note_chunks, wiki_sources)
```

`build_free_chat_hooks` must call it with `prefetch_wiki=False`; legacy `free_chat*` calls remain unchanged and therefore use `True`.

- [ ] **Step 5: Integrate registry into non-stream and stream paths**

```python
registry = build_free_chat_registry(
    conversation_id=conversation_id,
    linked_task_id=linked_task_id,
    use_wiki=use_wiki,
    long_task_manager=long_task_manager,
    source_sink=hooks.sources,
)
hooks.system_prompt = registry.build_l0_summary(question) + "\n\n" + hooks.system_prompt
tools = create_progressive_tools(registry)

agent = Agent(
    initial_state=AgentState(model=model, tools=tools, messages=messages),
    max_turns=_FREE_CHAT_MAX_TURNS,
    tool_execution="parallel",
    models=models,
    transform_context=hooks.transform_context,
    convert_to_llm=hooks.convert_to_llm,
    usage_context={"phase": "free_chat", "task_id": linked_task_id},
)
try:
    await agent.prompt(question)
    await agent.wait_for_idle()
    if agent.error is not None:
        raise RuntimeError(agent.error.message or "agent error")
    return {"answer": _extract_last_assistant_text(agent.messages), "sources": hooks.sources}
finally:
    await registry.close()
```

流式路径使用同一个 registry：

```python
try:
    async for event in agent_events_to_sse_dict(
        agent, question, hooks.sources, long_task_manager=long_task_manager
    ):
        yield event
finally:
    await registry.close()
```

The stream `finally` must execute on normal completion, model error, client disconnect, and cancellation.

- [ ] **Step 6: Run Agent integration and compatibility tests**

Run: `cd backend && python3 -m pytest tests/agent/test_agent_service_p3_integration.py tests/agent/test_chat_compat.py tests/ai/test_chat_service_migration.py -q`

Expected: PASS.

- [ ] **Step 7: Checkpoint**

Run: `git diff --check -- backend/app/services/chat_service.py backend/app/agent/chat_adapter.py backend/app/agent/agent_service.py backend/tests/agent/test_agent_service_p3_integration.py backend/tests/agent/test_chat_compat.py`

### Task 6: Security, Routing Decisions, and Performance Regression Tests

**Files:**
- Modify: `backend/tests/agent/test_capability_catalog.py`
- Modify: `backend/tests/agent/test_mcp_client.py` only if an existing helper needs a lifecycle assertion.

**Interfaces:**
- Verifies requirement acceptance 1–11.

- [ ] **Step 1: Add parameterized routing scenarios**

```python
@pytest.mark.parametrize("question,expects_hint", [
    ("你好", False),
    ("帮我润色这句话", False),
    ("我的知识库里 RAG 是什么", True),
    ("请给出 Agent 的来源证据", True),
])
def test_l0_routing_hints(question, expects_hint, graph_registry):
    summary = graph_registry.build_l0_summary(question)
    assert ("本轮候选：" in summary) is expects_hint
```

- [ ] **Step 2: Add Wiki-off and sensitive-config tests**

```python
def test_use_wiki_false_registers_no_wiki_capability(self):
    registry = CapabilityRegistry(use_wiki=False, wiki_dir=None, source_sink=[])
    self.assertFalse(any(cid.startswith("wiki:") for cid in registry.capability_ids))

def test_l0_and_l1_never_expose_mcp_auth_url_env(self):
    registry = CapabilityRegistry(
        use_wiki=False,
        wiki_dir=None,
        source_sink=[],
        mcp_servers={"private": {
            "name": "Private MCP",
            "enabled": True,
            "url": "https://private.example/mcp",
            "auth": {"token": "secret"},
            "env": {"API_KEY": "secret"},
        }},
    )
    rendered = registry.build_l0_summary("MCP") + json.dumps(
        registry.discover("MCP"), ensure_ascii=False
    )
    assert "secret" not in rendered
    assert "https://private.example" not in rendered
```

- [ ] **Step 3: Add bounded-output and cache tests**

```python
def test_l0_is_bounded_for_10000_nodes(self):
    nodes = [
        {"id": f"concept:{i}", "label": f"topic-{i}", "type": "concept", "size": 1}
        for i in range(10000)
    ]
    registry = self._registry_with_graph({"nodes": nodes, "communities": {}})
    self.assertLessEqual(len(registry.build_l0_summary("topic-9999")), 1200)

def test_graph_snapshot_cache_reuses_same_mtime(self):
    registry = self._registry_with_graph({"nodes": [], "communities": {}})
    graph_path = registry.wiki_dir / "graph.json"
    original = Path.read_text
    with patch.object(Path, "read_text", autospec=True, side_effect=original) as read_text:
        registry.build_l0_summary("first")
        registry.build_l0_summary("second")
    graph_reads = [call for call in read_text.call_args_list if call.args[0] == graph_path]
    self.assertEqual(len(graph_reads), 1)
```

- [ ] **Step 4: Run focused security/performance contracts**

Run: `cd backend && python3 -m pytest tests/agent/test_capability_catalog.py tests/agent/test_mcp_client.py tests/test_core_mcp_generation_tools.py -q`

Expected: PASS.

### Task 7: System Documentation and Verification Evidence

**Files:**
- Modify: `docs/system/current-architecture.md`
- Modify: `docs/system/product-rules.md`
- Modify: `docs/system/api-inventory.md`
- Modify: `docs/system/known-pitfalls.md`
- Modify: `docs/requirements/2026-08-11-progressive-capability-routing.md`
- Modify: `docs/requirements/index.md`
- Create: `docs/superpowers/tests/2026-08-11-progressive-capability-routing.md`

**Interfaces:**
- Produces persistent system facts and doc-driven verification evidence.

- [ ] **Step 1: Write back system facts**

Document exactly:

- Agent free-chat no longer prefetches Wiki when flag=true.
- L0 is graph/config metadata only; L1/L2/L3 are discover/describe/invoke.
- only three meta-tool schemas are sent initially.
- MCP discovery is lazy and adapters close per request.
- legacy flag=false behavior remains.
- `use_wiki=false` is a hard registration + execution boundary.

- [ ] **Step 2: Run backend targeted suite**

Run:

```bash
python3 -m compileall backend/app
cd backend && python3 -m pytest tests/agent tests/agent_core tests/ai/test_chat_service_migration.py tests/test_core_mcp_generation_tools.py -q
```

Expected: all selected tests PASS.

- [ ] **Step 3: Run frontend contracts and build**

Run:

```bash
cd frontend && pnpm test:contracts
cd frontend && pnpm build
```

Expected: both commands exit 0.

- [ ] **Step 4: Run core regression if time and environment permit**

Run: `scripts/run_core_regression.sh`

Expected: exit 0. If an unrelated pre-existing failure occurs, record the exact command and failure in the test evidence without claiming full pass.

- [ ] **Step 5: Record metrics and status**

Write `docs/superpowers/tests/2026-08-11-progressive-capability-routing.md` with:

- backlink to the canonical requirement;
- exact commands and pass/fail counts;
- L0 length and cold/warm elapsed time;
- proof that ordinary Agent chat executes zero `WikiSearch.search` calls;
- any uncovered risk.

Then set requirement/index status to `Implemented` only if all mandatory tests pass; otherwise retain `Planned` and record the blocker.

- [ ] **Step 6: Final self-review**

Run:

```bash
git diff --check
git status --short
git diff -- backend/app/agent/capability_catalog.py backend/app/agent/agent_service.py backend/app/agent/chat_adapter.py backend/app/services/chat_service.py backend/tests/agent docs/requirements docs/superpowers docs/system
```

Expected: no whitespace errors; every changed line maps to this requirement; unrelated user changes remain untouched.
