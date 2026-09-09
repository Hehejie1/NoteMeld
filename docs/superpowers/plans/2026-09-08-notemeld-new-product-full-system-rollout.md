# NoteMeld new-product 完整系统迁移实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `docs/new-product` 的 D01/D03/D06/D09、APP01–APP04、Cloud、远程设备和移动端全部迁移为真实可运行系统，并保持 Agent、插件、文件和权限边界可验证。

**Architecture:** 以现有 Agent SDK/Agent Host 为唯一 Agent runtime；前端只消费真实 API、持久化状态和事件。先冻结跨端接口与数据契约，再分别完成桌面应用、Cloud/设备、移动端和最终集成验收；不复制 Agent loop，不用静态原型数据掩盖缺失后端。

**Tech Stack:** React/TypeScript、FastAPI/Python、SQLite、Tauri、Agent Host/独立 Agent SDK、插件与 Application Protocol、Cloud relay、iOS/Android/Harmony 客户端。

**Spec:** [`docs/requirements/2026-09-06-notemeld-new-product-desktop-system-v2.md`](../../requirements/2026-09-06-notemeld-new-product-desktop-system-v2.md)、[`docs/requirements/2026-09-08-notemeld-new-product-interface-matrix-v1.md`](../../requirements/2026-09-08-notemeld-new-product-interface-matrix-v1.md)

## Global Constraints

- `new-product` 是页面、功能和交互的第一权威来源；生产代码中的额外功能不自动新增产品入口。
- 本轮覆盖桌面端、Cloud、远程设备和移动端；不把任何已确认功能标记为“以后再做”。
- 不要求兼容现有会话、笔记、设置或插件数据；清空/重建必须明确确认、可审计、可观察。
- Agent SDK 是唯一 Agent 行为事实源；NoteMeld 不复制 Agent loop、状态机或事件语义。
- 本地 secret、Cookie、设备私钥、用户文件正文和 Relay 明文不得进入日志、fixture、分享或文档。
- 所有 UI 必须实现 loading、empty、running、approval、failed、cancelled、recovered 和 completed 状态。
- 任何 API、数据库字段、跨仓库协议或性能指标，在代码/测试未核对前不得凭页面名称猜测。
- 每个任务先写失败测试或契约测试，再实现最小改动；任务完成后运行对应仓库的最小验证集。

## 交付拆分

本总计划拆成四条可独立验收的实施线：

1. **合同与数据线**：接口矩阵、数据库/任务状态、三项缺口契约和安全门禁。
2. **桌面迁移线**：D01/D03/D06/D09 与 APP01–APP04 接入真实 service/API。
3. **Cloud/设备/移动线**：C01–C06、设备身份/LAN/Relay 和 M01–M06 迁移。
4. **集成发布线**：跨端纵向链路、性能、恢复、打包和最终 UI 验收。

合同与数据线完成前，不进入大规模 UI 重写；桌面迁移线通过前，不宣称桌面端完成；四条线全部通过后，才把 PRD 标为 Implemented。

### Task 1: 冻结真实接口与数据权威矩阵

**Files:**
- Modify: `docs/requirements/2026-09-08-notemeld-new-product-interface-matrix-v1.md`
- Modify: `docs/requirements/2026-09-06-notemeld-new-product-desktop-system-v2.md`
- Modify: `docs/system/api-inventory.md`（仅补充已核对的接口，不创造未实现路由）
- Test: `scripts/cloud/validate_product_docs.py`

**Interfaces:**
- Consumes: 现有 `desktop/frontend/src/services/`、`desktop/backend/app/routers/`、`docs/system/data-model.md`、`docs/system/api-inventory.md`。
- Produces: 每个 D/APP/C/M 功能均有页面、service、router、数据权威、权限和测试入口；每个 `missing`/`verify` 项都有明确决策结果。

- [x] **Step 1: 写矩阵完整性测试**

  为矩阵增加可机器检查的字段：`page`、`frontend_service`、`backend_route`、`authority`、`permission`、`tests`、`status`。缺任何字段的行必须失败。

- [x] **Step 2: 运行测试确认当前矩阵不完整**

  Run: `python3 scripts/cloud/validate_product_docs.py`

  Expected: 现有产品注册表继续通过；新的矩阵检查指出 APP01 笔记库、APP03 监控快照、APP04 更新/设备 Host 和 Cloud/移动端明细未完成。

- [x] **Step 3: 用源码和测试补齐事实映射**

  逐项核对 `desktop/frontend/src/services`、`desktop/backend/app/routers`、`desktop/backend/tests`、Cloud API inventory 和 Agent SDK contract；只记录已存在的 route/type/table，未知项进入“契约设计”任务。

- [x] **Step 4: 运行文档与静态契约校验**

  Run: `python3 -m json.tool docs/new-product/config/feature-registry.json`  
  Run: `python3 scripts/cloud/validate_product_docs.py`  
  Expected: PASS，且矩阵中不再存在无 owner 的功能行。

### Task 2: 设计三个缺失契约并完成安全门禁

**Files:**
- Create: `docs/system/change-spec-new-product-application-snapshots.md`
- Modify: `docs/system/api-inventory.md`
- Modify: `docs/system/data-model.md`
- Test: `desktop/backend/tests/test_new_product_contracts.py`

**Interfaces:**
- Consumes: Task 1 的事实矩阵；现有 Agent/Application/usage/note APIs。
- Produces: 三个可测试契约：笔记库查询、监控快照、更新/设备 Host 状态；不直接安装、更新或执行外部应用。

- [x] **Step 1: 为三个契约写失败测试**

  测试必须覆盖：分页边界、空数据、权限拒绝、聚合时间窗固定、组件 degraded/offline、更新签名校验失败、设备/Relay 明文不落盘。

- [x] **Step 2: 定义接口与状态**

  契约必须明确请求/响应字段、错误码、幂等键、权限 scope、审计动作和状态枚举；只读快照不得触发安装、更新、设备授权或文件读取副作用。

- [x] **Step 3: 更新系统文档并让测试先失败**

  Run: `pytest desktop/backend/tests/test_new_product_contracts.py -q`  
  Expected: 在实现路由前，缺失契约测试明确失败且失败原因指向缺失实现，不是 import 或环境错误。

