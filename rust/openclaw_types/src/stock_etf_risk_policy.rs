//! Stock/ETF cash risk-policy contract for ADR-0048.
//!
//! This source-only validator turns the dormant paper/shadow risk config into
//! a named contract. It does not contact IBKR, inspect secrets, create
//! connectors, route orders, start collectors, write scorecards, or change
//! Bybit live execution behavior.

use serde::{Deserialize, Serialize};

use crate::stock_etf_lane::{AssetLane, Broker, BrokerEnvironment, InstrumentKind};

pub const STOCK_ETF_RISK_POLICY_CONTRACT_ID: &str = "stock_etf_risk_policy_v1";

const MAX_OPEN_ORDERS_V1: u16 = 20;
const MAX_OPEN_POSITIONS_V1: u16 = 100;
const REQUIRED_ALLOWED_KINDS: &[InstrumentKind] = &[
    InstrumentKind::Stock,
    InstrumentKind::Etf,
    InstrumentKind::Cash,
];
const REQUIRED_DENIED_KINDS: &[InstrumentKind] =
    &[InstrumentKind::CfdReserved, InstrumentKind::CryptoPerp];
const FORBIDDEN_ALLOWED_KINDS: &[InstrumentKind] =
    &[InstrumentKind::CfdReserved, InstrumentKind::CryptoPerp];

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StockEtfRiskPolicyV1 {
    pub contract_id: String,
    pub source_version: u32,
    pub config_version: u16,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub enabled: bool,
    pub shadow_only: bool,
    pub max_order_notional_usd: f64,
    pub max_position_notional_usd: f64,
    pub max_daily_notional_usd: f64,
    pub max_open_orders: u16,
    pub max_open_positions: u16,
    pub allow_fractional_shares: bool,
    pub allow_margin: bool,
    pub allow_short: bool,
    pub allow_options: bool,
    pub allow_cfd: bool,
    pub allow_transfer: bool,
    pub allow_live: bool,
    pub instrument_kinds_allowed: Vec<InstrumentKind>,
    pub instrument_kinds_denied: Vec<InstrumentKind>,
    pub requires_frozen_universe_hash: bool,
    pub requires_instrument_identity_hash: bool,
    pub requires_market_session: bool,
    pub cost_model_required_before_shadow_fill: bool,
    pub cost_model_required_before_scorecard: bool,
    pub commission_schedule_required: bool,
    pub spread_estimate_required: bool,
    pub slippage_estimate_required: bool,
    pub fx_drag_required: bool,
    pub conservative_fill_penalty_required: bool,
    pub rust_authority_required: bool,
    pub session_attestation_required: bool,
    pub decision_lease_required: bool,
    pub guardian_required: bool,
    pub idempotency_key_required: bool,
    pub broker_reconciliation_required: bool,
    pub bybit_live_execution_unchanged: bool,
    pub ibkr_contact_performed: bool,
    pub connector_runtime_started: bool,
    pub secret_content_serialized: bool,
}

impl Default for StockEtfRiskPolicyV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_version: 0,
            config_version: 0,
            asset_lane: AssetLane::CryptoPerp,
            broker: Broker::Bybit,
            environment: BrokerEnvironment::LiveReservedDenied,
            enabled: true,
            shadow_only: false,
            max_order_notional_usd: 0.0,
            max_position_notional_usd: 0.0,
            max_daily_notional_usd: 0.0,
            max_open_orders: 0,
            max_open_positions: 0,
            allow_fractional_shares: false,
            allow_margin: true,
            allow_short: true,
            allow_options: true,
            allow_cfd: true,
            allow_transfer: true,
            allow_live: true,
            instrument_kinds_allowed: Vec::new(),
            instrument_kinds_denied: Vec::new(),
            requires_frozen_universe_hash: false,
            requires_instrument_identity_hash: false,
            requires_market_session: false,
            cost_model_required_before_shadow_fill: false,
            cost_model_required_before_scorecard: false,
            commission_schedule_required: false,
            spread_estimate_required: false,
            slippage_estimate_required: false,
            fx_drag_required: false,
            conservative_fill_penalty_required: false,
            rust_authority_required: false,
            session_attestation_required: false,
            decision_lease_required: false,
            guardian_required: false,
            idempotency_key_required: false,
            broker_reconciliation_required: false,
            bybit_live_execution_unchanged: false,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
        }
    }
}

