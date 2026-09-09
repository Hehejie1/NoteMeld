# Agent ToolDriver 产品能力链路 Change Spec

状态：Implemented
日期：2026-08-19
关联需求：`2026-08-17-agent-sdk-single-runtime-cutover.md`

## 0. 预检查

- [x] 已阅读 `AGENTS.md`、`CLAUDE.md` 和五份 `docs/system/` 必读文档。
- [x] 已阅读 `docs/system/change-spec-template.md`。
- [x] 已搜索 `backend/app/agent_host/`、Capability Registry、产品知识能力服务和 Agent 测试。
- [x] 已核对独立 `notemeld-agent-sdk` 的 `ToolDriver`、`execute_tool_round`、`ToolResult`、FFI driver envelope 和事件协议。
- [x] 已确认不修改本地数据、线上服务、公共 HTTP/MCP 或 approval 流程。

## 1. 当前系统现状

- 相关模块：`backend/app/agent_host/capabilities.py`、`drivers/tools.py`、`native_executor.py`、`drivers/model.py`，以及独立 SDK 的 Rust `agent-tools`、`agent-core`、`agent-ffi`。
- 相关入口：Web/Tauri/CLI 统一提交 `/api/agent/v1` Turn；`NativeAgentExecutor` 把 SDK driver callback 路由到 ModelDriver 或 ToolDriver。
- 相关数据：Conversation history、`agent_turns`、`agent_events`；本次不改 schema 或文件布局。
- 相关 API：不新增或修改公共 API；内部 ABI 仍为 schema v1 的 `model.stream` / `tool.describe` / `tool.invoke`。
- 当前类似能力：`NoteMeldCapabilityRegistry` 已注册 `wiki:search`、`note:search`、`note:read` 并调用现有 Wiki/Note 服务；`NoteMeldToolDriver` 已有薄适配雏形。
- 当前行为：SDK Rust loop 已在模型返回 tool calls 后调用 `execute_tool_round`，把 `ToolResult` 写入 canonical messages 后进行下一轮模型调用。
- 当前限制：NoteMeld adapter 没有稳定的 ToolResult wire contract；同步/异步 registry 描述不统一；参数只做局部手写校验；未知工具和所有 `ValueError` 都被当作 `invalid_input`，其他异常终止 Turn；没有真实 SDK 集成测试证明 ToolResult 回填、第二轮模型调用及多 Session 隔离。

## 2. 本次目标

- SDK ModelDriver 返回 tool call 后，只由 SDK ToolScheduler 调度。
- NoteMeld 只实现产品适配层 `NoteMeldToolDriver`，并通过 `NoteMeldCapabilityRegistry` 调用已有产品能力服务。
- 所有产品成功结果和可恢复产品失败都转换为 SDK `ToolResult` wire shape；FFI 只取 `output` 交回 Rust SDK。
- 未知工具、非法参数、权限错误、业务错误和未预期执行异常使用稳定、安全的分类，不回显参数、Provider payload、凭证或异常原文。
- 工具结果进入 SDK canonical tool message，并触发下一轮模型调用。
- 多 Session 共用进程级 SDK Host 时，driver callback 和结果不串 Turn/Session。

## 3. 明确不做

- 不实现 approval pause/resume。
- 不修改 SDK Rust loop、ToolScheduler、ToolResult ABI 或事件 schema。
- 不在 NoteMeld 新增工具循环、重试队列、活动 Turn map 或第二状态机。
- 不让 UI/CLI 发现、执行或持久化工具结果。
- 不扩充可写能力、第三方 MCP、Memory、Workspace 或 Skill 工具范围。

## 4. 冲突分析

- 产品规则：一致。继续保持 `/api/agent/v1` 单入口、SDK 单 loop、Host 无第二状态和 Provider payload 脱敏。
- 数据模型：无冲突；不改表、字段、状态枚举或文件结构。
- API：无公共接口变化；补充内部 ToolDriver 错误/结果契约说明。
- known pitfalls：必须避免 NoteMeld 重做 Agent loop、Provider/参数泄漏、assistant tool call 与 tool result 关系断裂，以及用进程内状态隔离 Session。
- 运行模式：源码、桌面和 CLI 继续共用同一已安装 standalone SDK artifact 与 Host。
- 打包/迁移/导入：无结构性影响；只使用现有 Python 标准库和既有依赖。

## 5. 影响范围

- 后端：`agent_host/capabilities.py`、`agent_host/drivers/tools.py`、`agent_host/native_executor.py`。
- 测试：`backend/tests/agent_host/test_capabilities.py`、`test_tool_driver.py`、`test_native_executor.py`，必要时新增真实 SDK 链路测试文件。
- 文档：本 Change Spec、执行 plan/spec、`current-architecture.md`、`api-inventory.md`、`known-pitfalls.md`、验证证据。
- 不影响：前端、Tauri、数据库迁移、文件系统、公共 MCP 工具。