- [x] **Step 4: 将契约决策回写矩阵和 PRD**

  把 `missing`/`verify` 转为 `planned` 或 `reuse`，保留尚未实现的 API 为 `needs_backend`，不得提前标成 `implemented`。

### Task 3: 后端和数据链路实现

**Files:**
- Create/Modify: `desktop/backend/app/routers/` 下与 Task 2 契约对应的 router
- Create/Modify: `desktop/backend/app/services/` 下的 note library、monitoring snapshot、updater/device projection service
- Create/Modify: `desktop/backend/app/db/` 下对应 schema/DAO/迁移
- Test: `desktop/backend/tests/test_new_product_contracts.py` 及领域测试

**Interfaces:**
- Consumes: Task 2 的请求/响应和状态契约。
- Produces: 可被现有 TypeScript service 调用的真实 API；所有写操作具备权限、幂等、事务边界和审计。

- [x] **Step 1: 为每个新增/变更路由写 API contract test**
- [x] **Step 2: 实现 service/DAO，优先复用现有 note、usage、application、device、agent 数据，不复制表和状态机**
- [x] **Step 3: 实现权限拒绝、空数据、超时、取消、失败恢复和审计路径**
- [x] **Step 4: 运行后端定向测试和 Python 编译检查**

  Run: `cd desktop/backend && pytest tests/test_new_product_contracts.py tests/learning tests/whiteboard -q`  
  Run: `python3 -m compileall desktop/backend/app`

### Task 4: 桌面壳层与 APP01 笔记应用迁移

**Files:**
- Modify: `desktop/frontend/src/App.tsx`、桌面布局和导航组件
- Create/Modify: `desktop/frontend/src/pages/` 下应用壳、Notes 应用页面和子视图
- Modify: `desktop/frontend/src/services/note.ts`、`noteStyle.ts`、`wiki.ts`
- Create/Modify: `desktop/frontend/src/services/importedNotes.ts`
- Test: `desktop/frontend/tests/` 中导航、Note/Wiki/导入 contract tests

**Interfaces:**
- Consumes: Task 3 的 note library、style、Wiki、import job API；`new-product` tokens/primitives。
- Produces: APP01 真实列表、搜索、样式模板、Wiki、导入和任务状态；没有静态成功数字。

- [x] **Step 1: 写 APP01 的加载/空/运行/失败/完成测试**
- [x] **Step 2: 实现应用壳和路由，保留现有 session/Workspace/permission context**
- [x] **Step 3: 接入笔记、样式、Wiki、导入 service；统一请求取消和分页**
- [ ] **Step 4: 验证大列表、长标题、图谱空状态、导入失败和重建取消**

### Task 5: 桌面 APP02 学习应用迁移

**Files:**
- Modify: `desktop/frontend/src/services/learning.ts`、`whiteboard.ts`
- Create/Modify: `desktop/frontend/src/pages/` 学习应用页面、画布、掌握验证和复习视图
- Test: `desktop/frontend/tests/` learning/whiteboard contract tests；`desktop/backend/tests/learning`、`whiteboard`

**Interfaces:**
- Consumes: 现有 Learning Canvas、review、Whiteboard、publish-note API。
- Produces: APP02 的学习空间列表、画布编辑、mastery evidence、复习队列和 Note 发布状态。

- [x] **Step 1: 写状态机测试，禁止客户端直接把 exposed 改成 mastered**
- [x] **Step 2: 接入画布/白板 revision 和 409 冲突恢复**
- [x] **Step 3: 接入复习 due、证据提交和异步发布结果**
- [x] **Step 4: 运行学习/白板定向测试及窄窗口验证**

### Task 6: 桌面 APP03 监控和 APP04 系统运行迁移

**Files:**
- Modify: `desktop/frontend/src/services/usage.ts`、`system.ts`、`transcriber.ts`、`plugins.ts`、`applications.ts`、`agent.ts`
- Create/Modify: `desktop/frontend/src/pages/` 监控应用和系统运行应用
- Test: usage/system/application/candidate/agent diagnostic contract tests

**Interfaces:**
- Consumes: Task 3 的监控快照、Application Host、candidate、Agent diagnostics、device/update contracts。
- Produces: APP03/APP04 真实健康状态、诊断、权限、审批、更新和设备连接 UI。

- [x] **Step 1: 写聚合快照和诊断时间线测试**
- [x] **Step 2: 接入 usage/provider/task filters、runtime health、plugin/transcriber health**
- [x] **Step 3: 接入 Application instances/runs/logs/permissions 和 candidate validation/decision**
- [x] **Step 4: 接入 updater/device/LAN/Relay 状态，所有危险写操作保留确认和审计**
- [x] **Step 5: 运行桌面前端 contract/build 和后端定向测试**

  `pnpm test:contracts`、前端全量契约测试（`106 passed, 0 failed`）、Vite 生产构建、NotesApp 单文件 lint、桌面核心回归（后端 `33 passed` + 前端 runtime/migration contracts）均已通过；本轮类型边界重构后全量 frontend lint 为 `0 errors, 17 warnings`，剩余仅为 React Fast Refresh/Hooks 提示。桌面后端全量回归为 `955 passed, 13 subtests passed`，定向 Application/Notes/Monitoring/Learning/Whiteboard 为 `193 passed`。

### Task 7: Cloud、远程设备和移动端迁移

**Files:**
- Modify: `cloud/` 认证、会话、设备、Workspace、usage、audit 和 relay 相关模块
- Modify: `ios/`、`android/`、`harmony/` 对应 M01–M06 页面和 Agent binding
- Test: Cloud tests、平台 binding/conformance tests、relay/device integration tests

**Interfaces:**
- Consumes: Task 1 的全端矩阵和 Task 2 的安全/状态契约。
- Produces: C01–C06、设备配对/LAN/Relay、M01–M06 的真实纵向闭环；移动端离线只读约束保持不变。

