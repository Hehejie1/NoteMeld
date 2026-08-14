# 跨平台 NoteMeld Agent SDK 与统一 UI/CLI 会话

日期：2026-08-14  
作者 / Agent：Codex（doc-driven）  
状态：Ready for Plan  
关联对话 / 任务：Harbor Agent 测评前置改造、UI/CLI 统一 Agent、跨平台 Agent SDK  
关联系统文档：`docs/system/current-architecture.md`、`docs/system/product-rules.md`、`docs/system/data-model.md`、`docs/system/api-inventory.md`、`docs/system/known-pitfalls.md`  
关联历史需求：`docs/requirements/2026-08-01-notemeld-agent-core-runtime.md`、`docs/requirements/2026-08-01-notemeld-agent-research-assistant.md`、`docs/requirements/2026-08-11-progressive-capability-routing.md`

## 1. 原始需求

用户希望把 NoteMeld Agent 改造成真正的一套底层能力：

> “页面调用 agent 对话，以及支持 cli 调用的 agent 对话保持完全底层一套内容。”

> “`notemeld agent` 和 UI 只是入口不一样，两个操作的数据库底层都是一样的。”

> “同一个 agent 能力包，桌面端（mac、win）、手机端（苹果、安卓、鸿蒙）、网页端（后端服务）都来自一个包，一套代码维护，然后打包不同平台使用。”

用户确认：

- 采用后端统一 Agent Application Service，UI/CLI 只是入口。
- Agent 核心采用 Rust 作为唯一跨平台实现；现有 Python Agent Core 迁移为 Rust SDK 的调用方。
- `notemeld agent` 同时支持交互式和单次无交互调用。
- UI 与 CLI 共享会话、消息、默认模型、来源、工具结果和笔记数据。
- 生成 iOS、Android、OpenHarmony SDK 产物及最小验证工程，但本次不开发完整移动端产品。
- 远程设备间 Agent 调用与 Harbor 接入不在本次范围；统一 Agent/CLI 完成后再单独接入 Harbor。

## 2. 背景和问题

- 当前用户是谁：NoteMeld 桌面/网页用户、终端用户，以及后续 iOS、Android、HarmonyOS 客户端开发者。
- 当前场景是什么：React 页面通过 `/api/chat/free/stream` 调用 FastAPI；现有 `notemeld` 命令只负责启动、停止、日志和更新；Tauri 启动 Python backend sidecar。
- 当前痛点是什么：
  1. 当前 Agent Core 是 Python 仓库内模块，不能作为同一原生能力包编译到 iOS、Android、OpenHarmony。
  2. 当前页面在前端创建用户/助手消息、提交 history、结束后补写数据库；Agent turn 不由后端原子管理。
  3. CLI 没有 Agent REPL、单次调用和机器可读事件协议。
  4. UI 与未来 CLI 若分别维护历史、持久化和流式映射，会形成两套运行语义并引入并发脏状态。
  5. 当前 `AGENT_CHAT_ENABLED` 可让聊天在 legacy 与 Agent 两套实现间分流，无法成为唯一正式底层。
  6. 当前桌面退出时会杀掉 backend sidecar，会中断独立终端会话或长任务。
- 为什么现在要做：Harbor 自动测评和后续多端产品都需要稳定、无界面、机器可读且可复用的 Agent 入口；继续围绕当前 UI 兼容接口叠加会放大迁移成本。

## 3. 目标结果

