# 验收报告：P3 阶段二 — Agent 运行时全量集成

更新时间：2026-08-02
对应 Spec：`docs/system/change-spec-p3-stage2-agent-runtime.md`

## 验收清单

| # | 验收项 | 状态 | 证据 |
|---|--------|------|------|
| 1 | flag=false：全量 pytest 全绿，0 回归 | ✅ | `417 passed`（396 旧 + 21 新） |
| 2 | flag=true：run_free_chat_stream 注册 workspace+memory+skill 工具 | ✅ | `test_run_free_chat_with_cid_registers_workspace_tools` / `test_run_free_chat_registers_memory_tools` |
| 3 | flag=true + cid：system_prompt 含 research_space 记忆前缀 | ✅ | `test_build_free_chat_hooks_injects_rs_id` |
| 4 | flag=true：长任务 task_card/task_card_progress 经 SSE 推送，done 后流不立即关闭 | ✅ | `test_long_task_manager_delays_break_after_done` / `test_long_task_progress_flows_through_sse` |
| 5 | conversations 表新增 research_space_id 列，幂等迁移，历史行 NULL | ✅ | `test_adds_column_when_missing` / `test_idempotent_when_column_exists` / `test_upsert_without_research_space_id_keeps_null` |
| 6 | 前端 `pnpm test:contracts` + `tsc --noEmit` 通过 | ✅ | 无输出（成功） |
| 7 | api-inventory.md / data-model.md 同步更新 | ✅ | 见下文"文档同步" |

## 实现摘要

### 1. cid→rs_id 落库
- `backend/app/db/models/conversation.py`：Conversation 新增 `research_space_id = Column(String, nullable=True)`
- `backend/app/db/conversation_schema.py`（新增）：`ensure_conversation_columns(engine)` 幂等 ALTER TABLE，模仿 `ensure_note_style_columns`
- `backend/app/db/init_db.py`：`ensure_note_style_columns()` 后调用 `ensure_conversation_columns(engine)`
- `backend/app/services/conversation_store.py`：
  - `_hydrate_conversation_payload` 读 `research_space_id` → `researchSpaceId`
  - `upsert_conversation` 写 `data.get("researchSpaceId")`，空字符串清空为 None
  - 新增 `get_conversation_research_space_id(cid) -> Optional[str]`，容错返回 None
- `backend/app/agent/memory.py`：修正 docstring L18 为"存 conversations.research_space_id 列"

### 2. research_space 注入
- `backend/app/agent/chat_adapter.py`：
  - `_memory_prefix(rs_id=None)` 调 `MemoryManager().build_system_prefix(rs_id)`
  - 新增 `_resolve_research_space_id(conversation_id)` 容错查询
  - `build_free_chat_hooks` 通过 cid 查 rs_id 传给 `_memory_prefix`；cid=None 时 rs_id=None
  - `build_chat_hooks` 保持 `_memory_prefix()`（rs_id=None，run_chat 无 cid）

### 3. workspace+memory+skill 工具注册
- `backend/app/agent/agent_service.py`：
  - 新增 `_build_free_chat_tools(cid, long_task_manager)`：memory 始终注册；cid 非空加 workspace；extend skill 工具
  - `run_free_chat` / `run_free_chat_stream`：`tools=[]` → `_build_free_chat_tools(...)`，max_turns 1→6（`_FREE_CHAT_MAX_TURNS`）

### 4. long_task SSE 接入
- `backend/app/agent/sse_bridge.py`：
  - `agent_events_to_sse_dict(..., long_task_manager=None)`：注入 `dispatcher = lambda evt: queue.put_nowait(evt)`
  - done/error 后：无 long_task_manager 立即 break（旧行为）；有 long_task_manager 不 break，run_agent finally 调 `wait_for_all(30s)` 后放哨兵 None 通知主循环退出
  - task_card/task_card_progress 事件经 dispatcher 汇入同一 SSE 队列
- `backend/app/agent/agent_service.py` `run_free_chat_stream`：
  - cid 非空时构造 `LongTaskManager(agent=None, auto_follow_up=False, dispatcher=None, default_timeout=0)`，设 `_conversation_id=conversation_id`
  - 传入 `agent_events_to_sse_dict` + `load_skills`

### 5. 测试
- 新增 `backend/tests/agent/test_agent_service_p3_integration.py`（10 tests）：工具注册、cid=None 不注册 workspace、rs_id 注入、sse_bridge 生命周期、长任务端到端
- 新增 `backend/tests/agent/test_conversation_research_space.py`（9 tests）：迁移幂等 + research_space_id 读写 + 容错
- 扩展 `backend/tests/agent/test_chat_compat.py`（+1 test）：flag=false 流式只产 delta/done

### 6. 文档同步
- `docs/system/api-inventory.md`：`/api/chat/free/stream` 补充 task_card/task_card_progress SSE 类型说明
- `docs/system/data-model.md`：conversations 表补充 `research_space_id` 字段说明

## 明确未做（spec §3）

- mcp_client 注册（异步网络 + adapter 生命周期，风险高，单独评估）
- run_chat（task-based RAG）的 P3 工具注册（语义不同，保留 create_builtin_tools + create_memory_tools）
- 前端改动（已支持 task_card/task_card_progress/parameter_request SSE 类型）
- ParameterCollector HTTP 端点 / 前端弹窗
- auto_follow_up（LongTaskManager.agent=None）

## 风险与回滚

- 主要风险：sse_bridge 生命周期重构（done 后不 break）→ 已用哨兵 + wait_for_all(30s) 兜底，超时也会退出
- 降级：`AGENT_CHAT_ENABLED=false` 立即回退旧路径（flag=false 0 回归已验证）
- research_space_id 列保留无害（nullable，旧路径不读写）
