use std::sync::{
    atomic::{AtomicUsize, Ordering},
    Arc, Mutex,
};

use agent_core::{AgentEventSink, AgentRuntime, AgentRuntimeConfig};
use agent_events::{
    AgentError, AgentErrorCode, AgentEvent, ApprovalMode, RequestId, SessionId, TurnInput,
    TurnRequest, SCHEMA_VERSION,
};
use agent_model::{
    CancellationToken, ModelChunk, ModelChunkSink, ModelCompletion, ModelDriver, ModelRequest,
    ModelToolCall, ModelUsage,
};
use agent_tools::{
    ToolCall, ToolContext, ToolDescriptor, ToolDriver, ToolProgressSink, ToolResult,
};
use async_trait::async_trait;
use serde_json::{json, Value};
use tokio::sync::mpsc;

fn request() -> TurnRequest {
    TurnRequest {
        schema_version: SCHEMA_VERSION.to_owned(),
        request_id: RequestId("00000000-0000-4000-8000-000000000001".to_owned()),
        session_id: SessionId("failure-session".to_owned()),
        input: TurnInput {
            text: "hello".to_owned(),
            ..TurnInput::default()
        },
        model_override: None,
        approval_mode: ApprovalMode::Interactive,
        extra: Default::default(),
    }
}

struct NeverTools;

#[async_trait]
impl ToolDriver for NeverTools {
    async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(vec![])
    }

    async fn invoke(
        &self,
        _call: ToolCall,
        _context: ToolContext,
        _sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        panic!("tool must not be invoked")
    }
}

struct FailingModel;

#[async_trait]
impl ModelDriver for FailingModel {
    async fn stream(
        &self,
        _request: ModelRequest,
        _sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        Err(AgentError::new(
            AgentErrorCode::ModelUnavailable,
            "model unavailable",
        ))
    }
}

struct CancellingFailingModel;

#[async_trait]
impl ModelDriver for CancellingFailingModel {
    async fn stream(
        &self,
        request: ModelRequest,
        _sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        request.cancellation.cancel();
        Err(AgentError::new(
            AgentErrorCode::ModelUnavailable,
            "model failed while cancellation was requested",
        ))
    }
}

struct ToolCallingModel;

#[async_trait]
impl ModelDriver for ToolCallingModel {
    async fn stream(
        &self,
        _request: ModelRequest,
        _sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        Ok(ModelCompletion {
            content: String::new(),
            tool_calls: vec![ModelToolCall {
                call_id: "call-1".to_owned(),
                tool_name: "explode".to_owned(),
                arguments: json!({}),
            }],
            finish_reason: "tool_calls".to_owned(),
            usage: ModelUsage::default(),
        })
    }
}

struct FailingTools;

#[async_trait]
impl ToolDriver for FailingTools {
    async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(vec![])
    }

    async fn invoke(
        &self,
        _call: ToolCall,
        _context: ToolContext,
        _sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        Err(AgentError::new(AgentErrorCode::ToolFailed, "tool failed"))
    }
}

struct CancellingFailingTools;

#[async_trait]
impl ToolDriver for CancellingFailingTools {
    async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(vec![])
    }

    async fn invoke(
        &self,
        _call: ToolCall,
        context: ToolContext,
        _sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        context.cancellation.cancel();
        Err(AgentError::new(
            AgentErrorCode::ToolFailed,
            "tool failed while cancellation was requested",
        ))
    }
}

struct SuccessfulModel {
    calls: Arc<AtomicUsize>,
    cancel_before_return: bool,
}

struct OverflowingUsageModel;

#[async_trait]
impl ModelDriver for OverflowingUsageModel {
    async fn stream(
        &self,
        _request: ModelRequest,
        _sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        Ok(ModelCompletion {
            content: "bounded usage".to_owned(),
            tool_calls: vec![],
            finish_reason: "stop".to_owned(),
            usage: ModelUsage {
                input_tokens: u64::MAX,
                output_tokens: 1,
                cache_read_tokens: 0,
                cache_write_tokens: 0,
            },
        })
    }
}

struct SensitiveRoundModel {
    calls: AtomicUsize,
    arguments: Value,
}

