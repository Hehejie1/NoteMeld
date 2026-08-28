# L0–L3 渐进式能力路由与按需 Wiki 检索 Spec

日期：2026-08-11
作者 / Agent：Codex（doc-driven + writing-plans）
状态：Implemented
关联需求：[`docs/requirements/2026-08-11-progressive-capability-routing.md`](../../requirements/2026-08-11-progressive-capability-routing.md)
关联计划：[`docs/superpowers/plans/2026-08-11-progressive-capability-routing.md`](../plans/2026-08-11-progressive-capability-routing.md)
验证证据：[`docs/superpowers/tests/2026-08-11-progressive-capability-routing.md`](../tests/2026-08-11-progressive-capability-routing.md)

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已阅读 `docs/system/change-spec-template.md`
- [x] 已阅读 `docs/system/local-model-evaluation.md`
- [x] 已搜索 chat/free-chat、Agent loop、WikiSearch、Skill Loader、MCP client、MCP server、前端调用方和相关测试
- [x] 已确认类似能力：`query_intent`、`search_knowledge`、`load_skills`、`discover_all_tools`
- [x] 已确认影响仅为本地 Agent 请求；不修改线上发布、SQLite 或 Wiki 持久化结构

## 1. 当前系统现状

### 1.1 相关模块与入口

- `frontend/src/pages/HomePage/components/ChatComposer.tsx`：free-chat 固定传 `use_wiki: true`。
- `backend/app/routers/chat.py`：`FreeAskRequest.use_wiki: bool = True`，调用 `chat_service.free_chat*`。
- `backend/app/services/chat_service.py`：`_prepare_free_chat_context()` 先分类意图；默认 `mixed`，且 `mixed/current_note/global_wiki` 都会执行 `WikiSearch.search()`。
- `backend/app/agent/chat_adapter.py`：Agent free-chat hooks 复用 `_prepare_free_chat_context()`，因此 Agent 路径也会在首次 LLM 前预搜 Wiki。
- `backend/app/agent/agent_service.py`：free-chat 直接注册 workspace、memory 和全部 Skill 工具；每轮最大 6 turn。
- `backend/app/agent/core/loop.py`：每轮执行 `[t.to_openai_function() for t in state.tools]`，把全部注册工具 schema 交给模型。
- `backend/app/agent/mcp_client.py`：第三方 MCP 工具可发现并适配成 AgentTool，但尚未接入 Agent；adapter 必须由调用方关闭。

### 1.2 相关数据与性能事实

- Wiki 索引文件：`note_results/wiki/graph.json`。
- Wiki 正文/贡献：`contributions/`、`sources/`、`entities/`、`concepts/`。
- 真实样本：561 concept、183 entity、27 source、27 contribution、graph 771 nodes/24 communities。
- `WikiSearch` 当前遍历 contribution JSON 和 materialized Markdown；常驻进程 10 条混合查询只读基准平均约 206ms/次。
- `_format_context` 最多注入约 9000 字符；无关问题存在返回 8 条结果的情况。

### 1.3 相关测试与限制

- `backend/tests/agent/test_agent_service_p3_integration.py` 当前断言直接注册 workspace/memory 工具。
- `backend/tests/agent/test_mcp_client.py` 覆盖 enabled opt-in、tools/list、tools/call 和 adapter close 基础行为。
- `tests/agent/evaluate_retrieval.py` 只评估搜索结果质量，不评估“是否应该搜索”。
- 当前没有 no-search、工具 schema 数量、L0 上限、MCP lazy discovery 或动态 sources 测试。

## 2. 本次目标

- Agent free-chat 首轮不执行完整 Wiki 搜索；legacy flag=false 保持旧行为。
- 首轮只注入 L0 能力地图与三个固定元工具：`capability_discover`、`capability_describe`、`capability_invoke`。
- Wiki、builtin、memory、workspace、Skill、MCP 统一使用带 namespace 的 capability id。
- Wiki graph 用于 L0 主题规模和精确名称 query hints；不读取 Markdown 正文。
- Wiki 搜索只在 L3 调用，结果动态追加到现有 `sources` list。
- MCP server 只在 enabled 且 L2/L3 选中时发现工具；请求结束关闭 adapter。

## 3. 明确不做

