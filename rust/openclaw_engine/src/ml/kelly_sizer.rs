//! Kelly position sizer — fractional Kelly with sample-size adjustment.
//! Kelly 倉位管理器 — 帶樣本量調整的分數 Kelly。
//!
//! MODULE_NOTE (EN): Ported from Python position_sizer.py. Computes Kelly-optimal
//!   position size with conservative fractional adjustment:
//!   - < `young_threshold` trades (default 50): young_fraction (default 1/8)
//!   - < `mature_threshold` trades (default 200): mature_fraction (default 1/6)
//!   - >= `mature_threshold` trades: established_fraction (default 1/4)
//!   Tier boundaries and fractions are TOML-configurable via `RiskConfig.kelly`.
//!   ATR-based volatility adjustment caps size in high-vol regimes.
//! MODULE_NOTE (中): 從 Python position_sizer.py 移植。計算 Kelly 最優倉位，
//!   保守分數調整：< young_threshold 筆 young_fraction，< mature_threshold 筆
//!   mature_fraction，>= mature_threshold 筆 established_fraction。分級邊界和
//!   分數可由 `RiskConfig.kelly` TOML 配置。
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
    /// ATR% normalization anchor for vol adjustment (typical 5m crypto perp = 2%)
    /// ATR% 歸一化錨點，用於波動率調整（5m 加密永續典型值 2%）
    pub reference_atr_pct: f64,
    /// Minimum vol multiplier (floor for high-vol compression) / 最小波動乘數
    pub vol_mult_floor: f64,
    /// Maximum vol multiplier (ceil for low-vol expansion) / 最大波動乘數
    pub vol_mult_ceil: f64,
    /// G7-01 (2026-04-24): Sample-size tier boundary for "young" → "mature".
    /// Trades < `young_threshold` use 1/8 Kelly (most conservative).
    /// Default 50 preserves pre-G7-01 behavior; mirror of
    /// `RiskConfig.kelly.young_threshold`. Must satisfy `young < mature`.
    /// G7-01：樣本量分級邊界 — 「young」轉「mature」門檻。
    /// 交易數 < `young_threshold` 用 1/8 Kelly（最保守）。預設 50 保留 G7-01 前行為，
    /// 對應 `RiskConfig.kelly.young_threshold`。需滿足 `young < mature`。
    pub young_threshold: u32,
    /// G7-01 (2026-04-24): Sample-size tier boundary for "mature" → "established".
    /// Trades in `[young_threshold, mature_threshold)` use 1/6 Kelly;
    /// trades `>= mature_threshold` use 1/4 Kelly. Default 200 preserves
    /// pre-G7-01 behavior; mirror of `RiskConfig.kelly.mature_threshold`.
    /// G7-01：樣本量分級邊界 — 「mature」轉「established」門檻。
    /// 交易數 ∈ `[young_threshold, mature_threshold)` 用 1/6 Kelly；
    /// `>= mature_threshold` 用 1/4 Kelly。預設 200 保留 G7-01 前行為。
    pub mature_threshold: u32,
    /// Fraction applied while the cell is young (default 1/8 Kelly).
    /// young 分層使用的 Kelly 分數（預設 1/8）。
    pub young_fraction: f64,
    /// Fraction applied while the cell is mature (default 1/6 Kelly).
    /// mature 分層使用的 Kelly 分數（預設 1/6）。
    pub mature_fraction: f64,
    /// Fraction applied once established (default 1/4 Kelly).
    /// established 分層使用的 Kelly 分數（預設 1/4）。
    pub established_fraction: f64,
}

impl Default for KellyConfig {
    fn default() -> Self {
        Self {
            max_fraction: 0.25,
            min_trades: 50,
            risk_pct: crate::config::DEFAULT_PER_TRADE_RISK_PCT,
            enabled: true,
            reference_atr_pct: 0.02,
            vol_mult_floor: 0.5,
            vol_mult_ceil: 1.5,
            young_threshold: 50,
            mature_threshold: 200,
            young_fraction: 1.0 / 8.0,
            mature_fraction: 1.0 / 6.0,
            established_fraction: 1.0 / 4.0,
        }
    }
}

