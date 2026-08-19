# Agent ToolDriver 产品能力链路执行计划

Canonical requirement: [`../../requirements/2026-08-19-agent-tool-driver-chain.md`](../../requirements/2026-08-19-agent-tool-driver-chain.md)

## 任务与依赖

1. 固化 ToolResult 与错误分类契约。
   - 文件：`backend/app/agent_host/drivers/tools.py`、`backend/tests/agent_host/test_tool_driver.py`
   - 验证：成功/未知/参数/权限/业务/异常均返回稳定 `{call_id, output}`。
2. 收紧 Capability Registry 产品服务边界。
   - 文件：`backend/app/agent_host/capabilities.py`、`backend/tests/agent_host/test_capabilities.py`
   - 验证：三项能力继续调用现有服务；不存在 Note 为业务错误；未知能力 fail-closed。
3. 接通 native driver completion。
   - 文件：`backend/app/agent_host/native_executor.py`、`backend/tests/agent_host/test_native_executor.py`
   - 验证：ABI `result.output` 只承载 ToolResult output；产品失败不终止 SDK loop。
4. 增加真实 SDK scheduler 集成与 Session 隔离测试。
   - 文件：`backend/tests/agent_host/test_tool_scheduler_integration.py`
   - 验证：首轮 tool call → ToolDriver/Registry → ToolResult → 第二轮 model；共享 Host 的两个 Session 不串结果。
5. 同步系统事实并完成回归、review、commit。
   - 文件：`docs/system/current-architecture.md`、`api-inventory.md`、`known-pitfalls.md`、验证证据。

## 风险与回滚

- 保持 SDK ABI v1，不修改 Rust artifact。
- 只实现现有 schema 所需校验子集，避免引入新运行依赖。
- 回滚只需回退本提交；无数据迁移。
