//! Backtest Engine — bar-by-bar replay with Sharpe/drawdown.
//! 回測引擎 — 逐 K 線回放 + Sharpe/回撤計算。
//!
//! Processes OHLCV bars, evaluates signals, simulates fills, tracks equity.
//! 處理 OHLCV K 線，評估信號，模擬成交，追蹤權益。

use crate::execution;
use crate::stop_manager::{self, PositionState, StopConfig};
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Config / 配置
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BacktestConfig {
    pub initial_balance: f64,
    pub risk_per_trade_pct: f64,
    pub max_positions: usize,
    pub stop_config: StopConfig,
    pub turnover_24h: f64, // for slippage model
}

impl Default for BacktestConfig {
    fn default() -> Self {
        Self {
            initial_balance: 10_000.0,
            risk_per_trade_pct: 3.0,
            max_positions: 5,
            stop_config: StopConfig::default(),
            turnover_24h: 100_000_000.0,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Bar / K 線
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Bar {
    pub timestamp_ms: u64,
    pub open: f64,
    pub high: f64,
    pub low: f64,
    pub close: f64,
    pub volume: f64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Signal / 信號
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum Signal {
    Long,
    Short,
    Close,
    None,
}

/// Signal generator trait — implement for each strategy.
/// 信號產生器 trait — 為每個策略實現。
pub trait SignalGenerator {
    fn on_bar(&mut self, bar: &Bar) -> Signal;
}

// ═══════════════════════════════════════════════════════════════════════════════
// Position / 持倉
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone)]
struct Position {
    is_long: bool,
    entry_price: f64,
    qty: f64,
    entry_fee: f64,
    entry_ts_ms: u64,
    best_price: f64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Results / 結果
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BacktestResult {
    pub total_return_pct: f64,
    pub sharpe_ratio: f64,
    pub max_drawdown_pct: f64,
    pub win_rate: f64,
    pub trade_count: usize,
    pub total_pnl: f64,
    pub total_fees: f64,
    pub equity_curve: Vec<f64>,
    pub final_balance: f64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Engine / 引擎
// ═══════════════════════════════════════════════════════════════════════════════

pub struct BacktestEngine {
    config: BacktestConfig,
    balance: f64,
    peak_balance: f64,
    positions: Vec<Position>,
    equity_curve: Vec<f64>,
    trade_pnls: Vec<f64>,
    total_fees: f64,
}

impl BacktestEngine {
    pub fn new(config: BacktestConfig) -> Self {
        let balance = config.initial_balance;
        Self {
            config,
            balance,
            peak_balance: balance,
            positions: Vec::new(),
            equity_curve: vec![balance],
            trade_pnls: Vec::new(),
            total_fees: 0.0,
        }
    }

    /// Run backtest on a bar series with a signal generator.
    /// 在 K 線序列上用信號產生器運行回測。
    pub fn run(&mut self, bars: &[Bar], generator: &mut dyn SignalGenerator) -> BacktestResult {
        for bar in bars {
            // 1. Check stops on existing positions
            self.check_stops_on_bar(bar);

            // 2. Get signal
            let signal = generator.on_bar(bar);

            // 3. Process signal
            match signal {
                Signal::Long if self.positions.len() < self.config.max_positions => {
                    self.open_position(bar, true);
                }
                Signal::Short if self.positions.len() < self.config.max_positions => {
                    self.open_position(bar, false);
                }
                Signal::Close => {
                    self.close_all_positions(bar);
                }
                _ => {}
            }

            // 4. Update best prices
            for pos in &mut self.positions {
                let ps = PositionState {
                    entry_price: pos.entry_price,
                    best_price: pos.best_price,
                    is_long: pos.is_long,
                    entry_ts_ms: pos.entry_ts_ms,
                };
                let mut ps = ps;
                stop_manager::update_best_price(
                    &mut ps,
                    if pos.is_long { bar.high } else { bar.low },
                );
                pos.best_price = ps.best_price;
            }

            // 5. Record equity
            let unrealized: f64 = self
                .positions
                .iter()
                .map(|p| {
                    execution::compute_unrealized_pnl(p.entry_price, bar.close, p.qty, p.is_long)
                })
                .sum();
            self.equity_curve.push(self.balance + unrealized);
        }

        self.compute_result()
    }

    fn open_position(&mut self, bar: &Bar, is_long: bool) {
        let atr_mult = self.config.stop_config.atr_multiplier.unwrap_or(2.0);
        // Simple ATR estimate from bar range
        let atr_est = bar.high - bar.low;
        let qty = stop_manager::compute_atr_position_size(
            self.balance,
            self.config.risk_per_trade_pct,
            atr_est,
            atr_mult,
            0.001,
            self.balance / bar.close,
        );

        let fill =
            execution::execute_market_fill(bar.close, qty, is_long, self.config.turnover_24h);
        self.balance -= fill.fee;
        self.total_fees += fill.fee;

        self.positions.push(Position {
            is_long,
            entry_price: fill.fill_price,
            qty: fill.fill_qty,
            entry_fee: fill.fee,
            entry_ts_ms: bar.timestamp_ms,
            best_price: fill.fill_price,
        });
    }

    fn close_position(&mut self, pos: &Position, exit_price: f64) {
        let fill = execution::execute_market_fill(
            exit_price,
            pos.qty,
            !pos.is_long,
            self.config.turnover_24h,
        );
        // Gross PnL (no fees) — entry fee already deducted when opening
        let gross = if pos.is_long {
            (fill.fill_price - pos.entry_price) * pos.qty
        } else {
            (pos.entry_price - fill.fill_price) * pos.qty
        };
        self.balance += gross - fill.fee;
        self.total_fees += fill.fee;
        // Net PnL for attribution (includes both fees)
        let net_pnl = gross - pos.entry_fee - fill.fee;
        self.trade_pnls.push(net_pnl);
        self.peak_balance = self.peak_balance.max(self.balance);
    }

    fn close_all_positions(&mut self, bar: &Bar) {
        let positions: Vec<Position> = self.positions.drain(..).collect();
        for pos in &positions {
            self.close_position(pos, bar.close);
        }
    }

    fn check_stops_on_bar(&mut self, bar: &Bar) {
        let mut to_close = Vec::new();
        for (i, pos) in self.positions.iter().enumerate() {
            let ps = PositionState {
                entry_price: pos.entry_price,
                best_price: pos.best_price,
                is_long: pos.is_long,
                entry_ts_ms: pos.entry_ts_ms,
            };
            let check_price = if pos.is_long { bar.low } else { bar.high };
            if stop_manager::check_stops(
                &self.config.stop_config,
                &ps,
                check_price,
                bar.timestamp_ms,
            )
            .is_some()
            {
                to_close.push(i);
            }
        }
        // Close in reverse to preserve indices
        for &i in to_close.iter().rev() {
            let pos = self.positions.remove(i);
            let exit_price = if pos.is_long { bar.low } else { bar.high };
            self.close_position(&pos, exit_price);
        }
    }

    fn compute_result(&self) -> BacktestResult {
        let initial = self.config.initial_balance;
        let total_return_pct = (self.balance - initial) / initial * 100.0;

        // Sharpe ratio (annualized, assuming daily bars)
        let returns: Vec<f64> = self
            .equity_curve
            .windows(2)
            .map(|w| {
                if w[0] > 0.0 {
                    (w[1] - w[0]) / w[0]
                } else {
                    0.0
                }
            })
            .collect();
        let sharpe = compute_sharpe(&returns);

        // Max drawdown
        let max_dd = compute_max_drawdown(&self.equity_curve);

        // Win rate
        let wins = self.trade_pnls.iter().filter(|&&p| p > 0.0).count();
        let win_rate = if self.trade_pnls.is_empty() {
            0.0
        } else {
            wins as f64 / self.trade_pnls.len() as f64
        };

        BacktestResult {
            total_return_pct,
            sharpe_ratio: sharpe,
            max_drawdown_pct: max_dd,
            win_rate,
            trade_count: self.trade_pnls.len(),
            total_pnl: self.balance - initial,
            total_fees: self.total_fees,
            equity_curve: self.equity_curve.clone(),
            final_balance: self.balance,
        }
    }
}

/// Compute annualized Sharpe ratio from daily returns.
/// 從日收益率計算年化 Sharpe 比率。
pub fn compute_sharpe(returns: &[f64]) -> f64 {
    if returns.len() < 2 {
        return 0.0;
    }
    let n = returns.len() as f64;
    let mean: f64 = returns.iter().sum::<f64>() / n;
    let var: f64 = returns.iter().map(|r| (r - mean).powi(2)).sum::<f64>() / (n - 1.0);
    let std = var.sqrt();
    if std < 1e-15 {
        return 0.0;
    }
    (mean / std) * (252.0_f64).sqrt()
}

/// Compute maximum drawdown percentage from equity curve.
/// 從權益曲線計算最大回撤百分比。
pub fn compute_max_drawdown(equity: &[f64]) -> f64 {
    let mut peak = f64::NEG_INFINITY;
    let mut max_dd = 0.0_f64;
    for &e in equity {
        peak = peak.max(e);
        if peak > 0.0 {
            let dd = (peak - e) / peak * 100.0;
            max_dd = max_dd.max(dd);
        }
    }
    max_dd
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    struct AlwaysLong;
    impl SignalGenerator for AlwaysLong {
        fn on_bar(&mut self, _bar: &Bar) -> Signal {
            Signal::Long
        }
    }

    struct AlternateSignal {
        count: usize,
    }
    impl SignalGenerator for AlternateSignal {
        fn on_bar(&mut self, _bar: &Bar) -> Signal {
            self.count += 1;
            if self.count % 5 == 1 {
                Signal::Long
            } else if self.count % 5 == 3 {
                Signal::Close
            } else {
                Signal::None
            }
        }
    }

    fn make_bars(prices: &[f64]) -> Vec<Bar> {
        prices
            .iter()
            .enumerate()
            .map(|(i, &p)| Bar {
                timestamp_ms: i as u64 * 60_000,
                open: p,
                high: p * 1.01,
                low: p * 0.99,
                close: p,
                volume: 1000.0,
            })
            .collect()
    }

    fn rising_bars() -> Vec<Bar> {
        make_bars(&[
            100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 106.0, 107.0, 108.0, 109.0,
        ])
    }

    fn falling_bars() -> Vec<Bar> {
        make_bars(&[100.0, 99.0, 98.0, 97.0, 96.0, 95.0, 94.0, 93.0, 92.0, 91.0])
    }

    #[test]
    fn test_sharpe_positive() {
        let returns = vec![0.01, 0.02, 0.01, 0.015, 0.005];
        let s = compute_sharpe(&returns);
        assert!(s > 0.0);
    }

    #[test]
    fn test_sharpe_zero_std() {
        let returns = vec![0.01, 0.01, 0.01];
        assert_eq!(compute_sharpe(&returns), 0.0);
    }

    #[test]
    fn test_sharpe_insufficient_data() {
        assert_eq!(compute_sharpe(&[0.01]), 0.0);
    }

    #[test]
    fn test_max_drawdown_no_drawdown() {
        let equity = vec![100.0, 101.0, 102.0, 103.0];
        assert_eq!(compute_max_drawdown(&equity), 0.0);
    }

    #[test]
    fn test_max_drawdown_with_drop() {
        let equity = vec![100.0, 110.0, 100.0, 90.0, 95.0];
        let dd = compute_max_drawdown(&equity);
        // Peak 110, trough 90 → dd = 18.18%
        assert!((dd - 18.18).abs() < 0.1);
    }

    #[test]
    fn test_backtest_rising_market() {
        let config = BacktestConfig {
            max_positions: 1,
            ..BacktestConfig::default()
        };
        let mut engine = BacktestEngine::new(config);
        let bars = rising_bars();
        let mut gen = AlternateSignal { count: 0 };
        let result = engine.run(&bars, &mut gen);
        assert!(result.trade_count > 0);
        assert!(result.equity_curve.len() > 1);
    }

    #[test]
    fn test_backtest_falling_market_stops() {
        let config = BacktestConfig {
            max_positions: 1,
            stop_config: StopConfig {
                hard_stop_pct: 3.0,
                ..StopConfig::default()
            },
            ..BacktestConfig::default()
        };
        let mut engine = BacktestEngine::new(config);
        let bars = falling_bars();
        let mut gen = AlwaysLong;
        let result = engine.run(&bars, &mut gen);
        // Longs in falling market should trigger hard stops
        assert!(result.max_drawdown_pct > 0.0);
    }

    #[test]
    fn test_backtest_no_trades() {
        struct NoSignal;
        impl SignalGenerator for NoSignal {
            fn on_bar(&mut self, _: &Bar) -> Signal {
                Signal::None
            }
        }
        let mut engine = BacktestEngine::new(BacktestConfig::default());
        let bars = rising_bars();
        let mut gen = NoSignal;
        let result = engine.run(&bars, &mut gen);
        assert_eq!(result.trade_count, 0);
        assert_eq!(result.total_pnl, 0.0);
    }

    #[test]
    fn test_equity_curve_length() {
        let mut engine = BacktestEngine::new(BacktestConfig::default());
        let bars = make_bars(&[100.0, 101.0, 102.0]);
        struct NoSig;
        impl SignalGenerator for NoSig {
            fn on_bar(&mut self, _: &Bar) -> Signal {
                Signal::None
            }
        }
        let result = engine.run(&bars, &mut NoSig);
        // initial + 3 bars = 4
        assert_eq!(result.equity_curve.len(), 4);
    }
}
