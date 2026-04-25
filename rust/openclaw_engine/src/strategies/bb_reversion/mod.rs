//! BB Reversion Strategy V2 — Bollinger Band mean reversion + RSI filter.
//! BB 回歸策略 V2 — 布林帶均值回歸 + RSI 過濾。
//!
//! MODULE_NOTE (EN): Mean-reversion entries at Bollinger Band extremes with
//!   RSI oversold/overbought confirmation. Exits on band middle touch or time stop.
//!   G5-05 (2026-04-24) split this directory:
//!     - `params.rs`  — `BbReversionParams` struct, Default, StrategyParams impl
//!     - `tests.rs`   — `#[cfg(test)] mod tests`
//!     - `mod.rs`     — `BbReversion` struct + impl + `Strategy` trait
//!   Public API preserved via `pub use params::BbReversionParams;`.
//! MODULE_NOTE (中): 在布林帶極端值處均值回歸入場，RSI 超賣/超買確認。
//!   觸及帶中線或時間止損出場。G5-05（2026-04-24）將本目錄拆分：
//!     - `params.rs`  — `BbReversionParams` 結構、Default、StrategyParams 實作
//!     - `tests.rs`   — `#[cfg(test)] mod tests`
//!     - `mod.rs`     — `BbReversion` 結構 + 實作 + `Strategy` trait
//!   公開 API 透過 `pub use params::BbReversionParams;` 維持不變。

mod params;
pub use params::BbReversionParams;

#[cfg(test)]
mod tests;

use std::collections::HashMap;

use super::common::{compute_post_only_price, MakerPriceInputs, PerSymbolState, TrendCooldown};
use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use tracing::info;

pub struct BbReversion {
    active: bool,
    /// Per-symbol position tracking: symbol → is_long direction.
    /// E1-P0-2: Migrated from `HashMap<String, bool>` to `PerSymbolState<bool>`.
    /// 每幣種獨立持倉追蹤：symbol → 多空方向（E1-P0-2 包裝）。
    pub(crate) positions: PerSymbolState<bool>,
    /// Per-symbol last trade timestamp for cooldown.
    /// E1-P0-2: Migrated from `HashMap<String, u64>` to `TrendCooldown`. The
    /// original check `last_ms > 0 && ts < last_ms + cooldown_ms` maps exactly
    /// to `TrendCooldown::is_cooled_down` (unseen-symbol → None → cooled).
    /// 每幣種最後交易時間戳（E1-P0-2：改用 TrendCooldown，語意完全保留）。
    pub(crate) cooldown: TrendCooldown,
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
    pub(crate) persistence: PersistenceTracker,
    pub min_persistence_ms: u64,
    pub min_notional_usd: f64,
    /// G7-09c Phase 1: ticks INSIDE the inside quote for BBO-aware PostOnly.
    /// See `BbReversionParams::maker_price_buffer_ticks` for semantics. Note
    /// `use_limit` is currently force-disabled at line ~131 (GAP-9 — paper
    /// engine has no limit-order matcher), so this field is plumbing-only
    /// until GAP-9 lifts.
    /// G7-09c Phase 1：BBO-aware PostOnly buffer，語義見 params。注意 `use_limit`
    /// 在 ~131 行被 GAP-9 強制關閉，本欄位現為埋線。
    pub(crate) maker_price_buffer_ticks: u32,
}

impl BbReversion {
    pub fn new() -> Self {
        Self {
            active: true,
            positions: PerSymbolState::new(),
            cooldown: TrendCooldown::new(600_000),
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
            // G7-09c Phase 1: default 1 tick inside the inside quote.
            // G7-09c Phase 1：預設退一 tick。
            maker_price_buffer_ticks: 1,
        }
    }

