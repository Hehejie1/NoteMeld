# NoteMeld 主动学习空间 V1 Spec

日期：2026-08-11（2026-08-12 交互增量）
状态：Approved for execution（用户已要求 doc-driven 创建并执行）
Canonical requirement：[`docs/requirements/2026-08-01-notemeld-agent-deep-learning-canvas.md`](../../requirements/2026-08-01-notemeld-agent-deep-learning-canvas.md)
Implementation plan：[`docs/superpowers/plans/2026-08-11-notemeld-active-learning-space.md`](../plans/2026-08-11-notemeld-active-learning-space.md)

## 1. 目标与交付边界

V1 交付一个会话内可持续恢复的 Learning Space：从本地 Wiki/笔记建立初始画布，默认补充 arXiv 与 GitHub 来源，并在配置可用时补充通用 Web，生成有依赖的学习路径，并通过 recall/apply/review 证据更新掌握状态。

V1 使用一个 Agent 的阶段化角色：

1. researcher：本地检索、外部候选、来源归一化；
2. curriculum：节点、前置关系、路径与重点；
3. tutor：短讲解、回忆题、应用题；
4. examiner：rubric 评测、掌握状态和复习队列。

不实现多 Agent 运行时、Agent 权限、Agent 间消息或组织工作台。

## 2. 文件结构

### 后端新增

- `backend/app/models/learning_canvas.py`：唯一领域 schema。
- `backend/app/services/learning_canvas_store.py`：会话 canvas 文件读写、版本与并发控制。
- `backend/app/services/research_search_config.py`：搜索配置与凭证脱敏。
- `backend/app/services/research_search.py`：Web/arXiv/GitHub provider 与聚合器。
- `backend/app/services/learning_canvas_service.py`：本地优先画布生成与路径构建。
- `backend/app/services/learning_session_service.py`：学习单元、证据、掌握状态与复习。
- `backend/app/routers/learning.py`：Learning Space API。
- `backend/app/agent/learning_tools.py`：AgentTool 适配。
- `backend/tests/learning/`：领域、搜索、服务、API 契约测试。

### 前端新增

- `frontend/src/services/learning.ts`：类型与 API。
- `frontend/src/pages/HomePage/components/LearningCanvasCard.tsx`：富媒体消息容器。
- `frontend/src/pages/HomePage/components/LearningCanvasGraph.tsx`：Sigma 图谱适配。
- `frontend/src/pages/SettingPage/ResearchSearch.tsx`：搜索配置。
- `frontend/tests/learningCanvasContracts.test.mjs`：源代码契约。

### 复用且只做最小修改

- `backend/app/services/wiki_search.py`、`backend/app/agent/builtin_tools.py`：复用现有本地检索，不改变 Wiki materialize。
- `backend/app/agent/workspace.py`：仅修正原子写唯一临时文件。
- `backend/app/agent/agent_service.py`：只在 Agent free-chat 路径注册 learning tools。
- `frontend/src/pages/WikiPage/graph/SigmaWikiGraph.tsx`：保持通用组件；Learning graph 只做输入适配。
- `frontend/src/pages/HomePage/messageRenderers.tsx`：新增一种 renderer，不重写现有消息。

## 3. 数据契约

### 3.1 LearningSource

```json
{
  "id": "arxiv:2608.01234",
  "source_type": "academic",
  "provider": "arxiv",
  "title": "Paper title",
  "url": "https://arxiv.org/abs/2608.01234",
  "snippet": "Abstract...",
  "published_at": "2026-08-01T00:00:00Z",
  "authors": ["A", "B"],
  "repository": null,
  "default_branch": null,
  "stars": null,
  "license": null,
  "version": "v1",
  "local_task_id": null,
  "compile_status": "candidate"
}
```

`source_type`：`local_wiki | local_note | web | academic | github`。

`compile_status`：`local | candidate | selected | compiling | compiled | failed | canceled`。外部 discovery 结果只能从 `candidate` 开始；未经用户动作不得进入 `selected`。

