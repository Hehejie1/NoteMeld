# Change Spec：Agent ModelDriver 完整请求上下文

日期：2026-08-19
状态：Implemented and verified

## 0. 预检查

- [x] 已阅读 `AGENTS.md`、`CLAUDE.md` 与五份必读系统文档
- [x] 已阅读 `docs/system/change-spec-template.md`
- [x] 已搜索 `backend/app/agent_host/`、notemeld-ai Provider/Models 和相关测试
- [x] 已核对独立 `notemeld-agent-sdk` 的 ModelDriver、ABI v1、Python binding 与 Rust FFI
- [x] 已确认不影响本地数据、远端服务或发布资产

## 1. 当前系统现状

- 相关模块：`ConversationHistoryStore`、`NativeAgentExecutor`、`NoteMeldModelDriver`、`app.ai.Models`、OpenAI-compatible Provider，以及独立 SDK 的 Rust Agent loop/FFI。
- 相关入口：`POST /api/agent/v1/sessions/{session_id}/turns`。
- 相关数据：Conversation 历史仍以 `conversations` / `conversation_messages` 为唯一事实源；本次不新增表或文件。
- 当前行为：Host 在 native turn submit 时附带 history、input、model override 和工具描述；SDK ABI v1 从 flattened `history` 初始化 Rust loop，并在每一轮 `model.stream` 回调中返回 canonical `messages`。
- 当前限制：ABI v1 的 `model.stream.payload` 只包含 `messages`。Host 直接把 payload 交给 ModelDriver，导致模型安全配置、当前 `context_refs` 与工具描述没有附着到每轮 Provider 请求；带 tool call/result 或结构化 context 的 SDK message 也没有转成 OpenAI-compatible message envelope。历史还被 Host 额外截成最后 40 条，绕过了统一模型窗口预算器。
- 复现证据：`backend/tests/agent_host/test_native_executor.py` 的上下文回归在基线出现 2 个失败；`backend/app/agent_host/event_broker.py` 另有一个已存在的括号语法错误，会阻断完整 Agent Host 导入。

## 2. 本次目标

- 每一轮模型请求使用 SDK loop 提供的 canonical messages，并保留完整 Conversation 历史、system 消息、当前 user 输入和完整 tool call/result 关系。
- 把当前 input/`context_refs`、安全模型运行配置和本轮工具描述附着到每一次 `model.stream` Host 请求。
- 把结构化 SDK message 转成 notemeld-ai/OpenAI-compatible message，并继续支持文本 delta、tool call、usage 和稳定 Provider 错误分类。
- Provider 错误日志、返回值和事件不得包含 API Key、原始 payload 或本地路径。
- 继续由 Rust SDK 维护 Agent loop；NoteMeld 只做 Host driver envelope 和 Provider adapter。

## 3. 明确不做

- 不实现或修改 ToolDriver 调度、approval 流程或 UI。
- 不在 NoteMeld 重建 Agent loop、工具轮次或会话状态机。
- 不修改独立 SDK 仓库、ABI 版本或公开 HTTP API。
- 不改数据库 schema、历史数据或文件结构。

## 4. 冲突分析

- 产品规则：不冲突；统一由 `Models.stream()` 在 Provider 前按保存的模型窗口裁剪副本，system/最新 user/tool group 规则继续生效。
- 数据模型：不冲突；Conversation 仍是唯一历史源，无新增持久化字段。
- API：不冲突；Agent v1 请求/响应与 SSE envelope 不变，只补齐内部 native driver payload。
- Known pitfalls：避免重新引入“完整历史直接交给小窗口模型”的问题，历史完整进入 SDK 后仍由 notemeld-ai 统一预算；不记录 Provider 原始异常文本。
- 运行入口：源码、CLI、桌面和 MCP 无接口变化；Agent Host 的现有 event broker 语法错误做最小前置修复。
- 打包/迁移/导入：无影响；继续加载已发布 ABI v1 artifact。

## 5. 影响范围

- 后端：`backend/app/agent_host/drivers/model.py`、`backend/app/agent_host/native_executor.py`；前置修复 `event_broker.py`。
- 测试：`backend/tests/agent_host/test_model_driver.py`、`test_native_executor.py`，并运行 Agent Host focused suite 与 AI Provider/Models 回归。
- 文档：本 Change Spec、`current-architecture.md`、`api-inventory.md`、`known-pitfalls.md`。
- 前端、桌面、数据库、MCP：无改动。

## 6. 实施方案

### Host / ModelDriver

- 从 Conversation store 读取完整模型历史，不再用固定 40 条截断；Provider 前预算仍由 `Models` 负责。
- 构造不含 key/base URL 的 model descriptor，并将它、当前 input/context refs、工具描述附着到每次 SDK `model.stream` 回调。
- SDK 每轮 `messages` 是权威；仅对旧/最小 ABI 首轮只回当前 user 的形态补回已加载历史，空 messages 直接返回 `invalid_input`，不伪造空历史成功。
- 规范化 system/user/assistant/tool message；恢复 assistant tool calls 与 tool result call id，结构化 context 以 JSON 资料文本进入 Provider。
- generation config 只接受已有 `LLMContext` 支持的显式安全字段。
- 流事件继续投影为 content delta、完整 tool call、usage；错误仅返回稳定 code/安全文案，日志只记录异常类别。

