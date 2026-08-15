//! Stable C ABI for the NoteMeld Agent SDK.
//!
//! Handles are monotonically allocated registry tokens. They are never
//! dereferenced, so a stale or double-freed handle cannot alias a later
//! runtime even if the native allocator reuses an address.

// These exported functions intentionally remain safe `extern "C"` functions:
// the C header is the primary contract, every raw pointer is null-checked and
// bounded before decoding, and every entry catches panics. Memory readability
// is still the caller's C-ABI precondition and cannot be proven by Rust.
#![allow(clippy::not_unsafe_ptr_arg_deref)]

use std::{
    collections::HashMap,
    ffi::{c_char, c_void, CString},
    panic::{catch_unwind, AssertUnwindSafe},
    ptr,
    sync::{
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
        Arc, Condvar, Mutex, OnceLock, RwLock, Weak,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use agent_core::{
    AgentEventSink, AgentMessage, AgentRuntime, AgentRuntimeConfig, CancellationToken,
};
use agent_events::{
    AgentError, AgentErrorCode, AgentEvent, AgentEventEnvelope, EventId, TurnId, TurnRequest,
    SCHEMA_VERSION, SDK_VERSION,
};
use agent_model::{ModelChunk, ModelChunkSink, ModelCompletion, ModelDriver, ModelRequest};
use agent_tools::{
    ToolCall, ToolContext, ToolDescriptor, ToolDriver, ToolProgressSink, ToolResult,
};
use async_trait::async_trait;
use chrono::{DateTime, SecondsFormat, Utc};
use serde::Deserialize;
use serde_json::{json, Value};
use tokio::sync::oneshot;
use uuid::Uuid;

pub const FFI_OK: i32 = 0;
pub const FFI_INVALID_HANDLE: i32 = -1;
pub const FFI_INVALID_INPUT: i32 = -2;
pub const FFI_UNKNOWN_CALL: i32 = -3;
pub const FFI_DUPLICATE_COMPLETION: i32 = -4;
pub const FFI_LATE_COMPLETION: i32 = -5;
pub const FFI_UNSUPPORTED: i32 = -6;
pub const FFI_TURN_NOT_FOUND: i32 = -7;
pub const FFI_TURN_TERMINAL: i32 = -8;
pub const FFI_INTERNAL_ERROR: i32 = -9;

const MAX_CONFIG_BYTES: usize = 64 * 1024;
const MAX_TURN_REQUEST_BYTES: usize = 1024 * 1024;
const MAX_DRIVER_COMPLETION_BYTES: usize = 8 * 1024 * 1024;
const MAX_STEER_BYTES: usize = 1024 * 1024;

static SDK_VERSION_C: &[u8] = b"0.1.0\0";
static SCHEMA_VERSION_C: &[u8] = b"1\0";

#[repr(C)]
pub struct AgentRuntimeHandle {
    _private: [u8; 0],
}

pub type EventCallback = unsafe extern "C-unwind" fn(*mut c_void, *const c_char) -> i32;
pub type DriverCallback = unsafe extern "C-unwind" fn(*mut c_void, *const c_char) -> i32;

#[derive(Clone, Copy, Default)]
struct Callbacks {
    event: Option<EventCallback>,
    event_context: usize,
    driver: Option<DriverCallback>,
    driver_context: usize,
}

#[derive(Debug, Deserialize)]
struct RuntimeConfigDto {
    schema_version: String,
    #[serde(default = "default_max_turns")]
    max_turns: usize,
}

const fn default_max_turns() -> usize {
    16
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SettledCall {
    Completed,
    Late,
}

#[derive(Debug, Clone)]
struct TurnControl {
    cancellation: CancellationToken,
    terminal: bool,
}

struct RuntimeState {
    id: usize,
    max_turns: usize,
    callbacks: RwLock<Callbacks>,
    pending: Mutex<HashMap<u64, oneshot::Sender<Value>>>,
    settled: Mutex<HashMap<u64, SettledCall>>,
    turns: Mutex<HashMap<u64, TurnControl>>,
    turns_changed: Condvar,
    next_turn_token: AtomicU64,
    stopping: AtomicBool,
    last_error: Mutex<Option<AgentError>>,
}

impl RuntimeState {
    fn new(id: usize, max_turns: usize) -> Self {
        Self {
            id,
            max_turns,
            callbacks: RwLock::new(Callbacks::default()),
            pending: Mutex::new(HashMap::new()),
            settled: Mutex::new(HashMap::new()),
            turns: Mutex::new(HashMap::new()),
            turns_changed: Condvar::new(),
            next_turn_token: AtomicU64::new(1),
            stopping: AtomicBool::new(false),
            last_error: Mutex::new(None),
        }
    }

    fn set_error(&self, error: AgentError) {
        if let Ok(mut slot) = self.last_error.lock() {
            *slot = Some(error);
        }
    }

    fn mark_terminal(&self, turn_token: u64) {
        if let Ok(mut turns) = self.turns.lock() {
            if let Some(turn) = turns.get_mut(&turn_token) {
                turn.terminal = true;
            }
            self.turns_changed.notify_all();
        }
    }
}

static REGISTRY: OnceLock<Mutex<HashMap<usize, Arc<RuntimeState>>>> = OnceLock::new();
static NEXT_RUNTIME_ID: AtomicUsize = AtomicUsize::new(1);
static NEXT_DRIVER_CALL_ID: AtomicU64 = AtomicU64::new(1);
static ASYNC_RUNTIME: OnceLock<Result<tokio::runtime::Runtime, ()>> = OnceLock::new();

fn registry() -> &'static Mutex<HashMap<usize, Arc<RuntimeState>>> {
    REGISTRY.get_or_init(|| Mutex::new(HashMap::new()))
}

fn async_runtime() -> Result<&'static tokio::runtime::Runtime, AgentError> {
    ASYNC_RUNTIME
        .get_or_init(|| {
            tokio::runtime::Builder::new_multi_thread()
                .enable_all()
                .thread_name("notemeld-agent-ffi")
                .build()
                .map_err(|_| ())
        })
        .as_ref()
        .map_err(|_| internal_error("agent async runtime unavailable"))
}

fn handle_id(handle: *mut AgentRuntimeHandle) -> Option<usize> {
    let id = handle as usize;
    (id != 0).then_some(id)
}

fn runtime_for(handle: *mut AgentRuntimeHandle) -> Result<Arc<RuntimeState>, i32> {
    let id = handle_id(handle).ok_or(FFI_INVALID_HANDLE)?;
    registry()
        .lock()
        .map_err(|_| FFI_INTERNAL_ERROR)?
        .get(&id)
        .cloned()
        .ok_or(FFI_INVALID_HANDLE)
}

fn next_nonzero(counter: &AtomicU64) -> Option<u64> {
    let value = counter.fetch_add(1, Ordering::Relaxed);
    (value != 0 && value != u64::MAX).then_some(value)
}

/// Reads at most `max` bytes and therefore never performs an unbounded C
/// string scan. As with every C ABI, the caller remains responsible for
/// passing a readable buffer through the first NUL byte.
unsafe fn read_bounded_c_string(pointer: *const c_char, max: usize) -> Result<String, AgentError> {
    if pointer.is_null() {
        return Err(invalid_input("input pointer must not be null"));
    }
    let mut bytes = Vec::new();
    for index in 0..=max {
        let byte = pointer.cast::<u8>().add(index).read();
        if byte == 0 {
            return std::str::from_utf8(&bytes)
                .map(str::to_owned)
                .map_err(|_| invalid_input("input must be valid UTF-8"));
        }
        bytes.push(byte);
    }
    Err(invalid_input("input exceeds the FFI byte limit"))
}

fn invalid_input(message: &str) -> AgentError {
    AgentError::new(AgentErrorCode::InvalidInput, message)
}

fn internal_error(message: &str) -> AgentError {
    AgentError::new(AgentErrorCode::SdkInternalError, message)
}

fn panic_error() -> AgentError {
    internal_error("agent FFI operation failed")
}

fn invoke_json_callback(
    callback: unsafe extern "C-unwind" fn(*mut c_void, *const c_char) -> i32,
    context: usize,
    value: &Value,
) -> Result<(), AgentError> {
    let wire = serde_json::to_string(value).map_err(|_| internal_error("JSON encoding failed"))?;
    let wire = CString::new(wire).map_err(|_| internal_error("JSON encoding failed"))?;
    match catch_unwind(AssertUnwindSafe(|| unsafe {
        callback(context as *mut c_void, wire.as_ptr())
    })) {
        Ok(FFI_OK) => Ok(()),
        Ok(_) => Err(internal_error("host callback rejected the request")),
        Err(_) => Err(panic_error()),
    }
}

async fn dispatch_driver_call(
    state: &Arc<RuntimeState>,
    kind: &str,
    payload: Value,
    cancellation: CancellationToken,
) -> Result<Value, AgentError> {
    if cancellation.is_cancelled() || state.stopping.load(Ordering::Acquire) {
        return Err(AgentError::new(AgentErrorCode::Cancelled, "turn cancelled"));
    }
    // Process-global call ids prevent a completion from runtime A from ever
    // matching a numerically-colliding pending call in runtime B.
    let call_id = next_nonzero(&NEXT_DRIVER_CALL_ID)
        .ok_or_else(|| internal_error("driver call id space exhausted"))?;
    let (sender, receiver) = oneshot::channel();
    state
        .pending
        .lock()
        .map_err(|_| internal_error("driver registry unavailable"))?
        .insert(call_id, sender);

    let callbacks = *state
        .callbacks
        .read()
        .map_err(|_| internal_error("callback registry unavailable"))?;
    let Some(callback) = callbacks.driver else {
        state
            .pending
            .lock()
            .ok()
            .and_then(|mut calls| calls.remove(&call_id));
        return Err(AgentError::new(
            AgentErrorCode::AgentRuntimeUnavailable,
            "model/tool driver callback is not configured",
        ));
    };
    let request = json!({
        "schema_version": SCHEMA_VERSION,
        "sdk_version": SDK_VERSION,
        "call_id": call_id,
        "kind": kind,
        "payload": payload,
    });
    if let Err(error) = invoke_json_callback(callback, callbacks.driver_context, &request) {
        state
            .pending
            .lock()
            .ok()
            .and_then(|mut calls| calls.remove(&call_id));
        state
            .settled
            .lock()
            .ok()
            .map(|mut settled| settled.insert(call_id, SettledCall::Late));
        return Err(error);
    }

    tokio::select! {
        biased;
        _ = cancellation.cancelled() => {
            state.pending.lock().ok().and_then(|mut calls| calls.remove(&call_id));
            state.settled.lock().ok().map(|mut settled| settled.insert(call_id, SettledCall::Late));
            Err(AgentError::new(AgentErrorCode::Cancelled, "turn cancelled"))
        }
        response = receiver => response.map_err(|_| internal_error("driver completion channel closed")),
    }
}

struct FfiModelDriver {
    state: Weak<RuntimeState>,
}

#[async_trait]
impl ModelDriver for FfiModelDriver {
    async fn stream(
        &self,
        request: ModelRequest,
        sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        let state = self
            .state
            .upgrade()
            .ok_or_else(|| AgentError::new(AgentErrorCode::Cancelled, "runtime closed"))?;
        let messages = serde_json::to_value(&request.messages)
            .map_err(|_| internal_error("model request encoding failed"))?;
        let response = dispatch_driver_call(
            &state,
            "model.stream",
            json!({"messages": messages}),
            request.cancellation,
        )
        .await?;
        parse_driver_error(&response)?;
        if let Some(chunks) = response.get("chunks").and_then(Value::as_array) {
            for chunk in chunks {
                if chunk.get("type").and_then(Value::as_str) == Some("content_delta") {
                    let delta = chunk
                        .get("delta")
                        .and_then(Value::as_str)
                        .ok_or_else(|| invalid_input("model chunk delta must be a string"))?;
                    sink.emit(ModelChunk::ContentDelta {
                        delta: delta.to_owned(),
                    })
                    .await?;
                }
            }
        }
        serde_json::from_value(
            response
                .get("completion")
                .cloned()
                .ok_or_else(|| invalid_input("model completion is missing"))?,
        )
        .map_err(|_| invalid_input("model completion schema is invalid"))
    }
}

struct FfiToolDriver {
    state: Weak<RuntimeState>,
}

#[async_trait]
impl ToolDriver for FfiToolDriver {
    async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(Vec::new())
    }

    async fn invoke(
        &self,
        call: ToolCall,
        context: ToolContext,
        _sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        let state = self
            .state
            .upgrade()
            .ok_or_else(|| AgentError::new(AgentErrorCode::Cancelled, "runtime closed"))?;
        let response = dispatch_driver_call(
            &state,
            "tool.invoke",
            json!({
                "call_id": call.id(),
                "tool_name": call.name(),
                "arguments": call.arguments(),
                "session_id": context.session_id.0,
                "turn_id": context.turn_id.0,
            }),
            context.cancellation,
        )
        .await?;
        parse_driver_error(&response)?;
        Ok(ToolResult::new(
            call.id(),
            response.get("output").cloned().unwrap_or(Value::Null),
        ))
    }
}

