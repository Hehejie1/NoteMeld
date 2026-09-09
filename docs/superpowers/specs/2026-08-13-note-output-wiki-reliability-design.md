# 笔记输出格式与 Wiki 抽取可靠性设计规格

日期：2026-08-13
Requirement：`docs/requirements/2026-08-13-note-output-wiki-reliability.md`
Change Spec：`docs/system/change-spec-note-output-wiki-reliability.md`

## 设计边界

修复位于内容进入持久化之前和 LLM 兼容响应进入 Wiki 解析之前。前端只负责渲染已规范化的数据，不承担内容猜测。

## 笔记输出契约

新增 `backend/app/services/note_output_normalizer.py`：

- `strip_single_document_fence(content)`：仅当去除首尾空白后的全文由一个 fenced block 构成时剥离；语言仅识别 `html`、`markdown`、`md` 或空。
- `looks_like_html(content)`：检测实际元素标签，不依据 fence label。
- `normalize_note_output(content, output_formats)`：
  - Markdown 目标 + 实际 HTML：调用现有 `html_to_markdown`。
  - Markdown 目标 + 非 HTML：返回剥离后的裸 Markdown。
  - HTML 目标：剥离错误全文 fence 后保留内容。
  - 双格式 + 实际 HTML：保留现有 HTML/Markdown 双区块协议；非 HTML 不伪造 HTML。

`note_style_prompt_builder`：Markdown-only 直接输出裸 Markdown；HTML-only/双格式才要求 HTML skeleton。视频和网页生成器共同调用 normalizer。

## Wiki 响应契约

- `CompleteResult.finish_reason: str | None`，向后兼容默认 `None`。
- OpenAICompatibleProvider 从 `message.reasoning_content`（兼容 `message.reasoning`）读取推理文本，并读取 choice.finish_reason。
- NotemeldGPT 的 OpenAI 形状 response 同时暴露 `message.reasoning_content` 与真实 `finish_reason`。
- KnowledgeExtractor 的解析顺序：
  1. 非空 final `message.content`；
  2. reasoning 中完整 BEGIN_JSON/END_JSON、完整 `json` fence 或全文 JSON object；
  3. 若 `finish_reason` 为 `length`/`max_tokens`，报 output truncated；
  4. 若 reasoning 非空，报 produced reasoning but no final JSON；
  5. 否则报 returned empty content。

任何错误不得包含 reasoning 原文。恢复出的 dict 继续通过 `_normalize_analysis_payload` 与 WikiAnalysis schema。

## 预算

`WIKI_ANALYSIS_MAX_TOKENS` 默认从 1600 调整到 3200，环境变量继续覆盖。单块 prompt 限制实体/概念各 6、claim/evidence/relation 各 8，并限制摘要/描述/证据长度，降低无边界输出。

## 接口和数据

无 API 结构或数据库迁移。仅 Wiki error detail 更精确；旧调用方忽略新增 `finish_reason` 时行为不变。

## 安全

- 不向日志/UI 输出 chain-of-thought。
- 不接受 reasoning prose、截断 JSON 或数组作为 payload。
- 不修改内部代码 fence。

