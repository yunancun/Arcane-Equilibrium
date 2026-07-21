from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB_EVIDENCE = ROOT / "rust/openclaw_types/src/stock_etf_db_evidence_ddl.rs"
from tests.structure.file_line_policy import MAX_FILE_LINES as MAX_LINES

REQUIRED_TYPE_TOKENS = {
    "STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH",
    "docs/execution_plan/specs/2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql",
    "stock_etf_db_evidence_ddl_v1.source_only.sql",
    "STOCK_ETF_DB_EVIDENCE_CONTRACT_ID",
    '"stock_etf_db_evidence_ddl_v1"',
    "const REQUIRED_SCHEMAS",
    "const REQUIRED_TABLES",
    "const REQUIRED_NATURAL_KEYS",
    "pub struct StockEtfDbEvidenceDdlContractV1",
    "pub fn accepted_fixture() -> Self",
    "pub fn validate(&self) -> StockEtfDbEvidenceDdlVerdict<StockEtfDbEvidenceDdlBlocker>",
    "pub fn audit_stock_etf_db_evidence_source_sql(raw: &str) -> StockEtfDbEvidenceDdlSourceAudit",
    "pub struct StockEtfDbEvidenceDdlSourceAudit",
    "pub struct StockEtfDbEvidenceDdlVerdict",
    "pub enum StockEtfDbEvidenceDdlBlocker",
    "pub enum StockEtfDbEvidenceDdlSourceBlocker",
    "fn normalize_sql(raw: &str) -> String",
    "fn extract_table_block(sql: &str, table: &str) -> Option<String>",
    "fn table_block_has_column_declaration(block: &str, column: &str) -> bool",
    "fn required_source_table_columns()",
    "fn required_foreign_key_fragments()",
    "fn natural_key_unique_fragment(key: &str) -> String",
    "fn contains_all(actual: &[String], required: &[&str]) -> bool",
}
REQUIRED_SCHEMAS = {
    '"broker"',
    '"research"',
    '"audit"',
}
REQUIRED_TABLES = {
    "broker.instruments",
    "broker.instrument_listings",
    "broker.market_sessions",
    "broker.corporate_actions",
    "broker.fx_rates",
    "broker.account_cash_ledger",
    "broker.paper_orders",
    "broker.paper_fills",
    "broker.commissions",
    "research.stock_shadow_signals",
    "research.stock_shadow_fills",
    "research.stock_etf_scorecard",
    "audit.asset_lane_events",
}
REQUIRED_NATURAL_KEYS = {
    "instrument:asset_lane,broker,symbol,listing_venue,currency,primary_exchange",
    "order:asset_lane,broker,environment,account_fingerprint,local_order_id",
    "fill:asset_lane,broker,environment,broker_order_id,execution_id",
    "scorecard:asset_lane,strategy_id,universe_version,benchmark_version,as_of_date",
}
REQUIRED_BLOCKERS = {
    "ContractIdMismatch",
    "SourceVersionMismatch",
    "SourceSqlPathMismatch",
    "SourceSqlHashInvalid",
    "SourceOnlyFlagMissing",
    "MigrationFilePathPresent",
    "CopiedToSqlMigrations",
    "DbApplyPerformed",
    "PgWritePerformed",
    "SqlxMigrationRegistered",
    "PmOperatorApplyAuthorizationClaimed",
    "E2ReviewRequirementMissing",
    "E4ReviewRequirementMissing",
    "LinuxPgDryRunRequirementMissing",
    "PgDoubleApplyRequirementMissing",
    "GuardAExistingTableColumnsMissing",
    "GuardBTypeSensitiveAddColumnMissing",
    "GuardCHotPathIndexesMissing",
    "RequiredSchemaMissing",
    "RequiredTableMissing",
    "RequiredNaturalKeyMissing",
    "StockAssetLaneCheckMissing",
    "IbkrBrokerCheckMissing",
    "LiveEnvironmentNotDenied",
    "PaperShadowTableSeparationMissing",
    "SyntheticShadowCheckMissing",
    "RawArtifactHashRequirementMissing",
    "AuditAssetLaneEventsMissing",
    "ForwardOnlyEvidenceRetentionMissing",
    "DestructiveCleanupRollbackNotDenied",
    "SecretContentSerialized",
}
REQUIRED_SOURCE_BLOCKERS = {
    "SourceOnlyBannerMissing",
    "MigrationApplyDenialMissing",
    "ForbiddenDestructiveOrMigrationStatement",
    "RequiredSchemaMissing",
    "GuardABlockMissing",
    "GuardBBlockMissing",
    "GuardCBlockMissing",
    "MigrationDryRunPlanMissing",
    "RequiredTableMissing",
    "RequiredTableColumnMissing",
    "RequiredNaturalKeyMissing",
    "RequiredForeignKeyMissing",
    "StockAssetLaneCheckMissing",
    "IbkrBrokerCheckMissing",
    "PaperEnvironmentCheckMissing",
    "LiveEnvironmentNotDenied",
    "SyntheticShadowCheckMissing",
    "RawArtifactHashRequirementMissing",
    "AuditAssetLaneEventsMissing",
    "ForwardOnlyAuditCommentMissing",
    "HypertableRetentionPlanMissing",
    "HotPathIndexMissing",
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
    return DB_EVIDENCE.read_text(encoding="utf-8")


def _contract_validate_block(source: str) -> str:
    return source.split(
        "pub fn validate(&self) -> StockEtfDbEvidenceDdlVerdict<StockEtfDbEvidenceDdlBlocker>",
        1,
    )[1].split("StockEtfDbEvidenceDdlVerdict::new(blockers)", 1)[0]


def _source_audit_block(source: str) -> str:
    return source.split(
        "pub fn audit_stock_etf_db_evidence_source_sql(raw: &str) -> StockEtfDbEvidenceDdlSourceAudit",
        1,
    )[1].split("StockEtfDbEvidenceDdlSourceAudit {", 1)[0]


def test_stock_etf_db_evidence_ddl_source_stays_below_governance_cap() -> None:
    assert len(_source().splitlines()) <= MAX_LINES


def test_stock_etf_db_evidence_ddl_source_keeps_contract_surface() -> None:
    source = _source()

    for token in REQUIRED_TYPE_TOKENS | REQUIRED_SCHEMAS | REQUIRED_TABLES | REQUIRED_NATURAL_KEYS:
        assert token in source
    for blocker in REQUIRED_BLOCKERS | REQUIRED_SOURCE_BLOCKERS:
        assert f"Blocker::{blocker}" in source or blocker in source

    assert "accepted: blockers.is_empty()" in source


def test_stock_etf_db_evidence_ddl_source_keeps_source_only_fixture_boundary() -> None:
    source = _source()

    assert "contract_id: String::new()" in source
    assert "source_version: 0" in source
    assert "source_only: false" in source
    assert "migration_file_path: String::new()" in source
    assert "copied_to_sql_migrations: false" in source
    assert "db_apply_performed: false" in source
    assert "pg_write_performed: false" in source
    assert "sqlx_migration_registered: false" in source
    assert "pm_operator_apply_authorized: false" in source
    assert "contract_id: STOCK_ETF_DB_EVIDENCE_CONTRACT_ID.to_string()" in source
    assert "source_version: 1" in source
    assert "source_sql_path: STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH.to_string()" in source
    assert 'source_sql_sha256: "1".repeat(64)' in source
    assert "source_only: true" in source
    assert "e2_review_required: true" in source
    assert "e4_review_required: true" in source
    assert "linux_pg_dry_run_required: true" in source
    assert "pg_double_apply_required: true" in source
    assert "guard_a_existing_table_columns: true" in source
    assert "guard_b_type_sensitive_add_column: true" in source
    assert "guard_c_hot_path_indexes: true" in source
    assert "live_environment_denied: true" in source
    assert "paper_shadow_separate_tables: true" in source
    assert "synthetic_shadow_check: true" in source
    assert "audit_asset_lane_events_present: true" in source
    assert "forward_only_evidence_retention: true" in source
    assert "destructive_cleanup_as_rollback_denied: true" in source
    assert "secret_content_serialized: false" in source


def test_stock_etf_db_evidence_ddl_source_keeps_contract_validation_matrix() -> None:
    source = _source()

    assert "self.contract_id != STOCK_ETF_DB_EVIDENCE_CONTRACT_ID" in source
    assert "self.source_version != 1" in source
    assert "self.source_sql_path != STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH" in source
    assert "!is_sha256_hex(&self.source_sql_sha256)" in source
    assert "!self.source_only" in source
    assert "!self.migration_file_path.trim().is_empty()" in source
    assert "self.copied_to_sql_migrations" in source
    assert "self.db_apply_performed" in source
    assert "self.pg_write_performed" in source
    assert "self.sqlx_migration_registered" in source
    assert "self.pm_operator_apply_authorized" in source
    assert "!self.e2_review_required" in source
    assert "!self.e4_review_required" in source
    assert "!self.linux_pg_dry_run_required" in source
    assert "!self.pg_double_apply_required" in source
    assert "!self.guard_a_existing_table_columns" in source
    assert "!self.guard_b_type_sensitive_add_column" in source
    assert "!self.guard_c_hot_path_indexes" in source
    assert "!contains_all(&self.required_schemas, REQUIRED_SCHEMAS)" in source
    assert "!contains_all(&self.required_tables, REQUIRED_TABLES)" in source
    assert "!contains_all(&self.required_natural_keys, REQUIRED_NATURAL_KEYS)" in source
    assert "!self.stock_tables_asset_lane_check" in source
    assert "!self.ibkr_facts_broker_check" in source
    assert "!self.live_environment_denied" in source
    assert "!self.paper_shadow_separate_tables" in source
    assert "!self.synthetic_shadow_check" in source
    assert "!self.raw_artifact_hash_required" in source
    assert "!self.audit_asset_lane_events_present" in source
    assert "!self.forward_only_evidence_retention" in source
    assert "!self.destructive_cleanup_as_rollback_denied" in source
    assert "self.secret_content_serialized" in source


def test_stock_etf_db_evidence_ddl_source_keeps_source_sql_auditor_checks() -> None:
    source = _source()

    assert 'sql.contains("source-only ddl draft")' in source
    assert 'sql.contains("do not copy into sql/migrations/ or apply to any database")' in source
    assert '"drop table"' in source
    assert '"drop schema"' in source
    assert '"truncate table"' in source
    assert '"delete from"' in source
    assert '"insert into _sqlx_migrations"' in source
    assert 'format!("create schema if not exists {schema};")' in source
    assert 'sql.contains("guard a")' in source
    assert 'sql.contains("information_schema.columns")' in source
    assert 'sql.contains("guard b")' in source
    assert 'sql.contains("data_type")' in source
    assert 'sql.contains("guard c")' in source
    assert 'sql.contains("pg_get_indexdef")' in source
    assert 'sql.contains("linux postgres dry-run")' in source
    assert 'sql.contains("idempotency double-apply proof")' in source
    assert 'sql.contains("pm/operator migration apply authorization")' in source
    assert "for table in REQUIRED_TABLES" in source
    assert "for (table, columns) in required_source_table_columns()" in source
    assert "for key in REQUIRED_NATURAL_KEYS" in source
    assert "for foreign_key in required_foreign_key_fragments()" in source
    assert 'sql.matches("check (asset_lane = ' in source
    assert 'sql.matches("check (broker = ' in source
    assert 'sql.contains("check (environment = ' in source
    assert "sql.contains(\"'live'\")" in source
    assert 'sql.contains("create table if not exists research.stock_shadow_fills")' in source
    assert "synthetic_shadow boolean not null default true check (synthetic_shadow = true)" in source
    assert 'sql.matches("raw_artifact_hash").count() < 12' in source
    assert 'sql.contains("create table if not exists audit.asset_lane_events")' in source
    assert 'sql.contains("append-only asset lane audit event contract")' in source
    assert 'sql.contains("hypertable/retention promotion plan")' in source
    assert 'sql.contains("create_hypertable")' in source
    assert 'sql.contains("add_retention_policy")' in source
    assert 'sql.matches("create index if not exists").count()' in source


def test_stock_etf_db_evidence_ddl_source_keeps_exact_blocker_order() -> None:
    source = _source()
    contract_ordered_blockers = (
        "ContractIdMismatch",
        "SourceVersionMismatch",
        "SourceSqlPathMismatch",
        "SourceSqlHashInvalid",
        "SourceOnlyFlagMissing",
        "MigrationFilePathPresent",
        "CopiedToSqlMigrations",
        "DbApplyPerformed",
        "PgWritePerformed",
        "SqlxMigrationRegistered",
        "PmOperatorApplyAuthorizationClaimed",
        "E2ReviewRequirementMissing",
        "E4ReviewRequirementMissing",
        "LinuxPgDryRunRequirementMissing",
        "PgDoubleApplyRequirementMissing",
        "GuardAExistingTableColumnsMissing",
        "GuardBTypeSensitiveAddColumnMissing",
        "GuardCHotPathIndexesMissing",
        "RequiredSchemaMissing",
        "RequiredTableMissing",
        "RequiredNaturalKeyMissing",
        "StockAssetLaneCheckMissing",
        "IbkrBrokerCheckMissing",
        "LiveEnvironmentNotDenied",
        "PaperShadowTableSeparationMissing",
        "SyntheticShadowCheckMissing",
        "RawArtifactHashRequirementMissing",
        "AuditAssetLaneEventsMissing",
        "ForwardOnlyEvidenceRetentionMissing",
        "DestructiveCleanupRollbackNotDenied",
        "SecretContentSerialized",
    )
    source_ordered_blockers = (
        "SourceOnlyBannerMissing",
        "MigrationApplyDenialMissing",
        "ForbiddenDestructiveOrMigrationStatement",
        "RequiredSchemaMissing",
        "GuardABlockMissing",
        "GuardBBlockMissing",
        "GuardCBlockMissing",
        "MigrationDryRunPlanMissing",
        "RequiredTableMissing",
        "RequiredTableColumnMissing",
        "RequiredNaturalKeyMissing",
        "RequiredForeignKeyMissing",
        "StockAssetLaneCheckMissing",
        "IbkrBrokerCheckMissing",
        "PaperEnvironmentCheckMissing",
        "LiveEnvironmentNotDenied",
        "SyntheticShadowCheckMissing",
        "RawArtifactHashRequirementMissing",
        "AuditAssetLaneEventsMissing",
        "ForwardOnlyAuditCommentMissing",
        "HypertableRetentionPlanMissing",
        "HotPathIndexMissing",
    )

    contract = _contract_validate_block(source)
    contract_positions = [
        contract.index(f"Blocker::{blocker}") for blocker in contract_ordered_blockers
    ]
    assert contract_positions == sorted(contract_positions)

    source_audit = _source_audit_block(source)
    source_positions = [
        source_audit.index(f"Blocker::{blocker}") for blocker in source_ordered_blockers
    ]
    assert source_positions == sorted(source_positions)


def test_stock_etf_db_evidence_ddl_source_has_no_runtime_secret_order_or_bybit_client_tokens() -> None:
    source = _source()
    violations = []

    for token in FORBIDDEN_RUNTIME_TOKENS + FORBIDDEN_SECRET_MATERIAL_TOKENS:
        if token in source:
            violations.append(f"{DB_EVIDENCE}: contains forbidden token {token!r}")

    assert violations == []
