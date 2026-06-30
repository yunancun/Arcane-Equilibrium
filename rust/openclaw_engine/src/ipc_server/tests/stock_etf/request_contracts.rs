//! Stock/ETF IPC request contract fixture tests.

use super::*;
use openclaw_types::{
    BrokerOperation, NonBybitApiAction, StockEtfIbkrReadonlyProbeKind,
    StockEtfIbkrReadonlyProbeRequestV1, StockEtfPaperFillImportRequestV1,
    StockEtfPaperOrderRequestEnvelopeV1, StockEtfShadowSignalRequestV1,
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
    assert_eq!(
        result["request_envelope"]["expected_contract_id"],
        "stock_etf_paper_order_request_v1"
    );
    assert_eq!(result["request_envelope"]["parse_ok"], false);
    assert_eq!(result["request_envelope"]["accepted"], false);
    assert_eq!(
        result["request_envelope"]["blockers"][0],
        "request_envelope_parse_failed"
    );
    assert_eq!(result["request_envelope_accepted_for_ipc"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(
        result["phase2"]["external_surface_gate"]["ibkr_contact_allowed"],
        false
    );
}

#[tokio::test]
async fn stock_etf_preview_validates_paper_request_envelope_without_runtime_authority() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let params =
        serde_json::to_string(&StockEtfPaperOrderRequestEnvelopeV1::accepted_preview_fixture())
            .expect("preview envelope json");
    let req = format!(
        r#"{{"jsonrpc":"2.0","method":"stock_etf.preview_paper_order","params":{params},"id":48011}}"#
    );
    let resp = dispatch_request(
        &req,
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
    assert_eq!(result["runtime_authority_denied"], true);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["request_envelope"]["parse_ok"], true);
    assert_eq!(result["request_envelope"]["accepted"], true);
    assert_eq!(
        result["request_envelope"]["expected_request_method"],
        "preview_paper_order"
    );
    assert_eq!(
        result["request_envelope"]["request_method"],
        "preview_paper_order"
    );
    assert_eq!(result["request_envelope"]["ipc_method_matches"], true);
    assert_eq!(result["request_envelope"]["accepted_for_ipc"], true);
    assert_eq!(result["request_envelope_accepted_for_ipc"], true);
    assert_eq!(result["request_envelope"]["effect_capable"], false);
    assert_eq!(result["request_envelope"]["request_id_present"], true);
    assert_eq!(
        result["request_envelope"]["account_fingerprint_hash_present"],
        true
    );
}

#[tokio::test]
async fn stock_etf_paper_request_envelope_rejects_ipc_method_mismatch() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let params =
        serde_json::to_string(&StockEtfPaperOrderRequestEnvelopeV1::accepted_submit_fixture())
            .expect("submit envelope json");
    let req = format!(
        r#"{{"jsonrpc":"2.0","method":"stock_etf.cancel_paper_order","params":{params},"id":48012}}"#
    );
    let resp = dispatch_request(
        &req,
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
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["request_envelope"]["parse_ok"], true);
    assert_eq!(result["request_envelope"]["accepted"], true);
    assert_eq!(
        result["request_envelope"]["expected_request_method"],
        "cancel_paper_order"
    );
    assert_eq!(
        result["request_envelope"]["request_method"],
        "submit_paper_order"
    );
    assert_eq!(result["request_envelope"]["ipc_method_matches"], false);
    assert_eq!(
        result["request_envelope"]["ipc_binding_blockers"][0],
        "ipc_method_mismatch"
    );
    assert_eq!(result["request_envelope"]["accepted_for_ipc"], false);
    assert_eq!(result["request_envelope_accepted_for_ipc"], false);
}

#[tokio::test]
async fn stock_etf_import_paper_fills_validates_fill_import_request_without_runtime_authority() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let params = serde_json::to_string(&StockEtfPaperFillImportRequestV1::accepted_fixture())
        .expect("fill import request json");
    let req = format!(
        r#"{{"jsonrpc":"2.0","method":"stock_etf.import_paper_fills","params":{params},"id":48013}}"#
    );
    let resp = dispatch_request(
        &req,
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
    assert_eq!(result["runtime_authority_denied"], true);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["fill_import_request"]["parse_ok"], true);
    assert_eq!(result["fill_import_request"]["accepted"], true);
    assert_eq!(
        result["fill_import_request"]["expected_request_method"],
        "import_paper_fills"
    );
    assert_eq!(
        result["fill_import_request"]["request_method"],
        "import_paper_fills"
    );
    assert_eq!(result["fill_import_request"]["ipc_method_matches"], true);
    assert_eq!(result["fill_import_request"]["accepted_for_ipc"], true);
    assert_eq!(result["fill_import_request_accepted_for_ipc"], true);
    assert_eq!(result["fill_import_request"]["effect_capable"], false);
    assert_eq!(
        result["fill_import_request"]["reconciliation_run_id_present"],
        true
    );
    assert_eq!(result["fill_import_request"]["execution_id_present"], true);
    assert_eq!(
        result["fill_import_request"]["raw_artifact_hash_present"],
        true
    );
    assert_eq!(
        result["fill_import_request"]["fill_import_performed"],
        false
    );
    assert_eq!(result["fill_import_request"]["db_apply_performed"], false);
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
}

