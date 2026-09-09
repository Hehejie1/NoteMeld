# 高保真静态产品演示与功能讲解设计

日期：2026-08-13
状态：待用户复核
Canonical requirement：`docs/requirements/2026-08-13-static-product-demo-and-feature-guide.md`

## 1. 设计结论

静态演示采用“正式 UI + 演示运行时适配层”，不复制一套平行页面。现有路由、布局、页面组件、设计 token 和大部分 store 逻辑继续作为唯一 UI 来源；仅在显式 demo 构建模式下替换后端 ready 判断、数据传输和桌面副作用。

核心边界：

```text
正式模式：页面/组件 → 现有 services → Axios/fetch/Tauri → FastAPI/桌面运行时
演示模式：页面/组件 → 现有 services → demo adapter → fixtures + scenario engine
```

演示模式不得向真实 `/api`、`/static`、MCP、LLM Provider 或 Tauri 命令发起业务调用。正式模式不得导入或初始化演示数据。

## 2. 方案比较

### 方案 A：复用正式 UI，在传输边界切换演示适配层（采用）

- 优点：正式页面和演示页面共享视觉与交互代码；截图偏差最小；状态契约可复用；后续维护成本低。
- 代价：需要清点 Axios、原生 fetch、动态 Tauri import 和文件资源 URL 四类调用，不能只替换 Axios baseURL。
- 适用：本需求强调与线上一致并允许模拟接口。

### 方案 B：复制页面到独立 demo app

- 优点：隔离直观、开发初期容易控制。
- 缺点：立即形成第二套 UI；源码变化后容易漂移；难以证明“与产品完全一样”。
- 不采用。

### 方案 C：截图热点图

- 优点：单一截图状态视觉一致。
- 缺点：无法覆盖真实响应式、滚动、抽屉、状态和组件交互；不属于代码抽离。
- 不采用。

## 3. 运行模式与入口

### 3.1 模式识别

- 新增单一的 `isDemoMode()` 运行时判断，编译期读取 `VITE_NOTEMELD_DEMO=true`。
- 正式模式默认值必须为 false；不存在 query string、localStorage 或运行时点击即可偷偷切换到 demo 的路径。
- demo build 仍使用现有 React 入口和路由树，但 `BackendInitProvider` 在该模式提供固定 ready context，不执行 runtime/backend health check。

### 3.2 预览脚本

- 仓库根目录新增 `scripts/preview_static_demo.sh`。
- 脚本检查 Node 与 pnpm，按需提示依赖安装，执行 demo build，并用 Vite preview 启动带 history fallback 的本地服务器。
- 默认绑定 `127.0.0.1`，默认端口使用独立端口，允许通过参数或专用环境变量覆盖；不复用系统 `$HOME` 等变量。
- 脚本输出 URL；若平台支持且用户未显式关闭，可打开浏览器。
- 失败时保留构建输出并返回非零状态。

### 3.3 静态托管

- Vite `base: './'` 保持资源相对路径兼容。
- 本地 preview 依赖 history fallback 支持 BrowserRouter 直达路由。
- 若后续要求双击 `index.html` 或无 fallback 的对象存储托管，再单独评估 demo 模式使用 HashRouter；本轮不改变正式浏览器路由语义。

## 4. 演示数据架构

### 4.1 Fixture 原则

- fixture 使用 TypeScript 模块并复用现有 service/store 类型。
- 只参考数据库 schema、状态分布和数据关系；正文、标题、URL、路径和身份信息改写为合成内容。
- fixture id 使用稳定、可读的 demo 前缀，保证刷新和截图可重复。
- 时间戳固定在一个参考时刻，避免相对时间与排序每次变化。
- 不包含 API Key、Cookie、token、Authorization、真实本地绝对路径或用户原始对话。

### 4.2 Fixture 分域

- conversations：聊天、笔记、空会话、失败会话、研究白板会话。
- messages：user_input、assistant_text、note_progress、note_result、system_error、task_card、learning_canvas。
- documents：完整 Markdown、来源信息、Wiki pending/partial/success。
- task status：PENDING、PARSING、DOWNLOADING、TRANSCRIBING、SUMMARIZING、FORMATTING、SAVING、SUCCESS、FAILED、CANCELED。
- wiki：节点、边、cluster、空图和加载失败场景。
- styles：现有内置模板卡片、创建/编辑表单和提取任务状态。
- settings：脱敏 Provider、模型、转写器模型状态、下载器 Cookie 是否配置、迁移 job、usage、deploy status、MCP server 和研究搜索配置。
- updater/desktop：非桌面、已是最新版、发现更新、下载进度和失败等纯模拟结果。

