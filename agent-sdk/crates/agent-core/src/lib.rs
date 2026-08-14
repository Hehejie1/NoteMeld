//! Canonical, platform-neutral Agent loop.

mod context;
mod r#loop;

pub use context::{AgentDiagnostic, AgentEventSink, AgentMessage, TurnOutcome};
pub use r#loop::{AgentRuntime, AgentRuntimeConfig};
pub use tokio_util::sync::CancellationToken;