#[tokio::test]
async fn stock_etf_import_paper_fills_rejects_stale_or_minimal_params() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"stock_etf.import_paper_fills","params":{},"id":48014}"#;
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
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["fill_import_request"]["parse_ok"], false);
    assert_eq!(result["fill_import_request"]["accepted"], false);
    assert_eq!(
        result["fill_import_request"]["blockers"][0],
        "fill_import_request_parse_failed"
    );
    assert_eq!(result["fill_import_request"]["accepted_for_ipc"], false);
    assert_eq!(result["fill_import_request_accepted_for_ipc"], false);
    assert_eq!(
        result["fill_import_request"]["fill_import_performed"],
        false
    );
    assert_eq!(result["fill_import_request"]["db_apply_performed"], false);
}

#[tokio::test]
async fn stock_etf_evaluate_shadow_signal_validates_request_without_runtime_authority() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let params = serde_json::to_string(&StockEtfShadowSignalRequestV1::accepted_fixture())
        .expect("shadow signal request json");
    let req = format!(
        r#"{{"jsonrpc":"2.0","method":"stock_etf.evaluate_shadow_signal","params":{params},"id":48015}}"#
    );
    let resp = dispatch_request(
        &req,
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
    assert_eq!(result["runtime_authority_denied"], true);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["shadow_signal_request"]["parse_ok"], true);
    assert_eq!(result["shadow_signal_request"]["accepted"], true);
    assert_eq!(
        result["shadow_signal_request"]["expected_request_method"],
        "evaluate_shadow_signal"
    );
    assert_eq!(
        result["shadow_signal_request"]["request_method"],
        "evaluate_shadow_signal"
    );
    assert_eq!(result["shadow_signal_request"]["ipc_method_matches"], true);
    assert_eq!(result["shadow_signal_request"]["accepted_for_ipc"], true);
    assert_eq!(result["shadow_signal_request_accepted_for_ipc"], true);
    assert_eq!(result["shadow_signal_request"]["effect_capable"], false);
    assert_eq!(
        result["shadow_signal_request"]["shadow_signal_id_present"],
        true
    );
    assert_eq!(
        result["shadow_signal_request"]["evidence_clock_hash_present"],
        true
    );
    assert_eq!(
        result["shadow_signal_request"]["cost_model_version_hash_present"],
        true
    );
    assert_eq!(
        result["shadow_signal_request"]["shadow_signal_emitted"],
        false
    );
    assert_eq!(
        result["shadow_signal_request"]["shadow_fill_generated"],
        false
    );
    assert_eq!(
        result["shadow_signal_request"]["scorecard_writer_started"],
        false
    );
    assert_eq!(result["shadow_signal_request"]["db_apply_performed"], false);
}

#[tokio::test]
async fn stock_etf_evaluate_shadow_signal_rejects_stale_or_minimal_params() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.evaluate_shadow_signal","params":{},"id":48016}"#;
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
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["shadow_signal_request"]["parse_ok"], false);
    assert_eq!(result["shadow_signal_request"]["accepted"], false);
    assert_eq!(
        result["shadow_signal_request"]["blockers"][0],
        "shadow_signal_request_parse_failed"
    );
    assert_eq!(result["shadow_signal_request"]["accepted_for_ipc"], false);
    assert_eq!(result["shadow_signal_request_accepted_for_ipc"], false);
    assert_eq!(
        result["shadow_signal_request"]["shadow_signal_emitted"],
        false
    );
    assert_eq!(result["shadow_signal_request"]["db_apply_performed"], false);
}

