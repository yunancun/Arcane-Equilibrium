use super::*;
use serde_json::json;

fn complete_scanner_inputs() -> CandidateScannerInputsV1 {
    CandidateScannerInputsV1 {
        authority_mode: "advisory".to_string(),
        legacy_would_block: false,
        legacy_block_reason: None,
        scan_id: "scan-20260710-001".to_string(),
        best_strategy: "ma_crossover".to_string(),
        intent_strategy: "ma_crossover".to_string(),
        market_regime: "range".to_string(),
        trend_phase: "neutral".to_string(),
        trend_score: 0.1,
        range_score: 0.8,
        shock_score: 0.0,
        close_alignment: 0.5,
        range_position: 0.4,
        crowding_score: 0.2,
        reversal_risk_score: 0.1,
        directional_efficiency: 0.3,
        dir_pct: 0.2,
        signed_dir_pct: -0.2,
        range_pct: 0.6,
        fr_bps: 0.4,
        f_ma: 61.0,
        f_grid: 40.0,
        f_bbrv: 55.0,
        f_bkout: 12.0,
        f_funding_arb: 8.0,
        edge_bps: Some(-2.5),
        edge_n: 17,
        edge_status: "observed".to_string(),
        route_mode: "advisory".to_string(),
        market_status: "compatible".to_string(),
        route_reason: "scanner_candidate".to_string(),
        opportunity: None,
        final_score: 58.0,
        raw_score: 62.0,
    }
}

fn complete_input() -> CandidateEventCaptureInput {
    CandidateEventCaptureInput {
        captured_at_ms: 1_783_700_000_000,
        strategy_name: "ma_crossover".to_string(),
        runtime_strategy_name: "ma_crossover".to_string(),
        build_git_sha: "0123456789abcdef0123456789abcdef01234567".to_string(),
        strategy_params_json: r#"{"slow":20,"fast":5}"#.to_string(),
        conf_scale: 1.0,
        symbol: "ETHUSDT".to_string(),
        side: "Sell".to_string(),
        horizon_env_value: None,
        evidence_engine_mode: "live_demo".to_string(),
        pipeline_kind: "live".to_string(),
        endpoint_environment: Some("live_demo".to_string()),
        context_id: Some("ctx-live_demo-ETHUSDT-1783700000000".to_string()),
        signal_id: Some("sig-live_demo-ma_crossover-ETHUSDT-1783700000000".to_string()),
        scanner_inputs: Some(complete_scanner_inputs()),
        market_inputs: CandidateMarketInputsV1 {
            observed_at_ms: 1_783_700_000_000,
            last_price: Some(2_500.0),
            best_bid: Some(2_499.9),
            best_ask: Some(2_500.1),
            tick_size: Some(0.1),
            index_price: Some(2_499.8),
            funding_rate: Some(0.0001),
            open_interest: Some(1_000_000.0),
            atr_value: Some(25.0),
        },
        risk_state: "NORMAL".to_string(),
        governance_profile: "Validation".to_string(),
        risk_config: Some(json!({"limits": {"leverage_max": 2.0}})),
        portfolio_snapshot_ref: Some(
            "paper_state:live_demo:ctx-live_demo-ETHUSDT-1783700000000:1783700000000".to_string(),
        ),
        portfolio_snapshot: Some(CandidatePortfolioSnapshotV1 {
            schema_version: CANDIDATE_PORTFOLIO_SNAPSHOT_SCHEMA_VERSION.to_string(),
            captured_at_ms: 1_783_700_000_000,
            balance: 10_000.0,
            accepted_demo_equity_usdt: Some(10_000.0),
            peak_balance: 10_000.0,
            drawdown_pct: 0.0,
            position_count: 0,
            gross_mark_notional_usdt: 0.0,
            net_mark_notional_usdt: 0.0,
            total_realized_pnl: 0.0,
            total_fees: 0.0,
            total_funding_pnl: 0.0,
            trade_count: 0,
        }),
    }
}

