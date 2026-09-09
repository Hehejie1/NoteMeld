# NoteMeld 架构与数据迁移说明

更新时间：2026-06-09

## 1. 产品形态

NoteMeld 是一个本地优先的 AI 知识工作台，核心能力包括多来源内容采集、音频转写、LLM 总结、笔记沉淀、Wiki/知识图谱、向量检索、模型与下载器配置、本地 HTTP MCP，以及整库迁移。

整体采用四层结构：

- 前端：React + Vite + TypeScript，负责工作台 UI、任务进度轮询、桌面/浏览器差异化交互。
- 后端：FastAPI + SQLite + 本地文件系统，负责采集、转写、总结、Wiki、向量索引、迁移和 MCP 服务。
- 桌面端：Tauri 2，负责启动 Python sidecar、注入运行时配置、提供系统文件弹窗和桌面能力。
- 打包层：PyInstaller + Tauri bundle + hdiutil，负责将 Python 后端、前端静态资源、Tauri 壳和 ffmpeg 打成可安装应用。

## 2. 运行模式

NoteMeld 支持三种运行模式，并通过 `NOTEMELD_RUNTIME_MODE` 区分：

- `source-script`：通过 `run_notemeld.sh` 在源码目录同时启动后端和前端，默认前端端口 `3015`，后端端口 `8483`。
- `source-cli`：通过 `notemeld` / `notemeld start` 启动，用于源码安装后的本地使用或调试。
- `desktop`：通过 Tauri App 启动，固定绑定 `127.0.0.1:8483`，启动 Python sidecar，并向前端注入运行时配置。

运行时识别由后端 `backend/app/core/runtime_mode.py` 和前端 `frontend/src/utils/runtime.ts` 共同完成。

## 3. 前端架构

前端位于 `frontend/`，技术栈包括 React 19、Vite、TypeScript、React Router、Zustand、Tailwind、Radix/shadcn 组件、Ant Design、Markdown 和 Markmap。

关键入口：

- `frontend/src/main.tsx`：React 挂载入口。
- `frontend/src/App.tsx`：路由入口和桌面/浏览器路由模式切换。
- `frontend/src/utils/request.ts`：Axios 请求封装。
- `frontend/src/utils/runtime.ts`：桌面运行时注入、API Base URL 解析。
- `frontend/src/hooks/useCheckBackend.ts`：后端健康检查和桌面 sidecar 就绪门禁。
- `frontend/src/pages/HomePage/`：笔记生成、聊天输入、Markdown 展示、导出和复制入口。
- `frontend/src/pages/SettingPage/`：模型、风格、用量等设置页面。
- `frontend/src/services/`：按业务模块封装后端 API。

浏览器模式使用 `BrowserRouter`，桌面模式使用 `HashRouter`，避免桌面静态资源路径刷新问题。

## 4. 后端架构

后端位于 `backend/`，入口为：

- `backend/main.py`：FastAPI app 创建、生命周期、CORS、静态资源挂载、Uvicorn 启动。
- `backend/desktop_entry.py`：桌面 sidecar 入口。
- `backend/app/__init__.py`：路由统一注册。

主要目录职责：

- `backend/app/routers/`：API 路由层。
- `backend/app/services/`：业务服务层，包括笔记、聊天、Wiki、向量索引、导入、转写等。
- `backend/app/db/`：SQLAlchemy、SQLite、DAO 和数据库初始化。
- `backend/app/gpt/`：LLM Provider、Prompt、工具调用和请求封装。
- `backend/app/downloaders/`：Bilibili、Douyin、YouTube、Kuaishou、本地文件等下载器。
- `backend/app/transcriber/`：Whisper、MLX、Groq、Bcut、快手等转写实现。
- `backend/app/services/ingestion/`：文档/网页/素材摄入流水线。
- `backend/app/utils/storage_paths.py`：统一数据路径定义。
- `backend/app/mcp/`：本地 HTTP MCP 工具定义、调用封装和鉴权。

核心 API 按模块拆分，例如：

- `/api/note`
- `/api/chat`
- `/api/provider`
- `/api/model`
- `/api/wiki`
- `/api/ingestion`
- `/api/migration`
- `/api/mcp`
- `/mcp`

## 5. 数据与存储

默认数据根目录由 `NOTEMELD_DATA_DIR` 控制；未配置时，源码模式使用仓库下 `vector_db`，桌面模式使用系统 App Data 目录。

