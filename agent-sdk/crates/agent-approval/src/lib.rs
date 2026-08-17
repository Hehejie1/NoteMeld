//! Approval policy and lifecycle owned by the SDK, independent of NoteMeld.

use agent_events::ApprovalMode;
use serde::{Deserialize, Serialize};
use std::collections::HashMap;
use std::time::{Duration, Instant};
use tokio::sync::oneshot;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Decision { Approve, Deny, Expired, Cancelled }

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ApprovalState { Pending, Approved, Denied, Expired, Cancelled }

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ApprovalRequest {
    pub approval_id: String,
    pub turn_id: String,
    pub call_id: String,
    pub risk: String,
    pub summary: String,
    pub deadline: Instant,
}

struct Pending { request: ApprovalRequest, result: Option<oneshot::Sender<Decision>> }

#[derive(Default)]
pub struct ApprovalManager { pending: HashMap<String, Pending> }

impl ApprovalManager {
    pub fn new() -> Self { Self::default() }

    pub fn requires_approval(mode: ApprovalMode, risk: &str, safe: bool) -> bool {
        match mode { ApprovalMode::Deny => true, ApprovalMode::Interactive => !safe || risk != "safe", ApprovalMode::AllowSafe => !safe || risk != "safe" }
    }

    pub fn request(&mut self, request: ApprovalRequest) -> (ApprovalRequest, oneshot::Receiver<Decision>) {
        let (tx, rx) = oneshot::channel();
        let id = request.approval_id.clone();
        let copy = request.clone();
        self.pending.insert(id, Pending { request, result: Some(tx) });
        (copy, rx)
    }

    pub fn resolve(&mut self, approval_id: &str, decision: Decision) -> bool {
        let Some(mut pending) = self.pending.remove(approval_id) else { return false };
        pending.result.take().is_some_and(|tx| tx.send(decision).is_ok())
    }

    pub fn expire(&mut self, now: Instant) -> Vec<ApprovalRequest> {
        let ids: Vec<_> = self.pending.iter().filter(|(_, p)| p.request.deadline <= now).map(|(id, _)| id.clone()).collect();
        ids.into_iter().filter_map(|id| {
            let mut pending = self.pending.remove(&id)?;
            let request = pending.request.clone();
            if let Some(tx) = pending.result.take() { let _ = tx.send(Decision::Expired); }
            Some(request)
        }).collect()
    }

    pub fn cancel_turn(&mut self, turn_id: &str) -> usize {
        let ids: Vec<_> = self.pending.iter().filter(|(_, p)| p.request.turn_id == turn_id).map(|(id, _)| id.clone()).collect();
        let count = ids.len();
        for id in ids { self.resolve(&id, Decision::Cancelled); }
        count
    }

    pub fn len(&self) -> usize { self.pending.len() }
    pub fn is_empty(&self) -> bool { self.pending.is_empty() }
}

pub fn deadline_after(seconds: u64) -> Instant { Instant::now() + Duration::from_secs(seconds) }

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn dangerous_actions_require_approval() {
        assert!(ApprovalManager::requires_approval(ApprovalMode::Interactive, "high", false));
        assert!(!ApprovalManager::requires_approval(ApprovalMode::AllowSafe, "safe", true));
        assert!(ApprovalManager::requires_approval(ApprovalMode::Deny, "safe", true));
    }
    #[tokio::test]
    async fn resolve_is_idempotent_and_cancel_wins() {
        let mut manager = ApprovalManager::new();
        let (_, rx) = manager.request(ApprovalRequest { approval_id: "a".into(), turn_id: "t".into(), call_id: "c".into(), risk: "high".into(), summary: "write".into(), deadline: deadline_after(60) });
        assert_eq!(manager.cancel_turn("t"), 1);
        assert!(!manager.resolve("a", Decision::Approve));
        assert_eq!(rx.await.unwrap(), Decision::Cancelled);
    }
}
