//! BB Reversion Strategy V2 — Bollinger Band mean reversion + RSI filter.
//! BB 回歸策略 V2 — 布林帶均值回歸 + RSI 過濾。
//!
//! MODULE_NOTE (EN): Mean-reversion entries at Bollinger Band extremes with
//!   RSI oversold/overbought confirmation. Exits on band middle touch or time stop.
//! MODULE_NOTE (中): 在布林帶極端值處均值回歸入場，RSI 超賣/超買確認。
//!   觸及帶中線或時間止損出場。

use std::collections::HashMap;

use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use serde::{Deserialize, Serialize};
use tracing::info;

/// Tunable parameters for BB Reversion strategy (Phase 3a).
/// BB 回歸策略的可調參數。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct BbReversionParams {
    pub cooldown_ms: u64,
    pub default_qty: f64,
    pub use_limit: bool,
    pub limit_offset_bps: f64,
    /// RSI oversold threshold for long entry / RSI 超賣閾值（做多入場）
    pub rsi_oversold: f64,
    /// RSI overbought threshold for short entry / RSI 超買閾值（做空入場）
    pub rsi_overbought: f64,
    /// QC-#7: Hurst regime confidence boost for mean-reverting regime (default 0.1).
    /// QC-#7：均值回歸市場狀態信心加成（默認 0.1）。
    pub hurst_regime_boost: f64,
    // ── G-SR-1 confluence + persistence fields (A0-c) ──
    /// Minimum signal persistence before entry (ms). / 入場前信號最小持續時間（ms）。
    pub min_persistence_ms: u64,
    /// Minimum order notional (USD). / 最小訂單名義值（USD）。
    pub min_notional_usd: f64,
    /// EDGE-P1-2: Minimum |funding_rate| to trigger directional boost (default 5 bps = 0.0005).
    /// EDGE-P1-2：觸發方向性加成的最低 |funding_rate|（默認 5 bps = 0.0005）。
    pub funding_rate_threshold: f64,
    /// EDGE-P1-2: Confidence boost when funding rate is extreme + aligned with signal (default 0.08).
    /// EDGE-P1-2：資金費率極端且與信號方向一致時的信心加成（默認 0.08）。
    pub funding_rate_boost: f64,
    /// Confluence weights + thresholds (reversion profile, inverted ADX).
    /// 匯流權重 + 閾值（回歸配置，反轉 ADX）。
    pub weight_adx: f64,
    pub weight_regime: f64,
    pub weight_volume: f64,
    pub weight_momentum: f64,
    pub adx_floor: f64,
    pub adx_inverted: bool,
    pub confluence_threshold_no_trade: f64,
    pub confluence_threshold_light: f64,
    pub confluence_threshold_full: f64,
}

impl Default for BbReversionParams {
    fn default() -> Self {
        let cc = ConfluenceConfig::reversion();
        Self {
            cooldown_ms: 600_000,
            default_qty: 1e9,
            use_limit: false,
            limit_offset_bps: 10.0,
            rsi_oversold: 30.0,
            rsi_overbought: 70.0,
            hurst_regime_boost: 0.1,
            funding_rate_threshold: 0.0005,
            funding_rate_boost: 0.08,
            min_persistence_ms: 180_000,
            min_notional_usd: 10.0,
            weight_adx: cc.weight_adx,
            weight_regime: cc.weight_regime,
            weight_volume: cc.weight_volume,
            weight_momentum: cc.weight_momentum,
            adx_floor: cc.adx_floor,
            adx_inverted: true,
            confluence_threshold_no_trade: cc.threshold_no_trade,
            confluence_threshold_light: cc.threshold_light,
            confluence_threshold_full: cc.threshold_full,
        }
    }
}

