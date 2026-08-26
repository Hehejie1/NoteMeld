# NoteMeld 桌面 Note Agent 与插件集成验收证据

Canonical requirement：`../../requirements/2026-08-24-desktop-note-agent-plugin-integration.md`
状态：Wave A in progress

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
| N02 Note adapter | focused：`PYTHONPATH=backend .venv/bin/pytest -q backend/tests/agent_host/test_note_contract.py backend/tests/agent_host/test_note_store_adapter.py`；回归：`PYTHONPATH=backend .venv/bin/pytest -q backend/tests/agent_host`、`... pytest -q backend/tests/test_model_runtime_schema.py`；`python3 -m compileall backend/app` | focused 12 passed；Agent Host 113 passed/5 skipped；model migration 5 passed；真实临时 SQLite 覆盖历史 task_id、same/different payload、operation transitions、原子回滚、并发版本、reopen needs-attention、投影失败、关系/authority 和多 registry 共存；compileall 通过 | I03 需统一接入 DB bootstrap 与 SDK/transport composition；2 条既有 downloader regex warning |
| N03 Plugin control plane | [`system/n03-evidence.md`](../../system/n03-evidence.md)：Release fixture、supply-chain、权限/崩溃、rollback、UI contracts | Implemented | N01 pinned handoff；链接插件迁移留 N04 |
| N04 Link plugin | `./.venv/bin/python -m pytest -q backend/tests/plugins/test_official_link_note.py backend/tests/test_n04_link_capability_matrix.py backend/tests/test_n01_url_capability_baseline.py backend/tests/test_douyin_downloader_contracts.py backend/tests/test_multisource_summary_contracts.py backend/tests/test_multisource_video_collector_contracts.py backend/tests/test_web_note_contracts.py backend/tests/test_core_note_task_status_api.py`；`plugins/official-link-note/release-fixture/official-link-note-1.0.0.zip`；N01→N04 before/after matrix | Passed: 48 tests；7 N01 platforms + web_link covered，before/after rows identical；manifest/index/digest and local Release fixture present；应用 validator 复用插件 URL contract | Real network/platform media and N03 installer integration remain for I03/N07 |
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
