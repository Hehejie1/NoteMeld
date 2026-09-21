# Known Pitfalls

## 桌面、Android 和 Cloud RC 来自不同 commit 或只有 updater 签名

- 风险：旧发布流水线只生成桌面制品；`TAURI_SIGNING_PRIVATE_KEY` 只证明 updater 包签名，不能证明 Windows MSI/EXE 已通过 Authenticode。手工加入 APK/Cloud 镜像还可能来自不同 commit，导致设备协议偶发不兼容且无法回滚到同一批次。
- 不允许：把 Tauri updater `.sig` 当 Windows 系统代码签名；发布 unsigned Android release；只记 tag 不记完整 commit/image digest；手工拼接三端制品。
- 检查方式：正式 tag workflow 必须通过 Windows `signtool verify /pa`、Android `apksigner verify`，并由 `scripts/release/generate_first_batch_rc_manifest.py` 生成 `first-batch-rc.json`。Windows 实机先由 `verify_first_batch_clients.py desktop` 校验运行 EXE、sidecar 和 loopback canonical Agent，形成不能绑定 X-01/X-02 的 `windows_local_agent_runtime` 子证据。随后必须由 `verify_first_batch_windows_local_agent.ps1` 核对同一 EXE 的 PE x64、ProductVersion、Authenticode、哈希与内嵌 commit，再驱动安装版 UI 选模型、输入新的唯一 challenge，并从唯一 `turn.succeeded` assistant 语义节点读取回答；只有该结果同时形成 X-01/X-02。清单必须保留三端身份、SHA-256 和 `notemeld.sync.v1`；`release_approved=true` 只能来自台账中 19 个可读取、对应 check 为 PASS、且由 `bind_first_batch_evidence.py` 绑定同一版本/commit 的 JSON，禁止裸布尔开关。
- 修复经验：Windows PFX 和 Android keystore 只从 Actions secrets 临时导入；Cloud 镜像按 commit SHA 推送 GHCR 并记录不可变 digest；清单默认 `release_approved=false`，现场 19 项全 PASS 后才允许发布决策。
- 发布分层：`-rc`/`-alpha`/`-beta` tag 必须是 prerelease；稳定 tag 必须先通过 `verify_first_batch_ledger.py`，不能仅因为构建成功就发布正式版本。

## 用开发 Cloud 回显冒充生产 Agent 验收

- 风险：`/health`、开发环境 `/ready` 和 deterministic runner 都能快速返回成功；如果只看 HTTP 200 或输出中包含输入文本，会把单进程 memory Relay 和固定回显误记为真实 Provider/生产 Cloud 可用。若终态 model 直接回显本地配置，或忽略 `finish_reason=length`，上游换模和截断回答也会被伪装成成功。
- 不允许：用 HTTP 地址、`environment=development`、memory Relay、deterministic model、多个 terminal event、本地配置回显的 model 或非 `stop` 的普通回答通过 C-01/C-02。
- 不允许：仅凭相同 Cloud URL 认定后续现场证据属于同一部署。C-01 必须记录 `/ready` 返回的完整 build commit 与 `sha256:` 镜像摘要；C-02～C-05、X-03～X-06、A-03～A-06、E-01/E-02 必须传播并由最终台账逐项核对这两个值，Windows 组合证据也必须先核对 Cloud 与真实 Host 子证据。部署侧应使用 `image@sha256:...` 并注入实际摘要。
- 检查方式：执行 `scripts/release/verify_first_batch_cloud.py`；它要求 HTTPS、production、OpenAI-compatible backend、Redis、设备证明、完整非敏感 readiness 配置，并要求 `/ready` 的 build commit/image digest 与候选 `cloud-image.json` 一致；随后验证 Provider 实际报告的模型与显式声明的生产模型一致、唯一 challenge/成功终态和一致 snapshot cursor。`desktop/backend/tests/test_cloud_agent.py` 还覆盖模型漂移与截断终态。
- 修复经验：`/ready` 只公开 `environment`、`agent_backend` 和检查名称/状态，不公开 Provider、Redis、SMTP、S3 的地址或凭据；Cloud runner 从响应读取实际 model 并校验 finish reason；真实 Provider 是否可用仍以带唯一 challenge 的纵向对话证明。

## 只看 E2EE 代码或空 API 投影就宣称 Cloud 无明文泄漏

- 风险：端侧加密和 `commands/events=[]` 只能证明正常业务表没有保存 device-remote payload；部署平台 access log、异常日志、SQLite WAL/SHM、Redis 当前 keyspace 或错误诊断仍可能泄漏 token、密文 envelope，甚至误打印端侧传入的业务内容。
- 不允许：用静态代码搜索、Cloud capability 声明或单元测试替代目标 RC 动态审计；把“Cloud 没有 command row”扩大为日志、Redis 和会话密钥全部安全。
- 检查方式：`test_device_remote_relay_payload_and_tokens_are_absent_from_cloud_storage_and_application_logs` 必须证明 Relay 往返后只留下 cursor；`verify_first_batch_remote_agent.py` 必须在清理前确认该 session 的 Cloud command/event 投影为空。E-01 最终 PASS 还必须通过 `verify_first_batch_security_audit.py` 对同一 production RC 的有界平台日志、Cloud DB/WAL/SHM 和 Redis keyspace 执行动态扫描；审计器要求 session 仍存在且有双向 cursor，防止拿旧快照或无关 DB 冒充。
- 修复经验：Relay 只解析路由 envelope 并瞬时 Pub/Sub 转发，不记录 frame body；日志只记录非敏感状态/ID。动态审计证据必须记录扫描范围和 hash，不复制发现的 secret 原文。

## 桌面控制端与 Host 复用设备 ID 或公钥

- 风险：桌面 Web UI 的控制端密钥和 sidecar 的 OS Host 密钥登记到同一 device id，会触发公钥轮换、撤销既有 device token 并清除 recent proof；若 Host id 尚未解析就启动 bootstrap，还可能把控制端 id 短暂注册成 Host，导致生产 Relay proof 随机失败。
- 不允许：用 `openDeviceKeyMaterial()` 得到的控制端公钥注册 Tauri Host id；把控制端 device id 作为 Host id 的初始占位；Host 只注册不完成 challenge 就长期持有账户 token。
- 检查方式：运行 `frontend/tests/cloudSessionPanelContracts.test.mjs` 和 `backend/tests/test_cloud_sync_bootstrap.py`；确认控制端使用 `desktop-controller-*` 身份，Host bootstrap 等待 `get_desktop_device_id()`，并由 OS Ed25519 私钥完成 proof 后换取绑定 Host 的有限 scope token。
- 修复经验：控制端负责选择 Host、创建 Grant 和端到端握手；Host 身份只由 sidecar/OS secure store 管理。两者可以属于同一账号，但必须是两个独立设备与密钥生命周期。

## Windows x64 可以安装，但 Host identity 永远不可用

- 风险：只实现 macOS Keychain/Linux Secret Service，并把 Windows 当“不支持平台”，会让 `/api/cloud-sync/host/bootstrap` 在 Windows 安装包中必然 fail-closed；桌面 UI 和 Agent 本机对话可能正常，LAN/Relay Host 却永远无法注册。
- 不允许：用普通文件、注册表明文、环境变量或 device id 派生 Ed25519 private key；仅靠 macOS 上 monkeypatch `platform.system()` 宣称 Windows 可用；把 updater/Authenticode 签名误当 Host 身份可用证据。
- 检查方式：`test_cloud_secure_identity.py` 覆盖 Windows dispatch、round-trip、未知平台 fail-closed；`scripts/release/verify_windows_secure_identity.py` 必须在 Windows Release runner 上通过真实 Credential Manager 创建/重读/清理，然后才能构建 sidecar。
- 修复经验：使用 Win32 `CredReadW/CredWriteW/CredDeleteW` 的 Unicode Generic Credential，限定当前登录用户并只保存短 Ed25519 原始密钥的 Base64；两条 credential 任一写入失败时回滚已写 private。现场 X-03 仍需用最终签名 RC 重启后证明 identity 稳定。

## Android 有 E2EE 代码，但生产 Relay 仍立即拒绝

- 风险：只注册 Android 公钥后直接拿账户 token 打开 Relay，没有创建 device-pair Grant、没有完成 recent device proof，也没有换取 device-bound token；开发配置可能掩盖 proof 缺失，生产 `NOTEMELD_CLOUD_REQUIRE_DEVICE_PROOF=true` 会 fail-closed。固定 `Thread.sleep(60_000)` 还会让已完成回答持续显示发送中。
- 不允许：把“能构造加密帧”等同于“远程链路可用”；长期以账户 token 充当移动设备 bearer；把 Android 自身或桌面 controller 误列为可连接 Host；无视 terminal event 固定等待。
- 检查方式：运行 `frontend/tests/mobilePlatformAdapterContracts.test.mjs` 与 `android/gradlew test assembleDebug`；Release workflow 必须注入完整 `NOTEMELD_ANDROID_BUILD_COMMIT`，所有 Android 现场模式都从实体包 `notemeld-build-commit:*` UI 语义核对目标 RC。A-02～A-06 还必须读取绑定后的 A-01 证据，并在每次对话/恢复验收前回拉当前安装 APK，核对 SHA-256 仍是同一签名 RC，防止 A-01 后换装同版本 debug 包。现场用 `verify_first_batch_clients.py android-remote-agent` 分别确认 LAN 和蜂窝 Relay；证据必须读取连接成功后 transport 的实际值并匹配所选 Host 哈希，不能从“存在 LAN candidate”、外部 JSON commit 或命令参数推断。

## Android 本地 Agent 成功但界面没有回答

