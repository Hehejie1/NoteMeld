# NoteMeld Cloud / macOS x64 / Android Agent 上线需求与验收标准

日期：2026-09-13  
作者 / Agent：Codex（依据用户确认整理）  
状态：Planned  
关联对话 / 任务：2026-09-13 上线目标梳理；本轮只定义需求与验收，不进入实现  
关联系统文档：[当前架构](../system/current-architecture.md)、[产品规则](../system/product-rules.md)、[数据模型](../system/data-model.md)、[API 清单](../system/api-inventory.md)、[已知坑点](../system/known-pitfalls.md)、[`/docs/new-product` 页面地图](../new-product/PAGE-MAP.md)、[设计系统规范](../new-product/design.md)、[组件库说明](../new-product/design-system/README.md)、[界面映射现状](2026-09-08-notemeld-new-product-interface-matrix-v1.md)

## 1. 原始需求

用户要求先梳理现有代码，把可上线目标写成需求和验收标准，不要求本轮直接实现或达成上线目标。

本批范围固定为：

1. Cloud。
2. macOS x64 本机端。
3. Android。

三端都必须能够独立运行 Agent runtime、同步 Cloud 配置，并支持端到端通信。验收不仅要求能够编译、安装、启动且无错误，还必须逐项覆盖功能、异常路径和 `/docs/new-product` 中对应页面及组件库。公共组件库需要按平台独立交付；桌面端与 Web 共用一套可单独构建、版本化和引用的组件包，Android 交付独立原生组件模块。

本文采用严格口径解释“各端独立运行 Agent runtime”：Cloud、macOS x64、Android 各自持有并执行 canonical Agent runtime；任一端的本地 Agent 成功不得依赖另一客户端、`adb reverse`、开发机 loopback 服务或静态假数据。

## 2. 背景和问题

- 当前用户：需要确定首批上线边界、安排后续开发和最终签字的产品负责人、研发和验收人员。
- 当前场景：仓库已存在 Cloud、桌面、Android、Agent Host/SDK 接口、设备配对、Relay、`/docs/new-product` 原型与分散的 UI primitives，但“已有代码”“原型已实现”和“可上线”尚未形成同一套可逐项签字的定义。
- 当前痛点：
  - 旧首批需求使用 Windows x64，与本次确认的 macOS x64 范围冲突。
  - Android 已切换为 APK 内 `:agent-runtime` + 锁定 SDK AAR；仍需真实模型和实体设备现场证据证明独立运行。
  - Cloud 配置同步已有模型下发和设备接口基础，但同步对象、权威源、冲突和敏感配置边界没有完整验收口径。
  - E2E 通信的配对、授权、LAN/Relay、断线恢复、撤销和审批需要作为一条真实纵向链路验收，不能只靠单元测试或局部接口通过。
  - `/docs/new-product` 是设计与页面合同，当前设计系统明确不是生产 npm 包；桌面/Web 仍需独立公共 UI 包，Android 已有独立 `:ui-core`，但仍需补齐完整页面状态和现场视觉证据。
- 为什么现在做：先冻结上线产品合同，才能据此拆 Plan/Spec、排开发顺序、建立测试台账，并避免用“能启动”代替“可上线”。

## 3. 目标结果

### 3.1 总体上线目标

同一候选版本中的 Cloud、macOS x64 和 Android 达到以下结果后，才可判定首批范围具备上线条件：

1. 三端各自独立完成真实 Agent 会话闭环：创建 session、提交 turn、接收事件、处理工具/审批、得到唯一终态、恢复历史。
2. 三端以 Cloud 为账号、设备、授权和共享配置的权威协调面，完成有版本、可恢复、可撤销的配置同步；端侧机密只进入安全存储。
3. Cloud Web、macOS x64 和 Android 可以在授权后完成端到端通信；Cloud Relay 看不到正文，LAN 不可用时可回退 Relay，网络恢复后不重复副作用。
4. 三端对应 `/docs/new-product` 页面与每个功能点具备真实数据、真实操作、完整状态和失败反馈，不以静态原型、disabled placeholder 或 mock 响应计为完成。
5. 桌面/Web 公共组件库作为独立包交付并被两个生产入口实际引用；Android 公共组件库作为独立原生模块交付并被 Android 页面实际引用；两者遵守同一语义 token、状态和可访问性合同。
6. 三端制品均可重复构建、安装、首次启动、升级启动和冷启动，无崩溃、白屏、阻塞性错误或未处理异常；制品与 Cloud 部署可追溯到同一兼容版本和协议基线。

### 3.2 上线判定

- `GO`：本文所有标为 P0 的验收项都有绑定候选版本的自动化或真实设备证据，结果全部为 `PASS`，且无未关闭的阻塞级安全/数据问题。
- `NO-GO`：任一 P0 项为 `FAIL`、`PARTIAL`、`BLOCKED`、无证据或证据来自 mock/debug 替代链路。
- “编译成功”“页面能打开”“接口返回 200”“原型 registry 标记 implemented”只能作为子证据，不能单独判定上线。

## 4. 非目标

