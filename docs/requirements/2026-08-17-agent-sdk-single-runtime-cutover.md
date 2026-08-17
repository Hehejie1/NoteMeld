# Agent SDK 单一运行时与 NoteMeld 正式切换

日期：2026-08-17
作者 / Agent：Codex（doc-driven）
状态：Planned（Requirement / Architecture / Change Spec / Plan / Execution Spec 已完成，等待用户确认；尚未开发）
关联对话 / 任务：用户确认 Agent 核心能力全部收口到独立 `notemeld-agent-sdk`，NoteMeld 不保留历史 Agent 逻辑兼容路径
关联系统文档：`docs/system/current-architecture.md`、`docs/system/product-rules.md`、`docs/system/data-model.md`、`docs/system/api-inventory.md`、`docs/system/known-pitfalls.md`
替代需求：`docs/requirements/2026-08-14-universal-agent-sdk-unified-cli.md`

## 1. 原始需求

用户明确要求：

> Agent 的核心功能全部收口到 notemeld-agent-sdk。

> 当前 NoteMeld 完成接入，并且不兼容历史逻辑，全部以 notemeld-agent-sdk 为准进行适配。

> 先给出能看清应用层、NoteMeld 框架层、Agent SDK 核心能力的最新系统架构；每个名词需要有一句白话说明。

这里的“不兼容历史逻辑”指不保留第二套 Python Agent loop、旧 Agent feature flag、旧 chat-to-Agent 兼容执行路径和静默回滚。它不授权删除历史会话、消息、笔记、Wiki、白板或用户模型配置。

## 2. 背景和问题

- 当前用户：NoteMeld 桌面、网页和 CLI 用户，以及直接使用独立 Agent SDK 的开发者。
- 当前场景：独立 SDK 已有 Rust crates、C ABI、Python/Swift/Kotlin/Harmony binding 和 Ollama 测试入口；NoteMeld 已新增 `/api/agent/v1`、native executor 和前端/CLI 客户端。
- 当前痛点：现有接入仍把 Turn 管理、事件落库、模型选择、取消和终态处理拆在 Python Host 中，同时保留旧 Python Agent Core，形成两个行为事实源。
- 真实断点：当前 native 路径没有向 FFI 传会话历史，ToolDriver 未接入 executor，steer/approval 未实现，HTTP cancel 未调用 native cancel，SSE 不是持续订阅，助手消息没有形成完整的服务器权威持久化闭环。
- 为什么现在做：如果继续在现有过渡层上补功能，UI、CLI、SDK 独立测试和未来移动端会继续出现不同的会话、事件和控制语义。

## 3. 目标结果

1. `notemeld-agent-sdk` 成为 Agent loop、Session/Turn 状态、事件、工具调度、能力发现、取消、steer、审批、上下文组装和错误语义的唯一事实源。
2. NoteMeld 只保留产品框架能力：API/Host、模型 Provider 适配、Note/Wiki/白板/MCP 等产品能力适配、数据库映射、权限与运行生命周期。
3. 桌面、Web、CLI 只作为入口，调用同一个 NoteMeld Agent Host；客户端不直接写 Agent 消息、Turn 或 Event。
4. 独立 SDK 可在不启动 NoteMeld 的情况下用 Ollama 等 Host Driver 实际测试；NoteMeld 产品 CLI 则连接 NoteMeld Host 并共享 NoteMeld 数据。
5. 删除旧 Python Agent 核心和兼容执行逻辑后，源码启动、桌面启动、CLI、MCP、笔记、Wiki、上传、迁移和发布入口继续可用。
6. 历史 Conversation/Message/Note/Wiki 数据继续读取；仅运行逻辑切换，不做破坏性数据清理。

## 4. 非目标

- 不在本阶段开发完整 iOS、Android 或 HarmonyOS NoteMeld 应用。
- 不做跨设备发现、远程 Agent 调用或多主数据库同步。
- 不做 Harbor benchmark 接入；等单一运行时和产品切换完成后单独开始。
- 不把 Note/Wiki/白板/下载/转写等产品业务重写进 SDK。
- 不让 SDK 直接读取 NoteMeld SQLite 表名、FastAPI 对象、React 状态或用户目录。
- 不保留自动切回 Python Agent 的回滚路径。

## 5. 当前系统事实

