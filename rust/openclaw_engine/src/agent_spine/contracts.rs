//! Agent Spine typed contracts.

use serde::{Deserialize, Serialize};

/// Stable contract version for MAG-031 strategy signals.
pub const STRATEGY_SIGNAL_SCHEMA_VERSION: &str = "agent_spine.strategy_signal.v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StrategySignalDirection {
    Long,
    Short,
    CloseLong,
    CloseShort,
    Neutral,
}

impl StrategySignalDirection {
    pub fn as_trading_signal_type(self) -> &'static str {
        match self {
            Self::Long => "OpenLong",
            Self::Short => "OpenShort",
            Self::CloseLong => "CloseLong",
            Self::CloseShort => "CloseShort",
            Self::Neutral => "Neutral",
        }
    }
}

/// Rust strategy output normalized for Agent Decision Spine consumption.
///
/// This is advisory lineage only in MAG-031. It is not an order, permission,
/// Guardian verdict, ExecutionPlan, or Decision Lease.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StrategySignal {
    pub schema_version: String,
    pub signal_id: String,
    pub ts_ms: u64,
    pub engine_mode: String,
    pub symbol: String,
    pub strategy: String,
    pub direction: StrategySignalDirection,
    pub raw_signal_strength: f64,
    pub expected_edge_bps: Option<f64>,
    pub expected_cost_bps: Option<f64>,
    pub confidence: f64,
    pub regime: Option<String>,
    pub scanner_candidate_id: Option<String>,
    pub scanner_decay_id: Option<String>,
    pub context_id: Option<String>,
    pub evidence_refs: Vec<String>,
    pub invalidation: Option<String>,
    pub order_type: Option<String>,
    pub limit_price: Option<f64>,
    pub time_in_force: Option<String>,
    pub maker_timeout_ms: Option<u64>,
}

impl StrategySignal {
    pub fn trading_signal_type(&self) -> &'static str {
        self.direction.as_trading_signal_type()
    }
}
