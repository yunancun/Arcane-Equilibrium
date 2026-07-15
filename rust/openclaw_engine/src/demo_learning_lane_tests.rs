use crate::candidate_event_context::{canonical_sha256, CandidateEventContextV1};
use crate::candidate_evaluation_source_snapshot::*;
use crate::demo_learning_lane::*;
use crate::demo_learning_lane_ledger::*;
use crate::edge_predictor::features::{
    feature_definition_hash, feature_schema_hash, FEATURE_NAMES_V1, FEATURE_SCHEMA_VERSION,
};
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
        candidate_event_context: None,
    }
}

fn rehash_source_snapshot_event_hash(context: &mut CandidateEventContextV1) {
    let mut event_without_hash =
        serde_json::to_value(&context).expect("candidate event context serializes");
    event_without_hash
        .as_object_mut()
        .expect("candidate event context is an object")
        .remove("event_hash");
    context.event_hash = canonical_sha256(&event_without_hash);
}

fn rehash_source_snapshot_event_context(context: &mut CandidateEventContextV1) {
    let portfolio = context
        .portfolio_snapshot
        .as_ref()
        .expect("shared valid context has a portfolio snapshot");
    context.portfolio_snapshot_hash = Some(canonical_sha256(
        &serde_json::to_value(portfolio).expect("portfolio snapshot serializes"),
    ));
    rehash_source_snapshot_event_hash(context);
}

