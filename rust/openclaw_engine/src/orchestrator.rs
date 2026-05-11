//! Strategy Orchestrator — dispatch ticks to strategies, collect intents (R04-4).
//! 策略調度器 — 分派 tick 到策略，收集意圖。
//!
//! MODULE_NOTE (EN): Holds registered Strategy trait objects, dispatches TickContext
//!   to each on_tick(), collects StrategyAction results for the pipeline.
//! MODULE_NOTE (中): 持有已註冊的 Strategy trait 物件，將 TickContext 分派到各
//!   on_tick()，收集 StrategyAction 結果供管線處理。

use std::collections::{HashMap, HashSet};

use openclaw_core::alpha_surface::{AlphaSourceTag, AlphaSurface};

use crate::config::risk_config::CusumConfig;
use crate::risk_cusum::{evaluate_downside_cusum, CusumEvaluation};
use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::{StrategyInfo, TickContext};

/// CUSUM alarm attached to a registered strategy.
/// 綁定到已註冊策略的 CUSUM 告警。
#[derive(Debug, Clone, PartialEq)]
pub struct StrategyCusumAlarm {
    pub strategy_name: String,
    pub evaluation: CusumEvaluation,
}

/// W-AUDIT-8a Phase A：alpha source dispatch tracking key（tag + strategy name）。
pub type AlphaDispatchKey = (AlphaSourceTag, String);

/// Strategy orchestrator — dispatches ticks to all active strategies.
/// 策略調度器 — 分派 tick 到所有活躍策略。
pub struct Orchestrator {
    strategies: Vec<Box<dyn Strategy>>,
    /// W-AUDIT-8a Phase A：dispatched 計數，pub(crate) 暴露供 step_4_5_dispatch
    /// hot path 以 disjoint-field split borrow 增量。
    pub(crate) alpha_dispatched_counter: HashMap<AlphaDispatchKey, u64>,
    /// W-AUDIT-8a Phase A：surface field 為 None 的 declared tag 計數。
    pub(crate) alpha_unavailable_counter: HashMap<AlphaDispatchKey, u64>,
}

impl Orchestrator {
    pub fn new() -> Self {
        Self {
            strategies: Vec::new(),
            alpha_dispatched_counter: HashMap::new(),
            alpha_unavailable_counter: HashMap::new(),
        }
    }

    /// Register a strategy.
    /// 註冊策略。
    pub fn register(&mut self, strategy: Box<dyn Strategy>) {
        self.strategies.push(strategy);
    }

    /// W7-5 part 2：bootstrap 階段呼叫每個策略的 `import_positions(&paper_state)`，
    /// 讓策略各自從 paper_state 已 seed 的倉位重建內部 self.positions /
    /// self.net_inventory / self.symbols。對應 `event_consumer/bootstrap.rs` 中
    /// `StrategyFactory::create_for_engine` register 之後、grant_paper_auth 之前
    /// 的單次呼叫。各策略 override 內以 `pos.owner_strategy == self.name()` 過濾。
    pub fn import_positions_for_all(&mut self, paper_state: &crate::paper_state::PaperState) {
        for strategy in &mut self.strategies {
            strategy.import_positions(paper_state);
        }
    }

    /// Dispatch tick to all strategies and collect intents.
    /// NOTE: Not called in production since RC-04 (per-strategy loop in tick_pipeline).
    /// Retained for test helpers and potential future batch-processing use.
    /// 分派 tick 到所有策略並收集意圖。
    /// 注意：自 RC-04 起生產環境不再調用（tick_pipeline 使用逐策略循環）。
    /// 保留用於測試輔助和潛在的未來批處理。
    /// W-AUDIT-8a Phase A：簽名升級加 `surface`，並 tally counter。
    #[allow(dead_code)]
    pub fn dispatch_tick(
        &mut self,
        ctx: &TickContext,
        surface: &AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        let mut all_intents = Vec::new();
        for strategy in &mut self.strategies {
            if strategy.is_active() {
                Self::tally_alpha_sources(
                    strategy.name(),
                    strategy.declared_alpha_sources(),
                    surface,
                    &mut self.alpha_dispatched_counter,
                    &mut self.alpha_unavailable_counter,
                );
                let intents = strategy.on_tick(ctx, surface);
                all_intents.extend(intents);
            }
        }
        all_intents
    }