- 不把 Windows x64、macOS arm64、iOS、HarmonyOS 或其他平台作为本批上线前置。
- 不在本文指定数据库字段、HTTP payload、FFI 函数名、包名或任务拆分；这些属于后续 Plan/Spec。
- 不在本轮实现代码、生成执行计划、承诺上线日期或执行发布。
- 不要求桌面/Web 与 Android 共享同一 UI 源码；共享的是语义 token、组件状态、交互和可访问性合同，各端使用适合平台的实现。
- 不把 `/docs/new-product` 原型本身直接发布为生产 UI，也不把 A04 参考 HTML 当成生产组件包。
- 不同步本机绝对路径、设备私钥、模型权重、运行缓存、原始日志或无必要的用户内容。
- 不要求 Cloud 解密、存储或检索设备间 E2E 消息正文。

## 5. 当前系统事实与差距

| 领域 | 已确认事实 | 与目标的差距 |
| --- | --- | --- |
| Agent 单一事实源 | 独立 Rust Agent SDK 是 canonical runtime；产品通过 Agent Host/绑定消费，产品不应复制第二套 loop。 | 需证明三端实际消费兼容的 canonical runtime，并分别完成真实模型纵向闭环。 |
| Cloud Agent | Cloud 已有 session/turn/event、真实 runner、模型与设备/Relay 基础。 | 需要 production 配置、真实 Provider、恢复/重试、审计和端到端证据。 |
| macOS x64 | Release workflow 已有 `x86_64-apple-darwin` 构建入口；桌面已有 Agent Host、UI 和 Tauri 壳；正式打包路径现要求 Developer ID identity、notary 凭据、notary submit、staple 和 Gatekeeper 检查，缺任一项即失败。 | 仍需要在 Intel 实机安装同一签名/公证制品，完成安装/升级、Keychain 身份、真实 Agent 与远程链路证据。 |
| Android Agent | Android 已有 Compose 页面、`MobileApi`、`CloudApi`、`AndroidRemoteRelay`，并通过独立 `:agent-runtime` 模块嵌入锁定的 canonical SDK AAR；LOCAL 模式不调用产品 loopback。 | 仍需真实模型、签名 RC、实体设备和跨端现场证据，不能用本地编译或 debug smoke 代替最终门禁。 |
| 配置同步 | Cloud 有模型、默认模型、设备、Grant、配对确认等接口；配对可一次性返回启用模型配置。 | 需要定义完整同步集合、版本、冲突、删除、离线和安全存储行为，并做三端实测。 |
| E2E 通信 | 已有 Ed25519/X25519/AES-GCM、LAN/Relay、opaque frame 和设备授权设计基础。 | 需要真实三端、双路径、重连、防重放、撤销、审批和 Cloud 明文审计证据。 |
| 桌面/Web UI | 已建立可独立发布的 `@notemeld/ui-web` workspace package（版本 `0.1.0`、显式 `workspace:0.1.0` 消费、独立 `build`/`lint`/`typecheck`/`test`/`test:a11y`/`test:visual` scripts、catalog 与 token CSS）；包已覆盖 ThemeProvider、Button/IconButton、Input/Textarea、Select、Checkbox/Switch、Tabs、Card、List/Table、Badge、Alert/Toast、Progress/Skeleton、Empty/Error/Offline/Loading、Dialog/Sheet/Drawer、Popover/Tooltip、Navigation/Sidebar/AppBar、ScrollArea、Resizable；桌面和 Cloud Web 已通过该包消费业务所需 primitives，Cloud 页面、Applications 页面及 CloudSessionList、CloudSessionPanel、CloudModelList、CloudWorkspaceBrowser、CloudDeviceList、CloudUserList 已实际消费共享状态 primitives。 | 仍需把状态 primitives 接入其余生产页面，并补齐全页面消费证据；package-local 门禁已通过，但不替代真实页面视觉/实体端验收。 |
| Android UI | Android 已使用独立 `:ui-core` Compose design-system，提供 `NoteMeldTheme`、semantic tokens、Loading/Error/Empty/Offline/Progress/Snackbar 状态、稳定 testTag/content description 和共享交互 primitives；模块 Compose androidTest 已覆盖 empty/offline/loading/error/button，移动 Surface 实际引用该模块。 | 仍需补齐完整 M01-M06 的截图、字体缩放、旋转、TalkBack、减少动画和实体设备证据。 |
| new-product | `PAGE-MAP.md`、`design.md`、A04 和 feature registry 定义了目标页面、功能、状态和设计语义。 | registry 的 implemented/partial 表示原型映射状态，不等同生产验收；所有在批页面必须绑定真实服务。 |

### 5.1 配置同步范围

首批 Cloud 权威配置集合固定为：

- 账号与 workspace 身份、成员角色和可用 workspace 元数据。
- Provider/模型的启用状态、endpoint、能力元数据、默认模型和用户可选模型集合。
- 通过配对授权下发的模型凭据；凭据只允许在受保护通道和一次性/可轮换流程中出现，端侧进入安全存储，UI、日志、事件、数据库投影不得回显明文。
- 用户偏好：主题、语言、通知、默认模型及 `/docs/new-product` 设置页已定义的跨设备偏好。
- 设备列表、设备状态、Grant、权限 scope、撤销状态和最近同步版本。
- Cloud session 与远程 session 的可见元数据和恢复 cursor；E2E 正文仍不进入 Cloud 配置存储。

明确不在同步集合中的内容：设备私钥、本机绝对路径、本地 workspace 文件、模型权重、本地缓存、未授权笔记正文、诊断原始日志。