- 风险：canonical Agent SSE 的流式正文使用 `payload.delta`，如果移动 adapter 只读取 terminal 常见的 `payload.content`，turn 可以成功而 UI 一直没有模型正文；后台投影刷新若用新的 `initialState` 重建整个 Compose surface，还会每 5 秒清掉当前会话；IO 回调直接写 Compose 状态会引入线程竞态。把本机 8483 投影状态当成全局网络状态，还会在纯手机场景错误禁用 Cloud/远程对话。验收脚本若只在整页搜索 challenge，会把用户自己的输入误判为回答；若用 `startsWith("turn.")` 判断终态，`turn.started` 会提前释放等待，回答后再出现 `turn.failed` 也可能被误收为成功。
- 不允许：为 Android 制造第二套 Agent loop 或静态成功回答；只断言请求成功/进程存活；以轮询投影覆盖当前屏幕/消息；从 IO 线程直接 dispatch UI action；用本机 sidecar 离线禁用 Cloud/远程 adapter；把每个 delta 永久拆成独立气泡；在不区分 user/assistant 角色的 UI dump 中搜索 challenge；把任意 `turn.*` 或仅回到 idle 当成成功。
- 检查方式：adapter 必须兼容 `delta/answer/content/output` 的 canonical 文本字段，并在主线程把连续 assistant delta 归并；投影刷新只合并服务端连接/记忆状态；可交互条件按本机/Cloud/远程 location 判断。`verify_first_batch_clients.py android-agent` 仅是显式标记的 `adb reverse` 开发 smoke，不能产生 Release P0 PASS；最终 Android 候选包只使用 `android-cloud-agent`/远程现场门禁，并只拼接 `notemeld-message-assistant` 语义节点，要求 UI 暴露的终态列表精确等于唯一 `notemeld-agent-terminal:turn.succeeded:1`；失败、取消、中断或重复终态全部拒绝。
- 修复经验：移动 Surface 保留当前导航、输入和消息，只从周期刷新吸收连接/投影字段；IO transport 回调切回 Compose scope。远程发送前按 controller/desktop Host 创建或复用标准 Grant，签署 `notemeld-device-proof-v1` challenge，领取不撤销账户 token 的有限 scope device token；仅列出桌面 Host，并仅用精确的 `turn.succeeded|failed|cancelled|interrupted` 释放等待，同时保留终态类型和累计数供现场核验。

## LAN-first 直连泄露 cloud bearer 或绕过 Grant

- 风险：把 cloud WebSocket URL 机械替换为 `ws://192.168.x.x` 并继续携带 bearer，会让局域网监听者获得长期凭证；只检查设备 ID 或 `ipaddress.is_private` 还会接受保留地址、旧 Grant、错误 workspace 或 stale authority epoch。
- 不允许：在 LAN hello/query/header 中发送 cloud token；把候选地址当授权；宿主自行信任控制端声明的 scope；在 AEAD 验证或 durable enqueue 前返回 received；让 Python 使用 ChaCha20 而 Web 使用 AES-GCM；允许 handler 返回任意明文结果。
- Web 端的连接策略同样不得把 `bearer.<token>` 子协议用于 LAN；没有实现 `LanHandshake` 时必须跳过 LAN 候选并回退 `wss` Relay。
- 检查方式：运行 `backend/tests/test_cloud_lan_authorization.py`、`test_cloud_lan_auth.py`、`test_cloud_lan_transport.py`、`test_cloud_connection.py`，以及 `frontend/tests/relayCryptoInterop.test.mjs`。
- 修复经验：宿主用绑定 device token 通过 HTTPS 获取 60 秒云端断言；控制端只在 LAN 上提交 Ed25519 一次性 proof 和 E2EE frame；结果/event 必须继续使用 encrypted `RemoteFrame`，明文只允许无业务内容的最小 durable receipt。

## 远程危险工具等待审批，但控制端看起来只是卡住

- 风险：Host canonical Agent 发出 `approval.required` 后，Windows/Android 控制端若只处理文本 delta 和 terminal event，会持续显示“等待”，用户无法判断是网络故障还是安全门禁；贸然在控制端增加普通批准按钮又会绕过 Host authority。
- 不允许：标准远程 Grant 包含 `dangerous.approve`/`approval.remote.resolve`；控制端静默自动批准；让安装版审批 list/resolve 绕过 `X-NoteMeld-Session`；把没有 terminal event 的审批等待记为成功或超时后重放命令。
- 检查方式：标准 Grant 只含消息、事件、上下文、模型和普通工具 scope；Windows 与 Android 都必须把 `approval.required` 显示为 Host 本机审批提示，且远程组件不调用 approval resolve API。运行 Agent 的桌面 Host 必须在应用根布局持续读取 durable `waiting_approval` Turn，不能要求用户先找到远程 session；列表只能显示会话名、风险、摘要和截止时间。
- 修复经验：审批 authority 保留在运行 Agent 的 Host；控制端只投影加密审批事件与安全说明。Host 通知收件箱通过既有 native approval control 作出决定，处理或超时后随 Turn 状态自动消失，不建立第二套审批状态；工具参数、action digest 和 Provider payload 不进入列表 API。拒绝、超时、撤销仍必须分别形成现场门禁证据。
- 现场门禁：拒绝/超时必须是两个不同 approval ID。远程证据要求 `approval.resolved` 分别为 `deny`/`expired`、对应 call 没有 `tool.started`，Windows UI 证据用 approval ID 哈希与之绑定；超时还必须以 `turn.failed + approval_expired` 结束。只有 `verify_first_batch_e02.py` 同时验证这两条链路和 Grant/设备撤销后才允许产生 `e_02: PASS`，子证据名不得以 `e_02` 开头，避免被通用绑定器误升格。

## Windows 远程连接截图看似成功，但无法证明目标 Host 和实际 transport

- 风险：设备下拉框中的 `LAN` 只表示候选存在，配置参数中的 `relay` 只表示预期；二者都不证明本次 WebView2 连接实际采用对应路径。截图也无法可靠绑定 RC、Host device id、assistant 消息与唯一终态。
- 不允许：用候选列表、命令参数、普通截图或 Cloud Relay receipt 代替安装版 UI 的最终状态。
- 检查方式：远程面板必须暴露稳定的 Host、连接、transport、输入、发送、assistant 和 terminal 可访问性语义；Release 构建把完整 commit 注入只读 `notemeld-build-commit:*` 可访问性标记。Windows x64-A 使用 `verify_first_batch_windows_remote.ps1`，校验精确运行 EXE 的 PE x64、Authenticode、版本和内嵌 commit，再输入已绑定同一 RC/Cloud 部署的 C-01/C-02 与 C-04/X-06 证据，分别执行 LAN 和 Relay。
- 修复经验：UI 只在 `connectLanRemoteClient` 返回后发布实际 transport；现场工具读取选中 Host device id、连续 assistant 输出和恰好一个 `turn.succeeded`，证据只保留 Host/challenge/answer 哈希。
- 本地 wiring 必须走 `CloudSyncHostRuntime`/`install_lan_direct_service()` 的显式依赖注入；没有平台安全存储得到的 CloudClient、私钥和 cipher resolver 时保持端点关闭，不能为了 smoke test 从环境变量读取长期凭证。

## 桌面源码可用，但发布包缺少端侧加密运行时

- 发生过的问题/风险：开发虚拟环境已安装 `cryptography`，云端测试和令牌加密测试都通过，但桌面 `requirements-core.txt` 未声明该依赖；同时 E2EE 原语只位于不会被 PyInstaller 收集的 `cloud/crypto.py`。发布后的 sidecar 会在导入令牌存储或建立加密会话时失败。
- 不允许：依赖开发机的传递安装；只修改 cloud requirements；把端侧私钥或解密逻辑移入 Relay；让 cloud 反向 import backend；在端侧维护两份加密实现；先普通权限创建明文临时 token 文件再 chmod。
- 检查方式：运行 `backend/tests/test_cloud_packaging_contracts.py`、`backend/tests/test_cloud_crypto.py` 和 `backend/tests/test_cloud_token_store.py`；确认桌面与 cloud 锁定相同版本，canonical E2EE 模块位于 `app.cloud_sync`，cloud 不依赖它，失败的原子替换保留旧 token 且清理临时文件。
- 修复经验：端侧加密实现只放入被桌面收集的 backend namespace；cloud 只消费协议，不导入端侧模块；临时文件通过 `os.open(..., 0o600)` 创建，文件 fsync 后原子替换并尽力同步父目录。

## 把 relay_accepted 当成宿主已收到

- 风险：Relay 向 peer socket 写入成功后立刻向控制端显示“已送达”，但宿主可能在解密、授权或 durable enqueue 前崩溃，command 实际丢失。
- 不允许：云端代替宿主生成 received receipt；入队前回 receipt；receipt 携带 input/工具参数；Host 接受额外 command 字段。
- 检查方式：`backend/tests/test_cloud_remote_host.py::test_remote_host_receipts_only_after_durable_enqueue`。
- 修复经验：relay_accepted 只表示传输接纳；平台先验证 AEAD，再经 `RemoteHostAuthority` 授权和事务入队，成功后由宿主生成最小 received receipt。

## Relay 收到 command/receipt，但控制端永远等不到 Agent 终态

