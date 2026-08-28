# notemeld-agent-core：Agent 运行时（工具循环、状态机、事件流）

日期：2026-08-01
作者 / Agent：doc-driven 流程
状态：Ready for Plan
关联对话 / 任务：Pi 框架分析 → 分层架构确认 → P1 agent-core
关联系统文档：`docs/system/current-architecture.md`、`docs/system/product-rules.md`、`docs/system/known-pitfalls.md`、[P0 notemeld-ai 需求](2026-08-01-notemeld-ai-llm-abstraction.md)

## 1. 原始需求

> "notemeld-agent 修改为 'notemeld-agent-core' 这个完全对标 pi-agent-core，就是 agent 运行基础"
>
> "core 管 '怎么循环执行工具'，不管 '工具从哪里来、工具执行后 UI 怎么展示'。分层纯净。"
>
> 确认的分层：function call 原生支持；MCP 作为工具适配器接入；Skills 基于 Tool 之上再封装一层（封装在 notemeld-agent 业务层，不在 core）。
>
> 技术路线：先作为仓库内模块 `backend/app/agent/core/`。

## 2. 背景和问题

- **当前用户是谁**：上层 notemeld-agent（研究助手）和后续需要 agent 循环的子系统（比如样式提取、模板抽取、Wiki 智能合并）
- **当前场景是什么**：chat_service.py 里 `chat()` 手写了一个 `for round_i in range(3)` 的 tool loop，串行、无状态、无流式、最多 3 轮；其他业务如果要跑 agent 循环需要再抄一遍
- **当前痛点是什么**：
  1. Agent 循环不是一等公民：手写 for + 手动 append(msg) + 手动检查 tool_calls，容易漏边界（超过最大轮数、tool error 没回传正确格式、history 截断时机不对）
  2. 无状态机：每轮结束不知道 agent 是正在跑 tool、还是在等 LLM、还是出错；UI 无法做细粒度响应
  3. 无事件流：tool 开始/结束、每轮开始/结束都没有结构化事件，上层业务只能硬写回调或直接看日志
  4. 无 abort / steering：长 tool 循环过程中用户不能取消；想追加一条纠正消息要等下一轮才能注入
  5. 工具串行：一批 tool_calls 一个一个执行，note 级可并行的工具（如同时 lookup_transcript + get_video_info）被拖慢
  6. 消息和 LLM 消息没解耦：conversation_messages 里的 note_result / note_progress 等 UI 消息现在要靠 `message_type` 字段区分，塞到 LLM context 里时调用方得手动过滤
- **为什么现在要做**：P2 notemeld-agent（研究助手）的长任务、画布、三层记忆等能力都依赖一个稳定的 agent loop；现在不抽，业务层写死循环后后面返工更痛

## 3. 目标结果

- **目标 1**：提供 `notemeld_agent_core` 模块（仓库内路径 `backend/app/agent/core/`），暴露 `Agent` 类和底层 `agent_loop()` 生成器。内置状态机：AgentState（messages / tools / isStreaming / pendingToolCalls / error）
- **目标 2**：事件驱动。支持订阅 `agent_start / turn_start / message_start / message_update（delta） / message_end / tool_execution_start / tool_execution_update / tool_execution_end / turn_end / agent_end` 10 类事件，上层 UI / 日志 / 持久化各自订阅
- **目标 3**：原生支持工具循环。`AgentTool` 接口（name/description/参数 schema/execute），支持并行 / 串行执行模式（全局 + per-tool override），tool 抛异常自动以 `isError=True` 回传 LLM；最多轮数 + `shouldStopAfterTurn` 钩子双保险
- **目标 4**：上下文管理钩子。`transform_context()` 负责裁剪 / 压缩 / 注入外部上下文；`convert_to_llm()` 负责过滤 UI-only 消息、转换自定义类型。替换现有的 `history[-20:]` 暴力截断
- **目标 5**：控制能力。`abort()` 取消当前运行（中断 LLM stream + 调 tool 的 signal abort）；`steer()` 在 tool 执行中注入打断消息；`followUp()` 排队后续任务；`waitForIdle()` 等完整结束

## 4. 非目标

