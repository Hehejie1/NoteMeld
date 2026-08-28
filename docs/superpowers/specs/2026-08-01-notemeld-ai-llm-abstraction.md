# P0 notemeld-ai：Plan + Spec（合并）

日期：2026-08-01
作者 / Agent：doc-driven 流程
关联需求：[`docs/requirements/2026-08-01-notemeld-ai-llm-abstraction.md`](../../requirements/2026-08-01-notemeld-ai-llm-abstraction.md)
状态：Confirmed（待用户最终确认后开始执行）

---

## Part A：Plan（任务拆分 + 依赖顺序 + 风险）

### A.1 任务拆分（按依赖顺序）

| # | 任务 | 依赖 | 验收映射 | 风险 |
| --- | --- | --- | --- | --- |
| T1 | 创建 `backend/app/ai/` 骨架 + errors.py + tool.py（Type schema） | 无 | - | 低，纯类型定义 |
| T2 | 实现 `provider.py`：Provider 抽象 + OpenAICompatibleProvider（复用现有 OpenAI SDK） | T1 | §7.4 Auth 错误分类 | 中，需保留与 ModelService 一致的 auth 解析 |
| T3 | 实现 `catalog.py`：从 `model_capabilities` 表加载能力 | T1 | §7.3 capability 报错 | 低 |
| T4 | 实现 `usage.py`：Usage 收集器 + 自动写 `model_usage_records`（复用 `record_usage`） | T1 | §7.1 §7.2 字段一致 | **高**，必须字段逐字段等价 |
| T5 | 实现 `stream.py`：StreamEvent 12 类 + 流式协议 | T1 | §7.2 流式唯一写入 | 中 |
| T6 | 实现 `models.py`：Models 集合 + Model 对象 + `stream()` / `complete()` 入口 | T2 T3 T4 T5 | §7.1 §7.2 §7.3 §7.4 | 中，整合层 |
| T7 | 单元测试 `backend/tests/ai/test_*.py`（models/stream/usage/catalog/errors） | T6 | §13.5 回归 | 中 |
| T8 | 双写对比测试 `test_provider_compat.py`：同 prompt 同时走 GPTFactory 和 notemeld-ai | T6 | §7.1 §7.2 §7.5 | **高**，是迁移质量门禁 |
| T9 | 迁移调用点 1：`chat_service.py`（chat/free_chat/free_chat_stream） | T6 T8 | §7.5 接口不变 | **高**，最敏感 |
| T10 | 迁移调用点 2：`note_generator.py`（_summarize_text 等） | T6 T8 | §13.5 核心回归 | **高**，路径多 |
| T11 | 迁移调用点 3：`wiki_page_merger.py` / `template_extraction.py` / `summary_refine_engine.py` / `style_service.py` | T6 T8 | §13.5 | 中 |
| T12 | 给 `gpt_factory.py` 加 DeprecationWarning（不删） | T9-T11 | §9 兼容性 | 低 |
| T13 | 端到端回归：`scripts/run_core_regression.sh` + `pnpm test:contracts` + 手动 SSE 验证 | T9-T12 | §13.5 全部 | - |
| T14 | 验收报告 `docs/superpowers/tests/2026-08-01-notemeld-ai-llm-abstraction.md` | T13 | - | - |

### A.2 依赖图

```
T1 ─┬─ T2 ──┐
    ├─ T3 ──┤
    ├─ T4 ──┼─ T6 ── T7
    └─ T5 ──┘       │
                    ├─ T8 ──┐
                    │       │
                    └───────┼─ T9 ──┐
                            ├─ T10 ─┼─ T12 ─ T13 ─ T14
                            └─ T11 ─┘
```

### A.3 风险与回滚

| 风险 | 触发信号 | 降级 / 回滚 |
| --- | --- | --- |
| usage 字段不一致 | 双写对比失败 | 立即回滚 T9-T11 调用点迁移，GPTFactory 不动 |
| 流式 SSE 行为变化 | `pnpm test:contracts` 失败 | 回滚 T9 中 free_chat_stream，保留旧实现 |
| 桌面 sidecar 启动失败 | packaging build 后启动无响应 | 检查 ready 门禁，回滚全部迁移 |
| DeprecationWarning 噪声 | 用户反馈日志爆炸 | 调整 warning 级别为 OncePerSession |

