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
    /// G7-09c Phase 1: number of ticks INSIDE the book at which the BBO-aware
    /// PostOnly limit sits. `0` = exactly on best_bid/ask (still passive maker
    /// per Bybit), `1` (default) = one tick away (more passive, safer against
    /// single-tick book moves). If BBO or tick_size is unavailable, maker
    /// entries are skipped instead of falling back to last_price.
    /// G7-09c Phase 1：BBO-aware PostOnly 限價離 inside quote 的 tick 數。
    /// 0 = 同 best_bid/ask（仍 passive maker），1（預設）= 退一 tick（更被動）。
    /// BBO 或 tick_size 不可得時跳過 maker 入場，不再 fallback 到 last_price。
    #[serde(default = "default_maker_price_buffer_ticks")]
    pub maker_price_buffer_ticks: u32,
    /// G7-09c Phase 2 (FIX-G7-09C-PHASE2-WIRE-1B3): per-symbol cooldown set
    /// after the exchange rejects a PostOnly maker entry (currently:
    /// `EC_PostOnlyWillTakeLiquidity`, `EC_ReachMaxPendingOrders`,
    /// `EC_CancelForNoFullFill`). Distinct from `reject_backoff_ms`
    /// (which fires on *governance* pipeline rejection, default 30s) —
    /// exchange-side rejects usually mean the BBO has shifted faster than
    /// our quote, so we want a longer pause (default 60s) before re-emitting
    /// a maker entry on the same symbol. Bounded `[5_000, 600_000]` by
    /// `validate()` to prevent operator misconfiguration.
    /// G7-09c Phase 2：交易所拒絕 PostOnly 入場後設置的逐 symbol 冷卻。
    /// 與 `reject_backoff_ms`（治理拒絕，預設 30s）不同，交易所拒絕通常
    /// 代表 BBO 比我方報價先動，需更長冷卻（預設 60s）。`validate()`
    /// 限制 `[5_000, 600_000]`，防止 operator 誤配。
    #[serde(default = "default_reject_cooldown_ms")]
    pub reject_cooldown_ms: u64,
    /// Minimum grid step in bps of current price. 0 preserves legacy OU spacing.
    /// 最小網格步長，以現價 bps 表示；0 保留舊 OU 間距。
    #[serde(default)]
    pub min_grid_step_bps: f64,
    /// Multiplier on the round-trip fee floor in OU spacing. 1 preserves legacy.
    /// OU 間距中的往返費用地板倍率；1 保留舊行為。
    #[serde(default = "default_cost_floor_multiplier")]
    pub cost_floor_multiplier: f64,
    /// G2-04: Optional symbol list where grid_trading should not emit new entries.
    /// Existing positions are still allowed to close via the normal close path.
    /// G2-04：可選逐 symbol 禁止 grid 新開倉清單；既有倉位仍可正常平倉。
    #[serde(default)]
    pub blocked_symbols: Vec<String>,
    /// Churn breaker: pause new grid entries after repeated closes in a short window.
    /// 平倉 churn breaker：短窗內反覆平倉後暫停新 grid 入場。
    #[serde(default = "default_churn_breaker_enabled")]
    pub churn_breaker_enabled: bool,
    /// Churn breaker lookback window in ms. / churn breaker 回看窗口（毫秒）。
    #[serde(default = "default_churn_breaker_window_ms")]
    pub churn_breaker_window_ms: u64,
    /// Close count threshold inside the lookback window. / 回看窗口內 close 次數門檻。
    #[serde(default = "default_churn_breaker_close_count")]
    pub churn_breaker_close_count: usize,
    /// Cooldown applied to new entries after the threshold trips. / 觸發後新入場冷卻。
    #[serde(default = "default_churn_breaker_cooldown_ms")]
    pub churn_breaker_cooldown_ms: u64,
}

/// G7-09c Phase 1: default buffer = 1 tick (one tick inside the inside quote).
/// G7-09c Phase 1：預設 1 tick（退一 tick）。
fn default_maker_price_buffer_ticks() -> u32 {
    1
}

/// G7-09c Phase 2: default exchange-reject cooldown = 60s.
/// QC-recommended baseline: ≈ 1× grid `cooldown_ms` (60s default). Long
/// enough to outlast the typical micro-burst on Bybit perps that triggers
/// `EC_PostOnlyWillTakeLiquidity`, short enough that a stable book recovers
/// new entries within ~1 minute.
/// G7-09c Phase 2：交易所拒絕後預設冷卻 = 60 秒。QC 建議基準：約等於
/// grid `cooldown_ms`，可吸收典型 micro-burst，又不致過長。
fn default_reject_cooldown_ms() -> u64 {
    60_000
}

