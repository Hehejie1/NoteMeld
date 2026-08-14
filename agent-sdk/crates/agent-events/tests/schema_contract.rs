use std::{fs, path::PathBuf};

use agent_events::{
    AgentError, AgentErrorCode, AgentEvent, AgentEventEnvelope, ApprovalRequiredPayload,
    ApprovalResolvedPayload, EventId, MessageCompletedPayload, MessageDeltaPayload,
    MessageStartedPayload, ModelOverride, SessionId, ToolCompletedPayload, ToolProgressPayload,
    ToolStartedPayload, TurnCancelledPayload, TurnFailedPayload, TurnId, TurnInterruptedPayload,
    TurnRequest, TurnStartedPayload, TurnSucceededPayload, UnknownEvent, UsageUpdatedPayload,
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
    assert_eq!(paths.len(), 5, "exactly five oracle fixtures are required");

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

fn without_field(mut value: Value, name: &str) -> Value {
    value
        .as_object_mut()
        .expect("golden example must be an object")
        .remove(name);
    value
}

#[test]
fn oracle_rows_deserialize_without_losing_legacy_event_bodies() {
    let rows = fixture_rows();
    assert_eq!(
        rows.len(),
        88,
        "all checked-in oracle rows must be exercised"
    );

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
fn envelope_rejects_zero_sequence_on_decode_and_encode() {
    let mut wire = serde_json::to_value(envelope(AgentEvent::TurnStarted(
        TurnStartedPayload::default(),
    )))
    .unwrap();
    wire["sequence"] = json!(0);
    let decode_error = serde_json::from_value::<AgentEventEnvelope>(wire)
        .expect_err("sequence zero must be rejected while decoding");
    assert!(decode_error.to_string().contains("sequence"));

    let mut invalid = envelope(AgentEvent::TurnStarted(TurnStartedPayload::default()));
    invalid.sequence = 0;
    let encode_error =
        serde_json::to_value(invalid).expect_err("sequence zero must be rejected while encoding");
    assert!(encode_error.to_string().contains("sequence"));
}

#[test]
fn envelope_rejects_invalid_ids_and_non_utc_timestamps_in_both_directions() {
    let valid = serde_json::to_value(envelope(AgentEvent::TurnStarted(
        TurnStartedPayload::default(),
    )))
    .unwrap();
    for (field, invalid_value) in [
        ("event_id", json!("x")),
        ("turn_id", json!("not-a-uuid")),
        ("timestamp", json!("2026-08-14T08:00:00+08:00")),
        ("timestamp", json!("2026-08-14T00:00:00-00:00")),
        ("timestamp", json!("not-a-timestamp")),
    ] {
        let error = serde_json::from_value::<AgentEventEnvelope>(with_field(
            valid.clone(),
            field,
            invalid_value,
        ))
        .expect_err("invalid envelope identity/timestamp must be rejected");
        assert!(error.to_string().contains(field));
    }

    let mut invalid_event = envelope(AgentEvent::TurnStarted(TurnStartedPayload::default()));
    invalid_event.event_id = EventId("x".to_owned());
    assert!(serde_json::to_value(invalid_event).is_err());

    let mut invalid_turn = envelope(AgentEvent::TurnStarted(TurnStartedPayload::default()));
    invalid_turn.turn_id = TurnId("x".to_owned());
    assert!(serde_json::to_value(invalid_turn).is_err());

    let mut invalid_timestamp = envelope(AgentEvent::TurnStarted(TurnStartedPayload::default()));
    invalid_timestamp.timestamp = "2026-08-14T00:00:00-00:00".to_owned();
    assert!(serde_json::to_value(invalid_timestamp).is_err());
}

#[test]
fn request_ids_reject_non_uuid_strings_in_both_directions() {
    let invalid = json!({
        "schema_version": "1",
        "request_id": "x",
        "session_id": "session-1",
        "input": {"text": "hello", "attachments": [], "context_refs": []},
        "model_override": null,
        "approval_mode": "interactive"
    });
    let error = serde_json::from_value::<TurnRequest>(invalid)
        .expect_err("request_id must be a UUID while decoding");
    assert!(error.to_string().contains("UUID"));

    assert!(serde_json::to_value(agent_events::RequestId("x".to_owned())).is_err());
}

#[test]
fn session_ids_reject_empty_strings_in_both_directions() {
    let valid = serde_json::to_value(envelope(AgentEvent::TurnStarted(
        TurnStartedPayload::default(),
    )))
    .unwrap();
    let error =
        serde_json::from_value::<AgentEventEnvelope>(with_field(valid, "session_id", json!("")))
            .expect_err("session_id must be nonempty while decoding");
    assert!(error.to_string().contains("session_id"));

    assert!(serde_json::to_value(SessionId(String::new())).is_err());
}

#[test]
fn rust_request_and_error_shapes_match_required_wire_fields() {
    let request_base = json!({
        "schema_version": "1",
        "request_id": "00000000-0000-4000-8000-000000000003",
        "session_id": "session-1",
        "input": {"text": "hello", "attachments": [], "context_refs": []},
        "model_override": null,
        "approval_mode": "interactive"
    });
    for missing in ["text", "attachments", "context_refs"] {
        let mut invalid = request_base.clone();
        invalid["input"].as_object_mut().unwrap().remove(missing);
        let error = serde_json::from_value::<TurnRequest>(invalid)
            .expect_err("TurnInput fields are required");
        assert!(error.to_string().contains(missing));
    }
    let missing_override = serde_json::from_value::<TurnRequest>(without_field(
        request_base.clone(),
        "model_override",
    ))
    .expect_err("model_override is required even though its value may be null");
    assert!(missing_override.to_string().contains("model_override"));

    for invalid_override in [
        json!({}),
        json!({"provider_id": "", "model_name": "model"}),
        json!({"provider_id": "provider", "model_name": ""}),
        json!({"provider_id": "provider", "model_name": 7}),
    ] {
        let error = serde_json::from_value::<TurnRequest>(with_field(
            request_base.clone(),
            "model_override",
            invalid_override,
        ))
        .expect_err("non-null model_override must be fully typed and nonempty");
        assert!(!error.to_string().is_empty());
    }

    let without_details: AgentError = serde_json::from_value(json!({
        "code": "tool_failed",
        "message": "safe failure"
    }))
    .expect("AgentError.details is optional");
    assert!(without_details.details.is_empty());

    let empty_message = serde_json::from_value::<AgentError>(json!({
        "code": "tool_failed",
        "message": ""
    }))
    .expect_err("AgentError.message must be nonempty");
    assert!(empty_message.to_string().contains("message"));

    let empty_message = AgentError::new(AgentErrorCode::ToolFailed, "");
    assert!(serde_json::to_value(empty_message).is_err());

    let invalid_override = ModelOverride {
        provider_id: String::new(),
        model_name: "model".to_owned(),
        extra: Default::default(),
    };
    assert!(serde_json::to_value(invalid_override).is_err());
}

#[test]
fn malformed_known_payload_is_rejected_by_rust() {
    let invalid = json!({
        "schema_version": "1",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "sequence": 1,
        "session_id": "session-1",
        "turn_id": "00000000-0000-4000-8000-000000000002",
        "timestamp": "2026-08-14T00:00:00Z",
        "type": "message.delta",
        "payload": {"delta": 7}
    });
    assert!(serde_json::from_value::<AgentEventEnvelope>(invalid).is_err());
}

#[test]
fn unknown_event_payload_must_be_an_object_on_decode_and_encode() {
    let wire = json!({
        "schema_version": "1",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "sequence": 1,
        "session_id": "session-1",
        "turn_id": "00000000-0000-4000-8000-000000000002",
        "timestamp": "2026-08-14T00:00:00Z",
        "type": "future.event",
        "payload": ["not", "an", "object"]
    });
    let decode_error = serde_json::from_value::<AgentEventEnvelope>(wire)
        .expect_err("unknown payload arrays must be rejected while decoding");
    assert!(decode_error.to_string().contains("payload"));

    let invalid = envelope(AgentEvent::Unknown(UnknownEvent {
        event_type: "future.event".to_owned(),
        payload: json!(["not", "an", "object"]),
    }));
    let encode_error = serde_json::to_value(invalid)
        .expect_err("unknown payload arrays must be rejected while encoding");
    assert!(encode_error.to_string().contains("payload"));
}

#[test]
fn unknown_event_type_must_be_nonempty_on_decode_and_encode() {
    let wire = json!({
        "schema_version": "1",
        "event_id": "00000000-0000-4000-8000-000000000001",
        "sequence": 1,
        "session_id": "session-1",
        "turn_id": "00000000-0000-4000-8000-000000000002",
        "timestamp": "2026-08-14T00:00:00Z",
        "type": "",
        "payload": {}
    });
    assert!(serde_json::from_value::<AgentEventEnvelope>(wire).is_err());

    let invalid = envelope(AgentEvent::Unknown(UnknownEvent {
        event_type: String::new(),
        payload: json!({}),
    }));
    assert!(serde_json::to_value(invalid).is_err());
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
    assert!(
        jsonschema::draft202012::meta::is_valid(&schema),
        "{schema_file} must be a valid Draft 2020-12 schema"
    );
    let validator = jsonschema::draft202012::options()
        .should_validate_formats(true)
        .build(&schema)
        .expect("schema must compile as Draft 2020-12");
    for instance in valid {
        assert!(
            validator.is_valid(instance),
            "{schema_file} rejected valid instance: {instance}"
        );
    }
    for instance in invalid {
        assert!(
            !validator.is_valid(instance),
            "{schema_file} accepted invalid instance: {instance}"
        );
    }
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
        "message": "请先配置模型"
    });

    assert_schema_cases(
        "turn-request.v1.json",
        &[turn_request.clone()],
        &[
            with_field(turn_request.clone(), "schema_version", json!("2")),
            with_field(turn_request.clone(), "request_id", json!("x")),
            without_field(turn_request.clone(), "model_override"),
            with_field(turn_request.clone(), "approval_mode", json!("always")),
            with_field(
                turn_request.clone(),
                "model_override",
                json!({"provider_id": "", "model_name": "model"}),
            ),
            with_field(
                turn_request.clone(),
                "model_override",
                json!({"provider_id": "provider"}),
            ),
            with_field(
                turn_request.clone(),
                "input",
                json!({"attachments": [], "context_refs": []}),
            ),
            with_field(
                turn_request.clone(),
                "input",
                json!({"text": "user input", "context_refs": []}),
            ),
            with_field(
                turn_request,
                "input",
                json!({"text": "user input", "attachments": []}),
            ),
        ],
    );
    assert_schema_cases(
        "agent-event.v1.json",
        &[event.clone(), unknown_event],
        &[
            with_field(event.clone(), "schema_version", json!("2")),
            with_field(event.clone(), "event_id", json!("x")),
            with_field(event.clone(), "turn_id", json!("x")),
            with_field(
                event.clone(),
                "timestamp",
                json!("2026-08-14T08:00:00+08:00"),
            ),
            with_field(event.clone(), "sequence", json!(0)),
            with_field(
                with_field(event.clone(), "type", json!("message.delta")),
                "payload",
                json!({"delta": 7}),
            ),
            with_field(
                with_field(event.clone(), "type", json!("future.event")),
                "payload",
                json!([]),
            ),
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