impl StrategyParams for BbReversionParams {
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
                name: "default_qty".into(),
                min: 0.001,
                max: 1e12,
                step: None,
                agent_adjustable: false,
                db_persisted: true,
            },
            // GAP-9: use_limit / limit_offset_bps removed from agent-tunable
            // ranges. Paper engine has no order-book sim and silently degrades
            // limit→market, so enabling these would corrupt PnL accounting.
            // Re-add when paper engine grows a real limit-order matcher.
            // GAP-9：use_limit/limit_offset_bps 從可調列表移除（paper 無撮合）。
            ParamRange {
                name: "rsi_oversold".into(),
                min: 5.0,
                max: 45.0,
                step: Some(5.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "rsi_overbought".into(),
                min: 55.0,
                max: 95.0,
                step: Some(5.0),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "hurst_regime_boost".into(),
                min: 0.0,
                max: 0.3,
                step: Some(0.05),
                agent_adjustable: true,
                db_persisted: true,
            },
            // ── EDGE-P1-2: Funding rate signal params ──
            ParamRange {
                name: "funding_rate_threshold".into(),
                min: 0.0001,
                max: 0.005,
                step: Some(0.0001),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "funding_rate_boost".into(),
                min: 0.0,
                max: 0.2,
                step: Some(0.01),
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
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.cooldown_ms < 60_000 {
            return Err("cooldown_ms must be >= 60s".into());
        }
        if self.limit_offset_bps < 0.0 || self.limit_offset_bps > 200.0 {
            return Err("limit_offset_bps must be in [0, 200]".into());
        }
        if self.rsi_oversold < 5.0 || self.rsi_oversold > 45.0 {
            return Err("rsi_oversold must be in [5, 45]".into());
        }
        if self.rsi_overbought < 55.0 || self.rsi_overbought > 95.0 {
            return Err("rsi_overbought must be in [55, 95]".into());
        }
        if self.hurst_regime_boost < 0.0 || self.hurst_regime_boost > 0.3 {
            return Err("hurst_regime_boost must be in [0, 0.3]".into());
        }
        if self.funding_rate_threshold < 0.0001 || self.funding_rate_threshold > 0.005 {
            return Err("funding_rate_threshold must be in [0.0001, 0.005]".into());
        }
        if self.funding_rate_boost < 0.0 || self.funding_rate_boost > 0.2 {
            return Err("funding_rate_boost must be in [0, 0.2]".into());
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
        Ok(())
    }
}

impl BbReversionParams {
    /// Build ConfluenceConfig from flat params (reversion profile, inverted ADX).
    /// 從扁平參數構建 ConfluenceConfig（回歸配置，反轉 ADX）。
    pub fn build_confluence_config(&self) -> ConfluenceConfig {
        ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: self.adx_inverted,
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: true,
        }
    }
}

pub struct BbReversion {
    active: bool,
    /// Per-symbol position tracking: symbol → is_long direction.
    /// 每幣種獨立持倉追蹤：symbol → 多空方向。
    positions: HashMap<String, bool>,
    /// Per-symbol last trade timestamp for cooldown.
    /// 每幣種最後交易時間戳（用於冷卻）。
    last_trade_ms: HashMap<String, u64>,
    pub(crate) cooldown_ms: u64,
    default_qty: f64,
    // RC-07: Limit order support — Agent can switch from market to limit entries
    // RC-07：限價單支持 — Agent 可從市價切換為限價入場
    /// When true, entry orders use limit instead of market / 為 true 時入場用限價單
    pub use_limit: bool,
    /// Basis points inside the band for limit price offset / 限價偏移（基點，band 內側）
    pub limit_offset_bps: f64,
    /// FIX-24: Configurable RSI thresholds / 可配置 RSI 閾值
    pub rsi_oversold: f64,
    pub rsi_overbought: f64,
    /// QC-H3: Entry confidence base (default 0.6). / 入場信心基礎值。
    pub(crate) entry_conf_base: f64,
    /// QC-H3: Exit confidence base (default 0.55). / 出場信心基礎值。
    pub(crate) exit_conf_base: f64,
    /// QC-H3: Exit %B lower bound (default 0.2). / 出場 %B 下界。
    pub(crate) exit_pctb_lower: f64,
    /// QC-H3: Exit %B upper bound (default 0.8). / 出場 %B 上界。
    pub(crate) exit_pctb_upper: f64,
    /// QC-#7: Hurst regime boost for mean-reverting regime (default 0.1).
    /// QC-#7：均值回歸市場狀態信心加成。
    pub(crate) hurst_regime_boost: f64,
    /// EDGE-P1-2: Minimum |funding_rate| to trigger directional boost.
    /// EDGE-P1-2：觸發方向性加成的最低 |funding_rate|。
    pub(crate) funding_rate_threshold: f64,
    /// EDGE-P1-2: Confidence boost when extreme funding rate aligns with signal.
    /// EDGE-P1-2：資金費率極端且方向一致時的信心加成。
    pub(crate) funding_rate_boost: f64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    prev_position: HashMap<String, Option<bool>>,
    prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    conf_scale: f64,
    // ── G-SR-1: Confluence scoring + persistence filter (A0-c, A1) ──
    pub confluence_config: ConfluenceConfig,
    persistence: PersistenceTracker,
    pub min_persistence_ms: u64,
    pub min_notional_usd: f64,
}

