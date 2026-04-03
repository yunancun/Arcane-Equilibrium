//! Risk configuration structs and regime multipliers.
//! 風控配置結構體及 regime 乘數。

use serde::{Deserialize, Serialize};

/// Operational risk configuration (merged P0/P1/P2 parameters for hot-path use).
/// 運營風控配置（合併 P0/P1/P2 參數，供熱路徑使用）。
///
/// Distinct from `openclaw_types::RiskConfig` which is the top-level composite.
/// 與 `openclaw_types::RiskConfig`（頂層組合配置）不同。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct RiskManagerConfig {
    // -- P1 global limits / P1 全局限制 --

    /// Maximum stop-loss percentage (hard ceiling) / 最大止損百分比（硬上限）
    pub max_stop_loss_pct: f64,
    /// Maximum take-profit percentage / 最大止盈百分比
    pub max_take_profit_pct: f64,
    /// Whether take-profit is enabled / 是否啟用止盈
    pub tp_enabled: bool,
    /// Max single position as % of balance / 單一持倉佔餘額最大百分比
    pub max_single_position_pct: f64,
    /// Max total exposure as % of balance / 總曝險佔餘額最大百分比
    pub max_total_exposure_pct: f64,
    /// Max correlated exposure as % of balance / 相關曝險佔餘額最大百分比
    pub max_correlated_exposure_pct: f64,
    /// Max allowed leverage / 最大允許槓桿
    pub max_leverage: f64,
    /// Max session drawdown % before halt / 觸發暫停的最大會話回撤百分比
    pub max_session_drawdown_pct: f64,
    /// Max daily loss % / 最大日損百分比
    pub max_daily_loss_pct: f64,
    /// Consecutive losses before cooldown / 連續虧損幾次後進入冷卻
    pub consecutive_loss_cooldown_count: u32,
    /// Cooldown duration in minutes / 冷卻時長（分鐘）
    pub consecutive_loss_cooldown_minutes: u32,
    /// Max holding time in hours / 最大持倉時間（小時）
    pub max_holding_hours: f64,
    /// Cost/edge ratio threshold for close suggestion / 成本邊際比率閾值
    pub max_cost_edge_ratio: f64,

    // -- P2 agent parameters / P2 Agent 參數 --

    /// Whether trailing stop is enabled / 是否啟用追蹤止損
    pub trailing_stop_enabled: bool,
    /// Trailing stop activation threshold % / 追蹤止損啟動門檻百分比
    pub trailing_stop_activation_pct: f64,
    /// Trailing stop distance % / 追蹤止損距離百分比
    pub trailing_stop_distance_pct: f64,
    /// Position size multiplier (1.0 = full) / 持倉大小倍率（1.0 = 滿倉）
    pub position_size_multiplier: f64,
}

impl Default for RiskManagerConfig {
    fn default() -> Self {
        Self {
            max_stop_loss_pct: 5.0,
            max_take_profit_pct: 20.0,
            tp_enabled: false,
            max_single_position_pct: 20.0,
            max_total_exposure_pct: 100.0,
            max_correlated_exposure_pct: 60.0,
            max_leverage: 20.0,
            max_session_drawdown_pct: 15.0,
            max_daily_loss_pct: 5.0,
            consecutive_loss_cooldown_count: 3,
            consecutive_loss_cooldown_minutes: 30,
            max_holding_hours: 72.0,
            max_cost_edge_ratio: 0.8,
            trailing_stop_enabled: true,
            trailing_stop_activation_pct: 1.0,
            trailing_stop_distance_pct: 0.8,
            position_size_multiplier: 1.0,
        }
    }
}

/// Regime-based multipliers for stop-loss, take-profit, and time limits.
/// 基於市場 regime 的止損、止盈、時間限制乘數。
#[derive(Debug, Clone, Copy)]
pub struct RegimeMultipliers {
    /// Stop-loss distance multiplier / 止損距離乘數
    pub stop: f64,
    /// Take-profit distance multiplier / 止盈距離乘數
    pub tp: f64,
    /// Time limit multiplier / 時間限制乘數
    pub time: f64,
}

/// Return regime-specific multipliers for risk parameters.
/// 回傳特定 regime 的風控參數乘數。
///
/// | Regime    | Stop | TP  | Time |
/// |-----------|------|-----|------|
/// | trending  | 1.0  | 1.5 | 1.5  |  ← wider TP, longer hold
/// | volatile  | 1.5  | 0.8 | 0.8  |  ← wider stop, tight TP
/// | ranging   | 0.7  | 0.7 | 0.8  |  ← tight both
/// | squeeze   | 0.6  | 0.5 | 1.0  |  ← very tight, normal time
/// | _default  | 1.0  | 1.0 | 1.0  |
pub fn regime_multipliers(regime: &str) -> RegimeMultipliers {
    match regime {
        "trending" => RegimeMultipliers {
            stop: 1.0,
            tp: 1.5,
            time: 1.5,
        },
        "volatile" => RegimeMultipliers {
            stop: 1.5,
            tp: 0.8,
            time: 0.8,
        },
        "ranging" => RegimeMultipliers {
            stop: 0.7,
            tp: 0.7,
            time: 0.8,
        },
        "squeeze" => RegimeMultipliers {
            stop: 0.6,
            tp: 0.5,
            time: 1.0,
        },
        _ => RegimeMultipliers {
            stop: 1.0,
            tp: 1.0,
            time: 1.0,
        },
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config_values() {
        let cfg = RiskManagerConfig::default();
        assert_eq!(cfg.max_stop_loss_pct, 5.0);
        assert_eq!(cfg.max_leverage, 20.0);
        assert!(!cfg.tp_enabled);
        assert!(cfg.trailing_stop_enabled);
        assert_eq!(cfg.position_size_multiplier, 1.0);
    }

    #[test]
    fn test_config_serde_round_trip() {
        let cfg = RiskManagerConfig::default();
        let json = serde_json::to_string(&cfg).unwrap();
        let de: RiskManagerConfig = serde_json::from_str(&json).unwrap();
        assert_eq!(de.max_stop_loss_pct, cfg.max_stop_loss_pct);
        assert_eq!(de.trailing_stop_distance_pct, cfg.trailing_stop_distance_pct);
    }

    #[test]
    fn test_regime_trending() {
        let rm = regime_multipliers("trending");
        assert_eq!(rm.stop, 1.0);
        assert_eq!(rm.tp, 1.5);
        assert_eq!(rm.time, 1.5);
    }

    #[test]
    fn test_regime_volatile() {
        let rm = regime_multipliers("volatile");
        assert_eq!(rm.stop, 1.5);
        assert_eq!(rm.tp, 0.8);
    }

    #[test]
    fn test_regime_unknown_defaults() {
        let rm = regime_multipliers("unknown_regime");
        assert_eq!(rm.stop, 1.0);
        assert_eq!(rm.tp, 1.0);
        assert_eq!(rm.time, 1.0);
    }
}
