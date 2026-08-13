# Current Architecture

更新时间：2026-06-19

本文只记录当前仓库真实系统事实，不描述理想化重构方案。新需求、方案、Bug 修复和代码改动前必须先阅读本文。

## 系统定位

NoteMeld 是本地优先的 AI 知识工作台。它把网页、本地文件、多平台视频、音频和 AI 对话加工为结构化 Markdown 笔记，并把每篇笔记继续抽取为 Wiki 知识包，供图谱、检索、问答和 MCP 工具复用。

产品路线不是传统“先堆原文再临时检索”的 RAG，而是 Wiki-First Retrieval：先沉淀结构化知识层，再检索和引用。

## 主要模块

- 前端：`frontend/`，React 19 + Vite + TypeScript + React Router + Zustand + Tailwind。负责工作台 UI、任务提交、进度轮询、Markdown/Wiki 展示、设置页面和桌面运行时门禁。
- 后端：`backend/`，FastAPI + SQLite + 本地文件系统。负责采集、下载、转写、LLM 总结、笔记保存、Wiki、向量索引、迁移和 MCP。
- 桌面端：`desktop/src-tauri/`，Tauri v2。负责启动 Python backend sidecar、注入运行时配置、控制窗口展示、桌面文件能力和自动更新。
- 打包层：`packaging/` + `.trae/skills/notemeld-dmg-packaging/`。负责 PyInstaller 后端 sidecar、前端静态资源、Tauri bundle、ffmpeg runtime、DMG/MSI 发布。
- 测试层：`backend/tests/` 和 `frontend/tests/`。以契约测试为主，覆盖运行时、MCP、上传、Wiki、迁移、桌面启动、打包规则等。

## 前端入口

- React 挂载入口：`frontend/src/main.tsx`。
- 路由入口：`frontend/src/App.tsx`。
- 桌面环境使用 `HashRouter`，普通 Web 使用 `BrowserRouter`，避免桌面静态资源刷新路径问题。
- 主要路由包括 `/`、`/new`、`/notes/:taskId`、`/wiki`、`/settings/*`、`/styles`、`/about`。
- Axios 请求封装：`frontend/src/utils/request.ts`。`baseURL` 优先取桌面注入的 `window.__NOTEMELD_RUNTIME__.apiBaseUrl`，其次 `VITE_API_BASE_URL`，最后 `/api`。
- 桌面 session token 通过 `X-NoteMeld-Session` header 注入所有 Axios 请求。
- 后端就绪门禁：`frontend/src/hooks/useCheckBackend.ts` 和 `BackendInitContext`。桌面 sidecar 未就绪时业务请求不能抢跑。
- 主要 API 调用集中在 `frontend/src/services/`。

## 后端入口

- 源码/服务入口：`backend/main.py`。负责加载 `.env`、创建 FastAPI app、初始化 DB、注册事件、挂载静态目录并启动 Uvicorn。
- 桌面 sidecar 入口：`backend/desktop_entry.py`，复用 `main.app`。
- app 工厂：`backend/app/__init__.py`。大部分 router 挂载到 `/api`，MCP router 直接挂根路径，实际 endpoint 为 `/mcp`。
- CORS 默认允许 `127.0.0.1:<frontend_port>`、`localhost:<frontend_port>`、`http://tauri.localhost`、`tauri://localhost`，可用 `NOTEMELD_CORS_ORIGINS` 扩展。

## 数据存储

默认数据根目录由 `NOTEMELD_DATA_DIR` 控制。未配置时，源码模式使用仓库下 `vector_db`；桌面模式由 Tauri 注入系统 App Data 目录。

统一路径定义在 `backend/app/utils/storage_paths.py`：

- `notemeld.db`：SQLite 主数据库。
- `note_results/`：任务结果、Markdown、状态文件、Wiki、转写、sidecar JSON。
- `uploads/`：上传文件和附件。
- `static/`：运行时静态资源。
- `static/screenshots/`：截图资源。
- `models/`：本地模型。
- `chroma/`：Chroma 向量库。

SQLite 模型位于 `backend/app/db/models/`，主要包含 provider、model、usage、conversation、note document、note style、template extraction task、video task 等。

Wiki 文件位于 `note_results/wiki/`：

- `contributions/*.json`：每篇笔记的结构化知识贡献。
- `sources/*.md`：来源页。
- `entities/*.md`：实体页。
- `concepts/*.md`：概念页。
- `graph.json`：图谱快照。
- `wiki_rebuild_job.json`：全局 Wiki 重建状态。

## 外部服务依赖

- LLM Provider：OpenAI / DeepSeek / Qwen / 任意 OpenAI 兼容 Provider。配置在 provider/model 相关表中。
- 视频/网页采集：Bilibili、YouTube、抖音、快手、视频号、本地视频、网页文章等下载器/解析器。
- 转写服务：Faster-Whisper、MLX-Whisper、Groq、必剪 BCut、快手等。
- 系统依赖：Python 3.11+、Node 20+、pnpm/corepack、ffmpeg。
- ChromaDB：本地向量库。
- Tauri 桌面能力：sidecar、系统文件弹窗、外链打开、自动更新。
- MCP 客户端：Trae、Claude Code、Cursor、Codex、OpenClaw 等 HTTP MCP 客户端。