impl BbReversion {
    pub fn new() -> Self {
        Self {
            active: true,
            positions: HashMap::new(),
            last_trade_ms: HashMap::new(),
            cooldown_ms: 600_000,
            default_qty: 1e9,
            use_limit: false,
            limit_offset_bps: 10.0,
            rsi_oversold: 30.0,
            rsi_overbought: 70.0,
            entry_conf_base: 0.6,
            exit_conf_base: 0.55,
            exit_pctb_lower: 0.2,
            exit_pctb_upper: 0.8,
            hurst_regime_boost: 0.1,
            funding_rate_threshold: 0.0005,
            funding_rate_boost: 0.08,
            prev_position: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
            confluence_config: ConfluenceConfig::reversion(),
            persistence: PersistenceTracker::new(),
            min_persistence_ms: 180_000,
            min_notional_usd: 10.0,
        }
    }

    /// Phase 3a: Update tunable parameters.
    pub fn update_params(&mut self, params: BbReversionParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        self.default_qty = params.default_qty;
        // GAP-9: paper engine cannot honor limit orders (no order-book sim).
        // Force market mode regardless of incoming param to keep PnL faithful.
        // GAP-9：paper 模式無法支援限價單，強制 market。
        if params.use_limit {
            tracing::warn!(
                strategy = "bb_reversion",
                "use_limit=true ignored: paper engine has no limit-order sim (GAP-9)"
            );
        }
        self.use_limit = false;
        self.limit_offset_bps = params.limit_offset_bps;
        self.rsi_oversold = params.rsi_oversold;
        self.rsi_overbought = params.rsi_overbought;
        self.hurst_regime_boost = params.hurst_regime_boost;
        self.funding_rate_threshold = params.funding_rate_threshold;
        self.funding_rate_boost = params.funding_rate_boost;
        // R4-7: Rebuild ConfluenceConfig from updated params.
        self.confluence_config = params.build_confluence_config();
        self.min_persistence_ms = params.min_persistence_ms;
        self.min_notional_usd = params.min_notional_usd;
        info!(strategy = "bb_reversion", "params updated / 參數���更新");
        Ok(())
    }

    /// Phase 3a: Get current tunable parameters.
    pub fn get_params(&self) -> BbReversionParams {
        BbReversionParams {
            cooldown_ms: self.cooldown_ms,
            default_qty: self.default_qty,
            use_limit: self.use_limit,
            limit_offset_bps: self.limit_offset_bps,
            rsi_oversold: self.rsi_oversold,
            rsi_overbought: self.rsi_overbought,
            hurst_regime_boost: self.hurst_regime_boost,
            funding_rate_threshold: self.funding_rate_threshold,
            funding_rate_boost: self.funding_rate_boost,
            min_persistence_ms: self.min_persistence_ms,
            min_notional_usd: self.min_notional_usd,
            weight_adx: self.confluence_config.weight_adx,
            weight_regime: self.confluence_config.weight_regime,
            weight_volume: self.confluence_config.weight_volume,
            weight_momentum: self.confluence_config.weight_momentum,
            adx_floor: self.confluence_config.adx_floor,
            adx_inverted: self.confluence_config.invert_adx,
            confluence_threshold_no_trade: self.confluence_config.threshold_no_trade,
            confluence_threshold_light: self.confluence_config.threshold_light,
            confluence_threshold_full: self.confluence_config.threshold_full,
        }
    }

