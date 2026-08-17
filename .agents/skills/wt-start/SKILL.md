---
name: wt-start
description: 为指定任务创建 linked worktree，从用户指定的目标基线分支隔离开发。
---

# wt-start：开 worktree 开发

该流程仅使用本地 Git 与 worktree，不依赖 `tabtin`、`scripts/wt.sh` 或其他外部脚本。

## 任务

调用 `/skill:wt-start` 时附带的参数会由 Pi 追加到本 Skill 末尾，作为本次操作的上下文。

若未提供上下文，先确认：任务目标、issue ID（如 `TD-n` / `CC-n` / `H-n`）、目标基线分支（默认本地 `main`）、新分支名。

## 目标分支解析（本地优先）

- 解析用户要求的目标分支（支持 `main`、`release/*` 或其他本地分支名），先本地切到该分支再创建新支线。
- 若未指定，默认 `main`。
- 仅允许使用本地已有分支；不存在时先停下确认是否允许创建本地分支，不自动远端补齐。
- 所有流程以本地为主，不做远端同步、fetch/push、PR 自动化。

## 纯本地流程（推荐）

1. `git checkout <目标分支>`
2. 若开发分支存在：
   - `git worktree add ../notemeld-<开发分支> <开发分支>`
3. 若开发分支不存在：
   - 先确认是否允许创建新本地分支；
   - `git worktree add --detach ../notemeld-<开发分支> -b <开发分支> <目标分支>`
4. 若目标目录已存在：先确认是否允许清理重建；确认后执行 `git worktree remove` / `rm -rf` 清理旧目录再重建。
5. 返回新 worktree 路径，随后在该目录继续任务。

### 可复制安全脚本

```bash
set -euo pipefail

BASE_BRANCH="${BASE_BRANCH:-main}"
TASK_BRANCH="${TASK_BRANCH:?task branch is required}"
WORKTREE_BASE="${WORKTREE_BASE:-../notemeld-${TASK_BRANCH}}"

git checkout "$BASE_BRANCH"
if [ -d "$WORKTREE_BASE" ] && [ "$(ls -A "$WORKTREE_BASE")" ]; then
  echo "worktree exists: $WORKTREE_BASE"
  exit 1
fi

if git show-ref --verify --quiet "refs/heads/$TASK_BRANCH"; then
  git worktree add "$WORKTREE_BASE" "$TASK_BRANCH"
else
  git worktree add --detach "$WORKTREE_BASE" -b "$TASK_BRANCH" "$BASE_BRANCH"
fi
```

## 流程

1. 只做 `git checkout` + `git worktree` 检出，不装依赖，不启动服务，不做构建。
2. 在支线仅改代码；**禁止**在支线执行 `pnpm install`。
3. 需要 lint / typecheck / 前端 test / build 时回 main worktree 执行。
4. `wt-start` 仅负责分支与 worktree 初始化；提交与 PR 流程留给后续步骤。

## 硬约束

- **禁止**装依赖；**禁止**在 linked worktree 起 live stack（dev / Electron / daemon / 探针）
- **禁止** `git stash drop` / `git reset --hard` / force push
- live 等用户切回 main 工作树到 PR 分支后再做

## 快速命令

```bash
git checkout main
git worktree add ../notemeld-fix/<issue-id>-<slug> -b fix/<issue-id>-<slug> main
```

下一步：PR 推上去后，live 回归用 `/wt-verify`，合入清理用 `/wt-merge`。
