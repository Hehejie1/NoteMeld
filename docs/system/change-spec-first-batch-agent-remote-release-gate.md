# Change Spec: 首批 Cloud / x64 / Android Agent 与远程连接发布门禁

状态：Accepted scope / verification in progress

日期：2026-09-12

## 1. 当前现状

NoteMeld 已分别实现 Cloud-native Agent、桌面 Agent Host、设备身份、LAN-first、Cloud Relay、E2EE 握手、移动端 Agent 和 Android 远程控制代码，并已有大量契约、模拟器、构建和局部真机证据。现有产品计划同时覆盖 macOS、Windows、Android、iOS、Harmony、Cloud 和全部应用，最终设备脚本也强制三种移动平台同时在场，无法准确表达首批上线范围。

当前证据仍不能证明以下用户纵向结果：

- 生产配置的 Cloud 使用真实 Provider 完成 Agent 对话。
- x64 桌面 UI 能作为控制端选择远程机器并获得 Agent 最终回答。
- Android 经 LAN 和 Relay 两条路径连接 x64 Host 并获得 Agent 最终回答。
- Relay 断线、Host 离线和恢复后不会丢失终态、重复副作用或泄露明文。

## 2. 本次目标

首批发布只验收三个交付面：

1. Cloud：真实 Agent 正常运行；Relay 只转发端到端加密消息。
2. x64 桌面客户端：本机 Agent 正常对话；能够作为控制端连接另一台授权 x64 Host 并完成远程 Agent 对话；也能作为 Host 接受授权连接。
3. Android：本机/Cloud Agent 正常对话；能够连接授权 x64 Host 并完成远程 Agent 对话。

每个结果都必须由可重复命令、运行日志或 UI 录像/截图证明，测试证据统一记录在 `docs/superpowers/tests/2026-09-12-first-batch-agent-remote-release-gate.md`。

## 3. 明确不做

- iOS 和 Harmony 不阻塞首批发布。
- 插件市场、Application 用户包安装、多人组织管理和完整知识产品矩阵不进入首批门禁。
- 不以 deterministic smoke runner 证明“真实 Cloud Agent 可用”。
- 不以单元测试、模拟器启动或同进程 mock 证明“真实远程连接可用”。
- 不把 Cloud Relay 改造成消息明文存储或第二套 Agent runtime。

## 4. 目标验收拓扑

至少需要以下四个独立运行角色：

- 一套 HTTPS Cloud RC：真实 OpenAI-compatible Provider、Redis Relay、设备证明和生产 fail-closed 配置。
- x64-A：桌面控制端，安装候选版本。
- x64-B：远程 Host，安装相同候选版本并绑定同一 Cloud 账号。
- 一台 Android 实体设备：安装候选 APK，绑定同一 Cloud 账号。

LAN 场景要求控制端与 x64-B 同一局域网；Relay 场景要求关闭或移除 LAN candidate，并让双方通过不同外网连接 Cloud。单机 loopback、`adb reverse` 和模拟器不算远程 Relay 验收。

## 5. 影响范围

- Cloud：`cloud/` Agent runner、session/command/event、device/grant、Relay 和 production config。
- 桌面 Host：`desktop/backend/app/cloud_sync/`、Agent Host、Cloud bootstrap 和设备身份。
- 桌面控制端：`desktop/frontend/src/services/lanRemoteClient.ts`、Cloud/会话 UI。Cloud 会话页现已提供远程 Host 选择、显式授权、LAN-first/Relay 连接、消息发送和事件展示入口，仍需在双机 RC 上完成纵向验收。
- Android：`CloudApi.kt`、`AndroidRemoteRelay.kt`、`MobileApi.kt`、`MobileSurface.kt`。
- 发布与验证：Windows x64 安装包、Android APK、Cloud RC、自动化和实体设备纵向记录。

不改变 Agent SDK、Cloud、桌面和移动端之间的 authority：Agent 行为仍由 canonical Agent runtime 执行；Cloud Relay 不解密 payload；Host durable enqueue 后才能返回 `received`。

## 6. 最小可行改动

