# 首批 Cloud / x64 / Android Agent 与远程连接验收台账

状态：In progress — 2026-09-13 baseline audit

范围规范：[`../../system/change-spec-first-batch-agent-remote-release-gate.md`](../../system/change-spec-first-batch-agent-remote-release-gate.md)

## 1. 状态定义

- `PASS`：当前 RC 在目标环境完成了与目标同范围的验证，并保留证据。
- `PARTIAL`：实现和局部证据存在，但未覆盖完整用户纵向。
- `FAIL`：已执行目标范围验证并失败。
- `UNVERIFIED`：缺少目标环境、凭据、设备或运行证据。
- `BLOCKED`：存在明确实现缺口，当前用户流程无法执行。

只有全部 P0 项为 `PASS` 才能发布首批版本。

随时执行 `python3 scripts/release/verify_first_batch_ledger.py --report docs/superpowers/tests/2026-09-12-first-batch-agent-remote-release-gate.md`，可在不放宽正式发布门禁的前提下重新计算当前状态和待完成 ID。

现场验证器的原始脱敏 JSON 必须先用 `scripts/release/bind_first_batch_evidence.py --input <raw.json> --output <evidence.json> --rc-version <version> --rc-commit <40-char-sha> --gate <ID> [--gate <ID>...]` 绑定到唯一 RC。某项改为 `PASS` 时，“当前证据”单元格只能填写相对本台账目录的 JSON 路径；正式 tag 会读取每个文件、核对对应 `release_checks`、版本、commit 和 SHA-256。单独设置批准布尔值或只写文字说明不能生成获批 manifest。

## 2. 2026-09-13 基线结论

