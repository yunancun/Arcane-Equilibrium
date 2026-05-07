//! Agent Spine durable event envelopes.

use super::config::AgentSpineMode;
use super::contracts::{
    ExecutionPlan, ExecutionReport, GuardianVerdict, StrategistDecision, StrategySignal,
};
use serde::{Deserialize, Serialize};
use serde_json::Value;
use sha2::{Digest, Sha256};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DecisionObjectType {
    StrategySignal,
    StrategistDecision,
    GuardianVerdict,
    ExecutionPlan,
    ExecutionReport,
    AnalystInsight,
}

impl DecisionObjectType {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::StrategySignal => "strategy_signal",
            Self::StrategistDecision => "strategist_decision",
            Self::GuardianVerdict => "guardian_verdict",
            Self::ExecutionPlan => "execution_plan",
            Self::ExecutionReport => "execution_report",
            Self::AnalystInsight => "analyst_insight",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum DecisionEdgeType {
    EvidenceFor,
    SignalFor,
    ReviewedBy,
    ModifiedBy,
    PlannedBy,
    LeasedBy,
    ExecutedBy,
    AnalyzedBy,
    ProtectiveBypassFor,
}

impl DecisionEdgeType {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::EvidenceFor => "evidence_for",
            Self::SignalFor => "signal_for",
            Self::ReviewedBy => "reviewed_by",
            Self::ModifiedBy => "modified_by",
            Self::PlannedBy => "planned_by",
            Self::LeasedBy => "leased_by",
            Self::ExecutedBy => "executed_by",
            Self::AnalyzedBy => "analyzed_by",
            Self::ProtectiveBypassFor => "protective_bypass_for",
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpineObjectEnvelope {
    pub created_at_ms: u64,
    pub object_id: String,
    pub object_type: DecisionObjectType,
    pub object_version: String,
    pub engine_mode: String,
    pub symbol: String,
    pub strategy: Option<String>,
    pub signal_id: Option<String>,
    pub decision_id: Option<String>,
    pub verdict_id: Option<String>,
    pub verdict_version: Option<i32>,
    pub order_plan_id: Option<String>,
    pub execution_report_id: Option<String>,
    pub lease_id: Option<String>,
    pub state: String,
    pub source_agent: String,
    pub authority_mode: AgentSpineMode,
    pub idempotency_key: String,
    pub payload_hash: String,
    pub payload: Value,
}

impl SpineObjectEnvelope {
    pub fn from_strategy_signal(
        signal: &StrategySignal,
        authority_mode: AgentSpineMode,
    ) -> serde_json::Result<Self> {
        let payload = serde_json::to_value(signal)?;
        Ok(Self {
            created_at_ms: signal.ts_ms,
            object_id: signal.signal_id.clone(),
            object_type: DecisionObjectType::StrategySignal,
            object_version: signal.schema_version.clone(),
            engine_mode: signal.engine_mode.clone(),
            symbol: signal.symbol.clone(),
            strategy: Some(signal.strategy.clone()),
            signal_id: Some(signal.signal_id.clone()),
            decision_id: None,
            verdict_id: None,
            verdict_version: None,
            order_plan_id: None,
            execution_report_id: None,
            lease_id: None,
            state: "observed".to_string(),
            source_agent: "strategy".to_string(),
            authority_mode,
            idempotency_key: format!(
                "strategy_signal:{}:{}",
                signal.engine_mode, signal.signal_id
            ),
            payload_hash: payload_hash(&payload),
            payload,
        })
    }

