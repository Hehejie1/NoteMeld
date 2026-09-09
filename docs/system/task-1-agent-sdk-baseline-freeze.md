# Task 1 任务基线冻结记录

> 历史基线记录。2026-08-18 起，NoteMeld 不再跟踪 `agent-sdk/` 源码；现行唯一 SDK 源码仓库为 `/Users/hehejie/ai/notemeld-agent-sdk`。以下差异统计仅用于回溯，不代表当前目录结构。

创建时间：2026-08-17

本文件用于 `Task 1`：冻结双仓库基线与能力边界，记录当前可复现差距。

## 1. 仓库基线

- NoteMeld 主仓库分支：`task1-9-agent-sdk-cutover`
- 独立仓库：`/Users/hehejie/ai/notemeld-agent-sdk`
- 独立仓库 HEAD：`d3ac41b`（`fix(ollama): support native driver payload and reliable defaults`）
- Task 0 冻结项：
  - 目标版本边界：`SDK_VERSION=0.1.0`、`Schema=1`（当前实际状态）
  - Rust workspace 测试统计：当前仅记录为既有历史结果（后续 Task2+执行时会重跑并写入可复验命令）
  - 依赖链路：独立仓库与 NoteMeld 嵌入版共享同一套 Rust crates 源码集合，未新增外部依赖路径。

## 2. NoteMeld 与独立仓库 `agent-sdk/` 文件差异（跟踪文件）

- `NoteMeld agent-sdk` 跟踪文件：`76` 个
- `notemeld-agent-sdk` 跟踪文件：`85` 个
- 仅额外存在于独立仓库（非嵌入）:
  - `.gitignore`
  - `README.md`
  - `bindings/python/notemeld_agent_sdk/ollama_cli.py`
  - `bindings/python/tests/test_ollama_cli.py`
  - `docs/verification/2026-08-17-local-validation.md`
  - `pyproject.toml`
  - `scripts/ollama-agent.sh`
  - `scripts/test-python.sh`
  - `scripts/test-sdk.sh`

说明：以上条目主要是独立仓库用于脚本/CLI/验证和开发文档的补齐，不表示功能差异边界的绝对事实来源；后续 Task9/Task10 会整理统一入口后再统一处理。

## 3. Task 1 需新增的失败契约（当前基线）

已新增基线测试文件：`backend/tests/agent_host/test_agent_sdk_cutover_baseline_contracts.py`

当前未实现/待实现的能力已用 `xfail` 标记固定：

1. 本地历史复用
   - `NativeAgentExecutor.run_sync` 当前提交请求未携带历史上下文字段。
   - 现状：`submit_turn({"input": {"text": ..., "attachments": [], "context_refs": []}})`
   - 期望：`submit_turn` 请求应携带会话历史（或与会话模型一致的历史 DTO）。

2. turn 事件流 `live` 能力
   - `/agent/v1/turns/{turn_id}/events` 当前只做数据库回放，不订阅 `EventBroker.subscribe`。
   - 现状：新事件写入后不会推给已打开 SSE。
   - 期望：在回放历史后持续订阅新事件。

3. steer 执行链
   - `/agent/v1/turns/{turn_id}/steer` 当前直接返回 `409 steer_unsupported`。
   - 现状：中途输入无法进入当前 Turn。
   - 期望：支持注入下一步可执行的 steer，并返回有效 ack。

4. approval 解析链
   - `/agent/v1/approvals/{approval_id}` 当前返回 `501 approval_not_ready`。
   - 现状：未接入 Rust turn 的审批 wait/resolution。
   - 期望：支持 approval 的挂起、超时、resolve 生命周期。

## 4. 验收前置

- Task 1 完成标记：上述基线测试全部保留为已知失败合同，并在 Task2 之后改写为真实通过标准。
- 下一步执行顺序：先 `Task 2`（Session/Turn/Store）→ `Task 3`（Context）→ `Task 4-7`（Streaming / Control / Approval）→ `Task 8-9`（Binding/CLI）。