| ID | P0 可验收结果 | 当前状态 | 当前证据 / 缺口 |
|---|---|---|---|
| C-01 | Cloud production 配置 fail-closed，`/ready` 的 DB、workspace、Redis Relay 均为 ok | PARTIAL | production 现在强制要求完整 build commit 与不可变 image digest，镜像构建注入 commit，部署必须按 digest 拉取并把实际 digest 注入运行环境；`/ready` 暴露两个非敏感身份，现场验证器要求与候选元数据完全一致，最终 manifest 再把 C-01 digest 与待发布 Cloud metadata 交叉比较。本地契约通过，但仓库尚未绑定生产部署目标，生产 HTTPS/Redis RC 未执行 |
| C-02 | Cloud 真实 Provider 完成一轮 Agent 对话，并产生唯一 terminal event | UNVERIFIED | OpenAI-compatible runner 现只接受 Provider 实际返回且与配置一致的 model；普通回答必须 `finish_reason=stop`，模型漂移、截断/过滤及畸形 choices fail-closed。现场验证器要求唯一 challenge/terminal，但仍缺 production Provider 凭据与真实执行证据 |
| C-03 | Cloud 重启后 queued 恢复，running 进入 `needs_attention`，不自动重放未知副作用 | PARTIAL | 后端契约已覆盖 queued 启动恢复、session 级单 active Turn、active lease 保留、stale lease 周期 fail-closed 仲裁及 abandon 后续跑；新增生产 C-03 现场验证器，会并发提交两条真实 Provider 命令、执行 operator 提供的无 shell 重启 argv，要求 running 仅一次 `process_restarted/needs_attention`、queued 保持零 attempt，显式 abandon 后 queued 才完成且只有一个成功终态。仍缺 production RC 进程级执行证据 |
| C-04 | Redis Relay 在两个独立连接/worker 间转发 E2EE envelope，不保存消息明文 | PARTIAL | 自动化和既有 Redis CI 证据通过；已有临时双端 Relay 验证器和真实桌面 Host Agent 纵向验证器，均尚未在 production Cloud 执行 |
| C-05 | Host 离线返回明确失败；恢复后新命令成功且 cursor 连续 | UNVERIFIED | Relay 子门禁验证 `host_offline`、双方持久 cursor 与重连后第二次交换；新增 C-05 合成器还要求同 RC/Cloud/Windows Host 的真实进程重启、身份与 heartbeat 前进，以及时间上晚于重启的第二次真实 remote Agent 成功和 Cloud 零 command/event 投影。仍缺现场三段证据，普通 socket 重连不能单独通过 |
| X-01 | Windows x64 安装候选包并启动 sidecar/UI | PARTIAL | Release workflow 已要求 Authenticode；Python desktop 模式只形成不能绑定 X-01/X-02 的 runtime 子证据。只有 PowerShell UIA 门禁核对精确运行 EXE 的 PE x64、ProductVersion、Authenticode、内嵌 commit 与 runtime 文件哈希，并验证保留的正式 MSI/EXE 安装包使用同一 signer 后，才会记录 installer SHA-256 并和 X-02 一起输出 X-01。当前 RC 尚未在 Windows 实机安装执行 |
| X-02 | x64 本机使用真实模型完成 Agent 对话 | UNVERIFIED | Python desktop 模式只形成 `windows_local_agent_runtime` 子证据，不能绑定 X-01/X-02；PowerShell UIA 门禁会绑定同一签名 EXE/RC/模型，从真实安装版工作区选择模型、输入第二个唯一 challenge，并只接受包含回答的唯一 `turn.succeeded` assistant 语义节点，然后同时输出 X-01/X-02。当前机器无 Windows RC 与已配置真实模型，无法形成现场证据 |
| X-03 | x64 设备身份、Cloud 登录、heartbeat、grant 和 Host Relay 生命周期正常 | PARTIAL | Windows Credential Manager Host identity、device proof/token、后台 heartbeat 和同步 bootstrap Relay discovery 已实现；Host 现由应用根生命周期从加密 Cloud 登录自动恢复，不依赖访问 Cloud 页。新增签名 x64 安装版重启现场门禁，要求同一 device ID/公钥指纹并验证 Cloud `last_seen_at` 前进，且绑定 C-01/C-02/C-04/X-06 同 RC 证据；尚未在 Windows/production Cloud 执行 |
| X-04 | x64-A 从 UI 选择 x64-B，并通过 LAN 完成远程 Agent 对话 | PARTIAL | Cloud 会话页已接入 Host 选择、授权、LAN-first 连接、发送和终态事件展示；新增 Windows UI Automation 门禁，可从安装版可访问性树选择绑定 Host、读取实际 `lan`、发送唯一 challenge，并只接受 assistant 输出和唯一成功终态。缺真实 Windows 双机 LAN 纵向 |
| X-05 | x64-A 禁用 LAN 后经 Cloud Relay 完成同一远程 Agent 对话 | PARTIAL | UI 已显示实际 transport，并用控制端 device token/ID 建立 Relay；同一 Windows UI Automation 门禁可强制读取实际 `relay`，且输入 Cloud/Host 证据必须绑定相同 RC 版本、commit 和部署。缺真实 Windows 双机 Relay 纵向 |
| X-06 | x64-B 收到远程命令后 durable enqueue，回传 receipt、Agent event 和最终回答 | PARTIAL | Host adapter/consumer 已实现；`verify_first_batch_remote_agent.py` 可对已在线真实 Host 执行签名握手、E2EE command、durable receipt、Agent event/challenge 纵向，缺 Windows x64 RC 现场执行证据 |
| A-01 | Android 候选 APK 在实体设备安装、启动且无 fatal crash | PARTIAL | 当前 debug APK 已在 24115RA8EC / Android 14 实体机完成安装与 cold launch，但只算非门禁 smoke。A-01 验证器现要求 APK 内嵌 commit 与目标 RC 一致、`apksigner` v2/v3、固定单一 signer SHA-256，并从设备回拉已安装 APK，与签名 RC 字节和 SHA-256 完全一致；正式签名 RC 尚未执行 |
| A-02 | Android 本机/宿主 Agent 使用真实模型完成对话 | PARTIAL | 修复本地 adapter 忽略标准 `payload.delta`、5 秒投影刷新重置活跃会话、IO 线程直接更新 Compose 状态和流式 delta 拆成多个气泡的问题；会话页恢复本机/Cloud/远程三态入口，发送按钮改为小屏独立整行。现场模式必须绑定 A-01 并重新回拉当前 APK 核对签名 RC 哈希，再强制选择本机、驱动真实 Host Agent、只认 assistant challenge 与唯一 `turn.succeeded`。当前无在线实体设备、宿主也无已配置真实模型，尚未形成现场 PASS |
| A-03 | Android Cloud-native Agent 使用真实 Provider 完成对话 | PARTIAL | 修复本机 8483 离线时错误禁用 Cloud/远程输入的问题，并恢复可逆设置导航、明确 Cloud 模式与目标 URL；新增 `android-cloud-agent` 实体包 UI 门禁，强制绑定同 RC 的 A-01、同 URL/模型的 C-01/C-02 PASS 证据和实时 production `/ready`，重新核对当前安装 APK 后只接受 assistant challenge 与唯一 `turn.succeeded`。真实 Cloud Provider 与实体设备尚未执行，不能形成现场 PASS |
| A-04 | Android 选择 x64-B，经 LAN 完成远程 Agent 对话 | PARTIAL | Android 现会筛选桌面 Host、创建/复用标准 Grant、完成 LAN proof/E2EE，并在 UI 显示所选 Host 哈希与 transport 实际值；`android-remote-agent` 会绑定 A-01、C-01/C-02 与真实 Host PASS 证据，重新核对当前安装 APK，只接受 UI 回报 `lan`、assistant 最终回答与唯一 `turn.succeeded`，失败或重复终态拒绝。缺实体设备 + x64 Host LAN 纵向 |
| A-05 | Android 切换外网后经 Relay 完成远程 Agent 对话 | PARTIAL | Android 在 Relay 前完成 Cloud device proof、换取非覆盖账户登录的有限 scope device token，并解密 receipt/event；同一实体包门禁绑定 A-01 并重新核对当前 APK，只接受 UI 回报 `relay`、assistant 最终回答与唯一 `turn.succeeded`，不会把自动回退、配置预期、`turn.started` 或 idle 当成成功。缺真实蜂窝网络 Relay 纵向和最终回答证据 |
| A-06 | Android 离线时只读；恢复后 cursor 连续、可继续新对话 | PARTIAL | 已拆分“本机 Host 离线”与“设备网络离线”：本机 8483 不可达仍允许 Cloud/远程，真正无网络时输入、附件、模型与发送进入可访问性标记的只读态；远程 session 按 Host 持久复用并显示 Cloud Relay 起始 cursor。`android-recovery` 先绑定 A-01 并重新核对当前 APK，再保存/恢复实体机 radio，完成首轮 Relay，在第二条命令发送中断网并验证只读、单条保留且无回答，恢复后要求旧命令仍未回放、cursor 严格增加和第三条新 challenge 成功；本轮另在实体机 debug APK 沙箱注入 pending Turn、强杀并重新启动，确认 `turn.interrupted:needs_attention` 与恢复文案持久化后清理恢复。签名 RC、网络切换和 Relay cursor 现场仍未执行 |
| E-01 | Relay/Cloud 日志和数据库不包含测试消息明文、Token 或会话密钥 | UNVERIFIED | 自动化已证明 device-remote 只持久化 relay cursor、Cloud command/event 投影为空且应用日志/SQLite dump 不含测试 token/opaque payload；真实 Host 验证器现可在同一进程把 challenge、账户/设备 Token 和握手 session key 交给只读 production DB/WAL/SHM、日志、Redis 审计器。目标 RC 尚未实际执行该组合门禁 |
| E-02 | 远程危险工具要求审批；拒绝、超时和撤销设备均 fail-closed | PARTIAL | 标准远程 Grant 不含 elevated approval scope；Windows/Android 控制端会显式显示 `approval.required` 与“只能在 Host 本机审批”，且没有远程批准入口。Windows Host 根布局现持续轮询 durable `waiting_approval` 安全投影，远程 Turn 无需位于当前页面即可在本机拒绝/批准，列表不泄露工具参数/action digest。真实 Host 验证器现可分别要求 `deny`/`expired`、危险 call 未 `tool.started`、超时以 `approval_expired` 失败，并验证 Grant/设备当前与新连接撤销；Windows UIA 验证器以审批 ID 哈希证明本机拒绝或观察超时，独立合成器只有四份证据同 RC/Cloud/Host 匹配才输出 E-02。自动化契约已通过，但缺 Windows 签名 RC 现场运行，故仍为 PARTIAL |

