# NoteMeld 首批 Cloud / x64 / Android Agent 与远程连接发布目标

状态：Superseded

superseded_by: [`2026-09-13-cloud-macos-x64-android-agent-release.md`](2026-09-13-cloud-macos-x64-android-agent-release.md)

> 本文保留为 Windows x64 历史范围和既有验证资产索引。2026-09-13 用户将首批桌面范围改为 macOS x64，并补充三端独立 runtime、Cloud 配置同步、`/docs/new-product` 全页面及跨端组件库要求；后续需求与验收以 `superseded_by` 指向的文档为准，本文及 Windows 验收台账不得作为新范围完成证据。

日期：2026-09-12

## 1. 用户目标

首批上线范围固定为：

1. Cloud 能以真实模型正常运行 Agent，并只转发端到端加密的设备消息。
2. x64 桌面客户端能完成本机 Agent 对话，作为控制端连接远程 x64 Host 对话，也能作为 Host 接受授权连接。
3. Android 实体客户端能完成 Agent 对话，并通过 LAN-first / Relay fallback 连接远程 x64 Host 对话。

本需求不以 iOS、Harmony 或完整产品功能矩阵作为首批发布前置。

## 2. 完成定义

- Cloud production RC 使用真实 OpenAI-compatible Provider，命令形成唯一成功终态；deterministic runner 不计入验收。
- x64 和 Android 都能从用户界面发起本地/Cloud Agent 对话并看到最终回答。
- x64-A → x64-B、Android → x64-B 均分别通过 LAN 和 Cloud Relay 完成远程 Agent 对话。
- Cloud Relay 不解密或持久化消息正文；Host durable enqueue 后才返回 receipt。
- Host 离线、网络中断、恢复、重复 request id、授权撤销和危险操作审批均 fail-closed，不产生重复副作用。
- Windows x64、Android 和 Cloud 制品来自同一 RC commit/协议基线，记录签名或 SHA-256/image digest。
- [`验收台账`](../superpowers/tests/2026-09-12-first-batch-agent-remote-release-gate.md) 中全部 19 个 P0 项为 `PASS`。

## 3. 需求分解

### Cloud

- 生产配置、数据库、Workspace、Redis Relay 和真实 Provider readiness 可观测。
- Cloud-native session 支持提交、事件、snapshot、恢复和有界重试。
- Relay 仅处理经授权的 opaque E2EE envelope，执行序列防重放和大小/速率限制。
- 设备/Grant 撤销立即阻止新命令，断线和 Host offline 返回稳定状态。

### Windows x64

- 签名安装包可安装、启动、更新/回滚，sidecar 与 UI ready。
- 本地 Agent 复用 canonical Agent Host/SDK，真实模型完成对话。
- Cloud 登录后注册稳定设备身份，Host bootstrap、heartbeat、LAN 和 Relay 生命周期正常。
- 桌面控制端 UI 能选择远程 Host、显示实际 transport、发送命令、显示 receipt/事件/最终回答和失败状态。

### Android

- 候选 APK 内嵌并暴露目标 RC 完整 commit，可在实体设备安装、冷启动、后台恢复。
- 本地/Cloud/Remote 三种 Agent location 都进入真实 adapter，不使用静态回答。
- 远程连接使用持久设备身份、LAN proof、E2EE handshake、加密 command/receipt/event 和 Relay fallback。
- 离线时只读；恢复后 cursor 连续，旧未知副作用不自动重放。

## 4. 关联材料

