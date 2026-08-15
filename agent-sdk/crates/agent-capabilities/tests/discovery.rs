use std::sync::Arc;

use agent_capabilities::{
    CapabilityInvocation, CapabilityManifest, CapabilityProvider, CapabilityRegistration,
    CapabilityRegistry, DisclosureLevel,
};
use agent_events::{AgentError, AgentErrorCode};
use async_trait::async_trait;
use serde_json::{json, Value};

struct EchoProvider(&'static str);

#[async_trait]
impl CapabilityProvider for EchoProvider {
    async fn invoke(&self, invocation: CapabilityInvocation) -> Result<Value, AgentError> {
        Ok(json!({
            "provider": self.0,
            "capability_id": invocation.capability_id,
            "arguments": invocation.arguments,
        }))
    }
}

fn registration(id: &str, provider: &'static str) -> CapabilityRegistration {
    CapabilityRegistration::new(
        CapabilityManifest::try_new(
            id,
            format!("{id} name"),
            format!("{id} summary"),
            format!("{id} full description"),
            json!({"type": "object", "properties": {"query": {"type": "string"}}}),
        )
        .unwrap(),
        Arc::new(EchoProvider(provider)),
    )
}

#[test]
fn l0_and_l1_discovery_are_bounded_and_stably_sorted() {
    let registry = CapabilityRegistry::try_new(vec![
        registration("wiki:search", "wiki"),
        registration("builtin:clock", "builtin"),
        registration("mcp:lookup", "mcp"),
    ])
    .unwrap();

    let l0 = registry.list(DisclosureLevel::L0).unwrap();
    assert_eq!(
        l0.iter().map(|item| item.id.as_str()).collect::<Vec<_>>(),
        vec!["builtin:clock", "mcp:lookup", "wiki:search"]
    );
    assert!(l0.iter().all(|item| item.summary.is_none()));

    let l1 = registry.list(DisclosureLevel::L1).unwrap();
    assert_eq!(
        l1.iter().map(|item| item.id.as_str()).collect::<Vec<_>>(),
        vec!["builtin:clock", "mcp:lookup", "wiki:search"]
    );
    assert_eq!(l1[2].summary.as_deref(), Some("wiki:search summary"));
}

#[test]
fn l2_describe_exposes_only_the_selected_contract() {
    let registry = CapabilityRegistry::try_new(vec![
        registration("wiki:search", "wiki"),
        registration("skill:summarize", "skill"),
    ])
    .unwrap();

    let described = registry.describe("skill:summarize").unwrap();
    assert_eq!(described.disclosure_level, DisclosureLevel::L2);
    assert_eq!(described.id, "skill:summarize");
    assert_eq!(described.summary, "skill:summarize summary");
    assert_eq!(
        described.input_schema,
        json!({"type": "object", "properties": {"query": {"type": "string"}}})
    );
}

#[tokio::test]
async fn l3_invoke_routes_to_the_registered_host_provider() {
    let registry = CapabilityRegistry::try_new(vec![registration("wiki:search", "wiki")]).unwrap();
    let result = registry
        .invoke(
            CapabilityInvocation::try_new("wiki:search", json!({"query": "agent sdk"})).unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(
        result,
        json!({
            "provider": "wiki",
            "capability_id": "wiki:search",
            "arguments": {"query": "agent sdk"},
        })
    );
}

#[tokio::test]
async fn unknown_capabilities_and_invalid_levels_return_typed_errors() {
    let registry = CapabilityRegistry::try_new(vec![registration("wiki:search", "wiki")]).unwrap();

    let unknown = registry.describe("wiki:missing").unwrap_err();
    assert_eq!(unknown.code, AgentErrorCode::ToolFailed);
    assert_eq!(unknown.message, "capability not found");
    assert_eq!(unknown.details["capability_id"], "wiki:missing");

    let invalid_level = registry.list(DisclosureLevel::L2).unwrap_err();
    assert_eq!(invalid_level.code, AgentErrorCode::InvalidInput);
    assert_eq!(
        invalid_level.message,
        "list supports only L0 and L1 disclosure"
    );

    let invalid_arguments =
        CapabilityInvocation::try_new("wiki:search", json!(["not-object"])).unwrap_err();
    assert_eq!(invalid_arguments.code, AgentErrorCode::InvalidInput);
}

#[test]
fn duplicate_capability_identity_is_rejected() {
    let duplicate = CapabilityRegistry::try_new(vec![
        registration("wiki:search", "one"),
        registration("wiki:search", "two"),
    ])
    .unwrap_err();
    assert_eq!(duplicate.code, AgentErrorCode::InvalidInput);
    assert_eq!(duplicate.message, "duplicate capability id");
    assert_eq!(duplicate.details["capability_id"], "wiki:search");
}

#[test]
fn capability_identity_requires_a_nonempty_namespace_and_local_name() {
    for invalid in ["search", ":search", "wiki:", " wiki:search"] {
        let error = CapabilityManifest::try_new(
            invalid,
            "Search",
            "Search summary",
            "Search description",
            json!({"type": "object"}),
        )
        .unwrap_err();
        assert_eq!(error.code, AgentErrorCode::InvalidInput, "{invalid}");
        assert_eq!(
            error.message, "capability id must use namespace:name form",
            "{invalid}"
        );
    }
}
