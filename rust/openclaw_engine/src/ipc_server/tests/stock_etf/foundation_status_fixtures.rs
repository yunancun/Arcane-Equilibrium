//! Stock/ETF foundation, policy, and authorization IPC fixture tests.

use super::*;

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
