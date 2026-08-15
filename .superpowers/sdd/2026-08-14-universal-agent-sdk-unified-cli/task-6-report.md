# Task 6 Report

## AGENTS.md preflight

1. 影响模块：`agent-sdk` workspace、new `agent-ffi`、四种语言薄 binding 与四个平台 smoke harness；不触碰产品 Host/DB/API/UI/CLI/desktop。
2. 既有类似能力：Tasks 1–5 已提供唯一 AgentEvent、canonical loop、driver traits、session/storage primitives；仓库无既有 FFI/binding/mobile harness。
3. 产品规则：不冲突；FFI 只提供平台入口，事件语义继续来自 Rust，且不读 NoteMeld 数据或密钥。
4. 数据模型：不改 SQLite/文件事实源，故无字段语义冲突。
5. Known pitfalls：重点防止 secret/payload 日志泄漏、callback 持锁死锁、取消竞态和迁移期复制第二套 loop。
6. 数据/线上影响：本 Task 无产品数据写入、无远程服务调用；只增加构建源文件与本机测试产物。
7. 最小改动：稳定 C ABI + ctypes/Swift/Kotlin/ArkTS 类型翻译层 + fake-driver harness，不引入产品 Host 或 UniFFI generator。
8. 回归测试：ABI 生命周期/错误/竞态、真实 Python native load、binding 漂移静态契约、可用平台 build，以及 Rust workspace/oracle。

## TDD evidence

- RED: `cargo test ... -p agent-ffi --test abi_contract` failed before implementation with `can't find library agent_ffi ... src/lib.rs`; the ABI test existed first and named the missing lifecycle/driver/event/control symbols.
- GREEN: native ABI contract `6 passed`; real Python binding smoke `1 passed`; current-host Swift harness printed `swift harness: turn.succeeded`.

## ABI v1 table

| Surface | Contract |
|---|---|
| versions | `sdk_version=0.1.0`, `schema_version=1` |
| handle | opaque monotonic nonzero registry token; never dereferenced or reused; null/stale/double-free safe |
| runtime | `runtime_new`, `runtime_set_callbacks`, non-blocking idempotent `runtime_free` |
| Turn | `submit_turn` drives Task 4 `AgentRuntime::run_turn`; `wait_turn` is a bounded harness/embedding helper |
| Driver | process-global `call_id`; JSON `model.stream`/`tool.invoke`; `complete_driver_call` distinguishes unknown, duplicate and late completion |
| Events | Task 4 `AgentEvent` is wrapped with `agent-events::AgentEventEnvelope`; callback receives that exact v1 JSON |
| cancel | idempotent `CancellationToken` propagation; canonical loop emits exactly one `turn.cancelled` terminal |
| steer | Task 4 fixed loop has no mid-turn injection point, so v1 returns typed `FFI_UNSUPPORTED` and never pretends input was applied |
| errors | numeric ABI result plus owned `last_error_json`; free with `string_free`; safe messages only |

All extern entries are panic-contained. Rust-host callbacks use the ABI-permitted `C-unwind` function type so the contract test can prove unwind containment without an aborting `extern C` pseudo-test. C/Swift/Kotlin/ArkTS hosts use ordinary non-unwinding callbacks. Inputs are null checked, scanned only through a bounded maximum, then validated as UTF-8/JSON/v1 schema. Arbitrary unreadable foreign addresses remain the standard C caller memory-validity precondition; no portable C ABI can probe them safely.

## Ownership and threading

- Callback strings are borrowed only for callback duration. `last_error_json` is owned by the caller and has one matching free function.
- The global runtime registry and pending-call maps are released before invoking callbacks. Driver completion may safely re-enter the ABI synchronously.
- Runtime free first removes the registry token, clears future callbacks, cancels all Turn tokens and drops pending senders. It never waits indefinitely. An already-entered host callback may finish; each wrapper retains callback context accordingly.
- Callback errors/panics become bounded observer diagnostics and cannot change the canonical Turn outcome or create a second terminal event.
- Cancel/complete/free and cross-runtime tests use channels/condition variables, not sleeps or yield loops.

## Shared declarations and bindings

- Canonical callable list/ownership/threading metadata: `agent-sdk/bindings/abi-v1.json`.
- C consumers: `agent-sdk/include/notemeld_agent.h`.
- Generated semantic C-ABI declaration: `notemeld_agent.udl`. It explicitly states that it is **not** UniFFI input; this task does not claim generated UniFFI output.
- Python: ctypes wrapper validates versions, requires an explicit path or `NOTEMELD_AGENT_SDK_LIBRARY`, retains callbacks, exposes context-manager/idempotent close and never hard-codes a developer path.
- Swift: SwiftPM package directly imports the shared C header; current-host fake-model executable used the same native dylib and terminal envelope.
- Android: Android library/AAR source with Kotlin wrapper and JNI C-ABI adapter. It does not copy AgentEvent enums.
- OpenHarmony: ArkTS package and N-API/TSFN C-ABI adapter. TSFN is necessary because Rust callbacks may originate on worker threads.

