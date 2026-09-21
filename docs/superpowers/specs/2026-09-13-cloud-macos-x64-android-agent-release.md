# Spec：Cloud / macOS x64 / Android Agent 上线执行规格

状态：Planned  
日期：2026-09-13  
Canonical requirement：[`2026-09-13-cloud-macos-x64-android-agent-release.md`](../../requirements/2026-09-13-cloud-macos-x64-android-agent-release.md)  
Execution plan：[`2026-09-13-cloud-macos-x64-android-agent-release.md`](../plans/2026-09-13-cloud-macos-x64-android-agent-release.md)

> 本 Spec 冻结后续实现的模块、协议、文件、测试和证据边界。它不代表这些改动已经实现。

## 1. Current-state decisions

1. Cloud 当前 `cloud/agent.py` 的 Python Agent runner 不是 canonical Rust SDK；目标实现必须改为锁定 SDK artifact 驱动。
2. Android 当前 `MobileApi.streamAgent` 通过 `127.0.0.1` / `10.0.2.2` 调 `/api/agent/v1`；目标 `LOCAL` 必须改为 APK embedded SDK runtime。
3. Cloud production image 当前不包含真实 Web bundle；`docs/new-product` 条件静态 mount 不能用于生产。
4. React `CloudPage` 只注册 `/cloud`，内部 `/cloud/workbench|sessions|people|devices|settings` 深链当前不可达；目标 Cloud Web 必须有独立 router/entry。
5. Web primitives 当前位于桌面应用内部；目标抽取独立 `@notemeld/ui-web`。Android 当前只有 `:app`；目标新增 `:ui-core`。
6. macOS 本机已有 x86_64 构建能力，但当前包为 ad-hoc 签名且 Gatekeeper 拒绝；目标必须 Developer ID 签名、公证、staple 和实机安装通过。

## 2. Repository and artifact boundaries

### 2.1 SDK repository

路径：`../packages/notemeld-agent-sdk`

输出：

- Python wheel：供 Cloud 与 macOS sidecar/Agent Host 消费。
- Android AAR：包含 `armeabi-v7a`、`arm64-v8a`、`x86`、`x86_64` 的 `libnotemeld_agent.so` 和 JNI bridge。
- Artifact manifest：`sdk_commit`、`version`、`abi_version`、`schema_version`、target、library hashes、license inventory。
- Conformance fixtures：submit/wait/cancel/steer/approval/history/tool result/error/event ordering。

SDK 仓独立提交、测试和发布；NoteMeld pin 只引用 artifact version + SHA-256，不使用相对源码路径或 import fallback。

### 2.2 NoteMeld repository

输出：

- Cloud image + Cloud Web dist。
- Developer ID 签名、公证的 macOS x64 app/DMG。
- 固定发布证书签名的 Android APK；若分发渠道需要，同时输出 AAB。
- `@notemeld/ui-web` package artifact 与 Android `:ui-core` module version metadata。
- 同一 RC manifest、视觉 manifest 和 56-gate ledger。

## 3. Runtime contract

### 3.1 Canonical operations

三端 adapter 只能调用 SDK 提供的统一操作：

- create/restore runtime context；
- submit turn；
- wait/poll ordered events；
- cancel turn；
- steer running turn；
- resolve approval；
- provide model/tool results；
- release runtime resources。

统一事件必须至少覆盖 `turn.started`、模型增量、`tool.started`、`tool.result`、`approval.required`、`approval.resolved`、`turn.succeeded|failed|cancelled|interrupted|needs_attention`。一个 turn 只能有一个终态。

### 3.2 Cloud adapter

**Modify**

- `cloud/agent.py`：只保留 Cloud ModelDriver/ToolDriver/Approval adapter；删除或隔离生产自有 loop。
- `cloud/app.py`：session/command/lease worker 调 SDK binding；HTTP 和 durable Cloud queue 仍由 Cloud authority 管理。
- `cloud/db.py`：保存 canonical session/turn/event projection、lease、attempt 和 recovery decision，不复制 SDK 状态机。
- `cloud/requirements.txt`：固定 wheel version/hash 或由 image build 注入并严格校验。

`DeterministicAgentRunner` 仅允许测试 profile；production readiness 检测到该 runner 必须失败。

### 3.3 macOS adapter

**Modify/verify**

- `desktop/backend/app/agent_host/entry.py`
- `desktop/backend/app/agent_host/native_executor.py`
- `desktop/backend/app/routers/agent.py`
- `desktop/backend/app/services/agent_store.py`
- `desktop/backend/app/agent_host/sdk_artifact_pin.py`