- 不做：MCP 工具适配器（在 notemeld-agent 业务层做，core 只认 AgentTool 接口）
- 不做：Skill 加载器 / skill.md 解析 / Parameter Collector（在 notemeld-agent 业务层做）
- 不做：长任务卡片 / 占位卡片 / 前端进度 UI（在 notemeld-agent + 前端做）
- 不做：工作空间、三层记忆、画布、知识看板（在 notemeld-agent 做）
- 不做：Provider 适配、token 统计（依赖 notemeld-ai P0）
- 不做：直接替换现有 chat_service.chat 循环（P2 notemeld-agent 再做替换，本 P1 只保证能跑通最小 demo）
- 不做：浏览器搜索 API、Web 搜索工具
- 不做：发布独立 pip 包（先仓库内模块）

## 5. 当前系统事实

- 已有类似能力：`chat_service.chat()` 中的 `for round_i in range(3)` 手写工具循环（位于 `backend/app/services/chat_service.py#L382-L445`）；`TOOLS` + `execute_tool` 位于 `backend/app/services/chat_tools.py`
- 当前入口 / 页面 / API：无 Agent 专用 API；现有 chat 通过 `/api/chat/ask` 和 `/api/chat/free/stream` 触发
- 当前数据来源和写入位置：conversation_messages（对话消息）、conversation（会话头）；usage 由 record_usage 直接写
- 当前限制：
  - 历史消息截断 = `history[-20:]`，不看 token 数
  - tool 循环最大 3 轮，到最后一轮强制不带 tools 再调一次兜底
  - 没有 abort，chat 发起后后端会跑到结束即使前端页面已关闭
- 相关 known pitfalls：
  - 长任务进度 / 状态不同步的教训：agent 事件必须支持持久化到 conversation_messages，不能只走内存
  - 取消语义：abort 必须是"温柔取消"，取消后产生的部分输出必须保留且能续跑（参考 Wiki rebuild 的 latest-wins 思想，但 agent 侧先简单实现：cancel token + 写 state）

## 6. 用户故事

- 作为 notemeld-agent 开发者，我希望 `agent.prompt(prompt_text)` 一行跑完整轮对话 + 工具 + 多轮循环，而不用自己写 for round_i 和检查 tool_calls，以便把精力放在业务工具上
- 作为前端聊天 UI，我希望订阅 agent 事件后，能实时渲染 "Agent 正在思考" / "正在查询转写片段" / "查询完成" 等状态，而不是等到最后一次性展示，以便让长对话不卡死
- 作为长任务的上层业务（compile_source 长任务），我希望在工具执行到一半时 `agent.steer(user_interrupt_msg)` 注入用户纠正，工具结束后下一 turn 立刻生效，以便用户可以中途改需求

## 7. 验收标准

1. GIVEN 一个至少调 2 次 tool 的对话（比如先 lookup_transcript 再 summarize），WHEN 走 `agent.prompt()` 跑完，THEN 事件序列严格为 `agent_start → turn_start → message_start(user) → message_end → message_start(assistant) → message_update* → message_end(toolCall) → tool_execution_start → tool_execution_end → message_start(toolResult) → message_end → turn_end → turn_start(下一轮) → ... → agent_end`，缺事件或事件倒序 = 失败

2. WHEN 配置 `toolExecution="parallel"` 且同一轮 assistant 返回 2 个无依赖 tool_calls，THEN 2 个 execute() 并发执行（时间差 ≤ 各自耗时的 10%），tool_execution_end 顺序按完成先后；但 `turn_end.toolResults` 和写入 messages 的顺序与 assistant 原文顺序一致

3. GIVEN agent 当前正在执行一个耗时工具（execute 里有 sleep 2s），WHEN 调用 `agent.abort()`，THEN AbortSignal 在 200ms 内被传递到 execute 的 signal 参数，工具尽快退出；agent 状态 `isStreaming=False`，`errorMessage` 包含 "aborted" 可读描述；未完成的 tool 不产生僵尸状态

4. GIVEN `messages` 里混入 5 条 UI-only 的 `note_progress` 消息，WHEN `convert_to_llm()` 过滤后，THEN 送给 LLM 的消息列表里不包含这 5 条；且原 messages 数组不被 mutate（浅拷贝后过滤）

