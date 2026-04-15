//! Stress Integration Tests — extreme scenarios for R-05 decision gate.
//! 壓力集成測試 — R-05 決策點的極端場景。
//!
//! Covers: fast_track emergency, multi-symbol mixed trading, cascade governance,
//!   flash crash, drawdown breach, position limits, stop triggers, rapid ticks.

use openclaw_core::governance_core::{GovernanceCore, GovernanceProfile};
use openclaw_core::indicators::*;
use openclaw_core::sm::risk_gov::RiskLevel;
use openclaw_engine::fast_track::{evaluate_fast_track, FastTrackAction};
use openclaw_engine::intent_processor::{IntentProcessor, OrderIntent};
use openclaw_engine::paper_state::PaperState;
use openclaw_engine::strategies::{
    bb_breakout::BbBreakout, bb_reversion::BbReversion, grid_trading::GridTrading,
    ma_crossover::MaCrossover, Strategy, StrategyAction,
};
use openclaw_engine::tick_pipeline::{TickContext, TickPipeline};
use openclaw_types::PriceEvent;

// ═══════════════════════════════════════════════════════════════════════════════
// Helper functions / 輔助函數
// ═══════════════════════════════════════════════════════════════════════════════

fn make_event(symbol: &str, price: f64, ts_ms: u64) -> PriceEvent {
    PriceEvent::new(symbol.to_string(), price, ts_ms)
}

