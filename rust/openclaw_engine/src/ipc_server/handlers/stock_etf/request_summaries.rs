//! Stock/ETF IPC request parsing and source-only request summaries.

use super::*;

fn operation_for_method(method: &str) -> Option<BrokerOperation> {
    match method {
        "stock_etf.preview_paper_order" => Some(BrokerOperation::PaperOrderSubmit),
        "stock_etf.submit_paper_order" => Some(BrokerOperation::PaperOrderSubmit),
        "stock_etf.cancel_paper_order" => Some(BrokerOperation::PaperOrderCancel),
        "stock_etf.replace_paper_order" => Some(BrokerOperation::PaperOrderReplace),
        "stock_etf.import_paper_fills" => Some(BrokerOperation::PaperOrderFillImport),
        "stock_etf.evaluate_shadow_signal" => Some(BrokerOperation::ShadowSignalEmit),
        "stock_etf.preview_readonly_probe" => Some(BrokerOperation::HealthRead),
        _ => None,
    }
}

pub(super) fn operation_for_method_and_params(
    method: &str,
    params: &serde_json::Value,
) -> Option<BrokerOperation> {
    if method == "stock_etf.preview_readonly_probe" {
        return readonly_probe_operation_from_params(params)
            .or_else(|| operation_for_method(method));
    }
    operation_for_method(method)
}

fn readonly_probe_operation_from_params(params: &serde_json::Value) -> Option<BrokerOperation> {
    let request =
        serde_json::from_value::<StockEtfIbkrReadonlyProbeRequestV1>(params.clone()).ok()?;
    request.validate().accepted.then_some(request.operation)
}

fn paper_request_method_for_ipc(method: &str) -> Option<StockEtfLaneScopedIpcMethod> {
    match method {
        "stock_etf.preview_paper_order" => Some(StockEtfLaneScopedIpcMethod::PreviewPaperOrder),
        "stock_etf.submit_paper_order" => Some(StockEtfLaneScopedIpcMethod::SubmitPaperOrder),
        "stock_etf.cancel_paper_order" => Some(StockEtfLaneScopedIpcMethod::CancelPaperOrder),
        "stock_etf.replace_paper_order" => Some(StockEtfLaneScopedIpcMethod::ReplacePaperOrder),
        _ => None,
    }
}

fn fill_import_request_method_for_ipc(method: &str) -> Option<StockEtfLaneScopedIpcMethod> {
    match method {
        "stock_etf.import_paper_fills" => Some(StockEtfLaneScopedIpcMethod::ImportPaperFills),
        _ => None,
    }
}

fn shadow_signal_request_method_for_ipc(method: &str) -> Option<StockEtfLaneScopedIpcMethod> {
    match method {
        "stock_etf.evaluate_shadow_signal" => {
            Some(StockEtfLaneScopedIpcMethod::EvaluateShadowSignal)
        }
        _ => None,
    }
}

fn readonly_probe_request_method_for_ipc(method: &str) -> Option<StockEtfLaneScopedIpcMethod> {
    match method {
        "stock_etf.preview_readonly_probe" => {
            Some(StockEtfLaneScopedIpcMethod::PreviewReadonlyProbe)
        }
        _ => None,
    }
}

