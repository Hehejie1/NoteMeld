# notemeld-agent：研究助手 Agent（技能强化、长任务、工作空间、三层记忆、接管现有 Chat）

日期：2026-08-01
作者 / Agent：doc-driven 流程
状态：Ready for Plan
关联对话 / 任务：Pi 框架分析 → 分层架构确认 → P2-P3 研究助手基础+强化
关联系统文档：`docs/system/current-architecture.md`、`docs/system/data-model.md`、`docs/system/product-rules.md`、`docs/system/api-inventory.md`、`docs/system/known-pitfalls.md`、[P0 notemeld-ai](2026-08-01-notemeld-ai-llm-abstraction.md)、[P1 notemeld-agent-core](2026-08-01-notemeld-agent-core-runtime.md)

## 1. 原始需求

> "这个与用户进行对话的 agent 封装在 notemeld-agent 里面。"
>
> 功能 1：强化 Skill 工具。现有 skill 标准（skill.md + 脚本调用）基础上新增：
>   - Parameter Collector：长任务技能（如 compile_source）缺参数时，触发前端弹窗让用户输入（例如视频链接）
>   - Agent 在对话中检测到视频链接时，**先询问用户**是否调用 compile_source；长任务期间用户可随时取消
>   - 长任务 = 先占位展示任务卡片 + 状态 + 单独卡片进度通道，不阻塞当前 turn，不影响最终输出；完成后默认自动 follow-up（用户可在设置关闭）
>   - Sub-Agent = 必须等结果出来后再继续 turn（和长任务明确区分）
>
> 功能 2：工作空间。每次对话一个独立目录；Agent 完全读写权限，外部只读。
>
> 功能 3：三层记忆。参考 Trae 结构：
>   - 全局用户记忆（user_profile 级，跨所有研究方向）
>   - 研究空间记忆（project_memory 级，每个研究方向的硬约束、工程约定、已学概念）
>   - 会话记忆（session 级，当前对话的消息）
>   - 存储：先 JSON 文件，后续迁 SQLite
>
> 功能 4：基础能力。MCP 适配器、内建工具、**直接接管现有 chat**，做出来就是替换原有一套。
>
> 前端入口：现有会话界面增强，保持单一入口。
>
> 技术路线：依赖 P0 notemeld-ai + P1 notemeld-agent-core，仓库内模块 `backend/app/agent/`（不含 core，core 是子目录 core/）。

## 2. 背景和问题

- **当前用户是谁**：NoteMeld 终端用户（研究某个方向、需要 AI 辅助编译知识 + 深入学习的个人）
- **当前场景是什么**：用户在会话界面发送视频链接、问题或研究方向；现有 `/api/chat/ask` 和 `/api/chat/free/stream` 只能做简单 Q&A + 笔记 RAG；没有长任务、没有工作空间、没有跨会话记忆
- **当前痛点是什么**：
  1. 现有 Skill（`trae/skills/notemeld-model-recommender` 等）只定义了 skill.md + 脚本，运行时不是 Agent 的一等公民；Agent 无法在对话中按需发现、收集参数、触发 Skill
  2. 生成笔记（compile_source）的动作当前要用户手动跳转到首页表单；在对话里粘贴链接不能一键触发；且编译是 2-3 分钟的长任务，用户等不及就关页面
  3. 对话上下文 = 暴力 `history[-20:]`，之前聊过的同一个研究方向内容（跨会话）完全带不进来；"深入学习"做不到持续积累
  4. 没有工作空间：搜索结果、临时文件、画布 JSON、工具中间产物无统一存放地；跨工具共享数据靠临时变量
  5. MCP 当前只能接外部 Agent（Trae、Claude Code）调用 NoteMeld 的能力；NoteMeld 自己的研究助手 Agent 不能作为 MCP client 去调第三方 MCP server
- **为什么现在要做**：P4 知识看板和深入学习流程依赖强基础能力（长任务、记忆、工作空间）；现在不做，后面看板就只剩空壳 UI

## 3. 目标结果

