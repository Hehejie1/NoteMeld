//! Stable, versioned wire contracts for the universal Agent SDK.

use chrono::DateTime;
use serde::{de::Error as _, ser::Error as _, Deserialize, Deserializer, Serialize, Serializer};
use serde_json::{Map, Value};
use uuid::Uuid;

pub const SCHEMA_VERSION: &str = "1";
pub const SDK_VERSION: &str = "0.1.0";

macro_rules! string_id {
    ($name:ident, $wire_name:literal) => {
        #[derive(Debug, Clone, PartialEq, Eq, Hash)]
        pub struct $name(pub String);

        impl From<String> for $name {
            fn from(value: String) -> Self {
                Self(value)
            }
        }

        impl From<&str> for $name {
            fn from(value: &str) -> Self {
                Self(value.to_owned())
            }
        }

        impl Serialize for $name {
            fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
            where
                S: Serializer,
            {
                validate_nonempty($wire_name, &self.0).map_err(S::Error::custom)?;
                serializer.serialize_str(&self.0)
            }
        }

        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
            where
                D: Deserializer<'de>,
            {
                let value = String::deserialize(deserializer)?;
                validate_nonempty($wire_name, &value).map_err(D::Error::custom)?;
                Ok(Self(value))
            }
        }
    };
}

string_id!(SessionId, "session_id");

macro_rules! uuid_id {
    ($name:ident, $wire_name:literal) => {
        #[derive(Debug, Clone, PartialEq, Eq, Hash)]
        pub struct $name(pub String);

        impl From<String> for $name {
            fn from(value: String) -> Self {
                Self(value)
            }
        }

        impl From<&str> for $name {
            fn from(value: &str) -> Self {
                Self(value.to_owned())
            }
        }

        impl Serialize for $name {
            fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
            where
                S: Serializer,
            {
                validate_uuid($wire_name, &self.0).map_err(S::Error::custom)?;
                serializer.serialize_str(&self.0)
            }
        }

        impl<'de> Deserialize<'de> for $name {
            fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
            where
                D: Deserializer<'de>,
            {
                let value = String::deserialize(deserializer)?;
                validate_uuid($wire_name, &value).map_err(D::Error::custom)?;
                Ok(Self(value))
            }
        }
    };
}

uuid_id!(TurnId, "turn_id");
uuid_id!(EventId, "event_id");
uuid_id!(RequestId, "request_id");

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum TurnStatus {
    Created,
    Running,
    WaitingApproval,
    Cancelling,
    Succeeded,
    Failed,
    Cancelled,
    Interrupted,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum ApprovalMode {
    Interactive,
    Deny,
    AllowSafe,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct TurnInput {
    pub text: String,
    pub attachments: Vec<Value>,
    pub context_refs: Vec<Value>,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ModelOverride {
    #[serde(
        serialize_with = "serialize_nonempty_provider_id",
        deserialize_with = "deserialize_nonempty_provider_id"
    )]
    pub provider_id: String,
    #[serde(
        serialize_with = "serialize_nonempty_model_name",
        deserialize_with = "deserialize_nonempty_model_name"
    )]
    pub model_name: String,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TurnRequest {
    #[serde(deserialize_with = "deserialize_schema_version")]
    pub schema_version: String,
    pub request_id: RequestId,
    pub session_id: SessionId,
    pub input: TurnInput,
    #[serde(deserialize_with = "deserialize_model_override")]
    pub model_override: Option<ModelOverride>,
    pub approval_mode: ApprovalMode,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AgentErrorCode {
    InvalidInput,
    AgentRuntimeUnavailable,
    AgentSchemaMismatch,
    SessionNotFound,
    SessionBusy,
    TurnNotFound,
    TurnTerminal,
    DuplicateRequest,
    ModelNotConfigured,
    ModelUnavailable,
    ContextBudgetExceeded,
    ApprovalRequired,
    ApprovalExpired,
    ToolFailed,
    Cancelled,
    Interrupted,
    InvalidSessionToken,
    SdkInternalError,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AgentError {
    pub code: AgentErrorCode,
    #[serde(
        serialize_with = "serialize_nonempty_message",
        deserialize_with = "deserialize_nonempty_message"
    )]
    pub message: String,
    #[serde(default, skip_serializing_if = "Map::is_empty")]
    pub details: Map<String, Value>,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

impl AgentError {
    pub fn new(code: AgentErrorCode, message: impl Into<String>) -> Self {
        Self {
            code,
            message: message.into(),
            details: Map::new(),
            extra: Map::new(),
        }
    }
}

impl Default for AgentError {
    fn default() -> Self {
        Self::new(AgentErrorCode::SdkInternalError, "internal error")
    }
}

macro_rules! payload {
    ($name:ident { $($field:ident : $ty:ty),* $(,)? }) => {
        #[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
        pub struct $name {
            $(
                #[serde(default, skip_serializing_if = "Option::is_none")]
                pub $field: Option<$ty>,
            )*
            #[serde(flatten)]
            pub extra: Map<String, Value>,
        }
    };
}

payload!(TurnStartedPayload { status: TurnStatus });
payload!(MessageStartedPayload {
    message_id: String,
    role: String,
});
payload!(MessageDeltaPayload {
    message_id: String,
    delta: String,
});
payload!(MessageCompletedPayload {
    message_id: String,
    role: String,
    content: Value,
});
payload!(ToolStartedPayload {
    call_id: String,
    tool_name: String,
    arguments_summary: Value,
});
payload!(ToolProgressPayload {
    call_id: String,
    message: String,
    progress: f64,
});
payload!(ToolCompletedPayload {
    call_id: String,
    tool_name: String,
    status: String,
    result_summary: Value,
});
payload!(ApprovalRequiredPayload {
    approval_id: String,
    call_id: String,
    action_digest: String,
    risk: String,
    summary: String,
    deadline: String,
});
payload!(ApprovalResolvedPayload {
    approval_id: String,
    decision: String,
});
payload!(UsageUpdatedPayload {
    input_tokens: u64,
    output_tokens: u64,
    total_tokens: u64,
});
payload!(TurnSucceededPayload { result: Value });

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize, Default)]
pub struct TurnFailedPayload {
    #[serde(default)]
    pub error: AgentError,
    #[serde(flatten)]
    pub extra: Map<String, Value>,
}

