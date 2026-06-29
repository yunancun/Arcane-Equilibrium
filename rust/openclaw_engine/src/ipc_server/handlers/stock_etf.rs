//! ADR-0048 Stock/ETF lane IPC fixtures.
//!
//! Phase 1 only: these handlers expose lane status/readiness and typed denial
//! previews. They intentionally do not send `PipelineCommand`, do not reuse the
//! Bybit `submit_paper_order` path, and do not contact IBKR.

use super::super::*;
use openclaw_types::{
    evaluate_broker_operation, AssetLane, Broker, BrokerCapabilityRequest, BrokerEnvironment,
    BrokerOperation, IbkrExternalSurfaceGateV1, IbkrPhase2PolicyBundleV1, InstrumentKind,
    StockEtfFeatureFlags, StockEtfGateInputs,
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
    let phase2 = phase2_precontact_summary();

    match method {
        "stock_etf.get_lane_status" => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "phase": "phase2_precontact_source_fixture",
                "asset_lane": AssetLane::StockEtfCash,
                "broker": Broker::Ibkr,
                "default_asset_lane": flags.asset_lane_default,
                "flags": flags,
                "phase2": phase2,
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
                "phase": "phase2_precontact_source_fixture",
                "readiness": flags.readiness(),
                "phase2": phase2,
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
                    "phase2": phase2,
                    "ibkr_call_performed": false,
                    "secret_slot_touched": false,
                    "order_routed": false,
                    "bybit_ipc_reused": false,
                }),
            )
        }
    }
}

fn phase2_precontact_summary() -> serde_json::Value {
    let policy_bundle = IbkrPhase2PolicyBundleV1::source_template();
    let policy_verdict = policy_bundle.validate();
    let policy_flags = policy_bundle.gate_prerequisite_flags();
    let gate = IbkrExternalSurfaceGateV1 {
        api_allowlist_present: true,
        redaction_suite_passed: policy_flags.redaction_suite_passed,
        rate_limit_policy_present: policy_flags.rate_limit_policy_present,
        audit_event_policy_present: policy_flags.audit_event_policy_present,
        paper_attestation_contract_present: policy_flags.paper_attestation_contract_present,
        python_no_write_guard_present: policy_flags.python_no_write_guard_present,
        ibkr_call_performed: false,
        ..IbkrExternalSurfaceGateV1::default()
    };
    let gate_verdict = gate.validate();

    serde_json::json!({
        "external_surface_gate": {
            "status": gate.status,
            "ibkr_contact_allowed": gate_verdict.ibkr_contact_allowed,
            "blockers": gate_verdict.blockers,
            "ibkr_call_performed": gate.ibkr_call_performed,
        },
        "policy_prerequisites": {
            "bundle_accepted": policy_verdict.accepted,
            "blockers": policy_verdict.blockers,
            "flags": policy_flags,
        },
        "immutable_pass_artifact_present": false,
        "first_ibkr_contact_allowed": false,
        "connector_enabled": false,
        "secret_slot_touched": false,
        "order_routed": false,
    })
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
