# NoteMeld 插件管理与内置目录页面

日期：2026-08-27
状态：Ready for Plan
需求类型：产品 UI 与既有插件控制面增量
视觉参考：用户提供的 WorkBuddy 风格“专家 / 技能 / 连接器”页面截图；截图只作为信息架构和交互意图参考，不作为实现指令。
相关系统文档：`../system/current-architecture.md`、`../system/product-rules.md`、`../system/data-model.md`、`../system/api-inventory.md`、`../system/known-pitfalls.md`
相关既有需求：`2026-08-24-desktop-note-agent-plugin-integration.md`
Change Spec：本文件第 8 节，执行前需复制为独立 `docs/system/change-spec-*.md` 或在 Plan/Spec 中保持同等内容。

## 1. 原始需求

用户希望在 NoteMeld 增加一个面向用户的插件页面：

1. 页面默认展示 NoteMeld 内置插件及其配置状态。
2. 用户可以浏览、搜索和筛选插件/技能内容。
3. 用户可以添加自定义插件内容，并查看安装、权限、启用和运行状态。
4. 页面整体可参考截图中的卡片式目录体验，但不复制其品牌、文案或实现。

本需求将“添加内容”解释为添加插件/技能包及其 manifest 描述内容。如果用户所说的“内容”实际指知识库文档或 Note 内容，应另立需求，不能与插件安装混用。

## 2. 背景与用户问题

当前 NoteMeld 已有 `/settings/plugins` 页面，但它主要是 Release ZIP 的安装和运行控制台：用户需要直接输入 URL、SHA-256 和权限，已安装项按 `plugin_id` 展示，缺少可发现的目录、内置默认项、能力说明和统一的添加入口。当前用户因此难以回答以下问题：

- NoteMeld 默认具备哪些插件能力；
- 某个插件是已安装、已启用、正在运行，还是只支持当前平台的协议；
- 插件请求哪些权限、这些权限为什么需要；
- 如何从页面安全地添加自己的插件；
- 安装失败、运行失败或已有旧版本时下一步是什么。

现有后端已经提供插件 control-plane：允许的 HTTPS Release 下载、staging 校验、manifest/version/license/hash 检查、权限授权、不可变版本目录、active pointer、启停、激活/回滚和审计。页面应把这些能力组织成用户可理解的体验，不应新增一套插件状态或安装事实源。

## 3. 目标

### 3.1 用户目标

- 用户进入设置中的插件页面即可看到内置插件目录和当前安装状态。
- 用户可以通过搜索、分类和安装状态筛选定位插件。
- 用户可以打开插件详情，了解简介、能力、版本、权限、兼容平台和运行状态。
- 用户可以从“添加插件/内容”入口添加受支持来源的标准插件包，并在安装前看见来源、版本、摘要、hash 和权限确认。
- 用户能够启用、禁用、切换版本和回滚，并得到明确的成功、失败或待处理状态。

### 3.2 系统目标

- 内置目录来自版本化的本地 manifest/catalog；目录项和数据库中的 `PluginInstallation` 明确分离。
- 已安装插件的运行状态继续以现有 `/api/plugins` 和 PluginManager 为权威。
- 添加流程继续使用现有 Release resolver、verifier、权限 authority 和 active-pointer 流程。
- UI 不执行插件安装脚本，不绕过后端校验，不暴露 token、凭证、完整内部路径或原始异常。
- 页面在桌面 sidecar/backend 未 ready 时遵守现有 ready gate，不提前发起业务请求。

## 4. 非目标

- 不在本需求中重新设计插件协议、manifest v1、SDK runtime 或 Host capability contract。
- 不建设中心化云端 SkillHub/插件市场、账号同步、评分评论或自动更新服务。
- 不允许从任意 Git branch clone、任意 URL 下载或安装并执行脚本。
- 不在本需求中实现浏览器、终端、文件预览、沙箱或移动端 runtime；页面只能准确展示插件 manifest 声明的目标状态。
- 不把“内置目录项”自动当作“已安装并可运行”；缺少本机包、Host adapter 或平台验证时必须显示对应状态。
- 不修改 Note、Conversation、Wiki 或 Agent runtime 的事实源。
- 不做与插件目录无关的设置页重构。

## 5. 当前系统事实

### 5.1 前端

- `frontend/src/App.tsx` 已注册 `/settings/plugins`。
- `frontend/src/pages/SettingPage/Menu.tsx` 已有“插件运行”入口。
- `frontend/src/pages/SettingPage/Plugins.tsx` 已支持：列出已安装插件、安装 Release ZIP、输入 SHA-256、选择权限、启用/禁用、激活版本和回滚。
- `frontend/src/services/plugins.ts` 已封装 `list/install/enable/disable/activate/rollback` API。
- 当前页面没有目录 catalog、卡片详情、搜索/分类、未安装内置项和分阶段安装确认体验。

