use std::sync::{Arc, Mutex};

use agent_events::{
    AgentError, AgentErrorCode, AgentEvent, MessageCompletedPayload, MessageDeltaPayload,
    MessageStartedPayload, ToolCompletedPayload, ToolProgressPayload, ToolStartedPayload,
    TurnCancelledPayload, TurnFailedPayload, TurnId, TurnRequest, TurnStartedPayload, TurnStatus,
    TurnSucceededPayload, UsageUpdatedPayload, SCHEMA_VERSION,
};
use agent_model::{
    invoke_model, ModelChunk, ModelChunkSink, ModelDriver, ModelRequest, ModelUsage,
};
use agent_tools::{execute_tool_round, ToolCall, ToolContext, ToolDriver, ToolProgressSink};
use agent_tools::ToolDescriptor;
use agent_capabilities::{CapabilityRegistry, DisclosureLevel};
use agent_storage::AgentStore;
use async_trait::async_trait;
use serde_json::{json, Value};
use tokio_util::sync::CancellationToken;

use crate::{AgentEventSink, AgentMessage, TurnOutcome};

const MAX_SUMMARY_DEPTH: usize = 4;
const MAX_SUMMARY_COLLECTION_ITEMS: usize = 16;
const MAX_SUMMARY_TOTAL_ITEMS: usize = 64;
const MAX_SUMMARY_STRING_CHARS: usize = 256;
const MAX_SUMMARY_KEY_CHARS: usize = 128;
const MAX_SUMMARY_SERIALIZED_BYTES: usize = 4096;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct AgentRuntimeConfig {
    pub max_turns: usize,
}

impl Default for AgentRuntimeConfig {
    fn default() -> Self {
        Self { max_turns: 16 }
    }
}

pub struct AgentRuntime {
    model: Arc<dyn ModelDriver>,
    tools: Arc<dyn ToolDriver>,
    config: AgentRuntimeConfig,
    tool_descriptors: Vec<ToolDescriptor>,
    capabilities: Option<Arc<CapabilityRegistry>>,
}

impl AgentRuntime {
    pub fn new(
        model: Arc<dyn ModelDriver>,
        tools: Arc<dyn ToolDriver>,
        config: AgentRuntimeConfig,
    ) -> Self {
        Self {
            model,
            tools,
            config,
            tool_descriptors: Vec::new(),
            capabilities: None,
        }
    }

    pub fn with_tool_descriptors(mut self, descriptors: Vec<ToolDescriptor>) -> Self {
        self.tool_descriptors = descriptors;
        self
    }

    pub fn with_capabilities(mut self, registry: Arc<CapabilityRegistry>) -> Self {
        self.capabilities = Some(registry);
        self
    }

