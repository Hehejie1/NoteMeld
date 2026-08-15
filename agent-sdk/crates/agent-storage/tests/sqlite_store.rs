use std::{
    fs,
    path::PathBuf,
    sync::{mpsc, Arc, Barrier},
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use agent_events::{
    AgentErrorCode, AgentEvent, AgentEventEnvelope, EventId, MessageDeltaPayload, RequestId,
    SessionId, TurnId, TurnStatus, UnknownEvent, SCHEMA_VERSION,
};
use agent_storage::{
    EventStore, EventWriteOutcome, ReferenceSqliteStore, SessionStore, StoredSession, StoredTurn,
    TurnWriteOutcome,
};
use rusqlite::{Connection, TransactionBehavior};
use serde_json::{json, Map};

fn temporary_database_path(label: &str) -> PathBuf {
    let unique = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap()
        .as_nanos();
    std::env::temp_dir().join(format!(
        "notemeld-agent-storage-{label}-{}-{unique}.sqlite",
        std::process::id()
    ))
}

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
fn concurrent_retry_across_connections_linearizes_turn_insertion() {
    let path = temporary_database_path("turn-race");
    let stored_turn = turn(
        "session-race",
        "10000000-0000-4000-8000-000000000031",
        "20000000-0000-4000-8000-000000000031",
    );
    {
        let seed = ReferenceSqliteStore::open(&path).unwrap();
        seed.insert_session(&StoredSession::new(SessionId::from("session-race")))
            .unwrap();
    }

    let stores = [
        Arc::new(ReferenceSqliteStore::open(&path).unwrap()),
        Arc::new(ReferenceSqliteStore::open(&path).unwrap()),
    ];
    let barrier = Arc::new(Barrier::new(3));
    let workers: Vec<_> = stores
        .iter()
        .map(|store| {
            let store = Arc::clone(store);
            let barrier = Arc::clone(&barrier);
            let stored_turn = stored_turn.clone();
            thread::spawn(move || {
                barrier.wait();
                store.insert_turn(&stored_turn)
            })
        })
        .collect();
    barrier.wait();
    let outcomes: Vec<_> = workers
        .into_iter()
        .map(|worker| worker.join().unwrap().unwrap())
        .collect();
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| **outcome == TurnWriteOutcome::Inserted)
            .count(),
        1
    );
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| {
                matches!(outcome, TurnWriteOutcome::Replayed(existing) if **existing == stored_turn)
            })
            .count(),
        1
    );

    drop(stores);
    fs::remove_file(&path).unwrap();
}

#[test]
fn concurrent_conflicting_turns_across_connections_keep_typed_error() {
    let path = temporary_database_path("turn-conflict");
    {
        let seed = ReferenceSqliteStore::open(&path).unwrap();
        seed.insert_session(&StoredSession::new(SessionId::from("session-race")))
            .unwrap();
    }
    let turns = [
        turn(
            "session-race",
            "10000000-0000-4000-8000-000000000032",
            "20000000-0000-4000-8000-000000000032",
        ),
        turn(
            "session-race",
            "10000000-0000-4000-8000-000000000033",
            "20000000-0000-4000-8000-000000000032",
        ),
    ];
    let stores = [
        Arc::new(ReferenceSqliteStore::open(&path).unwrap()),
        Arc::new(ReferenceSqliteStore::open(&path).unwrap()),
    ];
    let barrier = Arc::new(Barrier::new(3));
    let workers: Vec<_> = stores
        .iter()
        .zip(turns)
        .map(|(store, stored_turn)| {
            let store = Arc::clone(store);
            let barrier = Arc::clone(&barrier);
            thread::spawn(move || {
                barrier.wait();
                store.insert_turn(&stored_turn)
            })
        })
        .collect();
    barrier.wait();
    let outcomes: Vec<_> = workers
        .into_iter()
        .map(|worker| worker.join().unwrap())
        .collect();
    assert_eq!(
        outcomes
            .iter()
            .filter(|outcome| matches!(outcome, Ok(TurnWriteOutcome::Inserted)))
            .count(),
        1
    );
    let errors: Vec<_> = outcomes
        .iter()
        .filter_map(|outcome| outcome.as_ref().err())
        .collect();
    assert_eq!(errors.len(), 1);
    assert_eq!(errors[0].code, AgentErrorCode::DuplicateRequest);
    assert_eq!(
        errors[0].message,
        "session request_id already belongs to another turn"
    );

    drop(stores);
    fs::remove_file(&path).unwrap();
}

