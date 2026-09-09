# L0–L3 渐进式能力路由与按需 Wiki 检索

日期：2026-08-11
作者 / Agent：Codex（doc-driven 流程）
状态：Implemented
关联对话 / 任务：分析 LLM Wiki 搜索是否应每轮调用，并要求对 Wiki、Skill、MCP 采用 L0/L1/L2/L3 分级信息披露
关联系统文档：`docs/system/current-architecture.md`、`docs/system/product-rules.md`、`docs/system/data-model.md`、`docs/system/api-inventory.md`、`docs/system/known-pitfalls.md`、`docs/system/local-model-evaluation.md`

## 1. 原始需求

用户希望确认 NoteMeld 提供给 LLM 的 Wiki 搜索是否需要每轮调用，并提出：

> “是否可以向上抽离一层进行总结目前有哪些相关的内容，一段话描述，让 AI 决定是否调用这个搜索呢？来提升 AI 优化空间。包括 skill，mcp 这些工具也是一样的处理方式。采用 L0, L1, L2, L3 分级提取信息的方式。”

随后用户要求使用 `doc-driven` 将该想法写为正式需求，并继续完成 Plan、Spec、实现与验证。

## 2. 背景和问题

- 当前用户是谁：使用 NoteMeld 会话助手检索个人 Wiki、调用本地 Skill 或第三方 MCP 工具的个人研究者。
- 当前场景是什么：用户在 free-chat 会话中发送普通聊天、知识问题、来源核验、笔记操作或工具任务；Agent 需要判断是否读取个人知识或调用工具。
- 当前痛点是什么：
  1. 前端固定发送 `use_wiki=true`，free-chat 默认意图通常是 `mixed`，导致大多数请求在首次 LLM 调用前执行完整 Wiki 搜索。
  2. 当前 Wiki 搜索按查询遍历 contribution 与 materialized Markdown；真实本地样本约有 561 个概念页、183 个实体页、27 个来源页和 27 份 contribution。只读基准中，常驻进程平均约 206ms/次；无关问题也可能返回结果并占用上下文。
  3. Agent 每轮把已注册工具的完整名称、描述和 JSON Schema 交给模型；Skill 数量增长后会持续占用提示词并干扰工具选择。
  4. 第三方 MCP client 已能发现工具，但尚未接入 Agent 运行时；若直接把所有远端工具平铺给模型，会产生网络发现、生命周期和上下文膨胀问题。
  5. 一段总览可以减少噪声，但仅靠一段话无法覆盖长尾实体和概念，可能使模型漏掉实际存在的个人知识。
- 为什么现在要做：P3 Agent 已接入 workspace、memory、Skill 和长任务；继续平铺能力会让上下文成本随知识量和工具量增长，并阻塞后续 MCP 与深入学习能力扩展。

## 3. 目标结果

- 目标 1：普通聊天或已有上下文足够时，不读取 Wiki 正文、不执行完整 Wiki 搜索；模型仍能从一个短小、可更新的能力总览知道个人 Wiki 和工具大致覆盖什么。
- 目标 2：当问题涉及个人知识、来源、证据、跨笔记比较或命中已知主题时，模型可以逐级发现候选能力、查看选中能力契约，并最终按需执行搜索或工具。
- 目标 3：Wiki、内建工具、Skill 和第三方 MCP 使用同一套 L0–L3 语义，避免为每类能力重复设计路由协议。
- 目标 4：保留 `use_wiki`、现有 Chat API/SSE、来源展示、长任务卡片、feature flag 回退和本地安全边界。
- 目标 5：工具数量和 Wiki 规模增长时，首轮提示词只包含固定数量的渐进式入口，而不是全部工具 schema 或 Wiki 正文。

## 4. 非目标

