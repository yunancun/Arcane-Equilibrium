//! Grid Trading params — `GridTradingParams` struct + Default + StrategyParams impl.
//! Grid Trading 參數 — `GridTradingParams` 結構 + Default + StrategyParams impl。
//!
//! MODULE_NOTE (EN): Split out of `strategies/grid_trading.rs` by GRID-TRADING-MOD-SPLIT-1
//!   (2026-04-23) to honour CLAUDE.md §九's 1200-line hard cap (pre-split 1729 lines).
//!   Contains the tunable parameters struct, its Default values, and the
//!   `StrategyParams` trait impl (`param_ranges` + `validate`). Logic /
//!   signatures / field ordering preserved byte-identical to pre-split.
//! MODULE_NOTE (中)：GRID-TRADING-MOD-SPLIT-1（2026-04-23）由
//!   `strategies/grid_trading.rs` 拆出以遵守 CLAUDE.md §九 1200 行硬上限
//!   （拆前 1729 行）。本檔包含可調參數結構、Default 值、以及 `StrategyParams`
//!   trait impl（`param_ranges` + `validate`）。邏輯 / 簽名 / 欄位順序與拆前
//!   逐字節相同。

use super::{
    DEFAULT_GRID_COUNT, DEFAULT_MAKER_LIMIT_TIMEOUT_MS, DEFAULT_MAKER_OFFSET_BPS,
    DEFAULT_QTY_PER_GRID, DEFAULT_USE_MAKER_ENTRY,
};
use crate::strategies::{ParamRange, StrategyParams};
use serde::{Deserialize, Serialize};

/// Tunable parameters for Grid Trading (Phase 3a).
/// FIX-06: added grid_levels field (was hardcoded, TOML stored but not applied).
/// FIX-06：新增 grid_levels 欄位（原硬編碼，TOML 存但不生效）。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct GridTradingParams {
    pub cooldown_ms: u64,
    pub qty_per_grid: f64,
    pub max_inventory: f64,
    pub ou_lookback: usize,
    pub health_check_interval: usize,
    pub max_out_of_range: usize,
    /// Number of grid levels. FIX-06: was hardcoded DEFAULT_GRID_COUNT=10.
    /// 網格層級數量。FIX-06：原硬編碼為 10。
    pub grid_levels: usize,
    // ── G-SR-1 A3: Trend-adaptive cooldown params ──
    // ── G-SR-1 A3：趨勢自適應冷卻參數 ──
    /// ADX low threshold for cooldown scaling (below = no boost). / ADX 冷卻縮放下閾值。
    pub adx_low_threshold: f64,
    /// ADX high threshold for cooldown scaling (above = max boost). / ADX 冷卻縮放上閾值。
    pub adx_high_threshold: f64,
    /// Max cooldown multiplier boost (1+boost = max multiplier). / 最大冷卻倍率加成。
    pub max_cooldown_boost: f64,
    /// EDGE-P2-3 Phase 1a: emit PostOnly Limit entries to pay maker fees.
    /// Default `false` (conservative; per-env TOML enables).
    /// EDGE-P2-3 Phase 1a：入場改發 PostOnly Limit 以支付 maker 費率；默認 false。
    pub use_maker_entry: bool,
    /// EDGE-P2-3 Phase 1a: bps offset from last_price for PostOnly limit placement.
    /// EDGE-P2-3 Phase 1a：PostOnly 限價偏移（bps）。
    pub maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 1B-3.1: milliseconds a PostOnly maker order may rest
    /// before the event_consumer sweeps it via cancel-by-link-id. Consumer
    /// clamps to `[MAKER_LIMIT_TIMEOUT_MIN_MS, MAKER_LIMIT_TIMEOUT_MAX_MS]`.
    /// 1B-3.1 is plumbing-only: no call site reads this yet. 1B-3.2 wires
    /// the sweep.
    /// EDGE-P2-3 Phase 1B-3.1：PostOnly 掛單最長停留時間（毫秒）。消費端 clamp
    /// 至 `[15_000, 300_000]`。本批次僅埋線，1B-3.2 接入 sweep。
    pub maker_limit_timeout_ms: u64,
}

impl Default for GridTradingParams {
    fn default() -> Self {
        Self {
            cooldown_ms: 180_000, // EDGE-P0-2: 120s→180s (align with persistence improvement)
            qty_per_grid: DEFAULT_QTY_PER_GRID,
            max_inventory: 5.0,
            ou_lookback: 60,
            health_check_interval: 100,
            max_out_of_range: 5,
            grid_levels: DEFAULT_GRID_COUNT,
            adx_low_threshold: 20.0,
            adx_high_threshold: 50.0,
            max_cooldown_boost: 5.0,
            use_maker_entry: DEFAULT_USE_MAKER_ENTRY,
            maker_price_offset_bps: DEFAULT_MAKER_OFFSET_BPS,
            maker_limit_timeout_ms: DEFAULT_MAKER_LIMIT_TIMEOUT_MS,
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
            // ── G-SR-1 S3: Trend cooldown param ranges (A3) ──
            // ── G-SR-1 S3：趨勢冷卻參數範圍（A3）──
            ParamRange {
                name: "adx_low_threshold".into(),
                min: 5.0,
                max: 40.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "adx_high_threshold".into(),
                min: 20.0,
                max: 80.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "max_cooldown_boost".into(),
                min: 0.0,
                max: 10.0,
                step: Some(0.5),
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
        if self.grid_levels < 3 {
            return Err("grid_levels must be >= 3".into());
        }
        // G-SR-1 S3: Validate trend cooldown params / 驗證趨勢冷卻參數
        if self.adx_low_threshold >= self.adx_high_threshold {
            return Err("adx_low_threshold must be < adx_high_threshold".into());
        }
        if self.max_cooldown_boost < 0.0 || self.max_cooldown_boost > 10.0 {
            return Err("max_cooldown_boost must be in [0, 10]".into());
        }
        Ok(())
    }
}
