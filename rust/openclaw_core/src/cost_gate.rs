//! CostGate — Round-trip cost estimation and cost-based trade rejection
//! CostGate — 往返成本估算及基於成本的交易拒絕
//!
//! MODULE_NOTE (中文):
//!   CostGate 根據 24h 成交量分級估算往返交易成本（滑點 + 手續費），
//!   並判斷 ATR 是否足以覆蓋成本。若預期波動不足以覆蓋成本，則拒絕交易。
//!   安全閥：每日首筆交易且 ATR > 0.5×成本時放行（防止零交易日）。
//!   fail-open：ATR 為 None 時放行（資料不足時不阻塞）。
//!
//! MODULE_NOTE (English):
//!   CostGate estimates round-trip trading costs (slippage + fees) by 24h volume tier,
//!   then checks whether ATR is sufficient to cover costs. Rejects trades when expected
//!   volatility cannot overcome costs.
//!   Safety valve: first trade of day with ATR > 0.5× cost is allowed (prevent zero-trade days).
//!   Fail-open: ATR=None passes (don't block when data is unavailable).

// ---------------------------------------------------------------------------
// Cost tiers by 24h volume / 按 24h 成交量的成本分級
// ---------------------------------------------------------------------------

/// A single cost tier mapping volume threshold to slippage and fee estimates.
/// 單一成本分級：成交量門檻對應滑點和手續費估算。
struct CostTier {
    min_volume_usd: f64,
    slippage_pct: f64,
    taker_fee_pct: f64,
}

/// Volume-based cost tiers (sorted descending by volume).
/// 基於成交量的成本分級（按成交量降序排列）。
const COST_TIERS: &[CostTier] = &[
    CostTier {
        min_volume_usd: 1_000_000_000.0,
        slippage_pct: 0.01,
        taker_fee_pct: 0.055,
    },
    CostTier {
        min_volume_usd: 100_000_000.0,
        slippage_pct: 0.02,
        taker_fee_pct: 0.055,
    },
    CostTier {
        min_volume_usd: 10_000_000.0,
        slippage_pct: 0.05,
        taker_fee_pct: 0.055,
    },
    CostTier {
        min_volume_usd: 1_000_000.0,
        slippage_pct: 0.15,
        taker_fee_pct: 0.055,
    },
    CostTier {
        min_volume_usd: 0.0,
        slippage_pct: 0.30,
        taker_fee_pct: 0.055,
    },
];

/// Compute round-trip cost percentage for a given 24h volume.
/// 計算指定 24h 成交量的往返成本百分比。
///
/// Formula: (taker_fee + slippage) × 2 × 100 (entry + exit).
/// 公式：(taker_fee + slippage) × 2 × 100（入場 + 出場）。
pub fn compute_round_trip_cost_pct(volume_24h: f64) -> f64 {
    let tier = COST_TIERS
        .iter()
        .find(|t| volume_24h >= t.min_volume_usd)
        .unwrap_or(COST_TIERS.last().unwrap());
    (tier.taker_fee_pct + tier.slippage_pct) * 2.0 / 100.0 * 100.0
}

/// Result of the cost gate check / 成本門控檢查結果
pub struct CostGateResult {
    /// Whether the trade should be rejected / 是否應拒絕交易
    pub rejected: bool,
    /// Human-readable reason / 人類可讀原因
    pub reason: String,
}

/// Check whether a trade should be rejected due to insufficient volatility vs cost.
/// 檢查交易是否應因波動性不足以覆蓋成本而被拒絕。
///
/// # Arguments / 參數
/// - `atr_pct`:    ATR as percentage of price (None = fail-open) / ATR 佔價格百分比（None = 放行）
/// - `win_rate`:   Estimated strategy win rate (default 0.5) / 策略預估勝率（預設 0.5）
/// - `daily_trade_count`: Trades executed today so far / 今日已執行交易數
/// - `volume_24h`: 24-hour USD volume for the symbol / 該幣種 24h 美元成交量
pub fn should_reject_for_cost(
    atr_pct: Option<f64>,
    win_rate: f64,
    daily_trade_count: u32,
    volume_24h: f64,
) -> CostGateResult {
    // 1. No ATR data → fail-open (don't block when we lack data)
    //    沒有 ATR 資料 → 放行（資料不足時不阻塞）
    let atr = match atr_pct {
        Some(a) => a,
        None => {
            return CostGateResult {
                rejected: false,
                reason: "no ATR data, fail-open".into(),
            }
        }
    };

    // 2. Compute round-trip cost / 計算往返成本
    let c_round = compute_round_trip_cost_pct(volume_24h);

    // 3. Clamp win rate to [0.3, 1.0] (prevent division issues)
    //    限制勝率在 [0.3, 1.0]（防止除法問題）
    let clamped_wr = win_rate.clamp(0.3, 1.0);

    // 4. Minimum required move = cost / win_rate × safety margin 1.3
    //    最低要求波動 = 成本 / 勝率 × 安全邊際 1.3
    let min_move_pct = c_round / clamped_wr * 1.3;

    // 5. Safety valve: first trade of day AND ATR > 0.5×cost → allow
    //    安全閥：今日首筆交易且 ATR > 0.5×成本 → 放行
    if daily_trade_count == 0 && atr > c_round * 0.5 {
        return CostGateResult {
            rejected: false,
            reason: format!(
                "safety valve: first trade, ATR {:.4}% > 0.5×cost {:.4}%",
                atr,
                c_round * 0.5
            ),
        };
    }

    // 6. Reject if ATR < minimum required move / ATR < 最低要求波動則拒絕
    if atr < min_move_pct {
        CostGateResult {
            rejected: true,
            reason: format!(
                "ATR {:.4}% < min_move {:.4}% (cost={:.4}%, wr={:.2})",
                atr, min_move_pct, c_round, clamped_wr
            ),
        }
    } else {
        CostGateResult {
            rejected: false,
            reason: format!(
                "ATR {:.4}% >= min_move {:.4}% (cost={:.4}%)",
                atr, min_move_pct, c_round
            ),
        }
    }
}