### 4.3 Scenario Engine

- demo runtime 保存当前 scenario 与内存变更，不写正式 SQLite 或文件系统。
- 默认场景与 `docs/product/` 截图对应。
- 通过演示控制面板或预定义路由参数进入空、运行中、成功、失败、取消、partial 等状态。
- 模拟生成使用显式状态机和可清理 timer：

```text
PENDING → PARSING → DOWNLOADING/TRANSCRIBING → SUMMARIZING
→ FORMATTING → SAVING → SUCCESS
                         ├→ FAILED
                         └→ CANCELED
```

- 状态机更新现有 Zustand task 表达，确保 StepBar、消息卡和内容面板走正式渲染路径。
- 重置场景时清理全部 timer；React StrictMode 重挂载不得启动两套模拟任务。

## 5. 服务适配边界

### 5.1 普通请求

- 在统一 request 层加入 demo adapter，按 method + pathname 匹配现有 API 契约并返回解包后的业务数据。
- 不使用浏览器 Service Worker：本需求不需要离线缓存与网络级代理，避免增加调试复杂度。
- 未注册的 demo endpoint 必须快速失败并指出路径，不能回退到真实网络。

### 5.2 流式请求

- `streamFreeChat()` 等直接 fetch 的调用显式路由到 demo stream adapter。
- adapter 复用现有 handler 接口依次发送 delta、task_card、task_card_progress、done 或 error，避免伪造真实 `ReadableStream` 的不必要复杂度。

### 5.3 静态资源与代理 URL

- 视频封面、Logo、占位图使用 `frontend/public/` 的演示资源或 data-safe fixture URL。
- demo 模式禁止拼接真实 `/api/image_proxy` 和 `/static` backend URL。

### 5.4 Tauri 与破坏性操作

- 文件选择、自动启动、应用更新、下载模型、迁移、删除与保存等操作走 demo action adapter。
- 删除只改变 demo 内存并支持刷新恢复默认 fixture。
- 文件上传只读取浏览器提供的文件名/类型用于展示；不上传、不保存原文件内容，除非某组件展示需要短暂内存预览。
- 外链可保留普通浏览器打开，但必须是仓库已有公开地址；不发送数据。

## 6. 页面与状态覆盖

### 6.1 截图基线页面

| 基准截图 | 演示入口 | 必须覆盖 |
| --- | --- | --- |
| `index.png` | `/` | 正式营销首页与进入工作台 |
| `home.png` | `/new` | 空白工作台、侧边栏笔记列表、composer |
| `notes.png` | `/notes/demo-note-success` | 对话 + 笔记双栏、来源 banner、Markdown |
| `wiki.png` | `/wiki` | 类型/社群切换、缩放、节点聚焦、说明抽屉 |
| `styles.png` | `/styles` | 搜索、模板卡、内置标识 |
| `styles-create.png` | `/styles` 后点击新建 | 模板助手与编辑抽屉、遮罩、保存模拟 |
| `setting-model.png` | `/settings/model` | Provider 选择、开关、模型配置 |
| `setting-transcriber.png` | `/settings/transcriber` | 引擎选择、模型状态、下载模拟 |
| `settings-youtube.png` | `/settings/download/youtube` | 平台列表、Cookie 状态、保存模拟 |
| `about.png` | `/about` | 版本与检查更新模拟 |

### 6.2 补充路由

- 现有设置菜单中的数据迁移、Token 消耗、部署监控、MCP 服务器、研究搜索均可跳转并返回 fixture。
- 这些页面不一定有截图基准，但必须保持正式组件布局且不访问后端。
- 移动端不以像素一致为本轮主验收，但导航、内容切换和说明抽屉不得不可用。

## 7. 功能讲解系统

### 7.1 交互

- 演示界面提供克制的“功能讲解”全局开关；关闭时不改变正式视觉和点击行为。
- 关闭讲解模式时：左键执行原功能；右键阻止浏览器菜单并打开对应说明。
- 开启讲解模式时：点击已标注功能区打开说明，不执行原动作；抽屉内提供“执行此功能”按钮用于继续原动作。
- Escape 或关闭按钮关闭抽屉；焦点进入抽屉，关闭后返回触发元素。
- 移动端无右键，因此使用讲解开关；不依赖长按劫持系统菜单。

### 7.2 标注方式

