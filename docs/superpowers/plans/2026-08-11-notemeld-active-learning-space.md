# NoteMeld Active Learning Space Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:test-driven-development for each task and superpowers:verification-before-completion before claiming completion. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a persistent, source-traceable learning space that starts from NoteMeld knowledge, fills gaps with Web/arXiv/GitHub research, and only advances mastery from learner evidence.

**Architecture:** Keep Wiki and note storage unchanged. Add a conversation-scoped `LearningCanvas` JSON artifact under the existing workspace `canvases/` directory, a multi-source research service, a learning/assessment service, wrapped `/api` endpoints, and a conversation message renderer. V1 uses one Agent with researcher/curriculum/tutor/examiner phases; no multi-Agent runtime.

**Tech Stack:** FastAPI, Pydantic, httpx, SQLite conversation messages, local JSON workspace artifacts, React 19, TypeScript, Sigma/graphology, Zustand, existing Axios wrapper.

## Global Constraints

- Local Wiki and notes are searched before any external provider.
- External source discovery may be automatic; external collection/compilation requires user confirmation.
- `mastered` requires learner evidence and delayed review; exposure alone never advances mastery.
- Existing `graph.json`, TaskStatus, `/api/chat/*`, `/mcp`, desktop ready gate, source/CLI/desktop entry points remain compatible.
- Provider credentials stay local, are masked in responses, and never enter logs or canvas artifacts.
- Slow network/LLM calls must not run under Wiki write locks.
- All ordinary `/api` responses keep `{code,msg,data}`.

---

### Task 1: Learning domain contracts and safe persistence

**Files:**
- Create: `backend/app/models/learning_canvas.py`
- Create: `backend/app/services/learning_canvas_store.py`
- Modify: `backend/app/agent/workspace.py`
- Test: `backend/tests/learning/test_learning_canvas_store.py`

**Interfaces:**
- Produces: `LearningCanvas`, `LearningNode`, `LearningSource`, `MasteryEvidence`, `LearningCanvasStore.load/save/create_path`.
- Persists: `<note_output_dir>/workspaces/{conversation_id}/canvases/{canvas_id}.json`.

- [x] **Step 1: Write failing contract tests** for schema defaults, unsafe IDs, round-trip recovery, and concurrent atomic writes.
- [x] **Step 2: Run** `pytest backend/tests/learning/test_learning_canvas_store.py -q` and confirm failures.
- [x] **Step 3: Implement Pydantic contracts** with `mastery ∈ unknown|exposed|learning|provisional|mastered`, evidence kinds `exposed|recall|explain|apply|transfer|review`, and version `1`.
- [x] **Step 4: Implement store** using workspace path validation and unique temp files before `replace()`; never reuse a fixed `.tmp` name.
- [x] **Step 5: Run the focused test** and confirm PASS.

### Task 2: Local research and external source adapters

**Files:**
- Create: `backend/app/services/research_search_config.py`
- Create: `backend/app/services/research_search.py`
- Modify: `backend/app/services/web_search.py`
- Modify: `backend/app/utils/storage_paths.py`
- Test: `backend/tests/learning/test_research_search.py`

**Interfaces:**
- `ResearchSearchConfigManager.get_public_config() -> dict` masks `tavily_api_key` and `github_token`.
- `ResearchSearchService.search(query, scopes, limit) -> ResearchSearchBundle` returns independent `sources` and `errors`.
- Adapters: `TavilySearchProvider`, `SearxngSearchProvider`, `ArxivSearchProvider`, `GitHubSearchProvider`.

- [ ] **Step 1: Write failing adapter tests** with mocked httpx responses for normalization, timeouts, auth failures, and partial success.
- [x] **Step 2: Run focused tests** and confirm failure.
- [x] **Step 3: Add `research_search_config_path()`** under `<data_root>/config/research_search.json`.
- [x] **Step 4: Implement config manager** with atomic local JSON writes and masked public output.
- [x] **Step 5: Implement providers** using bounded timeouts and stable User-Agent; parse arXiv Atom metadata and GitHub REST metadata without inventing missing fields.
- [x] **Step 6: Implement orchestrator** so provider failures append typed errors while successful providers remain usable.
- [ ] **Step 7: Keep `WebSearchCollector` compatible** by adapting unified sources back to its existing result shape.
- [x] **Step 8: Run focused tests** and confirm PASS.

