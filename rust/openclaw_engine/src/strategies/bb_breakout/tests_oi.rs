//! BB Breakout — Open Interest confluence signal + on_rejection regression tests.
//! BB 突破 — OI 合流信號與 on_rejection 回滾回歸測試。
//!
//! MODULE_NOTE (EN): EDGE-P2-2 / EDGE-P2-2 FUP coverage. Split from the main
//!   tests module so neither file exceeds the 800 soft warn. Helpers (`ctx_oi`,
//!   `ctx_full_entry`, `state_with_oi`, `make_open_intent`) are local here.
//! MODULE_NOTE (中): EDGE-P2-2 / EDGE-P2-2 FUP 相關測試。與主測試模組拆分以維持
//!   每檔 ≤ 800 soft warn；`ctx_oi` / `ctx_full_entry` / `state_with_oi` /
//!   `make_open_intent` 僅供本檔使用。

use super::super::{Strategy, StrategyAction, StrategyParams};
use super::params::BbBreakoutParams;
use super::{BbBreakout, BbBreakoutPerSymbolState};
use crate::intent_processor::OrderIntent;
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::{
    AdxResult, BollingerResult, DonchianResult, IndicatorSnapshot as IS,
};

/// Build a context with custom OI value (kept separate from `ctx_ext` to
/// preserve bit-identical behaviour for all non-OI callers).
/// 建立帶 OI 的 context；與 `ctx_ext` 分開避免改動既有調用點的位元等價性。
fn ctx_oi(
    bw: f64,
    pct_b: f64,
    vol: f64,
    ts: u64,
    price: f64,
    open_interest: Option<f64>,
) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IS {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: bw,
            percent_b: pct_b,
        }),
        volume_ratio: Some(vol),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price,
        timestamp_ms: ts,
        indicators: Some(ind),
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest,
        // G7-09c Phase 1: OI tests don't exercise BBO/tick_size — leave None so
        // strategy falls back to legacy `last_price ± offset_bps` (matches
        // pre-G7-09c behaviour for these specific tests).
        // G7-09c Phase 1：OI 測試不涉及 BBO/tick_size，留 None 讓策略走 legacy fallback。
        best_bid: None,
        best_ask: None,
        tick_size: None,
    }
}

