//! Tail Stock/ETF status IPC fixture tests.

use super::*;

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
    assert_eq!(
        matching["expected_reconciliation_contract_id"],
        "stock_etf_paper_shadow_reconciliation_v1"
    );
    assert_eq!(matching["reconciliation_contract_id"], "");
    assert_eq!(matching["lifecycle_event_accepted"], false);
    assert_eq!(matching["shadow_fill_model_accepted"], false);
    assert_eq!(matching["reconciliation_accepted"], false);
    assert!(json_array_contains(
        &matching["lifecycle_blockers"],
        "lifecycle_contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &matching["shadow_blockers"],
        "contract_id_mismatch"
    ));
    assert!(json_array_contains(
        &matching["reconciliation_blockers"],
        "contract_id_mismatch"
    ));
    assert_eq!(matching["append_only_event_ready"], false);
    assert_eq!(matching["paper_order_id_present"], false);
    assert_eq!(matching["broker_order_id_present"], false);
    assert_eq!(matching["execution_id_present"], false);
    assert_eq!(matching["commission_report_id_present"], false);
    assert_eq!(matching["contract_reconciliation_run_id_present"], false);
    assert_eq!(matching["shadow_signal_id_present"], false);
    assert_eq!(matching["shadow_fill_price_present"], false);
    assert_eq!(matching["paper_shadow_link_present"], false);
    assert_eq!(matching["paper_shadow_link_hash_present"], false);
    assert_eq!(matching["divergence_bps"], 0);
    assert_eq!(matching["divergence_threshold_bps"], 0);
    assert_eq!(matching["divergence_within_threshold"], false);
    assert_eq!(matching["unmatched_paper_fill_count"], 0);
    assert_eq!(matching["unmatched_shadow_fill_count"], 0);
    assert_eq!(matching["reconciliation_run_id_present"], false);
    assert_eq!(matching["raw_artifact_hash_present"], false);
    assert_eq!(matching["redacted_summary_hash_present"], false);
    assert_eq!(matching["paper_fill_imported"], false);
    assert_eq!(matching["shadow_fill_synthetic"], false);
    assert_eq!(matching["reconciliation_writer_started"], false);
    assert_eq!(matching["ibkr_contact_performed"], false);
    assert_eq!(matching["connector_runtime_started"], false);
    assert_eq!(matching["secret_content_serialized"], false);
    assert_eq!(matching["fill_import_performed"], false);
    assert_eq!(matching["shadow_fill_generated"], false);

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

    let derivation = &result["scorecard_derivation"];
    assert_eq!(
        derivation["expected_contract_id"],
        "stock_etf_scorecard_derivation_v1"
    );
    assert_eq!(derivation["contract_id"], "");
    assert_eq!(derivation["source_version"], 0);
    assert_eq!(derivation["accepted"], false);
    assert!(json_array_contains(
        &derivation["blockers"],
        "contract_id_missing"
    ));
    assert_eq!(derivation["derivation_run_id_present"], false);
    assert_eq!(
        derivation["paper_shadow_reconciliation_hash_present"],
        false
    );
    assert_eq!(derivation["scorecard_verdict_hash_present"], false);
    assert_eq!(derivation["output_artifact_hash_present"], false);
    assert_eq!(derivation["derived_from_atomic_facts_only"], false);
    assert_eq!(derivation["idempotent_replay_proven"], false);
    assert_eq!(derivation["paper_and_shadow_fills_separate"], false);
    assert_eq!(derivation["bybit_live_execution_unchanged"], false);
    assert_eq!(derivation["ibkr_contact_performed"], false);
    assert_eq!(derivation["shadow_fill_generated"], false);
    assert_eq!(derivation["reconciliation_writer_started"], false);
    assert_eq!(derivation["scorecard_writer_started"], false);
    assert_eq!(derivation["db_apply_performed"], false);
    assert_eq!(derivation["live_or_tiny_live_authorized"], false);
    assert_eq!(derivation["sealed"], false);

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
    assert_eq!(scorecard["paper_shadow_reconciliation_hash_present"], false);
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

