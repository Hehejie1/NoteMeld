# Agent approval 暂停与恢复执行规格

日期：2026-08-19
Canonical Requirement：`docs/requirements/2026-08-19-agent-approval-resume.md`

## SDK 文件与协议

- `crates/agent-approval/src/lib.rs`：pending oneshot、resolved/terminal 有界 tombstone、unknown/duplicate/terminal typed result。
- `crates/agent-core/src/loop.rs`：按 Turn tools descriptor 的 `risk/safe` 决定审批；发 `approval.required/resolved`；approve 进入既有 `execute_tool_round`；deny 生成原 call id 的 `approval_denied` ToolResult。
- `crates/agent-ffi/src/lib.rs`：runtime 共享 approval manager；`notemeld_agent_resolve_approval(handle,id,decision)` 原子唤醒；submit 时按 session_id 拒绝第二活动 Turn；terminal/free 取消 pending approval。
- `bindings/python/notemeld_agent_sdk/runtime.py`、`include/notemeld_agent.h`、`bindings/abi-v1.json`、`bindings/abi-v2.json`、UDL：保持函数签名和错误码同步。
- ABI 错误：`-2 invalid decision`、`-3 unknown`、`-4 duplicate`、`-8 terminal`、`-10 wait timeout`。

## NoteMeld 文件与协议

- `backend/app/agent_host/native_executor.py`：把 approval 事件交给控制事件事务；`waiting_approval ↔ running`；native wait timeout 只重试，不制造 terminal。
- `backend/app/services/agent_store.py`、`agent_host/entry.py`：允许外部 event id/sequence 与状态在一个 SQLite 事务提交。
- `backend/app/agent_host/host.py`：把 native 整数错误映射为脱敏 `ApprovalControlError`。
- `backend/app/routers/agent.py`：兼容 `decision` / `approved`，返回 400 `invalid_approval_decision`、404 `approval_not_found`、409 `approval_already_resolved|approval_turn_terminal`。
- `frontend/.../ChatComposer.tsx`：在原 SSE consumer 中处理 `approval.required` 并调用已有 Agent service。
- `scripts/notemeld-agent.py`：逐帧读 SSE；text 模式交互决策；机器模式输出暂停事件；支持从另一入口 `--approve|--deny APPROVAL_ID --turn TURN_ID` 继续原 Turn。

## 数据与并发

- 不新增 SQLite 表/字段/迁移；approval 事实写入 `agent_events`，当前状态写入 `agent_turns.status`，轻量 UI 投影写入既有 assistant message meta。
- SQLite `BEGIN IMMEDIATE` 继续是产品 Session 单活动 Turn 权威；native runtime 增加同 session_id 活动检查作为 ABI 防线。
- pending approval 只存在于同一进程的 native control plane；持久事件支持客户端重连，不承诺进程崩溃后恢复栈帧。

## 测试命令

```bash
RUSTUP_TOOLCHAIN=stable cargo test --workspace --locked
RUSTUP_TOOLCHAIN=stable cargo fmt --all --check
python3 scripts/test-python.sh
PYTHONPATH=backend .venv-agent-approval/bin/python -m pytest backend/tests/agent_host -q
.venv-agent-approval/bin/python -m compileall backend/app
cd frontend && pnpm test:contracts && pnpm build
scripts/run_core_regression.sh
```

真实 native artifact 可用时，Agent Host ToolScheduler integration tests 不得 skip；否则必须单独记录 skip 原因并以 SDK ABI native tests 覆盖 approval 纵向链路。
