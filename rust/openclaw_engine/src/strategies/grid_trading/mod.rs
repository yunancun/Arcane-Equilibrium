//! Grid Trading Strategy V2 — OU dynamic spacing + fee floor + geometric mode + health check.
//! 網格交易策略 V2 — OU 動態間距 + 手續費地板 + 幾何模式 + 健康檢查。
//!
//! MODULE_NOTE (EN): Grid levels between lower/upper bounds. Buy on down-cross,
//!   sell on up-cross. OU model: optimal spacing = σ·√(2/θ) with floor = 2× round-trip fee.
//!   Geometric mode: equal ratio gaps (better for crypto). Inventory drift health check.
//!
//!   GRID-TRADING-MOD-SPLIT-1 (2026-04-23): pre-split file was 1729 lines
//!   (over CLAUDE.md §九's 1200-line hard cap). Split into this `mod.rs`
//!   (struct + `Strategy` impl thin delegators + free fns + constants +
//!   `GridHealth` enum) plus six sibling child modules:
//!     - `params.rs`       — `GridTradingParams` + Default + `StrategyParams` impl
//!     - `constructors.rs` — `new` / `new_geometric` / `new_adaptive*` + `set_fee_rate` + `update_params` + `get_params`
//!     - `grid_layout.rs`  — `nearest_grid_idx` / `check_health` / `rebalance` / `compute_ou_step` / `update_ou_spacing`
//!     - `position_mgmt.rs`— `compute_trend_adjusted_cooldown` + `on_external_close/confirmed/skipped/rejection` impls
//!     - `signal.rs`       — `on_tick_impl` main per-tick dispatch
//!     - `tests.rs`        — 36 existing unit tests (byte-identical)
//!   Each sibling uses the `impl super::GridTrading { ... }` pattern; the
//!   Strategy trait impl here delegates to `_impl` helpers declared in those
//!   sibling files as `pub(super) fn`. Logic / signatures / public API
//!   preserved byte-identical to pre-split.
//! MODULE_NOTE (中)：在上下界之間設置網格。下穿買入，上穿賣出。
//!   OU 模型：最佳間距 = σ·√(2/θ)，地板 = 2× 來回手續費。
//!   幾何模式：等比間距（更適合加密貨幣）。含庫存漂移健康檢查。
//!
//!   GRID-TRADING-MOD-SPLIT-1（2026-04-23）：拆前檔案 1729 行（超過 CLAUDE.md
//!   §九 1200 行硬上限）。拆為本 `mod.rs`（struct + `Strategy` impl 薄派發 +
//!   自由函式 + 常數 + `GridHealth` enum）加六個 sibling child-module：
//!     - `params.rs`       — `GridTradingParams` + Default + `StrategyParams` impl
//!     - `constructors.rs` — `new` / `new_geometric` / `new_adaptive*` + `set_fee_rate` + `update_params` + `get_params`
//!     - `grid_layout.rs`  — `nearest_grid_idx` / `check_health` / `rebalance` / `compute_ou_step` / `update_ou_spacing`
//!     - `position_mgmt.rs`— `compute_trend_adjusted_cooldown` + `on_external_close/confirmed/skipped/rejection` impls
//!     - `signal.rs`       — `on_tick_impl` 主要逐 tick 派發
//!     - `tests.rs`        — 36 個既有單元測試（逐字節相同）
//!   各 sibling 使用 `impl super::GridTrading { ... }` pattern；此處的 Strategy
//!   trait impl 派發到 sibling 中以 `pub(super) fn` 宣告的 `_impl` helper。
//!   邏輯 / 簽名 / 公開 API 與拆前逐字節相同。

use std::collections::{HashMap, HashSet};

use crate::intent_processor::OrderIntent;
use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};
use openclaw_core::indicators::IndicatorSnapshot;

mod constructors;
mod grid_layout;
mod params;
mod position_mgmt;
mod signal;

#[cfg(test)]
mod tests;

pub use params::GridTradingParams;

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

