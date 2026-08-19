# API Inventory

更新时间：2026-08-16

本文记录当前接口事实。新增、删除、重命名接口或修改返回结构前，必须更新本文和相关调用方/契约测试。

## 通用约定

- 大部分后端接口挂载在 `/api` 前缀下。
- MCP endpoint 不走 `/api`，固定为 `/mcp`。
- 普通成功响应使用 `ResponseWrapper.success()`：

```json
{ "code": 0, "msg": "success", "data": {} }
```

- 业务错误通常使用 `ResponseWrapper.error()` 或抛 `HTTPException`。
- 前端 Axios 封装会按项目约定解包响应，调用侧多数直接拿 `data`。
- 桌面模式 Axios 请求会带 `X-NoteMeld-Session`。
- migration 接口在 `NOTEMELD_DESKTOP_SESSION_TOKEN` 存在时校验 session token。
- MCP 本地请求默认免 token；远程或强制配置时校验 `Authorization: Bearer <NOTEMELD_MCP_TOKEN>`。

## Note / Task 接口

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/generate_note` | JSON，来源 URL/输入类型、provider/model、style、conversation/task 等 | `{task_id, conversation_id, ...}` 或任务状态 | HomePage、MCP generate_note | 本地 | Provider/输入/任务创建失败返回错误 | 不能破坏 task_id 和 conversation 绑定 |
| GET | `/api/task_status/{task_id}` | path: `task_id` | 任务状态、进度、message、结果摘要 | 前端轮询、MCP get_task | 本地 | 找不到时按状态文件/结果文件容错 | 状态枚举和 SUCCESS fallback 需兼容 |
| POST | `/api/delete_task` | JSON: `task_id` 等 | 删除结果 | 前端任务删除 | 本地 | 删除失败返回错误 | 不能误删其他任务或用户数据 |
| POST | `/api/upload` | multipart file | 上传文件元信息、upload_id | 上传入口 | 本地 | 扩展名/MIME/大小/解析失败 | Markdown octet-stream 兼容不能删 |
| GET | `/api/uploads/{upload_id}` | path: `upload_id` | 上传文件信息/内容 | 上传文档链路 | 本地 | 文件不存在 404 | 禁止路径穿越 |
| POST | `/api/uploaded_files/ingest` | JSON: upload_id、模型、样式等 | 文档摄入任务 | 上传文档入口 | 本地 | 解析/任务创建失败 | 必须复用任务状态体系 |
| POST | `/api/wiki/retry/{task_id}` | path: task_id | Wiki 重试任务状态 | WikiViewer | 本地 | 找不到任务或重试失败 | 重试后需同步 note document wiki_status |
| GET | `/api/wiki/status/{task_id}` | path: task_id | 单篇 Wiki job 状态 | WikiViewer | 本地 | 无状态时返回默认/错误 | 需兼容历史 running/materialize |
| POST | `/api/wiki/cancel/{task_id}` | path: task_id | 取消结果 | WikiViewer | 本地 | 取消失败返回错误 | 不能取消错误任务 |
| GET | `/api/image_proxy` | query: url | 图片响应 | Markdown 图片展示 | 本地/远端代理 | 拉取失败返回错误 | 禁止 SSRF 扩大化，保留必要校验 |

## Wiki 接口

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/wiki/graph` | 无 | `{nodes, edges, clusters}` | Wiki 页面/图谱 | 本地 | 无图返回空图 | 图字段需兼容前端图谱 |
| GET | `/api/wiki/communities` | 无 | community index | Wiki 页面 | 本地 | 无索引返回空/默认 | 社区 id 用字符串 key |
| GET | `/api/wiki/communities/{community_id}` | path: int | 单个 community | Wiki 页面 | 本地 | 不存在 404 | 不改变 id 类型 |
| GET | `/api/wiki/pages` | 无 | source page summaries | 旧 Wiki 页面 | 本地 | 空列表 | 保留旧调用兼容 |
| GET | `/api/wiki/pages/{page_id}` | path: page_id | `{id,title,markdown,contribution}` | 旧 Wiki 页面 | 本地 | 不存在 404 | page_id 需 safe_id |
| GET | `/api/wiki/articles/{source_id}` | path: source_id | 单篇 article detail，含 entities/concepts/claims/evidence/relations | WikiViewer | 本地 | contribution 不存在 404 | 前端字段名需与 contribution 对齐 |
| GET | `/api/wiki/file-pages` | 无 | source/entity/concept file page summaries | 旧 Wiki 文件页 | 本地 | 空列表 | 保留旧 Wiki 导航兼容 |
| GET | `/api/wiki/file-pages/{page_type}/{page_id}` | path: type/id | file page detail | 旧 Wiki 文件页 | 本地 | 不存在 404 | page_type 限 source/entity/concept 语义 |

