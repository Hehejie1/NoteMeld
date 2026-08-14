use std::{fs, path::PathBuf};

use agent_events::{
    AgentError, AgentErrorCode, AgentEvent, AgentEventEnvelope, ApprovalRequiredPayload,
    ApprovalResolvedPayload, EventId, MessageCompletedPayload, MessageDeltaPayload,
    MessageStartedPayload, SessionId, ToolCompletedPayload, ToolProgressPayload,
    ToolStartedPayload, TurnCancelledPayload, TurnFailedPayload, TurnId, TurnInterruptedPayload,
    TurnRequest, TurnStartedPayload, TurnSucceededPayload, UsageUpdatedPayload,
};
use serde_json::{json, Value};

fn sdk_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../..")
}

fn fixture_rows() -> Vec<Value> {
    let fixture_dir = sdk_root().join("fixtures/conformance");
    let mut paths = fs::read_dir(fixture_dir)
        .expect("conformance fixture directory must exist")
        .map(|entry| entry.expect("fixture entry must be readable").path())
        .filter(|path| {
            path.extension()
                .is_some_and(|extension| extension == "jsonl")
        })
        .collect::<Vec<_>>();
    paths.sort();

    paths
        .into_iter()
        .flat_map(|path| {
            fs::read_to_string(&path)
                .unwrap_or_else(|error| panic!("failed to read {}: {error}", path.display()))
                .lines()
                .map(|line| serde_json::from_str(line).expect("fixture row must be JSON"))
                .collect::<Vec<Value>>()
        })
        .collect()
}

fn envelope(event: AgentEvent) -> AgentEventEnvelope {
    AgentEventEnvelope {
        schema_version: "1".to_owned(),
        event_id: EventId("00000000-0000-4000-8000-000000000001".to_owned()),
        sequence: 1,
        session_id: SessionId("session-1".to_owned()),
        turn_id: TurnId("00000000-0000-4000-8000-000000000002".to_owned()),
        timestamp: "2026-08-14T00:00:00Z".to_owned(),
        event,
    }
}

fn with_field(mut value: Value, name: &str, replacement: Value) -> Value {
    value
        .as_object_mut()
        .expect("golden example must be an object")
        .insert(name.to_owned(), replacement);
    value
}

#[test]
fn oracle_rows_deserialize_without_losing_legacy_event_bodies() {
    let rows = fixture_rows();
    assert!(!rows.is_empty(), "checked-in oracle rows must be exercised");

    for row in rows {
        let parsed: AgentEventEnvelope =
            serde_json::from_value(row.clone()).expect("schema v1 oracle row must deserialize");
        assert_eq!(parsed.schema_version, "1");
        match parsed.event {
            AgentEvent::Unknown(unknown) => {
                assert_eq!(unknown.event_type, row["type"]);
                assert_eq!(unknown.payload, row["payload"]);
            }
            known => panic!("legacy oracle type unexpectedly became v1 event: {known:?}"),
        }
    }
}

#[test]
fn envelope_rejects_non_v1_schema_version() {
    let invalid = json!({
        "schema_version": "2",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "sequence": 1,
        "session_id": "session-1",
        "turn_id": "00000000-0000-4000-8000-000000000002",
        "timestamp": "2026-08-14T00:00:00Z",
        "type": "future.event",
        "payload": {"kept": true}
    });

    let error = serde_json::from_value::<AgentEventEnvelope>(invalid)
        .expect_err("non-v1 envelope must be rejected");
    assert!(error.to_string().contains("schema_version"));
}

