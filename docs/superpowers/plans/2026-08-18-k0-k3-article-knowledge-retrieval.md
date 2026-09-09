# K0-K3 文章级分层知识检索实施计划

日期：2026-08-18
状态：Planned（尚未执行）
Canonical Requirement：[`2026-08-18-k0-k3-article-knowledge-retrieval.md`](../../requirements/2026-08-18-k0-k3-article-knowledge-retrieval.md)
Execution Spec：[`2026-08-18-k0-k3-article-knowledge-retrieval-execution.md`](../specs/2026-08-18-k0-k3-article-knowledge-retrieval-execution.md)
架构依赖：[`2026-08-17-agent-sdk-single-runtime-architecture.md`](../specs/2026-08-17-agent-sdk-single-runtime-architecture.md)

## 1. 交付结果

本计划交付一个面向 P6 单一 Agent 运行时的 NoteMeld Knowledge Services 增量：

- K0 文档事实源、K1 原文证据、K2 文档画像、K3 实体/概念/关系四层数据契约。
- 全层统一 `article_id`，工具层值复用现有 `task_id`。
- K1/K2/K3 支持 `article_ids` 预过滤；K3 保存 node/edge 到文章和 evidence 的 provenance。
- 四个独立 capability：`knowledge:article_lookup`、`knowledge:evidence_search`、`knowledge:profile_search`、`knowledge:semantic_search`。
- 固定数量的共享版本化索引、SQLite FTS5/graph 表、可取消增量 reindex。
- SDK 只负责通用 capability/tool 调度；NoteMeld Host/Knowledge Services 负责所有产品查询。
- 可复现的功能测试、迁移测试、Agent 纵向测试和 10 万篇 benchmark evidence。

## 2. 依赖与执行边界

| 工作流 | 是否依赖 P6 完成 | 说明 |
| --- | --- | --- |
| K0-K3 数据契约、SQLite schema、共享索引 | 否 | 可先在 NoteMeld 后端实现和测试。 |
| 四个纯 Knowledge Service 工具 | 否 | 可直接做服务级契约测试，不接旧 Python Agent loop。 |
| CapabilityManifest 注册、ToolDriver invoke | 是 | 依赖 P6 SDK capability/tool 正式路径和进程级 Runtime。 |
| UI/CLI 纵向来源投影 | 是 | 依赖 P6 权威 event/projection 闭环。 |
| 删除旧 Python capability 执行路径 | 由 P6 负责 | 本需求不得重新引入旧 Agent 兼容分支。 |

实施期间不把四工具接到即将删除的第二套 Python Agent loop。若 P6 尚未到达 Host capability 接入任务，先完成服务、存储和独立工具测试，保持 capability integration pending。

## 3. 任务总览

| Task | 内容 | 依赖 | 主要验收标准 |
| --- | --- | --- | --- |
| 1 | 固定契约与 RED 测试基线 | 无 | AC 1-8、17 |
| 2 | 建立知识 schema、版本与 provenance | 1 | AC 1、3-4、13-15 |
| 3 | 实现 K0 article service | 2 | AC 1、5、8 |
| 4 | 迁移 K1 为共享证据索引 | 2 | AC 1-2、5、9-10 |
| 5 | 建立 K2 文档画像索引 | 2 | AC 1-2、5、9、12 |
| 6 | 建立 K3 occurrence 混合索引与图存储 | 2 | AC 1、3-5、9-10 |
| 7 | 实现四个独立查询服务与统一结果协议 | 3-6 | AC 2、4-8、16 |
| 8 | 增量 reindex、导入、删除和回滚 | 4-7 | AC 13-15 |
| 9 | 注册 P6 CapabilityManifest 与 ToolDriver | 7 + P6 capability path | AC 6-8、16-17 |
| 10 | Agent event/source 纵向闭环 | 9 + P6 projection | AC 7、17-18 |
| 11 | 10 万篇 benchmark 与调优 | 4-10 | AC 9-11、18 |
| 12 | 全量回归、系统文档和验证证据 | 1-11 | AC 18 |

## 4. Task 1：固定契约与 RED 测试基线

### 涉及文件

