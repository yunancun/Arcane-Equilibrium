//! Data quality events writer — detects and logs stale/invalid market data.
//! 數據質量事件寫入器 — 檢測並記錄過期/無效的市場數據。
//!
//! MODULE_NOTE (EN): Monitors tick freshness and NaN/Inf occurrences. Writes events
//!   to observability.data_quality_events table. Non-blocking, runs on periodic timer.
//! MODULE_NOTE (中): 監控 tick 新鮮度和 NaN/Inf 出現。將事件寫入
//!   observability.data_quality_events 表。非阻塞，定期運行。

use super::pool::DbPool;
use std::collections::HashMap;
use std::sync::Arc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Stale threshold — if no tick received for this long, emit quality event.
/// 過期閾值 — 如果超過此時間未收到 tick，發出質量事件。
const STALE_THRESHOLD_MS: u64 = 30_000; // 30 seconds

/// Check interval / 檢查間隔
const CHECK_INTERVAL_SECS: u64 = 60;

/// Run the data quality monitoring task.
/// 運行數據質量監控任務。
pub async fn run_quality_monitor(
    pool: Arc<DbPool>,
    latest_prices: Arc<std::sync::RwLock<HashMap<String, (f64, u64)>>>,
    symbols: Vec<String>,
    cancel: CancellationToken,
) {
    let mut interval = tokio::time::interval(std::time::Duration::from_secs(CHECK_INTERVAL_SECS));
    interval.tick().await;
    let mut event_count: u64 = 0;

    info!("data quality monitor started / 數據質量監控器已啟動");

    loop {
        tokio::select! {
            _ = cancel.cancelled() => break,
            _ = interval.tick() => {
                let now_ms = std::time::SystemTime::now()
                    .duration_since(std::time::UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_millis() as u64;

                if let Ok(guard) = latest_prices.read() {
                    for sym in &symbols {
                        match guard.get(sym.as_str()) {
                            Some(&(price, last_ts)) => {
                                // Check staleness / 檢查過期
                                if now_ms.saturating_sub(last_ts) > STALE_THRESHOLD_MS {
                                    event_count += 1;
                                    let event_id = format!("dq-stale-{}-{}", sym, event_count);
                                    write_quality_event(
                                        &pool, &event_id, "stale_data", sym,
                                        "1m", "WARNING",
                                        &format!("No tick for {}ms", now_ms - last_ts),
                                    ).await;
                                }
                                // Check NaN/Inf price / 檢查 NaN/Inf 價格
                                if !price.is_finite() {
                                    event_count += 1;
                                    let event_id = format!("dq-nan-{}-{}", sym, event_count);
                                    write_quality_event(
                                        &pool, &event_id, "invalid_data", sym,
                                        "1m", "ALERT",
                                        &format!("Non-finite price: {}", price),
                                    ).await;
                                }
                            }
                            None => {
                                // No data at all for this symbol / 此交易對完全無數據
                                event_count += 1;
                                let event_id = format!("dq-missing-{}-{}", sym, event_count);
                                write_quality_event(
                                    &pool, &event_id, "missing_data", sym,
                                    "1m", "WARNING",
                                    "No price data received yet",
                                ).await;
                            }
                        }
                    }
                }
            }
        }
    }

    info!("data quality monitor stopped / 數據質量監控器已停止");
}

/// Write a single quality event to observability.data_quality_events.
/// 寫入一條質量事件到 observability.data_quality_events。
async fn write_quality_event(
    pool: &DbPool,
    event_id: &str,
    check_type: &str,
    symbol: &str,
    timeframe: &str,
    severity: &str,
    description: &str,
) {
    let pg = match pool.get() {
        Some(p) => p,
        None => return,
    };

    let ts = chrono::Utc::now();
    let result = sqlx::query(
        "INSERT INTO observability.data_quality_events \
         (ts, event_id, check_type, symbol, timeframe, severity, description) \
         VALUES ($1, $2, $3, $4, $5, $6, $7) \
         ON CONFLICT (event_id, ts) DO NOTHING"
    )
    .bind(ts)
    .bind(event_id)
    .bind(check_type)
    .bind(symbol)
    .bind(timeframe)
    .bind(severity)
    .bind(description)
    .execute(pg)
    .await;

    match result {
        Ok(_) => debug!(event_id = event_id, "quality event written / 質量事件已寫入"),
        Err(e) => warn!(event_id = event_id, error = %e, "quality event write failed / 質量事件寫入失敗"),
    }
}
