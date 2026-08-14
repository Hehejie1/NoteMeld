# 模型上下文与能力感知分块设计规格

日期：2026-08-13
状态：Approved for planning
关联需求：`docs/requirements/2026-08-13-model-context-capability-aware-chunking.md`

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已搜索模型设置前端、模型 API、DAO、notemeld-ai、笔记总结、聊天、分帧/OCR和对应测试
- [x] 已确认现有 `models`、`model_capabilities`、`RequestChunker`、`SummaryRefineEngine` 和 `VideoFrameCollector` 可复用
- [x] 已确认影响本地 SQLite 与本地/远端模型请求，不修改线上 Provider 配置

## 1. 当前系统现状

- 相关模块：
  - `frontend/src/components/Form/modelForm/Form.tsx` 同时展示 Provider 表单、内联模型选择/保存和已启用模型标签。
  - `frontend/src/components/Form/modelForm/ModelSelector.tsx` 拉取 Provider 模型列表并直接保存模型。
  - `backend/app/routers/model.py` 提供模型列表、添加、删除和 JSON Mode 探测接口。
  - `backend/app/db/models/models.py` 的 `models` 只存模型身份；`model_capabilities` 存探测缓存。
  - `backend/app/ai/models.py` 创建统一 `Model` 并提供 stream/complete。
  - `backend/app/gpt/universal_gpt.py` 与 `request_chunker.py` 负责笔记请求分块，但只使用 HTTP 字节预算。
  - `backend/app/services/note.py`、`summary_refine_engine.py` 和 `video_frame_collector.py` 负责视频多源上下文、map/final 总结和视觉/OCR降级。
- 相关数据：
  - `models(id, provider_id, model_name, created_at)`。
  - `model_capabilities` 是探测缓存，不是用户确认的端点运行配置。
  - 已生成笔记保存在 `note_documents` 与 `note_results/`，不依赖 `models` 外键。
- 当前限制：模型选择不携带上下文/视觉/流式配置；聊天不按窗口裁剪；笔记分块可能超过 4K；OCR 空占位会膨胀 prompt。

## 2. 本次目标

- 把模型添加改为单一居中弹窗交互。
- 在 `models` 行中保存模型名称、实际上下文长度、图像和流式能力。
- 通过随应用发布的本地目录给出常见模型建议，未命中使用 4096。
- 笔记与聊天统一读取当前选中模型的保存配置。
- 笔记字幕按 token 输入预算分块；聊天按相同预算裁剪历史消息。
- 模型不支持图像时，截图链路直接 OCR；模型不支持流式时，stream API 兼容输出非流式结果。
- 只清空旧模型配置，完整保留笔记及其他用户数据。

## 3. 明确不做

- 不提供模型编辑弹窗；删除后重新添加。
- 不在线更新模型目录，不自动修改 Ollama/vLLM/LM Studio 服务配置。
- 不迁移旧模型配置值；检测到旧 schema 时一次性清空。
- 不删除 Provider、笔记、会话、任务、Wiki、转写、媒体缓存和用量记录。
- 不移除请求字节上限，不引入重型 tokenizer 依赖。
- 不重构无关 Provider、Wiki、Agent 或桌面打包逻辑。

## 4. 方案比较与选择

### 方案 A：全部字段放进 `models`（采用）

- 优点：一行就是用户确认的模型运行配置；添加、列举、删除和运行时读取一致；不会与自动探测缓存互相覆盖。
- 缺点：需要一次 schema 升级并清空旧模型配置。
- 选择原因：用户明确允许重新添加模型，并要求保存到最新数据库字段。

### 方案 B：字段继续放 `model_capabilities`

- 优点：复用现有能力表。
- 缺点：该表当前语义是可过期的探测缓存，用户设置和探测结果会产生两个写入者；上下文长度也不是“探测缓存”。
- 结论：不采用。

### 方案 C：新增 `model_runtime_configs` 表

