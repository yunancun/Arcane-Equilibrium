//! StrategyOverride — per-strategy risk override schema (extracted from risk_config.rs).
//! StrategyOverride —— 每策略風控覆蓋 schema（自 risk_config.rs 抽出）。
//!
//! MODULE_NOTE (English):
//!   G2-03 (2026-04-26) refactor: extracted to a sibling per CLAUDE.md §九 1200-line
//!   hard cap discipline. risk_config.rs grew past the cap when G2-03's
//!   `validate_against_limits` impl + 4 new SL/TP override fields landed inline;
//!   moving the entire StrategyOverride block (struct + Default + impl) here
//!   keeps the parent file under cap while preserving all behaviour.
//!
//!   Visibility note: `default_true()` was previously `pub(super)` in
//!   risk_config.rs and used by StrategyOverride's `#[serde(default)]`. After
//!   extraction, this sibling owns its own private `default_true()` and the
//!   parent module re-exports `StrategyOverride` for downstream callers
//!   (governance / tests / dispatch). No public API change.
//!
//! MODULE_NOTE (中文):
//!   G2-03（2026-04-26）重構：抽至 sibling 守 §九 1200 行硬上限。原 risk_config.rs
//!   因加入 G2-03 4 個 SL/TP override 欄位 + `validate_against_limits` impl 超限
//!   17 行，整個 StrategyOverride 區塊（struct + Default + impl）抽出來保持父檔
//!   在上限內，行為完全不變。
//!
//!   可見性：原 `default_true()` 為 `pub(super)`，本檔自帶 private 版本；父模組
//!   re-export `StrategyOverride` 供下游（governance/tests/dispatch）使用，
//!   公開 API 無變化。

use serde::{Deserialize, Serialize};

use super::default_true;
use super::{GlobalLimits, RiskConfig};

// ---------------------------------------------------------------------------
// StrategyOverride (per-strategy)
// ---------------------------------------------------------------------------

/// Per-strategy risk override. Indexed by strategy name in `RiskConfig.per_strategy`.
/// 按策略名稱索引的策略級風控覆蓋。
///
/// G2-03 (2026-04-26) — Option B2 SL/TP per-strategy override layer:
///   `stop_loss_max_pct_override` / `take_profit_max_pct_override` /
///   `take_profit_enforced_override` / `trailing_activation_pct_override` /
///   `trailing_distance_pct_override` allow ma_crossover (or any strategy) to
///   run with tighter (never looser) SL/TP than the global `RiskConfig.limits`
///   ceiling, and to enforce TP for one strategy without globally changing all
///   strategies. Three-line enforcement:
///     A. validate() rejects override > limits at IPC patch / TOML load time
///     B. risk_checks::check_position_on_tick clamps any survivor at runtime
///     C. counterfactual_calibrator dry-run rejects before write (offline)
///   Per PA RFC §3.1 + memory `project_agent_p2_dynamic_sl_tp.md`. Schema-only
///   in this commit — binding values land via manual SOP (G2-03-T4) AFTER
///   QC + FA review G2-02 counterfactual report.
///
/// G2-03（2026-04-26）—— Option B2 SL/TP 每策略覆蓋層：
///   4 個 *_override 欄位允許 ma_crossover 等策略以「比 P1 更緊」的 SL/TP
///   執行，永不可比 P1 更鬆。三道守線（A. validate 拒 > limits / B. runtime
///   clamp / C. calibrator dry-run），守住 §四 硬邊界。本 commit 只落 schema，
///   binding 值需 G2-02 counterfactual + QC+FA review 後 manual SOP 寫入。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct StrategyOverride {
    /// One-click pause/resume.
    /// 一鍵暫停/恢復。
    #[serde(default = "default_true")]
    pub enabled: bool,
    #[serde(default)]
    pub position_size_max_pct: Option<f64>,
    #[serde(default)]
    pub max_concurrent_positions: Option<u32>,
    #[serde(default)]
    pub consec_loss_cooldown_count: Option<u32>,
    #[serde(default)]
    pub allowed_symbols: Option<Vec<String>>,
    #[serde(default)]
    pub blocked_symbols: Option<Vec<String>>,

    // G2-03 (2026-04-26) — SL/TP per-strategy override fields (Option B2).
    // All Optional; None = fall back to RiskConfig.limits / RiskConfig.agent.
    // validate() enforces `override <= limits` (rejects > P1 hard ceiling).
    // G2-03 — SL/TP 每策略覆蓋；None = 走全局 limits/agent；validate 拒 > P1。
    /// Per-strategy stop-loss max pct override (must be <= limits.stop_loss_max_pct).
    /// 每策略止損最大百分比覆蓋（必須 <= limits.stop_loss_max_pct）。
    #[serde(default)]
    pub stop_loss_max_pct_override: Option<f64>,
    /// Per-strategy take-profit max pct override (must be <= limits.take_profit_max_pct).
    /// 每策略止盈最大百分比覆蓋（必須 <= limits.take_profit_max_pct）。
    #[serde(default)]
    pub take_profit_max_pct_override: Option<f64>,
    /// Per-strategy take-profit enforcement override. None = use global limits.
    /// 每策略強制止盈開關覆蓋；None = 使用全局 limits。
    #[serde(default)]
    pub take_profit_enforced_override: Option<bool>,
    /// Per-strategy trailing activation pct override (>0 when set; not capped by P1).
    /// 每策略追蹤啟動百分比覆蓋（設值時必 >0；非 P1 上限項）。
    #[serde(default)]
    pub trailing_activation_pct_override: Option<f64>,
    /// Per-strategy trailing distance pct override (>0 when set; not capped by P1).
    /// 每策略追蹤距離百分比覆蓋（設值時必 >0；非 P1 上限項）。
    #[serde(default)]
    pub trailing_distance_pct_override: Option<f64>,
}