### 5.2 同步规则

- Cloud 是共享配置的权威源；端侧保存最近成功版本和本地安全副本。
- 用户在允许编辑的客户端更改共享配置后，变更必须提交 Cloud 成功才显示为跨设备已生效；版本冲突不得静默覆盖。
- 登录、配对、恢复前台和用户手动刷新均可触发增量同步；首次配对必须取得完整基线。
- 离线时允许使用最近一次有效且未过期的非敏感配置；涉及已撤销设备、Grant 或凭据的操作必须 fail-closed。
- 删除、禁用、撤销必须作为一等同步事件传播，不能只同步新增/更新。

## 6. 用户故事

- 作为 Cloud 用户，我希望直接在 Web 创建和运行 Agent 会话，以便没有桌面 Host 时也能完成任务。
- 作为 macOS x64 用户，我希望离线于其他客户端也能在本机运行 Agent，以便本地文件、工具和审批不依赖手机或 Cloud Agent。
- 作为 Android 用户，我希望 APK 自己运行 Agent runtime，而不是依赖开发机 loopback，以便手机单独使用时仍能创建、恢复和完成 Agent 会话。
- 作为跨设备用户，我希望登录或配对后在三端得到一致的模型、偏好、workspace 和权限配置，以便不重复配置且撤销即时生效。
- 作为远程控制用户，我希望从 Cloud Web 或 Android 安全连接 macOS Host，并看到真实 transport、receipt、事件和最终结果，以便可靠地远程使用本机能力。
- 作为 Host 用户，我希望高风险工具只能在 Host 端审批，以便远程控制端不能绕过本机授权。
- 作为 UI 开发者，我希望桌面与 Web 引用同一版本化组件包、Android 引用独立 Compose 组件模块，以便产品状态和交互一致且不复制页面级 primitives。
- 作为验收人员，我希望每一功能点都有候选版本、设备、输入、输出和失败结果证据，以便给出可审计的 Go/No-Go 结论。

## 7. 功能范围清单

以下均为 P0；“完成”必须满足第 8 节对应验收，不以静态展示计数。

### 7.1 Cloud 功能

| 页面 / 领域 | 必须具备的功能点 |
| --- | --- |
| C01 登录与访问 | 登录、登出、会话恢复、访问申请、申请状态、无权限/过期/网络失败反馈。 |
| C02 AI Dashboard | workspace 概览、Agent/session 状态、设备状态、Cloud 存储/用量摘要、快速创建 Cloud Agent、空/加载/错误/离线状态。 |
| C03 Cloud Session | 创建 session、模型选择、附件、权限、发送 turn、流式事件、工具调用、审批状态、取消/steer、重试、恢复、文件/产物面板、唯一终态。 |
| C04 成员与访问 | 成员列表、邀请、访问申请审批、角色/权限变更、移除成员、越权拒绝和审计反馈。 |
| C05 设备与配对 | 配对开始/确认、设备注册/验证、在线状态、scope 筛选、设备详情、Grant 管理、撤销、重配、失败/过期状态。 |
| C06 Cloud 设置 | 账号、workspace、模型、偏好、安全、设备/会话、审计分类；保存、撤销、冲突和失败反馈。 |
| Cloud runtime | 真实 Provider readiness、session/turn/event durable 状态、排队、恢复、有界重试、取消、唯一终态、可观测但脱敏的错误。 |
| Relay | 授权连接、opaque E2E frame、LAN 元数据协调、Relay fallback、限流/大小限制、防重放、断连、撤销。 |

### 7.2 macOS x64 本机端功能

| 页面 / 领域 | 必须具备的功能点 |
| --- | --- |
| D01 新建会话 | 本地 Agent session、workspace 选择、附件、能力、权限、模型、语音输入（若页面展示该入口）、发送、排队、取消及完整状态。 |
| D03 会话列表与详情 | 历史列表、搜索/筛选、消息、工具调用、审批、队列、文件/产物、远程设备与 transport、复制/fork/archive/delete、恢复与失败反馈。 |
| D06 能力中心 | Skills、MCP、Plugins、Applications、Agents 的发现、安装状态、启禁用、权限、兼容性、错误和空状态。 |
| D09 设置 | 模型/Provider、主题、账号、设备、数据、安全、远程授权、Agent diagnostics；dirty/saving/saved/error 状态。 |
| APP01 Notes | 笔记列表/详情、来源和产物、Agent 关联、空/加载/错误状态；使用真实数据。 |
| APP02 Learning | 学习空间、研究/学习会话、画布或相关投影、进度和失败状态；使用真实服务。 |
| APP03 Monitoring | runtime、模型、任务、用量、错误和设备/Relay 可观测状态；数据脱敏且可追溯。 |
| APP04 System Runtime | sidecar/runtime 健康、版本、协议、Agent diagnostics、设备身份/Host 状态、恢复和故障指引。 |
| 本地 runtime | 不依赖 Cloud Agent 或其他客户端；支持真实模型、工具、审批、取消、steer、恢复和唯一终态。 |
| 远程 Host / 控制端 | 注册稳定设备身份、Host bootstrap/heartbeat、LAN 与 Relay、receipt/event/终态、本机审批、撤销和重连。 |

### 7.3 Android 功能

