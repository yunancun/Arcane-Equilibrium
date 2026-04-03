//! Strategy modules — 5 trading strategies (R04-5).
//! 策略模組 — 5 個交易策略。

pub mod bb_breakout;
pub mod bb_reversion;
pub mod funding_arb;
pub mod grid_trading;
pub mod ma_crossover;

use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

/// Strategy trait — implement for each trading strategy.
/// 策略 trait — 為每個交易策略實現。
/// Send required for tokio::spawn compatibility.
pub trait Strategy: Send {
    /// Strategy name for logging and attribution.
    /// 策略名稱用於日誌和歸因。
    fn name(&self) -> &str;

    /// Is this strategy currently active?
    /// 此策略當前是否活躍？
    fn is_active(&self) -> bool;

    /// Process a tick and return trade intents.
    /// 處理 tick 並返回交易意圖。
    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent>;
}
