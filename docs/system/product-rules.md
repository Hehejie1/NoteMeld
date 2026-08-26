# Product Rules

更新时间：2026-08-19

本文记录已经确认的产品硬规则。任何开发者或 Agent 修改需求、方案、代码、接口、数据结构前，都必须确认不会破坏这些规则。

## 用户明确要求过的业务规则

- NoteMeld 是自托管、本地优先的个人知识编译器，不是云端多租户产品，不是传统笔记存储工具。对外定位是"你的 AI 研究助手"，对内架构隐喻是"知识编译器"。
- 核心范式是：AI 编译知识，人验证和消费。AI 负责下载、转写、理解、抽取、构建图谱；人负责标记来源、验证结果、消费知识。
- 核心价值是把零散输入编译为可追溯、可复用、自动生长的个人知识图谱。
- NoteMeld 采用 Wiki-First Retrieval：先编译结构化知识层，再检索、引用和问答。
- 每篇笔记都应产出结构化 Markdown，并尽量产出 Wiki 知识包。
- Wiki 知识包语义包括 `entity`、`concept`、`evidence`、`claim`、`relation`。
- 内容来源必须支持网页、本地文件、多平台视频和 AI 对话沉淀。
- B 站 / YouTube 有官方字幕时应优先使用字幕，避免不必要转写成本。
- 视频下载、音频下载或转写失败时，允许降级为网页抓取继续生成笔记。
- 上传 Markdown 必须兼容浏览器把 `.md` 识别为 `application/octet-stream` 或 `binary/octet-stream` 的情况。
- MCP 必须作为本地知识工具接入 AI IDE，endpoint 保持 `http://127.0.0.1:8483/mcp`。
- 桌面端不能替代源码启动入口，`run_notemeld.sh` 和 `notemeld` CLI 必须继续可用。
- Web、Tauri 和 `notemeld agent` 只能通过 `/api/agent/v1` 使用同一个 Agent Host；Session 复用 Conversation，同一 Session 同时只能有一个活动 Turn，不得由入口维护第二套 Agent 状态或直接写 Agent 数据库。
- N05 的 MCP Note create/link/read/search 与 CLI 关联 Note 必须复用 Agent Host capability registry 和 N02 Note authority；外部入口不得直接写 SQLite 或 Agent Event。桌面插件/任务诊断请求服从 Backend ready gate。
- 外部链接转 Note 只能通过已安装并校验的 `official.link-note` capability；插件通过 host port 使用现有字幕优先、下载、转写、截图、多源总结、网页抓取、任务状态和降级能力，不直接写 Conversation、Agent Event 或内部 SQLite。
- 危险或未知 Agent 工具必须由 SDK 在原 Turn 内发起 approval 并暂停；UI/CLI 只能通过 Agent v1 resolve 同一个 native 暂停点。HTTP 成功不得伪装 runtime 已恢复，拒绝不得执行受保护工具，approval 事件与 `waiting_approval/running` 必须进入既有 Conversation/Turn/Event 链。

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
- 一期 SDK NoteId 必须 opaque 映射 `note_documents.task_id`；`note_documents` 是 Note 正文/来源/产品状态 authority，note_results、Conversation、Wiki、向量索引和 UI 只能是可重建投影。
- SDK Note 写操作必须以 request id 和 canonical payload hash 持久幂等：same request/same payload 返回原 outcome，different payload 稳定冲突；未完成 operation 重开后进入 `needs_attention`，禁止自动重放。Note 正文、版本和必要 operation/provenance 原子提交后即成功，后续投影失败不得回滚或重复创建 Note。
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
- LLM 实际运行只能选择用户已添加的模型；`models` 表中的上下文长度、图像支持和流式支持是权威配置，能力探测缓存不得覆盖用户保存值。
- 本地模型目录只用于添加时给出可修改建议；未命中、缺失或损坏必须安全回退 `4096 / false / true`。用户保存的端点实际值始终优先，不得用官网或模型文件的理论窗口自动覆盖。
- 不支持流式的模型仍须对现有流式调用方可用；后端将非流式结果转换为兼容事件，并保证单次 Provider 请求只记录一条 usage。
- 任何含图片内容的 LLM 请求必须在 Provider 请求前以用户保存的 `supports_vision` 做最终闸门；探测缓存的 `true` 不能绕过保存的 `false`，探测的 `false` 也不能覆盖保存的 `true`。不支持时返回可分类的 vision capability 错误；OCR 降级不在当前运行时层实现。
- 所有聊天、Agent 和笔记 LLM 请求必须以用户保存的上下文窗口计算同一输入预算；聊天只裁剪发送给 Provider 的副本，保留 system、最新 user 及完整 tool call/result 关系，不得截断或改写持久会话原消息。笔记分块必须同时满足 token 与字节上限。
- 长笔记的 map 请求不得重复携带整份画面、OCR 或网页搜索上下文；这些辅助证据只在 final 阶段注入。Provider 实际窗口仍小于保存值时只允许按原输入预算 70% 重分块一次，上下文错误不得因同时含 500/timeout 而进入通用重试；失败必须返回不含 Provider payload 的中文提示，日志也不得记录原 payload，并保留采集缓存与 checkpoint。
- 开启截图但所选模型不支持视觉时必须直接复用本地 OCR 路径，抽帧器必须显式接受“不生成 grid”契约，不得先调用视觉模型或构造/编码 grid/image payload；OCR 空文本不得变成“未识别到文本”占位上下文。视觉 analyzer 临时失败的 OCR fallback 不得写入会抑制后续 analyzer 重试的稳定视觉 cache。
- 清空或删除模型配置不得删除历史笔记。重新添加模型后，新笔记仍必须同时保存 task result Markdown、conversation `note_result` message 和 `note_documents`。
- 缓存命中不能只看文件存在，还要结合任务状态、collection 内容或 checksum 语义。
- 桌面运行状态以注入 runtime、`/sys_health` 和 backend init context 共同判断。

