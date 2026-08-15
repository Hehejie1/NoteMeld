use std::{
    ffi::{c_char, c_void, CStr, CString},
    sync::{
        atomic::{AtomicU64, AtomicUsize, Ordering},
        mpsc, Arc, Barrier, Mutex, OnceLock,
    },
};

use notemeld_agent::*;
use serde_json::{json, Value};

static EVENTS: OnceLock<Mutex<Vec<Value>>> = OnceLock::new();
static HANDLE: OnceLock<Mutex<usize>> = OnceLock::new();
static TEST_LOCK: OnceLock<Mutex<()>> = OnceLock::new();
static LAST_CALL: AtomicU64 = AtomicU64::new(0);
static DRIVER_MODE: AtomicUsize = AtomicUsize::new(0);
static TOOL_STAGE: AtomicUsize = AtomicUsize::new(0);
type BlockedCallSender = mpsc::Sender<(usize, u64)>;
static BLOCKED_CALL: OnceLock<Mutex<Option<BlockedCallSender>>> = OnceLock::new();

unsafe extern "C-unwind" fn event_callback(
    _context: *mut c_void,
    event_json: *const c_char,
) -> i32 {
    let event = serde_json::from_str(CStr::from_ptr(event_json).to_str().unwrap()).unwrap();
    EVENTS
        .get_or_init(Default::default)
        .lock()
        .unwrap()
        .push(event);
    FFI_OK
}

unsafe extern "C-unwind" fn noop_release(_context: *mut c_void) {}

unsafe extern "C-unwind" fn driver_callback(
    _context: *mut c_void,
    request_json: *const c_char,
) -> i32 {
    let request: Value =
        serde_json::from_str(CStr::from_ptr(request_json).to_str().unwrap()).unwrap();
    assert_eq!(request["schema_version"], "1");
    let call_id = request["call_id"].as_u64().unwrap();
    LAST_CALL.store(call_id, Ordering::SeqCst);
    if DRIVER_MODE.load(Ordering::SeqCst) == 1 {
        let result = CString::new(
            json!({
                "schema_version": "1",
                "ok": false,
                "error": {
                    "code": "model_unavailable",
                    "message": "provider rejected sk-live-secret",
                    "details": {"authorization": "Bearer sk-live-secret"}
                }
            })
            .to_string(),
        )
        .unwrap();
        let handle = *HANDLE.get_or_init(Default::default).lock().unwrap();
        return notemeld_agent_complete_driver_call(
            handle as *mut AgentRuntimeHandle,
            call_id,
            result.as_ptr(),
        );
    }
    if DRIVER_MODE.load(Ordering::SeqCst) == 2 {
        let stage = TOOL_STAGE.fetch_add(1, Ordering::SeqCst);
        let result = match (stage, request["kind"].as_str()) {
            (0, Some("model.stream")) => json!({"schema_version":"1","ok":true,
                "completion":{"content":"","tool_calls":[{"call_id":"ffi-tool-1","tool_name":"lookup","arguments":{"q":"hello"}}],"finish_reason":"tool_calls","usage":{"input_tokens":1,"output_tokens":1,"cache_read_tokens":0,"cache_write_tokens":0}}}),
            (1, Some("tool.invoke")) => {
                json!({"schema_version":"1","ok":true,"output":{"answer":42}})
            }
            (2, Some("model.stream")) => json!({"schema_version":"1","ok":true,
                "completion":{"content":"tool complete","tool_calls":[],"finish_reason":"stop","usage":{"input_tokens":1,"output_tokens":1,"cache_read_tokens":0,"cache_write_tokens":0}}}),
            _ => {
                json!({"schema_version":"1","ok":false,"error":{"code":"sdk_internal_error","message":"unexpected harness sequence"}})
            }
        };
        let result = CString::new(result.to_string()).unwrap();
        let handle = *HANDLE.get_or_init(Default::default).lock().unwrap();
        return notemeld_agent_complete_driver_call(
            handle as *mut AgentRuntimeHandle,
            call_id,
            result.as_ptr(),
        );
    }
    let result = CString::new(
        json!({
            "schema_version": "1",
            "ok": true,
            "chunks": [{"type": "content_delta", "delta": "hello"}],
            "completion": {
                "content": "hello",
                "tool_calls": [],
                "finish_reason": "stop",
                "usage": {"input_tokens": 1, "output_tokens": 1,
                    "cache_read_tokens": 0, "cache_write_tokens": 0}
            }
        })
        .to_string(),
    )
    .unwrap();
    let handle = *HANDLE.get_or_init(Default::default).lock().unwrap();
    notemeld_agent_complete_driver_call(handle as *mut AgentRuntimeHandle, call_id, result.as_ptr())
}

