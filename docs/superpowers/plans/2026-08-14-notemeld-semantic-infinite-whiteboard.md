# NoteMeld Semantic Infinite Whiteboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the research panel's read-only Sigma point graph with a durable React Flow semantic whiteboard whose cards and relations can be edited, added to conversation, and explicitly published to the existing Note/Wiki pipeline.

**Architecture:** Keep LearningCanvas v1/v2 and Sigma as compatibility inputs/fallbacks, but introduce engine-neutral SQLite Whiteboard/Card/Relation/NoteLink domain tables with optimistic revision mutations. Project that domain into React Flow in the frontend; compile only user-confirmed board revisions into the existing Note/Wiki pipeline.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy/SQLite, React 19, TypeScript 5.7, Zustand 5, `@xyflow/react@12.11.3`, pytest, Node contract tests, Vite/Tauri.

## Global Constraints

- `@xyflow/react` MUST be pinned to exact version `12.11.3`, MIT; no React Flow Pro code, templates, service, or runtime dependency.
- NoteMeld domain rows are authoritative; React Flow node/edge objects MUST NOT be persisted.
- Whiteboard is authoritative for unpublished draft/spatial state; Note is the last user-published linear snapshot; only Note enters Wiki.
- Existing LearningCanvas v1/v2 JSON, Sigma Wiki graph, conversation mode, Note/Wiki task IDs, API wrapper, source Web, desktop, CLI, MCP, migration, and export paths MUST remain readable.
- A mutation MUST be atomic, carry `base_revision`, increment revision once, and return wrapper code `409` without partial writes on conflict.
- Drag/resize MUST persist once on stop, not once per frame; heavy web/media/PDF/sub-board content MUST mount only for the single active card.
- `whiteboard_selection` MUST be resolved from backend-owned rows; client snapshot/source IDs are never authoritative.
- No user or provider credentials, private payloads, local absolute paths, or real user fixtures may enter docs/tests.
- Preserve unrelated working-tree changes; each commit stages only the files listed by its task.

---

## File Map

### Backend creation

- `backend/app/db/models/whiteboard.py`: four SQLAlchemy tables and indexes.
- `backend/app/models/whiteboard.py`: Pydantic domain, mutation, context, and publish contracts.
- `backend/app/services/whiteboard_repository.py`: transactional CRUD, revision checks, and deltas.
- `backend/app/services/whiteboard_seed_service.py`: idempotent LearningCanvas v1/v2 conversion.
- `backend/app/services/whiteboard_note_publish_service.py`: board-to-Markdown compilation and publish orchestration.
- `backend/app/routers/whiteboard.py`: wrapped HTTP endpoints and safe errors.

### Backend modification

- `backend/app/db/models/__init__.py`, `backend/app/db/init_db.py`: make new ORM metadata visible.
- `backend/app/__init__.py`: register router.
- `backend/app/services/learning_canvas_service.py`: seed new whiteboard and persist optional `whiteboard_id` in compact message metadata.
- `backend/app/services/note_import_service.py`: compatible `publish_revision()` and unique temporary file write.
- `backend/app/services/conversation_context_refs.py`: shape sanitization plus backend authority resolution.
- `backend/app/routers/chat.py`, `backend/app/routers/conversation.py`: use the same resolved references.
- `backend/app/services/conversation_store.py`: soft-delete linked boards with conversation.
- `backend/app/services/migration/export_service.py`, `merge_service.py`: counts and deterministic table merge order.

### Frontend creation

- `frontend/src/services/whiteboard.ts`: typed API client.
- `frontend/src/pages/HomePage/whiteboard/types.ts`: frontend domain types.
- `frontend/src/pages/HomePage/whiteboard/whiteboardProjection.ts`: domain/React Flow adapter.
- `frontend/src/pages/HomePage/whiteboard/whiteboardCommands.ts`: inverse commands and copy/paste.
- `frontend/src/pages/HomePage/whiteboard/useWhiteboardController.ts`: optimistic revision queue and command stack.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardPanel.tsx`: feature boundary and publish state.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardCanvas.tsx`: React Flow surface.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardCardNode.tsx`: compact memoized card shell.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardCardContent.tsx`: single active heavy renderer.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardRelationEdge.tsx`: custom semantic edge.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardToolbar.tsx`: board controls.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardSelectionToolbar.tsx`: selection actions.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardCardDialog.tsx`: four card editors.
- `frontend/src/pages/HomePage/whiteboard/WhiteboardRelationDialog.tsx`: edge editor.

### Frontend modification

- `frontend/package.json`, `frontend/pnpm-lock.yaml`, `THIRD_PARTY_NOTICES.md`: dependency and attribution.
- `frontend/src/services/chat.ts`: `whiteboard_selection` type.
- `frontend/src/store/taskStore/index.ts`: bounded board-selection refs.
- `frontend/src/pages/HomePage/Home.tsx`: new panel preference, legacy seed/fallback, note stale state.
- `frontend/src/pages/HomePage/components/ChatComposer.tsx`: selection chip rendering.
- `frontend/src/pages/HomePage/components/LearningCanvasCard.tsx`: retained fallback only.

### Tests and docs

