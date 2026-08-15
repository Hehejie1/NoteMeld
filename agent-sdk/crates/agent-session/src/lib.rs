//! Session coordination contracts for the universal Agent SDK.

use std::{
    collections::HashMap,
    sync::{Arc, Mutex},
};

use agent_events::{AgentError, AgentErrorCode, RequestId, SessionId, TurnId, TurnStatus};
use serde_json::Value;
use uuid::Uuid;

#[derive(Debug, Clone, PartialEq)]
pub struct TurnStartRequest {
    pub session_id: SessionId,
    pub request_id: RequestId,
    pub payload: Value,
}

impl TurnStartRequest {
    pub fn new(session_id: SessionId, request_id: RequestId, payload: Value) -> Self {
        Self {
            session_id,
            request_id,
            payload,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct AgentTurn {
    pub id: TurnId,
    pub session_id: SessionId,
    pub request_id: RequestId,
    pub status: TurnStatus,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct TurnStartOutcome {
    pub turn: AgentTurn,
    pub replayed: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct TurnStateMachine {
    status: TurnStatus,
}

impl TurnStateMachine {
    pub const fn new(status: TurnStatus) -> Self {
        Self { status }
    }

    pub const fn status(&self) -> TurnStatus {
        self.status
    }

    pub fn transition(&mut self, next: TurnStatus) -> Result<(), AgentError> {
        if is_terminal(self.status) {
            return Err(AgentError::new(
                AgentErrorCode::TurnTerminal,
                format!(
                    "terminal turn cannot transition: {} -> {}",
                    status_name(self.status),
                    status_name(next)
                ),
            ));
        }

        if !is_legal_transition(self.status, next) {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                format!(
                    "illegal turn transition: {} -> {}",
                    status_name(self.status),
                    status_name(next)
                ),
            ));
        }

        self.status = next;
        Ok(())
    }
}

#[derive(Debug, Clone)]
struct TrackedTurn {
    turn: AgentTurn,
    payload: Value,
}

#[derive(Debug, Default)]
struct CoordinatorState {
    turns: HashMap<TurnId, TrackedTurn>,
    active_by_session: HashMap<SessionId, TurnId>,
    by_request: HashMap<(SessionId, RequestId), TurnId>,
}

#[derive(Debug, Clone, Default)]
pub struct TurnCoordinator {
    state: Arc<Mutex<CoordinatorState>>,
}

impl TurnCoordinator {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn start_turn(&self, request: TurnStartRequest) -> Result<TurnStartOutcome, AgentError> {
        let mut state = self.lock_state()?;
        let request_key = (request.session_id.clone(), request.request_id.clone());

        if let Some(turn_id) = state.by_request.get(&request_key) {
            let tracked = state
                .turns
                .get(turn_id)
                .expect("request index must reference a tracked turn");
            if tracked.payload != request.payload {
                return Err(AgentError::new(
                    AgentErrorCode::DuplicateRequest,
                    "request_id was already used with a different payload",
                ));
            }
            return Ok(TurnStartOutcome {
                turn: tracked.turn.clone(),
                replayed: true,
            });
        }

        if state.active_by_session.contains_key(&request.session_id) {
            return Err(AgentError::new(
                AgentErrorCode::SessionBusy,
                "session already has an active turn",
            ));
        }

        let turn = AgentTurn {
            id: TurnId::from(Uuid::new_v4().to_string()),
            session_id: request.session_id.clone(),
            request_id: request.request_id.clone(),
            status: TurnStatus::Created,
        };
        state
            .active_by_session
            .insert(request.session_id, turn.id.clone());
        state.by_request.insert(request_key, turn.id.clone());
        state.turns.insert(
            turn.id.clone(),
            TrackedTurn {
                turn: turn.clone(),
                payload: request.payload,
            },
        );
        Ok(TurnStartOutcome {
            turn,
            replayed: false,
        })
    }

    pub fn transition(&self, turn_id: &TurnId, next: TurnStatus) -> Result<AgentTurn, AgentError> {
        let mut state = self.lock_state()?;
        let tracked = state.turns.get_mut(turn_id).ok_or_else(turn_not_found)?;
        let mut machine = TurnStateMachine::new(tracked.turn.status);
        machine.transition(next)?;
        tracked.turn.status = next;
        let turn = tracked.turn.clone();
        if is_terminal(next) && state.active_by_session.get(&turn.session_id) == Some(turn_id) {
            state.active_by_session.remove(&turn.session_id);
        }
        Ok(turn)
    }

    pub fn release(&self, turn_id: &TurnId) -> Result<(), AgentError> {
        let mut state = self.lock_state()?;
        let session_id = state
            .turns
            .get(turn_id)
            .map(|tracked| tracked.turn.session_id.clone())
            .ok_or_else(turn_not_found)?;
        if state.active_by_session.get(&session_id) == Some(turn_id) {
            state.active_by_session.remove(&session_id);
        }
        Ok(())
    }

    fn lock_state(&self) -> Result<std::sync::MutexGuard<'_, CoordinatorState>, AgentError> {
        self.state.lock().map_err(|_| {
            AgentError::new(
                AgentErrorCode::SdkInternalError,
                "turn coordinator unavailable",
            )
        })
    }
}

fn turn_not_found() -> AgentError {
    AgentError::new(AgentErrorCode::TurnNotFound, "turn not found")
}

fn is_terminal(status: TurnStatus) -> bool {
    matches!(
        status,
        TurnStatus::Succeeded
            | TurnStatus::Failed
            | TurnStatus::Cancelled
            | TurnStatus::Interrupted
    )
}

fn is_legal_transition(from: TurnStatus, to: TurnStatus) -> bool {
    matches!(
        (from, to),
        (TurnStatus::Created, TurnStatus::Running)
            | (TurnStatus::Running, TurnStatus::WaitingApproval)
            | (TurnStatus::Running, TurnStatus::Cancelling)
            | (TurnStatus::Running, TurnStatus::Succeeded)
            | (TurnStatus::Running, TurnStatus::Failed)
            | (TurnStatus::Running, TurnStatus::Cancelled)
            | (TurnStatus::Running, TurnStatus::Interrupted)
            | (TurnStatus::WaitingApproval, TurnStatus::Running)
            | (TurnStatus::WaitingApproval, TurnStatus::Cancelling)
            | (TurnStatus::WaitingApproval, TurnStatus::Failed)
            | (TurnStatus::WaitingApproval, TurnStatus::Cancelled)
            | (TurnStatus::WaitingApproval, TurnStatus::Interrupted)
            | (TurnStatus::Cancelling, TurnStatus::Cancelled)
            | (TurnStatus::Cancelling, TurnStatus::Failed)
            | (TurnStatus::Cancelling, TurnStatus::Interrupted)
    )
}

fn status_name(status: TurnStatus) -> &'static str {
    match status {
        TurnStatus::Created => "created",
        TurnStatus::Running => "running",
        TurnStatus::WaitingApproval => "waiting_approval",
        TurnStatus::Cancelling => "cancelling",
        TurnStatus::Succeeded => "succeeded",
        TurnStatus::Failed => "failed",
        TurnStatus::Cancelled => "cancelled",
        TurnStatus::Interrupted => "interrupted",
    }
}