sidecar 启动时验证 SDK artifact manifest/hash/ABI/schema；不匹配时 `/ready` 失败并显示可行动诊断。macOS 本地 Agent 即使 Cloud offline 也可运行；Cloud 配置不可用时仅能使用最近有效、未撤销的本地配置。

### 3.4 Android adapter

**Create**

- `android/agent-runtime/build.gradle.kts`
- `android/agent-runtime/src/main/kotlin/com/notemeld/runtime/AgentRuntime.kt`
- `android/agent-runtime/src/main/kotlin/com/notemeld/runtime/ModelDriver.kt`
- `android/agent-runtime/src/main/kotlin/com/notemeld/runtime/ToolDriver.kt`
- `android/agent-runtime/src/main/kotlin/com/notemeld/runtime/RuntimeStore.kt`
- `android/agent-runtime/src/test/`

**Modify**

- `android/settings.gradle.kts`：加入 `:agent-runtime`、`:ui-core`。
- `android/app/build.gradle.kts`：锁定 AAR，依赖两个模块，增加 unit/instrumentation 配置。
- `MobileApi.kt`：不再作为 LOCAL runtime；保留 Host projection/兼容 API 的命名清晰 adapter。
- `MainActivity.kt`：根据 `LOCAL|CLOUD|REMOTE` 注入不同 runtime owner。
- `MobileLocalStore.kt`：持久化 session locator、ordered event cursor、history projection、pending recovery 和 config revision。

Android runtime 不实现第二套 loop。应用进程恢复时以 durable history/event projection 重建 SDK request；已开始但结果未知的外部副作用进入 `needs_attention`，不自动重放。

## 4. Version and capability negotiation

扩展 `GET /v1/capabilities`，响应至少包含：

```json
{
  "protocol": {"name": "notemeld.sync", "current": 1, "min": 1, "max": 1},
  "runtime": {"sdk_version": "<semver>", "abi": 2, "schema": 2},
  "service": {"version": "<semver>", "build_commit": "<40-char commit>"},
  "required_features": ["config_sync_v1", "e2ee_relay_v1", "durable_receipt_v1"]
}
```

客户端在登录后、配对前、Remote connect 前校验交集：

- 无协议交集：阻止连接，展示服务器/客户端版本和升级动作。
- required feature 缺失：阻止对应危险操作，不静默降级。
- SDK ABI/schema 不匹配：本地 runtime readiness 失败。
- 兼容但版本不同：允许连接并记录 negotiated version。

涉及文件：`cloud/app.py`、`desktop/frontend/src/services/cloud.ts`、`desktop/backend/app/cloud_sync/`、`android/.../CloudApi.kt`、`AndroidRemoteRelay.kt` 和共同 fixture。

## 5. Revisioned Cloud config sync

### 5.1 Authority and data set

Cloud 是共享配置 authority。同步对象严格限定为 requirement 第 5.1 节；设备私钥、本机绝对路径、模型权重、缓存、E2E 正文不进入同步。

Provider secret 不进入普通 snapshot/change response。首次配对或轮换走一次性加密 provisioning envelope，端侧成功写入安全存储后只回传 receipt/hash，不回传 secret。

### 5.2 API

新增版本化接口：

```text
GET  /v1/config-sync/snapshot?workspace_id=<id>&after_revision=<n>
POST /v1/config-sync/changes
```

`snapshot` 响应：

```json
{
  "revision": 42,
  "full": false,
  "items": [{"kind": "user_preference", "key": "theme", "value": "dark", "revision": 42}],
  "deleted": [{"kind": "device_grant", "key": "<opaque-id>", "revision": 41}],
  "next_cursor": null,
  "server_time": "<RFC3339>"
}
```

`changes` 请求：

```json
{
  "workspace_id": "<opaque-id>",
  "base_revision": 42,
  "idempotency_key": "<uuid>",
  "changes": [{"kind": "user_preference", "key": "theme", "operation": "set", "value": "light"}]
}
```

结果：

- 成功：返回新 revision 和 canonical changed items。
- revision 冲突：HTTP 409 + current revision；不执行部分写入。
- scope 不足：HTTP 403；不透露越权对象详情。
- 重复 idempotency key：返回第一次的同一结果。
- 删除/撤销：以 tombstone 同步；新鉴权立即查询 authority，不只依赖同步延迟。

