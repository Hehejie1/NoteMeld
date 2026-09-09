# K0-K3 文章级分层知识检索与独立 Agent 工具

日期：2026-08-18
作者 / Agent：Codex（doc-driven）
状态：Planned（Requirement / Plan / Execution Spec 已完成，尚未开发）
关联对话 / 任务：用户确认四层知识结构、全层 `article_id` 约束、四个工具相互独立并由 Agent 自主组合
关联系统文档：`docs/system/current-architecture.md`、`docs/system/product-rules.md`、`docs/system/data-model.md`、`docs/system/api-inventory.md`、`docs/system/known-pitfalls.md`
关联目标架构：`docs/superpowers/specs/2026-08-17-agent-sdk-single-runtime-architecture.md`
前置需求：`docs/requirements/2026-08-17-agent-sdk-single-runtime-cutover.md`
扩展需求：`docs/requirements/2026-08-11-progressive-capability-routing.md`

## 1. 原始需求

用户明确要求：

> 所有笔记按四层组织：原始文档、原文证据块、高密文档画像、实体/概念/关系。

> 四层结构都必须带文章 ID，以便先按文章范围筛选，再在原文证据和文档画像中匹配。

> 四个工具相互分离，不限制 Agent 必须先调用 K3、再调用 K2；Agent 可以自主关联和组合。

> 结合 Agent SDK 单一运行时最新架构，先完整形成需求、计划和执行 Spec，不写代码；后续可以严格按 Plan/Spec 实现并测试。

本需求将知识数据层命名为 `K0-K3`，避免与 Agent SDK 的 Capability Router `L0-L3` 信息披露层混淆。

## 2. 背景和问题

- 当前用户是谁：需要在大量 NoteMeld 笔记中查询事实、比较观点、追溯来源和调用 Agent 工具的研究者；目标规模按单机约 10 万篇文章设计。
- 当前场景是什么：用户可能直接指定文章，也可能提出宽泛主题、精确证据、页码定位、实体关系或跨文章比较问题；Agent 应根据问题自主选择一个或多个知识工具。
- 当前痛点是什么：
  - 当前 Chroma 以 `task_id` 为 collection 名，每篇文章一个 collection；适合单篇检索，不适合 10 万篇全库召回。
  - 当前 `WikiSearch` 遍历 contribution JSON 和 materialized Markdown；规模增长后查询成本随文件数线性增加。
  - ingestion chunk 已有 `page_number` 和 anchor，但现有向量查询只按 `source_type` 配额检索，没有统一的文章集合、页码、章节和时间范围过滤协议。
  - Wiki contribution 已有 summary、entity、concept、claim、evidence 和 relation，但摘要未形成独立的全局文档画像索引，图谱主要以 `graph.json` 作为 materialized snapshot。
  - 当前 Agent 工具有 `task_id`、`linked_task_id`、Wiki page id 等不同定位字段，跨工具组合缺少统一主键和结果信封。
  - 旧渐进式能力需求解决的是“何时披露/调用能力”，没有解决 10 万篇知识数据如何分层索引、混合召回和按文章过滤。
- 为什么现在要做：P6 Agent SDK 单一运行时已经明确 SDK 只负责通用 Agent 行为，NoteMeld Knowledge Services 负责产品知识能力。此时需要在切换前固定知识工具和数据契约，避免把旧 Python WikiSearch 或 per-task Chroma 结构直接固化进新 Host Driver。

## 3. 目标结果

1. 建立四层知识模型：K0 文档事实源、K1 原文证据块、K2 高密文档画像、K3 实体/概念/关系语义网络。
2. 四层每条记录、命中或 provenance 都必须直接携带或可靠追溯到统一 `article_id`；对外 `article_id` 的值直接复用现有 `task_id`，不新增第二套文章主键。
3. K1、K2 和 K3 检索均支持可选 `article_ids` 先过滤再匹配；K0 支持按 `article_id` 精确读取和有界定位。
4. 提供四个独立 Knowledge Capability：`article_lookup`、`evidence_search`、`profile_search`、`semantic_search`。任何工具都没有其他知识工具调用成功这一前置条件。
5. Agent 可以独立、串行、并行调用四个工具，也可以把任一工具返回的 `article_id` 传给另一个工具；系统只施加参数、权限、资源和取消边界。
6. 对 10 万篇文章使用共享、版本化索引和增量重建，不通过遍历 10 万个 collection 或 10 万份 Wiki 文件执行在线查询。
7. 所有回答证据保留文章、页码/章节/时间、evidence、节点和关系 provenance，能够进入 Agent 的可验证来源输出。
8. 新能力遵循 P6 目标架构：产品知识逻辑只存在于 NoteMeld Knowledge Services/Driver Adapter，SDK 只消费通用 CapabilityManifest 和 ToolResult。