pub(crate) const DEFAULT_GRID_COUNT: usize = 10;
/// Large default qty — intent_processor P1 sizing will cap to actual risk budget.
/// 大默認 qty — intent_processor P1 sizing 會裁剪到實際風險預算。
pub(crate) const DEFAULT_QTY_PER_GRID: f64 = 1e9;
/// M-2 (2026-04-11) audit fix: per-symbol backoff after a rejection so the strategy
/// doesn't tight-loop re-emitting the same intent every tick. The rollback in
/// `on_rejection` restores prev_cross_idx, which immediately re-fires next tick
/// because price has not moved. 30s gives Guardian/cost_gate state a chance to
/// change before retry.
/// M-2 審計修復：拒絕後每幣種退避，避免策略每 tick 重發同一意圖緊湊迴圈。
/// `on_rejection` 中的回滾會還原 prev_cross_idx，下一 tick 立即重發（價格未動）。
/// 30 秒給 Guardian/cost_gate 狀態變化的機會再重試。
pub(crate) const REJECT_BACKOFF_MS: u64 = 30_000;
/// FIX-25: Default fallback fee rate; prefer runtime `taker_fee_rate` via `set_fee_rate()`.
/// FIX-25：默認回退費率；優先使用 `set_fee_rate()` 設定的運行時 taker_fee_rate。
pub(crate) const DEFAULT_FEE_PCT: f64 = 0.00055;
/// Default adaptive range: ±10% of current price for initial/rebalance grid.
/// 默認自適應範圍：當前價格 ±10% 用於初始化/再平衡網格。
pub(crate) const ADAPTIVE_RANGE_PCT: f64 = 0.10;

/// EDGE-P2-3 Phase 1a: Default PostOnly price offset in basis points.
/// BUY limit placed at `last_price * (1 - offset/10_000)`, SELL at `last_price * (1 + offset/10_000)`
/// so the order rests on the passive side of the book. 1 bps is tight enough to
/// still fill on normal ranging markets while avoiding accidental crossings.
/// EDGE-P2-3 Phase 1a：PostOnly 限價偏移（bps）。BUY 以 last×(1−offset/萬)，
/// SELL 以 last×(1+offset/萬)，確保掛單停在被動側。1 bps 在常規震盪中仍能成交。
pub(crate) const DEFAULT_MAKER_OFFSET_BPS: f64 = 1.0;

/// EDGE-P2-3 Phase 1a: Default for `use_maker_entry`. Root principle #6 —
/// failure default shrink: cold-boot stays on proven Market path until the
/// per-env TOML opts in.
/// EDGE-P2-3 Phase 1a：`use_maker_entry` 默認值。根原則 #6（失敗默認收縮），
/// 冷啟動維持已驗證的 Market 路徑，待各環境 TOML 顯式啟用。
pub(crate) const DEFAULT_USE_MAKER_ENTRY: bool = false;

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
pub(crate) const DEFAULT_MAKER_LIMIT_TIMEOUT_MS: u64 = 45_000;

/// EDGE-P2-3 Phase 1B-3.1: Hard lower bound — below this, maker fills too
/// rarely to justify the cancel round-trip cost.
/// EDGE-P2-3 Phase 1B-3.1：硬下限，低於此值成交機率太低，不值得一次 cancel 往返。
pub(crate) const MAKER_LIMIT_TIMEOUT_MIN_MS: u64 = 15_000;

/// EDGE-P2-3 Phase 1B-3.1: Hard upper bound — above this, a resting order is
/// more stale inventory than price discovery.
/// EDGE-P2-3 Phase 1B-3.1：硬上限，超出後掛單已屬過期庫存而非價格發現。
pub(crate) const MAKER_LIMIT_TIMEOUT_MAX_MS: u64 = 300_000;

/// EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — close-side reject cooldown
/// 預設時長（取代既有 entry-side `reject_cooldown_ms`），對應 spec v1.2 §6.1
/// 的 close cooldown 表「其他 reject → 1min」分支。當 close-maker 路徑被
/// Bybit 以 PostOnly 以外的原因（如 Other / FokCancel）拒絕時，arm 該 symbol
/// 的 close cooldown 1 分鐘，避免下一 tick 同條件再撞拒絕。
pub(crate) const CLOSE_REJECT_COOLDOWN_DEFAULT_MS: u64 = 60_000;

/// EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — close-side TooManyPending
/// 帳戶級背壓固定退避時長，對應 spec v1.2 §6.1 表中 close TooManyPending
/// 5min 分支（PM Wave 2b 任務明文要求 5min 固定值；spec §5.4 BB-MF-2 的
/// per-symbol dynamic backoff (1s exp → 60s 上限 + global cascade) 屬獨立
/// 工作項，不在本 prereq IMPL scope 內）。
pub(crate) const CLOSE_REJECT_COOLDOWN_TOO_MANY_PENDING_MS: u64 = 300_000;

/// Clamp a maker-limit timeout value into the strategy's supported range.
/// Centralised so TOML binding + factory + tests all agree on the bounds.
/// 將 maker-limit 超時值 clamp 至策略支援區間。集中處理以保 TOML binding /
/// 工廠 / 測試皆一致。
pub(crate) fn clamp_maker_limit_timeout_ms(v: u64) -> u64 {
    v.clamp(MAKER_LIMIT_TIMEOUT_MIN_MS, MAKER_LIMIT_TIMEOUT_MAX_MS)
}

// GridSpacingMode moved to grid_helpers.rs (A0-a extraction), re-exported for compatibility.
// GridSpacingMode 已移至 grid_helpers.rs（A0-a 提取），此處重導出保持兼容。
pub use crate::strategies::grid_helpers::GridSpacingMode;

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
    pub(super) active: bool,
    /// Template grid bounds for non-adaptive constructors (None = adaptive / ±10%).
    /// 非自適應構造函數的模板邊界（None = 自適應 / ±10%）。
    pub(super) template_bounds: Option<(f64, f64)>,
    /// Per-symbol grid levels. Initialized lazily on first tick per symbol.
    /// 每幣種網格層級。每個 symbol 首次 tick 時延遲初始化。
    pub(super) grid_levels: HashMap<String, Vec<f64>>,
    /// Per-symbol last crossed grid index.
    /// 每幣種最後穿越的網格索引。
    pub(super) last_cross_idx: HashMap<String, usize>,
    /// Per-symbol net inventory tracking.
    /// 每幣種淨庫存追蹤。
    pub(super) net_inventory: HashMap<String, f64>,
    /// Max net inventory — reserved for future Agent position sizing control (Phase 3a).
    /// 最大淨庫存 — 預留給未來 Agent 倉位管理（Phase 3a）。
    #[allow(dead_code)]
    pub(super) max_inventory: f64,
    /// Per-symbol last trade timestamp for cooldown.
    /// 每幣種最後交易時間戳（用於冷卻）。
    pub(super) last_trade_ms: HashMap<String, u64>,
    /// E5-P2-4: Now factory-wired from TOML `strategy_params_*.toml::grid_trading.cooldown_ms`.
    /// E5-P2-4：現透過工廠自 TOML（`grid_trading.cooldown_ms`）接線。
    pub(crate) cooldown_ms: u64,
    pub(super) qty_per_grid: f64,
    // OU parameters / OU 參數 — per-symbol price history
    pub(super) price_history: HashMap<String, Vec<f64>>,
    pub(super) ou_lookback: usize,
    // Spacing mode / 間距模式
    pub(crate) spacing_mode: GridSpacingMode,
    // Health check fields / 健康檢查欄位
    /// How often (in ticks) to run health check / 每隔多少 tick 執行健康檢查
    pub(crate) health_check_interval: usize,
    /// Per-symbol ticks elapsed since last health check.
    /// 每幣種距上次健康檢查已過的 tick 數。
    pub(super) ticks_since_health_check: HashMap<String, usize>,
    /// Per-symbol consecutive ticks price was out of grid range.
    /// 每幣種連續價格超出網格範圍的 tick 數。
    pub(super) out_of_range_count: HashMap<String, usize>,
    /// Max allowed consecutive out-of-range ticks before rebalance / 觸發再平衡前允許的最大連續超出範圍次數
    pub(crate) max_out_of_range: usize,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    pub(super) prev_cross_idx: HashMap<String, Option<usize>>,
    pub(super) prev_inventory: HashMap<String, f64>,
    pub(super) prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    pub(super) conf_scale: f64,
    /// FIX-06: Configurable grid level count (was hardcoded DEFAULT_GRID_COUNT).
    /// FIX-06：可配置的網格層級數（原硬編碼 DEFAULT_GRID_COUNT）。
    pub(crate) grid_count: usize,
    /// FIX-25: One-way taker fee rate for OU spacing floor calculation.
    /// FIX-25：單邊 taker 手續費率，用於 OU 間距地板計算。
    pub(super) fee_rate: f64,
    /// M-2 + EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — entry-side per-symbol
    /// rejection backoff deadline (epoch ms)。原 `reject_cooldown_until_ms`
    /// 拆分為 entry / close 兩條獨立 map 以解決 BB-MF-3「entry reject 凍結
    /// close path silent degradation」（AMD-2026-05-15-02 §8 IMPL Prereq 6）。
    /// 由 `on_rejection_impl`（governance 拒絕）+ `on_post_only_rejected_impl`
    /// （PostOnly entry 拒絕）寫入；`on_tick` entry path 在 would_open 已知
    /// 後檢查，僅阻擋 `Open` 發送，不影響同 tick 的 `Close` emission。
    pub(super) reject_cooldown_entry_until_ms: HashMap<String, u64>,
    /// EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — close-side per-symbol
    /// rejection backoff deadline (epoch ms)。Phase 1b close-maker-first
    /// 啟用後由 close-side dispatcher 透過 `arm_close_cooldown` 寫入，
    /// 路由規則對應 spec v1.2 §6.1：
    ///   - `MakerRejectionCategory::TooManyPending` → 5min（固定，spec §5.4
    ///     dynamic backoff 屬獨立工作項，本 prereq 不實作）
    ///   - `MakerRejectionCategory::PostOnlyCross` → no-op（per spec §5.3
    ///     Race C：直接走 market，不進 close cooldown）
    ///   - 其他類別（FokCancel / SelfCancel / Other） → 1min default
    /// 本 prereq commit 僅完成「資料欄位 + 寫入 helper + 隔離測試」，close
    /// path 真正進 cooldown gate 的接線留給 Phase 1b 主軸 IMPL（預期 close
    /// emission 處檢查此 map，cooldown 期內走 market fallback）。
    pub(super) reject_cooldown_close_until_ms: HashMap<String, u64>,
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
    /// G7-09c Phase 1: ticks INSIDE the inside quote at which the BBO-aware
    /// PostOnly limit sits. See `params.rs::maker_price_buffer_ticks`. Bounded
    /// `[0, 10]` by `validate()`.
    /// G7-09c Phase 1：BBO-aware PostOnly 限價離 inside quote 的 tick 數，
    /// 範圍 `[0, 10]` 由 `validate()` 限制。
    pub(crate) maker_price_buffer_ticks: u32,
    /// G7-09c Phase 2 (FIX-G7-09C-PHASE2-WIRE-1B3): cooldown duration set
    /// in `on_post_only_rejected` after Bybit rejects a PostOnly maker
    /// entry. Bounded `[5_000, 600_000]` by `validate()`. Distinct from
    /// `reject_backoff_ms` which fires on governance pipeline rejection.
    /// Consumed by `signal.rs` via the entry-side cooldown guard
    /// (`reject_cooldown_entry_until_ms`，BB-MF-3 重命名 2026-05-16)。
    /// G7-09c Phase 2：交易所拒絕 PostOnly 後設冷卻時長，由
    /// `on_post_only_rejected` 寫入 `reject_cooldown_entry_until_ms` map；
    /// `signal.rs` entry path check 此 map，僅阻擋 `Open` 發送。
    pub(crate) reject_cooldown_ms: u64,
    /// Minimum grid step in bps of anchor price, applied after OU spacing.
    /// OU spacing 後套用的最小網格步長（錨定價格 bps）。
    pub(crate) min_grid_step_bps: f64,
    /// Multiplier on the round-trip fee floor in OU spacing.
    /// OU spacing 中往返費用地板倍率。
    pub(crate) cost_floor_multiplier: f64,
    /// G2-04: Operator-maintained per-symbol no-new-grid-entry list. Close
    /// paths stay enabled so existing exposure can still be reduced.
    /// G2-04：operator 維護的逐 symbol 暫停新 grid 入場清單；平倉路徑仍啟用。
    pub(crate) blocked_symbols: HashSet<String>,
    /// Per-symbol close timestamps used by the churn breaker.
    /// churn breaker 使用的逐 symbol 平倉時間戳。
    pub(super) churn_breaker_close_times: HashMap<String, Vec<u64>>,
    /// Per-symbol deadline before which new grid entries are suppressed.
    /// 逐 symbol 新 grid 入場暫停截止時間。
    pub(super) churn_breaker_until_ms: HashMap<String, u64>,
    /// Churn breaker master toggle. / churn breaker 主開關。
    pub(crate) churn_breaker_enabled: bool,
    /// Churn breaker close lookback window. / churn breaker 平倉回看窗口。
    pub(crate) churn_breaker_window_ms: u64,
    /// Number of closes inside the window required to trip. / 觸發所需 close 次數。
    pub(crate) churn_breaker_close_count: usize,
    /// Cooldown applied to new entries after trip. / 觸發後新入場冷卻。
    pub(crate) churn_breaker_cooldown_ms: u64,
}

