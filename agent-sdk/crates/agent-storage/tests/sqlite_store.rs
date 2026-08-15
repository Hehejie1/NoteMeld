use std::{
    fs,
    path::PathBuf,
    sync::{Arc, Barrier},
    thread,
    time::{SystemTime, UNIX_EPOCH},
};

use agent_events::{
    AgentErrorCode, AgentEvent, AgentEventEnvelope, EventId, MessageDeltaPayload, RequestId,
    SessionId, TurnId, TurnStatus, SCHEMA_VERSION,
};
use agent_storage::{
    EventStore, EventWriteOutcome, ReferenceSqliteStore, SessionStore, StoredSession, StoredTurn,
    TurnWriteOutcome,
};
use serde_json::Map;

fn turn(session: &str, turn_id: &str, request_id: &str) -> StoredTurn {
    StoredTurn {
        id: TurnId::from(turn_id),
        session_id: SessionId::from(session),
        request_id: RequestId::from(request_id),
        status: TurnStatus::Created,
        model_provider_id: None,
        model_name: None,
        error_code: None,
        error_message: None,
        created_at: "2026-08-15T00:00:00Z".to_owned(),
        started_at: None,
        finished_at: None,
        updated_at: "2026-08-15T00:00:00Z".to_owned(),
    }
}

fn event(session: &str, turn_id: &str, event_id: &str, sequence: u64) -> AgentEventEnvelope {
    AgentEventEnvelope {
        schema_version: SCHEMA_VERSION.to_owned(),
        event_id: EventId::from(event_id),
        sequence,
        session_id: SessionId::from(session),
        turn_id: TurnId::from(turn_id),
        timestamp: format!("2026-08-15T00:00:{sequence:02}Z"),
        event: AgentEvent::MessageDelta(MessageDeltaPayload {
            message_id: Some("assistant-1".to_owned()),
            delta: Some(format!("delta-{sequence}")),
            extra: Map::new(),
        }),
    }
}

fn seeded_store(session: &str, stored_turn: StoredTurn) -> ReferenceSqliteStore {
    let store = ReferenceSqliteStore::open_in_memory().unwrap();
    store
        .insert_session(&StoredSession::new(SessionId::from(session)))
        .unwrap();
    assert_eq!(
        store.insert_turn(&stored_turn).unwrap(),
        TurnWriteOutcome::Inserted
    );
    store
}

#[test]
fn turn_request_is_idempotent_within_session_and_conflicts_are_typed() {
    let store = ReferenceSqliteStore::open_in_memory().unwrap();
    store
        .insert_session(&StoredSession::new(SessionId::from("session-a")))
        .unwrap();
    let original = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000001",
        "20000000-0000-4000-8000-000000000001",
    );
    assert_eq!(
        store.insert_turn(&original).unwrap(),
        TurnWriteOutcome::Inserted
    );
    assert_eq!(
        store.insert_turn(&original).unwrap(),
        TurnWriteOutcome::Replayed(Box::new(original.clone()))
    );

    let conflicting = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000002",
        "20000000-0000-4000-8000-000000000001",
    );
    let error = store.insert_turn(&conflicting).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::DuplicateRequest);
    assert_eq!(
        error.message,
        "session request_id already belongs to another turn"
    );
}

#[test]
fn event_replay_after_sequence_is_gapless_stable_and_turn_isolated() {
    let turn_a = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000010",
        "20000000-0000-4000-8000-000000000010",
    );
    let store = seeded_store("session-a", turn_a.clone());
    let turn_b = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000011",
        "20000000-0000-4000-8000-000000000011",
    );
    store.insert_turn(&turn_b).unwrap();

    for sequence in 1..=3 {
        store
            .append_event(&event(
                "session-a",
                &turn_a.id.0,
                &format!("30000000-0000-4000-8000-{sequence:012}"),
                sequence,
            ))
            .unwrap();
    }
    store
        .append_event(&event(
            "session-a",
            &turn_b.id.0,
            "30000000-0000-4000-8000-000000000099",
            1,
        ))
        .unwrap();

    let replay = store.replay_events(&turn_a.id, 1).unwrap();
    assert_eq!(
        replay
            .iter()
            .map(|stored| stored.sequence)
            .collect::<Vec<_>>(),
        vec![2, 3]
    );
    assert!(replay.iter().all(|stored| stored.turn_id == turn_a.id));
    assert_eq!(store.replay_events(&turn_b.id, 0).unwrap().len(), 1);
}