    /// Durable entry point. The Store owns turn identity, idempotency and
    /// history loading; the legacy `run_turn` remains available for callers
    /// that explicitly provide an in-memory history.
    pub async fn start_turn<S: AgentStore + ?Sized + 'static>(
        &self,
        store: Arc<S>,
        request: TurnRequest,
        cancel: CancellationToken,
        events: AgentEventSink,
    ) -> Result<TurnOutcome, AgentError> {
        let payload = serde_json::to_value(&request).map_err(|_| AgentError::new(AgentErrorCode::InvalidInput, "turn request cannot be serialized"))?;
        let started = store.begin_turn(request.session_id.clone(), request.request_id.clone(), payload).await?;
        let history_values = store.load_history(&request.session_id).await?;
        let mut history = Vec::with_capacity(history_values.len());
        for value in history_values {
            history.push(serde_json::from_value(value).map_err(|_| AgentError::new(AgentErrorCode::InvalidInput, "stored message is invalid"))?);
        }
        if started.replayed && matches!(started.turn.status, TurnStatus::Succeeded | TurnStatus::Failed | TurnStatus::Cancelled | TurnStatus::Interrupted) {
            let content = history.iter().rev().find(|m: &&AgentMessage| m.role == "assistant").and_then(|m| m.content.as_str()).unwrap_or_default().to_owned();
            return Ok(TurnOutcome { status: started.turn.status, content, messages: history, usage: ModelUsage::default(), turn_count: 0, diagnostics: Vec::new() });
        }
        let result = self.run_turn(request.clone(), history, cancel, events).await;
        match &result {
            Ok(outcome) => {
                for message in &outcome.messages { let _ = store.append_message(&request.session_id, &started.turn.id, serde_json::to_value(message).unwrap_or(Value::Null)).await; }
                let _ = store.finish_turn(&started.turn.id, outcome.status, None).await;
            }
            Err(error) => { let status = if error.code == AgentErrorCode::Cancelled { TurnStatus::Cancelled } else { TurnStatus::Failed }; let _ = store.finish_turn(&started.turn.id, status, Some(error.clone())).await; }
        }
        result
    }

    pub async fn run_turn(
        &self,
        request: TurnRequest,
        history: Vec<AgentMessage>,
        cancel: CancellationToken,
        events: AgentEventSink,
    ) -> Result<TurnOutcome, AgentError> {
        events
            .emit(AgentEvent::TurnStarted(TurnStartedPayload {
                status: Some(TurnStatus::Running),
                ..TurnStartedPayload::default()
            }))
            .await;

        match self
            .run_turn_inner(request, history, cancel, events.clone())
            .await
        {
            Ok(mut outcome) => {
                events
                    .emit(AgentEvent::TurnSucceeded(TurnSucceededPayload {
                        result: Some(json!({
                            "content": outcome.content,
                            "turn_count": outcome.turn_count,
                        })),
                        ..TurnSucceededPayload::default()
                    }))
                    .await;
                outcome.diagnostics = events.diagnostics();
                Ok(outcome)
            }
            Err(error) => {
                let terminal = if error.code == AgentErrorCode::Cancelled {
                    AgentEvent::TurnCancelled(TurnCancelledPayload {
                        reason: Some(error.message.clone()),
                        ..TurnCancelledPayload::default()
                    })
                } else {
                    AgentEvent::TurnFailed(TurnFailedPayload {
                        error: error.clone(),
                        ..TurnFailedPayload::default()
                    })
                };
                events.emit(terminal).await;
                Err(error)
            }
        }
    }

    async fn run_turn_inner(
        &self,
        request: TurnRequest,
        mut messages: Vec<AgentMessage>,
        cancel: CancellationToken,
        events: AgentEventSink,
    ) -> Result<TurnOutcome, AgentError> {
        validate_max_turns(self.config.max_turns)?;
        validate_request(&request)?;
        messages.push(AgentMessage::user(input_content(&request)));

        let mut usage = ModelUsage::default();
        let mut turn_count = 0usize;
        loop {
            check_cancelled(&cancel)?;
            if turn_count >= self.config.max_turns {
                return Err(max_turns_error(self.config.max_turns));
            }
            turn_count += 1;

            let message_id = format!("assistant-{turn_count}");
            events
                .emit(AgentEvent::MessageStarted(MessageStartedPayload {
                    message_id: Some(message_id.clone()),
                    role: Some("assistant".to_owned()),
                    ..MessageStartedPayload::default()
                }))
                .await;

            check_cancelled(&cancel)?;
            let accumulated = Arc::new(Mutex::new(String::new()));
            let chunk_text = Arc::clone(&accumulated);
            let chunk_events = events.clone();
            let chunk_message_id = message_id.clone();
            let chunk_sink = ModelChunkSink::new(move |chunk| {
                let chunk_text = Arc::clone(&chunk_text);
                let chunk_events = chunk_events.clone();
                let chunk_message_id = chunk_message_id.clone();
                async move {
                    let ModelChunk::ContentDelta { delta } = chunk;
                    chunk_text.lock().unwrap().push_str(&delta);
                    chunk_events
                        .emit(AgentEvent::MessageDelta(MessageDeltaPayload {
                            message_id: Some(chunk_message_id),
                            delta: Some(delta),
                            ..MessageDeltaPayload::default()
                        }))
                        .await;
                    Ok(())
                }
            });
            let mut model_request = ModelRequest::new(
                messages
                    .iter()
                    .map(AgentMessage::as_model_message)
                    .collect(),
            );
            model_request.tools = self.tool_descriptors.clone();
            if let Some(registry) = &self.capabilities {
                model_request.tools.extend(meta_tool_descriptors(registry));
            }
            model_request.cancellation = cancel.clone();
            let completion_result =
                invoke_model(self.model.as_ref(), model_request, chunk_sink).await;
            check_cancelled(&cancel)?;
            let completion = completion_result?;

            add_usage(&mut usage, completion.usage);
            let streamed_content = accumulated.lock().unwrap().clone();
            let content = if streamed_content.is_empty() {
                completion.content.clone()
            } else {
                streamed_content
            };
            let completed_content = if completion.tool_calls.is_empty() {
                Value::String(content.clone())
            } else {
                let tool_calls = completion
                    .tool_calls
                    .iter()
                    .map(|call| {
                        json!({
                            "call_id": call.call_id,
                            "tool_name": call.tool_name,
                            "arguments_summary": safe_event_summary(&call.arguments),
                        })
                    })
                    .collect::<Vec<_>>();
                json!({
                    "content": content,
                    "tool_calls": tool_calls,
                })
            };
            messages.push(AgentMessage::assistant(
                Value::String(content.clone()),
                completion.tool_calls.clone(),
            ));
            events
                .emit(AgentEvent::MessageCompleted(MessageCompletedPayload {
                    message_id: Some(message_id),
                    role: Some("assistant".to_owned()),
                    content: Some(completed_content),
                    ..MessageCompletedPayload::default()
                }))
                .await;
            events
                .emit(AgentEvent::UsageUpdated(UsageUpdatedPayload {
                    input_tokens: Some(usage.input_tokens),
                    output_tokens: Some(usage.output_tokens),
                    total_tokens: Some(saturating_total_tokens(usage)),
                    ..UsageUpdatedPayload::default()
                }))
                .await;
            check_cancelled(&cancel)?;

            if completion.tool_calls.is_empty() {
                return Ok(TurnOutcome {
                    status: TurnStatus::Succeeded,
                    content,
                    messages,
                    usage,
                    turn_count,
                    diagnostics: Vec::new(),
                });
            }

            let calls = completion
                .tool_calls
                .iter()
                .map(|call| {
                    ToolCall::try_new(
                        call.call_id.clone(),
                        call.tool_name.clone(),
                        call.arguments.clone(),
                        false,
                    )
                })
                .collect::<Result<Vec<_>, _>>()?;
            for call in &calls {
                events
                    .emit(AgentEvent::ToolStarted(ToolStartedPayload {
                        call_id: Some(call.id().to_owned()),
                        tool_name: Some(call.name().to_owned()),
                        arguments_summary: Some(safe_event_summary(&Value::Object(
                            call.arguments().clone(),
                        ))),
                        ..ToolStartedPayload::default()
                    }))
                    .await;
            }

            check_cancelled(&cancel)?;
            let progress_events = events.clone();
            let progress_sink = ToolProgressSink::new(move |progress| {
                let progress_events = progress_events.clone();
                async move {
                    progress_events
                        .emit(AgentEvent::ToolProgress(ToolProgressPayload {
                            call_id: Some(progress.call_id),
                            message: Some(progress.message),
                            progress: progress.progress,
                            ..ToolProgressPayload::default()
                        }))
                        .await;
                    Ok(())
                }
            });
            let mut tool_context = ToolContext::new(
                request.session_id.clone(),
                // Session coordination allocates the durable TurnId in Task 5. Until
                // then request_id is the valid UUID correlation available at this API.
                TurnId(request.request_id.0.clone()),
            );
            tool_context.cancellation = cancel.clone();
            let tool_round_result =
                execute_tool_round(Arc::clone(&self.tools), calls, tool_context, progress_sink)
                    .await;
            let cancellation_error = cancellation_error(&cancel);
            let results = match tool_round_result {
                Ok(results) => results,
                Err(error) => return Err(cancellation_error.unwrap_or(error)),
            };

            for (tool_call, result) in completion.tool_calls.iter().zip(&results) {
                events
                    .emit(AgentEvent::ToolCompleted(ToolCompletedPayload {
                        call_id: Some(result.call_id().to_owned()),
                        tool_name: Some(tool_call.tool_name.clone()),
                        status: Some("succeeded".to_owned()),
                        result_summary: Some(safe_event_summary(&result.output)),
                        ..ToolCompletedPayload::default()
                    }))
                    .await;
            }
            for result in results {
                let tool_message_id = format!("tool-{}", result.call_id());
                events
                    .emit(AgentEvent::MessageStarted(MessageStartedPayload {
                        message_id: Some(tool_message_id.clone()),
                        role: Some("tool".to_owned()),
                        ..MessageStartedPayload::default()
                    }))
                    .await;
                messages.push(AgentMessage::tool_result(
                    result.call_id(),
                    result.output.clone(),
                ));
                events
                    .emit(AgentEvent::MessageCompleted(MessageCompletedPayload {
                        message_id: Some(tool_message_id),
                        role: Some("tool".to_owned()),
                        content: Some(safe_event_summary(&result.output)),
                        ..MessageCompletedPayload::default()
                    }))
                    .await;
            }
            if let Some(error) = cancellation_error {
                return Err(error);
            }
        }
    }
}

