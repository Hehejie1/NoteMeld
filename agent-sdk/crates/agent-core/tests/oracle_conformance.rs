use std::{
    collections::VecDeque,
    fs,
    path::PathBuf,
    sync::{Arc, Mutex},
};

use agent_core::{AgentEventSink, AgentMessage, AgentRuntime, AgentRuntimeConfig, TurnOutcome};
use agent_events::{
    AgentError, AgentEvent, ApprovalMode, RequestId, SessionId, TurnInput, TurnRequest,
    SCHEMA_VERSION,
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

#[derive(Clone)]
struct ModelStep {
    chunks: Vec<&'static str>,
    content: &'static str,
    tool_calls: Vec<ModelToolCall>,
    usage: ModelUsage,
}

struct ScriptedModel {
    steps: Mutex<VecDeque<ModelStep>>,
}

#[async_trait]
impl ModelDriver for ScriptedModel {
    async fn stream(
        &self,
        _request: ModelRequest,
        sink: ModelChunkSink,
    ) -> Result<ModelCompletion, AgentError> {
        let step = self
            .steps
            .lock()
            .unwrap()
            .pop_front()
            .expect("fixture model must have another scripted response");
        for delta in step.chunks {
            sink.emit(ModelChunk::ContentDelta {
                delta: delta.to_owned(),
            })
            .await?;
        }
        Ok(ModelCompletion {
            content: step.content.to_owned(),
            tool_calls: step.tool_calls,
            finish_reason: "stop".to_owned(),
            usage: step.usage,
        })
    }
}

#[derive(Default)]
struct FixtureTools {
    wait_started: Option<mpsc::UnboundedSender<()>>,
}

#[async_trait]
impl ToolDriver for FixtureTools {
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
        context: ToolContext,
        _sink: ToolProgressSink,
    ) -> Result<ToolResult, AgentError> {
        let output = match call.name() {
            "slow" => {
                json!({"content": [{"type": "text", "text": "slow result"}], "details": {"name": "slow"}})
            }
            "fast" => {
                json!({"content": [{"type": "text", "text": "fast result"}], "details": {"name": "fast"}})
            }
            "hold" => {
                json!({"content": [{"type": "text", "text": "corrected result"}], "details": {}})
            }
            "repeat" => {
                json!({"content": [{"type": "text", "text": format!("completed {}", call.id())}], "details": {}})
            }
            "wait" => {
                if let Some(started) = &self.wait_started {
                    let _ = started.send(());
                }
                context.cancellation.cancelled().await;
                json!({"content": [{"type": "text", "text": "tool observed abort"}], "details": {"aborted": true}})
            }
            other => panic!("unexpected fixture tool: {other}"),
        };
        Ok(ToolResult::new(call.id(), output))
    }
}

fn tool_call(call_id: &str, tool_name: &str, arguments: Value) -> ModelToolCall {
    ModelToolCall {
        call_id: call_id.to_owned(),
        tool_name: tool_name.to_owned(),
        arguments,
    }
}

fn step(
    chunks: Vec<&'static str>,
    content: &'static str,
    tool_calls: Vec<ModelToolCall>,
) -> ModelStep {
    ModelStep {
        chunks,
        content,
        tool_calls,
        usage: ModelUsage {
            input_tokens: 10,
            output_tokens: 2,
            cache_read_tokens: 1,
            cache_write_tokens: 0,
        },
    }
}

fn script(scenario: &str) -> Vec<ModelStep> {
    match scenario {
        "simple_answer" => vec![step(
            vec!["orac", "le a", "nswe", "r"],
            "oracle answer",
            vec![],
        )],
        "parallel_tools" => vec![
            step(
                vec![],
                "",
                vec![
                    tool_call("slow-call", "slow", json!({})),
                    tool_call("fast-call", "fast", json!({})),
                ],
            ),
            step(
                vec!["para", "llel", " com", "plet", "e"],
                "parallel complete",
                vec![],
            ),
        ],
        "abort" => vec![step(
            vec![],
            "",
            vec![tool_call("abort-call", "wait", json!({}))],
        )],
        "steer" => vec![
            step(
                vec![],
                "",
                vec![tool_call(
                    "steer-call",
                    "hold",
                    json!({"query": "original"}),
                )],
            ),
            step(
                vec!["stee", "r ac", "know", "ledg", "ed"],
                "steer acknowledged",
                vec![],
            ),
        ],
        "max_turns" => (1..=3)
            .map(|turn| {
                step(
                    vec![],
                    "",
                    vec![tool_call(&format!("max-call-{turn}"), "repeat", json!({}))],
                )
            })
            .collect(),
        other => panic!("unknown scenario: {other}"),
    }
}

