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

pub mod abi_render;

use std::{
    collections::{HashMap, HashSet, VecDeque},
    ffi::{c_char, c_void, CString},
    panic::{catch_unwind, AssertUnwindSafe},
    ptr,
    sync::{
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
        Arc, Condvar, Mutex, OnceLock, Weak,
    },
    time::{Duration, Instant, SystemTime, UNIX_EPOCH},
};

use agent_core::{
    AgentEventSink, AgentMessage, AgentRuntime, AgentRuntimeConfig, CancellationToken,
};
use agent_events::{
    AgentError, AgentErrorCode, AgentEvent, AgentEventEnvelope, EventId, TurnFailedPayload, TurnId,
    TurnRequest, SCHEMA_VERSION, SDK_VERSION,
};
use agent_model::{ModelChunk, ModelChunkSink, ModelCompletion, ModelDriver, ModelMessage, ModelRequest};
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
pub const FFI_TIMEOUT: i32 = -10;

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
pub type ContextReleaseCallback = unsafe extern "C-unwind" fn(*mut c_void);

#[derive(Clone, Copy, Default)]
struct Callbacks {
    event: Option<EventCallback>,
    event_context: usize,
    driver: Option<DriverCallback>,
    driver_context: usize,
    release: Option<ContextReleaseCallback>,
    release_context: usize,
}

#[derive(Default)]
struct CallbackGate {
    callbacks: Option<Callbacks>,
    closing: bool,
    active: usize,
}

struct CallbackLease {
    state: Arc<RuntimeState>,
    callbacks: Callbacks,
}

impl Drop for CallbackLease {
    fn drop(&mut self) {
        self.state.finish_callback();
    }
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

#[derive(Debug)]
enum DriverCallState {
    Pending(oneshot::Sender<Value>),
    Completed,
    Late,
}

#[derive(Default)]
struct DriverCalls {
    states: HashMap<u64, DriverCallState>,
    tombstones: VecDeque<u64>,
}

const MAX_CALL_TOMBSTONES: usize = 256;
const MAX_TURN_TOMBSTONES: usize = 256;

impl DriverCalls {
    fn settle(&mut self, call_id: u64, state: DriverCallState) {
        if let Some(index) = self.tombstones.iter().position(|id| *id == call_id) {
            self.tombstones.remove(index);
        }
        self.states.insert(call_id, state);
        self.tombstones.push_back(call_id);
        while self.tombstones.len() > MAX_CALL_TOMBSTONES {
            if let Some(evicted) = self.tombstones.pop_front() {
                if matches!(
                    self.states.get(&evicted),
                    Some(DriverCallState::Completed | DriverCallState::Late)
                ) {
                    self.states.remove(&evicted);
                }
            }
        }
    }

    fn mark_all_pending_late(&mut self) {
        let pending = self
            .states
            .iter()
            .filter_map(|(id, state)| matches!(state, DriverCallState::Pending(_)).then_some(*id))
            .collect::<Vec<_>>();
        for id in pending {
            self.mark_pending_late(id);
        }
    }

