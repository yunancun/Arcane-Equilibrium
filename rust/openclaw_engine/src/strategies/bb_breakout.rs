//! BB Breakout Strategy V2 — Squeeze→Expansion + Volume + Donchian + ATR trailing stop + Regime exit.
//! BB 突破策略 V2 — 壓縮→擴張 + 成交量 + Donchian + ATR 追蹤止損 + Regime 出場。
//!
//! MODULE_NOTE (EN): Detects Bollinger Band squeeze→expansion with volume
//!   confirmation and Donchian channel breakout. ATR-based trailing stop for exits.
//! MODULE_NOTE (中): 檢測布林帶壓縮→擴張 + 成交量確認 + Donchian 通道突破。
//!   ATR 追蹤止損出場。

use std::collections::HashMap;

use super::confluence::{self, ConfluenceConfig, PersistenceTracker};
use super::{ParamRange, Strategy, StrategyAction, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use serde::{Deserialize, Serialize};
use tracing::info;

/// Tunable parameters for BB Breakout (Phase 3a).
#[derive(Debug, Clone, Serialize, Deserialize)]
#[serde(default)]
pub struct BbBreakoutParams {
    pub cooldown_ms: u64,
    pub default_qty: f64,
    pub squeeze_bw: f64,
    pub expansion_bw: f64,
    pub volume_threshold: f64,
    pub trailing_stop_atr_mult: f64,
    /// FIX-26: Squeeze state expiry duration (ms). Default 30 min.
    /// FIX-26：壓縮狀態有效期（ms）。默認 30 分鐘。
    pub squeeze_expiry_ms: u64,
    // ── G-SR-1 confluence + persistence fields (A0-c) ──
    /// Minimum signal persistence before entry (ms). / 入場前信號最小持續時間（ms）。
    pub min_persistence_ms: u64,
    /// Minimum order notional (USD). / 最小訂單名義值（USD）。
    pub min_notional_usd: f64,
    /// Confluence as qty modifier only (not gate). / 匯流僅作為 qty 調整器（非門控）。
    pub confluence_as_gate: bool,
    /// Confluence weights + thresholds (breakout profile).
    pub weight_adx: f64,
    pub weight_regime: f64,
    pub weight_volume: f64,
    pub weight_momentum: f64,
    pub adx_floor: f64,
    pub confluence_threshold_no_trade: f64,
    pub confluence_threshold_light: f64,
    pub confluence_threshold_full: f64,
}

impl Default for BbBreakoutParams {
    fn default() -> Self {
        let cc = ConfluenceConfig::breakout();
        Self {
            cooldown_ms: 300_000,
            default_qty: 1e9,
            squeeze_bw: DEFAULT_SQUEEZE_BW,
            expansion_bw: DEFAULT_EXPANSION_BW,
            volume_threshold: DEFAULT_VOLUME_THRESHOLD,
            trailing_stop_atr_mult: 2.0,
            squeeze_expiry_ms: 1_800_000,
            min_persistence_ms: 60_000, // 1 min (triple gate already strict)
            min_notional_usd: 10.0,
            confluence_as_gate: false,
            weight_adx: cc.weight_adx,
            weight_regime: cc.weight_regime,
            weight_volume: cc.weight_volume,
            weight_momentum: cc.weight_momentum,
            adx_floor: cc.adx_floor,
            confluence_threshold_no_trade: cc.threshold_no_trade,
            confluence_threshold_light: cc.threshold_light,
            confluence_threshold_full: cc.threshold_full,
        }
    }
}

impl StrategyParams for BbBreakoutParams {
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
                name: "squeeze_bw".into(),
                min: 0.005,
                max: 0.05,
                step: None,
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "expansion_bw".into(),
                min: 0.02,
                max: 0.1,
                step: None,
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "volume_threshold".into(),
                min: 1.0,
                max: 5.0,
                step: Some(0.1),
                agent_adjustable: true,
                db_persisted: true,
            },
            ParamRange {
                name: "trailing_stop_atr_mult".into(),
                min: 1.0,
                max: 5.0,
                step: Some(0.5),
                agent_adjustable: true,
                db_persisted: true,
            },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.squeeze_bw >= self.expansion_bw {
            return Err("squeeze_bw must be < expansion_bw".into());
        }
        if self.volume_threshold < 1.0 {
            return Err("volume_threshold must be >= 1.0".into());
        }
        if self.trailing_stop_atr_mult < 0.5 {
            return Err("trailing_stop_atr_mult must be >= 0.5".into());
        }
        self.build_confluence_config().validate()?;
        if self.min_notional_usd < 1.0 {
            return Err("min_notional_usd must be >= 1.0".into());
        }
        Ok(())
    }
}

