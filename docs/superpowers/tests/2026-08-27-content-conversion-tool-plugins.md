# 内容转换工具插件与 Agent 总结链路验证计划

关联需求：`../../requirements/2026-08-27-content-conversion-tool-plugins.md`

## Contract

- manifest 校验 runtime targets、capability、permission、license、dependency 和 artifact hash。
- capability discovery/describe/invoke 在桌面 Host、MCP、CLI 使用相同 schema。
- `ConversionArtifact` 包含 input hash、source、tool/version、状态和 artifact refs。

## Document

- 覆盖 DOC/DOCX/DOCM、PPT/PPTX/PPS/POT、XLS/XLSX/XLSM/XLSB、ODF、RTF、EPUB、CSV、文本 PDF。
- 覆盖标题、段落、列表、表格、链接、脚注、公式和 embedded asset metadata。
- 损坏、加密、未知格式和图片型 PDF 分别断言 typed error / `ocr_required`。

## Media/OCR

- video fetch、audio extract、audio transcribe、frames 和 image OCR 可单独调用。
- OCR 结果包含 text blocks、行/块结构、bbox 和 confidence。
- 超时、取消、空 OCR、转写失败和媒体不可用不创建伪成功 Note。
- 明确没有 ASCII capability。

## Agent integration

- Agent 能组合视频工具，读取多个 artifact 后调用 Note create/link。
- 最终 Note 保留 source、tool/plugin/version、Turn、operation 和 relation。
- Note 已提交后索引、消息或 Wiki 投影失败不触发重复创建。

## Compatibility and release

- `official.link-note` 所有既有 URL baseline 不回退。
- 插件安装失败保留旧 active version，权限拒绝和 hash/version/license 失败 fail closed。
- desktop runtime 做真实链路；server/mobile 只做 contract/manifest target 验证，未接入平台不得声称 runtime verified。

## 已执行证据（2026-08-27）

- 在独立 `../notemeld-plugins` 仓库执行 `cargo test --manifest-path plugins/official-document-to-markdown/Cargo.toml --locked`：通过，Rust 插件 CSV→Markdown smoke 通过。
- 在独立 `../notemeld-plugins` 仓库执行 `cargo fmt --manifest-path plugins/official-document-to-markdown/Cargo.toml --all -- --check`：通过。
- `PYTHONPATH=backend pytest -q`：`723 passed, 5 skipped`；跳过项为未接入的跨平台/外部运行时测试。
- 定向 Agent Host / MCP / plugin control-plane 回归：`19 passed`。
- 实际 JSONL 子进程 smoke：文档插件返回 `conversion-artifact.v1`、`completed`、`csv` 和 Markdown 内容。
- 未执行 Android、iOS、Harmony 和 server runtime 验收；这些目标在 manifest 中明确标注为未打包或 contract-ready。
