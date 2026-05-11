use super::*;
// R0-T0 Sprint C R6 W2: helpers moved to crate::replay::apply_fill.
// Import them at the test module level so existing call sites
// (replay_fee_rate_for_tif / replay_slippage_bps_for_tif /
// apply_slippage_to_price / DEFAULT_*_FEE_RATE) compile unchanged.
// R0-T0 Sprint C R6 W2：4 helper 抽至 `crate::replay::apply_fill`，
// 在 tests 模組 import，使既有 test 呼叫 byte-equal 不變。
use crate::replay::apply_fill::{
    apply_slippage_to_price, bbo_anchor_taker_reference_price, replay_fee_rate_for_tif,
    replay_slippage_bps_for_tif, DEFAULT_MAKER_FEE_RATE, DEFAULT_TAKER_FEE_RATE,
};

fn synthetic_events() -> Vec<MarketEvent> {
    vec![
        MarketEvent {
            ts_ms: 1,
            symbol: "BTCUSDT".into(),
            open: 100.0,
            high: 101.0,
            low: 99.0,
            close: 100.0,
            volume: 1.0,
            turnover: None,
            turnover_24h: None,
            best_bid: None,
            best_ask: None,
            bid_size: None,
            ask_size: None,
            bid_depth_5: None,
            ask_depth_5: None,
            spread_bps: None,
            microstructure_source: None,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            tick_size: None,
            h0_allowed: None,
            indicators: None,
            signals: Vec::new(),
        },
        MarketEvent {
            ts_ms: 2,
            symbol: "BTCUSDT".into(),
            open: 100.0,
            high: 105.0,
            low: 100.0,
            close: 105.0,
            volume: 1.0,
            turnover: None,
            turnover_24h: None,
            best_bid: None,
            best_ask: None,
            bid_size: None,
            ask_size: None,
            bid_depth_5: None,
            ask_depth_5: None,
            spread_bps: None,
            microstructure_source: None,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            tick_size: None,
            h0_allowed: None,
            indicators: None,
            signals: Vec::new(),
        },
        MarketEvent {
            ts_ms: 3,
            symbol: "ETHUSDT".into(),
            open: 50.0,
            high: 51.0,
            low: 49.0,
            close: 50.5,
            volume: 5.0,
            turnover: None,
            turnover_24h: None,
            best_bid: None,
            best_ask: None,
            bid_size: None,
            ask_size: None,
            bid_depth_5: None,
            ask_depth_5: None,
            spread_bps: None,
            microstructure_source: None,
            funding_rate: None,
            index_price: None,
            open_interest: None,
            tick_size: None,
            h0_allowed: None,
            indicators: None,
            signals: Vec::new(),
        },
    ]
}

#[test]
fn build_rejects_non_isolated() {
    // Sprint B2 R5-T3: `unwrap_err()` would require IsolatedPipeline:Debug;
    // since it now holds Option<Box<dyn Strategy>> via ReplayStrategyAdapter
    // (Box<dyn Strategy> is not Debug), use explicit match like the sibling
    // adapter modules.
    // Sprint B2 R5-T3：`unwrap_err()` 需 IsolatedPipeline:Debug；因經
    // ReplayStrategyAdapter 持 Option<Box<dyn Strategy>>（不可 Debug），
    // 改用顯式 match 與 sibling adapter module 對齊。
    match build_isolated_pipeline(
        ReplayProfile::Live,
        "exp_1".into(),
        "S3",
        synthetic_events(),
    ) {
        Err(ReplayError::NonIsolatedProfile { found }) => {
            assert_eq!(found, ReplayProfile::Live);
        }
        Ok(_) => panic!("expected NonIsolatedProfile rejection"),
        Err(other) => panic!("expected NonIsolatedProfile, got {:?}", other),
    }
}

#[test]
fn execute_completed_walks_fixtures() {
    let mut p = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_2".into(),
        "S3",
        synthetic_events(),
    )
    .unwrap();
    p.execute().unwrap();
    let r = p.into_result();
    assert_eq!(r.status, ReplayStatus::Completed);
    // 2 distinct symbols => 2 entry fills emitted.
    assert_eq!(r.fills.len(), 2);
    // BTCUSDT entry at 100 then mark to 105 → +5 USDT delta on balance.
    assert!((r.pnl_summary.net_pnl - 5.0).abs() < 1e-9);
    assert_eq!(r.execution_confidence, "none");
    assert_eq!(r.pnl_summary.fills_emitted, 2);
    assert!(r.diagnostics.guard_enforce_runtime_calls >= 3);
    assert_eq!(r.diagnostics.abort_reason, None);
}

#[test]
fn evidence_source_tier_maps_correctly() {
    let mut p = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_3".into(),
        "S2",
        synthetic_events(),
    )
    .unwrap();
    p.execute().unwrap();
    let r = p.into_result();
    for f in &r.fills {
        assert_eq!(f.evidence_source_tier, "calibrated_replay");
    }

    let mut p3 = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_4".into(),
        "S3",
        synthetic_events(),
    )
    .unwrap();
    p3.execute().unwrap();
    let r3 = p3.into_result();
    for f in &r3.fills {
        assert_eq!(f.evidence_source_tier, "synthetic_replay");
    }
}

#[test]
fn status_label_matches_variant() {
    assert_eq!(ReplayStatus::Completed.label(), "completed");
    assert_eq!(
        ReplayStatus::AbortedForbidden { action: "x".into() }.label(),
        "aborted_forbidden"
    );
    assert_eq!(
        ReplayStatus::AbortedFixtureExhausted.label(),
        "aborted_fixture_exhausted"
    );
}

// ─── Sprint B2 R5-T3 inline tests ───
// ─── Sprint B2 R5-T3 inline 測試 ───
//
// These cover the new adapter wire-up + fail-loud snapshot construction.
// Acceptance-level coverage (cross-language parameter delta, full
// baseline-vs-candidate replay) lives in `tests/replay/test_replay_*_smoke.rs`
// (R5-T7).
//
// 涵蓋新 adapter 接線 + fail-loud snapshot 構造。Acceptance 層覆蓋
// （跨語言 parameter delta、完整 baseline-vs-candidate replay）在
// R5-T7 `tests/replay/test_replay_*_smoke.rs`。

use crate::intent_processor::OrderIntent;
use crate::ml::kelly_sizer::KellyConfig;
use crate::strategies::{Strategy, StrategyAction};
use openclaw_core::guardian::GuardianConfig;

/// Stub strategy that emits one Open per call until `stop_after` ticks.
/// Stub 策略：每 tick 發一個 Open 直到 `stop_after`。
struct OneShotStub {
    emitted: usize,
    stop_after: usize,
}

