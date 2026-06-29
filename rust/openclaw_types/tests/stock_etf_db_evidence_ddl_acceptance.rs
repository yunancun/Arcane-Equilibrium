//! ADR-0048 Stock/ETF DB evidence DDL contract acceptance tests.
//!
//! These tests validate source-only evidence-schema artifacts. They do not
//! apply migrations, open Postgres, register sqlx migrations, contact IBKR,
//! create secrets, route orders, or start an evidence clock.

use std::path::PathBuf;

use openclaw_types::{
    StockEtfDbEvidenceDdlBlocker, StockEtfDbEvidenceDdlContractV1,
    STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH,
};

#[test]
fn default_db_evidence_ddl_contract_blocks_migration_authority() {
    let verdict = StockEtfDbEvidenceDdlContractV1::default().validate();

    assert!(!verdict.accepted);
    assert!(has(
        &verdict.blockers,
        StockEtfDbEvidenceDdlBlocker::ContractIdMismatch
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDbEvidenceDdlBlocker::SourceSqlHashInvalid
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDbEvidenceDdlBlocker::SourceOnlyFlagMissing
    ));
    assert!(has(
        &verdict.blockers,
        StockEtfDbEvidenceDdlBlocker::RequiredTableMissing
    ));
}

#[test]
fn accepted_fixture_is_source_only_and_has_expected_schema_surface() {
    let contract = StockEtfDbEvidenceDdlContractV1::accepted_fixture();
    let verdict = contract.validate();

    assert!(
        verdict.accepted,
        "unexpected blockers: {:?}",
        verdict.blockers
    );
    assert_eq!(
        contract.source_sql_path,
        STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH
    );
    assert!(contract.source_only);
    assert!(!contract.copied_to_sql_migrations);
    assert!(!contract.db_apply_performed);
    assert!(!contract.pg_write_performed);
    assert!(!contract.sqlx_migration_registered);
    assert!(!contract.pm_operator_apply_authorized);
    assert!(contract.required_schemas.contains(&"broker".to_string()));
    assert!(contract.required_schemas.contains(&"research".to_string()));
    assert!(contract.required_schemas.contains(&"audit".to_string()));
    assert_eq!(contract.required_tables.len(), 13);
    assert!(contract
        .required_tables
        .contains(&"broker.paper_orders".to_string()));
    assert!(contract
        .required_tables
        .contains(&"research.stock_shadow_fills".to_string()));
    assert!(contract
        .required_tables
        .contains(&"audit.asset_lane_events".to_string()));
}

#[test]
fn required_lists_must_include_schemas_tables_and_natural_keys() {
    let mut contract = StockEtfDbEvidenceDdlContractV1::accepted_fixture();
    contract.required_schemas.retain(|schema| schema != "audit");
    contract
        .required_tables
        .retain(|table| table != "broker.paper_fills");
    contract
        .required_natural_keys
        .retain(|key| !key.starts_with("fill:"));

    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::RequiredSchemaMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::RequiredTableMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::RequiredNaturalKeyMissing
    ));
}

#[test]
fn migration_apply_or_runtime_claims_are_rejected() {
    let mut contract = StockEtfDbEvidenceDdlContractV1::accepted_fixture();
    contract.migration_file_path = "sql/migrations/V999__stock_etf.sql".to_string();
    contract.copied_to_sql_migrations = true;
    contract.db_apply_performed = true;
    contract.pg_write_performed = true;
    contract.sqlx_migration_registered = true;
    contract.pm_operator_apply_authorized = true;
    contract.secret_content_serialized = true;

    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::MigrationFilePathPresent
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::CopiedToSqlMigrations
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::DbApplyPerformed
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::PgWritePerformed
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::SqlxMigrationRegistered
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::PmOperatorApplyAuthorizationClaimed
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::SecretContentSerialized
    ));
}

