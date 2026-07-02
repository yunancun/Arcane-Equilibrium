//! Stock/ETF pre-contact IPC fixture tests.

use super::*;

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
    assert_json_array_eq(
        &connector_skeleton["blockers"],
        &["phase2_gate_not_accepted"],
    );
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
    assert_eq!(phase2["api_allowlist"]["accepted"], true);
    assert_json_array_eq(
        &phase2["api_allowlist"]["read_actions"],
        &[
            "server_time_read",
            "connection_health_read",
            "account_summary_snapshot_read",
            "portfolio_positions_snapshot_read",
            "contract_details_read",
            "market_data_snapshot_read",
            "market_data_subscription_read",
            "historical_bars_read",
            "open_paper_orders_read",
            "paper_executions_commissions_read",
        ],
    );
    assert_eq!(phase2["api_allowlist"]["read_action_count"], 10);
    assert_json_array_eq(
        &phase2["api_allowlist"]["paper_write_actions"],
        &[
            "paper_order_submit",
            "paper_order_cancel",
            "paper_order_replace",
        ],
    );
    assert_eq!(phase2["api_allowlist"]["paper_write_action_count"], 3);
    assert_json_array_eq(
        &phase2["api_allowlist"]["denied_actions"],
        &[
            "live_order_submit",
            "live_account_query",
            "account_transfer",
            "margin_enablement",
            "short_borrow",
            "options_trading",
            "cfd_trading",
            "market_data_entitlement_purchase",
            "account_management_write",
            "client_portal_web_api_use",
        ],
    );
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
    assert_json_array_eq(
        &readonly_probe["blockers"],
        &["phase2_gate_not_accepted", "probe_request_artifact_missing"],
    );
    assert_eq!(readonly_probe["ibkr_contact_performed"], false);
    assert_eq!(readonly_probe["connector_runtime_started"], false);
    assert_eq!(readonly_probe["secret_content_serialized"], false);
    assert_eq!(readonly_probe["order_routed"], false);
    assert_eq!(readonly_probe["paper_order_submitted"], false);
    assert_eq!(readonly_probe["db_apply_performed"], false);
    assert_eq!(readonly_probe["evidence_clock_started"], false);
    assert_eq!(readonly_probe["bybit_path_reused"], false);
    assert_eq!(readonly_probe["live_or_tiny_live_authorized"], false);
    let result_import_request = &phase2["readonly_probe_result_import_request"];
    assert_eq!(
        result_import_request["contract_id"],
        "stock_etf_ibkr_readonly_probe_result_import_request_v1"
    );
    assert_eq!(result_import_request["source_version"], 1);
    assert_eq!(result_import_request["request_artifact_present"], false);
    assert_eq!(result_import_request["request_validated"], false);
    assert_eq!(result_import_request["accepted_for_import"], false);
    assert_eq!(
        result_import_request["status"],
        "blocked_no_result_import_request_artifact"
    );
    assert_json_array_eq(
        &result_import_request["blockers"],
        &[
            "phase2_gate_not_accepted",
            "probe_result_import_request_artifact_missing",
        ],
    );
    assert_eq!(result_import_request["ibkr_contact_performed"], false);
    assert_eq!(result_import_request["connector_runtime_started"], false);
    assert_eq!(result_import_request["secret_content_serialized"], false);
    assert_eq!(result_import_request["result_import_performed"], false);
    assert_eq!(result_import_request["evidence_writer_started"], false);
    assert_eq!(result_import_request["scorecard_writer_started"], false);
    assert_eq!(result_import_request["db_apply_performed"], false);
    assert_eq!(result_import_request["order_routed"], false);
    assert_eq!(result_import_request["paper_order_submitted"], false);
    assert_eq!(result_import_request["bybit_path_reused"], false);
    assert_eq!(result_import_request["live_or_tiny_live_authorized"], false);
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
