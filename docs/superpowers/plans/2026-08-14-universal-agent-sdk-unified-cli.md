# Universal Agent SDK and Unified CLI Implementation Plan

> **状态：Superseded。** 用户已取消“一发布周期 Python oracle/rollback”兼容方案。新计划为 `docs/superpowers/plans/2026-08-17-agent-sdk-single-runtime-cutover.md`，本文件只保留历史证据，不得继续作为执行入口。

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 NoteMeld 现有 Python Agent 能力迁移为单一 Rust Agent SDK，并让桌面 UI、Web Host、`notemeld agent` CLI、iOS、Android 与 OpenHarmony 产物共享同一 Turn/Event/Session 语义及同一份 NoteMeld 会话数据。

**Architecture:** Rust workspace 是 Agent 行为的唯一事实源；平台差异通过 Driver 与 binding 注入。FastAPI 进程内加载 SDK 并作为本机 Agent Host，统一负责会话、Turn、事件、审批与 SQLite 持久化。React UI 与 CLI 都只调用 `/api/agent/v1`，现有 `/api/chat/free/stream` 在一个发布周期内作为兼容入口转发到新 Host。

**Tech Stack:** Rust 2021、Tokio、Serde、UniFFI/C ABI、Python 3.11、FastAPI、SQLAlchemy/SQLite、React/TypeScript、Tauri 2、pytest、Vitest/Node contract tests、GitHub Actions。

## Global Constraints

- Canonical requirement: `docs/requirements/2026-08-14-universal-agent-sdk-unified-cli.md`。
- Approved design: `docs/superpowers/specs/2026-08-14-universal-agent-sdk-unified-cli-design.md`。
- Change Spec: `docs/system/change-spec-universal-agent-sdk-unified-cli.md`。
- `AgentSession.id == Conversation.id`，不得建立第二套会话主表。
- 同一 Session 同时最多一个活动 Turn；不同 Session 可并行。
- Rust SDK 是唯一正式 Agent loop；Python core 只保留一个发布周期的 oracle/rollback。
- `AgentEvent v1` 是 Rust、binding、HTTP SSE 与 CLI JSONL 的共同协议；事件必须按 Turn 内 `sequence` 严格单调递增。
- Host 是用户消息、助手消息、Turn 与 Event 的唯一持久化写入者；UI/CLI 不得双写。
- 默认模型优先级固定为：Turn 显式模型 > `agent_preferences.default_model_id` > 用户模型列表第一个可用项；无可用模型时必须提示配置。
- SDK 不读取 Provider key、NoteMeld SQLite 路径或平台环境变量；敏感值只由 Host 传入 Driver。
- 不实现远程设备互调，不接入 Harbor，不交付完整移动应用。
- 每个任务必须先写失败测试，再写最小实现；只有当前任务相关测试通过后才进入下一任务。
- 每个任务独立提交；不得把工作区内已有用户改动混入提交。

---

## File Structure Map

### New SDK tree

```text
agent-sdk/
├── Cargo.toml
├── Cargo.lock
├── rust-toolchain.toml
├── crates/
│   ├── agent-events/src/lib.rs
│   ├── agent-model/src/lib.rs
│   ├── agent-tools/src/lib.rs
│   ├── agent-capabilities/src/lib.rs
│   ├── agent-core/src/lib.rs
│   ├── agent-session/src/lib.rs
│   ├── agent-storage/src/lib.rs
│   ├── agent-ffi/src/lib.rs
│   └── agent-cli/src/main.rs
├── bindings/
│   ├── python/notemeld_agent_sdk/__init__.py
│   ├── swift/Package.swift
│   ├── kotlin/build.gradle.kts
│   └── harmony/{oh-package.json5,src/main/ets/index.ets}
├── schemas/{turn-request.v1.json,agent-event.v1.json,errors.v1.json}
├── fixtures/conformance/*.jsonl
└── examples/{python-host,ios-harness,android-harness,harmony-harness}/
```

### New Host/API files

```text
backend/app/agent_host/
├── __init__.py
├── runtime.py
├── turn_manager.py
├── event_broker.py
├── approval.py
├── preferences.py
├── compat.py
└── drivers/{__init__.py,model.py,tools.py,storage.py}
backend/app/db/models/agent.py
backend/app/services/agent_store.py
backend/app/routers/agent.py
backend/tests/agent_host/
```