// P-08: TickContext<'a> uses borrowed refs; Box::leak gives 'static lifetime for test helpers.
// P-08：TickContext<'a> 使用借用引用；Box::leak 為測試輔助函數提供 'static 生命週期。
fn make_ctx(symbol: &'static str, price: f64, ts: u64, ind: Option<IndicatorSnapshot>) -> TickContext<'static> {
    static NO_SIGNALS: &[openclaw_core::signals::Signal] = &[];
    let indicators = ind.map(|i| &*Box::leak(Box::new(i)));
    TickContext {
        symbol,
        price,
        timestamp_ms: ts,
        indicators,
        signals: NO_SIGNALS,
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
    }
}

fn bb_snapshot(
    pct_b: f64,
    bw: f64,
    rsi: f64,
    sma: f64,
    kama: f64,
    adx: f64,
    vol_ratio: f64,
) -> IndicatorSnapshot {
    IndicatorSnapshot {
        sma_20: Some(sma),
        sma_50: None,
        ema_12: Some(sma * 1.001),
        ema_26: None,
        rsi_14: Some(rsi),
        bollinger: Some(BollingerResult {
            upper: sma * 1.02,
            middle: sma,
            lower: sma * 0.98,
            bandwidth: bw,
            percent_b: pct_b,
        }),
        kama: Some(KamaResult {
            kama,
            efficiency_ratio: 0.5,
        }),
        adx: Some(AdxResult {
            adx,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        volume_ratio: Some(vol_ratio),
        macd: Some(MacdResult {
            macd: 0.5,
            signal: 0.3,
            histogram: 0.2,
        }),
        atr_14: Some(AtrResult {
            atr: sma * 0.02,
            atr_percent: 2.0,
        }),
        atr_5: None,
        stochastic: Some(StochResult { k: 50.0, d: 50.0 }),
        // EDGE-P1-3: trending regime produces good scores for trend-following strategies.
        // bb_reversion tests override with mean_reverting locally.
        hurst: Some(HurstResult { hurst: 0.70, regime: "trending".into() }),
        ewma_vol: None,
        donchian: None,
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. Fast Track Emergency Scenarios / 快速通道緊急場景
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_fast_track_flash_crash_closes_all_positions() {
    // Scenario: 5-symbol portfolio, BTC flash crashes 8%, all positions must close
    let symbols = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];
    let mut pipeline = TickPipeline::new(symbols);
    pipeline.grant_paper_auth().unwrap();

    // Open positions via direct apply_fill
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.01, 65000.0, 3.575, 1000, "test");
    pipeline
        .paper_state
        .apply_fill("ETHUSDT", true, 0.1, 2000.0, 0.11, 1000, "test");
    pipeline
        .paper_state
        .apply_fill("SOLUSDT", true, 1.0, 150.0, 0.0825, 1000, "test");
    pipeline
        .paper_state
        .apply_fill("XRPUSDT", true, 100.0, 0.60, 0.033, 1000, "test");
    pipeline
        .paper_state
        .apply_fill("DOGEUSDT", false, 1000.0, 0.15, 0.0825, 1000, "test");
    assert_eq!(pipeline.paper_state.position_count(), 5);

    // Simulate CircuitBreaker risk level triggering fast_track
    let action = evaluate_fast_track(RiskLevel::CircuitBreaker, 0.0, 0.0, 0.0);
    assert_eq!(action, FastTrackAction::CloseAll);

    // Post FA-PHANTOM-2: 8% drop on held at Normal with sigma<3 → NoAction
    // (naturally-volatile symbol). With sigma≥3 it becomes ReduceToHalf at
    // Normal; CloseAll only at Defensive+ or at ≥15% cliff.
    // FA-PHANTOM-2 修復後：8% + Normal + sigma<3 → NoAction（小幣正常波動）。
    let action = evaluate_fast_track(RiskLevel::Normal, 8.0, 2.5, 50.0);
    assert_eq!(action, FastTrackAction::NoAction);
    // 8% + sigma≥3 + Normal → ReduceToHalf
    let action = evaluate_fast_track(RiskLevel::Normal, 8.0, 4.0, 50.0);
    assert_eq!(action, FastTrackAction::ReduceToHalf);
    // 15% drop triggers regardless — cliff-level flash crash
    let action = evaluate_fast_track(RiskLevel::Normal, 15.0, 0.0, 50.0);
    assert_eq!(action, FastTrackAction::CloseAll);

    let action = evaluate_fast_track(RiskLevel::Normal, 0.5, 0.5, 95.0); // margin crisis
    assert_eq!(action, FastTrackAction::CloseAll);
}

#[test]
fn stress_fast_track_defensive_reduces_exposure() {
    let action = evaluate_fast_track(RiskLevel::Defensive, 2.0, 0.5, 60.0);
    assert_eq!(action, FastTrackAction::ReduceToHalf);
}

#[test]
fn stress_fast_track_reduced_pauses_but_keeps_positions() {
    let action = evaluate_fast_track(RiskLevel::Reduced, 1.0, 0.5, 40.0);
    assert_eq!(action, FastTrackAction::PauseNewEntries);
}

#[test]
fn stress_fast_track_boundary_extreme_drop_cliff() {
    // FA-PHANTOM-2: only ≥15% held-symbol drops auto-trigger CloseAll
    // regardless of sigma/risk_level. Moderate drops now require sigma≥3
    // (and even then downgrade to ReduceToHalf at <Defensive levels).
    // FA-PHANTOM-2：只有 ≥15% 持倉跌幅才無條件 CloseAll。
    assert_eq!(
        evaluate_fast_track(RiskLevel::Normal, 15.0, 0.0, 0.0),
        FastTrackAction::CloseAll
    );
    assert_eq!(
        evaluate_fast_track(RiskLevel::Normal, 14.99, 0.0, 0.0),
        FastTrackAction::NoAction
    );
    assert_eq!(
        evaluate_fast_track(RiskLevel::Normal, 14.99, 5.0, 0.0),
        FastTrackAction::ReduceToHalf
    );
}

#[test]
fn stress_fast_track_boundary_exactly_90pct_margin() {
    assert_eq!(
        evaluate_fast_track(RiskLevel::Normal, 0.0, 0.0, 90.0),
        FastTrackAction::CloseAll
    );
    assert_eq!(
        evaluate_fast_track(RiskLevel::Normal, 0.0, 0.0, 89.99),
        FastTrackAction::NoAction
    );
}

// FA-PHANTOM-1 end-to-end regression: prior to the 2026-04-14 fix in
// `on_tick.rs`, margin_utilization_pct was computed as total_notional /
// balance with no leverage divisor. Default leverage_max=20 +
// position_size_max_pct=20 means five strategies each opening a 20%
// notional position accumulate to 100% of balance — which the old formula
// reported as 100% margin util, tripping the fast_track 90% threshold and
// force-closing every position every tick. This caused the 22 phantom fills
// observed during G-2 funding_arb validation. The unit test in fast_track.rs
// only pins the threshold arithmetic; this test drives a real on_tick() so
// that any future regression which deletes the `/leverage` divider, skips
// `risk_config()`, or accidentally bypasses PaperState fails end-to-end.
// FA-PHANTOM-1 端到端回歸：5 倉 × 100% notional × leverage=20 → 真實 margin 5%。
// 透過實際 on_tick 驅動，抓住未來刪 /leverage 除法的回歸。
#[test]
fn stress_fa_phantom_1_regression_5_positions_100pct_notional_20x_leverage() {
    let symbols = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];
    let mut pipeline = TickPipeline::with_balance(symbols, 10_000.0);
    pipeline.grant_paper_auth().unwrap();

    assert!(
        (pipeline.intent_processor.risk_config().limits.leverage_max - 20.0).abs() < 1e-9,
        "test precondition: default leverage_max should be 20.0",
    );

    // Five positions at $2_000 notional each = $10_000 total = 100% of balance.
    pipeline.paper_state.apply_fill("BTCUSDT", true, 0.04, 50_000.0, 0.0, 1000, "test");
    pipeline.paper_state.apply_fill("ETHUSDT", true, 1.0, 2_000.0, 0.0, 1000, "test");
    pipeline.paper_state.apply_fill("SOLUSDT", true, 20.0, 100.0, 0.0, 1000, "test");
    pipeline.paper_state.apply_fill("XRPUSDT", true, 2_000.0, 1.0, 0.0, 1000, "test");
    pipeline.paper_state.apply_fill("DOGEUSDT", false, 10_000.0, 0.2, 0.0, 1000, "test");
    assert_eq!(pipeline.paper_state.position_count(), 5);

    // Drive a tick at the same entry price so price_drop_pct stays 0 and
    // margin_utilization_pct is the sole fast_track input.
    pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, 2000));

    // Post-fix: 100% notional / 20x leverage = 5% true margin → no CloseAll.
    // Pre-fix: would have reported 100% margin util and dropped count to 0.
    assert_eq!(
        pipeline.paper_state.position_count(),
        5,
        "FA-PHANTOM-1 regression: fast_track must NOT CloseAll at 100% notional / 20x leverage (true margin = 5%)",
    );
}

