# API Inventory

更新时间：2026-08-27

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

## Cloud backend（first slice）

`cloud/` 是独立 FastAPI 服务，不改变本地 `/api` 路由。云端普通 API 使用 `{code,msg,data}`；远程 relay 使用 WebSocket，消息 payload 不持久化。

| 方法 | 路径 | 作用 | 认证 |
| --- | --- | --- | --- |
| GET | `/health` | 云端健康检查 | 无 |
| POST | `/v1/auth/login` | 云端用户/管理员登录并签发 bearer token | 无（限流待补） |
| POST | `/v1/auth/revoke` | 撤销当前 bearer token | bearer token |
| POST | `/v1/auth/rotate` | 原子撤销当前 token 并签发新 token | bearer token |
| GET | `/v1/admin/users` | 管理员查询普通用户 | admin token |
| POST | `/v1/admin/users` | 管理员创建普通用户 | admin token |
| PUT | `/v1/admin/users/{user_id}` | 管理员修改普通用户用户名、密码或禁用状态 | admin token |
| DELETE | `/v1/admin/users/{user_id}` | 管理员删除普通用户 | admin token |
| POST | `/v1/devices` | 注册用户设备 | bearer token |
| GET | `/v1/devices` | 查询当前用户设备 | bearer token |
| POST | `/v1/devices/{device_id}/revoke` | 撤销当前用户设备 | bearer token |
| POST | `/v1/pairings/start` | 创建 5 分钟有效的一次性配对码 | bearer token |
| POST | `/v1/pairings/confirm` | 使用配对码注册设备 | bearer token |
| POST | `/v1/grants` | 创建设备间远程控制授权 | bearer token |
| POST | `/v1/sessions` | 创建 cloud-native/device-remote session | bearer token |
| GET | `/v1/sessions` | 查询当前用户云端会话及收纳状态 | bearer token |
| POST | `/v1/sessions/{session_id}/commands` | 以 request_id + payload_hash 幂等提交消息 | bearer token |
| GET | `/v1/sessions/{session_id}/snapshot` | 读取 session snapshot 和事件 | bearer token |
| GET | `/v1/sessions/{session_id}/events?after=` | 按 event sequence 拉取事件 | bearer token |
| POST | `/v1/sessions/{session_id}/archive` | 收纳当前用户会话 | bearer token |
| DELETE | `/v1/sessions/{session_id}` | 硬删除当前用户云端会话 | bearer token |
| WebSocket | `/v1/relay/connect/{session_id}` | 在线实时 relay；不提供离线历史 | bearer token（后续补充） |

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

## Application Host 接口

协议定义：[`application-protocol-v1.md`](application-protocol-v1.md)。本节只记录当前 API 实现，不替代协议。

应用接口统一使用 `{code,msg,data}` wrapper，并要求现有 session token。应用 UI 通过带 run context 的 capability bridge 读取数据，不直接调用旧 `/api/wiki/*` UI 入口。

| 方法 | 路径 | 请求参数 | 返回结构 | 调用方 | 类型 | 错误语义 |
| --- | --- | --- | --- | --- | --- | --- |
| GET | `/api/applications` | 无 | 应用摘要列表 | 应用列表 | 本地 | 应用不存在/清单损坏返回错误 |
| GET | `/api/applications/{app_id}` | path: app_id | manifest 摘要、启用状态和运行状态 | Application Host | 本地 | 不存在 404 |
| POST | `/api/applications/{app_id}/enable`、`/disable` | path: app_id | 更新后的应用摘要 | 应用设置/Host | 本地 | 不存在 404；禁用应用启动返回 409 |
| POST/GET | `/api/applications/{app_id}/instances` | title、可选 instance_id | 应用实例及逻辑 workspace 引用 | Application Host | 本地 | 越权/冲突返回错误 |
| POST/GET | `/api/applications/{app_id}/instances/{instance_id}/runs`、`/api/applications/runs/{run_id}` | run payload / run_id | `run_id`、runtime kind、Run status | Application Host | 本地 | 幂等 payload 冲突、运行策略拒绝、找不到 run |
| POST | `/api/applications/runs/{run_id}/invoke` | method、input | 应用 runtime result | Application UI/SDK | 本地 | Run 非活动、transport/协议错误 |
| POST | `/api/applications/runs/{run_id}/capability` | capability、method、input | capability result | Application UI/SDK | 本地 | Run 非活动；未声明 capability 403；不支持 method 501 |
| POST | `/api/applications/runs/{run_id}/cancel` | path: run_id | 取消后的 Run | Application Host | 本地 | 已终态运行保持终态 |
| GET/PUT | `/api/applications/settings/workspace` | PUT: 绝对 root | 默认 workspace ref、root、configured | Settings | 本地 | 非绝对路径或越权路径 400 |

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

