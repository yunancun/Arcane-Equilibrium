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

use super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown};
use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};
use tracing::info;

pub struct BbReversion {
    active: bool,
    // P0 Option A-Lite (2026-05-11) — `self.positions` 與 `prev_position` 已移除。
    // 倉位狀態唯一來源為 `paper_state` (透過 `ctx.position_state` 注入)；
    // 策略以 `owner_strategy == self.name()` 過濾自家持倉，cross-strategy 倉位
    // 自然 skip entry 不觸發 exit zone，從根源杜絕 22:08 watchdog restart 後
    // 的 cross-strategy mass scalp（W7-2 sync self.positions = root trigger，
    // 移除後 race window 整體消失）。詳設計：
    //   `docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-11--p0_option_a_position_state_ssot_refactor.md`
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
    // P0 Option A-Lite — 保留供 on_rejection cooldown rollback；
    // 與 self.positions/prev_position 解耦（cooldown 不依賴本地 position state）。
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
    /// W-AUDIT-6d #6 (AMD-2026-05-09-02 §3) — pair MA confirmation gate enabled
    /// flag。Default true。Reversion entry 要求 long → price < ma；short → price > ma；
    /// MA 不可得時 fail-closed（不入場）。
    /// W-AUDIT-6d #6: pair MA confirmation gate flag (default true).
    pub(crate) require_ma_confirmation: bool,
    /// W-AUDIT-6d #6 — MA 種類（sma_20 / sma_50 / ema_12 / ema_26）。
    /// W-AUDIT-6d #6: MA kind for confirmation gate.
    pub(crate) ma_confirmation_kind: String,
}

impl BbReversion {
    pub fn new() -> Self {
        Self {
            active: true,
            // P0 Option A-Lite — 不再持 `positions` / `prev_position`，
            // 倉位 SSoT 為 paper_state。
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
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
            confluence_config: ConfluenceConfig::reversion(),
            persistence: PersistenceTracker::new(),
            min_persistence_ms: 180_000,
            min_notional_usd: 10.0,
            // G7-09c Phase 1: default 1 tick inside the inside quote.
            // G7-09c Phase 1：預設退一 tick。
            maker_price_buffer_ticks: 1,
            // W-AUDIT-6d #6 (AMD-2026-05-09-02 §3): default ON。
            require_ma_confirmation: true,
            ma_confirmation_kind: "sma_50".to_string(),
        }
    }

    /// W-AUDIT-6d #6 — 取對應 MA 值（依 `ma_confirmation_kind` 從 IndicatorSnapshot
    /// 取對應字段）。warm-up 不足 / 字段未填 → 回 None；caller 必 fail-closed。
    /// W-AUDIT-6d #6: pluck MA value per `ma_confirmation_kind`. None on warm-up.
    fn ma_value(&self, ind: &openclaw_core::indicators::IndicatorSnapshot) -> Option<f64> {
        match self.ma_confirmation_kind.as_str() {
            "sma_20" => ind.sma_20,
            "sma_50" => ind.sma_50,
            "ema_12" => ind.ema_12,
            "ema_26" => ind.ema_26,
            // 不可達（params validate 已 whitelist）；fail-closed 為防 hot-reload race。
            _ => None,
        }
    }

