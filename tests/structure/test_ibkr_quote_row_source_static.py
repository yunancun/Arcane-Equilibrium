from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用來源檔字面 rel 路徑（滿足 rust-source-coverage 守衛 + 本治理測試自身實質斷言）。
QUOTE_ROW = ROOT / "rust/openclaw_types/src/ibkr_quote_row.rs"
MAX_LINES = 2_000

# W6-S3 quote 行契約層:契約 id + tickType/entitlement/value-kind 封閉枚舉。
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_QUOTE_ROW_CONTRACT_ID: &str = "ibkr_quote_row_v1";',
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrTickValueKind",
    "pub enum IbkrQuoteFieldV1",
    "pub enum IbkrTickEntitlementV1",
    "pub enum IbkrTickTypeV1",
    "pub struct IbkrQuoteRowV1",
    "pub fn classify_wire_tick_type(id: i64) -> Self",
    "pub fn as_wire_tick_type(&self) -> Option<i64>",
    "pub fn logical_field(&self) -> Option<IbkrQuoteFieldV1>",
    "pub fn entitlement(&self) -> Option<IbkrTickEntitlementV1>",
    "pub fn value_kind(&self) -> Option<IbkrTickValueKind>",
    "pub fn validate(&self, now_ms: u64) -> IbkrQuoteRowVerdict",
    "impl Default for IbkrTickTypeV1",
    "impl Default for IbkrQuoteRowV1",
}
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "ConIdInvalid",
    "SymbolInvalid",
    "ReqIdInvalid",
    "TickTypeUnknownDenied",
    "PriceValueInvalid",
    "SizeValueInvalid",
    "EntitlementProvenanceMismatch",
    "CapturedAtMissing",
    "CapturedAtInFuture",
    "SeqMissing",
    "OrderRouted",
    "SecretContentSerialized",
}
# **配對守衛（source token 側）**：delayed↔realtime 對映六對 + delayed provenance 強制。
# logical_field 中每個 realtime 與其 delayed 共用同一 arm（`Self::X | Self::DelayedX => F::..`）
# 是配對不變量的源碼錨;behavioral 守衛在 Rust `delayed_realtime_pairing_invariant`。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    "Self::Bid | Self::DelayedBid => F::Bid,",
    "Self::Ask | Self::DelayedAsk => F::Ask,",
    "Self::Last | Self::DelayedLast => F::Last,",
    "Self::BidSize | Self::DelayedBidSize => F::BidSize,",
    "Self::AskSize | Self::DelayedAskSize => F::AskSize,",
    "Self::LastSize | Self::DelayedLastSize => F::LastSize,",
    "66 => Self::DelayedBid,",
    "71 => Self::DelayedLastSize,",
    "blockers.push(B::EntitlementProvenanceMismatch);",
    "if expected != self.entitlement {",
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
    return QUOTE_ROW.read_text(encoding="utf-8")


def test_quote_row_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_quote_row_keeps_contract_id() -> None:
    source = _source()
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source, f"missing contract token {token!r}"


def test_quote_row_keeps_types_and_pure_functions() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_quote_row_keeps_blocker_taxonomy() -> None:
    source = _source()
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_quote_row_keeps_pairing_and_provenance_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_quote_row_has_no_runtime_secret_socket_or_clock_tokens() -> None:
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{QUOTE_ROW}: contains forbidden token {token!r}")
    assert violations == []
