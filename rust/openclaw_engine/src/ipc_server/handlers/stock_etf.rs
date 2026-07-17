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
    IbkrPaperAttestationPolicyV1, IbkrSessionAttestationV1, InstrumentKind,
    StockEtfBrokerCapabilityRegistryV1, StockEtfCollectorRunV1, StockEtfDisableCleanupRunbookV1,
    StockEtfEvidenceClockDayV1, StockEtfFeatureFlags, StockEtfGateInputs,
    StockEtfIbkrReadonlyProbeRequestV1, StockEtfInstrumentIdentityV1, StockEtfLaneScopedIpcMethod,
    StockEtfPaperFillImportRequestV1, StockEtfPaperOrderRequestEnvelopeV1,
    StockEtfPaperShadowReconciliationV1, StockEtfPhase0ContractPacketManifestV1,
    StockEtfPitUniverseV1, StockEtfReferenceDataSourcesV1, StockEtfReleasePacketV1,
    StockEtfRiskPolicyV1, StockEtfScorecardDerivationV1, StockEtfScorecardInputBundleV1,
    StockEtfScorecardVerdictV1, StockEtfShadowSignalRequestV1, StockEtfStrategyHypothesisV1,
    StockMarketDataProvenanceV1, StockShadowFillModelV1, TinyLiveAdrEligibilityV1,
    BROKER_ACCOUNT_PORTFOLIO_CASH_LEDGER_CONTRACT_ID, BROKER_LIFECYCLE_EVENT_LOG_CONTRACT_ID,
    FEATURE_FLAG_SECRET_AUTH_MATRIX_CONTRACT_ID, IBKR_EXTERNAL_SURFACE_GATE_CONTRACT_ID,
    IBKR_PAPER_ATTESTATION_CONTRACT_ID, IBKR_PAPER_ORDER_LIFECYCLE_CONTRACT_ID,
    IBKR_SECRET_SLOT_CONTRACT_ID, IBKR_SESSION_ATTESTATION_CONTRACT_ID,
    STOCK_ETF_BROKER_CAPABILITY_REGISTRY_ID, STOCK_ETF_COLLECTOR_RUN_CONTRACT_ID,
    STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID, STOCK_ETF_DQ_MANIFEST_CONTRACT_ID,
    STOCK_ETF_EVIDENCE_CLOCK_CONTRACT_ID, STOCK_ETF_IBKR_READONLY_PROBE_REQUEST_CONTRACT_ID,
    STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
    STOCK_ETF_INSTRUMENT_IDENTITY_CONTRACT_ID, STOCK_ETF_LANE_SCOPED_IPC_CONTRACT_ID,
    STOCK_ETF_PAPER_FILL_IMPORT_REQUEST_CONTRACT_ID, STOCK_ETF_PAPER_ORDER_REQUEST_CONTRACT_ID,
    STOCK_ETF_PAPER_SHADOW_RECONCILIATION_CONTRACT_ID, STOCK_ETF_PIT_UNIVERSE_CONTRACT_ID,
    STOCK_ETF_REFERENCE_DATA_SOURCES_CONTRACT_ID, STOCK_ETF_RELEASE_PACKET_CONTRACT_ID,
    STOCK_ETF_RISK_POLICY_CONTRACT_ID, STOCK_ETF_SCORECARD_DERIVATION_CONTRACT_ID,
    STOCK_ETF_SCORECARD_VERDICT_CONTRACT_ID, STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID,
    STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID, STOCK_ETF_TINY_LIVE_ADR_ELIGIBILITY_CONTRACT_ID,
    STOCK_MARKET_DATA_PROVENANCE_CONTRACT_ID, STOCK_SHADOW_FILL_MODEL_CONTRACT_ID,
};