- 风险：Host 只把 Agent event 投影到 LAN websocket，或 Relay 自动发现逻辑用 `set[dict]` 收集 device-pair Grant 并在循环内静默抛错；此外 `/host/bootstrap` 是同步 FastAPI 路由，若 `install()` 只尝试 `get_running_loop()`，discovery 根本不会启动。即使启动，若 Host 心跳只由 Cloud React 页面发送，切页约 90 秒后设备也会被判离线。锁定的 `websockets==15.0.1` 还有两套 connector API：legacy `websockets.client.connect` 使用 `extra_headers`，把 `additional_headers` 传给它会在真实联网时失败。
- 风险：若桌面 Host bootstrap 只挂在 Cloud 页面 effect，安装版重启停留在普通工作区时不会恢复 Host，Cloud 设备虽保留注册记录却无法接受 LAN/Relay 连接。Host 恢复必须位于应用根生命周期，从加密 token store + OS identity 启动；Windows RC 需关闭并重启真实安装 EXE，核对同一 device id/公钥指纹以及 Cloud `last_seen_at` 前进，不能用临时 Credential Manager round-trip 代替。
- 不允许：把 receipt 当最终回答；只在 `LanDirectService` 注册 event sink；把 Relay discovery/Host heartbeat 绑定到某个 React 页面；在同步 bootstrap 无 loop 时静默跳过后台 runtime；混用 legacy connector 与 asyncio connector 参数；让 discovery 的异常被重试循环长期吞掉而没有聚焦测试。
- 检查方式：运行 `test_cloud_runtime.py::test_host_runtime_projects_agent_event_as_encrypted_event_frame`、`test_cloud_relay_host.py::test_relay_host_schedules_encrypted_agent_events_on_active_socket`、`::test_relay_host_default_connector_uses_websockets_asyncio_api` 和 `test_cloud_relay_lifecycle.py::test_sync_runtime_install_starts_relay_discovery`。最后一项必须以普通同步调用安装 runtime，并同时观察 heartbeat 与 session discovery。
- 修复经验：同一个 canonical Agent event 加密一次后投影到当前 LAN/Relay transport；同步 bootstrap 启动由 runtime 管理的专用 asyncio 线程，异步构造仍复用当前 loop；同一循环维持 device heartbeat 与授权 session discovery，关闭时跨线程安全取消并 join。Relay Host 使用 `websockets.asyncio.client.connect(additional_headers=...)`，保存其 event loop/socket，只接受 Host→controller 的加密 event frame 进行跨线程调度；device-pair Grant 显式映射全部 active `device_remote` session。

## Relay 握手成功，但第一条 receipt 被判为重放

- 风险：Cloud 对 handshake 与业务帧共用每个发送设备的持久 sequence 游标；若 Host 返回 sequence 1 的 handshake 后安装一个游标仍为 0 的 `SessionCipher`，第一条 receipt 会再次使用 sequence 1，被 Cloud 以 `replayed relay envelope` 拒绝。控制端表现为已连通、command 已发送，但一直等不到 durable receipt。
- 不允许：把 handshake 当成 sequence 之外的特殊帧；安装新 cipher 后从 0 重新计数；只验证密钥相等而不验证握手后的双向游标。
- 检查方式：运行 `test_cloud_runtime.py::test_host_runtime_completes_relay_handshake_and_installs_cipher` 和 `test_cloud_relay_host.py::test_relay_host_decrypts_first_post_handshake_command_and_returns_sequence_two_receipt`；前者必须证明握手 sequence 已进入 cipher，后者必须证明首条 command 与加密 receipt 均使用 sequence 2。
- 修复经验：Host 验证 signed offer 后，以入站 handshake sequence 初始化 `last_received_sequence`，以返回 handshake sequence 初始化 `last_sent_sequence`，再安装 cipher；后续 receipt/event 只能从下一序号开始。

同一问题在断线重连时还有第二层：Cloud 的 replay cursor 会跨 socket 和进程持久化，端侧若重新硬编码 handshake sequence 1，握手本身就会被拒绝。Relay 注册新 socket 后必须先返回只含该发送设备 `next_sequence` 的 `relay_ready`；Web、Android 与桌面 Host 都等待并校验该值，再构造 signed handshake。`verify_first_batch_relay.py` 必须让双方完成一次交换、真实关闭 socket、重连并以精确递增的双向 cursor 完成第二次交换；任一 cursor 重置都要失败。禁止通过断开连接或重置数据库游标来“修复”重连，因为那会恢复旧密文的重放窗口。

## Durable mailbox 连续领取多个 active Turn

- 风险：只把 `pop()` 做成“取第一条 queued 并改 admitted”，却不先检查 active 状态，同一 session 可并行执行多个 Turn；重启后还可能越过未知副作用继续下一条。
- 不允许：重启时把 admitted 自动当 queued；存在 `needs_attention` 时继续接收消息；authority epoch 变化后接受旧 epoch command。
- 检查方式：`backend/tests/test_cloud_sync_protocol.py::test_durable_mailbox_allows_only_one_admitted_turn_across_restart` 和 `::test_durable_mailbox_authority_rotation_fences_old_active_turn`。

## Cloud 只在启动时检查 running lease

- 风险：新 API 进程启动时若旧 worker 的 lease 尚未到期，会正确保留该命令；但旧 worker 已死亡且之后无人再次检查时，命令会永久停在 `running`。多个 API 进程若只对具体 command 做抢占，也可能各自领取同一 session 的不同 queued 命令。
- 不允许：启动时无条件打断 active lease；只做一次启动恢复后假设 lease 一定会被 heartbeat 续期；或在同一 session 已有 `running`/`needs_attention` 时继续 claim。
- 检查方式：`desktop/backend/tests/test_cloud_backend_slice.py::test_cloud_startup_preserves_running_command_with_active_lease`、`::test_cloud_reconciler_marks_crashed_worker_after_lease_expires`、`::test_cloud_command_claim_is_single_active_turn_per_session` 和 `::test_abandon_needs_attention_continues_next_queued_command`。
- 修复经验：复用同一个 `BEGIN IMMEDIATE` stale-lease 仲裁，在 lifespan 中启动有界周期 reconciler；只处理无 lease/已过期行，产生唯一 `turn.needs_attention`，并唤醒长轮询等待者。Claim 事务先做 session active 门禁；abandon 后若仍有 queued 命令则显式拉起 worker。

## 设备撤销但设备 Bearer 仍有效

- 风险：只把设备标记为 revoked、只撤销 remote grant，泄漏到该设备的 bearer 仍能继续访问 session/workspace API。
- 不允许：把账户 token 当作长期设备身份；设备交换成功后仍默认保留 bootstrap token；签发设备 token 时不验证设备私钥；rotation 丢失 `device_id` 绑定；撤销设备后等待 token 自然过期。
- 检查方式：`backend/tests/test_cloud_backend_slice.py::test_device_bound_token_requires_proof_and_is_revoked_with_device` 和 `::test_device_token_rotation_preserves_device_binding_and_expiry`。
- 修复经验：账户 token 只用于 bootstrap；设备完成 Ed25519 challenge 后领取短期 `device-api` token。认证时联查 active device，设备撤销事务同时撤销 grant 和所有匹配 device token。

应用协议唯一规范源：[`application-protocol-v1.md`](application-protocol-v1.md)。插件协议由 `notemeld-plugins/docs/system/plugin-protocol-v1.md` 维护。

- 本地 workspace 可能将独立插件仓库放在 `packages/notemeld-plugins/`；官方 `official.link-note` fixture 的发现必须同时支持已打包资源、`NOTEMELD_PLUGINS_DIR`、根目录 sibling 和 workspace `packages/` 路径。全新数据目录启动时缺失 fixture 必须明确失败，不能静默回退到旧实现。
- PyInstaller 桌面打包同样必须拿到独立 `notemeld-plugins` 的 `official-link-note` release；`backend.spec` 在 `NOTEMELD_PLUGINS_DIR`、根目录 sibling 和 workspace `packages/` 均找不到时会在构建阶段 fail-closed，不能生成一个直到 sidecar startup 才因缺少 fixture 退出的坏制品。
- Release workflow 通过仓库变量 `NOTEMELD_PLUGINS_ARCHIVE_URL` 与 `NOTEMELD_PLUGINS_ARCHIVE_SHA256` 下载并校验该独立仓库归档，再注入 `NOTEMELD_PLUGINS_DIR`；两个变量缺失、哈希错误或归档没有 `plugins/official-link-note/release-fixture/official-link-note-1.0.0.zip` 时，桌面构建必须停止。
- Intel macOS release 不得设置 `NOTEMELD_SKIP_PORTABILITY_CHECK=1`；x86_64 ffmpeg/ffprobe 必须经过依赖扫描，发现 Homebrew 路径时应让构建失败，而不是把本机可运行误当成可移植制品。

更新时间：2026-09-12

## Application Host 越权或假运行

- 风险：应用 UI 直接调用旧产品 router/SQLite，应用 backend 自行监听公网端口，或 Host 仅把 Run 标记为 running 却绕过 manifest、workspace 和 capability 校验。
- 防线：应用必须声明 `notemeld.application.v1` manifest；桌面使用 Host 监督的私有 process-JSONL/RPC，Web 使用 Host gateway 的 managed-worker seam；所有调用重新检查 session、app/instance、平台、权限和 capability。
- 不允许：把宿主 session token 放入应用环境变量/UI；应用使用绝对系统路径或 `..`；Wiki 应用复制 graph/article 作为第二事实源；用旧 `/wiki` UI route 作为兼容入口。
- 当前边界：已实现内建包发现、候选审批后的应用包安装、桌面 Host 监督的私有 process-JSONL、Web 本地 managed-worker seam、Cloud worker、Wiki capability、设置 API、应用对 process-jsonl 插件的受监督 `plugin.invoke`，以及 iOS/Android/Harmony 的原生 LAN-first/E2EE Relay。Harmony 的 ArkTS/CryptoFramework transport 已通过 HAP 编译，但尚未在真实 Harmony 设备上完成端到端互操作验证；外部 Web worker 部署、Host-port 插件、完整 Agent/File/Artifact adapter 和 Agent 自动生成应用仍未实现，不得在发布说明中宣称已完成。
- 加载边界：应用中心只能读取 manifest catalog；不得在应用列表 import 全部应用组件或启动所有 backend。只有用户点击应用后，Host 才能动态加载对应 bundle 并创建 instance/run。

## Application workspace 配置泄露或跨实例访问

- 风险：默认目录设置错误导致应用实例互相读写，或把宿主绝对路径暴露给应用协议。
- 防线：Settings 只配置 Host 根目录；应用收到逻辑 `workspace://applications/{app_id}/instances/{instance_id}`，Host 在 resolve 后确认目标仍位于根目录，并为每个实例创建独立子目录。路径设置必须是绝对路径且禁止 `..`。
- 检查方式：运行 `backend/tests/test_applications.py` 的 workspace 隔离、非法路径和迁移 registry 测试；检查 `/api/applications/settings/workspace` 始终使用 response wrapper。

