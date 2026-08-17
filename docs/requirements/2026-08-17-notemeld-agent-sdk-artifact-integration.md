# NoteMeld 消费独立 Agent SDK 产物并统一 CLI

日期：2026-08-17
作者 / Agent：Codex
状态：Planned
关联需求：`2026-08-14-universal-agent-sdk-unified-cli.md`、`2026-08-16-agent-sdk-project-extraction.md`
关联系统文档：`current-architecture.md`、`product-rules.md`、`data-model.md`、`api-inventory.md`、`known-pitfalls.md`

## 1. 原始需求

用户要求 NoteMeld 接入 `notemeld-agent-sdk` 的编译产物，UI 与 CLI 通过同一 Agent Host、同一数据库和同一会话工作；同时清理 NoteMeld 内重复的 Python SDK 基础包及已经不再承担生产职责的代码。

## 2. 背景和问题

- 当前用户是 NoteMeld 的本地桌面/CLI 用户与 SDK 维护者。
- 独立 SDK 已能构建 Rust native library 和带 native library 的 Python wheel。
- NoteMeld Agent v1 已调用外部 `notemeld_agent_sdk.runtime`，但源码启动和已安装 CLI 对 wheel 的安装契约不一致。
- NoteMeld 仓库仍包含一份完整 `agent-sdk/` 副本、Python oracle 回滚入口和 legacy Python Agent core；其中 legacy core 仍被旧聊天和工具模块引用，不能无条件删除。
- 痛点是产物来源不唯一、CLI 能力不完整、清理边界不明确，容易形成两套 Agent 行为。

## 3. 目标结果

1. NoteMeld 的源码启动、桌面/安装启动和 CLI 都消费同一版本化 SDK wheel/native artifact。
2. `notemeld agent` 通过 `/api/agent/v1` 创建/恢复同一 Conversation，支持单次与交互模式、模型切换和会话管理。
3. SDK 缺失、文件不存在、版本不匹配或 native library 不可加载时 fail-closed，给出可操作错误。
4. 删除 NoteMeld 内不再是事实源的重复 Python SDK binding、无效 Python oracle 回滚入口和对应测试/构建引用。
5. 对仍有生产调用方的 `backend/app/agent/core` 建立“生产 import 归零才允许删除”的门禁，迁移期间不丢工具、旧聊天、MCP 或笔记能力。

## 4. 非目标

- 本轮不重新实现 SDK Rust core。
- 不改变 SQLite 表、Conversation/Message/Turn/Event 字段语义。
- 不做跨设备 Agent 调用、Harbor 接入或移动端 NoteMeld UI。
- 不为了追求目录干净而删除仍有生产调用方的 legacy core。
- 不声称 Android/OpenHarmony 真机验证。

## 5. 当前系统事实

- `backend/app/agent_host/runtime.py` 已从安装包或显式开发路径导入 `notemeld_agent_sdk.runtime`。
- `backend/app/agent_host/native_executor.py` 已通过 SDK native runtime 执行 Agent v1 Turn；当前只接入 model driver，tool driver 仍返回 `invalid_input`。
- `backend/app/routers/agent.py`、`agent_store` 和 `conversation_store` 已提供共享会话、Turn 和事件入口。
- `scripts/notemeld-agent.py` 是 Agent v1 HTTP 客户端，不包含另一套 Agent loop。
- `packaging/scripts/build-backend-macos.sh` 和 PyInstaller spec 已支持外部 wheel/native resource。
- `run_notemeld.sh` 尚未在源码启动时安装/校验外部 SDK；`scripts/notemeld` 此前也未完整校验安装结果。
- `agent-sdk/bindings/python` 是独立 SDK 拆分前的仓内副本；SDK CI/契约测试仍引用它。
- `backend/app/agent/core` 仍被 `agent_service`、`sse_bridge`、工具/Skill/MCP adapter 及其测试引用。
- 相关坑点：不能静默 fallback 到两套 Agent；不能绕过桌面 ready gate；不能把 API key/provider payload 写入错误；不能删除仍被旧入口调用的能力。

## 6. 用户故事

- 作为源码用户，我希望只提供一个 SDK wheel 路径即可启动 NoteMeld，而不需要手动调整 `PYTHONPATH`。
- 作为桌面/CLI 用户，我希望 `notemeld agent` 与 UI 看到同一会话、模型和回答。
- 作为维护者，我希望 NoteMeld 不再维护一份重复 Python SDK runtime，以免独立 SDK 与应用内副本漂移。

## 7. 验收标准