### 并发、取消与超时

- 不改变 SDK cancel token、工具调度或线程模型。
- 每轮上下文为 turn 内不可变快照加 SDK canonical messages，不新增共享可变状态。
- Provider timeout 仅在显式 generation config 存在时透传。

## 7. 数据变更

- SQLite、字段、文件结构、迁移、历史数据：均无变化。
- 回滚：回滚本提交即可，不产生数据清理需求。

## 8. 接口变更

- 公开 HTTP/MCP：无变化。
- 内部 `model.stream` Host payload：补齐 `model`、`model_override`、`input`、`context_refs`、`tools`、`generation_config`；保持 ABI v1 response envelope。
- 错误语义：补齐 `context_budget_exceeded` 安全分类；其他稳定 code 保持兼容。

## 9. UI/交互变更

无 UI 变更。用户可见效果仅为多轮 Agent 对话、工具轮和引用上下文能够真实进入模型请求。

## 10. 测试方案

- ModelDriver：多轮历史、system/user、结构化 context refs、工具描述与 tool messages；delta/tool call/usage；Provider auth/network/rate/capability/context 错误脱敏。
- Native executor：submit context 与每轮 driver context；第二轮保留 assistant tool call/result；模型 descriptor 不含敏感字段。
- 回归：Agent Host focused suite、AI Provider/Models tests、`compileall`；环境允许时运行全 backend tests。
- 原问题复现：基线 focused suite 的 2 个失败应转绿；空 `messages` 必须 fail closed。

## 11. 验收标准

- [x] 每轮 Provider 请求都包含正确 Conversation/system/current user/tool history。
- [x] `context_refs`、模型安全配置和工具描述进入每轮请求。
- [x] delta、tool call、usage 和 Provider error 投影测试通过。
- [x] 不出现 API Key、Provider payload 或本地路径泄漏。
- [x] NoteMeld 未新增 Agent loop、ToolDriver、approval 或 UI 实现。

验证证据：

- `PYTHONPATH=backend pytest -q backend/tests/agent_host/test_model_driver.py backend/tests/agent_host/test_native_executor.py`：`15 passed`。
- `PYTHONPATH=backend pytest -q backend/tests/agent_host/test_model_driver.py backend/tests/agent_host/test_native_executor.py backend/tests/agent_host/test_event_broker.py backend/tests/agent_host/test_host.py backend/tests/agent_host/test_runtime_loader.py`：`28 passed`。
- `PYTHONPATH=backend pytest -q backend/tests/ai/test_models.py backend/tests/ai/test_provider.py backend/tests/ai/test_stream.py backend/tests/ai/test_errors.py`：`70 passed`。
- `python3 -m compileall -q backend/app` 与 `git diff --check`：通过；compileall 仅报告 3 个未改动文件的既有 invalid-escape `SyntaxWarning`。
- 扩展 `backend/tests/agent_host` + AI focused suite：`136 passed, 13 failed`。13 个失败位于未改动的 CLI、旧 SDK cutover baseline、Agent store 事务和 TurnManager，未作为本需求通过项。
- 独立 SDK 源码契约确认 FFI 从 Turn `history` 初始化 canonical messages，并在工具轮后继续传递 assistant/tool group；本机现有 dylib 比 SDK Python binding/ABI contract 旧，缺少 `notemeld_agent_resolve_approval` export，真实 native smoke 在 runtime 初始化时 fail-closed，因此未宣称 native artifact 验证通过。

## 12. 风险和回滚

- 风险：SDK structured message 与 OpenAI-compatible envelope 形态不一致；通过显式规范化和 tool round tests 防守。
- 风险：完整历史增大 native submit payload；ABI 仍有请求大小上限，Provider 输入则由保存窗口统一裁剪。超出 ABI 上限会安全失败，不静默丢历史。
- 触发信号：`invalid_input`、tool result 缺 call id、Provider 400 或上下文预算错误。
- 回滚：回滚提交；无持久数据副作用。

## 13. Agent 必答问题

- 影响模块：Conversation history adapter、native executor、ModelDriver、notemeld-ai Provider 请求边界与相关测试。
- 已有类似能力：SDK 已维护 canonical loop/messages，Models 已做统一预算与 usage；本次只补 Host 适配断点。
- 产品/数据冲突：无；保持单一历史源和保存模型配置权威。
- Known pitfalls：重点防止固定截断破坏 tool group、原始 Provider 错误泄漏、NoteMeld 重做 loop。
- 本地/线上影响：只影响本地 Agent 模型请求；无数据迁移和线上服务变更。
- 最小改动：每轮 enrich + message normalization + 安全错误映射，不改 ABI/loop。
- 回归测试：多轮/system/user/context/tools/delta/tool/usage/error，以及完整 Agent Host focused suite。