impl BbBreakoutParams {
    /// Build ConfluenceConfig (breakout profile: qty modifier only, non-inverted ADX).
    /// 構建 ConfluenceConfig（突破配置：僅 qty 調整器，非反轉 ADX）。
    pub fn build_confluence_config(&self) -> ConfluenceConfig {
        ConfluenceConfig {
            weight_adx: self.weight_adx,
            weight_regime: self.weight_regime,
            weight_volume: self.weight_volume,
            weight_momentum: self.weight_momentum,
            adx_floor: self.adx_floor,
            invert_adx: false,
            threshold_no_trade: self.confluence_threshold_no_trade,
            threshold_light: self.confluence_threshold_light,
            threshold_full: self.confluence_threshold_full,
            confluence_as_gate: self.confluence_as_gate,
        }
    }
}

/// Default bandwidth threshold to detect squeeze (壓縮帶寬閾值默認)
const DEFAULT_SQUEEZE_BW: f64 = 0.02;
/// Default bandwidth threshold to detect expansion (擴張帶寬閾值默認)
const DEFAULT_EXPANSION_BW: f64 = 0.04;
/// Default volume ratio threshold for breakout confirmation (成交量確認閾值默認)
const DEFAULT_VOLUME_THRESHOLD: f64 = 1.5;

pub struct BbBreakout {
    active: bool,
    /// Per-symbol position tracking: symbol → is_long direction.
    /// 每幣種獨立持倉追蹤：symbol → 多空方向。
    positions: HashMap<String, bool>,
    /// Per-symbol squeeze state tracking: symbol → timestamp (ms) when squeeze was first detected.
    /// FIX-26: Now stores detection time so squeeze expires after `squeeze_expiry_ms`.
    /// 每幣種壓縮狀態追蹤：symbol → 首次偵測壓縮的時間戳（ms）。
    squeeze_detected_ms: HashMap<String, u64>,
    /// FIX-26: Max duration (ms) a squeeze remains valid. Default 30 min.
    /// FIX-26：壓縮狀態最長有效期（ms）。默認 30 分鐘。
    pub squeeze_expiry_ms: u64,
    /// Per-symbol last trade timestamp for cooldown.
    /// 每幣種最後交易時間戳（用於冷卻）。
    last_trade_ms: HashMap<String, u64>,
    pub(crate) cooldown_ms: u64,
    default_qty: f64,
    // V2: Per-symbol ATR trailing stop fields / 每幣種 ATR 追蹤止損欄位
    entry_price: HashMap<String, f64>,
    trailing_stop: HashMap<String, f64>,
    /// ATR multiplier for trailing stop distance. Agent-adjustable (Phase 3a).
    /// ATR 追蹤止損距離乘數。Agent 可調（Phase 3a）。
    pub trailing_stop_atr_mult: f64,
    // RC-03: Configurable thresholds for Agent adjustability
    // RC-03：可配置閾值，供 Agent 動態調整
    /// Bandwidth below this = squeeze detected / 帶寬低於此值 = 偵測到壓縮
    pub squeeze_bw: f64,
    /// QC-H4: Entry confidence base (default 0.7). / 入場信心基礎值。
    pub(crate) entry_conf_base: f64,
    /// QC-H4: Exit confidence base (default 0.5). Exit reasons add offsets.
    /// QC-H4：出場信心基礎值。各出場原因加減偏移。
    pub(crate) exit_conf_base: f64,
    /// Bandwidth above this = expansion confirmed / 帶寬高於此值 = 確認擴張
    pub expansion_bw: f64,
    /// Minimum volume ratio for breakout entry / 突破入場最低成交量倍率
    pub volume_threshold: f64,
    // RC-04: Per-symbol previous state for rejection rollback / 每幣種拒絕回滾用的先前狀態
    prev_position: HashMap<String, Option<bool>>,
    prev_squeeze_detected_ms: HashMap<String, Option<u64>>,
    prev_entry_price: HashMap<String, Option<f64>>,
    prev_trailing_stop: HashMap<String, Option<f64>>,
    prev_last_trade_ms: HashMap<String, u64>,
    /// CONF-D: Multiplier applied to emitted intent.confidence (default 1.0, range [0,2]).
    conf_scale: f64,
    // ── G-SR-1: Confluence scoring + persistence filter (A0-c, A1) ──
    pub confluence_config: ConfluenceConfig,
    persistence: PersistenceTracker,
    pub min_persistence_ms: u64,
    pub min_notional_usd: f64,
}

