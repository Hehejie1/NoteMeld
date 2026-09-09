# 内容转换工具插件与 Agent 总结链路执行计划

日期：2026-08-27  
需求：`../../requirements/2026-08-27-content-conversion-tool-plugins.md`  
Change Spec：`../../system/change-spec-content-conversion-tool-plugins.md`

## 目标

- G01：冻结跨 Host plugin/capability/artifact contract。
- G02：交付文档转 Markdown 插件，覆盖 anydoc 目标格式。
- G03：交付视频/音频原子插件：fetch、audio extract、transcribe、frames。
- G04：交付图片 OCR 插件，保留文本块基础位置结构。
- G05：Agent 可组合工具并最终通过 Note capability 创建/关联 Note。
- G06：MCP、CLI、桌面使用同一 discovery/invoke、权限、取消和审计语义。
- G07：现有链接转 Note baseline 不回退，插件失败可恢复。

## 串行与并行规则

1. G01 必须先完成。
2. G02、G03、G04 在 G01 完成后可以并行开发，彼此不得直接依赖业务表。
3. G05 依赖 G01 和至少一个工具插件的稳定结果 envelope。
4. G06 依赖 G01、G05；MCP/CLI/UI 适配可以并行，但共享同一 Host。
5. G07 可并行准备，最终必须串行执行完整回归。
6. anydoc 集成评估在 G02 开始时完成；不能直接集成时，采用 MIT 许可下的内部适配/移植，不保留运行时外部引用。

## 执行顺序

### G01 Contract

定义 plugin manifest 的 runtime targets：desktop、server、mobile-native/wasm；定义 `ConversionArtifact`、文档块、媒体转写、OCR 文本块和 provenance envelope。

### G02 Document

新增 `official.document-to-markdown`，统一文档模型和 Markdown serializer；图片型 PDF 返回 `ocr_required`。一期只交付 desktop Host。

### G03 Media

将现有链接/媒体宿主能力拆成 fetch、audio extract、transcribe、frames，并保留字幕优先、失败降级和网页 fallback。

### G04 OCR

新增 `official.image-ocr`，输入图片或视频帧，输出文字、行/块、bbox、置信度和语言信息；本期不实现 ASCII。

### G05 Agent

Agent 通过 capability discovery 选择工具，读取 artifact 和 evidence，完成总结、引用和关系判断，最后调用 `note:create` / `note:link`。

### G06 Access

MCP、CLI、桌面调用统一 Host；服务端和移动端只冻结并验证 contract-compatible Host seam。

### G07 Regression

执行格式 corpus、插件供应链、工具链失败恢复、Agent Note provenance 和现有 URL baseline；未接入平台不得声称 runtime pass。

## 回滚

新插件安装失败保留旧 active version；工具链失败不回滚已成功提交的 Note；新原子工具不可用时保留现有 `official.link-note` host adapter。