## Application v2 权限或异步 Job 越权

- 风险：把 manifest permission 当成已授权，或 async Job 绕过 run/app/instance 校验；外部文件 capability 也可能退化成任意绝对路径读取。
- 防线：调用前重新校验 run、应用启用状态、capability 声明和 `ApplicationPermission` effective grant；外部文件必须位于 Host 授权根目录，Job 只能通过持久化 `job_id` 和单调 sequence 查询。
- 不允许：默认授予 network/agent/plugin；应用自行提供外部路径；Job worker 复用失效的 SQLAlchemy session；因 transport 超时自动重放未知副作用。
- 检查方式：运行 `backend/tests/test_applications.py` 的权限、实例隔离、路径穿越和 async Job 测试；审查 `/applications/jobs/*` 是否只返回安全结果。

本文记录历史踩坑和回归防线。修 Bug、新需求或重构前必须确认不会重新引入这些问题。

## 官方链接插件回退能力丢失

- 风险：链接插件化后只保留少数平台或只迁移下载路径，导致字幕优先、转写、截图、多源总结、网页抓取、任务状态或网页降级静默丢失。
- 防线：`backend/tests/fixtures/n01-url-capability-baseline.json` 是平台硬基线，`backend/tests/fixtures/n04-url-capability-matrix.json` 必须逐行 before/after 相等；入口只能调用 `official-link-note:create`，插件只能通过 host port 访问应用能力。
- 不允许：在 router 中恢复按平台分支的第二实现；插件直接写 SQLite、Conversation 或 Agent Event；视频/音频/转写失败后返回伪成功 Note。

## Wiki 同步 materialize 卡死 UI

- 发生过的问题：Wiki 总结阶段出现长时间卡顿，任务卡在 `materialize`。
- 根因：笔记保存路径同步执行完整 Wiki materialize，且 `WikiPageMerger` 调用 LLM 合并页面时持有全局写锁；模型接口慢或超时会拖慢所有后续任务保存。
- 不允许重新引入的错误做法：在笔记任务保存路径中同步重建完整 Wiki；把慢 LLM 请求放进 `_WIKI_WRITE_LOCK`。
- 检查方式：`backend/tests/test_wiki_rebuild_service_contracts.py` 应覆盖 contribution 保存不 materialize；代码审查搜索 `WikiStore.persist(`、`rebuild_from_contributions(`、`WikiPageMerger().merge`。
- 修复经验：笔记任务只做单篇知识抽取和 contribution 保存；完整 Wiki rebuild 交给独立 `WikiRebuildService`；LLM merge 设置超时。

## Wiki rebuild 必须 latest-wins

- 发生过的问题：多个 Wiki 更新请求可能堆积，旧任务覆盖新任务或长时间占用资源。
- 根因：全局 Wiki 重建是跨任务共享资源，缺少 generation/cancel 语义会导致过期结果落盘。
- 不允许重新引入的错误做法：排队执行所有 rebuild；取消请求只改状态不停止当前重建；旧 generation 继续写 live Wiki。
- 检查方式：检查 `backend/app/services/wiki_rebuild_service.py` 中 `_generation`、`_current_cancel`、`cancel_check`；运行 `backend/tests/test_wiki_rebuild_service_contracts.py`。
- 修复经验：新 rebuild 请求递增 generation 并 set 当前 cancel event；materialize 中定期检查 cancel。

## 取消 rebuild 后清空 live Wiki

- 发生过的问题：rebuild 刚开始先清空 `sources/entities/concepts`，随后被新请求取消，前端短暂读到空 Wiki 或 404。
- 根因：删除 live 目录发生在 cancel check 或 staging 原子替换之前。
- 不允许重新引入的错误做法：在可取消流程中先删除 live 数据，再慢慢重建。
- 检查方式：审查 `WikiStore._materialize_from_packets()` 是否 reset 前检查 cancel；必要时补充 staging 目录原子替换测试。
- 修复经验：至少 reset 前检查 cancel；更稳妥是写 staging，确认未取消后再原子替换 live。

## Wiki 文件并发写 tmp 冲突

- 发生过的问题：并发写同一路径时固定 `.tmp` 文件互相覆盖，可能触发 `FileNotFoundError` 或写入旧内容。
- 根因：`_atomic_write_text()` 使用 `path.with_suffix(path.suffix + ".tmp")` 固定临时文件名；新增无锁 `persist_contribution()` 与 rebuild 可并发写。
- 不允许重新引入的错误做法：多个线程/worker 对同一路径使用同一个 tmp 文件；去掉写锁后不改 atomic write。
- 检查方式：搜索 `_atomic_write_text`；审查 `persist_contribution()`、`_write_status()`、task status 写入是否存在同路径并发。
- 修复经验：短写入可加互斥；更通用是唯一 tmp 文件名加 `replace()`，并避免旧 generation 覆盖新结果。

## 历史 running/materialize 状态误导 UI

- 发生过的问题：大量 Wiki 页面长期显示“正在提取中”。
- 根因：旧状态文件残留 `status=running, stage=materialize`；前端把非 success/failed/canceled/partial 状态映射为 pending 类展示。
- 不允许重新引入的错误做法：把历史残留状态当成真实后台任务；只改前端文案不清理状态语义。
- 检查方式：核对 `wiki_rebuild_job.json`、单篇 Wiki job 文件、`note_documents.wiki_status` 和前端状态映射。
- 修复经验：区分单篇 analysis 状态和全局 rebuild 状态；必要时提供脏状态清理或更准确文案。

## 桌面 sidecar 未 ready 时前端抢跑

- 发生过的问题：桌面启动期间前端业务请求早于 backend sidecar 就绪，导致错误弹窗或空状态。
- 根因：前端没有等待 Tauri runtime 注入和 `/sys_health` 成功。
- 不允许重新引入的错误做法：组件 mount 后无条件请求 workspace、models、conversations、tasks。
- 检查方式：运行 `frontend/tests/backendReadyGatesWorkspaceRequests.test.mjs`、`frontend/tests/useCheckBackendNonBlockingContracts.test.mjs`、`frontend/tests/backendInitStartupWindowContracts.test.mjs`。
- 修复经验：通过 BackendInitContext 和 ready gate 控制业务请求；首次启动窗口必须足够长。

## 桌面首次启动等待窗口过短

- 发生过的问题：PyInstaller、模型、SQLite 或 ffmpeg 初始化较慢时，用户看到启动失败。
- 根因：前端或桌面壳等待时间不足。
- 不允许重新引入的错误做法：为了“更快失败”把首次启动静默等待降到 60 秒以下。
- 检查方式：`frontend/tests/backendInitStartupWindowContracts.test.mjs`。
- 修复经验：保留足够长的 silent check，后续再显示可操作错误。

## MCP 路径穿越和 API Key 泄露

- 发生过的问题/风险：MCP `get_note` 如果直接拼路径会读取数据目录外文件；`list_models` 如果返回 Provider 原始对象会泄露 API Key。
- 根因：MCP 是 AI IDE 可调用入口，安全边界比普通 UI 更敏感。
- 不允许重新引入的错误做法：把文件路径作为可信输入；把 provider rows 原样返回；日志打印完整 headers/payload。
- 检查方式：`backend/tests/test_core_mcp_generation_tools.py`；搜索 `api_key`、`read_text`、`Path(` 在 MCP service 中的使用。
- 修复经验：按 taskId/title 映射读取，拒绝 `..` 和绝对路径；MCP 模型列表只返回必要字段。

## MCP 设置脱敏后编辑覆盖真实凭证

- 发生过的问题/风险：列表接口只移除 `auth`，却回显任意 header/env 原值；前端再把 `***` 或空 auth 通过整体 PUT 写回，导致凭证泄露或启用切换后认证失效。
- 根因：不同 MCP 配置接口各自实现脱敏，且后端没有区分“用户输入新值”和“脱敏占位符/字段省略”。
- 不允许重新引入的错误做法：只脱敏 Authorization 而信任其他 header/env；把 `***` 写入配置；省略 auth 时清空旧 token；把保存异常原文返回前端。
- 检查方式：`backend/tests/agent/test_mcp_config_api.py`、`test_mcp_client.py::SaveLoadRoundTripTest`；确认 list/enabled/upsert 三条响应都不含 secret，编辑和 enabled 切换后旧凭证仍在。
- 修复经验：所有响应复用单一 sanitizer；auth 完全移除，headers/env 的所有值统一占位；PUT 按 `model_fields_set` 和占位符合并旧值；配置文件用唯一 tmp + 原子替换，错误只暴露安全文案和类型。

## Agent 首轮无条件 Wiki 搜索和全工具 schema 膨胀

- 发生过的问题/风险：free-chat 默认 `mixed` 且前端固定 `use_wiki=true`，导致首次 LLM 调用前几乎每轮遍历 Wiki；同时 Agent 每轮平铺 workspace、memory 和全部 Skill schema。继续直接接入第三方 MCP 会叠加网络发现、提示词噪声和连接泄漏。
- 根因：把“允许使用 Wiki/工具”实现成“请求前立即检索/一次性注册全部 schema”，缺少能力目录和渐进披露层。
- 不允许重新引入的错误做法：Agent hooks 调 `_prepare_free_chat_context()` 时省略 `prefetch_wiki=False`；在 `run_free_chat*` 直接把真实 Skill/MCP 工具放入 `AgentState.tools`；L0/L1 输出 MCP URL/header/env/token；请求结束不关闭 MCP adapter。
- 检查方式：`backend/tests/agent/test_capability_catalog.py`、`backend/tests/agent/test_agent_service_p3_integration.py`；首轮工具名必须恰为 `capability_discover/capability_describe/capability_invoke`，L0 不超过 1200 字符，MCP L0/L1 discovery 次数为 0。
- 修复经验：用请求级 `CapabilityRegistry` 统一 Wiki、builtin、memory、workspace、Skill、MCP；L0 只读 graph/config 元数据，L1 发现、L2 描述、L3 执行；`use_wiki=false` 双重门禁；non-stream/stream 都在 `finally` 关闭 registry。

