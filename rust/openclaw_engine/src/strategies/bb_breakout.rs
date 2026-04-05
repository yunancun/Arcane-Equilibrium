//! BB Breakout Strategy V2 — Squeeze→Expansion + Volume + Donchian + ATR trailing stop + Regime exit.
//! BB 突破策略 V2 — 壓縮→擴張 + 成交量 + Donchian + ATR 追蹤止損 + Regime 出場。

use super::{ParamRange, Strategy, StrategyParams};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use serde::{Deserialize, Serialize};
use tracing::info;

/// Tunable parameters for BB Breakout (Phase 3a).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct BbBreakoutParams {
    pub cooldown_ms: u64,
    pub default_qty: f64,
    pub squeeze_bw: f64,
    pub expansion_bw: f64,
    pub volume_threshold: f64,
    pub trailing_stop_atr_mult: f64,
}

impl Default for BbBreakoutParams {
    fn default() -> Self {
        Self {
            cooldown_ms: 300_000,
            default_qty: 1e9,
            squeeze_bw: DEFAULT_SQUEEZE_BW,
            expansion_bw: DEFAULT_EXPANSION_BW,
            volume_threshold: DEFAULT_VOLUME_THRESHOLD,
            trailing_stop_atr_mult: 2.0,
        }
    }
}

impl StrategyParams for BbBreakoutParams {
    fn param_ranges() -> Vec<ParamRange> {
        vec![
            ParamRange { name: "cooldown_ms".into(), min: 60_000.0, max: 3_600_000.0, step: Some(60_000.0), agent_adjustable: true, db_persisted: true },
            ParamRange { name: "squeeze_bw".into(), min: 0.005, max: 0.05, step: None, agent_adjustable: true, db_persisted: true },
            ParamRange { name: "expansion_bw".into(), min: 0.02, max: 0.1, step: None, agent_adjustable: true, db_persisted: true },
            ParamRange { name: "volume_threshold".into(), min: 1.0, max: 5.0, step: Some(0.1), agent_adjustable: true, db_persisted: true },
            ParamRange { name: "trailing_stop_atr_mult".into(), min: 1.0, max: 5.0, step: Some(0.5), agent_adjustable: true, db_persisted: true },
        ]
    }

    fn validate(&self) -> Result<(), String> {
        if self.squeeze_bw >= self.expansion_bw { return Err("squeeze_bw must be < expansion_bw".into()); }
        if self.volume_threshold < 1.0 { return Err("volume_threshold must be >= 1.0".into()); }
        if self.trailing_stop_atr_mult < 0.5 { return Err("trailing_stop_atr_mult must be >= 0.5".into()); }
        Ok(())
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
    position: Option<bool>,
    was_in_squeeze: bool,
    last_trade_ms: u64,
    cooldown_ms: u64,
    default_qty: f64,
    // V2: ATR trailing stop fields / ATR 追蹤止損欄位
    entry_price: Option<f64>,
    trailing_stop: Option<f64>,
    /// ATR multiplier for trailing stop distance. Agent-adjustable (Phase 3a).
    /// ATR 追蹤止損距離乘數。Agent 可調（Phase 3a）。
    pub trailing_stop_atr_mult: f64,
    // RC-03: Configurable thresholds for Agent adjustability
    // RC-03：可配置閾值，供 Agent 動態調整
    /// Bandwidth below this = squeeze detected / 帶寬低於此值 = 偵測到壓縮
    pub squeeze_bw: f64,
    /// Bandwidth above this = expansion confirmed / 帶寬高於此值 = 確認擴張
    pub expansion_bw: f64,
    /// Minimum volume ratio for breakout entry / 突破入場最低成交量倍率
    pub volume_threshold: f64,
    // RC-04: Previous state for rejection rollback / 拒絕回滾用的先前狀態
    prev_position: Option<bool>,
    prev_was_in_squeeze: bool,
    prev_entry_price: Option<f64>,
    prev_trailing_stop: Option<f64>,
    prev_last_trade_ms: u64,
}

impl BbBreakout {
    pub fn new() -> Self {
        Self {
            active: true, position: None, was_in_squeeze: false,
            last_trade_ms: 0, cooldown_ms: 600_000, default_qty: 1e9,
            entry_price: None, trailing_stop: None, trailing_stop_atr_mult: 2.0,
            squeeze_bw: DEFAULT_SQUEEZE_BW,
            expansion_bw: DEFAULT_EXPANSION_BW,
            volume_threshold: DEFAULT_VOLUME_THRESHOLD,
            prev_position: None, prev_was_in_squeeze: false,
            prev_entry_price: None, prev_trailing_stop: None,
            prev_last_trade_ms: 0,
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
        }
    }
}

impl Strategy for BbBreakout {
    fn name(&self) -> &str { "bb_breakout" }
    fn is_active(&self) -> bool { self.active }

