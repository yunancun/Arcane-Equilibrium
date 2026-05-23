//! `FundingHarvestParams` — TOML schema + `StrategyParams` impl + 預設範圍。
//!
//! MODULE_NOTE：
//!   模塊用途：C10 funding harvest 策略的 TOML 載入結構與 Optuna/Agent 可調參數聲明，
//!     對齊 sibling 模組 `bb_breakout/params.rs` 與 `funding_arb` 的 `FundingArbParams`。
//!   主要類函數：FundingHarvestParams、StrategyParams::param_ranges / validate。
//!   依賴：serde、super::ParamRange + StrategyParams trait（透過 `crate::strategies`）。
//!   硬邊界：
//!     - `position_cap_usd` Stage 1 Demo 上限 100 USD（absolute），validate 強制 ≤ 100。
//!     - `funding_exit_annualized < funding_threshold_annualized` 才能避免進出場 same-tick 抖動。
//!     - `allowed_symbols` Stage 1 只允 `BTCUSDT`；Stage 2+ 才擴 ETHUSDT，validate 防止越級。
//!     - `active` 預設 false：Stage 0R replay preflight PASS + operator IPC 顯式 true 才啟。

use serde::{Deserialize, Serialize};

use crate::strategies::params::{ParamRange, StrategyParams};

// ──────────────────────────────────────────────────────────────────────────
// 預設常量：與 PA dispatch packet §2.5 / §5.1 對齊
// （`pub` 是 mod.rs 解構初始化需要）
// ──────────────────────────────────────────────────────────────────────────

/// 入場 annualized funding rate 下界：5% APR（即 8h funding ≈ 0.00457 bps）。
pub const DEFAULT_FUNDING_THRESHOLD_ANNUALIZED: f64 = 0.05;

/// 平倉 annualized funding rate 下界：2% APR；hysteresis 避免進出場抖動。
pub const DEFAULT_FUNDING_EXIT_ANNUALIZED: f64 = 0.02;

/// 出場 basis 上限百分比；入場用 max × entry_basis_ratio 較嚴格門。
pub const DEFAULT_MAX_BASIS_PCT: f64 = 0.5;

/// 入場 basis 收緊係數：0.5% × 0.8 = 0.4% 入場門。
pub const DEFAULT_ENTRY_BASIS_RATIO: f64 = 0.8;

/// 最大持倉時間：72h；超過強制平 perp + 同步 synthetic spot。
pub const DEFAULT_MAX_HOLD_MS: u64 = 72 * 3_600_000;

/// 雙腿往返總成本（bps）：perp 11 + spot 20 + 滑點 3 + basis drift 3。
pub const DEFAULT_TOTAL_COST_BPS: f64 = 37.0;

/// 攤銷分母：3 個 8h funding window；24h 內預期累積 funding payment 攤平 cost。
pub const DEFAULT_EXPECTED_PERIODS: f64 = 3.0;

/// 持倉中 2h tick 一次檢查 delta drift / 是否需要 synthetic spot rebalance。
pub const DEFAULT_REBALANCE_CHECK_MS: u64 = 2 * 3_600_000;

/// delta 漂移觸發 rebalance 的閾值（spot vs perp notional 偏離 / spot）。
pub const DEFAULT_DELTA_DRIFT_THRESHOLD: f64 = 0.02;

/// Stage 1 Demo 單筆絕對 USD 上限；validate 強制 ≤ 100。
pub const DEFAULT_POSITION_CAP_USD: f64 = 100.0;

/// 預設 cooldown：1h（per FundingArb 範式）。
pub const DEFAULT_COOLDOWN_MS: u64 = 3_600_000;

// ──────────────────────────────────────────────────────────────────────────
// FundingHarvestParams（TOML schema + Optuna search 表面）
// ──────────────────────────────────────────────────────────────────────────

