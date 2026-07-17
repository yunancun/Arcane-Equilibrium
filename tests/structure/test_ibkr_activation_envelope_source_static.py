from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字
# 含該檔 rel 路徑」判定;R10 教訓:新契約檔必配 source_static 守衛檔）。
ENVELOPE = ROOT / "rust/openclaw_types/src/ibkr_activation_envelope.rs"
ENVELOPE_CHECK = ROOT / "rust/openclaw_engine/src/ibkr_activation_envelope_check.rs"
MAX_LINES = 800

# ── types 契約層:契約 id + readonly 單值白名單 + 24h 窗上限 ────────────────────
REQUIRED_CONTRACT_TOKENS = {
    'pub const IBKR_ACTIVATION_ENVELOPE_CONTRACT_ID: &str = "ibkr_activation_envelope_v1";',
    "pub const IBKR_ACTIVATION_WINDOW_MAX_MS: u64 = 24 * 60 * 60 * 1000;",
}
REQUIRED_TYPE_TOKENS = {
    "pub enum IbkrActivationOperationScopeV1",
    "pub struct IbkrActivationEnvelopeV1",
    "pub fn classify_scope(raw: &str) -> Self",
    "impl Default for IbkrActivationOperationScopeV1",
    "impl Default for IbkrActivationEnvelopeV1",
    "pub fn validate(&self, now_ms: u64) -> IbkrActivationEnvelopeVerdict",
}
# §2 活化鐵律綁定全清單的封閉 blocker taxonomy（逐欄專屬拒因）。
REQUIRED_BLOCKER_VARIANTS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "EnvironmentNotReadonly",
    "OperationScopeDenied",
    "BuildGitShaInvalid",
    "AccountFingerprintInvalid",
    "SessionAttestationFingerprintInvalid",
    "RiskConfigHashInvalid",
    "OrderNotionalLimitNotZero",
    "PositionNotionalLimitNotZero",
    "OrdersPerDayLimitNotZero",
    "CostGateLineageInvalid",
    "GuardianLineageInvalid",
    "DecisionLeaseLineageInvalid",
    "OperatorIdentityMissing",
    "ActivationNonceInvalid",
    "MissingIssuedAt",
    "IssuedInFuture",
    "InvalidActivationWindow",
    "ActivationWindowTooLong",
    "EnvelopeExpired",
    "OrderRouted",
    "SecretContentSerialized",
}
# fail-closed 關鍵語義行（readonly 單值白名單/表外拒/readonly 額度恆零/snake_case serde）。
REQUIRED_SEMANTIC_TOKENS = {
    '#[serde(rename_all = "snake_case")]',
    '"readonly" => Self::Readonly,',
    "_ => Self::UnknownDenied,",
    "blockers.push(B::OperationScopeDenied);",
    "blockers.push(B::OrderNotionalLimitNotZero);",
    "blockers.push(B::PositionNotionalLimitNotZero);",
    "blockers.push(B::OrdersPerDayLimitNotZero);",
    "blockers.push(B::EnvelopeExpired);",
}
# source-only 契約層：不得開 socket / 讀 secret / 起牆鐘 / 觸碰 runtime material。
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
)
FORBIDDEN_SECRET_MATERIAL_TOKENS = (
    "api_key",
    "api_secret",
    "password",
    "OPENCLAW_",
    "SecretString",
    "SecretVec",
    "keyring",
)

# ── engine 驗證器層:唯一裁決入口 + 原子消費 + seal≠活化 + order verb 結構性拒 ──
REQUIRED_CHECK_TOKENS = {
    "pub(crate) fn check_readonly_contact(",
    "pub(crate) struct ActivationNonceLedger",
    "consumed: Mutex<HashSet<String>>",
    "OrderVerbStructurallyDenied",
    "OperationOutsideReadonlyScope",
    "SealIsNotActivationAuthority",
    "NonceAlreadyConsumed",
    "BuildGitShaMismatch",
    "RevocationEpochMismatch",
    "KillSwitchEpochMismatch",
    "EnvelopeAbsent",
}
# 只驗不發 + INV-1 隔離:驗證器 code(去註解)不得觸碰 permit 面型別、不得開 socket、
# 不得自讀 env/磁碟(seal_present 必須注入)、不得起牆鐘(now_ms 注入)。
FORBIDDEN_CHECK_CODE_TOKENS = (
    "ConnectPermitProvider",
    "PermitToken",
    "fn mint",
    "TcpStream",
    "std::net",
    "tokio::net",
    "std::env",
    "env::var",
    "std::fs",
    "File::open",
    "read_to_string",
    "std::time",
    "SystemTime",
    "Instant",
    "Utc::now",
)


