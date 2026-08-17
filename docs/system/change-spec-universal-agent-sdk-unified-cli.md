# Change Spec：跨平台 NoteMeld Agent SDK 与统一 UI/CLI 会话

> 状态：Superseded。用户于 2026-08-17 明确取消旧 Agent 兼容与 rollback；新事实源为 `docs/system/change-spec-agent-sdk-single-runtime-cutover.md`。

更新时间：2026-08-14
状态：Design Review
Canonical Requirement：`docs/requirements/2026-08-14-universal-agent-sdk-unified-cli.md`

依据 `docs/system/change-spec-template.md` 编写。本 Change Spec 描述如何在现有 Python/FastAPI/React/Tauri 系统上增量引入 Rust Agent SDK，并在可回滚前提下把 UI 与 CLI 迁移到统一 Agent Host。

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已阅读 `docs/system/change-spec-template.md`
- [x] 已搜索相关 Agent core、service、router、前端流式调用和会话持久化代码
- [x] 已搜索源码/CLI/桌面 sidecar、PyInstaller、Tauri 和 Release CI
- [x] 已搜索 Agent、SSE、Conversation、桌面、打包和前端契约测试
- [x] 已确认存在 Python Agent Core 和 P3 capability，但不存在跨平台 SDK、Agent CLI、统一 Turn Store 或移动端构建矩阵
- [x] 已确认影响本地 SQLite/文件、桌面发布和 GitHub Actions；远程 Agent 和 Harbor 不在本次范围

## 1. 当前系统现状

### 1.1 相关模块

- Python Agent Core：`backend/app/agent/core/`。
- Agent 业务能力：`backend/app/agent/agent_service.py`、`capability_catalog.py`、`chat_adapter.py`、`sse_bridge.py`、`memory.py`、`workspace.py`、`skill_loader.py`、`mcp_client.py`、`long_task.py`。
- LLM 抽象：`backend/app/ai/`，模型来自 SQLite `providers/models/model_capabilities`。
- 会话存储：`backend/app/services/conversation_store.py`，模型位于 `backend/app/db/models/conversation.py`。
- Chat 路由：`backend/app/routers/chat.py`。
- 前端聊天：`frontend/src/pages/HomePage/components/ChatComposer.tsx` 与 `frontend/src/services/chat.ts`。
- CLI 启动器：`scripts/notemeld`、`scripts/notemeld.ps1`、`scripts/install.sh`、`scripts/install.ps1`。
- 桌面运行时：`desktop/src-tauri/src/lib.rs`。
- 后端打包：`packaging/backend/pyinstaller/backend.spec` 和平台构建脚本。
- 发布：`.github/workflows/release.yml`。

### 1.2 相关入口

- 源码：`run_notemeld.sh`、`backend/main.py`、Vite frontend。
- 安装式源码 CLI：`notemeld start|stop|restart|logs|doctor|update|uninstall`。
- 桌面：Tauri 固定 8483 端口，启动 `notemeld-backend` sidecar；退出时 `kill_backend()`。
- Web/UI chat：`POST /api/chat/free/stream`。
- MCP：`/mcp`，与 FastAPI 同进程。

### 1.3 相关数据表/文件

- `conversations`：会话头；未来 AgentSession 继续复用其 `id`。
- `conversation_messages`：用户、助手、卡片、进度等消息。
- `models/providers/model_capabilities/model_usage_records`：模型与用量。
- `note_documents` 与 `note_results/`：笔记事实源。
- `workspaces/`、Wiki、memory、uploads、Chroma：Agent capability 数据。
- 当前没有 `agent_turns`、`agent_events`、共享 Agent 默认模型记录或运行时 descriptor。

### 1.4 相关 API

