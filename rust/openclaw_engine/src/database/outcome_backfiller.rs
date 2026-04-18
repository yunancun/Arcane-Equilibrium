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

/// Run one backfill cycle: find pending contexts → compute outcomes → write.
/// 執行一次回填週期：查找待處理上下文 → 計算結果 → 寫入。
pub async fn run_backfill_cycle(pool: &DbPool) -> Result<u64, String> {
    let pg = match pool.get() {
        Some(p) => p,
        None => return Err("PG pool unavailable / PG 連接池不可用".into()),
    };

    // Step 1: Backfill outcomes using LATERAL joins on market.klines.
    // All windows (1m/5m/1h/4h/24h) are computed in a single SQL statement.
    // 步驟 1：使用 LATERAL JOIN 從 market.klines 回填結果。
    // 所有窗口（1m/5m/1h/4h/24h）在單一 SQL 語句中計算。
    //
    // The CTE `pending` selects unbackfilled contexts older than 25h (ensures
    // 24h window has complete kline data). Each LATERAL subquery finds the
    // closest kline close price at the target offset.
    // CTE `pending` 選取未回填且超過 25h 的上下文（確保 24h 窗口有完整 kline 數據）。
    // 每個 LATERAL 子查詢找到目標偏移處最近的 kline 收盤價。
    let rows_affected = sqlx::query(
        r#"
        WITH pending AS (
            SELECT context_id, ts, symbol, last_price
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
                -- 1m return / 1 分鐘回報
                (SELECT k.close FROM market.klines k
                 WHERE k.symbol = p.symbol AND k.timeframe = '1'
                   AND k.ts >= p.ts + INTERVAL '1 minute'
                 ORDER BY k.ts ASC LIMIT 1) AS price_1m,
                -- 5m return / 5 分鐘回報
                (SELECT k.close FROM market.klines k
                 WHERE k.symbol = p.symbol AND k.timeframe = '5'
                   AND k.ts >= p.ts + INTERVAL '5 minutes'
                 ORDER BY k.ts ASC LIMIT 1) AS price_5m,
                -- 1h return / 1 小時回報
                (SELECT k.close FROM market.klines k
                 WHERE k.symbol = p.symbol AND k.timeframe = '60'
                   AND k.ts >= p.ts + INTERVAL '1 hour'
                 ORDER BY k.ts ASC LIMIT 1) AS price_1h,
                -- 4h return / 4 小時回報
                (SELECT k.close FROM market.klines k
                 WHERE k.symbol = p.symbol AND k.timeframe = '240'
                   AND k.ts >= p.ts + INTERVAL '4 hours'
                 ORDER BY k.ts ASC LIMIT 1) AS price_4h,
                -- 24h return / 24 小時回報
                (SELECT k.close FROM market.klines k
                 WHERE k.symbol = p.symbol AND k.timeframe = '240'
                   AND k.ts >= p.ts + INTERVAL '24 hours'
                 ORDER BY k.ts ASC LIMIT 1) AS price_24h,
                -- Max favorable excursion (highest high in 24h) / 最大有利偏移
                (SELECT MAX(k.high) FROM market.klines k
                 WHERE k.symbol = p.symbol AND k.timeframe = '1'
                   AND k.ts > p.ts AND k.ts <= p.ts + INTERVAL '24 hours'
                ) AS max_high_24h,
                -- Max adverse excursion (lowest low in 24h) / 最大不利偏移
                (SELECT MIN(k.low) FROM market.klines k
                 WHERE k.symbol = p.symbol AND k.timeframe = '1'
                   AND k.ts > p.ts AND k.ts <= p.ts + INTERVAL '24 hours'
                ) AS min_low_24h
            FROM pending p
        ),
        inserted AS (
            INSERT INTO trading.decision_outcomes
                (context_id, outcome_1m, outcome_5m, outcome_1h, outcome_4h, outcome_24h,
                 max_favorable, max_adverse, backfilled_ts)
            SELECT
                o.context_id,
                (o.price_1m  - o.last_price) / o.last_price,
                (o.price_5m  - o.last_price) / o.last_price,
                (o.price_1h  - o.last_price) / o.last_price,
                (o.price_4h  - o.last_price) / o.last_price,
                (o.price_24h - o.last_price) / o.last_price,
                (o.max_high_24h - o.last_price) / o.last_price,
                (o.min_low_24h  - o.last_price) / o.last_price,
                NOW()
            FROM outcomes o
            ON CONFLICT (context_id) DO NOTHING
            RETURNING context_id
        )
        -- Step 2: Mark contexts as backfilled / 步驟 2：標記上下文已回填
        UPDATE trading.decision_context_snapshots
        SET outcome_backfilled = TRUE
        WHERE context_id IN (SELECT context_id FROM inserted)
        "#,
    )
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
