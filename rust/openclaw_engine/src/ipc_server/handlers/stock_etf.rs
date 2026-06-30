//! ADR-0048 Stock/ETF lane IPC fixtures.
//!
//! Phase 1 only: these handlers expose lane status/readiness and typed denial
//! previews. They intentionally do not send `PipelineCommand`, do not reuse the
//! Bybit `submit_paper_order` path, and do not contact IBKR.

use super::super::*;
use openclaw_types::{
    evaluate_broker_operation, AssetLane, Broker, BrokerAccountPortfolioCashLedgerV1,
    BrokerCapabilityRequest, BrokerEnvironment, BrokerLifecycleEventLogV1, BrokerOperation,
    IbkrExternalSurfaceGateV1, IbkrPaperAttestationPolicyV1, IbkrPhase2PolicyBundleV1,
    IbkrSessionAttestationV1, InstrumentKind, NonBybitApiAllowlistV1, StockEtfEvidenceClockDayV1,
    StockEtfFeatureFlags, StockEtfGateInputs, StockEtfPitUniverseV1, StockEtfStrategyHypothesisV1,
    StockMarketDataProvenanceV1, StockShadowFillModelV1,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    IBKR_PAPER_ATTESTATION_CONTRACT_ID, IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
    IBKR_SESSION_ATTESTATION_CONTRACT_ID, STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID,
    STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID, STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID,
    STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID, STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
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
        "matching": {
            "expected_lifecycle_contract_id": IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
            "lifecycle_contract_id": lifecycle_event.lifecycle_contract_id,
            "expected_event_log_contract_id": BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
            "event_log_contract_id": lifecycle_event.event_log_contract_id,
            "expected_shadow_contract_id": STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
            "shadow_contract_id": shadow_fill_model.contract_id,
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
            "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
            "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
        },
        "phase2": phase2,
        "ibkr_live_enabled": false,
        "ibkr_call_performed": false,
        "secret_slot_touched": false,
        "order_routed": false,
        "bybit_ipc_reused": false,
    })
}

fn paper_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    let lifecycle_event = BrokerLifecycleEventLogV1::default();
    let lifecycle_verdict = lifecycle_event.validate();

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
        "lifecycle_event": {
            "expected_lifecycle_contract_id": IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
            "lifecycle_contract_id": lifecycle_event.lifecycle_contract_id,
            "expected_event_log_contract_id": BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
            "event_log_contract_id": lifecycle_event.event_log_contract_id,
            "source_version": lifecycle_event.source_version,
            "accepted": lifecycle_verdict.accepted,
            "blockers": lifecycle_verdict.blockers,
            "operation": lifecycle_event.operation,
            "previous_state": lifecycle_event.previous_state,
            "next_state": lifecycle_event.next_state,
            "allowed": lifecycle_event.allowed,
            "denial_reason": lifecycle_event.denial_reason,
            "event_id_present": !lifecycle_event.event_id.is_empty(),
            "event_time_ms": lifecycle_event.event_time_ms,
            "order_local_id_present": !lifecycle_event.order_local_id.is_empty(),
            "idempotency_key_present": !lifecycle_event.idempotency_key.is_empty(),
            "broker_order_id_present": !lifecycle_event.broker_order_id.is_empty(),
            "execution_id_present": !lifecycle_event.execution_id.is_empty(),
            "commission_report_id_present": !lifecycle_event.commission_report_id.is_empty(),
            "reconciliation_run_id_present": !lifecycle_event.reconciliation_run_id.is_empty(),
            "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
            "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
        },
        "reconstructability": {
            "append_only_event_ready": lifecycle_verdict.accepted,
            "broker_order_id_present": !lifecycle_event.broker_order_id.is_empty(),
            "execution_id_present": !lifecycle_event.execution_id.is_empty(),
            "commission_report_id_present": !lifecycle_event.commission_report_id.is_empty(),
            "raw_artifact_hash_present": !lifecycle_event.raw_artifact_hash.is_empty(),
            "redacted_summary_hash_present": !lifecycle_event.redacted_summary_hash.is_empty(),
            "restart_recovery_required": false,
            "manual_review_required": false,
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