impl Strategy for OneShotStub {
    fn name(&self) -> &str {
        "r5t3_stub"
    }
    fn is_active(&self) -> bool {
        true
    }
    fn set_active(&mut self, _: bool) {}
    fn declared_alpha_sources(&self) -> &[openclaw_core::alpha_surface::AlphaSourceTag] {
        const TAGS: &[openclaw_core::alpha_surface::AlphaSourceTag] =
            &[openclaw_core::alpha_surface::AlphaSourceTag::Ta1m];
        TAGS
    }
    fn on_tick(
        &mut self,
        ctx: &crate::tick_pipeline::TickContext<'_>,
        _surface: &openclaw_core::alpha_surface::AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        if self.emitted >= self.stop_after {
            return Vec::new();
        }
        self.emitted += 1;
        vec![StrategyAction::Open(OrderIntent {
            symbol: ctx.symbol.to_string(),
            is_long: true,
            qty: 0.01,
            confidence: 0.5,
            strategy: "r5t3_stub".to_string(),
            order_type: "market".to_string(),
            limit_price: None,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: None,
            maker_timeout_ms: None,
        })]
    }
}

/// Stub strategy that closes a seeded replay position when its symbol tick
/// is still delivered after scanner timeline removal.
/// Stub 策略：scanner timeline 移除後若既有倉位 tick 仍送達，即發平倉。
struct CloseOnTickStub {
    target_symbol: String,
    emitted: bool,
}

impl Strategy for CloseOnTickStub {
    fn name(&self) -> &str {
        "mag023_close_stub"
    }
    fn is_active(&self) -> bool {
        true
    }
    fn set_active(&mut self, _: bool) {}
    fn declared_alpha_sources(&self) -> &[openclaw_core::alpha_surface::AlphaSourceTag] {
        const TAGS: &[openclaw_core::alpha_surface::AlphaSourceTag] =
            &[openclaw_core::alpha_surface::AlphaSourceTag::Ta1m];
        TAGS
    }
    fn on_tick(
        &mut self,
        ctx: &crate::tick_pipeline::TickContext<'_>,
        _surface: &openclaw_core::alpha_surface::AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        if self.emitted || ctx.symbol != self.target_symbol {
            return Vec::new();
        }
        self.emitted = true;
        vec![StrategyAction::Close {
            symbol: ctx.symbol.to_string(),
            confidence: 0.95,
            reason: "mag023_replay_exit_after_scanner_drop".to_string(),
        }]
    }
}

fn make_snapshot_seed(
    balance: f64,
    latest_price: Option<f64>,
    positions: Vec<crate::replay::risk_adapter::ReplayPosition>,
) -> crate::replay::risk_adapter::ReplayPaperSnapshot {
    crate::replay::risk_adapter::ReplayPaperSnapshot {
        balance,
        drawdown_pct: 0.0,
        positions,
        latest_price,
        exposure_pct: 0.0,
        correlated_exposure_pct: 0.0,
        leverage: 0.0,
        daily_loss_pct: 0.0,
        trade_stats: None,
    }
}

fn make_adapters(
    kelly: Option<KellyConfig>,
) -> (
    crate::replay::strategy_adapter::ReplayStrategyAdapter,
    crate::replay::risk_adapter::ReplayRiskAdapter,
) {
    let strat = Box::new(OneShotStub {
        emitted: 0,
        stop_after: 1,
    });
    let strategy_adapter =
        crate::replay::strategy_adapter::ReplayStrategyAdapter::new(strat, ReplayProfile::Isolated)
            .expect("Isolated accepts");
    let risk_adapter = crate::replay::risk_adapter::ReplayRiskAdapter::new(
        ReplayProfile::Isolated,
        GuardianConfig::default(),
        crate::config::RiskConfig::default(),
        0.02,
        kelly,
    )
    .expect("risk adapter Isolated accepts");
    (strategy_adapter, risk_adapter)
}

fn scanner_guard_event(symbol: &str, ts_ms: i64, close: f64) -> MarketEvent {
    MarketEvent {
        ts_ms,
        symbol: symbol.to_string(),
        open: close,
        high: close * 1.01,
        low: close * 0.99,
        close,
        volume: 1.0,
        turnover: None,
        turnover_24h: None,
        best_bid: None,
        best_ask: None,
        bid_size: None,
        ask_size: None,
        bid_depth_5: None,
        ask_depth_5: None,
        spread_bps: None,
        microstructure_source: None,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        tick_size: None,
        h0_allowed: None,
        indicators: None,
        signals: Vec::new(),
    }
}

#[test]
fn adapter_pipeline_rejects_nan_balance_snapshot() {
    // F-3 LOW finding fix: NaN balance must fail loud at attach time.
    // F-3 LOW finding fix：NaN balance 必須在 attach 時 fail loud。
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_r5t3_nan".into(),
        "S3",
        synthetic_events(),
    )
    .expect("baseline build OK");
    let (strategy_adapter, risk_adapter) = make_adapters(None);
    let snapshot = make_snapshot_seed(f64::NAN, Some(100.0), Vec::new());
    match pipeline.with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot) {
        Err(ReplayError::InvalidSnapshot { reason }) => {
            assert!(
                reason.contains("NaN") || reason.contains("Inf") || reason.contains("finite"),
                "reason should mention finite/NaN, got: {}",
                reason
            );
        }
        Ok(_) => panic!("expected InvalidSnapshot rejection on NaN balance"),
        Err(other) => panic!("expected InvalidSnapshot, got {:?}", other),
    }
}

#[test]
fn adapter_pipeline_rejects_empty_anchor_snapshot() {
    // F-3 LOW finding fix part 2: empty latest_price + empty positions
    // would silent-bypass Gate 2.6 P1 cap; must fail loud at attach.
    // F-3 LOW finding fix part 2：空 latest_price + 空 positions 會
    // silent-bypass Gate 2.6 P1 cap；必須在 attach 時 fail loud。
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_r5t3_empty".into(),
        "S3",
        synthetic_events(),
    )
    .expect("baseline build OK");
    let (strategy_adapter, risk_adapter) = make_adapters(None);
    let snapshot = make_snapshot_seed(10_000.0, None, Vec::new());
    match pipeline.with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot) {
        Err(ReplayError::InvalidSnapshot { reason }) => {
            assert!(
                reason.contains("latest_price") && reason.contains("empty"),
                "reason should mention latest_price + empty, got: {}",
                reason
            );
        }
        Ok(_) => panic!("expected InvalidSnapshot rejection on empty anchor"),
        Err(other) => panic!("expected InvalidSnapshot, got {:?}", other),
    }
}

