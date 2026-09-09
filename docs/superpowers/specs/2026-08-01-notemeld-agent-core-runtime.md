# P1 notemeld-agent-core：Plan + Spec（合并）

日期：2026-08-01
作者 / Agent：doc-driven 流程
关联需求：[`docs/requirements/2026-08-01-notemeld-agent-core-runtime.md`](../../requirements/2026-08-01-notemeld-agent-core-runtime.md)
前置依赖：[P0 notemeld-ai](2026-08-01-notemeld-ai-llm-abstraction.md) 必须先完成并跑通
状态：Confirmed（待用户最终确认后开始执行）

---

## Part A：Plan（任务拆分 + 依赖顺序 + 风险）

### A.1 任务拆分

| # | 任务 | 依赖 | 验收映射 | 风险 |
| --- | --- | --- | --- | --- |
| T1 | 创建 `backend/app/agent/core/` 骨架 + `signal.py`（AbortSignal 基于 asyncio.Event） | 无 | - | 低 |
| T2 | 实现 `message.py`：AgentMessage 抽象（role/content/message_type/meta）+ 与 LLM Message 转换 | T1 | §7.4 convert 过滤 | 低 |
| T3 | 实现 `tool.py`：AgentTool 接口（name/label/description/parameters/executionMode/execute） | T1 | §7.2 并行执行 | 低 |
| T4 | 实现 `events.py`：10 类 AgentEvent + EventDispatcher（异步派发 + 异常隔离） | T1 | §7.1 事件序列 | 中，异常隔离关键 |
| T5 | 实现 `state.py`：AgentState（messages/tools/isStreaming/pendingToolCalls/error/turnCount） | T2 T3 | - | 低 |
| T6 | 实现 `hooks.py`：transform_context/convert_to_llm/before_tool_call/after_tool_call 钩子签名 + 默认实现 | T2 T3 | §7.4 | 低 |
| T7 | 实现 `loop.py`：agent_loop 核心生成器（turn 循环 + LLM 调用 + tool 执行 + 事件派发） | T4 T5 T6 P0 | §7.1 §7.2 §7.3 §7.5 | **高**，最核心 |
| T8 | 实现 `agent.py`：Agent 类（prompt/continue/abort/steer/followUp/waitForIdle/subscribe） | T7 | §7.3 abort §7.5 max_turns | **高** |
| T9 | 单测 1：`test_events_sequence.py`（3 turn 事件序列快照断言） | T8 | §7.1 | 中 |
| T10 | 单测 2：`test_parallel_tools.py`（2 个无依赖 tool_calls 并发 + 顺序一致） | T8 | §7.2 | 中 |
| T11 | 单测 3：`test_abort_steer.py`（sleep 2s 工具的 abort + steer 注入） | T8 | §7.3 | 中 |
| T12 | 单测 4：`test_max_turns.py`（5 轮后仍 tool_call 的兜底） | T8 | §7.5 | 低 |
| T13 | 单测 5：`test_transform_context.py` + `test_convert_to_llm.py`（注入 5 条 note_progress 过滤 + 不 mutate） | T8 | §7.4 | 低 |
| T14 | 端到端：`test_e2e_demo.py`（接 P0 notemeld-ai + deepseek + 2 假工具跑 3 turn） | T8 P0 完成 | §7.1 全量 | 中 |
| T15 | 回归：`backend/tests/test_chat_*.py` + `scripts/run_core_regression.sh` 应 0 影响 | T14 | §13.5 | 低 |
| T16 | 验收报告 `docs/superpowers/tests/2026-08-01-notemeld-agent-core-runtime.md` | T15 | - | - |

### A.2 依赖图

```
T1 ─┬─ T2 ──┐
    ├─ T3 ──┼─ T5 ──┐
    └─ T4 ──┘       │
                    ├─ T6 ──┐
                    │       │
                    └───────┼─ T7 ── T8 ──┬─ T9  ──┐
                            │   ↑↓ P0     ├─ T10 ──┤
                            │             ├─ T11 ──┼─ T15 ─ T16
                            │             ├─ T12 ──┤
                            │             ├─ T13 ──┤
                            │             └─ T14 ──┘
```

