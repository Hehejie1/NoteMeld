# NoteMeld Agent SDK 产物接入执行计划

Canonical requirement：`../../requirements/2026-08-17-notemeld-agent-sdk-artifact-integration.md`

## 顺序与依赖

1. 冻结 artifact/CLI/删除边界与回归门禁。
2. 统一源码启动、安装启动和桌面打包的 wheel 安装/校验契约。
3. 补齐统一 CLI 的单次、交互、会话和模型命令。
4. 移除无效 Python oracle fallback；验证 Rust SDK 为 Agent v1 唯一执行核心。
5. 清理重复 Python SDK 副本及其 NoteMeld 内引用；独立 SDK 仓库继续拥有 wheel 构建/发布。
6. 运行生产 import 审计；仅删除零调用模块。仍有调用者的 legacy Agent core进入明确后续清单。
7. 同步系统文档、验证证据并提交 worktree 分支。

## 可并行任务

- A：启动/打包 artifact 契约与 focused tests。
- B：CLI 命令与 fake HTTP Host 单元测试。
- C：Python fallback/重复代码依赖图与安全清理。

三项不得编辑同一文件；完成后由主 Agent 统一集成和真实验证。

## 风险与回滚

- wheel 架构或版本错误：import/version probe fail-closed；恢复上一个有效 wheel 即可。
- CLI 行为漂移：保留 `/api/agent/v1` 为唯一协议，fake host 锁定请求/输出。
- 清理过度：任何删除前必须 `rg` 证明生产 import 为零；否则保留。
- 独立 SDK CI 尚未迁出：不删除仍承担 SDK 构建职责的文件，先记录下一独立迁移任务。

## 完成定义

- Spec 中所有 MUST 项完成。
- focused tests、shell syntax、Python compile、external wheel/native smoke 均有证据。
- 文档与源码一致；无未解释的生产依赖或静默 fallback。
