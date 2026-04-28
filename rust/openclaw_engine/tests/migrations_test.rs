//! Integration tests for the auto-migration runner.
//! 自動遷移執行器的整合測試。
//!
//! MODULE_NOTE (EN): Requires a live Postgres the test can create tables in.
//!   Pass the connection URL via `OPENCLAW_TEST_PG` env var. Tests are skipped
//!   (not failed) when the env var is absent so CI without a local pg is green.
//!   Each test uses a fresh schema space by wiping `_sqlx_migrations` + a
//!   handful of seed objects up front. DO NOT point this at any DB carrying
//!   real data — the tests will drop `_sqlx_migrations` and may apply V001+
//!   which creates the full trading/learning/market schema tree.
//! MODULE_NOTE (中): 需連得上 Postgres 測試 DB。透過 `OPENCLAW_TEST_PG` 環境變數
//!   傳入連線 URL；未設則跳過測試不視為失敗，CI 本機無 pg 依然綠。
//!   每個 case 會清空 `_sqlx_migrations` 與幾個 seed 物件；**切勿**指向正式
//!   DB，測試會 drop tracking table 並可能套用 V001+ 建立完整 schema 樹。

use openclaw_engine::database::migrations::{
    ensure_legacy_seeded, list_applied_versions, load_migrations_from_dir, truncate_tracking_table,
    MigrationRunner, MigrationsError, RunOutcome, AUTO_MIGRATE_ENV_VAR, MIGRATIONS_DIR_REL,
};
use sqlx::postgres::PgPool;
use sqlx::Executor;
use std::path::PathBuf;