#[test]
fn canonical_json_recursively_sorts_compact_utf8_and_hashes_exact_bytes() {
    let value = json!({"z": 1.25, "a": [{"b": 2, "a": "é"}]});
    let canonical = canonical_json(&value);
    assert_eq!(canonical, r#"{"a":[{"a":"é","b":2}],"z":1.25}"#);
    assert_eq!(
        canonical_sha256(&value),
        "e8c43da6bb3b73ebf733a97ee59637bd35e7727d87326f4395827c5e2f1660c3"
    );
}

#[test]
fn shared_cross_language_fixture_matches_canonical_bytes_and_hash() {
    let fixture: serde_json::Value = serde_json::from_str(include_str!(
        "../tests/fixtures/candidate_event_context_v1/canonical_fixture.json"
    ))
    .expect("shared canonical fixture parses");
    let input = &fixture["input"];

    assert_eq!(
        canonical_json(input),
        fixture["expected_canonical_json"]
            .as_str()
            .expect("canonical fixture string")
    );
    assert_eq!(
        canonical_sha256(input),
        fixture["expected_sha256"]
            .as_str()
            .expect("canonical fixture hash")
    );
}

#[test]
fn complete_capture_is_typed_hashed_and_authority_free() {
    let input = complete_input();
    let first = capture_candidate_event_context(input.clone());
    let second = capture_candidate_event_context(input);
    assert_eq!(first, second);
    assert_eq!(first.schema_version, CANDIDATE_EVENT_CONTEXT_SCHEMA_VERSION);
    assert_eq!(first.capture_status, CAPTURE_COMPLETE_STATUS);
    assert!(first.capture_blockers.is_empty());
    assert_eq!(first.strategy_version, first.build_git_sha);
    assert_eq!(first.strategy_params_json, r#"{"slow":20,"fast":5}"#);
    assert_eq!(
        first.strategy_params_canonical_json.as_deref(),
        Some(r#"{"fast":5,"slow":20}"#)
    );
    assert_eq!(first.horizon_policy.outcome_horizon_minutes, Some(60));
    assert!(first.horizon_policy.default_applied);
    assert_eq!(first.venue, "bybit");
    assert_eq!(first.product, "linear_perpetual");
    assert_eq!(first.boundary, CANDIDATE_EVENT_CONTEXT_BOUNDARY);
    let mut without_hash = serde_json::to_value(&first).expect("context serializes");
    without_hash
        .as_object_mut()
        .expect("context is object")
        .remove("event_hash");
    assert_eq!(first.event_hash, canonical_sha256(&without_hash));
}

#[test]
fn incomplete_capture_is_durable_blocked_without_backfill_or_panic() {
    let mut input = complete_input();
    input.build_git_sha = "unknown".to_string();
    input.captured_at_ms = 0;
    input.runtime_strategy_name = "grid_trading".to_string();
    input.symbol = " ".to_string();
    input.side = "sell".to_string();
    input.strategy_params_json = "[]".to_string();
    input.conf_scale = f64::NAN;
    input.horizon_env_value = Some("invalid".to_string());
    input.context_id = Some(" padded-context ".to_string());
    input.signal_id = Some(" ".to_string());
    input.scanner_inputs = None;
    input.endpoint_environment = None;
    input.market_inputs.best_bid = None;
    input.portfolio_snapshot_ref = None;
    input.portfolio_snapshot = None;
    input.risk_state.clear();
    input.governance_profile = "Production".to_string();
    input.risk_config = None;
    let captured = capture_candidate_event_context(input);
    assert_eq!(captured.capture_status, CAPTURE_BLOCKED_STATUS);
    assert_eq!(
        captured.capture_blockers,
        vec![
            "BUILD_GIT_SHA_UNKNOWN_OR_INVALID",
            "CAPTURE_TIMESTAMP_INVALID",
            "STRATEGY_NAME_MISMATCH",
            "SYMBOL_MISSING_OR_INVALID",
            "SIDE_MISSING_OR_INVALID",
            "STRATEGY_PARAMS_JSON_INVALID_OR_NOT_OBJECT",
            "CONF_SCALE_INVALID",
            "HORIZON_POLICY_INVALID",
            "CONTEXT_ID_MISSING",
            "SIGNAL_ID_MISSING",
            "SCAN_CONTEXT_MISSING_OR_INVALID",
            "ENDPOINT_BINDING_MISSING_OR_INCOMPATIBLE",
            "BBO_MISSING_OR_INVALID",
            "PORTFOLIO_SNAPSHOT_INVALID",
            "ACCEPTED_DEMO_EQUITY_MISSING_OR_INVALID",
            "RISK_CONTEXT_INVALID",
            "RISK_CONFIG_HASH_UNCOMPUTABLE",
        ]
    );
    assert_eq!(captured.strategy_version, "unknown");
    assert!(captured.strategy_params_canonical_json.is_none());
    assert!(captured.strategy_config_hash.is_none());
    assert!(captured.conf_scale.is_none());
    assert!(captured.horizon_policy.outcome_horizon_minutes.is_none());
    assert!(!captured.horizon_policy.default_applied);
    assert!(captured.context_id.is_none());
    assert!(captured.signal_id.is_none());
    assert!(captured.scan_id.is_none());
    assert!(captured.portfolio_snapshot.is_none());
    assert!(captured.portfolio_snapshot_hash.is_none());
    assert_eq!(captured.event_hash.len(), 64);
}

#[test]
fn crossed_bbo_is_blocked_without_rewriting_observed_prices() {
    let mut input = complete_input();
    input.market_inputs.best_bid = Some(2_500.1);
    input.market_inputs.best_ask = Some(2_500.1);

    let captured = capture_candidate_event_context(input);

    assert_eq!(captured.capture_status, CAPTURE_BLOCKED_STATUS);
    assert_eq!(captured.capture_blockers, vec!["BBO_CROSSED"]);
    assert_eq!(captured.market_inputs.best_bid, Some(2_500.1));
    assert_eq!(captured.market_inputs.best_ask, Some(2_500.1));
    assert_eq!(captured.event_hash.len(), 64);
}

#[test]
fn nonfinite_scanner_market_and_portfolio_values_never_reach_hash_serialization() {
    let mut input = complete_input();
    input
        .scanner_inputs
        .as_mut()
        .expect("scanner fixture")
        .trend_score = f64::INFINITY;
    input.market_inputs.index_price = Some(f64::NAN);
    input.market_inputs.funding_rate = Some(f64::INFINITY);
    input.market_inputs.open_interest = Some(f64::NEG_INFINITY);
    input.market_inputs.atr_value = Some(f64::NAN);
    input
        .portfolio_snapshot
        .as_mut()
        .expect("portfolio fixture")
        .gross_mark_notional_usdt = f64::NAN;

    let captured = capture_candidate_event_context(input);

    assert_eq!(captured.capture_status, CAPTURE_BLOCKED_STATUS);
    assert!(captured
        .capture_blockers
        .contains(&"SCAN_CONTEXT_MISSING_OR_INVALID".to_string()));
    assert!(captured
        .capture_blockers
        .contains(&"PORTFOLIO_SNAPSHOT_INVALID".to_string()));
    assert!(captured.scanner_inputs.is_none());
    assert!(captured.portfolio_snapshot.is_none());
    assert!(captured.market_inputs.index_price.is_none());
    assert!(captured.market_inputs.funding_rate.is_none());
    assert!(captured.market_inputs.open_interest.is_none());
    assert!(captured.market_inputs.atr_value.is_none());
    assert_eq!(captured.event_hash.len(), 64);
}

#[test]
fn reduced_risk_state_from_runtime_enum_remains_capture_complete() {
    let mut input = complete_input();
    input.risk_state = "REDUCED".to_string();

    let captured = capture_candidate_event_context(input);

    assert_eq!(captured.capture_status, CAPTURE_COMPLETE_STATUS);
    assert!(captured.capture_blockers.is_empty());
}

#[test]
fn scanner_intent_strategy_must_match_top_level_strategy_identity() {
    let mut input = complete_input();
    let scanner = input.scanner_inputs.as_mut().expect("scanner fixture");
    scanner.intent_strategy = "grid_trading".to_string();
    scanner.best_strategy = "bb_reversion".to_string();

    let captured = capture_candidate_event_context(input);

    assert_eq!(captured.capture_status, CAPTURE_BLOCKED_STATUS);
    assert_eq!(
        captured.capture_blockers,
        vec!["SCAN_CONTEXT_MISSING_OR_INVALID"]
    );
    assert!(captured.scanner_inputs.is_none());
}