- **目标 1（Skill 强化）**：统一 Skill Loader。读 `SKILL.md`（或未来 `skills/registry.json`）注册成 Agent 工具；长任务 Skill 支持 Parameter Collector、占位卡片、独立 SSE 进度、自动 follow-up（默认开启，设置可关）；Sub-Agent 与长任务明确区分实现路径
- **目标 2（接管现有 Chat）**：替换 `/api/chat/ask`、`/api/chat/free`、`/api/chat/free/stream` 三个接口的实现；旧的 `chat_service.chat()` / `free_chat()` / `free_chat_stream()` 内部重定向到 notemeld-agent；对外 API request/response 结构 100% 不变，前端不改就能跑；会话界面增强后新功能靠 SSE 新增事件类型扩展
- **目标 3（工作空间）**：每个 conversation_id 对应独立目录 `<data_dir>/note_results/workspaces/{cid}/`（下分子目录 assets/skills/canvases/memory/scratch）；Agent 通过内建工具 `workspace_list/read/write` 访问（路径穿越校验）；前端新增只读接口 `/api/conversations/{cid}/workspace/*`
- **目标 4（三层记忆）**：JSON 文件存储（后期迁 SQLite），对应 Trae 结构：
  - `user_profile.json`：全局偏好、默认模型/样式、技术栈、UI 偏好、全局已学通用概念
  - `research_spaces/{rs_id}.json`：每个研究空间 = 一个研究方向；存该方向的硬约束、工程约定、该领域 mastery 表、关注论文/作者
  - 会话记忆：复用 conversation_messages（DB 已有），不重复存 JSON
  - 注入时机：每轮对话通过 `transform_context` 注入 user_profile + 当前 research_space 摘要到 system prompt 前缀
- **目标 5（基础能力）**：
  - MCP 工具适配器：把第三方 MCP server（HTTP/SSE/stdio，配置化注册）的 tools 转换为 AgentTool 注册
  - 内建工具：`compile_source`（调 System A）、`get_compile_status`、`search_knowledge`（Wiki + 笔记）、`read_note`、`read_transcript`、`manage_research_space`、`update_user_profile`、`workspace_*`

## 4. 非目标

- 不做：知识看板、画布数据结构、build_knowledge_canvas 流程（属于 P4 独立需求）
- 不做：Web 搜索工具（属于 P4 search_web 抽象层 + 默认 Tavily/SearXNG）
- 不做：前端画布渲染组件（P4）
- 不做：独立抽包 pip 发布
- 不做：移动端 / 多租户云服务
- 不做：前端聊天消息组件完全重写（增强现有组件，兼容旧消息类型映射）
- 不做：桌面端新增 Node.js 运行时或其他 sidecar

## 5. 当前系统事实

- 已有类似能力：
  - Skill 体系：`.trae/skills/` 下有 Trae Skill 规范示例（notemeld-model-recommender、notemeld-dmg-packaging 等），但用于 Trae 平台，NoteMeld 自身运行时无法加载
  - 工作空间雏形：`note_results/` 存任务结果，`uploads/` 存上传文件，但未按 conversation 隔离
  - 记忆雏形：`user_profile.md` / `project_memory.md` 存在于 Trae memory 目录（用户本地 IDE），NoteMeld 应用本身没有读这些文件
  - 聊天：`/api/chat/ask`、`/api/chat/free`、`/api/chat/free/stream`；conversation_messages 表
- 当前入口 / 页面 / API：HomePage（笔记生成表单）、WorkSpace（会话 + 笔记列表）、Wiki 页、Settings 页；Chat 路由位于 `backend/app/routers/chat.py`；Conversation 路由位于 `backend/app/routers/conversation.py`
- 当前数据来源和写入位置：notemeld.db（conversations / conversation_messages / providers / models / model_usage_records / note_documents）；note_results/ 文件；uploads/ 文件；static/ 文件
- 当前限制：
  - conversation 没有 research_space 归属字段
  - `linked_task_id` 是单任务关联，不是多任务/研究空间维度
  - Skill 没有在 NoteMeld 后端内的标准注册机制