fn parse_driver_error(response: &Value) -> Result<(), AgentError> {
    if response.get("schema_version").and_then(Value::as_str) != Some(SCHEMA_VERSION) {
        return Err(AgentError::new(
            AgentErrorCode::AgentSchemaMismatch,
            "driver completion schema version mismatch",
        ));
    }
    if response.get("ok").and_then(Value::as_bool) == Some(true) {
        return Ok(());
    }
    let error = response
        .get("error")
        .cloned()
        .ok_or_else(|| invalid_input("driver completion error is missing"))?;
    serde_json::from_value(error).map_err(|_| invalid_input("driver error schema is invalid"))
}

fn emit_envelope(
    state: &Arc<RuntimeState>,
    request: &TurnRequest,
    sequence: u64,
    event: AgentEvent,
) -> Result<(), AgentError> {
    let envelope = AgentEventEnvelope {
        schema_version: SCHEMA_VERSION.to_owned(),
        event_id: EventId::from(Uuid::new_v4().to_string()),
        sequence,
        session_id: request.session_id.clone(),
        turn_id: TurnId::from(request.request_id.0.clone()),
        timestamp: utc_now()?,
        event,
    };
    let value = serde_json::to_value(envelope)
        .map_err(|_| internal_error("event envelope encoding failed"))?;
    let callbacks = *state
        .callbacks
        .read()
        .map_err(|_| internal_error("callback registry unavailable"))?;
    if let Some(callback) = callbacks.event {
        invoke_json_callback(callback, callbacks.event_context, &value)?;
    }
    Ok(())
}