- `POST /api/chat/free`、`POST /api/chat/free/stream` 接受客户端 history/provider/model/conversation_id。
- `/api/conversations*` 由前端显式创建会话、追加用户消息、结束后追加助手消息。
- 桌面 token 当前注入 Axios；SSE fetch 未统一使用 Axios，新的 Agent API 需要显式 session header。
- 普通 `/api` 接口使用 `{code,msg,data}` wrapper；流式接口是明确例外。

### 1.5 相关前端页面/组件

- `ChatComposer.tsx` 当前负责用户消息和助手占位的前端状态，调用 Conversation API 持久化。
- `streamFreeChat()` 解析 `delta/done/error/task_card/task_card_progress/parameter_request` 私有 SSE 类型。
- Zustand task store 保存页面投影，但不应继续作为 Agent Turn 的事务所有者。

### 1.6 相关测试

- `backend/tests/agent_core/`：Python Agent loop 行为。
- `backend/tests/agent/`：service、capability、MCP、long task、SSE 兼容。
- `backend/tests/test_core_conversation_contracts.py`、`test_core_security_contracts.py`。
- `frontend/tests/chatComposerBackendInitContracts.test.mjs`、`learningCanvasContracts.test.mjs`、`modelRuntimeConfigContracts.test.mjs`。
- 桌面/Tauri Rust tests 与前端 desktop/autostart/packaging contracts。
- 当前没有 Rust Agent conformance、FFI smoke、Agent API、CLI REPL、移动 SDK target 测试。

### 1.7 当前行为与限制

- Python `Agent` 是运行时事实源，但直接依赖项目内 `app.ai` 类型和可选 `create_models()` 懒加载，不能独立跨平台构建。
- UI 与服务端分担同一次聊天的持久化，断线/并发/错误时难以形成原子终态。
- `AGENT_CHAT_ENABLED` 仍允许 legacy/Agent 双路。
- CLI 无 Agent 能力。
- 桌面 backend 生命周期属于窗口进程，不满足 UI 关闭后 CLI/长任务继续。
- Release CI 只覆盖桌面三类 job，不输出移动/服务端 Agent SDK。

## 2. 本次目标

- 用户问题：需要一个由同一套源码维护、可打包到桌面/移动/服务端的 Agent 能力包，并让 NoteMeld UI/CLI 使用同一 Agent、会话和数据库。
- 成功后的用户可见行为：
  - 页面和 `notemeld agent` 可新建或继续同一 Conversation。
  - CLI 提供 REPL、单次调用、模型切换、text/json/jsonl。
  - 页面刷新能看到 CLI 产生的消息，CLI 能读取页面历史。
  - 未配置模型时给出明确设置提示；危险操作统一审批。
  - 关闭 UI 不会打断活动 CLI Turn/长任务。
- 成功后的系统内部行为：
  - Rust `notemeld-agent-sdk` 是唯一 Agent loop/Turn/event 事实源。
  - Python FastAPI 进程内加载 binding，统一管理 Session/Turn/持久化/事件。
  - Session id 与 Conversation id 一一对应。
  - Agent API 版本化，SSE/JSONL 共用 schema。
  - SDK 构建矩阵产生桌面、server、iOS、Android、OpenHarmony 产物和 smoke harness。
- 必须保留的旧行为：
  - 历史 Conversation/Message/Note/Wiki 数据可读。
  - 源码、桌面、MCP、迁移、上传、打包入口继续工作。
  - `/api/chat/free*` 保留一发布周期兼容适配。
  - Python Agent legacy 在迁移验收期保留为显式紧急回滚，不作为新 UI/CLI 自动降级。

## 3. 明确不做

- 不做完整移动端应用。
- 不做设备间 Agent 发现、配对、远程调用或多主同步。
- 不做 Harbor 接入和正式测评。
- 不做独立 Notes CRUD CLI。
- 不一次性重写所有 Python 笔记/Wiki/学习/MCP 工具。
- 不改变现有 Note/Wiki/Canvas 权威数据语义。
- 不自动编辑 shell rc 或泄漏运行时 token。