#[async_trait]
impl ModelDriver for SensitiveRoundModel {
    async fn stream(
        &self,
        _request: ModelRequest,
        _sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        if self.calls.fetch_add(1, Ordering::SeqCst) == 0 {
            Ok(ModelCompletion {
                content: String::new(),
                tool_calls: vec![ModelToolCall {
                    call_id: "sensitive-call".to_owned(),
                    tool_name: "sensitive-tool".to_owned(),
                    arguments: self.arguments.clone(),
                }],
                finish_reason: "tool_calls".to_owned(),
                usage: ModelUsage::default(),
            })
        } else {
            Ok(ModelCompletion {
                content: "safe final answer".to_owned(),
                tool_calls: vec![],
                finish_reason: "stop".to_owned(),
                usage: ModelUsage::default(),
            })
        }
    }
}

struct CapturingSensitiveTool {
    seen_arguments: Arc<Mutex<Option<Value>>>,
    output: Value,
}

#[async_trait]
impl ToolDriver for CapturingSensitiveTool {
    async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(vec![])
    }

    async fn invoke(
        &self,
        call: ToolCall,
        _context: ToolContext,
        _sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        *self.seen_arguments.lock().unwrap() = Some(Value::Object(call.arguments().clone()));
        Ok(ToolResult::new(call.id(), self.output.clone()))
    }
}

#[async_trait]
impl ModelDriver for SuccessfulModel {
    async fn stream(
        &self,
        request: ModelRequest,
        sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        self.calls.fetch_add(1, Ordering::SeqCst);
        sink.emit(ModelChunk::ContentDelta {
            delta: "done".to_owned(),
        })
        .await?;
        if self.cancel_before_return {
            request.cancellation.cancel();
        }
        Ok(ModelCompletion {
            content: "driver fallback must not replace streamed text".to_owned(),
            tool_calls: vec![],
            finish_reason: "stop".to_owned(),
            usage: ModelUsage {
                input_tokens: 4,
                output_tokens: 1,
                cache_read_tokens: 0,
                cache_write_tokens: 0,
            },
        })
    }
}

fn terminal_count(events: &[AgentEvent]) -> usize {
    events
        .iter()
        .filter(|event| {
            matches!(
                event,
                AgentEvent::TurnSucceeded(_)
                    | AgentEvent::TurnFailed(_)
                    | AgentEvent::TurnCancelled(_)
                    | AgentEvent::TurnInterrupted(_)
            )
        })
        .count()
}

async fn error_trace(
    model: Arc<dyn ModelDriver>,
    tools: Arc<dyn ToolDriver>,
) -> (AgentError, Vec<AgentEvent>) {
    let observed = Arc::new(Mutex::new(vec![]));
    let observer = Arc::clone(&observed);
    let sink = AgentEventSink::new(move |event| {
        observer.lock().unwrap().push(event);
        async { Ok(()) }
    });
    let error = AgentRuntime::new(model, tools, AgentRuntimeConfig { max_turns: 3 })
        .run_turn(request(), vec![], CancellationToken::new(), sink)
        .await
        .unwrap_err();
    let events = observed.lock().unwrap().clone();
    (error, events)
}

#[tokio::test]
async fn model_and_tool_errors_each_emit_one_failed_terminal() {
    let (model_error, model_events) =
        error_trace(Arc::new(FailingModel), Arc::new(NeverTools)).await;
    assert_eq!(model_error.code, AgentErrorCode::ModelUnavailable);
    assert_eq!(terminal_count(&model_events), 1);
    assert!(matches!(
        model_events.last(),
        Some(AgentEvent::TurnFailed(_))
    ));

    let (tool_error, tool_events) =
        error_trace(Arc::new(ToolCallingModel), Arc::new(FailingTools)).await;
    assert_eq!(tool_error.code, AgentErrorCode::ToolFailed);
    assert_eq!(terminal_count(&tool_events), 1);
    assert!(matches!(
        tool_events.last(),
        Some(AgentEvent::TurnFailed(_))
    ));
}

