# Data Model

更新时间：2026-08-19

本文记录当前数据模型和字段语义。修改数据结构、状态、缓存、统计或文件布局前必须先阅读本文，并搜索相关代码和测试。

## 数据库位置或存储方式

数据根目录由 `backend/app/utils/storage_paths.py` 统一决定：

- `NOTEMELD_DATA_DIR` 已配置：使用该运行模式的数据根；其所有子目录仍由系统固定派生。
- 未配置：默认使用项目根目录下的 `vector_db`。
- 桌面模式：Tauri sidecar 注入 App Data、SQLite、uploads、static、models、screenshots 等路径。

主要存储：

- SQLite：`<data_dir>/notemeld.db`。
- 任务结果：`<data_dir>/note_results/`。
- 上传文件：`<data_dir>/uploads/`。
- 静态资源：`<data_dir>/static/`。
- 后端临时文件：`<data_dir>/tmp/`。
- 日志：项目/安装应用下的 `logs/`，不属于数据根。
- 截图：`<data_dir>/static/screenshots/`。
- 向量库：`<data_dir>/chroma/`。
- Wiki：`<data_dir>/note_results/wiki/`。
- 研究搜索配置：`<data_dir>/config/research_search.json`。
- 第三方 MCP 配置：`<note_output_dir>/settings/mcp_servers.json`。
- 会话学习空间：`<note_output_dir>/workspaces/{conversation_id}/canvases/{canvas_id}.json`。

## 核心表/集合/文件结构

### SQLite 表

- `providers`：LLM Provider 配置。字段：`id`、`name`、`logo`、`api_key`、`base_url`、`enabled`、`created_at`。
- `provider_templates`：Provider 模板。字段：`id`、`name`、`logo`、`base_url`、`created_at`；`name` 唯一。
- `models`：Provider 下的模型运行配置。字段：`id`、`provider_id`、`model_name`、`context_window_tokens`、`supports_vision`、`supports_stream`、`created_at`。用户保存的后三项运行字段是运行时权威值。
- `model_capabilities`：模型能力探测缓存。字段：`provider_id`、`model_name`、`supports_json_mode`、`supports_vision`、探测时间和错误；`provider_id + model_name` 唯一。它保持探测缓存语义，不替代 `models` 中用户保存的运行配置。
- `model_usage_records`：LLM 调用用量记录。字段：`task_id`、`provider_id`、`provider_name`、`model_name`、`phase`、`platform`、`video_id`、token、状态、错误和耗时。
- `video_tasks`：视频任务索引。字段：`video_id`、`platform`、`task_id`；`task_id` 唯一。
- `conversations`：会话。字段：`id`、`mode`、`title`、`status`、`message`、`platform`、`linked_note_task_id`、`note_state`、表单/转写/音频/Markdown JSON、`research_space_id`（P3 阶段二新增，nullable，cid→rs_id 映射，由 `ensure_conversation_columns` 幂等迁移）、时间戳、`deleted_at`。
- `conversation_messages`：会话消息。字段：`id`、`conversation_id`、`role`、`message_type`、`content`、`status`、`meta_json`、`sources_json`、`context_refs_authority_version`、`error`、时间戳。authority version 是客户端不可写的服务端 provenance：当前 resolver 成功处理引用后写 1；历史 schema、legacy merge 和未认证内部写入默认 0。
- `note_documents`：笔记文档索引。字段：`task_id`、`conversation_id`、`title`、`content`、`source_url`、`platform`、`model_name`、`style`、`status`、`wiki_status`、时间戳、`deleted_at`。

N01 冻结 `note_documents.task_id` 为一期 SDK `NoteId` 的 opaque 映射；历史
task id 不改写，`note_documents` 的标题、Markdown 正文、来源和产品状态是
Note authority。`note_results/`、conversation message、Wiki/FTS/Chroma 和
UI 只属于投影或兼容输出，不能因投影失败回滚已成功提交的 Note。产品侧
DTO/adapter seam 见 `docs/system/n01-note-authority-and-sdk-seam.md`。

N02 新增独立 registry `note_agent_app_migrations`，并新增以下只保存 SDK
operation 元数据的表；该 registry 不使用共享 `PRAGMA user_version`：

| 表 | 关键字段 | 语义 |
| --- | --- | --- |
| `note_agent_sources` | `source_id`, `note_id`, `authority`, `locator`, `digest`, `operation_id` | 每次 SDK 写操作验证后的来源引用；不复制正文，主来源仍同步到 `note_documents.source_url`。 |
| `note_agent_relations` | `relation_id`, `from_note_id`, `to_note_id`, `kind`, `operation_id` | Note 间的 typed relation；两端都复用 `note_documents.task_id`。 |
| `note_agent_operations` | `operation_id`, `request_id`, `payload_hash`, `status`, `outcome_json` | request 幂等和恢复 ledger；`request_id` 唯一。 |
| `note_agent_provenance` | `note_id`, `note_version`, `operation_id`, actor/plugin/turn/source ids | Note 版本及提交 provenance；`(note_id, note_version)` 唯一，历史无行 Note 懒映射为 version 1。 |