## 3. 已执行的自动化基线

统一入口：`scripts/release/verify-first-batch-preflight.sh`。正式候选执行时使用 `--rc`，脏工作树会 fail-closed。该入口只证明自动化预检，不替代第 4 节的生产 Cloud、Windows 双机和 Android 实体拓扑。

| 检查 | 结果 |
|---|---|
| `scripts/release/verify-first-batch-preflight.sh` | PASS：当前完整入口返回 `automated checks passed`；覆盖文档、1114 项后端、TypeScript、147 项 Node、前端生产构建、Android 构建和 Agent SDK workspace；RC 模式已验证会拒绝脏工作树。现场 P0 仍需真实环境证据 |
| `PYTHONPATH=.:desktop/backend .venv/bin/python -m pytest desktop/backend/tests -q` | PASS：`1114 passed, 1 skipped, 13 subtests passed`；完整复跑包含 Cloud Provider 实际 model/finish reason、production factory 禁止 production deterministic/provider-only runner、production readiness 必须报告 canonical SDK、production 拒绝 localhost/plaintext Agent Provider、production build commit/image digest fail-closed 与 C-01→manifest 镜像绑定、canonical Cloud SDK adapter 对畸形 finish/tool-call/JSON 响应的 fail-closed 校验、所有 Cloud/远程 gate 对同一 runtime commit + image digest 的交叉绑定、session 单 active Turn、stale command lease 周期仲裁与 abandon 后续跑、C-03 生产进程重启现场验证器、C-05 Windows Host 重启后真实 Agent 证据合成、Windows 安装 EXE 的 PE x64/版本/Authenticode/运行态 runtime 子证据、Windows 本机/远程/Host UI 对内嵌 commit 的直接核对、Windows 本机 Agent UIA/X-02 分层门禁、Windows 跨 gate EXE/signer/installer 绑定、Host 脱敏状态与安装版重启门禁、Host 全局审批安全投影、E-02 拒绝/超时/UI/完整证据合成门禁、Android APK 内嵌 commit、签名/设备安装字节绑定、A-01 后换包拒绝、Android 跨 gate 制品与 Cloud 镜像证据交叉绑定、唯一成功终态、发送中断网/恢复及客户端现场门禁、Relay 断开重连/cursor 连续性、Grant/设备逐帧撤销、真实 Host remote Agent、production E-01 审计器、确定性证据包与无重建 promotion，以及固定 schema、可重算 source hash、显式 gate binding 和验收包/发布包哈希一致性的 19 项现场证据绑定 |
| `cd desktop/frontend && corepack pnpm test:contracts` | PASS |
| `cd desktop/frontend && node --test tests/*.test.mjs` | PASS：`147 passed` |
| `cd desktop/frontend && corepack pnpm build` | PASS：`13183 modules transformed`；保留既有大 chunk 与 `lottie-web eval` warning |
| `python3 scripts/cloud/validate_product_docs.py` | PASS：`40 features, 40 bindings` |
| Android实体机 debug smoke（`24115RA8EC`，Android 14） | PARTIAL：2026-09-14 重新构建并安装 `app-debug.apk`（SHA-256 `50fd4cc893f79dc2d4a10033a9975cb64f46a397d9fd4160ac6802d8a624c41e`），无 fatal exception、无 `adb reverse`，进程和 `MainActivity` cold launch 正常；本次包含 embedded Provider malformed-response fail-closed adapter、将 `MobileLocalStore` 的有界历史恢复给 canonical FFI runtime、pending Turn 的 interrupted/needs-attention recovery projection、关键 pending/recovery 状态的同步 `commit()` 落盘，以及有界 sequence/type/timestamp 本地 event projection、stale-turn callback 拒绝和 pending input 补回。实体机沙箱 smoke 实际确认 `NM-RECOVERY-INPUT` 与 `turn.interrupted:needs_attention` 均持久化，随后已恢复原始偏好。UI hierarchy 暴露 `notemeld-build-commit:development`、设置页 Cloud/本机 Provider 控件，首页快捷入口已验证为 vector drawable 而非文字占位图标。debug 包、`development` commit 且未绑定签名 RC，不能形成 A-01～A-06 PASS |
| 本地桌面 `GET /api/sys_health` | PASS |
| 本地 Cloud `GET /ready` | PASS：database/workspace ok |
| 本地 Cloud `smoke_mobile_cloud.py` | UNVERIFIED：本地实例没有可用于验收的 admin password 配置 |
| Cloud RC C-01/C-02 验证器契约 | PASS：覆盖 production readiness、HTTPS/Redis/E2EE/device-proof、候选 build commit + immutable image digest、预期模型、唯一终态、cursor、API 编排及敏感凭据不出现在证据中；真实 RC 尚未执行 |
| Cloud Provider adapter 终态契约 | PASS：7 项覆盖 Provider 实际 model、瞬态重试、tool round、脱敏失败、模型精确匹配及截断终态拒绝；真实 Provider 尚未执行 |
| Cloud C-03 进程重启现场验证器契约 | PASS：6 项覆盖 production HTTPS/真实 Provider/无 shell 重启命令输入、running→`needs_attention`、queued 不自动重放、显式 abandon 后单次执行、唯一成功终态、重复终态拒绝、清理和证据脱敏；真实 RC 尚未执行 |
| Cloud RC C-04/C-05 Relay 验证器契约 | PASS：4 项覆盖 HTTPS→WSS 路径、两台临时设备 Ed25519 proof/有限 device token、Host 离线显式失败、X25519+HKDF/AES-256-GCM 双向密文转发、双方断开重连、持久 cursor 单调连续、第二次双向交换、清理与证据脱敏；真实 RC 尚未执行 |
| C-05 Host 重启证据合成器契约 | PASS：7 项覆盖同 RC/Cloud URL/runtime commit/image digest、Relay 离线与 cursor 子证据、Windows x64 身份/heartbeat 重启、重启前后 remote Agent 证据文件分离、相同 Host 哈希、严格时间顺序、真实 Relay Agent 和 Cloud 零 command/event 投影；真实现场链尚未执行 |
| 真实桌面 Host remote Agent 验证器契约 | PASS：10 项覆盖临时控制端 proof/token、在线桌面 Host 筛选、canonical 签名握手/E2EE frame、durable `queued` receipt、Agent challenge/唯一成功终态、重复终态拒绝、deny/expired 审批负向、Grant 撤销后当前/新连接拒绝、设备撤销后当前连接拒绝/新连接关闭、Cloud command/event 空投影、同进程 E-01 审计传参、配置完整性、资源清理与证据脱敏；撤销或单次审批仅作为 E-02 子证据，不单独宣称完整 PASS。真实 production Cloud + Windows x64 Host 尚未执行 |
| E-02 拒绝/超时/合成器契约 | PASS：真实 Host 验证器的 deny/expired 两种事件判定、无 `tool.started`、超时 `approval_expired`；Windows x64 UIA 脚本的签名/PE/空收件箱/拒绝按钮/条目消失语义；最终合成器对四份独立证据、approval 哈希、RC/Cloud URL/runtime commit/image digest、Host 和撤销完整性 fail-closed。子证据刻意不能被绑定器当作完整 E-02 |
| Device-remote Cloud 保密存储契约 | PASS：真实 Relay command/receipt 往返后仅有两条 sequence cursor，`commands/events` 均为 0；SQLite dump 与应用日志不含测试 token、opaque payload 或端侧明文 sentinel。production 平台日志/Redis 仍须现场扫描 |
| Production E-01 现场审计器契约 | PASS：7 项覆盖 DB/WAL/SHM、已解压日志跨块有界扫描、压缩包/符号链接拒绝、同一 device-remote session/双向 cursor/零 command-event 语义、五类完整且不同的环境变量 needle、远程 Redis TLS、仅短 TTL presence key、未知持久 key 拒绝和证据脱敏；目标 RC 尚未执行 |
| Windows x64 / Android 客户端现场验证器 | PASS（Python 客户端契约 27 项 + Windows 本机 UIA 契约 3 项 + Windows 远程 UI Automation/Host 重启契约 5 项）：Windows desktop 模式验证运行 EXE 的 PE x86_64、ProductVersion、Authenticode 与文件哈希，再经 loopback canonical API 形成不能单独绑定 X-02 的 runtime 子证据；Windows 本机、远程、Host 重启与审批 UIA 都直接核对运行安装版内嵌的完整 commit，本机模式还必须实际选择模型、输入新的 challenge，并读取唯一成功 assistant 终态后才输出 X-02。Android runtime 只有在签名方案、固定证书指纹、回拉安装包与 RC 字节完全一致时才输出 A-01；A-02～A-06 每次都必须绑定同 RC 的 A-01 并重新回拉当前安装 APK 核对 SHA-256，防止换装同版本 debug 包；本机/Cloud/远程模式只输出各自 gate，并且只接受唯一 `turn.succeeded`，拒绝 `turn.started`、失败和重复终态；恢复模式拒绝无线 adb，并要求发送中断网只读、radio 原样恢复、持久 session Relay cursor 严格增加和恢复后的新回答，且可选强制验证 LOCAL 进程回收后的 `turn.interrupted:needs_attention`、原输入单次持久化和不重放。当前机器仍缺目标真实拓扑，未伪造现场 PASS |
| 首批 RC manifest / 证据绑定契约 | PASS：锁定 Windows x64、Android APK、Cloud image digest、SemVer、完整 commit、协议与 SHA-256；正式批准必须提供 evidence root 并实际读取 19 个同版本/commit 的 PASS JSON，每份还必须是固定 live-evidence schema、含可从内容重算的 source SHA-256 且 `bound_gate_ids` 显式包含当前项，再交叉确认 A-01/APK、X-01/EXE signer/installer、C-01 HTTPS deployment/image digest 和 X-03 Host。最终 manifest 还会要求待上传 Android APK 与 A-01 哈希相同、至少一份待上传 Windows 安装包与 X-01 installer 哈希相同、Cloud metadata digest 与 C-01 运行部署相同；验收包或镜像和发布目标不同会拒绝。验证结果含固定 schema 与完整 gate ID 集，manifest 拒绝旧形状或手工裸对象。任意路径逃逸、绑定后篡改、错版本、错 commit、绑定错项、跨制品/Cloud/Host 拼接、缺证据或裸批准布尔值均拒绝 |
| 稳定发布台账门禁 | PASS：只接受恰好 19 个已知 P0、全部 `PASS` 且每行存在证据；除跨端制品/Cloud/Host 绑定外，A-06 还强制核对 Relay transport、离线只读、恰好一条中断命令、严格递增 cursor、进程回收后的 `needs_attention` 投影和恢复/离线 UI 哈希；RC/alpha/beta 强制 prerelease 并保持 `release_approved=false` |
| 稳定版 promotion 证据输入 | PARTIAL：候选 workflow 只接受 `vX.Y.Z-rc/alpha/beta` tag，并把 Windows/Android/manifest 版本解析为目标 `X.Y.Z`；新增受控 promotion workflow，在候选原 commit 上下载原 Release 字节、安全解压由确定性打包器生成的 19 项证据包、复验台账和制品哈希，再创建 `vX.Y.Z` tag 与稳定 Release，全程不调用 Tauri/Gradle/Docker 重建。25 项聚焦测试与两份 YAML 解析通过；尚未用真实 GitHub prerelease + 现场证据执行 promotion，故不能升为 PASS |
| Android Release 签名机制 | PASS（非生产证书）：本机一次性 RSA 测试证书完成 `assembleRelease`，`apksigner` 验证 APK Signature Scheme v2、单一 signer，注入的 `versionName=9.9.9`/`versionCode=999` 经 `aapt` 读回一致；正式 keystore RC 仍待执行 |
| Agent SDK `cargo test --workspace --locked` | PASS：清理 `agent-events` 的旧 worktree 构建缓存后，全 workspace tests 与 doc-tests 通过；初始失败确认为旧 binary 内嵌已删除路径 |
| Android `./gradlew test assembleDebug --no-daemon` | PASS：统一预检复跑 `BUILD SUCCESSFUL`，62 tasks 全部 up-to-date；包含生成 `BuildConfig.BUILD_COMMIT` 和精确终态语义 |
| 移动平台 adapter 契约（28 项） | PASS：Android Release commit 身份、远程 Grant、device proof/device token、LAN/Relay E2EE、实际 transport/Host UI 证据、receipt/event 解密、精确终态枚举与唯一成功标记、embedded Provider 畸形响应拒绝、持久历史注入和 pending Turn interrupted/needs-attention recovery 均覆盖 |
| Android 实体机 debug APK 安装/冷启动 | PASS（非门禁 smoke）：Android 14，APK SHA-256 `50fd4cc893f79dc2d4a10033a9975cb64f46a397d9fd4160ac6802d8a624c41e`；冷启动后无 FATAL、无 `adb reverse`。调试 APK 不能形成 A-01，正式签名 RC 仍待验收 |
| 桌面 Cloud/远程前端聚焦契约（含 Host 审批收件箱） | PASS：远程 UI、独立 controller/Host identity、device proof、LAN fallback、Relay `device_id`、Windows Release commit 与本机/远程 UI Automation 语义、Agent terminal 精确计数、Host 根布局待审批轮询与拒绝/批准语义，以及危险工具只允许 Host 本机审批均通过；完整 Node 契约为 `147 passed` |
| 桌面 Host bootstrap/Cloud client/Relay 聚焦后端（23 项） | PASS：Host 使用 OS Ed25519 身份完成 challenge proof，并换取绑定 Host 的有限 scope device token |
| Relay Host runtime 聚焦回归（新增序号/重连断言） | PASS：同步 bootstrap 会启动专用 discovery loop 并发送 Host heartbeat；pair Grant 会发现活动 remote session；锁定的 websockets 15 使用 asyncio connector；Cloud 重连提示持久 `next_sequence`，握手占用的 sequence 会进入 cipher 双向游标，首条 command/receipt 使用后继序号；Relay socket 会回传加密 Agent event，LAN 与 Relay 共用 canonical event projection |
| Windows Host identity 契约与 Release 门禁 | PASS（实现/工作流层）：Windows dispatch、Credential Manager round-trip mock、未知平台 fail-closed、脱敏 smoke 输出和清理共 5 项；Release Windows job 会在打包前运行真实 `CredReadW/CredWriteW/CredDeleteW` 往返。当前分支尚未触发 Windows runner，不能替代 X-03 现场 PASS |
| GitHub `v0.0.4` 桌面发布审计 | PARTIAL：2026-09-09 Release workflow `34387157614` 成功，公开资产含 `NoteMeld_0.0.4_x64_en-US.msi`（SHA-256 `b980d1247d77a296e880b85e820674b55080813c9da236e9b4f2014bfb332cf9`）及 updater `.sig`；不含 Android APK、Cloud image digest 或新 workflow 要求的 Authenticode 验证 |
| GitHub `v0.0.4` Cloud 审计 | FAIL（仅针对旧发布，不改变当前分支本地回归结果）：同 commit 的 Cloud workflow `34387157728` 因并发 workspace 配额用例得到 `[200, 400]` 而非 `[200, 413]` 失败；compose、Cloud image 和 mobile Cloud smoke 后续步骤全部跳过，因此 `v0.0.4` 不能作为首批 RC 基线 |
| GitHub Actions 签名 secrets 名称审计 | UNVERIFIED：当前活动 GitHub 账号可读取公开 workflow/release，但列出 Actions secrets 返回 HTTP 403；这只表示权限不足，不表示 secrets 未配置，需仓库管理员在打 RC 前按第 5 节逐项确认 |

