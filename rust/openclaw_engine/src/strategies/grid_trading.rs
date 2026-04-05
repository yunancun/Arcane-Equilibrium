//! Grid Trading Strategy V2 — OU dynamic spacing + fee floor + geometric mode + health check.
//! 網格交易策略 V2 — OU 動態間距 + 手續費地板 + 幾何模式 + 健康檢查。
//!
//! Grid levels between lower/upper bounds. Buy on down-cross, sell on up-cross.
//! OU model: optimal spacing = σ·√(2/θ) with floor = 2× round-trip fee.
//! Geometric mode: equal ratio gaps between levels (better for crypto).
//! Health check: detect stale/out-of-range grids and auto-rebalance.

use super::{ParamRange, Strategy, StrategyParams};
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
            ParamRange { name: "cooldown_ms".into(), min: 30_000.0, max: 600_000.0, step: Some(30_000.0), agent_adjustable: true, db_persisted: true },
            ParamRange { name: "qty_per_grid".into(), min: 0.001, max: 1e12, step: None, agent_adjustable: false, db_persisted: true },
            ParamRange { name: "max_inventory".into(), min: 1.0, max: 20.0, step: Some(1.0), agent_adjustable: true, db_persisted: true },
            ParamRange { name: "ou_lookback".into(), min: 20.0, max: 200.0, step: Some(10.0), agent_adjustable: true, db_persisted: true },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.max_inventory < 1.0 { return Err("max_inventory must be >= 1".into()); }
        if self.ou_lookback < 10 { return Err("ou_lookback must be >= 10".into()); }
        Ok(())
    }
}
use crate::tick_pipeline::TickContext;

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
    grid_levels: Vec<f64>,
    last_cross_idx: Option<usize>,
    net_inventory: f64,
    /// Max net inventory — reserved for future Agent position sizing control (Phase 3a).
    /// 最大淨庫存 — 預留給未來 Agent 倉位管理（Phase 3a）。
    #[allow(dead_code)]
    max_inventory: f64,
    last_trade_ms: u64,
    cooldown_ms: u64,
    qty_per_grid: f64,
    // OU parameters / OU 參數
    price_history: Vec<f64>,
    ou_lookback: usize,
    // Spacing mode / 間距模式
    spacing_mode: GridSpacingMode,
    // Health check fields / 健康檢查欄位
    /// How often (in ticks) to run health check / 每隔多少 tick 執行健康檢查
    health_check_interval: usize,
    /// Ticks elapsed since last health check / 距上次健康檢查已過的 tick 數
    ticks_since_health_check: usize,
    /// Consecutive ticks price was out of grid range / 連續價格超出網格範圍的 tick 數
    out_of_range_count: usize,
    /// Max allowed consecutive out-of-range ticks before rebalance / 觸發再平衡前允許的最大連續超出範圍次數
    max_out_of_range: usize,
    // RC-04: Previous state for rejection rollback / 拒絕回滾用的先前狀態
    prev_cross_idx: Option<usize>,
    prev_inventory: f64,
    prev_last_trade_ms: u64,
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
    pub fn new(lower: f64, upper: f64) -> Self {
        let levels = build_linear_levels(lower, upper, DEFAULT_GRID_COUNT);
        Self {
            active: true,
            grid_levels: levels,
            last_cross_idx: None,
            net_inventory: 0.0,
            max_inventory: 5.0,
            last_trade_ms: 0,
            cooldown_ms: 60_000,
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            price_history: Vec::new(),
            ou_lookback: 100,
            spacing_mode: GridSpacingMode::Linear,
            health_check_interval: 200,
            ticks_since_health_check: 0,
            out_of_range_count: 0,
            max_out_of_range: 50,
            prev_cross_idx: None, prev_inventory: 0.0, prev_last_trade_ms: 0,
        }
    }

    /// Create a grid with geometric (ratio-based) spacing.
    /// Not deployed in main.rs yet — available for Agent/config selection in Phase 3a.
    /// 建立幾何（等比）間距網格 — 各層級間比率相等。
    /// 尚未在 main.rs 部署 — Phase 3a 供 Agent/配置選擇使用。
    #[allow(dead_code)]
    pub fn new_geometric(lower: f64, upper: f64) -> Self {
        let levels = build_geometric_levels(lower, upper, DEFAULT_GRID_COUNT);
        Self {
            active: true,
            grid_levels: levels,
            last_cross_idx: None,
            net_inventory: 0.0,
            max_inventory: 5.0,
            last_trade_ms: 0,
            cooldown_ms: 60_000,
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            price_history: Vec::new(),
            ou_lookback: 100,
            spacing_mode: GridSpacingMode::Geometric,
            health_check_interval: 200,
            ticks_since_health_check: 0,
            out_of_range_count: 0,
            max_out_of_range: 50,
            prev_cross_idx: None, prev_inventory: 0.0, prev_last_trade_ms: 0,
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
        // Start with a placeholder range; the first tick will re-center the grid.
        // 使用占位范围；第一个 tick 会重新居中网格。
        Self {
            active: true,
            grid_levels: Vec::new(), // Empty — initialized on first tick / 空 — 首次 tick 時初始化
            last_cross_idx: None,
            net_inventory: 0.0,
            max_inventory: 5.0,
            last_trade_ms: 0,
            cooldown_ms: 60_000,
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            price_history: Vec::new(),
            ou_lookback: 100,
            spacing_mode: mode,
            health_check_interval: 200,
            ticks_since_health_check: 0,
            out_of_range_count: 0,
            max_out_of_range: 50,
            prev_cross_idx: None, prev_inventory: 0.0, prev_last_trade_ms: 0,
        }
    }

    /// Find nearest grid level index for a price.
    /// 找到價格最近的網格等級索引。
    fn nearest_grid_idx(&self, price: f64) -> usize {
        let mut best = 0;
        let mut best_dist = f64::MAX;
        for (i, &level) in self.grid_levels.iter().enumerate() {
            let d = (price - level).abs();
            if d < best_dist {
                best_dist = d;
                best = i;
            }
        }
        best
    }

    /// Check grid health: is price within bounds? Should we rebalance?
    /// 檢查網格健康：價格是否在範圍內？是否需要再平衡？
    pub fn check_health(&mut self, price: f64) -> GridHealth {
        if self.grid_levels.is_empty() {
            return GridHealth::Healthy;
        }
        let lo = self.grid_levels[0];
        let hi = self.grid_levels[self.grid_levels.len() - 1];

        if price < lo || price > hi {
            self.out_of_range_count += 1;
            if self.out_of_range_count >= self.max_out_of_range {
                GridHealth::NeedsRebalance
            } else {
                GridHealth::OutOfRange
            }
        } else {
            // Price back in range — reset counter / 價格回到範圍 — 重置計數器
            self.out_of_range_count = 0;
            GridHealth::Healthy
        }
    }

    /// Rebalance the grid centered on the given price.
    /// If OU has enough data, use OU-derived spacing; otherwise ±10% range.
    /// Respects current spacing_mode (Linear or Geometric).
    /// 以指定價格為中心重建網格。
    /// 若 OU 有足夠數據則使用 OU 間距；否則 ±10% 範圍。
    /// 遵循當前 spacing_mode。
    fn rebalance(&mut self, price: f64) {
        let (lower, upper) = if self.price_history.len() >= 20 {
            // Use OU-derived step to compute bounds / 用 OU 推導的步長計算邊界
            let ou_step = self.compute_ou_step();
            if let Some(step) = ou_step {
                let lo = price - step * (DEFAULT_GRID_COUNT as f64 / 2.0);
                let hi = price + step * (DEFAULT_GRID_COUNT as f64 / 2.0);
                // For geometric mode, ensure lower > 0
                // 幾何模式需確保下界 > 0
                (lo.max(price * 0.01), hi)
            } else {
                (price * (1.0 - ADAPTIVE_RANGE_PCT), price * (1.0 + ADAPTIVE_RANGE_PCT))
            }
        } else {
            (price * (1.0 - ADAPTIVE_RANGE_PCT), price * (1.0 + ADAPTIVE_RANGE_PCT))
        };

        self.grid_levels = build_levels(lower, upper, DEFAULT_GRID_COUNT, &self.spacing_mode);
        self.out_of_range_count = 0;
        self.last_cross_idx = None;
    }

    /// Compute OU-derived optimal step size (without rebuilding the grid).
    /// Returns None if data is insufficient or parameters are degenerate.
    /// 計算 OU 推導的最佳步長（不重建網格）。
    /// 數據不足或參數退化時返回 None。
    fn compute_ou_step(&self) -> Option<f64> {
        if self.price_history.len() < 20 {
            return None;
        }
        let n = self.price_history.len().min(self.ou_lookback);
        let prices = &self.price_history[self.price_history.len() - n..];

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

        if step > 0.0 && mu > 0.0 { Some(step) } else { None }
    }

    /// Update grid spacing based on OU model (V2). Respects current spacing_mode.
    /// 基於 OU 模型更新網格間距 (V2)。遵循當前 spacing_mode。
    pub fn update_ou_spacing(&mut self) {
        if self.price_history.len() < 20 {
            return;
        }
        let n = self.price_history.len().min(self.ou_lookback);
        let prices = &self.price_history[self.price_history.len() - n..];
        let mu = prices.iter().sum::<f64>() / prices.len() as f64;

        if let Some(step) = self.compute_ou_step() {
            match self.spacing_mode {
                GridSpacingMode::Linear => {
                    // Linear: center on mu with equal dollar steps.
                    // 線性：以 mu 為中心，等差步長。
                    let lower = mu - step * (DEFAULT_GRID_COUNT as f64 / 2.0);
                    self.grid_levels = build_linear_levels(lower, lower + step * (DEFAULT_GRID_COUNT as f64 - 1.0), DEFAULT_GRID_COUNT);
                }
                GridSpacingMode::Geometric => {
                    // Geometric: center on mu, derive lower/upper from step size.
                    // 幾何：以 mu 為中心，由步長推算上下界。
                    let half_range = step * (DEFAULT_GRID_COUNT as f64 / 2.0);
                    let lower = (mu - half_range).max(mu * 0.01); // Ensure positive / 確保正數
                    let upper = mu + half_range;
                    self.grid_levels = build_geometric_levels(lower, upper, DEFAULT_GRID_COUNT);
                }
            }
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
    fn name(&self) -> &str { "grid_trading" }
    fn is_active(&self) -> bool { self.active }

    /// RC-04: Revert net_inventory, last_cross_idx, last_trade_ms on rejection.
    /// RC-04：拒絕時回滾 net_inventory、last_cross_idx、last_trade_ms。
    fn on_rejection(&mut self, _intent: &OrderIntent, _reason: &str) {
        self.last_cross_idx = self.prev_cross_idx;
        self.net_inventory = self.prev_inventory;
        self.last_trade_ms = self.prev_last_trade_ms;
    }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        self.price_history.push(ctx.price);
        if self.price_history.len() > self.ou_lookback * 2 {
            self.price_history.drain(0..self.ou_lookback);
        }

        // Auto-initialize grid from first price (±10% range) for adaptive mode.
        // Respects spacing_mode.
        // 自适应模式：首次价格 ±10% 初始化网格，遵循 spacing_mode。
        if self.grid_levels.is_empty() && ctx.price > 0.0 {
            let lower = ctx.price * (1.0 - ADAPTIVE_RANGE_PCT);
            let upper = ctx.price * (1.0 + ADAPTIVE_RANGE_PCT);
            self.grid_levels = build_levels(lower, upper, DEFAULT_GRID_COUNT, &self.spacing_mode);
        }

        // Health check every health_check_interval ticks.
        // 每 health_check_interval 個 tick 執行健康檢查。
        self.ticks_since_health_check += 1;
        if self.ticks_since_health_check >= self.health_check_interval {
            self.ticks_since_health_check = 0;
            let health = self.check_health(ctx.price);
            if health == GridHealth::NeedsRebalance {
                self.rebalance(ctx.price);
            }
        }

        // Periodically update grid spacing via OU model
        // 定期通过 OU 模型更新网格间距
        if self.price_history.len() % 50 == 0 {
            self.update_ou_spacing();
        }

        if self.last_trade_ms > 0 && ctx.timestamp_ms < self.last_trade_ms + self.cooldown_ms {
            return vec![];
        }

        let idx = self.nearest_grid_idx(ctx.price);
        if self.last_cross_idx == Some(idx) {
            return vec![];
        }

        let prev_idx = self.last_cross_idx.unwrap_or(idx);

        // RC-04: Snapshot state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照狀態，供拒絕回滾使用。
        self.prev_cross_idx = self.last_cross_idx;
        self.prev_inventory = self.net_inventory;
        self.prev_last_trade_ms = self.last_trade_ms;

        self.last_cross_idx = Some(idx);

        let mut intents = Vec::new();

        if idx < prev_idx {
            // Price crossed down → buy (intent_processor handles position/sizing)
            // 價格下穿 → 買入（intent_processor 處理倉位/sizing）
            intents.push(OrderIntent {
                symbol: ctx.symbol.clone(),
                is_long: true,
                qty: self.qty_per_grid,
                confidence: 0.5,
                strategy: self.name().into(),
                order_type: "market".into(),
                limit_price: None,
            });
            self.net_inventory += self.qty_per_grid;
            self.last_trade_ms = ctx.timestamp_ms;
        } else if idx > prev_idx {
            // Price crossed up → sell (may close existing long — Gate 1.5 allows opposite)
            // 價格上穿 → 賣出（可能平多倉 — Gate 1.5 允許反向）
            intents.push(OrderIntent {
                symbol: ctx.symbol.clone(),
                is_long: false,
                qty: self.qty_per_grid,
                confidence: 0.5,
                strategy: self.name().into(),
                order_type: "market".into(),
                limit_price: None,
            });
            self.net_inventory -= self.qty_per_grid;
            self.last_trade_ms = ctx.timestamp_ms;
        }

        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let p: GridTradingParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(p)
    }
    fn get_params_json(&self) -> String { serde_json::to_string(&self.get_params()).unwrap_or_default() }
    fn param_ranges_json(&self) -> String { serde_json::to_string(&GridTradingParams::param_ranges()).unwrap_or_default() }
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
        let g = GridTrading::new(49000.0, 51000.0);
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);
        assert!((g.grid_levels[0] - 49000.0).abs() < 0.01);
    }

    #[test]
    fn test_grid_buy_on_down_cross() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(50500.0, 0)); // initial
        let i = g.on_tick(&ctx(49500.0, 100_000)); // cross down
        assert!(!i.is_empty());
        assert!(i[0].is_long);
    }

    #[test]
    fn test_grid_sell_on_up_cross() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.on_tick(&ctx(49500.0, 0));
        let i = g.on_tick(&ctx(50500.0, 100_000));
        assert!(!i.is_empty());
        assert!(!i[0].is_long);
    }

    #[test]
    fn test_no_inventory_cap_blocking() {
        // Inventory cap removed — intent_processor Gate 1.5 handles duplicates.
        // 庫存上限已移除 — intent_processor Gate 1.5 處理重複。
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.net_inventory = g.max_inventory;
        g.on_tick(&ctx(50500.0, 0));
        let i = g.on_tick(&ctx(49500.0, 100_000));
        assert!(!i.is_empty()); // Grid always emits; intent_processor decides
    }

    #[test]
    fn test_adaptive_grid_init_on_first_tick() {
        // Adaptive grid starts empty and auto-initializes on first tick
        // 自适应网格初始为空，首次 tick 时自动初始化
        let mut g = GridTrading::new_adaptive();
        assert!(g.grid_levels.is_empty());
        let intents = g.on_tick(&ctx(50000.0, 0));
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);
        // Range should be ±10% of 50000 → 45000..55000
        assert!((g.grid_levels[0] - 45000.0).abs() < 1.0);
        assert!(intents.is_empty()); // first tick = no trade
    }

    #[test]
    fn test_ou_spacing_update() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        // Fill price history
        for i in 0..60 {
            g.price_history.push(50000.0 + (i as f64 * 0.1).sin() * 100.0);
        }
        g.update_ou_spacing();
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);
    }

    // ── Geometric spacing tests / 幾何間距測試 ──

    #[test]
    fn test_geometric_grid_levels() {
        // Verify geometric spacing produces correct ratio-based levels.
        // 驗證幾何間距產生正確的等比層級。
        let g = GridTrading::new_geometric(1000.0, 2000.0);
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);
        assert!((g.grid_levels[0] - 1000.0).abs() < 0.01);
        let last = g.grid_levels[g.grid_levels.len() - 1];
        assert!((last - 2000.0).abs() < 0.1);

        // All ratios between consecutive levels should be equal.
        // 所有相鄰層級之間的比率應相等。
        let expected_ratio = (2000.0_f64 / 1000.0).powf(1.0 / 9.0);
        for i in 1..g.grid_levels.len() {
            let ratio = g.grid_levels[i] / g.grid_levels[i - 1];
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
        let lin = GridTrading::new(1000.0, 2000.0);
        let geo = GridTrading::new_geometric(1000.0, 2000.0);

        assert_eq!(lin.grid_levels.len(), geo.grid_levels.len());

        // First and last levels match (same bounds).
        // 首末層級應相同（邊界一致）。
        assert!((lin.grid_levels[0] - geo.grid_levels[0]).abs() < 0.01);
        let last = lin.grid_levels.len() - 1;
        assert!((lin.grid_levels[last] - geo.grid_levels[last]).abs() < 0.5);

        // Middle levels should differ — geometric bunches more toward lower end.
        // 中間層級應不同 — 幾何模式在低端更密集。
        let mid = lin.grid_levels.len() / 2;
        assert!(
            (lin.grid_levels[mid] - geo.grid_levels[mid]).abs() > 1.0,
            "Middle levels should differ: linear={}, geometric={}",
            lin.grid_levels[mid],
            geo.grid_levels[mid]
        );
    }

    // ── Health check tests / 健康檢查測試 ──

    #[test]
    fn test_health_check_in_range() {
        // Price within grid → Healthy.
        // 價格在網格範圍內 → Healthy。
        let mut g = GridTrading::new(49000.0, 51000.0);
        let h = g.check_health(50000.0);
        assert_eq!(h, GridHealth::Healthy);
        assert_eq!(g.out_of_range_count, 0);
    }

    #[test]
    fn test_health_check_out_of_range() {
        // Price outside grid → OutOfRange (but not yet NeedsRebalance).
        // 價格超出網格 → OutOfRange（但尚未到 NeedsRebalance）。
        let mut g = GridTrading::new(49000.0, 51000.0);

        // Price below grid
        let h = g.check_health(48000.0);
        assert_eq!(h, GridHealth::OutOfRange);
        assert_eq!(g.out_of_range_count, 1);

        // Price above grid
        let h = g.check_health(52000.0);
        assert_eq!(h, GridHealth::OutOfRange);
        assert_eq!(g.out_of_range_count, 2);

        // Price back in range → resets counter
        // 價格回到範圍 → 重置計數器
        let h = g.check_health(50000.0);
        assert_eq!(h, GridHealth::Healthy);
        assert_eq!(g.out_of_range_count, 0);
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
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);
        let lo = g.grid_levels[0];
        let hi = g.grid_levels[g.grid_levels.len() - 1];
        // The new grid should contain the far price.
        // 新網格應包含遠離的價格。
        assert!(
            lo < far_price && far_price < hi,
            "Rebalanced grid [{}, {}] should contain price {}",
            lo,
            hi,
            far_price
        );
        assert_eq!(g.out_of_range_count, 0);
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
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);
        assert_eq!(g.spacing_mode, GridSpacingMode::Geometric);

        // Verify geometric property: constant ratio between consecutive levels.
        // 驗證幾何特性：相鄰層級間比率恆定。
        let ratios: Vec<f64> = g
            .grid_levels
            .windows(2)
            .map(|w| w[1] / w[0])
            .collect();
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
        let lo = g.grid_levels[0];
        let hi = g.grid_levels[g.grid_levels.len() - 1];
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
        assert_eq!(g.grid_levels.len(), DEFAULT_GRID_COUNT);

        // Verify geometric property.
        // 驗證幾何特性。
        let ratios: Vec<f64> = g
            .grid_levels
            .windows(2)
            .map(|w| w[1] / w[0])
            .collect();
        let first_ratio = ratios[0];
        for &r in &ratios {
            assert!((r - first_ratio).abs() < 1e-10);
        }
    }

    #[test]
    fn test_grid_param_ranges() { assert!(!GridTradingParams::param_ranges().is_empty()); }
    #[test]
    fn test_grid_validate() {
        assert!(GridTradingParams::default().validate().is_ok());
        assert!(GridTradingParams { max_inventory: 0.5, ..Default::default() }.validate().is_err());
    }
    #[test]
    fn test_grid_update() {
        let mut g = GridTrading::new(100.0, 110.0);
        assert!(g.update_params(GridTradingParams { max_inventory: 10.0, ..Default::default() }).is_ok());
        assert!((g.get_params().max_inventory - 10.0).abs() < 0.01);
    }
}
