//! Market scanner scoring engine — per-strategy fitness + edge feedback + correlation filter.
//! 市場掃描器評分引擎 — 分策略適配評分 + 邊際反饋 + 相關性過濾。
//!
//! MODULE_NOTE (EN): All functions are pure (no async, no I/O, no global state).
//!   The five fitness functions (F_ma, F_grid, F_bbrv, F_bkout, F_funding_arb) model different
//!   optimal market regimes. `apply_correlation_filter` greedily selects the top-N
//!   symbols while enforcing BTC-beta, per-strategy, and per-sector caps.
//!   See SCANNER_TODO.md §評分框架 for the full formula derivation.
//! MODULE_NOTE (中): 所有函數為純函數（無異步、無 I/O、無全局狀態）。
//!   五個適配評分函數（F_ma、F_grid、F_bbrv、F_bkout、F_funding_arb）建模不同的最優市場環境。
//!   `apply_correlation_filter` 貪心選擇前 N 個交易對，同時執行 BTC-beta、
//!   每策略和每板塊上限。完整公式推導見 SCANNER_TODO.md §評分框架。

use crate::edge_estimates::{CellEstimate, EdgeEstimates};
use crate::market_data_client::types::TickerInfo;
use crate::scanner::config::{
    CorrelationLimits, EdgeRoutingConfig, HardFilters, MarketJudgmentConfig, OpportunityConfig,
};
use crate::scanner::market_judgment::{build_strategy_judgments, classify_market_regime};
use crate::scanner::opportunity::evaluate_opportunity;
use crate::scanner::sectors::{base_from_usdt_symbol, symbol_sector, STABLECOIN_BASES};
use crate::scanner::strategy_policy::{apply_strategy_policy, ScannerStrategyPolicy};
use crate::scanner::types::{ScoredSymbol, StrategyCategory, StrategyRouteJudgment};
use std::collections::HashMap;

// ─── Hard Filters ─────────────────────────────────────────────────────────────

/// Apply hard filters to a ticker. Returns Some(()) if the ticker passes all filters.
/// Returns None if any filter fails (symbol is disqualified entirely).
/// 對行情施加硬過濾器。若所有過濾器通過則返回 Some(())。
/// 若任一過濾器失敗（交易對被完全淘汰）則返回 None。
pub fn apply_hard_filters(ticker: &TickerInfo, config: &HardFilters) -> Option<()> {
    // FILTER_4: Must end with USDT / 必須以 USDT 結尾
    let base = base_from_usdt_symbol(&ticker.symbol)?;

    // FILTER_5: Base must not be a stablecoin / 基礎貨幣不得為穩定幣
    if STABLECOIN_BASES.contains(&base) {
        return None;
    }

    // FILTER_1: Minimum turnover / 最低成交額
    if ticker.turnover_24h < config.min_turnover_24h_usdt {
        return None;
    }

    // FILTER_2: Minimum price / 最低價格
    if ticker.last_price < config.min_price_usdt {
        return None;
    }

    // FILTER_3: Maximum spread in basis points / 最大買賣差價（基點）
    // spread_bps = (ask1 - bid1) / mid * 10000
    let mid = (ticker.bid1_price + ticker.ask1_price) / 2.0;
    if mid > 0.0 {
        let spread_bps = (ticker.ask1_price - ticker.bid1_price) / mid * 10_000.0;
        if spread_bps > config.max_spread_bps {
            return None;
        }
    }

    Some(())
}

// ─── Intermediate calculations ─────────────────────────────────────────────────

/// Market condition intermediates derived from a TickerInfo.
/// Bybit's price24hPcnt is a decimal fraction (0.0077 = +0.77%). We multiply by 100
/// to get percentage points for intuitive comparisons.
/// 從 TickerInfo 計算的市場條件中間值。
/// Bybit 的 price24hPcnt 是小數分數（0.0077 = +0.77%）。乘以 100 得到百分比點。
#[derive(Debug, Clone)]
pub struct MarketConditions {
    /// Signed net directional move % / 帶方向的淨移動百分比
    pub signed_dir_pct: f64,
    /// Net directional move % (absolute value) / 淨方向移動百分比（絕對值）
    pub dir_pct: f64,
    /// 24h total range % = (high - low) / price * 100 / 24h 總 range 百分比
    pub range_pct: f64,
    /// Directional efficiency = dir_pct / range_pct ∈ [0, 1] / 方向效率
    pub de: f64,
    /// Funding rate absolute value in bps / 資金費率絕對值（基點）
    pub fr_bps: f64,
    /// Signed funding rate in bps / 帶方向資金費率（基點）
    pub signed_fr_bps: f64,
    /// Trend score [0, 1] / 趨勢分數
    pub trend_score: f64,
    /// Range / mean-reversion score [0, 1] / 區間震盪分數
    pub range_score: f64,
    /// One-way shock score [0, 1] / 單邊衝擊分數
    pub shock_score: f64,
    /// Close alignment with the signed 24h move [0, 1] / 收盤與 24h 方向一致性
    pub close_alignment: f64,
    /// Last price position inside the 24h range [0, 1] / 最新價在 24h range 內的位置
    pub range_position: f64,
    /// Funding + one-way trend crowding proxy [0, 1] / 資金費率 + 單邊趨勢擁擠 proxy
    pub crowding_score: f64,
    /// Failed-trend / reversal risk proxy [0, 1] / 趨勢失敗 / 反轉風險 proxy
    pub reversal_risk_score: f64,
    /// Fine-grained trend phase label / 細粒度趨勢階段標籤
    pub trend_phase: String,
    /// 24h turnover / 24h 成交額
    pub turnover_24h: f64,
}

fn classify_trend_phase(
    trend_score: f64,
    shock_score: f64,
    range_score: f64,
    crowding_score: f64,
    reversal_risk_score: f64,
    range_pct: f64,
) -> &'static str {
    if shock_score >= 0.55 && crowding_score >= 0.45 {
        "crowded_shock"
    } else if shock_score >= 0.55 {
        "one_way_shock"
    } else if reversal_risk_score >= 0.30 {
        "failed_trend"
    } else if trend_score >= 0.60 {
        "clean_trend"
    } else if range_score >= 0.35 {
        "range_bound"
    } else if range_pct < 3.0 {
        "quiet"
    } else {
        "mixed"
    }
}