- 不做：替换 `WikiSearch` 的关键词排序算法、接入 embedding、query rewrite 或 LLM reranker；检索质量优化属于独立需求。
- 不做：修改 Wiki contribution、entity、concept、relation、graph.json 的持久化结构。
- 不做：修改 MCP `/mcp` 服务端对外的 `tools/list` / `tools/call` 协议；本次只处理 NoteMeld 内部 Agent 作为 MCP client 的能力披露。
- 不做：新增数据库表或字段。
- 不做：新增前端页面、开关或可视化；沿用现有 `use_wiki` 和来源列表。
- 不做：让无工具调用能力的模型自动获得工具执行能力。
- 不做：移除 legacy chat 路径或 `AGENT_CHAT_ENABLED` 回退。

## 5. 当前系统事实

- 已有类似能力：
  - `backend/app/services/query_intent.py` 已有规则式 scope/intent 分类，但默认 scope 为 `mixed`。
  - `backend/app/agent/builtin_tools.py` 已有 `search_knowledge`，可搜索关联笔记与 Wiki。
  - `backend/app/agent/skill_loader.py` 已能把每个 `SKILL.md` 转成 `AgentTool`。
  - `backend/app/agent/mcp_client.py` 已能按 enabled 配置发现第三方 MCP 工具并转成 `AgentTool`，且要求调用方关闭 adapter。
  - `backend/app/agent/core/loop.py` 每轮把 `state.tools` 全部转换为 OpenAI function schema。
- 当前入口 / 页面 / API：
  - `POST /api/chat/free`、`POST /api/chat/free/stream`。
  - 前端 `ChatComposer` 固定发送 `use_wiki: true`。
  - Agent 路径由 `AGENT_CHAT_ENABLED` 控制。
- 当前数据来源和写入位置：
  - Wiki：`note_results/wiki/graph.json`、`contributions/`、`sources/`、`entities/`、`concepts/`。
  - Skill：`note_results/skills/**/SKILL.md`。
  - MCP 配置：`note_results/settings/mcp_servers.json`，只有 `enabled=true` 的 server 可用。
- 当前限制：
  - `_prepare_free_chat_context()` 在 LLM 前执行 WikiSearch；Agent hooks 复用该行为。
  - `run_free_chat*` 当前直接注册 workspace、memory 和所有 Skill 工具。
  - free-chat 尚未接入第三方 MCP 工具。
  - SSE done 的 `sources` 来自 hooks 构建时的静态检索结果；工具调用后的 Wiki 来源尚无动态汇入路径。
- 相关 known pitfalls：
  - MCP 路径穿越和 API Key 泄露。
  - API response wrapper 兼容。
  - 慢 LLM / I/O 不得放入 Wiki 全局写锁。
  - Agent 新需求必须基于当前事实并保留 feature flag 回退。

## 6. 用户故事

- 作为普通聊天用户，我希望问候、改写、头脑风暴等请求不自动扫描整个个人 Wiki，以便更快得到干净回答。
- 作为研究者，我希望模型知道 Wiki 大致包含哪些领域，并在问题确实相关时主动搜索，以便保留 Wiki-First Retrieval 的价值。
- 作为长尾知识使用者，我希望问题命中一个具体实体或概念时，系统能给模型轻量候选提示，而不是因为总览没列出该词就永久漏检。
- 作为 Skill 使用者，我希望模型先看到 Skill 的一句话能力，再按需读取参数并执行，以便避免把所有 schema 塞进每一轮上下文。
- 作为 MCP 使用者，我希望未使用 MCP 时不连接第三方 server；需要时才发现并调用已启用工具，且连接在请求结束后关闭。
- 作为 NoteMeld 用户，我希望工具搜索产生的 Wiki 结果仍出现在来源列表中，便于验证和追溯。

## 7. 验收标准

