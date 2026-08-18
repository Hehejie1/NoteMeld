---
name: wt-start
description: 为指定任务创建 linked worktree，在其中完成需求开发与代码 review，最后回报结果。
---

# wt-start：开 worktree 并在其中完成任务

该流程用于本地开发隔离，仅使用 Git 与 worktree；不依赖 `tabtin`、`scripts/wt.sh` 或其他外部脚本。

**本 skill 不是只建目录就结束。** 创建 worktree 只是第 1 阶段，创建成功后必须立刻进入该 worktree 完成用户需求、自查 review，最后一次性回报。

## 零追问原则（最重要）

用户只描述需求，**不需要提供分支名**。

- **禁止**向用户询问 `task_branch`、`worktree_path`。分支名必须由 Agent 从需求描述自动生成。
- **禁止**向用户询问 `base_branch`。用户显式给出就用，否则一律用本地 `main`。
- **禁止**创建完 worktree 就把控制权交回用户等待下一步指令。
- 只有在下列情况才允许停下来问用户：
  - 仓库不干净且必须切分支才能继续（有未提交改动会被切分支影响）。
  - `base_branch` 在本地不存在。
  - 目标 worktree 路径已存在且非空。
  - 需求本身有歧义、存在多种互斥解读，无法安全实现。

## 任务上下文

`/skill:wt-start` 的参数全部可选：

- `task_branch`：开发分支名。缺失则自动生成，不追问。
- `base_branch`：基线分支，默认本地 `main`。
- `worktree_path`：默认 `../notemeld-<task_branch 中 / 替换为 ->`。
- `reuse_existing`：是否复用已存在的空目录，默认 `true`。

## 分支名自动生成规则

1. 从用户需求描述提取 2-4 个英文关键词（中文需求先意译成英文），小写，用 `-` 连接，总长 ≤ 40 字符。
2. 按需求性质选前缀：新增能力 `feat/`，修 Bug `fix/`，重构/整理 `refactor/`，文档 `docs/`，杂项 `chore/`。
3. 示例：
   - "所有中间数据放 vector_db，日志放 logs" → `refactor/unify-storage-paths`
   - "修复上传大文件超时" → `fix/upload-large-file-timeout`
4. 冲突检测（必须执行）：
   - `git branch --list`、`git worktree list` 检查分支名与目标路径是否已被占用。
   - 若冲突，追加 `-2`、`-3`… 直到分支名与路径都空闲。
5. 生成结果直接使用，不需要用户确认。

## 目标分支解析（本地优先）

- 基线分支默认 `main`，支持 `main`、`release/*` 或其他本地存在的分支名。
- 只走本地：不执行 `fetch/pull/push`，不处理远端分支。
- 不自动创建基线分支；基线分支不存在时停止并提示。

## 阶段一：创建 worktree

1. 收集上下文（可并行执行）
   - `git rev-parse --show-toplevel`
   - `git branch --show-current`
   - `git status --porcelain`
   - `git branch --list`
   - `git worktree list`
2. 确定 `base_branch`（用户给定 > 本地 `main`）；本地不存在则停止并提示。
3. 按上文规则生成 `task_branch` 与 `worktree_path`，完成冲突检测。
4. 若当前分支不是 `base_branch` 且工作区干净：`git switch <base_branch>`；工作区不干净则停止并提示用户先处理。
5. 创建 worktree：`git worktree add <worktree_path> -b <task_branch> <base_branch>`。
   - 目标路径已存在且为空：按 `reuse_existing` 复用。
   - 目标路径非空：返回占用信息并停止（默认不自动清空）。
6. 简要告知已创建的路径与分支，然后**立即继续阶段二，不等待用户确认**。

## 阶段二：在 worktree 中完成需求

工作目录从此固定为 `<worktree_path>`（所有 RunCommand 用 `cwd=<worktree_path>`），**禁止**在主仓库路径下改任何文件。

1. 先读 `AGENTS.md`、`CLAUDE.md` 与 `docs/system/` 下相关文档，再搜索现状代码与测试。
2. 用 TodoWrite 拆解步骤，按最小改动原则实现需求。
3. 需求涉及架构、数据模型、API、产品规则变化时，同步更新 `docs/system/`。
4. 按改动范围选择验证命令（在 worktree 内执行）：
   - `python3 -m compileall backend/app`
   - `pytest backend/tests`
   - `cd frontend && pnpm test:contracts`
   - `cd frontend && pnpm build`
   - `scripts/run_core_regression.sh`
5. 需要前端依赖时可在该 worktree 执行 `pnpm install`；**禁止**启动 dev server 或 Electron 进程。

## 阶段三：代码 review

1. 在 worktree 内跑 `git status --porcelain` 与 `git diff <base_branch>...HEAD`（或未提交时 `git diff`）拿到完整改动面。
2. 调用 `TRAE-code-review` skill 对该 diff 做审查；无法调用时按以下清单人工自查：
   - 是否有超出需求范围的无关改动、无关重构、被误删能力。
   - 是否残留调试代码、临时日志、注释掉的旧逻辑、未使用导入。
   - 是否破坏源码启动、CLI、桌面、MCP、迁移、Wiki、上传、打包发布任一入口。
   - 是否引入 `docs/system/known-pitfalls.md` 中已记录的问题。
   - 是否泄露 API Key、Cookie、token、本地绝对路径等敏感信息。
   - 边界与并发：取消、超时、文件写入的 race condition 与脏状态。
3. review 发现的问题当场修掉并重跑相关验证；只有确认无阻塞问题才进入阶段四。
4. 是否 `git commit` 由用户决定：用户未明确要求提交时保留工作区改动，不自动 commit。

## 阶段四：回报

只在阶段三通过后向用户输出一次总结：

- base_branch: `<base_branch>`
- task_branch: `<task_branch>`（自动生成 / 用户指定）
- worktree_path: `<path>`
- 需求实现摘要：改了哪些文件、关键逻辑变化
- 验证证据：实际执行的命令与结果（不得编造）
- review 结论：发现的问题与处理方式，遗留风险
- 下一步：`确认无误后执行 /wt-merge source=<task_branch> target=<base_branch>`

## 快速命令

```bash
git switch main
git worktree add ../notemeld-refactor-unify-storage-paths -b refactor/unify-storage-paths main
```

## 注意

- 阶段二/三的所有命令都必须在 `<worktree_path>` 下执行，避免污染主工作树。
- 不启动 dev server / Electron 进程。
- 遇到路径、分支或未跟踪文件冲突时中止，不自动修复，避免误删。
- 没有实际执行验证命令，不得声称"已验证通过"。

## 硬约束

- **禁止** `git stash drop` / `git reset --hard` / force push。
- **禁止** 自动 `rm -rf` 已存在非空目录。必要清理必须人工确认并执行。
- **禁止** 因为缺少分支名而中断流程去追问用户。
- **禁止** 只创建完 worktree 就结束本次任务。
- **禁止** 未做 review 就回报完成。
