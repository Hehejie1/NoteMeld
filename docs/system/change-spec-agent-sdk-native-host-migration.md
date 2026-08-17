# Change Spec：独立 Agent SDK native host 迁移

> 状态：Superseded。该文档记录过渡接入；正式单一运行时架构见 `docs/system/change-spec-agent-sdk-single-runtime-cutover.md`。

## 当前现状

独立仓库 `/Users/hehejie/ai/notemeld-agent-sdk` 已提供 Rust workspace、C ABI、Python binding 和带 native library 的 macOS wheel。NoteMeld 的 `/api/agent/v1` 已有 Turn/事件存储，但此前只创建 Turn，不实际执行 Rust runtime；旧 `backend/app/agent/core` 仍被聊天、工具和 MCP 兼容路径使用。

## 目标

让 Agent v1 新入口通过独立 SDK 的 native runtime 执行模型 turn，同时沿用 NoteMeld 的会话、事件、模型偏好和终态持久化。迁移期间保持旧聊天、CLI、MCP 和笔记链路可用。

## 明确不做

- 本变更不一次性删除仍被生产代码引用的 `backend/app/agent/core`。
- 不改变 SQLite 表、现有 API wrapper 或历史 conversation 数据格式。
- 不在本机声称 Android/OpenHarmony target 已构建；这些留给 CI 工具链。

## 最小改动

1. SDK native artifact 已通过 Rust 87 项测试、dylib 构建、wheel 安装和 Python fake turn 验证。
2. NoteMeld 增加 `NativeAgentExecutor`：将已保存模型映射到 SDK `model.stream` driver，接收 SDK 事件，持久化非终态事件并完成终态 Turn。
3. `/api/agent/v1/sessions/{id}/turns` 选择用户默认/兜底模型后，后台启动 executor。
4. 继续迁移旧聊天和工具前，保持 `agent/core` 兼容层；每次迁移以生产 import 搜索和 focused tests 作为门禁。

## 测试与验收

- SDK workspace test：87 passed。
- native wheel clean virtualenv smoke：`turn.succeeded`。
- NoteMeld executor unit tests：fake SDK event/driver 和后台启动路径通过。
- 后续阶段必须补真实已配置 Provider 的 Agent turn、取消、工具调用、CLI/UI 同会话回放测试。

## 风险与回滚

SDK binding 缺失、模型未配置或 native driver 失败时，executor 写入安全的 `sdk_internal_error`/模型错误终态，不泄露 Provider payload。回滚只需关闭 Agent v1 native executor feature flag，旧 `agent/core` 与旧聊天入口仍保留。
