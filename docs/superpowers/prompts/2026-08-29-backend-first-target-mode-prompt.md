# 目标模式提示词：NoteMeld 多端同步后端优先实现

请在 NoteMeld 项目中执行本任务。目标是先完善后端逻辑和跨端协议，暂不实现任何 UI、移动端页面或视觉设计。

## 任务目标

基于以下权威文档实施：

- `docs/requirements/2026-08-29-multiplatform-cloud-sync-and-device-control.md`
- `docs/superpowers/plans/2026-08-29-multiplatform-sync-plan.md`
- `docs/superpowers/specs/2026-08-29-multiplatform-sync-spec.md`
- `docs/superpowers/reviews/2026-08-29-multiplatform-sync-expert-review.md`
- `docs/system/current-architecture.md`
- `docs/system/product-rules.md`
- `docs/system/data-model.md`
- `docs/system/api-inventory.md`
- `docs/system/known-pitfalls.md`

实现一个可本地运行、可测试、可供未来各端接入的后端 vertical slice：

```text
云端 FastAPI：管理员/用户登录 → 设备注册 → 云端会话 → Agent turn → 事件流
本地 Backend：设备配对 → 授权 → E2EE remote command → 宿主本地 queue → Agent Host 执行
```

## 强制边界

1. 只改后端、云端服务、协议 schema、数据库迁移、SDK contract 和测试；不要写 React、Tauri UI、iOS、Android、Harmony UI。
2. 不修改或复制 `notemeld-agent-sdk` 的 canonical Agent loop；必要的通用 queue/pause/event contract 才在 SDK 中增加最小 port。
3. `NoteMeld/cloud/` 与 `NoteMeld/backend/` 前期物理分开，不直接 import 对方 Python domain package；通过版本化 HTTP/JSON schema 和 SDK artifact 复用协议。
4. 保留现有本地 `/api/agent/v1`、MCP、桌面启动、Note/Conversation/Wiki authority 和 `{code,msg,data}` response wrapper。
5. 不做公网部署，不声称商用安全通过；必须把未实现的 P0/P1 门禁记录为 blocked/not implemented。
6. 所有新表使用独立 forward-only migration registry，不修改共享 `PRAGMA user_version`。

## 实施顺序

### Phase 0：现状检查与实现计划

- 分别检查 `NoteMeld` 和 `notemeld-agent-sdk` 的 git status、分支和现有入口。
- 阅读上述文档和相关测试；搜索现有 AgentHost、SQLite、session token、workspace、MCP 配置和原子写工具。
- 先输出一份短 plan，列出具体文件、迁移、API、测试和风险；发现现状与文档冲突时以源码/测试为准并记录。

### Phase 1：共享协议和本地数据模型

在不耦合 Python domain 的前提下建立版本化 schema：

- `protocol_version`、`session_kind`（`local` / `cloud_native` / `device_remote`）。
- `account_id`、`login_handle`、`device_id`、`authority_epoch`。
- `session_id`、`command_id`、`request_id`、`payload_hash`、`event_seq`、`snapshot_seq`。
- `accepted`、`received`、`processed`、`host_offline`、`delivery_unknown`、`needs_attention` 等错误/终态。
- 未知字段可前向兼容；未知 major version 必须拒绝。

本地新增独立 migration registry 和必要表，至少覆盖：

- cloud users/auth metadata（不保存明文密码/token）。
- devices、device grants、pairing attempts。
- session locators、session commands、event receipts、sync conflicts。
- session archive（设备本地收纳状态）。
- workspace backup/restore/migration job 状态和容量统计。

不得复制 `note_documents`、`conversations`、`agent_events` 正文作为第二 authority；只保存映射、游标和 provenance。

### Phase 2：Cloud FastAPI

在 `NoteMeld/cloud/` 创建独立 FastAPI 服务，至少实现：

#### 账户和管理后台 API

- bootstrap admin 从 `NOTEMELD_CLOUD_ADMIN_USERNAME` / `NOTEMELD_CLOUD_ADMIN_PASSWORD` 初始化，重复启动幂等。
- 密码使用 Argon2id 或 bcrypt/cryptography 官方安全实现，最少 12 字符。
- admin 登录、退出、token rotate/revoke。
- admin 对普通云端用户执行 CRUD、禁用、设备撤销和审计查询。
- 本地 profile name 与云端登录身份分离；云端使用唯一 `login_handle`，显示 `cloud_username` 可按产品规则处理。
- 登录失败按账号/IP 限流；错误不能泄露账户是否存在。

#### Cloud-native Session API

- 创建云端 workspace/session。
- 从本地 full-share snapshot 创建新云端 session。
- 按 command 顺序提交消息，单 session 单 active Turn。
- snapshot 查询、event cursor 拉取/订阅、复制分支、收纳和硬删除。
- 云端 workspace 默认写入 `NOTEMELD_CLOUD_DATA_DIR/workspaces/`，禁止写入代码目录。
- 云端 Agent 复用 SDK canonical runtime，但使用独立 CloudWorkspaceProvider、CloudModelProvider、CloudCapabilityProvider 和 CloudSecretStore。