fn utc_now() -> Result<String, AgentError> {
    let duration = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| internal_error("system clock is before the Unix epoch"))?;
    let seconds = i64::try_from(duration.as_secs())
        .map_err(|_| internal_error("system clock is outside the supported range"))?;
    let datetime = DateTime::<Utc>::from_timestamp(seconds, duration.subsec_nanos())
        .ok_or_else(|| internal_error("system clock is outside the supported range"))?;
    Ok(datetime.to_rfc3339_opts(SecondsFormat::Millis, true))
}

fn run_submitted_turn(state: Arc<RuntimeState>, turn_token: u64, request: TurnRequest) {
    let cancellation = match state.turns.lock() {
        Ok(turns) => match turns.get(&turn_token) {
            Some(turn) => turn.cancellation.clone(),
            None => return,
        },
        Err(_) => return,
    };
    let weak = Arc::downgrade(&state);
    let model: Arc<dyn ModelDriver> = Arc::new(FfiModelDriver {
        state: weak.clone(),
    });
    let tools: Arc<dyn ToolDriver> = Arc::new(FfiToolDriver { state: weak });
    let runtime = AgentRuntime::new(
        model,
        tools,
        AgentRuntimeConfig {
            max_turns: state.max_turns,
        },
    );
    let sequence = Arc::new(AtomicU64::new(1));
    let event_state = Arc::clone(&state);
    let event_request = request.clone();
    let sink = AgentEventSink::new(move |event| {
        let state = Arc::clone(&event_state);
        let request = event_request.clone();
        let sequence = sequence.fetch_add(1, Ordering::Relaxed);
        async move { emit_envelope(&state, &request, sequence, event) }
    });
    let result = async_runtime().and_then(|executor| {
        executor.block_on(async {
            runtime
                .run_turn(request, Vec::<AgentMessage>::new(), cancellation, sink)
                .await
        })
    });
    if let Err(error) = result {
        state.set_error(error);
    }
    state.mark_terminal(turn_token);
}

