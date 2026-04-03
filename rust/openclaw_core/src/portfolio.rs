//! Portfolio risk control — correlation, concentration, reserve checks.
//! 組合風控 — 相關性、集中度、儲備檢查。

use serde::{Deserialize, Serialize};

// ═══════════════════════════════════════════════════════════════════════════════
// Config / 配置
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortfolioConfig {
    pub correlation_threshold: f64,
    pub correlation_lookback: usize,
    pub min_data_points: usize,
    pub max_sector_exposure_pct: f64,
    pub min_reserve_buffer_pct: f64,
}

impl Default for PortfolioConfig {
    fn default() -> Self {
        Self {
            correlation_threshold: 0.7,
            correlation_lookback: 20,
            min_data_points: 5,
            max_sector_exposure_pct: 40.0,
            min_reserve_buffer_pct: 30.0,
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Correlation / 相關性
// ═══════════════════════════════════════════════════════════════════════════════

/// Compute Pearson correlation coefficient between two return series.
/// 計算兩個收益率序列的 Pearson 相關係數。
pub fn pearson_correlation(x: &[f64], y: &[f64]) -> Option<f64> {
    let n = x.len().min(y.len());
    if n < 2 {
        return None;
    }

    let mean_x: f64 = x[..n].iter().sum::<f64>() / n as f64;
    let mean_y: f64 = y[..n].iter().sum::<f64>() / n as f64;

    let mut cov = 0.0;
    let mut var_x = 0.0;
    let mut var_y = 0.0;

    for i in 0..n {
        let dx = x[i] - mean_x;
        let dy = y[i] - mean_y;
        cov += dx * dy;
        var_x += dx * dx;
        var_y += dy * dy;
    }

    let denom = (var_x * var_y).sqrt();
    if denom < 1e-15 {
        return None;
    }

    Some(cov / denom)
}

// ═══════════════════════════════════════════════════════════════════════════════
// Portfolio Check / 組合檢查
// ═══════════════════════════════════════════════════════════════════════════════

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortfolioCheckResult {
    pub allowed: bool,
    pub reserve_buffer_pct: f64,
    pub sector_exposure_pct: f64,
    pub max_correlation: f64,
    pub rejection_reasons: Vec<String>,
}

/// Holding for portfolio checks.
/// 持倉用於組合檢查。
#[derive(Debug, Clone)]
pub struct Holding {
    pub symbol: String,
    pub sector: String,
    pub side: String,
    pub notional: f64,
    pub returns: Vec<f64>,
}

/// Check if a new position is allowed given existing portfolio.
/// 檢查新持倉在現有組合下是否被允許。
pub fn check_portfolio_risk(
    config: &PortfolioConfig,
    balance: f64,
    holdings: &[Holding],
    new_notional: f64,
    new_sector: &str,
    new_side: &str,
    new_returns: &[f64],
) -> PortfolioCheckResult {
    let mut reasons = Vec::new();

    // Check 1: Reserve buffer
    let total_exposure: f64 = holdings.iter().map(|h| h.notional).sum();
    let used_pct = if balance > 0.0 {
        (total_exposure + new_notional) / balance * 100.0
    } else {
        100.0
    };
    let reserve_pct = (100.0 - used_pct).max(0.0);

    if reserve_pct < config.min_reserve_buffer_pct {
        reasons.push(format!(
            "reserve_buffer: {reserve_pct:.1}% < min {:.1}%",
            config.min_reserve_buffer_pct
        ));
    }

    // Check 2: Sector concentration
    let sector_exposure: f64 = holdings.iter()
        .filter(|h| h.sector == new_sector)
        .map(|h| h.notional)
        .sum::<f64>() + new_notional;
    let sector_pct = if balance > 0.0 { sector_exposure / balance * 100.0 } else { 100.0 };

    if sector_pct > config.max_sector_exposure_pct {
        reasons.push(format!(
            "sector_concentration: {new_sector} {sector_pct:.1}% > max {:.1}%",
            config.max_sector_exposure_pct
        ));
    }

    // Check 3: Correlation gate
    let mut max_corr = 0.0_f64;
    for h in holdings {
        if h.side != new_side { continue; }
        if h.returns.len() < config.min_data_points || new_returns.len() < config.min_data_points {
            continue;
        }
        if let Some(corr) = pearson_correlation(&h.returns, new_returns) {
            max_corr = max_corr.max(corr);
            if corr > config.correlation_threshold {
                reasons.push(format!(
                    "correlation: {} r={corr:.3} > threshold {:.2}",
                    h.symbol, config.correlation_threshold
                ));
            }
        }
    }

    PortfolioCheckResult {
        allowed: reasons.is_empty(),
        reserve_buffer_pct: reserve_pct,
        sector_exposure_pct: sector_pct,
        max_correlation: max_corr,
        rejection_reasons: reasons,
    }
}

/// Compute portfolio-wide metrics.
/// 計算組合級指標。
pub fn compute_portfolio_metrics(
    balance: f64,
    holdings: &[Holding],
) -> PortfolioMetrics {
    let total_exposure: f64 = holdings.iter().map(|h| h.notional).sum();
    let reserve_pct = if balance > 0.0 {
        (balance - total_exposure) / balance * 100.0
    } else {
        0.0
    };

    // Pairwise correlations
    let mut corr_sum = 0.0;
    let mut corr_count = 0u32;
    for i in 0..holdings.len() {
        for j in (i + 1)..holdings.len() {
            if holdings[i].returns.len() >= 5 && holdings[j].returns.len() >= 5 {
                if let Some(r) = pearson_correlation(&holdings[i].returns, &holdings[j].returns) {
                    corr_sum += r;
                    corr_count += 1;
                }
            }
        }
    }
    let avg_corr = if corr_count > 0 { corr_sum / corr_count as f64 } else { 0.0 };
    let effective_diversification = if avg_corr > 0.01 {
        (1.0 / avg_corr).min(holdings.len() as f64)
    } else {
        holdings.len() as f64
    };

    PortfolioMetrics {
        total_exposure,
        reserve_buffer_pct: reserve_pct,
        position_count: holdings.len(),
        avg_correlation: avg_corr,
        effective_diversification,
    }
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct PortfolioMetrics {
    pub total_exposure: f64,
    pub reserve_buffer_pct: f64,
    pub position_count: usize,
    pub avg_correlation: f64,
    pub effective_diversification: f64,
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_pearson_perfect_positive() {
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let y = vec![2.0, 4.0, 6.0, 8.0, 10.0];
        let r = pearson_correlation(&x, &y).unwrap();
        assert!((r - 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_pearson_perfect_negative() {
        let x = vec![1.0, 2.0, 3.0, 4.0, 5.0];
        let y = vec![10.0, 8.0, 6.0, 4.0, 2.0];
        let r = pearson_correlation(&x, &y).unwrap();
        assert!((r + 1.0).abs() < 1e-10);
    }

    #[test]
    fn test_pearson_insufficient_data() {
        assert!(pearson_correlation(&[1.0], &[2.0]).is_none());
        assert!(pearson_correlation(&[], &[]).is_none());
    }

    #[test]
    fn test_pearson_constant_returns_none() {
        let x = vec![1.0, 1.0, 1.0, 1.0];
        let y = vec![2.0, 3.0, 4.0, 5.0];
        assert!(pearson_correlation(&x, &y).is_none());
    }

    #[test]
    fn test_reserve_buffer_check_pass() {
        let config = PortfolioConfig::default();
        let result = check_portfolio_risk(
            &config, 10000.0, &[], 3000.0, "crypto", "Buy", &[],
        );
        assert!(result.allowed);
        assert!((result.reserve_buffer_pct - 70.0).abs() < 0.1);
    }

    #[test]
    fn test_reserve_buffer_check_fail() {
        let config = PortfolioConfig::default();
        let holdings = vec![Holding {
            symbol: "BTC".into(), sector: "crypto".into(), side: "Buy".into(),
            notional: 6000.0, returns: vec![],
        }];
        let result = check_portfolio_risk(
            &config, 10000.0, &holdings, 2000.0, "crypto", "Buy", &[],
        );
        assert!(!result.allowed);
        assert!(result.rejection_reasons[0].starts_with("reserve_buffer"));
    }

    #[test]
    fn test_sector_concentration_fail() {
        let config = PortfolioConfig::default();
        let holdings = vec![Holding {
            symbol: "BTC".into(), sector: "defi".into(), side: "Buy".into(),
            notional: 3500.0, returns: vec![],
        }];
        let result = check_portfolio_risk(
            &config, 10000.0, &holdings, 1000.0, "defi", "Buy", &[],
        );
        assert!(!result.allowed);
        assert!(result.rejection_reasons.iter().any(|r| r.starts_with("sector_concentration")));
    }

    #[test]
    fn test_correlation_gate_fail() {
        let config = PortfolioConfig::default();
        let returns_a = vec![0.01, 0.02, 0.03, 0.04, 0.05];
        let returns_b = vec![0.01, 0.02, 0.03, 0.04, 0.05]; // perfect correlation
        let holdings = vec![Holding {
            symbol: "BTC".into(), sector: "crypto".into(), side: "Buy".into(),
            notional: 1000.0, returns: returns_a,
        }];
        let result = check_portfolio_risk(
            &config, 10000.0, &holdings, 1000.0, "crypto", "Buy", &returns_b,
        );
        assert!(!result.allowed);
        assert!((result.max_correlation - 1.0).abs() < 0.01);
    }

    #[test]
    fn test_correlation_different_sides_skip() {
        let config = PortfolioConfig::default();
        let returns = vec![0.01, 0.02, 0.03, 0.04, 0.05];
        let holdings = vec![Holding {
            symbol: "BTC".into(), sector: "crypto".into(), side: "Sell".into(),
            notional: 1000.0, returns: returns.clone(),
        }];
        let result = check_portfolio_risk(
            &config, 10000.0, &holdings, 1000.0, "crypto", "Buy", &returns,
        );
        // Different sides → correlation check skipped
        assert_eq!(result.max_correlation, 0.0);
    }

    #[test]
    fn test_portfolio_metrics() {
        let holdings = vec![
            Holding { symbol: "BTC".into(), sector: "crypto".into(), side: "Buy".into(),
                notional: 2000.0, returns: vec![0.01, 0.02, 0.03, 0.04, 0.05] },
            Holding { symbol: "ETH".into(), sector: "crypto".into(), side: "Buy".into(),
                notional: 1000.0, returns: vec![0.01, 0.02, 0.03, 0.04, 0.05] },
        ];
        let m = compute_portfolio_metrics(10000.0, &holdings);
        assert!((m.total_exposure - 3000.0).abs() < 0.01);
        assert!((m.reserve_buffer_pct - 70.0).abs() < 0.01);
        assert_eq!(m.position_count, 2);
        assert!((m.avg_correlation - 1.0).abs() < 0.01); // identical returns
    }
}