// Cash-mode companion: leverage=1 collapses the leverage-aware formula back
// to notional/balance, so 100% notional IS a genuine margin crisis and
// CloseAll must still fire. Guards against a "simplification" regression
// that would force leverage to 1 in all cases and re-open FA-PHANTOM-1.
// 現貨模式對照：leverage=1 時 100% notional 為真實 margin 危機，CloseAll 應觸發。
#[test]
fn stress_fa_phantom_1_cash_mode_100pct_notional_closes_all() {
    let symbols = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];
    let mut pipeline = TickPipeline::with_balance(symbols, 10_000.0);
    pipeline.grant_paper_auth().unwrap();

    let mut rc = pipeline.intent_processor.risk_config().clone();
    rc.limits.leverage_max = 1.0;
    pipeline.intent_processor.update_risk_config(rc);

    pipeline.paper_state.apply_fill("BTCUSDT", true, 0.04, 50_000.0, 0.0, 1000, "test");
    pipeline.paper_state.apply_fill("ETHUSDT", true, 1.0, 2_000.0, 0.0, 1000, "test");
    pipeline.paper_state.apply_fill("SOLUSDT", true, 20.0, 100.0, 0.0, 1000, "test");
    pipeline.paper_state.apply_fill("XRPUSDT", true, 2_000.0, 1.0, 0.0, 1000, "test");
    pipeline.paper_state.apply_fill("DOGEUSDT", false, 10_000.0, 0.2, 0.0, 1000, "test");
    assert_eq!(pipeline.paper_state.position_count(), 5);

    pipeline.on_tick(&make_event("BTCUSDT", 50_000.0, 2000));

    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "cash mode (leverage=1): 100% notional is a real margin crisis — CloseAll must fire",
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// 2. Multi-Symbol Mixed Strategy Scenarios / 多幣種混合策略場景
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_multi_symbol_5_coins_simultaneous_ticks() {
    let symbols = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "DOGEUSDT"];
    let mut pipeline = TickPipeline::new(symbols);
    pipeline.grant_paper_auth().unwrap();

    // Register all 4 strategies
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));
    pipeline.orchestrator.register(Box::new(BbReversion::new()));
    pipeline.orchestrator.register(Box::new(BbBreakout::new()));
    pipeline
        .orchestrator
        .register(Box::new(GridTrading::new(60000.0, 80000.0)));

    // Simulate 500 ticks across 5 symbols with realistic prices
    let base_prices = [67000.0, 2050.0, 150.0, 0.60, 0.15];
    for i in 0..500 {
        let sym_idx = i % 5;
        let price_jitter = (i as f64 * 0.7).sin() * base_prices[sym_idx] * 0.005;
        let price = base_prices[sym_idx] + price_jitter;
        let ts = i as u64 * 1000; // 1 second apart
        pipeline.on_tick(&make_event(symbols[sym_idx], price, ts));
    }

    assert!(pipeline.stats.total_ticks == 500);
    // Should have processed without panic — that's the key assertion
    let status = pipeline.status();
    assert!(status.symbols_tracked >= 5);
    // Balance should not be wildly off from initial 10k
    assert!(status.balance > 5000.0 && status.balance < 15000.0);
}