mod health_summary;
mod precontact;
mod request_summaries;
mod status_summaries;
use health_summary::connection_health_summary;
use precontact::{connector_skeleton_summary, phase2_precontact_summary};
use request_summaries::{
    fill_import_request_summary, operation_for_method_and_params, paper_request_envelope_summary,
    readonly_probe_request_ipc_summary, request_from_params, shadow_signal_request_summary,
};
use status_summaries::{
    account_status_summary, disable_cleanup_status_summary, evidence_status_summary,
    launch_status_summary, paper_status_summary, reconciliation_status_summary,
    release_packet_status_summary, scorecard_status_summary, shadow_status_summary,
    universe_status_summary,
};
// risk-policy loader 已抽至 sibling 模組（handler 本體不再持有檔案系統/路徑類
// runtime material 讀取）；此處跨 sibling 取用進程級快取與 denied 回退。
use super::stock_etf_risk_policy::{denied_stock_etf_risk_policy_fallback, stock_etf_risk_policy};

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
        "stock_etf.get_connection_health" => {
            JsonRpcResponse::success(id, connection_health_summary(phase2))
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

/// 薄包裝（handler dispatch 入口）：以進程級 OnceLock 快取的載入結果渲染
/// policy_status。純顯示，不 enable 任何下單路徑（lane 仍 enabled=false /
/// shadow_only=true）。
fn policy_status_summary(phase2: serde_json::Value) -> serde_json::Value {
    policy_status_summary_from_result(phase2, stock_etf_risk_policy())
}

/// 純渲染子：把「risk policy 載入結果」渲染成 policy_status IPC 顯示投影。
///
/// 為什麼收 &Result 參數而非讀 OnceLock：讓 fixture 能以注入方式（pure loader
/// 回 Err 或直接構造 Err）確定性驗證 denied fallback 渲染，繞過進程級 OnceLock
/// 初始化順序與 OPENCLAW_RISK_CONFIG_DIR 全域狀態，比原走 IPC/OnceLock 的測試
/// 更確定（原測試自承 env-set 常為 no-op）。
///
/// fail-closed：載入/解析為 Err 時回退 denied fallback，並在輸出帶
/// risk_config_load_error（非 null），讓消費端可區分「檔案問題」與「刻意 dormant」。
pub(in crate::ipc_server) fn policy_status_summary_from_result(
    phase2: serde_json::Value,
    result: &Result<StockEtfRiskPolicyV1, String>,
) -> serde_json::Value {
    // win ②：顯示的 caps 必須等於真正的 source-of-record
    // （risk_config_stock_etf_paper.toml），而非 default() 的 0。
    let (risk_policy, risk_config_load_error) = match result {
        Ok(policy) => (policy.clone(), None),
        Err(e) => (denied_stock_etf_risk_policy_fallback(), Some(e.clone())),
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
    let scorecard_rows: Vec<_> = registry
        .operations
        .iter()
        .filter(|entry| entry.operation == BrokerOperation::ScorecardDerive)
        .collect();
    let scorecard_requires_readonly_probe_result_import_request = scorecard_rows.len() == 1
        && scorecard_rows[0].required_gates.iter().any(|gate| {
            gate.as_str() == STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID
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
    // fail-closed reason（happy path = null）：載入/解析失敗時攜帶原因字串，讓 IPC
    // 消費端可區分「檔案問題」與「刻意 dormant」；denial 本身已由 accepted/blockers 表達。
    put_risk!("risk_config_load_error", risk_config_load_error);
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
        "readonly_probe_result_import_request_contract_id": STOCK_ETF_IBKR_READONLY_PROBE_RESULT_IMPORT_REQUEST_CONTRACT_ID,
        "read_rows_require_lane_scoped_ipc": read_rows_require_lane_scoped_ipc,
        "read_rows_require_readonly_probe_request": read_rows_require_readonly_probe_request,
        "scorecard_requires_readonly_probe_result_import_request": scorecard_requires_readonly_probe_result_import_request,
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

/// W6-S0（E2-R13-F1 re-scope,三角測量第三腿）:auth-matrix producer 的 session_attestation
/// 腿接 attestation producer 真值。production 域引擎 inactive、無 wire 實檢事實 →
/// `blocked_session_attestation()` 恆 Blocked/無指紋——matrix 腿呈**誠實 absent/blocked 態**
/// （同 W4 health emitter 代碼路徑,非手搓 default、不捏值）;attested 態只能經 driver wire
/// 實檢派生（fixture 域行為測試見 `foundation_status_fixtures`）。三腿指紋一致性
/// （secret-slot 契約腿/attestation 腿/authorization envelope 腿）由
/// `FeatureFlagSecretAuthMatrixV1::validate_operation` 的 mismatch blocker 收口。
pub(in crate::ipc_server) fn production_feature_flag_secret_auth_matrix(
    flags: StockEtfFeatureFlags,
) -> FeatureFlagSecretAuthMatrixV1 {
    FeatureFlagSecretAuthMatrixV1 {
        flags,
        session_attestation: crate::ibkr_tws_session_attestation::blocked_session_attestation(),
        gui_lane_state_override_denied: true,
        server_rust_matrix_authoritative: true,
        ..FeatureFlagSecretAuthMatrixV1::default()
    }
}

fn authorization_status_summary(
    phase2: serde_json::Value,
    flags: StockEtfFeatureFlags,
) -> serde_json::Value {
    let matrix = production_feature_flag_secret_auth_matrix(flags);
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

/// 測試用 phase2 precontact 投影再導出：讓 policy_status fixture 以注入方式呼叫純
/// 渲染子時，取得與 handler dispatch 入口一致的 phase2 值，不必走完整 IPC dispatch
/// 與進程級 OnceLock。非測試建置無消費端，故 cfg(test) 限定。
#[cfg(test)]
pub(in crate::ipc_server) fn stock_etf_phase2_precontact_summary_for_test() -> serde_json::Value {
    phase2_precontact_summary()
}
