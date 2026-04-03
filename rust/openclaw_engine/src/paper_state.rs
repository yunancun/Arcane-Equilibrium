//! Paper Trading State — position tracking + PnL (R04-7).
//! 紙盤交易狀態 — 持倉追蹤 + 損益。

use openclaw_core::stop_manager::{self, PositionState, StopConfig, StopTrigger};
use serde::{Deserialize, Serialize};
use std::collections::HashMap;

/// A paper trading position.
/// 紙盤交易持倉。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaperPosition {
    pub symbol: String,
    pub is_long: bool,
    pub qty: f64,
    pub entry_price: f64,
    pub best_price: f64,
    pub entry_fee: f64,
    pub entry_ts_ms: u64,
    pub unrealized_pnl: f64,
}

/// Paper trading state manager.
/// 紙盤交易狀態管理器。
pub struct PaperState {
    _initial_balance: f64,
    balance: f64,
    peak_balance: f64,
    positions: HashMap<String, PaperPosition>,
    latest_prices: HashMap<String, f64>,
    total_realized_pnl: f64,
    total_fees: f64,
    trade_count: u32,
    stop_config: StopConfig,
    forced_drawdown: f64,
}

impl PaperState {
    pub fn new(initial_balance: f64) -> Self {
        Self {
            _initial_balance: initial_balance,
            balance: initial_balance,
            peak_balance: initial_balance,
            positions: HashMap::new(),
            latest_prices: HashMap::new(),
            total_realized_pnl: 0.0,
            total_fees: 0.0,
            trade_count: 0,
            stop_config: StopConfig::default(),
            forced_drawdown: 0.0,
        }
    }

    pub fn balance(&self) -> f64 { self.balance }

    pub fn position_count(&self) -> usize { self.positions.len() }

    pub fn positions(&self) -> Vec<&PaperPosition> {
        self.positions.values().collect()
    }

    /// Get a specific position by symbol (for duplicate check).
    /// 按交易對獲取特定持倉（用於重複檢查）。
    pub fn get_position(&self, symbol: &str) -> Option<&PaperPosition> {
        self.positions.get(symbol)
    }

    pub fn drawdown_pct(&self) -> f64 {
        if self.forced_drawdown > 0.0 { return self.forced_drawdown; }
        if self.peak_balance <= 0.0 { return 0.0; }
        (self.peak_balance - self.balance) / self.peak_balance * 100.0
    }

    pub fn latest_price(&self, symbol: &str) -> Option<f64> {
        self.latest_prices.get(symbol).copied()
    }

    pub fn set_latest_price(&mut self, symbol: &str, price: f64) {
        self.latest_prices.insert(symbol.to_string(), price);
    }

    /// For testing: force a specific drawdown percentage.
    /// 用於測試：強制特定回撤百分比。
    pub fn force_drawdown(&mut self, pct: f64) {
        self.forced_drawdown = pct;
    }

    /// Apply a fill to paper state.
    /// 在紙盤狀態上應用成交。
    pub fn apply_fill(
        &mut self, symbol: &str, is_long: bool, qty: f64,
        fill_price: f64, fee: f64, ts_ms: u64,
    ) {
        self.balance -= fee;
        self.total_fees += fee;
        self.set_latest_price(symbol, fill_price);

        if let Some(pos) = self.positions.get(symbol) {
            if pos.is_long != is_long {
                // Closing position (opposite direction)
                // 平倉（反方向）
                let close_qty = pos.qty.min(qty);
                let pnl = if pos.is_long {
                    (fill_price - pos.entry_price) * close_qty
                } else {
                    (pos.entry_price - fill_price) * close_qty
                };
                self.balance += pnl;
                self.total_realized_pnl += pnl;
                self.trade_count += 1;
                self.positions.remove(symbol);
                self.peak_balance = self.peak_balance.max(self.balance);
                return;
            } else {
                // Same direction — accumulate (weighted average entry price)
                // 同方向 — 累加（加權平均入場價）
                let old_qty = pos.qty;
                let old_entry = pos.entry_price;
                let new_qty = old_qty + qty;
                let avg_entry = (old_entry * old_qty + fill_price * qty) / new_qty;
                let mut updated = pos.clone();
                updated.qty = new_qty;
                updated.entry_price = avg_entry;
                updated.entry_fee += fee;
                self.positions.insert(symbol.to_string(), updated);
                return;
            }
        }

        // Opening new position (no existing position for this symbol)
        // 開新倉（此交易對無現有持倉）
        self.positions.insert(symbol.to_string(), PaperPosition {
            symbol: symbol.to_string(),
            is_long,
            qty,
            entry_price: fill_price,
            best_price: fill_price,
            entry_fee: fee,
            entry_ts_ms: ts_ms,
            unrealized_pnl: 0.0,
        });
    }

