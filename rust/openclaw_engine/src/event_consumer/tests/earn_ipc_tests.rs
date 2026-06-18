//! Earn IPC owner-task tests.

use std::collections::HashSet;

use crate::tick_pipeline::{PipelineCommand, PipelineKind};

use super::{make_test_pipeline, make_test_writer};

#[tokio::test]
async fn process_earn_intent_command_fail_closed_when_unwired() {
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut state = super::super::loop_handlers::LoopState::new(HashSet::new());
    let (response_tx, response_rx) = tokio::sync::oneshot::channel();

    super::super::loop_handlers::handle_pipeline_command(
        Some(PipelineCommand::ProcessEarnIntent {
            coin: "USDT".to_string(),
            product_id: "BYBIT_USDT_FLEXIBLE_v1".to_string(),
            amount_usdt: "100".to_string(),
            expected_apr_bps: 800,
            rationale: "Sprint 1B first stake owner task contract test".to_string(),
            actor_id: "test-operator".to_string(),
            submitted_ts_ms: 1_803_000_000_000,
            trace_id: "earn-owner-trace-123".to_string(),
            response_tx,
        }),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
        None,
        None,
        PipelineKind::Paper,
    )
    .await;

    let json_str = response_rx
        .await
        .expect("oneshot response")
        .expect("handler returns JSON envelope");
    let payload: serde_json::Value = serde_json::from_str(&json_str).expect("valid JSON");
    assert_eq!(payload["submitted"], false);
    assert!(
        payload["rejected_reason"]
            .as_str()
            .unwrap_or_default()
            .contains("earn_dispatch_unwired"),
        "actual payload={payload}"
    );
    assert!(payload["intent_id"].is_null());
    assert!(payload["movement_id"].is_null());
    assert!(payload["bybit_response"].is_null());
}