impl BbBreakout {
    pub fn new() -> Self {
        Self {
            active: true,
            positions: HashMap::new(),
            squeeze_detected_ms: HashMap::new(),
            squeeze_expiry_ms: 1_800_000, // 30 minutes
            last_trade_ms: HashMap::new(),
            cooldown_ms: 600_000,
            default_qty: 1e9,
            entry_price: HashMap::new(),
            trailing_stop: HashMap::new(),
            trailing_stop_atr_mult: 2.0,
            squeeze_bw: DEFAULT_SQUEEZE_BW,
            expansion_bw: DEFAULT_EXPANSION_BW,
            volume_threshold: DEFAULT_VOLUME_THRESHOLD,
            entry_conf_base: 0.7,
            exit_conf_base: 0.5,
            prev_position: HashMap::new(),
            prev_squeeze_detected_ms: HashMap::new(),
            prev_entry_price: HashMap::new(),
            prev_trailing_stop: HashMap::new(),
            prev_last_trade_ms: HashMap::new(),
            conf_scale: 1.0,
            confluence_config: ConfluenceConfig::breakout(),
            persistence: PersistenceTracker::new(),
            min_persistence_ms: 60_000, // 1 min (triple gate already strict)
            min_notional_usd: 10.0,
        }
    }

    pub fn update_params(&mut self, params: BbBreakoutParams) -> Result<(), String> {
        params.validate()?;
        self.cooldown_ms = params.cooldown_ms;
        self.default_qty = params.default_qty;
        self.squeeze_bw = params.squeeze_bw;
        self.expansion_bw = params.expansion_bw;
        self.volume_threshold = params.volume_threshold;
        self.trailing_stop_atr_mult = params.trailing_stop_atr_mult;
        self.squeeze_expiry_ms = params.squeeze_expiry_ms;
        self.confluence_config = params.build_confluence_config();
        self.min_persistence_ms = params.min_persistence_ms;
        self.min_notional_usd = params.min_notional_usd;
        info!(strategy = "bb_breakout", "params updated / 參數已更新");
        Ok(())
    }

    pub fn get_params(&self) -> BbBreakoutParams {
        BbBreakoutParams {
            cooldown_ms: self.cooldown_ms,
            default_qty: self.default_qty,
            squeeze_bw: self.squeeze_bw,
            expansion_bw: self.expansion_bw,
            volume_threshold: self.volume_threshold,
            trailing_stop_atr_mult: self.trailing_stop_atr_mult,
            squeeze_expiry_ms: self.squeeze_expiry_ms,
            min_persistence_ms: self.min_persistence_ms,
            min_notional_usd: self.min_notional_usd,
            confluence_as_gate: self.confluence_config.confluence_as_gate,
            weight_adx: self.confluence_config.weight_adx,
            weight_regime: self.confluence_config.weight_regime,
            weight_volume: self.confluence_config.weight_volume,
            weight_momentum: self.confluence_config.weight_momentum,
            adx_floor: self.confluence_config.adx_floor,
            confluence_threshold_no_trade: self.confluence_config.threshold_no_trade,
            confluence_threshold_light: self.confluence_config.threshold_light,
            confluence_threshold_full: self.confluence_config.threshold_full,
        }
    }
}

impl Strategy for BbBreakout {
    fn name(&self) -> &str {
        "bb_breakout"
    }
    fn is_active(&self) -> bool {
        self.active
    }
    fn set_active(&mut self, active: bool) {
        self.active = active;
    }