## 4. 冲突分析

- 是否和 `product-rules.md` 冲突：不冲突。统一 Agent SDK强化核心范式，所有既有入口保留；危险写操作由人确认。
- 是否和 `data-model.md` 字段语义冲突：需新增 Agent Turn/Event/Preference 表，但 Conversation/Message/Note 语义保持；AgentSession 复用 Conversation id，避免双会话源。
- 是否和 `api-inventory.md` 接口契约冲突：新增 `/api/agent/v1`；旧 Chat API 兼容适配。普通 JSON 使用 wrapper，SSE 是文档化例外。
- 是否会重新引入 `known-pitfalls.md`：
  - 通过 Turn 原子创建和终态恢复避免任务/消息不同步。
  - 通过唯一 request_id 和同会话单 Turn 避免重复/竞态。
  - 通过批量 checkpoint 与唯一临时文件避免写放大/并发脏状态。
  - 通过本地 token、payload 脱敏和 stdout/stderr 分离避免秘密泄漏。
  - 通过旧实现保留一发布周期避免迁移期过早删除回滚路径。
- 是否影响桌面/源码/CLI/MCP：全部影响运行入口或回归范围；MCP endpoint 与工具语义保持。
- 是否影响打包、迁移、导入、回滚：增加 Rust/FFI 产物收集、SQLite 幂等迁移和 CI jobs；导入需包含新增表或可重建策略；回滚保留新表不删除历史数据。

## 5. 影响范围

### 5.1 后端文件

- 新增 `agent-sdk/` Rust workspace 与 binding 输出。
- 新增 `backend/app/agent_host/`（runtime loader、drivers、turn manager、event broker、approval、preference、persistence）。
- 新增 `backend/app/routers/agent.py`。
- 修改 `backend/app/__init__.py`、`backend/main.py` lifespan、DB models/init/schema ensure。
- 修改 `backend/app/services/chat_service.py` 和现有 Agent compatibility adapter。
- 迁移/冻结 `backend/app/agent/core/` 为行为 oracle/legacy rollback，最终删除需另一个明确变更。

### 5.2 前端文件

- 新增 `frontend/src/services/agent.ts` 与 Agent event types。
- 修改 `ChatComposer.tsx`、message/task store 和 runtime token fetch。
- 模型设置/选择接入共享 default model API。
- 危险操作审批 UI 复用统一事件。

### 5.3 桌面/Tauri 文件

- 修改 `desktop/src-tauri/Cargo.toml`/workspace 依赖与 `src/lib.rs` runtime ensure/lifecycle。
- 新增 CLI 安装 command、运行时 descriptor/权限处理和 Host supervisor 逻辑。
- 修改 Tauri resources/bundle 配置以携带 Agent SDK、binding、CLI 和 backend。

### 5.4 数据库模型/迁移

- 新增 `agent_turns`、`agent_events`、`agent_preferences`。
- 复用 `conversations`、`conversation_messages`；工具/模型/来源摘要写消息 meta/sources。
- 新增幂等 ensure，无 Alembic。

### 5.5 文件系统结构

- 新增用户运行时 descriptor（位于运行目录，权限仅当前用户可读）。
- SDK build artifacts 位于独立构建目录，不写入用户数据目录。
- 现有 note_results/workspaces/wiki/chroma 保持。

### 5.6 API 调用方

- 新 UI、CLI、未来移动绑定。
- 旧 UI/第三方 caller 继续通过 `/api/chat/free*` 兼容层。
- MCP 不改 endpoint。

### 5.7 测试与文档

- Rust unit/conformance/FFI/target smoke。
- Python binding/Host/API/DB/recovery/security tests。
- 前端契约与 UI/CLI 纵向测试。
- PyInstaller/Tauri/Release/CLI installer contracts。
- 更新 current architecture、product rules、data model、API inventory、known pitfalls、changelog 和验证证据。

