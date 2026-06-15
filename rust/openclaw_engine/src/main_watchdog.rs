//! Tick-stale watchdog — detects WS freeze / event_consumer zombie by polling
//! a WALL-CLOCK "last processed tick" atomic and triggering engine-wide cancel
//! on stall.
//! Tick 過期看門狗 — 輪詢「牆鐘」last-processed atomic，stall 時觸發全引擎
//! cancel，偵測 WS 靜默或 event_consumer 殭屍。
//!
//! MODULE_NOTE (EN): Extracted from `main.rs` (G1-03 Wave 1) to keep the
//!   orchestration file lean. Independent background task that polls every
//!   30s. If a tick has ever been processed (last != 0) AND no new tick has
//!   been processed for ≥120s, triggers cancel — a stale processed-tick stream
//!   strongly indicates either WS disconnect or an event_consumer zombie
//!   (2026-04-14 14-min silent zombie pattern). Clean cancel → watchdog restart
//!   from fresh boot with re-subscribed WS is the safest recovery. Threshold
//!   120s (not 60s) reduces false positives during quiet market hours.
//!
//!   ENGINE-CRASH-FIX C3 (2026-06-15): this atomic now carries the WALL-CLOCK
//!   timestamp at which the event_consumer loop last processed a tick
//!   (`shared_last_processed_wallclock_ms`), NOT the Bybit payload `ts`
//!   (`shared_last_tick_ms`). The old payload-ts source false-positived because
//!   the payload clock can skew from / be non-monotonic vs wall-clock (replay /
//!   auto-补单), occasionally crossing the 120s delta on a perfectly healthy
//!   live engine and SIGTERMing it (market-closing positions). Wall-clock only
//!   stops advancing when the loop itself is genuinely frozen, so this removes
//!   the false-positive WITHOUT weakening the true WS-zombie / loop-freeze guard.
//!   See docs/known_issues/2026-04-14--ws_stale_detector.md.
//!
//! MODULE_NOTE (中): 從 `main.rs` 抽出（G1-03 Wave 1）讓編排檔精簡。獨立背景
//!   任務每 30s 檢查 atomic。曾處理過 tick（!=0）且 ≥120s 無新處理 → 觸發
//!   全引擎 cancel。Tick 流靜默強烈暗示 WS 斷連或 event_consumer 殭屍（即
//!   2026-04-14 14 分鐘靜默殭屍事故模式）。乾淨 cancel → watchdog 從頭重啟
//!   重新訂閱 WS 是最安全的恢復。閾值選 120s 而非 60s 以減少市場清淡時段誤報。
//!
//!   ENGINE-CRASH-FIX C3（2026-06-15）：此 atomic 現在攜帶 event_consumer loop
//!   「最後處理 tick 的牆鐘時間」（`shared_last_processed_wallclock_ms`），
//!   而非 Bybit payload `ts`（`shared_last_tick_ms`）。舊的 payload-ts 來源會
//!   誤報：payload 時鐘可能與牆鐘偏移或非單調（重放 / auto-补單），偶爾在
//!   健康的 live 引擎上越過 120s delta → SIGTERM 市價平倉。牆鐘只有在 loop
//!   真正凍結時才停止前進，因此移除假陽性又不弱化真 WS-殭屍 / loop-凍結防護。

use std::sync::Arc;
use tokio_util::sync::CancellationToken;
use tracing::info;

/// Spawn the Fix-4 tick-stale watchdog task.
///
/// EN: Polls every 30s. If `last_processed_wallclock_ms > 0` AND
///   `now - last > 120s`, flushes stdout/stderr, logs the stale delta, and
///   calls `cancel.cancel()`. The task runs on the main tokio runtime; the
///   global panic_hook installed in `main()` covers it if it ever panics.
///   ENGINE-CRASH-FIX C3 (2026-06-15): the param is now the wall-clock
///   last-processed atomic (see MODULE_NOTE), not the payload-ts one.
/// 中: 每 30s 輪詢。若 `last_processed_wallclock_ms > 0` 且 `now - last > 120s`，
///   flush stdout/stderr、記錄 stale delta、呼叫 `cancel.cancel()`。任務跑在
///   主 tokio runtime；`main()` 中安裝的全域 panic_hook 覆蓋其自身 panic。
///   ENGINE-CRASH-FIX C3（2026-06-15）：參數改為牆鐘 last-processed atomic
///   （見 MODULE_NOTE），非 payload-ts。
pub(crate) fn spawn_tick_stale_watchdog(
    last_processed_wallclock_ms: &Arc<std::sync::atomic::AtomicU64>,
    cancel: &CancellationToken,
) {
    const TICK_STALE_THRESHOLD_MS: u64 = 120_000;
    const TICK_WATCHDOG_INTERVAL_SECS: u64 = 30;
    let tick_ref = Arc::clone(last_processed_wallclock_ms);
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
