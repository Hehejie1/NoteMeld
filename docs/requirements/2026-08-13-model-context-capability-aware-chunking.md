# 模型上下文与能力感知分块

日期：2026-08-13
作者 / Agent：Codex（doc-driven 流程）
状态：Planned
实施进度：Tasks 1–8 自动化验证已通过，手动纵向验收待完成
关联对话 / 任务：本地 Ollama `deepseek-r1:7b` 笔记总结因 6492/4096 token 超限失败；用户要求模型导入时配置上下文、图像和流式能力，并让分块依据选中模型配置
关联系统文档：`docs/system/current-architecture.md`、`docs/system/product-rules.md`、`docs/system/data-model.md`、`docs/system/api-inventory.md`、`docs/system/known-pitfalls.md`

## 1. 原始需求

用户确认以下产品方向：

> 在导入或编辑大模型时设置上下文长度，并勾选是否支持图像和流式；总结分块根据当前选中模型的上下文判断。

用户进一步明确默认策略：

> 本地维护常见模型上下文映射，命中时自动使用映射值；没有映射时再回退 4096，不能把所有模型默认值写死为 4096。

用户要求把该功能写成需求，随后生成 Plan、Spec，完成实现和测试。

在审阅首版需求后，用户进一步收紧交互和数据边界：

> 模型列表右边去除“保存模型”，换成“添加模型”；点击后显示居中弹窗，弹窗支持选择模型、上下文长度、支持图像、支持流式，保存后写入数据库。

> 不需要兼容目前数据库里已经设置的模型，这部分模型配置数据可以清空后按新字段重新添加；已经生成的笔记内容必须保留。

## 2. 背景和问题（实现前基线，需求提出时）

- 当前用户是谁：在 NoteMeld 中导入 OpenAI 兼容、Ollama 或其他 Provider 模型，并用其生成视频、网页和文档笔记的用户。
- 当前场景是什么：用户选择一个已保存模型生成笔记，系统将基础提示词、字幕块、视觉上下文和输出协议组合后调用模型。
- 当前痛点是什么：
  1. `models` 当前只存 `provider_id` 和 `model_name`；系统无法知道所选端点实际开放的上下文窗口。
  2. `RequestChunker` 当前按请求 JSON 字节数和全局 45 MB 上限分块，不按模型 token 上下文分块。
  3. 模型理论上下文可能大于 Provider 实际分配值。例如本地 `deepseek-r1:7b` 模型文件声明 131072，但 Ollama 当前实际只分配 4096。
  4. 多源视频总结会把无效 OCR 文本等辅助上下文带入 map 请求；即使字幕已分块，第一块仍可能超限。
  5. 当前 `model_capabilities` 只有 JSON Mode 和图像能力，没有上下文长度、流式能力和配置来源。
- 为什么现在要做：同一错误已连续影响多个真实笔记任务；仅调整单个 Ollama 配置不能防止其他 Provider/模型重复出现上下文超限。

## 3. 目标结果

- 目标 1：模型列表区域只提供“添加模型”入口；点击后通过居中弹窗一次性选择模型并配置上下文长度、图像能力和流式能力。
- 目标 2：系统根据本地常见模型目录自动推荐上下文长度；目录未命中时使用 4096；用户保存值始终优先。
- 目标 3：笔记总结根据当前选中模型的上下文窗口计算安全输入预算并分块，而不是仅按请求字节数判断。
- 目标 4：模型不支持图像时不发送 image payload；模型不支持流式时聊天自动使用非流式兼容路径。
- 目标 5：上下文超限错误触发一次更保守的重新分块或压缩，而不是直接把整个笔记任务标记失败。
- 目标 6：过滤明显无效的视觉/OCR上下文，map 阶段不重复注入整份 final-stage 辅助上下文。
- 目标 7：数据库升级时只清空旧模型配置并采用新字段；现有笔记、会话、任务产物、转写、Wiki 和 Token 用量记录完整保留。

## 4. 非目标

