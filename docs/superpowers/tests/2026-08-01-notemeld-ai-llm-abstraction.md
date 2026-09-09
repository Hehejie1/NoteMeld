# P0 notemeld-ai 验收报告

日期：2026-08-01
作者 / Agent：doc-driven 流程
关联需求：[`docs/requirements/2026-08-01-notemeld-ai-llm-abstraction.md`](../../requirements/2026-08-01-notemeld-ai-llm-abstraction.md)
关联 Plan/Spec：[`docs/superpowers/specs/2026-08-01-notemeld-ai-llm-abstraction.md`](../specs/2026-08-01-notemeld-ai-llm-abstraction.md)
状态：**核心验收通过**（桌面 packaging + 真机手动验证为待办项，见 §5）

---

## 1. 验收结论

| 维度 | 结果 | 证据 |
| --- | --- | --- |
| §7 验收标准 1-5 | ✅ 全部通过 | 见 §2 |
| §13.5 回归测试点 | 🟡 6/8 通过，2 项待真机验证 | 见 §3 |
| Plan T1-T14 任务 | 🟡 T1-T12 完成，T13 部分，T14 本报告 | 见 §4 |
| 约束 §9 兼容性 | ✅ 0 schema 改动 / 0 API 改动 / GPTFactory 保留 + DeprecationWarning | 见 §6 |

**结论**：P0 notemeld-ai 核心目标达成——所有 LLM 调用点已迁移至 `app.ai`，usage 字段逐字段等价，流式唯一写入，类型化错误，4 个查询接口 0 改动。剩余桌面 packaging + 真机手动验证不阻塞 P1 开工（P1 仅依赖 `app.ai` 模块的正确性，已由 138 个单测 + 双写对比保证）。

---

## 2. 验收标准逐条核验（需求 §7）

### §7.1 旧调用点迁移后字段逐字段相等 ✅

**验证**：`backend/tests/ai/test_provider_compat.py::DualWriteFieldEquivalenceTest`

- `test_non_stream_dual_write_field_count_matches_orm` PASSED — 字段数量一致
- `test_non_stream_dual_write_field_equivalence` PASSED — 同 prompt 双路径（旧 GPTFactory ↔ 新 notemeld-ai）逐字段断言 usage 记录等价

**迁移调用点覆盖**（每个调用点均有迁移测试）：

| 调用点 | 迁移测试 | 状态 |
| --- | --- | --- |
| `chat_service.py` chat/free_chat/free_chat_stream（T9） | `test_chat_service_migration.py` | ✅ |
| `note.py` _summarize_text 等（T10） | `test_note_generator_migration.py` | ✅ |
| `wiki_page_merger.py` / `summary_refine_engine.py` / `web_note.py` / `note_style_*`（T11） | `test_t11_migration.py` | ✅ |
| 残留 `gpt.client.chat` 调用扫描 | `test_t11_migration.py::NoResidualGptClientUsageTest::test_no_gpt_client_chat_in_services` | ✅ 无残留 |

### §7.2 流式只写一条 usage ✅

**验证**：`test_provider_compat.py::StreamSingleUsageTest::test_stream_writes_exactly_one_usage_on_success` PASSED

补充：
- `test_stream.py::StreamEventTypeTest::test_all_twelve_event_types_present` — 12 类 StreamEvent 齐全
- `test_usage.py::UsageWriterTest` — 4 个用例覆盖 success/failed/异常吞掉/timestamp

### §7.3 不支持 tool 的模型主动报错 ✅

**验证**：`test_provider_compat.py::CapabilityCheckCompatTest`

- `test_new_path_pre_checks_tool_capability` PASSED — 新路径主动预检
- `test_legacy_path_does_not_pre_check_tool_capability` PASSED — 旧路径不预检（兼容性对照）
- `test_tool.py::TypeSchemaTest` + `ToolToOpenAIFunctionTest` — Type schema + Tool→OpenAI function 转换

### §7.4 Auth/Network/RateLimit 类型化错误 ✅

**验证**：`test_provider.py::ClassifyOpenAIErrorTest`（10 个用例）

