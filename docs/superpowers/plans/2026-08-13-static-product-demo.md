# High-Fidelity Static Product Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a backend-free NoteMeld demo that reuses the production React UI, offers deterministic product states and simulated actions, adds requirement/code-backed feature guidance, and starts through one shell script.

**Architecture:** A compile-time `VITE_NOTEMELD_DEMO=true` flag selects a fail-closed in-browser transport and a fixed-ready backend context while preserving the production route/component tree. Typed synthetic fixtures and one scheduler-backed scenario runtime satisfy existing service/store contracts; a guide provider and non-visual targets add the explanation drawer without cloning pages.

**Tech Stack:** React 19, TypeScript 5.7, Vite 6, Zustand, Axios, React Router, existing Radix/shadcn components, Node contract tests, shell smoke tests.

## Global Constraints

- Production mode remains the default and must retain runtime/backend readiness checks and real service behavior.
- Demo mode must never fall back to `/api`, `/static`, MCP, LLM providers, or Tauri commands for business actions.
- Demo fixtures must contain synthetic content only: no user conversation text, secrets, cookies, tokens, authorization headers, or absolute local paths.
- Reuse existing routes, pages, components, design tokens, and status meanings; do not create parallel page copies or screenshot hot maps.
- Cover empty, pending, running, success, failed, canceled, and Wiki partial states.
- Default clicks keep product behavior; guide mode clicks open explanations; right-click always opens the same explanation where a target exists.
- `docs/product/*.png` are visual baselines, not runtime assets.
- Do not change backend APIs, SQLite schema, business file layout, MCP tools, Tauri native code, or release packaging.
- Preserve unrelated staged and unstaged work already present in the shared worktree.

---

## Planned File Structure

- `frontend/src/demo/mode.ts`: compile-time demo detection; no UI or data concerns.
- `frontend/src/demo/types.ts`: demo request, response, scenario, action, and scheduler contracts.
- `frontend/src/demo/fixtures.ts`: typed synthetic fixture graph and state catalog.
- `frontend/src/demo/runtime.ts`: in-memory request router, mutations, reset, and fail-closed errors.
- `frontend/src/demo/scenarios.ts`: timer-driven task/chat/update simulations with disposal.
- `frontend/src/demo/transport.ts`: Axios-shaped and stream/action adapters used by existing boundaries.
- `frontend/src/demo/featureGuideCatalog.ts`: requirement/code-backed guide records.
- `frontend/src/demo/FeatureGuideContext.tsx`: guide mode, selected feature, deferred original action.
- `frontend/src/demo/FeatureGuideTarget.tsx`: transparent click/context-menu event policy.
- `frontend/src/demo/FeatureGuideDrawer.tsx`: accessible right-side explanation UI.
- `frontend/src/demo/DemoControlBar.tsx`: restrained scenario/guide/reset controls visible only in demo mode.
- `frontend/tests/staticDemoContracts.test.mjs`: source-level mode/transport/fixture/guide contracts matching the repository test style.
- `frontend/tests/staticDemoRuntime.test.mjs`: runtime behavior tests executed against compiled test output where feasible.
- `scripts/preview_static_demo.sh`: build-and-preview entry point.

### Task 1: Demo Mode and Backend Isolation

**Files:**
- Create: `frontend/src/demo/mode.ts`
- Modify: `frontend/src/contexts/BackendInitContext.tsx`
- Modify: `frontend/src/main.tsx`
- Test: `frontend/tests/staticDemoContracts.test.mjs`

**Interfaces:**
- Produces: `isDemoMode(): boolean` and a demo-ready `BackendInitContextValue` with `runtimeStatus/backendStatus/status='ready'`, `runtimeReady/backendReady/initialized=true`, `blocking/loading=false`, `phase='ready'`, `failureKind=null`, and no-op `checkNow()`.
- Consumes: existing `BackendInitContextValue` and production hooks without changing their production invocation order.

- [ ] **Step 1: Write failing source-contract tests**

Add assertions that `mode.ts` reads only `import.meta.env.VITE_NOTEMELD_DEMO === 'true'`, the provider has a demo-ready branch, `useCheckBackend` remains in the production branch, and `main.tsx` skips `registerDesktopRuntimeOnPageLoad()` in demo mode.

- [ ] **Step 2: Run the test and verify RED**

Run: `cd frontend && node --test tests/staticDemoContracts.test.mjs`
Expected: FAIL because the demo mode module and branches do not exist.

- [ ] **Step 3: Implement the minimal mode and provider branch**

Implement `isDemoMode()`, a stable demo context value, and guard desktop registration. Do not modify `useCheckBackend.ts` or its retry constants.

- [ ] **Step 4: Run the test and existing readiness contracts**