impl Default for StrategyOverride {
    fn default() -> Self {
        Self {
            enabled: true,
            position_size_max_pct: None,
            max_concurrent_positions: None,
            consec_loss_cooldown_count: None,
            allowed_symbols: None,
            blocked_symbols: None,
            stop_loss_max_pct_override: None,
            take_profit_max_pct_override: None,
            take_profit_enforced_override: None,
            trailing_activation_pct_override: None,
            trailing_distance_pct_override: None,
        }
    }
}

impl StrategyOverride {
    /// G2-03 (2026-04-26): Validate per-strategy SL/TP overrides against the
    /// global `GlobalLimits` P1 ceiling. Called from `RiskConfig::validate()`
    /// for each `per_strategy` entry. Defense line A (per PA RFC §3.1):
    /// rejects any override that would loosen SL/TP beyond the operator hard
    /// cap. Also rejects NaN, Inf, and non-positive values.
    ///
    /// G2-03：驗證每策略 SL/TP 覆蓋不超 P1 全局上限（PA RFC §3.1 防線 A）。
    /// 由 `RiskConfig::validate()` 對每個 per_strategy entry 呼叫；
    /// 拒絕 override > P1、NaN、Inf、非正值。
    pub(crate) fn validate_against_limits(
        &self,
        strategy_name: &str,
        limits: &GlobalLimits,
    ) -> Result<(), String> {
        // Helper: reject NaN/Inf and require finite > 0 when Some.
        // 輔助：值為 Some 時拒 NaN/Inf 並要求有限正值。
        let check_pos_finite = |v: f64, field: &str| -> Result<(), String> {
            if !v.is_finite() {
                return Err(format!(
                    "risk.per_strategy.{}.{} must be finite (got {})",
                    strategy_name, field, v
                ));
            }
            if v <= 0.0 {
                return Err(format!(
                    "risk.per_strategy.{}.{} must be > 0 (got {})",
                    strategy_name, field, v
                ));
            }
            Ok(())
        };

        if let Some(sl_override) = self.stop_loss_max_pct_override {
            check_pos_finite(sl_override, "stop_loss_max_pct_override")?;
            if sl_override > limits.stop_loss_max_pct {
                return Err(format!(
                    "risk.per_strategy.{}.stop_loss_max_pct_override ({}) exceeds risk.limits.stop_loss_max_pct ({}); P1 hard ceiling cannot be loosened",
                    strategy_name, sl_override, limits.stop_loss_max_pct
                ));
            }
        }
        if let Some(tp_override) = self.take_profit_max_pct_override {
            check_pos_finite(tp_override, "take_profit_max_pct_override")?;
            if tp_override > limits.take_profit_max_pct {
                return Err(format!(
                    "risk.per_strategy.{}.take_profit_max_pct_override ({}) exceeds risk.limits.take_profit_max_pct ({}); P1 hard ceiling cannot be loosened",
                    strategy_name, tp_override, limits.take_profit_max_pct
                ));
            }
        }
        if let Some(trailing_act) = self.trailing_activation_pct_override {
            check_pos_finite(trailing_act, "trailing_activation_pct_override")?;
        }
        if let Some(trailing_dist) = self.trailing_distance_pct_override {
            check_pos_finite(trailing_dist, "trailing_distance_pct_override")?;
        }

        // Cross-field: position_size_max_pct (existing field) also bounded by
        // limits when set. Previously unvalidated; G2-03 adds this guard since
        // we're now adding the per_strategy validate hook.
        // 跨欄位：原有 position_size_max_pct 同受 limits 約束（原先未驗）。
        if let Some(pos_pct) = self.position_size_max_pct {
            if !pos_pct.is_finite() || pos_pct <= 0.0 {
                return Err(format!(
                    "risk.per_strategy.{}.position_size_max_pct must be finite > 0 (got {})",
                    strategy_name, pos_pct
                ));
            }
            if pos_pct > limits.position_size_max_pct {
                return Err(format!(
                    "risk.per_strategy.{}.position_size_max_pct ({}) exceeds risk.limits.position_size_max_pct ({})",
                    strategy_name, pos_pct, limits.position_size_max_pct
                ));
            }
        }

        Ok(())
    }
}

