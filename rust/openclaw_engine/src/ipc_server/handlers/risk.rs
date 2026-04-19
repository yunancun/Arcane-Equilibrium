//! Risk-config IPC handlers: live hot-patch of 21 risk parameters, runtime
//! status snapshot, and the safe per-symbol consecutive-loss counter reset.
//!
//! MODULE_NOTE (EN): Split out of `handlers.rs` in E5-P1-3. These handlers are
//!   pure JSON parsers + `PipelineCommand` senders; all clamping / validation
//!   lives on the event-consumer side so a single source of truth governs the
//!   numeric bounds. `parse_opt_opt_f64` is a private helper used only by
//!   `handle_update_risk_config` and stays file-local.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分後的「風控」桶。
//!   三個 handler 僅負責 JSON 解析與 PipelineCommand 發送；所有 clamp 與
//!   驗證邏輯均在事件消費者側，確保單一真理源。`parse_opt_opt_f64` 為
//!   `handle_update_risk_config` 獨用的檔案內私有輔助。

use super::super::*;

/// Update risk config at runtime (GUI → Python → IPC → Rust engine).
/// 運行時更新風控配置。
/// Parse Option<Option<f64>> from JSON: absent=None, null=Some(None), number=Some(Some(x)).
/// 解析 JSON 中的 Option<Option<f64>>：不存在=None，null=Some(None)，數字=Some(Some(x))。
fn parse_opt_opt_f64(params: &serde_json::Value, key: &str) -> Option<Option<f64>> {
    match params.get(key) {
        None => None,                         // key absent = no change
        Some(v) if v.is_null() => Some(None), // key: null = disable
        Some(v) => v.as_f64().map(Some),      // key: 2.5 = enable with value
    }
}

pub(in crate::ipc_server) async fn handle_update_risk_config(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "no paper command channel".to_string())
        }
    };

    // Parse all risk params / 解析所有風控參數
    let hard_stop_pct = params.get("hard_stop_pct").and_then(|v| v.as_f64());
    let p1_risk_pct = params.get("p1_risk_pct").and_then(|v| v.as_f64());
    let trailing_stop_pct = parse_opt_opt_f64(params, "trailing_stop_pct");
    let trailing_activation_pct = parse_opt_opt_f64(params, "trailing_activation_pct");
    let time_stop_hours = parse_opt_opt_f64(params, "time_stop_hours");
    let atr_multiplier = parse_opt_opt_f64(params, "atr_multiplier");
    let take_profit_pct = parse_opt_opt_f64(params, "take_profit_pct");
    let max_leverage = params.get("max_leverage").and_then(|v| v.as_f64());
    let max_drawdown_pct = params.get("max_drawdown_pct").and_then(|v| v.as_f64());
    let max_same_direction_positions = params
        .get("max_same_direction_positions")
        .and_then(|v| v.as_u64())
        .map(|v| v as usize);
    // RRC-1-A3: H0Gate shadow mode toggle / H0 門控影子模式切換
    let h0_shadow_mode = params.get("h0_shadow_mode").and_then(|v| v.as_bool());
    // PNL-7: agent-tunable dynamic-stop knobs / PNL-7：Agent 可調動態止損參數
    let dynamic_stop_base_ratio = params
        .get("dynamic_stop_base_ratio")
        .and_then(|v| v.as_f64());
    let dynamic_stop_cap_ratio = params
        .get("dynamic_stop_cap_ratio")
        .and_then(|v| v.as_f64());
    let trailing_min_rr_ratio = params.get("trailing_min_rr_ratio").and_then(|v| v.as_f64());
    // Session 12: cost-gate + regime + boot cooldown
    let cost_gate_min_confidence = params
        .get("cost_gate_min_confidence")
        .and_then(|v| v.as_f64());
    let cost_gate_k_base = params.get("cost_gate_k_base").and_then(|v| v.as_f64());
    let cost_gate_k_medium = params.get("cost_gate_k_medium").and_then(|v| v.as_f64());
    let cost_gate_k_small = params.get("cost_gate_k_small").and_then(|v| v.as_f64());
    let adx_trending_threshold = params
        .get("adx_trending_threshold")
        .and_then(|v| v.as_f64());
    let boot_cooldown_ms = params.get("boot_cooldown_ms").and_then(|v| v.as_u64());
    let signals_heartbeat_ms = params.get("signals_heartbeat_ms").and_then(|v| v.as_u64());

    // At least one param must be provided / 至少需要一個參數
    let has_any = hard_stop_pct.is_some()
        || p1_risk_pct.is_some()
        || trailing_stop_pct.is_some()
        || trailing_activation_pct.is_some()
        || time_stop_hours.is_some()
        || atr_multiplier.is_some()
        || take_profit_pct.is_some()
        || max_leverage.is_some()
        || max_drawdown_pct.is_some()
        || max_same_direction_positions.is_some()
        || h0_shadow_mode.is_some()
        || dynamic_stop_base_ratio.is_some()
        || dynamic_stop_cap_ratio.is_some()
        || trailing_min_rr_ratio.is_some()
        || cost_gate_min_confidence.is_some()
        || cost_gate_k_base.is_some()
        || cost_gate_k_medium.is_some()
        || cost_gate_k_small.is_some()
        || adx_trending_threshold.is_some()
        || boot_cooldown_ms.is_some()
        || signals_heartbeat_ms.is_some();
    if !has_any {
        return JsonRpcResponse::error(
            id,
            ERR_INVALID_REQUEST,
            "need at least one risk parameter".to_string(),
        );
    }

    let _ = tx.send(PipelineCommand::UpdateRiskConfig {
        hard_stop_pct,
        trailing_stop_pct,
        trailing_activation_pct,
        time_stop_hours,
        atr_multiplier,
        take_profit_pct,
        max_leverage,
        max_drawdown_pct,
        max_same_direction_positions,
        p1_risk_pct,
        h0_shadow_mode,
        dynamic_stop_base_ratio,
        dynamic_stop_cap_ratio,
        trailing_min_rr_ratio,
        cost_gate_min_confidence,
        cost_gate_k_base,
        cost_gate_k_medium,
        cost_gate_k_small,
        adx_trending_threshold,
        boot_cooldown_ms,
        signals_heartbeat_ms,
    });
    JsonRpcResponse::success(id, serde_json::json!({ "updated": true }))
}

