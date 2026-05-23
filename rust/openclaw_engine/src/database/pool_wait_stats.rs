//! PG pool acquire wait latency p95 直方統計 — Sprint 5+ Track C real probe。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md §3.3：
//!   sqlx 0.8 未暴露 pool 內部 wait metric histogram；走「自建包裝
//!   `Pool::acquire()` 計時」approach — caller hot-path（market_writer /
//!   trading_writer）透過 `pool_acquire_with_stats(pool, stats)` helper 取
//!   connection，wait latency 寫入此 stats 的滑動窗口；emitter 端 5min 一次
//!   sample 走 `p95_ms()` 投影。
//!
//! 主要類 / 函數:
//!   - `PoolWaitStats`：parking_lot::Mutex 包裝 `VecDeque<u32>`，300-sample sliding
//!     window。
//!   - `record_wait_ms(u32)`：caller 端 helper 包裝 acquire 後 push_back（capacity
//!     滿走 pop_front）。
//!   - `p95_ms()`：emitter 端 5min sample；sort + index `(n × 0.95)`。
//!
//!   為什麼 300 sample（per spec §3.3 line 304）：
//!     5min window × ~1 acquire/sec average dispatch frequency ≈ 300。
//!     高頻 hot-path 25 acquire/sec 高峰 → 1500 sample/min；300 = 12 sec 平滑窗。
//!
//!   為什麼 sliding window 而非 EWMA（per spec §3.3 註解）:
//!     p95 = 分位數估計；EWMA 是平均，不適用分位數。
//!
//! 依賴:
//!   - `parking_lot::Mutex`（既有 dep，非 hot path 鎖）。
//!   - 0 額外 crate。
//!
//! 硬邊界:
//!   - hot path 端走 `record_wait_ms` 是 `Mutex::lock` 持有 < 10us（push_back +
//!     pop_front O(1)）；hot-path latency 影響可忽略（per spec §3.3 E2 重點審查
//!     #2 lock 時段）。
//!   - emitter 端 `p95_ms()` 是 `Mutex::lock` 持有 ~50us（VecDeque clone +
//!     `sort_unstable`）；5min sample 一次接受。
//!   - record 與 read 用同一 parking_lot::Mutex；無 priority inversion。
//!   - 樣本 cap 在 300；不漲記憶體（per `feedback_no_dead_params` 反洩漏）。
//!   - failure path 也 record（per spec §5 E2 重點審查 #4：失敗也是觀測樣本）；
//!     caller 端 helper 控制此語意。

use std::collections::VecDeque;

use parking_lot::Mutex;

/// 滑動窗口最大 sample 數（per spec §3.3 line 304）。
const CAPACITY: usize = 300;

/// PG pool acquire wait latency p95 histogram（300-sample sliding window）。
pub struct PoolWaitStats {
    samples_ms: Mutex<VecDeque<u32>>,
}

impl PoolWaitStats {
    pub fn new() -> Self {
        Self {
            samples_ms: Mutex::new(VecDeque::with_capacity(CAPACITY)),
        }
    }

    /// caller 端 helper 包裝 acquire 後呼此 fn 記 wait 時段。
    ///
    /// 為什麼 u32 ms：
    ///   - wait 時段在毫秒級；overflow > u32::MAX ≈ 49 天，不可能（acquire timeout
    ///     遠小於此），cap 在 caller 端用 `min(u32::MAX as u128)`。
    ///
    /// 為什麼 push_back + pop_front 而非 sort-on-write：
    ///   - hot path 0 sort 開銷；只在 read 端 sort（5min/次）。
    pub fn record_wait_ms(&self, ms: u32) {
        let mut g = self.samples_ms.lock();
        if g.len() >= CAPACITY {
            g.pop_front();
        }
        g.push_back(ms);
    }

    /// 當前 sample size；test / observability 用。
    pub fn sample_count(&self) -> usize {
        self.samples_ms.lock().len()
    }

    /// p95 ms：sort + index `(n × 0.95)`。
    ///
    /// 為什麼 `sort_unstable`：
    ///   - u32 已是 total order；不需 stable sort。
    ///   - `sort_unstable` 比 `sort` 快 20-50%（per std 文件）。
    ///
    /// 為什麼 idx = `min(n - 1)`：
    ///   - n × 0.95 對 n=10 = 9.5 → as usize = 9 = n - 1（正確）；對 n=20 = 19 = n - 1。
    ///   - 對 n=21 = 19.95 → as usize = 19 < n - 1 (=20)（正確）。
    ///   - cap 在 n - 1 防 n=1 (idx=0) edge case。
    ///
    /// 為什麼 empty 返 0：per `feedback_no_dead_params` cold-start OK band fail-soft；
    /// classify 端 0 ms 走 OK band 不誤升 WARN/DEGRADED。
    pub fn p95_ms(&self) -> u32 {
        let g = self.samples_ms.lock();
        if g.is_empty() {
            return 0;
        }
        let mut v: Vec<u32> = g.iter().copied().collect();
        drop(g); // 提早釋放 Mutex，sort 不佔鎖
        v.sort_unstable();
        let idx = ((v.len() as f64 * 0.95) as usize).min(v.len() - 1);
        v[idx]
    }
}

impl Default for PoolWaitStats {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_empty_returns_zero_p95() {
        let s = PoolWaitStats::new();
        assert_eq!(s.p95_ms(), 0, "empty → 0 OK band placeholder");
        assert_eq!(s.sample_count(), 0);
    }

    #[test]
    fn test_single_sample_returns_itself() {
        let s = PoolWaitStats::new();
        s.record_wait_ms(42);
        // n=1, idx = (1*0.95) as usize = 0 (cap n-1=0)
        assert_eq!(s.p95_ms(), 42);
    }

    #[test]
    fn test_100_samples_p95_is_top_5_percent() {
        let s = PoolWaitStats::new();
        // 寫 0..100 順序；sort 後 idx=(100*0.95)=95 → samples[95]=95
        for i in 0..100u32 {
            s.record_wait_ms(i);
        }
        assert_eq!(s.p95_ms(), 95);
    }

    #[test]
    fn test_sliding_window_drops_oldest_at_capacity() {
        let s = PoolWaitStats::new();
        // 寫 350 條，前 50 條應被丟（300 capacity）
        for i in 0..350u32 {
            s.record_wait_ms(i);
        }
        assert_eq!(s.sample_count(), CAPACITY);
        // sample = 50..350; sort → 50..350; n=300; idx=(300*0.95)=285;
        // samples[285] = 50 + 285 = 335
        assert_eq!(s.p95_ms(), 335);
    }

    #[test]
    fn test_p95_handles_unsorted_input() {
        let s = PoolWaitStats::new();
        // 亂序寫，內部 sort 後 p95 結果正確
        let unsorted = [50u32, 10, 90, 30, 70, 20, 80, 40, 60, 100];
        for v in unsorted {
            s.record_wait_ms(v);
        }
        // sort → [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        // n=10; idx=(10*0.95)=9 (cap n-1=9); samples[9]=100
        assert_eq!(s.p95_ms(), 100);
    }
}