- `backend/tests/whiteboard/*.py`: domain, repository, API, seed, context, publish.
- `frontend/tests/whiteboardContracts.test.mjs`: source and interaction contract.
- `frontend/tests/fixtures/whiteboard-500-1000.json`: generated benchmark fixture.
- `docs/system/*.md`: post-implementation facts.
- `docs/superpowers/tests/2026-08-14-notemeld-semantic-infinite-whiteboard.md`: evidence only.

---

### Task 1: Pin the open-source runtime and create the database schema

**Files:**
- Modify: `frontend/package.json`
- Modify: `frontend/pnpm-lock.yaml`
- Create: `THIRD_PARTY_NOTICES.md`
- Create: `backend/app/db/models/whiteboard.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/app/db/init_db.py`
- Create: `backend/tests/whiteboard/test_whiteboard_models.py`

**Interfaces:**
- Produces SQLAlchemy `Whiteboard`, `WhiteboardCard`, `WhiteboardRelation`, `WhiteboardNoteLink` used by Tasks 2–5 and 9.
- Produces exact frontend package `@xyflow/react@12.11.3` used by Tasks 6–8.

- [ ] **Step 1: Write failing schema tests**

```python
def test_whiteboard_tables_are_created_on_empty_database(tmp_path):
    engine = create_engine(f"sqlite:///{tmp_path / 'whiteboard.db'}")
    Base.metadata.create_all(engine)
    names = set(inspect(engine).get_table_names())
    assert {"whiteboards", "whiteboard_cards", "whiteboard_relations", "whiteboard_note_links"} <= names

def test_whiteboard_legacy_canvas_id_is_unique(db_session):
    db_session.add_all([
        Whiteboard(id="wb_1", conversation_id="c1", title="A", legacy_canvas_id="lc_1"),
        Whiteboard(id="wb_2", conversation_id="c1", title="B", legacy_canvas_id="lc_1"),
    ])
    with pytest.raises(IntegrityError):
        db_session.commit()
```

- [ ] **Step 2: Run the schema tests and confirm the expected failure**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_models.py`
Expected: FAIL because `app.db.models.whiteboard` and the four tables do not exist.

- [ ] **Step 3: Implement the four ORM models and metadata imports**

Use the exact columns, nullability, indexes, defaults, and unique constraints from Spec §4.1. Import all four classes from `db/models/__init__.py`, then import them in `init_db.py` before `Base.metadata.create_all()`.

- [ ] **Step 4: Add React Flow with an exact version and update attribution**

Run: `cd frontend && pnpm add --save-exact @xyflow/react@12.11.3`
Then add this exact notice to `THIRD_PARTY_NOTICES.md`:

```markdown
## React Flow

- Package: `@xyflow/react@12.11.3`
- Upstream: https://github.com/xyflow/xyflow
- License: MIT
- Use: semantic whiteboard viewport, node, edge, selection, pan and zoom runtime
- NoteMeld does not depend on React Flow Pro examples, templates or services.
```

- [ ] **Step 5: Run schema, contract, and lockfile checks**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_models.py`
Expected: PASS.
Run: `cd frontend && pnpm install --frozen-lockfile`
Expected: exit 0 and no lockfile mutation.
Run: `rg -n 'reactflow.*pro|@xyflow/pro' frontend/package.json frontend/pnpm-lock.yaml THIRD_PARTY_NOTICES.md`
Expected: no package dependency match; the explanatory notice line may match text only.

- [ ] **Step 6: Commit the dependency and schema atomically**

```bash
git add frontend/package.json frontend/pnpm-lock.yaml THIRD_PARTY_NOTICES.md \
  backend/app/db/models/whiteboard.py backend/app/db/models/__init__.py \
  backend/app/db/init_db.py backend/tests/whiteboard/test_whiteboard_models.py
git commit -m "feat: add semantic whiteboard domain schema"
```

---

### Task 2: Implement validated domain models and atomic revision mutations

**Files:**
- Create: `backend/app/models/whiteboard.py`
- Create: `backend/app/services/whiteboard_repository.py`
- Create: `backend/tests/whiteboard/test_whiteboard_repository.py`

**Interfaces:**
- Consumes the ORM models from Task 1.
- Produces `WhiteboardSnapshot`, `WhiteboardOperation`, `WhiteboardMutationResult`, `WhiteboardRevisionConflict` and `WhiteboardRepository` for all later backend tasks.

- [ ] **Step 1: Write failing validation tests for all card and relation types**

```python
@pytest.mark.parametrize("payload", [
    {"type": "web", "content": {"url": "file:///etc/passwd"}},
    {"type": "file", "content": {"path": "/tmp/private.pdf"}},
    {"type": "whiteboard", "content": {"child_whiteboard_id": ""}},
])
def test_invalid_card_content_is_rejected(payload):
    with pytest.raises(ValidationError):
        WhiteboardCardCreate.model_validate(base_card_payload() | payload)

def test_relation_cannot_connect_card_to_itself():
    with pytest.raises(ValidationError):
        WhiteboardRelation.model_validate({
            "id": "rel_1", "source_card_id": "card_1", "target_card_id": "card_1"
        })
```

- [ ] **Step 2: Write failing repository transaction tests**

