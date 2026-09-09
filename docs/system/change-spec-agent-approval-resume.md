# Agent Approval 暂停、持久化与跨入口恢复 Change Spec

更新时间：2026-08-19

## 0. 预检查

- [x] 已阅读 `AGENTS.md`、`CLAUDE.md` 与五份必读系统文档
- [x] 已阅读 `docs/system/change-spec-template.md`
- [x] 已搜索 Agent 前端、Router、Host、SQLite store、CLI、测试与独立 SDK crates
- [x] 已确认已有 approval schema、HTTP 入口和 binding 壳层，但 native resolve 固定返回 `FFI_UNSUPPORTED`
- [x] 已确认影响本机 SQLite、独立 SDK artifact、源码/桌面/CLI 共用入口，不影响远端服务

## 1. 当前系统现状

- 相关模块：独立 SDK 的 `agent-approval`、`agent-core`、`agent-ffi` 和 Python binding；NoteMeld 的 `agent_host`、Agent Router、`agent_store`、ChatComposer 与产品 CLI。
- 相关入口：Web/Tauri/CLI 均经 `/api/agent/v1` 进入共享进程级 `AgentSdkHost`。
- 相关数据：Conversation 是 Session；`agent_turns` 保存 Turn；`agent_events` 保存有序事件；消息历史继续保存在 `conversation_messages`。
- 相关 API：已有 `POST /api/agent/v1/approvals/{approval_id}`，但只能调用一个永远返回 unsupported 的 native ABI。
- 当前行为：SDK event schema 已声明 `approval.required`、`approval.resolved` 和 `waiting_approval`，`agent-approval` 也有 oneshot manager；canonical loop 未使用它们，FFI 没有 pending approval registry，Host 的 30 秒 wait 会把真正的长暂停误判成失败。
- 当前限制：UI 没有处理 approval event；CLI 以整段 `response.read()` 等终态，无法在暂停事件后交互；同 Session 并发门禁仅由 NoteMeld SQLite 保证，native submit 自身未保护。

## 2. 本次目标

- SDK 在危险工具调用前生成 approval、发出 `approval.required` 并暂停同一 Turn；approve 后调用原工具并继续 loop，deny 后写入稳定拒绝 ToolResult 并由模型继续或结束。
- native runtime 持有 pending approval，`notemeld_agent_resolve_approval` 原子完成一次决策并唤醒原 Turn。
- NoteMeld 将 approval 事件与 `waiting_approval/running` 状态原子写入同一 Conversation→Turn→Event 数据链，SSE 可重放。
- HTTP 对非法决策、未知 approval、重复 resolve 和已完成 approval 返回稳定、脱敏的错误 code。
- UI 可从同一 SSE 事件直接批准/拒绝；CLI 可在同一 Turn 暂停点交互决策并继续消费事件。
- native 与 SQLite 两层都阻止同一 Session 同时存在/恢复两个活动 Turn。

## 3. 明确不做

- 不在 NoteMeld 重写模型→工具→模型 loop，不新增 legacy/Python runtime fallback。
- 不新增第二套 Session、Message 或 approval 数据库表；approval 的持久事实使用既有 `agent_events`，当前 pending 状态使用 `agent_turns.status`。
- 不改变普通 Note、Wiki、MCP、学习空间链路，不引入远端 approval 服务。
- 本阶段不承诺进程崩溃后恢复 native 栈帧；Host 重启仍按现有规则将非终态 Turn 标为 `interrupted`。持久化保证客户端断线、刷新或 UI/CLI 切换后可从同一进程中的暂停 Turn 和事件日志继续。

## 4. 冲突分析

- 产品规则：一致。Web/Tauri/CLI 继续只走 Agent v1，同一 Conversation 只有一个活动 Turn。
- 数据模型：不新增表；扩展非终态 `waiting_approval`，approval payload 只进入既有事件表。
- API：保留既有请求兼容形式 `decision` / `approved`，只补稳定错误和真实恢复语义。
- known pitfalls：不引入进程内 Session map；native 只维护运行中 Turn/approval 控制状态，SQLite 仍是产品并发与重放事实源；Host 不执行第二套 Agent loop。
- 运行入口：源码、桌面和 CLI 共用 wheel/native ABI；需同步 ABI manifest/header/binding 与打包契约测试。
- 发布/迁移：SQLite 无 schema migration；发布必须携带更新后的 SDK wheel/native library。

## 5. 影响范围

- SDK：`agent-approval` 生命周期与稳定 resolve 结果；`agent-core` approval gate；`agent-ffi` runtime registry/ABI/Python binding/测试。
- NoteMeld 后端：Host 错误映射、executor 长暂停等待与 approval 事件状态投影、Router、store/entry。
- 前端：Agent service 错误解析与 ChatComposer approval 交互。
- CLI：暂停帧的增量读取、批准/拒绝后继续同一 Turn。
- 测试：Rust crate/ABI、Python binding、Agent Host、Router、store、CLI、前端 contracts。
- 文档：架构、数据模型、API inventory、known pitfalls。

## 6. 实施方案

### SDK