## Platform probe and harness evidence

| Platform | Evidence | Status |
|---|---|---|
| Rust native macOS x86_64 | ABI 6/6; dylib exported all manifest symbols | local GREEN |
| Python | real ctypes load + fake model + terminal assertion | local GREEN (pytest runtime available; target wrapper remains Python 3.11-compatible) |
| Swift/macOS | Swift 6.3.2 package build and executable native fake Turn | local GREEN |
| iOS device/simulator | same Swift package/harness source; no simulator/device target run | CI-only |
| Android | Gradle/Kotlin/JNI project present; Gradle/Android SDK unavailable on host | CI-only, not claimed passed |
| OpenHarmony | ArkTS/N-API TSFN project present; `hvigor`/`ohpm` unavailable | CI-only, not claimed passed |

The Android and OpenHarmony target builds belong to Task 7's artifact matrix; this Task deliberately does not turn missing local toolchains into a skip-pass.

## Dependency, license and lock review

- No new third-party package/version/checksum entered `Cargo.lock`; its only change is the local `agent-ffi 0.1.0` package entry.
- Direct dependencies are existing workspace crates plus already-locked async-trait/chrono/serde/serde_json/tokio/uuid. MSRV remains workspace `1.85.0`, edition 2021.
- `cargo-deny` is unavailable locally. Since no third-party dependency was introduced, license inventory is unchanged; formal archive license evidence remains Task 7.
- Cargo used `/tmp/notemeld-task2-cargo-home`, `/tmp/notemeld-agent-sdk-target`, official sparse metadata, offline and locked. No global Cargo config or workspace target was modified.

## Verification

- `cargo test --workspace`: 74 passed.
- `cargo clippy --workspace --all-targets -- -D warnings`: passed.
- `cargo fmt --all -- --check`: passed.
- `git diff --check -- agent-sdk`: passed.
- Native ABI suite: 6 passed.
- Python native smoke: 1 passed.
- Swift package + native harness: passed, terminal `turn.succeeded`.
- Python oracle: 27 passed.
- Python binding/example syntax compilation: passed.

## Security/self-review and residual concerns

- No stdout/stderr logging exists in the Rust FFI/bindings; raw prompt, result, error and secret payloads are not logged or embedded in events beyond the canonical core's bounded/redacted summaries.
- The SDK reads no NoteMeld database, environment secret or product path. The Python library path environment variable contains a binary path only.
- Process-global call ids prevent cross-runtime completion collision. Monotonic runtime tokens prevent allocator ABA.
- The OpenHarmony and Android callback bridge contexts are retained through potential free/callback overlap; target CI must run sanitizer/instrumented lifecycle tests before publishing artifacts.
- Full iOS/Android/OpenHarmony archive generation, XCFramework/AAR/HAR packaging and `artifact-manifest.json` are Task 7, not falsely claimed by Task 6.

## Fix Round 1 (2026-08-15)

### Review RED → GREEN

- **Driver error RED:** a valid `model_unavailable` completion whose untrusted message/details contained `sk-live-secret` produced `turn.failed.payload.error.code=invalid_input`. The focused ABI test failed with `left invalid_input / right model_unavailable`.
- **Driver error GREEN:** `serde_json::from_value::<AgentError>` now parses the shared error type explicitly. The trust-boundary sanitizer retains only the stable code and a code-specific safe message, dropping driver details/extra recursively. The ABI test proves the original secret is absent from both the canonical event envelope and `last_error_json`.
- **Lifecycle RED represented by contract:** the prior ABI had no release acknowledgement and copied raw contexts outside the callback lock. The delayed-callback test now enters a host callback, calls non-blocking `runtime_free`, proves no early release, unblocks the callback, then observes exactly one release acknowledgement without sleep/yield.
- **Concurrency GREEN:** a `Barrier` starts two completions for one pending call; exactly one returns `FFI_OK` and one `FFI_DUPLICATE_COMPLETION`. A zero-duration active wait returns the new independent `FFI_TIMEOUT`.
- **Counter boundary RED/GREEN:** the first checked-counter implementation exposed eager `then_some(current + 1)` overflow in the boundary unit test. It was replaced with `checked_add`; exhaustion remains permanent and never wraps into an ABA-capable token.

