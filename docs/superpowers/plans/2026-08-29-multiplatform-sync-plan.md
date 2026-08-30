# Plan：多端会话、云端 Agent 与设备协同

状态：Clarifying（商用评审后）  
Canonical requirement：[`2026-08-29-multiplatform-cloud-sync-and-device-control.md`](../../requirements/2026-08-29-multiplatform-cloud-sync-and-device-control.md)

## 1. 目标架构

分成两个数据面，复用一个版本化 Agent Protocol：

- **Cloud-native data plane**：云端 workspace + 云端 Agent runtime + 云端持久化；各端是客户端。
- **Device-remote data plane**：宿主本地 workspace + 宿主 Agent runtime + E2EE P2P session；云端只提供账号认证、设备发现、信令和实时 relay，不保存消息或离线 mailbox。

两条路径都使用“每 Session 单写者串行 mailbox”：宿主/云端 runtime 是唯一 queue authority，控制端只提交 command，不直接写 authority store。

## 2. 实施阶段

### P0.5（首期）：全端 mock 骨架（仅 UI/fixture，不含生产认证与真实 relay）

- `cloud/` 建立 FastAPI mock 服务：健康检查、脱敏登录 fixture、云端 session fixture、最小 Agent turn stub/SDK 接入、实时 relay fixture；不接入真实账号、密钥或生产 relay。
- `backend/` 和 `frontend/` 增加 local/cloud/device-remote 三种 session 路由与统一 client；保留现有本地 `/api/agent/v1`。
- `desktop/` 验证 Windows/macOS/Linux 共用的 runtime 配置和本地 Host 适配边界。
- `ios/`、`android/`、`harmony/` 先完成登录、设备注册、云端 session 列表、远程连接和事件订阅的原生壳与协议 fixture 联调。
- 实现最小链路：注册/登录 → 注册设备 → 创建云端会话 → 发送消息 → 事件回传；以及配对 → 在线 relay → 宿主回执 → 本地队列执行。
- 首期允许 Agent 使用 deterministic/mock driver 验证跨端协议，真实云端模型和完整插件能力随后接入；UI 先按 Stitch 设计实现主体结构。

### P0：冻结身份、账号、加密和协议（当前阻塞）

- 定义用户名/密码账户、随机或平台原生 device id、账户 token、设备 token、share token、轮换/撤销/恢复。
- 定义 E2EE handshake、relay frame、实时送达确认和 replay protection；宿主离线立即失败，不保留云端队列。
- 定义 `local`、`cloud-native`、`device-remote` 三种 session kind。
- 产出威胁模型和 Cloud/Remote Protocol v1 schema。
- 增加成熟握手（建议 Noise/MLS）、设备公钥认证、前向保密、密钥轮换和成员撤销。
- 固化 `account_id/login handle + password`，用户名仅展示；定义 PAT/设备 token 的 PoP、jti、scope、轮换和恢复。
- 固化 relay 长连接、宿主 receipt 成功边界、断线竞态、帧大小/频率/背压和 no-body logging。
- 增加 queue lease/fencing、authority epoch、event cursor/gap、at-least-once + idempotency 语义。

### P1：单仓目录与共享客户端层

- 在 `NoteMeld/` 下建立 `cloud/`、`ios/`、`android/`、`harmony/` 边界（名称待最终确认）。
- Web/桌面复用 `frontend/` 的 TypeScript protocol client；移动端通过 SDK binding 消费 canonical events。
- 不移动或复制独立 `notemeld-agent-sdk` 源码。

### P2：云端原生 Agent 纵向闭环

- 云端身份注册、密码/token auth、统一 workspace、session mailbox、Agent runtime、事件订阅和硬删除。
- 本地会话 full-share 创建新 cloud-native session；Skill/插件/Application/secret 不复制。
- 桌面/Web 先完成创建、查看、发送、排队、收纳和复制分支。

### P3：设备配对与 E2EE 远程会话

- 双向设备配对、默认/超管授权、workspace scope、设备撤销。
- snapshot request + live publish/subscribe；relay 不解析 payload。
- 宿主模型/工具/Skill/插件/Application discovery，只投影宿主能力。

### P4：暂停、重启与可靠队列