### Changed consumers and release files

```text
backend/app/__init__.py
backend/app/routers/chat.py
frontend/src/services/agent.ts
frontend/src/pages/HomePage/components/ChatComposer.tsx
frontend/src/pages/HomePage/messageRenderers.tsx
frontend/src/store/taskStore/index.ts
scripts/notemeld
scripts/notemeld.ps1
scripts/install.sh
scripts/install.ps1
desktop/src-tauri/src/lib.rs
packaging/backend/pyinstaller/backend.spec
.github/workflows/agent-sdk.yml
.github/workflows/release.yml
docs/system/{current-architecture.md,data-model.md,api-inventory.md,known-pitfalls.md}
```

---

### Task 1: Freeze Python oracle behavior as cross-language fixtures

**Files:**
- Create: `backend/tests/agent_core/export_oracle_fixtures.py`
- Create: `agent-sdk/fixtures/conformance/simple_answer.jsonl`
- Create: `agent-sdk/fixtures/conformance/parallel_tools.jsonl`
- Create: `agent-sdk/fixtures/conformance/abort.jsonl`
- Create: `agent-sdk/fixtures/conformance/steer.jsonl`
- Create: `agent-sdk/fixtures/conformance/max_turns.jsonl`
- Modify: `backend/tests/agent_core/test_events_sequence.py`
- Test: `backend/tests/agent_core/test_oracle_fixtures.py`

- [ ] Add a failing fixture-shape test asserting every row has `scenario`, `sequence`, `type`, and `payload`, and sequence starts at 1 with no gaps.

```python
def test_oracle_fixtures_are_gapless():
    for path in FIXTURE_DIR.glob("*.jsonl"):
        rows = [json.loads(line) for line in path.read_text().splitlines()]
        assert [row["sequence"] for row in rows] == list(range(1, len(rows) + 1))
```

- [ ] Run `pytest backend/tests/agent_core/test_oracle_fixtures.py -q` and record the expected missing-fixture failure.
- [ ] Implement a deterministic exporter using the existing fake model/tool drivers; normalize timestamps and generated IDs to fixed fixture values.
- [ ] Generate the five fixtures and add assertions for final status, tool result order, abort outcome, steer message placement, and max-turn error.
- [ ] Run `pytest backend/tests/agent_core -q` and require all existing oracle tests plus the new fixture test to pass.
- [ ] Commit only these files with `test(agent): freeze python core conformance oracle`.

### Task 2: Establish the Rust workspace and versioned wire schemas

**Files:**
- Create: `agent-sdk/Cargo.toml`
- Create: `agent-sdk/rust-toolchain.toml`
- Create: `agent-sdk/crates/agent-events/{Cargo.toml,src/lib.rs}`
- Create: `agent-sdk/schemas/{turn-request.v1.json,agent-event.v1.json,errors.v1.json}`
- Test: `agent-sdk/crates/agent-events/tests/schema_contract.rs`

- [ ] Add a failing Rust test that deserializes all oracle rows into `AgentEventEnvelope` and rejects `schema_version != "1"`.
- [ ] Run `cargo test --manifest-path agent-sdk/Cargo.toml -p agent-events` and record the unresolved-type failure.
- [ ] Define the stable public types below and use `#[serde(tag = "type", content = "payload")]` only for the event body, keeping the outer envelope fields stable.

```rust
pub struct AgentEventEnvelope {
    pub schema_version: String,
    pub event_id: EventId,
    pub sequence: u64,
    pub session_id: SessionId,
    pub turn_id: TurnId,
    pub timestamp: String,
    #[serde(flatten)]
    pub event: AgentEvent,
}

pub enum TurnStatus {
    Created, Running, WaitingApproval, Cancelling,
    Succeeded, Failed, Cancelled, Interrupted,
}
```

- [ ] Define all approved v1 event variants and error codes from the design spec, including unknown-field tolerance on reads and canonical snake_case serialization.
- [ ] Add JSON Schema golden tests for `TurnRequest`, `AgentEventEnvelope`, and `AgentError` with valid and invalid examples.
- [ ] Run `cargo fmt --manifest-path agent-sdk/Cargo.toml --check` and `cargo test --manifest-path agent-sdk/Cargo.toml -p agent-events`.
- [ ] Commit with `feat(agent-sdk): establish versioned event contracts`.

