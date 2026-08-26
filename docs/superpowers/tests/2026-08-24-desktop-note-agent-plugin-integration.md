# NoteMeld 桌面 Note Agent 与插件集成验收证据

Canonical requirement：`../../requirements/2026-08-24-desktop-note-agent-plugin-integration.md`
状态：I03 integrated; release-gate follow-ups remain

## 前置门禁

- SDK requirement 状态：Implemented（见 `docs/system/n01-evidence.md`）
- SDK version/schema/ABI/commit：`0.1.0 / 1 / 1 / f926bd7674c98b27895734c0df18e0c0241cb132`
- SDK artifact SHA-256：见 `docs/system/n01-evidence.md`
- SDK strict conformance：desktop verified；Android/iOS/Harmony 按 N01 记录的授权边界

结论：N01 已完成；N02/N03/N04 可基于固定产品 commit `895ab32c465ee630c69196179ea16281abe0d9a7` 并行。

## Goal 证据

| Goal | 命令/证据 | 结果 | 失败或阻塞 |
| --- | --- | --- | --- |
| N01 Artifact/baseline | `docs/system/n01-evidence.md`：loader contract、URL inventory、Note authority ADR | Implemented | 平台 waiver/skip 边界见 N01 evidence |
| N02 Note adapter | focused DB/adapter/idempotency/migration tests；Agent Host tests；`python3 -m compileall backend/app` | Implemented | I03 已接入同一 DB bootstrap |
| N03 Plugin control plane | [`system/n03-evidence.md`](../../system/n03-evidence.md)：Release fixture、supply-chain、权限/崩溃、rollback、UI contracts | Implemented | N01 pinned handoff；链接插件迁移由 N04 收口 |
| N04 Link plugin | focused N04 tests；N01→N04 before/after matrix；临时 SQLite bootstrap + installed pointer/load 验证 | Passed: 48 core link tests；7 N01 platforms + web_link covered，before/after rows identical；官方 fixture 安装到统一 `plugins/versions` 后由 active pointer 加载 | Real network/platform media remains outside this gate |
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

结果：focused tests、contracts/build、compile、Agent Host 与 `scripts/run_core_regression.sh` 均通过；DMG contract 仍引用已删除的 `.trae` skill 文件。

## 最终纵向证据

- GitHub Release fixture install/hash/rollback：Pending
- Gitee Release fixture install/hash/rollback：Pending
- 全 URL baseline：Pending
- Desktop sidecar/UI：Pending
- External MCP Client：Pending
- CLI relation continuation：Pending
- Candidate SDK boundary denial：Pending
- Same SQLite migration isolation：Pending

最终结论：I03 集成提交完成；DMG 发布 contract 作为后续发布收口风险。