/// Compute market condition intermediates from a TickerInfo.
/// 從 TickerInfo 計算市場條件中間值。
pub fn compute_market_conditions(ticker: &TickerInfo) -> MarketConditions {
    // Bybit price24hPcnt is a ratio (e.g. 0.0077 = 0.77%), convert to %
    // Bybit price24hPcnt 是比率（例如 0.0077 = 0.77%），轉換為百分比
    let signed_dir_pct = ticker.price_change_24h_pct * 100.0;
    let dir_pct = signed_dir_pct.abs();

    let price = ticker.last_price.max(1e-12);
    let range_abs = (ticker.high_price_24h - ticker.low_price_24h).max(0.0);
    let range_pct = (range_abs / price * 100.0).max(0.0);

    let de = if range_pct > 0.0 {
        (dir_pct / range_pct).clamp(0.0, 1.0)
    } else {
        0.0
    };

    let signed_fr_bps = ticker.funding_rate * 10_000.0;
    let fr_bps = signed_fr_bps.abs();
    let range_position = if range_abs > 0.0 {
        ((ticker.last_price - ticker.low_price_24h) / range_abs).clamp(0.0, 1.0)
    } else {
        0.5
    };
    let close_alignment = if signed_dir_pct > 0.0 {
        range_position
    } else if signed_dir_pct < 0.0 {
        1.0 - range_position
    } else {
        0.5
    };
    let dir_norm = (dir_pct / 6.0).clamp(0.0, 1.0);
    let range_norm = (range_pct / 12.0).clamp(0.0, 1.0);
    let range_mid_score = (1.0 - (range_position - 0.5).abs() * 2.0).clamp(0.0, 1.0);
    let trend_score = (0.45 * de + 0.35 * dir_norm + 0.20 * close_alignment).clamp(0.0, 1.0);
    let range_score = ((0.70 * (1.0 - de) + 0.30 * range_mid_score) * range_norm).clamp(0.0, 1.0);
    let shock_score =
        (de * (dir_pct / 8.0).clamp(0.0, 1.0) * (0.5 + 0.5 * close_alignment)).clamp(0.0, 1.0);
    let crowding_score =
        (((fr_bps - 8.0) / 20.0).clamp(0.0, 1.0) * (0.5 + 0.5 * trend_score)).clamp(0.0, 1.0);
    let reversal_risk_score =
        (trend_score * (1.0 - close_alignment) * (dir_pct / 4.0).clamp(0.0, 1.0)).clamp(0.0, 1.0);
    let trend_phase = classify_trend_phase(
        trend_score,
        shock_score,
        range_score,
        crowding_score,
        reversal_risk_score,
        range_pct,
    )
    .to_string();

    MarketConditions {
        signed_dir_pct,
        dir_pct,
        range_pct,
        de,
        fr_bps,
        signed_fr_bps,
        trend_score,
        range_score,
        shock_score,
        close_alignment,
        range_position,
        crowding_score,
        reversal_risk_score,
        trend_phase,
        turnover_24h: ticker.turnover_24h,
    }
}

// ─── Per-strategy fitness functions ───────────────────────────────────────────

/// F_ma: MA crossover fitness score [0, 100].
/// Rewards directional efficiency and magnitude. Penalizes crowded funding rates.
/// Zero if dir_pct < 0.5% (no meaningful trend). Threshold lowered from 1.5% (M-3 fix):
/// BTC in sideways periods typically moves 0.5–1.2% over 24h; 1.5% gate excluded it entirely.
/// F_ma：MA 交叉適配分 [0, 100]。
/// 獎勵方向效率和幅度。懲罰擁擠的資金費率。
/// 若 dir_pct < 0.5%（無有意義趨勢）則為零。閾值從 1.5% 降低（M-3 修復）：
/// BTC 橫盤期 24h 移動通常在 0.5–1.2%，1.5% 門檻會完全過濾掉它。
pub fn f_ma(mc: &MarketConditions) -> f64 {
    if mc.dir_pct < 0.5 {
        return 0.0;
    }
    let base = 100.0 * (0.70 * mc.trend_score + 0.30 * (mc.dir_pct / 10.0).clamp(0.0, 1.0));
    (base - mc.crowding_score * 20.0 - mc.reversal_risk_score * 35.0).max(0.0)
}

/// F_grid: Grid trading fitness score [0, 100].
/// Rewards oscillating, range-bound markets. Penalizes directional drift.
/// Zero if range_pct < 3% or dir_pct >= 8% (too trending for grid).
/// High-liquidity bonus: +15% if turnover >= $100M.
/// F_grid：網格交易適配分 [0, 100]。
/// 獎勵振盪、區間震蕩行情。懲罰方向漂移。
/// 若 range_pct < 3% 或 dir_pct >= 8%（趨勢太強不適合網格）則為零。
/// 高流動性加成：成交額 >= $100M 時 +15%。
pub fn f_grid(mc: &MarketConditions) -> f64 {
    if mc.range_pct < 3.0 || mc.dir_pct >= 8.0 {
        return 0.0;
    }
    let base = (mc.range_score * 100.0 - mc.trend_score * 25.0 - mc.shock_score * 20.0).max(0.0);
    let liquidity_bonus = if mc.turnover_24h >= 100_000_000.0 {
        base * 0.15
    } else {
        0.0
    };
    (base + liquidity_bonus).min(100.0)
}

/// F_bbrv: BB reversion fitness score [0, 100].
/// Rewards mean-reverting markets with 4%-20% intraday range.
/// Snap-back bonus when funding rate is extreme but price barely moved (crowded → squeeze).
/// F_bbrv：BB 回歸適配分 [0, 100]。
/// 獎勵具有 4%-20% 日內 range 的均值回歸行情。
/// 當資金費率極端但價格幾乎不動時（持倉擁擠 → 擠壓）給予回彈加成。
pub fn f_bbrv(mc: &MarketConditions) -> f64 {
    if mc.range_pct < 4.0 || mc.range_pct > 20.0 {
        return 0.0;
    }
    let base = (mc.range_score * 100.0 + mc.reversal_risk_score * 20.0).max(0.0);
    // Snap-back bonus: extreme funding + low net move = likely reversal setup
    // 回彈加成：極端資金費率 + 低淨移動 = 可能的反轉設置
    let bonus_multiplier =
        if (mc.fr_bps > 15.0 && mc.dir_pct < 3.0) || mc.reversal_risk_score > 0.25 {
            1.2
        } else {
            1.0
        };
    (base * bonus_multiplier - mc.shock_score * 20.0)
        .max(0.0)
        .min(100.0)
}

/// F_bkout: BB breakout fitness score [0, 100].
/// Approximates post-squeeze breakout using directional efficiency + range.
/// NOTE: This is a proxy — real BB bandwidth requires kline data (future improvement).
/// Penalizes crowded / failed trends, which signal exhaustion rather than continuation.
/// F_bkout：BB 突破適配分 [0, 100]。
/// 使用方向效率 + range 近似擠壓後的突破。
/// 注意：這是代理指標 — 真實 BB 帶寬需要 K 線數據（未來改進路徑）。
/// 懲罰過度擁擠 / 失敗趨勢，這表示耗盡而非延續。
pub fn f_bkout(mc: &MarketConditions) -> f64 {
    if mc.range_pct < 3.0 || mc.range_pct > 20.0 || mc.dir_pct <= 2.0 {
        return 0.0;
    }
    let base = 100.0
        * (0.55 * mc.trend_score
            + 0.25 * (mc.range_pct / 12.0).clamp(0.0, 1.0)
            + 0.20 * mc.close_alignment);
    (base - mc.crowding_score * 25.0 - mc.reversal_risk_score * 30.0).max(0.0)
}

