# Agent approval 暂停与恢复验证证据

Canonical Requirement：`docs/requirements/2026-08-19-agent-approval-resume.md`

## 通过

- `RUSTUP_TOOLCHAIN=stable PYTHON_BIN=<isolated-python> ./scripts/test-sdk.sh`（独立 SDK）：Rust workspace 98 passed；Python binding 7 passed；包含 approval pause/approve/deny、unknown/duplicate/terminal、cancel 和同 Session native 并发。
- `PYTHONPATH=backend <isolated-python> -m pytest backend/tests/agent_host -q --timeout=30`：98 passed，5 skipped；skip 原因为当前环境未安装 standalone SDK wheel，对应 native approval 纵向由 SDK ABI contract 覆盖。
- `cd frontend && pnpm test:contracts`：通过。
- `cd frontend && pnpm build`：通过；仅有既有 lottie `eval` 与 chunk-size warnings。
- `<isolated-python> -m compileall -q backend/app`：通过。

## 基线失败与未覆盖风险

- 核心迁移组合回归：32 passed，1 failed。失败为既有 `test_export_service_writes_structured_package` 未把测试临时 `static/screenshots/shot-1.jpg` 打入导出包；在 `main` 同一测试复现，和本需求修改文件无交集，因此未做无关修复。
- 未安装发布形态 standalone wheel，NoteMeld 的 5 个真实 artifact ToolScheduler integration tests 被 skip；SDK 自身真实 C ABI 测试已经验证 resolve 会唤醒 native runtime，但发布 wheel 的产品纵向仍应在 artifact CI 再跑。
- 不承诺进程崩溃后恢复 native approval 栈帧；重启按既有 recovery 将非终态 Turn 标为 `interrupted`。