impl StockEtfRiskPolicyV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_RISK_POLICY_CONTRACT_ID.to_string(),
            source_version: 1,
            config_version: 1,
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            enabled: false,
            shadow_only: true,
            max_order_notional_usd: 1_000.0,
            max_position_notional_usd: 5_000.0,
            max_daily_notional_usd: 10_000.0,
            max_open_orders: 5,
            max_open_positions: 10,
            allow_fractional_shares: true,
            allow_margin: false,
            allow_short: false,
            allow_options: false,
            allow_cfd: false,
            allow_transfer: false,
            allow_live: false,
            instrument_kinds_allowed: REQUIRED_ALLOWED_KINDS.to_vec(),
            instrument_kinds_denied: REQUIRED_DENIED_KINDS.to_vec(),
            requires_frozen_universe_hash: true,
            requires_instrument_identity_hash: true,
            requires_market_session: true,
            cost_model_required_before_shadow_fill: true,
            cost_model_required_before_scorecard: true,
            commission_schedule_required: true,
            spread_estimate_required: true,
            slippage_estimate_required: true,
            fx_drag_required: true,
            conservative_fill_penalty_required: true,
            rust_authority_required: true,
            session_attestation_required: true,
            decision_lease_required: true,
            guardian_required: true,
            idempotency_key_required: true,
            broker_reconciliation_required: true,
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
        }
    }

    pub fn from_source_config(source: &StockEtfRiskPolicySourceConfigV1) -> Self {
        Self {
            contract_id: STOCK_ETF_RISK_POLICY_CONTRACT_ID.to_string(),
            source_version: 1,
            config_version: source.meta.version,
            asset_lane: source.meta.asset_lane,
            broker: source.meta.broker,
            environment: source.meta.environment,
            enabled: source.meta.enabled,
            shadow_only: source.meta.shadow_only,
            max_order_notional_usd: source.limits.max_order_notional_usd,
            max_position_notional_usd: source.limits.max_position_notional_usd,
            max_daily_notional_usd: source.limits.max_daily_notional_usd,
            max_open_orders: source.limits.max_open_orders,
            max_open_positions: source.limits.max_open_positions,
            allow_fractional_shares: source.limits.allow_fractional_shares,
            allow_margin: source.limits.allow_margin,
            allow_short: source.limits.allow_short,
            allow_options: source.limits.allow_options,
            allow_cfd: source.limits.allow_cfd,
            allow_transfer: source.limits.allow_transfer,
            allow_live: source.limits.allow_live,
            instrument_kinds_allowed: source.universe.instrument_kinds_allowed.clone(),
            instrument_kinds_denied: source.universe.instrument_kinds_denied.clone(),
            requires_frozen_universe_hash: source.universe.requires_frozen_universe_hash,
            requires_instrument_identity_hash: source.universe.requires_instrument_identity_hash,
            requires_market_session: source.universe.requires_market_session,
            cost_model_required_before_shadow_fill: source.cost_model.required_before_shadow_fill,
            cost_model_required_before_scorecard: source.cost_model.required_before_scorecard,
            commission_schedule_required: source.cost_model.commission_schedule_required,
            spread_estimate_required: source.cost_model.spread_estimate_required,
            slippage_estimate_required: source.cost_model.slippage_estimate_required,
            fx_drag_required: source.cost_model.fx_drag_required,
            conservative_fill_penalty_required: source
                .cost_model
                .conservative_fill_penalty_required,
            rust_authority_required: source.paper_order.rust_authority_required,
            session_attestation_required: source.paper_order.session_attestation_required,
            decision_lease_required: source.paper_order.decision_lease_required,
            guardian_required: source.paper_order.guardian_required,
            idempotency_key_required: source.paper_order.idempotency_key_required,
            broker_reconciliation_required: source.paper_order.broker_reconciliation_required,
            bybit_live_execution_unchanged: true,
            ibkr_contact_performed: false,
            connector_runtime_started: false,
            secret_content_serialized: false,
        }
    }

    pub fn validate(&self) -> StockEtfRiskPolicyVerdict<StockEtfRiskPolicyBlocker> {
        use StockEtfRiskPolicyBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_RISK_POLICY_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_version != 1 {
            blockers.push(Blocker::SourceVersionMismatch);
        }
        if self.config_version != 1 {
            blockers.push(Blocker::VersionMismatch);
        }
        if self.asset_lane != AssetLane::StockEtfCash {
            blockers.push(Blocker::WrongAssetLane);
        }
        if self.broker != Broker::Ibkr {
            blockers.push(Blocker::WrongBroker);
        }
        if !matches!(
            self.environment,
            BrokerEnvironment::Paper | BrokerEnvironment::Shadow
        ) {
            blockers.push(Blocker::WrongEnvironment);
        }
        if self.enabled {
            blockers.push(Blocker::RuntimeEnablementClaimed);
        }
        if !self.shadow_only {
            blockers.push(Blocker::ShadowOnlyPostureMissing);
        }

        validate_caps(self, &mut blockers);
        validate_cash_only_controls(self, &mut blockers);
        validate_universe_controls(self, &mut blockers);
        validate_cost_model_controls(self, &mut blockers);
        validate_paper_order_controls(self, &mut blockers);

        if !self.bybit_live_execution_unchanged {
            blockers.push(Blocker::BybitLiveExecutionNotProtected);
        }
        if self.ibkr_contact_performed {
            blockers.push(Blocker::IbkrContactPerformed);
        }
        if self.connector_runtime_started {
            blockers.push(Blocker::ConnectorRuntimeStarted);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }

        StockEtfRiskPolicyVerdict::new(blockers)
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StockEtfRiskPolicySourceConfigV1 {
    pub meta: StockEtfRiskPolicySourceMetaV1,
    pub limits: StockEtfRiskPolicySourceLimitsV1,
    pub universe: StockEtfRiskPolicySourceUniverseV1,
    pub cost_model: StockEtfRiskPolicySourceCostModelV1,
    pub paper_order: StockEtfRiskPolicySourcePaperOrderV1,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfRiskPolicySourceMetaV1 {
    pub version: u16,
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub enabled: bool,
    pub shadow_only: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct StockEtfRiskPolicySourceLimitsV1 {
    pub max_order_notional_usd: f64,
    pub max_position_notional_usd: f64,
    pub max_daily_notional_usd: f64,
    pub max_open_orders: u16,
    pub max_open_positions: u16,
    pub allow_fractional_shares: bool,
    pub allow_margin: bool,
    pub allow_short: bool,
    pub allow_options: bool,
    pub allow_cfd: bool,
    pub allow_transfer: bool,
    pub allow_live: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfRiskPolicySourceUniverseV1 {
    pub instrument_kinds_allowed: Vec<InstrumentKind>,
    pub instrument_kinds_denied: Vec<InstrumentKind>,
    pub requires_frozen_universe_hash: bool,
    pub requires_instrument_identity_hash: bool,
    pub requires_market_session: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfRiskPolicySourceCostModelV1 {
    pub required_before_shadow_fill: bool,
    pub required_before_scorecard: bool,
    pub commission_schedule_required: bool,
    pub spread_estimate_required: bool,
    pub slippage_estimate_required: bool,
    pub fx_drag_required: bool,
    pub conservative_fill_penalty_required: bool,
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfRiskPolicySourcePaperOrderV1 {
    pub rust_authority_required: bool,
    pub session_attestation_required: bool,
    pub decision_lease_required: bool,
    pub guardian_required: bool,
    pub idempotency_key_required: bool,
    pub broker_reconciliation_required: bool,
}

fn validate_caps(policy: &StockEtfRiskPolicyV1, blockers: &mut Vec<StockEtfRiskPolicyBlocker>) {
    use StockEtfRiskPolicyBlocker as Blocker;

    if !positive_finite(policy.max_order_notional_usd) {
        blockers.push(Blocker::OrderCapMissing);
    }
    if !positive_finite(policy.max_position_notional_usd) {
        blockers.push(Blocker::PositionCapMissing);
    }
    if !positive_finite(policy.max_daily_notional_usd) {
        blockers.push(Blocker::DailyCapMissing);
    }
    if positive_finite(policy.max_order_notional_usd)
        && positive_finite(policy.max_position_notional_usd)
        && positive_finite(policy.max_daily_notional_usd)
        && !(policy.max_order_notional_usd <= policy.max_position_notional_usd
            && policy.max_position_notional_usd <= policy.max_daily_notional_usd)
    {
        blockers.push(Blocker::CapOrderingInvalid);
    }
    if policy.max_open_orders == 0 {
        blockers.push(Blocker::OpenOrderLimitMissing);
    }
    if policy.max_open_orders > MAX_OPEN_ORDERS_V1 {
        blockers.push(Blocker::OpenOrderLimitTooHigh);
    }
    if policy.max_open_positions == 0 {
        blockers.push(Blocker::OpenPositionLimitMissing);
    }
    if policy.max_open_positions > MAX_OPEN_POSITIONS_V1 {
        blockers.push(Blocker::OpenPositionLimitTooHigh);
    }
}

fn validate_cash_only_controls(
    policy: &StockEtfRiskPolicyV1,
    blockers: &mut Vec<StockEtfRiskPolicyBlocker>,
) {
    use StockEtfRiskPolicyBlocker as Blocker;

    if policy.allow_margin {
        blockers.push(Blocker::MarginAllowed);
    }
    if policy.allow_short {
        blockers.push(Blocker::ShortAllowed);
    }
    if policy.allow_options {
        blockers.push(Blocker::OptionsAllowed);
    }
    if policy.allow_cfd {
        blockers.push(Blocker::CfdAllowed);
    }
    if policy.allow_transfer {
        blockers.push(Blocker::TransferAllowed);
    }
    if policy.allow_live {
        blockers.push(Blocker::LiveAllowed);
    }
}

fn validate_universe_controls(
    policy: &StockEtfRiskPolicyV1,
    blockers: &mut Vec<StockEtfRiskPolicyBlocker>,
) {
    use StockEtfRiskPolicyBlocker as Blocker;

    if !contains_all_kinds(&policy.instrument_kinds_allowed, REQUIRED_ALLOWED_KINDS) {
        blockers.push(Blocker::AllowedInstrumentMissing);
    }
    if contains_any_kind(&policy.instrument_kinds_allowed, FORBIDDEN_ALLOWED_KINDS) {
        blockers.push(Blocker::ForbiddenInstrumentAllowed);
    }
    if !contains_all_kinds(&policy.instrument_kinds_denied, REQUIRED_DENIED_KINDS) {
        blockers.push(Blocker::DeniedInstrumentMissing);
    }
    if !policy.requires_frozen_universe_hash {
        blockers.push(Blocker::FrozenUniverseHashNotRequired);
    }
    if !policy.requires_instrument_identity_hash {
        blockers.push(Blocker::InstrumentIdentityHashNotRequired);
    }
    if !policy.requires_market_session {
        blockers.push(Blocker::MarketSessionNotRequired);
    }
}

fn validate_cost_model_controls(
    policy: &StockEtfRiskPolicyV1,
    blockers: &mut Vec<StockEtfRiskPolicyBlocker>,
) {
    use StockEtfRiskPolicyBlocker as Blocker;

    if !policy.cost_model_required_before_shadow_fill {
        blockers.push(Blocker::CostModelBeforeShadowFillMissing);
    }
    if !policy.cost_model_required_before_scorecard {
        blockers.push(Blocker::CostModelBeforeScorecardMissing);
    }
    if !policy.commission_schedule_required {
        blockers.push(Blocker::CommissionScheduleMissing);
    }
    if !policy.spread_estimate_required {
        blockers.push(Blocker::SpreadEstimateMissing);
    }
    if !policy.slippage_estimate_required {
        blockers.push(Blocker::SlippageEstimateMissing);
    }
    if !policy.fx_drag_required {
        blockers.push(Blocker::FxDragMissing);
    }
    if !policy.conservative_fill_penalty_required {
        blockers.push(Blocker::ConservativePenaltyMissing);
    }
}

fn validate_paper_order_controls(
    policy: &StockEtfRiskPolicyV1,
    blockers: &mut Vec<StockEtfRiskPolicyBlocker>,
) {
    use StockEtfRiskPolicyBlocker as Blocker;

    if !policy.rust_authority_required {
        blockers.push(Blocker::RustAuthorityMissing);
    }
    if !policy.session_attestation_required {
        blockers.push(Blocker::SessionAttestationMissing);
    }
    if !policy.decision_lease_required {
        blockers.push(Blocker::DecisionLeaseMissing);
    }
    if !policy.guardian_required {
        blockers.push(Blocker::GuardianMissing);
    }
    if !policy.idempotency_key_required {
        blockers.push(Blocker::IdempotencyKeyMissing);
    }
    if !policy.broker_reconciliation_required {
        blockers.push(Blocker::BrokerReconciliationMissing);
    }
}

fn positive_finite(value: f64) -> bool {
    value.is_finite() && value > 0.0
}

fn contains_all_kinds(actual: &[InstrumentKind], required: &[InstrumentKind]) -> bool {
    required
        .iter()
        .all(|expected| actual.iter().any(|item| item == expected))
}

fn contains_any_kind(actual: &[InstrumentKind], forbidden: &[InstrumentKind]) -> bool {
    forbidden
        .iter()
        .any(|blocked| actual.iter().any(|item| item == blocked))
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfRiskPolicyVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfRiskPolicyVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfRiskPolicyBlocker {
    ContractIdMismatch,
    SourceVersionMismatch,
    VersionMismatch,
    WrongAssetLane,
    WrongBroker,
    WrongEnvironment,
    RuntimeEnablementClaimed,
    ShadowOnlyPostureMissing,
    OrderCapMissing,
    PositionCapMissing,
    DailyCapMissing,
    CapOrderingInvalid,
    OpenOrderLimitMissing,
    OpenOrderLimitTooHigh,
    OpenPositionLimitMissing,
    OpenPositionLimitTooHigh,
    MarginAllowed,
    ShortAllowed,
    OptionsAllowed,
    CfdAllowed,
    TransferAllowed,
    LiveAllowed,
    AllowedInstrumentMissing,
    ForbiddenInstrumentAllowed,
    DeniedInstrumentMissing,
    FrozenUniverseHashNotRequired,
    InstrumentIdentityHashNotRequired,
    MarketSessionNotRequired,
    CostModelBeforeShadowFillMissing,
    CostModelBeforeScorecardMissing,
    CommissionScheduleMissing,
    SpreadEstimateMissing,
    SlippageEstimateMissing,
    FxDragMissing,
    ConservativePenaltyMissing,
    RustAuthorityMissing,
    SessionAttestationMissing,
    DecisionLeaseMissing,
    GuardianMissing,
    IdempotencyKeyMissing,
    BrokerReconciliationMissing,
    BybitLiveExecutionNotProtected,
    IbkrContactPerformed,
    ConnectorRuntimeStarted,
    SecretContentSerialized,
}
