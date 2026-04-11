//! Paper Trading State — position tracking + PnL (R04-7).
//! 紙盤交易狀態 — 持倉追蹤 + 損益。
//!
//! MODULE_NOTE (EN): Manages simulated positions, fills, balance, and PnL for
//!   paper/demo/live modes. apply_fill() updates positions; mark_to_market()
//!   computes unrealized PnL each tick. Thread-safe: sole-owner in TickPipeline.
//! MODULE_NOTE (中): 管理紙盤/Demo/Live 模式的模擬持倉、成交、餘額和損益。
//!   apply_fill() 更新持倉；mark_to_market() 每 tick 計算未實現損益。
//!   線程安全：TickPipeline 獨佔所有權。

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
    /// Per-symbol 24h turnover for dynamic slippage calculation.
    /// 每交易對 24h 成交額，用於動態滑點計算。
    latest_turnovers: HashMap<String, f64>,
    total_realized_pnl: f64,
    total_fees: f64,
    trade_count: u32,
    stop_config: StopConfig,
    forced_drawdown: f64,
    /// Bybit Demo account real balance (Mode B: bybit_sync). None = custom mode.
    /// Bybit Demo 帳戶真實餘額（模式 B：bybit_sync）。None = 自設金額模式。
    bybit_sync_balance: Option<f64>,
    /// API-reported unrealized PnL per symbol (from WS position updates).
    /// API 報告的每交易對未實現損益（來自 WS 持倉更新）。
    api_unrealized_pnl: HashMap<String, f64>,
}

impl PaperState {
    pub fn new(initial_balance: f64) -> Self {
        Self {
            _initial_balance: initial_balance,
            balance: initial_balance,
            peak_balance: initial_balance,
            positions: HashMap::new(),
            latest_prices: HashMap::new(),
            latest_turnovers: HashMap::new(),
            total_realized_pnl: 0.0,
            total_fees: 0.0,
            trade_count: 0,
            stop_config: StopConfig::default(),
            forced_drawdown: 0.0,
            bybit_sync_balance: None,
            api_unrealized_pnl: HashMap::new(),
        }
    }

    pub fn balance(&self) -> f64 {
        self.balance
    }

    // SEC-18: Clamp risk-parameter setters so a hostile/buggy IPC caller cannot
    // disable stops, zero-out timeouts, or invert signs. Values outside the sane
    // operating envelope are silently coerced to the nearest bound.
    // SEC-18：對風控參數 setter 加上邊界，避免 IPC 惡意/錯誤調用關閉止損或倒轉符號。
    // 超出安全運行區間的值會被靜默夾到最近的邊界。

    /// Set hard stop loss percentage. / 設定硬止損百分比。
    pub fn set_hard_stop_pct(&mut self, pct: f64) {
        // Allow between 0.5% (very tight) and 50% (very loose). Reject NaN.
        let v = if pct.is_finite() {
            pct.clamp(0.5, 50.0)
        } else {
            2.0
        };
        self.stop_config.hard_stop_pct = v;
    }

    /// Set trailing stop percentage (None = disabled). / 設定跟蹤止損百分比。
    pub fn set_trailing_stop_pct(&mut self, pct: Option<f64>) {
        self.stop_config.trailing_stop_pct = pct.and_then(|v| {
            if v.is_finite() {
                Some(v.clamp(0.1, 50.0))
            } else {
                None
            }
        });
    }

    /// Set time stop hours (None = disabled). / 設定超時止損小時數。
    pub fn set_time_stop_hours(&mut self, hours: Option<f64>) {
        self.stop_config.time_stop_hours = hours.and_then(|v| {
            if v.is_finite() {
                // Minimum 0.25h (15min) to avoid "instant timeout" weaponisation.
                Some(v.clamp(0.25, 720.0))
            } else {
                None
            }
        });
    }

    /// Set ATR multiplier (None = disabled). / 設定 ATR 乘數。
    pub fn set_atr_multiplier(&mut self, mult: Option<f64>) {
        self.stop_config.atr_multiplier = mult.and_then(|v| {
            if v.is_finite() {
                Some(v.clamp(0.1, 20.0))
            } else {
                None
            }
        });
    }

