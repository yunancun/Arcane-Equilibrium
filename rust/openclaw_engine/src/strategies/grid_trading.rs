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

use super::grid_helpers;
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use serde::{Deserialize, Serialize};
use tracing::info;

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
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::IndicatorSnapshot;

/// Dynamic grid confidence: ranging regime + narrow BB → high; trending → low.
/// 動態網格信心：ranging regime + 窄 BB → 高；trending → 低。
fn compute_grid_confidence(snap: Option<&IndicatorSnapshot>) -> f64 {
    let base = 0.5_f64;
    let Some(ind) = snap else {
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
/// M-2 (2026-04-11) audit fix: per-symbol backoff after a rejection so the strategy
/// doesn't tight-loop re-emitting the same intent every tick. The rollback in
/// `on_rejection` restores prev_cross_idx, which immediately re-fires next tick
/// because price has not moved. 30s gives Guardian/cost_gate state a chance to
/// change before retry.
/// M-2 審計修復：拒絕後每幣種退避，避免策略每 tick 重發同一意圖緊湊迴圈。
/// `on_rejection` 中的回滾會還原 prev_cross_idx，下一 tick 立即重發（價格未動）。
/// 30 秒給 Guardian/cost_gate 狀態變化的機會再重試。
const REJECT_BACKOFF_MS: u64 = 30_000;
/// FIX-25: Default fallback fee rate; prefer runtime `taker_fee_rate` via `set_fee_rate()`.
/// FIX-25：默認回退費率；優先使用 `set_fee_rate()` 設定的運行時 taker_fee_rate。
const DEFAULT_FEE_PCT: f64 = 0.00055;
/// Default adaptive range: ±10% of current price for initial/rebalance grid.
/// 默認自適應範圍：當前價格 ±10% 用於初始化/再平衡網格。
const ADAPTIVE_RANGE_PCT: f64 = 0.10;

/// EDGE-P2-3 Phase 1a: Default PostOnly price offset in basis points.
/// BUY limit placed at `last_price * (1 - offset/10_000)`, SELL at `last_price * (1 + offset/10_000)`
/// so the order rests on the passive side of the book. 1 bps is tight enough to
/// still fill on normal ranging markets while avoiding accidental crossings.
/// EDGE-P2-3 Phase 1a：PostOnly 限價偏移（bps）。BUY 以 last×(1−offset/萬)，
/// SELL 以 last×(1+offset/萬)，確保掛單停在被動側。1 bps 在常規震盪中仍能成交。
const DEFAULT_MAKER_OFFSET_BPS: f64 = 1.0;

/// EDGE-P2-3 Phase 1a: Default for `use_maker_entry`. Root principle #6 —
/// failure default shrink: cold-boot stays on proven Market path until the
/// per-env TOML opts in.
/// EDGE-P2-3 Phase 1a：`use_maker_entry` 默認值。根原則 #6（失敗默認收縮），
/// 冷啟動維持已驗證的 Market 路徑，待各環境 TOML 顯式啟用。
const DEFAULT_USE_MAKER_ENTRY: bool = false;

/// EDGE-P2-3 Phase 1B-3.1: Default timeout for resting PostOnly maker orders.
/// QC-recommended base for tier-1 perps at 1 bps offset: 45_000 ms balances
/// expected fill probability (40-55% on liquid pairs in this window) against
/// adverse-selection decay. Distinct from `cooldown_ms` (which gates re-emit)
/// — this is the "order has rested too long, cancel it" knob consumed by the
/// event_consumer sweep (Phase 1B-3.2 wires actual cancellation).
///
/// Runtime clamp (enforced where it's read, not here): `[15_000, 300_000]` ms.
/// Values below 15s starve fill probability; above 300s stale inventory risk.
/// QC justification: base 45s ≈ 0.75 × grid cooldown (60s) at current config.
///
/// EDGE-P2-3 Phase 1B-3.1：PostOnly 掛單超時預設。QC 針對 tier-1 永續於 1 bps
/// 偏移的建議：45 秒平衡成交機率（流動性良好幣對 40-55%）與逆向選擇衰減。
/// 有別於 `cooldown_ms`（限制重發），此為「掛單停留過久應取消」；實際取消由
/// event_consumer sweep（1B-3.2）執行。消費端 clamp 至 [15_000, 300_000]。
const DEFAULT_MAKER_LIMIT_TIMEOUT_MS: u64 = 45_000;

/// EDGE-P2-3 Phase 1B-3.1: Hard lower bound — below this, maker fills too
/// rarely to justify the cancel round-trip cost.
/// EDGE-P2-3 Phase 1B-3.1：硬下限，低於此值成交機率太低，不值得一次 cancel 往返。
pub(crate) const MAKER_LIMIT_TIMEOUT_MIN_MS: u64 = 15_000;

/// EDGE-P2-3 Phase 1B-3.1: Hard upper bound — above this, a resting order is
/// more stale inventory than price discovery.
/// EDGE-P2-3 Phase 1B-3.1：硬上限，超出後掛單已屬過期庫存而非價格發現。
pub(crate) const MAKER_LIMIT_TIMEOUT_MAX_MS: u64 = 300_000;

/// Clamp a maker-limit timeout value into the strategy's supported range.
/// Centralised so TOML binding + factory + tests all agree on the bounds.
/// 將 maker-limit 超時值 clamp 至策略支援區間。集中處理以保 TOML binding /
/// 工廠 / 測試皆一致。
pub(crate) fn clamp_maker_limit_timeout_ms(v: u64) -> u64 {
    v.clamp(MAKER_LIMIT_TIMEOUT_MIN_MS, MAKER_LIMIT_TIMEOUT_MAX_MS)
}

// GridSpacingMode moved to grid_helpers.rs (A0-a extraction), re-exported for compatibility.
// GridSpacingMode 已移至 grid_helpers.rs（A0-a 提取），此處重導出保持兼容。
pub use super::grid_helpers::GridSpacingMode;

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
    /// E5-P2-4: Now factory-wired from TOML `strategy_params_*.toml::grid_trading.cooldown_ms`.
    /// E5-P2-4：現透過工廠自 TOML（`grid_trading.cooldown_ms`）接線。
    pub(crate) cooldown_ms: u64,
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
    /// FIX-06: Configurable grid level count (was hardcoded DEFAULT_GRID_COUNT).
    /// FIX-06：可配置的網格層級數（原硬編碼 DEFAULT_GRID_COUNT）。
    pub(crate) grid_count: usize,
    /// FIX-25: One-way taker fee rate for OU spacing floor calculation.
    /// FIX-25：單邊 taker 手續費率，用於 OU 間距地板計算。
    fee_rate: f64,
    /// M-2: Per-symbol rejection backoff deadline (epoch ms). Set in `on_rejection`,
    /// honored at the top of `on_tick` to prevent tight retry loops on persistent
    /// guardian/cost_gate rejections.
    /// M-2：每幣種拒絕退避截止時間（epoch ms）。`on_rejection` 中設定，
    /// `on_tick` 開頭遵守，避免持續性 guardian/cost_gate 拒絕造成緊湊迴圈。
    reject_cooldown_until_ms: HashMap<String, u64>,
    /// QC-H7: Adaptive range ±% for initial/rebalance grid (default 0.10 = ±10%).
    /// QC-H7：自適應範圍 ±%（默認 0.10 = ±10%）。
    pub(crate) adaptive_range_pct: f64,
    /// QC-H8: Reject backoff duration ms (default 30_000 = 30s).
    /// QC-H8：拒絕退避時長 ms（默認 30_000 = 30 秒）。
    pub(crate) reject_backoff_ms: u64,
    /// QC-H9: OU model recalculation interval in ticks (default 50).
    /// QC-H9：OU 模型重算間隔（tick 數，默認 50）。
    pub(crate) ou_update_interval: usize,
    // ── G-SR-1 A3: Trend-adaptive cooldown ──
    // ── G-SR-1 A3：趨勢自適應冷卻 ──
    /// ADX low threshold for cooldown scaling. / ADX 冷卻縮放下閾值。
    pub(crate) adx_low_threshold: f64,
    /// ADX high threshold for cooldown scaling. / ADX 冷卻縮放上閾值。
    pub(crate) adx_high_threshold: f64,
    /// Max cooldown boost factor (range 1x to 1+boost). / 最大冷卻倍率加成。
    pub(crate) max_cooldown_boost: f64,
    /// EDGE-P2-3 Phase 1a: emit PostOnly Limit entries instead of Market.
    /// Close path remains Market (entry-only scope). Default `false` per
    /// root principle #6; enabled via per-env TOML once validated.
    /// EDGE-P2-3 Phase 1a：入場發 PostOnly Limit 取代 Market；平倉維持 Market。
    /// 默認 false（根原則 #6），由 TOML 顯式啟用。
    pub(crate) use_maker_entry: bool,
    /// EDGE-P2-3 Phase 1a: bps offset from last_price for PostOnly limit placement.
    /// Only honored when `use_maker_entry = true`.
    /// EDGE-P2-3 Phase 1a：PostOnly 掛單相對 last_price 的 bps 偏移；僅在開啟 maker 時生效。
    pub(crate) maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 1B-3.1: milliseconds a resting PostOnly maker order may
    /// sit before event_consumer sweep cancels it. Stored here as the param
    /// source-of-truth; actual sweep wiring lands in 1B-3.2. Always pre-clamped
    /// on assignment (factory / update_params) into
    /// `[MAKER_LIMIT_TIMEOUT_MIN_MS, MAKER_LIMIT_TIMEOUT_MAX_MS]`.
    /// EDGE-P2-3 Phase 1B-3.1：PostOnly 掛單允許停留的最長毫秒數，超時後由
    /// event_consumer 取消。本批次僅資料欄位；1B-3.2 接入 sweep。
    pub(crate) maker_limit_timeout_ms: u64,
}

// build_linear_levels, build_geometric_levels, build_levels moved to grid_helpers.rs (A0-a)
// 建構函數已移至 grid_helpers.rs（A0-a 提取）

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

    /// Find nearest grid level index for a price in a given symbol's grid.
    /// 找到指定幣種網格中價格最近的等級索引。
    fn nearest_grid_idx(&self, symbol: &str, price: f64) -> usize {
        match self.grid_levels.get(symbol) {
            Some(levels) => grid_helpers::nearest_grid_idx(levels, price),
            None => 0,
        }
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
            let count = self
                .out_of_range_count
                .entry(symbol.to_string())
                .or_insert(0);
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
                let lo = price - step * (self.grid_count as f64 / 2.0);
                let hi = price + step * (self.grid_count as f64 / 2.0);
                // For geometric mode, ensure lower > 0
                // 幾何模式需確保下界 > 0
                (lo.max(price * 0.01), hi)
            } else {
                (
                    price * (1.0 - self.adaptive_range_pct),
                    price * (1.0 + self.adaptive_range_pct),
                )
            }
        } else {
            (
                price * (1.0 - self.adaptive_range_pct),
                price * (1.0 + self.adaptive_range_pct),
            )
        };

        self.grid_levels.insert(
            symbol.to_string(),
            grid_helpers::build_levels(lower, upper, self.grid_count, &self.spacing_mode),
        );
        self.out_of_range_count.insert(symbol.to_string(), 0);
        self.last_cross_idx.remove(symbol);
    }

    /// Compute OU-derived optimal step size for a symbol (without rebuilding the grid).
    /// Delegates to grid_helpers::compute_ou_step() pure function.
    /// 計算指定幣種的 OU 推導最佳步長。委派給 grid_helpers::compute_ou_step() 純函數。
    fn compute_ou_step(&self, symbol: &str) -> Option<f64> {
        let history = self.price_history.get(symbol)?;
        grid_helpers::compute_ou_step(history, self.ou_lookback, self.fee_rate)
    }

    /// G-SR-1 A3: Compute trend-adjusted cooldown for a symbol.
    /// In trending markets (high ADX + high Hurst), cooldown scales up 1x→6x
    /// to reduce grid frequency and limit inventory drift losses.
    /// G-SR-1 A3：計算趨勢調整後的冷卻時間。
    /// 趨勢市場（高 ADX + 高 Hurst）中，冷卻從 1x 增至 6x，降低網格頻率。
    fn compute_trend_adjusted_cooldown(&self, snap: Option<&IndicatorSnapshot>) -> u64 {
        let Some(ind) = snap else {
            return self.cooldown_ms;
        };

        let adx_val = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        let hurst_val = ind.hurst.as_ref().map(|h| h.hurst).unwrap_or(0.5);

        // ADX factor: adx_low→adx_high maps to 0→1
        let adx_range = self.adx_high_threshold - self.adx_low_threshold;
        let adx_factor = if adx_range > 0.0 {
            ((adx_val - self.adx_low_threshold) / adx_range).clamp(0.0, 1.0)
        } else {
            0.0
        };

        // Hurst factor: 0.50→0.75 maps to 0→1
        let hurst_factor = ((hurst_val - 0.50) / 0.25).clamp(0.0, 1.0);

        // Blend 60/40 (ADX reacts faster than Hurst) / 混合 60/40（ADX 反應快於 Hurst）
        let trend_score = 0.6 * adx_factor + 0.4 * hurst_factor;

        // Multiplier range: 1x to (1 + max_cooldown_boost)x / 倍率範圍：1x 到 (1+max_cooldown_boost)x
        let multiplier = 1.0 + (trend_score * self.max_cooldown_boost);

        (self.cooldown_ms as f64 * multiplier) as u64
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
            let gc = self.grid_count;
            let new_levels = match self.spacing_mode {
                GridSpacingMode::Linear => {
                    let lower = mu - step * (gc as f64 / 2.0);
                    grid_helpers::build_linear_levels(lower, lower + step * (gc as f64 - 1.0), gc)
                }
                GridSpacingMode::Geometric => {
                    let half_range = step * (gc as f64 / 2.0);
                    let lower = (mu - half_range).max(mu * 0.01);
                    let upper = mu + half_range;
                    grid_helpers::build_geometric_levels(lower, upper, gc)
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

    /// Pipeline skipped a strategy-emitted Close (no position found) — roll back cross state.
    /// FIX-C: Do NOT roll back last_trade_ms. The emit timestamp is kept as-is so the
    /// existing 30s cooldown (REJECT_BACKOFF_MS) stays active and prevents tight-loop
    /// re-emission on the next tick. Previously, rolling back last_trade_ms removed the
    /// cooldown entirely, causing grid to re-emit the same Close intent every single tick
    /// (observed: hundreds of `close_skipped:no_position_grid_close_short` per second during CB).
    /// 管線跳過策略平倉（未找到倉位）— 回滾交叉狀態。
    /// FIX-C：不回滾 last_trade_ms。保留發送時間戳使現有 30s 冷卻繼續有效，防止下一 tick 立即重發。
    /// 舊行為：回滾 last_trade_ms → 冷卻失效 → 每 tick 重發 Close（CB 期間每秒數百條 close_skipped）。
    fn on_close_skipped(&mut self, symbol: &str) {
        if let Some(prev) = self.prev_cross_idx.get(symbol) {
            match prev {
                Some(idx) => {
                    self.last_cross_idx.insert(symbol.to_string(), *idx);
                }
                None => {
                    self.last_cross_idx.remove(symbol);
                }
            }
        }
        // NOTE: last_trade_ms intentionally NOT rolled back here (FIX-C).
        // last_trade_ms 此處刻意不回滾（FIX-C）。
        info!(strategy = "grid_trading", %symbol, "close skipped: cross state rolled back, trade_ms preserved / 平倉跳過：交叉狀態已回滾，trade_ms 保留");
    }

    /// RC-04: Revert per-symbol net_inventory, last_cross_idx, last_trade_ms on rejection.
    /// M-2: Also arm a per-symbol rejection backoff using the emit timestamp captured
    /// in `last_trade_ms` BEFORE the rollback overwrites it. This breaks tight retry
    /// loops on persistent guardian/cost_gate rejections without losing state coherence.
    /// RC-04：拒絕時回滾該幣種的 net_inventory、last_cross_idx、last_trade_ms。
    /// M-2：同時使用回滾前 `last_trade_ms` 中捕獲的發送時間戳設定該幣種拒絕退避。
    /// 在不破壞狀態一致性的前提下打破持續性 guardian/cost_gate 拒絕的緊湊重試迴圈。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;

        // M-2: Capture emit timestamp before rollback overwrites it.
        // M-2：在回滾覆蓋之前捕獲發送時間戳。
        if let Some(&emit_ts) = self.last_trade_ms.get(sym) {
            if emit_ts > 0 {
                self.reject_cooldown_until_ms
                    .insert(sym.to_string(), emit_ts + self.reject_backoff_ms);
            }
        }

        if let Some(prev) = self.prev_cross_idx.get(sym) {
            match prev {
                Some(idx) => {
                    self.last_cross_idx.insert(sym.to_string(), *idx);
                }
                None => {
                    self.last_cross_idx.remove(sym);
                }
            }
        }
        if let Some(&inv) = self.prev_inventory.get(sym) {
            self.net_inventory.insert(sym.to_string(), inv);
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.last_trade_ms.remove(sym);
            } else {
                self.last_trade_ms.insert(sym.to_string(), ts);
            }
        }
    }

    fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let sym = ctx.symbol;

        // Per-symbol price history for OU model
        let history = self.price_history.entry(sym.to_string()).or_default();
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
                    ctx.price * (1.0 - self.adaptive_range_pct),
                    ctx.price * (1.0 + self.adaptive_range_pct),
                ),
            };
            self.grid_levels.insert(
                sym.to_string(),
                grid_helpers::build_levels(lower, upper, self.grid_count, &self.spacing_mode),
            );
        }

        // Per-symbol health check every health_check_interval ticks.
        // 每幣種每 health_check_interval 個 tick 執行健康檢查。
        let ticks = self
            .ticks_since_health_check
            .entry(sym.to_string())
            .or_insert(0);
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
        // QC-H9: ou_update_interval configurable (was hardcoded 50)
        if hist_len > 0 && self.ou_update_interval > 0 && hist_len % self.ou_update_interval == 0 {
            self.update_ou_spacing(sym);
        }

        // EDGE-P1-1: Trending hard stop — suppress new grid entries in strong trends.
        // ADX > 30 or Hurst regime = "trending" → grid is structurally disadvantaged,
        // return empty (existing positions exit via normal risk/stop path).
        // EDGE-P1-1：趨勢硬停 — 強趨勢中暫停 grid 新開倉。
        // ADX > 30 或 Hurst regime = "trending" → grid 結構性不利，返回空。
        if let Some(ind) = ctx.indicators {
            let adx_val = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
            let is_trending_regime = ind
                .hurst
                .as_ref()
                .map(|h| h.regime.as_str() == "trending")
                .unwrap_or(false);
            if adx_val > 30.0 || is_trending_regime {
                return vec![];
            }
        }

        // M-2: Honor per-symbol rejection backoff before any cross detection.
        // M-2：在任何 cross 偵測前遵守該幣種的拒絕退避。
        if let Some(&until) = self.reject_cooldown_until_ms.get(sym) {
            if ctx.timestamp_ms < until {
                return vec![];
            }
        }

        let last_ms = self.last_trade_ms.get(sym).copied().unwrap_or(0);
        // A3: Trend-adaptive cooldown — scales 1x→6x in trending markets.
        // A3：趨勢自適應冷卻 — 趨勢市場中 1x→6x 縮放。
        let effective_cooldown = self.compute_trend_adjusted_cooldown(ctx.indicators);
        if last_ms > 0 && ctx.timestamp_ms < last_ms + effective_cooldown {
            return vec![];
        }

        let idx = self.nearest_grid_idx(sym, ctx.price);
        if self.last_cross_idx.get(sym) == Some(&idx) {
            return vec![];
        }

        let prev_idx = self.last_cross_idx.get(sym).copied().unwrap_or(idx);

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        self.prev_cross_idx
            .insert(sym.to_string(), self.last_cross_idx.get(sym).copied());
        let cur_inventory = self.net_inventory.get(sym).copied().unwrap_or(0.0);
        self.prev_inventory.insert(sym.to_string(), cur_inventory);
        self.prev_last_trade_ms.insert(sym.to_string(), last_ms);

        self.last_cross_idx.insert(sym.to_string(), idx);

        let mut intents = Vec::new();

        // Dynamic confidence: grid thrives in ranging + narrow BB, suffers in trending.
        // 動態信心：grid 在 ranging + 窄 BB 中表現好，trending 中表現差。
        // CONF-D: apply per-strategy scale.
        let conf = crate::tick_pipeline::on_tick_helpers::clamp_confidence(
            compute_grid_confidence(ctx.indicators) * self.conf_scale,
        );

        // EDGE-P2-3 Phase 1a: resolve entry order shape (Market vs PostOnly Limit).
        // Close path stays Market; only new-open intents use the maker path.
        // BUY offset below last_price; SELL offset above — so PostOnly always rests passively.
        // EDGE-P2-3 Phase 1a：決定入場單型（Market 或 PostOnly Limit）。平倉維持 Market；
        // 僅新開倉意圖走 maker 路徑。BUY 掛 last 下方、SELL 掛 last 上方，確保被動側。
        let maker_entry_for_buy = if self.use_maker_entry {
            let offset = self.maker_price_offset_bps / 10_000.0;
            (
                "limit".to_string(),
                Some(ctx.price * (1.0 - offset)),
                Some(TimeInForce::PostOnly),
            )
        } else {
            ("market".to_string(), None, None)
        };
        let maker_entry_for_sell = if self.use_maker_entry {
            let offset = self.maker_price_offset_bps / 10_000.0;
            (
                "limit".to_string(),
                Some(ctx.price * (1.0 + offset)),
                Some(TimeInForce::PostOnly),
            )
        } else {
            ("market".to_string(), None, None)
        };

        if idx < prev_idx {
            // Price crossed down → buy. If net_inventory < 0 (short), this closes short → Close.
            // Otherwise it's a new long → Open.
            // 價格下穿 → 買入。若 net_inventory < 0（空倉），為平空 → Close；否則新多 → Open。
            let (order_type, limit_price, time_in_force) = maker_entry_for_buy;
            let intent = OrderIntent {
                symbol: ctx.symbol.to_string(),
                is_long: true,
                qty: self.qty_per_grid,
                confidence: conf,
                strategy: self.name().into(),
                order_type,
                limit_price,
                // Grid has no confluence/persistence; builder fills 0.0.
                // Grid 無 confluence/persistence；builder 填 0。
                confluence_score: None,
                persistence_elapsed_ms: None,
                time_in_force,
            };
            if cur_inventory < 0.0 {
                intents.push(StrategyAction::Close {
                    symbol: ctx.symbol.to_string(),
                    confidence: conf,
                    reason: "grid_close_short".into(),
                });
            } else {
                intents.push(StrategyAction::Open(intent));
                *self.net_inventory.entry(sym.to_string()).or_insert(0.0) += self.qty_per_grid;
            }
            self.last_trade_ms.insert(sym.to_string(), ctx.timestamp_ms);
        } else if idx > prev_idx {
            // Price crossed up → sell. If net_inventory > 0 (long), this closes long → Close.
            // Otherwise it's a new short → Open.
            // 價格上穿 → 賣出。若 net_inventory > 0（多倉），為平多 → Close；否則新空 → Open。
            let (order_type, limit_price, time_in_force) = maker_entry_for_sell;
            let intent = OrderIntent {
                symbol: ctx.symbol.to_string(),
                is_long: false,
                qty: self.qty_per_grid,
                confidence: conf,
                strategy: self.name().into(),
                order_type,
                limit_price,
                // Grid has no confluence/persistence; builder fills 0.0.
                // Grid 無 confluence/persistence；builder 填 0。
                confluence_score: None,
                persistence_elapsed_ms: None,
                time_in_force,
            };
            if cur_inventory > 0.0 {
                intents.push(StrategyAction::Close {
                    symbol: ctx.symbol.to_string(),
                    confidence: conf,
                    reason: "grid_close_long".into(),
                });
            } else {
                intents.push(StrategyAction::Open(intent));
                *self.net_inventory.entry(sym.to_string()).or_insert(0.0) -= self.qty_per_grid;
            }
            self.last_trade_ms.insert(sym.to_string(), ctx.timestamp_ms);
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

    fn ctx(price: f64, ts: u64) -> TickContext<'static> {
        TickContext {
            symbol: "BTC",
            price,
            timestamp_ms: ts,
            indicators: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
        }
    }

    #[test]
    fn test_grid_creation() {
        // Grid levels are lazily initialized on first tick, not at construction.
        // 網格層級在首次 tick 時延遲初始化，不在構造時。
        let mut g = GridTrading::new(49000.0, 51000.0);
        assert!(
            g.grid_levels.is_empty(),
            "grid_levels should be empty before first tick"
        );
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
        assert!(
            *g.net_inventory.get("BTC").unwrap_or(&0.0) > 0.0,
            "inventory deferred: still positive before confirm"
        );

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
        assert_eq!(
            g.last_cross_idx.get("BTC").copied(),
            prev_cross,
            "cross state should be rolled back"
        );
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
        let btc_levels = g
            .grid_levels
            .get("BTC")
            .expect("BTC grid should be initialized on first tick");
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

    // ── G-SR-1 S3+S4: param_ranges + validation tests ──

    #[test]
    fn test_grid_param_ranges_count() {
        let ranges = GridTradingParams::param_ranges();
        // 4 original + 3 trend cooldown = 7
        assert_eq!(
            ranges.len(),
            7,
            "expected 7 param ranges, got {}",
            ranges.len()
        );
    }

    #[test]
    fn test_grid_param_ranges_cooldown_names() {
        let ranges = GridTradingParams::param_ranges();
        let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
        for expected in &[
            "adx_low_threshold",
            "adx_high_threshold",
            "max_cooldown_boost",
        ] {
            assert!(names.contains(expected), "missing param range: {expected}");
        }
    }

    #[test]
    fn test_grid_validate_default_ok() {
        assert!(GridTradingParams::default().validate().is_ok());
    }

    #[test]
    fn test_grid_validate_bad_adx_order() {
        let mut p = GridTradingParams::default();
        p.adx_low_threshold = 50.0;
        p.adx_high_threshold = 20.0; // low > high
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_grid_validate_equal_adx_thresholds() {
        let mut p = GridTradingParams::default();
        p.adx_low_threshold = 30.0;
        p.adx_high_threshold = 30.0; // equal = invalid
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_grid_validate_bad_cooldown_boost() {
        let mut p = GridTradingParams::default();
        p.max_cooldown_boost = 15.0; // > 10
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_grid_validate_negative_cooldown_boost() {
        let mut p = GridTradingParams::default();
        p.max_cooldown_boost = -1.0;
        assert!(p.validate().is_err());
    }

    // ── G-SR-1 S4: Trend cooldown unit tests (A3) ──

    #[test]
    fn test_trend_cooldown_no_indicators() {
        let g = GridTrading::new(49000.0, 51000.0);
        // None indicators → base cooldown (new() sets cooldown_ms=60_000)
        assert_eq!(g.compute_trend_adjusted_cooldown(None), 60_000);
    }

    #[test]
    fn test_trend_cooldown_low_adx_no_boost() {
        use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
        let snap = Box::leak(Box::new(IndicatorSnapshot {
            adx: Some(AdxResult {
                adx: 15.0,
                plus_di: 0.0,
                minus_di: 0.0,
            }),
            hurst: Some(HurstResult {
                hurst: 0.45,
                regime: "mean_reverting".into(),
            }),
            ..Default::default()
        }));
        let g = GridTrading::new(49000.0, 51000.0);
        // ADX=15 < adx_low(20) → factor=0, Hurst=0.45 < 0.50 → factor=0
        // trend_score=0, multiplier=1.0, cooldown=60_000
        assert_eq!(g.compute_trend_adjusted_cooldown(Some(snap)), 60_000);
    }

    #[test]
    fn test_trend_cooldown_high_adx_max_boost() {
        use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
        let snap = Box::leak(Box::new(IndicatorSnapshot {
            adx: Some(AdxResult {
                adx: 60.0,
                plus_di: 0.0,
                minus_di: 0.0,
            }),
            hurst: Some(HurstResult {
                hurst: 0.80,
                regime: "trending".into(),
            }),
            ..Default::default()
        }));
        let g = GridTrading::new(49000.0, 51000.0);
        // ADX=60 > adx_high(50) → factor=1.0, Hurst=0.80 > 0.75 → factor=1.0
        // trend_score=0.6*1+0.4*1=1.0, multiplier=1+5=6, cooldown=60_000*6=360_000
        let cd = g.compute_trend_adjusted_cooldown(Some(snap));
        assert_eq!(cd, 360_000, "expected 60_000*6 = 360_000, got {cd}");
    }

    #[test]
    fn test_trend_cooldown_mid_adx_partial_boost() {
        use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
        let snap = Box::leak(Box::new(IndicatorSnapshot {
            adx: Some(AdxResult {
                adx: 35.0,
                plus_di: 0.0,
                minus_di: 0.0,
            }),
            hurst: Some(HurstResult {
                hurst: 0.625,
                regime: "uncertain".into(),
            }),
            ..Default::default()
        }));
        let g = GridTrading::new(49000.0, 51000.0);
        // ADX=35: (35-20)/(50-20)=0.5, Hurst=0.625: (0.625-0.50)/0.25=0.5
        // trend_score=0.6*0.5+0.4*0.5=0.5, multiplier=1+2.5=3.5, cooldown=60_000*3.5=210_000
        let cd = g.compute_trend_adjusted_cooldown(Some(snap));
        assert_eq!(cd, 210_000, "expected 60_000*3.5 = 210_000, got {cd}");
    }

    // ── EDGE-P2-3 Phase 1a: PostOnly maker entry tests ──
    // ── EDGE-P2-3 Phase 1a：PostOnly maker 入場測試 ──

    /// Default constructor must keep `use_maker_entry = false` (root principle #6
    /// — failure default shrink). Cold-boot behavior stays on proven Market path.
    /// 默認構造必須保持 `use_maker_entry = false`（根原則 #6），冷啟動走已驗證 Market 路徑。
    #[test]
    fn test_grid_maker_disabled_by_default() {
        let g = GridTrading::new(49000.0, 51000.0);
        assert!(!g.use_maker_entry, "use_maker_entry must default to false");
        assert_eq!(
            g.maker_price_offset_bps, DEFAULT_MAKER_OFFSET_BPS,
            "maker_price_offset_bps must default to 1 bps"
        );
        let g2 = GridTrading::new_geometric(49000.0, 51000.0);
        assert!(!g2.use_maker_entry);
        let g3 = GridTrading::new_adaptive();
        assert!(!g3.use_maker_entry);
    }

    /// When maker disabled, buy intents keep order_type="market" + time_in_force=None
    /// (byte-identical legacy behavior).
    /// maker 關閉時，買入意圖維持 market + TIF=None（與舊行為 byte-identical）。
    #[test]
    fn test_grid_market_entry_when_maker_disabled() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        assert!(!g.use_maker_entry);
        g.on_tick(&ctx(50500.0, 0));
        let i = g.on_tick(&ctx(49500.0, 100_000));
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert_eq!(intent.order_type, "market");
                assert!(intent.limit_price.is_none());
                assert!(intent.time_in_force.is_none());
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    /// Buy on down-cross with maker enabled emits PostOnly Limit below last_price.
    /// 下穿買入時，maker 啟用 → PostOnly Limit 掛在 last_price 下方。
    #[test]
    fn test_grid_buy_postonly_below_last_price() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.use_maker_entry = true;
        g.maker_price_offset_bps = 1.0; // 1 bps
        g.on_tick(&ctx(50500.0, 0));
        let i = g.on_tick(&ctx(49500.0, 100_000));
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!(intent.is_long);
                assert_eq!(intent.order_type, "limit");
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                let lp = intent.limit_price.expect("limit_price set");
                let expected = 49500.0 * (1.0 - 1.0 / 10_000.0);
                assert!(
                    (lp - expected).abs() < 1e-9,
                    "buy PostOnly must be below last_price: got {lp}, expected {expected}"
                );
                assert!(lp < 49500.0, "buy limit must rest below last_price");
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    /// Sell on up-cross with maker enabled emits PostOnly Limit above last_price.
    /// 上穿賣出時，maker 啟用 → PostOnly Limit 掛在 last_price 上方。
    #[test]
    fn test_grid_sell_postonly_above_last_price() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.use_maker_entry = true;
        g.maker_price_offset_bps = 2.0; // 2 bps
        g.on_tick(&ctx(49500.0, 0));
        let i = g.on_tick(&ctx(50500.0, 100_000));
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!(!intent.is_long);
                assert_eq!(intent.order_type, "limit");
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                let lp = intent.limit_price.expect("limit_price set");
                let expected = 50500.0 * (1.0 + 2.0 / 10_000.0);
                assert!(
                    (lp - expected).abs() < 1e-9,
                    "sell PostOnly must be above last_price: got {lp}, expected {expected}"
                );
                assert!(lp > 50500.0, "sell limit must rest above last_price");
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    /// maker_price_offset_bps scales the limit price proportionally.
    /// maker_price_offset_bps 線性縮放限價。
    #[test]
    fn test_grid_maker_offset_scales_linearly() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.use_maker_entry = true;
        g.maker_price_offset_bps = 5.0; // 5 bps
        g.on_tick(&ctx(50500.0, 0));
        let i = g.on_tick(&ctx(49500.0, 100_000));
        match &i[0] {
            StrategyAction::Open(intent) => {
                let lp = intent.limit_price.unwrap();
                let expected = 49500.0 * (1.0 - 5.0 / 10_000.0);
                assert!((lp - expected).abs() < 1e-9);
            }
            other => panic!("expected Open, got {:?}", other),
        }
    }

    /// Close actions stay Market even when maker entry is enabled — Phase 1a scope
    /// intentionally excludes close path (PostOnly rejects would strand positions).
    /// 平倉維持 Market，即使 maker 入場啟用 — Phase 1a 刻意排除平倉路徑（避免 PostOnly 拒絕卡倉）。
    #[test]
    fn test_grid_close_stays_market_with_maker_enabled() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        g.use_maker_entry = true;
        g.maker_price_offset_bps = 1.0;
        // Build positive inventory via Open
        g.on_tick(&ctx(50500.0, 0));
        g.on_tick(&ctx(49500.0, 100_000));
        // Sell with positive inventory → Close (not Open)
        let i = g.on_tick(&ctx(50500.0, 200_000));
        match &i[0] {
            StrategyAction::Close { reason, .. } => {
                assert_eq!(reason, "grid_close_long");
                // Close variant carries no order_type field — it's always Market at dispatch.
            }
            other => panic!("expected Close, got {:?}", other),
        }
    }

    /// update_params round-trips maker fields so Agent IPC can toggle at runtime.
    /// update_params 來回保留 maker 欄位，Agent IPC 可運行時切換。
    #[test]
    fn test_grid_update_params_roundtrips_maker_fields() {
        let mut g = GridTrading::new(49000.0, 51000.0);
        let mut params = g.get_params();
        assert!(!params.use_maker_entry);
        params.use_maker_entry = true;
        params.maker_price_offset_bps = 3.0;
        g.update_params(params).expect("update_params");
        let p2 = g.get_params();
        assert!(p2.use_maker_entry);
        assert!((p2.maker_price_offset_bps - 3.0).abs() < 1e-9);
        assert!(g.use_maker_entry);
    }
}