#[test]
fn adapter_pipeline_walks_strategy_then_risk_emits_real_fill() {
    // R5-T3 acceptance: with strategy + risk adapter wired, execute
    // produces a real fill via Strategy::on_tick → 6-Gate risk evaluate
    // → apply_fill_open. decision_traces captures the strategy's Open.
    // R5-T3 acceptance：接 strategy + risk adapter 後，execute 經
    // Strategy::on_tick → 6-Gate 風控 evaluate → apply_fill_open 產真 fill。
    // decision_traces 捕獲策略的 Open。
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_r5t3_happy".into(),
        "S3",
        synthetic_events(),
    )
    .expect("baseline build OK");
    let (strategy_adapter, risk_adapter) = make_adapters(None);
    let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes");
    wired.execute().expect("execute completes");
    let result = wired.into_result();
    assert_eq!(result.status, ReplayStatus::Completed);
    assert_eq!(result.execution_confidence, "none");
    // OneShotStub emits 1 Open on first tick (BTCUSDT@1) — risk gates
    // accept (qty=0.01 < P1 cap 2.0 at price=100 balance=10_000) → 1 fill.
    // OneShotStub 第一 tick 發 1 Open（BTCUSDT@1）— 風控通過
    // （qty=0.01 < P1 cap 2.0，price=100 balance=10000）→ 1 fill。
    assert_eq!(result.fills.len(), 1, "expected 1 accepted fill");
    let f0 = &result.fills[0];
    assert_eq!(f0.symbol, "BTCUSDT");
    assert_eq!(f0.side, "long");
    assert!((f0.qty - 0.01).abs() < 1e-9);
    // Decision trace populated (strategy emitted 1 Open).
    // 決策追蹤填入（策略發 1 Open）。
    assert_eq!(result.decision_traces.len(), 1);
    assert_eq!(result.decision_traces[0].symbol, "BTCUSDT");
    assert_eq!(result.decision_traces[0].strategy_name, "r5t3_stub");
}

#[test]
fn adapter_pipeline_scanner_timeline_gates_inactive_entries() {
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_ref21_scanner_gate".into(),
        "S3",
        synthetic_events(),
    )
    .expect("baseline build OK");
    let (strategy_adapter, risk_adapter) = make_adapters(None);
    let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
    let scan = crate::scanner::types::ScanResult {
        scan_ts_ms: 1,
        scan_id: "ref21_test_scan".to_string(),
        active_symbols: vec!["ETHUSDT".to_string()],
        added: vec!["ETHUSDT".to_string()],
        removed: Vec::new(),
        candidates: Vec::new(),
        opportunity_decays: Vec::new(),
        rejected_count: 0,
        scan_duration_ms: 0,
    };
    let timeline =
        ReplayScannerTimeline::from_scan_results(60_000, vec![scan]).expect("valid timeline");
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes")
        .with_scanner_timeline(timeline);

    wired.execute().expect("execute completes");
    let result = wired.into_result();

    assert_eq!(result.status, ReplayStatus::Completed);
    assert_eq!(result.fills.len(), 1);
    assert_eq!(result.fills[0].symbol, "ETHUSDT");
    assert_eq!(result.diagnostics.scanner_timeline_cycles, 1);
    assert_eq!(result.diagnostics.scanner_timeline_skipped_events, 2);
}

#[test]
fn adapter_pipeline_preserves_open_position_tick_after_scanner_drop() {
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_mag023_scanner_drop_exit".into(),
        "S3",
        vec![
            scanner_guard_event("SOLUSDT", 1, 20.0),
            scanner_guard_event("BTCUSDT", 2, 110.0),
        ],
    )
    .expect("baseline build OK");
    let strategy_adapter = crate::replay::strategy_adapter::ReplayStrategyAdapter::new(
        Box::new(CloseOnTickStub {
            target_symbol: "BTCUSDT".to_string(),
            emitted: false,
        }),
        ReplayProfile::Isolated,
    )
    .expect("Isolated accepts");
    let risk_adapter = crate::replay::risk_adapter::ReplayRiskAdapter::new(
        ReplayProfile::Isolated,
        GuardianConfig::default(),
        crate::config::RiskConfig::default(),
        0.02,
        None,
    )
    .expect("risk adapter Isolated accepts");
    let snapshot = make_snapshot_seed(
        10_000.0,
        None,
        vec![crate::replay::risk_adapter::ReplayPosition {
            symbol: "BTCUSDT".to_string(),
            is_long: true,
            qty: 1.0,
            entry_price: 100.0,
            owner_strategy: String::new(),
        }],
    );
    let scan = crate::scanner::types::ScanResult {
        scan_ts_ms: 1,
        scan_id: "mag023_drop_scan".to_string(),
        active_symbols: vec!["ETHUSDT".to_string()],
        added: vec!["ETHUSDT".to_string()],
        removed: vec!["BTCUSDT".to_string()],
        candidates: Vec::new(),
        opportunity_decays: Vec::new(),
        rejected_count: 0,
        scan_duration_ms: 0,
    };
    let timeline =
        ReplayScannerTimeline::from_scan_results(60_000, vec![scan]).expect("valid timeline");
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes")
        .with_scanner_timeline(timeline);

    wired.execute().expect("execute completes");
    let result = wired.into_result();

    assert_eq!(result.status, ReplayStatus::Completed);
    assert_eq!(result.fills.len(), 1);
    assert_eq!(result.fills[0].symbol, "BTCUSDT");
    assert_eq!(result.fills[0].side, "short");
    assert!(
        result.pnl_summary.net_pnl > 9.0,
        "close after scanner drop should realise the seeded position PnL, got {}",
        result.pnl_summary.net_pnl
    );
    assert_eq!(result.diagnostics.scanner_timeline_cycles, 1);
    assert_eq!(result.diagnostics.scanner_timeline_skipped_events, 1);
    assert!(
        result
            .diagnostics
            .last_action_label
            .contains("close:BTCUSDT"),
        "last_action should record close, got {}",
        result.diagnostics.last_action_label
    );
}

#[test]
fn adapter_pipeline_records_ghost_fill_on_risk_reject() {
    // R5-T3 acceptance + PA §6.1: rejected intent records qty=0 ghost fill.
    // Construct snapshot with existing same-direction position to trigger
    // Gate 1.5 (DuplicatePosition reject). Use only 1 event to keep the
    // last_action_label deterministic at the rejection action.
    // R5-T3 acceptance + PA §6.1：被拒 intent 記 qty=0 ghost fill。
    // 構造同向倉以觸 Gate 1.5（DuplicatePosition）。僅用 1 event 使
    // last_action_label 確定停在 reject。
    let single_event = vec![MarketEvent {
        ts_ms: 1,
        symbol: "BTCUSDT".into(),
        open: 100.0,
        high: 101.0,
        low: 99.0,
        close: 100.0,
        volume: 1.0,
        turnover: None,
        turnover_24h: None,
        best_bid: None,
        best_ask: None,
        bid_size: None,
        ask_size: None,
        bid_depth_5: None,
        ask_depth_5: None,
        spread_bps: None,
        microstructure_source: None,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        tick_size: None,
        h0_allowed: None,
        indicators: None,
        signals: Vec::new(),
    }];
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_r5t3_ghost".into(),
        "S3",
        single_event,
    )
    .expect("baseline build OK");
    let (strategy_adapter, risk_adapter) = make_adapters(None);
    let snapshot = make_snapshot_seed(
        10_000.0,
        Some(100.0),
        vec![crate::replay::risk_adapter::ReplayPosition {
            symbol: "BTCUSDT".into(),
            is_long: true, // same direction as stub
            qty: 0.5,
            entry_price: 100.0,
            owner_strategy: String::new(),
        }],
    );
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes");
    wired.execute().expect("execute completes");
    let result = wired.into_result();
    // Ghost row recorded with qty=0.
    // Ghost row 紀錄 qty=0。
    let ghost = result
        .fills
        .iter()
        .find(|f| f.qty == 0.0 && f.symbol == "BTCUSDT")
        .expect("expected ghost fill on Gate 1.5 reject");
    assert_eq!(ghost.side, "long");
    assert!(
        result
            .diagnostics
            .last_action_label
            .contains("reject:BTCUSDT:1.5_dup"),
        "last_action should record 1.5_dup gate, got: {}",
        result.diagnostics.last_action_label
    );
}