/// Resolve the `srv` repo root for the running test binary.
/// 解析測試二進位對應的 `srv` repo root。
fn srv_root() -> PathBuf {
    // CARGO_MANIFEST_DIR points at `srv/rust/openclaw_engine`; two levels up to
    // reach `srv/`. Env var `OPENCLAW_BASE_DIR` wins if set.
    // CARGO_MANIFEST_DIR 指到 `srv/rust/openclaw_engine`，向上兩層為 `srv/`。
    if let Ok(env) = std::env::var("OPENCLAW_BASE_DIR") {
        return PathBuf::from(env);
    }
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

/// Build a Postgres pool from OPENCLAW_TEST_PG. Returns None if unset so the
/// caller can skip the test.
/// 用 OPENCLAW_TEST_PG 建 pool；未設回 None 由呼叫端跳過。
async fn maybe_pool() -> Option<PgPool> {
    let url = std::env::var("OPENCLAW_TEST_PG").ok()?;
    match sqlx::postgres::PgPoolOptions::new()
        .max_connections(2)
        .acquire_timeout(std::time::Duration::from_secs(5))
        .connect(&url)
        .await
    {
        Ok(p) => Some(p),
        Err(e) => {
            eprintln!("[migrations_test] OPENCLAW_TEST_PG set but connect failed: {e}");
            None
        }
    }
}

/// Wipe `_sqlx_migrations` (and, for legacy-seed tests, the canary table) so
/// each case runs against a known baseline.
/// 每個 case 先清 `_sqlx_migrations`（legacy-seed case 另清 canary 表）。
async fn reset_tracking(pool: &PgPool) {
    let _ = truncate_tracking_table(pool).await;
}

/// Drop ALL schemas that V001 creates. Used only by the "fresh DB" path test
/// — destructive, therefore additionally gated behind OPENCLAW_TEST_PG_DESTRUCTIVE=1.
/// 清掉 V001 建的所有 schema。僅「fresh DB」case 使用；另需
/// OPENCLAW_TEST_PG_DESTRUCTIVE=1 才會跑。
async fn wipe_app_schemas(pool: &PgPool) {
    for s in [
        "market",
        "trading",
        "agent",
        "learning",
        "features",
        "observability",
        "risk",
        "news",
    ] {
        let sql = format!("DROP SCHEMA IF EXISTS {s} CASCADE");
        let _ = pool.execute(sql.as_str()).await;
    }
}

// ─────────────────────────────────────────────────────────────────
// 1) Disabled flag path — already covered by the lib unit test; we
//    re-validate end-to-end here so an integration caller can skip
//    safely even when they forget to set OPENCLAW_AUTO_MIGRATE.
// 1) 旗標關閉 — lib unit test 已覆蓋，這裡做 E2E 再驗一次。
// ─────────────────────────────────────────────────────────────────
#[tokio::test]
async fn flag_disabled_is_noop_even_with_pool() {
    let Some(pool) = maybe_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    std::env::remove_var(AUTO_MIGRATE_ENV_VAR);
    let outcome = MigrationRunner::run_if_enabled(Some(&pool), &srv_root())
        .await
        .expect("run_if_enabled Err with flag unset");
    assert_eq!(outcome, RunOutcome::Disabled);
}

// ─────────────────────────────────────────────────────────────────
// 2) Legacy-applied DB: canary table exists, tracking table empty.
//    Expect seed of 22 rows, then migrator runs as no-op.
// 2) Legacy-applied DB：canary 表在、tracking 表空；
//    預期 seed 22 行，migrator 跑 no-op。
// ─────────────────────────────────────────────────────────────────
#[tokio::test]
async fn legacy_seed_populates_tracking_table() {
    let Some(pool) = maybe_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };
    // Pre-req: canary table `learning.model_registry` must exist (live DB has
    // it per 2026-04-24 state). Create a minimal stub if absent so the test
    // can run on any test DB that has had V023 applied OR we are allowed to
    // fake the canary. We do NOT create it implicitly when the test DB is
    // virgin — that is what test #3 covers.
    // 前提：`learning.model_registry` 表在（2026-04-24 live 狀態）。測試 DB
    // 已套用 V023 則通過；若 virgin DB 則跳過（留給 test #3 驗）。
    let canary_exists: Option<bool> = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables \
         WHERE table_schema = 'learning' AND table_name = 'model_registry')",
    )
    .fetch_optional(&pool)
    .await
    .unwrap();
    if !canary_exists.unwrap_or(false) {
        eprintln!(
            "SKIP: test DB has no learning.model_registry — legacy seed precondition not met"
        );
        return;
    }

    reset_tracking(&pool).await;

    let migrations_dir = srv_root().join(MIGRATIONS_DIR_REL);
    let migrations = load_migrations_from_dir(&migrations_dir).expect("load migrations");
    let seeded = ensure_legacy_seeded(&pool, &migrations)
        .await
        .expect("seed legacy");
    assert!(
        seeded >= 22,
        "expected ≥22 legacy rows seeded, got {seeded}"
    );

    let versions = list_applied_versions(&pool).await.unwrap();
    assert!(versions.contains(&1), "V001 row missing");
    assert!(versions.contains(&23), "V023 row missing");
    // V017_rollback and V999 must never appear / rollback + V999 不可出現
    assert!(
        !versions.iter().any(|v| *v == 999),
        "V999 test fixture leaked into tracking"
    );
}

// ─────────────────────────────────────────────────────────────────
// 3) Ambiguous state: app schemas exist BUT canary absent → refuse.
// 3) 曖昧狀態：有 app schema 但 canary 不存在 → 拒絕 seed。
// ─────────────────────────────────────────────────────────────────
#[tokio::test]
async fn ambiguous_state_is_rejected() {
    let Some(pool) = maybe_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };

    reset_tracking(&pool).await;

    // Probe whether app schemas exist but canary is absent. If BOTH conditions
    // hold, this is the exact ambiguous-state bucket we want to verify. If
    // the test DB is fully migrated (canary present), skip — this assertion
    // would need to drop the canary table, which is destructive.
    // 偵測是否處於「有 app schema 但無 canary」狀態；若 canary 在則跳過，
    // 因為 drop canary 屬破壞性操作。
    let app_schema_present: Option<bool> = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.schemata \
         WHERE schema_name IN ('learning','trading','market'))",
    )
    .fetch_optional(&pool)
    .await
    .unwrap();
    let canary_present: Option<bool> = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables \
         WHERE table_schema = 'learning' AND table_name = 'model_registry')",
    )
    .fetch_optional(&pool)
    .await
    .unwrap();
    if !app_schema_present.unwrap_or(false) || canary_present.unwrap_or(false) {
        eprintln!(
            "SKIP: ambiguous-state precondition not met (app_schema={:?}, canary={:?})",
            app_schema_present, canary_present
        );
        return;
    }

    let migrations_dir = srv_root().join(MIGRATIONS_DIR_REL);
    let migrations = load_migrations_from_dir(&migrations_dir).expect("load migrations");
    let err = ensure_legacy_seeded(&pool, &migrations).await.unwrap_err();
    matches!(err, MigrationsError::LegacySeedRefused);
}

