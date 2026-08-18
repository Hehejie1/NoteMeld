---
name: wt-merge
description: 将 linked worktree 分支并入目标本地分支，并在成功后清理 worktree 或本地分支。
---

# wt-merge：合入并清理（本地）

该流程用于本地 `worktree` 场景合并，不依赖 `tabtin`、`scripts/wt.sh` 或任何外部服务。
默认行为：**合并成功后清理来源 worktree，不默认删除来源分支**。

## 触发上下文

`/skill:wt-merge` 可附带参数，参数未提供时按默认值处理：

- `source`：来源分支，默认当前分支。
- `target`：目标分支，默认本地 `main`。
- `delete_worktree`：是否删除来源 worktree，默认 `true`。
- `delete_branch`：是否删除来源本地分支，默认 `false`。
- `worktree_path`：可选，显式指定来源 worktree 的路径。

若参数缺失，先向用户确认来源分支、目标分支、`delete_worktree`、`delete_branch`。

## 注意边界

- 仅本地操作，禁止执行 `fetch/pull/push/gh`。
- 若冲突，立即停止，不执行任何清理。
- 分支删除默认不启用 `-D`，先尝试安全删除（`git branch -d`）后再视需要确认执行更激进命令。
- 不确定时停下并确认用户。

## 流程

1. 校验仓库上下文与分支参数
   - 执行 `git rev-parse --show-toplevel` 与 `git branch --show-current`。
   - 确认来源与目标分支存在（`git branch --list <branch>`）。
   - 若 `source == target`，停止并要求修正参数。
2. 先验工作树干净度
   - 检查当前工作树：`git status --short`，若有未提交变更暂停。
   - 若用户指定了来源工作树路径，额外确认该路径无未提交/未跟踪内容。
3. 切到目标分支并合并
   - `git switch <target>`
   - `git merge --no-edit <source>`
4. 冲突处理
   - 若冲突，报告冲突文件与状态，要求用户处理；**不执行清理**。
5. 合并成功后的清理（按顺序）
   - 先 worktree：`git worktree list` 查到 source 关联路径（或使用显式 `worktree_path`），执行 `git worktree remove --force <path>`。
   - 再 branch：若 `delete_branch=true`，先执行 `git branch -d <source>` 进行安全删除。
   - 若 `git branch -d` 因未完全合并失败，暂停并说明原因，不执行强制删除。
6. 汇报结果
   - 回报来源/目标、merge 状态、worktree 删除状态、branch 删除状态、剩余需人工处理项。

## 输出模板（给用户）

- 来源分支：`<source>`
- 目标分支：`<target>`
- 合并：`成功/失败`
- 是否已清理 worktree：`是/否`
- 是否已删除来源分支：`是/否`
- 冲突文件：`列表`（如有）
- 备注：`未找到 worktree / 未满足清理条件 / 其余注意事项`

## 硬约束

**禁止** `git push --force`、`git reset --hard`、`git stash drop` 等破坏性命令。

完整支线流程：`/wt-start` → `/wt-verify` → `/wt-merge`。