def _source() -> str:
    return ENVELOPE.read_text(encoding="utf-8")


def _check_source() -> str:
    return ENVELOPE_CHECK.read_text(encoding="utf-8")


def _strip_line_comments(text: str) -> str:
    """移除每行 `//` 起的行註解（MODULE_NOTE 提及 permit 型別屬說明,不算觸碰;掃 code）。"""
    out = []
    for line in text.splitlines():
        idx = line.find("//")
        out.append(line if idx < 0 else line[:idx])
    return "\n".join(out)


# ── types 契約檔守衛 ─────────────────────────────────────────────────────────
def test_ibkr_activation_envelope_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_ibkr_activation_envelope_keeps_contract_id_and_window_cap() -> None:
    source = _source()
    for token in REQUIRED_CONTRACT_TOKENS:
        assert token in source, f"missing contract token {token!r}"


def test_ibkr_activation_envelope_keeps_types_and_pure_functions() -> None:
    source = _source()
    for token in REQUIRED_TYPE_TOKENS:
        assert token in source, f"missing type token {token!r}"


def test_ibkr_activation_envelope_keeps_closed_blocker_taxonomy() -> None:
    source = _source()
    for variant in REQUIRED_BLOCKER_VARIANTS:
        assert variant in source, f"missing blocker variant {variant!r}"


def test_ibkr_activation_envelope_keeps_fail_closed_semantics() -> None:
    source = _source()
    for token in REQUIRED_SEMANTIC_TOKENS:
        assert token in source, f"missing semantic token {token!r}"


def test_ibkr_activation_envelope_has_no_runtime_secret_socket_or_clock_tokens() -> None:
    source = _source()
    violations = []
    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{ENVELOPE}: contains forbidden token {token!r}")
    assert violations == []


# ── engine 驗證器檔守衛 ───────────────────────────────────────────────────────
def test_ibkr_activation_envelope_check_stays_below_governance_cap() -> None:
    assert len(_check_source().splitlines()) <= MAX_LINES


def test_ibkr_activation_envelope_check_keeps_verdict_and_ledger_surface() -> None:
    source = _check_source()
    for token in REQUIRED_CHECK_TOKENS:
        assert token in source, f"missing check token {token!r}"


def test_ibkr_activation_envelope_check_denies_before_consuming_nonce() -> None:
    # deny path 先於 nonce 消費(拒絕不燒授權):blocker 空檢查必須出現在 try_consume 前。
    code = _strip_line_comments(_check_source())
    deny_idx = code.find("if !blockers.is_empty()")
    consume_idx = code.find("ledger.try_consume(")
    assert deny_idx >= 0, "missing deny-before-consume guard"
    assert consume_idx >= 0, "missing atomic nonce consume call"
    assert deny_idx < consume_idx, "nonce consume must come after the deny gate"


def test_ibkr_activation_envelope_check_is_validate_only_and_permit_isolated() -> None:
    # 只驗不發 + INV-1 隔離:W8 前本驗證器不得接進 permit trait 位、不得自帶 IO/牆鐘。
    code = _strip_line_comments(_check_source())
    violations = []
    for token in FORBIDDEN_CHECK_CODE_TOKENS:
        if token in code:
            violations.append(f"{ENVELOPE_CHECK}: code contains forbidden token {token!r}")
    assert violations == []


def test_ibkr_activation_envelope_check_tests_are_cfg_test_gated() -> None:
    # 測試檔經 #[cfg(test)] path attribute 掛入(production 域排除 *_tests.rs 的前提)。
    source = _check_source()
    assert "#[cfg(test)]" in source
    assert '#[path = "ibkr_activation_envelope_check_tests.rs"]' in source
