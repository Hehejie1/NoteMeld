use std::collections::{HashMap, HashSet};
use std::sync::{Arc, Mutex};

use agent_events::{
    AgentError, AgentErrorCode, AgentEvent, AgentEventEnvelope, MessageCompletedPayload,
    MessageDeltaPayload, MessageStartedPayload, RequestId, SessionId, ToolCompletedPayload,
    ToolProgressPayload, ToolStartedPayload, TurnCancelledPayload, TurnFailedPayload, TurnId,
    TurnRequest, TurnStartedPayload, TurnStatus, TurnSucceededPayload, UsageUpdatedPayload,
    SCHEMA_VERSION,
};
use agent_model::{
    invoke_model, ModelChunk, ModelChunkSink, ModelDriver, ModelRequest, ModelUsage,
};
use agent_tools::{execute_tool_round, ToolCall, ToolContext, ToolDriver, ToolProgressSink};
use async_trait::async_trait;
use serde_json::{json, Value};
use tokio_util::sync::CancellationToken;
use uuid::Uuid;

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

#[derive(Debug, Clone)]
pub struct BeginTurnInput {
    pub session_id: SessionId,
    pub request_id: RequestId,
    pub payload: serde_json::Value,
}

#[derive(Debug, Clone)]
pub struct BeginTurnOutcome {
    pub turn_id: TurnId,
    pub replayed: bool,
    pub cached_outcome: Option<TurnOutcome>,
}

#[derive(Debug, Clone)]
pub struct ReplayQuery {
    pub turn_id: TurnId,
    pub sequence: u64,
}

#[derive(Debug, Clone)]
pub struct RecoverOutcome {
    pub interrupted: Vec<TurnId>,
}

#[async_trait]
pub trait AgentStore: Send + Sync {
    async fn begin_turn(&self, input: BeginTurnInput) -> Result<BeginTurnOutcome, AgentError>;
    async fn load_history(
        &self,
        session_id: &SessionId,
    ) -> Result<Vec<crate::AgentMessage>, AgentError>;
    async fn append_events(
        &self,
        turn_id: &TurnId,
        events: &[AgentEventEnvelope],
    ) -> Result<(), AgentError>;
    async fn checkpoint_messages(
        &self,
        turn_id: &TurnId,
        messages: &[crate::AgentMessage],
    ) -> Result<(), AgentError>;
    async fn finish_turn(
        &self,
        turn_id: &TurnId,
        outcome: &crate::TurnOutcome,
    ) -> Result<(), AgentError>;
    async fn replay_events(
        &self,
        query: ReplayQuery,
    ) -> Result<Vec<AgentEventEnvelope>, AgentError>;
    async fn recover_nonterminal(&self) -> Result<RecoverOutcome, AgentError>;
}

#[derive(Default)]
struct InMemoryAgentStore {
    inner: Mutex<InMemoryAgentStoreState>,
}

#[derive(Default)]
struct InMemoryAgentStoreState {
    turns: HashMap<TurnId, InMemoryTurnRecord>,
    by_request: HashMap<(SessionId, RequestId), TurnId>,
    by_session: HashSet<SessionId>,
    order: HashMap<SessionId, Vec<TurnId>>,
    active_turn: HashMap<SessionId, TurnId>,
    events: HashMap<TurnId, Vec<AgentEventEnvelope>>,
}

#[derive(Clone)]
struct InMemoryTurnRecord {
    request_payload: serde_json::Value,
    status: TurnStatus,
    messages: Vec<crate::AgentMessage>,
    usage: agent_model::ModelUsage,
    turn_count: usize,
    content: String,
    diagnostics: Vec<crate::AgentDiagnostic>,
    _request_id: RequestId,
    session_id: SessionId,
}

impl Default for InMemoryTurnRecord {
    fn default() -> Self {
        Self {
            request_payload: Value::Null,
            status: TurnStatus::Created,
            messages: Vec::new(),
    usage: ModelUsage::default(),
    turn_count: 0,
    content: String::new(),
    diagnostics: Vec::new(),
    _request_id: RequestId(String::new()),
    session_id: SessionId(String::new()),
        }
    }
}