operation 状态为 `begun → checkpointed → committed|failed`，进程重开把未终结
的 `begun/checkpointed` 转为 `needs_attention`。权威写事务原子包含
`note_documents` 正文、对应版本 provenance、来源/关系和 committed outcome；
Wiki、FTS/Chroma、Conversation message 与 UI projection 不在该事务内。
- `note_styles`：笔记样式。字段：`id`、`name`、`description`、`skeleton_html`、`style_constraints`、`rule_config`、`example_content`、`output_formats`、`builtin`、时间戳。
- `template_extraction_tasks`：样式模板提取任务。字段：`task_id`、`status`、`stage`、`messages_json`、`chunks_json`、`provider_id`、`model_name`、`file_name`、`progress`、请求 payload、结果和错误。

`models` 运行字段的旧 schema 升级是受控的一次性边界：仅在缺少 `context_window_tokens` / `supports_vision` / `supports_stream` 任一字段时，在同一事务补列并清空 `models` 与 `model_capabilities`。完整 schema 重复启动或只补建唯一索引时不清空模型行；`providers`、`note_documents`、conversation、usage、任务状态和 `note_results/` 始终不在该迁移的删除范围。

legacy SQLite 合并不导入 `models` 表，返回摘要中 `models` 始终为 `0`。这一规则与 legacy 表是否已包含完整运行字段无关，用于避免绕过用户对端点实际上下文、图像和流式能力的重新确认。Provider、Note、Conversation、Usage 和任务等其他 legacy 数据仍按原有去重规则合并。

### 文件结构

- `config/research_search.json`：Web provider、SearXNG endpoint、请求超时及本地 Tavily/GitHub 凭证。`academic/github` 是代码层基线，不依赖该文件；旧文件中的 `enabled_scopes` 继续容忍读取但不能关闭基线。公开读取时删除密钥和旧 scopes，并派生 `tavily_api_key_set/github_token_set`。
- `settings/mcp_servers.json`：第三方 MCP server 的 transport、endpoint、command、headers/env/auth 和 enabled 状态。文件使用进程内写锁、唯一临时文件和原子替换；API 读取不返回 auth，headers/env 值只返回 `***`，编辑回传占位符时保留已有值。
- `workspaces/{conversation_id}/canvases/{canvas_id}.json`：版本化 `LearningCanvas`。version 2 在原字段上追加 `document_task_id/overview/clarification/suggested_actions`，作为研究 Note 的白板投影；显式 version 1 历史文件继续读取。原始学习证据仍只保存在对应 canvas session attempt 中。
- `whiteboards`：会话内语义白板主体（标题、`revision`、`viewport`、`legacy_canvas_id`、状态）与四类关系表 `whiteboard_cards/whiteboard_relations/whiteboard_note_links`。白板是未发布草稿/关系结构的权威，`note_documents` 才是已发布文本权威。
- `whiteboard_note_links`：持久化白板与 Note 的绑定关系（`note_task_id` + `published_revision`）
- `document_task_id`：来自 `whiteboard_note_links.note_task_id` 的已发布 Note 绑定字段。白板内 `card/relation` 可更新并保留草稿状态，未发布内容不自动改变 `note_documents`。
- `conversation_messages.message_type=learning_canvas`：只持久化轻量消息索引；`meta_json` 可含 `canvas_id/goal/status/node_count/document_task_id/overview/clarification/suggested_actions`，完整 nodes、正文和作答不得复制进消息表。
- `conversation_messages.meta_json.context_refs`：用户消息可保存最多 8 条 `note_selection|whiteboard_node|whiteboard_selection` 引用。每条含有界 snapshot、document/canvas/node 或 whiteboard/card/relation 定位和 source_ids；legacy 单条 snapshot 最多 2000 字符，服务端生成的 `whiteboard_selection` canonical snapshot 最多 12000 字符。
- `conversation_messages.context_refs_authority_version`：是否允许按相同 locator/revision 复用发送时快照的内部版本。只有 row 的版本等于当前服务端版本且 stored/resulting role 均为 user 才可复用；字段不进入普通会话 API 响应或请求模型。幂等补列和 legacy merge 均将历史行置 0，首次安全 PATCH 后才能升级。