#[test]
fn guard_and_constraint_controls_are_required() {
    let mut contract = StockEtfDbEvidenceDdlContractV1::accepted_fixture();
    contract.e2_review_required = false;
    contract.e4_review_required = false;
    contract.linux_pg_dry_run_required = false;
    contract.pg_double_apply_required = false;
    contract.guard_a_existing_table_columns = false;
    contract.guard_b_type_sensitive_add_column = false;
    contract.guard_c_hot_path_indexes = false;
    contract.stock_tables_asset_lane_check = false;
    contract.ibkr_facts_broker_check = false;
    contract.live_environment_denied = false;
    contract.paper_shadow_separate_tables = false;
    contract.synthetic_shadow_check = false;
    contract.raw_artifact_hash_required = false;
    contract.audit_asset_lane_events_present = false;
    contract.forward_only_evidence_retention = false;
    contract.destructive_cleanup_as_rollback_denied = false;

    let blockers = contract.validate().blockers;

    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::E2ReviewRequirementMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::E4ReviewRequirementMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::LinuxPgDryRunRequirementMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::PgDoubleApplyRequirementMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::GuardAExistingTableColumnsMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::GuardBTypeSensitiveAddColumnMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::GuardCHotPathIndexesMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::LiveEnvironmentNotDenied
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::PaperShadowTableSeparationMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::SyntheticShadowCheckMissing
    ));
    assert!(has(
        &blockers,
        StockEtfDbEvidenceDdlBlocker::DestructiveCleanupRollbackNotDenied
    ));
}

#[test]
fn source_sql_draft_remains_source_only_and_contains_contract_ddl() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let source_path = srv_root.join(STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH);
    let raw = std::fs::read_to_string(&source_path).expect("read source-only DDL draft");

    assert!(!source_path.to_string_lossy().contains("sql/migrations"));
    assert!(raw.contains("SOURCE-ONLY DDL DRAFT"));
    assert!(raw.contains("CREATE SCHEMA IF NOT EXISTS broker;"));
    assert!(raw.contains("CREATE SCHEMA IF NOT EXISTS research;"));
    assert!(raw.contains("CREATE SCHEMA IF NOT EXISTS audit;"));
    assert!(raw.contains("Guard A"));
    assert!(raw.contains("CREATE TABLE IF NOT EXISTS broker.paper_orders"));
    assert!(raw.contains("environment TEXT NOT NULL DEFAULT 'paper' CHECK (environment = 'paper')"));
    assert!(raw.contains("CREATE TABLE IF NOT EXISTS research.stock_shadow_fills"));
    assert!(raw.contains(
        "synthetic_shadow BOOLEAN NOT NULL DEFAULT TRUE CHECK (synthetic_shadow = TRUE)"
    ));
    assert!(raw.contains("CREATE TABLE IF NOT EXISTS audit.asset_lane_events"));
    assert!(raw.contains("CREATE INDEX IF NOT EXISTS idx_asset_lane_events_lane_time"));
    assert!(raw.contains("Do not copy into sql/migrations/ or apply to any database"));
}

#[test]
fn blocked_template_is_parseable_and_secret_free() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let raw = std::fs::read_to_string(
        srv_root.join("settings/broker/stock_etf_db_evidence_ddl.template.toml"),
    )
    .expect("read DB evidence DDL template");
    let parsed: StockEtfDbEvidenceDdlContractV1 =
        toml::from_str(&raw).expect("DB evidence DDL template parses");

    assert_eq!(
        parsed.source_sql_path,
        STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH
    );
    assert!(!parsed.source_only);
    assert!(!parsed.db_apply_performed);
    assert!(!parsed.pg_write_performed);
    assert!(!parsed.sqlx_migration_registered);
    assert!(!parsed.pm_operator_apply_authorized);
    assert!(!parsed.validate().accepted);

    let lower = raw.to_ascii_lowercase();
    assert!(!lower.contains("api_key ="));
    assert!(!lower.contains("api_secret ="));
    assert!(!lower.contains("account_id ="));
    assert!(!lower.contains("password ="));
    assert!(!lower.contains("token ="));
}

fn has(blockers: &[StockEtfDbEvidenceDdlBlocker], blocker: StockEtfDbEvidenceDdlBlocker) -> bool {
    blockers.contains(&blocker)
}