主要路径由 `backend/app/utils/storage_paths.py` 统一定义：

- `notemeld.db`：SQLite 主数据库。
- `note_results/`：笔记结果、Markdown、转写、辅助 JSON。
- `uploads/`：上传文件和附件。
- `static/`：运行时静态资源。
- `static/screenshots/`：截图资源。
- `models/`：本地模型。
- `chroma/`：向量库。

桌面端会在 Tauri 启动 sidecar 时注入这些路径，避免数据写入应用包内部。

## 6. 笔记生成链路

视频、网页和上传文档最终都会进入统一的任务状态体系：

1. 前端或 MCP 提交内容来源、模型、Provider、风格和附加参数。
2. 后端创建或复用 conversation，并通过 `register_task_conversation()` 记录任务输入。
3. 后台任务根据平台选择下载、字幕、转写、网页兜底或上传文档解析链路。
4. Refine Engine 对长内容执行 Plan / Map / Reduce。
5. 生成 Markdown、截图、知识包和 Wiki 文件，并写入 `note_results/`。
6. 前端或 MCP 通过任务状态接口轮询，完成后读取 Markdown。

上传文件入口会先执行扩展名、MIME 和大小校验。为兼容浏览器对 `.md` 等文件的识别偏差，Markdown 上传允许 `application/octet-stream` 和 `binary/octet-stream`，但仍受扩展名与内容签名约束。

## 7. MCP 架构

NoteMeld 在后端提供本地 HTTP MCP endpoint：

```text
http://127.0.0.1:8483/mcp
```

桌面 DMG 模式固定绑定 `127.0.0.1:8483`，MCP endpoint 固定为 `http://127.0.0.1:8483/mcp`。MCP 是后端 FastAPI 路由，不是独立 daemon；NoteMeld 退出时后端 sidecar 和 MCP 一起停止。

MCP 路由位于 `backend/app/routers/mcp.py`，工具定义和业务封装位于 `backend/app/mcp/service.py`。

当前 MCP 支持：

- `generate_note`：从视频或网页 URL 创建结构化 Markdown 笔记。
- `get_task`：按 `taskId` 查询笔记生成状态。
- `get_note`：按 `taskId` 读取生成后的 Markdown。
- `list_models`：列出本地已启用 Provider 和模型，不暴露 API Key。
- `notemeld_import_note`：导入现成 Markdown，并后台触发 Wiki 抽取。
- `notemeld_search_notes`：按标题搜索笔记。
- `notemeld_read_note`：按标题读取笔记内容。
- `notemeld_search_wiki`：搜索结构化 LLM Wiki。
- `notemeld_read_wiki_page`：读取白名单 Wiki concept/entity 页面。

`generate_note` 兼容 BiliNote 风格参数：

- `url` / `videoUrl`：视频或网页链接。
- `model` / `modelName`：可选模型名；省略时自动选择本地启用模型。
- `providerId`：可选 Provider；省略时随模型自动选择。
- `maxWaitSeconds`：等待 Markdown 的最长时间。
- `pollIntervalSeconds`：内部轮询间隔。

短任务会直接在 MCP `content.text` 中返回 Markdown；长任务超过 `maxWaitSeconds` 后返回 `taskId` 和下一步提示，客户端可继续调用 `get_task` 与 `get_note`。

远程访问时可通过 `NOTEMELD_MCP_TOKEN` 启用 Bearer Token 校验；本地默认适配 Claude Code、Cursor、Codex、OpenClaw 和 Trae 等 HTTP MCP 客户端。

## 8. 桌面端架构

桌面端位于 `desktop/src-tauri/`。

关键文件：

- `desktop/src-tauri/src/lib.rs`：Tauri 主逻辑，负责端口分配、sidecar 启动、运行时注入、窗口展示和退出清理。
- `desktop/src-tauri/tauri.conf.json`：Tauri 产品配置、窗口、bundle、updater、资源配置。
- `desktop/src-tauri/src/main.rs`：桌面入口。

桌面启动流程：

1. Tauri 启动应用。
2. 分配可用后端端口。
3. 准备 app data、log、database、uploads、static、models 等目录。
4. 启动 Python backend sidecar。
5. 注入 `window.__NOTEMELD_RUNTIME__`，包含 `apiBaseUrl`、运行模式和桌面标识。
6. 前端等待 runtime ready 后开始后端健康检查。
7. 后端就绪后显示主窗口。

桌面端提供的关键能力：