fn request(scenario: &str) -> TurnRequest {
    let text = match scenario {
        "simple_answer" => "answer simply",
        "parallel_tools" => "run tools in parallel",
        "abort" => "begin cancellable work",
        "steer" => "start original query",
        "max_turns" => "continue until the turn limit",
        other => panic!("unknown scenario: {other}"),
    };
    TurnRequest {
        schema_version: SCHEMA_VERSION.to_owned(),
        request_id: RequestId("00000000-0000-4000-8000-000000000001".to_owned()),
        session_id: SessionId(format!("oracle-session-{scenario}")),
        input: TurnInput {
            text: text.to_owned(),
            ..TurnInput::default()
        },
        model_override: None,
        approval_mode: ApprovalMode::Interactive,
        extra: Default::default(),
    }
}

fn fixture_path(scenario: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../fixtures/conformance")
        .join(format!("{scenario}.jsonl"))
}

fn expected_semantics(scenario: &str) -> Vec<String> {
    fs::read_to_string(fixture_path(scenario))
        .expect("checked-in Python oracle fixture must exist")
        .lines()
        .filter_map(|line| {
            let row: Value = serde_json::from_str(line).expect("fixture row must be JSON");
            let payload = &row["payload"];
            match row["type"].as_str().unwrap() {
                "agent_start" => Some("turn.started".to_owned()),
                "message_start" => Some(format!(
                    "message.started:{}",
                    normalize_role(payload["role"].as_str().unwrap())
                )),
                "message_update" => Some(format!(
                    "message.delta:{}",
                    payload["delta"].as_str().unwrap()
                )),
                "message_end" => Some(format!(
                    "message.completed:{}",
                    normalize_role(payload["role"].as_str().unwrap())
                )),
                "tool_execution_start" => Some(format!(
                    "tool.started:{}:{}",
                    payload["call_id"].as_str().unwrap(),
                    payload["tool_name"].as_str().unwrap()
                )),
                // Completion ordering differs legitimately across schedulers; call/result
                // ordering is asserted independently from TurnOutcome below.
                "tool_execution_end" => Some("tool.completed".to_owned()),
                "agent_end" => Some(match payload["final_state"]["status"].as_str().unwrap() {
                    "completed" => "turn.succeeded".to_owned(),
                    "aborted" => "turn.cancelled".to_owned(),
                    "failed" => "turn.failed".to_owned(),
                    status => panic!("unexpected oracle terminal status: {status}"),
                }),
                "turn_start" | "turn_end" => None,
                event_type => panic!("unexpected oracle event: {event_type}"),
            }
        })
        .collect()
}

fn normalize_role(role: &str) -> &str {
    if role == "toolResult" {
        "tool"
    } else {
        role
    }
}

fn actual_semantics(events: &[AgentEvent]) -> Vec<String> {
    events
        .iter()
        .filter_map(|event| match event {
            AgentEvent::TurnStarted(_) => Some("turn.started".to_owned()),
            AgentEvent::MessageStarted(payload) => Some(format!(
                "message.started:{}",
                normalize_role(payload.role.as_deref().unwrap())
            )),
            AgentEvent::MessageDelta(payload) => Some(format!(
                "message.delta:{}",
                payload.delta.as_deref().unwrap()
            )),
            AgentEvent::MessageCompleted(payload) => Some(format!(
                "message.completed:{}",
                normalize_role(payload.role.as_deref().unwrap())
            )),
            AgentEvent::ToolStarted(payload) => Some(format!(
                "tool.started:{}:{}",
                payload.call_id.as_deref().unwrap(),
                payload.tool_name.as_deref().unwrap()
            )),
            AgentEvent::ToolCompleted(_) => Some("tool.completed".to_owned()),
            AgentEvent::TurnSucceeded(_) => Some("turn.succeeded".to_owned()),
            AgentEvent::TurnFailed(_) => Some("turn.failed".to_owned()),
            AgentEvent::TurnCancelled(_) => Some("turn.cancelled".to_owned()),
            AgentEvent::UsageUpdated(_) | AgentEvent::ToolProgress(_) => None,
            other => panic!("unexpected Rust event in oracle trace: {other:?}"),
        })
        .collect()
}