## 4. RC 现场验收步骤

### Gate C：Cloud Agent 与 Relay

- [ ] C1 使用候选 Release 的 `cloud-image.json`，按 `image@sha256:...` 部署 production RC；把其中 commit/digest 分别注入 `NOTEMELD_CLOUD_BUILD_COMMIT`、`NOTEMELD_CLOUD_IMAGE_DIGEST`，记录域名和配置项是否存在，不记录密钥值。缺失或格式错误时 production 进程必须拒绝启动。
- [ ] C2 执行 `NOTEMELD_CLOUD_BASE_URL=https://... NOTEMELD_CLOUD_ADMIN_USERNAME=... NOTEMELD_CLOUD_ADMIN_PASSWORD=... NOTEMELD_EXPECTED_CLOUD_MODEL=... NOTEMELD_EXPECTED_CLOUD_COMMIT=<40-char-sha> NOTEMELD_EXPECTED_CLOUD_IMAGE_DIGEST=sha256:<64-hex> python3 scripts/release/verify_first_batch_cloud.py`；验证器只接受 production、OpenAI-compatible runner、Redis Relay、设备证明、全部 readiness 配置，以及与候选元数据相同的运行 commit/digest。
- [ ] C3 保留上一步 JSON 证据；验证器创建真实 `cloud_native` session，发送唯一 challenge，拒绝 deterministic model，并要求回答包含 challenge、事件只有一个成功终态且 snapshot cursor 一致。
- [ ] C4 执行 `NOTEMELD_CLOUD_BASE_URL=https://... NOTEMELD_CLOUD_ADMIN_USERNAME=... NOTEMELD_CLOUD_ADMIN_PASSWORD=... python3 scripts/release/verify_first_batch_relay.py`；保留脱敏 JSON。脚本先证明 `host_offline`，再以两个完成 proof 的独立 WSS 连接双向转发端侧可解密的 AES-256-GCM envelope；随后断开双方、重连并以 Cloud 返回的连续 cursor 完成第二次交换。只输出 challenge SHA-256，不输出明文、密码或 Token。
- [ ] C5 在能重启 production worker 且不删除持久数据的 operator 环境执行 `NOTEMELD_CLOUD_BASE_URL=https://... NOTEMELD_CLOUD_ADMIN_USERNAME=... NOTEMELD_CLOUD_ADMIN_PASSWORD=... NOTEMELD_EXPECTED_CLOUD_MODEL=... python3 scripts/release/verify_first_batch_c03.py --restart-command-json '["<platform-cli>","<restart-verb>","<deployment>"]' > cloud-c03-raw.json`。重启命令以 JSON argv 直接执行，不经过 shell；脚本必须在重启前捕获同一 session 的一条 running 和一条 queued，重启后等待租约 fail-closed 为 `needs_attention`，证明 queued attempt 仍为 0，再显式 abandon 中断命令并要求 queued 只执行一次、使用预期真实模型且只有一个成功终态。随后用绑定器只绑定 C-03；不得使用会清空数据库、滚动到另一数据卷或让旧 worker 继续存活的“重启”。
- [ ] C6 先让已配置真实模型的 Windows x64 Host 登录 production Cloud 并保持在线，执行 `NOTEMELD_CLOUD_BASE_URL=https://... NOTEMELD_CLOUD_ADMIN_USERNAME=... NOTEMELD_CLOUD_ADMIN_PASSWORD=... NOTEMELD_REMOTE_HOST_DEVICE_ID=... python3 scripts/release/verify_first_batch_remote_agent.py`；保留 durable receipt、唯一成功终态和 challenge/answer hash 的脱敏 JSON。随后仍须由 Windows/Android 真实 UI 建立 `device_remote` session；临时控制端结果不能替代 UI、LAN 或断线恢复项。
- [ ] C7 在可只读访问 live Cloud 数据卷、同一验收时间窗完整日志和 Redis 的 release operator 环境执行 C6；追加 `--security-audit-database /read-only/cloud.db --security-audit-log /exported/complete-window-logs`。进程从 `NOTEMELD_CLOUD_RELAY_URL` 和 `NOTEMELD_CLOUD_AGENT_API_KEY` 读取 Redis/Provider 配置，并把本轮 challenge、账户/设备 Token、握手 session key 直接从内存交给 `verify_first_batch_security_audit.py`；要求两个 E-01 release check 都为 `PASS`。DB 同目录 WAL/SHM 会自动纳入，日志必须先解压并覆盖本轮握手到终态；不得把 needle 原文放进 argv 或证据文件。