#[test]
fn native_driver_roundtrip_runs_model_tool_and_model_to_success() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    EVENTS.get_or_init(Default::default).lock().unwrap().clear();
    DRIVER_MODE.store(2, Ordering::SeqCst);
    TOOL_STAGE.store(0, Ordering::SeqCst);
    let config = CString::new(r#"{"schema_version":"1","max_turns":4}"#).unwrap();
    let handle = notemeld_agent_runtime_new(config.as_ptr());
    *HANDLE.get_or_init(Default::default).lock().unwrap() = handle as usize;
    assert_eq!(
        notemeld_agent_runtime_set_callbacks(
            handle,
            Some(event_callback),
            std::ptr::null_mut(),
            Some(driver_callback),
            std::ptr::null_mut(),
            Some(noop_release),
            std::ptr::null_mut()
        ),
        FFI_OK
    );
    let turn = notemeld_agent_submit_turn(
        handle,
        request("eeeeeeee-eeee-4eee-8eee-eeeeeeeeeeee").as_ptr(),
    );
    assert_eq!(notemeld_agent_wait_turn(handle, turn, 5_000), FFI_OK);
    assert_eq!(TOOL_STAGE.load(Ordering::SeqCst), 3);
    let events = EVENTS.get().unwrap().lock().unwrap().clone();
    assert!(events.iter().any(|event| event["type"] == "tool.started"));
    assert_eq!(events.last().unwrap()["type"], "turn.succeeded");
    DRIVER_MODE.store(0, Ordering::SeqCst);
    notemeld_agent_runtime_free(handle);
}

#[test]
fn driver_errors_preserve_stable_code_without_leaking_untrusted_payloads() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    EVENTS.get_or_init(Default::default).lock().unwrap().clear();
    DRIVER_MODE.store(1, Ordering::SeqCst);
    let config = CString::new(r#"{"schema_version":"1"}"#).unwrap();
    let handle = notemeld_agent_runtime_new(config.as_ptr());
    *HANDLE.get_or_init(Default::default).lock().unwrap() = handle as usize;
    assert_eq!(
        notemeld_agent_runtime_set_callbacks(
            handle,
            Some(event_callback),
            std::ptr::null_mut(),
            Some(driver_callback),
            std::ptr::null_mut(),
            Some(noop_release),
            std::ptr::null_mut(),
        ),
        FFI_OK
    );
    let turn = notemeld_agent_submit_turn(
        handle,
        request("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa").as_ptr(),
    );
    assert_eq!(notemeld_agent_wait_turn(handle, turn, 5_000), FFI_OK);
    let events = EVENTS.get().unwrap().lock().unwrap().clone();
    let failed = events
        .iter()
        .find(|event| event["type"] == "turn.failed")
        .expect("driver failure must produce turn.failed");
    assert_eq!(failed["payload"]["error"]["code"], "model_unavailable");
    assert!(!failed.to_string().contains("sk-live-secret"));
    let pointer = notemeld_agent_last_error_json(handle);
    assert!(!pointer.is_null());
    let last_error = unsafe { CStr::from_ptr(pointer).to_string_lossy().into_owned() };
    assert!(last_error.contains("model_unavailable"));
    assert!(!last_error.contains("sk-live-secret"));
    notemeld_agent_string_free(pointer);
    DRIVER_MODE.store(0, Ordering::SeqCst);
    notemeld_agent_runtime_free(handle);
}

fn request(id: &str) -> CString {
    CString::new(
        json!({
            "schema_version": "1",
            "request_id": id,
            "session_id": "ffi-session",
            "input": {"text": "hello", "attachments": [], "context_refs": []},
            "model_override": null,
            "approval_mode": "interactive"
        })
        .to_string(),
    )
    .unwrap()
}