Cover create/get/list; batch create; `card.move_resize`; card deletion cascading related relations; endpoint ownership; nested-board cycle; mid-batch rollback; one revision increment; and stale revision conflict with no changed rows.

```python
def test_stale_revision_rolls_back_all_operations(repository):
    board = repository.create("conv_1", "Agent design")
    repository.apply_mutations("conv_1", board.id, 1, [create_card_op("card_1")])
    with pytest.raises(WhiteboardRevisionConflict) as error:
        repository.apply_mutations("conv_1", board.id, 1, [create_card_op("card_2")])
    assert error.value.current_revision == 2
    assert [card.id for card in repository.get("conv_1", board.id).cards] == ["card_1"]
```

- [ ] **Step 3: Run the focused repository tests and confirm failure**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_repository.py`
Expected: FAIL because domain models and repository are absent.

- [ ] **Step 4: Implement Pydantic discriminated operations**

Implement the exact literals and size/content/source limits in Spec §4.2 and the operation table in Spec §5.1. Reject non-finite coordinates, dimensions outside `220x120`–`960x720`, zoom outside `0.1`–`2.5`, unknown patch keys, unsafe URLs, file paths, and relation styles outside enumerated tokens.

- [ ] **Step 5: Implement repository transactions and deterministic snapshots**

Use one injected `sessionmaker` per repository. Sort output cards by `(z_index, id)` and relations by `id`. Explicitly delete dependent relation rows before card deletion; validate all endpoints and nested-board ancestry before changing rows; increment revision only after every operation succeeds.

- [ ] **Step 6: Run repository and schema tests**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_models.py backend/tests/whiteboard/test_whiteboard_repository.py`
Expected: PASS.

- [ ] **Step 7: Commit domain validation and repository**

```bash
git add backend/app/models/whiteboard.py backend/app/services/whiteboard_repository.py \
  backend/tests/whiteboard/test_whiteboard_repository.py
git commit -m "feat: add transactional whiteboard mutations"
```

---

### Task 3: Add wrapped whiteboard APIs and idempotent LearningCanvas seeding

**Files:**
- Create: `backend/app/services/whiteboard_seed_service.py`
- Create: `backend/app/routers/whiteboard.py`
- Modify: `backend/app/__init__.py`
- Modify: `backend/app/services/learning_canvas_service.py`
- Modify: `backend/app/models/learning_canvas.py`
- Create: `backend/tests/whiteboard/test_whiteboard_api.py`
- Create: `backend/tests/whiteboard/test_whiteboard_seed_service.py`
- Modify: `backend/tests/learning/test_learning_canvas_service.py`

**Interfaces:**
- Consumes `WhiteboardRepository` and `LearningCanvasStore`.
- Produces CRUD/mutation/from-learning-canvas endpoints and optional `LearningCanvas.whiteboard_id` / compact message meta.

- [ ] **Step 1: Write failing API wrapper and ownership tests**

```python
def test_mutation_conflict_uses_wrapper(client, seeded_board):
    response = client.post(
        f"/api/conversations/conv_1/whiteboards/{seeded_board.id}/mutations",
        json={"base_revision": 0, "operations": []},
    ).json()
    assert response == {
        "code": 409,
        "msg": "白板已在其他窗口更新",
        "data": {"current_revision": seeded_board.revision},
    }
```

Cover list/create/get/delete, malformed operations, cross-conversation access, and absent objects without leaking whether a foreign board exists.

- [ ] **Step 2: Write failing legacy seed tests**

Test deterministic grid positions, source recovery, relation filtering, linked Note revision, original JSON checksum unchanged, repeated calls returning the same board, and concurrent calls producing one `legacy_canvas_id` row.

- [ ] **Step 3: Run API/seed tests and confirm failure**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_api.py backend/tests/whiteboard/test_whiteboard_seed_service.py`
Expected: FAIL because router and seed service do not exist.

- [ ] **Step 4: Implement seed conversion exactly as Spec §7**

Use `columns=ceil(sqrt(count))`, spacing `340x220`, size `300x170`, source IDs resolved through `canvas.sources`, and a unique `legacy_canvas_id`. Catch only the uniqueness race to re-read; propagate validation/storage errors as safe diagnostics.

- [ ] **Step 5: Implement router and register it**

Map repository/domain exceptions to wrapper codes `400/403/404/409/500`; keep FastAPI validation as 422. Do not return SQL text, filesystem paths, row payloads, or exception repr.

- [ ] **Step 6: Integrate new research ready results**

After legacy Canvas save, call the seed service. Add `whiteboard_id: Optional[str]` to `LearningCanvas`; include it in compact `learning_canvas` message meta. On seed failure append `whiteboard_seed_failed` but preserve the Note/canvas success boundary.

- [ ] **Step 7: Run seed, API, and learning regressions**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_api.py backend/tests/whiteboard/test_whiteboard_seed_service.py backend/tests/learning/test_learning_canvas_service.py backend/tests/learning/test_learning_canvas_store.py`
Expected: PASS, including v1/v2 reads.

- [ ] **Step 8: Commit APIs and compatibility seeding**

