# Change Spec：Agent SDK 单一运行时与 NoteMeld 正式切换

日期：2026-08-17
状态：Planned / Pending Approval（文档闭环已完成，用户确认前不开发）
Requirement：`docs/requirements/2026-08-17-agent-sdk-single-runtime-cutover.md`
目标架构：`docs/superpowers/specs/2026-08-17-agent-sdk-single-runtime-architecture.md`
实施计划：`docs/superpowers/plans/2026-08-17-agent-sdk-single-runtime-cutover.md`
执行规格：`docs/superpowers/specs/2026-08-17-agent-sdk-single-runtime-execution.md`
Supersedes：`docs/system/change-spec-universal-agent-sdk-unified-cli.md`、`docs/system/change-spec-agent-sdk-native-host-migration.md`

当前状态：核心切换和 SDK 唯一源码仓库收敛已完成；本文保留为迁移设计与验收依据。

## 0. 预检查

- [x] 已阅读五份必读系统文档。
- [x] 已搜索 NoteMeld 前端、后端、SQLite Store、CLI、打包测试和独立 SDK。
- [x] 已核对 SDK Rust crates、C ABI、Python binding 和 Ollama launcher。
- [x] 已确认本次影响本地 Agent 数据写入、桌面/源码 Host、CLI 和发布 artifact。

## 1. 当前系统现状

- NoteMeld 已有 Agent v1 API、native executor、Agent 表、前端 client 和 HTTP CLI。
- 独立 SDK 已有八个 Rust crate、C ABI、四类语言 binding 和 artifact workflow。
- 当前 native FFI Turn 固定使用空历史；ToolDriver、CapabilityRegistry、SessionCoordinator 和 Store contract 没有组合进正式执行路径。
- NoteMeld `NativeAgentExecutor` 只处理 model driver，`tool.invoke` 返回未接入；steer/approval 路由是占位。
- HTTP cancel 直接写数据库终态，没有调用 SDK cancel。
- events endpoint 只读取一次持久事件后结束，不是 replay + live subscription。
- Python `backend/app/agent/core` 及其 AgentService/SSE bridge 已从生产代码删除。
- 历史基线曾包含 NoteMeld 内嵌 `agent-sdk/` 文件和 SDK workflow；本次收敛将其移除，独立 SDK 仓库成为唯一源码/CI 发布源。
- 当前 Agent Host、SDK session crate 和 SQLAlchemy store 同时持有部分 Turn 规则，边界重叠。

## 2. 本次目标

- SDK 成为 Agent 行为唯一事实源；NoteMeld 成为产品 Host/adapter。
- UI、CLI 调用同一 Agent v1 Host、同一 Conversation 和同一事件协议。
- SDK 独立 Ollama 入口可完成真正带历史的多轮能力测试。
- 新链路验收后删除旧 Python Agent Core、compat、feature flag 和回滚模式。
- 保留历史用户数据和所有非 Agent 产品入口。

## 3. 明确不做

- 不开发完整移动端产品。
- 不做远程设备互调或 Harbor 测评。
- 不把 Note/Wiki/白板/MCP 产品实现迁入 SDK。
- 不删除历史 Conversation/Message/Note/Wiki/Whiteboard/Provider/Model 数据。
- 不为旧 Agent 执行逻辑保留兼容层。

## 4. 冲突分析

- 产品规则：用户已明确授权删除旧 Agent 能力；非 Agent 入口和历史数据继续保留。
- 数据模型：Conversation/Message 仍为产品历史事实源；Agent Turn/Event 由 SDK contract 管理并通过 adapter 映射。
- API：Agent v1 成为唯一 Agent API；旧 free-chat Agent 兼容路径在调用方清零后删除。
- Known pitfalls：重点防止双写、双状态机、事件断裂、SDK version 漂移、上下文工具对拆散和秘密泄漏。
- 桌面/源码/CLI/MCP：桌面/源码/CLI Host 生命周期受影响；MCP endpoint 和非 Agent tool 能力保留。
- 打包/迁移：PyInstaller/Tauri 必须携带 native SDK；migration/export 必须包含 Agent 表或明确可重建范围。

## 5. 影响范围

- 独立 SDK：`agent-core/events/model/tools/capabilities/session/storage/ffi`、Python binding、Ollama CLI、schemas/fixtures/artifact tests。
- SDK 仓库边界：把 SDK artifact CI 移到独立仓库，NoteMeld 删除内嵌 `agent-sdk/`，只保留消费验证。
- NoteMeld 后端：`backend/app/agent_host/`、`backend/app/routers/agent.py`、`backend/app/services/agent_store.py`、conversation projection、runtime lifespan。
- 旧 Agent：`backend/app/agent/core/`、`agent_service.py`、`sse_bridge.py` 及依赖旧 DTO 的 product tool adapters。
- 前端：`frontend/src/services/agent.ts`、`ChatComposer.tsx`、event reducer、model preference 和 approval UI。
- CLI：`scripts/notemeld-agent.py`、`scripts/notemeld`、PowerShell 对等入口、Host discovery。
- 桌面/打包：PyInstaller hidden imports/native resource、Tauri lifecycle、release workflow。
- 文档：current architecture、product rules、data model、API inventory、known pitfalls、changelog 和验证证据。

## 6. 实施方案

### SDK

- 将 session、storage、capability、approval/control 组合进正式 Runtime。
- 扩展 FFI/bindings 支持 history/store、真实 streaming chunk、tool progress、cancel、steer、approval 和 replay。
- 保持 SDK provider-neutral；NoteMeld 业务只能经 Driver/Provider 注册。