// ─── Sprint C R6-T1 + R6-T2 unit tests / R6-T1 + R6-T2 單元測試 ───
// Dispatch §5 6 cases + 3 cross-checks (PostOnly path / synthetic walker
// backward compat / ghost row counterfactual). Helpers tested directly;
// SimulatedFill end-to-end via TifStub.
// Dispatch §5 6 case + 3 交叉驗證（PostOnly path / synthetic walker
// 向後兼容 / ghost row counterfactual）。Helper 直測；end-to-end 用 TifStub。

use crate::order_manager::TimeInForce;

/// Stub strategy emitting one Open with caller-controlled TimeInForce.
/// Stub 策略：發一筆 caller 指定 TimeInForce 的 Open。
struct TifStub {
    emitted: bool,
    tif: Option<TimeInForce>,
    is_long: bool,
    limit_price: Option<f64>,
}

impl Strategy for TifStub {
    fn name(&self) -> &str {
        "r6t1t2_stub"
    }
    fn is_active(&self) -> bool {
        true
    }
    fn set_active(&mut self, _: bool) {}
    fn declared_alpha_sources(&self) -> &[openclaw_core::alpha_surface::AlphaSourceTag] {
        const TAGS: &[openclaw_core::alpha_surface::AlphaSourceTag] =
            &[openclaw_core::alpha_surface::AlphaSourceTag::Ta1m];
        TAGS
    }
    fn on_tick(
        &mut self,
        ctx: &crate::tick_pipeline::TickContext<'_>,
        _surface: &openclaw_core::alpha_surface::AlphaSurface<'_>,
    ) -> Vec<StrategyAction> {
        if self.emitted {
            return Vec::new();
        }
        self.emitted = true;
        vec![StrategyAction::Open(OrderIntent {
            symbol: ctx.symbol.to_string(),
            is_long: self.is_long,
            qty: 0.01,
            confidence: 0.5,
            strategy: "r6t1t2_stub".to_string(),
            order_type: if self.limit_price.is_some() {
                "limit".to_string()
            } else {
                "market".to_string()
            },
            limit_price: self.limit_price,
            confluence_score: None,
            persistence_elapsed_ms: None,
            time_in_force: self.tif,
            maker_timeout_ms: None,
        })]
    }
}

fn make_tif_adapters(
    tif: Option<TimeInForce>,
    is_long: bool,
    limit_price: Option<f64>,
) -> (
    crate::replay::strategy_adapter::ReplayStrategyAdapter,
    crate::replay::risk_adapter::ReplayRiskAdapter,
) {
    let strat = Box::new(TifStub {
        emitted: false,
        tif,
        is_long,
        limit_price,
    });
    let strategy_adapter =
        crate::replay::strategy_adapter::ReplayStrategyAdapter::new(strat, ReplayProfile::Isolated)
            .expect("Isolated accepts");
    let risk_adapter = crate::replay::risk_adapter::ReplayRiskAdapter::new(
        ReplayProfile::Isolated,
        GuardianConfig::default(),
        crate::config::RiskConfig::default(),
        0.02,
        None,
    )
    .expect("risk adapter Isolated accepts");
    (strategy_adapter, risk_adapter)
}

/// Sprint C R6-T1+T2 — minimal 1-event fixture builder.
/// Sprint C R6-T1+T2 — 最小 1-event fixture 構造器。
fn r6_single_event() -> Vec<MarketEvent> {
    vec![MarketEvent {
        ts_ms: 1,
        symbol: "BTCUSDT".into(),
        open: 100.0,
        high: 101.0,
        low: 99.0,
        close: 100.0,
        volume: 1.0,
        turnover: None,
        turnover_24h: None,
        best_bid: None,
        best_ask: None,
        bid_size: None,
        ask_size: None,
        bid_depth_5: None,
        ask_depth_5: None,
        spread_bps: None,
        microstructure_source: None,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        tick_size: None,
        h0_allowed: None,
        indicators: None,
        signals: Vec::new(),
    }]
}

fn r6_single_event_with_bbo(best_bid: f64, best_ask: f64) -> Vec<MarketEvent> {
    let mut events = r6_single_event();
    events[0].best_bid = Some(best_bid);
    events[0].best_ask = Some(best_ask);
    events[0]
        .microstructure_source
        .replace("market.market_tickers".to_string());
    events
}

// ─── Helper unit tests / 輔助函式單元測試 ───

#[test]
fn test_apply_fill_postonly_uses_maker_fee() {
    // R6-T1: PostOnly TIF + no AM seeded → DEFAULT_MAKER_FEE_RATE + 'maker'.
    // R6-T1：PostOnly TIF + 無 AM → DEFAULT_MAKER_FEE_RATE + 'maker'。
    let (rate, role) = replay_fee_rate_for_tif(None, "BTCUSDT", Some(TimeInForce::PostOnly));
    assert!(
        (rate - DEFAULT_MAKER_FEE_RATE).abs() < 1e-12,
        "maker rate, got {}",
        rate
    );
    assert_eq!(role, "maker", "PostOnly → 'maker' role");
}

#[test]
fn test_apply_fill_non_postonly_uses_taker_fee() {
    // R6-T1: non-PostOnly TIF (None / GTC / IOC / FOK) → taker + 'taker'.
    // R6-T1：非 PostOnly（None / GTC / IOC / FOK）→ taker + 'taker'。
    for (tif, label) in [
        (None, "None"),
        (Some(TimeInForce::GTC), "GTC"),
        (Some(TimeInForce::IOC), "IOC"),
        (Some(TimeInForce::FOK), "FOK"),
    ] {
        let (rate, role) = replay_fee_rate_for_tif(None, "BTCUSDT", tif);
        assert!(
            (rate - DEFAULT_TAKER_FEE_RATE).abs() < 1e-12,
            "{} taker, got {}",
            label,
            rate
        );
        assert_eq!(role, "taker", "{} → 'taker'", label);
    }
}

#[test]
fn test_apply_fill_long_slippage_increases_fill_price() {
    // R6-T2: buy (is_long=true) at $1B tier → +1.0 bps signed →
    // 100.0 × (1 + 1/10000) = 100.01.
    // R6-T2：買 + $1B tier → +1.0 bps → 100.0 × (1 + 1/10000) = 100.01。
    let cfg = crate::config::SlippageConfig::default();
    let bps = replay_slippage_bps_for_tif(&cfg, None, 2_000_000_000.0, true);
    assert!(bps > 0.0, "buy → positive bps, got {}", bps);
    let fill = apply_slippage_to_price(100.0, bps);
    assert!(fill > 100.0, "buy → fill > ref, got {}", fill);
    assert!((bps - 1.0).abs() < 1e-9, "$1B tier 1.0 bps, got {}", bps);
    assert!((fill - 100.01).abs() < 1e-9, "fill=100.01, got {}", fill);
}

