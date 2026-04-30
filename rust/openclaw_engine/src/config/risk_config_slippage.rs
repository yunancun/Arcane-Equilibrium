//! Slippage and cost-gate weighting config.
//! 滑點與成本門權重配置。

use serde::{Deserialize, Serialize};

/// G7-07 (2026-04-24): Cost-gate slippage assumptions consolidated into a single
/// hot-reloadable struct. Defaults preserve the pre-G7-07 hardcoded values
/// (`SLIPPAGE_TIERS`, `DEFAULT_SLIPPAGE_RATE`, `win_rate.clamp(0.3, 1.0)`,
/// `× 1.3` safety margin) so engine behaviour is bit-identical when this section
/// is absent from `risk_config*.toml`.
///
/// G7-07：成本門滑點假設整合進可熱重載 struct；預設保持 G7-07 前的硬編碼數值
/// （`SLIPPAGE_TIERS` / `DEFAULT_SLIPPAGE_RATE` / 勝率 floor 0.3 / safety
/// multiplier 1.3），TOML 缺此 section 時引擎行為 bit-identical。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlippageConfig {
    /// Default slippage rate (decimal, NOT bps — `0.0005` = 5 bps) used when
    /// `volume_24h <= 0.0` or no tier matches. Validated 0 ≤ rate ≤ 0.01
    /// (1.0 % cap to catch unit confusion).
    /// 默認滑點率（小數而非 bps，`0.0005` = 5 bps）；當 24h 成交量無法判斷
    /// 或無 tier 命中時回退。Validate 限制 [0, 0.01]（1% 上限防單位混淆）。
    #[serde(default = "default_slippage_default_rate")]
    pub default_rate: f64,
    /// Volume-tier table sorted by descending `min_turnover_usd`. Lookup picks
    /// the first row whose `min_turnover_usd <= volume_24h`. Defaults mirror
    /// the pre-G7-07 SLIPPAGE_TIERS exactly. Empty list ⇒ always fall back
    /// to `default_rate`.
    /// 成交量分級表（依 `min_turnover_usd` 降序）。Lookup 選首個
    /// `min_turnover_usd <= volume_24h` 的列；空列表 ⇒ 永用 `default_rate`。
    /// 預設與 G7-07 前 SLIPPAGE_TIERS 完全一致。
    #[serde(default = "default_slippage_tiers")]
    pub tiers: Vec<SlippageTier>,
    /// Lower clamp on `win_rate` when computing the cost-gate threshold.
    /// `threshold_bps = fee_bps / max(floor, win_rate) × safety_multiplier`.
    /// Pre-G7-07 hardcoded `0.3`. Validated 0 < floor < 1.
    /// 成本門 threshold 計算時對 `win_rate` 的下限 clamp。
    /// `threshold_bps = fee_bps / max(floor, win_rate) × safety_multiplier`。
    /// G7-07 前硬編 0.3。Validate 限制 (0, 1)。
    #[serde(default = "default_cost_gate_win_rate_floor")]
    pub cost_gate_win_rate_floor: f64,
    /// Safety multiplier applied to the win-rate-weighted threshold above.
    /// Pre-G7-07 hardcoded `1.3` (= 30 % buffer). Validated 1 ≤ x ≤ 5.
    /// 勝率加權 threshold 的 safety multiplier；G7-07 前硬編 1.3（30% buffer）。
    /// Validate 限制 [1, 5]。
    #[serde(default = "default_cost_gate_safety_multiplier")]
    pub cost_gate_safety_multiplier: f64,
    /// Minimum `n_trades` required for `cost_gate_moderate` (demo path) to BLOCK
    /// on a negative shrunk_bps. Below this threshold the JS estimate is treated
    /// as noise-dominated and the gate switches to exploration mode (allow + log)
    /// so demo can keep accumulating data toward statistically robust estimates.
    /// Live path (`cost_gate_live`) is unaffected — it remains strict per
    /// CLAUDE.md §四 (operator policy: demo loose, live strict).
    /// Default 30 (≈ CLT threshold). Validated 1 ≤ x ≤ 1000.
    /// 拒絕負 shrunk_bps 前要求的最小 n_trades（demo cost_gate_moderate 路徑）。
    /// 低於此值則 JS 估計被視為噪音主導，gate 切換到探索模式（放行+log），
    /// 讓 demo 累積資料以達到統計穩健估計。Live 路徑不受影響，仍保持嚴格
    /// （CLAUDE.md §四 operator 政策：demo 放寬 / live 收緊）。
    /// 預設 30（≈ CLT 門檻）。Validate 限制 [1, 1000]。
    #[serde(default = "default_cost_gate_min_n_trades_for_block")]
    pub cost_gate_min_n_trades_for_block: u64,
}

