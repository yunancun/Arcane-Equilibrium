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
//!   hard-fail），再用既有 public API `MigrationRunner::run_if_enabled` 對 ephemeral PG
//!   跑真 V001-V139 全樹（`OPENCLAW_AUTO_MIGRATE=1`），最後逐表開 transaction、INSERT/SELECT
//!   後 ROLLBACK（不留 row）。沿用 migrations_test.rs 的 maybe_pool() / srv_root()
//!   模式與 `OPENCLAW_TEST_PG` env gate：未設則 SKIP（本機 `cargo test` 仍綠），CI
//!   會設 → 真跑。
//!
//!   已知 BLOCKER（PA/PM follow-up，非本檔可解）：除 V005 外，migration 樹對
//!   `learning.model_registry` 另有一條 brownfield-only 矛盾——V004:135 建舊 shape stub、
//!   V005:168 建 `is_active` 索引（依賴舊欄位）、V023:67 schema_guard A 又要求新欄位否則
//!   RAISE；且 run_if_enabled 的 legacy-seed canary 正是「model_registry 是否存在」，故
//!   任何 pre-seed model_registry 都會反觸發 V001-V023 被 seed-skip（schema 不建全）→
//!   V024 guard 連鎖炸。此矛盾**無法在 test-precondition 層解**，需 PA 以 migration-hygiene
//!   收（V023 guard 改 repair-not-raise / V005 索引加 column-exists 守衛 / V004 stub 對齊），
//!   在此之前對 **virgin** ephemeral DB 全樹仍會在 ordinal 23/24 fail。
//!
//!   邊界：**切勿**指向帶真實資料的 DB——測試會跑 migration 全樹建 schema；且本檔
//!   會在隔離 transaction 內 INSERT 後 ROLLBACK，雖不 commit，仍不可指向 prod。
//!   本檔不覆蓋 V037 類 REVOKE PUBLIC INSERT 的 permission 面（CI 單一 superuser
//!   role，GRANT/REVOKE 分支不真 fire，與 prod role-absent NOTICE 路一致）。

use openclaw_engine::database::migrations::{
    MigrationRunner, RunOutcome, AUTO_MIGRATE_ENV_VAR,
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

/// 用 OPENCLAW_TEST_PG 建 pool；未設回 None 由呼叫端 SKIP（與 migrations_test.rs 同）。
/// Build a Postgres pool from OPENCLAW_TEST_PG. Returns None if unset.
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
            eprintln!("[schema_contract_test] OPENCLAW_TEST_PG set but connect failed: {e}");
            None
        }
    }
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
/// 在 migration ordinal 5 hard-fail（V001-V139 全樹掛在這裡，6 個契約 probe 一個都跑不到）。
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

/// 對 ephemeral PG 跑真 V001-V139 全樹後回 pool；未設 env 回 None（呼叫端 SKIP）。
/// Apply the full V001-V139 tree to an ephemeral PG, then return the pool.
///
/// 為什麼要在這裡跑 migration：契約測試必須對「migration 宣告的真實 schema」斷言，
/// 而非對手寫 fixture——否則 fixture 與 migration drift 時測試會 silent 假綠。
async fn migrated_pool() -> Option<PgPool> {
    let pool = maybe_pool().await?;
    // 先種 V005 brownfield 前置（見 seed_legacy_precondition），否則全樹在 ordinal 5 掛。
    // 對已 migrate 過的 DB 是 no-op（CREATE TABLE IF NOT EXISTS / 表早已 rename 走）。
    seed_legacy_precondition(&pool).await;
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
        Err(e) => panic!("V001-V139 full-tree apply failed: {e}"),
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
    assert!(row.is_none(), "fresh DB unexpectedly returned a registry row");
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
    assert!(close.is_none(), "fresh DB unexpectedly returned a kline row");
}