#[async_trait]
impl AgentStore for InMemoryAgentStore {
    async fn begin_turn(&self, input: BeginTurnInput) -> Result<BeginTurnOutcome, AgentError> {
        let mut state = self
            .inner
            .lock()
            .map_err(|_| internal_error("agent store unavailable"))?;
        if input.session_id.0.is_empty() {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "session_id must not be empty",
            ));
        }

        if state
            .by_request
            .contains_key(&(input.session_id.clone(), input.request_id.clone()))
        {
            let existing = state
                .by_request
                .get(&(input.session_id.clone(), input.request_id.clone()))
                .expect("request index should reference an in-memory turn");
            let record = state
                .turns
                .get(existing)
                .ok_or_else(|| internal_error("turn index drift"))?;
            if record.request_payload == input.payload {
                let outcome = cached_outcome_for_turn(record);
                return Ok(BeginTurnOutcome {
                    turn_id: existing.clone(),
                    replayed: true,
                    cached_outcome: outcome,
                });
            }
            return Err(AgentError::new(
                AgentErrorCode::DuplicateRequest,
                "request_id already used with a different payload",
            ));
        }

        if let Some(active) = state.active_turn.get(&input.session_id) {
            let active_status = state
                .turns
                .get(active)
                .ok_or_else(|| internal_error("active turn missing"))?
                .status;
            if !matches!(
                active_status,
                TurnStatus::Succeeded
                    | TurnStatus::Failed
                    | TurnStatus::Cancelled
                    | TurnStatus::Interrupted
            ) {
                return Err(AgentError::new(
                    AgentErrorCode::SessionBusy,
                    "session already has an active turn",
                ));
            }
        }

        let turn_id = TurnId(Uuid::new_v4().to_string());
        let record = InMemoryTurnRecord {
            request_payload: input.payload,
            status: TurnStatus::Created,
            session_id: input.session_id.clone(),
            _request_id: input.request_id.clone(),
            ..InMemoryTurnRecord::default()
        };
        state.by_request.insert(
            (input.session_id.clone(), input.request_id),
            turn_id.clone(),
        );
        state.turns.insert(turn_id.clone(), record);
        state
            .active_turn
            .insert(input.session_id.clone(), turn_id.clone());
        state
            .order
            .entry(input.session_id.clone())
            .or_default()
            .push(turn_id.clone());
        state.by_session.insert(input.session_id);
        Ok(BeginTurnOutcome {
            turn_id,
            replayed: false,
            cached_outcome: None,
        })
    }

    async fn load_history(
        &self,
        session_id: &SessionId,
    ) -> Result<Vec<crate::AgentMessage>, AgentError> {
        let state = self
            .inner
            .lock()
            .map_err(|_| internal_error("agent store unavailable"))?;
        if !state.by_session.contains(session_id) {
            return Err(AgentError::new(
                AgentErrorCode::SessionNotFound,
                "session not found",
            ));
        }

        let mut history = Vec::new();
        if let Some(order) = state.order.get(session_id) {
            for turn_id in order {
                if let Some(record) = state.turns.get(turn_id) {
                    history.extend(record.messages.clone());
                }
            }
        }
        Ok(history)
    }

    async fn append_events(
        &self,
        turn_id: &TurnId,
        events: &[AgentEventEnvelope],
    ) -> Result<(), AgentError> {
        let mut state = self
            .inner
            .lock()
            .map_err(|_| internal_error("agent store unavailable"))?;
        if !state.turns.contains_key(turn_id) {
            return Err(AgentError::new(
                AgentErrorCode::TurnNotFound,
                "turn not found",
            ));
        }
        let entry = state.events.entry(turn_id.clone()).or_default();
        entry.extend_from_slice(events);
        entry.sort_by_key(|event| event.sequence);
        Ok(())
    }

    async fn checkpoint_messages(
        &self,
        turn_id: &TurnId,
        messages: &[crate::AgentMessage],
    ) -> Result<(), AgentError> {
        let mut state = self
            .inner
            .lock()
            .map_err(|_| internal_error("agent store unavailable"))?;
        let record = state
            .turns
            .get_mut(turn_id)
            .ok_or_else(|| AgentError::new(AgentErrorCode::TurnNotFound, "turn not found"))?;
        record.messages = messages.to_vec();
        Ok(())
    }

    async fn finish_turn(
        &self,
        turn_id: &TurnId,
        outcome: &crate::TurnOutcome,
    ) -> Result<(), AgentError> {
        let mut state = self
            .inner
            .lock()
            .map_err(|_| internal_error("agent store unavailable"))?;
        let record = state
            .turns
            .get_mut(turn_id)
            .ok_or_else(|| AgentError::new(AgentErrorCode::TurnNotFound, "turn not found"))?;
        let session_id = record.session_id.clone();
        record.status = outcome.status;
        record.messages = outcome.messages.clone();
        record.usage = outcome.usage;
        record.turn_count = outcome.turn_count;
        record.content = outcome.content.clone();
        record.diagnostics = outcome.diagnostics.clone();
        if matches!(
            outcome.status,
            TurnStatus::Succeeded
                | TurnStatus::Failed
                | TurnStatus::Cancelled
                | TurnStatus::Interrupted
        ) {
            state.active_turn.remove(&session_id);
        }
        Ok(())
    }

    async fn replay_events(
        &self,
        query: ReplayQuery,
    ) -> Result<Vec<AgentEventEnvelope>, AgentError> {
        let state = self
            .inner
            .lock()
            .map_err(|_| internal_error("agent store unavailable"))?;
        let events = state
            .events
            .get(&query.turn_id)
            .ok_or_else(|| internal_error("event stream unavailable"))?;
        Ok(events
            .iter()
            .filter(|event| event.sequence > query.sequence)
            .cloned()
            .collect())
    }

    async fn recover_nonterminal(&self) -> Result<RecoverOutcome, AgentError> {
        let state = self
            .inner
            .lock()
            .map_err(|_| internal_error("agent store unavailable"))?;
        let interrupted = state
            .turns
            .iter()
            .filter_map(|(turn_id, record)| {
                (!matches!(
                    record.status,
                    TurnStatus::Succeeded
                        | TurnStatus::Failed
                        | TurnStatus::Cancelled
                        | TurnStatus::Interrupted
                ))
                .then_some(turn_id.clone())
            })
            .collect();
        Ok(RecoverOutcome { interrupted })
    }
}

