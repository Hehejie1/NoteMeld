---
name: wt-start
description: 为指定任务创建 linked worktree，从本地基线分支隔离开发。
---

# wt-start：开 worktree 开发

该流程用于本地开发隔离，仅使用 Git 与 worktree；不依赖 `tabtin`、`scripts/wt.sh` 或其他外部脚本。

## 零追问原则（最重要）

用户只描述需求，**不需要提供分支名**。

- **禁止**向用户询问 `task_branch`、`worktree_path`。分支名必须由 Agent 从需求描述自动生成。
- **禁止**向用户询问 `base_branch`。用户显式给出就用，否则一律用本地 `main`。
- 只有在下列情况才允许停下来问用户：
  - 仓库不干净且必须切分支才能继续（有未提交改动会被切分支影响）。
  - `base_branch` 在本地不存在。
  - 目标 worktree 路径已存在且非空。

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

## 流程

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
6. 回报结果并告知下一步：去该 worktree 开发；完成后调用 `/wt-merge source=<task_branch> target=<base_branch>`。

## 快速命令

```bash
git switch main
git worktree add ../notemeld-refactor-unify-storage-paths -b refactor/unify-storage-paths main
```

## 输出模板

- base_branch: `<base_branch>`
- task_branch: `<task_branch>`（自动生成 / 用户指定）
- worktree_path: `<path>`
- reused_path: `true/false`
- 下一步:
  - `cd <worktree_path>` 开发
  - `开发完成后执行 /wt-merge source=<task_branch> target=<base_branch>`

## 注意

- 不在新 worktree 执行 `pnpm install` 或启动 dev server / Electron 进程。
- 遇到路径、分支或未跟踪文件冲突时中止，不自动修复，避免误删。
- 若需回到主工作流，先在新工作树完成切换回基线上下文再调用 `/wt-merge`。

## 硬约束

- **禁止** `git stash drop` / `git reset --hard` / force push。
- **禁止** 自动 `rm -rf` 已存在非空目录。必要清理必须人工确认并执行。
- **禁止** 因为缺少分支名而中断流程去追问用户。
