//! G3-09 cost_edge_advisor IPC handler — single method `get_cost_edge_advisor_status`.
//! G3-09 cost_edge_advisor IPC handler — 單一 method `get_cost_edge_advisor_status`.
//!
//! MODULE_NOTE (EN): Phase A advisory-only IPC. Returns the current advisor
//!   state snapshot (or a structured `advisor_disabled` payload when the
//!   env-gate is off / advisor not injected). Mirrors the
//!   `handle_get_h_state_status` shape so downstream consumers (healthcheck
//!   [22], GUI) follow the same status-string branch pattern.
//!
//!   Per CLAUDE.md §二 #2 read-write separation: this handler is purely
//!   read-only, no side effects on RiskConfig / advisor state / DB.
//!
//! MODULE_NOTE (中)：Phase A 純 advisory IPC。回當前 advisor state snapshot
//!   （或 env-gate 關 / advisor 未注入時回結構化 `advisor_disabled` payload），
//!   對齊 `handle_get_h_state_status` shape，方便下游（healthcheck [22] / GUI）
//!   走同樣 status-string 分支。
//!
//!   CLAUDE.md §二 #2 讀寫分離：本 handler 純唯讀，不對 RiskConfig /
//!   advisor state / DB 產生任何 side-effect。

use super::super::slots::CostEdgeAdvisorSlot;
use super::super::*;
use crate::cost_edge_advisor::is_advisor_env_enabled;

/// `get_cost_edge_advisor_status` IPC — return current advisor state snapshot.
/// Fail-soft when env-gate disabled or advisor uninjected.
/// `get_cost_edge_advisor_status` IPC — 回當前 advisor state snapshot。
/// env-gate 關 / advisor 未注入時 fail-soft。
pub(in crate::ipc_server) async fn handle_get_cost_edge_advisor_status(
    id: serde_json::Value,
    advisor_slot: &CostEdgeAdvisorSlot,
) -> JsonRpcResponse {
    let guard = advisor_slot.read().await;
    let advisor = match guard.as_ref() {
        Some(a) => a,
        None => {
            // env=0 or advisor not yet injected — return structured disabled
            // shape so Python healthcheck [22] can branch on `status` field.
            // env=0 或 advisor 未注入 — 回結構化 disabled shape 讓 Python
            // healthcheck [22] 用 status 分支。
            return advisor_disabled_response(id, "advisor not injected (env=0 or pre-spawn)");
        }
    };
    let state = advisor.state();
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": state.status.as_str(),
            "ratio": state.ratio,
            "threshold": state.threshold,
            "data_days": state.data_days,
            "ai_spend_7d_usd": state.ai_spend_7d_usd,
            "paper_pnl_7d_usd": state.paper_pnl_7d_usd,
            "last_eval_ms": state.last_eval_ms,
            "triggered_at_ms": state.triggered_at_ms,
            "env_enabled": is_advisor_env_enabled(),
            // Phase B advancement: phase string flips to "B_shadow" so
            // downstream consumers (healthcheck [30] Phase B impl, GUI)
            // can branch on advisor maturity. The `phase` slot is
            // forward-compat — Phase C will write "C_gated".
            // Phase B 推進：phase 字串翻 "B_shadow"，下游 consumer
            // （healthcheck [30] Phase B 版、GUI）可依此判斷 advisor 成熟度。
            "phase": "B_shadow",
            // Phase B (G3-09 2026-04-28) observability counters maintained
            // by the daemon. `last_trigger_ms` survives Trigger exit (vs
            // `triggered_at_ms` which resets to 0); `dryrun_observation_window_ms`
            // tells consumers how warm the rolling counters are.
            // Phase B observability 計數，由 daemon 維護。`last_trigger_ms`
            // 在退出 Trigger 後仍保留（vs `triggered_at_ms` 清 0）；
            // `dryrun_observation_window_ms` 告訴 consumer rolling counter 已熱多久。
            "evaluations_24h": state.evaluations_24h,
            "triggers_24h": state.triggers_24h,
            "last_trigger_ms": state.last_trigger_ms,
            "dryrun_observation_window_ms": state.dryrun_observation_window_ms,
        }),
    )
}