- 宿主 session mailbox、command ledger、event receipt、pause checkpoint、needs_attention 和恢复选择；云端只转发实时 frame。
- 宿主离线期间冻结会话入口；恢复时继续原 Turn 或终止并处理下一条。
- 增加重复/乱序/断线/重启/副作用不确定态回归。

### P5：移动端和 Application Association

- iOS、Android、Harmony 完成会话、远程设备、审批、队列和应用关联 UI。
- `ApplicationAssociation` 将同一业务应用的多平台包关联；未安装/不兼容时只展示。

### P6：安全与跨端验收

- token 泄漏、越权设备、relay 明文、重放、撤销、路径穿越、宿主审批绕过测试。
- 桌面↔移动、移动↔移动、Web↔云端、设备离线/重启完整 E2E。
- 本期不做生产上线或公网部署。
- 商用前补齐租户隔离、磁盘加密、备份恢复/可验证删除、配额/限流、沙箱/MCP SSRF 防护、供应链签名、SLO/告警和 chaos/load/fuzz 测试。

## 3. 分仓职责

- `notemeld-agent-sdk`：canonical event、session mailbox/queue port、pause/checkpoint 和 remote authority trait；不拥有账户或云端服务。
- `NoteMeld/backend`：本地 Agent Host、本地 authority、设备远程执行和现有数据投影。
- `NoteMeld/cloud`：账户/密码/token、cloud-native Agent、实时 relay 和云端 workspace；不保存 device-remote 消息。
- `NoteMeld/frontend`、`desktop`：Web/桌面 UI 与 Windows/macOS/Linux 桌面运行时。
- `NoteMeld/ios|android|harmony`：原生 UI、secure storage、设备密钥和 SDK binding。
- `notemeld-applications`：独立应用包及跨平台 manifest identity；不并入产品源码。

## 4. 关键门禁

1. P0 安全协议和身份语义未签字，不开始数据库或 API 实现。
2. 同一 Session 永远只有一个 queue authority 和一个 active Turn。
3. relay 日志、数据库和 tracing 中不得出现 P2P 明文；relay 不保存未送达消息。
4. 默认授权不能在控制端批准危险工具；超管必须显式授权。
5. 未确认副作用的恢复只能 `needs_attention`，不能自动重放。
6. 每阶段保留 local-only fallback，不破坏现有桌面入口。

## 5. 回滚

- 所有新入口受 feature flag 控制；关闭后回到现有 local-only 会话。
- 新表使用独立 forward-only registry，不修改共享 `PRAGMA user_version`。
- 协议带 major version，旧客户端遇到未知 major 必须拒绝而非猜测。
- full-share 创建新 session，失败不会修改或删除原本地会话。

## 6. Agent 复用方案

- 不把 `backend/app/agent_host` 整体复制到 `cloud/`。
- 把创建 session、提交 turn、事件流、审批、取消和串行 queue 抽成平台无关的 Agent application service/contract。
- 桌面注入 `LocalWorkspaceProvider`、本地 ModelProvider、桌面 capability registry 和本地 secret store。
- 云端注入 `CloudWorkspaceProvider`、云端 ModelProvider、云端 capability registry 和云端 secret store。
- 两者都通过同一 `notemeld-agent-sdk` artifact 运行 canonical loop；差异只存在于 storage、transport 和 provider adapter。
- 远程控制只向宿主的本地 Agent service 提交 command，不允许控制端直接调用 provider。

## 6. 已确认的产品决策

- 云端同时提供 cloud-native Agent 和 P2P remote relay，两者数据边界不同。
- remote relay 仅实时转发；宿主离线时发送失败，已接收队列在宿主设备。
- 用户名/密码 + token；token 丢失使用恢复密钥或已授权设备恢复。
- 设备 ID 算法按平台选择，只要求分布式唯一和可持久识别。
- remote host 与 cloud-native workspace 分别负责硬删除；不设 7 天撤销期。
- share token 支持向他人授权；应用/Skill/插件仍按既定隔离规则处理。

## 7. 评审结论

三方专项评审认为方向可行，但当前文档还不是商用安全规格。P0 阻塞项见 P0 阶段；P1（云磁盘 HA/备份、移动后台、Linux 发布、配额计费、审计和运维）必须在公网 Beta 前完成。