#[tokio::test]
async fn zero_max_turns_is_a_stable_invalid_input_with_one_failed_terminal() {
    let calls = Arc::new(AtomicUsize::new(0));
    let observed = Arc::new(Mutex::new(vec![]));
    let observer = Arc::clone(&observed);
    let error = AgentRuntime::new(
        Arc::new(SuccessfulModel {
            calls: Arc::clone(&calls),
            cancel_before_return: false,
        }),
        Arc::new(NeverTools),
        AgentRuntimeConfig { max_turns: 0 },
    )
    .run_turn(
        request(),
        vec![],
        CancellationToken::new(),
        AgentEventSink::new(move |event| {
            observer.lock().unwrap().push(event);
            async { Ok(()) }
        }),
    )
    .await
    .expect_err("zero max_turns must be rejected before calling a driver");

    assert_eq!(error.code, AgentErrorCode::InvalidInput);
    assert_eq!(error.details["reason"], "max_turns_must_be_positive");
    assert_eq!(error.details["max_turns"], 0);
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert_eq!(terminal_count(&observed.lock().unwrap()), 1);
    assert!(matches!(
        observed.lock().unwrap().last(),
        Some(AgentEvent::TurnFailed(_))
    ));
}

#[tokio::test]
async fn cancellation_is_checked_before_and_after_model_calls() {
    let calls = Arc::new(AtomicUsize::new(0));
    let runtime = AgentRuntime::new(
        Arc::new(SuccessfulModel {
            calls: Arc::clone(&calls),
            cancel_before_return: false,
        }),
        Arc::new(NeverTools),
        AgentRuntimeConfig { max_turns: 3 },
    );
    let cancel = CancellationToken::new();
    cancel.cancel();
    let observed = Arc::new(Mutex::new(vec![]));
    let observer = Arc::clone(&observed);
    let error = runtime
        .run_turn(
            request(),
            vec![],
            cancel,
            AgentEventSink::new(move |event| {
                observer.lock().unwrap().push(event);
                async { Ok(()) }
            }),
        )
        .await
        .unwrap_err();
    assert_eq!(error.code, AgentErrorCode::Cancelled);
    assert_eq!(calls.load(Ordering::SeqCst), 0);
    assert_eq!(terminal_count(&observed.lock().unwrap()), 1);

    let calls = Arc::new(AtomicUsize::new(0));
    let (error, events) = error_trace(
        Arc::new(SuccessfulModel {
            calls: Arc::clone(&calls),
            cancel_before_return: true,
        }),
        Arc::new(NeverTools),
    )
    .await;
    assert_eq!(error.code, AgentErrorCode::Cancelled);
    assert_eq!(calls.load(Ordering::SeqCst), 1);
    assert_eq!(terminal_count(&events), 1);
    assert!(matches!(events.last(), Some(AgentEvent::TurnCancelled(_))));
}

#[tokio::test]
async fn cancellation_outranks_a_simultaneous_model_error() {
    let (error, events) = error_trace(Arc::new(CancellingFailingModel), Arc::new(NeverTools)).await;

    assert_eq!(error.code, AgentErrorCode::Cancelled);
    assert_eq!(terminal_count(&events), 1);
    assert!(matches!(events.last(), Some(AgentEvent::TurnCancelled(_))));
}

#[tokio::test]
async fn cancellation_outranks_a_simultaneous_tool_error() {
    let (error, events) =
        error_trace(Arc::new(ToolCallingModel), Arc::new(CancellingFailingTools)).await;

    assert_eq!(error.code, AgentErrorCode::Cancelled);
    assert_eq!(terminal_count(&events), 1);
    assert!(matches!(events.last(), Some(AgentEvent::TurnCancelled(_))));
}

#[tokio::test]
async fn observer_cancellation_after_final_usage_prevents_success() {
    let cancel = CancellationToken::new();
    let observer_cancel = cancel.clone();
    let (ack_tx, mut ack_rx) = mpsc::unbounded_channel();
    let observed = Arc::new(Mutex::new(vec![]));
    let observer_events = Arc::clone(&observed);
    let sink = AgentEventSink::new(move |event| {
        if matches!(event, AgentEvent::UsageUpdated(_)) {
            observer_cancel.cancel();
            ack_tx
                .send(())
                .expect("usage observer cancellation acknowledgement must be delivered");
        }
        observer_events.lock().unwrap().push(event);
        async { Ok(()) }
    });
    let runtime = AgentRuntime::new(
        Arc::new(SuccessfulModel {
            calls: Arc::new(AtomicUsize::new(0)),
            cancel_before_return: false,
        }),
        Arc::new(NeverTools),
        AgentRuntimeConfig { max_turns: 3 },
    );

    let error = runtime
        .run_turn(request(), vec![], cancel, sink)
        .await
        .expect_err("observer-triggered cancellation must outrank final success");
    ack_rx
        .recv()
        .await
        .expect("usage observer must acknowledge the cancellation point");

    assert_eq!(error.code, AgentErrorCode::Cancelled);
    assert_eq!(terminal_count(&observed.lock().unwrap()), 1);
    assert!(matches!(
        observed.lock().unwrap().last(),
        Some(AgentEvent::TurnCancelled(_))
    ));
}