    /// Reset per-symbol position state on external close (risk-stop).
    /// 外部平倉（風控止損）時重設該幣種的內部狀態。
    fn on_external_close(&mut self, symbol: &str) {
        self.positions.remove(symbol);
        self.entry_price.remove(symbol);
        self.trailing_stop.remove(symbol);
        self.persistence.clear(symbol);
    }

    /// RC-04: Revert per-symbol position, entry_price, trailing_stop, squeeze_detected_ms on rejection.
    /// RC-04：拒絕時回滾該幣種的 position、entry_price、trailing_stop、squeeze_detected_ms。
    fn on_rejection(&mut self, intent: &OrderIntent, _reason: &str) {
        let sym = &intent.symbol;
        if let Some(prev) = self.prev_position.get(sym) {
            match prev {
                Some(b) => { self.positions.insert(sym.to_string(), *b); }
                None => { self.positions.remove(sym); }
            }
        }
        if let Some(prev) = self.prev_squeeze_detected_ms.get(sym) {
            match prev {
                Some(ts) => { self.squeeze_detected_ms.insert(sym.to_string(), *ts); }
                None => { self.squeeze_detected_ms.remove(sym); }
            }
        }
        if let Some(prev) = self.prev_entry_price.get(sym) {
            match prev {
                Some(p) => { self.entry_price.insert(sym.to_string(), *p); }
                None => { self.entry_price.remove(sym); }
            }
        }
        if let Some(prev) = self.prev_trailing_stop.get(sym) {
            match prev {
                Some(s) => { self.trailing_stop.insert(sym.to_string(), *s); }
                None => { self.trailing_stop.remove(sym); }
            }
        }
        if let Some(&ts) = self.prev_last_trade_ms.get(sym) {
            if ts == 0 { self.last_trade_ms.remove(sym); } else { self.last_trade_ms.insert(sym.to_string(), ts); }
        }
    }