## Candidate boundary（N06）

- `GET /api/candidates`：列出 candidate（session token required）。
- `POST /api/candidates`：保存 scope、evidence/trace、artifact/patch、tests、risks、permissions、rollback；只接受 Application/plugin 两类。
- `GET /api/candidates/{candidate_id}`：读取完整 candidate 和下一步提示。
- `POST /api/candidates/{candidate_id}/validate`：静态边界与证据门禁；缺 evidence/test/rollback、越权、SDK 路径/制品/公共契约触碰时 fail closed。
- `POST /api/candidates/{candidate_id}/approve`、`POST /api/candidates/{candidate_id}/decline`：显式人工审批/拒绝入口。
- `POST /api/candidates/{candidate_id}/decision`：人工审批/拒绝，只记录追加式决策（审批主体由受保护桌面 API 固定为 `desktop-user`）；不 patch/激活 Application，plugin 仍必须回到 N03 标准包流程。

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
| POST | `/api/agent/v1/approvals/{approval_id}` | `decision=approve\|deny`；兼容 `approved: bool` | `{data:{approval_id,decision,accepted:true}}` | UI/CLI | 400 `invalid_approval_decision`；404 `approval_not_found`；409 `approval_already_resolved` / `approval_turn_terminal` | 仅将请求原子透传至同一 SDK runtime；成功才表示原暂停点已被唤醒，不伪造 ACK |
| GET/PUT | `/api/agent/v1/sessions/{session_id}/model-preference` | `default_model_id/fallback_models` | `{data: Preference}` | 设置/CLI | `invalid_input` |
| GET | `/api/agent/v1/turns/{turn_id}/diagnostics` | path | `{data:{turn,events,event_count,last_sequence}}` | 桌面任务诊断 | `turn_not_found` |
| GET | `/api/agent/v1/capabilities` | 无 | `{data: Capability[]}` | MCP/外部 Agent/桌面 | bounded capability schema |
| POST | `/api/agent/v1/capabilities/{name}` | `{arguments,request_id?,actor_id?}` | `{data: ToolResult}` | CLI/外部 Agent | stable ToolResult error codes |

这些接口是 Web、Tauri、CLI、源码和桌面打包运行的唯一 Agent HTTP 入口。它们复用 `conversations` 作为 Session 主表；Agent 表只保存 Turn、Event 和模型偏好，不建立第二套历史。Router 只向 `AgentHostEntry` 提交生命周期命令，不直接写 Agent 表；同一 Session 的并发 Turn 返回 409 `session_busy`，不同 Session 可各自运行活动 Turn。

CLI 契约：`notemeld agent -p/--prompt` 提交单次 Turn；`--conversation/--session` 继续指定 Conversation；`--model` 传递模型覆盖；`--output/--format text|json|jsonl` 控制输出。REPL 的 `/new`、`/resume ID`、`/sessions`、`/model [NAME]`、`/exit` 只组合本表接口，不直接写数据库，也不加载另一套 Agent runtime。