| 页面 / 领域 | 必须具备的功能点 |
| --- | --- |
| M01 Agent Home | session 列表、创建 Agent、Agent location、workspace/模型摘要、设备/同步状态、加载/空/错误/离线状态。 |
| M02 Session Detail | 消息、流式事件、工具/审批状态、发送、取消/steer、附件/产物入口、远程 Host 与实际 transport、恢复和唯一终态。 |
| M03 Settings | 账号、Cloud、模型、设备、同步、通知、安全、诊断、退出；保存/冲突/失败状态。 |
| M04 Memory | memory 列表、创建、查看、删除、空/加载/失败状态；权限和同步边界明确。 |
| M05 Font | 字体/字号或可读性偏好预览、保存、恢复默认，并同步属于共享偏好的配置。 |
| M06 Storage | 本地占用、缓存、离线数据、清理动作、风险确认、成功/失败反馈；不误删安全身份和未同步数据。 |
| Android runtime | APK 内嵌并执行与 canonical SDK 兼容的 runtime；真实模型、工具、事件、取消、恢复和唯一终态不依赖 `adb reverse`、开发机服务或另一客户端。 |
| 远程控制端 | 稳定设备身份、配对、LAN-first、Relay fallback、E2E command/receipt/event、Host 审批投影、撤销和断线恢复。 |

M07、M08 及 `PAGE-MAP.md` 中标记排除的移动页面不在本批范围。

### 7.4 公共组件库完成点

#### 桌面 / Web 独立包

- 可独立构建、测试、版本化和发布/本地锁定；桌面与 Cloud Web 通过包依赖引用，禁止复制包内源码形成分叉。
- 提供 semantic tokens：颜色、文字、间距、圆角、边框、层级、motion、focus ring、light/dark/reduced-motion。
- 提供 primitives：Button、IconButton、Input、Textarea、Select/Listbox、Checkbox、Switch、Tabs、Card、List/Table、Badge、Alert、Toast、Progress、Skeleton、Empty/Error/Offline、Dialog、Sheet/Drawer、Popover、Tooltip、Navigation/Sidebar/AppBar、ScrollArea；Resizable 仅桌面宽屏使用。
- 提供所有交互状态：default、hover、focus-visible、active、disabled、loading、selected、invalid、open/closed。
- Select 在桌面/Web 使用 trigger + Popover/Listbox；窄屏 Web 必须保持可触控且不溢出。
- 业务组件留在产品层，由 primitives 组合，不把 Session、Device、Model 等业务状态硬编码进基础组件。

#### Android 独立原生模块

- 作为独立 Compose design-system/ui-core 模块构建和测试，被 M01-M06 实际引用；禁止各页面重复定义同语义按钮、字段、弹层和状态视图。
- 与桌面/Web 共享语义 token 名称和状态合同，但使用原生 Compose/Material 交互。
- 提供与首批页面相需的 Button/IconButton、Field、Textarea、Checkbox/Switch、Tabs、Card/List、Badge、Banner/Snackbar、Progress/Skeleton/Empty/Error/Offline、Dialog、Bottom Sheet、Top/Bottom Navigation、App Bar。
- Select 使用 Bottom Sheet/Listbox，并具备取消、确认、选中、禁用、错误和返回键行为。
- 所有主要触控目标不小于 44dp，支持系统字体缩放、屏幕阅读器语义、深浅色和减少动画。

#### 跨端语义合同

- 使用 NoteMeld 蓝作为主强调色、平静中性工作区、border 优先于重阴影、卡片圆角 10–14px、控件圆角 7–9px、圆形发送按钮。
- 产品图标统一使用 Lucide 或 Android 对应的受控矢量资产，不用 emoji、icon font 或页面内临时手绘 SVG。
- 动效只服务状态转换，优先 transform/opacity；开启 reduced motion 后移除非必要位移和缩放。
- 每个 primitive 必须有用途、结构、状态、何时使用/不使用、宽窄屏或移动适配、可访问性和可执行示例。

## 8. 验收标准

### 8.1 制品、安装与基础运行

1. **BUILD-CLOUD-01** GIVEN 锁定的候选 commit 和生产构建配置，WHEN 构建并部署 Cloud，THEN 镜像 digest、版本、协议版本和 commit 可追溯，HTTPS、数据库、Redis/Relay 和真实 Provider readiness 全部健康。
2. **BUILD-MAC-01** GIVEN 一台 Intel macOS x64 验收机，WHEN 安装签名且完成公证的候选制品，THEN 安装、首次启动、冷启动、退出重启和覆盖升级均成功，无崩溃、白屏、sidecar 启动失败或未处理异常。
3. **BUILD-ANDROID-01** GIVEN 支持 minSdk 26 及以上的实体 Android 设备，WHEN 安装固定证书签名的候选 APK/AAB，THEN 安装、首次启动、冷启动、前后台切换和覆盖升级均成功，无崩溃、ANR、白屏或未处理异常。
4. **BUILD-COMPAT-01** GIVEN 同一批 Cloud、macOS x64、Android 制品，WHEN 三端建立连接，THEN 版本/协议协商成功；不兼容版本显示可行动提示并拒绝危险降级。
5. **BUILD-EVIDENCE-01** WHEN 任一上述验收完成，THEN 证据包含制品哈希或 image digest、完整 commit、版本、设备/OS、测试时间和脱敏结果，不包含密钥、token 或正文。

