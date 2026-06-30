//! ADR-0048 Stock/ETF lane IPC fixtures.
//!
//! Phase 1 only: these handlers expose lane status/readiness and typed denial
//! previews. They intentionally do not send `PipelineCommand`, do not reuse the
//! Bybit `submit_paper_order` path, and do not contact IBKR.

use super::super::*;
use openclaw_types::{
    evaluate_broker_operation, evaluate_feature_flag_secret_auth_matrix, AssetLane, AuthorityScope,
    Broker, BrokerAccountPortfolioCashLedgerV1, BrokerCapabilityRequest, BrokerEnvironment,
    BrokerLifecycleEventLogV1, BrokerOperation, FeatureFlagSecretAuthMatrixV1,
    IbkrExternalSurfaceGateV1, IbkrPaperAttestationPolicyV1, IbkrPhase2PolicyBundleV1,
    IbkrSessionAttestationV1, InstrumentKind, NonBybitApiAllowlistV1,
    StockEtfBrokerCapabilityRegistryV1, StockEtfDisableCleanupRunbookV1,
    StockEtfEvidenceClockDayV1, StockEtfFeatureFlags, StockEtfGateInputs,
    StockEtfIbkrReadonlyProbeRequestV1, StockEtfInstrumentIdentityV1, StockEtfLaneScopedIpcMethod,
    StockEtfPaperFillImportRequestV1, StockEtfPaperOrderRequestEnvelopeV1,
    StockEtfPaperShadowReconciliationV1, StockEtfPhase0ContractPacketManifestV1,
    StockEtfPitUniverseV1, StockEtfReferenceDataSourcesV1, StockEtfReleasePacketV1,
    StockEtfRiskPolicyV1, StockEtfScorecardDerivationV1, StockEtfScorecardVerdictV1,
    StockEtfShadowSignalRequestV1, StockEtfStrategyHypothesisV1, StockMarketDataProvenanceV1,
    StockShadowFillModelV1, TinyLiveAdrEligibilityV1,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_PAPER_ATTESTATION_CONTRACT_ID, IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
    IBKR_SECRET_SLOT_CONTRACT_ID, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID, STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID,
    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID, STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
    STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID, STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
    STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID, STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
    STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID, STOCK_ETF_RELEASE_PACKET_CONTRACT_ID,
    STOCK_ETF_RISK_POLICY_CONTRACT_ID, STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID,
    STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID, STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID,
    STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID, STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID,
    STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID, STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
};

