//! Market scanner scoring engine — per-strategy fitness + edge feedback + correlation filter.
//! 市場掃描器評分引擎 — 分策略適配評分 + 邊際反饋 + 相關性過濾。
//!
//! MODULE_NOTE (EN): All functions are pure (no async, no I/O, no global state).
//!   The four fitness functions (F_ma, F_grid, F_bbrv, F_bkout) model different
//!   optimal market regimes. `apply_correlation_filter` greedily selects the top-N
//!   symbols while enforcing BTC-beta, per-strategy, and per-sector caps.
//!   See SCANNER_TODO.md §評分框架 for the full formula derivation.
//! MODULE_NOTE (中): 所有函數為純函數（無異步、無 I/O、無全局狀態）。
//!   四個適配評分函數（F_ma、F_grid、F_bbrv、F_bkout）建模不同的最優市場環境。
//!   `apply_correlation_filter` 貪心選擇前 N 個交易對，同時執行 BTC-beta、
//!   每策略和每板塊上限。完整公式推導見 SCANNER_TODO.md §評分框架。

use crate::edge_estimates::EdgeEstimates;
use crate::market_data_client::types::TickerInfo;
use crate::scanner::config::{CorrelationLimits, HardFilters};
use crate::scanner::sectors::{base_from_usdt_symbol, symbol_sector, STABLECOIN_BASES};
use crate::scanner::types::{ScoredSymbol, StrategyCategory};
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
    /// Net directional move % (absolute value) / 淨方向移動百分比（絕對值）
    pub dir_pct: f64,
    /// 24h total range % = (high - low) / price * 100 / 24h 總 range 百分比
    pub range_pct: f64,
    /// Directional efficiency = dir_pct / range_pct ∈ [0, 1] / 方向效率
    pub de: f64,
    /// Funding rate absolute value in bps / 資金費率絕對值（基點）
    pub fr_bps: f64,
    /// 24h turnover / 24h 成交額
    pub turnover_24h: f64,
}

/// Compute market condition intermediates from a TickerInfo.
/// 從 TickerInfo 計算市場條件中間值。
pub fn compute_market_conditions(ticker: &TickerInfo) -> MarketConditions {
    // Bybit price24hPcnt is a ratio (e.g. 0.0077 = 0.77%), convert to %
    // Bybit price24hPcnt 是比率（例如 0.0077 = 0.77%），轉換為百分比
    let dir_pct = (ticker.price_change_24h_pct * 100.0).abs();

    let price = ticker.last_price.max(1e-12);
    let range_pct = ((ticker.high_price_24h - ticker.low_price_24h) / price * 100.0).max(0.0);

    let de = if range_pct > 0.0 {
        (dir_pct / range_pct).clamp(0.0, 1.0)
    } else {
        0.0
    };

    let fr_bps = (ticker.funding_rate * 10_000.0).abs();

    MarketConditions {
        dir_pct,
        range_pct,
        de,
        fr_bps,
        turnover_24h: ticker.turnover_24h,
    }
}

// ─── Per-strategy fitness functions ───────────────────────────────────────────

/// F_ma: MA crossover fitness score [0, 100].
/// Rewards directional efficiency and magnitude. Penalizes crowded funding rates.
/// Zero if dir_pct < 1.5% (no meaningful trend).
/// F_ma：MA 交叉適配分 [0, 100]。
/// 獎勵方向效率和幅度。懲罰擁擠的資金費率。
/// 若 dir_pct < 1.5%（無有意義趨勢）則為零。
pub fn f_ma(mc: &MarketConditions) -> f64 {
    if mc.dir_pct < 1.5 {
        return 0.0;
    }
    let base = 100.0 * mc.de * (mc.dir_pct / 10.0).clamp(0.0, 1.0);
    let crowd = ((mc.fr_bps - 10.0) * 2.0).clamp(0.0, 30.0);
    (base - crowd).max(0.0)
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
    let usable_range = mc.range_pct.min(15.0);
    let dir_mult = if mc.dir_pct >= 3.0 { 0.5 } else { 1.0 };
    let base = (usable_range / 15.0) * 100.0 * (1.0 - mc.de) * dir_mult;
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
    let base = (1.0 - mc.de) * (mc.range_pct * 8.0).min(100.0);
    // Snap-back bonus: extreme funding + low net move = likely reversal setup
    // 回彈加成：極端資金費率 + 低淨移動 = 可能的反轉設置
    let bonus_multiplier = if mc.fr_bps > 15.0 && mc.dir_pct < 3.0 {
        1.2
    } else {
        1.0
    };
    (base * bonus_multiplier).min(100.0)
}