- 优点：语义最纯。
- 缺点：模型身份与配置分表，没有带来当前规模下的实际收益，增加 join、迁移和删除一致性成本。
- 结论：YAGNI，不采用。

## 5. 数据模型与迁移

### 5.1 `models` 权威字段

```text
id                    INTEGER PRIMARY KEY
provider_id           VARCHAR NOT NULL
model_name            VARCHAR NOT NULL
context_window_tokens INTEGER NOT NULL
supports_vision       BOOLEAN NOT NULL
supports_stream       BOOLEAN NOT NULL
created_at            DATETIME
```

约束：

- `context_window_tokens` API 范围为 512–4,000,000。
- `(provider_id, model_name)` 继续由 service/DAO 保证不重复，本次不为 SQLite 重建唯一约束。
- `supports_vision`、`supports_stream` 是用户确认的端点运行配置，运行时必须使用。
- `model_capabilities` 继续保存 JSON Mode、vision/tool calling 探测缓存；视觉运行决策以 `models.supports_vision` 为准。

### 5.2 一次性 schema ensure

新增 `backend/app/db/model_schema.py::ensure_model_runtime_schema(engine)`：

1. 检查 `models` 是否包含三个新字段。
2. 若字段完整，立即返回，绝不清空。
3. 若任一字段缺失，在单事务中补列并执行：
   - `DELETE FROM model_capabilities`
   - `DELETE FROM models`
4. 不执行任何其他表的 DELETE/UPDATE，不操作 `note_results/`。
5. `init_db()` 在 `Base.metadata.create_all()` 后调用该 ensure。

测试必须在同一个临时数据库中写入 Provider、旧模型、能力、笔记、会话和 usage；升级后只允许模型和能力记录为空。

## 6. 本地模型默认目录

新增：

- `backend/app/resources/model_runtime_catalog.json`
- `backend/app/services/model_runtime_catalog.py`

目录项字段：

```json
{
  "match": "deepseek-r1:*",
  "context_window_tokens": 131072,
  "supports_vision": false,
  "supports_stream": true
}
```

匹配顺序：

1. 规范化后精确名称。
2. `fnmatch` 家族模式，按配置文件顺序取首个。
3. fallback：`4096 / false / true`。

首批至少覆盖：

- `deepseek-r1:*`
- `qwen2.5vl:*`
- `qwen3-vl:*`
- `qwen3:*`
- `qwen2:*`
- `gemma3:*`
- DeepSeek API 常见 `deepseek-chat`、`deepseek-reasoner`
- OpenAI 常见 GPT 系列与兼容别名（只作为建议，用户确认后保存）

返回结构必须包含 `source=catalog|fallback` 和 `matched_rule`，用于前端解释默认来源。目录缺失或损坏时记录 warning 并返回 fallback，不阻断添加模型。

打包脚本必须把 JSON 收入 PyInstaller sidecar；源码模式与打包模式使用统一资源解析 helper。

## 7. API 规格

### 7.1 读取模型建议

`POST /api/models/defaults`

请求：

```json
{"model_name":"deepseek-r1:7b"}
```

响应 `data`：

```json
{
  "model_name":"deepseek-r1:7b",
  "context_window_tokens":131072,
  "supports_vision":false,
  "supports_stream":true,
  "source":"catalog",
  "matched_rule":"deepseek-r1:*"
}
```

### 7.2 添加模型

`POST /api/models`

请求字段全部必填：

```json
{
  "provider_id":"provider-id",
  "model_name":"deepseek-r1:7b",
  "context_window_tokens":16384,
  "supports_vision":false,
  "supports_stream":true
}
```

成功返回新模型完整行。重复模型返回 wrapper `code=409`；字段非法返回 `code=400`。

### 7.3 模型列表

`GET /api/model_list` 与 `GET /api/model_enable/{provider_id}` 的每个已添加模型返回三个新字段。远端 Provider 原始模型列表接口 `GET /api/model_list/{provider_id}` 继续只用于弹窗下拉选择。

