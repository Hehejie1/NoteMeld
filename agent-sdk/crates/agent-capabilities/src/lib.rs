//! Progressive capability discovery contracts for the universal Agent SDK.

use std::{collections::BTreeMap, fmt, sync::Arc};

use agent_events::{AgentError, AgentErrorCode};
use async_trait::async_trait;
use serde::{de::Error as _, Deserialize, Deserializer, Serialize};
use serde_json::{Map, Value};

pub const MAX_DISCOVERY_RESULTS: usize = 20;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum DisclosureLevel {
    L0,
    L1,
    L2,
    L3,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CapabilityManifest {
    id: String,
    name: String,
    summary: String,
    description: String,
    input_schema: Value,
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
        manifest.validate()?;
        Ok(manifest)
    }

    pub fn id(&self) -> &str {
        &self.id
    }

    pub fn name(&self) -> &str {
        &self.name
    }

    pub fn summary(&self) -> &str {
        &self.summary
    }

    pub fn description(&self) -> &str {
        &self.description
    }

    pub fn input_schema(&self) -> &Value {
        &self.input_schema
    }

    fn validate(&self) -> Result<(), AgentError> {
        validate_capability_id(&self.id)?;
        if self.name.trim().is_empty()
            || self.summary.trim().is_empty()
            || self.description.trim().is_empty()
        {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "capability metadata must be nonempty",
            ));
        }
        if !self.input_schema.is_object() {
            return Err(AgentError::new(
                AgentErrorCode::InvalidInput,
                "capability input_schema must be a JSON object",
            ));
        }
        Ok(())
    }
}

#[derive(Deserialize)]
struct CapabilityManifestWire {
    id: String,
    name: String,
    summary: String,
    description: String,
    input_schema: Value,
}

impl<'de> Deserialize<'de> for CapabilityManifest {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let wire = CapabilityManifestWire::deserialize(deserializer)?;
        Self::try_new(
            wire.id,
            wire.name,
            wire.summary,
            wire.description,
            wire.input_schema,
        )
        .map_err(|error| D::Error::custom(error.message))
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

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct CapabilityInvocation {
    capability_id: String,
    arguments: Map<String, Value>,
}

impl CapabilityInvocation {
    pub fn try_new(capability_id: impl Into<String>, arguments: Value) -> Result<Self, AgentError> {
        let capability_id = capability_id.into();
        validate_capability_id(&capability_id)?;
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

    pub fn capability_id(&self) -> &str {
        &self.capability_id
    }

    pub fn arguments(&self) -> &Map<String, Value> {
        &self.arguments
    }

    fn validate(&self) -> Result<(), AgentError> {
        validate_capability_id(&self.capability_id)
    }
}

#[derive(Deserialize)]
struct CapabilityInvocationWire {
    capability_id: String,
    arguments: Value,
}

impl<'de> Deserialize<'de> for CapabilityInvocation {
    fn deserialize<D>(deserializer: D) -> Result<Self, D::Error>
    where
        D: Deserializer<'de>,
    {
        let wire = CapabilityInvocationWire::deserialize(deserializer)?;
        Self::try_new(wire.capability_id, wire.arguments)
            .map_err(|error| D::Error::custom(error.message))
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
            registration.manifest.validate()?;
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
            .take(MAX_DISCOVERY_RESULTS)
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
        invocation.validate()?;
        let provider = self
            .registrations
            .get(&invocation.capability_id)
            .map(|registered| Arc::clone(&registered.provider))
            .ok_or_else(|| capability_not_found(&invocation.capability_id))?;
        provider.invoke(invocation).await
    }
}

fn validate_capability_id(capability_id: &str) -> Result<(), AgentError> {
    let valid = capability_id.trim() == capability_id
        && capability_id
            .split_once(':')
            .is_some_and(|(namespace, local_name)| !namespace.is_empty() && !local_name.is_empty());
    if valid {
        Ok(())
    } else {
        Err(AgentError::new(
            AgentErrorCode::InvalidInput,
            "capability id must use namespace:name form",
        ))
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
