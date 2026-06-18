//! Earn IPC command handler.
//!
//! This module keeps Earn asset-movement dispatch out of the trading
//! `SubmitOrder` path. The IPC server only translates JSON to a
//! `PipelineCommand`; this handler runs inside the per-pipeline owner task
//! where `TickPipeline` and its `IntentProcessor` are available.

use crate::intent_processor::{EarnIntentPayload, IntentType, OrderIntent};
use crate::tick_pipeline::TickPipeline;

#[allow(clippy::too_many_arguments)]
pub(crate) async fn handle_process_earn_intent(
    coin: String,
    product_id: String,
    amount_usdt: String,
    expected_apr_bps: i32,
    rationale: String,
    actor_id: String,
    submitted_ts_ms: u64,
    trace_id: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let approval_id = if trace_id.trim().is_empty() {
        format!("earn-ipc-{submitted_ts_ms}")
    } else {
        trace_id.clone()
    };

    let intent_id = format!("earn-EARN_STAKE-{coin}-{approval_id}-{actor_id}");
    let intent = OrderIntent {
        symbol: coin,
        is_long: true,
        qty: 0.0,
        confidence: 1.0,
        strategy: "earn_governance".to_string(),
        order_type: "earn".to_string(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
        intent_type: IntentType::EarnStake,
        earn_payload: Some(EarnIntentPayload {
            amount_usdt,
            expected_apr_bps,
            product_id,
            tenor_days: 0,
            approval_id,
            actor_id,
            rationale,
        }),
    };

    let profile = pipeline.effective_governance_profile();
    let result = pipeline
        .intent_processor
        .process_earn_intent(&intent, &pipeline.governance, profile)
        .await;

    let payload = serde_json::json!({
        "submitted": result.submitted,
        "rejected_reason": result.rejected_reason,
        "lease_id": result.lease_id,
        "intent_id": if result.submitted { Some(intent_id) } else { None::<String> },
        "movement_id": serde_json::Value::Null,
        "bybit_response": serde_json::Value::Null,
    });

    let reply = serde_json::to_string(&payload).map_err(|e| format!("serialize earn result: {e}"));
    let _ = response_tx.send(reply);
}
