# Change Spec：跨端模型配置协议（notemeld.model-add.v1）三端落地

更新时间：2026-09-20
协议依据：`docs/new-product/config/feature-registry.json` 的 `model_config_contract`（schema `notemeld.model-add.v1`）
交互/逻辑参考：`docs/new-product/assets/model-vendor-registry.js`（22 厂商预设、三协议适配、统一校验、分享载荷编解码）

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`（L29、L37、L57-65、L73、L96：密钥不出后端、运行字段权威、视觉闸门、添加弹窗契约）
- [x] 已阅读 `docs/system/data-model.md`（L51 `providers` 现状、L103 运行字段一次性迁移边界、L143/L222 密钥与能力缓存语义、L290 Cloud 加密列）
- [x] 已阅读 `docs/system/api-inventory.md`（L157-170 桌面 provider/model 端点契约；L556-567 Cloud `/v1/models*` 契约）
- [x] 已阅读 `docs/system/known-pitfalls.md`（L224 MCP list_models 泄 Key、L359-365 GPTFactory/list_models 迁移禁令、L409-413 模型表清空迁移边界、L77-82 cryptography 打包教训）
- [x] 已搜索相关代码（桌面 backend/app/routers|services|db、cloud/app.py|db.py|agent.py、android kotlin 全量勘察）
- [x] 已搜索相关测试（desktop backend/tests、test_cloud_backend_slice.py、frontend contracts、android app/src/test）
- [x] 已确认类似能力：三端原型（D09/C06/M07）+ 共享 registry 已作为 prototype 落地验证，本 spec 是产品化
- [x] 已确认影响本地数据与线上服务：桌面/Cloud SQLite 均需迁移；Cloud pairings 响应结构变化影响已配对端

## 1. 当前系统现状

### 桌面（desktop/backend FastAPI + desktop/frontend React）

- 相关模块：`app/routers/provider.py`、`app/routers/model.py`；`app/services/provider.py`、`app/services/model.py`；`app/db/models/providers.py`、`app/db/models/models.py`；`app/db/{provider_dao,model_dao,provider_schema,model_schema,init_db}.py`；`app/gpt/`（OpenAI 单协议）。
- 相关 API：
  - `POST /api/add_provider`、`GET /api/get_all_providers`（**响应含明文 api_key**）、`GET/POST /api/provider_templates`、`GET /api/get_provider_by_id/{id}`（唯一掩码端点）、`POST /api/update_provider`（仅过滤 None，空串/掩码串会覆盖真实 Key）、`POST /api/connect_test`（实现走 `models.list`，非协议测试端点）。
  - `GET /api/model_list`、`GET /api/model_list/{provider_id}`（实时拉远端）、`POST /api/model_list_by_config`、`POST /api/models`（单个）、`POST /api/models/defaults`、`POST /api/models/probe`、`GET /api/model_enable/{provider_id}`、`GET /api/models/delete/{id}`（GET 删除，前端兼容保留）。
- 数据表：`providers(id,name,logo,api_key 明文,base_url,enabled,created_at)`；`models(id,provider_id,model_name,context_window_tokens 默认4096,max_input_tokens,max_output_tokens,supports_vision,supports_stream,created_at, UNIQUE(provider_id,model_name))`；`model_capabilities`（探测缓存）。
- 前端：`pages/SettingPage/Model.tsx`、`Provider.tsx`、`components/Form/modelForm/Form.tsx`、`AddModelDialog.tsx`（单选+5 运行时字段）、`providerTemplates.ts`（8 个硬编码模板）；`services/model.ts`、`store/{modelStore,providerStore}`、`types/index.d.ts IProvider{apiKey...}`。
- 测试：`tests/test_model_runtime_api.py`、`test_model_runtime_schema.py`、`test_core_model_service_contracts.py`、`test_model_runtime_catalog.py`；前端 `tests/modelRuntimeConfigContracts.test.mjs`。
- 当前限制：
  1. `providers.api_key` 明文落 SQLite；列表/新增响应回显明文（违反 data-model L143、product-rules L96）。
  2. 编辑态以掩码回填输入框，直接保存会用掩码串覆盖真实 Key。
  3. 仅 OpenAI 兼容单协议；无 protocol/vendor_id/auth_type 维度；无 Anthropic/Ollama 拉列表与测试。
  4. 厂商预设仅 8 个且分散在前端；`builtin_providers.json`（8 厂商）零引用；与协议 22 预设不一致。
  5. 模型无 display_name/enabled/is_default/test_status；添加仅单选；上下文默认 4096（协议默认 128000）。
  6. 无分享载荷编解码端点/模块。
  7. 迁移教训（pitfalls L409-413）：`models` 运行字段曾做过"缺列即补列并清空"的一次性迁移，legacy merge 白名单已排除 models。

### 云端（cloud/ FastAPI 单体 + cloud-web）

- 相关模块：`cloud/app.py`（models 五端点 L1268-1396、pairings/confirm L1568-1612、`_runner_for_session` L3134-3165、SSRF L3168-3197、鉴权依赖 L2518-2531）、`cloud/db.py`（SCHEMA + init 迁移 L207-281）、`cloud/agent.py`（仅 OpenAI 兼容 runner L47-149）、`cloud/security.py`（Fernet L11-24）。
- 数据表：`models(id,user_id FK,name,provider,model,base_url,api_key_ciphertext,enabled,is_default,created_at,updated_at)`——扁平、**user_id 私有**；`organizations`（单 default）、`organization_members(owner/admin/member)`。
- API：`POST /v1/models/discover`（白名单 {openai-compatible,openai,deepseek,volcengine}，SSRF+httpx 12s）、`GET /v1/models`（附加 has_api_key/credential_status）、`POST /v1/models`（首个自动默认）、`PATCH /v1/models/{id}`（exclude_unset）、`DELETE /v1/models/{id}`。无测试连接端点；models 路由无组织/角色校验。
- **`POST /v1/pairings/confirm` 响应 `model_bundle` 含明文 api_key**（L1609/1612，审计 credentials_sent L1611）。
- runner 仅认 `provider IN ('openai','openai-compatible')`，按 session 取模型行并解密。
- cloud-web：`CloudModelForm.tsx`（4 预设、全 openai-compatible、Promise.all 逐条 POST）、`CloudModelList.tsx`、`services/cloud.ts`（CloudModel L115-125）。
- 测试：`desktop/backend/tests/test_cloud_backend_slice.py`（密钥不泄漏 L564-581、默认 L584、discover L599-637、runner L659-715、组织 admin 先例 L86-95）。
- 当前限制：无 providers 两级表、无 organization 共享；无 anthropic/ollama；无 test；配对下发明文 Key。

### 安卓（android/ Kotlin 纯 Compose）

- 相关模块：主源码在 `android/src/main/kotlin/com/notemeld/mobile/`（`MobileLocalStore.kt` 280 行 object 全量 SharedPreferences+JSON；`MobileSurfaceState.kt`；`MobileSurface.kt` ~925 行，ModelSettingsScreen L535 只读、ModelAddSheet L908 纯静态 testTag 骨架；`CloudApi.kt` 440 行 HttpURLConnection+org.json，PairedModel 含 apiKey 字段，AndroidPairedModelStore 只写不读；`EmbeddedLocalAgent.kt` 硬编码 POST /v1/chat/completions 直读 prefs、第 4 套 Keystore LocalProviderSecretStore；`ModelPairingScanner.kt` 仅识别 `notemeld://pair?code=`）。
- 零 SQLite/Room、零 OkHttp/Retrofit、minSdk 26；构建强制 `NOTEMELD_AGENT_SDK_AAR` + SHA-256；三语文案有完整性单测。
- 当前限制：模型配置不落库（SaveModelDraft 仅 append 名字+toast）；无厂商注册表/拉取/测试/分享；无深链 intent-filter；EmbeddedLocalAgent 单协议直读 prefs。

