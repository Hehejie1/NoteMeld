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
use serde_json::{json, Value};
use tokio_util::sync::CancellationToken;

use crate::{AgentEventSink, AgentMessage, TurnOutcome};

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
        }
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
            let completion = invoke_model(self.model.as_ref(), model_request, chunk_sink).await?;
            check_cancelled(&cancel)?;

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
                json!({
                    "content": content,
                    "tool_calls": completion.tool_calls,
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
                    total_tokens: Some(usage.total_tokens()),
                    ..UsageUpdatedPayload::default()
                }))
                .await;

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
                        arguments_summary: Some(Value::Object(call.arguments().clone())),
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
            let results =
                execute_tool_round(Arc::clone(&self.tools), calls, tool_context, progress_sink)
                    .await?;

            for (tool_call, result) in completion.tool_calls.iter().zip(&results) {
                events
                    .emit(AgentEvent::ToolCompleted(ToolCompletedPayload {
                        call_id: Some(result.call_id().to_owned()),
                        tool_name: Some(tool_call.tool_name.clone()),
                        status: Some("succeeded".to_owned()),
                        result_summary: Some(result.output.clone()),
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
                        content: Some(result.output),
                        ..MessageCompletedPayload::default()
                    }))
                    .await;
            }
            check_cancelled(&cancel)?;
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

fn check_cancelled(cancel: &CancellationToken) -> Result<(), AgentError> {
    if cancel.is_cancelled() {
        Err(AgentError::new(AgentErrorCode::Cancelled, "turn cancelled"))
    } else {
        Ok(())
    }
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