## 把“读过”误判成“学会”或丢失学习状态

- 发生过的问题/风险：AI 展示一段解释后直接把节点标为 mastered；即时问答通过后不安排延迟复测；画布只存在前端内存，刷新或重启后作答、当前节点和复习队列消失。
- 根因：把内容消费事件和掌握证据混为一个布尔字段，或只持久化静态图而没有 session/evidence/review 状态机。
- 不允许重新引入的错误做法：前端直接写 `mastered`；`start_unit` 推进到 provisional/mastered；接受空答案、缺 rubric 字段、越界分数或低分 `passed=true`；复用固定 canvas `.tmp`；只锁 `save()` 而在锁外 `load→mutate`；只写消息 meta 不写完整 canvas artifact。
- 检查方式：运行 `backend/tests/learning/test_learning_session_service.py`、`test_learning_canvas_store.py`、`test_learning_api.py::test_parallel_evidence_submissions_do_not_overwrite_each_other`、`frontend/tests/learningCanvasContracts.test.mjs`；确认 48 小时 review 门禁、并发证据不丢失和刷新恢复。
- 修复经验：展示只记 `exposed`；后端验证 learner answer + rubric，recall/apply 后只到 `provisional`，到期 review 才可 `mastered`；所有 canvas 读改写必须经 store 事务锁并原子写入会话 workspace，消息只存索引。

## pytest 收集期 stub 污染全局模块表

- 发生过的问题：测试文件用 `sys.modules.setdefault("app.services.web_note", stub)` 隔离重量依赖后不恢复，导致同一进程后续真实契约测试从 stub 导入符号并在收集阶段失败；单文件运行却全部通过。
- 根因：模块级 stub 生命周期跨越了测试文件边界，测试结果依赖 pytest 收集顺序。
- 不允许重新引入的错误做法：在模块顶层永久写 `sys.modules`；以“两个测试单独都绿”替代全量单进程验证。
- 检查方式：`PYTHONPATH=backend python3 -m pytest backend/tests -q` 必须作为最终门禁；检查 stub 导入后是否立即恢复原模块表。
- 修复经验：优先使用作用域内 patch；确需收集期 stub 时，在目标 router 导入完成后只删除自己注册的同一 stub 对象。

## Markdown 上传 MIME 兼容被删

- 发生过的问题：浏览器会把 `.md` 上传识别为 `application/octet-stream` 或 `binary/octet-stream`，严格 MIME 会误拒。
- 根因：只按 MIME 白名单判断，不结合扩展名和内容解析。
- 不允许重新引入的错误做法：删除 Markdown octet-stream 兼容；只看 MIME 或只看扩展名。
- 检查方式：`backend/tests/test_core_upload_contracts.py`。
- 修复经验：扩展名、MIME、大小和内容签名/解析共同判断。

## DMG 发布只做本地 hdiutil verify

- 发生过的问题/风险：本地可挂载不代表用户机器可安装、可通过 Gatekeeper、可更新。
- 根因：发布校验不完整，缺少 Developer ID、公证、staple、codesign、双架构和公网回验。
- 不允许重新引入的错误做法：正式发布只跑 `hdiutil verify`；只构建 Apple Silicon；使用 Homebrew 动态库 ffmpeg。
- 检查方式：`frontend/tests/dmgPackagingContracts.test.mjs`，`.trae/skills/notemeld-dmg-packaging/`，`packaging/scripts/build-backend-macos.sh`。
- 修复经验：正式发布使用 `--release --upload --public-verify`，并强制双架构、公证、Gatekeeper、SHA256 公网校验。

## 桌面更新入口残留坏版本

- 发生过的问题/风险：云端 `latest.json` 继续指向有问题的 `0.1.0`，导致本地 `0.0.3` 客户端提示升级到坏版本；release 下载页或根站首页 `https://notemeld.wiki/` 也可能保留旧 DMG 链接。
- 根因：DMG 发布目录、Tauri updater manifest、release 下载页和根站首页是不同产物，清理或发布 DMG 时未同步清理 `latest.json`、`*.app.tar.gz`、签名文件和所有公开下载入口。
- 不允许重新引入的错误做法：只删除或上传 DMG，不检查 `latest.json`；只更新 `/srv/filebox/releases/notemeld/stable/index.html`，漏掉 `/var/www/notemeld.wiki/index.html`；让公开下载页继续引用已废弃版本；发布请求不确认版本策略。
- 检查方式：发布或下架后必须 `curl` 校验 `latest.json`、废弃版本 DMG URL、release 下载页 `/releases/notemeld/stable/index.html`、根站首页 `https://notemeld.wiki/` 中的版本号和链接。
- 修复经验：用户说“打包并部署到云端”时先确认版本策略，默认建议当前版本递增一个 patch 小版本；如果需要 major/minor/beta/非正式版，必须先确认。坏版本下架时删除 updater manifest、updater 压缩包、签名文件、坏版本 DMG，并同步 release 下载页和根站首页。

## 迁移和导入绕过索引重建

- 发生过的问题/风险：导入数据后笔记存在但检索/Wiki/索引不可用。
- 根因：迁移导入只复制文件，不触发 reindex/rebuild。
- 不允许重新引入的错误做法：导入 zip 后直接返回成功，不创建 job 或不重建索引。
- 检查方式：`backend/tests/test_core_migration_contracts.py`、`backend/tests/test_core_migration_api_contracts.py`、迁移路由 `/api/migration/reindex`。
- 修复经验：迁移使用 job store，导入后默认重建索引，并保留下载/查询 job 能力。

## 任务状态和会话消息不同步

- 发生过的问题/风险：状态文件成功但会话不显示结果，或会话进度残留旧状态。
- 根因：只写 `note_results` 文件，没有同步 `conversation_messages` 和 `note_documents`。
- 不允许重新引入的错误做法：绕过 `emit_note_progress()`、`emit_note_result()`、`register_task_conversation()` 创建任务。
- 检查方式：`backend/tests/test_core_task_status_contracts.py`、`backend/tests/test_core_note_task_status_api.py`。
- 修复经验：任务创建时绑定 conversation，状态更新走统一 writer，成功时同步 note document。

## 仅凭 role=user 信任历史 context refs

- 发生过的问题/风险：assistant row 可先保存伪造白板 `snapshot/source_ids` 再改成 user；第一轮角色门禁修复后，漏洞产生的历史 tainted user row 仍能在相同 locator/revision PATCH 时被当成可信发送时快照。
- 根因：`role` 和 `meta_json` 都是客户端可影响的业务数据，不能证明该 row 曾经过服务端 authority resolver；只检查 stored/resulting role 会把历史污染状态永久升级成可信。
- 不允许重新引入的错误做法：仅凭 `role=user` 复用；把可伪造 marker 放在 `meta_json`；迁移或 legacy merge 时把历史 row 默认标可信；把内部 provenance 暴露为 POST/PATCH 请求字段。
- 检查方式：`backend/tests/test_conversation_context_refs.py` 的 tainted-user/canonical-reuse/assistant-transition 回归，以及 `backend/tests/test_core_conversation_contracts.py` 的幂等补列、legacy 默认 0 和 store 持久化测试。
- 修复经验：使用 `conversation_messages.context_refs_authority_version` 作为服务端持久、客户端不可写的 provenance。只有当前 resolver 写入的版本可复用；历史/legacy 默认 0 并在下一次引用 PATCH 时重新解析。

## 学习入口依赖模型自行选工具

- 发生过的问题：用户在普通聊天里说“我想学习某主题”，界面只返回一段泛化建议，没有学习画布；LearningCanvas 已存在却无法被稳定体验。
- 根因：产品显式操作被错误地依赖于 Agent 的能力发现与工具选择；同时完整学习卡内嵌在对话消息，没有形成稳定的右侧学习工作区。
- 不允许重新引入的错误做法：把“学习”按钮实现为换一条 prompt；让输入内容自动覆盖用户选择的学习模式；以 `AGENT_CHAT_ENABLED` 作为显式学习入口的开关；在会话消息中保存完整 canvas；用短于串行 provider 总预算的前端超时；用组件局部锁处理跨路由长请求；canvas 已落盘后因消息 patch/reload/navigation 失败而标记为构建失败。
- 检查方式：`frontend/tests/learningCanvasContracts.test.mjs`；手动验证“学习 → 提交主题 → 对话摘要 + 右侧面板 → 刷新恢复”。
- 修复经验：显式学习 intent 直接调用 canvas API，持久会话保持 `chat` 兼容；消息只存 compact meta，HomePage 用最新 `canvas_id` 投影右侧面板。同步研究不设前端固定超时，互斥放入共享 store；canvas 返回成功是不可回滚的成功边界，旧请求只能在发起路径仍活跃时自动导航。

## 把搜索结果列表当成研究白板

- 发生过的问题：GitHub 搜索返回的无关仓库（例如 profile、政治归档或只因词项偶合命中的项目）直接成为首个“学习路径”；右侧一次展示 20 多个节点、完整路径、掌握度、复习和来源，用户无法形成判断。
- 根因：`LearningCanvasService` 把每个外部 `LearningSource` 直接转换成 `type=source` 节点，没有相关性安全门、概念编译或信息分层；UI 把领域模型的所有字段当作首屏内容。
- 不允许重新引入的错误做法：按 provider 排名直接建节点；用论文/仓库/网页标题充当概念；把完整 canvas 所有分区同时展开；让白板正文与 Note 各自演进形成双事实源。
- 检查方式：`backend/tests/learning/test_research_note_compiler.py`、`frontend/tests/learningCanvasContracts.test.mjs`；手动输入宽泛 Agent 主题并确认无关仓库不进入节点，右侧只显示图和当前焦点。
- Sigma 相机坐标不能直接使用 Graphology 布局坐标：聚焦节点应读取 `renderer.getNodeDisplayData()`，适配视图应使用 Camera `animatedReset()`，并在分栏尺寸变化后调用 `resize/refresh`。写死 `(0, 0, ratio=1)` 会把已有节点移出可视区域，造成“白板为空”的假象。无关系边的图应使用确定性紧凑布局，不运行 ForceAtlas2 把孤立节点推散。
- 修复经验：候选先做本地/外部相关性过滤，再由严格 schema compiler 生成 topic/concept/claim/evidence/conflict/case/question；Note 是正文权威，白板只做投影；首屏先概览，用户主动选择深入方向。

