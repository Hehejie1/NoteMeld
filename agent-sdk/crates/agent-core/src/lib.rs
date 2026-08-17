//! Canonical, platform-neutral Agent loop.

mod context;
mod context_policy;
mod r#loop;

pub use context::{AgentDiagnostic, AgentEventSink, AgentMessage, TurnOutcome};
pub use context_policy::{ContextBudget, ContextPolicy, ContextTrimDiagnostic};
pub use r#loop::{AgentRuntime, AgentRuntimeConfig};
pub use tokio_util::sync::CancellationToken;