#[test]
fn concurrent_retry_across_connections_linearizes_event_append() {
    let path = temporary_database_path("event-race");
    let stored_turn = turn(
        "session-race",
        "10000000-0000-4000-8000-000000000034",
        "20000000-0000-4000-8000-000000000034",
    );
    let envelope = event(
        "session-race",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000034",
        1,
    );
    {
        let seed = ReferenceSqliteStore::open(&path).unwrap();
        seed.insert_session(&StoredSession::new(SessionId::from("session-race")))
            .unwrap();
        seed.insert_turn(&stored_turn).unwrap();
    }

    let stores = [
        Arc::new(ReferenceSqliteStore::open(&path).unwrap()),
        Arc::new(ReferenceSqliteStore::open(&path).unwrap()),
    ];
    let barrier = Arc::new(Barrier::new(3));
    let workers: Vec<_> = stores
        .iter()
        .map(|store| {
            let store = Arc::clone(store);
            let barrier = Arc::clone(&barrier);
            let envelope = envelope.clone();
            thread::spawn(move || {
                barrier.wait();
                store.append_event(&envelope)
            })
        })
        .collect();
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

    drop(stores);
    fs::remove_file(&path).unwrap();
}

#[test]
fn an_external_write_lock_has_a_bounded_safe_busy_error() {
    let path = temporary_database_path("bounded-busy");
    {
        let seed = ReferenceSqliteStore::open(&path).unwrap();
        seed.insert_session(&StoredSession::new(SessionId::from("session-busy")))
            .unwrap();
    }
    let mut blocking_connection = Connection::open(&path).unwrap();
    let blocking_transaction = blocking_connection
        .transaction_with_behavior(TransactionBehavior::Immediate)
        .unwrap();
    let store = ReferenceSqliteStore::open(&path).unwrap();
    let stored_turn = turn(
        "session-busy",
        "10000000-0000-4000-8000-000000000039",
        "20000000-0000-4000-8000-000000000039",
    );
    let (sender, receiver) = mpsc::channel();
    let worker = thread::spawn(move || {
        sender.send(store.insert_turn(&stored_turn)).unwrap();
    });

    let outcome = receiver.recv_timeout(Duration::from_secs(3));
    drop(blocking_transaction);
    worker.join().unwrap();
    let error = outcome
        .expect("reference store must stop waiting within its busy timeout")
        .unwrap_err();
    assert_eq!(error.code, AgentErrorCode::SdkInternalError);
    assert_eq!(error.message, "reference sqlite database is busy");

    drop(blocking_connection);
    fs::remove_file(&path).unwrap();
}

#[test]
fn persisted_max_sequence_returns_exhausted_without_poisoning_the_store() {
    let path = temporary_database_path("sequence-exhausted");
    let stored_turn = turn(
        "session-exhausted",
        "10000000-0000-4000-8000-000000000040",
        "20000000-0000-4000-8000-000000000040",
    );
    let first = event(
        "session-exhausted",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000040",
        1,
    );
    let store = ReferenceSqliteStore::open(&path).unwrap();
    store
        .insert_session(&StoredSession::new(SessionId::from("session-exhausted")))
        .unwrap();
    store.insert_turn(&stored_turn).unwrap();
    store.append_event(&first).unwrap();
    {
        let raw = Connection::open(&path).unwrap();
        raw.execute(
            "UPDATE agent_events SET sequence = ?1 WHERE event_id = ?2",
            rusqlite::params![i64::MAX, first.event_id.0],
        )
        .unwrap();
    }

    let mut incoming = event(
        "session-exhausted",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000041",
        i64::MAX as u64 - 1,
    );
    incoming.timestamp = "2026-08-15T00:00:02Z".to_owned();
    let error = store.append_event(&incoming).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::InvalidInput);
    assert_eq!(error.message, "event sequence space is exhausted");
    assert_eq!(error.details["reason"], "sequence_exhausted");

    let replay = store.replay_events(&stored_turn.id, 0).unwrap();
    assert_eq!(replay.len(), 1);
    assert_eq!(replay[0].sequence, i64::MAX as u64);
    assert_eq!(store.get_turn(&stored_turn.id).unwrap(), Some(stored_turn));

    drop(store);
    fs::remove_file(&path).unwrap();
}