payload!(TurnCancelledPayload { reason: String });
payload!(TurnInterruptedPayload { reason: String });

#[derive(Debug, Clone, PartialEq)]
pub enum AgentEvent {
    TurnStarted(TurnStartedPayload),
    MessageStarted(MessageStartedPayload),
    MessageDelta(MessageDeltaPayload),
    MessageCompleted(MessageCompletedPayload),
    ToolStarted(ToolStartedPayload),
    ToolProgress(ToolProgressPayload),
    ToolCompleted(ToolCompletedPayload),
    ApprovalRequired(ApprovalRequiredPayload),
    ApprovalResolved(ApprovalResolvedPayload),
    UsageUpdated(UsageUpdatedPayload),
    TurnSucceeded(TurnSucceededPayload),
    TurnFailed(TurnFailedPayload),
    TurnCancelled(TurnCancelledPayload),
    TurnInterrupted(TurnInterruptedPayload),
    Unknown(UnknownEvent),
}

#[derive(Debug, Clone, PartialEq)]
pub struct UnknownEvent {
    pub event_type: String,
    pub payload: Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(tag = "type", content = "payload")]
enum KnownAgentEvent {
    #[serde(rename = "turn.started")]
    TurnStarted(TurnStartedPayload),
    #[serde(rename = "message.started")]
    MessageStarted(MessageStartedPayload),
    #[serde(rename = "message.delta")]
    MessageDelta(MessageDeltaPayload),
    #[serde(rename = "message.completed")]
    MessageCompleted(MessageCompletedPayload),
    #[serde(rename = "tool.started")]
    ToolStarted(ToolStartedPayload),
    #[serde(rename = "tool.progress")]
    ToolProgress(ToolProgressPayload),
    #[serde(rename = "tool.completed")]
    ToolCompleted(ToolCompletedPayload),
    #[serde(rename = "approval.required")]
    ApprovalRequired(ApprovalRequiredPayload),
    #[serde(rename = "approval.resolved")]
    ApprovalResolved(ApprovalResolvedPayload),
    #[serde(rename = "usage.updated")]
    UsageUpdated(UsageUpdatedPayload),
    #[serde(rename = "turn.succeeded")]
    TurnSucceeded(TurnSucceededPayload),
    #[serde(rename = "turn.failed")]
    TurnFailed(TurnFailedPayload),
    #[serde(rename = "turn.cancelled")]
    TurnCancelled(TurnCancelledPayload),
    #[serde(rename = "turn.interrupted")]
    TurnInterrupted(TurnInterruptedPayload),
}