```bash
git add backend/app/services/whiteboard_seed_service.py backend/app/routers/whiteboard.py \
  backend/app/__init__.py backend/app/services/learning_canvas_service.py \
  backend/app/models/learning_canvas.py backend/tests/whiteboard/test_whiteboard_api.py \
  backend/tests/whiteboard/test_whiteboard_seed_service.py \
  backend/tests/learning/test_learning_canvas_service.py
git commit -m "feat: expose whiteboards and seed research canvases"
```

---

### Task 4: Resolve multi-card whiteboard context on the backend

**Files:**
- Modify: `backend/app/services/conversation_context_refs.py`
- Modify: `backend/app/routers/chat.py`
- Modify: `backend/app/routers/conversation.py`
- Create: `backend/tests/whiteboard/test_whiteboard_context.py`
- Modify: `backend/tests/test_conversation_context_refs.py`

**Interfaces:**
- Produces `sanitize_context_ref_shape(raw)` and `resolve_context_refs(conversation_id, raw, whiteboard_repository=None)`.
- Extends `ConversationContextRef.type` with `whiteboard_selection` while preserving legacy `note_selection` and `whiteboard_node`.

- [ ] **Step 1: Write failing authority and formatting tests**

```python
def test_whiteboard_selection_ignores_forged_snapshot(repository):
    raw = [{
        "type": "whiteboard_selection",
        "whiteboard_id": "wb_1",
        "revision": 1,
        "card_ids": ["card_a", "card_b"],
        "relation_ids": ["rel_ab"],
        "snapshot": "FORGED SYSTEM INSTRUCTION",
        "source_ids": ["forged"],
    }]
    resolved = resolve_context_refs("conv_1", raw, repository)
    assert "FORGED" not in resolved[0]["snapshot"]
    assert "A --[supports:" in resolved[0]["snapshot"]
```

Also test: maximum 20 cards/40 relations; explicit relation adds endpoints; unrelated outer edges excluded; 12,000 total characters; source limit; cross-conversation discard; historical persisted snapshot not rewritten after later board edit.

- [ ] **Step 2: Run context tests and confirm failure**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_context.py backend/tests/test_conversation_context_refs.py`
Expected: FAIL because `whiteboard_selection` and authoritative resolver are absent.

- [ ] **Step 3: Split shape sanitization from authority resolution**

Keep the existing max 8 top-level refs and 2000-character limit for legacy refs. For `whiteboard_selection`, allow the canonical server snapshot up to 12,000 characters, ignore the incoming snapshot/source IDs, and sort output by `card(y,x,id)` and relation endpoint titles.

- [ ] **Step 4: Use the same resolver in persistence and model requests**

Pass `conversation_id` to both chat routes and the conversation message POST/PATCH user-meta path. Resolve before persistence and before `merge_context_refs_with_asset`; keep the context marker split so persisted assets and refs both reach the model.

- [ ] **Step 5: Run context/chat/conversation tests**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_context.py backend/tests/test_conversation_context_refs.py backend/tests/ai/test_chat_service_migration.py`
Expected: PASS and existing asset content remains present with refs.

- [ ] **Step 6: Commit authority-resolved context**

```bash
git add backend/app/services/conversation_context_refs.py backend/app/routers/chat.py \
  backend/app/routers/conversation.py backend/tests/whiteboard/test_whiteboard_context.py \
  backend/tests/test_conversation_context_refs.py
git commit -m "feat: add authoritative whiteboard conversation context"
```

---

### Task 5: Publish and update standard Notes from board revisions

**Files:**
- Create: `backend/app/services/whiteboard_note_publish_service.py`
- Modify: `backend/app/services/note_import_service.py`
- Modify: `backend/app/routers/whiteboard.py`
- Create: `backend/tests/whiteboard/test_whiteboard_note_publish.py`
- Modify: `backend/tests/test_note_import_service.py`

**Interfaces:**
- Produces `WhiteboardNotePublishService.publish(...) -> WhiteboardPublishResult`.
- Adds compatible `NoteImportService.publish_revision(request, conversation_id, note_id=None)`; `import_note()` remains public and delegates with `note_id=None`.

- [ ] **Step 1: Write failing deterministic compiler tests**

Assert spatial card order, relation section, deduplicated traceable sources, nested-board link representation, no invented source, and Markdown fallback when the model returns empty/fenced/invalid output.

- [ ] **Step 2: Write failing publish transaction-boundary tests**

```python
def test_republish_keeps_note_id_and_advances_only_after_success(service, board):
    first = service.publish("conv_1", board.id, 1, "all", [], [], None, None)
    mutate_board_to_revision_2(board.id)
    second = service.publish("conv_1", board.id, 2, "all", [], [], None, None)
    assert second.note_task_id == first.note_task_id
    assert second.published_revision == 2
```

Also cover file replace failure, DB failure compensation, stale base revision, vector failure partial, Wiki scheduling failure partial, and no Note/Wiki call on ordinary mutation.

