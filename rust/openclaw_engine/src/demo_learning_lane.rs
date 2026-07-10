//! Cost-gate demo-learning lane admission policy.
//!
//! This module mirrors the artifact/control-plane adapter in Rust so the
//! trading authority layer has a small, testable seam before any future
//! hot-path wiring. It is pure policy: no file IO, no DB, no Bybit calls, no
//! order submission, and no mutation of runtime config.
//!
//! Cost-gate demo-learning lane 准入策略。
//!
//! 本模組把 artifact/control-plane adapter 的語義鏡像到 Rust 交易權威層，
//! 讓未來接入 hot path 時只需依賴一個小而可測的 seam。此處僅是純策略：
//! 不讀寫檔案、不連 DB、不呼叫 Bybit、不送單、不修改 runtime config。

use chrono::{DateTime, Utc};
use serde::{Deserialize, Serialize};

pub const PLAN_SCHEMA_VERSION: &str = "cost_gate_demo_learning_lane_plan_v1";
pub const ADAPTER_SCHEMA_VERSION: &str = "cost_gate_demo_learning_lane_adapter_v1";
pub const ORDER_AUTHORITY_GRANTED: &str = "DEMO_LEARNING_PROBE_GRANTED";
pub const ELIGIBLE_REJECT_REASON_CODE: &str = "cost_gate_js_demo_negative_edge";
pub const ADMIT_DECISION: &str = "ADMIT_DEMO_LEARNING_PROBE";
pub const BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION: &str =
    "bounded_demo_probe_operator_authorization_v1";
pub const BOUNDED_PROBE_AUTHORIZED_STATUS: &str = "BOUNDED_DEMO_PROBE_AUTHORIZED";
pub const AUTHORITY_PATH_PATCH_READY_STATUS: &str =
    "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW";
/// envelope 過期的唯一 reason 字串。soak 圍欄依此把「確定性過期」與其他
/// envelope 缺陷(一律 fail-closed)區分開;字面值與抽取前 byte-identical。
pub const OPERATOR_AUTHORIZATION_EXPIRED_REASON: &str = "operator_authorization_expired";

#[derive(Debug, Clone, PartialEq)]
pub struct AdmissionConfig {
    pub max_plan_age_hours: u64,
    pub min_failed_outcomes_to_disable: usize,
    pub min_outcome_net_positive_pct: f64,
    pub min_avg_net_bps: f64,
}

impl Default for AdmissionConfig {
    fn default() -> Self {
        Self {
            // P2-7:n=2 對 ±75bps 效應量兩個方向都近擲硬幣(誤殺率 ~42%)。改為 UCB-futility
            // 規則需 n≥8 才禁用;此常數是「觸發禁用檢定的最小樣本」,不是 probe 預算。
            max_plan_age_hours: 24,
            min_failed_outcomes_to_disable: 8,
            min_outcome_net_positive_pct: 50.0,
            min_avg_net_bps: 0.0,
        }
    }
}

impl AdmissionConfig {
    pub fn validate(&self) -> Result<(), String> {
        if !(1..=24 * 14).contains(&self.max_plan_age_hours) {
            return Err("max_plan_age_hours_must_be_in_1_336".to_string());
        }
        if !(1..=20).contains(&self.min_failed_outcomes_to_disable) {
            return Err("min_failed_outcomes_to_disable_must_be_in_1_20".to_string());
        }
        if !(0.0..=100.0).contains(&self.min_outcome_net_positive_pct) {
            return Err("min_outcome_net_positive_pct_must_be_in_0_100".to_string());
        }
        if !self.min_avg_net_bps.is_finite()
            || !(-10_000.0..=10_000.0).contains(&self.min_avg_net_bps)
        {
            return Err("min_avg_net_bps_must_be_finite_in_-10000_10000".to_string());
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Deserialize)]
pub struct DemoLearningLanePlan {
    pub schema_version: String,
    #[serde(default)]
    pub generated_at_utc: Option<String>,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub gate_status: String,
    #[serde(default)]
    pub main_cost_gate_adjustment: String,
    #[serde(default)]
    pub learning_gate_adjustment: String,
    #[serde(default)]
    pub order_authority: String,
    #[serde(default)]
    pub operator_authorization: Option<BoundedProbeOperatorAuthorization>,
    #[serde(default)]
    pub selected_probe_candidate_count: usize,
    #[serde(default)]
    pub probe_candidates: Vec<ProbeCandidate>,
}

impl DemoLearningLanePlan {
    pub fn from_json_str(input: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(input)
    }

