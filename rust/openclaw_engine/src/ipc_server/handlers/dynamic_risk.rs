//! DYNAMIC-RISK-1 IPC handlers: per-engine Sharpe-aware sizer status read and
//! runtime enable/disable toggle.
//!
//! MODULE_NOTE (EN): Split out of `handlers.rs` in E5-P1-3. Routes through the
//!   selected engine's command channel — `extract_engine_tx` resolution lives
//!   in `ipc_server/mod.rs` and feeds the `pipeline_cmd_tx` argument here.
//!   Toggle is transient: the next TOML hot-reload restores the file's intent.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分後的「動態風險」桶。
//!   透過所選引擎的命令通道發命令；切換屬運行時臨時覆蓋，下次 TOML 熱重載
//!   會還原檔案意圖。

use super::super::*;

/// DYNAMIC-RISK-1: Per-engine Sharpe-aware sizer status snapshot.
/// Routes the call through the selected engine's command channel (same
/// `extract_engine_tx` path as every other per-engine RPC).
/// DYNAMIC-RISK-1：按引擎取動態風險調整器狀態快照。
pub(in crate::ipc_server) async fn handle_get_dynamic_risk_status(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                "engine command channel not configured",
            )
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetDynamicRiskStatus {
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

/// DYNAMIC-RISK-1: Runtime toggle of the per-engine sizer.
/// Transient override — the next TOML hot-reload restores the file's intent.
/// DYNAMIC-RISK-1：運行時切換；下次 TOML 熱重載會還原。
pub(in crate::ipc_server) async fn handle_set_dynamic_risk_enabled(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                "engine command channel not configured",
            )
        }
    };
    let enabled = match params.get("enabled").and_then(|v| v.as_bool()) {
        Some(v) => v,
        None => {
            return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing or non-bool `enabled`")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::SetDynamicRiskEnabled {
        enabled,
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