### 8.2 三端独立 Agent runtime

6. **RUNTIME-CLOUD-01** GIVEN Cloud 配置真实可用模型，WHEN Web 用户创建 session 并发送唯一 challenge，THEN Cloud 自身 runtime 产生流式事件、assistant 回答和唯一 `turn.succeeded`，不使用 deterministic/mock runner。
7. **RUNTIME-CLOUD-02** GIVEN Cloud turn 调用工具或需要审批，WHEN工具成功、失败、拒绝、过期或取消，THEN event 顺序、状态、错误和唯一终态与 canonical runtime 合同一致，副作用至多一次。
8. **RUNTIME-MAC-01** GIVEN Cloud 不可用但本机模型/Provider 可用，WHEN macOS 用户创建本地 session 并发送唯一 challenge，THEN 本机 runtime 独立完成回答并产生唯一成功终态。
9. **RUNTIME-MAC-02** GIVEN macOS session 正在运行，WHEN用户取消、steer、重启应用或恢复历史，THEN状态可解释、cursor 连续、已确认副作用不重复、未知副作用不自动重放。
10. **RUNTIME-ANDROID-01** GIVEN Android 关闭 USB 调试、没有 `adb reverse`、没有局域网 NoteMeld backend 且 Cloud Agent 不参与执行，WHEN 用户创建本地 Android session 并发送唯一 challenge，THEN APK 内 runtime 独立完成真实回答和唯一成功终态。
11. **RUNTIME-ANDROID-02** GIVEN Android 本地 session，WHEN发生工具成功/失败、用户取消、进程被系统回收并重新进入，THEN session 能恢复到明确状态，事件不乱序，副作用不重复。
12. **RUNTIME-PARITY-01** GIVEN 同一兼容 runtime contract fixture，WHEN分别在 Cloud、macOS x64、Android 执行，THEN session/turn/event/approval/error 的必需语义一致；平台差异只能出现在声明的 capability 上。
13. **RUNTIME-ISOLATION-01** GIVEN 两个并发 session，WHEN同时发送不同 challenge 和工具调用，THEN消息、工具结果、审批和终态互不串线。

### 8.3 Cloud 配置同步

14. **SYNC-BASELINE-01** GIVEN新登录或新配对的 macOS/Android 设备，WHEN首次同步完成，THEN第 5.1 节全部授权配置按同一 Cloud revision 可见，本地专属数据未被上传或覆盖。
15. **SYNC-CHANGE-01** GIVEN三端已在同一账号/workspace，WHEN用户在任一允许编辑端修改默认模型或共享偏好并成功保存，THEN其他在线端在一次增量同步后显示相同有效值和更高 revision。
16. **SYNC-CONFLICT-01** GIVEN两个端基于同一旧 revision 编辑同一配置，WHEN第二个写入发生冲突，THEN系统明确提示冲突并要求刷新/选择，不静默 last-write-wins 覆盖。
17. **SYNC-DELETE-01** GIVEN模型、设备或 Grant 已在 Cloud 禁用/删除/撤销，WHEN端侧下一次鉴权或同步，THEN相应能力立即不可用于新操作，旧缓存不能绕过撤销。
18. **SYNC-OFFLINE-01** GIVEN客户端离线，WHEN用户查看配置或尝试受保护操作，THEN可读取最近有效的非敏感快照并明确标注离线；需要最新授权的写操作 fail-closed，不虚报已同步。
19. **SYNC-SECRET-01** GIVEN配对下发 Provider 凭据，WHEN同步、持久化、显示、导出或记录错误，THEN凭据只在受保护通道和端侧安全存储中存在，UI/日志/事件/Cloud 投影不出现明文。
20. **SYNC-RECOVERY-01** GIVEN同步中途断网或进程退出，WHEN恢复网络并重启，THEN从已确认 revision 继续，同一变更不重复应用，部分写入不会成为已同步状态。
21. **SYNC-SCOPE-01** GIVEN用户切换 workspace 或权限角色，WHEN同步完成，THEN只展示新 scope 授权的模型、设备、session 和配置，旧 workspace 缓存不可越权读取。

### 8.4 端到端通信与远程 Agent

