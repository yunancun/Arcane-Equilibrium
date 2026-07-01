from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DISABLE_CLEANUP = ROOT / "rust/openclaw_types/src/stock_etf_disable_cleanup_runbook.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID",
    '"stock_etf_kill_switch_and_disable_cleanup_runbook_v1"',
    "const REQUIRED_ENV_FLAGS",
    "const REQUIRED_PROOFS",
    "pub struct StockEtfDisableCleanupRunbookV1",
    "pub struct StockEtfDisableCleanupEnvFlagV1",
    "pub enum StockEtfDisableCleanupProofKind",
    "pub struct StockEtfDisableCleanupProofV1",
    "pub struct StockEtfDisableCleanupVerdict",
    "pub enum StockEtfDisableCleanupBlocker",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfDisableCleanupVerdict<StockEtfDisableCleanupBlocker>",
    "fn validate_env_flags(",
    "fn validate_env_flag(",
    "fn validate_proofs(",
    "fn validate_proof(",
    "fn expected_env_flag_value(name: &str) -> Option<&'static str>",
    "fn hash(fill: char) -> String",
}
REQUIRED_ENV_FLAG_PAIRS = {
    '("OPENCLAW_STOCK_ETF_LANE_ENABLED", "0")',
    '("OPENCLAW_IBKR_READONLY_ENABLED", "0")',
    '("OPENCLAW_IBKR_PAPER_ENABLED", "0")',
    '("OPENCLAW_STOCK_ETF_SHADOW_ONLY", "1")',
}
REQUIRED_PROOF_KINDS = {
    "CollectorStopped",
    "GuiStockViewsDisabledOrHidden",
    "LiveSecretAbsenceProven",
    "EvidenceArchiveForwardOnly",
    "DbForwardOnlyRetentionPreserved",
    "AppendOnlyAuditPreserved",
    "BybitLiveExecutionUnchanged",
}
REQUIRED_BLOCKERS = {
    "RunbookIdMismatch",
    "SourceVersionMismatch",
    "WrongAssetLane",
    "WrongBroker",
    "SourceArtifactHashInvalid",
    "BybitLiveExecutionNotProtected",
    "IbkrContactPerformed",
    "ConnectorRuntimeStarted",
    "PaperOrderRouted",
    "SecretSlotCreated",
    "SecretContentSerialized",
    "DestructiveDbCleanupRequested",
    "DbDeleteOrTruncateAllowed",
    "PaperShadowLaunchAuthorityClaimed",
    "TinyLiveAuthorityClaimed",
    "LiveAuthorityClaimed",
    "EnvFlagMissing",
    "EnvFlagDuplicated",
    "EnvFlagUnexpected",
    "EnvFlagExpectedValueMismatch",
    "EnvFlagObservedValueMismatch",
    "EnvFlagEvidenceHashInvalid",
    "ProofMissing",
    "ProofDuplicated",
    "ProofNotVerified",
    "ProofEvidenceHashInvalid",
    "ProofGrantsRuntimeAuthority",
    "ProofDestructiveCleanupClaimed",
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
    "SecretString",
    "SecretVec",
    "keyring",
)


def _source() -> str:
    return DISABLE_CLEANUP.read_text(encoding="utf-8")


def _function_block(source: str, start: str, end: str) -> str:
    return source.split(start, 1)[1].split(end, 1)[0]


def test_stock_etf_disable_cleanup_runbook_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_disable_cleanup_runbook_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_ENV_FLAG_PAIRS | REQUIRED_PROOF_KINDS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_disable_cleanup_runbook_source_keeps_fail_closed_default() -> None:
    source = _source()

    assert "runbook_id: String::new()" in source
    assert "source_version: 0" in source
    assert "asset_lane: AssetLane::CryptoPerp" in source
    assert "broker: Broker::Bybit" in source
    assert "source_artifact_hash: String::new()" in source
    assert "bybit_live_execution_unchanged: false" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "paper_order_routed: false" in source
    assert "secret_slot_created: false" in source
    assert "secret_content_serialized: false" in source
    assert "destructive_db_cleanup_requested: false" in source
    assert "db_delete_or_truncate_allowed: false" in source
    assert "paper_shadow_launch_authorized: false" in source
    assert "tiny_live_authorized: false" in source
    assert "live_authorized: false" in source
    assert "env_flags: Vec::new()" in source
    assert "proofs: Vec::new()" in source


def test_stock_etf_disable_cleanup_runbook_source_keeps_accepted_fixture_boundary() -> None:
    source = _source()

    assert "runbook_id: STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "asset_lane: AssetLane::StockEtfCash" in source
    assert "broker: Broker::Ibkr" in source
    assert "source_artifact_hash: hash('1')" in source
    assert "bybit_live_execution_unchanged: true" in source
    assert "ibkr_contact_performed: false" in source
    assert "connector_runtime_started: false" in source
    assert "paper_order_routed: false" in source
    assert "secret_slot_created: false" in source
    assert "secret_content_serialized: false" in source
    assert "destructive_db_cleanup_requested: false" in source
    assert "db_delete_or_truncate_allowed: false" in source
    assert "paper_shadow_launch_authorized: false" in source
    assert "tiny_live_authorized: false" in source
    assert "live_authorized: false" in source
    assert "env_flags: REQUIRED_ENV_FLAGS" in source
    assert "proofs: REQUIRED_PROOFS" in source
    assert "grants_runtime_authority: false" in source
    assert "destructive_cleanup_claimed: false" in source


