//! Strategy Orchestrator — dispatch ticks to strategies, collect intents (R04-4).
//! 策略調度器 — 分派 tick 到策略，收集意圖。
//!
//! MODULE_NOTE (EN): Holds registered Strategy trait objects, dispatches TickContext
//!   to each on_tick(), collects StrategyAction results for the pipeline.
//! MODULE_NOTE (中): 持有已註冊的 Strategy trait 物件，將 TickContext 分派到各
//!   on_tick()，收集 StrategyAction 結果供管線處理。

use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::{StrategyInfo, TickContext};

/// Strategy orchestrator — dispatches ticks to all active strategies.
/// 策略調度器 — 分派 tick 到所有活躍策略。
pub struct Orchestrator {
    strategies: Vec<Box<dyn Strategy>>,
}

impl Orchestrator {
    pub fn new() -> Self {
        Self {
            strategies: Vec::new(),
        }
    }

    /// Register a strategy.
    /// 註冊策略。
    pub fn register(&mut self, strategy: Box<dyn Strategy>) {
        self.strategies.push(strategy);
    }

    /// Dispatch tick to all strategies and collect intents.
    /// NOTE: Not called in production since RC-04 (per-strategy loop in tick_pipeline).
    /// Retained for test helpers and potential future batch-processing use.
    /// 分派 tick 到所有策略並收集意圖。
    /// 注意：自 RC-04 起生產環境不再調用（tick_pipeline 使用逐策略循環）。
    /// 保留用於測試輔助和潛在的未來批處理。
    #[allow(dead_code)]
    pub fn dispatch_tick(&mut self, ctx: &TickContext) -> Vec<StrategyAction> {
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
        self.strategies
            .iter()
            .filter(|s| s.is_active())
            .map(|s| s.name())
            .collect()
    }

    /// Get strategy status info for IPC snapshot.
    /// 獲取策略狀態信息供 IPC 快照使用。
    pub fn strategy_infos(&self) -> Vec<StrategyInfo> {
        self.strategies
            .iter()
            .map(|s| StrategyInfo {
                name: s.name().to_string(),
                active: s.is_active(),
            })
            .collect()
    }

    /// Mutable access to strategies for per-strategy rejection/fill callbacks (RC-04/RC-05).
    /// 策略的可變訪問，供逐策略拒絕/成交回調使用。
    pub fn strategies_mut(&mut self) -> &mut [Box<dyn Strategy>] {
        &mut self.strategies
    }

    /// RRC-1-E2: Set strategy active/paused by name. Returns Ok(was_active) or Err.
    /// RRC-1-E2：按名稱設置策略活躍/暫停。返回 Ok(之前是否活躍) 或 Err。
    pub fn set_strategy_active(&mut self, name: &str, active: bool) -> Result<bool, String> {
        match self.find_strategy_mut(name) {
            Some(s) => {
                let was = s.is_active();
                s.set_active(active);
                Ok(was)
            }
            None => Err(format!("strategy not found: {name}")),
        }
    }

    /// Find a strategy by name (case-insensitive) for IPC param updates (Phase 3b PF-1).
    /// 按名稱查找策略（大小寫不敏感），用於 IPC 參數更新。
    pub fn find_strategy_mut(&mut self, name: &str) -> Option<&mut Box<dyn Strategy>> {
        let name_lower = name.to_lowercase();
        self.strategies
            .iter_mut()
            .find(|s| s.name().to_lowercase() == name_lower)
    }
}

impl Default for Orchestrator {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::intent_processor::OrderIntent;
    use crate::strategies::Strategy;

    struct MockStrategy {
        active: bool,
        actions: Vec<StrategyAction>,
    }

    impl Strategy for MockStrategy {
        fn name(&self) -> &str {
            "mock"
        }
        fn is_active(&self) -> bool {
            self.active
        }
        fn set_active(&mut self, active: bool) {
            self.active = active;
        }
        fn on_tick(&mut self, _ctx: &TickContext<'_>) -> Vec<StrategyAction> {
            self.actions.clone()
        }
    }

    #[test]
    fn test_empty_orchestrator() {
        let mut orch = Orchestrator::new();
        let ctx = TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: 0,
            indicators: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
        };
        assert!(orch.dispatch_tick(&ctx).is_empty());
    }

    #[test]
    fn test_dispatch_collects_intents() {
        let mut orch = Orchestrator::new();
        let intent = OrderIntent {
            symbol: "BTC".into(),
            is_long: true,
            qty: 0.01,
            confidence: 0.8,
            strategy: "mock".into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        };
        orch.register(Box::new(MockStrategy {
            active: true,
            actions: vec![StrategyAction::Open(intent.clone())],
        }));
        let ctx = TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: 0,
            indicators: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
        };
        assert_eq!(orch.dispatch_tick(&ctx).len(), 1);
    }

    #[test]
    fn test_inactive_strategy_skipped() {
        let mut orch = Orchestrator::new();
        let intent = OrderIntent {
            symbol: "BTC".into(),
            is_long: true,
            qty: 0.01,
            confidence: 0.8,
            strategy: "mock".into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        };
        orch.register(Box::new(MockStrategy {
            active: false,
            actions: vec![StrategyAction::Open(intent)],
        }));
        let ctx = TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: 0,
            indicators: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
        };
        assert!(orch.dispatch_tick(&ctx).is_empty());
    }

    #[test]
    fn test_strategy_count() {
        let mut orch = Orchestrator::new();
        orch.register(Box::new(MockStrategy {
            active: true,
            actions: vec![],
        }));
        orch.register(Box::new(MockStrategy {
            active: false,
            actions: vec![],
        }));
        assert_eq!(orch.strategy_count(), 2);
        assert_eq!(orch.active_strategy_names().len(), 1);
    }

    #[test]
    fn test_find_strategy_mut() {
        let mut orch = Orchestrator::new();
        orch.register(Box::new(MockStrategy {
            active: true,
            actions: vec![],
        }));
        // MockStrategy.name() returns "mock"
        assert!(orch.find_strategy_mut("mock").is_some());
        assert!(orch.find_strategy_mut("MOCK").is_some()); // case-insensitive
        assert!(orch.find_strategy_mut("nonexistent").is_none());
    }
}