1. GIVEN NoteMeld 虚拟环境未安装 SDK，WHEN 设置有效 `NOTEMELD_AGENT_SDK_WHEEL` 并源码启动，THEN wheel 被以 `--no-deps` 安装且 runtime import/version 校验通过。
2. GIVEN SDK 已正确安装，WHEN 再次启动，THEN 不重复安装 wheel。
3. GIVEN SDK 未安装且未提供 wheel，WHEN 启动源码版或已安装版，THEN 启动 fail-closed 并提示 `NOTEMELD_AGENT_SDK_WHEEL`。
4. GIVEN wheel 路径不存在或安装后不可导入，WHEN 启动，THEN 返回明确错误且不启动 Agent Host。
5. GIVEN NoteMeld Host 运行，WHEN 执行 `notemeld agent -p "问题" --model <name>`，THEN CLI 创建 Agent v1 Turn、输出唯一终态并复用同一 Conversation 数据。
6. GIVEN 交互式 CLI，WHEN 使用 `/new`、`/resume`、`/sessions`、`/model`、`/exit`，THEN 会话和模型状态按命令更新；CLI 不包含 Agent loop。
7. WHEN SDK runtime mode 为 `python`、`python-oracle` 或 `legacy`，THEN Host 拒绝启动而不是静默切换实现。
8. WHEN 删除重复 Python SDK binding，THEN NoteMeld 生产代码、启动脚本和打包脚本只从外部 wheel/import package 消费 runtime。
9. WHEN 搜索 `backend/app`，THEN任何被删除模块的生产 import 数量为零；若不为零，该模块必须保留并记录后续迁移任务。
10. WHEN 执行 focused tests、shell syntax、Python compile 和 native wheel smoke，THEN全部通过后才能声明完成。

## 8. 输入 / 输出样例

### 输入

```bash
NOTEMELD_AGENT_SDK_WHEEL=/path/notemeld_agent_sdk-0.1.0-...whl ./run_notemeld.sh
notemeld agent -p "总结这个会话" --model gemma3:4b --output json
notemeld agent --conversation conv-123
```

### 输出

- 启动日志只显示 wheel 安装/校验结果，不打印密钥或原始 provider payload。
- CLI text/json/jsonl 输出来自 `/api/agent/v1` 事件流。

### 失败样例

```text
NoteMeld ERROR: notemeld-agent-sdk is not installed. Set NOTEMELD_AGENT_SDK_WHEEL to the compiled wheel.
```

## 9. 约束

- 平台：本地至少验证当前 macOS；脚本保持 Linux/macOS shell 兼容。
- 性能：已安装 SDK 时只做一次 import/version probe，不重复 pip install。
- 隐私：错误与日志不得包含 provider key、token、authorization header 或原始响应。
- 兼容性：保留 Conversation/Turn 数据、UI、CLI、MCP、Wiki、上传、迁移和打包入口。
- 第三方依赖：NoteMeld 不新增 SDK runtime 第三方依赖；wheel 使用独立 SDK 已审核依赖。

## 10. 边界场景

- SDK wheel 文件存在但架构错误：安装或 import probe 必须失败。
- backend 已运行但 SDK 未安装：CLI 不得悄悄启动第二套 Agent。
- CLI 指定不存在会话：显示稳定错误，不创建同名伪会话。
- CLI JSON/JSONL：stdout 不混入日志。
- 旧 core 尚有调用方：保留并在 Spec 中列出清理门禁。

## 11. 开放问题

无阻塞问题。删除采用依赖门禁，不猜测“无关代码”。

## 12. 与系统事实的冲突检查

- `product-rules.md`：不冲突；统一 Agent 有利于 AI 编译知识与人验证。
- `data-model.md`：不改变数据模型。
- `api-inventory.md`：沿用 `/api/agent/v1`，仅扩充 CLI 参数/命令文档。
- `known-pitfalls.md`：通过 fail-closed、唯一产物源、生产 import 门禁避免静默 fallback 和误删能力。
- 本地数据/线上服务：不迁移或删除数据；只影响本地启动、CLI 与打包输入。

## 13. Superpowers 交接

- 是否已达到 Ready for Plan：是，且已生成 Plan/Spec。
- 计划必须覆盖：验收标准 1–10。
- 必须补充：真实 wheel import/native fake turn、CLI HTTP fake-host 测试、删除前后 import 搜索。

## 14. Requirement Quality Gate

- [x] 用户、场景、痛点与价值明确。
- [x] 当前事实来自代码与系统文档。
- [x] 正常、失败和边界路径均有可验证标准。
- [x] 数据/API/known pitfalls 冲突已检查。
- [x] 非目标与删除门禁明确。
- [x] 无密钥、token 或隐私数据。
