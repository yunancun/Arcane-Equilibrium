//! H State Cache poller — background tokio task that pulls Python H state
//! every N seconds via reverse IPC `query_h_state_full` and stores the
//! parsed snapshot into [`HStateCache`].
//!
//! MODULE_NOTE (EN): Two trigger paths into the poll body:
//!   1. Periodic timer (default 10s) — base refresh cadence.
//!   2. Invalidation channel — Python pushes `invalidate_h_state` IPC
//!      after a state change to ask Rust to poll sooner. Implemented as a
//!      `tokio::sync::watch` channel so back-to-back invalidations within
//!      one tick coalesce to a single poll (dedup).
//!
//!   Phase 1 boundaries (PA design plan §10.1, commit `7564d07`):
//!   - Phase 1 Sub-task A (this file) only wires the daemon plumbing.
//!     The poll body uses a pluggable `HStateFetcher` trait so unit tests
//!     can inject mock fetchers without spinning up a real Python IPC
//!     server. The production fetcher (Python reverse-IPC client) is
//!     parked here as `RealHStateFetcher` stub — it returns
//!     `Ok(default snapshot)` until Sub-task B + C provides the live
//!     route in `app/h_state_query_handler.py` + Python reverse-IPC
//!     server. The stub keeps Phase 1 mid-air pluggable: env=1 will see
//!     `version=0` empty dict (which is the documented Phase 1 spec).
//!
//!   - Phase 2-4 (out of scope): real fetcher integrating with the IPC
//!     client `EngineIPCClient` once Sub-task B/C lands.
//!
//!   Cancellation: respects engine-wide `CancellationToken`. Poller task
//!   exits cleanly on `cancel.cancelled()`.
//!
//! MODULE_NOTE (中)：兩條觸發 poll body 的路徑：
//!   1. 週期計時器（預設 10s）— 基本刷新節奏。
//!   2. Invalidation channel — Python 在 state 變化後推
//!      `invalidate_h_state` IPC 提示 Rust 提前 poll。用
//!      `tokio::sync::watch` 實作，連續 invalidation 可合併為單次 poll
//!      （dedup）。
//!
//!   Phase 1 邊界（PA design plan §10.1，commit `7564d07`）：
//!   - Phase 1 Sub-task A（本檔）只接 daemon 管線。Poll body 走
//!     `HStateFetcher` trait，單元測試可注入 mock fetcher。生產 fetcher
//!     （Python reverse-IPC client）以 `RealHStateFetcher` stub 暫存於
//!     此 — 回 `Ok(default snapshot)`，待 Sub-task B + C 提供
//!     `app/h_state_query_handler.py` + Python reverse-IPC server 後
//!     接通。stub 確保 Phase 1 可運行：env=1 會看到 `version=0` 空 dict
//!     （即 Phase 1 規格定義的行為）。
//!
//!   - Phase 2-4（範圍外）：Sub-task B/C 落地後接真實 fetcher。
//!
//!   取消：尊重 engine-wide `CancellationToken`，
//!   `cancel.cancelled()` 觸發時 poller task 乾淨退出。

use super::{unix_now_ms, HStateCache, HStateSnapshot};
use async_trait::async_trait;
use std::sync::Arc;
use std::time::Duration;
use tokio::sync::watch;
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

/// Default poll interval — see PA design plan §4.1.
/// 預設 poll 間隔 — 詳 PA design plan §4.1。
pub const DEFAULT_POLL_INTERVAL: Duration = Duration::from_secs(10);

/// Pluggable fetcher trait — production uses Python reverse-IPC, tests
/// inject mocks. Returns the freshly-fetched snapshot or an error.
/// 可插拔 fetcher trait — 生產走 Python reverse-IPC，測試注 mock。
/// 回新拉的 snapshot 或錯誤。
#[async_trait]
pub trait HStateFetcher: Send + Sync {
    /// Fetch the full H state snapshot. Implementations may set
    /// `fetched_at_ms` themselves (Python build time) OR leave 0 for the
    /// poller to stamp — both are accepted.
    /// 拉完整 H state snapshot。實作可自行填 `fetched_at_ms`（Python 建構
    /// 時點）或留 0 讓 poller 蓋戳 — 兩者皆可。
    async fn fetch(&self) -> Result<HStateSnapshot, FetchError>;
}