    /// Build entry intent with explicit qty (confluence-scaled). / 使用顯式 qty 構建入場 intent。
    ///
    /// EDGE-P3-1 A6: last two params carry the decision-time confluence score
    /// (raw [0, 65]) and persistence elapsed ms so the edge predictor gate in
    /// IntentProcessor can read them from the intent instead of zero placeholders.
    /// EDGE-P3-1 A6：最後兩參數為決策時的 confluence/persistence，供 predictor gate 使用。
    fn make_entry_intent_with_qty(
        &self,
        ctx: &TickContext<'_>,
        is_long: bool,
        conf: f64,
        bb_lower: f64,
        bb_upper: f64,
        qty: f64,
        confluence_score: Option<f32>,
        persistence_elapsed_ms: Option<u64>,
    ) -> OrderIntent {
        let (order_type, limit_price) = if self.use_limit {
            let price = if is_long {
                bb_lower * (1.0 + self.limit_offset_bps / 10_000.0)
            } else {
                bb_upper * (1.0 - self.limit_offset_bps / 10_000.0)
            };
            ("limit".to_string(), Some(price))
        } else {
            ("market".to_string(), None)
        };
        let scaled = crate::tick_pipeline::on_tick_helpers::clamp_confidence(conf * self.conf_scale);
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
        }
    }
}

