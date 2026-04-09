//! Data types for the market scanner module.
//! 市場掃描器模塊的數據類型。
//!
//! MODULE_NOTE (EN): Pure data structures — no async, no I/O.
//!   `ScoredSymbol` carries all intermediate scoring values for auditability.
//!   `ScanResult` is the immutable snapshot returned by each scan cycle.
//!   `ChurnState` tracks per-symbol stability to prevent rapid symbol churn.
//! MODULE_NOTE (中): 純數據結構，無異步，無 I/O。
//!   `ScoredSymbol` 攜帶所有中間評分值以便審計。
//!   `ScanResult` 是每次掃描週期返回的不可變快照。
//!   `ChurnState` 跟蹤每個交易對的穩定性，防止快速更換交易對。

use serde::{Deserialize, Serialize};

/// Strategy category for per-strategy fitness scoring.
/// 策略類別，用於分立的策略適配評分。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
pub enum StrategyCategory {
    /// MA crossover — favors clean directional trends.
    /// MA 交叉 — 偏好方向純淨的趨勢行情。
    MaCrossover,
    /// Grid trading — favors oscillating, range-bound markets.
    /// 網格交易 — 偏好振盪、區間震蕩行情。
    GridTrading,
    /// BB reversion — favors mean-reverting markets with intraday range.
    /// BB 回歸 — 偏好具有日內 range 的均值回歸行情。
    BbReversion,
    /// BB breakout — favors post-squeeze directional expansion.
    /// BB 突破 — 偏好擠壓後方向性膨脹行情。
    BbBreakout,
}

impl StrategyCategory {
    /// Returns the canonical string key used in edge_estimates.json lookups.
    /// 返回在 edge_estimates.json 中查找使用的標準字串鍵。
    pub fn as_estimate_key(&self) -> &'static str {
        match self {
            StrategyCategory::MaCrossover => "ma_crossover",
            StrategyCategory::GridTrading => "grid_trading",
            StrategyCategory::BbReversion => "bb_reversion",
            StrategyCategory::BbBreakout => "bb_breakout",
        }
    }
}

/// Full scoring breakdown for a single symbol candidate.
/// Carries all intermediate values so decisions are fully auditable.
/// 單個候選交易對的完整評分明細。
/// 攜帶所有中間值以便完全審計決策。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoredSymbol {
    /// Symbol name (e.g. "SOLUSDT") / 交易對名稱
    pub symbol: String,
    /// Final score after edge bonus, clamped [0, 100] / 加上邊際獎勵後的最終分數，限制在 [0, 100]
    pub final_score: f64,
    /// Raw score before edge bonus (max of four fitness scores) / 邊際獎勵前的原始分數（四個適配分的最大值）
    pub raw_score: f64,
    /// Strategy with the highest fitness score / 適配分最高的策略
    pub best_strategy: StrategyCategory,

    // Per-strategy fitness scores / 各策略適配分
    /// MA crossover fitness [0, 100] / MA 交叉適配分
    pub f_ma: f64,
    /// Grid trading fitness [0, 100] / 網格交易適配分
    pub f_grid: f64,
    /// BB reversion fitness [0, 100] / BB 回歸適配分
    pub f_bbrv: f64,
    /// BB breakout fitness [0, 100] / BB 突破適配分
    pub f_bkout: f64,

    // Market condition intermediates / 市場條件中間值
    /// Directional efficiency = dir_pct / range_pct ∈ [0, 1] / 方向效率
    pub de: f64,
    /// Net directional move pct (abs of 24h change %) / 淨方向移動百分比（24h 漲跌絕對值）
    pub dir_pct: f64,
    /// Total 24h range pct = (high - low) / price * 100 / 24h 總 range 百分比
    pub range_pct: f64,
    /// Funding rate absolute value in basis points / 資金費率絕對值（基點）
    pub fr_bps: f64,
    /// 24h turnover in USDT / 24h 成交額（USDT）
    pub turnover_24h: f64,

    // Edge feedback / 邊際反饋
    /// Edge bonus applied (positive = unexplored or positive edge; negative = known negative) / 施加的邊際獎勵
    pub edge_bonus: f64,
    /// Number of fill samples for the best strategy estimate (0 = unexplored) / 最佳策略估計的成交樣本數（0 = 未探索）
    pub edge_n: u32,

    // Correlation / diversification / 相關性 / 分散
    /// BTC beta proxy (None if BTC barely moved) / BTC beta 代理（BTC 幾乎不動時為 None）
    pub beta_proxy: Option<f64>,
    /// Sector of this symbol / 此交易對的板塊
    pub sector: String,
}

/// Immutable snapshot produced by one scanner cycle.
/// 一次掃描週期產生的不可變快照。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanResult {
    /// Unix timestamp (ms) when the scan completed / 掃描完成時的 Unix 時間戳（毫秒）
    pub scan_ts_ms: u64,
    /// Currently active symbols after this scan / 本次掃描後的當前活躍交易對
    pub active_symbols: Vec<String>,
    /// Symbols added in this cycle / 本次週期新增的交易對
    pub added: Vec<String>,
    /// Symbols removed in this cycle / 本次週期移除的交易對
    pub removed: Vec<String>,
    /// Top candidates considered (sorted by final_score desc) / 考慮的頂級候選（按 final_score 降序）
    pub candidates: Vec<ScoredSymbol>,
    /// Number of symbols rejected by hard filters / 被硬過濾器拒絕的交易對數量
    pub rejected_count: usize,
    /// Duration of the scan in milliseconds / 掃描耗時（毫秒）
    pub scan_duration_ms: u64,
}

/// Per-symbol stability tracking to prevent rapid churn.
/// 每個交易對的穩定性跟蹤，防止快速更換。
#[derive(Debug, Clone, Default)]
pub struct ChurnState {
    /// Number of consecutive scan cycles this symbol has been active / 此交易對連續保持活躍的掃描週期數
    pub cycles_held: u32,
    /// Timestamp (ms) before which this symbol cannot re-enter after removal / 移除後此交易對不能重新加入的時間戳（毫秒）
    pub removal_cooldown_until_ms: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_strategy_estimate_key_ma() {
        assert_eq!(StrategyCategory::MaCrossover.as_estimate_key(), "ma_crossover");
    }

    #[test]
    fn test_strategy_estimate_key_grid() {
        assert_eq!(StrategyCategory::GridTrading.as_estimate_key(), "grid_trading");
    }

    #[test]
    fn test_strategy_estimate_key_bbrv() {
        assert_eq!(StrategyCategory::BbReversion.as_estimate_key(), "bb_reversion");
    }

    #[test]
    fn test_strategy_estimate_key_bkout() {
        assert_eq!(StrategyCategory::BbBreakout.as_estimate_key(), "bb_breakout");
    }

    #[test]
    fn test_churn_state_default_zero_cycles() {
        let s = ChurnState::default();
        assert_eq!(s.cycles_held, 0);
        assert_eq!(s.removal_cooldown_until_ms, 0);
    }
}
