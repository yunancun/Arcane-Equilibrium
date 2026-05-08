//! Agent Spine rollout mode.

use serde::{Deserialize, Serialize};
use std::str::FromStr;

pub const RUNTIME_MODE_ENV: &str = "OPENCLAW_AGENT_SPINE_RUNTIME_MODE";

/// Agent Decision Spine rollout mode.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize, Default)]
#[serde(rename_all = "snake_case")]
pub enum AgentSpineMode {
    /// No spine writes or enforcement.
    #[default]
    Disabled,
    /// Write shadow lineage where wired; never change trading behavior.
    Shadow,
    /// Compute shadow allow/reject comparisons, but do not become authority.
    Canary,
    /// Primary typed lineage. Reserved for a later explicit cutover.
    Primary,
}

impl AgentSpineMode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::Disabled => "disabled",
            Self::Shadow => "shadow",
            Self::Canary => "canary",
            Self::Primary => "primary",
        }
    }

    pub fn writes_enabled(self) -> bool {
        !matches!(self, Self::Disabled)
    }

    pub fn enforces_new_exposure(self) -> bool {
        matches!(self, Self::Primary)
    }

    pub fn store_error_blocks_new_exposure(self) -> bool {
        matches!(self, Self::Primary)
    }

    pub fn from_runtime_env() -> Self {
        std::env::var(RUNTIME_MODE_ENV)
            .ok()
            .and_then(|raw| Self::from_str(raw.trim()).ok())
            .unwrap_or(Self::Disabled)
    }
}

impl FromStr for AgentSpineMode {
    type Err = String;

    fn from_str(value: &str) -> Result<Self, Self::Err> {
        match value {
            "disabled" => Ok(Self::Disabled),
            "shadow" => Ok(Self::Shadow),
            "canary" => Ok(Self::Canary),
            "primary" => Ok(Self::Primary),
            other => Err(format!("unknown agent spine mode: {other}")),
        }
    }
}
