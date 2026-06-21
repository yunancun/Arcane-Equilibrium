use crate::demo_learning_lane::*;

const NOW_MS: u64 = 1_782_040_200_000;

fn sample_plan(order_authority: &str) -> DemoLearningLanePlan {
    let json = format!(
        r#"{{
            "schema_version": "cost_gate_demo_learning_lane_plan_v1",
            "generated_at_utc": "2026-06-21T11:00:00+00:00",
            "status": "READY_FOR_DEMO_LEARNING_PROBE",
            "gate_status": "OPERATOR_REVIEW",
            "main_cost_gate_adjustment": "NONE",
            "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
            "order_authority": "{order_authority}",
            "selected_probe_candidate_count": 1,
            "probe_candidates": [
                {{
                    "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                    "strategy_name": "ma_crossover",
                    "symbol": "ETHUSDT",
                    "side": "Sell",
                    "reject_reason_code": "cost_gate_js_demo_negative_edge",
                    "probe_proposal": {{
                        "mode": "demo_only_learning_probe",
                        "max_probe_orders": 2,
                        "cooldown_minutes": 30,
                        "requires_runtime_policy_adapter": true,
                        "requires_probe_attempt_logging": true,
                        "requires_probe_outcome_logging": true
                    }},
                    "guardrails": {{
                        "main_cost_gate_adjustment": "NONE",
                        "may_bypass_main_live_gate": false,
                        "demo_only": true,
                        "paper_not_promotion_evidence": true,
                        "notional_or_qty_not_granted_by_artifact": true
                    }}
                }}
            ]
        }}"#
    );
    DemoLearningLanePlan::from_json_str(&json).unwrap()
}