impl Serialize for AgentEvent {
    fn serialize<S>(&self, serializer: S) -> Result<S::Ok, S::Error>
    where
        S: Serializer,
    {
        let known = match self {
            Self::TurnStarted(payload) => Some(KnownAgentEvent::TurnStarted(payload.clone())),
            Self::MessageStarted(payload) => Some(KnownAgentEvent::MessageStarted(payload.clone())),
            Self::MessageDelta(payload) => Some(KnownAgentEvent::MessageDelta(payload.clone())),
            Self::MessageCompleted(payload) => {
                Some(KnownAgentEvent::MessageCompleted(payload.clone()))
            }
            Self::ToolStarted(payload) => Some(KnownAgentEvent::ToolStarted(payload.clone())),
            Self::ToolProgress(payload) => Some(KnownAgentEvent::ToolProgress(payload.clone())),
            Self::ToolCompleted(payload) => Some(KnownAgentEvent::ToolCompleted(payload.clone())),
            Self::ApprovalRequired(payload) => {
                Some(KnownAgentEvent::ApprovalRequired(payload.clone()))
            }
            Self::ApprovalResolved(payload) => {
                Some(KnownAgentEvent::ApprovalResolved(payload.clone()))
            }
            Self::UsageUpdated(payload) => Some(KnownAgentEvent::UsageUpdated(payload.clone())),
            Self::TurnSucceeded(payload) => Some(KnownAgentEvent::TurnSucceeded(payload.clone())),
            Self::TurnFailed(payload) => Some(KnownAgentEvent::TurnFailed(payload.clone())),
            Self::TurnCancelled(payload) => Some(KnownAgentEvent::TurnCancelled(payload.clone())),
            Self::TurnInterrupted(payload) => {
                Some(KnownAgentEvent::TurnInterrupted(payload.clone()))
            }
            Self::Unknown(unknown) => {
                validate_nonempty("type", &unknown.event_type).map_err(S::Error::custom)?;
                if !unknown.payload.is_object() {
                    return Err(S::Error::custom("payload must be a JSON object"));
                }
                let mut wire = Map::new();
                wire.insert("type".to_owned(), Value::String(unknown.event_type.clone()));
                wire.insert("payload".to_owned(), unknown.payload.clone());
                return Value::Object(wire).serialize(serializer);
            }
        };
        known
            .expect("known event arm must set a value")
            .serialize(serializer)
    }
}

impl<'de> Deserialize<'de> for AgentEvent {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let wire = Value::deserialize(deserializer)?;
        let event_type = wire
            .get("type")
            .and_then(Value::as_str)
            .ok_or_else(|| D::Error::missing_field("type"))?;
        validate_nonempty("type", event_type).map_err(D::Error::custom)?;
        let payload = wire
            .get("payload")
            .cloned()
            .ok_or_else(|| D::Error::missing_field("payload"))?;
        if !payload.is_object() {
            return Err(D::Error::custom("payload must be a JSON object"));
        }

        let known = matches!(
            event_type,
            "turn.started"
                | "message.started"
                | "message.delta"
                | "message.completed"
                | "tool.started"
                | "tool.progress"
                | "tool.completed"
                | "approval.required"
                | "approval.resolved"
                | "usage.updated"
                | "turn.succeeded"
                | "turn.failed"
                | "turn.cancelled"
                | "turn.interrupted"
        );
        if !known {
            return Ok(Self::Unknown(UnknownEvent {
                event_type: event_type.to_owned(),
                payload,
            }));
        }

        let known: KnownAgentEvent = serde_json::from_value(wire).map_err(D::Error::custom)?;
        Ok(match known {
            KnownAgentEvent::TurnStarted(payload) => Self::TurnStarted(payload),
            KnownAgentEvent::MessageStarted(payload) => Self::MessageStarted(payload),
            KnownAgentEvent::MessageDelta(payload) => Self::MessageDelta(payload),
            KnownAgentEvent::MessageCompleted(payload) => Self::MessageCompleted(payload),
            KnownAgentEvent::ToolStarted(payload) => Self::ToolStarted(payload),
            KnownAgentEvent::ToolProgress(payload) => Self::ToolProgress(payload),
            KnownAgentEvent::ToolCompleted(payload) => Self::ToolCompleted(payload),
            KnownAgentEvent::ApprovalRequired(payload) => Self::ApprovalRequired(payload),
            KnownAgentEvent::ApprovalResolved(payload) => Self::ApprovalResolved(payload),
            KnownAgentEvent::UsageUpdated(payload) => Self::UsageUpdated(payload),
            KnownAgentEvent::TurnSucceeded(payload) => Self::TurnSucceeded(payload),
            KnownAgentEvent::TurnFailed(payload) => Self::TurnFailed(payload),
            KnownAgentEvent::TurnCancelled(payload) => Self::TurnCancelled(payload),
            KnownAgentEvent::TurnInterrupted(payload) => Self::TurnInterrupted(payload),
        })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct AgentEventEnvelope {
    #[serde(deserialize_with = "deserialize_schema_version")]
    pub schema_version: String,
    pub event_id: EventId,
    #[serde(
        serialize_with = "serialize_sequence",
        deserialize_with = "deserialize_sequence"
    )]
    pub sequence: u64,
    pub session_id: SessionId,
    pub turn_id: TurnId,
    #[serde(
        serialize_with = "serialize_utc_timestamp",
        deserialize_with = "deserialize_utc_timestamp"
    )]
    pub timestamp: String,
    #[serde(flatten)]
    pub event: AgentEvent,
}