1. 为桌面会话 UI 接入已有 `connectLanRemoteClient()`，提供远程 Host 选择、传输状态、发送、事件展示和安全错误状态。
2. 增加首批专用自动化预检 `scripts/release/verify-first-batch-preflight.sh`，统一验证产品文档、桌面后端、桌面前端、Android 构建和 Agent SDK；生产 Cloud、真实 Provider、Windows x64 制品和实体拓扑继续由现场台账验收，不再要求 iOS/Harmony。
3. 增加实体拓扑运行手册，分别执行 x64-A → x64-B 和 Android → x64-B 的 LAN、Relay、断线恢复场景。Windows 控制端使用 `verify_first_batch_windows_remote.ps1` 校验精确运行的 Authenticode x64 EXE 及内嵌 commit，再从安装版 WebView2 可访问性树选择证据绑定的 Host，并读取实际 transport、assistant 输出和唯一 terminal event；Android 同样从实体 APK UI 语义核对内嵌 commit。不接受截图、外部 JSON 标注或配置推断。
4. 将每次 RC 的版本、commit、Cloud deployment、设备、命令、终态、transport 和失败证据写入同一验收表。
5. 候选 Tag 发布流水线只接受 `vX.Y.Z-rc/alpha/beta`，但制品内嵌目标稳定版本 `X.Y.Z`；它必须同时产出 Authenticode 校验通过的 Windows x64 安装包、`apksigner` 校验通过的 Android APK、带 digest 且构建时注入完整 commit 的 GHCR Cloud 镜像，以及锁定三者 commit/版本/协议和 SHA-256 的 `first-batch-rc.json`，缺任一签名 secret 或制品时 fail-closed。production Cloud 必须按 metadata digest 拉取镜像，将实际 commit/digest 注入运行环境并由 `/ready` 暴露；C-01 与最终 manifest 都要交叉核对，不能只凭域名宣称部署了候选镜像。19 项现场门禁通过后，`package_first_batch_live_evidence.py` 必须实际复验台账并确定性打包其 19 个引用；独立 promotion workflow 只在候选原 commit 上安全解压、复验版本/commit/台账/制品哈希并创建稳定 tag，禁止重新执行 Tauri、Gradle 或 Docker 构建。
6. `-rc`/`-alpha`/`-beta` tag 只能生成 prerelease，清单保持 `release_approved=false`；稳定 tag 在创建 Release 前必须由 `verify_first_batch_ledger.py` 证明 19 个 P0 均为 `PASS` 且实际读取每行 JSON，未提供 evidence root 时不得批准。每份证据必须带固定 `notemeld.first-batch-live-evidence.v1` schema、有效且可从非绑定字段重算的 source SHA-256，并由 `bound_gate_ids` 显式包含当前台账项；绑定后改写 URL、Host、制品哈希或检查结果，手写相似 JSON，或拿只绑定其他 gate 的文件都不能参与批准。最终门禁除统一版本/commit 外，还必须确认 A-02～A-06 记录的 A-01 source hash 等于台账 A-01，并且各次回拉 APK 的 SHA-256 等于 A-01 的签名制品；X-02～X-05 的安装 EXE SHA-256 与 Authenticode signer 必须等于 X-01，X-01 还必须记录实际用于安装且 signer 相同的 MSI/EXE SHA-256。最终 manifest 必须把 A-01 APK 与 X-01 installer 哈希分别和本次待上传制品逐项比较，不能验收一个包再发布另一个包；所有 Cloud/远程相关项必须指向 C-01 的同一 HTTPS deployment，C-05、Windows/Android 远程、E-01/E-02 还必须指向 X-03 的同一 Host。验证结果带固定 schema 和完整 19 gate ID，manifest 不接受手工构造的旧形状批准对象。这样不能把同 RC 的不同制品、Cloud 环境或 Host 证据拼接起来。
7. Release workflow 把完整 git commit 注入 Windows 前端和 Android `BuildConfig` 的只读 `notemeld-build-commit:*` 语义，现场脚本必须从正在运行的安装版直接核对。`verify_first_batch_clients.py desktop` 只在安装后的 Windows x64 上，以显式真实模型通过 canonical Agent v1 完成唯一 challenge，并只输出不能绑定 X-01/X-02 的 `windows_local_agent_runtime` 子证据。`verify_first_batch_windows_local_agent.ps1` 再核对该子证据对应的同一签名 EXE，从安装版 UI Automation 核对 commit、选择模型、输入第二个 challenge，并要求唯一成功 assistant 语义节点和终态标记后同时输出 X-01/X-02。Android 所有现场模式要求显式 RC commit 并从实体包 UI 核对；`android-runtime` 未提供制品参数时只输出非门禁 smoke，只有 adb 在线实体设备上的单 APK、显式 RC 版本/commit、`apksigner` v2/v3、固定单一 signer SHA-256，以及设备回拉 APK 与候选制品逐字节一致全部成立时才输出 A-01。`android-agent`、`android-cloud-agent`、`android-remote-agent` 和 `android-recovery` 必须读取已绑定同一版本/commit 的 A-01 证据，并在各次运行时重新回拉当前安装 APK、核对其 SHA-256 仍与签名 RC 完全一致，防止换装同版本 debug 包；它们分别只输出 A-02、A-03、A-04/A-05、A-06，不能替代或顺带生成 A-01。对话模式继续绑定相应 Cloud/Host 证据、读取应用实际 target/transport，只从 assistant 语义节点判定回答，并且只接受恰好一个 `turn.succeeded`，拒绝 `turn.started`、失败或重复终态。所有模式只输出脱敏证据，且不替代双机 LAN/Relay 纵向。
8. `verify_first_batch_relay.py` 在离线失败和首次双向交换后关闭两个 peer，重连时必须取得精确连续的 Cloud 持久 cursor 并完成第二次双向交换，拒绝以重置 sequence 冒充恢复。`verify_first_batch_remote_agent.py` 只创建短期控制端身份并连接账号内已在线的真实桌面 Host；它复用产品 canonical handshake/frame/cipher 契约，等待 Host durable `queued` receipt、加密 Agent events、唯一成功终态和 challenge 回答，并在清理会话前确认 Cloud `commands/events` 投影均为空，同时记录本轮开始时 Cloud 所见 Host heartbeat 时间。`verify_first_batch_c03.py` 必须针对同一 production session 捕获一条 running 和一条 queued 后执行 operator 提供的无 shell 重启 argv；重启后 running 只能以单个 `process_restarted/needs_attention` 收口，queued 在人工处理前保持零 attempt，显式 abandon 后才允许 queued 以预期真实模型执行一次并产生唯一成功终态。该工作流证明真实 Host 纵向、C-03 进程故障和 E-01 的 Cloud 业务表子项，但不能替代 Windows/Android UI、真实网络断线恢复或 production 日志/Redis 审计。
9. `verify_first_batch_security_audit.py` 对 release operator 提供的只读 Cloud `cloud.db`（自动包含同目录 WAL/SHM）、完整验收时间窗的已解压日志和 production `rediss://` keyspace 做有界扫描。必须提供 challenge、账户/设备 Token、握手 session key 和 Provider key 五类不同 needle，且值只从环境变量或同进程真实 Host 验证器内存读取；输出仅含 needle SHA-256、扫描字节数/bundle hash 和聚合计数。审计 session 必须仍存在、类型为 `device_remote`、有双向 cursor 且 command/event 行为 0；压缩日志、符号链接、未知 Redis relay key 或任何命中均 fail-closed，且不回显原文。
10. Android 必须区分本机 Host 可达性与设备网络可用性：本机 8483 离线不应禁用 Cloud/远程，但设备无可用网络时 Cloud/远程必须只读。远程 session 按 Host 持久复用，Relay `next_sequence` 显示为可访问性证据；`android-recovery` 只允许 USB adb 实体机，保存并恢复原始 Wi-Fi/移动数据开关，先完成基线命令，再在第二条命令发送中断网，要求只读且 UI 仅保留一条该命令；恢复后 cursor 必须严格增加且第三个唯一 challenge 成功，才输出 A-06。
11. Windows 桌面 Host bootstrap 必须挂在应用根生命周期并从加密 IndexedDB Cloud token + Credential Manager Host identity 自动恢复，不能依赖用户进入 Cloud 路由。`verify_first_batch_windows_host_restart.ps1` 必须绑定同 RC 的 Cloud/真实 Host 证据和 Authenticode x64 安装版，重启前后从 UI Automation 脱敏标记读取相同 device ID/公钥指纹，并要求 production Cloud 在线设备的公钥匹配且 `last_seen_at` 前进，才输出 X-03；输出还绑定重启前 remote Agent 证据文件哈希。C-05 只有在 `verify_first_batch_c05.py` 再合成同 RC/Cloud/Host 的 Relay recovery、Windows 重启和时间上晚于重启的第二次真实 remote Agent 证据后才能 PASS。
12. Host 远程纵向在成功 Agent turn 后必须继续做撤销负向验证：撤销标准 Grant 后，已建立和新建 Relay 连接发送的 envelope 都应在 Cloud 逐帧校验处拒绝且不送达 Host；恢复 Grant 后撤销临时控制设备，已建立连接应拒绝，新连接应在认证阶段关闭。该结果只证明 E-02 的撤销子项；危险工具在 Host 本机拒绝和超时仍需独立现场证据，三项未齐全时不得输出 E-02 PASS。
13. Windows Host 必须在应用根布局提供全局待审批收件箱，直接从 durable `waiting_approval` Turn 与最新 `approval.required` 事件读取，不依赖当前打开的会话或远程页面。列表仅允许安全字段，批准/拒绝必须调用 canonical SDK runtime 的既有 control ABI，且安装版 list/resolve 都必须验证 Tauri 启动时随机生成的 `X-NoteMeld-Session`；处理或超时后不得残留。远程 Windows/Android 控制端继续只读显示审批状态，不得获得 resolve authority。
14. E-02 现场证据必须由两次独立远程危险工具运行产生：一次由 Windows Host UI 拒绝，一次由 SDK 自行超时。远程侧与 Host UI 侧以 approval ID SHA-256 绑定，必须证明对应危险 call 没有 `tool.started`；超时必须产生 `approval.resolved:expired` 和 `turn.failed/approval_expired`。最终合成器还要验证 Grant/设备撤销的当前/新连接均 fail-closed，并绑定同一 RC、Cloud deployment 和 Host。子证据不得使用 E-02 前缀，只有完整合成结果可以输出 `e_02:PASS`。