## Chat / Conversation 接口

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/chat/index` | JSON: task/note 等 | 索引结果 | 聊天检索 | 本地 | 索引失败 | Chroma 持久化兼容 |
| GET | `/api/chat/status` | query | 索引/聊天状态 | 聊天 UI | 本地 | 返回状态错误 | 不阻塞页面加载 |
| POST | `/api/chat/ask` | 已下线 | 已下线 | 聊天 UI | 本地+LLM | 404/移除 | 已收口到 `/api/agent/v1/sessions/{session_id}/turns`（保留向后兼容入口请另行评审） |
| POST | `/api/chat/free` | 已下线 | 已下线 | 聊天 UI | 本地+LLM | 404/移除 | 已收口到 `/api/agent/v1`；历史兼容由会话迁移脚本处理 |
| POST | `/api/chat/free/stream` | 已下线 | 已下线 | 聊天 UI fetch | 本地+LLM | 404/移除 | 已收口到 `/api/agent/v1` |
| GET | `/api/conversations` | query | 会话列表 | 侧边栏/工作区 | 本地 | 空列表 | 软删除过滤 |
| GET | `/api/conversations/{conversation_id}` | path | 会话详情 | 工作区 | 本地 | 不存在 404 | 消息和文档结构兼容 |
| PUT/PATCH | `/api/conversations/{conversation_id}` | JSON patch | 更新会话 | 工作区 | 本地 | 更新失败 | 不能破坏 linked task |
| POST | `/api/conversations/{conversation_id}/messages` | JSON message | 新消息 | 聊天/笔记 | 本地 | 写入失败 | role/message_type 兼容；user refs 经 resolver 后写内部 authority provenance，客户端不能设置该字段 |
| PATCH | `/api/conversations/{conversation_id}/messages/{message_id}` | JSON patch | 更新消息 | 聊天/编辑 | 本地 | 不存在 404 | 保留 meta_json/sources_json；只有 provenance 为当前版本的 user→user 同 locator/revision 可复用发送时快照，历史/legacy/角色转换必须重解析 |
| DELETE | `/api/conversations/{conversation_id}` | path | 删除结果 | 会话删除 | 本地 | 删除失败 | 应软删并清理关联 artifacts |
| DELETE | `/api/conversations/{conversation_id}/documents/{task_id}` | path | 删除文档 | 文档删除 | 本地 | 删除失败 | 不误删其他 conversation |
| POST | `/api/conversations/{conversation_id}/workspace/cancel_task` | `card_id` | 取消结果 | 长任务卡 | 本地 | 不存在/跨会话 code=404；已结束 code=400 | 必须按卡片自身 `conversation_id` 校验归属 |

## Provider / Model / Config 接口

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/add_provider` | JSON provider | Provider | 设置页 | 本地 | 校验/连接失败 | API Key 不回显 |
| GET | `/api/get_all_providers` | 无 | Provider 列表 | 设置页、模型选择 | 本地 | 空列表 | 不泄露 API Key |
| GET | `/api/provider_templates` | 无 | Provider 模板 | 设置页 | 本地 | 空列表 | name 唯一 |
| POST | `/api/provider_templates` | JSON template | 模板 | 设置页 | 本地 | 写入失败 | 不破坏内置模板 |
| GET | `/api/get_provider_by_id/{id}` | path | Provider | 设置页 | 本地 | 不存在 404/错误 | 不泄露 API Key |
| POST | `/api/update_provider` | JSON provider | 更新结果 | 设置页 | 本地 | 更新失败 | enabled/base_url 语义兼容 |
| POST | `/api/connect_test` | JSON provider/model | 测试结果 | 设置页 | 本地+远端 | 远端失败返回错误 | 不记录敏感 payload |
| GET | `/api/model_list` | query | wrapper `data` 为已启用 Provider 的模型列表；每项含 `id/provider_id/model_name/context_window_tokens/supports_vision/supports_stream/created_at/capabilities` | 设置页 | 本地 | 空列表 | 保留 provider 关联；后三项是用户保存的运行配置，`capabilities` 仍仅为探测缓存 |
| GET | `/api/model_list/{provider_id}` | path | 模型列表 | 设置页 | 本地 | 空列表 | provider_id 语义不能改 |
| POST | `/api/models/defaults` | JSON: `model_name` | wrapper `data` 包含规范化 `model_name`、`context_window_tokens`、`supports_vision`、`supports_stream`、`source`、`matched_rule` | 模型添加弹窗 | 本地 | 空名称返回 wrapper `code=400`；目录缺失或损坏降级安全 fallback | 保持 `{code,msg,data}`；建议值不替代用户保存的运行配置 |
| POST | `/api/models` | JSON：`provider_id`、`model_name`、`context_window_tokens`（512–4,000,000）、严格布尔 `supports_vision`、严格布尔 `supports_stream` | wrapper `data` 为完整已保存模型行 | 设置页 | 本地 | 请求字段不合法由 FastAPI 返回 422；Provider 不存在 wrapper `code=404`；同 Provider+模型名重复（含并发插入的数据库约束冲突）wrapper `code=409` | 保持 `{code,msg,data}`；运行配置由调用方显式提交，不使用服务端写死默认值 |
| GET | `/api/models/delete/{model_id}` | path | wrapper 删除结果 | 设置页 | 本地 | 不存在 wrapper `code=404`；事务失败 `code=500` | 旧接口用 GET 删除，前端兼容；模型与对应 `model_capabilities` 探测缓存同一事务删除，失败整体回滚；不删除 Provider、笔记或 usage |
| POST | `/api/models/probe` | JSON provider/model | 能力探测 | 设置页/模型能力 | 本地+远端 | 探测失败写错误 | 支持 null=未知 |
| GET | `/api/model_enable/{provider_id}` | path | wrapper `data` 为该 Provider 已添加模型，每项含 `id/provider_id/model_name/context_window_tokens/supports_vision/supports_stream/created_at/capabilities` | 任务表单 | 本地 | 空列表 | 不改返回层级；三项运行字段为用户保存值，`capabilities` 仅为探测缓存且不得覆盖保存运行字段 |
| GET | `/api/sys_health` | 无 | 健康状态 | 后端初始化 | 本地 | 不健康 | 桌面 ready 门禁依赖 |
| GET | `/api/sys_check` | 无 | runtime/data_dir/ffmpeg/transcriber 等 | 设置/诊断 | 本地 | 返回检查失败项 | 字段用于诊断 |
| GET | `/api/deploy_status` | 无 | backend/cuda/whisper/ffmpeg/mcp | 设置/诊断 | 本地 | 返回检查失败项 | 契约测试覆盖 |
| POST | `/api/transcriber_config` | JSON | 保存配置 | 设置页 | 本地 | 写入失败 | 兼容本地转写器 |
| GET | `/api/transcriber_config` | 无 | 转写配置 | 设置页 | 本地 | 默认配置 | 字段兼容 |
| GET | `/api/transcriber_models_status` | 无 | 模型状态 | 设置页 | 本地 | 检查失败 | 不阻塞主流程 |
| POST | `/api/transcriber_download` | JSON | 下载任务 | 设置页 | 本地/远端 | 下载失败 | 需保留进度状态 |
| GET | `/api/get_downloader_cookie/{platform}` | path | cookie 状态 | 设置页 | 本地 | 不存在为空 | 不泄露敏感细节 |
| POST | `/api/update_downloader_cookie` | JSON | 更新结果 | 设置页 | 本地 | 写入失败 | cookie 不入日志 |
| POST | `/api/mcp/recheck` | 无/JSON | MCP 检查 | 设置页 | 本地 | 检查失败 | endpoint 保持 `/mcp` |
| GET | `/api/mcp_servers` | 无 | MCP server 配置列表 | MCP 设置页 | 本地 | 损坏配置降级为空 | 不返回 auth；headers/env 只返回 `***` 占位符 |
| PUT | `/api/mcp_servers/{server_id}` | server 配置 | 脱敏后的配置 | MCP 设置页 | 本地 | 校验 code=400；保存 code=500 | 编辑时省略凭证或回传 `***` 必须保留旧值，不能把占位符落盘 |
| GET | `/api/mcp_servers/enabled` | 无 | 已启用 server 的脱敏配置与 count | 设置/诊断 | 本地 | 空列表 | 与列表接口共用脱敏边界，不返回 auth/header/env 原值 |
| DELETE | `/api/mcp_servers/{server_id}` | path | 删除结果 | MCP 设置页 | 本地 | 不存在 code=404；保存 code=500 | 错误响应不得回显本地路径或敏感 payload |

