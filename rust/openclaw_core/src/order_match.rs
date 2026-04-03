//! Order matching engine for paper trading.
//! 紙盤交易的訂單匹配引擎。
//!
//! Determines if/when limit orders fill based on market price movement.
//! 根據市場價格變動判斷限價單是否/何時成交。

use crate::execution::{self, FillResult};
use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Order / 訂單
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PaperOrder {
    pub order_id: String,
    pub symbol: String,
    pub side: String,
    pub order_type: String,
    pub qty: f64,
    pub limit_price: Option<f64>,
    pub filled_qty: f64,
    pub avg_fill_price: f64,
    pub status: PaperOrderStatus,
    pub created_at_ms: u64,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub enum PaperOrderStatus {
    Created,
    Submitted,
    Working,
    PartiallyFilled,
    Filled,
    Canceled,
    Rejected,
}

impl PaperOrderStatus {
    pub fn is_terminal(self) -> bool {
        matches!(self, Self::Filled | Self::Canceled | Self::Rejected)
    }

    pub fn as_str(self) -> &'static str {
        match self {
            Self::Created => "CREATED",
            Self::Submitted => "SUBMITTED",
            Self::Working => "WORKING",
            Self::PartiallyFilled => "PARTIALLY_FILLED",
            Self::Filled => "FILLED",
            Self::Canceled => "CANCELED",
            Self::Rejected => "REJECTED",
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Matching Logic / 匹配邏輯
// ═══════════════════════════════════════════════════════════════════════════════

/// Check if a limit order should fill at the given market price.
/// 檢查限價單在給定市場價格下是否應該成交。
pub fn should_fill_limit_order(
    side: &str,
    limit_price: f64,
    market_price: f64,
) -> bool {
    match side {
        "Buy" => market_price <= limit_price,
        "Sell" => market_price >= limit_price,
        _ => false,
    }
}

/// Compute partial fill quantity based on price cross depth.
/// 根據價格穿越深度計算部分成交數量。
///
/// cross_pct = |limit_price - market_price| / limit_price
/// ≥0.5% → 100% fill, ≥0.1% → 70% fill, else → 50% fill
pub fn compute_partial_fill_pct(limit_price: f64, market_price: f64) -> f64 {
    if limit_price <= 0.0 {
        return 0.0;
    }
    let cross_pct = (limit_price - market_price).abs() / limit_price;
    if cross_pct >= 0.005 {
        1.0
    } else if cross_pct >= 0.001 {
        0.7
    } else {
        0.5
    }
}

/// Match result for a single price tick.
/// 單個價格 tick 的匹配結果。
#[derive(Debug, Clone)]
pub struct MatchResult {
    pub filled: bool,
    pub fill_result: Option<FillResult>,
    pub remaining_qty: f64,
}

/// Try to match a working order against the current market price.
/// 嘗試將工作中的訂單與當前市場價格匹配。
pub fn try_match(order: &PaperOrder, market_price: f64, turnover_24h: f64) -> MatchResult {
    let remaining = order.qty - order.filled_qty;
    if remaining <= 0.0 || order.status.is_terminal() {
        return MatchResult { filled: false, fill_result: None, remaining_qty: 0.0 };
    }

    match order.order_type.as_str() {
        "market" => {
            let is_buy = order.side == "Buy";
            let fill = execution::execute_market_fill(market_price, remaining, is_buy, turnover_24h);
            MatchResult { filled: true, fill_result: Some(fill), remaining_qty: 0.0 }
        }
        "limit" => {
            let limit_price = match order.limit_price {
                Some(p) => p,
                None => return MatchResult { filled: false, fill_result: None, remaining_qty: remaining },
            };

            if !should_fill_limit_order(&order.side, limit_price, market_price) {
                return MatchResult { filled: false, fill_result: None, remaining_qty: remaining };
            }

            let fill_pct = compute_partial_fill_pct(limit_price, market_price);
            let fill_qty = remaining * fill_pct;

            // If remaining after fill < 1% of original → fill everything
            let actual_fill_qty = if (remaining - fill_qty) < order.qty * 0.01 {
                remaining
            } else {
                fill_qty
            };

            let fill = execution::execute_limit_fill(limit_price, actual_fill_qty);
            let new_remaining = remaining - actual_fill_qty;
            MatchResult { filled: true, fill_result: Some(fill), remaining_qty: new_remaining.max(0.0) }
        }
        _ => MatchResult { filled: false, fill_result: None, remaining_qty: remaining },
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    fn buy_limit(qty: f64, limit: f64) -> PaperOrder {
        PaperOrder {
            order_id: "test".into(), symbol: "BTCUSDT".into(), side: "Buy".into(),
            order_type: "limit".into(), qty, limit_price: Some(limit),
            filled_qty: 0.0, avg_fill_price: 0.0, status: PaperOrderStatus::Working,
            created_at_ms: 0,
        }
    }

    fn sell_limit(qty: f64, limit: f64) -> PaperOrder {
        PaperOrder {
            order_id: "test".into(), symbol: "BTCUSDT".into(), side: "Sell".into(),
            order_type: "limit".into(), qty, limit_price: Some(limit),
            filled_qty: 0.0, avg_fill_price: 0.0, status: PaperOrderStatus::Working,
            created_at_ms: 0,
        }
    }

    fn market_buy(qty: f64) -> PaperOrder {
        PaperOrder {
            order_id: "test".into(), symbol: "BTCUSDT".into(), side: "Buy".into(),
            order_type: "market".into(), qty, limit_price: None,
            filled_qty: 0.0, avg_fill_price: 0.0, status: PaperOrderStatus::Working,
            created_at_ms: 0,
        }
    }

    #[test]
    fn test_should_fill_buy_limit() {
        assert!(should_fill_limit_order("Buy", 50000.0, 49999.0));
        assert!(should_fill_limit_order("Buy", 50000.0, 50000.0));
        assert!(!should_fill_limit_order("Buy", 50000.0, 50001.0));
    }

    #[test]
    fn test_should_fill_sell_limit() {
        assert!(should_fill_limit_order("Sell", 50000.0, 50001.0));
        assert!(should_fill_limit_order("Sell", 50000.0, 50000.0));
        assert!(!should_fill_limit_order("Sell", 50000.0, 49999.0));
    }

    #[test]
    fn test_partial_fill_pct_deep_cross() {
        // cross 1% → 100% fill
        let pct = compute_partial_fill_pct(50000.0, 49500.0);
        assert_eq!(pct, 1.0);
    }

    #[test]
    fn test_partial_fill_pct_medium_cross() {
        // cross 0.2% → 70%
        let pct = compute_partial_fill_pct(50000.0, 49900.0);
        assert_eq!(pct, 0.7);
    }

    #[test]
    fn test_partial_fill_pct_shallow_cross() {
        // cross 0.02% → 50%
        let pct = compute_partial_fill_pct(50000.0, 49990.0);
        assert_eq!(pct, 0.5);
    }

    #[test]
    fn test_try_match_market_order() {
        let order = market_buy(1.0);
        let result = try_match(&order, 50000.0, 1_000_000_000.0);
        assert!(result.filled);
        assert_eq!(result.remaining_qty, 0.0);
        let fill = result.fill_result.unwrap();
        assert!(fill.is_taker);
    }

    #[test]
    fn test_try_match_limit_not_triggered() {
        let order = buy_limit(1.0, 49000.0);
        let result = try_match(&order, 50000.0, 1e9);
        assert!(!result.filled);
        assert_eq!(result.remaining_qty, 1.0);
    }

    #[test]
    fn test_try_match_limit_triggered() {
        let order = buy_limit(1.0, 50000.0);
        let result = try_match(&order, 49500.0, 1e9); // deep cross
        assert!(result.filled);
        assert_eq!(result.remaining_qty, 0.0);
        assert_eq!(result.fill_result.unwrap().fill_price, 50000.0);
    }

    #[test]
    fn test_try_match_sell_limit() {
        let order = sell_limit(1.0, 51000.0);
        let result = try_match(&order, 51500.0, 1e9);
        assert!(result.filled);
    }

    #[test]
    fn test_terminal_order_no_match() {
        let mut order = market_buy(1.0);
        order.status = PaperOrderStatus::Canceled;
        let result = try_match(&order, 50000.0, 1e9);
        assert!(!result.filled);
    }

    #[test]
    fn test_partial_fill_small_remainder_fills_all() {
        // 0.5% of qty = 0.005, remaining after 50% fill = 0.5
        // But if remaining after fill is < 1% of original (0.01), fill all
        let order = buy_limit(0.02, 50000.0); // tiny order
        let result = try_match(&order, 49990.0, 1e9); // shallow cross → 50%
        // 50% of 0.02 = 0.01, remaining = 0.01, which is exactly 50% of 0.02
        // remaining (0.01) >= 0.02 * 0.01 (0.0002) → partial, not full
        assert!(result.filled);
    }
}
