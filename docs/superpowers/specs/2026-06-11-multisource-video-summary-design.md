# 多源视频增强总结设计

## 背景

NoteMeld 当前视频笔记链路以 `NoteGenerator.generate` 为主入口，按顺序执行平台字幕、媒体下载、音频转写、LLM 总结、截图后处理和保存。现有代码已经具备多源增强总结所需的大部分基础能力：

- `backend/app/services/note.py`：视频笔记主流程、字幕优先、媒体下载、总结、截图后处理。
- `backend/app/utils/video_reader.py`：视频抽帧、去重、时间戳标注、网格图拼接、base64 图片输出。
- `backend/app/models/summary_input.py`：`PageContext`、`TranscriptContext`、`VisionContext`、`WeightedContextPack` 等统一上下文模型。
- `backend/app/services/context_normalizer.py`：视频任务到 `SummaryInput` 的标准化。
- `backend/app/services/summary_planner.py`：长视频 direct/hybrid/map-reduce 策略和视觉采样策略。
- `backend/app/services/summary_refine_engine.py`：长视频分块总结、final 图片降级重试。
- `backend/app/services/ocr`：OCR provider 抽象和 RapidOCR 实现。
- `frontend/src/pages/HomePage/progressSteps.ts`：当前进度展示仍是单线阶段。

但当前链路仍存在几个问题：

- 视频链接的网页搜索、音频转文字、视频分帧没有作为标准三路并行采集编排。
- 有字幕时默认不会下载视频，只有 `screenshot` 或 `video_understanding` 才会补拉视频资源。
- 截图分帧只是生成图片并交给多模态总结，没有独立的“视觉摘要 -> OCR 兜底 -> frame_context”结果层。
- 目前没有独立联网 Web Search 服务，只有网页解析、本地 Wiki 和向量检索。
- 进度阶段过粗，`SUMMARIZING` 容易把视觉识别、搜索融合、最终总结混在一起，用户无法判断慢在哪里。

## 目标

视频链接进入标准多源增强总结链路：

- 链接必须走网页搜索，形成 `web_search_context`。
- 视频必须走音频转文字，形成 `transcript_context`。
- 用户勾选截图时必须走视频分帧，形成 `frame_context`。
- 网页搜索、音频转文字、视频分帧三路并行执行，最终统一融合总结。
- 视频分帧优先使用多模态 LLM 识别，失败或结果不可用时自动走 OCR。
- 最终总结明确区分视频转写事实、画面证据、网页搜索补充，避免把外部资料混写成视频原话。
- 缓存优先，同一任务重试或同一视频重复生成时尽量复用中间产物。

## 非目标

- 不在第一版重做整个笔记任务系统。
- 不把所有图片直接塞进最终总结，避免 token、请求体和超时失控。
- 不要求 Web Search 直接成为事实来源的唯一依据；它只作为背景补充和事实校验。
- 不把 OCR 当作视觉理解替代品；OCR 只负责提取画面文字，视觉语义仍优先交给多模态模型。

## 当前代码结构

### 后端

- `routers/note.py`：`POST /generate_note` 创建任务，按 `platform` 分发到视频任务或网页任务。
- `services/note.py`：视频生成核心流程。当前是顺序流程：字幕/下载/转写/总结/后处理/保存。
- `downloaders/base.py`：平台下载器抽象，提供 `download`、`download_video`、`download_subtitles`。
- `utils/video_reader.py`：抽帧拼图实现，已支持并行 ffmpeg 抽帧、时间戳绘制、grid 图片输出。
- `services/ocr`：OCR 抽象层，`get_ocr_provider()` 默认选择 RapidOCR。
- `gpt/universal_gpt.py`：OpenAI 兼容多模态消息构建、请求分块、重试、usage 记录。
- `gpt/request_chunker.py`：文本和图片请求体预算控制。
- `services/summary_refine_engine.py`：长视频分块摘要和 final 阶段图片数量降级。
- `services/web_note.py` / `services/web_source_layer.py`：网页解析与网页笔记链路，但不是联网搜索。
- `services/wiki_search.py` / `services/context_builder.py`：本地 Wiki 和笔记上下文检索，不等价于 Web Search。

### 前端

- `frontend/src/services/note.ts`：提交参数已包含 `screenshot`、`video_understanding`、`vision_mode`、`max_sampling_points`、`grid_size`。
- `frontend/src/pages/HomePage/progressSteps.ts`：进度目前是 `解析链接 / 下载音频 / 转写文字 / 总结内容 / 保存笔记`。
- `frontend/src/store/taskStore`：任务状态类型目前只覆盖粗粒度 `TaskStatus`。

