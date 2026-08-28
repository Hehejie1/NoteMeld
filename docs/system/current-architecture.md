# Current Architecture

Application Package 与运行时协议的唯一规范源是 [`application-protocol-v1.md`](application-protocol-v1.md)。

更新时间：2026-08-27

本文只记录当前仓库真实系统事实，不描述理想化重构方案。新需求、方案、Bug 修复和代码改动前必须先阅读本文。

## 系统定位

NoteMeld 是本地优先的个人知识编译器。核心范式是：AI 编译知识，人验证和消费。它把网页、本地文件、多平台视频、音频和 AI 对话加工为结构化 Markdown 笔记，并把每篇笔记继续抽取为 Wiki 知识包，供图谱、检索、问答和 MCP 工具复用。

产品路线不是传统"先堆原文再临时检索"的 RAG，也不是"人手动整理"的传统 PKM，而是 Wiki-First Retrieval：AI 先编译结构化知识层，人再验证、检索和引用。

## 主要模块

- 前端：`frontend/`，React 19 + Vite + TypeScript + React Router + Zustand + Tailwind。负责工作台 UI、任务提交、进度轮询、Markdown/Wiki 展示、设置页面和桌面运行时门禁。
- 后端：`backend/`，FastAPI + SQLite + 本地文件系统。负责采集、下载、转写、LLM 总结、笔记保存、Wiki、向量索引、迁移和 MCP。
- 桌面端：`desktop/src-tauri/`，Tauri v2。负责启动 Python backend sidecar、注入运行时配置、控制窗口展示、桌面文件能力和自动更新。
- 打包层：`packaging/` + `.trae/skills/notemeld-dmg-packaging/`。负责 PyInstaller 后端 sidecar、前端静态资源、Tauri bundle、ffmpeg runtime、DMG/MSI 发布。
- 测试层：`backend/tests/` 和 `frontend/tests/`。以契约测试为主，覆盖运行时、MCP、上传、Wiki、迁移、桌面启动、打包规则等。
- Agent runtime：`backend/app/agent_host/` 通过独立仓库 `notemeld-agent-sdk` 的 Python binding 加载 Rust native runtime；Web、Tauri 和 CLI 都只调用 `/api/agent/v1`，Router 再通过无内存状态的 `AgentHostEntry` 进入同一 Host 生命周期。Turn 由后台 executor 执行，事件和终态继续写入 NoteMeld 的 `agent_turns` / `agent_events` / conversation 存储。产品能力通过 `agent_host/capabilities.py` 和 `NoteMeldToolDriver` 适配到 SDK；SDK 在每轮模型请求前通过 `tool.describe` 获取有界能力描述，模型→工具→模型链路由 Rust runtime 调度；取消先进入 `cancelling`，最终 `cancelled` 只能由 native Turn 终态完成。危险或未知工具由 SDK 发出 `approval.required` 并暂停原 Turn；Web/CLI 的 approval resolve 通过同一个 native runtime 控制面原子唤醒，Host 只投影 `waiting_approval/running` 与事件。
- I04 集成将 plugin/candidate router 和各自 migration registry 统一挂入同一个 FastAPI/SQLite bootstrap；设置导航同时提供插件运行、Agent 任务诊断和 candidate 审批入口。candidate 只允许人工验证/审批/拒绝，plugin candidate 审批后仍必须回到 N03 installer 的校验、权限和 active-pointer 流程。
- Application Host：`backend/app/applications/` 是独立于 Agent/Plugin 的应用域。`applications/*/manifest.json` 是内建应用包的目录边界，Host 启动时只扫描、校验并生成 catalog，不执行应用 UI/backend；应用 API 统一挂载在 `/api/applications`，通过 `ResponseWrapper` 和 session token 保护。桌面协议由 Host 监督私有 stdin/stdout process-JSONL，应用不得监听公开端口，Host 负责启动、超时、退出、取消和回收；Web 协议固定为 Host gateway 管理的 `managed-worker` invocation seam，外部云 worker 部署和用户应用包安装仍不属于第一版。
- Wiki application：Wiki 由 `frontend/src/apps/wiki/` 作为第一个内建应用包，包含独立 `manifest.json`，通过 Application API 的 `wiki.read` capability 读取既有 Wiki store 的 graph/article。应用中心只加载 manifest 元数据，用户进入 `/applications/:appId` 后才动态加载 Wiki UI。旧 `/wiki` 前端 route 和导航已移除；Wiki pipeline、`note_results/wiki`、Note authority 和旧 Wiki API 仍是数据事实源，其他学习组件可复用图谱渲染原语。默认 application workspace 可在 `/settings/applications` 配置。

