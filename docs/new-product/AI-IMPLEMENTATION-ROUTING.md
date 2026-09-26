# new-product AI 实施路由

这份文件是把 `docs/new-product` 交给 AI 或开发者实施时的唯一入口。它不替代源码、测试或系统规范；目的是在开始改动前准确找到**应该改的层**，避免只改静态原型、重复实现状态机，或把端侧数据误写到 Cloud。

跨端会话 Command、Transcript、等待队列和 Agent 事件语义以 [CONVERSATION-STREAM-PROTOCOL.md](./CONVERSATION-STREAM-PROTOCOL.md) 为产品目标契约；动运行时代码前仍须按本文件核对真实 API、schema、源码与测试。协议文档中标为“当前事实”的内容不自动代表目标能力已全部落地。

**1:1 复刻 Cloud** 时以 [CLOUD-IMPLEMENTATION-SPEC.md](./CLOUD-IMPLEMENTATION-SPEC.md) 为权威实现规格：技术栈、全部数据表、API 清单、SSE/终端契约、root-jail 算法、状态机、安全边界与关键坑。该文档与当前 `cloud/` 代码对齐。

## 0. 先做判断

1. 从用户描述确定页面编号（如 `C05`、`M07`、`D03`）；编号不明确时，先查 [PAGE-MAP.md](./PAGE-MAP.md) 与 [功能注册表](./config/feature-registry.json)，不要猜。
2. 判断任务类型：
   - **仅原型/视觉评审**：改 `pages/` 与 `assets/`，并保持 `feature-registry.json` 的功能状态准确。
   - **正式 Web / 桌面产品**：改 `desktop/frontend/`，经已有 `services/` 调用后端；不要从页面直连 SQLite。
   - **Cloud 能力/API/数据**：改 `cloud/`，同时检查 Cloud Web 调用方、Cloud tests 与系统文档。
   - **移动端正式能力**：改 Android/iOS/Harmony 的原生适配；`pages/mobile/` 只是原型，不能当作运行时代码。
3. 先读下列事实源，再提交方案或改代码：
   - 仓库协作规则：[AGENTS.md](../../AGENTS.md)、[CLAUDE.md](../../CLAUDE.md)
   - [当前架构](../system/current-architecture.md)
   - [产品规则](../system/product-rules.md)
   - [数据模型](../system/data-model.md)
   - [API 清单](../system/api-inventory.md)
   - [已知风险](../system/known-pitfalls.md)
   - [多端架构、数据与功能地图](./PAGE-MAP.md)、[功能注册表](./config/feature-registry.json)

若系统规范、测试和原型相互矛盾，以**实际代码/测试为当前事实**，以 `status: partial` 或 `prototype` 标出的条目为待实现目标；不要静默把目标当成已完成能力。

## 1. 实施顺序与硬边界

| 先确认什么 | 再进入哪里 | 不可绕过的边界 |
|---|---|---|
| 产品意图、页面编号、完成度 | `docs/new-product/config/feature-registry.json` | 页面原型不是生产实现证明。 |
| 运行位置、authority、跨端状态 | `docs/system/current-architecture.md`、`data-model.md` | Cloud 是控制面；桌面/移动端各自保有本地事实与安全存储。 |
| 真实接口和 schema | `cloud/app.py`、`cloud/db.py`、`desktop/backend/app/routers/` | 不凭文档猜字段或路由。 |
| 真实 UI 与调用边界 | `desktop/frontend/src/App.tsx` → 页面 → `services/` | UI 不直接改数据库、不复制 Agent loop。 |
| 回归门禁 | 对应 tests 与本文件末尾命令 | 改 API、数据、状态或权限必须同步系统文档。 |

### 必须保留的跨端规则

- Cloud 团队共享的是**模型目录与 Auto 默认策略**；Cloud 会话和已连接 Cloud 的本地端发送时只从此目录选模型。
- 桌面/移动端的本地 Provider API Key 各自保管，不能进入 Cloud 目录、跨端同步、二维码或日志。模型目录组织共享迁移当前仍是 `partial`，先查 `cloud/app.py` 与对应测试再动 schema。
- 扫码只传短时、一次性添加材料。它不等于登录、在线、Grant 或可控制。
- 桌面和移动端在 Cloud 看来都是第三端设备；离线统一为 `offline_readonly`，恢复在线且完成同步后才允许远程写操作。
- Workspace 使用统一 ID 与字段语义，但文件正文仍由各端文件系统负责；Cloud 备份索引与对象存储不等同于本地文件夹。
- Agent turn、审批、事件与取消必须继续走既有 Agent Host/SDK；远控端不能创建第二套执行状态机。

## 2. 页面编号 → 真实实现入口

“原型”栏用于核对设计；“正式入口”才是要实施真实功能时的第一站。先从该行入口阅读，再沿 import、service、router 和测试追踪。

### 桌面端 D 系列

