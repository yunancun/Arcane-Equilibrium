//! M12 OrderRouter trait stub — Sprint 1A-δ integration test。
//!
//! MODULE_NOTE
//! 模塊用途：驗證 `order_router` module 的 trait stub 行為：
//!   1. `Box<dyn OrderRouter>` dyn safety smoke（trait object 可建構）。
//!   2. `route_order` 對 `Venue::BinancePerp` / `Venue::BinanceOption` 走
//!      `Err(RoutingError::VenueDeferred)` early return（不 panic；5-gate
//!      inheritance 紅線）。
//!   3. 其他 5 method（venue_health / cross_venue_position / forecast_slippage /
//!      reverse_snipe / maker_fill_rate_30d）+ Bybit 路徑 `route_order` 全走
//!      `unimplemented!()` panic（fail-loud）。
//!   4. `MakerTier` 4-variant 枚舉 round-trip。
//! 依賴：openclaw_engine::order_router public API + openclaw_types Venue / AssetClass。
//! 硬邊界：
//!   - 不引入 mock 隱蔽邏輯（per E4 SOP）；純驗 stub 行為。
//!   - 不模擬 Sprint 6+ adaptive routing；任何 method body 真實邏輯 = scope creep。
//!
//! 參考：
//!   - ADR-0039 §Decision 1 authoritative 6 method signature。
//!   - PA spec §6.1 E1 dispatch brief test scope。

use openclaw_engine::order_router::{
    DefensiveAction, MakerFillRateStats, MakerTier, MarketEvent, MarketSnapshot, NetPosition,
    OrderRequest, OrderRouter, RoutingDecision, RoutingError, SlippageEstimate,
    UnimplementedOrderRouter, VenueHealth,
};
use openclaw_types::{AssetClass, Venue};

/// 構造一個 Bybit 路徑 sample order request（其他 test 共用 helper）。
fn sample_bybit_order_request() -> OrderRequest {
    OrderRequest {
        symbol: "BTCUSDT".to_string(),
        venue: Venue::BybitPerp,
        asset_class: AssetClass::Perp,
        side_is_buy: true,
        qty: 0.01,
        price: Some(50_000.0),
        order_type_hint: "postonly".to_string(),
    }
}

/// 構造一個 Binance 路徑 sample order request（驗 Y3+ defer hardcode）。
fn sample_binance_perp_order_request() -> OrderRequest {
    OrderRequest {
        symbol: "BTCUSDT".to_string(),
        venue: Venue::BinancePerp,
        asset_class: AssetClass::Perp,
        side_is_buy: true,
        qty: 0.01,
        price: Some(50_000.0),
        order_type_hint: "postonly".to_string(),
    }
}

fn sample_binance_option_order_request() -> OrderRequest {
    OrderRequest {
        symbol: "BTC-26JUN26-50000-C".to_string(),
        venue: Venue::BinanceOption,
        asset_class: AssetClass::Option,
        side_is_buy: true,
        qty: 1.0,
        price: Some(0.05),
        order_type_hint: "limit".to_string(),
    }
}

// ============================================================================
// AC-1：trait object dyn safety smoke
// ============================================================================

#[test]
fn test_order_router_trait_object_constructible() {
    // 為什麼：caller 在 Sprint 6+ IMPL 前可能持有 `Box<dyn OrderRouter>` 引用，
    // trait 必須滿足 dyn safe；任一 method signature 違反 dyn safety（如
    // self-referencing return type）會在此 compile fail。
    let router: Box<dyn OrderRouter> = Box::new(UnimplementedOrderRouter);
    // 構造合法即驗證通過；不呼叫任何 method（其餘 method panic 由獨立 test 驗）。
    // 觸碰 router 以避免 unused warning：對 Bybit 路徑呼叫會 panic，這裡用 forget
    // 不執行 method；簡單檢查 Box 已成功 allocate。
    drop(router);
}

// ============================================================================
// AC-2/3：route_order Binance Y3+ defer 路徑（不 panic；Err return）
// ============================================================================

#[test]
fn test_route_order_binance_perp_returns_y3_deferred() {
    // 紅線：BinancePerp 必走 Err(VenueDeferred("Y3+ per ADR-0033"))；不 panic。
    let router = UnimplementedOrderRouter;
    let result = router.route_order(&sample_binance_perp_order_request());
    match result {
        Err(RoutingError::VenueDeferred(reason)) => {
            assert!(
                reason.contains("Y3+"),
                "expected defer reason contain 'Y3+', got: {}",
                reason
            );
            assert!(
                reason.contains("ADR-0033"),
                "expected defer reason contain 'ADR-0033', got: {}",
                reason
            );
        }
        other => panic!(
            "expected Err(RoutingError::VenueDeferred(_)) for BinancePerp, got: {:?}",
            other
        ),
    }
}

