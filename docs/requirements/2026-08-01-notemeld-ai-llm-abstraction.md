# notemeld-ai：统一 LLM Provider 抽象与 Token 统计

日期：2026-08-01
作者 / Agent：doc-driven 流程
状态：Ready for Plan
关联对话 / 任务：Pi 框架分析 → 分层架构确认 → P0 底层
关联系统文档：`docs/system/current-architecture.md`、`docs/system/data-model.md`、`docs/system/product-rules.md`、`docs/system/known-pitfalls.md`

## 1. 原始需求

> "pi-ai 只负责将所有 ai 平台底层抹平，还有就是统计这个 token 的消耗，支持调用查询。有一定的改造工作。"
>
> "先抽离底层 notemeld-ai 和 notemeld-agent-core，然后再验证顶层的 notemeld-agent。"
>
> 技术路线：先作为 NoteMeld 仓库内模块，稳定后再抽独立 pip 包。

## 2. 背景和问题

- **当前用户是谁**：NoteMeld 开发者和后续使用 notemeld-agent-core / notemeld-agent 的上层业务
- **当前场景是什么**：每次 LLM 调用需要手动组装 provider 配置、建 OpenAI 兼容 client、手动调用 record_usage、分散在 NoteGenerator / SummaryRefineEngine / chat_service / WikiPageMerger / template_extraction 等十几个调用点
- **当前痛点是什么**：
  1. `GPTFactory` 锁死 OpenAI SDK，无法接入 Anthropic 原生 thinking 模式、Google Gemini 原生 API、非 OpenAI 兼容协议
  2. `record_usage` 散落在每个调用点，流式场景下需要手动组装 usage_usage，漏统计或重复统计风险高
  3. 流式和非流式走不同代码路径，错误处理和重试逻辑不一致
  4. 模型能力（vision/thinking/tool_call）以 `model_capabilities` 表手动探测，探测失败时为 null，调用方必须容错但没人统一处理
  5. provider 的 API key 解析在 `ModelService._resolve_api_key`，但没有 auth 失效/刷新的统一钩子
- **为什么现在要做**：后续的 notemeld-agent-core 依赖统一的模型接口；研究助手需要多模型切换和 thinking 模式；现在不抽会导致 agent 层重复写兼容逻辑

## 3. 目标结果