/// One row of the slippage volume-tier table.
/// 滑點成交量分級表單一條目。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct SlippageTier {
    /// Lower-bound 24h USD turnover for this tier (inclusive).
    /// 本級 24h USD 成交量下限（含）。
    pub min_turnover_usd: f64,
    /// Slippage rate (decimal) applied when `volume_24h >= min_turnover_usd`.
    /// 命中本級時套用的滑點率（小數）。
    pub rate: f64,
}

fn default_slippage_default_rate() -> f64 {
    0.0005 // 5 bps — fallback when volume unavailable
}

fn default_slippage_tiers() -> Vec<SlippageTier> {
    // Mirrors pre-G7-07 SLIPPAGE_TIERS in `intent_processor::mod`.
    // 對齊 G7-07 前 intent_processor::mod 的 SLIPPAGE_TIERS。
    vec![
        SlippageTier {
            min_turnover_usd: 1_000_000_000.0,
            rate: 0.0001, // >$1B: 1 bps (BTC/ETH)
        },
        SlippageTier {
            min_turnover_usd: 100_000_000.0,
            rate: 0.0002, // >$100M: 2 bps
        },
        SlippageTier {
            min_turnover_usd: 10_000_000.0,
            rate: 0.0005, // >$10M: 5 bps
        },
        SlippageTier {
            min_turnover_usd: 1_000_000.0,
            rate: 0.0015, // >$1M: 15 bps
        },
        SlippageTier {
            min_turnover_usd: 0.0,
            rate: 0.0030, // <$1M: 30 bps (illiquid alts)
        },
    ]
}

fn default_cost_gate_win_rate_floor() -> f64 {
    0.3
}

fn default_cost_gate_safety_multiplier() -> f64 {
    1.3
}

fn default_cost_gate_min_n_trades_for_block() -> u64 {
    30
}

impl Default for SlippageConfig {
    fn default() -> Self {
        Self {
            default_rate: default_slippage_default_rate(),
            tiers: default_slippage_tiers(),
            cost_gate_win_rate_floor: default_cost_gate_win_rate_floor(),
            cost_gate_safety_multiplier: default_cost_gate_safety_multiplier(),
            cost_gate_min_n_trades_for_block: default_cost_gate_min_n_trades_for_block(),
        }
    }
}

impl SlippageConfig {
    /// Validate cross-field invariants and ranges.
    /// 驗證跨欄位不變量與範圍。
    pub(crate) fn validate(&self) -> Result<(), String> {
        if !(0.0..=0.01).contains(&self.default_rate) {
            return Err(
                "risk.slippage.default_rate must be in [0, 0.01] (decimal, 1 % cap)".into(),
            );
        }
        if !(0.0..1.0).contains(&self.cost_gate_win_rate_floor) {
            return Err(
                "risk.slippage.cost_gate_win_rate_floor must be in [0, 1) (exclusive upper)".into(),
            );
        }
        if !(1.0..=5.0).contains(&self.cost_gate_safety_multiplier) {
            return Err("risk.slippage.cost_gate_safety_multiplier must be in [1, 5]".into());
        }
        if !(1..=1000).contains(&self.cost_gate_min_n_trades_for_block) {
            return Err(
                "risk.slippage.cost_gate_min_n_trades_for_block must be in [1, 1000]".into(),
            );
        }
        let mut prev_floor: Option<f64> = None;
        for (i, tier) in self.tiers.iter().enumerate() {
            if tier.min_turnover_usd < 0.0 {
                return Err(format!(
                    "risk.slippage.tiers[{}].min_turnover_usd must be >= 0",
                    i
                ));
            }
            if !(0.0..=0.01).contains(&tier.rate) {
                return Err(format!(
                    "risk.slippage.tiers[{}].rate must be in [0, 0.01] (decimal, 1 % cap)",
                    i
                ));
            }
            if let Some(prev) = prev_floor {
                if tier.min_turnover_usd >= prev {
                    return Err(format!(
                        "risk.slippage.tiers must be sorted by descending min_turnover_usd \
                         (row {} = {} not strictly less than previous {})",
                        i, tier.min_turnover_usd, prev
                    ));
                }
            }
            prev_floor = Some(tier.min_turnover_usd);
        }
        Ok(())
    }

