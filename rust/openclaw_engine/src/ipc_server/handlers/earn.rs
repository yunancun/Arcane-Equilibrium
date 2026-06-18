//! Earn IPC handlers.
//!
//! `process_earn_intent` is a thin JSON-RPC to `PipelineCommand` bridge. The
//! actual asset-movement gate sequence stays inside the per-pipeline owner task
//! (`IntentProcessor::process_earn_intent`), not in the IPC server.

use super::super::*;

fn required_string(
    id: &serde_json::Value,
    params: &serde_json::Value,
    key: &str,
) -> Result<String, JsonRpcResponse> {
    match params.get(key).and_then(|v| v.as_str()) {
        Some(value) if !value.trim().is_empty() => Ok(value.to_string()),
        _ => Err(JsonRpcResponse::error(
            id.clone(),
            ERR_INVALID_REQUEST,
            format!("missing/invalid {key}"),
        )),
    }
}

fn required_i32(
    id: &serde_json::Value,
    params: &serde_json::Value,
    key: &str,
) -> Result<i32, JsonRpcResponse> {
    match params.get(key).and_then(|v| v.as_i64()) {
        Some(value) if value >= i32::MIN as i64 && value <= i32::MAX as i64 => Ok(value as i32),
        _ => Err(JsonRpcResponse::error(
            id.clone(),
            ERR_INVALID_REQUEST,
            format!("missing/invalid {key}"),
        )),
    }
}

fn required_u64(
    id: &serde_json::Value,
    params: &serde_json::Value,
    key: &str,
) -> Result<u64, JsonRpcResponse> {
    match params.get(key).and_then(|v| v.as_u64()) {
        Some(value) => Ok(value),
        _ => Err(JsonRpcResponse::error(
            id.clone(),
            ERR_INVALID_REQUEST,
            format!("missing/invalid {key}"),
        )),
    }
}

pub(in crate::ipc_server) async fn handle_process_earn_intent(
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
                "pipeline command channel not configured",
            )
        }
    };

    let coin = match required_string(&id, params, "coin") {
        Ok(value) => value,
        Err(resp) => return resp,
    };
    let product_id = match required_string(&id, params, "product_id") {
        Ok(value) => value,
        Err(resp) => return resp,
    };
    let amount_usdt = match required_string(&id, params, "amount_usdt") {
        Ok(value) => value,
        Err(resp) => return resp,
    };
    let expected_apr_bps = match required_i32(&id, params, "expected_apr_bps") {
        Ok(value) => value,
        Err(resp) => return resp,
    };
    let rationale = match required_string(&id, params, "rationale") {
        Ok(value) => value,
        Err(resp) => return resp,
    };
    let actor_id = match required_string(&id, params, "actor_id") {
        Ok(value) => value,
        Err(resp) => return resp,
    };
    let submitted_ts_ms = match required_u64(&id, params, "submitted_ts_ms") {
        Ok(value) => value,
        Err(resp) => return resp,
    };
    let trace_id = match required_string(&id, params, "trace_id") {
        Ok(value) => value,
        Err(resp) => return resp,
    };

    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ProcessEarnIntent {
        coin,
        product_id,
        amount_usdt,
        expected_apr_bps,
        rationale,
        actor_id,
        submitted_ts_ms,
        trace_id,
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }

    match tokio::time::timeout(std::time::Duration::from_secs(12), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(value) => JsonRpcResponse::success(id, value),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse envelope: {e}")),
        },
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}
