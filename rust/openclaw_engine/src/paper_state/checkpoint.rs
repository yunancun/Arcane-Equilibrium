//! P1-5 A2: `trading.paper_state_checkpoint` — cross-restart drawdown continuity.
//! P1-5 A2：`trading.paper_state_checkpoint` — 跨重啟 drawdown 連續性。
//!
//! MODULE_NOTE (EN): Thin async I/O layer around the V018 schema. Exposes three
//!   free functions so callers (reader = boot-time restore; writer = 30s state
//!   writer cycle; reset = IPC handler) don't need to touch `PaperState`'s
//!   internals. The table is keyed by `engine_mode`, so paper / demo / live /
//!   live_demo each own one row max — no hypertable, no time dimension.
//!
//!   All three functions log + propagate `sqlx::Error` so callers can decide
//!   the fail-soft policy (reader logs + continues; writer skips one cycle;
//!   IPC returns error to operator). None of them touch `PaperState` — the
//!   caller is responsible for pairing DB writes with the in-memory setters
//!   (`restore_checkpoint`, `reset_drawdown_baseline`).
//!
//!   Violating Root Principle #5 (生存>利潤): if this module's writer silently
//!   fails for hours, peak_balance reverts to balance-on-restart and drawdown
//!   breach circuit breaker becomes a no-op across restarts — hence the logs
//!   are WARN level, not TRACE, even on the writer hot path.
//!
//! MODULE_NOTE (中): V018 表的薄 async I/O 層。暴露三個自由函式，呼叫者（啟動
//!   還原 / 30s 週期寫入 / IPC reset）不需碰 PaperState 內部。表以 engine_mode
//!   為主鍵，paper/demo/live/live_demo 各最多 1 row，非 hypertable、無 time
//!   維度。三個函式都 log + 向上拋 sqlx::Error，由呼叫者決定 fail-soft 策略。
//!
//!   違反根原則 #5（生存>利潤）的風險：若寫入端靜默失敗數小時，重啟後
//!   peak_balance 會退化為當下 balance，跨重啟 drawdown 斷路器失效 —
//!   因此 writer 失敗用 WARN 不是 TRACE，確保 operator 看得見。

use sqlx::PgPool;
use tracing::{debug, warn};

/// EN: Load the single checkpoint row for `engine_mode`. Returns `Ok(None)`
///     when no row exists (cold start or post-reset) so the caller can treat
///     it as "first session" and keep `peak_balance = balance`. `Ok(Some(...))`
///     means a prior session's peak survived and should be re-applied via
///     `PaperState::restore_checkpoint`.
///
/// Columns returned:
/// - `peak_balance` — f64 (DOUBLE PRECISION; the PK engine_mode check
///   constraint guarantees non-negative).
/// - `session_start_ts` — converted to Unix-epoch milliseconds. Postgres
///   `TIMESTAMPTZ` epoch wraps well past 2262, so the saturating `i64`→`u64`
///   cast is safe for the entire supported range.
///
/// 中文: 載入 `engine_mode` 的 checkpoint row。Ok(None) 表無 row（冷啟動或
///       reset 後），呼叫者視為「首次 session」；Ok(Some(...)) 則由
///       `PaperState::restore_checkpoint` 套用。peak_balance 與 session_start_ts
///       （轉 Unix epoch 毫秒）一同返回。
pub(crate) async fn load_checkpoint(
    pool: &PgPool,
    engine_mode: &str,
) -> Result<Option<(f64, u64)>, sqlx::Error> {
    // TIMESTAMPTZ → ms: `EXTRACT(EPOCH FROM ...)::bigint * 1000` would lose
    // sub-second precision; use `(EXTRACT(EPOCH FROM ...) * 1000)::bigint`.
    // 用 EXTRACT(EPOCH)*1000 轉毫秒以保留亞秒精度。
    let row: Option<(f64, i64)> = sqlx::query_as(
        "SELECT peak_balance::float8 AS peak, \
                (EXTRACT(EPOCH FROM session_start_ts) * 1000)::bigint AS session_start_ms \
         FROM trading.paper_state_checkpoint \
         WHERE engine_mode = $1",
    )
    .bind(engine_mode)
    .fetch_optional(pool)
    .await?;

    Ok(row.map(|(peak, ts_ms)| {
        let ts_u64 = if ts_ms < 0 { 0 } else { ts_ms as u64 };
        (peak, ts_u64)
    }))
}