- 新增 `backend/app/models/knowledge_retrieval.py`。
- 新增 `backend/tests/knowledge/test_knowledge_contracts.py`。
- 新增 `backend/tests/knowledge/test_knowledge_tool_independence.py`。
- 新增 `backend/tests/knowledge/fixtures.py`。

### 执行

1. 定义纯 DTO：四个请求、统一结果信封、location、score、source_ref、K3 provenance。
2. 明确 `article_id` 的边界映射函数只做 `article_id <-> task_id` 同值校验，不生成新 ID。
3. 写 RED：缺省 `article_ids` 表示全库；显式空数组报错；最多 100 个；去重后保持稳定顺序。
4. 写 RED：四个工具可在空 invocation history 中分别调用，不读取 `prior_calls`。
5. 写 RED：K2/K3 并行调用不会共享可变筛选状态，ToolResult 顺序由 SDK scheduler 负责。
6. 写 RED：所有结果必须包含单个 `article_id` 或 K3 provenance 中至少一个 `article_id`。

### 完成条件

- DTO/schema snapshot 被测试固定。
- 不存在知识工具调用顺序字段，例如 `required_previous_layer`、`stage` 或 `prior_call`。
- AC 1-8 的失败契约先于实现存在。

## 5. Task 2：知识 schema、索引版本与 provenance

### 涉及文件

- 新增 `backend/app/db/models/knowledge.py`。
- 修改 `backend/app/db/models/__init__.py`。
- 修改 `backend/app/db/init_db.py`。
- 新增 `backend/app/db/knowledge_schema.py`。
- 新增 `backend/app/services/knowledge_repository.py`。
- 新增 `backend/tests/knowledge/test_knowledge_schema.py`。
- 新增 `backend/tests/knowledge/test_knowledge_repository.py`。

### 执行

1. 新增 canonical node、node source、canonical edge、edge source、article index state 五类表。
2. 对 provenance 建数据库唯一约束和 article/node/edge 查询索引。
3. 通过 `ensure_knowledge_schema()` 幂等创建 FTS5 occurrence 表和必要索引；重复启动不得删除已有行。
4. 启动时检查 FTS5/trigram 能力；缺失时记录可分类 `knowledge_fts_unavailable`，Agent Host 不得崩溃，K3 lexical 路径 fail-closed。
5. article index state 保存 K1/K2/K3 content hash、index generation、embedding version、状态和安全错误摘要。
6. 保持 `note_documents` schema 不变；repository 在边界把 `article_id` 映射到同值 `task_id`。

### 完成条件

- schema 初始化、重复初始化、legacy DB 升级和约束冲突测试通过。
- 删除一个 article provenance 不会误删仍有其他来源的 canonical node/edge。
- AC 1、3-4、13-15 有数据层防线。

## 6. Task 3：K0 文档事实源服务

### 涉及文件

- 新增 `backend/app/services/knowledge_article_service.py`。
- 复用 `backend/app/services/note_document_store.py`。
- 复用 `backend/app/services/ingestion/artifact_reader.py`。
- 新增 `backend/tests/knowledge/test_knowledge_article_service.py`。

### 执行

1. 按 `article_id` 读取 `note_documents` 和既有 NoteResult/Markdown，不接受任意路径。
2. 支持有界 `page_number/section_path/chunk_index/start_time/end_time` 定位；不适用字段返回 null。
3. `include_content=false` 只返回 metadata；`include_content=true` 受 `max_chars` 硬限制。
4. 不传 article_ids 时必须提供有界 metadata filter；禁止无条件倾倒全部 K0 正文。
5. 软删除、缺失、越权和损坏 sidecar 返回安全 typed error。

### 完成条件

- K0 不需要向量库即可精确读取。
- 任意返回都包含 article_id，不暴露本地绝对路径。

## 7. Task 4：K1 共享原文证据索引

### 涉及文件

- 修改 `backend/app/services/vector_store.py`。
- 修改 `backend/app/services/ingestion/chunker.py`。
- 修改 `backend/app/services/ingestion/materialization.py`。
- 新增 `backend/app/services/knowledge_evidence_index.py`。
- 新增 `backend/tests/knowledge/test_knowledge_evidence_index.py`。
- 更新 `backend/tests/test_core_ingestion_contracts.py`。

### 执行