- 目标 1：交付一个以 Rust 为唯一行为事实源的 `notemeld-agent-sdk`，同一源码可构建 macOS、Windows、Linux server、iOS、Android 和 OpenHarmony 产物。
- 目标 2：让 Agent Turn、事件、工具调度、取消、steer、审批、会话协调和通用能力路由在所有平台保持一致。
- 目标 3：让当前 FastAPI 后端以 Python binding 加载 SDK，成为 NoteMeld Agent Host；UI 和 CLI 调用同一 Session/Turn API。
- 目标 4：UI 与 CLI 在同一运行环境中共享同一个 SQLite/文件数据目录；新建、续聊、刷新和错误恢复得到相同数据。
- 目标 5：提供 `notemeld agent` 交互模式、单次模式和 text/json/jsonl 输出，供用户、脚本和未来 Harbor adapter 调用。
- 目标 6：桌面端和源码入口都能确保 Agent Host 可用；关闭 UI 不得中断仍在运行的 CLI Turn 或 Agent 长任务。
- 目标 7：保留历史会话、笔记、Wiki、MCP、源码、桌面、迁移、上传和打包入口兼容性。

## 4. 非目标

- 不做完整 iOS、Android、HarmonyOS NoteMeld 应用，只交付 SDK 产物、绑定和最小验证工程。
- 不做不同设备之间的 Agent 发现、配对、远程调用或多主数据库同步。
- 不做 Harbor custom agent adapter、Harbor benchmark task 或测评报告；它是本需求完成后的独立需求。
- 不做完整的 `notemeld notes list/edit/delete` 显式 CRUD 命令；笔记操作由 Agent 工具完成。
- 不在第一阶段一次性把所有 NoteMeld Python 业务工具重写为 Rust；通过 Driver 接入并按后续阶段迁移。
- 不改变 Note、Wiki、学习白板的事实源语义，不删除现有能力。
- 不静默修改用户 shell rc；CLI 安装采用用户可见的一键安装与 PATH 指引。

## 5. 当前系统事实

- 已有类似能力：
  - `backend/app/agent/core/` 已实现 Python Agent loop、状态、事件、工具并发、abort、steer、follow-up。
  - `backend/app/agent/` 已实现 capability routing、memory、workspace、Skill、MCP client 和 long task。
  - `backend/tests/agent_core/`、`backend/tests/agent/` 已覆盖现有 Python 行为，可作为 Rust 迁移行为基线。
- 当前入口 / 页面 / API：
  - UI：`frontend/src/pages/HomePage/components/ChatComposer.tsx`。
  - UI 流式客户端：`frontend/src/services/chat.ts`。
  - API：`POST /api/chat/free`、`POST /api/chat/free/stream`。
  - CLI：`scripts/notemeld`、`scripts/notemeld.ps1`，当前无 Agent 子命令。
  - 桌面：`desktop/src-tauri/src/lib.rs::spawn_backend_sidecar()`。
- 当前数据来源和写入位置：
  - `conversations`、`conversation_messages`、`note_documents` 等 SQLite 表。
  - `note_results/`、`workspaces/`、`uploads/`、Wiki 文件和 Chroma。
  - 页面目前先调用 Conversation API 写用户消息，流结束后再写助手消息。
- 当前限制：
  - Python Agent Core 内部仍直接引用 `app.ai` 的模型上下文和流事件，并可懒加载 `create_models()`，尚非独立包。
  - Tauri Cargo workspace 目前只有桌面壳 crate。
  - Release CI 目前只构建 macOS/Windows 桌面产物，没有 Agent SDK 的 iOS/Android/OpenHarmony/Linux 构建矩阵。
  - PyInstaller spec 目前只收集 Python `app` 子模块和静态资源，没有原生 Agent binding。
  - 桌面 session token 仅在部分敏感接口强制校验；新的 Agent mutation/stream 接口需要统一安全边界。
- 相关 known pitfalls：
  - 任务状态和会话消息不同步。
  - API ResponseWrapper 被破坏。
  - 桌面 ready gate 被绕过。
  - API Key/token/headers 泄漏。
  - 并发文件写固定 tmp、状态长期停留 running。
  - 模型上下文裁剪破坏 tool call/result 成组语义。
  - 迁移期过早删除旧实现导致失去回滚路径。

## 6. 用户故事