### 5.2 后端与数据

- `backend/app/routers/plugins.py` 提供 `/api/plugins`、`/api/plugins/ready`、安装、启停、激活、回滚和审计接口，并使用统一 response wrapper 与 session token。
- `backend/app/services/plugins/manager.py` 负责安装、权限校验、版本注册、active pointer、运行状态和审计。
- `backend/app/services/plugins/release_resolver.py` 与 `verifier.py` 负责来源、重定向、大小、超时、路径和包内容边界。
- `PluginInstallation`、`PluginVersion`、`PluginAuditEvent` 属于独立 plugin control-plane；版本目录和 active pointer 是运行时文件事实的一部分。
- 当前内建启动时明确自动安装的是 `official.link-note`；`notemeld-plugins` 还声明了 `official.browser`、`official.terminal`、文档转换、OCR、视频/音频等插件 manifest，但各 target 的状态必须按 manifest 和实际 bundle/Host 能力显示。
- `official.terminal` 的 manifest 已声明 desktop `host-ready`、server `contract-ready`、mobile-native/wasm 不支持一期；此类状态只能展示为兼容性信息，不能由页面自行推断成可执行。

### 5.3 既有安全与产品约束

- 插件不能直接写 NoteMeld 内部数据库、Conversation、Agent Event 或 UI；能力通过 Host port/capability 接入。
- 权限由 Host/Application authority 决定，manifest 不能自授权；未知权限必须 fail closed。
- 所有普通 API 使用 `{code,msg,data}`；错误给用户显示安全文案，详细诊断留在受控审计/日志。
- L0–L3 能力发现约束仍适用于 Agent；目录首屏不得把全部工具 schema 或敏感配置平铺给 Agent 或 UI。

## 6. 用户故事与范围

### US-01：浏览内置插件

作为 NoteMeld 用户，我希望进入插件页面就能看到官方内置插件及摘要、能力、兼容平台和当前状态，从而知道当前安装了什么、能用什么。

### US-02：查看已安装插件

作为用户，我希望切换到“已安装”视图，看到启用状态、active version、运行状态、权限和可用旧版本，从而安全维护插件。

### US-03：搜索与筛选

作为用户，我希望按名称、简介、能力 ID、分类和安装状态筛选，从而快速找到目标插件。

### US-04：添加自定义插件

作为用户，我希望点击“添加插件/内容”，提供受支持的 Release ZIP 来源或本地可验证包信息，在安装前查看包信息与权限并确认，从而接入自己的插件。

### US-05：处理失败与恢复

作为用户，我希望安装失败、权限不匹配、版本重复、插件崩溃或 backend 未 ready 时看到原因和下一步，而不是看到假成功或页面卡死。

## 7. 验收标准

### AC-01 页面入口与目录首屏

**GIVEN** 用户打开 NoteMeld 设置且 backend 已 ready
**WHEN** 用户进入 `/settings/plugins`
**THEN** 页面展示插件目录、已安装视图入口、搜索/筛选入口和“添加插件/内容”入口；页面名称和“插件运行”旧入口语义兼容，既有链接不失效。

### AC-02 内置默认配置准确

**GIVEN** 应用首次启动或本地没有插件安装记录
**WHEN** 用户打开插件目录
**THEN** 页面展示版本化内置 catalog；每个目录项明确标注 `内置/推荐`、`已安装/未安装`、`已启用/已禁用`、`运行中/不可用/未验证` 等状态，不把仅有 manifest 的项目伪装成已安装运行项。

### AC-03 已安装状态唯一

**GIVEN** PluginManager 返回某插件的 installation/version 状态
**WHEN** 页面刷新、切换筛选或打开详情
**THEN** active version、enabled、runtime status、permissions 和 versions 与 `/api/plugins` 一致；页面不自行维护第二份可写状态。

### AC-04 详情与权限可理解

**GIVEN** 用户打开一个目录项或已安装插件详情
**WHEN** 页面渲染详情
**THEN** 至少展示插件 ID/显示名、简介、能力摘要、当前版本、兼容 target 状态、请求权限、已授予权限、来源/许可证及运行诊断入口；权限展示人类可读的用途说明，且不显示密钥、token 或内部绝对路径。

### AC-05 添加前确认

**GIVEN** 用户从添加入口提交受支持的 HTTPS GitHub/Gitee Release ZIP 来源
**WHEN** 用户填写来源、可选 SHA-256 和待授予权限
**THEN** 页面展示来源、hash、权限和“安装脚本不会执行”的风险提示，用户明确确认后才调用正式安装；plugin id、version、license、digest 和兼容性仍以既有后端最终校验结果为准；同一页面提供取消操作。