## 前端入口

- React 挂载入口：`frontend/src/main.tsx`。
- 路由入口：`frontend/src/App.tsx`。
- 桌面环境使用 `HashRouter`，普通 Web 使用 `BrowserRouter`，避免桌面静态资源刷新路径问题。
- 主要路由包括 `/`、`/new`、`/notes/:taskId`、`/applications`、`/applications/:appId`、`/settings/*`、`/styles`、`/about`；不存在旧 Wiki UI route `/wiki`。
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

默认数据根目录固定为项目（或安装应用）下的 `vector_db`。桌面模式由 Tauri 注入应用数据目录下的 `vector_db`；`NOTEMELD_DATA_DIR` 只用于运行模式注入数据根，不再允许各子目录单独改写。

统一路径定义在 `backend/app/utils/storage_paths.py`：

- `notemeld.db`：SQLite 主数据库。
- `note_results/`：任务结果、Markdown、状态文件、Wiki、转写、sidecar JSON。
- `uploads/`：上传文件和附件。
- `static/`：运行时静态资源。
- `static/screenshots/`：截图资源。
- `models/`：本地模型。
- `chroma/`：Chroma 向量库。
- `tmp/`：后端运行时临时文件；NoteMeld 业务临时文件不得写入项目根目录或系统临时目录。

所有日志统一写入项目（或安装应用）下的 `logs/`，由 `NOTEMELD_LOG_DIR` 注入桌面/CLI 的日志根。`NOTE_OUTPUT_DIR`、`VECTOR_DB_DIR`、`STATIC_DIR`、`OUT_DIR`、`UPLOAD_DIR`、`DATA_DIR` 等旧子目录变量不再生效。

SQLite 模型位于 `backend/app/db/models/`，主要包含 provider、model、usage、conversation、note document、note style、template extraction task、video task 等。

Wiki 文件位于 `vector_db/note_results/wiki/`：

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
4. 外部链接入口统一调用 `official-link-note:create` capability；独立 `notemeld-plugins/plugins/official-link-note/` 负责平台路由，稳定 Host adapter 再调用现有视频/网页生成服务。
5. 视频链路仍保留平台识别、下载、字幕/转写优先、截图、多源总结、Markdown 渲染、sidecar 保存；下载/音频/转写失败继续降级到网页抓取。网页链接通过同一 capability 进入网页抓取/总结链路。
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
- MCP 工具包括 `generate_note`、`get_task`、`get_note`、`list_models`、导入/搜索/读取笔记和 Wiki 页面；N05 新增 `notemeld_create_note`、`notemeld_link_notes`、`notemeld_note_relations`，这些写入经 Agent Host 的 `NoteMeldCapabilityRegistry`、N02 Note adapter 和 Note authority 完成，MCP/CLI 不直接写 SQLite/Event。Agent capability discovery/invoke 也通过 `/api/agent/v1/capabilities*` 提供同一 Host seam。

### Agent free-chat 渐进式能力路由

