//! ADR-0048 Stock/ETF lane IPC fixtures.
//!
//! Phase 1 only: these handlers expose lane status/readiness and typed denial
//! previews. They intentionally do not send `PipelineCommand`, do not reuse the
//! Bybit `submit_paper_order` path, and do not contact IBKR.

use super::super::*;
use openclaw_types::{
    evaluate_broker_operation, AssetLane, Broker, BrokerCapabilityRequest, BrokerEnvironment,
    BrokerOperation, IbkrExternalSurfaceGateV1, IbkrPhase2PolicyBundleV1, InstrumentKind,
    NonBybitApiAllowlistV1, StockEtfEvidenceClockDayV1, StockEtfFeatureFlags, StockEtfGateInputs,
    StockMarketDataProvenanceV1, STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
    STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
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
        "stock_etf.get_evidence_status" => {
            JsonRpcResponse::success(id, evidence_status_summary(phase2))
        }
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

fn evidence_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let market_data_provenance = StockMarketDataProvenanceV1::default();
    let market_data_verdict = market_data_provenance.validate();
    let evidence_clock_day = StockEtfEvidenceClockDayV1::default();
    let evidence_clock_verdict = evidence_clock_day.validate();
    let frozen_inputs_verdict = evidence_clock_day.frozen_inputs.validate();
    let dq_shape_verdict = evidence_clock_day.dq_manifest.validates_shape();

    serde_json::json!({
        "phase": "phase3_evidence_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "evidence_status_state": "blocked",
        "phase3_started": false,
        "market_data_provenance": {
            "expected_contract_id": STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
            "contract_id": market_data_provenance.contract_id,
            "source_version": market_data_provenance.source_version,
            "accepted": market_data_verdict.accepted,
            "blockers": market_data_verdict.blockers,
            "ibkr_contact_performed": market_data_provenance.ibkr_contact_performed,
            "connector_runtime_started": market_data_provenance.connector_runtime_started,
            "secret_content_serialized": market_data_provenance.secret_content_serialized,
            "live_or_tiny_live_authorized": market_data_provenance.live_or_tiny_live_authorized,
        },
        "evidence_clock": {
            "expected_contract_id": STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
            "contract_id": evidence_clock_day.contract_id,
            "source_version": evidence_clock_day.source_version,
            "status": evidence_clock_day.status,
            "accepted": evidence_clock_verdict.accepted,
            "blockers": evidence_clock_verdict.blockers,
            "checker_contacted_ibkr": evidence_clock_day.checker_contacted_ibkr,
            "checker_started_connector_runtime": evidence_clock_day.checker_started_connector_runtime,
            "checker_started_evidence_clock": evidence_clock_day.checker_started_evidence_clock,
            "checker_wrote_scorecard": evidence_clock_day.checker_wrote_scorecard,
            "checker_applied_db": evidence_clock_day.checker_applied_db,
            "secret_content_serialized": evidence_clock_day.secret_content_serialized,
            "live_or_tiny_live_authorized": evidence_clock_day.live_or_tiny_live_authorized,
            "ibkr_readonly_paper_connector_green_5d": evidence_clock_day.ibkr_readonly_paper_connector_green_5d,
            "shadow_collector_green_5d": evidence_clock_day.shadow_collector_green_5d,
        },
        "frozen_inputs": {
            "accepted": frozen_inputs_verdict.accepted,
            "blockers": frozen_inputs_verdict.blockers,
            "universe_hash_present": !evidence_clock_day.frozen_inputs.universe_hash.is_empty(),
            "benchmark_hash_present": !evidence_clock_day.frozen_inputs.benchmark_hash.is_empty(),
            "cost_model_hash_present": !evidence_clock_day.frozen_inputs.cost_model_hash.is_empty(),
            "strategy_hypothesis_hash_present": !evidence_clock_day.frozen_inputs.strategy_hypothesis_hash.is_empty(),
            "reference_data_sources_contract_hash_present": !evidence_clock_day.frozen_inputs.reference_data_sources_contract_hash.is_empty(),
            "paper_shadow_divergence_threshold_hash_present": !evidence_clock_day.frozen_inputs.paper_shadow_divergence_threshold_hash.is_empty(),
            "gui_evidence_view_available": evidence_clock_day.frozen_inputs.gui_evidence_view_available,
            "daily_scorecard_regeneration_passed": evidence_clock_day.frozen_inputs.daily_scorecard_regeneration_passed,
        },
        "dq_manifest": {
            "shape_accepted": dq_shape_verdict.accepted,
            "shape_blockers": dq_shape_verdict.blockers,
            "passes_day_quality": evidence_clock_day.dq_manifest.passes_day_quality(),
            "trading_day": evidence_clock_day.dq_manifest.trading_day,
            "calendar_aware_coverage_bps": evidence_clock_day.dq_manifest.calendar_aware_coverage_bps,
            "symbol_completeness_bps": evidence_clock_day.dq_manifest.symbol_completeness_bps,
            "latency_dq_passed": evidence_clock_day.dq_manifest.latency_dq_passed,
            "market_data_provenance_accepted": evidence_clock_day.dq_manifest.market_data_provenance_accepted,
            "scorecard_regeneration_passed": evidence_clock_day.dq_manifest.scorecard_regeneration_passed,
        },
        "scorecard": {
            "writer_started": evidence_clock_day.checker_wrote_scorecard,
            "db_apply_performed": evidence_clock_day.checker_applied_db,
            "daily_scorecard_regeneration_passed": evidence_clock_day.frozen_inputs.daily_scorecard_regeneration_passed,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn phase2_precontact_summary() -> serde_json::Value {
    let api_allowlist = NonBybitApiAllowlistV1::accepted_fixture();
    let api_allowlist_verdict = api_allowlist.validate();
    let policy_bundle = IbkrPhase2PolicyBundleV1::source_template();
    let policy_verdict = policy_bundle.validate();
    let policy_flags = policy_bundle.gate_prerequisite_flags();
    let gate = IbkrExternalSurfaceGateV1 {
        api_allowlist_present: api_allowlist_verdict.accepted,
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
        "api_allowlist": {
            "contract_id": api_allowlist.contract_id,
            "source_version": api_allowlist.source_version,
            "accepted": api_allowlist_verdict.accepted,
            "blockers": api_allowlist_verdict.blockers,
            "read_action_count": api_allowlist.read_actions.len(),
            "paper_write_action_count": api_allowlist.paper_write_actions.len(),
            "denied_action_count": api_allowlist.denied_actions.len(),
            "ibkr_contact_performed": api_allowlist.ibkr_contact_performed,
            "secret_content_serialized": api_allowlist.secret_content_serialized,
            "bybit_live_execution_protected": api_allowlist.bybit_live_execution_protected,
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
