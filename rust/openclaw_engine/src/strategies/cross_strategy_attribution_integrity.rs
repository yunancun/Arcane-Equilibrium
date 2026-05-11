//! Cross-strategy attribution integrity — holistic integration test (E4, 2026-05-11).
//! 跨策略歸屬完整性 — holistic integration 測試（E4，2026-05-11）。
//!
//! 背景：P0 Option A-Lite post-merge regression。22:08 May 10 watchdog Auto
//!   restart 引爆 cross-strategy mass scalp（grid 開倉 → paper_state.apply_fill
//!   寫入；bb_reversion self.positions empty → W7-2 Option A sync paper_state
//!   進本地 → 下個 tick 走 exit 分支撞 [0.2, 0.8] 寬 exit zone → close grid 倉
//!   並寫 close fill `strategy=grid_trading + exit_reason=bb_mean_revert`）。
//!
//! Post Option A-Lite (5 策略 SSoT 重構)：
//!   - ma_crossover / bb_reversion / bb_breakout / funding_arb 移除本地
//!     `self.positions`，由 `ctx.position_state` 作 SSoT
//!   - 5 策略 exit / entry 路徑加 `ctx.position_state.owner_strategy == self.name()`
//!     filter，cross-strategy 倉位 skip 全路徑（不平、不開、不寫狀態）
//!   - grid_trading 保留 net_inventory 但 entry path 加 `cross_strategy_holds` gate
//!
//! 已存 acceptance test 分布：
//!   - `ma_crossover::tests::test_cross_strategy_position_skips_entry` 等 3 個
//!   - `bb_reversion::tests::test_bbr_p0_skip_entry_when_cross_strategy_position_holds` 等 4 個
//!   - `bb_breakout::tests::test_skips_entry_when_other_strategy_holds_position` 等
//!   - `grid_trading::tests::test_grid_skip_entry_when_cross_strategy_holds_paper_state` 等 3 個
//!   - `funding_arb::tests::*` dormant 結構驗
//!
//! 本檔補上 5 策略 sibling acceptance 之外的 **holistic / multi-strategy interaction**
//! 視角：同一 tick 內 2 個策略對同 symbol 同時呼叫 on_tick，cross-strategy 倉位
//! 永遠不會在錯誤的策略 exit 分支被誤平。對應 PA report §5.3 設計初衷的「cross-strategy
//! integration」覆蓋層（E1 各自 sibling 已驗 self-view，本檔驗 holistic 跨策略視角）。

use crate::paper_state::PaperPosition;
use crate::strategies::bb_breakout::BbBreakout;
use crate::strategies::bb_reversion::BbReversion;
use crate::strategies::grid_trading::GridTrading;
use crate::strategies::ma_crossover::MaCrossover;
use crate::strategies::{Strategy, StrategyAction};
use crate::tick_pipeline::TickContext;
use openclaw_core::indicators::{
    AdxResult, BollingerResult, HurstResult, IndicatorSnapshot, KamaResult,
};

/// 構造 cross-strategy holistic 場景所需的指標快照。
/// 同時填上 ma / bb / hurst 三類指標，使 ma_crossover / bb_reversion / bb_breakout
/// 任何一個都會「正常」想觸發 entry 或 exit signal — 從而暴露 cross-strategy
/// gate 是否真實生效。
fn make_indicators_combined() -> &'static IndicatorSnapshot {
    Box::leak(Box::new(IndicatorSnapshot {
        // ── ma_crossover 路徑 ──
        sma_20: Some(100.0),
        kama: Some(KamaResult {
            kama: 101.0,
            efficiency_ratio: 0.5,
        }),
        adx: Some(AdxResult {
            adx: 25.0,
            plus_di: 25.0,
            minus_di: 15.0,
        }),
        // sma_50 > price=50000 → long signal MA pair confirmation ✓
        sma_50: Some(51_000.0),
        // ── bb_reversion 路徑（pct_b=0.5 → exit zone 內，oversold 不觸發） ──
        bollinger: Some(BollingerResult {
            upper: 51_000.0,
            middle: 50_000.0,
            lower: 49_000.0,
            bandwidth: 0.04,
            percent_b: 0.5, // 落 [0.2, 0.8] exit zone 中央
        }),
        rsi_14: Some(50.0),
        // ── bb_breakout 路徑（不觸發 entry，但有 exit fall back data） ──
        hurst: Some(HurstResult {
            hurst: 0.5,
            regime: "random".into(),
        }),
        volume_ratio: Some(1.0),
        ..Default::default()
    }))
}