### 5.3 Storage

**Cloud**：在 `cloud/db.py` 的 schema migration 中增加 config revision/change/tombstone/idempotency ledger；复用现有 `user_preferences`、`organization_preferences`、models/devices/grants 作为业务 authority，不复制完整业务表。

**macOS**：新增/扩展 `desktop/backend/app/cloud_sync/` 下 config cache/store；secret 写入 Keychain/token store，普通 SQLite 只保存引用、revision 和脱敏元数据。

**Android**：`MobileLocalStore.kt` 保存 snapshot/revision/tombstone；secret 继续由 AndroidKeyStore 包装密钥加密存储。Android backup 必须排除私钥和可解密 secret。

## 6. E2E and remote protocol

共同协议继续使用 Ed25519 identity、X25519 ephemeral key、HKDF、AES-GCM 与完整 envelope AAD。

每个 command/frame 必须包含或绑定：protocol version、session id、sender/recipient device id、request id、monotonic sequence、nonce、ciphertext、expiry。规则：

- Cloud 只校验 envelope、recipient、scope、size/rate，不解密 body。
- `relay accepted` 不是业务成功；Host durable enqueue 后才能返回 `received` receipt。
- 重复 request id 返回原结果；重复/乱序/篡改 frame 拒绝且不 dispatch。
- LAN 和 Relay 使用同一业务 frame；transport 切换不能生成第二个 command。
- Relay 不保存未送达 command 或历史正文；恢复由 Host snapshot/event cursor 补齐。
- Grant/device 撤销关闭当前连接并拒绝新连接。
- dangerous tool 只在 Host durable approval inbox resolve；控制端只显示 waiting/result。

**Modify**

- `cloud/relay.py`、`cloud/app.py`
- `desktop/backend/app/cloud_sync/{runtime,agent_consumer,remote_host,relay_host,queue,lan_transport,lan_auth,e2ee,e2ee_handshake,secure_identity,token_store}.py`
- `android/.../AndroidRemoteRelay.kt`、`CloudApi.kt`
- `tests/fixtures/relay-aes-gcm-v1.json`

## 7. Web UI package and Cloud Web

### 7.1 Workspace layout

```text
desktop/frontend/
├── apps/cloud-web/
├── packages/ui-contract/
├── packages/ui-web/
└── src/                       # desktop business app
```

`pnpm-workspace.yaml` 改为包含根应用、`apps/*`、`packages/*`。

### 7.2 `@notemeld/ui-web`

包内只允许 tokens、primitives、catalog 和通用状态视图，不含 Session/Device/Model/Workspace 业务类型。

最低 exports：ThemeProvider、Button/IconButton、Input/Textarea、Select/Listbox、Checkbox/Switch、Tabs、Card、List/Table、Badge、Alert/Toast、Progress/Skeleton、Empty/Error/Offline、Dialog/Sheet/Drawer、Popover/Tooltip、Navigation/Sidebar/AppBar、ScrollArea、desktop-only Resizable。

包 scripts 至少包含 `build`、`test`、`lint`、`test:a11y`、`test:visual`；桌面与 Cloud Web 必须通过 package dependency 消费同一 version。

### 7.3 Cloud Web application

`apps/cloud-web` 实现独立 browser router：

```text
/cloud/login                 C01
/cloud/access-request        C01
/cloud/workbench             C02
/cloud/sessions/:sessionId?  C03
/cloud/people                C04
/cloud/devices               C05
/cloud/settings/*            C06
```

未经认证深链重定向登录并保留安全 return target；无 scope 返回 403 页面；未知 route 返回 404。C04 管理动作只对有权限用户展示。

`cloud/Dockerfile` 使用 Node build stage 产出 Cloud Web dist，并复制到 runtime image。`cloud/app.py` 只 serve 该 dist，支持 hashed assets/cache/CSP 和 SPA fallback；production 禁止 serve `docs/new-product`。

### 7.4 Desktop migration

以下生产页面逐步替换本地 primitives 为 UI package：

- D01/D03：`pages/HomePage/`、`layouts/AppLayout.tsx`。
- D06：`pages/CapabilityCenter/`、`app-host/ApplicationHost.tsx`。
- D09：`layouts/SettingLayout.tsx`、`pages/SettingPage/`。
- APP01-04：`pages/Applications/`。

页面保留业务组件与 service；不得把业务逻辑搬进 UI package。

## 8. Android UI module

### 8.1 Module layout