fn meta_tool_descriptors(registry: &CapabilityRegistry) -> Vec<ToolDescriptor> {
    let _ = registry;
    vec![
        ToolDescriptor { name: "capability_discover".to_owned(), description: "List available capabilities at L0/L1".to_owned(), input_schema: json!({"type":"object","properties":{"level":{"enum":["L0","L1"]}}}) },
        ToolDescriptor { name: "capability_describe".to_owned(), description: "Describe one capability schema at L2".to_owned(), input_schema: json!({"type":"object","required":["capability_id"]}) },
        ToolDescriptor { name: "capability_invoke".to_owned(), description: "Invoke an allowed capability at L3".to_owned(), input_schema: json!({"type":"object","required":["capability_id","arguments"]}) },
    ]
}

fn validate_request(request: &TurnRequest) -> Result<(), AgentError> {
    if request.schema_version != SCHEMA_VERSION {
        return Err(AgentError::new(
            AgentErrorCode::AgentSchemaMismatch,
            "unsupported agent schema version",
        ));
    }
    if request.input.text.trim().is_empty()
        && request.input.attachments.is_empty()
        && request.input.context_refs.is_empty()
    {
        return Err(AgentError::new(
            AgentErrorCode::InvalidInput,
            "turn input must not be empty",
        ));
    }
    Ok(())
}

