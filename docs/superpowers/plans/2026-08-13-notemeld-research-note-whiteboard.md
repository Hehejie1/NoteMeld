# Research Note Whiteboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Learning into an active research conversation whose durable artifact is a standard Note with a switchable whiteboard projection and reusable context references.

**Architecture:** Extend the existing LearningCanvas as a backward-compatible projection bound to a NoteDocument. Compile filtered local/external evidence into a research note, reuse NoteImportService/Wiki, and extend existing conversation meta/free-chat payloads with bounded references.

**Tech Stack:** FastAPI, Pydantic, SQLite/SQLAlchemy, React 19, TypeScript, Zustand, Sigma, pytest, Node contract tests.

## Global Constraints

- Note Markdown is the only canonical body; canvas labels/summaries are rebuildable projection caches.
- External search results are evidence candidates and never become nodes directly.
- No SQLite migration, new dependency, conversation-mode change, synchronous full Wiki rebuild, or deletion of legacy canvas/mastery data.
- One context snapshot is at most 2000 characters and one request contains at most 8 references.
- Note creation success is the transaction boundary; projection/message/Wiki failures cannot convert it to a failed note.

---

### Task 1: Research compilation domain

**Files:**
- Create: `backend/app/services/research_note_compiler.py`
- Modify: `backend/app/models/learning_canvas.py`
- Test: `backend/tests/learning/test_research_note_compiler.py`

**Interfaces:**
- Produces `ResearchNoteCompiler.compile(goal, local_nodes, sources, provider_id, model_name) -> ResearchCompilation`.
- Produces canvas v2 optional fields used by Task 2.

- [x] Write failing tests for irrelevant GitHub rejection, source-not-node, single clarification, valid ready compilation and deterministic fallback.
- [x] Run `PYTHONPATH=backend pytest backend/tests/learning/test_research_note_compiler.py -q` and verify expected failures.
- [x] Implement bounded relevance filtering, Pydantic compiler output, model adapter and deterministic fallback.
- [x] Re-run the test and verify pass.

### Task 2: Bind ready research to standard Note

**Files:**
- Modify: `backend/app/services/learning_canvas_service.py`
- Modify: `backend/app/routers/learning.py`
- Test: `backend/tests/learning/test_learning_canvas_service.py`
- Test: `backend/tests/learning/test_learning_api.py`

**Interfaces:**
- Consumes `ResearchCompilation`.
- Produces `LearningCanvas.document_task_id`, compact clarification/ready messages and standard NoteDocument.

- [x] Write failing service/API tests: clarification writes no Note; ready imports Note; message meta is compact; old requests remain valid.
- [x] Run focused tests and verify failures.
- [x] Inject compiler and note importer into LearningCanvasService; add optional provider/model request fields.
- [x] Treat Note success as transaction boundary and preserve legacy loader compatibility.
- [x] Re-run focused tests and verify pass.

### Task 3: Bounded conversation references

**Files:**
- Modify: `backend/app/routers/chat.py`
- Create: `backend/app/services/conversation_context_refs.py`
- Modify: `frontend/src/services/chat.ts`
- Modify: `frontend/src/store/taskStore/index.ts`
- Test: `backend/tests/test_conversation_context_refs.py`

**Interfaces:**
- Produces `sanitize_context_refs(raw) -> list[dict]` and `format_context_refs(raw) -> str`.
- Produces Zustand `pendingContextRefs/add/remove/clear`.

- [x] Write failing tests for type validation, count/snapshot limits and prompt isolation.
- [x] Run the test and verify failures.
- [x] Implement sanitization and merge formatted references into free-chat asset context without changing downstream signatures.
- [x] Add matching frontend types/store state.
- [x] Re-run tests and verify pass.

### Task 4: Note/whiteboard dual view and context menus

**Files:**
- Modify: `frontend/src/pages/HomePage/Home.tsx`
- Modify: `frontend/src/pages/HomePage/components/MarkdownViewer.tsx`
- Modify: `frontend/src/pages/HomePage/components/LearningCanvasCard.tsx`
- Modify: `frontend/src/pages/HomePage/components/LearningCanvasGraph.tsx`
- Modify: `frontend/src/pages/WikiPage/graph/SigmaWikiGraph.tsx`
- Modify: `frontend/src/pages/HomePage/components/ChatComposer.tsx`
- Modify: `frontend/src/pages/HomePage/messageRenderers.tsx`
- Modify: `frontend/src/services/learning.ts`
- Test: `frontend/tests/learningCanvasContracts.test.mjs`

**Interfaces:**
- Consumes canvas `document_task_id/overview/clarification/suggested_actions` and context-ref store.
- Produces right-click note/node references, composer chips, `笔记 | 白板`, focus/research actions.

- [x] Add failing source-contract assertions for dual view, no information-dump sections, note/node context menus, bounded refs in payload and typed actions.
- [x] Run `node frontend/tests/learningCanvasContracts.test.mjs` and verify failure.
- [x] Redesign ready/clarifying message renderer and LearningCanvasCard; add Sigma right-click and graph controls.
- [x] Add Markdown selection menu and composer reference chips/payload persistence.
- [x] Change Home right panel to Note/Whiteboard projection with legacy fallback.
- [x] Re-run frontend contract test and verify pass.

### Task 5: Documentation and verification

**Files:**
- Modify: `docs/system/current-architecture.md`
- Modify: `docs/system/product-rules.md`
- Modify: `docs/system/data-model.md`
- Modify: `docs/system/api-inventory.md`
- Modify: `docs/system/known-pitfalls.md`
- Create: `docs/superpowers/tests/2026-08-13-notemeld-research-note-whiteboard.md`

- [x] Run focused backend learning/context/note tests.
- [x] Run `python3 -m compileall -q backend/app`.
- [x] Run `cd frontend && pnpm test:contracts && pnpm build`.
- [x] Run `scripts/run_core_regression.sh` if the environment supports its dependencies.
- [x] Record exact observed results and residual risks; synchronize system facts.

## Self-review

- Coverage: all requirement acceptance items map to Tasks 1-5.
- Placeholder scan: no implementation placeholder or undefined follow-on interface remains.
- Type consistency: `document_task_id`, `context_refs`, `suggested_actions`, `provider_id` and `model_name` use the same names across backend/frontend.
- Scope: one vertical research-note workflow; free drawing and multi-agent evolution remain excluded.

---

### Task 6: Full-height whiteboard and progressive node detail (2026-08-14)

**Files:**
- Modify: `frontend/src/pages/HomePage/Home.tsx`
- Modify: `frontend/src/pages/HomePage/components/LearningCanvasCard.tsx`
- Modify: `frontend/src/pages/HomePage/components/LearningCanvasGraph.tsx`
- Modify: `frontend/src/pages/WikiPage/graph/SigmaWikiGraph.tsx`
- Modify: `frontend/src/pages/WikiPage/graph/layout.ts`
- Test: `frontend/tests/learningCanvasContracts.test.mjs`

- [x] Add failing contracts for Camera display coordinates/reset, resize observation, full-height Home mounting, a single in-canvas inspector, and zero-edge layout.
- [x] Replace fixed focus footer with one absolute in-canvas inspector containing the existing context-reference action.
- [x] Let LearningCanvasCard fill the right panel below the view switch without ScrollArea/padding wrappers.
- [x] Correct Sigma focus/reset behavior and resize handling; add deterministic compact layout for edge-less graphs.
- [x] Run the focused contract, frontend type/build verification, and record evidence.
