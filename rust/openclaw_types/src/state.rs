//! Governance modes, agent states, OMS states, and shared enums.
//! 治理模式、Agent 狀態、OMS 狀態、共享枚舉。
//!
//! Includes types from V3 §3.2 shared_types: RiskLevel, RiskInitiator,
//! OrderState/OmsState, OrderInitiator — needed by Python shared_types.py.

use serde::{Deserialize, Serialize};

/// Global governance mode.
/// 全局治理模式。
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
pub enum GovernanceMode {
    #[default]
    Normal,
    Restricted,
    Frozen,
    ManualReview,
}

impl std::fmt::Display for GovernanceMode {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Normal => write!(f, "NORMAL"),
            Self::Restricted => write!(f, "RESTRICTED"),
            Self::Frozen => write!(f, "FROZEN"),
            Self::ManualReview => write!(f, "MANUAL_REVIEW"),
        }
    }
}

/// Agent lifecycle state.
/// Agent 生命週期狀態。
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
pub enum AgentState {
    #[default]
    Initializing,
    Running,
    Degraded,
    Paused,
    Stopped,
}

impl std::fmt::Display for AgentState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Initializing => write!(f, "initializing"),
            Self::Running => write!(f, "running"),
            Self::Degraded => write!(f, "degraded"),
            Self::Paused => write!(f, "paused"),
            Self::Stopped => write!(f, "stopped"),
        }
    }
}

/// OMS order state (V3 §3.2 shared_types — OrderState).
/// OMS 訂單狀態。
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq)]
pub enum OmsState {
    #[default]
    PendingSubmission,
    Submitted,
    PartiallyFilled,
    Filled,
    Cancelled,
    Rejected,
}

impl std::fmt::Display for OmsState {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::PendingSubmission => write!(f, "pending_submission"),
            Self::Submitted => write!(f, "submitted"),
            Self::PartiallyFilled => write!(f, "partially_filled"),
            Self::Filled => write!(f, "filled"),
            Self::Cancelled => write!(f, "cancelled"),
            Self::Rejected => write!(f, "rejected"),
        }
    }
}

/// Order initiator (V3 §3.2 shared_types).
/// 訂單發起者。
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum OrderInitiator {
    Strategy,
    Operator,
    Guardian,
    System,
}

impl std::fmt::Display for OrderInitiator {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Strategy => write!(f, "strategy"),
            Self::Operator => write!(f, "operator"),
            Self::Guardian => write!(f, "guardian"),
            Self::System => write!(f, "system"),
        }
    }
}

/// Risk level (V3 §3.2 shared_types — from risk_governor_sm).
/// 風險等級。
#[derive(Debug, Clone, Copy, Default, Serialize, Deserialize, PartialEq, Eq, PartialOrd, Ord)]
#[repr(u8)]
pub enum RiskLevel {
    #[default]
    Normal = 0,
    Elevated = 1,
    High = 2,
    Critical = 3,
    Emergency = 4,
}

impl std::fmt::Display for RiskLevel {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Normal => write!(f, "normal"),
            Self::Elevated => write!(f, "elevated"),
            Self::High => write!(f, "high"),
            Self::Critical => write!(f, "critical"),
            Self::Emergency => write!(f, "emergency"),
        }
    }
}

/// Risk initiator (V3 §3.2 shared_types — from risk_governor_sm).
/// 風險發起者。
#[derive(Debug, Clone, Copy, Serialize, Deserialize, PartialEq, Eq)]
pub enum RiskInitiator {
    Market,
    System,
    Operator,
    Guardian,
}

impl std::fmt::Display for RiskInitiator {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::Market => write!(f, "market"),
            Self::System => write!(f, "system"),
            Self::Operator => write!(f, "operator"),
            Self::Guardian => write!(f, "guardian"),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_governance_mode_serde() {
        let mode = GovernanceMode::Frozen;
        let json = serde_json::to_string(&mode).unwrap();
        let de: GovernanceMode = serde_json::from_str(&json).unwrap();
        assert_eq!(de, GovernanceMode::Frozen);
    }

    #[test]
    fn test_oms_state_display() {
        assert_eq!(OmsState::PartiallyFilled.to_string(), "partially_filled");
    }

    #[test]
    fn test_risk_level_ordering() {
        assert!(RiskLevel::Emergency > RiskLevel::Normal);
        assert!(RiskLevel::High > RiskLevel::Elevated);
    }

    #[test]
    fn test_all_enums_serde_roundtrip() {
        // GovernanceMode
        for mode in [
            GovernanceMode::Normal,
            GovernanceMode::Restricted,
            GovernanceMode::Frozen,
            GovernanceMode::ManualReview,
        ] {
            let json = serde_json::to_string(&mode).unwrap();
            let de: GovernanceMode = serde_json::from_str(&json).unwrap();
            assert_eq!(de, mode);
        }
        // OmsState
        for state in [
            OmsState::PendingSubmission,
            OmsState::Submitted,
            OmsState::PartiallyFilled,
            OmsState::Filled,
            OmsState::Cancelled,
            OmsState::Rejected,
        ] {
            let json = serde_json::to_string(&state).unwrap();
            let de: OmsState = serde_json::from_str(&json).unwrap();
            assert_eq!(de, state);
        }
    }
}
