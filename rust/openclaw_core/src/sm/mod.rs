//! State Machine modules — 4 governance SM implementations.
//! 狀態機模組 — 4 個治理 SM 實現。
//!
//! Each SM: enum states + transition validation + audit trail.
//! 每個 SM：枚舉狀態 + 遷移驗證 + 審計軌跡。

pub mod auth;
pub mod lease;
pub mod oms;
pub mod risk_gov;

use serde::{Deserialize, Serialize};
use std::time::{SystemTime, UNIX_EPOCH};

/// Milliseconds since epoch.
/// 自 epoch 起的毫秒數。
pub fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

/// Transition record shared structure.
/// 遷移記錄共用結構。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TransitionRecord {
    pub transition_id: String,
    pub from_state: String,
    pub to_state: String,
    pub event: String,
    pub initiator: String,
    pub reason_codes: Vec<String>,
    pub requires_approval: bool,
    pub approved_by: Option<String>,
    pub timestamp_ms: u64,
    pub version_before: u32,
    pub version_after: u32,
}

impl TransitionRecord {
    pub fn new(
        from_state: &str,
        to_state: &str,
        event: &str,
        initiator: &str,
        reason_codes: Vec<String>,
        requires_approval: bool,
        approved_by: Option<String>,
        version: u32,
    ) -> Self {
        Self {
            transition_id: format!("tx:{:012x}", rand::random::<u64>() & 0xFFFF_FFFF_FFFF),
            from_state: from_state.to_string(),
            to_state: to_state.to_string(),
            event: event.to_string(),
            initiator: initiator.to_string(),
            reason_codes,
            requires_approval,
            approved_by,
            timestamp_ms: now_ms(),
            version_before: version,
            version_after: version + 1,
        }
    }
}

/// SM transition error.
/// SM 遷移錯誤。
#[derive(Debug, Clone, thiserror::Error)]
pub enum SmError {
    #[error("Not found: {0}")]
    NotFound(String),
    #[error("Terminal state: cannot transition from {0}")]
    TerminalState(String),
    #[error("Forbidden transition: {from} → {to}")]
    Forbidden { from: String, to: String },
    #[error("Invalid transition: {from} → {to} (not in table)")]
    InvalidTransition { from: String, to: String },
    #[error("Initiator {initiator} not allowed for {from} → {to}")]
    InitiatorNotAllowed {
        initiator: String,
        from: String,
        to: String,
    },
    #[error("Approval required for {from} → {to}")]
    ApprovalRequired { from: String, to: String },
    #[error("Hold time not met: {remaining_ms}ms remaining")]
    HoldTimeNotMet { remaining_ms: u64 },
}