/// F_funding_arb: funding-arb market fitness proxy [0, 100].
/// Requires meaningful funding while penalizing strong one-way spot movement.
/// F_funding_arb：funding arb 行情適配 proxy；需有資金費率，同時懲罰單邊行情。
pub fn f_funding_arb(mc: &MarketConditions) -> f64 {
    if mc.fr_bps < 3.0 {
        return 0.0;
    }
    let funding_base = ((mc.fr_bps - 3.0) / 17.0).clamp(0.0, 1.0) * 100.0;
    (funding_base - mc.trend_score * 30.0 - mc.shock_score * 25.0 - mc.crowding_score * 15.0)
        .max(0.0)
}

// ─── Full fitness bundle ───────────────────────────────────────────────────────

/// All five strategy fitness scores for one symbol.
/// 一個交易對的五個策略適配分。
#[derive(Debug, Clone)]
pub struct FitnessScores {
    pub f_ma: f64,
    pub f_grid: f64,
    pub f_bbrv: f64,
    pub f_bkout: f64,
    pub f_funding_arb: f64,
    pub raw: f64,
    pub best: StrategyCategory,
}

/// Compute all five fitness scores and identify the best strategy.
/// 計算所有五個適配分並確定最佳策略。
pub fn compute_fitness(mc: &MarketConditions) -> FitnessScores {
    let scores = [
        (f_ma(mc), StrategyCategory::MaCrossover),
        (f_grid(mc), StrategyCategory::GridTrading),
        (f_bbrv(mc), StrategyCategory::BbReversion),
        (f_bkout(mc), StrategyCategory::BbBreakout),
        (f_funding_arb(mc), StrategyCategory::FundingArb),
    ];
    let (raw, best) =
        scores
            .iter()
            .copied()
            .fold((0.0_f64, StrategyCategory::MaCrossover), |acc, (s, cat)| {
                if s > acc.0 {
                    (s, cat)
                } else {
                    acc
                }
            });
    FitnessScores {
        f_ma: scores[0].0,
        f_grid: scores[1].0,
        f_bbrv: scores[2].0,
        f_bkout: scores[3].0,
        f_funding_arb: scores[4].0,
        raw,
        best,
    }
}

// ─── Edge feedback ────────────────────────────────────────────────────────────

#[derive(Debug, Clone, PartialEq)]
pub struct EdgeFeedback {
    pub final_score: f64,
    pub bonus: f64,
    pub n: u32,
    pub edge_bps: Option<f64>,
    pub edge_status: String,
    pub route_mode: String,
    pub market_status: String,
    pub route_reason: String,
}

fn posterior_lcb_bps(cell: &CellEstimate, config: &EdgeRoutingConfig) -> Option<f64> {
    if config.posterior_lcb_z <= 0.0 || cell.n_trades == 0 {
        return None;
    }
    let sample_std = if cell.std_bps.is_finite() && cell.std_bps > 0.0 {
        cell.std_bps
    } else {
        config.posterior_min_std_bps
    };
    let std = sample_std.max(config.posterior_min_std_bps);
    Some(cell.shrunk_bps - config.posterior_lcb_z * std / (cell.n_trades as f64).sqrt())
}

/// Apply edge feedback from runtime estimates.
/// Normal known cells preserve the previous formula by default:
/// `bonus = clamp(runtime_bps * 0.5, -30, 10)`. Mature negative cells are
/// capped out of the main route so scanner fitness cannot keep routing symbols
/// that the realized net edge already rejected.
/// 套用 runtime edge 回饋。正常 known cell 預設保持舊公式；成熟負 edge cell
/// 會被 cap 出主路由，避免 scanner raw fitness 誤導策略。
pub fn apply_edge_bonus(
    raw: f64,
    best_strategy: StrategyCategory,
    symbol: &str,
    estimates: &EdgeEstimates,
    config: &EdgeRoutingConfig,
) -> EdgeFeedback {
    apply_edge_bonus_for_strategy(
        raw,
        best_strategy.as_estimate_key(),
        symbol,
        estimates,
        config,
    )
}

/// Apply edge feedback for an explicit strategy key.
/// 對指定策略鍵套用 edge 回饋。
pub fn apply_edge_bonus_for_strategy(
    raw: f64,
    strategy_key: &str,
    symbol: &str,
    estimates: &EdgeEstimates,
    config: &EdgeRoutingConfig,
) -> EdgeFeedback {
    match estimates.get_cell(strategy_key, symbol) {
        Some(cell) => {
            let bonus =
                (cell.shrunk_bps * config.bonus_weight).clamp(config.bonus_min, config.bonus_max);
            let mut final_score = (raw + bonus).clamp(0.0, 100.0);
            let mature = cell.n_trades >= u64::from(config.robust_negative_min_trades);
            let point_negative = cell.shrunk_bps < config.robust_negative_bps_threshold;
            let posterior_negative = mature
                && posterior_lcb_bps(cell, config)
                    .map(|lcb| lcb < config.posterior_negative_lcb_threshold_bps)
                    .unwrap_or(false);
            let robust_negative = mature && (point_negative || posterior_negative);
            let (edge_status, route_mode, route_reason) = if robust_negative {
                final_score = final_score.min(config.robust_negative_score_cap);
                if posterior_negative && !point_negative {
                    (
                        "posterior_negative",
                        "exploration_only",
                        format!(
                            "posterior_negative_edge:n={} bps={:.2}",
                            cell.n_trades, cell.shrunk_bps
                        ),
                    )
                } else {
                    (
                        "robust_negative",
                        "exploration_only",
                        format!(
                            "robust_negative_edge:n={} bps={:.2}",
                            cell.n_trades, cell.shrunk_bps
                        ),
                    )
                }
            } else {
                (
                    "known",
                    "main",
                    format!("known_edge:n={} bps={:.2}", cell.n_trades, cell.shrunk_bps),
                )
            };
            EdgeFeedback {
                final_score,
                bonus,
                n: cell.n_trades.min(u64::from(u32::MAX)) as u32,
                edge_bps: Some(cell.shrunk_bps),
                edge_status: edge_status.to_string(),
                route_mode: route_mode.to_string(),
                market_status: "compatible".to_string(),
                route_reason,
            }
        }
        None => {
            // Unexplored symbol — give exploration credit / 未探索交易對 — 給予探索加分
            let final_score = (raw + config.unexplored_bonus).clamp(0.0, 100.0);
            EdgeFeedback {
                final_score,
                bonus: config.unexplored_bonus,
                n: 0,
                edge_bps: None,
                edge_status: "unexplored".to_string(),
                route_mode: "exploration".to_string(),
                market_status: "compatible".to_string(),
                route_reason: "edge_unexplored".to_string(),
            }
        }
    }
}

// ─── BTC beta proxy ───────────────────────────────────────────────────────────

