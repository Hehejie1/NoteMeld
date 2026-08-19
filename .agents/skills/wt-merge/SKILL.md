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
- 若冲突，**先分析再决策**：禁止一遇冲突就停止并把原始冲突丢给用户。必须按第 5 步流程判定是否可自动解决。
- 冲突未完全解决前，不执行任何清理。
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
5. 冲突处理（必须先理解意图，禁止直接把冲突甩给用户）
   - **5.1 收集事实**
     - `git status --porcelain` 取冲突文件列表（`UU`/`AA`/`DU`/`UD` 等）。
     - 对每个冲突文件：`git diff --diff-filter=U <file>` 看冲突块；`git log --oneline <merge_base>..<source> -- <file>` 与 `git log --oneline <merge_base>..<target> -- <file>` 看两边各自改了什么（`merge_base` 由 `git merge-base <target> <source>` 得到）。
   - **5.2 判定两边意图**
     - 逐个冲突块回答：source 想达成什么？target 想达成什么？两者是**互补**（改不同关注点，可共存）还是**互斥**（对同一语义给出不同答案）。
     - 结合仓库文档与产品规则判断哪边符合当前系统现状，不靠猜。
   - **5.3 可自动解决的类型 —— 直接解决**
     - 互补型：两边新增不同的函数/用例/字段/导入/列表项 ⇒ 合并两边内容，保留双方意图。
     - 纯格式、导入顺序、空行、注释位置差异 ⇒ 按目标分支风格归一。
     - 一边只是把另一边的改动做了重命名或搬移 ⇒ 以语义更新的一侧为准并同步引用。
     - 一边明显是另一边的超集（同一意图的更完整实现）⇒ 取超集。
     - 解决后：`git add <file>`，全部冲突清空再 `git commit --no-edit`，然后跑与冲突文件相关的测试（如冲突在 `backend/tests/**` 或 `backend/app/**`，运行对应 `pytest <path>`）验证结果，通过后按第 6 步清理，并在汇报中逐文件说明解决方式。
   - **5.4 不可自动解决的类型 —— 给出方案让用户选**
     - 互斥的业务语义、数据模型字段语义、API 契约、并发/取消策略等；或两边意图无法从代码与文档中确定。
     - 此时**不留下半成品状态**：保持 merge 冲突态但必须给出结构化选项，每项含"改动内容 + 影响范围 + 风险"，并给出推荐项及理由：
       - 方案 A：采用 source 版本（`git checkout --theirs <file>`）
       - 方案 B：采用 target 版本（`git checkout --ours <file>`）
       - 方案 C：手工融合（给出具体融合后的代码建议）
       - 方案 D：放弃本次合并（`git merge --abort`，回到干净 target）
     - 用户确认后再执行对应方案，不执行任何清理。
   - **5.5 硬性要求**
     - 禁止仅输出"冲突：<文件名>，已停止"这类无分析结论。任何冲突汇报必须包含：冲突文件、两边意图、是否已解决、解决方式或候选方案。
     - 禁止用 `--ours`/`--theirs` 整文件覆盖来"快速消除冲突"，除非该结论来自 5.2 的意图分析或用户明确选择。
     - 混合情况（部分文件可自动解决、部分不可）：先解决可解决的并 `git add`，其余按 5.4 提方案，不提交、不清理。
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
- 合并：`成功/自动解决冲突后成功/待用户决策`
- 是否已清理 worktree：`是/否`（否则说明原因）
- 是否已删除来源分支：`是/否`
- 冲突处理（如有冲突则必填，逐文件列出）：
  - 文件：`<path>`
  - source 意图：`<一句话>`
  - target 意图：`<一句话>`
  - 关系：`互补/互斥/无法判定`
  - 处理：`已自动解决（说明如何解决）` 或 `需用户决策（列出方案 A/B/C/D + 推荐项及理由）`
- 验证：`已运行的测试命令与结果`（自动解决冲突时必填）
- 备注：`未找到 worktree / 未满足清理条件 / 其余注意事项`

## 硬约束

- **禁止** `git push --force`、`git reset --hard`、`git stash drop` 等破坏性命令。
- **禁止** 在未校验来源 worktree 干净度的情况下执行合并或清理。
- **禁止** 默认使用 `git worktree remove --force`；强制删除必须人工确认。
- **禁止** 在 merge 报 "Already up to date." 时仍继续清理。
- **禁止** 遇到冲突就停止并只报冲突文件名；必须先完成第 5 步的意图分析，能解决的直接解决，不能解决的给出带推荐的可选方案。
- **禁止** 在冲突未全部解决的情况下 `git commit` 或执行任何清理。
- **禁止** 未经用户确认执行 `git merge --abort`（会丢弃已完成的冲突解决工作）。

完整支线流程：`/wt-start` → `/wt-merge`。
