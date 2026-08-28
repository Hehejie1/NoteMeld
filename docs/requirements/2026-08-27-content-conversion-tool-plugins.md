# 内容转换工具插件与 Agent 总结链路

日期：2026-08-27  
作者 / Agent：Codex  
状态：Implemented（一期桌面 Host）
关联对话 / 任务：完善 NoteMeld 插件系统，参考 firecrawl/anydoc 设计文档/文件转换插件，并将视频、音频、图片处理拆为 Agent 可调用的原子工具。  
关联系统文档：`../system/current-architecture.md`、`../system/product-rules.md`、`../system/data-model.md`、`../system/api-inventory.md`、`../system/known-pitfalls.md`、`../system/change-spec-content-conversion-tool-plugins.md`

## 1. 原始需求

用户希望完善 NoteMeld 插件系统，参考 [firecrawl/anydoc](https://github.com/firecrawl/anydoc)，增加各种文档转 Markdown 的能力，并将视频转笔记拆为音频转文字、图片 OCR 等原子插件能力。内容转换工具只负责产生可追溯的中间结果；理解、合并、总结和最终写成 Note 仍由 Agent 完成。

## 2. 背景和问题

- 当前用户：使用本地个人知识库、Agent、MCP 或 CLI 沉淀资料的用户。
- 当前场景：用户输入视频链接、音频、图片、PDF、Word 或其他文档，希望 Agent 将其加工为结构化 Note。
- 当前痛点：现有链接转 Note 已有 `official.link-note` 插件边界，但下载、转写、画面分析、文档解析和总结职责仍较集中；文档和媒体能力尚未形成统一的、可发现、可独立安装的工具插件。
- 参考事实：anydoc 将多种文档解析到统一文档模型，再由单一 Markdown serializer 输出；支持 Word、PowerPoint、Excel、OpenDocument、RTF、EPUB、CSV 和 PDF，并提供 Rust、Node、Python、WASM 绑定。图片型 PDF OCR 不属于 anydoc 本身能力，需要独立 OCR 工具或服务。

## 3. 目标结果

- 用户可以让 Agent 发现并调用独立的内容转换工具，把文件、链接或媒体转换为统一的 Markdown、文本、结构化块和证据资产。
- Agent 可以根据任务选择多个原子工具，例如“视频下载 → 音频转写 → 视频帧 OCR/视觉识别 → Agent 总结 → Note 写入”。
- 转换工具不直接决定 Note 标题、摘要、知识关系或最终总结，不直接写 Note 业务表；Agent 通过 Note capability 负责最终知识编译。
- 每个中间结果都带来源、工具/插件身份、版本、输入 hash、任务/Turn 和可恢复状态，失败可以重试或替换工具，不产生伪成功 Note。
- 文档转换优先复用 anydoc 的统一文档模型和 Markdown 输出思路，同时保留 NoteMeld 的本地优先、安全校验和插件生命周期。

## 4. 非目标

- 不修改 `notemeld-agent-sdk` 的核心 Loop、Session、Turn 或 Note authority；SDK 只消费通用工具结果契约。
- 不让插件直接总结、直接写 `note_documents`、直接写 Conversation/Event/Wiki 内部表。
- 插件能力契约面向桌面端、服务端和未来移动端复用；当前一期只实现 NoteMeld 桌面 Host，其他 Host 后续接入。
- 不在本需求中实现跨设备同步或复杂 Multi-Agent DAG。
- 不在本需求中实现中心化插件市场或任意 Git 仓库安装脚本。
- 不承诺图片型 PDF 仅依靠 anydoc 完成 OCR；OCR 是独立能力。

## 5. 当前系统事实

- 独立 `notemeld-plugins/plugins/official-link-note/` 提供 `official-link-note:create`，覆盖视频/网页链接路由，真实生成仍通过宿主 `generate_video` / `generate_web` ports。
- 视频宿主已有平台下载、字幕/转写优先、截图、视觉分析、OCR fallback、多源总结和网页降级服务。
- `DocumentParser` 当前处理 PDF、DOC/DOCX、PPT/PPTX、TXT/RTF/Markdown 和 PNG/JPG/JPEG/WEBP；这些能力仍属于 Application 服务，不是独立发布插件。
- 已有 OCR provider、视频帧采集、图片 VLM 分析和 Markdown 资源处理服务。
- Agent Host 已有 capability discovery/describe/invoke、ToolDriver、Note adapter、MCP 和 CLI 入口。
- Note authority、来源、关系、operation 和 migration isolation 规则已存在，不能新建第二套 Note 权威。

## 6. 用户故事

- 作为知识库用户，我希望把 PDF、Word、PPT、Excel、网页、视频、音频或图片交给 Agent，以便获得结构化、可追溯的 Note。
- 作为 Agent，我希望发现“转换工具”和其输入输出 schema，以便按任务组合工具，而不是依赖一个不可解释的超级工具。
- 作为插件开发者，我希望只实现一种输入转换能力，并通过公开 capability 协议接入 NoteMeld。
- 作为用户，我希望转换失败时看到明确原因，并能更换工具、重试或继续处理，不因一次中间步骤失败而创建空 Note。

## 7. 首批能力范围

### 7.1 文档转换

建议新增 `official.document-to-markdown`，首批支持 anydoc 已覆盖的：DOC/DOCX/DOCM、PPT/PPTX/PPS/POT、XLS/XLSX/XLSM/XLSB、ODT/ODS/ODP、RTF、EPUB、CSV、文本 PDF。输出统一为 Markdown + 结构化文档块 + embedded asset metadata。

### 7.2 视频/音频原子工具

- `official.video-fetch`：链接或本地视频获取媒体、字幕、元信息和来源证据。
- `official.audio-extract`：视频提取音轨或读取音频文件。
- `official.audio-transcribe`：音频转带时间戳的文本、说话人和置信度信息。
- `official.video-frames`：按时间点或场景采集视频帧。
- `official.image-ocr`：图片或视频帧 OCR，输出文本块、位置和置信度。
- `official.image-vision`：调用具备视觉能力的模型输出结构化画面描述；不直接生成最终 Note。

### 7.3 Agent 总结

Agent 通过 capability discovery 选择工具，读取工具结果和来源证据，完成摘要、章节、要点、引用、关系判断，然后调用 `note:create` / `note:link` 写入最终 Note。工具链中的中间结果可以只保留引用和 artifact pointer，避免把大文件直接塞入模型上下文。

## 8. 验收标准

1. GIVEN 一个受支持的文档，WHEN Agent 调用文档转换 capability，THEN 得到统一 Markdown、结构化块、格式、输入 hash 和 asset metadata，且不直接创建 Note。
2. GIVEN 一个视频任务，WHEN Agent 依次调用获取媒体、音频转写、帧采集和 OCR/视觉工具，THEN 每一步都有可发现 schema、独立结果和来源证据，最终由 Agent 生成 Note。
3. GIVEN 转换工具失败或超时，WHEN Agent 处理任务，THEN 返回 typed error 和可恢复状态，不提交空 Note，不自动重复已提交的副作用。
4. GIVEN 图片输入，WHEN 调用 OCR 或视觉识别工具，THEN 输出包含文字或结构化视觉信息及基础位置结构，并可被 Agent 继续消费；本期不提供 ASCII capability。
5. GIVEN 一个插件包，WHEN manifest、版本、hash、license、权限或路径校验失败，THEN 插件 fail closed，旧 active version 保持可用。
6. GIVEN 任意工具输出，WHEN Agent 最终写入 Note，THEN Note 保留 source、tool/plugin/version、Turn、operation 和关系信息。
7. GIVEN 现有链接转 Note baseline，WHEN 新原子工具链启用，THEN 原有视频平台、字幕优先、下载/转写、截图、网页 fallback 和错误分类行为不回退。
8. GIVEN 工具被 MCP、CLI 或 Application Agent 调用，WHEN capability 被发现和执行，THEN 三种入口使用同一 schema、权限、取消、超时和审计语义。

## 9. 输入 / 输出样例

### 输入

```json
{
  "source": {"kind": "file", "uri": "upload://example.docx"},
  "operation": "document.to_markdown",
  "request_id": "stable-request-id"
}
```

### 输出

```json
{
  "artifact": {"kind": "markdown", "uri": "artifact://...", "sha256": "..."},
  "document": {"format": "docx", "blocks": [], "assets": []},
  "provenance": {"tool_id": "official.document-to-markdown", "tool_version": "1.0.0"},
  "status": "completed"
}
```

### 反例或失败样例

- 加密或损坏的文档：返回 `encrypted` / `malformed`，不创建 Note。
- 图片型 PDF：文档转换工具返回 `ocr_required`，Agent 选择 OCR 工具后继续。
- 音频转写失败：保留媒体来源和失败状态，不生成伪造正文。
- OCR 为空：返回空结果和诊断，不将空文本作为有效总结依据。

## 10. 约束

- 平台：一期仍以 NoteMeld 桌面端和同机 Agent/CLI/MCP 为主。
- 隐私：默认本地处理；外发到视觉模型或云端转写前必须有 provider/permission 语义和脱敏记录。
- 安全：插件不能直接访问 NoteMeld 内部表；安装不执行脚本；工具有超时、取消、资源上限和输入大小上限。
- 兼容：公开 capability schema 优先兼容 MCP 和标准 function/tool calling；不绑定某个模型厂商。
- License：anydoc 为 MIT；引入前需记录版本、license 和 artifact hash，其他 OCR/媒体依赖逐项审查许可证。

## 11. 已确认的边界

- 首批采用“一个文档转换插件 + 多个视频/音频/图片原子插件”，不做超级 `media-to-note` 插件。
- anydoc 作为参考和可集成的文档转换能力，归属 NoteMeld Application 插件，不进入 `notemeld-agent-sdk` 核心；无法直接集成时，在 MIT 许可边界内修改/移植，去除运行时外部引用。
- 插件 contract 面向桌面、服务端和未来移动端；本期只交付桌面 Host。
- 本期不做图片 ASCII；图片只做 OCR，并尽量保留文字块的基础位置结构。

## 12. 与系统事实的冲突检查

- `product-rules.md`：不冲突；继续遵循“AI 编译知识，人验证和消费”。
- `data-model.md`：不新增第二套 Note authority；中间结果使用 artifact/provenance 记录，最终 Note 继续由现有 Note adapter 写入。
- `api-inventory.md`：优先复用 capability discovery/invoke、MCP 和 Agent Host；具体新增 capability schema 需在 spec 阶段登记。
- `known-pitfalls.md`：必须防止大文件进入上下文、工具副作用重放、Note 成功后投影失败造成重复创建、插件依赖/权限泄漏和进程内任务状态。
- 本地数据或线上服务：主要影响本地插件目录、artifact、上传文件和 SQLite 审计/任务状态；不要求新增线上服务。

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是；插件拆分、跨 Host 目标、anydoc 归属和 ASCII 排除范围已确认。
- 用户确认后推荐下一步：
  - [x] 生成 `docs/system/change-spec-content-conversion-tool-plugins.md`
  - [x] 生成对应 plan/spec/tests
  - [ ] 先实现文档转换插件，再实现媒体原子插件，最后接入 Agent 工具链
- 计划必须覆盖：插件 manifest、artifact schema、跨 Host runtime target、capability discovery/invoke、文档转换、媒体原子工具、Agent 总结、Note provenance、权限/取消/恢复、MCP/CLI 和旧链接 baseline。
