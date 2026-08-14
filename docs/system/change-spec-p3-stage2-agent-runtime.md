# Change Spec: P3 阶段二 — Agent 运行时全量集成

更新时间：2026-08-02

依据 `docs/system/change-spec-template.md` 编写。基于当前系统事实，描述 P3 五模块（workspace / memory / skill_loader / mcp_client / long_task）注册到 agent_service 运行时的最小可行改动。

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`（P2 Agent 已落地，feature flag `AGENT_CHAT_ENABLED`）
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`（Conversation 表无 `meta_json` 字段；记忆文件在 `note_results/memory/`）
- [x] 已阅读 `docs/system/api-inventory.md`（`/api/chat/free/stream` SSE 由 `agent_events_to_sse_dict` 映射）
- [x] 已阅读 `docs/system/known-pitfalls.md`（任务状态/会话消息同步、API wrapper、Agent 变更流程）
- [x] 已搜索相关代码（agent_service / chat_adapter / sse_bridge / long_task / workspace / memory / skill_loader / mcp_client / chat_service / conversation_store / chat router / conversation router）
- [x] 已搜索相关测试（tests/agent/* 118 passed；test_chat_compat.py 覆盖 feature flag）
- [x] 已确认前端 SSE handler（frontend/src/services/chat.ts）已支持 `task_card`/`task_card_progress`/`parameter_request` 且未知 type 静默忽略
- [x] 已确认无线上服务影响（全部本地，feature flag 默认 false）

## 1. 当前系统现状

### 1.1 P3 五模块（阶段一已实现 + 单测 118 passed）

- `backend/app/agent/workspace.py`：`create_workspace_tools(cid) -> list[AgentTool]`（workspace_list/read/write，路径穿越校验，仅访问 `cid` 工作空间）。**未注册到任何 agent 入口**。
- `backend/app/agent/memory.py`：
  - `MemoryManager.build_system_prefix(rs_id=None) -> str`：拼装 user_profile + research_space 前缀。
  - `MemoryContextHook` / `build_memory_hook(rs_id)`：transform_context 注入 hook（**当前未被调用**）。
  - `create_memory_tools()`：update_user_profile / manage_research_space。**已注册到 `run_chat` L59**，但 **未注册到 `run_free_chat*`**。
  - docstring L18 声称"research_space_id 存 conversations.meta_json，由上层业务读写"——**此字段在 Conversation 表上不存在**（仅 `conversation_messages` 有 meta_json）。属 aspirational 错误。
- `backend/app/agent/skill_loader.py`：`load_skills(skills_dir=None, *, long_task_manager=None, parameter_collector=None)`，解析 SKILL.md → AgentTool，目录不存在返回 `[]`。**未注册到任何 agent 入口**。
- `backend/app/agent/mcp_client.py`：`async discover_all_tools(servers=None, *, adapters_out=None)`，异步并发 discover，失败返回 `[]`，需调用方 `close()` adapters。**未注册到任何 agent 入口**。
- `backend/app/agent/long_task.py`：`LongTaskManager(agent, auto_follow_up, dispatcher, default_timeout)`。`dispatcher` 是 `Callable[[dict], Optional[Awaitable]]`，发 `task_card`/`task_card_progress` 事件 dict。**无任何 dispatcher 注入，事件不发 SSE**。

### 1.2 agent_service.py 现状（237 行）

- `run_chat(task_id, question, history, provider_id, model_name)`：max_turns=3 + 兜底无 tools；`tools = create_builtin_tools(task_id) + create_memory_tools()`；**无 conversation_id 参数**。
- `run_free_chat(question, history, provider_id, model_name, conversation_id=None, linked_task_id=None, use_wiki=True, asset_content=None)`：max_turns=1，**tools=[]**，单轮。
- `run_free_chat_stream(...同参...) -> AsyncIterator[dict]`：max_turns=1，**tools=[]**，`yield agent_events_to_sse_dict(agent, question, hooks.sources)`。

### 1.3 chat_adapter.py 现状

- `_memory_prefix()`（L69）：仅注入 user_profile 全局，注释明确"research_space 注入需要 cid→rs_id 映射，由上层业务后续接入"。
- `build_chat_hooks(task_id, question)` / `build_free_chat_hooks(question, linked_task_id, use_wiki, conversation_id, asset_content)`：都调 `_memory_prefix()` 拼 system_prompt。

### 1.4 sse_bridge.py 现状（159 行）

- `agent_events_to_sse_dict(agent, question, sources)`：内部 `asyncio.Queue`，listener 订阅 Agent 事件，只映射 `MESSAGE_UPDATE→delta`、`AGENT_END→done/error`，其他忽略。**yield 循环在 `done`/`error` 后 break**。
- `long_task` 的 `task_card`/`task_card_progress` 事件**不走 Agent 事件系统**，而是 `LongTaskManager.dispatcher` 回调，当前无注入路径。

### 1.5 cid→rs_id 映射现状

- **不存在**。Conversation 表字段：id/mode/title/status/message/platform/linked_note_task_id/note_state/form_data_json/transcript_json/audio_meta_json/markdown_json/created_at/updated_at/deleted_at。无 research_space_id，无 meta_json。
- memory.py docstring 声称存 conversations.meta_json 属错误（该字段不存在）。

### 1.6 迁移框架现状

- 无 Alembic。`init_db.py` 用 `Base.metadata.create_all()` + 手动幂等 `ALTER TABLE ADD COLUMN`（见 `note_style_dao.ensure_note_style_columns()`，用 inspector 检查列是否存在）。

### 1.7 前端 SSE 现状（frontend/src/services/chat.ts）

- `streamFreeChat` 用 fetch + ReadableStream reader，`while(true)` 读 chunk → split `\n\n` → 解析 `data:` JSON。
- 已显式处理 `delta`/`done`/`error`/`task_card`/`task_card_progress`（L136-168）+ `parameter_request`（按 `kind` 区分，L126-134）。
- **未知 type 静默忽略**（L170 注释"其他未知 type 静默忽略，保证旧前端不 crash"）。
- reader 循环**不在 `done` 事件上 break**，只在 `reader.read()` 的 `done=true`（HTTP body 结束）时退出。→ 服务端可在 `done` 后继续发 `task_card_progress`，前端会继续渲染。

### 1.8 feature flag 现状

- `chat_service.py` L21：`_AGENT_CHAT_ENABLED = os.getenv("AGENT_CHAT_ENABLED","false")`。
- L186/244/319 三处 gate：chat / free_chat / free_chat_stream 路径切换到 agent_service。
- 默认 false（旧实现路径，测试 0 影响）；生产环境 `AGENT_CHAT_ENABLED=true` 启用 Agent 路径。
- `tests/test_chat_compat.py` 覆盖。

## 2. 本次目标

把 P3 五模块接入 agent_service 运行时，使 `AGENT_CHAT_ENABLED=true` 时 free_chat 成为完整 Agent（工具调用 + 长任务卡片 + 研究空间记忆）。

- 成功后的用户可见行为（flag=true）：
  - 在主聊天窗口（free_chat / free_chat_stream），Agent 可读写当前会话工作空间（workspace_list/read/write）。
  - Agent 可维护 user_profile / research_space 记忆（update_user_profile / manage_research_space）。
  - system prompt 自动注入 user_profile + 当前会话绑定的 research_space 记忆前缀。
  - 长 task skill 返回卡片，SSE 流持续推送 task_card / task_card_progress 直到任务结束。
  - skills 目录下的 SKILL.md 注册为 AgentTool。
- 成功后的系统内部行为：
  - `run_free_chat*` 注册 workspace + memory + skill 工具；max_turns 提升以支持工具循环。
  - cid→rs_id 映射落库（新增 `conversations.research_space_id` 列）。
  - `agent_events_to_sse_dict` 接受 long_task_manager，dispatcher 事件汇入同一 SSE 队列，且 `done` 不再立即关闭流（待长任务结束）。
- 必须保留的旧行为：
  - flag=false 时三函数行为逐字节不变（旧实现路径）。
  - flag=true 但 cid=None 时：不注册 workspace 工具，rs_id=None，仍可工作。
  - 旧 SSE `delta`/`done`/`error` 语义不变。

## 3. 明确不做

- **不做 mcp_client 注册**：mcp 涉及异步网络 + 子进程 + adapter 生命周期管理（需 close），风险高且 settings 默认关闭（无 enabled server 时返回 `[]`）。本次仅保留模块现状，不接入 agent_service。后续单独评估。
- 不做 `run_chat`（task-based RAG）的 P3 工具注册：它无 conversation_id，且语义是"基于笔记的 RAG 问答"，与 workspace/记忆研究助手范式不同。保留 create_builtin_tools + create_memory_tools。
- 不做前端改动：前端已支持 task_card/task_card_progress/parameter_request SSE 类型。本次只动后端。
- 不做 ParameterCollector 的 HTTP 端点：parameter_request 事件已能经 SSE 派发，但 `parameter_response` HTTP 接口和前端弹窗不在本次范围。必填参数缺失时 skill_loader 现有逻辑返回 error ToolResult（parameter_collector=None 时）。
- 不做 auto_follow_up：LongTaskManager.agent 需持有 Agent 实例且 follow_up 语义复杂，本次 `auto_follow_up=False`，agent=None。
- 不做新 API 路由：workspace 前端只读接口和 cancel_task 路由已存在（conversation router L182-233）。

## 4. 冲突分析

- **product-rules.md**：不冲突。P3 服务"AI 编译知识，人验证消费"范式——Agent 工具用于编译/检索/记忆，人通过卡片验证。
- **data-model.md**：需新增 `conversations.research_space_id` 列（见 §7）。属有据变更（memory.py docstring 已声明 rs_id 存 conversation，仅字段名纠正），用幂等 ALTER TABLE，历史行 NULL 兼容。
- **api-inventory.md**：`/api/chat/free/stream` 返回结构新增 `task_card`/`task_card_progress` SSE 类型——**前端已支持**，需同步更新 api-inventory 文档说明。
- **known-pitfalls.md**：
  - "任务状态和会话消息不同步"——long_task.py 已 `_persist_card` 写 conversation_messages，不冲突。
  - "API response wrapper 被破坏"——SSE 流式接口是 wrapper 例外，不冲突。
  - "Agent 变更流程缺失"——本 Spec 即为合规流程。
- 桌面/源码/CLI/MCP 任一运行模式：不破坏。feature flag 默认 false。
- 打包/迁移/导入/回滚：新增列用幂等迁移，不动既有数据；回滚只需 flag=false。

## 5. 影响范围

- 后端文件：
  - `backend/app/db/models/conversation.py`（新增 research_space_id 列）
  - `backend/app/db/init_db.py`（调用 ensure_conversation_columns）
  - `backend/app/services/conversation_store.py`（读写 research_space_id + 新增 helper）
  - `backend/app/agent/chat_adapter.py`（_memory_prefix 接受 rs_id；build_free_chat_hooks 查 rs_id）
  - `backend/app/agent/agent_service.py`（run_free_chat* 注册工具 + 提升 max_turns + 注入 long_task_manager）
  - `backend/app/agent/sse_bridge.py`（agent_events_to_sse_dict 接受 long_task_manager，dispatcher 汇入队列，done 不立即关闭）
- 前端文件：无（已支持）。
- 桌面/Tauri：无。
- 数据库：conversations 表加一列。
- 文件系统：无新结构（复用 note_results/memory/、workspaces/、skills/）。
- API 调用方：前端 streamFreeChat 已兼容。
- MCP 工具：无。
- 测试：新增 tests/agent/test_agent_service_p3_integration.py；扩展 test_chat_compat.py。
- 文档：更新 api-inventory.md（SSE 类型）、data-model.md（新列）。

## 6. 实施方案

### 6.1 后端

#### A. cid→rs_id 映射落库

1. `backend/app/db/models/conversation.py`：`Conversation` 新增 `research_space_id = Column(String, nullable=True)`。
2. 新增 `backend/app/db/conversation_schema.py`（或并入现有 dao）`ensure_conversation_columns()`：用 inspector 检查 `conversations` 表是否有 `research_space_id`，无则 `ALTER TABLE conversations ADD COLUMN research_space_id TEXT`。模仿 `ensure_note_style_columns()`。
3. `init_db.py`：在 `ensure_note_style_columns()` 后调 `ensure_conversation_columns()`。
4. `conversation_store.py`：
   - `_hydrate_conversation_payload` 读 `conversation.research_space_id`。
   - `upsert_conversation` 写 `research_space_id`（data.get("researchSpaceId")）。
   - 新增 `get_conversation_research_space_id(conversation_id) -> Optional[str]`：查 Conversation.research_space_id，容错返回 None。
5. 修正 `memory.py` docstring L18：改为"存 conversations.research_space_id"。

#### B. research_space 注入 system prompt

1. `chat_adapter._memory_prefix(rs_id=None)`：调 `MemoryManager().build_system_prefix(rs_id)`。
2. `build_free_chat_hooks`：若 conversation_id 非空，调 `get_conversation_research_space_id(conversation_id)` 取 rs_id，传给 `_memory_prefix(rs_id)`。容错：查询失败 → rs_id=None。
3. `build_chat_hooks`：无 cid，保持 `_memory_prefix()`（rs_id=None）。
- 说明：不使用 MemoryContextHook.transform_context 组合，直接在 system_prompt 拼前缀（最小改动，与现有 _memory_prefix 模式一致）。

#### C. workspace + memory + skill 工具注册到 run_free_chat*

1. `agent_service.run_free_chat` / `run_free_chat_stream`：
   - `tools = []` → `tools = create_memory_tools()`；若 conversation_id 非空，`tools = create_workspace_tools(conversation_id) + tools`。
   - skills：`skill_tools = load_skills(long_task_manager=...)`（流式场景传 long_task_manager；非流式场景 long_running skill 无意义，传 None → 长任务 skill 缺 manager 报错，可接受；或非流式不注册 long_running skill）。本次：非流式 `load_skills(long_task_manager=None)`，流式 `load_skills(long_task_manager=ltm)`。
   - `tools.extend(skill_tools)`。
   - **max_turns**：从 1 提升到 6（允许若干轮工具调用）。仅 flag=true 路径生效（旧路径 max_turns 不变）。
2. 错误处理：workspace/skill 工具内部已 try/except 返回 error ToolResult，不 crash agent loop。
3. 并发：workspace_read/list execution_mode=parallel；workspace_write/skill=serial。Agent tool_execution 保持 "parallel"。

#### D. long_task SSE 接入 sse_bridge

1. `agent_events_to_sse_dict(agent, question, sources, long_task_manager=None)`：
   - 若传入 long_task_manager：设 `long_task_manager.dispatcher = lambda evt: queue.put_nowait(evt)`（dispatcher 同步返回 None，事件 dict 汇入同一 queue）。
   - task_card/task_card_progress 事件 dict 已含 `type` 字段，可直接 yield。
   - **生命周期**：`done`/`error` 不立即 break。新增 `agent_finished` flag + 活跃卡片检查：
     - listener 收到 AGENT_END → 置 `agent_finished=True`，先 yield done/error。
     - 主循环：`agent_finished` 且 `long_task_manager` 无活跃卡片（`list_active_cards()` 为空）且 queue 空 → break。
     - 若无 long_task_manager：保持原 break 逻辑（done/error 立即 break）。
   - 后台 run_agent task 完成后，若 long_task_manager 存在，`await long_task_manager.wait_for_all(timeout=30)` 再 drain queue。
   - finally 仍 cancel run_agent task + unsubscribe。
2. `run_free_chat_stream`：构造 `LongTaskManager(dispatcher=None, auto_follow_up=False, default_timeout=0)`，`_conversation_id=conversation_id`（需校验非空），传入 `agent_events_to_sse_dict` + `load_skills`。
3. 注意：LongTaskManager 是 dataclass，`_conversation_id` 是实例属性字段，构造后赋值或通过 `field`。skill_loader.build_skill_tool 用 `getattr(long_task_manager, "_conversation_id", None)`。需在构造时设置。
4. 非 long_running skill 在流式/非流式均可执行（subprocess，不依赖 long_task_manager）。

### 6.2 前端

无改动。

### 6.3 桌面/打包

无改动。feature flag 默认 false。

## 7. 数据变更

- 新增 SQLite 列：`conversations.research_space_id TEXT`（nullable）。
- 迁移：幂等 `ALTER TABLE conversations ADD COLUMN research_space_id TEXT`，inspector 检查已存在则跳过。无 Alembic。
- 历史数据：旧行 research_space_id=NULL，`build_system_prefix(None)` 不注入 rs 记忆，兼容。
- 文件结构：无变更。
- 回滚：drop 列（SQLite 3.35+ 支持 DROP COLUMN）或重建表；实际回滚只需 flag=false，列保留无害。

## 8. 接口变更

- 无新增/删除接口。
- `/api/chat/free/stream` SSE 新增事件类型 `task_card` / `task_card_progress`（前端已支持）。
- `/api/chat/free` / `/api/chat/free/stream` 内部行为变更（flag=true 时）：max_turns 提升、注册工具——**请求/响应结构不变**，answer 仍是字符串，sources 仍是列表。
- 兼容策略：flag=false 时完全不变；flag=true 时前端无需改动。
- 需更新 `docs/system/api-inventory.md`：`/api/chat/free/stream` 行补充"flag=true 时 SSE 含 task_card/task_card_progress"。

## 9. UI/交互变更

无前端改动。task_card 渲染已有（messageRenderers.tsx L451）。

## 10. 测试方案

- 后端单测 `tests/agent/test_agent_service_p3_integration.py`：
  - run_free_chat 注册 workspace+memory 工具（mock models，断言 tools 名称）。
  - cid=None 时不注册 workspace 工具。
  - research_space_id 注入：构造 conversation 带 rs_id，断言 system_prompt 含 rs 标题。
  - sse_bridge：long_task_manager.dispatcher 事件的 task_card_progress 在 done 之后仍 yield；无活跃卡片后流关闭。
  - 长任务端到端：mock skill 脚本输出 PROGRESS 行，断言 card 状态流转。
- 扩展 `tests/test_chat_compat.py`：flag=false 行为不变断言。
- conversation_store 测试：research_space_id 读写 + ensure_conversation_columns 幂等。
- 回归：`cd backend && python3 -m pytest tests/ -q --ignore=tests/test_web_note_contracts.py` 全绿。
- 前端契约：`cd frontend && npx tsc --noEmit && pnpm test:contracts`（应无变化，因前端不改）。
- 原问题复现：flag=true 时 free_chat_stream 中 Agent 调用长任务 skill，前端能看到 task_card_progress 直到 SUCCESS。

## 11. 验收标准

- [ ] flag=false：`pytest tests/ -q --ignore=tests/test_web_note_contracts.py` 全绿（396+ passed，0 回归）。
- [ ] flag=true：run_free_chat_stream 注册 workspace+memory+skill 工具。
- [ ] flag=true + cid：system_prompt 含 research_space 记忆前缀（若 rs_id 已绑定）。
- [ ] flag=true：长任务 skill 的 task_card/task_card_progress 经 SSE 流推送，`done` 后流不立即关闭，任务结束后关闭。
- [ ] conversations 表新增 research_space_id 列，幂等迁移，历史行 NULL。
- [ ] 前端 `pnpm test:contracts` + `tsc --noEmit` 通过。
- [ ] api-inventory.md / data-model.md 同步更新。

## 12. 风险和回滚

- 主要风险：
  1. sse_bridge 生命周期重构引入死锁/泄漏（done 后不 break，若 long_task_manager 卡住流不关闭）。
  2. max_turns 提升导致 Agent 多轮调用增加 token 消耗。
  3. skill 脚本执行子进程安全（已在 skill_loader 用 create_subprocess_exec 非 shell + shlex）。
- 风险触发信号：flag=true 时流式请求超时/hang；usage 暴增。
- 降级策略：`AGENT_CHAT_ENABLED=false` 立即回退旧路径。
- 回滚步骤：设 flag=false；代码 revert；research_space_id 列保留无害。
- 回滚后数据一致性：research_space_id 列保留，记忆文件保留，不影响旧路径。

## 13. Agent 必答问题

- 影响哪些已有模块？agent_service / chat_adapter / sse_bridge / conversation_store / Conversation model / init_db。
- 当前系统是否已有类似能力？P3 五模块阶段一已实现但未接入运行时；本次是接入。
- 是否和产品规则冲突？不冲突，服务研究助手范式。
- 是否和数据模型字段语义冲突？新增列，不冲突；修正 memory.py docstring 错误字段名。
- 是否会重新引入 known-pitfalls？不：long_task 持久化卡片消息（不踩"状态不同步"）；SSE 是 wrapper 例外；本 Spec 合规。
- 是否影响本地数据或线上服务？仅本地；flag 默认 false。
- 最小可行改动？见 §6：一列 + 一 helper + _memory_prefix 加 rs_id + run_free_chat 注册工具提 max_turns + sse_bridge 接 long_task_manager。
- 需要补哪些测试防止回归？见 §10。