## 推荐架构

新增一个后端编排层 `MultiSourceVideoCollector`，由 `NoteGenerator.generate` 调用。该编排层负责并行运行三个采集器，并产出统一的 `MultiSourceSummaryBundle`。

### 采集器

#### WebSearchCollector

职责：

- 对视频链接、标题、作者、平台、描述生成搜索 query。
- 执行联网搜索，提取来源标题、链接、摘要、发布时间、可信度。
- 对结果去重、截断、排序，输出 `web_search_context`。

第一版实现建议：

- 新增 `backend/app/services/web_search.py`。
- Provider 抽象为 `WebSearchProvider`，支持后续接入 Tavily、Bing、SerpAPI 或自建搜索 API。
- 若没有配置搜索 provider，返回 `status=skipped`，不阻塞主链路。
- 缓存文件：`{task_id}_web_search.json`。

#### TranscriptCollector

职责：

- 复用当前字幕优先逻辑：缓存 -> 平台字幕 -> 音频下载 -> ASR。
- 产出 `transcript_context`。
- 为视频抽帧提供 `audio_meta`、时长和可能的字幕关键时间点。

第一版实现建议：

- 将 `note.py` 中字幕获取、媒体元信息、转写逻辑抽成可复用方法，不改变下载器接口。
- 保留现有 `{task_id}_transcript.json` 和 `{task_id}_audio.json` 缓存。
- 如果平台字幕命中，但截图勾选为真，仍要允许 FrameCollector 拉取视频文件。

#### FrameCollector

职责：

- 只在 `screenshot=True` 时执行。
- 下载视频文件，按智能采样或固定间隔抽帧。
- 生成带 `mm:ss` 时间标记的 grid 图片。
- 优先调用视觉 LLM 生成 `frame_context`。
- 视觉 LLM 失败、模型不支持图片、结果为空或质量低时，自动走 OCR。

第一版实现建议：

- 新增 `backend/app/services/video_frame_collector.py`。
- 复用 `VideoReader`，但要避免当前 `VideoReader.run()` 清空全局 `output_frames/grid_output` 导致并发任务互相影响。
- 为每个 task 使用独立目录：`note_output_dir()/frames/{task_id}/raw` 和 `note_output_dir()/frames/{task_id}/grid`。
- 视觉结果缓存：`{task_id}_frame_context.json`。
- grid 图片缓存：`{task_id}_frame_grids.json`。
- OCR 结果缓存：`{task_id}_frame_ocr.json`。

## 并行数据流

当前串行链路：

```text
解析链接 -> 字幕/下载 -> 转写 -> 总结 -> 截图后处理 -> 保存
```

目标并行链路：

```text
解析链接
  -> 并行启动 WebSearchCollector
  -> 并行启动 TranscriptCollector
  -> screenshot=True 时并行启动 FrameCollector
等待三路结果
  -> 标准化 MultiSourceSummaryBundle
  -> 构建 SummaryInput / WeightedContextPack
  -> direct 或 hybrid 融合总结
  -> 截图/链接后处理
  -> 保存
```

三路采集使用 `ThreadPoolExecutor` 即可满足第一版需求：

- `web_future = executor.submit(collect_web_search)`
- `transcript_future = executor.submit(collect_transcript)`
- `frame_future = executor.submit(collect_frames)`，仅 `screenshot=True` 时创建

注意：`FrameCollector` 可能需要视频文件，`TranscriptCollector` 也可能下载音频。第一版为降低冲突，建议：

- 平台字幕命中时，`TranscriptCollector` 不下载音频，`FrameCollector` 独立下载视频。
- 平台字幕未命中时，`TranscriptCollector` 负责下载音频，`FrameCollector` 负责下载视频。
- 下载器实现如果存在共享临时文件路径风险，必须按 task_id 设置独立输出目录。

## 统一数据模型

新增 `backend/app/models/multisource_summary.py`：

