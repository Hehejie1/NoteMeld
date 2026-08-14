# 模型上下文与能力感知分块 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将模型添加改为携带上下文、图像和流式能力的居中弹窗，并让笔记、聊天和视频 OCR 路径统一消费当前所选模型保存的运行配置。

**Architecture:** `models` 成为用户确认的模型运行配置权威表，`model_capabilities` 继续只做自动探测缓存；本地 JSON 目录只给添加弹窗提供建议，未命中回退 4096。统一 token budget 在 notemeld-ai 和 UniversalGPT 两条调用路径生效，视频分帧依据 `supports_vision` 在视觉模型和 OCR 之间路由。

**Tech Stack:** FastAPI、Pydantic、SQLAlchemy/SQLite、React 19、TypeScript、Zustand、Radix Dialog、Python unittest/pytest、Node contract tests。

## Global Constraints

- 只允许清空旧 `models` 和 `model_capabilities` 配置；不得删除 `providers`、`note_documents`、会话、任务、转写、Wiki、媒体缓存或 `model_usage_records`。
- `context_window_tokens` 必须在 512–4,000,000；目录未命中使用 4096。
- 用户在添加弹窗保存的值是运行时权威值，本地目录升级不得覆盖。
- `supports_vision=false` 且开启截图时直接 OCR，不先请求视觉模型，也不向总结模型发送图片。
- `supports_stream=false` 时保持现有 SSE 协议，通过非流式 complete 适配输出。
- token 预算与现有 request byte 预算同时生效；不新增重型 tokenizer 依赖。
- map 阶段不重复注入 final-stage 视觉/搜索上下文；空 OCR 占位不得进入 prompt。
- API 保持 `{code,msg,data}` wrapper；不得记录 API Key、完整 prompt 或图片 base64。
- 不提供模型编辑弹窗；配置变更通过删除后重新添加完成。

---

## File Map

### New files

- `backend/app/db/model_schema.py`：幂等升级 `models` schema，并限制一次性清空范围。
- `backend/app/resources/model_runtime_catalog.json`：随应用发布的常见模型建议目录。
- `backend/app/services/model_runtime_catalog.py`：目录加载、规范化匹配和 4096 fallback。
- `backend/app/gpt/token_budget.py`：统一 token 估算、预算计算和消息裁剪。
- `backend/tests/test_model_runtime_schema.py`：schema 清空边界与笔记保留测试。
- `backend/tests/test_model_runtime_catalog.py`：目录匹配和 fallback 测试。
- `backend/tests/test_model_runtime_api.py`：添加/列表/删除模型配置 API 测试。
- `backend/tests/test_token_budget.py`：预算计算和聊天裁剪测试。
- `frontend/src/components/Form/modelForm/AddModelDialog.tsx`：居中添加模型弹窗。
- `frontend/tests/modelRuntimeConfigContracts.test.mjs`：模型 UI 和请求 payload 契约。
- `docs/superpowers/tests/2026-08-13-model-context-capability-aware-chunking.md`：最终验证证据。

### Modified files

- `backend/app/db/models/models.py`、`backend/app/db/model_dao.py`、`backend/app/db/init_db.py`
- `backend/app/models/model_config.py`
- `backend/app/services/model.py`、`backend/app/routers/model.py`
- `backend/app/ai/catalog.py`、`backend/app/ai/models.py`
- `backend/app/gpt/notemeld_gpt.py`、`backend/app/gpt/universal_gpt.py`、`backend/app/gpt/request_chunker.py`、`backend/app/gpt/provider_runtime.py`
- `backend/app/services/chat_service.py`、`backend/app/agent/core/loop.py`
- `backend/app/services/note.py`、`backend/app/services/summary_refine_engine.py`、`backend/app/services/context_normalizer.py`
- `backend/app/services/multisource_video_collector.py`、`backend/app/services/video_frame_collector.py`
- `frontend/src/components/Form/modelForm/Form.tsx`、`frontend/src/components/Form/modelForm/ModelSelector.tsx`
- `frontend/src/services/model.ts`、`frontend/src/store/modelStore/index.ts`
- `packaging/backend/pyinstaller/backend.spec`（只添加 JSON data）
- `backend/tests/ai/test_models.py`、`backend/tests/ai/test_provider_compat.py`、`backend/tests/ai/test_note_generator_migration.py`
- `backend/tests/test_multisource_summary_contracts.py`、`backend/tests/test_multisource_video_collector_contracts.py`
- `docs/system/current-architecture.md`、`docs/system/product-rules.md`、`docs/system/data-model.md`、`docs/system/api-inventory.md`、`docs/system/known-pitfalls.md`

