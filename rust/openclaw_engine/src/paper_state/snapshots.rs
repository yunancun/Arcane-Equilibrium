//! Paper Trading snapshots — serialisable state exports for persistence / IPC.
//! 紙盤交易快照 — 可序列化的狀態導出，用於持久化 / IPC。
//!
//! MODULE_NOTE (EN): Owns the snapshot DTOs (`PositionSnapshot`,
//!   `PaperStateSnapshot`) and the `PaperState::export_state` constructor that
//!   builds them with live unrealized-PnL recomputation. Split out of
//!   `paper_state.rs` in E5-P1-1 (2026-04-18) so the large snapshot shape isn't
//!   co-located with state mutation logic.
//! MODULE_NOTE (中): 持有快照 DTO（PositionSnapshot、PaperStateSnapshot）與建構器
//!   `PaperState::export_state`（同時重算即時未實現損益）。2026-04-18 E5-P1-1 自
//!   paper_state.rs 拆出，避免快照形狀與狀態變更邏輯混在同一檔。

use super::containers::PaperPosition;
use super::PaperState;
use serde::{Deserialize, Serialize};

/// Per-position snapshot with optional API PnL for comparison (M5 fix).
/// 每倉位快照，含可選 API PnL 對比（M5 修復）。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PositionSnapshot {
    #[serde(flatten)]
    pub position: PaperPosition,
    /// API-reported unrealized PnL (from Bybit WS position updates).
    /// API 報告的未實現損益（來自 Bybit WS 持倉更新）。
    #[serde(skip_serializing_if = "Option::is_none")]
    pub api_pnl: Option<f64>,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaperStateSnapshot {
    pub balance: f64,
    /// The balance the engine was initialized with (never changes after startup).
    /// 引擎啟動時的初始餘額（啟動後永不改變）。
    pub initial_balance: f64,
    pub peak_balance: f64,
    pub total_realized_pnl: f64,
    pub total_fees: f64,
    #[serde(default)]
    pub total_funding_pnl: f64,
    pub trade_count: u32,
    pub positions: Vec<PositionSnapshot>,
    /// Bybit Demo sync balance for comparison (None = custom mode).
    /// Bybit Demo 同步餘額用於對比（None = 自設金額模式）。
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bybit_sync_balance: Option<f64>,
}

impl PaperState {
    /// Export state for persistence (with real-time unrealized PnL).
    /// 導出狀態用於持久化（含即時未實現損益）。
    pub fn export_state(&self) -> PaperStateSnapshot {
        let positions: Vec<PositionSnapshot> = self
            .positions
            .values()
            .map(|pos| {
                // Compute real unrealized PnL using latest price for this symbol (QC fix).
                // 使用該交易對最新價格計算真實未實現損益。
                let current_price = self
                    .latest_prices
                    .get(&pos.symbol)
                    .copied()
                    .unwrap_or(pos.entry_price);
                let unrealized_pnl = if pos.is_long {
                    (current_price - pos.entry_price) * pos.qty
                } else {
                    (pos.entry_price - current_price) * pos.qty
                };
                PositionSnapshot {
                    position: PaperPosition {
                        unrealized_pnl,
                        ..pos.clone()
                    },
                    api_pnl: self.api_unrealized_pnl.get(&pos.symbol).copied(),
                }
            })
            .collect();
        PaperStateSnapshot {
            balance: self.balance,
            initial_balance: self._initial_balance,
            peak_balance: self.peak_balance,
            total_realized_pnl: self.total_realized_pnl,
            total_fees: self.total_fees,
            total_funding_pnl: self.total_funding_pnl,
            trade_count: self.trade_count,
            positions,
            bybit_sync_balance: self.bybit_sync_balance,
        }
    }
}