```python
from dataclasses import dataclass, field
from typing import Optional

@dataclass
class CollectorResult:
    source: str
    status: str
    content: str = ""
    confidence: float = 0.0
    error: Optional[str] = None
    artifacts: dict = field(default_factory=dict)

@dataclass
class WebSearchResult(CollectorResult):
    sources: list[dict] = field(default_factory=list)

@dataclass
class FrameContextResult(CollectorResult):
    mode: str = "disabled"  # vision_llm | ocr | mixed | disabled
    frames: list[dict] = field(default_factory=list)
    grid_images: list[str] = field(default_factory=list)

@dataclass
class MultiSourceSummaryBundle:
    task_id: str
    source_url: str
    platform: str
    title: str
    audio_meta: object | None
    transcript: object | None
    web_search: WebSearchResult
    frame_context: FrameContextResult
```

`ContextNormalizer.from_video_task()` 后续增强为：

- 将 `web_search.content` 加入 `PageContext.key_points` 或新增 `SearchContext`。
- 将 `frame_context.frames` 映射到 `VisionContext.frames`。
- 将 `frame_context.content` 作为 `VisionContext.storyboard_summary`。
- `WeightedContextPack` 增加 `search` 和 `vision` source block。

为了减少侵入，第一版可以不新增 `SearchContext` dataclass，先将 Web Search 作为 `ContextBlock(source_type="search", role="external_evidence")` 注入 `WeightedContextPack`。

## 视觉识别与 OCR 兜底

FrameCollector 的识别策略：

```text
生成 grid 图片
  -> 检查当前模型是否支持 image_url
  -> 支持则调用视觉 LLM
  -> 校验视觉结果是否有效
  -> 无效则走 OCR
  -> 视觉有效但画面文字少时，可补 OCR 作为 detected_text
```

视觉 LLM 输出要求：

- 按时间点整理：`mm:ss -> 画面摘要 -> 画面文字 -> 证据类型`。
- 明确识别 PPT、代码、图表、网页、产品界面、操作步骤。
- 不要虚构看不见的内容。

OCR 输出要求：

- 按 grid 图片和 frame 时间组织。
- 保留文本置信度。
- 不做强语义推理，只做画面文字证据。

结果质量校验：

- 视觉 LLM 内容为空，走 OCR。
- 视觉 LLM 返回明显拒答、模型不支持图片、请求体过大、网关超时，走 OCR。
- OCR provider 未安装或失败，`frame_context.status=failed`，最终总结继续进行。

## 最终融合总结

最终 prompt 固定包含四类上下文：

- `source_meta`：链接、平台、标题、作者、时长。
- `transcript_context`：字幕/转写文本或分块摘要。
- `frame_context`：视觉 LLM 摘要、OCR 时间线、grid 图片证据。
- `web_search_context`：搜索结果摘要、来源链接、可信度。

融合规则：

- 字幕/转写是视频事实主源。
- 画面识别是视觉证据，用于补充字幕没有说出的信息。
- Web Search 是外部背景和事实校验，不得写成视频作者原话。
- 搜索结果与视频内容冲突时，保留冲突说明。
- 输出尽量保留关键时间点，方便回看原片。

长视频策略：

- 继续复用 `SummaryPlanner` 的 `hybrid` 判定：超过 30 分钟或 120 段字幕走分块。
- map 阶段只处理 transcript，避免每块都带图片和搜索资料。
- final 阶段合并 `transcript_summary + frame_context + web_search_context`。
- final 阶段不再直接传大量图片，优先传文本化后的 `frame_context`；只有需要截图 marker 时再保留少量 grid 图。

## 缓存策略

新增或保留以下缓存：

- `{task_id}_audio.json`：现有音频/视频元信息。
- `{task_id}_transcript.json`：现有字幕/转写结果。
- `{task_id}_web_search.json`：新增 Web Search 结果。
- `{task_id}_frame_grids.json`：新增 grid 图片路径、base64 或本地 URL、时间点映射。
- `{task_id}_frame_context.json`：新增视觉 LLM/OCR 后的 frame context。
- `{task_id}_markdown.md`：现有最终 Markdown。

缓存命中原则：

- 优先使用 task 缓存。
- 重试同一 task 时复用已成功的 collector 结果。
- 用户手动重新生成时可以通过新 task_id 强制重新采集。

## 任务状态与前端展示

现有 `TaskStatus` 只有单线阶段，不适合表达并行采集。第一版建议保留主状态枚举，新增 `collector_timings` 字段：

```json
{
  "status": "SUMMARIZING",
  "collector_timings": {
    "web_search": {"status": "done", "duration_ms": 1200},
    "transcript": {"status": "running", "elapsed_ms": 3200},
    "frames": {"status": "done", "duration_ms": 2800},
    "vision": {"status": "fallback_ocr", "duration_ms": 2100}
  }
}
```

