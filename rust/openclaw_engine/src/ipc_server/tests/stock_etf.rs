//! ADR-0048 Stock/ETF IPC fixture tests.

use super::super::*;
use super::{
    empty_account_manager_slot, empty_budget_slot, empty_cost_edge_advisor_slot,
    empty_h_state_cache_slot, empty_teacher_slot, make_test_config, make_test_data_dir,
};

#[tokio::test]
async fn stock_etf_submit_denies_without_paper_channel_or_ibkr_call() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.submit_paper_order","params":{"symbol":"SPY","instrument_kind":"etf"},"id":4801}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(
        resp.error.is_none(),
        "stock_etf fixture must not require paper channel"
    );
    let result = resp.result.expect("stock_etf result");
    assert_eq!(result["method"], "stock_etf.submit_paper_order");
    assert_eq!(result["allowed"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(
        result["phase2"]["external_surface_gate"]["ibkr_contact_allowed"],
        false
    );
}

#[tokio::test]
async fn legacy_submit_paper_order_still_uses_existing_channel_path() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"submit_paper_order","params":{"symbol":"BTCUSDT","side":"Buy","qty":0.01},"id":4802}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    let err = resp
        .error
        .expect("legacy paper route should still need channel");
    assert!(
        err.message.contains("paper command channel not configured"),
        "unexpected legacy route error: {}",
        err.message
    );
}

#[tokio::test]
async fn stock_etf_live_environment_is_typed_denial() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.preview_paper_order","params":{"environment":"live","instrument_kind":"stock"},"id":4803}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf result");
    assert_eq!(result["allowed"], false);
    assert_eq!(result["denial_reason"], "live_reserved_denied");
    assert_eq!(result["ibkr_call_performed"], false);
}

#[tokio::test]
async fn stock_etf_readiness_exposes_phase2_precontact_blockers_without_ibkr_contact() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_readiness","params":{},"id":4804}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf readiness result");
    assert_eq!(result["phase"], "phase2_precontact_source_fixture");
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let phase2 = &result["phase2"];
    assert_eq!(phase2["immutable_pass_artifact_present"], false);
    assert_eq!(phase2["first_ibkr_contact_allowed"], false);
    assert_eq!(phase2["connector_enabled"], false);
    assert_eq!(phase2["external_surface_gate"]["status"], "BLOCKED");
    assert_eq!(
        phase2["external_surface_gate"]["ibkr_contact_allowed"],
        false
    );
    assert!(json_array_contains(
        &phase2["external_surface_gate"]["blockers"],
        "status_not_pass"
    ));
    assert!(json_array_contains(
        &phase2["external_surface_gate"]["blockers"],
        "secret_contract_missing"
    ));
    assert_eq!(
        phase2["api_allowlist"]["contract_id"],
        "non_bybit_api_allowlist_v1"
    );
    assert_eq!(phase2["api_allowlist"]["source_version"], 1);
    assert_eq!(phase2["api_allowlist"]["accepted"], true);
    assert_eq!(phase2["api_allowlist"]["read_action_count"], 10);
    assert_eq!(phase2["api_allowlist"]["paper_write_action_count"], 3);
    assert_eq!(phase2["api_allowlist"]["denied_action_count"], 10);
    assert_eq!(phase2["api_allowlist"]["ibkr_contact_performed"], false);
    assert_eq!(phase2["api_allowlist"]["secret_content_serialized"], false);
    assert_eq!(
        phase2["api_allowlist"]["bybit_live_execution_protected"],
        true
    );
    assert_eq!(phase2["policy_prerequisites"]["bundle_accepted"], true);
    assert_eq!(
        phase2["policy_prerequisites"]["flags"]["redaction_suite_passed"],
        true
    );
    assert_eq!(
        phase2["policy_prerequisites"]["flags"]["python_no_write_guard_present"],
        true
    );
}