pub(super) fn paper_request_envelope_summary(
    method: &str,
    params: &serde_json::Value,
) -> Option<(serde_json::Value, bool)> {
    let expected_request_method = paper_request_method_for_ipc(method)?;
    let parsed = serde_json::from_value::<StockEtfPaperOrderRequestEnvelopeV1>(params.clone());

    Some(match parsed {
        Ok(envelope) => {
            let verdict = envelope.validate();
            let ipc_method_matches = envelope.request_method == expected_request_method;
            let ipc_binding_blockers: Vec<&str> = if ipc_method_matches {
                Vec::new()
            } else {
                vec!["ipc_method_mismatch"]
            };
            let accepted_for_ipc = verdict.accepted && ipc_method_matches;
            (
                serde_json::json!({
                    "expected_contract_id": STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
                    "contract_id": envelope.contract_id,
                    "source_version": envelope.source_version,
                    "parse_ok": true,
                    "accepted": verdict.accepted,
                    "blockers": verdict.blockers,
                    "expected_request_method": expected_request_method,
                    "request_method": envelope.request_method,
                    "ipc_method_matches": ipc_method_matches,
                    "ipc_binding_blockers": ipc_binding_blockers,
                    "accepted_for_ipc": accepted_for_ipc,
                    "operation": envelope.operation,
                    "authority_scope": envelope.authority_scope,
                    "effect_capable": envelope.effect_capable,
                    "request_id_present": !envelope.request_id.is_empty(),
                    "account_fingerprint_hash_present": !envelope.account_fingerprint_hash.is_empty(),
                    "session_attestation_hash_present": !envelope.session_attestation_hash.is_empty(),
                    "scoped_authorization_hash_present": !envelope.scoped_authorization_hash.is_empty(),
                    "decision_lease_id_present": !envelope.decision_lease_id.is_empty(),
                    "guardian_state_hash_present": !envelope.guardian_state_hash.is_empty(),
                    "risk_config_hash_present": !envelope.risk_config_hash.is_empty(),
                    "instrument_identity_hash_present": !envelope.instrument_identity_hash.is_empty(),
                    "lifecycle_contract_hash_present": !envelope.lifecycle_contract_hash.is_empty(),
                    "broker_capability_registry_hash_present": !envelope.broker_capability_registry_hash.is_empty(),
                    "audit_event_id_present": !envelope.audit_event_id.is_empty(),
                    "order_local_id_present": !envelope.order_local_id.is_empty(),
                    "idempotency_key_present": !envelope.idempotency_key.is_empty(),
                    "broker_order_id_present": !envelope.broker_order_id.is_empty(),
                    "cancel_reason_present": !envelope.cancel_reason.is_empty(),
                    "replacement_idempotency_key_present": !envelope.replacement_idempotency_key.is_empty(),
                    "replace_reason_present": !envelope.replace_reason.is_empty(),
                    "ibkr_contact_performed": envelope.ibkr_contact_performed,
                    "connector_runtime_started": envelope.connector_runtime_started,
                    "secret_content_serialized": envelope.secret_content_serialized,
                    "order_routed": envelope.order_routed,
                    "bybit_path_reused": envelope.bybit_path_reused,
                    "live_or_tiny_live_authorized": envelope.live_or_tiny_live_authorized,
                    "margin_short_options_cfd_requested": envelope.margin_short_options_cfd_requested,
                    "python_direct_broker_write_requested": envelope.python_direct_broker_write_requested,
                }),
                accepted_for_ipc,
            )
        }
        Err(e) => (
            serde_json::json!({
                "expected_contract_id": STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
                "contract_id": "",
                "source_version": 0,
                "parse_ok": false,
                "accepted": false,
                "blockers": ["request_envelope_parse_failed"],
                "expected_request_method": expected_request_method,
                "request_method": serde_json::Value::Null,
                "ipc_method_matches": false,
                "ipc_binding_blockers": ["request_envelope_parse_failed"],
                "accepted_for_ipc": false,
                "parse_error": e.to_string(),
                "request_id_present": false,
                "ibkr_contact_performed": false,
                "connector_runtime_started": false,
                "secret_content_serialized": false,
                "order_routed": false,
                "bybit_path_reused": false,
                "live_or_tiny_live_authorized": false,
                "margin_short_options_cfd_requested": false,
                "python_direct_broker_write_requested": false,
            }),
            false,
        ),
    })
}

