//! Tick-stale watchdog — detects WS freeze / event_consumer zombie by
//! polling `shared_last_tick_ms` and triggering engine-wide cancel on stall.
//! Tick 過期看門狗 — 輪詢 `shared_last_tick_ms`，stall 時觸發全引擎 cancel
//! 偵測 WS 靜默或 event_consumer 殭屍。
//!
//! MODULE_NOTE (EN): Extracted from `main.rs` (G1-03 Wave 1) to keep the
//!   orchestration file lean. Independent background task that polls every
//!   30s. If a tick has ever been seen (last != 0) AND no new tick has arrived
//!   for ≥120s, triggers cancel — a stale tick stream strongly indicates
//!   either WS disconnect or an event_consumer zombie (2026-04-14 14-min
//!   silent zombie pattern). Clean cancel → watchdog restart from fresh boot
//!   with re-subscribed WS is the safest recovery. Threshold 120s (not 60s)
//!   reduces false positives during quiet market hours.
//!   See docs/known_issues/2026-04-14--ws_stale_detector.md.
//!
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1）讓編排檔精簡。獨立背景
//!   任務每 30s 檢查 shared_last_tick_ms。曾收過 tick（!=0）且 ≥120s 無新
//!   tick → 觸發全引擎 cancel。Tick 流靜默強烈暗示 WS 斷連或 event_consumer
//!   殭屍（即 2026-04-14 14 分鐘靜默殭屍事故模式）。乾淨 cancel → watchdog
//!   從頭重啟重新訂閱 WS 是最安全的恢復。閾值選 120s 而非 60s 以減少市場清淡
//!   時段誤報。

use std::sync::Arc;
use tokio_util::sync::CancellationToken;
use tracing::info;

/// Spawn the Fix-4 tick-stale watchdog task.
///
/// EN: Polls every 30s. If `shared_last_tick_ms > 0` AND `now - last > 120s`,
///   flushes stdout/stderr, logs the stale delta, and calls `cancel.cancel()`.
///   The task itself runs on the main tokio runtime; the global panic_hook
///   installed in `main()` covers it if it ever panics.
/// 中: 每 30s 輪詢。若 `shared_last_tick_ms > 0` 且 `now - last > 120s`，flush
///   stdout/stderr、記錄 stale delta、呼叫 `cancel.cancel()`。任務跑在主 tokio
///   runtime；`main()` 中安裝的全域 panic_hook 覆蓋其自身 panic。
pub(crate) fn spawn_tick_stale_watchdog(
    shared_last_tick_ms: &Arc<std::sync::atomic::AtomicU64>,
    cancel: &CancellationToken,
) {
    const TICK_STALE_THRESHOLD_MS: u64 = 120_000;
    const TICK_WATCHDOG_INTERVAL_SECS: u64 = 30;
    let tick_ref = Arc::clone(shared_last_tick_ms);
    let cancel_ref = cancel.clone();
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(tokio::time::Duration::from_secs(
            TICK_WATCHDOG_INTERVAL_SECS,
        ));
        interval.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);
        // Consume the immediate-fire first tick so we don't trip during warmup.
        // 消耗 interval 立即觸發的第一次 tick，避免暖機期誤觸。
        interval.tick().await;
        loop {
            tokio::select! {
                _ = cancel_ref.cancelled() => {
                    tracing::info!("tick-stale watchdog stopped (cancel) / tick-stale watchdog 已停止（cancel）");
                    break;
                }
                _ = interval.tick() => {
                    let last = tick_ref.load(std::sync::atomic::Ordering::Relaxed);
                    if last == 0 {
                        continue;
                    }
                    let now_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_millis() as u64)
                        .unwrap_or(0);
                    if now_ms > last && now_ms - last > TICK_STALE_THRESHOLD_MS {
                        let stale_ms = now_ms - last;
                        tracing::error!(
                            target: "openclaw_engine::panic",
                            stale_ms,
                            threshold_ms = TICK_STALE_THRESHOLD_MS,
                            "WS tick stale — triggering engine cancel (Fix 4) / \
                             WS tick 過期 — 觸發引擎 cancel (修復 4)"
                        );
                        use std::io::Write;
                        let _ = std::io::stdout().flush();
                        let _ = std::io::stderr().flush();
                        cancel_ref.cancel();
                        break;
                    }
                }
            }
        }
    });
    info!(
        stale_threshold_ms = TICK_STALE_THRESHOLD_MS,
        check_interval_secs = TICK_WATCHDOG_INTERVAL_SECS,
        "tick-stale watchdog spawned / tick-stale watchdog 已啟動"
    );
}