- [Change Spec](../system/change-spec-first-batch-agent-remote-release-gate.md)
- [逐项验收与当前进度](../superpowers/tests/2026-09-12-first-batch-agent-remote-release-gate.md)
- 自动化预检：`scripts/release/verify-first-batch-preflight.sh`（正式候选使用 `--rc`）
- Cloud RC C-01/C-02：`scripts/release/verify_first_batch_cloud.py`（只接受 HTTPS production + Redis + 真实 Provider）
- Cloud RC C-04：`scripts/release/verify_first_batch_relay.py`（两台临时 proof 设备、Host 离线失败、双 WSS、端侧 E2EE 往返；输出脱敏 JSON）
- 真实 Host 远程 Agent：`scripts/release/verify_first_batch_remote_agent.py`（临时控制端连接已在线桌面 Host，复用 canonical Ed25519/X25519/AES-GCM 契约，要求 durable receipt、唯一 `turn.succeeded`、challenge 回答，并在清理前确认 Cloud command/event 投影为空；CLI 随后撤销 Grant 并验证当前/新 Relay 连接均拒绝，再恢复 Grant、撤销临时控制设备并验证当前连接拒绝及新连接关闭。可选 `--approval-scenario deny|expired` 从环境变量读取危险工具 prompt，要求唯一 `approval.required/resolved`、匹配决定、唯一终态和对应 call 从未 `tool.started`；输出只包含 prompt/approval/call 哈希。撤销与单次审批结果都只是 E-02 子证据。）
- Windows Host 审批现场：`scripts/release/verify_first_batch_windows_host_approval.ps1`（要求 Authenticode-valid x64 安装版并绑定同 RC Cloud/Host 基线；先证明收件箱为空，再等待唯一远程审批。`deny` 模式从 UI Automation 点击本机拒绝，`expired` 模式不操作并观察 SDK 超时后条目消失；只输出 approval ID 哈希和签名/RC 元数据，子检查名刻意不使用 `E-02` 前缀。）
- E-02 合成：`scripts/release/verify_first_batch_e02.py` 只在两次独立远程运行的 deny/expired 与两份 Windows Host UI 证据逐项匹配，并且其中一轮同时证明 Grant/设备撤销、危险 call 均未 dispatch 时输出唯一 `e_02: PASS`。任一子证据不能单独绑定为整项 PASS。
- Production E-01 审计：`scripts/release/verify_first_batch_security_audit.py`（只读扫描同一 device-remote session 的 Cloud DB/WAL/SHM、完整时间窗日志和 `rediss://` relay keyspace；敏感 needle 仅从环境变量或真实 Host 验证器内存传入，证据只保留 SHA-256）
- Windows x64 / Android 现场入口：Release 构建把完整 git commit 注入两端只读可访问性语义。`scripts/release/verify_first_batch_clients.py` 的 desktop 模式通过 canonical API 生成不能绑定 X-01/X-02 的 `windows_local_agent_runtime` 子证据；`scripts/release/verify_first_batch_windows_local_agent.ps1` 必须核对同一签名 EXE 的哈希、版本和内嵌 commit，再从 UI Automation 选择同一模型、输入新的唯一 challenge，并从唯一成功 assistant 语义节点读取回答后同时输出 X-01/X-02。Android 所有现场模式都要求 `--expected-commit` 并从实体设备 UI hierarchy 核对 APK 内嵌值；runtime 模式还只有在 `apksigner` 验证 v2/v3、固定单一证书指纹，且从设备回拉的已安装 APK 与签名 RC 字节及 SHA-256 完全一致后才输出 A-01，未提供制品参数时只输出非门禁 smoke；A-02～A-06 模式必须通过 `--android-artifact-evidence` 读取同 RC 的绑定 A-01 证据并重新回拉当前安装 APK 核对 SHA-256，Host/Cloud/Remote Agent 模式只证明各自链路，不再顺带宣称 A-01；`android-recovery` 通过 USB 控制网络 radio，先完成 Relay 基线，再在第二条命令发送中断网并验证只读/单条保留，恢复后要求同一持久 session 的 cursor 单调前进且第三条新命令成功。所有 Android Agent 回答只接受 assistant 语义节点中的 challenge 和唯一 `turn.succeeded` 终态标记，任何 `turn.started`、失败、取消、中断或重复终态都不能通过；证据仅输出脱敏哈希。
- RC 制品清单：`scripts/release/generate_first_batch_rc_manifest.py`（锁定 Cloud image digest、Windows x64、Android APK、commit、版本和协议；正式批准只能来自 19/19 且逐项绑定版本/commit 的 JSON 证据，台账校验器还强制 Android A-01/APK、Windows X-01/EXE signer、C-01 HTTPS deployment 和 X-03 Host 的跨 gate 一致性）
- 现场证据绑定：`scripts/release/bind_first_batch_evidence.py`（把验证器脱敏 JSON 与 RC 版本、完整 commit 和一个或多个 P0 gate ID 绑定；台账只引用绑定后的文件）
- 正式发布门禁：`scripts/release/verify_first_batch_ledger.py`（稳定 tag 必须实际读取 19/19 PASS JSON；无 evidence root、跨制品/Cloud/Host 拼接或缺固定 verification schema 均拒绝；RC tag 始终为 prerelease）
- [多端与设备协同上位需求](2026-08-29-multiplatform-cloud-sync-and-device-control.md)
- [当前接口矩阵](2026-09-08-notemeld-new-product-interface-matrix-v1.md)

## 5. 当前已知阻塞

