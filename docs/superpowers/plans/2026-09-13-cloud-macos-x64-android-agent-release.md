# NoteMeld Cloud / macOS x64 / Android Agent 上线执行计划

状态：Planned  
日期：2026-09-13  
Canonical requirement：[`2026-09-13-cloud-macos-x64-android-agent-release.md`](../../requirements/2026-09-13-cloud-macos-x64-android-agent-release.md)  
Execution spec：[`2026-09-13-cloud-macos-x64-android-agent-release.md`](../specs/2026-09-13-cloud-macos-x64-android-agent-release.md)

> 本文件只定义后续执行方式。本轮未开始实现、构建候选包或宣称任何上线 Gate 已通过。

## 1. Goal

把当前已有但不完整的 Cloud、macOS x64 和 Android 能力收敛为同一可上线候选版本：三端各自运行 canonical Agent runtime，同步 Cloud 权威配置，完成授权 E2E 通信，交付 `/docs/new-product` 对应生产页面和公共组件库，并用自动化、Intel Mac 本机、Android 模拟器与实体机、截图差异和安全审计形成 56/56 P0 证据。

## 2. Architecture and execution rules

- Rust Agent SDK 是唯一 Agent loop、状态机和事件语义来源。Cloud 现有 Python loop、Android loopback adapter 都只能作为迁移输入，不能作为目标架构。
- SDK 与 NoteMeld 是独立仓库。SDK artifact 先独立构建、测试、提交和发布/锁定；NoteMeld 只消费带 manifest、hash、ABI/schema 版本的 wheel/AAR，不引用 SDK 工作区源码回退。
- 每条并行工作流使用独立 worktree/分支和明确文件 owner；跨工作流共享协议先由合同任务冻结。不得在同一脏工作树中同时修改同一文件。
- 新增迁移优先 additive、可回滚；设备撤销、Grant、密钥和安全 revision 不允许因客户端回滚而复活。
- 每个任务先补失败测试/契约，再实现，再运行最小验证；任务合入后由最终同步任务运行全量验证。
- `/docs/new-product` 只作为页面和设计合同。生产 Cloud 不挂载或发布原型 HTML。
- 视觉验收同时包含：feature locator 完整性、同视口结构比对、平台 golden diff 和人工签字。动态真实数据可以遮罩内容，但不得遮罩控件、状态、导航或布局。

## 3. Parallel execution DAG

```text
T00 冻结基线与 ownership
 ├─ T01 SDK/runtime/ABI 合同 ─────────────┐
 ├─ T02 UI token/page/state 合同 ────────┤
 ├─ T03 配置同步/兼容协议合同 ───────────┤  Barrier A：合同与 artifact 可消费
 └─ T04 验证/截图基础设施 ───────────────┘

Barrier A 后并行：
 ├─ T05 Cloud canonical runtime + sync backend
 ├─ T06 macOS x64 runtime/Host/打包
 ├─ T07 Android embedded runtime + sync client
 ├─ T08 Web 公共组件包 + Cloud Web
 ├─ T09 桌面 D/APP 页面迁移
 ├─ T10 Android :ui-core + M01-M06
 └─ T11 E2E/设备/Relay 安全加固

Barrier B：各 lane 定向测试通过
 → T12 同步合入与版本协商
 → T13 全量自动化与迁移/恢复
 → T14 本机/模拟器运行与截图对比
 → T15 production-like Cloud + Intel Mac + Android 实体机 E2E
 → T16 RC 制品、证据台账与最终 Go/No-Go
```

最大并行宽度建议为 6；T12–T16 必须串行执行，不允许在截图或最终验收期间继续修改页面和协议。

## 4. Worktree and ownership model