---

### Task 1: 模型运行配置 schema 与受控清空

**Files:**
- Create: `backend/app/db/model_schema.py`
- Create: `backend/tests/test_model_runtime_schema.py`
- Modify: `backend/app/db/models/models.py`
- Modify: `backend/app/db/model_dao.py`
- Modify: `backend/app/db/init_db.py`

**Interfaces:**
- Produces: `ensure_model_runtime_schema(engine) -> dict[str, object]`
- Produces: `get_model_by_provider_and_name(provider_id: str, model_name: str) -> dict | None` 返回三个运行字段
- Produces: `insert_model(..., context_window_tokens: int, supports_vision: bool, supports_stream: bool) -> dict`
- Produces: `delete_model(model_id: int) -> dict | None`，供 service 同步删能力缓存

- [ ] **Step 1: 写失败测试，证明升级只清模型配置**

在临时 SQLite 创建旧 `models`、`model_capabilities`、`providers`、`note_documents`、`conversations`、`conversation_messages`、`model_usage_records` 并各插入一行。调用 `ensure_model_runtime_schema(engine)` 后断言：

```python
assert columns("models") >= {
    "context_window_tokens", "supports_vision", "supports_stream"
}
assert count("models") == 0
assert count("model_capabilities") == 0
assert count("providers") == 1
assert count("note_documents") == 1
assert count("conversations") == 1
assert count("conversation_messages") == 1
assert count("model_usage_records") == 1
```

同一数据库第二次调用后插入的新模型仍存在，证明 ensure 幂等且不会重复清空。

- [ ] **Step 2: 运行失败测试**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_model_runtime_schema.py -q`

Expected: FAIL，原因是 `model_schema` 不存在或字段缺失。

- [ ] **Step 3: 实现最小 schema ensure**

`models.py` 增加三个 `nullable=False` 字段。`ensure_model_runtime_schema()` 使用 SQLAlchemy inspector 判断缺列；SQLite 用 `ALTER TABLE` 增加带安全默认值的列，再在同一事务定向清空两张模型表。返回：

```python
{
    "upgraded": True,
    "cleared_models": model_count,
    "cleared_capabilities": capability_count,
}
```

结构完整时返回 `upgraded=False`。`init_db()` 在 `create_all()` 后调用并记录计数日志。

- [ ] **Step 4: 扩展 DAO 并验证**

所有模型读取返回三个字段；插入函数要求显式值；删除函数返回被删除模型身份。运行：

`PYTHONPATH=backend python3 -m pytest backend/tests/test_model_runtime_schema.py backend/tests/test_core_model_service_contracts.py -q`

Expected: PASS。

- [ ] **Step 5: 检查迁移文件无越界删除**

Run: `rg -n "DELETE FROM|drop_all|DROP TABLE" backend/app/db/model_schema.py`

Expected: 只出现 `models` 和 `model_capabilities`。

### Task 2: 本地常见模型目录和默认解析 API

**Files:**
- Create: `backend/app/resources/model_runtime_catalog.json`
- Create: `backend/app/services/model_runtime_catalog.py`
- Create: `backend/tests/test_model_runtime_catalog.py`
- Modify: `backend/app/routers/model.py`
- Modify: `packaging/backend/pyinstaller/backend.spec`

**Interfaces:**
- Produces: `ModelRuntimeDefaults` dataclass
- Produces: `resolve_model_runtime_defaults(model_name: str) -> ModelRuntimeDefaults`
- Produces: `POST /api/models/defaults`

- [ ] **Step 1: 写目录解析失败测试**

覆盖：精确匹配优先、`deepseek-r1:*` 家族匹配、`qwen2.5vl:*` 图像能力、名称大小写/空格规范化、未知模型 4096 fallback、损坏 JSON fallback。

```python
defaults = resolve_model_runtime_defaults(" company/custom-model ")
assert defaults.context_window_tokens == 4096
assert defaults.supports_vision is False
assert defaults.supports_stream is True
assert defaults.source == "fallback"
```

- [ ] **Step 2: 运行失败测试**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_model_runtime_catalog.py -q`

