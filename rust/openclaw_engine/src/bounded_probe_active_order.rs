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
use crate::demo_learning_lane::{
    AdmissionDecision, AdmissionDecisionCode, RejectEvent, ORDER_AUTHORITY_GRANTED,
};
use crate::order_manager::{OrderType, TimeInForce};

pub const DEFAULT_MAX_DEMO_NOTIONAL_USDT_PER_ORDER: f64 = 10.0;
pub const DEFAULT_MAX_PROBE_INTENTS_BEFORE_REVIEW: u64 = 1;

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ActiveBoundedProbeRiskLimits {
    pub demo_only: bool,
    pub allow_live_demo: bool,
    pub max_demo_notional_usdt_per_order: f64,
    pub max_probe_intents_before_review: u64,
    pub one_order_per_admitted_attempt: bool,
    pub max_fresh_bbo_age_ms: u64,
    pub max_initial_passive_gap_bps: f64,
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
        }
    }
}

impl ActiveBoundedProbeRiskLimits {
    fn validate(&self) -> bool {
        self.demo_only
            && self.max_demo_notional_usdt_per_order.is_finite()
            && self.max_demo_notional_usdt_per_order > 0.0
            && self.max_demo_notional_usdt_per_order <= 1_000.0
            && (1..=10).contains(&self.max_probe_intents_before_review)
            && self.one_order_per_admitted_attempt
            && (1..=60_000).contains(&self.max_fresh_bbo_age_ms)
            && self.max_initial_passive_gap_bps.is_finite()
            && (0.0..=10_000.0).contains(&self.max_initial_passive_gap_bps)
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
    NotionalLimitExceeded,
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
    if !request.qty.is_finite() || request.qty <= 0.0 {
        return skip(side_cell_key, ActiveBoundedProbeOrderSkipReason::QtyInvalid);
    }
    let notional = request.qty * placement.limit_price;
    if !notional.is_finite() || notional > request.limits.max_demo_notional_usdt_per_order {
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
    if request.order_link_id.trim().is_empty() {
        return skip(
            side_cell_key,
            ActiveBoundedProbeOrderSkipReason::MissingLineage,
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
        ActiveBoundedProbeOrderRequest {
            reject_event: event(),
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
            order_link_id: "oc_ld_1782040200000_1".to_string(),
            decision_lease_id: Some("lease-demo-1".to_string()),
            risk_state: "NORMAL".to_string(),
            limits: ActiveBoundedProbeRiskLimits::default(),
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
        assert_eq!(draft.lineage.order_link_id, "oc_ld_1782040200000_1");
        assert_eq!(draft.lineage.fee, None);
        assert_eq!(draft.lineage.exec_fee, None);
        assert_eq!(draft.lineage.slippage_bps, None);
        assert_eq!(draft.lineage.matched_blocked_control, None);
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
    fn missing_decision_lease_blocks_active_order_draft() {
        let mut request = request();
        request.decision_lease_id = None;

        let decision = candidate_matched_bounded_probe_order(request);
        let ActiveBoundedProbeOrderDecision::Skip(skip) = decision else {
            panic!("expected skip");
        };
        assert_eq!(skip.reason, ActiveBoundedProbeOrderSkipReason::MissingLineage);
    }
}