- 桌面远程客户端 UI 与生产设备 proof/token 交换已实现并通过契约测试，但尚无 Windows 双机纵向证据。
- 已有可直接穿过 production Cloud Relay 调用真实桌面 Host canonical Agent 的现场验证器；尚缺 production Cloud、已配置真实模型且在线的 Windows x64 Host 来实际执行。
- 当前本地桌面没有已配置模型，无法证明真实本机 Agent 对话。
- 本地 Cloud 测试实例缺少可用于烟测的账号凭据，真实 Provider 状态未证明。
- Android 实体设备已完成当前 debug APK 安装/冷启动，但该证据明确只算 smoke、不能形成 A-01。客户端现会展示所选 Host 哈希与连接成功后的实际 LAN/Relay transport，现场验证器会绑定既有 Cloud/真实 Host 证据并读取该 UI 值。尚无签名 RC、固定生产证书指纹、第二台 x64 Host 和双网络拓扑，无法执行 A-01 或目标范围的 LAN/Relay 双路径。
- Release workflow 现已配置 Windows Authenticode、Android keystore 签名和 GHCR Cloud image；正式 tag 仍需仓库配置对应签名 secrets 后实际执行并保留 `first-batch-rc.json`。
- Windows Host 身份已接入 Credential Manager；桌面根生命周期会在任意路由恢复加密保存的 Cloud 登录和 Host，不再要求用户重启后先打开 Cloud 页。新增本地脱敏 Host 状态投影及 `verify_first_batch_windows_host_restart.ps1`，会绑定同 RC 的 C-01/C-02/C-04/X-06 证据、签名 x64 EXE、Cloud 设备公钥与 heartbeat，重启安装版后要求 device ID/公钥指纹不变且 `last_seen_at` 前进。尚缺 Windows 签名 RC 现场执行，X-03 仍为 PARTIAL。
- Windows Host 根布局现提供全局待审批收件箱：从 durable Turn/Event 安全投影轮询远程或本地 Agent 的 `waiting_approval`，无需打开对应会话即可拒绝/批准；列表不返回工具参数或 action digest，控制端仍不能代批。E-02 仍需 Windows 签名 RC 上完成危险工具拒绝与不处理至 SDK 超时的现场证据。
- Host 可通过可选环境变量 `NOTEMELD_AGENT_APPROVAL_TIMEOUT_SECONDS=1..86400` 调整 canonical SDK 审批等待窗口；未设置或非法时保持 SDK 默认 300 秒。该变量只用于 RC 超时门禁提速，计时、`approval.resolved: expired` 和 `approval_expired` 终态仍完全由独立 SDK 产生。
- 仓库当前只负责构建并推送 GHCR Cloud 镜像，没有绑定生产集群、域名或自动部署 workflow；09-18 前必须明确部署平台/负责人，并用不可变 image digest 部署 HTTPS production RC。否则即使 Release 成功，也只得到镜像而不是可验收的 Cloud 服务。
- C-03 不能再用单元测试或普通健康重启替代：现场脚本必须在同一 production session 观察到 running + queued，直接执行 operator 的进程/部署重启 argv，验证中断项进入 `process_restarted/needs_attention` 且 queued 未增加 attempt；只有显式 abandon 后第二条真实 Provider 命令执行一次并产生唯一成功终态，才允许绑定 C-03。
- 稳定版不能在现场验收后重新构建“看起来相同”的包：X-01 必须记录实际安装 MSI/EXE 的 SHA-256，A-01 已记录实际 APK SHA-256，最终 manifest 会与待上传制品逐字节比对。候选 tag 使用 `vX.Y.Z-rc.N` 等 prerelease 名称，但 Windows/Android/RC manifest 内嵌目标稳定版本 `X.Y.Z`；19 项通过后由确定性打包器生成 live-evidence ZIP，独立 promotion workflow 在候选原 commit 上复验并复用原 APK、Windows 安装包和 Cloud metadata，创建 `vX.Y.Z`，不得调用 Tauri/Gradle/Docker 重建。该 workflow 仍需真实 GitHub 候选运行验证。

## 6. 首批上线目标

目标上线日：**2026-09-25（周五）**。该日期是严格 Go/No-Go 目标，不以跳过 P0 项换取按时上线；若 9 月 24 日仍有任一 P0 非 `PASS`，整批顺延到 **2026-10-09**，不做逐日漂移。

| 日期 | 必须产出 |
|---|---|
| 09-16 | 功能冻结并生成 RC1；Cloud、Windows x64、Android 锁定同一 commit/协议基线 |
| 09-18 | production Cloud RC、真实 Provider、HTTPS、Redis、测试账号就绪；完成 C-01/C-02 |
| 09-21 | 两台 Windows x64 完成签名安装、Host/Controller、本机 Agent 基线 |
| 09-22 | Android 签名 RC 在实体机完成安装、本机/Cloud Agent 基线 |
| 09-23 | x64→x64 与 Android→x64 的 LAN、Relay、断线恢复、撤销和审批纵向全部完成 |
| 09-24 | 安全日志/数据库明文审计、制品哈希、镜像 digest 和回滚演练；Go/No-Go |
| 09-25 | 仅在全部 19 个 P0 为 `PASS` 时首批上线 |
