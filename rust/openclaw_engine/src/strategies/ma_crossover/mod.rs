//! MA Crossover Strategy V2 — KAMA + ADX filter + Hurst regime filter + multi-TF confirmation.
//! MA 交叉策略 V2 — 快慢 KAMA 交叉 + ADX 過濾 + 赫斯特狀態過濾 + 多時間框架確認。
//!
//! MODULE_NOTE (EN): Fast/slow KAMA crossover with ADX trending filter, Hurst
//!   regime gating, and multi-timeframe confirmation for reduced false signals.
//!   Split into child-module files by E5-P2-4c (2026-04-23) to honour CLAUDE.md
//!   §九 1200-line hard cap. This file retains types (`MaCrossoverParams`,
//!   `MaCrossover`), `impl Default` / `impl StrategyParams` / `impl MaCrossoverParams`
//!   for the parameter bundle, the struct-internal ctor `MaCrossover::new`, and
//!   sub-module declarations. Methods live in sibling impl files (`config.rs`,
//!   `helpers.rs`, `strategy_impl.rs`); tests live in `tests.rs` /
//!   `tests_a1_a2_maker.rs`. Zero-logic split — public API unchanged.
//! MODULE_NOTE (中)：E5-P2-4c（2026-04-23）依 §九 1200 行硬上限拆分；本檔保留
//!   參數型別與 struct（`MaCrossoverParams` / `MaCrossover`）、`Default` /
//!   `StrategyParams` / `MaCrossoverParams` 的 impl、以及 `MaCrossover::new` 建構子
//!   與子模組宣告。方法定義移至 sibling `config.rs` / `helpers.rs` /
//!   `strategy_impl.rs`；測試移至 `tests.rs` / `tests_a1_a2_maker.rs`。零邏輯變更，
//!   對外 API 不變。

use std::collections::HashMap;

use super::common::{ConfidenceBuilder, PerSymbolState, TrendCooldown};
use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{ParamRange, StrategyParams};

mod config;
mod helpers;
mod strategy_impl;

#[cfg(test)]
mod tests;
#[cfg(test)]
mod tests_a1_a2_maker;

/// Tunable parameters for MA Crossover strategy (Phase 3a AGT-1).
/// MA 交叉策略的可調參數。
#[derive(Debug, Clone, serde::Serialize, serde::Deserialize)]
#[serde(default)]
pub struct MaCrossoverParams {
    pub cooldown_ms: u64,
    pub adx_threshold: f64,
    pub default_qty: f64,
    pub regime_filter_enabled: bool,
    pub higher_tf_alpha: f64,
    // ── G-SR-1 confluence + persistence fields (A0-c) ──
    // ── G-SR-1 匯流 + 持續性欄位（A0-c）──
    /// Minimum signal persistence before entry (ms). / 入場前信號最小持續時間（ms）。
    pub min_persistence_ms: u64,
    /// Minimum order notional to emit intent (USD). / 發出 intent 的最小名義值（USD）。
    pub min_notional_usd: f64,
    /// Confluence scoring weights + thresholds (trend profile). / 匯流評分權重 + 閾值（趨勢配置）。
    pub weight_adx: f64,
    pub weight_regime: f64,
    pub weight_volume: f64,
    pub weight_momentum: f64,
    pub adx_floor: f64,
    pub confluence_threshold_no_trade: f64,
    pub confluence_threshold_light: f64,
    pub confluence_threshold_full: f64,
    /// A2: Trend-adaptive cooldown multiplier cap. effective_cooldown_ms =
    /// cooldown_ms × (1 + trend_score × max_cooldown_boost). Default 3.0 →
    /// cooldown scales 1x→4x in strong trends (ADX≥2.5×adx_threshold + Hurst≥0.75).
    /// A2：趨勢自適應冷卻倍率上限。strong trend 下冷卻 1x→4x（預設 3.0）。
    pub max_cooldown_boost: f64,
    /// EDGE-P2-3 Phase 2+: emit PostOnly Limit entries to pay maker fees.
    /// Default `false` (root principle #6).
    /// EDGE-P2-3 Phase 2+：入場改發 PostOnly Limit 以支付 maker 費率；默認 false。
    pub use_maker_entry: bool,
    /// EDGE-P2-3 Phase 2+: bps offset from last_price for PostOnly limit placement.
    /// EDGE-P2-3 Phase 2+：PostOnly 限價偏移（bps）。
    pub maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 2+: ms a resting PostOnly maker order may sit before sweep.
    /// Clamped to [15_000, 300_000] on assignment.
    /// EDGE-P2-3 Phase 2+：PostOnly 掛單最長停留時間（毫秒），寫入時 clamp。
    pub maker_limit_timeout_ms: u64,
    /// G7-09c Phase 1: ticks INSIDE the inside quote at which the BBO-aware
    /// PostOnly limit sits. Default 1 (one tick more passive than best_bid/ask).
    /// `maker_price_offset_bps` is now the fallback-only path used when BBO or
    /// tick_size are unavailable (cold-start / instrument cache miss). Bounded
    /// `[0, 10]` by `validate()`.
    /// G7-09c Phase 1：BBO-aware PostOnly 限價離 inside quote 的 tick 數，預設 1
    /// （比 best_bid/ask 退一 tick 更被動）。`maker_price_offset_bps` 退化為
    /// BBO 不可得時的 fallback offset。`validate()` 限制 `[0, 10]`。
    pub maker_price_buffer_ticks: u32,
}