| Lane | 仓库 | 独占文件域 | 可并行条件 |
| --- | --- | --- | --- |
| SDK | `packages/notemeld-agent-sdk` | `crates/agent-ffi/`、`bindings/kotlin/`、Python binding、artifact scripts/fixtures | T00 后立即开始 |
| Cloud | `NoteMeld` | `cloud/`、Cloud tests、Cloud Docker/CI | T01/T03 合同冻结后实现 |
| macOS | `NoteMeld` | `desktop/backend/app/agent_host/`、`cloud_sync/`、Tauri/mac packaging/release job | T01 artifact 合同冻结后 |
| Android runtime | `NoteMeld` | `android/agent-runtime/`、API/store/runtime wiring、runtime tests | T01 AAR 可消费后 |
| Web UI | `NoteMeld` | `desktop/frontend/packages/ui-web/`、`apps/cloud-web/` | T02 后 |
| Desktop UI | `NoteMeld` | D01/D03/D06/D09、APP01-04 页面与业务组件 | T02、T08 package API 稳定后 |
| Android UI | `NoteMeld` | `android/ui-core/`、M01-M06、Compose UI tests | T02 后；与 Android runtime 分文件并行 |
| E2E | `NoteMeld` | relay/handshake/protocol fixtures/verifiers | T01/T03 后；三端 adapter owner review |
| Verification | `NoteMeld` | `tests/visual/`、`scripts/acceptance/`、证据 schema | T00 后并行，T12 后冻结 |

## 5. Tasks

### Acceptance coverage matrix

| Plan owner | Requirement acceptance IDs |
| --- | --- |
| T01/T05/T06/T07 | `RUNTIME-CLOUD-01`, `RUNTIME-CLOUD-02`, `RUNTIME-MAC-01`, `RUNTIME-MAC-02`, `RUNTIME-ANDROID-01`, `RUNTIME-ANDROID-02`, `RUNTIME-PARITY-01`, `RUNTIME-ISOLATION-01` |
| T03/T05/T07 | `SYNC-BASELINE-01`, `SYNC-CHANGE-01`, `SYNC-CONFLICT-01`, `SYNC-DELETE-01`, `SYNC-OFFLINE-01`, `SYNC-SECRET-01`, `SYNC-RECOVERY-01`, `SYNC-SCOPE-01` |
| T11/T15 | `E2E-PAIR-01`, `E2E-WEB-MAC-01`, `E2E-ANDROID-MAC-01`, `E2E-FALLBACK-01`, `E2E-CLOUD-CLIENT-01`, `E2E-OPAQUE-01`, `E2E-REPLAY-01`, `E2E-OFFLINE-01`, `E2E-RECOVERY-01`, `E2E-REVOKE-01`, `E2E-APPROVAL-01`, `E2E-LIMIT-01` |
| T08/T09/T10/T14 | `UI-DATA-01`, `UI-STATE-01`, `UI-CLOUD-01`, `UI-MAC-01`, `UI-ANDROID-01`, `UI-RESPONSIVE-01`, `UI-THEME-01`, `UI-A11Y-01`, `UI-NAV-01` |
| T02/T04/T08/T10/T14 | `DS-WEB-PACKAGE-01`, `DS-WEB-CONSUME-01`, `DS-ANDROID-MODULE-01`, `DS-CONTRACT-01`, `DS-CATALOG-01`, `DS-SELECT-01`, `DS-ICON-01`, `DS-MOTION-01`, `DS-VISUAL-01` |
| T05/T06/T07/T11/T13/T15 | `BUILD-CLOUD-01`, `BUILD-MAC-01`, `BUILD-ANDROID-01`, `BUILD-COMPAT-01`, `BUILD-EVIDENCE-01`, `SEC-IDENTITY-01`, `SEC-AUTH-01`, `DATA-MIGRATION-01`, `OBS-01`, `CLEAN-01` |

任一 ID 必须有一个主 owner 和至少一个最终验证任务；T16 只汇总证据，不替代 owner 的实现与定向验证。

### T00 — 冻结基线、差距矩阵与并行边界

**Files**

- Modify: `docs/requirements/2026-09-08-notemeld-new-product-interface-matrix-v1.md`
- Create: `docs/superpowers/tests/2026-09-13-cloud-macos-x64-android-agent-release.md`（仅证据索引骨架）
- Modify: `scripts/cloud/validate_product_docs.py`

**Steps**

