use std::{future::Future, pin::Pin, sync::Arc};

use agent_events::{AgentError, AgentErrorCode, AgentEvent, TurnStatus};
use agent_model::{ModelMessage, ModelToolCall, ModelUsage};
use serde::{Deserialize, Serialize};
use serde_json::{json, Map, Value};
use tokio::sync::Mutex;

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AgentMessage {
    pub role: String,
    pub content: Value,
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub tool_calls: Vec<ModelToolCall>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub tool_call_id: Option<String>,
    #[serde(default, skip_serializing_if = "Map::is_empty")]
    pub meta: Map<String, Value>,
}

impl AgentMessage {
    pub fn user(content: Value) -> Self {
        Self::new("user", content)
    }

    pub fn assistant(content: Value, tool_calls: Vec<ModelToolCall>) -> Self {
        Self {
            tool_calls,
            ..Self::new("assistant", content)
        }
    }

    pub fn tool_result(call_id: impl Into<String>, content: Value) -> Self {
        Self {
            tool_call_id: Some(call_id.into()),
            ..Self::new("tool", content)
        }
    }

    fn new(role: impl Into<String>, content: Value) -> Self {
        Self {
            role: role.into(),
            content,
            tool_calls: Vec::new(),
            tool_call_id: None,
            meta: Map::new(),
        }
    }

    pub(crate) fn as_model_message(&self) -> ModelMessage {
        let content = if !self.tool_calls.is_empty() {
            json!({
                "content": self.content,
                "tool_calls": self.tool_calls,
            })
        } else if let Some(call_id) = &self.tool_call_id {
            json!({
                "call_id": call_id,
                "content": self.content,
            })
        } else {
            self.content.clone()
        };
        ModelMessage {
            role: self.role.clone(),
            content,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct AgentDiagnostic {
    pub code: AgentErrorCode,
    pub message: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TurnOutcome {
    pub status: TurnStatus,
    pub content: String,
    pub messages: Vec<AgentMessage>,
    pub usage: ModelUsage,
    pub turn_count: usize,
    pub diagnostics: Vec<AgentDiagnostic>,
}

type SinkFuture = Pin<Box<dyn Future<Output = Result<(), AgentError>> + Send>>;
type EventObserver = dyn Fn(AgentEvent) -> SinkFuture + Send + Sync;

struct AgentEventSinkInner {
    observer: Arc<EventObserver>,
    emission_gate: Mutex<()>,
    first_diagnostic: std::sync::Mutex<Option<AgentDiagnostic>>,
}

/// A best-effort external event observer.
///
/// Observer failures never cross into the canonical loop. The first safe error
/// is retained as a bounded diagnostic, while later events (including the one
/// terminal event) are still offered to the observer. Diagnostics are not
/// emitted as events, so a failing observer cannot recurse.
#[derive(Clone)]
pub struct AgentEventSink {
    inner: Arc<AgentEventSinkInner>,
}

impl AgentEventSink {
    pub fn new<F, Fut>(observer: F) -> Self
    where
        F: Fn(AgentEvent) -> Fut + Send + Sync + 'static,
        Fut: Future<Output = Result<(), AgentError>> + Send + 'static,
    {
        Self {
            inner: Arc::new(AgentEventSinkInner {
                observer: Arc::new(move |event| Box::pin(observer(event))),
                emission_gate: Mutex::new(()),
                first_diagnostic: std::sync::Mutex::new(None),
            }),
        }
    }

    pub fn discard() -> Self {
        Self::new(|_event| async { Ok(()) })
    }

    pub async fn emit(&self, event: AgentEvent) {
        let _guard = self.inner.emission_gate.lock().await;
        if let Err(error) = (self.inner.observer)(event).await {
            let mut diagnostic = self.inner.first_diagnostic.lock().unwrap();
            if diagnostic.is_none() {
                *diagnostic = Some(AgentDiagnostic {
                    code: error.code,
                    message: error.message,
                });
            }
        }
    }

    pub fn diagnostics(&self) -> Vec<AgentDiagnostic> {
        self.inner
            .first_diagnostic
            .lock()
            .unwrap()
            .clone()
            .into_iter()
            .collect()
    }
}