    /// Dispatch tick while filtering strategies that have an active CUSUM alarm.
    ///
    /// This is the G7-04 Phase B consumer hook. It is not used by the hot
    /// production path yet; `tick_pipeline` still calls the explicit per-strategy
    /// loop. The method gives Phase C a tested, side-effect-free route to wire
    /// realized-edge alarms into strategy dispatch without changing existing
    /// behaviour while `RiskConfig.cusum.enabled=false`.
    ///
    /// CUSUM alarm strategy 會被跳過；目前生產 hot path 尚未調用此方法，預設
    /// `cusum.enabled=false` 因此現有行為不變。
    pub fn dispatch_tick_with_cusum_filter(
        &mut self,
        ctx: &TickContext,
        surface: &AlphaSurface<'_>,
        realized_net_bps_by_strategy: &HashMap<String, Vec<f64>>,
        cfg: &CusumConfig,
    ) -> Vec<StrategyAction> {
        let blocked: HashSet<String> = self
            .strategy_cusum_alarms(realized_net_bps_by_strategy, cfg)
            .into_iter()
            .map(|alarm| alarm.strategy_name.to_lowercase())
            .collect();
        let mut all_intents = Vec::new();
        for strategy in &mut self.strategies {
            if !strategy.is_active() || blocked.contains(&strategy.name().to_lowercase()) {
                continue;
            }
            Self::tally_alpha_sources(
                strategy.name(),
                strategy.declared_alpha_sources(),
                surface,
                &mut self.alpha_dispatched_counter,
                &mut self.alpha_unavailable_counter,
            );
            let intents = strategy.on_tick(ctx, surface);
            all_intents.extend(intents);
        }
        all_intents
    }

    /// W-AUDIT-8a Phase A：tally alpha source dispatch metric。
    pub(crate) fn tally_alpha_sources(
        strategy_name: &str,
        declared: &[AlphaSourceTag],
        surface: &AlphaSurface<'_>,
        dispatched_counter: &mut HashMap<AlphaDispatchKey, u64>,
        unavailable_counter: &mut HashMap<AlphaDispatchKey, u64>,
    ) {
        for tag in declared {
            let available = surface.is_source_available(*tag);
            let key = (*tag, strategy_name.to_string());
            if available {
                *dispatched_counter.entry(key).or_insert(0) += 1;
            } else {
                *unavailable_counter.entry(key).or_insert(0) += 1;
            }
        }
    }

    /// W-AUDIT-8a Phase A：snapshot getter for healthcheck / IPC export。
    pub fn alpha_dispatched_snapshot(&self) -> &HashMap<AlphaDispatchKey, u64> {
        &self.alpha_dispatched_counter
    }

    /// W-AUDIT-8a Phase A：snapshot unavailable counter。
    pub fn alpha_unavailable_snapshot(&self) -> &HashMap<AlphaDispatchKey, u64> {
        &self.alpha_unavailable_counter
    }