| 页面 | 原型 | 正式入口 | 后端/数据入口 | 优先验证 |
|---|---|---|---|---|
| D01 新对话 | `pages/desktop/d01.html` | `desktop/frontend/src/pages/HomePage/Home.tsx`、`components/ChatComposer.tsx` | `desktop/backend/app/routers/agent.py`、`routers/conversation.py`、`services/agent_store.py` | `frontend/tests/*Agent*`、`backend/tests/agent_host/` |
| D03 会话详情与产物 | `pages/desktop/d03.html` | `Home.tsx`、`messageRenderers.tsx`、`conversationHelpers.ts` | `routers/conversation.py`、`routers/agent.py`、`agent_host/` | Agent/Conversation 对应契约测试 |
| D06 插件应用 | `pages/desktop/d06.html` | `pages/Applications/index.tsx`、`layouts/AppLayout.tsx` | `backend/app/applications/`、`routers/mcp.py` | `backend/tests/test_applications.py`、前端 Applications tests |
| D09 设置 | `pages/desktop/d09.html` | `pages/SettingPage/SettingsHome.tsx`、`Model.tsx` | `routers/model.py`、`routers/provider.py`、`services/model.py` | `frontend/tests/modelRuntimeConfigContracts.test.mjs`、模型后端测试 |

### Cloud C 系列

| 页面 | 原型 | 正式入口 | Cloud 入口 | 优先验证 |
|---|---|---|---|---|
| C01 登录与申请 | `pages/cloud/c01.html` | `desktop/frontend/src/pages/CloudPage/index.tsx`、`CloudLoginPanel` | `cloud/app.py` 的 `/v1/auth/*`、访问申请/邀请处理 | `desktop/backend/tests/test_cloud_backend_slice.py`、`test_cloud_config.py` |
| C02 AI 工作台 | `pages/cloud/c02.html` | `CloudPage/index.tsx`、`CloudSessionList` | `cloud/app.py` dashboard、session、usage 路由 | Cloud 页面与会话 contract tests |
| C03 云端会话 | `pages/cloud/c03.html` | `CloudSessionPanel`、`CloudSharePanel`、`CloudApprovalList` | `cloud/app.py` session/command/stream/terminal/event/approval 路由、`cloud/agent.py`、`cloud/terminal.py`；规格见 `CLOUD-IMPLEMENTATION-SPEC.md` | `test_cloud_agent.py`、`test_cloud_backend_slice.py` |
| C04 人员管理 | `pages/cloud/c04.html` | `CloudUserList`、`CloudUserForm` | `cloud/app.py` admin users、access requests、invitations | Cloud admin/API tests |
| C05 设备与远控 | `pages/cloud/c05.html` | `CloudDeviceList`、`CloudPairingPanel`、`CloudGrantPanel`、`CloudRemoteAgentPanel` | `cloud/app.py` device/pairing/grant、`desktop/backend/app/cloud_sync/` | `test_cloud_relay_*`、`test_cloud_runtime.py`、`test_cloud_sync_protocol.py` |
| C06 设置 | `pages/cloud/c06.html` | `CloudPage/index.tsx` 的 `SettingsView`、`CloudModelList`、`CloudWorkspaceBrowser` | `cloud/app.py` preferences/models/workspaces/audits、`cloud/db.py` | `test_cloud_config.py`、Cloud settings/client contract tests |

### 移动端 M 系列

| 页面 | 原型 | Android 正式入口 | 关联能力/验证 |
|---|---|---|---|
| M01 首页、M02 会话 | `pages/mobile/m01.html`、`m02.html` | `android/src/main/kotlin/com/notemeld/mobile/MobileSurface.kt`、`MobileSurfaceState.kt`、`android/app/.../MainActivity.kt` | 本地/Cloud/远程发送、Agent 终态、离线状态；Android UI 与 adapter tests |
| M03 设置、M04 记忆、M05 字体、M06 存储 | `m03.html`–`m06.html` | `MobileSurface.kt`、`MobileLocalStore.kt`、`MobileApi.kt` | 设置持久化、记忆投影、设备本地存储；先检查平台 API 是否已有真实调用 |
| M07 模型设置 | `m07.html`、`mobile-model-settings.js` | `MobileSurface.kt`、`ModelPairingScanner.kt` | Cloud 目录选择与本地 Provider 分开；扫码不得同步 API Key |
| M08 远程设置 | `m08.html`、`mobile-remote-settings.js` | `MobileSurface.kt`、`CloudApi.kt`、`AndroidRemoteRelay.kt` | 设备身份、Grant、LAN-first/Relay；表单保存不等于远控已连接 |
| M09 产物、M10 预览 | `m09.html`、`m10.html` | `MobileSurface.kt`、`MobileLocalStore.kt` | 文件 ID 与授权读取；HTML 必须隔离，未知格式只能给下载提示 |

