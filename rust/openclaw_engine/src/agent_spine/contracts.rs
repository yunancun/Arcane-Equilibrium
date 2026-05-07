//! Agent Spine typed contracts.

use serde::{Deserialize, Serialize};

/// Stable contract version for MAG-031 strategy signals.
pub const STRATEGY_SIGNAL_SCHEMA_VERSION: &str = "agent_spine.strategy_signal.v1";
pub const STRATEGIST_DECISION_SCHEMA_VERSION: &str = "agent_spine.strategist_decision.v1";
pub const GUARDIAN_VERDICT_SCHEMA_VERSION: &str = "agent_spine.guardian_verdict.v1";
pub const EXECUTION_PLAN_SCHEMA_VERSION: &str = "agent_spine.execution_plan.v1";
pub const EXECUTION_REPORT_SCHEMA_VERSION: &str = "agent_spine.execution_report.v1";

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

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StrategistDecision {
    pub schema_version: String,
    pub decision_id: String,
    pub signal_id: String,
    pub ts_ms: u64,
    pub engine_mode: String,
    pub symbol: String,
    pub strategy: String,
    pub direction: StrategySignalDirection,
    pub confidence: f64,
    #[serde(default = "default_decision_action")]
    pub decision_action: String,
    #[serde(default)]
    pub selected_strategy: Option<String>,
    #[serde(default)]
    pub selected_candidate_id: Option<String>,
    #[serde(default)]
    pub candidate_scores: serde_json::Value,
    #[serde(default)]
    pub expected_net_edge_bps: Option<f64>,
    #[serde(default)]
    pub portfolio_impact: serde_json::Value,
    #[serde(default)]
    pub thesis: Option<String>,
    #[serde(default)]
    pub invalidation: Option<String>,
    #[serde(default)]
    pub fact_refs: Vec<String>,
    #[serde(default)]
    pub inference_refs: Vec<String>,
    #[serde(default)]
    pub hypothesis_refs: Vec<String>,
    pub proposed_qty: Option<f64>,
    pub proposed_price: Option<f64>,
    pub rationale: Option<String>,
    pub evidence_refs: Vec<String>,
    pub metadata: serde_json::Value,
}

fn default_decision_action() -> String {
    "open".to_string()
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct GuardianVerdict {
    pub schema_version: String,
    pub verdict_id: String,
    pub decision_id: String,
    pub verdict_version: i32,
    pub ts_ms: u64,
    pub engine_mode: String,
    pub symbol: String,
    pub strategy: String,
    pub allow: bool,
    pub risk_level: String,
    pub reasons: Vec<String>,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ExecutionPlan {
    pub schema_version: String,
    pub order_plan_id: String,
    pub decision_id: String,
    pub verdict_id: String,
    pub ts_ms: u64,
    pub engine_mode: String,
    pub symbol: String,
    pub strategy: String,
    pub direction: StrategySignalDirection,
    pub qty: f64,
    pub order_type: String,
    pub limit_price: Option<f64>,
    pub time_in_force: Option<String>,
    pub lease_id: Option<String>,
    pub idempotency_key: String,
    pub metadata: serde_json::Value,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ExecutionReport {
    pub schema_version: String,
    pub execution_report_id: String,
    pub order_plan_id: String,
    pub decision_id: String,
    pub ts_ms: u64,
    pub engine_mode: String,
    pub symbol: String,
    pub status: String,
    pub exchange_order_id: Option<String>,
    pub fill_id: Option<String>,
    pub metadata: serde_json::Value,
}