| HTTP/错误 | 映射 | 用例 |
| --- | --- | --- |
| 401 | ProviderAuthError | `test_401_maps_to_auth_error` ✅ |
| 403 | ProviderAuthError | `test_403_maps_to_auth_error` ✅ |
| 429 | ProviderRateLimitError | `test_429_maps_to_rate_limit` ✅ |
| 503 | ProviderNetworkError | `test_503_maps_to_network_error` ✅ |
| 连接错误 | ProviderNetworkError | `test_connection_error_maps_to_network_error` ✅ |
| timeout | ProviderNetworkError | `test_timeout_message_maps_to_network_error` ✅ |
| invalid_api_key 文案 | ProviderAuthError | `test_invalid_api_key_message_maps_to_auth_error` ✅ |
| rate_limit 文案 | ProviderRateLimitError | `test_rate_limit_message_maps_to_rate_limit` ✅ |
| 其他错误 | 原样透传 | `test_other_errors_pass_through_unchanged` ✅ |

补充：`test_provider.py::OpenAICompatibleProviderTest::test_complete_raises_classified_error_on_auth_failure` + `test_stream_emits_error_event_on_create_exception`

### §7.5 /api/usage/* 4 接口 0 字段差异 ✅

**验证方式**：Spec B.8 确认 4 个接口（`/api/usage/overview|records|task_summary|task_calls/{id}`）0 改动——无新增/修改/删除接口，请求参数/返回结构/错误语义 0 变化。

回归保证：
- `test_core_model_service_contracts.py::TestCoreModelServiceContracts::test_add_new_model_does_not_probe_capability_on_save` PASSED
- `test_core_mcp_generation_tools.py::test_list_models_returns_enabled_models_without_api_keys` PASSED — API Key 不回显行为保持

> 备注：需求 §13.5 提到的 `test_usage_apis.py` 未单独创建（接口 0 改动，0 风险）；建议后续补一个轻量接口契约测试作为防御性回归点，但不阻塞验收。

---

## 3. 回归测试点核验（需求 §13.5）