- [ ] 记录 NoteMeld 与 SDK 的基线 commit、dirty files 和不得覆盖的用户改动。
- [ ] 将 56 个验收 ID 映射到 owner、代码入口、测试、运行环境和证据类型。
- [ ] 为 40 个 scoped feature-registry ID 建立页面/service/authority/permission/state/locator 矩阵。
- [ ] 冻结 lane 文件 ownership、依赖、合入顺序和 artifact registry。
- [ ] 运行文档校验，确认无遗漏、重复 owner 或用旧 Windows 证据替代 macOS 的条目。

**Exit**：56/56 验收项与全部 scoped 页面可在两步内定位；每条并行 lane 可在不修改同一文件的情况下启动。

### T01 — SDK canonical runtime、ABI 和跨端 conformance artifact

**Repository**：`packages/notemeld-agent-sdk`

**Files**

- Modify: `crates/agent-ffi/`
- Modify: `bindings/python/`、`bindings/kotlin/`
- Modify: `bindings/abi-v*.json`、`schemas/`、`fixtures/abi/`
- Modify: `scripts/build-kotlin.sh`、`scripts/test-kotlin.sh`、artifact verification scripts
- Modify: `examples/android-harness/`

**Steps**

- [ ] 冻结 Cloud/Android 需要的 submit/wait/cancel/steer/approval/history/tool/model driver port。
- [ ] 补 Cloud Python binding 与 Android 四 ABI AAR conformance tests；fixture 只证明合同，不冒充真实 Provider。
- [ ] 构建 wheel/AAR，验证 native libraries、ABI/schema/license、manifest、commit 和 SHA-256。
- [ ] 在 SDK 仓独立提交和发布/锁定 artifact；把版本与 hash 交给 NoteMeld。

**Acceptance mapping**：`RUNTIME-CLOUD-01/02`、`RUNTIME-ANDROID-01/02`、`RUNTIME-PARITY-01`、`RUNTIME-ISOLATION-01`、`BUILD-COMPAT-01` 的合同基础。

### T02 — UI contract、页面状态和视觉基线合同

**Files**

- Create: `desktop/frontend/packages/ui-contract/`
- Modify: `docs/new-product/config/feature-registry.json`
- Create: `tests/visual/page-state-matrix.json`
- Create: `tests/visual/locator-contract.json`

**Steps**

- [ ] 将 `tokens.css`、A04 和 `design.md` 收敛为语言中立 token/state/a11y JSON Schema。
- [ ] 冻结 C01-C06、D01/D03/D06/D09、APP01-04、M01-M06 的 route、feature IDs、状态和稳定 locator。
- [ ] 固定视觉 viewport/theme/fontScale/reduced-motion 矩阵和动态内容遮罩规则。
- [ ] 从同一基线 commit 的 `/docs/new-product` 捕获参考图并登记 hash；参考图不是生产 PASS。

**Acceptance mapping**：全部 `UI-*`、`DS-CONTRACT-01`、`DS-CATALOG-01`、`DS-VISUAL-01`。

### T03 — Cloud 配置同步与版本兼容合同

**Files**

- Create: `docs/system/change-spec-cloud-config-sync-v1.md`
- Modify: `docs/system/api-inventory.md`、`data-model.md`、`product-rules.md`
- Create/Modify: Cloud/Desktop/Android contract fixtures and tests

**Steps**

- [ ] 冻结 config snapshot/change/revision/idempotency/conflict/deletion/scope 合同。
- [ ] 冻结 capability negotiation 的 protocol/runtime/schema/client min/max 与 required features。
- [ ] 明确 Provider secret 只经配对/轮换安全通道下发，不进入普通 config snapshot。
- [ ] 用 Cloud、TypeScript、Kotlin 共同 fixture 证明序列化与错误语义一致。

**Acceptance mapping**：全部 `SYNC-*`、`BUILD-COMPAT-01`、`SEC-AUTH-01`、`SYNC-SECRET-01`。

### T04 — 自动化、截图和证据基础设施

**Files**

