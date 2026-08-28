# P2-P3 notemeld-agent：Plan + Spec（合并）

日期：2026-08-01
作者 / Agent：doc-driven 流程
关联需求：[`docs/requirements/2026-08-01-notemeld-agent-research-assistant.md`](../../requirements/2026-08-01-notemeld-agent-research-assistant.md)
前置依赖：[P0 notemeld-ai](2026-08-01-notemeld-ai-llm-abstraction.md) ✅ + [P1 notemeld-agent-core](2026-08-01-notemeld-agent-core-runtime.md) ✅
状态：Confirmed（待用户最终确认后开始执行）

---

## 总览：P2/P3 两期交付

需求 §9 已明确建议拆分。本 Spec 按两期组织：

| 期 | 目标 | 交付物 | 验收重心 |
| --- | --- | --- | --- |
| **P2** | Agent 接管现有 Chat + 内建工具 + SSE 兼容 | `backend/app/agent/` 业务层（不含 core）；chat 三接口内部 redirect 到 Agent；内建工具 7 个 | §验收 1（API 逐字节兼容） |
| **P3** | 长任务 Skill + 工作空间 + 三层记忆 + MCP 适配器 | Skill Loader + 长任务卡片 + workspace + memory + MCP client | §验收 3/4/5/6 |

P2 先交付用户尝鲜（旧前端不改可用），P3 再叠加增强能力。

---

## Part A：Plan（任务拆分 + 依赖顺序 + 风险）

### A.1 P2 任务拆分

| # | 任务 | 依赖 | 验收映射 | 风险 |
| --- | --- | --- | --- | --- |
| P2-T1 | 创建 `backend/app/agent/` 骨架 + `__init__.py`（不含 core） | P1 完成 | - | 低 |
| P2-T2 | 实现 `agent/builtin_tools.py`：7 个内建工具转 AgentTool | P1 core 的 AgentTool | §验收 1 工具可用 | 低 |
| P2-T3 | 实现 `agent/chat_adapter.py`：把旧 chat_service 的上下文构建（RAG/wiki/asset）封装为 Agent hooks | P1 hooks + P0 models | §验收 1 上下文等价 | 中 |
| P2-T4 | 实现 `agent/sse_bridge.py`：Agent 10 类事件 → 旧 SSE delta/done/error 格式映射 | P1 events | §验收 1 SSE 逐字节兼容 | **高** |
| P2-T5 | 实现 `agent/agent_service.py`：统一入口 `run_chat()` / `run_free_chat()` / `run_free_chat_stream()`，内部创建 Agent + 注册工具 + 设置 hooks + 跑 agent_loop | P2-T2 T3 T4 | §验收 1 | 中 |
| P2-T6 | 修改 `chat_service.py`：三个函数内部 redirect 到 agent_service，保留签名和返回结构 | P2-T5 | §验收 1 | **高**（改现有代码） |
| P2-T7 | 单测：`tests/agent/test_sse_bridge.py` + `test_chat_compat.py`（旧 SSE 格式断言） | P2-T4 T6 | §验收 1 | 中 |
| P2-T8 | 回归：`test_core_mcp_generation_tools.py` + `test_core_task_status_contracts.py` + `pnpm test:contracts` | P2-T6 | §13.5 | 低 |
| P2-T9 | 验收报告 | P2-T8 | - | - |

### A.2 P3 任务拆分