pub(super) fn fill_import_request_summary(
    method: &str,
    params: &serde_json::Value,
) -> Option<(serde_json::Value, bool)> {
    let expected_request_method = fill_import_request_method_for_ipc(method)?;
    let parsed = serde_json::from_value::<StockEtfPaperFillImportRequestV1>(params.clone());

    Some(match parsed {
        Ok(request) => {
            let verdict = request.validate();
            let ipc_method_matches = request.request_method == expected_request_method;
            let ipc_binding_blockers: Vec<&str> = if ipc_method_matches {
                Vec::new()
            } else {
                vec!["ipc_method_mismatch"]
            };
            let accepted_for_ipc = verdict.accepted && ipc_method_matches;
            (
                serde_json::json!({
                    "expected_contract_id": STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID,
                    "contract_id": request.contract_id,
                    "source_version": request.source_version,
                    "parse_ok": true,
                    "accepted": verdict.accepted,
                    "blockers": verdict.blockers,
                    "expected_request_method": expected_request_method,
                    "request_method": request.request_method,
                    "ipc_method_matches": ipc_method_matches,
                    "ipc_binding_blockers": ipc_binding_blockers,
                    "accepted_for_ipc": accepted_for_ipc,
                    "operation": request.operation,
                    "authority_scope": request.authority_scope,
                    "effect_capable": request.effect_capable,
                    "request_id_present": !request.request_id.is_empty(),
                    "session_attestation_hash_present": !request.session_attestation_hash.is_empty(),
                    "lifecycle_contract_hash_present": !request.lifecycle_contract_hash.is_empty(),
                    "event_log_contract_hash_present": !request.event_log_contract_hash.is_empty(),
                    "redaction_policy_hash_present": !request.redaction_policy_hash.is_empty(),
                    "source_artifact_hash_present": !request.source_artifact_hash.is_empty(),
                    "reconciliation_run_id_present": !request.reconciliation_run_id.is_empty(),
                    "broker_order_id_present": !request.broker_order_id.is_empty(),
                    "execution_id_present": !request.execution_id.is_empty(),
                    "commission_report_id_present": !request.commission_report_id.is_empty(),
                    "import_idempotency_key_present": !request.import_idempotency_key.is_empty(),
                    "observed_order_state_present": request.observed_order_state.is_some(),
                    "stale_state_policy_present": request.stale_state_policy.is_some(),
                    "raw_artifact_hash_present": !request.raw_artifact_hash.is_empty(),
                    "redacted_summary_hash_present": !request.redacted_summary_hash.is_empty(),
                    "duplicate_import_detected": request.duplicate_import_detected,
                    "stale_unknown_state_without_policy": request.stale_unknown_state_without_policy,
                    "ibkr_contact_performed": request.ibkr_contact_performed,
                    "connector_runtime_started": request.connector_runtime_started,
                    "secret_content_serialized": request.secret_content_serialized,
                    "fill_import_performed": request.fill_import_performed,
                    "db_apply_performed": request.db_apply_performed,
                    "order_routed": request.order_routed,
                    "bybit_path_reused": request.bybit_path_reused,
                    "live_or_tiny_live_authorized": request.live_or_tiny_live_authorized,
                    "margin_short_options_cfd_requested": request.margin_short_options_cfd_requested,
                    "python_direct_broker_write_requested": request.python_direct_broker_write_requested,
                }),
                accepted_for_ipc,
            )
        }
        Err(e) => (
            serde_json::json!({
                "expected_contract_id": STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID,
                "contract_id": "",
                "source_version": 0,
                "parse_ok": false,
                "accepted": false,
                "blockers": ["fill_import_request_parse_failed"],
                "expected_request_method": expected_request_method,
                "request_method": serde_json::Value::Null,
                "ipc_method_matches": false,
                "ipc_binding_blockers": ["fill_import_request_parse_failed"],
                "accepted_for_ipc": false,
                "parse_error": e.to_string(),
                "request_id_present": false,
                "ibkr_contact_performed": false,
                "connector_runtime_started": false,
                "secret_content_serialized": false,
                "fill_import_performed": false,
                "db_apply_performed": false,
                "order_routed": false,
                "bybit_path_reused": false,
                "live_or_tiny_live_authorized": false,
                "margin_short_options_cfd_requested": false,
                "python_direct_broker_write_requested": false,
            }),
            false,
        ),
    })
}