```text
android/ui-core/
├── build.gradle.kts
└── src/main/kotlin/com/notemeld/ui/
    ├── theme/
    ├── components/
    ├── state/
    └── catalog/
```

`:ui-core` 是 Android library，只依赖 Compose/Material3 和语言中立 ui-contract 生成物，不依赖 API、storage、Agent/session/device 业务模型。

最低 primitives 与状态按 requirement 第 7.4 节。所有主要触控目标 ≥44dp；Select 为 BottomSheet/Listbox；支持 fontScale、TalkBack semantics、light/dark/reduced motion。Unicode/emoji 临时图标替换为受控矢量资源。

### 8.2 M01-M06

从 `MobileSurface.kt` 拆分为独立 screen 文件；`MobileSurfaceState.kt` 保持导航/state authority，并补 ViewModel/repository seam：

- M01：local/cloud/remote location、session、sync/device/runtime state。
- M02：messages/events/tools/approval/artifacts/send/cancel/steer/transport/recovery。
- M03：account/cloud/model/device/sync/theme/language/notification/security/diagnostic。
- M04：真实 memory CRUD、permission/sync/offline state。
- M05：font preview/system/default/save/revision conflict。
- M06：storage categories/preview/confirm/progress/failure；不删 identity/未同步数据。

## 9. Visual and runtime verification specification

### 9.1 Evidence layout

```text
artifacts/acceptance/<rc>/visual/<platform>/<page>/<case>/
├── reference.png
├── actual.png
├── diff.png
└── manifest.json
```

生成目录不作为源码提交；最终 test ledger 保存 bundle hash、摘要、选定 contact sheet 和安全可分享路径。

`manifest.json` 必含：requirement IDs、feature IDs、page、state、route、viewport/density、theme、fontScale、reducedMotion、OS/device、artifact hash/image digest、commit、reference hash、diff metric、missing locator、reviewer、timestamp、result。

### 9.2 Matrix

**Web/Cloud**

- viewport：1440×960、1024×768、390×844。
- theme：light、dark；关键页面再测 reduced-motion。
- 页面：C01-C06；D/APP 的浏览器纵向预检。

**macOS**

- Intel x64 安装版，固定应用窗口 1440×960 与 1100×780。
- D01、D03、D06、D09、APP01-04。
- light/dark；loading/empty/running/approval/error/offline/complete 中与页面相关的状态。

**Android**

- API 34 x86_64 AVD：portrait/landscape、light/dark、fontScale 1.0/1.3、reduced animation。
- 实体机：安装、前后台、网络切换、local Agent、Remote Agent 和关键 M01-M06 截图。

### 9.3 Comparison rules

- 第一层：locator/feature completeness，任何必需控件缺失直接 FAIL。
- 第二层：prototype reference 与 production 同视口 side-by-side/overlay 人工结构审查；HTML 与 Compose 不要求逐像素相同。
- 第三层：批准后的同平台 production golden 做严格像素 diff。
- UI catalog `maxDiffPixelRatio <= 0.001`；真实页面 `<= 0.01`。字体/GPU 动态区域可按 manifest 遮罩，但 controls/status/navigation/layout 不得遮罩。
- overflow、截断关键含义、错误 token、不可见 focus、无 accessible name、对比度失败均为 FAIL，不受像素容差豁免。

### 9.4 Real-data rule

生产页面截图使用专用测试账号和真实临时数据库/API/runtime。确定性 fixture 只用于组件状态与 golden 稳定性；不能用于 `UI-DATA-01`、真实 Agent、配置同步或 E2E PASS。

## 10. Tests and commands

### 10.1 SDK repository

```bash
cd /Users/hehejie/ai/notemeld-project/packages/notemeld-agent-sdk
bash scripts/check-dev-env.sh --android
cargo fmt --all --check
cargo test --workspace --locked
bash scripts/build-kotlin.sh
bash scripts/test-kotlin.sh
bash scripts/test-sdk.sh --strict
```

并运行 artifact manifest、ABI fixture 和 license verifier；命令名以 SDK 仓实际脚本为准，缺失则在 T01 中补充。

### 10.2 Cloud and Relay