- `AGENT_CHAT_ENABLED=true` 时，free-chat 首轮不再预执行完整 `WikiSearch`；只读取并缓存 `wiki/graph.json` 的节点、社区和名称元数据，形成最多 1200 字符的 L0 能力地图。
- Agent 初始只注册 `capability_discover`、`capability_describe`、`capability_invoke` 三个固定元工具。Wiki、builtin、memory、workspace、Skill 和第三方 MCP 都以带命名空间的 capability id 进入请求级 `CapabilityRegistry`。
- L1 只返回候选名称与摘要；L2 只展开选中能力的 schema；L3 才执行 Wiki 搜索/页面读取、Skill 或 MCP 工具。L3 Wiki 结果动态写回原有 `sources` 列表。
- 第三方 MCP 只读取 `enabled=true` 的 server 配置；L0/L1 不连接 server，L2/L3 才执行单 server 工具发现，请求完成、异常或 SSE 断开时关闭 adapter。
- 同一请求内对同一 MCP server 的并行 L2/L3 发现通过 server 级异步锁合并为一次；设置 API 统一移除 auth 并把 headers/env 值替换为 `***`，编辑时由后端恢复已有凭证。
- `use_wiki=false` 同时禁止注册和执行 Wiki capability。生产 Agent 不存在 `AGENT_CHAT_ENABLED` 或 legacy free-chat runtime fallback。

### 主动学习空间链路

- 主动学习空间是会话工作区中的持久化知识产物，不修改全局 `wiki/graph.json`。领域对象由 `models/learning_canvas.py` 定义，完整状态写入 `workspaces/{conversation_id}/canvases/{canvas_id}.json`，会话消息只保存 `canvas_id`、目标、状态和节点数等轻量索引。
- `LearningCanvasService` 固定先检索本地 Wiki；arXiv 与 GitHub 是每次学习构建都启用的基线来源，不由 Settings 开关。只有 Tavily 已配置 key，或 SearXNG 已配置 endpoint 时才自动追加普通 Web。外部 provider 独立失败时保留成功结果；只要本地内容可用，画布会以 `blocked_external` 显示外部缺口而不清空已有内容。
- 学术与 GitHub 搜索结果在 V1 中是带类型和来源 URL 的候选证据，不自动写入 Wiki，也不自动采集全文。后续采集/编译必须经过用户确认并复用现有长任务能力。
- `LearningSessionService` 管理 `unknown → exposed → learning → provisional → mastered`。展示学习单元只产生 `exposed`；通过 recall/explain 与 apply/transfer 后进入 `provisional`，至少 48 小时后的 review 再次通过才进入 `mastered`。
- Canvas 的 PATCH、start unit 和 evidence 提交均由 `LearningCanvasStore.update()` 在同一路径锁内完成完整 load→mutate→原子 replace，避免并发证据或用户覆盖字段互相丢失。
- free-chat 的请求级 `CapabilityRegistry` 仍以 `learning:*` 命名空间渐进披露四个能力：构建、读取/恢复最近画布、开始学习单元、提交学习证据。首页“学习”标签则是确定性入口：它不等待模型选择工具，直接调用 canvas API。`learn` 只是前端提交意图，持久会话继续使用 `mode=chat`，不新增 SQLite 枚举。
- 画布创建后写入一条 compact `learning_canvas` 消息，包含目标、节点数、来源类型、推荐起点和引导，不包含完整 nodes。对话流渲染该摘要；HomePage 从最新消息恢复 `canvas_id`，把完整 Sigma 图、路径、当前单元和复习队列放到右侧学习面板。若同会话已有笔记，右侧可以在“学习 / 笔记”间切换。
- 前端同步等待多来源研究完成时不设置比 provider 总预算更短的固定超时；学习构建互斥保存在共享 task store，跨 composer 挂载仍生效。canvas API 返回成功是事务成功边界，后续消息 patch、会话 reload 或导航失败不得回写成构建失败；只有用户仍停留在发起路径时才自动打开结果会话。
- 搜索凭证写入本机 `config/research_search.json`。GET 只返回 `*_key_set` 布尔值，画布、日志和 API 响应都不得包含原始密钥。学习卡与设置页都等待 BackendInit ready 后才发请求。

#### 研究笔记白板（2026-08-13 主交互）