impl Default for MaCrossoverParams {
    fn default() -> Self {
        let cc = ConfluenceConfig::default(); // trend profile
        Self {
            cooldown_ms: 300_000,
            adx_threshold: 20.0,
            default_qty: 1e9,
            regime_filter_enabled: true,
            higher_tf_alpha: 0.003,
            min_persistence_ms: 180_000,
            min_notional_usd: 10.0,
            weight_adx: cc.weight_adx,
            weight_regime: cc.weight_regime,
            weight_volume: cc.weight_volume,
            weight_momentum: cc.weight_momentum,
            adx_floor: cc.adx_floor,
            confluence_threshold_no_trade: cc.threshold_no_trade,
            confluence_threshold_light: cc.threshold_light,
            confluence_threshold_full: cc.threshold_full,
            max_cooldown_boost: 3.0,
            use_maker_entry: false,
            maker_price_offset_bps: 1.0,
            maker_limit_timeout_ms: 45_000,
            // G7-09c Phase 1: default 1 tick inside the inside quote.
            // G7-09c Phase 1：預設退一 tick。
            maker_price_buffer_ticks: 1,
        }
    }
}

impl StrategyParams for MaCrossoverParams {
    fn param_ranges() -> Vec<ParamRange> {
        vec![
            ParamRange {
                name: "cooldown_ms".into(),
                min: 60_000.0,
                max: 3_600_000.0,
                step: Some(60_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "adx_threshold".into(),
                min: 10.0,
                max: 50.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "default_qty".into(),
                min: 0.001,
                max: 1e12,
                step: None,
                agent_adjustable: false,
                db_persisted: true,
            },
            ParamRange {
                name: "regime_filter_enabled".into(),
                min: 0.0,
                max: 1.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "higher_tf_alpha".into(),
                min: 0.001,
                max: 0.05,
                step: None,
                agent_adjustable: true,
                db_persisted: true,
            },
            // ── G-SR-1 S3: Confluence param ranges (R3-4: exempt from ±30% delta cap) ──
            // ── G-SR-1 S3：匯流參數範圍（R3-4：豁免 ±30% delta 上限）──
            ParamRange {
                name: "weight_adx".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_regime".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_volume".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "weight_momentum".into(),
                min: 0.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "adx_floor".into(),
                min: 0.0,
                max: 30.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "confluence_threshold_no_trade".into(),
                min: 10.0,
                max: 55.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "confluence_threshold_light".into(),
                min: 20.0,
                max: 60.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "confluence_threshold_full".into(),
                min: 30.0,
                max: 65.0,
                step: Some(1.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "min_persistence_ms".into(),
                min: 0.0,
                max: 300_000.0,
                step: Some(10_000.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "min_notional_usd".into(),
                min: 1.0,
                max: 100.0,
                step: Some(1.0),
                agent_adjustable: false,
                db_persisted: true,
            },
            // A2: Trend-adaptive cooldown boost (ported from grid_trading A3).
            // A2：趨勢自適應冷卻加成（移植自 grid_trading A3）。
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
        if self.cooldown_ms < 60_000 {
            return Err("cooldown_ms must be >= 60s".into());
        }
        if self.adx_threshold < 5.0 || self.adx_threshold > 80.0 {
            return Err("adx_threshold must be in [5, 80]".into());
        }
        if self.higher_tf_alpha <= 0.0 || self.higher_tf_alpha > 0.1 {
            return Err("higher_tf_alpha must be in (0, 0.1]".into());
        }
        // G-SR-1: Validate confluence weight sum = 65 / 驗證匯流權重總和 = 65
        self.build_confluence_config().validate()?;
        // G-SR-1 S3: Threshold ordering / 閾值排序驗證
        if self.confluence_threshold_no_trade >= self.confluence_threshold_light
            || self.confluence_threshold_light >= self.confluence_threshold_full
        {
            return Err("confluence thresholds must be ordered: no_trade < light < full".into());
        }
        if self.min_notional_usd < 1.0 {
            return Err("min_notional_usd must be >= 1.0".into());
        }
        // A2: Cooldown boost must be non-negative and bounded.
        // A2：冷卻加成必須非負且有上限。
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
        Ok(())
    }
}

impl MaCrossoverParams {
    /// Build ConfluenceConfig from flat params (trend profile, non-inverted ADX).
    /// 從扁平參數構建 ConfluenceConfig（趨勢配置，非反轉 ADX）。
    pub fn build_confluence_config(&self) -> ConfluenceConfig {
        ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: false, // trend-following / 趨勢跟蹤
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: true,
        }
    }
}

pub struct MaCrossover {
    active: bool,
    /// Per-symbol position tracking: symbol → is_long direction.
    /// E1-P0-2: Migrated from `HashMap<String, bool>` to `PerSymbolState<bool>`.
    /// 每幣種獨立持倉追蹤：symbol → 多空方向（E1-P0-2：改用 `PerSymbolState<bool>`）。
    positions: PerSymbolState<bool>,
    /// Per-symbol last trade timestamp for cooldown.
    /// E1-P0-2: Migrated from `HashMap<String, u64>` to `TrendCooldown`.
    /// The trend-adaptive cooldown multiplier still lives in
    /// `compute_trend_adjusted_cooldown` (ma_crossover-specific); each tick we
    /// push the effective duration into the shared `TrendCooldown` via
    /// `set_duration()` before calling `is_cooled_down()` — preserves the
    /// original `ts < last_ms + effective` semantics exactly (including the
    /// `last_ms == 0 → unseen → cooled` sentinel via the HashMap-absent branch).
    /// E1-P0-2：改用 TrendCooldown；趨勢自適應倍率仍留在 `compute_trend_adjusted_cooldown`，
    /// 每個 tick 先 `set_duration()` 再查 `is_cooled_down()`，原語意完全保留。
    cooldown: TrendCooldown,
    pub(crate) cooldown_ms: u64,
    pub(crate) adx_threshold: f64,
    default_qty: f64,
    /// RC-01: Enable Hurst regime filter — skip entry in mean-reverting / random-walk markets.
    /// RC-01: 啟用赫斯特狀態過濾 — 在均值回歸/隨機漫步市場中跳過入場。
    pub(crate) regime_filter_enabled: bool,
    /// RC-02: Per-symbol higher timeframe trend direction.
    /// RC-02: 每幣種較高時間框架趨勢方向。
    higher_tf_trend: HashMap<String, bool>,
    /// RC-02: Per-symbol slow EMA of sma_50 as proxy for 4h trend.
    /// RC-02: 每幣種 sma_50 的慢速 EMA，作為 4h 趨勢的替代指標。
    higher_tf_sma: HashMap<String, f64>,
    /// Higher-TF EMA smoothing alpha. Default 0.003 = ~231min half-life ≈ 4h at 1m ticks.
    /// Agent can tune this parameter. Will be replaced by real multi-TF klines in Phase 1.
    /// 較高時間框架 EMA 平滑 alpha。默認 0.003 = ~231 分鐘半衰期 ≈ 1 分鐘 tick 下約 4 小時。
    /// Agent 可調整此參數。Phase 1 將改用真實多時間框架 K 線替代。
    pub higher_tf_alpha: f64,
    /// QC-H1: Entry confidence base (default 0.45). / 入場信心基礎值。
    pub(crate) entry_conf_base: f64,
    /// QC-H1: Entry regime bonus ±(default 0.15): trending +, mean_reverting −.
    /// QC-H1：入場市場狀態加分 ±（默認 0.15）：趨勢 +，均值回歸 −。
    pub(crate) entry_regime_bonus: f64,
    /// QC-H1: Exit confidence base (default 0.5). / 出場信心基礎值。
    pub(crate) exit_conf_base: f64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    // prev_last_trade_ms keeps the "0 = unseen" sentinel semantics so RC-04
    // rollback can restore the "never traded" state via `TrendCooldown::clear`.
    // prev_last_trade_ms 沿用「0 = 未見」哨兵，RC-04 透過 TrendCooldown::clear 回復「未交易」狀態。
    prev_position: HashMap<String, Option<bool>>,
    prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    /// CONF-D：發出 intent.confidence 的乘數（默認 1.0，範圍 [0,2]）。
    conf_scale: f64,
    // ── G-SR-1: Confluence scoring + persistence filter (A0-c, A1) ──
    // ── G-SR-1：匯流評分 + 持續性過濾器 ──
    /// Confluence scoring configuration (trend profile). / 匯流評分配置（趨勢配置）。
    pub confluence_config: ConfluenceConfig,
    /// Time-based signal persistence tracker. / 基於時間的信號持續性追蹤器。
    persistence: PersistenceTracker,
    /// Minimum signal persistence before entry (ms). / 入場前信號最小持續時間。
    pub min_persistence_ms: u64,
    /// Minimum order notional (USD). / 最小訂單名義值。
    pub min_notional_usd: f64,
    // ── A1: Exit-side persistence tracker (separate from entry) ──
    // ── A1：出場側持續性追蹤器（與入場獨立）──
    /// A1: Reverse-crossover persistence tracker scaled by KAMA efficiency ratio.
    /// Choppy market (ER→0) demands near-entry-level confirmation; trending (ER→1)
    /// lets reversal exit fire almost immediately.
    /// A1：反向交叉持續性追蹤器，由 KAMA 效率比縮放。盤整（ER→0）要求接近入場級別確認；
    /// 趨勢（ER→1）允許幾乎即時出場。
    exit_persistence: PersistenceTracker,
    // ── A2: Trend-adaptive cooldown multiplier cap ──
    // ── A2：趨勢自適應冷卻倍率上限 ──
    /// Max cooldown boost for trend-adaptive cooldown. See
    /// `compute_trend_adjusted_cooldown()`. Default 3.0.
    /// 趨勢自適應冷卻的最大加成倍率。
    pub(crate) max_cooldown_boost: f64,
    /// EDGE-P2-3 Phase 2+: emit PostOnly Limit entries instead of Market.
    /// Close path remains Market (entry-only scope). Default `false`.
    /// EDGE-P2-3 Phase 2+：入場發 PostOnly Limit；平倉維持 Market。
    pub(crate) use_maker_entry: bool,
    /// EDGE-P2-3 Phase 2+: bps offset from last_price for PostOnly limit placement.
    pub(crate) maker_price_offset_bps: f64,
    /// EDGE-P2-3 Phase 2+: ms a resting PostOnly maker order may sit (clamped on assign).
    pub(crate) maker_limit_timeout_ms: u64,
    /// G7-09c Phase 1: ticks INSIDE the inside quote for BBO-aware PostOnly.
    /// See `MaCrossoverParams::maker_price_buffer_ticks` for semantics.
    /// G7-09c Phase 1：BBO-aware PostOnly buffer，語義見 params。
    pub(crate) maker_price_buffer_ticks: u32,
}

impl MaCrossover {
    pub fn new() -> Self {
        Self {
            active: true,
            positions: PerSymbolState::new(),
            cooldown: TrendCooldown::new(300_000),
            cooldown_ms: 300_000,
            adx_threshold: 20.0,
            default_qty: 1e9,
            regime_filter_enabled: true,
            higher_tf_trend: HashMap::new(),
            higher_tf_sma: HashMap::new(),
            higher_tf_alpha: 0.003,
            entry_conf_base: 0.45,
            entry_regime_bonus: 0.15,
            exit_conf_base: 0.5,
            prev_position: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
            confluence_config: ConfluenceConfig::default(),
            persistence: PersistenceTracker::new(),
            min_persistence_ms: 180_000,
            min_notional_usd: 10.0,
            exit_persistence: PersistenceTracker::new(),
            max_cooldown_boost: 3.0,
            use_maker_entry: false,
            maker_price_offset_bps: 1.0,
            maker_limit_timeout_ms: 45_000,
            // G7-09c Phase 1: default 1 tick inside the inside quote.
            // G7-09c Phase 1：預設退一 tick。
            maker_price_buffer_ticks: 1,
        }
    }
}