#[tokio::test]
async fn stock_etf_lane_status_exposes_flags_without_ibkr_contact() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_lane_status","params":{},"id":4805}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf lane status result");
    assert_eq!(result["phase"], "phase2_precontact_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(
        result["default_asset_lane"],
        result["flags"]["asset_lane_default"]
    );
    assert_eq!(result["ibkr_live_enabled"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert!(result["flags"]["stock_etf_lane_enabled"].is_boolean());
    assert!(result["flags"]["ibkr_readonly_enabled"].is_boolean());
    assert!(result["flags"]["ibkr_paper_enabled"].is_boolean());
    assert!(result["flags"]["stock_etf_shadow_only"].is_boolean());

    let phase2 = &result["phase2"];
    assert_eq!(phase2["immutable_pass_artifact_present"], false);
    assert_eq!(phase2["first_ibkr_contact_allowed"], false);
    assert_eq!(phase2["connector_enabled"], false);
    assert_eq!(phase2["external_surface_gate"]["status"], "BLOCKED");
    assert_eq!(
        phase2["external_surface_gate"]["ibkr_contact_allowed"],
        false
    );
    assert!(json_array_contains(
        &phase2["external_surface_gate"]["blockers"],
        "status_not_pass"
    ));
    assert_eq!(
        phase2["api_allowlist"]["contract_id"],
        "non_bybit_api_allowlist_v1"
    );
    assert_eq!(phase2["api_allowlist"]["source_version"], 1);
    assert_eq!(phase2["api_allowlist"]["ibkr_contact_performed"], false);
    assert_eq!(phase2["api_allowlist"]["secret_content_serialized"], false);
    assert_eq!(
        phase2["api_allowlist"]["bybit_live_execution_protected"],
        true
    );
}

#[tokio::test]
async fn stock_etf_evidence_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_evidence_status","params":{},"id":4806}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf evidence status result");
    assert_eq!(result["phase"], "phase3_evidence_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["evidence_status_state"], "blocked");
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let market_data = &result["market_data_provenance"];
    assert_eq!(
        market_data["expected_contract_id"],
        "stock_market_data_provenance_v1"
    );
    assert_eq!(market_data["contract_id"], "");
    assert_eq!(market_data["source_version"], 0);
    assert_eq!(market_data["accepted"], false);
    assert!(json_array_contains(
        &market_data["blockers"],
        "market_data_provenance_contract_id_mismatch"
    ));
    assert_eq!(market_data["ibkr_contact_performed"], false);
    assert_eq!(market_data["connector_runtime_started"], false);
    assert_eq!(market_data["secret_content_serialized"], false);
    assert_eq!(market_data["live_or_tiny_live_authorized"], false);

    let evidence_clock = &result["evidence_clock"];
    assert_eq!(
        evidence_clock["expected_contract_id"],
        "stock_etf_evidence_clock_v1"
    );
    assert_eq!(evidence_clock["contract_id"], "");
    assert_eq!(evidence_clock["source_version"], 0);
    assert_eq!(evidence_clock["status"], "NOT_STARTED");
    assert_eq!(evidence_clock["accepted"], false);
    assert!(json_array_contains(
        &evidence_clock["blockers"],
        "evidence_clock_contract_id_mismatch"
    ));
    assert_eq!(evidence_clock["checker_contacted_ibkr"], false);
    assert_eq!(evidence_clock["checker_started_connector_runtime"], false);
    assert_eq!(evidence_clock["checker_started_evidence_clock"], false);
    assert_eq!(evidence_clock["checker_wrote_scorecard"], false);
    assert_eq!(evidence_clock["checker_applied_db"], false);
    assert_eq!(evidence_clock["secret_content_serialized"], false);
    assert_eq!(evidence_clock["live_or_tiny_live_authorized"], false);
    assert_eq!(
        evidence_clock["ibkr_readonly_paper_connector_green_5d"],
        false
    );
    assert_eq!(evidence_clock["shadow_collector_green_5d"], false);

    let frozen_inputs = &result["frozen_inputs"];
    assert_eq!(frozen_inputs["accepted"], false);
    assert_eq!(frozen_inputs["universe_hash_present"], false);
    assert_eq!(frozen_inputs["gui_evidence_view_available"], false);
    assert_eq!(frozen_inputs["daily_scorecard_regeneration_passed"], false);

    let dq_manifest = &result["dq_manifest"];
    assert_eq!(dq_manifest["shape_accepted"], false);
    assert_eq!(dq_manifest["passes_day_quality"], false);
    assert_eq!(dq_manifest["calendar_aware_coverage_bps"], 0);
    assert_eq!(dq_manifest["symbol_completeness_bps"], 0);
    assert_eq!(dq_manifest["latency_dq_passed"], false);
    assert_eq!(dq_manifest["market_data_provenance_accepted"], false);
    assert_eq!(dq_manifest["scorecard_regeneration_passed"], false);

    let scorecard = &result["scorecard"];
    assert_eq!(scorecard["writer_started"], false);
    assert_eq!(scorecard["db_apply_performed"], false);
    assert_eq!(scorecard["daily_scorecard_regeneration_passed"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_universe_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_universe_status","params":{},"id":4807}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf universe status result");
    assert_eq!(result["phase"], "phase3_universe_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["universe_status_state"], "blocked");
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["collector_started"], false);
    assert_eq!(result["market_data_ingestion_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let universe = &result["universe"];
    assert_eq!(
        universe["expected_contract_id"],
        "stock_etf_pit_universe_contract_v1"
    );
    assert_eq!(universe["contract_id"], "");
    assert_eq!(universe["source_version"], 0);
    assert_eq!(universe["accepted"], false);
    assert!(json_array_contains(
        &universe["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &universe["blockers"],
        "source_version_mismatch"
    ));
    assert_eq!(universe["universe_hash_present"], false);
    assert_eq!(universe["constituent_count"], 0);
    assert_eq!(universe["sample_constituents"].as_array().unwrap().len(), 0);
    assert_eq!(universe["frozen_for_evidence_clock"], false);
    assert_eq!(universe["survivorship_bias_controls_present"], false);
    assert_eq!(universe["bybit_live_execution_unchanged"], true);
    assert_eq!(universe["ibkr_live_denied"], true);
    assert_eq!(universe["ibkr_contact_performed"], false);
    assert_eq!(universe["secret_content_serialized"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_shadow_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_shadow_status","params":{},"id":4808}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf shadow status result");
    assert_eq!(result["phase"], "phase3_shadow_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "shadow");
    assert_eq!(result["shadow_status_state"], "blocked");
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["shadow_collector_started"], false);
    assert_eq!(result["shadow_signal_emitted"], false);
    assert_eq!(result["shadow_fill_generated"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let shadow = &result["shadow_fill_model"];
    assert_eq!(shadow["expected_contract_id"], "stock_shadow_fill_model_v1");
    assert_eq!(shadow["contract_id"], "");
    assert_eq!(shadow["source_version"], 0);
    assert_eq!(shadow["accepted"], false);
    assert!(json_array_contains(
        &shadow["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &shadow["blockers"],
        "source_version_mismatch"
    ));
    assert!(json_array_contains(
        &shadow["blockers"],
        "signal_id_missing"
    ));
    assert_eq!(shadow["synthetic_shadow"], false);
    assert_eq!(shadow["broker_paper_fill_linked"], false);
    assert_eq!(shadow["live_fill_linked"], false);

    let strategy = &result["strategy_hypothesis"];
    assert_eq!(
        strategy["expected_contract_id"],
        "stock_etf_strategy_hypothesis_contract_v1"
    );
    assert_eq!(strategy["contract_id"], "");
    assert_eq!(strategy["source_version"], 0);
    assert_eq!(strategy["accepted"], false);
    assert!(json_array_contains(
        &strategy["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &strategy["blockers"],
        "source_version_mismatch"
    ));
    assert_eq!(strategy["paper_shadow_only"], true);
    assert_eq!(strategy["profitability_claimed"], false);
    assert_eq!(strategy["live_or_tiny_live_authority_claimed"], false);
    assert_eq!(strategy["bybit_live_execution_unchanged"], true);
    assert_eq!(strategy["ibkr_live_denied"], true);
    assert_eq!(strategy["ibkr_contact_performed"], false);
    assert_eq!(strategy["secret_content_serialized"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_paper_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_paper_status","params":{},"id":4809}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf paper status result");
    assert_eq!(result["phase"], "phase2_paper_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["paper_status_state"], "blocked");
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["paper_lifecycle_started"], false);
    assert_eq!(result["paper_order_submitted"], false);
    assert_eq!(result["paper_fill_imported"], false);
    assert_eq!(result["paper_reconciliation_started"], false);
    assert_eq!(result["paper_account_snapshot_present"], false);
    assert_eq!(result["broker_paper_attestation_present"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["db_apply_performed"], false);

    let lifecycle = &result["lifecycle_event"];
    assert_eq!(
        lifecycle["expected_lifecycle_contract_id"],
        "ibkr_paper_order_lifecycle_v1"
    );
    assert_eq!(lifecycle["lifecycle_contract_id"], "");
    assert_eq!(
        lifecycle["expected_event_log_contract_id"],
        "broker_lifecycle_event_log_v1"
    );
    assert_eq!(lifecycle["event_log_contract_id"], "");
    assert_eq!(lifecycle["source_version"], 0);
    assert_eq!(lifecycle["accepted"], false);
    assert!(json_array_contains(
        &lifecycle["blockers"],
        "lifecycle_contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &lifecycle["blockers"],
        "event_log_contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &lifecycle["blockers"],
        "source_version_mismatch"
    ));
    assert_eq!(lifecycle["operation"], "paper_order_submit");
    assert_eq!(lifecycle["previous_state"], "LOCAL_INTENT_CREATED");
    assert_eq!(lifecycle["next_state"], "LOCAL_INTENT_CREATED");
    assert_eq!(lifecycle["allowed"], false);
    assert_eq!(lifecycle["event_id_present"], false);
    assert_eq!(lifecycle["order_local_id_present"], false);
    assert_eq!(lifecycle["idempotency_key_present"], false);
    assert_eq!(lifecycle["broker_order_id_present"], false);
    assert_eq!(lifecycle["execution_id_present"], false);
    assert_eq!(lifecycle["commission_report_id_present"], false);
    assert_eq!(lifecycle["reconciliation_run_id_present"], false);
    assert_eq!(lifecycle["raw_artifact_hash_present"], false);
    assert_eq!(lifecycle["redacted_summary_hash_present"], false);

    let reconstructability = &result["reconstructability"];
    assert_eq!(reconstructability["append_only_event_ready"], false);
    assert_eq!(reconstructability["broker_order_id_present"], false);
    assert_eq!(reconstructability["execution_id_present"], false);
    assert_eq!(reconstructability["commission_report_id_present"], false);
    assert_eq!(reconstructability["raw_artifact_hash_present"], false);
    assert_eq!(reconstructability["redacted_summary_hash_present"], false);
    assert_eq!(reconstructability["restart_recovery_required"], false);
    assert_eq!(reconstructability["manual_review_required"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_account_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_account_status","params":{},"id":4811}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf account status result");
    assert_eq!(result["phase"], "phase2_account_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_readonly");
    assert_eq!(result["account_status_state"], "blocked");
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["readonly_account_snapshot_started"], false);
    assert_eq!(result["paper_account_snapshot_started"], false);
    assert_eq!(result["account_snapshot_present"], false);
    assert_eq!(result["portfolio_positions_snapshot_present"], false);
    assert_eq!(result["cash_ledger_present"], false);
    assert_eq!(result["paper_account_attestation_present"], false);
    assert_eq!(result["session_attestation_present"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["gateway_socket_open"], false);
    assert_eq!(result["ibkr_live_enabled"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["db_apply_performed"], false);

    let account = &result["account_snapshot"];
    assert_eq!(
        account["expected_contract_id"],
        "broker_account_portfolio_cash_ledger_v1"
    );
    assert_eq!(account["contract_id"], "");
    assert_eq!(account["source_version"], 0);
    assert_eq!(account["accepted"], false);
    assert!(json_array_contains(
        &account["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &account["blockers"],
        "source_version_mismatch"
    ));
    assert!(json_array_contains(
        &account["blockers"],
        "wrong_asset_lane"
    ));
    assert_eq!(account["account_fingerprint_hash_present"], false);
    assert_eq!(account["account_snapshot_hash_present"], false);
    assert_eq!(account["portfolio_positions_hash_present"], false);
    assert_eq!(account["currency"], "");
    assert_eq!(account["cash_balance_minor_units"], 0);
    assert_eq!(account["buying_power_minor_units"], 0);
    assert_eq!(account["as_of_ms"], 0);
    assert_eq!(account["source_report_hash_present"], false);

    let session = &result["session_attestation"];
    assert_eq!(
        session["expected_contract_id"],
        "ibkr_session_attestation_v1"
    );
    assert_eq!(session["contract_id"], "");
    assert_eq!(session["source_version"], 0);
    assert_eq!(session["status"], "BLOCKED");
    assert_eq!(session["accepted"], false);
    assert!(json_array_contains(
        &session["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &session["blockers"],
        "source_version_mismatch"
    ));
    assert!(json_array_contains(&session["blockers"], "status_blocked"));
    assert_eq!(session["account_fingerprint_present"], false);
    assert_eq!(session["account_fingerprint_is_live"], false);
    assert_eq!(session["environment"], "read_only");
    assert_eq!(session["host"], "");
    assert_eq!(session["port"], 0);
    assert_eq!(session["process_identity_present"], false);
    assert_eq!(session["gateway_mode"], "unknown");
    assert_eq!(session["secret_slot_fingerprint_present"], false);
    assert_eq!(session["secret_slot_mode"], "unknown");
    assert_eq!(session["secret_world_readable"], false);
    assert_eq!(session["live_secret_absent_or_empty"], false);
    assert_eq!(session["env_var_credential_fallback_used"], false);
    assert_eq!(session["api_server_version_present"], false);
    assert_eq!(session["attested_at_ms"], 0);
    assert_eq!(session["expires_at_ms"], 0);
    assert_eq!(session["raw_artifact_hash_present"], false);

    let paper_policy = &result["paper_attestation_policy"];
    assert_eq!(
        paper_policy["expected_contract_id"],
        "ibkr_paper_attestation_v1"
    );
    assert_eq!(paper_policy["contract_id"], "ibkr_paper_attestation_v1");
    assert_eq!(paper_policy["source_version"], 1);
    assert_eq!(paper_policy["accepted"], true);
    assert_eq!(paper_policy["external_surface_gate_required"], true);
    assert_eq!(paper_policy["session_attestation_required"], true);
    assert_eq!(paper_policy["rust_lane_scoped_ipc_required"], true);
    assert_eq!(paper_policy["decision_lease_required"], true);
    assert_eq!(paper_policy["guardian_required"], true);
    assert_eq!(paper_policy["paper_environment_only"], true);
    assert_eq!(paper_policy["live_account_fingerprint_denied"], true);
    assert_eq!(paper_policy["margin_short_options_cfd_denied"], true);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
    assert_eq!(
        result["phase2"]["external_surface_gate"]["status"],
        "BLOCKED"
    );
}

#[tokio::test]
async fn stock_etf_reconciliation_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.get_reconciliation_status","params":{},"id":4810}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf reconciliation status result");
    assert_eq!(
        result["phase"],
        "phase3_reconciliation_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_shadow");
    assert_eq!(result["reconciliation_status_state"], "blocked");
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["paper_shadow_reconciliation_started"], false);
    assert_eq!(result["paper_orders_ready"], false);
    assert_eq!(result["paper_fills_ready"], false);
    assert_eq!(result["shadow_fills_ready"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let matching = &result["matching"];
    assert_eq!(
        matching["expected_lifecycle_contract_id"],
        "ibkr_paper_order_lifecycle_v1"
    );
    assert_eq!(matching["lifecycle_contract_id"], "");
    assert_eq!(
        matching["expected_event_log_contract_id"],
        "broker_lifecycle_event_log_v1"
    );
    assert_eq!(matching["event_log_contract_id"], "");
    assert_eq!(
        matching["expected_shadow_contract_id"],
        "stock_shadow_fill_model_v1"
    );
    assert_eq!(matching["shadow_contract_id"], "");
    assert_eq!(matching["lifecycle_event_accepted"], false);
    assert_eq!(matching["shadow_fill_model_accepted"], false);
    assert!(json_array_contains(
        &matching["lifecycle_blockers"],
        "lifecycle_contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &matching["shadow_blockers"],
        "contract_id_mismatch"
    ));
    assert_eq!(matching["append_only_event_ready"], false);
    assert_eq!(matching["paper_order_id_present"], false);
    assert_eq!(matching["broker_order_id_present"], false);
    assert_eq!(matching["execution_id_present"], false);
    assert_eq!(matching["commission_report_id_present"], false);
    assert_eq!(matching["shadow_signal_id_present"], false);
    assert_eq!(matching["shadow_fill_price_present"], false);
    assert_eq!(matching["paper_shadow_link_present"], false);
    assert_eq!(matching["divergence_bps"], 0);
    assert_eq!(matching["divergence_threshold_bps"], 0);
    assert_eq!(matching["divergence_within_threshold"], false);
    assert_eq!(matching["unmatched_paper_fill_count"], 0);
    assert_eq!(matching["unmatched_shadow_fill_count"], 0);
    assert_eq!(matching["reconciliation_run_id_present"], false);
    assert_eq!(matching["raw_artifact_hash_present"], false);
    assert_eq!(matching["redacted_summary_hash_present"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_scorecard_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.get_scorecard_status","params":{},"id":4812}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("stock_etf scorecard status result");
    assert_eq!(result["phase"], "phase3_scorecard_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_shadow");
    assert_eq!(result["scorecard_status_state"], "blocked");
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["paper_shadow_window_complete"], false);
    assert_eq!(result["ibkr_live_enabled"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["live_or_tiny_live_authorized"], false);

    let scorecard = &result["scorecard"];
    assert_eq!(
        scorecard["expected_contract_id"],
        "stock_etf_scorecard_verdict_v1"
    );
    assert_eq!(scorecard["contract_id"], "");
    assert_eq!(scorecard["source_version"], 0);
    assert_eq!(scorecard["accepted"], false);
    assert_eq!(scorecard["verdict_label"], "insufficient_evidence");
    assert!(json_array_contains(
        &scorecard["blockers"],
        "contract_id_missing"
    ));
    assert!(json_array_contains(
        &scorecard["blockers"],
        "source_version_mismatch"
    ));
    assert_eq!(scorecard["scorecard_input_bundle_hash_present"], false);
    assert_eq!(scorecard["formula_appendix_hash_present"], false);
    assert_eq!(scorecard["statistical_preregistration_hash_present"], false);
    assert_eq!(scorecard["scorecard_manifest_hash_present"], false);
    assert_eq!(scorecard["paper_shadow_window_trading_days"], 0);
    assert_eq!(scorecard["min_independent_observation_count"], 0);
    assert_eq!(scorecard["benchmark_excess_lcb_bps"], 0);
    assert_eq!(scorecard["conservative_cost_stress_lcb_bps"], 0);
    assert_eq!(scorecard["psr_bps"], 0);
    assert_eq!(scorecard["dsr_bps"], 0);
    assert_eq!(scorecard["concentration_label_passed"], false);
    assert_eq!(scorecard["execution_realism_label_passed"], false);
    assert_eq!(scorecard["qc_review_hash_present"], false);
    assert_eq!(scorecard["qc_review_passed"], false);
    assert_eq!(scorecard["scorecard_is_derived_only"], false);
    assert_eq!(scorecard["paper_and_shadow_fills_separate"], false);
    assert_eq!(scorecard["live_fill_claimed"], false);
    assert_eq!(scorecard["bybit_live_execution_unchanged"], false);
    assert_eq!(scorecard["sealed"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

fn json_array_contains(value: &serde_json::Value, expected: &str) -> bool {
    value
        .as_array()
        .map(|items| items.iter().any(|item| item.as_str() == Some(expected)))
        .unwrap_or(false)
}
