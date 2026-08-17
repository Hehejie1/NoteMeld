# 跨平台 NoteMeld Agent SDK 与统一 UI/CLI 执行规格

日期：2026-08-14
状态：Superseded（不得继续执行）
批准依据：用户于 2026-08-14 回复“规格确认”
实施计划：`docs/superpowers/plans/2026-08-14-universal-agent-sdk-unified-cli.md`
设计规格：`docs/superpowers/specs/2026-08-14-universal-agent-sdk-unified-cli-design.md`
替代规格：`docs/superpowers/specs/2026-08-17-agent-sdk-single-runtime-execution.md`

> 用户于 2026-08-17 明确取消旧 Python Agent compatibility/rollback。本文只保留历史实施证据，新的开发必须以替代规格为准。

## 1. 执行目标与边界

本规格把已批准设计转换为执行期间不可随意改变的工程约束。实施必须按计划 Task 1–19 顺序通过 Gate A–G；任何阶段失败时停在最近通过的 Gate，不得跳过契约、兼容性或打包验证。

交付范围固定为：

- 单一 Rust Agent SDK 源码与桌面、服务端、iOS、Android、OpenHarmony 构建产物。
- FastAPI 进程内 Agent Host、版本化 Session/Turn/Event API。
- React UI 与 `notemeld agent` CLI 共享 Conversation、SQLite、默认模型和工具/来源结果。
- 现有 Python Agent Core 保留一个发布周期作为 conformance oracle 与显式 rollback。
- 移动/OpenHarmony 只交付 binding、artifact 与最小 harness。

明确不执行：远程设备互调、多端数据同步、Harbor adapter/benchmark、完整移动应用、全量 Rust 重写 Note/Wiki/MCP 业务工具。

## 2. 执行方法

### 2.1 顺序和状态

- 唯一任务清单是实施计划中的 19 个 Task；执行者逐项把 `- [ ]` 改为 `- [x]`。
- Task 内严格执行 red → green → focused regression → commit。
- 只有当前 Gate 的所有 Task 和验证通过后，才能进入下一 Gate。
- 发现设计冲突时先更新 canonical requirement、Change Spec、设计规格和本执行规格，再继续实现。
- 不允许用“后续补测试”“临时双写”“先复制一套移动 loop”等方式跨越 Gate。

### 2.2 Git 与脏工作区

- 当前仓库存在用户自有 staged、unstaged 和 untracked 改动；每次提交必须使用显式文件列表核对。
- 推荐执行前创建 `codex/universal-agent-sdk` 隔离分支/工作树；若用户选择当前工作区执行，只提交当前 Task 的明确文件。
- 禁止 reset、checkout 或删除用户改动。
- 每个 Task 使用计划中固定的 commit message；验证失败不提交。

### 2.3 实现 feature gates

执行期只允许以下运行模式：

| 配置 | 含义 | 默认值 |
|---|---|---|
| `NOTEMELD_AGENT_RUNTIME` | `rust` 或 `python_oracle` | Gate D 前 `python_oracle`；Gate E 起 `rust` |
| `NOTEMELD_AGENT_API_ENABLED` | 暴露 `/api/agent/v1` | Gate D shadow 测试起 `true` |
| `NOTEMELD_AGENT_LEGACY_ADAPTER` | `/chat/free/stream` 是否转发新 Host | Gate E 起 `true` |

规则：

- `rust` 初始化失败不得静默切换 `python_oracle`，必须报告 `AGENT_RUNTIME_UNAVAILABLE`。
- rollback 必须由显式配置触发并记录安全日志。
- 新 UI 与 CLI 上线后只调用 Agent v1，不读取上述 feature gate 来自行选择 loop。

## 3. 工具链与依赖基线

### 3.1 Rust

- Edition：2021。
- 开发/CI toolchain：`1.97.1`，写入 `agent-sdk/rust-toolchain.toml`。
- MSRV：`1.85.0`；每次 release 在 MSRV 与 pinned toolchain 各执行一次 core workspace 测试。
- 锁定策略：workspace dependency 使用下面的精确 minor 线，`agent-sdk/Cargo.lock` 提交并锁定实际 patch；发布构建必须加 `--locked`。

```toml
[workspace.dependencies]
async-trait = "0.1.92"
chrono = { version = "0.4.45", features = ["serde"] }
futures = "0.3.34"
serde = { version = "1.0.229", features = ["derive"] }
serde_json = "1.0.151"
thiserror = "2.0.20"
tokio = { version = "1.53.1", features = ["macros", "rt-multi-thread", "sync", "time"] }
uuid = { version = "1.24.0", features = ["v4", "serde"] }
```