- `note_results/{task_id}.status.json`：任务状态事实来源。
- `note_results/{task_id}.json`：结构化任务结果。
- `note_results/{task_id}_markdown.md`：Markdown 笔记。
- `note_results/{task_id}_summary_input.json`、`*_plan.json`、`*_context_pack.json` 等：sidecar 调试文件。
- `note_results/task_conversations/{task_id}.json`：任务到 conversation 的映射。
- `note_results/wiki/contributions/{source_id}.json`：单篇知识贡献。
- `note_results/wiki/sources/{source_id}.md`：来源页。
- `note_results/wiki/entities/{safe_name}.md`：实体页。
- `note_results/wiki/concepts/{safe_name}.md`：概念页。
- `note_results/wiki/graph.json`：Wiki 图谱。
- `note_results/wiki_rebuild_job.json`：完整 Wiki rebuild 状态。
- `uploads/`：上传原始文件。
- `chroma/`：Chroma collection 持久化目录。

## 字段语义

- `task_id`：任务唯一标识，是状态文件、结果文件、note document、conversation 关联、Wiki source 的核心关联键。
- `conversation_id`：会话唯一标识，`note_documents` 和 `conversation_messages` 通过它归属会话。
- `status`：不同表含义不同，不能混用。任务状态使用 `TaskStatus`；会话状态表示会话整体；Wiki job 状态表示单篇或全局 Wiki 状态。
- `wiki_status`：`note_documents` 中的 Wiki 状态。前端会读取它决定 WikiViewer 展示。
- `phase`：usage 记录中的 LLM 调用阶段，例如 analysis、summary 等。
- `platform`：来源平台或输入类型，可能是视频平台、web、upload 等。
- `content`：`note_documents.content` 存 Markdown 正文；`conversation_messages.content` 存消息内容。
- `meta_json` / `sources_json`：字符串形式 JSON，写入前必须序列化，读取后必须容错解析。
- `api_key`：敏感字段，只允许本地持久化和后端使用，不允许返回给前端或 MCP。
- `supports_json_mode` / `supports_vision`：模型能力缓存，可为 `null` 表示未探测。

## 唯一性规则

- `providers.id` 是 Provider 主键。
- `provider_templates.name` 唯一。
- `models.id` 自增主键；`(provider_id, model_name)` 有数据库级唯一约束，同一 Provider 下模型名不得重复。运行时字段旧 schema 升级会清空旧模型配置和能力缓存后再建立该约束；已经具备运行时字段的现有模型行不会因补建唯一索引而清空。
- `model_capabilities(provider_id, model_name)` 唯一。
- `video_tasks.task_id` 唯一。
- `conversations.id` 唯一。
- `conversation_messages.id` 唯一。
- `note_documents.task_id` 唯一。
- `template_extraction_tasks.task_id` 唯一。
- Wiki contribution 文件名由 `_safe_id(source_id)` 决定，同一 source_id 覆盖同一 contribution。

## 状态流转

### 学习掌握状态

- `unknown`：没有学习证据。
- `exposed`：学习单元已展示；不得据此推断理解或应用能力。
- `learning`：已有有效作答，但 recall/explain 与 apply/transfer 证据尚未同时通过，或到期复测失败。
- `provisional`：即时 recall/explain 与 apply/transfer 均通过；写入 `next_review_at = now + 48h` 和 `review_queue`。
- `mastered`：仅允许在 `next_review_at` 到期后，`review` 再次通过时进入；成功后清除该节点复习项。

评测输入必须含非空学习者答案，以及 `rubric_version/score/passed/feedback/answer_summary`。`score` 必须在 0–1，V1 中 `passed=true` 要求分数不低于 0.7。

Canvas 变更对同一路径使用进程内锁覆盖完整 load→mutate→save，并通过目标目录内唯一 `NamedTemporaryFile` 后 `replace()`；不得只锁最终写入，也不得使用固定 `.tmp` 文件名。`conversation_id/canvas_id` 只允许安全字符，禁止路径穿越。

### 笔记任务状态

`TaskStatus` 位于 `backend/app/enmus/task_status_enums.py`：

```text
PENDING -> PARSING -> DOWNLOADING -> TRANSCRIBING -> SUMMARIZING -> FORMATTING -> SAVING -> SUCCESS
```

终态还包括：

- `FAILED`
- `CANCELED`

状态写入 `note_results/{task_id}.status.json`，并同步 upsert 会话进度消息。

### Wiki 单篇状态

Wiki job store 以 `task_id` 记录单篇 Wiki 抽取状态，常见值：

- `pending`
- `running`
- `success`
- `partial`
- `failed`
- `canceled`

前端会将非 success/failed/canceled/partial 的状态视为 pending 类状态。修改文案或状态映射前必须确认历史残留状态兼容性。

### Wiki 全局重建状态

`WikiRebuildService` 写 `wiki_rebuild_job.json`：

- `pending`
- `running`
- `success`
- `failed`
- `canceled`

rebuild 使用 generation 号实现 latest-wins。新请求会取消正在运行的 generation。

### 样式提取任务状态

`template_extraction_tasks.status` 默认 `pending`，配合 `stage`、`progress`、`result_json`、`error` 展示任务进度。