#[test]
fn approved_events_serialize_to_canonical_dotted_names() {
    let cases = [
        (
            "turn.started",
            AgentEvent::TurnStarted(TurnStartedPayload::default()),
        ),
        (
            "message.started",
            AgentEvent::MessageStarted(MessageStartedPayload::default()),
        ),
        (
            "message.delta",
            AgentEvent::MessageDelta(MessageDeltaPayload::default()),
        ),
        (
            "message.completed",
            AgentEvent::MessageCompleted(MessageCompletedPayload::default()),
        ),
        (
            "tool.started",
            AgentEvent::ToolStarted(ToolStartedPayload::default()),
        ),
        (
            "tool.progress",
            AgentEvent::ToolProgress(ToolProgressPayload::default()),
        ),
        (
            "tool.completed",
            AgentEvent::ToolCompleted(ToolCompletedPayload::default()),
        ),
        (
            "approval.required",
            AgentEvent::ApprovalRequired(ApprovalRequiredPayload::default()),
        ),
        (
            "approval.resolved",
            AgentEvent::ApprovalResolved(ApprovalResolvedPayload::default()),
        ),
        (
            "usage.updated",
            AgentEvent::UsageUpdated(UsageUpdatedPayload::default()),
        ),
        (
            "turn.succeeded",
            AgentEvent::TurnSucceeded(TurnSucceededPayload::default()),
        ),
        (
            "turn.failed",
            AgentEvent::TurnFailed(TurnFailedPayload {
                error: AgentError::new(AgentErrorCode::SdkInternalError, "safe failure"),
                ..TurnFailedPayload::default()
            }),
        ),
        (
            "turn.cancelled",
            AgentEvent::TurnCancelled(TurnCancelledPayload::default()),
        ),
        (
            "turn.interrupted",
            AgentEvent::TurnInterrupted(TurnInterruptedPayload::default()),
        ),
    ];

    for (expected_type, event) in cases {
        let value = serde_json::to_value(envelope(event)).expect("event must serialize");
        assert_eq!(value["type"], expected_type);
        assert!(value["payload"].is_object());
    }
}

#[test]
fn unknown_v1_event_round_trips_raw_type_and_payload() {
    let source = json!({
        "schema_version": "1",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "sequence": 9,
        "session_id": "session-1",
        "turn_id": "00000000-0000-4000-8000-000000000002",
        "timestamp": "2026-08-14T00:00:00Z",
        "type": "message.annotation",
        "payload": {"nested": {"future": [1, true, null]}}
    });

    let parsed: AgentEventEnvelope = serde_json::from_value(source.clone()).unwrap();
    assert!(matches!(parsed.event, AgentEvent::Unknown(_)));
    let serialized = serde_json::to_value(parsed).unwrap();
    assert_eq!(serialized["type"], source["type"]);
    assert_eq!(serialized["payload"], source["payload"]);
}

fn assert_schema_cases(schema_file: &str, valid: &[Value], invalid: &[Value]) {
    let path = sdk_root().join("schemas").join(schema_file);
    let schema: Value = serde_json::from_str(
        &fs::read_to_string(&path)
            .unwrap_or_else(|error| panic!("failed to read {}: {error}", path.display())),
    )
    .expect("schema must be JSON");
    for instance in valid {
        assert!(
            validates_schema(&schema, instance),
            "{schema_file} rejected valid instance: {instance}"
        );
    }
    for instance in invalid {
        assert!(
            !validates_schema(&schema, instance),
            "{schema_file} accepted invalid instance: {instance}"
        );
    }
}