/// Fetch errors — keep exhaustive so future Sub-task B can inspect.
/// Fetch 錯誤 — exhaustive 列出，便於未來 Sub-task B 檢視。
#[derive(Debug, thiserror::Error)]
pub enum FetchError {
    /// IPC client unavailable / connect failed / timeout.
    /// IPC client 不可用 / 連線失敗 / timeout。
    #[error("ipc unavailable: {0}")]
    IpcUnavailable(String),
    /// IPC returned but Python raised. Includes JSON-RPC error message.
    /// IPC 通了但 Python 報錯。含 JSON-RPC error message。
    #[error("python error: {0}")]
    PythonError(String),
    /// Response parse failed (schema drift / corrupt JSON).
    /// Response parse 失敗（schema drift / JSON 損壞）。
    #[error("parse error: {0}")]
    ParseError(String),
}

/// Phase 1 stub fetcher — returns `default()` so env=1 path lights up
/// without depending on Sub-task B/C. Sub-task B will replace this with
/// a real `EngineIPCClient` reverse-IPC call site.
/// Phase 1 stub fetcher — 回 `default()`，讓 env=1 路徑可運行而不依賴
/// Sub-task B/C。Sub-task B 會以真實 `EngineIPCClient` 反向 IPC 取代。
#[derive(Debug, Default, Clone)]
pub struct StubHStateFetcher;

#[async_trait]
impl HStateFetcher for StubHStateFetcher {
    async fn fetch(&self) -> Result<HStateSnapshot, FetchError> {
        Ok(HStateSnapshot::default())
    }
}

/// Invalidation hint sender + receiver pair (paired via [`watch::channel`]).
/// `Sender` 由 IPC handler 持有以推 hint，`Receiver` 由 poller 持有以
/// dedup-merge 監聽。
///
/// MODULE_NOTE (EN): `tokio::sync::watch` chosen over mpsc because:
///   - Single-slot semantics ⇒ N rapid invalidations in one tick collapse
///     to a single notification (natural dedup, see `changed()` doc).
///   - Lock-free Sender::send_modify keeps the IPC handler hot-path fast.
///   - Independent of `mpsc` queue depth tuning.
/// MODULE_NOTE (中)：選 `tokio::sync::watch` 而非 mpsc 因：
///   - 單槽語意 ⇒ 一個 tick 內 N 次快速 invalidation 自然合併為單次通知
///     （原生 dedup，見 `changed()` 文檔）。
///   - Lock-free `Sender::send_modify` 讓 IPC handler hot-path 快。
///   - 不必調 mpsc 隊列深度。
pub type InvalidationSender = watch::Sender<u64>;
pub type InvalidationReceiver = watch::Receiver<u64>;

/// Build a fresh invalidation channel pair.
/// 建立新 invalidation channel pair。
pub fn make_invalidation_channel() -> (InvalidationSender, InvalidationReceiver) {
    watch::channel(0u64)
}

/// Push an invalidation hint — increments the watch slot. Multiple
/// rapid pushes collapse to a single `changed()` event for dedup.
/// 推 invalidation hint — 遞增 watch slot。連續多次自然合併為單次
/// `changed()` 事件以 dedup。
pub fn push_invalidation(tx: &InvalidationSender) {
    tx.send_modify(|v| {
        *v = v.wrapping_add(1);
    });
}

/// Spawn the H state poller task. Returns the [`tokio::task::JoinHandle`].
/// 啟動 H state poller task。回 [`tokio::task::JoinHandle`]。
///
/// MODULE_NOTE (EN): Caller is responsible for env-gate check — see
///   `main_boot_tasks::spawn_h_state_poller_if_enabled`. Once spawned the
///   poller will run until `cancel.cancelled()`.
/// MODULE_NOTE (中)：env-gate check 由 caller 負責 — 詳
///   `main_boot_tasks::spawn_h_state_poller_if_enabled`。spawn 後 poller
///   一直跑到 `cancel.cancelled()`。
pub fn spawn_h_state_poller<F: HStateFetcher + 'static>(
    cache: Arc<HStateCache>,
    fetcher: Arc<F>,
    poll_interval: Duration,
    invalidation_rx: InvalidationReceiver,
    cancel: CancellationToken,
) -> tokio::task::JoinHandle<()> {
    tokio::spawn(async move {
        run_poller_loop(cache, fetcher, poll_interval, invalidation_rx, cancel).await;
    })
}