前端展示：

- 主进度仍保留一屏式，不引入复杂页面。
- 在当前阶段卡片内展示三路并行子状态：
  - `网页搜索`
  - `音频转文字`
  - `视频分帧`
  - `画面识别/OCR`
  - `融合总结`
- `progressSteps.ts` 后续可把 `下载音频` 文案改为更准确的 `采集素材`，避免并行后误导用户。

## 错误处理

错误策略为“可用内容尽量总结”：

- Web Search 失败：记录错误，最终总结跳过搜索上下文。
- 平台字幕失败：回退音频转写。
- 音频转写失败：如果 Web Search 或 FrameContext 有内容，可生成弱总结，并标注“转写不可用”。
- 视频分帧失败：跳过 frame_context，不影响字幕总结。
- 视觉 LLM 失败：走 OCR。
- OCR 失败：frame_context 标记 failed，不阻塞最终总结。
- 最终总结请求体过大：复用 `SummaryRefineEngine` 降级到压缩上下文。

## 实施计划草案

第一阶段：结构抽取

- 从 `NoteGenerator.generate` 抽出 transcript 采集函数。
- 新增 `MultiSourceVideoCollector` 和 `MultiSourceSummaryBundle`。
- 保持现有串行行为不变，先在内部用 bundle 承接结果。

第二阶段：并行采集

- 接入 `ThreadPoolExecutor` 并行执行 Web Search、Transcript、Frame。
- 为并行 collector 增加独立缓存和错误结果。
- 修正下载输出目录，避免并发任务互相覆盖。

第三阶段：FrameContext

- 新增 FrameCollector。
- 改造 `VideoReader` 支持 task 独立目录，不清理全局目录。
- 增加视觉 LLM 识别。
- 增加 OCR fallback。

第四阶段：Web Search

- 新增 `WebSearchProvider` 抽象。
- 第一版支持配置型 provider；未配置时 graceful skip。
- 将 search 结果注入 `WeightedContextPack`。

第五阶段：融合总结

- 改造 `_summarize_text` 接受 `MultiSourceSummaryBundle` 或增强后的 pack。
- direct 模式融合三源上下文。
- hybrid 模式 map 只处理 transcript，final 合并 search 和 frame。

第六阶段：前端进度

- 后端 status json 增加 `collector_timings`。
- 前端任务卡片展示三路并行子状态。
- 更新文案为 `网页搜索 / 音频转文字 / 视频分帧 / 融合总结`。

## 测试策略

后端契约测试：

- 视频链接创建任务时，`screenshot=True` 会启动 frame collector。
- Web Search 失败不会导致任务失败。
- 视觉 LLM 失败时会调用 OCR fallback。
- transcript 命中缓存时仍可执行 frame collector。
- 三路 collector 结果能合并到最终 prompt 上下文。

单元测试：

- `VideoReader` 使用 task 独立目录，不清理其他任务目录。
- `FrameCollector` 对视觉失败、OCR 失败、空结果分别返回正确状态。
- `MultiSourceSummaryBundle` 到 `WeightedContextPack` 的映射稳定。

前端契约测试：

- `TaskStatusResponse` 兼容 `collector_timings`。
- 进度卡片能展示并行子状态。
- 没有 `collector_timings` 时保持旧 UI。

## 风险与取舍

- 默认多源增强会增加资源消耗，但并行采集能把总耗时从三路相加降为接近最慢一路加最终总结。
- Web Search 需要外部 provider；未配置时必须跳过，不能卡死任务。
- 多模态 LLM 对图片支持不稳定，必须保留 OCR fallback。
- `VideoReader` 当前使用共享输出目录并清理旧帧，必须优先改造，否则并发任务会互相影响。
- 最终总结不能直接吃全部图片，应使用文本化后的 `frame_context`，只保留必要截图引用。

## 验收标准

- 视频链接任务会并行运行网页搜索、音频转文字、视频分帧。
- 勾选截图时，grid 图包含每帧时间标记。
- 视觉模型不能识别图片时自动使用 OCR，任务不失败。
- 最终笔记融合 `web_search_context`、`transcript_context`、`frame_context`。
- 搜索内容在笔记中被标记为外部补充，不与视频原文混淆。
- 任务状态能展示三路采集的独立耗时。
- 未配置 Web Search 或 OCR 时，任务仍可完成并生成可用笔记。