- 已有 SDK 能力：Rust fixed-loop、版本化事件和错误、ModelDriver、ToolDriver、工具并发与取消、Session 状态机、CapabilityRegistry、reference SQLite store、C ABI、Python/Swift/Kotlin/Harmony binding、artifact 校验和 Ollama smoke CLI。
- 已有 NoteMeld 接入：`backend/app/agent_host/`、`backend/app/routers/agent.py`、`frontend/src/services/agent.ts`、ChatComposer Agent v1 调用和 `notemeld agent` HTTP CLI。
- 当前旧逻辑仍被 `backend/app/agent/agent_service.py`、`sse_bridge.py`、builtin/skill/memory/workspace/MCP 工具模块引用。
- NoteMeld 仓库仍跟踪一份 `agent-sdk/` 源码副本及其构建 workflow；正式目标是只维护独立 `/Users/hehejie/ai/notemeld-agent-sdk`，NoteMeld 仅消费版本化 artifact。
- 当前 SDK 的 core Rust API能接收 history，但 FFI submit path 固定以空 history 执行；独立 Ollama CLI 多轮复用 session_id 但没有真正复用历史。
- 当前 `agent-capabilities`、`agent-session`、`agent-storage` 提供了基础契约，但没有组合进 FFI 的正式 Turn 执行路径。
- 当前 NoteMeld Host 自己维护活动 Turn 和终态，并把 SDK 事件再次包装/落库；这违反单一事实源目标。

## 6. 用户故事

- 作为 NoteMeld 用户，我希望 UI 和 CLI 只是不同入口，以便它们在同一会话中获得完全一致的历史、工具、模型和终态。
- 作为 SDK 使用者，我希望直接启动一个本地模型测试客户端，以便不依赖 NoteMeld 产品也能评估 Agent 核心能力。
- 作为开发者，我希望所有 Agent 行为只在 Rust SDK 中维护，以便桌面、服务端和未来移动端不会分别修复同一个 Agent Bug。
- 作为现有用户，我希望升级只替换运行逻辑而不删除历史知识数据。

## 7. 验收标准

1. GIVEN 仓库完成切换，WHEN 搜索生产代码和仓库目录，THEN 不再存在第二套 Python Agent loop、状态机、事件类型、自动 legacy fallback 或 NoteMeld 内嵌 `agent-sdk/` 源码副本。
2. GIVEN 同一历史会话，WHEN UI 或 CLI 提交新 Turn，THEN SDK 从权威 SessionStore 读取同一历史并将结果写回同一 Conversation。
3. GIVEN 模型返回流式文本和工具调用，WHEN Turn 执行，THEN UI/CLI 实时收到连续 `message.delta/tool.*/turn.*` 事件，并且每个 Turn 只有一个终态。
4. GIVEN 工具调用，WHEN SDK 调用 ToolDriver，THEN NoteMeld capability adapter 可执行 Wiki/Note/Memory/Workspace/Skill/MCP 能力，SDK 负责调度、取消和结果回填。
5. GIVEN危险操作，WHEN策略要求审批，THEN SDK 进入 `waiting_approval`，UI/CLI 可 resolve，超时/拒绝/取消都有稳定事件和终态。
6. GIVEN活动 Turn，WHEN调用 cancel 或 steer，THEN命令到达同一个 native Turn，而不是只修改数据库状态。
7. GIVEN SSE/JSONL 客户端在 sequence=N 断线，WHEN重连，THEN先回放 N 之后持久事件，再持续订阅实时事件直到终态。
8. GIVEN相同 request_id 重试，WHEN Host 重复收到请求，THEN只产生一个 Turn 和一组权威消息，不重复执行模型或工具。
9. GIVEN用户未显式选模型，WHEN创建 Turn，THEN按全局默认模型、用户配置的第一个 fallback、首个可用模型顺序解析；无模型时明确提示设置。
10. GIVEN独立 SDK checkout，WHEN运行 SDK Ollama shell，THEN不启动 NoteMeld 也能进行真正带历史的多轮对话、切换模型并观察统一 AgentEvent。
11. GIVEN NoteMeld 启动，WHEN SDK artifact 缺失或版本不匹配，THEN Agent Host fail-closed 并给出可分类诊断，不静默运行旧 Agent。
12. GIVEN历史会话、笔记、Wiki 和白板数据，WHEN删除旧 Agent 运行代码并升级，THEN这些数据仍可读取，非 Agent 业务入口回归通过。

