use std::{
    sync::{Arc, Barrier},
    thread,
};

use agent_events::{AgentErrorCode, RequestId, SessionId, TurnStatus};
use agent_session::{TurnCoordinator, TurnStartRequest, TurnStateMachine};
use serde_json::json;

fn request(session: &str, request_id: &str, text: &str) -> TurnStartRequest {
    TurnStartRequest::new(
        SessionId::from(session),
        RequestId::from(request_id),
        json!({"text": text}),
    )
}

#[test]
fn transition_table_accepts_every_approved_edge() {
    let legal = [
        (TurnStatus::Created, TurnStatus::Running),
        (TurnStatus::Running, TurnStatus::WaitingApproval),
        (TurnStatus::Running, TurnStatus::Cancelling),
        (TurnStatus::Running, TurnStatus::Succeeded),
        (TurnStatus::Running, TurnStatus::Failed),
        (TurnStatus::Running, TurnStatus::Cancelled),
        (TurnStatus::Running, TurnStatus::Interrupted),
        (TurnStatus::WaitingApproval, TurnStatus::Running),
        (TurnStatus::WaitingApproval, TurnStatus::Cancelling),
        (TurnStatus::WaitingApproval, TurnStatus::Failed),
        (TurnStatus::WaitingApproval, TurnStatus::Cancelled),
        (TurnStatus::WaitingApproval, TurnStatus::Interrupted),
        (TurnStatus::Cancelling, TurnStatus::Cancelled),
        (TurnStatus::Cancelling, TurnStatus::Failed),
        (TurnStatus::Cancelling, TurnStatus::Interrupted),
    ];

    for (from, to) in legal {
        let mut machine = TurnStateMachine::new(from);
        assert_eq!(machine.transition(to), Ok(()), "{from:?} -> {to:?}");
        assert_eq!(machine.status(), to);
    }
}

#[test]
fn illegal_and_terminal_transitions_return_exact_stable_errors() {
    let mut created = TurnStateMachine::new(TurnStatus::Created);
    let illegal = created.transition(TurnStatus::Succeeded).unwrap_err();
    assert_eq!(illegal.code, AgentErrorCode::InvalidInput);
    assert_eq!(
        illegal.message,
        "illegal turn transition: created -> succeeded"
    );
    assert_eq!(created.status(), TurnStatus::Created);

    for terminal in [
        TurnStatus::Succeeded,
        TurnStatus::Failed,
        TurnStatus::Cancelled,
        TurnStatus::Interrupted,
    ] {
        let mut machine = TurnStateMachine::new(terminal);
        let error = machine.transition(TurnStatus::Running).unwrap_err();
        assert_eq!(error.code, AgentErrorCode::TurnTerminal);
        assert_eq!(
            error.message,
            format!(
                "terminal turn cannot transition: {} -> running",
                match terminal {
                    TurnStatus::Succeeded => "succeeded",
                    TurnStatus::Failed => "failed",
                    TurnStatus::Cancelled => "cancelled",
                    TurnStatus::Interrupted => "interrupted",
                    _ => unreachable!(),
                }
            )
        );
        assert_eq!(machine.status(), terminal);
    }
}

#[test]
fn same_session_has_one_atomic_active_lease() {
    let coordinator = Arc::new(TurnCoordinator::new());
    let barrier = Arc::new(Barrier::new(3));
    let mut workers = Vec::new();

    for (request_id, text) in [
        ("00000000-0000-4000-8000-000000000001", "first"),
        ("00000000-0000-4000-8000-000000000002", "second"),
    ] {
        let coordinator = Arc::clone(&coordinator);
        let barrier = Arc::clone(&barrier);
        workers.push(thread::spawn(move || {
            barrier.wait();
            coordinator.start_turn(request("session-a", request_id, text))
        }));
    }
    barrier.wait();

    let results: Vec<_> = workers
        .into_iter()
        .map(|worker| worker.join().unwrap())
        .collect();
    assert_eq!(results.iter().filter(|result| result.is_ok()).count(), 1);
    let error = results
        .into_iter()
        .find_map(Result::err)
        .expect("one contender must be rejected");
    assert_eq!(error.code, AgentErrorCode::SessionBusy);
    assert_eq!(error.message, "session already has an active turn");
}

#[test]
fn different_sessions_can_acquire_leases_concurrently() {
    let coordinator = Arc::new(TurnCoordinator::new());
    let barrier = Arc::new(Barrier::new(3));
    let mut workers = Vec::new();

    for session in ["session-a", "session-b"] {
        let coordinator = Arc::clone(&coordinator);
        let barrier = Arc::clone(&barrier);
        workers.push(thread::spawn(move || {
            barrier.wait();
            coordinator.start_turn(request(
                session,
                "00000000-0000-4000-8000-000000000003",
                "same request id, different scope",
            ))
        }));
    }
    barrier.wait();

    let turns: Vec<_> = workers
        .into_iter()
        .map(|worker| worker.join().unwrap().unwrap().turn)
        .collect();
    assert_ne!(turns[0].id, turns[1].id);
    assert_ne!(turns[0].session_id, turns[1].session_id);
}

#[test]
fn terminal_transition_or_explicit_release_allows_next_turn() {
    let coordinator = TurnCoordinator::new();
    let first = coordinator
        .start_turn(request(
            "session-a",
            "00000000-0000-4000-8000-000000000004",
            "first",
        ))
        .unwrap();
    coordinator
        .transition(&first.turn.id, TurnStatus::Running)
        .unwrap();
    coordinator
        .transition(&first.turn.id, TurnStatus::Succeeded)
        .unwrap();
    coordinator
        .start_turn(request(
            "session-a",
            "00000000-0000-4000-8000-000000000005",
            "second",
        ))
        .unwrap();

    let released = coordinator
        .start_turn(request(
            "session-b",
            "00000000-0000-4000-8000-000000000006",
            "release me",
        ))
        .unwrap();
    coordinator.release(&released.turn.id).unwrap();
    coordinator
        .start_turn(request(
            "session-b",
            "00000000-0000-4000-8000-000000000007",
            "after release",
        ))
        .unwrap();
}

#[test]
fn request_replay_is_linearized_and_payload_conflicts_are_rejected() {
    let coordinator = Arc::new(TurnCoordinator::new());
    let barrier = Arc::new(Barrier::new(3));
    let mut workers = Vec::new();
    for _ in 0..2 {
        let coordinator = Arc::clone(&coordinator);
        let barrier = Arc::clone(&barrier);
        workers.push(thread::spawn(move || {
            barrier.wait();
            coordinator.start_turn(request(
                "session-idempotent",
                "00000000-0000-4000-8000-000000000008",
                "same payload",
            ))
        }));
    }
    barrier.wait();
    let outcomes: Vec<_> = workers
        .into_iter()
        .map(|worker| worker.join().unwrap().unwrap())
        .collect();
    assert_eq!(outcomes[0].turn.id, outcomes[1].turn.id);
    assert_eq!(
        outcomes.iter().filter(|outcome| outcome.replayed).count(),
        1
    );

    let conflict = coordinator
        .start_turn(request(
            "session-idempotent",
            "00000000-0000-4000-8000-000000000008",
            "different payload",
        ))
        .unwrap_err();
    assert_eq!(conflict.code, AgentErrorCode::DuplicateRequest);
    assert_eq!(
        conflict.message,
        "request_id was already used with a different payload"
    );
}
