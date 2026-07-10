//! Bounded Demo probe active order contract.
//!
//! This module is intentionally pure Rust construction logic. It converts an
//! already-admitted learning-lane decision plus a near-touch placement into a
//! post-only limit order draft that a separately reviewed dispatch path can
//! forward. It performs no IO and grants no authority by itself.

use crate::bounded_probe_near_touch::{
    post_only_near_touch_or_skip, BboSnapshot, BoundedProbeNearTouchConfig,
    BoundedProbePlacementDecision, BoundedProbePlacementRequest, DEFAULT_MAX_FRESH_BBO_AGE_MS,
    DEFAULT_MAX_INITIAL_PASSIVE_GAP_BPS,
};
use crate::config::risk_config::RiskConfig;
use crate::demo_learning_lane::{
    AdmissionDecision, AdmissionDecisionCode, PlanSummary, RejectEvent, ADAPTER_SCHEMA_VERSION,
    ORDER_AUTHORITY_GRANTED, PLAN_SCHEMA_VERSION,
};
use crate::order_manager::{OrderType, TimeInForce};

// Fail-closed until the reviewed GUI/RiskConfig cap is supplied by admission.
pub const DEFAULT_MAX_DEMO_NOTIONAL_USDT_PER_ORDER: f64 = 0.0;
pub const DEFAULT_MAX_PROBE_INTENTS_BEFORE_REVIEW: u64 = 1;
pub const DEFAULT_ACTIVE_BOUNDED_PROBE_MAKER_TIMEOUT_MS: u64 = 45_000;
pub const ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE: &str = "bounded_probe_active_near_touch";
pub const BYBIT_ORDER_LINK_ID_PREFIX: &str = "oc_";
pub const BYBIT_ORDER_LINK_ID_MAX_LEN: usize = 36;
pub const ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ: u64 = 2_176_782_335;

const ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_MOD: u64 = 101_559_956_668_416;
const ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_LEN: usize = 9;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ActiveBoundedProbeRiskLimits {
    pub demo_only: bool,
    pub allow_live_demo: bool,
    pub max_demo_notional_usdt_per_order: f64,
    pub max_probe_intents_before_review: u64,
    pub one_order_per_admitted_attempt: bool,
    pub max_fresh_bbo_age_ms: u64,
    pub max_initial_passive_gap_bps: f64,
    pub maker_timeout_ms: u64,
}

impl Default for ActiveBoundedProbeRiskLimits {
    fn default() -> Self {
        Self {
            demo_only: true,
            allow_live_demo: true,
            max_demo_notional_usdt_per_order: DEFAULT_MAX_DEMO_NOTIONAL_USDT_PER_ORDER,
            max_probe_intents_before_review: DEFAULT_MAX_PROBE_INTENTS_BEFORE_REVIEW,
            one_order_per_admitted_attempt: true,
            max_fresh_bbo_age_ms: DEFAULT_MAX_FRESH_BBO_AGE_MS,
            max_initial_passive_gap_bps: DEFAULT_MAX_INITIAL_PASSIVE_GAP_BPS,
            maker_timeout_ms: DEFAULT_ACTIVE_BOUNDED_PROBE_MAKER_TIMEOUT_MS,
        }
    }
}