- 系统保存文件弹窗。
- 系统打开文件弹窗。
- 原生文件拖拽真实路径。
- 后端 sidecar 生命周期管理。
- 外部 URL 打开。
- 自动更新配置。

## 9. 打包与发布架构

macOS 基础打包入口：

- `packaging/scripts/build-backend-macos.sh`
- `packaging/scripts/build-desktop-macos.sh`

统一 DMG 发布入口：

- `.trae/skills/notemeld-dmg-packaging/scripts/package-notemeld-dmg.sh`

打包流程：

1. 使用 PyInstaller 将 `backend/desktop_entry.py` 打成 `dist/notemeld-backend`。
2. 将 sidecar 复制到 `desktop/src-tauri/bin/backend/notemeld-backend`。
3. 校验 ffmpeg/ffprobe 可执行，并拒绝依赖 Homebrew Cellar/opt 动态库的不可分发二进制。
4. 压缩 portable ffmpeg/ffprobe 到 `desktop/src-tauri/resources/ffmpeg/ffmpeg-runtime-macos.zip`。
5. 执行前端 `vite build` 生成 `frontend/dist`。
6. 执行 `tauri build --no-bundle` 编译桌面二进制。
7. 执行 `tauri bundle --bundles app` 生成 `.app`。
8. 对 `.app` 执行 `codesign --verify --deep --strict`。
9. 使用 `hdiutil` 生成 `.dmg`，并在 DMG 中加入 `Applications -> /Applications` 快捷方式。

发布规则：

- 每次 macOS DMG 发布必须同时构建 Apple Silicon `aarch64` 和 Intel `x64` 两个架构。
- 本地测试包允许 ad-hoc 签名，但必须通过 `hdiutil verify`、挂载后 `codesign --verify --deep --strict` 和架构校验。
- 正式发布必须使用 `--release`，并强制 Developer ID 签名、Apple notarization、`stapler staple` 和 Gatekeeper 校验通过。
- 服务器发布建议使用 `--release --upload --public-verify`，上传后重新下载公网文件并校验 SHA256 与 DMG 完整性。

示例正式发布命令：

```bash
NOTEMELD_CODESIGN_IDENTITY="Developer ID Application: <Name> (<TEAMID>)" \
NOTEMELD_NOTARY_PROFILE="notemeld-notary" \
./.trae/skills/notemeld-dmg-packaging/scripts/package-notemeld-dmg.sh --release --upload --public-verify
```

当前产物位置：

- `desktop/src-tauri/target/aarch64-apple-darwin/release/bundle/dmg/NoteMeld_<version>_aarch64.dmg`
- `desktop/src-tauri/target/x86_64-apple-darwin/release/bundle/dmg/NoteMeld_<version>_x64.dmg`

## 10. 安全边界

当前安全边界以本地优先为核心：

- 后端默认面向本机运行，桌面模式由 Tauri sidecar 管理生命周期。
- MCP 写能力可通过 `NOTEMELD_MCP_TOKEN` 启用 Bearer Token。
- `list_models` 不返回 API Key。
- `get_note` 按 `taskId` 读取文件时会拒绝路径穿越。
- 上传文件受扩展名、MIME、最大大小和内容解析约束。
- DMG 正式发布必须经过 Developer ID 签名、公证和 Gatekeeper 门禁。

## 11. 文档与契约测试

与本文档同步的关键契约测试包括：

- `backend/tests/test_core_mcp_generation_tools.py`：验证 MCP 生成、轮询、Markdown 返回、默认模型选择和路径穿越防护。
- `backend/tests/test_core_upload_contracts.py`：验证 Markdown 上传兼容浏览器 octet-stream MIME。
- `frontend/tests/dmgPackagingContracts.test.mjs`：验证 DMG 打包脚本包含 Applications 快捷方式、Developer ID 签名、公证和 ffmpeg portable 依赖门禁。
- `frontend/tests/documentationContracts.test.mjs`：验证 README 和架构文档包含当前 MCP、上传和发布约束。

## 12. 近期维护原则

- README 面向用户，保留快速开始、MCP 配置、发布命令和常用验证入口。
- 架构文档面向维护者，记录真实运行链路、入口文件、发布门禁和测试映射。
- MCP 工具、上传白名单、DMG 发布规则发生变化时，必须同步 README、本文档和对应契约测试。
- 不再维护过期的安全治理长计划文档；可执行规则应进入脚本、测试和架构说明。
