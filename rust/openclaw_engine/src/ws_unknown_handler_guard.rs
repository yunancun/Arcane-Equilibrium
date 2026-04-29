//! WS unknown-topic handler guard with force-reconnect trigger (G9-02).
//! WS 未知 topic / handler not found 強制重連守衛（G9-02）。
//!
//! MODULE_NOTE (EN): When Bybit V5 WebSocket pushes a topic that has no
//!   matching dispatcher branch (`unhandled topic / 未處理的主題` in
//!   `ws_client.rs:417` and `Unhandled private topic / 未處理的私有主題`
//!   in `bybit_private_ws.rs:633`), the current behaviour is "log + skip".
//!   BB audit (Bybit Broker Compatibility Auditor) flagged this as a
//!   potential silent failure mode: persistent unknown topics may indicate
//!   that Bybit force-unsubscribed our session without notification, leaving
//!   the WS subscription set corrupted while the TCP connection is alive.
//!
//!   This guard tracks unknown-topic events in a 60s sliding window and
//!   signals the WS run loop to break (→ falls into existing reconnect
//!   path → resubscribes all topics from the cached `subscriptions` set
//!   in ws_client / from `BybitEnvironment::private_ws_topics()` in
//!   bybit_private_ws). The hot path (subscribe / heartbeat / parse) is
//!   not modified.
//!
//!   DEFAULT-OFF behaviour: env var
//!   `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED` must be "1" to arm
//!   the trigger. When unset / "0" / any other value, `record_unknown()`
//!   still increments counters (for metrics) but never returns
//!   `ShouldReconnect::Yes`. Operator flips to "1" after monitoring
//!   the `unknown_handler_total` metric for a representative period.
//!
//!   Trigger thresholds (per BB recommendation):
//!     - `unique_count >= UNIQUE_THRESHOLD` (3 distinct topics within window), OR
//!     - `total_count >= TOTAL_THRESHOLD` (5 events within window)
//!   Window length: `WINDOW_MS` (60_000 ms).
//!
//!   Concurrency model: `record_unknown()` is `&self` and safe to call from
//!   any tokio task. `AtomicU64` for the cumulative counters; a single
//!   `parking_lot::Mutex<Vec<(String, u64)>>` for the sliding window list
//!   (entry count bounded by trigger threshold + late-arrival skew → very
//!   short critical section, no contention concern at WS message rates).
//!
//! MODULE_NOTE (中): 當 Bybit V5 WebSocket 推送一個沒有匹配 dispatcher 分支
//!   的 topic（公共 WS `ws_client.rs:417`「unhandled topic / 未處理的主題」+
//!   私有 WS `bybit_private_ws.rs:633`「Unhandled private topic / 未處理的
//!   私有主題」），當前行為是「log 後 skip」。BB（Bybit Broker Compatibility
//!   Auditor）審計指出這是潛在的「靜默失敗模式」：持續的未知 topic 可能代表
//!   Bybit 已強制 unsubscribe 我們的 session 但沒主動通知，造成 WS subscription
//!   set 已 corrupted 但 TCP 仍在線。
//!
//!   此守衛在 60s 滑動視窗內追蹤未知 topic 事件，達到閾值時通知 WS run loop
//!   break（→ 進入既有 reconnect 路徑 → 重訂閱所有 cached topics —— 公共 WS
//!   來自 `subscriptions` HashSet，私有 WS 來自 `BybitEnvironment::private_ws_topics()`）。
//!   不動 hot path（subscribe / heartbeat / parse 解析邏輯）。
//!
//!   DEFAULT-OFF 行為：環境變數
//!   `OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED` 必須為 "1" 才 arm trigger。
//!   未設 / "0" / 其他值時，`record_unknown()` 仍會增計數（提供 metrics）但永不
//!   回傳 `ShouldReconnect::Yes`。Operator 觀察 `unknown_handler_total` 一段
//!   時間後，再翻為 "1"。
//!
//!   觸發閾值（依 BB 建議）：
//!     - `unique_count >= UNIQUE_THRESHOLD`（視窗內 3 個 distinct topics），或
//!     - `total_count >= TOTAL_THRESHOLD`（視窗內 5 個事件）
//!   視窗長度：`WINDOW_MS`（60_000 ms）。
//!
//!   併發模型：`record_unknown()` 為 `&self`，可從任意 tokio 任務呼叫。累計
//!   counters 用 `AtomicU64`；滑動視窗用單一 `parking_lot::Mutex<Vec<(String, u64)>>`
//!   （entry 數受閾值 + 遲延誤差約束 → 臨界區極短，WS 訊息速率下無爭用問題）。