#[no_mangle]
pub extern "C" fn notemeld_agent_sdk_version() -> *const c_char {
    SDK_VERSION_C.as_ptr().cast()
}

#[no_mangle]
pub extern "C" fn notemeld_agent_schema_version() -> *const c_char {
    SCHEMA_VERSION_C.as_ptr().cast()
}

#[no_mangle]
pub extern "C" fn notemeld_agent_runtime_new(
    config_json: *const c_char,
) -> *mut AgentRuntimeHandle {
    catch_unwind(AssertUnwindSafe(|| {
        let config = unsafe { read_bounded_c_string(config_json, MAX_CONFIG_BYTES) }.ok()?;
        let config: RuntimeConfigDto = serde_json::from_str(&config).ok()?;
        if config.schema_version != SCHEMA_VERSION || config.max_turns == 0 {
            return None;
        }
        async_runtime().ok()?;
        let id = NEXT_RUNTIME_ID.fetch_add(1, Ordering::Relaxed);
        if id == 0 || id == usize::MAX {
            return None;
        }
        let state = Arc::new(RuntimeState::new(id, config.max_turns));
        registry().lock().ok()?.insert(id, state);
        Some(id as *mut AgentRuntimeHandle)
    }))
    .ok()
    .flatten()
    .unwrap_or(ptr::null_mut())
}