```bash
cd /Users/hehejie/ai/notemeld-project/NoteMeld
python3 -m compileall -q cloud desktop/backend/app/cloud_sync
PYTHONPATH=.:desktop/backend python3 -m pytest \
  desktop/backend/tests/test_cloud_agent.py \
  desktop/backend/tests/test_cloud_backend_slice.py \
  desktop/backend/tests/test_cloud_config.py \
  desktop/backend/tests/test_cloud_runtime.py \
  desktop/backend/tests/test_cloud_sync_protocol.py \
  desktop/backend/tests/test_cloud_relay.py \
  desktop/backend/tests/test_cloud_redis_relay.py \
  desktop/backend/tests/test_cloud_relay_host.py \
  desktop/backend/tests/test_cloud_relay_lifecycle.py \
  desktop/backend/tests/test_cloud_lan_auth.py \
  desktop/backend/tests/test_cloud_lan_authorization.py \
  desktop/backend/tests/test_cloud_lan_transport.py \
  desktop/backend/tests/test_cloud_secure_identity.py \
  desktop/backend/tests/test_cloud_sync_bootstrap.py -q
docker compose -f cloud/compose.yaml config --quiet
docker build -f cloud/Dockerfile -t notemeld-cloud:acceptance .
```

Redis integration 必须使用隔离 `rediss://` 测试实例；production-like smoke 使用真实 Provider readiness，但证据不记录 secret。

### 10.3 Web and desktop frontend

```bash
cd /Users/hehejie/ai/notemeld-project/NoteMeld/desktop/frontend
corepack pnpm install --frozen-lockfile
corepack pnpm --filter @notemeld/ui-web lint
corepack pnpm --filter @notemeld/ui-web test
corepack pnpm --filter @notemeld/ui-web build
corepack pnpm --filter @notemeld/ui-web test:a11y
corepack pnpm --filter @notemeld/ui-web test:visual
node --test tests/*.test.mjs
corepack pnpm test:contracts
corepack pnpm lint
corepack pnpm build
corepack pnpm --filter cloud-web build
corepack pnpm exec playwright test
```

### 10.4 Desktop backend and macOS x64

```bash
cd /Users/hehejie/ai/notemeld-project/NoteMeld
python3 -m pytest desktop/backend/tests/agent_host -q
bash scripts/desktop/run_core_regression.sh
NOTEMELD_TARGET_ARCH=x86_64 \
NOTEMELD_PYTHON_BIN=<x64-python> \
NOTEMELD_AGENT_SDK_WHEEL=<pinned-wheel> \
NOTEMELD_PORTABLE_FFMPEG_DIR=<portable-x64-dir> \
bash scripts/desktop/packaging/scripts/build-desktop-macos.sh
NOTEMELD_PACKAGED_BACKEND=<x64-sidecar> bash scripts/desktop/test-packaged-backend.sh
```

制品检查：

```bash
file <app-binary> <sidecar> <ffmpeg> <ffprobe>
otool -L <app-binary> <sidecar> <ffmpeg> <ffprobe>
codesign --verify --deep --strict --verbose=4 <NoteMeld.app>
xcrun notarytool submit <NoteMeld.dmg> --keychain-profile <profile> --wait
xcrun stapler staple <NoteMeld.app>
xcrun stapler staple <NoteMeld.dmg>
xcrun stapler validate <NoteMeld.app>
xcrun stapler validate <NoteMeld.dmg>
spctl -a -vv --type execute <NoteMeld.app>
spctl -a -vv --type open <NoteMeld.dmg>
```

正式 Gate 必须在 Intel Mac 安装候选 DMG 后执行首次启动、冷启动、退出重启、上一受支持版本覆盖升级、本地 Agent challenge、Keychain identity 和 Remote Host。

### 10.5 Android

```bash
cd /Users/hehejie/ai/notemeld-project/NoteMeld/android
./gradlew --no-daemon \
  :ui-core:testDebugUnitTest :ui-core:lint :ui-core:assembleDebug \
  :agent-runtime:testDebugUnitTest :agent-runtime:lint \
  :app:testDebugUnitTest :app:lintDebug \
  :app:assembleDebug :app:assembleRelease :app:bundleRelease
./gradlew --no-daemon :app:connectedDebugAndroidTest
```

制品/运行：

```bash
<android-sdk>/build-tools/<version>/apksigner verify --verbose --print-certs <apk>
<android-sdk>/cmdline-tools/latest/bin/apkanalyzer files list <apk>
adb install -r <apk>
adb shell am force-stop com.notemeld.mobile
adb shell monkey -p com.notemeld.mobile 1
adb exec-out screencap -p > <actual.png>
```

