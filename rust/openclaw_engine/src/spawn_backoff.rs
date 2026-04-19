//! PIPELINE-SLOT-1 Phase 3 — exponential backoff for slot respawn attempts.
//! PIPELINE-SLOT-1 Phase 3 — 槽位 respawn 嘗試的指數退避。
//!
//! MODULE_NOTE (EN):
//!   The Live auth watcher polls the signed authorization every 5 seconds
//!   (Phase 3 default). Without a backoff gate, a persistently-failing
//!   `build_exchange_pipeline` (Bybit REST down, expired credentials, etc.)
//!   would become a request-storm — each tick re-hits `get_positions`,
//!   `set_dcp`, `set_auto_add_margin`, ws `kline.subscribe`, etc. This
//!   module gates respawn attempts with a simple exponential backoff:
//!   ready immediately on construction, doubles on each `record_failure()`
//!   up to `max`, resets on `reset()`.
//!
//!   Backoff applies **only** to spawn attempts. Teardown must always run
//!   immediately on auth invalidation — there is no "storm" concern there
//!   because teardown cancels the slot's child token and joins once.
//!
//!   Design points:
//!     * Single-threaded: the watcher owns one `SpawnBackoff` and reads/writes
//!       it from the same task. No `Mutex` needed. Not `Send + Sync`-useful
//!       out of the box; do not share across tasks.
//!     * `Instant`-based, monotonic: not affected by system clock jumps.
//!     * Deterministic: no jitter. The watcher poll interval already adds
//!       enough de-sync for the single-engine single-client case; jitter
//!       would complicate unit tests without buying anything.
//!     * Cross-platform: uses `std::time::{Instant, Duration}` only. No
//!       Linux-only syscalls, no tokio types (callers use `tokio::time::sleep`
//!       separately for the actual wait).
//!
//! MODULE_NOTE (中):
//!   Live 授權 watcher 每 5 秒輪詢簽名授權（Phase 3 預設）。若無退避閘，
//!   持續失敗的 `build_exchange_pipeline`（Bybit REST 故障、憑證過期等）
//!   會變成請求風暴 — 每 tick 都打 `get_positions`/`set_dcp`/
//!   `set_auto_add_margin`/ws `kline.subscribe` 等。本模組以簡單指數退避
//!   收窄 respawn 嘗試：建構後即 ready；每次 `record_failure()` 將延遲倍增
//!   直到 `max`；`reset()` 歸零。
//!
//!   退避**只**針對 spawn 嘗試。授權失效時 teardown 必須立即執行 —
//!   teardown 取消槽位子 token 並 join 一次即可，無「風暴」風險。
//!
//!   設計要點：
//!     * 單線程：watcher 擁有一個 `SpawnBackoff`，同一任務內讀寫，無需
//!       `Mutex`。不提供跨任務共享。
//!     * 基於 `Instant`、單調遞增：不受系統時鐘跳動影響。
//!     * 確定性：無 jitter。單引擎單客戶端情境下 watcher poll 間隔本身
//!       已提供足夠錯峰，jitter 只會讓單測複雜化。
//!     * 跨平台：只用 `std::time::{Instant, Duration}`。不用 tokio 類型
//!       （實際等待由呼叫端用 `tokio::time::sleep` 自己做）。

use std::time::{Duration, Instant};

/// Simple exponential backoff gate for slot respawn attempts.
///
/// 槽位 respawn 嘗試的簡單指數退避閘。
///
/// Usage:
/// ```ignore
/// let mut backoff = SpawnBackoff::new(Duration::from_secs(1), Duration::from_secs(60));
/// if backoff.is_ready() {
///     match try_spawn().await {
///         Ok(_) => backoff.reset(),
///         Err(_) => backoff.record_failure(),
///     }
/// }
/// ```
#[derive(Debug)]
pub struct SpawnBackoff {
    /// Minimum delay after a failure. First failure gates for this duration.
    /// 失敗後的最小延遲。第一次失敗等此延遲。
    base: Duration,
    /// Upper bound on the current delay. Subsequent failures saturate here.
    /// 延遲上限。後續失敗飽和於此。
    max: Duration,
    /// Earliest `Instant` at which the next `is_ready()` returns true.
    /// `is_ready()` 下次回 true 的最早 `Instant`。
    next_earliest: Instant,
    /// Delay currently applied after a failure. Doubles each failure until
    /// saturating at `max`; `reset()` returns it to `base` (the pre-failure
    /// state — next failure will wait `base`, not `0`, but `is_ready()`
    /// returns true immediately after `reset()` because `next_earliest`
    /// also moves to "now").
    /// 當前失敗延遲。每次失敗倍增直到飽和於 `max`；`reset()` 回到 `base`
    /// （失敗前狀態 — 下次失敗等 `base` 而非 0，但 `reset()` 後
    /// `is_ready()` 立即回 true，因為 `next_earliest` 也被設為「當下」）。
    current_delay: Duration,
}

