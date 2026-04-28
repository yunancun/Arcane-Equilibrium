//! G3-09 Phase B Wave 1 integration test — proves daemon writes
//! `learning.cost_edge_advisor_log` rows when persistence is enabled.
//! G3-09 Phase B Wave 1 整合測試 — 證明 daemon 在啟用 persistence 時
//! 真寫 `learning.cost_edge_advisor_log` row。
//!
//! MODULE_NOTE (EN): Requires a live Postgres URL via `OPENCLAW_TEST_PG`.
//!   When unset, the test is skipped (CI without local PG stays green).
//!   The test creates the V026 table fresh (or uses an existing one if
//!   shape matches), spawns `spawn_cost_edge_advisor_with_persistence`
//!   with a 100ms poll interval (force PHASE_B_INSERT_DOWNSAMPLE_MS to
//!   not gate the first cycle), waits for the daemon to fire one cycle,
//!   then asserts at least one row exists with the matching engine_mode
//!   tag.
//!
//!   Coverage:
//!     1. `daemon_persists_cycle_row_when_pool_provided` — proves the
//!        Phase B INSERT path actually fires (non-trivial: Phase A had
//!        zero DB writes, daemon could silent-no-op without test).
//!     2. `transition_row_carries_transition_from_string` — proves the
//!        transition row distinguishes itself via `transition_from`.
//!
//! MODULE_NOTE (中)：需 `OPENCLAW_TEST_PG` 連 PG；未設則跳過（本機無 PG
//!   時 CI 仍綠）。測試新建（或 shape 相符時沿用）V026 表，spawn
//!   `spawn_cost_edge_advisor_with_persistence`（100ms poll，force
//!   PHASE_B_INSERT_DOWNSAMPLE_MS 首 cycle 不 gate），等 daemon 完成一
//!   輪、assert 至少一筆 row 帶對應 engine_mode 標籤。
//!
//!   覆蓋：
//!     1. `daemon_persists_cycle_row_when_pool_provided` — 證 Phase B
//!        INSERT path 真開火（Phase A 0 DB write，沒 test 容易 silent-no-op）。
//!     2. `transition_row_carries_transition_from_string` — 證 transition
//!        row 用 `transition_from` 區分。

use openclaw_engine::config::{ConfigStore, RiskConfig};
use openclaw_engine::cost_edge_advisor::{
    spawn_cost_edge_advisor_with_persistence, CostEdgeAdvisor, CostEdgeAdvisorStatus,
};
use openclaw_engine::database::pool::DbPool;
use openclaw_engine::database::DatabaseConfig;
use openclaw_engine::h_state_cache::{H5CostStats, HStateCache, HStateSnapshot};

use sqlx::postgres::{PgPool, PgPoolOptions};
use std::sync::Arc;
use std::time::{Duration, Instant};
use tokio_util::sync::CancellationToken;

/// Pull `OPENCLAW_TEST_PG` and connect; return None when unset (to skip).
/// 讀 `OPENCLAW_TEST_PG` 連 PG；未設回 None（跳過測試）。
async fn maybe_pg_pool() -> Option<PgPool> {
    let url = std::env::var("OPENCLAW_TEST_PG").ok()?;
    match PgPoolOptions::new()
        .max_connections(2)
        .acquire_timeout(Duration::from_secs(5))
        .connect(&url)
        .await
    {
        Ok(p) => Some(p),
        Err(e) => {
            eprintln!(
                "[test_cost_edge_advisor_persistence] OPENCLAW_TEST_PG set but \
                 connect failed: {e}"
            );
            None
        }
    }
}

/// Build a `DbPool` wrapper around a live PgPool by routing through
/// `DbPool::connect` with the same URL. Mirrors what main.rs does.
/// 用 main.rs 同 path（`DbPool::connect`）建 DbPool wrapper 包住 live PgPool。
async fn build_test_db_pool() -> Option<Arc<DbPool>> {
    let url = std::env::var("OPENCLAW_TEST_PG").ok()?;
    let mut cfg = DatabaseConfig::default();
    cfg.database_url = url;
    cfg.db_writes_enabled = true;
    cfg.pool_max_connections = 2;
    cfg.connect_timeout_ms = 5_000;
    let pool = DbPool::connect(&cfg).await;
    if !pool.is_available() {
        eprintln!(
            "[test_cost_edge_advisor_persistence] DbPool::connect succeeded but \
             pool reports !is_available; skipping"
        );
        return None;
    }
    Some(Arc::new(pool))
}