pub(super) fn shadow_signal_request_summary(
    method: &str,
    params: &serde_json::Value,
) -> Option<(serde_json::Value, bool)> {
    let expected_request_method = shadow_signal_request_method_for_ipc(method)?;
    let parsed = serde_json::from_value::<StockEtfShadowSignalRequestV1>(params.clone());

    Some(match parsed {
        Ok(request) => {
            let verdict = request.validate();
            let ipc_method_matches = request.request_method == expected_request_method;
            let ipc_binding_blockers: Vec<&str> = if ipc_method_matches {
                Vec::new()
            } else {
                vec!["ipc_method_mismatch"]
            };
            let accepted_for_ipc = verdict.accepted && ipc_method_matches;
            (
                serde_json::json!({
                    "expected_contract_id": STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID,
                    "contract_id": request.contract_id,
                    "source_version": request.source_version,
                    "parse_ok": true,
                    "accepted": verdict.accepted,
                    "blockers": verdict.blockers,
                    "expected_request_method": expected_request_method,
                    "request_method": request.request_method,
                    "ipc_method_matches": ipc_method_matches,
                    "ipc_binding_blockers": ipc_binding_blockers,
                    "accepted_for_ipc": accepted_for_ipc,
                    "operation": request.operation,
                    "authority_scope": request.authority_scope,
                    "effect_capable": request.effect_capable,
                    "request_id_present": !request.request_id.is_empty(),
                    "evaluation_run_id_present": !request.evaluation_run_id.is_empty(),
                    "shadow_signal_id_present": !request.shadow_signal_id.is_empty(),
                    "evidence_clock_hash_present": !request.evidence_clock_hash.is_empty(),
                    "pit_universe_contract_hash_present": !request.pit_universe_contract_hash.is_empty(),
                    "strategy_hypothesis_hash_present": !request.strategy_hypothesis_hash.is_empty(),
                    "instrument_identity_hash_present": !request.instrument_identity_hash.is_empty(),
                    "market_data_provenance_hash_present": !request.market_data_provenance_hash.is_empty(),
                    "cost_model_version_hash_present": !request.cost_model_version_hash.is_empty(),
                    "asset_lane_events_contract_hash_present": !request.asset_lane_events_contract_hash.is_empty(),
                    "source_artifact_hash_present": !request.source_artifact_hash.is_empty(),
                    "ibkr_contact_performed": request.ibkr_contact_performed,
                    "connector_runtime_started": request.connector_runtime_started,
                    "secret_content_serialized": request.secret_content_serialized,
                    "shadow_signal_emitted": request.shadow_signal_emitted,
                    "shadow_fill_generated": request.shadow_fill_generated,
                    "scorecard_writer_started": request.scorecard_writer_started,
                    "db_apply_performed": request.db_apply_performed,
                    "order_routed": request.order_routed,
                    "bybit_path_reused": request.bybit_path_reused,
                    "live_or_tiny_live_authorized": request.live_or_tiny_live_authorized,
                    "margin_short_options_cfd_requested": request.margin_short_options_cfd_requested,
                    "python_direct_broker_write_requested": request.python_direct_broker_write_requested,
                }),
                accepted_for_ipc,
            )
        }
        Err(e) => (
            serde_json::json!({
                "expected_contract_id": STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID,
                "contract_id": "",
                "source_version": 0,
                "parse_ok": false,
                "accepted": false,
                "blockers": ["shadow_signal_request_parse_failed"],
                "expected_request_method": expected_request_method,
                "request_method": serde_json::Value::Null,
                "ipc_method_matches": false,
                "ipc_binding_blockers": ["shadow_signal_request_parse_failed"],
                "accepted_for_ipc": false,
                "parse_error": e.to_string(),
                "request_id_present": false,
                "evaluation_run_id_present": false,
                "shadow_signal_id_present": false,
                "ibkr_contact_performed": false,
                "connector_runtime_started": false,
                "secret_content_serialized": false,
                "shadow_signal_emitted": false,
                "shadow_fill_generated": false,
                "scorecard_writer_started": false,
                "db_apply_performed": false,
                "order_routed": false,
                "bybit_path_reused": false,
                "live_or_tiny_live_authorized": false,
                "margin_short_options_cfd_requested": false,
                "python_direct_broker_write_requested": false,
            }),
            false,
        ),
    })
}

