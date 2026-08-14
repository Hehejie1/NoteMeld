//! Platform-neutral model driver contracts for the universal Agent SDK.

use std::{future::Future, pin::Pin, sync::Arc};

use agent_events::AgentError;
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tokio::sync::Mutex;

pub use tokio_util::sync::CancellationToken;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ModelMessage {
    pub role: String,
    pub content: Value,
}

#[derive(Debug, Clone)]
pub struct ModelRequest {
    pub messages: Vec<ModelMessage>,
    pub cancellation: CancellationToken,
}

impl ModelRequest {
    pub fn new(messages: Vec<ModelMessage>) -> Self {
        Self {
            messages,
            cancellation: CancellationToken::new(),
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub enum ModelChunk {
    ContentDelta { delta: String },
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ModelToolCall {
    pub call_id: String,
    pub tool_name: String,
    pub arguments: Value,
}

#[derive(Debug, Clone, Copy, Default, PartialEq, Eq, Serialize, Deserialize)]
pub struct ModelUsage {
    pub input_tokens: u64,
    pub output_tokens: u64,
    pub cache_read_tokens: u64,
    pub cache_write_tokens: u64,
}

impl ModelUsage {
    pub const fn total_tokens(self) -> u64 {
        self.input_tokens + self.output_tokens
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ModelCompletion {
    pub content: String,
    pub tool_calls: Vec<ModelToolCall>,
    pub finish_reason: String,
    pub usage: ModelUsage,
}

type SinkFuture = Pin<Box<dyn Future<Output = Result<(), AgentError>> + Send>>;
type ChunkObserver = dyn Fn(ModelChunk) -> SinkFuture + Send + Sync;

struct ModelChunkSinkInner {
    observer: Arc<ChunkObserver>,
    emission_gate: Mutex<()>,
    first_failure: std::sync::Mutex<Option<AgentError>>,
}

#[derive(Clone)]
pub struct ModelChunkSink {
    inner: Arc<ModelChunkSinkInner>,
}

impl ModelChunkSink {
    pub fn new<F, Fut>(observer: F) -> Self
    where
        F: Fn(ModelChunk) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<(), AgentError>> + Send + 'static,
    {
        Self {
            inner: Arc::new(ModelChunkSinkInner {
                observer: Arc::new(move |chunk| Box::pin(observer(chunk))),
                emission_gate: Mutex::new(()),
                first_failure: std::sync::Mutex::new(None),
            }),
        }
    }

    pub fn discard() -> Self {
        Self::new(|_chunk| async { Ok(()) })
    }

    pub async fn emit(&self, chunk: ModelChunk) -> Result<(), AgentError> {
        let _guard = self.inner.emission_gate.lock().await;
        if let Some(error) = self.first_failure() {
            return Err(error);
        }

        let result = (self.inner.observer)(chunk).await;
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
pub trait ModelDriver: Send + Sync {
    async fn stream(
        &self,
        request: ModelRequest,
        sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError>;
}

pub async fn invoke_model<D>(
    driver: &D,
    request: ModelRequest,
    sink: ModelChunkSink,
) -> Result<ModelCompletion, AgentError>
where
    D: ModelDriver + ?Sized,
{
    let result = driver.stream(request, sink.clone()).await;
    if let Some(error) = sink.first_failure() {
        return Err(error);
    }
    result
}