1. GIVEN `AGENT_CHAT_ENABLED=true` 且 `use_wiki=true`，WHEN 用户发送不涉及个人知识的普通聊天，THEN 首次 LLM 调用前不执行 `WikiSearch.search()`，system prompt 不包含 Wiki 正文片段。
2. GIVEN Wiki 有可用 graph，WHEN构建任意 free-chat 首轮上下文，THEN system prompt 包含一个有字符上限的 L0 能力总览，至少说明 Wiki 节点/主题规模、Skill 数量、已启用 MCP server 数量和 L0–L3 使用规则。
3. GIVEN 用户问题包含 graph 中的具体实体或概念名称，WHEN构建 L0 总览，THEN总览包含有限数量的匹配候选名称，但不读取候选 Markdown 正文。
4. GIVEN 模型只需要判断有哪些能力，WHEN调用 L1 发现入口，THEN返回有限数量的 capability id、类型、名称和一句话摘要，不返回完整 JSON Schema、Wiki 正文或敏感 MCP 配置。
5. GIVEN 模型选中了一个 capability，WHEN调用 L2 描述入口，THEN只返回所选 capability 的输入契约、执行模式和必要说明；未选中能力的 schema 不进入上下文。
6. GIVEN 模型调用 L3 执行入口并选择 Wiki 搜索，WHEN搜索成功，THEN复用现有 `WikiSearch` 返回有来源标识的结果，并把结果追加到 `/api/chat/free*` 的 `sources` 输出。
7. GIVEN 本地存在多个 Skill，WHEN构建首次 LLM 调用，THEN模型只收到固定的渐进式入口 schema；Skill 完整 schema 只在 L2 描述选中 Skill 后出现，Skill 仍可在 L3 正常执行。
8. GIVEN存在 enabled 第三方 MCP server，WHEN只构建 L0 或调用普通 L1 发现，THEN系统不连接 MCP server；WHEN L2 描述该 server 或 L3 调用其工具，THEN才执行工具发现，并在请求结束后关闭 adapter。
9. GIVEN `use_wiki=false`，WHEN进行 free-chat，THEN L0、L1、L2、L3 均不暴露或执行 Wiki 能力，现有 note/asset/workspace/memory 能力继续可用。
10. GIVEN `AGENT_CHAT_ENABLED=false`，WHEN调用现有 Chat API，THEN legacy 行为和请求/响应结构保持兼容。
11. WHEN渐进式能力发现、描述或执行失败，THEN错误以 `ToolResult.is_error=true` 返回，不中断整个 Agent 循环、不泄露 auth/header/url/token。
12. WHEN运行新增契约测试、现有 Agent 测试、MCP 安全测试和前端 contract/build，THEN全部通过，且验证证据写入 `docs/superpowers/tests/`。

## 8. 输入 / 输出样例

### 输入

- 普通聊天：`你好，帮我润色这句话。`
- Wiki 问题：`我的知识库里 RAG 和 Agent 的边界是什么？请给来源。`
- Skill 请求：`把这个视频编译成结构化笔记。`
- MCP 请求：`看看已启用的 MCP 里有没有能查询项目 Issue 的能力。`

### 输出

- L0 示例：`个人 Wiki：771 个节点、24 个主题社区，主要涉及 AI Agent、RAG/知识库、产品与工作流；本轮命中候选：RAG、Agent。可用本地 Skill 2 个；已启用 MCP server 1 个。普通聊天无需检索；涉及个人知识、证据或候选主题时按 L1→L2→L3 使用能力。`
- L1 示例：`[{"id":"wiki:search","kind":"wiki","name":"搜索个人 Wiki","summary":"搜索实体、概念、观点、证据和关系"}]`
- L2 示例：`{"id":"wiki:search","input_schema":{"query":"string","limit":"integer"},"execution_mode":"parallel"}`
- L3 示例：`{"capability_id":"wiki:search","arguments":{"query":"RAG Agent 边界","limit":6}}`

### 反例或失败样例

- `你好` 自动返回 8 条 Wiki 来源：失败，因为无关聊天不应进行重型搜索。
- L0 把 700 多个实体/概念名称全部列给模型：失败，因为这等价于全量平铺。
- L1 返回 MCP auth、command 环境变量或远端 URL：失败，属于敏感配置泄露。
- `use_wiki=false` 仍可通过通用 L3 入口调用 `wiki:search`：失败，开关必须在注册和执行两层生效。

## 9. 约束

