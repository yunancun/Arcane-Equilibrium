//! Stock/ETF DB evidence DDL contract for ADR-0048.
//!
//! This source-only validator defines the evidence-schema contract shape. It
//! does not apply migrations, open Postgres, register sqlx migrations, contact
//! IBKR, read secrets, or authorize paper/live execution.

use serde::{Deserialize, Serialize};

use crate::ibkr_phase2_artifact::is_sha256_hex;

pub const STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH: &str =
    "docs/execution_plan/specs/2026-06-29--stock_etf_db_evidence_ddl_v1.source_only.sql";

pub const STOCK_ETF_DB_EVIDENCE_CONTRACT_ID: &str = "stock_etf_db_evidence_ddl_v1";

const REQUIRED_SCHEMAS: &[&str] = &["broker", "research", "audit"];

const REQUIRED_TABLES: &[&str] = &[
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
];

const REQUIRED_NATURAL_KEYS: &[&str] = &[
    "instrument:asset_lane,broker,symbol,listing_venue,currency,primary_exchange",
    "order:asset_lane,broker,environment,account_fingerprint,local_order_id",
    "fill:asset_lane,broker,environment,broker_order_id,execution_id",
    "scorecard:asset_lane,strategy_id,universe_version,benchmark_version,as_of_date",
];

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfDbEvidenceDdlContractV1 {
    pub contract_id: String,
    pub source_sql_path: String,
    pub source_sql_sha256: String,
    pub source_only: bool,
    pub migration_file_path: String,
    pub copied_to_sql_migrations: bool,
    pub db_apply_performed: bool,
    pub pg_write_performed: bool,
    pub sqlx_migration_registered: bool,
    pub pm_operator_apply_authorized: bool,
    pub e2_review_required: bool,
    pub e4_review_required: bool,
    pub linux_pg_dry_run_required: bool,
    pub pg_double_apply_required: bool,
    pub guard_a_existing_table_columns: bool,
    pub guard_b_type_sensitive_add_column: bool,
    pub guard_c_hot_path_indexes: bool,
    pub required_schemas: Vec<String>,
    pub required_tables: Vec<String>,
    pub required_natural_keys: Vec<String>,
    pub stock_tables_asset_lane_check: bool,
    pub ibkr_facts_broker_check: bool,
    pub live_environment_denied: bool,
    pub paper_shadow_separate_tables: bool,
    pub synthetic_shadow_check: bool,
    pub raw_artifact_hash_required: bool,
    pub audit_asset_lane_events_present: bool,
    pub forward_only_evidence_retention: bool,
    pub destructive_cleanup_as_rollback_denied: bool,
    pub secret_content_serialized: bool,
}

impl Default for StockEtfDbEvidenceDdlContractV1 {
    fn default() -> Self {
        Self {
            contract_id: String::new(),
            source_sql_path: STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH.to_string(),
            source_sql_sha256: String::new(),
            source_only: false,
            migration_file_path: String::new(),
            copied_to_sql_migrations: false,
            db_apply_performed: false,
            pg_write_performed: false,
            sqlx_migration_registered: false,
            pm_operator_apply_authorized: false,
            e2_review_required: false,
            e4_review_required: false,
            linux_pg_dry_run_required: false,
            pg_double_apply_required: false,
            guard_a_existing_table_columns: false,
            guard_b_type_sensitive_add_column: false,
            guard_c_hot_path_indexes: false,
            required_schemas: Vec::new(),
            required_tables: Vec::new(),
            required_natural_keys: Vec::new(),
            stock_tables_asset_lane_check: false,
            ibkr_facts_broker_check: false,
            live_environment_denied: false,
            paper_shadow_separate_tables: false,
            synthetic_shadow_check: false,
            raw_artifact_hash_required: false,
            audit_asset_lane_events_present: false,
            forward_only_evidence_retention: false,
            destructive_cleanup_as_rollback_denied: false,
            secret_content_serialized: false,
        }
    }
}