- [~] **Step 1: 为 Cloud/移动端补全页面到 API/数据表/权限矩阵**
- [~] **Step 2: 写认证、设备、公钥、grant、relay、离线同步和恢复测试**
- [~] **Step 3: 迁移 Cloud 页面并保留 C07 合并到 C06 的权限/审计语义**
- [~] **Step 4: 迁移移动端页面，验证离线、缓存、同步游标和跨端状态投影**
- [~] **Step 5: 运行 Cloud、iOS、Android、Harmony 可用的最小验证集，缺设备时记录未验证而不虚报通过**

  Cloud/Application 全量回归、iOS Simulator 和 Android APK 编译已有通过证据；iOS/Android/Harmony 已接入 LAN-first 与 Relay fallback、设备签名握手和 AES-GCM transport，桌面 Host 已能自动发现授权并启停 Relay。Harmony HAP 已通过编译，系统 DocumentViewPicker 已接入并将选择的文件复制到应用沙箱，Cloud command 会读取沙箱文件并提交 base64 附件；当前 Redis relay 运行回归已启用并通过。新增 OpenHarmony QEMU/`hdc` 验收：使用 SDK 的真实签名链生成 signed HAP，设备成功安装并由 `bm dump -n com.notemeld.mobile` 注册；启动 Ability 仍被 QEMU 开发模式锁屏阻止，因此 Harmony UI 启动、跨设备纵向和完整离线同步仍未完成，不能将本阶段标为 completed。

  本轮新增 `workspace_projections` / `workspace_memories` 宿主持久化表和 `/api/mobile/*` 投影 API，桌面系统运行应用已接入真实读取与记忆写入；接口具备 revision 冲突返回，测试覆盖创建、读取、更新、冲突和删除。移动端 service 请求契约已补齐；Android 现在启动时读取真实投影，记忆按钮调用真实 POST 且仅在成功后更新本地视图，Android/iOS/Harmony 的记忆路径均不再依赖静态业务数据。

  随后补齐了 iOS `UserDefaults` 与 Android `SharedPreferences` 的会话摘要缓存：网络请求失败时保留最近一次真实投影，在线返回非空结果后更新缓存；Harmony 已接入同一投影读取和记忆写入。Android/iOS/Harmony 的 Cloud-native session ID 与 event sequence 现在持久化，重连从上次游标继续分页；Cloud 后端游标/快照回归 `105 passed`，移动平台契约测试已增至 `7 passed`。Android/iOS/Harmony 的构建均通过；Android 已完成 AVD 在线/离线/恢复截图，iOS 已完成 Simulator 在线 API 联调，Harmony 已完成 QEMU signed-HAP 安装/注册，但三类真实设备之间的断网、恢复和游标连续性仍未验收。另修正 Android Cloud 密码输入使用 `PasswordVisualTransformation`，与 iOS `SecureField`、Harmony `InputType.Password` 保持一致。

  新版 Android APK 已在 API 34 `Pixel_3a_API_34_extension_level_7_x86_64` AVD 完成安装、启动和截图验收；断开本地后端时首页真实显示“离线模式：仅可查看已同步内容”。新版桌面后端在临时数据目录启动后，`/api/mobile/projection`、记忆 POST、Workspace PUT 和再次读取均返回 200，数据库实际创建 `workspace_projections` / `workspace_memories` 表并保留写入内容。随后补充了宿主后端在线联调：修正 Android 目标 SDK 35 的明文开发连接策略和成功后的在线状态回写，AVD 可通过 `10.0.2.2:8483` 成功加载宿主 API；按“后端停止→首页进入离线→后端恢复→重启后恢复在线”顺序完成截图验证。生产 Cloud/Relay 仍要求 HTTPS/加密通道。

  iOS 追加联调：在已启动的 iPhone 17 Pro Simulator 安装当前 `NoteMeldMobile.app`，临时桌面后端运行期间启动成功，并从后端日志确认模拟器请求 `/api/conversations` 与 `/api/mobile/projection` 均返回 200，截取到真实首页；模拟器构建继续使用无签名 Debug 产物，真机签名/安装仍属于发布环境门槛。

### Task 8: 全端集成、性能和发布验收

**Files:**
- Modify: `docs/new-product/` 验收说明和 feature registry 状态
- Modify: `docs/system/` 性能、恢复、发布和 known pitfalls
- Test: `tests/` 跨层测试、桌面/浏览器纵向测试、打包测试

**Interfaces:**
- Consumes: Tasks 1–7 的真实 API、状态和测试证据。
- Produces: 可运行安装包、真实数据库/Agent/插件/文件/Cloud/移动端连接，以及可审查的完成证据。

- [~] **Step 1: 建立性能基线**

  新增 `scripts/desktop/perf_baseline.py`。它对移动投影、Application 列表和监控聚合三个只读真实 API 做固定次数采样，输出 p50/p95、成功率、环境和原始样本；脚本返回非零状态表示请求未全部成功。当前已具备可重复的采样入口，正式发布阈值仍需在目标硬件和生产 Cloud 环境采集后锁定。

  临时全新 SQLite 后端实测（3 次/接口，HTTP 200 全部成功）：移动投影 p50 3.80ms / p95 50.31ms，Application 列表 p50 4.35ms / p95 4.65ms，监控聚合 p50 87.19ms / p95 268.55ms。该结果是本机开发环境基线，不是生产 SLA。

  固定首屏、应用切换、长会话、事件吞吐、Wiki/白板节点数、监控窗口、并发任务和内存上限，指标先写入文档再测试。