Run: `cd frontend && node --test tests/staticDemoContracts.test.mjs tests/backendReadyGatesWorkspaceRequests.test.mjs tests/useCheckBackendNonBlockingContracts.test.mjs tests/backendInitStartupWindowContracts.test.mjs`
Expected: all tests PASS.

- [ ] **Step 5: Commit only Task 1 files**

Commit message: `feat: isolate static demo runtime`

### Task 2: Typed Fixtures and Fail-Closed Demo Runtime

**Files:**
- Create: `frontend/src/demo/types.ts`
- Create: `frontend/src/demo/fixtures.ts`
- Create: `frontend/src/demo/runtime.ts`
- Test: `frontend/tests/staticDemoContracts.test.mjs`
- Test: `frontend/tests/staticDemoRuntime.test.mjs`
- Modify: `frontend/tsconfig.contract.json` if test compilation needs the new pure TypeScript modules.

**Interfaces:**
- Produces: `demoRuntime.request<T>({ method, path, body, query }): Promise<T>`, `demoRuntime.reset(): void`, `demoRuntime.subscribe(listener): () => void`, `demoRuntime.getSnapshot(): DemoSnapshot`.
- Produces fixture ids `demo-chat`, `demo-note-success`, `demo-note-running`, `demo-note-failed`, `demo-note-canceled` and typed domain fixtures for conversations, documents, Wiki, styles, model/settings, usage, deployment, MCP, and research search.
- Unknown paths throw `DemoEndpointNotImplementedError` containing method/path and never invoke network APIs.

- [ ] **Step 1: Write failing runtime and safety tests**

Test stable fixture ids, required state coverage, reset after mutation, unknown endpoint rejection, and scans for `api_key`, `cookie`, `token`, `authorization`, `/Users/`, `/home/`, and Windows drive paths in serialized fixtures.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test tests/staticDemoContracts.test.mjs tests/staticDemoRuntime.test.mjs`
Expected: FAIL because fixture/runtime exports are missing.

- [ ] **Step 3: Implement minimal typed fixtures and request router**

Register the exact endpoints currently consumed by initial app load and screenshot-baseline pages: conversations/detail, task status, Wiki graph, note styles, providers/models, transcriber config/status, downloader Cookie status, deploy status, updater result, usage, MCP servers, research-search config, and supported mutations.

- [ ] **Step 4: Run tests and type contracts**

Run: `cd frontend && node --test tests/staticDemoContracts.test.mjs tests/staticDemoRuntime.test.mjs && pnpm test:contracts`
Expected: all commands PASS.

- [ ] **Step 5: Commit only Task 2 files**

Commit message: `feat: add static demo fixtures`

### Task 3: Route Existing Services Through Demo Transport

**Files:**
- Create: `frontend/src/demo/transport.ts`
- Modify: `frontend/src/utils/request.ts`
- Modify: `frontend/src/services/chat.ts`
- Modify: `frontend/src/services/desktopRuntime.ts`
- Modify: `frontend/src/services/desktopUpdater.ts`
- Modify: `frontend/src/utils/fileDialog.ts`
- Modify: `frontend/src/pages/HomePage/components/VideoBanner.tsx`
- Modify: `frontend/src/pages/HomePage/components/MarkdownViewer.tsx`
- Modify: any additional direct `fetch`, `/static`, image proxy, or Tauri call site found by the required scan.
- Test: `frontend/tests/staticDemoContracts.test.mjs`

**Interfaces:**
- Consumes: `demoRuntime.request<T>()`.
- Produces: `demoRequest<T>(method, path, body?, query?)`, `demoStreamFreeChat(payload, handlers)`, and demo desktop/file/update actions.
- Production mode continues through existing Axios/fetch/Tauri implementations unchanged.

- [ ] **Step 1: Write failing boundary tests**

Assert request interceptor delegates before Axios dispatch in demo mode, stream chat delegates before fetch, desktop/file/update functions delegate before dynamic imports, and demo resource helpers never construct backend URLs.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test tests/staticDemoContracts.test.mjs`
Expected: FAIL at each unimplemented boundary.

- [ ] **Step 3: Implement the adapters and enumerate direct side effects**

Use `rg -n "fetch\\(|request\\.|@tauri-apps|/api|/static|image_proxy" frontend/src` and route every user-reachable demo call through the adapter. Unknown demo operations must reject with a fixed safe message.

- [ ] **Step 4: Run contract, runtime, and existing network tests**

Run: `cd frontend && node --test tests/staticDemoContracts.test.mjs tests/staticDemoRuntime.test.mjs tests/chatStreamApiBaseUrl.test.mjs tests/runtimeContracts.test.mjs && pnpm test:contracts`
Expected: all commands PASS; production URL assertions remain intact.

- [ ] **Step 5: Commit only Task 3 files**