#[tokio::test]
async fn stock_etf_launch_status_is_blocked_source_fixture_without_side_effects() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_launch_status","params":{},"id":4813}"#;
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
    let result = resp.result.expect("stock_etf launch status result");
    assert_eq!(result["phase"], "phase5_launch_status_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_shadow");
    assert_eq!(result["launch_status_state"], "blocked");
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["phase5_started"], false);

    let release = &result["release_packet"];
    assert_eq!(
        release["expected_contract_id"],
        "stock_etf_release_packet_v1"
    );
    assert_eq!(release["accepted"], false);
    assert_eq!(release["paper_shadow_window_complete"], false);
    assert_eq!(release["engineering_shakedown_complete"], false);
    assert_eq!(release["role_report_count"], 0);
    assert_eq!(release["manifest_hash_count"], 0);
    assert_eq!(release["gui_screenshot_hash_count"], 0);
    assert_eq!(release["dq_manifest_hash_count"], 0);
    assert_eq!(release["scorecard_regeneration_hash_count"], 0);
    assert_eq!(release["secret_content_serialized"], false);
    assert_eq!(release["ibkr_live_or_tiny_live_authorized"], false);
    assert_eq!(release["sealed"], false);

    let runbook = &result["disable_cleanup_runbook"];
    assert_eq!(
        runbook["expected_runbook_id"],
        "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    );
    assert_eq!(runbook["accepted"], false);
    assert_eq!(runbook["env_flag_count"], 0);
    assert_eq!(runbook["proof_count"], 0);
    assert_eq!(runbook["ibkr_contact_performed"], false);
    assert_eq!(runbook["connector_runtime_started"], false);
    assert_eq!(runbook["paper_order_routed"], false);
    assert_eq!(runbook["secret_slot_created"], false);
    assert_eq!(runbook["secret_content_serialized"], false);
    assert_eq!(runbook["destructive_db_cleanup_requested"], false);
    assert_eq!(runbook["db_delete_or_truncate_allowed"], false);
    assert_eq!(runbook["paper_shadow_launch_authorized"], false);
    assert_eq!(runbook["tiny_live_authorized"], false);
    assert_eq!(runbook["live_authorized"], false);

    let tiny_live = &result["tiny_live_adr_eligibility"];
    assert_eq!(
        tiny_live["expected_contract_id"],
        "tiny_live_adr_eligibility_v1"
    );
    assert_eq!(tiny_live["accepted"], false);
    assert_eq!(tiny_live["decision"], "not_eligible");
    assert_eq!(tiny_live["scorecard_derivation_hash_present"], false);
    assert_eq!(tiny_live["scorecard_verdict_hash_present"], false);
    assert_eq!(tiny_live["scorecard_manifest_hash_present"], false);
    assert_eq!(tiny_live["paper_shadow_reconciliation_hash_present"], false);
    assert_eq!(tiny_live["qa_review_hash_present"], false);
    assert_eq!(tiny_live["paper_shadow_window_complete"], false);
    assert_eq!(tiny_live["benchmark_relative_after_cost_lcb_bps"], 0);
    assert_eq!(tiny_live["independent_observation_count"], 0);
    assert_eq!(tiny_live["min_independent_observation_count"], 0);
    assert_eq!(tiny_live["conservative_cost_stress_lcb_bps"], 0);
    assert_eq!(tiny_live["paper_shadow_divergence_bps"], 0);
    assert_eq!(tiny_live["max_paper_shadow_divergence_bps"], 0);
    assert_eq!(tiny_live["qa_review_passed"], false);
    assert_eq!(tiny_live["secret_content_serialized"], false);
    assert_eq!(tiny_live["sealed"], false);

    assert_eq!(result["paper_shadow_launch_authorized"], false);
    assert_eq!(result["tiny_live_or_live_authorized"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_release_packet_status_is_display_only_source_fixture() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.get_release_packet_status","params":{},"id":4818}"#;
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
    let result = resp.result.expect("stock_etf release packet status result");
    assert_eq!(
        result["phase"],
        "phase5_release_packet_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_shadow");
    assert_eq!(
        result["release_packet_status_state"],
        "source_ready_runtime_blocked"
    );
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["phase5_started"], false);

    let release = &result["release_packet"];
    assert_eq!(
        release["expected_contract_id"],
        "stock_etf_release_packet_v1"
    );
    assert_eq!(release["packet_id"], "stock_etf_release_packet_v1");
    assert_eq!(release["source_version"], 1);
    assert_eq!(release["accepted"], true);
    assert_eq!(release["blockers"].as_array().unwrap().len(), 0);
    assert_eq!(release["source_commit_present"], true);
    assert_eq!(release["reviewer_role_count"], 8);
    assert_eq!(release["role_report_count"], 2);
    assert_eq!(release["e2_log_hash_present"], true);
    assert_eq!(release["e3_redaction_log_hash_present"], true);
    assert_eq!(release["e4_log_hash_present"], true);
    assert_eq!(release["qa_log_hash_present"], true);
    assert_eq!(release["manifest_hash_count"], 2);
    assert_eq!(release["manifest_hashes"].as_array().unwrap().len(), 2);
    assert_eq!(release["pg_migrations_declared"], false);
    assert_eq!(release["pg_dry_run_log_hash_present"], false);
    assert_eq!(release["pg_double_apply_log_hash_present"], false);
    assert_eq!(release["redaction_fixture_hash_present"], true);
    assert_eq!(release["gui_screenshot_hash_count"], 1);
    assert_eq!(release["dq_manifest_hash_count"], 1);
    assert_eq!(release["scorecard_regeneration_hash_count"], 1);
    assert_eq!(release["evidence_archive_pointer_present"], true);
    assert_eq!(release["evidence_archive_hash_present"], true);
    assert_eq!(release["paper_shadow_window_complete"], true);
    assert_eq!(release["engineering_shakedown_complete"], true);
    assert_eq!(release["secret_content_serialized"], false);
    assert_eq!(release["ibkr_live_or_tiny_live_authorized"], false);
    assert_eq!(release["sealed"], true);

    let kill = &release["kill_disable_cleanup_proof"];
    assert_eq!(kill["stock_etf_lane_enabled_false"], true);
    assert_eq!(kill["ibkr_readonly_enabled_false"], true);
    assert_eq!(kill["ibkr_paper_enabled_false"], true);
    assert_eq!(kill["stock_etf_shadow_only_true"], true);
    assert_eq!(kill["collector_stopped"], true);
    assert_eq!(kill["gui_stock_views_disabled_or_hidden"], true);
    assert_eq!(kill["live_secret_absence_proven"], true);
    assert_eq!(kill["evidence_archive_forward_only"], true);
    assert_eq!(kill["destructive_db_cleanup_requested"], false);
    assert_eq!(kill["proof_hash_present"], true);

    assert_eq!(result["paper_shadow_launch_authorized"], false);
    assert_eq!(result["tiny_live_or_live_authorized"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}

#[tokio::test]
async fn stock_etf_disable_cleanup_status_is_display_only_source_fixture() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.get_disable_cleanup_status","params":{},"id":4817}"#;
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
        .expect("stock_etf disable cleanup status result");
    assert_eq!(
        result["phase"],
        "phase5_disable_cleanup_status_source_fixture"
    );
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_shadow");
    assert_eq!(
        result["disable_cleanup_status_state"],
        "source_ready_runtime_blocked"
    );
    assert_eq!(result["phase3_started"], false);
    assert_eq!(result["phase5_started"], false);
    assert_eq!(result["collector_stop_requested"], false);
    assert_eq!(result["gui_disable_requested"], false);
    assert_eq!(result["evidence_archive_requested"], false);
    assert_eq!(result["db_cleanup_requested"], false);

    let runbook = &result["runbook"];
    assert_eq!(
        runbook["expected_runbook_id"],
        "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    );
    assert_eq!(
        runbook["runbook_id"],
        "stock_etf_kill_switch_and_disable_cleanup_runbook_v1"
    );
    assert_eq!(runbook["source_version"], 1);
    assert_eq!(runbook["accepted"], true);
    assert_eq!(runbook["blockers"].as_array().unwrap().len(), 0);
    assert_eq!(runbook["source_artifact_hash_present"], true);
    assert_eq!(runbook["bybit_live_execution_unchanged"], true);
    assert_eq!(runbook["env_flag_count"], 4);
    assert_eq!(runbook["proof_count"], 7);
    assert_eq!(runbook["env_flags"].as_array().unwrap().len(), 4);
    assert_eq!(runbook["proofs"].as_array().unwrap().len(), 7);
    assert_eq!(runbook["ibkr_contact_performed"], false);
    assert_eq!(runbook["connector_runtime_started"], false);
    assert_eq!(runbook["paper_order_routed"], false);
    assert_eq!(runbook["secret_slot_created"], false);
    assert_eq!(runbook["secret_content_serialized"], false);
    assert_eq!(runbook["destructive_db_cleanup_requested"], false);
    assert_eq!(runbook["db_delete_or_truncate_allowed"], false);
    assert_eq!(runbook["paper_shadow_launch_authorized"], false);
    assert_eq!(runbook["tiny_live_authorized"], false);
    assert_eq!(runbook["live_authorized"], false);

    assert_eq!(result["paper_shadow_launch_authorized"], false);
    assert_eq!(result["tiny_live_or_live_authorized"], false);
    assert_eq!(result["connector_runtime_started"], false);
    assert_eq!(result["scorecard_writer_started"], false);
    assert_eq!(result["db_apply_performed"], false);
    assert_eq!(result["evidence_clock_started"], false);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}