### NoteMeld Framework

- 使用进程级 `AgentSdkHost` 代替每 Turn 临时 Runtime/daemon thread。
- Model/Tool/Storage adapters 成为唯一 SDK 回调边界。
- 事件先按 SDK envelope 持久化，再通过 replay + live broker 提供 SSE。
- Conversation projection 幂等写 user/assistant/tool 消息；前端不再承担持久化。
- 全部 control API 调用 native Turn handle，不直接制造终态。

### 前端/CLI

- UI 和 CLI 仅提交 command、消费 event、读取 projection。
- 支持断线重连、session_busy、审批、全局模型偏好和服务器 ID 对账。
- SDK 测试 CLI 与 NoteMeld 产品 CLI 保持用途分离。

### 删除旧路径

- 新链路纵向验收通过后删除 Python Agent Core、legacy Agent service、compat、feature flag 和 rollback。
- 独立 SDK artifact/CI 已迁移至 `/Users/hehejie/ai/notemeld-agent-sdk`；NoteMeld 内嵌 `agent-sdk/` 源码与本仓库 SDK build workflow 已删除，NoteMeld release 只下载/校验 artifact。
- 旧 product tools 改写成 SDK adapters 后保留，不删除业务能力。

## 7. 数据变更

- 不删除或重写历史业务数据。
- Agent Turn/Event 表结构需与 SDK v1 envelope、sequence 和状态机完全一致。
- 模型偏好升级为全局默认 provider/model + 有序 fallback；可保留 session/Turn override。
- Conversation projection 需要持久保存实际 provider/model、turn_id、sources 和安全工具摘要。
- migration/export/import 纳入 Agent 表；schema ensure 必须幂等。

## 8. 接口变更

- 保留并补全 `/api/agent/v1` Session/Turn/events/cancel/steer/approval/preference。
- events 使用 `Last-Event-ID`/`after_sequence`，先回放再 live，终态后关闭。
- JSON API 统一 `{code,msg,data}`；SSE payload 直接使用完整 AgentEvent envelope。
- 删除 `/api/chat/free*` 的 Agent 兼容执行路径和旧 Agent feature flag。
- 前端与 CLI 不再调用旧 Chat Agent endpoint。

## 9. UI/交互变更

- ChatComposer 只保留 optimistic projection，不直接持久化 Agent user/assistant/tool 消息。
- 显示 SDK 的真实 tool progress、approval、cancel/steer 结果和安全错误。
- 重连后按服务器事件和 Conversation projection 恢复，不依赖组件内存。
- 无模型明确引导设置；桌面继续遵守 BackendInit ready gate。

## 10. 测试方案

- SDK：Rust workspace、conformance、真 streaming、history、tool、approval、cancel/steer、storage/replay、FFI/binding。
- SDK 实测：Ollama 连续三轮历史、模型切换、工具、取消和 JSONL。
- Host：binding loader、driver payload、transaction/idempotency、live SSE、startup interrupted、security/redaction。
- UI/CLI：同会话互相续聊、断线恢复、全局模型、审批、机器输出、Host discovery。
- 删除门禁：生产 import 不再引用 `backend/app/agent/core`，旧 endpoint/flag 不再被调用。
- 全量：后端 pytest、前端 contracts/build、core regression、PyInstaller/Tauri/release artifact contracts。

## 11. 验收标准

- [ ] SDK 是唯一 Agent loop/Turn/Event/control 实现。
- [ ] SDK 独立 Ollama 真多轮与统一事件通过。
- [ ] NoteMeld UI/CLI 同会话和同数据库纵向通过。
- [ ] model/tool/storage/control 全部经 SDK Driver contract。
- [ ] replay + live SSE、幂等、取消、steer、审批、interrupted 恢复通过。
- [ ] 旧 Python Agent Core、compat、feature flag 和 rollback 已删除。
- [ ] 历史数据和非 Agent 产品入口回归通过。
- [ ] 源码、桌面、CLI 和发布 artifact 都能加载版本匹配的 SDK。

## 12. 风险和回滚

- 风险：FFI async streaming/GIL deadlock、SQLite 写放大、工具副作用重复、Host 退出时活动 Turn 悬挂、打包漏 native library。
- 触发信号：空历史、无 delta、sequence gap、双 terminal、UI/CLI 消息不一致、cancel 后模型继续、SDK 缺失却仍可聊天。
- 降级：实施阶段可在发布前保留旧分支用于 Git 回退，但正式运行产物不包含动态 legacy fallback。
- 回滚步骤：代码版本整体回退；新 Agent 表保留，不删除历史数据；不得在单个 Turn 内切换 runtime。

## 13. Agent 必答问题

- 影响模块：SDK、Host/API、DB adapter、前端、CLI、桌面/打包、旧 Agent 模块。
- 已有能力：有，但目前是过渡接入，未形成单一运行时。
- 产品冲突：用户已明确覆盖旧兼容要求；历史数据与非 Agent 入口仍保留。
- 数据冲突：不改变 Conversation/Note 权威语义，新增/强化 Agent projection 和偏好。
- 已知坑：双写、版本漂移、事件断线、上下文超限、秘密泄漏、桌面 ready、打包漏资源。
- 本地/线上影响：主要影响本地 Host/数据/桌面；Web 后端部署使用同一 SDK artifact。
- 最小可行改动：先补齐 SDK session-oriented runtime，再替换 Host 唯一路径，最后删除旧逻辑。
- 回归测试：SDK direct、Host API、UI/CLI 纵向、非 Agent 全量和打包契约。