/// Compute a BTC beta proxy from 24h price changes.
/// Returns None if BTC barely moved (avoids extreme/meaningless ratios).
/// Result is clamped to [-0.5, 3.0] to bound outliers.
/// 從 24h 價格變化計算 BTC beta 代理。
/// 若 BTC 幾乎不動（避免極端/無意義的比率）則返回 None。
/// 結果限制在 [-0.5, 3.0] 以限制異常值。
pub fn beta_proxy(symbol_change_pct: f64, btc_change_pct: f64, min_btc_move: f64) -> Option<f64> {
    if btc_change_pct.abs() < min_btc_move {
        return None;
    }
    Some((symbol_change_pct / btc_change_pct).clamp(-0.5, 3.0))
}

// ─── Correlation filter ────────────────────────────────────────────────────────

/// Greedily select top symbols from sorted candidates, enforcing diversification caps.
/// Input: `candidates` sorted by `final_score` descending.
/// Input: `pinned` symbols already guaranteed inclusion (BTC, ETH).
/// Output: up to `max_dynamic_slots` symbols, excluding pinned.
/// 從排序後的候選中貪心選擇頂部交易對，執行分散上限。
/// 輸入：`candidates` 按 `final_score` 降序排序。
/// 輸入：`pinned` 已保證包含的交易對（BTC、ETH）。
/// 輸出：最多 `max_dynamic_slots` 個交易對，不含固定交易對。
pub fn apply_correlation_filter(
    candidates: Vec<ScoredSymbol>,
    pinned: &[String],
    max_dynamic_slots: usize,
    config: &CorrelationLimits,
) -> Vec<ScoredSymbol> {
    let mut selected: Vec<ScoredSymbol> = Vec::with_capacity(max_dynamic_slots);
    let mut high_beta_count: usize = 0;
    let mut strategy_counts: HashMap<String, usize> = HashMap::new();
    let mut sector_counts: HashMap<String, usize> = HashMap::new();

    // C-4 fix: Pre-occupy cap counters with pinned symbol data so the greedy
    // loop sees the true remaining capacity.  BTC+ETH are both high-beta
    // l1_infra, so without this they don't count against max_high_beta or
    // max_per_sector — allowing the pool to select beyond the intended limits.
    // C-4 修復：用固定交易對數據預佔上限計數器，使貪心循環看到真實剩餘容量。
    for p in pinned {
        if let Some(pinned_sym) = candidates.iter().find(|c| &c.symbol == p) {
            if let Some(bp) = pinned_sym.beta_proxy {
                if bp > config.high_beta_threshold {
                    high_beta_count += 1;
                }
            }
            let strategy_key = pinned_sym.best_strategy.as_estimate_key().to_string();
            *strategy_counts.entry(strategy_key).or_insert(0) += 1;
            *sector_counts.entry(pinned_sym.sector.clone()).or_insert(0) += 1;
        }
    }

    for candidate in candidates {
        if selected.len() >= max_dynamic_slots {
            break;
        }

        // Skip pinned symbols (they're added separately) / 跳過固定交易對（單獨添加）
        if pinned.iter().any(|p| p == &candidate.symbol) {
            continue;
        }

        // BTC beta cap / BTC beta 上限
        if let Some(bp) = candidate.beta_proxy {
            if bp > config.high_beta_threshold {
                if high_beta_count >= config.max_high_beta_symbols {
                    continue;
                }
                high_beta_count += 1;
            }
        }

        // Per-strategy cap / 每策略上限
        let strategy_key = candidate.best_strategy.as_estimate_key().to_string();
        let strategy_count = strategy_counts.entry(strategy_key).or_insert(0);
        if *strategy_count >= config.max_per_strategy {
            continue;
        }
        *strategy_count += 1;

        // Per-sector cap / 每板塊上限
        let sector_count = sector_counts.entry(candidate.sector.clone()).or_insert(0);
        if *sector_count >= config.max_per_sector {
            continue;
        }
        *sector_count += 1;

        selected.push(candidate);
    }

    selected
}

/// Build a complete ScoredSymbol from a TickerInfo, given BTC's 24h change for beta calc.
/// This is the main entry point called by ScannerRunner for each ticker.
/// 從 TickerInfo 構建完整的 ScoredSymbol，給定 BTC 的 24h 變化用於 beta 計算。
/// 這是 ScannerRunner 對每個行情調用的主入口。
pub fn score_ticker(
    ticker: &TickerInfo,
    btc_change_pct: f64,
    estimates: &EdgeEstimates,
    hard_filter_config: &HardFilters,
    edge_routing_config: &EdgeRoutingConfig,
    market_judgment_config: &MarketJudgmentConfig,
) -> Option<ScoredSymbol> {
    score_ticker_with_policy(
        ticker,
        btc_change_pct,
        estimates,
        hard_filter_config,
        edge_routing_config,
        market_judgment_config,
        &ScannerStrategyPolicy::default(),
    )
}

/// Build a scored symbol while applying scanner-side strategy policy.
/// 套用 scanner 側策略政策後生成候選交易對評分。
pub fn score_ticker_with_policy(
    ticker: &TickerInfo,
    btc_change_pct: f64,
    estimates: &EdgeEstimates,
    hard_filter_config: &HardFilters,
    edge_routing_config: &EdgeRoutingConfig,
    market_judgment_config: &MarketJudgmentConfig,
    strategy_policy: &ScannerStrategyPolicy,
) -> Option<ScoredSymbol> {
    score_ticker_with_policy_and_opportunity(
        ticker,
        btc_change_pct,
        estimates,
        hard_filter_config,
        edge_routing_config,
        market_judgment_config,
        &OpportunityConfig::default(),
        strategy_policy,
    )
}

/// Build a scored symbol while applying scanner-side strategy policy and
/// emitting scanner opportunity shadow fields.
/// 套用 scanner 側策略政策並輸出 opportunity shadow 欄位後生成候選評分。
#[allow(clippy::too_many_arguments)]
pub fn score_ticker_with_policy_and_opportunity(
    ticker: &TickerInfo,
    btc_change_pct: f64,
    estimates: &EdgeEstimates,
    hard_filter_config: &HardFilters,
    edge_routing_config: &EdgeRoutingConfig,
    market_judgment_config: &MarketJudgmentConfig,
    opportunity_config: &OpportunityConfig,
    strategy_policy: &ScannerStrategyPolicy,
) -> Option<ScoredSymbol> {
    score_ticker_internal(
        ticker,
        btc_change_pct,
        estimates,
        hard_filter_config,
        edge_routing_config,
        market_judgment_config,
        opportunity_config,
        strategy_policy,
        true,
    )
}

/// Build scanner context for an already-active symbol without applying universe
/// hard filters. This is for observability/attribution only; selection still
/// uses `score_ticker_with_policy`.
/// 為已活躍交易對建立 scanner context，不套用 universe hard filters。僅供
/// 可觀測性/歸因使用；候選選擇仍走 `score_ticker_with_policy`。
pub fn score_ticker_for_context(
    ticker: &TickerInfo,
    btc_change_pct: f64,
    estimates: &EdgeEstimates,
    hard_filter_config: &HardFilters,
    edge_routing_config: &EdgeRoutingConfig,
    market_judgment_config: &MarketJudgmentConfig,
    strategy_policy: &ScannerStrategyPolicy,
) -> Option<ScoredSymbol> {
    score_ticker_for_context_with_opportunity(
        ticker,
        btc_change_pct,
        estimates,
        hard_filter_config,
        edge_routing_config,
        market_judgment_config,
        &OpportunityConfig::default(),
        strategy_policy,
    )
}