### A.3 风险与回滚

| 风险 | 触发信号 | 降级 / 回滚 |
| --- | --- | --- |
| 事件序列乱序 | test_events_sequence 失败 | 检查 EventDispatcher 的派发顺序；必要时改同步派发 |
| 并行工具顺序错乱 | test_parallel_tools 失败 | 改为 gather 后按原 index 重排，不依赖完成顺序 |
| abort 不温柔 | sleep 工具 abort 超过 200ms | 检查 signal 传递路径；execute 内必须轮询 signal |
| 现有 chat 退化 | test_chat_*.py 失败 | P1 不改 chat_service，应 0 影响；失败说明误改了 |
| 独立单测依赖 SQLite | pytest backend/tests/agent_core/ 启动失败 | 检查 import 链；core 不应 import 任何 services/gpt/ |

**回滚策略**：P1 全部为新增文件，无修改现有文件；回滚 = 删除 `backend/app/agent/core/` 目录。零影响。

---

## Part B：Spec（详细规格，按 NoteMeld change-spec-template）

### B.0 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已搜索 `backend/app/services/chat_service.py` 现有 tool loop（行号 §5）
- [x] 已搜索 `backend/app/services/chat_tools.py` 现有工具定义
- [x] 已确认 P0 notemeld-ai 必须先完成
- [x] 已确认 P1 不影响线上服务（无对外 API 改动）

### B.1 当前系统现状

- **相关模块**：`backend/app/services/chat_service.py`（chat 函数的 `for round_i in range(3)` 手写循环）、`backend/app/services/chat_tools.py`（TOOLS + execute_tool）
- **相关入口**：无 Agent 专用入口；现有 chat 通过 `/api/chat/ask` 和 `/api/chat/free/stream` 触发
- **相关数据表**：conversation_messages / conversations（P1 不读写）
- **相关 API**：无（P1 不新增/修改 API）
- **相关测试**：`backend/tests/test_chat_*.py`（P1 应 0 影响）
- **当前行为**：手写 for + 手动 append + 手动检查 tool_calls；串行；最多 3 轮
- **当前限制**：见需求 §2

### B.2 本次目标（可验证）

- 用户问题：见需求 §1
- 成功后的用户可见行为：无（P1 是底层模块，P2 才对外替换 chat）
- 成功后的系统内部行为：`backend/app/agent/core/` 可独立运行；`pytest backend/tests/agent_core/` 全绿
- 必须保留的旧行为：chat_service 不动

### B.3 明确不做

见需求 §4。

### B.4 冲突分析

见需求 §12。

### B.5 影响范围（即需求 §13 实际影响清单）

详见需求 §13.1-§13.5。

**关键摘要**：
- DB：0 表 0 字段 0 迁移；core 不读写任何 SQLite
- 接口：0 改动
- 文件：纯新增 10 个源文件 + 7 个测试文件；0 修改现有文件
- 回归点：9 类回归断言（核心是"应 0 影响"）

### B.6 实施方案

#### 后端

**改动点**：见 A.1 任务拆分。核心实现：

