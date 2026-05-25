//! `FundingShortV2Params` — TOML schema + `StrategyParams` impl + 預設範圍。
//!
//! MODULE_NOTE：
//!   模塊用途：Sprint 2 Alpha Tournament Candidate #1 — funding rate >30%
//!     annualized 短倉 directional capture 策略的 TOML 載入結構與 Optuna/Agent
//!     可調參數聲明，對齊 sibling `funding_harvest/params.rs` 範式。
//!   主要類函數：FundingShortV2Params、StrategyParams::param_ranges / validate。
//!   依賴：serde、super::ParamRange + StrategyParams trait（透過 `crate::strategies`）。
//!   硬邊界：
//!     - 不變量（dispatch §0 #2A）：與 funding_arb V2 (ADR-0018 dormant) 區別 = short-only
//!       + 30% annualized gate + 24h hold；不繞 dormant 結論。
//!     - `funding_threshold_annualized` 預設 0.30 (30%)；validate floor 0.20 防 IPC 誤
//!       patch 到 break-even 以下（spec §9 §2）。
//!     - `funding_exit_annualized` < `funding_threshold_annualized` (hysteresis)。
//!     - `allowed_symbols` Stage 1 限定 BTCUSDT / ETHUSDT；validate 防越級。
//!     - `active` 預設 false：5-gate auto path inheritance + operator IPC 顯式 true 才啟。

use serde::{Deserialize, Serialize};

use crate::strategies::params::{ParamRange, StrategyParams};

// ──────────────────────────────────────────────────────────────────────────
// 預設常量：與 W1-A spec §3.1 / Step X PM closure 對齊
// ──────────────────────────────────────────────────────────────────────────

/// 入場 annualized funding rate 下界：30%（QC 量化分析 break-even threshold）。
pub const DEFAULT_FUNDING_THRESHOLD_ANNUALIZED: f64 = 0.30;

/// 平倉 annualized funding rate 下界：5%（hysteresis 防進出場抖動）。
pub const DEFAULT_FUNDING_EXIT_ANNUALIZED: f64 = 0.05;

/// 出場 basis 上限百分比；入場用 max × entry_basis_ratio 較嚴格門。
pub const DEFAULT_MAX_BASIS_PCT: f64 = 0.5;

/// 入場 basis 收緊係數：0.5% × 0.6 = 0.3% 入場門。
pub const DEFAULT_ENTRY_BASIS_RATIO: f64 = 0.6;

/// 最大持倉時間：24h（3 funding cycle 硬上限）。
pub const DEFAULT_MAX_HOLD_MS: u64 = 24 * 3_600_000;

/// 單腿 perp roundtrip 成本（bps）：entry maker 1 + exit taker 5.5 + slip 3 +
/// funding settlement variability 12.5 = 22.0；無 spot 腿。
pub const DEFAULT_TOTAL_COST_BPS: f64 = 22.0;

/// 攤銷分母：1.5 個 8h funding window（1-2 cycle median hold，QC 量化分析）。
pub const DEFAULT_EXPECTED_PERIODS: f64 = 1.5;

/// 預設 cooldown：8h（1 funding cycle，避同 cycle 重入）。
pub const DEFAULT_COOLDOWN_MS: u64 = 8 * 3_600_000;

/// Floor on funding_threshold_annualized to guard against IPC tunable patches
/// dropping below break-even threshold (per spec §9 #2 對抗式 review focus)。
/// 不變量：IPC patch funding_threshold < 0.20 (20% annualized) 必 fail-closed reject。
pub const FUNDING_THRESHOLD_FLOOR: f64 = 0.20;

// ──────────────────────────────────────────────────────────────────────────
// FundingShortV2Params（TOML schema + Optuna search 表面）
// ──────────────────────────────────────────────────────────────────────────

/// Sprint 2 Alpha Tournament Candidate #1 — funding_short_v2 策略 TOML / IPC schema。
///
/// 透過 `StrategyParamsConfig.funding_short_v2` 接線到 `strategy_params_*.toml`
/// `[funding_short_v2]` block。三環境（live / demo / paper）TOML 故意獨立
/// （per memory `feedback_env_config_independence`）：
///   - demo：W2-B IMPL 階段 `active=false`；W3-A operator IPC 顯式 true 才啟
///   - live：永遠 `active=false`，待 P0-EDGE-1 closure + 5-gate green
///   - paper：恒 `active=false`（AMD-2026-05-15-01 §2.2 paper 不再做 alpha 樣本）
#[derive(Debug, Clone, Deserialize, Serialize)]
#[serde(default)]
pub struct FundingShortV2Params {
    /// 啟用開關；fail-closed 默認 false。
    pub active: bool,