#[test]
fn stress_multi_symbol_rapid_alternating_ticks() {
    // BTC and ETH ticks alternating every ms — tests symbol isolation
    let mut pipeline = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
    pipeline.grant_paper_auth().unwrap();
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));
    pipeline
        .orchestrator
        .register(Box::new(GridTrading::new(60000.0, 80000.0)));

    for i in 0..1000 {
        if i % 2 == 0 {
            pipeline.on_tick(&make_event(
                "BTCUSDT",
                67000.0 + (i as f64).sin() * 100.0,
                i,
            ));
        } else {
            pipeline.on_tick(&make_event("ETHUSDT", 2050.0 + (i as f64).sin() * 5.0, i));
        }
    }

    assert_eq!(pipeline.stats.total_ticks, 1000);
    // Verify BTC stop checks don't use ETH prices (bug we fixed)
    let state = pipeline.paper_state.export_state();
    for snap in &state.positions {
        if snap.position.symbol == "ETHUSDT" {
            assert!(
                snap.position.best_price < 3000.0,
                "ETH best_price contaminated by BTC: {}",
                snap.position.best_price
            );
        }
        if snap.position.symbol == "BTCUSDT" {
            assert!(
                snap.position.best_price > 50000.0 || snap.position.best_price == 0.0,
                "BTC best_price contaminated by ETH: {}",
                snap.position.best_price
            );
        }
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 3. Strategy Edge Cases / 策略邊界情況
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_ma_crossover_whipsaw_rapid_reversals() {
    // Rapid crossover reversals within cooldown window — cooldown should throttle
    let mut strat = MaCrossover::new();
    strat.min_persistence_ms = 0; // disable persistence for test
    let mut fills_throttled = 0;
    let mut fills_unthrottled = 0;

    // Phase 1: Within cooldown (100s < 300s cooldown) — should be throttled
    for i in 0..20 {
        let sma = 50000.0;
        let kama = if i % 2 == 0 { 50100.0 } else { 49900.0 };
        let ts = i as u64 * 100_000; // 100s intervals — within 300s cooldown
        let ctx = make_ctx(
            "BTCUSDT",
            50000.0,
            ts,
            Some(bb_snapshot(0.5, 0.03, 50.0, sma, kama, 25.0, 1.0)),
        );
        fills_throttled += strat.on_tick(&ctx).len();
    }
    // Cooldown should prevent most trades — at most ~7 (every 3rd tick)
    assert!(fills_throttled > 0, "no trades generated");
    assert!(
        fills_throttled < 15,
        "cooldown not throttling: {} trades in 20 ticks",
        fills_throttled
    );

    // Phase 2: Beyond cooldown (400s > 300s) — every alternation should trade
    let mut strat2 = MaCrossover::new();
    strat2.min_persistence_ms = 0; // disable persistence for test
    for i in 0..20 {
        let sma = 50000.0;
        let kama = if i % 2 == 0 { 50100.0 } else { 49900.0 };
        let ts = i as u64 * 400_000; // above cooldown
        let ctx = make_ctx(
            "BTCUSDT",
            50000.0,
            ts,
            Some(bb_snapshot(0.5, 0.03, 50.0, sma, kama, 25.0, 1.0)),
        );
        fills_unthrottled += strat2.on_tick(&ctx).len();
    }
    // Should have many more trades when above cooldown
    assert!(
        fills_unthrottled > fills_throttled,
        "above-cooldown ({}) should produce more trades than within-cooldown ({})",
        fills_unthrottled,
        fills_throttled
    );
}

#[test]
fn stress_bb_reversion_extreme_oversold_bounce() {
    let mut strat = BbReversion::new();
    strat.min_persistence_ms = 0; // disable persistence for test

    // EDGE-P1-3: bb_reversion needs mean_reverting regime for score ≥ 45.
    // Override bb_snapshot's default trending hurst with mean_reverting.
    let mut snap1 = bb_snapshot(-0.5, 0.06, 10.0, 2050.0, 2040.0, 30.0, 2.0);
    snap1.hurst = Some(HurstResult { hurst: 0.35, regime: "mean_reverting".into() });
    // Extreme oversold: %B = -0.5, RSI = 10
    let ctx1 = make_ctx("ETHUSDT", 2000.0, 0, Some(snap1));
    let intents = strat.on_tick(&ctx1);
    assert_eq!(intents.len(), 1, "should enter long on extreme oversold");
    match &intents[0] {
        StrategyAction::Open(i) => assert!(i.is_long),
        other => panic!("expected Open, got {:?}", other),
    }

    // Bounce to mean — should exit
    let mut snap2 = bb_snapshot(0.5, 0.04, 50.0, 2050.0, 2050.0, 25.0, 1.0);
    snap2.hurst = Some(HurstResult { hurst: 0.35, regime: "mean_reverting".into() });
    let ctx2 = make_ctx("ETHUSDT", 2050.0, 700_000, Some(snap2));
    let intents = strat.on_tick(&ctx2);
    assert_eq!(intents.len(), 1, "should exit at mean reversion");
}

#[test]
fn stress_bb_breakout_false_squeeze_no_volume() {
    let mut strat = BbBreakout::new();
    strat.min_persistence_ms = 0; // disable persistence for test

    // Enter squeeze
    let ctx1 = make_ctx(
        "BTCUSDT",
        67000.0,
        0,
        Some(bb_snapshot(0.5, 0.015, 50.0, 67000.0, 67000.0, 25.0, 0.8)),
    );
    strat.on_tick(&ctx1);

    // Expansion but LOW volume — should NOT enter
    let ctx2 = make_ctx(
        "BTCUSDT",
        67500.0,
        700_000,
        Some(bb_snapshot(1.1, 0.05, 60.0, 67000.0, 67100.0, 25.0, 1.0)),
    );
    let intents = strat.on_tick(&ctx2);
    assert!(
        intents.is_empty(),
        "should not enter without volume confirmation"
    );
}

#[test]
fn stress_bb_breakout_valid_squeeze_with_volume() {
    let mut strat = BbBreakout::new();
    strat.min_persistence_ms = 0; // disable persistence for test

    // Squeeze phase
    let ctx1 = make_ctx(
        "BTCUSDT",
        67000.0,
        0,
        Some(bb_snapshot(0.5, 0.015, 50.0, 67000.0, 67000.0, 25.0, 0.8)),
    );
    strat.on_tick(&ctx1);

    // Expansion + volume + upper breakout
    let ctx2 = make_ctx(
        "BTCUSDT",
        68000.0,
        700_000,
        Some(bb_snapshot(1.2, 0.06, 65.0, 67000.0, 67100.0, 30.0, 2.0)),
    );
    let intents = strat.on_tick(&ctx2);
    assert_eq!(intents.len(), 1, "should enter on valid squeeze breakout");
    match &intents[0] {
        StrategyAction::Open(i) => assert!(i.is_long, "should be long on upper breakout"),
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn stress_grid_trading_wide_range_traversal() {
    let mut strat = GridTrading::new(60000.0, 80000.0);

    // Traverse the full grid range in one direction, then back
    let mut total_intents = 0;
    for i in 0..200 {
        // Price goes 60000 → 80000 → 60000
        let price = if i < 100 {
            60000.0 + (i as f64 / 100.0) * 20000.0
        } else {
            80000.0 - ((i - 100) as f64 / 100.0) * 20000.0
        };
        let ts = i as u64 * 120_000; // 2 min between ticks (above 60s cooldown)
        let ctx = make_ctx("BTCUSDT", price, ts, None);
        total_intents += strat.on_tick(&ctx).len();
    }
    // Should have multiple grid crosses
    assert!(
        total_intents > 5,
        "grid should trade on range traversal: got {}",
        total_intents
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// 4. Guardian + Governance Cascade / 守護者 + 治理級聯
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_guardian_rejects_on_high_drawdown() {
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();

    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTCUSDT", 67000.0);
    state.force_drawdown(20.0); // 20% drawdown — above 15% limit

    let intent = OrderIntent {
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.01,
        confidence: 0.8,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
    };
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted, "should reject on high drawdown");
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("guardian_rejected"));
}

#[test]
fn stress_guardian_rejects_direction_conflict() {
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();

    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTCUSDT", 67000.0);
    state.apply_fill("BTCUSDT", true, 0.01, 67000.0, 0.0, 0, "test"); // existing long

    // Try to open short on same symbol
    let intent = OrderIntent {
        symbol: "BTCUSDT".into(),
        is_long: false,
        qty: 0.01,
        confidence: 0.8,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
    };
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted, "should reject direction conflict");
}

#[test]
fn stress_guardian_rejects_position_count_limit() {
    let proc = IntentProcessor::new();
    let mut gov = GovernanceCore::new();
    gov.grant_paper_authorization(None).unwrap();

    let mut state = PaperState::new(10_000.0);
    // Open 3 long positions (max_same_direction = 3)
    state.apply_fill("ETHUSDT", true, 0.1, 2000.0, 0.0, 0, "test");
    state.apply_fill("SOLUSDT", true, 1.0, 150.0, 0.0, 0, "test");
    state.apply_fill("XRPUSDT", true, 100.0, 0.6, 0.0, 0, "test");
    state.set_latest_price("BTCUSDT", 67000.0);

    // Try to open 4th long
    let intent = OrderIntent {
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.01,
        confidence: 0.8,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
    };
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(
        !result.submitted,
        "should reject 4th same-direction position"
    );
}

#[test]
fn stress_governance_not_authorized_rejects_all() {
    let proc = IntentProcessor::new();
    let gov = GovernanceCore::new(); // NOT authorized

    let mut state = PaperState::new(10_000.0);
    state.set_latest_price("BTCUSDT", 67000.0);

    let intent = OrderIntent {
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.01,
        confidence: 0.8,
        strategy: "test".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
    };
    let result = proc.process(&intent, &gov, &state, 500.0, GovernanceProfile::Exploration);
    assert!(!result.submitted);
    assert!(result
        .rejected_reason
        .unwrap()
        .contains("governance_not_authorized"));
}

// ═══════════════════════════════════════════════════════════════════════════════
// 5. Stop Manager Edge Cases / 止損管理器邊界情況
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_hard_stop_triggers_on_5pct_drop() {
    let mut state = PaperState::new(10_000.0);
    state.apply_fill("BTCUSDT", true, 0.01, 67000.0, 0.0, 1000, "test");
    state.set_latest_price("BTCUSDT", 63000.0); // ~6% drop

    let triggers = state.check_stops(63000.0, 100_000);
    assert_eq!(triggers.len(), 1, "hard stop should trigger on 6% drop");
    assert!(
        triggers[0].1.reason.contains("hard"),
        "reason: {}",
        triggers[0].1.reason
    );
}

#[test]
fn stress_hard_stop_does_not_trigger_at_4pct() {
    let mut state = PaperState::new(10_000.0);
    state.apply_fill("BTCUSDT", true, 0.01, 67000.0, 0.0, 1000, "test");
    state.set_latest_price("BTCUSDT", 64500.0); // ~3.7% drop

    let triggers = state.check_stops(64500.0, 100_000);
    assert!(triggers.is_empty(), "4% drop should not trigger hard stop");
}

#[test]
fn stress_short_position_stop_on_price_rise() {
    let mut state = PaperState::new(10_000.0);
    state.apply_fill("ETHUSDT", false, 0.1, 2000.0, 0.0, 1000, "test"); // short at 2000
    state.set_latest_price("ETHUSDT", 2120.0); // 6% rise = loss for short

    let triggers = state.check_stops(2120.0, 100_000);
    assert_eq!(triggers.len(), 1, "short should stop on 6% adverse move");
}

#[test]
fn stress_multi_position_independent_stops() {
    let mut state = PaperState::new(10_000.0);
    state.apply_fill("BTCUSDT", true, 0.01, 67000.0, 0.0, 1000, "test");
    state.apply_fill("ETHUSDT", true, 0.1, 2000.0, 0.0, 1000, "test");

    // BTC crashes but ETH is fine
    state.set_latest_price("BTCUSDT", 62000.0); // ~7.5% drop
    state.set_latest_price("ETHUSDT", 1980.0); // ~1% drop

    let triggers = state.check_stops(62000.0, 100_000);
    assert_eq!(triggers.len(), 1, "only BTC should trigger stop");
    assert_eq!(triggers[0].0, "BTCUSDT");
}

// ═══════════════════════════════════════════════════════════════════════════════
// 6. Pipeline Throughput Stress / 管線吞吐壓力
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_10k_ticks_no_panic() {
    let symbols = &["BTCUSDT", "ETHUSDT", "SOLUSDT"];
    let mut pipeline = TickPipeline::new(symbols);
    pipeline.grant_paper_auth().unwrap();
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));
    pipeline.orchestrator.register(Box::new(BbReversion::new()));
    pipeline
        .orchestrator
        .register(Box::new(GridTrading::new(60000.0, 80000.0)));

    let base_prices = [67000.0, 2050.0, 150.0];
    for i in 0..10_000 {
        let sym_idx = i % 3;
        let wobble = (i as f64 * 0.1).sin() * base_prices[sym_idx] * 0.01;
        let price = base_prices[sym_idx] + wobble;
        let ts = i as u64 * 500;
        pipeline.on_tick(&make_event(symbols[sym_idx], price, ts));
    }

    assert_eq!(pipeline.stats.total_ticks, 10_000);
    let status = pipeline.status();
    assert!(status.balance > 0.0, "balance should be positive");
    assert!(status.symbols_tracked == 3);
}

