//! MA Crossover Strategy V2 — KAMA + ADX filter + Hurst regime filter + multi-TF confirmation.
//! MA 交叉策略 V2 — KAMA + ADX 過濾 + 赫斯特狀態過濾 + 多時間框架確認。
//!
//! MODULE_NOTE (EN): Fast/slow KAMA crossover with ADX trending filter, Hurst
//!   regime gating, and multi-timeframe confirmation for reduced false signals.
//! MODULE_NOTE (中): 快慢 KAMA 交叉 + ADX 趨勢過濾 + 赫斯特狀態門控 +
//!   多時間框架確認，減少假信號。

use std::collections::HashMap;

use super::common::{ConfidenceBuilder, PerSymbolState, TrendCooldown};
use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use serde::{Deserialize, Serialize};
use tracing::info;

/// Tunable parameters for MA Crossover strategy (Phase 3a AGT-1).
/// MA 交叉策略的可調參數。
#[derive(Debug, Clone, Serialize, Deserialize)]
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
        }
    }

    /// Phase 3a: Update tunable parameters (does not reset state).
    /// Phase 3a：更新可調參數（不重置狀態）。
    pub fn update_params(&mut self, params: MaCrossoverParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        // E1-P0-2: Keep TrendCooldown's base duration in sync. The per-tick
        // `set_duration(effective)` call will overwrite this with the trend-
        // adjusted value, but holding the base in the struct preserves the
        // old invariant where `cooldown_ms` is the authoritative baseline.
        // E1-P0-2：TrendCooldown 基礎值同步；每 tick 仍會用有效值覆蓋。
        self.cooldown.set_duration(params.cooldown_ms);
        self.adx_threshold = params.adx_threshold;
        self.default_qty = params.default_qty;
        self.regime_filter_enabled = params.regime_filter_enabled;
        self.higher_tf_alpha = params.higher_tf_alpha;
        // R4-7: Rebuild ConfluenceConfig from updated params (cheap struct copy).
        // R4-7：從更新的參數重建 ConfluenceConfig（廉價結構體拷貝）。
        self.confluence_config = params.build_confluence_config();
        self.min_persistence_ms = params.min_persistence_ms;
        self.min_notional_usd = params.min_notional_usd;
        self.max_cooldown_boost = params.max_cooldown_boost;
        // EDGE-P2-3 Phase 2+: hot-reload PostOnly entry toggles.
        // EDGE-P2-3 Phase 2+：熱重載 PostOnly 入場參數。
        self.use_maker_entry = params.use_maker_entry;
        self.maker_price_offset_bps = params.maker_price_offset_bps;
        // Clamp at assignment so runtime values satisfy invariant.
        // 於寫入時 clamp，運行時值恆在區間內。
        self.maker_limit_timeout_ms = super::grid_trading::clamp_maker_limit_timeout_ms(
            params.maker_limit_timeout_ms,
        );
        info!(strategy = "ma_crossover", "params updated / 參數已更新");
        Ok(())
    }

    /// Phase 3a: Get current tunable parameters.
    /// Phase 3a：獲取當前可調參數。
    pub fn get_params(&self) -> MaCrossoverParams {
        MaCrossoverParams {
            cooldown_ms: self.cooldown_ms,
            adx_threshold: self.adx_threshold,
            default_qty: self.default_qty,
            regime_filter_enabled: self.regime_filter_enabled,
            higher_tf_alpha: self.higher_tf_alpha,
            min_persistence_ms: self.min_persistence_ms,
            min_notional_usd: self.min_notional_usd,
            weight_adx: self.confluence_config.weight_adx,
            weight_regime: self.confluence_config.weight_regime,
            weight_volume: self.confluence_config.weight_volume,
            weight_momentum: self.confluence_config.weight_momentum,
            adx_floor: self.confluence_config.adx_floor,
            confluence_threshold_no_trade: self.confluence_config.threshold_no_trade,
            confluence_threshold_light: self.confluence_config.threshold_light,
            confluence_threshold_full: self.confluence_config.threshold_full,
            max_cooldown_boost: self.max_cooldown_boost,
            use_maker_entry: self.use_maker_entry,
            maker_price_offset_bps: self.maker_price_offset_bps,
            maker_limit_timeout_ms: self.maker_limit_timeout_ms,
        }
    }

    fn make_intent(&self, ctx: &TickContext<'_>, is_long: bool, conf: f64) -> OrderIntent {
        self.make_intent_with_qty(ctx, is_long, conf, self.default_qty, None, None)
    }

    /// Build intent with explicit qty (used by confluence-scaled entries).
    /// 使用顯式 qty 構建 intent（用於匯流調整後的入場）。
    ///
    /// EDGE-P3-1 A6: `confluence_score` is the raw compute_score result [0, 65]
    /// (None on cold-start fallback); `persistence_elapsed_ms` is ms since signal
    /// onset. Exits pass None/None — features are decision-time only.
    /// EDGE-P3-1 A6：confluence_score 為原始分數，persistence_elapsed_ms 為信號經時；
    /// 出場路徑傳 None。
    fn make_intent_with_qty(
        &self,
        ctx: &TickContext<'_>,
        is_long: bool,
        conf: f64,
        qty: f64,
        confluence_score: Option<f32>,
        persistence_elapsed_ms: Option<u64>,
    ) -> OrderIntent {
        let scaled =
            crate::tick_pipeline::on_tick_helpers::clamp_confidence(conf * self.conf_scale);
        // EDGE-P2-3 Phase 2+: resolve entry order shape (Market vs PostOnly Limit).
        // BUY offset below last_price; SELL offset above — PostOnly always rests passively.
        // Close path (StrategyAction::Close) bypasses this helper entirely.
        // EDGE-P2-3 Phase 2+：決定入場單型。BUY 掛 last 下方、SELL 掛上方；平倉走 Close variant 不經此。
        let (order_type, limit_price, time_in_force, maker_timeout_ms) =
            if self.use_maker_entry {
                let offset = self.maker_price_offset_bps / 10_000.0;
                let limit = if is_long {
                    ctx.price * (1.0 - offset)
                } else {
                    ctx.price * (1.0 + offset)
                };
                (
                    "limit".to_string(),
                    Some(limit),
                    Some(TimeInForce::PostOnly),
                    Some(self.maker_limit_timeout_ms),
                )
            } else {
                ("market".to_string(), None, None, None)
            };
        OrderIntent {
            symbol: ctx.symbol.to_string(),
            is_long,
            qty,
            confidence: scaled,
            strategy: self.name().into(),
            order_type,
            limit_price,
            confluence_score,
            persistence_elapsed_ms,
            time_in_force,
            maker_timeout_ms,
        }
    }

    /// RC-01: Check if Hurst regime allows entry (only "trending" passes).
    /// RC-01: 檢查赫斯特狀態是否允許入場（僅 "trending" 通過）。
    fn regime_allows_entry(&self, ctx: &TickContext<'_>) -> bool {
        if !self.regime_filter_enabled {
            return true;
        }
        let ind = match ctx.indicators {
            Some(i) => i,
            None => return true,
        };
        match &ind.hurst {
            // No Hurst data — don't block (cold-start safe).
            // 無赫斯特數據 — 不阻擋（冷啟動安全）。
            None => true,
            Some(hr) => hr.regime == "trending",
        }
    }

    /// RC-02: Update higher-TF SMA and trend using EMA of sma_50.
    /// Alpha=0.003 gives half-life ~231 min ≈ 4h on 1m ticks (ln2/0.003=231).
    /// RC-02: 使用 sma_50 的 EMA 更新較高時間框架 SMA 及趨勢。
    /// Alpha=0.003 在 1 分鐘 tick 上半衰期 ~231 分鐘 ≈ 4 小時。
    fn update_higher_tf(&mut self, symbol: &str, sma_50: f64) {
        let alpha = self.higher_tf_alpha;
        let new_val = match self.higher_tf_sma.get(symbol) {
            // First data point — initialize directly, no trend yet.
            // 第一個數據點 — 直接初始化，尚無趨勢。
            None => {
                self.higher_tf_sma.insert(symbol.to_string(), sma_50);
                self.higher_tf_trend.remove(symbol); // Need at least one update to determine trend.
                return;
            }
            Some(&prev) => alpha * sma_50 + (1.0 - alpha) * prev,
        };
        self.higher_tf_sma.insert(symbol.to_string(), new_val);
        self.higher_tf_trend
            .insert(symbol.to_string(), sma_50 > new_val);
    }

    /// Dynamic confidence: ADX excess + Hurst regime fit.
    /// 動態信心：ADX 超額 + Hurst regime 契合度。
    /// trending regime + 高 ADX → 高 conf；mean_reverting regime → 懲罰。
    ///
    /// E1-P0-2: Delegates to `ConfidenceBuilder`. Bit-exact equivalence with
    /// the pre-extraction formula is covered by
    /// `ConfidenceBuilder::tests::test_bit_exact_matches_pre_extraction_trending`
    /// (same base / adx_threshold / regime_bonus / 100.0 / 0.25 / 0.2 / 0.9).
    /// E1-P0-2：委派給 `ConfidenceBuilder`，位元精確對齊已於共享模組單測驗證。
    fn compute_entry_confidence(&self, adx: f64, regime: Option<&str>) -> f64 {
        ConfidenceBuilder::new(self.entry_conf_base, self.adx_threshold, self.entry_regime_bonus)
            .compute(adx, regime)
    }

    /// Exit confidence: cross-back is a real signal but weaker than fresh entry.
    /// 出場信心：反向交叉是真信號但弱於新入場。
    fn compute_exit_confidence(&self, adx: f64) -> f64 {
        // QC-H1: base configurable (was hardcoded 0.5)
        let base = self.exit_conf_base;
        let adx_bonus = ((adx - self.adx_threshold).max(0.0) / 100.0).min(0.2);
        (base + adx_bonus).clamp(0.4, 0.8)
    }

    /// A2: Trend-adaptive cooldown — in trending markets, extend cooldown to
    /// avoid re-entering too quickly after a close only to get whipsawed by the
    /// very trend that drove the reverse cross. Formula mirrors
    /// `grid_trading::compute_trend_adjusted_cooldown` but derives the ADX
    /// upper bound from the single `adx_threshold` parameter instead of
    /// carrying a separate `adx_high_threshold`.
    ///
    /// Upper bound = `adx_threshold × 2.5` (matches grid_trading's 20→50
    /// default). Hurst bound = 0.50→0.75. 60/40 ADX/Hurst blend.
    /// multiplier = 1 + trend_score × max_cooldown_boost, clamped via
    /// input bounds.
    ///
    /// A2：趨勢自適應冷卻。趨勢市場下延長冷卻，避免剛平又被同趨勢打回。
    /// 公式與 grid_trading A3 一致，但 ADX 上界由 `adx_threshold × 2.5` 推導。
    fn compute_trend_adjusted_cooldown(
        &self,
        snap: Option<&openclaw_core::indicators::IndicatorSnapshot>,
    ) -> u64 {
        let Some(ind) = snap else {
            return self.cooldown_ms;
        };

        let adx_val = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        let hurst_val = ind.hurst.as_ref().map(|h| h.hurst).unwrap_or(0.5);

        // ADX factor: adx_threshold → adx_threshold*2.5 maps to 0 → 1.
        // `adx_threshold * 1.5` is the width (upper − lower) of that range.
        // ADX 因子：adx_threshold 到 adx_threshold*2.5 線性映射為 0 到 1。
        let adx_range = self.adx_threshold * 1.5;
        let adx_factor = if adx_range > 0.0 {
            ((adx_val - self.adx_threshold) / adx_range).clamp(0.0, 1.0)
        } else {
            0.0
        };

        // Hurst factor: 0.50 → 0.75 maps to 0 → 1.
        // Hurst 因子：0.50 到 0.75 映射為 0 到 1。
        let hurst_factor = ((hurst_val - 0.50) / 0.25).clamp(0.0, 1.0);

        // 60/40 blend — ADX reacts faster than Hurst. / 60/40 混合：ADX 反應快於 Hurst。
        let trend_score = 0.6 * adx_factor + 0.4 * hurst_factor;

        let multiplier = 1.0 + (trend_score * self.max_cooldown_boost);
        (self.cooldown_ms as f64 * multiplier) as u64
    }

    /// A1: ER-scaled exit persistence window (ms).
    /// ER→1 (clean trend) → window→0 → reverse cross exits immediately.
    /// ER→0 (choppy) → window→min_persistence_ms → near-entry-level confirmation.
    /// A1：KAMA 效率比驅動的出場持續性窗口（ms）。
    fn compute_exit_persistence_ms(&self, efficiency_ratio: f64) -> u64 {
        let er = efficiency_ratio.clamp(0.0, 1.0);
        (self.min_persistence_ms as f64 * (1.0 - er)).max(0.0) as u64
    }

    /// RC-02: Check if higher-TF trend aligns with the proposed entry direction.
    /// RC-02: 檢查較高時間框架趨勢是否與擬入場方向一致。
    fn higher_tf_allows_entry(&self, symbol: &str, is_long: bool) -> bool {
        match self.higher_tf_trend.get(symbol) {
            // No trend data yet — allow entry (cold-start safe).
            // 尚無趨勢數據 — 允許入場（冷啟動安全）。
            None => true,
            // Long requires bullish (true), short requires bearish (false).
            // 做多需要看漲（true），做空需要看跌（false）。
            Some(&bullish) => bullish == is_long,
        }
    }
}