## 2. 本次目标

依据 `model_config_contract` 与用户四项决策，完成三端真实产品代码落地：

1. **桌面**：Provider/Model 两层数据补齐协议字段；`api_key` 改为 **Python Fernet 加密列**（用户决策），列表/新增/更新永不回显明文，编辑留空保留、掩码串不覆盖；内置 22 厂商预设（TS 化 registry 模块，单一来源）；三协议（openai-compatible / anthropic-messages / ollama）拉取模型列表与协议规定的测试端点；模型多选批量保存、每模型独立 context_window（512–4,000,000，默认 128000）、display_name/enabled/is_default/test_status；分享 URI 编解码（后端代理编解码或前端纯函数 + 后端校验端点）。
2. **云端（完整两级迁移，用户决策）**：新建 `providers` 表、`models` 挂 `organization_id` + provider_id 两级；启动时幂等回填（按旧行 user_id+provider+base_url 去重生成 provider 行，保留 model 行与默认/启用状态，旧 user_id 列保留一个版本作回滚参照）；组织目录 owner/admin 可写、member 只读；三协议 discover + 新增 test 连接端点；runner 按 provider.protocol 分派（新增 anthropic/ollama 适配，ollama 在 Cloud 侧仅允许配置/测试，实际 worker 网络可达性另行标注）。
3. **配对下发禁令（用户决策原文）**："这个不允许发送 api_key，只需要把模型名称和 id 发送客户端和移动端。这时候客户端回传模型 id。" `/v1/pairings/confirm` 的 `model_bundle` 移除明文 api_key（及任何凭据字段），仅下发模型 id/名称/provider/base_url 等元数据；桌面/安卓发命令时回传 `model_id`；Cloud 在 `_runner_for_session`/命令执行侧按 model_id JOIN providers 解密凭据。审计从 credentials_sent 改为 models_metadata_sent。
4. **安卓**：新建端侧 SQLite 两表（`mobile_model_providers`/`mobile_models`，SQLiteOpenHelper）+ 统一 Keystore SecretStore（alias + 密文 + key_ref，不再新增第 5 套重复实现），DB 仅存 key_ref；旧 SharedPreferences 标量一次性迁移；Kotlin 版厂商注册表（22 预设）与三协议网络（HttpURLConnection）；分享 payload base64url 编解码 + 扫码分流（pair/model-add 互斥）+ `notemeld://model-add` 深链；ModelSettings 正式页与 ModelAddSheet 完整 CRUD（多选/显隐/校验/测试/分享导入）；EmbeddedLocalAgent 改查表 + key_ref + 协议分派。三语文案同步。

- 必须保留的旧行为：
  - 桌面统一响应包装 `{code,msg,data}`、HTTP 200；`GET /api/models/delete/{id}` 旧路径保留；删除模型同事务删 `model_capabilities`，不删 Provider/笔记/usage；`models` 运行字段（context_window/supports_vision/supports_stream）权威语义与视觉闸门不变；list_models 仍走同步 OpenAI client 路径（pitfalls L359-365，GPTFactory 不删）；MCP `list_models` 脱敏。
  - Cloud 旧 `/v1/models*` 请求/响应字段对现有 cloud-web 与已发布桌面保持兼容（新字段增补、不改既有字段含义）；首个模型自动默认；SSRF/trust_env=False 不变。
  - Auto 仍是路由策略、位于选择列表顶部，不可作为模型记录。
  - 安卓 M02 会话链路、配对 pair?code 流程不受 model-add 分流影响。

