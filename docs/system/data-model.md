# Data Model

更新时间：2026-06-19

本文记录当前数据模型和字段语义。修改数据结构、状态、缓存、统计或文件布局前必须先阅读本文，并搜索相关代码和测试。

## 数据库位置或存储方式

数据根目录由 `backend/app/utils/storage_paths.py` 统一决定：

- `NOTEMELD_DATA_DIR` 已配置：使用该目录。
- 未配置：源码模式默认使用仓库下 `vector_db`。
- 桌面模式：Tauri sidecar 注入 App Data、SQLite、uploads、static、models、screenshots 等路径。

主要存储：

- SQLite：`<data_dir>/notemeld.db`。
- 任务结果：`<data_dir>/note_results/`。
- 上传文件：`<data_dir>/uploads/`。
- 静态资源：`<data_dir>/static/`。
- 截图：`<data_dir>/static/screenshots/`。
- 向量库：`<data_dir>/chroma/`。
- Wiki：`<data_dir>/note_results/wiki/`。

## 核心表/集合/文件结构

### SQLite 表

- `providers`：LLM Provider 配置。字段：`id`、`name`、`logo`、`api_key`、`base_url`、`enabled`、`created_at`。
- `provider_templates`：Provider 模板。字段：`id`、`name`、`logo`、`base_url`、`created_at`；`name` 唯一。
- `models`：Provider 下的模型列表。字段：`id`、`provider_id`、`model_name`、`created_at`。
- `model_capabilities`：模型能力探测缓存。字段：`provider_id`、`model_name`、`supports_json_mode`、`supports_vision`、探测时间和错误；`provider_id + model_name` 唯一。
- `model_usage_records`：LLM 调用用量记录。字段：`task_id`、`provider_id`、`provider_name`、`model_name`、`phase`、`platform`、`video_id`、token、状态、错误和耗时。
- `video_tasks`：视频任务索引。字段：`video_id`、`platform`、`task_id`；`task_id` 唯一。
- `conversations`：会话。字段：`id`、`mode`、`title`、`status`、`message`、`platform`、`linked_note_task_id`、`note_state`、表单/转写/音频/Markdown JSON、时间戳、`deleted_at`。
- `conversation_messages`：会话消息。字段：`id`、`conversation_id`、`role`、`message_type`、`content`、`status`、`meta_json`、`sources_json`、`error`、时间戳。
- `note_documents`：笔记文档索引。字段：`task_id`、`conversation_id`、`title`、`content`、`source_url`、`platform`、`model_name`、`style`、`status`、`wiki_status`、时间戳、`deleted_at`。
- `note_styles`：笔记样式。字段：`id`、`name`、`description`、`skeleton_html`、`style_constraints`、`rule_config`、`example_content`、`output_formats`、`builtin`、时间戳。
- `template_extraction_tasks`：样式模板提取任务。字段：`task_id`、`status`、`stage`、`messages_json`、`chunks_json`、`provider_id`、`model_name`、`file_name`、`progress`、请求 payload、结果和错误。

### 文件结构

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
- `models.id` 自增主键；同一 Provider 下模型名语义上不应重复。
- `model_capabilities(provider_id, model_name)` 唯一。
- `video_tasks.task_id` 唯一。
- `conversations.id` 唯一。
- `conversation_messages.id` 唯一。
- `note_documents.task_id` 唯一。
- `template_extraction_tasks.task_id` 唯一。
- Wiki contribution 文件名由 `_safe_id(source_id)` 决定，同一 source_id 覆盖同一 contribution。

## 状态流转

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
- 模型能力缓存以 `model_capabilities` 为准；`null` 表示未知，不等于不支持。
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
