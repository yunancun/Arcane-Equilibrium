//! Account/reconciliation/scorecard Stock/ETF status IPC fixture tests.

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
    assert_json_array_eq(
        &account["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "wrong_asset_lane",
            "wrong_broker",
            "cash_ledger_environment_denied",
            "account_fingerprint_hash_invalid",
            "account_snapshot_hash_invalid",
            "portfolio_positions_hash_invalid",
            "currency_missing",
            "as_of_missing",
            "source_report_hash_invalid",
        ],
    );
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
    assert_json_array_eq(
        &session["blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "status_blocked",
            "host_not_loopback",
            "port_not_paper_gateway_default",
            "missing_account_fingerprint",
            "missing_process_identity",
            "unknown_or_live_gateway_mode",
            "missing_secret_slot_fingerprint",
            "secret_slot_mode_denied",
            "live_secret_present_or_unknown",
            "missing_api_server_version",
            "missing_data_tier",
            "missing_data_entitlements_fingerprint",
            "market_data_entitlement_purchase_not_denied",
            "missing_gateway_startup_time",
            "missing_raw_artifact_hash",
            "invalid_attestation_window",
            "stale_attestation",
        ],
    );
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
    assert_json_array_eq(
        &matching["lifecycle_blockers"],
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
    assert_json_array_eq(
        &matching["shadow_blockers"],
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
    assert_json_array_eq(
        &matching["reconciliation_blockers"],
        &[
            "contract_id_mismatch",
            "source_version_mismatch",
            "wrong_asset_lane",
            "wrong_broker",
            "scope_mismatch",
            "authority_scope_mismatch",
            "reconciliation_run_id_missing",
            "paper_order_local_id_missing",
            "broker_order_id_missing",
            "execution_id_missing",
            "commission_report_id_missing",
            "shadow_signal_id_missing",
            "lifecycle_contract_hash_invalid",
            "event_log_contract_hash_invalid",
            "paper_fill_import_request_hash_invalid",
            "shadow_signal_request_hash_invalid",
            "shadow_fill_model_hash_invalid",
            "cost_model_version_hash_invalid",
            "market_data_provenance_hash_invalid",
            "paper_shadow_divergence_threshold_hash_invalid",
            "paper_shadow_link_hash_invalid",
            "raw_artifact_hash_invalid",
            "redacted_summary_hash_invalid",
            "source_artifact_hash_invalid",
            "append_only_event_not_ready",
            "paper_fill_not_imported",
            "shadow_fill_not_synthetic",
            "divergence_threshold_missing",
        ],
    );
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

    let input_bundle = &result["scorecard_input_bundle"];
    assert_eq!(input_bundle["accepted"], false);
    assert_json_array_eq(
        &input_bundle["blockers"],
        &[
            "cash_ledger_rejected",
            "cost_model_rejected",
            "benchmark_rejected",
            "shadow_fill_model_rejected",
            "storage_capacity_rejected",
            "readonly_probe_result_import_request_contract_id_mismatch",
            "readonly_probe_result_import_request_hash_invalid",
            "market_data_provenance_contract_hash_invalid",
            "reference_data_sources_contract_hash_invalid",
            "risk_policy_contract_hash_invalid",
            "atomic_fact_input_hash_invalid",
            "source_commit_missing",
            "scorecard_not_derived_only",
            "paper_shadow_fill_separation_missing",
            "bybit_live_execution_not_protected",
        ],
    );
    assert_eq!(
        input_bundle["readonly_probe_result_import_request_contract_id"],
        ""
    );
    assert_eq!(
        input_bundle["readonly_probe_result_import_request_hash_present"],
        false
    );
    assert_eq!(
        input_bundle["market_data_provenance_contract_hash_present"],
        false
    );
    assert_eq!(
        input_bundle["reference_data_sources_contract_hash_present"],
        false
    );
    assert_eq!(input_bundle["risk_policy_contract_hash_present"], false);
    assert_eq!(input_bundle["atomic_fact_input_hash_present"], false);
    assert_eq!(input_bundle["source_commit_present"], false);
    assert_eq!(input_bundle["scorecard_is_derived_only"], false);
    assert_eq!(input_bundle["paper_and_shadow_fills_separate"], false);
    assert_eq!(input_bundle["bybit_live_execution_unchanged"], false);
    assert_eq!(input_bundle["ibkr_contact_performed"], false);
    assert_eq!(input_bundle["connector_runtime_started"], false);
    assert_eq!(input_bundle["broker_fill_import_performed"], false);
    assert_eq!(input_bundle["scorecard_writer_started"], false);
    assert_eq!(input_bundle["db_apply_performed"], false);
    assert_eq!(input_bundle["evidence_clock_started"], false);
    assert_eq!(input_bundle["secret_content_serialized"], false);
    assert_eq!(input_bundle["live_or_tiny_live_authorized"], false);

    let derivation = &result["scorecard_derivation"];
    assert_eq!(
        derivation["expected_contract_id"],
        "stock_etf_scorecard_derivation_v1"
    );
    assert_eq!(derivation["contract_id"], "");
    assert_eq!(derivation["source_version"], 0);
    assert_eq!(derivation["accepted"], false);
    assert_json_array_eq(
        &derivation["blockers"],
        &[
            "contract_id_missing",
            "source_version_mismatch",
            "wrong_asset_lane",
            "wrong_broker",
            "environment_denied",
            "derivation_run_id_missing",
            "strategy_id_missing",
            "universe_version_missing",
            "benchmark_version_missing",
            "as_of_date_missing",
            "scorecard_input_bundle_hash_invalid",
            "evidence_clock_manifest_hash_invalid",
            "dq_manifest_hash_invalid",
            "paper_shadow_reconciliation_hash_invalid",
            "formula_appendix_hash_invalid",
            "statistical_preregistration_hash_invalid",
            "scorecard_manifest_hash_invalid",
            "scorecard_verdict_hash_invalid",
            "source_commit_hash_invalid",
            "derivation_code_hash_invalid",
            "output_artifact_hash_invalid",
            "qc_review_hash_invalid",
            "mit_review_hash_invalid",
            "qa_review_hash_invalid",
            "not_derived_from_atomic_facts_only",
            "idempotent_replay_not_proven",
            "paper_shadow_fill_separation_missing",
            "bybit_live_execution_not_protected",
            "not_sealed",
        ],
    );
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
    assert_json_array_eq(
        &scorecard["blockers"],
        &[
            "contract_id_missing",
            "source_version_mismatch",
            "wrong_asset_lane",
            "wrong_broker",
            "environment_denied",
            "scorecard_input_bundle_hash_invalid",
            "evidence_clock_manifest_hash_invalid",
            "dq_manifest_hash_invalid",
            "formula_appendix_hash_invalid",
            "statistical_preregistration_hash_invalid",
            "benchmark_version_hash_invalid",
            "cost_model_version_hash_invalid",
            "strategy_hypothesis_hash_invalid",
            "reference_data_sources_hash_invalid",
            "paper_shadow_reconciliation_hash_invalid",
            "scorecard_manifest_hash_invalid",
            "verdict_rationale_hash_invalid",
            "window_threshold_missing",
            "min_independent_observation_missing",
            "divergence_threshold_missing",
            "psr_threshold_missing",
            "dsr_threshold_missing",
            "qc_review_hash_invalid",
            "mit_review_hash_invalid",
            "qa_review_hash_invalid",
            "qc_review_missing",
            "mit_review_missing",
            "qa_review_missing",
            "scorecard_not_derived_only",
            "paper_shadow_fill_separation_missing",
            "bybit_live_execution_not_protected",
            "not_sealed",
        ],
    );
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