impl StockEtfDbEvidenceDdlContractV1 {
    pub fn accepted_fixture() -> Self {
        Self {
            contract_id: STOCK_ETF_DB_EVIDENCE_CONTRACT_ID.to_string(),
            source_sql_path: STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH.to_string(),
            source_sql_sha256: "1".repeat(64),
            source_only: true,
            migration_file_path: String::new(),
            copied_to_sql_migrations: false,
            db_apply_performed: false,
            pg_write_performed: false,
            sqlx_migration_registered: false,
            pm_operator_apply_authorized: false,
            e2_review_required: true,
            e4_review_required: true,
            linux_pg_dry_run_required: true,
            pg_double_apply_required: true,
            guard_a_existing_table_columns: true,
            guard_b_type_sensitive_add_column: true,
            guard_c_hot_path_indexes: true,
            required_schemas: REQUIRED_SCHEMAS
                .iter()
                .map(|schema| schema.to_string())
                .collect(),
            required_tables: REQUIRED_TABLES
                .iter()
                .map(|table| table.to_string())
                .collect(),
            required_natural_keys: REQUIRED_NATURAL_KEYS
                .iter()
                .map(|key| key.to_string())
                .collect(),
            stock_tables_asset_lane_check: true,
            ibkr_facts_broker_check: true,
            live_environment_denied: true,
            paper_shadow_separate_tables: true,
            synthetic_shadow_check: true,
            raw_artifact_hash_required: true,
            audit_asset_lane_events_present: true,
            forward_only_evidence_retention: true,
            destructive_cleanup_as_rollback_denied: true,
            secret_content_serialized: false,
        }
    }

    pub fn validate(&self) -> StockEtfDbEvidenceDdlVerdict<StockEtfDbEvidenceDdlBlocker> {
        use StockEtfDbEvidenceDdlBlocker as Blocker;
        let mut blockers = Vec::new();

        if self.contract_id != STOCK_ETF_DB_EVIDENCE_CONTRACT_ID {
            blockers.push(Blocker::ContractIdMismatch);
        }
        if self.source_sql_path != STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH {
            blockers.push(Blocker::SourceSqlPathMismatch);
        }
        if !is_sha256_hex(&self.source_sql_sha256) {
            blockers.push(Blocker::SourceSqlHashInvalid);
        }
        if !self.source_only {
            blockers.push(Blocker::SourceOnlyFlagMissing);
        }
        if !self.migration_file_path.trim().is_empty() {
            blockers.push(Blocker::MigrationFilePathPresent);
        }
        if self.copied_to_sql_migrations {
            blockers.push(Blocker::CopiedToSqlMigrations);
        }
        if self.db_apply_performed {
            blockers.push(Blocker::DbApplyPerformed);
        }
        if self.pg_write_performed {
            blockers.push(Blocker::PgWritePerformed);
        }
        if self.sqlx_migration_registered {
            blockers.push(Blocker::SqlxMigrationRegistered);
        }
        if self.pm_operator_apply_authorized {
            blockers.push(Blocker::PmOperatorApplyAuthorizationClaimed);
        }
        if !self.e2_review_required {
            blockers.push(Blocker::E2ReviewRequirementMissing);
        }
        if !self.e4_review_required {
            blockers.push(Blocker::E4ReviewRequirementMissing);
        }
        if !self.linux_pg_dry_run_required {
            blockers.push(Blocker::LinuxPgDryRunRequirementMissing);
        }
        if !self.pg_double_apply_required {
            blockers.push(Blocker::PgDoubleApplyRequirementMissing);
        }
        if !self.guard_a_existing_table_columns {
            blockers.push(Blocker::GuardAExistingTableColumnsMissing);
        }
        if !self.guard_b_type_sensitive_add_column {
            blockers.push(Blocker::GuardBTypeSensitiveAddColumnMissing);
        }
        if !self.guard_c_hot_path_indexes {
            blockers.push(Blocker::GuardCHotPathIndexesMissing);
        }
        if !contains_all(&self.required_schemas, REQUIRED_SCHEMAS) {
            blockers.push(Blocker::RequiredSchemaMissing);
        }
        if !contains_all(&self.required_tables, REQUIRED_TABLES) {
            blockers.push(Blocker::RequiredTableMissing);
        }
        if !contains_all(&self.required_natural_keys, REQUIRED_NATURAL_KEYS) {
            blockers.push(Blocker::RequiredNaturalKeyMissing);
        }
        if !self.stock_tables_asset_lane_check {
            blockers.push(Blocker::StockAssetLaneCheckMissing);
        }
        if !self.ibkr_facts_broker_check {
            blockers.push(Blocker::IbkrBrokerCheckMissing);
        }
        if !self.live_environment_denied {
            blockers.push(Blocker::LiveEnvironmentNotDenied);
        }
        if !self.paper_shadow_separate_tables {
            blockers.push(Blocker::PaperShadowTableSeparationMissing);
        }
        if !self.synthetic_shadow_check {
            blockers.push(Blocker::SyntheticShadowCheckMissing);
        }
        if !self.raw_artifact_hash_required {
            blockers.push(Blocker::RawArtifactHashRequirementMissing);
        }
        if !self.audit_asset_lane_events_present {
            blockers.push(Blocker::AuditAssetLaneEventsMissing);
        }
        if !self.forward_only_evidence_retention {
            blockers.push(Blocker::ForwardOnlyEvidenceRetentionMissing);
        }
        if !self.destructive_cleanup_as_rollback_denied {
            blockers.push(Blocker::DestructiveCleanupRollbackNotDenied);
        }
        if self.secret_content_serialized {
            blockers.push(Blocker::SecretContentSerialized);
        }

        StockEtfDbEvidenceDdlVerdict::new(blockers)
    }
}