Agent Host 控制约束：SDK 原生 driver 请求包含 `model.stream`、`tool.describe` 和 `tool.invoke`；Host 对 `tool.describe` 只返回 bounded namespaced capabilities。ABI v1 每轮 `model.stream` 的 canonical `messages` 是权威，Host 为该轮补齐安全 `model/model_override`、当前 `input/context_refs`、工具描述和显式 generation config；返回继续使用 schema v1 的 chunks/completion envelope。`tool.invoke` 的 Host adapter 返回 SDK ToolResult wire shape `{call_id, output}`，FFI driver completion 只把 `output` 交给 Rust scheduler；成功 output 为 `{ok:true,result}`，可恢复失败为 `{ok:false,error:{code,message}}`。稳定产品错误 code 为 `unknown_tool`、`invalid_arguments`、`permission_denied`、`business_error`、`tool_execution_error`，且不得携带原参数、Provider payload、凭证或异常原文。产品级失败仍形成 ToolResult 并触发下一轮模型；只有 Host/ABI 协议损坏才返回 driver-level `ok:false` 并终止 Turn。危险或未知工具由 SDK 发出 `approval.required` 并暂停原 Turn；approve 后 SDK 才调用工具，deny 形成带原 call id 的拒绝 ToolResult。审批 API 把决定原子传给同一个 native runtime；Host 只把 `approval.required/resolved` 与 `waiting_approval/running` 投影到既有 Event/Turn，不直接修改终态或实现 Agent loop。

N02 只新增内部 SDK host ports，不新增 HTTP API：`NoteMeldNoteStoreAdapter` 提供
read/search/create/update/link/relations，`NoteMeldOperationStore` 提供
begin/checkpoint/commit/fail/mark-needs-attention/get-by-request，
`NoteMeldNoteAuthority` 裁决 actor 与 source locator。N05/I03 才负责把这些 ports
接入公开 Agent/MCP transport。N05 的 capability endpoint、CLI 和 MCP Note
create/link/read/search 共享 `NoteMeldCapabilityRegistry` 与 Note authority；入口不直接写
SQLite 或 Agent Event。MCP 仍使用根路径 `/mcp`，新增公开工具
`notemeld_create_note`、`notemeld_link_notes`、`notemeld_note_relations`。

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
- `notemeld_document_to_markdown`
- `notemeld_image_ocr`
- `notemeld_video_fetch`
- `notemeld_audio_extract`
- `notemeld_audio_transcribe`
- `notemeld_video_frames`

## Agent Content Conversion Capabilities

这些能力通过 `/api/agent/v1/capabilities` 和 Agent Host 的通用
`ToolDriver` 暴露；MCP 使用同一 capability registry 和
`conversion-artifact.v1` 结果 envelope。工具只返回中间产物，不直接创建 Note。

| capability id | 输入 | 输出 | 一期 Host | 说明 |
| --- | --- | --- | --- | --- |
| `document:to_markdown` | `file_url`, `file_name` | Markdown artifact + provenance | desktop | Rust/anydoc；图片型 PDF 可能返回 OCR required/failed |
| `image:ocr` | `file_url`, `file_name` | OCR text + lines/pages/bbox/confidence | desktop | 不提供 image ASCII |
| `video:fetch` | `source_url`, `platform?` | media metadata artifact | desktop | 复用现有下载器 |
| `audio:extract` | `source_url`, `platform?` | audio metadata artifact | desktop | 复用 ffmpeg/下载器 |
| `audio:transcribe` | `source_url`, `platform?` | timestamped transcript artifact | desktop | 字幕优先、配置转写 fallback |
| `video:frames` | `source_url`, `platform?`, `timestamps?` | frame/OCR artifact | desktop | 当前关闭视觉总结，只返回基础 OCR 结果 |

服务端列为 contract-ready，部署时必须提供对应运行时依赖；mobile-native
和 WASM 列为一期 unsupported，不对未接入平台声称通过测试。

## 远端接口边界

### Cloud sync backend (v1)

Cloud service endpoints are intentionally separated from the local `/api` namespace. Authentication uses bearer tokens issued by `/v1/auth/login`; relay frames are opaque encrypted envelopes and are never persisted by the relay.
All HTTP requests are rejected with 413 before parsing when their declared
Content-Length exceeds `NOTEMELD_CLOUD_MAX_REQUEST_BYTES` (16 MiB by default).
The canonical cloud-native session prefix is `/v1/cloud/sessions`; the earlier
`/v1/sessions` paths remain backward-compatible aliases during client rollout.

`GET /health` is a liveness probe. `GET /ready` verifies SQLite access and a
writable Workspace root, returning HTTP 503 with per-check status when the
instance should not receive traffic.

