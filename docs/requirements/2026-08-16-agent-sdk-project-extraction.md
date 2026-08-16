# 独立 Agent SDK 项目拆分与 NoteMeld 延后接入

状态：Ready for Plan

## 原始意图

将当前仓库中的 `agent-sdk/` 拆成可独立维护、构建、测试和发布的 Agent SDK 项目。先完成 Rust SDK 及可安装的 Python SDK，并能在本地用 fake driver 验证；SDK 稳定后再接入 NoteMeld 的后端、前端、CLI 和桌面端。

## 当前事实

- NoteMeld 当前是一个包含 `backend/`、`frontend/`、`desktop/`、`scripts/`、`packaging/` 和 `agent-sdk/` 的单仓库。
- `agent-sdk/` 已有 Rust workspace、事件 schema、FFI、跨平台 binding 源码、fixtures 和构建脚本。
- Python binding 当前是 ctypes 运行时模块，缺少独立项目的 Python 构建元数据和发布入口。
- NoteMeld 的 `backend/app/agent_host/` 已开始依赖 SDK，但真实执行桥仍未闭环。

## 目标

1. 建立独立 `notemeld-agent-sdk` 项目，SDK 源码不依赖 NoteMeld backend/frontend/desktop。
2. Rust workspace 可独立执行格式化、单元测试、契约测试和 fake-driver smoke。
3. 提供可安装的 Python SDK，包含版本/schema 校验、native library 加载、事件订阅、driver 回调、取消和关闭。
4. 提供一条本地验收命令，完成 Rust 测试、Python 单元测试和 Python fake turn。
5. SDK 稳定后，NoteMeld 只通过版本化 Python SDK/native artifact 接入。

## 非目标

- 本阶段不接入 Harbor。
- 本阶段不迁移 NoteMeld UI、数据库或桌面逻辑到 SDK 项目。
- 不在 SDK 中实现 NoteMeld Wiki、MCP、Skill、ConversationStore 等产品能力。
- 不要求本阶段完成 Android/Harmony 真机验证。

## 验收标准

- GIVEN 独立 SDK checkout，WHEN 执行 Rust workspace 命令，THEN 不需要 NoteMeld backend 环境即可通过 SDK 单元/契约测试。
- GIVEN Python 3.11 环境和当前平台 native artifact，WHEN 安装 Python SDK 并运行 fake driver，THEN 能收到统一事件并得到唯一终态。
- GIVEN 缺少或版本不匹配的 native library，THEN Python SDK 返回稳定、脱敏的错误。
- GIVEN NoteMeld 暂时不安装 SDK，THEN NoteMeld 旧 Agent/聊天链路仍可按回滚开关运行。
- SDK 与 NoteMeld 的边界通过版本化 schema、ABI manifest 和 package contract 测试锁定。

## 风险与回滚

- 风险：直接移动目录会丢失历史或造成 SDK/NoteMeld 依赖漂移。采用 `git subtree split` 保留历史，并在 NoteMeld 中暂时保留兼容适配层。
- 风险：Python wheel 与 native library 版本不一致。安装时强制校验 SDK、schema、ABI 三者版本。
- 回滚：NoteMeld 保留 Python oracle/legacy mode；SDK 拆分只先新增独立项目，不立即删除原接入适配层。
