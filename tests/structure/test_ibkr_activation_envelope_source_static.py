from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
# 直接引用的來源檔字面 rel 路徑（同時滿足 rust-source-coverage 守衛的「測試源文字
# 含該檔 rel 路徑」判定;R10 教訓:新契約檔必配 source_static 守衛檔）。
ENVELOPE = ROOT / "rust/openclaw_types/src/ibkr_activation_envelope.rs"
ENVELOPE_CHECK = ROOT / "rust/openclaw_engine/src/ibkr_activation_envelope_check.rs"
# R16 EA3 mini-wiring:G4 entry 消費驗證器的檔（rust/openclaw_engine/src/ibkr_readonly_tws_client.rs）。
READONLY_CLIENT = ROOT / "rust/openclaw_engine/src/ibkr_readonly_tws_client.rs"
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


# ── R16 EA3 mini-wiring 守衛:G4 entry 消費驗證器(IB-NOTE-1) ─────────────────
# 斷言面更新申報:W8a 期「驗證器零 production caller」的 dormant 姿態自 R16 起部分
# 解除——G4 readonly entry(feature `ibkr_g4_contact` gated)成為 `check_readonly_contact`
# 首個 production caller。本節鎖住:①消費呼叫存在;②envelope 閘在全部既有 gate 之後、
# 唯一 socket 接觸之前(加閘=收緊,既有 gate 一個不少);③artifact 載入 owner-only
# (非 0o400/0o600 拒,沿 seal 慣例)。


def _client_code() -> str:
    return _strip_line_comments(READONLY_CLIENT.read_text(encoding="utf-8"))


def _g4_entry_region(code: str) -> str:
    idx = code.find("pub async fn g4_operator_triggered_first_contact")
    assert idx >= 0, "g4 entry fn absent from readonly client"
    return code[idx:]


def test_g4_entry_consumes_envelope_gate_before_socket_connect() -> None:
    # entry 區域內:ea3 gate 呼叫必須存在且先於唯一 TcpStream::connect(活化時刻緊接接觸)。
    region = _g4_entry_region(_client_code())
    gate_idx = region.find("ea3_envelope_activation_gate(")
    connect_idx = region.find("TcpStream::connect")
    assert gate_idx >= 0, "g4 entry does not consume ea3_envelope_activation_gate"
    assert connect_idx >= 0, "g4 entry lost its TcpStream::connect anchor"
    assert gate_idx < connect_idx, "envelope gate must precede any socket contact"


def test_g4_entry_keeps_every_preexisting_gate_before_envelope_gate() -> None:
    # 加閘=收緊:env APPLY → seal+approval → structural host/port 全部保留且序在
    # envelope 閘之前(前置 gate 失敗不燒 nonce)。
    region = _g4_entry_region(_client_code())
    env_idx = region.find('"OPENCLAW_IBKR_G4_CONTACT_APPLY"')
    seal_idx = region.find("phase2_first_contact_gate_ok()")
    endpoint_idx = region.find("assert_loopback_paper_endpoint(")
    gate_idx = region.find("ea3_envelope_activation_gate(")
    assert env_idx >= 0, "env APPLY gate removed"
    assert seal_idx >= 0, "seal+approval gate removed"
    assert endpoint_idx >= 0, "structural endpoint gate removed"
    assert gate_idx >= 0, "envelope gate absent"
    assert env_idx < seal_idx < endpoint_idx < gate_idx, (
        "pre-existing gate chain reordered/weakened relative to envelope gate"
    )


def test_readonly_client_envelope_gate_calls_validator_and_owner_only_loader() -> None:
    code = _client_code()
    # ①唯一裁決入口被消費(check_readonly_contact 首個 production caller)。
    assert "check_readonly_contact(" in code, "validator not consumed by readonly client"
    # ②artifact owner-only 紀律(沿 seal 慣例:非 0o400/0o600 拒)。
    assert "if mode != 0o600 && mode != 0o400 {" in code, "owner-only mode check missing"
    # ③兩個治理 artifact 檔名為固定 config 路徑(禁 env-var 憑證 fallback 語義)。
    assert 'const ACTIVATION_ENVELOPE_FILENAME: &str = "ibkr_activation_envelope_v1.json";' in code
    assert (
        'const ACTIVATION_CURRENT_EPOCHS_FILENAME: &str = "ibkr_activation_current_epochs.toml";'
        in code
    )
    # ④現值 epoch 絕不從 envelope 自帶值推導(撤銷機制不可自證):現值型別必須獨立存在。
    assert "pub(crate) struct ActivationCurrentEpochs" in code