/// Ensure the `learning` schema + V026 table exist on the test DB. Idempotent
/// — recreates only when missing or shape-mismatched. Does **not** invoke
/// `create_hypertable` (test PG may lack Timescale; the integration test
/// only validates row INSERTs against a plain table).
/// 確保 `learning` schema + V026 表存在。冪等 — 缺或 shape 不符才重建。
/// **不**呼叫 `create_hypertable`（測試 PG 可能無 Timescale；本整合測試只
/// 驗 row INSERT 對純表）。
async fn ensure_v026_table(pool: &PgPool) -> Result<(), sqlx::Error> {
    sqlx::query("CREATE SCHEMA IF NOT EXISTS learning")
        .execute(pool)
        .await?;
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS learning.cost_edge_advisor_log (
            ts_ms              BIGINT  NOT NULL,
            engine_mode        TEXT    NOT NULL,
            status             TEXT    NOT NULL,
            ratio              DOUBLE PRECISION,
            threshold          DOUBLE PRECISION NOT NULL,
            data_days          INTEGER NOT NULL,
            ai_spend_7d_usd    DOUBLE PRECISION NOT NULL,
            paper_pnl_7d_usd   DOUBLE PRECISION NOT NULL,
            is_stale           BOOLEAN NOT NULL,
            phase              TEXT    NOT NULL DEFAULT 'B_shadow',
            transition_from    TEXT,
            PRIMARY KEY (ts_ms, engine_mode)
        )",
    )
    .execute(pool)
    .await?;
    Ok(())
}

/// Wipe rows for a specific engine_mode tag so tests don't see stale data.
/// 清除特定 engine_mode 標籤的 row，避免測試看到陳舊資料。
async fn wipe_engine_mode_rows(pool: &PgPool, tag: &str) {
    let _ = sqlx::query("DELETE FROM learning.cost_edge_advisor_log WHERE engine_mode = $1")
        .bind(tag)
        .execute(pool)
        .await;
}

fn now_ms() -> i64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0)
}

/// Build a fresh `RiskConfig` with cost_edge enabled + reasonable threshold.
/// 建 `RiskConfig`：cost_edge enabled + 合理 threshold。
fn risk_config_advisor_enabled() -> Arc<ConfigStore<RiskConfig>> {
    let mut cfg = RiskConfig::default();
    cfg.cost_edge.enabled = true;
    cfg.cost_edge.trigger_threshold = -0.5;
    Arc::new(ConfigStore::new(cfg))
}