    fn mark_pending_late(&mut self, call_id: u64) -> bool {
        if matches!(self.states.get(&call_id), Some(DriverCallState::Pending(_))) {
            self.settle(call_id, DriverCallState::Late);
            true
        } else {
            false
        }
    }
}

#[derive(Debug, Clone)]
struct TurnControl {
    cancellation: CancellationToken,
    steer: Arc<Mutex<VecDeque<Value>>>,
}

#[derive(Default)]
struct Turns {
    active: HashMap<u64, TurnControl>,
    terminal: HashSet<u64>,
    terminal_order: VecDeque<u64>,
}

struct RuntimeState {
    id: usize,
    max_turns: usize,
    callbacks: Mutex<CallbackGate>,
    calls: Mutex<DriverCalls>,
    turns: Mutex<Turns>,
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
            callbacks: Mutex::new(CallbackGate::default()),
            calls: Mutex::new(DriverCalls::default()),
            turns: Mutex::new(Turns::default()),
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
            if turns.active.remove(&turn_token).is_some() {
                turns.terminal.insert(turn_token);
                turns.terminal_order.push_back(turn_token);
                while turns.terminal_order.len() > MAX_TURN_TOMBSTONES {
                    if let Some(evicted) = turns.terminal_order.pop_front() {
                        turns.terminal.remove(&evicted);
                    }
                }
            }
            self.turns_changed.notify_all();
        }
    }

    fn acquire_callback(self: &Arc<Self>) -> Result<CallbackLease, AgentError> {
        let mut gate = self
            .callbacks
            .lock()
            .map_err(|_| internal_error("callback registry unavailable"))?;
        if gate.closing {
            return Err(AgentError::new(AgentErrorCode::Cancelled, "runtime closed"));
        }
        let callbacks = gate
            .callbacks
            .ok_or_else(|| internal_error("callbacks are not configured"))?;
        gate.active = gate
            .active
            .checked_add(1)
            .ok_or_else(|| internal_error("callback lease space exhausted"))?;
        Ok(CallbackLease {
            state: Arc::clone(self),
            callbacks,
        })
    }

    fn finish_callback(&self) {
        let release = self.callbacks.lock().ok().and_then(|mut gate| {
            gate.active = gate.active.saturating_sub(1);
            if gate.closing && gate.active == 0 {
                gate.callbacks.take().and_then(|callbacks| {
                    callbacks
                        .release
                        .map(|release| (release, callbacks.release_context))
                })
            } else {
                None
            }
        });
        invoke_release(release);
    }

    fn close_callbacks(&self) {
        let release = self.callbacks.lock().ok().and_then(|mut gate| {
            gate.closing = true;
            if gate.active == 0 {
                gate.callbacks.take().and_then(|callbacks| {
                    callbacks
                        .release
                        .map(|release| (release, callbacks.release_context))
                })
            } else {
                None
            }
        });
        invoke_release(release);
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

fn next_u64(counter: &AtomicU64) -> Option<u64> {
    counter
        .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |current| {
            (current != 0).then(|| current.checked_add(1)).flatten()
        })
        .ok()
}

fn next_usize(counter: &AtomicUsize) -> Option<usize> {
    counter
        .fetch_update(Ordering::Relaxed, Ordering::Relaxed, |current| {
            (current != 0).then(|| current.checked_add(1)).flatten()
        })
        .ok()
}

fn invoke_release(release: Option<(ContextReleaseCallback, usize)>) {
    if let Some((callback, context)) = release {
        let _ = catch_unwind(AssertUnwindSafe(|| unsafe {
            callback(context as *mut c_void)
        }));
    }
}

