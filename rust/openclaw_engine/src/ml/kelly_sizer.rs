//! Kelly position sizer — fractional Kelly with sample-size adjustment.
//! Kelly 倉位管理器 — 帶樣本量調整的分數 Kelly。
//!
//! MODULE_NOTE (EN): Ported from Python position_sizer.py. Computes Kelly-optimal
//!   position size with conservative fractional adjustment:
//!   - < 50 trades: 1/8 Kelly (most conservative)
//!   - < 200 trades: 1/6 Kelly
//!   - >= 200 trades: 1/4 Kelly (never full Kelly)
//!   ATR-based volatility adjustment caps size in high-vol regimes.
//! MODULE_NOTE (中): 從 Python position_sizer.py 移植。計算 Kelly 最優倉位，
//!   保守分數調整：< 50 筆 1/8，< 200 筆 1/6，>= 200 筆 1/4。
//!   ATR 波動率調整在高波動 regime 中限制倉位。

use tracing::debug;

/// Per-symbol trade statistics for Kelly calculation.
/// 每交易對的交易統計數據，用於 Kelly 計算。
#[derive(Debug, Clone, Default)]
pub struct TradeStats {
    pub total_trades: u32,
    pub wins: u32,
    pub losses: u32,
    pub total_win_pnl: f64,
    pub total_loss_pnl: f64,
}

impl TradeStats {
    /// Record a closed trade result / 記錄已平倉交易結果
    pub fn record(&mut self, pnl: f64) {
        self.total_trades += 1;
        if pnl >= 0.0 {
            self.wins += 1;
            self.total_win_pnl += pnl;
        } else {
            self.losses += 1;
            self.total_loss_pnl += pnl.abs();
        }
    }

    /// Win rate (0.0-1.0) / 勝率
    pub fn win_rate(&self) -> f64 {
        if self.total_trades == 0 {
            return 0.0;
        }
        self.wins as f64 / self.total_trades as f64
    }

    /// Average win amount / 平均獲利金額
    pub fn avg_win(&self) -> f64 {
        if self.wins == 0 {
            return 0.0;
        }
        self.total_win_pnl / self.wins as f64
    }

    /// Average loss amount (positive) / 平均虧損金額（正數）
    pub fn avg_loss(&self) -> f64 {
        if self.losses == 0 {
            return 0.0;
        }
        self.total_loss_pnl / self.losses as f64
    }
}

/// Kelly position sizer configuration.
/// Kelly 倉位管理器配置。
#[derive(Debug, Clone)]
pub struct KellyConfig {
    /// Maximum Kelly fraction (never full Kelly) / 最大 Kelly 分數
    pub max_fraction: f64,
    /// Minimum trades before Kelly activates / Kelly 啟動的最少交易數
    pub min_trades: u32,
    /// Fallback risk percentage (when Kelly inactive) / 回退風險百分比
    pub risk_pct: f64,
    /// Enable Kelly sizing / 啟用 Kelly 倉位管理
    pub enabled: bool,
}

impl Default for KellyConfig {
    fn default() -> Self {
        Self {
            max_fraction: 0.25,
            min_trades: 50,
            risk_pct: 0.03,
            enabled: true,
        }
    }
}

