//! Reference persistence contracts for the universal Agent SDK.

use std::{
    path::Path,
    sync::{Mutex, MutexGuard},
    time::Duration,
};

use agent_events::{
    AgentError, AgentErrorCode, AgentEvent, AgentEventEnvelope, EventId, RequestId, SessionId,
    TurnId, TurnStatus, SCHEMA_VERSION,
};
use rusqlite::{params, Connection, ErrorCode, OptionalExtension, Row, TransactionBehavior};
use serde_json::{json, Value};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredSession {
    pub id: SessionId,
}

impl StoredSession {
    pub fn new(id: SessionId) -> Self {
        Self { id }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StoredTurn {
    pub id: TurnId,
    pub session_id: SessionId,
    pub request_id: RequestId,
    pub status: TurnStatus,
    pub model_provider_id: Option<String>,
    pub model_name: Option<String>,
    pub error_code: Option<AgentErrorCode>,
    pub error_message: Option<String>,
    pub created_at: String,
    pub started_at: Option<String>,
    pub finished_at: Option<String>,
    pub updated_at: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum TurnWriteOutcome {
    Inserted,
    Replayed(Box<StoredTurn>),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EventWriteOutcome {
    Inserted,
    Replayed,
}

pub trait SessionStore {
    fn insert_session(&self, session: &StoredSession) -> Result<(), AgentError>;
    fn insert_turn(&self, turn: &StoredTurn) -> Result<TurnWriteOutcome, AgentError>;
    fn get_turn(&self, turn_id: &TurnId) -> Result<Option<StoredTurn>, AgentError>;
}

pub trait EventStore {
    fn append_event(&self, envelope: &AgentEventEnvelope) -> Result<EventWriteOutcome, AgentError>;
    fn replay_events(
        &self,
        turn_id: &TurnId,
        after_sequence: u64,
    ) -> Result<Vec<AgentEventEnvelope>, AgentError>;
}

pub struct ReferenceSqliteStore {
    connection: Mutex<Connection>,
}

impl ReferenceSqliteStore {
    pub fn open(path: impl AsRef<Path>) -> Result<Self, AgentError> {
        let connection = Connection::open(path).map_err(sqlite_error)?;
        Self::initialize(connection)
    }

    pub fn open_in_memory() -> Result<Self, AgentError> {
        let connection = Connection::open_in_memory().map_err(sqlite_error)?;
        Self::initialize(connection)
    }

    fn initialize(connection: Connection) -> Result<Self, AgentError> {
        connection
            .busy_timeout(Duration::from_secs(2))
            .map_err(sqlite_error)?;
        connection
            .execute_batch(
                "PRAGMA foreign_keys = ON;
                 CREATE TABLE IF NOT EXISTS reference_sessions (
                    id TEXT PRIMARY KEY NOT NULL
                 );
                 CREATE TABLE IF NOT EXISTS agent_turns (
                    id TEXT PRIMARY KEY NOT NULL,
                    session_id TEXT NOT NULL REFERENCES reference_sessions(id),
                    request_id TEXT NOT NULL,
                    status TEXT NOT NULL CHECK(status IN (
                        'created', 'running', 'waiting_approval', 'cancelling',
                        'succeeded', 'failed', 'cancelled', 'interrupted'
                    )),
                    model_provider_id TEXT,
                    model_name TEXT,
                    error_code TEXT,
                    error_message TEXT,
                    created_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    updated_at TEXT NOT NULL,
                    UNIQUE(session_id, request_id)
                 );
                 CREATE INDEX IF NOT EXISTS idx_agent_turns_session
                    ON agent_turns(session_id);
                 CREATE TABLE IF NOT EXISTS agent_events (
                    event_id TEXT PRIMARY KEY NOT NULL,
                    turn_id TEXT NOT NULL REFERENCES agent_turns(id),
                    sequence INTEGER NOT NULL CHECK(sequence > 0),
                    event_type TEXT NOT NULL,
                    payload_json TEXT NOT NULL CHECK(json_valid(payload_json)),
                    created_at TEXT NOT NULL,
                    UNIQUE(turn_id, sequence)
                 );
                 CREATE INDEX IF NOT EXISTS idx_agent_events_turn
                    ON agent_events(turn_id, sequence);",
            )
            .map_err(sqlite_error)?;
        Ok(Self {
            connection: Mutex::new(connection),
        })
    }

    fn lock(&self) -> Result<MutexGuard<'_, Connection>, AgentError> {
        self.connection.lock().map_err(|_| {
            AgentError::new(
                AgentErrorCode::SdkInternalError,
                "reference sqlite store unavailable",
            )
        })
    }
}

impl SessionStore for ReferenceSqliteStore {
    fn insert_session(&self, session: &StoredSession) -> Result<(), AgentError> {
        validate_session_id(&session.id)?;
        self.lock()?
            .execute(
                "INSERT OR IGNORE INTO reference_sessions(id) VALUES (?1)",
                params![session.id.0],
            )
            .map_err(sqlite_error)?;
        Ok(())
    }

    fn insert_turn(&self, turn: &StoredTurn) -> Result<TurnWriteOutcome, AgentError> {
        validate_turn(turn)?;
        let mut connection = self.lock()?;
        let transaction = connection
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(sqlite_error)?;

        if let Some(existing) =
            query_turn_by_request(&transaction, &turn.session_id.0, &turn.request_id.0)?
        {
            if existing == *turn {
                transaction.commit().map_err(sqlite_error)?;
                return Ok(TurnWriteOutcome::Replayed(Box::new(existing)));
            }
            return Err(AgentError::new(
                AgentErrorCode::DuplicateRequest,
                "session request_id already belongs to another turn",
            ));
        }

        if let Some(existing) = query_turn_by_id(&transaction, &turn.id.0)? {
            if existing == *turn {
                transaction.commit().map_err(sqlite_error)?;
                return Ok(TurnWriteOutcome::Replayed(Box::new(existing)));
            }
            return Err(AgentError::new(
                AgentErrorCode::DuplicateRequest,
                "turn_id already identifies a different turn",
            ));
        }

        let session_exists: bool = transaction
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM reference_sessions WHERE id = ?1)",
                params![turn.session_id.0],
                |row| row.get(0),
            )
            .map_err(sqlite_error)?;
        if !session_exists {
            return Err(AgentError::new(
                AgentErrorCode::SessionNotFound,
                "session not found",
            ));
        }

        transaction
            .execute(
                "INSERT INTO agent_turns(
                    id, session_id, request_id, status, model_provider_id, model_name,
                    error_code, error_message, created_at, started_at, finished_at, updated_at
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7, ?8, ?9, ?10, ?11, ?12)",
                params![
                    turn.id.0,
                    turn.session_id.0,
                    turn.request_id.0,
                    status_name(turn.status),
                    turn.model_provider_id,
                    turn.model_name,
                    turn.error_code.map(error_code_name),
                    turn.error_message,
                    turn.created_at,
                    turn.started_at,
                    turn.finished_at,
                    turn.updated_at,
                ],
            )
            .map_err(sqlite_error)?;
        transaction.commit().map_err(sqlite_error)?;
        Ok(TurnWriteOutcome::Inserted)
    }