def test_stock_etf_disable_cleanup_runbook_source_keeps_validation_matrix() -> None:
    source = _source()

    assert "self.runbook_id != STOCK_ETF_DISABLE_CLEANUP_RUNBOOK_ID" in source
    assert "self.source_version != 1" in source
    assert "self.asset_lane != AssetLane::StockEtfCash" in source
    assert "self.broker != Broker::Ibkr" in source
    assert "!is_sha256_hex(&self.source_artifact_hash)" in source
    assert "!self.bybit_live_execution_unchanged" in source
    assert "self.ibkr_contact_performed" in source
    assert "self.connector_runtime_started" in source
    assert "self.paper_order_routed" in source
    assert "self.secret_slot_created" in source
    assert "self.secret_content_serialized" in source
    assert "self.destructive_db_cleanup_requested" in source
    assert "self.db_delete_or_truncate_allowed" in source
    assert "self.paper_shadow_launch_authorized" in source
    assert "self.tiny_live_authorized" in source
    assert "self.live_authorized" in source
    assert "validate_env_flags(&self.env_flags, &mut blockers)" in source
    assert "validate_proofs(&self.proofs, &mut blockers)" in source


def test_stock_etf_disable_cleanup_runbook_source_keeps_env_and_proof_validation() -> None:
    source = _source()

    assert "for (name, _) in REQUIRED_ENV_FLAGS" in source
    assert "flags.iter().filter(|flag| flag.name == *name).collect()" in source
    assert "if matches.is_empty()" in source
    assert "if matches.len() > 1" in source
    assert "expected_env_flag_value(&flag.name).is_none()" in source
    assert "flag.expected_value != expected" in source
    assert "flag.observed_value != expected" in source
    assert "!is_sha256_hex(&flag.evidence_hash)" in source
    assert "for kind in REQUIRED_PROOFS" in source
    assert "proofs.iter().filter(|proof| proof.kind == *kind).collect()" in source
    assert "if !proof.verified" in source
    assert "!is_sha256_hex(&proof.evidence_hash)" in source
    assert "proof.grants_runtime_authority" in source
    assert "proof.destructive_cleanup_claimed" in source


def test_stock_etf_disable_cleanup_runbook_source_keeps_exact_blocker_order() -> None:
    source = _source()
    runbook = _function_block(
        source,
        "pub fn validate(&self) -> StockEtfDisableCleanupVerdict<StockEtfDisableCleanupBlocker>",
        "StockEtfDisableCleanupVerdict::new(blockers)",
    )
    env_flags = _function_block(source, "fn validate_env_flags(", "fn validate_env_flag(")
    env_flag = _function_block(source, "fn validate_env_flag(", "fn validate_proofs(")
    proofs = _function_block(source, "fn validate_proofs(", "fn validate_proof(")
    proof = _function_block(source, "fn validate_proof(", "fn expected_env_flag_value(")

    for block, ordered_blockers in (
        (
            runbook,
            (
                "RunbookIdMismatch",
                "SourceVersionMismatch",
                "WrongAssetLane",
                "WrongBroker",
                "SourceArtifactHashInvalid",
                "BybitLiveExecutionNotProtected",
                "IbkrContactPerformed",
                "ConnectorRuntimeStarted",
                "PaperOrderRouted",
                "SecretSlotCreated",
                "SecretContentSerialized",
                "DestructiveDbCleanupRequested",
                "DbDeleteOrTruncateAllowed",
                "PaperShadowLaunchAuthorityClaimed",
                "TinyLiveAuthorityClaimed",
                "LiveAuthorityClaimed",
            ),
        ),
        (env_flags, ("EnvFlagMissing", "EnvFlagDuplicated", "EnvFlagUnexpected")),
        (
            env_flag,
            (
                "EnvFlagExpectedValueMismatch",
                "EnvFlagObservedValueMismatch",
                "EnvFlagEvidenceHashInvalid",
            ),
        ),
        (proofs, ("ProofMissing", "ProofDuplicated")),
        (
            proof,
            (
                "ProofNotVerified",
                "ProofEvidenceHashInvalid",
                "ProofGrantsRuntimeAuthority",
                "ProofDestructiveCleanupClaimed",
            ),
        ),
    ):
        positions = [block.index(f"Blocker::{blocker}") for blocker in ordered_blockers]
        assert positions == sorted(positions)


def test_stock_etf_disable_cleanup_runbook_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{DISABLE_CLEANUP}: contains forbidden token {token!r}")

    assert violations == []