### 7.4 删除

保留现有删除接口与已添加模型标签上的删除按钮。删除 `models` 行时同步删除同 provider/model 的 `model_capabilities` 缓存，不能删除笔记。

## 8. 前端交互

### 8.1 Provider 编辑页

- 模型区域标题为“模型列表”。
- 标题右侧显示主按钮“添加模型”。
- 删除当前内联 `ModelSelector`、“刷新模型”和“保存模型”区域。
- 下方继续显示已添加模型标签和删除按钮；标签可附带 `上下文 · 图像/文本 · 流式/非流式` 的简短说明。

### 8.2 添加模型弹窗

新增 `AddModelDialog.tsx`，使用现有 `Dialog`：

- 居中，桌面最大宽度约 560px，窄屏保持 16px 边距。
- 字段：模型下拉、上下文长度数字输入、支持图像 Switch、支持流式 Switch。
- 模型下拉打开/刷新时复用当前 Provider 模型列表 API。
- 选择模型后调用 defaults API 并填充建议；用户修改后不再被同一选择的异步返回覆盖。
- 保存期间禁用控件；成功后关闭弹窗并刷新已添加模型；失败保持打开并显示错误。
- Provider 尚未保存时不显示可用的“添加模型”按钮。

## 9. 运行时模型选择

### 9.1 统一模型对象

`Models.get_model(provider_id, model_name)` 必须先读取 `models` 权威行：

- 未添加模型返回 `None`，不能只因 Provider 存在就构造任意模型。
- `Model` 新增 `context_window_tokens`、`supports_vision`、`supports_stream` 属性。
- `CapabilityCatalog` 的 JSON/tool 探测字段继续合并；`supports_vision` 使用模型保存值覆盖探测缓存。

`ModelConfig` 与 `NotemeldGPT.from_config()` 同步携带三个字段，使旧笔记编排层也能读取相同配置。

### 9.2 流式降级

`Models.stream()`：

- `supports_stream=true`：保持 Provider stream。
- `supports_stream=false`：直接调用 Provider complete，一次性产生一个 `delta` 和一个 `done` 事件。
- usage 只写一次，SSE 上层协议不变。

## 10. 上下文预算与分块

新增 `backend/app/gpt/token_budget.py`：

```python
@dataclass(frozen=True)
class TokenBudget:
    context_window_tokens: int
    output_reserve_tokens: int
    safety_margin_tokens: int
    image_reserve_tokens: int
    max_input_tokens: int
```

默认计算：

```text
output_reserve = min(4096, max(512, context_window * 25%))
safety_margin = max(256, ceil(context_window * 10%))
image_reserve = image_count * 1200
max_input = max(256, context - output_reserve - safety_margin - image_reserve)
```

无 tokenizer 时保守估算：`ceil(len(UTF-8 bytes) / 3) + message overhead`。这不是精确计费，只用于保证不把明显超限请求发送给端点。

### 10.1 笔记

- `UniversalGPT` 从 `ModelConfig` 获得 context window。
- `RequestChunker` 同时满足 `max_request_bytes` 和 `max_input_tokens` 才允许 chunk。
- chunk 大小由 token 预算动态决定，不再以固定 80 段作为真正上限；`SummaryPlanner` 的 80 段只作为初始软分组。
- 收到上下文超限错误时，识别为可降级错误，使用原预算 70% 重新分块一次。
- 失败时保留 transcript/frame 等采集缓存。

### 10.2 聊天和 Agent

- `Models.stream/complete` 调 Provider 前使用同一预算器裁剪历史消息。
- 保留 system、最近 user 消息和匹配的 tool-call/tool-result 对；从最旧普通对话开始删除。
- 若单条最新用户消息本身超限，返回明确的“输入超过模型上下文”错误，不静默截断用户本轮正文。

## 11. 多源视频与 OCR