### Gate X：Windows x64

- [ ] X1 在干净 Windows x64 机器安装签名 RC；启动 UI 和 sidecar，健康检查通过。
- [ ] X1/X2 从正式 MSI 安装并启动 NoteMeld，并保留用于安装的原始 MSI/EXE；配置真实模型后执行 `python scripts/release/verify_first_batch_clients.py desktop --expected-model <model> --expected-version <RC-version> --installed-exe "C:\\Program Files\\NoteMeld\\NoteMeld.exe" > windows-runtime-raw.json`。脚本必须通过 Windows x64、运行 EXE、ProductVersion、Authenticode、sidecar 健康、模型存在、唯一 challenge 与成功终态，但只输出不能绑定任何正式 gate 的 `windows_local_agent_runtime`。然后让安装版停留在本机 Agent 工作区，执行 `powershell -ExecutionPolicy Bypass -File scripts/release/verify_first_batch_windows_local_agent.ps1 -InstalledExe "C:\Program Files\NoteMeld\NoteMeld.exe" -ExpectedInstaller "C:\RC\NoteMeld_<version>_x64_en-US.msi" -ExpectedVersion <RC-version> -ExpectedCommit <40-char-sha> -ExpectedModel <model> -RuntimeEvidence windows-runtime-raw.json > windows-x01-x02-raw.json`；脚本核对同一 EXE 的签名、哈希、版本和内嵌 commit，并要求安装包为带版本号的 Authenticode MSI/EXE、与运行 EXE 使用同一 signer，再记录 installer SHA-256；随后从真实 UI 选择同一模型、输入新的唯一 challenge，只在唯一成功 assistant 节点和发送恢复 idle 后同时输出 X-01/X-02。最后用绑定器对该结果同时指定 `--gate X-01 --gate X-02`；开发 EXE、旧包、未签名包、验收后换包、loopback-only 对话或重复/缺失终态均不能形成正式证据。
- [ ] X3 在 x64-B 安装版登录 Cloud 并保持在线；设置进程环境变量 `NOTEMELD_CLOUD_ACCOUNT_TOKEN`（不得写入命令行或证据），执行 `powershell -ExecutionPolicy Bypass -File scripts/release/verify_first_batch_windows_host_restart.ps1 -InstalledExe "C:\Program Files\NoteMeld\NoteMeld.exe" -ExpectedVersion <RC-version> -ExpectedCommit <40-char-sha> -CloudEvidence <bound-C01-C02.json> -RemoteHostEvidence <bound-C04-X06.json>`。脚本验证签名 x64 PE、重启前 Cloud 在线公钥、完全退出并重启同一安装版、无需打开 Cloud 页自动恢复 Host、Credential Manager device ID/公钥指纹稳定和 Cloud heartbeat 时间前进；输出只含脱敏 X-03 证据。撤销/拒绝仍按 X6/E2 单独纵向。
- [ ] X4 在 Windows x64-A 的安装版中登录 Cloud 并展开远程 Agent 面板；执行 `powershell -ExecutionPolicy Bypass -File scripts/release/verify_first_batch_windows_remote.ps1 -InstalledExe "C:\Program Files\NoteMeld\NoteMeld.exe" -ExpectedTransport lan -HostDeviceId <x64-B-device-id> -ExpectedVersion <RC-version> -ExpectedCommit <40-char-sha> -CloudEvidence <bound-C01-C02.json> -RemoteHostEvidence <bound-C04-X06.json>`。脚本必须校验精确运行路径、PE x64、Authenticode、ProductVersion 和安装版内嵌 commit，再通过 UI Automation 选择绑定 Host、读取实际 LAN、发送唯一 challenge，并得到唯一 `turn.succeeded`。
- [ ] X5 移除 x64-B 的 LAN candidate 并让两端仅能访问 Cloud；重复 X4 命令但改为 `-ExpectedTransport relay`。脚本必须从安装版 UI 读取实际 Relay，不能使用命令参数或候选列表代替连接结果。
- [ ] X6 执行真实 Host 验证器；成功对话后脚本会自动验证 Grant/设备撤销对当前连接和新连接均 fail-closed。另执行 Host 离线、重连、重复 request id 和危险工具审批场景，状态与审计符合规范。

