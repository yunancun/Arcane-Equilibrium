//! Earn IPC contract tests.

use super::super::*;
use super::{
    empty_account_manager_slot, empty_budget_slot, empty_cost_edge_advisor_slot,
    empty_h_state_cache_slot, empty_teacher_slot, make_test_config, make_test_data_dir,
};

#[tokio::test]
async fn test_process_earn_intent_dispatches_pipeline_command() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();

    tokio::spawn(async move {
        let cmd = rx.recv().await.expect("process_earn_intent command");
        match cmd {
            PipelineCommand::ProcessEarnIntent {
                coin,
                product_id,
                amount_usdt,
                expected_apr_bps,
                rationale,
                actor_id,
                submitted_ts_ms,
                trace_id,
                response_tx,
            } => {
                assert_eq!(coin, "USDT");
                assert_eq!(product_id, "BYBIT_USDT_FLEXIBLE_v1");
                assert_eq!(amount_usdt, "100");
                assert_eq!(expected_apr_bps, 800);
                assert_eq!(rationale, "Sprint 1B first stake micro pressure test");
                assert_eq!(actor_id, "test-operator");
                assert_eq!(submitted_ts_ms, 1_803_000_000_000);
                assert_eq!(trace_id, "earn-trace-123");
                let _ = response_tx.send(Ok(serde_json::json!({
                    "submitted": false,
                    "rejected_reason": "earn_dispatch_unwired: bybit_earn_client not injected",
                    "lease_id": null,
                    "intent_id": null,
                    "movement_id": null,
                    "bybit_response": null,
                })
                .to_string()));
            }
            other => panic!("unexpected command: {other:?}"),
        }
    });

    let req = serde_json::json!({
        "jsonrpc": "2.0",
        "method": "process_earn_intent",
        "params": {
            "coin": "USDT",
            "product_id": "BYBIT_USDT_FLEXIBLE_v1",
            "amount_usdt": "100",
            "expected_apr_bps": 800,
            "rationale": "Sprint 1B first stake micro pressure test",
            "actor_id": "test-operator",
            "submitted_ts_ms": 1_803_000_000_000_u64,
            "trace_id": "earn-trace-123"
        },
        "id": 80
    })
    .to_string();

    let resp = dispatch_request(
        &req,
        &config,
        &dd,
        &EngineCommandChannels {
            paper: Some(tx),
            ..Default::default()
        },
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

    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.expect("result payload");
    assert_eq!(result["submitted"], false);
    assert!(result["rejected_reason"]
        .as_str()
        .unwrap_or_default()
        .contains("earn_dispatch_unwired"));
    assert!(result["movement_id"].is_null());
}