5. WHEN 达到最大轮数（比如配置 max_turns=5）仍在 tool_call，THEN 循环在第 5 轮后停止，状态 errorMessage 提示 "max turns reached"，不抛异常；并产出最后一次 assistant 文本内容（如果有的话），不吞掉已有输出

## 8. 输入 / 输出样例

### 输入

```python
from app.ai import Type
from app.agent.core import Agent, AgentTool, AgentState

lookup_tool = AgentTool(
    name="lookup_transcript",
    label="查询转写",
    description="按关键词查询视频转写片段",
    parameters=Type.Object({"task_id": Type.String(), "keyword": Type.String()}),
    executionMode="parallel",
    execute=lambda call_id, params, signal, on_update:
        {"content": [{"type": "text", "text": f"在{params['task_id']}找到 xxx"}], "details": {}},
)

agent = Agent(
    initial_state=AgentState(
        system_prompt="你是研究助手，必要时主动调用工具",
        model=model,              # 来自 notemeld-ai 的 Model 对象
        tools=[lookup_tool],
        messages=[],
    ),
    max_turns=10,
    tool_execution="parallel",
    # 上下文钩子
    transform_context=lambda msgs, sig: prune_by_token_budget(msgs, budget=128000),
    convert_to_llm=lambda msgs: [m for m in msgs if m.role in ("user", "assistant", "toolResult")],
    # 钩子
    before_tool_call=lambda tc, args, ctx: None,
    after_tool_call=None,
)

def on_event(evt):
    if evt.type == "tool_execution_start":
        print(f"[tool start] {evt.tool_call.name}")

agent.subscribe(on_event)
await agent.prompt("帮我在视频 task-abc 里搜 'NeRF' 关键词")
await agent.wait_for_idle()
```

### 输出（事件序列，简化）

```
agent_start
turn_start
message_start  user
message_end    user
message_start  assistant
message_update delta="好的，我来帮你查找"
message_end    assistant (tool_call=lookup_transcript(task_id="task-abc", keyword="NeRF"))
tool_execution_start  call_id=xxx, tool_name=lookup_transcript
tool_execution_end    call_id=xxx, result={...}
message_start  toolResult
message_end    toolResult
turn_end       toolResults=[lookup_transcript]
turn_start
message_start  assistant
message_update delta="找到了，原话是 'NeRF 于 2020 年提出...'"
message_end    assistant
turn_end       toolResults=[]
agent_end
```

### 反例或失败样例

- Tool execute 抛异常 → 不 crash agent；emit `tool_execution_end` 带 `isError=True`；下一轮 LLM 收到 toolResult.isError=True 并带异常 message
- 同一工具的并行执行参数冲突 → core 不在此层处理（上层业务工具自行保证可重入/并发安全），core 只负责并发调度

## 9. 约束

- **平台 / 设备**：Python 3.11+；asyncio 原生（Agent 基于 async/await）；兼容桌面 sidecar + 源码启动
- **性能 / 耗时**：单轮循环 + 空工具额外开销 ≤ 10ms；100 条消息的 transform_context/convert_to_llm 总耗时 ≤ 2ms
- **隐私 / 安全**：事件日志、subscribe 回调中不打印工具参数中的潜在敏感内容（可由上层工具在 details 字段中自行脱敏）；abort 不产生 partial 写入到 SQLite（写入逻辑在上层业务）
- **兼容性**：
  - 不引入对 notemeld-ai 以外的业务依赖；core 可以单独 `pytest backend/tests/agent-core/` 跑单测（不启动 FastAPI、不依赖 SQLite）
  - 仓库内模块路径 `backend/app/agent/core/`，与后续 notemeld-agent（`backend/app/agent/` 下其他子模块）不冲突
- **成本**：零新增付费依赖；依赖只用到项目已有的 pydantic/typing 生态 + P0 notemeld-ai
- **时间**：P1 里程碑，必须在 P0 notemeld-ai 完成后、P2 notemeld-agent 之前完成
- **第三方依赖 / License**：不引入新的重量级库；AbortSignal 用 `asyncio.Event` 实现；参数 schema validation 用 pydantic 或 notemeld-ai 的 TypeBox 等价实现

## 10. 边界场景

