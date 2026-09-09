# Spec：多端会话、云端 Agent 与设备协同

状态：Clarifying（商用安全评审后）  
Canonical requirement：[`2026-08-29-multiplatform-cloud-sync-and-device-control.md`](../../requirements/2026-08-29-multiplatform-cloud-sync-and-device-control.md)

## 1. Session 类型与 authority

| kind | workspace authority | Agent runtime | queue authority | 云端可读正文 |
|---|---|---|---|---|
| `local` | 当前设备 | 当前设备 | 当前设备 | 否 |
| `cloud_native` | 云端 | 云端 | 云端 | 执行时必须可读，待用户确认 |
| `device_remote` | 宿主设备 | 宿主设备 | 宿主设备 | 否，只中转 E2EE frame |

`copy_branch` 始终生成新 `session_id` 和完整 snapshot；可记录 `copied_from` provenance，但无运行时父子同步。

## 2. 身份与认证

建议结构：

- `account_id`：注册时生成 UUIDv7，不由用户名决定。
- `local_profile_name`：设备内显示名，与云端认证无关。
- `cloud_username`：由 bootstrap admin 创建和维护的云端登录名；在单个云端实例内唯一。
- `login_handle`：云端为 `cloud_username` 分配的 opaque 主键；与 `password_hash` 共同完成密码登录。
- `password_hash`：云端只保存不可逆密码哈希；密码不在设备间同步。
- `device_keypair`：设备本地产生，私钥进入 Keychain/Keystore/Harmony secure storage/桌面安全存储。
- `device_id`：各平台可采用不同算法，但必须稳定、可持久识别、具备碰撞防护；不强制硬件指纹。
- `account_token`：类似 PAT，用于设备注册/恢复；只存 hash，支持 scope/expiry/revoke/rotate。
- `device_token`：设备注册后签发的短期凭证，与设备公钥绑定并轮换。
- `share_token`：可选，用于把会话授权给其他身份，带 role、session、expiry 和 single-use 属性。

bootstrap admin 由 `NOTEMELD_CLOUD_ADMIN_USERNAME` / `NOTEMELD_CLOUD_ADMIN_PASSWORD` 初始化；管理后台提供普通用户 CRUD、禁用、设备撤销和审计查看。普通用户不能创建新云端账户。

第一版密码策略：最少 12 个字符；允许密码管理器字符；登录失败按账户和 IP 分级限流；不返回“用户名存在/不存在”的差异化错误。部署环境变量 `NOTEMELD_CLOUD_ADMIN_USERNAME`、`NOTEMELD_CLOUD_ADMIN_PASSWORD` 仅用于初始化 bootstrap admin，首次启动后写入哈希并支持轮换；环境变量不得写入日志或配置回显。

share token 的 `expires_at` 与 `role/scopes` 独立字段；`expires_at = null` 表示用户明确选择永久有效，不自动提升权限。

传输层必须 TLS；`device_remote` payload 再做应用层 E2EE。第一版采用成熟开源库实现 X25519 临时密钥交换 + Ed25519 设备身份签名 + HKDF + ChaCha20-Poly1305（或平台等价 AEAD），不自行实现密码学；支持会话密钥轮换、撤销后重握手和 sequence 防重放。token 加密传输不能替代服务端只存 hash、客户端安全存储和轮换。

## 3. Queue 与 Turn 状态

建议状态：

```text
queued -> admitted -> running -> pause_requested -> paused
                  -> waiting_approval
                  -> completed | failed | cancelled | interrupted | needs_attention
```

- `session_command.sequence` 只由 authority 分配。
- 一个 session 只允许一个 `running|waiting_approval|pause_requested` Turn。
- 远程优先尝试认证后的局域网直连（同一 E2EE session），失败再使用云端 WebSocket relay；远程宿主离线时 relay 返回 `host_offline`，不保存未送达 command；已接收 command 由宿主本地 queue authority 排队。
- 云端原生会话的离线队列由云端 runtime 持有。
- 重启后用户选择 `resume_interrupted` 或 `abandon_and_advance`。
- 外部副作用已开始但无法证明结果时进入 `needs_attention`。

