# NoteMeld 应用运行时与 Wiki 应用化验证

日期：2026-08-27

## 自动化验证

| 命令 | 结果 |
| --- | --- |
| `python3 -m compileall -q backend/app` | 通过 |
| `PYTHONPATH=backend pytest -q backend/tests/test_applications.py` | 通过：8 passed |
| `PYTHONPATH=backend pytest -q backend/tests` | 通过：715 passed, 6 skipped, 13 subtests passed |
| `scripts/run_core_regression.sh` | 通过：33 passed；前端既有 core contract 通过 |
| `cd frontend && node tests/applicationHostContracts.test.mjs` | 通过 |
| `cd frontend && corepack pnpm test:contracts` | 通过 |
| `cd frontend && corepack pnpm build` | 通过；仅有既有第三方 eval/chunk size warning |
| `git diff --check` | 通过 |

## 已覆盖的验收点

- `notemeld.application.v1` manifest 校验：版本、平台、capability/permission、UI/runtime entry、路径穿越、公开 listener 和 package 限制。
- 内建 Wiki registry、启用/禁用、Application Instance、Run、幂等 request、取消、Wiki graph/article capability 和 session-protected API。
- 应用域独立 migration registry 不修改 plugin/candidate registry 或 SQLite `user_version`。
- 默认 application workspace 可在 Settings 配置，实例目录按 app/instance 隔离并拒绝越权路径。
- 前端 Application Host 显示启动、运行、禁用、能力缺失、失败和中断状态；Wiki 迁移保留类型/社群视图、缩放、节点选择、文章详情、刷新、空状态和错误状态。
- 旧 `/wiki` 前端 route、导航和直接 Wiki 页面 wiring 已移除；应用列表和应用容器路由可用。

## 未在本期宣称完成

- 用户应用包上传/安装、公开分发和自动升级。
- 真正的桌面独立应用进程执行、完整 JSONL frame transport 和外部 Web worker 部署；当前实现冻结协议并提供本地 runtime policy/lifecycle seam。
- 移动端应用 UI bundle 与 Agent 自动生成应用。
- `agent.run`、`plugin.invoke`、文件/Artifact 的完整应用 SDK 执行面；本期只冻结 capability 名称和 Host 边界。
