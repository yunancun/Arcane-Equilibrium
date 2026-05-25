//! Sprint 2 Alpha Tournament Candidate #4 — liquidation_cascade_fade
//! microstructure mean-revert fade。
//!
//! MODULE_NOTE：
//!   模塊用途：5min liquidation cluster magnitude > threshold 後 fade against
//!     dominant side（counter-cascade mean-revert），per W1-A spec v1.1 +
//!     W2-A finalize §3 schema 修正。
//!   入場條件（5 條件 ALL true）：
//!     1. surface.liquidation_pulse.is_some() AND pulse_for(symbol).is_some()
//!     2. dominant_notional_5m > threshold_usd (per-symbol; BTC $500k / ETH $300k)
//!     3. event_count_5m >= min_events (default 3)
//!     4. dominant_side != LiquidationSide::Mixed
//!     5. h0_allowed && cooldown_expired (per symbol, 30min)
//!   入場方向（fade 邏輯 — spec §1.1）：
//!     - LongLiquidated → take long entry (price overshoot 下行 mean-revert)
//!     - ShortLiquidated → take short entry (price overshoot 上行 mean-revert)
//!     - Mixed → reject
//!   出場條件（OR 任一觸發）：
//!     1. time-stop: now_ms - entry_ms > max_hold_ms (default 60min)
//!     2. take_profit: pnl_pct >= take_profit_pct (default 1.5%)
//!     3. reverse_cascade: dominant_side flips + current_notional > entry × 1.5
//!     4. P1 per_strategy stop_loss override (2% tight SL)
//!   主要類函數：LiquidationCascadeFade、on_tick (三分支 + fail-closed)、
//!     should_enter (返 Option<bool> 方向)、should_exit、threshold_for、
//!     LiquidationCascadeFadeUpdateParams。
//!   依賴：super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown}、
//!     intent_processor::OrderIntent、tick_pipeline::TickContext、
//!     openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface, LiquidationPulse,
//!     LiquidationSide}。
//!   硬邊界：
//!     - 不變量（spec §5.1）：runtime 只走 in-memory `surface.liquidation_pulse`
//!       (Bybit allLiquidation WS panel)；不走 Bybit historical REST API
//!       (per ADR-0038 §Decision 1 M11 self-hosted PG only)。
//!     - 不變量（spec §1.5 + memory feedback_indicator_lookahead_bias）：
//!       不引入 `rolling(N).max()` selection bias pattern；entry signal 為
//!       直接閾值比較；5m window 為 panel aggregator 內部 trim，**非** entry rolling stat。
//!     - 不變量（spec §1.4）：self-fills filter Stage 1 stub returns false；
//!       Sprint 3+ V109 anomaly_events schema land 後 wire 真正 hard filter。
//!     - 不變量（spec §1.1 + §9 #6）：fade direction map (LongLiquidated → is_long=true)
//!       不可寫反；寫反 = alpha 反向 = trade loss。
//!     - 不變量（ADR-0036 Decision 1）：本 module 0 HMM / Markov-switching / GARCH 依賴。
//!     - Stage 1 限定 BTCUSDT / ETHUSDT；TOML validate 已擋；on_tick 再 fence。
//!     - active=false 預設；TOML 或 IPC active=true 才啟（fail-closed + 5-gate inherit）。
//!   spec ref:
//!     - srv/docs/execution_plan/2026-05-25--alpha_candidate_4_liquidation_cascade_fade_spec.md v1.1
//!     - srv/docs/CCAgentWorkSpace/PA/workspace/reports/2026-05-25--w2a_alpha_tournament_pre_spec_finalize.md

use std::collections::HashMap;

use serde::{Deserialize, Serialize};
use tracing::info;

use super::common::{compute_post_only_price, MakerPriceInputs, TrendCooldown};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{
    AlphaSourceTag, AlphaSurface, LiquidationPulse, LiquidationSide,
};

pub mod params;

#[cfg(test)]
mod tests;