    /// Set take profit percentage (None = disabled). / 設定止盈百分比。
    pub fn set_take_profit_pct(&mut self, pct: Option<f64>) {
        self.stop_config.take_profit_pct = pct.and_then(|v| {
            if v.is_finite() {
                // Minimum 0.1% so "instant take profit" cannot be triggered.
                Some(v.clamp(0.1, 1000.0))
            } else {
                None
            }
        });
    }

    /// Get current stop config reference. / 獲取當前止損配置引用。
    pub fn stop_config(&self) -> &stop_manager::StopConfig {
        &self.stop_config
    }

    pub fn position_count(&self) -> usize {
        self.positions.len()
    }

    pub fn positions(&self) -> Vec<&PaperPosition> {
        self.positions.values().collect()
    }

    /// Get a specific position by symbol (for duplicate check).
    /// 按交易對獲取特定持倉（用於重複檢查）。
    pub fn get_position(&self, symbol: &str) -> Option<&PaperPosition> {
        self.positions.get(symbol)
    }

    pub fn drawdown_pct(&self) -> f64 {
        if self.forced_drawdown > 0.0 {
            return self.forced_drawdown;
        }
        if self.peak_balance <= 0.0 {
            return 0.0;
        }
        (self.peak_balance - self.balance) / self.peak_balance * 100.0
    }

    pub fn latest_price(&self, symbol: &str) -> Option<f64> {
        self.latest_prices.get(symbol).copied()
    }

    pub fn set_latest_price(&mut self, symbol: &str, price: f64) {
        self.latest_prices.insert(symbol.to_string(), price);
    }

    /// Get latest 24h turnover for a symbol (for dynamic slippage).
    /// 獲取交易對最新 24h 成交額（用於動態滑點）。
    pub fn latest_turnover(&self, symbol: &str) -> Option<f64> {
        self.latest_turnovers.get(symbol).copied()
    }

    pub fn set_latest_turnover(&mut self, symbol: &str, turnover: f64) {
        self.latest_turnovers.insert(symbol.to_string(), turnover);
    }

    /// Set Bybit Demo sync balance (Mode B). Call with None to disable sync mode.
    /// 設定 Bybit Demo 同步餘額（模式 B）。傳 None 關閉同步模式。
    pub fn set_bybit_sync_balance(&mut self, balance: Option<f64>) {
        self.bybit_sync_balance = balance;
    }

    pub fn bybit_sync_balance(&self) -> Option<f64> {
        self.bybit_sync_balance
    }

    /// EXT-1: In exchange mode, correct local balance from exchange wallet balance.
    /// Only applies correction if drift exceeds threshold (avoids micro-corrections on every tick).
    /// EXT-1：交易所模式下，從交易所錢包餘額修正本地餘額。
    /// 僅在偏差超過閾值時修正（避免每個 tick 微修正）。
    pub fn reconcile_balance_from_exchange(&mut self, exchange_balance: f64) -> Option<f64> {
        let drift = (self.balance - exchange_balance).abs();
        let drift_pct = if self.balance > 0.0 {
            drift / self.balance * 100.0
        } else {
            0.0
        };
        // Only correct if drift > 0.1% (avoids float noise)
        if drift_pct > 0.1 {
            let old = self.balance;
            self.balance = exchange_balance;
            self.peak_balance = self.peak_balance.max(exchange_balance);
            Some(old)
        } else {
            None
        }
    }

    /// Set API-reported unrealized PnL for a symbol (from WS position updates).
    /// 設定 API 報告的未實現損益（來自 WS 持倉更新）。
    pub fn set_api_unrealized_pnl(&mut self, symbol: &str, pnl: f64) {
        self.api_unrealized_pnl.insert(symbol.to_string(), pnl);
    }

    pub fn api_unrealized_pnl(&self, symbol: &str) -> Option<f64> {
        self.api_unrealized_pnl.get(symbol).copied()
    }