fn tool_result_ids(outcome: &TurnOutcome) -> Vec<&str> {
    outcome
        .messages
        .iter()
        .filter(|message| message.role == "tool")
        .filter_map(|message| message.tool_call_id.as_deref())
        .collect()
}

#[tokio::test]
async fn five_python_oracles_match_the_canonical_rust_loop() {
    for scenario in ["simple_answer", "parallel_tools", "steer", "max_turns"] {
        let observed = Arc::new(Mutex::new(Vec::new()));
        let observer = Arc::clone(&observed);
        let sink = AgentEventSink::new(move |event| {
            observer.lock().unwrap().push(event);
            async { Ok(()) }
        });
        let runtime = AgentRuntime::new(
            Arc::new(ScriptedModel {
                steps: Mutex::new(script(scenario).into()),
            }),
            Arc::new(FixtureTools::default()),
            AgentRuntimeConfig { max_turns: 3 },
        );

        let result = runtime
            .run_turn(
                request(scenario),
                Vec::<AgentMessage>::new(),
                CancellationToken::new(),
                sink,
            )
            .await;

        if scenario == "max_turns" {
            let error = result.expect_err("max turns must fail the turn");
            assert_eq!(error.details["reason"], "max_turns_reached");
            assert_eq!(error.details["max_turns"], 3);
        } else {
            let outcome = result.expect("oracle success scenario must complete");
            assert_eq!(outcome.turn_count, script(scenario).len());
            assert_eq!(outcome.usage.input_tokens, 10 * outcome.turn_count as u64);
            assert_eq!(outcome.usage.output_tokens, 2 * outcome.turn_count as u64);
            assert_eq!(outcome.usage.cache_read_tokens, outcome.turn_count as u64);
            if scenario == "parallel_tools" {
                assert_eq!(tool_result_ids(&outcome), ["slow-call", "fast-call"]);
            }
        }
        assert_eq!(
            actual_semantics(&observed.lock().unwrap()),
            expected_semantics(scenario),
            "semantic event trace diverged for {scenario}"
        );
    }
}

#[tokio::test]
async fn abort_oracle_matches_when_cancellation_reaches_an_active_tool() {
    let observed = Arc::new(Mutex::new(Vec::new()));
    let observer = Arc::clone(&observed);
    let sink = AgentEventSink::new(move |event| {
        observer.lock().unwrap().push(event);
        async { Ok(()) }
    });
    let cancel = CancellationToken::new();
    let (started_tx, mut started_rx) = mpsc::unbounded_channel();
    let runtime = Arc::new(AgentRuntime::new(
        Arc::new(ScriptedModel {
            steps: Mutex::new(script("abort").into()),
        }),
        Arc::new(FixtureTools {
            wait_started: Some(started_tx),
        }),
        AgentRuntimeConfig { max_turns: 3 },
    ));

    let task = tokio::spawn({
        let runtime = Arc::clone(&runtime);
        let cancel = cancel.clone();
        async move {
            runtime
                .run_turn(request("abort"), vec![], cancel, sink)
                .await
        }
    });
    started_rx
        .recv()
        .await
        .expect("wait tool must acknowledge invocation before cancellation");
    cancel.cancel();
    let error = task.await.unwrap().unwrap_err();

    assert_eq!(error.code, agent_events::AgentErrorCode::Cancelled);
    assert_eq!(
        actual_semantics(&observed.lock().unwrap()),
        expected_semantics("abort")
    );
}