- 作为 NoteMeld 用户，我希望在页面和终端中打开同一会话继续提问，以便两种入口共享完整上下文与笔记。
- 作为终端用户，我希望使用 `notemeld agent` 进行交互式对话，或用 `-p` 执行单次请求，以便人工使用和脚本自动化。
- 作为多端开发者，我希望同一 Agent SDK 构建为桌面、服务端和移动端原生包，以便所有端共同研发 Agent 行为而不是分别重写。
- 作为 NoteMeld 用户，我希望模型选择具有共享默认值，并能在 CLI 使用 `/model` 切换，以便不同入口获得一致且可追溯的模型行为。
- 作为系统维护者，我希望每次 Turn 都有幂等 ID、终态和可重放事件，以便断线、取消和进程异常不会留下不可解释的半条消息。
- 作为安全敏感用户，我希望危险工具操作在 UI/CLI 使用同一审批策略，以便脚本不能绕过交互确认。

## 7. 验收标准

1. GIVEN 同一 SDK 源码，WHEN 执行平台构建矩阵，THEN 产出 macOS ARM64/x64、Windows x64、Linux server、iOS XCFramework、Android AAR/原生库和 OpenHarmony 原生库，且各产物通过最小加载测试。
2. GIVEN 一组固定模型流和工具 fixture，WHEN 分别通过 Rust 原生测试、Python binding、Swift/Kotlin/ArkTS 最小 harness 执行，THEN Turn 状态、事件类型、sequence、工具顺序和终态符合相同 conformance snapshot。
3. GIVEN 当前 NoteMeld FastAPI 启动，WHEN Agent Host 初始化，THEN 后端进程内成功加载 Rust SDK；SDK 加载失败时 `/api/agent/v1/*` 返回可分类的 `agent_runtime_unavailable`，既有非 Agent API 仍可诊断。
4. GIVEN 用户在 UI 创建会话并完成一次提问，WHEN 在 CLI 使用该 conversation id 续聊，THEN CLI 读取同一历史并将新消息写入同一 SQLite Conversation；页面刷新后显示 CLI 产生的消息、来源和工具结果。
5. GIVEN 用户从 CLI 新建会话，WHEN UI 重新加载侧栏，THEN 新会话可见且可从 UI 继续提问。
6. GIVEN 同一会话已有活动 Turn，WHEN UI 或 CLI 再提交新 Turn，THEN 服务返回 `409 session_busy`，不得并行写入第二组回答；不同会话仍可并行。
7. GIVEN 客户端提交相同 `request_id` 两次，WHEN 后端处理请求，THEN 只创建一条用户消息、一个助手占位和一个 Turn。
8. GIVEN SSE/JSONL 客户端在 sequence=N 后断线，WHEN 使用 `after_sequence=N` 或 `Last-Event-ID` 重连，THEN 后续事件顺序连续且不重复已确认事件。
9. GIVEN 客户端断线，WHEN Turn 仍在运行，THEN Turn 不被隐式取消；成功、失败、取消或进程中断最终都写入明确终态。
10. GIVEN 后端在 Turn 处于 RUNNING/WAITING_APPROVAL 时异常退出，WHEN 服务重启，THEN 残留 Turn 被标记为 `INTERRUPTED`，不得永久显示运行中。
11. GIVEN 用户没有显式指定模型，WHEN 创建 Turn，THEN 按“共享默认模型 → 第一个可用模型”解析；没有模型时返回 `model_not_configured` 并提示设置模型。
12. GIVEN UI 或 CLI 切换共享默认模型，WHEN另一个入口读取模型偏好，THEN 得到同一 provider/model；每条助手消息仍记录实际使用模型。
13. GIVEN Agent 请求删除、覆盖、批量修改或外部 MCP 写操作，WHEN执行工具，THEN UI/交互式 CLI 收到同一 `approval.required`；无交互模式默认拒绝，只有显式 `--yes` 才可批准允许的危险操作。
14. WHEN 运行 `notemeld agent`，THEN进入 REPL 并支持 `/model`、`/new`、`/resume`、`/sessions`、`/exit`；默认新建会话，`--conversation` 可继续指定会话。
15. WHEN 运行 `notemeld agent -p "问题" --output json|jsonl`，THEN stdout 只输出协议结果，日志写 stderr；JSON 包含 session/turn/message/model/usage/sources，JSONL 使用统一 AgentEvent schema。
16. GIVEN 桌面或源码 Agent Host 已运行，WHEN CLI 启动，THEN CLI 连接该运行实例和数据目录；服务未运行时 CLI 能启动对应 Host。
17. GIVEN UI 关闭但 CLI Turn 或 Agent 长任务仍在运行，WHEN桌面窗口退出，THEN运行不被终止；`notemeld stop` 可显式停止 Host。
18. GIVEN 历史 Conversation 和 Note 数据，WHEN升级并使用新 Agent API，THEN旧数据保持可读，现有 Note/Wiki/MCP/迁移/上传入口不丢失。
19. WHEN 新 UI 与 CLI 上线，THEN二者只调用统一 Agent Session/Turn 服务；`AGENT_CHAT_ENABLED` 不再让这两个入口分流到两套实现。
20. WHEN 运行现有 Agent、后端核心、前端契约、桌面打包测试及新增 SDK conformance tests，THEN全部通过后才能声明实现完成。