## 4. 数据对象

- `UserIdentity(account_id, username, created_at)`
- `Device(device_id, public_key, display_name, platform, id_scheme, status, last_seen_at)`
- `CloudUser(login_handle, cloud_username, password_hash, disabled, roles, created_at)`
- `DeviceGrant(grant_id, controller_device_id, host_device_id, role, scopes, workspace_refs, expires_at, revoked_at)`
- `SessionLocator(session_id, kind, authority_device_id?, cloud_workspace_id?)`
- `SessionCommand(command_id, session_id, sequence, request_id, payload_hash, status)`
- `RemoteFrame(frame_id, session_id, sender_device_id, recipient_device_id, sequence, ciphertext, sent_at)`：仅为内存中的 relay envelope，不建立持久化表。
- `RemoteReceipt(frame_id, recipient_device_id, received_at)`
- `SessionArchive(device_id, session_id, archived_at)`
- `ApplicationAssociation(association_id, logical_app_id, platform, package_id, version_range)`

本地数据库使用独立 `sync_app_migrations`；云端 schema 独立维护。现有 `conversations`、`agent_turns`、`agent_events` 和 `note_documents` authority 不被直接改写。

## 5. 协议

### 5.1 Cloud-native

- `POST /v1/cloud/sessions`：创建空云端会话。
- `POST /v1/cloud/sessions/import`：从本地 full-share snapshot 创建新会话。
- `POST /v1/cloud/sessions/{id}/commands`：提交排队消息。
- `GET /v1/cloud/sessions/{id}/snapshot`：获取当前快照。
- `GET /v1/cloud/sessions/{id}/events?after=`：按 cursor 拉取/订阅事件。
- `POST /v1/cloud/sessions/{id}/copy`：创建独立复制会话。
- `POST /v1/cloud/sessions/{id}/archive`：仅当前设备收纳。
- `DELETE /v1/cloud/sessions/{id}`：按最终 hard-delete authority 执行。

### 5.2 Device-remote

- `POST /v1/devices/register|rotate|revoke`
- `POST /v1/pairings/start|confirm`
- `POST /v1/grants`、`DELETE /v1/grants/{id}`
- `WebSocket /v1/relay/connect`：长连接实时转发；服务器只校验 envelope/recipient/size/rate，不解密或持久化 payload。局域网直连使用相同 frame schema，云 relay 为 fallback。
- relay 成功边界是宿主 `received` receipt，不是 relay `accepted`；宿主离线或连接竞态返回 `host_offline`/`delivery_unknown`，禁止云端重试。
- relay 不提供 `after` 历史拉取；重连后由宿主按 snapshot/event protocol 主动补发。

设备内仍通过 `/api/agent/v1` 进入同一 Agent Host；cloud/relay client 是 adapter，不建立第二套 Agent 状态机。

## 6. 内容复制规则

full-share 包含 conversation、message/event、compression、workspace file、memory、model descriptor、MCP sanitized config、tool/approval record、task state 和 provenance。

明确排除 secret、Skill 内容、插件包、Application 包和私有应用数据。缺失工具只生成 unavailable projection。所有文件携带 content hash、size、MIME 和 logical path；拒绝绝对路径和 `..`。

workspace 默认允许读取；写入、删除、执行和访问 workspace root 之外的路径必须经过 capability grant/用户审批。路径必须 canonicalize，拒绝 `..`、绝对路径越界、符号链接逃逸、压缩炸弹和超出大小/深度/文件数限制的输入。

## 7. 权限

- `standard`：`message.send`、`context.select`、`model.select`、`tool.invoke`；危险工具只能宿主审批。
- `super_admin`：额外 `approval.remote.resolve`、`session.permission.manage`、`session.full_access`。
- authority 每次 command 都重新检查 grant，不信任客户端缓存。
- ApplicationAssociation 只允许打开已安装且兼容的本地应用，不自动安装或执行远端应用代码。