- 不改 Wiki 抽取、materialize、rebuild、graph 数据结构。
- 不改 WikiSearch 关键词算法和现有离线检索指标。
- 不改 MCP server `/mcp` 的工具列表和协议。
- 不改前端 UI、请求字段或 SSE 类型。
- 不新增数据库、迁移、配置文件或第三方依赖。
- 不移除 legacy chat、GPTFactory 回滚路径、CLI、桌面或源码入口。

## 4. 冲突分析

| 检查项 | 结论 |
| --- | --- |
| `product-rules.md` | 无冲突。Wiki-First 表示优先使用编译后的结构化知识，不要求每轮无条件扫描；L3 仍返回来源和证据。 |
| `data-model.md` | 无字段或文件语义变更。CapabilityRegistry 为请求级内存对象。 |
| `api-inventory.md` | HTTP/SSE 结构不变；需记录 `use_wiki=true` 在 Agent 路径从“预取”变为“允许按需调用”。 |
| `known-pitfalls.md` | 不进入 Wiki 写锁；保留 MCP opt-in、脱敏、超时和关闭；保留 feature flag 回退。 |
| 桌面/源码/CLI/MCP server | 不改运行入口；Agent MCP client 只使用现有 enabled 配置。 |
| 打包/迁移/导入/回滚 | 无依赖和数据变更；回滚可通过 `AGENT_CHAT_ENABLED=false` 或 revert 代码完成。 |

## 5. 影响范围

- 后端新增：`backend/app/agent/capability_catalog.py`。
- 后端修改：`backend/app/agent/agent_service.py`、`backend/app/agent/chat_adapter.py`、`backend/app/services/chat_service.py`。
- 前端：无代码修改。
- 数据库/迁移：无。
- 文件系统：只读 `graph.json`、Skill 与 MCP 配置；无新持久化文件。
- API：无新增/删除路径或字段。
- MCP：不改 NoteMeld MCP server tools；Agent MCP client 获得延迟接入。
- 测试：新增 capability catalog 契约；更新 Agent 集成/兼容测试。
- 文档：架构、产品规则、API inventory、known pitfalls、requirement/index、验证证据。

## 6. 实施方案

### 6.1 Capability 数据结构

```python
@dataclass
class CapabilityCard:
    capability_id: str
    kind: str
    name: str
    summary: str
    tool: AgentTool | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_l1_dict(self) -> dict[str, Any]:
        return {"id": self.capability_id, "kind": self.kind, "name": self.name, "summary": self.summary}

    def to_l2_dict(self) -> dict[str, Any]:
        if self.tool is None:
            return self.to_l1_dict()
        return {
            **self.to_l1_dict(),
            "input_schema": self.tool.parameters,
            "execution_mode": self.tool.execution_mode,
        }
```

ID 规则：

- `wiki:search`、`wiki:read_page`
- `builtin:<tool_name>`
- `memory:<tool_name>`
- `workspace:<tool_name>`
- `skill:<skill_name>`
- `mcp-server:<server_id>`
- `mcp:<server_id>:<tool_name>`

Capability id 只作为通用元工具参数，不直接成为 OpenAI function name，因此可以安全包含 `:`；底层 AgentTool 名称仍遵守现有 64 字符规则。

### 6.2 L0：能力地图

- 读取 `graph.json`，缓存 key 为 `(absolute graph path, st_mtime_ns)`。
- 缓存值只包含 nodes 和 normalized communities；文件不存在、损坏或结构错误时返回空快照。
- 概览包含：node/community 数、按 size 排序的有限主题标签、问题中精确命中的 entity/concept label。
- query hints 只匹配 graph node label，不读取 entity/concept Markdown。
- Skill 只显示数量和最多 6 个名称；MCP 只显示 enabled server 数量和最多 6 个脱敏名称。
- L0 总长度硬截断为 1200 字符。
- L0 追加决策规则：普通聊天/已有上下文足够时不调用；个人知识、来源、证据、跨笔记比较或命中候选时使用 L1→L2→L3；不得伪造来源。

### 6.3 L1：发现

固定工具：

```text
capability_discover(query, kinds?, limit?)
```

返回：`id/kind/name/summary`。不返回 `parameters`、`input_schema`、Wiki Markdown、MCP config。

- 本地 capability 使用名称/summary 的简单 token score 排序。
- MCP 只返回 `mcp-server:<id>` group card，不触发 tools/list。
- limit clamp 为 1–20，默认 8。