Expected: FAIL，resolver 不存在。

- [ ] **Step 3: 创建版本化 JSON 目录并实现解析**

JSON 顶层包含 `version`、`fallback`、`models`。实现一次加载缓存、精确优先、按顺序 fnmatch；读取失败只 warning，不抛出。首批规则使用设计 Spec §6 清单。

- [ ] **Step 4: 新增 defaults API 契约测试并实现**

请求模型名为空返回 wrapper code 400；有效名称返回完整来源信息。运行：

`PYTHONPATH=backend python3 -m pytest backend/tests/test_model_runtime_catalog.py -q`

Expected: PASS。

- [ ] **Step 5: 验证打包资源被收集**

新增/更新现有打包契约测试，断言构建配置包含 `model_runtime_catalog.json`。运行对应 packaging contract test，Expected: PASS。

### Task 3: 模型添加、列表、删除 API

**Files:**
- Create: `backend/tests/test_model_runtime_api.py`
- Modify: `backend/app/routers/model.py`
- Modify: `backend/app/services/model.py`
- Modify: `backend/app/db/model_dao.py`
- Modify: `backend/app/db/model_capability_dao.py`

**Interfaces:**
- Consumes: Task 1 `insert_model`/完整模型行
- Produces: `ModelService.add_new_model(provider_id, model_name, context_window_tokens, supports_vision, supports_stream) -> dict`
- Produces: `ModelService.get_saved_model(provider_id, model_name) -> dict | None`
- Produces: 更新后的 `POST /api/models` 与模型列表响应

- [ ] **Step 1: 写 API 失败测试**

覆盖上下文 511/4,000,001 拒绝、缺少 bool 字段拒绝、Provider 不存在、重复模型 code 409、成功响应含完整行、列表字段完整、删除模型同步删对应 capability 但笔记行保留。

