# 内容转换工具插件与 Agent 总结链路执行规格

关联需求：`../../requirements/2026-08-27-content-conversion-tool-plugins.md`  
关联计划：`../plans/2026-08-27-content-conversion-tool-plugins.md`

## 契约

插件 manifest 必须声明 plugin id/version、schema、runtime targets、capabilities、输入输出 schema、permissions、dependencies、license、artifact hash 和 entrypoint。manifest 只声明权限，不授予权限。

统一工具结果必须能表达 `completed`、`failed`、`cancelled`、`needs_attention`、`ocr_required`，并带 request id、source refs、input hash、tool id/version、artifact refs 和诊断信息。

## 插件边界

- `official.document-to-markdown`
- `official.video-fetch`
- `official.audio-extract`
- `official.audio-transcribe`
- `official.video-frames`
- `official.image-ocr`
- 当前 `official.link-note` 保持兼容，继续覆盖既有链接 baseline。

插件不能导入 Application router、Conversation/Event 内部实现或直接访问 NoteMeld SQLite 表；写入必须经过 Host port。

## anydoc 集成策略

先检查 anydoc Rust 核心、格式支持、artifact 许可和跨平台构建是否能作为插件内部实现直接接入。若不能直接接入，则只在 MIT 许可范围内移植所需 parser/document model/serializer 能力，形成 NoteMeld 自有实现；运行时不访问 GitHub、不依赖 hosted API、不要求用户安装 anydoc。

## Agent 链路

Agent 首轮通过 capability discovery 发现工具，按任务调用工具并消费 artifact；工具只提供转换结果和证据。Agent 负责选择、合并、总结、引用和关系判断，最终通过既有 Note capability 提交 Note。

## Host 目标

- 一期：NoteMeld desktop Python Host。
- 后续：server Host、Android/iOS/Harmony native/WASM Host。
- 所有 Host 遵循相同 capability schema、artifact envelope、permission、cancellation、provenance 和 Note port 语义。

## 本期不实现

- 图片 ASCII。
- 移动端/服务端运行时交付和跨设备同步。
- Agent 自动修改 SDK 或复杂多 Agent 编排。
