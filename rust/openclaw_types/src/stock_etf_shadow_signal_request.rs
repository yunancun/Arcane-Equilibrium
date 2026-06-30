//! Stock/ETF shadow signal request contract.
//!
//! This source-only validator pins the request shape for
//! `stock_etf.evaluate_shadow_signal`. It does not contact IBKR, start
//! connectors, inspect secrets, emit shadow signals, generate shadow fills,
//! write scorecards, apply DB changes, route orders, or change Bybit behavior.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;
use crate::stock_etf_lane::{
    AssetLane, AuthorityScope, Broker, BrokerEnvironment, BrokerOperation,
};
use crate::stock_etf_lane_scoped_ipc::StockEtfLaneScopedIpcMethod;

pub const STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID: &str = "stock_etf_shadow_signal_request_v1";

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfShadowSignalRequestV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub request_method: StockEtfLaneScopedIpcMethod,
    pub operation: BrokerOperation,
    pub authority_scope: AuthorityScope,
    pub effect_capable: bool,
    pub request_id: String,
    pub evaluation_run_id: String,
    pub shadow_signal_id: String,
    pub evidence_clock_hash: String,
    pub pit_universe_contract_hash: String,
    pub strategy_hypothesis_hash: String,
    pub instrument_identity_hash: String,
    pub market_data_provenance_hash: String,
    pub cost_model_version_hash: String,
    pub asset_lane_events_contract_hash: String,
    pub source_artifact_hash: String,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
    pub shadow_signal_emitted: bool,
    pub shadow_fill_generated: bool,
    pub scorecard_writer_started: bool,
    pub db_apply_performed: bool,
    pub order_routed: bool,
    pub bybit_path_reused: bool,
    pub live_or_tiny_live_authorized: bool,
    pub margin_short_options_cfd_requested: bool,
    pub python_direct_broker_write_requested: bool,
}

impl Default for StockEtfShadowSignalRequestV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            request_method: StockEtfLaneScopedIpcMethod::UnknownDenied,
            operation: BrokerOperation::TransferOrAccountWrite,
            authority_scope: AuthorityScope::Denied,
            effect_capable: false,
            request_id: String::new(),
            evaluation_run_id: String::new(),
            shadow_signal_id: String::new(),
            evidence_clock_hash: String::new(),
            pit_universe_contract_hash: String::new(),
            strategy_hypothesis_hash: String::new(),
            instrument_identity_hash: String::new(),
            market_data_provenance_hash: String::new(),
            cost_model_version_hash: String::new(),
            asset_lane_events_contract_hash: String::new(),
            source_artifact_hash: String::new(),
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
            shadow_signal_emitted: false,
            shadow_fill_generated: false,
            scorecard_writer_started: false,
            db_apply_performed: false,
            order_routed: false,
            bybit_path_reused: false,
            live_or_tiny_live_authorized: false,
            margin_short_options_cfd_requested: false,
            python_direct_broker_write_requested: false,
        }
    }
}