    /// Close a position at market price.
    /// 以市場價平倉。
    pub fn close_position(&mut self, symbol: &str, price: f64, _ts_ms: u64) {
        if let Some(pos) = self.positions.remove(symbol) {
            let pnl = if pos.is_long {
                (price - pos.entry_price) * pos.qty
            } else {
                (pos.entry_price - price) * pos.qty
            };
            self.balance += pnl;
            self.total_realized_pnl += pnl;
            self.trade_count += 1;
            self.peak_balance = self.peak_balance.max(self.balance);
        }
    }

    /// Check stops on all positions using per-symbol latest prices.
    /// 使用每個交易對的最新價格檢查所有持倉的止損。
    pub fn check_stops(&mut self, _price: f64, now_ms: u64) -> Vec<(String, StopTrigger)> {
        let mut triggers = Vec::new();
        let latest = self.latest_prices.clone();
        for (symbol, pos) in &mut self.positions {
            let sym_price = match latest.get(symbol.as_str()) {
                Some(&p) => p,
                None => continue, // no price yet for this symbol
            };
            let mut ps = PositionState {
                entry_price: pos.entry_price,
                best_price: pos.best_price,
                is_long: pos.is_long,
                entry_ts_ms: pos.entry_ts_ms,
            };
            stop_manager::update_best_price(&mut ps, sym_price);
            pos.best_price = ps.best_price;

            if let Some(trigger) = stop_manager::check_stops(&self.stop_config, &ps, sym_price, now_ms) {
                triggers.push((symbol.clone(), trigger));
            }
        }
        triggers
    }

    /// Export state for persistence (with real-time unrealized PnL).
    /// 導出狀態用於持久化（含即時未實現損益）。
    pub fn export_state(&self) -> PaperStateSnapshot {
        let positions: Vec<PaperPosition> = self.positions.values().map(|pos| {
            // Compute real unrealized PnL using latest price for this symbol (QC fix).
            // 使用該交易對最新價格計算真實未實現損益。
            let current_price = self.latest_prices.get(&pos.symbol).copied().unwrap_or(pos.entry_price);
            let unrealized_pnl = if pos.is_long {
                (current_price - pos.entry_price) * pos.qty
            } else {
                (pos.entry_price - current_price) * pos.qty
            };
            PaperPosition {
                unrealized_pnl,
                ..pos.clone()
            }
        }).collect();
        PaperStateSnapshot {
            balance: self.balance,
            peak_balance: self.peak_balance,
            total_realized_pnl: self.total_realized_pnl,
            total_fees: self.total_fees,
            trade_count: self.trade_count,
            positions,
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaperStateSnapshot {
    pub balance: f64,
    pub peak_balance: f64,
    pub total_realized_pnl: f64,
    pub total_fees: f64,
    pub trade_count: u32,
    pub positions: Vec<PaperPosition>,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_initial_state() {
        let s = PaperState::new(10000.0);
        assert_eq!(s.balance(), 10000.0);
        assert_eq!(s.position_count(), 0);
        assert_eq!(s.drawdown_pct(), 0.0);
    }

    #[test]
    fn test_open_and_close_long() {
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 2.75, 0);
        assert_eq!(s.position_count(), 1);

        s.close_position("BTC", 51000.0, 1000);
        assert_eq!(s.position_count(), 0);
        // PnL: (51000-50000) * 0.1 = 100 - 2.75 fee = 97.25
        assert!((s.balance() - 10097.25).abs() < 0.01);
    }

    #[test]
    fn test_open_and_close_short() {
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", false, 0.1, 50000.0, 2.75, 0);
        s.close_position("BTC", 49000.0, 1000);
        // PnL: (50000-49000) * 0.1 = 100 - 2.75 fee
        assert!((s.balance() - 10097.25).abs() < 0.01);
    }

    #[test]
    fn test_drawdown() {
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0);
        s.close_position("BTC", 45000.0, 1000);
        // Loss: (45000-50000) * 0.1 = -500
        assert!(s.drawdown_pct() > 0.0);
    }

    #[test]
    fn test_stop_check() {
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0);
        s.set_latest_price("BTC", 46000.0); // per-symbol price for stop check
        let triggers = s.check_stops(46000.0, 1000);
        assert_eq!(triggers.len(), 1); // hard stop at 5%
    }

