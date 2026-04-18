//! Supervised task spawn helpers (E5-P1-5 orphan §九).
//! 受監管的任務啟動輔助（E5-P1-5，§九 孤兒抽取）。
//!
//! MODULE_NOTE (EN):
//!   ``tasks.rs`` opens with 4+ near-identical ``tokio::spawn`` blocks that
//!   follow the exact same shape::
//!
//!       tokio::spawn(async move {
//!           let mut interval = tokio::time::interval(<period>);
//!           interval.tick().await;             // skip first immediate tick
//!           loop {
//!               tokio::select! {
//!                   _ = cancel.cancelled() => {
//!                       info!("<name> stopping (cancel)");
//!                       break;
//!                   }
//!                   _ = interval.tick() => { <body> }
//!               }
//!           }
//!       });
//!
//!   (``fee_rate`` refresh, staleness monitor, ``instrument_refresh``, news
//!   pipeline scheduler all use it.)  This module extracts the frame into
//!   :func:`spawn_cancellable_interval` so callers only supply the period,
//!   a task name, a cancel token, and the per-tick body.
//!
//!   Crucially, the restart / supervision semantics are NOT invented here.
//!   ``tasks.rs`` never restarts on error — it just logs and continues on the
//!   next tick.  ``main.rs::WS supervisor`` has its own exponential-backoff
//!   respawn loop which is intentionally left alone — it carries
//!   reconnection-specific state (attempt counter, topic re-fetch) that a
//!   generic helper would obscure.
//!
//!   Hence this module ships ONE primitive:
//!
//!     - :func:`spawn_cancellable_interval` — the dominant tick-loop pattern.
//!
//!   Any future spawner that needs a genuinely different supervision policy
//!   (e.g. restart-on-panic, fixed retry budget) should land here as a new
//!   free function rather than grow options on the existing one.
//!
//! MODULE_NOTE (中):
//!   ``tasks.rs`` 前段有 4+ 個幾乎一樣的 ``tokio::spawn`` 區塊（費率刷新、
//!   新鮮度監控、instrument_refresh、新聞管線排程器）皆遵循上方 EN 範例的
//!   相同骨架。本模組把骨架抽為 :func:`spawn_cancellable_interval`，
//!   呼叫方只需提供週期、任務名、cancel token、每 tick 的 body。
//!
//!   重點：本模組**不發明新的重啟/監管語意**。``tasks.rs`` 的原始邏輯從未
//!   重啟，錯誤時僅 log 後下一個 tick 繼續；``main.rs::WS supervisor`` 有自
//!   成體系的指數退避重生迴圈，因其攜帶重連特有狀態（嘗試次數、topic
//!   刷新），刻意不納入此處的通用 helper。
//!
//!   因此本模組只提供一個原語：:func:`spawn_cancellable_interval`。
//!   未來若有真正不同的監管策略（例如 panic 重啟、固定重試額度），應以新的
//!   自由函數加入，而不是在既有 API 疊旗標選項。
//!
//! Safety guarantees / 安全保證:
//!   - Cancel token is awaited in ``tokio::select!`` every tick → graceful
//!     shutdown on ``CancellationToken::cancel()``.
//!   - First ``interval.tick()`` is always skipped — matches legacy
//!     ``tasks.rs`` behaviour (avoids an unwanted immediate tick at boot).
//!   - Body is ``async`` and ``FnMut``; any panic propagates to the tokio
//!     runtime unchanged (same semantics as raw ``tokio::spawn``).

use std::future::Future;
use std::time::Duration;
use tokio::task::JoinHandle;
use tokio_util::sync::CancellationToken;
use tracing::info;