## 6. 实施方案

本需求必须按依赖阶段交付，不允许一次性替换全部路径。

### 阶段 A：Rust SDK 基础与行为冻结

- 从现有 Python Agent tests 提炼与语言无关 fixture/snapshot。
- 建立 Cargo workspace：core/events/model/tools/capabilities/session/storage/ffi/cli。
- 实现 Turn 状态机、事件、tool 调度、abort/steer/follow-up、审批 hook 和 Driver traits。
- Rust conformance 与 Python oracle 对齐后，Rust 成为新行为事实源。
- 错误处理：全部使用稳定 error code + safe message；原始 Provider/tool payload 不跨 FFI。
- 并发/取消：同 Session coordinator 单活动 Turn；AbortToken 贯穿 model/tool；事件 channel 有界。

### 阶段 B：跨平台 binding 与构建矩阵

- 提供稳定 C ABI/JSON schema；Swift/Kotlin/Python typed wrapper；OpenHarmony N-API/ArkTS 薄层。
- 产出 macOS/Windows/Linux、iOS、Android、OpenHarmony artifact。
- 每个平台最小 harness 加载 SDK、执行 fake model+fake tool Turn 并校验 snapshot。
- License、target toolchain、版本固定在 execution spec。

### 阶段 C：NoteMeld Agent Host、数据库与 API

- Python binding 进程内加载 Rust SDK；FastAPI lifespan 初始化单例 runtime。
- Python ModelDriver/ToolDriver 复用当前 notemeld-ai、capability registry、Wiki/Note/Memory/Workspace/Skill/MCP。
- Agent Turn Manager 原子创建 Conversation Message/Turn，持久化 events、终态和实际模型。
- Agent API 支持 Session/Turn/events/cancel/steer/approval/model preference。
- 服务启动清理把残留 RUNNING/WAITING_APPROVAL 标为 INTERRUPTED。
- 普通 API 用 ResponseWrapper，SSE 直接输出 AgentEvent。

### 阶段 D：UI 迁移

- UI 只提交 session_id + input/context/attachment/model override。
- 删除 ChatComposer 对 Agent 用户/助手消息的双写职责；Zustand 只投影后端事件。
- 支持断线重连、session_busy、approval、模型未配置和 Backend ready gate。
- 旧 `/chat/free*` 不再被新 UI 调用。

### 阶段 E：CLI、Host 生命周期与安装

- Rust CLI 提供 REPL、one-shot、text/json/jsonl、`/model`、`/new`、`/resume`、`/sessions`、`/exit`。
- CLI 通过运行时 descriptor 发现本地 Agent Host；未运行时确保对应源码/安装 Host 启动。
- stdout/stderr 严格分离；无交互危险操作默认拒绝，`--yes` 显式授权。
- Host 独立于 UI 窗口生命周期，使用 pid/lock/descriptor 保证单实例；`notemeld stop` 显式停止。
- 桌面首次检测 CLI，不存在时显示一键用户级安装；不静默改 shell rc。

### 阶段 F：兼容、打包与切换

- `/api/chat/free*` 映射到新 Host，保留旧响应结构。
- 新 UI/CLI 不使用 `AGENT_CHAT_ENABLED` 分流；legacy 仅显式 rollback。
- PyInstaller 收集 native binding，Tauri bundle 收集 CLI/SDK/backend；Release CI 加 SDK jobs。
- 全量验证后才把默认正式路径切到 Rust；legacy 删除另开变更。

### 日志/可观测性

- 日志统一带 session_id/turn_id/request_id/event sequence，不记录 prompt 全文、秘密或原始 tool auth。
- 记录 SDK load version/target、Turn 时长、driver 调用时长、事件 backlog、checkpoint 和终态。
- CLI 机器模式日志只写 stderr。

## 7. 数据变更

### 7.1 新增表

`agent_turns`：