// build_linear_levels, build_geometric_levels, build_levels moved to grid_helpers.rs (A0-a)
// 建構函數已移至 grid_helpers.rs（A0-a 提取）

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

    /// W-AUDIT-8a Phase A spec §3 Phase A Deliverable #3：
    /// `grid_trading`：`[Ta1m]`（best_bid/ask 屬 TickContext 不屬 AlphaSurface）。
    ///
    /// Sprint N+1 W2：宣告 `CrossAsset` tag 表示本策略在 BtcLeadLagPanel
    /// 可用時用它作 entry direction bias；surface 無 panel 時保留既有 TA/grid
    /// 行為（demo/live fence 仍由 step_4_5_dispatch 控制）。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::Ta1m, AlphaSourceTag::CrossAsset];
        TAGS
    }

    /// Reset per-symbol net_inventory on external close (risk-stop) to prevent desync.
    /// 外部平倉（風控止損）時重設該幣種 net_inventory，防止與 paper_state 脫鉤。
    fn on_external_close(&mut self, symbol: &str) {
        self.on_external_close_impl(symbol);
    }

    /// W7-5 part 1：grid_trading 用 `net_inventory: HashMap<String, f64>` 而非
    /// boolean position；entry path 路徑 inventory 已在 `signal.rs:185`
    /// `self.net_inventory.insert(sym, inv)` 隨 cross signal 寫入；fill confirmed
    /// 後 inventory 不需再次同步（idempotent）。on_fill 此處 W7-4 §1 verdict =
    /// LOW（M-2 backoff + churn breaker 已護），保留 default no-op + tracing 提醒
    /// 而不重複寫 inventory（避免與 entry path qty_per_grid 偏移計算相撞）。
    fn on_fill(&mut self, intent: &OrderIntent, _fill: &openclaw_core::execution::FillResult) {
        // grid_trading inventory 由 entry path 自管，on_fill 不重複寫。
        // 留 trace 便於 debug：fill 路徑與既有 inventory model 不對齊時可診斷。
        tracing::trace!(
            target: "grid_trading",
            symbol = %intent.symbol,
            is_long = intent.is_long,
            current_inventory = self.net_inventory.get(&intent.symbol).copied().unwrap_or(0.0),
            "on_fill: inventory unchanged (W7-5 part 1, by-design no-op for inventory model)"
        );
    }

    /// W7-5 part 2：bootstrap 階段從 paper_state 重建 `self.net_inventory`。
    ///
    /// 過濾條件：`pos.owner_strategy == "grid_trading"`；is_long → +qty，is_short → -qty。
    /// 重啟後 paper_state 已由 bootstrap 種入；此處讓 grid 知道既有部位數量，
    /// 避免 cold-start 時把已存倉位視為 0 inventory 而產生與真實狀態偏差的 cross signal。
    fn import_positions(&mut self, paper_state: &crate::paper_state::PaperState) {
        let mut imported = 0_usize;
        for pos in paper_state.positions() {
            if pos.owner_strategy == self.name() {
                let signed_qty = if pos.is_long { pos.qty } else { -pos.qty };
                self.net_inventory.insert(pos.symbol.clone(), signed_qty);
                imported += 1;
            }
        }
        if imported > 0 {
            tracing::info!(
                strategy = "grid_trading",
                imported,
                "W7-5 import_positions: rebuilt self.net_inventory from paper_state \
                 / 從 paper_state 重建 self.net_inventory"
            );
        }
    }

    /// Pipeline confirmed a strategy-emitted Close was executed — adjust per-symbol inventory.
    /// 管線確認策略平倉已執行 — 調整該幣種庫存。
    fn on_close_confirmed(&mut self, symbol: &str) {
        self.on_close_confirmed_impl(symbol);
    }

    /// Pipeline skipped a strategy-emitted Close (no position found) — roll back cross state.
    /// 管線跳過策略平倉（未找到倉位）— 回滾交叉狀態。
    fn on_close_skipped(&mut self, symbol: &str) {
        self.on_close_skipped_impl(symbol);
    }

    /// RC-04: Revert per-symbol net_inventory, last_cross_idx, last_trade_ms on rejection.
    /// RC-04：拒絕時回滾該幣種的 net_inventory、last_cross_idx、last_trade_ms。
    fn on_rejection(&mut self, intent: &OrderIntent, reason: &str) {
        self.on_rejection_impl(intent, reason);
    }

    /// EDGE-P2-3 Phase 1B-3: exchange-side PostOnly maker rejection callback.
    /// 此 callback 預期由「PostOnly maker entry」路徑觸發（spec v1.2 §6.1 + §6.2）；
    /// BB-MF-3 (2026-05-16) 後僅寫入 entry cooldown map，不影響 close path。
    /// EDGE-P2-3 Phase 1B-3：交易所側 PostOnly maker entry 拒絕回調；
    /// 寫入 `reject_cooldown_entry_until_ms`，與 `reject_cooldown_close_until_ms`
    /// 互不影響。
    fn on_post_only_rejected(
        &mut self,
        symbol: &str,
        ts_ms: i64,
        category: &crate::strategies::maker_rejection::MakerRejectionCategory,
    ) {
        self.on_post_only_rejected_impl(symbol, ts_ms, category);
    }

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        self.on_tick_impl(ctx, surface)
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let p: GridTradingParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(p)
    }
    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }
    fn param_ranges_json(&self) -> String {
        use crate::strategies::StrategyParams;
        serde_json::to_string(&GridTradingParams::param_ranges()).unwrap_or_default()
    }
    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }
    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }
}

// EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — close-side cooldown public API。
// 不放在 `Strategy` trait（避免影響 4 個非 grid 策略 default impl 與 Box<dyn>
// dispatcher）；Phase 1b 主軸如需擴及他策略另議。
impl GridTrading {
    /// 對外暴露的 close-side maker rejection cooldown 寫入入口。Phase 1b
    /// 主軸 IMPL 後由 close dispatcher 觸發；本 prereq commit 提供完整入口
    /// + 測試覆蓋 + 路由邏輯，但不接線生產 dispatcher（commands.rs 仍
    /// hard-coded market）。實作細節見 `position_mgmt::arm_close_cooldown_impl`。
    pub fn arm_close_cooldown(
        &mut self,
        symbol: &str,
        ts_ms: i64,
        category: &crate::strategies::maker_rejection::MakerRejectionCategory,
    ) {
        self.arm_close_cooldown_impl(symbol, ts_ms, category);
    }
}
