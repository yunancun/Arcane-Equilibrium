//! ADR-0048 Stock/ETF IPC fixture tests.

use super::super::*;
use super::{
    empty_account_manager_slot, empty_budget_slot, empty_cost_edge_advisor_slot,
    empty_h_state_cache_slot, empty_teacher_slot, make_test_config, make_test_data_dir,
};
mod foundation_status_fixtures;
mod precontact_fixtures;
mod request_contracts;
mod status_fixtures;

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
