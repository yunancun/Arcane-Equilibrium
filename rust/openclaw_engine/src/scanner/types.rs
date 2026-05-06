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
use std::collections::BTreeMap;

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
    /// Funding arbitrage — favors meaningful funding with controlled price drift.
    /// 資金費率套利 — 偏好有意義資金費率且價格漂移受控的行情。
    FundingArb,
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
            StrategyCategory::FundingArb => "funding_arb",
        }
    }
}

/// Scanner-side opportunity component breakdown.
/// scanner 側機會判斷的組件拆解。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OpportunityComponents {
    /// Current market-structure score before historical calibration.
    /// 當前市場結構分數，不含歷史校準。
    pub market_structure_score: f64,
    /// Strategy-specific scanner fitness score.
    /// 策略別 scanner 適配分。
    pub strategy_fitness_score: f64,
    /// Current-state gross opportunity estimate in bps.
    /// 當前狀態 gross opportunity 估計（bps）。
    pub gross_current_opportunity_bps: Option<f64>,
    /// Expected round-trip execution cost in bps.
    /// 預期來回執行成本（bps）。
    pub expected_execution_cost_bps: Option<f64>,
    /// Source used for the fee/slippage component of execution cost.
    /// 執行成本中 fee/slippage component 的來源。
    #[serde(default)]
    pub cost_source: String,
    /// Q90-style cost uncertainty buffer in bps.
    /// q90 風格成本不確定性 buffer（bps）。
    pub cost_uncertainty_bps: Option<f64>,
    /// Market/data uncertainty buffer in bps.
    /// 市場/數據不確定性 buffer（bps）。
    pub uncertainty_buffer_bps: Option<f64>,
    /// Historical realized-edge estimate in bps, if any.
    /// 歷史 realized-edge 估計（bps），未知時為 None。
    pub historical_edge_bps: Option<f64>,
    /// Historical sample count for the strategy-symbol cell.
    /// strategy-symbol cell 的歷史樣本數。
    pub historical_edge_n: u32,
    /// Historical lower confidence bound in bps, if computable.
    /// 歷史 edge 下置信界（bps），可計算時提供。
    pub historical_edge_lcb_bps: Option<f64>,
    /// Data quality score [0, 1].
    /// 數據品質分數 [0, 1]。
    pub data_quality_score: f64,
    /// Historical calibration weight [0, 1].
    /// 歷史校準權重 [0, 1]。
    pub calibration_weight: f64,
}

/// Scanner-side opportunity decision emitted in shadow mode.
/// scanner 側機會判斷；v1 僅 shadow emit，不新增拒單行為。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct OpportunityDecision {
    /// Normalized opportunity score [0, 100].
    /// 標準化機會分數 [0, 100]。
    pub opportunity_score: f64,
    /// Net lower-confidence opportunity in bps after cost and uncertainty.
    /// 扣除成本與不確定性後的 net LCB opportunity（bps）。
    pub opportunity_lcb_bps: Option<f64>,
    /// Admission hint: opportunity_positive / weak / calibration_block / etc.
    /// admission 提示。
    pub admission_hint: String,
    /// Demo/live_demo canary admission decision. True means new opens may be
    /// rejected by the scanner opportunity canary, while close/reduce paths are
    /// untouched.
    /// demo/live_demo canary 准入判斷。true 表示新開倉可被 scanner opportunity
    /// canary 拒絕；close/reduce 不受影響。
    #[serde(default)]
    pub canary_block_new_entry: bool,
    /// Compact audit reason.
    /// 精簡審計原因。
    pub reason: String,
    /// Component breakdown.
    /// 組件拆解。
    pub components: OpportunityComponents,
}