/// C10 funding harvest 策略 TOML / IPC schema。
///
/// 透過 `StrategyParamsConfig.funding_harvest` 接線到 `strategy_params_*.toml`
/// `[funding_harvest]` block。三環境（live / demo / paper）TOML 故意獨立
/// （per memory `feedback_env_config_independence`）：
///   - demo：Stage 0R PASS 後可改 `active=true`
///   - live：永遠 `active=false`，待 Sprint 5+ Stage 4 cascade
///   - paper：恒 `active=false`（AMD-2026-05-15-01 §2.2 paper 不再做 alpha 樣本）
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct FundingHarvestParams {
    /// 啟用開關；fail-closed 默認 false。
    pub active: bool,

    /// cooldown 間隔（同 funding_arb 範式，rollback 用 `prev_last_trade_ms`）。
    pub cooldown_ms: u64,

    /// Stage 1 Demo 限定 BTCUSDT；Stage 2+ 才擴 ETHUSDT。
    pub allowed_symbols: Vec<String>,

    /// 入場 annualized funding（>5% APR）。
    pub funding_threshold_annualized: f64,

    /// 平倉 annualized funding（<2% APR）；hysteresis 防 same-tick 抖。
    pub funding_exit_annualized: f64,

    /// 出場 basis 上限；入場 = max × entry_basis_ratio。
    pub max_basis_pct: f64,

    /// 入場 basis 收緊係數（默認 0.8）。
    pub entry_basis_ratio: f64,

    /// 最大持倉時間（毫秒）；超過強制平倉。
    pub max_hold_ms: u64,

    /// 雙腿往返成本（bps）；用於 amortized edge gate。
    pub total_cost_bps: f64,

    /// 成本攤銷分母（funding 周期數）。
    pub expected_periods: f64,

    /// 持倉中檢查 delta drift 的 tick 間隔（毫秒）。
    pub rebalance_check_ms: u64,

    /// delta 漂移閾值（spot_notional vs perp_notional 偏離 / spot_notional）。
    pub delta_drift_threshold: f64,

    /// Stage 1 hard cap = 100 USD absolute；validate 強制 ≤ 100。
    pub position_cap_usd: f64,
}

impl Default for FundingHarvestParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: DEFAULT_COOLDOWN_MS,
            allowed_symbols: vec!["BTCUSDT".to_string()],
            funding_threshold_annualized: DEFAULT_FUNDING_THRESHOLD_ANNUALIZED,
            funding_exit_annualized: DEFAULT_FUNDING_EXIT_ANNUALIZED,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
            rebalance_check_ms: DEFAULT_REBALANCE_CHECK_MS,
            delta_drift_threshold: DEFAULT_DELTA_DRIFT_THRESHOLD,
            position_cap_usd: DEFAULT_POSITION_CAP_USD,
        }
    }
}