Commit message: `feat: route demo actions in browser`

### Task 4: Deterministic Scenario Engine and Demo Controls

**Files:**
- Create: `frontend/src/demo/scenarios.ts`
- Create: `frontend/src/demo/DemoControlBar.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/store/taskStore/index.ts` only if an explicit demo reset/hydration seam is required.
- Test: `frontend/tests/staticDemoRuntime.test.mjs`
- Test: `frontend/tests/staticDemoContracts.test.mjs`

**Interfaces:**
- Produces: `startDemoNoteScenario(outcome: 'success'|'failed'|'canceled', options?): DemoScenarioHandle`, whose handle exposes `cancel(): void` and `dispose(): void`.
- Produces: `setDemoScenario(id: DemoScenarioId)`, `resetDemoScenario()`, and a subscriber notification that causes existing stores/pages to reload fixtures.
- Consumes: existing `TaskStatus` order and runtime mutation methods.

- [ ] **Step 1: Write failing state-machine tests**

Using an injected scheduler, assert success status order, failed terminal state, cancellation, reset, and that `dispose()` prevents later state writes.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test tests/staticDemoRuntime.test.mjs`
Expected: FAIL because scenario functions do not exist.

- [ ] **Step 3: Implement scheduler-backed scenarios and control bar**

Keep timers centralized and injectable. Render the control bar only when `isDemoMode()` is true; provide scenario selection, simulate success/failure/cancel, and reset without changing production layout.

- [ ] **Step 4: Run runtime/contracts/type tests**

Run: `cd frontend && node --test tests/staticDemoRuntime.test.mjs tests/staticDemoContracts.test.mjs && pnpm test:contracts`
Expected: PASS, with no dangling timer warnings.

- [ ] **Step 5: Commit only Task 4 files**

Commit message: `feat: simulate demo product states`

### Task 5: Feature Guide Catalog, Interaction Policy, and Drawer

**Files:**
- Create: `frontend/src/demo/featureGuideCatalog.ts`
- Create: `frontend/src/demo/FeatureGuideContext.tsx`
- Create: `frontend/src/demo/FeatureGuideTarget.tsx`
- Create: `frontend/src/demo/FeatureGuideDrawer.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/layouts/AppLayout.tsx`
- Modify: `frontend/src/pages/HomePage/components/ChatComposer.tsx`
- Modify: `frontend/src/pages/WikiPage/index.tsx`
- Modify: `frontend/src/pages/StylesPage/index.tsx`
- Modify: `frontend/src/pages/SettingPage/Menu.tsx`
- Modify: selected setting/about toolbar files required for the initial guide coverage.
- Test: `frontend/tests/staticDemoGuide.test.mjs`
- Test: `frontend/tests/staticDemoContracts.test.mjs`

**Interfaces:**
- Produces: `FeatureGuideEntry`, `getFeatureGuide(id)`, `FeatureGuideProvider`, `useFeatureGuide()`, and `<FeatureGuideTarget featureId onExecute?>`.
- `FeatureGuideEntry` contains `title`, `summary`, `userValue`, `behavior`, `productEvidence[]`, `codeEvidence[]`, `dataAndStates[]`, `demoLimit`, and `evidenceType`.
- Context produces `guideMode`, `setGuideMode`, `openGuide(featureId, execute?)`, `closeGuide()`, and `executeSelectedFeature()`.

- [ ] **Step 1: Write failing catalog and event-policy tests**

Assert required guide ids have product/code evidence; code paths are repository-relative; normal click executes with guide mode off; right-click opens guide without executing; guide-mode click opens guide; deferred execution runs once; Escape/close restores state.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test tests/staticDemoGuide.test.mjs tests/staticDemoContracts.test.mjs`
Expected: FAIL because guide modules/targets are absent.

- [ ] **Step 3: Implement provider, target, drawer, and initial catalog**

Catalog at minimum: new note, styles, Wiki, settings, about, composer chat/note/learn, upload, model selection, submit, Wiki type/community/zoom, create style, model provider, transcriber, downloader, migration, usage, monitor, MCP, research search, update check.

- [ ] **Step 4: Add transparent targets to existing UI**

Merge events without changing dimensions. Use the existing dialog/scroll/button primitives; drawer is fixed right, focusable, Escape-closeable, and mobile-width safe.

- [ ] **Step 5: Run guide/contracts/type tests**

Run: `cd frontend && node --test tests/staticDemoGuide.test.mjs tests/staticDemoContracts.test.mjs && pnpm test:contracts`
Expected: PASS.

- [ ] **Step 6: Commit only Task 5 files**

Commit message: `feat: explain demo product features`

### Task 6: Preview Script, Build Modes, and Deep-Route Smoke Test