- 由 `agent-core` 在工具执行前根据 Turn approval mode 与请求内有界工具风险元数据决定是否暂停。
- 复用 `agent-approval` oneshot，不持锁等待；决策 registry 保留有界 tombstone，稳定区分 unknown 与 already-resolved。
- `approval.required` 携带 approval/call/action/risk/summary/deadline；`approval.resolved` 携带最终 decision。
- approve 才把调用交给既有 `execute_tool_round`；deny 生成带原 call id 的安全 ToolResult，保持 canonical messages 与下一轮模型关系。
- FFI runtime 共享 approval manager；resolve ABI 唤醒接续；cancel/free 会取消 pending approval；native submit 按 session_id 拒绝第二个活动 Turn。

### NoteMeld Host/API

- executor 对 `approval.required/resolved` 使用 store 的原子事件+状态更新，其他事件沿用 append；暂停期间循环执行有界 native wait，不把 timeout 当终态。
- Host 把 native FFI code 转换为稳定内部异常；Router 映射为 `invalid_approval_decision`、`approval_not_found`、`approval_already_resolved`、`approval_turn_terminal`。
- 只读 NoteMeld capability 标记为 safe；未知/危险能力默认需要 approval。

### UI/CLI

- ChatComposer 收到 `approval.required` 时展示确定性确认并调用既有 approval API，原 SSE 保持消费。
- CLI 逐帧读到 approval 后立即让用户 approve/deny，提交后以当前 sequence 继续同一 Turn；JSON/JSONL 保持机器可读。

## 7. 数据变更

- SQLite 表/字段：无新增。
- 状态：`agent_turns.status` 新增既有 SDK schema 已定义的非终态值 `waiting_approval`；resolve event 后回到 `running`。
- 文件结构/迁移/脏数据：无。
- 回滚：旧代码仍能读取 approval 事件为普通事件；暂停中的 Turn 回滚/重启后按既有 recovery 变为 interrupted。

## 8. 接口变更

- 修改 `POST /api/agent/v1/approvals/{approval_id}`：成功结构保持；补稳定 400/404/409 错误。
- SSE 增加已在 schema v1 中声明的 `approval.required` / `approval.resolved` 实际事件。
- ABI v1 同名 resolve 函数从 unsupported 壳层变为可用控制面，不改函数签名。
- 兼容 `approved: bool` 和 `decision: approve|deny`。

## 9. UI/交互变更

- approval 时 Turn 保持非终态，用户可批准或拒绝；批准后流继续，拒绝后模型获得拒绝结果。
- 请求失败显示稳定安全文案；不展示原始工具参数、Provider payload 或凭证。
- Web 与 Tauri 使用同一 ChatComposer 行为。

## 10. 测试方案

- SDK：approval 创建/暂停事件、approve 继续、deny 结果、unknown、duplicate、terminal/cancel、同 Session 并发。
- ABI/Python：真实 resolve 返回值和 runtime 恢复，manifest/header/UDL/binding 同步。
- NoteMeld：store 原子状态事件、Host resolve code、Router 错误、executor 暂停不超时、跨 UI/CLI 对同一 Conversation/Turn resolve。
- 前端/CLI：approval 调用与流继续契约；CLI 帧读取不等终态才返回。
- 回归：`cargo test` 相关 crates、`pytest backend/tests/agent_host`、`pnpm test:contracts`、`pnpm build`、compileall。

## 11. 验收标准

- [x] 危险工具触发 `approval.required`，Turn 状态为 `waiting_approval` 且事件可重放。
- [x] approve 真正恢复原 native Turn 并继续工具/模型；deny 产生稳定拒绝结果且不执行工具。
- [x] 非法、未知、重复和已结束 approval 有稳定 HTTP/ABI 错误。
- [x] UI 与 CLI 均可对同一 Conversation 中的暂停 Turn 决策并继续。
- [x] 同一 Session 的第二个活动 native/产品 Turn 均被拒绝。
- [x] NoteMeld 无 Agent loop 或 legacy runtime 回退。

## 12. 风险和回滚

- 风险：approval 与 cancel/terminal 并发、重复决策、Host 30 秒 wait、事件序列冲突、客户端断线。
- 防线：oneshot 原子消费+有界 tombstone、cancel select、wait timeout 仅轮询、事件与状态同事务、SSE sequence 重放。
- 回滚：同时回滚 SDK artifact 与 NoteMeld Host/UI 变更；无数据库 migration，历史事件可保留。

## 13. Agent 必答问题

- 影响模块：SDK approval/core/ffi/binding，NoteMeld Host/store/router，UI/CLI 与对应测试/系统文档。
- 类似能力：已有 schema、manager、HTTP/binding 壳层和 SQLite 活动 Turn 门禁；缺少 loop/FFI 真实接线。
- 产品/数据冲突：无；复用 Conversation/Turn/Event，不新增第二事实源。
- known pitfalls：重点防止 Host 重写 loop、进程内 Session map、假成功 ACK、事件状态不同步和 ABI 漂移。
- 本地/线上影响：修改本机 SQLite 的状态/事件值与发布 SDK artifact；不调用线上服务。
- 最小改动：打通既有 approval primitives、在既有 event/store/route/UI/CLI 边界补接线。
- 回归测试：上述 SDK、ABI、Host、Router、store、CLI、前端 contract 与 build。
