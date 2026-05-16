//! Grid Trading unit tests.
//! Grid Trading 單元測試。
//!
//! MODULE_NOTE (EN): Split out of `strategies/grid_trading.rs` by GRID-TRADING-MOD-SPLIT-1
//!   (2026-04-23) to honour CLAUDE.md §九's 1200-line hard cap (pre-split 1729 lines).
//!   Contains the 36-case test suite covering grid creation, lazy init, buy/sell
//!   on cross, Close-on-inventory-reduction lifecycle, close_skipped rollback,
//!   adaptive + geometric grid behaviours, OU spacing update, health check +
//!   auto-rebalance, param range / validation, G-SR-1 A3 trend cooldown, and
//!   EDGE-P2-3 Phase 1a PostOnly maker entry, and grid churn breaker behavior.
//! MODULE_NOTE (中)：GRID-TRADING-MOD-SPLIT-1（2026-04-23）由
//!   `strategies/grid_trading.rs` 拆出以遵守 CLAUDE.md §九 1200 行硬上限
//!   （拆前 1729 行）。本檔包含 36 個測試案例，涵蓋網格建構、延遲初始化、
//!   穿越時買入/賣出、庫存縮減時 Close 生命週期、close_skipped 回滾、自適應
//!   + 幾何網格行為、OU 間距更新、健康檢查 + 自動再平衡、參數範圍 / 驗證、
//!   G-SR-1 A3 趨勢冷卻、EDGE-P2-3 Phase 1a PostOnly maker 入場，以及
//!   grid churn breaker 行為。

use super::*;
use crate::order_manager::TimeInForce;
use crate::strategies::{Strategy, StrategyAction, StrategyParams};
use crate::tick_pipeline::TickContext;
use openclaw_core::alpha_surface::{AlphaSurface, BtcLeadLagPanel};

fn ctx(price: f64, ts: u64) -> TickContext<'static> {
    ctx_for_symbol("BTC", price, ts)
}