    /// Phase 3a: Update tunable parameters.
    pub fn update_params(&mut self, params: BbReversionParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        // E1-P0-2: Keep TrendCooldown duration in sync with hot-reloaded param.
        // E1-P0-2：熱更新時同步 TrendCooldown 時長。
        self.cooldown.set_duration(params.cooldown_ms);
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
        // G7-09c Phase 1: hot-reload BBO buffer (validate() bounds [0, 10]).
        // Plumbing-only until GAP-9 lifts (use_limit force-disabled above).
        // G7-09c Phase 1：熱重載 BBO buffer（[0, 10]），GAP-9 解禁前為埋線。
        self.maker_price_buffer_ticks = params.maker_price_buffer_ticks;
        info!(strategy = "bb_reversion", "params updated / 參數已更新");
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
            // G7-09c Phase 1: round-trip BBO buffer for IPC consumers.
            // G7-09c Phase 1：BBO buffer 經 IPC 來回。
            maker_price_buffer_ticks: self.maker_price_buffer_ticks,
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
        // G7-09c Phase 1: when `use_limit` enabled (currently force-disabled by
        // GAP-9 — see line ~131), use BBO-aware passive PostOnly price instead
        // of legacy bb_lower/bb_upper × (1 ± limit_offset_bps/10_000) which
        // crosses the book on Bybit (RCA `7f0e793`). bb_lower/bb_upper kept in
        // sig for back-compat / future band-anchored variant. `use_limit`
        // GAP-9 force-disable retained — see Backlog A for that scope.
        // G7-09c Phase 1：當 `use_limit` 啟用時（目前 GAP-9 強制關閉），改用
        // BBO-aware 被動 PostOnly 價，取代舊 bb_lower/bb_upper × (1 ± offset/萬)
        // 公式（RCA 顯示舊式 100% 跨 book）；GAP-9 force-disable 不解禁，
        // 屬 Backlog A scope。bb_lower/bb_upper 保留供未來 band-anchored 變體。
        let _ = (bb_lower, bb_upper); // silence unused-on-cold-path warning
        let (order_type, limit_price) = if self.use_limit {
            let inputs = MakerPriceInputs {
                last_price: ctx.price,
                best_bid: ctx.best_bid,
                best_ask: ctx.best_ask,
                tick_size: ctx.tick_size,
            };
            let price = compute_post_only_price(
                is_long,
                inputs,
                self.limit_offset_bps,
                self.maker_price_buffer_ticks,
                "bb_reversion",
                ctx.symbol,
            );
            ("limit".to_string(), Some(price))
        } else {
            ("market".to_string(), None)
        };
        let scaled =
            crate::tick_pipeline::on_tick_helpers::clamp_confidence(conf * self.conf_scale);
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
            time_in_force: None,
            maker_timeout_ms: None,
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
                // Sentinel 0 → unseen prior to mutation; clear to restore.
                // 哨兵 0 → 變更前未見；清除以還原。
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
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
        // Snapshot pre-mutation last_ms for RC-04 (sentinel 0 when unseen).
        // 為 RC-04 快照變更前的 last_ms（未見時為 0 哨兵）。
        let last_ms = self.cooldown.last_ms(ctx.symbol).unwrap_or(0);
        // E1-P0-2: Cooldown check delegated to shared TrendCooldown. Unseen
        // symbol's None branch maps to the old `last_ms == 0` "cooled" case.
        // E1-P0-2：冷卻檢查委派給 TrendCooldown；未見的 None 分支對應原本 last_ms==0 的「已冷卻」。
        if !self.cooldown.is_cooled_down(ctx.symbol, ctx.timestamp_ms) {
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
        self.prev_position.insert(
            ctx.symbol.to_string(),
            self.positions.get(ctx.symbol).copied(),
        );
        self.prev_last_trade_ms
            .insert(ctx.symbol.to_string(), last_ms);

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
                        ind.hurst
                            .as_ref()
                            .map(|h| h.regime.as_str())
                            .unwrap_or("uncertain"),
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
                    let fr_boost = if funding_aligned(is_long) {
                        funding_boost
                    } else {
                        0.0
                    };
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
                    self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
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
                    self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
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