## 缓存判断口径

- 任务是否完成不能只看 Markdown 文件存在；必须结合 status 文件和 `{task_id}.json`。
- `/api/task_status/{task_id}` 当前优先读 status 文件；若无状态但有结果文件，也可返回 SUCCESS。
- 向量库缓存不能只看 `chroma/` 存在，应检查 collection 是否包含该 task 的 chunks。
- 用户保存的 `models.context_window_tokens`、`models.supports_vision`、`models.supports_stream` 是运行时权威值；`model_capabilities` 仅保存自动探测缓存，不覆盖这些用户保存值，其中 `null` 表示未知，不等于不支持。删除模型与其匹配能力缓存必须在同一 SQLite 事务完成；不删除 Provider、笔记或 usage 行。
- Wiki 文章视图以 contribution 是否存在为准；完整 Wiki 图谱以 `graph.json` 和 materialized pages 为准。
- 上传文件缓存必须保留原文件安全边界，不允许用用户传入路径直接读取。

## 统计口径

- LLM 使用量统计来自 `model_usage_records`。
- 统计维度包括 provider、model、phase、platform、task_id、video_id、状态、token 和耗时。
- 错误调用也应记录 `status` 和 `error_message`，不能只统计成功调用。
- 任务级成本或调用摘要应以 `task_id` 聚合。

## 本地数据和远端数据边界

- NoteMeld 的主要业务数据本地持久化在 SQLite 和文件系统。
- 远端 Provider 只负责 LLM 推理；不应假设远端保存 NoteMeld 数据。
- 视频平台、网页和外部下载器是内容来源，不是 NoteMeld 的持久化事实源。
- MCP 远程访问只暴露经过授权的本地能力，不能绕过本地安全边界。
- 桌面自动更新元数据来自远端 endpoint，但用户数据仍在本地 App Data。
## Agent Host 数据边界

Agent Host 使用 `agent_turns`, `agent_events`, `agent_preferences` 三张附加表。`agent_turns.session_id` 外键指向 `conversations.id`；不存在 `agent_sessions`、`agent_messages` 或独立 approval 表，消息历史仍来自 `conversation_messages`。UI-only 的 `note_progress`、`task_card`、`parameter_request` 等消息不会进入 SDK model history。模型选择顺序为显式 Turn 模型、会话偏好默认模型、偏好 fallback 第一项、用户可用模型第一项。同一 Session 只允许一个非终态 Turn；SQLite 创建 Turn 时使用短 `BEGIN IMMEDIATE` 事务原子完成 Conversation 存在性、幂等键和活动 Turn 检查及插入，不维护进程内第二状态。审批暂停时，同一事务写入 `approval.required` 并把 Turn 置为非终态 `waiting_approval`；SDK 收到决定后写入 `approval.resolved` 并回到 `running`。客户端断线或 UI/CLI 切换通过 `agent_events.sequence` 重放同一 Turn；进程重启仍按既有恢复规则把无法恢复 native 栈帧的非终态 Turn 标为 `interrupted`。

## K0-K3 Article Knowledge Index

更新时间：2026-08-18

K0-K3 是建立在既有 `note_documents.task_id` 之上的增量索引模型，不替换 Note、Wiki contribution、materialized page 或历史 Chroma 数据。

| 表 | 关键字段 | 语义 |
| --- | --- | --- |
| `knowledge_articles` | `article_id`, `content`, `status` | K0 文章索引镜像；`article_id == note_documents.task_id`。 |
| `knowledge_chunks` | `chunk_id`, `article_id`, `page_number`, `section_path`, `start_time`, `end_time` | K1 原文证据块和位置 provenance。 |
| `knowledge_profiles` | `profile_id`, `article_id`, `summary`, `topics_json`, `status` | K2 每篇文章一个高密画像，优先复用 Wiki summary。 |
| `knowledge_terms` | `term_id`, `term_type`, `normalized_name` | K3 canonical 实体/概念节点。 |
| `knowledge_term_occurrences` | `term_id`, `article_id`, `evidence_id` | 节点到文章和证据的 occurrence provenance。 |
| `knowledge_relations` | `source_term_id`, `target_term_id`, `article_id`, `evidence_id` | K3 关系边及其文章来源，不按文章复制 canonical 节点。 |
| `knowledge_index_states` | `layer`, `generation`, `status` | 索引 generation 和可重建状态预留。 |

SQLite FTS5 表 `knowledge_chunk_fts`、`knowledge_profile_fts`、`knowledge_term_fts` 为共享在线词法索引；向量 collection 使用版本化固定名称，禁止为每篇文章创建 collection。删除文章时移除 occurrence、chunk/profile 和 FTS 行，再把文章置为 `deleted`；共享 term 只有不再被任何文章引用时才允许后续清理。
