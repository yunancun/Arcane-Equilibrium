//! PnL Attribution — 6-factor trade decomposition.
//! 損益歸因 — 6 因子交易分解。
//!
//! Factors: alpha, timing, sizing, execution, cost, luck.
//! 因子：alpha、時機、倉位、執行、成本、運氣。

use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Trade Record / 交易記錄
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct TradeRecord {
    pub symbol: String,
    pub side: String,
    pub entry_price: f64,
    pub exit_price: f64,
    pub qty: f64,
    pub entry_fee: f64,
    pub exit_fee: f64,
    pub slippage_bps: f64,
    pub hold_duration_ms: u64,
    pub strategy: String,
    /// Best price seen during the trade.
    /// 交易期間見到的最佳價格。
    pub best_price: f64,
    /// Worst price seen during the trade.
    /// 交易期間見到的最差價格。
    pub worst_price: f64,
    /// Market benchmark return over the same period.
    /// 同期市場基準收益率。
    pub benchmark_return: f64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Attribution Result / 歸因結果
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct AttributionResult {
    pub gross_pnl: f64,
    pub net_pnl: f64,
    pub total_fees: f64,
    pub alpha: f64,
    pub timing: f64,
    pub sizing: f64,
    pub execution: f64,
    pub cost: f64,
    pub luck: f64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Attribution Engine / 歸因引擎
// ═══════════════════════════════════════════════════════════════════════════════

/// Compute 6-factor PnL attribution for a single trade.
/// 計算單筆交易的 6 因子損益歸因。
pub fn attribute_trade(trade: &TradeRecord) -> AttributionResult {
    let is_long = trade.side == "Buy";
    let notional = trade.qty * trade.entry_price;

    // Gross and net PnL
    let gross_pnl = if is_long {
        (trade.exit_price - trade.entry_price) * trade.qty
    } else {
        (trade.entry_price - trade.exit_price) * trade.qty
    };
    let total_fees = trade.entry_fee + trade.exit_fee;
    let net_pnl = gross_pnl - total_fees;

    // 1. Alpha: excess return vs benchmark
    let trade_return = if trade.entry_price > 0.0 {
        gross_pnl / notional
    } else {
        0.0
    };
    let alpha = (trade_return - trade.benchmark_return) * notional;

    // 2. Timing: how much was captured of the max opportunity
    let max_favorable = if is_long {
        (trade.best_price - trade.entry_price).max(0.0) * trade.qty
    } else {
        (trade.entry_price - trade.worst_price).max(0.0) * trade.qty
    };
    let timing = if max_favorable > 0.0 {
        // timing_efficiency = gross_pnl / max_favorable
        // timing_value = what was left on the table
        gross_pnl - max_favorable
    } else {
        0.0
    };

    // 3. Sizing: deviation from ideal position size (simplified)
    // In a full implementation, compare to Kelly-optimal qty
    let sizing = 0.0; // placeholder — requires external Kelly reference

    // 4. Execution: slippage impact
    let execution = -(trade.slippage_bps / 10_000.0) * notional;

    // 5. Cost: fee impact
    let cost = -total_fees;

    // 6. Luck: residual (what can't be explained by other factors)
    let explained = alpha + timing + sizing + execution + cost;
    let luck = net_pnl - explained;

    AttributionResult {
        gross_pnl,
        net_pnl,
        total_fees,
        alpha,
        timing,
        sizing,
        execution,
        cost,
        luck,
    }
}

/// Aggregate attribution across multiple trades.
/// 聚合多筆交易的歸因。
pub fn aggregate_attributions(results: &[AttributionResult]) -> AttributionResult {
    let mut agg = AttributionResult {
        gross_pnl: 0.0,
        net_pnl: 0.0,
        total_fees: 0.0,
        alpha: 0.0,
        timing: 0.0,
        sizing: 0.0,
        execution: 0.0,
        cost: 0.0,
        luck: 0.0,
    };
    for r in results {
        agg.gross_pnl += r.gross_pnl;
        agg.net_pnl += r.net_pnl;
        agg.total_fees += r.total_fees;
        agg.alpha += r.alpha;
        agg.timing += r.timing;
        agg.sizing += r.sizing;
        agg.execution += r.execution;
        agg.cost += r.cost;
        agg.luck += r.luck;
    }
    agg
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_long_trade() -> TradeRecord {
        TradeRecord {
            symbol: "BTCUSDT".into(),
            side: "Buy".into(),
            entry_price: 50000.0,
            exit_price: 51000.0,
            qty: 1.0,
            entry_fee: 27.5,
            exit_fee: 28.05,
            slippage_bps: 1.0,
            hold_duration_ms: 3_600_000,
            strategy: "momentum".into(),
            best_price: 51500.0,
            worst_price: 49500.0,
            benchmark_return: 0.005,
        }
    }

    fn sample_short_trade() -> TradeRecord {
        TradeRecord {
            symbol: "ETHUSDT".into(),
            side: "Sell".into(),
            entry_price: 3000.0,
            exit_price: 2900.0,
            qty: 10.0,
            entry_fee: 1.65,
            exit_fee: 1.595,
            slippage_bps: 2.0,
            hold_duration_ms: 7_200_000,
            strategy: "reversion".into(),
            best_price: 3050.0,
            worst_price: 2850.0,
            benchmark_return: -0.02,
        }
    }

    #[test]
    fn test_long_gross_pnl() {
        let r = attribute_trade(&sample_long_trade());
        assert!((r.gross_pnl - 1000.0).abs() < 0.01);
    }

    #[test]
    fn test_long_net_pnl() {
        let r = attribute_trade(&sample_long_trade());
        assert!((r.net_pnl - (1000.0 - 27.5 - 28.05)).abs() < 0.01);
    }

    #[test]
    fn test_short_gross_pnl() {
        let r = attribute_trade(&sample_short_trade());
        // (3000 - 2900) * 10 = 1000
        assert!((r.gross_pnl - 1000.0).abs() < 0.01);
    }

    #[test]
    fn test_alpha_factor() {
        let r = attribute_trade(&sample_long_trade());
        // trade_return = 1000 / 50000 = 0.02, benchmark = 0.005
        // alpha = (0.02 - 0.005) * 50000 = 750
        assert!((r.alpha - 750.0).abs() < 0.1);
    }

    #[test]
    fn test_timing_factor() {
        let r = attribute_trade(&sample_long_trade());
        // max_favorable = (51500 - 50000) * 1 = 1500
        // timing = gross - max = 1000 - 1500 = -500
        assert!((r.timing - (-500.0)).abs() < 0.1);
    }

    #[test]
    fn test_execution_factor() {
        let r = attribute_trade(&sample_long_trade());
        // execution = -(1.0/10000) * 50000 = -5.0
        assert!((r.execution - (-5.0)).abs() < 0.1);
    }

    #[test]
    fn test_cost_factor() {
        let r = attribute_trade(&sample_long_trade());
        assert!((r.cost - (-55.55)).abs() < 0.01);
    }

    #[test]
    fn test_factors_sum_to_net_pnl() {
        let r = attribute_trade(&sample_long_trade());
        let sum = r.alpha + r.timing + r.sizing + r.execution + r.cost + r.luck;
        assert!((sum - r.net_pnl).abs() < 0.01);
    }

    #[test]
    fn test_aggregate() {
        let trades = vec![sample_long_trade(), sample_short_trade()];
        let results: Vec<_> = trades.iter().map(|t| attribute_trade(t)).collect();
        let agg = aggregate_attributions(&results);
        assert!((agg.gross_pnl - 2000.0).abs() < 0.01);
    }

    #[test]
    fn test_zero_entry_price() {
        let trade = TradeRecord {
            entry_price: 0.0,
            exit_price: 100.0,
            qty: 1.0,
            ..sample_long_trade()
        };
        let r = attribute_trade(&trade);
        assert_eq!(r.alpha, 0.0); // division by zero protected
    }
}
