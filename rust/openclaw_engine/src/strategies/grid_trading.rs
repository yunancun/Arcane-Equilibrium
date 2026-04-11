//! Grid Trading Strategy V2 — OU dynamic spacing + fee floor + geometric mode + health check.
//! 網格交易策略 V2 — OU 動態間距 + 手續費地板 + 幾何模式 + 健康檢查。
//!
//! MODULE_NOTE (EN): Grid levels between lower/upper bounds. Buy on down-cross,
//!   sell on up-cross. OU model: optimal spacing = σ·√(2/θ) with floor = 2× round-trip fee.
//!   Geometric mode: equal ratio gaps (better for crypto). Inventory drift health check.
//! MODULE_NOTE (中): 在上下界之間設置網格。下穿買入，上穿賣出。
//!   OU 模型：最佳間距 = σ·√(2/θ)，地板 = 2× 來回手續費。
//!   幾何模式：等比間距（更適合加密貨幣）。含庫存漂移健康檢查。

use std::collections::HashMap;

use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use serde::{Deserialize, Serialize};
use tracing::info;

/// Tunable parameters for Grid Trading (Phase 3a).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct GridTradingParams {
    pub cooldown_ms: u64,
    pub qty_per_grid: f64,
    pub max_inventory: f64,
    pub ou_lookback: usize,
    pub health_check_interval: usize,
    pub max_out_of_range: usize,
}

impl Default for GridTradingParams {
    fn default() -> Self {
        Self {
            cooldown_ms: 120_000,
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            max_inventory: 5.0,
            ou_lookback: 60,
            health_check_interval: 100,
            max_out_of_range: 5,
        }
    }
}

