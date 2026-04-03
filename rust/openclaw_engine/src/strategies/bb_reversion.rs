//! BB Reversion Strategy V2 — Bollinger Band mean reversion + RSI filter.
//! BB 回歸策略 V2 — 布林帶均值回歸 + RSI 過濾。

use super::Strategy;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

pub struct BbReversion {
    active: bool,
    position: Option<bool>,
    last_trade_ms: u64,
    cooldown_ms: u64,
    default_qty: f64,
}

impl BbReversion {
    pub fn new() -> Self {
        Self { active: true, position: None, last_trade_ms: 0, cooldown_ms: 600_000, default_qty: 0.01 }
    }

    fn make_intent(&self, ctx: &TickContext, is_long: bool, conf: f64) -> OrderIntent {
        OrderIntent {
            symbol: ctx.symbol.clone(), is_long, qty: self.default_qty, confidence: conf,
            strategy: self.name().into(), order_type: "market".into(), limit_price: None,
        }
    }
}

impl Strategy for BbReversion {
    fn name(&self) -> &str { "bb_reversion" }
    fn is_active(&self) -> bool { self.active }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        let ind = match &ctx.indicators { Some(i) => i, None => return vec![] };
        if self.last_trade_ms > 0 && ctx.timestamp_ms < self.last_trade_ms + self.cooldown_ms { return vec![]; }

        let bb = match &ind.bollinger { Some(b) => b, None => return vec![] };
        let rsi = ind.rsi_14.unwrap_or(50.0);

        let mut intents = Vec::new();
        match self.position {
            None => {
                if bb.percent_b < 0.0 && rsi < 30.0 {
                    intents.push(self.make_intent(ctx, true, 0.6));
                    self.position = Some(true);
                    self.last_trade_ms = ctx.timestamp_ms;
                } else if bb.percent_b > 1.0 && rsi > 70.0 {
                    intents.push(self.make_intent(ctx, false, 0.6));
                    self.position = Some(false);
                    self.last_trade_ms = ctx.timestamp_ms;
                }
            }
            Some(is_long) => {
                if bb.percent_b >= 0.2 && bb.percent_b <= 0.8 {
                    intents.push(self.make_intent(ctx, !is_long, 0.5));
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

    fn ctx_bb(pct_b: f64, rsi: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                bollinger: Some(BollingerResult {
                    upper: 51000.0, middle: 50000.0, lower: 49000.0,
                    bandwidth: 0.04, percent_b: pct_b,
                }),
                rsi_14: Some(rsi), ..Default::default()
            }),
            signals: vec![], h0_allowed: true,
        }
    }

    #[test]
    fn test_long_oversold() {
        let mut s = BbReversion::new();
        let i = s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        assert_eq!(i.len(), 1);
        assert!(i[0].is_long);
    }

    #[test]
    fn test_exit_mean() {
        let mut s = BbReversion::new();
        s.on_tick(&ctx_bb(-0.1, 25.0, 0));
        let i = s.on_tick(&ctx_bb(0.5, 50.0, 700_000));
        assert_eq!(i.len(), 1);
    }
}