impl SpawnBackoff {
    /// Construct a backoff gate that is immediately ready and gates for
    /// `base` on the first failure, then `2*base`, `4*base`, ... capped at
    /// `max`.
    ///
    /// Panics-avoidance: `base` and `max` are used as-is. Calling with
    /// `base > max` is a caller bug; we do not assert in production paths
    /// (would risk taking down the watcher on a config typo), but the
    /// doubling logic clamps at `max` so the effective behaviour is
    /// "always `max`". Unit tests verify this saturating behaviour.
    ///
    /// 建構一個立即 ready 的退避閘；首次失敗等 `base`，第二次 `2*base`，
    /// 第三次 `4*base`...，飽和於 `max`。
    ///
    /// 防 panic：`base` 與 `max` 直接採納。`base > max` 為呼叫端 bug，
    /// 生產路徑不 assert（配置拼錯不該拖垮 watcher），但倍增邏輯會 clamp
    /// 在 `max`，實際行為變成「永遠 `max`」。單測覆蓋此飽和行為。
    pub fn new(base: Duration, max: Duration) -> Self {
        Self {
            base,
            max,
            next_earliest: Instant::now(),
            current_delay: base,
        }
    }

    /// True iff `Instant::now() >= self.next_earliest`. Called at every
    /// watcher tick before attempting `try_spawn`.
    ///
    /// 僅當 `Instant::now() >= self.next_earliest` 時回 true。Watcher 每次
    /// tick 嘗試 `try_spawn` 前呼叫。
    pub fn is_ready(&self) -> bool {
        Instant::now() >= self.next_earliest
    }

    /// Record a spawn failure: gate `next_earliest = now + current_delay`,
    /// then double `current_delay` for the *next* failure (clamped at `max`).
    ///
    /// Semantics:
    ///   * First failure after `new()` or `reset()` → gates for `base`.
    ///   * Second failure in the same cycle → gates for `2*base`.
    ///   * N-th failure → gates for `min(base * 2^(N-1), max)`.
    ///
    /// Misconfigured `base > max` saturates at `max` on the first failure
    /// (the `.min(max)` clamp wins; no `.max(base)` re-lift). Operators who
    /// typo `base > max` get "always max" behaviour rather than a panic.
    ///
    /// 記錄 spawn 失敗：先以當前 `current_delay` 作為 gate（`next_earliest =
    /// now + current_delay`），再把 `current_delay` 倍增（飽和於 `max`）給
    /// **下一次**失敗用。
    ///
    /// 語意：第一次失敗等 `base`，第二次 `2*base`，第 N 次 `min(base·2^(N-1), max)`。
    /// `base > max` 配置首次即 clamp 於 `max`，不 panic。
    pub fn record_failure(&mut self) {
        // Gate first with the CURRENT delay, then grow the delay for the
        // next failure. This yields "first failure gates for base" — the
        // natural exponential-backoff semantics.
        // 先以當前延遲作 gate，再為下次失敗倍增。產出「第一次等 base」的
        // 自然指數退避語意。
        self.next_earliest = Instant::now() + self.current_delay;
        // `Duration::saturating_mul` saturates at `Duration::MAX` so we
        // never overflow even if `current_delay` starts absurdly high.
        // Then clamp down to `max`.
        // `Duration::saturating_mul` 飽和於 `Duration::MAX`，溢位安全。
        let doubled = self.current_delay.saturating_mul(2);
        self.current_delay = doubled.min(self.max);
    }

    /// Reset backoff to the post-construction state: `is_ready()` returns
    /// true immediately, `current_delay` resets to `base`.
    ///
    /// Called on successful spawn, and on teardown (new decision cycle).
    ///
    /// 退避重設為剛構造狀態：`is_ready()` 立即回 true，`current_delay`
    /// 回到 `base`。成功 spawn 或 teardown（新決策週期）時呼叫。
    pub fn reset(&mut self) {
        self.current_delay = self.base;
        self.next_earliest = Instant::now();
    }

    /// Current delay in milliseconds (used by tests + tracing). Not part of
    /// the steady-state API — callers should observe via `is_ready()`. Public
    /// so structured logs in the watcher can report how long the backoff
    /// gate is holding.
    ///
    /// 當前延遲（毫秒，測試 + tracing 用）。非穩態 API — 呼叫端觀察應用
    /// `is_ready()`。公開以便 watcher 的結構化 log 報告退避閘時長。
    pub fn current_delay_ms(&self) -> u64 {
        self.current_delay.as_millis() as u64
    }

    /// Current delay (test-only helper that returns the full `Duration`).
    /// 當前延遲（測試用，回完整 `Duration`）。
    #[cfg(test)]
    pub(crate) fn current_delay(&self) -> Duration {
        self.current_delay
    }
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    fn base_max() -> (Duration, Duration) {
        (Duration::from_millis(10), Duration::from_millis(320))
    }