- 不做：联网维护模型排行榜或在线下载模型能力数据库。
- 不做：保证本地目录覆盖所有模型、模型别名和第三方中转站自定义限制。
- 不做：自动修改 Ollama、vLLM、LM Studio 或云 Provider 服务端的上下文配置。
- 不做：在本次重写全部 LLM Provider 抽象、聊天协议或多源总结架构。
- 不做：把流式能力用于笔记分块；流式只影响响应传输方式。
- 不做：删除现有请求字节数上限；字节上限继续作为 HTTP payload 第二道保护。
- 不做：用模型官网理论上限覆盖用户在添加弹窗中确认并保存的端点实际值。
- 不做：本次不提供已添加模型的编辑弹窗；配置错误时删除后重新添加。
- 不做：清理、迁移或重写已有笔记正文及其关联会话、转写、Wiki 和媒体产物。

## 5. 实现前系统事实（需求提出时）

- 已有类似能力：
  - `model_capabilities` 已按 `provider_id + model_name` 唯一保存 `supports_json_mode`、`supports_vision`。
  - `ModelCapabilityService` 和 `CapabilityCatalog` 已提供能力读取与探测缓存。
  - `SummaryPlanner` 和 `SummaryRefineEngine` 已支持 direct/hybrid/map-reduce 与字幕段分块。
  - `RequestChunker` 已支持按序拆字幕和合并 partial，但预算单位是 JSON UTF-8 字节。
- 当前入口 / 页面 / API：
  - 设置页模型列表：`frontend/src/components/Form/modelForm/ModelSelector.tsx`。
  - `POST /api/models` 当前请求只有 `provider_id`、`model_name`。
  - `GET /api/model_list`、`GET /api/model_enable/{provider_id}` 返回已保存模型及部分能力。
  - `POST /api/models/probe` 当前只探测 JSON Mode。
- 当前数据来源和写入位置：
  - SQLite `models`：当前只保存模型身份，将在本需求中升级为模型身份与用户确认的运行配置权威表。
  - SQLite `model_capabilities`：继续作为 JSON Mode、tool calling 等自动探测缓存，不再作为用户手工图像/流式/上下文配置的权威来源。
  - 当前没有常见模型上下文目录文件。
- 当前限制：
  - 非 FreeModel Provider 默认允许 45 MB 请求体，远大于常见 4K/8K token 模型可接受的提示词。
  - `SummaryRefineEngine._is_final_retryable_error()` 未识别 `exceed_context_size_error`。
  - map 阶段 `_map_extras()` 会附加调用方传入的完整 extras。
  - OCR 结果即使全部为“未识别到文本”也会作为有效 frame context 注入。
- 相关 known pitfalls：
  - 数据模型和 API 变更必须兼容历史 SQLite 与现有调用方。
  - API 必须保持 `{code,msg,data}` wrapper。
  - notemeld-ai 迁移期不得绕回或删除现有兼容调用层。
  - 多源视频 collector 失败应可降级，不能让辅助源破坏主转写总结。

## 6. 用户故事

- 作为模型配置用户，我希望模型列表区域只有一个明确的“添加模型”按钮，并在居中弹窗中完成全部设置，以便不再混淆“选择模型”和“保存模型”。
- 作为模型配置用户，我希望添加模型时自动看到合理的上下文建议值，以便无需逐个查文档。
- 作为本地模型用户，我希望能把模型理论 131K 改成当前 Ollama 实际分配的 16K，以便分块符合真实端点限制。
- 作为笔记用户，我希望长视频自动分成模型可以接受的块，以便不会在采集十几分钟后才因 400 错误失败。
- 作为纯文本模型用户，我希望系统不要把图片发送给不支持图像的模型，以便避免无意义请求和 Provider 错误。
- 作为聊天用户，我希望不支持流式的模型仍能正常回答，只是一次性显示结果。

## 7. 验收标准