#[tokio::test]
async fn stock_etf_preview_readonly_probe_validates_request_without_runtime_authority() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let params = serde_json::to_string(&StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture())
        .expect("readonly probe request json");
    let req = format!(
        r#"{{"jsonrpc":"2.0","method":"stock_etf.preview_readonly_probe","params":{params},"id":48017}}"#
    );
    let resp = dispatch_request(
        &req,
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
    assert_eq!(result["runtime_authority_denied"], true);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(
        result["readonly_probe_request"]["expected_contract_id"],
        "stock_etf_ibkr_readonly_probe_request_v1"
    );
    assert_eq!(result["readonly_probe_request"]["parse_ok"], true);
    assert_eq!(result["readonly_probe_request"]["accepted"], true);
    assert_eq!(
        result["readonly_probe_request"]["expected_request_method"],
        "preview_readonly_probe"
    );
    assert_eq!(result["readonly_probe_request"]["accepted_for_ipc"], true);
    assert_eq!(result["readonly_probe_request_accepted_for_ipc"], true);
    assert_eq!(
        result["readonly_probe_request"]["probe_kind"],
        "connection_health"
    );
    assert_eq!(
        result["readonly_probe_request"]["api_action"],
        "connection_health_read"
    );
    assert_eq!(result["readonly_probe_request"]["operation"], "health_read");
    assert_eq!(
        result["readonly_probe_request"]["authority_scope"],
        "read_only"
    );
    assert_eq!(result["readonly_probe_request"]["effect_capable"], false);
    assert_eq!(result["readonly_probe_request"]["request_id_present"], true);
    assert_eq!(result["readonly_probe_request"]["probe_id_present"], true);
    assert_eq!(
        result["readonly_probe_request"]["phase2_gate_artifact_hash_present"],
        true
    );
    assert_eq!(
        result["readonly_probe_request"]["api_allowlist_hash_present"],
        true
    );
    assert_eq!(
        result["readonly_probe_request"]["read_probe_executed"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["ibkr_contact_performed"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["connector_runtime_started"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["secret_content_serialized"],
        false
    );
    assert_eq!(result["readonly_probe_request"]["order_routed"], false);
    assert_eq!(
        result["readonly_probe_request"]["paper_order_submitted"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["db_apply_performed"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["evidence_clock_started"],
        false
    );
    assert_eq!(result["readonly_probe_request"]["bybit_path_reused"], false);
    assert_eq!(
        result["readonly_probe_request"]["live_or_tiny_live_authorized"],
        false
    );
    assert_eq!(
        result["phase2"]["external_surface_gate"]["ibkr_contact_allowed"],
        false
    );
}

#[tokio::test]
async fn stock_etf_preview_readonly_probe_decision_uses_request_operation() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let mut request = StockEtfIbkrReadonlyProbeRequestV1::accepted_fixture();
    request.probe_kind = StockEtfIbkrReadonlyProbeKind::MarketDataSnapshot;
    request.api_action = NonBybitApiAction::MarketDataSnapshotRead;
    request.operation = BrokerOperation::MarketDataRead;
    let params = serde_json::to_string(&request).expect("readonly probe request json");
    let req = format!(
        r#"{{"jsonrpc":"2.0","method":"stock_etf.preview_readonly_probe","params":{params},"id":48019}}"#
    );
    let resp = dispatch_request(
        &req,
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
    assert_eq!(result["decision"]["operation"], "market_data_read");
    assert_eq!(
        result["readonly_probe_request"]["probe_kind"],
        "market_data_snapshot"
    );
    assert_eq!(
        result["readonly_probe_request"]["api_action"],
        "market_data_snapshot_read"
    );
    assert_eq!(
        result["readonly_probe_request"]["operation"],
        "market_data_read"
    );
    assert_eq!(result["readonly_probe_request_accepted_for_ipc"], true);
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["order_routed"], false);
}

#[tokio::test]
async fn stock_etf_preview_readonly_probe_rejects_minimal_params() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.preview_readonly_probe","params":{},"id":48018}"#;
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
    assert_eq!(result["ibkr_call_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["readonly_probe_request"]["parse_ok"], false);
    assert_eq!(result["readonly_probe_request"]["accepted"], false);
    assert_eq!(
        result["readonly_probe_request"]["blockers"][0],
        "readonly_probe_request_parse_failed"
    );
    assert_eq!(result["readonly_probe_request"]["accepted_for_ipc"], false);
    assert_eq!(result["readonly_probe_request_accepted_for_ipc"], false);
    assert_eq!(
        result["readonly_probe_request"]["read_probe_executed"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["ibkr_contact_performed"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["connector_runtime_started"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["secret_content_serialized"],
        false
    );
    assert_eq!(result["readonly_probe_request"]["order_routed"], false);
    assert_eq!(
        result["readonly_probe_request"]["paper_order_submitted"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["db_apply_performed"],
        false
    );
    assert_eq!(
        result["readonly_probe_request"]["evidence_clock_started"],
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
