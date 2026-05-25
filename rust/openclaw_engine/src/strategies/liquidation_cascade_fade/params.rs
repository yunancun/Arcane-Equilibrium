//! `LiquidationCascadeFadeParams` — TOML schema + `StrategyParams` impl + 預設範圍。
//!
//! MODULE_NOTE：
//!   模塊用途：Sprint 2 Alpha Tournament Candidate #4 — microstructure liquidation
//!     cascade mean-revert fade 策略的 TOML 載入結構與 Optuna/Agent 可調參數聲明。
//!   主要類函數：LiquidationCascadeFadeParams、StrategyParams::param_ranges / validate。
//!   依賴：serde、super::ParamRange + StrategyParams trait（透過 `crate::strategies`）。
//!   硬邊界：
//!     - per-symbol threshold：BTC $500k / ETH $300k 5m notional；non-cohort fallback $100k。
//!     - `allowed_symbols` Stage 1 限定 BTCUSDT / ETHUSDT；Sprint 3+ 才擴 SOL/BNB。
//!     - `take_profit_pct` 1.5%；`reverse_cascade_ratio` 1.5x（出場條件 spec §1.2）。
//!     - `active` 預設 false：5-gate auto path inheritance + operator IPC 顯式 true 才啟。

use serde::{Deserialize, Serialize};

use crate::strategies::params::{ParamRange, StrategyParams};

// ──────────────────────────────────────────────────────────────────────────
// 預設常量：與 W1-A spec §3.1 / Step X PM closure 對齊
// ──────────────────────────────────────────────────────────────────────────

/// non-cohort fallback threshold (USD)；Stage 1 只 cohort 內走 per-symbol。
pub const DEFAULT_THRESHOLD_USD: f64 = 100_000.0;

/// BTCUSDT 5m notional threshold (USD)；per spec §1.3 percentile 80%。
pub const DEFAULT_BTC_THRESHOLD_USD: f64 = 500_000.0;

/// ETHUSDT 5m notional threshold (USD)。
pub const DEFAULT_ETH_THRESHOLD_USD: f64 = 300_000.0;

/// 5m window 內最小事件數；防 single-large-event 假訊號（spec §1.1 條件 3）。
pub const DEFAULT_MIN_EVENTS: u32 = 3;

/// 最大持倉時間：60min（spec §1.2 條件 1 time-stop）。
pub const DEFAULT_MAX_HOLD_MS: u64 = 60 * 60_000;

/// Take profit 1.5%（spec §1.2 條件 2）。
pub const DEFAULT_TAKE_PROFIT_PCT: f64 = 1.5;

/// Reverse cascade ratio：current_dominant / entry_notional > 1.5x → 立即出場
/// （spec §1.2 條件 4）。
pub const DEFAULT_REVERSE_CASCADE_RATIO: f64 = 1.5;

/// 預設 cooldown：30min（防同 cascade 重入；spec §1.1 條件 5）。
pub const DEFAULT_COOLDOWN_MS: u64 = 30 * 60_000;

// ──────────────────────────────────────────────────────────────────────────
// LiquidationCascadeFadeParams（TOML schema + Optuna search 表面）
// ──────────────────────────────────────────────────────────────────────────

/// Sprint 2 Alpha Tournament Candidate #4 — liquidation_cascade_fade 策略
/// TOML / IPC schema。
///
/// 透過 `StrategyParamsConfig.liquidation_cascade_fade` 接線到
/// `strategy_params_*.toml` `[liquidation_cascade_fade]` block。三環境
/// （live / demo / paper）TOML 故意獨立（per memory `feedback_env_config_independence`）。
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct LiquidationCascadeFadeParams {
    /// 啟用開關；fail-closed 默認 false。
    pub active: bool,

    /// cooldown 間隔（per symbol）。
    pub cooldown_ms: u64,

    /// Stage 1 Demo 限定 BTCUSDT / ETHUSDT。
    pub allowed_symbols: Vec<String>,

    /// non-cohort fallback threshold；理論不應 trigger（cohort 在 BTC/ETH only）。
    pub default_threshold_usd: f64,

    /// BTCUSDT 5m notional threshold (USD)。
    pub btc_threshold_usd: f64,

    /// ETHUSDT 5m notional threshold (USD)。
    pub eth_threshold_usd: f64,

    /// 5m window 內最小事件數（spec §1.1 條件 3）。
    pub min_events: u32,

    /// 最大持倉時間（毫秒）；60min hard time-stop。
    pub max_hold_ms: u64,

    /// Take profit 百分比（spec §1.2 條件 2）。
    pub take_profit_pct: f64,

    /// Reverse cascade 觸發 ratio（spec §1.2 條件 4）。
    pub reverse_cascade_ratio: f64,
}

impl Default for LiquidationCascadeFadeParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: DEFAULT_COOLDOWN_MS,
            allowed_symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
            default_threshold_usd: DEFAULT_THRESHOLD_USD,
            btc_threshold_usd: DEFAULT_BTC_THRESHOLD_USD,
            eth_threshold_usd: DEFAULT_ETH_THRESHOLD_USD,
            min_events: DEFAULT_MIN_EVENTS,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            take_profit_pct: DEFAULT_TAKE_PROFIT_PCT,
            reverse_cascade_ratio: DEFAULT_REVERSE_CASCADE_RATIO,
        }
    }
}

impl StrategyParams for LiquidationCascadeFadeParams {
    /// Optuna / Agent 可調參數範圍宣告。
    /// `active` / `allowed_symbols` 為控制表面，不入 search space。
    fn param_ranges() -> Vec<ParamRange> {
        vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 60_000.0,
                max: 4.0 * 3_600_000.0,
                step: Some(60_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "default_threshold_usd".into(),
                min: 50_000.0,
                max: 2_000_000.0,
                step: Some(10_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "btc_threshold_usd".into(),
                min: 100_000.0,
                max: 5_000_000.0,
                step: Some(50_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "eth_threshold_usd".into(),
                min: 100_000.0,
                max: 3_000_000.0,
                step: Some(50_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "min_events".into(),
                min: 2.0,
                max: 50.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "max_hold_ms".into(),
                min: 600_000.0,
                max: 6.0 * 3_600_000.0,
                step: Some(300_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "take_profit_pct".into(),
                min: 0.3,
                max: 5.0,
                step: Some(0.1),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "reverse_cascade_ratio".into(),
                min: 1.1,
                max: 5.0,
                step: Some(0.1),
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    /// 全範圍校驗 + 業務不變量校驗。
    /// 為什麼：TOML 載入 / IPC patch 路徑必須在 strategy 接收前 fail-closed，
    /// 防止 NaN / Inf / Stage 1 cohort 越界。
    fn validate(&self) -> Result<(), String> {
        if !self.default_threshold_usd.is_finite()
            || !(50_000.0..=2_000_000.0).contains(&self.default_threshold_usd)
        {
            return Err(format!(
                "default_threshold_usd={} must be in [50k, 2M]",
                self.default_threshold_usd
            ));
        }
        if !self.btc_threshold_usd.is_finite()
            || !(100_000.0..=5_000_000.0).contains(&self.btc_threshold_usd)
        {
            return Err(format!(
                "btc_threshold_usd={} must be in [100k, 5M]",
                self.btc_threshold_usd
            ));
        }
        if !self.eth_threshold_usd.is_finite()
            || !(100_000.0..=3_000_000.0).contains(&self.eth_threshold_usd)
        {
            return Err(format!(
                "eth_threshold_usd={} must be in [100k, 3M]",
                self.eth_threshold_usd
            ));
        }
        if !(2..=50).contains(&self.min_events) {
            return Err(format!(
                "min_events={} must be in [2, 50]",
                self.min_events
            ));
        }
        if self.max_hold_ms < 600_000 || self.max_hold_ms > 6 * 3_600_000 {
            return Err(format!(
                "max_hold_ms={} must be in [10min, 6h]",
                self.max_hold_ms
            ));
        }
        if !self.take_profit_pct.is_finite() || !(0.3..=5.0).contains(&self.take_profit_pct) {
            return Err(format!(
                "take_profit_pct={} must be in [0.3, 5.0]",
                self.take_profit_pct
            ));
        }
        if !self.reverse_cascade_ratio.is_finite()
            || !(1.1..=5.0).contains(&self.reverse_cascade_ratio)
        {
            return Err(format!(
                "reverse_cascade_ratio={} must be in [1.1, 5.0]",
                self.reverse_cascade_ratio
            ));
        }
        if self.cooldown_ms < 60_000 || self.cooldown_ms > 4 * 3_600_000 {
            return Err(format!(
                "cooldown_ms={} must be in [60s, 4h]",
                self.cooldown_ms
            ));
        }
        // allowed_symbols Stage 1 限定 BTCUSDT / ETHUSDT。
        if self.allowed_symbols.is_empty() {
            return Err("allowed_symbols must not be empty".into());
        }
        for sym in &self.allowed_symbols {
            if sym != "BTCUSDT" && sym != "ETHUSDT" {
                return Err(format!(
                    "Stage 1 only allows BTCUSDT / ETHUSDT; got {sym}"
                ));
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn default_params_validate() {
        let p = LiquidationCascadeFadeParams::default();
        assert!(p.validate().is_ok());
        assert!(!p.active);
        assert_eq!(p.allowed_symbols.len(), 2);
        assert!((p.btc_threshold_usd - 500_000.0).abs() < 1e-6);
        assert!((p.eth_threshold_usd - 300_000.0).abs() < 1e-6);
        assert_eq!(p.min_events, 3);
        // spec §1.2 take_profit_pct 1.5。
        assert!((p.take_profit_pct - 1.5).abs() < 1e-9);
        // spec §1.2 reverse_cascade_ratio 1.5x。
        assert!((p.reverse_cascade_ratio - 1.5).abs() < 1e-9);
    }

    #[test]
    fn rejects_non_cohort_symbol() {
        let p = LiquidationCascadeFadeParams {
            allowed_symbols: vec!["SOLUSDT".to_string()],
            ..Default::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn accepts_btc_and_eth_only() {
        let p = LiquidationCascadeFadeParams {
            allowed_symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
            ..Default::default()
        };
        assert!(p.validate().is_ok());
    }

    #[test]
    fn rejects_min_events_below_2() {
        let p = LiquidationCascadeFadeParams {
            min_events: 1,
            ..Default::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn rejects_take_profit_out_of_range() {
        let p = LiquidationCascadeFadeParams {
            take_profit_pct: 0.0,
            ..Default::default()
        };
        assert!(p.validate().is_err());

        let p2 = LiquidationCascadeFadeParams {
            take_profit_pct: 10.0,
            ..Default::default()
        };
        assert!(p2.validate().is_err());
    }

    #[test]
    fn rejects_reverse_cascade_below_1_1() {
        // 1.0 = 立即觸發（無 buffer）；必 reject。
        let p = LiquidationCascadeFadeParams {
            reverse_cascade_ratio: 1.0,
            ..Default::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn rejects_btc_threshold_too_low() {
        let p = LiquidationCascadeFadeParams {
            btc_threshold_usd: 50_000.0, // below 100k floor
            ..Default::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn param_ranges_well_formed() {
        let ranges = LiquidationCascadeFadeParams::param_ranges();
        let names: std::collections::HashSet<_> =
            ranges.iter().map(|r| r.name.as_str()).collect();
        for required in [
            "cooldown_ms",
            "default_threshold_usd",
            "btc_threshold_usd",
            "eth_threshold_usd",
            "min_events",
            "max_hold_ms",
            "take_profit_pct",
            "reverse_cascade_ratio",
        ] {
            assert!(names.contains(required), "missing param: {required}");
        }
        assert!(!names.contains("active"));
        assert!(!names.contains("allowed_symbols"));
    }
}
