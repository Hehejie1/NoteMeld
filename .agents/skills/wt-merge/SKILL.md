---
name: wt-merge
description: 将 linked worktree 分支并入目标本地分支并清理 worktree。
---

# wt-merge：合入并清理（本地）

**先读 skill `$tabtin-dev-worktree`** 的「合入与清理」节，并参考 `wt-pause` 的分支状态约束。

## 合哪个 PR / 分支

调用 `/skill:wt-merge` 时附带的参数会由 Pi 追加到本 Skill 末尾，作为本次操作的上下文。

若上面为空，先向用户确认：合哪个本地分支、目标分支（默认本地 `main`，用户可指定其他本地分支）。

## 流程

1. 确认来源分支：默认当前分支（`git branch --show-current`）；若用户指定，以用户为准。
2. 确认目标分支：默认 `main`；若用户指定，先确认本地分支存在。
3. 检查来源分支与目标分支都无未提交遗留：`git status --short`。
4. 回到目标分支所在工作树，执行 `git switch <目标分支>`，再 `git merge --no-edit <来源分支>`。
5. 合并成功后执行 `bash scripts/wt.sh remove <来源分支>` 清理本流程建的 linked worktree。
6. 若合并冲突，停止并把冲突文件报给用户。
7. 向用户汇报：目标分支、merge 是否成功、冲突与清理结果。

## 注意

- 本流程仅用于本地合并；不执行 `fetch`、`push`、`pull`、`gh`。
- 与用户或系统要求一致时可切换目标分支；若用户未指定则用 `main`。
- 清理时先确认该来源 worktree 目录无未提交 / 未跟踪遗留，不满足即停下。

## 硬约束

**禁止** force push / `git reset --hard` / `git stash drop` 等破坏性 git；不确定时先停下问用户。

完整支线流程：`/wt-start` → `/wt-verify` → `/wt-merge`。