fn source_snapshot_bound_event_context() -> CandidateEventContextV1 {
    let fixture: serde_json::Value = serde_json::from_str(include_str!(
        "../tests/fixtures/candidate_event_context_v1/canonical_fixture.json"
    ))
    .expect("shared candidate event fixture parses");
    let mut context: CandidateEventContextV1 =
        serde_json::from_value(fixture["valid_candidate_event_context"].clone())
            .expect("shared valid context matches the Rust typed contract");
    let portfolio = context
        .portfolio_snapshot
        .as_mut()
        .expect("shared valid context has a portfolio snapshot");
    portfolio.position_count = 2;
    portfolio.gross_mark_notional_usdt = 2_000.0;
    portfolio.net_mark_notional_usdt = -1_000.0;
    rehash_source_snapshot_event_context(&mut context);
    context
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
fn candidate_event_context_is_optional_and_old_ledger_json_stays_compatible() {
    let event = selected_event();
    assert!(event.candidate_event_context.is_none());
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
    let json = record.to_json_string().unwrap();
    let value: serde_json::Value = serde_json::from_str(&json).unwrap();
    assert!(value["event"].get("candidate_event_context").is_none());
    assert!(value["event"]
        .get("candidate_evaluation_source_snapshot")
        .is_none());

    let old_row = r#"{"record_type":"probe_admission_decision","event":{"strategy_name":"ma_crossover","symbol":"ETHUSDT","side":"Sell","ts_ms":1782040200000}}"#;
    let parsed = LedgerRecord::from_jsonl_str(old_row).unwrap();
    assert!(parsed[0]
        .event
        .as_ref()
        .expect("old event remains readable")
        .candidate_event_context
        .is_none());
    assert!(parsed[0]
        .event
        .as_ref()
        .expect("old event remains readable")
        .candidate_evaluation_source_snapshot
        .is_none());

    let observation = |name: &str, value: f64, source: &str| {
        CandidateEvaluationFeatureObservationV1 {
            name: name.to_string(),
            value: Some(value),
            raw_present: true,
            source: source.to_string(),
        }
    };
    let event_context = source_snapshot_bound_event_context();
    let source_snapshot = capture_candidate_evaluation_source_snapshot(
        &event_context,
        Some(CandidateEvaluationScanSourceV1 {
            scan_id: event_context
                .scan_id
                .clone()
                .expect("valid event context has scan identity"),
            scan_ts_ms: event_context.captured_at_ms,
            symbol: event_context.symbol.clone(),
            sector: Some("layer_1".to_string()),
            turnover_24h: Some(1_500_000_000.0),
            beta_proxy: Some(0.85),
            beta_proxy_status: CandidateEvaluationBetaProxyStatusV1::Observed,
        }),
        CandidateEvaluationFeatureSourceV1 {
            schema_version: FEATURE_SCHEMA_VERSION.to_string(),
            schema_hash: feature_schema_hash().to_string(),
            definition_hash: feature_definition_hash().to_string(),
            observations: vec![
                observation("adx_1h", 30.0, "indicator_snapshot.adx.adx"),
                observation(
                    "bb_width_pct",
                    2.0,
                    "indicator_snapshot.bollinger.bandwidth",
                ),
                observation(
                    "atr_pct",
                    1.2,
                    "tick.atr_value+price_event.last_price",
                ),
                observation("funding_rate", 0.0004, "price_event.funding_rate"),
                observation(
                    "realized_vol_1h",
                    1.5,
                    "indicator_snapshot.ewma_vol.ewma_vol",
                ),
                observation(
                    "basis_bps",
                    0.5,
                    "price_event.index_price+price_event.last_price",
                ),
                observation(
                    "orderbook_imbalance_top5",
                    0.1,
                    "price_event.bids5+price_event.asks5",
                ),
                observation(
                    "spread_bps",
                    1.0,
                    "price_event.bid_price+price_event.ask_price",
                ),
                observation("confluence_score", 42.0, "order_intent.confluence_score"),
                observation(
                    "persistence_elapsed_ms",
                    30_000.0,
                    "order_intent.persistence_elapsed_ms",
                ),
                observation("side", -1.0, "order_intent.is_long"),
                observation(
                    "notional_pct_of_bal",
                    5.0,
                    "order_intent.qty+price_event.last_price+paper_state.balance",
                ),
                observation(
                    "concurrent_positions",
                    2.0,
                    "paper_state.positions.count",
                ),
                observation(
                    "same_direction_cnt",
                    1.0,
                    "paper_state.positions.same_direction_count",
                ),
                observation("tod_sin", 0.5, "price_event.ts_ms.utc_hour_sin"),
                observation(
                    "tod_cos",
                    -0.866025403784,
                    "price_event.ts_ms.utc_hour_cos",
                ),
                observation(
                    "is_funding_settlement_window",
                    0.0,
                    "price_event.ts_ms.funding_settlement_window",
                ),
            ],
        },
        CandidateEvaluationPortfolioSourceV1 {
            portfolio_snapshot_hash: event_context.portfolio_snapshot_hash.clone(),
            accepted_demo_equity_usdt: event_context
                .portfolio_snapshot
                .as_ref()
                .and_then(|portfolio| portfolio.accepted_demo_equity_usdt),
            positions: vec![
                CandidateEvaluationPositionV1 {
                    symbol: "BTCUSDT".to_string(),
                    side: "Long".to_string(),
                    quantity: Some(0.01),
                    mark_source: "latest_price".to_string(),
                    mark_price: Some(50_000.0),
                    mark_notional_usdt: Some(500.0),
                    owner_strategy: "ma_crossover".to_string(),
                    entry_context_id: "ctx-demo-ma_crossover-BTCUSDT-1782040100000"
                        .to_string(),
                },
                CandidateEvaluationPositionV1 {
                    symbol: "ETHUSDT".to_string(),
                    side: "Short".to_string(),
                    quantity: Some(0.5),
                    mark_source: "latest_price".to_string(),
                    mark_price: Some(3_000.0),
                    mark_notional_usdt: Some(1_500.0),
                    owner_strategy: "bb_reversion".to_string(),
                    entry_context_id: "ctx-demo-bb_reversion-ETHUSDT-1782040150000"
                        .to_string(),
                },
            ],
            position_count: Some(2),
            gross_mark_notional_usdt: Some(2_000.0),
            net_mark_notional_usdt: Some(-1_000.0),
            empty_position_attestation: false,
        },
    );
    assert_eq!(
        source_snapshot.capture_status,
        CANDIDATE_EVALUATION_SOURCE_CAPTURE_COMPLETE_STATUS
    );
    assert!(source_snapshot.capture_blockers.is_empty());
    assert!(validate_candidate_evaluation_source_snapshot(&source_snapshot, &event_context).is_ok());

    let mut event_hash_mutation = source_snapshot.clone();
    event_hash_mutation.event_hash.push('0');
    assert!(validate_candidate_evaluation_source_snapshot(&event_hash_mutation, &event_context)
        .is_err());
    let mut captured_at_mutation = source_snapshot.clone();
    captured_at_mutation.captured_at_ms += 1;
    assert!(validate_candidate_evaluation_source_snapshot(&captured_at_mutation, &event_context)
        .is_err());
    let mut snapshot_hash_mutation = source_snapshot.clone();
    snapshot_hash_mutation.snapshot_hash.push('0');
    assert!(validate_candidate_evaluation_source_snapshot(&snapshot_hash_mutation, &event_context)
        .is_err());

    let capture_with_scan = |scan| {
        capture_candidate_evaluation_source_snapshot(
            &event_context,
            scan,
            source_snapshot.decision_features.clone(),
            source_snapshot.portfolio.clone(),
        )
    };
    let assert_scan_blocked = |snapshot: &CandidateEvaluationSourceSnapshotV1,
                               expected: &[&str]| {
        assert_eq!(
            snapshot.capture_status,
            CANDIDATE_EVALUATION_SOURCE_CAPTURE_BLOCKED_STATUS
        );
        assert_eq!(
            snapshot.capture_blockers,
            expected
                .iter()
                .map(|blocker| (*blocker).to_string())
                .collect::<Vec<_>>()
        );
        assert!(validate_candidate_evaluation_source_snapshot(snapshot, &event_context).is_ok());
    };

    let missing_scan = capture_with_scan(None);
    assert_scan_blocked(&missing_scan, &["SCAN_SOURCE_MISSING"]);

    let mut mismatched_id = source_snapshot.scan.clone().unwrap();
    mismatched_id.scan_id.push_str("-other");
    assert_scan_blocked(
        &capture_with_scan(Some(mismatched_id)),
        &["SCAN_ID_MISMATCH"],
    );

    let mut mismatched_symbol = source_snapshot.scan.clone().unwrap();
    mismatched_symbol.symbol = "ETHUSDT".to_string();
    assert_scan_blocked(
        &capture_with_scan(Some(mismatched_symbol)),
        &["SCAN_SYMBOL_MISMATCH"],
    );

    let mut zero_timestamp = source_snapshot.scan.clone().unwrap();
    zero_timestamp.scan_ts_ms = 0;
    assert_scan_blocked(
        &capture_with_scan(Some(zero_timestamp)),
        &["SCAN_TIMESTAMP_INVALID"],
    );

    let mut future_timestamp = source_snapshot.scan.clone().unwrap();
    future_timestamp.scan_ts_ms = event_context.captured_at_ms + 1;
    let future_capture = capture_with_scan(Some(future_timestamp));
    assert_scan_blocked(&future_capture, &["SCAN_TIMESTAMP_AFTER_CAPTURE"]);
    let mut stale_hash_mutation = future_capture;
    stale_hash_mutation.scan.as_mut().unwrap().scan_ts_ms -= 1;
    assert!(
        validate_candidate_evaluation_source_snapshot(&stale_hash_mutation, &event_context)
            .is_err()
    );

    let mut missing_sector = source_snapshot.scan.clone().unwrap();
    missing_sector.sector = None;
    assert_scan_blocked(
        &capture_with_scan(Some(missing_sector)),
        &["SCAN_SECTOR_MISSING_OR_INVALID"],
    );

    let mut missing_turnover = source_snapshot.scan.clone().unwrap();
    missing_turnover.turnover_24h = None;
    assert_scan_blocked(
        &capture_with_scan(Some(missing_turnover)),
        &["SCAN_TURNOVER_MISSING_OR_INVALID"],
    );

    let mut invalid_beta = source_snapshot.scan.clone().unwrap();
    invalid_beta.beta_proxy = Some(f64::NAN);
    assert_scan_blocked(
        &capture_with_scan(Some(invalid_beta)),
        &["SCAN_BETA_PROXY_INVALID"],
    );
    let normalized_beta = capture_with_scan(Some({
        let mut scan = source_snapshot.scan.clone().unwrap();
        scan.beta_proxy = Some(f64::INFINITY);
        scan
    }));
    assert_eq!(normalized_beta.scan.as_ref().unwrap().beta_proxy, None);
    assert_eq!(
        normalized_beta.scan.as_ref().unwrap().beta_proxy_status,
        CandidateEvaluationBetaProxyStatusV1::Invalid
    );
    assert_eq!(normalized_beta.snapshot_hash.len(), 64);
    assert!(serde_json::to_string(&normalized_beta).is_ok());

    for boundary_beta in [-0.5, 3.0] {
        let boundary_capture = capture_with_scan(Some({
            let mut scan = source_snapshot.scan.clone().unwrap();
            scan.beta_proxy = Some(boundary_beta);
            scan
        }));
        assert_eq!(
            boundary_capture.capture_status,
            CANDIDATE_EVALUATION_SOURCE_CAPTURE_COMPLETE_STATUS,
            "observed beta boundary {boundary_beta} is inclusive"
        );
        assert!(
            validate_candidate_evaluation_source_snapshot(&boundary_capture, &event_context)
                .is_ok()
        );
    }

    for out_of_range_beta in [-0.500_000_1, 3.000_000_1] {
        let out_of_range_capture = capture_with_scan(Some({
            let mut scan = source_snapshot.scan.clone().unwrap();
            scan.beta_proxy = Some(out_of_range_beta);
            scan
        }));
        assert_scan_blocked(
            &out_of_range_capture,
            &["SCAN_BETA_PROXY_OUT_OF_RANGE"],
        );
        let captured_scan = out_of_range_capture.scan.as_ref().unwrap();
        assert_eq!(
            captured_scan.beta_proxy,
            Some(out_of_range_beta),
            "finite out-of-domain beta remains durable forensic evidence"
        );
        assert_eq!(
            captured_scan.beta_proxy_status,
            CandidateEvaluationBetaProxyStatusV1::Observed
        );
    }

    let mut absent_beta = source_snapshot.scan.clone().unwrap();
    absent_beta.beta_proxy = None;
    absent_beta.beta_proxy_status = CandidateEvaluationBetaProxyStatusV1::UnavailableBtcMove;
    let absent_beta_capture = capture_with_scan(Some(absent_beta));
    assert_eq!(
        absent_beta_capture.capture_status,
        CANDIDATE_EVALUATION_SOURCE_CAPTURE_COMPLETE_STATUS
    );
    assert!(validate_candidate_evaluation_source_snapshot(&absent_beta_capture, &event_context)
        .is_ok());

    let mut event_without_scan_id = event_context.clone();
    event_without_scan_id.scan_id = None;
    rehash_source_snapshot_event_context(&mut event_without_scan_id);
    let missing_bound_scan_id = capture_candidate_evaluation_source_snapshot(
        &event_without_scan_id,
        source_snapshot.scan.clone(),
        source_snapshot.decision_features.clone(),
        source_snapshot.portfolio.clone(),
    );
    assert_eq!(
        missing_bound_scan_id.capture_blockers,
        vec!["BOUND_SCAN_ID_MISSING"]
    );
    assert!(validate_candidate_evaluation_source_snapshot(
        &missing_bound_scan_id,
        &event_without_scan_id
    )
    .is_ok());

    assert_eq!(
        source_snapshot
            .decision_features
            .observations
            .iter()
            .map(|observation| observation.name.as_str())
            .collect::<Vec<_>>(),
        FEATURE_NAMES_V1
    );
    let expected_sources = [
        "indicator_snapshot.adx.adx",
        "indicator_snapshot.bollinger.bandwidth",
        "tick.atr_value+price_event.last_price",
        "price_event.funding_rate",
        "indicator_snapshot.ewma_vol.ewma_vol",
        "price_event.index_price+price_event.last_price",
        "price_event.bids5+price_event.asks5",
        "price_event.bid_price+price_event.ask_price",
        "order_intent.confluence_score",
        "order_intent.persistence_elapsed_ms",
        "order_intent.is_long",
        "order_intent.qty+price_event.last_price+paper_state.balance",
        "paper_state.positions.count",
        "paper_state.positions.same_direction_count",
        "price_event.ts_ms.utc_hour_sin",
        "price_event.ts_ms.utc_hour_cos",
        "price_event.ts_ms.funding_settlement_window",
    ];
    assert_eq!(
        source_snapshot
            .decision_features
            .observations
            .iter()
            .map(|observation| observation.source.as_str())
            .collect::<Vec<_>>(),
        expected_sources
    );
    let capture_with_features = |decision_features| {
        capture_candidate_evaluation_source_snapshot(
            &event_context,
            source_snapshot.scan.clone(),
            decision_features,
            source_snapshot.portfolio.clone(),
        )
    };
    let assert_feature_blocked = |snapshot: &CandidateEvaluationSourceSnapshotV1,
                                  expected: &[&str]| {
        assert_eq!(
            snapshot.capture_status,
            CANDIDATE_EVALUATION_SOURCE_CAPTURE_BLOCKED_STATUS
        );
        assert_eq!(
            snapshot.capture_blockers,
            expected
                .iter()
                .map(|blocker| (*blocker).to_string())
                .collect::<Vec<_>>()
        );
        assert!(validate_candidate_evaluation_source_snapshot(snapshot, &event_context).is_ok());
    };

    let mut wrong_feature_version = source_snapshot.decision_features.clone();
    wrong_feature_version.schema_version = "v2".to_string();
    assert_feature_blocked(
        &capture_with_features(wrong_feature_version),
        &["FEATURE_SCHEMA_VERSION_INVALID"],
    );

    let mut wrong_schema_hash = source_snapshot.decision_features.clone();
    wrong_schema_hash.schema_hash.push('0');
    assert_feature_blocked(
        &capture_with_features(wrong_schema_hash),
        &["FEATURE_SCHEMA_HASH_MISMATCH"],
    );

    let mut wrong_definition_hash = source_snapshot.decision_features.clone();
    wrong_definition_hash.definition_hash.push('0');
    assert_feature_blocked(
        &capture_with_features(wrong_definition_hash),
        &["FEATURE_DEFINITION_HASH_MISMATCH"],
    );

    let mut missing_observation = source_snapshot.decision_features.clone();
    missing_observation.observations.pop();
    assert_feature_blocked(
        &capture_with_features(missing_observation),
        &["FEATURE_OBSERVATION_COUNT_INVALID"],
    );

    let mut wrong_order = source_snapshot.decision_features.clone();
    wrong_order.observations.swap(0, 1);
    assert_feature_blocked(
        &capture_with_features(wrong_order),
        &[
            "FEATURE_OBSERVATION_ORDER_INVALID",
            "FEATURE_SOURCE_MISMATCH:adx_1h",
            "FEATURE_SOURCE_MISMATCH:bb_width_pct",
        ],
    );

    let mut wrong_name = source_snapshot.decision_features.clone();
    wrong_name.observations[0].name = "adx_renamed".to_string();
    assert_feature_blocked(
        &capture_with_features(wrong_name),
        &["FEATURE_OBSERVATION_ORDER_INVALID"],
    );

    let mut missing_presence = source_snapshot.decision_features.clone();
    missing_presence.observations[0].raw_present = false;
    let missing_presence_capture = capture_with_features(missing_presence);
    assert_feature_blocked(
        &missing_presence_capture,
        &["FEATURE_RAW_SOURCE_MISSING:adx_1h"],
    );
    let mut stale_presence_hash = missing_presence_capture;
    stale_presence_hash.decision_features.observations[0].raw_present = true;
    assert!(
        validate_candidate_evaluation_source_snapshot(&stale_presence_hash, &event_context)
            .is_err()
    );

    let mut missing_value = source_snapshot.decision_features.clone();
    missing_value.observations[0].value = None;
    assert_feature_blocked(
        &capture_with_features(missing_value),
        &["FEATURE_RAW_SOURCE_MISSING:adx_1h"],
    );

    let mut nonfinite_value = source_snapshot.decision_features.clone();
    nonfinite_value.observations[0].value = Some(f64::NEG_INFINITY);
    let normalized_feature = capture_with_features(nonfinite_value);
    assert_feature_blocked(
        &normalized_feature,
        &["FEATURE_RAW_SOURCE_MISSING:adx_1h"],
    );
    assert_eq!(
        normalized_feature.decision_features.observations[0].value,
        None
    );
    assert_eq!(normalized_feature.snapshot_hash.len(), 64);
    assert!(serde_json::to_string(&normalized_feature).is_ok());

    let mut value_when_missing = source_snapshot.decision_features.clone();
    value_when_missing.observations[0].raw_present = false;
    value_when_missing.observations[0].value = Some(30.0);
    let normalized_missing = capture_with_features(value_when_missing);
    assert_feature_blocked(
        &normalized_missing,
        &["FEATURE_RAW_SOURCE_MISSING:adx_1h"],
    );
    assert_eq!(
        normalized_missing.decision_features.observations[0].value,
        None
    );

    let mut out_of_range = source_snapshot.decision_features.clone();
    out_of_range.observations[0].value = Some(101.0);
    assert_feature_blocked(
        &capture_with_features(out_of_range),
        &["FEATURE_VALUE_OUT_OF_RANGE:adx_1h"],
    );

    let mut missing_source = source_snapshot.decision_features.clone();
    missing_source.observations[0].source = " ".to_string();
    assert_feature_blocked(
        &capture_with_features(missing_source),
        &["FEATURE_SOURCE_MISSING_OR_INVALID"],
    );

    let mut arbitrary_source = source_snapshot.decision_features.clone();
    arbitrary_source.observations[0].source = "arbitrary.nonempty".to_string();
    assert_feature_blocked(
        &capture_with_features(arbitrary_source),
        &["FEATURE_SOURCE_MISMATCH:adx_1h"],
    );

    let mut swapped_sources = source_snapshot.decision_features.clone();
    let first_source = swapped_sources.observations[0].source.clone();
    swapped_sources.observations[0].source = swapped_sources.observations[1].source.clone();
    swapped_sources.observations[1].source = first_source;
    assert_feature_blocked(
        &capture_with_features(swapped_sources),
        &[
            "FEATURE_SOURCE_MISMATCH:adx_1h",
            "FEATURE_SOURCE_MISMATCH:bb_width_pct",
        ],
    );

    let capture_with_portfolio = |portfolio| {
        capture_candidate_evaluation_source_snapshot(
            &event_context,
            source_snapshot.scan.clone(),
            source_snapshot.decision_features.clone(),
            portfolio,
        )
    };
    let assert_portfolio_blocked = |snapshot: &CandidateEvaluationSourceSnapshotV1,
                                    expected: &[&str]| {
        assert_eq!(
            snapshot.capture_status,
            CANDIDATE_EVALUATION_SOURCE_CAPTURE_BLOCKED_STATUS
        );
        assert_eq!(
            snapshot.capture_blockers,
            expected
                .iter()
                .map(|blocker| (*blocker).to_string())
                .collect::<Vec<_>>()
        );
        assert!(validate_candidate_evaluation_source_snapshot(snapshot, &event_context).is_ok());
    };

    let mut shuffled = source_snapshot.portfolio.clone();
    shuffled.positions.reverse();
    let canonicalized_shuffle = capture_with_portfolio(shuffled);
    assert_eq!(
        canonicalized_shuffle.portfolio.positions,
        source_snapshot.portfolio.positions
    );
    assert_eq!(canonicalized_shuffle.snapshot_hash, source_snapshot.snapshot_hash);

    let mut stale_position_order = source_snapshot.clone();
    stale_position_order.portfolio.positions.swap(0, 1);
    assert!(
        validate_candidate_evaluation_source_snapshot(&stale_position_order, &event_context)
            .is_err()
    );

    let mut duplicate_symbol = source_snapshot.portfolio.clone();
    duplicate_symbol.positions[1].symbol = "BTCUSDT".to_string();
    assert_portfolio_blocked(
        &capture_with_portfolio(duplicate_symbol),
        &["POSITION_SYMBOL_ORDER_OR_DUPLICATE_INVALID"],
    );

    let mut invalid_symbol = source_snapshot.portfolio.clone();
    invalid_symbol.positions[0].symbol = " btcusdt ".to_string();
    assert_portfolio_blocked(
        &capture_with_portfolio(invalid_symbol),
        &["POSITION_SYMBOL_MISSING_OR_INVALID"],
    );

    let mut invalid_side = source_snapshot.portfolio.clone();
    invalid_side.positions[0].side = "Buy".to_string();
    assert_portfolio_blocked(
        &capture_with_portfolio(invalid_side),
        &["POSITION_SIDE_INVALID"],
    );

    let mut nonfinite_quantity = source_snapshot.portfolio.clone();
    nonfinite_quantity.positions[0].quantity = Some(f64::NAN);
    let normalized_quantity = capture_with_portfolio(nonfinite_quantity);
    assert_portfolio_blocked(
        &normalized_quantity,
        &["POSITION_QUANTITY_MISSING_OR_INVALID"],
    );
    assert_eq!(normalized_quantity.portfolio.positions[0].quantity, None);
    assert_eq!(normalized_quantity.snapshot_hash.len(), 64);
    assert!(serde_json::to_string(&normalized_quantity).is_ok());

    let mut invalid_mark_source = source_snapshot.portfolio.clone();
    invalid_mark_source.positions[0].mark_source = "current_price".to_string();
    assert_portfolio_blocked(
        &capture_with_portfolio(invalid_mark_source),
        &["POSITION_MARK_SOURCE_INVALID"],
    );

    let mut missing_mark_price = source_snapshot.portfolio.clone();
    missing_mark_price.positions[0].mark_price = None;
    assert_portfolio_blocked(
        &capture_with_portfolio(missing_mark_price),
        &["POSITION_MARK_PRICE_MISSING_OR_INVALID"],
    );

    let mut mismatched_mark_notional = source_snapshot.portfolio.clone();
    mismatched_mark_notional.positions[0].mark_notional_usdt = Some(501.0);
    assert_portfolio_blocked(
        &capture_with_portfolio(mismatched_mark_notional),
        &["POSITION_MARK_NOTIONAL_RECONCILIATION_MISMATCH"],
    );

    let mut missing_owner = source_snapshot.portfolio.clone();
    missing_owner.positions[0].owner_strategy = " ".to_string();
    assert_portfolio_blocked(
        &capture_with_portfolio(missing_owner),
        &["POSITION_OWNER_STRATEGY_MISSING_OR_INVALID"],
    );

    let mut missing_entry_context = source_snapshot.portfolio.clone();
    missing_entry_context.positions[0].entry_context_id.clear();
    assert_portfolio_blocked(
        &capture_with_portfolio(missing_entry_context),
        &["POSITION_ENTRY_CONTEXT_ID_MISSING_OR_INVALID"],
    );

    let mut wrong_source_hash = source_snapshot.portfolio.clone();
    wrong_source_hash
        .portfolio_snapshot_hash
        .as_mut()
        .unwrap()
        .push('0');
    assert_portfolio_blocked(
        &capture_with_portfolio(wrong_source_hash),
        &["PORTFOLIO_SNAPSHOT_HASH_MISSING_OR_MISMATCH"],
    );

    let mut wrong_equity = source_snapshot.portfolio.clone();
    wrong_equity.accepted_demo_equity_usdt = Some(10_001.0);
    assert_portfolio_blocked(
        &capture_with_portfolio(wrong_equity),
        &["PORTFOLIO_EQUITY_MISMATCH"],
    );

    let mut wrong_count = source_snapshot.portfolio.clone();
    wrong_count.position_count = Some(3);
    assert_portfolio_blocked(
        &capture_with_portfolio(wrong_count),
        &["PORTFOLIO_POSITION_COUNT_MISSING_OR_MISMATCH"],
    );

    let mut wrong_gross = source_snapshot.portfolio.clone();
    wrong_gross.gross_mark_notional_usdt = Some(2_001.0);
    assert_portfolio_blocked(
        &capture_with_portfolio(wrong_gross),
        &["PORTFOLIO_GROSS_MARK_NOTIONAL_MISSING_OR_MISMATCH"],
    );

    let mut wrong_net = source_snapshot.portfolio.clone();
    wrong_net.net_mark_notional_usdt = Some(-999.0);
    assert_portfolio_blocked(
        &capture_with_portfolio(wrong_net),
        &["PORTFOLIO_NET_MARK_NOTIONAL_MISSING_OR_MISMATCH"],
    );

    let mut invalid_bound_hash_context = event_context.clone();
    invalid_bound_hash_context
        .portfolio_snapshot_hash
        .as_mut()
        .unwrap()
        .push('0');
    rehash_source_snapshot_event_hash(&mut invalid_bound_hash_context);
    let invalid_bound_hash_capture = capture_candidate_evaluation_source_snapshot(
        &invalid_bound_hash_context,
        source_snapshot.scan.clone(),
        source_snapshot.decision_features.clone(),
        source_snapshot.portfolio.clone(),
    );
    assert!(invalid_bound_hash_capture
        .capture_blockers
        .contains(&"BOUND_PORTFOLIO_SNAPSHOT_HASH_INVALID".to_string()));

    let mut empty_context = event_context.clone();
    let empty_bound = empty_context.portfolio_snapshot.as_mut().unwrap();
    empty_bound.position_count = 0;
    empty_bound.gross_mark_notional_usdt = 0.0;
    empty_bound.net_mark_notional_usdt = 0.0;
    rehash_source_snapshot_event_context(&mut empty_context);
    let empty_portfolio = CandidateEvaluationPortfolioSourceV1 {
        portfolio_snapshot_hash: empty_context.portfolio_snapshot_hash.clone(),
        accepted_demo_equity_usdt: empty_context
            .portfolio_snapshot
            .as_ref()
            .and_then(|portfolio| portfolio.accepted_demo_equity_usdt),
        positions: Vec::new(),
        position_count: Some(0),
        gross_mark_notional_usdt: Some(0.0),
        net_mark_notional_usdt: Some(0.0),
        empty_position_attestation: true,
    };
    let empty_capture = capture_candidate_evaluation_source_snapshot(
        &empty_context,
        source_snapshot.scan.clone(),
        source_snapshot.decision_features.clone(),
        empty_portfolio.clone(),
    );
    assert_eq!(
        empty_capture.capture_status,
        CANDIDATE_EVALUATION_SOURCE_CAPTURE_COMPLETE_STATUS
    );
    assert!(validate_candidate_evaluation_source_snapshot(&empty_capture, &empty_context).is_ok());

    let mut false_empty_attestation = empty_portfolio;
    false_empty_attestation.empty_position_attestation = false;
    let invalid_empty_capture = capture_candidate_evaluation_source_snapshot(
        &empty_context,
        source_snapshot.scan.clone(),
        source_snapshot.decision_features.clone(),
        false_empty_attestation,
    );
    assert_eq!(
        invalid_empty_capture.capture_blockers,
        vec!["EMPTY_POSITION_ATTESTATION_INVALID"]
    );

    let mut false_nonempty_attestation = source_snapshot.portfolio.clone();
    false_nonempty_attestation.empty_position_attestation = true;
    assert_portfolio_blocked(
        &capture_with_portfolio(false_nonempty_attestation),
        &["EMPTY_POSITION_ATTESTATION_INVALID"],
    );
    let serialized_snapshot = serde_json::to_string(&source_snapshot).unwrap();
    let source_symbol = &event_context.symbol;
    let source_side = &event_context.side;
    let source_ts_ms = event_context.captured_at_ms;
    let row_with_source_snapshot = format!(
        r#"{{"record_type":"probe_admission_decision","event":{{"strategy_name":"ma_crossover","symbol":"{source_symbol}","side":"{source_side}","ts_ms":{source_ts_ms},"candidate_evaluation_source_snapshot":{serialized_snapshot}}}}}"#
    );
    let parsed = LedgerRecord::from_jsonl_str(&row_with_source_snapshot).unwrap();
    let retained = parsed[0]
        .event
        .as_ref()
        .and_then(|event| event.candidate_evaluation_source_snapshot.as_ref())
        .expect("typed source snapshot sibling remains present");
    assert_eq!(
        retained, &source_snapshot,
        "retained-ledger public parsing must preserve a present typed source snapshot sibling",
    );
    assert_eq!(serde_json::to_string(retained).unwrap(), serialized_snapshot);

    let snapshot_admission = build_admission_ledger_record(&decision, &event, generated_at)
        .with_candidate_evaluation_source_snapshot(Some(source_snapshot.clone()));
    let admission_json = snapshot_admission.to_json_string().unwrap();
    assert_eq!(admission_json.lines().count(), 1);
    let admission_rows = LedgerRecord::from_jsonl_str(&admission_json).unwrap();
    assert_eq!(admission_rows.len(), 1);
    assert_eq!(
        admission_rows[0]
            .event
            .as_ref()
            .and_then(|event| event.candidate_evaluation_source_snapshot.as_ref()),
        Some(&source_snapshot)
    );

    let snapshot_capture_error = build_capture_error_ledger_record(
        &event,
        generated_at,
        "NORMAL",
        "transport fixture capture error",
    )
    .with_candidate_evaluation_source_snapshot(Some(source_snapshot.clone()));
    let capture_error_json = snapshot_capture_error.to_json_string().unwrap();
    assert_eq!(capture_error_json.lines().count(), 1);
    let capture_error_rows = LedgerRecord::from_jsonl_str(&capture_error_json).unwrap();
    assert_eq!(capture_error_rows.len(), 1);
    assert_eq!(
        capture_error_rows[0]
            .event
            .as_ref()
            .and_then(|event| event.candidate_evaluation_source_snapshot.as_ref()),
        Some(&source_snapshot)
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