fn selected_event() -> RejectEvent {
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

#[test]
fn current_plan_matches_candidate_but_keeps_no_order_authority() {
    let decision = evaluate_probe_admission(
        &sample_plan("NOT_GRANTED"),
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );

    assert_eq!(
        decision.decision,
        AdmissionDecisionCode::OrderAuthorityNotGranted
    );
    assert!(!decision.allowed_to_submit_order);
    assert!(decision.no_order_authority);
    assert_eq!(decision.side_cell_key, "ma_crossover|ETHUSDT|Sell");
    assert_eq!(
        decision
            .runtime_state
            .as_ref()
            .unwrap()
            .remaining_probe_orders,
        2
    );
    assert_eq!(decision.plan_summary.main_cost_gate_adjustment, "NONE");
}

#[test]
fn admits_only_with_explicit_authority_and_enable_flag() {
    let disabled = evaluate_probe_admission(
        &sample_plan(ORDER_AUTHORITY_GRANTED),
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        false,
        "NORMAL",
    );
    assert_eq!(disabled.decision, AdmissionDecisionCode::AdapterDisabled);

    let admitted = evaluate_probe_admission(
        &sample_plan(ORDER_AUTHORITY_GRANTED),
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        admitted.decision,
        AdmissionDecisionCode::AdmitDemoLearningProbe
    );
    assert!(admitted.allowed_to_submit_order);
    assert!(!admitted.no_order_authority);
}

#[test]
fn blocks_unselected_side_cell_and_non_negative_cost_gate_reason() {
    let plan = sample_plan(ORDER_AUTHORITY_GRANTED);
    let mut unselected = selected_event();
    unselected.symbol = "BTCUSDT".to_string();
    unselected.side = "Buy".to_string();
    let mut not_negative = selected_event();
    not_negative.reject_reason_code = "cost_gate_atr_unavailable".to_string();

    let unselected_decision = evaluate_probe_admission(
        &plan,
        &unselected,
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        unselected_decision.decision,
        AdmissionDecisionCode::SideCellNotSelected
    );

    let reason_decision = evaluate_probe_admission(
        &plan,
        &not_negative,
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        reason_decision.decision,
        AdmissionDecisionCode::RejectReasonNotEligible
    );
}

#[test]
fn enforces_budget_cooldown_and_failed_outcome_disable() {
    let plan = sample_plan(ORDER_AUTHORITY_GRANTED);
    let event = selected_event();
    let cooldown_rows = vec![LedgerRecord {
        record_type: Some("probe_admission_decision".to_string()),
        decision: Some(ADMIT_DECISION.to_string()),
        admission_decision: None,
        side_cell_key: Some("ma_crossover|ETHUSDT|Sell".to_string()),
        strategy_name: None,
        symbol: None,
        side: None,
        ts_ms: Some(NOW_MS - 10 * 60_000),
        attempt_ts_ms: None,
        generated_at_ms: None,
        event: None,
        realized_net_bps: None,
        disable_reason: None,
    }];
    let cooldown = evaluate_probe_admission(
        &plan,
        &event,
        &cooldown_rows,
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(cooldown.decision, AdmissionDecisionCode::CooldownActive);

    let exhausted_rows = LedgerRecord::from_jsonl_str(
        r#"
        {"record_type":"probe_admission_decision","decision":"ADMIT_DEMO_LEARNING_PROBE","side_cell_key":"ma_crossover|ETHUSDT|Sell","ts_ms":1782033000000}
        {"record_type":"probe_admission_decision","decision":"ADMIT_DEMO_LEARNING_PROBE","side_cell_key":"ma_crossover|ETHUSDT|Sell","ts_ms":1782034000000}
        "#,
    )
    .unwrap();
    let exhausted = evaluate_probe_admission(
        &plan,
        &event,
        &exhausted_rows,
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        exhausted.decision,
        AdmissionDecisionCode::ProbeBudgetExhausted
    );

    let failed_rows = LedgerRecord::from_jsonl_str(
        r#"
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-3.0}
        "#,
    )
    .unwrap();
    let failed = evaluate_probe_admission(
        &plan,
        &event,
        &failed_rows,
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        failed.decision,
        AdmissionDecisionCode::RealizedProbeOutcomesFailLearningThreshold
    );
}

#[test]
fn explicit_side_cell_disable_is_separate_from_risk_state() {
    let plan = sample_plan(ORDER_AUTHORITY_GRANTED);
    let rows = LedgerRecord::from_jsonl_str(
        r#"
        {"record_type":"side_cell_disabled","side_cell_key":"ma_crossover|ETHUSDT|Sell","disable_reason":"manual_disable"}
        "#,
    )
    .unwrap();
    let disabled = evaluate_probe_admission(
        &plan,
        &selected_event(),
        &rows,
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );

    assert_eq!(disabled.decision, AdmissionDecisionCode::SideCellDisabled);
    assert_eq!(disabled.reason, "manual_disable");
}

#[test]
fn rejects_stale_plan_and_main_gate_relaxation() {
    let mut stale = sample_plan(ORDER_AUTHORITY_GRANTED);
    stale.generated_at_utc = Some("2026-06-19T11:00:00+00:00".to_string());
    let stale_decision = evaluate_probe_admission(
        &stale,
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        stale_decision.decision,
        AdmissionDecisionCode::PlanStaleOrMissingGeneratedAt
    );

    let mut future = sample_plan(ORDER_AUTHORITY_GRANTED);
    future.generated_at_utc = Some("2026-06-21T12:00:01+00:00".to_string());
    let future_decision = evaluate_probe_admission(
        &future,
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        future_decision.decision,
        AdmissionDecisionCode::PlanStaleOrMissingGeneratedAt
    );

    let mut relaxed = sample_plan(ORDER_AUTHORITY_GRANTED);
    relaxed.main_cost_gate_adjustment = "LOWER".to_string();
    let relaxed_decision = evaluate_probe_admission(
        &relaxed,
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        relaxed_decision.decision,
        AdmissionDecisionCode::MainCostGateAdjustmentNotAllowed
    );
}

#[test]
fn normalizes_cost_gate_negative_reason_text() {
    assert_eq!(
        normalize_reject_reason_code("cost_gate(JS-demo): negative edge -15.2 bps blocked"),
        ELIGIBLE_REJECT_REASON_CODE
    );
    assert_eq!(
        side_cell_key("ma_crossover", "ethusdt", "Sell"),
        "ma_crossover|ETHUSDT|Sell"
    );
}
