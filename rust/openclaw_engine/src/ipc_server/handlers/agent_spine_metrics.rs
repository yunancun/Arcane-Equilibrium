//! Agent Decision Spine channel metrics IPC handler.
//!
//! MODULE_NOTE:
//!   `get_agent_spine_channel_metrics` is a read-only observability route used
//!   by passive healthcheck `[55]` / P1-FILL-LINEAGE-MONITOR. It exposes the
//!   three process-wide runtime_shadow channel counters without introducing a
//!   DB dependency or touching the tick hot path.
//!
//!   `drop_total` means initial `try_send` failures, not final lineage loss.
//!   `final_loss_approx_total` subtracts retry successes as a conservative
//!   operator-facing approximation, while `retry_fail_total` remains the direct
//!   fill-completion retry-exhausted counter.

use super::super::*;
use crate::agent_spine::runtime_shadow::{
    spine_channel_drop_total, spine_channel_retry_fail_total, spine_channel_retry_success_total,
};

/// `get_agent_spine_channel_metrics` IPC — return process-wide channel counters.
pub(in crate::ipc_server) async fn handle_get_agent_spine_channel_metrics(
    id: serde_json::Value,
) -> JsonRpcResponse {
    let drop_total = spine_channel_drop_total();
    let retry_success_total = spine_channel_retry_success_total();
    let retry_fail_total = spine_channel_retry_fail_total();
    let final_loss_approx_total = drop_total.saturating_sub(retry_success_total);

    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "drop_total": drop_total,
            "retry_success_total": retry_success_total,
            "retry_fail_total": retry_fail_total,
            "final_loss_approx_total": final_loss_approx_total,
            "drop_total_semantics": "initial_try_send_failures_not_final_loss",
            "warn_threshold_initial_fail_per_min": 5.0,
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn channel_metrics_returns_stable_shape() {
        let resp = handle_get_agent_spine_channel_metrics(serde_json::json!(55)).await;

        assert!(resp.error.is_none());
        assert_eq!(resp.id, serde_json::json!(55));
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "ok");
        assert!(r["drop_total"].as_u64().is_some());
        assert!(r["retry_success_total"].as_u64().is_some());
        assert!(r["retry_fail_total"].as_u64().is_some());
        assert!(r["final_loss_approx_total"].as_u64().is_some());
        assert_eq!(
            r["drop_total_semantics"],
            "initial_try_send_failures_not_final_loss"
        );
    }
}