/// Strategy-specific route judgement emitted by scanner scoring.
/// scanner scoring 輸出的策略別路由判斷。
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct StrategyRouteJudgment {
    /// Strategy key (e.g. "grid_trading").
    /// 策略鍵。
    pub strategy: String,
    /// Strategy-specific raw fitness score before edge/market caps.
    /// 策略別原始適配分。
    pub fitness_score: f64,
    /// Strategy-specific final score after edge and market judgement.
    /// edge 與行情判斷後的策略別最終分。
    pub final_score: f64,
    /// Runtime edge estimate in bps for this strategy-symbol cell.
    /// 此 strategy-symbol cell 的 runtime edge bps。
    pub edge_bps: Option<f64>,
    /// Edge bonus applied before market judgement caps.
    /// market judgement cap 前套用的 edge bonus。
    pub edge_bonus: f64,
    /// Runtime sample count for this strategy-symbol cell.
    /// 此 strategy-symbol cell 的樣本數。
    pub edge_n: u32,
    /// Edge status for this strategy-symbol cell.
    /// 此 strategy-symbol cell 的 edge 狀態。
    pub edge_status: String,
    /// Route mode for this strategy-symbol cell.
    /// 此 strategy-symbol cell 的路由模式。
    pub route_mode: String,
    /// Market compatibility status: compatible / blocked / edge_quarantine.
    /// 行情相容狀態：相容 / 阻擋 / edge 隔離。
    pub market_status: String,
    /// Human-readable reason for the route decision.
    /// 路由決策原因。
    pub route_reason: String,
    /// Current opportunity evaluation for this strategy-symbol route.
    /// 此 strategy-symbol route 的當前機會判斷。
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub opportunity: Option<OpportunityDecision>,
}