/// ARCH-RC1 1C-3-B: Get Rust-native risk runtime status snapshot.
/// Routes the call through the paper command channel so the response is
/// built from live `TickPipeline` state owned by the event consumer task.
/// ARCH-RC1 1C-3-B：獲取 Rust 原生風控運行時狀態快照。
pub(in crate::ipc_server) async fn handle_risk_runtime_status(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetRiskRuntimeStatus {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(v) => JsonRpcResponse::success(id, v),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse status: {e}")),
        },
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-B: Clear per-symbol consecutive-loss counters (safe reset,
/// does NOT touch RiskGovernor tier — for governor override see 1C-3-B-2).
/// ARCH-RC1 1C-3-B：清除 per-symbol 連虧計數器（安全重置，不影響 governor tier）。
pub(in crate::ipc_server) async fn handle_clear_consecutive_losses(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ClearConsecutiveLosses {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(msg))) => JsonRpcResponse::success(id, serde_json::json!({ "result": msg })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// P1-5 A2: operator-driven drawdown baseline reset. Sends
/// `PipelineCommand::ResetDrawdownBaseline` to the per-engine consumer and
/// awaits the oneshot reply (fires AFTER the in-memory reset + DB
/// `paper_state_checkpoint` DELETE). Timeout matches the other risk IPC
/// handlers (5s) so a stuck event loop surfaces as an explicit IPC error
/// instead of a silently-hung HTTP request.
///
/// Per Root Principle #5 (生存>利潤): this IPC is the ONLY legitimate way to
/// lower `peak_balance` at runtime; the Python FastAPI route fronting it MUST
/// attach operator auth + a `change_audit_log` row (Root Principle #8).
///
/// P1-5 A2：operator 手動重置 drawdown 基準。發送 ResetDrawdownBaseline、
/// 等待 oneshot 回覆（於記憶體重置 + DB DELETE 完成後觸發），5s 超時與其他
/// 風控 IPC 對齊。根原則 #5：此 IPC 是 runtime 唯一合法降低 peak_balance
/// 的路徑；Python 路由須附加 operator 授權 + change_audit_log（根原則 #8）。
pub(in crate::ipc_server) async fn handle_reset_drawdown_baseline(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ResetDrawdownBaseline {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(msg))) => JsonRpcResponse::success(id, serde_json::json!({ "result": msg })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}