impl ActiveBoundedProbeRiskLimits {
    fn validate(&self) -> bool {
        self.demo_only
            && self.max_demo_notional_usdt_per_order.is_finite()
            && self.max_demo_notional_usdt_per_order > 0.0
            && (1..=10).contains(&self.max_probe_intents_before_review)
            && self.one_order_per_admitted_attempt
            && (1..=60_000).contains(&self.max_fresh_bbo_age_ms)
            && self.max_initial_passive_gap_bps.is_finite()
            && (0.0..=10_000.0).contains(&self.max_initial_passive_gap_bps)
            && (1_000..=60_000).contains(&self.maker_timeout_ms)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct ActiveBoundedProbeOrderRequest {
    pub reject_event: RejectEvent,
    pub admission_decision: AdmissionDecision,
    pub placement_decision: BoundedProbePlacementDecision,
    pub qty: f64,
    pub order_link_id: String,
    pub decision_lease_id: Option<String>,
    pub risk_state: String,
    pub limits: ActiveBoundedProbeRiskLimits,
}

#[derive(Debug, Clone, PartialEq)]
pub enum ActiveBoundedProbeOrderDecision {
    Submit(ActiveBoundedProbeOrderDraft),
    Skip(ActiveBoundedProbeOrderSkip),
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ActiveBoundedProbeOrderSkipReason {
    AdmissionNotAllowed,
    NotDemoEngineMode,
    RiskLimitsInvalid,
    PlacementSkipped,
    SideCellMismatch,
    QtyInvalid,
    PlacementInvalid,
    NotionalLimitExceeded,
    InvalidOrderLinkId,
    MissingLineage,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ActiveBoundedProbeOrderSkip {
    pub side_cell_key: String,
    pub reason: ActiveBoundedProbeOrderSkipReason,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ActiveBoundedProbeOrderDraft {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub strategy: String,
    pub paper_fill_ts: u64,
    pub decision_lease_id: String,
    pub order_type: OrderType,
    pub time_in_force: TimeInForce,
    pub limit_price: f64,
    pub reference_price: f64,
    pub touch_gap_bps: f64,
    pub max_demo_notional_usdt_per_order: f64,
    pub maker_timeout_ms: u64,
    pub bounded_probe_attempt_id: String,
    pub lineage: ActiveBoundedProbeLineage,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ActiveBoundedProbeLineage {
    pub side_cell_key: String,
    pub context_id: String,
    pub signal_id: String,
    pub bounded_probe_attempt: String,
    pub order_id: Option<String>,
    pub order_link_id: String,
    pub fill_id: Option<String>,
    pub fee: Option<f64>,
    pub exec_fee: Option<f64>,
    pub slippage_bps: Option<f64>,
    pub matched_blocked_control: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ActiveBoundedProbeProofKey {
    pub side_cell_key: String,
    pub engine_mode: String,
    pub signal_ts_ms: u64,
    pub context_id: String,
    pub signal_id: String,
    pub order_link_id: String,
    pub decision_lease_id: String,
    pub reference_source: String,
}

pub fn bounded_probe_attempt_record_type() -> &'static str {
    "bounded_probe_attempt"
}

pub fn learning_probe_admission_is_demo_only(engine_mode: &str) -> bool {
    matches!(
        engine_mode.trim().to_ascii_lowercase().as_str(),
        "demo" | "live_demo"
    )
}

pub fn learning_probe_admission_is_live_demo(engine_mode: &str) -> bool {
    engine_mode.trim().eq_ignore_ascii_case("live_demo")
}

pub fn active_bounded_probe_effective_notional_within_cap(
    effective_qty: f64,
    effective_limit_price: f64,
    max_demo_notional_usdt_per_order: f64,
) -> bool {
    if !effective_qty.is_finite()
        || effective_qty <= 0.0
        || !effective_limit_price.is_finite()
        || effective_limit_price <= 0.0
        || !max_demo_notional_usdt_per_order.is_finite()
        || max_demo_notional_usdt_per_order <= 0.0
    {
        return false;
    }
    let notional = effective_qty * effective_limit_price;
    notional.is_finite() && notional <= max_demo_notional_usdt_per_order
}

pub fn active_bounded_probe_risk_limits_from_gui_risk_config(
    risk_config: &RiskConfig,
    accepted_demo_equity_usdt: f64,
) -> Option<ActiveBoundedProbeRiskLimits> {
    if !accepted_demo_equity_usdt.is_finite() || accepted_demo_equity_usdt <= 0.0 {
        return None;
    }
    let per_trade_pct = risk_config.limits.per_trade_risk_pct;
    let position_size_max_pct = risk_config.limits.position_size_max_pct;
    let max_order_notional_usdt = risk_config.limits.max_order_notional_usdt;
    if !per_trade_pct.is_finite()
        || per_trade_pct <= 0.0
        || !position_size_max_pct.is_finite()
        || position_size_max_pct <= 0.0
        || position_size_max_pct > 100.0
        || !max_order_notional_usdt.is_finite()
        || max_order_notional_usdt < 0.0
    {
        return None;
    }

    let per_trade_budget_usdt = accepted_demo_equity_usdt * per_trade_pct;
    let single_position_budget_usdt = accepted_demo_equity_usdt * (position_size_max_pct / 100.0);
    if !per_trade_budget_usdt.is_finite()
        || per_trade_budget_usdt <= 0.0
        || !single_position_budget_usdt.is_finite()
        || single_position_budget_usdt <= 0.0
    {
        return None;
    }

    let mut effective_single_order_cap_usdt =
        per_trade_budget_usdt.min(single_position_budget_usdt);
    if max_order_notional_usdt > 0.0 {
        effective_single_order_cap_usdt =
            effective_single_order_cap_usdt.min(max_order_notional_usdt);
    }
    if !effective_single_order_cap_usdt.is_finite() || effective_single_order_cap_usdt <= 0.0 {
        return None;
    }

    Some(ActiveBoundedProbeRiskLimits {
        max_demo_notional_usdt_per_order: effective_single_order_cap_usdt,
        ..ActiveBoundedProbeRiskLimits::default()
    })
}

pub fn active_bounded_probe_pending_admission_placeholder(
    reject_event: &RejectEvent,
) -> AdmissionDecision {
    AdmissionDecision {
        schema_version: ADAPTER_SCHEMA_VERSION,
        decision: AdmissionDecisionCode::AdapterDisabled,
        reason: "active_bounded_probe_request_pending_runtime_admission".to_string(),
        allowed_to_submit_order: false,
        no_order_authority: true,
        side_cell_key: reject_event.side_cell_key(),
        runtime_state: None,
        plan_summary: PlanSummary {
            schema_version: PLAN_SCHEMA_VERSION.to_string(),
            status: String::new(),
            gate_status: String::new(),
            main_cost_gate_adjustment: "NONE".to_string(),
            learning_gate_adjustment: String::new(),
            order_authority: "NOT_GRANTED".to_string(),
            selected_probe_candidate_count: 0,
        },
    }
}

#[allow(clippy::too_many_arguments)]
pub fn candidate_matched_active_bounded_probe_proof_key(
    engine_mode: &str,
    signal_ts_ms: u64,
    strategy_name: &str,
    symbol: &str,
    side: &str,
    context_id: Option<&str>,
    signal_id: Option<&str>,
    order_link_id: &str,
    decision_lease_id: Option<&str>,
    reference_source: Option<&str>,
) -> Option<ActiveBoundedProbeProofKey> {
    if engine_mode.trim() != engine_mode
        || !learning_probe_admission_is_demo_only(engine_mode)
        || signal_ts_ms == 0
    {
        return None;
    }
    let reference_source = reference_source?;
    if reference_source != ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE {
        return None;
    }
    let context_id = context_id?;
    let signal_id = signal_id?;
    let decision_lease_id = decision_lease_id?;
    if !lineage_component_is_stable(context_id)
        || !lineage_component_is_stable(signal_id)
        || !lineage_component_is_stable(decision_lease_id)
    {
        return None;
    }
    let side_cell_key = active_bounded_probe_side_cell_key(strategy_name, symbol, side)?;
    if !is_candidate_bound_bounded_probe_order_link_id(
        order_link_id,
        engine_mode,
        signal_ts_ms,
        &side_cell_key,
        context_id,
        signal_id,
    ) {
        return None;
    }
    Some(ActiveBoundedProbeProofKey {
        side_cell_key,
        engine_mode: engine_mode.trim().to_ascii_lowercase(),
        signal_ts_ms,
        context_id: context_id.to_string(),
        signal_id: signal_id.to_string(),
        order_link_id: order_link_id.to_string(),
        decision_lease_id: decision_lease_id.to_string(),
        reference_source: reference_source.to_string(),
    })
}

pub fn candidate_matched_bounded_probe_order_from_bbo(
    mut request: ActiveBoundedProbeOrderRequest,
    bbo: BboSnapshot,
) -> ActiveBoundedProbeOrderDecision {
    let config = BoundedProbeNearTouchConfig {
        max_fresh_bbo_age_ms: request.limits.max_fresh_bbo_age_ms,
        max_initial_passive_gap_bps: request.limits.max_initial_passive_gap_bps,
    };
    request.placement_decision = post_only_near_touch_or_skip(&BoundedProbePlacementRequest {
        side_cell_key: request.reject_event.side_cell_key(),
        is_buy: request.reject_event.side.eq_ignore_ascii_case("Buy"),
        now_ms: request.reject_event.ts_ms,
        bbo,
        config,
    });
    candidate_matched_bounded_probe_order(request)
}

pub fn candidate_matched_bounded_probe_order(
    request: ActiveBoundedProbeOrderRequest,
) -> ActiveBoundedProbeOrderDecision {
    let side_cell_key = request.reject_event.side_cell_key();
    let order_authority_granted =
        request.admission_decision.plan_summary.order_authority == ORDER_AUTHORITY_GRANTED;
    let allowed_to_submit_order = request.admission_decision.allowed_to_submit_order
        && request
            .admission_decision
            .decision
            .allowed_to_submit_order()
        && request.admission_decision.decision == AdmissionDecisionCode::AdmitDemoLearningProbe
        && !request.admission_decision.no_order_authority
        && order_authority_granted
        && request
            .admission_decision
            .plan_summary
            .main_cost_gate_adjustment
            == "NONE";
    if !allowed_to_submit_order {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::AdmissionNotAllowed,
        );
    }

    if !learning_probe_admission_is_demo_only(&request.reject_event.engine_mode)
        || (!request.limits.allow_live_demo
            && learning_probe_admission_is_live_demo(&request.reject_event.engine_mode))
    {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::NotDemoEngineMode,
        );
    }
    if !request.limits.validate() || !request.risk_state.trim().eq_ignore_ascii_case("NORMAL") {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::RiskLimitsInvalid,
        );
    }

    let placement = match request.placement_decision {
        BoundedProbePlacementDecision::Submit(placement) => placement,
        BoundedProbePlacementDecision::Skip(_) => {
            return skip(
                side_cell_key,
                ActiveBoundedProbeOrderSkipReason::PlacementSkipped,
            )
        }
    };
    if placement.side_cell_key != side_cell_key
        || request.admission_decision.side_cell_key != side_cell_key
    {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::SideCellMismatch,
        );
    }
    if !placement.limit_price.is_finite()
        || placement.limit_price <= 0.0
        || !placement.reference_price.is_finite()
        || placement.reference_price <= 0.0
    {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::PlacementInvalid,
        );
    }
    if !request.qty.is_finite() || request.qty <= 0.0 {
        return skip(side_cell_key, ActiveBoundedProbeOrderSkipReason::QtyInvalid);
    }
    if !active_bounded_probe_effective_notional_within_cap(
        request.qty,
        placement.limit_price,
        request.limits.max_demo_notional_usdt_per_order,
    ) {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::NotionalLimitExceeded,
        );
    }
    let Some(context_id) = request.reject_event.context_id.clone() else {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::MissingLineage,
        );
    };
    let Some(signal_id) = request.reject_event.signal_id.clone() else {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::MissingLineage,
        );
    };
    let Some(decision_lease_id) = request
        .decision_lease_id
        .clone()
        .filter(|lease_id| !lease_id.trim().is_empty())
    else {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::MissingLineage,
        );
    };
    if !is_candidate_bound_bounded_probe_order_link_id(
        &request.order_link_id,
        &request.reject_event.engine_mode,
        request.reject_event.ts_ms,
        &side_cell_key,
        &context_id,
        &signal_id,
    ) {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::InvalidOrderLinkId,
        );
    }

    let bounded_probe_attempt = bounded_probe_attempt_record_type().to_string();
    ActiveBoundedProbeOrderDecision::Submit(ActiveBoundedProbeOrderDraft {
        symbol: request.reject_event.symbol,
        is_long: request.reject_event.side.eq_ignore_ascii_case("Buy"),
        qty: request.qty,
        strategy: request.reject_event.strategy_name,
        paper_fill_ts: request.reject_event.ts_ms,
        decision_lease_id,
        order_type: OrderType::Limit,
        time_in_force: TimeInForce::PostOnly,
        limit_price: placement.limit_price,
        reference_price: placement.reference_price,
        touch_gap_bps: placement.touch_gap_bps,
        max_demo_notional_usdt_per_order: request.limits.max_demo_notional_usdt_per_order,
        maker_timeout_ms: request.limits.maker_timeout_ms,
        bounded_probe_attempt_id: context_id.clone(),
        lineage: ActiveBoundedProbeLineage {
            side_cell_key,
            context_id,
            signal_id,
            bounded_probe_attempt,
            order_id: None,
            order_link_id: request.order_link_id,
            fill_id: None,
            fee: None,
            exec_fee: None,
            slippage_bps: None,
            matched_blocked_control: None,
        },
    })
}