```python
# backend/app/agent/core/loop.py 核心伪代码
async def agent_loop(state: AgentState, hooks: Hooks, dispatcher: EventDispatcher,
                     max_turns: int, signal: AbortSignal):
    await dispatcher.emit(AgentStartEvent())
    while state.turn_count < max_turns and not signal.aborted:
        state.turn_count += 1
        await dispatcher.emit(TurnStartEvent(turn=state.turn_count))

        # 1. transform_context + convert_to_llm
        ctx = hooks.transform_context(state.messages, signal)
        llm_msgs = hooks.convert_to_llm(ctx)

        # 2. LLM 调用（notemeld-ai）
        await dispatcher.emit(MessageStartEvent(role="assistant"))
        async for evt in models.stream(state.model, llm_msgs, signal=signal):
            if evt.type == "text_delta":
                await dispatcher.emit(MessageUpdateEvent(delta=evt.delta))
            elif evt.type == "toolcall_end":
                state.pending_tool_calls.append(evt.tool_call)
        await dispatcher.emit(MessageEndEvent(role="assistant",
                                                tool_calls=state.pending_tool_calls))
        # 3. 无 tool_call → turn 结束，无下一轮
        if not state.pending_tool_calls:
            await dispatcher.emit(TurnEndEvent(turn=state.turn_count, tool_results=[]))
            break

        # 4. 执行工具（并行/串行）
        results = await execute_tools(state.pending_tool_calls, state.tools,
                                       hooks, dispatcher, signal)
        # 5. 写回 toolResult 消息
        for r in results:
            state.messages.append(ToolResultMessage(content=r.content, isError=r.isError,
                                                     tool_call_id=r.call_id))
            await dispatcher.emit(MessageStartEvent(role="toolResult"))
            await dispatcher.emit(MessageEndEvent(role="toolResult"))
        await dispatcher.emit(TurnEndEvent(turn=state.turn_count, tool_results=results))
        state.pending_tool_calls.clear()

    if state.turn_count >= max_turns and state.pending_tool_calls:
        state.error = AgentError(code="max_turns_reached",
                                  message=f"reached max_turns={max_turns}")
    await dispatcher.emit(AgentEndEvent(error=state.error))
```

```python
# backend/app/agent/core/agent.py 核心伪代码
class Agent:
    def __init__(self, initial_state, max_turns=10, tool_execution="parallel", **hooks):
        self._state = initial_state
        self._dispatcher = EventDispatcher()
        self._max_turns = max_turns
        self._tool_execution = tool_execution
        self._hooks = Hooks(**hooks)
        self._signal = AbortSignal()
        self._idle = asyncio.Event(); self._idle.set()

    def subscribe(self, listener): self._dispatcher.subscribe(listener)

    async def prompt(self, text: str):
        if not text: raise ValueError("prompt text required")
        self._state.messages.append(UserMessage(content=text))
        await self._run()

    async def continue_(self):
        last = self._state.messages[-1]
        if last.role not in ("user", "toolResult"):
            raise AgentError("continue requires last message be user/toolResult")
        await self._run()

    async def abort(self):
        self._signal.abort(reason="user_aborted")
        self._state.error = AgentError(code="aborted", message="aborted by user")

    async def steer(self, interrupt_msg: str):
        """注入打断消息，下一 turn 生效"""
        self._state.messages.append(UserMessage(content=interrupt_msg, meta={"steer": True}))

    async def follow_up(self, prompt: str):
        """排队后续任务"""
        await self._idle.wait()
        await self.prompt(prompt)

    async def wait_for_idle(self):
        await self._idle.wait()

    async def _run(self):
        self._idle.clear()
        try:
            await agent_loop(self._state, self._hooks, self._dispatcher,
                              self._max_turns, self._signal)
        finally:
            self._idle.set()
```

```python
# backend/app/agent/core/signal.py
class AbortSignal:
    def __init__(self):
        self._event = asyncio.Event()
        self._reason: str | None = None
    def abort(self, reason: str = ""):
        self._reason = reason
        self._event.set()
    @property
    def aborted(self) -> bool: return self._event.is_set()
    @property
    def reason(self) -> str | None: return self._reason
    async def wait(self): await self._event.wait()
```

**错误处理**：见需求 §10。
**日志/可观测性**：subscribe listener 抛异常不中断主循环；写 error log。
**并发/取消**：abort 通过 signal 传递；execute 内必须轮询 signal.aborted。

#### 前端

无改动。

#### 桌面/打包

无改动。

### B.7 数据变更

- 是否新增/修改 SQLite 表：**否**
- 是否新增/修改字段：**否**
- 是否新增/修改文件结构：**是**，新增 `backend/app/agent/core/` 目录
- 是否需要迁移：**否**
- 是否影响历史数据：**否**
- 是否需要清理脏数据：**否**
- 回滚后数据如何处理：N/A（core 不写数据）

### B.8 接口变更

- 新增接口：**无**
- 修改接口：**无**
- 删除接口：**无**
- 请求参数变化：**无**
- 返回结构变化：**无**
- 错误语义变化：**无**
- 前端调用方：无改动
- MCP 调用方：无改动
- 兼容策略：N/A（纯新增）
- 是否更新 `docs/system/api-inventory.md`：**否**（P0-P5 完成后统一更新）