pub use params::LiquidationCascadeFadeParams;
use params::{
    DEFAULT_BTC_THRESHOLD_USD, DEFAULT_COOLDOWN_MS, DEFAULT_ETH_THRESHOLD_USD, DEFAULT_MAX_HOLD_MS,
    DEFAULT_MIN_EVENTS, DEFAULT_REVERSE_CASCADE_RATIO, DEFAULT_TAKE_PROFIT_PCT,
    DEFAULT_THRESHOLD_USD,
};

// PostOnly maker 入場參數（與 funding_arb / funding_harvest / funding_short_v2 範式對齊）。
const LCF_MAKER_OFFSET_BPS: f64 = 1.0;
const LCF_MAKER_BUFFER_TICKS: u32 = 1;
const LCF_MAKER_TIMEOUT_MS: u64 = 45_000;

// ──────────────────────────────────────────────────────────────────────────
// LiquidationCascadeFade strategy struct
// ──────────────────────────────────────────────────────────────────────────

pub struct LiquidationCascadeFade {
    active: bool,
    /// per-symbol cooldown（同 funding_arb 範式；rollback 用 prev_last_trade_ms）。
    cooldown: TrendCooldown,
    pub cooldown_ms: u64,

    /// Stage 1 Demo 限定 BTCUSDT / ETHUSDT。
    pub allowed_symbols: Vec<String>,

    /// per-symbol threshold map (key: symbol, value: 5m notional USD)。
    /// Sprint 3+ 可走 V109 anomaly_events table walk-forward calibrated threshold。
    pub per_symbol_threshold: HashMap<String, f64>,

    pub default_threshold_usd: f64,
    pub min_events: u32,
    pub max_hold_ms: u64,
    pub take_profit_pct: f64,
    pub reverse_cascade_ratio: f64,

    /// sentinel qty → IntentProcessor 套用 Kelly/risk sizing。
    default_qty: f64,

    /// 入場時 cascade dominant notional 快照（用於 reverse cascade 1.5x ratio 判定）。
    pub(crate) entry_notional: HashMap<String, f64>,

    /// rejection rollback 用的 cooldown 快照（funding_arb 範式）。
    prev_last_trade_ms: HashMap<String, u64>,

    /// CONF-D：策略 confidence 縮放係數（預設 1.0）。
    conf_scale: f64,
}

impl Default for LiquidationCascadeFade {
    fn default() -> Self {
        Self::new()
    }
}

impl LiquidationCascadeFade {
    pub fn new() -> Self {
        let mut per_symbol = HashMap::new();
        per_symbol.insert("BTCUSDT".to_string(), DEFAULT_BTC_THRESHOLD_USD);
        per_symbol.insert("ETHUSDT".to_string(), DEFAULT_ETH_THRESHOLD_USD);
        Self {
            active: false,
            cooldown: TrendCooldown::new(DEFAULT_COOLDOWN_MS),
            cooldown_ms: DEFAULT_COOLDOWN_MS,
            allowed_symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
            per_symbol_threshold: per_symbol,
            default_threshold_usd: DEFAULT_THRESHOLD_USD,
            min_events: DEFAULT_MIN_EVENTS,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            take_profit_pct: DEFAULT_TAKE_PROFIT_PCT,
            reverse_cascade_ratio: DEFAULT_REVERSE_CASCADE_RATIO,
            default_qty: 1e9, // sentinel → IntentProcessor Kelly sizing
            entry_notional: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
        }
    }

    /// 取 per-symbol threshold；non-cohort fallback 預設 (Stage 1 cohort gate 在 on_tick
    /// 已擋，理論不應 trigger fallback)。
    pub(crate) fn threshold_for(&self, symbol: &str) -> f64 {
        self.per_symbol_threshold
            .get(symbol)
            .copied()
            .unwrap_or(self.default_threshold_usd)
    }