### Task 3: Canvas builder and deterministic learning path

**Files:**
- Create: `backend/app/services/learning_canvas_service.py`
- Test: `backend/tests/learning/test_learning_canvas_service.py`

**Interfaces:**
- `create_canvas(conversation_id, goal, external_scopes, external_limit) -> LearningCanvas`.
- `build_local_sources(goal) -> list[LearningSource]` reuses `WikiSearch` and note indexes.
- `build_path(nodes, edges) -> list[LearningPathStep]` guarantees prerequisites precede dependents.

- [x] **Step 1: Write failing tests** for local-first ordering, zero-result behavior, partial external failure, source attachment, and topological ordering.
- [x] **Step 2: Run focused tests** and confirm failure.
- [x] **Step 3: Implement local retrieval** from contributions/Wiki search without mutating or rebuilding Wiki.
- [x] **Step 4: Implement deterministic source-to-node canvas fallback** so the feature works even when LLM synthesis fails.
- [ ] **Step 5: Add optional LLM synthesis boundary** that can enrich summaries/relations but must validate against the same schema and fall back safely.
- [x] **Step 6: Persist the canvas and append one `learning_canvas` conversation message** containing only summary identifiers; full state stays in the workspace artifact.
- [x] **Step 7: Run focused tests** and confirm PASS.

### Task 4: Diagnostic, study unit, assessment, and review state machine

**Files:**
- Create: `backend/app/services/learning_session_service.py`
- Test: `backend/tests/learning/test_learning_session_service.py`

**Interfaces:**
- `start_unit(canvas, node_id) -> LearningUnit` records exposure only.
- `submit_evidence(canvas, node_id, kind, answer, rubric_result) -> LearningCanvas`.
- `due_reviews(canvas, now) -> list[ReviewItem]`.

- [x] **Step 1: Write failing state-machine tests** proving exposure cannot become mastered, recall+apply becomes provisional, failed review returns learning, and delayed review can become mastered.
- [x] **Step 2: Run focused tests** and confirm failure.
- [x] **Step 3: Implement transition rules** as pure functions before any LLM integration.
- [x] **Step 4: Implement question/unit generation fallback** from node summary and prerequisites.
- [ ] **Step 5: Add optional LLM rubric evaluation** with stored rubric version, score, feedback, answer summary, and timestamp; invalid LLM JSON is a recoverable assessment error.
- [ ] **Step 6: Persist every transition atomically** and mirror mastery into the bound Research Space only after provisional/mastered transitions.
- [x] **Step 7: Run focused tests** and confirm PASS.

### Task 5: Wrapped HTTP APIs and Agent tools

**Files:**
- Create: `backend/app/routers/learning.py`
- Create: `backend/app/agent/learning_tools.py`
- Modify: `backend/app/__init__.py`
- Modify: `backend/app/agent/agent_service.py`
- Modify: `backend/app/routers/config.py`
- Test: `backend/tests/learning/test_learning_api.py`
- Test: `backend/tests/agent/test_learning_tools.py`

**Interfaces:**
- `GET/PUT /api/research-search/config`.
- `POST /api/conversations/{cid}/learning-canvases`.
- `GET/PATCH /api/conversations/{cid}/learning-canvases/{canvas_id}`.
- `POST .../{canvas_id}/units/{node_id}/start`.
- `POST .../{canvas_id}/units/{node_id}/evidence`.
- Agent tools: `build_learning_canvas`, `read_learning_canvas`, `start_learning_unit`, `submit_learning_evidence`.

- [ ] **Step 1: Write failing API tests** for wrappers, not-found, unsafe IDs, masked config, and state transitions.
- [x] **Step 2: Run focused tests** and confirm failure.
- [x] **Step 3: Implement request/response models and routes** with no raw business dict responses.
- [x] **Step 4: Implement Agent tools** bound to `conversation_id`; register only in the Agent-enabled free-chat path.
- [x] **Step 5: Preserve feature-flag rollback** so `AGENT_CHAT_ENABLED=false` keeps existing behavior.
- [x] **Step 6: Run API and compatibility tests** and confirm PASS.

### Task 6: Frontend learning canvas and interaction