22. **E2E-PAIR-01** GIVEN未配对客户端和 Host，WHEN用户完成一次配对，THEN双方身份可验证、设备私钥不离端、Grant scope 明确、过期或错误码不能建立连接。
23. **E2E-WEB-MAC-01** GIVEN Cloud Web 控制端与在线 macOS Host 已授权，WHEN Web 发起远程 Agent turn，THEN macOS durable enqueue 后返回 receipt，Web 依次看到事件和唯一终态，实际 transport 可见。
24. **E2E-ANDROID-MAC-01** GIVEN Android 与在线 macOS Host 在同一 LAN，WHEN Android 发起远程 turn，THEN优先使用经证明的 LAN E2E 通道并完成 receipt、event、answer 闭环。
25. **E2E-FALLBACK-01** GIVEN LAN 不可达但双方可访问 Cloud Relay，WHEN发起同一类远程 turn，THEN自动或经明确提示回退 Relay，业务语义不变且不会重复提交 command。
26. **E2E-CLOUD-CLIENT-01** GIVEN macOS 或 Android 已登录且 Cloud Agent 可用，WHEN客户端选择 Cloud location 发起 turn，THEN请求绑定正确 workspace/session，流式事件可恢复且得到唯一终态。
27. **E2E-OPAQUE-01** GIVEN包含唯一敏感 needle 的远程会话，WHEN通过 Relay 完成通信，THEN Cloud 应用日志、数据库、Redis/Relay keyspace、审计投影均找不到明文 needle；端点可正确解密。
28. **E2E-REPLAY-01** GIVEN已成功处理的 request id、sequence 或密文帧，WHEN重复、乱序或篡改后再次发送，THEN接收端拒绝且不产生工具调用或其他副作用。
29. **E2E-OFFLINE-01** GIVEN Host 离线，WHEN控制端发送远程命令，THEN在有界时间内显示稳定的 offline/needs-attention 结果，不伪造 receipt，不无限等待。
30. **E2E-RECOVERY-01** GIVEN远程 turn 传输中断，WHEN网络恢复并重连，THEN cursor 单调前进、已确认事件不重复应用、未知副作用不自动重放，用户可明确重试或放弃。
31. **E2E-REVOKE-01** GIVEN设备或 Grant 被撤销，WHEN现有或新连接继续发送命令，THEN新命令立即拒绝，现有连接关闭或失去授权，旧 token 不能重新建立会话。
32. **E2E-APPROVAL-01** GIVEN远程命令触发危险工具，WHEN控制端等待审批，THEN只有 Host 端能批准/拒绝；拒绝或过期产生唯一 resolved/terminal 结果且危险工具从未启动。
33. **E2E-LIMIT-01** GIVEN超大 frame、超频请求或恶意连接，WHEN到达 Cloud/Host，THEN执行大小、速率、权限和并发限制，返回稳定错误且不影响其他 session。

### 8.5 `/docs/new-product` 页面验收

34. **UI-DATA-01** GIVEN第 7 节任一页面，WHEN页面加载和用户操作，THEN展示来自真实 service/router/runtime 的数据；mock、固定数组、仅 console log 或无行为控件判定失败。
35. **UI-STATE-01** GIVEN加载、空数据、运行、排队、等待审批、完成、失败、离线、needs-attention 中任一状态，WHEN页面进入该状态，THEN用户能看到一致、可理解且可行动的反馈，不以无限 spinner 代替终态。
36. **UI-CLOUD-01** WHEN逐页验收 C01-C06，THEN第 7.1 节每个功能点均可从生产路由到达、可操作、可恢复且权限正确。
37. **UI-MAC-01** WHEN逐页验收 D01、D03、D06、D09 和 APP01-APP04，THEN第 7.2 节每个功能点均可从桌面导航到达并绑定真实本地/Cloud 数据。
38. **UI-ANDROID-01** WHEN逐页验收 M01-M06，THEN第 7.3 节每个功能点均可从移动导航到达，支持返回键、前后台恢复、触控与窄屏布局。
39. **UI-RESPONSIVE-01** GIVEN `/docs/new-product` 定义的宽屏、窄屏和移动形态，WHEN调整窗口、系统字体或旋转 Android 屏幕，THEN主要操作可见、文本不截断关键含义、弹层不溢出、数据不丢失。
40. **UI-THEME-01** GIVEN light、dark 和系统主题，WHEN切换主题，THEN所有 scoped 页面和 overlay 使用 semantic tokens，文字、边界、focus 和状态色可辨识，无硬编码造成的不可读区域。
41. **UI-A11Y-01** GIVEN键盘/屏幕阅读器或 Android accessibility service，WHEN遍历主要流程，THEN焦点顺序、控件名称、错误关联、选中/禁用状态、Dialog/Sheet 焦点管理和返回行为正确；颜色不是唯一状态线索。
42. **UI-NAV-01** GIVEN刷新、深链、返回、会话恢复或无权限路由，WHEN进入 scoped 页面，THEN导航到正确页面或稳定的登录/403/404 状态，不丢失已确认 session。

### 8.6 公共组件库验收

43. **DS-WEB-PACKAGE-01** GIVEN干净环境，WHEN独立构建桌面/Web UI 包并运行测试，THEN无需启动产品即可成功产出版本化制品；桌面和 Cloud Web 锁定并引用同一版本。
44. **DS-WEB-CONSUME-01** WHEN扫描并运行 D01/D03/D06/D09、APP01-04、C01-C06，THEN第 7.4 节所列通用 primitives 来自公共包，页面层没有功能等价的复制实现。
45. **DS-ANDROID-MODULE-01** GIVEN干净 Android 工程构建，WHEN独立编译和测试 design-system/ui-core 模块，THEN模块成功，M01-M06 实际消费该模块而非页面内重复 primitives。
46. **DS-CONTRACT-01** GIVEN相同 token/state fixture，WHEN分别渲染桌面/Web 和 Android 组件，THEN语义名称、状态含义、错误/禁用/选中/加载行为一致，平台交互差异符合第 7.4 节。
47. **DS-CATALOG-01** WHEN打开组件目录或可执行示例，THEN每个 primitive 展示用途、结构、全部状态、使用/禁用场景、平台适配和可访问性说明。
48. **DS-SELECT-01** GIVEN相同 options/value，WHEN在桌面/Web 和 Android 使用 Select，THEN桌面/Web 使用可键盘操作的 Popover/Listbox，Android 使用可触控 Bottom Sheet/Listbox；取消不改值，确认只提交一个有效值。
49. **DS-ICON-01** WHEN检查 scoped 页面图标，THEN没有 emoji、icon font、来源不明或页面临时手绘 SVG；图标有可访问名称或正确标记为装饰。
50. **DS-MOTION-01** GIVEN系统启用 reduced motion，WHEN打开页面、弹层或状态变化，THEN非必要动画被禁用，关键操作与反馈不受影响。
51. **DS-VISUAL-01** WHEN对 scoped 页面进行候选版本截图对比，THEN结构、组件、状态和响应式行为符合 `/docs/new-product` 合同；允许内容与真实数据差异，不允许缺页、缺控件或以原型截图代替实现。