    /// Entry gate check (純函式)。返 None = reject；Some(true) = long entry；Some(false) = short。
    /// per spec §1.1 入場條件 2/3/4 + 入場方向決定（counter-fade 映射）。
    ///
    /// 不變量（spec §9 #6 對抗式 review focus）：fade direction 映射不可寫反。
    /// - LongLiquidated → entry_is_long = true (price overshoot 下行 → fade buy mean-revert)
    /// - ShortLiquidated → entry_is_long = false (price overshoot 上行 → fade sell mean-revert)
    /// - Mixed → None (無 directional thesis；reject)
    pub(crate) fn should_enter(&self, pulse: &LiquidationPulse, symbol: &str) -> Option<bool> {
        // Gate 2: dominant_notional > threshold (per-symbol)。
        let dominant_notional = pulse.long_notional_5m.max(pulse.short_notional_5m);
        if dominant_notional < self.threshold_for(symbol) {
            return None;
        }
        // Gate 3: event_count >= min_events (防 single-large-event 假訊號)。
        if pulse.event_count_5m < self.min_events {
            return None;
        }
        // Gate 4 + direction map: dominant_side fade。
        match pulse.dominant_side {
            LiquidationSide::LongLiquidated => Some(true), // fade buy
            LiquidationSide::ShortLiquidated => Some(false), // fade sell
            LiquidationSide::Mixed => None,                // reject
        }
    }

    /// Exit decision (純函式)。Some(reason) = exit 立即觸發；None = 持倉繼續。
    /// per spec §1.2 出場條件 1/2/3（SL 由 P1 per_strategy override 處理）。
    pub(crate) fn should_exit(
        &self,
        symbol: &str,
        pulse: &LiquidationPulse,
        is_long_position: bool,
        entry_price: f64,
        current_price: f64,
        now_ms: u64,
        entry_ms: u64,
    ) -> Option<&'static str> {
        // 1. time-stop。
        if now_ms.saturating_sub(entry_ms) > self.max_hold_ms {
            return Some("time_stop");
        }
        // 2. take profit (per_strategy override 由 P1 強制；strategy 內亦判 early exit signal)。
        // 不變量：entry_price > 0 (paper_state 已驗證；fail-closed if not)。
        if entry_price <= 0.0 {
            return None;
        }
        let pnl_pct = if is_long_position {
            ((current_price - entry_price) / entry_price) * 100.0
        } else {
            ((entry_price - current_price) / entry_price) * 100.0
        };
        if pnl_pct >= self.take_profit_pct {
            return Some("take_profit");
        }
        // 3. reverse cascade detected。
        // 入場時 dominant_side 期望：is_long=true 表示入場時 LongLiquidated（long 被強平 → 我們 fade buy）。
        let entry_n = self.entry_notional.get(symbol).copied().unwrap_or(0.0);
        let current_dominant = pulse.long_notional_5m.max(pulse.short_notional_5m);
        let expected_dominant_side = if is_long_position {
            LiquidationSide::LongLiquidated
        } else {
            LiquidationSide::ShortLiquidated
        };
        if pulse.dominant_side != expected_dominant_side
            && entry_n > 0.0
            && current_dominant > entry_n * self.reverse_cascade_ratio
        {
            return Some("reverse_cascade");
        }
        // 4. SL 由 P1 per_strategy stop_loss_max_pct_override 處理（strategy 內不重複判定）。
        None
    }

    /// Stage 1 cohort fence：必 BTCUSDT / ETHUSDT。其他 symbol fail-closed skip。
    fn is_allowed_symbol(&self, sym: &str) -> bool {
        self.allowed_symbols.iter().any(|s| s.as_str() == sym)
    }

    /// rejection rollback 用的 cooldown 快照。
    fn snapshot_prev_cooldown(&mut self, sym: &str) {
        self.prev_last_trade_ms
            .insert(sym.to_string(), self.cooldown.last_ms(sym).unwrap_or(0));
    }

    /// self-fills filter Stage 1 stub（per spec §1.4）。
    /// 為什麼 Stage 1 stub：
    /// - per BB C6 PROOF PASS：market.liquidations 31,473 rows 無 self-origin
    ///   (writer 訂閱 Bybit-wide stream，不含本 demo 倉位)
    /// - Stage 1 demo balance ($1000 typical) 強平閾值 90%+ margin loss 之前 P0
    ///   hardstop 已強平倉位 (reduceOnly close)；不會走 Bybit liquidation engine 路徑
    /// - defensive filter Sprint 3+ V109 schema land 後加 hard enforcement
    ///   (per AC-S2-A-C4-7 + spec §1.4)
    /// 不變量：本 stub 永遠 return false；W2-E E2 review focus 確認不誤判 true
    /// （誤判 true 會錯失所有合法 cascade entry）。
    #[allow(dead_code)]
    pub(crate) fn is_self_origin_event(_pulse: &LiquidationPulse) -> bool {
        // Stage 1 stub — Sprint 3+ V109 anomaly_events wire 真正 filter。
        false
    }

    /// IPC `update_strategy_params` 熱更新；同步 active + 全範圍。
    pub fn update_params(
        &mut self,
        params: LiquidationCascadeFadeUpdateParams,
    ) -> Result<(), String> {
        params.validate()?;
        self.active = params.active;
        self.cooldown_ms = params.cooldown_ms;
        self.cooldown.set_duration(params.cooldown_ms);
        self.allowed_symbols = params.allowed_symbols.clone();
        self.default_threshold_usd = params.default_threshold_usd;
        // per-symbol threshold map 從 IPC params 重建（BTC + ETH 兩 key）。
        let mut new_map = HashMap::new();
        new_map.insert("BTCUSDT".to_string(), params.btc_threshold_usd);
        new_map.insert("ETHUSDT".to_string(), params.eth_threshold_usd);
        self.per_symbol_threshold = new_map;
        self.min_events = params.min_events;
        self.max_hold_ms = params.max_hold_ms;
        self.take_profit_pct = params.take_profit_pct;
        self.reverse_cascade_ratio = params.reverse_cascade_ratio;
        info!(
            strategy = "liquidation_cascade_fade",
            active = self.active,
            btc_threshold = params.btc_threshold_usd,
            eth_threshold = params.eth_threshold_usd,
            "params updated via IPC"
        );
        Ok(())
    }

    /// 將當前 tunable 狀態快照成 IPC payload。
    pub fn get_params(&self) -> LiquidationCascadeFadeUpdateParams {
        let btc = self
            .per_symbol_threshold
            .get("BTCUSDT")
            .copied()
            .unwrap_or(DEFAULT_BTC_THRESHOLD_USD);
        let eth = self
            .per_symbol_threshold
            .get("ETHUSDT")
            .copied()
            .unwrap_or(DEFAULT_ETH_THRESHOLD_USD);
        LiquidationCascadeFadeUpdateParams {
            active: self.active,
            cooldown_ms: self.cooldown_ms,
            allowed_symbols: self.allowed_symbols.clone(),
            default_threshold_usd: self.default_threshold_usd,
            btc_threshold_usd: btc,
            eth_threshold_usd: eth,
            min_events: self.min_events,
            max_hold_ms: self.max_hold_ms,
            take_profit_pct: self.take_profit_pct,
            reverse_cascade_ratio: self.reverse_cascade_ratio,
        }
    }
}