impl Strategy for MaCrossover {
    fn name(&self) -> &str {
        "ma_crossover"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// RC-04: Revert per-symbol position and last_trade_ms on rejection.
    /// RC-04：拒絕時回滾該幣種的 position 和 last_trade_ms。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(prev) = self.prev_position.get(sym) {
            match prev {
                Some(b) => {
                    self.positions.insert(sym.clone(), *b);
                }
                None => {
                    self.positions.remove(sym);
                }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                // Sentinel 0 → unseen prior to mutation; restore by clearing.
                // 哨兵 0 → 變更前為未見；清除以還原。
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    /// Reset internal position for the closed symbol (risk-stop).
    /// 外部平倉（風控止損）時重設該幣種的內部倉位狀態。
    fn on_external_close(&mut self, symbol: &str) {
        self.positions.remove(symbol);
        self.persistence.clear(symbol);
        self.exit_persistence.clear(symbol);
    }

    fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let ind = match ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        // Snapshot pre-mutation last_ms for RC-04 (sentinel 0 when unseen, as before).
        // 為 RC-04 快照變更前的 last_ms（未見時沿用哨兵 0）。
        let last_ms = self.cooldown.last_ms(ctx.symbol).unwrap_or(0);
        // A2: trend-adaptive cooldown — extends cooldown in strong-trend markets
        // to prevent re-entering into a continuing trend that just closed us out.
        // E1-P0-2: Delegated to shared `TrendCooldown`; we push the effective
        // duration in each tick so semantics match `ts < last_ms + effective`
        // exactly (unseen symbol still → cooled via TrendCooldown's None branch).
        // A2：趨勢自適應冷卻；E1-P0-2 委派給 TrendCooldown，語意完全一致。
        let effective_cooldown = self.compute_trend_adjusted_cooldown(ctx.indicators);
        self.cooldown.set_duration(effective_cooldown);
        if !self.cooldown.is_cooled_down(ctx.symbol, ctx.timestamp_ms) {
            return vec![];
        }

        // ADX trend-strength gate (existing).
        // ADX 趨勢強度門檻（原有）。
        let adx = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        if adx < self.adx_threshold {
            return vec![];
        }

        // RC-02: Update per-symbol higher-TF proxy from sma_50 (every tick for EMA warmup).
        // RC-02: 從 sma_50 更新該幣種的較高時間框架替代指標（每個 tick 更新以暖機 EMA）。
        if let Some(sma_50) = ind.sma_50 {
            self.update_higher_tf(ctx.symbol, sma_50);
        }

        let fast = match ind.kama.as_ref() {
            Some(k) => k.kama,
            None => {
                // QC-#2: Log KAMA fallback — strategy silently degrades to SMA vs SMA (never crosses).
                // QC-#2：記錄 KAMA 退化 — 策略靜默退化為 SMA vs SMA（永不交叉）。
                tracing::debug!(
                    symbol = %ctx.symbol,
                    "KAMA unavailable, falling back to SMA(20) / KAMA 不可用，退化為 SMA(20)"
                );
                ind.sma_20.unwrap_or(0.0)
            }
        };
        let slow = ind.sma_20.unwrap_or(0.0);
        if fast == 0.0 || slow == 0.0 {
            return vec![];
        }

        let mut intents = Vec::new();

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        self.prev_position.insert(
            ctx.symbol.to_string(),
            self.positions.get(ctx.symbol).copied(),
        );
        self.prev_last_trade_ms
            .insert(ctx.symbol.to_string(), last_ms);

        match self.positions.get(ctx.symbol).copied() {
            None => {
                // Entry path — apply RC-01 regime filter + RC-02 higher-TF confirmation.
                // 入場路徑 — 套用 RC-01 狀態過濾 + RC-02 較高時間框架確認。
                if !self.regime_allows_entry(ctx) {
                    return vec![];
                }

                // G-SR-1 A1: Determine signal direction for persistence check.
                // G-SR-1 A1：確定信號方向供持續性檢查。
                let signal: Option<bool> = if fast > slow {
                    Some(true)
                } else if fast < slow {
                    Some(false)
                } else {
                    None
                };

                // A1: Time-based persistence filter — signal must hold ≥ min_persistence_ms.
                // A1：基於時間的持續性過濾 — 信號必須持續 ≥ min_persistence_ms。
                if !self.persistence.check(
                    ctx.symbol,
                    signal,
                    ctx.timestamp_ms,
                    self.min_persistence_ms,
                    false, // not a close signal / 非平倉信號
                ) {
                    return vec![];
                }

                // A2: Confluence scoring — primary signal is mandatory gate.
                // A2：匯流評分 — 主信號是強制門控。
                let score = confluence::compute_score(
                    &self.confluence_config,
                    signal.is_some(),
                    ind.adx.as_ref().map(|a| a.adx),
                    ind.hurst
                        .as_ref()
                        .map(|h| h.regime.as_str())
                        .unwrap_or("uncertain"),
                    ind.volume_ratio,
                    ind.rsi_14,
                    signal.unwrap_or(true),
                );
                let qty_pct = confluence::score_to_qty_pct(score, &self.confluence_config);
                if qty_pct <= 0.0 {
                    return vec![];
                }
                let qty = self.default_qty * qty_pct;
                // R3-9: Min notional guard / 最小名義值守衛
                if qty * ctx.price < self.min_notional_usd {
                    return vec![];
                }

                let regime = ind.hurst.as_ref().map(|h| h.regime.as_str());
                let entry_conf = self.compute_entry_confidence(adx, regime);
                // R3-2: Reuse confidence field for confluence score.
                // R3-2：復用 confidence 欄位存放匯流分數。
                let conf_with_score = match score {
                    Some(s) if s > 0.0 => s / 65.0, // normalize to [0,1]
                    _ => entry_conf,
                };

                if let Some(is_long) = signal {
                    if !self.higher_tf_allows_entry(ctx.symbol, is_long) {
                        return vec![];
                    }
                    // EDGE-P3-1 A6: snapshot confluence + persistence elapsed at
                    // decision time so predictor sees the same numbers the gate
                    // used. Clamp score to f32 for feature vector.
                    // EDGE-P3-1 A6：抓取決策時的 confluence/persistence 供預測器。
                    let confluence_score = score.map(|s| s as f32);
                    let persistence_elapsed_ms =
                        self.persistence.elapsed_ms(ctx.symbol, ctx.timestamp_ms);
                    intents.push(StrategyAction::Open(self.make_intent_with_qty(
                        ctx,
                        is_long,
                        conf_with_score,
                        qty,
                        confluence_score,
                        persistence_elapsed_ms,
                    )));
                    self.positions.insert(ctx.symbol.to_string(), is_long);
                    self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
                }
            }
            Some(is_long) => {
                // Exit path — RC-01/RC-02 filters do NOT apply to exits.
                // KAMA crosses back through SMA20 = trend reversal (Kaufman).
                // Exit urgency > entry selectivity: no ADX/regime/higher-TF filter on exit.
                // 出場路徑 — KAMA 回穿 SMA20 = 趨勢反轉。出場不套用入場過濾器。
                //
                // A1: instead of firing Close on the first reverse tick, require
                // the reverse signal to persist for `min_persistence_ms × (1 − ER)`.
                // Choppy markets (ER→0) demand confirmation; clean trends (ER→1)
                // exit nearly instantly. Hard stop / trailing / fast_track paths
                // operate independently and remain unaffected.
                // A1：反向交叉不再單 tick 出場，以 KAMA ER 縮放的持續性窗口過濾假反轉。
                let reverse_signal: Option<bool> = if is_long && fast < slow {
                    Some(false) // bearish reverse for long position
                } else if !is_long && fast > slow {
                    Some(true) // bullish reverse for short position
                } else {
                    None // aligned with position, no reverse signal
                };

                // ER-scaled exit persistence window. KAMA-less snapshots fall
                // back to ER=0.5 (mid) rather than 0 to avoid pinning exit at
                // the entry-level threshold on cold starts.
                // ER 縮放的出場持續性窗口；無 KAMA 時退回 ER=0.5。
                let er = ind.kama.as_ref().map(|k| k.efficiency_ratio).unwrap_or(0.5);
                let exit_persistence_ms = self.compute_exit_persistence_ms(er);

                let persisted = self.exit_persistence.check(
                    ctx.symbol,
                    reverse_signal,
                    ctx.timestamp_ms,
                    exit_persistence_ms,
                    false, // not a close-exempt path — we WANT persistence
                );

                if persisted && reverse_signal.is_some() {
                    let exit_conf = self.compute_exit_confidence(adx);
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.to_string(),
                        confidence: exit_conf,
                        reason: "ma_reverse_cross".into(),
                    });
                    self.positions.remove(ctx.symbol);
                    self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
                    self.exit_persistence.clear(ctx.symbol);
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: MaCrossoverParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&MaCrossoverParams::param_ranges()).unwrap_or_default()
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
    use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot, KamaResult};

    // P-08: Test helpers use Box::leak for owned indicator data (fine for tests).

    /// Helper: build a TickContext with given indicator values.
    /// 輔助函數：用給定指標值構建 TickContext。
    fn ctx_with(sma: f64, kama: f64, adx: f64, ts: u64) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            sma_20: Some(sma),
            kama: Some(KamaResult {
                kama,
                efficiency_ratio: 0.5,
            }),
            adx: Some(AdxResult {
                adx,
                plus_di: 25.0,
                minus_di: 15.0,
            }),
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
        }
    }

    /// Helper: build a TickContext with Hurst regime data.
    /// 輔助函數：用赫斯特狀態數據構建 TickContext。
    fn ctx_with_hurst(
        sma: f64,
        kama: f64,
        adx: f64,
        ts: u64,
        regime: &str,
        hurst_val: f64,
    ) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            sma_20: Some(sma),
            kama: Some(KamaResult {
                kama,
                efficiency_ratio: 0.5,
            }),
            adx: Some(AdxResult {
                adx,
                plus_di: 25.0,
                minus_di: 15.0,
            }),
            hurst: Some(HurstResult {
                hurst: hurst_val,
                regime: regime.to_string(),
            }),
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
        }
    }

    /// Helper: build a TickContext with sma_50 for higher-TF testing.
    /// 輔助函數：用 sma_50 構建 TickContext 以測試較高時間框架。
    fn ctx_with_sma50(
        sma_20: f64,
        kama: f64,
        adx: f64,
        ts: u64,
        sma_50: f64,
    ) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            sma_20: Some(sma_20),
            sma_50: Some(sma_50),
            kama: Some(KamaResult {
                kama,
                efficiency_ratio: 0.5,
            }),
            adx: Some(AdxResult {
                adx,
                plus_di: 25.0,
                minus_di: 15.0,
            }),
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // Existing tests (must still pass) / 原有測試（必須繼續通過）
    // ═══════════════════════════════════════════════════════════════════════

    #[test]
    fn test_no_signal_low_adx() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        assert!(s.on_tick(&ctx_with(100.0, 101.0, 15.0, 0)).is_empty());
    }

    #[test]
    fn test_long_entry() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let i = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    #[test]
    fn test_exit_on_reverse() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        let i = s.on_tick(&ctx_with(101.0, 100.0, 25.0, 500_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { symbol, reason, .. } => {
                assert_eq!(symbol, "BTC");
                assert_eq!(reason, "ma_reverse_cross");
            }
            other => panic!("expected StrategyAction::Close, got {:?}", other),
        }
    }

    // ═══════════════════════════════════════════════════════════════════════
    // RC-01: Hurst regime filter tests / RC-01: 赫斯特狀態過濾測試
    // ═══════════════════════════════════════════════════════════════════════

    /// Entry blocked when Hurst regime is "mean_reverting" (H < 0.5).
    /// 赫斯特狀態為「均值回歸」時阻擋入場。
    #[test]
    fn test_regime_filter_blocks_mean_reverting() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // fast(kama=101) > slow(sma_20=100), ADX=25 → would normally enter long.
                                  // 快線 > 慢線, ADX 足夠 → 正常情況會做多入場。
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "mean_reverting", 0.35);
        let intents = s.on_tick(&ctx);
        assert!(
            intents.is_empty(),
            "Entry must be blocked in mean_reverting regime"
        );
    }

    /// Entry allowed when Hurst regime is "trending" (H > 0.5).
    /// 赫斯特狀態為「趨勢」時允許入場。
    #[test]
    fn test_regime_filter_allows_trending() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
        let intents = s.on_tick(&ctx);
        assert_eq!(intents.len(), 1, "Entry must be allowed in trending regime");
        match &intents[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    /// Exit still works even in mean_reverting regime (position already open).
    /// 即使在均值回歸狀態下，已持有的倉位仍可出場。
    #[test]
    fn test_regime_filter_allows_exit() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // Step 1: Enter long in trending regime.
                                  // 步驟 1：在趨勢狀態下做多入場。
        let ctx_entry = ctx_with_hurst(100.0, 101.0, 25.0, 0, "trending", 0.72);
        let entry = s.on_tick(&ctx_entry);
        assert_eq!(entry.len(), 1, "Should enter long");

        // Step 2: Regime flips to mean_reverting, but crossover reverses → exit must work.
        // 步驟 2：狀態轉為均值回歸，但交叉反轉 → 出場必須有效。
        let ctx_exit = ctx_with_hurst(101.0, 100.0, 25.0, 500_000, "mean_reverting", 0.35);
        let exit = s.on_tick(&ctx_exit);
        assert_eq!(
            exit.len(),
            1,
            "Exit must work even in mean_reverting regime"
        );
        match &exit[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "ma_reverse_cross"),
            other => panic!("expected StrategyAction::Close, got {:?}", other),
        }
    }

    /// Entry blocked when Hurst regime is "random_walk".
    /// 赫斯特狀態為「隨機漫步」時阻擋入場。
    #[test]
    fn test_regime_filter_blocks_random_walk() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "random_walk", 0.50);
        let intents = s.on_tick(&ctx);
        assert!(
            intents.is_empty(),
            "Entry must be blocked in random_walk regime"
        );
    }

    /// Regime filter can be disabled via struct field.
    /// 狀態過濾可通過結構體字段禁用。
    #[test]
    fn test_regime_filter_disabled() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.regime_filter_enabled = false;
        let ctx = ctx_with_hurst(100.0, 101.0, 25.0, 0, "mean_reverting", 0.35);
        let intents = s.on_tick(&ctx);
        assert_eq!(
            intents.len(),
            1,
            "Entry allowed when regime filter is disabled"
        );
    }

    // ═══════════════════════════════════════════════════════════════════════
    // RC-02: Multi-TF confirmation tests / RC-02: 多時間框架確認測試
    // ═══════════════════════════════════════════════════════════════════════

    /// Long entry blocked when higher-TF trend is bearish.
    /// 較高時間框架趨勢看跌時阻擋做多入場。
    #[test]
    fn test_higher_tf_blocks_misaligned() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // Warm up higher_tf_sma with a high value so sma_50 < higher_tf_sma → bearish trend.
                                  // 用高值暖機 higher_tf_sma，使 sma_50 < higher_tf_sma → 看跌趨勢。
        s.higher_tf_sma.insert("BTC".into(), 110.0);
        // After one tick, higher_tf_sma ≈ 0.01*100 + 0.99*110 = 109.9, sma_50=100 < 109.9 → bearish.
        // 一個 tick 後，higher_tf_sma ≈ 109.9，sma_50=100 < 109.9 → 看跌。
        let ctx = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        // fast(101) > slow(100) → would want to go long, but higher TF is bearish → blocked.
        // 快線 > 慢線 → 想做多，但較高 TF 看跌 → 阻擋。
        assert!(
            intents.is_empty(),
            "Long entry must be blocked when higher TF is bearish"
        );
    }

    /// Long entry allowed when higher-TF trend is bullish.
    /// 較高時間框架趨勢看漲時允許做多入場。
    #[test]
    fn test_higher_tf_allows_aligned() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // Warm up higher_tf_sma with a low value so sma_50 > higher_tf_sma → bullish trend.
                                  // 用低值暖機 higher_tf_sma，使 sma_50 > higher_tf_sma → 看漲趨勢。
        s.higher_tf_sma.insert("BTC".into(), 90.0);
        // After one tick, higher_tf_sma ≈ 0.01*100 + 0.99*90 = 90.1, sma_50=100 > 90.1 → bullish.
        // 一個 tick 後，higher_tf_sma ≈ 90.1，sma_50=100 > 90.1 → 看漲。
        let ctx = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        assert_eq!(
            intents.len(),
            1,
            "Long entry must be allowed when higher TF is bullish"
        );
        match &intents[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    /// Short entry blocked when higher-TF trend is bullish.
    /// 較高時間框架趨勢看漲時阻擋做空入場。
    #[test]
    fn test_higher_tf_blocks_short_when_bullish() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.higher_tf_sma.insert("BTC".into(), 90.0);
        // sma_50=100 > 90.1 → bullish → short blocked.
        let ctx = ctx_with_sma50(101.0, 100.0, 25.0, 0, 100.0);
        let intents = s.on_tick(&ctx);
        assert!(
            intents.is_empty(),
            "Short entry must be blocked when higher TF is bullish"
        );
    }

    /// Entry allowed when higher_tf_trend is None (cold start).
    /// higher_tf_trend 為 None 時允許入場（冷啟動）。
    #[test]
    fn test_higher_tf_cold_start_allows_entry() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // No sma_50 in context → higher_tf_trend stays None → entry allowed.
                                  // 上下文中無 sma_50 → higher_tf_trend 保持 None → 允許入場。
        let ctx = ctx_with(100.0, 101.0, 25.0, 0);
        let intents = s.on_tick(&ctx);
        assert_eq!(
            intents.len(),
            1,
            "Entry must be allowed during cold start (no higher TF data)"
        );
    }

    /// Exit works regardless of higher-TF trend direction.
    /// 無論較高時間框架趨勢方向如何，出場均有效。
    #[test]
    fn test_higher_tf_does_not_block_exit() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
                                  // Enter long with aligned higher TF.
        s.higher_tf_sma.insert("BTC".into(), 90.0);
        let ctx_entry = ctx_with_sma50(100.0, 101.0, 25.0, 0, 100.0);
        let entry = s.on_tick(&ctx_entry);
        assert_eq!(entry.len(), 1);

        // Now flip higher TF to bearish and reverse crossover → exit must still work.
        // 現在將較高 TF 翻轉為看跌並反轉交叉 → 出場仍必須有效。
        s.higher_tf_sma.insert("BTC".into(), 110.0);
        s.higher_tf_trend.insert("BTC".into(), false);
        let ctx_exit = ctx_with_sma50(101.0, 100.0, 25.0, 500_000, 100.0);
        let exit = s.on_tick(&ctx_exit);
        assert_eq!(
            exit.len(),
            1,
            "Exit must work regardless of higher TF trend"
        );
    }

    // ── Phase 3a: StrategyParams tests ──

    #[test]
    fn test_param_ranges_non_empty() {
        let ranges = MaCrossoverParams::param_ranges();
        assert!(!ranges.is_empty());
        assert!(ranges.iter().any(|r| r.name == "adx_threshold"));
    }

    #[test]
    fn test_validate_pass() {
        let p = MaCrossoverParams::default();
        assert!(p.validate().is_ok());
    }

    #[test]
    fn test_validate_fail() {
        let p = MaCrossoverParams {
            cooldown_ms: 1000,
            ..Default::default()
        }; // too low
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_update_and_get_roundtrip() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let new_params = MaCrossoverParams {
            adx_threshold: 35.0,
            ..Default::default()
        };
        assert!(s.update_params(new_params).is_ok());
        let got = s.get_params();
        assert!((got.adx_threshold - 35.0).abs() < 1e-10);
    }

    #[test]
    fn test_json_roundtrip() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        let json = r#"{"cooldown_ms":600000,"adx_threshold":25.0,"default_qty":1000000000.0,"regime_filter_enabled":true,"higher_tf_alpha":0.005}"#;
        assert!(s.update_params_json(json).is_ok());
        let out = s.get_params_json();
        assert!(out.contains("25.0") || out.contains("25"));
    }

    #[test]
    fn test_conf_scale_clamps_to_range() {
        // CONF-D: set_conf_scale must clamp to [0, 2].
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.set_conf_scale(3.0);
        assert!((s.conf_scale() - 2.0).abs() < 1e-10);
        s.set_conf_scale(-1.0);
        assert!((s.conf_scale() - 0.0).abs() < 1e-10);
        s.set_conf_scale(1.5);
        assert!((s.conf_scale() - 1.5).abs() < 1e-10);
    }

    #[test]
    fn test_conf_scale_applied_to_emit() {
        // CONF-D: emitted confidence == raw * conf_scale, clamped to [0, 1].
        use crate::tick_pipeline::TickContext;
        let ctx = TickContext {
            symbol: "BTCUSDT",
            price: 50000.0,
            timestamp_ms: 0,
            indicators: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
        };
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        s.set_conf_scale(0.5);
        let intent = s.make_intent(&ctx, true, 0.8);
        assert!((intent.confidence - 0.4).abs() < 1e-10);

        s.set_conf_scale(2.0);
        let intent = s.make_intent(&ctx, true, 0.9);
        assert!((intent.confidence - 1.0).abs() < 1e-10); // clamped
    }

    // ── G-SR-1 S3+S4: param_ranges + validation tests ──

    #[test]
    fn test_ma_param_ranges_count() {
        let ranges = MaCrossoverParams::param_ranges();
        // 5 original + 10 confluence + 1 A2 (max_cooldown_boost) = 16
        assert_eq!(
            ranges.len(),
            16,
            "expected 16 param ranges, got {}",
            ranges.len()
        );
    }

    #[test]
    fn test_ma_param_ranges_confluence_names() {
        let ranges = MaCrossoverParams::param_ranges();
        let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
        for expected in &[
            "weight_adx",
            "weight_regime",
            "weight_volume",
            "weight_momentum",
            "adx_floor",
            "confluence_threshold_no_trade",
            "confluence_threshold_light",
            "confluence_threshold_full",
            "min_persistence_ms",
            "min_notional_usd",
        ] {
            assert!(names.contains(expected), "missing param range: {expected}");
        }
    }

    #[test]
    fn test_ma_param_ranges_agent_adjustable() {
        let ranges = MaCrossoverParams::param_ranges();
        // Weights should be agent_adjustable / 權重應可被 Agent 調整
        for name in &[
            "weight_adx",
            "weight_regime",
            "weight_volume",
            "weight_momentum",
        ] {
            let r = ranges.iter().find(|r| r.name == *name).unwrap();
            assert!(r.agent_adjustable, "{name} should be agent_adjustable");
        }
        // min_notional_usd should NOT be agent_adjustable
        let mn = ranges
            .iter()
            .find(|r| r.name == "min_notional_usd")
            .unwrap();
        assert!(
            !mn.agent_adjustable,
            "min_notional_usd should not be agent_adjustable"
        );
    }

    #[test]
    fn test_ma_validate_default_ok() {
        assert!(MaCrossoverParams::default().validate().is_ok());
    }

    #[test]
    fn test_ma_validate_bad_weight_sum() {
        let mut p = MaCrossoverParams::default();
        p.weight_adx = 30.0; // sum = 70 ≠ 65
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_ma_validate_bad_threshold_order() {
        let mut p = MaCrossoverParams::default();
        p.confluence_threshold_no_trade = 50.0;
        p.confluence_threshold_light = 45.0; // light < no_trade
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_ma_validate_bad_min_notional() {
        let mut p = MaCrossoverParams::default();
        p.min_notional_usd = 0.5; // < 1.0
        assert!(p.validate().is_err());
    }

    // ═══════════════════════════════════════════════════════════════════════
    // A1: ER-scaled exit persistence tests
    // A1：KAMA 效率比縮放的出場持續性測試
    // ═══════════════════════════════════════════════════════════════════════

    /// Helper: build TickContext with an explicit KAMA efficiency ratio.
    /// 輔助函數：用顯式 KAMA 效率比構建 TickContext。
    fn ctx_with_er(sma: f64, kama: f64, adx: f64, ts: u64, er: f64) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            sma_20: Some(sma),
            kama: Some(KamaResult {
                kama,
                efficiency_ratio: er,
            }),
            adx: Some(AdxResult {
                adx,
                plus_di: 25.0,
                minus_di: 15.0,
            }),
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price: 50_000.0,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
        }
    }

    #[test]
    fn test_a1_exit_persistence_formula() {
        // Raw formula check: window = min_persistence_ms × (1 − ER).
        // 公式驗證：window = min_persistence_ms × (1 − ER)。
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 200_000;
        assert_eq!(s.compute_exit_persistence_ms(0.0), 200_000);
        assert_eq!(s.compute_exit_persistence_ms(1.0), 0);
        assert_eq!(s.compute_exit_persistence_ms(0.5), 100_000);
        // Clamp: ER outside [0,1] must not produce negative / overflow windows.
        // 邊界：ER 超出 [0,1] 不可產生負值或溢出窗口。
        assert_eq!(s.compute_exit_persistence_ms(-0.5), 200_000);
        assert_eq!(s.compute_exit_persistence_ms(1.5), 0);
    }

    #[test]
    fn test_a1_trending_er_exits_immediately() {
        // Clean trend (ER=1.0) → window collapses to 0 → exit fires on the
        // first reverse-cross tick, matching pre-A1 behavior in trending regimes.
        // 乾淨趨勢（ER=1.0）→ 窗口為 0 → 首個反向交叉 tick 即出場。
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 180_000;
        // Entry with ER=0 to pass persistence=0 exit semantics cleanly; bypass
        // entry-side persistence by setting min to 0 only for the entry tick.
        // 入場側 persistence 設 0 以免與 A1 出場路徑糾纏。
        s.min_persistence_ms = 0;
        let opened = s.on_tick(&ctx_with_er(100.0, 101.0, 25.0, 0, 1.0));
        assert_eq!(opened.len(), 1, "long entry should fire");
        // Re-enable persistence before exit — A1 window uses it scaled by ER.
        // 重新啟用 persistence，讓 A1 公式生效。
        s.min_persistence_ms = 180_000;
        // ER=1.0 → window=0 → even 1 ms later the reverse exit fires.
        let exit = s.on_tick(&ctx_with_er(101.0, 100.0, 25.0, 500_000, 1.0));
        assert_eq!(exit.len(), 1, "trending ER must exit on first reverse tick");
        match &exit[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "ma_reverse_cross"),
            other => panic!("expected Close, got {:?}", other),
        }
    }

    #[test]
    fn test_a1_choppy_er_delays_exit_until_window_elapses() {
        // Choppy market (ER=0.0) → full min_persistence_ms window demanded.
        // First reverse tick records onset but does NOT emit Close; only after
        // ≥ window elapses does the persisted reverse fire.
        // 盤整（ER=0.0）→ 全 min_persistence_ms 窗口；首個反向 tick 僅記錄。
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0;
        // Open long cleanly first.
        let _ = s.on_tick(&ctx_with_er(100.0, 101.0, 25.0, 0, 0.5));
        s.min_persistence_ms = 180_000;

        // t=500_000: first reverse tick in choppy regime — must NOT exit yet.
        // t=500_000：盤整下首個反向 tick — 尚不可出場。
        let first = s.on_tick(&ctx_with_er(101.0, 100.0, 25.0, 500_000, 0.0));
        assert!(
            first.is_empty(),
            "choppy regime must defer exit until window elapses"
        );
        // Still inside the window (only 100 s passed of 180 s).
        // 仍在窗口內（僅過 100 秒，需 180 秒）。
        let mid = s.on_tick(&ctx_with_er(101.0, 100.0, 25.0, 600_000, 0.0));
        assert!(mid.is_empty(), "still inside choppy persistence window");
        // t=680_001: 180_001 ms after the onset → persistence passes, Close emits.
        // t=680_001：距首次反向 180_001 毫秒 → 持續性通過，出場。
        let exit = s.on_tick(&ctx_with_er(101.0, 100.0, 25.0, 680_001, 0.0));
        assert_eq!(exit.len(), 1, "choppy exit must fire once window elapsed");
        match &exit[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "ma_reverse_cross"),
            other => panic!("expected Close, got {:?}", other),
        }
    }

    #[test]
    fn test_a1_reverse_flicker_resets_exit_persistence() {
        // A flicker back to position-aligned (no reverse signal) between two
        // reverse ticks must reset the onset — classic PersistenceTracker
        // semantics. Otherwise a 10-min-old flicker would let the very next
        // reverse tick exit instantly in a choppy regime.
        // A1 + PersistenceTracker：中間一個對齊 tick 清空 onset。
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0;
        let _ = s.on_tick(&ctx_with_er(100.0, 101.0, 25.0, 0, 0.5));
        s.min_persistence_ms = 180_000;

        // t=100_000: reverse tick starts timer.
        assert!(s
            .on_tick(&ctx_with_er(101.0, 100.0, 25.0, 100_000, 0.0))
            .is_empty());
        // t=120_000: aligned tick (fast>slow, same as current long) → resets timer.
        // 對齊 tick → 重設計時。
        assert!(s
            .on_tick(&ctx_with_er(100.0, 101.0, 25.0, 120_000, 0.0))
            .is_empty());
        // t=200_000: reverse again — 80 s elapsed since new onset, not 100 s
        // since flicker start → must NOT exit.
        // 再次反向，距新 onset 80 秒 < 180 秒 → 不可出場。
        assert!(s
            .on_tick(&ctx_with_er(101.0, 100.0, 25.0, 200_000, 0.0))
            .is_empty());
    }

    #[test]
    fn test_a1_external_close_clears_exit_persistence() {
        // After external close (risk-stop / hard-stop / ft_scoped_reduce),
        // on_external_close must wipe the exit_persistence onset, else a
        // stale onset from the now-closed position would let the *next*
        // entry exit prematurely on its first reverse-looking tick.
        // 外部平倉後，exit_persistence 必須一併清空。
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0;
        let _ = s.on_tick(&ctx_with_er(100.0, 101.0, 25.0, 0, 0.5));
        s.min_persistence_ms = 180_000;
        // Record an exit_persistence onset via a reverse tick.
        assert!(s
            .on_tick(&ctx_with_er(101.0, 100.0, 25.0, 100_000, 0.0))
            .is_empty());

        // External close wipes everything for this symbol.
        s.on_external_close("BTC");
        // Verify via public API: a fresh long entry must succeed (positions clear)
        // and then a choppy reverse tick must NOT exit (exit_persistence clear).
        // 驗證：新倉可開，之後的反向 tick 不會立即觸發 A1（onset 已清）。
        s.min_persistence_ms = 0;
        let reopen = s.on_tick(&ctx_with_er(100.0, 101.0, 25.0, 1_000_000, 0.5));
        assert_eq!(reopen.len(), 1, "should re-enter after external close");
        s.min_persistence_ms = 180_000;
        assert!(
            s.on_tick(&ctx_with_er(101.0, 100.0, 25.0, 1_100_000, 0.0))
                .is_empty(),
            "exit_persistence must start from zero after on_external_close"
        );
    }

    // ═══════════════════════════════════════════════════════════════════════
    // A2: Trend-adaptive cooldown tests
    // A2：趨勢自適應冷卻測試
    // ═══════════════════════════════════════════════════════════════════════

    fn indicator_with(adx: Option<f64>, hurst: Option<f64>) -> IndicatorSnapshot {
        IndicatorSnapshot {
            adx: adx.map(|a| AdxResult {
                adx: a,
                plus_di: 25.0,
                minus_di: 15.0,
            }),
            hurst: hurst.map(|h| HurstResult {
                hurst: h,
                regime: "trending".into(),
            }),
            ..Default::default()
        }
    }

    #[test]
    fn test_a2_cooldown_no_indicators_returns_base() {
        // Missing IndicatorSnapshot → conservative fallback to base cooldown.
        // 無指標 → 退回基準冷卻。
        let s = MaCrossover::new();
        assert_eq!(s.compute_trend_adjusted_cooldown(None), s.cooldown_ms);
    }

    #[test]
    fn test_a2_cooldown_at_threshold_no_boost() {
        // ADX exactly at adx_threshold + Hurst = 0.50 → both factors = 0 →
        // multiplier = 1.0 → cooldown unchanged.
        // ADX 剛好在門檻 + Hurst=0.5 → 因子為 0 → 乘數 1.0 → 冷卻不變。
        let s = MaCrossover::new();
        let snap = indicator_with(Some(s.adx_threshold), Some(0.50));
        assert_eq!(
            s.compute_trend_adjusted_cooldown(Some(&snap)),
            s.cooldown_ms,
            "adx at threshold + hurst 0.5 should return base cooldown"
        );
    }

    #[test]
    fn test_a2_cooldown_strong_trend_4x_at_cap() {
        // ADX = adx_threshold × 2.5 + Hurst = 0.75 → both factors = 1.0 →
        // trend_score = 1.0 → multiplier = 1 + 1×3 = 4 → cooldown × 4.
        // 強趨勢上界 → multiplier = 4 → 冷卻 × 4。
        let s = MaCrossover::new();
        let snap = indicator_with(Some(s.adx_threshold * 2.5), Some(0.75));
        let got = s.compute_trend_adjusted_cooldown(Some(&snap));
        assert_eq!(got, s.cooldown_ms * 4, "strong trend must 4× cooldown");
    }

    #[test]
    fn test_a2_cooldown_beyond_upper_bound_clamps() {
        // ADX above 2.5× threshold and Hurst above 0.75 clamp at trend_score=1.
        // 上界之上再往上也不會加倍 — clamp 在 1.0。
        let s = MaCrossover::new();
        let snap = indicator_with(Some(s.adx_threshold * 5.0), Some(0.95));
        assert_eq!(
            s.compute_trend_adjusted_cooldown(Some(&snap)),
            s.cooldown_ms * 4
        );
    }

    #[test]
    fn test_a2_cooldown_mixed_adx_only_partial_boost() {
        // Pure ADX factor = 0.5 (midpoint) + Hurst = 0.50 → trend_score = 0.3 →
        // multiplier = 1 + 0.3×3 = 1.9. Use adx_threshold=20, so midpoint is
        // 20 + 0.5 × (30) = 35 (since range = 30).
        // 純 ADX 半途 + Hurst 平 → score = 0.3 → multiplier 1.9。
        let s = MaCrossover::new();
        // adx_threshold=20, range=30 → ADX=35 gives factor=0.5.
        let snap = indicator_with(Some(35.0), Some(0.50));
        let expected = (s.cooldown_ms as f64 * (1.0 + 0.3 * 3.0)) as u64;
        assert_eq!(s.compute_trend_adjusted_cooldown(Some(&snap)), expected);
    }

    #[test]
    fn test_a2_cooldown_missing_adx_uses_zero() {
        // Missing ADX treated as 0 → factor clamps to 0 → base × (1 + 0.4×hurst_factor×3).
        // With Hurst=0.75 → hurst_factor=1 → multiplier=2.2.
        // 無 ADX 視為 0 → 僅 Hurst 貢獻。
        let s = MaCrossover::new();
        let snap = indicator_with(None, Some(0.75));
        let expected = (s.cooldown_ms as f64 * (1.0 + 0.4 * 3.0)) as u64;
        assert_eq!(s.compute_trend_adjusted_cooldown(Some(&snap)), expected);
    }

    #[test]
    fn test_a2_cooldown_respects_max_cooldown_boost_param() {
        // max_cooldown_boost = 0 disables A2 entirely → cooldown always base.
        // max_cooldown_boost=0 → A2 被禁用 → 永遠基準。
        let mut s = MaCrossover::new();
        s.max_cooldown_boost = 0.0;
        let snap = indicator_with(Some(s.adx_threshold * 3.0), Some(0.90));
        assert_eq!(
            s.compute_trend_adjusted_cooldown(Some(&snap)),
            s.cooldown_ms
        );
    }

    #[test]
    fn test_a2_validate_max_cooldown_boost_bounds() {
        // Validation: max_cooldown_boost ∈ [0, 10].
        // 驗證：max_cooldown_boost 範圍 [0, 10]。
        let mut p = MaCrossoverParams::default();
        p.max_cooldown_boost = -0.1;
        assert!(p.validate().is_err());
        p.max_cooldown_boost = 10.1;
        assert!(p.validate().is_err());
        p.max_cooldown_boost = 0.0;
        assert!(p.validate().is_ok());
        p.max_cooldown_boost = 10.0;
        assert!(p.validate().is_ok());
    }

    // ── EDGE-P2-3 Phase 2+ (b): PostOnly maker entry tests ──
    // ── EDGE-P2-3 Phase 2+ (b)：PostOnly maker 入場測試 ──

    /// Default constructor must keep `use_maker_entry = false` (root principle #6 —
    /// failure default shrink). Market entry emits order_type="market" + TIF=None
    /// (byte-identical legacy behavior) when long-entry gate fires.
    /// 默認 maker 關閉時，入場 intent 維持 market + TIF=None（與舊行為 byte-identical）。
    #[test]
    fn test_ma_crossover_market_entry_when_maker_disabled() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0; // disable persistence for unit tests
        assert!(!s.use_maker_entry, "use_maker_entry must default to false");
        let i = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert_eq!(intent.order_type, "market");
                assert!(intent.limit_price.is_none());
                assert!(intent.time_in_force.is_none());
                assert!(intent.maker_timeout_ms.is_none());
            }
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    /// Long entry with maker enabled emits PostOnly Limit below last_price.
    /// Limit = price × (1 − offset_bps / 10_000), bit-exact.
    /// 多頭入場啟用 maker → PostOnly Limit 掛在 last_price 下方（bit-exact）。
    #[test]
    fn test_ma_crossover_buy_postonly_below_last_price() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0;
        s.use_maker_entry = true;
        s.maker_price_offset_bps = 1.0; // 1 bps
        let i = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!(intent.is_long);
                assert_eq!(intent.order_type, "limit");
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                assert_eq!(intent.maker_timeout_ms, Some(45_000));
                let lp = intent.limit_price.expect("limit_price set");
                let expected = 50000.0 * (1.0 - 1.0 / 10_000.0);
                assert!(
                    (lp - expected).abs() < 1e-9,
                    "buy PostOnly must be below last_price: got {lp}, expected {expected}"
                );
                assert!(lp < 50000.0, "buy limit must rest below last_price");
            }
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    /// Short entry with maker enabled emits PostOnly Limit above last_price.
    /// Limit = price × (1 + offset_bps / 10_000), bit-exact.
    /// 空頭入場啟用 maker → PostOnly Limit 掛在 last_price 上方。
    #[test]
    fn test_ma_crossover_sell_postonly_above_last_price() {
        let mut s = MaCrossover::new();
        s.min_persistence_ms = 0;
        s.use_maker_entry = true;
        s.maker_price_offset_bps = 2.0; // 2 bps
        // Fast KAMA below slow SMA → short signal.
        // 快 KAMA 低於慢 SMA → 空頭信號。
        let i = s.on_tick(&ctx_with(101.0, 100.0, 25.0, 0));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!(!intent.is_long);
                assert_eq!(intent.order_type, "limit");
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                assert_eq!(intent.maker_timeout_ms, Some(45_000));
                let lp = intent.limit_price.expect("limit_price set");
                let expected = 50000.0 * (1.0 + 2.0 / 10_000.0);
                assert!(
                    (lp - expected).abs() < 1e-9,
                    "sell PostOnly must be above last_price: got {lp}, expected {expected}"
                );
                assert!(lp > 50000.0, "sell limit must rest above last_price");
            }
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    /// update_params round-trips maker fields so Agent IPC can toggle at runtime.
    /// Also verifies maker_limit_timeout_ms is clamped on assignment
    /// (500_000 → 300_000 upper bound, 1_000 → 15_000 lower bound).
    /// update_params 來回保留 maker 欄位；timeout 於寫入時 clamp 到 [15s, 300s]。
    #[test]
    fn test_ma_crossover_update_params_roundtrips_maker_fields() {
        let mut s = MaCrossover::new();
        let mut params = s.get_params();
        assert!(!params.use_maker_entry);
        assert!((params.maker_price_offset_bps - 1.0).abs() < 1e-9);
        assert_eq!(params.maker_limit_timeout_ms, 45_000);

        // Round-trip basic values.
        // 基本往返。
        params.use_maker_entry = true;
        params.maker_price_offset_bps = 3.0;
        params.maker_limit_timeout_ms = 60_000;
        s.update_params(params).expect("update_params");
        let p2 = s.get_params();
        assert!(p2.use_maker_entry);
        assert!((p2.maker_price_offset_bps - 3.0).abs() < 1e-9);
        assert_eq!(p2.maker_limit_timeout_ms, 60_000);
        assert!(s.use_maker_entry);

        // Upper clamp: 500_000 → 300_000.
        // 上限 clamp：500_000 → 300_000。
        let mut params_hi = s.get_params();
        params_hi.maker_limit_timeout_ms = 500_000;
        s.update_params(params_hi).expect("update_params clamp hi");
        assert_eq!(s.get_params().maker_limit_timeout_ms, 300_000);

        // Lower clamp: 1_000 → 15_000.
        // 下限 clamp：1_000 → 15_000。
        let mut params_lo = s.get_params();
        params_lo.maker_limit_timeout_ms = 1_000;
        s.update_params(params_lo).expect("update_params clamp lo");
        assert_eq!(s.get_params().maker_limit_timeout_ms, 15_000);
    }
}