- **目标 1**：提供 `notemeld_ai` 模块（仓库内路径 `backend/app/ai/`），对外暴露统一的 `Models` 集合，支持 `stream()` / `complete()` 双入口，内置 usage 事件，调用方无需手动 record_usage
- **目标 2**：Provider 抽象支持 OpenAI 兼容（现有所有 provider 无缝迁移）+ Anthropic 原生 + Google Gemini（先预留接口，本期不接具体实现）；模型 catalog 声明 vision/thinking/tool 能力
- **目标 3**：替换现有所有 GPTFactory 调用点（NoteGenerator / chat_service / WikiPageMerger 等），model_usage_records 表口径、字段、统计维度 100% 不变，现有用量页无差异
- **目标 4**：提供查询 API（与原 /api/usage/* 对齐），调用方可以按 provider/model/task_id 等维度查询用量和成本

## 4. 非目标

- 不做：前端模型选择 UI 的改造（保留现有 providers/models 表结构和设置页流程）
- 不做：新增或删减 SQLite 表/字段（model_usage_records、providers、models、model_capabilities 结构不变）
- 不做：具体接入 Anthropic / Google 的实现（只留扩展点和 Provider 抽象接口）
- 不做：把 notemeld-ai 抽成独立 pip 包（先作为仓库内模块）
- 不做：Agent 循环和工具执行（属于 notemeld-agent-core）
- 不做：thinking / reasoning budget 的业务层策略（notemeld-agent-core 再定义）

## 5. 当前系统事实

- 已有类似能力：`backend/app/gpt/`（GPTFactory、UniversalGPT、OpenAICompatibleProvider、base GPT 抽象）+ `record_usage()` 在 `backend/app/services/usage_tracker.py`
- 当前入口 / API：`/api/usage/overview`、`/api/usage/records`、`/api/usage/task_summary`、`/api/usage/task_calls/{task_id}`；LLM 调用无统一入口，每个 service 自己调
- 当前数据来源和写入位置：providers/models/model_capabilities/model_usage_records 四张 SQLite 表；API key 明文存 providers.api_key（字段语义不变）
- 当前限制：
  - 所有 Provider 必须走 OpenAI 兼容 SDK（`from openai import OpenAI`）
  - `free_chat_stream` 流式场景手动拼接 SSE，usage 通过 `response_usage` 参数传入
  - `model_capabilities(provider_id, model_name)` 探测结果为 null 时，调用方无法知道模型到底支不支持 tool call
- 相关 known pitfalls：
  - API Key 不允许出现在响应、日志、MCP 输出（notemeld-ai 的 Provider 层必须继续遵守）
  - 不能破坏现有 API response wrapper（/api/usage 接口保持 {code,msg,data}）
  - 不能让慢 LLM 请求进入全局写锁（notemeld-ai 本身不持锁，但要保证上层可以保持当前锁粒度）

## 6. 用户故事

- 作为开发者，我希望通过 `models.stream(model, context, options)` 一行代码发起 LLM 流式调用，自动解析 auth、自动写 usage、自动抛标准化错误，以便在 NoteGenerator、chat_service 等十多个地方不用重复组装
- 作为研究助手 Agent，我希望切换到 Anthropic Claude（原生 thinking）时，只需要 `models.getModel('anthropic', 'claude-sonnet-4-5')`，不需要改调用方代码，以便 Agent 能选最合适的模型做深入分析
- 作为用户，我打开 `/settings/usage` 用量页，看到的 token 数、成本、按 provider/model 维度的聚合和改造前完全一致，以便迁移无感

## 7. 验收标准

1. GIVEN 旧代码 `gpt = GPTFactory.from_config(config); resp = gpt.client.chat.completions.create(...)` 的所有调用点，WHEN 迁移到 `models.complete(model, ctx, opts)` 后，THEN 返回的 message.content / tool_calls 语义不变，且 model_usage_records 表中插入的记录字段（task_id/provider_id/model_name/phase/platform/video_id/token/状态/耗时）和迁移前逐字段相等

2. WHEN 调用 `models.stream(model, ctx, opts)` 并读取完整流后，THEN 同一次调用只写一条 usage 记录，prompt_tokens/output_tokens 与 provider 返回值一致，流式场景不产生重复或缺失记录

3. GIVEN 一个不支持 tool calling 的模型，WHEN 传了 tools 参数，THEN notemeld-ai 主动返回清晰错误（而不是让 provider 返回 400 或静默丢弃 tools），错误中包含 model id + capability 缺失类型

4. WHEN providers.api_key 读取失败或 provider.base_url 不可达，THEN notemeld-ai 抛出类型化错误（ProviderAuthError / ProviderNetworkError / ProviderRateLimitError），上层可以分类处理

5. GIVEN /api/usage/overview 等 4 个现有用量查询接口，WHEN 对照迁移前后同一份 SQLite，THEN 返回的聚合值、分页、排序、错误语义逐字段一致

## 8. 输入 / 输出样例

### 输入（统一调用示例）

```python
from app.ai import create_models, get_provider, Type, Tool

models = create_models()  # 自动注册 DB 中的 provider
model = models.get_model(provider_id="prov_123", model_name="deepseek-chat")

tools = [Tool(
    name="lookup_transcript",
    description="查询视频转写片段",
    parameters=Type.Object({
        "task_id": Type.String(),
        "keyword": Type.Optional(Type.String())
    })
)]

ctx = {
    "system_prompt": "你是助手",
    "messages": [{"role": "user", "content": "帮我查 XXX 说了什么", "timestamp": 1234567890}],
    "tools": tools,
}

# 流式
for event in models.stream(model, ctx, options={"usage_context": {"task_id": "abc", "phase": "chat"}}):
    if event.type == "text_delta":
        yield event.delta

# 非流式
final = models.complete(model, ctx, options={"usage_context": {"task_id": "abc"}})
```

### 输出

- 流事件类型：`start` / `text_start` / `text_delta` / `text_end` / `thinking_start` / `thinking_delta` / `thinking_end` / `toolcall_start` / `toolcall_delta` / `toolcall_end` / `done` / `error`
- `final.usage` 字段：`{input_tokens, output_tokens, total_tokens, cost: {total, input, output}}`
- `model_usage_records`：插入一条，字段值和调用时传入的 `usage_context` + 最终 `usage` 对齐

### 反例或失败样例

- provider.api_key 为 None → 抛 `ProviderAuthError("provider_id=xxx 未配置 API Key")`，不向 provider 发起空请求
- 流式中途网络断开 → 在流中 emit `error` 事件，并尝试写一条 `status=failed` usage 记录
- `get_model()` 找不到对应 provider/model → 返回 None（和现有 ModelService 行为一致），不抛异常

## 9. 约束

- **平台 / 设备**：Python 3.11+；本地自托管；桌面 sidecar 和源码启动双模式都必须跑通
- **性能 / 耗时**：单次 LLM 调用额外开销（notemeld-ai 封装层）≤ 原 GPTFactory 的 5%；P95 增加不超过 20ms
- **隐私 / 安全**：providers.api_key 不写入日志、不序列化、不缓存到内存以外的地方；和现有 `record_usage` 同级别脱敏
- **兼容性**：
  - 旧的 `GPTFactory` / `UniversalGPT` 在过渡期保留（加 DeprecationWarning），迁移完成后至少等一个 Beta 版本再删
  - providers/models/model_capabilities/model_usage_records 字段、唯一性、索引 0 改动
  - /api/usage/* 四个接口的请求/响应结构 0 改动
  - MCP list_models 不回显 API Key 的行为 0 改动
- **成本**：不引入任何付费 SDK 或云依赖；仍使用用户本地配置的 provider 自付
- **时间**：P0 里程碑，必须在 notemeld-agent-core 之前完成并通过回归
- **第三方依赖 / License**：可以引入 `pydantic`（项目已用）做参数 schema；不引入重量级 LLM SDK，OpenAI SDK 保留（项目已用）

## 10. 边界场景

- **空数据**：messages 为空、provider 列表为空 → 返回明确错误或空集合，不得 crash
- **权限拒绝**：provider 返回 401/403 → ProviderAuthError，并写 usage.status=failed，error_message 取 provider 原文截断到 1000 字符
- **网络失败**：超时 / 连接重置 / DNS 失败 → ProviderNetworkError；不无限重试（默认 1 次，由上层策略决定是否重试）
- **任务中断**：LLM 请求进行中收到 abort signal（上层传入 AbortSignal）→ 立即 cancel，写 usage.status=failed，不泄露 traceback
- **旧数据兼容**：model_usage_records 中旧记录的 token/cost 字段为 null 时，查询接口按原逻辑容错（新模块不改变查询方兼容代码）
- **大数据量**：长 context（>100K token）下，封装层不应把整个消息列表全量深拷贝超过 1 次
- **其他**：同一个 provider 在多线程并发调用时，auth modify 操作（如果有）必须串行化，避免 token refresh 双刷（参考 pi-ai 的 CredentialStore.modify 语义）

## 11. 开放问题

无。所有阻塞项已在对话中确认。

## 12. 与系统事实的冲突检查

- **是否和 product-rules.md 冲突**：否。本地优先、API Key 不回显、MCP endpoint 不变等规则均在约束中显式承诺
- **是否和 data-model.md 字段语义冲突**：否。表结构、字段、唯一性、task_id 关联主键均不动
- **是否和 api-inventory.md 接口语义冲突**：否。/api/usage/* 四个接口 wrapper 不变；新增内部模块（不新增 API，初期）
- **是否会重新引入 known-pitfalls.md 中的问题**：
  - Wiki 同步 materialize 卡死：否，notemeld-ai 不涉及 Wiki 写锁
  - API Key 泄露：约束 + 验收标准覆盖
  - 桌面 sidecar 未 ready 抢跑：否，notemeld-ai 不改变 ready 门禁
- **是否影响本地数据或线上服务**：本地数据只读 providers/models 表 + 追加写 model_usage_records，无破坏性变更
- **是否影响用户已确认交互**：否。用量页、设置页 UI/UX 不变

## 13. 实际影响清单（DB / 数据结构 / 接口 / 文件 / 回归点）

> 用于回归测试与变更影响审计。P0-P5 全部完成后统一写回 `docs/system/`。

### 13.1 数据库影响

| 表 | 字段 | 影响 | 备注 |
| --- | --- | --- | --- |
| `providers` | 全部字段 | **只读** | notemeld-ai 通过 `ModelService` 读取，不修改 |
| `models` | 全部字段 | **只读** | 同上 |
| `model_capabilities` | 全部字段 | **只读** | catalog 声明从该表加载；探测逻辑不动 |
| `model_usage_records` | 全部字段 | **追加写**（不改 schema） | 由 notemeld-ai 内置 usage writer 写入；字段、主键、索引、唯一约束 0 改动 |

**结论**：P0 不新增表、不新增字段、不新增索引、不新增迁移脚本。

### 13.2 数据结构影响

| 数据结构 | 类型 | 变更 |
| --- | --- | --- |
| `Models` / `Model` / `Provider` 抽象类 | 新增 | `backend/app/ai/models.py`、`backend/app/ai/provider.py` |
| `Tool` / `Type` 参数 schema | 新增 | `backend/app/ai/tool.py`（TypeBox 等价，pydantic 实现） |
| Stream 事件 `StreamEvent` | 新增 | 12 种事件类型枚举（start/text_start/text_delta/text_end/thinking_*/toolcall_*/done/error） |
| `Usage` / `UsageContext` | 新增 | 内置 usage 收集器，封装 prompt_tokens/output_tokens/cost |
| `ProviderAuthError` / `ProviderNetworkError` / `ProviderRateLimitError` / `ProviderCapabilityError` | 新增 | 标准化异常分类 |
| 旧 `GPTFactory` / `UniversalGPT` | **保留 + DeprecationWarning** | 过渡期至少 1 个 Beta 版本不删 |
| 旧 `record_usage()` 函数 | **保留** | notemeld-ai 内部调用它，不破坏其他调用点 |