    /// W-AUDIT-6d #6 — MA pair confirmation gate。
    /// long entry: price < ma → 確認下方反轉（不違 trend）。
    /// short entry: price > ma → 確認上方反轉。
    /// MA 不可得 → 拒（fail-closed，§二 原則 6）。
    /// `require_ma_confirmation == false` → 直接 PASS（W-AUDIT-9 rollback 路徑）。
    /// W-AUDIT-6d #6: MA pair confirmation gate. Fail-closed when MA unavailable.
    fn ma_pair_allows_entry(
        &self,
        is_long: bool,
        price: f64,
        ind: &openclaw_core::indicators::IndicatorSnapshot,
    ) -> bool {
        if !self.require_ma_confirmation {
            return true;
        }
        match self.ma_value(ind) {
            Some(ma) if ma.is_finite() && ma > 0.0 => {
                // long entry → 必 price < ma；short entry → 必 price > ma。
                if is_long {
                    price < ma
                } else {
                    price > ma
                }
            }
            _ => {
                // MA 不可得（warm-up 不足或字段 None）→ fail-closed。
                tracing::debug!(
                    strategy = "bb_reversion",
                    ma_kind = %self.ma_confirmation_kind,
                    "MA confirmation skipped: MA unavailable, fail-closed (W-AUDIT-6d #6)"
                );
                false
            }
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
        // W-AUDIT-6d #6 (AMD-2026-05-09-02 §3): hot-reload MA pair confirmation。
        self.require_ma_confirmation = params.require_ma_confirmation;
        self.ma_confirmation_kind = params.ma_confirmation_kind;
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
            // W-AUDIT-6d #6 (AMD-2026-05-09-02 §3): round-trip MA pair gate config。
            require_ma_confirmation: self.require_ma_confirmation,
            ma_confirmation_kind: self.ma_confirmation_kind.clone(),
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
    ) -> Option<OrderIntent> {
        // G7-09c Phase 1: when `use_limit` enabled (currently force-disabled by
        // GAP-9 — see line ~131), use BBO-aware passive PostOnly price instead
        // of legacy bb_lower/bb_upper × (1 ± limit_offset_bps/10_000) which
        // crosses the book on Bybit (RCA `7f0e793`). If no safe maker price is
        // available, skip the new entry. bb_lower/bb_upper kept in sig for
        // back-compat / future band-anchored variant. `use_limit` GAP-9
        // force-disable retained — see Backlog A for that scope.
        // G7-09c Phase 1：當 `use_limit` 啟用時（目前 GAP-9 強制關閉），改用
        // BBO-aware 被動 PostOnly 價，取代舊 bb_lower/bb_upper × (1 ± offset/萬)
        // 公式（RCA 顯示舊式 100% 跨 book）；若無安全 maker 價則跳過新開倉。
        // GAP-9 force-disable 不解禁，屬 Backlog A scope。bb_lower/bb_upper 保留
        // 供未來 band-anchored 變體。
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
            )?;
            ("limit".to_string(), Some(price))
        } else {
            ("market".to_string(), None)
        };
        let scaled =
            crate::tick_pipeline::on_tick_helpers::clamp_confidence(conf * self.conf_scale);
        Some(OrderIntent {
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
        })
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