#[no_mangle]
pub extern "C" fn notemeld_agent_runtime_set_callbacks(
    handle: *mut AgentRuntimeHandle,
    event_callback: Option<EventCallback>,
    event_context: *mut c_void,
    driver_callback: Option<DriverCallback>,
    driver_context: *mut c_void,
) -> i32 {
    catch_unwind(AssertUnwindSafe(|| {
        let state = runtime_for(handle)?;
        let mut callbacks = state.callbacks.write().map_err(|_| FFI_INTERNAL_ERROR)?;
        *callbacks = Callbacks {
            event: event_callback,
            event_context: event_context as usize,
            driver: driver_callback,
            driver_context: driver_context as usize,
        };
        Ok::<_, i32>(FFI_OK)
    }))
    .unwrap_or(Err(FFI_INTERNAL_ERROR))
    .unwrap_or_else(|code| code)
}

#[no_mangle]
pub extern "C" fn notemeld_agent_submit_turn(
    handle: *mut AgentRuntimeHandle,
    request_json: *const c_char,
) -> u64 {
    catch_unwind(AssertUnwindSafe(|| {
        let state = runtime_for(handle).ok()?;
        if state.stopping.load(Ordering::Acquire) {
            return None;
        }
        let wire = unsafe { read_bounded_c_string(request_json, MAX_TURN_REQUEST_BYTES) }
            .map_err(|error| state.set_error(error))
            .ok()?;
        let request: TurnRequest = serde_json::from_str(&wire)
            .map_err(|_| state.set_error(invalid_input("turn request JSON is invalid")))
            .ok()?;
        let turn_token = next_nonzero(&state.next_turn_token)?;
        let cancellation = CancellationToken::new();
        state.turns.lock().ok()?.insert(
            turn_token,
            TurnControl {
                cancellation,
                terminal: false,
            },
        );
        let executor = async_runtime().ok()?;
        executor.spawn_blocking({
            let state = Arc::clone(&state);
            move || run_submitted_turn(state, turn_token, request)
        });
        Some(turn_token)
    }))
    .ok()
    .flatten()
    .unwrap_or(0)
}

