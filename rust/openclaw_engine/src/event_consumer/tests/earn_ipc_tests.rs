//! Earn IPC owner-task tests.

use std::collections::HashSet;
use std::sync::Arc;

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

#[tokio::test]
async fn process_earn_intent_command_hits_governance_gate_when_capabilities_wired() {
    let mut pipeline =
        crate::tick_pipeline::TickPipeline::with_kind(&["USDT"], 10_000.0, PipelineKind::Live);
    let rest_client = Arc::new(
        crate::bybit_rest_client::BybitRestClient::new(
            crate::bybit_rest_client::BybitEnvironment::LiveDemo,
            Some("test_key".to_string()),
            Some("test_secret".to_string()),
        )
        .expect("LiveDemo client constructor must not require mainnet opt-in"),
    );
    let audit_pool = sqlx::postgres::PgPoolOptions::new()
        .max_connections(1)
        .connect_lazy("postgres://openclaw:openclaw@127.0.0.1:1/openclaw")
        .expect("lazy pool construction should not connect");
    super::super::bootstrap::wire_earn_capabilities(
        &mut pipeline,
        Some(&rest_client),
        Some(&audit_pool),
    );

    let mut writer = make_test_writer();
    let mut state = super::super::loop_handlers::LoopState::new(HashSet::new());
    let (response_tx, response_rx) = tokio::sync::oneshot::channel();

    super::super::loop_handlers::handle_pipeline_command(
        Some(PipelineCommand::ProcessEarnIntent {
            coin: "USDT".to_string(),
            product_id: "BYBIT_USDT_FLEXIBLE_v1".to_string(),
            amount_usdt: "100".to_string(),
            expected_apr_bps: 800,
            rationale: "Sprint 1B first stake capability wiring test".to_string(),
            actor_id: "test-operator".to_string(),
            submitted_ts_ms: 1_803_000_000_001,
            trace_id: "earn-owner-trace-wired-123".to_string(),
            response_tx,
        }),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
        None,
        None,
        PipelineKind::Live,
    )
    .await;

    let json_str = response_rx
        .await
        .expect("oneshot response")
        .expect("handler returns JSON envelope");
    let payload: serde_json::Value = serde_json::from_str(&json_str).expect("valid JSON");
    assert_eq!(payload["submitted"], false);
    let reason = payload["rejected_reason"].as_str().unwrap_or_default();
    assert!(
        reason.contains("earn_dispatch_governance_not_authorized"),
        "actual payload={payload}"
    );
    assert!(
        !reason.contains("earn_dispatch_unwired"),
        "capability wiring should move the failure past Gate E-0: {payload}"
    );
}