    /// B-1 Phase 2: Seed paper_state positions from exchange snapshot at startup.
    /// Replaces the entire positions map with the supplied list. Use the tuple
    /// `(symbol, is_long, qty, entry_price, ts_ms)`. Items with qty <= 0.0 or
    /// non-finite price are silently dropped (matches Bybit "size=0" stale rows).
    /// Returns the count of positions actually inserted. The latest_prices map
    /// is also seeded so trailing/stop checks have a non-zero reference price
    /// before the first market tick arrives.
    /// B-1 Phase 2：啟動時用交易所快照種入 paper_state 持倉。
    /// 直接以傳入清單覆蓋整個 positions map。元組格式為
    /// (symbol, is_long, qty, entry_price, ts_ms)。qty <= 0.0 或價格非有限值
    /// 的條目會被靜默丟棄（對應 Bybit 回傳的 "size=0" 殘留行）。
    /// 回傳實際插入的持倉數。同時種入 latest_prices，避免首個市場 tick 抵達前
    /// 跟蹤/止損檢查讀到 0 參考價。
    pub fn import_positions(
        &mut self,
        positions: Vec<(String, bool, f64, f64, u64)>,
    ) -> usize {
        self.positions.clear();
        let mut inserted = 0_usize;
        for (symbol, is_long, qty, entry_price, ts_ms) in positions {
            if qty <= 0.0 || !qty.is_finite() || !entry_price.is_finite() || entry_price <= 0.0 {
                continue;
            }
            self.latest_prices
                .entry(symbol.clone())
                .or_insert(entry_price);
            self.positions.insert(
                symbol.clone(),
                PaperPosition {
                    symbol,
                    is_long,
                    qty,
                    entry_price,
                    best_price: entry_price,
                    entry_fee: 0.0, // exchange did not bill fees through us — leave 0
                    entry_ts_ms: ts_ms,
                    unrealized_pnl: 0.0,
                },
            );
            inserted += 1;
        }
        inserted
    }

    /// B-1 Phase 2: Apply a runtime PositionUpdate from the exchange WS to paper_state.
    /// `size == 0` removes the entry (the exchange just reported a flat position).
    /// `size > 0` upserts using the latest avg entry price reported by the exchange;
    /// existing entries are updated in place so trailing-stop best_price is preserved
    /// when only size/avg_price changed.
    /// Returns true if anything was changed.
    /// B-1 Phase 2：將交易所 WS 推送的 PositionUpdate 應用到 paper_state。
    /// size == 0 表示交易所側已平倉，移除條目。size > 0 則 upsert：若條目存在
    /// 則就地更新（保留 best_price，避免重設跟蹤止損），否則新建。
    /// 任何狀態變動都回傳 true。
    pub fn upsert_position_from_exchange(
        &mut self,
        symbol: &str,
        is_long: bool,
        size: f64,
        avg_price: f64,
        ts_ms: u64,
    ) -> bool {
        if !size.is_finite() || size < 0.0 {
            return false;
        }
        if size == 0.0 {
            return self.positions.remove(symbol).is_some();
        }
        if !avg_price.is_finite() || avg_price <= 0.0 {
            return false;
        }
        match self.positions.get_mut(symbol) {
            Some(pos) => {
                // Capture old direction BEFORE mutating, so the flip-detection
                // comparison still has something meaningful to compare against.
                // 在改寫前先記下舊方向，方向翻轉的判斷才會正確。
                let direction_flipped = pos.is_long != is_long;
                pos.is_long = is_long;
                pos.qty = size;
                pos.entry_price = avg_price;
                // Reset best_price only if direction flipped (different position).
                // Same-direction upsert preserves best_price so trailing-stop tracking
                // does not reset on every WS heartbeat.
                // 方向翻轉視為新倉，best_price 重置；同向僅尺寸/均價變動則保留，
                // 避免每次 WS 心跳重置跟蹤止損狀態。
                if direction_flipped {
                    pos.best_price = avg_price;
                    pos.entry_ts_ms = ts_ms;
                    pos.entry_fee = 0.0;
                }
                true
            }
            None => {
                self.positions.insert(
                    symbol.to_string(),
                    PaperPosition {
                        symbol: symbol.to_string(),
                        is_long,
                        qty: size,
                        entry_price: avg_price,
                        best_price: avg_price,
                        entry_fee: 0.0,
                        entry_ts_ms: ts_ms,
                        unrealized_pnl: 0.0,
                    },
                );
                true
            }
        }
    }