Gate C 引入的直接依赖固定为以下兼容线，实际 patch 同样由提交的 `Cargo.lock` 固定：

```toml
uniffi = "0.31"
rusqlite = { version = "0.38", features = ["bundled"] }
clap = { version = "4.5", features = ["derive"] }
reqwest = { version = "0.12", default-features = false, features = ["json", "rustls-tls", "stream"] }
```

许可门禁：直接依赖必须为 MIT、Apache-2.0、MIT OR Apache-2.0、BSD-2-Clause、BSD-3-Clause 或 Unicode-3.0；新增其他许可证必须在 Gate C 前更新本规格并人工确认。使用 `cargo deny check licenses` 生成证据。

本机存在已失效的全局 Cargo `tuna` source replacement；执行不得修改用户全局配置。局部下载使用官方 sparse registry override，CI 直接使用官方 registry：

```bash
cargo --config 'source.crates-io.replace-with="notemeld-sparse"' \
  --config 'source.notemeld-sparse.registry="sparse+https://index.crates.io/"' \
  generate-lockfile --manifest-path agent-sdk/Cargo.toml
```

### 3.2 Python/Frontend/Desktop

- Python runtime：3.11；binding wheel tag 至少覆盖 CPython 3.11。
- FastAPI、SQLAlchemy、Pydantic 复用当前 backend 锁定版本，不另建第二个依赖环境。
- Node 20、pnpm 9，复用现有 frontend lockfile。
- Tauri 2，桌面 crate 继续独立构建，只消费对应 target 的 SDK/CLI artifact。
- Swift Package、Gradle/AAR、OpenHarmony HAR/N-API 版本必须与 SDK `0.1.0` 和 schema `1` 一致。

## 4. 稳定协议

### 4.1 标识与版本

- `schema_version`：字符串 `"1"`。
- `sdk_version`：首版 `"0.1.0"`。
- `session_id`：现有 `Conversation.id`。
- `turn_id`、`event_id`、`request_id`：UUID 字符串。
- `sequence`：每 Turn 从 1 开始严格递增的无符号 64 位整数。
- 时间：UTC RFC3339，数据库允许现有 datetime 存储，但 API 必须规范化为 RFC3339。

### 4.2 Turn request

```json
{
  "schema_version": "1",
  "request_id": "uuid",
  "session_id": "conversation-id",
  "input": {
    "text": "user input",
    "attachments": [],
    "context_refs": []
  },
  "model_override": null,
  "approval_mode": "interactive"
}
```

- `request_id` 同一 Session 内幂等。
- `approval_mode` 只允许 `interactive`、`deny`、`allow_safe`；CLI `--yes` 只映射为 `allow_safe`，不能跳过 SDK 标记为不可自动批准的操作。
- 输入文本 trim 后为空且无 attachment/context 时返回 `INVALID_INPUT`。

### 4.3 Event envelope

外层字段固定为：`schema_version`、`event_id`、`sequence`、`session_id`、`turn_id`、`timestamp`、`type`、`payload`。

v1 类型固定为：

- `turn.started`
- `message.started`
- `message.delta`
- `message.completed`
- `tool.started`
- `tool.progress`
- `tool.completed`
- `approval.required`
- `approval.resolved`
- `usage.updated`
- `turn.succeeded`
- `turn.failed`
- `turn.cancelled`
- `turn.interrupted`

终态事件每 Turn 恰好一个。客户端必须忽略未知 v1 event type 并继续 sequence，不得因未知事件丢弃已知后续事件。

### 4.4 Turn 状态机

允许转换固定为：

```text
CREATED -> RUNNING
RUNNING -> WAITING_APPROVAL | CANCELLING | SUCCEEDED | FAILED | CANCELLED | INTERRUPTED
WAITING_APPROVAL -> RUNNING | CANCELLING | FAILED | CANCELLED | INTERRUPTED
CANCELLING -> CANCELLED | FAILED | INTERRUPTED
```

所有终态不可再转换。Host 启动时把本实例数据目录内遗留的 `RUNNING`、`WAITING_APPROVAL`、`CANCELLING` 标为 `INTERRUPTED` 并补写终态事件。

## 5. 数据库执行契约

不创建 `agent_sessions`。新增表为 additive、idempotent，旧数据库可直接打开。