/// F_bkout: BB breakout fitness score [0, 100].
/// Approximates post-squeeze breakout using directional efficiency + range.
/// NOTE: This is a proxy — real BB bandwidth requires kline data (future improvement).
/// Penalizes overcrowded funding rate (> 20 bps), which signals exhaustion not breakout.
/// Additional penalty when DE > 0.7 (already in strong trend, not a breakout candidate).
/// F_bkout：BB 突破適配分 [0, 100]。
/// 使用方向效率 + range 近似擠壓後的突破。
/// 注意：這是代理指標 — 真實 BB 帶寬需要 K 線數據（未來改進路徑）。
/// 懲罰過度擁擠的資金費率（> 20 bps），這表示耗盡而非突破。
/// 當 DE > 0.7 時額外懲罰（已處於強趨勢中，不是突破候選）。
pub fn f_bkout(mc: &MarketConditions) -> f64 {
    if mc.range_pct < 3.0 || mc.range_pct > 20.0 || mc.dir_pct <= 2.0 {
        return 0.0;
    }
    let base = mc.de * 100.0 * (mc.dir_pct / 8.0).clamp(0.0, 1.0);
    // Crowded funding → exhaustion, not breakout / 擁擠資金費率 → 耗盡，非突破
    let funding_penalty = if mc.fr_bps > 20.0 { 25.0 } else { 0.0 };
    // Already in strong trend → not a squeeze candidate / 已在強趨勢中 → 非擠壓候選
    let trend_penalty = if mc.de > 0.7 { 20.0 } else { 0.0 };
    (base - funding_penalty - trend_penalty).max(0.0)
}

// ─── Full fitness bundle ───────────────────────────────────────────────────────

/// All four strategy fitness scores for one symbol.
/// 一個交易對的四個策略適配分。
#[derive(Debug, Clone)]
pub struct FitnessScores {
    pub f_ma: f64,
    pub f_grid: f64,
    pub f_bbrv: f64,
    pub f_bkout: f64,
    pub raw: f64,
    pub best: StrategyCategory,
}

/// Compute all four fitness scores and identify the best strategy.
/// 計算所有四個適配分並確定最佳策略。
pub fn compute_fitness(mc: &MarketConditions) -> FitnessScores {
    let scores = [
        (f_ma(mc), StrategyCategory::MaCrossover),
        (f_grid(mc), StrategyCategory::GridTrading),
        (f_bbrv(mc), StrategyCategory::BbReversion),
        (f_bkout(mc), StrategyCategory::BbBreakout),
    ];
    let (raw, best) = scores
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
        raw,
        best,
    }
}

// ─── Edge feedback ────────────────────────────────────────────────────────────