### ABI ownership and state machines

`abi-v1.json` is now the complete source for callback/function return types, parameter types, C calling convention, ownership, threading and error semantics. `abi_render.rs` deterministically renders the entire C header and semantic `.udl`; the contract test compares both complete files byte-for-byte. The `.udl` is intentionally a semantic C ABI declaration, not a claim that callback-capable UniFFI code was generated.

Callback ownership is `Open(callbacks, active=n) → Closing(active=n) → Released`. Acquiring a callback and incrementing `active` is one mutex operation. The host callback runs without that mutex and without the global runtime registry. `runtime_free` removes the runtime, closes the gate and returns without waiting. The final callback lease invokes the host release function exactly once, outside all SDK locks. Reentrant free/cancel/completion therefore remains safe. Python retains a callback box in a process registry through release acknowledgement; Swift uses `passRetained`/`takeRetainedValue`; JNI deletes its `GlobalRef` only at release acknowledgement; Harmony releases both TSFNs normally and deletes the bridge after both finalizers.

Driver calls use one mutex and one map: `Pending(sender) → Completed | Late`. Completion takes the sender and installs its tombstone atomically. Cancel/free atomically replace every remaining pending sender with `Late`. Process-global checked IDs prevent cross-runtime collision. Completed/late tombstones are FIFO-bounded at **256**; after eviction a completion is documented as `UNKNOWN_CALL`. Active turns are removed on terminal and terminal observation tombstones are likewise FIFO-bounded at **256**. Unit tests insert more than both capacities and prove eviction. Python's event buffer is bounded at 1024 and always makes room for a terminal event.

All externally supplied driver messages/details/extra fields are discarded before an error reaches event or last-error storage. The worker future is guarded by `catch_unwind`; a panic maps to the stable safe `sdk_internal_error`, and the worker emits one `turn.failed` if the canonical loop had not already emitted a terminal. The panic mapping helper has a boundary test. `string_free(NULL)` is safe; the generated header/manifest now explicitly state that a non-null pointer must be one outstanding allocation returned by this ABI, and foreign/double-free is undefined rather than falsely claimed safe.

### Driver and platform harness coverage

- Native ABI now runs both a model-error path and the real canonical `model.stream → tool.invoke → model.stream → turn.succeeded` path. Steer remains uniformly typed `FFI_UNSUPPORTED`; no binding pretends it applied.
- Python: real local dylib load and terminal smoke passed; the callback context stays in a global retained registry until native release. The default Python 3.14 lacked pytest, so the smoke function was executed directly with Python 3.11 against the real dylib. Task 1 oracle was separately run with pyenv Python 3.10.13 and passed 27/27.
- Swift/macOS: package build and real dylib harness passed, printing `swift harness: turn.succeeded`.
- Android: JNI now uses `GetStringChars`/`NewString` and explicit standard UTF-8 conversion, rejecting invalid surrogate sequences and embedded NUL. A host C++ test passes emoji round-trip plus invalid-surrogate/NUL cases. The harness is a real `androidTest` instrumentation test using `CountDownLatch`/`AtomicReference`, native load, submit, fake completion, terminal assertion and close. Gradle/Android SDK are unavailable locally, so `connectedAndroidTest` is CI-only; assemble is not claimed as execution.
- OpenHarmony: no synchronous native wait is exported to ArkTS. Terminal delivery is a Promise resolved by the terminal TSFN event; async close cancels/awaits an active terminal before native free. Invalid/throwing JS driver callbacks complete the pending call with a safe error. Release acknowledgement normally drains TSFNs and deletes the bridge after both finalizers. `hvigor`/DevEco are unavailable locally, so this remains static-contract/CI-only.

### Fix-round verification

- `cargo test --workspace`: GREEN, including agent-ffi **4 unit + 10 ABI** tests.
- `cargo clippy --workspace --all-targets -- -D warnings`: GREEN.
- `cargo fmt --all -- --check`: GREEN.
- ABI renderer whole-file equality: GREEN.
- `nm`: all 12 manifest functions exported by the native dylib.
- Python real native smoke: GREEN; Task 1 Python oracle: **27 passed**.
- Swift package and native harness: GREEN.
- Host C++ UTF codec test with `-Wall -Wextra -Werror`: GREEN.
- Android and OpenHarmony target execution: CI-only due missing local toolchains; static lifecycle/Promise/instrumentation contracts are checked by the Rust ABI suite.

No new Rust dependency or lockfile entry was added. MSRV and license inventory are unchanged. Remaining release work is target CI execution/package generation in Task 7; this fix round does not claim unavailable mobile target builds.