/// Full-indicator context for end-to-end confluence testing (ADX + Donchian +
/// volume). Simulates a clean breakout setup with OI override.
/// 完整指標 context（ADX + Donchian + volume）用於端到端 confluence 測試。
fn ctx_full_entry(
    bw: f64,
    pct_b: f64,
    vol: f64,
    ts: u64,
    price: f64,
    open_interest: Option<f64>,
) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IS {
        bollinger: Some(BollingerResult {
            upper: 51000.0,
            middle: 50000.0,
            lower: 49000.0,
            bandwidth: bw,
            percent_b: pct_b,
        }),
        volume_ratio: Some(vol),
        adx: Some(AdxResult {
            adx: 30.0,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        rsi_14: Some(55.0),
        donchian: Some(DonchianResult {
            upper: 50500.0,
            lower: 49500.0,
            middle: 50000.0,
            width: 1000.0,
        }),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price,
        timestamp_ms: ts,
        indicators: Some(ind),
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest,
        // G7-09c Phase 1: OI tests don't exercise BBO/tick_size — leave None.
        // G7-09c Phase 1：OI 測試不涉及 BBO/tick_size，留 None。
        best_bid: None,
        best_ask: None,
        tick_size: None,
    }
}

/// Helper: direct-construct a per-symbol state populated with OI samples.
/// 輔助：直接構造帶 OI 樣本的 per-symbol 狀態。
fn state_with_oi(samples: &[(u64, f64)]) -> BbBreakoutPerSymbolState {
    let mut st = BbBreakoutPerSymbolState::default();
    for (ts, oi) in samples {
        st.oi_buffer.push_back((*ts, *oi));
    }
    st
}

/// TEST 1: oi_buffer fills on every ticker event carrying OI and evicts
/// samples older than the configured window (saturating_sub guards regress).
/// 測試 1：每個帶 OI 的 ticker 入隊，超出窗口者從前端淘汰。
#[test]
fn test_oi_buffer_fills_and_evicts() {
    let mut s = BbBreakout::new();
    s.oi_buffer_window_ms = 60_000; // 60s rolling window
    // Feed 10 samples every 12s → span = 108s > 60s window.
    // 每 12s 入一筆，共 10 筆，跨 108s > 60s 窗口。
    for i in 0..10u64 {
        let ts = i * 12_000;
        // Use squeeze-neutral bandwidth; this exercises the buffer path only.
        // 用普通帶寬只驗 buffer 路徑。
        s.on_tick(&ctx_oi(0.03, 0.5, 1.0, ts, 50000.0, Some(100.0 + i as f64)));
    }
    let st = s.symbols.get("BTC").expect("symbol tracked");
    // Newest ts = 108_000; anything older than (108_000 - 60_000) = 48_000 evicted.
    // 最新 108_000；< 48_000 者淘汰 → 保留 ts ≥ 48_000 共 5 筆 (48,60,72,84,96,108) = 6 筆。
    for (ts, _) in st.oi_buffer.iter() {
        assert!(*ts >= 48_000, "sample ts {ts} should have been evicted");
    }
    assert!(st.oi_buffer.len() <= 10, "must not exceed push count");
    assert!(
        st.oi_buffer.len() >= 2,
        "window should retain at least newest + one previous sample"
    );
}

/// TEST 2: basic (newest - oldest)/oldest delta = 10% when oi goes 100→110.
/// 測試 2：基本差分 100→110 = +10%。
#[test]
fn test_oi_delta_pct_basic() {
    let st = state_with_oi(&[(0, 100.0), (30_000, 105.0), (60_000, 110.0)]);
    let d = st.compute_oi_delta_pct().expect("delta available");
    assert!((d - 0.10).abs() < 1e-12, "expected +0.10, got {d}");
}

/// TEST 3: single sample → None (cannot compute delta).
/// 測試 3：單一樣本 → None（無法計算差分）。
#[test]
fn test_oi_delta_pct_insufficient_samples() {
    let st = state_with_oi(&[(0, 100.0)]);
    assert!(st.compute_oi_delta_pct().is_none());
    // And empty buffer also None.
    // 空 buffer 亦應 None。
    let empty = BbBreakoutPerSymbolState::default();
    assert!(empty.compute_oi_delta_pct().is_none());
}

/// TEST 4: oldest == 0 → None (guard against div-by-zero; no panic).
/// 測試 4：oldest == 0 → None（防除以零，不 panic）。
#[test]
fn test_oi_delta_pct_zero_guard() {
    let st = state_with_oi(&[(0, 0.0), (30_000, 50.0)]);
    assert!(st.compute_oi_delta_pct().is_none());
    // Negative oldest also rejected (unusual but defensive).
    // 負數 oldest 亦拒絕（防守式檢查）。
    let st_neg = state_with_oi(&[(0, -5.0), (30_000, 50.0)]);
    assert!(st_neg.compute_oi_delta_pct().is_none());
}

/// TEST 5: flag=false → bit-identical behaviour to pre-EDGE-P2-2 baseline.
/// Run two strategy instances (one with OI feeds, one without) and assert
/// the emitted intent confluence_score is identical when flag is disabled.
/// 測試 5：flag=false → 與舊基線 bit-identical。
#[test]
fn test_confluence_bonus_disabled_by_default() {
    let mut baseline = BbBreakout::new();
    baseline.min_persistence_ms = 0;
    assert!(!baseline.enable_oi_signal, "default must be OFF");

    let mut with_oi = BbBreakout::new();
    with_oi.min_persistence_ms = 0;
    assert!(!with_oi.enable_oi_signal, "default must be OFF");

    // Seed squeeze on both.
    // 雙方都先進入壓縮。
    baseline.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, None));
    with_oi.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));

    // Feed mid-tick with OI climb (only affects buffer, not score, because flag=false).
    // 中途加入 OI 上升樣本（flag=false 時不應影響 score）。
    with_oi.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(110.0)));

    // Breakout tick (long).
    // 突破 tick（多頭）。
    let i_baseline = baseline.on_tick(&ctx_full_entry(0.05, 1.1, 2.0, 700_000, 51000.0, None));
    let i_oi = with_oi.on_tick(&ctx_full_entry(
        0.05,
        1.1,
        2.0,
        700_000,
        51000.0,
        Some(120.0),
    ));
    assert_eq!(i_baseline.len(), 1);
    assert_eq!(i_oi.len(), 1);
    let (sb, so) = match (&i_baseline[0], &i_oi[0]) {
        (StrategyAction::Open(a), StrategyAction::Open(b)) => {
            (a.confluence_score, b.confluence_score)
        }
        _ => panic!("expected Open intents"),
    };
    // Bit-identical (both Some or both None; if Some, equal bits).
    // bit-identical：同為 Some 且 bits 相等，或同為 None。
    match (sb, so) {
        (Some(a), Some(b)) => assert_eq!(
            a.to_bits(),
            b.to_bits(),
            "confluence_score must be bit-identical when flag=false"
        ),
        (None, None) => {}
        other => panic!("confluence_score mismatch: {:?}", other),
    }
}