## 3. 明确不做

- 不做：iOS / Harmony 的模型配置产品化（本 spec 仅安卓；协议层已跨端共享）。
- 不做：AWS Bedrock 原生接入（registry 标 unsupported，v1 仅经 OpenAI 兼容网关）。
- 不做：Rust keyring/Keychain 桥接（桌面密钥按决策用 Python Fernet 加密列；desktop/src-tauri keyring 依赖不动）。
- 不做：浏览器直连第三方 Provider（拉取/测试一律桌面后端、Cloud 后端、安卓原生代理；cloud-web/desktop frontend 不直发第三方）。
- 不做：删除 GPTFactory/UniversalGPT 或把 list_models 迁到 notemeld-ai（pitfalls 明令）。
- 不做：Cloud 侧 ollama 的 worker 真实出网执行保证（localhost Ollama 对 Cloud 无意义；允许在目录配置/测试局域网可达地址，执行失败按既有 fail-closed 中文错误处理；不新增 SSRF 例外）。
- 不做：模型用量、Wiki、会话、笔记等无关重构；不清理 `builtin_providers.json` 之外的历史文件（该死文件本次删除或标注）。
- 暂不处理：原型 c06-live.js L16-18 标签索引错位（用户未确认，不属本次范围）。
- 后续可选：组织目录变更审计明细、provider 级 usage 聚合、模型能力自动探测刷新（probe 缓存）接入新协议。

## 4. 冲突分析

- 与 product-rules：一致且强化（L29 扫码不带 Key、L37/L96 密钥不暴露、L57-65 运行字段权威/视觉闸门保持）。新校验上下文默认值 128000 与 L59"本地目录安全 fallback 4096"分属两个语义（前者新表单默认建议值，后者未命中目录的兜底），代码中保留 4096 fallback 路径。
- 与 data-model：`providers`/`models` 字段语义扩展，需同步更新 L51、L103、L143、L222；密钥由明文改加密列属于安全修复，旧明文行启动时一次性惰性/批量加密迁移。
- 与 api-inventory：桌面端点路径不变、字段增补；Cloud `/v1/models*` 增补两级路由（见第 8 节兼容策略）；pairings/confirm 响应删字段是**有意的破坏性安全变更**，调用方（安卓 CloudApi.confirmPairing、桌面配对消费）同次改造。
- known-pitfalls：不重新引入——迁移不把 models 纳入 legacy 白名单；加密依赖在桌面 requirements 显式声明 `cryptography`（pitfalls L77-82，确认现状已声明则保持）；MCP/list_models 继续脱敏；不复制第二套加密实现（云端复用 security.py，桌面新增独立轻量 fernet 模块，端侧 E2EE crypto 不复用于模型密钥但 Keystore 内部统一一套）。
- 运行模式：影响桌面源码与 PyInstaller 打包（新增 `cryptography` 收集核查）；不影响 CLI/MCP 入口签名。
- 打包/迁移/回滚：三端 SQLite 均为 additive 迁移（加列/加表/回填），保留旧列一个版本；安卓 DB version 升级走 onUpgrade。

## 5. 影响范围

- 桌面后端文件：
  - `desktop/backend/app/db/models/providers.py`、`models.py`；新增/改 `db/provider_schema.py`、`model_schema.py`、`init_db.py`；`db/{provider_dao,model_dao}.py`。
  - 新增 `app/security/model_secret.py`（Fernet 密钥派生与加解密，密钥文件 0600 落运行数据目录，复用 storage_paths）。
  - `app/routers/provider.py`、`app/routers/model.py`；`app/services/provider.py`、`app/services/model.py`。
  - 新增 `app/services/vendor_registry.py`（22 预设 Python 侧镜像，供测试/拉取协议分派；单一事实以 TS registry 为准，后端内置最小必要预设表或加载打包 JSON）。
  - 三协议适配：新增 `app/gpt/provider/anthropic_messages_provider.py`、`ollama_provider.py`（list + test），OpenAI 兼容补 test 走 chat/completions max_tokens=1。
  - 分享：`app/routers/model.py` 增 `POST /api/model_share/decode`（校验+解析，不触网）；编码可前端纯函数。
- 桌面前端文件：
  - 新增 `src/utils/modelVendorRegistry.ts`（从 model-vendor-registry.js 移植：常量+纯函数，无 window 依赖）。
  - `pages/SettingPage/Model.tsx`、`Provider.tsx`、`providerCard.tsx`、`ProviderNameCombobox.tsx`；`components/Form/modelForm/Form.tsx`、`AddModelDialog/`（改多选+新字段+分享导入）；删除/停用 `providerTemplates.ts` 8 模板改用 registry。
  - `services/model.ts`、`services/provider.ts`、`store/modelStore`、`store/providerStore`、`types/index.d.ts`。
- Cloud：`cloud/db.py`（建表/迁移/回填）、`cloud/app.py`（两级路由/鉴权/discover/test/pairings/runner 查询）、`cloud/agent.py`（协议分派）、`cloud/security.py`（复用，不改）。
- cloud-web：`CloudModelForm/CloudModelList`、`services/cloud.ts`、类型；成员只读态、分享导入。
- 安卓：
  - 新增 `data/ModelDatabase.kt`（SQLiteOpenHelper + 两表 + onUpgrade 迁移）、`data/ModelRepository.kt`、`security/LocalModelSecretStore.kt`（统一 Keystore，整合 LocalProviderSecretStore 职责）。
  - 新增 `data/VendorRegistry.kt`、`net/ModelProtocolClient.kt`、`share/ModelSharePayload.kt`（base64url+schema 校验）。
  - 改 `MobileLocalStore.kt`（一次性迁移标量后只读兜底）、`MobileSurfaceState.kt`、`MobileSurface.kt`（ModelSettings/ModelAddSheet）、`CloudApi.kt`（PairedModel 去 apiKey、命令带 model_id）、`EmbeddedLocalAgent.kt`、`ModelPairingScanner.kt`（分流）、`MainActivity.kt` + AndroidManifest（深链）、`MobileStrings.kt`（三语）。