    /// RC-04: Revert position, entry_price, trailing_stop, was_in_squeeze on rejection.
    /// RC-04：拒絕時回滾 position、entry_price、trailing_stop、was_in_squeeze。
    fn on_rejection(&mut self, _intent: &OrderIntent, _reason: &str) {
        self.position = self.prev_position;
        self.was_in_squeeze = self.prev_was_in_squeeze;
        self.entry_price = self.prev_entry_price;
        self.trailing_stop = self.prev_trailing_stop;
        self.last_trade_ms = self.prev_last_trade_ms;
    }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        let ind = match &ctx.indicators { Some(i) => i, None => return vec![] };
        let bb = match &ind.bollinger { Some(b) => b, None => return vec![] };
        let vol_ratio = ind.volume_ratio.unwrap_or(1.0);

        // RC-04: Snapshot state before any mutation for rejection rollback.
        // RC-04：在任何變更前快照狀態，供拒絕回滾使用。
        self.prev_position = self.position;
        self.prev_was_in_squeeze = self.was_in_squeeze;
        self.prev_entry_price = self.entry_price;
        self.prev_trailing_stop = self.trailing_stop;
        self.prev_last_trade_ms = self.last_trade_ms;

        if bb.bandwidth < self.squeeze_bw { self.was_in_squeeze = true; }
        if self.last_trade_ms > 0 && ctx.timestamp_ms < self.last_trade_ms + self.cooldown_ms { return vec![]; }

