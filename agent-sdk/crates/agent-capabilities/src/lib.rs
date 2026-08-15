//! Progressive capability discovery contracts for the universal Agent SDK.

use std::{collections::BTreeMap, fmt, sync::Arc};

use agent_events::{AgentError, AgentErrorCode};
use async_trait::async_trait;
use serde::{Deserialize, Serialize};
use serde_json::{Map, Value};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DisclosureLevel {
    L0,
    L1,
    L2,
    L3,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CapabilityManifest {
    pub id: String,
    pub name: String,
    pub summary: String,
    pub description: String,
    pub input_schema: Value,
}

impl CapabilityManifest {
    pub fn try_new(
        id: impl Into<String>,
        name: impl Into<String>,
        summary: impl Into<String>,
        description: impl Into<String>,
        input_schema: Value,
    ) -> Result<Self, AgentError> {
        let manifest = Self {
            id: id.into(),
            name: name.into(),
            summary: summary.into(),
            description: description.into(),
            input_schema,
        };
        let valid_identity = manifest.id.trim() == manifest.id
            && manifest
                .id
                .split_once(':')
                .is_some_and(|(namespace, local_name)| {
                    !namespace.is_empty() && !local_name.is_empty()
                });
        if !valid_identity {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "capability id must use namespace:name form",
            ));
        }
        if manifest.id.trim().is_empty()
            || manifest.name.trim().is_empty()
            || manifest.summary.trim().is_empty()
            || manifest.description.trim().is_empty()
        {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "capability metadata must be nonempty",
            ));
        }
        if !manifest.input_schema.is_object() {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "capability input_schema must be a JSON object",
            ));
        }
        Ok(manifest)
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct CapabilityListing {
    pub disclosure_level: DisclosureLevel,
    pub id: String,
    pub name: String,
    pub summary: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CapabilityDescription {
    pub disclosure_level: DisclosureLevel,
    pub id: String,
    pub name: String,
    pub summary: String,
    pub description: String,
    pub input_schema: Value,
}

#[derive(Debug, Clone, PartialEq)]
pub struct CapabilityInvocation {
    pub capability_id: String,
    pub arguments: Map<String, Value>,
}

impl CapabilityInvocation {
    pub fn try_new(capability_id: impl Into<String>, arguments: Value) -> Result<Self, AgentError> {
        let capability_id = capability_id.into();
        if capability_id.trim().is_empty() {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "capability_id must be nonempty",
            ));
        }
        let Value::Object(arguments) = arguments else {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "capability arguments must be a JSON object",
            ));
        };
        Ok(Self {
            capability_id,
            arguments,
        })
    }
}

#[async_trait]
pub trait CapabilityProvider: Send + Sync {
    async fn invoke(&self, invocation: CapabilityInvocation) -> Result<Value, AgentError>;
}

pub struct CapabilityRegistration {
    manifest: CapabilityManifest,
    provider: Arc<dyn CapabilityProvider>,
}

impl CapabilityRegistration {
    pub fn new(manifest: CapabilityManifest, provider: Arc<dyn CapabilityProvider>) -> Self {
        Self { manifest, provider }
    }
}

struct RegisteredCapability {
    manifest: CapabilityManifest,
    provider: Arc<dyn CapabilityProvider>,
}

pub struct CapabilityRegistry {
    registrations: BTreeMap<String, RegisteredCapability>,
}

impl fmt::Debug for CapabilityRegistry {
    fn fmt(&self, formatter: &mut fmt::Formatter<'_>) -> fmt::Result {
        formatter
            .debug_struct("CapabilityRegistry")
            .field(
                "capability_ids",
                &self.registrations.keys().collect::<Vec<_>>(),
            )
            .finish()
    }
}

impl CapabilityRegistry {
    pub fn try_new(registrations: Vec<CapabilityRegistration>) -> Result<Self, AgentError> {
        let mut by_id = BTreeMap::new();
        for registration in registrations {
            let id = registration.manifest.id.clone();
            if by_id
                .insert(
                    id.clone(),
                    RegisteredCapability {
                        manifest: registration.manifest,
                        provider: registration.provider,
                    },
                )
                .is_some()
            {
                let mut error =
                    AgentError::new(AgentErrorCode::InvalidInput, "duplicate capability id");
                error
                    .details
                    .insert("capability_id".to_owned(), Value::String(id));
                return Err(error);
            }
        }
        Ok(Self {
            registrations: by_id,
        })
    }

    pub fn list(&self, level: DisclosureLevel) -> Result<Vec<CapabilityListing>, AgentError> {
        if !matches!(level, DisclosureLevel::L0 | DisclosureLevel::L1) {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "list supports only L0 and L1 disclosure",
            ));
        }
        Ok(self
            .registrations
            .values()
            .map(|registered| CapabilityListing {
                disclosure_level: level,
                id: registered.manifest.id.clone(),
                name: registered.manifest.name.clone(),
                summary: (level == DisclosureLevel::L1)
                    .then(|| registered.manifest.summary.clone()),
            })
            .collect())
    }

    pub fn describe(&self, capability_id: &str) -> Result<CapabilityDescription, AgentError> {
        let registered = self
            .registrations
            .get(capability_id)
            .ok_or_else(|| capability_not_found(capability_id))?;
        Ok(CapabilityDescription {
            disclosure_level: DisclosureLevel::L2,
            id: registered.manifest.id.clone(),
            name: registered.manifest.name.clone(),
            summary: registered.manifest.summary.clone(),
            description: registered.manifest.description.clone(),
            input_schema: registered.manifest.input_schema.clone(),
        })
    }

    pub async fn invoke(&self, invocation: CapabilityInvocation) -> Result<Value, AgentError> {
        let provider = self
            .registrations
            .get(&invocation.capability_id)
            .map(|registered| Arc::clone(&registered.provider))
            .ok_or_else(|| capability_not_found(&invocation.capability_id))?;
        provider.invoke(invocation).await
    }
}

fn capability_not_found(capability_id: &str) -> AgentError {
    let mut error = AgentError::new(AgentErrorCode::ToolFailed, "capability not found");
    error.details.insert(
        "capability_id".to_owned(),
        Value::String(capability_id.to_owned()),
    );
    error
}