APK 必须包含目标 ABI 的 Agent/JNI libraries。`RUNTIME-ANDROID-01` 现场执行前关闭 USB 调试/移除 `adb reverse`，断开所有外部 NoteMeld backend，只保留模型所需网络或本地模型能力。

### 10.6 Visual/reference

```bash
cd /Users/hehejie/ai/notemeld-project/NoteMeld/docs/new-product
./start.sh

cd /Users/hehejie/ai/notemeld-project/NoteMeld/desktop/frontend
corepack pnpm exec playwright test --project=cloud-wide --project=cloud-narrow --project=cloud-mobile

cd /Users/hehejie/ai/notemeld-project/NoteMeld
node scripts/acceptance/compare-visuals.mjs --matrix tests/visual/page-state-matrix.json --rc <rc>
```

macOS 用 `scripts/acceptance/capture-macos.sh` 驱动安装版页面和 `screencapture`；Android 用 Compose stable testTag/UIAutomator 导航后由 `capture-android.sh` 调 `adb exec-out screencap`。Android capture 默认按 `locator-contract.json` 的 page/case 映射加载当前页面所需 locator，也可显式传入 `--required-locators` 覆盖；脚本会生成同一设备的 accessibility snapshot，缺少映射、任一 locator 或设备断开都必须 fail-closed。

## 11. Migration and rollback

### 11.1 Data migration

- Cloud config sync 使用 additive migration；旧 preferences/models/devices/grants 保持业务 authority。
- macOS/Android 本地 store 增加 schema version、revision、tombstone 和 recovery state；升级先备份/事务迁移。
- 设备私钥不可导出迁移；alias 损坏或安全存储不可用时要求重新配对，不生成静默新身份覆盖旧身份。
- SDK runtime/schema 升级必须通过历史 session fixture；不可解析状态进入可诊断阻断，不删数据。

### 11.2 Rollback

- SDK：pin 回上一个已验证 wheel/AAR，ABI 不兼容 fail-closed，无源码 fallback。
- Cloud：回退 image digest；数据库只使用向后兼容 migration，撤销/tombstone 不回滚。
- macOS：恢复上一个已公证 DMG/updater manifest，不用 ad-hoc 包替代。
- Android：恢复同签名证书的上一个版本；迁移失败停止升级并保留可恢复副本。
- UI：回退 `@notemeld/ui-web` 或 `:ui-core` 版本与消费者 commit；不复制组件源码临时修补。
- Relay：兼容窗口由 capability negotiation 控制；不清除 sequence/cursor/Grant 来换取连接。

## 12. Evidence and final gate

最终 RC manifest 至少包含：

- NoteMeld commit、SDK commit、runtime/ABI/schema/protocol/config-sync/UI contract versions。
- Cloud image digest 与部署 URL/环境标识。
- macOS app/DMG hashes、Developer ID team、notary submission、Intel Mac/OS。
- Android APK/AAB hashes、签名证书 fingerprint、versionCode/versionName、设备/API/ABI。
- UI package/AAR/wheel hashes与 license inventory。
- 每个测试/截图 bundle hash、运行时间、环境和脱敏结果。

Ledger 必须准确包含 requirement 的 56 个验收 ID，每项只能为 `PASS|FAIL|PARTIAL|BLOCKED`。以下任一情况强制 `NO-GO`：

仓库内的机器校验入口为 `scripts/acceptance/verify-release-ledger.py`；只有它验证出 56/56 PASS 后，`scripts/acceptance/generate-release-manifest.py` 才允许把 Cloud/macOS x64/Android 与 SDK/UI 制品的实际 SHA-256 写入同一 RC manifest。旧 `scripts/release/verify_first_batch_ledger.py` 只服务历史 Windows 首批流程，不得作为本需求的 macOS 证据。

- 缺证据或证据未绑定当前 RC。
- Cloud/Android 仍使用非 canonical/loopback runtime。
- Cloud 发布原型或没有生产 Cloud Web bundle。
- macOS 非 Developer ID、公证、Gatekeeper 通过的 Intel 安装包。
- Android 只有模拟器、没有实体机关键链路。
- 任一 scoped 页面/组件/状态缺失，或视觉 diff 未批准。
- E2E 明文泄露、审批绕过、撤销不生效、重放/重复副作用。
- 任一 P0 测试 skipped、FAIL、PARTIAL 或 BLOCKED。

只有 ledger 机器校验为 56/56 PASS、独立复核完成且无阻塞安全/数据问题时，最终报告才能写“完全没有问题，可以上线”。