- 首页“学习”现在以主动研究而不是课程式教学为主。`ResearchNoteCompiler` 先过滤本地 Wiki 和外部候选，再由所选 LLM 判断是否存在会改变研究对象的重大歧义；有效歧义只返回一个 `clarifying` 问题，不创建 Note。模型不可用、输出非法或证据不足时使用可追溯的确定性研究框架降级。
- 外部论文、GitHub 仓库和网页是 evidence candidate，不能直接转换为白板节点。compiler 只允许生成 `topic/concept/claim/evidence/conflict/case/question` 节点，并删除不存在于输入证据中的 `source_ids`。
- 明确目标通过 `NoteImportService` 创建标准研究 Note，复用 `note_results/{task_id}.json`、`note_documents`、向量索引和异步 Wiki contribution；`LearningCanvas.version=2` 通过 `document_task_id` 绑定该 Note。对于研究会话，白板与 Note 两条线分离：白板保存研究草稿与关系拓扑，Note 保存用户确认后的线性事实快照。
- HomePage 继续复用中间对话/右侧内容分栏，右侧在“笔记 / 白板”之间切换。白板首屏只显示图和当前焦点，不再同时倾倒学习路径、掌握度、复习队列和来源墙；version=1 历史画布仍可读取。
- 白板视图占满右侧切换栏以下的剩余空间，不再套页面级滚动容器。节点默认以紧凑图形和短标签呈现，只有选中节点在画布内出现一张可关闭的摘要浮层；浮层继续复用 `whiteboard_node` 引用进入对话。
- Markdown 选文与 `whiteboard_node/whiteboard_selection` 都可“添加到对话”。前端 Zustand 最多保存 8 条待发送引用，单条快照最多 2000 字（`whiteboard_selection` 在后端 authority resolver 后可扩展到 12000 字）；引用同时写入 user message meta，并通过 free-chat 或 learning create 的 `context_refs` 传入后端。后端重新校验、截断并把它们隔离为“资料而非指令”。仅经过当前服务端 resolver 的消息 row 会写入内部 `context_refs_authority_version=1`；历史/legacy row 默认为 0，同 locator 的 PATCH 也必须重新解析，不能只凭 `role=user` 复用快照。
- `suggested_actions` 分为 `focus` 和 `research`：focus 只派发前端节点聚焦事件，不调用模型；research 只预填研究问题，由用户提交后才触发新研究。
- NoteImportService 返回成功是研究事务成功边界。之后 canvas 保存或 compact message 写入失败只追加安全的 `projection_save_failed/guide_message_failed`，不得让 API 报研究失败或诱导重复创建 Note；Wiki 状态继续独立演进。

### 模型运行配置链路

- Provider 编辑页的模型区只保留“添加模型”入口和已添加模型列表。居中弹窗一次提交模型名、上下文长度、图像支持和流式支持；不提供已添加模型的编辑弹窗。
- `model_runtime_catalog.json` 随源码和 PyInstaller sidecar 发布。解析时先做规范化后的精确匹配，再按目录顺序做家族通配；未命中、目录缺失、损坏或 schema 非法时回退 `4096 / false / true`。目录值只是离线建议，不是端点探测结果。
- `ensure_model_runtime_schema()` 在初始化建表后运行。只有旧 `models` 缺少任一运行字段时，才在同一事务补列并清空 `models` / `model_capabilities`；字段完整时重复启动不清空。补建 `(provider_id, model_name)` 唯一索引也不清空完整 schema 的现有行。
- 旧 SQLite 合并继续导入 Provider、Note、Conversation、Usage 和任务等数据，但一律跳过 legacy `models` 行，即使旧表已含三个运行字段也不例外；旧模型配置必须由用户在当前弹窗中重新确认并添加。
- `POST /api/models/defaults` 只返回目录/fallback 建议；`POST /api/models` 必须显式保存三项运行字段。列表和运行时后续读取用户保存行，不用目录理论值或探测缓存覆盖。
- 模型选择后的 defaults 请求 pending 期间，弹窗同时禁用保存按钮并在保存 handler 内防御；只有当前 request version 能结束 loading。快速切换或关闭会使迟到响应失效，defaults 失败后解除 loading 并允许用户确认 fallback。

## LLM 调用层（notemeld-ai 抽象）

后端 LLM 调用分两层：