fn validate_max_turns(max_turns: usize) -> Result<(), AgentError> {
    if max_turns > 0 {
        return Ok(());
    }
    let mut error = AgentError::new(
        AgentErrorCode::InvalidInput,
        "max_turns must be greater than zero",
    );
    error.details.insert(
        "reason".to_owned(),
        Value::String("max_turns_must_be_positive".to_owned()),
    );
    error
        .details
        .insert("max_turns".to_owned(), json!(max_turns));
    Err(error)
}

fn input_content(request: &TurnRequest) -> Value {
    if request.input.attachments.is_empty() && request.input.context_refs.is_empty() {
        Value::String(request.input.text.clone())
    } else {
        json!({
            "text": request.input.text,
            "attachments": request.input.attachments,
            "context_refs": request.input.context_refs,
        })
    }
}

fn add_usage(total: &mut ModelUsage, next: ModelUsage) {
    total.input_tokens = total.input_tokens.saturating_add(next.input_tokens);
    total.output_tokens = total.output_tokens.saturating_add(next.output_tokens);
    total.cache_read_tokens = total
        .cache_read_tokens
        .saturating_add(next.cache_read_tokens);
    total.cache_write_tokens = total
        .cache_write_tokens
        .saturating_add(next.cache_write_tokens);
}

fn saturating_total_tokens(usage: ModelUsage) -> u64 {
    usage.input_tokens.saturating_add(usage.output_tokens)
}