/// EN: UPSERT the current peak + session-start for `engine_mode`. `updated_at`
///     rides on the default `NOW()`. Called from the 30s state-writer cycle;
///     an occasional failure is logged but not fatal — the next tick retries.
///     `peak_balance < 0` is rejected outright to match the table's CHECK
///     constraint (avoids a round-trip just to hit a PG violation).
///
/// 中文: 將當前 peak + session_start UPSERT 入 `engine_mode` 那行。30s
///       狀態寫入週期呼叫；偶發失敗 WARN log 但不致命，下個 tick 重試。
///       peak_balance<0 直接拒絕，對齊表 CHECK 約束避免無謂 DB round-trip。
pub(crate) async fn write_checkpoint(
    pool: &PgPool,
    engine_mode: &str,
    peak_balance: f64,
    session_start_ts_ms: u64,
) -> Result<(), sqlx::Error> {
    if !peak_balance.is_finite() || peak_balance < 0.0 {
        // Don't round-trip a row that will violate CHECK. Log + skip.
        // 不要回傳會違反 CHECK 的 row；log 後跳過。
        warn!(
            engine_mode,
            peak_balance, "P1-5 A2: refuse to checkpoint non-finite / negative peak"
        );
        return Ok(());
    }
    // Milliseconds → TIMESTAMPTZ via to_timestamp($3 / 1000.0). `::bigint /
    // 1000.0` keeps the fraction so sub-second precision survives the round-trip.
    // ms → TIMESTAMPTZ：to_timestamp 保留亞秒精度。
    sqlx::query(
        "INSERT INTO trading.paper_state_checkpoint \
            (engine_mode, peak_balance, session_start_ts, updated_at) \
         VALUES ($1, $2, to_timestamp($3::bigint / 1000.0), NOW()) \
         ON CONFLICT (engine_mode) DO UPDATE SET \
            peak_balance     = EXCLUDED.peak_balance, \
            session_start_ts = EXCLUDED.session_start_ts, \
            updated_at       = NOW()",
    )
    .bind(engine_mode)
    .bind(peak_balance)
    .bind(session_start_ts_ms as i64)
    .execute(pool)
    .await?;
    debug!(
        engine_mode, peak_balance, session_start_ts_ms,
        "P1-5 A2: checkpoint UPSERT / 已持久化"
    );
    Ok(())
}

/// EN: DELETE the checkpoint row for `engine_mode` — the DB side of an
///     operator-driven `reset_drawdown_baseline`. After the IPC handler calls
///     `PaperState::reset_drawdown_baseline()` in-memory, this removes the
///     persisted row so the next restart won't resurrect the old peak.
///     Returns Ok even if no row existed (DELETE is idempotent).
///
/// 中文: 刪除 `engine_mode` 的 checkpoint row — IPC reset_drawdown_baseline 的
///       DB 側。記憶體重置後呼叫本函式，避免下次重啟復活舊 peak。無 row 時
///       也回 Ok（DELETE 冪等）。
pub(crate) async fn delete_checkpoint(
    pool: &PgPool,
    engine_mode: &str,
) -> Result<(), sqlx::Error> {
    sqlx::query("DELETE FROM trading.paper_state_checkpoint WHERE engine_mode = $1")
        .bind(engine_mode)
        .execute(pool)
        .await?;
    debug!(engine_mode, "P1-5 A2: checkpoint row DELETED / 已刪除 checkpoint row");
    Ok(())
}
