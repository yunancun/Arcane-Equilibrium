//! ADR-0048 Stock/ETF IPC fixture tests.

use super::super::*;
use super::{
    empty_account_manager_slot, empty_budget_slot, empty_cost_edge_advisor_slot,
    empty_h_state_cache_slot, empty_teacher_slot, make_test_config, make_test_data_dir,
};
mod request_contracts;
mod status_fixtures;

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

    let connector_skeleton = &result["connector_skeleton"];
    assert_eq!(
        connector_skeleton["surface_id"],
        "ibkr_stock_etf_readonly_connector_skeleton_v1"
    );
    assert_eq!(connector_skeleton["accepted"], false);
    assert_eq!(connector_skeleton["status"], "blocked_source_only");
    assert!(json_array_contains(
        &connector_skeleton["blockers"],
        "phase2_gate_not_accepted"
    ));
    assert_eq!(connector_skeleton["network_contact_performed"], false);
    assert_eq!(connector_skeleton["secret_content_loaded"], false);
    assert_eq!(connector_skeleton["paper_channel_exposed"], false);
    assert_eq!(connector_skeleton["live_channel_exposed"], false);
    assert_eq!(connector_skeleton["order_write_method_present"], false);
    assert_eq!(connector_skeleton["bybit_path_reused"], false);

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
    let readonly_probe = &phase2["readonly_probe_request"];
    assert_eq!(
        readonly_probe["contract_id"],
        "stock_etf_ibkr_readonly_probe_request_v1"
    );
    assert_eq!(readonly_probe["source_version"], 1);
    assert_eq!(readonly_probe["request_artifact_present"], false);
    assert_eq!(readonly_probe["request_validated"], false);
    assert_eq!(readonly_probe["accepted_for_contact"], false);
    assert_eq!(readonly_probe["status"], "blocked_no_request_artifact");
    assert!(json_array_contains(
        &readonly_probe["blockers"],
        "phase2_gate_not_accepted"
    ));
    assert!(json_array_contains(
        &readonly_probe["blockers"],
        "probe_request_artifact_missing"
    ));
    assert_eq!(readonly_probe["ibkr_contact_performed"], false);
    assert_eq!(readonly_probe["connector_runtime_started"], false);
    assert_eq!(readonly_probe["secret_content_serialized"], false);
    assert_eq!(readonly_probe["order_routed"], false);
    assert_eq!(readonly_probe["paper_order_submitted"], false);
    assert_eq!(readonly_probe["db_apply_performed"], false);
    assert_eq!(readonly_probe["evidence_clock_started"], false);
    assert_eq!(readonly_probe["bybit_path_reused"], false);
    assert_eq!(readonly_probe["live_or_tiny_live_authorized"], false);
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
async fn stock_etf_status_methods_ignore_untrusted_params() {
    let methods = [
        "stock_etf.get_lane_status",
        "stock_etf.get_phase0_status",
        "stock_etf.get_readiness",
        "stock_etf.get_data_foundation_status",
        "stock_etf.get_policy_status",
        "stock_etf.get_authorization_status",
        "stock_etf.get_account_status",
        "stock_etf.get_evidence_status",
        "stock_etf.get_universe_status",
        "stock_etf.get_shadow_status",
        "stock_etf.get_paper_status",
        "stock_etf.get_reconciliation_status",
        "stock_etf.get_scorecard_status",
        "stock_etf.get_launch_status",
        "stock_etf.get_release_packet_status",
        "stock_etf.get_disable_cleanup_status",
    ];
    let untrusted_params = serde_json::json!({
        "asset_lane": "crypto_perp",
        "broker": "bybit",
        "environment": "live",
        "method": "stock_etf.submit_paper_order",
        "request_method": "submit_paper_order",
        "operation": "paper_order_submit",
        "ibkr_call_performed": true,
        "secret_slot_touched": true,
        "order_routed": true,
        "bybit_ipc_reused": true,
    });

    for method in methods {
        let empty_req =
            format!(r#"{{"jsonrpc":"2.0","method":"{method}","params":{{}},"id":49000}}"#);
        let untrusted_req = format!(
            r#"{{"jsonrpc":"2.0","method":"{method}","params":{},"id":49001}}"#,
            untrusted_params
        );

        let expected = dispatch_stock_etf_test_request(&empty_req).await;
        let actual = dispatch_stock_etf_test_request(&untrusted_req).await;

        assert!(expected.error.is_none(), "{method} empty params failed");
        assert!(actual.error.is_none(), "{method} untrusted params failed");
        assert_eq!(
            actual.result, expected.result,
            "{method} changed after untrusted params"
        );
    }
}

#[tokio::test]
async fn stock_etf_phase0_status_exposes_accepted_source_manifest_without_runtime_authority() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_phase0_status","params":{},"id":48041}"#;
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
    let result = resp.result.expect("stock_etf phase0 status result");
    assert_eq!(
        result["phase"],
        "phase0_contract_packet_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(
        result["phase0_status_state"],
        "accepted_no_runtime_authority"
    );
    assert_eq!(result["phase0_accepted"], true);
    assert_eq!(result["phase0_blockers"].as_array().unwrap().len(), 0);
    assert_eq!(result["contract_count"], 36);
    assert!(json_array_contains(
        &result["contracts"],
        "stock_etf_ibkr_readonly_probe_request_v1"
    ));
    assert!(json_array_contains(
        &result["contracts"],
        "stock_etf_ibkr_readonly_probe_result_import_request_v1"
    ));
    assert!(json_array_contains(
        &result["contracts"],
        "stock_etf_paper_fill_import_request_v1"
    ));
    assert!(json_array_contains(
        &result["contracts"],
        "stock_etf_shadow_signal_request_v1"
    ));
    assert!(json_array_contains(
        &result["contracts"],
        "stock_etf_paper_shadow_reconciliation_v1"
    ));
    assert!(json_array_contains(
        &result["contracts"],
        "stock_etf_collector_run_v1"
    ));
    assert!(json_array_contains(
        &result["contracts"],
        "stock_etf_dq_manifest_v1"
    ));
    assert_eq!(
        result["manifest"]["schema"],
        "stock_etf_phase0_contract_packet_manifest_v1"
    );
    assert_eq!(
        result["manifest"]["status"],
        "ACCEPTED_PHASE0_CONTRACT_NO_RUNTIME_AUTHORITY"
    );
    assert_eq!(result["api_baseline"]["live_ports_denied"], true);
    assert_eq!(result["api_baseline"]["ibkr_call_performed"], false);
    assert_eq!(result["global_denials"]["ibkr_live"], true);
    assert_eq!(result["global_denials"]["tiny_live"], true);
    assert_eq!(result["global_denials"]["gui_lane_authority"], true);
    assert_eq!(result["phase1_runtime_started"], false);
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["phase4_runtime_started"], false);
    assert_eq!(result["phase5_started"], false);
    assert_eq!(result["paper_shadow_launch_authorized"], false);
    assert_eq!(result["tiny_live_or_live_authorized"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
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

    let collector_run = &result["collector_run"];
    assert_eq!(
        collector_run["expected_contract_id"],
        "stock_etf_collector_run_v1"
    );
    assert_eq!(collector_run["contract_id"], "");
    assert_eq!(collector_run["source_version"], 0);
    assert_eq!(collector_run["accepted"], false);
    assert!(json_array_contains(
        &collector_run["blockers"],
        "collector_run_contract_id_mismatch"
    ));
    assert_eq!(collector_run["expected_trading_sessions"], 0);
    assert_eq!(collector_run["completed_trading_sessions"], 0);
    assert_eq!(collector_run["market_data_ingestion_started"], false);
    assert_eq!(collector_run["evidence_writer_started"], false);
    assert_eq!(collector_run["scorecard_writer_started"], false);
    assert_eq!(collector_run["db_apply_performed"], false);
    assert_eq!(collector_run["secret_content_serialized"], false);
    assert_eq!(collector_run["live_or_tiny_live_authorized"], false);

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
    assert_eq!(
        dq_manifest["expected_contract_id"],
        "stock_etf_dq_manifest_v1"
    );
    assert_eq!(dq_manifest["contract_id"], "");
    assert_eq!(dq_manifest["source_version"], 0);
    assert_eq!(dq_manifest["shape_accepted"], false);
    assert!(json_array_contains(
        &dq_manifest["shape_blockers"],
        "dq_manifest_contract_id_mismatch"
    ));
    assert_eq!(dq_manifest["passes_day_quality"], false);
    assert_eq!(dq_manifest["collector_run_id"], "");
    assert_eq!(
        dq_manifest["market_data_provenance_contract_hash_present"],
        false
    );
    assert_eq!(dq_manifest["source_artifact_hash_present"], false);
    assert_eq!(dq_manifest["bybit_live_execution_unchanged"], false);
    assert_eq!(dq_manifest["ibkr_contact_performed"], false);
    assert_eq!(dq_manifest["connector_runtime_started"], false);
    assert_eq!(dq_manifest["market_data_ingestion_started"], false);
    assert_eq!(dq_manifest["dq_writer_started"], false);
    assert_eq!(dq_manifest["evidence_clock_started"], false);
    assert_eq!(dq_manifest["scorecard_writer_started"], false);
    assert_eq!(dq_manifest["db_apply_performed"], false);
    assert_eq!(dq_manifest["secret_content_serialized"], false);
    assert_eq!(dq_manifest["live_or_tiny_live_authorized"], false);
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
async fn stock_etf_data_foundation_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_data_foundation_status","params":{},"id":4814}"#;
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
    let result = resp
        .result
        .expect("stock_etf data foundation status result");
    assert_eq!(
        result["phase"],
        "phase2_data_foundation_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["data_foundation_status_state"], "blocked");
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["contract_details_request_started"], false);
    assert_eq!(result["reference_data_collection_started"], false);
    assert_eq!(result["collector_started"], false);
    assert_eq!(result["market_data_ingestion_started"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let identity = &result["instrument_identity"];
    assert_eq!(
        identity["expected_contract_id"],
        "instrument_identity_contract_v1"
    );
    assert_eq!(identity["contract_id"], "");
    assert_eq!(identity["source_version"], 0);
    assert_eq!(identity["accepted"], false);
    assert!(json_array_contains(
        &identity["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &identity["blockers"],
        "source_version_mismatch"
    ));
    assert_eq!(identity["instrument_kind"], "stock");
    assert_eq!(identity["symbol"], "");
    assert_eq!(identity["market_calendar_hash_present"], false);
    assert_eq!(identity["broker_contract_details_hash_present"], false);
    assert_eq!(identity["instrument_identity_hash_present"], false);
    assert_eq!(identity["bybit_live_execution_unchanged"], true);
    assert_eq!(identity["ibkr_live_denied"], true);
    assert_eq!(identity["margin_short_denied"], true);
    assert_eq!(identity["options_cfd_denied"], true);
    assert_eq!(identity["ibkr_contact_performed"], false);
    assert_eq!(identity["secret_content_serialized"], false);

    let reference = &result["reference_data_sources"];
    assert_eq!(
        reference["expected_contract_id"],
        "stock_etf_reference_data_sources_v1"
    );
    assert_eq!(reference["contract_id"], "");
    assert_eq!(reference["source_version"], 0);
    assert_eq!(reference["accepted"], false);
    assert!(json_array_contains(
        &reference["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &reference["blockers"],
        "source_version_mismatch"
    ));
    assert_eq!(reference["environment"], "paper");
    assert_eq!(reference["frozen_for_evidence_clock"], false);
    assert_eq!(reference["corporate_action_raw_hash_present"], false);
    assert_eq!(reference["fx_rate_snapshot_hash_present"], false);
    assert_eq!(reference["commission_schedule_hash_present"], false);
    assert_eq!(reference["bybit_live_execution_unchanged"], true);
    assert_eq!(reference["ibkr_contact_performed"], false);
    assert_eq!(reference["connector_runtime_started"], false);
    assert_eq!(reference["secret_content_serialized"], false);
    assert_eq!(reference["live_or_tiny_live_authorized"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_policy_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_policy_status","params":{},"id":4815}"#;
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
    let result = resp.result.expect("stock_etf policy status result");
    assert_eq!(result["phase"], "phase2_policy_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["policy_status_state"], "blocked");
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["risk_runtime_started"], false);
    assert_eq!(result["paper_order_rehearsal_started"], false);
    assert_eq!(result["paper_order_submitted"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["ibkr_live_enabled"], false);
    assert_eq!(result["paper_order_entry_visible"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let risk = &result["risk_policy"];
    assert_eq!(risk["expected_contract_id"], "stock_etf_risk_policy_v1");
    assert_eq!(risk["contract_id"], "");
    assert_eq!(risk["source_version"], 0);
    assert_eq!(risk["config_version"], 0);
    assert_eq!(risk["accepted"], false);
    assert!(json_array_contains(
        &risk["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &risk["blockers"],
        "source_version_mismatch"
    ));
    assert_eq!(risk["environment"], "paper");
    assert_eq!(risk["enabled"], false);
    assert_eq!(risk["shadow_only"], true);
    assert_eq!(risk["allow_margin"], false);
    assert_eq!(risk["allow_short"], false);
    assert_eq!(risk["allow_options"], false);
    assert_eq!(risk["allow_cfd"], false);
    assert_eq!(risk["allow_transfer"], false);
    assert_eq!(risk["allow_live"], false);
    assert_eq!(risk["bybit_live_execution_unchanged"], true);
    assert_eq!(risk["ibkr_contact_performed"], false);
    assert_eq!(risk["connector_runtime_started"], false);
    assert_eq!(risk["secret_content_serialized"], false);

    let registry = &result["broker_capability_registry"];
    assert_eq!(
        registry["expected_registry_id"],
        "broker_capability_registry_v1"
    );
    assert_eq!(registry["registry_id"], "");
    assert_eq!(registry["source_version"], 0);
    assert_eq!(registry["accepted"], false);
    assert!(json_array_contains(
        &registry["blockers"],
        "registry_id_mismatch"
    ));
    assert!(json_array_contains(
        &registry["blockers"],
        "source_version_mismatch"
    ));
    assert_eq!(registry["operation_count"], 0);
    assert_eq!(registry["required_audit_field_count"], 0);
    assert_eq!(registry["read_operation_count"], 0);
    assert_eq!(
        registry["lane_scoped_ipc_contract_id"],
        "lane_scoped_ipc_v1"
    );
    assert_eq!(
        registry["readonly_probe_request_contract_id"],
        "stock_etf_ibkr_readonly_probe_request_v1"
    );
    assert_eq!(
        registry["readonly_probe_result_import_request_contract_id"],
        "stock_etf_ibkr_readonly_probe_result_import_request_v1"
    );
    assert_eq!(registry["read_rows_require_lane_scoped_ipc"], false);
    assert_eq!(registry["read_rows_require_readonly_probe_request"], false);
    assert_eq!(
        registry["scorecard_requires_readonly_probe_result_import_request"],
        false
    );
    assert_eq!(registry["paper_operation_count"], 0);
    assert_eq!(registry["denied_operation_count"], 0);
    assert_eq!(registry["bybit_live_execution_unchanged"], true);
    assert_eq!(registry["python_broker_write_authority_denied"], true);
    assert_eq!(registry["ibkr_live_denied"], true);
    assert_eq!(registry["cfd_margin_reserved_denied"], true);
    assert_eq!(registry["first_ibkr_contact_performed"], false);
    assert_eq!(registry["secret_content_serialized"], false);

    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_authorization_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.get_authorization_status","params":{},"id":4816}"#;
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
    let result = resp.result.expect("stock_etf authorization status result");
    assert_eq!(
        result["phase"],
        "phase2_authorization_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper");
    assert_eq!(result["authorization_status_state"], "blocked");
    assert_eq!(result["phase2_started"], false);
    assert_eq!(result["paper_order_authority_present"], false);
    assert_eq!(result["scoped_authorization_present"], false);
    assert_eq!(result["decision_lease_valid"], false);
    assert_eq!(result["guardian_allows"], false);
    assert_eq!(result["paper_order_submitted"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);

    let matrix = &result["authorization_matrix"];
    assert_eq!(
        matrix["expected_contract_id"],
        "feature_flag_secret_auth_matrix_v1"
    );
    assert_eq!(matrix["contract_id"], "");
    assert_eq!(matrix["source_version"], 0);
    assert_eq!(matrix["request_asset_lane"], "stock_etf_cash");
    assert_eq!(matrix["request_broker"], "ibkr");
    assert_eq!(matrix["request_environment"], "paper");
    assert_eq!(matrix["request_instrument_kind"], "stock");
    assert_eq!(matrix["request_operation"], "paper_order_submit");
    assert_eq!(matrix["request_allowed"], false);
    assert_eq!(matrix["effective_authority_scope"], "denied");
    assert_eq!(matrix["gui_lane_state_override_denied"], true);
    assert_eq!(matrix["server_rust_matrix_authoritative"], true);
    assert!(json_array_contains(
        &matrix["blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &matrix["blockers"],
        "source_version_mismatch"
    ));

    let secret = &result["secret_slot_contract"];
    assert_eq!(
        secret["expected_contract_id"],
        "ibkr_secret_slot_contract_v1"
    );
    assert_eq!(secret["accepted"], false);
    assert_eq!(secret["contract_present"], false);
    assert_eq!(secret["secret_content_serialized"], false);
    assert_eq!(secret["account_id_serialized"], false);

    let artifact = &result["phase2_gate_artifact"];
    assert_eq!(
        artifact["expected_contract_id"],
        "phase2_ibkr_external_surface_gate_v1"
    );
    assert_eq!(artifact["ibkr_contact_allowed"], false);
    assert_eq!(artifact["sealed"], false);

    let session = &result["session_attestation"];
    assert_eq!(
        session["expected_contract_id"],
        "ibkr_session_attestation_v1"
    );
    assert_eq!(session["attestation_accepted"], false);
    assert_eq!(session["account_fingerprint_is_live"], false);

    let envelope = &result["authorization_envelope"];
    assert_eq!(envelope["permission_scope"], "denied");
    assert_eq!(envelope["expires_at_ms"], 0);
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
    assert_eq!(
        lifecycle["expected_request_contract_id"],
        "stock_etf_paper_order_request_v1"
    );
    assert_eq!(lifecycle["request_contract_id"], "");
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
    assert_eq!(lifecycle["event_sequence"], 0);
    assert_eq!(lifecycle["event_sequence_present"], false);
    assert_eq!(lifecycle["genesis_event"], false);
    assert_eq!(lifecycle["previous_event_hash_present"], false);
    assert_eq!(lifecycle["event_hash_present"], false);
    assert_eq!(lifecycle["request_envelope_hash_present"], false);
    assert_eq!(lifecycle["stale_state_policy"], serde_json::Value::Null);
    assert_eq!(lifecycle["stale_state_policy_present"], false);
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
    assert_eq!(reconstructability["event_hash_chain_ready"], false);
    assert_eq!(reconstructability["request_envelope_linked"], false);
    assert_eq!(reconstructability["stale_state_policy_present"], false);
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

fn json_array_contains(value: &serde_json::Value, expected: &str) -> bool {
    value
        .as_array()
        .map(|items| items.iter().any(|item| item.as_str() == Some(expected)))
        .unwrap_or(false)
}

async fn dispatch_stock_etf_test_request(req: &str) -> JsonRpcResponse {
    let config = make_test_config();
    let dd = make_test_data_dir();
    dispatch_request(
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
    .await
}