fn symbol_list_contains(list: &[String], symbol: &str) -> bool {
    list.iter().any(|s| s.eq_ignore_ascii_case(symbol))
}

/// Return the per-strategy symbol-policy rejection for a fresh entry.
/// Returns `None` when the strategy has no override or the symbol is eligible.
/// 返回新開倉在 per-strategy symbol policy 下的拒絕原因；可交易則返回 None。
pub fn per_strategy_new_entry_rejection(
    config: &RiskConfig,
    strategy: &str,
    symbol: &str,
) -> Option<String> {
    let Some(override_cfg) = config.per_strategy.get(strategy) else {
        return None;
    };
    if !override_cfg.enabled {
        return Some(format!("per_strategy.{strategy}.enabled=false"));
    }
    if let Some(allowed) = override_cfg.allowed_symbols.as_ref() {
        if !allowed.is_empty() && !symbol_list_contains(allowed, symbol) {
            return Some(format!(
                "{symbol} not in per_strategy.{strategy}.allowed_symbols"
            ));
        }
    }
    if let Some(blocked) = override_cfg.blocked_symbols.as_ref() {
        if symbol_list_contains(blocked, symbol) {
            return Some(format!(
                "{symbol} blocked by per_strategy.{strategy}.blocked_symbols"
            ));
        }
    }
    None
}