## 8. 输入 / 输出样例

### 输入

```bash
notemeld agent
notemeld agent --conversation conv-123
notemeld agent -p "整理当前会话中的研究结论" --output json
notemeld agent -p "删除这些重复草稿" --output jsonl --yes
```

```json
{
  "schema_version": "1",
  "request_id": "req-uuid",
  "session_id": "conv-123",
  "input": {
    "text": "继续比较这两个方案",
    "attachments": [],
    "context_refs": []
  },
  "model_override": null
}
```

### 输出

```json
{
  "schema_version": "1",
  "session_id": "conv-123",
  "turn_id": "turn-456",
  "status": "SUCCEEDED",
  "answer": "……",
  "sources": [],
  "model": {"provider_id": "provider-1", "model_name": "model-a"},
  "usage": {"input_tokens": 0, "output_tokens": 0}
}
```

### 反例或失败样例

```json
{
  "schema_version": "1",
  "error": {
    "code": "session_busy",
    "message": "该会话正在其他入口运行"
  }
}
```

- 未配置模型时不得调用未知 Provider 或静默选择未保存模型。
- `--output json|jsonl` 时不得把日志、进度提示或敏感配置混入 stdout。
- 危险操作缺少批准时不得默认执行。

## 9. 约束

- 平台 / 设备：macOS ARM64/x64、Windows x64、Linux server、iOS ARM64/simulator、Android ARM64、OpenHarmony ARM64；移动端只要求 SDK 与最小验证工程。
- 性能 / 耗时：排除模型和工具实际耗时后，本地 start_turn 编排开销 p95 不高于 50ms；事件 sequence 不得丢失或乱序；流式 delta 必须批量 checkpoint，不能每 token 独立提交 SQLite。
- 隐私 / 安全：仅绑定 localhost 的本地服务仍必须用仅当前用户可读的运行时凭据保护 Agent mutation/stream；事件、日志和持久化 payload 不得包含 Provider Key、Cookie、MCP token 或未脱敏 env/header。
- 兼容性：保留源码、桌面、CLI、MCP、迁移、Wiki、上传、打包入口；历史数据保持可读；legacy chat 至少保留一个发布周期作为紧急回滚。
- 成本：优先开源许可兼容依赖；引入 Rust crate/绑定工具前必须完成 License 清单；不引入必须依赖云端的运行时。
- 时间：按依赖阶段交付，不能把 Rust SDK、Host、UI/CLI 和移动端产物作为无检查点的一次性大改。
- 第三方依赖 / License：Rust stable；Swift/Kotlin/Python binding 可使用 UniFFI/PyO3 组合，OpenHarmony 使用稳定 C ABI + N-API/ArkTS 薄封装；最终选择需在实施 Spec 固定版本和许可证。