/// Internal poll loop — periodic + invalidation-driven. Public for tests.
/// 內部 poll loop — 週期 + invalidation 驅動。對測試開放。
pub async fn run_poller_loop<F: HStateFetcher + 'static>(
    cache: Arc<HStateCache>,
    fetcher: Arc<F>,
    poll_interval: Duration,
    mut invalidation_rx: InvalidationReceiver,
    cancel: CancellationToken,
) {
    info!(
        interval_ms = poll_interval.as_millis() as u64,
        "h_state_poller started / H 狀態 poller 已啟動"
    );

    let mut ticker = tokio::time::interval(poll_interval);
    // Keep the first immediate tick: do an initial poll on spawn so env=1
    // path produces an empty-shape snapshot immediately (Phase 1 spec).
    // 保留首次立即 tick：spawn 即 poll 一次，讓 env=1 路徑立刻產生空殼
    // snapshot（Phase 1 規格）。
    ticker.set_missed_tick_behavior(tokio::time::MissedTickBehavior::Delay);

    loop {
        tokio::select! {
            biased;

            _ = cancel.cancelled() => {
                debug!("h_state_poller cancelled / poller 已取消");
                break;
            }

            _ = ticker.tick() => {
                run_one_poll(&cache, fetcher.as_ref()).await;
            }

            change = invalidation_rx.changed() => {
                if change.is_err() {
                    // All senders dropped — keep loop alive on timer alone.
                    // 所有 sender 已丟 — 留 timer 路徑繼續跑。
                    debug!("invalidation channel closed; falling back to ticker only / invalidation 通道已關，僅靠 ticker");
                    // Park the receiver path — pending() never resolves, so the
                    // select will just hit ticker / cancel from now on.
                    // 把 receiver 路徑停掉 — pending() 不解析，select 從此只走
                    // ticker / cancel。
                    invalidation_rx = make_invalidation_channel().1;
                    continue;
                }
                // Mark the new value as seen (so next `.changed()` waits for
                // the *next* invalidation). N back-to-back pushes between
                // two consecutive `.changed()` calls coalesce automatically.
                // 標記已讀（下次 `.changed()` 只等下一次 invalidation）。
                // 兩次 `.changed()` 之間的 N 次 push 自動合併。
                invalidation_rx.mark_unchanged();
                run_one_poll(&cache, fetcher.as_ref()).await;
            }
        }
    }

    info!("h_state_poller exited / H 狀態 poller 已退出");
}