## Note 成功后被白板或消息失败误判为研究失败

- 发生过的问题/风险：研究 Note 已写入 `note_documents`，后续 canvas 保存、摘要消息、reload 或 navigate 失败却向用户提示“研究生成失败”；用户重试后产生重复 Note。
- 根因：把 Note、投影、消息、Wiki 和导航当成一个可回滚事务，但它们跨 SQLite、文件、异步队列和前端路由，无法原子提交。
- 不允许重新引入的错误做法：NoteImportService 返回后仍用总 catch 标记创建失败；白板固定 tmp/消息异常向上抛导致重试；Wiki 失败删除 Note。
- 检查方式：`backend/tests/learning/test_learning_canvas_service.py::test_note_success_is_not_rolled_back_by_projection_or_message_failure`；前端仍以 create API 返回为成功边界。
- 修复经验：Note 保存成功即研究正文成功；投影/消息失败只返回 `projection_save_failed/guide_message_failed` 安全诊断，Wiki 状态独立，白板可由 Note 重建。

## Note operation 重放或共享 SQLite migration 相互覆盖

- 发生过的问题/风险：不确定副作用在进程重启后被自动执行两次；或 Note/plugin/candidate 各自升级时覆盖共享 schema version，导致其他表域误判版本。
- 根因：只在内存记录 request id，未持久化 payload hash/outcome；把 `PRAGMA user_version` 当作多个独立组件的公共 migration registry；把正文和 operation outcome 分成可观察的两个成功事务。
- 不允许重新引入的错误做法：same request 不比对 payload；恢复 `begun/checkpointed` 后直接重放；在 Note adapter 表保存第二份 title/content；修改 `PRAGMA user_version`；在 Note 提交事务内执行模型、插件、网络或投影。
- 检查方式：`backend/tests/agent_host/test_note_store_adapter.py`，使用真实临时 SQLite 覆盖 same/different payload、并发 expected version、重开 needs-attention、投影失败和多 registry 共存。
- 修复经验：短 `BEGIN IMMEDIATE` 原子提交 `note_documents` + version/provenance + operation outcome；未终结 operation 重开只标记 `needs_attention`；各域使用独立 forward-only registry，投影提交后 best-effort 执行。

## API response wrapper 被破坏

- 发生过的问题/风险：前端 Axios 封装按 `{code,msg,data}` 解包，后端局部返回裸对象会造成调用方类型错乱。
- 根因：新接口未遵循 `ResponseWrapper.success()`。
- 不允许重新引入的错误做法：在 `/api` 路由直接返回业务 dict，除非调用方明确按裸响应处理。
- 检查方式：新增接口时查 `frontend/src/services/` 调用方；运行 `pnpm test:contracts`。
- 修复经验：普通 API 统一返回 wrapper，MCP/文件下载/流式接口例外要在 API 文档中说明。

## 视频采集状态写入和抖音跳转解析

- 发生过的问题：抖音视频生成任务没有真实下载视频，先被 `*.status.status.tmp -> *.status.json` 并发写冲突打断，后续又把直链解析成 `/jingxuan`，导致 `aweme_id=''` 和 `aweme_detail:null`。
- 根因：collector 状态文件使用固定 tmp 文件名，多个采集线程并发读改写同一状态文件；抖音下载器先跟随跳转再解析 ID，抖音把请求导向精选页时覆盖了原始 `/video/{id}`。
- 不允许重新引入的错误做法：原子写使用固定 tmp 名；状态上报异常中断下载/转写/分帧主流程；对已有 `/video/{id}` 的直链先 follow redirect 再取 ID；`aweme_detail` 为空时继续下标访问。
- 检查方式：`backend/tests/test_core_collector_status_contracts.py`、`backend/tests/test_multisource_video_collector_contracts.py`、`backend/tests/test_douyin_downloader_contracts.py`。
- 修复经验：并发状态更新必须用锁保护读改写并使用唯一 tmp；状态上报失败只能记 warning；抖音直链先从原始 URL 提取 ID，只有短链才跟跳转；空 ID/空详情返回明确错误；视频下载器需要兼容 `TranscriptCollector` 协议参数，尤其是 `skip_download`；抖音详情可能缺少 `music`，应 fallback 到 `video.play_addr/download_addr`；抖音 `uri` 可能只是媒体标识不是可请求 URL，下载地址只能使用 `http/https` 或协议相对 URL，优先读取 `url_list/url`；所有媒体下载请求必须设置超时。

## notemeld-ai 迁移期误删 GPTFactory 或误迁移 list_models

- 发生过的问题/风险：迁移到 notemeld-ai 抽象层时，过早删除 `GPTFactory`/`UniversalGPT` 会丢失回滚路径；把 `services/model.py` 的 `list_models` 也迁到 `NotemeldGPT` 会破坏非 chat-completion 路径（notemeld-ai `Models` 没有 list models 能力）。
- 根因：迁移分两类路径——chat-completion 走 `NotemeldGPT.create_chat_completion`（override 后走 notemeld-ai），list_models 走 `gpt.client.models.list()`（同步 OpenAI client，notemeld-ai 无对应能力）。
- 不允许重新引入的错误做法：在过渡期删除 `GPTFactory`/`UniversalGPT`；把 `model.py` 的 `list_models` 改成 `NotemeldGPT`；移除 `GPTFactory.from_config` 的 `DeprecationWarning` 之前先删工厂；新 chat-completion 调用点继续用 `GPTFactory`。
- 检查方式：`backend/tests/ai/test_provider_compat.py`（usage 双写对齐）、`test_note_generator_migration.py`、`test_t11_migration.py`（迁移点 + GPTFactory 回滚 import 保留断言）；搜索 `GPTFactory().from_config` 确认仅剩 `model.py` 的 list_models 路径。
- 修复经验：`GPTFactory.from_config` 加 `DeprecationWarning`，至少保留 1 个 Beta 版本；`model.py` 的 `list_models` 刻意不迁移；新 chat-completion 调用点一律用 `NotemeldGPT.from_config`。

## 运行数据路径分裂

- 发生过的问题：源码启动后根目录出现 `note_results`、`static` 等目录，下载器和临时文件也可能落到工作目录或系统临时目录，用户无法判断哪份数据是事实源。
- 根因：`.env` 相对路径、子目录级环境变量、旧启动脚本迁移复制和下载器 `DATA_DIR` 回退同时存在。
- 不允许重新引入的错误做法：恢复 `NOTE_OUTPUT_DIR`、`VECTOR_DB_DIR`、`STATIC_DIR`、`OUT_DIR`、`UPLOAD_DIR`、`DATA_DIR` 等子目录覆盖；启动时扫描并复制根目录旧数据；把 NoteMeld 运行时临时文件写到工作目录或系统临时目录。
- 检查方式：检查 `storage_paths.py` 的所有子路径是否从 `data_root()` 派生；运行启动契约并确认桌面数据只在 `desktop/data/`、日志只在 `desktop/logs/`。
- 修复经验：数据根只允许单一运行模式注入口，业务子目录固定；应用临时文件写入 `desktop/data/tmp`，日志根固定为 `desktop/logs`，云端使用独立 `cloud/data` 或部署持久卷。

## Agent 变更流程缺失

- 发生过的问题：新需求容易直接写 PRD 或方案，忽略当前系统事实，重复踩 Wiki、桌面、MCP、数据路径等坑。
- 根因：缺少强制的系统文档入口和增量变更模板。
- 不允许重新引入的错误做法：不读代码和测试就写实现方案；孤立 PRD 不分析现状冲突。
- 检查方式：新需求必须先创建基于 `docs/system/change-spec-template.md` 的 Change Spec。
- 修复经验：把当前系统事实、产品规则、数据模型、API、坑点和 Agent 工作流固化在 `docs/system/` 与 `AGENTS.md`。

## 风格 prompt 与持久格式不一致导致整篇笔记成为代码块

- 发生过的问题：`knowledge_card` 声明 Markdown 输出，但 prompt 强制模型只返回 HTML；模型实际返回 Markdown 并套上 `html` fence，后端仅按真实 HTML 标签转换，最终 ReactMarkdown 正确地把整篇渲染为灰色代码块。
- 根因：生成策略、格式检测和持久化使用三套隐含判断；把 fence 的语言标签误当格式，又缺少保存前统一归一化。
- 不允许重新引入的错误做法：用前端 CSS 隐藏 code block；Markdown-only prompt 继续要求 HTML/CSS/DOM；无条件剥离所有代码围栏。
- 检查方式：`backend/tests/test_note_output_normalizer.py`、`test_web_note_contracts.py`；测试全文错误 fence、来源引用前缀、真实 HTML 转换和正文内部代码块。
- 修复经验：`output_formats` 必须同时约束 prompt 和保存；只在整个文档是一个 fence 时安全剥离，视频/网页入口共用同一 normalizer。

## 推理模型消耗 completion token 但 final content 为空

