# Change Spec：应用包独立化与 Wiki 应用抽离

状态：Ready for implementation
日期：2026-08-28
关联协议：[`application-protocol-v1.md`](application-protocol-v1.md)
关联需求：[`../requirements/2026-08-27-notemeld-application-runtime-and-wiki-app.md`](../requirements/2026-08-27-notemeld-application-runtime-and-wiki-app.md)

## 1. 当前系统现状

- `backend/app/applications/` 已有 manifest、应用实例、Run、workspace 和运行时抽象。
- `applications/wiki/manifest.json` 和 `applications/wiki/ui/index.html` 已存在，但 UI 文件只是占位入口。
- 真正的 Wiki UI 仍位于 `frontend/src/apps/wiki/WikiApplication.tsx`，由 `frontend/src/apps/registry.ts` 动态 import。
- `frontend/src/app-host/ApplicationHost.tsx` 在启动 Run 后直接加载 NoteMeld 自身的 React 组件，而不是加载应用包资源。
- 当前测试 `frontend/tests/applicationHostContracts.test.mjs` 明确断言 Wiki 必须来自 `@/apps/wiki/WikiApplication`，这与应用独立化目标相冲突。
- Tauri 目前将 NoteMeld 仓库内的 `applications/` 作为资源打包；没有独立应用仓库的构建、安装、版本切换和资源目录配置。

## 2. 本次目标

实现真正的应用包边界：

1. NoteMeld 主程序不得 import 任意应用的 React/TypeScript 源码。
2. Wiki UI 从 NoteMeld `frontend/src/apps/` 移出，作为独立应用项目构建为静态 HTML/CSS/JS 包。
3. Host 只读取 manifest，用户点击后加载应用包的 `ui.entry`。
4. 应用 UI 使用版本化 Application SDK/Bridge，通过 `postMessage` 或等价受控通道调用 `wiki.read`，不得直接依赖 NoteMeld service、组件、路由或内部类型。
5. 桌面和 Web 共用应用包格式与 Bridge 语义；宿主只替换资源加载和 runtime adapter。
6. 应用安装目录、内建应用目录和用户应用目录都可以独立配置，并支持按 app id/version 选择不可变包。

## 3. 明确不做

- 本次不实现移动端原生 UI；移动端只保留平台声明和独立入口扩展点。
- 本次不实现公开应用市场、远程下载、自动升级或 Agent 自动生成应用。
- 不让应用 UI 读取 session token、宿主 DOM、Tauri API、SQLite 或绝对文件路径。
- 不保留 `frontend/src/apps/registry.ts` 作为应用注册机制，也不保留 Wiki React 源码的兼容 import。

## 4. 目标目录和依赖方向

新增独立应用仓库 `notemeld-applications/`，目录形态：

```text
notemeld-applications/
└── apps/wiki/
    ├── manifest.json
    ├── package.json
    ├── src/
    ├── public/
    ├── dist/
    │   └── ui/index.html
    └── README.md
```

NoteMeld 只依赖应用包产物和协议，不依赖该仓库的源代码、Node 模块或内部组件。应用仓库通过 release/package 产物交付；开发态可通过 `NOTEMELD_APPLICATIONS_DIR` 指向本地包目录。

## 5. 实施方案

### Host

- 将应用包根目录解析改为环境变量、桌面资源目录和开发态外部目录的有序查找。
- 增加受控应用资源读取/加载入口，只允许读取当前 manifest 声明的 `ui.entry` 及包内静态资源。
- Application Host 由“动态 import 组件”改为“创建应用 iframe/WebView/等价隔离容器”。
- 建立 Host Bridge：应用发送 `{type, request_id, capability, method, input}`，Host 校验 `app_id + instance_id + run_id`、manifest 和权限后调用后端 capability，再返回结构化结果。
- UI 加载失败、Bridge 超时、来源不匹配和能力拒绝必须进入现有 failed/needs-attention 状态。

### Wiki 应用

- 将图谱展示、文章详情和交互逻辑迁移到独立应用仓库。
- Wiki 应用只依赖浏览器标准 API、应用 SDK 和自身依赖，不引用 `@/components`、`@/services`、`@/pages` 或 NoteMeld store。
- 保留 `wiki.read.graph`、`wiki.read.article` 的数据语义，数据事实源仍为 NoteMeld Wiki store。
- 删除 NoteMeld 内的 `frontend/src/apps/wiki/`、`frontend/src/apps/registry.ts` 以及对应旧契约断言。

### 打包与安装

- 开发态由 `NOTEMELD_APPLICATIONS_DIR` 指定应用包根目录。
- 桌面态把已构建的应用包作为 Tauri resource，Host 从资源目录读取，不将应用源码编译进 NoteMeld 前端 bundle。
- 应用 catalog 只来自 manifest；应用包版本和 digest 进入应用注册记录。
- 本次先支持内建/本地包目录，安装升级 API 作为后续增量，但目录和版本模型必须兼容它。

## 6. 测试方案

- 后端：应用根目录发现、manifest/ui.entry 读取、路径越权、版本/digest、资源访问和 Bridge 身份校验。
- 前端：验证 Application Host 不再出现应用源码 import；验证 iframe/resource loader、postMessage request/response、来源校验、超时和错误状态。
- 独立应用：在 `notemeld-applications` 内独立构建 Wiki，并用静态服务器验证不依赖 NoteMeld 源码即可加载。
- 集成：应用列表 → 点击 Wiki → 创建 Run → 加载独立 HTML → Bridge 读取 graph → 点击节点 → Bridge 读取 article。
- 回归：NoteMeld 主程序构建产物中不应出现 `WikiApplication` 或 `src/apps/wiki` 模块；旧 `/wiki` 路由继续不存在。

## 7. 风险与回滚

- 风险：Wiki 依赖的 Sigma/Markdown/样式组件目前来自 NoteMeld 前端，需要在独立应用中重新声明和打包。
- 风险：Tauri resource 路径和浏览器开发态静态资源路径不同，需要分别验证。
- 风险：Bridge 的 postMessage 来源校验不能依赖固定开发端口，必须使用 Host 生成的实例上下文和允许来源。
- 回滚：保留 Wiki domain service、graph/article 数据和 `wiki.read` capability；只回滚 Host loader 与应用包资源配置，不恢复旧 `/wiki` 路由。