/// TEST 6: flag=on + rising OI + bullish signal → confluence_score shifted
/// up by exactly `oi_confluence_bonus` relative to the same tick sequence
/// with OI held constant.
/// 測試 6：flag=on + OI 上升 + 多頭 → confluence_score 較 OI 無變化者高 +bonus。
#[test]
fn test_confluence_bonus_applied_when_flag_on() {
    // Two instances: both OI-enabled, one with OI rising, one flat.
    // 兩個實例：都啟用 OI，一個 OI 上升、一個持平。
    let mut rising = BbBreakout::new();
    rising.min_persistence_ms = 0;
    rising.enable_oi_signal = true;
    rising.oi_confluence_bonus = 0.10;
    rising.oi_buffer_window_ms = 600_000;

    let mut flat = BbBreakout::new();
    flat.min_persistence_ms = 0;
    flat.enable_oi_signal = true;
    flat.oi_confluence_bonus = 0.10;
    flat.oi_buffer_window_ms = 600_000;

    // Squeeze tick (same OI base on both).
    // 壓縮 tick（兩者 OI 相同基準）。
    rising.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
    flat.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
    // Mid tick — rising climbs, flat holds.
    // 中段：rising 上升，flat 不變。
    rising.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(110.0)));
    flat.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(100.0)));
    // Breakout long on both.
    // 突破多頭。
    let i_rising = rising.on_tick(&ctx_full_entry(
        0.05,
        1.1,
        2.0,
        700_000,
        51000.0,
        Some(120.0),
    ));
    let i_flat = flat.on_tick(&ctx_full_entry(
        0.05,
        1.1,
        2.0,
        700_000,
        51000.0,
        Some(100.0),
    ));
    assert_eq!(i_rising.len(), 1);
    assert_eq!(i_flat.len(), 1);
    let (sr, sf) = match (&i_rising[0], &i_flat[0]) {
        (StrategyAction::Open(a), StrategyAction::Open(b)) => (
            a.confluence_score.expect("score present"),
            b.confluence_score.expect("score present"),
        ),
        _ => panic!("expected Open intents"),
    };
    let diff = sr - sf;
    // Rising OI confirms long → bonus applied; flat → no bonus.
    // OI 上升確認多頭加 bonus；OI 不變（delta=0）不加；差異 ≈ bonus。
    // NOTE: confluence_score is stored as f32 in OrderIntent (EDGE-P3-1 A6),
    // so tolerance is relaxed to accommodate single-precision cast error.
    // 備註：OrderIntent.confluence_score 為 f32，放寬容差以容納 f32 cast 誤差。
    assert!(
        (diff - 0.10).abs() < 1e-4,
        "expected confluence_score diff ≈ +0.10, got {diff}"
    );
}