#[test]
fn append_is_idempotent_and_maps_sequence_or_event_id_conflicts() {
    let stored_turn = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000020",
        "20000000-0000-4000-8000-000000000020",
    );
    let store = seeded_store("session-a", stored_turn.clone());
    let first = event(
        "session-a",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000020",
        1,
    );
    assert_eq!(
        store.append_event(&first).unwrap(),
        EventWriteOutcome::Inserted
    );
    assert_eq!(
        store.append_event(&first).unwrap(),
        EventWriteOutcome::Replayed
    );

    let sequence_conflict = event(
        "session-a",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000021",
        1,
    );
    let error = store.append_event(&sequence_conflict).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::DuplicateRequest);
    assert_eq!(
        error.message,
        "turn sequence already contains a different event"
    );

    let event_id_conflict = event(
        "session-a",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000020",
        2,
    );
    let error = store.append_event(&event_id_conflict).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::DuplicateRequest);
    assert_eq!(
        error.message,
        "event_id already identifies a different event"
    );
}

#[test]
fn concurrent_retry_is_linearized_without_duplicate_rows() {
    let stored_turn = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000030",
        "20000000-0000-4000-8000-000000000030",
    );
    let store = Arc::new(seeded_store("session-a", stored_turn.clone()));
    let envelope = event(
        "session-a",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000030",
        1,
    );
    let barrier = Arc::new(Barrier::new(3));
    let mut workers = Vec::new();
    for _ in 0..2 {
        let store = Arc::clone(&store);
        let envelope = envelope.clone();
        let barrier = Arc::clone(&barrier);
        workers.push(thread::spawn(move || {
            barrier.wait();
            store.append_event(&envelope)
        }));
    }
    barrier.wait();
    let outcomes: Vec<_> = workers
        .into_iter()
        .map(|worker| worker.join().unwrap().unwrap())
        .collect();
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| **outcome == EventWriteOutcome::Inserted)
            .count(),
        1
    );
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| **outcome == EventWriteOutcome::Replayed)
            .count(),
        1
    );
    assert_eq!(store.replay_events(&stored_turn.id, 0).unwrap().len(), 1);
}

#[test]
fn missing_parent_turn_and_sequence_gaps_have_stable_errors() {
    let store = ReferenceSqliteStore::open_in_memory().unwrap();
    let missing = event(
        "session-a",
        "10000000-0000-4000-8000-000000000040",
        "30000000-0000-4000-8000-000000000040",
        1,
    );
    let error = store.append_event(&missing).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::TurnNotFound);

    let stored_turn = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000041",
        "20000000-0000-4000-8000-000000000041",
    );
    store
        .insert_session(&StoredSession::new(SessionId::from("session-a")))
        .unwrap();
    store.insert_turn(&stored_turn).unwrap();
    let gap = event(
        "session-a",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000041",
        2,
    );
    let error = store.append_event(&gap).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::InvalidInput);
    assert_eq!(error.message, "event sequence must append without gaps");
}

#[test]
fn file_backed_store_releases_the_database_file_on_drop() {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    let path: PathBuf = std::env::temp_dir().join(format!(
        "notemeld-agent-storage-{}-{unique}.sqlite",
        std::process::id()
    ));
    {
        let store = ReferenceSqliteStore::open(&path).unwrap();
        store
            .insert_session(&StoredSession::new(SessionId::from("session-file")))
            .unwrap();
    }
    fs::remove_file(&path).unwrap();
    assert!(!path.exists());
}