fn validate_uuid(field: &str, value: &str) -> Result<(), String> {
    Uuid::parse_str(value)
        .map(|_| ())
        .map_err(|_| format!("{field} must be a UUID"))
}

fn validate_nonempty(field: &str, value: &str) -> Result<(), String> {
    if value.is_empty() {
        Err(format!("{field} must be nonempty"))
    } else {
        Ok(())
    }
}

macro_rules! nonempty_string_serde {
    ($serialize:ident, $deserialize:ident, $field:literal) => {
        fn $serialize<S>(value: &str, serializer: S) -> Result<S::Ok, S::Error>
        where
            S: Serializer,
        {
            validate_nonempty($field, value).map_err(S::Error::custom)?;
            serializer.serialize_str(value)
        }

        fn $deserialize<'de, D>(deserializer: D) -> Result<String, D::Error>
        where
            D: Deserializer<'de>,
        {
            let value = String::deserialize(deserializer)?;
            validate_nonempty($field, &value).map_err(D::Error::custom)?;
            Ok(value)
        }
    };
}

nonempty_string_serde!(
    serialize_nonempty_provider_id,
    deserialize_nonempty_provider_id,
    "provider_id"
);
nonempty_string_serde!(
    serialize_nonempty_model_name,
    deserialize_nonempty_model_name,
    "model_name"
);
nonempty_string_serde!(
    serialize_nonempty_message,
    deserialize_nonempty_message,
    "message"
);

fn deserialize_model_override<'de, D>(deserializer: D) -> Result<Option<ModelOverride>, D::Error>
where
    D: Deserializer<'de>,
{
    Option::<ModelOverride>::deserialize(deserializer)
}

fn serialize_sequence<S>(sequence: &u64, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    if *sequence == 0 {
        return Err(S::Error::custom("sequence must be greater than zero"));
    }
    serializer.serialize_u64(*sequence)
}

fn deserialize_sequence<'de, D>(deserializer: D) -> Result<u64, D::Error>
where
    D: Deserializer<'de>,
{
    let sequence = u64::deserialize(deserializer)?;
    if sequence == 0 {
        return Err(D::Error::custom("sequence must be greater than zero"));
    }
    Ok(sequence)
}

fn validate_utc_timestamp(timestamp: &str) -> Result<(), String> {
    let parsed = DateTime::parse_from_rfc3339(timestamp)
        .map_err(|_| "timestamp must be RFC3339".to_owned())?;
    if parsed.offset().local_minus_utc() != 0
        || !(timestamp.ends_with('Z') || timestamp.ends_with("+00:00"))
    {
        return Err("timestamp must use UTC".to_owned());
    }
    Ok(())
}

fn serialize_utc_timestamp<S>(timestamp: &str, serializer: S) -> Result<S::Ok, S::Error>
where
    S: Serializer,
{
    validate_utc_timestamp(timestamp).map_err(S::Error::custom)?;
    serializer.serialize_str(timestamp)
}

fn deserialize_utc_timestamp<'de, D>(deserializer: D) -> Result<String, D::Error>
where
    D: Deserializer<'de>,
{
    let timestamp = String::deserialize(deserializer)?;
    validate_utc_timestamp(&timestamp).map_err(D::Error::custom)?;
    Ok(timestamp)
}

fn deserialize_schema_version<'de, D>(deserializer: D) -> Result<String, D::Error>
where
    D: Deserializer<'de>,
{
    let version = String::deserialize(deserializer)?;
    if version == SCHEMA_VERSION {
        Ok(version)
    } else {
        Err(D::Error::custom(format!(
            "schema_version must be {SCHEMA_VERSION:?}"
        )))
    }
}