### 3.2 LearningNode

```json
{
  "id": "concept:speculative-decoding",
  "label": "推测解码",
  "type": "concept",
  "summary": "用草稿模型提出候选 token，再由目标模型并行验证。",
  "priority": "high",
  "mastery": "unknown",
  "status": "ready",
  "prerequisites": ["concept:autoregressive-decoding"],
  "source_ids": ["wiki:task-1", "arxiv:2211.17192"],
  "mastery_evidence": [],
  "next_review_at": null,
  "user_label": null,
  "user_summary": null
}
```

`mastery`：`unknown → exposed → learning → provisional → mastered`。

禁止转换：

- `exposed → provisional/mastered`；
- 没有 learner answer 的 LLM 自评推动任何状态；
- review 未到期时用同一次即时答案直接进入 mastered。

### 3.3 MasteryEvidence

```json
{
  "id": "ev_...",
  "kind": "recall",
  "created_at": "2026-08-11T12:00:00Z",
  "answer_summary": "用户能解释草稿模型与验证模型职责",
  "rubric_version": "learning-rubric-v1",
  "score": 0.82,
  "passed": true,
  "feedback": "缺少接受率对收益的影响",
  "model_name": "configured-model",
  "provider_id": "configured-provider"
}
```

`kind`：`exposed | recall | explain | apply | transfer | review`。

原始答案保存在 canvas 的 `sessions[].attempts[]` 中，不写日志，不复制到全局 user profile。

### 3.4 LearningCanvas

```json
{
  "version": 1,
  "canvas_id": "lc_...",
  "conversation_id": "conv_...",
  "research_space_id": "rs_...",
  "goal": "真正掌握推测解码并能判断工程适用性",
  "status": "active",
  "diagnostic_status": "pending",
  "nodes": [],
  "edges": [],
  "clusters": [],
  "path": [],
  "sessions": [],
  "review_queue": [],
  "external_errors": [],
  "created_at": "...",
  "updated_at": "..."
}
```

文件路径：`<note_output_dir>/workspaces/{conversation_id}/canvases/{canvas_id}.json`。

写入规则：验证 `conversation_id/canvas_id` 安全字符；同一 canvas 进程内串行写；使用 `NamedTemporaryFile(dir=target.parent, delete=False)` 后 `replace()`；失败保留原文件。

## 4. 多源研究

### 4.1 配置

路径：`<data_root>/config/research_search.json`。

```json
{
  "web_provider": "searxng",
  "searxng_endpoint": "http://127.0.0.1:8888",
  "tavily_api_key": "...",
  "github_token": "...",
  "timeout_seconds": 15
}
```

`academic` 与 `github` 是领域层强制的基线 scope，不再存储或暴露开关。`web` 只有在 `web_provider=searxng` 且 endpoint 非空，或 `web_provider=tavily` 且 key 已配置时自动加入。旧配置中的 `enabled_scopes` 可以继续读取但不得关闭基线来源。GET API 返回 `tavily_api_key_set/github_token_set` 布尔值，不返回实际值。PUT 中空字符串表示保持原密钥，显式 `clear_*: true` 才删除。

### 4.2 Provider 行为

- Tavily：`POST https://api.tavily.com/search`，结果归一化为 `web`。
- SearXNG：`GET {endpoint}/search?format=json&q=...`，只允许配置的 endpoint；请求超时明确返回 `provider_down`。
- arXiv：`GET https://export.arxiv.org/api/query`，解析 Atom `id/title/summary/published/updated/author`，source_type=`academic`。
- GitHub：`GET https://api.github.com/search/repositories`，归一化 `full_name/html_url/description/stargazers_count/license/default_branch/updated_at`，source_type=`github`；token 可选。

所有 provider：timeout 5-30 秒；limit 1-20；错误只记录 provider/code/safe message，不记录 headers、token 或完整 payload。

## 5. 本地优先画布构建

`LearningCanvasService.create_canvas()` 顺序固定：