impl StrategyParams for GridTradingParams {
    fn param_ranges() -> Vec<ParamRange> {
        vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 30_000.0,
                max: 600_000.0,
                step: Some(30_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "qty_per_grid".into(),
                min: 0.001,
                max: 1e12,
                step: None,
                agent_adjustable: false,
                db_persisted: true,
            },
            ParamRange {
                name: "max_inventory".into(),
                min: 1.0,
                max: 20.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "ou_lookback".into(),
                min: 20.0,
                max: 200.0,
                step: Some(10.0),
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.max_inventory < 1.0 {
            return Err("max_inventory must be >= 1".into());
        }
        if self.ou_lookback < 10 {
            return Err("ou_lookback must be >= 10".into());
        }
        Ok(())
    }
}
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::IndicatorSnapshot;

/// Dynamic grid confidence: ranging regime + narrow BB → high; trending → low.
/// 動態網格信心：ranging regime + 窄 BB → 高；trending → 低。
fn compute_grid_confidence(snap: &Option<IndicatorSnapshot>) -> f64 {
    let base = 0.5_f64;
    let Some(ind) = snap.as_ref() else {
        return base;
    };
    let regime_bonus = match ind.hurst.as_ref().map(|h| h.regime.as_str()) {
        Some("mean_reverting") => 0.20,
        Some("random_walk") => 0.05,
        Some("trending") => -0.20,
        _ => 0.0,
    };
    let bw_bonus = match ind.bollinger.as_ref() {
        Some(b) if b.bandwidth < 0.02 => 0.10,
        Some(b) if b.bandwidth > 0.05 => -0.10,
        _ => 0.0,
    };
    (base + regime_bonus + bw_bonus).clamp(0.2, 0.85)
}

const DEFAULT_GRID_COUNT: usize = 10;
/// Large default qty — intent_processor P1 sizing will cap to actual risk budget.
/// 大默認 qty — intent_processor P1 sizing 會裁剪到實際風險預算。
const DEFAULT_QTY_PER_GRID: f64 = 1e9;
const FEE_PCT: f64 = 0.00055; // one-way taker
/// Default adaptive range: ±10% of current price for initial/rebalance grid.
/// 默認自適應範圍：當前價格 ±10% 用於初始化/再平衡網格。
const ADAPTIVE_RANGE_PCT: f64 = 0.10;

/// Grid spacing mode: linear (equal dollar) or geometric (equal ratio).
/// 網格間距模式：線性（等差）或幾何（等比）。
#[derive(Debug, Clone, PartialEq)]
pub enum GridSpacingMode {
    /// Equal dollar spacing between levels (arithmetic progression).
    /// 等差間距：各層級之間價差相等。
    Linear,
    /// Equal ratio spacing between levels (geometric progression).
    /// 等比間距：各層級之間比率相等，更適合加密貨幣（價格按比例波動）。
    Geometric,
}

/// Grid health status returned by health check.
/// 健康檢查返回的網格狀態。
#[derive(Debug, Clone, PartialEq)]
pub enum GridHealth {
    /// Price is within grid bounds — normal operation.
    /// 價格在網格範圍內 — 正常運作。
    Healthy,
    /// Price is outside grid bounds but not yet triggering rebalance.
    /// 價格超出網格範圍，但尚未觸發再平衡。
    OutOfRange,
    /// Too many consecutive out-of-range ticks — grid needs rebalancing.
    /// 連續超出範圍次數過多 — 需要再平衡網格。
    NeedsRebalance,
}

pub struct GridTrading {
    active: bool,
    /// Template grid bounds for non-adaptive constructors (None = adaptive / ±10%).
    /// 非自適應構造函數的模板邊界（None = 自適應 / ±10%）。
    template_bounds: Option<(f64, f64)>,
    /// Per-symbol grid levels. Initialized lazily on first tick per symbol.
    /// 每幣種網格層級。每個 symbol 首次 tick 時延遲初始化。
    grid_levels: HashMap<String, Vec<f64>>,
    /// Per-symbol last crossed grid index.
    /// 每幣種最後穿越的網格索引。
    last_cross_idx: HashMap<String, usize>,
    /// Per-symbol net inventory tracking.
    /// 每幣種淨庫存追蹤。
    net_inventory: HashMap<String, f64>,
    /// Max net inventory — reserved for future Agent position sizing control (Phase 3a).
    /// 最大淨庫存 — 預留給未來 Agent 倉位管理（Phase 3a）。
    #[allow(dead_code)]
    max_inventory: f64,
    /// Per-symbol last trade timestamp for cooldown.
    /// 每幣種最後交易時間戳（用於冷卻）。
    last_trade_ms: HashMap<String, u64>,
    cooldown_ms: u64,
    qty_per_grid: f64,
    // OU parameters / OU 參數 — per-symbol price history
    price_history: HashMap<String, Vec<f64>>,
    ou_lookback: usize,
    // Spacing mode / 間距模式
    pub(crate) spacing_mode: GridSpacingMode,
    // Health check fields / 健康檢查欄位
    /// How often (in ticks) to run health check / 每隔多少 tick 執行健康檢查
    pub(crate) health_check_interval: usize,
    /// Per-symbol ticks elapsed since last health check.
    /// 每幣種距上次健康檢查已過的 tick 數。
    ticks_since_health_check: HashMap<String, usize>,
    /// Per-symbol consecutive ticks price was out of grid range.
    /// 每幣種連續價格超出網格範圍的 tick 數。
    out_of_range_count: HashMap<String, usize>,
    /// Max allowed consecutive out-of-range ticks before rebalance / 觸發再平衡前允許的最大連續超出範圍次數
    pub(crate) max_out_of_range: usize,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    prev_cross_idx: HashMap<String, Option<usize>>,
    prev_inventory: HashMap<String, f64>,
    prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    conf_scale: f64,
}

/// Build grid levels with linear (arithmetic) spacing.
/// 以線性（等差）間距建構網格層級。
fn build_linear_levels(lower: f64, upper: f64, count: usize) -> Vec<f64> {
    let mut levels = Vec::with_capacity(count);
    let step = (upper - lower) / (count as f64 - 1.0);
    for i in 0..count {
        levels.push(lower + step * i as f64);
    }
    levels
}

/// Build grid levels with geometric (ratio-based) spacing.
/// 以幾何（等比）間距建構網格層級。
/// ratio = (upper / lower)^(1/(n-1)), level[i] = lower * ratio^i
fn build_geometric_levels(lower: f64, upper: f64, count: usize) -> Vec<f64> {
    let mut levels = Vec::with_capacity(count);
    if count <= 1 || lower <= 0.0 || upper <= 0.0 {
        // Degenerate case — fall back to single level or empty.
        // 退化情況 — 回退為單層級或空。
        if count >= 1 && lower > 0.0 {
            levels.push(lower);
        }
        return levels;
    }
    let ratio = (upper / lower).powf(1.0 / (count as f64 - 1.0));
    for i in 0..count {
        levels.push(lower * ratio.powi(i as i32));
    }
    levels
}

/// Build grid levels respecting the given spacing mode.
/// 根據指定的間距模式建構網格層級。
fn build_levels(lower: f64, upper: f64, count: usize, mode: &GridSpacingMode) -> Vec<f64> {
    match mode {
        GridSpacingMode::Linear => build_linear_levels(lower, upper, count),
        GridSpacingMode::Geometric => build_geometric_levels(lower, upper, count),
    }
}

impl GridTrading {
    /// Create a grid with linear (arithmetic) spacing — original behavior.
    /// 建立線性（等差）間距網格 — 原始行為。
    /// Create a grid with linear (arithmetic) spacing — bounds stored as template.
    /// Grid levels are lazily initialized per symbol on first tick.
    /// 建立線性（等差）間距網格 — 邊界存為模板，各 symbol 首次 tick 時延遲初始化。
    pub fn new(lower: f64, upper: f64) -> Self {
        Self {
            active: true,
            template_bounds: Some((lower, upper)),
            grid_levels: HashMap::new(),
            last_cross_idx: HashMap::new(),
            net_inventory: HashMap::new(),
            max_inventory: 5.0,
            last_trade_ms: HashMap::new(),
            cooldown_ms: 60_000,
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            price_history: HashMap::new(),
            ou_lookback: 100,
            spacing_mode: GridSpacingMode::Linear,
            health_check_interval: 200,
            ticks_since_health_check: HashMap::new(),
            out_of_range_count: HashMap::new(),
            max_out_of_range: 50,
            prev_cross_idx: HashMap::new(),
            prev_inventory: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
        }
    }