## 核心业务链路

### 笔记生成链路

1. 前端或 MCP 提交来源、模型、Provider、样式和附加参数。
2. 后端创建或复用 conversation，并通过 `register_task_conversation()` 记录任务输入。
3. 后端写入任务状态文件 `note_results/{task_id}.status.json`，并在后台执行任务。
4. 视频链路由 `NoteGenerator.generate()` 处理：平台识别、下载、字幕/转写、截图、LLM 总结、Markdown 渲染、sidecar 保存。
5. 网页链路由 `WebNoteGenerator` 处理。视频链路下载、音频或转写失败时可降级到网页抓取。
6. 上传文档链路先经过 ingestion pipeline，再复用总结能力生成笔记。
7. 成功后 `save_note_to_file()` 写 `note_results/{task_id}.json` 等文件，`emit_note_result()` 同步 conversation message 和 `note_documents`。
8. 前端通过 `/api/task_status/{task_id}` 轮询。成功后读取 Markdown 和相关展示数据。

### Wiki 链路

1. 笔记任务完成总结后，`WikiPipeline.extract_contribution()` 只做单篇知识抽取并保存 contribution。
2. 单篇 contribution 包含 source、summary、topics、entities、concepts、claims、evidence、relations。
3. 完整 Wiki materialize 由 `WikiRebuildService` 后台执行。
4. Wiki rebuild 采用 latest-wins：新请求会取消当前 generation 并以最新请求重建。
5. `WikiPageMerger` 调用 LLM 合并页面时有超时控制，避免长期持锁或卡死。

### MCP 链路

- MCP endpoint 固定为 `http://127.0.0.1:8483/mcp`。
- MCP 是 FastAPI 路由，不是独立 daemon。NoteMeld 退出时 MCP 随后端停止。
- 本地请求默认免 token；远程或强制配置时使用 `NOTEMELD_MCP_TOKEN` Bearer Token。
- MCP 工具包括 `generate_note`、`get_task`、`get_note`、`list_models`、导入/搜索/读取笔记和 Wiki 页面。

## 本地运行方式

源码启动：

```bash
cp .env.example .env
bash run_notemeld.sh
```

默认地址：

- 前端：`http://127.0.0.1:3015`
- 后端：`http://127.0.0.1:8483`

前端单独运行：

```bash
cd frontend
pnpm install
pnpm dev
```

纯静态产品演示（不启动后端、不读取 SQLite 或业务文件）：

```bash
bash scripts/preview_static_demo.sh
# 可选：--port 4175 --no-open
```

演示构建由 `VITE_NOTEMELD_DEMO=true` 显式启用。`frontend/src/demo/` 在浏览器内提供合成 fixture、fail-closed 请求适配器、模拟任务状态机、场景控制栏和功能讲解抽屉；未实现的演示 endpoint 直接报错，不回退到正式 API。默认生产构建仍使用正式 BackendInit、Axios/fetch、Tauri 和后端链路。Vite 的 demo mode 使用 `/` 作为资源基址，使 Vite preview history fallback 下的 `/notes/*` 与 `/settings/*` 可直接打开或刷新；正式构建继续保持 `./` 资源基址。

后端单独运行通常由 `run_notemeld.sh` 管理；脚本会创建 `.venv`、安装依赖、准备转写器并启动后端。

桌面开发：

```bash
cd desktop
pnpm install
pnpm tauri:dev
```

核心回归：

```bash
scripts/run_core_regression.sh
```

## 线上部署方式

当前仓库主要面向本地自托管和桌面发布。

- CLI 安装方式通过 `scripts/install.sh` / `scripts/install.ps1` 注册 `notemeld` 命令，默认数据在用户目录 `.notemeld`。
- 桌面发布通过 PyInstaller + Tauri 打包，macOS 产出 `.dmg`，Windows 产出 `.msi`。
- macOS 正式发布必须同时覆盖 Apple Silicon `aarch64` 和 Intel `x64`，并经过 Developer ID 签名、公证、staple、Gatekeeper、挂载后 codesign、SHA256 公网回验。
- Tauri updater endpoint 当前配置在 `desktop/src-tauri/tauri.conf.json`。

## 当前已知边界

- 当前系统是本地优先，不是多租户云服务。
- 后端默认绑定本机端口，桌面模式由 sidecar 管理生命周期。
- Provider API Key 存在本地 SQLite，不应通过接口、日志、MCP 或前端暴露。
- `note_results/` 同时承载任务状态、结果、Wiki 和 sidecar 调试文件，改动前必须确认文件兼容性。
- Wiki rebuild 必须可取消，且不能在笔记保存路径同步做完整 materialize。
- 桌面首次启动可能慢，前端必须保留后端 ready 门禁和足够长的等待窗口。
- 打包脚本对 ffmpeg runtime、签名、公证、双架构有强约束，不能为“本地能跑”而删。
- 现有文档中存在 PRD/架构说明，但新需求必须基于本目录的系统事实做增量 Change Spec。