pub fn is_bybit_safe_order_link_id(order_link_id: &str) -> bool {
    let trimmed = order_link_id.trim();
    !trimmed.is_empty()
        && trimmed == order_link_id
        && trimmed.starts_with(BYBIT_ORDER_LINK_ID_PREFIX)
        && trimmed.len() <= BYBIT_ORDER_LINK_ID_MAX_LEN
        && trimmed
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || byte == b'_' || byte == b'-')
}

// F11(E4 2026-07-04 補審):四段版 is_bybit_safe_order_link_id_for_engine_mode 已刪除。
// 該版驗證的是無 lineage hash 的舊格式(oc_<mode>_<ts>_<十進位 seq>),生產格式為五段
// (base36 seq + FNV lineage hash),由更嚴格的 is_candidate_bound_bounded_probe_order_link_id
// 驗證;全庫 grep 零 caller,保留只會誤導審閱者以為存在第二條校驗路徑。

pub fn bounded_probe_order_link_id_for_candidate(
    engine_mode: &str,
    ts_ms: u64,
    seq: u64,
    side_cell_key: &str,
    context_id: &str,
    signal_id: &str,
) -> Option<String> {
    let mode_tag = order_link_engine_mode_tag(engine_mode)?;
    if ts_ms == 0
        || !(1..=ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ).contains(&seq)
        || !lineage_component_is_stable(side_cell_key)
        || !lineage_component_is_stable(context_id)
        || !lineage_component_is_stable(signal_id)
    {
        return None;
    }
    let seq_part = to_base36(seq);
    let lineage_hash = candidate_lineage_hash_tag(side_cell_key, context_id, signal_id)?;
    let order_link_id = format!("oc_{mode_tag}_{ts_ms}_{seq_part}_{lineage_hash}");
    is_bybit_safe_order_link_id(&order_link_id).then_some(order_link_id)
}