- `id TEXT PRIMARY KEY`
- `conversation_id TEXT NOT NULL`，索引/FK 到 conversations
- `request_id TEXT NOT NULL UNIQUE`
- `user_message_id TEXT NOT NULL`
- `assistant_message_id TEXT NOT NULL`
- `schema_version TEXT NOT NULL`
- `status TEXT NOT NULL`
- `provider_id TEXT NULL`
- `model_name TEXT NULL`
- `last_sequence INTEGER NOT NULL DEFAULT 0`
- `error_code TEXT NULL`
- `error_message TEXT NULL`（仅安全归一化信息）
- `created_at/started_at/completed_at/updated_at`

`agent_events`：

- `id TEXT PRIMARY KEY`
- `turn_id TEXT NOT NULL`，索引/FK 到 agent_turns
- `sequence INTEGER NOT NULL`
- `event_type TEXT NOT NULL`
- `payload_json TEXT NOT NULL`
- `created_at TEXT NOT NULL`
- unique `(turn_id, sequence)`

`agent_preferences`：

- 单用户本地记录，固定 singleton key 或明确 primary key
- `default_provider_id TEXT NULL`
- `default_model_name TEXT NULL`
- `updated_at TEXT NOT NULL`

### 7.2 写入与迁移

- Turn 创建时在同一 SQLite transaction 创建/确认 Conversation、用户消息、助手占位和 agent_turns。
- `message.delta` 事件在内存有界队列中批量 checkpoint；工具、审批和终态立即提交。
- Session id 不新增映射表，直接使用 Conversation id。
- 历史 Conversation 不回填 Turn；仅新 Agent API 调用产生 agent_turns。
- schema ensure 幂等；旧安装升级不清空任何 Conversation/Note/Model。
- 回滚后新表保留为惰性数据；旧路径忽略，不执行 destructive drop。
- 迁移 export/import 需要纳入新增表；若 event journal 被设计为可重建，必须在 execution spec 明确导入策略，不能静默丢 Turn 终态。

## 8. 接口变更

### 8.1 新增接口

- `POST /api/agent/v1/sessions`
- `GET /api/agent/v1/sessions`
- `GET /api/agent/v1/sessions/{session_id}`
- `POST /api/agent/v1/sessions/{session_id}/turns`
- `GET /api/agent/v1/turns/{turn_id}`
- `GET /api/agent/v1/turns/{turn_id}/events`
- `POST /api/agent/v1/turns/{turn_id}/cancel`
- `POST /api/agent/v1/turns/{turn_id}/steer`
- `POST /api/agent/v1/turns/{turn_id}/approvals/{approval_id}`
- `GET /api/agent/v1/preferences/model`
- `PUT /api/agent/v1/preferences/model`
- CLI/runtime discovery 为本地文件协议，不新增公开远程 endpoint。

### 8.2 修改接口

- `/api/chat/free`、`/api/chat/free/stream` 内部改为新 Host compatibility adapter；旧 request/response 保持。
- `/api/conversations*` 继续用于列表/详情/非 Agent 消息，Agent Turn 消息不再由新 UI 分步写入。

### 8.3 请求/返回/错误

- start_turn 请求含 `schema_version/request_id/input/model_override/capability_policy`，不接收权威 history。
- 返回 session/turn/message ids、status、events_url。
- AgentEvent 信封含 schema_version/event_id/sequence/session_id/turn_id/timestamp/type/payload。
- 主要错误：`session_busy`、`model_not_configured`、`agent_runtime_unavailable`、`approval_required/expired`、`turn_not_found`、`invalid_session_token`。
- JSON API 使用 wrapper；SSE/文件流是文档化例外。

### 8.4 兼容策略

- 旧接口保留一发布周期。
- schema 新增字段向后兼容；破坏变更提升 major schema version。
- 新 UI/CLI 只使用 v1，不根据 feature flag 选择 legacy。
- 必须更新 `docs/system/api-inventory.md`。