/// Standard payload returned when the advisor is disabled / uninjected.
/// `status` field stable so Python callers can branch.
/// advisor 關 / 未注入時回的標準 payload；`status` 欄位穩定供 Python 分支。
fn advisor_disabled_response(id: serde_json::Value, note: &str) -> JsonRpcResponse {
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "Uninitialized",
            "ratio": serde_json::Value::Null,
            "threshold": 0.0,
            "data_days": 0,
            "ai_spend_7d_usd": 0.0,
            "paper_pnl_7d_usd": 0.0,
            "last_eval_ms": 0,
            "triggered_at_ms": 0,
            "env_enabled": false,
            // Phase B disabled stub mirrors live shape `phase: "B_shadow"`
            // so consumers branch identically. All Phase B counters are 0
            // because the daemon never spawned.
            // Phase B disabled stub 鏡射 live shape `phase: "B_shadow"`
            // 讓 consumer 分支一致；Phase B 計數全 0（daemon 未 spawn）。
            "phase": "B_shadow",
            "evaluations_24h": 0,
            "triggers_24h": 0,
            "last_trigger_ms": 0,
            "dryrun_observation_window_ms": 0,
            "note": note,
        }),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::cost_edge_advisor::types::CostEdgeAdvisorState;
    use crate::cost_edge_advisor::CostEdgeAdvisor;
    use std::sync::Arc;
    use tokio::sync::RwLock;

    fn empty_slot() -> CostEdgeAdvisorSlot {
        Arc::new(RwLock::new(None))
    }

    fn populated_slot(state: CostEdgeAdvisorState) -> CostEdgeAdvisorSlot {
        let advisor = CostEdgeAdvisor::new_arc();
        advisor.store_state(state);
        Arc::new(RwLock::new(Some(advisor)))
    }

    #[tokio::test]
    async fn status_uninjected_returns_disabled_shape() {
        let slot = empty_slot();
        let resp = handle_get_cost_edge_advisor_status(serde_json::json!(1), &slot).await;
        assert!(resp.error.is_none());
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "Uninitialized");
        assert_eq!(r["env_enabled"], false);
        // Phase B (G3-09 2026-04-28): phase string flipped from "A_advisory"
        // to "B_shadow". 4 new observability counters are all 0 in disabled stub.
        // Phase B（G3-09 2026-04-28）：phase 字串從 "A_advisory" 翻 "B_shadow"；
        // disabled stub 下 4 新 observability counter 全 0。
        assert_eq!(r["phase"], "B_shadow");
        assert_eq!(r["evaluations_24h"].as_u64(), Some(0));
        assert_eq!(r["triggers_24h"].as_u64(), Some(0));
        assert_eq!(r["last_trigger_ms"].as_i64(), Some(0));
        assert_eq!(r["dryrun_observation_window_ms"].as_i64(), Some(0));
        assert!(r["note"].as_str().is_some());
    }

    #[tokio::test]
    async fn status_injected_returns_advisor_state() {
        let slot = populated_slot(CostEdgeAdvisorState::ok(0.7, -0.5, 7, 5.0, 3.5, 1_700_000_000_000));
        let resp = handle_get_cost_edge_advisor_status(serde_json::json!(2), &slot).await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "OK");
        assert_eq!(r["ratio"].as_f64(), Some(0.7));
        assert_eq!(r["threshold"].as_f64(), Some(-0.5));
        assert_eq!(r["data_days"].as_u64(), Some(7));
    }

    #[tokio::test]
    async fn status_injected_trigger_serializes_correctly() {
        let slot = populated_slot(CostEdgeAdvisorState::trigger(
            -1.5,
            -0.5,
            7,
            5.0,
            -7.5,
            1_700_000_000_000,
            1_700_000_001_000,
        ));
        let resp = handle_get_cost_edge_advisor_status(serde_json::json!(3), &slot).await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "Trigger");
        assert_eq!(r["ratio"].as_f64(), Some(-1.5));
        assert_eq!(r["triggered_at_ms"].as_i64(), Some(1_700_000_001_000));
    }

    #[tokio::test]
    async fn status_anomaly_state_round_trips() {
        let slot = populated_slot(CostEdgeAdvisorState::anomaly(
            f64::NAN,
            -0.5,
            1_700_000_000_000,
        ));
        let resp = handle_get_cost_edge_advisor_status(serde_json::json!(4), &slot).await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "Anomaly");
    }

    #[tokio::test]
    async fn status_warm_up_state_round_trips() {
        let slot = populated_slot(CostEdgeAdvisorState::warm_up(-0.5, 2, 1_700_000_000_000));
        let resp = handle_get_cost_edge_advisor_status(serde_json::json!(5), &slot).await;
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "WarmUp");
        assert!(r["ratio"].is_null());
        assert_eq!(r["data_days"].as_u64(), Some(2));
    }
}