#[test]
fn stress_tick_latency_benchmark() {
    // Measure single-tick processing time
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.grant_paper_auth().unwrap();
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));

    // Warm up kline manager with 100 ticks
    for i in 0..100 {
        pipeline.on_tick(&make_event("BTCUSDT", 67000.0 + i as f64, i * 60_000));
    }

    // Measure 1000 ticks
    let start = std::time::Instant::now();
    for i in 100..1100 {
        pipeline.on_tick(&make_event(
            "BTCUSDT",
            67000.0 + (i as f64).sin() * 100.0,
            i * 60_000,
        ));
    }
    let elapsed = start.elapsed();
    let per_tick_us = elapsed.as_micros() as f64 / 1000.0;

    // Release mode target: <100μs. Debug mode ~10x slower, allow 1000μs.
    let threshold = if cfg!(debug_assertions) {
        1000.0
    } else {
        100.0
    };
    assert!(
        per_tick_us < threshold,
        "tick avg should be <{:.0}μs, got {:.1}μs",
        threshold,
        per_tick_us
    );

    // Print for manual inspection
    eprintln!("tick latency: {:.1}μs avg over 1000 ticks", per_tick_us);
}

// ═══════════════════════════════════════════════════════════════════════════════
// 7. Paper State PnL Correctness / 紙盤狀態損益正確性
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_pnl_long_profit_and_loss_sequences() {
    let mut state = PaperState::new(10_000.0);

    // Trade 1: Long BTC, profit
    state.apply_fill("BTCUSDT", true, 0.01, 67000.0, 3.685, 1000, "test");
    state.close_position("BTCUSDT", 68000.0, 2000);
    // PnL = (68000-67000) * 0.01 = 10.0, net = 10.0 - 3.685 fee
    assert!((state.balance() - (10_000.0 - 3.685 + 10.0)).abs() < 0.01);

    // Trade 2: Long ETH, loss
    state.apply_fill("ETHUSDT", true, 0.1, 2000.0, 0.11, 3000, "test");
    state.close_position("ETHUSDT", 1900.0, 4000);
    // PnL = (1900-2000) * 0.1 = -10.0
    let expected = 10_000.0 - 3.685 + 10.0 - 0.11 - 10.0;
    assert!(
        (state.balance() - expected).abs() < 0.01,
        "balance {} != expected {}",
        state.balance(),
        expected
    );
}