/// TEST 7: flag=on + falling OI + bullish signal (divergence) → score
/// shifted DOWN by `oi_confluence_bonus` vs the flat-OI control.
/// 測試 7：flag=on + OI 下降 + 多頭（背離）→ confluence_score 較對照組低 -bonus。
#[test]
fn test_confluence_penalty_on_divergence() {
    let mut falling = BbBreakout::new();
    falling.min_persistence_ms = 0;
    falling.enable_oi_signal = true;
    falling.oi_confluence_bonus = 0.10;
    falling.oi_buffer_window_ms = 600_000;

    let mut flat = BbBreakout::new();
    flat.min_persistence_ms = 0;
    flat.enable_oi_signal = true;
    flat.oi_confluence_bonus = 0.10;
    flat.oi_buffer_window_ms = 600_000;

    // Squeeze baseline.
    falling.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
    flat.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
    // Mid: falling drops, flat holds.
    falling.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(95.0)));
    flat.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(100.0)));
    // Breakout long on both.
    let i_falling = falling.on_tick(&ctx_full_entry(
        0.05,
        1.1,
        2.0,
        700_000,
        51000.0,
        Some(90.0),
    ));
    let i_flat = flat.on_tick(&ctx_full_entry(
        0.05,
        1.1,
        2.0,
        700_000,
        51000.0,
        Some(100.0),
    ));
    let (sfall, sflat) = match (&i_falling[0], &i_flat[0]) {
        (StrategyAction::Open(a), StrategyAction::Open(b)) => (
            a.confluence_score.expect("score present"),
            b.confluence_score.expect("score present"),
        ),
        _ => panic!("expected Open intents"),
    };
    let diff = sfall - sflat;
    // Falling OI + long = divergence → -bonus; flat delta=0 → no change.
    // OI 下降 + 多頭 = 背離扣 bonus；flat delta=0 不變；差異 ≈ -bonus。
    // f32 cast tolerance as above.
    assert!(
        (diff - (-0.10)).abs() < 1e-4,
        "expected confluence_score diff ≈ -0.10, got {diff}"
    );
}

/// TEST 8: validate() rejects out-of-range OI parameters.
/// 測試 8：validate() 拒絕超出範圍的 OI 參數。
#[test]
fn test_oi_params_validation() {
    let mut p = BbBreakoutParams::default();
    // Window too short.
    // 窗口太短。
    p.oi_buffer_window_ms = 500;
    assert!(p.validate().is_err(), "window < 1000ms must fail");
    p.oi_buffer_window_ms = 60_000;
    // Bonus out of bounds.
    // bonus 超界。
    p.oi_confluence_bonus = 0.6;
    assert!(p.validate().is_err(), "|bonus| > 0.5 must fail");
    p.oi_confluence_bonus = f64::NAN;
    assert!(p.validate().is_err(), "NaN bonus must fail");
    p.oi_confluence_bonus = 0.10;
    assert!(p.validate().is_ok(), "defaults must pass");
}

// ════════════════════════════════════════════════════════════════════════
// EDGE-P2-2 FUP (E2 findings #1 #2 #3 #5 #6): regression tests
// EDGE-P2-2 FUP（E2 #1 #2 #3 #5 #6）：回歸測試
// ════════════════════════════════════════════════════════════════════════

fn make_open_intent(symbol: &str) -> OrderIntent {
    OrderIntent {
        symbol: symbol.into(),
        is_long: true,
        qty: 0.01,
        confidence: 0.6,
        strategy: "bb_breakout".into(),
        order_type: "market".into(),
        limit_price: None,
        confluence_score: None,
        persistence_elapsed_ms: None,
        time_in_force: None,
        maker_timeout_ms: None,
    }
}

