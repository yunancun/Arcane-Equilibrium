//! BB Breakout Strategy V2 — Squeeze→Expansion + Volume + Donchian.
//! BB 突破策略 V2 — 壓縮→擴張 + 成交量 + Donchian。

use super::Strategy;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

const SQUEEZE_BW: f64 = 0.02;
const EXPANSION_BW: f64 = 0.04;
const VOLUME_THRESHOLD: f64 = 1.5;

pub struct BbBreakout {
    active: bool,
    position: Option<bool>,
    was_in_squeeze: bool,
    last_trade_ms: u64,
    cooldown_ms: u64,
    default_qty: f64,
}

impl BbBreakout {
    pub fn new() -> Self {
        Self {
            active: true, position: None, was_in_squeeze: false,
            last_trade_ms: 0, cooldown_ms: 600_000, default_qty: 1.0,
        }
    }
}

impl Strategy for BbBreakout {
    fn name(&self) -> &str { "bb_breakout" }
    fn is_active(&self) -> bool { self.active }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        let ind = match &ctx.indicators { Some(i) => i, None => return vec![] };
        let bb = match &ind.bollinger { Some(b) => b, None => return vec![] };
        let vol_ratio = ind.volume_ratio.unwrap_or(1.0);

        if bb.bandwidth < SQUEEZE_BW { self.was_in_squeeze = true; }
        if self.last_trade_ms > 0 && ctx.timestamp_ms < self.last_trade_ms + self.cooldown_ms { return vec![]; }

        let mut intents = Vec::new();
        match self.position {
            None => {
                if self.was_in_squeeze && bb.bandwidth > EXPANSION_BW && vol_ratio >= VOLUME_THRESHOLD {
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
                    }
                }
            }
            Some(is_long) => {
                if (bb.percent_b >= 0.2 && bb.percent_b <= 0.8) || bb.bandwidth < SQUEEZE_BW {
                    intents.push(OrderIntent {
                        symbol: ctx.symbol.clone(), is_long: !is_long, qty: self.default_qty,
                        confidence: 0.5, strategy: self.name().into(),
                        order_type: "market".into(), limit_price: None,
                    });
                    self.position = None;
                    self.last_trade_ms = ctx.timestamp_ms;
                }
            }
        }
        intents
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use openclaw_core::indicators::{BollingerResult, IndicatorSnapshot};

    fn ctx(bw: f64, pct_b: f64, vol: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                bollinger: Some(BollingerResult {
                    upper: 51000.0, middle: 50000.0, lower: 49000.0,
                    bandwidth: bw, percent_b: pct_b,
                }),
                volume_ratio: Some(vol), ..Default::default()
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
}