iOS/Harmony 的同一语义必须仍通过各自原生适配与共享 SDK 合同实现；不要把 Android UI 或状态机复制过去。跨端协议先读 [Cloud adapter contract](../system/cloud-adapter-contract.md)。

### 应用 APP 系列

| 页面 | 原型 | 正式入口 | authority |
|---|---|---|---|
| APP01 笔记 | `pages/apps/app01.html` | 应用源码属于独立 `notemeld-applications` 仓库；本仓库只从 `desktop/backend/app/applications/` 读取 manifest 并通过 Host 承载 | `note_documents` 与 Wiki store |
| APP02 学习 | `pages/apps/app02.html` | 先定位独立应用仓库；宿主侧再检查 `routers/learning.py`、`routers/whiteboard.py` | LearningCanvas、whiteboard、已发布 Note |
| APP03 监控 | `pages/apps/app03.html` | 先定位独立应用仓库；宿主侧检查 `services/usage.ts`、`routers/usage.py` | `model_usage_records`、运行健康投影 |
| APP04 系统运行 | `pages/apps/app04.html` | `pages/Applications/DeviceConnectivityPanel.tsx`、Application Host | Agent 诊断、设备/LAN/Relay 状态 |

当前 checkout 若没有独立 `notemeld-applications` 仓库，APP01–APP03 的应用源码不是本仓库可修改目标；先向任务发起人索取或切换到该仓库，不能在 `desktop/frontend/src/` 复制实现。

## 3. 按主题反向路由

| 用户需求关键词 | 先读 | 接着检查 |
|---|---|---|
| 模型、Provider、Auto、测试连接、扫码添加 | A01/A02/A03 的 `models` 条目；`docs/system/product-rules.md` | `cloud/app.py` model routes、`CloudModelList`、`CloudModelForm`、桌面 `Model.tsx`、`MobileSurface.kt` |
| Cloud 模型共享、组织范围、密钥不共享 | `data-model.md` 的 Cloud slice；`feature-registry.json` 的 `C03.model`/`C05.devices` | `cloud/db.py` 的 `models`、`cloud/app.py` 的 model/pairing 逻辑及 Cloud tests；必须明确 migration 与回归策略 |
| 设备、二维码、远控、在线/离线、Grant | A03 remote connection contract、`cloud-adapter-contract.md` | `cloud/app.py` device/pairing/grant、`cloud_sync/`、`Cloud*Device*` 组件、Android `CloudApi`/`AndroidRemoteRelay` |
| Workspace、文件、备份、存储 | A01/A02 的 workspace；`data-model.md` | `cloud/workspace.py`、`cloud/backup_storage.py`、`routers/workspace.py`、`CloudWorkspaceBrowser` |
| 会话、Agent、工具、审批、取消 | A01、D01/D03/C03/M02 功能条目 | `routers/agent.py` → `agent_host/` → SDK；不得绕过 Host 或复制状态机 |
| 人员、邀请、角色、审计 | C01/C04/C06 条目、`product-rules.md` | `cloud/app.py` admin/auth/audit；角色目前只读 |
| 新产品视觉或说明页 | `design.md`、A04、目标 `pages/*`、相关 `assets/*` | `feature-registry.json`、`scripts/cloud/validate_product_docs.py` |

## 4. 开始实现前的交付格式

在改动前，AI 应用以下模板简短说明：

```text
页面 / 目标：C05 设备配对
当前事实：<已从源码和测试确认的行为>
目标规则：<来自 product-rules / feature registry 的已确认边界>
改动层：<prototype | frontend | cloud | native adapter | docs>
影响文件：<具体文件>
验证：<最小命令或测试>
未决项：<仅无法由源码或已确认规则决定时提出；不要写入原型页面>
```

任何 API、schema、状态机或权限语义的改动，都要新建或更新 `docs/system/change-spec-*.md`，并同步 `current-architecture.md`、`data-model.md`、`api-inventory.md`、`product-rules.md` 或 `known-pitfalls.md` 中受影响的事实。

## 5. 最小验证命令

在仓库根目录执行与改动范围匹配的最小集合：

```bash
# new-product 文档、绑定与 Cloud 静态映射
python3 scripts/cloud/validate_product_docs.py

# Cloud 后端或控制面
pytest desktop/backend/tests/test_cloud_backend_slice.py
pytest desktop/backend/tests/test_cloud_config.py

# Agent / 同步 / 远控边界
pytest desktop/backend/tests/agent_host
pytest desktop/backend/tests/test_cloud_runtime.py
pytest desktop/backend/tests/test_cloud_sync_protocol.py

# Web / 桌面前端
(cd desktop/frontend && corepack pnpm test:contracts)
(cd desktop/frontend && corepack pnpm build)
```

只报告实际运行且通过的命令。工作树可能包含其他人的未提交改动：开始和结束都检查 `git status`，只提交本任务涉及的文件。
