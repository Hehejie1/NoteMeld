use std::{
    collections::HashMap,
    sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    },
};

use agent_events::{AgentError, AgentErrorCode, SessionId, TurnId};
use agent_tools::{
    execute_tool_round, ToolCall, ToolContext, ToolDescriptor, ToolDriver, ToolProgress,
    ToolProgressSink, ToolResult,
};
use async_trait::async_trait;
use serde_json::{json, Value};
use tokio::sync::{mpsc, Notify};

fn context() -> ToolContext {
    ToolContext::new(
        SessionId("session-1".to_owned()),
        TurnId("00000000-0000-4000-8000-000000000001".to_owned()),
    )
}

fn call(id: &str, serial: bool) -> ToolCall {
    ToolCall::try_new(id, format!("tool-{id}"), json!({"id": id}), serial).unwrap()
}

#[test]
fn malformed_or_non_object_tool_arguments_return_a_stable_agent_error() {
    for malformed in [json!(null), json!([1, 2]), json!("text"), json!(7)] {
        let error = ToolCall::try_new("call-1", "lookup", malformed, false).unwrap_err();
        assert_eq!(error.code, AgentErrorCode::InvalidInput);
        assert_eq!(error.message, "tool arguments must be a JSON object");
        assert_eq!(error.details["call_id"], "call-1");
        assert_eq!(error.details["tool_name"], "lookup");
    }
}

struct SerialProbeDriver {
    started: mpsc::UnboundedSender<String>,
    releases: Arc<HashMap<String, Arc<Notify>>>,
    active: Arc<AtomicUsize>,
    max_active: Arc<AtomicUsize>,
}

#[async_trait]
impl ToolDriver for SerialProbeDriver {
    async fn describe(&self, names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(names
            .iter()
            .map(|name| ToolDescriptor {
                name: name.clone(),
                description: String::new(),
                input_schema: json!({"type": "object"}),
            })
            .collect())
    }

    async fn invoke(
        &self,
        call: ToolCall,
        _context: ToolContext,
        _sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        let active = self.active.fetch_add(1, Ordering::SeqCst) + 1;
        self.max_active.fetch_max(active, Ordering::SeqCst);
        self.started.send(call.id().to_owned()).unwrap();
        self.releases[call.id()].notified().await;
        self.active.fetch_sub(1, Ordering::SeqCst);
        Ok(ToolResult::new(call.id(), json!({"completed": call.id()})))
    }
}

#[tokio::test]
async fn any_serial_call_makes_the_entire_model_round_serial() {
    let (started_tx, mut started_rx) = mpsc::unbounded_channel();
    let releases = Arc::new(HashMap::from([
        ("a".to_owned(), Arc::new(Notify::new())),
        ("b".to_owned(), Arc::new(Notify::new())),
        ("c".to_owned(), Arc::new(Notify::new())),
    ]));
    let max_active = Arc::new(AtomicUsize::new(0));
    let driver = Arc::new(SerialProbeDriver {
        started: started_tx,
        releases: Arc::clone(&releases),
        active: Arc::new(AtomicUsize::new(0)),
        max_active: Arc::clone(&max_active),
    });

    let task = tokio::spawn({
        let driver = Arc::clone(&driver);
        async move {
            execute_tool_round(
                driver,
                vec![call("a", false), call("b", true), call("c", false)],
                context(),
                ToolProgressSink::discard(),
            )
            .await
        }
    });

    assert_eq!(started_rx.recv().await.as_deref(), Some("a"));
    assert!(
        started_rx.try_recv().is_err(),
        "b must not start before a ends"
    );
    releases["a"].notify_one();
    assert_eq!(started_rx.recv().await.as_deref(), Some("b"));
    assert!(
        started_rx.try_recv().is_err(),
        "c must not start before b ends"
    );
    releases["b"].notify_one();
    assert_eq!(started_rx.recv().await.as_deref(), Some("c"));
    releases["c"].notify_one();

    let results = task.await.unwrap().unwrap();
    assert_eq!(
        results.iter().map(ToolResult::call_id).collect::<Vec<_>>(),
        ["a", "b", "c"]
    );
    assert_eq!(max_active.load(Ordering::SeqCst), 1);
}

struct ParallelDriver {
    started: mpsc::UnboundedSender<String>,
    releases: Arc<HashMap<String, Arc<Notify>>>,
}

#[async_trait]
impl ToolDriver for ParallelDriver {
    async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(Vec::new())
    }

    async fn invoke(
        &self,
        call: ToolCall,
        _context: ToolContext,
        sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        self.started.send(call.id().to_owned()).unwrap();
        self.releases[call.id()].notified().await;
        sink.emit(ToolProgress {
            call_id: call.id().to_owned(),
            message: format!("{} complete", call.id()),
            progress: Some(1.0),
            data: Value::Null,
        })
        .await?;
        Ok(ToolResult::new(call.id(), json!(call.id())))
    }
}