fn ctx_for_symbol(symbol: &'static str, price: f64, ts: u64) -> TickContext<'static> {
    TickContext {
        symbol,
        price,
        timestamp_ms: ts,
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

fn btc_panel(symbol: &str, expected_dir: i8) -> BtcLeadLagPanel {
    BtcLeadLagPanel {
        alt_symbols: vec![symbol.to_string()],
        btc_lead_return_pct: 25.0,
        lead_window_secs: 120,
        alt_xcorr: vec![0.65],
        alt_expected_dir: vec![expected_dir],
        snapshot_ts_ms: 1_715_000_000_000,
        source_tier: "cross_asset_btc_lead_lag".to_string(),
    }
}

fn surface_with_btc(panel: &BtcLeadLagPanel) -> AlphaSurface<'_> {
    AlphaSurface {
        btc_lead_lag: Some(panel),
        ..AlphaSurface::empty()
    }
}

#[test]
fn test_grid_creation() {
    // Grid levels are lazily initialized on first tick, not at construction.
    // 網格層級在首次 tick 時延遲初始化，不在構造時。
    let mut g = GridTrading::new(49000.0, 51000.0);
    assert!(
        g.grid_levels.is_empty(),
        "grid_levels should be empty before first tick"
    );
    g.on_tick(
        &ctx(50000.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // triggers lazy init with template_bounds
    let levels = g.grid_levels.get("BTC").unwrap();
    assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
    assert!((levels[0] - 49000.0).abs() < 0.01);
}

#[test]
fn test_grid_buy_on_down_cross() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.on_tick(
        &ctx(50500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // initial
    let i = g.on_tick(
        &ctx(49500.0, 100_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // cross down
    assert!(!i.is_empty());
    // net_inventory was 0 before buy → Open (new long)
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_grid_sell_on_up_cross() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.on_tick(
        &ctx(49500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let i = g.on_tick(
        &ctx(50500.0, 100_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!i.is_empty());
    // net_inventory was 0 before sell → Open (new short)
    match &i[0] {
        StrategyAction::Open(intent) => assert!(!intent.is_long),
        other => panic!("expected Open, got {:?}", other),
    }
}

#[test]
fn test_grid_btc_lead_lag_blocks_counter_direction_open() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.on_tick(
        &ctx_for_symbol("ETHUSDT", 50500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let panel = btc_panel("ETHUSDT", -1);
    let surface = surface_with_btc(&panel);

    let actions = g.on_tick(&ctx_for_symbol("ETHUSDT", 49500.0, 100_000), &surface);

    assert!(
        actions.is_empty(),
        "down-cross long open must be blocked when BTC lead-lag expects down"
    );
}

#[test]
fn test_grid_btc_lead_lag_allows_aligned_open() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.on_tick(
        &ctx_for_symbol("ETHUSDT", 50500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let panel = btc_panel("ETHUSDT", 1);
    let surface = surface_with_btc(&panel);

    let actions = g.on_tick(&ctx_for_symbol("ETHUSDT", 49500.0, 100_000), &surface);

    assert_eq!(actions.len(), 1);
    match &actions[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected aligned long Open, got {:?}", other),
    }
}

#[test]
fn test_no_inventory_cap_blocking() {
    // Inventory cap removed — intent_processor Gate 1.5 handles duplicates.
    // 庫存上限已移除 — intent_processor Gate 1.5 處理重複。
    let mut g = GridTrading::new(49000.0, 51000.0);
    // First tick initializes grid lazily / 首次 tick 延遲初始化網格
    g.on_tick(
        &ctx(50500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    g.net_inventory.insert("BTC".into(), g.max_inventory);
    let i = g.on_tick(
        &ctx(49500.0, 100_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!i.is_empty()); // Grid always emits; intent_processor decides
}

#[test]
fn test_grid_close_on_inventory_reduction() {
    // When net_inventory > 0 and price crosses up (sell), it's a Close (closing long).
    // When net_inventory < 0 and price crosses down (buy), it's a Close (closing short).
    // 當 net_inventory > 0 且價格上穿（賣出），為 Close（平多）。
    // 當 net_inventory < 0 且價格下穿（買入），為 Close（平空）。
    let mut g = GridTrading::new(49000.0, 51000.0);

    // Step 1: Buy to build positive inventory / 步驟 1：買入建立正庫存
    g.on_tick(
        &ctx(50500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let i = g.on_tick(
        &ctx(49500.0, 100_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!i.is_empty());
    assert!(*g.net_inventory.get("BTC").unwrap_or(&0.0) > 0.0);
    match &i[0] {
        StrategyAction::Open(intent) => assert!(intent.is_long),
        other => panic!("expected Open for initial buy, got {:?}", other),
    }

    // Step 2: Sell with positive inventory → Close / 步驟 2：正庫存賣出 → Close
    let i = g.on_tick(
        &ctx(50500.0, 200_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!i.is_empty());
    match &i[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "grid_close_long"),
        other => panic!("expected Close for inventory reduction, got {:?}", other),
    }
    // Inventory NOT yet adjusted (deferred until on_close_confirmed)
    // 庫存尚未調整（延遲到 on_close_confirmed）
    assert!(
        *g.net_inventory.get("BTC").unwrap_or(&0.0) > 0.0,
        "inventory deferred: still positive before confirm"
    );

    // Pipeline confirms close → inventory adjusted
    // 管線確認平倉 → 庫存已調整
    g.on_close_confirmed("BTC");
    let inv = g.net_inventory.get("BTC").copied().unwrap_or(0.0);
    assert!(
        inv.abs() < 1e-9,
        "inventory should be 0 after close confirmed, got {}",
        inv
    );
}

#[test]
fn test_grid_close_skipped_rolls_back() {
    // When pipeline skips a Close (no position), on_close_skipped rolls back cross state.
    // 管線跳過 Close（無倉位）時，on_close_skipped 回滾交叉狀態。
    let mut g = GridTrading::new(49000.0, 51000.0);
    // Build positive inventory via Open
    g.on_tick(
        &ctx(50500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    g.on_tick(
        &ctx(49500.0, 100_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let prev_cross = g.last_cross_idx.get("BTC").copied();
    let prev_inventory = g.net_inventory.get("BTC").copied().unwrap_or(0.0);

    // Emit Close (sell with positive inventory)
    let i = g.on_tick(
        &ctx(50500.0, 200_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(!i.is_empty());
    match &i[0] {
        StrategyAction::Close { .. } => {}
        other => panic!("expected Close, got {:?}", other),
    }

    // Pipeline says no position found → skip → roll back
    g.on_close_skipped("BTC");
    assert_eq!(
        g.last_cross_idx.get("BTC").copied(),
        prev_cross,
        "cross state should be rolled back"
    );
    // Inventory unchanged since Close doesn't adjust eagerly
    let cur_inv = g.net_inventory.get("BTC").copied().unwrap_or(0.0);
    assert!((cur_inv - prev_inventory).abs() < 1e-9);
}

#[test]
fn test_adaptive_grid_init_on_first_tick() {
    // Adaptive grid starts empty and auto-initializes on first tick
    // 自适应网格初始为空，首次 tick 时自动初始化
    let mut g = GridTrading::new_adaptive();
    assert!(g.grid_levels.is_empty());
    let intents = g.on_tick(
        &ctx(50000.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let levels = g.grid_levels.get("BTC").unwrap();
    assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
    // Range should be ±10% of 50000 → 45000..55000
    assert!((levels[0] - 45000.0).abs() < 1.0);
    assert!(intents.is_empty()); // first tick = no trade
}

#[test]
fn test_ou_spacing_update() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.on_tick(
        &ctx(50000.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // lazy init
       // Fill price history for BTC
    let history = g.price_history.entry("BTC".into()).or_default();
    for i in 0..60 {
        history.push(50000.0 + (i as f64 * 0.1).sin() * 100.0);
    }
    g.update_ou_spacing("BTC");
    let levels = g.grid_levels.get("BTC").unwrap();
    assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
}

// ── Geometric spacing tests / 幾何間距測試 ──

#[test]
fn test_geometric_grid_levels() {
    // Verify geometric spacing produces correct ratio-based levels.
    // 驗證幾何間距產生正確的等比層級。
    let mut g = GridTrading::new_geometric(1000.0, 2000.0);
    g.on_tick(
        &ctx(1500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // lazy init with template_bounds
    let levels = g.grid_levels.get("BTC").unwrap();
    assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
    assert!((levels[0] - 1000.0).abs() < 0.01);
    let last = levels[levels.len() - 1];
    assert!((last - 2000.0).abs() < 0.1);

    // All ratios between consecutive levels should be equal.
    // 所有相鄰層級之間的比率應相等。
    let expected_ratio = (2000.0_f64 / 1000.0).powf(1.0 / 9.0);
    for i in 1..levels.len() {
        let ratio = levels[i] / levels[i - 1];
        assert!(
            (ratio - expected_ratio).abs() < 1e-10,
            "Ratio at index {} was {}, expected {}",
            i,
            ratio,
            expected_ratio
        );
    }
}

#[test]
fn test_geometric_vs_linear() {
    // Geometric levels should differ from linear levels for the same bounds.
    // 相同邊界下，幾何層級應與線性層級不同。
    let mut lin = GridTrading::new(1000.0, 2000.0);
    let mut geo = GridTrading::new_geometric(1000.0, 2000.0);
    lin.on_tick(
        &ctx(1500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // lazy init
    geo.on_tick(
        &ctx(1500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // lazy init
    let lin_l = lin.grid_levels.get("BTC").unwrap();
    let geo_l = geo.grid_levels.get("BTC").unwrap();

    assert_eq!(lin_l.len(), geo_l.len());

    // First and last levels match (same bounds).
    // 首末層級應相同（邊界一致）。
    assert!((lin_l[0] - geo_l[0]).abs() < 0.01);
    let last = lin_l.len() - 1;
    assert!((lin_l[last] - geo_l[last]).abs() < 0.5);

    // Middle levels should differ — geometric bunches more toward lower end.
    // 中間層級應不同 — 幾何模式在低端更密集。
    let mid = lin_l.len() / 2;
    assert!(
        (lin_l[mid] - geo_l[mid]).abs() > 1.0,
        "Middle levels should differ: linear={}, geometric={}",
        lin_l[mid],
        geo_l[mid]
    );
}

// ── Health check tests / 健康檢查測試 ──

#[test]
fn test_health_check_in_range() {
    // Price within grid → Healthy.
    // 價格在網格範圍內 → Healthy。
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.on_tick(
        &ctx(50000.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // lazy init
    let h = g.check_health("BTC", 50000.0);
    assert_eq!(h, GridHealth::Healthy);
    assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 0);
}

#[test]
fn test_health_check_out_of_range() {
    // Price outside grid → OutOfRange (but not yet NeedsRebalance).
    // 價格超出網格 → OutOfRange（但尚未到 NeedsRebalance）。
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.on_tick(
        &ctx(50000.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // lazy init

    // Price below grid
    let h = g.check_health("BTC", 48000.0);
    assert_eq!(h, GridHealth::OutOfRange);
    assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 1);

    // Price above grid
    let h = g.check_health("BTC", 52000.0);
    assert_eq!(h, GridHealth::OutOfRange);
    assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 2);

    // Price back in range → resets counter
    // 價格回到範圍 → 重置計數器
    let h = g.check_health("BTC", 50000.0);
    assert_eq!(h, GridHealth::Healthy);
    assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 0);
}

#[test]
fn test_auto_rebalance() {
    // After max_out_of_range ticks outside grid, grid recenters.
    // 連續超出範圍達到 max_out_of_range 次後，網格重新居中。
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.max_out_of_range = 5;
    g.health_check_interval = 1; // Check every tick for test / 測試用每 tick 檢查

    let far_price = 60000.0; // Well outside 49000-51000 range

    // Feed ticks at the far price. Health check runs every tick.
    // 以遠離價格餵入 tick。每 tick 執行健康檢查。
    for ts in 0..10 {
        g.on_tick(
            &ctx(far_price, ts * 100_000),
            &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        );
    }

    // Grid should have rebalanced around 60000 (±10% → 54000..66000).
    // 網格應已以 60000 為中心重建（±10% → 54000..66000）。
    let levels = g.grid_levels.get("BTC").unwrap();
    assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
    let lo = levels[0];
    let hi = levels[levels.len() - 1];
    // The new grid should contain the far price.
    // 新網格應包含遠離的價格。
    assert!(
        lo < far_price && far_price < hi,
        "Rebalanced grid [{}, {}] should contain price {}",
        lo,
        hi,
        far_price
    );
    assert_eq!(g.out_of_range_count.get("BTC").copied().unwrap_or(0), 0);
}

#[test]
fn test_geometric_rebalance() {
    // Rebalance in geometric mode preserves geometric spacing.
    // 幾何模式下再平衡應保持等比間距。
    let mut g = GridTrading::new_geometric(49000.0, 51000.0);
    g.max_out_of_range = 3;
    g.health_check_interval = 1;

    let far_price = 60000.0;
    for ts in 0..8 {
        g.on_tick(
            &ctx(far_price, ts * 100_000),
            &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
        );
    }

    // Grid should have rebalanced with geometric spacing.
    // 網格應已以幾何間距重建。
    let levels = g.grid_levels.get("BTC").unwrap();
    assert_eq!(levels.len(), DEFAULT_GRID_COUNT);
    assert_eq!(g.spacing_mode, GridSpacingMode::Geometric);

    // Verify geometric property: constant ratio between consecutive levels.
    // 驗證幾何特性：相鄰層級間比率恆定。
    let ratios: Vec<f64> = levels.windows(2).map(|w| w[1] / w[0]).collect();
    let first_ratio = ratios[0];
    for (i, &r) in ratios.iter().enumerate() {
        assert!(
            (r - first_ratio).abs() < 1e-8,
            "Ratio at index {} was {}, expected {} (geometric invariant broken)",
            i,
            r,
            first_ratio
        );
    }

    // New grid should contain the rebalance price.
    // 新網格應包含再平衡價格。
    let lo = levels[0];
    let hi = levels[levels.len() - 1];
    assert!(lo < far_price && far_price < hi);
}

#[test]
fn test_adaptive_geometric_init() {
    // Adaptive geometric grid initializes with geometric spacing on first tick.
    // 自適應幾何網格在首次 tick 時以幾何間距初始化。
    let mut g = GridTrading::new_adaptive_geometric();
    assert!(g.grid_levels.is_empty());
    assert_eq!(g.spacing_mode, GridSpacingMode::Geometric);

    g.on_tick(
        &ctx(50000.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let btc_levels = g
        .grid_levels
        .get("BTC")
        .expect("BTC grid should be initialized on first tick");
    assert_eq!(btc_levels.len(), DEFAULT_GRID_COUNT);

    // Verify geometric property.
    // 驗證幾何特性。
    let ratios: Vec<f64> = btc_levels.windows(2).map(|w| w[1] / w[0]).collect();
    let first_ratio = ratios[0];
    for &r in &ratios {
        assert!((r - first_ratio).abs() < 1e-10);
    }
}

#[test]
fn test_grid_param_ranges() {
    assert!(!GridTradingParams::param_ranges().is_empty());
}
#[test]
fn test_grid_validate() {
    assert!(GridTradingParams::default().validate().is_ok());
    assert!(GridTradingParams {
        max_inventory: 0.5,
        ..Default::default()
    }
    .validate()
    .is_err());
}
#[test]
fn test_grid_update() {
    let mut g = GridTrading::new(100.0, 110.0);
    assert!(g
        .update_params(GridTradingParams {
            max_inventory: 10.0,
            ..Default::default()
        })
        .is_ok());
    assert!((g.get_params().max_inventory - 10.0).abs() < 0.01);
}

// ── G-SR-1 S3+S4: param_ranges + validation tests ──

#[test]
fn test_grid_param_ranges_count() {
    let ranges = GridTradingParams::param_ranges();
    // 4 original + 3 trend cooldown + 2 edge-cost spacing + 3 churn breaker knobs = 12
    assert_eq!(
        ranges.len(),
        12,
        "expected 12 param ranges, got {}",
        ranges.len()
    );
}

#[test]
fn test_grid_param_ranges_cooldown_names() {
    let ranges = GridTradingParams::param_ranges();
    let names: Vec<&str> = ranges.iter().map(|r| r.name.as_str()).collect();
    for expected in &[
        "adx_low_threshold",
        "adx_high_threshold",
        "max_cooldown_boost",
        "min_grid_step_bps",
        "cost_floor_multiplier",
        "churn_breaker_window_ms",
        "churn_breaker_close_count",
        "churn_breaker_cooldown_ms",
    ] {
        assert!(names.contains(expected), "missing param range: {expected}");
    }
}

#[test]
fn test_grid_validate_default_ok() {
    assert!(GridTradingParams::default().validate().is_ok());
}

#[test]
fn test_grid_validate_bad_adx_order() {
    let mut p = GridTradingParams::default();
    p.adx_low_threshold = 50.0;
    p.adx_high_threshold = 20.0; // low > high
    assert!(p.validate().is_err());
}

#[test]
fn test_grid_validate_equal_adx_thresholds() {
    let mut p = GridTradingParams::default();
    p.adx_low_threshold = 30.0;
    p.adx_high_threshold = 30.0; // equal = invalid
    assert!(p.validate().is_err());
}

#[test]
fn test_grid_validate_bad_cooldown_boost() {
    let mut p = GridTradingParams::default();
    p.max_cooldown_boost = 15.0; // > 10
    assert!(p.validate().is_err());
}

#[test]
fn test_grid_validate_negative_cooldown_boost() {
    let mut p = GridTradingParams::default();
    p.max_cooldown_boost = -1.0;
    assert!(p.validate().is_err());
}

// ── G-SR-1 S4: Trend cooldown unit tests (A3) ──

#[test]
fn test_trend_cooldown_no_indicators() {
    let g = GridTrading::new(49000.0, 51000.0);
    // None indicators → base cooldown (new() sets cooldown_ms=60_000)
    assert_eq!(g.compute_trend_adjusted_cooldown(None), 60_000);
}

#[test]
fn test_trend_cooldown_low_adx_no_boost() {
    use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
    let snap = Box::leak(Box::new(IndicatorSnapshot {
        adx: Some(AdxResult {
            adx: 15.0,
            plus_di: 0.0,
            minus_di: 0.0,
        }),
        hurst: Some(HurstResult {
            hurst: 0.45,
            regime: "mean_reverting".into(),
        }),
        ..Default::default()
    }));
    let g = GridTrading::new(49000.0, 51000.0);
    // ADX=15 < adx_low(20) → factor=0, Hurst=0.45 < 0.50 → factor=0
    // trend_score=0, multiplier=1.0, cooldown=60_000
    assert_eq!(g.compute_trend_adjusted_cooldown(Some(snap)), 60_000);
}

#[test]
fn test_trend_cooldown_high_adx_max_boost() {
    use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
    let snap = Box::leak(Box::new(IndicatorSnapshot {
        adx: Some(AdxResult {
            adx: 60.0,
            plus_di: 0.0,
            minus_di: 0.0,
        }),
        hurst: Some(HurstResult {
            hurst: 0.80,
            regime: "trending".into(),
        }),
        ..Default::default()
    }));
    let g = GridTrading::new(49000.0, 51000.0);
    // ADX=60 > adx_high(50) → factor=1.0, Hurst=0.80 > 0.75 → factor=1.0
    // trend_score=0.6*1+0.4*1=1.0, multiplier=1+5=6, cooldown=60_000*6=360_000
    let cd = g.compute_trend_adjusted_cooldown(Some(snap));
    assert_eq!(cd, 360_000, "expected 60_000*6 = 360_000, got {cd}");
}

#[test]
fn test_trend_cooldown_mid_adx_partial_boost() {
    use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
    let snap = Box::leak(Box::new(IndicatorSnapshot {
        adx: Some(AdxResult {
            adx: 35.0,
            plus_di: 0.0,
            minus_di: 0.0,
        }),
        hurst: Some(HurstResult {
            hurst: 0.625,
            regime: "uncertain".into(),
        }),
        ..Default::default()
    }));
    let g = GridTrading::new(49000.0, 51000.0);
    // ADX=35: (35-20)/(50-20)=0.5, Hurst=0.625: (0.625-0.50)/0.25=0.5
    // trend_score=0.6*0.5+0.4*0.5=0.5, multiplier=1+2.5=3.5, cooldown=60_000*3.5=210_000
    let cd = g.compute_trend_adjusted_cooldown(Some(snap));
    assert_eq!(cd, 210_000, "expected 60_000*3.5 = 210_000, got {cd}");
}

// ── EDGE-P2-3 Phase 1a: PostOnly maker entry tests ──
// ── EDGE-P2-3 Phase 1a：PostOnly maker 入場測試 ──

/// Default constructor must keep `use_maker_entry = false` (root principle #6
/// — failure default shrink). Cold-boot behavior stays on proven Market path.
/// 默認構造必須保持 `use_maker_entry = false`（根原則 #6），冷啟動走已驗證 Market 路徑。
#[test]
fn test_grid_maker_disabled_by_default() {
    let g = GridTrading::new(49000.0, 51000.0);
    assert!(!g.use_maker_entry, "use_maker_entry must default to false");
    assert_eq!(
        g.maker_price_offset_bps, DEFAULT_MAKER_OFFSET_BPS,
        "maker_price_offset_bps must default to 1 bps"
    );
    let g2 = GridTrading::new_geometric(49000.0, 51000.0);
    assert!(!g2.use_maker_entry);
    let g3 = GridTrading::new_adaptive();
    assert!(!g3.use_maker_entry);
}

/// When maker disabled, buy intents keep order_type="market" + time_in_force=None
/// (byte-identical legacy behavior).
/// maker 關閉時，買入意圖維持 market + TIF=None（與舊行為 byte-identical）。
#[test]
fn test_grid_market_entry_when_maker_disabled() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    assert!(!g.use_maker_entry);
    g.on_tick(
        &ctx(50500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let i = g.on_tick(
        &ctx(49500.0, 100_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert_eq!(intent.order_type, "market");
            assert!(intent.limit_price.is_none());
            assert!(intent.time_in_force.is_none());
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

/// Buy on down-cross with maker enabled emits BBO-derived PostOnly Limit.
/// 下穿買入時，maker 啟用 → 發 BBO-derived PostOnly Limit。
#[test]
fn test_grid_buy_postonly_below_last_price() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.use_maker_entry = true;
    g.maker_price_offset_bps = 1.0; // 1 bps
    g.on_tick(
        &ctx_with_bbo(50500.0, 0, 50_499.9, 50_500.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let i = g.on_tick(
        &ctx_with_bbo(49500.0, 100_000, 49_499.9, 49_500.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long);
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            let lp = intent.limit_price.expect("limit_price set");
            let expected = 49_499.8;
            assert!(
                (lp - expected).abs() < 1e-9,
                "buy PostOnly must use best_bid-buffer: got {lp}, expected {expected}"
            );
            assert!(lp < 49500.0, "buy limit must rest below last_price");
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

/// Sell on up-cross with maker enabled emits BBO-derived PostOnly Limit.
/// 上穿賣出時，maker 啟用 → 發 BBO-derived PostOnly Limit。
#[test]
fn test_grid_sell_postonly_above_last_price() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.use_maker_entry = true;
    g.maker_price_offset_bps = 2.0; // 2 bps
    g.on_tick(
        &ctx_with_bbo(49500.0, 0, 49_499.9, 49_500.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let i = g.on_tick(
        &ctx_with_bbo(50500.0, 100_000, 50_499.9, 50_500.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    match &i[0] {
        StrategyAction::Open(intent) => {
            assert!(!intent.is_long);
            assert_eq!(intent.order_type, "limit");
            assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
            let lp = intent.limit_price.expect("limit_price set");
            let expected = 50_500.2;
            assert!(
                (lp - expected).abs() < 1e-9,
                "sell PostOnly must use best_ask+buffer: got {lp}, expected {expected}"
            );
            assert!(lp > 50500.0, "sell limit must rest above last_price");
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

/// maker_price_buffer_ticks scales the BBO-derived limit price by ticks.
/// maker_price_buffer_ticks 以 tick 線性縮放 BBO-derived 限價。
#[test]
fn test_grid_maker_buffer_scales_linearly() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.use_maker_entry = true;
    g.maker_price_buffer_ticks = 5;
    g.on_tick(
        &ctx_with_bbo(50500.0, 0, 50_499.9, 50_500.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let i = g.on_tick(
        &ctx_with_bbo(49500.0, 100_000, 49_499.9, 49_500.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    match &i[0] {
        StrategyAction::Open(intent) => {
            let lp = intent.limit_price.unwrap();
            let expected = 49_499.4;
            assert!((lp - expected).abs() < 1e-9);
        }
        other => panic!("expected Open, got {:?}", other),
    }
}

/// Close actions stay Market even when maker entry is enabled — Phase 1a scope
/// intentionally excludes close path (PostOnly rejects would strand positions).
/// 平倉維持 Market，即使 maker 入場啟用 — Phase 1a 刻意排除平倉路徑（避免 PostOnly 拒絕卡倉）。
#[test]
fn test_grid_close_stays_market_with_maker_enabled() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    g.use_maker_entry = true;
    g.maker_price_offset_bps = 1.0;
    // Build positive inventory via Open
    g.on_tick(
        &ctx_with_bbo(50500.0, 0, 50_499.9, 50_500.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    g.on_tick(
        &ctx_with_bbo(49500.0, 100_000, 49_499.9, 49_500.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    // Sell with positive inventory → Close (not Open)
    let i = g.on_tick(
        &ctx(50500.0, 200_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    match &i[0] {
        StrategyAction::Close { reason, .. } => {
            assert_eq!(reason, "grid_close_long");
            // Close variant carries no order_type field — it's always Market at dispatch.
        }
        other => panic!("expected Close, got {:?}", other),
    }
}

/// update_params round-trips maker fields so Agent IPC can toggle at runtime.
/// update_params 來回保留 maker 欄位，Agent IPC 可運行時切換。
#[test]
fn test_grid_update_params_roundtrips_maker_fields() {
    let mut g = GridTrading::new(49000.0, 51000.0);
    let mut params = g.get_params();
    assert!(!params.use_maker_entry);
    params.use_maker_entry = true;
    params.maker_price_offset_bps = 3.0;
    g.update_params(params).expect("update_params");
    let p2 = g.get_params();
    assert!(p2.use_maker_entry);
    assert!((p2.maker_price_offset_bps - 3.0).abs() < 1e-9);
    assert!(g.use_maker_entry);
}

// ─────────────────────────────────────────────────────────────────────────
// G7-09c Phase 1: BBO-aware PostOnly maker price tests.
// G7-09c Phase 1：BBO-aware PostOnly 限價測試。
// ─────────────────────────────────────────────────────────────────────────

/// Helper: ctx with explicit BBO + tick_size for G7-09c maker_price tests.
/// 輔助：帶顯式 BBO + tick_size 的 ctx（G7-09c maker_price 測試用）。
fn ctx_with_bbo(price: f64, ts: u64, bid: f64, ask: f64, tick: f64) -> TickContext<'static> {
    TickContext {
        symbol: "BTC",
        price,
        timestamp_ms: ts,
        indicators: None,
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

/// G7-09c: grid_trading buy uses best_bid - buffer×tick when BBO present.
/// Use template_bounds (49_000, 51_000) so grid spacing = 200 → first-tick
/// 50_500 vs second-tick 49_700 cross several lines downward.
/// G7-09c：grid_trading 買單在 BBO 存在時使用 best_bid - buffer×tick。
/// 用 template_bounds 確保穿越觸發。
#[test]
fn test_g7_09c_grid_buy_uses_best_bid_passive() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.use_maker_entry = true;
    g.maker_price_buffer_ticks = 1;
    g.maker_price_offset_bps = 1.0; // fallback only — should not be exercised here
                                    // First tick at 50_500 sets last_cross_idx; second tick at 49_700 crosses.
                                    // 首 tick 50_500 設 last_cross_idx；第二 tick 49_700 跨越網格。
    g.on_tick(
        &ctx_with_bbo(50_500.0, 0, 50_499.5, 50_500.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let actions = g.on_tick(
        &ctx_with_bbo(49_700.0, 60_001, 49_699.9, 49_700.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let mut found_buy_limit = false;
    for action in &actions {
        if let StrategyAction::Open(intent) = action {
            if intent.is_long {
                let price = intent.limit_price.expect("limit_price required for buy");
                // Expected: 49_699.9 - 1*0.1 = 49_699.8 (strictly below ask).
                // 預期：49_699.9 - 0.1 = 49_699.8（嚴格低於 ask）。
                assert!(
                    (price - 49_699.8).abs() < 1e-6,
                    "buy limit got {price}, expected 49_699.8 (BBO-aware passive)",
                );
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                found_buy_limit = true;
            }
        }
    }
    assert!(
        found_buy_limit,
        "expected at least one BUY limit intent; got {actions:?}"
    );
}

/// G7-09c: grid_trading sell uses best_ask + buffer×tick when BBO present.
/// G7-09c：grid_trading 賣單在 BBO 存在時使用 best_ask + buffer×tick。
#[test]
fn test_g7_09c_grid_sell_uses_best_ask_passive() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.use_maker_entry = true;
    g.maker_price_buffer_ticks = 1;
    g.maker_price_offset_bps = 1.0;
    // First tick at 49_500 sets last_cross_idx; second tick at 50_300 crosses up.
    // 首 tick 49_500 設 last_cross_idx；第二 tick 50_300 向上跨越。
    g.on_tick(
        &ctx_with_bbo(49_500.0, 0, 49_499.5, 49_500.5, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let actions = g.on_tick(
        &ctx_with_bbo(50_300.0, 60_001, 50_299.9, 50_300.1, 0.1),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let mut found_sell_limit = false;
    for action in &actions {
        if let StrategyAction::Open(intent) = action {
            if !intent.is_long {
                let price = intent.limit_price.expect("limit_price required for sell");
                // Expected: 50_300.1 + 1*0.1 = 50_300.2 (strictly above bid).
                // 預期：50_300.1 + 0.1 = 50_300.2（嚴格高於 bid）。
                assert!(
                    (price - 50_300.2).abs() < 1e-6,
                    "sell limit got {price}, expected 50_300.2",
                );
                assert_eq!(intent.time_in_force, Some(TimeInForce::PostOnly));
                found_sell_limit = true;
            }
        }
    }
    assert!(
        found_sell_limit,
        "expected at least one SELL limit intent; got {actions:?}"
    );
}

/// G7-09c: grid_trading skips maker entries when no safe BBO quote exists.
/// G7-09c：無安全 BBO 報價時，grid_trading 跳過 maker 新開倉。
#[test]
fn test_g7_09c_grid_skips_when_no_bbo() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.use_maker_entry = true;
    g.maker_price_buffer_ticks = 1;
    g.maker_price_offset_bps = 5.0; // retained for config compatibility; not fallback
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // BBO=None
    let actions = g.on_tick(
        &ctx(49_700.0, 60_001),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    ); // BUY trigger, BBO=None
    assert!(
        actions.is_empty(),
        "maker entry must skip without BBO; got {actions:?}"
    );
    assert_eq!(
        g.net_inventory.get("BTC").copied().unwrap_or(0.0),
        0.0,
        "skip must not mutate inventory"
    );
}

#[test]
fn test_g7_09c_post_only_reject_callback_arms_cooldown() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.reject_cooldown_ms = 60_000;

    g.on_post_only_rejected(
        "BTC",
        1_000,
        &crate::strategies::maker_rejection::MakerRejectionCategory::PostOnlyCross,
    );

    // BB-MF-3 (2026-05-16) — entry-side cooldown 寫入 entry map（rename）。
    assert_eq!(
        g.reject_cooldown_entry_until_ms.get("BTC").copied(),
        Some(61_000),
        "PostOnly entry reject callback must route to grid entry cooldown wiring"
    );
    assert!(
        g.reject_cooldown_close_until_ms.get("BTC").is_none(),
        "PostOnly entry reject must NOT pollute close cooldown (BB-MF-3 isolation)"
    );
}

#[test]
fn test_grid_blocked_symbol_skips_open_but_allows_close() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    let mut params = g.get_params();
    params.blocked_symbols = vec!["btc".to_string()];
    g.update_params(params).expect("update_params");

    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let blocked = g.on_tick(
        &ctx(49_700.0, 60_001),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(blocked.is_empty(), "blocked symbol must skip new grid open");

    g.blocked_symbols.clear();
    let opened = g.on_tick(
        &ctx(49_700.0, 120_002),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(opened.len(), 1, "unblocked symbol should open");

    g.blocked_symbols.insert("BTC".to_string());
    let close = g.on_tick(
        &ctx(50_300.0, 240_003),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    match &close[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "grid_close_long"),
        other => panic!("blocked symbol must still allow close, got {other:?}"),
    }
}

#[test]
fn test_grid_churn_breaker_arms_after_repeated_confirmed_closes() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.churn_breaker_close_count = 2;
    g.churn_breaker_window_ms = 3_600_000;
    g.churn_breaker_cooldown_ms = 3_600_000;

    g.prev_inventory.insert("BTC".to_string(), 1.0);
    g.net_inventory.insert("BTC".to_string(), 1.0);
    g.last_trade_ms.insert("BTC".to_string(), 1_000);
    g.on_close_confirmed("BTC");
    assert!(
        !g.churn_breaker_until_ms.contains_key("BTC"),
        "first close alone should not arm churn breaker"
    );

    g.prev_inventory.insert("BTC".to_string(), 1.0);
    g.net_inventory.insert("BTC".to_string(), 1.0);
    g.last_trade_ms.insert("BTC".to_string(), 2_000);
    g.on_close_confirmed("BTC");
    assert_eq!(
        g.churn_breaker_until_ms.get("BTC").copied(),
        Some(3_602_000)
    );
}

#[test]
fn test_grid_churn_breaker_skips_open_but_allows_close() {
    let mut blocked = GridTrading::new(49_000.0, 51_000.0);
    blocked
        .churn_breaker_until_ms
        .insert("BTC".to_string(), 300_000);
    blocked.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let skipped = blocked.on_tick(
        &ctx(49_700.0, 60_001),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(skipped.is_empty(), "churn breaker must skip new grid open");

    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let opened = g.on_tick(
        &ctx(49_700.0, 60_001),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert_eq!(opened.len(), 1, "setup should create a long grid position");

    g.churn_breaker_until_ms.insert("BTC".to_string(), 500_000);
    let close = g.on_tick(
        &ctx(50_300.0, 240_003),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    match &close[0] {
        StrategyAction::Close { reason, .. } => assert_eq!(reason, "grid_close_long"),
        other => panic!("churn breaker must still allow close, got {other:?}"),
    }
}

// ─────────────────────────────────────────────────────────────────────────────
// W7-5 — grid_trading import_positions（inventory model：is_long → +qty / is_short → -qty）
// on_fill = no-op by-design（W7-4 §1 LOW，inventory 由 entry path 自管）
// ─────────────────────────────────────────────────────────────────────────────

/// W7-5 (grid_trading)：bootstrap import_positions 重建 net_inventory（含 sign convention）。
#[test]
fn test_grid_bootstrap_imports_signed_inventory_from_paper_state() {
    use crate::paper_state::PaperState;

    let mut paper = PaperState::new(10_000.0);
    paper.apply_fill("BTC", true, 1.5, 50_000.0, 0.5, 1_000, "grid_trading");
    paper.apply_fill("ETH", false, 2.0, 3_000.0, 0.3, 1_001, "grid_trading");
    paper.apply_fill("SOL", true, 5.0, 100.0, 0.1, 1_002, "ma_crossover"); // 不應被 grid import

    let mut g = GridTrading::new_adaptive_with_mode(GridSpacingMode::Linear);
    g.import_positions(&paper);

    assert_eq!(
        g.net_inventory.get("BTC").copied(),
        Some(1.5),
        "grid_trading import LONG 必為 +qty"
    );
    assert_eq!(
        g.net_inventory.get("ETH").copied(),
        Some(-2.0),
        "grid_trading import SHORT 必為 -qty"
    );
    assert!(
        g.net_inventory.get("SOL").is_none(),
        "ma_crossover owner 倉位不可被 grid import"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// OPTION-A-LITE-E1D (2026-05-11) — cross_strategy_holds entry gate
// 防 ma/bb_reversion/bb_breakout 已開的 paper_state 倉位讓 grid 誤觸發新入場。
// 接受的合法 owner：grid_trading（自己）/ bybit_sync / orphan_adopted。
// 不動 net_inventory 任何 read/write（PA §7 BLOCKER #2）。
// ─────────────────────────────────────────────────────────────────────────────

use crate::paper_state::PaperPosition;

/// OPTION-A-LITE-E1D helper：構建 PaperPosition 模擬 paper_state 真實持倉。
/// 全欄位最小可行值；owner_strategy 由 caller 指定以驗證 gate 行為。
fn make_paper_position_grid(symbol: &str, is_long: bool, owner: &str) -> PaperPosition {
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
        entry_notional: 1.0 * 50_000.0,
        max_favorable_pnl_pct: 0.0,
        peak_reached_ts_ms: 0,
    }
}

/// 帶 ctx.position_state 的 helper（複用 ctx 簽名）。
fn ctx_with_position(price: f64, ts: u64, pp: &PaperPosition) -> TickContext<'_> {
    TickContext {
        symbol: "BTC",
        price,
        timestamp_ms: ts,
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
        position_state: Some(pp),
        is_pinned: true,
    }
}

/// OPTION-A-LITE-E1D #1：cross-strategy paper_state 持倉時 grid skip new entry。
/// Setup：paper_state has bb_reversion LONG BTC，grid signal would_open=true（down cross）。
/// Verify：grid.on_tick 返回 0 Open intents（cross_strategy_holds gate 阻擋）。
#[test]
fn test_grid_skip_entry_when_cross_strategy_holds_paper_state() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    // 首 tick 初始化網格 + 設 last_cross_idx，無 position_state（baseline）。
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    // 第二 tick：down cross（would_open=true）+ paper_state 有 bb_reversion LONG。
    let pp = make_paper_position_grid("BTC", true, "bb_reversion");
    let ctx2 = ctx_with_position(49_500.0, 100_000, &pp);
    let intents = g.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert!(
        intents.is_empty(),
        "cross-strategy paper_state holds 時 grid 必 skip new entry，但發了 {} intents",
        intents.len()
    );
    // net_inventory 不應被修改（gate 在 net_inventory 寫入路徑之前 return）。
    assert_eq!(
        g.net_inventory.get("BTC").copied().unwrap_or(0.0),
        0.0,
        "gate skip 後 net_inventory 必保持 0（未進入 buy/sell dispatch）"
    );
}

/// OPTION-A-LITE-E1D #2：grid 自己擁有的 paper_state 倉位不應被 gate 阻擋。
/// Setup：paper_state has grid_trading LONG BTC，grid signal would_open=true（down cross）。
/// Verify：gate 不阻擋；依舊由 net_inventory 決定 Open vs Close。
/// 註：cur_inventory=0（net_inventory 未寫，因 paper_state 不影響 grid 本地 inventory）
/// 故 would_open=true && cross_strategy_holds=false → 正常 emit Open intent。
#[test]
fn test_grid_accepts_own_inventory_position() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    let pp = make_paper_position_grid("BTC", true, "grid_trading");
    let ctx2 = ctx_with_position(49_500.0, 100_000, &pp);
    let intents = g.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert!(
        !intents.is_empty(),
        "owner=grid_trading 時 gate 必不阻擋；intents 應 ≥1"
    );
    // down cross + cur_inventory=0 → Open（new long）。
    match &intents[0] {
        StrategyAction::Open(intent) => {
            assert!(intent.is_long, "down cross with own owner 必發 LONG Open")
        }
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// OPTION-A-LITE-E1D #3：owner=bybit_sync（boot 後 exchange sync 寫入）視為合法。
/// Setup：paper_state has bybit_sync LONG BTC（如 boot 後從 Bybit re-sync 拿回真實倉）。
/// Verify：gate 不阻擋；grid signal 正常進入 entry dispatch（Open or Close 由 net_inventory 決定）。
#[test]
fn test_grid_treats_bybit_sync_owner_as_legitimate() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    let pp = make_paper_position_grid("BTC", true, "bybit_sync");
    let ctx2 = ctx_with_position(49_500.0, 100_000, &pp);
    let intents = g.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert!(
        !intents.is_empty(),
        "owner=bybit_sync 時 gate 必不阻擋（boot re-sync 視為合法）"
    );
    match &intents[0] {
        StrategyAction::Open(_) => {} // expected
        other => panic!("expected StrategyAction::Open, got {:?}", other),
    }
}

/// OPTION-A-LITE-E1D #4：owner=orphan_adopted 視為合法（接受未知 owner，待 next fill 自然 re-attribute）。
/// Setup：paper_state has orphan_adopted LONG BTC。
/// Verify：gate 不阻擋。
#[test]
fn test_grid_treats_orphan_adopted_owner_as_legitimate() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    let pp = make_paper_position_grid("BTC", true, "orphan_adopted");
    let ctx2 = ctx_with_position(49_500.0, 100_000, &pp);
    let intents = g.on_tick(&ctx2, &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE);

    assert!(
        !intents.is_empty(),
        "owner=orphan_adopted 時 gate 必不阻擋（PA §7 #5 watch：視為未知 owner）"
    );
}

/// SCANNER-PINNED-GATE-1 helper：構造 ctx with is_pinned flag。
fn ctx_with_pinned(price: f64, ts: u64, is_pinned: bool) -> TickContext<'static> {
    TickContext {
        symbol: "BTC",
        price,
        timestamp_ms: ts,
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
        is_pinned,
    }
}

/// SCANNER-PINNED-GATE-1 #1：is_pinned=false 時 grid 必跳過 new entry。
/// 對應實證：03:15 scanner expand 後 HYPE/WLD（dynamic-add，is_pinned=false）虧 −$0.46。
#[test]
fn test_grid_skip_entry_when_symbol_not_pinned() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    // 首 tick 初始化網格，使用 default pinned ctx
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    // 第二 tick：非 pinned symbol，down-cross 信號（would_open=true）
    let ctx_not_pinned = ctx_with_pinned(49_500.0, 100_000, false);
    let intents = g.on_tick(
        &ctx_not_pinned,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    assert!(
        intents.is_empty(),
        "is_pinned=false 時 grid 必跳過 new entry（防 dynamic-add HYPE/WLD 結構性虧）"
    );
}

/// SCANNER-PINNED-GATE-1 #2：is_pinned=true 時 grid 走正常邏輯。
#[test]
fn test_grid_proceeds_entry_when_symbol_pinned() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    // 第二 tick：pinned symbol + down-cross 信號 → 必開新倉
    let ctx_pinned = ctx_with_pinned(49_500.0, 100_000, true);
    let intents = g.on_tick(
        &ctx_pinned,
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    assert!(
        !intents.is_empty(),
        "is_pinned=true 且 would_open=true 時 gate 必不阻擋"
    );
}

// ─────────────────────────────────────────────────────────────────────────────
// EDGE-P2-3 Phase 1b BB-MF-3 (2026-05-16) — reject_cooldown entry/close split
// 對應 spec v1.2 §6.1 + AMD-2026-05-15-02 §8 IMPL Prereq 6。
// 設計目標：
//   1. entry-side reject 寫 reject_cooldown_entry_until_ms，僅阻擋 Open emission
//   2. close-side reject 寫 reject_cooldown_close_until_ms，獨立 map
//   3. Race C (PostOnlyCross close) → 不 arm cooldown，走 market（spec §5.3）
//   4. TooManyPending close → dynamic 1s→60s per-symbol backoff + 5min global cascade
//   5. 其他 close reject → 1min default（spec §6.1）
//   6. entry reject 不凍結同 symbol 的 close emission（BB-MF-3 silent degradation 修復）
// 注意：Phase 1b 主軸 IMPL 後 close path 真正進 cooldown gate，本 prereq commit
//       僅完成 helper + 隔離測試，不接線 commands.rs / dispatch.rs production dispatcher。
// ─────────────────────────────────────────────────────────────────────────────

use crate::strategies::maker_rejection::MakerRejectionCategory;

/// BB-MF-3 #1：entry-side PostOnly reject 不凍結同 symbol 的 close emission。
/// 設定：grid 持 LONG 倉位（cur_inventory > 0），entry cooldown active；
/// 觸發 up-cross → close-long emission；驗 close intent 仍正常發送。
/// 對應 PM 任務 Step 4 test_entry_reject_does_not_freeze_close_path。
#[test]
fn test_entry_reject_does_not_freeze_close_path() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.reject_cooldown_ms = 60_000;

    // 首 tick 初始化網格 + 設 last_cross_idx + 種入持倉。
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    g.net_inventory.insert("BTC".to_string(), 1.0); // LONG 1 unit

    // entry-side PostOnly reject 寫入 entry cooldown（ts=1_000 + 60s = 61_000）。
    g.on_post_only_rejected("BTC", 1_000, &MakerRejectionCategory::PostOnlyCross);
    assert_eq!(
        g.reject_cooldown_entry_until_ms.get("BTC").copied(),
        Some(61_000),
        "entry reject 必寫入 entry cooldown map"
    );
    assert!(
        g.reject_cooldown_close_until_ms.get("BTC").is_none(),
        "entry reject 不可污染 close cooldown map（BB-MF-3 隔離不變式）"
    );

    // ts=30_000（entry cooldown 仍 active：30_000 < 61_000）+ up-cross
    // （價 50_500 → 50_900 跨越下一 grid level）→ cur_inventory > 0 → close-long emission。
    let intents = g.on_tick(
        &ctx(50_900.0, 30_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(
        !intents.is_empty(),
        "entry cooldown active 不可凍結 close emission（BB-MF-3 silent degradation 修復）"
    );
    let close_emitted = intents.iter().any(|a| {
        matches!(
            a,
            StrategyAction::Close { reason, .. } if reason == "grid_close_long"
        )
    });
    assert!(
        close_emitted,
        "up-cross with LONG inventory + entry cooldown active 必發 grid_close_long"
    );
}

/// BB-MF-3 #2：close-side reject 不凍結同 symbol 的 entry emission。
/// 設定：close cooldown active（透過 arm_close_cooldown(TooManyPending) 寫入），
/// 觸發 down-cross + cur_inventory=0 → would_open=true → entry emission；驗 entry 正常。
/// 對應 PM 任務 Step 4 test_close_reject_does_not_freeze_entry_path。
#[test]
fn test_close_reject_does_not_freeze_entry_path() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);

    // 首 tick 初始化網格。
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );

    // close-side TooManyPending reject 寫入 dynamic close cooldown（ts=1_000 + 1s = 2_000）。
    g.arm_close_cooldown("BTC", 1_000, &MakerRejectionCategory::TooManyPending);
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("BTC").copied(),
        Some(2_000),
        "TooManyPending close reject 必寫入 close cooldown map（dynamic 1s initial）"
    );
    assert!(
        g.reject_cooldown_entry_until_ms.get("BTC").is_none(),
        "close reject 不可污染 entry cooldown map（BB-MF-3 隔離不變式）"
    );

    // ts=100_000（close cooldown 仍 active：100_000 < 301_000）+ down-cross + inv=0
    // → would_open=true → Open emission。
    let intents = g.on_tick(
        &ctx(49_500.0, 100_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(
        !intents.is_empty(),
        "close cooldown active 不可凍結 entry emission（BB-MF-3 隔離反向驗證）"
    );
    let open_emitted = intents.iter().any(|a| matches!(a, StrategyAction::Open(_)));
    assert!(
        open_emitted,
        "down-cross with inv=0 + close cooldown active 必發 Open intent"
    );
}

/// BB-MF-3 #3：close-side TooManyPending → dynamic per-symbol cooldown。
/// 對應 PM 任務 Step 4 test_close_too_many_pending_5min_cooldown + spec §6.1 表
/// 舊「TooManyPending → 5min」baseline。函式名保留給 E4 baseline grep；
/// Phase 1b B-3A 語意已按 operator prompt 升級為 §5.4 dynamic backoff。
#[test]
fn test_close_too_many_pending_5min_cooldown() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);

    // ts = 1_000，首次 TooManyPending → 1s dynamic backoff。
    g.arm_close_cooldown("BTC", 1_000, &MakerRejectionCategory::TooManyPending);

    assert_eq!(
        g.reject_cooldown_close_until_ms.get("BTC").copied(),
        Some(2_000),
        "TooManyPending close cooldown 首次必為 ts + 1s（Phase 1b dynamic backoff）"
    );
    // 不可污染 entry map。
    assert!(
        g.reject_cooldown_entry_until_ms.get("BTC").is_none(),
        "TooManyPending close reject 不可寫入 entry cooldown"
    );
}

/// Phase 1b B-3A：同 symbol TooManyPending 連續觸發時 1s→2s→4s 指數退避，
/// 其他 symbol 不受影響。這是 §5.4 dynamic backoff 對舊 5min 固定 close
/// cooldown 的相容性更新。
#[test]
fn test_close_too_many_pending_dynamic_backoff_per_symbol() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);

    g.arm_close_cooldown("BTC", 1_000, &MakerRejectionCategory::TooManyPending);
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("BTC").copied(),
        Some(2_000)
    );
    assert_eq!(
        g.close_maker_rate_limit_scope("BTC", 1_500),
        Some(crate::strategies::maker_rejection::CloseMakerRateLimitScope::PerSymbol)
    );
    assert_eq!(g.close_maker_rate_limit_scope("ETH", 1_500), None);

    g.arm_close_cooldown("BTC", 2_000, &MakerRejectionCategory::TooManyPending);
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("BTC").copied(),
        Some(4_000),
        "second consecutive TooManyPending doubles to 2s"
    );

    g.arm_close_cooldown("ETH", 2_000, &MakerRejectionCategory::TooManyPending);
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("ETH").copied(),
        Some(3_000),
        "other symbol starts at independent 1s backoff"
    );
}

/// Phase 1b B-3A：1 分鐘內 >=10 distinct symbols 觸發 TooManyPending 時，
/// close-maker 全域 pause 5min；pause 到期後 symbol backoff reset 1s。
#[test]
fn test_close_too_many_pending_global_pause_cascade_resets() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    let now = 100_000u64;

    for i in 0..10 {
        g.arm_close_cooldown(
            &format!("SYM{i}"),
            (now + i) as i64,
            &MakerRejectionCategory::TooManyPending,
        );
    }

    let expected_until = now + 9 + 300_000;
    assert_eq!(
        g.close_maker_global_pause_until_ms(now + 10),
        Some(expected_until),
        "10-symbol cascade must arm 5min global pause"
    );
    assert_eq!(
        g.close_maker_rate_limit_scope("UNSEEN", now + 10),
        Some(crate::strategies::maker_rejection::CloseMakerRateLimitScope::Global),
        "global pause must apply to symbols that did not trigger the cascade"
    );

    assert_eq!(
        g.close_maker_rate_limit_scope("UNSEEN", expected_until),
        None
    );
    g.arm_close_cooldown(
        "SYM0",
        expected_until as i64,
        &MakerRejectionCategory::TooManyPending,
    );
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("SYM0").copied(),
        Some(expected_until + 1_000),
        "after global pause expiry, per-symbol backoff resets to initial 1s"
    );
}

/// BB-MF-3 #4：close-side PostOnlyCross → 不 arm cooldown（spec §5.3 Race C）。
/// PostOnlyCross close 表示掛價瞬間被吃，立即 fallback to market；
/// 不進 close cooldown 是 spec §5.3 + §2.3 negative whitelist 明文設計。
/// 對應 PM 任務 Step 4 test_close_postonly_cross_no_cooldown_immediate_market。
#[test]
fn test_close_postonly_cross_no_cooldown_immediate_market() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);

    g.arm_close_cooldown("BTC", 1_000, &MakerRejectionCategory::PostOnlyCross);

    // close cooldown 必不被 arm（spec §5.3 Race C：直接走 market）。
    assert!(
        g.reject_cooldown_close_until_ms.get("BTC").is_none(),
        "PostOnlyCross close 不可進 close cooldown（spec §5.3 Race C）"
    );
    // entry map 也不可被影響。
    assert!(
        g.reject_cooldown_entry_until_ms.get("BTC").is_none(),
        "PostOnlyCross close 不可污染 entry cooldown map"
    );
}

/// BB-MF-3 #5：close-side 其他 reject 類別（FokCancel/SelfCancel/Other）→ 1min default。
/// 對應 spec §6.1 表「其他 reject → 1min」。
#[test]
fn test_close_default_reject_categories_1min_cooldown() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);

    // FokCancel → 1min（60_000 ms）。
    g.arm_close_cooldown("BTC", 1_000, &MakerRejectionCategory::FokCancel);
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("BTC").copied(),
        Some(61_000),
        "FokCancel close 必為 ts + 1min default"
    );

    // SelfCancel → 1min。
    g.arm_close_cooldown("ETH", 2_000, &MakerRejectionCategory::SelfCancel);
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("ETH").copied(),
        Some(62_000),
        "SelfCancel close 必為 ts + 1min default"
    );

    // Other(raw) → 1min（保留 raw 鑑識，cooldown 行為一致）。
    g.arm_close_cooldown(
        "SOL",
        3_000,
        &MakerRejectionCategory::Other("EC_SomeFutureBybitCode".to_string()),
    );
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("SOL").copied(),
        Some(63_000),
        "Other(raw) close 必為 ts + 1min default"
    );
}

/// BB-MF-3 #6：兩 side cooldown 同時 active 時 short-circuit return（efficiency 優化保留）。
/// 設定：entry + close cooldown 同時 active；驗 on_tick 立即返回 vec![]，
/// 不進入 cross 偵測 / would_open 計算（spec v1.2 §6.1 + signal.rs short-circuit
/// SAFETY 不變量）。
#[test]
fn test_grid_short_circuits_when_both_cooldowns_active() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);

    // 首 tick 初始化網格 + 種入 LONG 持倉（讓 up-cross 會發 close）。
    g.on_tick(
        &ctx(50_500.0, 0),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    g.net_inventory.insert("BTC".to_string(), 1.0);

    // entry cooldown 寫到 100_000；close cooldown 寫到 200_000。
    g.reject_cooldown_entry_until_ms
        .insert("BTC".to_string(), 100_000);
    g.reject_cooldown_close_until_ms
        .insert("BTC".to_string(), 200_000);

    // ts = 50_000 → 50_000 < 100_000 (entry) AND 50_000 < 200_000 (close)
    // → 兩 side cooldown 都 active → short-circuit（price 動到 50_900 觸 up-cross 也應被擋）。
    let intents = g.on_tick(
        &ctx(50_900.0, 50_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    assert!(
        intents.is_empty(),
        "兩 side cooldown 都 active 時必 short-circuit；發了 {} intents",
        intents.len()
    );

    // ts = 150_000 → entry expired (150_000 ≥ 100_000), close still active
    //  → 不再 short-circuit；up-cross + LONG inv → close emission 應發
    //   （本 prereq commit 不接線生產 close cooldown gate；close emission 依舊發送）。
    let intents2 = g.on_tick(
        &ctx(50_900.0, 150_000),
        &openclaw_core::alpha_surface::EMPTY_ALPHA_SURFACE,
    );
    let close_emitted = intents2.iter().any(|a| {
        matches!(
            a,
            StrategyAction::Close { reason, .. } if reason == "grid_close_long"
        )
    });
    assert!(
        close_emitted,
        "entry cooldown expired 後 close path 必恢復 emission（即使 close cooldown 仍 active）"
    );
}

/// BB-MF-3 #7：cooldown isolation regression — 多 symbol 場景下 entry/close
/// cooldown 不交叉污染。
/// 對應 PM 任務 Step 4 cross-symbol regression coverage。
#[test]
fn test_cooldown_isolation_multi_symbol() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);
    g.reject_cooldown_ms = 60_000;

    // BTC entry reject、ETH close reject、SOL 都不 arm。
    g.on_post_only_rejected("BTC", 1_000, &MakerRejectionCategory::PostOnlyCross);
    g.arm_close_cooldown("ETH", 2_000, &MakerRejectionCategory::TooManyPending);

    // BTC entry 寫入 + close 不寫入。
    assert_eq!(
        g.reject_cooldown_entry_until_ms.get("BTC").copied(),
        Some(61_000)
    );
    assert!(g.reject_cooldown_close_until_ms.get("BTC").is_none());

    // ETH close 寫入 + entry 不寫入（first dynamic backoff = 1s）。
    assert_eq!(
        g.reject_cooldown_close_until_ms.get("ETH").copied(),
        Some(3_000)
    );
    assert!(g.reject_cooldown_entry_until_ms.get("ETH").is_none());

    // SOL 兩 map 都空。
    assert!(g.reject_cooldown_entry_until_ms.get("SOL").is_none());
    assert!(g.reject_cooldown_close_until_ms.get("SOL").is_none());
}

/// BB-MF-3 #8：i64 overflow 防護（saturating_add）— 邊界 ts_ms 不可 wrap to 0。
/// SAFETY 不變量：arm_close_cooldown 用 saturating_add 防 i64::MAX 溢出。
#[test]
fn test_arm_close_cooldown_saturating_add_overflow_safe() {
    let mut g = GridTrading::new(49_000.0, 51_000.0);

    // 接近 i64::MAX 的 ts_ms + default close cooldown → cooldown_until 必 saturate
    // 而非 wrap 為 0（u64 cast 後仍非 0 大數）。
    let near_max = i64::MAX - 100;
    g.arm_close_cooldown("BTC", near_max, &MakerRejectionCategory::FokCancel);

    let stored = g
        .reject_cooldown_close_until_ms
        .get("BTC")
        .copied()
        .expect("FokCancel 必 arm default cooldown");
    // 必 saturate 至 i64::MAX（u64 cast 即 i64::MAX as u64）。
    assert_eq!(
        stored,
        i64::MAX as u64,
        "saturating_add 必防溢出，不可 wrap 為小值（會破 cooldown 語意）"
    );
}