### 8.7 安全、可靠性和数据

52. **SEC-IDENTITY-01** GIVEN应用重启或升级，WHEN设备重新连接，THEN macOS 身份由 Keychain、Android 身份由系统安全存储恢复，device id/公钥稳定，私钥不明文落盘。
53. **SEC-AUTH-01** GIVEN未登录、token 过期、scope 不足或 workspace 不匹配，WHEN调用 Cloud、同步或远程能力，THEN返回稳定未授权状态，UI 清除敏感投影且不泄露资源是否存在。
54. **DATA-MIGRATION-01** GIVEN上一个受支持版本的数据，WHEN升级三端候选版本，THEN迁移可重复、失败可诊断，不丢失已完成 session、配置或安全身份；无法迁移时 fail-safe 并给出恢复路径。
55. **OBS-01** GIVEN任一失败场景，WHEN用户打开 diagnostics 或验收人员检索日志，THEN可以用 request/session/device 的脱敏标识定位问题，但看不到密钥、token、E2E 正文或原始隐私数据。
56. **CLEAN-01** GIVEN用户在 Android M06 或桌面数据设置执行清理，WHEN操作完成或失败，THEN预览/确认范围与实际删除一致，未同步数据和安全身份不被意外删除。

## 9. 输入 / 输出样例

### 9.1 本地 Agent 正常样例

输入：用户在 Android 本地 Agent 中发送“只回复 challenge `NM-A-7F3C`”。  
输出：事件流包含开始、必要的模型增量和唯一成功终态；assistant 语义内容包含该 challenge；证据确认没有 `adb reverse`、外部 NoteMeld backend 或 Cloud Agent 执行。

### 9.2 配置同步样例

输入：用户在 Cloud 将默认模型从 A 改为 B，保存成功；macOS 与 Android 当前处于旧 revision。  
输出：两端同步到新 revision 并显示 B；Provider secret 不显示；若 Android 同时基于旧 revision 修改，则收到冲突提示而不是覆盖 Cloud。

### 9.3 E2E 远程正常样例

输入：Android 选择已授权 macOS Host，发送包含唯一 challenge 的远程命令。  
输出：UI 显示实际 `LAN` 或 `Relay`；只有 Host durable enqueue 后出现 receipt；随后显示事件与唯一成功回答；Cloud 审计找不到 challenge 明文。

### 9.4 失败样例

- Android 依靠 `adb reverse` 调用开发机并返回回答：只能算开发 smoke，`RUNTIME-ANDROID-01` 失败。
- 页面能打开但按钮只显示 toast/mock 数据：对应 UI 功能点失败。
- Relay 返回“已发送”但 Host 未 durable enqueue：`E2E-WEB-MAC-01` 或 `E2E-ANDROID-MAC-01` 失败。
- 两端配置冲突后静默以后写覆盖：`SYNC-CONFLICT-01` 失败。
- Cloud 日志出现 Provider key、token、prompt 或 E2E challenge 明文：安全验收失败并整批 `NO-GO`。
- 组件只存在于 `/docs/new-product/design-system` 示例，生产页面没有引用独立包/模块：组件库验收失败。

## 10. 约束

- 平台 / 设备：Cloud production-like 环境；Intel macOS x64 实机；至少一台 minSdk 26+ Android 实体设备。模拟器只能用于补充，不能替代安装、后台恢复、网络切换和 E2E 现场证据。
- Runtime：Rust Agent SDK 保持唯一 Agent 行为事实源；三端不得分别复制 Agent loop、状态机或事件语义。
- 性能 / 耗时：所有网络、队列、模型、审批和连接操作必须有有界等待与可见进度；精确 SLO 在 Plan 前以现有基线测量后写入 Spec，不得以“无限等待最终成功”通过验收。
- 隐私 / 安全：E2E 正文、密钥、token、Provider 凭据和用户原始素材不得进入公开证据；审批、撤销、防重放和安全存储是发布硬门禁。
- 兼容性：三端锁定兼容的 runtime/schema/协议；升级不能破坏受支持的历史 session 和配置。
- UI：以 `/docs/new-product` 的页面结构与设计语义为目标合同；视觉细节继续由 `docs/new-product/design.md` 与 A04 管理，本文只定义可验收结果。
- License：新增依赖和图标资产必须有可用于产品发布的许可证并保留归属信息。
- 时间：本文不设上线日期；日期应在 Plan 形成、依赖和实体设备资源确认后单独确定，不能通过跳过 P0 验收保日期。

## 11. 边界场景

