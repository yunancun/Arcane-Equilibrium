//! Strategy IPC handlers: parameter CRUD (Update/Get/Ranges), strategy
//! active/pause flip, and the external paper-side order submit entry.
//!
//! MODULE_NOTE (EN): Split out of `handlers.rs` in E5-P1-3. Each handler is a
//!   thin JSON → `PipelineCommand` translator that routes through the paper
//!   command channel and awaits a oneshot reply with a 3-5s timeout. The
//!   `StrategyParamOp` enum is kept `pub(in crate::ipc_server)` so
//!   `dispatch_request` in mod.rs can construct the right variant per method.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分後的「策略」桶。
//!   所有 handler 皆為「解析 JSON → 發 PipelineCommand → 等 oneshot」的薄
//!   轉譯層；`StrategyParamOp` 對 `ipc_server` 模組可見，供 dispatch_request
//!   構造正確的命令變體。

use super::super::*;

/// Strategy parameter operation type / 策略參數操作類型
pub(in crate::ipc_server) enum StrategyParamOp {
    Update,
    Get,
    Ranges,
}

/// Handle strategy parameter commands — sends oneshot request to event consumer.
/// 處理策略參數命令 — 發送 oneshot 請求到事件消費者。
pub(in crate::ipc_server) async fn handle_strategy_param_cmd(
    id: serde_json::Value,
    tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
    op: StrategyParamOp,
) -> JsonRpcResponse {
    let tx = match tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };

    let strategy_name = match params.get("strategy_name").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing strategy_name parameter",
            )
        }
    };

    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();

    let cmd = match op {
        StrategyParamOp::Update => {
            let params_json = match params.get("params_json").and_then(|v| v.as_str()) {
                Some(s) => s.to_string(),
                None => {
                    // Also accept params_json as an object and serialize it
                    // 也接受 params_json 作為對象並序列化
                    match params.get("params_json") {
                        Some(v) if v.is_object() => serde_json::to_string(v).unwrap_or_default(),
                        _ => {
                            return JsonRpcResponse::error(
                                id,
                                ERR_INVALID_REQUEST,
                                "missing params_json parameter",
                            )
                        }
                    }
                }
            };
            PipelineCommand::UpdateStrategyParams {
                strategy_name,
                params_json,
                response_tx: resp_tx,
            }
        }
        StrategyParamOp::Get => PipelineCommand::GetStrategyParams {
            strategy_name,
            response_tx: resp_tx,
        },
        StrategyParamOp::Ranges => PipelineCommand::GetParamRanges {
            strategy_name,
            response_tx: resp_tx,
        },
    };

    if let Err(e) = tx.send(cmd) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }

    // Await response with timeout (5s) / 等待回應（5 秒超時）
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(result))) => JsonRpcResponse::success(id, serde_json::json!({ "result": result })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// RRC-1-E2: Set strategy active/paused via IPC / 通過 IPC 設置策略啟停。
pub(in crate::ipc_server) async fn handle_set_strategy_active(
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
    let name = match params.get("strategy_name").and_then(|v| v.as_str()) {
        Some(n) => n.to_string(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing strategy_name".to_string(),
            )
        }
    };
    let active = match params.get("active").and_then(|v| v.as_bool()) {
        Some(a) => a,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing active (bool)".to_string(),
            )
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    let _ = tx.send(PipelineCommand::SetStrategyActive {
        strategy_name: name,
        active,
        response_tx: resp_tx,
    });
    match tokio::time::timeout(std::time::Duration::from_secs(3), resp_rx).await {
        Ok(Ok(Ok(msg))) => {
            JsonRpcResponse::success(id, serde_json::json!({ "ok": true, "detail": msg }))
        }
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "channel closed".to_string()),
        Err(_) => {
            JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for engine".to_string())
        }
    }
}

/// ARCH-RC1 1C-3-F: External paper-side order submission. Drives the same
/// IntentProcessor pipeline strategies use (Guardian / Kelly / P1 cap / risk
/// gate / cost gate). On success returns the JSON envelope produced by
/// `TickPipeline::submit_external_order`.
/// ARCH-RC1 1C-3-F：外部紙盤訂單入口 — 與策略走同一條 IntentProcessor 管線。
pub(in crate::ipc_server) async fn handle_submit_paper_order(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let symbol = match params.get("symbol").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing symbol"),
    };
    let side = match params.get("side").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing side"),
    };
    let qty = match params.get("qty").and_then(|v| v.as_f64()) {
        Some(q) if q > 0.0 => q,
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/invalid qty"),
    };
    let order_type = params
        .get("order_type")
        .and_then(|v| v.as_str())
        .unwrap_or("market")
        .to_string();
    let limit_price = params.get("limit_price").and_then(|v| v.as_f64());
    let confidence = params
        .get("confidence")
        .and_then(|v| v.as_f64())
        .unwrap_or(1.0);
    let strategy = params
        .get("strategy")
        .and_then(|v| v.as_str())
        .unwrap_or("external")
        .to_string();

    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::SubmitOrder {
        symbol,
        side,
        qty,
        order_type,
        limit_price,
        confidence,
        strategy,
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(v) => JsonRpcResponse::success(id, v),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse envelope: {e}")),
        },
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}
