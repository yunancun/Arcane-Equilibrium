//! Stateless regime → risk-multiplier lookup used by hot-path stop math.
//! 無狀態 regime → 風控乘數查找，供熱路徑止損計算使用。
//!
//! NOTE: The authoritative, operator-tunable regime multipliers live in
//! `openclaw_engine::config::risk_config::RegimeMultipliers`. This helper
//! retains the legacy hardcoded lookup for `openclaw_core::risk::stops`,
//! which must remain crate-local (core cannot depend on engine).
//! 說明：可調的權威 regime 乘數在 engine::config::risk_config::RegimeMultipliers；
//! 本檔只是 core 側的硬編碼 fallback，供 stops.rs 獨立使用
//! （core 不能依賴 engine）。

/// Regime-based multipliers for stop-loss, take-profit, and time limits.
/// 基於市場 regime 的止損、止盈、時間限制乘數。
#[derive(Debug, Clone, Copy)]
pub struct RegimeMultipliers {
    pub stop: f64,
    pub tp: f64,
    pub time: f64,
}

/// Return regime-specific multipliers for risk parameters.
/// 回傳特定 regime 的風控參數乘數。
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