- **空数据**：messages 为空 + 不传 prompt → `agent.prompt("")` 直接抛 ValueError；`agent.continue()` 检查最后一条不是 user/toolResult 时抛清晰错误
- **权限拒绝**：工具权限由 `before_tool_call` 返回 `{block: True, reason: "xxx"}` 控制；被 block 的工具不执行，agent 收到一条 isError=True 的 toolResult，循环继续
- **网络失败**：LLM 调用失败（notemeld-ai 抛 ProviderNetworkError）→ agent 事件 emit error，agent 状态 errorMessage 赋值；不重试（重试策略在上层业务）
- **任务中断**：abort 后再 `agent.prompt(...)` 必须能正常续跑（不是永久坏状态）；符合 `continue()` 语义
- **旧数据兼容**：无数据库变更，此条不适用
- **大数据量**：一次事件订阅队列积压 ≥ 100 条时不阻塞生产者（事件派发到独立 asyncio task 队列，订阅者慢不拖慢主循环；但默认 await 顺序订阅者为兼容简单场景）
- **其他**：subscribe 的 listener 自己抛异常 → core 捕获、写 error log、不中断主循环、不影响其他订阅者

## 11. 开放问题

无。所有阻塞项已在对话中确认。

## 12. 与系统事实的冲突检查

- **是否和 product-rules.md 冲突**：否。本地优先、长任务可恢复、MCP 不变、桌面+源码双入口均保持
- **是否和 data-model.md 字段语义冲突**：否。core 不读写 DB（由上层业务订阅事件后写 conversation_messages 等）
- **是否和 api-inventory.md 接口语义冲突**：否。本期不新增/改动 API（P2 再替换 chat 接口）
- **是否会重新引入 known-pitfalls.md 中的问题**：
  - 取消后状态脏：abort 设置 state.errorMessage + 温柔退出，不会产生无限 running 的僵尸
  - 慢请求进全局锁：core 本身无锁（工具层自行决定），不会重引入
- **是否影响本地数据或线上服务**：本地追加写 conversation_messages 等，但由上层业务控制；core 是纯内存运行时
- **是否影响用户已确认交互**：否。P1 只替换底层循环，P2 再对外替换 chat

## 13. 实际影响清单（DB / 数据结构 / 接口 / 文件 / 回归点）

> 用于回归测试与变更影响审计。P0-P5 全部完成后统一写回 `docs/system/`。

### 13.1 数据库影响

| 表 | 字段 | 影响 | 备注 |
| --- | --- | --- | --- |
| `conversation_messages` | 全部字段 | **不读写** | core 是纯内存运行时；写入由上层业务订阅事件后处理 |
| `conversations` | 全部字段 | **不读写** | 同上 |
| `model_usage_records` | 全部字段 | **不直接写** | core 调用 notemeld-ai，由 notemeld-ai 内置 usage writer 写入 |

**结论**：P1 不新增表、不新增字段、不新增迁移脚本、不读写任何 SQLite 表。

### 13.2 数据结构影响（纯新增，零破坏）

| 数据结构 | 类型 | 文件路径 |
| --- | --- | --- |
| `Agent` 类（核心运行时） | 新增 | `backend/app/agent/core/agent.py` |
| `AgentState`（messages/tools/isStreaming/pendingToolCalls/error/turnCount） | 新增 | `backend/app/agent/core/state.py` |
| `AgentTool` 接口（name/label/description/parameters/executionMode/execute） | 新增 | `backend/app/agent/core/tool.py` |
| `AgentEvent` 联合类型（10 类事件） | 新增 | `backend/app/agent/core/events.py` |
| `AbortSignal`（基于 asyncio.Event） | 新增 | `backend/app/agent/core/signal.py` |
| `transform_context` / `convert_to_llm` 钩子签名 | 新增 | `backend/app/agent/core/hooks.py` |
| `before_tool_call` / `after_tool_call` 钩子签名 | 新增 | 同上 |
| `AgentMessage`（与 LLM Message 解耦的对话消息抽象） | 新增 | `backend/app/agent/core/message.py` |

### 13.3 接口影响

