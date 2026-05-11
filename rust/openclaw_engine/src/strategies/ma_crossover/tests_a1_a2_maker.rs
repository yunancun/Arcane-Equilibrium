//! MaCrossover tests — A1 (ER-scaled exit persistence) + A2 (trend-adaptive
//! cooldown) + EDGE-P2-3 Phase 2+ (b) PostOnly maker entry.
//! MaCrossover 測試 — A1（ER 縮放出場持續）+ A2（趨勢自適應冷卻）+ EDGE-P2-3
//! Phase 2+ (b) PostOnly maker 入場。
//!
//! MODULE_NOTE (EN): Split out of `strategies/ma_crossover.rs` by E5-P2-4c
//!   (2026-04-23). Paired with `tests.rs` — that file covers baseline /
//!   RC-01 / RC-02 / Phase 3a param bundle; this file focuses on A1 exit
//!   persistence windowing driven by KAMA efficiency ratio, A2 cooldown
//!   scaling in strong trends, and EDGE-P2-3 Phase 2+ PostOnly Limit entry
//!   emission (market vs. limit branch + clamp semantics of
//!   `maker_limit_timeout_ms`).
//! MODULE_NOTE (中)：E5-P2-4c（2026-04-23）由 `strategies/ma_crossover.rs` 拆出。
//!   與 `tests.rs` 成對 — 對方覆蓋基本 / RC-01 / RC-02 / Phase 3a 參數包；本檔聚焦
//!   A1 由 KAMA 效率比驅動的出場持續性窗口、A2 強趨勢下冷卻倍率、以及 EDGE-P2-3
//!   Phase 2+ PostOnly Limit 入場（market vs. limit 分支 + `maker_limit_timeout_ms`
//!   寫入時的 clamp 語意）。

use super::*;
use crate::order_manager::TimeInForce;
use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot, KamaResult};

// P-08: Test helpers use Box::leak for owned indicator data (fine for tests).

/// P0 Option A-Lite (2026-05-11) helper：構建 PaperPosition 模擬 paper_state 真實持倉。
/// 用於 A1/A2 tests 注入 self-owned 倉位以走 exit 分支。
fn make_paper_position_a1(symbol: &str, is_long: bool, owner: &str) -> crate::paper_state::PaperPosition {
    crate::paper_state::PaperPosition {
        symbol: symbol.to_string(),
        is_long,
        qty: 1.0,
        entry_price: 50_000.0,
        best_price: 50_000.0,
        entry_fee: 0.0,
        entry_ts_ms: 0,
        unrealized_pnl: 0.0,
        entry_context_id: String::new(),
        owner_strategy: owner.to_string(),
        entry_notional: 50_000.0,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    }
}