/// Run exactly one poll — bumps attempt counter, calls fetcher, stores
/// snapshot or bumps failure counter.
/// 跑一次 poll — bump attempt 計數、呼叫 fetcher、寫 snapshot 或 bump 失敗。
pub async fn run_one_poll<F: HStateFetcher + ?Sized>(cache: &HStateCache, fetcher: &F) {
    cache.bump_attempts();
    match fetcher.fetch().await {
        Ok(mut snap) => {
            // If Python didn't stamp, stamp ourselves so staleness is
            // measured against Rust-local clock (avoids cross-host skew).
            // Python 沒蓋戳則 Rust 自己蓋（避免跨機時鐘偏移）。
            let now = unix_now_ms();
            if snap.fetched_at_ms == 0 {
                snap.fetched_at_ms = now;
            }
            cache.store_snapshot(snap, now);
        }
        Err(e) => {
            cache.bump_failures();
            warn!(error = %e, "h_state_poller fetch failed (using last good) / poll 失敗（使用上次成功值）");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::sync::Mutex;

    /// Counting fetcher for tests — tracks how many times `fetch` was called
    /// and returns a configurable snapshot.
    /// 測試用計數 fetcher — 追蹤 fetch 次數並回可組態 snapshot。
    #[derive(Default)]
    struct CountingFetcher {
        calls: Mutex<u64>,
        next_snapshot: Mutex<HStateSnapshot>,
    }

    #[async_trait]
    impl HStateFetcher for CountingFetcher {
        async fn fetch(&self) -> Result<HStateSnapshot, FetchError> {
            *self.calls.lock().unwrap() += 1;
            Ok(self.next_snapshot.lock().unwrap().clone())
        }
    }

    /// Failing fetcher for tests — always errors.
    /// 測試用 fetcher — 永遠錯。
    struct FailingFetcher;

    #[async_trait]
    impl HStateFetcher for FailingFetcher {
        async fn fetch(&self) -> Result<HStateSnapshot, FetchError> {
            Err(FetchError::IpcUnavailable("test failure".into()))
        }
    }

    #[tokio::test]
    async fn run_one_poll_success_stores_snapshot_and_bumps_counters() {
        let cache = HStateCache::new();
        let fetcher = CountingFetcher {
            calls: Mutex::new(0),
            next_snapshot: Mutex::new(HStateSnapshot {
                version: 42,
                ..Default::default()
            }),
        };
        run_one_poll(&cache, &fetcher).await;
        assert_eq!(cache.snapshot().version, 42);
        assert_eq!(*fetcher.calls.lock().unwrap(), 1);
        let status = cache.build_status(true);
        assert_eq!(status.poll_attempts, 1);
        assert_eq!(status.poll_successes, 1);
        assert_eq!(status.poll_failures, 0);
    }

    #[tokio::test]
    async fn run_one_poll_failure_bumps_failure_keeps_last_good() {
        let cache = HStateCache::new();
        // Pre-load a "good" snapshot so we can assert it's preserved on failure.
        // 預載 good snapshot 以驗失敗時保留。
        cache.store_snapshot(
            HStateSnapshot {
                version: 7,
                ..Default::default()
            },
            unix_now_ms(),
        );
        run_one_poll(&cache, &FailingFetcher).await;
        // last-good preserved / last-good 保留
        assert_eq!(cache.snapshot().version, 7);
        let status = cache.build_status(true);
        assert_eq!(status.poll_attempts, 1);
        assert_eq!(status.poll_successes, 1, "the pre-load count");
        assert_eq!(status.poll_failures, 1);
    }

    #[tokio::test]
    async fn invalidation_channel_dedups_rapid_pushes() {
        // Push 5 invalidations back-to-back; the receiver's first
        // `.changed()` wakeup should see them as a single event.
        // 連推 5 次 invalidation；receiver 首次 `.changed()` 應視為單次。
        let (tx, mut rx) = make_invalidation_channel();
        for _ in 0..5 {
            push_invalidation(&tx);
        }
        // The watch channel collapses N pushes into one notification.
        // watch channel 將 N 次 push 合併為一次通知。
        rx.changed().await.unwrap();
        rx.mark_unchanged();
        // No further pending change.
        // 無更多 pending 變化。
        let no_more = tokio::time::timeout(Duration::from_millis(50), rx.changed()).await;
        assert!(
            no_more.is_err(),
            "second changed() should time out (no further pushes)"
        );
    }

    #[tokio::test]
    async fn poller_loop_runs_initial_tick_then_invalidation() {
        let cache = HStateCache::new_arc();
        let fetcher = Arc::new(CountingFetcher::default());
        let (inv_tx, inv_rx) = make_invalidation_channel();
        let cancel = CancellationToken::new();
        let cancel_for_task = cancel.clone();
        // Speed up: 50ms poll interval to keep the test fast.
        // 加速：50ms poll interval 讓測試快。
        let handle = tokio::spawn({
            let cache = Arc::clone(&cache);
            let fetcher = Arc::clone(&fetcher);
            async move {
                run_poller_loop(
                    cache,
                    fetcher,
                    Duration::from_millis(50),
                    inv_rx,
                    cancel_for_task,
                )
                .await;
            }
        });

        // Wait for first tick to land.
        // 等首次 tick 落地。
        tokio::time::sleep(Duration::from_millis(80)).await;
        let calls_after_initial = *fetcher.calls.lock().unwrap();
        assert!(calls_after_initial >= 1, "initial tick should have polled");

        // Push an invalidation; expect ≥ 1 extra poll soon.
        // 推 invalidation；應有 ≥ 1 次額外 poll。
        push_invalidation(&inv_tx);
        tokio::time::sleep(Duration::from_millis(30)).await;
        let calls_after_inv = *fetcher.calls.lock().unwrap();
        assert!(
            calls_after_inv > calls_after_initial,
            "invalidation should trigger an additional poll"
        );

        cancel.cancel();
        let _ = tokio::time::timeout(Duration::from_secs(1), handle).await;
    }
}
