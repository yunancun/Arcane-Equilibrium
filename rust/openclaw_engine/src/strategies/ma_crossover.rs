//! MA Crossover Strategy V2 — KAMA + ADX filter.
//! MA 交叉策略 V2 — KAMA + ADX 過濾。

use super::Strategy;
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;

pub struct MaCrossover {
    active: bool,
    position: Option<bool>,
    last_trade_ms: u64,
    cooldown_ms: u64,
    adx_threshold: f64,
    default_qty: f64,
}

impl MaCrossover {
    pub fn new() -> Self {
        Self {
            active: true, position: None, last_trade_ms: 0,
            cooldown_ms: 300_000, adx_threshold: 20.0, default_qty: 1e9,
        }
    }

    fn make_intent(&self, ctx: &TickContext, is_long: bool, conf: f64) -> OrderIntent {
        OrderIntent {
            symbol: ctx.symbol.clone(), is_long, qty: self.default_qty,
            confidence: conf, strategy: self.name().into(),
            order_type: "market".into(), limit_price: None,
        }
    }
}

impl Strategy for MaCrossover {
    fn name(&self) -> &str { "ma_crossover" }
    fn is_active(&self) -> bool { self.active }

    fn on_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        let ind = match &ctx.indicators { Some(i) => i, None => return vec![] };
        if self.last_trade_ms > 0 && ctx.timestamp_ms < self.last_trade_ms + self.cooldown_ms { return vec![]; }

        let adx = ind.adx.as_ref().map(|a| a.adx).unwrap_or(0.0);
        if adx < self.adx_threshold { return vec![]; }

        let fast = ind.kama.as_ref().map(|k| k.kama).unwrap_or_else(|| ind.sma_20.unwrap_or(0.0));
        let slow = ind.sma_20.unwrap_or(0.0);
        if fast == 0.0 || slow == 0.0 { return vec![]; }

        let mut intents = Vec::new();
        match self.position {
            None => {
                if fast > slow {
                    intents.push(self.make_intent(ctx, true, 0.6));
                    self.position = Some(true);
                    self.last_trade_ms = ctx.timestamp_ms;
                } else if fast < slow {
                    intents.push(self.make_intent(ctx, false, 0.6));
                    self.position = Some(false);
                    self.last_trade_ms = ctx.timestamp_ms;
                }
            }
            Some(is_long) => {
                if is_long && fast < slow {
                    intents.push(self.make_intent(ctx, false, 0.5));
                    self.position = None;
                    self.last_trade_ms = ctx.timestamp_ms;
                } else if !is_long && fast > slow {
                    intents.push(self.make_intent(ctx, true, 0.5));
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
    use openclaw_core::indicators::{AdxResult, IndicatorSnapshot, KamaResult};

    fn ctx_with(sma: f64, kama: f64, adx: f64, ts: u64) -> TickContext {
        TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: ts,
            indicators: Some(IndicatorSnapshot {
                sma_20: Some(sma), kama: Some(KamaResult { kama, efficiency_ratio: 0.5 }),
                adx: Some(AdxResult { adx, plus_di: 25.0, minus_di: 15.0 }),
                ..Default::default()
            }),
            signals: vec![], h0_allowed: true,
        }
    }

    #[test]
    fn test_no_signal_low_adx() {
        let mut s = MaCrossover::new();
        assert!(s.on_tick(&ctx_with(100.0, 101.0, 15.0, 0)).is_empty());
    }

    #[test]
    fn test_long_entry() {
        let mut s = MaCrossover::new();
        let i = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        assert_eq!(i.len(), 1);
        assert!(i[0].is_long);
    }

    #[test]
    fn test_exit_on_reverse() {
        let mut s = MaCrossover::new();
        s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0));
        let i = s.on_tick(&ctx_with(101.0, 100.0, 25.0, 500_000));
        assert_eq!(i.len(), 1);
        assert!(!i[0].is_long);
    }
}