    /// cooldown 間隔（每 symbol；防同 funding cycle 重入）。
    pub cooldown_ms: u64,

    /// Stage 1 Demo 限定 BTCUSDT / ETHUSDT。
    pub allowed_symbols: Vec<String>,

    /// 入場 annualized funding 下界（30%）；hard gate。
    pub funding_threshold_annualized: f64,

    /// 平倉 annualized funding 下界（5%）；hysteresis。
    pub funding_exit_annualized: f64,

    /// 出場 basis 上限；入場 = max × entry_basis_ratio。
    pub max_basis_pct: f64,

    /// 入場 basis 收緊係數（默認 0.6）。
    pub entry_basis_ratio: f64,

    /// 最大持倉時間（毫秒）；24h 硬上限。
    pub max_hold_ms: u64,

    /// Perp 單腿往返成本（bps）；用於 amortized edge gate。
    pub total_cost_bps: f64,

    /// 成本攤銷分母（funding 周期數）。
    pub expected_periods: f64,
}

impl Default for FundingShortV2Params {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: DEFAULT_COOLDOWN_MS,
            allowed_symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
            funding_threshold_annualized: DEFAULT_FUNDING_THRESHOLD_ANNUALIZED,
            funding_exit_annualized: DEFAULT_FUNDING_EXIT_ANNUALIZED,
            max_basis_pct: DEFAULT_MAX_BASIS_PCT,
            entry_basis_ratio: DEFAULT_ENTRY_BASIS_RATIO,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            total_cost_bps: DEFAULT_TOTAL_COST_BPS,
            expected_periods: DEFAULT_EXPECTED_PERIODS,
        }
    }
}