#[test]
fn stress_pnl_short_profit_and_loss() {
    let mut state = PaperState::new(10_000.0);

    // Short profit: sell high, buy low
    state.apply_fill("BTCUSDT", false, 0.01, 68000.0, 3.74, 1000, "test");
    state.close_position("BTCUSDT", 67000.0, 2000);
    // PnL = (68000-67000) * 0.01 = 10.0
    let expected = 10_000.0 - 3.74 + 10.0;
    assert!((state.balance() - expected).abs() < 0.01);

    // Short loss: sell low, price goes up
    state.apply_fill("ETHUSDT", false, 0.1, 2000.0, 0.11, 3000, "test");
    state.close_position("ETHUSDT", 2100.0, 4000);
    // PnL = (2000-2100) * 0.1 = -10.0
    let expected2 = expected - 0.11 - 10.0;
    assert!((state.balance() - expected2).abs() < 0.01);
}

#[test]
fn stress_pnl_zero_sum_round_trip() {
    // Buy and sell at same price — only fees should affect balance
    let mut state = PaperState::new(10_000.0);
    let fee = 0.1;
    state.apply_fill("BTCUSDT", true, 0.01, 67000.0, fee, 1000, "test");
    state.close_position("BTCUSDT", 67000.0, 2000);
    // PnL = 0, balance = 10000 - fee
    assert!((state.balance() - (10_000.0 - fee)).abs() < 0.001);
}

// ═══════════════════════════════════════════════════════════════════════════════
// 8. Persistence State Correctness / 持久化狀態正確性
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_export_state_matches_runtime() {
    let mut state = PaperState::new(10_000.0);
    state.apply_fill("BTCUSDT", true, 0.01, 67000.0, 3.685, 1000, "test");
    state.apply_fill("ETHUSDT", false, 0.1, 2000.0, 0.11, 2000, "test");

    let snap = state.export_state();
    assert_eq!(snap.balance, state.balance());
    assert_eq!(snap.positions.len(), state.position_count());
    assert_eq!(snap.trade_count, 0); // no closed trades yet

    state.close_position("BTCUSDT", 68000.0, 3000);
    let snap2 = state.export_state();
    assert_eq!(snap2.trade_count, 1);
    assert!(snap2.total_realized_pnl > 0.0);
}

// ═══════════════════════════════════════════════════════════════════════════════
// 9. Mixed Scenario: Full Pipeline Stress / 混合場景：完整管線壓力
// ═══════════════════════════════════════════════════════════════════════════════

#[test]
fn stress_full_pipeline_volatile_market_simulation() {
    // Simulate a volatile market: price swings ±3%, strategies should trade
    let symbols = &["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT"];
    let mut pipeline = TickPipeline::new(symbols);
    pipeline.grant_paper_auth().unwrap();

    pipeline.orchestrator.register(Box::new(MaCrossover::new()));
    pipeline.orchestrator.register(Box::new(BbReversion::new()));
    pipeline.orchestrator.register(Box::new(BbBreakout::new()));
    pipeline
        .orchestrator
        .register(Box::new(GridTrading::new(63000.0, 71000.0)));

    let base_prices = [67000.0, 2050.0, 150.0, 0.60];

    // Phase 1: Trending up (200 ticks)
    for i in 0..200 {
        let sym_idx = i % 4;
        let trend = i as f64 * 0.001 * base_prices[sym_idx];
        let noise = (i as f64 * 0.3).sin() * base_prices[sym_idx] * 0.002;
        let price = base_prices[sym_idx] + trend + noise;
        pipeline.on_tick(&make_event(symbols[sym_idx], price, i as u64 * 2000));
    }

    let mid_stats = pipeline.stats.clone();

    // Phase 2: Flash crash (50 ticks, -5%)
    for i in 200..250 {
        let sym_idx = i % 4;
        let crash = -((i - 200) as f64) * 0.001 * base_prices[sym_idx];
        let price = base_prices[sym_idx] * 1.2 + crash;
        pipeline.on_tick(&make_event(symbols[sym_idx], price, i as u64 * 2000));
    }

    // Phase 3: Recovery (200 ticks)
    for i in 250..450 {
        let sym_idx = i % 4;
        let recovery = (i - 250) as f64 * 0.0005 * base_prices[sym_idx];
        let noise = (i as f64 * 0.5).sin() * base_prices[sym_idx] * 0.001;
        let price = base_prices[sym_idx] * 1.15 + recovery + noise;
        pipeline.on_tick(&make_event(symbols[sym_idx], price, i as u64 * 2000));
    }

    let final_stats = pipeline.stats.clone();
    assert_eq!(final_stats.total_ticks, 450);
    assert!(final_stats.total_ticks > mid_stats.total_ticks);

    // Verify system integrity — no NaN, no negative balance (unless extreme loss)
    let status = pipeline.status();
    assert!(!status.balance.is_nan(), "balance is NaN");
    assert!(!status.balance.is_infinite(), "balance is infinite");
    assert!(
        status.balance > 0.0,
        "balance went to zero/negative: {}",
        status.balance
    );
}