- 发生过的问题：DeepSeek 等推理模型的每个 Wiki chunk 都记录了接近上限的 completion tokens，但 `message.content` 为空，系统统一报 `Wiki fallback analysis returned empty content`，无法判断截断还是响应适配丢字段。
- 根因：OpenAI 兼容 Provider 丢弃 `reasoning_content` 和真实 `finish_reason`，兼容 adapter 又把结束原因写死为 `stop`；Wiki 解析只读取 final content。
- 不允许重新引入的错误做法：以 usage success 证明已有 final answer；把任意 reasoning prose 当作 JSON；把 chain-of-thought 写入日志/UI；所有空响应统一归为网络或 empty content。
- 检查方式：`backend/tests/ai/test_provider.py`、`test_note_generator_migration.py`、`test_knowledge_extractor_response_contracts.py`；覆盖合法 JSON 恢复、length 截断、仅 reasoning、真正空响应。
- 修复经验：适配层要保留字段语义；业务层优先 final content，只恢复完整可验证 JSON，并按 finish reason 分类。输出预算与 schema 数量上限必须共同约束。

## 只按请求字节分块或把完整聊天历史直接发给 4K 模型

- 发生过的问题/风险：请求 JSON 明显低于 45MB，却因估算输入达到 6492 tokens 而超过 4096 模型上下文；聊天和 Agent 历史也可能在 Provider 端才失败。
- 根因：`RequestChunker` 只检查 HTTP 字节上限，`Models.stream/complete` 未把保存的模型窗口作为 Provider 前硬边界。
- 不允许重新引入的错误做法：只改模型设置 UI 而不让聊天、Agent 和笔记运行时消费保存值；用官网/模型文件的理论窗口覆盖用户确认的端点实际值；只按字节分块；用字符数冒充 token；在 chat_service/Agent loop 原地删除持久消息；拆散 assistant tool calls 与对应 tool messages；静默截断最新 user；使用能力探测缓存覆盖保存窗口。
- 检查方式：运行 `backend/tests/test_token_budget.py`、`backend/tests/ai/test_models.py`、`backend/tests/ai/test_chat_service_migration.py`、`backend/tests/ai/test_note_generator_migration.py`；确认 4096 的 literal 预算为 output 1024、safety 410、input 2662，并验证 token/byte 任一超限都会分块。
- 修复经验：统一使用保守的 `ceil(UTF-8 bytes / 3)` 加每消息 overhead；图片按每张 1200 token reserve；Provider 前裁剪副本，system/最新 user 必留，工具调用与结果成组；笔记分块同时执行 token 和 byte 两道门槛。

## legacy 合并重新导入已清空的模型配置

- 发生过的问题/风险：初始化先升级 schema 并清空旧 `models` / `model_capabilities`，随后 legacy SQLite merge 又导入模型行，三列旧表依靠 server defaults 被伪装成 `4096 / false / true`。
- 根因：通用 legacy table 白名单把 `models` 当成可兼容数据，忽略了模型运行字段必须由用户针对当前端点重新确认的产品边界。
- 不允许重新引入的错误做法：为 legacy `models` 补默认值后导入；因 legacy 表已含完整三字段就例外保留；为了跳过模型而一并丢弃 Provider、Note、Conversation 或 Usage。
- 检查方式：`backend/tests/test_model_runtime_schema.py`的 merge 和真实 `init_db()` 回归；确认 Provider/Note 可导入，`migrated_counts["models"] == 0` 且当前 `models` 保持空。
- 修复经验：legacy merge 表白名单彻底排除 `models`，保留摘要 key 以维持观测契约；用户重新添加后才产生完整权威运行配置。

## 模型 defaults pending 期间快速保存 fallback

- 发生过的问题/风险：用户选择模型后 defaults 请求尚未返回就点击“添加模型”，弹窗把初始 fallback 当作用户确认值持久化。
- 根因：只有 request version 与 dirty 保护迟到响应，没有把“当前 defaults 请求尚未 settle”纳入保存可用性和 handler 防御。
- 不允许重新引入的错误做法：只禁用按钮而不防御 handler；旧请求 `finally` 结束新请求的 loading；关闭后允许迟到响应改写状态；defaults 失败后永久禁止保存。
- 检查方式：`frontend/tests/modelRuntimeConfigContracts.test.mjs`；确认 loading 同步 ref + state、按钮/handler 双门禁、current-version-only finally 和关闭失效化。
- 修复经验：请求启动时同步锁定保存；仅当前 version 在 `finally` 解锁；失败后保留 fallback 可编辑并允许用户主动确认。

## 笔记 map 重复注入辅助上下文、非视觉模型仍先走视觉

- 发生过的问题/风险：多源 collector 先把 frame/search 拼入 `extras`，统一上下文又再次渲染，导致每个 map 块重复携带整份辅助内容；不支持视觉的模型仍可能调用 analyzer、生成 grid payload；空 OCR 占位也持续膨胀 prompt。
- 根因：用户原始要求和 collector 结果共用一个字符串通道，采集入口没有使用已保存的 `supports_vision` 做明确分支，OCR formatter 把空结果变成了有效文本。
- 不允许重新引入的错误做法：把 collector content 写回原始 `extras`；map 阶段注入 final-stage search/vision；`supports_vision=false` 时先试视觉再 OCR；对空 OCR 写“未识别到文本”；调用旧 extractor fallback 暗中生成 grid；即使 grid 为空仍调用 base64 encoder；把 vision→OCR 临时 fallback 当成稳定 vision cache。
- 检查方式：`backend/tests/test_multisource_summary_contracts.py`、`backend/tests/test_multisource_video_collector_contracts.py`；断言 map/final payload、vision analyzer/OCR 调用次数、真实 `VideoReaderFrameExtractor` 的 grid/group/concat/base64 调用次数、旧 extractor 未调用、空 OCR 不产生 vision extra，以及 analyzer 临时失败后下次仍会重试视觉。
- 修复经验：原始 `extras` 单独保留，collector 结果经 `SummaryInput.user_options` 进入 final weighted pack；`allow_vision=false` 通过显式 `include_grid_images=false` 契约直接逐帧 OCR 并使用独立 `_frames_ocr` 缓存，空文本跳过；vision fallback 不写稳定 vision cache。

## Provider 实际上下文小于保存值时无限重试或破坏缓存

- 发生过的问题/风险：本地模型报 `request (6492 tokens) exceeds ... (4096 tokens)`、`exceed_context_size_error` 或 `n_prompt_tokens/n_ctx` 后直接失败，或通用网络 retry 重发同一 payload；失败清理 checkpoint 会浪费已完成 map 和采集结果。
- 根因：只在请求前按保存窗口估算，没有统一识别 Provider 的上下文错误形态，也没有限制“缩小预算重分块”的次数和 checkpoint 命名边界。
- 不允许重新引入的错误做法：把上下文错误当网络抖动原样重发；因 payload 同时含 500/timeout/service unavailable 而先走通用重试；仅凭孤立或不可解析的 `n_ctx/n_prompt_tokens` 判超限；循环缩小预算；对用户或日志泄漏完整 Provider payload；重试前删除 transcript/frame/search cache 或原 checkpoint。
- 检查方式：`backend/tests/ai/test_note_generator_migration.py`、`backend/tests/ai/test_provider.py` 的 6492/4096、结构化 code、正负错误变体、混合 500/timeout 调用次数、70% 预算、二次安全错误、日志脱敏和 checkpoint 保留测试。
- 修复经验：统一 `is_context_limit_error()` 并优先解析结构化 code；成对数字必须满足 `n_prompt_tokens > n_ctx`。上下文错误在通用 retry 前排除，只用原输入预算的 70% 重分块一次，并给重试使用独立 checkpoint key；二次失败转换为专用安全 `ContextLimitExceededError`，日志也只记录安全归一化错误，已有缓存和 checkpoint 原样保留。
## Agent Host 与 SDK 版本漂移

- 运行时必须同时校验 SDK version 与 Agent Event schema version；不兼容时 fail-closed，错误不得包含 Provider key 或完整 payload。
- 当前已发布 artifact 的真实契约是 SDK `0.1.0`、schema `1`、ABI `1`；独立 SDK 的 wheel/header/build scripts/verifier 均以 `abi-v1.json` 为准。`abi-v2.json` 是未发布的未来契约，不能用 Python 包级临时 `ABI_VERSION=2` 覆盖 artifact 事实。
- UI/CLI 不得直接写 `conversation_messages` 或 Agent Event；应通过 Host，避免重复消息和事件序列断裂。
- 不允许通过 `NOTEMELD_AGENT_MODE=python|python-oracle|legacy` 回滚；这些模式必须 fail-closed。模型调用失败也不能静默切回旧 Agent，避免同一 Turn 执行两次。
- 启动入口必须复用 Host loader 校验外部 wheel 的 version metadata、ABI contract、binding signatures、native exports 和 native SDK/schema version；“Python 包能 import”不等于 native artifact 兼容。缺失、架构错误或版本错误都应在启动前阻断，诊断不得回显本地 artifact 路径。
- PyInstaller 会把 macOS native SDK dylib 的 install name 从构建目录改写为 `@rpath`，所以 frozen sidecar 中的字节 hash 与 standalone wheel 的 native hash 必然不同；loader 只能在 `sys.frozen` 路径使用单独锁定的 packaged digest，普通 wheel 仍必须校验原始 native digest，不能通过放宽校验解决启动失败。
- 检查方式：`backend/tests/agent_host/` 的 loader、artifact、CLI、driver、Turn、broker、preference 与 API 契约测试。

## Agent Session 并发门禁只靠进程内状态或 SELECT FOR UPDATE

- 发生过的问题/风险：入口各自维护活动 Turn map 会形成第二套状态；SQLite 又会忽略 `SELECT FOR UPDATE`，两个并发请求可能同时观察到“无活动 Turn”。SQLAlchemy 2.x 在查询 autobegin 后再次 `db.begin()` 还会直接拒绝创建 Turn。
- 不允许重新引入的错误做法：UI/CLI 直接写 Agent 表；Router 绕过 Host entry；用进程内 dict 作为 Session 活动状态事实源；在 SQLite 只做先查后插；并发门禁失败后回退旧 Python Agent。
- 检查方式：`backend/tests/agent_host/test_agent_store.py` 覆盖同 Session 并发一成一拒、不同 Session 均可创建、existing Conversation 不新增第二状态；`test_agent_route_cutover.py` 覆盖 Web/Tauri/CLI 的 `/api/agent/v1` 单一路径。
- 修复经验：入口只提交 Host lifecycle command；Agent Store 在短 SQLite `BEGIN IMMEDIATE` 写事务内完成 Conversation/幂等/活动检查和插入，Turn 创建后模型执行不持有该锁。

