//! Strategy signal emission 統計 — Sprint 5+ Track B real probe SSOT。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md §2.4：
//!   為 `RealPipelineThroughputSource::current_strategy_signal_rate_per_min`
//!   提供累積資料源。`step_3_signals.rs` 每 tick 在 `SignalEngine::evaluate`
//!   後若回傳非空 signal vec，呼 `inc_signal_batch(count, now_ms)`。
//!
//!   為什麼放 openclaw_engine 端而非 openclaw_core SignalEngine 內：
//!     - SignalEngine 在 openclaw_core；本 IMPL 範圍是 openclaw_engine（per
//!       PA spec dispatch 範圍與 `feedback_working_principles` 範圍最小化）。
//!     - 改 openclaw_core 跨 crate signature change 衝擊面太大；走「外圍累計」
//!       由 step_3_signals.rs hook 即可（signal 是否非空 evaluate caller 端可
//!       觀測，不需 SignalEngine 內部 self counter）。
//!
//! 主要類 / 函數:
//!   - `SignalStats`：兩 AtomicU64（signals_emitted_total / last_signal_ms）。
//!   - `inc_signal_batch`：caller 端傳本 tick signal count + wall-clock ms；
//!     一次性 fetch_add（避免 N 次 atomic op）。
//!
//! 依賴:
//!   - 0 外部 crate（std::sync::atomic 既有 dep）。
//!
//! 硬邊界:
//!   - hot path 走 `Ordering::Relaxed`（per spec §5 E2 重點審查 #2）。
//!   - 觀測層 0 trading 路徑滲透；同 WsStats 範式。
//!   - signal 為空時 caller 不呼 inc → counter 不前進；emitter 走 cold-start
//!     placeholder fail-soft（per `feedback_no_dead_params`）。

use std::sync::atomic::{AtomicU64, Ordering};

/// 策略 signal 產出次數累計。
///
/// 為什麼 batch increment 而非 per-signal：
///   - step_3_signals.rs 端 `SignalEngine::evaluate` 一次回 N 個 signal（最多
///     8 rule × 25 sym × 5/s = 1000 signals/s 上限）。
///   - 一次 `fetch_add(N)` vs N 次 `fetch_add(1)` 性能差距小但 caller 端更乾淨；
///     spec §2.4 hook 點是 evaluate() 後而非 record_signal() 內部。
#[derive(Debug, Default)]
pub struct SignalStats {
    /// 累計 strategy signal 產出總數。單調遞增；無 reset。
    signals_emitted_total: AtomicU64,
    /// 最近一次 signal 產出的 wall-clock ms。
    last_signal_ms: AtomicU64,
}

impl SignalStats {
    pub fn new() -> Self {
        Self {
            signals_emitted_total: AtomicU64::new(0),
            last_signal_ms: AtomicU64::new(0),
        }
    }

    /// hot path 接點：step_3_signals.rs evaluate 後 signal 非空時呼一次。
    ///
    /// `count` 為本 tick signal 數；`now_ms` 為 caller 端 wall-clock。
    pub fn inc_signal_batch(&self, count: u64, now_ms: u64) {
        if count == 0 {
            return;
        }
        self.signals_emitted_total.fetch_add(count, Ordering::Relaxed);
        self.last_signal_ms.store(now_ms, Ordering::Relaxed);
    }

    /// 讀取累計 signal 數；emitter delta 計算 per-minute rate。
    pub fn signals_emitted_total(&self) -> u64 {
        self.signals_emitted_total.load(Ordering::Relaxed)
    }

    /// 最近一次 signal 產出 wall-clock；0 表 cold-start。
    pub fn last_signal_ms(&self) -> u64 {
        self.last_signal_ms.load(Ordering::Relaxed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_starts_at_zero() {
        let s = SignalStats::new();
        assert_eq!(s.signals_emitted_total(), 0);
        assert_eq!(s.last_signal_ms(), 0);
    }

    #[test]
    fn test_inc_signal_batch_skips_zero() {
        let s = SignalStats::new();
        s.inc_signal_batch(0, 1_700_000_000_000);
        // count=0 不前進 counter 也不更新 ts (反假陽性 keep cold-start)
        assert_eq!(s.signals_emitted_total(), 0);
        assert_eq!(s.last_signal_ms(), 0);
    }

    #[test]
    fn test_inc_signal_batch_accumulates() {
        let s = SignalStats::new();
        s.inc_signal_batch(3, 1_700_000_000_000);
        assert_eq!(s.signals_emitted_total(), 3);
        assert_eq!(s.last_signal_ms(), 1_700_000_000_000);

        s.inc_signal_batch(2, 1_700_000_060_000);
        assert_eq!(s.signals_emitted_total(), 5);
        assert_eq!(s.last_signal_ms(), 1_700_000_060_000);
    }
}
