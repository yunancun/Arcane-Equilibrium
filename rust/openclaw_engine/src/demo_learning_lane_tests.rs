use crate::demo_learning_lane::*;
use crate::demo_learning_lane_ledger::*;
use chrono::{TimeZone, Utc};

const NOW_MS: u64 = 1_782_040_200_000;

fn sample_plan(order_authority: &str) -> DemoLearningLanePlan {
    sample_plan_with_authorization(
        order_authority,
        if order_authority == ORDER_AUTHORITY_GRANTED {
            Some("2026-06-21T12:00:00+00:00")
        } else {
            None
        },
    )
}

fn sample_plan_with_authorization(
    order_authority: &str,
    authorization_expires_at_utc: Option<&str>,
) -> DemoLearningLanePlan {
    let operator_authorization = authorization_expires_at_utc
        .map(|expires_at| {
            format!(
                r#",
            "operator_authorization": {{
                "schema_version": "bounded_demo_probe_operator_authorization_v1",
                "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
                "authorization_id": "auth-demo-eth-sell-001",
                "operator_id": "operator-test",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "expires_at_utc": "{expires_at}",
                "authority_path_readiness_status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
                "main_cost_gate_adjustment": "NONE",
                "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
                "max_authorized_probe_orders": 2,
                "probe_authority_granted": true,
                "order_authority_granted": true,
                "promotion_evidence": false
            }}"#
            )
        })
        .unwrap_or_default();
    let json = format!(
        r#"{{
            "schema_version": "cost_gate_demo_learning_lane_plan_v1",
            "generated_at_utc": "2026-06-21T11:00:00+00:00",
            "status": "READY_FOR_DEMO_LEARNING_PROBE",
            "gate_status": "OPERATOR_REVIEW",
            "main_cost_gate_adjustment": "NONE",
            "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
            "order_authority": "{order_authority}"{operator_authorization},
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
fn no_authority_decision_still_builds_learning_ledger_record() {
    let event = selected_event();
    let decision = evaluate_probe_admission(
        &sample_plan("NOT_GRANTED"),
        &event,
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    let generated_at = Utc.timestamp_millis_opt(NOW_MS as i64).single().unwrap();
    let record = build_admission_ledger_record(&decision, &event, generated_at);

    assert_eq!(record.schema_version, ADAPTER_SCHEMA_VERSION);
    assert_eq!(record.record_type, ADMISSION_LEDGER_RECORD_TYPE);
    assert_eq!(
        record.attempt_id,
        "ctx-demo-ma_crossover-ETHUSDT-1782040200000"
    );
    assert_eq!(record.decision, "ORDER_AUTHORITY_NOT_GRANTED");
    assert!(!record.allowed_to_submit_order);
    assert_eq!(record.side_cell_key, "ma_crossover|ETHUSDT|Sell");
    assert_eq!(record.event.reject_reason_code, ELIGIBLE_REJECT_REASON_CODE);
    assert_eq!(record.event.engine_mode, "live_demo");
    assert_eq!(
        record.runtime_state["remaining_probe_orders"].as_u64(),
        Some(2)
    );
    assert_eq!(record.boundary, ADMISSION_LEDGER_BOUNDARY);

    let json = record.to_json_string().unwrap();
    let parsed = LedgerRecord::from_jsonl_str(&json).unwrap();
    assert_eq!(parsed.len(), 1);
    assert_eq!(
        parsed[0].decision.as_deref(),
        Some("ORDER_AUTHORITY_NOT_GRANTED")
    );
    assert_eq!(
        parsed[0].side_cell_key.as_deref(),
        Some("ma_crossover|ETHUSDT|Sell")
    );
    assert_eq!(
        parsed[0].attempt_id.as_deref(),
        Some(record.attempt_id.as_str())
    );
}

#[test]
fn capture_error_record_keeps_rejected_signal_when_admission_cannot_run() {
    let event = selected_event();
    let generated_at = Utc.timestamp_millis_opt(NOW_MS as i64).single().unwrap();
    let record = build_capture_error_ledger_record(
        &event,
        generated_at,
        "NORMAL",
        "read plan /tmp/openclaw/cost_gate_learning_lane/demo_learning_lane_plan_latest.json failed: missing",
    );

    assert_eq!(record.schema_version, ADAPTER_SCHEMA_VERSION);
    assert_eq!(record.record_type, CAPTURE_ERROR_LEDGER_RECORD_TYPE);
    assert_eq!(record.decision, CAPTURE_ERROR_DECISION);
    assert!(!record.allowed_to_submit_order);
    assert_eq!(
        record.attempt_id,
        "ctx-demo-ma_crossover-ETHUSDT-1782040200000"
    );
    assert_eq!(record.side_cell_key, "ma_crossover|ETHUSDT|Sell");
    assert_eq!(record.event.reject_reason_code, ELIGIBLE_REJECT_REASON_CODE);
    assert_eq!(record.runtime_state["risk_state"].as_str(), Some("NORMAL"));
    assert!(record.capture_error.contains("read plan"));
    assert_eq!(record.reason, "runtime_admission_evaluation_failed");

    let json = record.to_json_string().unwrap();
    let parsed = LedgerRecord::from_jsonl_str(&json).unwrap();
    assert_eq!(parsed.len(), 1);
    assert_eq!(
        parsed[0].record_type.as_deref(),
        Some(CAPTURE_ERROR_LEDGER_RECORD_TYPE)
    );
    assert_eq!(parsed[0].decision.as_deref(), Some(CAPTURE_ERROR_DECISION));
    assert_eq!(
        parsed[0].attempt_id.as_deref(),
        Some("ctx-demo-ma_crossover-ETHUSDT-1782040200000")
    );
}

#[test]
fn ledger_attempt_id_prefers_context_then_signal_then_side_cell_timestamp() {
    let mut event = selected_event();
    assert_eq!(
        attempt_id_for_reject_event(&event),
        "ctx-demo-ma_crossover-ETHUSDT-1782040200000"
    );

    event.context_id = None;
    assert_eq!(
        attempt_id_for_reject_event(&event),
        "sig-demo-ma_crossover-ETHUSDT-1782040200000"
    );

    event.signal_id = None;
    assert_eq!(
        attempt_id_for_reject_event(&event),
        "ma_crossover|ETHUSDT|Sell|1782040200000"
    );
}

#[test]
fn admitted_ledger_record_reenters_runtime_state_cooldown_from_event_ts() {
    let plan = sample_plan(ORDER_AUTHORITY_GRANTED);
    let event = selected_event();
    let admitted = evaluate_probe_admission(
        &plan,
        &event,
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

    let generated_at = Utc.timestamp_millis_opt(NOW_MS as i64).single().unwrap();
    let record = build_admission_ledger_record(&admitted, &event, generated_at);
    let json = record.to_json_string().unwrap();
    let value: serde_json::Value = serde_json::from_str(&json).unwrap();
    assert!(value.get("ts_ms").is_none());
    assert_eq!(value["event"]["ts_ms"].as_u64(), Some(NOW_MS));

    let rows = LedgerRecord::from_jsonl_str(&json).unwrap();
    let cooldown = evaluate_probe_admission(
        &plan,
        &event,
        &rows,
        NOW_MS + 10 * 60_000,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(cooldown.decision, AdmissionDecisionCode::CooldownActive);
    assert_eq!(
        cooldown
            .runtime_state
            .as_ref()
            .unwrap()
            .admitted_attempt_count,
        1
    );
}

#[test]
fn admits_only_with_explicit_authority_and_enable_flag() {
    let missing_authorization = evaluate_probe_admission(
        &sample_plan_with_authorization(ORDER_AUTHORITY_GRANTED, None),
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        missing_authorization.decision,
        AdmissionDecisionCode::OperatorAuthorizationInvalid
    );
    assert_eq!(
        missing_authorization.reason,
        "operator_authorization_missing_for_order_authority"
    );

    let expired_authorization = evaluate_probe_admission(
        &sample_plan_with_authorization(
            ORDER_AUTHORITY_GRANTED,
            Some("2026-06-21T10:59:00+00:00"),
        ),
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(
        expired_authorization.decision,
        AdmissionDecisionCode::OperatorAuthorizationInvalid
    );
    assert_eq!(
        expired_authorization.reason,
        "operator_authorization_expired"
    );

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
        attempt_id: None,
        generated_at_utc: None,
        decision: Some(ADMIT_DECISION.to_string()),
        allowed_to_submit_order: None,
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
        reason: None,
        boundary: None,
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

    // P2-7:UCB-futility 需 n≥8 且 x̄+z₀.₉₀·s/√n<0 才禁用。8 筆全 −8bps(s=0) →
    // UCB=−8<0 → 禁用;n=2 已不足以禁用(默認門檻 2→8)。
    let failed_rows = LedgerRecord::from_jsonl_str(
        r#"
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
        {"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":-8.0}
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

fn side_cell_candidate() -> ProbeCandidate {
    let plan = sample_plan(ORDER_AUTHORITY_GRANTED);
    plan.probe_candidates
        .into_iter()
        .find(|c| c.side_cell_key == "ma_crossover|ETHUSDT|Sell")
        .expect("sample plan has ETHUSDT|Sell candidate")
}

fn outcome_rows_from_nets(nets: &[f64]) -> Vec<LedgerRecord> {
    let lines: String = nets
        .iter()
        .map(|net| {
            format!(
                r#"{{"record_type":"probe_outcome","side_cell_key":"ma_crossover|ETHUSDT|Sell","realized_net_bps":{net}}}"#
            )
        })
        .collect::<Vec<_>>()
        .join("\n");
    LedgerRecord::from_jsonl_str(&lines).unwrap()
}

#[test]
fn ucb_futility_disable_rule_matches_spec_thresholds() {
    // QC spec 測試用例 6:UCB-futility 規則的三個判準點。
    let candidate = side_cell_candidate();
    let cfg = AdmissionConfig::default();

    // n=7 全負 → 未達 n≥8 門檻 → 不禁用(UCB 規則不啟動)。
    let seven_neg = outcome_rows_from_nets(&[-120.0; 7]);
    let state7 = summarize_side_cell_runtime_state(&candidate, &seven_neg, NOW_MS, &cfg);
    assert!(
        !state7.disabled,
        "n=7 不應禁用(未達 n≥8),got reason={:?}",
        state7.disable_reason
    );

    // n=8,x̄=−120,s=200 → UCB = −120 + 1.2816·200/√8 ≈ −29.4 < 0 → 禁用。
    let mut nets_neg120 = vec![-120.0; 8];
    scale_to_mean_std(&mut nets_neg120, -120.0, 200.0);
    let state_neg = summarize_side_cell_runtime_state(&candidate, &outcome_rows_from_nets(&nets_neg120), NOW_MS, &cfg);
    assert!(
        state_neg.disabled,
        "n=8 x̄=−120 s=200 UCB≈−29.4<0 應禁用,got avg={:?} reason={:?}",
        state_neg.avg_realized_net_bps, state_neg.disable_reason
    );

    // n=8,x̄=−80,s=200 → UCB = −80 + 90.6 ≈ +10.6 > 0 → 不禁用。
    let mut nets_neg80 = vec![-80.0; 8];
    scale_to_mean_std(&mut nets_neg80, -80.0, 200.0);
    let state_hold = summarize_side_cell_runtime_state(&candidate, &outcome_rows_from_nets(&nets_neg80), NOW_MS, &cfg);
    assert!(
        !state_hold.disabled,
        "n=8 x̄=−80 s=200 UCB≈+10.6>0 不應禁用,got avg={:?} reason={:?}",
        state_hold.avg_realized_net_bps, state_hold.disable_reason
    );
}

/// 把 8 個等值樣本改造成指定均值與樣本標準差(ddof=1),供 UCB 判準測試。
/// 對稱雙點構造:4 個 mean+d、4 個 mean−d,則 x̄=mean、s=d·√(8/7)。
fn scale_to_mean_std(values: &mut [f64], mean: f64, std: f64) {
    assert_eq!(values.len(), 8);
    // s² = Σ(x−x̄)²/(n−1);對稱雙點 x̄=mean、Σ=8d² → s=d·√(8/7) ⇒ d=s·√(7/8)。
    let d = std * (7.0f64 / 8.0).sqrt();
    for (i, v) in values.iter_mut().enumerate() {
        *v = if i < 4 { mean + d } else { mean - d };
    }
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

// ─────────────────────────────────────────────────────────────────────────
// 2026-07-02 soak dispatch-edge containment §1.2:soak_envelope_state 全矩陣
// + envelope 共用核心(validate_operator_authorization_envelope)不漂移釘子。
// ─────────────────────────────────────────────────────────────────────────

fn plan_json_with_expiry(expires_at_utc: &str) -> String {
    format!(
        r#"{{
            "schema_version": "cost_gate_demo_learning_lane_plan_v1",
            "generated_at_utc": "2026-06-21T11:00:00+00:00",
            "status": "READY_FOR_DEMO_LEARNING_PROBE",
            "gate_status": "OPERATOR_REVIEW",
            "main_cost_gate_adjustment": "NONE",
            "learning_gate_adjustment": "SIDE_CELL_DEMO_PROBE_ONLY_AFTER_ADAPTER_WIRING",
            "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
            "operator_authorization": {{
                "schema_version": "bounded_demo_probe_operator_authorization_v1",
                "status": "BOUNDED_DEMO_PROBE_AUTHORIZED",
                "authorization_id": "auth-demo-eth-sell-001",
                "operator_id": "operator-test",
                "side_cell_key": "ma_crossover|ETHUSDT|Sell",
                "expires_at_utc": "{expires_at_utc}",
                "authority_path_readiness_status": "AUTHORITY_PATH_PATCH_READY_FOR_OPERATOR_REVIEW",
                "main_cost_gate_adjustment": "NONE",
                "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
                "max_authorized_probe_orders": 2,
                "probe_authority_granted": true,
                "order_authority_granted": true,
                "promotion_evidence": false
            }},
            "selected_probe_candidate_count": 0,
            "probe_candidates": []
        }}"#
    )
}

#[test]
fn soak_envelope_state_valid_envelope_is_active_with_expiry() {
    // NOW_MS < 2026-06-21T12:00:00Z(=1_782_043_200_000)→ Active。
    let json = plan_json_with_expiry("2026-06-21T12:00:00+00:00");
    assert_eq!(
        soak_envelope_state(Ok(&json), NOW_MS),
        SoakEnvelopeState::Active {
            expires_at_ms: 1_782_043_200_000
        }
    );
}

#[test]
fn soak_envelope_state_expired_envelope_is_expired() {
    let json = plan_json_with_expiry("2026-06-21T10:00:00+00:00");
    assert_eq!(
        soak_envelope_state(Ok(&json), NOW_MS),
        SoakEnvelopeState::Expired
    );
}

#[test]
fn soak_envelope_state_unreadable_is_indeterminate() {
    let state = soak_envelope_state(Err("No such file or directory"), NOW_MS);
    assert!(
        matches!(&state, SoakEnvelopeState::Indeterminate { reason }
            if reason.starts_with("plan_unreadable:")),
        "缺檔/IO 錯 → indeterminate,got {state:?}"
    );
}

#[test]
fn soak_envelope_state_bad_json_and_schema_are_indeterminate() {
    assert!(matches!(
        soak_envelope_state(Ok("{not json"), NOW_MS),
        SoakEnvelopeState::Indeterminate { reason } if reason == "plan_json_parse_failed"
    ));
    let wrong_schema = plan_json_with_expiry("2026-06-21T12:00:00+00:00")
        .replace("cost_gate_demo_learning_lane_plan_v1", "some_other_schema_v9");
    assert!(matches!(
        soak_envelope_state(Ok(&wrong_schema), NOW_MS),
        SoakEnvelopeState::Indeterminate { reason } if reason == "plan_schema_version_mismatch"
    ));
}

#[test]
fn soak_envelope_state_missing_or_invalid_authorization_is_indeterminate() {
    // 缺 operator_authorization 塊(order_authority 有 grant 也不算數)。
    let json = plan_json_with_expiry("2026-06-21T12:00:00+00:00");
    let plan_no_auth = r#"{
            "schema_version": "cost_gate_demo_learning_lane_plan_v1",
            "status": "READY_FOR_DEMO_LEARNING_PROBE",
            "order_authority": "DEMO_LEARNING_PROBE_GRANTED",
            "main_cost_gate_adjustment": "NONE",
            "probe_candidates": []
        }"#;
    assert!(matches!(
        soak_envelope_state(Ok(plan_no_auth), NOW_MS),
        SoakEnvelopeState::Indeterminate { reason }
            if reason == "operator_authorization_missing_for_order_authority"
    ));

    // 欄位無效(promotion_evidence=true)→ indeterminate,不是 Expired。
    let bad = json.replace(
        r#""promotion_evidence": false"#,
        r#""promotion_evidence": true"#,
    );
    assert!(matches!(
        soak_envelope_state(Ok(&bad), NOW_MS),
        SoakEnvelopeState::Indeterminate { reason }
            if reason == "operator_authorization_promotion_boundary_invalid"
    ));

    // 到期時間戳格式錯 → indeterminate(不可作確定性過期證據)。
    let malformed = plan_json_with_expiry("not-a-timestamp");
    assert!(matches!(
        soak_envelope_state(Ok(&malformed), NOW_MS),
        SoakEnvelopeState::Indeterminate { reason }
            if reason == "operator_authorization_expiry_malformed"
    ));
}

#[test]
fn soak_envelope_state_ignores_plan_staleness_when_envelope_valid() {
    // 刻意決策(§1.2):圍欄判準抽自 validate_operator_authorization,不含
    // plan generated_at staleness(stale 只影響 admission,不影響 soak 窗口)。
    let stale = plan_json_with_expiry("2026-06-21T12:00:00+00:00").replace(
        r#""generated_at_utc": "2026-06-21T11:00:00+00:00""#,
        r#""generated_at_utc": "2020-01-01T00:00:00+00:00""#,
    );
    assert!(matches!(
        soak_envelope_state(Ok(&stale), NOW_MS),
        SoakEnvelopeState::Active { .. }
    ));
}

/// 共用核心不漂移釘子:admission 的 validate_operator_authorization 與
/// soak_envelope_state 對同一 plan 必須同判(有效→admit 路徑通過 auth 檢查;
/// 過期→admission reason 與 soak Expired 同源同字串)。
#[test]
fn soak_envelope_core_stays_in_lockstep_with_admission_authorization_check() {
    // 有效 envelope:admission 走到 Admit(auth 檢查通過)。
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
    assert!(matches!(
        soak_envelope_state(
            Ok(&plan_json_with_expiry("2026-06-21T12:00:00+00:00")),
            NOW_MS
        ),
        SoakEnvelopeState::Active { .. }
    ));

    // 過期 envelope:admission reject reason 與 soak 判準用同一常量字串。
    let expired = evaluate_probe_admission(
        &sample_plan_with_authorization(
            ORDER_AUTHORITY_GRANTED,
            Some("2026-06-21T10:59:00+00:00"),
        ),
        &selected_event(),
        &[],
        NOW_MS,
        &AdmissionConfig::default(),
        true,
        "NORMAL",
    );
    assert_eq!(expired.reason, OPERATOR_AUTHORIZATION_EXPIRED_REASON);
    assert_eq!(
        soak_envelope_state(
            Ok(&plan_json_with_expiry("2026-06-21T10:59:00+00:00")),
            NOW_MS
        ),
        SoakEnvelopeState::Expired
    );
}

#[test]
fn normalizes_cost_gate_negative_reason_text() {
    assert_eq!(
        normalize_reject_reason_code("cost_gate(JS-demo): negative edge -15.2 bps blocked"),
        ELIGIBLE_REJECT_REASON_CODE
    );
    assert_eq!(
        normalize_reject_reason_code("cost_gate(JS-demo): estimated=-7.86bps < 0 — blocked / 負估計阻擋"),
        ELIGIBLE_REJECT_REASON_CODE
    );
    assert_eq!(
        normalize_reject_reason_code(
            "cost_gate(JS-demo): edge=2.00bps < threshold=6.50bps (fee=5.00bps, wr=0.50)"
        ),
        "cost_gate(js-demo): edge=2.00bps < threshold=6.50bps (fee=5.00bps, wr=0.50)"
    );
    assert_eq!(
        side_cell_key("ma_crossover", "ethusdt", "Sell"),
        "ma_crossover|ETHUSDT|Sell"
    );
}