/// Build scanner context for an active symbol and emit opportunity shadow
/// fields using the runtime scanner opportunity config.
/// 為已活躍交易對建立 scanner context，並使用 runtime opportunity config
/// 輸出 shadow 欄位。
#[allow(clippy::too_many_arguments)]
pub fn score_ticker_for_context_with_opportunity(
    ticker: &TickerInfo,
    btc_change_pct: f64,
    estimates: &EdgeEstimates,
    hard_filter_config: &HardFilters,
    edge_routing_config: &EdgeRoutingConfig,
    market_judgment_config: &MarketJudgmentConfig,
    opportunity_config: &OpportunityConfig,
    strategy_policy: &ScannerStrategyPolicy,
) -> Option<ScoredSymbol> {
    score_ticker_internal(
        ticker,
        btc_change_pct,
        estimates,
        hard_filter_config,
        edge_routing_config,
        market_judgment_config,
        opportunity_config,
        strategy_policy,
        false,
    )
}

#[allow(clippy::too_many_arguments)]
fn score_ticker_internal(
    ticker: &TickerInfo,
    btc_change_pct: f64,
    estimates: &EdgeEstimates,
    hard_filter_config: &HardFilters,
    edge_routing_config: &EdgeRoutingConfig,
    market_judgment_config: &MarketJudgmentConfig,
    opportunity_config: &OpportunityConfig,
    strategy_policy: &ScannerStrategyPolicy,
    enforce_hard_filters: bool,
) -> Option<ScoredSymbol> {
    if enforce_hard_filters {
        apply_hard_filters(ticker, hard_filter_config)?;
    }

    let base = base_from_usdt_symbol(&ticker.symbol).unwrap_or("");
    let sector = symbol_sector(base).to_string();

    let mc = compute_market_conditions(ticker);
    let fitness = compute_fitness(&mc);
    let mut strategy_judgments = build_strategy_judgments(
        &fitness,
        &mc,
        &ticker.symbol,
        estimates,
        edge_routing_config,
        market_judgment_config,
    );
    apply_strategy_policy(&ticker.symbol, &mut strategy_judgments, strategy_policy);
    for (strategy, judgment) in strategy_judgments.iter_mut() {
        let cell = estimates.get_cell(strategy, &ticker.symbol);
        judgment.opportunity = Some(evaluate_opportunity(
            strategy,
            judgment,
            &mc,
            ticker,
            cell,
            opportunity_config,
        ));
    }
    let best_route = [
        (StrategyCategory::MaCrossover, "ma_crossover"),
        (StrategyCategory::GridTrading, "grid_trading"),
        (StrategyCategory::BbReversion, "bb_reversion"),
        (StrategyCategory::BbBreakout, "bb_breakout"),
        (StrategyCategory::FundingArb, "funding_arb"),
    ]
    .into_iter()
    .filter_map(|(category, key)| strategy_judgments.get(key).cloned().map(|j| (category, j)))
    .filter(|(_, judgment)| {
        !matches!(
            judgment.route_mode.as_str(),
            "market_gate" | "exploration_only" | "risk_policy_gate"
        )
    })
    .max_by(|a, b| a.1.final_score.total_cmp(&b.1.final_score));
    let (best_strategy, best_judgment) = match best_route {
        Some(route) => route,
        None if !strategy_judgments.contains_key(fitness.best.as_estimate_key()) => {
            let best_key = fitness.best.as_estimate_key();
            let edge = apply_edge_bonus(
                fitness.raw,
                fitness.best,
                &ticker.symbol,
                estimates,
                edge_routing_config,
            );
            let mut fallback_judgment = StrategyRouteJudgment {
                strategy: best_key.to_string(),
                fitness_score: fitness.raw,
                final_score: edge.final_score,
                edge_bps: edge.edge_bps,
                edge_bonus: edge.bonus,
                edge_n: edge.n,
                edge_status: edge.edge_status,
                route_mode: edge.route_mode,
                market_status: edge.market_status,
                route_reason: edge.route_reason,
                opportunity: None,
            };
            fallback_judgment.opportunity = Some(evaluate_opportunity(
                best_key,
                &fallback_judgment,
                &mc,
                ticker,
                estimates.get_cell(best_key, &ticker.symbol),
                opportunity_config,
            ));
            (fitness.best, fallback_judgment)
        }
        None => return None,
    };

    // BTC change_pct already in percentage points (dir_pct * 100 from ticker)
    // Bybit's price24hPcnt is a ratio; mc.dir_pct is already in %, so we need
    // the raw pct (with sign) for beta proxy
    let symbol_change_pct = ticker.price_change_24h_pct * 100.0;
    let bp = beta_proxy(
        symbol_change_pct,
        btc_change_pct,
        hard_filter_config.btc_min_move_pct,
    );

    Some(ScoredSymbol {
        symbol: ticker.symbol.clone(),
        final_score: best_judgment.final_score,
        raw_score: best_judgment.fitness_score,
        best_strategy,
        f_ma: fitness.f_ma,
        f_grid: fitness.f_grid,
        f_bbrv: fitness.f_bbrv,
        f_bkout: fitness.f_bkout,
        f_funding_arb: fitness.f_funding_arb,
        de: mc.de,
        dir_pct: mc.dir_pct,
        range_pct: mc.range_pct,
        fr_bps: mc.fr_bps,
        signed_dir_pct: mc.signed_dir_pct,
        trend_score: mc.trend_score,
        range_score: mc.range_score,
        shock_score: mc.shock_score,
        close_alignment: mc.close_alignment,
        range_position: mc.range_position,
        crowding_score: mc.crowding_score,
        reversal_risk_score: mc.reversal_risk_score,
        market_regime: classify_market_regime(&mc).to_string(),
        trend_phase: mc.trend_phase.clone(),
        turnover_24h: mc.turnover_24h,
        edge_bonus: best_judgment.edge_bonus,
        edge_n: best_judgment.edge_n,
        edge_bps: best_judgment.edge_bps,
        edge_status: best_judgment.edge_status,
        route_mode: best_judgment.route_mode,
        market_status: best_judgment.market_status,
        route_reason: best_judgment.route_reason,
        strategy_judgments,
        beta_proxy: bp,
        sector,
    })
}