- [ ] **Step 2: 运行失败测试**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_model_runtime_api.py -q`

Expected: FAIL，旧 CreateModelRequest 不含字段。

- [ ] **Step 3: 实现 Pydantic 请求和 service 返回值**

使用 `Field(ge=512, le=4_000_000)`；`supports_vision`、`supports_stream` 不设默认。service 禁止吞异常或用 bool 模糊表示失败，返回完整模型 dict；router 根据明确异常映射 400/404/409。

- [ ] **Step 4: 删除能力缓存并运行测试**

DAO 新增 `delete_model_capability(provider_id, model_name)`。只删探测缓存，不删除 usage/note。运行：

`PYTHONPATH=backend python3 -m pytest backend/tests/test_model_runtime_api.py backend/tests/test_core_model_service_contracts.py -q`

Expected: PASS。

### Task 4: 居中“添加模型”弹窗

**Files:**
- Create: `frontend/src/components/Form/modelForm/AddModelDialog.tsx`
- Create: `frontend/tests/modelRuntimeConfigContracts.test.mjs`
- Modify: `frontend/src/components/Form/modelForm/Form.tsx`
- Modify: `frontend/src/components/Form/modelForm/ModelSelector.tsx`
- Modify: `frontend/src/services/model.ts`
- Modify: `frontend/src/store/modelStore/index.ts`

**Interfaces:**
- Produces: `AddModelDialog({providerId, open, onOpenChange, onSaved})`
- Produces: `fetchModelDefaults(modelName)`
- Produces: `addModel(ModelRuntimeConfigPayload)`

- [ ] **Step 1: 写前端静态契约失败测试**

断言：Provider form 不再渲染内联 `ModelSelector`；标题右侧包含“添加模型”；Dialog 包含模型、上下文长度、支持图像、支持流式；保存 payload 包含五个字段；成功调用 `onSaved`；失败不关闭。

- [ ] **Step 2: 运行失败测试**

Run: `cd frontend && node --test tests/modelRuntimeConfigContracts.test.mjs`

Expected: FAIL，AddModelDialog 不存在。

- [ ] **Step 3: 实现弹窗与 defaults 异步保护**

复用 `Dialog`、`Select`、`Input`、`Switch`。以递增 request id 或 AbortController 防止旧 defaults 响应覆盖新模型选择；用户改动字段后记录 dirty，不被同一模型迟到响应覆盖。

- [ ] **Step 4: 简化 ModelSelector 职责**

将它改成弹窗内部的纯模型选择控件，删除组件内部保存按钮和 `addNewModel` 调用。Provider form 仅管理 Dialog open 和刷新已添加模型。

- [ ] **Step 5: 更新类型/store 并运行契约**

`IModelListItem` 增加三个字段；`addNewModel` 接收完整 payload 并返回模型行。运行：

```bash
cd frontend
node --test tests/modelRuntimeConfigContracts.test.mjs
pnpm test:contracts
```

Expected: PASS。

### Task 5: 统一运行时模型配置与非流式降级

**Files:**
- Modify: `backend/app/models/model_config.py`
- Modify: `backend/app/ai/catalog.py`
- Modify: `backend/app/ai/models.py`
- Modify: `backend/app/gpt/notemeld_gpt.py`
- Modify: `backend/app/services/note.py`
- Modify: `backend/tests/ai/test_models.py`
- Modify: `backend/tests/ai/test_provider_compat.py`

**Interfaces:**
- Consumes: Task 3 `ModelService.get_saved_model`
- Produces: `Model.context_window_tokens: int`
- Produces: `Model.supports_vision: bool`
- Produces: `Model.supports_stream: bool`
- Produces: `ModelConfig` 同名字段

- [ ] **Step 1: 写模型解析失败测试**

断言未添加模型时 `Models.get_model()` 返回 None；已添加模型将三个字段装载到 Model；`CapabilityCatalog.supports_vision=True` 不能覆盖保存的 false。

- [ ] **Step 2: 写非流式降级失败测试**

Fake provider 统计调用次数：`supports_stream=false` 时 provider.stream 为 0、provider.complete 为 1；事件顺序至少为 `TEXT_DELTA, DONE`，usage 只写一次；带 tool_calls 的 complete 需转成 TOOLCALL_START/END 后 DONE。

- [ ] **Step 3: 运行失败测试**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/ai/test_models.py backend/tests/ai/test_provider_compat.py -q`

Expected: FAIL，Model 无运行配置且 stream 总调用 Provider stream。

- [ ] **Step 4: 实现配置装载和流式适配**

`Models.get_model()` 先查保存模型行；构造 Model 时以保存的 vision 为权威。`Models.stream()` 在非流式模型分支调用 complete，并规范化文本/tool events；复用同一 usage context，避免 complete 与 stream 双写。

- [ ] **Step 5: 透传到 NotemeldGPT/UniversalGPT**

`NoteGenerator._get_gpt()` 读取保存模型行构造 `ModelConfig`；`NotemeldGPT.from_config()` 将三个字段传给父类。运行上一步测试，Expected: PASS。

### Task 6: Token budget、聊天裁剪和双预算 RequestChunker

**Files:**
- Create: `backend/app/gpt/token_budget.py`
- Create: `backend/tests/test_token_budget.py`
- Modify: `backend/app/ai/models.py`
- Modify: `backend/app/gpt/universal_gpt.py`
- Modify: `backend/app/gpt/request_chunker.py`
- Modify: `backend/app/services/chat_service.py`
- Modify: `backend/app/agent/core/loop.py`
- Modify: `backend/tests/ai/test_chat_service_migration.py`
- Modify: `backend/tests/ai/test_note_generator_migration.py`

**Interfaces:**
- Produces: `build_token_budget(context_window_tokens: int, image_count: int = 0) -> TokenBudget`
- Produces: `estimate_messages_tokens(messages: list[dict]) -> int`
- Produces: `trim_messages_to_budget(messages, budget, tools=None) -> list[dict]`
- Extends: `RequestChunker(..., max_tokens: int | None, token_estimator: Callable | None)`

- [ ] **Step 1: 写预算公式和消息裁剪失败测试**