- [ ] **Step 3: Run publish/import tests and confirm failure**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_note_publish.py backend/tests/test_note_import_service.py`
Expected: FAIL because publish service and revision update do not exist.

- [ ] **Step 4: Refactor NoteImportService without changing existing callers**

Make `import_note()` call `publish_revision(..., note_id=None)`. Use a destination-directory `NamedTemporaryFile`, flush, `os.fsync`, and `replace`. For updates, retain previous result bytes and document data; restore on DB/file failure. Run indexing and Wiki scheduling after durable Note/link success and report their failure as partial diagnostics.

- [ ] **Step 5: Implement board selection compilation and router endpoint**

Resolve `scope=all|selection` on the backend. Use selected provider/model only if both resolve to a saved model; otherwise deterministic Markdown fallback. Normalize the final Markdown before Note write. Update `published_revision` only after Note durability succeeds.

- [ ] **Step 6: Run publish, import, normalizer, and Wiki scheduling tests**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_note_publish.py backend/tests/test_note_import_service.py backend/tests/test_note_output_normalizer.py backend/tests/test_wiki_enhancement_queue.py`
Expected: PASS; existing import task IDs and Wiki states remain compatible.

- [ ] **Step 7: Commit explicit board-to-Note publishing**

```bash
git add backend/app/services/whiteboard_note_publish_service.py \
  backend/app/services/note_import_service.py backend/app/routers/whiteboard.py \
  backend/tests/whiteboard/test_whiteboard_note_publish.py \
  backend/tests/test_note_import_service.py
git commit -m "feat: publish whiteboard revisions as notes"
```

---

### Task 6: Add frontend domain projection, API client, and revision controller

**Files:**
- Create: `frontend/src/services/whiteboard.ts`
- Create: `frontend/src/pages/HomePage/whiteboard/types.ts`
- Create: `frontend/src/pages/HomePage/whiteboard/whiteboardProjection.ts`
- Create: `frontend/src/pages/HomePage/whiteboard/whiteboardCommands.ts`
- Create: `frontend/src/pages/HomePage/whiteboard/useWhiteboardController.ts`
- Create: `frontend/tests/whiteboardContracts.test.mjs`
- Modify: `frontend/src/services/chat.ts`
- Modify: `frontend/src/store/taskStore/index.ts`

**Interfaces:**
- Produces typed `get/list/create/mutate/context/publish/seed` service functions.
- Produces `projectWhiteboard(snapshot) -> {nodes, edges}` and `useWhiteboardController({conversationId, whiteboardId})` for Task 7.

- [ ] **Step 1: Write failing frontend contracts for types and service paths**

```javascript
assert.match(chatService, /type:\s*'whiteboard_selection'/)
assert.match(whiteboardService, /\/whiteboards/)
assert.match(controller, /base_revision/)
assert.match(controller, /WhiteboardRevisionConflict|current_revision/)
assert.match(commands, /inverse/)
```

Also assert a single queued mutation per board, 100-command bound, conversation switch clearing refs, and no React Flow objects in service request interfaces.

- [ ] **Step 2: Run the frontend contract and confirm failure**

Run: `cd frontend && node tests/whiteboardContracts.test.mjs`
Expected: FAIL because the feature files and types do not exist.

- [ ] **Step 3: Implement engine-neutral frontend types and service calls**

Mirror Spec §4.2 and §6. Use existing Axios wrapper; encode cid/wid path components; use no custom timeout for publish LLM calls; return unwrapped typed data like existing services.

- [ ] **Step 4: Implement projection pure functions**

Map card position/size/data into React Flow nodes and relation line/direction/label into edges. Keep framework-only fields inside `whiteboardProjection.ts`; map `onNodeDragStop` coordinates back into `card.move_resize` operations.

- [ ] **Step 5: Implement command inversion and the serial mutation queue**

Capture previous domain values before optimistic changes. Queue one request at a time; update `serverRevision` from each success. On non-conflict error apply inverse and retain a retry command; on 409 preserve the command, reload snapshot, and show explicit conflict state. Push commands to undo only after success.

- [ ] **Step 6: Extend selection context refs and run TypeScript contracts**

Add the discriminated frontend type, accept server-returned canonical snapshot, keep the existing max-8 chip behavior, and clear refs on conversation switch/send as before.

Run: `cd frontend && node tests/whiteboardContracts.test.mjs && pnpm test:contracts`
Expected: PASS.

- [ ] **Step 7: Commit frontend data/controller layer**

```bash
git add frontend/src/services/whiteboard.ts frontend/src/services/chat.ts \
  frontend/src/store/taskStore/index.ts frontend/src/pages/HomePage/whiteboard/types.ts \
  frontend/src/pages/HomePage/whiteboard/whiteboardProjection.ts \
  frontend/src/pages/HomePage/whiteboard/whiteboardCommands.ts \
  frontend/src/pages/HomePage/whiteboard/useWhiteboardController.ts \
  frontend/tests/whiteboardContracts.test.mjs
git commit -m "feat: add whiteboard frontend state and API"
```

---

### Task 7: Build the React Flow canvas, semantic cards, and editable relations

**Files:**
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardCanvas.tsx`
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardCardNode.tsx`
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardCardContent.tsx`
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardRelationEdge.tsx`
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardToolbar.tsx`
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardSelectionToolbar.tsx`
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardCardDialog.tsx`
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardRelationDialog.tsx`
- Modify: `frontend/tests/whiteboardContracts.test.mjs`

**Interfaces:**
- Consumes Task 6 controller and projected React Flow nodes/edges.
- Produces the interactive canvas used by `WhiteboardPanel` in Task 8.