### 5.1 `agent_turns`

| 字段 | 约束/语义 |
|---|---|
| `id` | PK，Turn UUID |
| `session_id` | 非空，引用 `conversations.id` |
| `request_id` | 非空；与 session 组成唯一幂等键 |
| `status` | 非空，受 Turn 状态枚举约束 |
| `model_provider_id` | nullable，记录实际模型 |
| `model_name` | nullable，记录实际模型 |
| `error_code` | nullable，稳定安全错误码 |
| `error_message` | nullable，脱敏消息 |
| `created_at/started_at/finished_at/updated_at` | 生命周期时间 |

### 5.2 `agent_events`

| 字段 | 约束/语义 |
|---|---|
| `event_id` | PK |
| `turn_id` | 非空，引用 `agent_turns.id` |
| `sequence` | 非空，与 turn 唯一 |
| `event_type` | 非空 |
| `payload_json` | 非空 JSON，不含 secret |
| `created_at` | 非空 |

### 5.3 `agent_preferences`

| 字段 | 约束/语义 |
|---|---|
| `scope` | PK，首版固定 `global` |
| `default_provider_id` | nullable |
| `default_model_name` | nullable |
| `updated_at` | 非空 |

实际模型继续写入助手 `conversation_messages.meta`；sources/tool summaries 继续使用现有消息字段/JSON 语义。用户消息、助手最终消息、Turn 终态和终态 event 的写入边界由 `AgentStore` 事务控制，客户端不得写重复副本。

## 6. API 与安全契约

固定 API：

```text
POST /api/agent/v1/sessions
GET  /api/agent/v1/sessions
GET  /api/agent/v1/sessions/{session_id}
POST /api/agent/v1/sessions/{session_id}/turns
GET  /api/agent/v1/turns/{turn_id}
GET  /api/agent/v1/turns/{turn_id}/events
POST /api/agent/v1/turns/{turn_id}/cancel
POST /api/agent/v1/turns/{turn_id}/steer
POST /api/agent/v1/turns/{turn_id}/approvals/{approval_id}
GET  /api/agent/v1/preferences/model
PUT  /api/agent/v1/preferences/model
```

- Agent mutation 和 event stream 全部要求当前本机 session token；token 只存在于 mode 0600 descriptor/进程环境，不进入 URL、stdout 或日志。
- Host 默认仅监听 `127.0.0.1:8483`；网页后端部署时由服务端认证层包装，不因 localhost 规则直接暴露。
- SSE 使用 `id`、`event`、`data` 三行；`Last-Event-ID` 与 `after_sequence` 等价。
- 错误 HTTP 映射：无效输入 400、认证 401/403、不存在 404、session busy/幂等冲突 409、runtime unavailable 503、未分类内部错误 500。
- 错误 body 继续遵守项目 ResponseWrapper；SSE 建连后的错误使用 `turn.failed`/安全 error event。

## 7. Host 生命周期

- 源码 `notemeld start`、安装版桌面和 CLI 使用同一 descriptor schema 与健康检查。
- descriptor 写入现有 NoteMeld 数据根下的 runtime 子目录，临时文件 + fsync + atomic replace；Unix mode 0600。
- CLI 优先复用 `sdk_version`、schema、data root 均兼容的健康 Host；无 Host 时启动与当前安装形态匹配的 backend。
- 桌面只停止自己创建且没有活动 CLI Turn/长任务的 Host；`notemeld stop` 是明确停止入口。
- 不自动弹出交互终端窗口；“同时提供终端客户端”表示 CLI 已安装、Host 已可发现并可立即连接。

## 8. CLI 契约

固定入口：

```text
notemeld agent
notemeld agent -p <prompt>
notemeld agent --conversation <id>
notemeld agent --new
notemeld agent --resume <id>
notemeld agent --output text|json|jsonl
```

REPL 命令：`/model [provider/model]`、`/new`、`/resume <id>`、`/sessions`、`/exit`。

- `text` 面向人类；`json` 只在完成后输出一次 summary；`jsonl` 原样逐行输出 event envelope。
- machine output 的 stdout 不含日志、spinner、提示或 token；全部诊断进 stderr。
- Ctrl-C 首次请求 cancel 并等待终态，第二次强制退出客户端但不伪造服务端终态。
- one-shot 遇审批默认拒绝；只有 `--yes` 才启用 `allow_safe`。
- 默认会话规则：REPL 无参数新建；`--conversation/--resume` 续聊；one-shot 无 session 新建。

