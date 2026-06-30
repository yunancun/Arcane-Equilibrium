//! Stock/ETF cash lane contract types for ADR-0048 / AMD-2026-06-29-01.
//!
//! Phase 1 scope only: closed taxonomy, default-off feature flags, capability
//! denial decisions, and lifecycle fixtures. This module contains no IBKR API
//! client, no secret-slot access, no broker write, and no runtime dispatch.

use serde::{Deserialize, Serialize};
use std::{fmt, str::FromStr};

pub const STOCK_ETF_ASSET_LANE_TAXONOMY_CONTRACT_ID: &str = "asset_lane_taxonomy_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AssetLane {
    CryptoPerp,
    StockEtfCash,
    CfdMarginReserved,
}

impl AssetLane {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::CryptoPerp => "crypto_perp",
            Self::StockEtfCash => "stock_etf_cash",
            Self::CfdMarginReserved => "cfd_margin_reserved",
        }
    }
}

impl Default for AssetLane {
    fn default() -> Self {
        Self::CryptoPerp
    }
}

impl fmt::Display for AssetLane {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for AssetLane {
    type Err = StockEtfContractParseError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match normalize_token(s).as_str() {
            "cryptoperp" | "crypto_perp" => Ok(Self::CryptoPerp),
            "stocketfcash" | "stock_etf_cash" => Ok(Self::StockEtfCash),
            "cfdmarginreserved" | "cfd_margin_reserved" => Ok(Self::CfdMarginReserved),
            _ => Err(StockEtfContractParseError::unknown("asset_lane", s)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Broker {
    Bybit,
    Ibkr,
}

impl Broker {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::Bybit => "bybit",
            Self::Ibkr => "ibkr",
        }
    }
}

impl fmt::Display for Broker {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for Broker {
    type Err = StockEtfContractParseError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match normalize_token(s).as_str() {
            "bybit" => Ok(Self::Bybit),
            "ibkr" => Ok(Self::Ibkr),
            _ => Err(StockEtfContractParseError::unknown("broker", s)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BrokerEnvironment {
    ReadOnly,
    Paper,
    Shadow,
    LiveReservedDenied,
}

impl BrokerEnvironment {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::ReadOnly => "readonly",
            Self::Paper => "paper",
            Self::Shadow => "shadow",
            Self::LiveReservedDenied => "live_reserved_denied",
        }
    }

    pub const fn allows_ibkr_live(self) -> bool {
        false
    }
}

impl fmt::Display for BrokerEnvironment {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for BrokerEnvironment {
    type Err = StockEtfContractParseError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match normalize_token(s).as_str() {
            "readonly" | "read_only" => Ok(Self::ReadOnly),
            "paper" => Ok(Self::Paper),
            "shadow" => Ok(Self::Shadow),
            "livereserveddenied" | "live_reserved_denied" | "live" | "tiny_live" => {
                Ok(Self::LiveReservedDenied)
            }
            _ => Err(StockEtfContractParseError::unknown("broker_environment", s)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum InstrumentKind {
    CryptoPerp,
    Stock,
    Etf,
    Cash,
    CfdReserved,
}

impl InstrumentKind {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::CryptoPerp => "crypto_perp",
            Self::Stock => "stock",
            Self::Etf => "etf",
            Self::Cash => "cash",
            Self::CfdReserved => "cfd_reserved",
        }
    }

    pub const fn allowed_for_stock_etf_cash(self) -> bool {
        matches!(self, Self::Stock | Self::Etf | Self::Cash)
    }
}

impl fmt::Display for InstrumentKind {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

impl FromStr for InstrumentKind {
    type Err = StockEtfContractParseError;