### Gate A：Android

- [ ] A1 在实体 Android 安装候选 APK；执行 `python3 scripts/release/verify_first_batch_clients.py android-runtime --expected-version <RC-version> --expected-commit <40-char-sha> --expected-apk <signed-RC.apk> --expected-signer-sha256 <pinned-64-hex-cert-digest> --apksigner <Android-SDK-build-tools/apksigner> [--serial <serial>] > android-a01-raw.json`。脚本要求从真实 UI 读取 APK 内嵌 commit、v2/v3 签名、恰好一个固定 signer，并回拉设备上的 APK 与候选制品做字节级 SHA-256 比对；缺任一制品参数、错 commit、旧版本、split APK、模拟器、签名或字节不一致都不能形成 A-01。随后用证据绑定器生成 `android-a01-bound.json`，再人工验证后台恢复和前台会话无 fatal crash。
- [ ] A2 开发 smoke 可执行 `python3 scripts/release/verify_first_batch_clients.py android-agent ...`，但该 helper 会临时建立 USB loopback/`adb reverse`，输出明确标记为 `development_checks` 且 `release_evidence=false`，不得作为 A-02 或任何最终 RC 证据。最终 A-02 必须在无 USB 调试、无 `adb reverse`、无外部 backend 的 embedded runtime 条件下执行。
- [ ] A3 先完成 A1、C2 并保留绑定证据；在 Android 设置页登录同一 production Cloud 后，执行 `python3 scripts/release/verify_first_batch_clients.py android-cloud-agent --expected-version <RC-version> --expected-commit <40-char-sha> --base-url https://... --expected-model <model> --android-artifact-evidence android-a01-bound.json --cloud-evidence <bound-C01-C02.json> [--serial <serial>]`。脚本要求当前安装 APK 仍与 A-01 签名 RC 完全一致，live `/ready` 仍为 production/OpenAI-compatible、应用内嵌同一 commit 并显示同一 Cloud URL，再从 assistant 节点取得新的唯一 challenge 和唯一成功终态。
- [ ] A4 先保留 A1、C2 与 C6 的绑定证据；Android 与 x64-B 同 LAN，执行 `python3 scripts/release/verify_first_batch_clients.py android-remote-agent --expected-version <RC-version> --expected-commit <40-char-sha> --base-url https://... --expected-cloud-model <Cloud-model> --host-device-id <x64-B-device-id> --expected-transport lan --android-artifact-evidence android-a01-bound.json --cloud-evidence <bound-C01-C02.json> --remote-host-evidence <bound-C04-X06.json> [--serial <serial>]`。脚本必须重新核对当前 APK 哈希、匹配应用显示的 Host 哈希、UI 回报的实际 `lan`、assistant 最终回答与唯一成功终态。
- [ ] A5 移除 LAN candidate 并让 Android 走独立蜂窝网络，重复 A4 命令但改为 `--expected-transport relay`；脚本必须从 UI 读到实际 `relay`，配置值或“自动连接成功”不能替代该证据。
- [ ] A6 通过 USB adb 连接实体机（不能使用无线 adb），确保已完成 A5 的 Relay 配置；执行 `python3 scripts/release/verify_first_batch_clients.py android-recovery --expected-version <RC-version> --expected-commit <40-char-sha> --base-url <https-production-cloud> --expected-cloud-model <model> --host-device-id <x64-B-device-id> --android-artifact-evidence android-a01-bound.json --cloud-evidence <bound-C01-C02.json> --remote-host-evidence <bound-C04-X06.json> --verify-process-recovery [--serial <serial>]`。脚本先重新核对当前安装 APK 与 A-01 哈希及内嵌 commit，再记录 radio 原状态并完成第一个 Relay challenge；发送第二条唯一命令后立即关闭 Wi-Fi/移动数据，要求 UI 输入为 disabled、显示离线只读、发送终止、该用户命令只出现一次且没有收到对应回答；随后恢复原状态，旧命令仍不得出现回答，第三条 challenge 必须复用按 Host 持久 session，UI Relay cursor 严格大于首次值；最后在无网络/loopback backend/`adb reverse` 的 LOCAL 模式让真实 turn 进入 sending 后强杀并重启应用，必须看到原输入恰好一次、`turn.interrupted:needs_attention` 和“未知副作用未自动重放”恢复投影，不能出现原回答。任一步失败也会尝试恢复 radio。
- [ ] E2/A7 先设置环境变量 `NOTEMELD_E02_DANGEROUS_PROMPT` 为一个明确要求调用已配置危险工具的唯一 prompt。拒绝场景：在 Windows Host 先运行 `verify_first_batch_windows_host_approval.ps1 -Mode deny ...`，再从另一终端运行 `verify_first_batch_remote_agent.py --approval-scenario deny ...`；两边分别保存 JSON，远程结果用 `bind_first_batch_evidence.py` 绑定 C-04/X-06。超时场景：完全退出 Host，在启动安装版的同一进程环境设置 `NOTEMELD_AGENT_APPROVAL_TIMEOUT_SECONDS=15`，先运行 UIA 脚本 `-Mode expired`，再运行远程验证器 `--approval-scenario expired --agent-timeout 120`，不得触碰批准/拒绝。最后执行 `python3 scripts/release/verify_first_batch_e02.py --denial-remote <bound-deny-remote.json> --denial-host <deny-host.json> --expiry-remote <bound-expiry-remote.json> --expiry-host <expiry-host.json>`；只有输出 `e_02:PASS` 后才用绑定器绑定 E-02。该结果同时要求至少 denial 远程证据包含完整 Grant/设备撤销。Android 另确认撤销后现有/新连接不能发送、重新授权后才恢复；控制端始终不能代批。

