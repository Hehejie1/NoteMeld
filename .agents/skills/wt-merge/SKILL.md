---
name: wt-merge
description: 将 linked worktree 分支并入目标本地分支，并在成功后清理 worktree 或本地分支。
---

# wt-merge：合入并清理（本地）

该流程用于本地 `worktree` 场景合并，不依赖 `tabtin`、`scripts/wt.sh` 或任何外部服务。
默认行为：**合并成功后清理来源 worktree，不默认删除来源分支**。

## 前置检查：必须在主工作树执行（最容易出错的一点）

流程第 4 步要 `git switch <target>`，而 `target`（通常是 `main`）已被主工作树占用。在 linked worktree 里执行会直接
`fatal: 'main' is already used by worktree at ...`。

- 执行 `git rev-parse --git-dir --git-common-dir`；两者不相等 ⇒ 当前在 linked worktree。
- 此时**不要**尝试任何 switch/merge，先 `cd <main_root>`（`git worktree list` 第一行路径）再继续；无法自动切换则停止并提示用户。

## 触发上下文

`/skill:wt-merge` 参数全部可选，缺失按下述规则自动推断，**不追问用户**：

- `source`：来源分支。推断顺序：用户显式给定 > `git worktree list` 中唯一的 linked worktree 所在分支 > 若有多个 linked worktree 则列出让用户选。**不要**默认取"当前分支"（在主工作树里它就是 `main`，会等于 `target`）。
- `target`：目标分支，默认本地 `main`。
- `delete_worktree`：是否删除来源 worktree，默认 `true`。
- `delete_branch`：是否删除来源本地分支，默认 `false`。
- `worktree_path`：可选，显式指定来源 worktree 的路径；缺失则从 `git worktree list` 反查 `source` 对应路径。

## 注意边界

- 仅本地操作，禁止执行 `fetch/pull/push/gh`。
- 若冲突，立即停止，不执行任何清理。
- 分支删除默认不启用 `-D`，先尝试安全删除（`git branch -d`）后再视需要确认执行更激进命令。
- 不确定时停下并确认用户。

## 流程

1. 校验仓库上下文与分支参数
   - 完成上文「前置检查」，确保 cwd 在主工作树。
   - `git worktree list`、`git branch --list` 确认 `source` / `target` 都存在。
   - 若 `source == target`，停止并要求修正参数。
2. **来源 worktree 干净度校验（关键防线，禁止跳过）**
   - `git -C <worktree_path> status --porcelain`。
   - 只要存在**已跟踪文件的未提交改动**（输出中非 `??` 开头的行），立即停止并提示用户先在该 worktree 提交。
     原因：`git merge` 只合并 commit，未提交改动不会被合并，git 会报 "Already up to date."，随后清理 worktree 会**静默删除全部工作成果**。
   - `??` 未跟踪项若只是 bootstrap 产物（`.venv` / `node_modules` 软链、`.env`）可忽略；出现其他未跟踪文件要列出来让用户确认是否为需要保留的新代码。
   - 再校验主工作树：`git status --short`，有未提交改动则暂停（merge 会动工作区）。
3. 确认 source 领先于 target
   - `git rev-list --count <target>..<source>`；结果为 0 说明没有可合并的提交，停止并说明（防止把"空合并"当成功而触发清理）。
4. 切到目标分支并合并
   - `git switch <target>`
   - `git merge --no-edit <source>`
   - 校验结果：`git rev-list --count <target>..<source>` 应为 0，且 `git log -1 --oneline` 含预期提交。
5. 冲突处理
   - 若冲突，报告冲突文件与状态，要求用户处理；**不执行清理**。
6. 合并成功后的清理（按顺序）
   - 确认 cwd 不在待删除的 `<worktree_path>` 内部（否则删除后终端 cwd 失效，后续命令全部报错）；必要时先 `cd <main_root>`。
   - 先 worktree：`git worktree remove <path>`，**不加 `--force`**。
     - `--force` 会连同未提交/未跟踪内容一起删掉，与"禁止自动删除用户数据"冲突。
     - 命令失败说明该 worktree 仍有内容（通常是 bootstrap 软链或 `.env`）。此时列出 `git -C <path> status --porcelain` 结果给用户，确认后才可执行 `git worktree remove --force <path>`；发现是未提交代码则一律停止。
   - 再 branch：若 `delete_branch=true`，执行 `git branch -d <source>` 安全删除。
   - 若 `git branch -d` 因未完全合并失败，暂停并说明原因，不执行强制删除。
7. 汇报结果
   - 回报来源/目标、merge 状态、worktree 删除状态、branch 删除状态、剩余需人工处理项。

## 输出模板（给用户）

- 来源分支：`<source>`
- 目标分支：`<target>`
- 合并前来源领先提交数：`<n>`
- 合并：`成功/失败`
- 是否已清理 worktree：`是/否`（否则说明原因）
- 是否已删除来源分支：`是/否`
- 冲突文件：`列表`（如有）
- 备注：`未找到 worktree / 未满足清理条件 / 其余注意事项`

## 硬约束

- **禁止** `git push --force`、`git reset --hard`、`git stash drop` 等破坏性命令。
- **禁止** 在未校验来源 worktree 干净度的情况下执行合并或清理。
- **禁止** 默认使用 `git worktree remove --force`；强制删除必须人工确认。
- **禁止** 在 merge 报 "Already up to date." 时仍继续清理。

完整支线流程：`/wt-start` → `/wt-merge`。