#[test]
fn version_lifecycle_driver_event_cancel_steer_and_stale_handle_contract() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    EVENTS.get_or_init(Default::default).lock().unwrap().clear();
    unsafe {
        assert_eq!(
            CStr::from_ptr(notemeld_agent_sdk_version())
                .to_str()
                .unwrap(),
            "0.1.0"
        );
        assert_eq!(
            CStr::from_ptr(notemeld_agent_schema_version())
                .to_str()
                .unwrap(),
            "1"
        );
    }

    let config = CString::new(r#"{"schema_version":"1","max_turns":4}"#).unwrap();
    let handle = notemeld_agent_runtime_new(config.as_ptr());
    assert!(!handle.is_null());
    *HANDLE.get_or_init(Default::default).lock().unwrap() = handle as usize;
    assert_eq!(
        notemeld_agent_runtime_set_callbacks(
            handle,
            Some(event_callback),
            std::ptr::null_mut(),
            Some(driver_callback),
            std::ptr::null_mut(),
            Some(noop_release),
            std::ptr::null_mut(),
        ),
        FFI_OK
    );

    let turn = notemeld_agent_submit_turn(
        handle,
        request("11111111-1111-4111-8111-111111111111").as_ptr(),
    );
    assert_ne!(turn, 0);
    assert_eq!(notemeld_agent_wait_turn(handle, turn, 5_000), FFI_OK);
    let events = EVENTS.get().unwrap().lock().unwrap().clone();
    assert!(events.iter().all(|event| event["schema_version"] == "1"));
    assert_eq!(events.last().unwrap()["type"], "turn.succeeded");
    let duplicate = CString::new(r#"{"schema_version":"1","ok":true}"#).unwrap();
    assert_eq!(
        notemeld_agent_complete_driver_call(
            handle,
            LAST_CALL.load(Ordering::SeqCst),
            duplicate.as_ptr(),
        ),
        FFI_DUPLICATE_COMPLETION
    );
    assert_eq!(
        notemeld_agent_complete_driver_call(handle, u64::MAX, duplicate.as_ptr()),
        FFI_UNKNOWN_CALL
    );

    assert_eq!(notemeld_agent_cancel_turn(handle, turn), FFI_OK);
    assert_eq!(notemeld_agent_cancel_turn(handle, turn), FFI_OK);
    let steer = CString::new(r#"{"text":"change direction"}"#).unwrap();
    assert_eq!(
        notemeld_agent_steer_turn(handle, turn, steer.as_ptr()),
        FFI_UNSUPPORTED
    );

    notemeld_agent_runtime_free(handle);
    notemeld_agent_runtime_free(handle);
    assert_eq!(notemeld_agent_cancel_turn(handle, turn), FFI_INVALID_HANDLE);
}

#[test]
fn null_invalid_and_completion_ownership_contracts_are_safe() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    assert!(notemeld_agent_runtime_new(std::ptr::null()).is_null());
    assert_eq!(
        notemeld_agent_complete_driver_call(std::ptr::null_mut(), 1, std::ptr::null()),
        FFI_INVALID_HANDLE
    );
    notemeld_agent_runtime_free(std::ptr::null_mut());
    notemeld_agent_string_free(std::ptr::null_mut());
}

#[test]
fn callback_unwind_is_contained_by_the_ffi_boundary() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    unsafe extern "C-unwind" fn panicking_callback(
        _context: *mut c_void,
        _event_json: *const c_char,
    ) -> i32 {
        panic!("host callback panic")
    }

    let config = CString::new(r#"{"schema_version":"1"}"#).unwrap();
    let handle = notemeld_agent_runtime_new(config.as_ptr());
    *HANDLE.get_or_init(Default::default).lock().unwrap() = handle as usize;
    assert_eq!(
        notemeld_agent_runtime_set_callbacks(
            handle,
            Some(panicking_callback),
            std::ptr::null_mut(),
            Some(driver_callback),
            std::ptr::null_mut(),
            Some(noop_release),
            std::ptr::null_mut(),
        ),
        FFI_OK
    );
    let turn = notemeld_agent_submit_turn(
        handle,
        request("22222222-2222-4222-8222-222222222222").as_ptr(),
    );
    assert_ne!(turn, 0);
    assert_eq!(notemeld_agent_wait_turn(handle, turn, 5_000), FFI_OK);
    notemeld_agent_runtime_free(handle);
}

unsafe extern "C-unwind" fn blocked_driver_callback(
    context: *mut c_void,
    request_json: *const c_char,
) -> i32 {
    let request: Value =
        serde_json::from_str(CStr::from_ptr(request_json).to_str().unwrap()).unwrap();
    let call_id = request["call_id"].as_u64().unwrap();
    BLOCKED_CALL
        .get_or_init(Default::default)
        .lock()
        .unwrap()
        .as_ref()
        .unwrap()
        .send((context as usize, call_id))
        .unwrap();
    FFI_OK
}

#[test]
fn cancel_completion_and_free_races_have_typed_bounded_outcomes() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    EVENTS.get_or_init(Default::default).lock().unwrap().clear();
    let (call_tx, call_rx) = mpsc::channel();
    *BLOCKED_CALL.get_or_init(Default::default).lock().unwrap() = Some(call_tx);
    let config = CString::new(r#"{"schema_version":"1"}"#).unwrap();
    let handle = notemeld_agent_runtime_new(config.as_ptr());
    assert_eq!(
        notemeld_agent_runtime_set_callbacks(
            handle,
            Some(event_callback),
            std::ptr::null_mut(),
            Some(blocked_driver_callback),
            std::ptr::null_mut(),
            Some(noop_release),
            std::ptr::null_mut(),
        ),
        FFI_OK
    );
    let turn = notemeld_agent_submit_turn(
        handle,
        request("77777777-7777-4777-8777-777777777777").as_ptr(),
    );
    let (_, call_id) = call_rx.recv().unwrap();
    assert_eq!(notemeld_agent_cancel_turn(handle, turn), FFI_OK);
    assert_eq!(notemeld_agent_wait_turn(handle, turn, 5_000), FFI_OK);
    let events = EVENTS.get().unwrap().lock().unwrap();
    assert_eq!(
        events
            .iter()
            .filter(|event| event["type"] == "turn.cancelled")
            .count(),
        1
    );
    drop(events);
    let completion = CString::new(r#"{"schema_version":"1","ok":true}"#).unwrap();
    assert_eq!(
        notemeld_agent_complete_driver_call(handle, call_id, completion.as_ptr()),
        FFI_LATE_COMPLETION
    );
    notemeld_agent_runtime_free(handle);
    assert_eq!(
        notemeld_agent_complete_driver_call(handle, call_id, completion.as_ptr()),
        FFI_INVALID_HANDLE
    );
}

#[test]
fn driver_call_ids_are_process_unique_and_cannot_cross_runtime_boundaries() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    let (call_tx, call_rx) = mpsc::channel();
    *BLOCKED_CALL.get_or_init(Default::default).lock().unwrap() = Some(call_tx);
    let config = CString::new(r#"{"schema_version":"1"}"#).unwrap();
    let first = notemeld_agent_runtime_new(config.as_ptr());
    let second = notemeld_agent_runtime_new(config.as_ptr());
    for (handle, context) in [(first, 1usize), (second, 2usize)] {
        assert_eq!(
            notemeld_agent_runtime_set_callbacks(
                handle,
                None,
                std::ptr::null_mut(),
                Some(blocked_driver_callback),
                context as *mut c_void,
                Some(noop_release),
                std::ptr::null_mut(),
            ),
            FFI_OK
        );
    }
    let first_turn = notemeld_agent_submit_turn(
        first,
        request("88888888-8888-4888-8888-888888888888").as_ptr(),
    );
    let second_turn = notemeld_agent_submit_turn(
        second,
        request("99999999-9999-4999-8999-999999999999").as_ptr(),
    );
    let mut first_call = 0;
    let mut second_call = 0;
    for _ in 0..2 {
        let (runtime, call_id) = call_rx.recv().unwrap();
        if runtime == 1 {
            first_call = call_id;
        } else {
            second_call = call_id;
        }
    }
    assert_ne!(first_call, second_call);
    let completion = CString::new(r#"{"schema_version":"1","ok":true}"#).unwrap();
    assert_eq!(
        notemeld_agent_complete_driver_call(first, second_call, completion.as_ptr()),
        FFI_UNKNOWN_CALL
    );
    assert_eq!(notemeld_agent_cancel_turn(first, first_turn), FFI_OK);
    assert_eq!(notemeld_agent_cancel_turn(second, second_turn), FFI_OK);
    assert_eq!(notemeld_agent_wait_turn(first, first_turn, 5_000), FFI_OK);
    assert_eq!(notemeld_agent_wait_turn(second, second_turn, 5_000), FFI_OK);
    notemeld_agent_runtime_free(first);
    notemeld_agent_runtime_free(second);
}

struct DelayedCallbackContext {
    entered: mpsc::Sender<()>,
    resume: Mutex<mpsc::Receiver<()>>,
    released: mpsc::Sender<()>,
}

unsafe extern "C-unwind" fn delayed_driver_callback(
    context: *mut c_void,
    _request_json: *const c_char,
) -> i32 {
    let context = &*(context as *const DelayedCallbackContext);
    context.entered.send(()).unwrap();
    context.resume.lock().unwrap().recv().unwrap();
    FFI_INTERNAL_ERROR
}

unsafe extern "C-unwind" fn release_delayed_context(context: *mut c_void) {
    let context = Box::from_raw(context as *mut DelayedCallbackContext);
    context.released.send(()).unwrap();
}

#[test]
fn free_is_nonblocking_and_releases_callback_context_after_inflight_callback() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    let (entered_tx, entered_rx) = mpsc::channel();
    let (resume_tx, resume_rx) = mpsc::channel();
    let (released_tx, released_rx) = mpsc::channel();
    let context = Box::into_raw(Box::new(DelayedCallbackContext {
        entered: entered_tx,
        resume: Mutex::new(resume_rx),
        released: released_tx,
    }));
    let config = CString::new(r#"{"schema_version":"1"}"#).unwrap();
    let handle = notemeld_agent_runtime_new(config.as_ptr());
    assert_eq!(
        notemeld_agent_runtime_set_callbacks(
            handle,
            None,
            context.cast(),
            Some(delayed_driver_callback),
            context.cast(),
            Some(release_delayed_context),
            context.cast(),
        ),
        FFI_OK
    );
    let turn = notemeld_agent_submit_turn(
        handle,
        request("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb").as_ptr(),
    );
    assert_ne!(turn, 0);
    entered_rx.recv().unwrap();
    notemeld_agent_runtime_free(handle);
    assert!(released_rx.try_recv().is_err());
    resume_tx.send(()).unwrap();
    released_rx.recv().unwrap();
    assert!(
        released_rx.try_recv().is_err(),
        "release must run exactly once"
    );
    notemeld_agent_runtime_free(handle);
}

#[test]
fn concurrent_completion_has_one_atomic_winner_and_wait_timeout_is_typed() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    let (call_tx, call_rx) = mpsc::channel();
    *BLOCKED_CALL.get_or_init(Default::default).lock().unwrap() = Some(call_tx);
    let config = CString::new(r#"{"schema_version":"1"}"#).unwrap();
    let handle = notemeld_agent_runtime_new(config.as_ptr());
    assert_eq!(
        notemeld_agent_runtime_set_callbacks(
            handle,
            None,
            std::ptr::null_mut(),
            Some(blocked_driver_callback),
            std::ptr::null_mut(),
            Some(noop_release),
            std::ptr::null_mut()
        ),
        FFI_OK
    );
    let turn = notemeld_agent_submit_turn(
        handle,
        request("dddddddd-dddd-4ddd-8ddd-dddddddddddd").as_ptr(),
    );
    let (_, call_id) = call_rx.recv().unwrap();
    assert_eq!(notemeld_agent_wait_turn(handle, turn, 0), FFI_TIMEOUT);

    let barrier = Arc::new(Barrier::new(3));
    let mut workers = Vec::new();
    for _ in 0..2 {
        let barrier = Arc::clone(&barrier);
        let raw = handle as usize;
        workers.push(std::thread::spawn(move || {
            let completion = CString::new(r#"{"schema_version":"1","ok":false,"error":{"code":"tool_failed","message":"raw"}}"#).unwrap();
            barrier.wait();
            notemeld_agent_complete_driver_call(
                raw as *mut AgentRuntimeHandle, call_id, completion.as_ptr())
        }));
    }
    barrier.wait();
    let mut results = workers
        .into_iter()
        .map(|worker| worker.join().unwrap())
        .collect::<Vec<_>>();
    results.sort_unstable();
    assert_eq!(results, vec![FFI_DUPLICATE_COMPLETION, FFI_OK]);
    assert_eq!(notemeld_agent_wait_turn(handle, turn, 5_000), FFI_OK);
    notemeld_agent_runtime_free(handle);
}

#[test]
fn shared_declarations_and_bindings_cannot_drift_from_the_c_abi() {
    let _guard = TEST_LOCK.get_or_init(Default::default).lock().unwrap();
    let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../..");
    let manifest: Value =
        serde_json::from_str(&std::fs::read_to_string(root.join("bindings/abi-v1.json")).unwrap())
            .unwrap();
    assert_eq!(manifest["sdk_version"], "0.1.0");
    assert_eq!(manifest["schema_version"], "1");
    let header = std::fs::read_to_string(root.join("include/notemeld_agent.h")).unwrap();
    let udl =
        std::fs::read_to_string(root.join("crates/agent-ffi/src/notemeld_agent.udl")).unwrap();
    assert_eq!(header, notemeld_agent::abi_render::render_header(&manifest));
    assert_eq!(
        udl,
        notemeld_agent::abi_render::render_semantic_udl(&manifest)
    );
    for binding in [
        "bindings/python/notemeld_agent_sdk/runtime.py",
        "bindings/swift/Sources/NoteMeldAgentSDK/Runtime.swift",
        "bindings/kotlin/src/main/kotlin/wiki/notemeld/agent/Runtime.kt",
        "bindings/harmony/src/main/ets/index.ets",
    ] {
        let source = std::fs::read_to_string(root.join(binding)).unwrap();
        assert!(source.contains("0.1.0"));
        assert!(source.contains("\"1\"") || source.contains("'1'") || source.contains("= \"1\""));
    }
    let python =
        std::fs::read_to_string(root.join("bindings/python/notemeld_agent_sdk/runtime.py"))
            .unwrap();
    assert!(python.contains("_RELEASE_CALLBACK"));
    assert!(python.contains("FFI_TIMEOUT = -10"));
    let swift =
        std::fs::read_to_string(root.join("bindings/swift/Sources/NoteMeldAgentSDK/Runtime.swift"))
            .unwrap();
    assert!(swift.contains("passRetained"));
    assert!(swift.contains("takeRetainedValue"));
    assert!(!swift.contains("passUnretained"));
    let jni =
        std::fs::read_to_string(root.join("bindings/kotlin/src/main/cpp/runtime_jni.cpp")).unwrap();
    assert!(jni.contains("GetStringChars"));
    assert!(jni.contains("ReleaseBridge"));
    assert!(!jni.contains("GetStringUTFChars"));
    assert!(!jni.contains("retired"));
    assert!(jni.contains("deferred_releases"));
    assert!(jni.contains("DrainDeferred"));
    let android_test = std::fs::read_to_string(root.join("examples/android-harness/app/src/androidTest/java/wiki/notemeld/agent/harness/NativeSmokeTest.kt")).unwrap();
    assert!(android_test.contains("CountDownLatch"));
    assert!(android_test.contains("turn.succeeded"));
    let harmony =
        std::fs::read_to_string(root.join("bindings/harmony/src/main/ets/index.ets")).unwrap();
    assert!(harmony.contains("waitForTerminal(timeoutMs: number = 30000): Promise<string>"));
    assert!(!harmony.contains("agentNative.waitTurn"));
    let harmony_native =
        std::fs::read_to_string(root.join("bindings/harmony/src/main/cpp/napi_init.cpp")).unwrap();
    assert!(harmony_native.contains("ReleaseBridge"));
    assert!(harmony_native.contains("#include <memory>"));
    assert!(harmony_native.contains("type != napi_function"));
    assert!(harmony_native.contains("return Int(env, handle == nullptr ? -2 : 0)"));
    assert!(!harmony_native.contains("retired_bridges"));
    assert!(!harmony_native.contains("napi_tsfn_abort"));

    let parse = harmony.find("JSON.parse(eventJson)").unwrap();
    let user = harmony.find("this.userEvent(eventJson)").unwrap();
    assert!(
        parse < user,
        "terminal state must settle before user callback"
    );
    assert!(harmony.contains("event['turn_id'] === this.activeTurnId"));
    assert!(harmony.contains(
        "this.resolveTerminal = null\n        this.rejectTerminal = null\n        this.activeToken = 0n"
    ));
    assert!(harmony.contains("agent_runtime_busy"));
    assert!(harmony.contains("callback registration failed"));
    assert!(harmony.contains("terminal wait timed out"));
    assert!(harmony.contains("const pendingReject = this.rejectTerminal"));

    let kotlin = std::fs::read_to_string(
        root.join("bindings/kotlin/src/main/kotlin/wiki/notemeld/agent/Runtime.kt"),
    )
    .unwrap();
    assert!(
        kotlin.find("nativeSdkVersion()").unwrap() < kotlin.find("nativeNew(configJson)").unwrap()
    );
    assert!(kotlin.contains("catch (error: Throwable)"));
    assert!(kotlin.contains("nativeFree(created)"));

    assert!(!root
        .join("examples/android-harness/app/src/main/java/wiki/notemeld/agent/harness/Smoke.kt")
        .exists());

    assert!(swift.contains("defer { lock.unlock() }"));
}