fn contains_all(actual: &[String], required: &[&str]) -> bool {
    required
        .iter()
        .all(|expected| actual.iter().any(|item| item == expected))
}

#[derive(Debug, Clone, PartialEq, Eq, Serialize, Deserialize)]
pub struct StockEtfDbEvidenceDdlVerdict<B> {
    pub accepted: bool,
    pub blockers: Vec<B>,
}

impl<B> StockEtfDbEvidenceDdlVerdict<B> {
    fn new(blockers: Vec<B>) -> Self {
        Self {
            accepted: blockers.is_empty(),
            blockers,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum StockEtfDbEvidenceDdlBlocker {
    ContractIdMismatch,
    SourceSqlPathMismatch,
    SourceSqlHashInvalid,
    SourceOnlyFlagMissing,
    MigrationFilePathPresent,
    CopiedToSqlMigrations,
    DbApplyPerformed,
    PgWritePerformed,
    SqlxMigrationRegistered,
    PmOperatorApplyAuthorizationClaimed,
    E2ReviewRequirementMissing,
    E4ReviewRequirementMissing,
    LinuxPgDryRunRequirementMissing,
    PgDoubleApplyRequirementMissing,
    GuardAExistingTableColumnsMissing,
    GuardBTypeSensitiveAddColumnMissing,
    GuardCHotPathIndexesMissing,
    RequiredSchemaMissing,
    RequiredTableMissing,
    RequiredNaturalKeyMissing,
    StockAssetLaneCheckMissing,
    IbkrBrokerCheckMissing,
    LiveEnvironmentNotDenied,
    PaperShadowTableSeparationMissing,
    SyntheticShadowCheckMissing,
    RawArtifactHashRequirementMissing,
    AuditAssetLaneEventsMissing,
    ForwardOnlyEvidenceRetentionMissing,
    DestructiveCleanupRollbackNotDenied,
    SecretContentSerialized,
}