/// Full scoring breakdown for a single symbol candidate.
/// Carries all intermediate values so decisions are fully auditable.
/// 單個候選交易對的完整評分明細。
/// 攜帶所有中間值以便完全審計決策。
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScoredSymbol {
    /// Symbol name (e.g. "SOLUSDT") / 交易對名稱
    pub symbol: String,
    /// Final score for the selected scanner route after edge/market judgement.
    /// 經 edge / 行情判斷後，scanner 選中 route 的最終分。
    pub final_score: f64,
    /// Raw fitness score for the selected scanner route before edge/market caps.
    /// scanner 選中 route 在 edge / 行情 cap 前的原始適配分。
    pub raw_score: f64,
    /// Strategy selected by the scanner after per-strategy edge/market judgement.
    /// 經分策略 edge / 行情判斷後 scanner 選中的策略。
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
    /// Funding arbitrage fitness [0, 100] / funding arb 適配分
    pub f_funding_arb: f64,

    // Market condition intermediates / 市場條件中間值
    /// Directional efficiency = dir_pct / range_pct ∈ [0, 1] / 方向效率
    pub de: f64,
    /// Net directional move pct (abs of 24h change %) / 淨方向移動百分比（24h 漲跌絕對值）
    pub dir_pct: f64,
    /// Total 24h range pct = (high - low) / price * 100 / 24h 總 range 百分比
    pub range_pct: f64,
    /// Funding rate absolute value in basis points / 資金費率絕對值（基點）
    pub fr_bps: f64,
    /// Signed 24h direction pct (positive = up, negative = down).
    /// 帶方向的 24h 漲跌百分比。
    pub signed_dir_pct: f64,
    /// Trend score [0, 1] derived from directional efficiency and move size.
    /// 趨勢分數。
    pub trend_score: f64,
    /// Range / mean-reversion score [0, 1].
    /// 區間 / 均值回歸分數。
    pub range_score: f64,
    /// One-way shock score [0, 1].
    /// 單邊衝擊分數。
    pub shock_score: f64,
    /// Close alignment with the 24h move direction [0, 1].
    /// 收盤位置與 24h 方向的一致性。
    pub close_alignment: f64,
    /// Last price position inside the 24h range [0=low, 1=high].
    /// 最新價在 24h range 內的位置。
    pub range_position: f64,
    /// Funding/one-way crowding proxy [0, 1].
    /// 資金費率 / 單邊擁擠 proxy。
    pub crowding_score: f64,
    /// Failed-trend / reversal risk proxy [0, 1].
    /// 趨勢失敗 / 反轉風險 proxy。
    pub reversal_risk_score: f64,
    /// Coarse scanner regime label.
    /// scanner 粗粒度行情 regime。
    pub market_regime: String,
    /// More detailed trend phase label.
    /// 更細粒度的趨勢階段標籤。
    pub trend_phase: String,
    /// 24h turnover in USDT / 24h 成交額（USDT）
    pub turnover_24h: f64,

    // Edge feedback / 邊際反饋
    /// Edge bonus applied (positive = unexplored or positive edge; negative = known negative) / 施加的邊際獎勵
    pub edge_bonus: f64,
    /// Number of fill samples for the best strategy estimate (0 = unexplored) / 最佳策略估計的成交樣本數（0 = 未探索）
    pub edge_n: u32,
    /// Runtime edge estimate in bps for the best strategy, if available.
    /// 最佳策略的 runtime edge bps，未知時為 None。
    pub edge_bps: Option<f64>,
    /// Scanner edge classification: unexplored / known / robust_negative.
    /// scanner edge 分類：unexplored / known / robust_negative。
    pub edge_status: String,
    /// Route mode derived from edge: exploration / main / exploration_only.
    /// edge 推導的路由模式：exploration / main / exploration_only。
    pub route_mode: String,
    /// Market status for the scanner's best_strategy route.
    /// scanner best_strategy route 的行情狀態。
    pub market_status: String,
    /// Route reason for the scanner's best_strategy route.
    /// scanner best_strategy route 的路由原因。
    pub route_reason: String,
    /// Per-strategy route judgement keyed by strategy name.
    /// 以策略名為鍵的策略別路由判斷。
    pub strategy_judgments: BTreeMap<String, StrategyRouteJudgment>,

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
    /// Stable identifier for this scan snapshot.
    /// 本次掃描快照的穩定 ID。
    pub scan_id: String,
    /// Currently active symbols after this scan / 本次掃描後的當前活躍交易對
    pub active_symbols: Vec<String>,
    /// Symbols added in this cycle / 本次週期新增的交易對
    pub added: Vec<String>,
    /// Symbols removed in this cycle / 本次週期移除的交易對
    pub removed: Vec<String>,
    /// Scored context for the active universe, including pinned symbols and
    /// anti-churn retained symbols. Selection still happens before this field
    /// is assembled; this list is for dispatch-time attribution and gates.
    /// 活躍交易對的評分 context，包含固定交易對與 anti-churn 保留交易對。選擇
    /// 已在組裝本欄位前完成；本列表供 dispatch 歸因與 gate 使用。
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
        assert_eq!(
            StrategyCategory::MaCrossover.as_estimate_key(),
            "ma_crossover"
        );
    }

    #[test]
    fn test_strategy_estimate_key_grid() {
        assert_eq!(
            StrategyCategory::GridTrading.as_estimate_key(),
            "grid_trading"
        );
    }

    #[test]
    fn test_strategy_estimate_key_bbrv() {
        assert_eq!(
            StrategyCategory::BbReversion.as_estimate_key(),
            "bb_reversion"
        );
    }

    #[test]
    fn test_strategy_estimate_key_bkout() {
        assert_eq!(
            StrategyCategory::BbBreakout.as_estimate_key(),
            "bb_breakout"
        );
    }

    #[test]
    fn test_strategy_estimate_key_funding() {
        assert_eq!(
            StrategyCategory::FundingArb.as_estimate_key(),
            "funding_arb"
        );
    }

    #[test]
    fn test_churn_state_default_zero_cycles() {
        let s = ChurnState::default();
        assert_eq!(s.cycles_held, 0);
        assert_eq!(s.removal_cooldown_until_ms, 0);
    }
}
