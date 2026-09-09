# Agent SDK 独立项目拆分执行计划

## 阶段 1：冻结边界

- 确认独立项目名为 `notemeld-agent-sdk`，Rust crate/package 版本继续从 `0.1.0` 起步。
- 将 `agent-sdk/` 内 Rust、schema、fixtures、FFI、binding 和 SDK 专属脚本列入 SDK；NoteMeld adapter、API、数据库、UI、桌面和产品工具留在 NoteMeld。
- 用 `git subtree split --prefix=agent-sdk` 建立独立仓库历史，不在 NoteMeld 中直接删除原目录，直到 SDK 首个本地验收版本完成。

## 阶段 2：完成独立 Rust SDK

- 补齐 workspace README、版本策略、错误码/schema/ABI 兼容规则。
- 增加统一 `cargo test --workspace`、fixture conformance 和 fake driver smoke 入口。
- 将 CLI crate 纳入 SDK workspace，保证 Rust CLI 使用同一 canonical loop。
- 保留各 crate 的单元/契约测试，禁止 SDK 依赖 NoteMeld Python 模块。

## 阶段 3：完成独立 Python SDK

- 为 `bindings/python` 增加 `pyproject.toml`、包版本、类型声明和 native resource layout。
- 统一 `Runtime`、事件迭代、driver 回调、cancel、steer、close 和错误类型。
- 增加无 native、版本不匹配、callback failure、唯一终态和 fake turn 的 Python 单元测试。
- 支持开发模式通过环境变量指定 native library，发布模式从包资源加载。

## 阶段 4：本地验收与发布产物

- 设计一条不依赖 NoteMeld 的本地命令，顺序执行 Rust tests、Python tests、ABI/schema checks 和 fake turn。
- 生成 macOS 当前架构 native artifact；其他平台只保留 CI 构建矩阵，不阻塞 SDK 逻辑验收。
- 记录验证证据和版本 manifest，产出第一个可被 NoteMeld 消费的 SDK artifact。

## 阶段 5：重新接入 NoteMeld

- NoteMeld 通过版本化 Python package/native artifact 接入，不再把 SDK 源码作为 backend 的隐式内部模块。
- `backend/app/agent_host` 只负责 NoteMeld Model/Tool/Storage adapter、Host 生命周期和权限策略。
- 完成 TurnManager 到 Rust runtime 的真实执行桥，再迁移 UI、CLI、桌面启动和打包。
- SDK 稳定后再单独建立 Harbor integration Change Spec。

## 回滚

任一阶段失败时保留 NoteMeld 当前 `agent_host` 与 `python-oracle` 回滚模式；不删除旧目录、不改变现有聊天入口，直到独立 SDK artifact 和本地 fake turn 验收完成。