use parking_lot::Mutex;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::Arc;

/// Sliding window length in milliseconds (60s).
/// 滑動視窗長度（毫秒，60 秒）。
pub const WINDOW_MS: u64 = 60_000;

/// Distinct unknown topics within window required to trigger reconnect.
/// 視窗內 distinct 未知 topic 數，達此值觸發重連。
pub const UNIQUE_THRESHOLD: usize = 3;

/// Total unknown events within window required to trigger reconnect.
/// 視窗內未知事件總數，達此值觸發重連。
pub const TOTAL_THRESHOLD: usize = 5;

/// Env var name controlling whether the trigger is armed (DEFAULT-OFF).
/// 控制 trigger 是否啟用的環境變數名稱（預設關閉）。
pub const ENV_FORCE_RECONNECT_ENABLED: &str = "OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED";

/// Decision returned by `record_unknown()`.
/// `record_unknown()` 的回傳決策。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ShouldReconnect {
    /// Counter incremented, threshold not met (or env-gate off).
    /// 已計數，但未達閾值（或 env-gate 未開）。
    No,
    /// Threshold reached AND env-gate armed → caller should break run loop.
    /// 達閾值且 env-gate 已 arm → 呼叫端應 break run loop。
    Yes,
}

/// Internal sliding-window entry: (topic, ts_ms).
/// 內部滑動視窗 entry：(topic, ts_ms)。
type WindowEntry = (String, u64);

/// Per-WS-instance unknown-topic guard.
/// 單一 WS 實例的未知 topic 守衛。
///
/// EN: Construct with `new()` (env-gate snapshot taken once at construction;
///     not re-read per call to keep `record_unknown()` fast and predictable).
///     Share via `Arc` if multiple tasks need to record into the same guard.
/// 中文：用 `new()` 建立（env-gate 在建構時取一次快照；不在每次呼叫重讀，保持
///     `record_unknown()` 快速且行為可預測）。多任務共用時包 `Arc`。
pub struct UnknownHandlerGuard {
    /// Cumulative unknown-topic events seen since construction (metrics).
    /// 自建構以來累計未知 topic 事件數（metrics）。
    unknown_total: AtomicU64,
    /// Cumulative force-reconnect triggers (metrics).
    /// 自建構以來累計 force-reconnect 觸發次數（metrics）。
    forced_reconnect_total: AtomicU64,
    /// Sliding window of recent unknowns. Bounded by threshold + skew → ~10 entries.
    /// 近期未知事件的滑動視窗。受閾值 + 時鐘誤差約束 → 約 10 entries。
    window: Mutex<Vec<WindowEntry>>,
    /// Whether the trigger is armed (env-gate snapshot).
    /// trigger 是否已 arm（env-gate 快照）。
    armed: bool,
}

impl UnknownHandlerGuard {
    /// Construct a new guard reading env-gate from the process environment.
    /// 建立守衛，從 process 環境讀取 env-gate。
    pub fn new() -> Self {
        Self::with_armed(env_gate_armed())
    }

    /// Construct with explicit armed state (for tests).
    /// 以指定 arm 狀態建立（測試用）。
    pub fn with_armed(armed: bool) -> Self {
        Self {
            unknown_total: AtomicU64::new(0),
            forced_reconnect_total: AtomicU64::new(0),
            window: Mutex::new(Vec::with_capacity(TOTAL_THRESHOLD * 2)),
            armed,
        }
    }

    /// Construct wrapped in `Arc` for multi-task sharing.
    /// 建立 `Arc` 包裝以便多任務共用。
    pub fn new_arc() -> Arc<Self> {
        Arc::new(Self::new())
    }