/// Helper: build a TickContext with given indicator values.
/// 輔助函數：用給定指標值構建 TickContext。
fn ctx_with(sma: f64, kama: f64, adx: f64, ts: u64) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        sma_20: Some(sma),
        kama: Some(KamaResult {
            kama,
            efficiency_ratio: 0.5,
        }),
        adx: Some(AdxResult {
            adx,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
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

// ═══════════════════════════════════════════════════════════════════════
// A1: ER-scaled exit persistence tests
// A1：KAMA 效率比縮放的出場持續性測試
// ═══════════════════════════════════════════════════════════════════════

/// Helper: build TickContext with an explicit KAMA efficiency ratio.
/// 輔助函數：用顯式 KAMA 效率比構建 TickContext。
fn ctx_with_er(sma: f64, kama: f64, adx: f64, ts: u64, er: f64) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        sma_20: Some(sma),
        kama: Some(KamaResult {
            kama,
            efficiency_ratio: er,
        }),
        adx: Some(AdxResult {
            adx,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: 50_000.0,
        timestamp_ms: ts,
        indicators: Some(ind),
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

#[test]
fn test_a1_exit_persistence_formula() {
    // Raw formula check: window = min_persistence_ms × (1 − ER).
    // 公式驗證：window = min_persistence_ms × (1 − ER)。
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 200_000;
    assert_eq!(s.compute_exit_persistence_ms(0.0), 200_000);
    assert_eq!(s.compute_exit_persistence_ms(1.0), 0);
    assert_eq!(s.compute_exit_persistence_ms(0.5), 100_000);
    // Clamp: ER outside [0,1] must not produce negative / overflow windows.
    // 邊界：ER 超出 [0,1] 不可產生負值或溢出窗口。
    assert_eq!(s.compute_exit_persistence_ms(-0.5), 200_000);
    assert_eq!(s.compute_exit_persistence_ms(1.5), 0);
}

#[test]
fn test_a1_trending_er_exits_immediately() {
    // P0 Option A-Lite (2026-05-11)：exit path 由顯式 ctx.position_state
    // 注入 self-owned 倉位來觸發（原 self.positions local state 已移除）。
    // Clean trend (ER=1.0) → window collapses to 0 → exit fires on the
    // first reverse-cross tick.
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let opened = s.on_tick(
        &ctx_with_er(100.0, 101.0, 25.0, 0, 1.0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(opened.len(), 1, "long entry should fire");

    // Step 2：ER=1.0 → window=0 + 反向 cross + self-owned LONG 注入 → exit。
    s.min_persistence_ms = 180_000;
    let pp = make_paper_position_a1("BTC", true, "ma_crossover");
    let mut ctx_exit = ctx_with_er(101.0, 100.0, 25.0, 500_000, 1.0);
    ctx_exit.position_state = Some(&pp);
    let exit = s.on_tick(&ctx_exit, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(exit.len(), 1, "trending ER must exit on first reverse tick");
    match &exit[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "ma_reverse_cross"),
        other => panic!("expected Close, got {:?}", other),
    }
}

#[test]
fn test_a1_choppy_er_delays_exit_until_window_elapses() {
    // P0 Option A-Lite (2026-05-11)：exit path 由 ctx.position_state 注入 self-owned LONG 觸發。
    // Choppy market (ER=0.0) → full min_persistence_ms window demanded.
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let _ = s.on_tick(
        &ctx_with_er(100.0, 101.0, 25.0, 0, 0.5),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    s.min_persistence_ms = 180_000;
    let pp = make_paper_position_a1("BTC", true, "ma_crossover");

    // t=500_000：首個反向 tick + self-owned LONG → 進 exit 分支但 persistence 不足。
    let mut ctx_first = ctx_with_er(101.0, 100.0, 25.0, 500_000, 0.0);
    ctx_first.position_state = Some(&pp);
    let first = s.on_tick(&ctx_first, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(
        first.is_empty(),
        "choppy regime must defer exit until window elapses"
    );

    // t=600_000：仍在窗口內。
    let mut ctx_mid = ctx_with_er(101.0, 100.0, 25.0, 600_000, 0.0);
    ctx_mid.position_state = Some(&pp);
    let mid = s.on_tick(&ctx_mid, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert!(mid.is_empty(), "still inside choppy persistence window");

    // t=680_001：persistence 通過，emit Close。
    let mut ctx_exit = ctx_with_er(101.0, 100.0, 25.0, 680_001, 0.0);
    ctx_exit.position_state = Some(&pp);
    let exit = s.on_tick(&ctx_exit, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(exit.len(), 1, "choppy exit must fire once window elapsed");
    match &exit[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "ma_reverse_cross"),
        other => panic!("expected Close, got {:?}", other),
    }
}

#[test]
fn test_a1_reverse_flicker_resets_exit_persistence() {
    // P0 Option A-Lite (2026-05-11)：exit path 由 ctx.position_state 注入 self-owned LONG 觸發。
    // A flicker back to position-aligned (no reverse signal) between two
    // reverse ticks must reset the onset.
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let _ = s.on_tick(
        &ctx_with_er(100.0, 101.0, 25.0, 0, 0.5),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    s.min_persistence_ms = 180_000;
    let pp = make_paper_position_a1("BTC", true, "ma_crossover");

    // t=100_000：reverse tick starts timer。
    let mut ctx1 = ctx_with_er(101.0, 100.0, 25.0, 100_000, 0.0);
    ctx1.position_state = Some(&pp);
    assert!(s.on_tick(&ctx1, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty());

    // t=120_000：aligned tick → resets timer。
    let mut ctx2 = ctx_with_er(100.0, 101.0, 25.0, 120_000, 0.0);
    ctx2.position_state = Some(&pp);
    assert!(s.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty());

    // t=200_000：再次反向，距新 onset 80 秒 < 180 秒 → 不可出場。
    let mut ctx3 = ctx_with_er(101.0, 100.0, 25.0, 200_000, 0.0);
    ctx3.position_state = Some(&pp);
    assert!(s.on_tick(&ctx3, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty());
}

#[test]
fn test_a1_external_close_clears_exit_persistence() {
    // P0 Option A-Lite (2026-05-11)：exit_persistence onset 需 self-owned 倉位
    // 才能在 exit 分支記錄；改造後本 test 用顯式 ctx.position_state 注入。
    // After external close (risk-stop / hard-stop / ft_scoped_reduce),
    // on_external_close must wipe the exit_persistence onset, else a
    // stale onset from the now-closed position would let the *next*
    // entry exit prematurely on its first reverse-looking tick.
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    let _ = s.on_tick(
        &ctx_with_er(100.0, 101.0, 25.0, 0, 0.5),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    s.min_persistence_ms = 180_000;

    // Step 1：reverse tick + self-owned LONG 注入 → exit 分支記錄 onset。
    let pp = make_paper_position_a1("BTC", true, "ma_crossover");
    let mut ctx_reverse = ctx_with_er(101.0, 100.0, 25.0, 100_000, 0.0);
    ctx_reverse.position_state = Some(&pp);
    assert!(s.on_tick(&ctx_reverse, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty());

    // Step 2：External close wipes exit_persistence onset。
    s.on_external_close("BTC");

    // Step 3：fresh re-entry path 走 entry 分支（無 position_state）。
    s.min_persistence_ms = 0;
    let reopen = s.on_tick(
        &ctx_with_er(100.0, 101.0, 25.0, 1_000_000, 0.5),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(reopen.len(), 1, "should re-enter after external close");
    s.min_persistence_ms = 180_000;

    // Step 4：再次注入 self-owned LONG + reverse tick → 因 onset 已清，必須重新累積。
    let pp2 = make_paper_position_a1("BTC", true, "ma_crossover");
    let mut ctx_reverse2 = ctx_with_er(101.0, 100.0, 25.0, 1_100_000, 0.0);
    ctx_reverse2.position_state = Some(&pp2);
    assert!(
        s.on_tick(&ctx_reverse2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE).is_empty(),
        "exit_persistence must start from zero after on_external_close"
    );
}

// ═══════════════════════════════════════════════════════════════════════
// A2: Trend-adaptive cooldown tests
// A2：趨勢自適應冷卻測試
// ═══════════════════════════════════════════════════════════════════════

fn indicator_with(adx: Option<f64>, hurst: Option<f64>) -> IndicatorSnapshot {
    IndicatorSnapshot {
        adx: adx.map(|a| AdxResult {
            adx: a,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        hurst: hurst.map(|h| HurstResult {
            hurst: h,
            regime: "trending".into(),
        }),
        ..Default::default()
    }
}

#[test]
fn test_a2_cooldown_no_indicators_returns_base() {
    // Missing IndicatorSnapshot → conservative fallback to base cooldown.
    // 無指標 → 退回基準冷卻。
    let s = MaCrossover::new();
    assert_eq!(s.compute_trend_adjusted_cooldown(None), s.cooldown_ms);
}

#[test]
fn test_a2_cooldown_at_threshold_no_boost() {
    // ADX exactly at adx_threshold + Hurst = 0.50 → both factors = 0 →
    // multiplier = 1.0 → cooldown unchanged.
    // ADX 剛好在門檻 + Hurst=0.5 → 因子為 0 → 乘數 1.0 → 冷卻不變。
    let s = MaCrossover::new();
    let snap = indicator_with(Some(s.adx_threshold), Some(0.50));
    assert_eq!(
        s.compute_trend_adjusted_cooldown(Some(&snap)),
        s.cooldown_ms,
        "adx at threshold + hurst 0.5 should return base cooldown"
    );
}

#[test]
fn test_a2_cooldown_strong_trend_4x_at_cap() {
    // ADX = adx_threshold × 2.5 + Hurst = 0.75 → both factors = 1.0 →
    // trend_score = 1.0 → multiplier = 1 + 1×3 = 4 → cooldown × 4.
    // 強趨勢上界 → multiplier = 4 → 冷卻 × 4。
    let s = MaCrossover::new();
    let snap = indicator_with(Some(s.adx_threshold * 2.5), Some(0.75));
    let got = s.compute_trend_adjusted_cooldown(Some(&snap));
    assert_eq!(got, s.cooldown_ms * 4, "strong trend must 4× cooldown");
}

#[test]
fn test_a2_cooldown_beyond_upper_bound_clamps() {
    // ADX above 2.5× threshold and Hurst above 0.75 clamp at trend_score=1.
    // 上界之上再往上也不會加倍 — clamp 在 1.0。
    let s = MaCrossover::new();
    let snap = indicator_with(Some(s.adx_threshold * 5.0), Some(0.95));
    assert_eq!(
        s.compute_trend_adjusted_cooldown(Some(&snap)),
        s.cooldown_ms * 4
    );
}

#[test]
fn test_a2_cooldown_mixed_adx_only_partial_boost() {
    // Pure ADX factor = 0.5 (midpoint) + Hurst = 0.50 → trend_score = 0.3 →
    // multiplier = 1 + 0.3×3 = 1.9. Use adx_threshold=20, so midpoint is
    // 20 + 0.5 × (30) = 35 (since range = 30).
    // 純 ADX 半途 + Hurst 平 → score = 0.3 → multiplier 1.9。
    let s = MaCrossover::new();
    // adx_threshold=20, range=30 → ADX=35 gives factor=0.5.
    let snap = indicator_with(Some(35.0), Some(0.50));
    let expected = (s.cooldown_ms as f64 * (1.0 + 0.3 * 3.0)) as u64;
    assert_eq!(s.compute_trend_adjusted_cooldown(Some(&snap)), expected);
}

#[test]
fn test_a2_cooldown_missing_adx_uses_zero() {
    // Missing ADX treated as 0 → factor clamps to 0 → base × (1 + 0.4×hurst_factor×3).
    // With Hurst=0.75 → hurst_factor=1 → multiplier=2.2.
    // 無 ADX 視為 0 → 僅 Hurst 貢獻。
    let s = MaCrossover::new();
    let snap = indicator_with(None, Some(0.75));
    let expected = (s.cooldown_ms as f64 * (1.0 + 0.4 * 3.0)) as u64;
    assert_eq!(s.compute_trend_adjusted_cooldown(Some(&snap)), expected);
}

#[test]
fn test_a2_cooldown_respects_max_cooldown_boost_param() {
    // max_cooldown_boost = 0 disables A2 entirely → cooldown always base.
    // max_cooldown_boost=0 → A2 被禁用 → 永遠基準。
    let mut s = MaCrossover::new();
    s.max_cooldown_boost = 0.0;
    let snap = indicator_with(Some(s.adx_threshold * 3.0), Some(0.90));
    assert_eq!(
        s.compute_trend_adjusted_cooldown(Some(&snap)),
        s.cooldown_ms
    );
}

#[test]
fn test_a2_validate_max_cooldown_boost_bounds() {
    // Validation: max_cooldown_boost ∈ [0, 10].
    // 驗證：max_cooldown_boost 範圍 [0, 10]。
    let mut p = MaCrossoverParams::default();
    p.max_cooldown_boost = -0.1;
    assert!(p.validate().is_err());
    p.max_cooldown_boost = 10.1;
    assert!(p.validate().is_err());
    p.max_cooldown_boost = 0.0;
    assert!(p.validate().is_ok());
    p.max_cooldown_boost = 10.0;
    assert!(p.validate().is_ok());
}

// ── EDGE-P2-3 Phase 2+ (b): PostOnly maker entry tests ──
// ── EDGE-P2-3 Phase 2+ (b)：PostOnly maker 入場測試 ──

/// Default constructor must keep `use_maker_entry = false` (root principle #6 —
/// failure default shrink). Market entry emits order_type="market" + TIF=None
/// (byte-identical legacy behavior) when long-entry gate fires.
/// 默認 maker 關閉時，入場 intent 維持 market + TIF=None（與舊行為 byte-identical）。
#[test]
fn test_ma_crossover_market_entry_when_maker_disabled() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0; // disable persistence for unit tests
    assert!(!s.use_maker_entry, "use_maker_entry must default to false");
    let i = s.on_tick(&ctx_with(100.0, 101.0, 25.0, 0), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert_eq!(intent.order_type, "market");
            assert!(intent.limit_price.is_none());
            assert!(intent.time_in_force.is_none());
            assert!(intent.maker_timeout_ms.is_none());
        }
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// Long entry with maker enabled emits BBO-derived PostOnly Limit.
/// 多頭入場啟用 maker → 發 BBO-derived PostOnly Limit。
#[test]
fn test_ma_crossover_buy_postonly_below_last_price() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    s.use_maker_entry = true;
    s.maker_price_offset_bps = 1.0; // 1 bps
    let i = s.on_tick(&ctx_with_bbo_g709c(
        100.0, 101.0, 25.0, 0, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long);
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            assert_eq!(intent.maker_timeout_ms, Some(45_000));
            let lp = intent.limit_price.expect("limit_price set");
            let expected = 49_999.4;
            assert!(
                (lp - expected).abs() < 1e-9,
                "buy PostOnly must use best_bid-buffer: got {lp}, expected {expected}"
            );
            assert!(lp < 50000.0, "buy limit must rest below last_price");
        }
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// Short entry with maker enabled emits BBO-derived PostOnly Limit.
/// 空頭入場啟用 maker → 發 BBO-derived PostOnly Limit。
#[test]
fn test_ma_crossover_sell_postonly_above_last_price() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    s.use_maker_entry = true;
    s.maker_price_offset_bps = 2.0; // 2 bps
                                    // Fast KAMA below slow SMA → short signal.
                                    // 快 KAMA 低於慢 SMA → 空頭信號。
    let i = s.on_tick(&ctx_with_bbo_g709c(
        101.0, 100.0, 25.0, 0, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(!intent.is_long);
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            assert_eq!(intent.maker_timeout_ms, Some(45_000));
            let lp = intent.limit_price.expect("limit_price set");
            let expected = 50_000.6;
            assert!(
                (lp - expected).abs() < 1e-9,
                "sell PostOnly must use best_ask+buffer: got {lp}, expected {expected}"
            );
            assert!(lp > 50000.0, "sell limit must rest above last_price");
        }
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// update_params round-trips maker fields so Agent IPC can toggle at runtime.
/// Also verifies maker_limit_timeout_ms is clamped on assignment
/// (500_000 → 300_000 upper bound, 1_000 → 15_000 lower bound).
/// update_params 來回保留 maker 欄位；timeout 於寫入時 clamp 到 [15s, 300s]。
#[test]
fn test_ma_crossover_update_params_roundtrips_maker_fields() {
    let mut s = MaCrossover::new();
    let mut params = s.get_params();
    assert!(!params.use_maker_entry);
    assert!((params.maker_price_offset_bps - 1.0).abs() < 1e-9);
    assert_eq!(params.maker_limit_timeout_ms, 45_000);

    // Round-trip basic values.
    // 基本往返。
    params.use_maker_entry = true;
    params.maker_price_offset_bps = 3.0;
    params.maker_limit_timeout_ms = 60_000;
    s.update_params(params).expect("update_params");
    let p2 = s.get_params();
    assert!(p2.use_maker_entry);
    assert!((p2.maker_price_offset_bps - 3.0).abs() < 1e-9);
    assert_eq!(p2.maker_limit_timeout_ms, 60_000);
    assert!(s.use_maker_entry);

    // Upper clamp: 500_000 → 300_000.
    // 上限 clamp：500_000 → 300_000。
    let mut params_hi = s.get_params();
    params_hi.maker_limit_timeout_ms = 500_000;
    s.update_params(params_hi).expect("update_params clamp hi");
    assert_eq!(s.get_params().maker_limit_timeout_ms, 300_000);

    // Lower clamp: 1_000 → 15_000.
    // 下限 clamp：1_000 → 15_000。
    let mut params_lo = s.get_params();
    params_lo.maker_limit_timeout_ms = 1_000;
    s.update_params(params_lo).expect("update_params clamp lo");
    assert_eq!(s.get_params().maker_limit_timeout_ms, 15_000);
}

// ─────────────────────────────────────────────────────────────────────────
// G7-09c Phase 1: BBO-aware PostOnly maker price tests for ma_crossover.
// G7-09c Phase 1：ma_crossover BBO-aware PostOnly 限價測試。
// ─────────────────────────────────────────────────────────────────────────

/// Helper: ctx with explicit BBO + tick_size for G7-09c maker_price tests.
/// 輔助：帶顯式 BBO + tick_size 的 ctx（G7-09c maker_price 測試用）。
fn ctx_with_bbo_g709c(
    sma: f64,
    kama: f64,
    adx: f64,
    ts: u64,
    last: f64,
    bid: f64,
    ask: f64,
    tick: f64,
) -> TickContext<'static> {
    let ind = Box::leak(Box::new(IndicatorSnapshot {
        sma_20: Some(sma),
        kama: Some(KamaResult {
            kama,
            efficiency_ratio: 0.5,
        }),
        adx: Some(AdxResult {
            adx,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        ..Default::default()
    }));
    TickContext {
        symbol: "BTC",
        price: last,
        timestamp_ms: ts,
        indicators: Some(ind),
        indicators_5m: None,
        signals: &[],
        h0_allowed: true,
        funding_rate: None,
        index_price: None,
        open_interest: None,
        best_bid: Some(bid),
        best_ask: Some(ask),
        tick_size: Some(tick),
        alpha_surface_ref: &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        position_state: None,
            is_pinned: true,
    }
}

/// G7-09c: ma_crossover buy uses best_bid - buffer×tick when BBO present.
/// G7-09c：ma_crossover 買單在 BBO 存在時使用 best_bid - buffer×tick。
#[test]
fn test_g7_09c_ma_buy_uses_best_bid_passive() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    s.use_maker_entry = true;
    s.maker_price_buffer_ticks = 1;
    s.maker_price_offset_bps = 1.0;
    // sma=100 < kama=101 → BUY (long entry).
    // sma=100 < kama=101 → 多頭入場。
    let i = s.on_tick(&ctx_with_bbo_g709c(
        100.0, 101.0, 25.0, 0, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long);
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            let lp = intent.limit_price.expect("limit_price set");
            // Expected: 49_999.5 - 1*0.1 = 49_999.4 (strictly below ask 50_000.5).
            // 預期：49_999.5 - 0.1 = 49_999.4（嚴格低於 ask）。
            assert!(
                (lp - 49_999.4).abs() < 1e-6,
                "G7-09c BUY limit got {lp}, expected 49_999.4 (best_bid - buffer×tick)"
            );
        }
        other => panic!("expected Open, got {other:?}"),
    }
}

/// G7-09c: ma_crossover sell uses best_ask + buffer×tick when BBO present.
/// G7-09c：ma_crossover 賣單在 BBO 存在時使用 best_ask + buffer×tick。
#[test]
fn test_g7_09c_ma_sell_uses_best_ask_passive() {
    let mut s = MaCrossover::new();
    s.min_persistence_ms = 0;
    s.use_maker_entry = true;
    s.maker_price_buffer_ticks = 1;
    s.maker_price_offset_bps = 1.0;
    // sma=101 > kama=100 → SELL (short entry).
    // sma=101 > kama=100 → 空頭入場。
    let i = s.on_tick(&ctx_with_bbo_g709c(
        101.0, 100.0, 25.0, 0, 50_000.0, 49_999.5, 50_000.5, 0.1,
    ), &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);
    assert_eq!(i.len(), 1);
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(!intent.is_long);
            assert_eq!(intent.order_type, "limit");
            let lp = intent.limit_price.expect("limit_price set");
            // Expected: 50_000.5 + 1*0.1 = 50_000.6 (strictly above bid 49_999.5).
            // 預期：50_000.5 + 0.1 = 50_000.6（嚴格高於 bid）。
            assert!(
                (lp - 50_000.6).abs() < 1e-6,
                "G7-09c SELL limit got {lp}, expected 50_000.6 (best_ask + buffer×tick)"
            );
        }
        other => panic!("expected Open, got {other:?}"),
    }
}
