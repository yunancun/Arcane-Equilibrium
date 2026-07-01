//! ADR-0048 Stock/ETF DB evidence DDL contract acceptance tests.
//!
//! These tests validate source-only evidence-schema artifacts. They do not
//! apply migrations, open Postgres, register sqlx migrations, contact IBKR,
//! create secrets, route orders, or start an evidence clock.

use std::path::PathBuf;

use openclaw_types::{
    audit_stock_etf_db_evidence_source_sql, StockEtfDbEvidenceDdlBlocker,
    StockEtfDbEvidenceDdlContractV1, StockEtfDbEvidenceDdlSourceBlocker,
    STOCK_ETF_DB_EVIDENCE_CONTRACT_ID, STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH,
};

#[test]
fn default_db_evidence_ddl_contract_blocks_migration_authority() {
    use StockEtfDbEvidenceDdlBlocker as Blocker;

    let verdict = StockEtfDbEvidenceDdlContractV1::default().validate();

    assert!(!verdict.accepted);
    assert_eq!(
        verdict.blockers,
        vec![
            Blocker::ContractIdMismatch,
            Blocker::SourceVersionMismatch,
            Blocker::SourceSqlHashInvalid,
            Blocker::SourceOnlyFlagMissing,
            Blocker::E2ReviewRequirementMissing,
            Blocker::E4ReviewRequirementMissing,
            Blocker::LinuxPgDryRunRequirementMissing,
            Blocker::PgDoubleApplyRequirementMissing,
            Blocker::GuardAExistingTableColumnsMissing,
            Blocker::GuardBTypeSensitiveAddColumnMissing,
            Blocker::GuardCHotPathIndexesMissing,
            Blocker::RequiredSchemaMissing,
            Blocker::RequiredTableMissing,
            Blocker::RequiredNaturalKeyMissing,
            Blocker::StockAssetLaneCheckMissing,
            Blocker::IbkrBrokerCheckMissing,
            Blocker::LiveEnvironmentNotDenied,
            Blocker::PaperShadowTableSeparationMissing,
            Blocker::SyntheticShadowCheckMissing,
            Blocker::RawArtifactHashRequirementMissing,
            Blocker::AuditAssetLaneEventsMissing,
            Blocker::ForwardOnlyEvidenceRetentionMissing,
            Blocker::DestructiveCleanupRollbackNotDenied,
        ]
    );
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
    assert_eq!(contract.contract_id, STOCK_ETF_DB_EVIDENCE_CONTRACT_ID);
    assert_eq!(contract.source_version, 1);
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
fn db_evidence_ddl_requires_exact_contract_id_and_source_version() {
    let mut contract = StockEtfDbEvidenceDdlContractV1::accepted_fixture();
    contract.contract_id = "stock_etf_db_evidence_ddl_v1_fixture".to_string();
    contract.source_version = 2;

    let blockers = contract.validate().blockers;

    assert_eq!(
        blockers,
        vec![
            StockEtfDbEvidenceDdlBlocker::ContractIdMismatch,
            StockEtfDbEvidenceDdlBlocker::SourceVersionMismatch,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfDbEvidenceDdlBlocker::RequiredSchemaMissing,
            StockEtfDbEvidenceDdlBlocker::RequiredTableMissing,
            StockEtfDbEvidenceDdlBlocker::RequiredNaturalKeyMissing,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfDbEvidenceDdlBlocker::MigrationFilePathPresent,
            StockEtfDbEvidenceDdlBlocker::CopiedToSqlMigrations,
            StockEtfDbEvidenceDdlBlocker::DbApplyPerformed,
            StockEtfDbEvidenceDdlBlocker::PgWritePerformed,
            StockEtfDbEvidenceDdlBlocker::SqlxMigrationRegistered,
            StockEtfDbEvidenceDdlBlocker::PmOperatorApplyAuthorizationClaimed,
            StockEtfDbEvidenceDdlBlocker::SecretContentSerialized,
        ]
    );
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

    assert_eq!(
        blockers,
        vec![
            StockEtfDbEvidenceDdlBlocker::E2ReviewRequirementMissing,
            StockEtfDbEvidenceDdlBlocker::E4ReviewRequirementMissing,
            StockEtfDbEvidenceDdlBlocker::LinuxPgDryRunRequirementMissing,
            StockEtfDbEvidenceDdlBlocker::PgDoubleApplyRequirementMissing,
            StockEtfDbEvidenceDdlBlocker::GuardAExistingTableColumnsMissing,
            StockEtfDbEvidenceDdlBlocker::GuardBTypeSensitiveAddColumnMissing,
            StockEtfDbEvidenceDdlBlocker::GuardCHotPathIndexesMissing,
            StockEtfDbEvidenceDdlBlocker::StockAssetLaneCheckMissing,
            StockEtfDbEvidenceDdlBlocker::IbkrBrokerCheckMissing,
            StockEtfDbEvidenceDdlBlocker::LiveEnvironmentNotDenied,
            StockEtfDbEvidenceDdlBlocker::PaperShadowTableSeparationMissing,
            StockEtfDbEvidenceDdlBlocker::SyntheticShadowCheckMissing,
            StockEtfDbEvidenceDdlBlocker::RawArtifactHashRequirementMissing,
            StockEtfDbEvidenceDdlBlocker::AuditAssetLaneEventsMissing,
            StockEtfDbEvidenceDdlBlocker::ForwardOnlyEvidenceRetentionMissing,
            StockEtfDbEvidenceDdlBlocker::DestructiveCleanupRollbackNotDenied,
        ]
    );
}

#[test]
fn source_sql_draft_remains_source_only_and_contains_contract_ddl() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let source_path = srv_root.join(STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH);
    let raw = std::fs::read_to_string(&source_path).expect("read source-only DDL draft");
    let audit = audit_stock_etf_db_evidence_source_sql(&raw);

    assert!(audit.accepted, "source SQL blockers: {:?}", audit.blockers);
    assert_eq!(audit.table_count, 13);
    assert!(audit.index_count >= 6);
    assert!(audit.foreign_key_count >= 7);
    assert!(!source_path.to_string_lossy().contains("sql/migrations"));
}