### Task 3: Define model and tool driver boundaries

**Files:**
- Create: `agent-sdk/crates/agent-model/{Cargo.toml,src/lib.rs}`
- Create: `agent-sdk/crates/agent-tools/{Cargo.toml,src/lib.rs}`
- Test: `agent-sdk/crates/agent-model/tests/stream_contract.rs`
- Test: `agent-sdk/crates/agent-tools/tests/scheduler_contract.rs`

- [ ] Add failing tests for ordered model chunks, usage propagation, malformed tool arguments, serial execution, stable parallel result order, cancellation propagation, and progress events.
- [ ] Run both crate test targets and record missing trait/type failures.
- [ ] Implement the host-injected interfaces without NoteMeld imports or environment reads.

```rust
#[async_trait]
pub trait ModelDriver: Send + Sync {
    async fn stream(&self, request: ModelRequest, sink: ModelChunkSink)
        -> Result<ModelCompletion, AgentError>;
}

#[async_trait]
pub trait ToolDriver: Send + Sync {
    async fn describe(&self, names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError>;
    async fn invoke(&self, call: ToolCall, context: ToolContext, sink: ToolProgressSink)
        -> Result<ToolResult, AgentError>;
}
```

- [ ] Implement deterministic scheduling: any `serial` call makes that model round serial; otherwise execute concurrently but emit final results in original call order.
- [ ] Run `cargo test --manifest-path agent-sdk/Cargo.toml -p agent-model -p agent-tools` and `cargo clippy --manifest-path agent-sdk/Cargo.toml --all-targets -- -D warnings`.
- [ ] Commit with `feat(agent-sdk): add model and tool driver contracts`.

### Task 4: Implement the canonical Rust Agent loop

**Files:**
- Create: `agent-sdk/crates/agent-core/{Cargo.toml,src/lib.rs,src/loop.rs,src/context.rs}`
- Test: `agent-sdk/crates/agent-core/tests/oracle_conformance.rs`
- Test: `agent-sdk/crates/agent-core/tests/failure_paths.rs`

- [ ] Add failing parameterized tests that replay the five Python oracle scenarios using Rust fake drivers and compare normalized semantic event sequences.
- [ ] Run `cargo test --manifest-path agent-sdk/Cargo.toml -p agent-core` and record missing loop failures.
- [ ] Implement `AgentRuntime::run_turn` with the exact boundary below.

```rust
pub async fn run_turn(
    &self,
    request: TurnRequest,
    history: Vec<AgentMessage>,
    cancel: CancellationToken,
    events: AgentEventSink,
) -> Result<TurnOutcome, AgentError>;
```

- [ ] Implement model stream accumulation, tool-call rounds, tool result messages, max-turn enforcement, usage aggregation, abort checks before/after external calls, and terminal event emission exactly once.
- [ ] Ensure observer/sink failures are isolated and converted to diagnostics without changing the Agent outcome.
- [ ] Run oracle and failure-path tests; then run `cargo test --manifest-path agent-sdk/Cargo.toml --workspace`.
- [ ] Commit with `feat(agent-sdk): implement canonical rust agent loop`.

### Task 5: Add session coordination, capabilities, and reference storage

**Files:**
- Create: `agent-sdk/crates/agent-session/{Cargo.toml,src/lib.rs}`
- Create: `agent-sdk/crates/agent-capabilities/{Cargo.toml,src/lib.rs}`
- Create: `agent-sdk/crates/agent-storage/{Cargo.toml,src/lib.rs}`
- Test: `agent-sdk/crates/agent-session/tests/state_machine.rs`
- Test: `agent-sdk/crates/agent-capabilities/tests/discovery.rs`
- Test: `agent-sdk/crates/agent-storage/tests/sqlite_store.rs`