// ──────────────────────────────────────────────────────────────────────────
// LiquidationCascadeFadeUpdateParams (IPC payload)
// ──────────────────────────────────────────────────────────────────────────

/// IPC `update_strategy_params` 的 liquidation_cascade_fade payload schema。
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct LiquidationCascadeFadeUpdateParams {
    pub active: bool,
    pub cooldown_ms: u64,
    pub allowed_symbols: Vec<String>,
    pub default_threshold_usd: f64,
    pub btc_threshold_usd: f64,
    pub eth_threshold_usd: f64,
    pub min_events: u32,
    pub max_hold_ms: u64,
    pub take_profit_pct: f64,
    pub reverse_cascade_ratio: f64,
}

impl Default for LiquidationCascadeFadeUpdateParams {
    fn default() -> Self {
        Self {
            active: false,
            cooldown_ms: DEFAULT_COOLDOWN_MS,
            allowed_symbols: vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()],
            default_threshold_usd: DEFAULT_THRESHOLD_USD,
            btc_threshold_usd: DEFAULT_BTC_THRESHOLD_USD,
            eth_threshold_usd: DEFAULT_ETH_THRESHOLD_USD,
            min_events: DEFAULT_MIN_EVENTS,
            max_hold_ms: DEFAULT_MAX_HOLD_MS,
            take_profit_pct: DEFAULT_TAKE_PROFIT_PCT,
            reverse_cascade_ratio: DEFAULT_REVERSE_CASCADE_RATIO,
        }
    }
}