1. GIVEN 用户进入已保存 Provider 的模型设置页，WHEN页面加载完成，THEN模型列表标题右侧只有“添加模型”，不存在内联模型下拉框和“保存模型”按钮。
2. GIVEN 用户点击“添加模型”，WHEN弹窗打开，THEN页面中央显示模型选择、上下文长度、支持图像、支持流式、取消和保存控件。
3. GIVEN 模型名称命中本地常见模型目录，WHEN 用户在弹窗选择该模型，THEN 自动带出目录中的上下文和能力建议，且用户可以修改。
4. GIVEN 模型名称未命中目录，WHEN 用户在弹窗选择该模型，THEN 上下文建议值为 4096，并明确显示这是兜底建议而不是已探测值。
5. GIVEN 用户确认并保存，WHEN 后端写入成功，THEN `models` 同一行保存 `provider_id`、`model_name`、`context_window_tokens`、`supports_vision` 和 `supports_stream`；运行时始终读取该保存值。
6. GIVEN数据库仍是旧模型 schema，WHEN新版初始化首次执行，THEN只清空 `models` 和 `model_capabilities` 旧配置并建立最新字段；`providers`、`note_documents`、`conversations`、`conversation_messages`、`model_usage_records`、任务状态和 `note_results` 文件均不删除。
7. GIVEN 当前模型上下文为 4096，WHEN系统构建笔记或聊天请求，THEN输入预算扣除输出预留、提示词/协议开销、图片估算和安全余量后再截断或分块，预计 token 不超过该预算。
8. GIVEN模型上下文较大，WHEN同一字幕生成笔记，THEN系统允许合并更多字幕段，避免固定 80 段造成不必要的多轮请求。
9. GIVEN用户开启截图且模型 `supports_vision=false`，WHEN执行视频分帧，THEN直接调用 OCR，不先调用视觉模型，且发给总结模型的请求不包含图片。
10. GIVEN模型 `supports_stream=false`，WHEN用户发起流式聊天接口，THEN后端使用非流式模型调用并将完整结果适配为现有 SSE 输出，不破坏前端协议。
11. GIVEN OCR 结果全部为空或为“未识别到文本”，WHEN构建总结上下文，THEN这些占位文本不进入 map 或 final prompt。
12. GIVEN长视频走 map-reduce，WHEN执行 map 阶段，THEN每个 map 请求只包含当前字幕块、用户原始要求和 map 必需说明，不重复注入整份视觉、网页搜索或 final-stage上下文。
13. GIVEN Provider 返回 `exceed_context_size_error` 或等价上下文超限错误，WHEN第一次请求失败，THEN系统以更保守预算重新切块或压缩一次；若仍失败，返回简洁可操作错误并保留已完成采集缓存。
14. GIVEN新版初始化已经清空旧模型配置，WHEN用户重新添加模型并生成新笔记，THEN新笔记正常保存；历史笔记仍可打开和读取，不依赖旧模型配置行存在。
15. WHEN运行新增后端单测、模型/笔记/AI 兼容测试、前端契约测试和生产构建，THEN全部通过，并把验证证据写入 `docs/superpowers/tests/`。

## 8. 输入 / 输出样例

### 输入

- 模型：`deepseek-r1:7b`，本地目录建议 `131072`，用户将当前端点实际值改为 `16384`。
- 模型：未知别名 `company/custom-reasoner`，目录无匹配。
- 能力：`supports_vision=false`、`supports_stream=true`。

### 输出

- 已保存模型行：`model_name=deepseek-r1:7b`、`context_window_tokens=16384`、`supports_vision=false`、`supports_stream=true`。
- 未知模型表单建议：`context_window_tokens=4096`，来源显示为“默认兜底”。
- 任务预算信息可记录：模型窗口、预计固定开销、输出预留、安全余量和实际 chunk 数。

### 反例或失败样例

- 所有模型都静态使用 4096：失败，忽略常见模型目录。
- 将官网 131K 自动视为本地 Ollama 实际 131K 且不允许用户修改：失败。
- `supports_stream=false` 时直接拒绝聊天：失败，应兼容非流式调用。
- 只增加 UI 字段但总结仍按 45 MB 分块：失败。
- 224 条“OCR 未识别到文本”继续进入每个 map 块：失败。

## 9. 约束