    /// Record an unknown-topic event and decide whether to force reconnect.
    /// 記錄一筆未知 topic 事件，並決定是否強制重連。
    ///
    /// Always increments `unknown_total` (metric remains useful even when
    /// trigger is disarmed). Sliding window pruned to `now_ms - WINDOW_MS`
    /// before counting. Returns `ShouldReconnect::Yes` only when:
    ///   1. armed (env-gate "1"), AND
    ///   2. (unique_count >= UNIQUE_THRESHOLD) OR (total_count >= TOTAL_THRESHOLD).
    /// On `Yes`, also increments `forced_reconnect_total` and clears the window
    /// so the next reconnect cycle starts fresh.
    ///
    /// 永遠遞增 `unknown_total`（即使 trigger 未 arm，metric 仍有用）。計數
    /// 前先依 `now_ms - WINDOW_MS` 修剪視窗。僅在以下條件回傳
    /// `ShouldReconnect::Yes`：
    ///   1. armed（env-gate "1"），且
    ///   2. （unique 數 >= UNIQUE_THRESHOLD）或（總數 >= TOTAL_THRESHOLD）。
    /// 回 `Yes` 時，同時遞增 `forced_reconnect_total` 並清空視窗，下次 reconnect
    /// 後重新計數。
    pub fn record_unknown(&self, topic: &str, now_ms: u64) -> ShouldReconnect {
        self.unknown_total.fetch_add(1, Ordering::Relaxed);

        let mut window = self.window.lock();

        // Prune entries older than now_ms - WINDOW_MS / 修剪過期 entry
        let cutoff = now_ms.saturating_sub(WINDOW_MS);
        window.retain(|(_, ts)| *ts >= cutoff);

        // Append current event / 追加當前事件
        window.push((topic.to_string(), now_ms));

        if !self.armed {
            // env-gate disarmed → metric only, no trigger
            // env-gate 未 arm → 僅 metric，不觸發
            return ShouldReconnect::No;
        }

        // Count unique topics + total events / 計算 unique topic 數 + 總事件數
        let total_count = window.len();
        let unique_count: usize = {
            let mut topics: Vec<&str> = window.iter().map(|(t, _)| t.as_str()).collect();
            topics.sort_unstable();
            topics.dedup();
            topics.len()
        };

        let should_trigger = unique_count >= UNIQUE_THRESHOLD || total_count >= TOTAL_THRESHOLD;

        if should_trigger {
            self.forced_reconnect_total.fetch_add(1, Ordering::Relaxed);
            // Clear window so next post-reconnect cycle starts fresh.
            // 清空視窗，下次 reconnect 後重新計數。
            window.clear();
            ShouldReconnect::Yes
        } else {
            ShouldReconnect::No
        }
    }

    /// Reset the sliding window (called by run loop after a forced reconnect).
    /// 重置滑動視窗（強制重連後由 run loop 呼叫）。
    ///
    /// EN: Cumulative metrics are NOT reset (operator monitors lifetime totals).
    ///     Window-clear is also performed inside `record_unknown()` on Yes path
    ///     for safety; this method exists for explicit reset elsewhere if needed.
    /// 中文：累計 metrics 不重置（operator 監控生命週期累計）。`record_unknown()`
    ///     回 Yes 路徑也會清空視窗以策安全；此方法供其他需要顯式 reset 的位置使用。
    pub fn reset_window(&self) {
        self.window.lock().clear();
    }

    /// Snapshot metric counters: (unknown_handler_total, forced_reconnect_total).
    /// metric counters 快照：(unknown_handler_total, forced_reconnect_total)。
    pub fn snapshot_metrics(&self) -> (u64, u64) {
        (
            self.unknown_total.load(Ordering::Relaxed),
            self.forced_reconnect_total.load(Ordering::Relaxed),
        )
    }

    /// Whether the trigger is armed (for diagnostics / log output).
    /// trigger 是否已 arm（供診斷 / log 輸出使用）。
    pub fn is_armed(&self) -> bool {
        self.armed
    }
}

impl Default for UnknownHandlerGuard {
    fn default() -> Self {
        Self::new()
    }
}

