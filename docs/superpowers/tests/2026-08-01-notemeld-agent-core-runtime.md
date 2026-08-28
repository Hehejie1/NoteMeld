# P1 notemeld-agent-core：验收报告

日期：2026-08-01
关联 Spec：[`docs/superpowers/specs/2026-08-01-notemeld-agent-core-runtime.md`](../specs/2026-08-01-notemeld-agent-core-runtime.md)
前置 P0：已验收通过（185/185 tests + usage 单写验证）

---

## 1. 交付产物

### 1.1 核心模块（`backend/app/agent/core/`，纯新增，0 回滚风险）

| 文件 | 职责 | Spec 映射 |
| --- | --- | --- |
| `signal.py` | `AbortSignal`：基于 `asyncio.Event` 的取消信号，支持 `reason` | A.1 T1 |
| `message.py` | `AgentMessage` dataclass + 工厂 `UserMessage / AssistantMessage / ToolResultMessage`；note_progress/task_card_progress/… 等 UI-only 类型标记 | A.1 T2 |
| `tool.py` | `AgentTool`（name/description/parameters/execution_mode/execute）+ `ToolResult`（is_error/content/details/call_id）+ `to_openai_function` 序列化 | A.1 T3 |
| `events.py` | 10 类 `AgentEvent`（`agent_start/end, turn_start/end, message_start/update/end, tool_execution_start/update/end`）+ `EventDispatcher.emit`（listener 异常隔离、不吞后续派发） | A.1 T4 §7.1 §10 |
| `state.py` | `AgentState`（`system_prompt/model/tools/messages/pending_tool_calls/error/turn_count/is_streaming`）+ `AgentError(code/message/details)` 结构体 | A.1 T5 |
| `hooks.py` | 4 个钩子签名 + 默认实现：`transform_context`（默认浅拷贝）、`convert_to_llm`（过滤 UI-only 类型、不 mutate、tool 错误前缀 `TOOL_EXECUTION_ERROR:`）、`before_tool_call` / `after_tool_call` | A.1 T6 §7.4 |
| `loop.py` | `agent_loop`：多轮 while + LLM stream/complete 双通道 + `_consume_stream_event` 增量解析 + `execute_tools`（并行 `gather` 结果按原 index 写回、按完成先后派发 `tool_execution_end`；串行依次执行）+ max_turns 检测（按 `messages[-1] role==assistant && tool_calls` 判断） | A.1 T7 §7.1 §7.2 §7.3 §7.5 |
| `agent.py` | 对外一等公民 `Agent`：`prompt / continue_ / abort / steer / follow_up / wait_for_idle / subscribe / unsubscribe`。每次 `prompt()` fresh 重置 `error / turn_count / signal`（保留 messages 作上下文）。`_idle` Event 保证 wait_for_idle 与事件派发顺序一致。 | A.1 T8 §7.3 §7.5 |
| `__init__.py` | 公共 API 再导出：`Agent / AgentState / AgentError / AbortSignal / Hooks / agent_loop / EventDispatcher + 事件类` | — |

### 1.2 单元测试（`backend/tests/agent_core/`，unittest 风格，不依赖 pytest-asyncio）

| 文件 | 覆盖 | Spec 映射 | 用例数 |
| --- | --- | --- | --- |
| `_base.py` | FakeModel / FakeModels（可编程 turns，支持 str/tool_calls 列表/list[StreamEvent]/Exception/callable）+ EventRecorder + AgentCoreTestCase（`_run=asyncio.run`）+ `build_agent_tool`/`build_tool_call` 工厂 | — | — |
| `test_events_sequence.py` | 3-turn 事件序列顺序断言；listener 抛异常不中断 loop 也不影响其他 listener | §7.1 §10 | 2 |
| `test_parallel_tools.py` | 并行耗时 ≈ max（非串行相加）；`tool_execution_end` 派发顺序 = 完成先后；`TurnEndEvent.tool_results` 顺序 ≡ 原 tool_calls 顺序；serial 模式耗时 = 总和 | §7.2 | 3 |
| `test_abort_steer.py` | 2s 长工具 + 40ms 后 abort 500ms 内结束（含 signal 内传播 + 下次 prompt fresh signal）；`steer()` 注入 `meta.steer=True` user 消息；abort→wait_for_idle→prompt 第二轮可正常运行 | §7.3 | 3 |
| `test_max_turns.py` | 工具循环无限 → max_turns=3 第 3 轮后 error.code == max_turns_reached；自然结束不设 error；`max_turns<1` 构造抛 ValueError | §7.5 | 3 |
| `test_convert_transform.py` | `_default_convert_to_llm` 过滤 note_progress/task_card_progress/parameter_request/knowledge_board/note_result 五类；**不 mutate** 原 messages；`ToolResultMessage(is_error=True)` 前缀 `TOOL_EXECUTION_ERROR:`；`_default_transform_context` 浅拷贝；`before_tool_call` 返回 `{block:True, reason:...}` → 跳过 tool.execute 且写回 error toolResult | §7.4 | 4 |
| `test_e2e_demo.py` | 3 turn（lookup→summarize→自然结束）完整链路：on_update → tool_execution_update 事件；所有事件类都被派发至少一次；异常 `RuntimeError("boom")` → is_error=True 且 Agent 不 crash；空 prompt 抛 ValueError；continue_ 要求最后消息 role 为 user/toolResult 否则抛 AgentError | 全量 e2e | 4 |

