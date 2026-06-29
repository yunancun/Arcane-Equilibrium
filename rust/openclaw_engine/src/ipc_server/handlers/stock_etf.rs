//! ADR-0048 Stock/ETF lane IPC fixtures.
//!
//! Phase 1 only: these handlers expose lane status/readiness and typed denial
//! previews. They intentionally do not send `PipelineCommand`, do not reuse the
//! Bybit `submit_paper_order` path, and do not contact IBKR.

use super::super::*;
use openclaw_types::{
    evaluate_broker_operation, AssetLane, Broker, BrokerCapabilityRequest, BrokerEnvironment,
    BrokerOperation, InstrumentKind, StockEtfFeatureFlags, StockEtfGateInputs,
};

pub(in crate::ipc_server) fn handle_stock_etf_ipc(
    id: serde_json::Value,
    method: &str,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let flags = match StockEtfFeatureFlags::from_env() {
        Ok(flags) => flags,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                format!("stock_etf_config_invalid: {e}"),
            )
        }
    };

    match method {
        "stock_etf.get_lane_status" => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "phase": "phase1_source_foundation",
                "asset_lane": AssetLane::StockEtfCash,
                "broker": Broker::Ibkr,
                "default_asset_lane": flags.asset_lane_default,
                "flags": flags,
                "ibkr_live_enabled": false,
                "ibkr_call_performed": false,
                "secret_slot_touched": false,
                "order_routed": false,
                "bybit_ipc_reused": false,
            }),
        ),
        "stock_etf.get_readiness" => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "phase": "phase1_source_foundation",
                "readiness": flags.readiness(),
                "ibkr_live_enabled": false,
                "ibkr_call_performed": false,
                "secret_slot_touched": false,
                "order_routed": false,
                "bybit_ipc_reused": false,
            }),
        ),
        _ => {
            let operation = match operation_for_method(method) {
                Some(op) => op,
                None => {
                    return JsonRpcResponse::error(
                        id,
                        ERR_INVALID_REQUEST,
                        format!("stock_etf_method_not_fixture_enabled: {method}"),
                    )
                }
            };
            let request = match request_from_params(params, operation) {
                Ok(request) => request,
                Err(e) => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e),
            };
            let gates = StockEtfGateInputs::default();
            let decision = evaluate_broker_operation(request, &flags, &gates);
            let allowed = decision.allowed;
            let denial_reason = decision.denial_reason;
            JsonRpcResponse::success(
                id,
                serde_json::json!({
                    "phase": "phase1_ipc_fixture",
                    "method": method,
                    "decision": decision,
                    "allowed": allowed,
                    "denial_reason": denial_reason,
                    "ibkr_call_performed": false,
                    "secret_slot_touched": false,
                    "order_routed": false,
                    "bybit_ipc_reused": false,
                }),
            )
        }
    }
}

fn operation_for_method(method: &str) -> Option<BrokerOperation> {
    match method {
        "stock_etf.preview_paper_order" => Some(BrokerOperation::PaperOrderSubmit),
        "stock_etf.submit_paper_order" => Some(BrokerOperation::PaperOrderSubmit),
        "stock_etf.cancel_paper_order" => Some(BrokerOperation::PaperOrderCancel),
        "stock_etf.replace_paper_order" => Some(BrokerOperation::PaperOrderReplace),
        "stock_etf.import_paper_fills" => Some(BrokerOperation::PaperOrderFillImport),
        "stock_etf.evaluate_shadow_signal" => Some(BrokerOperation::ShadowSignalEmit),
        _ => None,
    }
}

fn request_from_params(
    params: &serde_json::Value,
    operation: BrokerOperation,
) -> Result<BrokerCapabilityRequest, String> {
    let asset_lane = parse_param(params, "asset_lane", AssetLane::StockEtfCash)?;
    let broker = parse_param(params, "broker", Broker::Ibkr)?;
    let environment_default = if operation.is_shadow() {
        BrokerEnvironment::Shadow
    } else if operation.is_read() {
        BrokerEnvironment::ReadOnly
    } else {
        BrokerEnvironment::Paper
    };
    let environment = parse_param(params, "environment", environment_default)?;
    let instrument_kind = parse_param(params, "instrument_kind", InstrumentKind::Stock)?;

    Ok(BrokerCapabilityRequest {
        asset_lane,
        broker,
        environment,
        instrument_kind,
        operation,
    })
}

fn parse_param<T>(params: &serde_json::Value, key: &'static str, default: T) -> Result<T, String>
where
    T: std::str::FromStr,
    T::Err: std::fmt::Display,
{
    match params.get(key).and_then(|v| v.as_str()) {
        Some(raw) => raw.parse::<T>().map_err(|e| format!("invalid {key}: {e}")),
        None => Ok(default),
    }
}