**Files:**
- Create: `frontend/src/services/learning.ts`
- Create: `frontend/src/pages/HomePage/components/LearningCanvasCard.tsx`
- Create: `frontend/src/pages/HomePage/components/LearningCanvasGraph.tsx`
- Modify: `frontend/src/pages/HomePage/messageRenderers.tsx`
- Modify: `frontend/src/store/taskStore/index.ts`
- Test: `frontend/tests/learningCanvasContracts.test.mjs`

**Interfaces:**
- `learning_canvas` is a new conversation message type; unknown/legacy payloads fall back to assistant text.
- Graph transforms LearningCanvas nodes/edges into existing `SigmaWikiGraph` compatible data, using mastery colors via `community_color`.

- [x] **Step 1: Write failing source-contract tests** for message type, service endpoints, mastery labels, source links, and no “exposed → mastered” UI action.
- [x] **Step 2: Run** `cd frontend && pnpm test:contracts` and confirm the new assertions fail.
- [x] **Step 3: Add typed API client** for canvas load, start unit, submit evidence, and patch label/summary.
- [x] **Step 4: Render six sections**: goal/diagnosis, focus, graph, path, current unit, review queue.
- [ ] **Step 5: Reuse Sigma/graphology** for click/focus/fullscreen; clicking a node selects it and offers “开始学习”, not an implicit mastery update.
- [ ] **Step 6: Wire evidence submission** so feedback and new mastery arrive from backend state.
- [x] **Step 7: Run TypeScript contracts and build** and confirm PASS.

### Task 7: Settings, documentation, and complete verification

**Files:**
- Create: `frontend/src/pages/SettingPage/ResearchSearch.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/pages/SettingPage/Menu.tsx`
- Modify: `docs/system/current-architecture.md`
- Modify: `docs/system/product-rules.md`
- Modify: `docs/system/data-model.md`
- Modify: `docs/system/api-inventory.md`
- Modify: `docs/system/known-pitfalls.md`
- Create: `docs/superpowers/tests/2026-08-11-notemeld-active-learning-space.md`

- [x] **Step 1: Add Settings form** for Web/arXiv/GitHub scopes, SearXNG endpoint, Tavily key and optional GitHub token; never display stored secrets.
- [x] **Step 2: Add frontend ready-gate contract** so settings/learning requests wait for backend readiness in desktop mode.
- [x] **Step 3: Update system documents** for architecture, local JSON artifacts, endpoints, mastery transitions, privacy boundary and concurrent canvas writes.
- [x] **Step 4: Run backend focused suite:** `pytest backend/tests/learning backend/tests/agent/test_learning_tools.py -q`.
- [ ] **Step 5: Run backend regression:** `pytest backend/tests -q`.
- [x] **Step 6: Run frontend contracts/build:** `cd frontend && pnpm test:contracts && pnpm build`.
- [x] **Step 7: Run core regression:** `scripts/run_core_regression.sh` when environment dependencies are available.
- [x] **Step 8: Record exact commands/results/failures** in the test evidence document and update requirement/index status only if required gates pass.

## Acceptance Mapping

| Requirement acceptance | Plan tasks |
| --- | --- |
| 1 search provider error | 2, 5, 7 |
| 2 selective compile/cancel | 3, 5; full compile orchestration remains a follow-on if current skill parameter collector cannot resume safely |
| 3 persisted rich artifact | 1, 3, 5, 6 |
| 4 mastery-aware priority | 3, 4, 6 |
| 5 node deepening/merge | 5, 6 |
| 6 topological path | 3, 6 |
| 7 exposure is not mastery | 1, 4, 6 |
| 8 provisional + delayed review | 4, 5, 6 |
| 9 local/arXiv/GitHub typed sources | 2, 3, 6 |
| 10 external failure fallback | 2, 3, 5 |
| 11 refresh/restart recovery | 1, 4, 5, 6 |

## Risks and rollback

- Set `AGENT_CHAT_ENABLED=false` to remove Agent tool exposure without deleting canvas files.
- External provider failures degrade to local-only; they never clear existing canvas or Research Space state.
- New APIs and message types are additive. Rollback can stop routing/rendering while leaving local JSON artifacts readable.
- If assessment quality is unreliable, disable LLM rubric evaluation and retain pure state transitions with `assessment_error`; do not promote mastery.
- Do not delete the nullable `research_space_id` column or P3 artifacts during rollback.
