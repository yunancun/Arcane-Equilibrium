//! Schema-consumer contract test — runtime-checked sqlx 的 column drift 兜底。
//! Schema-consumer contract test.
//!
//! MODULE_NOTE (中):
//!   為什麼需要這個檔：engine 的 99 個 sqlx call site 全是 runtime-checked
//!   `sqlx::query()`（無編譯期 `query!` 巨集、無 `.sqlx` cache），所以 migration
//!   把熱表 column rename / drop 後，Rust 編譯 + Python 全部隱形，首次撞見=runtime
//!   first-touch；而 quality_writer 類 writer 的 INSERT 失敗只 `warn!` 靜默丟（不
//!   panic、不 alert）=最難偵測的 silent-noop。本檔對代表性熱表直接執行「與真實
//!   writer/consumer 同形」的 query（不只斷言 column 存在，同時驗 type / nullable /
//!   ON CONFLICT 鍵），column drift 立刻 fail。
//!
//!   流程：先種 V005 brownfield 前置（見 seed_legacy_precondition——V005 PART 4 對 5 個
//!   `public.X_legacy` 有 brownfield-only 假設，virgin ephemeral PG 缺那段歷史會在 ordinal 5
//!   hard-fail），再以 seed_v158_role_preconditions 建立 V158/V159 測試專用前置，最後用
//!   既有 public API `MigrationRunner::run_if_enabled` 對 ephemeral PG
//!   跑真 migration 全樹（`OPENCLAW_AUTO_MIGRATE=1`），最後逐表開 transaction、
//!   INSERT/SELECT 後 ROLLBACK（不留 row）。沿用 migrations_test.rs 的 maybe_pool() /
//!   srv_root() 模式與 `OPENCLAW_TEST_PG` env gate：未設則 SKIP（本機 `cargo test`
//!   仍綠）；一旦設定 DSN，還必須明確設定
//!   `OPENCLAW_TEST_PG_DESTRUCTIVE=1`，因為 V158/V159 前置角色是 cluster-global DDL。
//!
//!   V004/V005/V023 曾有的 virgin-tree `learning.model_registry` 衝突已在 migration
//!   本體修復：V004 legacy shape 含 V005 所需的 `is_active`，V023 只會移除空的 legacy
//!   stub 再建立新 shape，非空 drift 仍 fail closed。因此本 fixture 不預種
//!   `model_registry`，讓完整 migration tree 自己驗證該 forward-compat 路徑。
//!
//!   邊界：**切勿**指向帶真實資料的 DB 或共用 cluster——測試會跑
//!   migration 全樹建 schema，並建立八個 cluster-global fixture roles（V158 writer、
//!   trainer caller、V159 attestor、attestor caller、V160 coordinator、caller、
//!   trading_ai、alr_shadow）；表探針雖在隔離 transaction 內 INSERT 後
//!   ROLLBACK，仍不可指向 prod。trading_ai/alr_shadow 存在，因此全樹中的對應
//!   role-conditional GRANT/REVOKE 分支會執行；V158/V159 的實際 ACL/denial 負向行為另由
//!   respective explicit disposable Python probes 驗證。

use openclaw_engine::database::migrations::{
    build_migrator, load_migrations_from_dir, MigrationRunner, RunOutcome, AUTO_MIGRATE_ENV_VAR,
};
use sqlx::postgres::PgPool;
use sqlx::Connection;
use std::path::PathBuf;

