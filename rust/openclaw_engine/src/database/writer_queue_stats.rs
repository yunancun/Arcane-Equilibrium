//! PG market_writer mpsc queue depth 統計 — Sprint 5+ Track C real probe。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/specs/2026-05-23--sprint5_wave1_4_3_5_6_track_b_c_real_probes.md §3.2：
//!   提供 `database_pool` domain `writer_queue_probe` 真實資料源。tokio mpsc
//!   `Sender::capacity()` 返「剩餘 permits」；`MAX_CAP - capacity = current
//!   in-flight queue depth`。本 struct 包裝該邏輯，main_health_emitters.rs 端
//!   構造 closure 把 `current_depth()` 接 `WriterQueueProbe` typedef。
//!
//! 主要類 / 函數:
//!   - `WriterQueueStats`：持有 `Arc<Sender<MarketDataMsg>>` 與 `capacity_max`。
//!   - `current_depth()`：`capacity_max - tx.capacity()`，u32 cap。
//!
//! 依賴:
//!   - `tokio::sync::mpsc::Sender` + `super::MarketDataMsg`。
//!   - 0 額外 crate。
//!
//! 硬邊界:
//!   - **Sender::capacity() 語意是剩餘 permits 非總容量**（per spec §5 E2 重點
//!     審查 #3 + spec §3.2 設計）；本 IMPL 嚴守此語意。
//!   - tasks.rs 端 `Arc::new(market_tx)` 不破任何 caller — `Arc<Sender>` deref
//!     透明，`Arc<Sender>::clone()` 共享同 channel handle（per `feedback_working
//!     _principles` 範圍最小化）。
//!   - 0 trading 路徑滲透：只觀測 channel capacity，不寫入 / 不關閉 channel。

use std::sync::Arc;

use tokio::sync::mpsc::Sender;

use super::MarketDataMsg;

/// 持有 market_tx Arc + 預設 max capacity，提供 emitter 端 depth accessor。
///
/// 為什麼 `Arc<Sender>`：
///   - tasks.rs 既有 `market_tx: Sender<MarketDataMsg>` 已是 `Clone` handle；
///     `Arc` 包裝 + clone 在 caller 端透明（per spec §5 item 2 + §6 副作用清單）。
///   - 同時也可以走 `Sender::clone()`，但 Arc 顯式表達「同 handle 共享」語意，
///     對 review 更友善。
///
/// 為什麼 capacity_max 是 ctor 時固定常量：
///   - tokio mpsc 不暴 channel 構造後總容量；caller 端記住傳入即可
///     (tasks.rs `mpsc::channel(4096)` → ctor 端 `WriterQueueStats::new(_, 4096)`）。
///   - 若實際 capacity > capacity_max（hypothesis impossible — channel 容量固定），
///     `saturating_sub` 守住非負。
pub struct WriterQueueStats {
    market_tx: Arc<Sender<MarketDataMsg>>,
    capacity_max: u32,
}

impl WriterQueueStats {
    /// 建構：caller 必傳 channel handle Arc + 構造時 max capacity。
    ///
    /// 為什麼不從 tx 反推 max：tokio `Sender` 0.x API 無 `max_capacity()` accessor
    /// 暴露；caller 端記住傳入是唯一可靠途徑。
    pub fn new(market_tx: Arc<Sender<MarketDataMsg>>, capacity_max: u32) -> Self {
        Self {
            market_tx,
            capacity_max,
        }
    }

    /// 當前 in-flight queue depth：`MAX_CAP - capacity_remaining`。
    ///
    /// 為什麼 saturating_sub：
    ///   - 防 Sender::capacity() 由於 producer / consumer race 短暫返回值 >
    ///     `capacity_max` 的 edge case（雖然 tokio 0.x 應該不會發生，留兜底）。
    ///   - tokio mpsc 0.x 文件保 capacity ≤ initial buffer size，但 race-free
    ///     並非絕對；保守 fail-soft（per `feedback_no_dead_params` 反假陽性）。
    pub fn current_depth(&self) -> u32 {
        let remaining = self.market_tx.capacity() as u32;
        self.capacity_max.saturating_sub(remaining)
    }

    /// emitter 端 typedef `WriterQueueProbe = Arc<dyn Fn() -> u32 + ...>` 接點。
    ///
    /// 為什麼 helper：caller 端常以 `Arc<dyn Fn>` 注入；本 method 不直接返
    /// closure，由 main_health_emitters.rs 端 `move ||` 包裝（避此檔依賴
    /// emitter typedef）。
    pub fn capacity_max(&self) -> u32 {
        self.capacity_max
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tokio::sync::mpsc;

    #[tokio::test]
    async fn test_empty_channel_returns_zero_depth() {
        let (tx, _rx) = mpsc::channel::<MarketDataMsg>(100);
        let stats = WriterQueueStats::new(Arc::new(tx), 100);
        assert_eq!(stats.current_depth(), 0, "empty channel → depth 0");
    }

    #[tokio::test]
    async fn test_partially_filled_channel_reflects_depth() {
        let (tx, _rx) = mpsc::channel::<MarketDataMsg>(100);
        // 灌 30 條（_rx 不取）→ remaining capacity = 70 → depth = 30
        for _ in 0..30 {
            tx.try_send(MarketDataMsg::Liquidation {
                ts_ms: 0,
                symbol: "BTCUSDT".to_string(),
                side: "Buy".to_string(),
                qty: 0.0,
                price: 0.0,
            })
            .ok();
        }
        let stats = WriterQueueStats::new(Arc::new(tx), 100);
        assert_eq!(stats.current_depth(), 30, "in-flight depth = sent count");
    }

    #[tokio::test]
    async fn test_capacity_max_accessor() {
        let (tx, _rx) = mpsc::channel::<MarketDataMsg>(4096);
        let stats = WriterQueueStats::new(Arc::new(tx), 4096);
        assert_eq!(stats.capacity_max(), 4096);
    }

    #[tokio::test]
    async fn test_saturating_sub_on_unexpected_capacity_overflow() {
        // 假設 tokio 0.x 異常 race 給回 capacity > capacity_max（normally
        // impossible，留兜底）。
        let (tx, _rx) = mpsc::channel::<MarketDataMsg>(100);
        // 用 capacity_max=50 < actual=100 來模擬「caller 寫錯 max」
        let stats = WriterQueueStats::new(Arc::new(tx), 50);
        // capacity()=100; 50 - 100 saturating = 0（不 wrap）
        assert_eq!(stats.current_depth(), 0, "saturating_sub 守 0 不 wrap");
    }
}
