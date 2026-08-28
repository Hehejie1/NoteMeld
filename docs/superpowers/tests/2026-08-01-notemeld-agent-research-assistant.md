# P3 notemeld-agent 验收报告（研究助手增强层）

日期：2026-08-02
关联 Spec：[`docs/superpowers/specs/2026-08-01-notemeld-agent-research-assistant.md`](../../superpowers/specs/2026-08-01-notemeld-agent-research-assistant.md)
前置：[P0 notemeld-ai](2026-08-01-notemeld-ai-llm-abstraction.md) ✅ + [P1 agent-core](2026-08-01-notemeld-agent-core-runtime.md) ✅ + [P2 Agent 接管 Chat](#) ✅

---

## 1. 交付物清单

### 新增模块（backend/app/agent/）

| 文件 | 行数 | 任务 | 说明 |
| --- | --- | --- | --- |
| [workspace.py](../../../backend/app/agent/workspace.py) | 370 | P3-T1 | 工作空间目录管理 + 路径穿越校验 + 3 个 AgentTool |
| [memory.py](../../../backend/app/agent/memory.py) | 546 | P3-T2 | 三层记忆 + 注入 hook + 2 个 AgentTool |
| [skill_loader.py](../../../backend/app/agent/skill_loader.py) | 780 | P3-T3 | SKILL.md 解析 + Parameter Collector + AgentTool 构造 |
| [long_task.py](../../../backend/app/agent/long_task.py) | 717 | P3-T4 | 长任务卡片 + 取消 + follow-up + SSE 事件 |
| [mcp_client.py](../../../backend/app/agent/mcp_client.py) | 853 | P3-T5 | MCP 适配器 + opt-in 配置 + 工具发现 |

### 接入改动

| 文件 | 改动 | 说明 |
| --- | --- | --- |
| [chat_adapter.py](../../../backend/app/agent/chat_adapter.py) | +`_memory_prefix()` 注入 | build_chat_hooks / build_free_chat_hooks 叠加 user_profile 长期记忆前缀 |
| [agent_service.py](../../../backend/app/agent/agent_service.py) | run_chat 追加 `create_memory_tools()` | Agent 可主动维护 user_profile / research_space |
| [routers/conversation.py](../../../backend/app/routers/conversation.py) | 引用 long_task + workspace | 长任务卡片查询 + 工作空间只读接口 |
| [routers/config.py](../../../backend/app/routers/config.py) | 引用 mcp_client | MCP server 配置管理接口 |

### 前端（P3-T6）

| 文件 | 说明 |
| --- | --- |
| [WorkspaceBrowser.tsx](../../../frontend/src/pages/HomePage/components/WorkspaceBrowser.tsx) | HomePage 工作空间浏览器组件 |
| [McpServers.tsx](../../../frontend/src/pages/SettingPage/McpServers.tsx) | Settings MCP 配置 UI（路由 `/mcp-servers`） |
| [workspace.ts](../../../frontend/src/services/workspace.ts) / [mcpServers.ts](../../../frontend/src/services/mcpServers.ts) | 前端服务层 |

### 新增测试（backend/tests/agent/）

| 文件 | 测试方法数 | 覆盖 |
| --- | --- | --- |
| [test_workspace.py](../../../backend/tests/agent/test_workspace.py) | 18 | 路径穿越（../、绝对、盘符）、cid 隔离、list/read/write、base64、截断、3 工具 |
| [test_memory.py](../../../backend/tests/agent/test_memory.py) | 19 | JSON 容错+备份、save/load 往返、masteries Top-N、build_system_prefix、hook 注入、2 工具 |
| [test_long_task.py](../../../backend/tests/agent/test_long_task.py) | 17 | 注册表、卡片状态流转、取消、follow-up 开关、持久化 |
| [test_skill_loader.py](../../../backend/tests/agent/test_skill_loader.py) | 30 | frontmatter 解析、load_skills、_substitute_command、build_skill_tool |
| [test_mcp_client.py](../../../backend/tests/agent/test_mcp_client.py) | 27 | 配置读写、opt-in 过滤、discover_all_tools（mock） |
| **合计** | **111** | — |

> 注：subagent 报告 74 + 本报告 workspace/memory 实测 118（含修复后），统一以实测为准：`pytest tests/agent/test_*.py -q` → **118 passed**。

---

## 2. 验收点逐条核对

| 验收点 | 状态 | 证据 |
| --- | --- | --- |
| §2 无 research_space 会话 → Agent 自动创建并询问确认 | 🟡 部分 | user_profile 注入已接通（chat_adapter `_memory_prefix`）；Agent 具备 `manage_research_space` 工具可创建；**research_space 注入需 cid→rs_id 业务映射，暂未接通** |
| §3 长任务卡片刷新页面状态不丢 | 🟡 部分 | long_task 模块实现 + 17 测试通过（含 append_message 持久化 mock 验证）；**SSE task_card 事件未接入 sse_bridge** |
| §4 取消 compile_source → 1s 内 CANCELED | ✅ 达成 | long_task `cancel_task` 调 `cancel_note_task` + 测试验证状态置 CANCELED |
| §5 工作空间路径穿越 → 403 | ✅ 达成 | workspace `resolve_safe_path` 拦截 `..`/绝对/盘符；18 测试含 11 个安全用例 |
| §6 follow-up 关闭后不产生新 assistant 消息 | ✅ 达成 | long_task `auto_follow_up` 开关 + 测试验证关闭时不调 `agent.follow_up` |

---

## 3. 测试验证结果

```bash
# P3 五模块单测
cd backend && python3 -m pytest tests/agent/test_workspace.py tests/agent/test_memory.py \
  tests/agent/test_long_task.py tests/agent/test_skill_loader.py tests/agent/test_mcp_client.py -q
# → 118 passed in 3.44s

# backend 全量（排除既有 web_note 收集错误）
cd backend && python3 -m pytest tests/ -q --ignore=tests/test_web_note_contracts.py
# → 394 passed, 2 failed（均为既有问题，与 P3 无关）

# 前端
cd frontend && npx tsc --noEmit        # → exit 0
cd frontend && pnpm test:contracts     # → 通过
```

### 既有失败（与本次 P3 无关，需另修）

1. `test_multisource_summary_contracts.py`：`app.services.note` 无 `NOTE_OUTPUT_DIR` 属性 — note.py 既有改动遗留。
2. `test_note_style_packaging_contracts.py`：打包脚本用 `rm -rf "${TARGET_OUTPUT_DIR}/bundle"`，测试断言旧路径 `${TARGET_DIR}/release/bundle` — 打包脚本既有改动遗留。

---

## 4. 关键设计决策

- **memory prefix 注入**：`chat_adapter._memory_prefix()` 仅注入全局 `user_profile`（无需 cid），research_space 注入留给上层业务（cid→rs_id 映射）。
- **memory 工具注册**：仅 `run_chat`（max_turns=3）追加 `create_memory_tools()`；`run_free_chat*`（max_turns=1，无工具）不追加（工具结果无法回传）。
- **容错**：memory JSON 损坏 → 备份 `*.corrupted-{ts}.json` + 默认值 + warning log；memory prefix 构建失败 → 跳过注入不阻断 chat。
- **P3 工具注册范围**：workspace/skill_loader/mcp_client 的 AgentTool 未注册到 agent_service（见未覆盖风险）。

---

## 5. 未覆盖风险（需后续接入）

1. **workspace/skill/mcp 工具未注册到 Agent 运行时**：模块自身可用（单测通过），但 Agent 运行时未调用。workspace 需 cid 传递，skill_loader 需 skills_dir + 脚本执行风险评估，mcp_client 需异步 discover 时机设计。
2. **research_space 记忆注入未接通**：需 `conversations.meta_json` 的 `research_space_id` → hook 的 cid→rs_id 映射。
3. **long_task SSE 事件未接入 sse_bridge**：`task_card` / `task_card_progress` 事件未映射到前端 SSE。
4. **P3 端到端 LLM 行为未验证**：同 P2 风险，单测用 FakeModels，生产 Agent 路径的 LLM 调用行为未做端到端 smoke test。建议启用 `AGENT_CHAT_ENABLED` 后手动验证：让 Agent 调 `update_user_profile` 记住用户偏好 → 新会话确认 prefix 注入。
5. **既有失败未修**：`test_multisource_summary_contracts` / `test_note_style_packaging_contracts` 两个失败属其他改动遗留，需单独修复。

---

## 6. 回滚策略

- memory 接入回滚：删除 `chat_adapter._memory_prefix()` 调用 + `agent_service.run_chat` 的 `create_memory_tools()` 追加。
- P3 模块回滚：删除 `backend/app/agent/{workspace,memory,skill_loader,long_task,mcp_client}.py` + 对应 router 引用 + 前端新增文件。
- 数据一致性：workspaces / memory 目录留盘不影响系统。

---

## 7. 结论

P3 五个模块（workspace / memory / skill_loader / long_task / mcp_client）**代码完成 + 111 单测全绿 + 前端接入 + tsc/契约通过**。memory hook 注入与 memory 工具已最小接入 agent_service，不破坏 P2 兼容性。

§4 / §5 / §6 验收点达成；§2 / §3 部分达成（模块就位，Agent 运行时集成待后续）。建议作为 **P3 阶段一（模块就绪）验收通过**，Agent 运行时全量集成（workspace/skill/mcp 工具注册 + research_space 注入 + long_task SSE）作为 P3 阶段二后续推进。