    #[test]
    fn test_latest_price() {
        let mut s = PaperState::new(10000.0);
        s.set_latest_price("BTC", 50000.0);
        assert_eq!(s.latest_price("BTC"), Some(50000.0));
        assert_eq!(s.latest_price("ETH"), None);
    }

    #[test]
    fn test_export_state() {
        let s = PaperState::new(10000.0);
        let snap = s.export_state();
        assert_eq!(snap.balance, 10000.0);
        assert!(snap.positions.is_empty());
    }

    #[test]
    fn test_same_direction_accumulates() {
        // Same-direction fills should accumulate qty with weighted avg entry.
        // 同方向成交應累加 qty 並加權平均入場價。
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 1.0, 0);  // buy 0.1 @ 50000
        s.apply_fill("BTC", true, 0.1, 52000.0, 1.0, 1000); // buy 0.1 @ 52000
        assert_eq!(s.position_count(), 1);
        let pos = s.get_position("BTC").unwrap();
        assert!((pos.qty - 0.2).abs() < 1e-10);  // 0.1 + 0.1
        assert!((pos.entry_price - 51000.0).abs() < 0.01); // avg(50000, 52000)
    }

    #[test]
    fn test_same_direction_does_not_reset_entry() {
        // Verify same-direction fill doesn't replace position (old bug: insert overwrites).
        // 驗證同方向成交不會覆蓋持倉（舊 bug：insert 直接替換）。
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", false, 0.05, 60000.0, 0.5, 0);
        let initial_fee = s.get_position("BTC").unwrap().entry_fee;
        s.apply_fill("BTC", false, 0.05, 61000.0, 0.5, 1000);
        let pos = s.get_position("BTC").unwrap();
        assert!((pos.qty - 0.10).abs() < 1e-10);
        assert!((pos.entry_price - 60500.0).abs() < 0.01);
        assert!((pos.entry_fee - 1.0).abs() < 1e-10); // accumulated fees
    }

    #[test]
    fn test_opposite_direction_closes() {
        // Opposite direction fill closes the position with PnL.
        // 反方向成交平倉並計算 PnL。
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0);
        s.apply_fill("BTC", false, 0.1, 51000.0, 0.0, 1000); // close
        assert_eq!(s.position_count(), 0);
        assert!((s.total_realized_pnl - 100.0).abs() < 0.01); // (51000-50000)*0.1
    }

    #[test]
    fn test_get_position() {
        let mut s = PaperState::new(10000.0);
        assert!(s.get_position("BTC").is_none());
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0);
        assert!(s.get_position("BTC").is_some());
        assert!(s.get_position("ETH").is_none());
    }
}