断言 4096 预算的 output/safety/input 与 Spec 公式一致；system 和最新 user 必留；从最旧普通 history 删除；assistant tool_calls 与对应 tool messages 成组删除；单条最新 user 超限抛明确异常。

- [ ] **Step 2: 写 RequestChunker 双预算失败测试**

构造“字节数低于 45MB、token 估算高于模型预算”的消息，断言会继续拆分；同时断言字节超限仍拆分。

- [ ] **Step 3: 运行失败测试**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests/test_token_budget.py backend/tests/ai/test_note_generator_migration.py -q`

Expected: FAIL，token budget 模块不存在。

- [ ] **Step 4: 实现纯 Python 保守估算和裁剪**

文本估算为 `ceil(len(text.encode("utf-8"))/3)`，每 message 增加固定 overhead，图片使用预算器 reserve。裁剪函数不改变传入列表，并验证 tool 对完整性。

- [ ] **Step 5: 接入 Models 和 UniversalGPT**

`Models.stream/complete` 在调用 Provider 前裁剪 `LLMContext` 副本；UniversalGPT 的 chunker 使用模型输入预算。日志只记录预算数值。

- [ ] **Step 6: 运行定向测试**

```bash
PYTHONPATH=backend python3 -m pytest \
  backend/tests/test_token_budget.py \
  backend/tests/ai/test_chat_service_migration.py \
  backend/tests/ai/test_note_generator_migration.py -q
```

Expected: PASS。

### Task 7: 笔记 map/final 边界、上下文重试与 OCR 直达

**Files:**
- Modify: `backend/app/services/note.py`
- Modify: `backend/app/services/context_normalizer.py`
- Modify: `backend/app/services/summary_refine_engine.py`
- Modify: `backend/app/services/multisource_video_collector.py`
- Modify: `backend/app/services/video_frame_collector.py`
- Modify: `backend/app/gpt/universal_gpt.py`
- Modify: `backend/app/gpt/provider_runtime.py`
- Modify: `backend/tests/test_multisource_summary_contracts.py`
- Modify: `backend/tests/test_multisource_video_collector_contracts.py`
- Modify: `backend/tests/ai/test_note_generator_migration.py`
- Modify: `backend/tests/test_core_note_task_status_api.py`

**Interfaces:**
- Consumes: `gpt.supports_vision` 和 Task 6 token budget
- Extends: `VideoFrameCollector.collect(..., allow_vision: bool = True)`
- Extends: `MultiSourceVideoCollector.collect(..., allow_vision: bool)`
- Produces: `is_context_limit_error(exc) -> bool`

- [ ] **Step 1: 写 OCR 直达和空 OCR 失败测试**

`allow_vision=False` 时 fake vision analyzer 调用次数为 0、OCR 被调用；输出无 grid image payload。OCR 返回空文本时 frame content 为空且 `_merge_multisource_extras` 不产生“视频画面补充上下文”。

- [ ] **Step 2: 写 map/final 隔离失败测试**

给 bundle 提供巨大 frame/search content；捕获 map 的 GPTSource，断言 extras 只含用户原始要求和 map 指令；final extras 才含有效 frame/search。

- [ ] **Step 3: 写 6492/4096 回归测试**

Fake GPT 第一次抛出包含 `exceed_context_size_error`、`n_prompt_tokens=6492`、`n_ctx=4096` 的异常；断言系统按 70% 输入预算重新分块一次并成功，checkpoint/采集缓存未删除。

- [ ] **Step 4: 运行失败测试**

```bash
PYTHONPATH=backend python3 -m pytest \
  backend/tests/test_multisource_summary_contracts.py \
  backend/tests/test_multisource_video_collector_contracts.py \
  backend/tests/ai/test_note_generator_migration.py -q