    /// Create a grid with geometric (ratio-based) spacing.
    /// Not deployed in main.rs yet — available for Agent/config selection in Phase 3a.
    /// 建立幾何（等比）間距網格 — 各層級間比率相等。
    /// 尚未在 main.rs 部署 — Phase 3a 供 Agent/配置選擇使用。
    #[allow(dead_code)]
    pub fn new_geometric(lower: f64, upper: f64) -> Self {
        Self {
            active: true,
            template_bounds: Some((lower, upper)),
            grid_levels: HashMap::new(),
            last_cross_idx: HashMap::new(),
            net_inventory: HashMap::new(),
            max_inventory: 5.0,
            last_trade_ms: HashMap::new(),
            cooldown_ms: 60_000,
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            price_history: HashMap::new(),
            ou_lookback: 100,
            spacing_mode: GridSpacingMode::Geometric,
            health_check_interval: 200,
            ticks_since_health_check: HashMap::new(),
            out_of_range_count: HashMap::new(),
            max_out_of_range: 50,
            prev_cross_idx: HashMap::new(),
            prev_inventory: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
        }
    }

    /// Create a grid that auto-adapts to the first price seen (±10% initial range).
    /// OU model will refine spacing after enough ticks.
    /// 创建自适应网格：首次价格 ±10% 为初始范围，OU 模型收集数据后自动调整。
    pub fn new_adaptive() -> Self {
        Self::new_adaptive_with_mode(GridSpacingMode::Linear)
    }

    /// Create an adaptive grid with geometric spacing (Phase 3a — not yet deployed).
    /// 建立幾何間距的自適應網格（Phase 3a — 尚未部署）。
    #[allow(dead_code)]
    pub fn new_adaptive_geometric() -> Self {
        Self::new_adaptive_with_mode(GridSpacingMode::Geometric)
    }

    /// Create an adaptive grid with the specified spacing mode (Phase 3a — not yet deployed).
    /// 以指定的間距模式建立自適應網格（Phase 3a — 尚未部署）。
    #[allow(dead_code)]
    pub fn new_adaptive_with_mode(mode: GridSpacingMode) -> Self {
        // Start with empty grids per symbol; each symbol's first tick will initialize its grid.
        // 各 symbol 空白起始；每個 symbol 首次 tick 時初始化自己的網格。
        Self {
            active: true,
            template_bounds: None,
            grid_levels: HashMap::new(),
            last_cross_idx: HashMap::new(),
            net_inventory: HashMap::new(),
            max_inventory: 5.0,
            last_trade_ms: HashMap::new(),
            cooldown_ms: 60_000,
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            price_history: HashMap::new(),
            ou_lookback: 100,
            spacing_mode: mode,
            health_check_interval: 200,
            ticks_since_health_check: HashMap::new(),
            out_of_range_count: HashMap::new(),
            max_out_of_range: 50,
            prev_cross_idx: HashMap::new(),
            prev_inventory: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
        }
    }

    /// Find nearest grid level index for a price in a given symbol's grid.
    /// 找到指定幣種網格中價格最近的等級索引。
    fn nearest_grid_idx(&self, symbol: &str, price: f64) -> usize {
        let levels = match self.grid_levels.get(symbol) {
            Some(l) => l,
            None => return 0,
        };
        let mut best = 0;
        let mut best_dist = f64::MAX;
        for (i, &level) in levels.iter().enumerate() {
            let d = (price - level).abs();
            if d < best_dist {
                best_dist = d;
                best = i;
            }
        }
        best
    }

    /// Check grid health for a symbol: is price within bounds? Should we rebalance?
    /// 檢查指定幣種的網格健康：價格是否在範圍內？是否需要再平衡？
    pub fn check_health(&mut self, symbol: &str, price: f64) -> GridHealth {
        let levels = match self.grid_levels.get(symbol) {
            Some(l) if !l.is_empty() => l,
            _ => return GridHealth::Healthy,
        };
        let lo = levels[0];
        let hi = levels[levels.len() - 1];

        if price < lo || price > hi {
            let count = self.out_of_range_count.entry(symbol.to_string()).or_insert(0);
            *count += 1;
            if *count >= self.max_out_of_range {
                GridHealth::NeedsRebalance
            } else {
                GridHealth::OutOfRange
            }
        } else {
            // Price back in range — reset counter / 價格回到範圍 — 重置計數器
            self.out_of_range_count.insert(symbol.to_string(), 0);
            GridHealth::Healthy
        }
    }

    /// Rebalance the grid centered on the given price.
    /// If OU has enough data, use OU-derived spacing; otherwise ±10% range.
    /// Respects current spacing_mode (Linear or Geometric).
    /// 以指定價格為中心重建網格。
    /// 若 OU 有足夠數據則使用 OU 間距；否則 ±10% 範圍。
    /// 遵循當前 spacing_mode。
    fn rebalance(&mut self, symbol: &str, price: f64) {
        let history = self.price_history.get(symbol);
        let (lower, upper) = if history.map(|h| h.len()).unwrap_or(0) >= 20 {
            // Use OU-derived step to compute bounds / 用 OU 推導的步長計算邊界
            let ou_step = self.compute_ou_step(symbol);
            if let Some(step) = ou_step {
                let lo = price - step * (DEFAULT_GRID_COUNT as f64 / 2.0);
                let hi = price + step * (DEFAULT_GRID_COUNT as f64 / 2.0);
                // For geometric mode, ensure lower > 0
                // 幾何模式需確保下界 > 0
                (lo.max(price * 0.01), hi)
            } else {
                (
                    price * (1.0 - ADAPTIVE_RANGE_PCT),
                    price * (1.0 + ADAPTIVE_RANGE_PCT),
                )
            }
        } else {
            (
                price * (1.0 - ADAPTIVE_RANGE_PCT),
                price * (1.0 + ADAPTIVE_RANGE_PCT),
            )
        };

        self.grid_levels.insert(symbol.to_string(), build_levels(lower, upper, DEFAULT_GRID_COUNT, &self.spacing_mode));
        self.out_of_range_count.insert(symbol.to_string(), 0);
        self.last_cross_idx.remove(symbol);
    }