#[no_mangle]
pub extern "C" fn notemeld_agent_complete_driver_call(
    handle: *mut AgentRuntimeHandle,
    call_id: u64,
    result_json: *const c_char,
) -> i32 {
    catch_unwind(AssertUnwindSafe(|| {
        let state = runtime_for(handle)?;
        if call_id == 0 {
            return Err(FFI_INVALID_INPUT);
        }
        let wire = unsafe { read_bounded_c_string(result_json, MAX_DRIVER_COMPLETION_BYTES) }
            .map_err(|error| {
                state.set_error(error);
                FFI_INVALID_INPUT
            })?;
        let value: Value = serde_json::from_str(&wire).map_err(|_| FFI_INVALID_INPUT)?;
        if !value.is_object() {
            return Err(FFI_INVALID_INPUT);
        }
        let sender = state
            .pending
            .lock()
            .map_err(|_| FFI_INTERNAL_ERROR)?
            .remove(&call_id);
        let Some(sender) = sender else {
            return match state
                .settled
                .lock()
                .map_err(|_| FFI_INTERNAL_ERROR)?
                .get(&call_id)
            {
                Some(SettledCall::Completed) => Err(FFI_DUPLICATE_COMPLETION),
                Some(SettledCall::Late) => Err(FFI_LATE_COMPLETION),
                None => Err(FFI_UNKNOWN_CALL),
            };
        };
        state
            .settled
            .lock()
            .map_err(|_| FFI_INTERNAL_ERROR)?
            .insert(call_id, SettledCall::Completed);
        sender.send(value).map_err(|_| FFI_LATE_COMPLETION)?;
        Ok(FFI_OK)
    }))
    .unwrap_or(Err(FFI_INTERNAL_ERROR))
    .unwrap_or_else(|code| code)
}

#[no_mangle]
pub extern "C" fn notemeld_agent_cancel_turn(
    handle: *mut AgentRuntimeHandle,
    turn_token: u64,
) -> i32 {
    catch_unwind(AssertUnwindSafe(|| {
        let state = runtime_for(handle)?;
        let turns = state.turns.lock().map_err(|_| FFI_INTERNAL_ERROR)?;
        let Some(turn) = turns.get(&turn_token) else {
            return Err(FFI_TURN_NOT_FOUND);
        };
        if turn.terminal {
            return Ok(FFI_OK);
        }
        turn.cancellation.cancel();
        Ok(FFI_OK)
    }))
    .unwrap_or(Err(FFI_INTERNAL_ERROR))
    .unwrap_or_else(|code| code)
}