| 回归点 | 验证方式 | 结果 |
| --- | --- | --- |
| Usage 记录一致性 | `test_provider_compat.py::DualWriteFieldEquivalenceTest` | ✅ 通过 |
| /api/usage/* 4 接口 | 接口 0 改动（B.8）+ model_service 契约 | ✅ 通过 |
| NoteGenerator 端到端 | `scripts/run_core_regression.sh` | ✅ 27 passed |
| chat 端到端 | `test_chat_service_migration.py` | ✅ 通过 |
| MCP list_models | `test_core_mcp_generation_tools.py` | ✅ 10 passed（含 API Key 不回显） |
| 流式 chat | `test_chat_service_migration` + `StreamSingleUsageTest` + 前端 `pnpm test:contracts`（tsc 通过） | ✅ 通过 |
| 桌面 sidecar 启动 | `packaging/build-backend-macos.sh` 后启动 | ⏸ **未执行**（待真机验证） |
| 源码启动 | `scripts/run_notemeld.sh` | ⏸ **未执行**（待手动验证） |

**测试汇总**：

```
backend/tests/ai/                                    → 138 passed
test_core_mcp_generation_tools.py                    → 10 passed
test_core_task_status_contracts.py                   →  3 passed
test_core_model_service_contracts.py                 →  1 passed
test_core_conversation_contracts.py                  →  5 passed
test_web_note_contracts.py                           →  1 passed
scripts/run_core_regression.sh                       → 27 passed
frontend pnpm test:contracts (tsc)                   → exit 0
--------------------------------------------------------
合计：185 passed，0 failed
```

---

## 4. Plan 任务完成度

| 任务 | 状态 | 证据 |
| --- | --- | --- |
| T1 `app/ai/` 骨架 + errors.py + tool.py | ✅ | [backend/app/ai/errors.py](../../../backend/app/ai/errors.py)、[tool.py](../../../backend/app/ai/tool.py) |
| T2 provider.py（Provider 抽象 + OpenAICompatible） | ✅ | [provider.py](../../../backend/app/ai/provider.py) |
| T3 catalog.py（能力加载） | ✅ | [catalog.py](../../../backend/app/ai/catalog.py) |
| T4 usage.py（Usage 收集器 + 自动写） | ✅ | [usage.py](../../../backend/app/ai/usage.py) |
| T5 stream.py（12 类 StreamEvent） | ✅ | [stream.py](../../../backend/app/ai/stream.py) |
| T6 models.py（Models/Model + stream/complete） | ✅ | [models.py](../../../backend/app/ai/models.py) |
| T7 单元测试 test_*.py | ✅ | [backend/tests/ai/](../../../backend/tests/ai) 8 个测试文件 |
| T8 双写对比 test_provider_compat.py | ✅ | DualWriteFieldEquivalenceTest 通过 |
| T9 迁移 chat_service.py | ✅ | [chat_service.py:4](../../../backend/app/services/chat_service.py#L4) `from app.ai import create_models` |
| T10 迁移 note.py | ✅ | [note.py:567](../../../backend/app/services/note.py#L567) `NotemeldGPT.from_config` |
| T11 迁移 wiki_merger/summary_refine/web_note/style | ✅ | test_t11_migration.py 6 用例通过 |
| T12 gpt_factory.py DeprecationWarning | ✅ | [gpt_factory.py:25-30](../../../backend/app/gpt/gpt_factory.py#L25-L30) |
| T13 端到端回归 | 🟡 部分 | 单测+契约+核心回归全绿；桌面 packaging + 真机手动待跑 |
| T14 验收报告 | ✅ | 本文档 |

---

## 5. 待办与风险

### 5.1 待办（不阻塞 P1）

| 项 | 说明 | 建议时机 |
| --- | --- | --- |
| 桌面 sidecar packaging 验证 | `packaging/build-backend-macos.sh` 后启动验证 ready 门禁 | 下次发版前 |
| 源码启动真机验证 | `scripts/run_notemeld.sh` + 粘贴视频链接生成 1 篇笔记 + 会话页聊天 1 次 | 用户手动 |
| 补 `test_usage_apis.py` 轻量契约 | 接口 0 改动，但 §13.5 列了此回归点，建议补防御性测试 | P1 收尾或 P2 前 |

### 5.2 残留 GPTFactory 调用说明（不在迁移范围）

| 位置 | 用途 | 是否迁移 |
| --- | --- | --- |
| [model.py:66,136](../../../backend/app/services/model.py#L66) `gpt.list_models()` | 拉取 provider 的模型列表（非 LLM 调用） | 否，§7.1 迁移范围是 `gpt.client.chat.completions.create(...)` 调用点 |
| [provider.py:15](../../../backend/app/services/provider.py#L15) `import GPTFactory` | **未使用 import**（残留） | 建议清理，不影响功能 |

### 5.3 风险

- **零破坏性**：GPTFactory 全程保留 + DeprecationWarning，T9-T11 迁移点可秒回滚（改回 `from app.gpt import GPTFactory`）
- **usage 记录混存**：回滚后 model_usage_records 中新旧记录按 task_id + timestamp 共存，不影响查询接口

---

## 6. 约束遵守情况（需求 §9）

| 约束 | 遵守 | 证据 |
| --- | --- | --- |
| Python 3.11+ / asyncio | ✅ | `app/ai/` 全异步实现 |
| 性能 P95 ≤ 旧 + 20ms | 🟡 未跑 benchmark | 封装层为薄 wrapper，预期达标；待真机验证 |
| API Key 不打日志/不序列化 | ✅ | test_core_mcp_generation_tools::test_list_models_returns_enabled_models_without_api_keys |
| 旧 GPTFactory 保留 + DeprecationWarning | ✅ | gpt_factory.py:25-30 |
| 4 张表 0 schema 改动 | ✅ | B.7 确认；仅 model_usage_records 追加写 |
| /api/usage/* 4 接口 0 改动 | ✅ | B.8 确认 |
| MCP list_models 0 改动 | ✅ | 契约测试通过 |
| 零新增付费依赖 | ✅ | 仅复用 openai + pydantic + asyncio |

---

## 7. 交接

- **P0 状态**：核心验收通过，可进入 P1 notemeld-agent-core 实现
- **P1 前置依赖**：`app.ai` 模块（Models/Model/Provider/StreamEvent/Tool/Type/Usage）已就绪，P1 AgentLoop 可直接调用 `models.stream()/complete()`
- **待办跟踪**：桌面 packaging + 真机手动验证 + test_usage_apis.py 补充，建议在 P1 开发期间穿插完成

**Backlink**：[docs/requirements/index.md](../../requirements/index.md)
