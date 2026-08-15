---
name: wt-start
description: 为指定任务创建 linked worktree，从用户指定的目标基线分支隔离开发。
---

# wt-start：开 worktree 开发

**先读 skill `$tabtin-dev-worktree`**——本命令仅作快捷入口；worktree 须用户主动触发，默认开发走本地 `main`。

## 任务

调用 `/skill:wt-start` 时附带的参数会由 Pi 追加到本 Skill 末尾，作为本次操作的上下文。

若上面为空，先向用户确认：要做什么、对应哪个稳定 issue ID（如 `TD-n` / `CC-n` / `H-n`）、目标基线分支（默认本地 `main`）、期望分支名。

## 目标分支解析（本地优先）

- 解析用户要求的目标分支（支持 `main`、`release/*` 或其他本地分支名），先本地切到该分支后再创建新支线。
- 若未指定，默认 `main`。
- 仅允许使用本地已有分支；不存在时先停下确认是否允许用户创建本地分支，不自动从远端补齐。
- 所有流程都以本地为主，不做远端分支同步、fetch/push、PR 相关逻辑。

## 宿主路由（先判断，再创建）

- System prompt 含 `<worktree_routing>` 时：先确保当前在目标分支（`git checkout <目标分支>`），再执行 `tabtin code worktree create --new-branch <开发分支> --base <目标分支>`；用户未指定路径时不传 `--path`。命令完成后由宿主绑定新根并在同一对话续跑，不要改用 `scripts/wt.sh` / `git worktree`，不要手动切 cwd。
- 没有 `<worktree_routing>` 时：当前宿主无原生路由，才使用下文 `scripts/wt.sh` 流程；fallback 里也先切到用户要求的目标分支。

## 流程

1. 按上述宿主路由创建 linked worktree（**只检出代码，永不装依赖**）。脚本 fallback 中之后编辑的 `working_directory` 指向 `bash scripts/wt.sh path <开发分支>`；TabTin 原生路由中等待宿主自动续跑。
2. 在支线**只改代码**；**禁止**在支线 `pnpm install`。需要 lint / typecheck / 前端 test / build 时回 main worktree。
3. `wt-start` 仅负责分支和 worktree 初始化；PR 创建与提交由后续流程处理。

## 硬约束

见 `$tabtin-dev-worktree`：**禁止**装依赖；**禁止**在 linked worktree 起 live stack（dev / Electron / daemon / 探针）；**禁止** `git stash drop` / `git reset --hard` / force push；live 等用户切 main worktree 到 PR 分支后再做。

## 快速开工

```bash
# TabTin 对话内（存在 <worktree_routing>）
tabtin code worktree create --new-branch fix/<issue-id>-<slug> --base main

# 外部宿主 fallback
bash scripts/wt.sh create fix/<issue-id>-<slug> --base main  # 只检出，永不装依赖
```

下一步：PR 推上去后，live 回归用 `/wt-verify`，合入清理用 `/wt-merge`。