mod status_summaries;
use status_summaries::{
    account_status_summary, disable_cleanup_status_summary, evidence_status_summary,
    launch_status_summary, paper_status_summary, reconciliation_status_summary,
    release_packet_status_summary, scorecard_status_summary, shadow_status_summary,
    universe_status_summary,
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
        "stock_etf.get_phase0_status" => {
            JsonRpcResponse::success(id, phase0_status_summary(phase2))
        }
        "stock_etf.get_readiness" => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "phase": "phase2_precontact_source_fixture",
                "readiness": flags.readiness(),
                "phase2": phase2,
                "connector_skeleton": connector_skeleton_summary(),
                "ibkr_live_enabled": false,
                "ibkr_call_performed": false,
                "secret_slot_touched": false,
                "order_routed": false,
                "bybit_ipc_reused": false,
            }),
        ),
        "stock_etf.get_data_foundation_status" => {
            JsonRpcResponse::success(id, data_foundation_status_summary(phase2))
        }
        "stock_etf.get_policy_status" => {
            JsonRpcResponse::success(id, policy_status_summary(phase2))
        }
        "stock_etf.get_authorization_status" => {
            JsonRpcResponse::success(id, authorization_status_summary(phase2, flags.clone()))
        }
        "stock_etf.get_account_status" => {
            JsonRpcResponse::success(id, account_status_summary(phase2))
        }
        "stock_etf.get_evidence_status" => {
            JsonRpcResponse::success(id, evidence_status_summary(phase2))
        }
        "stock_etf.get_universe_status" => {
            JsonRpcResponse::success(id, universe_status_summary(phase2))
        }
        "stock_etf.get_shadow_status" => {
            JsonRpcResponse::success(id, shadow_status_summary(phase2))
        }
        "stock_etf.get_paper_status" => JsonRpcResponse::success(id, paper_status_summary(phase2)),
        "stock_etf.get_reconciliation_status" => {
            JsonRpcResponse::success(id, reconciliation_status_summary(phase2))
        }
        "stock_etf.get_scorecard_status" => {
            JsonRpcResponse::success(id, scorecard_status_summary(phase2))
        }
        "stock_etf.get_launch_status" => {
            JsonRpcResponse::success(id, launch_status_summary(phase2))
        }
        "stock_etf.get_release_packet_status" => {
            JsonRpcResponse::success(id, release_packet_status_summary(phase2))
        }
        "stock_etf.get_disable_cleanup_status" => {
            JsonRpcResponse::success(id, disable_cleanup_status_summary(phase2))
        }
        _ => {
            let operation = match operation_for_method_and_params(method, params) {
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
            let paper_request = paper_request_envelope_summary(method, params);
            let request_envelope_accepted_for_ipc = paper_request
                .as_ref()
                .map(|(_, accepted)| *accepted)
                .unwrap_or(true);
            let fill_import_request = fill_import_request_summary(method, params);
            let fill_import_request_accepted_for_ipc = fill_import_request
                .as_ref()
                .map(|(_, accepted)| *accepted)
                .unwrap_or(true);
            let shadow_signal_request = shadow_signal_request_summary(method, params);
            let shadow_signal_request_accepted_for_ipc = shadow_signal_request
                .as_ref()
                .map(|(_, accepted)| *accepted)
                .unwrap_or(true);
            let readonly_probe_request = readonly_probe_request_ipc_summary(method, params);
            let readonly_probe_request_accepted_for_ipc = readonly_probe_request
                .as_ref()
                .map(|(_, accepted)| *accepted)
                .unwrap_or(true);
            let allowed = decision.allowed
                && request_envelope_accepted_for_ipc
                && fill_import_request_accepted_for_ipc
                && shadow_signal_request_accepted_for_ipc
                && readonly_probe_request_accepted_for_ipc;
            let denial_reason = decision.denial_reason;
            JsonRpcResponse::success(
                id,
                serde_json::json!({
                    "phase": "phase1_ipc_fixture",
                    "method": method,
                    "decision": decision,
                    "allowed": allowed,
                    "denial_reason": denial_reason,
                    "request_envelope": paper_request.map(|(summary, _)| summary),
                    "request_envelope_accepted_for_ipc": request_envelope_accepted_for_ipc,
                    "fill_import_request": fill_import_request.map(|(summary, _)| summary),
                    "fill_import_request_accepted_for_ipc": fill_import_request_accepted_for_ipc,
                    "shadow_signal_request": shadow_signal_request.map(|(summary, _)| summary),
                    "shadow_signal_request_accepted_for_ipc": shadow_signal_request_accepted_for_ipc,
                    "readonly_probe_request": readonly_probe_request.map(|(summary, _)| summary),
                    "readonly_probe_request_accepted_for_ipc": readonly_probe_request_accepted_for_ipc,
                    "runtime_authority_denied": true,
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

fn phase0_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let manifest = StockEtfPhase0ContractPacketManifestV1::accepted_fixture();
    let verdict = manifest.validate();
    serde_json::json!({
        "phase": "phase0_contract_packet_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "scope": manifest.scope,
        "gui_authority": "display_only",
        "phase0_status_state": "accepted_no_runtime_authority",
        "phase0_accepted": verdict.accepted,
        "phase0_blockers": verdict.blockers,
        "contract_count": manifest.contracts.len(),
        "contracts": manifest.contracts,
        "manifest": {
            "schema": manifest.schema,
            "generated_at": manifest.generated_at,
            "status": manifest.status,
            "scope": manifest.scope,
            "adr": manifest.authority.adr,
            "amd": manifest.authority.amd,
            "contract_packet": manifest.authority.contract_packet,
        },
        "api_baseline": {
            "selected": manifest.api_baseline.selected,
            "host_policy": manifest.api_baseline.host_policy,
            "paper_port_default_candidate": manifest.api_baseline.paper_port_default_candidate,
            "live_ports_denied": manifest.api_baseline.live_ports_denied,
            "ibkr_call_performed": manifest.api_baseline.ibkr_call_performed,
        },
        "global_denials": {
            "ibkr_live": manifest.global_denials.ibkr_live,
            "tiny_live": manifest.global_denials.tiny_live,
            "margin": manifest.global_denials.margin,
            "short": manifest.global_denials.short,
            "options": manifest.global_denials.options,
            "cfd": manifest.global_denials.cfd,
            "transfer": manifest.global_denials.transfer,
            "account_management_writes": manifest.global_denials.account_management_writes,
            "python_broker_write_authority": manifest.global_denials.python_broker_write_authority,
            "gui_lane_authority": manifest.global_denials.gui_lane_authority,
            "automatic_promotion": manifest.global_denials.automatic_promotion,
        },
        "phase_unlock": manifest.phase_unlock,
        "phase1_runtime_started": false,
        "phase2_started": false,
        "phase3_started": false,
        "phase4_runtime_started": false,
        "phase5_started": false,
        "paper_shadow_launch_authorized": false,
        "tiny_live_or_live_authorized": false,
        "connector_runtime_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "scorecard_writer_started": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
        "phase2": phase2,
    })
}

fn data_foundation_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let instrument_identity = StockEtfInstrumentIdentityV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        instrument_kind: InstrumentKind::Stock,
        bybit_live_execution_unchanged: true,
        ibkr_live_denied: true,
        margin_short_denied: true,
        options_cfd_denied: true,
        ..StockEtfInstrumentIdentityV1::default()
    };
    let instrument_verdict = instrument_identity.validate();
    let reference_sources = StockEtfReferenceDataSourcesV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        environment: BrokerEnvironment::Paper,
        bybit_live_execution_unchanged: true,
        live_or_tiny_live_authorized: false,
        ..StockEtfReferenceDataSourcesV1::default()
    };
    let reference_verdict = reference_sources.validate();

    let identity = serde_json::json!({
        "expected_contract_id": STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID,
        "contract_id": instrument_identity.contract_id,
        "source_version": instrument_identity.source_version,
        "accepted": instrument_verdict.accepted,
        "blockers": instrument_verdict.blockers,
        "symbol": instrument_identity.symbol,
        "instrument_kind": instrument_identity.instrument_kind,
        "listing_venue": instrument_identity.listing_venue,
        "primary_exchange": instrument_identity.primary_exchange,
        "currency": instrument_identity.currency,
        "tradability_status": instrument_identity.tradability_status,
        "priips_kid_status": instrument_identity.priips_kid_status,
        "fractional_policy_recorded": instrument_identity.fractional_policy_recorded,
        "point_in_time_asof_ms": instrument_identity.point_in_time_asof_ms,
        "market_calendar_id_present": !instrument_identity.market_calendar_id.is_empty(),
        "market_calendar_hash_present": !instrument_identity.market_calendar_hash.is_empty(),
        "broker_contract_details_hash_present": !instrument_identity.broker_contract_details_hash.is_empty(),
        "instrument_identity_hash_present": !instrument_identity.instrument_identity_hash.is_empty(),
        "corporate_action_adjustment_version_hash_present": !instrument_identity.corporate_action_adjustment_version_hash.is_empty(),
        "source_artifact_hash_present": !instrument_identity.source_artifact_hash.is_empty(),
        "bybit_live_execution_unchanged": instrument_identity.bybit_live_execution_unchanged,
        "ibkr_live_denied": instrument_identity.ibkr_live_denied,
        "margin_short_denied": instrument_identity.margin_short_denied,
        "options_cfd_denied": instrument_identity.options_cfd_denied,
        "ibkr_contact_performed": instrument_identity.ibkr_contact_performed,
        "secret_content_serialized": instrument_identity.secret_content_serialized,
    });
    let reference = serde_json::json!({
        "expected_contract_id": STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
        "contract_id": reference_sources.contract_id,
        "source_version": reference_sources.source_version,
        "accepted": reference_verdict.accepted,
        "blockers": reference_verdict.blockers,
        "environment": reference_sources.environment,
        "frozen_for_evidence_clock": reference_sources.frozen_for_evidence_clock,
        "corporate_action_source_name": reference_sources.corporate_action_source_name,
        "corporate_action_asof_ms": reference_sources.corporate_action_asof_ms,
        "corporate_action_raw_hash_present": !reference_sources.corporate_action_raw_hash.is_empty(),
        "corporate_action_adjustment_version_hash_present": !reference_sources.corporate_action_adjustment_version_hash.is_empty(),
        "corporate_action_policy_hash_present": !reference_sources.corporate_action_policy_hash.is_empty(),
        "dividend_treatment_hash_present": !reference_sources.dividend_treatment_hash.is_empty(),
        "fx_rate_source_name": reference_sources.fx_rate_source_name,
        "fx_rate_asof_ms": reference_sources.fx_rate_asof_ms,
        "base_currency": reference_sources.base_currency,
        "quote_currency": reference_sources.quote_currency,
        "fx_rate_snapshot_hash_present": !reference_sources.fx_rate_snapshot_hash.is_empty(),
        "fx_drag_model_hash_present": !reference_sources.fx_drag_model_hash.is_empty(),
        "fee_schedule_source_name": reference_sources.fee_schedule_source_name,
        "fee_schedule_asof_ms": reference_sources.fee_schedule_asof_ms,
        "commission_schedule_hash_present": !reference_sources.commission_schedule_hash.is_empty(),
        "exchange_regulatory_fee_hash_present": !reference_sources.exchange_regulatory_fee_hash.is_empty(),
        "tax_ftt_placeholder_hash_present": !reference_sources.tax_ftt_placeholder_hash.is_empty(),
        "withholding_tax_treatment_hash_present": !reference_sources.withholding_tax_treatment_hash.is_empty(),
        "source_artifact_hash_present": !reference_sources.source_artifact_hash.is_empty(),
        "bybit_live_execution_unchanged": reference_sources.bybit_live_execution_unchanged,
        "ibkr_contact_performed": reference_sources.ibkr_contact_performed,
        "connector_runtime_started": reference_sources.connector_runtime_started,
        "secret_content_serialized": reference_sources.secret_content_serialized,
        "live_or_tiny_live_authorized": reference_sources.live_or_tiny_live_authorized,
    });

    serde_json::json!({
        "phase": "phase2_data_foundation_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "data_foundation_status_state": "blocked",
        "phase2_started": false,
        "phase3_started": false,
        "contract_details_request_started": false,
        "reference_data_collection_started": false,
        "collector_started": false,
        "market_data_ingestion_started": false,
        "connector_runtime_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "scorecard_writer_started": false,
        "instrument_identity": identity,
        "reference_data_sources": reference,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "stock_live_disabled": true,
        "paper_order_entry_visible": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn policy_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let risk_policy = StockEtfRiskPolicyV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        environment: BrokerEnvironment::Paper,
        enabled: false,
        shadow_only: true,
        allow_margin: false,
        allow_short: false,
        allow_options: false,
        allow_cfd: false,
        allow_transfer: false,
        allow_live: false,
        bybit_live_execution_unchanged: true,
        ..StockEtfRiskPolicyV1::default()
    };
    let risk_verdict = risk_policy.validate();
    let registry = StockEtfBrokerCapabilityRegistryV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        bybit_live_execution_unchanged: true,
        python_broker_write_authority_denied: true,
        ibkr_live_denied: true,
        cfd_margin_reserved_denied: true,
        ..StockEtfBrokerCapabilityRegistryV1::default()
    };
    let registry_verdict = registry.validate();
    let read_operation_count = registry
        .operations
        .iter()
        .filter(|entry| entry.authority_scope == AuthorityScope::ReadOnly)
        .count();
    let paper_operation_count = registry
        .operations
        .iter()
        .filter(|entry| entry.authority_scope == AuthorityScope::PaperRehearsal)
        .count();
    let denied_operation_count = registry
        .operations
        .iter()
        .filter(|entry| entry.authority_scope == AuthorityScope::Denied)
        .count();
    let read_rows: Vec<_> = registry
        .operations
        .iter()
        .filter(|entry| entry.authority_scope == AuthorityScope::ReadOnly)
        .collect();
    let read_rows_require_lane_scoped_ipc = read_rows.len() == 4
        && read_rows.iter().all(|entry| {
            entry
                .required_gates
                .iter()
                .any(|gate| gate.as_str() == STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID)
        });
    let read_rows_require_readonly_probe_request = read_rows.len() == 4
        && read_rows.iter().all(|entry| {
            entry
                .required_gates
                .iter()
                .any(|gate| gate.as_str() == STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID)
        });

    let mut risk = serde_json::Map::new();
    macro_rules! put_risk {
        ($key:literal, $value:expr) => {
            risk.insert($key.to_string(), serde_json::json!($value));
        };
    }
    put_risk!("expected_contract_id", STOCK_ETF_RISK_POLICY_CONTRACT_ID);
    put_risk!("contract_id", &risk_policy.contract_id);
    put_risk!("source_version", risk_policy.source_version);
    put_risk!("config_version", risk_policy.config_version);
    put_risk!("accepted", risk_verdict.accepted);
    put_risk!("blockers", &risk_verdict.blockers);
    put_risk!("environment", risk_policy.environment);
    put_risk!("enabled", risk_policy.enabled);
    put_risk!("shadow_only", risk_policy.shadow_only);
    put_risk!("max_order_notional_usd", risk_policy.max_order_notional_usd);
    put_risk!(
        "max_position_notional_usd",
        risk_policy.max_position_notional_usd
    );
    put_risk!("max_daily_notional_usd", risk_policy.max_daily_notional_usd);
    put_risk!("max_open_orders", risk_policy.max_open_orders);
    put_risk!("max_open_positions", risk_policy.max_open_positions);
    put_risk!(
        "allow_fractional_shares",
        risk_policy.allow_fractional_shares
    );
    put_risk!("allow_margin", risk_policy.allow_margin);
    put_risk!("allow_short", risk_policy.allow_short);
    put_risk!("allow_options", risk_policy.allow_options);
    put_risk!("allow_cfd", risk_policy.allow_cfd);
    put_risk!("allow_transfer", risk_policy.allow_transfer);
    put_risk!("allow_live", risk_policy.allow_live);
    put_risk!(
        "allowed_kind_count",
        risk_policy.instrument_kinds_allowed.len()
    );
    put_risk!(
        "denied_kind_count",
        risk_policy.instrument_kinds_denied.len()
    );
    put_risk!(
        "requires_frozen_universe_hash",
        risk_policy.requires_frozen_universe_hash
    );
    put_risk!(
        "requires_instrument_identity_hash",
        risk_policy.requires_instrument_identity_hash
    );
    put_risk!(
        "requires_market_session",
        risk_policy.requires_market_session
    );
    put_risk!(
        "cost_model_required_before_shadow_fill",
        risk_policy.cost_model_required_before_shadow_fill
    );
    put_risk!(
        "cost_model_required_before_scorecard",
        risk_policy.cost_model_required_before_scorecard
    );
    put_risk!(
        "commission_schedule_required",
        risk_policy.commission_schedule_required
    );
    put_risk!(
        "spread_estimate_required",
        risk_policy.spread_estimate_required
    );
    put_risk!(
        "slippage_estimate_required",
        risk_policy.slippage_estimate_required
    );
    put_risk!("fx_drag_required", risk_policy.fx_drag_required);
    put_risk!(
        "conservative_fill_penalty_required",
        risk_policy.conservative_fill_penalty_required
    );
    put_risk!(
        "rust_authority_required",
        risk_policy.rust_authority_required
    );
    put_risk!(
        "session_attestation_required",
        risk_policy.session_attestation_required
    );
    put_risk!(
        "decision_lease_required",
        risk_policy.decision_lease_required
    );
    put_risk!("guardian_required", risk_policy.guardian_required);
    put_risk!(
        "idempotency_key_required",
        risk_policy.idempotency_key_required
    );
    put_risk!(
        "broker_reconciliation_required",
        risk_policy.broker_reconciliation_required
    );
    put_risk!(
        "bybit_live_execution_unchanged",
        risk_policy.bybit_live_execution_unchanged
    );
    put_risk!("ibkr_contact_performed", risk_policy.ibkr_contact_performed);
    put_risk!(
        "connector_runtime_started",
        risk_policy.connector_runtime_started
    );
    put_risk!(
        "secret_content_serialized",
        risk_policy.secret_content_serialized
    );
    let risk = serde_json::Value::Object(risk);
    let capability_registry = serde_json::json!({
        "expected_registry_id": STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID,
        "registry_id": registry.registry_id,
        "source_version": registry.source_version,
        "accepted": registry_verdict.accepted,
        "blockers": registry_verdict.blockers,
        "operation_count": registry.operations.len(),
        "required_audit_field_count": registry.required_audit_fields.len(),
        "read_operation_count": read_operation_count,
        "lane_scoped_ipc_contract_id": STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
        "readonly_probe_request_contract_id": STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
        "read_rows_require_lane_scoped_ipc": read_rows_require_lane_scoped_ipc,
        "read_rows_require_readonly_probe_request": read_rows_require_readonly_probe_request,
        "paper_operation_count": paper_operation_count,
        "denied_operation_count": denied_operation_count,
        "bybit_live_execution_unchanged": registry.bybit_live_execution_unchanged,
        "python_broker_write_authority_denied": registry.python_broker_write_authority_denied,
        "ibkr_live_denied": registry.ibkr_live_denied,
        "cfd_margin_reserved_denied": registry.cfd_margin_reserved_denied,
        "first_ibkr_contact_performed": registry.first_ibkr_contact_performed,
        "secret_content_serialized": registry.secret_content_serialized,
    });

    serde_json::json!({
        "phase": "phase2_policy_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "policy_status_state": "blocked",
        "phase2_started": false,
        "phase3_started": false,
        "risk_runtime_started": false,
        "paper_order_rehearsal_started": false,
        "paper_order_submitted": false,
        "connector_runtime_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "scorecard_writer_started": false,
        "risk_policy": risk,
        "broker_capability_registry": capability_registry,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "stock_live_disabled": true,
        "paper_order_entry_visible": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn authorization_status_summary(
    phase2: serde_json::Value,
    flags: StockEtfFeatureFlags,
) -> serde_json::Value {
    let matrix = FeatureFlagSecretAuthMatrixV1 {
        flags,
        gui_lane_state_override_denied: true,
        server_rust_matrix_authoritative: true,
        ..FeatureFlagSecretAuthMatrixV1::default()
    };
    let request = BrokerCapabilityRequest::stock_etf_ibkr_paper(
        InstrumentKind::Stock,
        BrokerOperation::PaperOrderSubmit,
    );
    let auth_verdict = evaluate_feature_flag_secret_auth_matrix(&matrix, request, 0);
    let secret_verdict = matrix.secret_slot_contract.validate();
    let artifact_verdict = matrix.phase2_gate_artifact.validate();
    let session_verdict = matrix.session_attestation.validate(0);
    let envelope = &matrix.authorization_envelope;

    serde_json::json!({
        "phase": "phase2_authorization_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "authorization_status_state": "blocked",
        "phase2_started": false,
        "phase3_started": false,
        "risk_runtime_started": false,
        "paper_order_rehearsal_started": false,
        "paper_order_submitted": false,
        "connector_runtime_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "scorecard_writer_started": false,
        "paper_order_authority_present": false,
        "scoped_authorization_present": false,
        "decision_lease_valid": false,
        "guardian_allows": false,
        "authorization_matrix": {
            "expected_contract_id": FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID,
            "contract_id": &matrix.contract_id,
            "source_version": matrix.source_version,
            "gui_lane_state_override_denied": matrix.gui_lane_state_override_denied,
            "server_rust_matrix_authoritative": matrix.server_rust_matrix_authoritative,
            "request_asset_lane": request.asset_lane,
            "request_broker": request.broker,
            "request_environment": request.environment,
            "request_instrument_kind": request.instrument_kind,
            "request_operation": request.operation,
            "request_allowed": auth_verdict.allowed,
            "effective_authority_scope": auth_verdict.effective_authority_scope,
            "blockers": auth_verdict.blockers,
        },
        "feature_flags": {
            "stock_etf_lane_enabled": matrix.flags.stock_etf_lane_enabled,
            "ibkr_readonly_enabled": matrix.flags.ibkr_readonly_enabled,
            "ibkr_paper_enabled": matrix.flags.ibkr_paper_enabled,
            "asset_lane_default": matrix.flags.asset_lane_default,
            "stock_etf_shadow_only": matrix.flags.stock_etf_shadow_only,
        },
        "secret_slot_contract": {
            "expected_contract_id": IBKR_SECRET_SLOT_CONTRACT_ID,
            "contract_id": &matrix.secret_slot_contract.contract_id,
            "source_version": matrix.secret_slot_contract.source_version,
            "accepted": secret_verdict.accepted,
            "blockers": secret_verdict.blockers,
            "contract_present": matrix.secret_slot_contract.contract_present,
            "readonly_slot_posture": matrix.secret_slot_contract.readonly_slot_posture,
            "paper_slot_posture": matrix.secret_slot_contract.paper_slot_posture,
            "live_slot_posture": matrix.secret_slot_contract.live_slot_posture,
            "owner_only_permissions": matrix.secret_slot_contract.owner_only_permissions,
            "env_var_credential_fallback_denied": matrix.secret_slot_contract.env_var_credential_fallback_denied,
            "live_secret_absent_or_empty": matrix.secret_slot_contract.live_secret_absent_or_empty,
            "secret_slot_fingerprint_present": !matrix.secret_slot_contract.secret_slot_fingerprint.is_empty(),
            "account_fingerprint_hash_present": !matrix.secret_slot_contract.account_fingerprint_hash.is_empty(),
            "secret_content_serialized": matrix.secret_slot_contract.secret_content_serialized,
            "account_id_serialized": matrix.secret_slot_contract.account_id_serialized,
        },
        "phase2_gate_artifact": {
            "expected_contract_id": IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
            "contract_id": &matrix.phase2_gate_artifact.contract_id,
            "source_version": matrix.phase2_gate_artifact.source_version,
            "ibkr_contact_allowed": artifact_verdict.ibkr_contact_allowed,
            "blockers": artifact_verdict.blockers,
            "artifact_id_present": !matrix.phase2_gate_artifact.artifact_id.is_empty(),
            "sealed": matrix.phase2_gate_artifact.sealed,
            "raw_artifact_hash_present": !matrix.phase2_gate_artifact.raw_artifact_hash.is_empty(),
            "redacted_summary_hash_present": !matrix.phase2_gate_artifact.redacted_summary_hash.is_empty(),
        },
        "session_attestation": {
            "expected_contract_id": IBKR_SESSION_ATTESTATION_CONTRACT_ID,
            "contract_id": &matrix.session_attestation.contract_id,
            "source_version": matrix.session_attestation.source_version,
            "status": matrix.session_attestation.status,
            "attestation_accepted": session_verdict.attestation_accepted,
            "blockers": session_verdict.blockers,
            "environment": matrix.session_attestation.environment,
            "account_fingerprint_present": !matrix.session_attestation.account_fingerprint.is_empty(),
            "account_fingerprint_is_live": matrix.session_attestation.account_fingerprint_is_live,
            "secret_slot_fingerprint_present": !matrix.session_attestation.secret_slot_fingerprint.is_empty(),
            "api_server_version_present": !matrix.session_attestation.api_server_version.is_empty(),
            "raw_artifact_hash_present": !matrix.session_attestation.raw_artifact_hash.is_empty(),
        },
        "authorization_envelope": {
            "asset_lane": envelope.asset_lane,
            "broker": envelope.broker,
            "environment": envelope.environment,
            "permission_scope": envelope.permission_scope,
            "secret_slot_fingerprint_present": !envelope.secret_slot_fingerprint.is_empty(),
            "account_fingerprint_hash_present": !envelope.account_fingerprint_hash.is_empty(),
            "risk_config_hash_present": !envelope.risk_config_hash.is_empty(),
            "expires_at_ms": envelope.expires_at_ms,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "stock_live_disabled": true,
        "paper_order_entry_visible": false,
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
        "readonly_probe_request": readonly_probe_request_summary(),
        "immutable_pass_artifact_present": false,
        "first_ibkr_contact_allowed": false,
        "connector_enabled": false,
        "secret_slot_touched": false,
        "order_routed": false,
    })
}

fn readonly_probe_request_summary() -> serde_json::Value {
    serde_json::json!({
        "contract_id": STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
        "source_version": 1,
        "request_artifact_present": false,
        "request_validated": false,
        "accepted_for_contact": false,
        "status": "blocked_no_request_artifact",
        "blockers": ["phase2_gate_not_accepted", "probe_request_artifact_missing"],
        "ibkr_contact_performed": false,
        "connector_runtime_started": false,
        "secret_content_serialized": false,
        "order_routed": false,
        "paper_order_submitted": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "bybit_path_reused": false,
        "live_or_tiny_live_authorized": false,
    })
}

fn connector_skeleton_summary() -> serde_json::Value {
    serde_json::json!({
        "surface_id": "ibkr_stock_etf_readonly_connector_skeleton_v1",
        "accepted": false,
        "status": "blocked_source_only",
        "blockers": ["phase2_gate_not_accepted"],
        "network_contact_performed": false,
        "secret_content_loaded": false,
        "paper_channel_exposed": false,
        "live_channel_exposed": false,
        "order_write_method_present": false,
        "bybit_path_reused": false,
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
        "stock_etf.preview_readonly_probe" => Some(BrokerOperation::HealthRead),
        _ => None,
    }
}

fn operation_for_method_and_params(
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

fn paper_request_envelope_summary(
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

fn fill_import_request_summary(
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

fn shadow_signal_request_summary(
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

fn readonly_probe_request_ipc_summary(
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
