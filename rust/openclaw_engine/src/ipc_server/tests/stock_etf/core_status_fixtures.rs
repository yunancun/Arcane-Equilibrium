//! Core Stock/ETF IPC status fixture tests.

use super::*;

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
    assert_json_array_eq(&result["phase0_blockers"], &[]);
    assert_eq!(result["contract_count"], 36);
    assert_json_array_eq(
        &result["contracts"],
        &[
            "asset_lane_taxonomy_v1",
            "broker_capability_registry_v1",
            "phase2_ibkr_external_surface_gate_v1",
            "non_bybit_api_allowlist_v1",
            "stock_etf_ibkr_readonly_probe_request_v1",
            "stock_etf_ibkr_readonly_probe_result_import_request_v1",
            "instrument_identity_contract_v1",
            "stock_etf_pit_universe_contract_v1",
            "stock_etf_strategy_hypothesis_contract_v1",
            "stock_etf_risk_policy_v1",
            "stock_etf_reference_data_sources_v1",
            "ibkr_api_session_topology_v1",
            "ibkr_session_attestation_v1",
            "feature_flag_secret_auth_matrix_v1",
            "lane_scoped_ipc_v1",
            "stock_etf_paper_order_request_v1",
            "stock_etf_paper_fill_import_request_v1",
            "stock_etf_shadow_signal_request_v1",
            "ibkr_paper_order_lifecycle_v1",
            "broker_lifecycle_event_log_v1",
            "audit.asset_lane_events_v1",
            "stock_etf_db_evidence_ddl_v1",
            "stock_market_data_provenance_v1",
            "broker_account_portfolio_cash_ledger_v1",
            "cost_model_version_v1",
            "benchmark_versions_v1",
            "stock_shadow_fill_model_v1",
            "stock_etf_paper_shadow_reconciliation_v1",
            "stock_etf_collector_run_v1",
            "stock_etf_dq_manifest_v1",
            "stock_etf_evidence_clock_v1",
            "gui_lane_contract_v1",
            "stock_etf_storage_capacity_v1",
            "stock_etf_kill_switch_and_disable_cleanup_runbook_v1",
            "stock_etf_release_packet_v1",
            "tiny_live_adr_eligibility_v1",
        ],
    );
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
    assert_json_array_eq(
        &phase2["external_surface_gate"]["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "status_not_pass",
            "live_ports_not_denied",
            "secret_contract_missing",
            "live_secret_present_or_unknown",
        ],
    );
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
    assert_json_array_eq(
        &market_data["blockers"],
        &[
            "market_data_provenance_contract_id_mismatch",
            "market_data_provenance_version_mismatch",
            "market_data_provenance_wrong_asset_lane",
            "market_data_provenance_wrong_broker",
            "market_data_provenance_environment_denied",
            "source_missing",
            "entitlement_tier_missing",
            "raw_payload_hash_invalid",
            "market_data_timestamp_missing",
            "adjustment_marker_unknown",
            "corporate_action_version_hash_invalid",
            "symbol_missing",
            "instrument_identity_hash_invalid",
            "calendar_session_missing",
            "source_artifact_hash_invalid",
            "bybit_live_execution_not_protected",
        ],
    );
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
    assert_json_array_eq(
        &collector_run["blockers"],
        &[
            "collector_run_contract_id_mismatch",
            "collector_run_version_mismatch",
            "collector_run_wrong_asset_lane",
            "collector_run_wrong_broker",
            "collector_run_environment_denied",
            "collector_run_id_missing",
            "collector_trading_day_missing",
            "collector_pit_universe_contract_mismatch",
            "collector_pit_universe_hash_invalid",
            "collector_market_data_provenance_contract_mismatch",
            "collector_market_data_provenance_hash_invalid",
            "collector_reference_data_sources_contract_mismatch",
            "collector_reference_data_sources_hash_invalid",
            "collector_storage_capacity_contract_mismatch",
            "collector_storage_capacity_hash_invalid",
            "collector_expected_sessions_too_small",
            "collector_gap_report_hash_invalid",
            "collector_dq_manifest_hash_invalid",
            "collector_replay_manifest_hash_invalid",
            "collector_source_artifact_hash_invalid",
            "bybit_live_execution_not_protected",
        ],
    );
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
    assert_json_array_eq(
        &evidence_clock["blockers"],
        &[
            "evidence_clock_contract_id_mismatch",
            "evidence_clock_version_mismatch",
            "evidence_clock_wrong_asset_lane",
            "evidence_clock_wrong_broker",
            "evidence_clock_environment_denied",
            "evidence_clock_collector_run_contract_mismatch",
            "evidence_clock_collector_run_hash_invalid",
            "evidence_clock_dq_manifest_contract_mismatch",
            "evidence_clock_dq_manifest_hash_invalid",
            "evidence_clock_source_artifact_hash_invalid",
            "evidence_clock_market_data_provenance_hash_invalid",
            "evidence_clock_scorecard_input_hash_invalid",
            "bybit_live_execution_not_protected",
            "ibkr_connector_not_green_five_days",
            "shadow_collector_not_green_five_days",
            "frozen_inputs_rejected",
            "dq_manifest_shape_rejected",
        ],
    );
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
    assert_json_array_eq(
        &dq_manifest["shape_blockers"],
        &[
            "dq_manifest_contract_id_mismatch",
            "dq_manifest_version_mismatch",
            "dq_manifest_wrong_asset_lane",
            "dq_manifest_wrong_broker",
            "dq_manifest_environment_denied",
            "dq_manifest_collector_run_id_missing",
            "dq_manifest_market_data_provenance_contract_mismatch",
            "dq_manifest_market_data_provenance_hash_invalid",
            "dq_manifest_source_artifact_hash_invalid",
            "bybit_live_execution_not_protected",
            "trading_day_missing",
            "quarantine_manifest_hash_invalid",
            "atomic_fact_input_hash_invalid",
        ],
    );
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
    assert_json_array_eq(
        &universe["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "universe_id_invalid",
            "universe_version_invalid",
            "universe_hash_invalid",
            "point_in_time_asof_missing",
            "effective_from_missing",
            "constituent_count_missing",
            "max_constituents_invalid",
            "inclusion_rule_hash_invalid",
            "exclusion_rule_hash_invalid",
            "liquidity_screen_hash_invalid",
            "tradability_screen_hash_invalid",
            "priips_screen_hash_invalid",
            "delisted_inactive_policy_hash_invalid",
            "corporate_action_version_hash_invalid",
            "market_calendar_hash_invalid",
            "source_artifact_hash_invalid",
            "universe_not_frozen_for_evidence_clock",
            "survivorship_controls_missing",
        ],
    );
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
    assert_json_array_eq(
        &shadow["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "signal_id_missing",
            "instrument_identity_hash_invalid",
            "order_side_unknown",
            "intended_notional_missing",
            "market_session_missing",
            "quote_or_bar_source_hash_invalid",
            "conservative_fill_price_missing",
            "synthetic_shadow_marker_missing",
        ],
    );
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
    assert_json_array_eq(
        &strategy["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "hypothesis_id_invalid",
            "hypothesis_version_invalid",
            "strategy_family_denied",
            "timeframe_denied",
            "instrument_scope_denied",
            "universe_hash_invalid",
            "pit_universe_contract_hash_invalid",
            "benchmark_version_hash_invalid",
            "cost_model_version_hash_invalid",
            "entry_rule_hash_invalid",
            "exit_rule_hash_invalid",
            "risk_rule_hash_invalid",
            "feature_set_hash_invalid",
            "data_source_policy_hash_invalid",
            "statistical_design_hash_invalid",
            "hypothesis_preregistration_hash_invalid",
            "holding_period_too_short",
            "turnover_limit_missing",
            "max_constituents_missing",
            "independent_observation_target_too_low",
            "lookahead_controls_missing",
            "survivorship_controls_missing",
            "multiple_testing_control_missing",
            "benchmark_metric_missing",
            "cost_after_metric_missing",
        ],
    );
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
    assert_json_array_eq(
        &lifecycle["blockers"],
        &[
            "lifecycle_contract_id_mismatch",
            "event_log_contract_id_mismatch",
            "source_version_mismatch",
            "event_id_missing",
            "event_sequence_missing",
            "previous_event_hash_invalid",
            "event_time_missing",
            "event_hash_invalid",
            "request_contract_id_mismatch",
            "request_envelope_hash_invalid",
            "operation_transition_mismatch",
            "local_order_id_missing",
            "idempotency_key_missing",
            "reconciliation_run_id_missing",
            "invalid_state_transition",
            "denial_reason_missing_on_denied_event",
            "stale_state_policy_missing",
            "raw_artifact_hash_invalid",
            "redacted_summary_hash_invalid",
        ],
    );
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