    /// Compute OU-derived optimal step size for a symbol (without rebuilding the grid).
    /// Returns None if data is insufficient or parameters are degenerate.
    /// 計算指定幣種的 OU 推導最佳步長（不重建網格）。
    fn compute_ou_step(&self, symbol: &str) -> Option<f64> {
        let history = self.price_history.get(symbol)?;
        if history.len() < 20 {
            return None;
        }
        let n = history.len().min(self.ou_lookback);
        let prices = &history[history.len() - n..];

        let changes: Vec<f64> = prices.windows(2).map(|w| w[1] - w[0]).collect();
        let x_lag: Vec<f64> = prices[..prices.len() - 1].to_vec();

        if changes.is_empty() {
            return None;
        }
        let n_f = changes.len() as f64;
        let mean_x: f64 = x_lag.iter().sum::<f64>() / n_f;
        let mean_dx: f64 = changes.iter().sum::<f64>() / n_f;

        let mut num = 0.0;
        let mut den = 0.0;
        for i in 0..changes.len() {
            let dx = x_lag[i] - mean_x;
            num += dx * (changes[i] - mean_dx);
            den += dx * dx;
        }

        if den.abs() < 1e-15 {
            return None;
        }
        let b = num / den;
        let theta = (-b).max(0.001);

        let sigma = (changes.iter().map(|c| c * c).sum::<f64>() / n_f).sqrt();
        let mu = prices.iter().sum::<f64>() / prices.len() as f64;

        // OU optimal grid spacing: σ·√(2/θ) — derived from OU first-passage time.
        // OU 最佳網格間距：σ·√(2/θ) — 由 OU 首次穿越時間推導。
        let ou_step = sigma * (2.0_f64 / theta).sqrt();
        let fee_floor = 2.0 * FEE_PCT * mu;
        let step = ou_step.max(fee_floor);

        if step > 0.0 && mu > 0.0 {
            Some(step)
        } else {
            None
        }
    }

    /// Update grid spacing for a symbol based on OU model (V2). Respects current spacing_mode.
    /// 基於 OU 模型更新指定幣種的網格間距 (V2)。遵循當前 spacing_mode。
    pub fn update_ou_spacing(&mut self, symbol: &str) {
        let history = match self.price_history.get(symbol) {
            Some(h) if h.len() >= 20 => h,
            _ => return,
        };
        let n = history.len().min(self.ou_lookback);
        let prices = &history[history.len() - n..];
        let mu = prices.iter().sum::<f64>() / prices.len() as f64;

        if let Some(step) = self.compute_ou_step(symbol) {
            let new_levels = match self.spacing_mode {
                GridSpacingMode::Linear => {
                    let lower = mu - step * (DEFAULT_GRID_COUNT as f64 / 2.0);
                    build_linear_levels(
                        lower,
                        lower + step * (DEFAULT_GRID_COUNT as f64 - 1.0),
                        DEFAULT_GRID_COUNT,
                    )
                }
                GridSpacingMode::Geometric => {
                    let half_range = step * (DEFAULT_GRID_COUNT as f64 / 2.0);
                    let lower = (mu - half_range).max(mu * 0.01);
                    let upper = mu + half_range;
                    build_geometric_levels(lower, upper, DEFAULT_GRID_COUNT)
                }
            };
            self.grid_levels.insert(symbol.to_string(), new_levels);
        }
    }

    pub fn update_params(&mut self, params: GridTradingParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        self.qty_per_grid = params.qty_per_grid;
        self.max_inventory = params.max_inventory;
        self.ou_lookback = params.ou_lookback;
        self.health_check_interval = params.health_check_interval;
        self.max_out_of_range = params.max_out_of_range;
        info!(strategy = "grid_trading", "params updated / 參數已更新");
        Ok(())
    }