## 用户体验偏好

- 沟通和产品文案默认中文，表达要直接、结果导向。
- 前端 UI 应保持高信息密度、克制、清晰，遵循现有 Structured Intelligence 风格。
- Provider 编辑区的已启用模型列表右侧使用“添加模型”入口；新增模型必须在居中弹窗中明确选择模型并确认上下文长度、图像与流式支持，保存失败时保留用户输入，删除已添加模型能力保持可用。
- 长任务必须有可理解的进度、阶段、错误信息和可恢复路径。
- 失败时应优先保留可读结果和排障信息，允许降级生成 partial 内容。
- Wiki、笔记、MCP 输出必须强调来源、证据、可追溯。
- Agent free-chat 对 Wiki、Skill 和第三方 MCP 采用 L0–L3 渐进披露：L0 只给有界元数据地图，L1 发现候选，L2 展开选中契约，L3 执行；不得把全部正文或全部工具 schema 平铺到首轮上下文。
- Wiki-First Retrieval 不等于每轮无条件扫描 Wiki。普通聊天可直接回答；涉及个人知识、来源、证据或 L0 命中候选时，应由模型按需进入 L1–L3，并把实际检索结果写入可验证来源。
- 主动学习空间必须先使用 NoteMeld 已编译的 Wiki/笔记；学术论文和 GitHub 是无需配置、不可关闭的默认补充来源，普通 Web 只在 Tavily/SearXNG 配置可用时加入；外部来源失败不能清空本地学习空间。
- “学习”是显式提交意图而不是新的持久会话类型。用户选择后，文字或链接识别不得擅自切回聊天/笔记；提交必须确定性创建学习空间，不依赖模型是否主动选择 Agent tool。
- 学习主体验是对话驱动的知识调研与冲突论证，不是老师式授课。只有会改变研究对象或搜索范围的重大歧义才逐个提问；不得机械询问用户水平、学习时长或制定课程。
- 白板是未发布研究草稿与关系结构的权威；用户显式发布后才将快照写入标准 Note（`note_documents`）。左侧为会话，中间为对话，右侧可在“白板 / 笔记”间切换；白板显示可操作关系图与当前焦点，笔记显示已发布线性文本。未发布白板不得代替正文参与最终事实判断。
- 白板是主要操作空间而不是详情列表：默认节点保持紧凑，最多展开一个画布内节点卡片；“添加到对话”属于该节点卡片/节点右键动作，不得用固定底部详情区持续挤压画布。
- 外部搜索结果只能作为候选证据；论文标题、GitHub 仓库名和网页标题未经相关性过滤、实体消歧、概念抽取和来源验证不得成为白板节点或推荐起点。
- 用户选中的笔记文本和白板节点可以作为有界、可追溯引用加入对话；引用不得自动发送，也不得被后端当作系统指令。导航建议只切白板焦点，研究建议必须由用户提交后才调用模型。
- 历史会话引用是否可复用必须由客户端不可写的服务端 provenance 判定；`role=user` 或 `meta_json` 内的 marker 都不能作为 authority。无 provenance 的历史/legacy 引用必须重新解析。
- 明确目标的研究内容进入标准 Note/Wiki 管线。Note 保存成功后，白板、消息或 Wiki 后处理失败不得回滚研究正文或提示用户重复生成。
- 搜索发现可以按本机配置自动执行；外部全文采集、编译和写入 Wiki 必须由用户确认，候选来源不得冒充已编译知识。
- “展示过/读过”不等于“掌握”。只有学习者作答形成的 recall/explain 与 apply/transfer 证据可进入 `provisional`；至少 48 小时后的到期复测通过才可进入 `mastered`。
- 掌握证据必须保存 rubric 版本、0–1 分数、通过与否、反馈、答案摘要、时间及来源节点；空答案、缺字段、越界分数或低于阈值却标记通过的评测必须拒绝。
- `use_wiki=false` 是注册与执行双重硬边界；第三方 MCP 只有 `enabled=true` 可发现，且未选中时不得建立连接，请求结束必须释放 adapter。
- 新能力应优先最小可行改动，避免无关重构导致用户已有流程失效。

## 安全/隐私边界

- Provider API Key 只应保存在本地数据库或本地配置中，不允许出现在响应、日志、MCP 输出、前端埋点或公开文档示例中。
- 研究搜索的 Tavily Key 和 GitHub Token 只保存在本机 `config/research_search.json`；读取接口仅允许返回是否已配置，空字符串默认保持原值，显式 clear 才能删除。
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