### 13.3 接口影响

| 接口 | 类型 | 变更 |
| --- | --- | --- |
| `/api/usage/overview` | 既有 | **0 改动**（response wrapper/字段/分页/排序） |
| `/api/usage/records` | 既有 | **0 改动** |
| `/api/usage/task_summary` | 既有 | **0 改动** |
| `/api/usage/task_calls/{task_id}` | 既有 | **0 改动** |
| MCP `list_models` | 既有 | **0 改动**（不回显 API Key 行为不变） |

**结论**：P0 不新增/不修改/不删除任何对外 API。仅替换内部 LLM 调用入口。

### 13.4 文件清单

**新增**：
- `backend/app/ai/__init__.py`
- `backend/app/ai/models.py`（Models 集合 + Model 对象）
- `backend/app/ai/provider.py`（Provider 抽象 + OpenAICompatible 实现 + Anthropic/Gemini 扩展点）
- `backend/app/ai/tool.py`（Tool / Type schema）
- `backend/app/ai/stream.py`（StreamEvent + 流式协议）
- `backend/app/ai/usage.py`（Usage 收集器 + 自动写 model_usage_records）
- `backend/app/ai/errors.py`（标准化异常）
- `backend/app/ai/catalog.py`（模型能力 catalog 加载）
- `backend/tests/ai/test_models.py`
- `backend/tests/ai/test_stream.py`
- `backend/tests/ai/test_usage.py`
- `backend/tests/ai/test_provider_compat.py`（旧→新双写对比）