impl StockEtfShadowSignalRequestV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID.to_string(),
            source_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Shadow,
            request_method: StockEtfLaneScopedIpcMethod::EvaluateShadowSignal,
            operation: BrokerOperation::ShadowSignalEmit,
            authority_scope: AuthorityScope::ShadowOnly,
            effect_capable: false,
            request_id: "shadow_request_0001".to_string(),
            evaluation_run_id: "shadow_eval_run_0001".to_string(),
            shadow_signal_id: "shadow_signal_0001".to_string(),
            evidence_clock_hash: "1".repeat(64),
            pit_universe_contract_hash: "2".repeat(64),
            strategy_hypothesis_hash: "3".repeat(64),
            instrument_identity_hash: "4".repeat(64),
            market_data_provenance_hash: "5".repeat(64),
            cost_model_version_hash: "6".repeat(64),
            asset_lane_events_contract_hash: "7".repeat(64),
            source_artifact_hash: "8".repeat(64),
            ..Self::default()
        }
    }

    pub fn validate(&self) -> StockEtfShadowSignalRequestVerdict {
        use StockEtfShadowSignalRequestBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_SHADOW_SIGNAL_REQUEST_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if self.environment != BrokerEnvironment::Shadow {
            blockers.push(Blocker::EnvironmentNotShadow);
        }
        if self.request_method != StockEtfLaneScopedIpcMethod::EvaluateShadowSignal {
            blockers.push(Blocker::RequestMethodMismatch);
        }
        if self.operation != BrokerOperation::ShadowSignalEmit {
            blockers.push(Blocker::OperationMismatch);
        }
        if self.authority_scope != AuthorityScope::ShadowOnly {
            blockers.push(Blocker::AuthorityScopeMismatch);
        }
        if self.effect_capable {
            blockers.push(Blocker::EffectCapabilityPresent);
        }

        validate_required_fields(self, &mut blockers);
        validate_boundary_flags(self, &mut blockers);

        StockEtfShadowSignalRequestVerdict {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfShadowSignalRequestVerdict {
    pub accepted: bool,
    pub blockers: Vec<StockEtfShadowSignalRequestBlocker>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfShadowSignalRequestBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    WrongAssetLane,
    WrongBroker,
    EnvironmentNotShadow,
    RequestMethodMismatch,
    OperationMismatch,
    AuthorityScopeMismatch,
    EffectCapabilityPresent,
    RequestIdMissing,
    EvaluationRunIdMissing,
    ShadowSignalIdMissing,
    EvidenceClockHashInvalid,
    PitUniverseContractHashInvalid,
    StrategyHypothesisHashInvalid,
    InstrumentIdentityHashInvalid,
    MarketDataProvenanceHashInvalid,
    CostModelVersionHashInvalid,
    AssetLaneEventsContractHashInvalid,
    SourceArtifactHashInvalid,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
    ShadowSignalEmitted,
    ShadowFillGenerated,
    ScorecardWriterStarted,
    DbApplyPerformed,
    OrderRouted,
    BybitPathReused,
    LiveOrTinyLiveAuthorized,
    MarginShortOptionsCfdRequested,
    PythonDirectBrokerWriteRequested,
}

fn validate_required_fields(
    request: &StockEtfShadowSignalRequestV1,
    blockers: &mut Vec<StockEtfShadowSignalRequestBlocker>,
) {
    use StockEtfShadowSignalRequestBlocker as Blocker;

    if request.request_id.trim().is_empty() {
        blockers.push(Blocker::RequestIdMissing);
    }
    if request.evaluation_run_id.trim().is_empty() {
        blockers.push(Blocker::EvaluationRunIdMissing);
    }
    if request.shadow_signal_id.trim().is_empty() {
        blockers.push(Blocker::ShadowSignalIdMissing);
    }
    if !is_sha256_hex(&request.evidence_clock_hash) {
        blockers.push(Blocker::EvidenceClockHashInvalid);
    }
    if !is_sha256_hex(&request.pit_universe_contract_hash) {
        blockers.push(Blocker::PitUniverseContractHashInvalid);
    }
    if !is_sha256_hex(&request.strategy_hypothesis_hash) {
        blockers.push(Blocker::StrategyHypothesisHashInvalid);
    }
    if !is_sha256_hex(&request.instrument_identity_hash) {
        blockers.push(Blocker::InstrumentIdentityHashInvalid);
    }
    if !is_sha256_hex(&request.market_data_provenance_hash) {
        blockers.push(Blocker::MarketDataProvenanceHashInvalid);
    }
    if !is_sha256_hex(&request.cost_model_version_hash) {
        blockers.push(Blocker::CostModelVersionHashInvalid);
    }
    if !is_sha256_hex(&request.asset_lane_events_contract_hash) {
        blockers.push(Blocker::AssetLaneEventsContractHashInvalid);
    }
    if !is_sha256_hex(&request.source_artifact_hash) {
        blockers.push(Blocker::SourceArtifactHashInvalid);
    }
}

fn validate_boundary_flags(
    request: &StockEtfShadowSignalRequestV1,
    blockers: &mut Vec<StockEtfShadowSignalRequestBlocker>,
) {
    use StockEtfShadowSignalRequestBlocker as Blocker;

    if request.ibkr_contact_performed {
        blockers.push(Blocker::IbkrContactPerformed);
    }
    if request.connector_runtime_started {
        blockers.push(Blocker::ConnectorRuntimeStarted);
    }
    if request.secret_content_serialized {
        blockers.push(Blocker::SecretContentSerialized);
    }
    if request.shadow_signal_emitted {
        blockers.push(Blocker::ShadowSignalEmitted);
    }
    if request.shadow_fill_generated {
        blockers.push(Blocker::ShadowFillGenerated);
    }
    if request.scorecard_writer_started {
        blockers.push(Blocker::ScorecardWriterStarted);
    }
    if request.db_apply_performed {
        blockers.push(Blocker::DbApplyPerformed);
    }
    if request.order_routed {
        blockers.push(Blocker::OrderRouted);
    }
    if request.bybit_path_reused {
        blockers.push(Blocker::BybitPathReused);
    }
    if request.live_or_tiny_live_authorized {
        blockers.push(Blocker::LiveOrTinyLiveAuthorized);
    }
    if request.margin_short_options_cfd_requested {
        blockers.push(Blocker::MarginShortOptionsCfdRequested);
    }
    if request.python_direct_broker_write_requested {
        blockers.push(Blocker::PythonDirectBrokerWriteRequested);
    }
}