    fn on_tick(&mut self, ctx: &TickContext<'_>) -> Vec<StrategyAction> {
        let ind = match ctx.indicators {
            Some(i) => i,
            None => return vec![],
        };
        let bb = match &ind.bollinger {
            Some(b) => b,
            None => return vec![],
        };
        let vol_ratio = ind.volume_ratio.unwrap_or(1.0);

        // RC-04: Snapshot per-symbol state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照該幣種狀態，供拒絕回滾使用。
        let sym = ctx.symbol;
        self.prev_position.insert(sym.to_string(), self.positions.get(sym).copied());
        self.prev_squeeze_detected_ms.insert(sym.to_string(), self.squeeze_detected_ms.get(sym).copied());
        self.prev_entry_price.insert(sym.to_string(), self.entry_price.get(sym).copied());
        self.prev_trailing_stop.insert(sym.to_string(), self.trailing_stop.get(sym).copied());
        let last_ms = self.last_trade_ms.get(sym).copied().unwrap_or(0);
        self.prev_last_trade_ms.insert(sym.to_string(), last_ms);

        if bb.bandwidth < self.squeeze_bw {
            // FIX-26: Only record first detection time; don't reset on continued squeeze.
            self.squeeze_detected_ms.entry(sym.to_string()).or_insert(ctx.timestamp_ms);
        }
        if last_ms > 0 && ctx.timestamp_ms < last_ms + self.cooldown_ms {
            return vec![];
        }

        let mut intents = Vec::new();
        match self.positions.get(sym).copied() {
            None => {
                // FIX-26: Check squeeze exists AND hasn't expired.
                let in_squeeze = self.squeeze_detected_ms.get(sym)
                    .map(|&ts| ctx.timestamp_ms < ts + self.squeeze_expiry_ms)
                    .unwrap_or(false);
                if in_squeeze
                    && bb.bandwidth > self.expansion_bw
                    && vol_ratio >= self.volume_threshold
                {
                    let is_long = bb.percent_b > 1.0;
                    let is_short = bb.percent_b < 0.0;

                    // A3: Donchian confirmation — price must also breach Donchian channel
                    // A3：Donchian 确认 — 价格需同时突破 Donchian 通道
                    if let Some(dc) = &ind.donchian {
                        if is_long && ctx.price < dc.upper {
                            return vec![];
                        }
                        if is_short && ctx.price > dc.lower {
                            return vec![];
                        }
                    }

                    if is_long || is_short {
                        // A1: Persistence filter — triple gate signal must hold.
                        // A1：持續性過濾 — 三重門控信號必須持續。
                        let signal = Some(is_long);
                        if !self.persistence.check(
                            sym,
                            signal,
                            ctx.timestamp_ms,
                            self.min_persistence_ms,
                            false,
                        ) {
                            return intents;
                        }

                        // A4: Hurst regime boost — trending regime boosts breakout confidence
                        // A4：Hurst 趋势状态 — 趋势型市场提升突破信心
                        let hurst_boost: f64 = match &ind.hurst {
                            Some(h) if h.regime == "trending" => 0.1,
                            _ => 0.0,
                        };

                        // A2: Confluence scoring — qty modifier only for breakout.
                        // A2：匯流評分 — 突破策略僅作為 qty 調整器。
                        let score = confluence::compute_score(
                            &self.confluence_config,
                            true,
                            ind.adx.as_ref().map(|a| a.adx),
                            ind.hurst.as_ref().map(|h| h.regime.as_str()).unwrap_or("uncertain"),
                            ind.volume_ratio,
                            ind.rsi_14,
                            is_long,
                        );
                        let qty_pct = confluence::score_to_qty_pct(score, &self.confluence_config);
                        // confluence_as_gate=false: always trade if triple gate passed,
                        // but scale qty. qty_pct=0 only blocks if confluence_as_gate=true.
                        let effective_pct = if self.confluence_config.confluence_as_gate {
                            qty_pct
                        } else {
                            qty_pct.max(0.10) // minimum 10% qty for breakout
                        };
                        let qty = self.default_qty * effective_pct;
                        if qty * ctx.price < self.min_notional_usd {
                            return intents;
                        }

                        let raw_conf = (self.entry_conf_base + hurst_boost).min(1.0);
                        intents.push(StrategyAction::Open(OrderIntent {
                            symbol: ctx.symbol.to_string(),
                            is_long,
                            qty,
                            confidence: crate::tick_pipeline::on_tick_helpers::clamp_confidence(raw_conf * self.conf_scale),
                            strategy: self.name().into(),
                            order_type: "market".into(),
                            limit_price: None,
                        }));
                        self.positions.insert(sym.to_string(), is_long);
                        self.squeeze_detected_ms.remove(sym);
                        self.last_trade_ms.insert(sym.to_string(), ctx.timestamp_ms);
                        // V2: Record entry price and initialize trailing stop per-symbol
                        self.entry_price.insert(sym.to_string(), ctx.price);
                        if let Some(atr_res) = &ind.atr_14 {
                            let dist = atr_res.atr * self.trailing_stop_atr_mult;
                            let stop = if is_long { ctx.price - dist } else { ctx.price + dist };
                            self.trailing_stop.insert(sym.to_string(), stop);
                        }
                    }
                }
            }
            Some(is_long) => {
                let mut exit_reason: Option<&str> = None;
                // QC-H4: exit_conf_base configurable (was hardcoded 0.5)
                let mut exit_confidence = self.exit_conf_base;

                // V2: ATR trailing stop — Chandelier exit, 2×ATR from peak.
                // V2：ATR 追蹤止損 — Chandelier 出場，峰值 2×ATR。
                if let Some(atr_res) = &ind.atr_14 {
                    let stop_distance = atr_res.atr * self.trailing_stop_atr_mult;
                    let cur_stop = self.trailing_stop.get(sym).copied();
                    if is_long {
                        let new_stop = ctx.price - stop_distance;
                        if cur_stop.is_none() || new_stop > cur_stop.unwrap() {
                            self.trailing_stop.insert(sym.to_string(), new_stop);
                        }
                        if ctx.price <= self.trailing_stop.get(sym).copied().unwrap_or(0.0) {
                            exit_reason = Some("trailing_stop");
                            exit_confidence = self.exit_conf_base + 0.2;
                        }
                    } else {
                        let new_stop = ctx.price + stop_distance;
                        if cur_stop.is_none() || new_stop < cur_stop.unwrap() {
                            self.trailing_stop.insert(sym.to_string(), new_stop);
                        }
                        if ctx.price >= self.trailing_stop.get(sym).copied().unwrap_or(f64::MAX) {
                            exit_reason = Some("trailing_stop");
                            exit_confidence = self.exit_conf_base + 0.2;
                        }
                    }
                }

                // V2: Regime exit — Hurst drops from trending to mean_reverting/random_walk.
                // V2：Regime 出場 — Hurst 從趨勢轉為均值回歸/隨機漫步。
                if exit_reason.is_none() {
                    if let Some(h) = &ind.hurst {
                        if h.regime == "mean_reverting" || h.regime == "random_walk" {
                            exit_reason = Some("regime_shift");
                            exit_confidence = self.exit_conf_base + 0.1;
                        }
                    }
                }

                // %B revert to mid: failed breakout — price returned to BB middle.
                // %B 回中軌：突破失敗 — 價格回到 BB 中間。
                if exit_reason.is_none() {
                    if bb.percent_b >= 0.2 && bb.percent_b <= 0.8 {
                        exit_reason = Some("pctb_revert");
                        exit_confidence = self.exit_conf_base + 0.05;
                    } else if bb.bandwidth < self.squeeze_bw {
                        // BW squeeze: volatility collapsed / 帶寬壓縮：波動塌陷
                        exit_reason = Some("bw_squeeze");
                        exit_confidence = self.exit_conf_base - 0.05;
                    }
                }

                if let Some(reason) = exit_reason {
                    intents.push(StrategyAction::Close {
                        symbol: ctx.symbol.to_string(),
                        confidence: crate::tick_pipeline::on_tick_helpers::clamp_confidence(exit_confidence * self.conf_scale),
                        reason: reason.into(),
                    });
                    self.positions.remove(sym);
                    self.last_trade_ms.insert(sym.to_string(), ctx.timestamp_ms);
                    // V2: Reset per-symbol trailing stop state on exit / 出場時重置該幣種追蹤止損狀態
                    self.entry_price.remove(sym);
                    self.trailing_stop.remove(sym);
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let p: BbBreakoutParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(p)
    }
    fn get_params_json(&self) -> String {
        serde_json::to_string(&self.get_params()).unwrap_or_default()
    }
    fn param_ranges_json(&self) -> String {
        serde_json::to_string(&BbBreakoutParams::param_ranges()).unwrap_or_default()
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
    use openclaw_core::indicators::{AtrResult, BollingerResult, HurstResult, IndicatorSnapshot};

    // P-08: Test helpers use Box::leak for owned indicator data (fine for tests).
    fn ctx(bw: f64, pct_b: f64, vol: f64, ts: u64) -> TickContext<'static> {
        ctx_ext(bw, pct_b, vol, ts, 50000.0, None, None)
    }

    /// Extended context builder with price, ATR, and Hurst overrides.
    /// 擴展上下文建構器，支持自訂價格、ATR、Hurst。
    fn ctx_ext(
        bw: f64,
        pct_b: f64,
        vol: f64,
        ts: u64,
        price: f64,
        atr: Option<AtrResult>,
        hurst: Option<HurstResult>,
    ) -> TickContext<'static> {
        let ind = Box::leak(Box::new(IndicatorSnapshot {
            bollinger: Some(BollingerResult {
                upper: 51000.0,
                middle: 50000.0,
                lower: 49000.0,
                bandwidth: bw,
                percent_b: pct_b,
            }),
            volume_ratio: Some(vol),
            atr_14: atr,
            hurst,
            ..Default::default()
        }));
        TickContext {
            symbol: "BTC",
            price,
            timestamp_ms: ts,
            indicators: Some(ind),
            signals: &[],
            h0_allowed: true,
        }
    }

    #[test]
    fn test_squeeze_then_breakout() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_no_breakout_without_squeeze() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        assert!(s.on_tick(&ctx(0.05, 1.1, 2.0, 0)).is_empty());
    }

    #[test]
    fn test_entry_price_recorded() {
        // After entry, entry_price should be set / 入場後 entry_price 應被設置
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.entry_price.get("BTC"), Some(&50000.0));
        assert!(s.trailing_stop.get("BTC").is_none()); // no ATR data, no trailing stop yet
    }