- 测试：桌面 backend pytest 新增/更新；前端 contracts 文本断言同步；Cloud slice 测试新增；安卓 app/src/test JVM 单测。
- 文档：data-model.md、api-inventory.md、product-rules.md（必要处）、feature-registry.json maturity/status 回写。

## 6. 实施方案

顺序（用户决策）：**桌面 → 云端 → 安卓**。每个仓库独立测试、独立提交。

### 6.1 桌面后端

1. 密钥模块 `model_secret.py`：首次启动在运行数据目录生成 0600 密钥文件（`os.open`+fsync+原子替换，遵循 pitfalls L82）；Fernet key=base64(urlsafe_b64encode(sha256(master))) 或直接 Fernet.generate_key 存文件；提供 encrypt/decrypt/mask/has。
2. schema 迁移（幂等、additive）：
   - `providers` 增列：`display_name TEXT`、`vendor_id TEXT DEFAULT 'custom'`、`protocol TEXT NOT NULL DEFAULT 'openai-compatible'`、`auth_type TEXT NOT NULL DEFAULT 'api_key'`、`api_key_ciphertext TEXT`、`updated_at TEXT`；旧 `api_key` 列保留但停止读写（迁移时把明文逐行加密入新列，成功后置空或保留一版；本次采用：加密后清空明文列内容，列保留避免表重建）。
   - `models` 增列：`display_name TEXT`、`enabled INTEGER NOT NULL DEFAULT 1`、`is_default INTEGER NOT NULL DEFAULT 0`、`test_status TEXT NOT NULL DEFAULT 'unknown'`、`updated_at TEXT`；`model_name` 保留，协议字段 `model_id` 以 model_name 兼容（新增 model_id 列，回填=model_name，后续唯一约束基于 provider_id+model_id；为避免表重建，唯一去重在 DAO 层校验 + 新建部分唯一索引 IF NOT EXISTS）。
   - 迁移挂 `init_db.ensure_*`，启动事务内完成；重复启动不清空任何行（区别于 L103 的历史一次性边界）。
3. provider 路由：请求/响应模型切 display_name/vendor_id/protocol/base_url/auth_type + `has_api_key`；新增/更新响应只有掩码状态；更新时空串与等于当前掩码的提交一律视为"未改"（exclude_unset 语义）；删除返回保留 GET 旧风格不强制。
4. 三协议：
   - openai-compatible：list 用既有 `client.models.list()`；test 新增 `POST {base_url}/chat/completions`（model 取首个/传入 model，max_tokens=1，非流式，超时短）。
   - anthropic-messages：list 返回内置 3 模型目录；test `POST {base_url}/v1/messages`，header `x-api-key`+`anthropic-version: 2023-06-01`，body max_tokens=1。
   - ollama：list `GET {base_url}/api/tags`；test 同端点（免 Key）；base_url 允许 http localhost/局域网。
   - 均经后端 httpx/OpenAI client，浏览器不直连；异常返回脱敏中文 message，不回显 provider payload。
5. 模型批量 API：新增 `POST /api/models/batch`（provider_id + 多选模型 [{model_id, display_name?, context_window, modalities?}]，同事务 upsert 去重，返回新增/已存在计数）；既有 `POST /api/models` 保留并复用同一 service；设默认 `POST /api/models/default`（每 Provider/全局至多一个——协议 scope 为设备级唯一默认，沿用现有默认语义）。
6. 分享 decode 端点：解析 base64url → 校验 s/v、拒绝含 api_key 字段、vendor 预设解析（custom 带 name/protocol/url），返回结构化表单预填；不自动保存。
7. 错误处理：400/404/409 沿用 wrapper code；日志严禁 Key/密文/分享载荷外的凭据。
8. 并发/超时：迁移在启动单连接事务；三协议请求超时 8s（list）/12s（test），失败不重试写操作。

#### 6.1.1 回归测试暴露的真实缺陷与修复（红-绿循环，2026-09）