## 9. 平台产物契约

| 平台 | 必须产物 | 最小验证 |
|---|---|---|
| macOS arm64/x64 | dylib、Python wheel、CLI | fake Turn + Host load |
| Windows x64 | DLL、Python wheel、CLI.exe | fake Turn + Host load |
| Linux x64/arm64 | so、Python wheel/host bundle、CLI | fake Turn + Host load |
| iOS device/simulator | XCFramework、Swift package | Swift harness terminal event |
| Android arm64-v8a/x86_64 | so、AAR/Kotlin wrapper | instrumented/JVM harness |
| OpenHarmony arm64 | so、HAR/N-API/ArkTS wrapper | ArkTS harness terminal event |

每个 archive 必须包含 `artifact-manifest.json`：`sdk_version`、`schema_version`、target、binding version、SHA-256、license inventory。

## 10. 验收标准到任务映射

| Canonical AC | 主要任务 | 强制证据 |
|---|---|---|
| 1–2 | 1–7 | SDK matrix、conformance snapshots、harness logs |
| 3 | 6、9、11 | binding load/API unavailable tests |
| 4–5 | 8、10、14、15 | UI↔CLI 同会话 E2E |
| 6–10 | 5、8、10、11 | concurrency/idempotency/replay/recovery tests |
| 11–12 | 8、10、14、15 | preference/fallback cross-entry tests |
| 13 | 3、6、10、14、15 | approval policy tests |
| 14–15 | 15 | CLI contract/snapshot tests |
| 16–17 | 16–17 | runtime discovery/ownership/exit tests |
| 18–19 | 12–18 | compatibility/data/release regression |
| 20 | 19 | verification report with exact command results |

任何 AC 缺少证据时，canonical requirement 状态不得改为 `Verified`。

## 11. 性能、背压与恢复门禁

- 排除模型/工具时间，Host `start_turn` p95 ≤ 50ms；用 1000 次 fake-driver benchmark 测量。
- model delta 进入有界 channel；默认容量 256，满时背压，不丢事件。
- 文本 checkpoint：满足任一条件写库——累计 256 字符、距上次 250ms、收到 message completed/terminal event；不得每 token commit。
- event 持久化与 live publish 顺序固定为 persist → commit → publish。
- SSE 重连先读库到当前 high-water mark，再加入 live broker；以 sequence 去重。
- Host 停机等待活动 Turn 的默认 grace period 为 30 秒；超时标记 `INTERRUPTED`。
- approval 默认超时 5 分钟；超时按 deny 处理并产生 `approval.resolved`。

## 12. 安全与隐私门禁

- secret 字段名（大小写不敏感）至少覆盖：`api_key`、`authorization`、`cookie`、`token`、`secret`、`password`。
- Driver 原始异常只进入内存诊断；持久化/API 返回稳定 code + 脱敏 message。
- runtime descriptor 不被 frontend 静态资源、日志、crash report 或 Release artifact 收集。
- FFI 输入做长度上限和 UTF-8/JSON 校验；panic 使用 `catch_unwind` 转为稳定错误。
- 工具 risk classification 与审批发生在共享 SDK/Host 路径，CLI 不能通过自定义 renderer 绕过。

## 13. 回滚触发器

下列任一情况阻止 consumer cutover：

- oracle conformance 的事件顺序、工具结果、abort/steer/max-turn 任一不一致。
- 新旧 chat compatibility 产生重复消息或回答/source 语义漂移。
- SDK binding 在任一桌面发布 target 无法加载。
- desktop exit 会杀死非桌面拥有的活动 Host。
- machine CLI stdout 混入日志或 secret。
- 历史数据库升级后 Conversation/Note/Wiki 任一不可读。

回滚动作：

1. Gate D/E：显式设置 `NOTEMELD_AGENT_RUNTIME=python_oracle`；保留 additive 表。
2. Gate F：UI 恢复 legacy adapter 调用；禁用新 CLI 安装，不删除会话/Turn 数据。
3. Gate G：撤下 SDK/CLI 新资产，保留原 DMG/MSI 命名和旧数据兼容。

## 14. 完成声明规则

只有执行计划 Task 1–19 全部完成、Gate A–G 全部通过、20 条验收标准有证据、系统文档已同步，才可以声明“统一 Agent SDK/CLI 已完成”。

Harbor 接入必须在本需求 Verified 后新建独立 canonical requirement 和 Change Spec；不得把 Harbor 适配塞入本执行分支。