**修改**（迁移调用点，每个文件加 `from app.ai import ...` 替换 GPTFactory）：
- `backend/app/services/note_generator.py`（NoteGenerator._summarize_text 等）
- `backend/app/services/chat_service.py`（chat / free_chat / free_chat_stream）
- `backend/app/services/wiki_page_merger.py`（merge）
- `backend/app/services/template_extraction.py`
- `backend/app/services/summary_refine_engine.py`
- `backend/app/services/style_service.py`（如涉及 LLM 调用）
- `backend/app/gpt/gpt_factory.py`（保留，加 DeprecationWarning）

### 13.5 回归测试点（关键回归断言）

| 回归点 | 验证方式 | 通过标准 |
| --- | --- | --- |
| Usage 记录一致性 | 双写对比脚本：同一 prompt 同时走 GPTFactory 和 notemeld-ai | model_usage_records 各字段逐字段相等 |
| /api/usage/* 4 接口 | `backend/tests/test_usage_apis.py` 迁移前后响应 diff | 0 字段差异 |
| NoteGenerator 端到端 | `scripts/run_core_regression.sh` | 全绿 |
| chat 端到端 | `backend/tests/test_chat_*.py` | 全绿 |
| MCP list_models | `backend/tests/test_core_mcp_generation_tools.py` | 全绿，API Key 不回显 |
| 流式 chat | 手动 + 契约 `frontend/pnpm test:contracts` | SSE delta/done/error 不变 |
| 桌面 sidecar 启动 | `packaging/build-backend-macos.sh` 后启动 | ready 门禁不被破坏 |
| 源码启动 | `scripts/run_notemeld.sh` | 启动正常 |

## 14. Superpowers 交接

- 是否已达到 Ready for Plan：是
- 推荐下一步：
  - [x] 使用 Superpowers 生成 `docs/superpowers/plans/2026-08-01-notemeld-ai-llm-abstraction.md`
  - [ ] 使用 Superpowers 生成 `docs/superpowers/specs/2026-08-01-notemeld-ai-llm-abstraction.md`
  - [ ] 继续向用户澄清
- 计划必须覆盖的验收标准：第 1（旧调用点迁移一致性）、2（流式 usage 唯一写入）、5（查询接口不变）条
- 计划必须补充的验证：
  - 旧→新调用点逐调用点对比回归（NoteGenerator._summarize_text / chat_service.chat / free_chat_stream / WikiPageMerger.merge / template_extraction 至少各一条端到端）
  - 双写对比：同一请求同时走旧 GPTFactory 和新 notemeld-ai，逐字段比对 usage 记录