- Create: `tests/visual/`
- Create: `scripts/acceptance/capture-web.mjs`
- Create: `scripts/acceptance/capture-macos.sh`
- Create: `scripts/acceptance/capture-android.sh`
- Create: `scripts/acceptance/compare-visuals.mjs`
- Create: `scripts/acceptance/verify-release-ledger.py`
- Create: `scripts/acceptance/generate-release-manifest.py`

**Steps**

- [ ] 增加 Playwright Web projects、Compose/UIAutomator screenshot cases 和通用 visual manifest。
- [ ] 每个 case 生成 `reference.png`、`actual.png`、`diff.png` 和脱敏 JSON。
- [ ] 将结构缺失、locator 缺失、overflow、未命名控件设为无容差失败。
- [x] 建立 56 gate 的机器可读 ledger schema，拒绝缺 artifact/commit/device 绑定的证据；RC manifest 进一步绑定制品 SHA-256。

**Acceptance mapping**：`BUILD-EVIDENCE-01`、全部 `UI-*`/`DS-*` 以及最终 Go/No-Go。

### T05 — Cloud canonical runtime、配置 authority 和生产服务

**Files**

- Modify: `cloud/agent.py`、`cloud/app.py`、`cloud/db.py`、`cloud/config.py`
- Modify: `cloud/security.py`、`cloud/workspace.py`
- Modify: `cloud/requirements.txt`、`cloud/Dockerfile`、`cloud/compose.yaml`
- Modify/Create: `desktop/backend/tests/test_cloud_*.py`

**Steps**

- [ ] 用锁定 SDK Python artifact 替换 Cloud 自有 Agent loop，保留 Cloud API/DB/queue 外壳。
- [ ] 实现真实 Provider/tool/approval/lease/recovery adapter 和 canonical event 投影。
- [ ] 实现 T03 的 revisioned config sync、删除、冲突、scope 和兼容协商。
- [ ] 加强 readiness、租户隔离、日志脱敏、备份/迁移和生产容器检查。

**Acceptance mapping**：`BUILD-CLOUD-01`、`RUNTIME-CLOUD-*`、`SYNC-*`、`E2E-CLOUD-CLIENT-01`、`SEC-AUTH-01`、`OBS-01`。

### T06 — macOS x64 本地 runtime、Host 与正式打包

**Files**

- Modify: `desktop/backend/app/agent_host/`
- Modify: `desktop/backend/app/cloud_sync/`、`desktop/backend/app/routers/cloud_sync.py`
- Modify: `desktop/backend/app/agent_host/sdk_artifact_pin.py`
- Modify: `scripts/desktop/packaging/scripts/build-backend-macos.sh`
- Modify: `scripts/desktop/packaging/scripts/build-desktop-macos.sh`
- Modify: `desktop/src-tauri/tauri.macos.conf.json`
- Modify: `.github/workflows/release.yml`

**Steps**

- [ ] 强制注入并校验锁定 SDK wheel；删除源码 fallback 和 release 中的可移植性跳过。
- [ ] 证明主程序、sidecar、ffmpeg/ffprobe 和依赖均为 x86_64 且不引用 Homebrew 路径。
- [ ] 完成 Keychain identity、Host bootstrap/heartbeat、Agent 恢复和本机审批。
- [ ] 建立 Developer ID、notary、staple、Gatekeeper、DMG 安装/升级/回滚硬门禁。

**Acceptance mapping**：`BUILD-MAC-01`、`RUNTIME-MAC-*`、`SEC-IDENTITY-01`、`DATA-MIGRATION-01`、`OBS-01`。

### T07 — Android embedded Agent runtime 与同步客户端

**Files**

- Modify: `android/settings.gradle.kts`、`android/app/build.gradle.kts`
- Create: `android/agent-runtime/`
- Modify: `android/src/main/kotlin/com/notemeld/mobile/MobileApi.kt`
- Modify: `CloudApi.kt`、`MobileLocalStore.kt`、`MainActivity.kt`
- Create: `android/app/src/test/`、`android/app/src/androidTest/`

**Steps**