## 5. 每条现场证据必须记录

- RC 版本与 commit；Cloud image digest；Windows 安装包和 APK SHA-256。
- 测试时间、设备/OS、网络拓扑、session/turn/request id（脱敏）。
- 实际 transport：LAN 或 Relay，不接受“自动选择成功”但无法说明路径。
- Cloud 收到的 envelope、Host durable receipt、Agent terminal event 和客户端最终回答。
- 断线/撤销/审批的预期错误码与 UI 文案。
- 屏幕录像或截图，以及去敏日志路径；不得保存 Token、密钥或真实用户数据。

正式 RC tag 前还必须在仓库 Actions secrets 中配置以下名称（只记录“已配置/未配置”，不得把值写入台账）：

- `TAURI_SIGNING_PRIVATE_KEY`、`TAURI_SIGNING_PRIVATE_KEY_PASSWORD`：桌面 updater 签名。
- `WINDOWS_CERTIFICATE_BASE64`、`WINDOWS_CERTIFICATE_PASSWORD`：Windows Authenticode PFX。
- `ANDROID_KEYSTORE_BASE64`、`ANDROID_KEYSTORE_PASSWORD`、`ANDROID_KEY_ALIAS`、`ANDROID_KEY_PASSWORD`：Android release APK。

Release workflow 还要求以下 GitHub Actions repository variables提供独立 SDK
artifact 下载地址和 SHA-256；它们不是源码仓库内的 SDK 副本，缺失或摘要不匹配时
Cloud/macOS/Android job 会在打包前失败：