#[tokio::test]
async fn usage_total_saturates_without_bypassing_the_success_terminal() {
    let observed = Arc::new(Mutex::new(vec![]));
    let observer = Arc::clone(&observed);
    let outcome = AgentRuntime::new(
        Arc::new(OverflowingUsageModel),
        Arc::new(NeverTools),
        AgentRuntimeConfig { max_turns: 1 },
    )
    .run_turn(
        request(),
        vec![],
        CancellationToken::new(),
        AgentEventSink::new(move |event| {
            observer.lock().unwrap().push(event);
            async { Ok(()) }
        }),
    )
    .await
    .expect("usage overflow must not fail or panic the turn");

    let events = observed.lock().unwrap();
    let total_tokens = events.iter().find_map(|event| match event {
        AgentEvent::UsageUpdated(payload) => payload.total_tokens,
        _ => None,
    });
    assert_eq!(outcome.content, "bounded usage");
    assert_eq!(total_tokens, Some(u64::MAX));
    assert_eq!(terminal_count(&events), 1);
    assert!(matches!(events.last(), Some(AgentEvent::TurnSucceeded(_))));
}

#[tokio::test]
async fn tool_events_redact_nested_secrets_and_bound_large_summaries() {
    let large_text = "x".repeat(20_000);
    let large_array = (0..100)
        .map(|index| json!({"index": index}))
        .collect::<Vec<_>>();
    let large_object = (0..100)
        .map(|index| (format!("field_{index:03}"), json!(index)))
        .collect::<serde_json::Map<_, _>>();
    let arguments = json!({
        "api_key": "ARG-API-SECRET",
        "nested": [{
            "Authorization": "ARG-AUTH-SECRET",
            "ordinary": large_text,
            "deeper": {"cookie": "ARG-COOKIE-SECRET"}
        }],
        "large_array": large_array,
        "large_object": large_object,
    });
    let output = json!({
        "result": [{
            "ToKeN": "RESULT-TOKEN-SECRET",
            "nested": {"password": "RESULT-PASSWORD-SECRET"},
            "large": "y".repeat(20_000)
        }],
        "secret": "RESULT-CREDENTIAL-SECRET"
    });
    let seen_arguments = Arc::new(Mutex::new(None));
    let observed = Arc::new(Mutex::new(vec![]));
    let observer = Arc::clone(&observed);
    let outcome = AgentRuntime::new(
        Arc::new(SensitiveRoundModel {
            calls: AtomicUsize::new(0),
            arguments: arguments.clone(),
        }),
        Arc::new(CapturingSensitiveTool {
            seen_arguments: Arc::clone(&seen_arguments),
            output: output.clone(),
        }),
        AgentRuntimeConfig { max_turns: 2 },
    )
    .run_turn(
        request(),
        vec![],
        CancellationToken::new(),
        AgentEventSink::new(move |event| {
            observer.lock().unwrap().push(event);
            async { Ok(()) }
        }),
    )
    .await
    .expect("safe summaries must not change the tool round outcome");

    assert_eq!(*seen_arguments.lock().unwrap(), Some(arguments));
    assert_eq!(
        outcome
            .messages
            .iter()
            .find(|message| message.role == "tool")
            .map(|message| &message.content),
        Some(&output),
        "the internal tool message must retain the complete result"
    );

    let events = observed.lock().unwrap();
    let serialized_events = serde_json::to_string(&*events).unwrap();
    for secret in [
        "ARG-API-SECRET",
        "ARG-AUTH-SECRET",
        "ARG-COOKIE-SECRET",
        "RESULT-TOKEN-SECRET",
        "RESULT-PASSWORD-SECRET",
        "RESULT-CREDENTIAL-SECRET",
    ] {
        assert!(
            !serialized_events.contains(secret),
            "event serialization leaked {secret}"
        );
    }
    for summary in events.iter().filter_map(|event| match event {
        AgentEvent::ToolStarted(payload) => payload.arguments_summary.as_ref(),
        AgentEvent::ToolCompleted(payload) => payload.result_summary.as_ref(),
        _ => None,
    }) {
        assert!(
            serde_json::to_vec(summary).unwrap().len() <= 4096,
            "tool event summary exceeded the 4096-byte wire bound"
        );
    }
    let started_summary = events
        .iter()
        .find_map(|event| match event {
            AgentEvent::ToolStarted(payload) => payload.arguments_summary.as_ref(),
            _ => None,
        })
        .expect("tool start must contain a safe summary");
    assert!(
        started_summary["large_array"].as_array().unwrap().len() <= 17,
        "large arrays must contain at most 16 values plus a truncation marker"
    );
    assert!(
        started_summary["large_object"].as_object().unwrap().len() <= 17,
        "large objects must contain at most 16 values plus a truncation marker"
    );
    assert!(serialized_events.contains("[REDACTED]"));
    assert_eq!(terminal_count(&events), 1);
}