- [ ] 锁定并消费 T01 AAR，验证 APK 含目标四 ABI native library 和 manifest/hash。
- [ ] 实现 Android model/tool/approval driver 与 durable history/event projection；不得复制 Agent loop。
- [ ] 让 `LOCAL` 只走 embedded runtime；Cloud/Remote 保留明确 adapter，不再用 loopback 伪装本地。
- [ ] 实现 config revision/scope/secret secure store、cancel/steer、进程回收恢复和数据迁移。
- [ ] 在无 USB、无 `adb reverse`、无外部 backend 条件下完成真实 Provider challenge。

**Acceptance mapping**：`BUILD-ANDROID-01`、`RUNTIME-ANDROID-*`、`RUNTIME-ISOLATION-01`、`SYNC-*`、`SEC-IDENTITY-01`、`DATA-MIGRATION-01`、`OBS-01`。

### T08 — 桌面/Web 公共组件包与生产 Cloud Web

**Files**

- Modify: `desktop/frontend/pnpm-workspace.yaml`
- Create: `desktop/frontend/packages/ui-web/`
- Create: `desktop/frontend/apps/cloud-web/`
- Modify: `cloud/Dockerfile`、`cloud/app.py`
- Create: component catalog/unit/a11y/visual tests

**Steps**

- [ ] 建立 `@notemeld/ui-web` 独立 build/test/version/catalog，并迁移所有 requirement primitives。
- [ ] 建立 Cloud Web 独立 production entry、C01-C06 route/deep-link 和真实 API client。
- [ ] Cloud Docker 多阶段构建 Cloud Web dist，设置 asset hash/CSP/cache/deep-link fallback。
- [ ] 删除 production 对 `docs/new-product` mount 的依赖；桌面和 Cloud Web 锁定同一 UI package 版本。

**Acceptance mapping**：`DS-WEB-PACKAGE-01`、`DS-WEB-CONSUME-01`、`DS-CONTRACT/SELECT/ICON/MOTION/CATALOG-*`、`UI-CLOUD-01`、`UI-NAV-01`。

### T09 — macOS 桌面 D/APP 页面生产化

**Files**

- Modify: `desktop/frontend/src/App.tsx`、layouts、shared business components
- Modify: `pages/HomePage/`、`pages/CapabilityCenter/`、`pages/SettingPage/`
- Modify: `pages/Applications/NotesApp.tsx`、`LearningApp.tsx`、`MonitoringApp.tsx`、`RuntimeApp.tsx`
- Modify: related `services/` and `desktop/frontend/tests/`

**Steps**

- [ ] D01/D03/D06/D09 和 APP01-04 全部消费 `@notemeld/ui-web`。
- [ ] 每个 registry feature 连接真实 service/authority，补 loading/empty/running/approval/failure/offline/recovery。
- [ ] 补宽/窄、light/dark、键盘、screen reader、reduced-motion 和深链契约。
- [ ] 禁止页面级重复 primitive、固定成功数字或静态业务数据。

**Acceptance mapping**：`UI-DATA/STATE/MAC/RESPONSIVE/THEME/A11Y/NAV-*`、`DS-WEB-CONSUME-01`、`CLEAN-01`。

### T10 — Android `:ui-core` 与 M01-M06 生产化

**Files**

- Create: `android/ui-core/`
- Modify: `android/settings.gradle.kts`、`android/app/build.gradle.kts`
- Refactor: `MobileSurface.kt`、`MobileSurfaceState.kt`
- Create: Compose UI and screenshot tests

**Steps**

- [ ] 实现 NoteMeld Theme/tokens/icons 和 requirement 所列 Compose primitives/catalog。
- [ ] 拆分 M01-M06 screen/state/navigation，使页面消费 `:ui-core`，业务模型不进入 ui-core。
- [ ] 移除 Unicode/emoji 临时图标和硬编码 token；Select 使用 Bottom Sheet/Listbox。
- [ ] 覆盖返回键、旋转、fontScale 1.0/1.3、light/dark、offline/error/approval 和进程恢复。

**Acceptance mapping**：`UI-ANDROID-*`、全部 Android 相关 `DS-*`、`CLEAN-01`。

