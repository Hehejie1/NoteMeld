# Change Spec：wt-start / wt-merge 本地分支驱动的 worktree 工作流改造

日期：2026-08-16
状态：Implemented

## 0. 预检查

- [x] 已阅读 `docs/system/current-architecture.md`
- [x] 已阅读 `docs/system/product-rules.md`
- [x] 已阅读 `docs/system/data-model.md`
- [x] 已阅读 `docs/system/api-inventory.md`
- [x] 已阅读 `docs/system/known-pitfalls.md`
- [x] 已搜索相关代码与测试（聚焦 `.agents/skills` 和 `docs/system`）
- [x] 已确认现有流程不涉及数据库/API 变更
- [x] 已确认影响本地执行/组织行为，不改动线上服务

## 1. 当前系统现状

- 相关模块：`.agents/skills/wt-start`、`.agents/skills/wt-merge`。
- 相关入口：`/skill:wt-start`、`/skill:wt-merge`。
- 相关数据：仅本地 git 工作树与分支；不涉及数据库/文件表。
- 相关 API：无。
- 当前行为：`wt-start` 的文档默认按 release 分支并携带远端 fetch/push/gh 步骤；`wt-merge` 文档以 GitHub PR merge 与 auto-merge 为中心。
- 当前限制：与用户要求“只做本地操作、目标分支默认 main、可指定覆盖分支”的行为不一致。

## 2. 本次目标

- 用户问题：当前指令流程偏远端 PR，且默认目标基线为 release 分支，不符合“本地 main-first 且可切分支”的需求。
- 成功后的用户可见行为：`wt-start` 可按用户指定目标分支（默认 main）切换并建起 linked worktree；`wt-merge` 在本地将来源分支合并到目标分支并清理 worktree。
- 系统内部行为：不再包含远端 `fetch/push/gh` 命令依赖；合并链路仅执行本地分支和本地工作树操作。
- 必须保留的旧行为：`wt-start` / `wt-merge` 的“仅检出、禁止在支线装依赖、保留 worktree 清理”约束。

## 3. 明确不做

- 不做 GitHub PR 自动创建、更新或 close 的远端操作。
- 不改 git 的数据库/API 层逻辑。
- 不改动 `wt-pause` / `wt-verify` 的具体执行逻辑，仅在规则文案中参考其约束。

## 4. 冲突分析

- 与 `product-rules.md`：不影响产品主功能与数据处理边界。
- 与 `data-model.md`：无数据模型字段触及。
- 与 `api-inventory.md`：无接口变更。
- 与 `known-pitfalls.md`：无历史坑点新增，且继续保持本地工作树清理与低风险 git 操作。
- 影响发布与本地运行入口：无。

## 5. 影响范围

- 后端文件：无。
- 前端文件：无。
- 桌面/Tauri 文件：无。
- 数据库模型/迁移：无。
- 文件系统结构：无。
- API 调用方：无。
- MCP 工具：无。
- 测试：本次为文档行为改造，无代码回归测试项新增。
- 文档：`.agents/skills/wt-start/SKILL.md`、`.agents/skills/wt-merge/SKILL.md`、本 change spec。

## 6. 实施方案

### 文档改动

- `wt-start`：新增“目标分支解析”规则，默认 local `main`，明确只本地切换分支与仅做 worktree 检出，不再执行远端 PR 前置。
- `wt-merge`：重写为本地合并流程，默认目标 `main`，支持用户指定目标分支，取消 gh/远端命令。

## 7. 数据变更

- 无新增字段/文件结构。
- 回滚：还原本地两个技能文档即可。

## 8. 接口变更

- 无新增、无修改、无删除 API。
- 本次变更不涉及 `docs/system/api-inventory.md` 的更新。

## 9. 测试方案

- 文档层：校验新增指令表述与原 hard constraints 是否一致。
- 人工验收：在本地运行 `/skill:wt-start` 与 `/skill:wt-merge` 场景下，确认不触发远端命令。

## 10. 验收标准

- [x] `wt-start` 默认目标分支为本地 `main`，支持用户指定替代本地分支。
- [x] `wt-start` 的流程不包含远端 fetch/push/gh 步骤。
- [x] `wt-merge` 默认合并到本地 `main`，并允许用户指定其他本地目标分支。
- [x] `wt-merge` 文档中不再要求 gh auto-merge、gh issue 同步。
- [x] `wt-merge` 明确继续执行 worktree 清理与冲突停顿。

## 11. 风险与回滚

- 风险：文档与实际执行者理解偏差，可能导致实际仍执行远端操作。
- 降级：按本地约束逐条复盘，确认指令执行来源。
- 回滚：恢复本次三份文档到修改前内容。

## 13. Agent 必答问题

- 影响模块：`wt-start` / `wt-merge` 本地流程文档。
- 当前系统是否已有类似能力：已有 linked worktree 与远端 PR 流程；本次降到本地优先。
- 与产品规则冲突：无。
- 与数据模型语义冲突：无。
- 重新引入 known-pitfalls：未见。
- 影响本地数据/线上服务：仅本地 git 工作流行为，无线上服务改动。
- 最小可行改动：仅改 2 个 SKILL 文档与 1 个 Change Spec。
- 需要补哪些测试：文档一致性人工验收为主，本次不涉及代码变更。