**回滚策略**：T9-T11 调用点迁移用 `from app.ai import ...` 一行 import 替换；回滚 = 改回 `from app.gpt import GPTFactory`。GPTFactory 全程不删，保证可秒回滚。

---

## Part B：Spec（详细规格，按 NoteMeld change-spec-template）

### B.0 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已搜索 `backend/app/gpt/` 现有代码
- [x] 已搜索 `backend/tests/test_chat_*.py` / `test_core_mcp_*.py` 现有测试
- [x] 已确认 ModelService 是 GPTFactory 的 auth/配置来源
- [x] 已确认不影响线上服务（NoteMeld 无线上服务，本地优先）

### B.1 当前系统现状

- **相关模块**：`backend/app/gpt/`（gpt_factory.py / universal_gpt.py / openai_compatible_provider.py / base.py）、`backend/app/services/usage_tracker.py`、`backend/app/services/model_service.py`
- **相关入口**：所有 LLM 调用入口都在各 service 内部，无统一 entry
- **相关数据表**：providers / models / model_capabilities / model_usage_records
- **相关 API**：`/api/usage/overview|records|task_summary|task_calls/{id}`（4 个查询接口）
- **相关测试**：`backend/tests/test_chat_*.py`、`backend/tests/test_core_mcp_generation_tools.py`、`backend/tests/test_core_task_status_contracts.py`、`frontend/contracts/*`
- **当前行为**：每个 service 调 `GPTFactory.from_config(config)` → `gpt.client.chat.completions.create(...)`；流式靠 `stream=True` 迭代 chunks；usage 靠 `record_usage(...)` 手动写
- **当前限制**：见需求 §2

### B.2 本次目标（可验证）

- 用户问题：见需求 §1
- 成功后的用户可见行为：用量页数值 0 差异；现有所有功能 0 退化
- 成功后的系统内部行为：所有 LLM 调用走 notemeld-ai；GPTFactory 标记 deprecated 但不删
- 必须保留的旧行为：见需求 §9 兼容性

### B.3 明确不做

见需求 §4。

### B.4 冲突分析

见需求 §12。

### B.5 影响范围（即需求 §13 实际影响清单）

详见需求 §13.1-§13.5。