impl KellyConfig {
    /// Build Kelly config from the authoritative risk snapshot.
    /// 從權威 RiskConfig 快照派生 Kelly 配置。
    pub fn from_risk_config(config: &crate::config::RiskConfig) -> Self {
        Self {
            risk_pct: config.limits.per_trade_risk_pct,
            young_threshold: config.kelly.young_threshold,
            mature_threshold: config.kelly.mature_threshold,
            young_fraction: config.kelly.young_fraction,
            mature_fraction: config.kelly.mature_fraction,
            established_fraction: config.kelly.established_fraction,
            ..Self::default()
        }
    }

    /// G7-01 (2026-04-24): Validate Kelly tier boundaries.
    /// Both thresholds must be > 0 and `young_threshold < mature_threshold`.
    /// G7-01：驗證 Kelly 分級邊界。兩個門檻必須 > 0 且 young < mature。
    pub fn validate(&self) -> Result<(), String> {
        if self.young_threshold == 0 {
            return Err("kelly.young_threshold must be > 0".into());
        }
        if self.mature_threshold == 0 {
            return Err("kelly.mature_threshold must be > 0".into());
        }
        if self.young_threshold >= self.mature_threshold {
            return Err(format!(
                "kelly.young_threshold ({}) must be < kelly.mature_threshold ({})",
                self.young_threshold, self.mature_threshold
            ));
        }
        validate_kelly_fraction("kelly.young_fraction", self.young_fraction)?;
        validate_kelly_fraction("kelly.mature_fraction", self.mature_fraction)?;
        validate_kelly_fraction("kelly.established_fraction", self.established_fraction)?;
        if self.young_fraction > self.mature_fraction {
            return Err("kelly.young_fraction must be <= kelly.mature_fraction".into());
        }
        if self.mature_fraction > self.established_fraction {
            return Err("kelly.mature_fraction must be <= kelly.established_fraction".into());
        }
        Ok(())
    }
}