fn validates_schema(schema: &Value, instance: &Value) -> bool {
    if schema
        .get("const")
        .is_some_and(|expected| expected != instance)
    {
        return false;
    }
    if schema
        .get("enum")
        .and_then(Value::as_array)
        .is_some_and(|values| !values.contains(instance))
    {
        return false;
    }
    if let Some(expected_type) = schema.get("type") {
        let type_matches = |name: &str| match name {
            "object" => instance.is_object(),
            "array" => instance.is_array(),
            "string" => instance.is_string(),
            "integer" => instance.as_i64().is_some() || instance.as_u64().is_some(),
            "number" => instance.is_number(),
            "boolean" => instance.is_boolean(),
            "null" => instance.is_null(),
            _ => false,
        };
        let matches = match expected_type {
            Value::String(name) => type_matches(name),
            Value::Array(names) => names.iter().filter_map(Value::as_str).any(type_matches),
            _ => false,
        };
        if !matches {
            return false;
        }
    }
    if schema
        .get("minLength")
        .and_then(Value::as_u64)
        .zip(instance.as_str())
        .is_some_and(|(minimum, text)| text.chars().count() < minimum as usize)
    {
        return false;
    }
    if schema
        .get("minimum")
        .and_then(Value::as_f64)
        .zip(instance.as_f64())
        .is_some_and(|(minimum, number)| number < minimum)
    {
        return false;
    }
    if let Some(object) = instance.as_object() {
        if schema
            .get("required")
            .and_then(Value::as_array)
            .is_some_and(|required| {
                required
                    .iter()
                    .filter_map(Value::as_str)
                    .any(|name| !object.contains_key(name))
            })
        {
            return false;
        }
        if let Some(properties) = schema.get("properties").and_then(Value::as_object) {
            for (name, value) in object {
                if let Some(property_schema) = properties.get(name) {
                    if !validates_schema(property_schema, value) {
                        return false;
                    }
                } else if schema.get("additionalProperties") == Some(&Value::Bool(false)) {
                    return false;
                }
            }
        }
    }
    if let (Some(items), Some(values)) = (schema.get("items"), instance.as_array()) {
        if values.iter().any(|value| !validates_schema(items, value)) {
            return false;
        }
    }
    true
}

#[test]
fn json_schemas_accept_valid_and_reject_invalid_wire_examples() {
    let turn_request = json!({
        "schema_version": "1",
        "request_id": "00000000-0000-4000-8000-000000000003",
        "session_id": "session-1",
        "input": {"text": "user input", "attachments": [], "context_refs": []},
        "model_override": null,
        "approval_mode": "interactive"
    });
    let event = json!({
        "schema_version": "1",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "sequence": 1,
        "session_id": "session-1",
        "turn_id": "00000000-0000-4000-8000-000000000002",
        "timestamp": "2026-08-14T00:00:00Z",
        "type": "turn.started",
        "payload": {}
    });
    let unknown_event = with_field(
        with_field(event.clone(), "type", json!("future.event")),
        "payload",
        json!({"kept": true}),
    );
    let error = json!({
        "code": "model_not_configured",
        "message": "请先配置模型",
        "details": {}
    });

    assert_schema_cases(
        "turn-request.v1.json",
        &[turn_request.clone()],
        &[
            with_field(turn_request.clone(), "schema_version", json!("2")),
            with_field(turn_request.clone(), "approval_mode", json!("always")),
            with_field(turn_request, "input", json!({"text": "user input"})),
        ],
    );
    assert_schema_cases(
        "agent-event.v1.json",
        &[event.clone(), unknown_event],
        &[
            with_field(event.clone(), "schema_version", json!("2")),
            with_field(event.clone(), "sequence", json!(0)),
            with_field(event, "payload", json!("not-an-object")),
        ],
    );
    assert_schema_cases(
        "errors.v1.json",
        &[error.clone()],
        &[
            with_field(error.clone(), "code", json!("raw_provider_exception")),
            with_field(error.clone(), "message", json!("")),
            with_field(error, "details", json!([])),
        ],
    );
}

#[test]
fn rust_types_parse_the_same_golden_examples() {
    let request: TurnRequest = serde_json::from_value(json!({
        "schema_version": "1",
        "request_id": "00000000-0000-4000-8000-000000000003",
        "session_id": "session-1",
        "input": {"text": "user input", "attachments": [], "context_refs": []},
        "model_override": null,
        "approval_mode": "allow_safe",
        "future_request_field": true
    }))
    .expect("TurnRequest must tolerate additive fields");
    assert_eq!(request.schema_version, "1");

    let error: AgentError = serde_json::from_value(json!({
        "code": "tool_failed",
        "message": "tool failed safely",
        "details": {"retryable": false},
        "future_error_field": true
    }))
    .expect("AgentError must tolerate additive fields");
    assert_eq!(error.code, AgentErrorCode::ToolFailed);
}