```

Expected: FAIL，当前仍重复 extras 且未识别上下文错误。

- [ ] **Step 5: 实现上下文分层和 OCR 过滤**

保留 `original_user_extras`；collector 结果进入 `SummaryInput.user_options` 的独立字段。`_format_content()` 跳过空 summary；frame content 为空时整个 vision block 不创建。

- [ ] **Step 6: 实现上下文错误分类和一次重分块**

统一识别 `exceed_context_size_error`、`available context size`、`n_ctx`、`maximum context length`。只重试一次，预算乘 0.7；第二次失败使用安全中文错误。保留已有 checkpoint 和 sidecar。

- [ ] **Step 7: 验证笔记保存边界**

增加测试：模型配置清空后历史 `note_documents` 仍可经 API 读取；重新添加模型后新 NoteResult 仍写入 markdown、conversation 和 note document。运行 Task 7 测试，Expected: PASS。

### Task 8: 文档同步和完整验证

**Files:**
- Modify: `docs/requirements/2026-08-13-model-context-capability-aware-chunking.md`
- Modify: `docs/requirements/index.md`
- Modify: `docs/system/current-architecture.md`
- Modify: `docs/system/product-rules.md`
- Modify: `docs/system/data-model.md`
- Modify: `docs/system/api-inventory.md`
- Modify: `docs/system/known-pitfalls.md`
- Create: `docs/superpowers/tests/2026-08-13-model-context-capability-aware-chunking.md`

**Interfaces:**
- Consumes: Tasks 1–7 的实际字段、接口和测试结果
- Produces: 可审计的最终验证证据

- [ ] **Step 1: 更新系统长期事实**

记录 `models` 权威字段、一次性清空边界、目录/fallback 规则、API 请求/响应、token/byte 双预算、OCR 直达和 non-stream SSE 适配。known pitfall 必须明确禁止“只改 UI 不接运行时”和“用理论窗口覆盖端点实际值”。

- [ ] **Step 2: 运行后端定向测试**

```bash
PYTHONPATH=backend python3 -m pytest \
  backend/tests/test_model_runtime_schema.py \
  backend/tests/test_model_runtime_catalog.py \
  backend/tests/test_model_runtime_api.py \
  backend/tests/test_token_budget.py \
  backend/tests/ai/test_models.py \
  backend/tests/ai/test_provider_compat.py \
  backend/tests/ai/test_chat_service_migration.py \
  backend/tests/ai/test_note_generator_migration.py \
  backend/tests/test_multisource_summary_contracts.py \
  backend/tests/test_multisource_video_collector_contracts.py \
  backend/tests/test_core_note_task_status_api.py -q
```

Expected: 全部 PASS。

- [ ] **Step 3: 运行后端全量单进程测试**

Run: `PYTHONPATH=backend python3 -m pytest backend/tests -q`

Expected: 全部 PASS，不发生 pytest 收集期 stub 污染。

- [ ] **Step 4: 运行前端契约与构建**

```bash
cd frontend
pnpm test:contracts
pnpm build
```

Expected: 全部 PASS，无 TypeScript/Vite 错误。

- [ ] **Step 5: 运行核心回归**

Run: `scripts/run_core_regression.sh`

Expected: PASS；若脚本因外部服务缺失跳过某项，证据文档必须记录具体跳过项，不能写“全部通过”。

- [ ] **Step 6: 手动纵向验收**

1. 打开 Ollama Provider，确认没有内联“保存模型”。
2. 点击“添加模型”，选择 `deepseek-r1:7b`，把上下文改为实际 16384，保存。
3. 重启后确认值仍在数据库并能被模型选择读取。
4. 用 `supports_vision=false` 生成开启截图的视频笔记，日志确认直接 OCR、无 vision call。
5. 用 4096 测试模型重跑原 7.5 分钟任务，确认不再以 6492/4096 首块失败。
6. 打开一篇升级前历史笔记，确认正文完整。

- [ ] **Step 7: 写验证证据并更新状态**

证据文件只写命令、关键结果、失败/跳过原因和需求 backlink。全部必要验证通过后，把 requirement/index 状态改为 `Implemented`；否则保持 `Planned` 并列出未完成验收项。

---

## Plan Self-Review

- Spec coverage：15 条验收标准分别由 Tasks 1–8 覆盖。
- 数据边界：只有 Task 1 允许清空，且测试锁定只清两张模型配置表。
- 类型一致性：数据库、API、前端和运行时统一使用 `context_window_tokens`、`supports_vision`、`supports_stream`。
- 运行时闭环：模型保存值进入 Models、NotemeldGPT、聊天预算、笔记分块和 OCR 路由。
- 无占位实现步骤；每个任务均包含失败测试、最小实现和通过命令。