## 7. 验收与发布规则

- 所有 P0 项必须为 `PASS`；`UNVERIFIED`、`PARTIAL`、`SKIPPED` 均阻止首批发布。
- 真实 Agent 回答必须来自配置的 Provider，并在事件中形成唯一 `turn.completed`/`turn.succeeded` 终态。
- 远程命令必须同时证明 Cloud 只看到密文 envelope、Host durable receipt、Agent 最终事件回传和 UI 可见回答。
- LAN 和 Relay 必须分别验证；Relay 不能以 LAN 成功代替。
- Host 离线必须快速、明确失败；Host 恢复后新命令成功，旧未知副作用不得自动重放。
- 最终发布候选必须来自干净 commit，Windows x64 与 Android 制品记录 SHA-256，Cloud 记录镜像 digest。

## 8. 风险与回滚

- 桌面远程控制入口已接入 Cloud 会话页，且控制端与 Host 使用独立设备 ID/密钥；真实 Windows 双机 LAN/Relay 仍未验收。
- 本地桌面实例当前没有已配置模型，不能证明真实 Agent 对话。
- 当前没有连接 Android 实体设备，不能执行本轮真机纵向。
- Cloud 本地实例虽 ready，但缺少可用于验收的测试账号凭据，且是否使用真实 Provider 未获证明。

发布后若本地 Agent 或远程链路出现终态、加密、授权或重复副作用问题，停止分发对应 RC，回滚到上一签名桌面/Android 制品和上一 Cloud 镜像；不执行破坏性数据库回滚。

## 9. 目标日期

首批 Go/No-Go 为 2026-09-24，上线目标为 2026-09-25。任一 P0 未通过则整批顺延至 2026-10-09；Cloud、Windows x64 和 Android 不拆批上线，避免协议和权限基线不一致。