#### Workspace 基础能力

- 默认读权限；写入、删除、执行通过 capability grant/approval。
- canonical path、workspace root、symlink、`..`、绝对路径和压缩包安全校验。
- 原子写入、崩溃恢复、磁盘容量统计/告警、备份/恢复和数据迁移 job 状态 API。
- 文件大小、数量、深度、并发和配额限制；磁盘不足返回稳定错误码。

### Phase 3：Device remote relay

实现云端实时 WebSocket relay：

- relay 只做认证、recipient/size/rate/envelope 校验和实时转发。
- 不解密 E2EE payload；不持久化正文、密文或未送达 command。
- 禁止 request body、APM body、core dump 和请求录制。
- relay `accepted` 不等于成功；宿主 `received` receipt 才是控制端成功边界。
- 宿主离线或在线检查竞态返回 `host_offline` / `delivery_unknown`，禁止云端重试。
- 增加反压、帧大小、频率和连接数限制。

提供 transport abstraction：

- `LanDirectTransport`：先尝试同局域网认证连接。
- `CloudRelayTransport`：失败后使用 WebSocket relay。
- 两者复用同一 E2EE frame schema；第一期可以让 LAN adapter 使用 deterministic/local fixture，但不能伪装为公网直连完成。

### Phase 4：E2EE 和远程权限

不要自研密码学，使用成熟开源库：

- X25519 临时密钥交换。
- Ed25519 设备身份签名。
- HKDF 密钥派生。
- ChaCha20-Poly1305 或平台等价 AEAD。
- sequence、nonce、AAD 和 replay protection。

必须实现：

- 双向配对确认和设备公钥绑定。
- session key epoch、重连轮换、设备撤销后重握手。
- standard / super_admin scope。
- workspace scope、命令过期、审批 nonce、审批超时。
- 宿主本地 kill switch 和紧急撤销。
- 危险能力 allowlist；默认权限下危险操作只能宿主审批。
- 云端不解密 device_remote frame。

### Phase 5：队列、恢复与 Agent Host 接入

- 本地 remote session 和 cloud-native session 都使用单写者串行 mailbox。
- command ledger 使用 `request_id + payload_hash` 幂等。
- authority lease/fencing/epoch 防止云端多实例或宿主重启双执行。
- event 使用单调 `event_seq`；重连发现 gap 时请求 snapshot，而不是依赖 relay 历史。
- 可靠语义明确为 at-least-once；未知副作用进入 `needs_attention`，禁止自动重放。
- 宿主离线时冻结远程会话并拒绝新 command；宿主重启后支持“继续原任务”或“终止并处理下一条”。
- 远程 command 必须最终进入现有 Agent Host，不得由 relay 或控制端直接调用模型/工具。

## API 和错误契约要求

所有普通 HTTP API 使用现有 `{code,msg,data}` wrapper，并补充：

- OpenAPI/JSON schema。
- 稳定错误码：`invalid_credentials`、`rate_limited`、`device_revoked`、`host_offline`、`delivery_unknown`、`session_frozen`、`permission_denied`、`payload_conflict`、`needs_attention`、`quota_exceeded` 等。
- request id、idempotency key、payload hash、分页、cursor、最大 body/frame/file 限制。
- correlation id、trace id 和 authority epoch；日志脱敏。

## 必须写的测试

至少补充：

1. admin bootstrap 幂等、普通用户 CRUD、登录限流、密码 hash、token rotate/revoke。
2. 用户/设备/权限越权、撤销即时生效、share token 独立 expiry/role。
3. E2EE 握手、篡改、重放、错 recipient、密钥轮换和设备撤销。
4. relay 在线/离线竞态、received receipt、断线失败、背压和限流；确认无 payload 持久化。
5. 同 session 并发 command 排队、幂等、乱序/重复 event、snapshot gap、lease fencing。
6. 宿主崩溃/重启、暂停/恢复、未知副作用 `needs_attention`。
7. workspace 路径穿越、symlink、压缩炸弹、磁盘满、原子写、备份/恢复/迁移。
8. cloud-native Agent 最小真实 SDK turn、事件流、取消、审批和硬删除。
9. 跨服务 contract fixture：cloud ↔ desktop backend ↔ WebSocket relay。

## 完成标准

- 所有新增代码有对应测试和文档。
- `python3 -m compileall`、后端相关 pytest、协议/schema 校验通过。
- 现有 NoteMeld 核心回归不被破坏。
- 生成 `docs/superpowers/tests/2026-08-29-multiplatform-backend-first.md`，只记录命令、结果、指标和未验证项。
- 更新 `docs/system/api-inventory.md`、`data-model.md`、`current-architecture.md`、`known-pitfalls.md` 中实际已落地的部分。
- 不修改 UI；最终报告列出下一阶段需要 Stitch 设计和各端适配的 API/事件依赖。

执行时遇到安全、协议或数据 authority 不确定点，先停止该子步骤、记录证据和最小决策问题，不得猜测实现。