- [ ] Add failing tests for legal/illegal Turn transitions, single-active-turn rejection, cross-session parallelism, idempotency-key replay, L0–L3 capability discovery, and SQLite event replay.
- [ ] Implement `TurnCoordinator` with an atomic per-session lease and transition table from the approved design.
- [ ] Implement `CapabilityRegistry` with `list`, `describe`, and `invoke`; keep Wiki/Skill/MCP implementations outside the SDK.
- [ ] Define `SessionStore`/`EventStore` traits and a reference SQLite store used only by harness/tests.
- [ ] Run the three crate test suites plus workspace clippy.
- [ ] Commit with `feat(agent-sdk): add session capability and storage layers`.

### Task 6: Build FFI, language bindings, and platform harnesses

**Files:**
- Create: `agent-sdk/crates/agent-ffi/{Cargo.toml,src/lib.rs,src/notemeld_agent.udl}`
- Create: `agent-sdk/bindings/python/notemeld_agent_sdk/{__init__.py,runtime.py}`
- Create: `agent-sdk/bindings/swift/Package.swift`
- Create: `agent-sdk/bindings/kotlin/{settings.gradle.kts,build.gradle.kts}`
- Create: `agent-sdk/bindings/harmony/{oh-package.json5,src/main/ets/index.ets}`
- Create: `agent-sdk/examples/python-host/test_smoke.py`
- Create minimal harness projects under `agent-sdk/examples/{ios-harness,android-harness,harmony-harness}`
- Test: `agent-sdk/crates/agent-ffi/tests/abi_contract.rs`

- [ ] Add a failing ABI test for `sdk_version`, `schema_version`, create/runtime lifecycle, driver request completion, event callback, cancel, steer, and double-free safety.
- [ ] Implement an opaque runtime handle and JSON event/request boundary; no callback may unwind across FFI.

```rust
pub extern "C" fn notemeld_agent_runtime_new(config_json: *const c_char) -> *mut AgentRuntimeHandle;
pub extern "C" fn notemeld_agent_submit_turn(handle: *mut AgentRuntimeHandle, request_json: *const c_char) -> u64;
pub extern "C" fn notemeld_agent_complete_driver_call(handle: *mut AgentRuntimeHandle, call_id: u64, result_json: *const c_char) -> i32;
pub extern "C" fn notemeld_agent_runtime_free(handle: *mut AgentRuntimeHandle);
```

- [ ] Generate Python/Swift/Kotlin wrappers from the shared API and implement an ArkTS N-API wrapper over the C ABI; bindings may translate types but not change event semantics.
- [ ] Make each harness run one fake-model Turn and assert the same terminal `turn.succeeded` event.
- [ ] Run native ABI tests and every harness available on the current host; document unavailable cross-platform harnesses as CI-only, not as passed locally.
- [ ] Commit with `feat(agent-sdk): add cross-platform ffi bindings and harnesses`.

### Task 7: Add SDK artifact CI matrix

**Files:**
- Create: `.github/workflows/agent-sdk.yml`
- Create: `agent-sdk/scripts/build-python.sh`
- Create: `agent-sdk/scripts/build-swift.sh`
- Create: `agent-sdk/scripts/build-kotlin.sh`
- Create: `agent-sdk/scripts/build-harmony.sh`
- Create: `agent-sdk/scripts/verify-artifact-manifest.py`
- Test: `backend/tests/test_agent_sdk_workflow_contracts.py`

- [ ] Add a failing static contract test requiring macOS x64/arm64, Windows x64, Linux x64/arm64, iOS device/simulator, Android ABI set, and OpenHarmony arm64 artifacts.
- [ ] Implement the workflow with a contract job first, platform build jobs second, and a final manifest verification job.
- [ ] Ensure every artifact includes SDK version, schema version, target triple, checksum, and binding version.
- [ ] Run `pytest backend/tests/test_agent_sdk_workflow_contracts.py -q` and validate workflow YAML parsing.
- [ ] Commit with `ci(agent-sdk): build and verify platform artifacts`.

### Task 8: Add Agent persistence without duplicating conversations

**Files:**
- Create: `backend/app/db/models/agent.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/app/db/database.py`
- Create: `backend/app/services/agent_store.py`
- Test: `backend/tests/agent_host/test_agent_schema.py`
- Test: `backend/tests/agent_host/test_agent_store.py`

