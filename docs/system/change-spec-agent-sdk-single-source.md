# Change Spec：Agent SDK 单一源码仓库收敛

状态：Implemented（本分支已完成代码收敛，待合并与最终回归）

## 当前系统现状

- 独立仓库 `/Users/hehejie/ai/notemeld-agent-sdk` 已包含 Rust workspace、Python SDK、C ABI、Swift/Kotlin/OpenHarmony binding、Ollama CLI、构建脚本和 release artifact。
- 本变更前 NoteMeld 跟踪 `agent-sdk/` 源码副本、跨平台构建脚本、fixture、schema 和 `.github/workflows/agent-sdk.yml`；本分支已删除这些副本。
- `backend/app/agent_host/` 已通过 Python binding 加载 Rust runtime，但 runtime loader、PyInstaller spec 和部分测试仍允许从 NoteMeld 或外部源码目录加载 SDK。

## 目标

1. `/Users/hehejie/ai/notemeld-agent-sdk` 成为 Agent SDK 唯一源码和跨平台构建仓库。
2. NoteMeld 不再维护 `agent-sdk/` 源码、SDK workflow、SDK Rust/Python binding 测试副本或 SDK 构建脚本。
3. NoteMeld 只通过已安装的、版本校验过的 SDK wheel/native artifact 运行 Agent Host。
4. NoteMeld 保留应用层 Agent API、Host 适配、Conversation/Agent 事件持久化、桌面启动和 artifact 消费契约测试。

## 不做什么

- 不修改 Agent v1 HTTP 路径、Turn/Event 数据模型或会话语义。
- 不删除独立 SDK 仓库的任何能力。
- 不在本次改动中实现远程 SDK 拉取、自动发布或移动端运行时。
- 不删除历史文档中的事实记录，但会同步当前架构和验收文档，避免把 `NoteMeld/agent-sdk/` 描述为现行源码。

## 影响范围

- 删除 NoteMeld `agent-sdk/` 和 `.github/workflows/agent-sdk.yml`。
- 删除仅服务于内嵌 SDK 构建的 NoteMeld workflow contract test。
- 收紧 `backend/app/agent_host/runtime.py`，拒绝源码目录和 `NOTEMELD_AGENT_SDK_PYTHON_PATH` 回退。
- 收紧 PyInstaller spec，只收集已安装 `notemeld_agent_sdk` package/native 资源。
- 更新启动脚本、Agent Host 测试、系统架构、需求索引和验收说明。

## 最小实现

1. 使用外部 SDK artifact 作为生产输入，保持 `NOTEMELD_AGENT_SDK_WHEEL` 安装和 SDK/schema 版本校验。
2. 删除 NoteMeld 内嵌 SDK 文件和 SDK 专属 CI；应用 CI 不再编译 Rust SDK。
3. 新增“无内嵌 SDK + 仅 artifact loader”契约测试。

## 验收

- `git ls-files agent-sdk` 无结果。
- NoteMeld 仓库无 SDK 构建 workflow、源码路径回退和 `NOTEMELD_AGENT_SDK_PYTHON_PATH`。
- `backend/tests/agent_host` 的 artifact/loader 契约已更新，能验证缺失/不匹配 wheel fail-closed；本机 pytest 缺失时需在项目测试环境执行。
- Python compileall、Shell syntax、前端和 Agent Host 回归通过。
- 独立 SDK 的 Rust/Python/跨平台构建和发布测试在 `/Users/hehejie/ai/notemeld-agent-sdk` 仓库执行，不由 NoteMeld 重复执行。

## 风险与回滚

- 风险：本地开发者未安装 SDK wheel 时，NoteMeld Agent Host 会启动失败；这是预期的 fail-closed 行为。
- 风险：外部 SDK 版本发布与 NoteMeld 版本不匹配；通过 SDK/schema 版本门禁阻断。
- 回滚：恢复删除的 NoteMeld 文件和 workflow，并回退本 Change Spec 对应提交；不修改用户数据和 SQLite schema。