// ===========================================================================
// Tests / 測試
// ===========================================================================
#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cost_tier_high_volume() {
        // 1B+ volume → slippage 0.01%, fee 0.055%
        let cost = compute_round_trip_cost_pct(2_000_000_000.0);
        let expected = (0.01 + 0.055) * 2.0;
        assert!((cost - expected).abs() < 1e-9, "high vol cost={cost}");
    }

    #[test]
    fn test_cost_tier_mid_volume() {
        // 50M is >= 10M tier but < 100M → slippage 0.05%
        let cost = compute_round_trip_cost_pct(50_000_000.0);
        let expected = (0.05 + 0.055) * 2.0;
        assert!((cost - expected).abs() < 1e-9, "mid vol cost={cost}");
    }

    #[test]
    fn test_cost_tier_low_volume() {
        // 500K → lowest tier: slippage 0.30%
        let cost = compute_round_trip_cost_pct(500_000.0);
        let expected = (0.30 + 0.055) * 2.0;
        assert!((cost - expected).abs() < 1e-9, "low vol cost={cost}");
    }

    #[test]
    fn test_cost_tier_exact_boundary() {
        // Exactly 10M → should match the 10M tier
        let cost = compute_round_trip_cost_pct(10_000_000.0);
        let expected = (0.05 + 0.055) * 2.0;
        assert!((cost - expected).abs() < 1e-9);
    }

    #[test]
    fn test_reject_no_atr_fail_open() {
        let res = should_reject_for_cost(None, 0.5, 5, 100_000_000.0);
        assert!(!res.rejected, "None ATR should pass: {}", res.reason);
    }

    #[test]
    fn test_reject_low_atr_high_cost() {
        // Low volume (high cost) + tiny ATR → should reject
        let res = should_reject_for_cost(Some(0.1), 0.5, 3, 500_000.0);
        assert!(res.rejected, "Low ATR should be rejected: {}", res.reason);
    }

    #[test]
    fn test_accept_high_atr() {
        // High ATR + high volume (low cost) → should pass
        let res = should_reject_for_cost(Some(2.0), 0.5, 3, 1_000_000_000.0);
        assert!(!res.rejected, "High ATR should pass: {}", res.reason);
    }

    #[test]
    fn test_safety_valve_first_trade() {
        // First trade of day, ATR barely above 0.5×cost → allow
        let cost = compute_round_trip_cost_pct(1_000_000.0);
        let atr = cost * 0.6; // above 0.5×cost but below min_move
        let res = should_reject_for_cost(Some(atr), 0.5, 0, 1_000_000.0);
        assert!(
            !res.rejected,
            "Safety valve should allow first trade: {}",
            res.reason
        );
    }

    #[test]
    fn test_safety_valve_not_first_trade() {
        // Same ATR but not first trade → should reject
        let cost = compute_round_trip_cost_pct(1_000_000.0);
        let atr = cost * 0.6;
        let res = should_reject_for_cost(Some(atr), 0.5, 1, 1_000_000.0);
        assert!(
            res.rejected,
            "Non-first trade with low ATR should reject: {}",
            res.reason
        );
    }

    #[test]
    fn test_win_rate_clamped_low() {
        // Very low win rate (0.1) → clamped to 0.3
        let res1 = should_reject_for_cost(Some(1.5), 0.1, 3, 100_000_000.0);
        let res2 = should_reject_for_cost(Some(1.5), 0.3, 3, 100_000_000.0);
        // Both should yield same result since 0.1 is clamped to 0.3
        assert_eq!(res1.rejected, res2.rejected);
    }

    #[test]
    fn test_zero_volume_uses_lowest_tier() {
        let cost = compute_round_trip_cost_pct(0.0);
        let expected = (0.30 + 0.055) * 2.0;
        assert!((cost - expected).abs() < 1e-9);
    }
}