    fn candidate_for_side_cell(&self, side_cell_key: &str) -> Option<&ProbeCandidate> {
        self.probe_candidates
            .iter()
            .find(|candidate| candidate.side_cell_key == side_cell_key)
    }
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct BoundedProbeOperatorAuthorization {
    #[serde(default)]
    pub schema_version: String,
    #[serde(default)]
    pub status: String,
    #[serde(default)]
    pub authorization_id: Option<String>,
    #[serde(default)]
    pub operator_id: Option<String>,
    #[serde(default)]
    pub side_cell_key: String,
    #[serde(default)]
    pub expires_at_utc: Option<String>,
    #[serde(default)]
    pub authority_path_readiness_status: String,
    #[serde(default)]
    pub main_cost_gate_adjustment: String,
    #[serde(default)]
    pub order_authority: String,
    #[serde(default)]
    pub max_authorized_probe_orders: Option<u64>,
    #[serde(default)]
    pub probe_authority_granted: Option<bool>,
    #[serde(default)]
    pub order_authority_granted: Option<bool>,
    #[serde(default)]
    pub promotion_evidence: Option<bool>,
}

#[derive(Debug, Clone, Deserialize)]
pub struct ProbeCandidate {
    #[serde(default)]
    pub side_cell_key: String,
    #[serde(default)]
    pub strategy_name: Option<String>,
    #[serde(default)]
    pub symbol: Option<String>,
    #[serde(default)]
    pub side: Option<String>,
    #[serde(default)]
    pub reject_reason_code: Option<String>,
    #[serde(default)]
    pub probe_proposal: ProbeProposal,
    #[serde(default)]
    pub guardrails: CandidateGuardrails,
}

impl ProbeCandidate {
    fn max_probe_orders(&self) -> u64 {
        self.probe_proposal.max_probe_orders.unwrap_or(0)
    }

    fn cooldown_ms(&self) -> u64 {
        self.probe_proposal
            .cooldown_minutes
            .unwrap_or(0)
            .saturating_mul(60_000)
    }

    fn validate_guardrails(&self) -> Result<(), &'static str> {
        if self.probe_proposal.mode.as_deref() != Some("demo_only_learning_probe") {
            return Err("candidate_probe_mode_not_demo_only");
        }
        if self.max_probe_orders() == 0 {
            return Err("candidate_probe_budget_not_positive");
        }
        if self.probe_proposal.requires_runtime_policy_adapter != Some(true) {
            return Err("candidate_missing_runtime_adapter_requirement");
        }
        if self.probe_proposal.requires_probe_attempt_logging != Some(true) {
            return Err("candidate_missing_attempt_logging_requirement");
        }
        if self.probe_proposal.requires_probe_outcome_logging != Some(true) {
            return Err("candidate_missing_outcome_logging_requirement");
        }
        if self.guardrails.main_cost_gate_adjustment.as_deref() != Some("NONE") {
            return Err("candidate_main_cost_gate_adjustment_not_none");
        }
        if self.guardrails.may_bypass_main_live_gate != Some(false) {
            return Err("candidate_live_bypass_guardrail_invalid");
        }
        if self.guardrails.demo_only != Some(true) {
            return Err("candidate_demo_only_guardrail_missing");
        }
        if self.guardrails.notional_or_qty_not_granted_by_artifact != Some(true) {
            return Err("candidate_qty_authority_guardrail_missing");
        }
        Ok(())
    }
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct ProbeProposal {
    #[serde(default)]
    pub mode: Option<String>,
    #[serde(default)]
    pub max_probe_orders: Option<u64>,
    #[serde(default)]
    pub cooldown_minutes: Option<u64>,
    #[serde(default)]
    pub requires_runtime_policy_adapter: Option<bool>,
    #[serde(default)]
    pub requires_probe_attempt_logging: Option<bool>,
    #[serde(default)]
    pub requires_probe_outcome_logging: Option<bool>,
}

#[derive(Debug, Clone, Default, Deserialize)]
pub struct CandidateGuardrails {
    #[serde(default)]
    pub main_cost_gate_adjustment: Option<String>,
    #[serde(default)]
    pub may_bypass_main_live_gate: Option<bool>,
    #[serde(default)]
    pub demo_only: Option<bool>,
    #[serde(default)]
    pub paper_not_promotion_evidence: Option<bool>,
    #[serde(default)]
    pub notional_or_qty_not_granted_by_artifact: Option<bool>,
}

#[derive(Debug, Clone, PartialEq)]
pub struct RejectEvent {
    pub strategy_name: String,
    pub symbol: String,
    pub side: String,
    pub reject_reason_code: String,
    pub engine_mode: String,
    pub ts_ms: u64,
    pub context_id: Option<String>,
    pub signal_id: Option<String>,
    pub candidate_event_context: Option<crate::candidate_event_context::CandidateEventContextV1>,
}

impl RejectEvent {
    pub fn side_cell_key(&self) -> String {
        side_cell_key(&self.strategy_name, &self.symbol, &self.side)
    }

