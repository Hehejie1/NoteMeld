---
name: wt-start
description: 为指定任务创建 linked worktree，在其中完成需求开发与代码 review，最后回报结果。
---

# wt-start：开 worktree 并在其中完成任务

该流程用于本地开发隔离，仅使用 Git 与 worktree；不依赖 `tabtin`、`scripts/wt.sh` 或其他外部脚本。

**本 skill 不是只建目录就结束。** 建 worktree 只是阶段一，之后必须在该 worktree 内完成需求、准备环境、跑验证、做 review、**提交 commit**，最后一次性回报。

## 零追问原则（最重要）

用户只描述需求，**不需要提供分支名**。

- **禁止**向用户询问 `task_branch`、`worktree_path`、`base_branch`。分支名由 Agent 自动生成；基线分支用户给了就用，否则一律本地 `main`。
- **禁止**建完 worktree 就把控制权交回用户等待下一步指令。
- 只有在下列情况才允许停下来问用户：
  - `base_branch` 在本地不存在。
  - 目标 worktree 路径已存在且非空。
  - 需求本身有歧义、存在多种互斥解读，无法安全实现。
  - 当前已身处 linked worktree（见「前置检查」）。

## 前置检查：必须在主工作树发起

`git worktree add` 在 linked worktree 里执行虽然可行，但会造成 worktree 嵌套与路径混乱。

- `git rev-parse --git-dir` 与 `--git-common-dir` 不相等 ⇒ 当前在 linked worktree。
- 此时停止，提示用户先 `cd` 回主工作树（`git worktree list` 第一行）再重新发起。

## 任务上下文

`/skill:wt-start` 的参数全部可选：

- `task_branch`：开发分支名。缺失则自动生成，不追问。
- `base_branch`：基线分支，默认本地 `main`。
- `worktree_path`：默认 `../notemeld-<task_branch>`，保留分支名中的 `/`，形成两层目录（与现存 worktree 布局一致）。
- `reuse_existing`：是否复用已存在的空目录，默认 `true`。

## 分支名自动生成规则

1. 从用户需求描述提取 2-4 个英文关键词（中文需求先意译成英文），小写，用 `-` 连接，总长 ≤ 40 字符。
2. 按需求性质选前缀：新增能力 `feat/`，修 Bug `fix/`，重构/整理 `refactor/`，文档 `docs/`，杂项 `chore/`。
3. 示例：
   - "所有中间数据放 vector_db，日志放 logs" → `refactor/unify-storage-paths` → `../notemeld-refactor/unify-storage-paths`
   - "修复上传大文件超时" → `fix/upload-large-file-timeout`
4. 冲突检测（必须执行）：用 `git branch --list`、`git worktree list` 检查分支名与目标路径是否被占用；冲突则追加 `-2`、`-3`… 直到两者都空闲。
5. 生成结果直接使用，不需要用户确认。

## 目标分支解析（本地优先）

- 基线分支默认 `main`，支持 `main`、`release/*` 或其他本地存在的分支名。
- 只走本地：不执行 `fetch/pull/push`，不处理远端分支。
- 不自动创建基线分支；基线分支不存在时停止并提示。

## 阶段一：创建 worktree

1. 收集上下文（可并行执行）
   - `git rev-parse --show-toplevel --git-dir --git-common-dir`（同时完成前置检查）
   - `git branch --list`
   - `git worktree list`
2. 确定 `base_branch`（用户给定 > 本地 `main`）；本地不存在则停止并提示。
3. 按上文规则生成 `task_branch` 与 `worktree_path`，完成冲突检测。
4. **不切换当前分支。** `git worktree add` 已显式指定 base，主工作树保持原状即可（也因此不要求主工作树干净）。
5. 创建 worktree，按 `task_branch` 是否已存在选命令：
   - 分支不存在：`git worktree add <worktree_path> -b <task_branch> <base_branch>`
   - 分支已存在（用户显式指定的情况）：`git worktree add <worktree_path> <task_branch>`，**不带 `-b`**（带了会 `fatal: a branch named ... already exists`）
   - 目标路径已存在且为空：按 `reuse_existing` 复用。
   - 目标路径非空：返回占用信息并停止（默认不自动清空）。
6. 简要告知已创建的路径与分支，然后**立即继续阶段二，不等待用户确认**。

## 阶段二：环境 bootstrap（不可跳过）

新 worktree 只含被 Git 跟踪的文件。`.venv`、`node_modules`、`.env` 都在 `.gitignore` 内，**新 worktree 里不存在**，不做 bootstrap 任何验证命令都会失败。

从主工作树 `<main_root>`（`git worktree list` 第一行路径）链接过来，按本次改动范围**按需**执行：

```bash
# 改后端时需要
ln -s <main_root>/.venv <worktree_path>/.venv
cp <main_root>/.env <worktree_path>/.env

# 改前端时需要
ln -s <main_root>/frontend/node_modules <worktree_path>/frontend/node_modules
```