## 6. 实施方案

### 后端

- `NoteMeldToolDriver.describe()` 同时兼容同步与异步 registry，并只返回有界 descriptor。
- ToolDriver 在调用前解析 call id/name/object arguments，并按 capability descriptor 的必要 JSON Schema 子集校验 required/type/min/max/minLength。
- ToolDriver 统一返回 `{call_id, output}`；`output` 为 `{ok:true,result}` 或 `{ok:false,error:{code,message}}`。
- registry 仍是唯一产品能力入口，继续调用 `WikiSearch` 和 Note document store；已知不存在等产品失败转为业务错误。
- 分类：`unknown_tool`、`invalid_arguments`、`permission_denied`、`business_error`、`tool_execution_error`。公开文案固定且不含参数或异常原文。
- Native executor 的 `tool.invoke` driver completion 始终把 `ToolResult.output` 放到 ABI `result.output`；只有 ABI/Host 自身格式错误才返回 driver-level `ok:false`。
- 不记录工具参数和异常原文；日志只记录工具名和稳定分类。

### 并发/取消

- 不新增共享 Session 状态。SDK `ToolContext` 的 session/turn id 只透传到本次 invoke context；结果以 call id 关联。
- 调度并行性、取消和下一轮模型调用继续由 SDK `execute_tool_round`/loop 管理。本阶段不扩展 ABI v1 的 progress/cancel callback。

## 7. 数据与接口变更

- SQLite/字段/文件/迁移：均无。
- 公共 HTTP/MCP：均无。
- 内部 ToolDriver result：规范化为 `{call_id, output}`；`output` 使用稳定 success/error envelope。
- 兼容：registry 的现有 descriptor `input_schema` 或 provider tool `parameters` 均可读取；产品返回 dict/list/scalar 均保留在 `result`。

## 8. 测试方案

- 正常 tool call：真实 SDK native runtime 首轮模型返回 tool call，Capability Registry 调现有/fixture 产品服务，SDK 接收 ToolResult，第二轮模型请求含匹配 call id 的 tool message。
- 未知工具：返回 `ToolResult.output.error.code=unknown_tool`，SDK 可继续下一轮。
- 非法参数：缺 required、类型不符、越界均返回 `invalid_arguments`。
- 权限错误：产品 `PermissionError` 返回 `permission_denied`，不回显异常文本。
- 业务错误：产品显式业务异常返回 `business_error`。
- 工具执行异常：未知异常返回 `tool_execution_error`，不回显异常文本或敏感参数。
- 多 Session：共享一个 SDK Host 并发执行两个 Turn，各自第二轮只看到自身 call id/result。
- 回归：Agent Host targeted tests、`compileall`，环境允许时运行 `backend/tests/agent_host`。

## 9. 验收标准

- [x] SDK ToolScheduler 是唯一工具调度者，NoteMeld diff 中没有新增 loop。
- [x] 正常工具调用经过 Registry 和已有服务，形成 ToolResult 后触发第二轮模型。
- [x] 五类失败有稳定 code 且不泄露敏感内容。
- [x] 未知工具/参数/权限/业务/执行错误不会绕过 Registry，也不会由 UI/CLI 执行。
- [x] 两个 Session 的 callback、call id、ToolResult 和第二轮消息互不串状态。
- [x] targeted tests 与 compileall 通过并有验证证据。

## 10. 风险和回滚

- 风险：错误 ToolResult envelope 可能让模型看不到产品结果；真实 SDK 测试必须断言第二轮 canonical tool message。
- 风险：过度 schema 校验破坏兼容；只实现当前 descriptor 使用的必要子集，业务 service 仍是最终校验边界。
- 风险：并发 callback 错路由；使用现有 Host token/turn mapping，不增加旁路缓存。
- 回滚：回退本次 Python adapter、测试和文档 commit；无数据迁移或持久化清理。

## 11. Agent 必答问题

- 影响模块：Agent Host capability registry、ToolDriver、native driver callback 和 Agent tests。
- 已有类似能力：有薄适配与 SDK scheduler，但错误/ToolResult/真实链路测试不完整。
- 产品规则冲突：无，反而补齐 SDK 单 loop 与产品适配边界。
- 数据语义冲突：无数据变更。
- known pitfalls：重点防止第二 loop、tool call/result 断裂、敏感 payload 日志和 Session 进程内旁路状态。
- 本地/线上影响：只影响本地 Agent tool invocation；不改公共服务和发布产物结构。
- 最小改动：三个生产文件加 targeted tests/docs。
- 防回归测试：成功第二轮、五类错误、真实 SDK、多 Session 隔离。