/// 構造 holistic 場景 TickContext。`position_state` 可在 caller 端覆寫。
fn make_holistic_ctx(symbol: &'static str, ts: u64) -> TickContext<'static> {
    TickContext {
        symbol,
        price: 50_000.0,
        timestamp_ms: ts,
        indicators: Some(make_indicators_combined()),
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

/// 構造 PaperPosition mock — `owner` 用以 simulate cross-strategy vs self-owned。
fn make_paper_position(symbol: &str, is_long: bool, owner: &str) -> PaperPosition {
    PaperPosition {
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

// ═══════════════════════════════════════════════════════════════════════════════
// Test 1：cross-strategy open then no alien close
// ═══════════════════════════════════════════════════════════════════════════════
//
// Scenario：grid_trading 開 LONG BTC 倉（paper_state.apply_fill 寫入
//   `owner_strategy="grid_trading"`）。下個 tick 同 symbol：
//   - ma_crossover 看 ctx.position_state（owner=grid_trading）+ 自身 signal
//   - bb_reversion 看同 ctx.position_state + bb.percent_b=0.5 落 exit zone
//   - bb_breakout 看同 ctx.position_state
//   無一可 emit StrategyAction::Close（owner_strategy gate 全防護）。
// Acceptance：3 個 sibling 策略各自 on_tick 都不發 Close。
// 對應 22:08 May 10 RCA root：「grid open + bb 寬 exit zone + cross-strategy
// mass scalp」現徹底封堵。

#[test]
fn cross_strategy_open_grid_then_no_alien_close() {
    let mut ma = MaCrossover::new();
    ma.min_persistence_ms = 0;
    let mut bbr = BbReversion::new();
    bbr.min_persistence_ms = 0;
    let mut bbb = BbBreakout::new();

    let grid_position = make_paper_position("BTC", true, "grid_trading");
    let mut ctx = make_holistic_ctx("BTC", 1_000);
    ctx.position_state = Some(&grid_position);

    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;

    // ── ma_crossover 視角 ──
    let ma_actions = ma.on_tick(&ctx, surface);
    let ma_closes = ma_actions
        .iter()
        .filter(|a| matches!(a, StrategyAction::Close { .. }))
        .count();
    assert_eq!(
        ma_closes, 0,
        "ma_crossover 必不平 cross-strategy（owner=grid_trading）倉位，發了 {} Close",
        ma_closes
    );

    // ── bb_reversion 視角 ──
    let bbr_actions = bbr.on_tick(&ctx, surface);
    let bbr_closes = bbr_actions
        .iter()
        .filter(|a| matches!(a, StrategyAction::Close { .. }))
        .count();
    assert_eq!(
        bbr_closes, 0,
        "bb_reversion 必不平 cross-strategy 倉位即使 bb.percent_b 在 exit zone，發了 {} Close",
        bbr_closes
    );

    // ── bb_breakout 視角 ──
    let bbb_actions = bbb.on_tick(&ctx, surface);
    let bbb_closes = bbb_actions
        .iter()
        .filter(|a| matches!(a, StrategyAction::Close { .. }))
        .count();
    assert_eq!(
        bbb_closes, 0,
        "bb_breakout 必不平 cross-strategy 倉位，發了 {} Close",
        bbb_closes
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 2：ma_crossover 開倉 → bb_breakout 不平
// ═══════════════════════════════════════════════════════════════════════════════
//
// Scenario：ma_crossover 開 LONG BTC（paper_state owner=ma_crossover）。下 tick
//   bb_breakout 看 ctx.position_state owner=ma_crossover ≠ "bb_breakout"，
//   應走「無自家倉位」分支，但無 squeeze/breakout signal 觸發故無 entry；
//   即使「有」exit signal 也必 skip exit（owner gate）。
// Acceptance：bb_breakout.on_tick 不發 StrategyAction::Close。

#[test]
fn ma_crossover_open_then_bb_breakout_does_not_close() {
    let mut bbb = BbBreakout::new();

    let ma_position = make_paper_position("BTC", true, "ma_crossover");
    let mut ctx = make_holistic_ctx("BTC", 2_000);
    ctx.position_state = Some(&ma_position);

    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;
    let actions = bbb.on_tick(&ctx, surface);

    let close_count = actions
        .iter()
        .filter(|a| matches!(a, StrategyAction::Close { .. }))
        .count();
    assert_eq!(
        close_count, 0,
        "bb_breakout 必不平 ma_crossover 持倉，發了 {} Close",
        close_count
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 3：cross-strategy paper_state holds → grid_trading skip entry
// ═══════════════════════════════════════════════════════════════════════════════
//
// Scenario：paper_state 已有 ma_crossover LONG BTC（cross-strategy 從 grid 視角）。
//   grid first tick 初始化網格，第二 tick price down cross would_open=true。
//   cross_strategy_holds gate 應該擋住 new entry。
// Acceptance：grid.on_tick 0 Open intents（cross_strategy_holds=true 蘊含
//   `owner_strategy != grid_trading && != bybit_sync && != orphan_adopted`）。

#[test]
fn cross_strategy_ma_holds_then_grid_skip_entry() {
    let mut grid = GridTrading::new(49_000.0, 51_000.0);
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;

    // 首 tick：初始化網格 + last_cross_idx（無 position_state）
    let ctx0 = TickContext {
        symbol: "BTC",
        price: 50_500.0,
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
        alpha_surface_ref: surface,
        position_state: None,
            is_pinned: true,
    };
    grid.on_tick(&ctx0, surface);

    // 第二 tick：down cross + paper_state has ma_crossover LONG（cross-strategy）
    let ma_position = make_paper_position("BTC", true, "ma_crossover");
    let ctx2 = TickContext {
        symbol: "BTC",
        price: 49_500.0,
        timestamp_ms: 100_000,
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
        alpha_surface_ref: surface,
        position_state: Some(&ma_position),
        is_pinned: true,
    };
    let intents = grid.on_tick(&ctx2, surface);
    let open_count = intents
        .iter()
        .filter(|a| matches!(a, StrategyAction::Open(_)))
        .count();
    assert_eq!(
        open_count, 0,
        "ma_crossover holds paper_state 時 grid 必 skip new entry，發了 {} Open",
        open_count
    );
    // net_inventory 必未被修改（gate 在 inventory write 前 return）
    assert_eq!(
        grid.net_inventory.get("BTC").copied().unwrap_or(0.0),
        0.0,
        "cross_strategy_holds skip 後 net_inventory 必保持 0"
    );
}

// ═══════════════════════════════════════════════════════════════════════════════
// Test 4：bybit_sync owner → grid 視為合法 / ma_crossover 仍視為 cross-strategy
// ═══════════════════════════════════════════════════════════════════════════════
//
// Scenario：paper_state owner = bybit_sync（boot 後 exchange re-sync 寫入，
//   不對應任何策略 name）。grid 的 cross_strategy_holds gate 包含 bybit_sync 為
//   合法 owner（PA §7 #5 acceptance）；ma_crossover 不在合法清單故 skip。
// Acceptance：
//   - ma_crossover.on_tick 不發 entry intent（owner ≠ "ma_crossover" → skip）
//   - grid.on_tick 不被 cross_strategy_holds gate 阻擋（owner == "bybit_sync"）

#[test]
fn bybit_sync_owner_grid_legal_ma_treats_as_cross() {
    let surface = &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE;

    // ── ma_crossover 視角：bybit_sync 不是 self → skip entry ──
    let mut ma = MaCrossover::new();
    ma.min_persistence_ms = 0;
    let bs_position = make_paper_position("BTC", true, "bybit_sync");
    let mut ctx_ma = make_holistic_ctx("BTC", 3_000);
    ctx_ma.position_state = Some(&bs_position);
    let ma_actions = ma.on_tick(&ctx_ma, surface);
    let ma_opens = ma_actions
        .iter()
        .filter(|a| matches!(a, StrategyAction::Open(_)))
        .count();
    assert_eq!(
        ma_opens, 0,
        "ma_crossover 視 bybit_sync 為 cross-strategy 必 skip entry，發了 {} Open",
        ma_opens
    );

    // ── grid_trading 視角：bybit_sync 合法 → gate 不擋 ──
    let mut grid = GridTrading::new(49_000.0, 51_000.0);
    // 首 tick 初始化
    let ctx0 = TickContext {
        symbol: "BTC",
        price: 50_500.0,
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
        alpha_surface_ref: surface,
        position_state: None,
            is_pinned: true,
    };
    grid.on_tick(&ctx0, surface);

    let bs_position2 = make_paper_position("BTC", true, "bybit_sync");
    let ctx_grid = TickContext {
        symbol: "BTC",
        price: 49_500.0,
        timestamp_ms: 100_000,
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
        alpha_surface_ref: surface,
        position_state: Some(&bs_position2),
        is_pinned: true,
    };
    let grid_intents = grid.on_tick(&ctx_grid, surface);
    // grid gate 不擋（bybit_sync 合法），允許正常進入 buy/sell dispatch；
    // 至少 1 Open intent（down cross → buy）。
    let grid_opens = grid_intents
        .iter()
        .filter(|a| matches!(a, StrategyAction::Open(_)))
        .count();
    assert!(
        grid_opens >= 1,
        "grid 視 bybit_sync 為合法 owner 應允許 new entry，但發了 {} Open",
        grid_opens
    );
}