**Files:**
- Create: `scripts/preview_static_demo.sh`
- Modify: `frontend/package.json`
- Modify: `frontend/vite.config.ts`
- Create: `frontend/tests/staticDemoPreviewScript.test.mjs`
- Test: `frontend/tests/staticDemoContracts.test.mjs`

**Interfaces:**
- Produces package scripts `build:demo` and `preview:demo`.
- Produces shell usage `bash scripts/preview_static_demo.sh [--port PORT] [--no-open]` with default host `127.0.0.1` and a demo-specific default port.

- [ ] **Step 1: Write failing script contract tests**

Assert strict shell mode, dependency checks, no backend startup, demo env flag, build before preview, validated numeric port, loopback default, nonzero failure behavior, URL output, and `--no-open` handling.

- [ ] **Step 2: Run tests and verify RED**

Run: `cd frontend && node --test tests/staticDemoPreviewScript.test.mjs`
Expected: FAIL because the script and package commands are absent.

- [ ] **Step 3: Implement package commands and shell script**

Use existing pnpm/Vite only. Do not install dependencies automatically without an explicit missing-dependency message. Keep process in foreground so Ctrl-C stops preview cleanly.

- [ ] **Step 4: Run script contracts and both builds**

Run: `cd frontend && node --test tests/staticDemoPreviewScript.test.mjs && pnpm build && pnpm build:demo`
Expected: PASS and both build commands exit 0.

- [ ] **Step 5: Smoke-test server and deep routes**

Run the script with `--no-open` on an unused explicit port, then request `/`, `/new`, `/notes/demo-note-success`, `/wiki`, `/styles`, `/settings/model`, and `/about`; expect HTTP 200 and the Vite app shell. Stop the exact spawned preview PID afterward.

- [ ] **Step 6: Commit only Task 6 files**

Commit message: `feat: preview static product demo`

### Task 7: Browser Visual Calibration and Full Verification

**Files:**
- Modify: only demo fixtures, targets, or demo-specific CSS proven to cause visual/interaction deviations.
- Create: `docs/superpowers/tests/2026-08-13-static-product-demo.md`
- Modify: `docs/system/current-architecture.md`
- Modify: `docs/requirements/2026-08-13-static-product-demo-and-feature-guide.md`
- Modify: `docs/system/change-spec-static-product-demo.md`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: verification evidence and long-lived architecture documentation for the new demo entry.

- [ ] **Step 1: Run full automated frontend verification**

Run: `cd frontend && node --test tests/*.test.mjs && pnpm test:contracts && pnpm build && pnpm build:demo`
Expected: all commands exit 0; record exact counts/output summaries.

- [ ] **Step 2: Start demo and verify network isolation in a browser**

Navigate all baseline routes and perform simulated generation, guide right-click, guide-mode click, style creation, settings changes, and updater check. Assert no business request targets `127.0.0.1:8483`, `/api`, `/mcp`, LLM providers, or Tauri.

- [ ] **Step 3: Capture baseline-sized screenshots**

At 3840×1916 capture the 10 states mapped in the design. Compare to `docs/product/*.png`; inspect sidebars, split ratios, spacing, typography, colors, cards/drawers, and scroll positions. Also inspect 1440px desktop and one mobile viewport.

- [ ] **Step 4: For each discovered deviation, use a new RED-GREEN test before code changes**

Add the smallest contract/runtime test that fails on the deviation, verify RED, patch only the demo cause, and verify GREEN. Do not modify production UI solely to force one screenshot.

- [ ] **Step 5: Run security and repository-scope scans**

Scan demo source/build output for secret-like keys and absolute paths; scan demo source for accidental backend fallback; review `git diff` to exclude unrelated work.

- [ ] **Step 6: Update durable docs and verification evidence**

Mark the requirement `Implemented` only after all acceptance criteria have evidence. Record commands, results, visual deviations and reasons, network findings, and any unverified risk in the test evidence document.

- [ ] **Step 7: Run final fresh verification**

Run the exact full frontend test/build suite and shell deep-route smoke again after documentation-adjacent code changes. Read full output before making completion claims.

- [ ] **Step 8: Commit only Task 7 files**

Commit message: `docs: verify static product demo`

## Plan Self-Review

- Spec coverage: mode isolation, backend-free fixtures, state matrix, simulated generation, direct fetch/Tauri boundaries, all screenshot routes, feature guide policy, preview shell, privacy, visual checks, formal docs, rollback, and production regression each map to a task.
- Placeholder scan: no TBD/TODO/“implement later” steps; every behavior has an exact file/interface/test command.
- Type consistency: runtime, scenario, transport, and feature-guide signatures are defined once and consumed under the same names.
- Execution choice: user explicitly requested execution in this session; use `superpowers:executing-plans` rather than dispatching subagents.