    fn get_turn(&self, turn_id: &TurnId) -> Result<Option<StoredTurn>, AgentError> {
        validate_turn_id(turn_id)?;
        let connection = self.lock()?;
        query_turn_by_id(&connection, &turn_id.0)
    }
}

impl EventStore for ReferenceSqliteStore {
    fn append_event(&self, envelope: &AgentEventEnvelope) -> Result<EventWriteOutcome, AgentError> {
        if envelope.schema_version != SCHEMA_VERSION {
            return Err(AgentError::new(
                AgentErrorCode::AgentSchemaMismatch,
                "event schema_version must be \"1\"",
            ));
        }
        let sequence = sequence_to_i64(envelope.sequence)?;
        let wire = serde_json::to_value(envelope).map_err(wire_error)?;
        let event_type = wire
            .get("type")
            .and_then(Value::as_str)
            .expect("validated AgentEvent wire has type")
            .to_owned();
        let payload = wire
            .get("payload")
            .cloned()
            .expect("validated AgentEvent wire has payload");
        let payload_json = serde_json::to_string(&payload).map_err(wire_error)?;

        let mut connection = self.lock()?;
        let transaction = connection
            .transaction_with_behavior(TransactionBehavior::Immediate)
            .map_err(sqlite_error)?;
        let parent_session: Option<String> = transaction
            .query_row(
                "SELECT session_id FROM agent_turns WHERE id = ?1",
                params![envelope.turn_id.0],
                |row| row.get(0),
            )
            .optional()
            .map_err(sqlite_error)?;
        let Some(parent_session) = parent_session else {
            return Err(AgentError::new(
                AgentErrorCode::TurnNotFound,
                "turn not found",
            ));
        };
        if parent_session != envelope.session_id.0 {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "event session_id does not match its turn",
            ));
        }

        if let Some(existing) = query_event_by_id(&transaction, &envelope.event_id.0)? {
            if existing == *envelope {
                transaction.commit().map_err(sqlite_error)?;
                return Ok(EventWriteOutcome::Replayed);
            }
            return Err(AgentError::new(
                AgentErrorCode::DuplicateRequest,
                "event_id already identifies a different event",
            ));
        }

        if let Some(existing) =
            query_event_by_sequence(&transaction, &envelope.turn_id.0, envelope.sequence)?
        {
            if existing == *envelope {
                transaction.commit().map_err(sqlite_error)?;
                return Ok(EventWriteOutcome::Replayed);
            }
            return Err(AgentError::new(
                AgentErrorCode::DuplicateRequest,
                "turn sequence already contains a different event",
            ));
        }

        let last_sequence: i64 = transaction
            .query_row(
                "SELECT COALESCE(MAX(sequence), 0) FROM agent_events WHERE turn_id = ?1",
                params![envelope.turn_id.0],
                |row| row.get(0),
            )
            .map_err(sqlite_error)?;
        let next_sequence = last_sequence.checked_add(1).ok_or_else(|| {
            let mut error = AgentError::new(
                AgentErrorCode::InvalidInput,
                "event sequence space is exhausted",
            );
            error.details.insert(
                "reason".to_owned(),
                Value::String("sequence_exhausted".to_owned()),
            );
            error
        })?;
        if sequence != next_sequence {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "event sequence must append without gaps",
            ));
        }

        transaction
            .execute(
                "INSERT INTO agent_events(
                    event_id, turn_id, sequence, event_type, payload_json, created_at
                 ) VALUES (?1, ?2, ?3, ?4, ?5, ?6)",
                params![
                    envelope.event_id.0,
                    envelope.turn_id.0,
                    sequence,
                    event_type,
                    payload_json,
                    envelope.timestamp,
                ],
            )
            .map_err(sqlite_error)?;
        transaction.commit().map_err(sqlite_error)?;
        Ok(EventWriteOutcome::Inserted)
    }

    fn replay_events(
        &self,
        turn_id: &TurnId,
        after_sequence: u64,
    ) -> Result<Vec<AgentEventEnvelope>, AgentError> {
        validate_turn_id(turn_id)?;
        let connection = self.lock()?;
        let turn_exists: bool = connection
            .query_row(
                "SELECT EXISTS(SELECT 1 FROM agent_turns WHERE id = ?1)",
                params![turn_id.0],
                |row| row.get(0),
            )
            .map_err(sqlite_error)?;
        if !turn_exists {
            return Err(AgentError::new(
                AgentErrorCode::TurnNotFound,
                "turn not found",
            ));
        }
        if after_sequence > i64::MAX as u64 {
            return Ok(Vec::new());
        }

        let mut statement = connection
            .prepare(
                "SELECT e.event_id, e.turn_id, e.sequence, e.event_type, e.payload_json,
                        e.created_at, t.session_id
                 FROM agent_events e
                 JOIN agent_turns t ON t.id = e.turn_id
                 WHERE e.turn_id = ?1 AND e.sequence > ?2
                 ORDER BY e.sequence ASC",
            )
            .map_err(sqlite_error)?;
        let rows = statement
            .query_map(params![turn_id.0, after_sequence as i64], event_from_row)
            .map_err(sqlite_error)?;
        rows.collect::<Result<Vec<_>, _>>().map_err(sqlite_error)
    }
}