#[tokio::test]
async fn parallel_results_stay_in_call_order_while_progress_arrives_as_it_happens() {
    let (started_tx, mut started_rx) = mpsc::unbounded_channel();
    let releases = Arc::new(HashMap::from([
        ("first".to_owned(), Arc::new(Notify::new())),
        ("second".to_owned(), Arc::new(Notify::new())),
    ]));
    let progress = Arc::new(Mutex::new(Vec::new()));
    let progress_observer = Arc::clone(&progress);
    let sink = ToolProgressSink::new(move |event| {
        let progress_observer = Arc::clone(&progress_observer);
        async move {
            progress_observer.lock().unwrap().push(event.call_id);
            Ok(())
        }
    });
    let driver = Arc::new(ParallelDriver {
        started: started_tx,
        releases: Arc::clone(&releases),
    });

    let task = tokio::spawn({
        let driver = Arc::clone(&driver);
        async move {
            execute_tool_round(
                driver,
                vec![call("first", false), call("second", false)],
                context(),
                sink,
            )
            .await
        }
    });

    let mut started = vec![
        started_rx.recv().await.unwrap(),
        started_rx.recv().await.unwrap(),
    ];
    started.sort();
    assert_eq!(started, ["first", "second"]);

    releases["second"].notify_one();
    while progress.lock().unwrap().is_empty() {
        tokio::task::yield_now().await;
    }
    assert_eq!(*progress.lock().unwrap(), ["second"]);
    releases["first"].notify_one();

    let results = task.await.unwrap().unwrap();
    assert_eq!(
        results.iter().map(ToolResult::call_id).collect::<Vec<_>>(),
        ["first", "second"]
    );
    assert_eq!(*progress.lock().unwrap(), ["second", "first"]);
}

struct CancellationDriver {
    started: mpsc::UnboundedSender<()>,
    saw_cancel: mpsc::UnboundedSender<()>,
}

#[async_trait]
impl ToolDriver for CancellationDriver {
    async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(Vec::new())
    }

    async fn invoke(
        &self,
        _call: ToolCall,
        context: ToolContext,
        _sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        self.started.send(()).unwrap();
        context.cancellation.cancelled().await;
        self.saw_cancel.send(()).unwrap();
        Err(AgentError::new(
            AgentErrorCode::Cancelled,
            "tool round cancelled",
        ))
    }
}

#[tokio::test]
async fn scheduler_propagates_cancellation_to_running_tool_contexts() {
    let (started_tx, mut started_rx) = mpsc::unbounded_channel();
    let (cancel_tx, mut cancel_rx) = mpsc::unbounded_channel();
    let driver = Arc::new(CancellationDriver {
        started: started_tx,
        saw_cancel: cancel_tx,
    });
    let context = context();
    let cancellation = context.cancellation.clone();
    let task = tokio::spawn({
        let driver = Arc::clone(&driver);
        async move {
            execute_tool_round(
                driver,
                vec![call("waiting", false)],
                context,
                ToolProgressSink::discard(),
            )
            .await
        }
    });

    started_rx.recv().await.unwrap();
    cancellation.cancel();
    cancel_rx.recv().await.unwrap();

    let error = task.await.unwrap().unwrap_err();
    assert_eq!(error.code, AgentErrorCode::Cancelled);
    assert_eq!(error.message, "tool round cancelled");
}

struct IgnoredSinkFailureDriver;

#[async_trait]
impl ToolDriver for IgnoredSinkFailureDriver {
    async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
        Ok(Vec::new())
    }

    async fn invoke(
        &self,
        call: ToolCall,
        _context: ToolContext,
        sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        let _ignored = sink
            .emit(ToolProgress {
                call_id: call.id().to_owned(),
                message: "ignored failure".to_owned(),
                progress: None,
                data: Value::Null,
            })
            .await;
        Ok(ToolResult::new(call.id(), Value::Null))
    }
}

#[tokio::test]
async fn scheduler_surfaces_progress_sink_failure_even_if_a_driver_ignores_it() {
    let sink = ToolProgressSink::new(|_event| async {
        Err(AgentError::new(
            AgentErrorCode::SdkInternalError,
            "tool progress observer failed",
        ))
    });

    let error = execute_tool_round(
        Arc::new(IgnoredSinkFailureDriver),
        vec![call("ignored", false)],
        context(),
        sink,
    )
    .await
    .unwrap_err();

    assert_eq!(error.code, AgentErrorCode::SdkInternalError);
    assert_eq!(error.message, "tool progress observer failed");
}