## 4. 非目标

- 不把 K0-K3 业务模型、SQLite 表名、Chroma collection 名或 Wiki 文件结构写进 `notemeld-agent-sdk`。
- 不新增第二套 Agent loop、知识工具调度器或强制的 K3→K2→K1 调用工作流。
- 不在本阶段引入 Neo4j、云向量数据库或多租户云服务。
- 不在本阶段实现团队账号、ACL 管理 UI 或跨设备同步；索引协议保留 `workspace_id/access_scope` 扩展位，但不改变当前本地优先产品边界。
- 不删除旧 Note、Wiki contribution、materialized pages、`graph.json`、历史 per-task Chroma collection 或迁移数据。
- 不让完整 Wiki rebuild 同步阻塞笔记保存。
- 不要求每个问题都调用知识工具；普通聊天和已有上下文足够的问题允许 Agent 直接回答。
- 不在本需求中新增独立的公共 HTTP 搜索 API 或改变 MCP `/mcp` 协议；首个交付面向 Agent Host 内部 Capability Provider。

## 5. 当前系统事实

- `note_documents.task_id` 是笔记、任务结果、conversation、Wiki source 和文件的现有核心关联键；本需求对外称为 `article_id`，值保持一致。
- K0 现有事实源包括 SQLite `note_documents.content`、`note_results/{task_id}.json` 和 `note_results/{task_id}_markdown.md`。
- `backend/app/services/vector_store.py` 当前按 `task_id` 创建 Chroma collection；Markdown 按 H2/H3、transcript 按时间窗口、ingestion 文档按 chunk 索引。
- `backend/app/services/ingestion/chunker.py` 已把 `page_number`、`chunk_index`、anchor 和 parser 信息写入 KnowledgeChunk metadata。
- `backend/app/models/knowledge_packet.py` 和 Wiki contribution 已包含 summary、topics、entities、concepts、claims、evidence 和 relations。
- `backend/app/services/vector_store.py` 已存在全局 `wiki_terms` collection，`WikiSemanticResolver` 已用它做实体/概念语义归并；它不是面向文章范围过滤的 K3 occurrence 检索索引。
- `backend/app/services/wiki_search.py` 当前执行文件遍历和词频计分，不是 BM25 + vector 的持久混合索引。
- `backend/app/agent/capability_catalog.py` 已实现旧 Python L0-L3 capability registry；P6 目标架构要求最终由 SDK 统一 Capability Router/Tool Scheduler，NoteMeld Host 只提供 manifest 和 invoke adapter。
- `backend/app/agent_host/drivers/tools.py` 当前是现有 registry 的薄适配器；P6 尚未完成正式 ToolDriver/capability provider 切换。
- 迁移导入后必须重建索引，不能只复制文件；Wiki rebuild 必须可取消并保持 latest-wins；Note 保存成功后索引/Wiki 后处理失败不得回滚正文。

## 6. 用户故事

- 作为研究者，我希望先按来源、时间或已选文章圈定范围，再搜索摘要或原文，以便减少无关结果。
- 作为精确问答用户，我希望直接在指定文章和页码中搜索证据，不必先调用实体图或文档画像。
- 作为主题研究用户，我希望先搜索 10 万篇文章的高密画像，再把候选 `article_id` 交给原文检索，以便快速获得可引用证据。
- 作为关系研究用户，我希望独立搜索实体、概念和关系，并看到每个节点/关系来自哪些文章和 evidence。
- 作为 Agent 用户，我希望模型可以并行调用 profile 与 semantic 工具，也可以直接调用任意单个工具，而不会被固定流程阻断。
- 作为现有用户，我希望升级和重建索引不会删除历史笔记，也不会让索引失败冒充笔记生成失败。
- 作为开发者，我希望四个工具具有统一参数、返回值、错误和取消语义，以便 SDK、UI、CLI 和后续 MCP adapter 复用同一产品能力。

