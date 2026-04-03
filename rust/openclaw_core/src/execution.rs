//! Execution calculations — slippage, fill price, fees.
//! 執行計算 — 滑點、成交價、手續費。
//!
//! Deterministic: given inputs, outputs are fixed (no RNG for market orders).
//! 確定性：給定輸入，輸出固定。

use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Fee Model / 手續費模型
// ═══════════════════════════════════════════════════════════════════════════════

/// Fee rates for Bybit perpetual/spot.
/// Bybit 永續/現貨手續費率。
pub const TAKER_FEE_RATE: f64 = 0.000_55; // 0.055%
pub const MAKER_FEE_RATE: f64 = 0.000_2;  // 0.02%

/// Compute trading fee.
/// 計算交易手續費。
pub fn compute_fee(qty: f64, price: f64, is_taker: bool) -> f64 {
    let rate = if is_taker { TAKER_FEE_RATE } else { MAKER_FEE_RATE };
    qty * price * rate
}

/// Compute round-trip fee (open + close, both taker worst case).
/// 計算往返手續費（開倉+平倉，均為 taker 最差情況）。
pub fn compute_round_trip_fee(qty: f64, price: f64) -> f64 {
    2.0 * compute_fee(qty, price, true)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Slippage Model / 滑點模型
// ═══════════════════════════════════════════════════════════════════════════════

/// Slippage tiers by 24h turnover (USD).
/// 按 24h 成交額的滑點分層。
const SLIPPAGE_TIERS: &[(f64, f64)] = &[
    (1_000_000_000.0, 0.0001), // >$1B → 1 bps
    (100_000_000.0, 0.0002),   // >$100M → 2 bps
    (10_000_000.0, 0.0005),    // >$10M → 5 bps (default)
    (1_000_000.0, 0.0015),     // >$1M → 15 bps
    (0.0, 0.0030),             // <$1M → 30 bps
];

/// Get slippage rate based on 24h turnover.
/// 根據 24h 成交額獲取滑點率。
pub fn slippage_rate(turnover_24h: f64) -> f64 {
    for &(threshold, rate) in SLIPPAGE_TIERS {
        if turnover_24h >= threshold {
            return rate;
        }
    }
    0.0005 // default fallback
}

// ═══════════════════════════════════════════════════════════════════════════════
// Fill Price / 成交價
// ═══════════════════════════════════════════════════════════════════════════════

/// Compute fill price for a market order with slippage.
/// 計算市價單含滑點的成交價。
pub fn compute_market_fill_price(market_price: f64, is_buy: bool, turnover_24h: f64) -> f64 {
    let slip = slippage_rate(turnover_24h);
    if is_buy {
        market_price * (1.0 + slip)
    } else {
        market_price * (1.0 - slip)
    }
}

/// Compute fill price for a limit order (no slippage).
/// 計算限價單成交價（無滑點）。
pub fn compute_limit_fill_price(limit_price: f64) -> f64 {
    limit_price
}

/// Compute weighted average fill price for partial fills.
/// 計算部分成交的加權平均成交價。
pub fn compute_avg_fill_price(
    prev_filled_qty: f64,
    prev_avg_price: f64,
    new_qty: f64,
    new_price: f64,
) -> f64 {
    let total = prev_filled_qty + new_qty;
    if total <= 0.0 {
        return 0.0;
    }
    (prev_filled_qty * prev_avg_price + new_qty * new_price) / total
}

// ═══════════════════════════════════════════════════════════════════════════════
// PnL Computation / 損益計算
// ═══════════════════════════════════════════════════════════════════════════════

/// Compute unrealized PnL for a position.
/// 計算持倉未實現損益。
pub fn compute_unrealized_pnl(
    entry_price: f64,
    current_price: f64,
    qty: f64,
    is_long: bool,
) -> f64 {
    if is_long {
        (current_price - entry_price) * qty
    } else {
        (entry_price - current_price) * qty
    }
}

/// Compute realized PnL including fees.
/// 計算已實現損益（含手續費）。
pub fn compute_realized_pnl(
    entry_price: f64,
    exit_price: f64,
    qty: f64,
    is_long: bool,
    entry_fee: f64,
    exit_fee: f64,
) -> f64 {
    let gross = if is_long {
        (exit_price - entry_price) * qty
    } else {
        (entry_price - exit_price) * qty
    };
    gross - entry_fee - exit_fee
}

// ═══════════════════════════════════════════════════════════════════════════════
// Fill Result / 成交結果
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct FillResult {
    pub fill_price: f64,
    pub fill_qty: f64,
    pub fee: f64,
    pub slippage_bps: f64,
    pub is_taker: bool,
}

/// Execute a fill computation for a market order.
/// 執行市價單的成交計算。
pub fn execute_market_fill(
    market_price: f64,
    qty: f64,
    is_buy: bool,
    turnover_24h: f64,
) -> FillResult {
    let fill_price = compute_market_fill_price(market_price, is_buy, turnover_24h);
    let fee = compute_fee(qty, fill_price, true);
    let slip_bps = ((fill_price - market_price).abs() / market_price) * 10_000.0;
    FillResult { fill_price, fill_qty: qty, fee, slippage_bps: slip_bps, is_taker: true }
}

/// Execute a fill computation for a limit order.
/// 執行限價單的成交計算。
pub fn execute_limit_fill(limit_price: f64, qty: f64) -> FillResult {
    let fee = compute_fee(qty, limit_price, false); // maker
    FillResult { fill_price: limit_price, fill_qty: qty, fee, slippage_bps: 0.0, is_taker: false }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_fee_calculation() {
        let fee = compute_fee(1.0, 50000.0, true);
        assert!((fee - 27.5).abs() < 0.01); // 1.0 * 50000 * 0.00055 = 27.5
    }

    #[test]
    fn test_maker_fee() {
        let fee = compute_fee(1.0, 50000.0, false);
        assert!((fee - 10.0).abs() < 0.01); // 1.0 * 50000 * 0.0002 = 10.0
    }

    #[test]
    fn test_round_trip_fee() {
        let fee = compute_round_trip_fee(1.0, 50000.0);
        assert!((fee - 55.0).abs() < 0.01);
    }

    #[test]
    fn test_slippage_rate_high_volume() {
        assert!((slippage_rate(2_000_000_000.0) - 0.0001).abs() < 1e-6);
    }

    #[test]
    fn test_slippage_rate_default() {
        assert!((slippage_rate(50_000_000.0) - 0.0005).abs() < 1e-6);
    }

    #[test]
    fn test_slippage_rate_low_volume() {
        assert!((slippage_rate(500_000.0) - 0.0030).abs() < 1e-6);
    }

    #[test]
    fn test_market_fill_buy() {
        let price = compute_market_fill_price(50000.0, true, 500_000_000.0);
        // turnover 500M → 2 bps → 50000 * 1.0002 = 50010
        assert!((price - 50010.0).abs() < 0.01);
    }

    #[test]
    fn test_market_fill_sell() {
        let price = compute_market_fill_price(50000.0, false, 500_000_000.0);
        assert!((price - 49990.0).abs() < 0.01);
    }

    #[test]
    fn test_avg_fill_price() {
        let avg = compute_avg_fill_price(0.5, 50000.0, 0.5, 51000.0);
        assert!((avg - 50500.0).abs() < 0.01);
    }

    #[test]
    fn test_avg_fill_price_zero() {
        assert_eq!(compute_avg_fill_price(0.0, 0.0, 0.0, 0.0), 0.0);
    }

    #[test]
    fn test_unrealized_pnl_long() {
        let pnl = compute_unrealized_pnl(50000.0, 51000.0, 1.0, true);
        assert!((pnl - 1000.0).abs() < 0.01);
    }

    #[test]
    fn test_unrealized_pnl_short() {
        let pnl = compute_unrealized_pnl(50000.0, 49000.0, 1.0, false);
        assert!((pnl - 1000.0).abs() < 0.01);
    }

    #[test]
    fn test_realized_pnl_with_fees() {
        let pnl = compute_realized_pnl(50000.0, 51000.0, 1.0, true, 27.5, 28.05);
        // gross = 1000, net = 1000 - 27.5 - 28.05 = 944.45
        assert!((pnl - 944.45).abs() < 0.01);
    }

    #[test]
    fn test_execute_market_fill() {
        let r = execute_market_fill(50000.0, 1.0, true, 2_000_000_000.0);
        assert!((r.fill_price - 50005.0).abs() < 0.01); // 1 bps
        assert!(r.is_taker);
        assert!(r.slippage_bps > 0.0);
    }

    #[test]
    fn test_execute_limit_fill() {
        let r = execute_limit_fill(50000.0, 1.0);
        assert_eq!(r.fill_price, 50000.0);
        assert!(!r.is_taker);
        assert_eq!(r.slippage_bps, 0.0);
    }
}
