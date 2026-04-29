//! Decision outcome backfill writer — FIX-34.
//! 決策結果回填寫入器 — FIX-34。
//!
//! MODULE_NOTE (EN): Periodic task that scans `trading.decision_context_snapshots`
//!   for rows with `outcome_backfilled = FALSE` and `ts` older than 25 hours,
//!   computes 1m/5m/1h/4h/24h return windows from `market.klines`, and writes
//!   results to `trading.decision_outcomes`. Runs every 5 minutes.
//!   Graceful degradation: if PG pool is unavailable, logs warning and skips.
//! MODULE_NOTE (中): 定期任務，掃描 `trading.decision_context_snapshots` 中
//!   `outcome_backfilled = FALSE` 且 `ts` 超過 25 小時的行，
//!   從 `market.klines` 計算 1m/5m/1h/4h/24h 回報窗口，
//!   寫入 `trading.decision_outcomes`。每 5 分鐘運行。
//!   優雅降級：PG pool 不可用時記錄警告並跳過。

use super::pool::DbPool;
use tracing::{debug, info, warn};

/// Maximum rows to process per backfill cycle.
/// 每次回填週期處理的最大行數。
const BATCH_SIZE: i64 = 200;

/// Backfill SQL (exposed as a const for unit-test regression guards).
///
/// Uses `market.klines.timeframe` values `'1m' / '5m' / '1h' / '4h'` (storage
/// format written by the kline ingestor), NOT Bybit API interval codes
/// (`'1' / '5' / '60' / '240'`). Historical bug where this used API codes
/// produced 100% NULL outcome_* — see TODO OUTCOME-BACKFILL-JOIN-NULL-1.
///
/// `engine_mode` is pulled from `decision_context_snapshots` and inserted
/// explicitly; omitting it triggers the schema default `'paper'` regardless
/// of actual mode — see TODO DECISION-OUTCOMES-ENGINE-MODE-TAG-BUG-1.
///
/// 回填 SQL（作為 const 以供單元測試回歸防護引用）。
/// 使用 `market.klines.timeframe` 儲存格式 `'1m'/'5m'/'1h'/'4h'`，
/// 非 Bybit API interval 代碼 `'1'/'5'/'60'/'240'`。
/// `engine_mode` 顯式從 snapshots CTE 帶入；省略會觸發 schema default `'paper'`。
pub(crate) const BACKFILL_SQL: &str = r#"
WITH pending AS (
    SELECT context_id, ts, symbol, last_price, engine_mode
    FROM trading.decision_context_snapshots
    WHERE outcome_backfilled = FALSE
      AND last_price IS NOT NULL
      AND last_price > 0
      AND ts < NOW() - INTERVAL '25 hours'
    ORDER BY ts ASC
    LIMIT $1
),
outcomes AS (
    SELECT
        p.context_id,
        p.last_price,
        p.engine_mode,
        -- 1m return / 1 分鐘回報
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '1m'
           AND k.ts >= p.ts + INTERVAL '1 minute'
         ORDER BY k.ts ASC LIMIT 1) AS price_1m,
        -- 5m return / 5 分鐘回報
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '5m'
           AND k.ts >= p.ts + INTERVAL '5 minutes'
         ORDER BY k.ts ASC LIMIT 1) AS price_5m,
        -- 1h return / 1 小時回報
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '1h'
           AND k.ts >= p.ts + INTERVAL '1 hour'
         ORDER BY k.ts ASC LIMIT 1) AS price_1h,
        -- 4h return / 4 小時回報
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '4h'
           AND k.ts >= p.ts + INTERVAL '4 hours'
         ORDER BY k.ts ASC LIMIT 1) AS price_4h,
        -- 24h return (4h kline, ±4h precision) / 24 小時回報（4h 框架，精度 ±4h）
        (SELECT k.close FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '4h'
           AND k.ts >= p.ts + INTERVAL '24 hours'
         ORDER BY k.ts ASC LIMIT 1) AS price_24h,
        -- Max favorable excursion (highest high in 24h) / 最大有利偏移
        (SELECT MAX(k.high) FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '1m'
           AND k.ts > p.ts AND k.ts <= p.ts + INTERVAL '24 hours'
        ) AS max_high_24h,
        -- Max adverse excursion (lowest low in 24h) / 最大不利偏移
        (SELECT MIN(k.low) FROM market.klines k
         WHERE k.symbol = p.symbol AND k.timeframe = '1m'
           AND k.ts > p.ts AND k.ts <= p.ts + INTERVAL '24 hours'
        ) AS min_low_24h
    FROM pending p
),
inserted AS (
    INSERT INTO trading.decision_outcomes
        (context_id, outcome_1m, outcome_5m, outcome_1h, outcome_4h, outcome_24h,
         max_favorable, max_adverse, backfilled_ts, engine_mode)
    SELECT
        o.context_id,
        (o.price_1m  - o.last_price) / o.last_price,
        (o.price_5m  - o.last_price) / o.last_price,
        (o.price_1h  - o.last_price) / o.last_price,
        (o.price_4h  - o.last_price) / o.last_price,
        (o.price_24h - o.last_price) / o.last_price,
        (o.max_high_24h - o.last_price) / o.last_price,
        (o.min_low_24h  - o.last_price) / o.last_price,
        NOW(),
        o.engine_mode
    FROM outcomes o
    ON CONFLICT (context_id) DO NOTHING
    RETURNING context_id
)
-- Step 2: Mark contexts as backfilled / 步驟 2：標記上下文已回填
UPDATE trading.decision_context_snapshots
SET outcome_backfilled = TRUE
WHERE context_id IN (SELECT context_id FROM inserted)
"#;