## 10. 边界场景

- 空数据：无会话时 `notemeld agent` 创建新会话；无模型时明确阻断并提示配置。
- 权限拒绝：审批拒绝写入 `approval.resolved` 和安全 tool result，Agent 可继续解释但不能执行被拒绝动作。
- 网络失败：模型/MCP 网络错误写入 `turn.failed`，保留已生成文本和工具结果，不泄漏原始响应 payload。
- 任务中断：显式 cancel 进入 CANCELLED；进程退出恢复为 INTERRUPTED；客户端断线不等于 cancel。
- 旧数据兼容：Session id 与 Conversation id 一一对应；不复制历史 Conversation；新增表使用幂等 schema ensure。
- 大数据量：长会话由统一 token budget 裁剪副本，不改写持久历史；事件写入分批提交并设置有界队列/背压。
- 并发：同会话单活动 Turn，不同会话并行；工具自身的文件写入继续使用锁和唯一临时文件。
- SDK 不可用：Host 提供明确诊断，不得静默回退到另一套 Agent 实现制造行为漂移。
- CLI 安装失败：桌面 UI 保持可用，展示目标路径、PATH 和恢复步骤，不自动修改 shell rc。
- 平台差异：平台专属代码只能实现 Driver/FFI/打包，不得复制 Agent loop、Turn 状态机或事件语义。

## 11. 开放问题

无阻塞问题。产品范围、核心语言、平台矩阵、UI/CLI 数据语义、模型规则、审批规则、并发规则和非目标均已由用户确认。

## 12. 与系统事实的冲突检查

- 是否和 `product-rules.md` 冲突：不冲突；服务“AI 编译知识，人验证和消费”，并保留所有现有入口。危险操作审批强化人的验证边界。
- 是否和 `data-model.md` 字段语义冲突：需要新增 Agent Turn/Event/Preference 数据结构，但不改变现有 Conversation、Message、Note 的权威语义；Session id 直接复用 Conversation id。
- 是否和 `api-inventory.md` 接口语义冲突：需要新增版本化 Agent API；旧 `/api/chat/free*` 保持兼容适配一个发布周期，必须同步 API 文档。
- 是否会重新引入 `known-pitfalls.md` 中的问题：通过后端原子持久化、明确终态、同会话并发门禁、token 脱敏、ready gate 和打包契约避免重引入；实施必须新增对应测试。
- 是否影响本地数据或线上服务：影响本地 SQLite、运行时目录、桌面 sidecar 生命周期、CLI 安装和发布 CI；不改变现有线上 API 服务，未来网页后端可加载同一 SDK。
- 是否影响用户已确认交互：按确认实现；UI/CLI 会话共享、默认模型、危险操作审批、CLI 命令和数据目录边界均已固定。

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是。
- 推荐下一步：
  - [x] 使用 doc-driven 生成 canonical requirement。
  - [x] 生成增量 Change Spec 和设计规格并交用户书面审阅。
  - [ ] 用户批准设计规格后，使用 `superpowers:writing-plans` 生成分阶段实施 Plan。
  - [ ] 依据 Plan 生成文件级执行 Spec，再进入实现。
- 计划必须覆盖的验收标准：第 1–20 条，按 SDK foundation、binding/platform、Agent Host/API、UI/CLI、service/packaging、迁移验证拆分检查点。
- 计划必须补充的验证：Rust conformance、FFI smoke、Python binding、API/SSE 重连、SQLite 幂等迁移、UI/CLI 同会话纵向、桌面退出后 CLI 续跑、PyInstaller/Tauri/CI 产物和全量回归。