#[no_mangle]
pub extern "C" fn notemeld_agent_steer_turn(
    handle: *mut AgentRuntimeHandle,
    turn_token: u64,
    steer_json: *const c_char,
) -> i32 {
    catch_unwind(AssertUnwindSafe(|| {
        let state = runtime_for(handle)?;
        let turns = state.turns.lock().map_err(|_| FFI_INTERNAL_ERROR)?;
        let Some(_turn) = turns.get(&turn_token) else {
            return Err(FFI_TURN_NOT_FOUND);
        };
        let wire = unsafe { read_bounded_c_string(steer_json, MAX_STEER_BYTES) }
            .map_err(|_| FFI_INVALID_INPUT)?;
        let value: Value = serde_json::from_str(&wire).map_err(|_| FFI_INVALID_INPUT)?;
        if !value.is_object() {
            return Err(FFI_INVALID_INPUT);
        }
        // Task 4's fixed canonical loop has no mid-turn input port. Expose an
        // explicit, typed control result instead of pretending steer applied.
        Err(FFI_UNSUPPORTED)
    }))
    .unwrap_or(Err(FFI_INTERNAL_ERROR))
    .unwrap_or_else(|code| code)
}

#[no_mangle]
pub extern "C" fn notemeld_agent_wait_turn(
    handle: *mut AgentRuntimeHandle,
    turn_token: u64,
    timeout_ms: u64,
) -> i32 {
    catch_unwind(AssertUnwindSafe(|| {
        let state = runtime_for(handle)?;
        let deadline = Instant::now()
            .checked_add(Duration::from_millis(timeout_ms))
            .ok_or(FFI_INVALID_INPUT)?;
        let mut turns = state.turns.lock().map_err(|_| FFI_INTERNAL_ERROR)?;
        loop {
            match turns.get(&turn_token) {
                Some(turn) if turn.terminal => return Ok(FFI_OK),
                Some(_) => {}
                None => return Err(FFI_TURN_NOT_FOUND),
            }
            let now = Instant::now();
            if now >= deadline {
                return Err(FFI_INTERNAL_ERROR);
            }
            let remaining = deadline.saturating_duration_since(now);
            let (next, timeout) = state
                .turns_changed
                .wait_timeout(turns, remaining)
                .map_err(|_| FFI_INTERNAL_ERROR)?;
            turns = next;
            if timeout.timed_out() {
                return Err(FFI_INTERNAL_ERROR);
            }
        }
    }))
    .unwrap_or(Err(FFI_INTERNAL_ERROR))
    .unwrap_or_else(|code| code)
}

#[no_mangle]
pub extern "C" fn notemeld_agent_last_error_json(handle: *mut AgentRuntimeHandle) -> *mut c_char {
    catch_unwind(AssertUnwindSafe(|| {
        let state = runtime_for(handle).ok()?;
        let error = state.last_error.lock().ok()?.clone()?;
        let wire = serde_json::to_string(&error).ok()?;
        CString::new(wire).ok().map(CString::into_raw)
    }))
    .ok()
    .flatten()
    .unwrap_or(ptr::null_mut())
}

#[no_mangle]
pub extern "C" fn notemeld_agent_string_free(pointer: *mut c_char) {
    let _ = catch_unwind(AssertUnwindSafe(|| {
        if !pointer.is_null() {
            unsafe { drop(CString::from_raw(pointer)) };
        }
    }));
}

#[no_mangle]
pub extern "C" fn notemeld_agent_runtime_free(handle: *mut AgentRuntimeHandle) {
    let _ = catch_unwind(AssertUnwindSafe(|| {
        let Some(id) = handle_id(handle) else {
            return;
        };
        let state = registry()
            .lock()
            .ok()
            .and_then(|mut runtimes| runtimes.remove(&id));
        if let Some(state) = state {
            debug_assert_eq!(state.id, id);
            state.stopping.store(true, Ordering::Release);
            if let Ok(mut callbacks) = state.callbacks.write() {
                *callbacks = Callbacks::default();
            }
            if let Ok(turns) = state.turns.lock() {
                for turn in turns.values() {
                    turn.cancellation.cancel();
                }
            }
            if let Ok(mut pending) = state.pending.lock() {
                pending.clear();
            }
            state.turns_changed.notify_all();
        }
    }));
}