- 平台 / 设备：保持 Python 3.11+、源码、CLI、Tauri sidecar 和浏览器运行方式兼容。
- 性能 / 耗时：L0 构建和长尾候选匹配只允许读取本地轻量索引并按文件版本缓存；不得读取全部 Wiki Markdown。缓存命中时目标耗时小于 50ms，首次读取 graph 的目标耗时小于 150ms。
- 隐私 / 安全：不得输出 Provider API Key、MCP auth/header/env、用户文件路径或原始敏感 payload；只发现 enabled MCP server。
- 兼容性：不修改 `/api/chat/free*` 请求字段和 response wrapper；SSE `delta/done/error/task_card/task_card_progress` 语义保持兼容；`use_wiki` 继续为 bool。
- 成本：L0 和 L1 不新增 LLM 调用；MCP 未被选中时不产生网络或子进程连接。
- 时间：本次交付最小闭环，不同时改进 Wiki 排序质量。
- 第三方依赖 / License：不新增第三方依赖；复用标准库和现有 MCP/Wiki 实现。

## 10. 边界场景

- 空数据：Wiki graph 不存在或为空时，L0 显示“个人 Wiki 当前为空”，发现/执行 Wiki 搜索返回空结果，不报 500。
- 权限拒绝：MCP server 未启用时不进入目录；请求已缓存但随后被禁用时，执行返回不可用错误。
- 网络失败：MCP tools/list 或 tools/call 超时，返回 error ToolResult，并关闭已经创建的 transport。
- 任务中断：Agent/SSE 被取消时，向 Skill/MCP 执行传递 AbortSignal；请求结束时关闭 adapter。
- 旧数据兼容：不迁移 graph、contribution、Skill 或 MCP 配置；损坏 graph 降级为空摘要并记录 warning。
- 大数据量：L0 主题和 query hints 都有固定数量与字符上限；L1/L2 返回数量有上限；Wiki 正文只在 L3 读取。
- 工具重名：capability id 必须包含 kind/server namespace，避免 Skill、内建工具和不同 MCP server 重名。
- 模型不调用工具：允许直接回答，但 system prompt 必须明确要求涉及个人知识或来源时调用能力且不得伪造来源。

## 11. 开放问题

无阻塞问题。

本次采用以下明确假设：以“不漏掉明确命中的个人知识”为优先，因此每轮可以执行不读取正文的本地目录候选匹配；只有 LLM 决定后才执行完整 Wiki 搜索、Skill 或 MCP 调用。

## 12. 与系统事实的冲突检查

- 是否和 `product-rules.md` 冲突：不冲突。仍是 Wiki-First Retrieval；改变的是检索时机，不是取消结构化 Wiki。来源和证据继续可追溯。
- 是否和 `data-model.md` 字段语义冲突：不冲突。不新增表、字段、状态或持久化文件。
- 是否和 `api-inventory.md` 接口语义冲突：请求和响应字段不变；Agent 内部工具集合与 `use_wiki=true` 的执行语义变化，需要同步记录。
- 是否会重新引入 `known-pitfalls.md` 中的问题：不会。只读目录不进入 Wiki 写锁；MCP 配置脱敏；错误通过 ToolResult 降级；feature flag 保留。
- 是否影响本地数据或线上服务：只读本地 Wiki/Skill/MCP 配置；无线上服务和数据迁移。L3 MCP 仍可能访问用户明确启用的第三方 server。
- 是否影响用户已确认交互：用户可见 API/UI 不变；来源列表由“预搜来源”变为“实际被调用的检索来源”。

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是。
- 推荐下一步：
  - [x] 使用 Superpowers 生成 `docs/superpowers/plans/2026-08-11-progressive-capability-routing.md`
  - [x] 使用 Superpowers 生成 `docs/superpowers/specs/2026-08-11-progressive-capability-routing.md`
  - [x] 按 Spec 进行 TDD 实现和验证
- 计划必须覆盖的验收标准：第 1–12 条全部覆盖，尤其是 no-search、L0 字符上限、L1/L2 信息边界、动态 sources、MCP lazy discovery/close 和 `use_wiki=false` 双重门禁。
- 计划必须补充的验证：新增路由决策测试集，至少包含普通聊天、已有上下文、个人知识、来源核验、长尾实体、Skill、MCP、Wiki 关闭八类用例。
