from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
PROVENANCE = ROOT / "rust/openclaw_types/src/ibkr_market_data_provenance.rs"
QUOTE_ROW = ROOT / "rust/openclaw_types/src/ibkr_quote_row.rs"
MAX_LINES = 800

# W6-S3 溯源契約層:契約 id + entitlement 三態 + adjustment marker 封閉枚舉。
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_MARKET_DATA_PROVENANCE_CONTRACT_ID: &str = "stock_market_data_provenance_v1";',
    # W6-S4:calendar 未綁哨兵（fail-closed typed 態,絕不捏 hash 冒充已綁）。
    'pub const IBKR_CALENDAR_HASH_UNBOUND_SENTINEL: &str = "calendar_unbound";',
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrMarketDataEntitlementStateV1",
    "pub enum IbkrPriceAdjustmentV1",
    "pub struct IbkrMarketDataProvenanceV1",
    "pub fn provenance_hash_preimage(&self) -> String",
    "pub fn validate(&self, now_ms: u64) -> IbkrMarketDataProvenanceVerdict",
    "impl Default for IbkrMarketDataEntitlementStateV1",
    "impl Default for IbkrPriceAdjustmentV1",
    "impl Default for IbkrMarketDataProvenanceV1",
}
# entitlement 三態 + fail-closed 未知。
REQUIRED_ENTITLEMENT_VARIANTS = {
    "Entitled",
    "Delayed",
    "None",
    "UnknownDenied",
}
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "EntitlementStateUnknownDenied",
    "AdjustmentUnknownDenied",
    "FirstTickMissing",
    "LastTickMissing",
    "LastTickInFuture",
    "WindowOutOfOrder",
    "InstrumentIdentityHashInvalid",
    "CalendarHashInvalid",
    "CalendarUnbound",
    "ProvenanceHashInvalid",
    "OrderRouted",
    "SecretContentSerialized",
}
# fail-closed + 溯源錨語義（sha256 shape / 窗有序 / preimage 排除自指）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    "is_sha256_hex(&self.instrument_identity_hash)",
    "is_sha256_hex(&self.calendar_hash)",
    "is_sha256_hex(&self.provenance_hash)",
    # W6-S4:未綁哨兵分支先於形狀檢查（typed fail-closed,不捏 hash）。
    "self.calendar_hash == IBKR_CALENDAR_HASH_UNBOUND_SENTINEL",
    "self.last_tick_at_ms < self.first_tick_at_ms",
    "self.entitlement_state.as_wire()",
}
FORBIDDEN_RUNTIME_TOKENS = (
    "std::env",
    "env::var",
    "std::fs",
    "File::open",
    "include_str!",
    "std::net",
    "TcpStream",
    "tokio::net",
    "reqwest",
    "ibapi",
    "std::time",
    "SystemTime",
    "Instant",
    "chrono",
    "Utc::now",
    "std::thread",
    "tokio::spawn",
    "std::process",
    "Command::new",
    "sha2::",
    "use sha2",
    "Sha256::",
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key",
    "api_secret",
    "password",
    "OPENCLAW_",
    "SecretString",
    "keyring",
)


def _source() -> str:
    return PROVENANCE.read_text(encoding="utf-8")


def test_provenance_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_provenance_keeps_contract_id() -> None:
    source = _source()
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source, f"missing contract token {token!r}"


def test_provenance_keeps_types_and_pure_functions() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_provenance_keeps_entitlement_three_states() -> None:
    source = _source()
    for variant in REQUIRED_ENTITLEMENT_VARIANTS:
        assert variant in source, f"missing entitlement variant {variant!r}"


def test_provenance_keeps_blocker_taxonomy() -> None:
    source = _source()
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_provenance_keeps_fail_closed_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_provenance_computes_no_hash_in_types_crate() -> None:
    # 契約只驗 shape（is_sha256_hex）;雜湊計算歸消化層——types crate 不得引入雜湊依賴。
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{PROVENANCE}: contains forbidden token {token!r}")
    assert violations == []


def test_pairing_guard_quote_and_provenance_share_entitlement_vocabulary() -> None:
    # **配對守衛（跨檔）**：quote row 的 delayed provenance 強制與 provenance 的 entitlement
    # 三態必須同源共存——兩檔缺一則 delayed 標記無溯源落點/溯源無 tick 落點。
    quote = QUOTE_ROW.read_text(encoding="utf-8")
    prov = _source()
    assert "EntitlementProvenanceMismatch" in quote
    assert "enum IbkrTickEntitlementV1" in quote
    assert "enum IbkrMarketDataEntitlementStateV1" in prov
    # delayed 檔位在兩檔皆為一等公民。
    assert "Delayed" in quote and "Delayed" in prov