// ─── Tests ────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::edge_estimates::EdgeEstimates;
    use crate::market_data_client::types::TickerInfo;
    use crate::scanner::config::{
        CorrelationLimits, EdgeRoutingConfig, HardFilters, MarketJudgmentConfig,
    };
    use std::collections::BTreeMap;

    fn make_ticker(
        symbol: &str,
        last_price: f64,
        bid1: f64,
        ask1: f64,
        turnover_24h: f64,
        high_24h: f64,
        low_24h: f64,
        funding_rate: f64,
        price_change_pct: f64, // as ratio (0.0077 = 0.77%)
    ) -> TickerInfo {
        TickerInfo {
            symbol: symbol.to_string(),
            last_price,
            bid1_price: bid1,
            ask1_price: ask1,
            volume_24h: 0.0,
            turnover_24h,
            high_price_24h: high_24h,
            low_price_24h: low_24h,
            prev_price_24h: last_price,
            open_interest: 0.0,
            funding_rate,
            next_funding_time: String::new(),
            price_change_24h_pct: price_change_pct,
        }
    }

    fn default_hard_filters() -> HardFilters {
        HardFilters::default()
    }

    fn make_mc(dir_pct: f64, range_pct: f64, de: f64, fr_bps: f64) -> MarketConditions {
        let signed_dir_pct = dir_pct;
        let dir_pct = dir_pct.abs();
        let signed_fr_bps = fr_bps;
        let fr_bps = fr_bps.abs();
        let range_position = if signed_dir_pct > 0.0 {
            0.75
        } else if signed_dir_pct < 0.0 {
            0.25
        } else {
            0.5
        };
        let close_alignment = if signed_dir_pct > 0.0 {
            range_position
        } else if signed_dir_pct < 0.0 {
            1.0 - range_position
        } else {
            0.5
        };
        let dir_norm = (dir_pct / 6.0).clamp(0.0, 1.0);
        let range_norm = (range_pct / 12.0).clamp(0.0, 1.0);
        let range_mid_score = (1.0 - (range_position - 0.5_f64).abs() * 2.0).clamp(0.0, 1.0);
        let trend_score = (0.45 * de + 0.35 * dir_norm + 0.20 * close_alignment).clamp(0.0, 1.0);
        let range_score =
            ((0.70 * (1.0 - de) + 0.30 * range_mid_score) * range_norm).clamp(0.0, 1.0);
        let shock_score =
            (de * (dir_pct / 8.0).clamp(0.0, 1.0) * (0.5 + 0.5 * close_alignment)).clamp(0.0, 1.0);
        let crowding_score =
            (((fr_bps - 8.0) / 20.0).clamp(0.0, 1.0) * (0.5 + 0.5 * trend_score)).clamp(0.0, 1.0);
        let reversal_risk_score =
            (trend_score * (1.0 - close_alignment) * (dir_pct / 4.0).clamp(0.0, 1.0))
                .clamp(0.0, 1.0);
        let trend_phase = classify_trend_phase(
            trend_score,
            shock_score,
            range_score,
            crowding_score,
            reversal_risk_score,
            range_pct,
        )
        .to_string();
        MarketConditions {
            signed_dir_pct,
            dir_pct,
            range_pct,
            de,
            fr_bps,
            signed_fr_bps,
            trend_score,
            range_score,
            shock_score,
            close_alignment,
            range_position,
            crowding_score,
            reversal_risk_score,
            trend_phase,
            turnover_24h: 60_000_000.0,
        }
    }

    // ── Hard filter tests ──────────────────────────────────────────────────────

    #[test]
    fn test_hard_filter_pass() {
        let t = make_ticker(
            "SOLUSDT",
            100.0,
            99.99,
            100.01,
            60_000_000.0,
            110.0,
            90.0,
            0.0001,
            0.05,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_some());
    }

    #[test]
    fn test_hard_filter_turnover_fail() {
        let t = make_ticker(
            "SOLUSDT",
            100.0,
            99.99,
            100.01,
            10_000_000.0,
            110.0,
            90.0,
            0.0001,
            0.05,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_none());
    }

    #[test]
    fn test_context_scoring_bypasses_hard_filters_for_active_attribution() {
        let t = make_ticker(
            "SOLUSDT",
            100.0,
            99.99,
            100.01,
            10_000_000.0,
            110.0,
            90.0,
            0.0001,
            0.05,
        );
        let filters = default_hard_filters();
        assert!(score_ticker(
            &t,
            1.0,
            &EdgeEstimates::empty(),
            &filters,
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
        )
        .is_none());
        let context = score_ticker_for_context(
            &t,
            1.0,
            &EdgeEstimates::empty(),
            &filters,
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
            &ScannerStrategyPolicy::default(),
        )
        .expect("active-symbol context should still be scored");
        assert_eq!(context.symbol, "SOLUSDT");
        assert!(!context.strategy_judgments.is_empty());
    }

    #[test]
    fn test_hard_filter_spread_fail() {
        // ask - bid = 1.0, mid = 100.5, spread_bps = 1.0/100.5*10000 ≈ 99.5 bps >> 8
        let t = make_ticker(
            "SOLUSDT",
            100.0,
            100.0,
            101.0,
            60_000_000.0,
            110.0,
            90.0,
            0.0001,
            0.05,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_none());
    }

    #[test]
    fn test_hard_filter_stablecoin_fail() {
        let t = make_ticker(
            "USDCUSDT",
            1.0,
            0.9999,
            1.0001,
            60_000_000.0,
            1.001,
            0.999,
            0.0,
            0.0,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_none());
    }

    #[test]
    fn test_hard_filter_non_usdt_fail() {
        let t = make_ticker(
            "BTCETH",
            50.0,
            49.9,
            50.1,
            60_000_000.0,
            55.0,
            45.0,
            0.0001,
            0.02,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_none());
    }

    #[test]
    fn test_hard_filter_low_price_fail() {
        let mut cfg = default_hard_filters();
        cfg.min_price_usdt = 0.01;
        let t = make_ticker(
            "XYZUSDT",
            0.001,
            0.00099,
            0.00101,
            60_000_000.0,
            0.0011,
            0.0009,
            0.0001,
            0.05,
        );
        assert!(apply_hard_filters(&t, &cfg).is_none());
    }

    // ── Fitness tests ──────────────────────────────────────────────────────────

    #[test]
    fn test_fitness_ma_zero_if_low_dir_pct() {
        // dir_pct < 0.5% → F_ma = 0 (M-3 fix: threshold lowered from 1.5% to 0.5%)
        let mc = make_mc(0.3, 5.0, 0.2, 5.0);
        assert_eq!(f_ma(&mc), 0.0);
        // dir_pct at 1.0% (previously filtered by 1.5% gate) should now be non-zero
        let mc2 = MarketConditions { dir_pct: 1.0, ..mc };
        assert!(f_ma(&mc2) > 0.0, "1.0% should pass new 0.5% gate");
    }

    #[test]
    fn test_fitness_ma_nonzero_clean_trend() {
        let mc = make_mc(8.0, 8.0, 1.0, 5.0); // perfect trend / 完美趨勢
        let score = f_ma(&mc);
        assert!(score > 70.0, "clean trend should score high: {score}");
    }

    #[test]
    fn test_fitness_grid_zero_if_trending() {
        // dir_pct >= 8.0 → F_grid = 0
        let mc = make_mc(9.0, 10.0, 0.9, 5.0);
        assert_eq!(f_grid(&mc), 0.0);
    }

    #[test]
    fn test_fitness_grid_zero_if_small_range() {
        // range_pct < 3.0 → F_grid = 0
        let mc = make_mc(1.0, 2.0, 0.5, 5.0);
        assert_eq!(f_grid(&mc), 0.0);
    }

    #[test]
    fn test_fitness_bbrv_range_band_too_small() {
        let mc = make_mc(1.0, 3.0, 0.1, 5.0); // < 4.0 → 0
        assert_eq!(f_bbrv(&mc), 0.0);
    }

    #[test]
    fn test_fitness_bbrv_range_band_too_large() {
        let mc = make_mc(1.0, 25.0, 0.1, 5.0); // > 20.0 → 0
        assert_eq!(f_bbrv(&mc), 0.0);
    }

    #[test]
    fn test_fitness_bbrv_snapback_bonus() {
        // fr_bps > 15 AND dir_pct < 3 → 1.2 multiplier
        let mc = make_mc(1.0, 8.0, 0.1, 20.0);
        let without = f_bbrv(&make_mc(1.0, 8.0, 0.1, 5.0));
        let with_bonus = f_bbrv(&mc);
        assert!(
            with_bonus > without,
            "snap-back bonus should increase score: {with_bonus} vs {without}"
        );
    }

    #[test]
    fn test_fitness_bkout_zero_if_low_dir() {
        // dir_pct <= 2.0 → F_bkout = 0
        let mc = make_mc(1.5, 8.0, 0.2, 5.0);
        assert_eq!(f_bkout(&mc), 0.0);
    }

    #[test]
    fn test_fitness_bkout_penalty_failed_trend() {
        let mc_clean = make_mc(5.0, 8.0, 0.8, 5.0);
        let mut mc_failed = mc_clean.clone();
        mc_failed.close_alignment = 0.10;
        mc_failed.reversal_risk_score = 0.50;
        mc_failed.trend_phase = "failed_trend".to_string();
        let clean_score = f_bkout(&mc_clean);
        let failed_score = f_bkout(&mc_failed);
        assert!(
            failed_score < clean_score,
            "failed trend should be penalized: {failed_score} < {clean_score}"
        );
    }

    #[test]
    fn test_de_formula_clean_trend() {
        let ticker = make_ticker(
            "SOLUSDT",
            100.0,
            99.99,
            100.01,
            60_000_000.0,
            108.0,
            100.0,
            0.0001,
            0.08,
        );
        let mc = compute_market_conditions(&ticker);
        // dir_pct = 8.0, range_pct = 8.0, DE should be 1.0
        assert!((mc.de - 1.0).abs() < 0.01, "de = {}", mc.de);
    }

    #[test]
    fn test_de_formula_pure_chop() {
        let ticker = make_ticker(
            "SOLUSDT",
            100.0,
            99.99,
            100.01,
            60_000_000.0,
            110.0,
            90.0,
            0.0001,
            0.0,
        );
        let mc = compute_market_conditions(&ticker);
        assert_eq!(mc.de, 0.0, "zero net move → DE = 0");
    }

    // ── Edge bonus tests ───────────────────────────────────────────────────────

    #[test]
    fn test_edge_bonus_exploration_no_data() {
        // M-5 fix: exploration credit lowered from +5 to +2 to prevent new listings
        // from crowding out symbols with real edge data.
        // M-5 修復：探索加分從 +5 降至 +2，防止新幣擠排有真實 edge 數據的交易對。
        let estimates = EdgeEstimates::default();
        let edge = apply_edge_bonus(
            50.0,
            StrategyCategory::MaCrossover,
            "NEWCOINUSDT",
            &estimates,
            &EdgeRoutingConfig::default(),
        );
        assert_eq!(edge.n, 0);
        assert_eq!(edge.edge_status, "unexplored");
        assert_eq!(edge.route_mode, "exploration");
        assert!((edge.bonus - 2.0).abs() < 1e-10);
        assert!((edge.final_score - 52.0).abs() < 1e-10);
    }

    #[test]
    fn test_edge_bonus_caps_mature_negative_cells() {
        let estimates = EdgeEstimates::load_from_str(
            r#"{"grid_trading::DOGEUSDT":{"runtime_bps":-12.0,"n":31}}"#,
        )
        .unwrap();
        let edge = apply_edge_bonus(
            95.0,
            StrategyCategory::GridTrading,
            "DOGEUSDT",
            &estimates,
            &EdgeRoutingConfig::default(),
        );
        assert_eq!(edge.n, 31);
        assert_eq!(edge.edge_bps, Some(-12.0));
        assert_eq!(edge.edge_status, "robust_negative");
        assert_eq!(edge.route_mode, "exploration_only");
        assert!((edge.final_score - 35.0).abs() < 1e-10);
    }

    #[test]
    fn test_edge_bonus_caps_posterior_negative_cells() {
        let estimates = EdgeEstimates::load_from_str(
            r#"{"ma_crossover::WIDEUSDT":{"runtime_bps":2.0,"n":36,"std_bps":30.0}}"#,
        )
        .unwrap();
        let cfg = EdgeRoutingConfig {
            posterior_lcb_z: 1.0,
            posterior_min_std_bps: 20.0,
            posterior_negative_lcb_threshold_bps: 0.0,
            ..EdgeRoutingConfig::default()
        };
        let edge = apply_edge_bonus(
            95.0,
            StrategyCategory::MaCrossover,
            "WIDEUSDT",
            &estimates,
            &cfg,
        );
        assert_eq!(edge.edge_status, "posterior_negative");
        assert_eq!(edge.route_mode, "exploration_only");
        assert!((edge.final_score - 35.0).abs() < 1e-10);
    }

    #[test]
    fn test_score_ticker_selects_best_judged_route_not_raw_regime_mismatch() {
        let ticker = make_ticker(
            "RANGEBOOMUSDT",
            100.0,
            99.99,
            100.01,
            80_000_000.0,
            110.0,
            90.0,
            0.0001,
            0.10,
        );
        let scored = score_ticker(
            &ticker,
            2.0,
            &EdgeEstimates::empty(),
            &default_hard_filters(),
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
        )
        .expect("scored symbol");
        let reversion = scored
            .strategy_judgments
            .get("bb_reversion")
            .expect("bb_reversion judgment");

        assert_eq!(reversion.route_mode, "market_gate");
        assert_ne!(scored.best_strategy, StrategyCategory::BbReversion);
        assert!(
            scored.final_score > reversion.final_score,
            "scanner should select the compatible judged route, scored={} reversion={}",
            scored.final_score,
            reversion.final_score
        );
    }

    #[test]
    fn test_score_ticker_can_select_funding_arb_as_fifth_route() {
        let ticker = make_ticker(
            "FUNDUSDT",
            100.0,
            99.99,
            100.01,
            80_000_000.0,
            102.0,
            98.0,
            0.0030,
            0.0,
        );
        let scored = score_ticker(
            &ticker,
            0.2,
            &EdgeEstimates::empty(),
            &default_hard_filters(),
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
        )
        .expect("scored symbol");

        assert_eq!(scored.best_strategy, StrategyCategory::FundingArb);
        assert!(scored.f_funding_arb > scored.f_grid);
        assert!(scored.strategy_judgments.contains_key("funding_arb"));
    }

    #[test]
    fn test_score_ticker_emits_opportunity_shadow_for_each_strategy_judgment() {
        let ticker = make_ticker(
            "OPPUSDT",
            100.0,
            99.99,
            100.01,
            120_000_000.0,
            106.0,
            96.0,
            0.0001,
            0.03,
        );
        let scored = score_ticker(
            &ticker,
            2.0,
            &EdgeEstimates::empty(),
            &default_hard_filters(),
            &EdgeRoutingConfig::default(),
            &MarketJudgmentConfig::default(),
        )
        .expect("scored symbol");

        assert_eq!(scored.strategy_judgments.len(), 5);
        for judgment in scored.strategy_judgments.values() {
            let opportunity = judgment
                .opportunity
                .as_ref()
                .expect("scanner opportunity shadow must be emitted");
            assert!(opportunity.opportunity_score.is_finite());
            assert!(opportunity.components.data_quality_score >= 0.0);
            assert!(opportunity.components.data_quality_score <= 1.0);
            assert!(opportunity.components.expected_execution_cost_bps.unwrap() > 0.0);
        }
    }

    // ── beta_proxy tests ───────────────────────────────────────────────────────

    #[test]
    fn test_beta_proxy_btc_zero() {
        assert_eq!(beta_proxy(5.0, 0.0, 0.3), None);
    }

    #[test]
    fn test_beta_proxy_btc_barely_moves() {
        // |btc_change| = 0.2 < 0.3 threshold → None
        assert_eq!(beta_proxy(3.0, 0.2, 0.3), None);
    }

    #[test]
    fn test_beta_proxy_normal() {
        let bp = beta_proxy(4.0, 2.0, 0.3).unwrap();
        assert!((bp - 2.0).abs() < 1e-10);
    }

    #[test]
    fn test_beta_proxy_clamped_high() {
        // 10/1 = 10, clamped to 3.0
        let bp = beta_proxy(10.0, 1.0, 0.3).unwrap();
        assert!((bp - 3.0).abs() < 1e-10);
    }

    #[test]
    fn test_beta_proxy_clamped_low() {
        // -2/1 = -2, clamped to -0.5
        let bp = beta_proxy(-2.0, 1.0, 0.3).unwrap();
        assert!((bp + 0.5).abs() < 1e-10);
    }

    fn test_candidate(
        symbol: &str,
        final_score: f64,
        raw_score: f64,
        best_strategy: StrategyCategory,
        beta_proxy: Option<f64>,
        sector: &str,
    ) -> ScoredSymbol {
        let strategy_key = best_strategy.as_estimate_key().to_string();
        let mut strategy_judgments = BTreeMap::new();
        strategy_judgments.insert(
            strategy_key.clone(),
            StrategyRouteJudgment {
                strategy: strategy_key,
                fitness_score: raw_score,
                final_score,
                edge_bps: None,
                edge_bonus: final_score - raw_score,
                edge_n: 0,
                edge_status: "unexplored".to_string(),
                route_mode: "exploration".to_string(),
                market_status: "compatible".to_string(),
                route_reason: "test".to_string(),
                opportunity: None,
            },
        );
        ScoredSymbol {
            symbol: symbol.to_string(),
            final_score,
            raw_score,
            best_strategy,
            f_ma: if best_strategy == StrategyCategory::MaCrossover {
                raw_score
            } else {
                0.0
            },
            f_grid: if best_strategy == StrategyCategory::GridTrading {
                raw_score
            } else {
                0.0
            },
            f_bbrv: if best_strategy == StrategyCategory::BbReversion {
                raw_score
            } else {
                0.0
            },
            f_bkout: if best_strategy == StrategyCategory::BbBreakout {
                raw_score
            } else {
                0.0
            },
            f_funding_arb: if best_strategy == StrategyCategory::FundingArb {
                raw_score
            } else {
                0.0
            },
            de: 0.2,
            dir_pct: 2.0,
            range_pct: 8.0,
            fr_bps: 5.0,
            signed_dir_pct: 2.0,
            trend_score: 0.25,
            range_score: 0.5,
            shock_score: 0.05,
            close_alignment: 0.60,
            range_position: 0.60,
            crowding_score: 0.0,
            reversal_risk_score: 0.0,
            market_regime: "range_bound".to_string(),
            trend_phase: "range_bound".to_string(),
            turnover_24h: 60_000_000.0,
            edge_bonus: final_score - raw_score,
            edge_n: 0,
            edge_bps: None,
            edge_status: "unexplored".to_string(),
            route_mode: "exploration".to_string(),
            market_status: "compatible".to_string(),
            route_reason: "test".to_string(),
            strategy_judgments,
            beta_proxy,
            sector: sector.to_string(),
        }
    }

    // ── Correlation filter tests ───────────────────────────────────────────────

    #[test]
    fn test_correlation_cap_per_sector() {
        let config = CorrelationLimits {
            max_per_sector: 2,
            ..CorrelationLimits::default()
        };
        // Create 3 candidates all in "meme" sector
        let candidates: Vec<ScoredSymbol> = vec!["DOGEUSDT", "SHIBUSDT", "PEPEUSDT"]
            .into_iter()
            .map(|sym| {
                test_candidate(
                    sym,
                    80.0,
                    75.0,
                    StrategyCategory::GridTrading,
                    Some(0.5),
                    "meme",
                )
            })
            .collect();

        let selected = apply_correlation_filter(candidates, &[], 10, &config);
        assert_eq!(
            selected.len(),
            2,
            "sector cap should limit to 2 meme symbols"
        );
    }

    #[test]
    fn test_correlation_cap_max_slots() {
        let config = CorrelationLimits::default();
        let candidates: Vec<ScoredSymbol> = (0..15)
            .map(|i| {
                test_candidate(
                    &format!("COIN{i}USDT"),
                    80.0 - i as f64,
                    75.0,
                    StrategyCategory::GridTrading,
                    Some(0.5),
                    &format!("sector_{}", i % 5),
                )
            })
            .collect();

        // max 5 dynamic slots
        let selected = apply_correlation_filter(candidates, &[], 5, &config);
        assert!(selected.len() <= 5, "should not exceed max_dynamic_slots");
    }

    #[test]
    fn test_pinned_skipped_in_filter() {
        let config = CorrelationLimits::default();
        let pinned = vec!["BTCUSDT".to_string()];
        let candidates = vec![
            test_candidate(
                "BTCUSDT",
                99.0,
                94.0,
                StrategyCategory::MaCrossover,
                Some(1.0),
                "l1_infra",
            ),
            test_candidate(
                "SOLUSDT",
                80.0,
                75.0,
                StrategyCategory::MaCrossover,
                Some(1.2),
                "l1_infra",
            ),
        ];

        let selected = apply_correlation_filter(candidates, &pinned, 5, &config);
        // BTC should not appear in dynamic selection (it's pinned)
        assert!(!selected.iter().any(|s| s.symbol == "BTCUSDT"));
        assert!(selected.iter().any(|s| s.symbol == "SOLUSDT"));
    }
}