    fn from_str(s: &str) -> Result<Self, Self::Err> {
        match normalize_token(s).as_str() {
            "cryptoperp" | "crypto_perp" => Ok(Self::CryptoPerp),
            "stock" => Ok(Self::Stock),
            "etf" => Ok(Self::Etf),
            "cash" => Ok(Self::Cash),
            "cfdreserved" | "cfd_reserved" | "cfd" => Ok(Self::CfdReserved),
            _ => Err(StockEtfContractParseError::unknown("instrument_kind", s)),
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum AuthorityScope {
    DisplayOnly,
    ReadOnly,
    PaperRehearsal,
    ShadowOnly,
    Denied,
}

impl AuthorityScope {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::DisplayOnly => "display_only",
            Self::ReadOnly => "readonly",
            Self::PaperRehearsal => "paper_rehearsal",
            Self::ShadowOnly => "shadow_only",
            Self::Denied => "denied",
        }
    }
}

impl fmt::Display for AuthorityScope {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum BrokerOperation {
    HealthRead,
    AccountSnapshotRead,
    MarketDataRead,
    ContractDetailsRead,
    PaperOrderSubmit,
    PaperOrderCancel,
    PaperOrderReplace,
    PaperOrderFillImport,
    ShadowSignalEmit,
    ShadowFillReconstruct,
    ScorecardDerive,
    LiveOrderSubmit,
    MarginOrShort,
    OptionsOrCfd,
    TransferOrAccountWrite,
}

impl BrokerOperation {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::HealthRead => "health_read",
            Self::AccountSnapshotRead => "account_snapshot_read",
            Self::MarketDataRead => "market_data_read",
            Self::ContractDetailsRead => "contract_details_read",
            Self::PaperOrderSubmit => "paper_order_submit",
            Self::PaperOrderCancel => "paper_order_cancel",
            Self::PaperOrderReplace => "paper_order_replace",
            Self::PaperOrderFillImport => "paper_order_fill_import",
            Self::ShadowSignalEmit => "shadow_signal_emit",
            Self::ShadowFillReconstruct => "shadow_fill_reconstruct",
            Self::ScorecardDerive => "scorecard_derive",
            Self::LiveOrderSubmit => "live_order_submit",
            Self::MarginOrShort => "margin_or_short",
            Self::OptionsOrCfd => "options_or_cfd",
            Self::TransferOrAccountWrite => "transfer_or_account_write",
        }
    }

    pub const fn is_read(self) -> bool {
        matches!(
            self,
            Self::HealthRead
                | Self::AccountSnapshotRead
                | Self::MarketDataRead
                | Self::ContractDetailsRead
                | Self::PaperOrderFillImport
                | Self::ScorecardDerive
        )
    }

    pub const fn is_paper_write(self) -> bool {
        matches!(
            self,
            Self::PaperOrderSubmit | Self::PaperOrderCancel | Self::PaperOrderReplace
        )
    }

    pub const fn is_shadow(self) -> bool {
        matches!(self, Self::ShadowSignalEmit | Self::ShadowFillReconstruct)
    }

    pub const fn authority_scope(self) -> AuthorityScope {
        if self.is_paper_write() {
            AuthorityScope::PaperRehearsal
        } else if self.is_shadow() {
            AuthorityScope::ShadowOnly
        } else if self.is_read() {
            AuthorityScope::ReadOnly
        } else {
            AuthorityScope::Denied
        }
    }
}

impl fmt::Display for BrokerOperation {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfDenialReason {
    LaneDisabled,
    BrokerDisabled,
    ShadowOnly,
    LiveReservedDenied,
    MarketClosed,
    InstrumentBlocked,
    CostModelMissing,
    UniverseMismatch,
    CredentialUnavailable,
    ConnectorUnavailable,
    AuthorizationInvalid,
    DecisionLeaseInvalid,
    GuardianDenied,
    IbkrLiveNotAuthorized,
    StockEtfCashOnly,
    InstrumentKindDenied,
    AccountWriteDenied,
    WrongAssetLane,
    WrongBroker,
    WrongEnvironment,
}

impl StockEtfDenialReason {
    pub const fn as_str(self) -> &'static str {
        match self {
            Self::LaneDisabled => "lane_disabled",
            Self::BrokerDisabled => "broker_disabled",
            Self::ShadowOnly => "shadow_only",
            Self::LiveReservedDenied => "live_reserved_denied",
            Self::MarketClosed => "market_closed",
            Self::InstrumentBlocked => "instrument_blocked",
            Self::CostModelMissing => "cost_model_missing",
            Self::UniverseMismatch => "universe_mismatch",
            Self::CredentialUnavailable => "credential_unavailable",
            Self::ConnectorUnavailable => "connector_unavailable",
            Self::AuthorizationInvalid => "authorization_invalid",
            Self::DecisionLeaseInvalid => "decision_lease_invalid",
            Self::GuardianDenied => "guardian_denied",
            Self::IbkrLiveNotAuthorized => "ibkr_live_not_authorized",
            Self::StockEtfCashOnly => "stock_etf_cash_only",
            Self::InstrumentKindDenied => "instrument_kind_denied",
            Self::AccountWriteDenied => "account_write_denied",
            Self::WrongAssetLane => "wrong_asset_lane",
            Self::WrongBroker => "wrong_broker",
            Self::WrongEnvironment => "wrong_environment",
        }
    }
}

impl fmt::Display for StockEtfDenialReason {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        f.write_str(self.as_str())
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfFeatureFlags {
    pub stock_etf_lane_enabled: bool,
    pub ibkr_readonly_enabled: bool,
    pub ibkr_paper_enabled: bool,
    pub asset_lane_default: AssetLane,
    pub stock_etf_shadow_only: bool,
}

impl Default for StockEtfFeatureFlags {
    fn default() -> Self {
        Self {
            stock_etf_lane_enabled: false,
            ibkr_readonly_enabled: false,
            ibkr_paper_enabled: false,
            asset_lane_default: AssetLane::CryptoPerp,
            stock_etf_shadow_only: true,
        }
    }
}

impl StockEtfFeatureFlags {
    pub fn from_env() -> Result<Self, StockEtfConfigError> {
        Self::from_lookup(|key| std::env::var(key).ok())
    }