1. 新建版本化共享 collection `note_chunks_v2`，不再以文章数增加 collection 数量。
2. 每条 record metadata 必含 article_id、chunk_id、source_type、chunk_index、content_hash；按来源选填 page/section/time/anchor。
3. `article_ids` 使用 metadata `$in` 在 ANN 前过滤；page range、source type 和其他位置条件组合为有界 where。
4. 旧 per-task collection 保留；新索引 dual-write 或 reindex 成功前不得删除旧 collection。
5. 新索引不可用时，只有明确单篇 article_id 才允许显式 legacy fallback；全库查询不得遍历旧 collections。
6. 写入按 article_id 幂等 replace/upsert，失败只更新 index state，不回滚 Note。

### 完成条件

- 过滤集合外零泄漏。
- collection 数与文章数解耦。
- page/section/time provenance 完整。

## 8. Task 5：K2 高密文档画像索引

### 涉及文件

- 修改 `backend/app/services/wiki_pipeline.py`。
- 修改 `backend/app/services/wiki_store.py`。
- 新增 `backend/app/services/knowledge_profile_index.py`。
- 新增 `backend/tests/knowledge/test_knowledge_profile_index.py`。
- 更新 `backend/tests/test_wiki_article_view_contracts.py`。

### 执行

1. 新建共享 collection `note_profiles_v1`，每篇文章当前 generation 最多一个 active profile record。
2. profile 文本由 title、high-density summary、topics、关键 claim 摘要组成；结构字段仍保存在 metadata/SQLite，不只保存拼接文本。
3. 正常 Wiki contribution 直接复用 `KnowledgePacket.summary`，不新增 LLM 调用。
4. source-only partial 使用 title、headings 和有界正文生成 deterministic fallback，并标记 `profile_status=partial`。
5. 支持 article_ids、source_types、时间、platform、status 等预过滤。
6. content hash 未变化时跳过 embedding；embedding version 变化时写新 generation。

### 完成条件

- K2 可独立全库召回并返回 article_id。
- Wiki 失败不导致 K2 永久缺失，也不把 partial 冒充完整画像。

## 9. Task 6：K3 occurrence 混合索引与图存储

### 涉及文件

- 修改 `backend/app/services/wiki_semantic_resolver.py`。
- 修改 `backend/app/services/wiki_store.py`。
- 新增 `backend/app/services/knowledge_semantic_index.py`。
- 新增 `backend/app/services/knowledge_graph_repository.py`。
- 修改 `backend/app/services/vector_store.py`。
- 新增 `backend/tests/knowledge/test_knowledge_semantic_index.py`。
- 新增 `backend/tests/knowledge/test_knowledge_graph_repository.py`。
- 更新 `backend/tests/test_wiki_semantic_incremental_merge.py`。

### 执行

1. 继续复用现有 semantic resolver 生成 canonical entity/concept，不按文章复制 canonical node。
2. 为每个 node/article/evidence mention 建 occurrence；FTS5 和 `knowledge_terms_v2` 都以 occurrence 为检索记录并携带 article_id。
3. BM25 与 vector 各自取有界候选，使用 RRF 融合；不直接比较 BM25 和 cosine 原始分数。
4. article_ids 过滤在 occurrence lexical/vector query 前执行；全库结果按 node_id 去重并聚合 provenance。
5. relation canonical edge 与 edge sources 分离；每条 edge source 必含 article_id，可选 evidence_id/confidence。
6. 图扩展只从已命中 seed nodes 出发，默认 1 hop、最大 2 hops，并受 node/edge/source 上限。
7. `graph.json` 继续作为 UI materialized projection，不作为大规模在线查询事实源。

### 完成条件

- 同一概念跨文章为一个 canonical node，但可返回所有受限来源。
- K3 article filter、BM25/vector fusion、1/2 hop 和删除 provenance 测试通过。

## 10. Task 7：四个独立查询服务和统一协议

### 涉及文件

- 新增 `backend/app/services/knowledge_query_service.py`。
- 新增 `backend/app/services/knowledge_capabilities.py`。
- 新增 `backend/tests/knowledge/test_knowledge_query_service.py`。
- 完成 `backend/tests/knowledge/test_knowledge_tool_independence.py`。

### 执行