#[test]
fn test_apply_fill_short_slippage_decreases_fill_price() {
    // R6-T2: sell at $1B tier → -1.0 bps → fill = 100 × (1 - 1/10000) = 99.99.
    // R6-T2：賣 + $1B tier → -1.0 bps → fill = 99.99。
    let cfg = crate::config::SlippageConfig::default();
    let bps = replay_slippage_bps_for_tif(&cfg, None, 2_000_000_000.0, false);
    assert!(bps < 0.0, "sell → negative bps, got {}", bps);
    let fill = apply_slippage_to_price(100.0, bps);
    assert!(fill < 100.0, "sell → fill < ref, got {}", fill);
    assert!((bps + 1.0).abs() < 1e-9, "$1B tier -1.0 bps, got {}", bps);
    assert!((fill - 99.99).abs() < 1e-9, "fill=99.99, got {}", fill);
}

#[test]
fn test_apply_fill_bbo_anchor_bounds_taker_reference_price() {
    assert_eq!(
        bbo_anchor_taker_reference_price(100.0, Some(99.0), Some(101.0), true),
        101.0,
        "buy taker must not price better than best ask"
    );
    assert_eq!(
        bbo_anchor_taker_reference_price(100.0, Some(99.0), Some(101.0), false),
        99.0,
        "sell taker must not price better than best bid"
    );
    assert_eq!(
        bbo_anchor_taker_reference_price(100.0, Some(102.0), Some(101.0), true),
        100.0,
        "crossed/invalid BBO must keep legacy reference price"
    );
}

#[test]
fn test_apply_fill_zero_volume_24h_graceful_fallback() {
    // R6-T2: volume_24h <= 0.0 → 5 bps fallback (signed by direction).
    // PostOnly always 0. No NaN.
    // R6-T2：volume_24h <= 0.0 → 5 bps fallback（帶符號）。PostOnly 必 0。
    let cfg = crate::config::SlippageConfig::default();
    let bps_buy = replay_slippage_bps_for_tif(&cfg, None, 0.0, true);
    let bps_sell = replay_slippage_bps_for_tif(&cfg, None, 0.0, false);
    assert!(
        bps_buy.is_finite(),
        "buy bps must be finite, got {}",
        bps_buy
    );
    assert!(
        bps_sell.is_finite(),
        "sell bps must be finite, got {}",
        bps_sell
    );
    assert!(
        (bps_buy - 5.0).abs() < 1e-9,
        "buy fallback +5.0 bps, got {}",
        bps_buy
    );
    assert!(
        (bps_sell + 5.0).abs() < 1e-9,
        "sell fallback -5.0 bps, got {}",
        bps_sell
    );
    // Negative volume_24h same fallback (live `lookup_rate` <= 0 → default).
    // 負 volume_24h 同 fallback。
    let bps_neg = replay_slippage_bps_for_tif(&cfg, None, -1.0, true);
    assert!(
        (bps_neg - 5.0).abs() < 1e-9,
        "negative vol → +5.0 bps, got {}",
        bps_neg
    );
    // PostOnly always 0 regardless of volume_24h. / PostOnly 必 0。
    let bps_po = replay_slippage_bps_for_tif(&cfg, Some(TimeInForce::PostOnly), 0.0, true);
    assert_eq!(bps_po, 0.0, "PostOnly slippage_bps must be 0");
}

#[test]
fn test_apply_fill_simulated_fill_fee_field_populated() {
    // R6-T1 end-to-end via adapter path: SimulatedFill row carries fee > 0
    // (finite), fee_rate=DEFAULT_TAKER_FEE_RATE, liquidity_role='taker',
    // slippage_bps non-zero (no AM seeded; default 5 bps fallback).
    // R6-T1 端到端（adapter path）：SimulatedFill row fee > 0、
    // fee_rate=DEFAULT_TAKER_FEE_RATE、liquidity_role='taker'、
    // slippage_bps 非 0（無 AM seed；預設 5 bps fallback）。
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_r6t1t2_taker".into(),
        "S3",
        r6_single_event(),
    )
    .expect("baseline build OK")
    .with_replay_fee_context(None, None, None);
    let (strategy_adapter, risk_adapter) = make_tif_adapters(None, true, None);
    let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes");
    wired.execute().expect("execute completes");
    let result = wired.into_result();
    assert_eq!(result.fills.len(), 1, "expected 1 accepted fill");
    let f0 = &result.fills[0];
    // R6-T1 assertions: fee + fee_rate + liquidity_role populated.
    // R6-T1 斷言：fee + fee_rate + liquidity_role 已填值。
    assert!(
        f0.fee.is_finite() && f0.fee > 0.0,
        "fee finite > 0, got {}",
        f0.fee
    );
    assert!(
        (f0.fee_rate - DEFAULT_TAKER_FEE_RATE).abs() < 1e-12,
        "taker rate, got {}",
        f0.fee_rate
    );
    assert_eq!(f0.liquidity_role, "taker", "non-PostOnly → taker role");
    // R6-T2 assertions: market + None volume → +5 bps; price=100.05.
    // R6-T2 斷言：market + None volume → +5 bps；price=100.05。
    assert!(
        (f0.slippage_bps - 5.0).abs() < 1e-9,
        "+5.0 bps, got {}",
        f0.slippage_bps
    );
    assert!(
        (f0.price - 100.05).abs() < 1e-9,
        "price=100.05, got {}",
        f0.price
    );
    // Fee = 0.01 × 100.05 × 0.00055 = 0.000550275.
    let expected_fee = 0.01 * 100.05 * DEFAULT_TAKER_FEE_RATE;
    assert!(
        (f0.fee - expected_fee).abs() < 1e-12,
        "fee={}, got {}",
        expected_fee,
        f0.fee
    );
}

#[test]
fn test_apply_fill_taker_open_uses_bbo_anchor_when_present() {
    // REF-21 Wave C1: market buy at close=100 with best_ask=101 uses ask
    // as the reference, then applies the existing +5 bps taker slippage.
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_ref21_bbo_anchor".into(),
        "S3",
        r6_single_event_with_bbo(99.0, 101.0),
    )
    .expect("baseline build OK")
    .with_replay_fee_context(None, None, None);
    let (strategy_adapter, risk_adapter) = make_tif_adapters(None, true, None);
    let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes");
    wired.execute().expect("execute completes");
    let result = wired.into_result();
    let f0 = &result.fills[0];
    assert_eq!(f0.liquidity_role, "taker");
    assert!((f0.slippage_bps - 5.0).abs() < 1e-9);
    assert!(
        (f0.price - 101.0505).abs() < 1e-9,
        "expected best_ask 101 plus 5 bps slippage, got {}",
        f0.price
    );
}

