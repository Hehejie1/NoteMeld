//! Stable, versioned wire contracts for the universal Agent SDK.

use serde::{de::Error as _, Deserialize, Deserializer, Serialize, Serializer};
use serde_json::{Map, Value};

pub const SCHEMA_VERSION: &str = "1";
pub const SDK_VERSION: &str = "0.1.0";

macro_rules! string_id {
    ($name:ident) => {
        #[derive(Debug, Clone, PartialEq, Eq, Hash, Serialize, Deserialize)]
        #[serde(transparent)]
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
    };
}

string_id!(SessionId);
string_id!(TurnId);
string_id!(EventId);
string_id!(RequestId);

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
    #[serde(default)]
    pub text: String,
    #[serde(default)]
    pub attachments: Vec<Value>,
    #[serde(default)]
    pub context_refs: Vec<Value>,
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
    pub model_override: Option<Value>,
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
    pub message: String,
    #[serde(default)]
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
        Self::new(AgentErrorCode::SdkInternalError, String::new())
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
        let payload = wire
            .get("payload")
            .cloned()
            .ok_or_else(|| D::Error::missing_field("payload"))?;

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
    pub sequence: u64,
    pub session_id: SessionId,
    pub turn_id: TurnId,
    pub timestamp: String,
    #[serde(flatten)]
    pub event: AgentEvent,
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