## 7. 验收标准

1. GIVEN 任意现有 Note，WHEN它进入 K0-K3 任一索引或关系存储，THEN每条记录或 provenance 都能解析到唯一 `article_id`，且该值等于现有 `task_id`。
2. GIVEN K1/K2 中存在多篇文章，WHEN调用方传入非空 `article_ids`，THEN系统先把候选限制在这些文章内再执行向量匹配，返回结果不得包含集合外文章。
3. GIVEN K3 节点被多篇文章共享，WHEN读取节点或关系，THEN canonical 节点不被按文章重复创建，节点/边 provenance 返回对应 `article_id` 和 `evidence_id`。
4. GIVEN K3 检索传入 `article_ids`，WHEN执行 BM25、vector 或图扩展，THEN lexical/vector occurrence 和 relation provenance 均限制在指定文章集合内。
5. GIVEN 未提供 `article_ids`，WHEN调用 K1、K2 或 K3，THEN工具可以执行全库检索；显式空数组必须返回参数错误，不能被解释为全库。
6. GIVEN四个 Knowledge Capability 已注册，WHEN Agent 只描述并调用其中任意一个，THEN执行不依赖本 Turn 是否调用过其他三个工具。
7. GIVEN Agent 同时调用 `profile_search` 和 `semantic_search`，WHEN SDK Tool Scheduler 允许并行，THEN两个工具可并行完成，结果按 SDK 的稳定 call 顺序回填，不共享可变的调用前置状态。
8. GIVEN任一工具返回候选，WHEN Agent 把其中的 `article_id` 传给另一个工具，THEN第二个工具按统一字段完成过滤，不需要转换为 page id、source id 或 collection name。
9. GIVEN同一 embedding 模型和索引版本，WHEN索引 10 万篇文章，THEN K1/K2/K3 分别使用固定数量的共享版本化 collection，不创建 10 万个文章 collection。
10. GIVEN 10 万篇 benchmark corpus，WHEN执行全局 K2、限定 50 篇的 K1、限定文章的 K3 一跳查询，THEN在线路径不遍历所有 contribution/Markdown 文件或所有 collection。
11. GIVEN推荐基准机为 8 核 CPU、32GB RAM、NVMe、warm index、单请求者，WHEN运行 top_k≤20 的基准，THEN目标 P95 为 K0≤100ms、K2≤300ms、限定文章 K1≤500ms、K3 BM25/vector + 1 hop≤500ms；未达标时不得宣称 10 万篇验收通过。
12. GIVEN Wiki contribution 已产生 summary，WHEN构建 K2，THEN复用该高密摘要而不额外强制调用 LLM；source-only partial 时生成可追溯降级画像并标记状态。
13. GIVEN Note 正文保存成功而任一索引写入失败，WHEN任务结束，THEN Note 保持成功，索引记录为可重试失败，不诱导用户重复创建 Note。
14. GIVEN迁移导入、embedding/index version 变化或索引缺失，WHEN触发 reindex，THEN使用可取消、可续跑、幂等 job 增量重建，并保留旧数据直至新 generation 可查询。
15. GIVEN文章被软删除或删除任务 artifacts，WHEN索引清理执行，THEN K1/K2 occurrence 和 K3 provenance 不再返回该文章；共享 K3 节点只有在没有其他来源时才可清理。
16. GIVEN `use_wiki=false`，WHEN构建 Agent capability allowlist，THEN K2/K3 全局 Wiki 能力不可发现和执行；显式关联文章的既有 Note K0/K1 行为按 Product Policy 保持兼容，不能通过缓存绕过边界。
17. GIVEN SDK 单一运行时切换完成，WHEN模型发现、描述和调用四个工具，THEN SDK 只处理通用 manifest/schema/scheduling，所有 K0-K3 查询和数据访问都经过 NoteMeld Tool Driver。
18. WHEN执行指定后端契约、迁移、Agent Host、前端契约、核心回归与 10 万篇 benchmark，THEN结果写入对应 test evidence 文档，失败项不得标记 Implemented。