#[test]
fn test_apply_fill_taker_open_uses_depth_partial_and_latency_metadata() {
    // REF-21 S1: taker replay consumes recorded top-5 depth when present.
    // Only 20% of usable top-5 depth is considered executable, and the
    // calibrated latency is surfaced without sleeping or mutating runtime.
    let mut events = r6_single_event_with_bbo(99.0, 101.0);
    events[0].ask_depth_5 = Some(0.02);
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_ref21_depth_latency".into(),
        "S3",
        events,
    )
    .expect("baseline build OK")
    .with_replay_fee_context(None, None, None)
    .with_execution_calibration(None, Some(250));
    let (strategy_adapter, risk_adapter) = make_tif_adapters(None, true, None);
    let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes");
    wired.execute().expect("execute completes");
    let result = wired.into_result();
    assert_eq!(result.fills.len(), 1, "expected one accepted partial fill");
    let f0 = &result.fills[0];
    assert_eq!(f0.requested_qty, 0.01);
    assert!(
        (f0.qty - 0.004).abs() < 1e-12,
        "20% of ask_depth_5=0.02 should fill 0.004, got {}",
        f0.qty
    );
    assert_eq!(f0.fill_status, "partial");
    assert_eq!(f0.partial_fill_model_status, "applied_partial");
    assert_eq!(f0.depth_available_qty, Some(0.02));
    assert_eq!(f0.latency_ms, Some(250));
    assert_eq!(f0.effective_ts_ms, Some(251));
}

#[test]
fn test_apply_fill_postonly_path_emits_maker_zero_slippage() {
    // R6-T1+T2 cross-check: PostOnly → maker / 0 slippage / price == limit_price.
    // R6-T1+T2 交叉驗證：PostOnly → maker / 0 slippage / price == limit_price。
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_r6t1t2_maker".into(),
        "S3",
        r6_single_event(),
    )
    .expect("baseline build OK")
    .with_replay_fee_context(None, None, None);
    // PostOnly + limit_price=99.5 (must be on book, below current 100).
    // PostOnly + limit_price=99.5（必掛單，低於現價 100）。
    let (strategy_adapter, risk_adapter) =
        make_tif_adapters(Some(TimeInForce::PostOnly), true, Some(99.5));
    let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes");
    wired.execute().expect("execute completes");
    let result = wired.into_result();
    assert_eq!(result.fills.len(), 1, "expected 1 accepted fill");
    let f0 = &result.fills[0];
    assert!(
        (f0.fee_rate - DEFAULT_MAKER_FEE_RATE).abs() < 1e-12,
        "maker, got {}",
        f0.fee_rate
    );
    assert_eq!(f0.liquidity_role, "maker", "PostOnly → maker role");
    assert_eq!(f0.slippage_bps, 0.0, "PostOnly slippage_bps must be 0");
    assert!(
        (f0.price - 99.5).abs() < 1e-9,
        "price=99.5, got {}",
        f0.price
    );
    // Fee = 0.01 × 99.5 × 0.0002 = 0.000199.
    let expected_fee = 0.01 * 99.5 * DEFAULT_MAKER_FEE_RATE;
    assert!(
        (f0.fee - expected_fee).abs() < 1e-12,
        "fee={}, got {}",
        expected_fee,
        f0.fee
    );
}

#[test]
fn test_apply_fill_postonly_calibration_cap_records_maker_miss() {
    // REF-21 calibration: maker cap=0 converts a risk-accepted PostOnly
    // attempt into a qty=0 maker-miss ghost row instead of over-claiming
    // immediate maker execution.
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_ref21_maker_cap_zero".into(),
        "S3",
        r6_single_event(),
    )
    .expect("baseline build OK")
    .with_replay_fee_context(None, None, None)
    .with_execution_calibration(Some(0.0), None);
    let (strategy_adapter, risk_adapter) =
        make_tif_adapters(Some(TimeInForce::PostOnly), true, Some(99.5));
    let snapshot = make_snapshot_seed(10_000.0, Some(100.0), Vec::new());
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes");
    wired.execute().expect("execute completes");
    let result = wired.into_result();
    assert_eq!(result.fills.len(), 1, "expected 1 maker miss ghost row");
    let f0 = &result.fills[0];
    assert_eq!(f0.qty, 0.0, "maker miss ghost row must carry qty=0");
    assert_eq!(
        f0.liquidity_role, "maker",
        "PostOnly miss remains maker role"
    );
    assert_eq!(f0.fee, 0.0, "maker miss has no fee");
    assert_eq!(f0.slippage_bps, 0.0, "PostOnly miss keeps zero slippage");
    assert!(
        result
            .diagnostics
            .last_action_label
            .contains("maker_miss:BTCUSDT"),
        "last_action should record maker miss, got {}",
        result.diagnostics.last_action_label
    );
}

#[test]
fn test_apply_fill_synthetic_walker_emits_unknown_role_zero_fee() {
    // R6-T1+T2 backward compat: synthetic-walker → 0 fee / 'unknown' role
    // (proof_1/4/5 e2e byte-equal on `price` since slippage_bps=0).
    // R6-T1+T2 向後兼容：synthetic-walker → 0 fee / 'unknown' role
    // （proof_1/4/5 e2e 因 slippage_bps=0 在 `price` byte-equal）。
    let mut p = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_r6t1t2_synthetic".into(),
        "S3",
        synthetic_events(),
    )
    .unwrap();
    p.execute().unwrap();
    let r = p.into_result();
    assert_eq!(
        r.fills.len(),
        2,
        "synthetic walker emits 1 fill per new symbol"
    );
    for f in &r.fills {
        assert_eq!(f.fee, 0.0, "synthetic walker fee must be 0");
        assert_eq!(f.fee_rate, 0.0, "synthetic walker fee_rate must be 0");
        assert_eq!(
            f.slippage_bps, 0.0,
            "synthetic walker slippage_bps must be 0"
        );
        assert_eq!(
            f.liquidity_role, "unknown",
            "synthetic walker liquidity_role must be 'unknown'"
        );
    }
}

