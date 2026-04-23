//! Grid Trading constructors + param round-trip.
//! Grid Trading 建構子 + 參數來回。
//!
//! MODULE_NOTE (EN): Split out of `strategies/grid_trading.rs` by GRID-TRADING-MOD-SPLIT-1
//!   (2026-04-23) to honour CLAUDE.md §九's 1200-line hard cap (pre-split 1729 lines).
//!   Contains the three `new*` constructors (linear / geometric / adaptive),
//!   `set_fee_rate`, and the `update_params` / `get_params` round-trip pair.
//!   All logic / field initialisation / defaults preserved byte-identical to
//!   pre-split.
//! MODULE_NOTE (中)：GRID-TRADING-MOD-SPLIT-1（2026-04-23）由
//!   `strategies/grid_trading.rs` 拆出以遵守 CLAUDE.md §九 1200 行硬上限
//!   （拆前 1729 行）。本檔包含三個 `new*` 建構子（linear / geometric /
//!   adaptive）、`set_fee_rate`，以及 `update_params` / `get_params` 來回對。
//!   所有邏輯 / 欄位初始化 / 預設值與拆前逐字節相同。

use std::collections::HashMap;

use tracing::info;

use super::params::GridTradingParams;
use super::{
    clamp_maker_limit_timeout_ms, GridTrading, ADAPTIVE_RANGE_PCT, DEFAULT_FEE_PCT,
    DEFAULT_GRID_COUNT, DEFAULT_MAKER_LIMIT_TIMEOUT_MS, DEFAULT_MAKER_OFFSET_BPS,
    DEFAULT_QTY_PER_GRID, DEFAULT_USE_MAKER_ENTRY, REJECT_BACKOFF_MS,
};
use crate::strategies::grid_helpers::GridSpacingMode;
use crate::strategies::StrategyParams;

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
            grid_count: DEFAULT_GRID_COUNT,
            fee_rate: DEFAULT_FEE_PCT,
            reject_cooldown_until_ms: HashMap::new(),
            adaptive_range_pct: ADAPTIVE_RANGE_PCT,
            reject_backoff_ms: REJECT_BACKOFF_MS,
            ou_update_interval: 50,
            adx_low_threshold: 20.0,
            adx_high_threshold: 50.0,
            max_cooldown_boost: 5.0,
            use_maker_entry: DEFAULT_USE_MAKER_ENTRY,
            maker_price_offset_bps: DEFAULT_MAKER_OFFSET_BPS,
            maker_limit_timeout_ms: DEFAULT_MAKER_LIMIT_TIMEOUT_MS,
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
            grid_count: DEFAULT_GRID_COUNT,
            fee_rate: DEFAULT_FEE_PCT,
            reject_cooldown_until_ms: HashMap::new(),
            adaptive_range_pct: ADAPTIVE_RANGE_PCT,
            reject_backoff_ms: REJECT_BACKOFF_MS,
            ou_update_interval: 50,
            adx_low_threshold: 20.0,
            adx_high_threshold: 50.0,
            max_cooldown_boost: 5.0,
            use_maker_entry: DEFAULT_USE_MAKER_ENTRY,
            maker_price_offset_bps: DEFAULT_MAKER_OFFSET_BPS,
            maker_limit_timeout_ms: DEFAULT_MAKER_LIMIT_TIMEOUT_MS,
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
            grid_count: DEFAULT_GRID_COUNT,
            fee_rate: DEFAULT_FEE_PCT,
            reject_cooldown_until_ms: HashMap::new(),
            adaptive_range_pct: ADAPTIVE_RANGE_PCT,
            reject_backoff_ms: REJECT_BACKOFF_MS,
            ou_update_interval: 50,
            adx_low_threshold: 20.0,
            adx_high_threshold: 50.0,
            max_cooldown_boost: 5.0,
            use_maker_entry: DEFAULT_USE_MAKER_ENTRY,
            maker_price_offset_bps: DEFAULT_MAKER_OFFSET_BPS,
            maker_limit_timeout_ms: DEFAULT_MAKER_LIMIT_TIMEOUT_MS,
        }
    }

    /// FIX-25: Set runtime taker fee rate (called from factory with actual exchange rate).
    /// FIX-25：設定運行時 taker 費率（由工廠使用實際交易所費率調用）。
    pub fn set_fee_rate(&mut self, rate: f64) {
        if rate > 0.0 {
            self.fee_rate = rate;
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
        // FIX-06: Apply grid_levels from config (was ignored before).
        // FIX-06：應用配置中的 grid_levels（之前被忽略）。
        if params.grid_levels >= 3 {
            self.grid_count = params.grid_levels;
        }
        // A3: Trend-adaptive cooldown params / A3：趨勢自適應冷卻參數
        self.adx_low_threshold = params.adx_low_threshold;
        self.adx_high_threshold = params.adx_high_threshold;
        self.max_cooldown_boost = params.max_cooldown_boost;
        // EDGE-P2-3 Phase 1a: honor runtime maker toggle + offset updates.
        self.use_maker_entry = params.use_maker_entry;
        self.maker_price_offset_bps = params.maker_price_offset_bps;
        // EDGE-P2-3 Phase 1B-3.1: clamp runtime timeout into supported range on
        // assignment so the event_consumer sweep (1B-3.2) can read this field
        // directly without re-clamping. Out-of-range values indicate operator
        // misconfiguration; prefer the clamped value to silent failure.
        // EDGE-P2-3 Phase 1B-3.1：賦值時 clamp 超時至支援區間，1B-3.2 的 sweep
        // 可直接讀取不必再 clamp。超界值屬 operator 誤配，採 clamp 不靜默失敗。
        self.maker_limit_timeout_ms =
            clamp_maker_limit_timeout_ms(params.maker_limit_timeout_ms);
        info!(
            strategy = "grid_trading",
            grid_count = self.grid_count,
            "params updated / 參數已更新"
        );
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
            grid_levels: self.grid_count,
            adx_low_threshold: self.adx_low_threshold,
            adx_high_threshold: self.adx_high_threshold,
            max_cooldown_boost: self.max_cooldown_boost,
            use_maker_entry: self.use_maker_entry,
            maker_price_offset_bps: self.maker_price_offset_bps,
            maker_limit_timeout_ms: self.maker_limit_timeout_ms,
        }
    }
}