- 用符号链接而非 `pnpm install` / 重建 venv，省时且避免磁盘浪费。
- `.env` 必须 `cp` 不能 `ln`，避免在 worktree 内改配置污染主工作树。
- `desktop/` 等其他目录如有依赖同理按需链接。
- 只改文档或纯配置时可跳过本阶段，但要在回报里说明「未 bootstrap，未跑代码验证」。
- 链接目标不存在时（主工作树自己也没装），提示用户先在主工作树装好，不要在 worktree 里从零安装。

## 阶段三：在 worktree 中完成需求

工作目录固定为 `<worktree_path>`（所有 RunCommand 传 `cwd=<worktree_path>`），**禁止**在主工作树路径下改任何文件。

1. 先读 worktree 内的 `AGENTS.md`、`CLAUDE.md` 与 `docs/system/` 相关文档，再搜索现状代码与测试。
2. 用 TodoWrite 拆解步骤，按最小改动原则实现需求。
3. 需求涉及架构、数据模型、API、产品规则变化时，同步更新 `docs/system/`。
4. 按改动范围选择验证命令（在 worktree 内执行）：
   - `python3 -m compileall backend/app`
   - `pytest backend/tests`
   - `cd frontend && pnpm test:contracts`
   - `cd frontend && pnpm build`
   - `scripts/run_core_regression.sh`
5. **禁止**启动 dev server 或 Electron 进程。

## 阶段四：代码 review

1. 拿到完整改动面（含新增文件）：

   ```bash
   git add -N .
   git status --porcelain
   git diff
   ```

   直接 `git diff` 会漏掉新增文件；`git diff <base>...HEAD` 在未 commit 时输出为空。用 `git add -N .`（intent-to-add）只登记新文件路径、不暂存内容，既能让 diff 完整，又不影响阶段五精确 `git add`。`.gitignore` 已覆盖 `.env` / `.venv` / `node_modules`，不会被登记进来。
2. 调用 `TRAE-code-review` skill 审查该 diff；无法调用时按以下清单人工自查：
   - 是否有超出需求范围的无关改动、无关重构、被误删能力。
   - 是否残留调试代码、临时日志、注释掉的旧逻辑、未使用导入。
   - 是否破坏源码启动、CLI、桌面、MCP、迁移、Wiki、上传、打包发布任一入口。
   - 是否引入 `docs/system/known-pitfalls.md` 中已记录的问题。
   - 是否泄露 API Key、Cookie、token、本地绝对路径等敏感信息。
   - 是否误把 bootstrap 产物（`.venv` 软链、`node_modules` 软链、`.env`）加进暂存区 —— 若有必须 `git restore --staged` 移除。
   - 边界与并发：取消、超时、文件写入的 race condition 与脏状态。
3. review 发现的问题当场修掉并重跑相关验证；只有确认无阻塞问题才进入阶段五。

## 阶段五：提交 commit（不可跳过）

**必须 commit。** `/wt-merge` 合并的是 commit，未提交的改动不会被合并，而合并"成功"后 worktree 会被清理 —— 不 commit 等于工作成果必然丢失。

```bash
git add <明确列出改动文件>   # 不要用 git add -A，避免带入 .env / 软链
git commit -m "<type>: <一句话说明 why>"
```

- 逐个列出文件名，不使用 `git add -A` / `git add .`。
- 确认 `.env`、`.venv`、`node_modules` 未进入提交（`git show --stat HEAD` 复核）。
- 提交后 `git status --porcelain` 必须只剩未跟踪的 bootstrap 产物，不得有已跟踪文件的未提交改动。

## 阶段六：回报

只在阶段四通过、阶段五提交完成后向用户输出一次总结：

- base_branch: `<base_branch>`
- task_branch: `<task_branch>`（自动生成 / 用户指定）
- worktree_path: `<path>`
- bootstrap: 链接了哪些依赖 / 未 bootstrap 及原因
- 需求实现摘要：改了哪些文件、关键逻辑变化
- 验证证据：实际执行的命令与结果（不得编造）
- review 结论：发现的问题与处理方式，遗留风险
- commit: `<sha> <message>`
- 下一步：**先 `cd <main_root>` 回到主工作树**，再执行 `/wt-merge source=<task_branch> target=<base_branch>`

## 注意

- 阶段二至五的所有命令都必须在 `<worktree_path>` 下执行，避免污染主工作树。
- 不启动 dev server / Electron 进程。
- 遇到路径、分支或未跟踪文件冲突时中止，不自动修复，避免误删。
- 没有实际执行验证命令，不得声称"已验证通过"。

## 硬约束

- **禁止** `git stash drop` / `git reset --hard` / force push。
- **禁止** 自动 `rm -rf` 已存在非空目录。必要清理必须人工确认并执行。
- **禁止** 因为缺少分支名而中断流程去追问用户。
- **禁止** 只创建完 worktree 就结束本次任务。
- **禁止** 跳过 bootstrap 却声称跑过测试。
- **禁止** 未做 review 就回报完成。
- **禁止** 不 commit 就结束（会导致 `/wt-merge` 丢失全部工作）。