### T11 — 设备身份、Grant、LAN/Relay 和 E2E hardening

**Files**

- Modify: `cloud/relay.py`、Cloud device/grant routes
- Modify: `desktop/backend/app/cloud_sync/`
- Modify: `android/src/main/kotlin/com/notemeld/mobile/AndroidRemoteRelay.kt`、`CloudApi.kt`
- Modify: `tests/fixtures/relay-aes-gcm-v1.json`
- Create/Modify: `scripts/release/verify_*` 的新三端版本

**Steps**

- [ ] 统一 handshake/AAD/sequence/request id/receipt/cursor/compatibility contract。
- [ ] 验证 LAN-first、Relay fallback、durable receipt、重连、防重放、限流和 host offline。
- [ ] 验证设备/Grant 撤销立即关闭当前连接并拒绝新连接。
- [ ] 危险工具只允许 Host 审批；拒绝/过期不能 dispatch tool。
- [ ] 对 Cloud DB/WAL/SHM、Redis、日志和审计执行敏感 needle 明文扫描。

**Acceptance mapping**：全部 `E2E-*`、`SEC-IDENTITY-01`、`OBS-01`。

## 6. Final synchronized tasks

### T12 — Barrier B：同步合入、artifact pin 和版本协商

- [ ] 按 SDK →合同/迁移 → Cloud/客户端 runtime →组件库 →页面 →E2E 的顺序合入。
- [ ] 处理 schema/ABI/lockfile 冲突；禁止用复制源码解决跨 lane 冲突。
- [ ] 重建 SDK wheel/AAR、UI package、Cloud image、macOS/Android 制品 pin。
- [ ] 运行兼容矩阵：当前版本、最低支持版本、未来不兼容版本；危险降级 fail-closed。

**Exit**：所有 lane 在同一 integration commit/兼容 artifact baseline 上通过定向测试。

### T13 — 全量自动化、迁移和恢复验证

- [ ] SDK：Rust workspace、Python/Kotlin binding、ABI/artifact strict tests。
- [ ] Cloud：全量 pytest、Redis Relay、多 worker、Docker、真实 Provider smoke。
- [ ] Desktop：后端全量、前端 contracts/lint/build、Tauri/sidecar packaging tests。
- [ ] Android：unit/lint/assemble/bundle/connected tests，检查 APK native libs 与签名。
- [ ] 执行旧版本升级、数据迁移、进程重启、断网、重复请求和并发 session 场景。

**Exit**：自动化零失败；任何 skipped 必须证明与 P0 无关，否则阻塞。

### T14 — 本机/模拟器运行与 UI 截图对比

- [ ] 启动 production-like Cloud Web，Playwright 捕获 C01-C06：1440×960、1024×768、390×844，light/dark/reduced-motion。
- [ ] 在本机运行桌面真实 backend/frontend 纵向流程；随后在 Intel Mac 安装版固定窗口捕获 D01/D03/D06/D09、APP01-04。
- [ ] 启动 API 34 x86_64 AVD，安装候选 APK，逐页捕获 M01-M06 的正常、空、错误、离线和关键运行状态。
- [ ] 生成 reference/actual/diff/manifest，执行结构、locator、overflow、token 和 golden diff；人工复核跨 HTML/Compose 结构语义。
- [ ] 页面或 baseline 有改动后整批重跑；视觉签字期间冻结代码。

**Exit**：所有 scoped page/state 有截图证据，无缺页、缺控件、溢出、错误 token、无名控件或未批准 diff。

### T15 — 真实环境三端纵向验收

- [ ] production-like/候选 Cloud：HTTPS、DB、Redis、真实 Provider、Cloud Web dist、日志审计。
- [ ] Intel Mac：签名、公证、staple、Gatekeeper、安装/升级/冷启动、Keychain、本地 Agent 和 Host。
- [ ] Android 实体机：签名候选、无 `adb reverse` 的 embedded Agent、前后台/进程回收、网络切换和截图。
- [ ] Web→Mac 与 Android→Mac 分别完成 LAN 和 Relay 路径，覆盖审批、撤销、offline、重放和恢复。
- [ ] 扫描 Cloud 明文并核对三端协议/build/runtime/schema 版本。

