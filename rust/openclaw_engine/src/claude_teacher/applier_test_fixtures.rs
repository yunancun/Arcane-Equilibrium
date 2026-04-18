//! Test fixtures for DirectiveApplier — extracted from applier.rs (FIX-08 file size).
//! DirectiveApplier 測試夾具 — 從 applier.rs 提取（FIX-08 文件大小）。

use super::*;
use crate::database::DatabaseConfig;
use serde_json::json;
use std::sync::atomic::{AtomicBool, AtomicUsize, Ordering};
use std::sync::Mutex;

pub(super) async fn empty_pool() -> Arc<DbPool> {
    let cfg = DatabaseConfig {
        database_url: String::new(),
        ..Default::default()
    };
    Arc::new(DbPool::connect(&cfg).await)
}

/// Mock governance — configurable per-test.
/// 可逐測試配置的 mock governance。
pub(super) struct MockGov {
    pub daily_loss: f64,
    pub threshold: f64,
    pub halted: bool,
    pub known: Vec<String>,
}
impl MockGov {
    pub fn default_healthy() -> Self {
        Self {
            daily_loss: 0.0,
            threshold: 0.05,
            halted: false,
            known: vec![
                "ma_crossover".into(),
                "bb_reversion".into(),
                "bb_breakout".into(),
                "grid_trading".into(),
            ],
        }
    }
}
impl GovernanceCheck for MockGov {
    fn current_daily_loss_pct(&self) -> f64 {
        self.daily_loss
    }
    fn session_halted(&self) -> bool {
        self.halted
    }
    fn unpause_daily_loss_threshold(&self) -> f64 {
        self.threshold
    }
    fn known_strategies(&self) -> Vec<String> {
        self.known.clone()
    }
}

/// Mock IPC sink — records all calls in-memory, flags Python touches.
/// mock IPC sink — 在記憶體紀錄所有呼叫，標記任何觸及 Python 的跡象。
#[derive(Default)]
pub(super) struct MockSink {
    pub update_calls: Mutex<Vec<(String, String)>>,
    pub set_active_calls: Mutex<Vec<(String, bool)>>,
    /// Set to true if any code path attempts a forbidden Python side-effect.
    /// 若任何路��嘗試禁止的 Python 副作用則設為 true。
    pub python_touched: AtomicBool,
    pub total_calls: AtomicUsize,
}
impl StrategyIpcSink for MockSink {
    fn update_strategy_params<'a>(
        &'a self,
        strategy_name: &'a str,
        params_json: &'a str,
    ) -> IpcFuture<'a> {
        self.total_calls.fetch_add(1, Ordering::SeqCst);
        self.update_calls
            .lock()
            .unwrap()
            .push((strategy_name.into(), params_json.into()));
        Box::pin(async move { Ok(format!("params updated for {strategy_name}")) })
    }
    fn set_strategy_active<'a>(&'a self, strategy_name: &'a str, active: bool) -> IpcFuture<'a> {
        self.total_calls.fetch_add(1, Ordering::SeqCst);
        self.set_active_calls
            .lock()
            .unwrap()
            .push((strategy_name.into(), active));
        Box::pin(async move { Ok(format!("was_active=true")) })
    }
}

pub(super) fn future_expiry() -> i64 {
    (std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs()
        + 86_400) as i64
}

pub(super) fn directive(ty: DirectiveType, scope: &str, params: serde_json::Value) -> Directive {
    Directive {
        directive_type: ty,
        scope: scope.into(),
        params,
        expiry: future_expiry(),
        priority: 3,
    }
}

pub(super) async fn make_applier(
    gov: MockGov,
    sink: Option<Arc<MockSink>>,
) -> (DirectiveApplier, Arc<MockGov>, Option<Arc<MockSink>>) {
    let pool = empty_pool().await;
    let gov_arc = Arc::new(gov);
    let sink_dyn: Option<Arc<dyn StrategyIpcSink>> =
        sink.clone().map(|s| s as Arc<dyn StrategyIpcSink>);
    let applier =
        DirectiveApplier::new(gov_arc.clone() as Arc<dyn GovernanceCheck>, sink_dyn, pool);
    (applier, gov_arc, sink)
}