    #[test]
    fn test_atr_trailing_stop_long_exit() {
        // Long position: price drops below trailing stop -> exit
        // 做多倉位：價格跌破追蹤止損 -> 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        let atr = || {
            Some(AtrResult {
                atr: 500.0,
                atr_percent: 0.01,
            })
        };

        // Enter long
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout
        assert_eq!(s.positions.get("BTC"), Some(&true));
        // trailing_stop = 50000 - 500*2 = 49000
        assert_eq!(s.trailing_stop.get("BTC"), Some(&49000.0));

        // Price rises -> trailing stop ratchets up, no exit
        // 價格上漲 -> 追蹤止損上移，不出場
        let i = s.on_tick(&ctx_ext(0.05, 1.2, 2.0, 1_400_000, 52000.0, atr(), None));
        assert!(i.is_empty()); // still in trend
        assert_eq!(s.trailing_stop.get("BTC"), Some(&51000.0)); // 52000 - 1000

        // Price drops to trailing stop -> exit
        // 價格跌至追蹤止損 -> 出場
        let i = s.on_tick(&ctx_ext(0.05, 0.9, 2.0, 2_100_000, 51000.0, atr(), None));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, confidence, .. } => {
                assert_eq!(reason, "trailing_stop");
                assert!((*confidence - 0.7).abs() < 1e-9);
            }
            other => panic!("expected Close, got {:?}", other),
        }
        assert!(s.positions.get("BTC").is_none());
        assert!(s.entry_price.get("BTC").is_none());
        assert!(s.trailing_stop.get("BTC").is_none());
    }

    #[test]
    fn test_atr_trailing_stop_short_exit() {
        // Short position: price rises above trailing stop -> exit
        // 做空倉位：價格漲破追蹤止損 -> 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        let atr = || {
            Some(AtrResult {
                atr: 500.0,
                atr_percent: 0.01,
            })
        };

        // Enter short
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx_ext(0.05, -0.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout short
        assert_eq!(s.positions.get("BTC"), Some(&false));
        // trailing_stop = 50000 + 500*2 = 51000
        assert_eq!(s.trailing_stop.get("BTC"), Some(&51000.0));

        // Price drops -> trailing stop ratchets down
        let i = s.on_tick(&ctx_ext(0.05, -0.2, 2.0, 1_400_000, 48000.0, atr(), None));
        assert!(i.is_empty());
        assert_eq!(s.trailing_stop.get("BTC"), Some(&49000.0)); // 48000 + 1000

        // Price rises to trailing stop -> exit
        let i = s.on_tick(&ctx_ext(0.05, 0.1, 2.0, 2_100_000, 49000.0, atr(), None));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, .. } => assert_eq!(reason, "trailing_stop"),
            other => panic!("expected Close, got {:?}", other),
        }
    }

    #[test]
    fn test_regime_exit() {
        // Exit when regime changes to mean_reverting / 當 regime 變為均值回歸時出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        let trending = || {
            Some(HurstResult {
                hurst: 0.7,
                regime: "trending".into(),
            })
        };
        let ranging = || {
            Some(HurstResult {
                hurst: 0.4,
                regime: "mean_reverting".into(),
            })
        };

        // Enter long (with trending regime boost)
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => {
                assert!((intent.confidence - 0.8).abs() < 1e-9); // 0.7 + 0.1 hurst boost
            }
            other => panic!("expected Open, got {:?}", other),
        }
        assert_eq!(s.positions.get("BTC"), Some(&true));

        // Regime shifts to mean_reverting -> exit
        let i = s.on_tick(&ctx_ext(
            0.05,
            1.1,
            2.0,
            1_400_000,
            51000.0,
            None,
            ranging(),
        ));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, confidence, .. } => {
                assert_eq!(reason, "regime_shift");
                assert!((*confidence - 0.6).abs() < 1e-9);
            }
            other => panic!("expected Close, got {:?}", other),
        }
        assert!(s.positions.get("BTC").is_none());
    }

    #[test]
    fn test_configurable_volume_threshold() {
        // RC-03: Custom volume threshold — higher threshold blocks low-volume breakouts
        // RC-03：自訂成交量閾值 — 較高閾值阻擋低量突破
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        s.volume_threshold = 3.0; // require 3x volume instead of default 1.5x
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
                                            // vol=2.0 passes default (1.5) but fails custom (3.0)
                                            // vol=2.0 通過默認閾值(1.5)但不通過自訂閾值(3.0)
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert!(i.is_empty(), "volume 2.0 should not pass threshold 3.0");

        // vol=3.5 passes custom threshold / vol=3.5 通過自訂閾值
        let i = s.on_tick(&ctx(0.05, 1.1, 3.5, 700_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Open(intent) => assert!(intent.is_long),
            other => panic!("expected Open, got {:?}", other),
        }
    }

    #[test]
    fn test_configurable_squeeze_expansion_bw() {
        // RC-03: Custom squeeze/expansion bandwidth thresholds
        // RC-03：自訂壓縮/擴張帶寬閾值
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        s.squeeze_bw = 0.03; // wider squeeze detection / 更寬的壓縮偵測
        s.expansion_bw = 0.06; // require stronger expansion / 要求更強擴張

        // bw=0.025 triggers squeeze with custom threshold (< 0.03)
        s.on_tick(&ctx(0.025, 0.5, 1.0, 0));
        assert!(s.squeeze_detected_ms.contains_key("BTC"));

        // bw=0.05 is expansion for default (> 0.04) but NOT for custom (< 0.06)
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert!(i.is_empty(), "bw 0.05 should not pass expansion_bw 0.06");

        // bw=0.07 passes custom expansion threshold / 通過自訂擴張閾值
        let i = s.on_tick(&ctx(0.07, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
    }

    #[test]
    fn test_bb_brk_param_ranges() {
        assert!(!BbBreakoutParams::param_ranges().is_empty());
    }
    #[test]
    fn test_bb_brk_validate() {
        assert!(BbBreakoutParams::default().validate().is_ok());
        assert!(BbBreakoutParams {
            squeeze_bw: 0.05,
            expansion_bw: 0.04,
            ..Default::default()
        }
        .validate()
        .is_err());
    }
    #[test]
    fn test_bb_brk_update() {
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        assert!(s
            .update_params(BbBreakoutParams {
                trailing_stop_atr_mult: 3.0,
                ..Default::default()
            })
            .is_ok());
        assert!((s.get_params().trailing_stop_atr_mult - 3.0).abs() < 0.01);
    }

    #[test]
    fn test_pctb_revert_exit() {
        // Failed breakout: %B returns to mid-band [0.2, 0.8] → exit with pctb_revert
        // 突破失敗：%B 回到中間帶 [0.2, 0.8] → 以 pctb_revert 出場
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        // Enter long (no ATR, no Hurst — only pctb/bw exits active)
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.positions.get("BTC"), Some(&true));

        // %B reverts to 0.5 (mid-band) → should trigger pctb_revert exit
        let i = s.on_tick(&ctx(0.05, 0.5, 2.0, 1_400_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, confidence, .. } => {
                assert_eq!(reason, "pctb_revert");
                // 0.55 * conf_scale(1.0) = 0.55
                assert!((*confidence - 0.55).abs() < 1e-9);
            }
            other => panic!("expected Close(pctb_revert), got {:?}", other),
        }
        assert!(s.positions.get("BTC").is_none());
    }

    #[test]
    fn test_bw_squeeze_exit() {
        // Volatility collapse: bandwidth drops below squeeze_bw while %B still extreme → bw_squeeze
        // 波動塌陷：帶寬低於壓縮閾值且 %B 仍在極端 → bw_squeeze
        let mut s = BbBreakout::new();
        s.min_persistence_ms = 0;  // disable persistence for unit tests
        // Enter long
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.positions.get("BTC"), Some(&true));

        // %B still extreme (1.1, outside [0.2,0.8]) but bandwidth collapsed below squeeze_bw (0.02)
        // → pctb_revert doesn't trigger, but bw_squeeze does
        let i = s.on_tick(&ctx(0.015, 1.1, 2.0, 1_400_000));
        assert_eq!(i.len(), 1);
        match &i[0] {
            StrategyAction::Close { reason, confidence, .. } => {
                assert_eq!(reason, "bw_squeeze");
                // 0.45 * conf_scale(1.0) = 0.45
                assert!((*confidence - 0.45).abs() < 1e-9);
            }
            other => panic!("expected Close(bw_squeeze), got {:?}", other),
        }
        assert!(s.positions.get("BTC").is_none());
    }
}