**Exit**：模拟器证据已由真实设备关键链路补齐；外部签名、设备或 Cloud 条件缺失必须标 `BLOCKED`，不得宣称完成。

### T16 — RC 台账、回滚演练与最终 Go/No-Go

- [ ] 生成不可变 RC manifest，锁定 Cloud digest、macOS DMG/app hash、Android APK/AAB hash、SDK/UI artifacts 和 commits。
- [ ] 将 56 项验收逐项绑定到证据；机器校验必须为 56/56 PASS。
- [ ] 演练 SDK/UI artifact、Cloud schema、macOS updater、Android upgrade 和 Relay protocol 回滚。
- [ ] 由独立验收者复核截图、E2E、安全与迁移证据。
- [ ] 只有零 FAIL/PARTIAL/BLOCKED、零阻塞安全问题时报告“完全没有问题，可以上线”；否则输出精确未通过项和 `NO-GO`。

## 7. Verification command groups

具体命令、预期结果和环境见 Execution Spec。任务实施时至少运行：

- SDK strict suite 与 Kotlin AAR emulator conformance。
- Cloud/Relay/Agent Host 全量定向 pytest、Docker build/readiness 和 production-like smoke。
- Web UI package build/test/catalog/Playwright、desktop frontend contracts/build。
- macOS x64 architecture、codesign/notary/staple/Gatekeeper、安装/升级与真实 Agent。
- Android `:ui-core`、app unit/lint/assemble/bundle/connected tests、签名/native-lib 检查、模拟器与实体机。
- E2E LAN/Relay、安全明文扫描、配置 conflict/revoke/offline/recovery。
- 视觉 reference/actual/diff/manifest 和人工结构签字。

## 8. Risks and rollback

| 风险 | 防护 | 回滚 |
| --- | --- | --- |
| Cloud/Android 再造 Agent loop | SDK conformance + artifact-only dependency | 原子回退上一个已验 artifact；旧 adapter 仅降级，不算上线完成 |
| 并行修改冲突/覆盖脏工作树 | worktree、文件 owner、Barrier 合入 | 停止合入并由 owner 重放提交，不清理用户改动 |
| sync revision 迁移损坏配置 | additive schema、事务、idempotency、备份 | 回退服务代码但保留安全 revision/撤销；禁止恢复已撤销权限 |
| Relay 协议漂移或重放 | 版本协商、共同 fixture、cursor/sequence 测试 | 保留旧协议只读/受控兼容窗；不清 cursor 或私钥 |
| UI 包迁移造成大面积视觉漂移 | token 单一源、逐页面迁移、golden review | 回退 package/module 版本和页面 commit，不回退用户数据 |
| 动态数据造成截图抖动 | 专用测试账号、稳定 seed、仅遮罩动态文本 | 重跑未稳定 case；不得扩大遮罩隐藏真实问题 |
| macOS 没有 Developer ID/公证 | 外部凭证和 Intel 机列为 T15 硬门禁 | 保留上一公证版本；ad-hoc 包不得顶替 |
| Android 模拟器代替真机 | T15 独立实体机 Gate | 保持 BLOCKED，不以 CI smoke 放行 |

## 9. Definition of done

只有同时满足以下条件才完成本计划：

- 需求 56 项 P0 全部 PASS，并绑定同一兼容 RC。
- Cloud、macOS x64、Android 各自真实 Agent runtime 通过，Android 无 loopback 依赖。
- 配置同步、E2E、撤销、审批、恢复和 Cloud 无明文通过。
- C/D/APP/M 全页面由真实服务驱动并消费对应公共组件库。
- Intel Mac 安装版、Android 模拟器与实体机、production-like Cloud 均完成运行验证。
- UI reference/actual/diff 和人工结构签字齐全。
- 全量自动化无 P0 skip，回滚演练成功，最终 ledger 为 56/56 PASS。