#[test]
fn source_sql_audit_rejects_contract_drift_and_migration_promotion() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let source_path = srv_root.join(STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH);
    let raw = std::fs::read_to_string(&source_path).expect("read source-only DDL draft");

    let missing_column = raw.replace("idempotency_key TEXT NOT NULL,\n", "");
    assert_ne!(missing_column, raw);
    let missing_column_audit = audit_stock_etf_db_evidence_source_sql(&missing_column);
    assert_eq!(
        missing_column_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::RequiredTableColumnMissing]
    );

    let missing_scorecard_lineage = raw.replace("cost_model_version TEXT NOT NULL,\n", "");
    assert_ne!(missing_scorecard_lineage, raw);
    let missing_scorecard_lineage_audit =
        audit_stock_etf_db_evidence_source_sql(&missing_scorecard_lineage);
    assert_eq!(
        missing_scorecard_lineage_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::RequiredTableColumnMissing]
    );

    let missing_foreign_key = raw.replace(
        "FOREIGN KEY (asset_lane, broker, environment, broker_order_id, execution_id)\n        REFERENCES broker.paper_fills (asset_lane, broker, environment, broker_order_id, execution_id)",
        "",
    );
    assert_ne!(missing_foreign_key, raw);
    let missing_foreign_key_audit = audit_stock_etf_db_evidence_source_sql(&missing_foreign_key);
    assert_eq!(
        missing_foreign_key_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::RequiredForeignKeyMissing]
    );

    let missing_shadow_check = raw.replace(
        "synthetic_shadow BOOLEAN NOT NULL DEFAULT TRUE CHECK (synthetic_shadow = TRUE)",
        "synthetic_shadow BOOLEAN NOT NULL DEFAULT TRUE",
    );
    assert_ne!(missing_shadow_check, raw);
    let missing_shadow_audit = audit_stock_etf_db_evidence_source_sql(&missing_shadow_check);
    assert_eq!(
        missing_shadow_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::SyntheticShadowCheckMissing]
    );

    let destructive = format!("{raw}\nDROP TABLE broker.paper_orders;\n");
    let destructive_audit = audit_stock_etf_db_evidence_source_sql(&destructive);
    assert_eq!(
        destructive_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::ForbiddenDestructiveOrMigrationStatement]
    );
}

#[test]
fn source_sql_audit_rejects_migration_guard_and_retention_plan_drift() {
    let srv_root = PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..");
    let source_path = srv_root.join(STOCK_ETF_DB_EVIDENCE_DDL_SOURCE_PATH);
    let raw = std::fs::read_to_string(&source_path).expect("read source-only DDL draft");

    let missing_dry_run_plan = raw.replace("Linux Postgres dry-run", "Linux Postgres review");
    assert_ne!(missing_dry_run_plan, raw);
    let missing_dry_run_plan_audit = audit_stock_etf_db_evidence_source_sql(&missing_dry_run_plan);
    assert_eq!(
        missing_dry_run_plan_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::MigrationDryRunPlanMissing]
    );

    let missing_guard_b = raw.replace("data_type INTO v_actual", "column_name INTO v_actual");
    assert_ne!(missing_guard_b, raw);
    let missing_guard_b_audit = audit_stock_etf_db_evidence_source_sql(&missing_guard_b);
    assert_eq!(
        missing_guard_b_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::GuardBBlockMissing]
    );

    let missing_guard_c = raw.replace("pg_get_indexdef", "pg_get_index_definition");
    assert_ne!(missing_guard_c, raw);
    let missing_guard_c_audit = audit_stock_etf_db_evidence_source_sql(&missing_guard_c);
    assert_eq!(
        missing_guard_c_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::GuardCBlockMissing]
    );

    let missing_retention_plan = raw.replace("create_hypertable", "create_time_table");
    assert_ne!(missing_retention_plan, raw);
    let missing_retention_plan_audit =
        audit_stock_etf_db_evidence_source_sql(&missing_retention_plan);
    assert_eq!(
        missing_retention_plan_audit.blockers,
        vec![StockEtfDbEvidenceDdlSourceBlocker::HypertableRetentionPlanMissing]
    );
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

    assert_eq!(parsed.contract_id, "");
    assert_eq!(parsed.source_version, 0);
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