## 8. 输入 / 输出样例

### NoteMeld 产品入口

```text
React / notemeld agent
  -> POST /api/agent/v1/sessions/{session_id}/turns
  -> SSE /api/agent/v1/turns/{turn_id}/events
```

### 独立 SDK 测试入口

```text
./scripts/ollama-agent.sh
  -> Python Host Driver
  -> native notemeld-agent-sdk
  -> local Ollama
```

### 失败反例

- UI 走 SDK、CLI 走 Python Agent：不允许。
- cancel 只把数据库改为 cancelled，native 模型仍继续运行：不允许。
- SDK 每轮使用空历史，却复用相同 session_id 冒充续聊：不允许。
- SDK 加载失败后自动执行 legacy Agent：不允许。

## 9. 约束

- 平台：Rust 核心继续面向 macOS、Windows、Linux、iOS、Android、OpenHarmony；本阶段产品接入优先完成当前 NoteMeld 桌面/Web/CLI。
- 隐私：Provider Key、MCP credential、Cookie、原始危险工具参数和 Provider payload 不跨事件/日志边界。
- 数据：不删除历史 Conversation、Message、Note、Wiki、Whiteboard、Provider、Model 或 Usage 数据。
- 性能：流式事件使用有界队列和批量 checkpoint；不得每 token 单独开启 SQLite transaction。
- 兼容性：不兼容旧 Agent 执行逻辑和旧 Agent feature flag；保留非 Agent 产品能力及历史业务数据。
- 依赖：NoteMeld 生产运行依赖已构建/发布的 SDK artifact，不以外部源码目录作为正式运行依赖。

## 10. 边界场景

- 无模型：阻断 Turn 并提示设置，不随机调用 Provider。
- SDK 缺失/版本漂移：Agent API fail-closed，非 Agent 诊断接口仍可用。
- 客户端断线：Turn 继续运行；重连回放并续订。
- Host 退出：非终态 Turn 恢复为 interrupted，不伪装成功。
- 工具副作用：request/call id 幂等；重启不自动重放未知完成状态的危险工具。
- 长会话：SDK 上下文策略裁剪 Provider 输入副本，不改写持久历史，并保持 tool call/result 成组。
- 多入口并发：同一 Session 单活动 Turn，不同 Session 可并行。

## 11. 开放问题

无阻塞问题。用户已确认 SDK 单一事实源、不保留旧 Agent 兼容逻辑；历史业务数据保留是产品安全边界。

## 12. 与系统事实的冲突检查

- `product-rules.md`：用户本次明确授权删除旧 Agent 运行能力；源码、桌面、CLI、MCP、迁移、Wiki、上传和打包入口仍必须保留。
- `data-model.md`：Conversation/Message 继续作为产品历史事实源；SDK 通过 Store contract 管理 Turn/Event 语义，不建立第二套会话。
- `api-inventory.md`：Agent v1 成为唯一聊天 Agent API；旧 `/api/chat/free*` 的 Agent 执行兼容在迁移完成后删除并同步调用方。
- `known-pitfalls.md`：必须防止 UI/Host 双写、SDK/Host 双状态机、版本漂移、事件 sequence 断裂、上下文工具对拆散和敏感 payload 泄漏。
- 本地/线上影响：影响 NoteMeld 本地 Host、SQLite Agent 表、前端聊天、CLI、桌面 sidecar 和 SDK artifact 装载；不新增远端数据服务。

## 13. Superpowers 交接

- 是否达到 Planned：是；Requirement、架构、Change Spec、19-Task Plan 和精确 Execution Spec 已形成闭环。
- 实施计划：`docs/superpowers/plans/2026-08-17-agent-sdk-single-runtime-cutover.md`。
- 执行规格：`docs/superpowers/specs/2026-08-17-agent-sdk-single-runtime-execution.md`。
- 下一步：等待用户确认；确认后只从 Plan Task 1 的双仓库基线与失败契约开始，不直接改造生产链路。
- 计划已覆盖验收标准 1–12，以及 SDK 直接 Ollama 多轮、NoteMeld UI/CLI 同会话、取消/审批/工具/SSE/恢复纵向测试。