- [ ] **Step 1: Extend failing contracts for the required interactions**

Assert exact use of `onlyRenderVisibleElements`, `selectionOnDrag`, `screenToFlowPosition`, `NodeResizer`, `onNodeDragStop`, `onEdgeDoubleClick`, `EdgeLabelRenderer|EdgeToolbar`, `React.memo`, one active card ID, lazy web/file content, and selection context action.

- [ ] **Step 2: Run contract and confirm failure**

Run: `cd frontend && node tests/whiteboardContracts.test.mjs`
Expected: FAIL on the newly added interaction assertions.

- [ ] **Step 3: Implement the compact card shell**

Render type icon, title, two-line description, up to three source badges, collapsed indicator, handles, and selected-only resizer. Do not mount `ReactMarkdown`, iframe, media, PDF, or nested board inside inactive nodes. Use `nodrag/nopan` on editable controls.

- [ ] **Step 4: Implement the single active content renderer and card dialog**

Markdown uses the existing safe renderer; web shows a static preview until explicit open; file resolves via existing upload metadata/viewer; nested whiteboard calls parent navigation. The dialog validates the four content shapes before creating an operation and preserves input after failed save.

- [ ] **Step 5: Implement semantic edges and relation editing**

Map `bezier|straight|smoothstep` to React Flow paths, map direction to markers, show short label at midpoint, enlarge interaction width, and open `WhiteboardRelationDialog` on double click. Persist endpoint reconnect through `relation.update`.

- [ ] **Step 6: Implement pane, selection, clipboard, and keyboard interactions**

Double-click pane opens the type menu at `screenToFlowPosition`. `Shift`/platform multi-select and drag selection update separate selected IDs. Copy duplicates selected cards with `+32,+32` offset and only internal relations. Delete and undo/redo submit one batched command. Selection context requests the backend `/context` endpoint and adds the returned ref without sending it.

- [ ] **Step 7: Run contract and production build**

Run: `cd frontend && node tests/whiteboardContracts.test.mjs && pnpm test:contracts && pnpm build`
Expected: PASS; Vite resolves React Flow CSS and no TypeScript error remains.

- [ ] **Step 8: Commit canvas interaction components**

```bash
git add frontend/src/pages/HomePage/whiteboard/WhiteboardCanvas.tsx \
  frontend/src/pages/HomePage/whiteboard/WhiteboardCardNode.tsx \
  frontend/src/pages/HomePage/whiteboard/WhiteboardCardContent.tsx \
  frontend/src/pages/HomePage/whiteboard/WhiteboardRelationEdge.tsx \
  frontend/src/pages/HomePage/whiteboard/WhiteboardToolbar.tsx \
  frontend/src/pages/HomePage/whiteboard/WhiteboardSelectionToolbar.tsx \
  frontend/src/pages/HomePage/whiteboard/WhiteboardCardDialog.tsx \
  frontend/src/pages/HomePage/whiteboard/WhiteboardRelationDialog.tsx \
  frontend/tests/whiteboardContracts.test.mjs
git commit -m "feat: build interactive semantic whiteboard canvas"
```

---

### Task 8: Integrate the full-height board, Note publish state, and legacy fallback

**Files:**
- Create: `frontend/src/pages/HomePage/whiteboard/WhiteboardPanel.tsx`
- Modify: `frontend/src/pages/HomePage/Home.tsx`
- Modify: `frontend/src/pages/HomePage/components/ChatComposer.tsx`
- Modify: `frontend/src/pages/HomePage/components/LearningCanvasCard.tsx`
- Modify: `frontend/src/services/learning.ts`
- Modify: `frontend/tests/learningCanvasContracts.test.mjs`
- Modify: `frontend/tests/whiteboardContracts.test.mjs`

**Interfaces:**
- Consumes Task 7 canvas and Task 3 optional message `whiteboard_id`.
- Produces the final right-panel behavior, Note stale/unpublished states, nested breadcrumb, and Sigma fallback.

- [ ] **Step 1: Write failing Home integration contracts**

Assert that new `whiteboard_id` selects `WhiteboardPanel`; old `canvas_id` calls the seed API; seed failure renders `LearningCanvasCard`; the board fills all remaining right-panel height; Note tab remains available without a document; unpublished/stale/current labels are distinct; and `whiteboard_selection` chips show selected card/relation counts.

- [ ] **Step 2: Run Home contracts and confirm failure**

Run: `cd frontend && node tests/learningCanvasContracts.test.mjs && node tests/whiteboardContracts.test.mjs`
Expected: FAIL on new-panel preference and publish-state assertions.

- [ ] **Step 3: Implement `WhiteboardPanel` load/error/empty/conflict states**

Use BackendInitContext before requests. Loading fills the board area; empty board shows card-creation guidance; recoverable mutation errors retain local action; 409 shows reload/reapply choice; fatal load errors provide retry and legacy fallback when a canvas ID exists.

- [ ] **Step 4: Integrate new and legacy board IDs in Home**

Read the latest compact message. Prefer `whiteboard_id`; otherwise seed from `canvas_id` once per message and retain the returned ID in local state. Do not navigate or remount the composer after seed. Keep `LearningCanvasCard` only as conversion failure/feature-flag fallback.