#[test]
fn stress_full_pipeline_zero_volume_ticks() {
    // Zero-volume ticks should not cause division by zero
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.grant_paper_auth().unwrap();
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));

    for i in 0..100 {
        let mut event = make_event("BTCUSDT", 67000.0, i * 60_000);
        event.volume_24h = 0.0;
        pipeline.on_tick(&event);
    }
    // Should not panic
    assert_eq!(pipeline.stats.total_ticks, 100);
}

#[test]
fn stress_full_pipeline_extreme_prices() {
    // Test with extreme but valid prices
    let mut pipeline = TickPipeline::new(&["BTCUSDT", "DOGEUSDT"]);
    pipeline.grant_paper_auth().unwrap();
    pipeline.orchestrator.register(Box::new(MaCrossover::new()));

    // BTC at 200k
    for i in 0..50 {
        pipeline.on_tick(&make_event(
            "BTCUSDT",
            200_000.0 + i as f64 * 10.0,
            i * 60_000,
        ));
    }
    // DOGE at 0.001 (very small)
    for i in 50..100 {
        pipeline.on_tick(&make_event(
            "DOGEUSDT",
            0.001 + (i as f64 * 0.0001).sin() * 0.0001,
            i * 60_000,
        ));
    }

    assert_eq!(pipeline.stats.total_ticks, 100);
    let status = pipeline.status();
    assert!(!status.balance.is_nan());
}

// ═══════════════════════════════════════════════════════════════════════════════
// P0-3: Three-pipeline concurrent isolation / 三管線並發隔離
// ═══════════════════════════════════════════════════════════════════════════════

/// P0-3: Three pipelines (Paper/Demo/Live) running concurrently produce
/// isolated state — no cross-contamination in balance, fills, or stats.
/// Uses std::thread to drive real parallelism.
/// P0-3：三管線（Paper/Demo/Live）並發運行產生隔離狀態 — 餘額、成交、統計
/// 互不污染。使用 std::thread 驅動真正並行。
#[test]
fn stress_three_pipeline_concurrent_isolation() {
    use openclaw_engine::tick_pipeline::PipelineKind;
    use std::thread;

    let configs: Vec<(PipelineKind, f64)> = vec![
        (PipelineKind::Paper, 10_000.0),
        (PipelineKind::Demo, 20_000.0),
        (PipelineKind::Live, 50_000.0),
    ];

    let mut handles = Vec::new();
    for (kind, balance) in configs {
        handles.push(thread::spawn(move || {
            let mut pipeline =
                TickPipeline::with_kind(&["BTCUSDT", "ETHUSDT"], balance, kind);
            pipeline.grant_paper_auth().unwrap();
            pipeline
                .orchestrator
                .register(Box::new(MaCrossover::new()));

            // Feed 500 ticks with slightly different prices per pipeline kind
            // to create distinct trading paths.
            // 每條管線用略有不同的價格餵 500 tick，產生不同的交易路徑。
            let offset = balance / 10.0; // unique price offset per pipeline
            for i in 0..500u64 {
                let btc_price = 65_000.0 + offset + (i as f64 * 0.7).sin() * 500.0;
                pipeline.on_tick(&make_event("BTCUSDT", btc_price, i * 60_000));
                let eth_price = 3_200.0 + offset / 10.0 + (i as f64 * 0.3).cos() * 50.0;
                pipeline.on_tick(&make_event("ETHUSDT", eth_price, i * 60_000 + 500));
            }

            let status = pipeline.status();
            (kind.db_mode().to_string(), status.balance, pipeline.stats.total_ticks)
        }));
    }

    let results: Vec<_> = handles.into_iter().map(|h| h.join().unwrap()).collect();

    // Verify isolation: each pipeline reports distinct balance and correct tick count.
    // 驗證隔離：每條管線報告不同餘額和正確 tick 數量。
    assert_eq!(results.len(), 3);
    for (mode, balance, ticks) in &results {
        assert_eq!(*ticks, 1000, "{} should have 1000 ticks", mode);
        assert!(!balance.is_nan(), "{} balance must not be NaN", mode);
    }

    // Balances must differ (different initial + different price paths).
    // 餘額必須不同（不同初始值 + 不同價格路徑）。
    assert_ne!(results[0].1, results[1].1, "Paper and Demo balances must differ");
    assert_ne!(results[1].1, results[2].1, "Demo and Live balances must differ");

    // db_mode must be correct per kind.
    assert_eq!(results[0].0, "paper");
    assert_eq!(results[1].0, "demo");
    assert_eq!(results[2].0, "live");
}