    pub fn get_params(&self) -> GridTradingParams {
        GridTradingParams {
            cooldown_ms: self.cooldown_ms,
            qty_per_grid: self.qty_per_grid,
            max_inventory: self.max_inventory,
            ou_lookback: self.ou_lookback,
            health_check_interval: self.health_check_interval,
            max_out_of_range: self.max_out_of_range,
        }
    }
}

impl Strategy for GridTrading {
    fn name(&self) -> &str {
        "grid_trading"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// Reset per-symbol net_inventory on external close (risk-stop) to prevent desync.
    /// 外部平倉（風控止損）時重設該幣種 net_inventory，防止與 paper_state 脫鉤。
    fn on_external_close(&mut self, symbol: &str) {
        let inv = self.net_inventory.get(symbol).copied().unwrap_or(0.0);
        if inv != 0.0 {
            info!(strategy = "grid_trading", %symbol, prev_inventory = %inv,
                  "external close: resetting net_inventory / 外部平倉：重設淨庫存");
            self.net_inventory.insert(symbol.to_string(), 0.0);
        }
    }

    /// Pipeline confirmed a strategy-emitted Close was executed — adjust per-symbol inventory.
    /// 管線確認策略平倉已執行 — 調整該幣種庫存。
    fn on_close_confirmed(&mut self, symbol: &str) {
        let prev_inv = self.prev_inventory.get(symbol).copied().unwrap_or(0.0);
        let cur_inv = self.net_inventory.entry(symbol.to_string()).or_insert(0.0);
        if prev_inv < 0.0 {
            *cur_inv += self.qty_per_grid;
        } else if prev_inv > 0.0 {
            *cur_inv -= self.qty_per_grid;
        }
        info!(strategy = "grid_trading", %symbol, new_inventory = %cur_inv,
              "close confirmed: inventory adjusted / 平倉確認：庫存已調整");
    }

    /// Pipeline skipped a strategy-emitted Close (no position found) — roll back per-symbol cross state.
    /// 管線跳過策略平倉（未找到倉位）— 回滾該幣種交叉狀態。
    fn on_close_skipped(&mut self, symbol: &str) {
        if let Some(prev) = self.prev_cross_idx.get(symbol) {
            match prev {
                Some(idx) => { self.last_cross_idx.insert(symbol.to_string(), *idx); }
                None => { self.last_cross_idx.remove(symbol); }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(symbol) {
            if ts == 0 { self.last_trade_ms.remove(symbol); } else { self.last_trade_ms.insert(symbol.to_string(), ts); }
        }
        info!(strategy = "grid_trading", %symbol, "close skipped: cross state rolled back / 平倉跳過：交叉狀態已回滾");
    }

    /// RC-04: Revert per-symbol net_inventory, last_cross_idx, last_trade_ms on rejection.
    /// RC-04：拒絕時回滾該幣種的 net_inventory、last_cross_idx、last_trade_ms。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(prev) = self.prev_cross_idx.get(sym) {
            match prev {
                Some(idx) => { self.last_cross_idx.insert(sym.clone(), *idx); }
                None => { self.last_cross_idx.remove(sym); }
            }
        }
        if let Some(&inv) = self.prev_inventory.get(sym) {
            self.net_inventory.insert(sym.clone(), inv);
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 { self.last_trade_ms.remove(sym); } else { self.last_trade_ms.insert(sym.clone(), ts); }
        }
    }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<StrategyAction> {
        let sym = &ctx.symbol;

        // Per-symbol price history for OU model
        let history = self.price_history.entry(sym.clone()).or_default();
        history.push(ctx.price);
        let ou_lookback = self.ou_lookback;
        if history.len() > ou_lookback * 2 {
            history.drain(0..ou_lookback);
        }

        // Auto-initialize per-symbol grid on first tick.
        // If template_bounds is set (from new(lower, upper)), use those bounds;
        // otherwise use adaptive ±10% of current price.
        // 每幣種首次 tick 初始化網格。有 template_bounds 用模板邊界，否則自適應 ±10%。
        if !self.grid_levels.contains_key(sym) && ctx.price > 0.0 {
            let (lower, upper) = match self.template_bounds {
                Some((lo, hi)) => (lo, hi),
                None => (
                    ctx.price * (1.0 - ADAPTIVE_RANGE_PCT),
                    ctx.price * (1.0 + ADAPTIVE_RANGE_PCT),
                ),
            };
            self.grid_levels.insert(sym.clone(), build_levels(lower, upper, DEFAULT_GRID_COUNT, &self.spacing_mode));
        }

        // Per-symbol health check every health_check_interval ticks.
        // 每幣種每 health_check_interval 個 tick 執行健康檢查。
        let ticks = self.ticks_since_health_check.entry(sym.clone()).or_insert(0);
        *ticks += 1;
        if *ticks >= self.health_check_interval {
            *ticks = 0;
            let health = self.check_health(sym, ctx.price);
            if health == GridHealth::NeedsRebalance {
                self.rebalance(sym, ctx.price);
            }
        }

        // Periodically update per-symbol grid spacing via OU model
        // 定期通過 OU 模型更新該幣種網格間距
        let hist_len = self.price_history.get(sym).map(|h| h.len()).unwrap_or(0);
        if hist_len > 0 && hist_len % 50 == 0 {
            self.update_ou_spacing(sym);
        }

        let last_ms = self.last_trade_ms.get(sym).copied().unwrap_or(0);
        if last_ms > 0 && ctx.timestamp_ms < last_ms + self.cooldown_ms {
            return vec![];
        }

        let idx = self.nearest_grid_idx(sym, ctx.price);
        if self.last_cross_idx.get(sym) == Some(&idx) {
            return vec![];
        }

        let prev_idx = self.last_cross_idx.get(sym).copied().unwrap_or(idx);

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        self.prev_cross_idx.insert(sym.clone(), self.last_cross_idx.get(sym).copied());
        let cur_inventory = self.net_inventory.get(sym).copied().unwrap_or(0.0);
        self.prev_inventory.insert(sym.clone(), cur_inventory);
        self.prev_last_trade_ms.insert(sym.clone(), last_ms);

        self.last_cross_idx.insert(sym.clone(), idx);

        let mut intents = Vec::new();

        // Dynamic confidence: grid thrives in ranging + narrow BB, suffers in trending.
        // 動態信心：grid 在 ranging + 窄 BB 中表現好，trending 中表現差。
        // CONF-D: apply per-strategy scale.
        let conf = (compute_grid_confidence(&ctx.indicators) * self.conf_scale).clamp(0.0, 1.0);

        if idx < prev_idx {
            // Price crossed down → buy. If net_inventory < 0 (short), this closes short → Close.
            // Otherwise it's a new long → Open.
            // 價格下穿 → 買入。若 net_inventory < 0（空倉），為平空 → Close；否則新多 → Open。
            let intent = OrderIntent {
                symbol: ctx.symbol.clone(),
                is_long: true,
                qty: self.qty_per_grid,
                confidence: conf,
                strategy: self.name().into(),
                order_type: "market".into(),
                limit_price: None,
            };
            if cur_inventory < 0.0 {
                intents.push(StrategyAction::Close {
                    symbol: ctx.symbol.clone(),
                    confidence: conf,
                    reason: "grid_close_short".into(),
                });
            } else {
                intents.push(StrategyAction::Open(intent));
                *self.net_inventory.entry(sym.clone()).or_insert(0.0) += self.qty_per_grid;
            }
            self.last_trade_ms.insert(sym.clone(), ctx.timestamp_ms);
        } else if idx > prev_idx {
            // Price crossed up → sell. If net_inventory > 0 (long), this closes long → Close.
            // Otherwise it's a new short → Open.
            // 價格上穿 → 賣出。若 net_inventory > 0（多倉），為平多 → Close；否則新空 → Open。
            let intent = OrderIntent {
                symbol: ctx.symbol.clone(),
                is_long: false,
                qty: self.qty_per_grid,
                confidence: conf,
                strategy: self.name().into(),
                order_type: "market".into(),
                limit_price: None,
            };
            if cur_inventory > 0.0 {
                intents.push(StrategyAction::Close {
                    symbol: ctx.symbol.clone(),
                    confidence: conf,
                    reason: "grid_close_long".into(),
                });
            } else {
                intents.push(StrategyAction::Open(intent));
                *self.net_inventory.entry(sym.clone()).or_insert(0.0) -= self.qty_per_grid;
            }
            self.last_trade_ms.insert(sym.clone(), ctx.timestamp_ms);
        }

        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let p: GridTradingParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(p)
    }
    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }
    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&GridTradingParams::param_ranges()).unwrap_or_default()
    }
    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }
    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn ctx(price: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(),
            price,
            timestamp_ms: ts,
            indicators: None,
            signals: vec![],
            h0_allowed: true,
        }
    }

    #[test]
    fn test_grid_creation() {
        // Grid levels are lazily initialized on first tick, not at construction.
        // 網格層級在首次 tick 時延遲初始化，不在構造時。
        let mut g = GridTrading::new(49000.0, 51000.0);
        assert!(g.grid_levels.is_empty(), "grid_levels should be empty before first tick");
        g.on_tick(&ctx(50000.0, 0)); // triggers lazy init with template_bounds
        let levels = g.grid_levels.get("BTC").unwrap();
        assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
        assert!((levels[0] - 49000.0).abs() < 0.01);
    }

    #[test]
    fn test_grid_buy_on_down_cross() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(50500.0, 0)); // initial
        let i = g.on_tick(&ctx(49500.0, 100_000)); // cross down
        assert!(!i.is_empty());
        // net_inventory was 0 before buy → Open (new long)
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_grid_sell_on_up_cross() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(49500.0, 0));
        let i = g.on_tick(&ctx(50500.0, 100_000));
        assert!(!i.is_empty());
        // net_inventory was 0 before sell → Open (new short)
        match &i[0] {
            StrategyAction::Open(intent) => assert!(!intent.is_long),
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_no_inventory_cap_blocking() {
        // Inventory cap removed — intent_processor Gate 1.5 handles duplicates.
        // 庫存上限已移除 — intent_processor Gate 1.5 處理重複。
        let mut g = GridTrading::new(49000.0, 51000.0);
        // First tick initializes grid lazily / 首次 tick 延遲初始化網格
        g.on_tick(&ctx(50500.0, 0));
        g.net_inventory.insert("BTC".into(), g.max_inventory);
        let i = g.on_tick(&ctx(49500.0, 100_000));
        assert!(!i.is_empty()); // Grid always emits; intent_processor decides
    }

    #[test]
    fn test_grid_close_on_inventory_reduction() {
        // When net_inventory > 0 and price crosses up (sell), it's a Close (closing long).
        // When net_inventory < 0 and price crosses down (buy), it's a Close (closing short).
        // 當 net_inventory > 0 且價格上穿（賣出），為 Close（平多）。
        // 當 net_inventory < 0 且價格下穿（買入），為 Close（平空）。
        let mut g = GridTrading::new(49000.0, 51000.0);

        // Step 1: Buy to build positive inventory / 步驟 1：買入建立正庫存
        g.on_tick(&ctx(50500.0, 0));
        let i = g.on_tick(&ctx(49500.0, 100_000));
        assert!(!i.is_empty());
        assert!(*g.net_inventory.get("BTC").unwrap_or(&0.0) > 0.0);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected Open for initial buy, got {:?}", other),
        }

        // Step 2: Sell with positive inventory → Close / 步驟 2：正庫存賣出 → Close
        let i = g.on_tick(&ctx(50500.0, 200_000));
        assert!(!i.is_empty());
        match &i[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "grid_close_long"),
            other => panic!("expected Close for inventory reduction, got {:?}", other),
        }
        // Inventory NOT yet adjusted (deferred until on_close_confirmed)
        // 庫存尚未調整（延遲到 on_close_confirmed）
        assert!(*g.net_inventory.get("BTC").unwrap_or(&0.0) > 0.0, "inventory deferred: still positive before confirm");

        // Pipeline confirms close → inventory adjusted
        // 管線確認平倉 → 庫存已調整
        g.on_close_confirmed("BTC");
        let inv = g.net_inventory.get("BTC").copied().unwrap_or(0.0);
        assert!(
            inv.abs() < 1e-9,
            "inventory should be 0 after close confirmed, got {}",
            inv
        );
    }

    #[test]
    fn test_grid_close_skipped_rolls_back() {
        // When pipeline skips a Close (no position), on_close_skipped rolls back cross state.
        // 管線跳過 Close（無倉位）時，on_close_skipped 回滾交叉狀態。
        let mut g = GridTrading::new(49000.0, 51000.0);
        // Build positive inventory via Open
        g.on_tick(&ctx(50500.0, 0));
        g.on_tick(&ctx(49500.0, 100_000));
        let prev_cross = g.last_cross_idx.get("BTC").copied();
        let prev_inventory = g.net_inventory.get("BTC").copied().unwrap_or(0.0);

        // Emit Close (sell with positive inventory)
        let i = g.on_tick(&ctx(50500.0, 200_000));
        assert!(!i.is_empty());
        match &i[0] {
            StrategyAction::Close { .. } => {}
            other => panic!("expected Close, got {:?}", other),
        }

        // Pipeline says no position found → skip → roll back
        g.on_close_skipped("BTC");
        assert_eq!(g.last_cross_idx.get("BTC").copied(), prev_cross, "cross state should be rolled back");
        // Inventory unchanged since Close doesn't adjust eagerly
        let cur_inv = g.net_inventory.get("BTC").copied().unwrap_or(0.0);
        assert!((cur_inv - prev_inventory).abs() < 1e-9);
    }

    #[test]
    fn test_adaptive_grid_init_on_first_tick() {
        // Adaptive grid starts empty and auto-initializes on first tick
        // 自适应网格初始为空，首次 tick 时自动初始化
        let mut g = GridTrading::new_adaptive();
        assert!(g.grid_levels.is_empty());
        let intents = g.on_tick(&ctx(50000.0, 0));
        let levels = g.grid_levels.get("BTC").unwrap();
        assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
        // Range should be ±10% of 50000 → 45000..55000
        assert!((levels[0] - 45000.0).abs() < 1.0);
        assert!(intents.is_empty()); // first tick = no trade
    }

    #[test]
    fn test_ou_spacing_update() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(50000.0, 0)); // lazy init
        // Fill price history for BTC
        let history = g.price_history.entry("BTC".into()).or_default();
        for i in 0..60 {
            history.push(50000.0 + (i as f64 * 0.1).sin() * 100.0);
        }
        g.update_ou_spacing("BTC");
        let levels = g.grid_levels.get("BTC").unwrap();
        assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
    }

    // ── Geometric spacing tests / 幾何間距測試 ──

    #[test]
    fn test_geometric_grid_levels() {
        // Verify geometric spacing produces correct ratio-based levels.
        // 驗證幾何間距產生正確的等比層級。
        let mut g = GridTrading::new_geometric(1000.0, 2000.0);
        g.on_tick(&ctx(1500.0, 0)); // lazy init with template_bounds
        let levels = g.grid_levels.get("BTC").unwrap();
        assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
        assert!((levels[0] - 1000.0).abs() < 0.01);
        let last = levels[levels.len() - 1];
        assert!((last - 2000.0).abs() < 0.1);

        // All ratios between consecutive levels should be equal.
        // 所有相鄰層級之間的比率應相等。
        let expected_ratio = (2000.0_f64 / 1000.0).powf(1.0 / 9.0);
        for i in 1..levels.len() {
            let ratio = levels[i] / levels[i - 1];
            assert!(
                (ratio - expected_ratio).abs() < 1e-10,
                "Ratio at index {} was {}, expected {}",
                i,
                ratio,
                expected_ratio
            );
        }
    }

    #[test]
    fn test_geometric_vs_linear() {
        // Geometric levels should differ from linear levels for the same bounds.
        // 相同邊界下，幾何層級應與線性層級不同。
        let mut lin = GridTrading::new(1000.0, 2000.0);
        let mut geo = GridTrading::new_geometric(1000.0, 2000.0);
        lin.on_tick(&ctx(1500.0, 0)); // lazy init
        geo.on_tick(&ctx(1500.0, 0)); // lazy init
        let lin_l = lin.grid_levels.get("BTC").unwrap();
        let geo_l = geo.grid_levels.get("BTC").unwrap();

        assert_eq!(lin_l.len(), geo_l.len());

        // First and last levels match (same bounds).
        // 首末層級應相同（邊界一致）。
        assert!((lin_l[0] - geo_l[0]).abs() < 0.01);
        let last = lin_l.len() - 1;
        assert!((lin_l[last] - geo_l[last]).abs() < 0.5);

        // Middle levels should differ — geometric bunches more toward lower end.
        // 中間層級應不同 — 幾何模式在低端更密集。
        let mid = lin_l.len() / 2;
        assert!(
            (lin_l[mid] - geo_l[mid]).abs() > 1.0,
            "Middle levels should differ: linear={}, geometric={}",
            lin_l[mid],
            geo_l[mid]
        );
    }

    // ── Health check tests / 健康檢查測試 ──

    #[test]
    fn test_health_check_in_range() {
        // Price within grid → Healthy.
        // 價格在網格範圍內 → Healthy。
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(50000.0, 0)); // lazy init
        let h = g.check_health("BTC", 50000.0);
        assert_eq!(h, GridHealth::Healthy);
        assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 0);
    }

    #[test]
    fn test_health_check_out_of_range() {
        // Price outside grid → OutOfRange (but not yet NeedsRebalance).
        // 價格超出網格 → OutOfRange（但尚未到 NeedsRebalance）。
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(50000.0, 0)); // lazy init

        // Price below grid
        let h = g.check_health("BTC", 48000.0);
        assert_eq!(h, GridHealth::OutOfRange);
        assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 1);

        // Price above grid
        let h = g.check_health("BTC", 52000.0);
        assert_eq!(h, GridHealth::OutOfRange);
        assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 2);

        // Price back in range → resets counter
        // 價格回到範圍 → 重置計數器
        let h = g.check_health("BTC", 50000.0);
        assert_eq!(h, GridHealth::Healthy);
        assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 0);
    }

    #[test]
    fn test_auto_rebalance() {
        // After max_out_of_range ticks outside grid, grid recenters.
        // 連續超出範圍達到 max_out_of_range 次後，網格重新居中。
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.max_out_of_range = 5;
        g.health_check_interval = 1; // Check every tick for test / 測試用每 tick 檢查

        let far_price = 60000.0; // Well outside 49000-51000 range

        // Feed ticks at the far price. Health check runs every tick.
        // 以遠離價格餵入 tick。每 tick 執行健康檢查。
        for ts in 0..10 {
            g.on_tick(&ctx(far_price, ts * 100_000));
        }

        // Grid should have rebalanced around 60000 (±10% → 54000..66000).
        // 網格應已以 60000 為中心重建（±10% → 54000..66000）。
        let levels = g.grid_levels.get("BTC").unwrap();
        assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
        let lo = levels[0];
        let hi = levels[levels.len() - 1];
        // The new grid should contain the far price.
        // 新網格應包含遠離的價格。
        assert!(
            lo < far_price && far_price < hi,
            "Rebalanced grid [{}, {}] should contain price {}",
            lo,
            hi,
            far_price
        );
        assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 0);
    }

    #[test]
    fn test_geometric_rebalance() {
        // Rebalance in geometric mode preserves geometric spacing.
        // 幾何模式下再平衡應保持等比間距。
        let mut g = GridTrading::new_geometric(49000.0, 51000.0);
        g.max_out_of_range = 3;
        g.health_check_interval = 1;

        let far_price = 60000.0;
        for ts in 0..8 {
            g.on_tick(&ctx(far_price, ts * 100_000));
        }

        // Grid should have rebalanced with geometric spacing.
        // 網格應已以幾何間距重建。
        let levels = g.grid_levels.get("BTC").unwrap();
        assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
        assert_eq!(g.spacing_mode, GridSpacingMode::Geometric);

        // Verify geometric property: constant ratio between consecutive levels.
        // 驗證幾何特性：相鄰層級間比率恆定。
        let ratios: Vec<f64> = levels.windows(2).map(|w| w[1] / w[0]).collect();
        let first_ratio = ratios[0];
        for (i, &r) in ratios.iter().enumerate() {
            assert!(
                (r - first_ratio).abs() < 1e-8,
                "Ratio at index {} was {}, expected {} (geometric invariant broken)",
                i,
                r,
                first_ratio
            );
        }

        // New grid should contain the rebalance price.
        // 新網格應包含再平衡價格。
        let lo = levels[0];
        let hi = levels[levels.len() - 1];
        assert!(lo < far_price && far_price < hi);
    }

    #[test]
    fn test_adaptive_geometric_init() {
        // Adaptive geometric grid initializes with geometric spacing on first tick.
        // 自適應幾何網格在首次 tick 時以幾何間距初始化。
        let mut g = GridTrading::new_adaptive_geometric();
        assert!(g.grid_levels.is_empty());
        assert_eq!(g.spacing_mode, GridSpacingMode::Geometric);

        g.on_tick(&ctx(50000.0, 0));
        let btc_levels = g.grid_levels.get("BTC").expect("BTC grid should be initialized on first tick");
        assert_eq!(btc_levels.len(), DEFAULT_GRID_COUNT);

        // Verify geometric property.
        // 驗證幾何特性。
        let ratios: Vec<f64> = btc_levels.windows(2).map(|w| w[1] / w[0]).collect();
        let first_ratio = ratios[0];
        for &r in &ratios {
            assert!((r - first_ratio).abs() < 1e-10);
        }
    }

    #[test]
    fn test_grid_param_ranges() {
        assert!(!GridTradingParams::param_ranges().is_empty());
    }
    #[test]
    fn test_grid_validate() {
        assert!(GridTradingParams::default().validate().is_ok());
        assert!(GridTradingParams {
            max_inventory: 0.5,
            ..Default::default()
        }
        .validate()
        .is_err());
    }
    #[test]
    fn test_grid_update() {
        let mut g = GridTrading::new(100.0, 110.0);
        assert!(g
            .update_params(GridTradingParams {
                max_inventory: 10.0,
                ..Default::default()
            })
            .is_ok());
        assert!((g.get_params().max_inventory - 10.0).abs() < 0.01);
    }
}