- 相关 known pitfalls：
  - 任务状态与会话消息不同步的教训：长任务卡片状态必须通过 `conversation_messages`（新增 message_type=task_card / task_card_progress）持久化，否则刷新页面前后不一致
  - 路径穿越：工作空间的 `/api/conversations/{cid}/workspace/*` 必须校验 `..` 和绝对路径，参考 MCP get_note 的安全实现
  - API Key 不泄露：MCP 适配器调第三方 server 时，第三方 auth 单独存用户配置，不在日志里打 headers

## 6. 用户故事

- 作为研究一个方向的用户，我在对话里粘贴 "https://www.bilibili.com/video/BV1xx"，WHEN Agent 检测到视频链接后询问 "我识别到一个 B 站视频，要帮你编译成笔记吗？[是 / 否]"，我点"是"，THEN 对话里立即插入一张 "视频编译中（0%）" 卡片，Agent 回复其他内容不被阻塞；2 分钟后卡片自动变"完成"并弹出摘要，我可以点开看完整笔记

- 作为跨会话研究 NeRF 的用户，我第一次会话聊完 NeRF 基础，第二次再开新会话问 "上次讨论的 NeRF 和 3DGS 对比总结一下"，THEN Agent 从 research_space 记忆里拿到上一次的摘要、已掌握概念、重点内容，不用我重新发上下文

- 作为想接入第三方 MCP 的用户，我在 Settings → MCP 里新增一个本地 server `stdio: path/to/server.py`，WHEN 保存后进入会话，THEN 该 server 提供的 tools 自动出现在 Agent 可用工具里；Agent 调用该 tool 和调用内建 compile_source 行为一致（有 tool_execution_start/end 事件）

- 作为偏好安静的用户，我在 Settings 里把"长任务完成后主动总结"关闭，THEN compile_source 完成后只更新卡片状态到 SUCCESS，Agent 不主动说话，我什么时候点开卡片什么时候看

## 7. 验收标准

1. GIVEN 旧前端代码（不修改）直接连 P2 完成后的后端，WHEN 调用 `/api/chat/free`、`/api/chat/free/stream`、`/api/chat/ask`，THEN 响应 wrapper、字段名、SSE 事件（delta/done/error）和迁移前逐字节一致；新增的 task_card / parameter_request 事件以**新增 SSE type** 形式出现，旧前端不处理即忽略（不 crash）

2. GIVEN 用户在会话中发 "我想了解 3DGS"，WHEN 这个会话没有绑定 research_space，THEN Agent 自动创建一个 research_space "3DGS 研究"并询问用户确认（Parameter Collector 式的确认卡片，非弹窗阻塞），确认后后续对话自动归属；记忆写入 `research_spaces/{rs_id}.json`

3. GIVEN compile_source 长任务启动后，WHEN 刷新页面，THEN 重新打开会话，卡片仍在原位置并展示最新状态（不是 "未开始"）；且通过独立接口 `/api/task_status/{task_id}` 和卡片内展示的状态字段一致

4. WHEN compile_source 长任务执行中用户点击卡片上的"取消"按钮，THEN 后端在 1 秒内收到 cancel 请求，NoteGenerator 走已有的 `is_note_task_canceled` 语义提前返回 CANCELED；卡片状态变 CANCELED；usage 里写一条 status=canceled

5. GIVEN conversation_id=c1 的工作空间里 Agent 写了 scratch/a.json，WHEN 前端访问 `/api/conversations/c1/workspace/scratch/a.json`，THEN 返回文件内容；WHEN 尝试访问 `/api/conversations/c1/workspace/../../../notemeld.db` 或 `/api/conversations/c1/workspace/scratch/../../notemeld.db`，THEN 返回 403 + 不读文件

6. GIVEN 用户在 Settings 关闭了长任务自动 follow-up，WHEN compile_source 长任务完成，THEN 只更新卡片状态 + 写 conversation_messages 一条 task_card 消息；不产生新的 assistant 文本消息（不 follow-up）

## 8. 输入 / 输出样例

### 输入（SSE 流新增事件类型示例）