#[test]
fn test_apply_fill_ghost_row_records_zero_fee_with_intent_metadata() {
    // R6-T1 ghost-row contract: rejected intent → qty=0 → fee=0; but
    // fee_rate / slippage_bps / liquidity_role still reflect intent's
    // TIF + direction (counterfactual transparency).
    // R6-T1 ghost row 契約：被拒 intent → qty=0 → fee=0；fee_rate /
    // slippage_bps / liquidity_role 仍反映 TIF + 方向（counterfactual）。
    let pipeline = build_isolated_pipeline(
        ReplayProfile::Isolated,
        "exp_r6t1t2_ghost".into(),
        "S3",
        r6_single_event(),
    )
    .expect("baseline build OK")
    .with_replay_fee_context(None, None, None);
    let (strategy_adapter, risk_adapter) = make_tif_adapters(None, true, None);
    // Same-direction position triggers Gate 1.5 reject. / 同向倉觸 Gate 1.5。
    let snapshot = make_snapshot_seed(
        10_000.0,
        Some(100.0),
        vec![crate::replay::risk_adapter::ReplayPosition {
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.5,
            entry_price: 100.0,
            owner_strategy: String::new(),
        }],
    );
    let mut wired = pipeline
        .with_adapter_pipeline(strategy_adapter, risk_adapter, snapshot)
        .expect("snapshot validation passes");
    wired.execute().expect("execute completes");
    let result = wired.into_result();
    let ghost = result
        .fills
        .iter()
        .find(|f| f.qty == 0.0 && f.symbol == "BTCUSDT")
        .expect("expected ghost fill on Gate 1.5 reject");
    assert_eq!(ghost.fee, 0.0, "ghost fee must be 0 (qty=0)");
    // fee_rate / liquidity_role / slippage_bps reflect counterfactual.
    // fee_rate / liquidity_role / slippage_bps 反映 counterfactual。
    assert!(
        (ghost.fee_rate - DEFAULT_TAKER_FEE_RATE).abs() < 1e-12,
        "taker, got {}",
        ghost.fee_rate
    );
    assert_eq!(ghost.liquidity_role, "taker", "None TIF → taker");
    assert!(
        (ghost.slippage_bps - 5.0).abs() < 1e-9,
        "+5.0 bps, got {}",
        ghost.slippage_bps
    );
}

// ─── Sprint C R6 W2 R6-T3 KellyConfig wire tests / R6-T3 Kelly 接線測試 ───
// Tests verify that bin/replay_runner.rs::main wiring (calibrated
// KellyConfig pulled from risk_config.kelly + per_trade_risk_pct from
// risk_config.limits) is byte-equal to the live `compute_kelly_qty`
// contract. R6-T3 dispatch §5 requires 2-3 cases.
//
// Sprint C R6 W2 R6-T3 Kelly 接線測試。驗 bin/replay_runner.rs::main
// 接線（從 risk_config.kelly 派生 KellyConfig + 從 risk_config.limits
// 派生 per_trade_risk_pct）與 live `compute_kelly_qty` 契約位元級一致。
// R6-T3 dispatch §5 要求 2-3 case。

use crate::ml::kelly_sizer::{compute_kelly_qty, TradeStats};

/// R6-T3 / W-AUDIT-6 — verify KellyConfig is derived from the authoritative
/// RiskConfig snapshot rather than carrying a separate risk_pct source.
/// R6-T3 / W-AUDIT-6 — 驗 KellyConfig 從權威 RiskConfig 快照派生，
/// 不再持有另一套 risk_pct 來源。
#[test]
fn test_r6t3_kelly_config_construction_reads_risk_config_snapshot() {
    let mut risk_config = crate::config::RiskConfig::default();
    risk_config.limits.per_trade_risk_pct = crate::config::MIN_PER_TRADE_RISK_PCT;
    risk_config.kelly.young_fraction = 0.10;
    risk_config.kelly.mature_fraction = 0.20;
    risk_config.kelly.established_fraction = 0.30;

    let kelly_config = KellyConfig::from_risk_config(&risk_config);
    // At G7-01 defaults, replay-derived KellyConfig must field-equal
    // the risk_config snapshot for tunables while keeping structural defaults.
    // G7-01 預設下，replay 派生的 KellyConfig 必須讀 risk_config 中的可調欄位，
    // 其餘結構欄位保留 KellyConfig 預設。
    assert_eq!(
        kelly_config.young_threshold,
        risk_config.kelly.young_threshold
    );
    assert_eq!(
        kelly_config.mature_threshold,
        risk_config.kelly.mature_threshold
    );
    assert!((kelly_config.risk_pct - risk_config.limits.per_trade_risk_pct).abs() < 1e-12);
    assert!((kelly_config.young_fraction - 0.10).abs() < 1e-12);
    assert!((kelly_config.mature_fraction - 0.20).abs() < 1e-12);
    assert!((kelly_config.established_fraction - 0.30).abs() < 1e-12);
    let defaults = KellyConfig::default();
    assert!((kelly_config.max_fraction - defaults.max_fraction).abs() < 1e-12);
    assert_eq!(kelly_config.min_trades, defaults.min_trades);
    assert_eq!(kelly_config.enabled, defaults.enabled);
    assert!((kelly_config.reference_atr_pct - defaults.reference_atr_pct).abs() < 1e-12);
    assert!((kelly_config.vol_mult_floor - defaults.vol_mult_floor).abs() < 1e-12);
    assert!((kelly_config.vol_mult_ceil - defaults.vol_mult_ceil).abs() < 1e-12);
    // Validate KellyConfig itself (G7-01 invariant: young < mature, both > 0).
    kelly_config
        .validate()
        .expect("derived KellyConfig must validate");
}

/// R6-T3 — verify p1_risk_pct extraction from risk_config.limits.
/// Sprint A baseline hardcoded 0.02; R6-T3 reads from risk_config.
/// Default `RiskConfig` has `limits.per_trade_risk_pct=0.03` (CLAUDE.md).
/// R6-T3 — 驗 p1_risk_pct 從 risk_config.limits 派生。Sprint A baseline
/// 硬編 0.02；R6-T3 改讀 risk_config。預設值 0.03。
#[test]
fn test_r6t3_p1_risk_pct_reads_from_risk_config_limits() {
    let risk_config = crate::config::RiskConfig::default();
    let p1_risk_pct = risk_config.limits.per_trade_risk_pct;
    // Default RiskConfig has per_trade_risk_pct=0.03 (Position Sizing memo:
    // "3% risk/trade" — feedback_position_sizing.md).
    // 預設 RiskConfig 有 per_trade_risk_pct=0.03（Position Sizing memo
    // 「3% risk/trade」— feedback_position_sizing.md）。
    assert!(
        p1_risk_pct > 0.0 && p1_risk_pct <= 1.0,
        "p1_risk_pct must be in (0,1], got {}",
        p1_risk_pct
    );
    assert!(
        (p1_risk_pct - 0.03).abs() < 1e-9,
        "default per_trade_risk_pct should be 0.03, got {}",
        p1_risk_pct
    );
    // Differs from Sprint A baseline hardcode of 0.02.
    // 與 Sprint A baseline 0.02 硬編不同。
    assert!(
        (p1_risk_pct - 0.02).abs() > 1e-9,
        "R6-T3 must replace Sprint A 0.02 hardcode"
    );
}