    pub fn from_strategist_decision(
        decision: &StrategistDecision,
        authority_mode: AgentSpineMode,
    ) -> serde_json::Result<Self> {
        let payload = serde_json::to_value(decision)?;
        Ok(Self {
            created_at_ms: decision.ts_ms,
            object_id: decision.decision_id.clone(),
            object_type: DecisionObjectType::StrategistDecision,
            object_version: decision.schema_version.clone(),
            engine_mode: decision.engine_mode.clone(),
            symbol: decision.symbol.clone(),
            strategy: Some(decision.strategy.clone()),
            signal_id: Some(decision.signal_id.clone()),
            decision_id: Some(decision.decision_id.clone()),
            verdict_id: None,
            verdict_version: None,
            order_plan_id: None,
            execution_report_id: None,
            lease_id: None,
            state: "proposed".to_string(),
            source_agent: "strategist".to_string(),
            authority_mode,
            idempotency_key: format!(
                "strategist_decision:{}:{}",
                decision.engine_mode, decision.decision_id
            ),
            payload_hash: payload_hash(&payload),
            payload,
        })
    }

    pub fn from_guardian_verdict(
        verdict: &GuardianVerdict,
        authority_mode: AgentSpineMode,
    ) -> serde_json::Result<Self> {
        let payload = serde_json::to_value(verdict)?;
        Ok(Self {
            created_at_ms: verdict.ts_ms,
            object_id: verdict.verdict_id.clone(),
            object_type: DecisionObjectType::GuardianVerdict,
            object_version: verdict.schema_version.clone(),
            engine_mode: verdict.engine_mode.clone(),
            symbol: verdict.symbol.clone(),
            strategy: Some(verdict.strategy.clone()),
            signal_id: None,
            decision_id: Some(verdict.decision_id.clone()),
            verdict_id: Some(verdict.verdict_id.clone()),
            verdict_version: Some(verdict.verdict_version),
            order_plan_id: None,
            execution_report_id: None,
            lease_id: None,
            state: if verdict.allow {
                "approved"
            } else {
                "rejected"
            }
            .to_string(),
            source_agent: "guardian".to_string(),
            authority_mode,
            idempotency_key: format!(
                "guardian_verdict:{}:{}:{}",
                verdict.engine_mode, verdict.decision_id, verdict.verdict_version
            ),
            payload_hash: payload_hash(&payload),
            payload,
        })
    }

    pub fn from_execution_plan(
        plan: &ExecutionPlan,
        authority_mode: AgentSpineMode,
    ) -> serde_json::Result<Self> {
        let payload = serde_json::to_value(plan)?;
        Ok(Self {
            created_at_ms: plan.ts_ms,
            object_id: plan.order_plan_id.clone(),
            object_type: DecisionObjectType::ExecutionPlan,
            object_version: plan.schema_version.clone(),
            engine_mode: plan.engine_mode.clone(),
            symbol: plan.symbol.clone(),
            strategy: Some(plan.strategy.clone()),
            signal_id: None,
            decision_id: Some(plan.decision_id.clone()),
            verdict_id: Some(plan.verdict_id.clone()),
            verdict_version: None,
            order_plan_id: Some(plan.order_plan_id.clone()),
            execution_report_id: None,
            lease_id: plan.lease_id.clone(),
            state: "planned".to_string(),
            source_agent: "executor".to_string(),
            authority_mode,
            idempotency_key: plan.idempotency_key.clone(),
            payload_hash: payload_hash(&payload),
            payload,
        })
    }

