# Agent approval 暂停与恢复实施计划

日期：2026-08-19
状态：Completed
Canonical Requirement：`docs/requirements/2026-08-19-agent-approval-resume.md`
Change Spec：`docs/system/change-spec-agent-approval-resume.md`

## 任务与依赖

1. 审计 SDK approval/core/FFI、NoteMeld Host/Store/Router、UI/CLI 与现有测试，冻结真实断点。
2. 在 SDK core loop 接入 approval gate、等待、approve/deny/cancel/timeout，并保持原 ToolScheduler 和消息顺序。
3. 在 FFI runtime 共享 approval manager，实现 resolve ABI、Python binding、声明文件和同 Session native 互斥。
4. 在 NoteMeld 将 approval.required/resolved 与 Turn 状态同事务投影，映射稳定 HTTP 错误，长暂停使用有界轮询。
5. UI 在原 SSE 上提交决定；CLI 按帧读取并支持交互 resolve 及 `--approve/--deny --turn` 跨入口接续。
6. 补 SDK core/ABI、Host/Router/Store/CLI、前端契约测试，同步 system 文档。
7. 运行 Rust workspace、Python binding、Agent Host、前端 contract/build、compileall 和核心回归，审阅 diff 后分别提交两个仓库。

## 验收映射

- Requirement 1–3：Tasks 2–4，SDK `approval_resume` 与 ABI native roundtrip。
- Requirement 4：Tasks 3–4，ABI/Host/Router typed error tests。
- Requirement 5：Tasks 4–5，Event replay、UI handler、CLI same-turn continuation tests。
- Requirement 6：Tasks 3–4，FFI concurrent session 与 Agent Store transaction tests。
- Requirement 7：Tasks 4–7，route cutover、legacy-zero 与源码搜索。

## 风险与回滚

- 风险：resolve/cancel/timeout 竞态、tombstone 无界、等待线程误超时、事件 sequence 冲突、SDK artifact 漂移。
- 防线：oneshot 原子消费、有界 settled registry、30 秒 timeout 仅轮询、状态+事件同事务、ABI manifest/header/binding 契约测试。
- 回滚：SDK 与 NoteMeld 两仓库分别回滚对应提交；无 SQLite migration，暂停 Turn 在重启后按既有规则进入 `interrupted`。