        let mut intents = Vec::new();
        match self.position {
            None => {
                if self.was_in_squeeze && bb.bandwidth > self.expansion_bw && vol_ratio >= self.volume_threshold {
                    let is_long = bb.percent_b > 1.0;
                    let is_short = bb.percent_b < 0.0;

                    // A3: Donchian confirmation — price must also breach Donchian channel
                    // A3：Donchian 确认 — 价格需同时突破 Donchian 通道
                    if let Some(dc) = &ind.donchian {
                        if is_long && ctx.price < dc.upper { return vec![]; }
                        if is_short && ctx.price > dc.lower { return vec![]; }
                    }

                    if is_long || is_short {
                        // A4: Hurst regime boost — trending regime boosts breakout confidence
                        // A4：Hurst 趋势状态 — 趋势型市场提升突破信心
                        let hurst_boost: f64 = match &ind.hurst {
                            Some(h) if h.regime == "trending" => 0.1,
                            _ => 0.0,
                        };
                        intents.push(OrderIntent {
                            symbol: ctx.symbol.clone(), is_long, qty: self.default_qty,
                            confidence: (0.7_f64 + hurst_boost).min(1.0), strategy: self.name().into(),
                            order_type: "market".into(), limit_price: None,
                        });
                        self.position = Some(is_long);
                        self.was_in_squeeze = false;
                        self.last_trade_ms = ctx.timestamp_ms;
                        // V2: Record entry price and initialize trailing stop
                        // V2：記錄入場價格並初始化追蹤止損
                        self.entry_price = Some(ctx.price);
                        self.trailing_stop = if let Some(atr_res) = &ind.atr_14 {
                            let dist = atr_res.atr * self.trailing_stop_atr_mult;
                            Some(if is_long { ctx.price - dist } else { ctx.price + dist })
                        } else {
                            None
                        };
                    }
                }
            }
            Some(is_long) => {
                let mut should_exit = false;
                let mut exit_confidence = 0.5_f64;

                // V2: ATR trailing stop — dynamic trailing stop to ride trends
                // V2：ATR 追蹤止損 — 動態追蹤止損以乘勢而行
                if let Some(atr_res) = &ind.atr_14 {
                    let stop_distance = atr_res.atr * self.trailing_stop_atr_mult;
                    if is_long {
                        // Long: trailing stop ratchets up as price rises
                        // 做多：追蹤止損隨價格上漲而上移
                        let new_stop = ctx.price - stop_distance;
                        if self.trailing_stop.is_none() || new_stop > self.trailing_stop.unwrap() {
                            self.trailing_stop = Some(new_stop);
                        }
                        if ctx.price <= self.trailing_stop.unwrap() {
                            should_exit = true;
                            exit_confidence = 0.7;
                        }
                    } else {
                        // Short: trailing stop ratchets down as price falls
                        // 做空：追蹤止損隨價格下跌而下移
                        let new_stop = ctx.price + stop_distance;
                        if self.trailing_stop.is_none() || new_stop < self.trailing_stop.unwrap() {
                            self.trailing_stop = Some(new_stop);
                        }
                        if ctx.price >= self.trailing_stop.unwrap() {
                            should_exit = true;
                            exit_confidence = 0.7;
                        }
                    }
                }

                // V2: Regime exit — exit when regime shifts from trending to ranging/squeeze
                // V2：Regime 出場 — 當趨勢狀態轉為震盪/壓縮時出場
                if !should_exit {
                    if let Some(h) = &ind.hurst {
                        if h.regime == "mean_reverting" || h.regime == "random_walk" {
                            should_exit = true;
                            exit_confidence = 0.6;
                        }
                    }
                }

                // Original exit: %B returns to mid-band or bandwidth squeezes again
                // 原有出場：%B 回到中間帶或帶寬再次壓縮
                if !should_exit {
                    if (bb.percent_b >= 0.2 && bb.percent_b <= 0.8) || bb.bandwidth < self.squeeze_bw {
                        should_exit = true;
                        exit_confidence = 0.5;
                    }
                }

                if should_exit {
                    intents.push(OrderIntent {
                        symbol: ctx.symbol.clone(), is_long: !is_long, qty: self.default_qty,
                        confidence: exit_confidence, strategy: self.name().into(),
                        order_type: "market".into(), limit_price: None,
                    });
                    self.position = None;
                    self.last_trade_ms = ctx.timestamp_ms;
                    // V2: Reset trailing stop state on exit / 出場時重置追蹤止損狀態
                    self.entry_price = None;
                    self.trailing_stop = None;
                }
            }
        }
        intents
    }