    pub fn from_execution_report(
        report: &ExecutionReport,
        authority_mode: AgentSpineMode,
    ) -> serde_json::Result<Self> {
        let payload = serde_json::to_value(report)?;
        Ok(Self {
            created_at_ms: report.ts_ms,
            object_id: report.execution_report_id.clone(),
            object_type: DecisionObjectType::ExecutionReport,
            object_version: report.schema_version.clone(),
            engine_mode: report.engine_mode.clone(),
            symbol: report.symbol.clone(),
            strategy: None,
            signal_id: None,
            decision_id: Some(report.decision_id.clone()),
            verdict_id: None,
            verdict_version: None,
            order_plan_id: Some(report.order_plan_id.clone()),
            execution_report_id: Some(report.execution_report_id.clone()),
            lease_id: None,
            state: report.status.clone(),
            source_agent: "executor".to_string(),
            authority_mode,
            idempotency_key: format!(
                "execution_report:{}:{}",
                report.engine_mode, report.execution_report_id
            ),
            payload_hash: payload_hash(&payload),
            payload,
        })
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpineEdge {
    pub edge_id: String,
    pub created_at_ms: u64,
    pub from_object_id: String,
    pub to_object_id: String,
    pub edge_type: DecisionEdgeType,
    pub engine_mode: String,
    pub decision_id: Option<String>,
    pub payload_hash: Option<String>,
    pub details: Value,
}

impl SpineEdge {
    pub fn new(
        created_at_ms: u64,
        from_object_id: impl Into<String>,
        to_object_id: impl Into<String>,
        edge_type: DecisionEdgeType,
        engine_mode: impl Into<String>,
        decision_id: Option<String>,
        details: Value,
    ) -> Self {
        let from_object_id = from_object_id.into();
        let to_object_id = to_object_id.into();
        let edge_id = stable_id(
            "edge",
            &[
                edge_type.as_str(),
                from_object_id.as_str(),
                to_object_id.as_str(),
            ],
        );
        let payload_hash = if details.is_null() {
            None
        } else {
            Some(payload_hash(&details))
        };
        Self {
            edge_id,
            created_at_ms,
            from_object_id,
            to_object_id,
            edge_type,
            engine_mode: engine_mode.into(),
            decision_id,
            payload_hash,
            details,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct SpineStateTransition {
    pub ts_ms: u64,
    pub transition_id: String,
    pub object_id: String,
    pub object_type: DecisionObjectType,
    pub from_state: Option<String>,
    pub to_state: String,
    pub engine_mode: String,
    pub trigger: String,
    pub details: Value,
}

impl SpineStateTransition {
    pub fn new(
        ts_ms: u64,
        object_id: impl Into<String>,
        object_type: DecisionObjectType,
        from_state: Option<String>,
        to_state: impl Into<String>,
        engine_mode: impl Into<String>,
        trigger: impl Into<String>,
        details: Value,
    ) -> Self {
        let object_id = object_id.into();
        let to_state = to_state.into();
        let trigger = trigger.into();
        let transition_id = stable_id(
            "transition",
            &[
                object_id.as_str(),
                to_state.as_str(),
                trigger.as_str(),
                &ts_ms.to_string(),
            ],
        );
        Self {
            ts_ms,
            transition_id,
            object_id,
            object_type,
            from_state,
            to_state,
            engine_mode: engine_mode.into(),
            trigger,
            details,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ExecutionIdempotencyKey {
    pub idempotency_key: String,
    pub order_plan_id: String,
    pub decision_id: String,
    pub engine_mode: String,
    pub first_seen_at_ms: u64,
    pub status: String,
    pub details: Value,
}

impl ExecutionIdempotencyKey {
    pub fn reserved(plan: &ExecutionPlan, first_seen_at_ms: u64) -> Self {
        Self {
            idempotency_key: plan.idempotency_key.clone(),
            order_plan_id: plan.order_plan_id.clone(),
            decision_id: plan.decision_id.clone(),
            engine_mode: plan.engine_mode.clone(),
            first_seen_at_ms,
            status: "reserved".to_string(),
            details: serde_json::json!({
                "verdict_id": plan.verdict_id,
                "symbol": plan.symbol,
                "order_type": plan.order_type,
            }),
        }
    }
}

pub fn payload_hash(payload: &Value) -> String {
    let bytes = serde_json::to_vec(payload).unwrap_or_default();
    let mut hasher = Sha256::new();
    hasher.update(bytes);
    format!("sha256:{}", hex::encode(hasher.finalize()))
}

pub fn stable_id(prefix: &str, parts: &[&str]) -> String {
    let mut hasher = Sha256::new();
    for part in parts {
        hasher.update(part.as_bytes());
        hasher.update([0]);
    }
    format!("{prefix}:{}", &hex::encode(hasher.finalize())[..32])
}
