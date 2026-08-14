//! Platform-neutral tool driver contracts for the universal Agent SDK.

use std::{future::Future, pin::Pin, sync::Arc};

use agent_events::{AgentError, AgentErrorCode, SessionId, TurnId};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};
use tokio::{sync::Mutex, task::JoinSet};

pub use tokio_util::sync::CancellationToken;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ToolDescriptor {
    pub name: String,
    pub description: String,
    pub input_schema: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ToolCall {
    call_id: String,
    tool_name: String,
    arguments: Map<String, Value>,
    serial: bool,
}

impl ToolCall {
    pub fn try_new(
        call_id: impl Into<String>,
        tool_name: impl Into<String>,
        arguments: Value,
        serial: bool,
    ) -> Result<Self, AgentError> {
        let call_id = call_id.into();
        let tool_name = tool_name.into();
        let Value::Object(arguments) = arguments else {
            let mut error = AgentError::new(
                AgentErrorCode::InvalidInput,
                "tool arguments must be a JSON object",
            );
            error
                .details
                .insert("call_id".to_owned(), Value::String(call_id));
            error
                .details
                .insert("tool_name".to_owned(), Value::String(tool_name));
            return Err(error);
        };

        Ok(Self {
            call_id,
            tool_name,
            arguments,
            serial,
        })
    }

    pub fn id(&self) -> &str {
        &self.call_id
    }

    pub fn name(&self) -> &str {
        &self.tool_name
    }

    pub fn arguments(&self) -> &Map<String, Value> {
        &self.arguments
    }

    pub const fn is_serial(&self) -> bool {
        self.serial
    }
}

#[derive(Debug, Clone)]
pub struct ToolContext {
    pub session_id: SessionId,
    pub turn_id: TurnId,
    pub cancellation: CancellationToken,
    pub metadata: Map<String, Value>,
}

impl ToolContext {
    pub fn new(session_id: SessionId, turn_id: TurnId) -> Self {
        Self {
            session_id,
            turn_id,
            cancellation: CancellationToken::new(),
            metadata: Map::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ToolProgress {
    pub call_id: String,
    pub message: String,
    pub progress: Option<f64>,
    pub data: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ToolResult {
    call_id: String,
    pub output: Value,
}

impl ToolResult {
    pub fn new(call_id: impl Into<String>, output: Value) -> Self {
        Self {
            call_id: call_id.into(),
            output,
        }
    }

    pub fn call_id(&self) -> &str {
        &self.call_id
    }
}

type SinkFuture = Pin<Box<dyn Future<Output = Result<(), AgentError>> + Send>>;
type ProgressObserver = dyn Fn(ToolProgress) -> SinkFuture + Send + Sync;

struct ToolProgressSinkInner {
    observer: Arc<ProgressObserver>,
    emission_gate: Mutex<()>,
    first_failure: std::sync::Mutex<Option<AgentError>>,
}

#[derive(Clone)]
pub struct ToolProgressSink {
    inner: Arc<ToolProgressSinkInner>,
}

impl ToolProgressSink {
    pub fn new<F, Fut>(observer: F) -> Self
    where
        F: Fn(ToolProgress) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<(), AgentError>> + Send + 'static,
    {
        Self {
            inner: Arc::new(ToolProgressSinkInner {
                observer: Arc::new(move |progress| Box::pin(observer(progress))),
                emission_gate: Mutex::new(()),
                first_failure: std::sync::Mutex::new(None),
            }),
        }
    }

    pub fn discard() -> Self {
        Self::new(|_progress| async { Ok(()) })
    }

    pub async fn emit(&self, progress: ToolProgress) -> Result<(), AgentError> {
        let _guard = self.inner.emission_gate.lock().await;
        if let Some(error) = self.first_failure() {
            return Err(error);
        }

        let result = (self.inner.observer)(progress).await;
        if let Err(error) = &result {
            *self.inner.first_failure.lock().unwrap() = Some(error.clone());
        }
        result
    }

    pub fn first_failure(&self) -> Option<AgentError> {
        self.inner.first_failure.lock().unwrap().clone()
    }
}

#[async_trait]
pub trait ToolDriver: Send + Sync {
    async fn describe(&self, names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError>;

    async fn invoke(
        &self,
        call: ToolCall,
        context: ToolContext,
        sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError>;
}

pub async fn execute_tool_round<D>(
    driver: Arc<D>,
    calls: Vec<ToolCall>,
    context: ToolContext,
    sink: ToolProgressSink,
) -> Result<Vec<ToolResult>, AgentError>
where
    D: ToolDriver + ?Sized + 'static,
{
    if context.cancellation.is_cancelled() {
        return Err(cancelled_error());
    }

    if calls.iter().any(ToolCall::is_serial) {
        let mut results = Vec::with_capacity(calls.len());
        for call in calls {
            results.push(invoke_one(driver.as_ref(), call, context.clone(), sink.clone()).await?);
        }
        Ok(results)
    } else {
        let result_count = calls.len();
        let mut tasks = JoinSet::new();
        for (index, call) in calls.into_iter().enumerate() {
            let driver = Arc::clone(&driver);
            let context = context.clone();
            let sink = sink.clone();
            tasks.spawn(async move {
                (
                    index,
                    invoke_one(driver.as_ref(), call, context, sink).await,
                )
            });
        }

        let mut results = vec![None; result_count];
        while let Some(joined) = tasks.join_next().await {
            let (index, result) = match joined {
                Ok(joined) => joined,
                Err(_) => {
                    let error = AgentError::new(
                        AgentErrorCode::SdkInternalError,
                        "tool invocation task failed",
                    );
                    tasks.shutdown().await;
                    return Err(error);
                }
            };
            match result {
                Ok(result) => results[index] = Some(result),
                Err(error) => {
                    tasks.shutdown().await;
                    return Err(error);
                }
            }
        }

        results
            .into_iter()
            .map(|result| {
                result.ok_or_else(|| {
                    AgentError::new(
                        AgentErrorCode::SdkInternalError,
                        "tool invocation result missing",
                    )
                })
            })
            .collect()
    }
}

async fn invoke_one<D>(
    driver: &D,
    call: ToolCall,
    context: ToolContext,
    sink: ToolProgressSink,
) -> Result<ToolResult, AgentError>
where
    D: ToolDriver + ?Sized,
{
    if context.cancellation.is_cancelled() {
        return Err(cancelled_error());
    }

    let result = driver.invoke(call, context, sink.clone()).await;
    if let Some(error) = sink.first_failure() {
        return Err(error);
    }
    result
}

fn cancelled_error() -> AgentError {
    AgentError::new(AgentErrorCode::Cancelled, "tool round cancelled")
}