    fn update_params_json(&mut self, json: &str) -> Result<(), String> {
        let p: BbBreakoutParams = serde_json::from_str(json).map_err(|e| e.to_string())?;
        self.update_params(p)
    }
    fn get_params_json(&self) -> String { serde_json::to_string(&self.get_params()).unwrap_or_default() }
    fn param_ranges_json(&self) -> String { serde_json::to_string(&BbBreakoutParams::param_ranges()).unwrap_or_default() }
}

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::indicators::{AtrResult, BollingerResult, HurstResult, IndicatorSnapshot};

    fn ctx(bw: f64, pct_b: f64, vol: f64, ts: u64) -> TickContext {
        ctx_ext(bw, pct_b, vol, ts, 50000.0, None, None)
    }

    /// Extended context builder with price, ATR, and Hurst overrides.
    /// 擴展上下文建構器，支持自訂價格、ATR、Hurst。
    fn ctx_ext(
        bw: f64, pct_b: f64, vol: f64, ts: u64, price: f64,
        atr: Option<AtrResult>, hurst: Option<HurstResult>,
    ) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price, timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                bollinger: Some(BollingerResult {
                    upper: 51000.0, middle: 50000.0, lower: 49000.0,
                    bandwidth: bw, percent_b: pct_b,
                }),
                volume_ratio: Some(vol), atr_14: atr, hurst, ..Default::default()
            }),
            signals: vec![], h0_allowed: true,
        }
    }

    #[test]
    fn test_squeeze_then_breakout() {
        let mut s = BbBreakout::new();
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0));
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
        assert!(i[0].is_long);
    }

    #[test]
    fn test_no_breakout_without_squeeze() {
        let mut s = BbBreakout::new();
        assert!(s.on_tick(&ctx(0.05, 1.1, 2.0, 0)).is_empty());
    }

    #[test]
    fn test_entry_price_recorded() {
        // After entry, entry_price should be set / 入場後 entry_price 應被設置
        let mut s = BbBreakout::new();
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000)); // breakout long
        assert_eq!(s.entry_price, Some(50000.0));
        assert!(s.trailing_stop.is_none()); // no ATR data, no trailing stop yet
    }

    #[test]
    fn test_atr_trailing_stop_long_exit() {
        // Long position: price drops below trailing stop -> exit
        // 做多倉位：價格跌破追蹤止損 -> 出場
        let mut s = BbBreakout::new();
        let atr = || Some(AtrResult { atr: 500.0, atr_percent: 0.01 });

        // Enter long
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout
        assert!(s.position == Some(true));
        // trailing_stop = 50000 - 500*2 = 49000
        assert_eq!(s.trailing_stop, Some(49000.0));

        // Price rises -> trailing stop ratchets up, no exit
        // 價格上漲 -> 追蹤止損上移，不出場
        let i = s.on_tick(&ctx_ext(0.05, 1.2, 2.0, 1_400_000, 52000.0, atr(), None));
        assert!(i.is_empty()); // still in trend
        assert_eq!(s.trailing_stop, Some(51000.0)); // 52000 - 1000

        // Price drops to trailing stop -> exit
        // 價格跌至追蹤止損 -> 出場
        let i = s.on_tick(&ctx_ext(0.05, 0.9, 2.0, 2_100_000, 51000.0, atr(), None));
        assert_eq!(i.len(), 1);
        assert!(!i[0].is_long); // close long = sell
        assert!((i[0].confidence - 0.7).abs() < 1e-9);
        assert!(s.position.is_none());
        assert!(s.entry_price.is_none());
        assert!(s.trailing_stop.is_none());
    }

    #[test]
    fn test_atr_trailing_stop_short_exit() {
        // Short position: price rises above trailing stop -> exit
        // 做空倉位：價格漲破追蹤止損 -> 出場
        let mut s = BbBreakout::new();
        let atr = || Some(AtrResult { atr: 500.0, atr_percent: 0.01 });

        // Enter short
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        s.on_tick(&ctx_ext(0.05, -0.1, 2.0, 700_000, 50000.0, atr(), None)); // breakout short
        assert!(s.position == Some(false));
        // trailing_stop = 50000 + 500*2 = 51000
        assert_eq!(s.trailing_stop, Some(51000.0));

        // Price drops -> trailing stop ratchets down
        let i = s.on_tick(&ctx_ext(0.05, -0.2, 2.0, 1_400_000, 48000.0, atr(), None));
        assert!(i.is_empty());
        assert_eq!(s.trailing_stop, Some(49000.0)); // 48000 + 1000

        // Price rises to trailing stop -> exit
        let i = s.on_tick(&ctx_ext(0.05, 0.1, 2.0, 2_100_000, 49000.0, atr(), None));
        assert_eq!(i.len(), 1);
        assert!(i[0].is_long); // close short = buy
    }

    #[test]
    fn test_regime_exit() {
        // Exit when regime changes to mean_reverting / 當 regime 變為均值回歸時出場
        let mut s = BbBreakout::new();
        let trending = || Some(HurstResult { hurst: 0.7, regime: "trending".into() });
        let ranging = || Some(HurstResult { hurst: 0.4, regime: "mean_reverting".into() });

        // Enter long (with trending regime boost)
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 700_000, 50000.0, None, trending()));
        assert_eq!(i.len(), 1);
        assert!((i[0].confidence - 0.8).abs() < 1e-9); // 0.7 + 0.1 hurst boost
        assert!(s.position == Some(true));

        // Regime shifts to mean_reverting -> exit
        let i = s.on_tick(&ctx_ext(0.05, 1.1, 2.0, 1_400_000, 51000.0, None, ranging()));
        assert_eq!(i.len(), 1);
        assert!(!i[0].is_long); // close long
        assert!((i[0].confidence - 0.6).abs() < 1e-9);
        assert!(s.position.is_none());
    }

    #[test]
    fn test_configurable_volume_threshold() {
        // RC-03: Custom volume threshold — higher threshold blocks low-volume breakouts
        // RC-03：自訂成交量閾值 — 較高閾值阻擋低量突破
        let mut s = BbBreakout::new();
        s.volume_threshold = 3.0; // require 3x volume instead of default 1.5x
        s.on_tick(&ctx(0.01, 0.5, 1.0, 0)); // squeeze
        // vol=2.0 passes default (1.5) but fails custom (3.0)
        // vol=2.0 通過默認閾值(1.5)但不通過自訂閾值(3.0)
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert!(i.is_empty(), "volume 2.0 should not pass threshold 3.0");

        // vol=3.5 passes custom threshold / vol=3.5 通過自訂閾值
        let i = s.on_tick(&ctx(0.05, 1.1, 3.5, 700_000));
        assert_eq!(i.len(), 1);
        assert!(i[0].is_long);
    }

    #[test]
    fn test_configurable_squeeze_expansion_bw() {
        // RC-03: Custom squeeze/expansion bandwidth thresholds
        // RC-03：自訂壓縮/擴張帶寬閾值
        let mut s = BbBreakout::new();
        s.squeeze_bw = 0.03;   // wider squeeze detection / 更寬的壓縮偵測
        s.expansion_bw = 0.06; // require stronger expansion / 要求更強擴張

        // bw=0.025 triggers squeeze with custom threshold (< 0.03)
        s.on_tick(&ctx(0.025, 0.5, 1.0, 0));
        assert!(s.was_in_squeeze);

        // bw=0.05 is expansion for default (> 0.04) but NOT for custom (< 0.06)
        let i = s.on_tick(&ctx(0.05, 1.1, 2.0, 700_000));
        assert!(i.is_empty(), "bw 0.05 should not pass expansion_bw 0.06");

        // bw=0.07 passes custom expansion threshold / 通過自訂擴張閾值
        let i = s.on_tick(&ctx(0.07, 1.1, 2.0, 700_000));
        assert_eq!(i.len(), 1);
    }

    #[test]
    fn test_bb_brk_param_ranges() { assert!(!BbBreakoutParams::param_ranges().is_empty()); }
    #[test]
    fn test_bb_brk_validate() {
        assert!(BbBreakoutParams::default().validate().is_ok());
        assert!(BbBreakoutParams { squeeze_bw: 0.05, expansion_bw: 0.04, ..Default::default() }.validate().is_err());
    }
    #[test]
    fn test_bb_brk_update() {
        let mut s = BbBreakout::new();
        assert!(s.update_params(BbBreakoutParams { trailing_stop_atr_mult: 3.0, ..Default::default() }).is_ok());
        assert!((s.get_params().trailing_stop_atr_mult - 3.0).abs() < 0.01);
    }
}