    /// Get hard stop percentage from config (for server-side stop calc).
    /// 從配置獲取硬止損百分比（用於伺服器端止損計算）。
    pub fn stop_config_pct(&self) -> f64 {
        self.stop_config.hard_stop_pct
    }

    /// For testing: force a specific drawdown percentage.
    /// 用於測試：強制特定回撤百分比。
    pub fn force_drawdown(&mut self, pct: f64) {
        self.forced_drawdown = pct;
    }

    /// Read total cumulative fees charged to the paper account (open + close).
    /// 讀取累計手續費（含開倉與平倉）。
    pub fn total_fees(&self) -> f64 {
        self.total_fees
    }

    /// PNL-FIX-2: Charge a standalone fee against the paper account.
    /// Used by `emit_close_fill` so risk/strategy/fast_track closes — which all
    /// route through the synchronous `close_position()` path (no fee param) —
    /// still bill the same maker/taker fee a real close would incur.
    /// `apply_fill` already bills its own fee on the open path; this helper is
    /// strictly for the close-only paths.
    /// PNL-FIX-2：對紙盤帳戶單獨計入一筆費用。
    /// 風控/策略/fast_track 平倉走的是同步 `close_position()` 路徑，原本不收費。
    /// 開倉路徑由 `apply_fill` 自行收費，本 helper 僅供 close-only 路徑使用。
    pub fn charge_fee(&mut self, fee: f64) {
        if fee <= 0.0 || !fee.is_finite() {
            return;
        }
        self.balance -= fee;
        self.total_fees += fee;
    }