**关键摘要**：
- DB：4 张表全部 0 schema 改动，仅 model_usage_records 追加写
- 接口：4 个 /api/usage/* 全部 0 改动；MCP list_models 0 改动
- 文件：新增 8 个 + 测试 4 个；修改 7 个调用点 + 1 个 GPTFactory（加 warning）
- 回归点：8 类回归断言

### B.6 实施方案

#### 后端

**改动点**：见 A.1 任务拆分。核心实现：

```python
# backend/app/ai/models.py 核心伪代码
class Models:
    def __init__(self, model_service: ModelService):
        self._ms = model_service
        self._providers_cache: dict[str, Provider] = {}

    def get_model(self, provider_id: str, model_name: str) -> Model | None:
        provider_cfg = self._ms.get_provider(provider_id)
        if not provider_cfg: return None
        provider = self._get_or_create_provider(provider_cfg)
        caps = self._ms.get_capabilities(provider_id, model_name)
        return Model(provider=provider, name=model_name, capabilities=caps)

    async def stream(self, model, ctx, options) -> AsyncIterator[StreamEvent]:
        # 1. capability check → 不支持 tools 抛 ProviderCapabilityError
        # 2. provider.stream(...) 异步生成器
        # 3. 累积 usage（流末由 provider 返回 usage）
        # 4. 流末调 usage_writer.write(usage, options.usage_context)
        # 5. 异常 → emit error event + 写 status=failed usage
        ...

    async def complete(self, model, ctx, options) -> CompleteResult:
        # 同 stream 但聚合为单次返回
        ...
```

```python
# backend/app/ai/usage.py 核心伪代码
class UsageWriter:
    def __init__(self, db_session):
        self._db = db_session

    async def write(self, usage: Usage, ctx: UsageContext):
        # 复用现有 record_usage() 函数，保证字段语义 100% 一致
        record_usage(
            db=self._db,
            task_id=ctx.task_id,
            provider_id=ctx.provider_id,
            model_name=ctx.model_name,
            phase=ctx.phase,
            platform=ctx.platform,
            video_id=ctx.video_id,
            prompt_tokens=usage.input_tokens,
            completion_tokens=usage.output_tokens,
            total_tokens=usage.total_tokens,
            cost=usage.cost.total,
            status="success",
            error_message=None,
            elapsed_ms=ctx.elapsed_ms,
        )
```

**错误处理**：见需求 §10 边界场景。
**日志/可观测性**：API Key 不打日志；usage 失败要单独 log（不能阻塞主流程）。
**并发/取消**：同一 provider 并发调用不互相阻塞；abort 信号通过 asyncio.CancelledError 传递。

#### 前端

无改动。

#### 桌面/打包

无改动。`packaging/build-backend-*.sh` 不动；Tauri ready 门禁不动。

### B.7 数据变更

- 是否新增/修改 SQLite 表：**否**
- 是否新增/修改字段：**否**
- 是否新增/修改文件结构：**是**，新增 `backend/app/ai/` 目录
- 是否需要迁移：**否**
- 是否影响历史数据：**否**
- 是否需要清理脏数据：**否**
- 回滚后数据如何处理：model_usage_records 中既有旧 GPTFactory 记录也有新 notemeld-ai 记录，按 task_id + timestamp 区分；回滚后新记录保留不删

### B.8 接口变更

- 新增接口：**无**
- 修改接口：**无**
- 删除接口：**无**
- 请求参数变化：**无**
- 返回结构变化：**无**
- 错误语义变化：**无**（内部 LLM 调用错误现在通过 ProviderAuthError 等类型化异常抛出，但对外 API 的错误响应 wrapper 不变）
- 前端调用方：无改动
- MCP 调用方：无改动
- 兼容策略：GPTFactory 保留 + DeprecationWarning
- 是否更新 `docs/system/api-inventory.md`：**否**（接口 0 改动，但 P0-P5 完成后统一更新）

### B.9 UI/交互变更

无。P0 纯后端。

### B.10 测试方案

- 后端单测：`backend/tests/ai/test_*.py`（models/stream/usage/catalog/errors）
- 双写对比：`test_provider_compat.py`（同 prompt 双路径，逐字段断言 usage 记录）
- 后端契约：`backend/tests/test_chat_*.py` / `test_core_mcp_generation_tools.py` / `test_core_task_status_contracts.py` 全绿
- 前端契约：`cd frontend && pnpm test:contracts` 全绿
- 构建：`cd frontend && pnpm build` 全绿
- 核心回归：`scripts/run_core_regression.sh` 全绿
- 桌面：`packaging/build-backend-macos.sh` 后启动验证
- 手动：粘贴视频链接生成笔记 1 次 + 在会话页 free_chat_stream 1 次
- 原问题复现：N/A（新需求）
- 回归断言：见需求 §13.5

### B.11 验收标准

见需求 §7。每条都通过即验收通过。

- [ ] §7.1 旧调用点迁移后字段逐字段相等
- [ ] §7.2 流式只写一条 usage
- [ ] §7.3 不支持 tool 的模型主动报错
- [ ] §7.4 Auth/Network/RateLimit 类型化错误
- [ ] §7.5 /api/usage/* 4 接口 0 字段差异

### B.12 风险和回滚

见 A.3。

### B.13 Agent 必答问题

- 这个需求影响哪些已有模块？→ `backend/app/gpt/`、`backend/app/services/note_generator.py / chat_service.py / wiki_page_merger.py / template_extraction.py / summary_refine_engine.py / style_service.py / model_service.py / usage_tracker.py`
- 当前系统是否已有类似能力？→ 有，GPTFactory + record_usage，本需求是替换内部实现
- 是否和产品规则冲突？→ 否
- 是否和数据模型字段语义冲突？→ 否，0 schema 改动
- 是否会重新引入 known-pitfalls 中的问题？→ 否，已逐项检查
- 是否影响本地数据或线上服务？→ 仅追加写 model_usage_records，无破坏
- 最小可行改动是什么？→ A.1 任务拆分
- 需要补哪些测试防止回归？→ B.10 测试方案

### B.14 Implementation Reference（关键实现参考）

#### Provider 抽象

```python
# backend/app/ai/provider.py
class Provider(Protocol):
    name: str
    async def stream(self, model: str, ctx: LLMContext, signal: AbortSignal) -> AsyncIterator[StreamEvent]: ...
    async def complete(self, model: str, ctx: LLMContext, signal: AbortSignal) -> CompleteResult: ...

class OpenAICompatibleProvider(Provider):
    """复用现有 from openai import OpenAI"""
    def __init__(self, config: ProviderConfig):
        self._client = OpenAI(api_key=config.api_key, base_url=config.base_url)
        ...
```

#### 流式事件类型

```python
# backend/app/ai/stream.py
class StreamEventType(str, Enum):
    START = "start"
    TEXT_START = "text_start"
    TEXT_DELTA = "text_delta"
    TEXT_END = "text_end"
    THINKING_START = "thinking_start"
    THINKING_DELTA = "thinking_delta"
    THINKING_END = "thinking_end"
    TOOLCALL_START = "toolcall_start"
    TOOLCALL_DELTA = "toolcall_delta"
    TOOLCALL_END = "toolcall_end"
    DONE = "done"
    ERROR = "error"
```

#### Type schema（pydantic 实现 TypeBox 等价）

```python
# backend/app/ai/tool.py
class Type:
    @staticmethod
    def Object(properties: dict, required: list[str] = None) -> dict: ...
    @staticmethod
    def String() -> dict: ...
    @staticmethod
    def Optional(t: dict) -> dict: ...
    # 转换为 JSON Schema 给 OpenAI tools 参数

class Tool(BaseModel):
    name: str
    label: str | None = None
    description: str
    parameters: dict  # JSON Schema
    execution_mode: Literal["parallel", "serial"] = "serial"
    execute: Callable  # async (call_id, params, signal, on_update) -> ToolResult
```

### B.15 依赖关系

| 依赖项 | 版本 | 用途 | 新增/修改 |
| --- | --- | --- | --- |
| openai | 已有 | OpenAICompatibleProvider | 已用 |
| pydantic | 已有 | Type schema + 参数校验 | 已用 |
| asyncio | 标准库 | 流式 + AbortSignal | 已用 |

无新增依赖。

### B.16 测试命令

```bash
# 单元测试
pytest backend/tests/ai/ -v

# 双写对比（迁移质量门禁）
pytest backend/tests/ai/test_provider_compat.py -v

# 后端契约
pytest backend/tests/test_chat_*.py backend/tests/test_core_mcp_generation_tools.py backend/tests/test_core_task_status_contracts.py -v

# 前端契约
cd frontend && pnpm test:contracts

# 构建
cd frontend && pnpm build

# 核心回归
scripts/run_core_regression.sh

# 桌面验证
packaging/build-backend-macos.sh && open packaging/output/NoteMeld.app

# 手动
python3 scripts/run_notemeld.sh
# 浏览器：粘贴视频链接生成 1 篇笔记 + 会话页聊天 1 次
```

### B.17 验证方式

- [x] 功能验证：B.16 单测 + 双写对比
- [x] 回归验证：B.16 契约 + 核心回归
- [x] 性能验证：单次 LLM 调用 P95 ≤ 旧 + 20ms（pytest benchmark）
- [x] 真机验证：桌面 sidecar 启动 + 1 次端到端笔记生成

---

## 执行顺序总结

按 A.1 任务号 T1 → T14 顺序执行。每个任务完成后跑对应测试，全部绿后进下一个任务。T9-T11 迁移调用点时，每迁移一个就跑一次双写对比（T8）+ 核心回归，确保不破坏。

**用户确认本 Spec 后即可开始执行 T1。**
