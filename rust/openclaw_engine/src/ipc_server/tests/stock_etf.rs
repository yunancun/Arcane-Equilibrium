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

fn json_array_contains(value: &serde_json::Value, expected: &str) -> bool {
    value
        .as_array()
        .map(|items| items.iter().any(|item| item.as_str() == Some(expected)))
        .unwrap_or(false)
}
