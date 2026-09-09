# Research Note Whiteboard Verification Evidence

Date: 2026-08-13

## Automated verification

- `PYTHONPATH=backend python3 -m pytest -q backend/tests`: **509 passed, 4 subtests passed** in 19.51s after review fixes.
- Review-focused source-boundary, clarification, projection and reference tests: **34 passed** in the independent final review.
- `python3 -m compileall -q backend/app`: exit 0.
- `cd frontend && pnpm test:contracts`: exit 0.
- `node frontend/tests/learningCanvasContracts.test.mjs`: exit 0.
- `cd frontend && pnpm build`: exit 0; Vite transformed 13,078 modules and built in 1m05s.
- `scripts/run_core_regression.sh`: **27 passed** in 2.24s.
- `git diff --check -- <feature files>`: exit 0.

The production build reports the repository's existing Lottie `eval` warning and large-chunk warnings; neither fails the build.

## Local smoke verification

- Backend is listening on `127.0.0.1:8483`; OpenAPI exposes the learning-canvas endpoints.
- Frontend is listening on `127.0.0.1:3015`.
- `/new` renders Chat / Note / Learn modes.
- An existing version-1 canvas opens through the research-whiteboard compatibility projection.
- Clicking a whiteboard node's `添加到对话` action creates a removable reference chip in the composer; the chip was removed after verification, so no user message or research task was created.
- Source services were restarted after verification; the current processes serve the reviewed backend/frontend code on ports 8483/3015.

Browser logs contain expected source-Web warnings for the unavailable Tauri bridge and warnings from historical failed note tasks. No new external research request was submitted during smoke verification.

## Residual manual verification

The following require the user's configured live provider and network sources, and are intentionally left for interactive acceptance:

1. Submit an ambiguous goal such as `韩信` and confirm one clarification question appears and no Note is created before an answer.
2. Submit a clear research goal and inspect live academic/GitHub/Web relevance, generated Note quality and Wiki ingestion.
3. Select text in a generated Note, right-click `添加到对话`, send a follow-up, and judge the model's use of that context.
4. Exercise Note / Whiteboard switching, zoom, node selection, suggested navigation and refresh recovery at the user's normal viewport.
# 2026-08-14 整块白板增量验证

Canonical requirement: `docs/requirements/2026-08-13-notemeld-research-note-whiteboard.md`

- `PATH=/Users/hehejie/.nvm/versions/node/v22.22.1/bin:$PATH node frontend/tests/learningCanvasContracts.test.mjs`：通过。新增断言覆盖整块白板、单浮层、零关系提示、display 坐标聚焦、Camera reset 和 ResizeObserver。
- `cd frontend && PATH=/Users/hehejie/.nvm/versions/node/v22.22.1/bin:$PATH pnpm test:contracts`：通过。
- `cd frontend && PATH=/Users/hehejie/.nvm/versions/node/v22.22.1/bin:$PATH pnpm build`：通过，`13090 modules transformed`，`built in 34.61s`。保留既有 lottie `eval` 与大 chunk 警告。
- 真实数据检查：`总结一下agent的设计哲学` Canvas 含 8 节点、0 关系；验证零关系分支不会把它当空数据，并使用紧凑环形布局。
