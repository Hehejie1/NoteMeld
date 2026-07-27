# Product Rules

更新时间：2026-06-19

本文记录已经确认的产品硬规则。任何开发者或 Agent 修改需求、方案、代码、接口、数据结构前，都必须确认不会破坏这些规则。

## 用户明确要求过的业务规则

- NoteMeld 是自托管、本地优先的 AI 知识工作台，不是云端多租户产品。
- 核心价值是把零散输入沉淀为可追溯、可复用、可持续增长的个人知识库。
- NoteMeld 采用 Wiki-First Retrieval：先编译结构化知识层，再检索、引用和问答。
- 每篇笔记都应产出结构化 Markdown，并尽量产出 Wiki 知识包。
- Wiki 知识包语义包括 `entity`、`concept`、`evidence`、`claim`、`relation`。
- 内容来源必须支持网页、本地文件、多平台视频和 AI 对话沉淀。
- B 站 / YouTube 有官方字幕时应优先使用字幕，避免不必要转写成本。
- 视频下载、音频下载或转写失败时，允许降级为网页抓取继续生成笔记。
- 上传 Markdown 必须兼容浏览器把 `.md` 识别为 `application/octet-stream` 或 `binary/octet-stream` 的情况。
- MCP 必须作为本地知识工具接入 AI IDE，endpoint 保持 `http://127.0.0.1:8483/mcp`。
- 桌面端不能替代源码启动入口，`run_notemeld.sh` 和 `notemeld` CLI 必须继续可用。

## 不允许被改坏的行为

- 不能把本地优先数据写入应用包内部；桌面模式数据必须写入 Tauri 注入的 App Data 目录。
- 不能让前端在桌面 sidecar 未 ready 时发起业务请求。
- 不能删除或缩短桌面首次启动的静默等待机制到不覆盖 PyInstaller、模型、SQLite 初始化的耗时。
- 不能让 `list_models`、MCP、日志或前端响应暴露 Provider API Key。
- 不能让 `get_note`、Wiki 读取、文件读取接口接受路径穿越。
- 不能把完整 Wiki materialize 同步放回笔记保存路径。
- 不能让 Wiki rebuild 失去 latest-wins 取消语义。
- 不能删除任务 sidecar 文件，它们是复盘和排障依据。
- 不能破坏 `task_id` 作为任务、结果文件、状态文件、note document 和 Wiki source 的关联主键。
- 不能随意改变 `TaskStatus` 枚举语义，前端轮询和进度 UI 依赖这些状态。
- 不能把已有文件上传安全校验降级为只看扩展名。
- 不能在没有兼容层的情况下改变 API response wrapper：`{ code, msg, data }`。
- 不能删除用户未明确要求删除的能力，包括源码运行、CLI、桌面、MCP、迁移、Wiki、导出等。

## 数据展示口径

- 笔记列表和会话中的文档以 `note_documents` 和 conversation message 为核心展示来源。
- 任务进度以 `note_results/{task_id}.status.json` 为事实来源；成功时可回读 `note_results/{task_id}.json`。
- Wiki 文章视图读取单篇 contribution，不代表完整全局 Wiki rebuild 已完成。
- Wiki 图谱和实体/概念页读取 materialized Wiki 文件和 `graph.json`。
- usage 统计来自 `model_usage_records`，按 provider、model、phase、platform、task_id 等维度聚合。
- 缓存命中不能只看文件存在，还要结合任务状态、collection 内容或 checksum 语义。
- 桌面运行状态以注入 runtime、`/sys_health` 和 backend init context 共同判断。

## 用户体验偏好

- 沟通和产品文案默认中文，表达要直接、结果导向。
- 前端 UI 应保持高信息密度、克制、清晰，遵循现有 Structured Intelligence 风格。
- 长任务必须有可理解的进度、阶段、错误信息和可恢复路径。
- 失败时应优先保留可读结果和排障信息，允许降级生成 partial 内容。
- Wiki、笔记、MCP 输出必须强调来源、证据、可追溯。
- 新能力应优先最小可行改动，避免无关重构导致用户已有流程失效。

## 安全/隐私边界

- Provider API Key 只应保存在本地数据库或本地配置中，不允许出现在响应、日志、MCP 输出、前端埋点或公开文档示例中。
- MCP 本地请求默认可免 token；远程访问或强制配置时必须使用 Bearer Token。
- migration 接口在桌面 session token 存在时必须校验 `X-NoteMeld-Session`。
- 上传文件必须保留扩展名、MIME、大小、内容解析和路径安全校验。
- 静态资源、截图、上传文件、导出文件不能通过路径穿越访问数据目录之外的文件。
- 删除会话、删除任务、迁移导入等破坏性动作必须尊重现有软删除或 job 机制，不能静默删除不可恢复数据。
- 打包发布必须保留签名、公证、Gatekeeper、DMG 完整性和公网 SHA256 校验。

## 必须禁止的行为

- 禁止基于猜测修改数据库字段、接口语义、任务状态或 Wiki 数据结构。
- 禁止新需求直接写孤立 PRD，必须先写增量 Change Spec。
- 禁止只读 README 就改核心链路，必须同时查代码、测试和 `docs/system/`。
- 禁止为了让局部测试通过而删除契约测试覆盖的发布、安全、MCP、上传、桌面启动规则。
- 禁止把历史脏数据现象误判为实时任务状态，涉及状态展示时必须核对状态文件和前端映射。
- 禁止把慢 LLM 请求放进全局写锁。
- 禁止在 rebuild 取消语义不清楚时删除 live Wiki 数据。
- 禁止回滚用户或其他 Agent 的未提交改动，除非用户明确要求。