    /// Apply a fill to paper state.
    /// 在紙盤狀態上應用成交。
    /// Apply a fill and return the realized PnL (0.0 for opens/accumulates, non-zero for closes).
    /// 應用成交並返回已實現損益（開倉/加倉返回 0.0，平倉返回非零值）。
    pub fn apply_fill(
        &mut self,
        symbol: &str,
        is_long: bool,
        qty: f64,
        fill_price: f64,
        fee: f64,
        ts_ms: u64,
    ) -> f64 {
        // Guard: reject zero-qty fills (prevents ghost positions)
        // 防護：拒絕零數量成交（防止幽靈持倉）
        if qty <= 0.0 || fill_price <= 0.0 {
            return 0.0;
        }
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
                // P0-1 fix: Only remove position if fully closed; reduce qty on partial close
                // P0-1 修復：僅在完全平倉時移除持倉；部分平倉時減少數量
                let remaining = pos.qty - close_qty;
                if remaining > 1e-12 {
                    let mut updated = pos.clone();
                    updated.qty = remaining;
                    self.positions.insert(symbol.to_string(), updated);
                } else {
                    self.positions.remove(symbol);
                }
                self.peak_balance = self.peak_balance.max(self.balance);
                return pnl;
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
                return 0.0;
            }
        }

        // Opening new position (no existing position for this symbol)
        // 開新倉（此交易對無現有持倉）
        self.positions.insert(
            symbol.to_string(),
            PaperPosition {
                symbol: symbol.to_string(),
                is_long,
                qty,
                entry_price: fill_price,
                best_price: fill_price,
                entry_fee: fee,
                entry_ts_ms: ts_ms,
                unrealized_pnl: 0.0,
            },
        );
        0.0 // Opening position — no realized PnL / 開倉無已實現損益
    }

    /// Close a position at market price. Returns realized PnL on close,
    /// None if no position existed for the symbol. (DB-RUN-3: caller should
    /// emit a TradingMsg::Fill with the returned PnL so trading.fills records
    /// non-zero realized_pnl for risk/stop-driven closes.)
    /// 以市場價平倉，返回已實現損益（None=無持倉）。DB-RUN-3：呼叫端應依此 PnL
    /// 發送 TradingMsg::Fill，避免風控/止損平倉的 realized_pnl 落為 0。
    pub fn close_position(&mut self, symbol: &str, price: f64, _ts_ms: u64) -> Option<f64> {
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
            Some(pnl)
        } else {
            None
        }
    }

    /// Close a single position at current market price (falls back to entry price if no live
    /// price available). Returns realized PnL or None if no position exists for the symbol.
    /// 以當前市場價平掉單一持倉（無市場價時回退入場價），返回已實現損益或 None。
    pub fn close_position_at_market(&mut self, symbol: &str) -> Option<f64> {
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        let price = self.latest_prices.get(symbol).copied().unwrap_or_else(|| {
            // Fallback to entry price if no live market price / 無市場價時回退到入場價
            self.positions
                .get(symbol)
                .map(|p| p.entry_price)
                .unwrap_or(0.0)
        });
        self.close_position(symbol, price, now)
    }

    /// Close all open positions at their latest market price.
    /// Returns the number of positions closed.
    /// 以最新市場價平掉所有持倉，返回已平倉數量。
    pub fn close_all_positions(&mut self) -> usize {
        let symbols: Vec<String> = self.positions.keys().cloned().collect();
        let mut closed = 0;
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        for symbol in &symbols {
            let price = self.latest_prices.get(symbol).copied().unwrap_or_else(|| {
                // Fallback to entry price if no market price available
                // 無市場價時回退到入場價
                self.positions
                    .get(symbol)
                    .map(|p| p.entry_price)
                    .unwrap_or(0.0)
            });
            self.close_position(symbol, price, now);
            closed += 1;
        }
        closed
    }

    /// Check stops on all positions using per-symbol latest prices.
    /// 使用每個交易對的最新價格檢查所有持倉的止損。
    /// RRC-1-C1: Update best_price for all positions (trailing stop tracking).
    /// RRC-1-C1：更新所有持倉的最佳價格（跟蹤止損追蹤）。
    pub fn update_best_prices(&mut self) {
        let latest = self.latest_prices.clone();
        for (symbol, pos) in &mut self.positions {
            if let Some(&sym_price) = latest.get(symbol.as_str()) {
                let mut ps = PositionState {
                    entry_price: pos.entry_price,
                    best_price: pos.best_price,
                    is_long: pos.is_long,
                    entry_ts_ms: pos.entry_ts_ms,
                };
                stop_manager::update_best_price(&mut ps, sym_price);
                pos.best_price = ps.best_price;
            }
        }
    }

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

            if let Some(trigger) =
                stop_manager::check_stops(&self.stop_config, &ps, sym_price, now_ms)
            {
                triggers.push((symbol.clone(), trigger));
            }
        }
        triggers
    }

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
            trade_count: self.trade_count,
            positions,
            bybit_sync_balance: self.bybit_sync_balance,
        }
    }
}

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
    pub trade_count: u32,
    pub positions: Vec<PositionSnapshot>,
    /// Bybit Demo sync balance for comparison (None = custom mode).
    /// Bybit Demo 同步餘額用於對比（None = 自設金額模式）。
    #[serde(skip_serializing_if = "Option::is_none")]
    pub bybit_sync_balance: Option<f64>,
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
        s.apply_fill("BTC", true, 0.1, 50000.0, 1.0, 0); // buy 0.1 @ 50000
        s.apply_fill("BTC", true, 0.1, 52000.0, 1.0, 1000); // buy 0.1 @ 52000
        assert_eq!(s.position_count(), 1);
        let pos = s.get_position("BTC").unwrap();
        assert!((pos.qty - 0.2).abs() < 1e-10); // 0.1 + 0.1
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
    fn test_close_all_positions() {
        // close_all_positions should close every open position at latest price.
        // close_all_positions 應以最新價格平掉所有持倉。
        let mut s = PaperState::new(10000.0);
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0);
        s.apply_fill("ETH", false, 1.0, 3000.0, 0.0, 0);
        s.set_latest_price("BTC", 51000.0);
        s.set_latest_price("ETH", 2900.0);
        assert_eq!(s.position_count(), 2);

        let closed = s.close_all_positions();
        assert_eq!(closed, 2);
        assert_eq!(s.position_count(), 0);
        // BTC PnL: (51000-50000)*0.1 = 100, ETH PnL: (3000-2900)*1.0 = 100
        assert!((s.balance() - 10200.0).abs() < 0.01);
    }

    #[test]
    fn test_get_position() {
        let mut s = PaperState::new(10000.0);
        assert!(s.get_position("BTC").is_none());
        s.apply_fill("BTC", true, 0.1, 50000.0, 0.0, 0);
        assert!(s.get_position("BTC").is_some());
        assert!(s.get_position("ETH").is_none());
    }

    #[test]
    fn test_import_positions_seeds_state() {
        // B-1 Phase 2: import_positions replaces the map and seeds latest_prices.
        // B-1 Phase 2：import_positions 覆蓋持倉並種入 latest_prices。
        let mut s = PaperState::new(10000.0);
        // Pre-existing position should be wiped by import_positions.
        // 既有持倉應被 import_positions 清掉。
        s.apply_fill("STALE", true, 1.0, 10.0, 0.0, 0);
        let inserted = s.import_positions(vec![
            ("BTCUSDT".to_string(), true, 0.5, 50_000.0, 1_000),
            ("ETHUSDT".to_string(), false, 2.0, 3_000.0, 1_001),
            ("ZERO".to_string(), true, 0.0, 1.0, 0),       // skipped (qty=0)
            ("BAD".to_string(), true, 1.0, -5.0, 0),       // skipped (price<=0)
        ]);
        assert_eq!(inserted, 2);
        assert_eq!(s.position_count(), 2);
        assert!(s.get_position("STALE").is_none());

        let btc = s.get_position("BTCUSDT").unwrap();
        assert!(btc.is_long);
        assert!((btc.qty - 0.5).abs() < 1e-12);
        assert!((btc.entry_price - 50_000.0).abs() < 1e-9);
        assert_eq!(s.latest_price("BTCUSDT"), Some(50_000.0));

        let eth = s.get_position("ETHUSDT").unwrap();
        assert!(!eth.is_long);
        assert!((eth.qty - 2.0).abs() < 1e-12);
    }

    #[test]
    fn test_upsert_position_from_exchange_handles_size_zero() {
        // size==0 → remove (Bybit just reported a flat position).
        // size > 0 → upsert (preserve best_price if direction unchanged).
        // size==0 → 移除（交易所剛回報該倉已平）。
        // size > 0 → upsert（同向時保留 best_price）。
        let mut s = PaperState::new(10000.0);

        // 1. Insert via upsert (no prior position).
        assert!(s.upsert_position_from_exchange("BTCUSDT", true, 0.5, 50_000.0, 100));
        assert_eq!(s.position_count(), 1);

        // 2. Mutate best_price via market move + update_best_prices.
        s.set_latest_price("BTCUSDT", 51_000.0);
        s.update_best_prices();
        let best_after_move = s.get_position("BTCUSDT").unwrap().best_price;
        assert!((best_after_move - 51_000.0).abs() < 1e-9);

        // 3. Same-direction upsert with new avg_price → best_price preserved.
        assert!(s.upsert_position_from_exchange("BTCUSDT", true, 1.0, 50_500.0, 200));
        let pos = s.get_position("BTCUSDT").unwrap();
        assert!((pos.qty - 1.0).abs() < 1e-12);
        assert!((pos.entry_price - 50_500.0).abs() < 1e-9);
        assert!((pos.best_price - 51_000.0).abs() < 1e-9); // preserved

        // 4. Size==0 removes the entry.
        assert!(s.upsert_position_from_exchange("BTCUSDT", true, 0.0, 50_000.0, 300));
        assert_eq!(s.position_count(), 0);

        // 5. Size==0 on non-existent symbol → no-op false.
        assert!(!s.upsert_position_from_exchange("NOPE", true, 0.0, 0.0, 0));

        // 6. Direction flip resets best_price.
        s.upsert_position_from_exchange("ETHUSDT", true, 1.0, 3_000.0, 100);
        s.set_latest_price("ETHUSDT", 3_100.0);
        s.update_best_prices();
        s.upsert_position_from_exchange("ETHUSDT", false, 1.0, 3_050.0, 200);
        let eth = s.get_position("ETHUSDT").unwrap();
        assert!(!eth.is_long);
        assert!((eth.best_price - 3_050.0).abs() < 1e-9); // reset on flip
    }
}