pub fn is_candidate_bound_bounded_probe_order_link_id(
    order_link_id: &str,
    engine_mode: &str,
    ts_ms: u64,
    side_cell_key: &str,
    context_id: &str,
    signal_id: &str,
) -> bool {
    if !is_bybit_safe_order_link_id(order_link_id) {
        return false;
    }
    let Some(expected_mode_tag) = order_link_engine_mode_tag(engine_mode) else {
        return false;
    };
    let Some(expected_hash) = candidate_lineage_hash_tag(side_cell_key, context_id, signal_id)
    else {
        return false;
    };
    let parts: Vec<&str> = order_link_id.split('_').collect();
    if parts.len() != 5 {
        return false;
    }
    let [prefix, mode_tag, ts_part, seq_part, hash_part]: [&str; 5] =
        [parts[0], parts[1], parts[2], parts[3], parts[4]];
    let Some(seq) = parse_base36(seq_part) else {
        return false;
    };
    prefix == "oc"
        && mode_tag == expected_mode_tag
        && ts_part == ts_ms.to_string()
        && (1..=ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ).contains(&seq)
        && seq_part == to_base36(seq)
        && hash_part == expected_hash
}

fn order_link_engine_mode_tag(engine_mode: &str) -> Option<&'static str> {
    match engine_mode.trim().to_ascii_lowercase().as_str() {
        "demo" => Some("dm"),
        "live_demo" => Some("ld"),
        _ => None,
    }
}

fn lineage_component_is_stable(value: &str) -> bool {
    let trimmed = value.trim();
    !trimmed.is_empty() && trimmed == value
}

fn active_bounded_probe_side_cell_key(
    strategy_name: &str,
    symbol: &str,
    side: &str,
) -> Option<String> {
    if !lineage_component_is_stable(strategy_name) || !lineage_component_is_stable(symbol) {
        return None;
    }
    let normalized_side = match side {
        "Buy" | "buy" => "Buy",
        "Sell" | "sell" => "Sell",
        _ => return None,
    };
    Some(format!("{strategy_name}|{symbol}|{normalized_side}"))
}

fn candidate_lineage_hash_tag(
    side_cell_key: &str,
    context_id: &str,
    signal_id: &str,
) -> Option<String> {
    if !lineage_component_is_stable(side_cell_key)
        || !lineage_component_is_stable(context_id)
        || !lineage_component_is_stable(signal_id)
    {
        return None;
    }
    let mut hash = 0xcbf2_9ce4_8422_2325u64;
    for byte in side_cell_key
        .bytes()
        .chain(std::iter::once(0x1e))
        .chain(context_id.bytes())
        .chain(std::iter::once(0x1f))
        .chain(signal_id.bytes())
    {
        hash ^= byte as u64;
        hash = hash.wrapping_mul(0x0000_0100_0000_01b3);
    }
    let mut tag = to_base36(hash % ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_MOD);
    while tag.len() < ACTIVE_BOUNDED_PROBE_LINEAGE_HASH_LEN {
        tag.insert(0, '0');
    }
    Some(tag)
}

fn to_base36(mut value: u64) -> String {
    const DIGITS: &[u8; 36] = b"0123456789abcdefghijklmnopqrstuvwxyz";
    if value == 0 {
        return "0".to_string();
    }
    let mut out = Vec::new();
    while value > 0 {
        let idx = (value % 36) as usize;
        out.push(DIGITS[idx] as char);
        value /= 36;
    }
    out.iter().rev().collect()
}

fn parse_base36(value: &str) -> Option<u64> {
    if value.is_empty() || value.len() > 6 {
        return None;
    }
    let mut out = 0u64;
    for byte in value.bytes() {
        let digit = match byte {
            b'0'..=b'9' => (byte - b'0') as u64,
            b'a'..=b'z' => 10 + (byte - b'a') as u64,
            _ => return None,
        };
        out = out.checked_mul(36)?.checked_add(digit)?;
    }
    Some(out)
}

