# API Inventory

更新时间：2026-06-19

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
| POST | `/api/chat/ask` | JSON: question/context | 回答 | 聊天 UI | 本地+LLM | LLM 错误返回失败 | 需保留来源引用 |
| POST | `/api/chat/free` | JSON: messages/model | 非索引自由聊天 | 聊天 UI | 本地+LLM | LLM 错误 | 不依赖 note task |
| POST | `/api/chat/free/stream` | JSON: messages/model | 流式响应 | 聊天 UI fetch | 本地+LLM | 流中错误事件 | 前端裸 fetch 需兼容 |
| GET | `/api/conversations` | query | 会话列表 | 侧边栏/工作区 | 本地 | 空列表 | 软删除过滤 |
| GET | `/api/conversations/{conversation_id}` | path | 会话详情 | 工作区 | 本地 | 不存在 404 | 消息和文档结构兼容 |
| PUT/PATCH | `/api/conversations/{conversation_id}` | JSON patch | 更新会话 | 工作区 | 本地 | 更新失败 | 不能破坏 linked task |
| POST | `/api/conversations/{conversation_id}/messages` | JSON message | 新消息 | 聊天/笔记 | 本地 | 写入失败 | role/message_type 兼容 |
| PATCH | `/api/conversations/{conversation_id}/messages/{message_id}` | JSON patch | 更新消息 | 聊天/编辑 | 本地 | 不存在 404 | 保留 meta_json/sources_json |
| DELETE | `/api/conversations/{conversation_id}` | path | 删除结果 | 会话删除 | 本地 | 删除失败 | 应软删并清理关联 artifacts |
| DELETE | `/api/conversations/{conversation_id}/documents/{task_id}` | path | 删除文档 | 文档删除 | 本地 | 删除失败 | 不误删其他 conversation |

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
| GET | `/api/model_list` | query | 模型列表 | 设置页 | 本地 | 空列表 | 保留 provider 关联 |
| GET | `/api/model_list/{provider_id}` | path | 模型列表 | 设置页 | 本地 | 空列表 | provider_id 语义不能改 |
| POST | `/api/models` | JSON model | 创建模型 | 设置页 | 本地 | 重复/失败 | 模型名兼容 |
| GET | `/api/models/delete/{model_id}` | path | 删除结果 | 设置页 | 本地 | 删除失败 | 旧接口用 GET 删除，前端兼容 |
| POST | `/api/models/probe` | JSON provider/model | 能力探测 | 设置页/模型能力 | 本地+远端 | 探测失败写错误 | 支持 null=未知 |
| GET | `/api/model_enable/{provider_id}` | path | 可用模型 | 任务表单 | 本地 | 空列表 | 不改返回层级 |
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

## Ingestion / Migration / Usage / Style 接口

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

- LLM Provider 请求通过后端 gpt/provider 封装发起，不由前端直接调用。
- 视频平台、网页和转写服务由后端下载器/转写器调用。
- 前端唯一允许直接访问后端之外的场景应经过明确设计，例如外链打开或图片代理；新增远端调用必须说明安全边界。