/// Reads at most `max` bytes and therefore never performs an unbounded C
/// string scan. As with every C ABI, the caller remains responsible for
/// passing a readable buffer through the first NUL byte.
unsafe fn read_bounded_c_string(pointer: *const c_char, max: usize) -> Result<String, AgentError> {
    if pointer.is_null() {
        return Err(invalid_input("input pointer must not be null"));
    }
    let mut bytes = Vec::new();
    for index in 0..max {
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

fn guard_worker<T>(work: impl FnOnce() -> Result<T, AgentError>) -> Result<T, AgentError> {
    catch_unwind(AssertUnwindSafe(work)).unwrap_or_else(|_| Err(panic_error()))
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
    turn_token: u64,
    turn_id: &str,
    kind: &str,
    payload: Value,
    cancellation: CancellationToken,
) -> Result<Value, AgentError> {
    if cancellation.is_cancelled() || state.stopping.load(Ordering::Acquire) {
        return Err(AgentError::new(AgentErrorCode::Cancelled, "turn cancelled"));
    }
    // Process-global call ids prevent a completion from runtime A from ever
    // matching a numerically-colliding pending call in runtime B.
    let call_id = next_u64(&NEXT_DRIVER_CALL_ID)
        .ok_or_else(|| internal_error("driver call id space exhausted"))?;
    let (sender, receiver) = oneshot::channel();
    state
        .calls
        .lock()
        .map_err(|_| internal_error("driver registry unavailable"))?
        .states
        .insert(call_id, DriverCallState::Pending(sender));

    let lease = match state.acquire_callback() {
        Ok(lease) => lease,
        Err(error) => {
            if let Ok(mut calls) = state.calls.lock() {
                calls.mark_pending_late(call_id);
            }
            return Err(error);
        }
    };
    let Some(callback) = lease.callbacks.driver else {
        if let Ok(mut calls) = state.calls.lock() {
            calls.mark_pending_late(call_id);
        }
        return Err(AgentError::new(
            AgentErrorCode::AgentRuntimeUnavailable,
            "model/tool driver callback is not configured",
        ));
    };
    let request = json!({
        "schema_version": SCHEMA_VERSION,
        "sdk_version": SDK_VERSION,
        "call_id": call_id,
        "turn_token": turn_token,
        "turn_id": turn_id,
        "kind": kind,
        "payload": payload,
    });
    if let Err(error) = invoke_json_callback(callback, lease.callbacks.driver_context, &request) {
        if let Ok(mut calls) = state.calls.lock() {
            calls.mark_pending_late(call_id);
        }
        return Err(error);
    }
    drop(lease);

    let mut receiver = receiver;
    tokio::select! {
        biased;
        _ = cancellation.cancelled() => {
            let was_pending = state.calls.lock().ok().map(|mut calls| {
                calls.mark_pending_late(call_id)
            }).unwrap_or(false);
            if was_pending {
                Err(AgentError::new(AgentErrorCode::Cancelled, "turn cancelled"))
            } else {
                (&mut receiver).await.map_err(|_| internal_error("driver completion channel closed"))
            }
        }
        response = &mut receiver => response.map_err(|_| internal_error("driver completion channel closed")),
    }
}

struct FfiModelDriver {
    state: Weak<RuntimeState>,
    steer: Arc<Mutex<VecDeque<Value>>>,
    turn_token: u64,
    turn_id: String,
}

#[async_trait]
impl ModelDriver for FfiModelDriver {
    async fn stream(
        &self,
        mut request: ModelRequest,
        sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        let state = self
            .state
            .upgrade()
            .ok_or_else(|| AgentError::new(AgentErrorCode::Cancelled, "runtime closed"))?;
        if let Ok(mut pending) = self.steer.lock() {
            while let Some(content) = pending.pop_front() {
                request.messages.push(ModelMessage { role: "user".to_owned(), content });
            }
        }
        let messages = serde_json::to_value(&request.messages)
            .map_err(|_| internal_error("model request encoding failed"))?;
        let response = dispatch_driver_call(
            &state,
            self.turn_token,
            &self.turn_id,
            "model.stream",
            json!({"messages": messages}),
            request.cancellation,
        )
        .await?;
        let result = validate_driver_response(&response)?;
        if let Some(chunks) = result.get("chunks").and_then(Value::as_array) {
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
            result
                .get("completion")
                .cloned()
                .ok_or_else(|| invalid_input("model completion is missing"))?,
        )
        .map_err(|_| invalid_input("model completion schema is invalid"))
    }
}

struct FfiToolDriver {
    state: Weak<RuntimeState>,
    turn_token: u64,
    turn_id: String,
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
            self.turn_token,
            &self.turn_id,
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
        let result = validate_driver_response(&response)?;
        Ok(ToolResult::new(
            call.id(),
            result.get("output").cloned().unwrap_or(Value::Null),
        ))
    }
}

fn validate_driver_response(response: &Value) -> Result<&Value, AgentError> {
    if response.get("schema_version").and_then(Value::as_str) != Some(SCHEMA_VERSION) {
        return Err(AgentError::new(
            AgentErrorCode::AgentSchemaMismatch,
            "driver completion schema version mismatch",
        ));
    }
    let object = response
        .as_object()
        .ok_or_else(|| invalid_input("driver completion must be an object"))?;
    match response.get("ok") {
        Some(Value::Bool(true)) => {
            if object.contains_key("error") || !object.contains_key("result") {
                return Err(invalid_input(
                    "driver completion must contain exactly one result or error",
                ));
            }
            response
                .get("result")
                .filter(|result| result.is_object())
                .ok_or_else(|| invalid_input("driver completion result must be an object"))
        }
        Some(Value::Bool(false)) => {
            if object.contains_key("result") || !object.contains_key("error") {
                return Err(invalid_input(
                    "driver completion must contain exactly one result or error",
                ));
            }
            match parse_driver_error(response) {
                Err(error) => Err(error),
                Ok(()) => Err(internal_error(
                    "driver error parser returned without an error",
                )),
            }
        }
        _ => Err(invalid_input("driver completion ok must be a boolean")),
    }
}

fn parse_driver_error(response: &Value) -> Result<(), AgentError> {
    if response.get("schema_version").and_then(Value::as_str) != Some(SCHEMA_VERSION) {
        return Err(AgentError::new(
            AgentErrorCode::AgentSchemaMismatch,
            "driver completion schema version mismatch",
        ));
    }
    match response.get("ok") {
        Some(Value::Bool(false)) => {}
        _ => return Err(invalid_input("driver completion ok must be false")),
    }
    let error = response
        .get("error")
        .cloned()
        .ok_or_else(|| invalid_input("driver completion error is missing"))?;
    let error = serde_json::from_value::<AgentError>(error)
        .map_err(|_| invalid_input("driver error schema is invalid"))?;
    Err(sanitize_driver_error(error))
}

fn sanitize_driver_error(error: AgentError) -> AgentError {
    let message = match error.code {
        AgentErrorCode::ModelUnavailable => "model unavailable",
        AgentErrorCode::ToolFailed => "tool failed",
        AgentErrorCode::Cancelled => "turn cancelled",
        AgentErrorCode::ModelNotConfigured => "model not configured",
        AgentErrorCode::ContextBudgetExceeded => "context budget exceeded",
        AgentErrorCode::ApprovalRequired => "approval required",
        AgentErrorCode::ApprovalExpired => "approval expired",
        AgentErrorCode::AgentSchemaMismatch => "driver schema mismatch",
        AgentErrorCode::InvalidInput => "driver returned invalid input",
        _ => "driver operation failed",
    };
    // Driver messages, details and flattened fields cross a host trust boundary.
    // Preserve only the stable code; raw provider payloads may contain secrets.
    AgentError::new(error.code, message)
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
    let lease = state.acquire_callback()?;
    if let Some(callback) = lease.callbacks.event {
        invoke_json_callback(callback, lease.callbacks.event_context, &value)?;
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
        Ok(turns) => match turns.active.get(&turn_token) {
            Some(turn) => turn.cancellation.clone(),
            None => return,
        },
        Err(_) => return,
    };
    let weak = Arc::downgrade(&state);
    let steer = state.turns.lock().ok().and_then(|turns| turns.active.get(&turn_token).map(|turn| Arc::clone(&turn.steer))).unwrap_or_else(|| Arc::new(Mutex::new(VecDeque::new())));
    let turn_id = request.request_id.0.clone();
    let model: Arc<dyn ModelDriver> = Arc::new(FfiModelDriver { state: weak.clone(), steer, turn_token, turn_id: turn_id.clone() });
    let tools: Arc<dyn ToolDriver> = Arc::new(FfiToolDriver { state: weak, turn_token, turn_id });
    let runtime = AgentRuntime::new(
        model,
        tools,
        AgentRuntimeConfig {
            max_turns: state.max_turns,
        },
    );
    let sequence = Arc::new(AtomicU64::new(1));
    let terminal_emitted = Arc::new(AtomicBool::new(false));
    let event_state = Arc::clone(&state);
    let event_request = request.clone();
    let event_terminal = Arc::clone(&terminal_emitted);
    let event_sequence = Arc::clone(&sequence);
    let sink = AgentEventSink::new(move |event| {
        let state = Arc::clone(&event_state);
        let request = event_request.clone();
        if matches!(
            event,
            AgentEvent::TurnSucceeded(_)
                | AgentEvent::TurnFailed(_)
                | AgentEvent::TurnCancelled(_)
                | AgentEvent::TurnInterrupted(_)
        ) {
            event_terminal.store(true, Ordering::Release);
        }
        let sequence = event_sequence.fetch_add(1, Ordering::Relaxed);
        async move { emit_envelope(&state, &request, sequence, event) }
    });
    let run_request = request.clone();
    // The C ABI runtime has no product database of its own.  Hosts that own
    // session history may supply a bounded `history` array in the request's
    // flattened fields; decode it into the canonical SDK messages instead of
    // silently discarding it.
    let history = request
        .extra
        .get("history")
        .cloned()
        .and_then(|value| serde_json::from_value::<Vec<AgentMessage>>(value).ok())
        .unwrap_or_default();
    let result = guard_worker(|| {
        async_runtime().and_then(|executor| {
            executor.block_on(async {
                runtime
                    .run_turn(run_request, history, cancellation, sink)
                    .await
            })
        })
    });
    finish_turn(
        &state,
        turn_token,
        &request,
        &sequence,
        &terminal_emitted,
        result.map(|_| ()),
    );
}

fn finish_turn(
    state: &Arc<RuntimeState>,
    turn_token: u64,
    request: &TurnRequest,
    sequence: &AtomicU64,
    terminal_emitted: &AtomicBool,
    result: Result<(), AgentError>,
) {
    if let Err(error) = result {
        let safe = if error.code == AgentErrorCode::SdkInternalError {
            panic_error()
        } else {
            error
        };
        if !terminal_emitted.swap(true, Ordering::AcqRel) {
            let _ = emit_envelope(
                state,
                request,
                sequence.fetch_add(1, Ordering::Relaxed),
                AgentEvent::TurnFailed(TurnFailedPayload {
                    error: safe.clone(),
                    ..TurnFailedPayload::default()
                }),
            );
        }
        state.set_error(safe);
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
        let id = next_usize(&NEXT_RUNTIME_ID)?;
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
    release_callback: Option<ContextReleaseCallback>,
    release_context: *mut c_void,
) -> i32 {
    catch_unwind(AssertUnwindSafe(|| {
        let state = runtime_for(handle)?;
        let mut gate = state.callbacks.lock().map_err(|_| FFI_INTERNAL_ERROR)?;
        if gate.closing || gate.callbacks.is_some() || release_callback.is_none() {
            return Err(FFI_INVALID_INPUT);
        }
        gate.callbacks = Some(Callbacks {
            event: event_callback,
            event_context: event_context as usize,
            driver: driver_callback,
            driver_context: driver_context as usize,
            release: release_callback,
            release_context: release_context as usize,
        });
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
        let turn_token = next_u64(&state.next_turn_token).or_else(|| {
            state.set_error(internal_error("turn token space exhausted"));
            None
        })?;
        let cancellation = CancellationToken::new();
        state
            .turns
            .lock()
            .ok()?
            .active
            .insert(turn_token, TurnControl { cancellation, steer: Arc::new(Mutex::new(VecDeque::new())) });
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
        let sender = {
            let mut calls = state.calls.lock().map_err(|_| FFI_INTERNAL_ERROR)?;
            match calls.states.remove(&call_id) {
                Some(DriverCallState::Pending(sender)) => {
                    calls.settle(call_id, DriverCallState::Completed);
                    sender
                }
                Some(DriverCallState::Completed) => {
                    calls.states.insert(call_id, DriverCallState::Completed);
                    return Err(FFI_DUPLICATE_COMPLETION);
                }
                Some(DriverCallState::Late) => {
                    calls.states.insert(call_id, DriverCallState::Late);
                    return Err(FFI_LATE_COMPLETION);
                }
                None => return Err(FFI_UNKNOWN_CALL),
            }
        };
        if sender.send(value).is_err() {
            if let Ok(mut calls) = state.calls.lock() {
                calls.settle(call_id, DriverCallState::Late);
            }
            return Err(FFI_LATE_COMPLETION);
        }
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
        if turns.terminal.contains(&turn_token) {
            return Ok(FFI_OK);
        }
        let Some(turn) = turns.active.get(&turn_token) else {
            return Err(FFI_TURN_NOT_FOUND);
        };
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
        if turns.terminal.contains(&turn_token) {
            return Err(FFI_TURN_TERMINAL);
        }
        let Some(turn) = turns.active.get(&turn_token) else {
            return Err(FFI_TURN_NOT_FOUND);
        };
        let wire = unsafe { read_bounded_c_string(steer_json, MAX_STEER_BYTES) }
            .map_err(|_| FFI_INVALID_INPUT)?;
        let value: Value = serde_json::from_str(&wire).map_err(|_| FFI_INVALID_INPUT)?;
        let text = value.get("text").or_else(|| value.get("input")).and_then(Value::as_str).map(str::trim).filter(|text| !text.is_empty()).ok_or(FFI_INVALID_INPUT)?;
        if text.len() > MAX_STEER_BYTES / 4 {
            return Err(FFI_INVALID_INPUT);
        }
        let mut pending = turn.steer.lock().map_err(|_| FFI_INTERNAL_ERROR)?;
        if pending.len() >= 16 {
            return Err(FFI_INVALID_INPUT);
        }
        pending.push_back(Value::String(text.to_owned()));
        Ok(FFI_OK)
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
            if turns.terminal.contains(&turn_token) {
                return Ok(FFI_OK);
            }
            if !turns.active.contains_key(&turn_token) {
                return Err(FFI_TURN_NOT_FOUND);
            }
            let now = Instant::now();
            if now >= deadline {
                return Err(FFI_TIMEOUT);
            }
            let remaining = deadline.saturating_duration_since(now);
            let (next, timeout) = state
                .turns_changed
                .wait_timeout(turns, remaining)
                .map_err(|_| FFI_INTERNAL_ERROR)?;
            turns = next;
            if timeout.timed_out() {
                return Err(FFI_TIMEOUT);
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
            state.close_callbacks();
            if let Ok(turns) = state.turns.lock() {
                for turn in turns.active.values() {
                    turn.cancellation.cancel();
                }
            }
            if let Ok(mut calls) = state.calls.lock() {
                calls.mark_all_pending_late();
            }
            state.turns_changed.notify_all();
        }
    }));
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn monotonic_counters_stop_before_wraparound() {
        let u64_counter = AtomicU64::new(u64::MAX - 1);
        assert_eq!(next_u64(&u64_counter), Some(u64::MAX - 1));
        assert_eq!(next_u64(&u64_counter), None);
        assert_eq!(next_u64(&u64_counter), None);

        let usize_counter = AtomicUsize::new(usize::MAX - 1);
        assert_eq!(next_usize(&usize_counter), Some(usize::MAX - 1));
        assert_eq!(next_usize(&usize_counter), None);
        assert_eq!(next_usize(&usize_counter), None);
    }

    #[test]
    fn driver_and_turn_tombstones_are_bounded() {
        let mut calls = DriverCalls::default();
        for id in 1..=(MAX_CALL_TOMBSTONES as u64 + 2) {
            calls.settle(id, DriverCallState::Late);
        }
        assert_eq!(calls.states.len(), MAX_CALL_TOMBSTONES);
        assert!(!calls.states.contains_key(&1));

        let state = RuntimeState::new(1, 1);
        for id in 1..=(MAX_TURN_TOMBSTONES as u64 + 2) {
            state.turns.lock().unwrap().active.insert(
                id,
                TurnControl { cancellation: CancellationToken::new(), steer: Arc::new(Mutex::new(VecDeque::new())) },
            );
            state.mark_terminal(id);
        }
        let turns = state.turns.lock().unwrap();
        assert_eq!(turns.terminal.len(), MAX_TURN_TOMBSTONES);
        assert!(!turns.terminal.contains(&1));
    }

    #[test]
    fn worker_panic_is_mapped_to_a_stable_internal_error() {
        let result = guard_worker::<()>(|| panic!("secret worker panic"));
        let error = result.unwrap_err();
        assert_eq!(error.code, AgentErrorCode::SdkInternalError);
        assert_eq!(error.message, "agent FFI operation failed");
        assert!(!error.message.contains("secret"));
    }

    #[test]
    fn worker_panic_result_finishes_with_one_safe_failed_terminal() {
        unsafe extern "C-unwind" fn capture(context: *mut c_void, wire: *const c_char) -> i32 {
            let events = &*(context as *const Mutex<Vec<Value>>);
            let wire = std::ffi::CStr::from_ptr(wire).to_str().unwrap();
            events
                .lock()
                .unwrap()
                .push(serde_json::from_str(wire).unwrap());
            FFI_OK
        }
        let events = Box::new(Mutex::new(Vec::<Value>::new()));
        let context = (&*events as *const Mutex<Vec<Value>>) as usize;
        let state = Arc::new(RuntimeState::new(1, 1));
        state.callbacks.lock().unwrap().callbacks = Some(Callbacks {
            event: Some(capture),
            event_context: context,
            ..Callbacks::default()
        });
        state.turns.lock().unwrap().active.insert(
            1,
            TurnControl { cancellation: CancellationToken::new(), steer: Arc::new(Mutex::new(VecDeque::new())) },
        );
        let request: TurnRequest = serde_json::from_value(json!({
            "schema_version":"1", "request_id":"ffffffff-ffff-4fff-8fff-ffffffffffff",
            "session_id":"panic-test", "input":{"text":"x","attachments":[],"context_refs":[]},
            "model_override":null, "approval_mode":"interactive"
        }))
        .unwrap();
        finish_turn(
            &state,
            1,
            &request,
            &AtomicU64::new(1),
            &AtomicBool::new(false),
            Err(panic_error()),
        );
        let events = events.lock().unwrap();
        assert_eq!(events.len(), 1);
        assert_eq!(events[0]["type"], "turn.failed");
        assert_eq!(
            events[0]["payload"]["error"]["message"],
            "agent FFI operation failed"
        );
    }

    #[test]
    fn driver_error_parser_requires_an_explicit_false_boolean() {
        for malformed in [
            json!({"schema_version":"1"}),
            json!({"schema_version":"1","ok":null}),
            json!({"schema_version":"1","ok":"false"}),
            json!({"schema_version":"1","ok":{}}),
            json!({"schema_version":"1","ok":true,"error":{"code":"model_unavailable","message":"unsafe"}}),
            json!({"schema_version":"1","ok":false,"error":{"code":"not_a_code","message":"unsafe"}}),
        ] {
            assert_eq!(
                parse_driver_error(&malformed).unwrap_err().code,
                AgentErrorCode::InvalidInput
            );
        }
        let error = parse_driver_error(&json!({
            "schema_version":"1","ok":false,
            "error":{"code":"tool_failed","message":"provider secret","details":{"token":"secret"}}
        }))
        .unwrap_err();
        assert_eq!(error.code, AgentErrorCode::ToolFailed);
        assert_eq!(error.message, "tool failed");
        assert!(error.details.is_empty());
        assert!(error.extra.is_empty());
    }
}