// ─────────────────────────────────────────────────────────────────
// 4) Fresh-DB happy path — destructive, so gated behind
//    OPENCLAW_TEST_PG_DESTRUCTIVE=1 as an explicit operator ack.
//    After drop, run_if_enabled with flag=1 should apply V001-V023 end-to-end.
// 4) 全新 DB Happy Path — 破壞性，加 OPENCLAW_TEST_PG_DESTRUCTIVE=1 ack。
// ─────────────────────────────────────────────────────────────────
#[tokio::test]
async fn fresh_db_applies_all_migrations_end_to_end() {
    if std::env::var("OPENCLAW_TEST_PG_DESTRUCTIVE")
        .ok()
        .as_deref()
        != Some("1")
    {
        eprintln!("SKIP: OPENCLAW_TEST_PG_DESTRUCTIVE not set (destructive test)");
        return;
    }
    let Some(pool) = maybe_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };

    // Destructive: drop everything.
    // 破壞性：清光。
    wipe_app_schemas(&pool).await;
    reset_tracking(&pool).await;

    std::env::set_var(AUTO_MIGRATE_ENV_VAR, "1");
    let outcome = MigrationRunner::run_if_enabled(Some(&pool), &srv_root())
        .await
        .expect("fresh-DB migrate");
    std::env::remove_var(AUTO_MIGRATE_ENV_VAR);

    // Expect real applied rows, no legacy seed.
    // 預期真實套用、無 legacy seed。
    match outcome {
        RunOutcome::Applied(n) => {
            assert!(n >= 22, "expected ≥22 applied, got {n}");
        }
        other => panic!("expected RunOutcome::Applied, got {other:?}"),
    }

    let versions = list_applied_versions(&pool).await.unwrap();
    assert!(versions.contains(&1));
    assert!(versions.contains(&23));
    assert!(!versions.contains(&999));
}

// ─────────────────────────────────────────────────────────────────
// 5) Idempotency: run twice against a fully-tracked DB → second run is
//    RunOutcome::NoOp (no new rows, no errors).
// 5) 冪等：全量 tracked 時第二次跑需 NoOp（無新行、無錯）。
// ─────────────────────────────────────────────────────────────────
#[tokio::test]
async fn second_run_is_noop() {
    let Some(pool) = maybe_pool().await else {
        eprintln!("SKIP: OPENCLAW_TEST_PG not set");
        return;
    };

    // Pre-req mirrors test #2: canary present and tracking seedable.
    // 前提同 test #2：canary 已在。
    let canary_exists: Option<bool> = sqlx::query_scalar(
        "SELECT EXISTS (SELECT 1 FROM information_schema.tables \
         WHERE table_schema = 'learning' AND table_name = 'model_registry')",
    )
    .fetch_optional(&pool)
    .await
    .unwrap();
    if !canary_exists.unwrap_or(false) {
        eprintln!("SKIP: canary absent");
        return;
    }

    reset_tracking(&pool).await;

    std::env::set_var(AUTO_MIGRATE_ENV_VAR, "1");
    // First run seeds legacy rows / 第一次 seed
    let first = MigrationRunner::run_if_enabled(Some(&pool), &srv_root())
        .await
        .expect("first run");
    // Could be SeededAndApplied{seeded=22, applied=0} or similar.
    // 可能是 SeededAndApplied{seeded=22, applied=0}。
    assert!(
        matches!(
            first,
            RunOutcome::SeededAndApplied { .. } | RunOutcome::Applied(_) | RunOutcome::NoOp
        ),
        "unexpected first-run outcome: {first:?}"
    );

    // Second run: tracking already populated → pure NoOp.
    // 第二次：tracking 已滿 → 純 NoOp。
    let second = MigrationRunner::run_if_enabled(Some(&pool), &srv_root())
        .await
        .expect("second run");
    std::env::remove_var(AUTO_MIGRATE_ENV_VAR);
    assert_eq!(second, RunOutcome::NoOp, "second run must be NoOp");
}