1. `WikiSearch.search(goal, limit=20)`；
2. 读取匹配 contribution 的 concept/entity/claim/evidence/relation；
3. 生成 local nodes/edges/sources；
4. 标记 gap：`covered | weak_evidence | missing`；
5. 每次创建都调用 academic 与 GitHub provider；Web provider 配置可用时自动加入；旧调用方传入 scopes 只能追加、不能移除基线来源；
6. 外部来源只作为 candidate/source node，不自动写入 Wiki；
7. 生成 prerequisites 和 topological path；环存在时打破最低置信 edge，并写 `path_warnings`；
8. 保存 canvas；
9. append `conversation_messages.message_type=learning_canvas`，meta 仅含 `canvas_id/goal/status/node_count/current_node_id`。

LLM enrichment 是可选步骤：输出必须通过 `LearningCanvas` schema，且 node 的 `source_ids` 必须指向输入 source。失败则用 deterministic fallback，不让整个创建失败。

## 6. 学习状态机

### 6.1 start unit

- 将选中 node 标为 current；
- 创建 session 与 `exposed` evidence；
- 返回 explanation、recall question、application question；
- mastery 从 unknown 变 exposed，不能更高。

### 6.2 submit evidence

- recall/explain 通过任一种 + apply/transfer 通过任一种：进入 provisional；
- 任一关键证据失败：保持/回到 learning；
- provisional 时创建 `next_review_at = now + 48h`；
- 到期 review 通过：进入 mastered；失败：回到 learning，并将下一复习时间设为 `now + 24h`。

评分阈值默认 `0.7`。用户可纠正评分；纠正会新增 `kind=override` 审计项，不覆盖旧证据。V1 UI 暂不暴露 override，后端 schema 预留。

### 6.3 Research Space 写回

只在 provisional/mastered 时调用现有 `MemoryManager.save_research_space()` 更新对应 subject；写回失败不回滚 canvas，而是在 `external_errors` 添加 `memory_sync_failed`，下次加载可重试。

## 7. HTTP API

所有响应使用 `ResponseWrapper`。

### 搜索配置

- `GET /api/research-search/config`
- `PUT /api/research-search/config`

### Learning Canvas

- `POST /api/conversations/{conversation_id}/learning-canvases`
  - body：`goal`, `external_scopes`, `external_limit`, `provider_id?`, `model_name?`
  - response：完整 canvas（V1 节点上限 100）。
- `GET /api/conversations/{conversation_id}/learning-canvases/{canvas_id}`
- `PATCH /api/conversations/{conversation_id}/learning-canvases/{canvas_id}`
  - 只允许 `goal`、node `user_label/user_summary`、selected source 状态。
- `POST .../{canvas_id}/sources/compile`
  - body：`source_ids[]`；只把明确选择的 candidate 交给现有 generate-note/compile-source 链路，每个返回独立 `task_id/card_id`。
- `POST .../{canvas_id}/units/{node_id}/start`
- `POST .../{canvas_id}/units/{node_id}/evidence`
  - body：`kind`, `answer`, `provider_id`, `model_name`。
- `GET .../{canvas_id}/reviews/due`

错误码：

- 400：非法 transition、空 goal、未选择 candidate；
- 403：路径越界；
- 404：conversation/canvas/node 不存在；
- 409：canvas version 冲突；
- 422：模型输出不可验证；
- 503：外部 provider 全失败且本地也无内容。

## 8. Agent tools

在 `run_free_chat*` 且存在 conversation_id 时注册：

- `build_learning_canvas(goal, external_scopes, external_limit)`；
- `read_learning_canvas(canvas_id)`；
- `start_learning_unit(canvas_id, node_id)`；
- `submit_learning_evidence(canvas_id, node_id, kind, answer)`。

System prompt 增加硬规则：不能仅凭对话语气、已阅读或已讲解调用 mastery 晋级；外部 source compilation 前必须得到 parameter response 或明确 API selection。

## 9. 前端交互

### 9.1 显式学习入口

