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
use serde_json::json;

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

struct SuccessfulModel {
    calls: Arc<AtomicUsize>,
    cancel_before_return: bool,
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