impl StrategyParams for LiquidationCascadeFadeUpdateParams {
    fn param_ranges() -> Vec<ParamRange> {
        LiquidationCascadeFadeParams::param_ranges()
    }

    fn validate(&self) -> Result<(), String> {
        let mirror = LiquidationCascadeFadeParams {
            active: self.active,
            cooldown_ms: self.cooldown_ms,
            allowed_symbols: self.allowed_symbols.clone(),
            default_threshold_usd: self.default_threshold_usd,
            btc_threshold_usd: self.btc_threshold_usd,
            eth_threshold_usd: self.eth_threshold_usd,
            min_events: self.min_events,
            max_hold_ms: self.max_hold_ms,
            take_profit_pct: self.take_profit_pct,
            reverse_cascade_ratio: self.reverse_cascade_ratio,
        };
        mirror.validate()
    }
}

// ──────────────────────────────────────────────────────────────────────────
// Strategy trait impl
// ──────────────────────────────────────────────────────────────────────────

impl Strategy for LiquidationCascadeFade {
    fn name(&self) -> &str {
        "liquidation_cascade_fade"
    }

    fn is_active(&self) -> bool {
        self.active
    }

    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// W-AUDIT-8a Phase A：liquidation_cascade_fade 聲明消費 LiquidationCascade
    /// (Tier 3 microstructure)。
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::LiquidationCascade];
        TAGS
    }

    fn on_tick(
        &mut self,
        ctx: &TickContext<'_>,
        surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        if !self.active {
            return vec![];
        }

        let sym = ctx.symbol;
        let now_ms = ctx.timestamp_ms;

        // Stage 1 cohort fence。
        if !self.is_allowed_symbol(sym) {
            return vec![];
        }

        // fail-closed: panel + pulse must be available（spec §5.2 設計約束）。
        // surface.liquidation_pulse = None → 不入場、不平倉，等待 panel 恢復。
        let panel = match surface.liquidation_pulse {
            Some(p) => p,
            None => return vec![],
        };
        let pulse = match panel.pulse_for(sym) {
            Some(p) => p,
            None => return vec![],
        };

        let current_price = ctx.price;
        if !current_price.is_finite() || current_price <= 0.0 {
            return vec![];
        }

        // ── 三分支（Option A-Lite 範式）──
        let owned_position = ctx
            .position_state
            .filter(|p| p.owner_strategy == self.name());

        match owned_position {
            Some(pos) => {
                // Exit 分支
                if let Some(reason) = self.should_exit(
                    sym,
                    pulse,
                    pos.is_long,
                    pos.entry_price,
                    current_price,
                    now_ms,
                    pos.entry_ts_ms,
                ) {
                    self.snapshot_prev_cooldown(sym);
                    self.cooldown.record_signal(sym, now_ms);
                    // 平倉前清 entry_notional snapshot。
                    self.entry_notional.remove(sym);

                    let mut confidence = 0.8 * self.conf_scale;
                    confidence = confidence.clamp(0.0, 1.0);

                    return vec![StrategyAction::Close {
                        symbol: sym.to_string(),
                        confidence,
                        reason: format!("liquidation_cascade_fade_exit: {reason}"),
                    }];
                }
                vec![]
            }
            None if ctx.position_state.is_some() => {
                // cross-strategy 占用 → skip。
                tracing::debug!(
                    strategy = "liquidation_cascade_fade",
                    symbol = %sym,
                    cross_owner = %ctx
                        .position_state
                        .map(|p| p.owner_strategy.as_str())
                        .unwrap_or(""),
                    "skip entry: cross-strategy holds position"
                );
                vec![]
            }
            None => {
                // ── Entry 分支 ──
                if !ctx.h0_allowed {
                    return vec![];
                }
                if !self.cooldown.is_cooled_down(sym, now_ms) {
                    return vec![];
                }
                // self-fills filter Stage 1 stub（Sprint 3+ V109 wire 真實 enforcement）。
                if Self::is_self_origin_event(pulse) {
                    return vec![];
                }

                // 5 entry gate + direction map（counter-cascade fade）。
                let entry_is_long = match self.should_enter(pulse, sym) {
                    Some(b) => b,
                    None => return vec![],
                };

                // confidence scale with notional magnitude over threshold (cap 3x)。
                let dominant_notional = pulse.long_notional_5m.max(pulse.short_notional_5m);
                let threshold = self.threshold_for(sym);
                let magnitude_ratio = if threshold > 0.0 {
                    (dominant_notional / threshold).min(3.0)
                } else {
                    0.0
                };
                let raw_conf = (magnitude_ratio / 3.0 * 0.5 + 0.4).clamp(0.4, 0.9);
                let confidence = crate::tick_pipeline::on_tick_helpers::clamp_confidence(
                    raw_conf * self.conf_scale,
                );

                let maker_inputs = MakerPriceInputs {
                    last_price: current_price,
                    best_bid: ctx.best_bid,
                    best_ask: ctx.best_ask,
                    tick_size: ctx.tick_size,
                };
                let limit_price = match compute_post_only_price(
                    entry_is_long,
                    maker_inputs,
                    LCF_MAKER_OFFSET_BPS,
                    LCF_MAKER_BUFFER_TICKS,
                    self.name(),
                    sym,
                ) {
                    Some(price) => price,
                    None => return vec![],
                };

                self.snapshot_prev_cooldown(sym);
                self.cooldown.record_signal(sym, now_ms);
                // 記錄 entry_notional 供 reverse cascade 判定使用。
                self.entry_notional
                    .insert(sym.to_string(), dominant_notional);

                info!(
                    strategy = "liquidation_cascade_fade",
                    symbol = sym,
                    entry_is_long,
                    dominant_notional,
                    event_count_5m = pulse.event_count_5m,
                    dominant_side = ?pulse.dominant_side,
                    limit_price,
                    "fade entry intent emitted (counter-cascade mean-revert)"
                );

                vec![StrategyAction::Open(OrderIntent::new_trade(
                    sym.to_string(),
                    entry_is_long,
                    self.default_qty,
                    confidence,
                    self.name().to_string(),
                    "limit".to_string(),
                    Some(limit_price),
                    None,
                    None,
                    Some(TimeInForce::PostOnly),
                    Some(LCF_MAKER_TIMEOUT_MS),
                ))]
            }
        }
    }

    /// rejection rollback：清 entry_notional + 還原 cooldown。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        if intent.strategy != self.name() {
            return;
        }
        let sym = &intent.symbol;
        self.entry_notional.remove(sym);
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 {
                self.cooldown.clear(sym);
            } else {
                self.cooldown.record_signal(sym, ts);
            }
        }
    }

    /// 風控強平 → 同步清 entry_notional snapshot。
    fn on_external_close(&mut self, symbol: &str, _close_price: f64, _close_ts_ms: u64) {
        self.entry_notional.remove(symbol);
    }

    /// strategy 自發 Close 確認 → 同步清 entry_notional snapshot。
    fn on_close_confirmed(&mut self, symbol: &str, _close_price: f64, _close_ts_ms: u64) {
        self.entry_notional.remove(symbol);
    }

    /// strategy Close 被跳過（paper_state 找不到倉位）→ 清 entry_notional snapshot。
    fn on_close_skipped(&mut self, symbol: &str) {
        self.entry_notional.remove(symbol);
    }

    // ── Phase 3a runtime tuning IPC ──

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let params: LiquidationCascadeFadeUpdateParams =
            serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(params)
    }

    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }

    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&LiquidationCascadeFadeUpdateParams::param_ranges()).unwrap_or_default()
    }

    fn conf_scale(&self) -> f64 {
        self.conf_scale
    }

    fn set_conf_scale(&mut self, scale: f64) {
        self.conf_scale = scale.clamp(0.0, 2.0);
    }
}