- [ ] Add failing tests that initialize both a fresh database and a pre-feature database, then verify `agent_turns`, `agent_events`, and `agent_preferences` are created idempotently.
- [ ] Define `agent_turns.session_id` as a foreign key/reference to `conversations.id`; do not add an `agent_sessions` table.
- [ ] Add unique constraints for `(turn_id, sequence)`, `event_id`, and `(session_id, idempotency_key)` when the key is non-null.
- [ ] Implement atomic store methods: `create_turn`, `append_event`, `transition_turn`, `get_turn`, `list_events`, `get_model_preference`, `set_model_preference`.
- [ ] Verify a transaction failure cannot leave a terminal Turn without its terminal event.
- [ ] Run the two new suites and existing conversation/data-model tests.
- [ ] Commit with `feat(agent-host): persist turns events and model preferences`.

### Task 9: Load the Rust SDK and adapt NoteMeld model/tool/storage drivers

**Files:**
- Create: `backend/app/agent_host/runtime.py`
- Create: `backend/app/agent_host/drivers/{__init__.py,model.py,tools.py,storage.py}`
- Modify: `backend/requirements.txt` or the active backend dependency manifest discovered during execution
- Test: `backend/tests/agent_host/test_runtime_loader.py`
- Test: `backend/tests/agent_host/test_model_driver.py`
- Test: `backend/tests/agent_host/test_tool_driver.py`

- [ ] Add failing loader tests for source development, packaged sidecar, incompatible SDK/schema version, and explicit Python-oracle rollback mode.
- [ ] Implement `AgentSdkRuntime.load()` with startup fail-fast diagnostics that never include API keys or full provider payloads.
- [ ] Adapt `app.ai.create_models()` streaming into the shared model chunks and map provider/model errors to stable `AgentError` codes.
- [ ] Register existing builtin, memory, workspace, Wiki, Skill, and MCP tools through `ToolDriver`; retain existing approval/risk metadata.
- [ ] Implement history/context loading from `ConversationStore`, filtering UI-only message types before LLM input.
- [ ] Run focused driver tests and existing `backend/tests/agent`, `backend/tests/agent_core`, and `backend/tests/ai` suites.
- [ ] Commit with `feat(agent-host): bridge notemeld drivers to rust sdk`.

### Task 10: Implement Turn manager, event broker, approval, and model fallback

**Files:**
- Create: `backend/app/agent_host/{turn_manager.py,event_broker.py,approval.py,preferences.py}`
- Test: `backend/tests/agent_host/test_turn_manager.py`
- Test: `backend/tests/agent_host/test_event_broker.py`
- Test: `backend/tests/agent_host/test_approval.py`
- Test: `backend/tests/agent_host/test_preferences.py`

- [ ] Add failing tests for one active Turn per Session, reconnect replay with `after_sequence`, cancellation, steer, approval timeout, Host restart interruption, and model precedence/fallback.
- [ ] Implement `TurnManager.start_turn()` so it creates/persists the user message and Turn in one transaction before invoking Rust.
- [ ] Implement `EventBroker.subscribe(turn_id, after_sequence)` to replay persisted events then stream live events without duplicates or gaps.
- [ ] Persist assistant content incrementally at controlled checkpoints and finalize it atomically with the terminal Turn event.
- [ ] Implement approval resolution as an explicit Host command; default to deny on timeout or disconnected client when policy requires confirmation.
- [ ] Implement model selection priority exactly as stated in Global Constraints and return `MODEL_CONFIGURATION_REQUIRED` when no model is usable.
- [ ] Run all new Host component tests.
- [ ] Commit with `feat(agent-host): coordinate turns events approvals and models`.

### Task 11: Expose the versioned Agent v1 API

**Files:**
- Create: `backend/app/routers/agent.py`
- Modify: `backend/app/__init__.py`
- Create: `backend/tests/agent_host/test_agent_api.py`
- Modify: `backend/tests/test_core_security_contracts.py`