```
// 旧前端已经在处理的
data: {"type": "delta", "content": "你好"}
data: {"type": "done", "answer": "你好...", "sources": []}

// P2 新增的，旧前端收到不认识即忽略
data: {"type": "parameter_request", "request_id": "pr-123", "skill": "compile_source", "fields": [{"key": "url", "label": "视频链接", "widget": "text_input", "required": true}]}
data: {"type": "task_card", "card_id": "card-1", "kind": "compile_source", "task_id": "task-abc", "status": "PENDING", "title": "视频编译中", "progress": null}
data: {"type": "task_card_progress", "card_id": "card-1", "status": "DOWNLOADING", "progress": 30, "details": "下载音频：1.2MB/5.8MB"}
```

Parameter Collector 的响应（前端填完后，发给后端的 steering 消息格式）：

```json
{
  "role": "user",
  "message_type": "parameter_response",
  "request_id": "pr-123",
  "params": {"url": "https://bilibili.com/video/BV1xx"}
}
```

### 输出（研究空间记忆 JSON 样例：research_spaces/rs-3dgs.json）

```json
{
  "id": "rs-3dgs",
  "name": "3D Gaussian Splatting 研究",
  "version": 1,
  "hard_constraints": [
    "对比实验必须在 MipNeRF360 数据集上跑",
    "PSNR 指标用官方评估脚本"
  ],
  "engineering_conventions": [
    "视频按 3fps 截帧",
    "长任务卡片命名格式 job-时间戳"
  ],
  "masteries": {
    "Gaussian 椭球参数化": {"status": "known", "first_seen": "2026-07-15", "sources_count": 2},
    "Splats 光栅化原理": {"status": "learning", "last_reviewed": "2026-07-28"}
  },
  "focuses": [
    {"topic": "3DGS vs NeRF 速度对比", "priority": "high", "created_at": "2026-07-20"}
  ],
  "linked_conversations": ["conv-1", "conv-5", "conv-12"],
  "linked_note_task_ids": ["task-abc", "task-def"]
}
```

### 反例或失败样例

- compile_source 长任务中，后端进程挂了 → 重启后从 `note_results/{task_id}.status.json` 恢复卡片状态到 FAILED / CANCELED，不显示"运行中"的假状态
- Parameter Collector 多次收到同一个 request_id 的 response → 只生效第一次，后续返回幂等成功（不重复触发 execute）
- research_space JSON 损坏（非法 JSON）→ 加载时容错：空 JSON 默认 + 记录日志 + 备份损坏文件，不清空用户数据

## 9. 约束