impl Strategy for BbReversion {
    fn name(&self) -> &str {
        "bb_reversion"
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
                Some(b) => { self.positions.insert(sym.clone(), *b); }
                None => { self.positions.remove(sym); }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 { self.last_trade_ms.remove(sym); } else { self.last_trade_ms.insert(sym.clone(), ts); }
        }
    }

    fn on_external_close(&mut self, symbol: &str) {
        self.positions.remove(symbol);
        self.persistence.clear(symbol);
    }

    fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let ind = match ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        let last_ms = self.last_trade_ms.get(ctx.symbol).copied().unwrap_or(0);
        if last_ms > 0 && ctx.timestamp_ms < last_ms + self.cooldown_ms {
            return vec![];
        }

        let bb = match &ind.bollinger {
            Some(b) => b,
            None => return vec![],
        };
        let rsi = ind.rsi_14.unwrap_or(50.0);

        // A4: Hurst regime boost — mean-reverting regime boosts reversion confidence
        // A4：Hurst 市场状态 — 均值回归型市场提升回归信心
        // QC-#7: hurst_regime_boost configurable (was hardcoded 0.1)
        let hurst_boost: f64 = match &ind.hurst {
            Some(h) if h.regime == "mean_reverting" => self.hurst_regime_boost,
            _ => 0.0,
        };

        // EDGE-P1-2: Funding rate directional boost — extreme funding rate signals
        // overleveraged crowd, boosting mean reversion confidence when aligned.
        // Positive funding (shorts pay longs) → market is overleveraged long → boost short entries.
        // Negative funding (longs pay shorts) → market is overleveraged short → boost long entries.
        // EDGE-P1-2：資金費率方向加成 — 極端費率表明市場單邊過度槓桿，
        // 正費率 → 做多過度 → 加成做空回歸；負費率 → 做空過度 → 加成做多回歸。
        let funding_boost: f64 = match ctx.funding_rate {
            Some(fr) if fr.abs() >= self.funding_rate_threshold => self.funding_rate_boost,
            _ => 0.0,
        };
        // Whether funding rate aligns with a given signal direction:
        // fr > 0 aligns with short (is_long=false), fr < 0 aligns with long (is_long=true).
        let funding_aligned = |is_long: bool| -> bool {
            match ctx.funding_rate {
                Some(fr) if fr.abs() >= self.funding_rate_threshold => {
                    (fr > 0.0 && !is_long) || (fr < 0.0 && is_long)
                }
                _ => false,
            }
        };

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        self.prev_position.insert(ctx.symbol.to_string(), self.positions.get(ctx.symbol).copied());
        self.prev_last_trade_ms.insert(ctx.symbol.to_string(), last_ms);

        let mut intents = Vec::new();
        match self.positions.get(ctx.symbol).copied() {
            None => {
                // G-SR-1 A1: Determine signal for persistence check.
                let signal: Option<bool> = if bb.percent_b < 0.0 && rsi < self.rsi_oversold {
                    Some(true) // oversold → long
                } else if bb.percent_b > 1.0 && rsi > self.rsi_overbought {
                    Some(false) // overbought → short
                } else {
                    None
                };

                // A1: Persistence filter / 持續性過濾
                if !self.persistence.check(
                    ctx.symbol,
                    signal,
                    ctx.timestamp_ms,
                    self.min_persistence_ms,
                    false,
                ) {
                    return intents;
                }

                if let Some(is_long) = signal {
                    // A2: Confluence scoring (reversion profile, inverted ADX).
                    // A2：匯流評分（回歸配置，反轉 ADX）。
                    let score = confluence::compute_score(
                        &self.confluence_config,
                        true, // signal already confirmed
                        ind.adx.as_ref().map(|a| a.adx),
                        ind.hurst.as_ref().map(|h| h.regime.as_str()).unwrap_or("uncertain"),
                        ind.volume_ratio,
                        ind.rsi_14,
                        is_long,
                    );
                    let qty_pct = confluence::score_to_qty_pct(score, &self.confluence_config);
                    if qty_pct <= 0.0 {
                        return intents;
                    }
                    let qty = self.default_qty * qty_pct;
                    if qty * ctx.price < self.min_notional_usd {
                        return intents;
                    }

                    // EDGE-P1-2: Add funding_boost when aligned with signal direction.
                    let fr_boost = if funding_aligned(is_long) { funding_boost } else { 0.0 };
                    let conf_with_score = match score {
                        Some(s) if s > 0.0 => (s / 65.0 + fr_boost).min(1.0),
                        _ => (self.entry_conf_base + hurst_boost + fr_boost).min(1.0),
                    };
                    // EDGE-P3-1 A6: pass decision-time confluence + persistence
                    // to the intent for the predictor gate.
                    // EDGE-P3-1 A6：把決策時的 confluence/persistence 寫入 intent。
                    let confluence_score = score.map(|s| s as f32);
                    let persistence_elapsed_ms =
                        self.persistence.elapsed_ms(ctx.symbol, ctx.timestamp_ms);
                    intents.push(StrategyAction::Open(self.make_entry_intent_with_qty(
                        ctx,
                        is_long,
                        conf_with_score,
                        bb.lower,
                        bb.upper,
                        qty,
                        confluence_score,
                        persistence_elapsed_ms,
                    )));
                    self.positions.insert(ctx.symbol.to_string(), is_long);
                    self.last_trade_ms.insert(ctx.symbol.to_string(), ctx.timestamp_ms);
                }
            }
            Some(_is_long) => {
                // Exit: %B returns to [0.2, 0.8] = textbook mean-reversion target reached.
                // Wider than exact 0.5 to handle crypto mean-overshoot.
                // 出場：%B 回到 [0.2, 0.8] = 教科書均值回歸目標。比精確 0.5 更寬以應對加密貨幣超調。
                // QC-H3: exit %B range + exit_conf_base configurable (was [0.2, 0.8] / 0.55)
                if bb.percent_b >= self.exit_pctb_lower && bb.percent_b <= self.exit_pctb_upper {
                    let exit_conf = (self.exit_conf_base + hurst_boost).clamp(0.4, 0.8);
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.to_string(),
                        confidence: exit_conf,
                        reason: "bb_mean_revert".into(),
                    });
                    self.positions.remove(ctx.symbol);
                    self.last_trade_ms.insert(ctx.symbol.to_string(), ctx.timestamp_ms);
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: BbReversionParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&BbReversionParams::param_ranges()).unwrap_or_default()
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
    use openclaw_core::indicators::{AdxResult, BollingerResult, IndicatorSnapshot};

    fn ctx_bb(pct_b: f64, rsi: f64, ts: u64) -> TickContext<'static> {
        use openclaw_core::indicators::HurstResult;
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            bollinger: Some(BollingerResult {
                upper: 51000.0,
                middle: 50000.0,
                lower: 49000.0,
                bandwidth: 0.04,
                percent_b: pct_b,
            }),
            rsi_14: Some(rsi),
            // ADX=15: low ADX = ranging market = ideal for mean-reversion.
            // ADX=15：低 ADX = 震盪市場 = 均值回歸理想環境。
            adx: Some(AdxResult { adx: 15.0, plus_di: 20.0, minus_di: 18.0 }),
            // EDGE-P1-3: Hurst mean_reverting regime needed for score ≥ 45 threshold.
            hurst: Some(HurstResult { hurst: 0.35, regime: "mean_reverting".into() }),
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

    #[test]
    fn test_long_oversold() {
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        }
    }

    #[test]
    fn test_exit_mean() {
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "bb_mean_revert"),
            other => panic!("expected StrategyAction::Close, got {:?}", other),
        }
    }

    // ── RC-07: Limit order tests / RC-07 限價單測試 ──

    #[test]
    fn test_limit_order_long() {
        // RC-07: use_limit=true, oversold entry produces limit order with correct price
        // RC-07：use_limit=true，超賣入場產生正確限價的限價單
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        s.use_limit = true;
        s.limit_offset_bps = 10.0; // 10 bps = 0.1%
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        let intent = match &i[0] {
            StrategyAction::Open(intent) => intent,
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        };
        assert!(intent.is_long);
        assert_eq!(intent.order_type, "limit");
        // limit_price = lower * (1 + 10/10000) = 49000 * 1.001 = 49049.0
        let expected = 49000.0 * (1.0 + 10.0 / 10_000.0);
        assert!(
            (intent.limit_price.unwrap() - expected).abs() < 1e-6,
            "expected limit_price={}, got={}",
            expected,
            intent.limit_price.unwrap()
        );
    }

    #[test]
    fn test_limit_order_short() {
        // RC-07: use_limit=true, overbought entry produces limit order
        // RC-07：use_limit=true，超買入場產生限價單
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        s.use_limit = true;
        s.limit_offset_bps = 10.0;
        let i = s.on_tick(&ctx_bb(1.1, 75.0, 0));
        assert_eq!(i.len(), 1);
        let intent = match &i[0] {
            StrategyAction::Open(intent) => intent,
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        };
        assert!(!intent.is_long);
        assert_eq!(intent.order_type, "limit");
        // limit_price = upper * (1 - 10/10000) = 51000 * 0.999 = 50949.0
        let expected = 51000.0 * (1.0 - 10.0 / 10_000.0);
        assert!(
            (intent.limit_price.unwrap() - expected).abs() < 1e-6,
            "expected limit_price={}, got={}",
            expected,
            intent.limit_price.unwrap()
        );
    }

    #[test]
    fn test_market_order_default() {
        // RC-07: use_limit=false (default), entries produce market orders
        // RC-07：use_limit=false（默認），入場產生市價單
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        assert!(!s.use_limit); // verify default is false / 確認默認為 false
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        let intent = match &i[0] {
            StrategyAction::Open(intent) => intent,
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        };
        assert_eq!(intent.order_type, "market");
        assert!(intent.limit_price.is_none());
    }

    #[test]
    fn test_exit_always_market() {
        // RC-07: Even with use_limit=true, exit orders are always market
        // RC-07：即使 use_limit=true，出場單永遠是市價單
        // With StrategyAction::Close, exit is no longer an OrderIntent —
        // it's a Close action that the pipeline handles directly.
        // 使用 StrategyAction::Close 後，出場不再是 OrderIntent。
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        s.use_limit = true;
        // Enter long with limit order / 限價入場做多
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        let entry_intent = match &i[0] {
            StrategyAction::Open(intent) => intent,
            other => panic!("expected StrategyAction::Open, got {:?}", other),
        };
        assert_eq!(entry_intent.order_type, "limit");
        // Exit at mean reversion / 均值回歸出場
        let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, .. } => {
                assert_eq!(reason, "bb_mean_revert", "exit must be a Close action");
            }
            other => panic!("expected StrategyAction::Close, got {:?}", other),
        }
    }

    #[test]
    fn test_bb_rev_param_ranges() {
        assert!(!BbReversionParams::param_ranges().is_empty());
    }

    #[test]
    fn test_bb_rev_validate() {
        assert!(BbReversionParams::default().validate().is_ok());
        assert!(BbReversionParams {
            cooldown_ms: 1000,
            ..Default::default()
        }
        .validate()
        .is_err());
    }

    #[test]
    fn test_bb_rev_update_roundtrip() {
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        let p = BbReversionParams {
            use_limit: true, // GAP-9: should be coerced to false
            limit_offset_bps: 20.0,
            ..Default::default()
        };
        assert!(s.update_params(p).is_ok());
        assert!(
            !s.get_params().use_limit,
            "GAP-9: use_limit must be coerced to false (paper has no limit sim)"
        );
        assert!((s.get_params().limit_offset_bps - 20.0).abs() < 0.01);
    }

    // ── G-SR-1 S3+S4: param_ranges + validation tests ──

    #[test]
    fn test_bbr_param_ranges_count() {
        let ranges = BbReversionParams::param_ranges();
        // 5 original + 2 funding_rate + 10 confluence = 17
        assert_eq!(ranges.len(), 17, "expected 17 param ranges, got {}", ranges.len());
    }

    #[test]
    fn test_bbr_param_ranges_confluence_names() {
        let ranges = BbReversionParams::param_ranges();
        let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
        for expected in &[
            "weight_adx", "weight_regime", "weight_volume", "weight_momentum",
            "adx_floor", "confluence_threshold_no_trade", "confluence_threshold_light",
            "confluence_threshold_full", "min_persistence_ms", "min_notional_usd",
        ] {
            assert!(names.contains(expected), "missing param range: {expected}");
        }
    }

    #[test]
    fn test_bbr_validate_default_ok() {
        assert!(BbReversionParams::default().validate().is_ok());
    }

    #[test]
    fn test_bbr_validate_bad_weight_sum() {
        let mut p = BbReversionParams::default();
        p.weight_momentum = 20.0; // sum = 15+30+10+20 = 75 ≠ 65
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_bbr_validate_bad_threshold_order() {
        let mut p = BbReversionParams::default();
        p.confluence_threshold_light = p.confluence_threshold_full; // equal = invalid
        assert!(p.validate().is_err());
    }

    #[test]
    fn test_bbr_validate_bad_min_notional() {
        let mut p = BbReversionParams::default();
        p.min_notional_usd = 0.0;
        assert!(p.validate().is_err());
    }

    // ── EDGE-P1-2: Funding rate signal tests ──

    /// Build a TickContext with funding rate for testing.
    fn ctx_bb_with_funding(pct_b: f64, rsi: f64, ts: u64, funding_rate: Option<f64>) -> TickContext<'static> {
        use openclaw_core::indicators::HurstResult;
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            bollinger: Some(BollingerResult {
                upper: 51000.0,
                middle: 50000.0,
                lower: 49000.0,
                bandwidth: 0.04,
                percent_b: pct_b,
            }),
            rsi_14: Some(rsi),
            adx: Some(AdxResult { adx: 15.0, plus_di: 20.0, minus_di: 18.0 }),
            hurst: Some(HurstResult { hurst: 0.35, regime: "mean_reverting".into() }),
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
            funding_rate,
            index_price: None,
        }
    }

    #[test]
    fn test_funding_rate_boost_short_with_positive_funding() {
        // Positive funding → overleveraged long → short reversion boost.
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;

        // Short signal: %B > 1.0, RSI > 70 (overbought)
        // With extreme positive funding rate → aligned with short → boost
        let ctx_with = ctx_bb_with_funding(1.2, 75.0, 1000, Some(0.001));
        let actions_with = s.on_tick(&ctx_with);
        assert!(!actions_with.is_empty(), "should produce short entry with positive funding");
        let conf_with = match &actions_with[0] {
            StrategyAction::Open(intent) => intent.confidence,
            _ => panic!("expected Open"),
        };

        // Same signal without funding rate
        s.positions.clear();
        s.last_trade_ms.clear();
        s.persistence = PersistenceTracker::new();
        let ctx_without = ctx_bb_with_funding(1.2, 75.0, 2000, None);
        let actions_without = s.on_tick(&ctx_without);
        assert!(!actions_without.is_empty());
        let conf_without = match &actions_without[0] {
            StrategyAction::Open(intent) => intent.confidence,
            _ => panic!("expected Open"),
        };

        assert!(
            conf_with > conf_without,
            "funding boost should increase confidence: {conf_with} > {conf_without}"
        );
    }

    #[test]
    fn test_funding_rate_boost_long_with_negative_funding() {
        // Negative funding → overleveraged short → long reversion boost.
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;

        // Long signal: %B < 0.0, RSI < 30 (oversold)
        let ctx_with = ctx_bb_with_funding(-0.1, 25.0, 1000, Some(-0.001));
        let actions_with = s.on_tick(&ctx_with);
        assert!(!actions_with.is_empty(), "should produce long entry with negative funding");
        let conf_with = match &actions_with[0] {
            StrategyAction::Open(intent) => intent.confidence,
            _ => panic!("expected Open"),
        };

        s.positions.clear();
        s.last_trade_ms.clear();
        s.persistence = PersistenceTracker::new();
        let ctx_without = ctx_bb_with_funding(-0.1, 25.0, 2000, None);
        let actions_without = s.on_tick(&ctx_without);
        assert!(!actions_without.is_empty());
        let conf_without = match &actions_without[0] {
            StrategyAction::Open(intent) => intent.confidence,
            _ => panic!("expected Open"),
        };

        assert!(
            conf_with > conf_without,
            "funding boost should increase confidence: {conf_with} > {conf_without}"
        );
    }

    #[test]
    fn test_funding_rate_no_boost_when_misaligned() {
        // Positive funding should NOT boost long entries (misaligned).
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;

        // Long signal with positive funding (misaligned)
        let ctx_misaligned = ctx_bb_with_funding(-0.1, 25.0, 1000, Some(0.001));
        let actions_mis = s.on_tick(&ctx_misaligned);
        assert!(!actions_mis.is_empty());
        let conf_mis = match &actions_mis[0] {
            StrategyAction::Open(intent) => intent.confidence,
            _ => panic!("expected Open"),
        };

        s.positions.clear();
        s.last_trade_ms.clear();
        s.persistence = PersistenceTracker::new();
        let ctx_none = ctx_bb_with_funding(-0.1, 25.0, 2000, None);
        let actions_none = s.on_tick(&ctx_none);
        assert!(!actions_none.is_empty());
        let conf_none = match &actions_none[0] {
            StrategyAction::Open(intent) => intent.confidence,
            _ => panic!("expected Open"),
        };

        assert!(
            (conf_mis - conf_none).abs() < 1e-10,
            "misaligned funding should not boost: {conf_mis} == {conf_none}"
        );
    }

    #[test]
    fn test_funding_rate_below_threshold_no_boost() {
        // Funding rate below threshold → no boost regardless of direction.
        let mut s = BbReversion::new();
        s.min_persistence_ms = 0;

        let ctx_small = ctx_bb_with_funding(1.2, 75.0, 1000, Some(0.0001)); // below 0.0005 threshold
        let actions_small = s.on_tick(&ctx_small);
        assert!(!actions_small.is_empty());
        let conf_small = match &actions_small[0] {
            StrategyAction::Open(intent) => intent.confidence,
            _ => panic!("expected Open"),
        };

        s.positions.clear();
        s.last_trade_ms.clear();
        s.persistence = PersistenceTracker::new();
        let ctx_none = ctx_bb_with_funding(1.2, 75.0, 2000, None);
        let actions_none = s.on_tick(&ctx_none);
        assert!(!actions_none.is_empty());
        let conf_none = match &actions_none[0] {
            StrategyAction::Open(intent) => intent.confidence,
            _ => panic!("expected Open"),
        };

        assert!(
            (conf_small - conf_none).abs() < 1e-10,
            "sub-threshold funding should not boost: {conf_small} == {conf_none}"
        );
    }

    #[test]
    fn test_funding_rate_validate_bounds() {
        let mut p = BbReversionParams::default();
        p.funding_rate_threshold = 0.00001; // below min 0.0001
        assert!(p.validate().is_err());

        let mut p = BbReversionParams::default();
        p.funding_rate_boost = 0.3; // above max 0.2
        assert!(p.validate().is_err());
    }
}