- 平台 / 设备：兼容源码、CLI、Tauri sidecar、macOS Intel/Apple Silicon 和 Windows；不依赖仅某平台可用的 tokenizer native 扩展。
- 性能 / 耗时：预算计算和目录匹配应为本地内存操作；不为每次请求新增联网探测。
- 隐私 / 安全：模型目录与能力配置不含 API Key、token、请求正文或用户素材。
- 兼容性：不兼容旧 `models`/`model_capabilities` 配置行，升级时定向清空；必须兼容并保留旧笔记、会话、任务文件、Wiki、转写和用量数据。
- 成本：不新增在线服务；目录随应用发布。
- 时间：本次交付最小可用闭环，目录先覆盖仓库/用户当前常见模型家族并提供安全 fallback。
- 第三方依赖 / License：优先使用现有依赖或纯 Python 估算，不引入重型 tokenizer 依赖。

## 10. 边界场景

- 空数据：模型名为空时禁止保存；能力字段缺失时按目录/fallback 解析。
- 权限拒绝：数据库写入失败返回安全错误，不伪装保存成功。
- 网络失败：Provider 能力探测失败不阻止手工保存。
- 任务中断：已完成 transcript/frame 缓存继续保留，重试可复用。
- 旧数据兼容：schema ensure 只在检测到旧模型结构时执行一次定向清空与字段升级；新结构后续启动不得重复清空。
- 大数据量：目录匹配按精确名称优先、规范化别名/家族规则其次；单次解析不能扫描网络或模型文件。
- 端点限制小于目录值：由用户覆盖；错误兜底仍会缩小一次，且错误提示要求检查端点实际上下文。
- 图片 token：无法精确预估不同 Provider 的图片成本时，使用保守占位预算和现有字节上限双重约束。

## 11. 开放问题

无阻塞问题。

已确认策略：目录命中值作为建议，用户保存值优先；目录未命中回退 4096。实现规格需明确目录首批模型和 token 估算公式。

## 12. 与系统事实的冲突检查

- 是否和 `product-rules.md` 冲突：不冲突。该能力提升后台知识编译稳定性和可验证性。
- 是否和 `data-model.md` 字段语义冲突：需要把 `models` 从纯身份表升级为用户确认的模型运行配置权威表；`model_capabilities` 保留探测缓存语义；必须同步文档。
- 是否和 `api-inventory.md` 接口语义冲突：`POST /api/models` 请求改为必须提交上下文、图像和流式字段；用户已明确无需兼容旧模型添加交互，必须同步前端和文档。
- 是否会重新引入 `known-pitfalls.md` 中的问题：若只改 UI 会重现超限；需求明确要求运行时消费。数据库迁移必须幂等，API 保持 wrapper。
- 是否影响本地数据或线上服务：首次升级定向清空本地模型配置表，影响模型选择，用户需重新添加；不影响笔记内容或线上 Provider 配置。
- 是否影响用户已确认交互：按用户确认删除内联保存模型，改为居中添加弹窗；已添加模型继续列表展示和删除。

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是。
- 推荐下一步：
  - [x] 使用 Superpowers 形成设计并经用户确认
  - [x] 生成 `docs/superpowers/plans/2026-08-13-model-context-capability-aware-chunking.md`
  - [x] 生成 `docs/superpowers/specs/2026-08-13-model-context-capability-aware-chunking-design.md`
  - [x] 使用 TDD 实现并完成自动化验证（手动纵向验收待完成）
- 计划必须覆盖的验收标准：第 1–15 条全部覆盖，尤其是添加弹窗、定向清空边界、目录/fallback/保存值、token 预算、OCR 直达、流式降级和超限重试。
- 计划必须补充的验证：4096 本地模型复现、旧 schema 定向升级与模型配置清空、未知模型 fallback、视觉/流式降级、目录匹配优先级和完整后端单进程测试。

## 14. 实施与验收状态

- Tasks 1–7 的实现已落入当前工作区；Task 8 于 2026-08-13 fresh 运行后端定向、后端全量单进程、前端契约、前端生产构建和核心回归，均以 exit 0 完成。
- 当前自动化环境未执行真实 UI/Ollama/7.5 分钟视频及升级前历史笔记手动纵向验收，因此需求状态保持 `Planned`，不标记为完整 `Implemented`。
- 验证证据：[`docs/superpowers/tests/2026-08-13-model-context-capability-aware-chunking.md`](../superpowers/tests/2026-08-13-model-context-capability-aware-chunking.md)。
