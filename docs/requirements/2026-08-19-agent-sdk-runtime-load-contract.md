# Agent SDK Runtime 加载契约收口 Change Spec

日期：2026-08-19
状态：Completed

## 0. 预检查

- [x] 已阅读 `AGENTS.md`、`CLAUDE.md` 与 `docs/system/` 必读文档。
- [x] 已阅读单一运行时切换需求、Agent Host 代码和相关契约测试。
- [x] 已核对独立 `notemeld-agent-sdk` 的 Python binding、C header、ABI JSON、构建脚本和 artifact verifier。
- [x] 已确认本目标不修改本地数据、公共 API、模型调用、ToolDriver 或 UI。

## 1. 当前系统现状

- `backend/app/agent_host/runtime.py` 只允许 Rust SDK，但把期望 ABI 写成 `2`，并在 runtime 模块缺少 `ABI_VERSION` 时回退读取包级常量。
- 独立 SDK 的真实发布链路固定打包并校验 `bindings/abi-v1.json`；C header、Python wheel、Swift/Kotlin/Harmony 构建脚本和 artifact verifier 均声明 ABI `1`。
- 独立 SDK 包级 `ABI_VERSION=2` 与实际发布 artifact 不一致；Python runtime 模块本身不声明 ABI。NoteMeld 当前因此验证了错误的元数据来源，没有验证 wheel 内 ABI contract，也没有在 loader 阶段验证 native artifact 的存在、导出符号和 native SDK/schema version。
- `run_notemeld.sh` 与 `scripts/notemeld` 直接读取 runtime 模块中不存在的 `ABI_VERSION`，导致兼容 wheel 也无法通过启动前检查。
- Host 不包含 legacy fallback，但 native runtime 初始化异常尚未统一为脱敏的 SDK 加载错误。

## 2. 本次目标

- NoteMeld 只接受已安装的独立 SDK wheel 及其随包 native artifact，不从 SDK 源码目录加载。
- 以 wheel 内 `notemeld-agent-sdk.json`、`abi-v1.json` 和 native exports 共同验证 SDK、schema 与 ABI；真实发布 ABI 统一为 `1`。
- SDK、metadata 或 native artifact 缺失，以及 SDK/schema/ABI 不匹配时明确 fail-closed。
- legacy runtime mode 在任何 binding/native 加载前失败，不调用回退路径。
- 所有加载错误只返回固定分类诊断，不回显异常 payload、凭证或本地 artifact 路径。

## 3. 明确不做

- 不修改模型调用、ToolDriver、能力注册、Turn 业务逻辑或 UI。
- 不修改 SQLite、文件数据结构、Agent HTTP API 或 MCP。
- 不在 NoteMeld 内嵌 SDK 源码，也不修改独立 SDK 仓库的用户工作区。
- 不升级 SDK/schema 版本，不实现 ABI v2 计划能力。

## 4. 冲突分析

- 产品规则：不冲突；强化源码、CLI 和桌面共用单一 Rust runtime 的启动门禁。
- 数据模型：不修改表或字段；runtime descriptor 只同步真实 ABI 值。
- API inventory：不修改路径、请求或返回结构。
- known pitfalls：直接修复“Agent Host 与 SDK 版本漂移”，禁止静默 fallback 和敏感错误透传。
- 运行模式：源码 launcher、安装 CLI 和 PyInstaller sidecar 均使用相同 loader 契约。
- 打包：继续消费 `NOTEMELD_AGENT_SDK_WHEEL`；PyInstaller 继续从已安装 package 收集 metadata、ABI contract 和 native 资源。

## 5. 影响范围

- 后端：Agent SDK loader、Host 初始化、runtime descriptor 写读。
- 启动入口：`run_notemeld.sh`、`scripts/notemeld`。
- 测试：runtime loader、artifact/launcher、Host lifecycle、descriptor。
- 文档：当前架构与已知坑点同步真实 ABI 和校验事实。
- 前端、数据库、MCP、模型、ToolDriver：无改动。

## 6. 最小实施方案

1. loader 从安装包资源读取版本 metadata 和 `abi-v1.json`，不再读取包级 `ABI_VERSION` fallback。
2. loader 检查 packaged native 文件、ABI contract 与 Python binding signature 集合，并通过 native 导出函数复核 SDK/schema version。
3. 显式 native artifact 路径只用于已安装 wheel 的 native smoke；目录和不存在路径均拒绝，路径不进入错误信息。
4. 两个 launcher 直接调用同一 `AgentSdkRuntime.load()`，避免复制不完整的版本检查。
5. descriptor 和文档统一记录真实 ABI `1`；Host 初始化异常转换为固定安全诊断。

## 7. 数据、接口和 UI

- SQLite/文件结构/迁移：无。
- 公共 API/MCP：无。
- UI/交互：无。
- 本地历史数据：不读取、不迁移、不清理。

## 8. 测试与验收

- [x] SDK package 缺失时返回明确的 `Agent SDK is not installed`。
- [x] ABI contract 不为 `1` 时返回明确 ABI mismatch。
- [x] SDK version 或 schema version 不匹配时分别明确失败。
- [x] 兼容的 wheel metadata、ABI contract 和 native exports 可正常加载。
- [x] `python`、`python-oracle`、`legacy` 在调用 binding loader 前失败。
- [x] 源码与安装 launcher 均调用统一 loader，缺失/不兼容时 fail-closed。
- [x] 定向 Agent Host 测试、修改文件 compileall、shell syntax 和真实 wheel/native smoke 通过。

## 9. 风险和回滚

- 风险：旧环境中只安装了纯 Python 包、缺少 wheel metadata/ABI/native 的非正式 SDK 安装将被拒绝；这是目标要求的显式失败。
- 风险：跨架构 native library 会在启动时明确不可加载，不再延迟到首个 Turn。
- 回滚：回退本 Change Spec 对应 commit；不涉及数据回滚。
- 未覆盖：独立 SDK 后续正式发布 ABI v2 时，需要同时发布新的 versioned ABI contract，并显式升级 NoteMeld 常量和测试，不能靠兼容猜测自动放行。