- [ ] Add failing API tests for all approved endpoints: sessions create/list/get; Turn create/get/events; cancel; steer; approval; model preference get/put.
- [ ] Require the existing local session token on every mutating Agent endpoint and reject non-loopback browser origins using current security helpers.
- [ ] Implement SSE frames with `id: <sequence>`, `event: <type>`, and JSON `data`; support `Last-Event-ID` plus explicit `after_sequence`.
- [ ] Return `409 SESSION_BUSY` for a second active Turn and the same Turn for a repeated idempotency key.
- [ ] Verify session responses hydrate existing `conversation_messages` and `note_documents`, not a new history representation.
- [ ] Run API/security tests and `python3 -m compileall backend/app`.
- [ ] Commit with `feat(api): expose unified agent v1 sessions and turns`.

### Task 12: Preserve `/chat/free/stream` as a compatibility adapter

**Files:**
- Create: `backend/app/agent_host/compat.py`
- Modify: `backend/app/routers/chat.py`
- Modify: `backend/app/agent/sse_bridge.py`
- Test: `backend/tests/agent/test_chat_compat.py`
- Test: `backend/tests/agent_host/test_chat_adapter_equivalence.py`

- [ ] Add a failing equivalence test that submits the same fake-model request through old and new endpoints and compares answer, source list, error class, and persisted message count.
- [ ] Route only free-chat Agent execution through `TurnManager`; keep unrelated note-generation chat behavior unchanged.
- [ ] Map v1 events to the legacy `delta/sources/done/error` SSE frames without executing the Python loop a second time.
- [ ] Add an explicit rollback flag that restores the Python oracle for one release without changing the UI contract.
- [ ] Run compatibility, SSE bridge, and Agent integration suites.
- [ ] Commit with `refactor(agent): route legacy chat through unified host`.

### Task 13: Introduce the frontend Agent client and event reducer

**Files:**
- Create: `frontend/src/services/agent.ts`
- Create: `frontend/src/services/agent.test.ts`
- Create: `frontend/src/store/taskStore/agentEventReducer.ts`
- Create: `frontend/src/store/taskStore/agentEventReducer.test.ts`

- [ ] Add failing tests for SSE parsing, sequence deduplication, reconnect cursor, message delta reduction, tool progress, approval, terminal errors, and unknown v1 event tolerance.
- [ ] Define TypeScript discriminated unions generated/copied exactly from `agent-event.v1.json`; include a schema-version guard.
- [ ] Implement `startAgentTurn`, `streamAgentEvents`, `cancelAgentTurn`, `steerAgentTurn`, `resolveAgentApproval`, and model preference calls.
- [ ] Implement a pure reducer from ordered Agent events to existing `ConversationMessage` UI state.
- [ ] Run the focused frontend tests and typecheck/build.
- [ ] Commit with `feat(frontend): add unified agent event client`.

### Task 14: Migrate ChatComposer and conversation rendering to Host-owned persistence

**Files:**
- Modify: `frontend/src/pages/HomePage/components/ChatComposer.tsx`
- Modify: `frontend/src/pages/HomePage/messageRenderers.tsx`
- Modify: `frontend/src/store/taskStore/index.ts`
- Modify: `frontend/src/store/taskStore/mergeConversationMessages.ts`
- Test: `frontend/src/pages/HomePage/components/ChatComposer.agent.test.tsx`
- Test: `frontend/src/store/taskStore/mergeConversationMessages.test.mjs`

- [ ] Add a failing UI test proving submit sends exactly one Turn command and does not call `appendConversationMessage` for the user or assistant message.
- [ ] Replace `streamFreeChat` only for chat mode with Agent v1; preserve note/research submission branches.
- [ ] Render approval prompts and tool progress from events, and reconnect active Turns using the last applied sequence.
- [ ] On terminal/reconnect completion, reload the canonical Conversation and merge local transient state without duplicating persisted messages.
- [ ] Add a UI path to set the default model and show a configuration prompt on `MODEL_CONFIGURATION_REQUIRED`.
- [ ] Run component/store tests, `cd frontend && pnpm test:contracts`, and `cd frontend && pnpm build`.
- [ ] Commit with `feat(frontend): use shared host for agent conversations`.

### Task 15: Implement `notemeld agent` REPL and one-shot CLI

**Files:**
- Create: `agent-sdk/crates/agent-cli/{Cargo.toml,src/main.rs,src/client.rs,src/repl.rs,src/render.rs}`
- Test: `agent-sdk/crates/agent-cli/tests/cli_contract.rs`
- Create: `backend/tests/agent_host/test_cli_e2e.py`