`/v1/auth/login` accepts either the legacy username label or explicit
`account_id`; clients should prefer `account_id` so token identity does not
depend on a display label.
Issued account tokens expose a stable `jti` (the opaque token ID), audience,
scopes and expiry; only the token digest is persisted.
Users can manage independent PAT-style tokens via `POST/GET /v1/auth/tokens`
and `POST /v1/auth/tokens/{jti}/revoke`; raw token material is returned only
at creation time. Login tokens currently carry wildcard scope. PAT access to
the core session API is enforced as follows: `session.read` permits session,
command-status, snapshot and event reads; `session.write` permits session and
command creation. Missing scopes return HTTP 403.
The remaining bearer APIs use the same least-privilege mapping: `auth.token`
for PAT management, `device.read/device.write` for device and pairing
operations, `grant.read/grant.write` for remote-control grants,
`share.read/share.write` for share-token management, and
`workspace.read/workspace.write` for cloud workspace reads and mutations.
Rotation preserves the source token's audience, scopes and expiry rather than
upgrading a PAT to a wildcard token.

Failed logins are limited to five attempts per source/account key in a
60-second process-local window and return HTTP 429 after the limit. Production
multi-instance deployments must replace this in-memory counter with a shared
rate-limit store.

Web access is disabled by default; `NOTEMELD_CLOUD_CORS_ORIGINS` accepts a
comma-separated explicit origin allowlist. Wildcard origins are not enabled by
the default configuration.

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/v1/cloud/sessions/import` | create a new independent cloud-native session from an idempotent, allowlisted local full-share snapshot; validates active source device, secrets, paths, file count/size and SHA-256 |
| POST | `/v1/devices/register` | canonical device registration path (legacy `/v1/devices` remains supported) |
| POST | `/v1/devices/{device_id}/challenge` | issue a one-time device proof challenge |
| POST | `/v1/devices/{device_id}/challenge/verify` | verify an Ed25519 proof and authorize the device for a short relay window |
| DELETE | `/v1/sessions/{session_id}` | hard-delete session metadata and purge workspace/backups when no other session references that workspace |
| GET | `/v1/workspaces/{workspace_id}/stats` | workspace file count and bytes used |
| GET/PUT | `/v1/workspaces/{workspace_id}/files/{path}` | UTF-8 file read/write with traversal and symlink checks; writes are atomic |
| DELETE | `/v1/workspaces/{workspace_id}/files/{path}` | delete one file after traversal and symlink checks |
| GET | `/v1/workspaces/{workspace_id}/files?prefix=` | list safe logical file paths and size/mtime metadata |
| POST/GET | `/v1/workspaces/{workspace_id}/backups` | create/list local-disk ZIP backups |
| POST | `/v1/workspaces/{workspace_id}/backups/restore` | safely restore a backup as an atomic per-file overlay |
| GET | `/v1/grants` | list remote-control grants |
| POST | `/v1/grants/{grant_id}/revoke` | revoke a grant |
| DELETE | `/v1/grants/{grant_id}` | canonical grant revoke path (legacy POST revoke remains supported) |
| POST/GET | `/v1/share-tokens` | create/list scoped share tokens; raw token is returned only on creation |
| POST | `/v1/share-tokens/{id}/revoke` | revoke a share token |
| GET | `/v1/shared/{session_id}/snapshot` | read a session snapshot with `X-Share-Token` |
| GET | `/v1/shared/{session_id}/events` | read events after a cursor with `X-Share-Token` |
| POST | `/v1/shared/{session_id}/commands` | submit a cloud-native command when the share token explicitly has `message.send` |
| WS | `/v1/relay/connect/{session_id}?device_id=...` | validated, targeted opaque-frame relay; requires an active device and non-expired grant; returns `host_offline` when target is not connected, rejects replayed sequence numbers, enforces 120 frames/minute/connection, and forwards a host `received` receipt on the reverse direction |
Only one active relay connection is retained per device/session; a newer
connection replaces the older one with WebSocket close code `4009`.
| GET | `/v1/admin/audits?limit=` | admin-only redacted security and lifecycle audit records |

Remote grants require both active devices to have registered public keys;
device IDs alone are not sufficient to authorize E2EE control.
The API validates registered key material as 32-byte URL-safe Base64 Ed25519
public keys before accepting a device for a grant.
Registered devices can rotate keys with `POST /v1/devices/{device_id}/rotate-key`;
the old public key is replaced immediately and the rotation is audited.
Revoking a device also revokes all active Grants that reference it in the same
transaction.
When omitted, a standard Grant receives `message.send`, `context.select`,
`model.select` and `tool.invoke`; elevated approval/full-access scopes must be
explicitly requested and are never inferred from a permanent expiry.
`POST /v1/devices/{device_id}/heartbeat` records `last_seen_at`; relay
connections update the same field on connect.
When `NOTEMELD_CLOUD_REQUIRE_DEVICE_PROOF=true`, relay connect additionally
requires a non-expired proof from the challenge/verify endpoints. Proofs are
process-scoped and short-lived; clients must repeat the challenge after a
restart or expiry.
Device registration is idempotent for the owning account (metadata/key is
updated); the same ID owned by another account remains a conflict.
Relay `command` frames additionally require the Grant's `message.send` scope;
`receipt` and `event` frames are allowed only on an existing bidirectional Grant.
When a Grant contains `workspace_refs`, the current session workspace must be
listed; an empty list retains the account-level default behavior.
The versioned frame schema carries `nonce`, `frame_type`, sequence and opaque
`ciphertext`; relay never interprets plaintext or AEAD contents.
Relay validates the nonce as URL-safe Base64 encoding of a 12-byte AEAD nonce;
missing or malformed nonces are rejected before routing.
Relay replay cursors are persisted per `(session_id, sender_device_id)` and
advanced transactionally, so a cloud restart does not reset the highest
accepted sequence even though frame payloads remain non-persistent.

`POST /v1/sessions/{session_id}/copy` creates a new independent session and
workspace copy, retaining `copied_from` only as provenance; it does not create
a runtime parent/child synchronization relationship.
`POST /v1/sessions/{session_id}/authority/rotate` increments the persisted
authority epoch; relay rejects frames from older epochs.
`POST /v1/sessions/{session_id}/authority/lease` acquires or renews a
5–300-second exclusive execution lease using SQLite transactional fencing;
another live owner receives HTTP 409.
Session archive/restore/list accepts optional `X-Device-Id`; when present,
archive visibility is isolated to that active device. Legacy rows without a
device ID remain visible as compatibility archives.
`GET /v1/sessions/{session_id}/commands?after=&limit=` lists command states by
sequence cursor for reconnect and queue reconstruction.

Client adapters may use `cloud/crypto.py` for the E2EE handshake and AEAD frame
payload. The cloud relay treats the resulting ciphertext as opaque; the
crypto test is skipped in environments where `cryptography` is not installed.

Workspace writes enforce the deployment-level `NOTEMELD_CLOUD_MAX_WORKSPACE_BYTES`
quota and return `413 workspace quota exceeded` before modifying a file.

`POST /v1/sessions/{id}/commands` is only valid for `cloud_native` sessions. A
`device_remote` session must deliver commands through the host relay; the cloud
service never fabricates a remote Agent result.

Cloud-native commands are durably queued and claimed in sequence by one worker
per session within one API process. The
configured `CloudAgentRunner` calls an OpenAI-compatible provider when
`NOTEMELD_CLOUD_AGENT_BASE_URL` is set; otherwise its deterministic response is
intended only for protocol smoke tests, not production inference.
Configured providers currently receive only session-bound read-only workspace
tools (`workspace.list`, `workspace.read`); mutation tools require a future
approval and are never executed implicitly.
Commands are first persisted as `queued`, then claimed as `running`; provider failures are projected as
`turn.failed` with a redacted error and remain queryable by command id. On
startup, any leftover `running` command is fail-closed as `needs_attention`
with a `turn.needs_attention` event rather than being replayed automatically.
The command submission endpoint returns `200` for a completed command and
`202` when the bounded wait expires while the command remains queued/running.
Claimed commands expose a bounded lease owner/expiry and attempt count in the
command status API. SQLite `BEGIN IMMEDIATE` makes claim single-winner across
processes; expired running work remains fail-closed until explicit recovery.
Operators can explicitly recover `needs_attention` commands with
`POST /v1/cloud/sessions/{session_id}/commands/{command_id}/recover` using
`resume` (requeue) or `abandon`; both transitions are idempotent and audited.

`/v1/models` provides per-user cloud model metadata CRUD and default selection.
Provider credentials are encrypted at rest with `NOTEMELD_CLOUD_SECRET_KEY`
(falling back to the bootstrap admin password) and responses expose only
`has_api_key`.
Sessions may set `model_id` when created; cloud execution then resolves the
enabled model row for that user and constructs a bounded OpenAI-compatible
runner for the command. Unsupported providers or disabled models fail closed.
Model base URLs must be absolute HTTP(S) URLs without embedded credentials or
credential-like query parameters.

Cloud Agent workspace mutation tools (`workspace.write`, `workspace.delete`) do
not mutate immediately. They create an auditable `pending` approval exposed by
`/v1/cloud/sessions/{session_id}/approvals`; resolve with `approved` or
`rejected`. Approval currently records the decision boundary; execution resume
is performed synchronously with the approval transition using the same safe
workspace resolver; remote-approval grant enforcement remains a follow-up slice.
Approval listings return only a bounded content preview.

The current slice provides scoped share-token read/control access and cloud
workspace backup/restore. Multi-instance queue fencing and full end-to-end key
exchange remain future work; device relay still requires the platform clients
to perform the E2EE handshake before sending opaque frames.

- LLM Provider 请求由后端发起，不由前端直接调用。当前主路径走 `backend/app/ai/`（notemeld-ai 抽象层）：通过 `NotemeldGPT` 适配器在 `create_chat_completion` 内调 `Models.complete()`，由 notemeld-ai 统一写 usage。旧 `backend/app/gpt/` 的 `GPTFactory`/`UniversalGPT` 过渡期保留供回滚（`from_config` 已加 `DeprecationWarning`）；`services/model.py` 的 `list_models` 仍走 `GPTFactory`（非 chat-completion 路径）。详见 `docs/system/current-architecture.md` 的 LLM 调用层章节。
- 视频平台、网页和转写服务由后端下载器/转写器调用。
- 前端唯一允许直接访问后端之外的场景应经过明确设计，例如外链打开或图片代理；新增远端调用必须说明安全边界。

## Agent Knowledge Capability Contract

## Official Link Note Capability Contract

`official-link-note:create` is an installed-plugin capability, not a new HTTP
endpoint. The existing `/api/generate_note` task entry delegates both video and
web links to it. Its host port owns Note/task persistence, progress,
cancellation and error projection; the plugin owns only URL routing and does
not access Conversation, Agent Event or SQLite internals.

| capability id | input | output | compatibility |
| --- | --- | --- | --- |
| `official-link-note:create` | `url`, `platform`, optional `force_web_fallback` and `options` | host Note result / stable task error | N01 seven platforms plus `web_link`; subtitle-first, download, transcription, screenshots, multi-source summary, web scrape, task state and fallback remain covered by N04 matrix |

更新时间：2026-08-18

本阶段不新增公共 HTTP 或 MCP endpoint。四个能力通过 Agent Host 的通用 `ToolDriver` 注册：

| capability id | 作用 | 关键参数 |
| --- | --- | --- |
| `knowledge:article_lookup` | K0 精确文章读取 | `article_ids?`, `query?` |
| `knowledge:evidence_search` | K1 原文证据混合检索 | `query`, `article_ids?`, `location?`, `top_k?` |
| `knowledge:profile_search` | K2 高密画像检索 | `query`, `article_ids?`, `filters?`, `top_k?` |
| `knowledge:semantic_search` | K3 实体/概念/关系检索 | `query`, `article_ids?`, `node_types?`, `relation_types?`, `hops?`, `top_k?` |

除 K0 精确读取外，查询均返回 `knowledge_result.v1` envelope：`schema_version`、`capability_id`、`total`、`results`、`warnings`。每个 result 必须包含 `article_id`；K1 追加 chunk/location，K3 追加 term/relation/evidence provenance。`article_ids` 缺省为全库，显式 `[]` 返回 `invalid_arguments`，不能静默放宽为全库。