#[tokio::test]
async fn observer_failures_become_nonrecursive_diagnostics_without_changing_success() {
    let attempts = Arc::new(Mutex::new(vec![]));
    let observer_attempts = Arc::clone(&attempts);
    let fail_once = Arc::new(AtomicUsize::new(0));
    let observer_failure = Arc::clone(&fail_once);
    let sink = AgentEventSink::new(move |event| {
        observer_attempts.lock().unwrap().push(event);
        let should_fail = matches!(
            observer_attempts.lock().unwrap().last(),
            Some(AgentEvent::MessageDelta(_))
        ) && observer_failure.fetch_add(1, Ordering::SeqCst) == 0;
        async move {
            if should_fail {
                Err(AgentError::new(
                    AgentErrorCode::SdkInternalError,
                    "observer unavailable",
                ))
            } else {
                Ok(())
            }
        }
    });
    let diagnostic_view = sink.clone();
    let outcome = AgentRuntime::new(
        Arc::new(SuccessfulModel {
            calls: Arc::new(AtomicUsize::new(0)),
            cancel_before_return: false,
        }),
        Arc::new(NeverTools),
        AgentRuntimeConfig { max_turns: 3 },
    )
    .run_turn(request(), vec![], CancellationToken::new(), sink)
    .await
    .expect("observer failure must not fail the canonical turn");

    assert_eq!(outcome.content, "done");
    assert_eq!(outcome.diagnostics.len(), 1);
    assert_eq!(diagnostic_view.diagnostics(), outcome.diagnostics);
    assert_eq!(terminal_count(&attempts.lock().unwrap()), 1);
    assert!(matches!(
        attempts.lock().unwrap().last(),
        Some(AgentEvent::TurnSucceeded(_))
    ));
}

#[tokio::test]
async fn a_terminal_observer_failure_never_causes_a_second_terminal() {
    let terminal_attempts = Arc::new(AtomicUsize::new(0));
    let attempts = Arc::clone(&terminal_attempts);
    let sink = AgentEventSink::new(move |event| {
        let terminal = matches!(
            event,
            AgentEvent::TurnSucceeded(_)
                | AgentEvent::TurnFailed(_)
                | AgentEvent::TurnCancelled(_)
                | AgentEvent::TurnInterrupted(_)
        );
        if terminal {
            attempts.fetch_add(1, Ordering::SeqCst);
        }
        async move {
            if terminal {
                Err(AgentError::new(
                    AgentErrorCode::SdkInternalError,
                    "terminal observer failed",
                ))
            } else {
                Ok(())
            }
        }
    });

    let outcome = AgentRuntime::new(
        Arc::new(SuccessfulModel {
            calls: Arc::new(AtomicUsize::new(0)),
            cancel_before_return: false,
        }),
        Arc::new(NeverTools),
        AgentRuntimeConfig { max_turns: 3 },
    )
    .run_turn(request(), vec![], CancellationToken::new(), sink)
    .await
    .unwrap();

    assert_eq!(terminal_attempts.load(Ordering::SeqCst), 1);
    assert_eq!(outcome.diagnostics.len(), 1);
}