fn default_cost_floor_multiplier() -> f64 {
    1.0
}

fn default_churn_breaker_enabled() -> bool {
    true
}

fn default_churn_breaker_window_ms() -> u64 {
    3_600_000
}

fn default_churn_breaker_close_count() -> usize {
    3
}

fn default_churn_breaker_cooldown_ms() -> u64 {
    21_600_000
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
            // G7-09c Phase 1: default 1 tick inside the inside quote.
            // G7-09c Phase 1：預設退一 tick。
            maker_price_buffer_ticks: 1,
            // G7-09c Phase 2: default 60s exchange-reject cooldown.
            // G7-09c Phase 2：交易所拒絕預設冷卻 60 秒。
            reject_cooldown_ms: 60_000,
            min_grid_step_bps: 0.0,
            cost_floor_multiplier: 1.0,
            blocked_symbols: Vec::new(),
            churn_breaker_enabled: true,
            churn_breaker_window_ms: 3_600_000,
            churn_breaker_close_count: 3,
            churn_breaker_cooldown_ms: 21_600_000,
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
            ParamRange {
                name: "min_grid_step_bps".into(),
                min: 0.0,
                max: 200.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "cost_floor_multiplier".into(),
                min: 1.0,
                max: 5.0,
                step: Some(0.25),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "churn_breaker_window_ms".into(),
                min: 60_000.0,
                max: 86_400_000.0,
                step: Some(60_000.0),
                agent_adjustable: false,
                db_persisted: true,
            },
            ParamRange {
                name: "churn_breaker_close_count".into(),
                min: 2.0,
                max: 20.0,
                step: Some(1.0),
                agent_adjustable: false,
                db_persisted: true,
            },
            ParamRange {
                name: "churn_breaker_cooldown_ms".into(),
                min: 300_000.0,
                max: 86_400_000.0,
                step: Some(300_000.0),
                agent_adjustable: false,
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
        // G7-09c Phase 1: bounded buffer to prevent operators / IPC writes
        // from placing limits 1000+ ticks away (which would never fill on
        // a quiet symbol). 10 ticks is a sane upper bound for major coins.
        // G7-09c Phase 1：限定 buffer，防止 operator 或 IPC 設過大造成永不成交。
        if self.maker_price_buffer_ticks > 10 {
            return Err("maker_price_buffer_ticks must be <= 10".into());
        }
        // G7-09c Phase 2 (FIX-G7-09C-PHASE2-WIRE-1B3): bound exchange-reject
        // cooldown so operator misconfig cannot starve liquidity (e.g. 0ms
        // disables the cooldown entirely, 24h pauses the strategy de-facto).
        // 5s lower bound = at least one tick window; 600s upper bound =
        // outlasts any expected micro-burst without permanently silencing.
        // G7-09c Phase 2：限制 reject_cooldown_ms 範圍 [5s, 600s]，防止 0
        // 失效或過大永久靜音。
        if self.reject_cooldown_ms < 5_000 || self.reject_cooldown_ms > 600_000 {
            return Err("reject_cooldown_ms must be in [5_000, 600_000] ms".into());
        }
        if !self.min_grid_step_bps.is_finite() || !(0.0..=200.0).contains(&self.min_grid_step_bps) {
            return Err("min_grid_step_bps must be in [0, 200]".into());
        }
        if !self.cost_floor_multiplier.is_finite()
            || !(1.0..=5.0).contains(&self.cost_floor_multiplier)
        {
            return Err("cost_floor_multiplier must be in [1, 5]".into());
        }
        if self.churn_breaker_window_ms < 60_000 || self.churn_breaker_window_ms > 86_400_000 {
            return Err("churn_breaker_window_ms must be in [60_000, 86_400_000] ms".into());
        }
        if self.churn_breaker_close_count < 2 || self.churn_breaker_close_count > 20 {
            return Err("churn_breaker_close_count must be in [2, 20]".into());
        }
        if self.churn_breaker_cooldown_ms < 300_000 || self.churn_breaker_cooldown_ms > 86_400_000 {
            return Err("churn_breaker_cooldown_ms must be in [300_000, 86_400_000] ms".into());
        }
        Ok(())
    }
}