- [ ] Add failing CLI tests for `-p`, REPL, `--session`, `--new`, `--resume`, `/new`, `/resume`, `/sessions`, `/model`, text/json/jsonl output, Ctrl-C cancellation, and non-zero error exit codes.
- [ ] Implement runtime discovery from the Host descriptor and authenticate using the local token without printing it.
- [ ] Make `--format jsonl` output the unmodified `AgentEventEnvelope` one event per line; text/json are renderers over the same events.
- [ ] Make `/model` with no argument list available models and mark default/fallback; `/model <id>` persists via Agent preference API.
- [ ] Ensure a CLI-started Turn appears in the UI after reload and a UI-started session can be resumed by CLI.
- [ ] Run Cargo CLI contracts and Python cross-entry E2E.
- [ ] Commit with `feat(cli): add unified notemeld agent client`.

### Task 16: Unify local Host lifecycle for source and desktop startup

**Files:**
- Create: `backend/app/core/agent_runtime_descriptor.py`
- Modify: `backend/app/__init__.py`
- Modify: `scripts/notemeld`
- Modify: `scripts/notemeld.ps1`
- Modify: `desktop/src-tauri/src/lib.rs`
- Test: `backend/tests/agent_host/test_runtime_descriptor.py`
- Test: `backend/tests/test_core_runtime_contracts.py`
- Test: `desktop/src-tauri/src/lib.rs` unit tests

- [ ] Add failing tests for descriptor atomic write, PID/port/token/version validation, stale descriptor cleanup, existing healthy Host reuse, incompatible Host rejection, and desktop exit cleanup.
- [ ] Define the descriptor under the existing NoteMeld data root with mode `0600` where supported; write via temp file plus atomic replace.

```json
{
  "schema_version": "1",
  "pid": 1234,
  "base_url": "http://127.0.0.1:8483/api",
  "token": "redacted-in-logs",
  "sdk_version": "0.1.0",
  "started_at": "RFC3339"
}
```

- [ ] Make source `notemeld start` and Tauri startup both start/reuse the same Host semantics; do not spawn an interactive terminal window automatically.
- [ ] Preserve existing `start/stop/restart/logs/doctor/update/uninstall` behavior and add `agent` dispatch without changing established flags.
- [ ] Ensure desktop shutdown only terminates a Host it owns; an independently running compatible Host remains alive.
- [ ] Run backend runtime contracts and `cargo test --manifest-path desktop/src-tauri/Cargo.toml`.
- [ ] Commit with `feat(runtime): share agent host across ui and cli`.

### Task 17: Install and package the CLI and SDK binding

**Files:**
- Modify: `scripts/install.sh`
- Modify: `scripts/install.ps1`
- Modify: `packaging/backend/pyinstaller/backend.spec`
- Modify: `packaging/scripts/build-backend-macos.sh`
- Modify: `packaging/scripts/build-backend-windows.ps1`
- Modify: `desktop/src-tauri/tauri.conf.json`
- Test: `backend/tests/test_agent_packaging_contracts.py`

- [ ] Add a failing packaging contract requiring the CLI binary, Rust native library, Python binding, schemas, and licenses in source-install and desktop layouts.
- [ ] Install `notemeld-agent` beside the existing wrapper and route `notemeld agent ...` to it on macOS/Linux/Windows.
- [ ] Include the platform native library and binding in PyInstaller collection without hard-coded developer paths.
- [ ] Add packaged-runtime smoke tests for SDK load, descriptor creation, one fake Turn, and clean shutdown.
- [ ] Run packaging contract tests and the current-host backend build/smoke script.
- [ ] Commit with `build(agent): package sdk binding and cli`.

### Task 18: Integrate SDK assets into desktop release CI

**Files:**
- Modify: `.github/workflows/release.yml`
- Modify: `packaging/scripts/smoke-test-desktop.sh`
- Modify: `backend/tests/test_core_deploy_status_contracts.py`
- Test: `backend/tests/test_agent_release_workflow_contracts.py`