fn safe_event_summary(value: &Value) -> Value {
    let mut remaining_items = MAX_SUMMARY_TOTAL_ITEMS;
    let summary = summarize_value(value, 0, &mut remaining_items);
    match serde_json::to_vec(&summary) {
        Ok(serialized) if serialized.len() <= MAX_SUMMARY_SERIALIZED_BYTES => summary,
        _ => json!({
            "truncated": true,
            "reason": "size_limit",
            "value_type": value_type(value),
        }),
    }
}

fn summarize_value(value: &Value, depth: usize, remaining_items: &mut usize) -> Value {
    match value {
        Value::Null | Value::Bool(_) | Value::Number(_) => value.clone(),
        Value::String(text) => Value::String(truncate_chars(text, MAX_SUMMARY_STRING_CHARS)),
        Value::Array(items) => {
            if depth >= MAX_SUMMARY_DEPTH {
                return truncation_marker("depth_limit", Some(items.len()));
            }
            let mut summary = Vec::new();
            let mut consumed = 0usize;
            for item in items.iter().take(MAX_SUMMARY_COLLECTION_ITEMS) {
                if *remaining_items == 0 {
                    break;
                }
                *remaining_items -= 1;
                consumed += 1;
                summary.push(summarize_value(item, depth + 1, remaining_items));
            }
            if consumed < items.len() {
                summary.push(truncation_marker(
                    "item_limit",
                    Some(items.len() - consumed),
                ));
            }
            Value::Array(summary)
        }
        Value::Object(fields) => {
            if depth >= MAX_SUMMARY_DEPTH {
                return truncation_marker("depth_limit", Some(fields.len()));
            }
            let mut summary = serde_json::Map::new();
            let mut consumed = 0usize;
            for (key, field) in fields.iter().take(MAX_SUMMARY_COLLECTION_ITEMS) {
                if *remaining_items == 0 {
                    break;
                }
                *remaining_items -= 1;
                let safe_key =
                    truncate_chars(&format!("field_{consumed:03}"), MAX_SUMMARY_KEY_CHARS);
                consumed += 1;
                let safe_value = if is_secret_key(key) {
                    Value::String("[REDACTED]".to_owned())
                } else {
                    summarize_value(field, depth + 1, remaining_items)
                };
                summary.insert(safe_key, safe_value);
            }
            if consumed < fields.len() {
                summary.insert(
                    "__notemeld_truncated__".to_owned(),
                    truncation_marker("item_limit", Some(fields.len() - consumed)),
                );
            }
            Value::Object(summary)
        }
    }
}

fn is_secret_key(key: &str) -> bool {
    matches!(
        key.to_ascii_lowercase().as_str(),
        "api_key" | "authorization" | "cookie" | "token" | "secret" | "password"
    )
}

fn truncate_chars(value: &str, max_chars: usize) -> String {
    let mut chars = value.chars();
    let prefix = chars.by_ref().take(max_chars).collect::<String>();
    if chars.next().is_some() {
        format!("{prefix}…[truncated]")
    } else {
        prefix
    }
}

fn truncation_marker(reason: &str, omitted_items: Option<usize>) -> Value {
    json!({
        "truncated": true,
        "reason": reason,
        "omitted_items": omitted_items,
    })
}

fn value_type(value: &Value) -> &'static str {
    match value {
        Value::Null => "null",
        Value::Bool(_) => "boolean",
        Value::Number(_) => "number",
        Value::String(_) => "string",
        Value::Array(_) => "array",
        Value::Object(_) => "object",
    }
}

fn check_cancelled(cancel: &CancellationToken) -> Result<(), AgentError> {
    cancellation_error(cancel).map_or(Ok(()), Err)
}

fn cancellation_error(cancel: &CancellationToken) -> Option<AgentError> {
    cancel
        .is_cancelled()
        .then(|| AgentError::new(AgentErrorCode::Cancelled, "turn cancelled"))
}

fn max_turns_error(max_turns: usize) -> AgentError {
    let mut error = AgentError::new(
        AgentErrorCode::SdkInternalError,
        "maximum agent turns reached",
    );
    error.details.insert(
        "reason".to_owned(),
        Value::String("max_turns_reached".to_owned()),
    );
    error
        .details
        .insert("max_turns".to_owned(), json!(max_turns));
    error
}