    /// Evaluate G7-04 downside-CUSUM for registered active strategies.
    ///
    /// Missing realized-edge history is treated as no alarm. Unknown strategy
    /// keys in the input map are ignored; only registered active strategy names
    /// can return alarms. This keeps the hook safe for future DB/IPC snapshots.
    /// 僅針對已註冊且 active 的策略評估；缺資料/未知策略不告警。
    pub fn strategy_cusum_alarms(
        &self,
        realized_net_bps_by_strategy: &HashMap<String, Vec<f64>>,
        cfg: &CusumConfig,
    ) -> Vec<StrategyCusumAlarm> {
        if !cfg.enabled {
            return Vec::new();
        }
        let mut alarms = Vec::new();
        for strategy in &self.strategies {
            if !strategy.is_active() {
                continue;
            }
            let Some(values) = realized_net_bps_by_strategy.get(strategy.name()) else {
                continue;
            };
            let evaluation = evaluate_downside_cusum(values, cfg);
            if evaluation.alarm {
                alarms.push(StrategyCusumAlarm {
                    strategy_name: strategy.name().to_string(),
                    evaluation,
                });
            }
        }
        alarms
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

    /// W-AUDIT-8a Phase A：disjoint-field split borrow — 同時取 strategies +
    /// dispatch / unavailable counter 的 mutable ref，hot path 避免 NLL 衝突。
    #[allow(clippy::type_complexity)]
    pub fn split_borrow_for_dispatch(
        &mut self,
    ) -> (
        &mut [Box<dyn Strategy>],
        &mut HashMap<AlphaDispatchKey, u64>,
        &mut HashMap<AlphaDispatchKey, u64>,
    ) {
        (
            &mut self.strategies,
            &mut self.alpha_dispatched_counter,
            &mut self.alpha_unavailable_counter,
        )
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

    #[derive(Clone)]
    struct MockStrategy {
        name: String,
        active: bool,
        actions: Vec<StrategyAction>,
    }

    impl Strategy for MockStrategy {
        fn name(&self) -> &str {
            &self.name
        }
        fn is_active(&self) -> bool {
            self.active
        }
        fn set_active(&mut self, active: bool) {
            self.active = active;
        }
        fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
            const TAGS: &[AlphaSourceTag] = &[AlphaSourceTag::Ta1m];
            TAGS
        }
        fn on_tick(
            &mut self,
            _ctx: &TickContext<'_>,
            _surface: &AlphaSurface<'_>,
        ) -> Vec<StrategyAction> {
            self.actions.clone()
        }
    }

    fn mock_strategy(name: &str, active: bool, actions: Vec<StrategyAction>) -> Box<dyn Strategy> {
        Box::new(MockStrategy {
            name: name.to_string(),
            active,
            actions,
        })
    }

    fn ctx() -> TickContext<'static> {
        TickContext {
            symbol: "BTC",
            price: 50000.0,
            timestamp_ms: 0,
            indicators: None,
            indicators_5m: None,
            signals: &[],
            h0_allowed: true,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            best_bid: None,
            best_ask: None,
            tick_size: None,
            alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
            position_state: None,
            is_pinned: true,
        }
    }

    fn empty_surface() -> &'static AlphaSurface<'static> {
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE
    }