- `backend/app/ai/`：notemeld-ai 统一 LLM 抽象层。对外暴露 `Models` 集合（`create_models()`）、`Provider` 抽象、`LLMContext`、`Tool`/`Type` schema、`StreamEvent` 流式事件、`Usage` 收集器和标准化异常。内部通过 `ModelService` 读取 providers/models/model_capabilities 表，按 `provider_id` + `model_name` 解析到具体 Provider（OpenAI 兼容），统一写 usage 记录。
- `backend/app/gpt/`：旧 GPT 编排层。`UniversalGPT` 负责摘要/合并/checkpoint/retry 等编排逻辑，`GPTFactory.from_config` 是旧工厂入口。

运行时模型解析规则：

- `Models.get_model(provider_id, model_name)` 只能解析 `models` 表中已保存的模型；仅 Provider 存在但模型未添加时返回 `None`。
- `models.context_window_tokens` / `supports_vision` / `supports_stream` 会装载到运行时 `Model`，并经 `ModelConfig` 透传到 `NotemeldGPT` / `UniversalGPT`。用户保存值是权威；`model_capabilities` 的 vision 探测值不得把保存的 `false` 覆盖为 `true`。
- `Models.stream()` 对 `supports_stream=false` 的模型只调用一次 Provider `complete()`，再把文本、thinking 和 tool calls 转换为现有 `StreamEvent` 协议；调用方无需分支，且每次 Provider 请求仍只写一条 usage。
- `Models.stream()` / `Models.complete()` 在 Provider 调用前按已保存的 `context_window_tokens` 构造上下文副本并统一裁剪；估算使用 UTF-8 字节数除以 3 向上取整、每消息固定 overhead 和每图 1200 token reserve。system 与最新 user 必留，tool call/result 成组保留或删除，原会话消息不被改写；必留输入仍超限时抛出可分类的 `ContextBudgetExceededError`。
- Note/Web/Wiki retry/Research 等 `NotemeldGPT` 编排入口统一通过 `ModelService.build_saved_model_config()` 从保存行构造 `ModelConfig`，避免非主入口落入 `4096/false/true` 兼容默认。
- `NotemeldGPT.create_chat_completion()` 是含 `image_url` 请求的最终 vision 硬闸门；保存的 `supports_vision=false` 在创建 notemeld-ai Provider 请求前抛出可分类的 `ProviderCapabilityError(capability="vision")`。`model_capabilities` 的探测值不能授权或否决已保存的 vision 运行值。

迁移现状（P0，过渡期）：

- 适配器 `backend/app/gpt/notemeld_gpt.py::NotemeldGPT` 继承 `UniversalGPT`，只 override `create_chat_completion`，内部走 notemeld-ai `Models.complete()`（asyncio.run 包同步调用），保留 retry + phase 3 级回退，返回 OpenAI 形状 response 兼容 `_extract_message_content` 和外部 caller。
- `LLMContext.timeout` 会进入 OpenAI SDK 请求；Wiki 页面合并沿用 `NOTEMELD_WIKI_MERGE_TIMEOUT_SECONDS`（默认 20 秒），避免迁移后退回 SDK 默认长超时。
- 所有 chat-completion 调用点已切到 `NotemeldGPT`：`services/chat_service`、`services/note._get_gpt`、`services/web_note._get_gpt`、`services/wiki_page_merger`、`services/summary_refine_engine`、`services/note_style`（模板提取 + image_vlm_analyzer）、`routers/note.retry_wiki_extraction`。
- `GPTFactory` + `UniversalGPT` 过渡期保留供回滚；`GPTFactory.from_config` 已加 `DeprecationWarning`，至少保留 1 个 Beta 版本不删除。
- `services/model.py` 的 `list_models` 仍走 `GPTFactory`（非 chat-completion 路径，刻意不迁移）。
- usage 双写对齐由 `backend/tests/ai/test_provider_compat.py` 覆盖（GPTFactory/UniversalGPT vs notemeld-ai 逐字段断言）；迁移点由 `test_chat_service_migration`、`test_note_generator_migration`、`test_t11_migration` 覆盖。
- 非流式 `CompleteResult` 除 final `content` 外还保留可选 `thinking` 与真实 `finish_reason`；`NotemeldGPT` 在 OpenAI 形状兼容响应中透传为 `message.reasoning_content` 和 choice `finish_reason`。Wiki 抽取仍优先 final content，仅在 reasoning 中存在可完整解析的 JSON object 时恢复，不向日志或 UI 暴露推理原文。

