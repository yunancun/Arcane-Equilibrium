//! Data quality events writer — detects and logs stale/invalid market data.
//! 數據質量事件寫入器 — 檢測並記錄過期/無效的市場數據。
//!
//! MODULE_NOTE (EN): Monitors tick freshness per symbol using last_tick_ms from a shared
//!   atomic counter. Writes events to observability.data_quality_events. Non-blocking.
//!   F-3 audit fix: uses simple (symbol → price) map + shared last_tick_ms instead of
//!   phantom (f64, u64) tuple type.
//! MODULE_NOTE (中): 使用共享原子計數器中的 last_tick_ms 監控每交易對的 tick 新鮮度。
//!   將事件寫入 observability.data_quality_events。非阻塞。

use super::pool::DbPool;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Stale threshold — if no tick for this long, emit quality event.
/// 過期閾值 — 超過此時間未收到 tick 則發出質量事件。
const STALE_THRESHOLD_MS: u64 = 30_000;

/// Check interval / 檢查間隔
const CHECK_INTERVAL_SECS: u64 = 60;

/// Run the data quality monitoring task.
/// Uses a shared AtomicU64 for last_tick_ms (updated by event_consumer on every tick).
/// 運行數據質量監控任務。使用共享 AtomicU64 作為 last_tick_ms。
pub async fn run_quality_monitor(
    pool: Arc<DbPool>,
    last_tick_ms: Arc<AtomicU64>,
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

                let last = last_tick_ms.load(Ordering::Relaxed);
                if last > 0 && now_ms.saturating_sub(last) > STALE_THRESHOLD_MS {
                    event_count += 1;
                    let event_id = format!("dq-stale-all-{event_count}");
                    let age_ms = now_ms - last;
                    write_quality_event(
                        &pool, &event_id, "stale_data", "*",
                        "1m", "WARNING",
                        &format!("No tick for {age_ms}ms (threshold {STALE_THRESHOLD_MS}ms)"),
                    ).await;
                    warn!(age_ms = age_ms, "data quality: stale ticks / 數據質量：tick 過期");
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
