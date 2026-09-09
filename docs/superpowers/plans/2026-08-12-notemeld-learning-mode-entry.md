# NoteMeld Learning Mode Entry Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a deterministic “学习” composer intent that builds a local-first canvas with academic/GitHub defaults, then shows guidance in chat and the complete learning experience in the right panel.

**Architecture:** Keep persisted conversations as `chat|note`; `learn` is a frontend-only submit intent. Centralize learning-source resolution in the backend, persist one compact guide message per canvas, and project the latest canvas into HomePage's existing split layout.

**Tech Stack:** React 18, TypeScript, Zustand, FastAPI, Pydantic, pytest, Node source-contract tests.

## Global Constraints

- Academic and GitHub research are always enabled for learning; Web is included only when Tavily or SearXNG is usable.
- Existing SQLite schemas, `ConversationMode`, canvas file paths, mastery transitions, desktop ready gate, response wrappers, chat, note, Wiki, MCP and packaging flows remain compatible.
- Full canvas state stays in the workspace JSON artifact; conversation messages remain compact.
- No unrelated refactor and no overwrite of pre-existing user/agent changes.

---

### Task 1: Lock backend source and guide contracts with RED tests

**Files:**
- Modify: `backend/tests/learning/test_research_search.py`
- Modify: `backend/tests/learning/test_learning_canvas_service.py`
- Modify: `backend/tests/learning/test_learning_api.py`
- Modify: `backend/tests/agent/test_learning_tools.py`

**Interfaces:**
- Produces expected `ResearchSearchConfigManager.get_learning_scopes() -> list[str]` behavior.
- Produces expected compact `learning_canvas.meta.source_types/recommended_node_id` contract.

- [x] **Step 1: Add failing scope tests** asserting academic/GitHub remain present even after an old config disables them, and Web appears only for a complete Tavily/SearXNG configuration.
- [x] **Step 2: Add failing service/API tests** asserting omitted scopes use defaults and the persisted guide message contains no full nodes.
- [x] **Step 3: Run** `PYTHONPATH=backend pytest backend/tests/learning/test_research_search.py backend/tests/learning/test_learning_canvas_service.py backend/tests/learning/test_learning_api.py backend/tests/agent/test_learning_tools.py -q` **and expect failures for missing default-scope and guide behavior.**

### Task 2: Implement backend defaults and compact learning guidance

**Files:**
- Modify: `backend/app/services/research_search_config.py`
- Modify: `backend/app/services/learning_canvas_service.py`
- Modify: `backend/app/routers/learning.py`
- Modify: `backend/app/agent/learning_tools.py`

**Interfaces:**
- `get_learning_scopes(requested_scopes: list[str] | None = None) -> list[str]` returns ordered unique scopes.
- `CreateCanvasPayload.external_scopes` accepts omission.
- `LearningCanvasService.create_canvas(..., external_scopes=None)` applies centralized resolution.

- [x] **Step 1: Implement `get_learning_scopes`** with baseline `academic, github` and validated optional Web.
- [x] **Step 2: Resolve providers at canvas creation time** so saving Web settings takes effect without backend restart.
- [x] **Step 3: Build compact guide content/meta** from the persisted canvas: goal, node count, source types, recommended node id/label, external error count; never embed nodes.
- [x] **Step 4: Keep old request/tool parameters compatible** while preventing them from removing baseline scopes.
- [x] **Step 5: Re-run Task 1 command and expect PASS.**

### Task 3: Lock frontend learning-entry and panel contracts with RED tests

**Files:**
- Modify: `frontend/tests/learningCanvasContracts.test.mjs`

**Interfaces:**
- Expects `createLearningCanvas(conversationId, {goal})`.
- Expects `ComposerMode` to contain `learn`, `ModeSwitch` to show `学习`, and HomePage to render `LearningCanvasCard` in a right content view.
- Expects the message renderer not to mount the full card inline.

- [x] **Step 1: Add source-contract assertions** for the three-mode switch, create API, panel projection, note/learning switching and scope-free settings.
- [x] **Step 2: Run** `node frontend/tests/learningCanvasContracts.test.mjs` **and expect failure.**

### Task 4: Implement explicit learning submission and right-side projection

**Files:**
- Modify: `frontend/src/services/learning.ts`
- Modify: `frontend/src/pages/HomePage/components/ChatComposer.tsx`
- Modify: `frontend/src/pages/HomePage/Home.tsx`
- Modify: `frontend/src/pages/HomePage/messageRenderers.tsx`
- Modify: `frontend/src/pages/HomePage/components/LearningCanvasCard.tsx`
- Modify: `frontend/src/pages/SettingPage/ResearchSearch.tsx`

**Interfaces:**
- `createLearningCanvas(conversationId, payload) -> Promise<LearningCanvas>`.
- `ComposerMode = 'note' | 'chat' | 'learn'`; persisted conversation mapping is `learn -> chat`.
- HomePage derives `latestLearningCanvasId` from the latest valid message.

- [x] **Step 1: Add the typed create API** and make Settings edit only optional Web/provider credentials.
- [x] **Step 2: Add Learn mode** without allowing URL/text auto-detection to overwrite explicit selection.
- [x] **Step 3: Implement `submitLearning`** to persist the user message and 构建状态、创建 canvas、重载会话、重置输入，并只在用户仍停留于发起页时导航；跨 composer 共享提交锁在任何异步操作前建立，canvas 创建成功是不可回滚的成功边界。
- [x] **Step 4: Replace the inline full card with a compact guidance bubble** that tolerates legacy meta.
- [x] **Step 5: Add desktop/mobile learning content views** and default to the newest canvas while preserving note switching.
- [x] **Step 6: Re-run** `node frontend/tests/learningCanvasContracts.test.mjs` **and expect PASS.**

### Task 5: Synchronize system docs and verify the complete increment

**Files:**
- Modify: `docs/system/current-architecture.md`
- Modify: `docs/system/product-rules.md`
- Modify: `docs/system/api-inventory.md`
- Modify: `docs/system/data-model.md` if required by contract wording only
- Modify: `docs/system/known-pitfalls.md`
- Modify: `docs/superpowers/tests/2026-08-11-notemeld-active-learning-space.md`

**Interfaces:** None beyond documenting the implemented contracts.

- [x] **Step 1: Update system docs** for frontend-only learn intent, default scopes, compact message and right panel recovery.
- [x] **Step 2: Run focused backend tests** from Task 1.
- [x] **Step 3: Run** `cd frontend && pnpm test:contracts && pnpm build`.
- [x] **Step 4: Run** `PYTHONPATH=backend pytest backend/tests -q`.
- [x] **Step 5: Run** `scripts/run_core_regression.sh` and `python3 -m compileall -q backend/app`.
- [x] **Step 6: Record exact results and any pre-existing warnings** in the evidence document; mark Change Spec acceptance only from observed results.

## Self-review

- Spec coverage: tasks map to all four new behaviors: default research, explicit entry, compact chat guidance, and right-side canvas with note coexistence.
- Placeholder scan: no TBD/TODO or undefined follow-on step is used.
- Type consistency: frontend uses `learn` only in `ComposerMode`; backend and store continue to use `chat|note`; all canvas API identifiers remain strings.