    fn normalized(&self) -> NormalizedRejectEvent {
        NormalizedRejectEvent {
            side_cell_key: self.side_cell_key(),
            reject_reason_code: normalize_reject_reason_code(&self.reject_reason_code),
            engine_mode: self.engine_mode.trim().to_ascii_lowercase(),
            ts_ms: self.ts_ms,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
struct NormalizedRejectEvent {
    side_cell_key: String,
    reject_reason_code: String,
    engine_mode: String,
    ts_ms: u64,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LedgerRecord {
    #[serde(default)]
    pub record_type: Option<String>,
    #[serde(default)]
    pub attempt_id: Option<String>,
    #[serde(default)]
    pub generated_at_utc: Option<String>,
    #[serde(default)]
    pub decision: Option<String>,
    #[serde(default)]
    pub allowed_to_submit_order: Option<bool>,
    #[serde(default)]
    pub admission_decision: Option<LedgerDecisionRef>,
    #[serde(default)]
    pub side_cell_key: Option<String>,
    #[serde(default)]
    pub strategy_name: Option<String>,
    #[serde(default)]
    pub symbol: Option<String>,
    #[serde(default)]
    pub side: Option<String>,
    #[serde(default)]
    pub ts_ms: Option<u64>,
    #[serde(default)]
    pub attempt_ts_ms: Option<u64>,
    #[serde(default)]
    pub generated_at_ms: Option<u64>,
    #[serde(default)]
    pub event: Option<LedgerEventRef>,
    #[serde(default)]
    pub realized_net_bps: Option<f64>,
    #[serde(default)]
    pub disable_reason: Option<String>,
    #[serde(default)]
    pub reason: Option<String>,
    #[serde(default)]
    pub boundary: Option<String>,
}

impl LedgerRecord {
    pub fn from_jsonl_str(input: &str) -> Result<Vec<Self>, String> {
        let mut out = Vec::new();
        for (idx, line) in input.lines().enumerate() {
            let trimmed = line.trim();
            if trimmed.is_empty() {
                continue;
            }
            let row: Self = serde_json::from_str(trimmed)
                .map_err(|err| format!("malformed JSONL ledger at line {}: {err}", idx + 1))?;
            out.push(row);
        }
        Ok(out)
    }

    fn decision(&self) -> Option<&str> {
        self.decision
            .as_deref()
            .or_else(|| self.admission_decision.as_ref()?.decision.as_deref())
    }

    fn side_cell_key(&self) -> String {
        if let Some(key) = self.side_cell_key.as_deref() {
            return key.trim().to_string();
        }
        if let Some(event) = self.event.as_ref() {
            if let Some(key) = event.side_cell_key.as_deref() {
                return key.trim().to_string();
            }
            return side_cell_key_opt(&event.strategy_name, &event.symbol, &event.side);
        }
        side_cell_key_opt(&self.strategy_name, &self.symbol, &self.side)
    }

    fn attempt_ts_ms(&self) -> Option<u64> {
        self.ts_ms
            .or(self.attempt_ts_ms)
            .or(self.generated_at_ms)
            .or_else(|| self.event.as_ref()?.ts_ms)
    }
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LedgerDecisionRef {
    #[serde(default)]
    pub decision: Option<String>,
}

#[derive(Debug, Clone, Deserialize, Serialize)]
pub struct LedgerEventRef {
    #[serde(default)]
    pub side_cell_key: Option<String>,
    #[serde(default, alias = "strategy")]
    pub strategy_name: Option<String>,
    #[serde(default)]
    pub symbol: Option<String>,
    #[serde(default)]
    pub side: Option<String>,
    #[serde(default)]
    pub reject_reason_code: Option<String>,
    #[serde(default)]
    pub engine_mode: Option<String>,
    #[serde(default)]
    pub ts_ms: Option<u64>,
    #[serde(default)]
    pub context_id: Option<String>,
    #[serde(default)]
    pub signal_id: Option<String>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub candidate_event_context: Option<crate::candidate_event_context::CandidateEventContextV1>,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct SideCellRuntimeState {
    pub side_cell_key: String,
    pub max_probe_orders: u64,
    pub admitted_attempt_count: usize,
    pub remaining_probe_orders: u64,
    pub latest_probe_attempt_ts_ms: Option<u64>,
    pub cooldown_ms: u64,
    pub cooldown_until_ts_ms: Option<u64>,
    pub cooldown_active: bool,
    pub completed_outcome_count: usize,
    pub avg_realized_net_bps: Option<f64>,
    pub net_positive_pct: Option<f64>,
    pub disabled: bool,
    pub disable_reason: Option<String>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AdmissionDecisionCode {
    AdmitDemoLearningProbe,
    ConfigInvalid,
    PlanSchemaMismatch,
    PlanNotReady,
    PlanStaleOrMissingGeneratedAt,
    MainCostGateAdjustmentNotAllowed,
    NonDemoEngineMode,
    RejectReasonNotEligible,
    SideCellNotSelected,
    CandidateGuardrailInvalid,
    SideCellDisabled,
    ProbeBudgetExhausted,
    RealizedProbeOutcomesFailLearningThreshold,
    CooldownActive,
    RiskStateNotNormal,
    OrderAuthorityNotGranted,
    OperatorAuthorizationInvalid,
    AdapterDisabled,
}

impl AdmissionDecisionCode {
    pub fn as_str(self) -> &'static str {
        match self {
            Self::AdmitDemoLearningProbe => ADMIT_DECISION,
            Self::ConfigInvalid => "CONFIG_INVALID",
            Self::PlanSchemaMismatch => "PLAN_SCHEMA_MISMATCH",
            Self::PlanNotReady => "PLAN_NOT_READY",
            Self::PlanStaleOrMissingGeneratedAt => "PLAN_STALE_OR_MISSING_GENERATED_AT",
            Self::MainCostGateAdjustmentNotAllowed => "MAIN_COST_GATE_ADJUSTMENT_NOT_ALLOWED",
            Self::NonDemoEngineMode => "NON_DEMO_ENGINE_MODE",
            Self::RejectReasonNotEligible => "REJECT_REASON_NOT_ELIGIBLE",
            Self::SideCellNotSelected => "SIDE_CELL_NOT_SELECTED",
            Self::CandidateGuardrailInvalid => "CANDIDATE_GUARDRAIL_INVALID",
            Self::SideCellDisabled => "SIDE_CELL_DISABLED",
            Self::ProbeBudgetExhausted => "PROBE_BUDGET_EXHAUSTED",
            Self::RealizedProbeOutcomesFailLearningThreshold => {
                "REALIZED_PROBE_OUTCOMES_FAIL_LEARNING_THRESHOLD"
            }
            Self::CooldownActive => "COOLDOWN_ACTIVE",
            Self::RiskStateNotNormal => "RISK_STATE_NOT_NORMAL",
            Self::OrderAuthorityNotGranted => "ORDER_AUTHORITY_NOT_GRANTED",
            Self::OperatorAuthorizationInvalid => "OPERATOR_AUTHORIZATION_INVALID",
            Self::AdapterDisabled => "ADAPTER_DISABLED",
        }
    }

    pub fn allowed_to_submit_order(self) -> bool {
        self == Self::AdmitDemoLearningProbe
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct AdmissionDecision {
    pub schema_version: &'static str,
    pub decision: AdmissionDecisionCode,
    pub reason: String,
    pub allowed_to_submit_order: bool,
    pub no_order_authority: bool,
    pub side_cell_key: String,
    pub runtime_state: Option<SideCellRuntimeState>,
    pub plan_summary: PlanSummary,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PlanSummary {
    pub schema_version: String,
    pub status: String,
    pub gate_status: String,
    pub main_cost_gate_adjustment: String,
    pub learning_gate_adjustment: String,
    pub order_authority: String,
    pub selected_probe_candidate_count: usize,
}

impl PlanSummary {
    fn from_plan(plan: &DemoLearningLanePlan) -> Self {
        Self {
            schema_version: plan.schema_version.clone(),
            status: plan.status.clone(),
            gate_status: plan.gate_status.clone(),
            main_cost_gate_adjustment: plan.main_cost_gate_adjustment.clone(),
            learning_gate_adjustment: plan.learning_gate_adjustment.clone(),
            order_authority: plan.order_authority.clone(),
            selected_probe_candidate_count: plan.selected_probe_candidate_count,
        }
    }
}

pub fn side_cell_key(strategy_name: &str, symbol: &str, side: &str) -> String {
    format!(
        "{}|{}|{}",
        strategy_name.trim(),
        symbol.trim().to_ascii_uppercase(),
        side.trim()
    )
}

fn side_cell_key_opt(
    strategy_name: &Option<String>,
    symbol: &Option<String>,
    side: &Option<String>,
) -> String {
    format!(
        "{}|{}|{}",
        strategy_name.as_deref().unwrap_or("").trim(),
        symbol.as_deref().unwrap_or("").trim().to_ascii_uppercase(),
        side.as_deref().unwrap_or("").trim()
    )
}

pub fn normalize_reject_reason_code(value: &str) -> String {
    let lowered = value.trim().to_ascii_lowercase();
    if lowered == ELIGIBLE_REJECT_REASON_CODE {
        return ELIGIBLE_REJECT_REASON_CODE.to_string();
    }
    let is_js_demo_cost_gate = lowered.contains("cost_gate(js-demo)")
        || (lowered.contains("cost_gate") && lowered.contains("js-demo"));
    let compact: String = lowered.chars().filter(|c| !c.is_whitespace()).collect();
    let is_negative_estimate = lowered.contains("negative")
        || lowered.contains("負估計")
        || (compact.contains("estimated=") && compact.contains("<0"));
    if is_js_demo_cost_gate && is_negative_estimate {
        return ELIGIBLE_REJECT_REASON_CODE.to_string();
    }
    lowered
}

pub fn summarize_side_cell_runtime_state(
    candidate: &ProbeCandidate,
    ledger_rows: &[LedgerRecord],
    now_ms: u64,
    cfg: &AdmissionConfig,
) -> SideCellRuntimeState {
    let key = candidate.side_cell_key.trim().to_string();
    let max_probe_orders = candidate.max_probe_orders();
    let cooldown_ms = candidate.cooldown_ms();
    let matching: Vec<&LedgerRecord> = ledger_rows
        .iter()
        .filter(|row| row.side_cell_key() == key)
        .collect();
    let admitted: Vec<&LedgerRecord> = matching
        .iter()
        .copied()
        .filter(|row| row.decision() == Some(ADMIT_DECISION))
        .collect();
    let admitted_attempt_count = admitted.len();
    let remaining_probe_orders = max_probe_orders.saturating_sub(admitted_attempt_count as u64);
    let latest_probe_attempt_ts_ms = admitted.iter().filter_map(|row| row.attempt_ts_ms()).max();
    let cooldown_until_ts_ms = latest_probe_attempt_ts_ms
        .and_then(|ts| ts.checked_add(cooldown_ms))
        .filter(|_| cooldown_ms > 0);
    let cooldown_active = cooldown_until_ts_ms.is_some_and(|ts| now_ms < ts);

    let realized_net_bps: Vec<f64> = matching
        .iter()
        .filter(|row| row.record_type.as_deref() == Some("probe_outcome"))
        .filter_map(|row| row.realized_net_bps)
        .filter(|value| value.is_finite())
        .collect();
    let completed_outcome_count = realized_net_bps.len();
    let avg_realized_net_bps = if completed_outcome_count > 0 {
        Some(realized_net_bps.iter().sum::<f64>() / completed_outcome_count as f64)
    } else {
        None
    };
    // P2-7:UCB-futility 禁用規則需樣本標準差(ddof=1)。n<2 無法估變異數。
    let std_realized_net_bps = match (completed_outcome_count, avg_realized_net_bps) {
        (n, Some(mean)) if n >= 2 => {
            let variance = realized_net_bps
                .iter()
                .map(|v| (v - mean) * (v - mean))
                .sum::<f64>()
                / (n as f64 - 1.0);
            Some(variance.sqrt())
        }
        _ => None,
    };
    let net_positive_pct = if completed_outcome_count > 0 {
        let positive = realized_net_bps
            .iter()
            .filter(|value| **value > 0.0)
            .count();
        Some(100.0 * positive as f64 / completed_outcome_count as f64)
    } else {
        None
    };
    let manual_disable_reason = matching.iter().find_map(|row| {
        if row.record_type.as_deref() == Some("side_cell_disabled") {
            Some(
                row.disable_reason
                    .as_deref()
                    .unwrap_or("manual_disable")
                    .to_string(),
            )
        } else {
            None
        }
    });
    // P2-7:UCB-futility 禁用規則。disable ⇔ n≥8 ∧ (x̄ + z₀.₉₀·s/√n < cfg.min_avg_net_bps)。
    // 為什麼 UCB 而非均值：n<20 下均值判準對 ±75bps 效應量兩向都近擲硬幣(誤殺率 ~42%);
    // 加 90% 信賴上界後只在「連樂觀上界都為負」時才 futility 禁用(真 μ=+30 誤殺率降到 ~4%)。
    // futility-only 早停不膨脹 type-I error。net_positive_pct 腿刪除:n<20 下比例判準更噪。
    // z₀.₉₀ = 1.2815515655446004(標準常態 0.90 分位)。
    const Z_090: f64 = 1.281_551_565_544_600_4;
    let ucb_futility = match (
        completed_outcome_count >= cfg.min_failed_outcomes_to_disable,
        avg_realized_net_bps,
        std_realized_net_bps,
    ) {
        (true, Some(mean), Some(std)) => {
            let ucb = mean + Z_090 * std / (completed_outcome_count as f64).sqrt();
            ucb < cfg.min_avg_net_bps
        }
        // s 不可估(n<2)但已達門檻(僅在 min_failed_outcomes_to_disable=1 且 n=1 時)：
        // 退回純均值判準,避免無變異數時漏禁真負 cell。
        (true, Some(mean), None) => mean < cfg.min_avg_net_bps,
        _ => false,
    };
    let disable_reason = if manual_disable_reason.is_some() {
        manual_disable_reason
    } else if remaining_probe_orders == 0 {
        Some("probe_budget_exhausted".to_string())
    } else if ucb_futility {
        Some("realized_probe_outcomes_fail_learning_threshold".to_string())
    } else {
        None
    };

    SideCellRuntimeState {
        side_cell_key: key,
        max_probe_orders,
        admitted_attempt_count,
        remaining_probe_orders,
        latest_probe_attempt_ts_ms,
        cooldown_ms,
        cooldown_until_ts_ms,
        cooldown_active,
        completed_outcome_count,
        avg_realized_net_bps,
        net_positive_pct,
        disabled: disable_reason.is_some(),
        disable_reason,
    }
}

pub fn evaluate_probe_admission(
    plan: &DemoLearningLanePlan,
    reject_event: &RejectEvent,
    ledger_rows: &[LedgerRecord],
    now_ms: u64,
    cfg: &AdmissionConfig,
    adapter_enabled: bool,
    risk_state: &str,
) -> AdmissionDecision {
    let event = reject_event.normalized();
    if let Err(reason) = cfg.validate() {
        return decision(
            AdmissionDecisionCode::ConfigInvalid,
            reason,
            &event.side_cell_key,
            None,
            plan,
        );
    }
    if plan.schema_version != PLAN_SCHEMA_VERSION {
        return decision(
            AdmissionDecisionCode::PlanSchemaMismatch,
            "plan_schema_version_is_not_cost_gate_demo_learning_lane_plan_v1",
            &event.side_cell_key,
            None,
            plan,
        );
    }
    if plan.status != "READY_FOR_DEMO_LEARNING_PROBE" {
        return decision(
            AdmissionDecisionCode::PlanNotReady,
            "plan_status_is_not_ready_for_demo_learning_probe",
            &event.side_cell_key,
            None,
            plan,
        );
    }
    if plan_is_stale_or_missing_generated_at(plan.generated_at_utc.as_deref(), now_ms, cfg) {
        return decision(
            AdmissionDecisionCode::PlanStaleOrMissingGeneratedAt,
            "plan_generated_at_missing_or_too_old",
            &event.side_cell_key,
            None,
            plan,
        );
    }
    if plan.main_cost_gate_adjustment != "NONE" {
        return decision(
            AdmissionDecisionCode::MainCostGateAdjustmentNotAllowed,
            "demo_learning_lane_must_not_lower_main_cost_gate",
            &event.side_cell_key,
            None,
            plan,
        );
    }
    if !matches!(event.engine_mode.as_str(), "demo" | "live_demo") {
        return decision(
            AdmissionDecisionCode::NonDemoEngineMode,
            "learning_probe_admission_is_demo_only",
            &event.side_cell_key,
            None,
            plan,
        );
    }
    if event.reject_reason_code != ELIGIBLE_REJECT_REASON_CODE {
        return decision(
            AdmissionDecisionCode::RejectReasonNotEligible,
            "only_cost_gate_js_demo_negative_edge_rejections_are_probe_eligible",
            &event.side_cell_key,
            None,
            plan,
        );
    }
    let Some(candidate) = plan.candidate_for_side_cell(&event.side_cell_key) else {
        return decision(
            AdmissionDecisionCode::SideCellNotSelected,
            "rejected_signal_side_cell_is_not_in_selected_probe_candidates",
            &event.side_cell_key,
            None,
            plan,
        );
    };

    let runtime_state = summarize_side_cell_runtime_state(candidate, ledger_rows, now_ms, cfg);
    if let Err(reason) = candidate.validate_guardrails() {
        return decision(
            AdmissionDecisionCode::CandidateGuardrailInvalid,
            reason,
            &event.side_cell_key,
            Some(runtime_state),
            plan,
        );
    }
    if runtime_state.disabled {
        let reason = runtime_state
            .disable_reason
            .clone()
            .unwrap_or_else(|| "side_cell_disabled".to_string());
        let code = if reason == "probe_budget_exhausted" {
            AdmissionDecisionCode::ProbeBudgetExhausted
        } else if reason == "realized_probe_outcomes_fail_learning_threshold" {
            AdmissionDecisionCode::RealizedProbeOutcomesFailLearningThreshold
        } else {
            AdmissionDecisionCode::SideCellDisabled
        };
        return decision(
            code,
            reason,
            &event.side_cell_key,
            Some(runtime_state),
            plan,
        );
    }
    if runtime_state.cooldown_active {
        return decision(
            AdmissionDecisionCode::CooldownActive,
            "side_cell_probe_cooldown_active",
            &event.side_cell_key,
            Some(runtime_state),
            plan,
        );
    }
    if !risk_state.trim().eq_ignore_ascii_case("NORMAL") {
        return decision(
            AdmissionDecisionCode::RiskStateNotNormal,
            "session_halt_or_guardian_risk_state_not_normal",
            &event.side_cell_key,
            Some(runtime_state),
            plan,
        );
    }
    if plan.order_authority != ORDER_AUTHORITY_GRANTED {
        return decision(
            AdmissionDecisionCode::OrderAuthorityNotGranted,
            "plan_matches_candidate_but_artifact_has_no_order_authority",
            &event.side_cell_key,
            Some(runtime_state),
            plan,
        );
    }
    if let Err(reason) =
        validate_operator_authorization(plan, candidate, &event.side_cell_key, now_ms)
    {
        return decision(
            AdmissionDecisionCode::OperatorAuthorizationInvalid,
            reason,
            &event.side_cell_key,
            Some(runtime_state),
            plan,
        );
    }
    if !adapter_enabled {
        return decision(
            AdmissionDecisionCode::AdapterDisabled,
            "runtime_adapter_enable_flag_is_false",
            &event.side_cell_key,
            Some(runtime_state),
            plan,
        );
    }
    decision(
        AdmissionDecisionCode::AdmitDemoLearningProbe,
        "selected_side_cell_with_budget_cooldown_clear_and_explicit_demo_probe_authority",
        &event.side_cell_key,
        Some(runtime_state),
        plan,
    )
}

/// operator authorization envelope 的 candidate 無關核心判定。
///
/// 為什麼抽共用純函數(2026-07-02 soak dispatch-edge containment 設計 §1.2):
/// soak 圍欄(demo_learning_lane_soak_gate)與 probe admission 必須使用同一份
/// envelope 判準;若兩端各自實現,任一側漂移即成安全洞(guard 攔錯窗口或
/// admission 放錯單)。side_cell 匹配與 candidate 預算比對屬 candidate 相關
/// 檢查,留在 `validate_operator_authorization`。回傳 Ok(expires_at_ms)。
pub fn validate_operator_authorization_envelope(
    operator_authorization: Option<&BoundedProbeOperatorAuthorization>,
    now_ms: u64,
) -> Result<u64, &'static str> {
    let Some(auth) = operator_authorization else {
        return Err("operator_authorization_missing_for_order_authority");
    };
    if auth.schema_version != BOUNDED_PROBE_OPERATOR_AUTHORIZATION_SCHEMA_VERSION {
        return Err("operator_authorization_schema_mismatch");
    }
    if auth.status != BOUNDED_PROBE_AUTHORIZED_STATUS {
        return Err("operator_authorization_status_not_authorized");
    }
    if auth.authorization_id.as_deref().unwrap_or("").trim().is_empty() {
        return Err("operator_authorization_id_missing");
    }
    if auth.operator_id.as_deref().unwrap_or("").trim().is_empty() {
        return Err("operator_authorization_operator_id_missing");
    }
    if auth.authority_path_readiness_status != AUTHORITY_PATH_PATCH_READY_STATUS {
        return Err("operator_authorization_authority_path_not_ready");
    }
    if auth.main_cost_gate_adjustment != "NONE" {
        return Err("operator_authorization_cost_gate_adjustment_not_none");
    }
    if auth.order_authority != ORDER_AUTHORITY_GRANTED {
        return Err("operator_authorization_order_authority_mismatch");
    }
    if auth.max_authorized_probe_orders.unwrap_or(0) == 0 {
        return Err("operator_authorization_probe_budget_missing");
    }
    if auth.probe_authority_granted != Some(true) {
        return Err("operator_authorization_probe_authority_not_granted");
    }
    if auth.order_authority_granted != Some(true) {
        return Err("operator_authorization_order_authority_not_granted");
    }
    if auth.promotion_evidence != Some(false) {
        return Err("operator_authorization_promotion_boundary_invalid");
    }
    let Some(expires_at_utc) = auth.expires_at_utc.as_deref() else {
        return Err("operator_authorization_expiry_missing");
    };
    let Ok(parsed) = DateTime::parse_from_rfc3339(expires_at_utc) else {
        return Err("operator_authorization_expiry_malformed");
    };
    let expires_ms = parsed.with_timezone(&Utc).timestamp_millis();
    if expires_ms < 0 || expires_ms as u64 <= now_ms {
        return Err(OPERATOR_AUTHORIZATION_EXPIRED_REASON);
    }
    Ok(expires_ms as u64)
}

fn validate_operator_authorization(
    plan: &DemoLearningLanePlan,
    candidate: &ProbeCandidate,
    side_cell_key: &str,
    now_ms: u64,
) -> Result<(), &'static str> {
    // candidate 無關檢查走共用核心(與 soak 圍欄同一實現,判準不可能漂移)。
    // 注意:多重缺陷 envelope 的 reason 先後順序與抽取前略有差異(核心檢查
    // 先於 side_cell / candidate 預算),accept/reject 語義逐位不變。
    // 跨實現註記(E2 2026-07-03 F3):Python 平行判準(runtime_adapter.py:274-296、
    // bounded_probe_plan_inclusion_review.py:310-325)保持舊檢查順序(side_cell
    // 先於 expiry);同一多缺陷 envelope 兩實現的 reason 字串可能不同——離線
    // Rust-vs-Python 對賬按 reason diff 屬預期噪音,accept/reject 逐位等價。
    validate_operator_authorization_envelope(plan.operator_authorization.as_ref(), now_ms)?;
    let Some(auth) = plan.operator_authorization.as_ref() else {
        return Err("operator_authorization_missing_for_order_authority");
    };
    if auth.side_cell_key.trim() != side_cell_key {
        return Err("operator_authorization_side_cell_mismatch");
    }
    if candidate.max_probe_orders() > auth.max_authorized_probe_orders.unwrap_or(0) {
        return Err("operator_authorization_probe_budget_below_candidate_budget");
    }
    Ok(())
}

/// soak dispatch-edge 圍欄的 envelope 三態(設計 §1.2)。
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum SoakEnvelopeState {
    /// 可讀+有效:圍欄武裝;expires_at_ms = operator 親簽的到期時刻。
    Active { expires_at_ms: u64 },
    /// 可讀+已確定過期:唯一一種可由 plan 內容直接證明的確定性解除證據。
    Expired,
    /// 不可讀/缺檔/壞 JSON/schema 錯/envelope 欄位無效:fail-closed 照攔。
    /// 為什麼 fail-closed:任何存疑狀態都不得成為放行邊(不確定默認收縮);
    /// 解除只能靠確定性過期證據(Expired,或呼叫端的 last_good 硬上界超時)。
    Indeterminate { reason: String },
}

/// 把「plan 檔讀取結果」分類成 soak 圍欄三態。純函數:讀檔 IO 由呼叫端
/// (demo_learning_lane_soak_gate)持有,本模組維持零 IO 契約。
/// `plan_json_read`:Ok = 檔案內容;Err = 讀檔失敗簡述(缺檔/IO 錯)。
pub fn soak_envelope_state(
    plan_json_read: Result<&str, &str>,
    now_ms: u64,
) -> SoakEnvelopeState {
    let plan_json = match plan_json_read {
        Ok(content) => content,
        Err(read_err) => {
            return SoakEnvelopeState::Indeterminate {
                reason: format!("plan_unreadable:{read_err}"),
            }
        }
    };
    let plan = match DemoLearningLanePlan::from_json_str(plan_json) {
        Ok(plan) => plan,
        Err(_) => {
            return SoakEnvelopeState::Indeterminate {
                reason: "plan_json_parse_failed".to_string(),
            }
        }
    };
    if plan.schema_version != PLAN_SCHEMA_VERSION {
        return SoakEnvelopeState::Indeterminate {
            reason: "plan_schema_version_mismatch".to_string(),
        };
    }
    match validate_operator_authorization_envelope(plan.operator_authorization.as_ref(), now_ms) {
        Ok(expires_at_ms) => SoakEnvelopeState::Active { expires_at_ms },
        Err(OPERATOR_AUTHORIZATION_EXPIRED_REASON) => SoakEnvelopeState::Expired,
        Err(reason) => SoakEnvelopeState::Indeterminate {
            reason: reason.to_string(),
        },
    }
}

fn plan_is_stale_or_missing_generated_at(
    generated_at_utc: Option<&str>,
    now_ms: u64,
    cfg: &AdmissionConfig,
) -> bool {
    let Some(value) = generated_at_utc else {
        return true;
    };
    let Ok(parsed) = DateTime::parse_from_rfc3339(value) else {
        return true;
    };
    let generated_ms = parsed.with_timezone(&Utc).timestamp_millis();
    if generated_ms < 0 {
        return true;
    }
    if generated_ms as u64 > now_ms {
        return true;
    }
    let age_ms = now_ms.saturating_sub(generated_ms as u64);
    age_ms > cfg.max_plan_age_hours.saturating_mul(3_600_000)
}

fn decision(
    code: AdmissionDecisionCode,
    reason: impl Into<String>,
    side_cell_key: &str,
    runtime_state: Option<SideCellRuntimeState>,
    plan: &DemoLearningLanePlan,
) -> AdmissionDecision {
    let allowed = code.allowed_to_submit_order();
    AdmissionDecision {
        schema_version: ADAPTER_SCHEMA_VERSION,
        decision: code,
        reason: reason.into(),
        allowed_to_submit_order: allowed,
        no_order_authority: !allowed,
        side_cell_key: side_cell_key.to_string(),
        runtime_state,
        plan_summary: PlanSummary::from_plan(plan),
    }
}