## Learning Space / Research Search 接口

以下普通接口均使用 `{code,msg,data}`。学术与 GitHub 由后端默认查询；普通 Web 只在 Tavily/SearXNG 配置可用时查询；密钥不进入响应。

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/research-search/config` | 无 | Web 配置、超时和脱敏 `*_key_set` | 研究搜索设置页 | 本地 | 损坏配置降级默认值 | 不返回 Tavily/GitHub 原始密钥或旧 enabled scopes |
| PUT | `/api/research-search/config` | provider/endpoint/timeout，可选新密钥或 `clear_*`；旧 scopes 仍兼容 | 脱敏后的新配置 | 研究搜索设置页 | 本地 | 写入失败 | 空密钥保持旧值；显式 clear 才删除；scopes 不能关闭 academic/GitHub |
| POST | `/api/conversations/{cid}/learning-canvases` | 必填 `goal`；可选 `external_scopes/external_limit/research_space_id/provider_id/model_name/context_refs[]` | 完整 `LearningCanvas` v2 | 学习标签/Agent | 本地+可选远端+LLM | 非法输入 code=400；Note 失败为请求失败，投影/消息失败降级成功 | 先过滤证据并编译；`clarifying` 不写 Note，`ready` 通过 NoteImportService 入库并绑定 `document_task_id`；academic/GitHub 基线保持 |
| GET | `/api/conversations/{cid}/learning-canvases/{canvas_id}` | path | 完整 `LearningCanvas` | 学习卡 | 本地 | 不存在 code=404；越界 code=403 | cid/canvas_id 路径安全；刷新和重启可恢复 |
| PATCH | `/api/conversations/{cid}/learning-canvases/{canvas_id}` | `node_id`，可选 `user_label/user_summary` | 更新后的 `LearningCanvas` | 学习卡 | 本地 | 节点/画布不存在 code=404 | 只改用户覆盖字段，不覆盖 AI 原始 label/summary |
| POST | `/api/conversations/{cid}/learning-canvases/{canvas_id}/units/{node_id}/start` | path | `unit + canvas` | 学习卡/Agent | 本地 | 节点不存在 code=404 | 只能产生 exposed，不得直接 mastered |
| POST | `/api/conversations/{cid}/learning-canvases/{canvas_id}/units/{node_id}/evidence` | `kind/answer/rubric_result/provider_id/model_name` | `evidence + canvas` | Agent | 本地+已有 LLM 评测结果 | 无效证据 code=409/400 | 非空答案和完整 rubric；状态由后端计算 |
| GET | `/api/conversations/{cid}/learning-canvases/{canvas_id}/reviews/due` | path | 已到期复习项 | 学习卡/Agent | 本地 | 不存在 code=404 | 未到期 review 不得进入 mastered |

## Whiteboard / 语义白板接口

## Agent v1 接口（增量迁移）

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 错误语义 |
| --- | --- | --- | --- | --- | --- |
| POST | `/api/agent/v1/sessions` | `session_id?/title` | `{data: Conversation}` | UI/CLI | 400 |
| GET | `/api/agent/v1/sessions` | 无 | `{data: Conversation[]}` | UI/CLI | 空列表 |
| GET | `/api/agent/v1/sessions/{session_id}` | path | `{data: Conversation}` | UI/CLI | `session_not_found` |
| POST | `/api/agent/v1/sessions/{session_id}/turns` | `input/model?/idempotency_key?` | `{data: Turn}` | UI/CLI | 409 `session_busy` |
| GET | `/api/agent/v1/turns/{turn_id}/events` | `after_sequence?` | `{data: AgentEvent[]}` | UI/CLI | `turn_not_found` |
| POST | `/api/agent/v1/turns/{turn_id}/cancel` | 无 | `{data:{turn_id,accepted,status:cancelling}}` | UI/CLI | 404/409 | 只请求 native Turn 取消；最终 `cancelled` 由 SDK terminal event 写入 |
| POST | `/api/agent/v1/turns/{turn_id}/steer` | JSON steer payload | `{data:{turn_id,accepted}}` | UI/CLI | 404/409 | 不伪造 steer；native handle 不存在时返回 `steer_unsupported` |
| POST | `/api/agent/v1/approvals/{approval_id}` | `approved` / `decision`（兼容） | `approve`\|`deny` | UI/CLI | 404/409 | 仅将请求透传至 SDK |
| GET/PUT | `/api/agent/v1/sessions/{session_id}/model-preference` | `default_model_id/fallback_models` | `{data: Preference}` | 设置/CLI | `invalid_input` |

这些接口复用 `conversations` 作为 Session 主表；Agent 表只保存 Turn、Event 和模型偏好，不建立第二套历史。

CLI 契约：`notemeld agent -p/--prompt` 提交单次 Turn；`--conversation/--session` 继续指定 Conversation；`--model` 传递模型覆盖；`--output/--format text|json|jsonl` 控制输出。REPL 的 `/new`、`/resume ID`、`/sessions`、`/model [NAME]`、`/exit` 只组合本表接口，不直接写数据库，也不加载另一套 Agent runtime。

Agent Host 控制约束：SDK 原生 driver 请求包含 `model.stream`、`tool.describe` 和 `tool.invoke`；Host 对 `tool.describe` 只返回 bounded namespaced capabilities。ABI v1 每轮 `model.stream` 的 canonical `messages` 是权威，Host 为该轮补齐安全 `model/model_override`、当前 `input/context_refs`、工具描述和显式 generation config；返回继续使用 schema v1 的 chunks/completion envelope。审批由 `POST /api/agent/v1/approvals/{approval_id}` 发送 `{"decision":"approve|deny"}` 或兼容 `{"approved":true|false}` 到同一个 native runtime；Host 不直接修改 Turn 终态。

白板采用 `{code,msg,data}` 包装；`whiteboard_selection` 经过后端 resolver 后改写为 authority snapshot。

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/conversations/{cid}/whiteboards` | `title/description` | `WhiteboardSnapshot` | 学习面板 / API | 本地 | 400/404 | 仅允许 conversation 归属操作 |
| GET | `/api/conversations/{cid}/whiteboards` | 无 | `WhiteboardSummary[]` | 学习面板 | 本地 | 404/500 | 软删白板不返回 |
| GET | `/api/conversations/{cid}/whiteboards/{wid}` | path | 完整 `WhiteboardSnapshot` | 学习面板 / API | 本地 | 403/404 | `whiteboard`、`conversation` 越界不可透传存在性 |
| DELETE | `/api/conversations/{cid}/whiteboards/{wid}` | path | `{deleted:true}` | 学习面板 | 本地 | 403/404 | 软删除白板，保留画布快照用于历史 context 复用 |
| POST | `/api/conversations/{cid}/whiteboards/{wid}/mutations` | `base_revision/operations[]` | `WhiteboardMutationResult` | 学习面板 | 本地 | 409/400/422/500 | 一次 mutation 成功才递增 revision，失败不落库 |
| POST | `/api/conversations/{cid}/whiteboards/{wid}/context` | `revision/card_ids/relation_ids/label` | 后端 authority `ConversationContextRef` | chat/learning | 本地 | 400/403/404/409/500 | 服务端重建快照并截断 `source_ids`；客户端 snapshot 仅作展示 |
| POST | `/api/conversations/{cid}/whiteboards/{wid}/publish-note` | `base_revision/scope/card_ids/relation_ids/provider_id/model_name` | `WhiteboardPublishResult` | 学习面板 / chat | 本地 | 409/400/500/503 | 发布失败不修改 `published_revision`，成功后异步触发向量索引/Wiki |
| POST | `/api/conversations/{cid}/whiteboards/from-learning-canvas/{canvas_id}` | 无 | `WhiteboardSnapshot` | 学习面板 / API | 本地 | 404/409/500 | 与 `LearningCanvas` v1/v2 幂等转换，保留旧 `canvas` 文件 |

