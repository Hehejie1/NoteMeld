# NoteMeld Agent SDK cutover acceptance

更新时间：2026-08-18

这份矩阵记录当前仓库可复现的 Task 2–20 证据。`通过` 只表示本机或指定 CI 合约已经验证；移动平台没有本机工具链/设备时不虚报为通过。

| 任务 | 当前结果 | 证据 |
|---|---|---|
| 2–7 | 通过 | Rust workspace tests、Session/Store、context、stream、tool、cancel/steer、approval tests |
| 8 | 本机通过，移动 CI-only | ABI/Python/Swift/native smoke；Android/Harmony 由 `.github/workflows/agent-sdk.yml` fail-closed |
| 9 | 真实通过 | Ollama 三轮上下文记忆、模型切换、shell CLI；第二轮复现“蓝色松树”记忆 |
| 10–13 | 通过重点链路 | 单进程 Host、native executor、Conversation projection、Agent v1 API、SSE 回放+终态、model preference |
| 14 | 通过契约 | 前端 chat service 只走 Agent v1；delta/terminal contract、TypeScript check |
| 15 | 通过 smoke | `scripts/notemeld-agent.py` fake Agent v1 server：session → turn → SSE terminal |
| 16 | 通过单测 | FastAPI Host lifecycle、0600 atomic descriptor、共享 session/CLI discovery |
| 17 | 通过 | `backend/app/agent/`、旧 loop、compat、旧 chat service 和 legacy tests 已删除；生产无旧 Agent import/flag |
| 18 | 本机通过 | dylib、Python wheel、clean wheel native smoke、artifact manifest/license/architecture verifier；Swift iOS harness 在指定 release dylib 目录后可构建 |
| 19 | 部分通过 | backend Agent/Host 相关契约 114 passed（另 4 xfailed）；Rust/clippy/frontend/CLI/native cancel/restart recovery 通过；Tauri 单测 7 passed，窗口退出不再终止共享 Host；真实 packaged 桌面纵向仍待跑 |
| 20 | 待最终发布验收 | UI → CLI → UI 真机续聊、Android/Harmony target、桌面 packaged host 作为发布前门禁 |

## 可复现门禁

```bash
cd agent-sdk
cargo +stable test --workspace --offline
cargo +stable clippy --workspace --all-targets --offline -- -D warnings

cd ..
PYTHONPATH=backend python3 -m pytest backend/tests -m 'not asyncio' -q
cd frontend && pnpm exec tsc --noEmit
```

本机 Android 仅发现 `adb` 且没有 connected device；`gradle`、OpenHarmony `hvigor/ohpm` 不在 PATH。因此 Android connected test 与 Harmony HAR/consumer test 只能由 CI 执行，不能在本机声明通过。