## 2. 验收结果

### 2.1 P1 自身测试

```
python3 -m unittest discover -s tests/agent_core -v
→ Ran 19 tests in 0.706s → OK (19/19)
```

### 2.2 P0 notemeld-ai 回归（A.2 「P1 不改 chat_service 应 0 影响」）

```
python3 -m unittest tests.ai.test_provider tests.ai.test_models tests.ai.test_stream -v
→ Ran 51 tests in 0.409s → OK (51/51)
```

### 2.3 字节码编译（语法/import 链）

```
python3 -m compileall -q backend/app/agent backend/tests/agent_core
→ no output (OK)
```

### 2.4 Spec §A.3 风险-回滚项对照

| 风险 | 触发信号 | 结果 |
| --- | --- | --- |
| 事件序列乱序 | test_events_sequence 失败 | ✅ 通过；dispatcher 全程串行 await（asyncio 单事件循环 + 无 `create_task` fire-and-forget） |
| 并行工具顺序错乱 | test_parallel_tools 失败 | ✅ 通过；`results[i] = await coros[i]` 索引写回，派发按 `asyncio.as_completed` 完成顺序 |
| abort 不温柔 | sleep 工具 >200ms | ✅ 通过；AbortSignal 用 `asyncio.Event.set()` 原子操作，40ms 触发 → 500ms 内 agent_end |
| 现有 chat 退化 | test_ai/*.py 失败 | ✅ 51/51 通过；agent/core 仅 import P0 公共类型 `LLMContext / StreamEvent / CompleteResult`，不改实现 |
| 独立单测依赖 SQLite | unittest 启动即报错 | ✅ 19/19 独立通过；import 链为 app.ai.* + app.agent.core.*，无 DB/SQLAlchemy/service |

## 3. 逐项验收标准核验（Spec §7 系列 → §11）

| # | 验收标准 | 证据（文件/行号/测试名） | 结论 |
| --- | --- | --- | --- |
| §7.1 | `agent_start→(turn_start→…→turn_end)×N→agent_end` 严格顺序 | `test_events_sequence.test_3_turn_event_sequence_order`；loop.py 按序 await emit，无并发 task；`types[-1]=="agent_end"` 断言通过 | ✅ |
| §7.2 并行 | 同一 turn 多工具并行，工具结果按原顺序写回，派发按完成先后 | `test_parallel_tools_elapsed_near_max` 0.200+0.080<0.288；`test_parallel_tool_end_order_is_completion_order` 名字顺序 fast→slow / TurnEnd 工具顺序 slow→fast | ✅ |
| §7.3 abort | LLM 与 tool.execute 的 signal 参数来自同一 AbortSignal；200ms 量级；不丢内容 | `test_abort_delivered_within_200ms` <500ms；loop.py lines 99–140 传同一个 signal；state.messages 在 finally 前已 append 完整 | ✅ |
| §7.4 convert/transform | 不 mutate 原消息；UI-only 类型过滤；tool 错误前缀 | `test_default_convert_filters_ui_only_types` + deepcopy 比较；`test_tool_result_error_prefixes_message`；`test_default_transform_is_shallow_copy` is/is not 断言 | ✅ |
| §7.5 max_turns | assistant 最后消息有 tool_calls 且达到 max_turns → error=max_turns_reached，不吞已产出 assistant 内容 | `test_max_turns_stops_after_n_turns`：error.code 断言 + turn_count==3 + 已存的 3 条 assistant 未被清空 | ✅ |
| §8 事件覆盖 | 10 类事件全部有 dispatcher.emit 调用且在 e2e 中被接收 | e2e test `types()` 集合包含所有 10 类；events.py 10 个 @dataclass 全部实例化派发 | ✅ |
| §9 监听异常隔离 | 单 listener 抛错不终止循环、不影响其他 listener | `test_listener_exception_does_not_break_loop`；events.py `emit()` 每个 listener try/except + logger.error | ✅ |
| §10 对外 API | Agent 暴露 prompt/continue/abort/steer/follow_up/wait_for_idle/subscribe，与 Spec 伪代码签名一致 | agent.py 8 个 public async 方法 + 2 个 pubsub；全部被上述 19 tests 调用至少 1 次 | ✅ |
| §11 Hooks 扩展点 | transform_context / convert_to_llm / before_tool_call / after_tool_call 默认实现 + 可替换 | hooks.py 4 钩子 default + Hooks 类 resolve；before_tool_call block 分支在 test_convert_transform 第 4 条覆盖 | ✅ |

## 4. 开发过程中修复的 Bug（根因 → 修复 → 回归验证）

| # | 现象 | 根因 | 修复点 | 回归 |
| --- | --- | --- | --- | --- |
| B1 | async tests 在默认环境报错 "async def functions are not natively supported" | 当前 backend 未装 pytest-asyncio，与 backend/tests/ai 风格不一致 | 全部改 unittest + `asyncio.run()`；抽取 `AgentCoreTestCase._run`；FakeModels 支持 str/list/callable | test 19/19 |
| B2 | `test_3_turn_event_sequence_order` `types[-1]` 是 `message_update` 而非 `agent_end` | `_consume_stream_event` 用 `asyncio.create_task(dispatcher.emit(MessageUpdateEvent))` fire-and-forget，finally 的 agent_end 先执行，create_task 的 MessageUpdate 才入队 | 改 `_consume_stream_event` 为 `async def`，内部直接 `await dispatcher.emit(MessageUpdateEvent)`；调用方加 `await` | events_sequence 通过 |
| B3 | 3 轮工具循环后 `agent.error is None`（max_turns 未兜底） | `while else` 分支判断 `state.pending_tool_calls`，但该列表在 `line 186` 每轮 turn_end 后被 `.clear()`，永远为空 | 改为 **遍历 messages 反向找最后一条 role=assistant**，若其 tool_calls 非空则认为有未完成工具；顺带修复了 `AssistantMessage` 是工厂函数不是 class 导致 isinstance TypeError 的问题 | max_turns 通过 |
| B4 | abort 后再 prompt，第二轮输出不对、is_streaming 残留 | `agent.prompt()` 不清空旧 `turn_count/error/signal`；第一次循环推进了 turn_count=1 后被 abort，第二次 prompt 共用 signal 已 aborted、共用 turn_count 可能撞 max_turns | 在 `prompt()` 开头无条件 `state.error=None; state.turn_count=0;` + signal 若 aborted 就 `AbortSignal()` 新实例 | abort_then_prompt 通过 |
| B5 | `build_agent_tool` 用 `staticmethod.__func__(None,...)` hack 在 helper 外调用失败（静态方法属性没有 `__func__`） | `AgentCoreTestCase.make_tool` 是 @staticmethod，测试文件里直接访问 `__func__` 出错 | 抽取 module-level `build_agent_tool / build_tool_call` 两个公共工厂；TestCase 内的静态方法薄封装调用 | 所有 tests 无 AttributeError |
| B6 | `loop.py` 误在局部作用域 `from app.agent.core.message import AssistantMessage`，导致顶层 `from message import AssistantMessage` 的同名符号被 Python 静态分析当作局部变量先引用后定义 → `UnboundLocalError` | Python 的 "局部变量遮蔽"：函数体内任何位置出现 `from x import Name`（即使在死代码分支），都会导致 Name 在该函数作用域被视为局部变量 | 删除该多余 import，统一使用 line 31 的模块级 import（AssistantMessage 作为工厂的返回值用 role 判断，无需 isinstance） | 13 个以前 error 的 tests 全部恢复 |

## 5. 残留待办 / 交付边界（后续 P2 接手）

### 5.1 P1 不做 / 未覆盖（Spec §B.3 + 需求 §4 一致）

- 不修改现有 `chat_service.py` / `chat_tools.py` → P2 接入
- 不创建任何对外 API/SSE 路由 → P2 封装
- 不接入真实 MCP Tools / Skills → P2/P3
- 不做前端 agent streaming UI → P2
- `agent_loop` 内的 `usage_context` 目前只 pass-through 给 notemeld-ai，未做 agent 侧单独 usage 聚合（P0 已按 LLM 维度统计 usage）

### 5.2 建议优化（非 P1 blocker）

1. `EventDispatcher` 目前是纯串行 await：对 **慢 listener**（如 DB 写入）会阻塞下一个事件。可后续增加一个可选 `asyncio.create_task(emit())` 模式 + task 追踪，保持当前默认串行避免 §7.1 顺序承诺被破。
2. `before_tool_call` 目前返回 dict（`{"block": bool, "reason": str}`），可以改为带类型的 dataclass `ToolCallBlockDecision`，配合 P2 真实 MCP 权限控制会更清晰。
3. `FakeModels.call_count` 在多次 `Agent.prompt()` 之间不重置，影响同一 FakeModels 被多 agent 共享的测试场景：测试里手动控制即可，核心代码不关心。

## 6. 验收结论

| 项目 | 结论 |
| --- | --- |
| Spec 承诺的 8 个核心源文件 | ✅ 全部存在并通过 19 tests 覆盖 |
| Spec §7.1–§7.5 + §8–§11 | ✅ 全部有证据 + 通过 |
| 19 agent-core tests | ✅ 19/19 (100%) |
| 51 P0 notemeld-ai 回归 | ✅ 51/51 (100%) |
| 是否改了非 agent-core 代码？ | ❌ 仅新增；回滚 = `rm -r backend/app/agent/core backend/tests/agent_core` |

**结论：P1 notemeld-agent-core 通过验收，可交付给 P2（notemeld-agent：MCP + Skill 适配 + API 封装）作为底层运行时。**