## 9. UI/交互变更

- 页面/组件：Home ChatComposer、对话流、模型选择、审批提示、backend ready 状态。
- 用户操作路径：
  - UI 新建/继续会话不变；底层改为 start_turn + event stream。
  - CLI 默认新会话，`--conversation`/`/resume` 续聊。
  - `/model` 读取和更新共享默认模型。
- 加载态：显示 Agent Turn 的真实状态和工具/审批事件；重连显示“正在恢复”。
- 空状态：无模型时明确进入设置；无会话时 CLI 新建。
- 失败态：区分 session busy、runtime unavailable、model missing、turn failed/interrupted。
- 成功态：后端终态为成功边界，页面刷新/CLI 重开可恢复。
- 可访问性：审批提示必须键盘可操作，CLI 提示不依赖颜色。
- 桌面与浏览器差异：桌面负责本地 Host/CLI 安装；普通 Web 只连接部署后端，不尝试启动本机服务。

## 10. 测试方案

### Rust/SDK

- crate unit tests：state/event/tool/abort/approval/session/idempotency。
- conformance fixtures：与 Python oracle 对齐事件 snapshot。
- stress：并行 session、同 session 冲突、10k event 顺序/背压。
- target smoke：macOS/Windows/Linux/iOS/Android/OpenHarmony artifact 加载和 fake turn。
- FFI tests：Swift/Kotlin/Python/ArkTS schema 与 error mapping。

### 后端

- Python binding loader、driver callback、SDK failure classification。
- DB schema ensure、transaction/idempotency、startup interrupted cleanup、event replay。
- API wrapper/SSE/Last-Event-ID/security/redaction。
- capability/tool/long-task regression。
- legacy chat compatibility。

### 前端

- Agent service contract：不再发送 history/双写 assistant message。
- SSE reconnect、busy、approval、model missing、runtime unavailable。
- Backend ready gate、消息刷新恢复、CLI-created conversation 可见。
- `pnpm test:contracts` 与 build。

### CLI/桌面/打包

- REPL commands、one-shot text/json/jsonl、stdout/stderr、exit codes、`--yes`。
- Host discovery/start/stop/singleton、UI close 后 CLI 继续。
- CLI user-space installer/PATH failure。
- PyInstaller native binding collection、Tauri resource/sidecar、Release artifact names。

### 推荐验证命令（最终以实施 Spec 为准）

```bash
cargo test --workspace
cargo clippy --workspace --all-targets -- -D warnings
cargo fmt --all -- --check
PYTHONPATH=backend python3 -m pytest backend/tests/agent_core backend/tests/agent
pytest backend/tests
cd frontend && pnpm test:contracts
cd frontend && pnpm build
scripts/run_core_regression.sh
```

移动平台和 release jobs 由新增 CI workflow 执行，不能用本机未安装 SDK 的跳过结果代替。

## 11. 验收标准

- [ ] Rust SDK 是新路径唯一 Agent loop/Turn/event 实现，跨平台 conformance 通过。
- [ ] SDK 构建产生 macOS/Windows/Linux/iOS/Android/OpenHarmony 目标产物和 smoke 证据。
- [ ] Python FastAPI 进程内加载 binding，Agent API/DB/事件/审批/恢复测试通过。
- [ ] UI 与 CLI 同会话、同数据、同模型偏好纵向验证通过。
- [ ] `notemeld agent` REPL、one-shot、text/json/jsonl、模型和会话命令通过。
- [ ] 同会话并发、幂等、断线重连、cancel、interrupted cleanup 通过。
- [ ] 桌面关闭不打断活动 CLI/长任务，Host 显式 stop 和单实例通过。
- [ ] 历史数据和源码/桌面/MCP/迁移/Wiki/上传/打包入口回归通过。
- [ ] 旧 Chat API 兼容适配通过；新 UI/CLI 不受 `AGENT_CHAT_ENABLED` 分流。
- [ ] 安全脱敏、运行时 token 权限、机器输出 stdout/stderr 通过。
- [ ] 系统文档和验证证据同步完成。