/// Read env-gate from process environment.
/// 從 process 環境讀取 env-gate。
///
/// EN: Treats only the literal string "1" as armed; anything else (unset,
///     "0", "true", "yes", typo) is treated as disarmed (DEFAULT-OFF).
///     This is intentionally strict so accidental enables are unlikely.
/// 中文：僅字串 "1" 視為 arm；其他（未設、"0"、"true"、"yes"、typo）皆視為
///     未 arm（DEFAULT-OFF）。刻意嚴格，避免誤啟。
fn env_gate_armed() -> bool {
    std::env::var(ENV_FORCE_RECONNECT_ENABLED)
        .map(|v| v == "1")
        .unwrap_or(false)
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Default-OFF: 1000 unknowns never trigger reconnect when env-gate disarmed.
    /// 預設關：env-gate 未 arm 時，1000 個未知事件也不觸發重連。
    #[test]
    fn test_env_disarmed_never_triggers() {
        let guard = UnknownHandlerGuard::with_armed(false);
        let now = 1_700_000_000_000_u64;
        for i in 0..1000 {
            let topic = format!("unknown_topic_{}", i);
            let result = guard.record_unknown(&topic, now + i);
            assert_eq!(
                result,
                ShouldReconnect::No,
                "iteration {} must not trigger when disarmed",
                i
            );
        }
        let (total, forced) = guard.snapshot_metrics();
        assert_eq!(
            total, 1000,
            "unknown_total must accumulate even when disarmed"
        );
        assert_eq!(
            forced, 0,
            "forced_reconnect_total must remain 0 when disarmed"
        );
    }

    /// 3 unique unknowns within window trigger reconnect.
    /// 視窗內 3 個 distinct 未知 topic 觸發重連。
    #[test]
    fn test_unique_threshold_triggers() {
        let guard = UnknownHandlerGuard::with_armed(true);
        let now = 1_700_000_000_000_u64;

        // First two unique → No
        assert_eq!(
            guard.record_unknown("topic_a", now),
            ShouldReconnect::No,
            "1st unique must not trigger"
        );
        assert_eq!(
            guard.record_unknown("topic_b", now + 1),
            ShouldReconnect::No,
            "2nd unique must not trigger"
        );
        // Third unique → Yes
        assert_eq!(
            guard.record_unknown("topic_c", now + 2),
            ShouldReconnect::Yes,
            "3rd unique must trigger"
        );

        let (total, forced) = guard.snapshot_metrics();
        assert_eq!(total, 3);
        assert_eq!(forced, 1);
    }

    /// Same topic repeated N times: counter increments but unique stays at 1
    /// → only TOTAL_THRESHOLD (5) triggers reconnect.
    /// 同 topic 重複 N 次：counter 遞增但 unique 維持 1 → 僅 TOTAL_THRESHOLD 觸發。
    #[test]
    fn test_repeated_topic_total_threshold_triggers() {
        let guard = UnknownHandlerGuard::with_armed(true);
        let now = 1_700_000_000_000_u64;

        // First 4 repeats of same topic → No (unique=1 < 3, total < 5)
        for i in 0..4 {
            assert_eq!(
                guard.record_unknown("repeat_topic", now + i),
                ShouldReconnect::No,
                "repeat {} must not trigger (total < 5)",
                i + 1
            );
        }
        // 5th of same topic → total=5 hits TOTAL_THRESHOLD → Yes
        assert_eq!(
            guard.record_unknown("repeat_topic", now + 4),
            ShouldReconnect::Yes,
            "5th repeat must trigger via total threshold"
        );

        let (total, forced) = guard.snapshot_metrics();
        assert_eq!(total, 5);
        assert_eq!(forced, 1);
    }

    /// Window expiry: events older than 60s are pruned, do not count toward threshold.
    /// 視窗到期：超過 60s 的事件被修剪，不計入閾值。
    #[test]
    fn test_window_expiry_prunes_old_events() {
        let guard = UnknownHandlerGuard::with_armed(true);
        let t0 = 1_700_000_000_000_u64;

        // Two unique unknowns at t=0
        assert_eq!(guard.record_unknown("a", t0), ShouldReconnect::No);
        assert_eq!(guard.record_unknown("b", t0 + 1), ShouldReconnect::No);

        // 70 seconds later (past WINDOW_MS=60s) → both old entries pruned
        // Third unique now alone in window → no trigger
        assert_eq!(
            guard.record_unknown("c", t0 + 70_000),
            ShouldReconnect::No,
            "after window expiry, lone unknown must not trigger"
        );

        let (total, forced) = guard.snapshot_metrics();
        assert_eq!(total, 3, "cumulative counter unaffected by window pruning");
        assert_eq!(forced, 0);
    }

    /// After triggering, window is cleared so next cycle starts fresh.
    /// 觸發後視窗清空，下個週期重新計數。
    #[test]
    fn test_window_cleared_after_trigger() {
        let guard = UnknownHandlerGuard::with_armed(true);
        let t0 = 1_700_000_000_000_u64;

        // Trigger via unique threshold
        guard.record_unknown("a", t0);
        guard.record_unknown("b", t0 + 1);
        assert_eq!(
            guard.record_unknown("c", t0 + 2),
            ShouldReconnect::Yes,
            "expected initial trigger"
        );

        // Window must be empty now: 2 more uniques should NOT re-trigger
        assert_eq!(
            guard.record_unknown("d", t0 + 3),
            ShouldReconnect::No,
            "post-trigger 1st unknown must not trigger"
        );
        assert_eq!(
            guard.record_unknown("e", t0 + 4),
            ShouldReconnect::No,
            "post-trigger 2nd unknown must not trigger"
        );
        // 3rd post-trigger unique fires again
        assert_eq!(
            guard.record_unknown("f", t0 + 5),
            ShouldReconnect::Yes,
            "post-trigger 3rd unique must re-trigger"
        );

        let (total, forced) = guard.snapshot_metrics();
        assert_eq!(total, 6);
        assert_eq!(forced, 2, "two distinct trigger events should accumulate");
    }

    /// Mixed scenario: 2 unique + 3 repeats of one of them = total=5 → triggers.
    /// 混合情境：2 unique + 其中一個重複 3 次 = total=5 → 觸發。
    #[test]
    fn test_mixed_unique_and_repeat_total_threshold() {
        let guard = UnknownHandlerGuard::with_armed(true);
        let t0 = 1_700_000_000_000_u64;

        // 2 unique topics
        guard.record_unknown("a", t0);
        guard.record_unknown("b", t0 + 1);
        // 2 repeats of "a" → total=4, unique=2 → still No
        assert_eq!(guard.record_unknown("a", t0 + 2), ShouldReconnect::No);
        assert_eq!(guard.record_unknown("a", t0 + 3), ShouldReconnect::No);
        // 5th event (any) → total=5 → Yes
        assert_eq!(
            guard.record_unknown("a", t0 + 4),
            ShouldReconnect::Yes,
            "total=5 must trigger even with unique=2"
        );
    }

    /// `reset_window()` clears entries without resetting cumulative counters.
    /// `reset_window()` 清空 entries 但不重置累計 counters。
    #[test]
    fn test_reset_window_preserves_metrics() {
        let guard = UnknownHandlerGuard::with_armed(true);
        let t0 = 1_700_000_000_000_u64;

        guard.record_unknown("a", t0);
        guard.record_unknown("b", t0 + 1);

        guard.reset_window();

        // Two more unique → unique=2 in window (not 4) → No
        assert_eq!(guard.record_unknown("c", t0 + 2), ShouldReconnect::No);
        assert_eq!(guard.record_unknown("d", t0 + 3), ShouldReconnect::No);

        let (total, forced) = guard.snapshot_metrics();
        assert_eq!(
            total, 4,
            "cumulative counter must include events before AND after reset"
        );
        assert_eq!(forced, 0);
    }

    /// `is_armed()` reflects the constructor input.
    /// `is_armed()` 反映建構參數。
    #[test]
    fn test_is_armed_reflects_constructor() {
        assert!(UnknownHandlerGuard::with_armed(true).is_armed());
        assert!(!UnknownHandlerGuard::with_armed(false).is_armed());
    }

    /// Saturating arithmetic: now_ms < WINDOW_MS does not panic.
    /// Saturating 算術：now_ms < WINDOW_MS 不 panic。
    #[test]
    fn test_small_timestamps_do_not_panic() {
        let guard = UnknownHandlerGuard::with_armed(true);
        // now_ms < WINDOW_MS → cutoff = saturating_sub = 0
        assert_eq!(guard.record_unknown("a", 100), ShouldReconnect::No);
        assert_eq!(guard.record_unknown("b", 200), ShouldReconnect::No);
        assert_eq!(guard.record_unknown("c", 300), ShouldReconnect::Yes);
    }

    /// Constants advertised in the public API match BB recommendations.
    /// public API 暴露的常量符合 BB 建議。
    #[test]
    fn test_public_constants_unchanged() {
        assert_eq!(WINDOW_MS, 60_000);
        assert_eq!(UNIQUE_THRESHOLD, 3);
        assert_eq!(TOTAL_THRESHOLD, 5);
        assert_eq!(
            ENV_FORCE_RECONNECT_ENABLED,
            "OPENCLAW_WS_FORCE_RECONNECT_ON_UNKNOWN_ENABLED"
        );
    }
}