/// R6-T3 — verify `IsolatedPipeline::with_adapter_pipeline` accepts the
/// replay-derived KellyConfig and `compute_kelly_qty` produces a finite
/// non-negative qty in the cold-boot (empty TradeStats) path.
/// R6-T3 — 驗 `IsolatedPipeline::with_adapter_pipeline` 接受 replay 派生的
/// KellyConfig，且冷啟動（空 TradeStats）路徑下 `compute_kelly_qty` 產出
/// 有限非負 qty。
#[test]
fn test_r6t3_kelly_qty_finite_with_calibrated_kelly_config() {
    let risk_config = crate::config::RiskConfig::default();
    let kelly_config = KellyConfig::from_risk_config(&risk_config);
    // Cold-boot stats: 0 trades → Kelly inactive path returns
    // `min(balance * risk_pct / price, max_qty)`.
    // 冷啟動 stats：0 trades → Kelly 未啟動路徑回 `min(balance*risk_pct/price, max_qty)`。
    let stats = TradeStats::default();
    let balance = 10_000.0;
    let price = 100.0;
    let atr_pct = 0.0;
    let max_qty = 5.0;
    let qty = compute_kelly_qty(&kelly_config, &stats, balance, price, atr_pct, max_qty);
    assert!(qty.is_finite(), "qty must be finite, got {}", qty);
    assert!(qty >= 0.0, "qty must be non-negative, got {}", qty);
    // Cold-boot expected: min(10000 * 0.03 / 100, 5.0) = min(3.0, 5.0) = 3.0
    // 冷啟動期望：min(10000 * 0.03 / 100, 5.0) = min(3.0, 5.0) = 3.0
    assert!(
        (qty - 3.0).abs() < 1e-9,
        "cold-boot expected balance*risk_pct/price = 3.0, got {}",
        qty
    );

    // Verify pipeline acceptance: building a risk_adapter with Some(kelly_config)
    // does NOT trip ReplayIsolationError.
    // 驗 pipeline 接受：用 Some(kelly_config) 建 risk_adapter 不觸發 ReplayIsolationError。
    let risk_adapter = crate::replay::risk_adapter::ReplayRiskAdapter::new(
        ReplayProfile::Isolated,
        GuardianConfig::default(),
        risk_config.clone(),
        risk_config.limits.per_trade_risk_pct,
        Some(kelly_config),
    );
    assert!(
        risk_adapter.is_ok(),
        "Isolated profile + Some(KellyConfig) must construct, got {:?}",
        risk_adapter.err()
    );
}

// ────────────────────────────────────────────────────────────────────────
// Tier A T1 + T2 + T2.5 sanity test（2026-05-11 E1-A）
// 對齊 PA design §3.3 / §3.5 acceptance：is_pinned 由 scanner_timeline 注入、
// position_state 由 ReplayPaperSnapshot 映射為 stack-local borrow、
// ReplayPosition.owner_strategy 由 apply_fill_open 寫入。
// ────────────────────────────────────────────────────────────────────────

/// 構造一個 ETHUSDT MarketEvent，方便 test 重用。
fn synthetic_event(symbol: &str, ts_ms: i64, close: f64) -> MarketEvent {
    MarketEvent {
        ts_ms,
        symbol: symbol.to_string(),
        open: close,
        high: close * 1.01,
        low: close * 0.99,
        close,
        volume: 1.0,
        turnover: None,
        turnover_24h: None,
        best_bid: None,
        best_ask: None,
        bid_size: None,
        ask_size: None,
        bid_depth_5: None,
        ask_depth_5: None,
        spread_bps: None,
        microstructure_source: None,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        tick_size: None,
        h0_allowed: None,
        indicators: None,
        signals: Vec::new(),
    }
}

#[test]
fn build_replay_position_borrow_preserves_owner_strategy() {
    // Tier A T2.5：驗證 helper 將 ReplayPosition.owner_strategy 對齊
    // 寫進 stack-local PaperPosition，供 ctx.position_state 借用。
    let rp = crate::replay::risk_adapter::ReplayPosition {
        symbol: "BTCUSDT".to_string(),
        is_long: true,
        qty: 0.5,
        entry_price: 64_000.0,
        owner_strategy: "ma_crossover".to_string(),
    };
    let pp = super::build_replay_position_borrow(&rp, 1_700_000_000_000);
    assert_eq!(pp.symbol, "BTCUSDT");
    assert_eq!(pp.is_long, true);
    assert_eq!(pp.qty, 0.5);
    assert_eq!(pp.entry_price, 64_000.0);
    assert_eq!(pp.best_price, 64_000.0);
    assert_eq!(pp.owner_strategy, "ma_crossover");
    assert_eq!(pp.entry_notional, 0.5 * 64_000.0);
    assert_eq!(pp.entry_ts_ms, 1_700_000_000_000u64);
}

#[test]
fn build_replay_position_borrow_clamps_negative_ts() {
    // 對齊 build_tick_context 的 ts_ms.max(0) as u64 行為。
    let rp = crate::replay::risk_adapter::ReplayPosition {
        symbol: "ADAUSDT".to_string(),
        is_long: false,
        qty: 100.0,
        entry_price: 0.5,
        owner_strategy: String::new(),
    };
    let pp = super::build_replay_position_borrow(&rp, -42);
    assert_eq!(pp.entry_ts_ms, 0u64, "negative ts_ms must clamp to 0");
}

#[test]
fn build_tick_context_threads_is_pinned_and_position_state() {
    // Tier A T1 + T2：驗證 build_tick_context 把 caller 注入的 is_pinned
    // 與 position_state 透傳到 TickContext。對齊 production 行為。
    let event = synthetic_event("BTCUSDT", 100, 64_000.0);
    // 顯式構造 ReplayTickInputs（無 Default impl）。
    let inputs = crate::replay::context_builder::ReplayTickInputs {
        indicators: None,
        signals: Vec::new(),
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        tick_size: None,
        turnover_24h: None,
    };
    let pp = crate::paper_state::PaperPosition {
        symbol: "BTCUSDT".to_string(),
        is_long: true,
        qty: 0.5,
        entry_price: 64_000.0,
        best_price: 64_000.0,
        entry_fee: 0.0,
        entry_ts_ms: 100,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: "ma_crossover".to_string(),
        entry_notional: 32_000.0,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    };

    // Case 1：is_pinned=true + Some(position) → ctx 取到等值。
    let ctx = super::build_tick_context(&event, &inputs, true, Some(&pp));
    assert_eq!(ctx.symbol, "BTCUSDT");
    assert!(ctx.is_pinned, "is_pinned=true must propagate");
    let ctx_pos = ctx.position_state.expect("position_state must be Some");
    assert_eq!(ctx_pos.symbol, "BTCUSDT");
    assert_eq!(ctx_pos.owner_strategy, "ma_crossover");
    assert_eq!(ctx_pos.qty, 0.5);

    // Case 2：is_pinned=false + None position → fail-closed 路徑可被策略觀察。
    let ctx2 = super::build_tick_context(&event, &inputs, false, None);
    assert!(!ctx2.is_pinned, "is_pinned=false must propagate");
    assert!(
        ctx2.position_state.is_none(),
        "position_state=None must propagate"
    );
}

#[test]
fn replay_position_owner_strategy_default_empty_string() {
    // Backward-compat：未提供 owner_strategy 時（test seed / 既有 ghost fill）
    // 預期空字串作為 first-write-wins 的初始值（與 production PaperPosition
    // pre-Phase-2A 行為一致）。
    let rp = crate::replay::risk_adapter::ReplayPosition {
        symbol: "ETHUSDT".to_string(),
        is_long: false,
        qty: 0.1,
        entry_price: 2_300.0,
        owner_strategy: String::new(),
    };
    assert_eq!(rp.owner_strategy, "");
}