    pub fn from_lookup<F>(lookup: F) -> Result<Self, StockEtfConfigError>
    where
        F: Fn(&str) -> Option<String>,
    {
        let defaults = Self::default();
        Ok(Self {
            stock_etf_lane_enabled: parse_bool_flag(
                "OPENCLAW_STOCK_ETF_LANE_ENABLED",
                lookup("OPENCLAW_STOCK_ETF_LANE_ENABLED"),
                defaults.stock_etf_lane_enabled,
            )?,
            ibkr_readonly_enabled: parse_bool_flag(
                "OPENCLAW_IBKR_READONLY_ENABLED",
                lookup("OPENCLAW_IBKR_READONLY_ENABLED"),
                defaults.ibkr_readonly_enabled,
            )?,
            ibkr_paper_enabled: parse_bool_flag(
                "OPENCLAW_IBKR_PAPER_ENABLED",
                lookup("OPENCLAW_IBKR_PAPER_ENABLED"),
                defaults.ibkr_paper_enabled,
            )?,
            asset_lane_default: match lookup("OPENCLAW_ASSET_LANE_DEFAULT") {
                Some(v) => {
                    AssetLane::from_str(&v).map_err(|_| StockEtfConfigError::InvalidEnum {
                        key: "OPENCLAW_ASSET_LANE_DEFAULT",
                        value: v,
                    })?
                }
                None => defaults.asset_lane_default,
            },
            stock_etf_shadow_only: parse_bool_flag(
                "OPENCLAW_STOCK_ETF_SHADOW_ONLY",
                lookup("OPENCLAW_STOCK_ETF_SHADOW_ONLY"),
                defaults.stock_etf_shadow_only,
            )?,
        })
    }