#[test]
fn append_rejects_non_v1_schema_without_persisting_it() {
    let stored_turn = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000035",
        "20000000-0000-4000-8000-000000000035",
    );
    let store = seeded_store("session-a", stored_turn.clone());
    let mut envelope = event(
        "session-a",
        &stored_turn.id.0,
        "30000000-0000-4000-8000-000000000035",
        1,
    );
    envelope.schema_version = "2".to_owned();

    let error = store.append_event(&envelope).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::AgentSchemaMismatch);
    assert_eq!(error.message, "event schema_version must be \"1\"");
    assert!(store.replay_events(&stored_turn.id, 0).unwrap().is_empty());
}

#[test]
fn file_reopen_replays_unknown_event_losslessly_and_retries_exactly() {
    let path = temporary_database_path("reopen");
    let stored_turn = turn(
        "session-file",
        "10000000-0000-4000-8000-000000000036",
        "20000000-0000-4000-8000-000000000036",
    );
    let envelope = AgentEventEnvelope {
        schema_version: SCHEMA_VERSION.to_owned(),
        event_id: EventId::from("30000000-0000-4000-8000-000000000036"),
        sequence: 1,
        session_id: SessionId::from("session-file"),
        turn_id: stored_turn.id.clone(),
        timestamp: "2026-08-15T09:08:07.654321Z".to_owned(),
        event: AgentEvent::Unknown(UnknownEvent {
            event_type: "future.deep-event".to_owned(),
            payload: json!({
                "nested": {"items": [1, true, null, {"future": "value"}]},
                "opaque_number": 18446744073709551615_u64,
                "unicode": "无损"
            }),
        }),
    };
    {
        let store = ReferenceSqliteStore::open(&path).unwrap();
        store
            .insert_session(&StoredSession::new(SessionId::from("session-file")))
            .unwrap();
        store.insert_turn(&stored_turn).unwrap();
        assert_eq!(
            store.append_event(&envelope).unwrap(),
            EventWriteOutcome::Inserted
        );
    }
    {
        let reopened = ReferenceSqliteStore::open(&path).unwrap();
        assert_eq!(
            reopened.replay_events(&stored_turn.id, 0).unwrap(),
            vec![envelope.clone()]
        );
        assert_eq!(
            reopened.append_event(&envelope).unwrap(),
            EventWriteOutcome::Replayed
        );
    }
    fs::remove_file(&path).unwrap();
    assert!(!path.exists());
}

#[test]
fn event_identity_is_global_and_sequence_respects_sqlite_u64_boundary() {
    let turn_a = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000037",
        "20000000-0000-4000-8000-000000000037",
    );
    let store = seeded_store("session-a", turn_a.clone());
    let turn_b = turn(
        "session-a",
        "10000000-0000-4000-8000-000000000038",
        "20000000-0000-4000-8000-000000000038",
    );
    store.insert_turn(&turn_b).unwrap();
    let global_event_id = "30000000-0000-4000-8000-000000000037";
    store
        .append_event(&event("session-a", &turn_a.id.0, global_event_id, 1))
        .unwrap();
    let error = store
        .append_event(&event("session-a", &turn_b.id.0, global_event_id, 1))
        .unwrap_err();
    assert_eq!(error.code, AgentErrorCode::DuplicateRequest);
    assert_eq!(
        error.message,
        "event_id already identifies a different event"
    );

    let mut max_in_range_gap = event(
        "session-a",
        &turn_b.id.0,
        "30000000-0000-4000-8000-000000000039",
        i64::MAX as u64,
    );
    max_in_range_gap.timestamp = "2026-08-15T00:00:02Z".to_owned();
    let error = store.append_event(&max_in_range_gap).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::InvalidInput);
    assert_eq!(error.message, "event sequence must append without gaps");

    let overflow = event(
        "session-a",
        &turn_b.id.0,
        "30000000-0000-4000-8000-000000000038",
        i64::MAX as u64 + 1,
    );
    let error = store.append_event(&overflow).unwrap_err();
    assert_eq!(error.code, AgentErrorCode::InvalidInput);
    assert_eq!(
        error.message,
        "event sequence exceeds reference SQLite range"
    );
    assert!(store
        .replay_events(&turn_b.id, u64::MAX)
        .unwrap()
        .is_empty());
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
    let path = temporary_database_path("close");
    {
        let store = ReferenceSqliteStore::open(&path).unwrap();
        store
            .insert_session(&StoredSession::new(SessionId::from("session-file")))
            .unwrap();
    }
    fs::remove_file(&path).unwrap();
    assert!(!path.exists());
}
