from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
STRATEGY_HYPOTHESIS = ROOT / "rust/openclaw_types/src/stock_etf_strategy_hypothesis.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID",
    '"stock_etf_strategy_hypothesis_contract_v1"',
    "pub struct StockEtfStrategyHypothesisV1",
    "impl Default for StockEtfStrategyHypothesisV1",
    "impl StockEtfStrategyHypothesisV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfStrategyHypothesisVerdict<StockEtfStrategyHypothesisBlocker>",
    "pub enum StockEtfStrategyFamily",
    "pub enum StockEtfStrategyTimeframe",
    "pub enum StockEtfStrategyInstrumentScope",
    "pub struct StockEtfStrategyHypothesisVerdict",
    "pub enum StockEtfStrategyHypothesisBlocker",
    "fn validate_hashes(",
    "fn validate_limits_and_controls(",
    "fn valid_identifier(value: &str) -> bool",
    "is_sha256_hex",
}
REQUIRED_FIELDS = {
    "contract_id",
    "source_version",
    "asset_lane",
    "broker",
    "hypothesis_id",
    "hypothesis_version",
    "strategy_family",
    "primary_timeframe",
    "instrument_scope",
    "universe_hash",
    "pit_universe_contract_hash",
    "benchmark_version_hash",
    "cost_model_version_hash",
    "entry_rule_hash",
    "exit_rule_hash",
    "risk_rule_hash",
    "feature_set_hash",
    "data_source_policy_hash",
    "statistical_design_hash",
    "hypothesis_preregistration_hash",
    "expected_holding_period_days_min",
    "max_turnover_per_month_bps",
    "max_constituents_used",
    "independent_observation_target",
    "lookahead_bias_controls_present",
    "survivorship_bias_controls_present",
    "multiple_testing_control_present",
    "benchmark_relative_metric_defined",
    "cost_after_metric_defined",
    "no_options_cfd_margin_short",
    "paper_shadow_only",
    "profitability_claimed",
    "live_or_tiny_live_authority_claimed",
    "bybit_live_execution_unchanged",
    "ibkr_live_denied",
    "ibkr_contact_performed",
    "secret_content_serialized",
}
REQUIRED_ENUM_SURFACE = {
    "StockEtfStrategyFamily::DailyMomentum",
    "StockEtfStrategyFamily::WeeklyMomentum",
    "StockEtfStrategyFamily::SectorRotation",
    "StockEtfStrategyFamily::EtfTrendRiskOff",
    "    EventDrivenReservedDenied,",
    "    HighFrequencyReservedDenied,",
    "StockEtfStrategyFamily::UnknownDenied",
    "StockEtfStrategyTimeframe::Daily",
    "StockEtfStrategyTimeframe::Weekly",
    "    IntradayReservedDenied,",
    "StockEtfStrategyTimeframe::UnknownDenied",
    "    StockOnly,",
    "    EtfOnly,",
    "StockEtfStrategyInstrumentScope::StockAndEtf",
    "StockEtfStrategyInstrumentScope::UnknownDenied",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "HypothesisIdInvalid",
    "HypothesisVersionInvalid",
    "StrategyFamilyDenied",
    "TimeframeDenied",
    "InstrumentScopeDenied",
    "UniverseHashInvalid",
    "PitUniverseContractHashInvalid",
    "BenchmarkVersionHashInvalid",
    "CostModelVersionHashInvalid",
    "EntryRuleHashInvalid",
    "ExitRuleHashInvalid",
    "RiskRuleHashInvalid",
    "FeatureSetHashInvalid",
    "DataSourcePolicyHashInvalid",
    "StatisticalDesignHashInvalid",
    "HypothesisPreregistrationHashInvalid",
    "HoldingPeriodTooShort",
    "TurnoverLimitMissing",
    "TurnoverLimitTooHigh",
    "MaxConstituentsMissing",
    "MaxConstituentsTooBroad",
    "IndependentObservationTargetTooLow",
    "LookaheadControlsMissing",
    "SurvivorshipControlsMissing",
    "MultipleTestingControlMissing",
    "BenchmarkMetricMissing",
    "CostAfterMetricMissing",
    "ForbiddenInstrumentPolicyMissing",
    "PaperShadowOnlyMissing",
    "PrematureProfitabilityClaim",
    "LiveOrTinyLiveAuthorityClaimed",
    "BybitLiveExecutionNotProtected",
    "IbkrLiveNotDenied",
    "IbkrContactPerformed",
    "SecretContentSerialized",
}
FORBIDDEN_RUNTIME_TOKENS = (
    "std::env",
    "env::var",
    "var_os",
    "vars_os",
    "std::fs",
    "std::path::Path",
    "File::open",
    "OpenOptions",
    "read_to_string",
    "read_to_end",
    "include_str!",
    "include_bytes!",
    "std::net",
    "TcpStream",
    "UdpSocket",
    "tokio::net",
    "reqwest",
    "hyper::",
    "ureq",
    "ib_insync",
    "ibapi",
    "IBApi",
    "std::time",
    "SystemTime",
    "Instant",
    "chrono",
    "Utc::now",
    "Local::now",
    "std::thread",
    "thread::spawn",
    "tokio::spawn",
    "tokio::task",
    "tokio::time",
    "sleep(",
    "std::process",
    "process::Command",
    "Command::new",
    ".spawn(",
    "BybitRestClient",
    "BybitPrivateWs",
    "bybit_rest_client::",
    "bybit_private_ws::",
    "order_manager::",
    "OrderManager",
    "CreateOrderRequest",
    "OrderResponse",
    ".place_order(",
    ".cancel_order(",
    ".replace_order(",
    ".modify_order(",
    ".create_order(",
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key",
    "api_secret",
    "password",
    "token =",
    "OPENCLAW_",
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return STRATEGY_HYPOTHESIS.read_text(encoding="utf-8")


def test_stock_etf_strategy_hypothesis_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_strategy_hypothesis_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_FIELDS | REQUIRED_ENUM_SURFACE:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_strategy_hypothesis_source_keeps_fail_closed_default() -> None:
    source = _source()

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "hypothesis_id: String::new()" in source
    assert "hypothesis_version: String::new()" in source
    assert "strategy_family: StockEtfStrategyFamily::UnknownDenied" in source
    assert "primary_timeframe: StockEtfStrategyTimeframe::UnknownDenied" in source
    assert "instrument_scope: StockEtfStrategyInstrumentScope::UnknownDenied" in source
    assert "expected_holding_period_days_min: 0" in source
    assert "max_turnover_per_month_bps: 0" in source
    assert "max_constituents_used: 0" in source
    assert "independent_observation_target: 0" in source
    assert "lookahead_bias_controls_present: false" in source
    assert "survivorship_bias_controls_present: false" in source
    assert "multiple_testing_control_present: false" in source
    assert "benchmark_relative_metric_defined: false" in source
    assert "cost_after_metric_defined: false" in source
    assert "no_options_cfd_margin_short: false" in source
    assert "paper_shadow_only: false" in source
    assert "profitability_claimed: false" in source
    assert "live_or_tiny_live_authority_claimed: false" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "ibkr_live_denied: false" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_strategy_hypothesis_source_keeps_accepted_fixture_boundary() -> None:
    source = _source()

    assert "contract_id: STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert 'hypothesis_id: "stock_etf_daily_momentum_us_large_100_v1".to_string()' in source
    assert 'hypothesis_version: "v1_20260301".to_string()' in source
    assert "strategy_family: StockEtfStrategyFamily::DailyMomentum" in source
    assert "primary_timeframe: StockEtfStrategyTimeframe::Daily" in source
    assert "instrument_scope: StockEtfStrategyInstrumentScope::StockAndEtf" in source
    assert "universe_hash: hash('1')" in source
    assert "pit_universe_contract_hash: hash('2')" in source
    assert "benchmark_version_hash: hash('3')" in source
    assert "cost_model_version_hash: hash('4')" in source
    assert "entry_rule_hash: hash('5')" in source
    assert "exit_rule_hash: hash('6')" in source
    assert "risk_rule_hash: hash('7')" in source
    assert "feature_set_hash: hash('8')" in source
    assert "data_source_policy_hash: hash('9')" in source
    assert "statistical_design_hash: hash('a')" in source
    assert "hypothesis_preregistration_hash: hash('b')" in source
    assert "expected_holding_period_days_min: 3" in source
    assert "max_turnover_per_month_bps: 5_000" in source
    assert "max_constituents_used: 100" in source
    assert "independent_observation_target: 50" in source
    assert "lookahead_bias_controls_present: true" in source
    assert "survivorship_bias_controls_present: true" in source
    assert "multiple_testing_control_present: true" in source
    assert "benchmark_relative_metric_defined: true" in source
    assert "cost_after_metric_defined: true" in source
    assert "no_options_cfd_margin_short: true" in source
    assert "paper_shadow_only: true" in source
    assert "profitability_claimed: false" in source
    assert "live_or_tiny_live_authority_claimed: false" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "ibkr_live_denied: true" in source
    assert "ibkr_contact_performed: false" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_strategy_hypothesis_fixture_excludes_live_profit_secret_and_bybit_crosswire() -> None:
    source = _source()
    fixture = source.split("pub fn accepted_fixture() -> Self", 1)[1].split(
        "pub fn validate(&self)",
        1,
    )[0]
    default_impl = source.split("impl Default for StockEtfStrategyHypothesisV1", 1)[1].split(
        "impl StockEtfStrategyHypothesisV1",
        1,
    )[0]

    for forbidden in (
        "paper_shadow_only: false",
        "profitability_claimed: true",
        "live_or_tiny_live_authority_claimed: true",
        "bybit_live_execution_unchanged: false",
        "ibkr_live_denied: false",
        "ibkr_contact_performed: true",
        "secret_content_serialized: true",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "paper_shadow_only: false",
        "profitability_claimed: false",
        "live_or_tiny_live_authority_claimed: false",
        "bybit_live_execution_unchanged: false",
        "ibkr_live_denied: false",
        "ibkr_contact_performed: false",
        "secret_content_serialized: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_strategy_hypothesis_source_keeps_identity_and_strategy_matrix() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_STRATEGY_HYPOTHESIS_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "!valid_identifier(&self.hypothesis_id)" in source
    assert "!valid_identifier(&self.hypothesis_version)" in source
    assert "StockEtfStrategyFamily::DailyMomentum" in source
    assert "StockEtfStrategyFamily::WeeklyMomentum" in source
    assert "StockEtfStrategyFamily::SectorRotation" in source
    assert "StockEtfStrategyFamily::EtfTrendRiskOff" in source
    assert "StockEtfStrategyTimeframe::Daily | StockEtfStrategyTimeframe::Weekly" in source
    assert "self.instrument_scope == StockEtfStrategyInstrumentScope::UnknownDenied" in source
    assert "validate_hashes(self, &mut blockers)" in source
    assert "validate_limits_and_controls(self, &mut blockers)" in source


def test_stock_etf_strategy_hypothesis_source_keeps_hash_checks() -> None:
    source = _source()

    for hash_field in (
        "universe_hash",
        "pit_universe_contract_hash",
        "benchmark_version_hash",
        "cost_model_version_hash",
        "entry_rule_hash",
        "exit_rule_hash",
        "risk_rule_hash",
        "feature_set_hash",
        "data_source_policy_hash",
        "statistical_design_hash",
        "hypothesis_preregistration_hash",
    ):
        assert f"!is_sha256_hex(&hypothesis.{hash_field})" in source


def test_stock_etf_strategy_hypothesis_source_keeps_limits_controls_and_boundaries() -> None:
    source = _source()

    assert "hypothesis.expected_holding_period_days_min < 1" in source
    assert "hypothesis.max_turnover_per_month_bps == 0" in source
    assert "hypothesis.max_turnover_per_month_bps > 10_000" in source
    assert "hypothesis.max_constituents_used == 0" in source
    assert "hypothesis.max_constituents_used > 500" in source
    assert "hypothesis.independent_observation_target < 30" in source
    assert "!hypothesis.lookahead_bias_controls_present" in source
    assert "!hypothesis.survivorship_bias_controls_present" in source
    assert "!hypothesis.multiple_testing_control_present" in source
    assert "!hypothesis.benchmark_relative_metric_defined" in source
    assert "!hypothesis.cost_after_metric_defined" in source
    assert "!hypothesis.no_options_cfd_margin_short" in source
    assert "!hypothesis.paper_shadow_only" in source
    assert "hypothesis.profitability_claimed" in source
    assert "hypothesis.live_or_tiny_live_authority_claimed" in source
    assert "!hypothesis.bybit_live_execution_unchanged" in source
    assert "!hypothesis.ibkr_live_denied" in source
    assert "hypothesis.ibkr_contact_performed" in source
    assert "hypothesis.secret_content_serialized" in source


def test_stock_etf_strategy_hypothesis_source_keeps_identifier_rules() -> None:
    source = _source()

    assert "trimmed == value" in source
    assert "trimmed.len() <= 96" in source
    assert "ch.is_ascii_alphanumeric()" in source
    assert "matches!(ch, '_' | '-' | '.' | ':' | '/')" in source


def test_stock_etf_strategy_hypothesis_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{STRATEGY_HYPOTHESIS}: contains forbidden token {token!r}")

    assert violations == []
