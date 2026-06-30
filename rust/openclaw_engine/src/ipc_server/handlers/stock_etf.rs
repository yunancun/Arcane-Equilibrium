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
    StockEtfInstrumentIdentityV1, StockEtfLaneScopedIpcMethod, StockEtfPaperFillImportRequestV1,
    StockEtfPaperOrderRequestEnvelopeV1, StockEtfPaperShadowReconciliationV1,
    StockEtfPhase0ContractPacketManifestV1, StockEtfPitUniverseV1, StockEtfReferenceDataSourcesV1,
    StockEtfReleasePacketV1, StockEtfRiskPolicyV1, StockEtfScorecardDerivationV1,
    StockEtfScorecardVerdictV1, StockEtfShadowSignalRequestV1, StockEtfStrategyHypothesisV1,
    StockMarketDataProvenanceV1, StockShadowFillModelV1, TinyLiveAdrEligibilityV1,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_PAPER_ATTESTATION_CONTRACT_ID, IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
    IBKR_SECRET_SLOT_CONTRACT_ID, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID, STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID,
    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID, STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID,
    STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID, STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID, STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID,
    STOCK_ETF_RELEASE_PACKET_CONTRACT_ID, STOCK_ETF_RISK_POLICY_CONTRACT_ID,
    STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID, STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID,
    STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID, STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
    STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID, STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID,
    STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
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
            let allowed = decision.allowed
                && request_envelope_accepted_for_ipc
                && fill_import_request_accepted_for_ipc
                && shadow_signal_request_accepted_for_ipc;
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

fn account_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let cash_ledger = BrokerAccountPortfolioCashLedgerV1::default();
    let cash_ledger_verdict = cash_ledger.validate();
    let session_attestation = IbkrSessionAttestationV1::default();
    let session_attestation_verdict = session_attestation.validate(0);
    let paper_attestation_policy = IbkrPaperAttestationPolicyV1::source_template();
    let paper_attestation_policy_verdict = paper_attestation_policy.validate();

    serde_json::json!({
        "phase": "phase2_account_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_readonly",
        "account_status_state": "blocked",
        "phase2_started": false,
        "readonly_account_snapshot_started": false,
        "paper_account_snapshot_started": false,
        "account_snapshot_present": false,
        "portfolio_positions_snapshot_present": false,
        "cash_ledger_present": false,
        "paper_account_attestation_present": false,
        "session_attestation_present": false,
        "connector_runtime_started": false,
        "gateway_socket_open": false,
        "account_snapshot": {
            "expected_contract_id": BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID,
            "contract_id": cash_ledger.contract_id,
            "source_version": cash_ledger.source_version,
            "accepted": cash_ledger_verdict.accepted,
            "blockers": cash_ledger_verdict.blockers,
            "account_fingerprint_hash_present": !cash_ledger.account_fingerprint_hash.is_empty(),
            "account_snapshot_hash_present": !cash_ledger.account_snapshot_hash.is_empty(),
            "portfolio_positions_hash_present": !cash_ledger.portfolio_positions_hash.is_empty(),
            "currency": cash_ledger.currency,
            "cash_balance_minor_units": cash_ledger.cash_balance_minor_units,
            "buying_power_minor_units": cash_ledger.buying_power_minor_units,
            "as_of_ms": cash_ledger.as_of_ms,
            "source_report_hash_present": !cash_ledger.source_report_hash.is_empty(),
        },
        "session_attestation": {
            "expected_contract_id": IBKR_SESSION_ATTESTATION_CONTRACT_ID,
            "contract_id": session_attestation.contract_id,
            "source_version": session_attestation.source_version,
            "status": session_attestation.status,
            "accepted": session_attestation_verdict.attestation_accepted,
            "blockers": session_attestation_verdict.blockers,
            "account_fingerprint_present": !session_attestation.account_fingerprint.is_empty(),
            "account_fingerprint_is_live": session_attestation.account_fingerprint_is_live,
            "environment": session_attestation.environment,
            "host": session_attestation.host,
            "port": session_attestation.port,
            "process_identity_present": !session_attestation.process_identity.is_empty(),
            "gateway_mode": session_attestation.gateway_mode,
            "secret_slot_fingerprint_present": !session_attestation.secret_slot_fingerprint.is_empty(),
            "secret_slot_mode": session_attestation.secret_slot_mode,
            "secret_world_readable": session_attestation.secret_world_readable,
            "live_secret_absent_or_empty": session_attestation.live_secret_absent_or_empty,
            "env_var_credential_fallback_used": session_attestation.env_var_credential_fallback_used,
            "api_server_version_present": !session_attestation.api_server_version.is_empty(),
            "attested_at_ms": session_attestation.attested_at_ms,
            "expires_at_ms": session_attestation.expires_at_ms,
            "raw_artifact_hash_present": !session_attestation.raw_artifact_hash.is_empty(),
        },
        "paper_attestation_policy": {
            "expected_contract_id": IBKR_PAPER_ATTESTATION_CONTRACT_ID,
            "contract_id": paper_attestation_policy.contract_id,
            "source_version": paper_attestation_policy.source_version,
            "accepted": paper_attestation_policy_verdict.accepted,
            "blockers": paper_attestation_policy_verdict.blockers,
            "external_surface_gate_required": paper_attestation_policy.external_surface_gate_required,
            "session_attestation_required": paper_attestation_policy.session_attestation_required,
            "rust_lane_scoped_ipc_required": paper_attestation_policy.rust_lane_scoped_ipc_required,
            "decision_lease_required": paper_attestation_policy.decision_lease_required,
            "guardian_required": paper_attestation_policy.guardian_required,
            "paper_environment_only": paper_attestation_policy.paper_environment_only,
            "live_account_fingerprint_denied": paper_attestation_policy.live_account_fingerprint_denied,
            "margin_short_options_cfd_denied": paper_attestation_policy.margin_short_options_cfd_denied,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
        "db_apply_performed": false,
    })
}