/// Spawn a tokio task that runs ``body`` on a ``CancellationToken``-aware
/// interval clock. First tick is skipped (matches legacy ``tasks.rs``
/// contract).  Returns the ``JoinHandle`` so callers can await shutdown or
/// drop it fire-and-forget.
/// 啟動一個受 ``CancellationToken`` 控制、以固定週期觸發 ``body`` 的 tokio
/// 任務；首次立即 tick 會被跳過（與舊 ``tasks.rs`` 契約一致）。回傳
/// ``JoinHandle``，呼叫方可 await 或原樣丟棄。
///
/// Semantics / 語意:
///   - When ``cancel`` fires, if ``on_cancel_msg`` is ``Some(s)`` the loop
///     emits an ``info!`` line with exactly ``s`` and exits; if ``None`` it
///     exits silently.  The per-site legacy messages (e.g. ``"fee_rate refresh
///     task stopping (cancel) / 費率刷新任務停止"``) are preserved byte-for-byte
///     via this parameter.
///   - ``on_cancel_msg=Some(s)`` 時 ``info!`` 輸出 ``s`` 後退出；``None`` 則
///     靜默退出。舊站點的訊息（如 ``"fee_rate refresh task stopping (cancel)
///     / 費率刷新任務停止"``）透過此參數 byte-for-byte 保留。
///   - The task body is responsible for its own error logging — this helper
///     does NOT catch panics or restart on failure (identical to the legacy
///     tasks.rs sites, which always swallowed errors at the body level).
///   - 任務 body 需自行處理錯誤記錄；本 helper 不捕獲 panic、不失敗重啟，
///     與舊 tasks.rs 完全一致（body 內部自行 swallow 錯誤）。
///
/// Example / 範例:
///   ```ignore
///   let cancel = CancellationToken::new();
///   let handle = spawn_cancellable_interval(
///       "fee_rate_refresh",
///       Duration::from_secs(6 * 3600),
///       Some("fee_rate refresh task stopping (cancel) / 費率刷新任務停止"),
///       cancel.clone(),
///       move || {
///           let acct = Arc::clone(&acct);
///           let client = Arc::clone(&client);
///           async move {
///               if let Err(e) = acct.refresh_fee_rates(&*client, "linear").await {
///                   warn!(error = %e, "fee rate refresh failed");
///               }
///           }
///       },
///   );
///   ```
pub fn spawn_cancellable_interval<F, Fut>(
    task_name: &'static str,
    period: Duration,
    on_cancel_msg: Option<&'static str>,
    cancel: CancellationToken,
    mut body: F,
) -> JoinHandle<()>
where
    F: FnMut() -> Fut + Send + 'static,
    Fut: Future<Output = ()> + Send,
{
    tokio::spawn(async move {
        let mut interval = tokio::time::interval(period);
        // Skip first immediate tick — matches legacy tasks.rs contract.
        // 跳過首次立即 tick — 與舊 tasks.rs 契約一致。
        interval.tick().await;
        loop {
            tokio::select! {
                _ = cancel.cancelled() => {
                    if let Some(msg) = on_cancel_msg {
                        info!(task = task_name, "{}", msg);
                    }
                    break;
                }
                _ = interval.tick() => {
                    body().await;
                }
            }
        }
    })
}

// ── Tests / 測試 ──────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    /// Body fires after the first-tick-skip and continues until cancel.
    /// 首次 tick 被跳過，之後週期性觸發 body 直到 cancel。
    ///
    /// Uses real wall-clock time (the ``test-util`` feature is not enabled in
    /// this bin target).  Interval is set to 50ms so the test stays well under
    /// a second; we require ≥2 ticks within ~250ms.
    /// 使用真實時鐘（本 bin target 未啟用 ``test-util``）；間隔設 50ms，
    /// 測試維持在 250ms 內要求至少 2 次觸發。
    #[tokio::test(flavor = "current_thread")]
    async fn interval_skips_first_tick_then_fires() {
        let cancel = CancellationToken::new();
        let counter = Arc::new(AtomicUsize::new(0));
        let counter_cb = Arc::clone(&counter);
        let handle = spawn_cancellable_interval(
            "unit_test_tick",
            Duration::from_millis(50),
            None,
            cancel.clone(),
            move || {
                let c = Arc::clone(&counter_cb);
                async move {
                    c.fetch_add(1, Ordering::SeqCst);
                }
            },
        );

        tokio::time::sleep(Duration::from_millis(250)).await;
        cancel.cancel();
        let _ = handle.await;

        let fired = counter.load(Ordering::SeqCst);
        assert!(fired >= 2, "expected at least 2 ticks, got {fired}");
    }

    /// Cancel fires before any tick → task completes, body never runs.
    /// cancel 先於任何 tick 觸發 → 任務退出，body 完全不執行。
    #[tokio::test(flavor = "current_thread")]
    async fn cancel_token_causes_clean_exit() {
        let cancel = CancellationToken::new();
        let counter = Arc::new(AtomicUsize::new(0));
        let counter_cb = Arc::clone(&counter);
        // Long period so the test will cancel well before any tick.
        // 週期設得夠長，確保 cancel 早於任何 tick。
        let handle = spawn_cancellable_interval(
            "unit_test_cancel",
            Duration::from_secs(60),
            Some("unit_test_cancel stopping"),
            cancel.clone(),
            move || {
                let c = Arc::clone(&counter_cb);
                async move {
                    c.fetch_add(1, Ordering::SeqCst);
                }
            },
        );

        cancel.cancel();
        let join_result = handle.await;
        assert!(join_result.is_ok(), "task should join cleanly after cancel");
        assert_eq!(counter.load(Ordering::SeqCst), 0);
    }
}