#[test]
fn test_route_order_binance_option_returns_y3_deferred() {
    // 紅線：BinanceOption 必走 Err(VenueDeferred("Y3+ per ADR-0033"))；不 panic。
    let router = UnimplementedOrderRouter;
    let result = router.route_order(&sample_binance_option_order_request());
    assert!(
        matches!(result, Err(RoutingError::VenueDeferred(_))),
        "expected Err(VenueDeferred) for BinanceOption, got: {:?}",
        result
    );
}

// ============================================================================
// AC-4：route_order Bybit 路徑 panic（Sprint 6+ IMPL pending）
// ============================================================================

#[test]
#[should_panic(expected = "M12")]
fn test_route_order_bybit_panics_pending_sprint6_impl() {
    // Bybit 路徑（BybitPerp / BybitSpot / BybitOption）在 Sprint 1A-δ 全走 panic；
    // Sprint 6+ IMPL 期才 override default body 加 Bybit-only adaptive routing。
    let router = UnimplementedOrderRouter;
    let _ = router.route_order(&sample_bybit_order_request());
}

// ============================================================================
// AC-5：剩餘 5 method panic verify（fail-loud；Sprint 6+ IMPL pending）
// ============================================================================

#[test]
#[should_panic(expected = "M12")]
fn test_venue_health_panics_pending_sprint6_impl() {
    let router = UnimplementedOrderRouter;
    let _ = router.venue_health(Venue::BybitPerp);
}

#[test]
#[should_panic(expected = "M12")]
fn test_cross_venue_position_panics_pending_sprint6_impl() {
    let router = UnimplementedOrderRouter;
    let _ = router.cross_venue_position(AssetClass::Perp);
}

#[test]
#[should_panic(expected = "M12")]
fn test_forecast_slippage_panics_pending_sprint6_impl() {
    let router = UnimplementedOrderRouter;
    let snapshot = MarketSnapshot::default();
    let _ = router.forecast_slippage(&sample_bybit_order_request(), &snapshot);
}

#[test]
#[should_panic(expected = "M12")]
fn test_reverse_snipe_panics_pending_sprint6_impl() {
    let router = UnimplementedOrderRouter;
    let _ = router.reverse_snipe(&MarketEvent::LiquidationCascade);
}

#[test]
#[should_panic(expected = "M12")]
fn test_maker_fill_rate_30d_panics_pending_sprint6_impl() {
    let router = UnimplementedOrderRouter;
    let _ = router.maker_fill_rate_30d("BTCUSDT");
}

// ============================================================================
// AC-6：MakerTier 4-variant 枚舉 round-trip
// ============================================================================

#[test]
fn test_maker_tier_enum_variants() {
    // 為什麼：ADR-0039 §Decision 2 列 4-tier rebate eligibility（Tier1 / Tier2 /
    // Default / Penalty）；驗證 enum 4 variant 全可建構 + 比較相等性 + 可作為
    // MakerFillRateStats.current_tier 欄位。
    let tiers = [
        MakerTier::Tier1,
        MakerTier::Tier2,
        MakerTier::Default,
        MakerTier::Penalty,
    ];
    assert_eq!(tiers.len(), 4);
    // 4 variant 必須兩兩不等（驗 PartialEq derive 正確）。
    assert_ne!(tiers[0], tiers[1]);
    assert_ne!(tiers[1], tiers[2]);
    assert_ne!(tiers[2], tiers[3]);
    assert_ne!(tiers[0], tiers[3]);

    // MakerFillRateStats data carrier 構造驗（純 struct round-trip）。
    let stats = MakerFillRateStats {
        window_30d_maker_notional: 75_000.0,
        window_30d_total_notional: 100_000.0,
        current_tier: MakerTier::Tier2,
    };
    assert_eq!(stats.current_tier, MakerTier::Tier2);
    assert!((stats.window_30d_maker_notional - 75_000.0).abs() < 1e-9);
}

// ============================================================================
// AC-7：周邊 struct 純構造驗（無 method panic；data carrier 行為）
// ============================================================================

#[test]
fn test_helper_structs_constructible() {
    // 為什麼：周邊 11 helper types 必須能在 Sprint 6+ IMPL 前就能構造（caller
    // 可能在 unit test / fixture 中需要 dummy data carrier）；驗無 hidden panic
    // path 在 struct construction 階段。
    let _decision = RoutingDecision {
        chosen_venue: Venue::BybitPerp,
        chosen_order_type: "postonly".to_string(),
        slice_count: 1,
        time_in_force: "GTC".to_string(),
        route_reason: "default_postonly".to_string(),
        decision_id: "test-uuid".to_string(),
    };
    let _vh = VenueHealth {
        rejection_rate_24h: 0.01,
        latency_p99_ms: 50.0,
        connection_stable: true,
    };
    let _np = NetPosition {
        net_qty: 0.5,
        net_notional_usdt: 25_000.0,
        asset_class: AssetClass::Perp,
    };
    let _se = SlippageEstimate {
        predicted_slippage_bps: 2.5,
        confidence_interval_bps: 1.0,
    };
    let _da = DefensiveAction::PostOnlyFallback;
    let _me = MarketEvent::LargeWick;
    // 全部構造成功即 pass。
}
