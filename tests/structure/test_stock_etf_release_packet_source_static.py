from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
RELEASE_PACKET = ROOT / "rust/openclaw_types/src/stock_etf_release_packet.rs"
MAX_LINES = 800

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_RELEASE_ADR_PATH",
    "docs/adr/0048-ibkr-stock-etf-paper-shadow-lane.md",
    "STOCK_ETF_RELEASE_AMD_PATH",
    "AMD-2026-06-29-01-ibkr-stock-etf-paper-shadow-lane.md",
    "STOCK_ETF_RELEASE_SPEC_PATH",
    "stock_etf_cash_phase0_named_contract_packet.md",
    "STOCK_ETF_RELEASE_PACKET_CONTRACT_ID",
    '"stock_etf_release_packet_v1"',
    "pub struct StockEtfReleaseManifestHashV1",
    "pub struct StockEtfPgMigrationEvidenceV1",
    "pub struct StockEtfKillDisableCleanupProofV1",
    "pub struct StockEtfReleasePacketV1",
    "pub struct StockEtfReleaseVerdict",
    "pub enum StockEtfReleasePacketBlocker",
    "fn required_release_roles()",
    "fn contains_role(",
    "fn empty_or_invalid_hashes(",
}
REQUIRED_BLOCKERS = {
    "PacketIdMissing",
    "PacketIdMismatch",
    "SourceVersionMismatch",
    "AdrPathMismatch",
    "AmdPathMismatch",
    "SpecPathMismatch",
    "SourceCommitMissing",
    "CreatedAtMissing",
    "PmSignoffMissing",
    "OperatorSignoffMissing",
    "E2SignoffMissing",
    "E3SignoffMissing",
    "E4SignoffMissing",
    "QaSignoffMissing",
    "QcSignoffMissing",
    "MitSignoffMissing",
    "UnknownRequiredRoleMissing",
    "RoleReportsMissing",
    "E2LogHashInvalid",
    "E3RedactionLogHashInvalid",
    "E4LogHashInvalid",
    "QaLogHashInvalid",
    "ManifestHashesInvalid",
    "PgMigrationManifestHashInvalid",
    "PgDryRunLogMissing",
    "PgDoubleApplyLogMissing",
    "RedactionFixtureHashInvalid",
    "GuiScreenshotsMissing",
    "DqManifestsMissing",
    "ScorecardRegenerationMissing",
    "KillLaneFlagNotDisabled",
    "KillReadonlyFlagNotDisabled",
    "KillPaperFlagNotDisabled",
    "KillShadowOnlyFlagNotPreserved",
    "CollectorStopProofMissing",
    "GuiDisableProofMissing",
    "LiveSecretAbsenceProofMissing",
    "EvidenceArchiveNotForwardOnly",
    "DestructiveDbCleanupRequested",
    "KillDisableProofHashInvalid",
    "EvidenceArchivePointerMissing",
    "EvidenceArchiveHashInvalid",
    "PaperShadowWindowIncomplete",
    "EngineeringShakedownIncomplete",
    "SecretContentSerialized",
    "LiveOrTinyLiveAuthorityPresent",
    "ReleasePacketNotSealed",
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
    return RELEASE_PACKET.read_text(encoding="utf-8")


def _block_between(source: str, start_token: str, end_tokens: tuple[str, ...]) -> str:
    start = source.index(start_token)
    end = len(source)
    for token in end_tokens:
        candidate = source.find(token, start + len(start_token))
        if candidate != -1:
            end = min(end, candidate)
    return source[start:end]


def _impl_block(source: str, type_name: str) -> str:
    return _block_between(
        source,
        f"impl {type_name} {{",
        ("\nimpl ", "\n#[derive", "\nfn "),
    )


def _default_block(source: str, type_name: str) -> str:
    return _block_between(
        source,
        f"impl Default for {type_name} {{",
        ("\nimpl ", "\n#[derive", "\nfn "),
    )


def _accepted_fixture_block(source: str, type_name: str) -> str:
    impl = _impl_block(source, type_name)
    return _block_between(
        impl,
        "pub fn accepted_fixture() -> Self",
        ("\n    pub fn validate(&self)",),
    )


def _release_packet_fixture_block(source: str) -> str:
    return _accepted_fixture_block(source, "StockEtfReleasePacketV1")


def _kill_disable_cleanup_fixture_block(source: str) -> str:
    return _accepted_fixture_block(source, "StockEtfKillDisableCleanupProofV1")


def test_stock_etf_release_packet_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_release_packet_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "packet_id: String::new()" in source
    assert "source_version: 0" in source
    assert "paper_shadow_window_complete: false" in source
    assert "engineering_shakedown_complete: false" in source
    assert "secret_content_serialized: false" in source
    assert "ibkr_live_or_tiny_live_authorized: false" in source
    assert "sealed: false" in source
    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_release_packet_source_keeps_manifest_migration_and_kill_proofs() -> None:
    source = _source()

    assert "pub fn fixture(label: &str, fill: char) -> Self" in source
    assert "!self.label.trim().is_empty() && is_sha256_hex(&self.sha256)" in source
    assert "migrations_declared: false" in source
    assert "pub fn no_migration_fixture() -> Self" in source
    assert "pub fn migration_fixture() -> Self" in source
    assert "if self.migrations_declared" in source
    assert "!is_sha256_hex(&self.migration_manifest_hash)" in source
    assert "!is_sha256_hex(&self.pg_dry_run_log_hash)" in source
    assert "!is_sha256_hex(&self.pg_double_apply_log_hash)" in source
    assert "stock_etf_lane_enabled_false: true" in source
    assert "ibkr_readonly_enabled_false: true" in source
    assert "ibkr_paper_enabled_false: true" in source
    assert "stock_etf_shadow_only_true: true" in source
    assert "collector_stopped: true" in source
    assert "gui_stock_views_disabled_or_hidden: true" in source
    assert "live_secret_absence_proven: true" in source
    assert "evidence_archive_forward_only: true" in source
    assert "destructive_db_cleanup_requested: false" in source


def test_stock_etf_release_packet_source_keeps_accepted_release_fixture_without_live_authority() -> None:
    source = _source()
    fixture = _release_packet_fixture_block(source)

    assert "packet_id: STOCK_ETF_RELEASE_PACKET_CONTRACT_ID.to_string()" in fixture
    assert "source_version: 1" in fixture
    assert "adr_path: STOCK_ETF_RELEASE_ADR_PATH.to_string()" in fixture
    assert "amd_path: STOCK_ETF_RELEASE_AMD_PATH.to_string()" in fixture
    assert "spec_path: STOCK_ETF_RELEASE_SPEC_PATH.to_string()" in fixture
    assert "reviewer_roles: required_release_roles()" in fixture
    assert "StockEtfReleaseManifestHashV1::fixture" in fixture
    assert "pg_migration_evidence: StockEtfPgMigrationEvidenceV1::no_migration_fixture()" in fixture
    assert "kill_disable_cleanup_proof: StockEtfKillDisableCleanupProofV1::accepted_fixture()" in fixture
    assert "evidence_archive_pointer: \"archive://stock-etf/fixture\".to_string()" in fixture
    assert "paper_shadow_window_complete: true" in fixture
    assert "engineering_shakedown_complete: true" in fixture
    assert "secret_content_serialized: false" in fixture
    assert "ibkr_live_or_tiny_live_authorized: false" in fixture
    assert "sealed: true" in fixture


def test_stock_etf_release_packet_fixture_excludes_live_secret_and_unsealed_crosswire() -> None:
    source = _source()
    fixture = _release_packet_fixture_block(source)
    default_impl = _default_block(source, "StockEtfReleasePacketV1")

    for forbidden in (
        "source_version: 0",
        "source_commit: String::new()",
        "created_at_ms: 0",
        "reviewer_roles: Vec::new()",
        "role_report_paths: Vec::new()",
        "manifest_hashes: Vec::new()",
        "evidence_archive_pointer: String::new()",
        "paper_shadow_window_complete: false",
        "engineering_shakedown_complete: false",
        "secret_content_serialized: true",
        "ibkr_live_or_tiny_live_authorized: true",
        "sealed: false",
    ):
        assert forbidden not in fixture

    for fail_closed in (
        "packet_id: String::new()",
        "source_version: 0",
        "source_commit: String::new()",
        "created_at_ms: 0",
        "reviewer_roles: Vec::new()",
        "role_report_paths: Vec::new()",
        "manifest_hashes: Vec::new()",
        "evidence_archive_pointer: String::new()",
        "paper_shadow_window_complete: false",
        "engineering_shakedown_complete: false",
        "secret_content_serialized: false",
        "ibkr_live_or_tiny_live_authorized: false",
        "sealed: false",
    ):
        assert fail_closed in default_impl


def test_stock_etf_release_packet_source_keeps_kill_disable_cleanup_fixture_safe() -> None:
    source = _source()
    fixture = _kill_disable_cleanup_fixture_block(source)

    for required in (
        "stock_etf_lane_enabled_false: true",
        "ibkr_readonly_enabled_false: true",
        "ibkr_paper_enabled_false: true",
        "stock_etf_shadow_only_true: true",
        "collector_stopped: true",
        "gui_stock_views_disabled_or_hidden: true",
        "live_secret_absence_proven: true",
        "evidence_archive_forward_only: true",
        "destructive_db_cleanup_requested: false",
        'proof_hash: "4".repeat(64)',
    ):
        assert required in fixture

    for forbidden in (
        "stock_etf_lane_enabled_false: false",
        "ibkr_readonly_enabled_false: false",
        "ibkr_paper_enabled_false: false",
        "stock_etf_shadow_only_true: false",
        "collector_stopped: false",
        "gui_stock_views_disabled_or_hidden: false",
        "live_secret_absence_proven: false",
        "evidence_archive_forward_only: false",
        "destructive_db_cleanup_requested: true",
        "proof_hash: String::new()",
    ):
        assert forbidden not in fixture


def test_stock_etf_release_packet_source_keeps_role_and_evidence_validation() -> None:
    source = _source()

    assert "self.packet_id.trim().is_empty()" in source
    assert "self.packet_id != STOCK_ETF_RELEASE_PACKET_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.adr_path != STOCK_ETF_RELEASE_ADR_PATH" in source
    assert "self.amd_path != STOCK_ETF_RELEASE_AMD_PATH" in source
    assert "self.spec_path != STOCK_ETF_RELEASE_SPEC_PATH" in source
    assert "self.source_commit.trim().is_empty()" in source
    assert "self.created_at_ms == 0" in source
    assert "for role in required_release_roles()" in source
    assert '"PM" => Blocker::PmSignoffMissing' in source
    assert '"Operator" => Blocker::OperatorSignoffMissing' in source
    assert '"E2" => Blocker::E2SignoffMissing' in source
    assert '"E3" => Blocker::E3SignoffMissing' in source
    assert '"E4" => Blocker::E4SignoffMissing' in source
    assert '"QA" => Blocker::QaSignoffMissing' in source
    assert '"QC" => Blocker::QcSignoffMissing' in source
    assert '"MIT" => Blocker::MitSignoffMissing' in source
    assert "self.role_report_paths.is_empty()" in source
    assert "!is_sha256_hex(&self.e2_log_hash)" in source
    assert "!is_sha256_hex(&self.e3_redaction_log_hash)" in source
    assert "!is_sha256_hex(&self.e4_log_hash)" in source
    assert "!is_sha256_hex(&self.qa_log_hash)" in source
    assert "self.manifest_hashes.is_empty()" in source


def test_stock_etf_release_packet_source_keeps_final_packet_denials() -> None:
    source = _source()

    assert "blockers.extend(self.pg_migration_evidence.validate().blockers)" in source
    assert "!is_sha256_hex(&self.redaction_fixture_hash)" in source
    assert "empty_or_invalid_hashes(&self.gui_screenshot_hashes)" in source
    assert "empty_or_invalid_hashes(&self.dq_manifest_hashes)" in source
    assert "empty_or_invalid_hashes(&self.scorecard_regeneration_hashes)" in source
    assert "blockers.extend(self.kill_disable_cleanup_proof.validate().blockers)" in source
    assert "self.evidence_archive_pointer.trim().is_empty()" in source
    assert "!is_sha256_hex(&self.evidence_archive_hash)" in source
    assert "if !self.paper_shadow_window_complete" in source
    assert "if !self.engineering_shakedown_complete" in source
    assert "if self.secret_content_serialized" in source
    assert "if self.ibkr_live_or_tiny_live_authorized" in source
    assert "if !self.sealed" in source
    assert '&["PM", "Operator", "E2", "E3", "E4", "QA", "QC", "MIT"]' in source
    assert "values.is_empty() || values.iter().any(|value| !is_sha256_hex(value))" in source


def test_stock_etf_release_packet_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{RELEASE_PACKET}: contains forbidden token {token!r}")

    assert violations == []