    /// W-AUDIT-8a Phase A spec §3 Phase A Deliverable #3：
    /// `bb_reversion`：`[Ta1m]`（純 1m kline TA）。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::Ta1m];
        TAGS
    }

    /// P0 Option A-Lite (2026-05-11) — on_rejection 化簡為純 cooldown rollback。
    ///
    /// 完全移除 W7-3 Option B duplicate_position sync（self.positions 已不存在）
    /// + RC-04 prev_position rollback。倉位 sync 改由下個 tick 從 paper_state
    /// 自然讀取（owner_strategy gate 過濾自家持倉），cross-strategy desync 從
    /// 根源消失。
    ///
    /// 保留 cooldown rollback：避免 reject 後 last_trade_ms 留在 entry tick
    /// 寫入的不可達狀態；rollback 確保下次 entry 仍受 cooldown_ms gate 阻擋
    /// hot loop（與 ma_crossover 同 pattern）。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                // 哨兵 0 → 變更前未見；清除以還原冷卻基線。
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    /// P0 Option A-Lite — 倉位被外部風控/止損平掉後，僅清 strategy-internal
    /// 訊號狀態（persistence）。本地 positions 已不存在；paper_state 端 close
    /// 後 ctx.position_state 自然為 None，策略下個 tick 即視為「未持倉」。
    fn on_external_close(&mut self, symbol: &str) {
        self.persistence.clear(symbol);
    }

    /// P0 Option A-Lite — on_fill no-op。
    /// paper_state.apply_fill 已寫入真實倉位，策略下個 tick 從
    /// `ctx.position_state` 自然讀取，不需本地 sync。顯式 override 為 no-op
    /// 是為了明確標示意圖（取代舊 W7-5 part 1 self.positions.insert sync）。
    fn on_fill(
        &mut self,
        _intent: &OrderIntent,
        _fill: &openclaw_core::execution::FillResult,
    ) {
        // 倉位由 paper_state 持有；本地不需同步。
    }

    // P0 Option A-Lite — import_positions 不再 override。
    // 使用 Strategy trait default no-op（mod.rs:137-139）。
    // bootstrap 後策略下個 tick 自然從 ctx.position_state 讀取 paper_state
    // 已 seed 的倉位（owner_strategy gate 過濾自家持倉）。

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        _surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
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

        // A4: Hurst regime boost — AntiPersistent regime boosts reversion confidence
        // A4：Hurst 市场状态 — AntiPersistent 市场提升回归信心
        // QC-#7: hurst_regime_boost configurable (was hardcoded 0.1)
        // G7-03 Phase B: typed `RegimeLabel` via `from_legacy_str`. Phase B's
        //   per-symbol hysteresis stabilizes the regime label upstream so this
        //   match sees a stabilized label when `hurst.enabled = true`, otherwise
        //   the instantaneous one (bit-identical to pre-G7-03 behaviour).
        // G7-03 Phase B：legacy 字串轉 typed enum；hurst 啟用時上游已穩定，停用時
        //   等同 G7-03 前的瞬時行為（bit-identical）。
        let hurst_boost: f64 = match &ind.hurst {
            Some(h)
                if crate::regime::RegimeLabel::from_legacy_str(&h.regime)
                    == crate::regime::RegimeLabel::AntiPersistent =>
            {
                self.hurst_regime_boost
            }
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

        // P0 Option A-Lite — cooldown rollback 快照（與 prev_position 解耦）。
        // entry 路徑 mutate cooldown 前 snapshot；on_rejection 由此 rollback。
        self.prev_last_trade_ms
            .insert(ctx.symbol.to_string(), last_ms);

        // P0 Option A-Lite — 倉位 SSoT = paper_state；策略以 owner_strategy
        // 過濾自家持倉。cross-strategy 倉位自然 skip entry 且不觸發 exit zone，
        // 從根源杜絕 22:08 watchdog restart 後 W7-2 sync 引發的 mass scalp。
        let owns_self = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name())
            .map(|p| p.is_long);

        let mut intents = Vec::new();
        match owns_self {
            None if ctx.position_state.is_some() => {
                // cross-strategy 持倉中（owner 非本策略）→ skip entry，不觸發 exit zone。
                // owner_strategy 過濾後直接跳出，杜絕 cross-strategy mass close。
                tracing::debug!(
                    target: "bb_reversion",
                    symbol = %ctx.symbol,
                    owner = %ctx.position_state.map(|p| p.owner_strategy.as_str()).unwrap_or(""),
                    "skip entry: cross-strategy paper_state position holds"
                );
                return intents;
            }
            None => {
                // Entry path — 無人持倉，按既有 reversion 訊號邏輯走。

                // G-SR-1 A1：判斷 signal 給 persistence check。
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
                    // W-AUDIT-6d #6 (AMD-2026-05-09-02 §3): pair MA confirmation。
                    // 反轉信號必經 MA 趨勢方向確認 — long entry → price < ma；
                    // short entry → price > ma；MA 不可得（warm-up 不足或字段 None）
                    // 一律 fail-closed 不入場（§二 原則 6 失敗默認收縮）。
                    // W-AUDIT-6d #6: MA pair confirmation gate (long: price<ma /
                    // short: price>ma; fail-closed when MA unavailable).
                    if !self.ma_pair_allows_entry(is_long, ctx.price, ind) {
                        return intents;
                    }

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
                    let maybe_intent = self.make_entry_intent_with_qty(
                        ctx,
                        is_long,
                        conf_with_score,
                        bb.lower,
                        bb.upper,
                        qty,
                        confluence_score,
                        persistence_elapsed_ms,
                    );
                    if let Some(intent) = maybe_intent {
                        intents.push(StrategyAction::Open(intent));
                        // P0 Option A-Lite — 不再 eager mutate self.positions，
                        // 由 paper_state.apply_fill 在 router accept + fill 後寫入。
                        self.cooldown.record_signal(ctx.symbol, ctx.timestamp_ms);
                    }
                }
            }
            Some(_is_long) => {
                // Exit path — paper_state 確認本策略持倉；進 mean-reversion exit zone。
                // 出場：%B 回到 [0.2, 0.8] = 教科書均值回歸目標。比精確 0.5 更寬以應對加密貨幣超調。
                // QC-H3：exit %B range + exit_conf_base configurable（預設 [0.2, 0.8] / 0.55）。
                if bb.percent_b >= self.exit_pctb_lower && bb.percent_b <= self.exit_pctb_upper {
                    let exit_conf = (self.exit_conf_base + hurst_boost).clamp(0.4, 0.8);
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.to_string(),
                        confidence: exit_conf,
                        reason: "bb_mean_revert".into(),
                    });
                    // P0 Option A-Lite — 不再 mutate self.positions；
                    // paper_state 端 close fill 後 ctx.position_state 自然變 None。
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
