# NoteMeld 桌面 Note Agent 与插件集成验收证据

Canonical requirement：`../../requirements/2026-08-24-desktop-note-agent-plugin-integration.md`
状态：Pending SDK Release Gate

## 前置门禁

- SDK requirement 状态：Pending
- SDK version/schema/ABI/commit：Pending
- SDK artifact SHA-256：Pending
- SDK strict conformance：Pending

结论：N01 代码实现当前未解锁。

## Goal 证据

| Goal | 命令/证据 | 结果 | 失败或阻塞 |
| --- | --- | --- | --- |
| N01 Artifact/baseline | loader contract、URL inventory、Note authority ADR | Pending | SDK S08 |
| N02 Note adapter | focused DB/adapter/idempotency/migration tests | Pending | Pending |
| N03 Plugin control plane | Release fixture、supply-chain、rollback、UI contracts | Pending | Pending |
| N04 Link plugin | before/after URL baseline matrix、package fixture | Pending | Pending |
| N05 Desktop/MCP/CLI | real desktop→plugin→Note→MCP→CLI vertical | Pending | Pending |
| N06 Candidate boundary | SDK deny、evidence/test/rollback、no-auto-activation | Pending | Pending |
| N07 Release gate | full regression/build/package/manual evidence | Pending | Pending |

## 最终自动化

```bash
python3 -m compileall backend/app
pytest backend/tests
(cd frontend && corepack pnpm test:contracts)
(cd frontend && corepack pnpm build)
scripts/run_core_regression.sh
```

结果：Pending。

## 最终纵向证据

- GitHub Release fixture install/hash/rollback：Pending
- Gitee Release fixture install/hash/rollback：Pending
- 全 URL baseline：Pending
- Desktop sidecar/UI：Pending
- External MCP Client：Pending
- CLI relation continuation：Pending
- Candidate SDK boundary denial：Pending
- Same SQLite migration isolation：Pending

最终结论：Pending。