## 8. 输入 / 输出样例

### 输入：直接证据搜索

```json
{
  "query": "如何避免把所有资料一次性塞给模型",
  "article_ids": ["task-001", "task-002"],
  "location": {"page_from": 3, "page_to": 10},
  "top_k": 10
}
```

### 输入：全局文档画像搜索

```json
{
  "query": "Agent 自主选择检索工具",
  "filters": {"source_types": ["web", "upload"]},
  "top_k": 20
}
```

### 输入：限定文章语义关系搜索

```json
{
  "query": "RAG 与 Agent 的关系",
  "article_ids": ["task-001", "task-002"],
  "node_types": ["entity", "concept"],
  "relation_types": ["depends_on", "contrasts_with"],
  "hops": 1,
  "top_k": 20
}
```

### 统一结果示例

```json
{
  "schema_version": "knowledge_result.v1",
  "capability_id": "knowledge:evidence_search",
  "total": 1,
  "results": [
    {
      "layer": "K1",
      "article_id": "task-001",
      "result_id": "task-001_chunk_12",
      "title": "Agentic RAG",
      "text": "匹配证据片段",
      "location": {"page_number": 8, "section_path": "第三章", "chunk_index": 12},
      "scores": {"vector": 0.86, "bm25": null, "graph": null},
      "source_ref": {"evidence_id": "task-001:evidence:3"}
    }
  ]
}
```

### 允许的调用组合

- `article_lookup`
- `evidence_search`
- `profile_search → evidence_search`
- `semantic_search → evidence_search`
- `profile_search || semantic_search`
- `semantic_search → profile_search → article_lookup`

### 反例或失败样例

- K1 命中只返回 Chroma collection 名，不返回 `article_id`：失败。
- K3 节点返回关系但无法定位来源文章/evidence：失败。
- `evidence_search` 因本 Turn 没有先调用 `profile_search` 而拒绝：失败。
- `semantic_search` 返回空后，系统强制禁止 Agent 调用 K1/K2：失败。
- `article_ids=[]` 被静默解释为全库：失败。
- K2 在线查询逐个读取 10 万份 contribution JSON：失败。
- 为了新索引删除旧 Note、Wiki 或历史 collection：失败。

## 9. 约束

- 平台 / 设备：保持源码、Tauri sidecar、Web、CLI、macOS Apple Silicon/Intel、Windows 打包入口；SQLite/FTS 和 Chroma 能力必须进入打包契约测试。
- 性能 / 耗时：在线查询必须走索引；每个工具有 top_k、article_ids、正文字符和图 hop 上限；benchmark 与 CI 功能测试分离。
- 隐私 / 安全：结果不得包含 Provider Key、MCP credential、Cookie、绝对用户路径或原始敏感 payload；后续 ACL 必须在召回前过滤而非回答后遮盖。
- 兼容性：`article_id` 是 `task_id` 的工具层语义名，不修改现有 task/status/file/Wiki source 主键；旧数据可重建，旧 collection 不在迁移前删除。
- 成本：K2 优先复用 Wiki extraction summary；索引更新不得为每次查询新增 LLM 调用。
- 并发：索引写入必须幂等并有 generation/version；查询不得持有 Wiki 全局写锁；重建可取消且 latest-wins。
- 第三方依赖 / License：第一版复用 SQLite FTS5 和现有 Chroma，不新增图数据库或新运行时依赖。
- 架构：SDK 不知道 K0-K3；四个工具通过 NoteMeld capability provider 注册到 SDK 的通用 L0-L3 Router。

## 10. 边界场景