/// Compute Kelly-optimal position quantity.
/// 計算 Kelly 最優倉位數量。
///
/// Returns the recommended qty, never exceeding `max_qty`.
/// 返回建議的 qty，永不超過 `max_qty`。
pub fn compute_kelly_qty(
    config: &KellyConfig,
    stats: &TradeStats,
    balance: f64,
    price: f64,
    atr_pct: f64,
    max_qty: f64,
) -> f64 {
    if !config.enabled || price <= 0.0 || balance <= 0.0 {
        return max_qty; // passthrough — let P1 cap decide
    }

    // Not enough trades → use simple risk-based sizing
    if stats.total_trades < config.min_trades {
        let risk_qty = balance * config.risk_pct / price;
        debug!(
            trades = stats.total_trades,
            min = config.min_trades,
            risk_qty = risk_qty,
            "Kelly inactive, using risk% / Kelly 未啟動"
        );
        return risk_qty.min(max_qty);
    }

    let win_rate = stats.win_rate();
    let avg_win = stats.avg_win();
    let avg_loss = stats.avg_loss();

    if avg_loss <= 0.0 || win_rate <= 0.0 {
        return (balance * config.risk_pct / price).min(max_qty);
    }

    // Kelly formula: f* = W - (1-W)/R where R = avg_win/avg_loss
    let r = avg_win / avg_loss;
    let kelly_full = win_rate - (1.0 - win_rate) / r;

    if kelly_full <= 0.0 {
        // Negative Kelly → edge is negative, minimum sizing
        debug!(
            kelly = kelly_full,
            "negative Kelly, minimum sizing / Kelly 為負"
        );
        return (balance * 0.01 / price).min(max_qty); // 1% minimum
    }

    // Fractional Kelly based on sample size (conservative)
    let fraction = if stats.total_trades < 50 {
        kelly_full / 8.0 // 1/8 Kelly
    } else if stats.total_trades < 200 {
        kelly_full / 6.0 // 1/6 Kelly
    } else {
        kelly_full / 4.0 // 1/4 Kelly
    };

    // Cap at configured max fraction
    let capped = fraction.min(config.max_fraction);

    // Kelly qty = fraction * balance / price
    let kelly_qty = capped * balance / price;

    // ATR volatility adjustment: reduce in high-vol regimes
    let vol_adjusted = if atr_pct > 0.0 {
        let vol_multiplier = (0.02 / atr_pct).clamp(0.5, 1.5); // reference ATR% = 2%
        kelly_qty * vol_multiplier
    } else {
        kelly_qty
    };

    debug!(
        kelly_full = format!("{:.4}", kelly_full),
        fraction = format!("{:.4}", capped),
        kelly_qty = format!("{:.6}", kelly_qty),
        vol_adj = format!("{:.6}", vol_adjusted),
        "Kelly sizing / Kelly 倉位計算"
    );

    vol_adjusted.min(max_qty).max(0.0)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_stats(wins: u32, losses: u32, avg_win: f64, avg_loss: f64) -> TradeStats {
        TradeStats {
            total_trades: wins + losses,
            wins,
            losses,
            total_win_pnl: avg_win * wins as f64,
            total_loss_pnl: avg_loss * losses as f64,
        }
    }

    #[test]
    fn test_fractional_kelly_tiers() {
        let cfg = KellyConfig::default();
        // 60% win rate, avg_win=100, avg_loss=80, R=1.25
        // Full Kelly = 0.6 - 0.4/1.25 = 0.6 - 0.32 = 0.28
        let stats_50 = make_stats(30, 20, 100.0, 80.0);
        let stats_200 = make_stats(120, 80, 100.0, 80.0);

        let qty_50 = compute_kelly_qty(&cfg, &stats_50, 10000.0, 50000.0, 0.02, 1.0);
        let qty_200 = compute_kelly_qty(&cfg, &stats_200, 10000.0, 50000.0, 0.02, 1.0);

        // 50 trades: 1/8 Kelly, 200 trades: 1/4 Kelly → qty_200 > qty_50
        assert!(
            qty_200 > qty_50,
            "more trades = more Kelly confidence: {} vs {}",
            qty_200,
            qty_50
        );
    }

    #[test]
    fn test_negative_kelly_minimum() {
        let cfg = KellyConfig::default();
        // 30% win rate, avg_win=50, avg_loss=100 → negative Kelly
        let stats = make_stats(30, 70, 50.0, 100.0);
        let qty = compute_kelly_qty(&cfg, &stats, 10000.0, 50000.0, 0.02, 1.0);
        assert!(qty > 0.0, "negative Kelly still gives minimum position");
        assert!(
            qty < 0.01,
            "negative Kelly gives very small position: {}",
            qty
        );
    }

    #[test]
    fn test_vol_adjustment() {
        let cfg = KellyConfig::default();
        let stats = make_stats(120, 80, 100.0, 80.0);

        let qty_low_vol = compute_kelly_qty(&cfg, &stats, 10000.0, 50000.0, 0.01, 1.0);
        let qty_high_vol = compute_kelly_qty(&cfg, &stats, 10000.0, 50000.0, 0.04, 1.0);

        assert!(
            qty_low_vol > qty_high_vol,
            "low vol = larger position: {} vs {}",
            qty_low_vol,
            qty_high_vol
        );
    }

    #[test]
    fn test_never_exceeds_max() {
        let cfg = KellyConfig::default();
        let stats = make_stats(180, 20, 1000.0, 10.0); // amazing stats
        let qty = compute_kelly_qty(&cfg, &stats, 1_000_000.0, 50000.0, 0.02, 0.1);
        assert!(qty <= 0.1, "never exceeds max_qty: {}", qty);
    }

    #[test]
    fn test_below_min_trades_uses_risk() {
        let cfg = KellyConfig {
            min_trades: 50,
            risk_pct: 0.03,
            ..Default::default()
        };
        let stats = make_stats(10, 5, 100.0, 80.0); // only 15 trades
        let qty = compute_kelly_qty(&cfg, &stats, 10000.0, 50000.0, 0.02, 1.0);
        // Should use risk_pct: 10000 * 0.03 / 50000 = 0.006
        assert!((qty - 0.006).abs() < 0.001, "should use risk%: {}", qty);
    }

    #[test]
    fn test_disabled_passthrough() {
        let cfg = KellyConfig {
            enabled: false,
            ..Default::default()
        };
        let stats = make_stats(100, 50, 100.0, 80.0);
        let qty = compute_kelly_qty(&cfg, &stats, 10000.0, 50000.0, 0.02, 0.5);
        assert_eq!(qty, 0.5, "disabled = passthrough max_qty");
    }
}