1. **SQLite `ADD COLUMN` 不支持非常量默认值**：初版迁移对 providers/models 的 `updated_at` 写 `... DEFAULT CURRENT_TIMESTAMP`，旧库迁移直接报 `Cannot add a column with non-constant default`。修复（[provider_schema.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/desktop/backend/app/db/provider_schema.py)、[model_schema.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/desktop/backend/app/db/model_schema.py)）：DDL 只加可空列 `updated_at DATETIME`，同一迁移事务内再 `UPDATE ... SET updated_at = CURRENT_TIMESTAMP WHERE updated_at IS NULL` 回填。
2. **裸 SQL 的 LIKE 模式触发 SQLAlchemy 绑定参数解析**：ollama 协议回填语句中 `base_url LIKE '%:11434%'` 的 `:11434` 被当作绑定参数（`A value is required for bind parameter '11434'`）。修复：改为 `LIKE :port_pattern` / `:loopback_pattern` 并以参数字典传 `"%:11434%"`、`"%//127.0.0.1:11434%"`。
3. **协议切换时密钥校验被名称/地址启发式绕过（安全缺陷）**：旧 `_requires_api_key` 先判 ollama 协议免 Key，但其余协议会 fallthrough 到 name/base_url 启发式，导致名为 "Ollama" 的供应商切到 openai-compatible 时不要求 Key。修复（[provider.py](file:///Users/hehejie/ai/notemeld-project/NoteMeld/desktop/backend/app/services/provider.py)）：显式 protocol 非空时直接按协议判定（仅 ollama 免 Key），名称/地址启发式只保留给无协议标记的历史行。

文档校验侧的连带修正：`scripts/cloud/validate_product_docs.py` 的绑定选择器检查从"仅页面 HTML"扩展为"页面 HTML + 其引用的本地 JS 资产"（选择器由脚本动态渲染）；`model.share-schema` 锚定页由不存在该 UI 的 A03 改为 D09；`C06.model-catalog` 状态由 prototype 改为 needs_backend（云端两级表/组织鉴权未落地前，表与路由检查按未就绪处理，不得伪装已实现）。

### 6.2 桌面前端

1. `modelVendorRegistry.ts`：PROTOCOLS、MODEL_VENDORS(22)、ANTHROPIC_BUILTIN_MODELS、validate、buildSharePayload/encode/decode（纯函数，可直接被后端测试对齐）。
2. 统一添加/编辑 Dialog（替换 AddModelDialog 单选流）：厂商网格/下拉 → 带出 protocol/base_url（可高级改写，未知厂商 url 留空提示不臆造，Bedrock 置灰）→ Key 显隐 + "已保存"占位（编辑留空保留）→ 拉列表多选 chips（Anthropic 内置目录）/手动添加 → 每模型 context_window（默认 128000，范围即时校验）→ 测试连接（结果写 test_status）→ 批量保存。
3. 编辑回显：从新 GET 详情取元数据 + has_api_key；保存不带掩码。
4. 分享：行内/Provider 级生成 URI（前端编码）；添加入口支持粘贴 URI/JSON → decode 端点校验 → imported 态。
5. store/types 全量 snake/camel normalize 梳理；保留旧字段读取兜底一版。
6. ready gate：沿用现有 modelStore 加载态，不新增 mount 无条件请求（pitfalls L210）。

### 6.3 云端

1. `db.py` 迁移（init 内、foreign_keys=OFF 事务、幂等）：
   - 新表 `organizations` 已存在；新增 `providers(id, organization_id FK, display_name, vendor_id, protocol, base_url, auth_type, api_key_ciphertext, created_by, created_at, updated_at, UNIQUE(organization_id,display_name))`。
   - `models` 增列 `organization_id TEXT`、`provider_id TEXT`、`display_name TEXT`、`context_window INTEGER DEFAULT 128000`、`modalities TEXT`、`test_status TEXT DEFAULT 'unknown'`、`model_id TEXT`（回填=model）、`updated_at`；旧列 user_id/provider/model/base_url/api_key_ciphertext 保留一版。
   - 回填：对旧 models 行按 (user_id, provider, base_url) 去重 INSERT OR IGNORE providers（created_by=user_id，凭据取该组首条 ciphertext；随后 models 行 provider_id 指向新 provider，organization_id=用户所属组织 id）；每个用户首个模型迁移为组织默认时冲突解决：只保留每组织一个 is_default（取最早 created_at）。
   - 新 SCHEMA 建库直接为两级结构。
2. 路由（`/v1/catalog/providers`、`/v1/catalog/models` 新路径承载两级 CRUD；旧 `/v1/models*` 保留为兼容 facade——读走组织目录映射为旧字段，写仅限服务端内部/标记 deprecated，cloud-web 本次切新路径）：
   - 鉴权：目录写 owner/admin（Depends 组织角色，仿 L1036-1090），member 只读（403 分类错误）；发现/测试端点组织成员可用（填写中的临时 Key 仅内存）。
   - `POST /v1/catalog/providers`、`PATCH .../{id}`（空 Key 保留）、`DELETE`；`POST /v1/catalog/providers/{id}/models/batch`、PATCH/DELETE model、`POST .../default`。
   - `POST /v1/catalog/discover`（扩协议白名单 anthropic-messages/ollama；SSRF 对 ollama 仅允许 localhost——Cloud 部署中 localhost 即容器自身，默认拒绝非 https 公网，保持现有私网拒绝）。
   - 新增 `POST /v1/catalog/test-connection`（三协议，不落库）。
3. pairings/confirm：model_bundle 仅 `{model_id, model(display name), provider, base_url?, protocol?}`，**无 api_key/ciphertext/credential_status**；审计 action 字段改名 `models_metadata_sent`；移除全量解密模型的 L1594 逻辑（bundle 不需要）。
4. 命令/runner：桌面/安卓命令载荷携带 `model_id`；`_runner_for_session` 按 model_id JOIN providers 解 protocol/base_url/解密 Key；会话创建时 model_id 必须属于调用者组织目录（member 可读即可用）；Auto 路由策略保持。
5. agent.py：runner 按 protocol 分派——openai-compatible 沿用；新增 `AnthropicMessagesRunner`（/v1/messages 转换 messages 最小子集）与 ollama（/api/chat）；不支持协议 fail-closed。
6. cloud-web：接 registry（前端纯函数同桌面实现），22 厂商/多选/测试/分享导入/只读态。

### 6.4 安卓

1. DB：`ModelDatabase(version=2 概念版本，全新 DB 从 1 起)` 两表；DAO 纯 JVM 可测（接口注入 SQLiteDatabase/或把校验/去重逻辑写成纯函数）。
2. SecretStore：统一一个 Android Keystore AES/GCM 实现，alias 按 `model_provider_<id>`，DB 存 key_ref=alias 与非空标记；迁移旧 LocalProviderSecretStore 条目（复用其 prefs 读出后写入新 alias，再清旧 prefs 键）；AndroidPairedModelStore 补读能力或明确仅保存配对元数据（无 Key 可存后，apiKey 字段删除）。
3. 旧 prefs 标量（localModelBaseUrl/Name/Context/availableModels/draft*）首次启动迁入 DB，迁移完成写 pref flag；之后这些键只读兜底/删除写入路径。
4. VendorRegistry.kt：22 预设常量 + protocol 枚举 + 内置 anthropic 目录；ModelProtocolClient（HttpURLConnection，cleartext 仅对 localhost/局域网，配 networkSecurityConfig）；ModelSharePayload base64url（android.util.BaseBase64 URL_SAFE|NO_PADDING|NO_WRAP）编解码 + 严格 schema（拒绝 apiKey）。
5. 扫码分流：识别 host=pair→既有配对；host=model-add→解析进 ModelAddSheet imported；互不识别、互相报错提示；Manifest 加 VIEW/BROWSABLE `scheme=notemeld host=model-add`（顺带 host=pair），MainActivity onNewIntent。
6. UI：ModelSettings 改分组列表（Provider→模型 chips、默认标记、启用开关、测试状态、编辑/删除/分享）；ModelAddSheet 八步流程压缩为 Sheet 分段（厂商网格→Key/URL→拉取多选→上下文→测试→保存）；失败态/空态/三语；testTag 沿用既有骨架并补新交互 tag。
7. EmbeddedLocalAgent：按 selected model 的 provider_id 查 DB → key_ref 取密文解密 → protocol 分派请求（保留超时 8s/60s 与现有签名）。
8. CloudApi：confirmPairing 模型消费改为仅元数据；发送会话/命令带 model_id。

## 7. 数据变更

- 桌面 SQLite：
  - providers 加 6 列；api_key 明文行迁移为 `api_key_ciphertext` 并清空明文；新增密钥文件（运行数据目录，不进库不进备份导出明文）。
  - models 加 5 列 + model_id 回填；不删行、不清表。
  - 回滚：新列保留无害；旧代码读到明文列已清空 → 回滚文档要求用户重新填写 Key（或回滚前未清空版本：本次采用**迁移后明文置空**，回滚影响明确告知）。
- Cloud SQLite：
  - 新增 providers；models 加列回填；旧列保留一版；可重复执行（IF NOT EXISTS + PRAGMA table_info 守卫 + UPDATE...WHERE provider_id IS NULL 幂等回填）。
  - 回滚：旧代码读旧列（user_id/provider/model/ciphertext 均保留），目录两级新代码停写后旧会话仍可跑；新列忽略。
- 安卓 SQLite：新库两表 + prefs→DB 一次性迁移 + flag；卸载/清数据重来；无用户文件影响。
- 不清理脏数据；不影响笔记/会话/usage 历史。

## 8. 接口变更

### 桌面（路径不变，字段增补，wrapper 不变）

- `POST /api/add_provider` / `POST /api/update_provider`：请求新增 display_name/vendor_id/protocol/auth_type；api_key 为空=保留；响应删除明文 api_key，新增 has_api_key/credential_status。
- `GET /api/get_all_providers`：**破坏性安全修复**——移除 api_key 明文字段（前端同次改造；MCP 不消费此端点）。
- 新增：`POST /api/models/batch`、`POST /api/models/default`、`POST /api/model_share/decode`；`POST /api/connect_test` 改协议测试语义（入参增 protocol/model_id）。
- 模型响应项新增 display_name/enabled/is_default/test_status/model_id；保留 model_name/context_window_tokens/supports_vision/supports_stream/capabilities。
- MCP：无签名变化；`list_models` 继续脱敏（加测试断言）。
- 更新 api-inventory.md L157-170。

### Cloud

- 新增 `/v1/catalog/providers*`、`/v1/catalog/models*`、`/v1/catalog/discover`、`/v1/catalog/test-connection`（信封 {code:0,msg,data} 或既有错误样式，实现时对齐同文件风格）。
- `/v1/models*` 保留为兼容 facade（内部映射组织目录）；C03 会话列表改读组织目录。
- `POST /v1/pairings/confirm`：**响应 model_bundle 移除 api_key**（破坏性安全变更，同次改两端调用方）；新增 model_id 稳定标识。
- 命令载荷：新增 model_id 字段（模型选择从 name 改 id 优先，name 兼容一版）。
- 更新 api-inventory.md L556-567 与 pairings 节。

### 安卓

- 无 HTTP API 变更（消费 Cloud）；端侧新增内部 DB/深链：`notemeld://model-add?d=...` intent-filter。

## 9. UI/交互变更

- 桌面：设置-模型页 Provider 卡片展示协议徽标/已保存密钥状态/测试状态；添加/编辑统一 Dialog（八步）；分享菜单（复制 URI）+ 添加入口"导入配置"；删除确认；失败保留输入。
- Cloud：C06 模型面板同构（模态），member 全表单只读 + 行内"分享"；管理员可见写操作。
- 安卓：M07 从只读列表升级为可 CRUD 页面；+ 进入 ModelAddSheet；扫码入口二分流（扫配对码/扫模型配置）；空态引导、测试成功/失败行内反馈、三语。
- 可访问性：密钥输入 password 视觉变换、开关 contentDescription、testTag 同步。
- 桌面/浏览器差异：cloud-web 与桌面前端均不直连第三方（经各自后端），无 CORS 差异。

## 10. 测试方案

- 桌面后端（`PYTHONPATH=desktop/backend python3 -m pytest desktop/backend/tests -q`）：
  - 迁移：新列/回填/重复启动幂等/明文已清空不影响其他表；断言旧模型行与 capabilities 保留。
  - 密钥：add/list/update/get 响应四端点无明文；留空保留；掩码串提交不覆盖；密钥文件 0600；日志无 Key。
  - 三协议：httpx mock 下 /models、/api/tags、anthropic 内置目录与三处 test 端点 URL/header/body 断言；超时/失败脱敏。
  - batch 去重/默认唯一/context 范围校验；分享 decode（合法/非法 schema/含 Key 拒绝/配对码拒绝）。
  - 回归：test_model_runtime_api/schema/catalog/core_contracts 全绿；GPTFactory 回滚断言不被破坏；MCP list_models 脱敏测试。
- 桌面前端：`pnpm test:contracts` + `node --test tests/*.test.mjs`；更新 modelRuntimeConfigContracts 文本断言到新字段；registry 纯函数单测（编解码往返、22 预设完整性、校验边界）；`pnpm build`。
- Cloud（`PYTHONPATH=.:desktop/backend python -m pytest desktop/backend/tests/test_cloud_*.py desktop/backend/tests/test_first_batch_*.py -q`）：
  - 两级表迁移/回填/幂等/旧列保留；组织角色（owner/admin 写、member 403、跨组织不可见）；discover/test 三协议 SSRD 断言；pairings 响应全字段扫描不含 api_key/ciphertext（递归断言）；命令带 model_id 的 runner 凭据解析；旧 /v1/models facade 兼容；旧密钥不泄漏测试继续绿。
- 安卓：`:app:testDebugUnitTest` JVM 单测（无 Robolectric）：VendorRegistry 常量/协议、SharePayload 编解码与拒绝 apiKey/拒绝 pair 码、DB 迁移 SQL（用纯 SQL 夹具或抽取 SQL builder 为 JVM 纯函数）、校验范围；MobileStringsTest 三语完整性更新。**完整 Gradle assemble/插桩在缺 NOTEMELD_AGENT_SDK_AAR 时报 blocked，不伪造通过。**
- 手动验证：桌面真实加一个 OpenAI 兼容 Provider + Ollama 本地多选；Cloud admin/member 两账号；安卓（有 AAR 构建条件时）扫码导入闭环。

## 11. 验收标准

- [ ] 桌面：所有 provider/model 响应与日志中 grep 不到任何真实 api_key；编辑留空保存后连接仍可用；掩码回填保存不覆盖。
- [ ] 桌面：22 预设可选并带出正确 protocol/base_url；三协议拉列表与测试端点与协议文档逐一吻合；多选模型批量入库、同 Provider 去重、上下文范围 512–4,000,000、默认 128000。
- [ ] 桌面：重启两次后数据完好、迁移幂等；旧笔记生成/聊天链路回归通过；视觉闸门测试通过。
- [x] Cloud：旧库升级后 providers/models 回填正确且可重复执行；组织 member 只读、admin 可写、跨组织隔离。
- [x] Cloud：`/v1/pairings/confirm` 响应及审计不含任何明文凭据（测试递归断言）；桌面/安卓仅持 model_id 即可让 Cloud 成功跑通一条命令。
- [x] Cloud：旧 `/v1/models`  facade 不破坏现有调用；SSRF 防护对新协议同样有效。
- [x] 安卓：Provider/模型落 SQLite、密钥入 Keystore（重启后仍可用，随 app 启动加载）；旧 prefs 迁移只执行一次；扫码 model-add 与 pair 严格分流（`classifyScanResult`，pair URI 形态正确但 code 非法不回落）；深链 `notemeld://model-add`/`pair` intent-filter + `onNewIntent`；三语 53+ 新键无缺失。
- [x] 安卓：EmbeddedLocalAgent 按选中模型的 provider 协议分派 openai-compatible/anthropic-messages/ollama 三请求形态（复用既有 URL/header/body 构造，无 SDK 依赖）。
- [x] 分享载荷形态与三端一致（`notemeld://model-add?d=<base64url>`，JDK `java.util.Base64`），任何载荷不含 Key；Auto 不出现在可保存模型列表。
- [ ] feature-registry.json 对应 maturity/status 回写（D09.model-catalog/C06.model-catalog/M07.models/model.share-schema、C03.model/C05.devices/C06.settings partial→implemented 的准确状态），系统文档同步。

## 12. 风险和回滚

- 主要风险：
  1. 桌面明文 Key 加密迁移失败导致用户需重填（缓解：迁移事务、逐行 try、失败行保留明文并标记 has_api_key=migration_failed，启动日志只报 id 不报值）。
  2. Cloud 回填去重把不同用户同名 provider 错误合并（缓解：去重键含 user_id；provider 是新行不共享凭据，组织共享仅在映射后生效，同 provider 多凭据时每个 user 生成独立 provider 行，命名加后缀）。
  3. pairings 去 Key 后旧版 App 无法跑云端命令（缓解：同次发布桌面与安卓；Cloud 侧 model_id 解析对缺少 id 的旧命令给明确升级提示，不回退到下发 Key）。
  4. cryptography 打包遗漏（缓解：requirements 核查 + PyInstaller import 测试，遵循 pitfalls）。
  5. 安卓 Keystore 迁移失败丢密钥（缓解：先写新 alias 成功再清旧 prefs；失败保留旧条目并可重试）。
- 触发信号：启动迁移异常日志、连接认证 401 激增、Cloud runner model_id 解析失败率、安卓 DB 崩溃。
- 降级：三协议任一不可用不影响其他协议；facade 保旧云端口径；前端可临时隐藏分享入口（feature 无开关需要，直接菜单项）。
- 回滚步骤：代码回退到旧版本（桌面新列保留、明文已清空需重填 Key；Cloud 旧列保留可直接运行；安卓卸载或清库）。
- 回滚一致性：不回滚数据库（additive）；不删新列/新表。
- 用户可见影响：桌面用户可能需重新输入一次 API Key（仅当迁移失败行）；其余透明。

## 13. Agent 必答问题

- **影响哪些已有模块？** 桌面 provider/model 整条 router-service-dao-schema + 设置页；Cloud models/pairings/runner/db/agent + cloud-web；安卓 data/net/ui/agent/scanner/manifest。
- **是否已有类似能力？** 有：三端 prototype + model-vendor-registry.js + 桌面扁平 providers/models + Cloud 加密列与 Fernet 基建；本 spec 是对齐与产品化，不另起体系。
- **是否和产品规则冲突？** 不冲突；修复现存违规（明文回显、配对下发 Key）。
- **是否和数据模型字段语义冲突？** models 既有运行字段语义不变，仅增列；context_window 新默认值仅用于新表单，不碰 4096 兜底。
- **是否重新引入 known-pitfalls？** 已逐项规避：GPTFactory 保留、list_models 不迁移、models 不入 legacy 白名单、cryptography 显式依赖、密钥不日志、端侧不复制加密实现。
- **是否影响本地数据或线上服务？** 是：三端 SQLite additive 迁移；Cloud pairings 响应为有意破坏性安全变更，调用方同次发布。
- **最小可行改动？** 复用现有迁移挂载、wrapper、Fernet、SSRF、HttpURLConnection、Keystore；新增集中在字段、协议适配与一套 registry，不重构无关层。
- **补哪些测试？** 见第 10 节：迁移幂等/脱敏/三协议 mock/组织鉴权/配对无密钥递归断言/安卓纯 JVM 编解码与 SQL/三语/前端契约。

## 14. 执行记录

### Cloud（已完成）

- 后端：`cloud/db.py` 幂等两级迁移（`_migrate_catalog`，旧 models 行回填
  provider_id/organization_id，legacy 协议映射 openai→openai-compatible、
  anthropic→anthropic-messages，每组织仅保留最早默认）；`cloud/app.py` 新增 10 个
  `/v1/catalog/*` 端点，组织鉴权（owner/admin 写、member 只读、无成员 403），
  Fernet 加密列 + 仅回 `has_api_key`/`api_key_masked`；discover/test-connection
  三协议路径 + SSRF 防护（非 ollama DNS 解析拒绝私网，ollama 仅 localhost）；
  `cloud/agent.py` 按 protocol 分派 `AnthropicMessagesRunner`/`OllamaAgentRunner`；
  配对 bundle 仅模型元数据（无 api_key）。
- cloud-web（物理树 = `desktop/frontend`，入口 `apps/cloud-web/`）：
  CloudModelList/CloudModelForm 两级 CRUD、22 厂商、多选拉取、测试、分享导入、
  member 只读态；`tsc --noEmit` 与 `build:cloud-web` 通过。
- 测试：`desktop/backend/tests/test_cloud_backend_slice.py` 全量 **127 passed**
  （新增 8 个 catalog 专项：组织鉴权四态、密钥脱敏与留空保留、batch 幂等/默认
  规则、模型生命周期、三协议 discover、三协议 test、迁移跨重启幂等、无 secret_key
  503）。
- 文档：`api-inventory.md` catalog 端点表与 pairing confirm 语义已同步。

### 安卓端执行记录（2026-09-21）

- 持久化：`ModelDatabase`（新库 `notemeld-models.db` v1）两表
  `mobile_model_providers`/`mobile_models`（协议三值 CHECK、FK CASCADE、
  provider+model 唯一、test_status 三值）；`ModelDao` 薄 CRUD。
- 密钥：`ModelProviderSecretStore` 每 Provider 一个 Android Keystore AES/GCM 别名
  `model_provider_<id>`，密文 Base64(iv+ct) 存独立 prefs；`migrateLegacyOnce`
  迁移旧 LocalProvider 单密钥、删除旧配对 bundle、清旧标量并写 flag。
- Registry/网络/分享：`VendorRegistry`（22 预设 + 三协议 + 校验）、
  `ModelProtocolClient`（HttpURLConnection 三协议 discover/test，明文仅本机，
  响应 4MB 上限、禁跟随重定向）、`ModelSharePayload`
  （`notemeld://model-add?d=<base64url>`，JDK Base64，拒绝密钥字段/pair/bedrock）。
- 扫码分流：`ScanTarget` 密封类型 + `classifyScanResult`，pair 码与 model-add
  配置严格互斥；pair URI 形态正确但 code 非法返回 null，不回落。
- UI：`ModelSettingsScreen` Provider 分组（模型 chips、默认/启用/测试状态、
  编辑/删除/设默认/启停/测试/分享）；`ModelAddSheet` 厂商网格→Key/URL→拉取
  多选→上下文→测试→保存；空态/失败态；三语；testTag 沿用旧骨架。
- 装配：`MainActivity` 启动加载 DAO/选中模型，CLOUD 发送携带
  `selectedCloudModelId`，登录/恢复写 `cloudModels`，配对写 `pairedModels`，
  本地选择经 `EmbeddedLocalAgent.selectModel`；`notemeld://model-add`/`pair`
  intent-filter + `onNewIntent`。
- 测试：`./gradlew :app:testDebugUnitTest` **BUILD SUCCESSFUL**（13 项：state
  目录投影、三语新键完备、扫码互斥）；androidTest `MainActivitySmokeTest`
  模型设置页用例已同步。完整 assemble/插桩未在本轮执行。