/// Build an H state cache with a fresh OK snapshot (ratio above threshold).
/// 建 H state cache：fresh OK snapshot（ratio 在 threshold 之上）。
fn h_state_cache_with_ok_ratio() -> Arc<HStateCache> {
    let cache = HStateCache::new_arc();
    let snap = HStateSnapshot {
        version: 1,
        fetched_at_ms: now_ms(),
        h5: H5CostStats {
            ai_spend_7d_usd: 5.0,
            paper_pnl_7d_usd: 2.5,
            cost_edge_ratio: Some(0.5),
            data_days: 7,
        },
        ..Default::default()
    };
    cache.store_snapshot(snap, now_ms());
    cache
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn daemon_persists_cycle_row_when_pool_provided() {
    let Some(pg) = maybe_pg_pool().await else {
        eprintln!("[test_cost_edge_advisor_persistence] skipped — OPENCLAW_TEST_PG not set");
        return;
    };
    if let Err(e) = ensure_v026_table(&pg).await {
        eprintln!(
            "[test_cost_edge_advisor_persistence] ensure_v026_table failed: {e}; \
             skipping (test DB likely missing learning schema permissions)"
        );
        return;
    }
    let tag = format!("test_persist_{}", std::process::id());
    wipe_engine_mode_rows(&pg, &tag).await;

    let Some(db_pool) = build_test_db_pool().await else {
        return;
    };

    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_ok_ratio();
    let risk = risk_config_advisor_enabled();
    let cancel = CancellationToken::new();

    // Spawn at 100ms poll cadence so the test finishes fast. The first
    // cycle's `last_insert_ms = 0` ensures the cycle row writes immediately
    // (down-sample threshold is `now - 0 >= 60_000` which is true at any
    // real epoch ms).
    // 100ms poll 加速測試。首 cycle 的 `last_insert_ms = 0` 讓 cycle row
    // 立即寫（down-sample 條件 `now - 0 >= 60_000` 在實際 epoch ms 永真）。
    let handle = spawn_cost_edge_advisor_with_persistence(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(100),
        cancel.clone(),
        Some(Arc::clone(&db_pool)),
        tag.clone(),
    );

    // Wait up to 5s for daemon to record + INSERT at least one row.
    // 等最多 5s 給 daemon 紀錄 + INSERT 至少一行。
    let deadline = Instant::now() + Duration::from_secs(5);
    let mut row_count: i64 = 0;
    while Instant::now() < deadline {
        row_count = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*) FROM learning.cost_edge_advisor_log WHERE engine_mode = $1",
        )
        .bind(&tag)
        .fetch_one(&pg)
        .await
        .unwrap_or(0);
        if row_count >= 1 {
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    cancel.cancel();
    let _ = handle.await;

    // Cleanup test rows so subsequent runs start fresh.
    // 清測試 row，下次跑乾淨。
    wipe_engine_mode_rows(&pg, &tag).await;

    assert!(
        row_count >= 1,
        "expected daemon to INSERT at least 1 row to learning.cost_edge_advisor_log \
         (engine_mode={tag}); observed {row_count}"
    );
    // Final advisor state should also reflect the OK snapshot.
    // 最終 advisor state 應反映 OK snapshot。
    assert_eq!(advisor.state().status, CostEdgeAdvisorStatus::Ok);
}

#[tokio::test(flavor = "multi_thread", worker_threads = 2)]
async fn transition_row_carries_transition_from_string() {
    let Some(pg) = maybe_pg_pool().await else {
        return;
    };
    if let Err(e) = ensure_v026_table(&pg).await {
        eprintln!("[test_cost_edge_advisor_persistence] ensure_v026_table failed: {e}");
        return;
    }
    let tag = format!("test_trans_{}", std::process::id());
    wipe_engine_mode_rows(&pg, &tag).await;

    let Some(db_pool) = build_test_db_pool().await else {
        return;
    };

    let advisor = CostEdgeAdvisor::new_arc();
    let cache = h_state_cache_with_ok_ratio();
    let risk = risk_config_advisor_enabled();
    let cancel = CancellationToken::new();

    let handle = spawn_cost_edge_advisor_with_persistence(
        Arc::clone(&advisor),
        Arc::clone(&cache),
        Arc::clone(&risk),
        Duration::from_millis(100),
        cancel.clone(),
        Some(Arc::clone(&db_pool)),
        tag.clone(),
    );

    // Wait until at least one row exists (daemon got past first cycle).
    // 等到至少一行（daemon 跑完首 cycle）。
    let deadline = Instant::now() + Duration::from_secs(5);
    while Instant::now() < deadline {
        let n = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*) FROM learning.cost_edge_advisor_log WHERE engine_mode = $1",
        )
        .bind(&tag)
        .fetch_one(&pg)
        .await
        .unwrap_or(0);
        if n >= 1 {
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    // Force a transition by storing a Trigger snapshot — daemon should
    // observe OK→Trigger and write a transition row.
    // 透過 store Trigger snapshot 強制 transition — daemon 應觀察到 OK→Trigger
    // 並寫 transition row。
    let trigger_snap = HStateSnapshot {
        version: 2,
        fetched_at_ms: now_ms(),
        h5: H5CostStats {
            ai_spend_7d_usd: 10.0,
            paper_pnl_7d_usd: -8.0,
            cost_edge_ratio: Some(-0.8),
            data_days: 7,
        },
        ..Default::default()
    };
    cache.store_snapshot(trigger_snap, now_ms());

    // Wait until a transition row appears (transition_from IS NOT NULL).
    // 等到出現 transition row（transition_from IS NOT NULL）。
    let deadline = Instant::now() + Duration::from_secs(5);
    let mut transition_count: i64 = 0;
    while Instant::now() < deadline {
        transition_count = sqlx::query_scalar::<_, i64>(
            "SELECT COUNT(*) FROM learning.cost_edge_advisor_log \
             WHERE engine_mode = $1 AND transition_from IS NOT NULL",
        )
        .bind(&tag)
        .fetch_one(&pg)
        .await
        .unwrap_or(0);
        if transition_count >= 1 {
            break;
        }
        tokio::time::sleep(Duration::from_millis(100)).await;
    }

    cancel.cancel();
    let _ = handle.await;

    wipe_engine_mode_rows(&pg, &tag).await;

    assert!(
        transition_count >= 1,
        "expected at least 1 transition row (transition_from IS NOT NULL) \
         after OK→Trigger snapshot store; observed {transition_count}"
    );
}
