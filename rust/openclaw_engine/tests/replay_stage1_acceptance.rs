//! R8 公開隔離管線驗收；固定輸入與真風控，不改既有回歸測試。
#![cfg(feature = "replay_isolated")]
use openclaw_core::{
    alpha_surface::{AlphaSourceTag, AlphaSurface},
    guardian::GuardianConfig,
};
use openclaw_engine::{
    config::RiskConfig,
    intent_processor::OrderIntent,
    replay::{
        build_isolated_pipeline,
        fixture_loader::{load_fixtures, FixtureSource},
        profile::ReplayProfile,
        risk_adapter::{ReplayPaperSnapshot, ReplayRiskAdapter},
        stage1::{ExecutionTiming, Stage1Config},
        strategy_adapter::ReplayStrategyAdapter,
        ReplayResult,
    },
    strategies::{Strategy, StrategyAction},
    tick_pipeline::TickContext,
};
use serde_json::{json, Value};
use std::collections::HashMap;

struct Scripted {
    actions: HashMap<u64, Vec<StrategyAction>>,
}
impl Strategy for Scripted {
    fn name(&self) -> &str {
        "r8_probe"
    }
    fn is_active(&self) -> bool {
        true
    }
    fn set_active(&mut self, _: bool) {}
    fn declared_alpha_sources(&self) -> &[AlphaSourceTag] {
        &[]
    }
    fn on_tick(&mut self, ctx: &TickContext<'_>, _: &AlphaSurface<'_>) -> Vec<StrategyAction> {
        self.actions.remove(&ctx.timestamp_ms).unwrap_or_default()
    }
}
fn open(symbol: &str) -> StrategyAction {
    StrategyAction::Open(serde_json::from_value::<OrderIntent>(json!({"symbol":symbol,"is_long":true,
        "qty":1.0,"confidence":0.99,"strategy":"r8_probe","order_type":"market","limit_price":null})).unwrap())
}
fn close(symbol: &str) -> StrategyAction {
    StrategyAction::Close {
        symbol: symbol.into(),
        confidence: 1.0,
        reason: "exit".into(),
    }
}
fn event(ts: u64, symbol: &str, price: f64) -> Value {
    json!({"ts_ms":ts,"symbol":symbol,"open":price,"high":1000.,"low":1.,"close":777.,"volume":100.})
}
fn run(
    rows: Vec<Value>,
    script: Vec<(u64, Vec<StrategyAction>)>,
    timing: ExecutionTiming,
) -> (ReplayResult, Value) {
    run_with_timeline(rows, script, timing, None)
}
fn run_with_timeline(
    rows: Vec<Value>,
    script: Vec<(u64, Vec<StrategyAction>)>,
    timing: ExecutionTiming,
    timeline: Option<openclaw_engine::replay::ReplayScannerTimeline>,
) -> (ReplayResult, Value) {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("fixture.json");
    std::fs::write(
        &path,
        serde_json::to_vec(&json!({"schema_version":1,"source":"r8_synthetic","events":rows}))
            .unwrap(),
    )
    .unwrap();
    let src = FixtureSource::S3Synthetic { path: path.clone() };
    let events = load_fixtures(&src).unwrap();
    let config = Stage1Config::from_fixture(&path, &events, timing, None, false).unwrap();
    let adapter = ReplayStrategyAdapter::new(
        Box::new(Scripted {
            actions: script.into_iter().collect(),
        }),
        ReplayProfile::Isolated,
    )
    .unwrap();
    let risk = ReplayRiskAdapter::new(
        ReplayProfile::Isolated,
        GuardianConfig::default(),
        RiskConfig::default(),
        0.02,
        None,
    )
    .unwrap();
    let snap = ReplayPaperSnapshot {
        balance: 10000.,
        drawdown_pct: 0.,
        positions: vec![],
        latest_price: Some(100.),
        latest_price_by_symbol: HashMap::new(),
        exposure_pct: 0.,
        correlated_exposure_pct: 0.,
        leverage: 0.,
        daily_loss_pct: 0.,
        trade_stats: None,
    };
    let mut pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "r8_test".into(),
        src.tier_label(),
        events,
    )
    .unwrap()
    .with_adapter_pipeline(adapter, risk, snap)
    .unwrap()
    .with_stage1(config)
    .unwrap();
    if let Some(timeline) = timeline {
        pipeline = pipeline.with_scanner_timeline(timeline);
    }
    pipeline.execute().unwrap();
    let meta = pipeline.stage1_metadata().unwrap_or(Value::Null);
    (pipeline.into_result(), meta)
}
#[test]
fn next_open_and_close_wait_for_same_symbol() {
    let (r, m) = run(
        vec![
            event(1, "BTCUSDT", 11.),
            event(2, "ETHUSDT", 22.),
            event(3, "BTCUSDT", 100.),
            event(4, "ETHUSDT", 33.),
            event(5, "BTCUSDT", 120.),
        ],
        vec![(1, vec![open("BTCUSDT")]), (3, vec![close("BTCUSDT")])],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills.len(), 2);
    assert!(r.fills[0].qty > 0.);
    assert_eq!(r.fills[0].price, 100. * 1.0005);
    assert_eq!(r.fills[1].price, 120. * 0.9995);
    assert_eq!(r.fills[0].effective_ts_ms, Some(3));
    assert_eq!(r.fills[1].effective_ts_ms, Some(5));
    assert_eq!(m["action_audit"][0]["signal_event_index"], 0);
    assert_eq!(m["action_audit"][0]["execution_event_index"], 2);
}
#[test]
fn eof_and_nonmarket_are_explicit_zero_records() {
    let mut limit = open("BTCUSDT");
    if let StrategyAction::Open(i) = &mut limit {
        i.order_type = "limit".into();
        i.limit_price = Some(10.);
    }
    let (r, _) = run(
        vec![event(1, "BTCUSDT", 100.), event(2, "BTCUSDT", 120.)],
        vec![(1, vec![limit]), (2, vec![open("BTCUSDT")])],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills[0].fill_status, "unsupported_nonmarket");
    assert_eq!(r.fills[1].fill_status, "expired_no_next_event");
    assert!(r.fills.iter().all(|f| f.qty == 0.));
}
#[test]
fn duplicate_pending_opens_have_one_execution_and_stable_ids() {
    let (r, m) = run(
        vec![event(1, "BTCUSDT", 100.), event(2, "BTCUSDT", 120.)],
        vec![(1, vec![open("BTCUSDT"), open("BTCUSDT")])],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills.iter().filter(|f| f.qty > 0.).count(), 1);
    assert_eq!(r.fills[0].fill_status, "pending_open_exists");
    assert_eq!(m["action_audit"][0]["action_id"], "0:0");
    assert_eq!(m["action_audit"][1]["action_id"], "0:1");
}
#[test]
fn size_down_scales_accepted_quantity_and_close_uses_actual_position() {
    let rows = vec![
        event(1, "BTCUSDT", 100.),
        event(2, "BTCUSDT", 100.),
        event(3, "BTCUSDT", 120.),
    ];
    let script = vec![(1, vec![open("BTCUSDT")]), (2, vec![close("BTCUSDT")])];
    let (base, _) = run(
        rows.clone(),
        script.clone(),
        ExecutionTiming::NextSymbolOpen,
    );
    let mut scaled = rows;
    scaled[0]["selector_decision"] = json!({"action":"SIZE_DOWN","size_factor":0.25});
    scaled[1]["selector_decision"] = json!({"action":"VETO"});
    let (r, m) = run(scaled, script, ExecutionTiming::NextSymbolOpen);
    assert!(r.fills[0].qty > 0.);
    assert!((r.fills[0].qty - base.fills[0].qty * 0.25).abs() < 1e-12);
    assert_eq!(r.fills[1].qty, r.fills[0].qty);
    assert_eq!(m["action_audit"][1]["selector_applied"], false);
}
#[test]
fn veto_does_not_reserve_pending_slot() {
    let mut first = event(1, "BTCUSDT", 100.);
    first["selector_decision"] = json!({"action":"VETO"});
    let (r, _) = run(
        vec![first, event(2, "BTCUSDT", 110.), event(3, "BTCUSDT", 120.)],
        vec![(1, vec![open("BTCUSDT")]), (2, vec![open("BTCUSDT")])],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills[0].fill_status, "selector_veto");
    assert!(r.fills[1].qty > 0.);
    assert_eq!(r.fills[1].ts_ms, 3);
}
#[test]
fn next_close_and_volume_do_not_influence_accepted_entry() {
    let rows = vec![event(1, "BTCUSDT", 100.), event(2, "BTCUSDT", 10000.)];
    let script = vec![(1, vec![open("BTCUSDT")])];
    let (base, _) = run(
        rows.clone(),
        script.clone(),
        ExecutionTiming::NextSymbolOpen,
    );
    let mut changed = rows;
    changed[1]["close"] = json!(1.);
    changed[1]["volume"] = json!(1e15);
    changed[1]["turnover_24h"] = json!(1e15);
    let (r, _) = run(changed, script, ExecutionTiming::NextSymbolOpen);
    assert_eq!(r.fills, base.fills);
    assert!(r.fills[0].qty <= 10000. * 0.02 / 10000.);
}
fn config_result(rows: Vec<Value>, latency: Option<u64>) -> bool {
    let dir = tempfile::tempdir().unwrap();
    let path = dir.path().join("fixture.json");
    std::fs::write(
        &path,
        serde_json::to_vec(&json!({"schema_version":1,"source":"r8_synthetic","events":rows}))
            .unwrap(),
    )
    .unwrap();
    let events = load_fixtures(&FixtureSource::S3Synthetic { path: path.clone() }).unwrap();
    Stage1Config::from_fixture(
        &path,
        &events,
        ExecutionTiming::NextSymbolOpen,
        latency,
        false,
    )
    .is_ok()
}
#[test]
fn invalid_selector_coefficients_fail_closed() {
    for selector in [
        json!({"action":"SIZE_DOWN"}),
        json!({"action":"SIZE_DOWN","size_factor":0}),
        json!({"action":"SIZE_DOWN","size_factor":1.1}),
        json!({"action":"SIZE_DOWN","size_factor":-1}),
        json!({"action":"NO_OP","size_factor":0.5}),
        json!({"action":"OPEN"}),
    ] {
        let mut row = event(1, "BTCUSDT", 100.);
        row["selector_decision"] = selector;
        assert!(!config_result(vec![row], None));
    }
}
#[test]
fn quote_time_latency_and_order_require_explicit_contract() {
    let mut row = event(1, "BTCUSDT", 100.);
    row["best_bid"] = json!(99.);
    row["best_ask"] = json!(101.);
    assert!(!config_result(vec![row.clone()], None));
    row["execution_quote_at_open"] = json!(true);
    assert!(config_result(vec![row.clone()], Some(0)));
    assert!(!config_result(vec![row.clone()], Some(1)));
    assert!(!config_result(vec![row.clone(), row], None));
}
#[test]
fn next_event_bbo_anchors_execution() {
    let mut second = event(2, "BTCUSDT", 100.);
    second["best_bid"] = json!(105.);
    second["best_ask"] = json!(106.);
    second["execution_quote_at_open"] = json!(true);
    let (r, _) = run(
        vec![event(1, "BTCUSDT", 10.), second],
        vec![(1, vec![open("BTCUSDT")])],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills[0].price, 106. * 1.0005);
}
#[test]
fn reducing_open_bypasses_selector_and_cannot_reverse() {
    let mut second = event(2, "BTCUSDT", 100.);
    second["selector_decision"] = json!({"action":"VETO"});
    let mut reduce = open("BTCUSDT");
    if let StrategyAction::Open(i) = &mut reduce {
        i.is_long = false;
        i.qty = 100.;
    }
    let (r, m) = run(
        vec![event(1, "BTCUSDT", 100.), second, event(3, "BTCUSDT", 100.)],
        vec![
            (1, vec![open("BTCUSDT")]),
            (2, vec![reduce]),
            (3, vec![close("BTCUSDT")]),
        ],
        ExecutionTiming::CurrentBarClose,
    );
    assert!(r.fills[0].qty > 0.);
    assert_eq!(r.fills[1].qty, r.fills[0].qty);
    assert_eq!(r.fills[2].qty, 0.);
    assert_eq!(m["action_audit"][1]["selector_applied"], false);
}
#[test]
fn selector_audit_is_joined_into_trace_and_fill() {
    let mut first = event(1, "BTCUSDT", 100.);
    first["selector_decision"] = json!({"action":"NO_OP"});
    let (r, m) = run(
        vec![first],
        vec![(1, vec![open("BTCUSDT")])],
        ExecutionTiming::CurrentBarClose,
    );
    let dir = tempfile::tempdir().unwrap();
    let path = openclaw_engine::replay::write_replay_report(dir.path(), &r).unwrap();
    openclaw_engine::replay::stage1::extend_report(&path, Some(m), None, None).unwrap();
    let v: Value = serde_json::from_slice(&std::fs::read(path).unwrap()).unwrap();
    assert_eq!(v["result"]["fills"][0]["replay_audit"]["action_id"], "0:0");
    assert_eq!(
        v["result"]["decision_traces"][0]["actions_emitted"][0]["replay_audit"]["action_id"],
        "0:0"
    );
}

