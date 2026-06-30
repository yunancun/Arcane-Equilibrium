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

fn json_array_contains(value: &serde_json::Value, expected: &str) -> bool {
    value
        .as_array()
        .map(|items| items.iter().any(|item| item.as_str() == Some(expected)))
        .unwrap_or(false)
}