- `NoteGenerator.generate` 保留用户原始 extras，不再把整份 frame/search content直接拼回 map extras。
- `ContextNormalizer` 通过独立 `frame_context`/`web_search_context` 构建 final-stage pack。
- map 阶段只携带当前字幕块、原始用户要求和 map 指令。
- final 阶段才合并 map summaries、有效视觉/OCR和搜索上下文。
- OCR 文本为空或等于“未识别到文本”时，不生成 context 行。
- `supports_vision=false` 时，`MultiSourceVideoCollector` 明确向 `VideoFrameCollector` 传 `allow_vision=False`；每帧直接 OCR，不调用 `vision_analyzer`，也不向总结模型传 grid image。
- `supports_vision=true` 时保留视觉优先、失败转 OCR 的现有策略。

## 12. 错误处理与可观测性

- 添加模型校验失败返回安全中文错误，不输出 Provider secret。
- 日志记录模型名、上下文窗口、max input、chunk 数、是否 OCR 直达；不记录完整 prompt 和图片 base64。
- 上下文错误统一显示：`模型上下文不足，请调低输入内容或在模型设置中确认实际上下文长度`。
- 目录损坏降级 fallback；OCR 不可用则 frame collector failed，但转写笔记仍可继续。

## 13. 测试与验收

后端：

- schema ensure 精确清空范围和幂等性。
- catalog 精确/家族/fallback/损坏文件。
- model API 必填字段、范围、重复、列表、删除能力缓存。
- `Models.get_model` 使用保存配置、流式降级和聊天裁剪。
- token 预算和双预算 RequestChunker。
- 4096 模型的真实失败形态回归。
- 无视觉能力直接 OCR，空 OCR 不注入。
- map/final 上下文边界和超限 70% 重分块。
- 历史笔记在模型清空后仍可读取，新模型仍能保存新笔记。

前端：

- 不再出现内联“保存模型”。
- “添加模型”打开 Dialog，四个字段存在。
- 选择模型加载 defaults，保存 payload 完整，成功刷新列表。
- `pnpm test:contracts` 与 `pnpm build`。

最终验证：

```bash
PYTHONPATH=backend python3 -m pytest backend/tests -q
cd frontend && pnpm test:contracts
cd frontend && pnpm build
scripts/run_core_regression.sh
```

## 14. 风险和回滚

- 风险：用户升级后模型选择为空。预期行为，设置页需明确重新添加。
- 风险：目录理论值大于实际端点值。用户保存实际值；运行时仍有超限重分块兜底。
- 风险：保守 token 估算增加请求次数。优先保证成功率；usage 可用于后续校准。
- 风险：聊天裁剪破坏 tool 对。测试强制成对保留/删除。
- 回滚：回滚代码时旧版本可忽略 `models` 新列；新添加模型名称仍可读取。笔记数据从未被迁移或删除。
- 数据一致性：回滚不恢复被清空的旧模型配置，用户需在旧版重新添加；笔记和用量记录保持完整。

## 15. Agent 必答问题

- 影响模块：模型设置 UI、模型 API/DAO/schema、notemeld-ai、UniversalGPT/RequestChunker、聊天上下文、多源视频/OCR、打包资源和系统文档。
- 已有类似能力：能力缓存、模型列表、RequestChunker、SummaryRefineEngine 和 OCR fallback 均可复用。
- 产品规则：不冲突，提升知识编译稳定性。
- 数据语义：明确升级 `models` 为运行配置权威表，保留 `model_capabilities` 探测缓存语义。
- known pitfalls：通过 wrapper、幂等 schema ensure、单进程全量 pytest、辅助源可降级和不泄露 prompt 防回归。
- 数据/线上影响：只清空本地模型配置；不改线上端点，不删笔记。
- 最小改动：三个模型字段 + 本地目录 + Dialog + 统一预算器 + OCR/stream 分支。
- 回归测试：schema 保留笔记、API/UI、预算、map/final、OCR、stream、全量 backend/frontend。