### B.9 UI/交互变更

无。P1 纯底层。

### B.10 测试方案

- 后端单测：`backend/tests/agent_core/test_*.py`（7 份测试文件）
- 独立可跑：`pytest backend/tests/agent_core/ -v` 不启动 FastAPI、不依赖 SQLite
- 后端契约：`backend/tests/test_chat_*.py` 应 0 影响（P1 不改 chat）
- 核心回归：`scripts/run_core_regression.sh` 应 0 影响
- 端到端：`test_e2e_demo.py` 接真实 P0 notemeld-ai + deepseek 跑 3 turn
- 原问题复现：N/A
- 回归断言：见需求 §13.5

### B.11 验收标准

见需求 §7。

- [ ] §7.1 事件序列严格按 10 类顺序
- [ ] §7.2 并行工具时间差 ≤ 10% + 写入顺序与原文一致
- [ ] §7.3 abort 200ms 内 signal 传递 + 状态 errorMessage 含 "aborted"
- [ ] §7.4 convert_to_llm 过滤 UI-only 消息 + 原 messages 不 mutate
- [ ] §7.5 max_turns 兜底 + 保留最后 assistant 文本

### B.12 风险和回滚

见 A.3。

### B.13 Agent 必答问题

- 这个需求影响哪些已有模块？→ **不影响**（纯新增；现有 chat_service 不动）
- 当前系统是否已有类似能力？→ 有，chat_service.py 的手写 for 循环，本需求是抽象出独立可复用的运行时
- 是否和产品规则冲突？→ 否
- 是否和数据模型字段语义冲突？→ 否，0 schema 改动
- 是否会重新引入 known-pitfalls 中的问题？→ 否
- 是否影响本地数据或线上服务？→ 否，core 是纯内存运行时
- 最小可行改动是什么？→ A.1 任务拆分
- 需要补哪些测试防止回归？→ B.10 测试方案

### B.14 Implementation Reference

#### 10 类事件类型

```python
# backend/app/agent/core/events.py
class AgentEventType(str, Enum):
    AGENT_START = "agent_start"
    TURN_START = "turn_start"
    MESSAGE_START = "message_start"
    MESSAGE_UPDATE = "message_update"
    MESSAGE_END = "message_end"
    TOOL_EXECUTION_START = "tool_execution_start"
    TOOL_EXECUTION_UPDATE = "tool_execution_update"
    TOOL_EXECUTION_END = "tool_execution_end"
    TURN_END = "turn_end"
    AGENT_END = "agent_end"

@dataclass
class AgentEvent:
    type: AgentEventType
    turn: int | None = None
    role: str | None = None  # user/assistant/toolResult
    delta: str | None = None
    tool_call: ToolCall | None = None
    call_id: str | None = None
    tool_name: str | None = None
    result: ToolResult | None = None
    error: AgentError | None = None

class EventDispatcher:
    def __init__(self):
        self._listeners: list[Callable[[AgentEvent], Awaitable[None]]] = []
    def subscribe(self, listener): self._listeners.append(listener)
    async def emit(self, evt: AgentEvent):
        for l in self._listeners:
            try: await l(evt)
            except Exception as e: logger.error(f"listener error: {e}")
            # 不中断主循环，不影响其他 listener
```

#### AgentTool 接口

```python
# backend/app/agent/core/tool.py
class AgentTool(BaseModel):
    name: str
    label: str | None = None
    description: str
    parameters: dict  # JSON Schema via P0 notemeld-ai Type
    execution_mode: Literal["parallel", "serial"] = "serial"
    execute: Callable  # async (call_id, params, signal, on_update) -> ToolResult

class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict

class ToolResult(BaseModel):
    call_id: str
    content: list[dict]  # [{type: "text", text: "..."}]
    details: dict = {}
    is_error: bool = False
```

#### 并行工具执行