1. 实现四个 capability handler，统一校验、超时、取消、错误映射和结果信封。
2. 工具之间不读取调用历史，不保存知识 stage；建议顺序只写 description，不成为 validation。
3. 所有工具支持独立调用；K2/K3 标记 `serial=false`，允许 SDK scheduler 并行。
4. result 统一包含 layer、article_id/provenance、result_id、title、text、location、scores、source_ref。
5. 对 article_ids、top_k、max_chars、hops 和返回总字节执行服务端硬上限。
6. Product Policy 根据 use_wiki/context refs 决定 allowlist，不让工具自行绕过权限。

### 完成条件

- 所有允许组合和反例均由契约测试覆盖。
- Agent 无需理解 task_id、Wiki page id 或 collection name。

## 11. Task 8：增量 reindex、导入、删除和回滚

### 涉及文件

- 修改 `backend/app/services/migration/reindex_service.py`。
- 修改 `backend/app/services/migration/import_service.py`。
- 修改 `backend/app/services/note_document_store.py`。
- 新增 `backend/app/services/knowledge_reindex_service.py`。
- 新增 `backend/tests/knowledge/test_knowledge_reindex_service.py`。
- 更新 `backend/tests/test_core_migration_contracts.py`。
- 更新 `backend/tests/test_core_migration_api_contracts.py`。

### 执行

1. reindex 按 article checkpoint，支持 pending/running/success/partial/failed/canceled 和 generation latest-wins。
2. 导入后默认排队 K1-K3 重建；导入成功与索引成功分别记录。
3. 新 generation 全部必要 collection/schema ready 后再原子切 active generation；失败保留旧 generation。
4. 软删除/删除 artifacts 同步标记索引 tombstone，再异步清理 Chroma occurrence 和 SQLite provenance。
5. 清理 orphan node/edge 前再次确认 source_count=0，避免并发删除误伤。
6. 回滚只停止新 capability/active generation，不删除新表和旧数据。

### 完成条件

- 中断续跑、重复触发、取消竞态、导入后自动重建、删除清理和回滚测试通过。

## 12. Task 9：P6 CapabilityManifest 与 ToolDriver 接入

### 依赖

P6 Plan 的 SDK capability integration 和 NoteMeld Host ToolDriver 正式路径已完成，不再使用旧 Python Agent loop。

### 涉及文件

- 修改 `backend/app/agent_host/drivers/tools.py`。
- 新增 `backend/app/agent_host/knowledge_provider.py`。
- 修改 P6 最终确定的 Host registry/runtime 组装文件。
- 新增 `backend/tests/agent_host/test_knowledge_capabilities.py`。
- 更新 `backend/tests/agent_host/test_tool_driver.py`。

### 执行

1. 注册四个 namespaced manifest；summary 明确独立调用和可选 article_ids。
2. L1 只返回 identity/summary；L2 返回单个选中 schema；L3 invoke 转到 knowledge capability handler。
3. SDK 不接收 collection/table/file path；Host context 只传递权限、session、linked article 和取消句柄。
4. `use_wiki=false` 在 manifest allowlist 和 invoke 双重门禁；旧缓存 identity 不能绕过。
5. ToolResult 的来源摘要进入 SDK event，完整有界结果回填模型；敏感内部错误不进入事件。

### 完成条件

- 四工具均可直接 discover/describe/invoke。
- 不存在 K 层调用顺序验证。
- SDK/Host 边界符合 P6 架构硬规则。

## 13. Task 10：Agent event/source 纵向闭环

### 涉及文件

- 修改 P6 最终 Conversation Projection/Event Adapter 文件。
- 更新 `frontend/src/services/agent.ts`，仅在最终事件 schema 需要兼容解析时修改。
- 新增 `backend/tests/agent_host/test_knowledge_source_projection.py`。
- 更新前端 Agent contract 测试。

### 执行

1. 将统一 result 中的 article/evidence/page/section/time provenance 投影为现有 sources 结构。
2. 同一 source/result 幂等去重；SSE replay 不重复来源。
3. UI/CLI 只消费 SDK 权威事件，不直接写 tool/source message。
4. 断线重连、取消、partial result 和工具并行保持 event sequence 与单终态。

### 完成条件

- UI、CLI 对同一 Turn 看到一致来源。
- 页面刷新和 SSE replay 后来源不丢失、不重复。

## 14. Task 11：10 万篇 benchmark 与调优