## Ingestion / Migration / Usage / Style 接口

Wiki 抽取/增强沿用既有任务状态与重试接口，不改变 response schema。错误详情现在保留 Provider 网络/超时错误，并将兼容模型的空 final response 区分为 `output truncated before final JSON`、`produced reasoning but no final JSON` 或 `returned empty content`；错误不得包含模型 reasoning 原文。

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/ingestion/{task_id}/report` | path | 摄入报告 | 文档详情 | 本地 | 不存在 404 | artifact 路径安全 |
| GET | `/api/ingestion/{task_id}/evidence` | path | evidence | 文档详情 | 本地 | 不存在 404 | 字段兼容 |
| GET | `/api/ingestion/{task_id}/chunks` | path | chunks | 文档详情 | 本地 | 不存在 404 | chunk schema 兼容 |
| GET | `/api/ingestion/{task_id}/source` | path | source | 文档详情 | 本地 | 不存在 404 | 不泄露越界文件 |
| GET | `/api/ingestion/{task_id}/job` | path | job | 文档详情 | 本地 | 不存在 404 | job 状态兼容 |
| POST | `/api/migration/export` | JSON options | export job/file | 数据迁移页 | 本地 | 失败写 job | session token 保护 |
| POST | `/api/migration/import` | JSON path/options | import job | 数据迁移页 | 本地 | 失败写 job | zip 主流程 |
| POST | `/api/migration/import/upload` | multipart zip | upload result | 数据迁移页 | 本地 | 校验失败 | zip 安全校验 |
| GET | `/api/migration/{job_id}/job` | path | job 状态 | 数据迁移页 | 本地 | 不存在 404 | job_id 安全 |
| GET | `/api/migration/{job_id}/download` | path | 文件下载 | 数据迁移页 | 本地 | 不存在 404 | 禁止路径穿越 |
| POST | `/api/migration/reindex` | JSON | reindex job | 数据迁移页 | 本地 | 失败写 job | 导入后默认重建索引 |
| GET | `/api/usage/overview` | query | usage 概览 | 用量页 | 本地 | 空统计 | 来源为 model_usage_records |
| GET | `/api/usage/records` | query | usage 记录 | 用量页 | 本地 | 空列表 | 分页/过滤兼容 |
| GET | `/api/usage/task_summary` | query | 任务汇总 | 用量页 | 本地 | 空统计 | task_id 聚合 |
| GET | `/api/usage/task_calls/{task_id}` | path | 任务调用 | 用量页/任务详情 | 本地 | 空列表 | task_id 不能改语义 |
| GET/POST/PUT/DELETE | `/api/note_styles*` | JSON/multipart/path | 样式和提取任务 | StylesPage | 本地+LLM | 失败写 task/error | 内置样式不可随意删 |

## Imported Notes 接口

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/api/notes/import` | Markdown/title 等 | 导入结果 | MCP/导入入口 | 本地 | 写入失败 | 导入后触发 Wiki 抽取 |
| GET | `/api/notes/search` | query: title/query | 搜索结果 | MCP | 本地 | 空列表 | 标题搜索兼容 |
| GET | `/api/notes/read` | query: title/task_id | 笔记内容 | MCP | 本地 | 不存在 404 | 禁止路径穿越 |