/// Run one backfill cycle: find pending contexts → compute outcomes → write.
/// 執行一次回填週期：查找待處理上下文 → 計算結果 → 寫入。
pub async fn run_backfill_cycle(pool: &DbPool) -> Result<u64, String> {
    let pg = match pool.get() {
        Some(p) => p,
        None => return Err("PG pool unavailable / PG 連接池不可用".into()),
    };

    // Execute the single-statement CTE chain. All windows (1m/5m/1h/4h/24h +
    // MFE/MAE) are computed in one pass; `engine_mode` is propagated from
    // `decision_context_snapshots`.
    // 在單一 SQL 語句中計算所有窗口（1m/5m/1h/4h/24h + 最大有利/不利偏移）；
    // `engine_mode` 從 `decision_context_snapshots` 傳遞。
    let rows_affected = sqlx::query(BACKFILL_SQL)
        .bind(BATCH_SIZE)
        .execute(&*pg)
        .await
        .map_err(|e| format!("backfill query failed: {e}"))?
        .rows_affected();

    Ok(rows_affected)
}

/// Spawn the periodic outcome backfill task.
/// 啟動定期結果回填任務。
pub async fn run_backfill_loop(
    pool: std::sync::Arc<DbPool>,
    cancel: tokio_util::sync::CancellationToken,
) {
    let mut interval = tokio::time::interval(std::time::Duration::from_secs(300)); // 5 min
    interval.tick().await; // skip immediate tick

    info!("outcome backfill task started (5min interval) / 結果回填任務已啟動（5 分鐘間隔）");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                info!("outcome backfill task stopping (cancel) / 結果回填任務停止");
                break;
            }
            _ = interval.tick() => {
                match run_backfill_cycle(&*pool).await {
                    Ok(0) => debug!("outcome backfill: no pending rows / 無待回填行"),
                    Ok(n) => info!(rows = n, "outcome backfill completed / 結果回填完成"),
                    Err(e) => warn!(error = %e, "outcome backfill failed / 結果回填失敗"),
                }
            }
        }
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
//
// SQL regression guards. We can't hit a live PG from `cargo test --lib`, so
// we assert the shape of the SQL string. This catches both historical bugs
// (OUTCOME-BACKFILL-JOIN-NULL-1 timeframe format, DECISION-OUTCOMES-ENGINE-
// MODE-TAG-BUG-1 missing column) if anyone re-introduces them.
//
// SQL 回歸防護。`cargo test --lib` 無法連 PG，以字串斷言檢查 SQL 形狀，
// 防止歷史 bug（timeframe 格式、engine_mode 缺欄）重新引入。
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::BACKFILL_SQL;

    /// OUTCOME-BACKFILL-JOIN-NULL-1 regression: timeframe literals must match
    /// `market.klines` storage format (`1m/5m/1h/4h`), not Bybit API codes
    /// (`1/5/60/240`). If someone swaps back to API codes every LATERAL
    /// subquery returns NULL.
    /// 歷史 bug：timeframe 需與 kline 儲存格式一致；用 API 碼 → 100% NULL。
    #[test]
    fn sql_uses_klines_timeframe_storage_format() {
        assert!(
            BACKFILL_SQL.contains("k.timeframe = '1m'"),
            "SQL must use k.timeframe = '1m' (not '1')"
        );
        assert!(
            BACKFILL_SQL.contains("k.timeframe = '5m'"),
            "SQL must use k.timeframe = '5m' (not '5')"
        );
        assert!(
            BACKFILL_SQL.contains("k.timeframe = '1h'"),
            "SQL must use k.timeframe = '1h' (not '60')"
        );
        assert!(
            BACKFILL_SQL.contains("k.timeframe = '4h'"),
            "SQL must use k.timeframe = '4h' (not '240')"
        );

        // Buggy literals must NOT appear — these produce 100% NULL outcomes.
        // 錯誤字面值不可出現——會造成 100% NULL outcome。
        assert!(
            !BACKFILL_SQL.contains("k.timeframe = '1'"),
            "buggy '1' literal must not reappear"
        );
        assert!(
            !BACKFILL_SQL.contains("k.timeframe = '5'"),
            "buggy '5' literal must not reappear"
        );
        assert!(
            !BACKFILL_SQL.contains("k.timeframe = '60'"),
            "buggy '60' literal must not reappear"
        );
        assert!(
            !BACKFILL_SQL.contains("k.timeframe = '240'"),
            "buggy '240' literal must not reappear"
        );
    }

    /// DECISION-OUTCOMES-ENGINE-MODE-TAG-BUG-1 regression: `engine_mode` must
    /// be propagated from the pending CTE into the INSERT so the schema
    /// default `'paper'` is overridden.
    /// 歷史 bug：INSERT 省略 engine_mode → schema default 'paper' 覆蓋實際值。
    #[test]
    fn sql_propagates_engine_mode_into_insert() {
        // pending CTE must carry engine_mode from snapshots.
        // pending CTE 必須帶 engine_mode 出來。
        assert!(
            BACKFILL_SQL.contains("SELECT context_id, ts, symbol, last_price, engine_mode"),
            "pending CTE must select engine_mode from snapshots"
        );

        // outcomes CTE must project engine_mode forward.
        // outcomes CTE 必須轉發 engine_mode。
        assert!(
            BACKFILL_SQL.contains("p.engine_mode,"),
            "outcomes CTE must carry p.engine_mode"
        );

        // INSERT column list must include engine_mode as the last column.
        // INSERT 欄位列尾必須含 engine_mode。
        assert!(
            BACKFILL_SQL.contains("backfilled_ts, engine_mode)"),
            "INSERT column list must end with `backfilled_ts, engine_mode)`"
        );

        // INSERT SELECT must write o.engine_mode (not omit → schema default).
        // INSERT SELECT 必須寫 o.engine_mode，不可省略。
        assert!(
            BACKFILL_SQL.contains("o.engine_mode"),
            "INSERT SELECT must source engine_mode from outcomes.o"
        );
    }

    /// Sanity: the 24h window correctly uses the 4h kline timeframe (not 24h,
    /// which doesn't exist in storage). `LIMIT 1` picks nearest-after with
    /// ±4h precision — acceptable for coarse outcome labels.
    /// 24h 窗口用 4h kline 查（無 24h 儲存），精度 ±4h，可接受。
    #[test]
    fn sql_24h_window_uses_4h_timeframe() {
        // The 24h LATERAL subquery for price_24h uses 4h klines + 24h interval.
        // 24h 子查詢：4h kline + INTERVAL '24 hours'。
        let needle = "k.timeframe = '4h'\n           AND k.ts >= p.ts + INTERVAL '24 hours'";
        assert!(
            BACKFILL_SQL.contains(needle),
            "24h window must use 4h kline with INTERVAL '24 hours'"
        );
    }
}