| # | 任务 | 依赖 | 验收映射 | 风险 |
| --- | --- | --- | --- | --- |
| P3-T1 | 实现 `agent/workspace.py`：工作空间目录管理 + 路径穿越校验 + 内建工具 workspace_list/read/write | P2 完成 | §验收 5 | 中 |
| P3-T2 | 实现 `agent/memory.py`：三层记忆（user_profile.json + research_spaces/*.json）+ 注入 hook + 内建工具 update_user_profile/manage_research_space | P2 完成 | §验收 2 | 中 |
| P3-T3 | 实现 `agent/skill_loader.py`：读 SKILL.md 注册 AgentTool + Parameter Collector 机制 | P2 完成 | §验收 2 | **高** |
| P3-T4 | 实现 `agent/long_task.py`：长任务卡片（task_card 消息持久化 + SSE task_card/task_card_progress 事件 + 取消 + 自动 follow-up） | P3-T3 | §验收 3/4/6 | **高** |
| P3-T5 | 实现 `agent/mcp_client.py`：MCP 适配器（把第三方 MCP server tools 转 AgentTool） | P2 完成 | §用户故事 3 | 中 |
| P3-T6 | 前端：workspace 只读接口 `/api/conversations/{cid}/workspace/*` + Settings MCP 配置 UI | P3-T1 T5 | §验收 5 | 中 |
| P3-T7 | 单测 + 回归 + 验收报告 | P3-T1~T6 | 全量 | - |

### A.3 依赖图

```
P1 完成 ──┬─ P2-T1 ── P2-T2 ──┐
          │                    ├─ P2-T3 ──┐
          │                    │           │
          └────────────────────┴─ P2-T4 ──┤
                                           ├─ P2-T5 ── P2-T6 ──┬─ P2-T7 ── P2-T8 ── P2-T9
                                           │                   │
                                           └───────────────────┘

P2 完成 ──┬─ P3-T1 ──┐
          ├─ P3-T2 ──┤
          ├─ P3-T3 ──┼─ P3-T4 ──┐
          └─ P3-T5 ──┘          ├─ P3-T6 ── P3-T7
                                │
                                └──────────┘
```

### A.4 风险与回滚

| 风险 | 触发信号 | 降级 / 回滚 |
| --- | --- | --- |
| SSE 格式不兼容 | test_sse_bridge 或 pnpm test:contracts 失败 | sse_bridge 做严格映射；失败时 chat_service 回退旧实现（feature flag） |
| 工具行为不等价 | test_chat_compat 失败 | 逐工具比对旧 execute_tool 输出 |
| 工作空间路径穿越 | test_workspace 安全用例失败 | 参考 MCP get_note 安全实现；强制 resolve + prefix 检查 |
| 长任务卡片刷新丢状态 | test_long_task 持久化失败 | 卡片状态必须写 conversation_messages（known-pitfall） |
| MCP client 安全风险 | 第三方 server 执行恶意命令 | Settings 默认关闭；用户手动 opt-in + 明确提示 |
| 记忆 JSON 损坏 | 加载时 crash | 容错：空默认 + 日志 + 备份损坏文件 |

**回滚策略**：
- P2：chat_service.py 保留旧实现为 `_legacy_chat()` / `_legacy_free_chat()` 等，通过 feature flag `AGENT_CHAT_ENABLED=true/false` 切换。回滚 = 关 flag。
- P3：全部为新增文件 + 新增接口；回滚 = 删除新增文件 + 关闭新接口。

---

## Part B：Spec（按 change-spec-template）

### B.0 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已搜索 `chat_service.py` / `chat_tools.py` / `routers/chat.py` 现有实现
- [x] 已搜索 `conversation_store.py` / `mcp/service.py` 现有实现
- [x] 已确认 P0 + P1 已验收通过
- [x] 已确认不影响线上服务（本地优先，无外部 API 改动）

### B.1 当前系统现状

- **chat_service.py**（`backend/app/services/chat_service.py`）：
  - `chat(task_id, question, history, provider_id, model_name)` — RAG + Tool Calling，3 轮 tool loop，使用 `TOOLS` + `execute_tool`
  - `free_chat(...)` — 非流式，history[-20:]，构建 note_context + asset_context + wiki_context → `models.complete()`
  - `free_chat_stream(...)` — 流式，yield `{"type":"delta","content":...}` / `{"type":"done",...}` / `{"type":"error",...}`
  - 上下文构建：`_prepare_free_chat_context()` 做 vector + wiki 检索；`_resolve_asset_context()` 读会话资产
- **chat_tools.py**：3 个工具（`lookup_transcript` / `get_video_info` / `get_note_content`），同步 `execute_tool(task_id, tool_name, args)` 读 `note_results/{task_id}.json`
- **chat router**（`backend/app/routers/chat.py`）：
  - `POST /api/chat/ask` → `chat_service.chat()` → `R.success(data=result)`
  - `POST /api/chat/free` → `free_chat_service()` → `R.success(data=result)`
  - `POST /api/chat/free/stream` → `free_chat_stream_service()` → SSE `data: {json}\n\n`
  - 请求体：`FreeAskRequest(question, history, provider_id, model_name, conversation_id, linked_task_id, use_wiki, asset_content)`
- **conversation_store.py**：管理 `conversation_messages` 表的 CRUD
- **mcp/service.py**：MCP server（`/mcp` endpoint），当前 8 个 tools（generate_note/get_task/get_note/list_models/notemeld_import_note/notemeld_search_notes/notemeld_read_note/notemeld_search_wiki/notemeld_read_wiki_page）
- **P0 notemeld-ai**：`create_models()` → `models.complete()` / `models.stream()`，统一 usage 写入
- **P1 agent-core**：`Agent` / `agent_loop` / 10 类事件 / 并行串行工具 / abort/steer / hooks
- **数据表**：`conversations(id, mode, title, status, linked_note_task_id, ...)` / `conversation_messages(id, conversation_id, role, message_type, content, status, meta_json, sources_json, ...)`
- **当前限制**：
  - 无 Agent 运行时（手写 for + append）
  - 无工作空间（note_results 按 task_id 不是 conversation_id）
  - 无跨会话记忆（history[-20:] 暴力截取）
  - 无 Skill 注册机制
  - 无 MCP client（只能被外部调，不能调外部）

### B.2 本次目标

#### P2 目标

- **接管 Chat**：`chat_service.py` 三函数内部 redirect 到 `agent_service`；Agent 使用 P1 core 的 `agent_loop` 替代手写 for 循环
- **SSE 兼容**：Agent 的 10 类事件通过 `sse_bridge` 映射为旧 `delta/done/error` 格式，旧前端不改可用
- **内建工具**：7 个 AgentTool——`lookup_transcript` / `get_video_info` / `get_note_content`（迁移自 chat_tools）+ `search_knowledge`（Wiki + 笔记向量检索）+ `read_note` / `read_transcript` / `get_compile_status`
- **上下文等价**：旧 `_prepare_free_chat_context` / `_resolve_asset_context` 逻辑封装为 Agent 的 `transform_context` hook

#### P3 目标

- **工作空间**：`<data_dir>/note_results/workspaces/{cid}/`（子目录 assets/skills/canvases/memory/scratch）+ workspace_list/read/write 工具 + 前端只读接口
- **三层记忆**：`user_profile.json` + `research_spaces/{rs_id}.json` + 会话记忆（复用 conversation_messages）+ `transform_context` 注入
- **Skill 强化**：Skill Loader 读 SKILL.md → AgentTool；Parameter Collector（parameter_request SSE + parameter_response）；长任务卡片（task_card/task_card_progress SSE + conversation_messages 持久化 + 取消 + 自动 follow-up）
- **MCP 适配器**：第三方 MCP server tools → AgentTool 注册

### B.3 明确不做

- 不做：知识看板、画布、build_knowledge_canvas（P4）
- 不做：Web 搜索工具 search_web（P4）
- 不做：前端画布渲染组件（P4）
- 不做：前端聊天消息组件完全重写（增强现有，兼容旧消息映射）
- 不做：独立 pip 发布
- 不做：移动端 / 多租户
- 不做：桌面端新增 Node.js sidecar

### B.4 冲突分析

| 检查项 | 结论 |
| --- | --- |
| product-rules.md 冲突 | ✅ 无。本地优先、API Key 不回显、路径穿越校验、response wrapper 不变、长任务可恢复 |
| data-model.md 字段语义冲突 | ✅ 无。新增 `conversation_messages.message_type` 枚举值（task_card/task_card_progress/parameter_request/parameter_response），不改现有字段语义。`research_space_id` 先存 `conversations.meta_json`，不新增表列 |
| api-inventory.md 接口契约冲突 | ✅ chat 三接口 request/response 100% 不变。新增 `/api/conversations/{cid}/workspace/*` 只读接口需同步更新 api-inventory |
| known-pitfalls.md 重新引入 | ✅ 已覆盖：任务状态与会话消息不同步（卡片写 conversation_messages）；MCP 路径穿越（workspace 接口校验）；API wrapper（新接口用 R.success）；notemeld-ai 迁移不删 GPTFactory |
| 桌面/源码/CLI/MCP 运行模式 | ✅ 不影响。`run_notemeld.sh` / CLI / 桌面 sidecar / `/mcp` endpoint 全部不变 |
| 打包/迁移/导入/回滚 | ✅ 不影响。P2 改 chat_service 内部实现但保留旧路径 + feature flag；P3 全新增 |

### B.5 影响范围

#### P2 影响范围

- **后端文件**：
  - 新增：`backend/app/agent/__init__.py` / `builtin_tools.py` / `chat_adapter.py` / `sse_bridge.py` / `agent_service.py`
  - 修改：`backend/app/services/chat_service.py`（三函数内部 redirect，保留签名 + 旧实现备份）
- **前端文件**：0 改动（P2 承诺旧前端不改可用）
- **数据库**：0 表 0 字段 0 迁移
- **文件系统**：0 新增
- **API**：0 改动（三接口 request/response 结构不变）
- **测试**：新增 `backend/tests/agent/test_sse_bridge.py` / `test_chat_compat.py`；现有 `test_chat_*.py` 应 0 影响
- **文档**：更新 `api-inventory.md`（标注 chat 内部实现已迁移到 Agent）

#### P3 影响范围

- **后端文件**：
  - 新增：`backend/app/agent/workspace.py` / `memory.py` / `skill_loader.py` / `long_task.py` / `mcp_client.py`
  - 修改：`backend/app/routers/conversation.py`（新增 workspace 只读接口路由）
- **前端文件**：
  - 修改：`frontend/src/` 新增 workspace 只读组件 + Settings MCP 配置 UI + 长任务卡片渲染
- **数据库**：0 表 0 字段（research_space_id 存 meta_json）
- **文件系统**：
  - 新增：`<data_dir>/note_results/workspaces/{cid}/`（懒创建）
  - 新增：`<data_dir>/note_results/memory/user_profile.json`
  - 新增：`<data_dir>/note_results/memory/research_spaces/{rs_id}.json`
- **API**：
  - 新增：`GET /api/conversations/{cid}/workspace/list` / `read`（只读 + 路径穿越校验）
  - 新增：`POST /api/conversations/{cid}/workspace/cancel_task`（取消长任务）
  - chat SSE 新增事件类型：`task_card` / `task_card_progress` / `parameter_request`（旧前端不认识即忽略）
- **测试**：新增 `test_workspace.py` / `test_memory.py` / `test_skill_loader.py` / `test_long_task.py` / `test_mcp_client.py`
- **文档**：更新 `api-inventory.md` + `data-model.md`（workspace + memory 文件结构）+ `known-pitfalls.md`（长任务卡片持久化防线）

### B.6 实施方案

#### P2 后端

**P2-T2 内建工具**（`agent/builtin_tools.py`）：

```python
# 把 chat_tools.py 的 3 个工具迁移为 AgentTool + 新增 4 个
def create_builtin_tools(task_id: str | None = None) -> list[AgentTool]:
    tools = []
    # 迁移自 chat_tools（保留 execute 逻辑，改为 async）
    tools.append(build_agent_tool(
        name="lookup_transcript",
        parameters={...},  # 同现有
        execute=_make_lookup_transcript_executor(task_id),
    ))
    tools.append(build_agent_tool(name="get_video_info", ...))
    tools.append(build_agent_tool(name="get_note_content", ...))
    # 新增
    tools.append(build_agent_tool(name="search_knowledge", execute=_search_knowledge))
    tools.append(build_agent_tool(name="read_note", execute=_read_note))
    tools.append(build_agent_tool(name="read_transcript", execute=_read_transcript))
    tools.append(build_agent_tool(name="get_compile_status", execute=_get_compile_status))
    return tools
```

**P2-T3 上下文适配**（`agent/chat_adapter.py`）：

```python
class ChatContextHooks:
    """把旧 chat_service 的上下文构建封装为 Agent hooks。"""
    
    def __init__(self, question, linked_task_id, use_wiki, conversation_id, asset_content):
        self._query_context = _prepare_free_chat_context(question, linked_task_id, use_wiki)
        self._asset_context = _resolve_asset_context(conversation_id, asset_content)
    
    def transform_context(self, messages, signal):
        """注入 system prompt（含 RAG/wiki/asset 上下文）。"""
        system = FREE_CHAT_SYSTEM_PROMPT.format(
            note_context=self._query_context.context_text,
            asset_context=self._asset_context,
            wiki_context="已合并到上方检索上下文中。",
        )
        return [AgentMessage(role="system", content=system)] + list(messages)
    
    def convert_to_llm(self, messages):
        """复用 P1 core 默认 convert + 追加 system 前缀。"""
        return _default_convert_to_llm(messages)
```

**P2-T4 SSE Bridge**（`agent/sse_bridge.py`）：

```python
async def agent_events_to_sse(agent: Agent) -> AsyncIterator[str]:
    """订阅 Agent 事件，yield 旧 SSE 格式字符串。
    
    映射：
    - MessageUpdateEvent(delta) → {"type":"delta","content":delta}
    - AgentEndEvent(error=None) → {"type":"done","answer":full_answer,"sources":...}
    - AgentEndEvent(error=...) → {"type":"error","message":...}
    - 其他事件 → 忽略（旧前端不处理）
    """
    full_answer = ""
    sources = []
    
    async def listener(evt):
        nonlocal full_answer
        if evt.type == AgentEventType.MESSAGE_UPDATE:
            full_answer += evt.delta
        # ...
    
    agent.subscribe(listener)
    # ...
```

**P2-T5 Agent Service**（`agent/agent_service.py`）：

```python
async def run_free_chat_stream(question, history, provider_id, model_name,
                                conversation_id, linked_task_id, use_wiki, asset_content):
    """替代 free_chat_stream，内部创建 Agent。"""
    models = create_models()
    model = models.get_model(provider_id, model_name)
    hooks = ChatContextHooks(question, linked_task_id, use_wiki, conversation_id, asset_content)
    tools = create_builtin_tools(linked_task_id)
    
    # 把旧 history 转为 AgentMessage
    messages = [UserMessage(content=m["content"]) if m["role"]=="user" else AssistantMessage(content=m["content"])
                for m in history[-20:]]
    
    agent = Agent(
        initial_state=AgentState(model=model, tools=tools, messages=messages),
        max_turns=10,
        tool_execution="parallel",
        models=models,
        transform_context=hooks.transform_context,
        convert_to_llm=hooks.convert_to_llm,
        usage_context={"phase": "free_chat_stream", "task_id": linked_task_id},
    )
    # 返回 SSE 生成器
    async for sse in agent_events_to_sse(agent):
        yield sse
    await agent.prompt(question)
```

**P2-T6 chat_service redirect**：

```python
# chat_service.py
_AGENT_CHAT_ENABLED = True  # feature flag

async def free_chat_stream(...):
    if _AGENT_CHAT_ENABLED:
        from app.agent.agent_service import run_free_chat_stream
        async for event in run_free_chat_stream(...):
            yield event
        return
    # 旧实现（fallback）
    ... (保留)
```

#### P3 后端（关键设计）

**P3-T1 工作空间**（`agent/workspace.py`）：

```python
def workspace_root(cid: str) -> Path:
    root = note_output_dir() / "workspaces" / cid
    # 路径穿越校验
    resolved = root.resolve()
    expected_prefix = (note_output_dir() / "workspaces").resolve()
    if not str(resolved).startswith(str(expected_prefix)):
        raise PermissionError("path traversal detected")
    return root

# AgentTool: workspace_list / workspace_read / workspace_write
# 前端接口: GET /api/conversations/{cid}/workspace/list?path=scratch
#           GET /api/conversations/{cid}/workspace/read?path=scratch/a.json
```

**P3-T2 三层记忆**（`agent/memory.py`）：

```python
# 文件位置
# <data_dir>/note_results/memory/user_profile.json
# <data_dir>/note_results/memory/research_spaces/{rs_id}.json

class MemoryManager:
    def load_user_profile(self) -> dict: ...  # 容错：损坏→空默认+备份
    def load_research_space(self, rs_id: str) -> dict: ...
    def save_user_profile(self, data: dict): ...
    def save_research_space(self, rs_id: str, data: dict): ...
    
    def build_system_prefix(self, rs_id: str | None) -> str:
        """注入 system prompt 前缀：user_profile 摘要 + research_space 摘要。"""
        # masteries > 1000 时截断 Top-20
```

**P3-T3 Skill Loader**（`agent/skill_loader.py`）：

```python
def load_skills(skills_dir: Path) -> list[AgentTool]:
    """读 SKILL.md → AgentTool。
    
    SKILL.md 格式：
    ---
    name: compile_source
    description: 编译视频/网页为结构化笔记
    parameters:
      - key: url
        label: 视频链接
        widget: text_input
        required: true
    long_running: true
    ---
    脚本调用：python scripts/compile_source.py --url "$url"
    """
    ...
```

**P3-T4 长任务卡片**（`agent/long_task.py`）：

```python
# SSE 新事件类型
# {"type":"task_card","card_id":"card-1","kind":"compile_source","task_id":"task-abc","status":"PENDING","title":"视频编译中","progress":null}
# {"type":"task_card_progress","card_id":"card-1","status":"DOWNLOADING","progress":30,"details":"下载音频：1.2MB/5.8MB"}

class LongTaskManager:
    async def start_task(self, skill, params, conversation_id) -> str:
        """启动长任务，返回 card_id。"""
        # 1. 写 conversation_messages (message_type=task_card, status=PENDING)
        # 2. 发 SSE task_card 事件
        # 3. 后台执行 skill 脚本
        # 4. 进度更新 → 写 conversation_messages + 发 SSE task_card_progress
        # 5. 完成 → 更新卡片状态 + 自动 follow-up（如果设置开启）
    
    async def cancel_task(self, card_id: str):
        """取消长任务。复用现有 cancel_note_task 语义。"""
        # 1. 调 cancel_note_task
        # 2. 更新卡片状态 CANCELED
        # 3. 发 SSE task_card (status=CANCELED)
```

**P3-T5 MCP 适配器**（`agent/mcp_client.py`）：

```python
class MCPClientAdapter:
    """把第三方 MCP server 的 tools 转为 AgentTool。"""
    
    async def discover_tools(self, server_config: dict) -> list[AgentTool]:
        """连 MCP server，调 tools/list，转 AgentTool。"""
        # 支持 stdio / HTTP / SSE transport
        # 每个 tool 的 execute 调 tools/call
        # auth 单独存用户配置，不在日志打 headers
```

### B.7 数据变更

- **新增 SQLite 表**：无
- **修改字段**：无（`conversation_messages.message_type` 新增枚举值，不改 schema）
- **新增文件结构**：
  - `note_results/workspaces/{cid}/`（懒创建）
  - `note_results/memory/user_profile.json`
  - `note_results/memory/research_spaces/{rs_id}.json`
- **迁移**：无（旧数据不迁移；旧会话默认无 research_space）
- **回滚后数据**：工作空间和记忆 JSON 保留在磁盘，不影响系统运行

### B.8 接口变更

| 接口 | 变更类型 | 说明 |
| --- | --- | --- |
| `POST /api/chat/ask` | 内部实现替换 | request/response 100% 不变 |
| `POST /api/chat/free` | 内部实现替换 | request/response 100% 不变 |
| `POST /api/chat/free/stream` | 内部实现替换 + SSE 新增类型 | 旧 delta/done/error 不变；新增 task_card/task_card_progress/parameter_request（旧前端忽略） |
| `GET /api/conversations/{cid}/workspace/list` | **新增** | 只读，路径穿越校验 |
| `GET /api/conversations/{cid}/workspace/read` | **新增** | 只读，路径穿越校验 |
| `POST /api/conversations/{cid}/workspace/cancel_task` | **新增** | 取消长任务 |

需更新 `docs/system/api-inventory.md`。

### B.9 测试方案

#### P2 测试

- **test_sse_bridge.py**：Agent 事件 → SSE 格式映射断言（delta 累积 / done 含 answer+sources / error 格式）
- **test_chat_compat.py**：旧 `FreeAskRequest` 请求 → Agent 路径 → 响应结构与旧实现逐字段比对
- **回归**：`test_core_mcp_generation_tools.py` / `test_core_task_status_contracts.py` / `pnpm test:contracts` 全绿

#### P3 测试

- **test_workspace.py**：路径穿越 `../` / 绝对路径 → 403；正常读写；懒创建
- **test_memory.py**：JSON 损坏容错；masteries > 1000 截断；注入 system prompt
- **test_skill_loader.py**：SKILL.md 解析；Parameter Collector 流程
- **test_long_task.py**：卡片持久化 → 刷新恢复；取消 1s 内生效；follow-up 开关
- **test_mcp_client.py**：tools/list → AgentTool；tools/call 执行；超时降级

### B.10 验收标准

P2 验收：
- [ ] §1 旧前端不改，连 P2 后端，三接口响应 wrapper / 字段名 / SSE 事件逐字节一致
- [ ] 新增 SSE 类型旧前端不 crash
- [ ] `pnpm test:contracts` + `test_core_*.py` 全绿

P3 验收：
- [ ] §2 无 research_space 会话 → Agent 自动创建并询问确认
- [ ] §3 长任务卡片刷新页面状态不丢
- [ ] §4 取消 compile_source → 1s 内 CANCELED
- [ ] §5 工作空间路径穿越 → 403
- [ ] §6 follow-up 关闭后不产生新 assistant 消息

### B.11 风险和回滚

- **主要风险**：P2 SSE 格式不兼容导致前端 break
- **触发信号**：`pnpm test:contracts` 或 `test_sse_bridge` 失败
- **降级策略**：feature flag `AGENT_CHAT_ENABLED=false` 回退旧实现
- **回滚步骤**：P2 关 flag；P3 删新增文件 + 关新接口
- **回滚后数据一致性**：工作空间/记忆 JSON 留盘不影响系统

### B.12 Agent 必答问题

| 问题 | 回答 |
| --- | --- |
| 影响哪些已有模块？ | chat_service.py（内部 redirect）、chat_tools.py（迁移为 AgentTool）、routers/chat.py（不改）、routers/conversation.py（P3 新增 workspace 路由） |
| 是否已有类似能力？ | P1 agent-core 提供运行时；chat_tools 有 3 个工具；MCP service 有 server 端 |
| 是否和产品规则冲突？ | 否。本地优先、API Key 安全、路径穿越、response wrapper 全部遵守 |
| 是否和数据模型冲突？ | 否。新增 message_type 枚举值不改 schema；research_space_id 存 meta_json |
| 是否重新引入 known-pitfalls？ | 否。卡片写 conversation_messages；workspace 校验路径穿越；新接口用 R.success |
| 是否影响本地数据/线上服务？ | 新增 workspaces + memory 目录；DB 仅追加 conversation_messages；无破坏性变更 |
| 最小可行改动是什么？ | P2：chat_service 三函数 redirect + sse_bridge + 7 工具；P3：新增文件 + 新增接口 |
| 需要补哪些测试？ | sse_bridge / chat_compat / workspace / memory / skill_loader / long_task / mcp_client |