- [~] **Step 2: 验证正常、空、加载、运行、审批、失败、取消、恢复、完成、权限拒绝和离线状态**
- [~] **Step 3: 验证重启、重复提交、刷新、网络断开、Worker 崩溃、索引重建和数据重建**
- [ ] **Step 4: 验证浅色/深色、宽/窄桌面、移动触摸、键盘焦点、长文本和可访问性**
- [ ] **Step 5: 运行完整构建/测试/打包，只有证据齐全后把 PRD 和 feature registry 状态更新为 Implemented**

  追加运行证据：Cloud 临时 SQLite 实例真实启动并通过 `/ready`、登录、cloud-native session、command、snapshot/events 烟测；桌面全新数据目录真实启动并通过 Agent SDK Host、插件自动安装、`sys_health`、`deploy_status`、`applications`、`monitoring/snapshot`、`plugins/ready` API 烟测。期间发现并修复本地 `packages/notemeld-plugins` fixture 未被启动路径发现的问题，新增回归测试；这证明运行链路可启动，但尚不足以替代 Task 8 的性能、移动真机和生产部署验收。

  浏览器纵向烟测也已完成：真实 Vite 页面从应用列表打开笔记应用，笔记列表、样式模板、Wiki 标签均请求并展示真实后端状态；学习、监控、系统运行三个应用分别成功加载对应 API。隔离测试使用非默认前端端口时必须同步设置 `VITE_FRONTEND_PORT`，否则默认 CORS 会使浏览器 fetch 被拒绝，即使后端收到 200 请求。

  APP01 增量验收：笔记应用现在轮询真实 Wiki job 状态，运行中的 Wiki 任务可取消，失败/取消任务可重建；前端 contract 检查和生产构建通过。笔记库已补齐基于真实 `total/offset/limit` 的 50 条分页和长标题悬浮完整标题；导入失败、图谱空状态与任务取消仍需在浏览器纵向场景中继续验收。

  可访问性增量验收：系统运行应用的分类导航现在使用 `tablist/tab/tabpanel` 语义并暴露 `aria-selected`、焦点顺序和面板关系；Workspace 名称、目录引用、记忆输入均有显式关联 label；笔记与 Wiki 详情弹窗具备标题关联和有意义的关闭标签。新增 `runtimeAccessibilityContracts.test.mjs` 与 Notes 合同测试共 `6 passed`，TypeScript contract compile 和 Vite 生产构建继续通过。

  移动 Web 适配页追加验收：移除静态记忆 seed 和固定存储数字，改为读取 `/api/mobile/projection`、通过 `/api/mobile/memories` 写入记忆，并按浏览器 `localStorage` 实际内容计算和清理存储；新增契约测试覆盖真实投影与本地清理。相关新产品文件 lint 通过，生产 Vite 构建重新通过（`13169 modules transformed`）。

  进一步清理移动 Web 假数据：菜单任务改为来自真实 `useTaskStore` 会话，产物面板在没有 Agent 真实产物时显示空状态，不再展示固定任务名或伪造产物；对应契约测试 `8 passed`。

  iOS Simulator 验收：iOS 26.5 的 iPhone 17 Pro Simulator 已启动；`xcodebuild` Debug `iphonesimulator` 构建成功，应用已安装并通过 `simctl launch com.notemeld.mobile` 启动，截图确认主界面正常渲染。当前移动状态已改为 UserDefaults 持久化，存储清理操作触达真实沙箱目录，文件导入使用系统 file importer，主题选择已接入状态与 `preferredColorScheme`；选中文件会复制到应用沙箱，Cloud command 会读取并提交 base64 附件。该证据覆盖 iOS 安装/启动/UI，不等价于真实 iOS 设备或跨设备 LAN/Relay 互操作。

  iOS 追加复验：同一 iPhone 17 Pro Simulator 已用当前构建重新安装、启动并截屏，确认最近加入的移动投影、记忆写入、Cloud session/cursor 持久化改动没有破坏首屏启动；由于没有把后端连接到该模拟器的独立网络环境，本条仍不宣称 iOS 断网恢复或跨设备互操作已完成。

  Android `gradle --no-daemon assembleDebug` 已通过，Debug APK 安装命令返回 `Success`；修复 Android Keystore/Ed25519 身份在 Compose 首帧期间同步初始化后，带显示的 API 34 AVD 已真实启动 `MainActivity`，截图确认首页渲染，且通过设置入口触摸与返回键完成一次交互验证。移动状态现在由 SharedPreferences 加载/保存，存储清理操作触达真实沙箱目录，系统文件选择器可以读取附件并保留真实文件元数据；选中文件会先落入应用沙箱，CloudApi 发送时按 Cloud command 附件契约提交。临时 SQLite Cloud 实例已完成真实附件烟测：命令返回 completed，附件在 workspace/attachments 下可读回且字节一致。该 AVD 首次图形初始化约 47 秒并出现大量 `OpenGLRenderer`/GMS 慢日志，属于验证环境性能问题；Android 真机、跨设备 LAN/Relay 和完整离线同步仍未验收。

  Android 追加复验：使用持久终端重新启动 API 34 AVD，系统 `boot_completed=1`，当前 `app-debug.apk` 安装返回 `Success`，`MainActivity` 进入 resumed 状态并截取到真实首页；通过设置入口触摸和系统返回键完成交互，未发现启动崩溃。随后将 `usesCleartextTraffic` 收紧到 `src/debug/AndroidManifest.xml`，Debug 合并 Manifest 保留 AVD 宿主联调能力，Release 合并 Manifest 不含明文流量开关；`gradle assembleRelease -x lintVitalAnalyzeRelease` 生成 `app-release-unsigned.apk`。未跳过的 Release lint 因当前环境无法从 Google/Maven 建立 TLS 下载 `lint-gradle:31.7.3`，需在网络正常的 CI 中补跑。

  全量桌面后端回归追加复验：在临时 Redis relay 配置下，`NOTEMELD_CLOUD_RELAY_TEST_URL=redis://127.0.0.1:6381/0 PYTHONPATH=.:desktop/backend .venv/bin/pytest -q desktop/backend/tests` 为 `955 passed, 13 subtests passed`，不再有 skip；单独 Cloud 回归为 `210 passed`。前端生产构建、桌面真实服务器烟测、Cloud 回归和移动平台契约仍需与设备/发布环境证据分开看待，不能用单一测试结果替代发布验收。

  插件纵向验收：在独立 `packages/notemeld-plugins` 仓库执行 `cargo build --manifest-path plugins/official-document-to-markdown/Cargo.toml` 成功；宿主 `test_document_plugin_jsonl_smoke_when_built` 已从未构建 skip 变为真实 JSONL 调用，插件能力文件测试 `10 passed`。测试同时兼容当前 `packages/notemeld-plugins` 目录布局。

  插件仓库单元测试追加通过：`cargo test --manifest-path plugins/official-document-to-markdown/Cargo.toml` 的 CSV→Markdown 测试 `1 passed`，无失败或 skip。

  Agent 诊断补验：新增 `test_agent_diagnostics_contract.py`，覆盖完成 Turn 的事件时间线、`event_count`、`last_sequence` 和未知 Turn 的 404；与监控快照测试合计 `6 passed`。

  容器发布检查：`docker compose -f cloud/compose.yaml config` 在提供临时校验变量后通过，确认 healthcheck、卷、端口和 relay profile 配置可解析。Docker daemon 恢复后，`docker build -f cloud/Dockerfile -t notemeld-cloud:local-20260909 .` 已成功生成本地镜像；随后使用临时数据库卷和临时校验配置启动容器，`GET /ready` 返回 database/workspace_root 均为 `ok`。容器内端到端烟测也已通过：登录、创建 `/v1/cloud/sessions`、提交 command、轮询 command 至 `completed`、读取 snapshot/events，最终 `snapshot_seq=2`、`event_count=2`。这证明镜像和核心 API 链路可运行，但不等同于生产部署、真实外部 Provider 或真实 Cloud 基础设施已验收。

  Cloud 生产邮件链路补齐：新增 `change-spec-cloud-mail-delivery.md`，复用现有 SMTP adapter 发送管理员邀请；开发模式保留一次性 token 返回，生产模式通过 `NOTEMELD_CLOUD_INVITE_BASE_URL/invite/<token>` 发送链接且 HTTP 响应不再包含原始 token，SMTP 失败会撤销 pending invitation 并返回 503。新增 Cloud 回归覆盖成功投递和失败撤销，相关测试 `4 passed`；邀请接受页面与 `/invite/:token` 路由已接入桌面/Web 两份前端入口。

  移动端 Cloud-native 纵向烟测已固化为 `scripts/cloud/smoke_mobile_cloud.py`：使用标准库真实调用 `/ready`、登录、设备注册/heartbeat、创建 session、提交 command、轮询终态、读取增量 events 和 snapshot，并校验 `turn.completed` 与快照序号一致。隔离临时 Cloud 实例实测输出 `command_status=completed`、`event_types=[command.queued,turn.completed]`、`snapshot_seq=2`；脚本不输出 bearer token 或密码，已补入 `cloud/README.md` 作为部署后 smoke gate。

  `.github/workflows/cloud-backend.yml` 已把该烟测接入 Cloud release image job：镜像构建后启动临时容器，等待 `/ready`，再执行真实移动 Cloud-native 链路；触发路径同时包含烟测脚本本身，避免脚本变更绕过 CI。

  桌面 Tauri 发布编译的首次尝试被本机 Cargo `tuna` 镜像索引阻塞；随后使用命令行临时覆写到 `sparse+https://rsproxy.cn/index/`（不修改用户 Cargo 配置）下载锁定依赖并完成 `cargo check --locked`，同时修复 macOS/Windows/默认配置中已失效的 `notemeld-applications` 资源路径。最终 `cargo build --locked --release --manifest-path desktop/src-tauri/Cargo.toml` 通过，生成优化后的桌面 Rust runtime；再用真实 frontend dist 执行 `pnpm exec tauri build --bundles app --no-sign --ci` 通过，生成 `desktop/src-tauri/target/release/bundle/macos/NoteMeld.app`，其中包含 `applications/wiki/manifest.json`、UI 资源和真实 backend sidecar；无签名 `.app` 已实际启动，sidecar 监听 `8483` 并返回 `/api/sys_health` 200。签名、DMG 公证和发布机密仍需在发布环境完成。

  Harmony QEMU 验收补充：使用 OpenHarmony `hap-sign-tool.jar` 基于 SDK 的 profile/app CA 生成临时签名链，签名 HAP 安装到 `127.0.0.1:5556` 成功，`bm dump -n com.notemeld.mobile` 可读到真实 bundle 和 API 版本；`aa start` 仅因 QEMU 处于开发模式锁屏而返回 `10106102`，不是安装或签名失败。该结果证明制品可安装/注册，但不能替代可见 UI 启动和真实设备验收。

  后续复验发现 Harmony HAP 原先缺少真正的 `UIAbility` 声明，设备虽然能注册 bundle，但 `abilityInfos` 为空，无法启动页面。已新增 `EntryAbility.ets`、`module.json5` 的 `abilities`/启动窗口资源和可滚动设置页；使用官方 SDK 签名链重新签名安装后，`bm dump` 显示 `EntryAbility`，`aa start -a EntryAbility -b com.notemeld.mobile` 返回 `start ability successfully`。`uitest dumpLayout` 已读取真实 `pages/MobileSurface` 首页、会话页和设置页，点击“新建任务”进入会话，设置页可见 Cloud 地址、用户名、密码和“登录并同步”；密码字段已用 `InputType.Password`。本次证明 Harmony 应用入口和 UI 渲染已修复；Cloud URL 特殊字符的 QEMU 输入法注入仍不稳定，因此不宣称 Harmony Cloud 登录已完成。

  移动端菜单继续收口：Android、iOS、Harmony 原先的示例任务标题已删除，菜单现在只渲染真实 `/api/conversations` 投影；无数据时显示空状态。新增契约测试禁止静态任务种子，移动平台契约测试 `8 passed`，Android Debug、iOS Simulator Debug 和 Harmony HAP 均重新构建成功。

  移动端会话标题继续收口：三端点击真实会话后保存并展示其投影标题，新建会话显示“新建会话”，不再固定显示示例标题；契约测试确认三端界面源码不含旧示例任务标题。

  移动端 M02 会话操作继续收口：Android、iOS、Harmony 均保存当前会话 ID 与标题；“全部产物”展示真实空状态；“删除对话”只在存在真实会话 ID 时调用桌面后端 `DELETE /api/conversations/{id}`，仅收到 2xx 后从本地投影移除并返回首页，失败保留当前会话并进入错误状态。Android、iOS Simulator 和 Harmony HAP 均重新构建成功，移动平台契约测试扩展为 9 项并通过。

  M01 同步基础设施继续收口：桌面后端新增 `mobile_sync_cursors` SQLite 表和 `/api/mobile/sync-cursor` GET/PUT 契约，按设备、Workspace、会话复合主键保存快照 revision 与事件序号，并使用 expected revision 拒绝过期写入。Android、iOS、Harmony 前台均改为每 5 秒重新读取真实会话投影，并在读取后把 Workspace revision 写回服务端游标；网络失败时保留本地缓存。新增游标生命周期/冲突测试 2 项，三端契约测试扩展为 11 项，Android Debug、iOS Simulator Debug、Harmony HAP 均重新构建成功；桌面后端全量回归 `957 passed, 1 skipped, 13 subtests passed`。

  Android 运行级复验：API 34 AVD 安装当前 Debug APK 并启动 `MainActivity`；临时桌面后端日志实际观察到重复的 `/api/conversations`、`/api/mobile/projection` 和 `/api/mobile/sync-cursor` 请求，手工查询同一 Android 设备游标可读回服务端保存值。该证据覆盖 Android→桌面投影刷新链路，不替代真实 Android 设备、iOS/Harmony 设备和 LAN/Relay 互操作验收。

  离线恢复状态机补验：iOS 与 Harmony 的投影刷新成功分支现在显式切回 `ready`，与 Android 行为一致；新增契约测试覆盖 offline→ready 恢复，移动平台契约测试 12 项通过，iOS Simulator Debug 与 Harmony HAP 重新构建成功。

  为避免本机 Docker 状态绕过发布门禁，`.github/workflows/cloud-backend.yml` 已增加 Compose `--quiet` 校验和 Cloud release image 构建步骤；本地无法连接 daemon 时由 CI runner 负责完成镜像级验证。

  远程传输协议互操作复验：发现并修复 iOS/Harmony Relay URL 未从 `http/https` 转换为 `ws/wss`、Android Relay `ws` 被误判为 LAN，以及 Android/iOS 命令帧在加密 AAD 中遗漏 nonce 的问题。三端现在都按 `RemoteFrame.associated_data()` 的完整 envelope（含 nonce、排除 ciphertext）生成 AES-GCM AAD；Cloud/桌面端协议相关回归 `27 passed`，Android Debug、iOS Simulator Debug、Harmony HAP 均重新构建成功。跨真实 iOS/Android/Harmony 设备的 LAN/Relay 端到端互操作仍需实体设备或 CI device farm 验收，不能仅凭编译结果标记完成。

  Cloud 组织记忆补齐：新增 `organization_memories` 表以及管理员限定的 GET/POST/DELETE API，数据按组织成员关系隔离，创建/删除写入审计；回归覆盖创建、读取、删除和空列表，`2 passed`。该数据与用户偏好、Workspace 记忆分离，已更新 feature registry 为 implemented。

  移动缓存闭环补齐：Harmony 原先只持久化设置和记忆，现已将真实会话投影写入 preferences；在线刷新成功替换缓存，离线刷新保留最近缓存，与 Android SharedPreferences、iOS UserDefaults 的行为一致。存储页面仍按实际沙箱目录统计并执行分类清理；Harmony HAP 重新构建 `BUILD SUCCESSFUL`。

  Cloud 设置纵向闭环补齐：CloudClient 新增组织记忆列表/创建/删除方法，Cloud 设置的安全页显示管理员可用的组织长期记忆，并将无权限/Cloud 未提供状态作为明确错误展示；前端 contract/type compile 与 Vite 生产构建通过（`13170 modules transformed`）。

  需求数据审计补齐：复核 Cloud `user_preferences`、`workspaces`、Workspace 文件/备份 API 与桌面 `workspace_projections.folders_json` 的实际代码和回归后，将 registry 中仍标记为 prototype 的三项数据能力更新为 implemented；本地绝对路径仍只保留脱敏/宿主侧引用，不上传到 Cloud。

  APP02 复习聚合补齐：新增 `GET /api/learning-reviews/due`，从持久化学习空间聚合到期节点、目标、掌握状态和画布来源；学习应用复习页现在可从任意空间进入对应掌握验证。API 回归新增用例通过，前端 contract compile 和 Vite 构建通过。

  APP04 安全审批补齐：candidate UI 增加逐 candidate 审批说明输入，批准/拒绝请求将 reason 传给后端审计；原有验证错误、权限、风险、测试和 rollback 展示保持不变。前端 contract compile 通过。

  全量桌面后端回归复验：`desktop/backend/tests` 首次发现新增 Cloud 表未登记在产品 registry，补齐 `organization_memories` 的 Cloud schema 标记后，最终结果为 `958 passed, 1 skipped, 13 subtests passed`；产品文档校验 `validated 40 features, 40 bindings`。

  原生远程回执链路补齐：Android RemoteRelay 原先发送命令后未等待协议回执，且把加密 event ciphertext 当作明文读取；现已按完整 envelope（含 nonce）生成 AES-GCM AAD，解密 receipt/event，校验 frame_id/request_id，并在 60 秒内等待持久化回执，异常或连接关闭会唤醒等待方。Android Debug APK 重新构建成功；iOS、Harmony 同步增加远程传输源码契约断言，三端移动协议契约测试扩展为 `13 passed`。Harmony 解密参数顺序也已修正并重新通过 `BUILD SUCCESSFUL`。跨真实设备 LAN/Relay 仍需设备矩阵验收。

  插件任务投影补齐：`IngestionJobStore` 新增按时间排序的 durable job 列表，桌面后端新增 `GET /api/ingestion/jobs?limit=`；监控应用同时读取统一运行快照和真实插件采集任务，展示阶段、进度、完成/失败状态，不再只显示插件健康总数。后端 ingestion contract `4 passed`，前端 contract compile 与 Vite 生产构建通过（`13171 modules transformed`）。

  桌面更新链路补齐：注册 `tauri-plugin-updater`、默认 capability、固定 GitHub `latest.json` endpoint 和公钥；Release workflow 在配置签名密钥时开启 Tauri updater artifacts，分别收集带架构名称的 macOS `.app.tar.gz(.sig)` 与 Windows `.msi.zip(.sig)`，生成并上传 `latest.json`。修复 Tauri 从 `desktop` 根目录执行时 `beforeBuildCommand` 的错误相对路径，并让 macOS/Windows 本地打包脚本在存在签名密钥时自动启用 updater artifacts。原生 Rust `cargo check --locked`、9 项 Tauri 单元测试、11 项包装契约测试和 workflow YAML 解析通过。当前机器的完整 Tauri bundle 复验被本机 Cargo 全局 `tuna` registry 配置阻塞，不能当作 bundle 成功；Release runner 仍需配置 `TAURI_SIGNING_PRIVATE_KEY(_PASSWORD)` 后执行签名/公钥回验。

  APP04 设备连接 UI 补齐：系统运行应用的设备页不再复用监控页，新增真实设备身份、公钥登记、Cloud 设备状态、LAN endpoint 编辑、heartbeat 和桌面 Host bootstrap；页面明确展示 LAN 优先/Relay 回退以及 Relay 只转发密文的状态。前端 contract compile、生产构建（`13172 modules transformed`）和 runtime contract 测试通过。跨设备真实 LAN/Relay 仍需实体设备矩阵验收。

  前端最终增量检查：`pnpm lint` 通过（0 errors，18 个既有 hooks/fast-refresh warnings）；更新器/设备连接改动没有引入新的 lint error。需求矩阵将桌面更新明确标为 `partial`（待 CI secret、公开 Release 和回滚验收），设备链路保持 `partial`（待真实设备矩阵），避免把源码和构建证据误报为生产完成。

  updater artifact 真实验收：通过临时 Cargo wrapper 绕过本机失效的 `tuna` registry，在本机真实执行 `tauri build --bundles app --config {"bundle":{"createUpdaterArtifacts":true}}`；生成 `NoteMeld.app.tar.gz` 与 `.sig`，并由 `generate-latest-json.py` 生成版本 `0.0.4` 的 `latest.json`，平台键、签名和 URL 校验通过。期间修复 Tauri 配置版本 `0.0.1` 与桌面包版本 `0.0.4` 不一致的问题，并新增版本一致性契约测试。该证据覆盖 macOS arm64 本地 artifact，不代表 Windows/macOS Intel、GitHub 公网发布或回滚安装已验收。

  最终 macOS `.app` 烟测：启动带 updater plugin 的 `NoteMeld.app`，内置 sidecar 在 `8483` 正常启动，`GET /api/sys_health` 返回 `{"code":0,"msg":"success","data":null}`；测试进程随后已退出。

  发布脚本安全收口：`scripts/desktop/packaging/scripts/publish-desktop-release.sh` 不再默认使用硬编码明文 HTTP 主机，默认更新清单改为当前版本对应的 GitHub Release HTTPS 地址；私有发布源和上传目标仍必须通过 `NOTEMELD_RELEASE_BASE_URL`、`NOTEMELD_RELEASE_REMOTE` 显式配置。新增包装契约测试，结果 `10 passed`；`git diff --check` 通过。

  发布制品 fail-closed 收口：`generate-latest-json.py` 遇到任意 `.app.tar.gz`/`.msi.zip` updater 制品缺少对应 `.sig` 时直接以失败退出，不再跳过未签名制品生成不完整清单；新增反例契约测试，包装测试结果 `11 passed`，需求注册表再次校验为 `40 features, 40 bindings`。

  需求状态收口：清理 feature registry 中已经由 `decisions` 决定但仍残留的四条旧 `open_questions`；接口矩阵状态从 `Draft for Plan` 更新为 `Implementation baseline`，剩余门禁明确限定为 Release 签名/安装回滚、真实移动设备 LAN/Relay 矩阵和部署环境凭据。JSON、registry validator、需求/包装相关测试通过（`12 passed`，`40 features, 40 bindings`）。

  Cloud 生产 fail-closed 补齐：新增 `NOTEMELD_CLOUD_ENV`；当设置为 `production` 时，Cloud 启动会拒绝开发 OTP、缺失 Provider、local backup、memory relay、未启用设备签名证明、非 HTTPS 邀请地址和空 CORS，防止静默退回 deterministic runner 或单进程内存状态。`.env.example` 与部署文档已同步，Cloud 配置/Relay 测试 `10 passed`，Python compile 和 diff 检查通过。

  Cloud Compose 生产变量补齐：`cloud/compose.yaml` 现在显式转发部署环境、SMTP/邀请、S3、Provider、设备证明、Relay 和启动恢复配置；Compose 校验通过，配置契约测试 `8 passed`。宿主配置不再出现“已设置但容器未接收”的静默错配。

  Release 平台完整性门禁补齐：GitHub Release job 在生成 `latest.json` 后强制检查 `darwin-aarch64`、`darwin-x86_64`、`windows-x86_64` 三个平台，缺任一平台即失败，不创建部分可更新的 Release。workflow YAML、包装契约测试 `11 passed` 和三平台模拟 manifest 校验通过。

  移动端 CI 门禁补齐：新增 `.github/workflows/mobile-adapters.yml`，在 Linux 构建 Android Debug、在 macOS 构建 iOS Simulator Debug，并在 Linux 运行 Android/iOS/Harmony 原生源码契约；Harmony 仍需 OpenHarmony runner 或实体设备补充 HAP/安装验证。workflow YAML 有效，本机移动协议契约 `13 passed`。

  公网 Release 验证补齐：Release workflow 在创建 GitHub Release 后下载公开 `latest.json`，检查三平台 manifest、签名字段和每个 updater URL 的 HTTP 可达性；包装契约测试 `11 passed`、workflow YAML 有效。当前远端最新 `v0.0.3` 实测 `latest.json` 返回 HTTP 404，且 Release 资产只有 DMG/MSI，证明公网更新门禁尚未被旧版本满足，不能提前宣称发布完成。

  远端 Cloud CI 首次真实回归发现 Redis Relay 订阅竞态：`register()` 返回时 Pub/Sub listener 可能尚未完成 `PSUBSCRIBE`，紧接着的跨 worker 首帧会丢失。`RedisRelayBroker` 现增加 listener-ready barrier，订阅成功后才允许注册/投递；本机 Redis 集成回归 `1 passed`，Cloud 全量回归 `216 passed`。该修复将随候选分支重新触发 GitHub Actions。

  Mobile CI 首次真实回归发现 iOS 工程使用 Xcode 26 project format `objectVersion = 77`，而 `macos-14` runner 的 Xcode 15.4 无法读取。工程未使用新格式特性，已降为兼容 Xcode 15 的 `objectVersion = 56`；本机 Xcode 26.5 Simulator 构建 `BUILD SUCCEEDED`，待候选分支重新触发 iOS job。

  正式 `v0.0.4` Release 首次触发后，三平台均在 Tauri 构建前的资源校验失败：桌面配置引用仓库外的 `../../../packages/notemeld-applications/apps`，GitHub checkout 不包含工作区兄弟仓库。已将当前可发布的 Wiki Application bundle 纳入 `desktop/src-tauri/resources/applications/wiki`，并让默认/macOS/Windows Tauri 配置统一从仓库内资源打包；这同时消除了发布机依赖未 checkout 的外部工作区。首次运行不创建 Release，旧 `v0.0.4` 标签原先指向 2026-07-28 旧提交，已校正为当前 `main` 合并提交后重新触发发布验证。

  第二次 Release 运行已证明三平台可越过 Application 资源校验；Apple Silicon 生成了完整 updater bundle。Windows 随后暴露 PowerShell 会剥离 workflow 内联 JSON 的引号，Tauri 收到非法 `{bundle:{...}}` 配置。已改用仓库内 `desktop/src-tauri/tauri.release.conf.json`，避免 runner shell 差异；发布 Secret 同步校正为与仓库公钥匹配的无密码 updater key，待第三次 Release 运行验证。

  第三次 Release 运行进一步证明 Windows 已读取正确的无密码 updater key；实际失败点是 Tauri 默认 `beforeBuildCommand` 使用 Unix `VITE_BASE_PATH=./`，Windows cmd 将其视为未知命令。已在 Windows 专用配置改为 `set VITE_BASE_PATH=./`，待第四次 Release 运行验证。

  第四次 Release 运行已完成三平台编译、签名和制品上传；最终 manifest 门禁发现 Windows 仅有 `.msi`/`.msi.sig`，缺少 updater 需要的 `.msi.zip`。Tauri 当前配置值 `true` 生成了 v2 兼容签名形式，现改为官方 `v1Compatible`，使 MSI updater zip 与现有 `latest.json` 平台规则一致，待第五次 Release 运行验证公开资产。

  第五次 Release 运行完成：macOS Apple Silicon、macOS Intel、Windows 三个平台均构建并签名通过；Windows 已生成 `NoteMeld_0.0.4_x64_en-US.msi.zip` 与 `.sig`。GitHub Release `v0.0.4` 已公开，独立回读 `latest.json` 得到版本 `0.0.4`，三个平台签名字段均存在，三个 updater URL 的 HEAD 均返回 HTTP 200。桌面发布/更新链路达到可公开下载和更新清单校验标准。

  最终未宣称的门禁仍限定为真实移动设备间 LAN/Relay 互操作：Android AVD、iOS Simulator、Harmony QEMU 安装/启动和移动源码契约均已验证，但没有实体 Android/iOS/Harmony 设备矩阵与实际网络环境，因此 `M01.home`、`M02.session` 保持 partial，避免将模拟器证据冒充真实设备验收。

  最终 Cloud 容器级审计补齐：从当前仓库构建 `cloud/Dockerfile`，以隔离 compose project 启动真实 FastAPI 容器和 SQLite volume；`/ready` 返回 database/workspace 均为 `ok`。执行 `scripts/cloud/smoke_mobile_cloud.py` 完成登录、设备注册/heartbeat、会话创建、命令提交与完成、事件类型读取和 snapshot cursor，脱敏结果包含 `command_status=completed`、事件 `command.queued`/`turn.completed` 和 `snapshot_seq=2`。测试容器与临时 volume 已清理，源码工作区仅保留原有两个本地未跟踪移动制品文件。

  Cloud 生产 fail-closed 容器审计补充：用同一构建镜像设置 `NOTEMELD_CLOUD_ENV=production`、开发 OTP 和短 secret 启动，容器以 exit code 1 拒绝启动并明确报 `production requires SMTP-backed OTP delivery`；证明生产模式不会因缺少真实基础设施而静默回退到开发 runner。

  移动端最后一轮本机运行复验：启动 `Pixel_3a_API_34_extension_level_7_x86_64` Android API 34 AVD，安装当前 `android/app/build/outputs/apk/debug/app-debug.apk` 后通过 `MainActivity` 启动，`pidof com.notemeld.mobile` 有存活进程，启动日志未出现 `FATAL EXCEPTION`、`AndroidRuntime` 崩溃或 NoteMeld 错误；启动 iOS 26.5 Simulator `iPhone 17 Pro` 上的 `com.notemeld.mobile`，CoreSimulator 返回 launch success 且进程进入前台，`xcodebuild ... -sdk iphonesimulator ... CODE_SIGNING_ALLOWED=NO build` 返回 `BUILD SUCCEEDED`。Android `./gradlew test assembleDebug --no-daemon` 返回 `BUILD SUCCESSFUL`。该轮补强 Android/iOS 运行时启动与构建证据，但不改变真实实体设备 LAN/Relay 互操作仍待验收的状态。

  跨平台 E2EE 复核发现 HKDF 缺少显式统一约束：桌面实现和 Android 已按 RFC 5869 的 absent-salt 语义使用 32 字节零盐，iOS/Harmony 原先以空盐表达该语义，容易被平台实现差异放大。现已将 iOS `CryptoKit` 和 Harmony `CryptoFramework` 明确改为 32 字节零盐，并新增移动三端源码契约；Swift `CryptoKit` 固定向量与桌面 Python `HKDF(salt=None)` 输出一致，Android Debug 与 iOS Simulator Debug 重新构建通过。该修复在实体设备互操作前消除了一个跨端密钥不一致风险。

  HKDF 修复推送后的 GitHub Actions Mobile adapters run `34391714625` 已完成：Android adapter build、iOS Simulator build、native source contracts 三个 job 全部成功；其中新增三端 HKDF 契约也在 CI 的 Node 测试中通过。

  运行级 Mobile CI 首次补强暴露并修复两处真实发布问题：iOS 生成的 `Info.plist` 缺少 `CFBundleVersion`，已在 Xcode 工程和生成配置中固定 `CURRENT_PROJECT_VERSION=1`、`MARKETING_VERSION=1.0`；Android AVD 已成功启动并安装 APK，但原 smoke 脚本过早依赖 `pidof`，现改为显式 `am start -W`、清空并检查 fatal log、检查前台 Activity。修复后本机 iOS Simulator 安装/启动、Android AVD 安装/启动均通过，待 PR CI 重新验证。

  运行级 Mobile CI 最终验证完成：PR #11（`b053999`）已合并；GitHub Actions run `34395610413` 的 Android API 34 emulator、iOS Simulator 和 native source contracts 三个 job 全部成功。Android smoke 脚本进一步改为启动后检查前台 Activity，并以单行 fatal-log 判定避免 action 对多行 shell 条件的错误拆分；移动端模拟器运行门禁已纳入主分支。

## 完成定义

- `new-product` 中所有 D/APP/C/M 页面均有真实 service/API/数据/权限/测试映射。
- 页面不再依赖静态业务数字、假进度、假会话或前端推断的终态。
- Agent、插件、Application、文件、Cloud、设备和移动端都从真实运行时获得状态。
- 三项当前缺失契约已实现并经过失败/恢复/权限测试。
- 允许清空旧数据但不发生无感知破坏；初始化和重建动作可审计、可观察、可重试。
- 所有未验证的平台或设备明确列出，不把“代码存在”当作“真实运行通过”。