fn query_turn_by_id(
    connection: &Connection,
    turn_id: &str,
) -> Result<Option<StoredTurn>, AgentError> {
    connection
        .query_row(
            "SELECT id, session_id, request_id, status, model_provider_id, model_name,
                    error_code, error_message, created_at, started_at, finished_at, updated_at
             FROM agent_turns WHERE id = ?1",
            params![turn_id],
            turn_from_row,
        )
        .optional()
        .map_err(sqlite_error)
}

fn query_turn_by_request(
    connection: &Connection,
    session_id: &str,
    request_id: &str,
) -> Result<Option<StoredTurn>, AgentError> {
    connection
        .query_row(
            "SELECT id, session_id, request_id, status, model_provider_id, model_name,
                    error_code, error_message, created_at, started_at, finished_at, updated_at
             FROM agent_turns WHERE session_id = ?1 AND request_id = ?2",
            params![session_id, request_id],
            turn_from_row,
        )
        .optional()
        .map_err(sqlite_error)
}

fn turn_from_row(row: &Row<'_>) -> rusqlite::Result<StoredTurn> {
    let status: String = row.get(3)?;
    let error_code: Option<String> = row.get(6)?;
    Ok(StoredTurn {
        id: TurnId::from(row.get::<_, String>(0)?),
        session_id: SessionId::from(row.get::<_, String>(1)?),
        request_id: RequestId::from(row.get::<_, String>(2)?),
        status: parse_status(&status).map_err(conversion_error)?,
        model_provider_id: row.get(4)?,
        model_name: row.get(5)?,
        error_code: error_code
            .as_deref()
            .map(parse_error_code)
            .transpose()
            .map_err(conversion_error)?,
        error_message: row.get(7)?,
        created_at: row.get(8)?,
        started_at: row.get(9)?,
        finished_at: row.get(10)?,
        updated_at: row.get(11)?,
    })
}