fn reconciliation_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let lifecycle_event = BrokerLifecycleEventLogV1::default();
    let lifecycle_verdict = lifecycle_event.validate();
    let shadow_fill_model = StockShadowFillModelV1::default();
    let shadow_fill_verdict = shadow_fill_model.validate();
    let reconciliation = StockEtfPaperShadowReconciliationV1::default();
    let reconciliation_verdict = reconciliation.validate();
    let matching = serde_json::json!({
        "expected_lifecycle_contract_id": IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
        "lifecycle_contract_id": lifecycle_event.lifecycle_contract_id,
        "expected_event_log_contract_id": BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
        "event_log_contract_id": lifecycle_event.event_log_contract_id,
        "expected_shadow_contract_id": STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
        "shadow_contract_id": shadow_fill_model.contract_id,
        "expected_reconciliation_contract_id": STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID,
        "reconciliation_contract_id": reconciliation.contract_id,
        "reconciliation_accepted": reconciliation_verdict.accepted,
        "reconciliation_blockers": reconciliation_verdict.blockers,
        "lifecycle_event_accepted": lifecycle_verdict.accepted,
        "shadow_fill_model_accepted": shadow_fill_verdict.accepted,
        "lifecycle_blockers": lifecycle_verdict.blockers,
        "shadow_blockers": shadow_fill_verdict.blockers,
        "append_only_event_ready": lifecycle_verdict.accepted,
        "paper_order_id_present": !lifecycle_event.order_local_id.is_empty(),
        "broker_order_id_present": !lifecycle_event.broker_order_id.is_empty(),
        "execution_id_present": !lifecycle_event.execution_id.is_empty(),
        "commission_report_id_present": !lifecycle_event.commission_report_id.is_empty(),
        "shadow_signal_id_present": !shadow_fill_model.signal_id.is_empty(),
        "shadow_fill_price_present": shadow_fill_model.conservative_fill_price_micros > 0,
        "paper_shadow_link_present": shadow_fill_model.broker_paper_fill_linked,
        "divergence_bps": 0,
        "divergence_threshold_bps": 0,
        "divergence_within_threshold": false,
        "unmatched_paper_fill_count": 0,
        "unmatched_shadow_fill_count": 0,
        "reconciliation_run_id_present": !lifecycle_event.reconciliation_run_id.is_empty(),
        "contract_reconciliation_run_id_present": !reconciliation.reconciliation_run_id.is_empty(),
        "paper_shadow_link_hash_present": !reconciliation.paper_shadow_link_hash.is_empty(),
        "paper_fill_imported": reconciliation.paper_fill_imported,
        "shadow_fill_synthetic": reconciliation.shadow_fill_synthetic,
        "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
        "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
        "reconciliation_writer_started": reconciliation.reconciliation_writer_started,
        "ibkr_contact_performed": reconciliation.ibkr_contact_performed,
        "connector_runtime_started": reconciliation.connector_runtime_started,
        "secret_content_serialized": reconciliation.secret_content_serialized,
        "fill_import_performed": reconciliation.fill_import_performed,
        "shadow_fill_generated": reconciliation.shadow_fill_generated,
    });

    serde_json::json!({
        "phase": "phase3_reconciliation_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "reconciliation_status_state": "blocked",
        "phase3_started": false,
        "paper_shadow_reconciliation_started": false,
        "paper_orders_ready": false,
        "paper_fills_ready": false,
        "shadow_fills_ready": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "matching": matching,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn scorecard_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let derivation = StockEtfScorecardDerivationV1::default();
    let derivation_verdict = derivation.validate();
    let verdict = StockEtfScorecardVerdictV1::default();
    let scorecard_verdict = verdict.validate();
    let derivation = serde_json::json!({
        "expected_contract_id": STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID,
        "contract_id": &derivation.contract_id,
        "source_version": derivation.source_version,
        "accepted": derivation_verdict.accepted,
        "blockers": derivation_verdict.blockers,
        "derivation_run_id_present": !derivation.derivation_run_id.is_empty(),
        "strategy_id_present": !derivation.strategy_id.is_empty(),
        "universe_version_present": !derivation.universe_version.is_empty(),
        "benchmark_version_present": !derivation.benchmark_version.is_empty(),
        "as_of_date_present": !derivation.as_of_date.is_empty(),
        "scorecard_input_bundle_hash_present": !derivation.scorecard_input_bundle_hash.is_empty(),
        "paper_shadow_reconciliation_hash_present": !derivation.paper_shadow_reconciliation_hash.is_empty(),
        "scorecard_verdict_hash_present": !derivation.scorecard_verdict_hash.is_empty(),
        "output_artifact_hash_present": !derivation.output_artifact_hash.is_empty(),
        "derived_from_atomic_facts_only": derivation.derived_from_atomic_facts_only,
        "idempotent_replay_proven": derivation.idempotent_replay_proven,
        "paper_and_shadow_fills_separate": derivation.paper_and_shadow_fills_separate,
        "bybit_live_execution_unchanged": derivation.bybit_live_execution_unchanged,
        "ibkr_contact_performed": derivation.ibkr_contact_performed,
        "connector_runtime_started": derivation.connector_runtime_started,
        "broker_fill_import_performed": derivation.broker_fill_import_performed,
        "shadow_fill_generated": derivation.shadow_fill_generated,
        "reconciliation_writer_started": derivation.reconciliation_writer_started,
        "scorecard_writer_started": derivation.scorecard_writer_started,
        "db_apply_performed": derivation.db_apply_performed,
        "evidence_clock_started": derivation.evidence_clock_started,
        "secret_content_serialized": derivation.secret_content_serialized,
        "live_or_tiny_live_authorized": derivation.live_or_tiny_live_authorized,
        "sealed": derivation.sealed,
    });
    let mut scorecard = serde_json::Map::new();
    macro_rules! put_scorecard {
        ($key:literal, $value:expr) => {
            scorecard.insert($key.to_string(), serde_json::json!($value));
        };
    }
    put_scorecard!(
        "expected_contract_id",
        STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID
    );
    put_scorecard!("contract_id", &verdict.contract_id);
    put_scorecard!("source_version", verdict.source_version);
    put_scorecard!("accepted", scorecard_verdict.accepted);
    put_scorecard!("blockers", scorecard_verdict.blockers);
    put_scorecard!("verdict_label", verdict.verdict_label);
    put_scorecard!(
        "scorecard_input_bundle_hash_present",
        !verdict.scorecard_input_bundle_hash.is_empty()
    );
    put_scorecard!(
        "evidence_clock_manifest_hash_present",
        !verdict.evidence_clock_manifest_hash.is_empty()
    );
    put_scorecard!(
        "dq_manifest_hash_present",
        !verdict.dq_manifest_hash.is_empty()
    );
    put_scorecard!(
        "formula_appendix_hash_present",
        !verdict.formula_appendix_hash.is_empty()
    );
    put_scorecard!(
        "statistical_preregistration_hash_present",
        !verdict.statistical_preregistration_hash.is_empty()
    );
    put_scorecard!(
        "benchmark_version_hash_present",
        !verdict.benchmark_version_hash.is_empty()
    );
    put_scorecard!(
        "cost_model_version_hash_present",
        !verdict.cost_model_version_hash.is_empty()
    );
    put_scorecard!(
        "strategy_hypothesis_hash_present",
        !verdict.strategy_hypothesis_hash.is_empty()
    );
    put_scorecard!(
        "reference_data_sources_hash_present",
        !verdict.reference_data_sources_hash.is_empty()
    );
    put_scorecard!(
        "paper_shadow_reconciliation_hash_present",
        !verdict.paper_shadow_reconciliation_hash.is_empty()
    );
    put_scorecard!(
        "scorecard_manifest_hash_present",
        !verdict.scorecard_manifest_hash.is_empty()
    );
    put_scorecard!(
        "verdict_rationale_hash_present",
        !verdict.verdict_rationale_hash.is_empty()
    );
    put_scorecard!(
        "paper_shadow_window_trading_days",
        verdict.paper_shadow_window_trading_days
    );
    put_scorecard!("min_window_trading_days", verdict.min_window_trading_days);
    put_scorecard!(
        "independent_observation_count",
        verdict.independent_observation_count
    );
    put_scorecard!(
        "min_independent_observation_count",
        verdict.min_independent_observation_count
    );
    put_scorecard!("gross_pnl_minor_units", verdict.gross_pnl_minor_units);
    put_scorecard!("net_pnl_minor_units", verdict.net_pnl_minor_units);
    put_scorecard!("commission_minor_units", verdict.commission_minor_units);
    put_scorecard!(
        "spread_slippage_minor_units",
        verdict.spread_slippage_minor_units
    );
    put_scorecard!("fx_drag_minor_units", verdict.fx_drag_minor_units);
    put_scorecard!("tax_drag_minor_units", verdict.tax_drag_minor_units);
    put_scorecard!("benchmark_excess_lcb_bps", verdict.benchmark_excess_lcb_bps);
    put_scorecard!(
        "conservative_cost_stress_lcb_bps",
        verdict.conservative_cost_stress_lcb_bps
    );
    put_scorecard!(
        "paper_shadow_divergence_bps",
        verdict.paper_shadow_divergence_bps
    );
    put_scorecard!(
        "max_paper_shadow_divergence_bps",
        verdict.max_paper_shadow_divergence_bps
    );
    put_scorecard!("psr_bps", verdict.psr_bps);
    put_scorecard!("min_psr_bps", verdict.min_psr_bps);
    put_scorecard!("dsr_bps", verdict.dsr_bps);
    put_scorecard!("min_dsr_bps", verdict.min_dsr_bps);
    put_scorecard!(
        "concentration_label_passed",
        verdict.concentration_label_passed
    );
    put_scorecard!("regime_label_passed", verdict.regime_label_passed);
    put_scorecard!("breadth_label_passed", verdict.breadth_label_passed);
    put_scorecard!("freshness_label_passed", verdict.freshness_label_passed);
    put_scorecard!(
        "survivorship_label_passed",
        verdict.survivorship_label_passed
    );
    put_scorecard!(
        "execution_realism_label_passed",
        verdict.execution_realism_label_passed
    );
    put_scorecard!("qc_review_hash_present", !verdict.qc_review_hash.is_empty());
    put_scorecard!(
        "mit_review_hash_present",
        !verdict.mit_review_hash.is_empty()
    );
    put_scorecard!("qa_review_hash_present", !verdict.qa_review_hash.is_empty());
    put_scorecard!("qc_review_passed", verdict.qc_review_passed);
    put_scorecard!("mit_review_passed", verdict.mit_review_passed);
    put_scorecard!("qa_review_passed", verdict.qa_review_passed);
    put_scorecard!(
        "scorecard_is_derived_only",
        verdict.scorecard_is_derived_only
    );
    put_scorecard!(
        "paper_and_shadow_fills_separate",
        verdict.paper_and_shadow_fills_separate
    );
    put_scorecard!("live_fill_claimed", verdict.live_fill_claimed);
    put_scorecard!(
        "bybit_live_execution_unchanged",
        verdict.bybit_live_execution_unchanged
    );
    put_scorecard!("sealed", verdict.sealed);
    let scorecard = serde_json::Value::Object(scorecard);

    serde_json::json!({
        "phase": "phase3_scorecard_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "scorecard_status_state": "blocked",
        "phase3_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "paper_shadow_window_complete": false,
        "scorecard_derivation": derivation,
        "scorecard": scorecard,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
        "live_or_tiny_live_authorized": false,
    })
}

fn launch_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let release_packet = StockEtfReleasePacketV1::default();
    let release_verdict = release_packet.validate();
    let disable_cleanup = StockEtfDisableCleanupRunbookV1::default();
    let disable_verdict = disable_cleanup.validate();
    let tiny_live = TinyLiveAdrEligibilityV1::default();
    let tiny_live_verdict = tiny_live.validate();

    serde_json::json!({
        "phase": "phase5_launch_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "launch_status_state": "blocked",
        "phase3_started": false,
        "phase5_started": false,
        "release_packet": {
            "expected_contract_id": STOCK_ETF_RELEASE_PACKET_CONTRACT_ID,
            "packet_id": release_packet.packet_id,
            "source_version": release_packet.source_version,
            "accepted": release_verdict.accepted,
            "blockers": release_verdict.blockers,
            "paper_shadow_window_complete": release_packet.paper_shadow_window_complete,
            "engineering_shakedown_complete": release_packet.engineering_shakedown_complete,
            "role_report_count": release_packet.role_report_paths.len(),
            "manifest_hash_count": release_packet.manifest_hashes.len(),
            "gui_screenshot_hash_count": release_packet.gui_screenshot_hashes.len(),
            "dq_manifest_hash_count": release_packet.dq_manifest_hashes.len(),
            "scorecard_regeneration_hash_count": release_packet.scorecard_regeneration_hashes.len(),
            "pg_migrations_declared": release_packet.pg_migration_evidence.migrations_declared,
            "pg_dry_run_log_hash_present": !release_packet.pg_migration_evidence.pg_dry_run_log_hash.is_empty(),
            "pg_double_apply_log_hash_present": !release_packet.pg_migration_evidence.pg_double_apply_log_hash.is_empty(),
            "redaction_fixture_hash_present": !release_packet.redaction_fixture_hash.is_empty(),
            "evidence_archive_pointer_present": !release_packet.evidence_archive_pointer.is_empty(),
            "evidence_archive_hash_present": !release_packet.evidence_archive_hash.is_empty(),
            "secret_content_serialized": release_packet.secret_content_serialized,
            "ibkr_live_or_tiny_live_authorized": release_packet.ibkr_live_or_tiny_live_authorized,
            "sealed": release_packet.sealed,
        },
        "disable_cleanup_runbook": {
            "expected_runbook_id": STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID,
            "runbook_id": disable_cleanup.runbook_id,
            "source_version": disable_cleanup.source_version,
            "accepted": disable_verdict.accepted,
            "blockers": disable_verdict.blockers,
            "bybit_live_execution_unchanged": disable_cleanup.bybit_live_execution_unchanged,
            "env_flag_count": disable_cleanup.env_flags.len(),
            "proof_count": disable_cleanup.proofs.len(),
            "ibkr_contact_performed": disable_cleanup.ibkr_contact_performed,
            "connector_runtime_started": disable_cleanup.connector_runtime_started,
            "paper_order_routed": disable_cleanup.paper_order_routed,
            "secret_slot_created": disable_cleanup.secret_slot_created,
            "secret_content_serialized": disable_cleanup.secret_content_serialized,
            "destructive_db_cleanup_requested": disable_cleanup.destructive_db_cleanup_requested,
            "db_delete_or_truncate_allowed": disable_cleanup.db_delete_or_truncate_allowed,
            "paper_shadow_launch_authorized": disable_cleanup.paper_shadow_launch_authorized,
            "tiny_live_authorized": disable_cleanup.tiny_live_authorized,
            "live_authorized": disable_cleanup.live_authorized,
        },
        "tiny_live_adr_eligibility": {
            "expected_contract_id": STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID,
            "contract_id": tiny_live.contract_id,
            "source_version": tiny_live.source_version,
            "accepted": tiny_live_verdict.accepted,
            "blockers": tiny_live_verdict.blockers,
            "decision": tiny_live.decision,
            "scorecard_derivation_hash_present": !tiny_live.scorecard_derivation_hash.is_empty(),
            "scorecard_verdict_hash_present": !tiny_live.scorecard_verdict_hash.is_empty(),
            "scorecard_manifest_hash_present": !tiny_live.scorecard_manifest_hash.is_empty(),
            "paper_shadow_reconciliation_hash_present": !tiny_live.paper_shadow_reconciliation_hash.is_empty(),
            "dq_manifest_hash_present": !tiny_live.dq_manifest_hash.is_empty(),
            "statistical_preregistration_hash_present": !tiny_live.statistical_preregistration_hash.is_empty(),
            "qc_review_hash_present": !tiny_live.qc_review_hash.is_empty(),
            "mit_review_hash_present": !tiny_live.mit_review_hash.is_empty(),
            "qa_review_hash_present": !tiny_live.qa_review_hash.is_empty(),
            "paper_shadow_window_complete": tiny_live.paper_shadow_window_complete,
            "benchmark_relative_after_cost_lcb_bps": tiny_live.benchmark_relative_after_cost_lcb_bps,
            "independent_observation_count": tiny_live.independent_observation_count,
            "min_independent_observation_count": tiny_live.min_independent_observation_count,
            "conservative_cost_stress_lcb_bps": tiny_live.conservative_cost_stress_lcb_bps,
            "paper_shadow_divergence_bps": tiny_live.paper_shadow_divergence_bps,
            "max_paper_shadow_divergence_bps": tiny_live.max_paper_shadow_divergence_bps,
            "concentration_label_passed": tiny_live.concentration_label_passed,
            "regime_label_passed": tiny_live.regime_label_passed,
            "freshness_label_passed": tiny_live.freshness_label_passed,
            "qc_review_passed": tiny_live.qc_review_passed,
            "mit_review_passed": tiny_live.mit_review_passed,
            "qa_review_passed": tiny_live.qa_review_passed,
            "secret_content_serialized": tiny_live.secret_content_serialized,
            "sealed": tiny_live.sealed,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "paper_shadow_launch_authorized": false,
        "tiny_live_or_live_authorized": false,
        "connector_runtime_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn disable_cleanup_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let runbook = StockEtfDisableCleanupRunbookV1::accepted_fixture();
    let verdict = runbook.validate();
    let env_flags: Vec<serde_json::Value> = runbook
        .env_flags
        .iter()
        .map(|flag| {
            serde_json::json!({
                "name": flag.name,
                "expected_value": flag.expected_value,
                "observed_value": flag.observed_value,
                "evidence_hash_present": !flag.evidence_hash.is_empty(),
            })
        })
        .collect();
    let proofs: Vec<serde_json::Value> = runbook
        .proofs
        .iter()
        .map(|proof| {
            serde_json::json!({
                "kind": proof.kind,
                "verified": proof.verified,
                "evidence_hash_present": !proof.evidence_hash.is_empty(),
                "grants_runtime_authority": proof.grants_runtime_authority,
                "destructive_cleanup_claimed": proof.destructive_cleanup_claimed,
            })
        })
        .collect();

    serde_json::json!({
        "phase": "phase5_disable_cleanup_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "disable_cleanup_status_state": "source_ready_runtime_blocked",
        "phase3_started": false,
        "phase5_started": false,
        "collector_stop_requested": false,
        "gui_disable_requested": false,
        "evidence_archive_requested": false,
        "db_cleanup_requested": false,
        "runbook": {
            "expected_runbook_id": STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID,
            "runbook_id": runbook.runbook_id,
            "source_version": runbook.source_version,
            "accepted": verdict.accepted,
            "blockers": verdict.blockers,
            "source_artifact_hash_present": !runbook.source_artifact_hash.is_empty(),
            "bybit_live_execution_unchanged": runbook.bybit_live_execution_unchanged,
            "env_flag_count": runbook.env_flags.len(),
            "proof_count": runbook.proofs.len(),
            "env_flags": env_flags,
            "proofs": proofs,
            "ibkr_contact_performed": runbook.ibkr_contact_performed,
            "connector_runtime_started": runbook.connector_runtime_started,
            "paper_order_routed": runbook.paper_order_routed,
            "secret_slot_created": runbook.secret_slot_created,
            "secret_content_serialized": runbook.secret_content_serialized,
            "destructive_db_cleanup_requested": runbook.destructive_db_cleanup_requested,
            "db_delete_or_truncate_allowed": runbook.db_delete_or_truncate_allowed,
            "paper_shadow_launch_authorized": runbook.paper_shadow_launch_authorized,
            "tiny_live_authorized": runbook.tiny_live_authorized,
            "live_authorized": runbook.live_authorized,
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "paper_shadow_launch_authorized": false,
        "tiny_live_or_live_authorized": false,
        "connector_runtime_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn release_packet_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let packet = StockEtfReleasePacketV1::accepted_fixture();
    let verdict = packet.validate();
    let manifest_hashes: Vec<serde_json::Value> = packet
        .manifest_hashes
        .iter()
        .map(|entry| {
            serde_json::json!({
                "label": entry.label,
                "hash_present": !entry.sha256.is_empty(),
            })
        })
        .collect();
    let kill = &packet.kill_disable_cleanup_proof;
    let kill_disable_cleanup_proof = serde_json::json!({
        "stock_etf_lane_enabled_false": kill.stock_etf_lane_enabled_false,
        "ibkr_readonly_enabled_false": kill.ibkr_readonly_enabled_false,
        "ibkr_paper_enabled_false": kill.ibkr_paper_enabled_false,
        "stock_etf_shadow_only_true": kill.stock_etf_shadow_only_true,
        "collector_stopped": kill.collector_stopped,
        "gui_stock_views_disabled_or_hidden": kill.gui_stock_views_disabled_or_hidden,
        "live_secret_absence_proven": kill.live_secret_absence_proven,
        "evidence_archive_forward_only": kill.evidence_archive_forward_only,
        "destructive_db_cleanup_requested": kill.destructive_db_cleanup_requested,
        "proof_hash_present": !kill.proof_hash.is_empty(),
    });
    let release_packet = serde_json::json!({
        "expected_contract_id": STOCK_ETF_RELEASE_PACKET_CONTRACT_ID,
        "packet_id": &packet.packet_id,
        "source_version": packet.source_version,
        "accepted": verdict.accepted,
        "blockers": &verdict.blockers,
        "adr_path": &packet.adr_path,
        "amd_path": &packet.amd_path,
        "spec_path": &packet.spec_path,
        "source_commit_present": !packet.source_commit.is_empty(),
        "created_at_ms": packet.created_at_ms,
        "reviewer_role_count": packet.reviewer_roles.len(),
        "reviewer_roles": &packet.reviewer_roles,
        "role_report_count": packet.role_report_paths.len(),
        "e2_log_hash_present": !packet.e2_log_hash.is_empty(),
        "e3_redaction_log_hash_present": !packet.e3_redaction_log_hash.is_empty(),
        "e4_log_hash_present": !packet.e4_log_hash.is_empty(),
        "qa_log_hash_present": !packet.qa_log_hash.is_empty(),
        "manifest_hash_count": packet.manifest_hashes.len(),
        "manifest_hashes": manifest_hashes,
        "pg_migrations_declared": packet.pg_migration_evidence.migrations_declared,
        "pg_migration_manifest_hash_present": !packet.pg_migration_evidence.migration_manifest_hash.is_empty(),
        "pg_dry_run_log_hash_present": !packet.pg_migration_evidence.pg_dry_run_log_hash.is_empty(),
        "pg_double_apply_log_hash_present": !packet.pg_migration_evidence.pg_double_apply_log_hash.is_empty(),
        "redaction_fixture_hash_present": !packet.redaction_fixture_hash.is_empty(),
        "gui_screenshot_hash_count": packet.gui_screenshot_hashes.len(),
        "dq_manifest_hash_count": packet.dq_manifest_hashes.len(),
        "scorecard_regeneration_hash_count": packet.scorecard_regeneration_hashes.len(),
        "evidence_archive_pointer_present": !packet.evidence_archive_pointer.is_empty(),
        "evidence_archive_hash_present": !packet.evidence_archive_hash.is_empty(),
        "paper_shadow_window_complete": packet.paper_shadow_window_complete,
        "engineering_shakedown_complete": packet.engineering_shakedown_complete,
        "secret_content_serialized": packet.secret_content_serialized,
        "ibkr_live_or_tiny_live_authorized": packet.ibkr_live_or_tiny_live_authorized,
        "sealed": packet.sealed,
        "kill_disable_cleanup_proof": kill_disable_cleanup_proof,
    });

    serde_json::json!({
        "phase": "phase5_release_packet_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": "paper_shadow",
        "release_packet_status_state": "source_ready_runtime_blocked",
        "phase3_started": false,
        "phase5_started": false,
        "release_packet": release_packet,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "paper_shadow_launch_authorized": false,
        "tiny_live_or_live_authorized": false,
        "connector_runtime_started": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "evidence_clock_started": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn paper_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let lifecycle_event = BrokerLifecycleEventLogV1::default();
    let lifecycle_verdict = lifecycle_event.validate();
    let lifecycle_event_summary = serde_json::json!({
        "expected_lifecycle_contract_id": IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
        "lifecycle_contract_id": lifecycle_event.lifecycle_contract_id,
        "expected_event_log_contract_id": BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
        "event_log_contract_id": lifecycle_event.event_log_contract_id,
        "expected_request_contract_id": STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
        "request_contract_id": lifecycle_event.request_contract_id,
        "source_version": lifecycle_event.source_version,
        "accepted": lifecycle_verdict.accepted,
        "blockers": lifecycle_verdict.blockers,
        "operation": lifecycle_event.operation,
        "previous_state": lifecycle_event.previous_state,
        "next_state": lifecycle_event.next_state,
        "allowed": lifecycle_event.allowed,
        "denial_reason": lifecycle_event.denial_reason,
        "event_id_present": !lifecycle_event.event_id.is_empty(),
        "event_sequence": lifecycle_event.event_sequence,
        "event_sequence_present": lifecycle_event.event_sequence > 0,
        "genesis_event": lifecycle_event.genesis_event,
        "event_time_ms": lifecycle_event.event_time_ms,
        "previous_event_hash_present": !lifecycle_event.previous_event_hash.is_empty(),
        "event_hash_present": !lifecycle_event.event_hash.is_empty(),
        "request_envelope_hash_present": !lifecycle_event.request_envelope_hash.is_empty(),
        "stale_state_policy": lifecycle_event.stale_state_policy,
        "stale_state_policy_present": lifecycle_event.stale_state_policy.is_some(),
        "order_local_id_present": !lifecycle_event.order_local_id.is_empty(),
        "idempotency_key_present": !lifecycle_event.idempotency_key.is_empty(),
        "broker_order_id_present": !lifecycle_event.broker_order_id.is_empty(),
        "execution_id_present": !lifecycle_event.execution_id.is_empty(),
        "commission_report_id_present": !lifecycle_event.commission_report_id.is_empty(),
        "reconciliation_run_id_present": !lifecycle_event.reconciliation_run_id.is_empty(),
        "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
        "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
    });
    let reconstructability_summary = serde_json::json!({
        "append_only_event_ready": lifecycle_verdict.accepted,
        "event_hash_chain_ready": lifecycle_verdict.accepted,
        "request_envelope_linked": lifecycle_verdict.accepted,
        "stale_state_policy_present": lifecycle_event.stale_state_policy.is_some(),
        "broker_order_id_present": !lifecycle_event.broker_order_id.is_empty(),
        "execution_id_present": !lifecycle_event.execution_id.is_empty(),
        "commission_report_id_present": !lifecycle_event.commission_report_id.is_empty(),
        "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
        "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
        "restart_recovery_required": false,
        "manual_review_required": false,
    });

    serde_json::json!({
        "phase": "phase2_paper_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "paper_status_state": "blocked",
        "phase2_started": false,
        "paper_lifecycle_started": false,
        "paper_order_submitted": false,
        "paper_fill_imported": false,
        "paper_reconciliation_started": false,
        "paper_account_snapshot_present": false,
        "broker_paper_attestation_present": false,
        "lifecycle_event": lifecycle_event_summary,
        "reconstructability": reconstructability_summary,
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
        "db_apply_performed": false,
    })
}

fn shadow_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let shadow_fill_model = StockShadowFillModelV1::default();
    let shadow_fill_verdict = shadow_fill_model.validate();
    let strategy_hypothesis = StockEtfStrategyHypothesisV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        no_options_cfd_margin_short: true,
        paper_shadow_only: true,
        bybit_live_execution_unchanged: true,
        ibkr_live_denied: true,
        ..StockEtfStrategyHypothesisV1::default()
    };
    let strategy_hypothesis_verdict = strategy_hypothesis.validate();

    serde_json::json!({
        "phase": "phase3_shadow_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Shadow,
        "shadow_status_state": "blocked",
        "phase3_started": false,
        "shadow_fill_model": {
            "expected_contract_id": STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
            "contract_id": shadow_fill_model.contract_id,
            "source_version": shadow_fill_model.source_version,
            "accepted": shadow_fill_verdict.accepted,
            "blockers": shadow_fill_verdict.blockers,
            "signal_id": shadow_fill_model.signal_id,
            "side": shadow_fill_model.side,
            "intended_notional_minor_units": shadow_fill_model.intended_notional_minor_units,
            "market_session_id": shadow_fill_model.market_session_id,
            "quote_or_bar_source_hash_present": !shadow_fill_model.quote_or_bar_source_hash.is_empty(),
            "conservative_fill_price_micros": shadow_fill_model.conservative_fill_price_micros,
            "spread_bps": shadow_fill_model.spread_bps,
            "slippage_bps": shadow_fill_model.slippage_bps,
            "cost_bps": shadow_fill_model.cost_bps,
            "rejection_reason": shadow_fill_model.rejection_reason,
            "synthetic_shadow": shadow_fill_model.synthetic_shadow,
            "broker_paper_fill_linked": shadow_fill_model.broker_paper_fill_linked,
            "live_fill_linked": shadow_fill_model.live_fill_linked,
        },
        "strategy_hypothesis": {
            "expected_contract_id": STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
            "contract_id": strategy_hypothesis.contract_id,
            "source_version": strategy_hypothesis.source_version,
            "accepted": strategy_hypothesis_verdict.accepted,
            "blockers": strategy_hypothesis_verdict.blockers,
            "hypothesis_id": strategy_hypothesis.hypothesis_id,
            "hypothesis_version": strategy_hypothesis.hypothesis_version,
            "strategy_family": strategy_hypothesis.strategy_family,
            "primary_timeframe": strategy_hypothesis.primary_timeframe,
            "instrument_scope": strategy_hypothesis.instrument_scope,
            "paper_shadow_only": strategy_hypothesis.paper_shadow_only,
            "profitability_claimed": strategy_hypothesis.profitability_claimed,
            "live_or_tiny_live_authority_claimed": strategy_hypothesis.live_or_tiny_live_authority_claimed,
            "bybit_live_execution_unchanged": strategy_hypothesis.bybit_live_execution_unchanged,
            "ibkr_live_denied": strategy_hypothesis.ibkr_live_denied,
            "ibkr_contact_performed": strategy_hypothesis.ibkr_contact_performed,
            "secret_content_serialized": strategy_hypothesis.secret_content_serialized,
        },
        "phase2": phase2,
        "shadow_collector_started": false,
        "shadow_signal_emitted": false,
        "shadow_fill_generated": false,
        "scorecard_writer_started": false,
        "db_apply_performed": false,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn universe_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let universe = StockEtfPitUniverseV1 {
        asset_lane: AssetLane::StockEtfCash,
        broker: Broker::Ibkr,
        bybit_live_execution_unchanged: true,
        ibkr_live_denied: true,
        ..StockEtfPitUniverseV1::default()
    };
    let universe_verdict = universe.validate();
    let constituents: Vec<serde_json::Value> = universe
        .constituents
        .iter()
        .take(10)
        .map(|constituent| {
            serde_json::json!({
                "symbol": constituent.symbol,
                "instrument_kind": constituent.instrument_kind,
                "listing_venue": constituent.listing_venue,
                "primary_exchange": constituent.primary_exchange,
                "currency": constituent.currency,
                "tradability_status": constituent.tradability_status,
                "priips_kid_status": constituent.priips_kid_status,
                "included": constituent.included,
            })
        })
        .collect();

    serde_json::json!({
        "phase": "phase3_universe_status_source_fixture",
        "asset_lane": AssetLane::StockEtfCash,
        "broker": Broker::Ibkr,
        "environment": BrokerEnvironment::Paper,
        "universe_status_state": "blocked",
        "phase3_started": false,
        "universe": {
            "expected_contract_id": STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
            "contract_id": universe.contract_id,
            "source_version": universe.source_version,
            "accepted": universe_verdict.accepted,
            "blockers": universe_verdict.blockers,
            "universe_id": universe.universe_id,
            "universe_version": universe.universe_version,
            "universe_hash_present": !universe.universe_hash.is_empty(),
            "point_in_time_asof_ms": universe.point_in_time_asof_ms,
            "effective_from_ms": universe.effective_from_ms,
            "effective_to_ms": universe.effective_to_ms,
            "constituent_count": universe.constituent_count,
            "max_constituents": universe.max_constituents,
            "sample_constituents": constituents,
            "frozen_for_evidence_clock": universe.frozen_for_evidence_clock,
            "survivorship_bias_controls_present": universe.survivorship_bias_controls_present,
            "bybit_live_execution_unchanged": universe.bybit_live_execution_unchanged,
            "ibkr_live_denied": universe.ibkr_live_denied,
            "ibkr_contact_performed": universe.ibkr_contact_performed,
            "secret_content_serialized": universe.secret_content_serialized,
        },
        "phase2": phase2,
        "collector_started": false,
        "market_data_ingestion_started": false,
        "db_apply_performed": false,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
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
        _ => None,
    }
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