- `ComposerMode = chat | note | learn` 只存在于输入组件；`learn` 创建或复用的持久会话仍为 `mode=chat`，不改 SQLite 和会话 API 枚举。
- 用户主动选择 `learn` 后，文本输入和 URL 识别不得自动覆盖该选择；切换到其他标签才退出。
- 提交时先保存 user message，再调用 `POST /conversations/{cid}/learning-canvases`。创建 API 自身追加一条 `learning_canvas` 摘要消息；前端随后重载会话并导航到该会话。
- 学习创建不依赖 Agent 是否在 L0-L3 中自行选择 `build_learning_canvas`，因此 `AGENT_CHAT_ENABLED=false` 时显式学习入口仍可用。

### 9.2 对话摘要与右侧面板

- `learning_canvas` 在对话流中渲染为精简摘要，不再内嵌完整图谱。摘要来自持久消息 `content/meta`，至少包含目标、节点数、来源类型、推荐起点和“从右侧开始学习”的引导。
- `HomePage` 从当前会话最后一条有效 `learning_canvas` 消息读取 `canvas_id`。存在时，纯 chat 页面升级为左右分栏，右侧渲染 `LearningCanvasCard`。
- 新 canvas 出现时自动展开右侧并选择学习视图。若会话还有已生成笔记，右侧标题栏提供“学习 / 笔记”切换；两者互不覆盖。
- 移动端把“学习”加入内容 tab，不在窄屏同时渲染双栏。

`learning_canvas` 消息渲染：

- 摘要栏：目标、状态、节点数、当前进度；
- 诊断：pending 时显示“开始诊断/跳过诊断”；
- 重点：按 priority、mastery、prerequisite ready 排序；
- 画布：复用 Sigma；mastery 颜色映射 unknown 灰、exposed 蓝灰、learning 橙、provisional 紫、mastered 绿；
- 学习路径：前置未满足节点不可直接标完成，但允许用户查看；
- 当前单元：解释、隐藏资料后的回忆输入、应用输入、提交；
- 待复习：只显示 due item，不在后台发 LLM 请求；
- 来源：每个 node 展示 local/web/academic/github 标识与可打开 URL。

节点点击只做选择/深入/开始学习，不改变 mastery。label/summary 修改写 `user_label/user_summary`，不覆盖 AI 原始字段。

## 10. 兼容与回滚

- 不修改 Wiki `graph.json` 和 materialized 页面。
- 新 `learning_canvas` message type 对旧前端以 content 文本降级；当前前端显式新增 renderer。
- 不新增 SQLite 表；canvas/session/evidence 使用工作空间 JSON，Research Space 继续现有 JSON。
- `AGENT_CHAT_ENABLED=false` 时旧 chat path 完全不注册新工具。
- 禁用外部 scopes 后功能退化为本地学习空间。
- 回滚代码不会删除 `canvases/*.json`；未来版本仍可读 version=1。

## 11. 测试与验收

后端重点断言：

- unsafe path 被拒绝；并发写无固定 tmp 冲突；
- provider 单点失败保留其他结果；凭证不回显；
- local/arXiv/GitHub 元数据区分；
- deterministic fallback 在 LLM 失败时仍生成可追溯 canvas；
- 拓扑路径满足 prerequisites；
- exposure 不晋级；recall+apply → provisional；到期 review → mastered；
- 重载 JSON 后 current unit/evidence/review queue 完整；
- `/api` wrapper 与错误语义；flag=false chat 回归。

前端重点断言：

- message type 和 API path 存在；
- mastery 标签/颜色完整；
- source link 与 academic/github metadata 可见；
- 不存在“阅读完成=掌握”的按钮或客户端状态更新；
- desktop ready gate 保留；
- TypeScript 与生产构建通过。

验证命令：

```bash
pytest backend/tests/learning backend/tests/agent/test_learning_tools.py -q
pytest backend/tests -q
cd frontend && pnpm test:contracts
cd frontend && pnpm build
scripts/run_core_regression.sh
```