/// P0-3b: Concurrent snapshot writes — three pipelines write snapshots to distinct
/// per-engine files in temp dir without collision.
/// P0-3b：並發快照寫入 — 三管線在 temp 目錄寫入不同的 per-engine 快照文件。
#[test]
fn stress_three_pipeline_concurrent_snapshot_writes() {
    use openclaw_engine::tick_pipeline::PipelineKind;
    use std::thread;

    let tmp_dir = std::env::temp_dir().join(format!(
        "oc_3pipe_test_{}",
        std::process::id()
    ));
    std::fs::create_dir_all(&tmp_dir).ok();

    let kinds = [PipelineKind::Paper, PipelineKind::Demo, PipelineKind::Live];
    let mut handles = Vec::new();

    for kind in kinds {
        let dir = tmp_dir.clone();
        handles.push(thread::spawn(move || {
            let mut pipeline =
                TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, kind);
            pipeline.grant_paper_auth().unwrap();

            for i in 0..100u64 {
                pipeline.on_tick(&make_event(
                    "BTCUSDT",
                    65_000.0 + (i as f64).sin() * 100.0,
                    i * 60_000,
                ));
            }

            // Write snapshot JSON to per-engine file
            let snapshot = pipeline.snapshot();
            let path = dir.join(format!("pipeline_snapshot_{}.json", kind.db_mode()));
            let json = serde_json::to_string_pretty(&snapshot).unwrap();
            std::fs::write(&path, &json).unwrap();
            kind.db_mode().to_string()
        }));
    }

    let modes: Vec<String> = handles.into_iter().map(|h| h.join().unwrap()).collect();
    assert_eq!(modes, vec!["paper", "demo", "live"]);

    // Verify three distinct files were created.
    // 驗證創建了三個不同的文件。
    for mode in &modes {
        let path = tmp_dir.join(format!("pipeline_snapshot_{}.json", mode));
        assert!(path.exists(), "snapshot file for {} must exist", mode);
        let content = std::fs::read_to_string(&path).unwrap();
        assert!(!content.is_empty(), "{} snapshot must not be empty", mode);
    }

    // Cleanup
    let _ = std::fs::remove_dir_all(&tmp_dir);
}

// ═══════════════════════════════════════════════════════════════════════════════
// P1-9: Config hot-reload concurrent with tick processing / 配置熱重載與 tick 並發
// ═══════════════════════════════════════════════════════════════════════════════

/// P1-9: ArcSwap-based config reload concurrent with on_tick — verify no panic,
/// no torn reads, no data corruption under parallel load+store.
/// P1-9：基於 ArcSwap 的配置重載與 on_tick 並發 — 驗證無 panic、無撕裂讀取、
/// 無數據損壞。
#[test]
fn stress_config_hot_reload_during_ticks() {
    use openclaw_engine::config::{ConfigStore, PatchSource};
    use openclaw_engine::config::risk_config::RiskConfig;
    use std::sync::Arc;
    use std::thread;

    let store = Arc::new(ConfigStore::new(RiskConfig::default()));

    // Thread 1: rapidly reload config 100 times
    // 線程 1：快速重載配置 100 次
    let store_writer = Arc::clone(&store);
    let writer_handle = thread::spawn(move || {
        for i in 0..100u32 {
            store_writer.apply_patch(
                PatchSource::Operator,
                |c: &mut RiskConfig| {
                    c.limits.open_positions_max = i % 50 + 1;
                },
                |_| Ok(()),
            ).unwrap();
        }
    });

    // Thread 2: feed ticks while config is being reloaded
    // 線程 2：在配置重載同時餵 tick
    let store_reader = Arc::clone(&store);
    let reader_handle = thread::spawn(move || {
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.grant_paper_auth().unwrap();
        pipeline.orchestrator.register(Box::new(MaCrossover::new()));

        for i in 0..500u64 {
            // Read config snapshot (simulates what on_tick does internally)
            let snap = store_reader.load();
            assert!(snap.limits.open_positions_max >= 1u32);
            pipeline.on_tick(&make_event(
                "BTCUSDT",
                65_000.0 + (i as f64 * 0.5).sin() * 200.0,
                i * 60_000,
            ));
        }
        pipeline.stats.total_ticks
    });

    writer_handle.join().expect("config writer must not panic");
    let ticks = reader_handle.join().expect("tick reader must not panic");
    assert_eq!(ticks, 500, "all ticks must be processed");

    // Final config version should be 100
    assert_eq!(store.version(), 100);
}

// ═══════════════════════════════════════════════════════════════════════════════
// P1-8: catch_unwind recovery semantics / panic 恢復語義
// ═══════════════════════════════════════════════════════════════════════════════

/// P1-8: A panic inside a pipeline closure is caught by catch_unwind — the
/// calling thread survives and can inspect the error.
/// P1-8：管線閉包內的 panic 被 catch_unwind 捕獲 — 調用線程存活並可檢查錯誤。
#[test]
fn stress_catch_unwind_recovers_from_pipeline_panic() {
    use std::panic;

    // Simulate the pattern used in main.rs for the Live OS thread:
    // std::thread::spawn → catch_unwind → handle error.
    // 模擬 main.rs 中 Live OS 線程的模式。
    let handle = std::thread::spawn(|| {
        let result = panic::catch_unwind(panic::AssertUnwindSafe(|| {
            let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
            pipeline.grant_paper_auth().unwrap();
            // Normal ticks first
            for i in 0..10u64 {
                pipeline.on_tick(&make_event("BTCUSDT", 65_000.0, i * 60_000));
            }
            // Force a panic (simulates unexpected runtime error)
            panic!("simulated live pipeline panic");
        }));
        // catch_unwind must capture the panic
        assert!(result.is_err(), "catch_unwind must capture panic");
        let err = result.unwrap_err();
        let msg = err
            .downcast_ref::<&str>()
            .copied()
            .unwrap_or("unknown panic");
        assert!(
            msg.contains("simulated"),
            "panic message must be preserved: {}",
            msg
        );
        true // signal success
    });

    let recovered = handle.join().expect("thread with catch_unwind must not abort");
    assert!(recovered, "recovery path must complete successfully");
}