fn skip(
    side_cell_key: String,
    reason: ActiveBoundedProbeOrderSkipReason,
) -> ActiveBoundedProbeOrderDecision {
    ActiveBoundedProbeOrderDecision::Skip(ActiveBoundedProbeOrderSkip {
        side_cell_key,
        reason,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::demo_learning_lane::{
        AdmissionConfig, DemoLearningLanePlan, RejectEvent, ADAPTER_SCHEMA_VERSION,
    };

    const NOW_MS: u64 = 1_782_040_200_000;
    const GUI_RISK_CAP_USDT: f64 = 955.24342626;

    fn plan() -> DemoLearningLanePlan {
        DemoLearningLanePlan::from_json_str(
            r#"{
                "schema_version": "cost_gate_demo_learning_lane_plan_v1",
                "generated_at_utc": "2026-06-21T11:00:00+00:00",
                "status": "READY_FOR_DEMO_LEARNING_PROBE",
                "gate_status": "OPERATOR_REVIEW",
                "main_cost_gate_adjustment": "NONE",
                "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
                "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
                "operator_authorization": {
                    "schema_version": "bounded_demo_probe_operator_authorization_v1",
                    "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
                    "authorization_id": "auth-demo-eth-sell-001",
                    "operator_id": "operator-test",
                    "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                    "expires_at_utc": "2026-06-21T12:00:00+00:00",
                    "authority_path_readiness_status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
                    "main_cost_gate_adjustment": "NONE",
                    "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
                    "max_authorized_probe_orders": 1,
                    "probe_authority_granted": true,
                    "order_authority_granted": true,
                    "promotion_evidence": false
                },
                "selected_probe_candidate_count": 1,
                "probe_candidates": [{
                    "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                    "strategy_name": "ma_crossover",
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "reject_reason_code": "cost_gate_js_demo_negative_edge",
                    "probe_proposal": {
                        "mode": "demo_only_learning_probe",
                        "max_probe_orders": 1,
                        "cooldown_minutes": 30,
                        "requires_runtime_policy_adapter": true,
                        "requires_probe_attempt_logging": true,
                        "requires_probe_outcome_logging": true
                    },
                    "guardrails": {
                        "main_cost_gate_adjustment": "NONE",
                        "may_bypass_main_live_gate": false,
                        "demo_only": true,
                        "paper_not_promotion_evidence": true,
                        "notional_or_qty_not_granted_by_artifact": true
                    }
                }]
            }"#,
        )
        .unwrap()
    }

    fn event() -> RejectEvent {
        RejectEvent {
            strategy_name: "ma_crossover".to_string(),
            symbol: "ETHUSDT".to_string(),
            side: "Sell".to_string(),
            reject_reason_code: "cost_gate_js_demo_negative_edge".to_string(),
            engine_mode: "live_demo".to_string(),
            ts_ms: NOW_MS,
            context_id: Some("ctx-demo-ma_crossover-ETHUSDT-1782040200000".to_string()),
            signal_id: Some("sig-demo-ma_crossover-ETHUSDT-1782040200000".to_string()),
            candidate_event_context: None,
        }
    }

    fn admitted() -> AdmissionDecision {
        crate::demo_learning_lane::evaluate_probe_admission(
            &plan(),
            &event(),
            &[],
            NOW_MS,
            &AdmissionConfig::default(),
            true,
            "NORMAL",
        )
    }

    fn request() -> ActiveBoundedProbeOrderRequest {
        let reject_event = event();
        let side_cell_key = reject_event.side_cell_key();
        let order_link_id = bounded_probe_order_link_id_for_candidate(
            &reject_event.engine_mode,
            reject_event.ts_ms,
            1,
            &side_cell_key,
            reject_event.context_id.as_deref().unwrap(),
            reject_event.signal_id.as_deref().unwrap(),
        )
        .unwrap();
        ActiveBoundedProbeOrderRequest {
            reject_event,
            admission_decision: admitted(),
            placement_decision: BoundedProbePlacementDecision::Submit(
                crate::bounded_probe_near_touch::BoundedProbeAttemptPlacement {
                    record_type: bounded_probe_attempt_record_type(),
                    side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
                    limit_price: 3_499.9,
                    touch_gap_bps: 0.29,
                    reference_price: 3_500.0,
                    bbo_age_ms: 0,
                },
            ),
            qty: 0.001,
            order_link_id,
            decision_lease_id: Some("lease-demo-1".to_string()),
            risk_state: "NORMAL".to_string(),
            limits: gui_risk_limits(),
        }
    }

    fn gui_risk_limits() -> ActiveBoundedProbeRiskLimits {
        ActiveBoundedProbeRiskLimits {
            max_demo_notional_usdt_per_order: GUI_RISK_CAP_USDT,
            ..ActiveBoundedProbeRiskLimits::default()
        }
    }

    #[test]
    fn admitted_candidate_builds_post_only_limit_order_draft_with_lineage() {
        let decision = candidate_matched_bounded_probe_order(request());
        let ActiveBoundedProbeOrderDecision::Submit(draft) = decision else {
            panic!("expected active bounded probe order draft");
        };

        assert_eq!(draft.order_type, OrderType::Limit);
        assert_eq!(draft.time_in_force, TimeInForce::PostOnly);
        assert_eq!(draft.limit_price, 3_499.9);
        assert_eq!(draft.max_demo_notional_usdt_per_order, GUI_RISK_CAP_USDT);
        assert_eq!(
            draft.maker_timeout_ms,
            DEFAULT_ACTIVE_BOUNDED_PROBE_MAKER_TIMEOUT_MS
        );
        assert_eq!(draft.decision_lease_id, "lease-demo-1");
        assert_eq!(draft.lineage.side_cell_key, "ma_crossover|ETHUSDT|Sell");
        assert_eq!(draft.lineage.bounded_probe_attempt, "bounded_probe_attempt");
        assert_eq!(
            draft.lineage.context_id,
            "ctx-demo-ma_crossover-ETHUSDT-1782040200000"
        );
        assert_eq!(
            draft.lineage.signal_id,
            "sig-demo-ma_crossover-ETHUSDT-1782040200000"
        );
        assert!(is_candidate_bound_bounded_probe_order_link_id(
            &draft.lineage.order_link_id,
            "live_demo",
            NOW_MS,
            "ma_crossover|ETHUSDT|Sell",
            "ctx-demo-ma_crossover-ETHUSDT-1782040200000",
            "sig-demo-ma_crossover-ETHUSDT-1782040200000",
        ));
        assert_eq!(draft.lineage.fee, None);
        assert_eq!(draft.lineage.exec_fee, None);
        assert_eq!(draft.lineage.slippage_bps, None);
        assert_eq!(draft.lineage.matched_blocked_control, None);
    }

    #[test]
    fn demo_engine_mode_accepts_matching_dm_order_link_id() {
        let mut request = request();
        request.reject_event.engine_mode = "demo".to_string();
        request.order_link_id = bounded_probe_order_link_id_for_candidate(
            "demo",
            NOW_MS,
            1,
            &request.reject_event.side_cell_key(),
            request.reject_event.context_id.as_deref().unwrap(),
            request.reject_event.signal_id.as_deref().unwrap(),
        )
        .unwrap();

        let decision = candidate_matched_bounded_probe_order(request);
        let ActiveBoundedProbeOrderDecision::Submit(draft) = decision else {
            panic!("expected demo active bounded probe order draft");
        };
        assert!(is_candidate_bound_bounded_probe_order_link_id(
            &draft.lineage.order_link_id,
            "demo",
            NOW_MS,
            "ma_crossover|ETHUSDT|Sell",
            "ctx-demo-ma_crossover-ETHUSDT-1782040200000",
            "sig-demo-ma_crossover-ETHUSDT-1782040200000",
        ));
    }

    #[test]
    fn non_admitted_decision_stays_skip() {
        let mut request = request();
        request.admission_decision.schema_version = ADAPTER_SCHEMA_VERSION;
        request.admission_decision.allowed_to_submit_order = false;
        request.admission_decision.decision = AdmissionDecisionCode::OrderAuthorityNotGranted;
        request.admission_decision.no_order_authority = true;

        let decision = candidate_matched_bounded_probe_order(request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::AdmissionNotAllowed
        );
    }

    #[test]
    fn notional_limit_blocks_oversized_demo_attempt() {
        let mut request = request();
        request.qty = 1.0;
        let decision = candidate_matched_bounded_probe_order(request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::NotionalLimitExceeded
        );
    }

    #[test]
    fn missing_gui_risk_cap_blocks_active_order() {
        let mut request = request();
        request.limits.max_demo_notional_usdt_per_order = DEFAULT_MAX_DEMO_NOTIONAL_USDT_PER_ORDER;

        let decision = candidate_matched_bounded_probe_order(request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::RiskLimitsInvalid
        );
    }

    #[test]
    fn effective_notional_cap_guard_rejects_post_round_breach_and_invalid_values() {
        assert!(active_bounded_probe_effective_notional_within_cap(
            0.2, 5_000.0, 1_000.0,
        ));
        assert!(!active_bounded_probe_effective_notional_within_cap(
            0.200_001, 5_000.0, 1_000.0,
        ));
        assert!(!active_bounded_probe_effective_notional_within_cap(
            f64::NAN,
            5_000.0,
            1_000.0,
        ));
        assert!(!active_bounded_probe_effective_notional_within_cap(
            0.2,
            f64::INFINITY,
            1_000.0,
        ));
        assert!(!active_bounded_probe_effective_notional_within_cap(
            0.2,
            5_000.0,
            DEFAULT_MAX_DEMO_NOTIONAL_USDT_PER_ORDER,
        ));
    }

    #[test]
    fn gui_risk_config_cap_uses_percent_budget_not_literal_usdt() {
        let mut risk_config = RiskConfig::default();
        risk_config.limits.per_trade_risk_pct = 0.10;
        risk_config.limits.position_size_max_pct = 25.0;
        risk_config.limits.max_order_notional_usdt = 0.0;
        let accepted_demo_equity_usdt = 9_551.369_426;

        let limits = active_bounded_probe_risk_limits_from_gui_risk_config(
            &risk_config,
            accepted_demo_equity_usdt,
        )
        .expect("valid GUI risk config and accepted demo equity should derive a cap");

        let expected_per_trade_budget_usdt = accepted_demo_equity_usdt * 0.10;
        assert!(
            (limits.max_demo_notional_usdt_per_order - expected_per_trade_budget_usdt).abs() < 1e-9
        );
        assert!(limits.max_demo_notional_usdt_per_order > 10.0);
    }

    #[test]
    fn gui_risk_config_cap_respects_single_position_and_absolute_order_ceiling() {
        let mut risk_config = RiskConfig::default();
        risk_config.limits.per_trade_risk_pct = 0.20;
        risk_config.limits.position_size_max_pct = 5.0;
        risk_config.limits.max_order_notional_usdt = 0.0;
        let accepted_demo_equity_usdt = 9_551.369_426;

        let position_limited = active_bounded_probe_risk_limits_from_gui_risk_config(
            &risk_config,
            accepted_demo_equity_usdt,
        )
        .expect("valid GUI risk config should derive position-limited cap");
        let expected_single_position_budget_usdt = accepted_demo_equity_usdt * 0.05;
        assert!(
            (position_limited.max_demo_notional_usdt_per_order
                - expected_single_position_budget_usdt)
                .abs()
                < 1e-9
        );

        risk_config.limits.max_order_notional_usdt = 250.0;
        let absolute_limited = active_bounded_probe_risk_limits_from_gui_risk_config(
            &risk_config,
            accepted_demo_equity_usdt,
        )
        .expect("configured absolute cap should be accepted");
        assert_eq!(absolute_limited.max_demo_notional_usdt_per_order, 250.0);
    }

    #[test]
    fn gui_risk_config_cap_fails_closed_without_positive_demo_equity() {
        let risk_config = RiskConfig::default();
        assert!(active_bounded_probe_risk_limits_from_gui_risk_config(&risk_config, 0.0).is_none());
        assert!(
            active_bounded_probe_risk_limits_from_gui_risk_config(&risk_config, f64::NAN).is_none()
        );
    }

    #[test]
    fn invalid_bybit_order_link_id_blocks_active_order_draft() {
        let mut long_id_request = request();
        long_id_request.order_link_id = "oc_ld_1782040200000_1_with_extra_suffix".to_string();

        let decision = candidate_matched_bounded_probe_order(long_id_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::InvalidOrderLinkId
        );

        let mut wrong_prefix_request = request();
        wrong_prefix_request.order_link_id = "external_ld_1782040200000_1".to_string();
        let decision = candidate_matched_bounded_probe_order(wrong_prefix_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::InvalidOrderLinkId
        );

        let mut bare_prefix_request = request();
        bare_prefix_request.order_link_id = "oc_".to_string();
        let decision = candidate_matched_bounded_probe_order(bare_prefix_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::InvalidOrderLinkId
        );

        let mut wrong_mode_request = request();
        wrong_mode_request.order_link_id = bounded_probe_order_link_id_for_candidate(
            "demo",
            NOW_MS,
            1,
            &wrong_mode_request.reject_event.side_cell_key(),
            wrong_mode_request
                .reject_event
                .context_id
                .as_deref()
                .unwrap(),
            wrong_mode_request
                .reject_event
                .signal_id
                .as_deref()
                .unwrap(),
        )
        .unwrap();
        let decision = candidate_matched_bounded_probe_order(wrong_mode_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::InvalidOrderLinkId
        );

        let mut wrong_ts_request = request();
        wrong_ts_request.order_link_id = bounded_probe_order_link_id_for_candidate(
            "live_demo",
            NOW_MS + 1,
            1,
            &wrong_ts_request.reject_event.side_cell_key(),
            wrong_ts_request.reject_event.context_id.as_deref().unwrap(),
            wrong_ts_request.reject_event.signal_id.as_deref().unwrap(),
        )
        .unwrap();
        let decision = candidate_matched_bounded_probe_order(wrong_ts_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::InvalidOrderLinkId
        );

        let mut zero_seq_request = request();
        zero_seq_request.order_link_id = "oc_ld_1782040200000_0_000000000".to_string();
        let decision = candidate_matched_bounded_probe_order(zero_seq_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::InvalidOrderLinkId
        );

        let mut bad_charset_request = request();
        bad_charset_request.order_link_id = "oc bad id".to_string();
        let decision = candidate_matched_bounded_probe_order(bad_charset_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::InvalidOrderLinkId
        );
    }

    #[test]
    fn active_probe_order_link_id_is_candidate_bound_and_rejects_lineage_drift() {
        let event = event();
        let link_id = bounded_probe_order_link_id_for_candidate(
            &event.engine_mode,
            event.ts_ms,
            36,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        )
        .unwrap();

        assert!(link_id.len() <= BYBIT_ORDER_LINK_ID_MAX_LEN);
        assert!(is_candidate_bound_bounded_probe_order_link_id(
            &link_id,
            &event.engine_mode,
            event.ts_ms,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        ));
        assert!(!is_candidate_bound_bounded_probe_order_link_id(
            &link_id,
            &event.engine_mode,
            event.ts_ms,
            "ma_crossover|BTCUSDT|Sell",
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        ));
        assert!(!is_candidate_bound_bounded_probe_order_link_id(
            &link_id,
            &event.engine_mode,
            event.ts_ms,
            &event.side_cell_key(),
            "ctx-demo-ma_crossover-BTCUSDT-1782040200000",
            event.signal_id.as_deref().unwrap(),
        ));
        assert!(!is_candidate_bound_bounded_probe_order_link_id(
            &link_id,
            &event.engine_mode,
            event.ts_ms,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            "sig-demo-ma_crossover-BTCUSDT-1782040200000",
        ));
        let seq_one_link_id = bounded_probe_order_link_id_for_candidate(
            &event.engine_mode,
            event.ts_ms,
            1,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        )
        .unwrap();
        let leading_zero_seq_link_id = seq_one_link_id.replacen("_1_", "_000001_", 1);
        assert!(!is_candidate_bound_bounded_probe_order_link_id(
            &leading_zero_seq_link_id,
            &event.engine_mode,
            event.ts_ms,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        ));
        assert_eq!(
            bounded_probe_order_link_id_for_candidate(
                &event.engine_mode,
                event.ts_ms,
                0,
                &event.side_cell_key(),
                event.context_id.as_deref().unwrap(),
                event.signal_id.as_deref().unwrap(),
            ),
            None
        );
        assert_eq!(
            bounded_probe_order_link_id_for_candidate(
                &event.engine_mode,
                event.ts_ms,
                ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ + 1,
                &event.side_cell_key(),
                event.context_id.as_deref().unwrap(),
                event.signal_id.as_deref().unwrap(),
            ),
            None
        );
        let max_seq_link_id = bounded_probe_order_link_id_for_candidate(
            &event.engine_mode,
            event.ts_ms,
            ACTIVE_BOUNDED_PROBE_ORDER_LINK_ID_MAX_SEQ,
            &event.side_cell_key(),
            event.context_id.as_deref().unwrap(),
            event.signal_id.as_deref().unwrap(),
        )
        .unwrap();
        assert_eq!(max_seq_link_id.len(), BYBIT_ORDER_LINK_ID_MAX_LEN);
    }

    #[test]
    fn active_bounded_probe_proof_key_requires_active_source_lease_and_candidate_lineage() {
        let event = event();
        let side_cell_key = event.side_cell_key();
        let context_id = event.context_id.as_deref().unwrap();
        let signal_id = event.signal_id.as_deref().unwrap();
        let order_link_id = bounded_probe_order_link_id_for_candidate(
            &event.engine_mode,
            event.ts_ms,
            7,
            &side_cell_key,
            context_id,
            signal_id,
        )
        .unwrap();

        let proof = candidate_matched_active_bounded_probe_proof_key(
            &event.engine_mode,
            event.ts_ms,
            &event.strategy_name,
            &event.symbol,
            &event.side,
            Some(context_id),
            Some(signal_id),
            &order_link_id,
            Some("lease-demo-1"),
            Some(ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE),
        )
        .expect("candidate-matched active proof key");

        assert_eq!(proof.side_cell_key, side_cell_key);
        assert_eq!(proof.engine_mode, "live_demo");
        assert_eq!(proof.signal_ts_ms, event.ts_ms);
        assert_eq!(proof.context_id, context_id);
        assert_eq!(proof.signal_id, signal_id);
        assert_eq!(proof.order_link_id, order_link_id);
        assert_eq!(proof.decision_lease_id, "lease-demo-1");
        assert_eq!(
            proof.reference_source,
            ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE
        );

        assert_eq!(
            candidate_matched_active_bounded_probe_proof_key(
                &event.engine_mode,
                event.ts_ms,
                &event.strategy_name,
                &event.symbol,
                &event.side,
                Some(context_id),
                Some(signal_id),
                &order_link_id,
                Some("lease-demo-1"),
                Some("bounded_probe_near_touch"),
            ),
            None
        );
        assert_eq!(
            candidate_matched_active_bounded_probe_proof_key(
                &event.engine_mode,
                event.ts_ms,
                &event.strategy_name,
                &event.symbol,
                &event.side,
                Some(context_id),
                Some(signal_id),
                &order_link_id,
                None,
                Some(ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE),
            ),
            None
        );
        assert_eq!(
            candidate_matched_active_bounded_probe_proof_key(
                &event.engine_mode,
                event.ts_ms,
                &event.strategy_name,
                &event.symbol,
                &event.side,
                Some("ctx-demo-ma_crossover-BTCUSDT-1782040200000"),
                Some(signal_id),
                &order_link_id,
                Some("lease-demo-1"),
                Some(ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE),
            ),
            None
        );
        assert_eq!(
            candidate_matched_active_bounded_probe_proof_key(
                "paper",
                event.ts_ms,
                &event.strategy_name,
                &event.symbol,
                &event.side,
                Some(context_id),
                Some(signal_id),
                &order_link_id,
                Some("lease-demo-1"),
                Some(ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE),
            ),
            None
        );
        assert_eq!(
            candidate_matched_active_bounded_probe_proof_key(
                " live_demo ",
                event.ts_ms,
                &event.strategy_name,
                &event.symbol,
                &event.side,
                Some(context_id),
                Some(signal_id),
                &order_link_id,
                Some("lease-demo-1"),
                Some(ACTIVE_BOUNDED_PROBE_REFERENCE_SOURCE),
            ),
            None
        );
    }

    #[test]
    fn nonpositive_limit_price_blocks_active_order_draft() {
        let mut request = request();
        request.placement_decision = BoundedProbePlacementDecision::Submit(
            crate::bounded_probe_near_touch::BoundedProbeAttemptPlacement {
                record_type: bounded_probe_attempt_record_type(),
                side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
                limit_price: 0.0,
                touch_gap_bps: 0.29,
                reference_price: 3_500.0,
                bbo_age_ms: 0,
            },
        );

        let decision = candidate_matched_bounded_probe_order(request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::PlacementInvalid
        );
    }

    #[test]
    fn nonpositive_reference_price_blocks_active_order_draft() {
        let mut request = request();
        request.placement_decision = BoundedProbePlacementDecision::Submit(
            crate::bounded_probe_near_touch::BoundedProbeAttemptPlacement {
                record_type: bounded_probe_attempt_record_type(),
                side_cell_key: "ma_crossover|ETHUSDT|Sell".to_string(),
                limit_price: 3_499.9,
                touch_gap_bps: 0.29,
                reference_price: 0.0,
                bbo_age_ms: 0,
            },
        );

        let decision = candidate_matched_bounded_probe_order(request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::PlacementInvalid
        );
    }

    #[test]
    fn invalid_maker_timeout_blocks_active_order_draft() {
        let mut zero_timeout_request = request();
        zero_timeout_request.limits.maker_timeout_ms = 0;

        let decision = candidate_matched_bounded_probe_order(zero_timeout_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::RiskLimitsInvalid
        );

        let mut high_timeout_request = request();
        high_timeout_request.limits.maker_timeout_ms = 60_001;
        let decision = candidate_matched_bounded_probe_order(high_timeout_request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::RiskLimitsInvalid
        );
    }

    #[test]
    fn missing_decision_lease_blocks_active_order_draft() {
        let mut request = request();
        request.decision_lease_id = None;

        let decision = candidate_matched_bounded_probe_order(request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(
            skip.reason,
            ActiveBoundedProbeOrderSkipReason::MissingLineage
        );
    }
}