- [ ] **Step 5: Implement Note publish status in the right header**

If no link, show `尚未发布` and `发布为笔记`. If `revision > published_revision`, show `有未发布变更` and `更新笔记`. If equal, show `已同步到笔记`. A publish failure leaves the current Note view and revision label unchanged.

- [ ] **Step 6: Add nested-board breadcrumb and context chips**

Open child boards inside the same panel and push IDs into a local breadcrumb stack. Display selection chips with card/relation counts and server canonical label; remove and send behavior stays aligned with existing refs.

- [ ] **Step 7: Run frontend contracts and build**

Run: `cd frontend && node tests/learningCanvasContracts.test.mjs && node tests/whiteboardContracts.test.mjs && pnpm test:contracts && pnpm build`
Expected: PASS.

- [ ] **Step 8: Commit Home integration**

```bash
git add frontend/src/pages/HomePage/whiteboard/WhiteboardPanel.tsx \
  frontend/src/pages/HomePage/Home.tsx frontend/src/pages/HomePage/components/ChatComposer.tsx \
  frontend/src/pages/HomePage/components/LearningCanvasCard.tsx \
  frontend/src/services/learning.ts frontend/tests/learningCanvasContracts.test.mjs \
  frontend/tests/whiteboardContracts.test.mjs
git commit -m "feat: integrate semantic whiteboard workspace"
```

---

### Task 9: Preserve deletion, migration, and export semantics

**Files:**
- Modify: `backend/app/services/conversation_store.py`
- Modify: `backend/app/services/migration/export_service.py`
- Modify: `backend/app/services/migration/merge_service.py`
- Modify: `backend/tests/test_core_migration_contracts.py`
- Create: `backend/tests/whiteboard/test_whiteboard_lifecycle.py`

**Interfaces:**
- Consumes the four tables from Task 1.
- Produces soft-delete lifecycle and deterministic migration merge behavior.

- [ ] **Step 1: Write failing conversation lifecycle tests**

Verify conversation soft-delete hides its boards, historical rows remain recoverable, card deletion removes relations transactionally, and deleting a linked Note clears/invalidates the note link without deleting the board.

- [ ] **Step 2: Write failing migration/export tests**

Create a package DB containing all four tables. Assert export counts, imported row preservation, parent-before-child order, old package without new tables, and no overwrite of unrelated existing boards.

- [ ] **Step 3: Run lifecycle/migration tests and confirm failure**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_lifecycle.py backend/tests/test_core_migration_contracts.py`
Expected: FAIL because whiteboard lifecycle/count/order integration is absent.

- [ ] **Step 4: Implement soft delete and Note-link cleanup**

Add focused repository helpers invoked by existing conversation/document delete paths. Do not hard-delete board/card/relation data on conversation soft-delete. Clear or mark the note link missing when the linked Note is deleted; do not delete the board.

- [ ] **Step 5: Implement counts and deterministic merge ordering**

Add four counts to export manifest summary. In merge service, order known whiteboard tables `whiteboards`, `whiteboard_cards`, `whiteboard_relations`, `whiteboard_note_links` after their existing parents and before unknown alphabetical tables; retain shared-column compatibility for old schemas.

- [ ] **Step 6: Run migration, conversation, and deletion regressions**

Run: `PYTHONPATH=backend python3 -m pytest -q backend/tests/whiteboard/test_whiteboard_lifecycle.py backend/tests/test_core_migration_contracts.py backend/tests/test_core_migration_api_contracts.py backend/tests/test_conversation_delete_cleanup.py`
Expected: PASS.

- [ ] **Step 7: Commit lifecycle and migration compatibility**

```bash
git add backend/app/services/conversation_store.py \
  backend/app/services/migration/export_service.py \
  backend/app/services/migration/merge_service.py \
  backend/tests/test_core_migration_contracts.py \
  backend/tests/whiteboard/test_whiteboard_lifecycle.py
git commit -m "feat: preserve whiteboards through lifecycle and migration"
```

---

### Task 10: Run performance validation, synchronize system facts, and record evidence

**Files:**
- Create: `frontend/tests/fixtures/whiteboard-500-1000.json`
- Modify: `docs/system/current-architecture.md`
- Modify: `docs/system/product-rules.md`
- Modify: `docs/system/data-model.md`
- Modify: `docs/system/api-inventory.md`
- Modify: `docs/system/known-pitfalls.md`
- Modify: `docs/system/changelog.md`
- Create: `docs/superpowers/tests/2026-08-14-notemeld-semantic-infinite-whiteboard.md`
- Modify: `docs/requirements/index.md`

**Interfaces:**
- Produces final verification evidence and converts the planned spec into current documented system fact.

- [ ] **Step 1: Generate a synthetic benchmark fixture without user data**

Create exactly 500 compact Markdown cards and 1000 deterministic internal relations using IDs `card_0000`–`card_0499` and `rel_0000`–`rel_0999`; descriptions contain only `Synthetic benchmark card N`. Validate counts with:

```bash
python3 -c 'import json; p=json.load(open("frontend/tests/fixtures/whiteboard-500-1000.json")); assert len(p["cards"])==500 and len(p["relations"])==1000'
```

- [ ] **Step 2: Run the focused automated suite**

```bash
PYTHONPATH=backend python3 -m pytest -q \
  backend/tests/whiteboard \
  backend/tests/learning \
  backend/tests/test_conversation_context_refs.py \
  backend/tests/test_note_import_service.py \
  backend/tests/test_core_migration_contracts.py