    fn intent(strategy: &str) -> OrderIntent {
        OrderIntent {
            symbol: "BTC".into(),
            is_long: true,
            qty: 0.01,
            confidence: 0.8,
            strategy: strategy.into(),
            order_type: "market".into(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        }
    }

    fn cusum_on() -> CusumConfig {
        CusumConfig {
            enabled: true,
            slack_k: 0.5,
            threshold_h: 4.0,
            min_observations: 5,
            target_return_bps: 0.0,
        }
    }

    #[test]
    fn test_empty_orchestrator() {
        let mut orch = Orchestrator::new();
        assert!(orch.dispatch_tick(&ctx(), empty_surface()).is_empty());
    }

    #[test]
    fn test_dispatch_collects_intents() {
        let mut orch = Orchestrator::new();
        let intent = intent("mock");
        orch.register(mock_strategy(
            "mock",
            true,
            vec![StrategyAction::Open(intent.clone())],
        ));
        assert_eq!(orch.dispatch_tick(&ctx(), empty_surface()).len(), 1);
    }

    #[test]
    fn test_alpha_tally_uses_surface_availability_for_cross_asset() {
        let panel = openclaw_core::alpha_surface::BtcLeadLagPanel {
            alt_symbols: vec!["ETHUSDT".to_string()],
            btc_lead_return_pct: 0.25,
            lead_window_secs: 60,
            alt_xcorr: vec![0.5],
            alt_expected_dir: vec![1],
            snapshot_ts_ms: 1715000000000,
            source_tier: "test".to_string(),
        };
        let surface = AlphaSurface {
            btc_lead_lag: Some(&panel),
            ..AlphaSurface::empty()
        };
        let mut dispatched = HashMap::new();
        let mut unavailable = HashMap::new();

        Orchestrator::tally_alpha_sources(
            "lead_lag_strategy",
            &[AlphaSourceTag::CrossAsset],
            &surface,
            &mut dispatched,
            &mut unavailable,
        );

        let key = (AlphaSourceTag::CrossAsset, "lead_lag_strategy".to_string());
        assert_eq!(dispatched.get(&key), Some(&1));
        assert!(!unavailable.contains_key(&key));
    }

    #[test]
    fn test_inactive_strategy_skipped() {
        let mut orch = Orchestrator::new();
        orch.register(mock_strategy(
            "mock",
            false,
            vec![StrategyAction::Open(intent("mock"))],
        ));
        assert!(orch.dispatch_tick(&ctx(), empty_surface()).is_empty());
    }

    #[test]
    fn test_strategy_count() {
        let mut orch = Orchestrator::new();
        orch.register(mock_strategy("mock", true, vec![]));
        orch.register(mock_strategy("idle", false, vec![]));
        assert_eq!(orch.strategy_count(), 2);
        assert_eq!(orch.active_strategy_names().len(), 1);
    }

    #[test]
    fn test_find_strategy_mut() {
        let mut orch = Orchestrator::new();
        orch.register(mock_strategy("mock", true, vec![]));
        // MockStrategy.name() returns "mock"
        assert!(orch.find_strategy_mut("mock").is_some());
        assert!(orch.find_strategy_mut("MOCK").is_some()); // case-insensitive
        assert!(orch.find_strategy_mut("nonexistent").is_none());
    }

    #[test]
    fn test_cusum_alarms_disabled_returns_empty() {
        let mut orch = Orchestrator::new();
        orch.register(mock_strategy("grid_trading", true, vec![]));
        let mut returns = HashMap::new();
        returns.insert("grid_trading".to_string(), vec![-20.0; 20]);
        assert!(orch
            .strategy_cusum_alarms(&returns, &CusumConfig::default())
            .is_empty());
    }

    #[test]
    fn test_cusum_alarms_ignore_inactive_and_unknown_strategies() {
        let mut orch = Orchestrator::new();
        orch.register(mock_strategy("grid_trading", false, vec![]));
        let mut returns = HashMap::new();
        returns.insert("grid_trading".to_string(), vec![-20.0; 20]);
        returns.insert("unknown".to_string(), vec![-20.0; 20]);
        assert!(orch.strategy_cusum_alarms(&returns, &cusum_on()).is_empty());
    }

    #[test]
    fn test_cusum_alarms_for_active_negative_edge() {
        let mut orch = Orchestrator::new();
        orch.register(mock_strategy("grid_trading", true, vec![]));
        let mut returns = HashMap::new();
        returns.insert(
            "grid_trading".to_string(),
            vec![-2.0, -5.0, -8.0, -10.0, -12.0, -15.0, -18.0, -21.0, -24.0],
        );
        let alarms = orch.strategy_cusum_alarms(&returns, &cusum_on());
        assert_eq!(alarms.len(), 1);
        assert_eq!(alarms[0].strategy_name, "grid_trading");
        assert!(alarms[0].evaluation.alarm);
    }

    #[test]
    fn test_dispatch_with_cusum_filter_skips_alarm_strategy_only() {
        let mut orch = Orchestrator::new();
        orch.register(mock_strategy(
            "grid_trading",
            true,
            vec![StrategyAction::Open(intent("grid_trading"))],
        ));
        orch.register(mock_strategy(
            "ma_crossover",
            true,
            vec![StrategyAction::Open(intent("ma_crossover"))],
        ));
        let mut returns = HashMap::new();
        returns.insert(
            "grid_trading".to_string(),
            vec![-2.0, -5.0, -8.0, -10.0, -12.0, -15.0, -18.0, -21.0, -24.0],
        );
        returns.insert("ma_crossover".to_string(), vec![3.0, 4.0, 5.0, 3.5, 4.5]);
        let actions =
            orch.dispatch_tick_with_cusum_filter(&ctx(), empty_surface(), &returns, &cusum_on());
        assert_eq!(actions.len(), 1);
        match &actions[0] {
            StrategyAction::Open(intent) => assert_eq!(intent.strategy, "ma_crossover"),
            _ => panic!("expected open intent"),
        }
    }
}