### 6.4 L2：描述

固定工具：

```text
capability_describe(capability_ids, query?, limit?)
```

- 本地 tool：只返回选中 id 的 `input_schema`、`execution_mode`、name/summary。
- Wiki synthetic tool：返回现有搜索/读取参数契约与 L0 coverage，不返回正文。
- MCP server group：首次调用现有 `discover_all_tools({sid: config}, adapters_out=adapters)`；把 discovered tools 注册为 `mcp:<sid>:<tool>`；按 query 过滤后返回选中 schema。
- MCP config 的 auth/header/env/url/command 不进入返回值或日志。

### 6.5 L3：执行

固定工具：

```text
capability_invoke(capability_id, arguments)
```

- 本地 AgentTool：透传 `call_id/params/signal/on_update`，保留 Skill 长任务、workspace 和 memory 行为。
- Wiki search：复用 `WikiSearch.search(query, limit, intent=classify_query_intent(query), linked_task_id=self.linked_task_id)`；通过 `asyncio.to_thread` 避免阻塞 loop。
- Wiki read：只允许 `concept/entity`，复用 `WikiStore.list_file_pages/get_file_page` 的 safe id 语义。
- Wiki 结果写入 registry 构造时拿到的 `source_sink`；按 source id 去重。SSE bridge 和非流式结果原本就持有同一 list，因此 done 时可见动态来源。
- MCP tool：若未发现则按 server id 延迟发现；调用现有 MCP AgentTool execute。
- 未知/禁用/参数错误返回 `ToolResult(is_error=True)`。
- `use_wiki=false` 时 registry 不注册 Wiki；invoke 再做一次前缀门禁，防止缓存/提示词残留绕过。

### 6.6 Free-chat 接入

`_prepare_free_chat_context` 新签名：

```python
def _prepare_free_chat_context(
    question: str,
    linked_task_id: Optional[str],
    use_wiki: bool,
    *,
    prefetch_wiki: bool = True,
) -> QueryContext:
```

- legacy `chat_service.free_chat*` 不传新参数，维持 prefetch。
- `build_free_chat_hooks` 显式传 `prefetch_wiki=False`，保留当前关联笔记向量与会话资产上下文。
- `run_free_chat*` 在 hooks 后构造 registry，把 L0 prepend 到 `hooks.system_prompt`，Agent tools 只设为三个 progressive tools。
- `run_free_chat` 和 `run_free_chat_stream` 都在 `finally` 调 `await registry.close()`。
- stream 客户端断开/取消时 finally 仍执行。

### 6.7 错误处理、日志、并发与超时

- graph 读取错误：warning + 空摘要，不影响聊天。
- Skill 解析错误：沿用 load_skills 跳过非法文件。
- MCP tools/list 或 tools/call：沿用 timeout/error ToolResult；registry.close best-effort。
- Wiki search/read：捕获异常并返回 error ToolResult，不修改 Wiki 状态。
- cache 使用 immutable snapshot；不引入写锁，也不调用 Wiki rebuild。
- 同一请求对同一 MCP server 最多 discover 一次；不同请求隔离 adapter 生命周期。

## 7. 数据变更

- SQLite 表：无新增/修改。
- 字段：无新增/修改。
- 文件结构：无新增/修改。
- 迁移：无。
- 历史数据：继续读取现有 graph、pages、Skill、MCP config。
- 脏数据：损坏 graph 降级为空；不清理、不覆盖。
- 回滚：无数据处理。

## 8. 接口变更

- 新增 HTTP 接口：无。
- 修改 HTTP 请求/返回字段：无。
- 删除接口：无。
- 内部 Python 接口：`_prepare_free_chat_context` 新增 kw-only `prefetch_wiki=True`。
- SSE：类型和字段不变；`sources` 改为实际 L3 Wiki 搜索结果动态追加。
- MCP server：无变化。
- 兼容策略：flag=false legacy 预搜；flag=true progressive routing。
- 更新 `docs/system/api-inventory.md`：是。

## 9. UI/交互变更

- 页面/组件：无。
- 用户操作路径：无。
- 加载/空/失败/成功态：沿用 Agent 工具结果、现有消息和 sources 展示。
- 桌面与浏览器差异：无。

## 10. 测试方案