    /// Look up the slippage rate for a given 24h USD turnover. Picks the first
    /// tier whose `min_turnover_usd <= volume_24h`; falls back to `default_rate`
    /// when `volume_24h <= 0` or no tier matches.
    /// 給定 24h USD 成交量取滑點率。選首個 `min_turnover_usd <= volume_24h`
    /// 的 tier；`volume_24h <= 0` 或無命中 → fallback `default_rate`。
    pub fn lookup_rate(&self, volume_24h: f64) -> f64 {
        if volume_24h <= 0.0 {
            return self.default_rate;
        }
        for tier in &self.tiers {
            if volume_24h >= tier.min_turnover_usd {
                return tier.rate;
            }
        }
        self.default_rate
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn slippage_config_default_validates() {
        assert!(SlippageConfig::default().validate().is_ok());
    }

    #[test]
    fn slippage_config_default_lookup_matches_pre_g7_07_tiers() {
        let cfg = SlippageConfig::default();
        assert_eq!(cfg.lookup_rate(2_000_000_000.0), 0.0001);
        assert_eq!(cfg.lookup_rate(500_000_000.0), 0.0002);
        assert_eq!(cfg.lookup_rate(50_000_000.0), 0.0005);
        assert_eq!(cfg.lookup_rate(5_000_000.0), 0.0015);
        assert_eq!(cfg.lookup_rate(100_000.0), 0.0030);
        assert_eq!(cfg.lookup_rate(0.0), 0.0005);
        assert_eq!(cfg.lookup_rate(-1.0), 0.0005);
    }

    #[test]
    fn slippage_config_rejects_default_rate_above_cap() {
        let mut cfg = SlippageConfig::default();
        cfg.default_rate = 0.015;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_rejects_win_rate_floor_at_one() {
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_win_rate_floor = 1.0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_rejects_safety_multiplier_below_one() {
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_safety_multiplier = 0.9;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_default_min_n_trades_is_30() {
        assert_eq!(
            SlippageConfig::default().cost_gate_min_n_trades_for_block,
            30
        );
    }

    #[test]
    fn slippage_config_rejects_min_n_trades_zero() {
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_min_n_trades_for_block = 0;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_rejects_min_n_trades_too_high() {
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_min_n_trades_for_block = 5000;
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_accepts_min_n_trades_boundary_values() {
        let mut cfg = SlippageConfig::default();
        cfg.cost_gate_min_n_trades_for_block = 1;
        assert!(cfg.validate().is_ok());
        cfg.cost_gate_min_n_trades_for_block = 1000;
        assert!(cfg.validate().is_ok());
    }

    #[test]
    fn slippage_config_rejects_unsorted_tiers() {
        let cfg = SlippageConfig {
            tiers: vec![
                SlippageTier {
                    min_turnover_usd: 1_000_000.0,
                    rate: 0.0015,
                },
                SlippageTier {
                    min_turnover_usd: 10_000_000.0,
                    rate: 0.0005,
                },
            ],
            ..SlippageConfig::default()
        };
        assert!(cfg.validate().is_err());
    }

    #[test]
    fn slippage_config_custom_tiers_lookup() {
        let cfg = SlippageConfig {
            default_rate: 0.001,
            tiers: vec![SlippageTier {
                min_turnover_usd: 500_000.0,
                rate: 0.0008,
            }],
            cost_gate_win_rate_floor: 0.4,
            cost_gate_safety_multiplier: 1.5,
            cost_gate_min_n_trades_for_block: 30,
        };
        assert!(cfg.validate().is_ok());
        assert_eq!(cfg.lookup_rate(1_000_000.0), 0.0008);
        assert_eq!(cfg.lookup_rate(100_000.0), 0.001);
        assert_eq!(cfg.lookup_rate(0.0), 0.001);
    }

    #[test]
    fn slippage_config_empty_tiers_uses_default_rate() {
        let cfg = SlippageConfig {
            tiers: vec![],
            ..SlippageConfig::default()
        };
        assert!(cfg.validate().is_ok());
        assert_eq!(cfg.lookup_rate(1_000_000_000.0), cfg.default_rate);
        assert_eq!(cfg.lookup_rate(1.0), cfg.default_rate);
    }

    #[test]
    fn slippage_config_toml_roundtrip_matches_pre_g7_07() {
        let toml_str = r#"
default_rate = 0.0005
cost_gate_win_rate_floor = 0.3
cost_gate_safety_multiplier = 1.3

[[tiers]]
min_turnover_usd = 1_000_000_000.0
rate = 0.0001

[[tiers]]
min_turnover_usd = 100_000_000.0
rate = 0.0002

[[tiers]]
min_turnover_usd = 10_000_000.0
rate = 0.0005

[[tiers]]
min_turnover_usd = 1_000_000.0
rate = 0.0015

[[tiers]]
min_turnover_usd = 0.0
rate = 0.003
"#;
        let cfg: SlippageConfig = toml::from_str(toml_str).expect("parse");
        assert!(cfg.validate().is_ok());
        let dflt = SlippageConfig::default();
        for vol in [
            -1.0,
            0.0,
            500.0,
            500_000.0,
            5_000_000.0,
            50_000_000.0,
            500_000_000.0,
            2_000_000_000.0,
        ] {
            assert!(
                (cfg.lookup_rate(vol) - dflt.lookup_rate(vol)).abs() < f64::EPSILON,
                "vol={} mismatch: cfg={} dflt={}",
                vol,
                cfg.lookup_rate(vol),
                dflt.lookup_rate(vol)
            );
        }
    }
}