    pub fn readiness(&self) -> StockEtfReadiness {
        let mut denial_reasons = Vec::new();
        if !self.stock_etf_lane_enabled {
            denial_reasons.push(StockEtfDenialReason::LaneDisabled);
        }
        if !self.ibkr_readonly_enabled && !self.ibkr_paper_enabled {
            denial_reasons.push(StockEtfDenialReason::BrokerDisabled);
        }
        if self.stock_etf_shadow_only {
            denial_reasons.push(StockEtfDenialReason::ShadowOnly);
        }

        StockEtfReadiness {
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            default_asset_lane: self.asset_lane_default,
            readonly_ready: self.stock_etf_lane_enabled && self.ibkr_readonly_enabled,
            paper_ready: self.stock_etf_lane_enabled
                && self.ibkr_paper_enabled
                && !self.stock_etf_shadow_only,
            shadow_only: self.stock_etf_shadow_only,
            live_denied: true,
            denial_reasons,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfReadiness {
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub default_asset_lane: AssetLane,
    pub readonly_ready: bool,
    pub paper_ready: bool,
    pub shadow_only: bool,
    pub live_denied: bool,
    pub denial_reasons: Vec<StockEtfDenialReason>,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfGateInputs {
    pub external_surface_gate_passed: bool,
    pub session_attested: bool,
    pub scoped_authorization_present: bool,
    pub decision_lease_valid: bool,
    pub guardian_allows: bool,
    pub risk_config_hash_present: bool,
    pub instrument_identity_hash_present: bool,
    pub idempotency_key_present: bool,
    pub market_open: bool,
    pub cost_model_present: bool,
    pub universe_match: bool,
    pub credential_available: bool,
    pub connector_available: bool,
}

impl Default for StockEtfGateInputs {
    fn default() -> Self {
        Self {
            external_surface_gate_passed: false,
            session_attested: false,
            scoped_authorization_present: false,
            decision_lease_valid: false,
            guardian_allows: false,
            risk_config_hash_present: false,
            instrument_identity_hash_present: false,
            idempotency_key_present: false,
            market_open: true,
            cost_model_present: false,
            universe_match: false,
            credential_available: false,
            connector_available: false,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct BrokerCapabilityRequest {
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub instrument_kind: InstrumentKind,
    pub operation: BrokerOperation,
}

impl BrokerCapabilityRequest {
    pub const fn stock_etf_ibkr_paper(
        instrument_kind: InstrumentKind,
        operation: BrokerOperation,
    ) -> Self {
        Self {
            asset_lane: AssetLane::StockEtfCash,
            broker: Broker::Ibkr,
            environment: BrokerEnvironment::Paper,
            instrument_kind,
            operation,
        }
    }
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct BrokerCapabilityDecision {
    pub asset_lane: AssetLane,
    pub broker: Broker,
    pub environment: BrokerEnvironment,
    pub operation: BrokerOperation,
    pub authority_scope: AuthorityScope,
    pub allowed: bool,
    pub denial_reason: Option<StockEtfDenialReason>,
}

impl BrokerCapabilityDecision {
    pub fn allow(request: BrokerCapabilityRequest) -> Self {
        Self {
            asset_lane: request.asset_lane,
            broker: request.broker,
            environment: request.environment,
            operation: request.operation,
            authority_scope: request.operation.authority_scope(),
            allowed: true,
            denial_reason: None,
        }
    }

    pub fn deny(request: BrokerCapabilityRequest, reason: StockEtfDenialReason) -> Self {
        Self {
            asset_lane: request.asset_lane,
            broker: request.broker,
            environment: request.environment,
            operation: request.operation,
            authority_scope: AuthorityScope::Denied,
            allowed: false,
            denial_reason: Some(reason),
        }
    }
}

pub fn evaluate_broker_operation(
    request: BrokerCapabilityRequest,
    flags: &StockEtfFeatureFlags,
    gates: &StockEtfGateInputs,
) -> BrokerCapabilityDecision {
    use BrokerOperation as Op;
    use StockEtfDenialReason as Deny;

    if request.asset_lane != AssetLane::StockEtfCash {
        return BrokerCapabilityDecision::deny(request, Deny::WrongAssetLane);
    }
    if request.broker != Broker::Ibkr {
        return BrokerCapabilityDecision::deny(request, Deny::WrongBroker);
    }
    if request.environment == BrokerEnvironment::LiveReservedDenied {
        return BrokerCapabilityDecision::deny(request, Deny::LiveReservedDenied);
    }
    if request.operation == Op::LiveOrderSubmit {
        return BrokerCapabilityDecision::deny(request, Deny::IbkrLiveNotAuthorized);
    }
    if request.operation == Op::MarginOrShort {
        return BrokerCapabilityDecision::deny(request, Deny::StockEtfCashOnly);
    }
    if request.operation == Op::OptionsOrCfd {
        return BrokerCapabilityDecision::deny(request, Deny::InstrumentKindDenied);
    }
    if request.operation == Op::TransferOrAccountWrite {
        return BrokerCapabilityDecision::deny(request, Deny::AccountWriteDenied);
    }
    if !request.instrument_kind.allowed_for_stock_etf_cash() {
        return BrokerCapabilityDecision::deny(request, Deny::InstrumentKindDenied);
    }
    if !flags.stock_etf_lane_enabled {
        return BrokerCapabilityDecision::deny(request, Deny::LaneDisabled);
    }
    if request.operation.is_read() && !flags.ibkr_readonly_enabled {
        return BrokerCapabilityDecision::deny(request, Deny::BrokerDisabled);
    }
    if request.operation.is_paper_write() && !flags.ibkr_paper_enabled {
        return BrokerCapabilityDecision::deny(request, Deny::BrokerDisabled);
    }
    if request.operation.is_paper_write() && flags.stock_etf_shadow_only {
        return BrokerCapabilityDecision::deny(request, Deny::ShadowOnly);
    }
    if request.operation.is_read() && !gates.external_surface_gate_passed {
        return BrokerCapabilityDecision::deny(request, Deny::AuthorizationInvalid);
    }
    if request.operation.is_shadow() {
        if !gates.cost_model_present {
            return BrokerCapabilityDecision::deny(request, Deny::CostModelMissing);
        }
        if !gates.universe_match {
            return BrokerCapabilityDecision::deny(request, Deny::UniverseMismatch);
        }
    }
    if request.operation.is_paper_write() {
        if !gates.market_open {
            return BrokerCapabilityDecision::deny(request, Deny::MarketClosed);
        }
        if !gates.credential_available {
            return BrokerCapabilityDecision::deny(request, Deny::CredentialUnavailable);
        }
        if !gates.connector_available {
            return BrokerCapabilityDecision::deny(request, Deny::ConnectorUnavailable);
        }
        if !gates.session_attested
            || !gates.scoped_authorization_present
            || !gates.risk_config_hash_present
            || !gates.instrument_identity_hash_present
            || !gates.idempotency_key_present
        {
            return BrokerCapabilityDecision::deny(request, Deny::AuthorizationInvalid);
        }
        if !gates.decision_lease_valid {
            return BrokerCapabilityDecision::deny(request, Deny::DecisionLeaseInvalid);
        }
        if !gates.guardian_allows {
            return BrokerCapabilityDecision::deny(request, Deny::GuardianDenied);
        }
    }
    BrokerCapabilityDecision::allow(request)
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
pub enum IbkrPaperOrderLifecycleState {
    LocalIntentCreated,
    RustAuthorityAccepted,
    BrokerSubmitRequested,
    BrokerAcknowledged,
    PartiallyFilled,
    Filled,
    CancelRequested,
    Cancelled,
    ReplaceRequested,
    Replaced,
    Rejected,
    Inactive,
    StateUnknown,
    ManualReviewRequired,
}

impl IbkrPaperOrderLifecycleState {
    pub const fn is_terminal(self) -> bool {
        matches!(
            self,
            Self::Filled
                | Self::Cancelled
                | Self::Rejected
                | Self::Inactive
                | Self::ManualReviewRequired
        )
    }
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StockEtfContractParseError {
    field: &'static str,
    input: String,
}

impl StockEtfContractParseError {
    fn unknown(field: &'static str, input: &str) -> Self {
        Self {
            field,
            input: input.to_string(),
        }
    }
}

impl fmt::Display for StockEtfContractParseError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "unknown {}: '{}'", self.field, self.input)
    }
}

impl std::error::Error for StockEtfContractParseError {}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum StockEtfConfigError {
    InvalidBool { key: &'static str, value: String },
    InvalidEnum { key: &'static str, value: String },
}

impl fmt::Display for StockEtfConfigError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::InvalidBool { key, value } => {
                write!(f, "invalid boolean flag {}='{}'", key, value)
            }
            Self::InvalidEnum { key, value } => {
                write!(f, "invalid enum flag {}='{}'", key, value)
            }
        }
    }
}

impl std::error::Error for StockEtfConfigError {}

fn parse_bool_flag(
    key: &'static str,
    value: Option<String>,
    default: bool,
) -> Result<bool, StockEtfConfigError> {
    let Some(raw) = value else {
        return Ok(default);
    };
    match raw.trim().to_ascii_lowercase().as_str() {
        "1" | "true" => Ok(true),
        "0" | "false" => Ok(false),
        _ => Err(StockEtfConfigError::InvalidBool { key, value: raw }),
    }
}

fn normalize_token(s: &str) -> String {
    s.trim().to_ascii_lowercase()
}