pub(super) fn readonly_probe_request_ipc_summary(
    method: &str,
    params: &serde_json::Value,
) -> Option<(serde_json::Value, bool)> {
    let expected_request_method = readonly_probe_request_method_for_ipc(method)?;
    let parsed = serde_json::from_value::<StockEtfIbkrReadonlyProbeRequestV1>(params.clone());

    Some(match parsed {
        Ok(request) => {
            let verdict = request.validate();
            let accepted_for_ipc = verdict.accepted;
            (
                serde_json::json!({
                    "expected_contract_id": STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
                    "contract_id": request.contract_id,
                    "source_version": request.source_version,
                    "parse_ok": true,
                    "accepted": verdict.accepted,
                    "blockers": verdict.blockers,
                    "expected_request_method": expected_request_method,
                    "accepted_for_ipc": accepted_for_ipc,
                    "probe_kind": request.probe_kind,
                    "api_action": request.api_action,
                    "operation": request.operation,
                    "authority_scope": request.authority_scope,
                    "effect_capable": request.effect_capable,
                    "request_id_present": !request.request_id.is_empty(),
                    "probe_id_present": !request.probe_id.is_empty(),
                    "phase2_gate_artifact_hash_present": !request.phase2_gate_artifact_hash.is_empty(),
                    "api_allowlist_hash_present": !request.api_allowlist_hash.is_empty(),
                    "secret_slot_contract_hash_present": !request.secret_slot_contract_hash.is_empty(),
                    "api_session_topology_hash_present": !request.api_session_topology_hash.is_empty(),
                    "session_attestation_hash_present": !request.session_attestation_hash.is_empty(),
                    "redaction_policy_hash_present": !request.redaction_policy_hash.is_empty(),
                    "rate_limit_policy_hash_present": !request.rate_limit_policy_hash.is_empty(),
                    "audit_event_policy_hash_present": !request.audit_event_policy_hash.is_empty(),
                    "source_artifact_hash_present": !request.source_artifact_hash.is_empty(),
                    "raw_artifact_hash_present": !request.raw_artifact_hash.is_empty(),
                    "redacted_summary_hash_present": !request.redacted_summary_hash.is_empty(),
                    "read_probe_executed": false,
                    "ibkr_contact_performed": request.ibkr_contact_performed,
                    "connector_runtime_started": request.connector_runtime_started,
                    "secret_content_serialized": request.secret_content_serialized,
                    "order_routed": request.order_routed,
                    "paper_order_submitted": request.paper_order_submitted,
                    "db_apply_performed": request.db_apply_performed,
                    "evidence_clock_started": request.evidence_clock_started,
                    "bybit_path_reused": request.bybit_path_reused,
                    "live_or_tiny_live_authorized": request.live_or_tiny_live_authorized,
                    "margin_short_options_cfd_requested": request.margin_short_options_cfd_requested,
                    "account_write_requested": request.account_write_requested,
                    "market_data_entitlement_purchase_requested": request.market_data_entitlement_purchase_requested,
                    "client_portal_web_api_requested": request.client_portal_web_api_requested,
                    "python_direct_broker_write_requested": request.python_direct_broker_write_requested,
                }),
                accepted_for_ipc,
            )
        }
        Err(e) => (
            serde_json::json!({
                "expected_contract_id": STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
                "contract_id": "",
                "source_version": 0,
                "parse_ok": false,
                "accepted": false,
                "blockers": ["readonly_probe_request_parse_failed"],
                "expected_request_method": expected_request_method,
                "accepted_for_ipc": false,
                "parse_error": e.to_string(),
                "request_id_present": false,
                "probe_id_present": false,
                "read_probe_executed": false,
                "ibkr_contact_performed": false,
                "connector_runtime_started": false,
                "secret_content_serialized": false,
                "order_routed": false,
                "paper_order_submitted": false,
                "db_apply_performed": false,
                "evidence_clock_started": false,
                "bybit_path_reused": false,
                "live_or_tiny_live_authorized": false,
                "margin_short_options_cfd_requested": false,
                "account_write_requested": false,
                "market_data_entitlement_purchase_requested": false,
                "client_portal_web_api_requested": false,
                "python_direct_broker_write_requested": false,
            }),
            false,
        ),
    })
}

pub(super) fn request_from_params(
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
