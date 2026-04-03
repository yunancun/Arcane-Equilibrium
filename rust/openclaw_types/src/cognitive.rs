//! Cognitive modulation parameters, regret tracking, dream engine insights.
//! 認知調製參數、遺憾追蹤、夢境引擎洞見。
//!
//! Mirrors Python modules: cognitive_modulator.py, opportunity_tracker.py, dream_engine.py.

use serde::{Deserialize, Serialize};

/// Cognitive modulator output parameters (SPEC §2).
/// 認知調製器輸出參數。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct CognitiveParams {
    /// Signal confidence floor (0.0 - 1.0).
    pub confidence_floor: f64,
    /// Position size ceiling multiplier.
    pub qty_ceiling: f64,
    /// Stop-loss distance multiplier.
    pub stoploss_multiplier: f64,
    /// Scan interval (seconds).
    pub scan_interval_s: u32,
    /// Update count.
    pub update_count: u32,
}

impl Default for CognitiveParams {
    fn default() -> Self {
        Self {
            confidence_floor: 0.60,
            qty_ceiling: 1.0,
            stoploss_multiplier: 1.0,
            scan_interval_s: 1800,
            update_count: 0,
        }
    }
}

/// Regret and opportunity tracking summary (SPEC §3).
/// 遺憾與機會追蹤摘要。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RegretSummary {
    pub bullets_dodged_pct: f64,
    pub regret_from_undertrading_pct: f64,
    /// "overtrading", "undertrading", or "balanced"
    pub net_regret_direction: String,
    pub sample_count: u32,
    pub top_missed_opportunity: Option<String>,
}

impl Default for RegretSummary {
    fn default() -> Self {
        Self {
            bullets_dodged_pct: 0.0,
            regret_from_undertrading_pct: 0.0,
            net_regret_direction: "balanced".into(),
            sample_count: 0,
            top_missed_opportunity: None,
        }
    }
}

/// Monte Carlo simulation insight from DreamEngine (SPEC §4).
/// 來自 DreamEngine 的蒙特卡洛模擬洞見。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct DreamInsight {
    pub strategy_name: String,
    pub param_name: String,
    pub current_value: f64,
    pub suggested_value: f64,
    pub improvement_pct: f64,
    pub confidence: f64,
    pub sample_count: u32,
}

impl DreamInsight {
    pub fn new(strategy_name: String, param_name: String, current: f64, suggested: f64) -> Self {
        let improvement = if current.abs() > f64::EPSILON {
            (suggested - current) / current * 100.0
        } else {
            0.0
        };
        Self {
            strategy_name,
            param_name,
            current_value: current,
            suggested_value: suggested,
            improvement_pct: improvement,
            confidence: 0.5,
            sample_count: 0,
        }
    }
}

/// Skipped opportunity record for virtual PnL tracking (SPEC §3).
/// 跳過機會記錄，用於虛擬 PnL 追蹤。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SkippedOpportunity {
    pub opp_id: String,
    pub symbol: String,
    pub direction: String,
    pub entry_price: f64,
    pub entry_ts_ms: u64,
    pub signal_confidence: f64,
    pub skip_reason: String,
    pub current_pnl_pct: f64,
    pub is_settled: bool,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_cognitive_params_default_serde() {
        let cp = CognitiveParams::default();
        let json = serde_json::to_string(&cp).unwrap();
        let de: CognitiveParams = serde_json::from_str(&json).unwrap();
        assert!((de.confidence_floor - 0.60).abs() < f64::EPSILON);
        assert_eq!(de.scan_interval_s, 1800);
    }

    #[test]
    fn test_regret_summary_serde() {
        let rs = RegretSummary::default();
        let json = serde_json::to_string(&rs).unwrap();
        let de: RegretSummary = serde_json::from_str(&json).unwrap();
        assert_eq!(de.net_regret_direction, "balanced");
    }

    #[test]
    fn test_dream_insight_improvement_calc() {
        let di = DreamInsight::new("ma_cross".into(), "fast_period".into(), 10.0, 12.0);
        assert!((di.improvement_pct - 20.0).abs() < 1e-10);
    }

    #[test]
    fn test_dream_insight_zero_current() {
        let di = DreamInsight::new("test".into(), "p".into(), 0.0, 5.0);
        assert!((di.improvement_pct - 0.0).abs() < f64::EPSILON);
    }

    #[test]
    fn test_skipped_opportunity_serde() {
        let so = SkippedOpportunity {
            opp_id: "opp_1".into(),
            symbol: "BTCUSDT".into(),
            direction: "long".into(),
            entry_price: 65000.0,
            entry_ts_ms: 1_700_000_000_000,
            signal_confidence: 0.7,
            skip_reason: "low_confidence".into(),
            current_pnl_pct: 2.5,
            is_settled: false,
        };
        let json = serde_json::to_string(&so).unwrap();
        let de: SkippedOpportunity = serde_json::from_str(&json).unwrap();
        assert_eq!(de.symbol, "BTCUSDT");
    }
}