## MCP 接口

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 | 兼容性约束 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| POST | `/mcp` | JSON-RPC 2.0 | JSON-RPC result/error | MCP 客户端 | 本地/可远程 | JSON-RPC error | endpoint 固定，工具名兼容 |

当前 MCP methods：

- `initialize`
- `tools/list`
- `tools/call`
- `resources/list`
- `resources/read`

当前 MCP tools：

- `generate_note`
- `get_task`
- `get_note`
- `list_models`
- `notemeld_import_note`
- `notemeld_search_notes`
- `notemeld_read_note`
- `notemeld_search_wiki`
- `notemeld_read_wiki_page`

## 远端接口边界

- LLM Provider 请求由后端发起，不由前端直接调用。当前主路径走 `backend/app/ai/`（notemeld-ai 抽象层）：通过 `NotemeldGPT` 适配器在 `create_chat_completion` 内调 `Models.complete()`，由 notemeld-ai 统一写 usage。旧 `backend/app/gpt/` 的 `GPTFactory`/`UniversalGPT` 过渡期保留供回滚（`from_config` 已加 `DeprecationWarning`）；`services/model.py` 的 `list_models` 仍走 `GPTFactory`（非 chat-completion 路径）。详见 `docs/system/current-architecture.md` 的 LLM 调用层章节。
- 视频平台、网页和转写服务由后端下载器/转写器调用。
- 前端唯一允许直接访问后端之外的场景应经过明确设计，例如外链打开或图片代理；新增远端调用必须说明安全边界。

## Agent Knowledge Capability Contract

更新时间：2026-08-18

本阶段不新增公共 HTTP 或 MCP endpoint。四个能力通过 Agent Host 的通用 `ToolDriver` 注册：

| capability id | 作用 | 关键参数 |
| --- | --- | --- |
| `knowledge:article_lookup` | K0 精确文章读取 | `article_ids?`, `query?` |
| `knowledge:evidence_search` | K1 原文证据混合检索 | `query`, `article_ids?`, `location?`, `top_k?` |
| `knowledge:profile_search` | K2 高密画像检索 | `query`, `article_ids?`, `filters?`, `top_k?` |
| `knowledge:semantic_search` | K3 实体/概念/关系检索 | `query`, `article_ids?`, `node_types?`, `relation_types?`, `hops?`, `top_k?` |

除 K0 精确读取外，查询均返回 `knowledge_result.v1` envelope：`schema_version`、`capability_id`、`total`、`results`、`warnings`。每个 result 必须包含 `article_id`；K1 追加 chunk/location，K3 追加 term/relation/evidence provenance。`article_ids` 缺省为全库，显式 `[]` 返回 `invalid_arguments`，不能静默放宽为全库。