```python
# backend/app/agent/core/loop.py 片段
async def execute_tools(tool_calls, tools, hooks, dispatcher, signal, mode="parallel"):
    results: list[ToolResult | None] = [None] * len(tool_calls)
    if mode == "parallel":
        async def run_one(i, tc):
            tool = next((t for t in tools if t.name == tc.name), None)
            if not tool:
                results[i] = ToolResult(call_id=tc.id, content=[{"type":"text","text":f"tool {tc.name} not found"}], is_error=True)
                return
            block = await hooks.before_tool_call(tc, tc.arguments, {})
            if block and block.get("block"):
                results[i] = ToolResult(call_id=tc.id, content=[{"type":"text","text":block["reason"]}], is_error=True)
                return
            await dispatcher.emit(TOOL_EXECUTION_START, call_id=tc.id, tool_name=tc.name)
            try:
                r = await tool.execute(tc.id, tc.arguments, signal,
                                        on_update=lambda u: dispatcher.emit(TOOL_EXECUTION_UPDATE, call_id=tc.id, details=u))
                results[i] = r
            except Exception as e:
                results[i] = ToolResult(call_id=tc.id, content=[{"type":"text","text":str(e)}], is_error=True)
            await dispatcher.emit(TOOL_EXECUTION_END, call_id=tc.id, result=results[i])
        await asyncio.gather(*[run_one(i, tc) for i, tc in enumerate(tool_calls)])
    else:
        # 串行模式：依次执行
        for i, tc in enumerate(tool_calls):
            await run_one(i, tc)
    # 关键：返回顺序与原 tool_calls 顺序一致，不按完成先后
    return [r for r in results]
```

### B.15 依赖关系

| 依赖项 | 版本 | 用途 | 新增/修改 |
| --- | --- | --- | --- |
| P0 notemeld-ai | 本仓库 | Model + stream/complete + Type schema | 内部依赖 |
| asyncio | 标准库 | EventDispatcher + AbortSignal | 已用 |
| pydantic | 已有 | AgentTool/AgentEvent/ToolResult | 已用 |

无新增外部依赖。

### B.16 测试命令

```bash
# 独立单元测试（不依赖 FastAPI / SQLite）
pytest backend/tests/agent_core/ -v

# 关键单测
pytest backend/tests/agent_core/test_events_sequence.py -v
pytest backend/tests/agent_core/test_parallel_tools.py -v
pytest backend/tests/agent_core/test_abort_steer.py -v
pytest backend/tests/agent_core/test_max_turns.py -v
pytest backend/tests/agent_core/test_convert_to_llm.py -v

# 端到端（接 P0 notemeld-ai + 真实 deepseek API）
pytest backend/tests/agent_core/test_e2e_demo.py -v

# 回归（应 0 影响）
pytest backend/tests/test_chat_*.py -v
scripts/run_core_regression.sh
```

### B.17 验证方式

- [x] 功能验证：B.16 单测全绿
- [x] 回归验证：现有 chat 测试 0 影响
- [x] 性能验证：单轮循环 + 空工具 ≤ 10ms；100 条消息 transform_context/convert_to_llm ≤ 2ms
- [x] 真机验证：N/A（P1 无 UI，P2 才有真机）

---

## 执行顺序总结

按 A.1 任务号 T1 → T16 顺序执行。**P0 notemeld-ai 必须先完成并跑通**才能开始 T7（loop.py 依赖 notemeld-ai 的 Models.stream）。

T7-T8 是核心难点，建议先写测试（T9-T13）再写实现（红绿 TDD）。T14 端到端测试需要真实 deepseek API key 配置。

**用户确认本 Spec 后，等 P0 完成即可开始执行 T1。**

---

## 执行顺序总结（P0 + P1 全局视图）

```
P0 notemeld-ai（T1→T14）
    ↓ 完成并跑通
P1 notemeld-agent-core（T1→T16）
    ↓ 完成并跑通
（后续 P2-P3 notemeld-agent / P4-P5 知识看板待用户开启）
```

P0 与 P1 串行（P1 依赖 P0 的 Models）；P0 内部任务可并行（T2/T3/T4/T5 互不依赖）；P1 内部任务可并行（T2/T3/T4 互不依赖）。