## Agent approval 只返回成功但没有恢复 native Turn

- 发生过的问题/风险：HTTP approval 接口存在，但 ABI 固定返回 unsupported；或 Host 只写 `running`/成功响应，原 Rust Turn 仍永久等待，UI/CLI 看似批准却不能继续。
- 不允许重新引入的错误做法：在 NoteMeld Host/UI/CLI 重写 Agent loop；用 HTTP ACK 冒充 SDK 已恢复；为 approval 新建第二套 Session/Message 状态；把 30 秒 wait timeout 当成 Turn 失败；重复 resolve 静默成功。
- 检查方式：独立 SDK 的 `agent-core/tests/approval_resume.rs` 与 `agent-ffi/tests/abi_contract.rs`，以及 `backend/tests/agent_host/` 的 Host/Router/store/CLI/executor approval 回归。
- 修复经验：SDK canonical loop 创建并等待 approval，FFI runtime 持有同一 manager 并原子唤醒；NoteMeld 只把 `approval.required/resolved` 与 `waiting_approval/running` 原子投影到 Conversation→Turn→Event 数据链。unknown、duplicate、terminal 和 invalid decision 使用稳定错误，长暂停通过有界 wait 轮询保持活动。

## K0-K3 检索不能重新退回文件遍历

- 发生过的问题/风险：如果在 10 万篇文章规模继续逐个读取 contribution/Markdown 或为每篇文章创建 Chroma collection，画像筛选和跨文章检索会随文章数线性放大，并且结果无法统一返回 `article_id`。
- 不允许重新引入的错误做法：K2 在线逐文件扫描；K1/K2/K3 依赖旧 per-task collection；把 K3 canonical 节点按文章复制；用 `article_ids=[]` 当作全库；要求先调 K3 才能调 K2/K1；把 K0-K3 业务模型写入 SDK。
- 检查方式：`backend/tests/knowledge/test_knowledge_retrieval.py` 的文章过滤、显式空集合、K3 provenance、四工具独立调用；检查 FTS/向量 collection 数量为固定版本集合。
- 修复经验：SQLite FTS5 负责共享词法索引，版本化共享 Chroma 负责向量索引，SQLite relation/occurrence 负责图 provenance；查询前校验文章范围，工具由 NoteMeld Provider 独立注册，Note 保存成功边界不受索引失败影响。

## Agent ModelDriver 每轮丢失请求上下文

- 发生过的问题/风险：native Turn submit 时虽然含 Conversation history、模型和工具，但 ABI v1 的 `model.stream.payload` 只带该轮 messages；Host 直接透传后，Provider 请求没有 context refs、工具描述或安全模型配置，structured assistant/tool message 也可能被当成普通 JSON 文本，工具第二轮关系断裂。
- 不允许重新引入的错误做法：每轮传空 history；用固定消息条数代替统一模型窗口预算；忽略 system/current user；丢弃 assistant tool calls 或 tool result call id；把 Provider 原始异常用 `logger.exception` 写入日志；在 NoteMeld 重做 Agent loop。
- 检查方式：`backend/tests/agent_host/test_model_driver.py` 与 `test_native_executor.py`；断言两轮 model request 都保留 system/history/current user/tool group，并重复携带 context refs、工具描述和无凭证 model descriptor，同时覆盖 delta、usage、tool call 和安全错误分类。
- 修复经验：Rust SDK canonical messages 始终是每轮权威；Host 只附着 Turn 级不可变上下文并做 Provider envelope 转换。完整历史交给 SDK，Provider 前裁剪继续复用 `Models.stream()`，空 messages fail-closed。
- Android LOCAL 例外：当前锁定 AAR 的 FFI host 没有暴露 durable `AgentStore`/未完成 Turn 恢复 API，`EmbeddedLocalAgent` 因此在新 Turn submit 时把 `MobileLocalStore` 的最多 200 条投影历史放入 `request.extra.history`，并把 pending Turn 的未知结果投影为 `turn.interrupted:needs_attention`；不得把这项跨进程上下文恢复写成 native Turn 中断后的自动续跑。

## 产品工具错误被当成 driver 失败而中断 SDK loop

- 发生过的问题/风险：NoteMeld ToolDriver 对未知工具、参数或产品异常直接抛错，Host 再返回 driver-level `ok:false`。Rust SDK 会把它视为整个 tool round 失败，Turn 在 ToolResult 写回前终止，模型没有机会读取分类错误并继续回答；如果 NoteMeld 为补偿而自己重试或调用下一轮模型，又会形成第二套工具循环。
- 不允许重新引入的错误做法：产品业务失败直接返回 ABI driver error；在 UI/CLI 执行工具；Host 自己循环调用模型；把工具参数、Provider payload、凭证或异常原文写入 ToolResult/日志；用进程内 Session map 关联并发结果。
- 检查方式：`backend/tests/agent_host/test_tool_driver.py` 覆盖五类稳定错误，`test_tool_scheduler_integration.py` 使用真实 standalone SDK artifact 断言 tool call → Capability Registry → ToolResult → 第二轮模型，并发两个 Session 的 call id/result 不串。
- 修复经验：NoteMeld 只实现薄 ToolDriver 并只调用 Capability Registry。产品成功和可恢复失败都转换为 `{call_id, output}` ToolResult；失败 output 使用稳定脱敏 code。只有 callback/ABI 自身格式损坏才返回 driver-level error，调度、并发、取消和下一轮模型始终归 SDK 所有。

## Agent SSE 尾帧或跨 Turn 事件污染前端

- 风险：SSE 在 UTF-8 多字节字符中间断块、连接结束时留下未分隔尾帧，或错误事件混入当前流，可能造成回复截断、乱码、重复拼接或跨会话串话。
- 根因：reader 只解析出现 `\\n\\n` 的帧；decoder 未在结束时 flush；前端 reducer 只按“最后一条 assistant 消息”归并 delta，未校验 `turn_id`、sequence 和 streaming 状态。
- 不允许重新引入的错误做法：把非法/负 sequence 当作有效事件；接受其他 Turn 的事件；把已完成 assistant 消息继续追加；只在正常网络关闭前提下测试 SSE。
- 检查方式：覆盖 UTF-8 chunk 边界、最后无空行尾帧、重复/乱序 sequence、错误 `turn_id`、空 payload、重复 `message.completed` 和终态后 delta；运行 `cd frontend && pnpm test:contracts`。
- 修复经验：SSE 使用流式 `TextDecoder` 并在 EOF flush，解析尾帧；客户端拒绝不属于当前 Turn 或没有合法 sequence 的事件；reducer 只追加正在流式的 assistant 消息，终态后不再修改消息。

## Android 调试包冷启动被误记为发布候选通过

- 发生过的问题/风险：实体机能安装和冷启动 debug APK，客户端聊天验证器又顺带输出运行态通过，最终可能把未签名、旧签名或与 RC 制品不一致的安装包绑定为 A-01。
- 不允许重新引入的错误做法：仅凭认 `versionName`、包名、PID 或无 crash；以 `assembleRelease` 的本地测试证书代替生产证书；只校验磁盘上的候选 APK，不检查设备实际安装字节；让 A-02/A-03/A-04/A-05 顺带宣称 A-01；A-01 通过后换装同版本/commit 的 debug APK继续跑其余门禁。
- 检查方式：`desktop/backend/tests/test_first_batch_client_verifier.py`；普通 `android-runtime` 只能输出 `android_runtime_smoke`，A-01 必须显式提供 signed RC APK、固定 signer SHA-256 和 `apksigner`，并从实体设备回拉唯一 APK 做签名与 SHA-256 字节一致性检查。A-02～A-06 必须读取绑定后的 A-01，并再次回拉当前 APK 核对同一 SHA-256。
- 修复经验：运行 smoke 与发布制品证据分离；A-01 独立绑定签名 RC，Agent 各模式只证明自己的纵向结果，但必须证明仍运行 A-01 的相同字节。split APK、模拟器、签名数量/指纹不符、设备回拉字节不符均 fail-closed。

## Android 把本机 Host 离线误当成整机断网，或重连时新建远程 session

- 发生过的问题/风险：只用本机 `127.0.0.1:8483` 投影刷新表示全部连接状态，会在本机 Host 不可达时误禁用仍可用的 Cloud；为修复这个问题而对所有非本机模式放行，又会导致 Wi-Fi/移动数据全部断开后仍可提交。远程消息每次新建 `device_remote` session 还会让“恢复后 cursor 连续”永远无法被同一客户端证明。
- 不允许重新引入的错误做法：用单一 `connection` 布尔量同时代表本机 Host 与设备网络；仅在请求失败后显示错误而不进入离线只读；重连时重置 session/sequence；用通用 Relay 双端测试替代 Android UI 的 cursor 证据；自动重放中断时状态未知的旧命令。
- 检查方式：`desktop/frontend/tests/mobilePlatformAdapterContracts.test.mjs`、`desktop/backend/tests/test_first_batch_client_verifier.py` 和 `verify_first_batch_clients.py android-recovery`；确认设备网络 callback、离线只读语义节点、按 Host 持久 session、Relay `next_sequence` UI、radio 恢复及 cursor 严格增加。
- 修复经验：本机可达性和系统网络可用性分层；Local 由 Host 状态控制，Cloud/Remote 由系统网络 callback 控制。网络恢复后只允许用户提交新命令，同一远程 session 从 Cloud 持久 cursor 继续，不自动重放未知旧副作用。