/// FUP #1: identical OI values must dedup so trade-tick replays don't
/// dilute the rolling window (change-of-state semantics).
/// FUP #1：相同 OI 值必須 dedup，避免 trade-tick 重播稀釋窗口。
#[test]
fn test_oi_buffer_deduplicates_same_value() {
    let mut s = BbBreakout::new();
    s.oi_buffer_window_ms = 60_000;
    s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 0, 50000.0, Some(100.0)));
    s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 1_000, 50000.0, Some(100.0)));
    s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 2_000, 50000.0, Some(100.0)));
    let st = s.symbols.get("BTC").expect("symbol tracked");
    assert_eq!(
        st.oi_buffer.len(),
        1,
        "repeated identical OI values must be deduped; got {}",
        st.oi_buffer.len()
    );
    // A genuine change should push a new sample.
    // 真實變動必須入隊。
    s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 3_000, 50000.0, Some(100.0001)));
    let st = s.symbols.get("BTC").unwrap();
    assert_eq!(st.oi_buffer.len(), 2, "change-of-state must append");
}

/// FUP #6: out-of-order or regressed timestamps (cross-stream interleave)
/// must be rejected — strict monotonic push guard.
/// FUP #6：亂序 / 回溯 ts（跨 stream 交錯）必須被拒絕，嚴格單調入隊。
#[test]
fn test_oi_buffer_skips_ts_regression() {
    let mut s = BbBreakout::new();
    s.oi_buffer_window_ms = 60_000;
    s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 10_000, 50000.0, Some(100.0)));
    // Stale sample with older ts → must be dropped even though OI changed.
    // 舊 ts（即使 OI 變動）必須丟棄。
    s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 5_000, 50000.0, Some(95.0)));
    // Equal ts → must also drop (strict >).
    // 相同 ts → 也丟（嚴格 >）。
    s.on_tick(&ctx_oi(0.03, 0.5, 1.0, 10_000, 50000.0, Some(105.0)));
    let st = s.symbols.get("BTC").expect("symbol tracked");
    assert_eq!(st.oi_buffer.len(), 1, "ts regressions must not push");
    let (ts, oi) = *st.oi_buffer.back().unwrap();
    assert_eq!(ts, 10_000);
    assert!((oi - 100.0).abs() < f64::EPSILON);
}

/// FUP #2: `on_rejection` must preserve the live `oi_buffer` (market
/// observation) while rolling back trading-state fields.
/// FUP #2：on_rejection 僅回滾策略狀態，oi_buffer（市場觀察）必須保留。
#[test]
fn test_on_rejection_preserves_oi_buffer() {
    let mut s = BbBreakout::new();
    s.min_persistence_ms = 0;
    s.oi_buffer_window_ms = 600_000;
    // Seed squeeze → OI sample #1.
    s.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
    // Mid tick → OI sample #2 (change of state pushes).
    s.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 10_000, 50000.0, Some(105.0)));
    // Breakout tick → emits Open intent + stashes prev_state snapshot.
    let actions = s.on_tick(&ctx_full_entry(
        0.05,
        1.1,
        2.0,
        20_000,
        51000.0,
        Some(110.0),
    ));
    assert!(
        matches!(actions.first(), Some(StrategyAction::Open(_))),
        "expected Open intent on breakout tick"
    );
    let buf_len_before = s.symbols.get("BTC").unwrap().oi_buffer.len();
    assert!(buf_len_before >= 2, "buffer must have samples");

    // Reject → trading state rolls back; oi_buffer must NOT.
    // 拒絕 → 交易狀態回滾；oi_buffer 不能丟。
    let intent = make_open_intent("BTC");
    s.on_rejection(&intent, "test rejection");

    let buf_after = &s.symbols.get("BTC").expect("symbol still tracked").oi_buffer;
    assert_eq!(
        buf_after.len(),
        buf_len_before,
        "oi_buffer must be preserved across rollback (market observation, not strategy state)"
    );
    // Values/ts must be byte-identical.
    let back = *buf_after.back().unwrap();
    assert_eq!(back.0, 20_000);
    assert!((back.1 - 110.0).abs() < f64::EPSILON);
}