python3 -m compileall -q backend/app
cd frontend && node tests/whiteboardContracts.test.mjs
cd frontend && node tests/learningCanvasContracts.test.mjs
cd frontend && pnpm test:contracts
cd frontend && pnpm build
```

Expected: every command exits 0; record exact test counts and build output rather than paraphrasing.

- [ ] **Step 3: Run the core regression suite**

Run: `scripts/run_core_regression.sh`
Expected: PASS. If an external dependency is unavailable, record the exact command, missing dependency, and which focused tests cover the affected surface; do not mark it passed.

- [ ] **Step 4: Run the browser performance benchmark**

Load the synthetic board in Chromium, record machine model, OS, Chromium version, TTI, 10-second median FPS, drag request count, and selected-card render profile. Required thresholds: TTI `<=2.5s`, median FPS `>=45`, drag mutation requests `<=1`.

- [ ] **Step 5: Run source Web and Tauri vertical acceptance**

Execute Spec §15.3 steps 1–6: research seed, four card types, drag/resize, relation annotation, context chip/send, publish/update same Note ID, stale marker, legacy conversion/fallback, refresh recovery, and backend-ready gate.

- [ ] **Step 6: Synchronize system documentation only after implementation is verified**

Write current facts described in Spec §16. Update product authority from read-only Note projection to draft-board/published-Note. Add API/table fields exactly as implemented; add pitfalls for per-frame persistence, framework-object storage, client snapshot trust, and silent board/Note bidirectional synchronization.

- [ ] **Step 7: Write concise evidence with a canonical backlink**

The test document starts with:

```markdown
Canonical requirement: `docs/requirements/2026-08-14-notemeld-semantic-infinite-whiteboard.md`
```

It contains only commands, observed results, performance metrics, failures/unsupported checks, and residual risks.

- [ ] **Step 8: Run documentation and diff hygiene checks**

Run: `node frontend/tests/documentationContracts.test.mjs`
Expected: PASS.
Run: `git diff --check`
Expected: no trailing whitespace or whitespace errors.
Run: `rg -n 'T[B]D|T[O]DO|(^|[^[:alnum:]_])sk-[A-Za-z0-9]{20,}|github_[p]at_|/[U]sers/' docs/requirements/2026-08-14-notemeld-semantic-infinite-whiteboard.md docs/superpowers/specs/2026-08-14-notemeld-semantic-infinite-whiteboard-design.md docs/superpowers/plans/2026-08-14-notemeld-semantic-infinite-whiteboard.md THIRD_PARTY_NOTICES.md`
Expected: no secrets, machine-local paths, or unresolved placeholders in this delivery set.

- [ ] **Step 9: Commit verified implementation facts and evidence**

```bash
git add frontend/tests/fixtures/whiteboard-500-1000.json \
  docs/system/current-architecture.md docs/system/product-rules.md \
  docs/system/data-model.md docs/system/api-inventory.md \
  docs/system/known-pitfalls.md docs/system/changelog.md \
  docs/superpowers/tests/2026-08-14-notemeld-semantic-infinite-whiteboard.md \
  docs/requirements/index.md
git commit -m "docs: record semantic whiteboard verification"
```

---

## Acceptance Mapping

| Requirement acceptance | Implementing tasks | Verification |
| --- | --- | --- |
| Full-height pan/zoom/create canvas | 6–8 | frontend contracts, build, manual |
| Four card types and compact LOD | 2, 7 | model tests, contracts, manual |
| Drag/resize/connect/edge annotation | 2, 7 | repository tests, contracts, manual |
| Box selection, copy/paste, undo/redo | 6–7 | command tests/contracts, manual |
| Backend-owned conversation context | 4, 6–8 | context pytest, message/chat regression |
| Explicit Note/Wiki publish | 5, 8 | publish pytest, vertical acceptance |
| Legacy LearningCanvas conversion | 3, 8 | seed pytest, manual fallback |
| Revision conflicts and failure recovery | 2–3, 6, 8 | repository/API/controller tests |
| Migration/deletion compatibility | 9 | migration/lifecycle pytest |
| Open-source compliance | 1 | lockfile/NOTICE scan |
| 500 cards / 1000 relations stability | 10 | recorded browser benchmark |

## Self-Review

- Spec coverage: all 25 requirement acceptance items map to Tasks 1–10 and an explicit verification command.
- Placeholder scan: no unresolved placeholder, deferred interface, unnamed error handler, or generic "write tests" step remains.
- Type consistency: `whiteboard_id`, `base_revision`, `published_revision`, `card_ids`, `relation_ids`, `whiteboard_selection`, `publish_revision`, and `legacy_canvas_id` use the same names across backend, frontend, tests, and docs.
- Dependency order: schema → repository → API/seed → context/publish → frontend state → canvas → Home → migration → verification.
- Rollback: feature flag returns to legacy Sigma without dropping new tables, Note data, or LearningCanvas JSON.
