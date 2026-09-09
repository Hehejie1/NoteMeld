# 内容转换工具插件与 Agent 总结链路 Change Spec

更新时间：2026-08-27
关联需求：`../requirements/2026-08-27-content-conversion-tool-plugins.md`

## 0. 预检查

- [x] 已阅读 `current-architecture.md`、`product-rules.md`、`data-model.md`、`api-inventory.md`、`known-pitfalls.md`
- [x] 已搜索相关代码和测试
- [x] 已确认存在 `official.link-note`、DocumentParser、OCR、视频帧和 VLM 类似能力
- [x] 已确认本次主要影响本地插件目录、artifact 和 Agent Host，不直接影响线上服务

## 1. 当前系统现状

- 独立 `notemeld-plugins/plugins/official-link-note/` 已提供视频/网页链接 capability，但宿主仍负责下载、转写、画面处理和 Note 生成。
- `backend/app/services/ingestion/document_parser.py` 已在 Application 内处理 PDF、Office、文本和图片输入。
- `backend/app/services/ocr/`、`video_frame_collector.py` 和 `note_style_image_vlm_analyzer.py` 已提供 OCR、视频帧和视觉分析基础设施。
- Agent Host 已提供 capability registry、ToolDriver、MCP、CLI 和 Note adapter。

## 2. 本次目标

- 将“输入转换”和“Agent 总结”拆成可发现、可授权、可取消、可审计的工具链。
- 用统一文档模型/Markdown 输出承接文档转换；建议 Application 插件使用 anydoc，不把 anydoc 或具体解析器加入 SDK 核心。
- 将视频/音频/图片处理拆成可组合原子 capability；最终 Note 只由 Agent 通过 Note capability 提交。
- 保留现有链接转 Note 的所有平台和降级路径。
- capability contract 与 artifact envelope 不绑定桌面；桌面先落地，服务端和移动端后续通过 Host/Binding 复用。

## 3. 明确不做

- 不修改 SDK L1/L2 核心 Loop 或 Note authority。
- 不新增第二套 Note 表或第二套 Agent loop。
- 不在本轮实现移动端、跨设备同步、复杂 Multi-Agent 编排和中心化插件市场。
- 不在本轮实现图片 ASCII；OCR 只输出文字和基础位置结构。

## 4. 影响范围

- 后端：插件 manager/verifier、官方插件 host、ingestion/document parser、OCR/video services、Agent capability registry/ToolDriver、artifact/provenance 记录。
- 前端：插件能力详情、工具链诊断和任务中间结果展示（具体 UI 在 spec 阶段冻结）。
- 文件系统：插件版本目录、artifact pointer、转换中间产物和来源 metadata。
- API/MCP/CLI：复用 capability discovery/invoke，必要时新增公开工具 schema，不让入口各自实现转换逻辑。
- 测试：插件 manifest、输入格式、结构化输出、错误/取消/恢复、权限、旧链接 baseline、Agent 最终 Note provenance；desktop 为本期 runtime，server/mobile 先验证 contract target。

## 5. 最小可行改动

1. 先定义统一 `ConversionArtifact` 和工具结果 envelope，不立即改变 Note 数据权威。
2. 将现有 DocumentParser 能力封装为一个文档转换插件，优先覆盖 anydoc 格式；先检查 anydoc Rust 核心是否可直接集成，不能直接集成时在 MIT 许可边界内移植/修改所需能力，运行时不依赖远程仓库或外部服务；图片型 PDF 转为 OCR required，而不是伪造文本。
3. 将现有视频服务按 fetch/audio/frames/transcribe/ocr/vision ports 暴露给原子插件。
4. 让 Agent 按 capability schema 组合工具，读取 artifact，再调用已有 Note create/link/relations 能力完成总结。
5. 通过 MCP/CLI/桌面共享同一 discovery/invoke 和审计语义。

## 6. 风险与回滚

- anydoc 或其他第三方依赖的 license、跨平台 artifact 和格式兼容性需要在 spec 阶段锁定；失败时保留现有内置解析器作为受控 adapter。
- 中间文件可能过大；必须使用 artifact pointer、大小限制和清理策略，不能直接注入模型上下文。
- 工具链中断时必须从 checkpoint 恢复，不重放已提交副作用；Note 只有在 Agent 最终提交成功后才视为成功。
- 插件迁移失败时保留旧 active version；新工具不可用时现有 `official.link-note` 继续可用。

## 7. 验收入口

以关联需求第 8 节为准。正式实现前必须补充 capability schema、artifact 数据模型、具体 API/MCP/CLI 映射和测试 fixture。