impl StrategyParams for FundingHarvestParams {
    /// Optuna / Agent 可調參數範圍宣告。`active` / `allowed_symbols` 為控制
    /// 表面，不入 search space（同 FundingArb 範式）。
    fn param_ranges() -> Vec<ParamRange> {
        vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 60_000.0,
                max: 24.0 * 3_600_000.0,
                step: Some(60_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "funding_threshold_annualized".into(),
                min: 0.01,
                max: 0.5,
                step: Some(0.005),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "funding_exit_annualized".into(),
                min: 0.005,
                max: 0.05,
                step: Some(0.005),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "max_basis_pct".into(),
                min: 0.1,
                max: 2.0,
                step: Some(0.05),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "entry_basis_ratio".into(),
                min: 0.5,
                max: 1.0,
                step: Some(0.05),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "max_hold_ms".into(),
                min: 3_600_000.0,
                max: 30.0 * 24.0 * 3_600_000.0,
                step: Some(3_600_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "total_cost_bps".into(),
                min: 10.0,
                max: 200.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "expected_periods".into(),
                min: 0.5,
                max: 30.0,
                step: Some(0.5),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "rebalance_check_ms".into(),
                min: 600_000.0,
                max: 14_400_000.0,
                step: Some(600_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "delta_drift_threshold".into(),
                min: 0.005,
                max: 0.10,
                step: Some(0.005),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "position_cap_usd".into(),
                min: 10.0,
                max: 1000.0,
                step: Some(10.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    /// 全範圍校驗 + 業務不變量校驗。
    /// 為什麼：TOML 載入 / IPC patch 路徑必須在 strategy 接收前 fail-closed，
    /// 防止 NaN / Inf / Stage 1 cap 越界等運行時災難。
    fn validate(&self) -> Result<(), String> {
        if !(0.01..=0.5).contains(&self.funding_threshold_annualized) {
            return Err(format!(
                "funding_threshold_annualized={} must be in [0.01, 0.5]",
                self.funding_threshold_annualized
            ));
        }
        if !(0.005..=0.05).contains(&self.funding_exit_annualized) {
            return Err(format!(
                "funding_exit_annualized={} must be in [0.005, 0.05]",
                self.funding_exit_annualized
            ));
        }
        // Hysteresis：exit < threshold 才能避免進出場同 tick 翻轉。
        if self.funding_exit_annualized >= self.funding_threshold_annualized {
            return Err(format!(
                "funding_exit_annualized ({}) must be < funding_threshold_annualized ({})",
                self.funding_exit_annualized, self.funding_threshold_annualized
            ));
        }
        if !(0.1..=2.0).contains(&self.max_basis_pct) {
            return Err(format!(
                "max_basis_pct={} must be in [0.1, 2.0]",
                self.max_basis_pct
            ));
        }
        if !(0.5..=1.0).contains(&self.entry_basis_ratio) {
            return Err(format!(
                "entry_basis_ratio={} must be in [0.5, 1.0]",
                self.entry_basis_ratio
            ));
        }
        if self.max_hold_ms < 3_600_000 || self.max_hold_ms > 30 * 24 * 3_600_000 {
            return Err(format!(
                "max_hold_ms={} must be in [1h, 30d]",
                self.max_hold_ms
            ));
        }
        if !(10.0..=200.0).contains(&self.total_cost_bps) {
            return Err(format!(
                "total_cost_bps={} must be in [10, 200]",
                self.total_cost_bps
            ));
        }
        if !(0.5..=30.0).contains(&self.expected_periods) {
            return Err(format!(
                "expected_periods={} must be in [0.5, 30]",
                self.expected_periods
            ));
        }
        if self.rebalance_check_ms < 600_000 || self.rebalance_check_ms > 14_400_000 {
            return Err(format!(
                "rebalance_check_ms={} must be in [10min, 4h]",
                self.rebalance_check_ms
            ));
        }
        if !(0.005..=0.10).contains(&self.delta_drift_threshold) {
            return Err(format!(
                "delta_drift_threshold={} must be in [0.005, 0.10]",
                self.delta_drift_threshold
            ));
        }
        // Stage 1 Demo hard ceiling：>$100 直接拒。
        // 為什麼：AMD-2026-05-15-01 §4.1 + FA §6 Stage 1 Demo absolute cap；
        // 任何 IPC 試圖 patch 到 >100 必 fail-closed。
        if !self.position_cap_usd.is_finite() || self.position_cap_usd <= 0.0 {
            return Err(format!(
                "position_cap_usd={} must be positive and finite",
                self.position_cap_usd
            ));
        }
        if self.position_cap_usd > 100.0 {
            return Err(format!(
                "Stage 1 Demo position_cap_usd hard ceiling = 100; got {}",
                self.position_cap_usd
            ));
        }
        if self.cooldown_ms < 60_000 || self.cooldown_ms > 24 * 3_600_000 {
            return Err(format!(
                "cooldown_ms={} must be in [60s, 24h]",
                self.cooldown_ms
            ));
        }
        // allowed_symbols Stage 1 限定（防 TOML 直接擴 ETH/SOL bypass 設計）。
        if self.allowed_symbols.is_empty() {
            return Err("allowed_symbols must not be empty".into());
        }
        for sym in &self.allowed_symbols {
            if sym != "BTCUSDT" && sym != "ETHUSDT" {
                return Err(format!(
                    "Stage 1-2 only allows BTCUSDT (Stage 2 may add ETHUSDT); got {sym}"
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
        let p = FundingHarvestParams::default();
        assert!(p.validate().is_ok(), "default params must pass validate");
        assert!(!p.active, "default active must be false (fail-closed)");
        assert_eq!(p.allowed_symbols, vec!["BTCUSDT".to_string()]);
    }

    #[test]
    fn rejects_position_cap_above_100() {
        let p = FundingHarvestParams {
            position_cap_usd: 101.0,
            ..Default::default()
        };
        let err = p.validate().unwrap_err();
        assert!(err.contains("hard ceiling"), "err: {err}");
    }

    #[test]
    fn rejects_zero_or_negative_position_cap() {
        let p = FundingHarvestParams {
            position_cap_usd: 0.0,
            ..Default::default()
        };
        assert!(p.validate().is_err());

        let p2 = FundingHarvestParams {
            position_cap_usd: -1.0,
            ..Default::default()
        };
        assert!(p2.validate().is_err());
    }

    #[test]
    fn rejects_exit_geq_threshold() {
        let p = FundingHarvestParams {
            funding_threshold_annualized: 0.05,
            funding_exit_annualized: 0.05,
            ..Default::default()
        };
        let err = p.validate().unwrap_err();
        assert!(err.contains("funding_exit_annualized"), "err: {err}");
    }

    #[test]
    fn rejects_non_btcusdt_ethusdt() {
        let p = FundingHarvestParams {
            allowed_symbols: vec!["SOLUSDT".to_string()],
            ..Default::default()
        };
        let err = p.validate().unwrap_err();
        assert!(err.contains("BTCUSDT"), "err: {err}");
    }

    #[test]
    fn rejects_empty_allowed_symbols() {
        let p = FundingHarvestParams {
            allowed_symbols: vec![],
            ..Default::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn param_ranges_well_formed() {
        let ranges = FundingHarvestParams::param_ranges();
        let names: std::collections::HashSet<_> =
            ranges.iter().map(|r| r.name.as_str()).collect();
        for required in [
            "cooldown_ms",
            "funding_threshold_annualized",
            "funding_exit_annualized",
            "max_basis_pct",
            "entry_basis_ratio",
            "max_hold_ms",
            "total_cost_bps",
            "expected_periods",
            "rebalance_check_ms",
            "delta_drift_threshold",
            "position_cap_usd",
        ] {
            assert!(names.contains(required), "missing param: {required}");
        }
        // active / allowed_symbols 為控制表面，不入 Optuna search。
        assert!(!names.contains("active"));
        assert!(!names.contains("allowed_symbols"));
    }
}