/// 解析測試二進位對應的 `srv` repo root（與 migrations_test.rs 同形）。
/// Resolve the `srv` repo root for the running test binary.
fn srv_root() -> PathBuf {
    // CARGO_MANIFEST_DIR 指到 `srv/rust/openclaw_engine`，向上兩層為 `srv/`；
    // 編譯期解析，與 CI cwd 無關。OPENCLAW_BASE_DIR 若設則優先。
    if let Ok(env) = std::env::var("OPENCLAW_BASE_DIR") {
        return PathBuf::from(env);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

const DESTRUCTIVE_ACK_ENV_VAR: &str = "OPENCLAW_TEST_PG_DESTRUCTIVE";
const V159_BASELINE_ACK_ENV_VAR: &str = "OPENCLAW_V159_PROBE_BASELINE";
const V160_BASELINE_ACK_ENV_VAR: &str = "OPENCLAW_V160_PROBE_BASELINE";
const V159_BASELINE_VERSION: i64 = 157;
const V160_BASELINE_VERSION: i64 = 157;

/// 用 OPENCLAW_TEST_PG 建 pool；只有未設才回 None 由呼叫端 SKIP。
/// Build a Postgres pool from OPENCLAW_TEST_PG. Only an absent variable skips.
/// A configured but invalid/unreachable target is a hard failure, and the
/// cluster-global V158/V159 role fixture requires an exact destructive-test ack.
async fn maybe_pool() -> Option<PgPool> {
    let url = match std::env::var("OPENCLAW_TEST_PG") {
        Ok(url) => url,
        Err(std::env::VarError::NotPresent) => return None,
        Err(std::env::VarError::NotUnicode(_)) => {
            panic!("OPENCLAW_TEST_PG is set but is not valid Unicode")
        }
    };
    assert_eq!(
        std::env::var(DESTRUCTIVE_ACK_ENV_VAR).as_deref(),
        Ok("1"),
        "OPENCLAW_TEST_PG is set; refuse schema and cluster-global role mutation without \
         {DESTRUCTIVE_ACK_ENV_VAR}=1 for a disposable PostgreSQL cluster"
    );

    Some(
        sqlx::postgres::PgPoolOptions::new()
            .max_connections(2)
            .acquire_timeout(std::time::Duration::from_secs(5))
            .connect(&url)
            .await
            .unwrap_or_else(|e| {
                panic!("[schema_contract_test] OPENCLAW_TEST_PG set but connect failed: {e}")
            }),
    )
}

/// 在跑 migration 前種下 V005 brownfield-only 的 legacy 前置表。
/// Seed the brownfield-only legacy precondition tables V005 assumes.
///
/// 為什麼必須 seed：V005 PART 4 有 5 個 **無條件** `CREATE OR REPLACE VIEW
/// public.X AS SELECT ... FROM public.X_legacy`（account_snapshots / system_health /
/// paper_pnl_snapshots / risk_events / learning_events）；但對應的 `X_legacy` 只在
/// PART 3 以 `IF EXISTS public.X THEN RENAME` 條件式產生。production 走過 V005 是因為
/// 手跑的 init_trading_schema.sql 早就建了 public.X 基表，RENAME 才有東西可改名；
/// 全新 ephemeral PG 沒有那段歷史 → PART 3 跳過 → X_legacy 不存在 → PART 4 的 VIEW
/// 在 migration ordinal 5 hard-fail（完整 migration tree 掛在這裡，6 個契約 probe 一個都跑不到）。
///
/// 修法=在 migration 前直接建好 5 個 `public.X_legacy` 最小 stub（欄位精確鏡像 PART 4
/// VIEW 所 SELECT 的欄位），讓 ephemeral PG 進入與 production 相同的「V005 brownfield
/// 前置已滿足」狀態。PART 3 的 `IF EXISTS public.X` 仍為 false（無基表）故是乾淨 no-op；
/// PART 4 的 VIEW 找得到 `X_legacy` → 全樹綠。這 5 個 stub 不被任何 V006-V139 migration
/// drop 或引用（grep 自證），故穿過全樹仍在。其餘 6 個 legacy 表（V126 DROP 的那批）走
/// `to_regclass(...) IS NULL → RETURN` 守衛，virgin DB 上本就安全，無需 seed。
async fn seed_legacy_precondition(pool: &PgPool) {
    // 欄位集合精確對齊 V005:410-551 各 VIEW 的 SELECT 投影；類型取寬鬆相容型別，
    // VIEW 對這 5 表不做 cast，故 stub 只需欄位名/可選取性正確即可（空表，無資料語意）。
    const LEGACY_STUBS: &[&str] = &[
        "CREATE TABLE IF NOT EXISTS public.account_snapshots_legacy ( \
            id BIGINT, ts TIMESTAMPTZ, total_equity NUMERIC, available_balance NUMERIC, \
            used_margin NUMERIC, unrealized_pnl NUMERIC, account_type TEXT, coin TEXT, raw_json JSONB)",
        "CREATE TABLE IF NOT EXISTS public.system_health_legacy ( \
            id BIGINT, ts TIMESTAMPTZ, component TEXT, status TEXT, latency_ms NUMERIC, \
            detail TEXT, metrics JSONB)",
        "CREATE TABLE IF NOT EXISTS public.paper_pnl_snapshots_legacy ( \
            id BIGINT, ts TIMESTAMPTZ, session_id TEXT, realized_pnl NUMERIC, \
            unrealized_pnl NUMERIC, total_fees NUMERIC, ai_cost NUMERIC, net_pnl NUMERIC, \
            open_positions INTEGER, total_trades INTEGER, win_rate NUMERIC, sharpe_ratio NUMERIC)",
        "CREATE TABLE IF NOT EXISTS public.risk_events_legacy ( \
            id BIGINT, ts TIMESTAMPTZ, event_type TEXT, symbol TEXT, severity TEXT, \
            layer TEXT, detail TEXT, metrics JSONB)",
        "CREATE TABLE IF NOT EXISTS public.learning_events_legacy ( \
            id BIGINT, ts TIMESTAMPTZ, event_type TEXT, title TEXT, detail TEXT, \
            status TEXT, confidence NUMERIC, tags JSONB, metadata JSONB)",
    ];
    for ddl in LEGACY_STUBS {
        sqlx::query(ddl)
            .execute(pool)
            .await
            .expect("seed legacy precondition stub (V005 brownfield 前置)");
    }
}

/// Seed the exact role prerequisites required by V158/V159/V160 in this disposable
/// schema-contract cluster. The migrations deliberately cannot create or
/// normalize their writer/caller roles; the two generic application fixtures
/// are also present before apply so explicit generic revocation paths are
/// exercised rather than silently skipped.
async fn seed_v158_role_preconditions(pool: &PgPool) {
    let mut conn = pool
        .acquire()
        .await
        .expect("acquire V158 role-precondition connection");
    let mut tx = conn
        .begin()
        .await
        .expect("begin V158 role-precondition transaction");

    // Role DDL is cluster-global. Before any CREATE ROLE, require PostgreSQL
    // 16 and a direct, un-switched superuser session that owns the explicitly
    // acknowledged disposable database. The query intentionally returns only
    // identities/catalog state and never exposes the configured DSN.
    let (
        server_version_num,
        session_identity,
        effective_identity,
        can_login,
        is_superuser,
        database_owner,
    ): (i32, String, String, bool, bool, String) = sqlx::query_as(
        "SELECT \
             pg_catalog.current_setting('server_version_num')::pg_catalog.int4, \
             SESSION_USER::pg_catalog.text, \
             CURRENT_USER::pg_catalog.text, \
             current_role_row.rolcanlogin, \
             current_role_row.rolsuper, \
             pg_catalog.pg_get_userbyid(current_database_row.datdba)::pg_catalog.text \
         FROM pg_catalog.pg_roles AS current_role_row \
         JOIN pg_catalog.pg_database AS current_database_row \
           ON current_database_row.datname = pg_catalog.current_database() \
         WHERE current_role_row.rolname = CURRENT_USER",
    )
    .fetch_one(&mut *tx)
    .await
    .expect("read PostgreSQL V158 role-fixture preflight identity");
    assert!(
        (160_000..170_000).contains(&server_version_num),
        "V158 role fixture requires PostgreSQL 16, got server_version_num={server_version_num}"
    );
    assert_eq!(
        effective_identity, session_identity,
        "V158 role fixture refuses SET ROLE/SET SESSION AUTHORIZATION identity drift"
    );
    assert!(
        can_login,
        "V158 role fixture requires a direct login identity, not a NOLOGIN role"
    );
    assert!(
        is_superuser,
        "V158 role fixture requires a direct superuser-authenticated disposable session"
    );
    assert_eq!(
        database_owner, session_identity,
        "V158 role fixture requires the direct session identity to own the disposable database"
    );

    sqlx::query(
        "DO $v158_roles$ \
         BEGIN \
             IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles \
                            WHERE rolname = 'alr_challenger_writer') THEN \
                 CREATE ROLE alr_challenger_writer NOLOGIN NOSUPERUSER NOCREATEDB \
                     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; \
             END IF; \
             IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles \
                            WHERE rolname = 'alr_challenger_trainer_caller') THEN \
                 CREATE ROLE alr_challenger_trainer_caller LOGIN NOSUPERUSER NOCREATEDB \
                     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1; \
             END IF; \
             IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles \
                            WHERE rolname = 'alr_challenger_fit_attestor') THEN \
                 CREATE ROLE alr_challenger_fit_attestor NOLOGIN NOSUPERUSER NOCREATEDB \
                     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; \
             END IF; \
             IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles \
                            WHERE rolname = 'alr_challenger_fit_attestor_caller') THEN \
                 CREATE ROLE alr_challenger_fit_attestor_caller LOGIN NOSUPERUSER NOCREATEDB \
                     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1; \
             END IF; \
             IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles \
                            WHERE rolname = 'alr_challenger_consumption_coordinator') THEN \
                 CREATE ROLE alr_challenger_consumption_coordinator NOLOGIN NOSUPERUSER NOCREATEDB \
                     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; \
             END IF; \
             IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles \
                            WHERE rolname = 'alr_challenger_consumption_caller') THEN \
                 CREATE ROLE alr_challenger_consumption_caller LOGIN NOSUPERUSER NOCREATEDB \
                     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS CONNECTION LIMIT 1; \
             END IF; \
             IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles \
                            WHERE rolname = 'trading_ai') THEN \
                 CREATE ROLE trading_ai NOLOGIN NOSUPERUSER NOCREATEDB \
                     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; \
             END IF; \
             IF NOT EXISTS (SELECT 1 FROM pg_catalog.pg_roles \
                            WHERE rolname = 'alr_shadow') THEN \
                 CREATE ROLE alr_shadow NOLOGIN NOSUPERUSER NOCREATEDB \
                     NOCREATEROLE NOINHERIT NOREPLICATION NOBYPASSRLS; \
             END IF; \
         END \
         $v158_roles$",
    )
    .execute(&mut *tx)
    .await
    .expect("seed exact V158 role prerequisites");

    let posture_is_exact: bool = sqlx::query_scalar(
        "SELECT \
             EXISTS ( \
                 SELECT 1 FROM pg_catalog.pg_roles \
                 WHERE rolname = 'alr_challenger_writer' \
                   AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb \
                   AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication \
                   AND NOT rolbypassrls AND rolconnlimit = -1 \
             ) \
             AND EXISTS ( \
                 SELECT 1 FROM pg_catalog.pg_roles \
                 WHERE rolname = 'alr_challenger_trainer_caller' \
                   AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb \
                   AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication \
                   AND NOT rolbypassrls AND rolconnlimit = 1 \
             ) \
             AND EXISTS ( \
                 SELECT 1 FROM pg_catalog.pg_roles \
                 WHERE rolname = 'alr_challenger_fit_attestor' \
                   AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb \
                   AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication \
                   AND NOT rolbypassrls AND rolconnlimit = -1 \
             ) \
             AND EXISTS ( \
                 SELECT 1 FROM pg_catalog.pg_roles \
                 WHERE rolname = 'alr_challenger_fit_attestor_caller' \
                   AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb \
                   AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication \
                   AND NOT rolbypassrls AND rolconnlimit = 1 \
             ) \
             AND EXISTS ( \
                 SELECT 1 FROM pg_catalog.pg_roles \
                 WHERE rolname = 'alr_challenger_consumption_coordinator' \
                   AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb \
                   AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication \
                   AND NOT rolbypassrls AND rolconnlimit = -1 \
             ) \
             AND EXISTS ( \
                 SELECT 1 FROM pg_catalog.pg_roles \
                 WHERE rolname = 'alr_challenger_consumption_caller' \
                   AND rolcanlogin AND NOT rolsuper AND NOT rolcreatedb \
                   AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication \
                   AND NOT rolbypassrls AND rolconnlimit = 1 \
             ) \
             AND ( \
                 SELECT pg_catalog.count(*) = 2 \
                 FROM pg_catalog.pg_roles \
                 WHERE rolname IN ('trading_ai', 'alr_shadow') \
                   AND NOT rolcanlogin AND NOT rolsuper AND NOT rolcreatedb \
                   AND NOT rolcreaterole AND NOT rolinherit AND NOT rolreplication \
                   AND NOT rolbypassrls AND rolconnlimit = -1 \
             ) \
             AND NOT EXISTS ( \
                 SELECT 1 \
                 FROM pg_catalog.pg_auth_members AS membership \
                 WHERE membership.roleid IN ( \
                     SELECT oid FROM pg_catalog.pg_roles \
                     WHERE rolname IN ( \
                         'alr_challenger_writer', \
                         'alr_challenger_trainer_caller', \
                         'alr_challenger_fit_attestor', \
                         'alr_challenger_fit_attestor_caller', \
                         'alr_challenger_consumption_coordinator', \
                         'alr_challenger_consumption_caller', \
                         'trading_ai', \
                         'alr_shadow' \
                     ) \
                 ) \
                    OR membership.member IN ( \
                     SELECT oid FROM pg_catalog.pg_roles \
                     WHERE rolname IN ( \
                         'alr_challenger_writer', \
                         'alr_challenger_trainer_caller', \
                         'alr_challenger_fit_attestor', \
                         'alr_challenger_fit_attestor_caller', \
                         'alr_challenger_consumption_coordinator', \
                         'alr_challenger_consumption_caller', \
                         'trading_ai', \
                         'alr_shadow' \
                     ) \
                 ) \
             ) \
             AND NOT pg_catalog.has_parameter_privilege( \
                 'alr_challenger_writer', 'session_replication_role', 'SET' \
             ) \
             AND NOT pg_catalog.has_parameter_privilege( \
                 'alr_challenger_trainer_caller', 'session_replication_role', 'SET' \
             ) \
             AND NOT EXISTS ( \
                 SELECT 1 FROM pg_catalog.unnest(ARRAY[ \
                     'alr_challenger_fit_attestor', \
                     'alr_challenger_fit_attestor_caller', \
                     'alr_challenger_consumption_coordinator', \
                     'alr_challenger_consumption_caller' \
                 ]) AS role_name(name) \
                 WHERE pg_catalog.has_parameter_privilege( \
                     role_name.name, 'session_replication_role', 'SET' \
                 ) \
             ) \
             AND NOT EXISTS ( \
                 SELECT 1 FROM pg_catalog.unnest(ARRAY['trading_ai', 'alr_shadow']) \
                     AS role_name(name) \
                 WHERE pg_catalog.has_parameter_privilege( \
                     role_name.name, 'session_replication_role', 'SET' \
                 ) \
             ) \
             AND NOT EXISTS ( \
                 SELECT 1 \
                 FROM pg_catalog.pg_parameter_acl AS parameter_acl \
                 CROSS JOIN LATERAL pg_catalog.aclexplode(parameter_acl.paracl) AS privilege \
                 JOIN pg_catalog.pg_roles AS grantee ON grantee.oid = privilege.grantee \
                 WHERE parameter_acl.parname = 'session_replication_role' \
                   AND grantee.rolname IN ( \
                       'alr_challenger_writer', \
                       'alr_challenger_trainer_caller', \
                       'alr_challenger_fit_attestor', \
                       'alr_challenger_fit_attestor_caller', \
                       'alr_challenger_consumption_coordinator', \
                       'alr_challenger_consumption_caller', \
                       'trading_ai', \
                       'alr_shadow' \
                   ) \
                   AND privilege.privilege_type = 'SET' \
             )",
    )
    .fetch_one(&mut *tx)
    .await
    .expect("verify exact V158 role posture");
    assert!(
        posture_is_exact,
        "V158 role fixture found attribute, membership, or parameter-privilege drift"
    );
    tx.commit()
        .await
        .expect("commit exact V158 role prerequisites in disposable cluster");
}

/// Prepare the exact pre-V158 schema used as the immutable template for the
/// V159 functional and concurrency probes. This test is separately gated so
/// the normal full-tree schema suite never stops at an old migration version.
/// Hosted CI independently prepares two different disposable databases through
/// V157; each probe then applies V158/V159 itself against empty ALR tables.
#[tokio::test]
async fn prepare_v159_probe_v157_baseline() {
    if std::env::var(V159_BASELINE_ACK_ENV_VAR).as_deref() != Ok("1") {
        eprintln!("SKIP: {V159_BASELINE_ACK_ENV_VAR}=1 not set");
        return;
    }
    let pool = maybe_pool()
        .await
        .expect("V159 baseline acknowledgement requires OPENCLAW_TEST_PG");
    seed_legacy_precondition(&pool).await;
    let role_preconditions = seed_v158_role_preconditions(&pool);
    role_preconditions.await;

    let migrations_dir = srv_root().join("sql").join("migrations");
    let all_migrations = load_migrations_from_dir(&migrations_dir)
        .expect("load canonical migration tree for V159 probe baseline");
    assert!(
        all_migrations.iter().any(|m| m.version == 158)
            && all_migrations.iter().any(|m| m.version == 159),
        "V159 probe baseline requires the canonical V158 and V159 sources"
    );
    let baseline_migrations = all_migrations
        .into_iter()
        .filter(|migration| migration.version <= V159_BASELINE_VERSION)
        .collect();
    build_migrator(baseline_migrations)
        .run(&pool)
        .await
        .expect("apply canonical migration tree through V157");

    let (highest_version, post_v157_count, v158_relations): (Option<i64>, i64, i64) =
        sqlx::query_as(
            "SELECT \
                 (SELECT max(version) FROM public._sqlx_migrations), \
                 (SELECT count(*) FROM public._sqlx_migrations WHERE version > 157), \
                 (SELECT count(*) FROM pg_catalog.pg_class AS relation \
                    JOIN pg_catalog.pg_namespace AS namespace \
                      ON namespace.oid = relation.relnamespace \
                   WHERE namespace.nspname = 'learning' \
                     AND relation.relname IN ( \
                         'alr_qualified_training_receipts', \
                         'alr_challenger_training_runs', \
                         'alr_challenger_model_artifacts', \
                         'alr_challenger_registry', \
                         'alr_challenger_fit_attestations' \
                     ))",
        )
        .fetch_one(&pool)
        .await
        .expect("verify exact V157 probe baseline");
    assert_eq!(highest_version, Some(V159_BASELINE_VERSION));
    assert_eq!(
        post_v157_count, 0,
        "V159 baseline applied a post-V157 migration"
    );
    assert_eq!(
        v158_relations, 0,
        "V159 baseline is not empty of V158/V159 durable relations"
    );
    pool.close().await;
}

/// Prepare an independently disposable pre-V158 database for each V160 probe.
/// The Python probes own application of V158/V159/V160 and their replay checks;
/// this Rust fixture only establishes the canonical V157 migration baseline and
/// all eight exact role prerequisites shared by those forward migrations.
#[tokio::test]
async fn prepare_v160_probe_v157_baseline() {
    if std::env::var(V160_BASELINE_ACK_ENV_VAR).as_deref() != Ok("1") {
        eprintln!("SKIP: {V160_BASELINE_ACK_ENV_VAR}=1 not set");
        return;
    }
    let pool = maybe_pool()
        .await
        .expect("V160 baseline acknowledgement requires OPENCLAW_TEST_PG");
    seed_legacy_precondition(&pool).await;
    let role_preconditions = seed_v158_role_preconditions(&pool);
    role_preconditions.await;

    let migrations_dir = srv_root().join("sql").join("migrations");
    let all_migrations = load_migrations_from_dir(&migrations_dir)
        .expect("load canonical migration tree for V160 probe baseline");
    assert!(
        all_migrations
            .iter()
            .any(|migration| migration.version == 158)
            && all_migrations
                .iter()
                .any(|migration| migration.version == 159)
            && all_migrations
                .iter()
                .any(|migration| migration.version == 160),
        "V160 probe baseline requires canonical V158/V159/V160 sources"
    );
    let baseline_migrations: Vec<_> = all_migrations
        .into_iter()
        .filter(|migration| migration.version <= V160_BASELINE_VERSION)
        .collect();
    let expected_baseline_migration_count = i64::try_from(baseline_migrations.len())
        .expect("canonical V157 migration count fits BIGINT");
    let mut canonical_baseline_versions: Vec<i64> = baseline_migrations
        .iter()
        .map(|migration| migration.version)
        .collect();
    canonical_baseline_versions.sort_unstable();
    canonical_baseline_versions.dedup();
    assert_eq!(
        i64::try_from(canonical_baseline_versions.len())
            .expect("canonical unique V157 migration count fits BIGINT"),
        expected_baseline_migration_count,
        "V160 canonical V157 source migration versions are not unique"
    );
    assert_eq!(
        canonical_baseline_versions.last().copied(),
        Some(V160_BASELINE_VERSION),
        "V160 canonical baseline source does not terminate at V157"
    );
    build_migrator(baseline_migrations)
        .run(&pool)
        .await
        .expect("apply canonical migration tree through V157 for V160 probe");

    let (
        highest_version,
        migration_count,
        distinct_migration_count,
        post_v157_count,
        failed_migration_count,
        durable_relations,
    ): (Option<i64>, i64, i64, i64, i64, i64) = sqlx::query_as(
        "SELECT \
                 (SELECT max(version) FROM public._sqlx_migrations), \
                 (SELECT count(*) FROM public._sqlx_migrations), \
                 (SELECT count(DISTINCT version) FROM public._sqlx_migrations), \
                 (SELECT count(*) FROM public._sqlx_migrations WHERE version > 157), \
                 (SELECT count(*) FROM public._sqlx_migrations WHERE success IS NOT TRUE), \
                 (SELECT count(*) FROM pg_catalog.pg_class AS relation \
                    JOIN pg_catalog.pg_namespace AS namespace \
                      ON namespace.oid = relation.relnamespace \
                   WHERE namespace.nspname = 'learning' \
                     AND relation.relname IN ( \
                         'alr_qualified_training_receipts', \
                         'alr_challenger_fit_attestations', \
                         'alr_challenger_training_runs', \
                         'alr_challenger_model_artifacts', \
                         'alr_challenger_registry', \
                         'alr_challenger_consumption_requests', \
                         'alr_challenger_consumption_claims', \
                         'alr_challenger_consumption_statuses', \
                         'alr_challenger_consumption_verifier_evidence', \
                         'alr_challenger_consumption_terminals', \
                         'alr_challenger_consumption_reconciliation_audit' \
                     ))",
    )
    .fetch_one(&pool)
    .await
    .expect("verify exact V157 V160-probe baseline");
    assert_eq!(highest_version, Some(V160_BASELINE_VERSION));
    assert_eq!(
        post_v157_count, 0,
        "V160 baseline applied a post-V157 migration"
    );
    assert_eq!(
        migration_count, expected_baseline_migration_count,
        "V160 baseline ledger differs from the canonical loaded <=V157 sources"
    );
    assert_eq!(
        distinct_migration_count, expected_baseline_migration_count,
        "V160 baseline ledger contains duplicate migration versions"
    );
    assert_eq!(
        failed_migration_count, 0,
        "V160 baseline ledger contains a failed migration"
    );
    assert_eq!(
        durable_relations, 0,
        "V160 baseline is not empty of V158/V159/V160 durable relations"
    );

    let sentinel_absent: bool = sqlx::query_scalar(
        "SELECT pg_catalog.to_regclass( \
             'public.alr_v160_disposable_probe_sentinel' \
         ) IS NULL",
    )
    .fetch_one(&pool)
    .await
    .expect("inspect V160 disposable baseline sentinel absence");
    assert!(
        sentinel_absent,
        "V160 disposable baseline sentinel already exists"
    );
    sqlx::query(
        "CREATE TABLE public.alr_v160_disposable_probe_sentinel ( \
             sentinel_id TEXT PRIMARY KEY, \
             database_name TEXT NOT NULL, \
             database_oid TEXT NOT NULL, \
             server_version_num TEXT NOT NULL, \
             postmaster_started_at TEXT NOT NULL, \
             database_owner TEXT NOT NULL, \
             baseline_session_user TEXT NOT NULL, \
             baseline_current_user TEXT NOT NULL, \
             highest_migration BIGINT NOT NULL, \
             migration_count BIGINT NOT NULL, \
             expected_migration_count BIGINT NOT NULL, \
             post_v157_count BIGINT NOT NULL, \
             created_at TIMESTAMPTZ NOT NULL DEFAULT pg_catalog.clock_timestamp() \
         )",
    )
    .execute(&pool)
    .await
    .expect("create V160 disposable baseline sentinel");
    sqlx::query(
        "INSERT INTO public.alr_v160_disposable_probe_sentinel ( \
             sentinel_id,database_name,database_oid,server_version_num, \
             postmaster_started_at,database_owner,baseline_session_user, \
             baseline_current_user,highest_migration,migration_count, \
             expected_migration_count,post_v157_count \
         ) SELECT \
             'V160_V157_BASELINE_DISPOSABLE_CONFIRMED:' || pg_catalog.current_database(), \
             pg_catalog.current_database(), \
             (SELECT oid::TEXT FROM pg_catalog.pg_database \
              WHERE datname=pg_catalog.current_database()), \
             pg_catalog.current_setting('server_version_num'), \
             pg_catalog.pg_postmaster_start_time()::TEXT, \
             pg_catalog.pg_get_userbyid(d.datdba),SESSION_USER,CURRENT_USER, \
             (SELECT max(version) FROM public._sqlx_migrations), \
             (SELECT count(*) FROM public._sqlx_migrations), \
             $1, \
             (SELECT count(*) FROM public._sqlx_migrations WHERE version>157) \
         FROM pg_catalog.pg_database d \
         WHERE d.datname=pg_catalog.current_database()",
    )
    .bind(expected_baseline_migration_count)
    .execute(&pool)
    .await
    .expect("insert exact V160 disposable baseline sentinel");
    let sentinel_is_exact: bool = sqlx::query_scalar(
        "SELECT count(*)=1 AND bool_and( \
             sentinel_id='V160_V157_BASELINE_DISPOSABLE_CONFIRMED:' || \
                 pg_catalog.current_database() \
             AND database_name=pg_catalog.current_database() \
             AND database_oid=(SELECT oid::TEXT FROM pg_catalog.pg_database \
                 WHERE datname=pg_catalog.current_database()) \
             AND server_version_num=pg_catalog.current_setting('server_version_num') \
             AND postmaster_started_at=pg_catalog.pg_postmaster_start_time()::TEXT \
             AND database_owner=(SELECT pg_catalog.pg_get_userbyid(datdba) \
                 FROM pg_catalog.pg_database \
                 WHERE datname=pg_catalog.current_database()) \
             AND baseline_session_user=SESSION_USER \
             AND baseline_current_user=CURRENT_USER \
             AND highest_migration=157 \
             AND migration_count=$1 \
             AND expected_migration_count=$1 \
             AND post_v157_count=0 \
         ) FROM public.alr_v160_disposable_probe_sentinel",
    )
    .bind(expected_baseline_migration_count)
    .fetch_one(&pool)
    .await
    .expect("verify exact V160 disposable baseline sentinel");
    assert!(
        sentinel_is_exact,
        "V160 disposable baseline sentinel identity or ledger drifted"
    );
    pool.close().await;
}

/// 對 ephemeral PG 跑真 migration 全樹後回 pool；未設 env 回 None（呼叫端 SKIP）。
/// Apply the full migration tree to an ephemeral PG, then return the pool.
///
/// 為什麼要在這裡跑 migration：契約測試必須對「migration 宣告的真實 schema」斷言，
/// 而非對手寫 fixture——否則 fixture 與 migration drift 時測試會 silent 假綠。
async fn migrated_pool() -> Option<PgPool> {
    let pool = maybe_pool().await?;
    // 先種 V005 brownfield 前置（見 seed_legacy_precondition），否則全樹在 ordinal 5 掛。
    // 對已 migrate 過的 DB 是 no-op（CREATE TABLE IF NOT EXISTS / 表早已 rename 走）。
    seed_legacy_precondition(&pool).await;
    // V158 intentionally fails closed unless its membership-free writer and
    // caller already exist. The fixture also provisions both generic roles so
    // their explicit revoke/Guard-C paths execute on every hosted run.
    seed_v158_role_preconditions(&pool).await;
    std::env::set_var(AUTO_MIGRATE_ENV_VAR, "1");
    let outcome = MigrationRunner::run_if_enabled(Some(&pool), &srv_root()).await;
    std::env::remove_var(AUTO_MIGRATE_ENV_VAR);
    match outcome {
        // Applied / SeededAndApplied / NoOp 皆可：CI fresh DB 走 Applied，
        // 重跑同 DB 走 NoOp，皆代表全樹已就緒。Disabled 不該出現（上面剛設旗標）。
        Ok(RunOutcome::Disabled) => {
            panic!("migration runner returned Disabled despite OPENCLAW_AUTO_MIGRATE=1");
        }
        Ok(_) => Some(pool),
        Err(e) => panic!("full migration-tree apply failed: {e}"),
    }
}

// ─────────────────────────────────────────────────────────────────
// 每個 case 開一條獨立 connection → begin transaction → INSERT/SELECT →
// ROLLBACK（不留 row）。用 connection 級 transaction 而非 pool，確保
// rollback 邊界清晰且不與其他 case 共用狀態。
// ─────────────────────────────────────────────────────────────────

/// 1) observability.data_quality_events —— quality_writer.rs:97 的 7-column INSERT
///    + `ON CONFLICT (event_id, ts)`。silent-warn-drop 類代表：column rename 立刻 fail。
#[tokio::test]
async fn contract_data_quality_events_insert() {
    let Some(pool) = migrated_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    let mut conn = pool.acquire().await.expect("acquire");
    let mut tx = conn.begin().await.expect("begin");
    let ts = chrono::Utc::now();
    sqlx::query(
        "INSERT INTO observability.data_quality_events \
         (ts, event_id, check_type, symbol, timeframe, severity, description) \
         VALUES ($1, $2, $3, $4, $5, $6, $7) \
         ON CONFLICT (event_id, ts) DO NOTHING",
    )
    .bind(ts)
    .bind("schema_contract_probe")
    .bind("STALE")
    .bind("BTCUSDT")
    .bind("1m")
    .bind("INFO")
    .bind("schema contract test probe / 契約測試探針")
    .execute(&mut *tx)
    .await
    .expect("data_quality_events INSERT contract broken");
    tx.rollback().await.expect("rollback");
}

/// 2) trading.fills —— 最熱 writer（trading_writer.rs:459）的代表性 column set，含
///    engine_mode（V015 ADD COLUMN）+ exit_source（V021）+ close_maker_*（V094）。
#[tokio::test]
async fn contract_trading_fills_insert() {
    let Some(pool) = migrated_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    let mut conn = pool.acquire().await.expect("acquire");
    let mut tx = conn.begin().await.expect("begin");
    let ts = chrono::Utc::now();
    // 與 trading_writer 同形：覆蓋 V003 base + V015 engine_mode + V021 exit_source
    // + V094 close-maker audit 欄位；這些跨多 migration 的欄位若被 rename/drop
    // 在此立刻 fail（編譯期看不見）。
    sqlx::query(
        "INSERT INTO trading.fills \
         (ts, fill_id, order_id, symbol, side, qty, price, fee, realized_pnl, \
          is_paper, strategy_name, context_id, engine_mode, exit_source, \
          close_maker_attempt, close_maker_fallback_reason) \
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16)",
    )
    .bind(ts)
    .bind("schema_contract_fill")
    .bind("schema_contract_order")
    .bind("BTCUSDT")
    .bind("Buy")
    .bind(0.001_f32)
    .bind(50000.0_f32)
    .bind(0.05_f32)
    .bind(0.0_f32)
    .bind(false)
    .bind("schema_contract")
    .bind("schema_contract_ctx")
    .bind("demo")
    .bind(None::<String>)
    .bind(false)
    .bind(None::<String>)
    .execute(&mut *tx)
    .await
    .expect("trading.fills INSERT contract broken");
    tx.rollback().await.expect("rollback");
}

/// 3) learning.exit_features —— ML 熱表（exit_feature_writer.rs:123）全 column INSERT
///    + `ON CONFLICT (context_id, ts)`。NOT NULL 欄位（含 feature_schema_hash）必帶值。
#[tokio::test]
async fn contract_exit_features_insert() {
    let Some(pool) = migrated_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    let mut conn = pool.acquire().await.expect("acquire");
    let mut tx = conn.begin().await.expect("begin");
    let ts = chrono::Utc::now();
    sqlx::query(
        "INSERT INTO learning.exit_features \
         (context_id, ts, engine_mode, strategy_name, symbol, side, \
          est_net_bps, peak_pnl_pct, atr_pct, giveback_atr_norm, \
          time_since_peak_ms, price_roc_short, entry_age_secs, \
          exit_source, exit_trigger_rule, realized_net_bps, \
          feature_schema_version, feature_schema_hash) \
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13,$14,$15,$16,$17,$18) \
         ON CONFLICT (context_id, ts) DO NOTHING",
    )
    .bind("schema_contract_ctx")
    .bind(ts)
    .bind("demo")
    .bind("schema_contract")
    .bind("BTCUSDT")
    .bind(1_i16) // side SMALLINT
    .bind(Some(1.0_f32))
    .bind(Some(2.0_f32))
    .bind(Some(0.5_f32))
    .bind(Some(0.3_f32))
    .bind(Some(1000_i64))
    .bind(Some(0.1_f32))
    .bind(Some(60.0_f32))
    .bind(Some("Physical"))
    .bind(Some("PHYS-LOCK"))
    .bind(Some(3.0_f32))
    .bind("v1.0")
    .bind("schema_contract_hash")
    .execute(&mut *tx)
    .await
    .expect("learning.exit_features INSERT contract broken");
    tx.rollback().await.expect("rollback");
}

/// 4) trading.decision_outcomes —— 歷史 engine_mode INSERT 漏接線 bug 表
///    （outcome_backfiller.rs:91）。engine_mode（V015 ADD COLUMN）+ PK context_id。
#[tokio::test]
async fn contract_decision_outcomes_insert() {
    let Some(pool) = migrated_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    let mut conn = pool.acquire().await.expect("acquire");
    let mut tx = conn.begin().await.expect("begin");
    sqlx::query(
        "INSERT INTO trading.decision_outcomes \
         (context_id, outcome_1m, outcome_5m, outcome_1h, outcome_4h, outcome_24h, \
          max_favorable, max_adverse, backfilled_ts, engine_mode) \
         VALUES ($1,$2,$3,$4,$5,$6,$7,$8,NOW(),$9) \
         ON CONFLICT (context_id) DO NOTHING",
    )
    .bind("schema_contract_ctx")
    .bind(0.01_f32)
    .bind(0.02_f32)
    .bind(0.03_f32)
    .bind(0.04_f32)
    .bind(0.05_f32)
    .bind(0.06_f32)
    .bind(-0.01_f32)
    .bind("demo")
    .execute(&mut *tx)
    .await
    .expect("trading.decision_outcomes INSERT contract broken");
    tx.rollback().await.expect("rollback");
}

/// 5) learning.model_registry —— registry 軸 consumer SELECT（ml/registry.rs:224）。
///    驗 SELECT column set + WHERE/ORDER BY 引用的欄位仍存在（空表回 None 即合約成立）。
#[tokio::test]
async fn contract_model_registry_select() {
    let Some(pool) = migrated_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    let mut conn = pool.acquire().await.expect("acquire");
    // consumer 為唯讀 SELECT；空表回 None 不影響合約（驗的是 column 仍可被選取/過濾/排序）。
    let row: Option<(
        i64,
        String,
        String,
        String,
        String,
        Option<String>,
        Option<String>,
    )> = sqlx::query_as(
        "SELECT id, artifact_path, canary_status, verdict, \
                to_char(train_date, 'YYYY-MM-DD') AS train_date, \
                artifact_sha256, feature_schema_hash \
         FROM learning.model_registry \
         WHERE strategy = $1 AND engine_mode = $2 AND quantile = $3 \
           AND canary_status IN ('production', 'promoting') \
         ORDER BY \
           CASE canary_status WHEN 'production' THEN 0 ELSE 1 END ASC, \
           promoted_at DESC NULLS LAST, \
           created_at DESC \
         LIMIT 1",
    )
    .bind("schema_contract")
    .bind("demo")
    .bind("q50")
    .fetch_optional(&mut *conn)
    .await
    .expect("learning.model_registry SELECT contract broken");
    assert!(
        row.is_none(),
        "fresh DB unexpectedly returned a registry row"
    );
}

/// 6) market.klines —— 最高頻 consumer SELECT（outcome_backfiller.rs:54 的 LATERAL
///    子查詢取 `k.close`）。驗 close / symbol / timeframe / ts 仍可查。
#[tokio::test]
async fn contract_klines_select() {
    let Some(pool) = migrated_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    let mut conn = pool.acquire().await.expect("acquire");
    // 鏡像 outcome_backfiller 取下一根 bar close 的代表性子查詢形狀。
    let close: Option<f32> = sqlx::query_scalar(
        "SELECT k.close FROM market.klines k \
         WHERE k.symbol = $1 AND k.timeframe = '1m' \
           AND k.ts >= NOW() \
         ORDER BY k.ts ASC LIMIT 1",
    )
    .bind("BTCUSDT")
    .fetch_optional(&mut *conn)
    .await
    .expect("market.klines SELECT contract broken");
    assert!(
        close.is_none(),
        "fresh DB unexpectedly returned a kline row"
    );
}

/// H1: the Grafana bridge must expose lifecycle progress and isolate engine modes.
#[tokio::test]
async fn contract_h1_order_events_lifecycle() {
    let Some(pool) = migrated_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    let mut tx = pool.begin().await.expect("transaction");
    let id = format!("schema-h1-{}", std::process::id());
    sqlx::query("INSERT INTO trading.orders (ts, order_id, symbol, side, order_type, qty, status, engine_mode) VALUES (NOW(), $1, 'BTCUSDT', 'Buy', 'Market', 1, 'PendingSubmit', 'demo')")
        .bind(&id).execute(&mut *tx).await.unwrap();
    let status: String =
        sqlx::query_scalar("SELECT status FROM public.order_events WHERE order_id=$1")
            .bind(&id)
            .fetch_one(&mut *tx)
            .await
            .unwrap();
    assert_eq!(status, "PendingSubmit");
    for (n, expected) in ["Acknowledged", "Working", "Filled"]
        .into_iter()
        .enumerate()
    {
        sqlx::query("INSERT INTO trading.order_state_changes (ts, order_id, to_status, filled_qty, engine_mode) VALUES (NOW() + $2::INT * interval '1 second', $1, $3, 1, 'demo')")
            .bind(&id).bind(n as i32).bind(expected).execute(&mut *tx).await.unwrap();
        let status: String =
            sqlx::query_scalar("SELECT status FROM public.order_events WHERE order_id=$1")
                .bind(&id)
                .fetch_one(&mut *tx)
                .await
                .unwrap();
        assert_eq!(status, expected);
    }
    sqlx::query("INSERT INTO trading.order_state_changes (ts, order_id, to_status, engine_mode) VALUES (NOW() + interval '1 hour', $1, 'Rejected', 'live')")
        .bind(&id).execute(&mut *tx).await.unwrap();
    let status: String =
        sqlx::query_scalar("SELECT status FROM public.order_events WHERE order_id=$1")
            .bind(&id)
            .fetch_one(&mut *tx)
            .await
            .unwrap();
    assert_eq!(status, "Filled", "other engine must not replace demo state");
    tx.rollback().await.unwrap();
}

#[tokio::test]
async fn contract_h1_clock_skew_and_complete_fill_average() {
    let Some(pool) = migrated_pool().await else {
        return;
    };
    let mut tx = pool.begin().await.unwrap();
    let id = "schema-h1-causal-fills";
    sqlx::query("INSERT INTO trading.orders (ts, order_id, symbol, side, order_type, qty, price, status, engine_mode) VALUES (NOW(),$1,'BTCUSDT','Buy','Limit',10,100,'PendingSubmit','demo')")
        .bind(id).execute(&mut *tx).await.unwrap();
    for (offset, status, qty, price) in [
        (30, "Acknowledged", 0.0, None),
        (-5, "PartiallyFilled", 3.0, Some(200.0)),
        (40, "Unknown", 3.0, None),
        (-4, "Working", 3.0, None),
        (-3, "Filled", 3.0, None),
    ] {
        sqlx::query("INSERT INTO trading.order_state_changes (ts,order_id,to_status,filled_qty,avg_price,engine_mode) VALUES (NOW()+$2::INT*interval '1 second',$1,$3,$4,$5,'demo')")
            .bind(id).bind(offset).bind(status).bind(qty as f32).bind(price.map(|p| p as f32)).execute(&mut *tx).await.unwrap();
        let actual: String =
            sqlx::query_scalar("SELECT status FROM public.order_events WHERE order_id=$1")
                .bind(id)
                .fetch_one(&mut *tx)
                .await
                .unwrap();
        assert_eq!(
            actual, status,
            "arrival order must win over skewed source timestamps"
        );
    }
    // Even an obsolete late ACK cannot hide definitive terminal evidence.
    sqlx::query("INSERT INTO trading.order_state_changes (ts,order_id,to_status,engine_mode) VALUES (NOW()+interval '1 hour',$1,'Acknowledged','demo')")
        .bind(id).execute(&mut *tx).await.unwrap();
    for (fill_id, qty, price, mode) in [
        ("h1-fill-a", 2.0, 100.0, "demo"),
        ("h1-fill-b", 1.0, 200.0, "demo"),
        ("h1-fill-other", 9.0, 999.0, "live"),
    ] {
        sqlx::query("INSERT INTO trading.fills (ts,fill_id,order_id,symbol,side,qty,price,engine_mode) VALUES (NOW(),$1,$2,'BTCUSDT','Buy',$3,$4,$5)")
            .bind(fill_id).bind(id).bind(qty as f32).bind(price as f32).bind(mode).execute(&mut *tx).await.unwrap();
    }
    let (status,qty,avg):(String,f64,f64) = sqlx::query_as("SELECT status,filled_qty::float8,avg_price::float8 FROM public.order_events WHERE order_id=$1")
        .bind(id).fetch_one(&mut *tx).await.unwrap();
    assert_eq!(status, "Filled");
    assert_eq!(qty, 3.0);
    assert!((avg - 400.0 / 3.0).abs() < 1e-6);
    // V161 must grant the new sequence default to the engine's writer role.
    sqlx::query("GRANT USAGE ON SCHEMA trading TO trading_ai")
        .execute(&mut *tx)
        .await
        .unwrap();
    sqlx::query("GRANT INSERT, SELECT ON trading.order_state_changes TO trading_ai")
        .execute(&mut *tx)
        .await
        .unwrap();
    sqlx::query("SET LOCAL ROLE trading_ai")
        .execute(&mut *tx)
        .await
        .unwrap();
    sqlx::query("INSERT INTO trading.order_state_changes (ts,order_id,to_status,engine_mode) VALUES (NOW(),'h1-role','Working','demo')").execute(&mut *tx).await.unwrap();
    tx.rollback().await.unwrap();
}

/// Apply the exact forward DDL to a populated compressed hypertable as well
/// as the empty full-tree CI database. Historical chunks must not be rewritten.
#[tokio::test]
async fn contract_h1_migration_preserves_compressed_history() {
    let Some(pool) = migrated_pool().await else {
        return;
    };
    let mut tx = pool.begin().await.unwrap();
    sqlx::raw_sql(
        "CREATE SCHEMA h1_migration_probe;
        CREATE TABLE h1_migration_probe.orders (LIKE trading.orders INCLUDING DEFAULTS);
        CREATE TABLE h1_migration_probe.fills (LIKE trading.fills INCLUDING DEFAULTS);
        CREATE TABLE h1_migration_probe.order_state_changes
            (ts timestamptz NOT NULL, order_id text, to_status text,
             filled_qty real, avg_price real, engine_mode text);
        SELECT create_hypertable('h1_migration_probe.order_state_changes','ts');
        ALTER TABLE h1_migration_probe.order_state_changes SET
            (timescaledb.compress, timescaledb.compress_segmentby='order_id');
        INSERT INTO h1_migration_probe.order_state_changes
            VALUES (NOW()-interval '30 days','legacy','Working',0,NULL,'demo');
        SELECT compress_chunk(show_chunks('h1_migration_probe.order_state_changes'));",
    )
    .execute(&mut *tx)
    .await
    .unwrap();
    let ddl = std::fs::read_to_string(
        srv_root().join("sql/migrations/V161__order_events_lifecycle_projection.sql"),
    )
    .unwrap()
    .replace("trading.", "h1_migration_probe.")
    .replace("public.order_events", "h1_migration_probe.order_events");
    sqlx::raw_sql(&ddl)
        .execute(&mut *tx)
        .await
        .expect("V161 on existing compressed history");
    let old_seq: Option<i64> = sqlx::query_scalar(
        "SELECT lifecycle_seq FROM h1_migration_probe.order_state_changes WHERE order_id='legacy'",
    )
    .fetch_one(&mut *tx)
    .await
    .unwrap();
    assert_eq!(old_seq, None, "legacy compressed rows remain untouched");
    let new_seq: i64 = sqlx::query_scalar("INSERT INTO h1_migration_probe.order_state_changes (ts,order_id,to_status,engine_mode) VALUES (NOW(),'new','Working','demo') RETURNING lifecycle_seq")
        .fetch_one(&mut *tx).await.unwrap();
    assert!(new_seq > 0);
    sqlx::raw_sql(&ddl)
        .execute(&mut *tx)
        .await
        .expect("V161 replay on populated compressed history");
    let next_seq: i64 = sqlx::query_scalar("INSERT INTO h1_migration_probe.order_state_changes (ts,order_id,to_status,engine_mode) VALUES (NOW(),'replay','Working','demo') RETURNING lifecycle_seq")
        .fetch_one(&mut *tx).await.unwrap();
    assert!(next_seq > new_seq, "replay must not reset the sequence");
    tx.rollback().await.unwrap();
}

#[tokio::test]
async fn contract_h1_migration_rejects_ordinal_drift() {
    let Some(pool) = migrated_pool().await else {
        return;
    };
    let ddl = std::fs::read_to_string(
        srv_root().join("sql/migrations/V161__order_events_lifecycle_projection.sql"),
    )
    .unwrap()
    .replace("trading.", "h1_drift_probe.")
    .replace("public.order_events", "h1_drift_probe.order_events");
    for (preparation, expected) in [
        ("CREATE TABLE h1_drift_probe.order_state_changes (lifecycle_seq TEXT)", "Guard B"),
        ("CREATE TABLE h1_drift_probe.order_state_changes (lifecycle_seq BIGINT); CREATE TABLE h1_drift_probe.order_state_changes_lifecycle_seq (id INT)", "Guard A"),
        ("CREATE TABLE h1_drift_probe.order_state_changes (lifecycle_seq BIGINT DEFAULT 0)", "default mismatch"),
        ("CREATE TABLE h1_drift_probe.order_state_changes (lifecycle_seq BIGINT); INSERT INTO h1_drift_probe.order_state_changes VALUES (99)", "behind existing ordinals"),
    ] {
        let mut tx = pool.begin().await.unwrap();
        sqlx::raw_sql(&format!("CREATE SCHEMA h1_drift_probe; {preparation}"))
            .execute(&mut *tx).await.unwrap();
        let error = sqlx::raw_sql(&ddl).execute(&mut *tx).await.unwrap_err();
        assert!(error.to_string().contains(expected), "expected {expected}: {error}");
        tx.rollback().await.unwrap();
    }
}

#[tokio::test]
async fn contract_h1_reused_id_keeps_order_incarnations_separate() {
    let Some(pool) = migrated_pool().await else {
        return;
    };
    let mut tx = pool.begin().await.unwrap();
    let id = "schema-h1-reused-id";
    for (hours, status, qty) in [
        (3, "Filled", 1.0),
        (2, "Rejected", 0.0),
        (1, "PartiallyFilled", 0.25),
    ] {
        sqlx::query("INSERT INTO trading.orders(ts,order_id,symbol,side,order_type,qty,price,status,engine_mode) VALUES(NOW()-$2::INT*interval '1 hour',$1,'BTCUSDT','Buy','Limit',1,200,'PendingSubmit','demo')")
            .bind(id).bind(hours).execute(&mut *tx).await.unwrap();
        sqlx::query("INSERT INTO trading.order_state_changes(ts,order_id,to_status,filled_qty,engine_mode) VALUES(NOW()-$2::INT*interval '1 hour',$1,'PendingSubmit',0,'demo')")
            .bind(id).bind(hours).execute(&mut *tx).await.unwrap();
        // The newest incarnation's venue clock precedes both newer registrations.
        let event_hours = if hours == 1 { 3 } else { hours };
        sqlx::query("INSERT INTO trading.order_state_changes(ts,order_id,to_status,filled_qty,engine_mode) VALUES(NOW()-$2::INT*interval '1 hour'+$3::INT*interval '1 minute',$1,$4,$5,'demo')")
            .bind(id).bind(event_hours).bind(4-hours).bind(status).bind(qty as f32).execute(&mut *tx).await.unwrap();
    }
    for (hours, qty, price) in [(3, 1.0, 100.0), (1, 0.25, 200.0)] {
        sqlx::query("INSERT INTO trading.fills(ts,fill_id,order_id,symbol,side,qty,price,engine_mode) VALUES(NOW()-$1::INT*interval '1 hour'+interval '1 minute',$2,$3,'BTCUSDT','Buy',$4,$5,'demo')")
            .bind(hours).bind(format!("{id}-{hours}")).bind(id).bind(qty as f32).bind(price as f32).execute(&mut *tx).await.unwrap();
    }
    let rows: Vec<(String,f64,Option<f64>)> = sqlx::query_as("SELECT status,filled_qty::float8,avg_price::float8 FROM public.order_events WHERE order_id=$1 ORDER BY ts")
        .bind(id).fetch_all(&mut *tx).await.unwrap();
    assert_eq!(
        rows,
        vec![
            ("Filled".into(), 1.0, Some(100.0)),
            ("Rejected".into(), 0.0, None),
            ("PartiallyFilled".into(), 0.25, Some(200.0))
        ]
    );
    // Legacy/new rows without a registration marker still have timestamp bounds.
    sqlx::query("INSERT INTO trading.orders(ts,order_id,symbol,side,order_type,qty,status,engine_mode) VALUES(NOW()-interval '2 hours','h1-legacy-reused','BTCUSDT','Buy','Market',1,'Working','demo'),(NOW(),'h1-legacy-reused','BTCUSDT','Buy','Market',1,'PendingSubmit','demo')").execute(&mut *tx).await.unwrap();
    sqlx::query("INSERT INTO trading.order_state_changes(ts,order_id,to_status,filled_qty,engine_mode) VALUES(NOW()-interval '1 hour','h1-legacy-reused','Filled',1,'demo')").execute(&mut *tx).await.unwrap();
    let statuses: Vec<String> = sqlx::query_scalar(
        "SELECT status FROM public.order_events WHERE order_id='h1-legacy-reused' ORDER BY ts",
    )
    .fetch_all(&mut *tx)
    .await
    .unwrap();
    assert_eq!(statuses, vec!["Filled", "PendingSubmit"]);
    tx.rollback().await.unwrap();
}

#[tokio::test]
async fn contract_h1_flashdip_restores_projected_pending_cap() {
    let Some(pool) = migrated_pool().await else {
        return;
    };
    let mut tx = pool.begin().await.unwrap();
    for (symbol, status) in [
        ("H1WORKUSDT", "Working"),
        ("H1PARTIALUSDT", "PartiallyFilled"),
        ("H1UNKNOWNUSDT", "Unknown"),
        ("H1ACKUSDT", "Acknowledged"),
        ("H1DONEUSDT", "Filled"),
        ("H1REJECTUSDT", "Rejected"),
    ] {
        sqlx::query("INSERT INTO trading.orders(ts,order_id,symbol,side,order_type,qty,price,status,engine_mode,strategy_name) VALUES(NOW(),$1,$1,'Buy','Limit',1,100,'PendingSubmit','demo','flash_dip_buy')")
            .bind(symbol).execute(&mut *tx).await.unwrap();
        sqlx::query("INSERT INTO trading.order_state_changes(ts,order_id,to_status,filled_qty,engine_mode) VALUES(NOW()+interval '1 second',$1,$2,0,'demo')")
            .bind(symbol).bind(status).execute(&mut *tx).await.unwrap();
    }
    // Execute the exact SQL included by the production bootstrap reader.
    let mut rows: Vec<String> =
        sqlx::query_scalar(include_str!("../src/event_consumer/flash_dip_pending.sql"))
            .bind(0.0_f64)
            .fetch_all(&mut *tx)
            .await
            .unwrap();
    rows.sort();
    assert_eq!(
        rows,
        vec!["H1ACKUSDT", "H1PARTIALUSDT", "H1UNKNOWNUSDT", "H1WORKUSDT"]
    );
    tx.rollback().await.unwrap();
}