### AC-06 添加成功

**GIVEN** 包来源、manifest、hash、license、版本和权限全部通过，且用户授予所需权限
**WHEN** 用户确认安装
**THEN** 页面显示安装成功并刷新目录/已安装状态；版本进入既有不可变版本记录，首次安装按现有规则设置 active version，审计记录可查询。

### AC-07 添加失败 fail closed

**GIVEN** 来源不是允许的 HTTPS host、重定向越界、包过大/超时、hash 不匹配、路径穿越、安装脚本、license/version/sdk 不兼容、未知权限或用户拒绝权限
**WHEN** 用户确认安装
**THEN** 页面显示稳定的安全错误分类，插件不进入 active pointer、不显示为已启用，已有 active version 和其他插件继续可用。

### AC-08 生命周期操作

**GIVEN** 插件存在 active version
**WHEN** 用户执行启用、禁用、版本激活或回滚
**THEN** 页面展示 pending/loading、成功或失败状态；所有结果以现有 control-plane 返回为准；回滚保留旧版本和审计记录。

### AC-09 搜索、分类和空状态

**GIVEN** catalog 中有多个插件，或用户输入没有匹配项
**WHEN** 用户搜索/分类/切换“已安装”
**THEN** 列表结果稳定且不改变安装状态；无匹配、无安装项、catalog 加载失败和 backend 未 ready 各有明确空/错误状态及可操作提示。

### AC-10 ready gate 与安全响应

**GIVEN** backend/desktop sidecar 尚未 ready
**WHEN** 用户打开页面或点击安装、启停、激活、回滚
**THEN** 页面不发起业务 mutation/list 请求，显示等待或诊断提示；任何接口错误遵循 response wrapper，日志和 UI 均不泄露凭证、token、用户本地绝对路径或原始敏感 payload。

### AC-11 回归兼容

**GIVEN** 现有插件 control-plane 契约测试和既有 `/settings/plugins` URL
**WHEN** 完成页面升级
**THEN** 现有安装、权限、启停、版本激活/回滚、崩溃 fail-closed 和 I04 路由契约继续通过；旧已安装数据无需用户重新安装即可展示。

## 8. 增量 Change Spec（执行前依据）

### 8.1 最小实施方案

#### 后端

- 增加只读 catalog 读取能力，优先从随应用发布/内建插件包携带的 manifest 生成目录；不把 catalog 记录写入 `PluginInstallation`。
- 本期不增加安装前 preview API；安装弹窗只确认来源、hash、权限和安全提示，正式安装仍唯一调用现有 `PluginManager.install`，其返回结果是 plugin id/version/license/digest 的权威来源。
- 继续复用现有 plugin response wrapper、session token、权限 authority、审计、独立 migration registry 和失败回滚边界。
- 对自定义“添加内容”限定为标准插件包/manifest，不提供任意文本直接变成可执行插件的路径。

#### 前端

- 将现有单页安装控制台升级为“目录 + 已安装 + 添加/详情”的页面结构；保留 `/settings/plugins` 路由与现有服务调用兼容。
- 目录卡片只消费 catalog 与安装状态的组合投影；详情页/抽屉显示能力、权限、版本、target 和诊断。
- 添加流程分为来源输入、校验预览、用户确认、安装结果四个状态；安装按钮在校验/确认前不可触发正式安装。
- 对加载、空列表、backend 未 ready、校验失败、安装失败、运行崩溃和权限拒绝提供可恢复提示。
- UI 文案和卡片信息参考截图的信息密度，但不引入截图中的第三方品牌和未经 NoteMeld 确认的分类/内容。

### 8.2 数据、接口与兼容性

- 默认不新增 SQLite 表或修改已有 plugin 表；catalog 的具体载体在 Plan 阶段根据打包边界确定，优先静态 manifest/catalog。
- 若需持久化用户自定义目录元数据，必须使用独立 plugin migration registry，并明确其与安装包/active pointer 的一致性和回滚策略；不能把 UI 草稿写成安装记录。
- 现有 `/api/plugins` 等接口保持兼容。若增加 catalog/preview API，必须同步 `docs/system/api-inventory.md`，返回仍使用统一 wrapper，并定义错误码/脱敏规则。
- 本期不修改 SDK 协议、插件 manifest 版本或 NoteMeld Agent 的 capability 语义。

### 8.3 影响范围