#[test]
fn duplicate_close_cannot_close_a_reopened_position() {
    let (r, _) = run(
        vec![
            event(1, "BTCUSDT", 100.),
            event(2, "BTCUSDT", 100.),
            event(3, "BTCUSDT", 100.),
        ],
        vec![
            (1, vec![open("BTCUSDT")]),
            (2, vec![close("BTCUSDT"), open("BTCUSDT"), close("BTCUSDT")]),
        ],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills.len(), 4);
    assert!(r.fills[2].qty > 0.);
    assert_eq!(r.fills[3].fill_status, "reduction_position_changed");
}

#[test]
fn execution_risk_uses_balance_after_actual_close() {
    let (r, _) = run(
        vec![
            event(1, "BTCUSDT", 10000.),
            event(2, "BTCUSDT", 10000.),
            event(3, "BTCUSDT", 5000.),
            event(4, "BTCUSDT", 10000.),
        ],
        vec![
            (1, vec![open("BTCUSDT")]),
            (2, vec![close("BTCUSDT")]),
            (3, vec![open("BTCUSDT")]),
        ],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills.len(), 3);
    let balance = 10000. - r.fills[0].fee + (r.fills[1].price - r.fills[0].price) * r.fills[0].qty
        - r.fills[1].fee;
    assert!((r.fills[2].qty - balance * 0.02 / 10000.).abs() < 1e-12);
    assert!(r.fills[2].qty < r.fills[0].qty);
}
#[test]
fn partial_close_preserves_actual_remainder_without_retry() {
    let mut last = event(3, "BTCUSDT", 100.);
    last["bid_size"] = json!(1.);
    last["execution_quote_at_open"] = json!(true);
    let (r, _) = run(
        vec![
            event(1, "BTCUSDT", 100.),
            event(2, "BTCUSDT", 100.),
            last,
            event(4, "BTCUSDT", 100.),
        ],
        vec![(1, vec![open("BTCUSDT")]), (2, vec![close("BTCUSDT")])],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills.len(), 2);
    assert_eq!(r.fills[0].qty, 1.);
    assert_eq!(r.fills[1].qty, 0.2);
}
#[test]
fn size_down_cannot_allow_a_risk_rejection() {
    let mut first = event(1, "BTCUSDT", 100.);
    first["selector_decision"] = json!({"action":"SIZE_DOWN","size_factor":0.5});
    let mut invalid = open("BTCUSDT");
    if let StrategyAction::Open(i) = &mut invalid {
        i.qty = 0.;
    }
    let (r, m) = run(
        vec![first, event(2, "BTCUSDT", 100.)],
        vec![(1, vec![invalid])],
        ExecutionTiming::NextSymbolOpen,
    );
    assert_eq!(r.fills[0].qty, 0.);
    assert_eq!(r.fills[0].fill_status, "rejected");
    assert!(m["action_audit"][0]["baseline_accepted_qty"].is_null());
}

#[test]
fn pending_fills_before_scanner_can_skip_an_inactive_event() {
    use openclaw_engine::{replay::ReplayScannerTimeline, scanner::types::ScanResult};
    let cycles = [(1, vec!["BTCUSDT".to_owned()]), (2, vec![])]
        .into_iter()
        .map(|(ts, active)| ScanResult {
            scan_ts_ms: ts,
            scan_id: ts.to_string(),
            active_symbols: active,
            added: vec![],
            removed: vec![],
            candidates: vec![],
            opportunity_decays: vec![],
            rejected_count: 0,
            scan_duration_ms: 0,
        })
        .collect();
    let timeline = ReplayScannerTimeline::from_scan_results(1, cycles).unwrap();
    let (r, _) = run_with_timeline(
        vec![event(1, "BTCUSDT", 100.), event(2, "BTCUSDT", 110.)],
        vec![(1, vec![open("BTCUSDT")])],
        ExecutionTiming::NextSymbolOpen,
        Some(timeline),
    );
    assert!(r.fills[0].qty > 0.);
    assert_eq!(r.fills[0].ts_ms, 2);
}