fn validate_kelly_fraction(name: &str, value: f64) -> Result<(), String> {
    if !value.is_finite() || value <= 0.0 || value > 1.0 {
        return Err(format!("{name} must be finite and in (0, 1]"));
    }
    Ok(())
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
        // FIX-27: Negative Kelly → negative edge → reject (return 0).
        // Old behavior returned 1% minimum which actively trades a losing edge.
        // FIX-27：Kelly 為負 → 負 edge → 拒絕（返回 0）。
        debug!(
            kelly = kelly_full,
            "negative Kelly, rejecting / Kelly 為負，拒絕開倉"
        );
        return 0.0;
    }

    // Fractional Kelly based on sample size (conservative).
    // G7-01 (2026-04-24): boundaries now read from `config.young_threshold` /
    // `config.mature_threshold` (TOML-configurable via `RiskConfig.kelly`);
    // defaults 50/200 preserve pre-G7-01 behavior.
    // G7-01：分級邊界改讀 config，預設 50/200 保留原行為。
    let fraction = if stats.total_trades < config.young_threshold {
        kelly_full * config.young_fraction
    } else if stats.total_trades < config.mature_threshold {
        kelly_full * config.mature_fraction
    } else {
        kelly_full * config.established_fraction
    };

    // Cap at configured max fraction
    let capped = fraction.min(config.max_fraction);

    // Kelly qty = fraction * balance / price
    let kelly_qty = capped * balance / price;

    // ATR volatility adjustment: reduce in high-vol regimes.
    // reference_atr_pct is the normalization anchor (typical crypto perp 5m ATR%
    // sits in 1–4% band; default 2% so the multiplier sits at 1.0 in steady state).
    // ATR 波動調整：高波動市場縮量。reference_atr_pct 為歸一化錨點，可透過 KellyConfig 調整。
    let vol_adjusted = if atr_pct > 0.0 {
        let vol_multiplier =
            (config.reference_atr_pct / atr_pct).clamp(config.vol_mult_floor, config.vol_mult_ceil);
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
    fn test_negative_kelly_rejects() {
        // FIX-27: Negative Kelly → 0 qty (reject), not 1% minimum.
        let cfg = KellyConfig::default();
        // 30% win rate, avg_win=50, avg_loss=100 → negative Kelly
        let stats = make_stats(30, 70, 50.0, 100.0);
        let qty = compute_kelly_qty(&cfg, &stats, 10000.0, 50000.0, 0.02, 1.0);
        assert_eq!(qty, 0.0, "negative Kelly must return 0 (reject)");
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

    // ----- G7-01 (2026-04-24): tier boundary configurability tests -----

    #[test]
    fn test_g7_01_default_tier_thresholds() {
        // Defaults must preserve pre-W-AUDIT-6 hardcoded values 50/200 +
        // 1/8, 1/6, 1/4.
        let cfg = KellyConfig::default();
        assert_eq!(cfg.young_threshold, 50, "default young_threshold = 50");
        assert_eq!(cfg.mature_threshold, 200, "default mature_threshold = 200");
        assert!((cfg.young_fraction - 1.0 / 8.0).abs() < f64::EPSILON);
        assert!((cfg.mature_fraction - 1.0 / 6.0).abs() < f64::EPSILON);
        assert!((cfg.established_fraction - 1.0 / 4.0).abs() < f64::EPSILON);
        assert!(cfg.validate().is_ok(), "default must validate");
    }

    #[test]
    fn test_g7_01_validate_rejects_inverted_thresholds() {
        // young >= mature is invalid (would skip the 1/6 Kelly tier).
        // young >= mature 無效（會跳過 1/6 Kelly 分層）。
        let cfg_eq = KellyConfig {
            young_threshold: 100,
            mature_threshold: 100,
            ..Default::default()
        };
        assert!(
            cfg_eq.validate().is_err(),
            "young == mature must be rejected"
        );

        let cfg_gt = KellyConfig {
            young_threshold: 250,
            mature_threshold: 100,
            ..Default::default()
        };
        assert!(
            cfg_gt.validate().is_err(),
            "young > mature must be rejected"
        );
    }

    #[test]
    fn test_g7_01_validate_rejects_zero_thresholds() {
        // 0 is invalid for either threshold.
        // 任一門檻為 0 皆無效。
        let cfg_young_zero = KellyConfig {
            young_threshold: 0,
            mature_threshold: 200,
            ..Default::default()
        };
        assert!(
            cfg_young_zero.validate().is_err(),
            "young_threshold = 0 must be rejected"
        );

        let cfg_mature_zero = KellyConfig {
            young_threshold: 50,
            mature_threshold: 0,
            ..Default::default()
        };
        assert!(
            cfg_mature_zero.validate().is_err(),
            "mature_threshold = 0 must be rejected"
        );
    }

    #[test]
    fn test_w_audit_6_validate_rejects_bad_fraction_config() {
        let mut cfg = KellyConfig::default();

        cfg.young_fraction = 0.0;
        assert!(cfg.validate().is_err(), "zero young fraction must reject");

        cfg = KellyConfig::default();
        cfg.mature_fraction = f64::NAN;
        assert!(cfg.validate().is_err(), "NaN mature fraction must reject");

        cfg = KellyConfig::default();
        cfg.established_fraction = 1.1;
        assert!(cfg.validate().is_err(), "fraction > 1 must reject");

        cfg = KellyConfig::default();
        cfg.young_fraction = 0.20;
        cfg.mature_fraction = 0.10;
        assert!(cfg.validate().is_err(), "decreasing fractions must reject");
    }

    #[test]
    fn test_g7_01_custom_thresholds_change_tier_selection() {
        // Verify that the tier boundary is actually read from `config.young_threshold`
        // and not hardcoded. With `min_trades` lowered to 10 (so the tier branch is
        // exercised), a 50-trade sample lands in different tiers under different
        // configs:
        //   - default (young=50):     50 < 50  is false → mature (1/6 Kelly)
        //   - custom  (young=80):     50 < 80  is true  → young  (1/8 Kelly)
        // Same Kelly-full ⇒ qty_default > qty_custom (default's 1/6 beats 1/8).
        // 同樣 50 筆樣本，預設邊界 50 → mature (1/6)，自訂邊界 80 → young (1/8)。
        let cfg_default = KellyConfig {
            min_trades: 10, // expose the tier branch
            ..KellyConfig::default()
        };
        let cfg_custom = KellyConfig {
            young_threshold: 80,
            mature_threshold: 200,
            min_trades: 10,
            ..KellyConfig::default()
        };
        // 50 trades: 30 wins + 20 losses, win_rate 0.6, avg_win=100, avg_loss=80,
        // R=1.25 → Kelly_full = 0.6 - 0.4/1.25 = 0.28 (positive).
        // 50 筆 60% 勝率，Kelly_full = 0.28 > 0，進 tier 分支。
        let stats = make_stats(30, 20, 100.0, 80.0);
        assert_eq!(stats.total_trades, 50);

        let qty_default = compute_kelly_qty(&cfg_default, &stats, 10000.0, 50000.0, 0.02, 1.0);
        let qty_custom = compute_kelly_qty(&cfg_custom, &stats, 10000.0, 50000.0, 0.02, 1.0);

        // Default (1/6) > custom (1/8) for the same Kelly-full.
        // 同 Kelly-full 下，1/6 > 1/8。
        assert!(
            qty_default > qty_custom,
            "default mature tier (1/6, young=50) must size larger than custom young tier \
             (1/8, young=80): default={} custom={}",
            qty_default,
            qty_custom
        );
    }

    #[test]
    fn test_w_audit_6_custom_fractions_change_tier_size() {
        let stats = make_stats(30, 20, 100.0, 80.0);
        let baseline = KellyConfig {
            min_trades: 10,
            ..KellyConfig::default()
        };
        let larger_mature = KellyConfig {
            min_trades: 10,
            mature_fraction: 0.20,
            ..KellyConfig::default()
        };

        let qty_baseline = compute_kelly_qty(&baseline, &stats, 10_000.0, 50_000.0, 0.02, 1.0);
        let qty_larger = compute_kelly_qty(&larger_mature, &stats, 10_000.0, 50_000.0, 0.02, 1.0);

        assert!(
            qty_larger > qty_baseline,
            "raising mature_fraction must increase same-cell Kelly size"
        );
    }

    #[test]
    fn test_w_audit_6_from_risk_config_uses_per_trade_risk_pct() {
        let mut risk_config = crate::config::RiskConfig::default();
        risk_config.limits.per_trade_risk_pct = crate::config::MIN_PER_TRADE_RISK_PCT;
        risk_config.kelly.young_fraction = 0.10;
        risk_config.kelly.mature_fraction = 0.20;
        risk_config.kelly.established_fraction = 0.30;

        let cfg = KellyConfig::from_risk_config(&risk_config);

        assert!(
            (cfg.risk_pct - risk_config.limits.per_trade_risk_pct).abs() < 1e-12,
            "Kelly cold-start risk_pct must be derived from RiskConfig.limits"
        );
        assert!((cfg.young_fraction - 0.10).abs() < 1e-12);
        assert!((cfg.mature_fraction - 0.20).abs() < 1e-12);
        assert!((cfg.established_fraction - 0.30).abs() < 1e-12);
    }
}