fn query_event_by_id(
    connection: &Connection,
    event_id: &str,
) -> Result<Option<AgentEventEnvelope>, AgentError> {
    connection
        .query_row(
            "SELECT e.event_id, e.turn_id, e.sequence, e.event_type, e.payload_json,
                    e.created_at, t.session_id
             FROM agent_events e
             JOIN agent_turns t ON t.id = e.turn_id
             WHERE e.event_id = ?1",
            params![event_id],
            event_from_row,
        )
        .optional()
        .map_err(sqlite_error)
}

fn query_event_by_sequence(
    connection: &Connection,
    turn_id: &str,
    sequence: u64,
) -> Result<Option<AgentEventEnvelope>, AgentError> {
    let sequence = sequence_to_i64(sequence)?;
    connection
        .query_row(
            "SELECT e.event_id, e.turn_id, e.sequence, e.event_type, e.payload_json,
                    e.created_at, t.session_id
             FROM agent_events e
             JOIN agent_turns t ON t.id = e.turn_id
             WHERE e.turn_id = ?1 AND e.sequence = ?2",
            params![turn_id, sequence],
            event_from_row,
        )
        .optional()
        .map_err(sqlite_error)
}

fn event_from_row(row: &Row<'_>) -> rusqlite::Result<AgentEventEnvelope> {
    let event_type: String = row.get(3)?;
    let payload_json: String = row.get(4)?;
    let payload: Value = serde_json::from_str(&payload_json).map_err(conversion_error)?;
    let event: AgentEvent = serde_json::from_value(json!({
        "type": event_type,
        "payload": payload,
    }))
    .map_err(conversion_error)?;
    let sequence: i64 = row.get(2)?;
    let sequence = u64::try_from(sequence).map_err(conversion_error)?;
    Ok(AgentEventEnvelope {
        schema_version: SCHEMA_VERSION.to_owned(),
        event_id: EventId::from(row.get::<_, String>(0)?),
        turn_id: TurnId::from(row.get::<_, String>(1)?),
        sequence,
        timestamp: row.get(5)?,
        session_id: SessionId::from(row.get::<_, String>(6)?),
        event,
    })
}

fn validate_session_id(session_id: &SessionId) -> Result<(), AgentError> {
    serde_json::to_value(session_id)
        .map(|_| ())
        .map_err(wire_error)
}

fn validate_turn_id(turn_id: &TurnId) -> Result<(), AgentError> {
    serde_json::to_value(turn_id)
        .map(|_| ())
        .map_err(wire_error)
}

fn validate_turn(turn: &StoredTurn) -> Result<(), AgentError> {
    validate_turn_id(&turn.id)?;
    validate_session_id(&turn.session_id)?;
    serde_json::to_value(&turn.request_id)
        .map(|_| ())
        .map_err(wire_error)
}

fn sequence_to_i64(sequence: u64) -> Result<i64, AgentError> {
    i64::try_from(sequence).map_err(|_| {
        AgentError::new(
            AgentErrorCode::InvalidInput,
            "event sequence exceeds reference SQLite range",
        )
    })
}

fn conversion_error(error: impl std::error::Error + Send + Sync + 'static) -> rusqlite::Error {
    rusqlite::Error::FromSqlConversionFailure(0, rusqlite::types::Type::Text, Box::new(error))
}