/// Apply edge bonus from JS shrinkage estimates.
/// Returns (bonus, edge_n).
/// - If estimate exists: bonus = clamp(shrunk_bps * 0.5, -30, 10), n = 1 (present)
/// - If not yet explored: bonus = +5.0 exploration credit, n = 0
/// 從 JS 收縮估計施加邊際獎勵。返回 (bonus, edge_n)。
/// - 若估計存在：bonus = clamp(shrunk_bps * 0.5, -30, 10)，n = 1（存在）
/// - 若尚未探索：bonus = +5.0 探索加分，n = 0
pub fn apply_edge_bonus(
    raw: f64,
    best_strategy: StrategyCategory,
    symbol: &str,
    estimates: &EdgeEstimates,
) -> (f64, f64, u32) {
    let strategy_key = best_strategy.as_estimate_key();
    match estimates.get(strategy_key, symbol) {
        Some(shrunk_bps) => {
            let bonus = (shrunk_bps * 0.5).clamp(-30.0, 10.0);
            let final_score = (raw + bonus).clamp(0.0, 100.0);
            (final_score, bonus, 1)
        }
        None => {
            // Unexplored symbol — give exploration credit / 未探索交易對 — 給予探索加分
            let final_score = (raw + 5.0).clamp(0.0, 100.0);
            (final_score, 5.0, 0)
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
        let sector_count = sector_counts
            .entry(candidate.sector.clone())
            .or_insert(0);
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
) -> Option<ScoredSymbol> {
    // Apply hard filters first / 首先應用硬過濾器
    apply_hard_filters(ticker, hard_filter_config)?;

    let base = base_from_usdt_symbol(&ticker.symbol).unwrap_or("");
    let sector = symbol_sector(base).to_string();

    let mc = compute_market_conditions(ticker);
    let fitness = compute_fitness(&mc);
    let (final_score, edge_bonus, edge_n) =
        apply_edge_bonus(fitness.raw, fitness.best, &ticker.symbol, estimates);

    // BTC change_pct already in percentage points (dir_pct * 100 from ticker)
    // Bybit's price24hPcnt is a ratio; mc.dir_pct is already in %, so we need
    // the raw pct (with sign) for beta proxy
    let symbol_change_pct = ticker.price_change_24h_pct * 100.0;
    let bp = beta_proxy(symbol_change_pct, btc_change_pct, hard_filter_config.btc_min_move_pct);

    Some(ScoredSymbol {
        symbol: ticker.symbol.clone(),
        final_score,
        raw_score: fitness.raw,
        best_strategy: fitness.best,
        f_ma: fitness.f_ma,
        f_grid: fitness.f_grid,
        f_bbrv: fitness.f_bbrv,
        f_bkout: fitness.f_bkout,
        de: mc.de,
        dir_pct: mc.dir_pct,
        range_pct: mc.range_pct,
        fr_bps: mc.fr_bps,
        turnover_24h: mc.turnover_24h,
        edge_bonus,
        edge_n,
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
    use crate::scanner::config::{CorrelationLimits, HardFilters};

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

    // ── Hard filter tests ──────────────────────────────────────────────────────

    #[test]
    fn test_hard_filter_pass() {
        let t = make_ticker(
            "SOLUSDT", 100.0, 99.99, 100.01, 60_000_000.0, 110.0, 90.0, 0.0001, 0.05,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_some());
    }

    #[test]
    fn test_hard_filter_turnover_fail() {
        let t = make_ticker(
            "SOLUSDT", 100.0, 99.99, 100.01, 10_000_000.0, 110.0, 90.0, 0.0001, 0.05,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_none());
    }

    #[test]
    fn test_hard_filter_spread_fail() {
        // ask - bid = 1.0, mid = 100.5, spread_bps = 1.0/100.5*10000 ≈ 99.5 bps >> 8
        let t = make_ticker(
            "SOLUSDT", 100.0, 100.0, 101.0, 60_000_000.0, 110.0, 90.0, 0.0001, 0.05,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_none());
    }

    #[test]
    fn test_hard_filter_stablecoin_fail() {
        let t = make_ticker(
            "USDCUSDT", 1.0, 0.9999, 1.0001, 60_000_000.0, 1.001, 0.999, 0.0, 0.0,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_none());
    }

    #[test]
    fn test_hard_filter_non_usdt_fail() {
        let t = make_ticker(
            "BTCETH", 50.0, 49.9, 50.1, 60_000_000.0, 55.0, 45.0, 0.0001, 0.02,
        );
        assert!(apply_hard_filters(&t, &default_hard_filters()).is_none());
    }

    #[test]
    fn test_hard_filter_low_price_fail() {
        let mut cfg = default_hard_filters();
        cfg.min_price_usdt = 0.01;
        let t = make_ticker(
            "XYZUSDT", 0.001, 0.00099, 0.00101, 60_000_000.0, 0.0011, 0.0009, 0.0001, 0.05,
        );
        assert!(apply_hard_filters(&t, &cfg).is_none());
    }

    // ── Fitness tests ──────────────────────────────────────────────────────────

    #[test]
    fn test_fitness_ma_zero_if_low_dir_pct() {
        // dir_pct < 1.5% → F_ma = 0
        let mc = MarketConditions {
            dir_pct: 1.0,
            range_pct: 5.0,
            de: 0.2,
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        assert_eq!(f_ma(&mc), 0.0);
    }

    #[test]
    fn test_fitness_ma_nonzero_clean_trend() {
        let mc = MarketConditions {
            dir_pct: 8.0,
            range_pct: 8.0,
            de: 1.0, // perfect trend / 完美趨勢
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        let score = f_ma(&mc);
        assert!(score > 70.0, "clean trend should score high: {score}");
    }

    #[test]
    fn test_fitness_grid_zero_if_trending() {
        // dir_pct >= 8.0 → F_grid = 0
        let mc = MarketConditions {
            dir_pct: 9.0,
            range_pct: 10.0,
            de: 0.9,
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        assert_eq!(f_grid(&mc), 0.0);
    }

    #[test]
    fn test_fitness_grid_zero_if_small_range() {
        // range_pct < 3.0 → F_grid = 0
        let mc = MarketConditions {
            dir_pct: 1.0,
            range_pct: 2.0,
            de: 0.5,
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        assert_eq!(f_grid(&mc), 0.0);
    }

    #[test]
    fn test_fitness_bbrv_range_band_too_small() {
        let mc = MarketConditions {
            dir_pct: 1.0,
            range_pct: 3.0, // < 4.0 → 0
            de: 0.1,
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        assert_eq!(f_bbrv(&mc), 0.0);
    }

    #[test]
    fn test_fitness_bbrv_range_band_too_large() {
        let mc = MarketConditions {
            dir_pct: 1.0,
            range_pct: 25.0, // > 20.0 → 0
            de: 0.1,
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        assert_eq!(f_bbrv(&mc), 0.0);
    }

    #[test]
    fn test_fitness_bbrv_snapback_bonus() {
        // fr_bps > 15 AND dir_pct < 3 → 1.2 multiplier
        let mc = MarketConditions {
            dir_pct: 1.0,
            range_pct: 8.0,
            de: 0.1,
            fr_bps: 20.0,
            turnover_24h: 60_000_000.0,
        };
        let without = (1.0 - 0.1) * (8.0_f64 * 8.0).min(100.0);
        let with_bonus = f_bbrv(&mc);
        assert!(
            with_bonus > without,
            "snap-back bonus should increase score: {with_bonus} vs {without}"
        );
    }

    #[test]
    fn test_fitness_bkout_zero_if_low_dir() {
        // dir_pct <= 2.0 → F_bkout = 0
        let mc = MarketConditions {
            dir_pct: 1.5,
            range_pct: 8.0,
            de: 0.2,
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        assert_eq!(f_bkout(&mc), 0.0);
    }

    #[test]
    fn test_fitness_bkout_penalty_high_de() {
        // DE > 0.7 → penalty applies; compare with low-DE score
        let mc_high_de = MarketConditions {
            dir_pct: 5.0,
            range_pct: 8.0,
            de: 0.8,
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        let mc_low_de = MarketConditions {
            dir_pct: 5.0,
            range_pct: 8.0,
            de: 0.5,
            fr_bps: 5.0,
            turnover_24h: 60_000_000.0,
        };
        let high_de_score = f_bkout(&mc_high_de);
        let low_de_score = f_bkout(&mc_low_de);
        assert!(
            high_de_score < low_de_score,
            "high DE should be penalized: {high_de_score} < {low_de_score}"
        );
    }

    #[test]
    fn test_de_formula_clean_trend() {
        let ticker = make_ticker(
            "SOLUSDT", 100.0, 99.99, 100.01, 60_000_000.0, 108.0, 100.0, 0.0001, 0.08,
        );
        let mc = compute_market_conditions(&ticker);
        // dir_pct = 8.0, range_pct = 8.0, DE should be 1.0
        assert!((mc.de - 1.0).abs() < 0.01, "de = {}", mc.de);
    }

    #[test]
    fn test_de_formula_pure_chop() {
        let ticker = make_ticker(
            "SOLUSDT", 100.0, 99.99, 100.01, 60_000_000.0, 110.0, 90.0, 0.0001, 0.0,
        );
        let mc = compute_market_conditions(&ticker);
        assert_eq!(mc.de, 0.0, "zero net move → DE = 0");
    }

    // ── Edge bonus tests ───────────────────────────────────────────────────────

    #[test]
    fn test_edge_bonus_exploration_no_data() {
        let estimates = EdgeEstimates::default();
        let (final_score, bonus, n) = apply_edge_bonus(
            50.0,
            StrategyCategory::MaCrossover,
            "NEWCOINUSDT",
            &estimates,
        );
        assert_eq!(n, 0);
        assert!((bonus - 5.0).abs() < 1e-10);
        assert!((final_score - 55.0).abs() < 1e-10);
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
            .map(|sym| ScoredSymbol {
                symbol: sym.to_string(),
                final_score: 80.0,
                raw_score: 75.0,
                best_strategy: StrategyCategory::GridTrading,
                f_ma: 0.0,
                f_grid: 75.0,
                f_bbrv: 0.0,
                f_bkout: 0.0,
                de: 0.1,
                dir_pct: 2.0,
                range_pct: 8.0,
                fr_bps: 5.0,
                turnover_24h: 60_000_000.0,
                edge_bonus: 5.0,
                edge_n: 0,
                beta_proxy: Some(0.5),
                sector: "meme".to_string(),
            })
            .collect();

        let selected = apply_correlation_filter(candidates, &[], 10, &config);
        assert_eq!(selected.len(), 2, "sector cap should limit to 2 meme symbols");
    }

    #[test]
    fn test_correlation_cap_max_slots() {
        let config = CorrelationLimits::default();
        let candidates: Vec<ScoredSymbol> = (0..15)
            .map(|i| ScoredSymbol {
                symbol: format!("COIN{i}USDT"),
                final_score: 80.0 - i as f64,
                raw_score: 75.0,
                best_strategy: StrategyCategory::GridTrading,
                f_ma: 0.0,
                f_grid: 75.0,
                f_bbrv: 0.0,
                f_bkout: 0.0,
                de: 0.1,
                dir_pct: 2.0,
                range_pct: 8.0,
                fr_bps: 5.0,
                turnover_24h: 60_000_000.0,
                edge_bonus: 5.0,
                edge_n: 0,
                beta_proxy: Some(0.5),
                sector: format!("sector_{}", i % 5),
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
            ScoredSymbol {
                symbol: "BTCUSDT".to_string(),
                final_score: 99.0,
                raw_score: 94.0,
                best_strategy: StrategyCategory::MaCrossover,
                f_ma: 94.0,
                f_grid: 0.0,
                f_bbrv: 0.0,
                f_bkout: 0.0,
                de: 0.9,
                dir_pct: 8.0,
                range_pct: 9.0,
                fr_bps: 3.0,
                turnover_24h: 1_000_000_000.0,
                edge_bonus: 5.0,
                edge_n: 0,
                beta_proxy: Some(1.0),
                sector: "l1_infra".to_string(),
            },
            ScoredSymbol {
                symbol: "SOLUSDT".to_string(),
                final_score: 80.0,
                raw_score: 75.0,
                best_strategy: StrategyCategory::MaCrossover,
                f_ma: 75.0,
                f_grid: 0.0,
                f_bbrv: 0.0,
                f_bkout: 0.0,
                de: 0.8,
                dir_pct: 6.0,
                range_pct: 7.5,
                fr_bps: 5.0,
                turnover_24h: 200_000_000.0,
                edge_bonus: 5.0,
                edge_n: 0,
                beta_proxy: Some(1.2),
                sector: "l1_infra".to_string(),
            },
        ];

        let selected = apply_correlation_filter(candidates, &pinned, 5, &config);
        // BTC should not appear in dynamic selection (it's pinned)
        assert!(!selected.iter().any(|s| s.symbol == "BTCUSDT"));
        assert!(selected.iter().any(|s| s.symbol == "SOLUSDT"));
    }
}