## 笔记输出格式边界

- 笔记风格的 `output_formats` 是生成与持久化的共同契约：Markdown-only 风格要求模型直接返回裸 Markdown；HTML-only 与 HTML+Markdown 风格才以 HTML skeleton 为一等结构。
- 视频和网页笔记在写入 `note_results`、`note_documents` 与 Wiki 前共同经过 `services/note_output_normalizer.py`。归一化只剥离“整个文档恰好由单一 html/markdown fence 包裹”的确定性错误（允许前置标准来源引用），正文内部代码块保持原样；真实 HTML 到 Markdown 继续复用 `html_to_markdown`。
- Wiki 分块提取默认输出预算为 3200 token（可由 `WIKI_ANALYSIS_MAX_TOKENS` 覆盖），同时限制每块实体/概念/论点/证据/关系数量。推理模型没有 final JSON 时区分截断、仅推理、真正空响应和 Provider 网络错误，继续沿用 source-only partial 降级与重试入口。
- `UniversalGPT` 的笔记与合并分块同时满足 Provider 的 `max_request_bytes`（默认上限仍为 45MB）和模型 token 输入预算；移除超预算图片回退纯文本时会按无图预算重新分块。
- 视频多源采集保留用户原始 `extras`，网页搜索和有效画面/OCR 文本以 `SummaryInput.user_options.web_search_context/frame_context` 独立进入 weighted pack。map 阶段只发送当前字幕块、用户原始要求和 map 指令；final 阶段才渲染 search/vision 辅助块。
- `VideoFrameCollector.collect(..., allow_vision=False)` 通过显式 `include_grid_images=False` 抽帧契约直接逐帧走现有 OCR provider，不调用视觉 analyzer，也不分组、拼图或编码 grid/base64 payload；不支持该显式契约的旧 extractor 不会被隐式调用。空 OCR 文本不生成占位行或 vision context。
- 非视觉直达 OCR 使用稳定 `_frames_ocr` cache；视觉 analyzer 临时失败后的 OCR fallback 不写入视觉稳定 cache，下次视觉收集仍会重试 analyzer。
- Provider 若仍返回上下文超限，`UniversalGPT` 统一识别结构化 context code、`request (... tokens) exceeds ...`、成对且 `n_prompt_tokens > n_ctx` 的数值、`available/maximum context length|size|window` 等明确形态，以原输入预算 70% 重新分块一次。上下文错误优先于 500/timeout 通用重试分类；重试使用独立 checkpoint key，不删除第一次 checkpoint。第二次同类失败转为 `ContextLimitExceededError(code="context_limit_exceeded")`，日志和用户错误均不记录 Provider 原始 payload。
- 模型配置 schema 升级和删除模型只处理模型配置；历史 `note_documents`、conversation 和 `note_results` 不依赖模型外键。新 NoteResult 仍由统一 result writer 同步写入任务 JSON、conversation message 和 `note_documents`。

## 本地运行方式

### Agent Host（增量迁移）

`backend/app/agent_host/` 是独立 `notemeld-agent-sdk` Python package 的 NoteMeld Host 适配层。它负责加载版本化 binding、把现有 `app.ai` 模型流和 L0-L3 capability registry 转成 SDK driver 边界，并从现有 `conversations`/`conversation_messages` 读取历史；源码和桌面启动都只允许加载已安装的 standalone wheel/native artifact，禁止从 SDK 源码目录回退。N01 另外固定 S08 source commit、desktop artifact manifest/wheel/native SHA-256、SDK/schema/ABI 和 binding/native contract；缺失或不一致时 loader fail-closed。当前真实发布契约是 `SDK 0.1.0 / Agent Event schema 1 / ABI 1`。`abi-v2.json` 仍是未来契约，不能用包级临时常量绕过 artifact 校验。`python/python-oracle/legacy` runtime mode 已 fail-closed，不再存在静默回退。统一 Agent API 位于 `/api/agent/v1`，源码/安装 CLI 通过 `notemeld agent` 访问同一 Host。旧 `/api/chat/ask`、`/api/chat/free`、`/api/chat/free/stream` 已从生产 Router 移除。