- **平台 / 设备**：Python 3.11+；桌面 + 源码；浏览器前端增强（SSE 支持）
- **性能 / 耗时**：Skill 加载（一次加载 20 个 Skill ≤ 100ms）；长任务 follow-up 产生的新 turn 不阻塞卡片状态先更新（先写卡片 + SSE，再异步跑 LLM）
- **隐私 / 安全**：
  - 工作空间上传/写入不允许 `..` / 绝对路径 / 符号链接逃逸
  - MCP 第三方 server 执行外部命令的风险在 Settings 明确提示；默认关闭，用户手动 opt-in
  - research_spaces/*.json 和 user_profile.json 不移入 Git；.gitignore 已包含数据根目录（按 NOTEMELD_DATA_DIR 规则）
- **兼容性**：
  - `/api/chat/*` 三接口 100% 向后兼容；旧前端不改可用
  - conversation_messages 的 role/message_type 字段枚举值新增时，旧 `message_type` 值保留映射
  - 迁移完成后，旧 chat_service.chat / free_chat 内部 redirect 到 Agent 实现，保留 DeprecationWarning 至少一个 Beta 版本
- **成本**：零新增付费依赖；MCP server 由用户自行配置；内建工具不产生外部费用
- **时间**：P2（基础能力 + 接管 chat）先交付；P3（长任务 Skill + 工作空间 + 三层记忆 + MCP 适配器）再交付；P0/P1 必须先稳定
- **第三方依赖 / License**：MCP 协议实现可引入官方 `mcp` Python SDK（MIT 协议）；其余用项目已有依赖

## 10. 边界场景

- **空数据**：新会话（0 条消息）发起时工作空间目录按需懒创建（等第一次 write 时建，不是会话创建时建）
- **权限拒绝**：MCP tool 被用户在 Settings 禁用 → Agent 的 tool 列表不包含它；如果 LLM 仍尝试调（由于缓存 context），notemeld-agent-core 返回 tool not found 错误，循环继续
- **网络失败**：MCP 调远端 server 超时 → 工具层捕获 → 返回 isError=True 的 toolResult，不中断整个对话
- **任务中断**：长任务卡片取消（compile_source）→ 复用现有 `cancel_note_task` 语义；Sub-Agent 取消时由 notemeld-agent-core.abort 传递到下层 agent
- **旧数据兼容**：没有 research_space 的历史会话，首次进入时默认不创建（用户显式触发 "归入研究空间..." 才建）；旧 conversation_messages 不做 migration
- **大数据量**：research_space.masteries > 1000 条时，注入 system prompt 前截断 Top-20（按 priority + last_reviewed 排序），不全量灌
- **其他**：Parameter Collector 弹出后用户长时间不响应 → 300s 超时自动发拒绝消息的 steering（超时可配置），避免对话永久挂起

## 11. 开放问题

无。所有阻塞项已在对话中确认：
1. 记忆存储：先 JSON 再 SQLite ✅
2. 长任务默认自动 follow-up（可设置关）✅
3. 自主编译前先询问用户 + 长任务可取消 ✅
4. 画布简单编辑留到 P4，P2-P3 不做 ✅
5. search_web 抽象层留到 P4 ✅

## 12. 与系统事实的冲突检查

- **是否和 product-rules.md 冲突**：
  - 本地优先 ✅
  - API Key 不回显 ✅（MCP auth 单独存）
  - 保留源码启动 + CLI + 桌面 + MCP + 迁移 + Wiki + 导出 ✅（P2 明确承诺旧 chat 接口兼容 + run_notemeld.sh 入口不变）
  - 长任务可恢复、进度可见 ✅（验收 3）
- **是否和 data-model.md 字段语义冲突**：
  - 新增 conversation_messages.message_type 值（task_card/task_card_progress/parameter_request/parameter_response）→ 不改变现有字段语义，只是新增枚举值 ✅
  - conversation 增加 research_space_id 可选字段 → 先存 conversation.meta_json（现有字段），不新增表列，下一期再迁独立列 ✅
  - 不破坏 task_id 主键关联 ✅（compile_source 还是调 System A，task_id 体系不动）
- **是否和 api-inventory.md 接口语义冲突**：
  - 新增 `/api/conversations/{cid}/workspace/*` 只读接口 → 文档要加
  - chat 三接口结构不变 ✅
  - MCP `/mcp` endpoint 不变 ✅
- **是否会重新引入 known-pitfalls.md 中的问题**：
  - 路径穿越：验收 5 已覆盖工作空间接口
  - 状态与会话不同步：验收 3 要求卡片写入 conversation_messages；不绕过 `append_message` 统一 writer
  - API Key 泄露：MCP auth 不打日志；setting 展示时脱敏
- **是否影响本地数据或线上服务**：新增工作空间目录、记忆 JSON 目录；DB 仅追加写 conversation_messages；无破坏性变更
- **是否影响用户已确认交互**：会话界面增强但单一入口不变；新增卡片/弹窗为增强不是重写

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是
- 推荐下一步（P0/P1 稳定后按顺序）：
  - [ ] 使用 Superpowers 生成 `docs/superpowers/plans/2026-08-01-notemeld-agent-research-assistant.md`（拆 P2 基础 / P3 强化两份 Plan 也可以）
  - [ ] 使用 Superpowers 生成 `docs/superpowers/specs/2026-08-01-notemeld-agent-research-assistant.md`
  - [ ] 先 P2（接管 chat + 基础工具 + 接口兼容）交付用户尝鲜，再 P3
- 计划必须覆盖的验收标准：第 1（chat 接口兼容）、3（卡片刷新不丢状态）、4（取消 compile_source）、5（工作空间路径穿越）、6（follow-up 开关）条
- 计划必须补充的验证：
  - 回归：现有 `backend/tests/test_core_mcp_generation_tools.py` / `test_core_task_status_contracts.py` / 前端 `pnpm test:contracts` 必须全绿
  - 端到端：一次完整"粘贴视频链接 → 询问确认 → 占位卡片 → 后台编译 System A → 30s 后进度更新 → 结束 follow-up 摘要"的人工验收脚本或契约测试
