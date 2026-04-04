//! Strategy Orchestrator — dispatch ticks to strategies, collect intents (R04-4).
//! 策略調度器 — 分派 tick 到策略，收集意圖。

use crate::intent_processor::OrderIntent;
use crate::strategies::Strategy;
use crate::tick_pipeline::TickContext;

/// Strategy orchestrator — dispatches ticks to all active strategies.
/// 策略調度器 — 分派 tick 到所有活躍策略。
pub struct Orchestrator {
    strategies: Vec<Box<dyn Strategy>>,
}

impl Orchestrator {
    pub fn new() -> Self {
        Self { strategies: Vec::new() }
    }

    /// Register a strategy.
    /// 註冊策略。
    pub fn register(&mut self, strategy: Box<dyn Strategy>) {
        self.strategies.push(strategy);
    }

    /// Dispatch tick to all strategies and collect intents.
    /// 分派 tick 到所有策略並收集意圖。
    pub fn dispatch_tick(&mut self, ctx: &TickContext) -> Vec<OrderIntent> {
        let mut all_intents = Vec::new();
        for strategy in &mut self.strategies {
            if strategy.is_active() {
                let intents = strategy.on_tick(ctx);
                all_intents.extend(intents);
            }
        }
        all_intents
    }

    /// Get count of registered strategies.
    /// 獲取已註冊策略數量。
    pub fn strategy_count(&self) -> usize {
        self.strategies.len()
    }

    /// Get names of active strategies.
    /// 獲取活躍策略名稱。
    pub fn active_strategy_names(&self) -> Vec<&str> {
        self.strategies.iter()
            .filter(|s| s.is_active())
            .map(|s| s.name())
            .collect()
    }

    /// Mutable access to strategies for per-strategy rejection/fill callbacks (RC-04/RC-05).
    /// 策略的可變訪問，供逐策略拒絕/成交回調使用。
    pub fn strategies_mut(&mut self) -> &mut [Box<dyn Strategy>] {
        &mut self.strategies
    }
}

impl Default for Orchestrator {
    fn default() -> Self { Self::new() }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::strategies::Strategy;

    struct MockStrategy {
        active: bool,
        intents: Vec<OrderIntent>,
    }

    impl Strategy for MockStrategy {
        fn name(&self) -> &str { "mock" }
        fn is_active(&self) -> bool { self.active }
        fn on_tick(&mut self, _ctx: &TickContext) -> Vec<OrderIntent> {
            self.intents.clone()
        }
    }

    #[test]
    fn test_empty_orchestrator() {
        let mut orch = Orchestrator::new();
        let ctx = TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: 0,
            indicators: None, signals: vec![], h0_allowed: true,
        };
        assert!(orch.dispatch_tick(&ctx).is_empty());
    }

    #[test]
    fn test_dispatch_collects_intents() {
        let mut orch = Orchestrator::new();
        let intent = OrderIntent {
            symbol: "BTC".into(), is_long: true, qty: 0.01, confidence: 0.8,
            strategy: "mock".into(), order_type: "market".into(), limit_price: None,
        };
        orch.register(Box::new(MockStrategy { active: true, intents: vec![intent.clone()] }));
        let ctx = TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: 0,
            indicators: None, signals: vec![], h0_allowed: true,
        };
        assert_eq!(orch.dispatch_tick(&ctx).len(), 1);
    }

    #[test]
    fn test_inactive_strategy_skipped() {
        let mut orch = Orchestrator::new();
        let intent = OrderIntent {
            symbol: "BTC".into(), is_long: true, qty: 0.01, confidence: 0.8,
            strategy: "mock".into(), order_type: "market".into(), limit_price: None,
        };
        orch.register(Box::new(MockStrategy { active: false, intents: vec![intent] }));
        let ctx = TickContext {
            symbol: "BTC".into(), price: 50000.0, timestamp_ms: 0,
            indicators: None, signals: vec![], h0_allowed: true,
        };
        assert!(orch.dispatch_tick(&ctx).is_empty());
    }

    #[test]
    fn test_strategy_count() {
        let mut orch = Orchestrator::new();
        orch.register(Box::new(MockStrategy { active: true, intents: vec![] }));
        orch.register(Box::new(MockStrategy { active: false, intents: vec![] }));
        assert_eq!(orch.strategy_count(), 2);
        assert_eq!(orch.active_strategy_names().len(), 1);
    }
}
