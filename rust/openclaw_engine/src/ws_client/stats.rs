//! WS 客戶端 hot-path 統計 — Sprint 5+ Track B real probe SSOT。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md §2.2：
//!   為 `RealPipelineThroughputSource` 提供 `current_ws_tick_rate_per_sec` 與
//!   `current_ws_heartbeat_lag_ms` 兩 metric 的累積資料源。dispatch.rs hot path
//!   每解一條 ws 訊息且確實產出 PriceEvent 後呼 `inc_tick(now_ms)`；emitter 端
//!   30s sample 走 delta count / elapsed seconds 推算 tick rate，並讀
//!   `last_tick_ms()` 算 heartbeat lag。
//!
//! 主要類 / 函數:
//!   - `WsStats`：兩 AtomicU64 計數器（total_tick_count / last_tick_ms）。
//!   - `WsStats::inc_tick`：dispatch.rs hot path 接點；fetch_add + store 兩 atomic
//!     op，無鎖。
//!   - `WsStats::total_tick_count` / `last_tick_ms`：emitter 端讀取 accessor。
//!
//! 依賴:
//!   - 0 外部 crate（std::sync::atomic 既有 dep）。
//!
//! 硬邊界:
//!   - hot path 必走 `Ordering::Relaxed`；計數器語意不要求 happens-before（per
//!     spec §5 E2 重點審查 #2）。
//!   - 0 trading 路徑滲透；觀測層只讀寫自身 counter。
//!   - 任一 caller 不接入 `inc_tick` → counter 永遠 0；emitter 端走 cold-start
//!     placeholder fail-soft（per `feedback_no_dead_params` 反假陽性）。

use std::sync::atomic::{AtomicU64, Ordering};

/// WS 客戶端 tick 與 heartbeat 統計。
///
/// 為什麼 AtomicU64 而非 Mutex：
///   - hot path 每條 ws 訊息調 `inc_tick`；Mutex 鎖開銷 vs Atomic fetch_add 是
///     0.1us vs 5ns 量級差距，per `feedback_working_principles` 範圍最小化 +
///     觀測層 0 性能退化（per spec AC-4 + E5 `hot_path_baseline` 不退）。
///   - 計數器語意（單調遞增 + 最新值覆寫）天然 atomic-friendly；無 read-modify-
///     write 競爭。
///
/// 為什麼分離 last_tick_ms 為獨立 atomic：
///   - heartbeat lag 需要「最新一筆 tick wall-clock」；不能由 tick_count 推算。
///   - `store(Ordering::Relaxed)` 對齊 fetch_add；reader 看到的 last_tick_ms
///     可能對應上一個 inc_tick 而非本次（最多 1 個 tick interval 滯後），對 30s
///     sample emitter 來說可接受。
#[derive(Debug, Default)]
pub struct WsStats {
    /// 累計 ws message dispatch 成功次數（即實際產出至少 1 PriceEvent）。
    /// 從進程啟動單調遞增；無 reset 設計。
    total_tick_count: AtomicU64,
    /// 最近一次 inc_tick 寫入的 wall-clock ms (unix epoch)。
    /// cold-start 為 0；reader 端看到 0 應走 placeholder fail-soft。
    last_tick_ms: AtomicU64,
}

impl WsStats {
    /// 建立全 0 計數器。
    pub fn new() -> Self {
        Self {
            total_tick_count: AtomicU64::new(0),
            last_tick_ms: AtomicU64::new(0),
        }
    }

    /// hot path 接點：解到實際 PriceEvent 後呼一次。
    ///
    /// `now_ms` 由 caller 提供（per dispatch.rs 既有 `now_ms()` helper），避免
    /// 此檔依賴 wall-clock 模塊（保此檔可獨立 test）。
    pub fn inc_tick(&self, now_ms: u64) {
        self.total_tick_count.fetch_add(1, Ordering::Relaxed);
        self.last_tick_ms.store(now_ms, Ordering::Relaxed);
    }

    /// 讀取累計 tick 次數；emitter 端 delta 計算 rate。
    pub fn total_tick_count(&self) -> u64 {
        self.total_tick_count.load(Ordering::Relaxed)
    }

    /// 讀取最近一次 inc_tick 的 wall-clock ms；emitter 端 now - last 算 lag。
    /// 0 表 cold-start 從未收 tick。
    pub fn last_tick_ms(&self) -> u64 {
        self.last_tick_ms.load(Ordering::Relaxed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_new_starts_at_zero() {
        let s = WsStats::new();
        assert_eq!(s.total_tick_count(), 0);
        assert_eq!(s.last_tick_ms(), 0);
    }

    #[test]
    fn test_inc_tick_updates_count_and_last_ms() {
        let s = WsStats::new();
        s.inc_tick(1_700_000_000_000);
        assert_eq!(s.total_tick_count(), 1);
        assert_eq!(s.last_tick_ms(), 1_700_000_000_000);

        s.inc_tick(1_700_000_001_000);
        assert_eq!(s.total_tick_count(), 2);
        assert_eq!(s.last_tick_ms(), 1_700_000_001_000);
    }

    #[test]
    fn test_default_equiv_to_new() {
        let s1 = WsStats::default();
        let s2 = WsStats::new();
        assert_eq!(s1.total_tick_count(), s2.total_tick_count());
        assert_eq!(s1.last_tick_ms(), s2.last_tick_ms());
    }
}