    #[test]
    fn ready_immediately_after_new() {
        let (base, max) = base_max();
        let b = SpawnBackoff::new(base, max);
        assert!(
            b.is_ready(),
            "a freshly-constructed backoff must be ready — first spawn attempt \
             happens at watcher start-up with no prior failure"
        );
        assert_eq!(b.current_delay(), base);
    }

    #[test]
    fn record_failure_sets_not_ready() {
        let (base, max) = base_max();
        let mut b = SpawnBackoff::new(base, max);
        b.record_failure();
        assert!(
            !b.is_ready(),
            "immediately after a failure, backoff must gate until the delay elapses"
        );
    }

    #[test]
    fn delay_doubles_up_to_max() {
        // base=10ms, max=320ms → sequence: 20, 40, 80, 160, 320, 320, 320...
        // (First record_failure: current_delay = max(min(20, 320), 10) = 20.)
        let (base, max) = base_max();
        let mut b = SpawnBackoff::new(base, max);
        let expected = [
            Duration::from_millis(20),
            Duration::from_millis(40),
            Duration::from_millis(80),
            Duration::from_millis(160),
            Duration::from_millis(320),
            Duration::from_millis(320),
            Duration::from_millis(320),
        ];
        for (idx, want) in expected.iter().enumerate() {
            b.record_failure();
            assert_eq!(
                b.current_delay(),
                *want,
                "unexpected delay at step {idx}: got {:?}, want {:?}",
                b.current_delay(),
                want,
            );
        }
    }

    #[test]
    fn delay_capped_at_max() {
        // Construct with base=50ms, max=100ms so that the second failure
        // already saturates: 50 → 100 → 100 → 100.
        let base = Duration::from_millis(50);
        let max = Duration::from_millis(100);
        let mut b = SpawnBackoff::new(base, max);
        b.record_failure(); // 50*2=100, clamp to max=100
        assert_eq!(b.current_delay(), Duration::from_millis(100));
        b.record_failure(); // 100*2=200, clamp to max=100
        assert_eq!(b.current_delay(), Duration::from_millis(100));
        b.record_failure(); // still 100
        assert_eq!(b.current_delay(), Duration::from_millis(100));
    }

    #[test]
    fn reset_clears_delay() {
        let (base, max) = base_max();
        let mut b = SpawnBackoff::new(base, max);
        // Push it up a few failures.
        b.record_failure();
        b.record_failure();
        b.record_failure();
        assert!(b.current_delay() > base);
        assert!(!b.is_ready());

        b.reset();

        assert!(
            b.is_ready(),
            "reset must unblock is_ready() — called on successful spawn / \
             teardown (new decision cycle)"
        );
        assert_eq!(
            b.current_delay(),
            base,
            "reset must return current_delay to base"
        );
    }

    #[test]
    fn misconfigured_base_above_max_saturates_at_max() {
        // Operator typo: base=500ms, max=100ms. We don't panic; current_delay
        // clamps to max on the first failure (via `.min(self.max)`).
        // Operator 打錯配置不應 panic；首次失敗即 clamp 到 max。
        let base = Duration::from_millis(500);
        let max = Duration::from_millis(100);
        let mut b = SpawnBackoff::new(base, max);
        // Fresh state: current_delay == base (500ms) — constructor does not clamp
        // here, that's fine; is_ready() is true initially regardless.
        assert!(b.is_ready());
        b.record_failure();
        assert_eq!(
            b.current_delay(),
            max,
            "misconfigured base>max must saturate at max on first failure, not panic"
        );
    }

    #[test]
    fn ready_returns_true_after_delay_elapses() {
        // Use a very small delay so we don't slow down CI too much.
        // 用極短延遲避免拖慢 CI。
        let base = Duration::from_millis(20);
        let max = Duration::from_millis(100);
        let mut b = SpawnBackoff::new(base, max);
        b.record_failure();
        assert!(!b.is_ready());
        std::thread::sleep(base + Duration::from_millis(5));
        assert!(
            b.is_ready(),
            "after the gated delay, is_ready() must return true again"
        );
    }

    #[test]
    fn record_failure_uses_instant_now_not_prior_value() {
        // Two sequential failures with sleeps in between must push the gate
        // relative to each `Instant::now()` — never anchor the gate to the
        // original construction time.
        // 兩次連續失敗（中間有 sleep）必須相對每次 `Instant::now()` 推遲 —
        // 絕不能錨定在原構造時間。
        let base = Duration::from_millis(20);
        let max = Duration::from_millis(200);
        let mut b = SpawnBackoff::new(base, max);

        b.record_failure();
        std::thread::sleep(Duration::from_millis(25)); // wait past first gate
        assert!(b.is_ready(), "first gate should have elapsed");

        b.record_failure(); // second failure: current_delay=40ms
        assert!(
            !b.is_ready(),
            "second failure must re-gate from now, not from the original Instant"
        );
    }
}