## 8. 加密与安全

- TLS 1.3 保护全部端云传输。
- P2P 远程 frame 使用会话级 E2EE key、AEAD、sequence 和 associated data 防篡改/重放。
- 云端只记录必要的 envelope 元数据和安全审计字段；P2P 消息正文、密文 payload 和未送达 command 不落盘。反向代理、APM、core dump 和请求录制必须关闭 body 收集。
- 云端原生会话允许云端 Agent 在运行时读取云 workspace；remote session 才适用“relay 不可读明文”承诺。
- token/secret/正文不得进入日志；账号 token 只保存单向 hash。

## 9. Agent 复用与目录入口

- Agent 对话服务抽取为平台无关 application service；桌面和云端都调用同一 `notemeld-agent-sdk` canonical loop。
- 第一期 `cloud/` 与 `backend/` 物理分开，不直接 import 对方 Python domain package；双方只依赖版本化 HTTP/JSON、E2EE relay schema 和 SDK artifact。
- 桌面 adapter 提供本地 workspace、桌面模型/secret、插件和文件能力；云端 adapter 提供云 workspace、云模型/secret 和云端 capability。
- `NoteMeld/cloud/`：FastAPI 登录、token、Agent service、relay 和云 workspace；workspace 根目录由 `NOTEMELD_CLOUD_DATA_DIR` 注入，默认使用云端运行数据目录下的 `workspaces/`，不得写入代码包目录；不落 device-remote 消息。
- `NoteMeld/backend/` + `desktop/` + `frontend/`：Windows/macOS/Linux 本地 Host、桌面壳和 Web/桌面 UI。
- `NoteMeld/ios/`、`android/`、`harmony/`：原生客户端、安全存储、设备身份和 SDK binding。
- `NoteMeld/frontend/src/services/`：cloud/device/remote clients。
- `NoteMeld/frontend/src/pages/`：session kind、设备、授权、队列、应用关联页面。
- `NoteMeld/backend/app/agent_host/`：remote authority adapter。
- `notemeld-agent-sdk/crates/agent-session|agent-runtime|agent-events/`：仅在协议需要时增加通用 queue/pause port。

## 10. 测试门禁

- 身份：ID 稳定、token hash/rotation/revoke、设备密钥不导出、用户名重复。
- E2EE：relay 无法解密、篡改/重放/错 recipient 拒绝、TTL/receipt 清理。
- Queue：并发发送严格排序、单 active Turn、离线 frozen、重启两种恢复选择。
- 权限：默认/超管审批位置、撤销即时生效、workspace scope 和 full-access 提升。
- 分享：全量非敏感复制、secret/Skill/plugin/Application 排除、缺失能力投影。
- 生命周期：收纳/恢复、hard delete、复制分支独立、应用跨端关联。
- 跨端：desktop↔iOS/Android/Harmony、mobile↔mobile、Web↔cloud-native。

## 11. 商用 P0 门禁（未完成前不实现生产路径）

- E2EE 成熟握手、设备认证、前向保密、密钥轮换和成员撤销。
- 账号主体、PAT/device token PoP、jti/scope/audience、限流、恢复和管理员 RBAC。
- queue lease/fencing、authority epoch、event cursor/gap、at-least-once + idempotency。
- 云端 Agent sandbox、租户隔离、MCP SSRF/路径/命令注入防护、资源配额。
- relay no-body logging、无持久化证明、帧限额和元数据最小化。
- API JSON schema、错误码、分页、版本兼容矩阵和跨端 contract tests。

## 12. 商用 P1 门禁

云 workspace 备份/恢复/容量告警、移动端后台恢复、Windows/macOS/Linux 签名和发布、插件/应用签名与撤销、审计/SLO/告警、滥用封禁、隐私导出/删除和 load/chaos/fuzz 测试。