fn wire_error(_error: serde_json::Error) -> AgentError {
    AgentError::new(
        AgentErrorCode::InvalidInput,
        "invalid versioned Agent wire value",
    )
}

fn sqlite_error(error: rusqlite::Error) -> AgentError {
    if matches!(
        error.sqlite_error_code(),
        Some(ErrorCode::DatabaseBusy | ErrorCode::DatabaseLocked)
    ) {
        return AgentError::new(
            AgentErrorCode::SdkInternalError,
            "reference sqlite database is busy",
        );
    }
    AgentError::new(
        AgentErrorCode::SdkInternalError,
        "reference sqlite operation failed",
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

fn parse_status(status: &str) -> Result<TurnStatus, std::io::Error> {
    match status {
        "created" => Ok(TurnStatus::Created),
        "running" => Ok(TurnStatus::Running),
        "waiting_approval" => Ok(TurnStatus::WaitingApproval),
        "cancelling" => Ok(TurnStatus::Cancelling),
        "succeeded" => Ok(TurnStatus::Succeeded),
        "failed" => Ok(TurnStatus::Failed),
        "cancelled" => Ok(TurnStatus::Cancelled),
        "interrupted" => Ok(TurnStatus::Interrupted),
        _ => Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "invalid turn status",
        )),
    }
}

fn error_code_name(code: AgentErrorCode) -> &'static str {
    match code {
        AgentErrorCode::InvalidInput => "invalid_input",
        AgentErrorCode::AgentRuntimeUnavailable => "agent_runtime_unavailable",
        AgentErrorCode::AgentSchemaMismatch => "agent_schema_mismatch",
        AgentErrorCode::SessionNotFound => "session_not_found",
        AgentErrorCode::SessionBusy => "session_busy",
        AgentErrorCode::TurnNotFound => "turn_not_found",
        AgentErrorCode::TurnTerminal => "turn_terminal",
        AgentErrorCode::DuplicateRequest => "duplicate_request",
        AgentErrorCode::ModelNotConfigured => "model_not_configured",
        AgentErrorCode::ModelUnavailable => "model_unavailable",
        AgentErrorCode::ContextBudgetExceeded => "context_budget_exceeded",
        AgentErrorCode::ApprovalRequired => "approval_required",
        AgentErrorCode::ApprovalExpired => "approval_expired",
        AgentErrorCode::ToolFailed => "tool_failed",
        AgentErrorCode::Cancelled => "cancelled",
        AgentErrorCode::Interrupted => "interrupted",
        AgentErrorCode::InvalidSessionToken => "invalid_session_token",
        AgentErrorCode::SdkInternalError => "sdk_internal_error",
    }
}

fn parse_error_code(code: &str) -> Result<AgentErrorCode, std::io::Error> {
    match code {
        "invalid_input" => Ok(AgentErrorCode::InvalidInput),
        "agent_runtime_unavailable" => Ok(AgentErrorCode::AgentRuntimeUnavailable),
        "agent_schema_mismatch" => Ok(AgentErrorCode::AgentSchemaMismatch),
        "session_not_found" => Ok(AgentErrorCode::SessionNotFound),
        "session_busy" => Ok(AgentErrorCode::SessionBusy),
        "turn_not_found" => Ok(AgentErrorCode::TurnNotFound),
        "turn_terminal" => Ok(AgentErrorCode::TurnTerminal),
        "duplicate_request" => Ok(AgentErrorCode::DuplicateRequest),
        "model_not_configured" => Ok(AgentErrorCode::ModelNotConfigured),
        "model_unavailable" => Ok(AgentErrorCode::ModelUnavailable),
        "context_budget_exceeded" => Ok(AgentErrorCode::ContextBudgetExceeded),
        "approval_required" => Ok(AgentErrorCode::ApprovalRequired),
        "approval_expired" => Ok(AgentErrorCode::ApprovalExpired),
        "tool_failed" => Ok(AgentErrorCode::ToolFailed),
        "cancelled" => Ok(AgentErrorCode::Cancelled),
        "interrupted" => Ok(AgentErrorCode::Interrupted),
        "invalid_session_token" => Ok(AgentErrorCode::InvalidSessionToken),
        "sdk_internal_error" => Ok(AgentErrorCode::SdkInternalError),
        _ => Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "invalid agent error code",
        )),
    }
}