- [ ] Add a failing workflow contract that requires each desktop job to consume the matching SDK artifact and run CLI smoke tests before Tauri packaging.
- [ ] Add SDK build job dependencies without weakening the existing all-platform release gate.
- [ ] Keep existing DMG/MSI names and add versioned SDK archives as separate Release assets.
- [ ] Verify release remains skipped when any required desktop or SDK platform job fails.
- [ ] Run workflow/deploy contract tests and YAML parsing.
- [ ] Commit with `ci(release): ship matching agent sdk and cli assets`.

### Task 19: Run full acceptance and synchronize system documentation

**Files:**
- Modify: `docs/system/current-architecture.md`
- Modify: `docs/system/data-model.md`
- Modify: `docs/system/api-inventory.md`
- Modify: `docs/system/known-pitfalls.md`
- Modify: `docs/requirements/2026-08-14-universal-agent-sdk-unified-cli.md`
- Modify: `docs/requirements/index.md`
- Create: `docs/verification/2026-08-14-universal-agent-sdk-unified-cli.md`
- Modify: `scripts/run_core_regression.sh`

- [ ] Add the SDK workspace, Host lifecycle, Agent v1 API, new tables, model fallback, compatibility window, binding artifacts, and runtime descriptor to the system docs.
- [ ] Add regression commands for Rust workspace, Host API, frontend Agent contracts, CLI E2E, and packaging contracts to `scripts/run_core_regression.sh`.
- [ ] Run and capture exact results for:

```bash
cargo fmt --manifest-path agent-sdk/Cargo.toml --check
cargo clippy --manifest-path agent-sdk/Cargo.toml --workspace --all-targets -- -D warnings
cargo test --manifest-path agent-sdk/Cargo.toml --workspace
python3 -m compileall backend/app
pytest backend/tests
cd frontend && pnpm test:contracts
cd frontend && pnpm build
cargo test --manifest-path desktop/src-tauri/Cargo.toml
scripts/run_core_regression.sh
```

- [ ] Run current-host packaged smoke tests and record which mobile/Harmony artifacts were verified by CI rather than locally.
- [ ] Execute the 20 canonical acceptance criteria and record evidence, failures, and residual risks in the verification document.
- [ ] Change requirement status to `Verified` only if every mandatory criterion has evidence; otherwise leave it `In Progress` with explicit failed criteria.
- [ ] Commit with `docs(agent): record unified sdk acceptance evidence`.

---

## Stage Gates and Rollback Points

1. **Gate A — Contract:** Tasks 1–2 complete; schemas and oracle fixtures are frozen. Rollback: remove the isolated `agent-sdk` tree.
2. **Gate B — SDK semantics:** Tasks 3–5 complete; Rust conformance matches Python oracle. Rollback: no production caller uses Rust yet.
3. **Gate C — Platform API:** Tasks 6–7 complete; bindings/harnesses build. Rollback: keep artifacts unpublished.
4. **Gate D — Host shadow mode:** Tasks 8–10 complete; Host may execute Rust behind a feature flag while legacy endpoint remains Python. Rollback: select Python oracle flag; new tables are additive.
5. **Gate E — API compatibility:** Tasks 11–12 complete; old/new endpoint equivalence passes. Rollback: point compatibility adapter back to Python oracle.
6. **Gate F — Consumer cutover:** Tasks 13–16 complete; UI and CLI share Host/Conversation. Rollback: UI uses legacy endpoint; CLI disabled, data remains readable.
7. **Gate G — Distribution:** Tasks 17–19 complete; source, desktop, platform artifacts, docs, and acceptance evidence are complete. Rollback: withdraw new SDK/CLI assets without changing existing DMG/MSI data compatibility.

## Definition of Done

- All 20 canonical acceptance criteria have reproducible evidence.
- Rust and Python oracle semantic conformance passes for the frozen scenarios.
- UI and CLI can continue/new the same Conversation and never duplicate messages.
- Default model selection and fallback are shared and persisted.
- Source startup and installed desktop startup expose a discoverable local Agent Host and usable CLI.
- Required SDK artifacts and harness tests pass for macOS, Windows, Linux, iOS, Android, and OpenHarmony.
- Existing note, Wiki, MCP, migration, upload, desktop, and release regressions remain green.
- Harbor remains a separate, subsequent Change Spec.