- `NOTEMELD_AGENT_SDK_ARM64_WHEEL_URL`、`NOTEMELD_AGENT_SDK_ARM64_WHEEL_SHA256`
- `NOTEMELD_AGENT_SDK_X86_64_WHEEL_URL`、`NOTEMELD_AGENT_SDK_X86_64_WHEEL_SHA256`
- `NOTEMELD_AGENT_SDK_AAR_URL`、`NOTEMELD_AGENT_SDK_AAR_SHA256`
- `NOTEMELD_AGENT_SDK_LINUX_WHEEL_URL`、`NOTEMELD_AGENT_SDK_LINUX_WHEEL_SHA256`
- `NOTEMELD_AGENT_SDK_LINUX_LIBRARY_URL`、`NOTEMELD_AGENT_SDK_LINUX_LIBRARY_SHA256`

19 项现场证据全部 PASS 后，在 operator 机器执行：

```bash
python3 scripts/release/package_first_batch_live_evidence.py /path/to/ledger.md \
  --output first-batch-live-evidence.zip \
  --expected-version X.Y.Z \
  --expected-commit <candidate-40-char-sha>
gh release upload vX.Y.Z-rc.N first-batch-live-evidence.zip
gh workflow run promote-first-batch.yml \
  -f candidate_tag=vX.Y.Z-rc.N \
  -f stable_tag=vX.Y.Z
```

打包器会先实际读取全部 19 份绑定 JSON，输出已存在时拒绝覆盖。promotion 只接受已存在的 prerelease、要求稳定 tag 尚不存在、校验安全 ZIP 路径，并在同一 commit 上复用候选 Release 文件；稳定 tag 不会再次触发候选构建 workflow。证据包必须保持脱敏，不随稳定 Release 发布，并在稳定 Release 创建成功后从候选 Release 删除。

## 6. 当前总体进度口径

实现层已经具备大部分组件，但首批用户纵向尚未闭环。按 19 个 P0 结果计，目前为 `0 PASS / 15 PARTIAL / 4 UNVERIFIED`；这是严格发布口径，不代表代码完成度为零。下一步优先级固定为：

2026-09-14 本次 operator 环境只读检查显示：Android 实体机 `24115RA8EC` 在线并完成 debug cold-launch smoke，但当前 shell 仍未配置 production Cloud URL/管理员凭据/真实模型、远程 Host、签名和 E-01 审计变量。该结果只描述本机当前会话，不等同于 GitHub Actions secrets 未配置；仓库 secrets 仍因权限不足保持 `UNVERIFIED`。

1. 准备真实 Provider 的 Cloud RC 和测试账号（C-02）。
2. 生成同一 commit 的 Windows x64 RC 与 Android APK，并记录哈希。
3. 准备第二台 x64 Host 与 Android 实体设备，执行 LAN/Relay 双路径。
4. 完成动态明文泄漏、断线恢复、撤销和审批审计。
