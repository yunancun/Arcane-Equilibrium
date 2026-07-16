//! W4 Stock/ETF connection-health IPC fixture tests。

use super::*;

#[tokio::test]
async fn stock_etf_connection_health_is_external_verification_pending_without_socket() {
    // W4：inactive 引擎的誠實 health＝對 inactive session 的真實 FSM 計算,非 fake-success。
    // ephemeral manager 撞 permit stub 一次 → Disconnected(EnvelopeRequired),零 socket。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req =
        r#"{"jsonrpc":"2.0","method":"stock_etf.get_connection_health","params":{},"id":4810}"#;
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
    let result = resp.result.expect("stock_etf connection health result");
    assert_eq!(result["phase"], "phase2_connection_health_source_fixture");
    assert_eq!(result["asset_lane"], "stock_etf_cash");
    assert_eq!(result["broker"], "ibkr");
    assert_eq!(result["environment"], "paper_readonly");
    assert_eq!(result["contract_id"], "ibkr_connection_health_report_v1");
    assert_eq!(result["source_version"], 1);
    assert_eq!(result["report_status"], "external_verification_pending");
    assert_eq!(
        result["connection_health_status_state"],
        "external_verification_pending"
    );

    // session 束：inactive 恆 Disconnected(EnvelopeRequired)、非 active、reconnect 0。
    assert_eq!(result["session_state"], "disconnected");
    assert_eq!(result["halt_reason"], "envelope_required");
    assert_eq!(result["session_active"], false);
    assert_eq!(result["reconnect_attempt"], 0);

    // pacing 束：main_tokens_available＝滿桶 telemetry(rate=lines/2=50);活動計數全零。
    assert_eq!(result["main_tokens_available"], 50);
    assert_eq!(result["queue_depth"], 0);
    assert_eq!(result["lines_in_use"], 0);
    assert_eq!(result["ib_pacing_strikes"], 0);
    assert_eq!(result["admitted"], 0);
    assert_eq!(result["rejected_order_verb"], 0);
    assert_eq!(result["rejected_queue_full"], 0);
    assert_eq!(result["rejected_timeout"], 0);
    assert_eq!(result["rejected_historical"], 0);
    assert_eq!(result["rejected_lines"], 0);

    // attestation / entitlement 束：恆 blocked / pending / 非 live。
    assert_eq!(result["attestation_status"], "BLOCKED");
    assert_eq!(result["account_fingerprint_is_live"], false);
    assert_eq!(result["entitlement_state"], "pending");

    // 負空間安全束：恆 false（零接觸/零 socket/零 secret/零 order）。
    assert_eq!(result["ibkr_contact_performed"], false);
    assert_eq!(result["secret_slot_touched"], false);
    assert_eq!(result["gateway_socket_open"], false);
    assert_eq!(result["order_routed"], false);
    assert_eq!(result["bybit_ipc_reused"], false);
    assert_eq!(result["ibkr_live_enabled"], false);
    assert_eq!(result["db_apply_performed"], false);

    // phase2 束：gate 恆 BLOCKED（normalizer 由此派生 lineage_present=false）。
    assert_eq!(
        result["phase2"]["external_surface_gate"]["status"],
        "BLOCKED"
    );
    assert_eq!(result["phase2"]["first_ibkr_contact_allowed"], false);
    assert_eq!(result["phase2"]["connector_enabled"], false);
}