- 空数据：四个工具返回成功空集合或明确 `index_unavailable`，不得 500 或伪造来源。
- 无效 ID：不存在、已删除或跨权限的 `article_id` 返回安全错误；不得泄露文章是否存在于其他数据域。
- 显式空集合：`article_ids=[]` 返回 `invalid_arguments`；字段缺省才表示全库。
- 位置差异：PDF 用 page，Markdown 用 section/chunk，视频用 start/end time；不适用字段为 null，不伪造页码。
- K3 共享节点：删除一篇文章只移除 provenance；仍被其他文章引用的节点和边保留。
- 画像缺失：Wiki partial/failed 时可使用 title、headings 和有界正文生成 deterministic fallback，状态标记 partial。
- embedding 变化：不同 dimension/model/version 不写入同一 collection generation；新索引成功前旧 generation 可读。
- 索引损坏：查询 fail-closed 到 `index_unavailable` 或显式 legacy single-article fallback，不执行全文件扫描兜底。
- Agent 不调用工具：允许；涉及个人知识和来源却直接回答时不得生成虚假 NoteMeld 来源。
- 工具取消：取消传播到向量、FTS、图扩展和结果组装的安全点；已完成的只读结果可丢弃，不产生副作用。
- 超大关系图：单次最多 2 hops，节点/边/来源数量有硬上限；不把全图送入模型。
- 迁移导入：导入成功与索引完成是不同状态；索引失败保留可重试 job。

## 11. 开放问题

无阻塞问题。

本 Requirement 采用以下已确认决策：

- 对外 `article_id` 直接复用现有 `task_id` 的值。
- K0-K3 是知识数据层；SDK L0-L3 是能力披露层，两者不合并命名。
- 四个知识工具没有知识层调用顺序约束；SDK 通用的 discover/describe/invoke 和 Product Policy 仍然适用。
- K3 逻辑上统一实体、概念和关系，物理上使用 occurrence 混合索引加 SQLite provenance/adjacency，不引入专用图数据库。

## 12. 与系统事实的冲突检查

- 是否和 `product-rules.md` 冲突：不冲突。继续采用 Wiki-First Retrieval、来源可追溯、本地优先和按需检索；四工具独立不等于无边界执行。
- 是否和 `data-model.md` 字段语义冲突：不修改 `task_id`；新增索引/图关系表和版本状态需要在实现时同步 data-model，并保留历史数据可读。
- 是否和 `api-inventory.md` 接口语义冲突：第一版不新增公共 HTTP API；Agent capability manifest 和内部 ToolResult 契约需要在实现时记录。若后续暴露 HTTP/MCP，另写增量接口 Spec。
- 是否会重新引入 `known-pitfalls.md` 中的问题：Plan/Spec 明确覆盖迁移后 reindex、Note 成功边界、Wiki latest-wins、固定 tmp、写锁、API/事件脱敏、上下文预算和 Agent SDK 版本漂移。
- 是否影响本地数据或线上服务：新增本地索引和 SQLite 表；不新增远端持久服务。embedding/LLM Provider 仍按用户配置调用。
- 是否影响用户已确认交互：不改变页面操作；实际检索来源继续进入统一 sources/event projection。
- 是否影响 P6 单一运行时：作为 P6 Knowledge Services 增量；不修改 SDK 产品边界，也不恢复旧 Python Agent 核心。

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是，且 Plan/Execution Spec 已生成，状态为 Planned。
- 实施计划：`docs/superpowers/plans/2026-08-18-k0-k3-article-knowledge-retrieval.md`。
- 执行规格：`docs/superpowers/specs/2026-08-18-k0-k3-article-knowledge-retrieval-execution.md`。
- 计划必须覆盖的验收标准：第 1-18 条全部覆盖。
- 计划必须补充的验证：小型确定性检索集、四工具独立/并行排列、迁移/取消/删除、Agent Host manifest、打包 FTS、10 万篇离线 benchmark 和 test evidence。
- 执行顺序：Knowledge Services/索引可与 P6 SDK 强化并行；Agent Host manifest 接入依赖 P6 Capability/Tool Driver 正式路径。

## 14. Requirement Quality Gate

- [x] 保留用户原始意图与关键原话。
- [x] 写清用户、场景、痛点和业务价值。
- [x] 目标是可观察产品结果，实施细节进入 Plan/Spec。
- [x] 明确非目标和架构边界。
- [x] 当前事实来自代码、系统文档、P6 架构和用户确认。
- [x] 验收标准可验证，覆盖正常、失败、边界和规模场景。
- [x] 已检查产品规则、数据模型、API、known pitfalls 和 P6 冲突。
- [x] 无密钥、token、隐私路径或用户原始素材。
- [x] 无阻塞开放问题，可进入执行计划。