- 前端：`frontend/src/pages/SettingPage/Plugins.tsx`、`frontend/src/services/plugins.ts`、必要的 UI 组件与契约测试。
- 后端：`backend/app/routers/plugins.py`、`backend/app/services/plugins/`、必要的 catalog/preview service；不改变现有 verifier/manager 的安全边界。
- 数据与文件：优先无迁移；若确需持久化，新增独立 registry/迁移并补历史兼容。
- 桌面/打包：若默认 catalog 携带内置 manifest，需要确保源码启动、PyInstaller sidecar 和桌面包都能读取同一 catalog；不能只在开发目录可见。
- 测试：插件 control-plane 现有测试、前端页面契约、API wrapper/脱敏、ready gate、打包资源存在性和手动桌面路径。
- MCP/Agent：本期无直接接口变化；页面展示能力不得绕过 Agent 的 capability discovery/Host authority。

### 8.4 冲突检查

- 与 `product-rules.md`：不冲突，前提是插件仍通过 Host/Capability 接入，用户对权限和副作用保持可见、可控。
- 与 `data-model.md`：不应把 catalog 当 `PluginInstallation`；candidate 的 plugin scope 仍只能引用真实已安装 `plugin:<id>`。
- 与 `api-inventory.md`：既有插件 API 继续使用统一 wrapper；任何新增 catalog/preview 接口必须登记。
- 与 `known-pitfalls.md`：重点防止插件权限自授权、敏感配置泄露、backend 未 ready 抢跑、运行崩溃仍显示 running、独立 migration registry 被共享 `PRAGMA user_version` 覆盖。
- 运行模式：影响桌面设置页和源码 Web 设置页；不改变 CLI、MCP、Agent runtime 的既有入口。

### 8.5 错误、并发与回滚

- 同一插件重复安装/重复点击必须由 UI 防抖和后端幂等/稳定错误共同防护；不能产生半注册版本。
- 校验或安装失败时清理/隔离 staging，不能改变旧 active pointer；具体清理策略以现有 verifier 的可恢复边界为准。
- 操作期间用户切换页面或刷新，重新读取后端事实，不以本地 optimistic state 覆盖结果。
- runtime crash 显示 `crashed`/不可用诊断，不显示为 running；用户可禁用、重新激活或回滚。

## 9. 测试与质量门禁

- 后端：补充 catalog 与 preview（如采用）的契约测试；保留并运行 `backend/tests/test_plugin_control_plane.py`、`backend/tests/test_i04_integration.py` 及相关 plugin/agent-host 回归。
- 前端：补充 `/settings/plugins` 的目录、默认项、已安装投影、搜索/分类、添加确认、失败/空/ready gate 和无泄露契约测试；运行 `cd frontend && pnpm test:contracts` 与 `pnpm build`。
- 集成：至少验证首次启动、已有 `official.link-note`、未安装的内置 manifest、添加合法包、拒绝非法包、旧版本回滚和插件崩溃状态。
- 手动：在桌面 sidecar ready 和未 ready 两种状态检查；确认窗口刷新后状态仍来自后端；确认内置插件 target 状态不被误报。
- 完成前运行 `git diff --check`，检查未改动用户已有文件，且不把 `target/`、dist、日志或凭证纳入提交。

## 10. 风险、回滚与开放问题

### 10.1 风险

- 内置 catalog 与实际打包资源版本不一致，导致用户看到可安装但实际无法安装。
- 将“推荐/内置”误显示为“已安装/运行中”，导致用户错误判断能力可用性。
- 为实现安装前预览而复制 verifier 规则，造成安全边界漂移。
- 卡片信息过多，把所有 capability schema 或权限细节直接平铺，增加认知和提示词噪声。

### 10.2 回滚

- 前端升级可回退到现有 `/settings/plugins` 控制台；既有 plugin tables、版本目录、active pointer 和审计记录保持不变。
- 若新增 catalog 文件，只移除新 UI 对其的读取并保留已安装插件事实；若新增数据库 migration，必须按独立 forward-only 规则设计可兼容旧版本读取，不能删除用户安装数据。

### 10.3 非阻塞开放问题

1. “添加内容”在最终 UI 中的按钮名称是“添加插件”还是“添加技能/内容”；本需求默认使用“添加插件/内容”，Plan 阶段可统一中文术语。
2. 首期 catalog 是仅随 NoteMeld 发布的静态 manifest，还是同时允许用户导入自定义 catalog 索引；本需求的安全最小范围是只允许标准插件包来源，不允许不受信任 catalog 改变权限或安装规则。
3. 视觉上是否保留“专家 / 技能 / 连接器”三类顶层 tab；本需求只要求插件页面，不把三类 tab 视为已确定的领域模型。

## 11. Agent 必答问题

- **影响模块**：设置页、插件前端 service、插件 catalog/preview（若需要）、既有 plugin control-plane、桌面打包资源和契约测试。
- **是否已有类似能力**：已有 `/settings/plugins` 安装/运行控制台；本需求是目录化和默认配置升级。
- **是否与产品规则冲突**：不冲突，前提是 Host authority、权限确认、Note/Agent/插件边界不变。