### 涉及文件

- 新增 `scripts/benchmark_knowledge_retrieval.py`。
- 新增 `backend/tests/knowledge/test_knowledge_scale_contracts.py`（小规模结构门禁，不在 CI 生成 10 万篇）。
- 未来写入 `docs/superpowers/tests/2026-08-18-k0-k3-article-knowledge-retrieval.md`。

### 执行

1. 生成可复现 corpus：10 万 profile、70 万至 150 万 chunk、可配置 K3 occurrence/edge。
2. 记录硬件、embedding dimension/version、collection count、磁盘、build time、峰值 RAM、P50/P95/P99。
3. 查询集覆盖 K0 exact、K2 global、K1 50-article filter、K3 lexical/vector、1 hop、空结果和取消。
4. 断言在线路径没有 glob contribution/Markdown、list all collections 或逐文章查询。
5. 如果 P95 未达 Requirement 目标，先调 batch、metadata filter、HNSW/FTS query、候选上限和 RRF，不通过扩大上下文掩盖召回问题。

### 完成条件

- benchmark JSON/摘要可复现并写入 evidence。
- 只有满足容量、延迟和正确性门槛才可标记 10 万篇通过。

## 15. Task 12：回归、文档和交接

### 涉及文档

- `docs/system/current-architecture.md`
- `docs/system/product-rules.md`
- `docs/system/data-model.md`
- `docs/system/api-inventory.md`
- `docs/system/known-pitfalls.md`
- `docs/system/changelog.md`
- `docs/requirements/index.md`
- `docs/superpowers/tests/2026-08-18-k0-k3-article-knowledge-retrieval.md`

### 验证命令

```bash
python3 -m compileall backend/app
PYTHONPATH=backend python3 -m pytest backend/tests/knowledge -q
PYTHONPATH=backend python3 -m pytest backend/tests/agent_host -q
PYTHONPATH=backend python3 -m pytest backend/tests/test_core_ingestion_contracts.py backend/tests/test_core_migration_contracts.py backend/tests/test_core_migration_api_contracts.py backend/tests/test_wiki_semantic_incremental_merge.py backend/tests/test_wiki_article_view_contracts.py -q
cd frontend && pnpm test:contracts
cd frontend && pnpm build
scripts/run_core_regression.sh
python3 scripts/benchmark_knowledge_retrieval.py --articles 100000 --output docs/superpowers/tests/artifacts/knowledge-retrieval-100k.json
```

### 完成条件

- Requirement AC 1-18 均映射到自动化或明确 benchmark 证据。
- 测试报告只记录命令、关键结果、指标和失败原因。
- 实现后的真实架构、数据、接口和新坑点同步写回 system 文档。

## 16. 风险与回滚

| 风险 | 触发信号 | 缓解/回滚 |
| --- | --- | --- |
| per-article collection 迁移导致旧检索中断 | v2 index 不完整或 active generation 错切 | 旧 collection 保留；新 generation ready 后才切换。 |
| K3 occurrence 数量膨胀 | 磁盘/构建时间超预算 | content hash 去重、只索引有效 entity/concept mention、批量写；保留 canonical/provenance。 |
| FTS5/trigram 打包缺失 | sidecar schema probe 失败 | fail-closed lexical 路径并给出诊断；不得静默文件扫描；修复打包后重建。 |
| article filter 在 ANN 后执行导致漏召回 | 集合外候选占满 top_k | K1/K2/K3 occurrence 必须 metadata pre-filter，契约测试检查零泄漏。 |
| Note 成功被索引失败回滚 | 用户看到失败并重复创建 | Note 成功为事务边界；索引独立状态和 retry。 |
| P6 未完成却接回旧 Agent | 新工具出现在第二套 Python loop | 禁止；只完成服务层，Host integration 等待 P6 正式路径。 |
| 工具说明被实现成固定流程 | 单工具直接 invoke 被拒绝 | 独立调用测试；不允许 prior layer state。 |
| 敏感数据进入 ToolResult/Event | 路径、凭证、原 payload 出现在日志/UI | typed safe error、result allowlist、projection contract。 |

回滚不删除知识表、v2 collection 或历史数据；停止注册四个新 manifest、保留旧 active generation，并通过后续 migration 清理确认无引用的索引数据。