- 空数据：新账号、无模型、无 session、无设备、无 memory、无成员时显示可行动空状态。
- 权限拒绝：登录过期、workspace 越权、设备/Grant 撤销、Host 拒绝审批均 fail-closed。
- 网络失败：离线、弱网、LAN 不可达、Relay 断开、同步中断、Cloud 重启均有明确状态和恢复路径。
- 任务中断：应用退出、Android 进程回收、macOS sidecar 重启、Cloud worker 重启后不重复未知副作用。
- 旧数据兼容：升级后历史 session、配置、设备身份和 cursor 可读；不兼容时有迁移或明确阻断。
- 大数据量：大量 session、事件、设备、成员、模型和 memory 时需要分页/虚拟化或有界加载，不能冻结 UI；具体阈值在 Spec 基于基线确定。
- 多端并发：同一 session 和同一配置被多端同时操作时，使用 revision/idempotency 明确冲突和结果。
- 时间与时区：token/Grant/配对码过期基于权威时间；端侧时钟偏差不能绕过授权。
- 存储不足：Android/桌面写入、升级或缓存清理失败时不损坏已确认数据，并给出释放空间提示。
- Provider 不可用：模型下线、凭据失效、限流或配额耗尽时显示稳定错误，不无限重试或改用未授权模型。

## 12. 开放问题

没有阻塞 Plan/Spec 的产品范围问题。本文已采用以下默认裁决：Android 的“独立 runtime”按 APK 内执行解释；Cloud 为共享配置权威源；D01/D03/D06/D09、APP01-APP04、C01-C06、M01-M06 全部纳入首批 P0。

以下是 Plan/Spec 必须通过测量或环境盘点补齐的实施参数，不改变需求状态：

1. macOS 最低受支持系统版本、签名/公证账号和 Intel 实机清单。
2. Android 目标实体机矩阵、商店/企业分发方式和发布证书托管责任。
3. 基于真实模型、网络和数据规模测得的启动、同步、事件恢复和页面加载 SLO。
4. 桌面/Web 包及 Android 模块的最终名称、发布 registry 和版本锁定方式。

## 13. 与系统事实的冲突检查

- 与 `product-rules.md`：不冲突。继续保持 canonical Agent runtime、Host 审批、Cloud 不解密 E2E 正文、显式授权和真实终态；Plan 必须复核现有规则的完整映射。
- 与 `data-model.md`：本需求不新增字段。revision、cursor、session/turn/event、device/grant 的具体复用或扩展由 Spec 基于现有 schema 决定，禁止并行状态源。
- 与 `api-inventory.md`：现有 Agent v1、models、pairings、devices、grants、sessions、relay 和 cloud-sync API 提供基础；Android embedded runtime、完整配置冲突语义及组件包不应通过猜测现有 API 宣称完成，Spec 必须逐项映射。
- 与 `known-pitfalls.md`：已显式防止多套 Agent loop、状态镜像漂移、receipt 早于 durable enqueue、恢复后重复副作用、Cloud 明文泄露、用 mock/原型替代真实纵向验收。
- 对本地数据 / 线上服务：未来实现会影响三端 runtime、Cloud 配置、设备授权、UI 依赖和发布链路；本轮只有需求文档变更。
- 对用户已确认交互：遵守 Cloud、macOS x64、Android 三端范围，以及 `/docs/new-product` 页面和组件库目标；Windows 旧门禁不再作为本需求验收依据。

## 14. Requirement Quality Gate

- [x] 保留用户原始意图并写清用户、场景、痛点和上线价值。
- [x] 目标描述产品结果，未写成实现任务清单。
- [x] 当前事实来自源码、system docs、new-product docs；差距未虚报为完成。
- [x] 平台、页面、功能、组件、正常路径、失败路径和边界均有可观察验收。
- [x] 验收标准使用 GIVEN/WHEN/THEN，并有稳定 ID 供 Plan/Test 映射。
- [x] 明确非目标、同步数据边界、安全、兼容、License 和制品约束。
- [x] 完成 product-rules、data-model、api-inventory、known-pitfalls 冲突检查。
- [x] 未写入密钥、token、隐私正文或原始用户素材。
- [x] 开放项只剩实施参数，不阻塞需求进入 Plan。

## 15. Superpowers 交接

- 是否达到 Ready for Plan：是；Plan 与 Spec 已生成，当前状态为 `Planned`。
- 下一步（需用户另行明确要求后才执行）：
  - [x] 已生成 `docs/superpowers/plans/2026-09-13-cloud-macos-x64-android-agent-release.md`。
  - [x] 已生成 `docs/superpowers/specs/2026-09-13-cloud-macos-x64-android-agent-release.md`。
  - [ ] 按 Plan 从 T00 开始实施，并创建候选版本验收台账；不得复用旧 Windows 证据冒充 macOS 证据。
- Plan 必须覆盖：`BUILD-*`、`RUNTIME-*`、`SYNC-*`、`E2E-*`、`UI-*`、`DS-*`、`SEC-*`、`DATA-*`、`OBS-*`、`CLEAN-*` 的逐项映射。
- Plan 必须补充：三端源码/制品归属、SDK artifact/ABI 版本锁定、API/schema 差距、UI 页面到真实 service 的映射、package/module 边界、实体设备矩阵、SLO 基线、迁移/回滚和脱敏证据格式。