impl StrategyParams for FundingShortV2Params {
    /// Optuna / Agent 可調參數範圍宣告。
    /// `active` / `allowed_symbols` 為控制表面，不入 search space（同 FundingArb 範式）。
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
                // floor 0.20 防 IPC 誤 patch 到 break-even 以下（spec §9 #2 對抗式 review）。
                min: FUNDING_THRESHOLD_FLOOR,
                max: 1.0,
                step: Some(0.01),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "funding_exit_annualized".into(),
                min: 0.01,
                max: 0.20,
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
                min: 0.3,
                max: 1.0,
                step: Some(0.05),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "max_hold_ms".into(),
                min: 3_600_000.0,
                max: 7.0 * 24.0 * 3_600_000.0,
                step: Some(3_600_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "total_cost_bps".into(),
                min: 10.0,
                max: 100.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "expected_periods".into(),
                min: 0.5,
                max: 6.0,
                step: Some(0.5),
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    /// 全範圍校驗 + 業務不變量校驗。
    /// 為什麼：TOML 載入 / IPC patch 路徑必須在 strategy 接收前 fail-closed，
    /// 防止 NaN / Inf / Stage 1 cohort 越界 / break-even threshold 漂移。
    fn validate(&self) -> Result<(), String> {
        // funding_threshold floor 0.20 enforced（spec §9 #2 對抗式 review focus）。
        if !self.funding_threshold_annualized.is_finite()
            || self.funding_threshold_annualized < FUNDING_THRESHOLD_FLOOR
            || self.funding_threshold_annualized > 1.0
        {
            return Err(format!(
                "funding_threshold_annualized={} must be in [{}, 1.0] (floor protects break-even)",
                self.funding_threshold_annualized, FUNDING_THRESHOLD_FLOOR
            ));
        }
        if !self.funding_exit_annualized.is_finite()
            || !(0.01..=0.20).contains(&self.funding_exit_annualized)
        {
            return Err(format!(
                "funding_exit_annualized={} must be in [0.01, 0.20]",
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
        if !self.max_basis_pct.is_finite() || !(0.1..=2.0).contains(&self.max_basis_pct) {
            return Err(format!(
                "max_basis_pct={} must be in [0.1, 2.0]",
                self.max_basis_pct
            ));
        }
        if !self.entry_basis_ratio.is_finite() || !(0.3..=1.0).contains(&self.entry_basis_ratio) {
            return Err(format!(
                "entry_basis_ratio={} must be in [0.3, 1.0]",
                self.entry_basis_ratio
            ));
        }
        if self.max_hold_ms < 3_600_000 || self.max_hold_ms > 7 * 24 * 3_600_000 {
            return Err(format!(
                "max_hold_ms={} must be in [1h, 7d]",
                self.max_hold_ms
            ));
        }
        if !self.total_cost_bps.is_finite() || !(10.0..=100.0).contains(&self.total_cost_bps) {
            return Err(format!(
                "total_cost_bps={} must be in [10, 100]",
                self.total_cost_bps
            ));
        }
        if !self.expected_periods.is_finite() || !(0.5..=6.0).contains(&self.expected_periods) {
            return Err(format!(
                "expected_periods={} must be in [0.5, 6.0]",
                self.expected_periods
            ));
        }
        if self.cooldown_ms < 60_000 || self.cooldown_ms > 24 * 3_600_000 {
            return Err(format!(
                "cooldown_ms={} must be in [60s, 24h]",
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
        let p = FundingShortV2Params::default();
        assert!(p.validate().is_ok(), "default params must pass validate");
        assert!(!p.active, "default active must be false (fail-closed)");
        assert_eq!(
            p.allowed_symbols,
            vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()]
        );
        // spec §0 + §1.3 hard invariant：default funding_threshold = 0.30 (30%)。
        assert!((p.funding_threshold_annualized - 0.30).abs() < 1e-9);
        // spec §1.3 hard invariant：default expected_periods = 1.5。
        assert!((p.expected_periods - 1.5).abs() < 1e-9);
    }

    #[test]
    fn rejects_funding_threshold_below_floor() {
        // 0.15 < FUNDING_THRESHOLD_FLOOR=0.20 → reject。
        // 為什麼這個 test 重要：spec §9 #2 對抗式 review focus；IPC 不可降至 break-even 以下。
        let p = FundingShortV2Params {
            funding_threshold_annualized: 0.15,
            ..Default::default()
        };
        let err = p.validate().unwrap_err();
        assert!(err.contains("funding_threshold_annualized"), "err: {err}");
        assert!(err.contains("floor"), "err must mention floor: {err}");
    }

    #[test]
    fn accepts_funding_threshold_at_floor() {
        let p = FundingShortV2Params {
            funding_threshold_annualized: FUNDING_THRESHOLD_FLOOR,
            funding_exit_annualized: 0.05,
            ..Default::default()
        };
        assert!(p.validate().is_ok());
    }

    #[test]
    fn rejects_exit_geq_threshold() {
        let p = FundingShortV2Params {
            funding_threshold_annualized: 0.30,
            funding_exit_annualized: 0.30,
            ..Default::default()
        };
        let err = p.validate().unwrap_err();
        assert!(err.contains("funding_exit_annualized"), "err: {err}");
    }

    #[test]
    fn rejects_non_cohort_symbol() {
        let p = FundingShortV2Params {
            allowed_symbols: vec!["SOLUSDT".to_string()],
            ..Default::default()
        };
        let err = p.validate().unwrap_err();
        assert!(err.contains("BTCUSDT"), "err: {err}");
    }

    #[test]
    fn accepts_btc_and_eth_only() {
        let p = FundingShortV2Params {
            allowed_symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
            ..Default::default()
        };
        assert!(p.validate().is_ok());
    }

    #[test]
    fn rejects_empty_allowed_symbols() {
        let p = FundingShortV2Params {
            allowed_symbols: vec![],
            ..Default::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn rejects_max_hold_above_7d() {
        let p = FundingShortV2Params {
            max_hold_ms: 8 * 24 * 3_600_000,
            ..Default::default()
        };
        assert!(p.validate().is_err());
    }

    #[test]
    fn param_ranges_well_formed() {
        let ranges = FundingShortV2Params::param_ranges();
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
        ] {
            assert!(names.contains(required), "missing param: {required}");
        }
        // active / allowed_symbols 為控制表面，不入 Optuna search。
        assert!(!names.contains("active"));
        assert!(!names.contains("allowed_symbols"));
        // funding_threshold_annualized 最小值必 = FUNDING_THRESHOLD_FLOOR。
        let funding_range = ranges
            .iter()
            .find(|r| r.name == "funding_threshold_annualized")
            .expect("funding_threshold_annualized range must exist");
        assert!((funding_range.min - FUNDING_THRESHOLD_FLOOR).abs() < 1e-9);
    }
}