### 10.1 后端单元/契约

- L0 graph cache、空/损坏 graph、字符上限、主题和 query hints。
- L1 不含 schema/正文/敏感 config。
- L2 只描述 selected id。
- L3 Wiki source sink、Wiki off 双重门禁、Skill execute。
- MCP L0/L1 zero discovery、L2 lazy tools/list、L3 tools/call、close。
- free-chat hook 不预搜；legacy 仍预搜。
- Agent 初始 tools 恰为三个 meta tools。
- model error/client cancel 时 registry.close。

### 10.2 回归

```bash
python3 -m compileall backend/app
cd backend && python3 -m pytest tests/agent tests/agent_core tests/ai/test_chat_service_migration.py tests/test_core_mcp_generation_tools.py -q
cd frontend && pnpm test:contracts
cd frontend && pnpm build
scripts/run_core_regression.sh
```

### 10.3 手动/指标

- 在真实 graph 上记录 L0 长度、首次/缓存耗时。
- 对“你好”“润色”“我的知识库里 RAG 是什么”“请给 Agent 的来源证据”记录 hint 和是否调用 WikiSearch。
- 首轮 OpenAI tools 数必须固定为 3，与 Skill/MCP 数量无关。

## 11. 验收标准

- [ ] Agent free-chat 首次 LLM 前 WikiSearch 调用数为 0。
- [ ] L0 ≤ 1200 字符，命中长尾名称时有 ≤5 个 hints，且未读取 Markdown。
- [ ] L1 无 schema/正文/敏感配置；L2 只有 selected schema。
- [ ] 初始 tools 数固定为 3。
- [ ] L3 Wiki 结果进入 sources。
- [ ] Skill L3 可执行并保留 long task update。
- [ ] MCP 只在 L2/L3 discovery，且请求结束 adapter close。
- [ ] `use_wiki=false` 注册与执行双重阻止 Wiki。
- [ ] flag=false legacy 和 API/SSE 契约不变。
- [ ] 定向后端测试、前端 contracts/build 通过；验证证据落盘。

## 12. 风险和回滚

- 主要风险：弱模型可能不按 L1→L2→L3 调用，导致召回下降。
- 触发信号：新增路由决策集上个人知识/来源问题的工具调用率下降，或用户问题无来源直接回答。
- 降级策略：system prompt 对个人知识/来源设 MUST 规则；保留 query hints；必要时后续引入明确意图的 deterministic forced discover，但本次不强制完整 search。
- MCP 风险：adapter 泄漏或远端发现慢；用请求级 registry、lazy discovery、finally close。
- Wiki 风险：graph stale；L3 实际 WikiSearch 仍读取 live pages，L0 只影响提示，不作为事实答案。
- 回滚步骤：设置 `AGENT_CHAT_ENABLED=false` 即时回退；代码回滚 capability integration；无数据回滚。
- 回滚后一致性：无新增数据，原 Wiki/Skill/MCP 配置不受影响。
- 用户可见影响：回滚后恢复默认 Wiki 预搜与旧 sources 行为。

## 13. Agent 必答问题

| 问题 | 回答 |
| --- | --- |
| 影响哪些已有模块？ | chat_service、chat_adapter、agent_service、Agent tool registry、WikiSearch、Skill Loader、MCP client、sources 输出。 |
| 当前是否已有类似能力？ | 有分散能力：query intent、search_knowledge、load_skills、discover_all_tools；缺统一层级和按需生命周期。 |
| 是否和产品规则冲突？ | 否。仍为 Wiki-First，只有检索时机从无条件预取改为按需。 |
| 是否和数据模型冲突？ | 否。请求级内存结构，无字段变化。 |
| 是否重新引入 known pitfalls？ | 不进入写锁；保留 MCP opt-in/脱敏/close；API wrapper 与 feature flag 保留。 |
| 是否影响本地数据或线上服务？ | 只读本地索引和配置；L3 可能访问用户已启用 MCP；无线上 NoteMeld 服务变更。 |
| 最小可行改动？ | 一个 capability_catalog 模块 + 三处 Agent/chat 接入 + 契约测试和系统文档。 |
| 需要补哪些测试？ | no-search、L0 bound/cache/hints、L1/L2 边界、L3 sources、Skill、MCP lazy/close、Wiki off、legacy compatibility。 |