/// FUP #3 (noise floor) + FUP #2 (buffer preserved) — if
/// `|oi_delta_pct| <= oi_min_delta_pct`, bonus must NOT apply and the
/// score equals the flat-OI control bit-for-bit (when both paths are at
/// the same suppression regime).
/// FUP #3：|oi_delta_pct| ≤ noise floor 時 bonus 不施加，與 flat 對照組相同。
#[test]
fn test_oi_min_delta_pct_below_threshold_no_effect() {
    let mut guarded = BbBreakout::new();
    guarded.min_persistence_ms = 0;
    guarded.enable_oi_signal = true;
    guarded.oi_confluence_bonus = 0.10;
    guarded.oi_buffer_window_ms = 600_000;
    // Noise floor 5% — OI must change by more than 5% to contribute.
    // 噪音地板 5% — OI 必須 >5% 變動才貢獻 bonus。
    guarded.oi_min_delta_pct = 0.05;

    let mut flat = BbBreakout::new();
    flat.min_persistence_ms = 0;
    flat.enable_oi_signal = true;
    flat.oi_confluence_bonus = 0.10;
    flat.oi_buffer_window_ms = 600_000;
    flat.oi_min_delta_pct = 0.05;

    // Squeeze baseline.
    guarded.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
    flat.on_tick(&ctx_full_entry(0.01, 0.5, 1.0, 0, 50000.0, Some(100.0)));
    // Mid-tick: guarded rises 2% (< floor); flat stays.
    // 中段：guarded 上升 2%（< 地板）；flat 不動。
    guarded.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(102.0)));
    flat.on_tick(&ctx_full_entry(0.02, 0.5, 1.0, 300_000, 50000.0, Some(100.0)));
    // Breakout long.
    let i_g = guarded.on_tick(&ctx_full_entry(
        0.05,
        1.1,
        2.0,
        700_000,
        51000.0,
        Some(102.0),
    ));
    let i_f = flat.on_tick(&ctx_full_entry(
        0.05,
        1.1,
        2.0,
        700_000,
        51000.0,
        Some(100.0),
    ));
    let (sg, sf) = match (&i_g[0], &i_f[0]) {
        (StrategyAction::Open(a), StrategyAction::Open(b)) => (
            a.confluence_score.expect("score present"),
            b.confluence_score.expect("score present"),
        ),
        _ => panic!("expected Open intents"),
    };
    // Below floor → bonus suppressed → equal to flat control (f32 bit-identical).
    // 低於地板 → bonus 被壓制 → 與 flat 相等（f32 bit-identical）。
    assert_eq!(
        sg.to_bits(),
        sf.to_bits(),
        "below noise floor, score must match flat control exactly"
    );
}

/// FUP #5: validate() must reject `oi_buffer_window_ms` above upper bound
/// (600_000 ms / 10 min) — prevents memory blow-up scenarios.
/// FUP #5：validate() 須拒絕 window > 600_000ms（防記憶體膨脹）。
#[test]
fn test_oi_window_upper_bound_validation() {
    let mut p = BbBreakoutParams::default();
    p.oi_buffer_window_ms = 600_001;
    assert!(
        p.validate().is_err(),
        "window > 600_000ms must fail"
    );
    p.oi_buffer_window_ms = 600_000;
    assert!(p.validate().is_ok(), "exact upper bound must pass");
}

/// FUP #3: validate() must enforce `oi_min_delta_pct` ∈ [0.0, 0.5] and
/// reject NaN/Inf.
/// FUP #3：validate() 須強制 oi_min_delta_pct 在 [0.0, 0.5] 且非 NaN/Inf。
#[test]
fn test_oi_min_delta_pct_validation() {
    let mut p = BbBreakoutParams::default();
    p.oi_min_delta_pct = -0.01;
    assert!(p.validate().is_err(), "negative floor must fail");
    p.oi_min_delta_pct = 0.51;
    assert!(p.validate().is_err(), "floor > 0.5 must fail");
    p.oi_min_delta_pct = f64::NAN;
    assert!(p.validate().is_err(), "NaN floor must fail");
    p.oi_min_delta_pct = 0.0;
    assert!(p.validate().is_ok(), "0.0 (default) must pass");
    p.oi_min_delta_pct = 0.5;
    assert!(p.validate().is_ok(), "0.5 upper bound must pass");
}
