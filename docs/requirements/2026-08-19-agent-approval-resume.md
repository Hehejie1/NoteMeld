# Agent approval 暂停、持久化与跨入口恢复

日期：2026-08-19
作者 / Agent：Codex（doc-driven）
状态：Implemented
关联 Change Spec：`docs/system/change-spec-agent-approval-resume.md`

## 原始意图与背景

独立 `notemeld-agent-sdk` 已声明 approval 事件和控制 ABI，但 `notemeld_agent_resolve_approval` 仍返回 unsupported，导致危险工具无法在同一 native Turn 上真正暂停和恢复。NoteMeld 已有 Conversation、`agent_turns`、`agent_events`、Agent v1 HTTP、SSE、Web/Tauri 和 CLI 单一入口，本需求必须打通这些现有边界，不能新建第二套 Agent loop 或回退 legacy runtime。

## 目标结果

- SDK 在需要审批的工具调用前发出 `approval.required` 并暂停原 Turn。
- approval 进入 Conversation → Turn → Event 统一数据链；`waiting_approval` 与 `running` 状态和对应事件同事务写入。
- `POST /api/agent/v1/approvals/{approval_id}` 的 approve/deny 原子唤醒同一 native runtime；拒绝不得执行受保护工具。
- UI 和 CLI 都可消费、处理和重放同一暂停 Turn；CLI 可从另一入口 resolve 后继续该 Turn。
- 同一 Session 在 SQLite 和 native runtime 两层都不能同时存在两个活动 Turn。
- 非法决定、未知 approval、重复 resolve 和已终态 Turn 返回稳定、脱敏错误。

## 非目标

- 不在 NoteMeld 重写模型→工具→模型循环。
- 不新增 approval、Session 或 Message 第二套表。
- 不恢复进程崩溃后已经丢失的 native 栈帧；重启继续沿用 `interrupted` 恢复规则。
- 不修改 Note、Wiki、上传、迁移或 MCP 业务语义。

## 当前系统事实

- Session 复用 `conversations`；Turn/Event 使用 `agent_turns` / `agent_events`；消息历史使用 `conversation_messages`。
- Web、Tauri、CLI 都只走 `/api/agent/v1`，`AgentSdkHost` 是进程级 native runtime owner。
- SDK 已有 `agent-approval` oneshot manager和 approval schema，但 core loop、FFI registry 和 Python binding 尚未完整接线。
- Host 的固定 30 秒 wait 会把长 approval 暂停误判为执行失败。
- 只读产品能力可以明确标为 safe；未知或危险能力必须默认需要审批。

## 用户故事

- 作为 UI 用户，我能批准或拒绝 Agent 的受保护操作，并继续看到同一 Turn 的后续事件。
- 作为 CLI 用户，我能交互处理 approval，或用 approval/turn id 从另一入口恢复同一暂停 Conversation。
- 作为开发者，我能依赖稳定 ABI/HTTP 错误区分未知、非法、重复和已终态请求。

## 验收标准

1. GIVEN 模型请求危险工具，WHEN approval policy 命中，THEN SDK 发出 `approval.required`，Turn 为 `waiting_approval`，工具尚未执行。
2. GIVEN pending approval，WHEN approve，THEN resolve 返回成功且原 native Turn 执行工具并继续模型循环。
3. GIVEN pending approval，WHEN deny，THEN工具不执行，原 call id 的拒绝 ToolResult 进入下一轮模型并正常结束或返回拒绝结果。
4. GIVEN invalid/unknown/duplicate/terminal resolve，WHEN 调用 ABI 或 HTTP，THEN 返回稳定且脱敏的不同错误。
5. GIVEN UI 与 CLI 指向同一 Conversation/Turn，WHEN 任一入口 resolve 并从 sequence 重放，THEN另一个入口可继续同一事件链。
6. GIVEN 同一 Session 已有活动 Turn，WHEN并发提交第二 Turn，THEN SQLite 和 native 两层至少一层稳定拒绝，且不会双执行。
7. GIVEN全仓搜索与契约测试，THEN NoteMeld 没有新增 Agent loop，也没有 legacy fallback。

## 约束、边界与冲突检查

- approval 事件不得包含工具原始秘密参数、Provider payload、凭证或本地路径。
- cancel、timeout、resolve、terminal 并发只能产生一次决定和一个 Turn 终态；重复请求由有界 tombstone 稳定分类。
- `product-rules.md`：符合“统一 Agent v1、SDK 唯一 loop、同 Session 单活动 Turn”。
- `data-model.md`：只扩展已有非终态值和事件，不新增表或迁移。
- `api-inventory.md`：保留 `decision` 与 `approved: bool` 兼容请求，只增强真实恢复和错误语义。
- `known-pitfalls.md`：重点防止 HTTP 假成功、Host 第二 loop、进程内 Session 事实源、30 秒暂停误失败和事件/状态分裂。
- 开放问题：无阻塞问题。

## 关联执行文档

- Plan：`docs/superpowers/plans/2026-08-19-agent-approval-resume.md`
- Spec：`docs/superpowers/specs/2026-08-19-agent-approval-resume.md`
- 验证证据：`docs/superpowers/tests/2026-08-19-agent-approval-resume.md`
