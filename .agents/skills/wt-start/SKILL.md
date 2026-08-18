---
name: wt-start
description: 为指定任务创建 linked worktree，从本地基线分支隔离开发。
---

# wt-start：开 worktree 开发

该流程用于本地开发隔离，仅使用 Git 与 worktree；不依赖 `tabtin`、`scripts/wt.sh` 或其他外部脚本。

## 任务上下文

`/skill:wt-start` 可附带参数，参数缺失则向用户确认：

- `task_branch`：开发分支名（必须）
- `base_branch`：基线分支，默认本地 `main`
- `worktree_path`：可选，默认 `../notemeld-<task_branch>`
- `reuse_existing`：是否复用已存在且为空的目录，默认 `false`
- `create_if_missing`：基线分支不存在时是否允许创建本地分支，默认 `false`

## 目标分支解析（本地优先）

- 基线分支默认 `main`，支持 `main`、`release/*` 或其他本地存在的分支名。
- 只走本地：不执行 `fetch/pull/push`，不处理远端分支。
- 仅在用户明确允许时才创建新分支。

## 流程

1. 校验参数与当前仓库上下文
   - `git rev-parse --show-toplevel`
   - `git branch --show-current`
   - 确认 `task_branch` 不为空。
2. 检查基线分支
   - 解析 `base_branch`，若不存在，按 `create_if_missing` 决定是否创建或停止。
3. 切到基线分支：`git switch <base_branch>`。
4. 处理开发分支与 worktree
   - 若 `task_branch` 已存在：
     - 若目标路径不存在：`git worktree add <worktree_path> <task_branch>`。
     - 若目标路径存在且空目录：按 `reuse_existing` 决定复用或停止。
     - 若目录非空：返回占用信息并停止（默认不自动清空）。
   - 若 `task_branch` 不存在：
     - 若不允许创建：停止并提示用户确认。
     - 允许创建则：`git worktree add --detach <worktree_path> -b <task_branch> <base_branch>`。
5. 回报新路径并告知下一步动作：去该 worktree 开发；开发完成后调用 `/wt-merge source=<task_branch> target=<base_branch>`。

## 快速命令

```bash
git switch main
git worktree add ../notemeld-fix/task-123 -b fix/task-123 main
```

## 输出模板

- base_branch: `<base_branch>`
- task_branch: `<task_branch>`
- worktree_path: `<path>`
- branch_exists: `true/false`
- reused_path: `true/false`
- 是否已创建新分支: `true/false`
- 下一步:
  - `开发完成后执行 /wt-merge source=<task_branch> target=<base_branch>`

## 注意

- 不在新 worktree 执行 `pnpm install` 或启动 dev server / Electron 进程。
- 遇到路径、分支或未跟踪文件冲突时中止，不自动修复，避免误删。
- 若需回到主工作流，先在新工作树完成切换回基线上下文再调用 `/wt-merge`。

## 硬约束

- **禁止** `git stash drop` / `git reset --hard` / force push。
- **禁止** 自动 `rm -rf` 已存在非空目录。必要清理必须人工确认并执行。