- 新增轻量 `FeatureGuideTarget` 包装器或 hook，仅负责 feature id、事件转发和可访问性属性。
- 默认不添加边框、徽标或改变布局；讲解模式开启时可用低干扰轮廓提示可讲解区域。
- 优先标注导航、composer 模式、模型选择、Wiki 视图、模板创建、设置主功能和内容工具栏；不把每段正文和纯装饰图标都标注。

### 7.3 说明数据

说明记录为版本控制的静态内容，不在运行时读取 Markdown 文件。每条包含：

- `id`、名称、短摘要。
- 用户价值与操作结果。
- 产品依据：canonical requirement/product rule 的仓库相对路径与章节名称。
- 代码依据：路由、组件、service/store 的仓库相对路径与符号名。
- 数据与状态：涉及的 API、模型或 fixture 状态。
- 演示限制：真实产品会做什么、静态模式模拟什么。
- 证据类型：`requirement_and_code`、`code_fact` 或 `needs_requirement`。

浏览器不能直接打开本地源码绝对路径，因此抽屉以可复制的仓库相对路径展示依据，不暴露本机路径。

## 8. 视觉一致性与验证

### 8.1 校准顺序

1. 先保证使用正式组件和 token。
2. 在 3840×1916 截取 10 个基准状态。
3. 对比侧边栏宽度、主分栏比例、页面边距、字号层级、颜色、卡片/抽屉尺寸和滚动位置。
4. 仅修复由 demo fixture 或 demo wrapper 引起的偏差；不为了适配单张截图破坏正式响应式布局。

### 8.2 自动检查

- contract test：demo 模式不调用 backend ready probe；未知 mock endpoint fail closed；正式模式仍走现有 service。
- fixture test：状态覆盖完整、关系 id 有效、无敏感字段/绝对路径。
- scenario test：成功、失败、取消、reset；timer cleanup。
- feature guide test：普通点击、讲解点击、右键、执行原功能、键盘关闭。
- build：正式 build 与 demo build 均成功。
- shell smoke：脚本启动后首页与深层路由返回 200。
- network check：操作主要页面时无 `127.0.0.1:8483`、LLM、MCP 或第三方业务请求。

### 8.3 人工检查

- 按 10 张基准截图逐页核对并记录偏差。
- 1440px 桌面宽度检查可用性。
- 至少检查一个移动宽度的导航与说明抽屉。

## 9. 错误与降级

- fixture 缺失：显示带 endpoint/feature id 的演示配置错误，不访问真实后端。
- 模拟失败：使用正式错误态组件或 toast；错误内容固定且不含本地环境信息。
- 浏览器不支持自动打开：脚本仍打印 URL。
- 字体网络不可用：回退到现有系统字体栈，演示仍可用；截图回归环境应固定字体条件。
- 说明缺少 requirement：显示“当前仅有代码事实”，而不是猜测产品意图。

## 10. 影响范围

- 前端入口：App/BackendInit 增加显式 demo 分支。
- 传输层：request、stream、desktop action 增加 demo adapter。
- 数据：新增纯前端 fixtures、scenario engine 和 feature guide catalog。
- UI：新增讲解开关、target 包装和右侧说明抽屉；现有页面做最小标注。
- 工具：新增 build/preview script 与 package scripts。
- 测试：新增 demo contract、fixture、scenario、guide 和启动 smoke 测试。
- 文档：requirement、Change Spec、implementation plan、验证证据；若最终形成长期运行入口，再同步 `current-architecture.md`。
- 后端、SQLite、文件结构、API 和 MCP：无变更。

## 11. 风险与回滚

- 风险：demo 分支渗入正式模式。防线：默认 false、正式 build 回归、未知 endpoint fail closed。
- 风险：fixture 含敏感内容。防线：只写合成内容、字段与路径扫描、人工审查。
- 风险：直接 fetch/Tauri 漏网。防线：调用清单、网络断言、桌面 action adapter。
- 风险：讲解 target 改变布局。防线：无包装 DOM 或 `display: contents`/事件合并策略，截图回归。
- 风险：模拟 timer 在路由切换后继续写状态。防线：集中 scheduler、reset/dispose、StrictMode 测试。
- 回滚：删除 demo mode 分支、adapter、fixtures、guide 和脚本；由于没有 DB/API/文件迁移，正式数据无需回滚。

## 12. 自审结果

- 无 TBD/TODO 或未决实现语义。
- requirement、架构、交互、测试与回滚相互一致。
- 范围为一个可执行项目：静态演示运行时与讲解系统共同服务同一交付物。
- 明确采用传输适配而非复制页面；明确说明点击冲突、路由策略、隐私边界和未知 endpoint 行为。