/// Return the per-strategy concurrency-cap rejection for a fresh entry.
/// `owned_count` is the number of OPEN positions currently attributed to
/// `strategy` (counted by `owner_strategy` from `PaperState` at the call site).
/// Returns `None` when the strategy has no override, no cap is configured,
/// or there is still headroom for one more position.
///
/// 為什麼這是 HARD 層而非 producer soft cap：producer 端 `open_symbols.len()`
/// 在重啟後可能 under-count（import_positions 把 owner 重置為 "bybit_sync"），
/// soft cap 失效 → 同策略可超開。風控層直接依 `owner_strategy` 重數一次
/// PaperState 真倉，作為 backstop 拒絕第 N+1 筆新開倉（fail-closed，不可被
/// producer 端誤差繞過）。`max_concurrent_positions` 屬 denylist 的 per_strategy
/// 前綴，agent 永不可放寬。
///
/// 不變量：僅對「新開倉」生效（呼叫端先排除 is_reducing），平倉/減倉永不被擋。
pub fn per_strategy_concurrency_rejection(
    config: &RiskConfig,
    strategy: &str,
    owned_count: usize,
) -> Option<String> {
    let override_cfg = config.per_strategy.get(strategy)?;
    let max = override_cfg.max_concurrent_positions?;
    // max=0 視為「不限」（與既有 Option=None 行為一致，避免把 0 誤判為全封）。
    if max == 0 {
        return None;
    }
    if owned_count >= max as usize {
        return Some(format!(
            "per_strategy.{strategy}.max_concurrent_positions={max} reached \
             (owned={owned_count}); new entry rejected by risk layer"
        ));
    }
    None
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::config::risk_config::{RiskConfig, StrategyOverride};

    fn cfg_with_cap(strategy: &str, cap: Option<u32>) -> RiskConfig {
        let mut cfg = RiskConfig::default();
        cfg.per_strategy.insert(
            strategy.into(),
            StrategyOverride {
                max_concurrent_positions: cap,
                ..Default::default()
            },
        );
        cfg
    }

    #[test]
    fn concurrency_rejection_blocks_at_cap() {
        // 不變量：owned==cap 時必須拒絕第 N+1 筆新開倉（HARD 層）。
        let cfg = cfg_with_cap("flash_dip_buy", Some(3));
        assert!(per_strategy_concurrency_rejection(&cfg, "flash_dip_buy", 3).is_some());
        let reason = per_strategy_concurrency_rejection(&cfg, "flash_dip_buy", 3).unwrap();
        assert!(reason.contains("max_concurrent_positions=3"));
        assert!(reason.contains("owned=3"));
    }

    #[test]
    fn concurrency_rejection_allows_below_cap() {
        let cfg = cfg_with_cap("flash_dip_buy", Some(3));
        assert!(per_strategy_concurrency_rejection(&cfg, "flash_dip_buy", 0).is_none());
        assert!(per_strategy_concurrency_rejection(&cfg, "flash_dip_buy", 2).is_none());
    }

    #[test]
    fn concurrency_rejection_blocks_above_cap() {
        // 重啟後 under-count 修正後可能出現 owned>cap，仍須拒絕（>= 比較）。
        let cfg = cfg_with_cap("flash_dip_buy", Some(3));
        assert!(per_strategy_concurrency_rejection(&cfg, "flash_dip_buy", 4).is_some());
    }

    #[test]
    fn concurrency_rejection_none_when_no_override() {
        let cfg = RiskConfig::default();
        assert!(per_strategy_concurrency_rejection(&cfg, "flash_dip_buy", 99).is_none());
    }

    #[test]
    fn concurrency_rejection_none_when_cap_unset() {
        // override 存在但 max_concurrent_positions=None → 不限。
        let cfg = cfg_with_cap("flash_dip_buy", None);
        assert!(per_strategy_concurrency_rejection(&cfg, "flash_dip_buy", 99).is_none());
    }

    #[test]
    fn concurrency_rejection_zero_means_unlimited() {
        // cap=0 視為不限，避免把 0 誤判為全封導致策略永不可開倉。
        let cfg = cfg_with_cap("flash_dip_buy", Some(0));
        assert!(per_strategy_concurrency_rejection(&cfg, "flash_dip_buy", 99).is_none());
    }
}