## 12. 风险和回滚

### 12.1 主要风险

1. Python→Rust 行为迁移偏差，尤其是流式 tool call、上下文和长任务。
2. Python async Driver 回调与 Rust runtime/GIL/deadlock。
3. iOS/Android/OpenHarmony toolchain 和 FFI 打包差异。
4. 新 Turn/Event 表造成 SQLite 写放大。
5. UI、CLI、compat caller 同时使用导致双写或 session race。
6. Host 脱离窗口生命周期后产生僵尸进程/端口冲突。
7. PyInstaller/Tauri 漏收 native library 或签名、公证失败。

### 12.2 风险触发信号

- Rust/Python conformance snapshot 不一致。
- Turn 长期 RUNNING、sequence gap、duplicate request/message。
- FFI callback 卡住 FastAPI event loop。
- event queue 无界增长或 SQLite lock 增多。
- 桌面退出后 backend 意外停止/重复启动。
- 目标平台 artifact 加载失败或 release job skipped。

### 12.3 降级策略

- 阶段 A/B 不接生产入口，仅运行 oracle/conformance。
- 阶段 C 使用内部开关选择 Rust Host 或 legacy，仅测试/灰度；新 UI/CLI 正式切换前必须纵向验证。
- 发布切换后若严重失败，可显式启用 legacy chat compatibility；不得在请求失败时静默双跑或自动 fallback，避免重复工具副作用。
- 移动 target 失败不影响桌面既有版本发布，但不得把 SDK 总验收标记完成。

### 12.4 回滚步骤

- 停用新 Agent v1 UI/CLI 入口，恢复旧 UI Chat adapter。
- 保留新增表和 Rust artifact，不删除用户产生的 Conversation/Message。
- 恢复 Tauri 旧 sidecar kill 行为前先确认没有活动 CLI Turn。
- 回滚 PyInstaller/Tauri resource 变更并运行旧打包契约。
- 后续重新启用时继续读取已完成 Turn；残留活动 Turn 标记 INTERRUPTED。

### 12.5 回滚后数据一致性

- Conversation/Message 是共享事实，legacy 仍可读取。
- agent_turns/events/preferences 可保留，不影响旧 ORM。
- 不执行 drop table/字段，不清空模型或笔记。
- Rust 执行过的有副作用工具结果必须保留审计，回滚不能重复执行。

## 13. Agent 必答问题

- 这个需求影响哪些已有模块？Agent core/business、notemeld-ai、Conversation/DB、Chat API、Home UI、CLI scripts、Tauri lifecycle、PyInstaller、Release CI、system docs。
- 当前系统是否已有类似能力？有 Python Agent Core/P3 capability 和 UI SSE，但无跨平台 SDK、Turn Store、Agent CLI、统一 Host。
- 是否和产品规则冲突？不冲突；保留全部入口并强化人类审批。
- 是否和数据模型字段语义冲突？不冲突；新增 Turn/Event/Preference，Session 复用 Conversation id。
- 是否会重新引入 known pitfalls？风险高，已用原子持久化、幂等、明确终态、脱敏、ready gate、打包契约和回滚期控制。
- 是否影响本地数据或线上服务？影响本地 DB、运行目录、桌面/CLI/CI；不含远程设备或 Harbor 服务。
- 最小可行改动是什么？不能仅加 CLI adapter；最小正确路径是先 Rust SDK/conformance，再 Python Host/Turn Store，再 UI/CLI，按阶段切换。
- 需要补哪些测试防止回归？Rust/FFI/target、Host/API/DB/recovery、安全、UI/CLI 纵向、Tauri/PyInstaller/Release 和现有全量回归。