N02 在 `agent_host/note_store_adapter.py` 提供 SDK NoteStore、
NoteOperationStore 和 NoteAuthority 的产品薄适配。`note_documents.task_id` 直接作为
opaque NoteId；正文仍只存在 `note_documents`。来源、关系、operation 和 provenance
写入 `note_agent_*` 元数据表，版本由每次权威提交的 provenance 单调派生。写入使用
短 `BEGIN IMMEDIATE`：正文、版本、必要 operation/provenance 在同一事务提交；事务
完成后才运行 Wiki/index/message/UI 投影，投影异常只形成诊断。operation reopen 会把
未完成的 `begun/checkpointed` 标为 `needs_attention`，不会自动重放可能已发生的副作用。
该表域由 `note_agent_app_migrations` 独立管理，不读取或写入 `PRAGMA user_version`。

每个 native Turn 只在开始时从 canonical Conversation store 读取一次完整历史；Rust SDK loop 在模型→工具→模型的每一轮维护 canonical messages。ABI v1 的 `model.stream` callback 以该轮 messages 为权威，NoteMeld Host 为每轮补齐同一份安全模型配置、当前 input/context refs 和 bounded 工具描述，再由 `NoteMeldModelDriver` 转成 notemeld-ai `LLMContext`。system、当前 user、assistant tool calls 和 tool result call id 均保留；Provider 前的实际窗口裁剪仍只由 `Models.stream()` 对副本执行，Host 不再固定截成 40 条或伪造空历史。

旧 NoteMeld Python Agent package（`backend/app/agent/`）、Python loop 测试和 `agent_host/compat.py` 已删除；Agent 行为只由独立 `notemeld-agent-sdk` 提供。

桌面后端打包时通过 `NOTEMELD_AGENT_SDK_WHEEL` 安装带 native library 的 wheel；PyInstaller 只从已安装的 `notemeld_agent_sdk` package 收集 Python 和 `native/` 资源。SDK 的 Rust workspace、binding、CLI、构建脚本和发布 workflow 全部维护在 `/Users/hehejie/ai/notemeld-agent-sdk`，NoteMeld 不再跟踪源码副本。

源码启动和已安装 CLI 启动都会调用同一个 `AgentSdkRuntime.load()` 校验 SDK/schema/ABI metadata 和 native artifact；未安装时必须通过 `NOTEMELD_AGENT_SDK_WHEEL` 提供带 native library 的 wheel，安装后再次校验，不兼容则阻止 Agent Host 启动。缺包、缺 native、架构不可加载和版本漂移均使用固定分类错误，不回显 wheel 路径、Provider payload 或凭证。`scripts/notemeld-agent.py` 是 `/api/agent/v1` 的薄客户端，不包含 Agent loop，支持一次性和交互式会话、会话恢复、模型切换与 JSON/JSONL 输出。

当前 Host 已提供基础只读知识能力适配：`wiki:search`、`note:search`、`note:read`。`NoteMeldToolDriver` 只通过请求级 `NoteMeldCapabilityRegistry` 调用现有 Wiki/Note 产品服务，不维护 Agent 状态机，也不直接调度下一轮模型。工具描述由 Host 在 Turn 开始时有界解析，并附着到每轮模型请求；模型返回 tool call 后，Rust SDK 的 `execute_tool_round` 是唯一调度者。产品成功或可恢复失败统一转换为 `{call_id, output}` ToolResult；`output` 使用 `{ok:true,result}` 或 `{ok:false,error}`，SDK 把它写入带同一 call id 的 canonical tool message 后继续下一轮模型。未知工具、非法参数、权限、业务失败和未预期执行异常分别使用 `unknown_tool`、`invalid_arguments`、`permission_denied`、`business_error`、`tool_execution_error`，公开结果和日志不包含参数、Provider payload 或异常原文。共享进程级 SDK Host 仍按 native turn token 路由 callback，不新增 Session 状态缓存。approval resolve 只透传独立 SDK 的 native control ABI，并把 unknown、duplicate、terminal 与 invalid decision 映射为稳定 HTTP 错误；只有 native manager 接受决策后才返回成功。