| 接口 | 类型 | 变更 |
| --- | --- | --- |
| 现有所有 API | 既有 | **0 改动**（P1 只替换底层循环，P2 才对外替换 chat） |
| `/api/chat/ask` / `/api/chat/free` / `/api/chat/free/stream` | 既有 | **0 改动** |
| MCP `/mcp` | 既有 | **0 改动** |

**结论**：P1 不新增/不修改/不删除任何对外 API。仅作为底层模块供 P2 调用。

### 13.4 文件清单

**新增**：
- `backend/app/agent/__init__.py`
- `backend/app/agent/core/__init__.py`
- `backend/app/agent/core/agent.py`（Agent 主循环 + agent_loop 生成器）
- `backend/app/agent/core/state.py`（AgentState）
- `backend/app/agent/core/tool.py`（AgentTool 接口）
- `backend/app/agent/core/events.py`（10 类事件 + 派发器）
- `backend/app/agent/core/signal.py`（AbortSignal）
- `backend/app/agent/core/hooks.py`（transform_context/convert_to_llm/before_tool_call/after_tool_call）
- `backend/app/agent/core/message.py`（AgentMessage 抽象）
- `backend/app/agent/core/loop.py`（agent_loop 核心生成器逻辑）
- `backend/tests/agent_core/__init__.py`
- `backend/tests/agent_core/test_events_sequence.py`（事件序列断言）
- `backend/tests/agent_core/test_parallel_tools.py`
- `backend/tests/agent_core/test_abort_steer.py`
- `backend/tests/agent_core/test_max_turns.py`
- `backend/tests/agent_core/test_transform_context.py`
- `backend/tests/agent_core/test_convert_to_llm.py`
- `backend/tests/agent_core/test_e2e_demo.py`（用 notemeld-ai + 2 假工具的 3 turn 端到端）

**修改**：无（P1 不动现有 chat_service，P2 才迁移）

### 13.5 回归测试点

| 回归点 | 验证方式 | 通过标准 |
| --- | --- | --- |
| 现有 chat 行为 | `backend/tests/test_chat_*.py` 不动 | 全绿（P1 不改 chat 实现，应 0 影响） |
| 事件序列 | `test_events_sequence.py` 录制 3 turn 快照对比 | 严格按 §7 验收 1 顺序 |
| 并行工具 | `test_parallel_tools.py` 测 2 个无依赖 tool_calls 并发 | 时间差 ≤ 各自耗时 10%；写入顺序与 assistant 原文一致 |
| abort 温柔取消 | `test_abort_steer.py` 测 sleep 2s 工具的 abort | 200ms 内 signal 传递；状态 errorMessage 含 "aborted" |
| max_turns 兜底 | `test_max_turns.py` 测 5 轮后仍 tool_call | 第 5 轮停止；不抛异常；保留最后 assistant 文本 |
| convert_to_llm 过滤 | `test_convert_to_llm.py` 注入 5 条 note_progress | 过滤后不含；原数组不 mutate |
| 独立单测可跑 | `pytest backend/tests/agent_core/ -v` | 不启动 FastAPI、不依赖 SQLite 也能跑 |
| 端到端 demo | `test_e2e_demo.py` 接真实 notemeld-ai + deepseek | 3 turn 对话事件序列快照通过 |
| 核心回归 | `scripts/run_core_regression.sh` | 全绿（应 0 影响） |

## 14. Superpowers 交接

- 是否已达到 Ready for Plan：是
- 推荐下一步：
  - [x] 先等 P0 notemeld-ai 的 Plan/Spec 完成并跑通
  - [ ] 使用 Superpowers 生成 `docs/superpowers/plans/2026-08-01-notemeld-agent-core-runtime.md`
  - [ ] 使用 Superpowers 生成 `docs/superpowers/specs/2026-08-01-notemeld-agent-core-runtime.md`
- 计划必须覆盖的验收标准：第 1（事件序列完整）、2（并行工具执行与顺序一致）、3（abort 温柔取消）条
- 计划必须补充的验证：
  - 单元测试覆盖 10 类事件的顺序和内容；并行工具；串行工具；before_tool_call block；异常 tool；max_turns；steer；followUp；continue
  - 端到端最小 demo：用 notemeld-ai 接 deepseek + 两个假工具，跑通 3 turn 对话，录制事件序列快照对比