fn cached_outcome_for_turn(record: &InMemoryTurnRecord) -> Option<TurnOutcome> {
    if matches!(
        record.status,
        TurnStatus::Succeeded
            | TurnStatus::Failed
            | TurnStatus::Cancelled
            | TurnStatus::Interrupted
    ) {
        Some(TurnOutcome {
            status: record.status,
            content: record.content.clone(),
            messages: record.messages.clone(),
            usage: record.usage,
            turn_count: record.turn_count,
            diagnostics: record.diagnostics.clone(),
        })
    } else {
        None
    }
}

pub struct AgentRuntime {
    model: Arc<dyn ModelDriver>,
    tools: Arc<dyn ToolDriver>,
    store: Arc<dyn AgentStore>,
    config: AgentRuntimeConfig,
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
            store: Arc::new(InMemoryAgentStore::default()),
            config,
        }
    }

    pub fn with_store(
        model: Arc<dyn ModelDriver>,
        tools: Arc<dyn ToolDriver>,
        store: Arc<dyn AgentStore>,
        config: AgentRuntimeConfig,
    ) -> Self {
        Self {
            model,
            tools,
            store,
            config,
        }
    }

    pub async fn start_turn(
        &self,
        request: TurnRequest,
        cancel: CancellationToken,
        events: AgentEventSink,
    ) -> Result<TurnOutcome, AgentError> {
        validate_max_turns(self.config.max_turns)?;
        validate_request(&request)?;

        let payload = serde_json::to_value(&request)
            .map_err(|_| internal_error("failed to serialize request for start turn"))?;
        let begin = self
            .store
            .begin_turn(BeginTurnInput {
                session_id: request.session_id.clone(),
                request_id: request.request_id.clone(),
                payload,
            })
            .await?;
        if begin.replayed {
            if let Some(outcome) = begin.cached_outcome {
                return Ok(outcome);
            }
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "replay outcome was not durable yet",
            ));
        }

        let history = self.store.load_history(&request.session_id).await?;
        let turn_id = begin.turn_id.clone();
        let result = self
            .run_turn_inner(request, turn_id.clone(), history, cancel, events)
            .await;

        match &result {
            Ok(outcome) => {
                self.store
                    .checkpoint_messages(&turn_id, &outcome.messages)
                    .await
                    .map_err(|error| AgentError::new(error.code, error.message))?;
                self.store
                    .finish_turn(&turn_id, outcome)
                    .await
                    .map_err(|error| AgentError::new(error.code, error.message))?;
            }
            Err(error) => {
                let terminal = if error.code == AgentErrorCode::Cancelled {
                    TurnStatus::Cancelled
                } else {
                    TurnStatus::Failed
                };
                let terminal_outcome = TurnOutcome {
                    status: terminal,
                    content: String::new(),
                    messages: Vec::new(),
                    usage: ModelUsage::default(),
                    turn_count: 0,
                    diagnostics: vec![crate::AgentDiagnostic {
                        code: error.code,
                        message: error.message.clone(),
                    }],
                };
                self.store
                    .finish_turn(&turn_id, &terminal_outcome)
                    .await
                    .map_err(|store_error| {
                        AgentError::new(store_error.code, store_error.message)
                    })?;
            }
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
        let turn_id = TurnId(Uuid::new_v4().to_string());
        self.run_turn_inner(request, turn_id, history, cancel, events)
            .await
    }

    async fn run_turn_inner(
        &self,
        request: TurnRequest,
        turn_id: TurnId,
        messages: Vec<AgentMessage>,
        cancel: CancellationToken,
        events: AgentEventSink,
    ) -> Result<TurnOutcome, AgentError> {
        events
            .emit(AgentEvent::TurnStarted(TurnStartedPayload {
                status: Some(TurnStatus::Running),
                ..TurnStartedPayload::default()
            }))
            .await;

        let outcome = match self
            .run_turn_turn(request, turn_id, messages, cancel, events.clone())
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
                outcome
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
                return Err(error);
            }
        };

        Ok(outcome)
    }

    async fn run_turn_turn(
        &self,
        request: TurnRequest,
        turn_id: TurnId,
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
            let mut tool_context = ToolContext::new(request.session_id.clone(), turn_id.clone());
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

fn internal_error(message: impl Into<String>) -> AgentError {
    AgentError::new(AgentErrorCode::SdkInternalError, message)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc, Mutex,
    };

    use agent_model::ModelRequest;
    use serde_json::Map;
    use agent_tools::{
        ToolCall, ToolContext, ToolDescriptor, ToolDriver, ToolProgressSink, ToolResult,
    };
    use async_trait::async_trait;

    fn request_for(session: &str, request_id: &str, text: &str) -> TurnRequest {
        TurnRequest {
            schema_version: SCHEMA_VERSION.to_owned(),
            request_id: RequestId(request_id.to_owned()),
            session_id: SessionId(session.to_owned()),
            input: agent_events::TurnInput {
                text: text.to_owned(),
                ..agent_events::TurnInput::default()
            },
            model_override: None,
            approval_mode: agent_events::ApprovalMode::Interactive,
            extra: Map::new(),
        }
    }

    #[derive(Default)]
    struct NoTools;

    #[async_trait]
    impl ToolDriver for NoTools {
        async fn describe(&self, _names: &[String]) -> Result<Vec<ToolDescriptor>, AgentError> {
            Ok(vec![])
        }

        async fn invoke(
            &self,
            _call: ToolCall,
            _context: ToolContext,
            _sink: ToolProgressSink,
        ) -> Result<ToolResult, AgentError> {
            panic!("tools should not be invoked in session runtime tests");
        }
    }

    #[derive(Clone, Default)]
    struct RecordingModel {
        calls: Arc<AtomicUsize>,
        history_lengths: Arc<Mutex<Vec<usize>>>,
    }

    #[async_trait]
    impl agent_model::ModelDriver for RecordingModel {
        async fn stream(
            &self,
            request: ModelRequest,
            _sink: agent_model::ModelChunkSink,
        ) -> Result<agent_model::ModelCompletion, AgentError> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            self.history_lengths
                .lock()
                .unwrap()
                .push(request.messages.len());
            Ok(agent_model::ModelCompletion {
                content: "ok".to_owned(),
                tool_calls: vec![],
                finish_reason: "stop".to_owned(),
                usage: ModelUsage::default(),
            })
        }
    }

    #[tokio::test]
    async fn start_turn_uses_durable_replay_for_duplicate_request_id() {
        let model = Arc::new(RecordingModel::default());
        let model_driver: Arc<dyn agent_model::ModelDriver> = model.clone();
        let runtime = AgentRuntime::new(
            model_driver,
            Arc::new(NoTools),
            AgentRuntimeConfig::default(),
        );
        let first = request_for("s-replay", "33333333-3333-3333-3333-333333333333", "first question");
        let second = request_for("s-replay", "44444444-4444-4444-4444-444444444444", "second question");

        let outcome1 = runtime
            .start_turn(
                first.clone(),
                CancellationToken::new(),
                AgentEventSink::discard(),
            )
            .await
            .expect("first run should succeed");
        assert_eq!(outcome1.content, "ok");
        assert_eq!(model.calls.load(Ordering::SeqCst), 1);

        let outcome2 = runtime
            .start_turn(
                second.clone(),
                CancellationToken::new(),
                AgentEventSink::discard(),
            )
            .await
            .expect("second run should succeed and see first turn history");
        assert_eq!(outcome2.content, "ok");
        let history_lengths = model.history_lengths.lock().unwrap().clone();
        assert_eq!(history_lengths[0], 1);
        assert_eq!(history_lengths[1], 3);

        let replay = runtime
            .start_turn(second, CancellationToken::new(), AgentEventSink::discard())
            .await
            .expect("duplicate request should replay without re-running");
        assert_eq!(model.calls.load(Ordering::SeqCst), 2);
        assert_eq!(replay.content, outcome2.content);

        let duplicate_payload_error = runtime
            .start_turn(
                request_for(
                    "s-replay",
                    "44444444-4444-4444-4444-444444444444",
                    "changed question",
                ),
                CancellationToken::new(),
                AgentEventSink::discard(),
            )
            .await
            .expect_err("same request_id with different payload must fail");
        assert_eq!(
            duplicate_payload_error.code,
            AgentErrorCode::DuplicateRequest
        );
        assert_eq!(model.calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn start_turn_blocks_when_session_has_active_turn() {
        let model = Arc::new(RecordingModel::default());
        let model_driver: Arc<dyn agent_model::ModelDriver> = model.clone();
        let store: Arc<dyn AgentStore> = Arc::new(InMemoryAgentStore::default());
        let runtime = AgentRuntime::with_store(
            model_driver,
            Arc::new(NoTools),
            Arc::clone(&store),
            AgentRuntimeConfig::default(),
        );
        let request_a = request_for("s-busy", "11111111-1111-1111-1111-111111111111", "blocked");
        let request_b = request_for("s-busy", "22222222-2222-2222-2222-222222222222", "still blocked");
        let busy_payload = serde_json::to_value(request_a.clone())
            .expect("request should serialize for active turn");
        store
            .begin_turn(BeginTurnInput {
                session_id: request_a.session_id.clone(),
                request_id: request_a.request_id.clone(),
                payload: busy_payload,
            })
            .await
            .expect("pre-seed active turn should succeed");

        let error = runtime
            .start_turn(
                request_b,
                CancellationToken::new(),
                AgentEventSink::discard(),
            )
            .await
            .expect_err("concurrent request should be rejected");
        assert_eq!(error.code, AgentErrorCode::SessionBusy);
        assert_eq!(model.calls.load(Ordering::SeqCst), 0);
    }

    #[derive(Default)]
    struct RejectingStore;

    #[async_trait]
    impl AgentStore for RejectingStore {
        async fn begin_turn(&self, _input: BeginTurnInput) -> Result<BeginTurnOutcome, AgentError> {
            Err(AgentError::new(
                AgentErrorCode::SdkInternalError,
                "store failed",
            ))
        }

        async fn load_history(
            &self,
            _session_id: &SessionId,
        ) -> Result<Vec<crate::AgentMessage>, AgentError> {
            Err(AgentError::new(
                AgentErrorCode::SessionNotFound,
                "unreachable",
            ))
        }

        async fn append_events(
            &self,
            _turn_id: &TurnId,
            _events: &[AgentEventEnvelope],
        ) -> Result<(), AgentError> {
            Err(AgentError::new(
                AgentErrorCode::SdkInternalError,
                "unreachable",
            ))
        }

        async fn checkpoint_messages(
            &self,
            _turn_id: &TurnId,
            _messages: &[crate::AgentMessage],
        ) -> Result<(), AgentError> {
            Err(AgentError::new(
                AgentErrorCode::SdkInternalError,
                "unreachable",
            ))
        }

        async fn finish_turn(
            &self,
            _turn_id: &TurnId,
            _outcome: &crate::TurnOutcome,
        ) -> Result<(), AgentError> {
            Err(AgentError::new(
                AgentErrorCode::SdkInternalError,
                "unreachable",
            ))
        }

        async fn replay_events(
            &self,
            _query: ReplayQuery,
        ) -> Result<Vec<AgentEventEnvelope>, AgentError> {
            Err(AgentError::new(
                AgentErrorCode::SdkInternalError,
                "unreachable",
            ))
        }

        async fn recover_nonterminal(&self) -> Result<RecoverOutcome, AgentError> {
            Ok(RecoverOutcome {
                interrupted: Vec::new(),
            })
        }
    }

    #[tokio::test]
    async fn start_turn_short_circuits_on_store_begin_error() {
        let model = Arc::new(RecordingModel::default());
        let model_driver: Arc<dyn agent_model::ModelDriver> = model.clone();
        let runtime = AgentRuntime::with_store(
            model_driver,
            Arc::new(NoTools),
            Arc::new(RejectingStore),
            AgentRuntimeConfig::default(),
        );
        let error = runtime
            .start_turn(
            request_for("s-store", "66666666-6666-6666-6666-666666666666", "should fail"),
                CancellationToken::new(),
                AgentEventSink::discard(),
            )
            .await
            .expect_err("store begin failure should fail fast");
        assert_eq!(error.code, AgentErrorCode::SdkInternalError);
        assert_eq!(model.calls.load(Ordering::SeqCst), 0);
    }
}