Agent v1 事件可通过 SSE 以 `sequence` 游标重放，前端 reducer 和兼容调用层都基于同一事件信封工作。Host descriptor 以原子方式写入数据根目录的 `run/agent-runtime.json`，供 Host 生命周期诊断复用。

ChatComposer 的 `chat` 模式已改为只提交一次 Agent v1 Turn 并消费 SSE；`note`、`learn` 等非聊天分支继续使用原有链路。聊天用户/助手消息由 Host executor 投影到 canonical conversation，前端不直接持久化 Agent 消息。`AgentHostEntry` 不维护活动 Turn map；SQLite `BEGIN IMMEDIATE` 事务在创建时保证同一 Session 只有一个非终态 Turn，不同 Session 的 Turn 创建后可并行执行。

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

## K0-K3 Knowledge Services

- 新增 `knowledge_articles`、`knowledge_chunks`、`knowledge_profiles`、`knowledge_terms`、`knowledge_term_occurrences` 和 `knowledge_relations` SQLite 表；K0-K3 统一使用 `article_id`，其值直接复用 `note_documents.task_id`。
- SQLite FTS5 共享表 `knowledge_chunk_fts`、`knowledge_profile_fts`、`knowledge_term_fts` 负责词法索引；共享向量 collection 使用固定版本名 `knowledge_k1_v1`、`knowledge_k2_v1`、`knowledge_k3_v1`，不再按文章创建 collection。
- `KnowledgeArticleService` 从现有 Note JSON、Wiki contribution 或 ingestion chunk 增量写入 K0-K3。旧 per-task Chroma collection、Wiki contribution 和 materialized pages 继续保留；共享索引失败只记录可重试 warning，不回滚已保存 Note。
- `KnowledgeQueryService` 提供 K0 article lookup、K1 evidence、K2 profile、K3 semantic 四类独立查询。`article_ids` 缺省为全库，显式空数组是参数错误；结果统一携带 `article_id` 和来源 provenance。
- `NoteMeldKnowledgeProvider` 通过现有 `NoteMeldToolDriver` 向 SDK 提供四个同级 capability。Host 不维护 K3→K2→K1 顺序，也不把 K0-K3 数据模型写入 SDK。

## Content Conversion Plugin Boundary

内容转换工具以独立插件目录和 `conversion-artifact.v1` envelope 接入
Agent Host。`official.document-to-markdown` 是 Rust process/JSONL 插件，内嵌
MIT `anydoc`，只读取宿主授权的输入文档并返回 Markdown；它不访问 NoteMeld
SQLite，也不负责总结或创建 Note。`official.image-ocr`、`official.video-fetch`、
`official.audio-extract`、`official.audio-transcribe` 和 `official.video-frames`
当前复用宿主已有的 OCR、下载器、ffmpeg、转写和视频帧
服务，通过相同的 capability/Artifact contract 暴露。

首批原子能力为 `document:to_markdown`、`image:ocr`、`video:fetch`、
`audio:extract`、`audio:transcribe` 和 `video:frames`。文档转换和 OCR 的产物
包含工具/插件版本、输入 hash、来源和 Turn；OCR 行包含 `bbox`、顺序和置信度。
Agent 负责读取这些产物、总结、决定关系，再调用 Note authority 写入 Note。
桌面 Host 已接入；服务端是 contract-ready 但需自行提供 ffmpeg、下载器和
转写/OCR 运行时；移动 native 和 WASM 在一期明确未打包/未接入。图片 ASCII
能力不在 capability registry 中。
