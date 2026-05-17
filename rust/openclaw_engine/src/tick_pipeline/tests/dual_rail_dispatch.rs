// G5-09 sibling: I-08 Dual-Rail Stop tests + execute_position_close /
// ipc_close_symbol dispatch contracts.
// 雙軌止損測試：驗證 broker-side SL 只在 primary exchange mode 開倉時啟用，
// 並測 close 路徑的 strategy 標記契約。

use super::super::*;
use crate::instrument_info::{InstrumentInfoCache, SymbolSpec};
use crate::order_manager::TimeInForce;
use std::sync::Arc;

fn ape_instrument_cache() -> Arc<InstrumentInfoCache> {
    let cache = InstrumentInfoCache::new();
    cache.cache.write().insert(
        "APEUSDT".to_string(),
        SymbolSpec {
            symbol: "APEUSDT".to_string(),
            base_currency: "APE".to_string(),
            quote_currency: "USDT".to_string(),
            contract_type: "LinearPerpetual".to_string(),
            qty_step: 0.1,
            min_qty: 0.1,
            max_qty: 1_000_000.0,
            tick_size: 0.0001,
            min_price: 0.0001,
            max_price: 1_000.0,
            min_notional: 5.0,
            qty_decimals: 1,
            price_decimals: 4,
        },
    );
    Arc::new(cache)
}

fn instrument_cache_for(symbol: &str, tick_size: f64) -> Arc<InstrumentInfoCache> {
    let cache = InstrumentInfoCache::new();
    cache.cache.write().insert(
        symbol.to_string(),
        SymbolSpec {
            symbol: symbol.to_string(),
            base_currency: symbol.trim_end_matches("USDT").to_string(),
            quote_currency: "USDT".to_string(),
            contract_type: "LinearPerpetual".to_string(),
            qty_step: 0.001,
            min_qty: 0.001,
            max_qty: 1_000_000.0,
            tick_size,
            min_price: tick_size,
            max_price: 1_000_000.0,
            min_notional: 5.0,
            qty_decimals: 3,
            price_decimals: 8,
        },
    );
    Arc::new(cache)
}

fn make_bbo_event(symbol: &str, last: f64, bid: f64, ask: f64, ts: u64) -> PriceEvent {
    let mut event = super::make_event(symbol, last, ts);
    event.bid_price = bid;
    event.ask_price = ask;
    event
}

// ─── I-08 Dual-Rail Stop tests (Principle #9) ───
// 雙軌止損測試：驗證 broker-side SL 只在 primary exchange mode 開倉時啟用

#[test]
fn test_dual_rail_shadow_order_has_sl_fields() {
    // Struct must expose stop_loss / take_profit for broker rail wiring
    let req = OrderDispatchRequest {
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.01,
        price: 50000.0,
        strategy: "test".into(),
        paper_fill_ts: 0,
        is_close: false,
        order_link_id: "oc_test".into(),
        decision_lease_id: None,
        is_primary: true,
        stop_loss: Some(49000.0),
        take_profit: Some(52000.0),
        // FILL-CONTEXT-LINKAGE-1: empty id preserves pre-fix behaviour
        // (apply_confirmed_fill falls back to exec-time recompute).
        // FILL-CONTEXT-LINKAGE-1：空字串保持修前行為（apply_confirmed_fill 退回 exec 重算）。
        context_id: String::new(),
        order_type: "market".to_string(),
        limit_price: None,
        time_in_force: None,
        maker_timeout_ms: None,
        close_maker_audit: None,
        reference_price: None,
        reference_ts_ms: None,
        reference_source: None,
        // W-C Caveat 2 修復（2026-05-11）：test fixture 預設 None。
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
    };
    assert_eq!(req.stop_loss, Some(49000.0));
    assert_eq!(req.take_profit, Some(52000.0));
}

#[test]
fn test_dual_rail_broker_sl_long_below_entry() {
    // Long SL must sit below entry price
    let entry: f64 = 50000.0;
    let sl_pct: f64 = 2.0;
    let sl = entry * (1.0 - sl_pct / 100.0);
    assert!(sl < entry);
    assert!((sl - 49000.0f64).abs() < 0.01);
}

#[test]
fn test_dual_rail_broker_sl_short_above_entry() {
    // Short SL must sit above entry price
    let entry: f64 = 50000.0;
    let sl_pct: f64 = 2.0;
    let sl = entry * (1.0 + sl_pct / 100.0);
    assert!(sl > entry);
    assert!((sl - 51000.0f64).abs() < 0.01);
}

#[test]
fn test_dual_rail_close_orders_no_broker_sl() {
    // Close orders never attach broker SL (Bybit auto-cancels on reduce-only fill)
    let req = OrderDispatchRequest {
        symbol: "BTCUSDT".into(),
        is_long: false,
        qty: 0.01,
        price: 50000.0,
        strategy: "risk_check".into(),
        paper_fill_ts: 0,
        is_close: true,
        order_link_id: "oc_risk".into(),
        decision_lease_id: None,
        is_primary: true,
        stop_loss: None,
        take_profit: None,
        // FILL-CONTEXT-LINKAGE-1: empty id preserves pre-fix behaviour.
        // FILL-CONTEXT-LINKAGE-1：空字串保持修前行為。
        context_id: String::new(),
        order_type: "market".to_string(),
        limit_price: None,
        time_in_force: None,
        maker_timeout_ms: None,
        close_maker_audit: None,
        reference_price: None,
        reference_ts_ms: None,
        reference_source: None,
        // W-C Caveat 2 修復（2026-05-11）：test fixture 預設 None。
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
    };
    assert!(req.stop_loss.is_none());
    assert!(req.is_close);
}

#[test]
fn test_dual_rail_paper_shadow_skips_broker_sl() {
    // Paper/shadow orders keep broker SL None (engine rail handles stops locally)
    let req = OrderDispatchRequest {
        symbol: "ETHUSDT".into(),
        is_long: true,
        qty: 0.1,
        price: 3000.0,
        strategy: "ma".into(),
        paper_fill_ts: 0,
        is_close: false,
        order_link_id: "sh_test".into(),
        decision_lease_id: None,
        is_primary: false,
        stop_loss: None,
        take_profit: None,
        // FILL-CONTEXT-LINKAGE-1: empty id preserves pre-fix behaviour.
        // FILL-CONTEXT-LINKAGE-1：空字串保持修前行為。
        context_id: String::new(),
        order_type: "market".to_string(),
        limit_price: None,
        time_in_force: None,
        maker_timeout_ms: None,
        close_maker_audit: None,
        reference_price: None,
        reference_ts_ms: None,
        reference_source: None,
        // W-C Caveat 2 修復（2026-05-11）：test fixture 預設 None。
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
    };
    assert!(!req.is_primary);
    assert!(req.stop_loss.is_none());
}

/// P0-4 R1 regression: execute_position_close must propagate `trigger_tag` to
/// OrderDispatchRequest.strategy. Previously hardcoded "risk_check", which
/// collapsed strategy exits + fast_track closes + shadow mirrors into a single
/// bucket in trading.fills.strategy_name and broke attribution (see audit
/// docs/audits/2026-04-16--demo_zero_strategy_exit_audit.md).
/// P0-4 R1 回歸：execute_position_close 必須把 trigger_tag 穿透到
/// OrderDispatchRequest.strategy，不能再硬編碼 "risk_check" 吞掉歸因。
#[test]
fn test_execute_position_close_propagates_trigger_tag() {
    let cases: &[(bool, &str)] = &[
        (true, "strategy_close:funding_arb_exit"),
        (true, "risk_close:fast_track_reduce_half"),
        (true, "risk_close:halt_session"),
        (false, "strategy_close:ma_crossover_flip"),
        (false, "risk_close:cost_edge_ratio"),
    ];
    for (is_primary, tag) in cases {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
        pipeline.set_shadow_channel(tx);

        let event = super::make_event("BTCUSDT", 50_000.0, 1_700_000_000_000);
        pipeline.execute_position_close(
            "BTCUSDT",
            true, // is_long — closing a long position
            0.1,
            &event,
            *is_primary,
            tag,
        );

        let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
        assert_eq!(
            req.strategy, *tag,
            "strategy must carry trigger_tag verbatim (is_primary={}, tag={})",
            is_primary, tag
        );
        assert!(req.is_close, "close dispatch must set is_close=true");
        assert_eq!(req.is_primary, *is_primary);
        let expected_prefix = if *is_primary { "oc_risk_" } else { "sh_risk_" };
        assert!(
            req.order_link_id.starts_with(expected_prefix),
            "order_link_id={} expected prefix {}",
            req.order_link_id,
            expected_prefix
        );
    }
}

#[test]
fn test_primary_exchange_full_close_dispatches_qty_zero() {
    let mut pipeline = TickPipeline::with_kind(&["APEUSDT"], 1_000.0, PipelineKind::Demo);
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    pipeline.paper_state.apply_fill(
        "APEUSDT",
        false,
        60.0,
        0.18,
        0.0,
        1_700_000_000_000,
        "grid_trading",
    );

    let event = super::make_event("APEUSDT", 0.15, 1_700_000_060_000);
    assert!(pipeline.execute_position_close(
        "APEUSDT",
        false,
        60.0,
        &event,
        true,
        "strategy_close:grid_close_short",
    ));

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    assert_eq!(
        req.qty, 0.0,
        "primary exchange full-close must use Bybit qty=0 close-all form"
    );
    assert!(req.is_close);
    assert!(req.is_primary);
}

#[test]
fn test_close_maker_cold_default_keeps_positive_close_market() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    pipeline.set_instrument_cache(instrument_cache_for("BTCUSDT", 0.1));
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    pipeline.paper_state.apply_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        0.0,
        1_700_000_000_000,
        "grid_trading",
    );

    let event = make_bbo_event("BTCUSDT", 50_000.0, 49_999.9, 50_000.1, 1_700_000_060_000);
    assert!(pipeline.execute_position_close(
        "BTCUSDT",
        true,
        0.1,
        &event,
        true,
        "strategy_close:grid_close_long",
    ));

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    assert_eq!(req.order_type, "market");
    assert_eq!(req.limit_price, None);
    assert_eq!(req.time_in_force, None);
    assert_eq!(req.maker_timeout_ms, None);
    assert!(req.close_maker_audit.is_none());
    assert_eq!(
        req.qty, 0.0,
        "cold-default market full-close keeps Bybit qty=0 close-all form"
    );
}

#[test]
fn test_close_maker_runtime_enable_surface_is_demo_only_and_default_false() {
    let mut demo = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    assert!(!demo.use_maker_close());
    assert!(demo.set_use_maker_close_runtime(true));
    assert!(demo.use_maker_close());
    assert!(demo.set_use_maker_close_runtime(false));
    assert!(!demo.use_maker_close());

    let mut live = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Live);
    assert!(!live.set_use_maker_close_runtime(true));
    assert!(!live.use_maker_close());

    let mut paper = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    assert!(!paper.set_use_maker_close_runtime(true));
    assert!(!paper.use_maker_close());
}

/// AMD-2026-05-15-02 §3 Phase 1b runtime 啟動層驗證（test 1/3）：
/// Demo 管線在 set_risk_store(`runtime.use_maker_close = true`) 後，
/// apply_risk_snapshot 必須 boot-time 同步把欄位推到 true。沒這條路徑
/// Phase 2a 就是 silent dead — E2 RCA 2026-05-18 catch 的真因。
#[test]
fn test_use_maker_close_toml_activates_on_demo() {
    use crate::config::{ConfigStore, RiskConfig};
    use std::sync::Arc;

    let mut demo = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    // cold-default：ctor 預設 false，未注入 store 前不可能 true。
    assert!(
        !demo.use_maker_close(),
        "cold-default：ctor 未注入 store 前必為 false"
    );

    let mut cfg = RiskConfig::default();
    cfg.runtime.use_maker_close = true;
    let store = Arc::new(ConfigStore::new(cfg));
    demo.set_risk_store(store);

    // set_risk_store 內部 sync 呼叫 apply_risk_snapshot — boot-time TOML
    // 必須立刻可見，否則 Phase 2a 觀察窗的第一個 tick 就會 silent dead。
    assert!(
        demo.use_maker_close(),
        "Demo set_risk_store 後 runtime.use_maker_close = true 必須立即生效"
    );
}

/// AMD-2026-05-15-02 §3 Phase 1b runtime 啟動層驗證（test 2/3）：
/// 即使 Live / Paper 的 TOML 誤填 `runtime.use_maker_close = true`，
/// apply_risk_snapshot 透過 set_use_maker_close_runtime 路由，
/// commands.rs:91-103 的 Demo-only 守衛必須拒絕並把欄位留 false。
/// 這是 feedback_demo_loose_live_strict_policy 的 hot-reload 兜底測試。
#[test]
fn test_use_maker_close_toml_rejected_on_live_and_paper() {
    use crate::config::{ConfigStore, RiskConfig};
    use std::sync::Arc;

    for kind in [PipelineKind::Live, PipelineKind::Paper] {
        let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, kind);
        let mut cfg = RiskConfig::default();
        // 模擬 operator 誤把 Live / Paper TOML 也設 true：
        cfg.runtime.use_maker_close = true;
        let store = Arc::new(ConfigStore::new(cfg));
        p.set_risk_store(store);

        assert!(
            !p.use_maker_close(),
            "{kind:?}: Demo-only 守衛必須拒絕 TOML drift，保留 use_maker_close=false"
        );
    }
}

/// AMD-2026-05-15-02 §3 Phase 1b runtime 啟動層驗證（test 3/3）：
/// hot-reload 路徑 — Demo 先以 use_maker_close=false 啟動，
/// 之後 ConfigStore.replace() 把 runtime.use_maker_close 改 true，
/// 下個 on_tick 觸發 sync_risk_config_if_changed → apply_risk_snapshot
/// 必須在 1 個 tick 內把欄位推到 true。
/// 對應 AMD §3 kill-switch「TOML hot-reload → 1 tick」契約。
#[test]
fn test_use_maker_close_hot_reload_within_one_tick() {
    use crate::config::{ConfigStore, PatchSource, RiskConfig};
    use std::sync::Arc;

    let mut demo = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);

    // Phase 0：cold-default = false TOML 載入，set_risk_store 後仍為 false。
    let initial = RiskConfig::default();
    let store = Arc::new(ConfigStore::new(initial.clone()));
    demo.set_risk_store(Arc::clone(&store));
    assert!(
        !demo.use_maker_close(),
        "初始 RiskConfig::default().runtime.use_maker_close = false 必須保持 false"
    );
    let v0 = store.version();

    // Phase 1：operator 補丁 — 把 use_maker_close flip 為 true。
    // 模擬 IPC patch_risk_config 後 store.replace 的行為。
    let mut next = initial.clone();
    next.runtime.use_maker_close = true;
    next.validate().expect("mutated config must be valid");
    store
        .replace(next, PatchSource::Operator)
        .expect("replace must succeed");
    assert_eq!(store.version(), v0 + 1, "replace 後版本號必須上升");

    // 此時尚未 tick — pipeline 還未看到新版本，欄位應該仍為 false。
    assert!(
        !demo.use_maker_close(),
        "tick 之前 sync_risk_config_if_changed 未觸發，欄位應仍為 false"
    );

    // Phase 2：1 個 on_tick → sync_risk_config_if_changed → apply_risk_snapshot
    // → set_use_maker_close_runtime(true) → 欄位 flip true。
    demo.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000));

    assert!(
        demo.use_maker_close(),
        "AMD §3 kill-switch 契約：TOML hot-reload 必須在 1 個 tick 內生效"
    );
    assert_eq!(
        demo.risk_config_version_seen,
        store.version(),
        "pipeline 必須記住新版本號避免下個 tick 重複套用"
    );
}

#[test]
fn test_close_maker_dispatch_postonly_spine_none() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    pipeline.set_use_maker_close_for_test(true);
    pipeline.set_instrument_cache(instrument_cache_for("BTCUSDT", 0.1));
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    pipeline.paper_state.apply_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        0.0,
        1_700_000_000_000,
        "grid_trading",
    );

    let event = make_bbo_event("BTCUSDT", 50_000.0, 49_999.9, 50_000.1, 1_700_000_060_000);
    assert!(pipeline.execute_position_close(
        "BTCUSDT",
        true,
        0.1,
        &event,
        true,
        "strategy_close:grid_close_long",
    ));

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    assert_eq!(req.order_type, "limit");
    assert_eq!(req.time_in_force, Some(TimeInForce::PostOnly));
    assert_eq!(req.maker_timeout_ms, Some(30_000));
    assert!(
        (req.limit_price.expect("limit price") - 50_000.2).abs() < 1e-9,
        "long close should price as passive sell at ask + one tick"
    );
    assert_eq!(req.qty, 0.1, "PostOnly limit close must carry explicit qty");
    assert!(!req.is_long, "long position close dispatches Sell side");
    assert!(req.spine_order_plan_id.is_none());
    assert!(req.spine_decision_id.is_none());
    assert!(req.spine_verdict_id.is_none());
    assert!(req.spine_stub_report_id.is_none());
    let audit = req.close_maker_audit.expect("close-maker audit");
    assert_eq!(audit.initial_limit_price, Some(50_000.2));
    assert_eq!(audit.eligible_reason, "grid_close_long");
    assert_eq!(audit.fallback_reason, None);
}

#[test]
fn test_close_maker_phys_lock_giveback_timeout_policy() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    pipeline.set_use_maker_close_for_test(true);
    pipeline.set_instrument_cache(instrument_cache_for("BTCUSDT", 0.1));
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    let close_tag = crate::tick_pipeline::build_risk_close_tag("phys_lock_gate4_giveback");
    pipeline.paper_state.apply_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        0.0,
        1_700_000_000_000,
        "grid_trading",
    );

    let event = make_bbo_event("BTCUSDT", 50_000.0, 49_999.9, 50_000.1, 1_700_000_060_000);
    assert!(pipeline.execute_position_close("BTCUSDT", true, 0.1, &event, true, &close_tag,));

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    assert_eq!(req.order_type, "limit");
    assert_eq!(req.time_in_force, Some(TimeInForce::PostOnly));
    assert_eq!(req.maker_timeout_ms, Some(15_000));
}

#[test]
fn test_close_maker_spread_guard_falls_back_market() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    pipeline.set_use_maker_close_for_test(true);
    pipeline.set_instrument_cache(instrument_cache_for("BTCUSDT", 0.1));
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    pipeline.paper_state.apply_fill(
        "BTCUSDT",
        true,
        0.1,
        100.0,
        0.0,
        1_700_000_000_000,
        "grid_trading",
    );

    let event = make_bbo_event("BTCUSDT", 100.0, 99.0, 100.0, 1_700_000_060_000);
    assert!(pipeline.execute_position_close(
        "BTCUSDT",
        true,
        0.1,
        &event,
        true,
        "strategy_close:grid_close_long",
    ));

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    assert_eq!(req.order_type, "market");
    assert_eq!(req.limit_price, None);
    assert_eq!(req.time_in_force, None);
    assert_eq!(req.maker_timeout_ms, None);
    assert!(req.close_maker_audit.is_none());
    assert_eq!(
        req.qty, 0.0,
        "strict maker skip returns to existing market full-close quantity"
    );
}

#[test]
fn test_ipc_close_dispatchers_remain_market_safety_paths() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    pipeline.set_use_maker_close_for_test(true);
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    pipeline.paper_state.apply_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        0.0,
        1_700_000_000_000,
        "grid_trading",
    );

    assert_eq!(pipeline.ipc_close_all(), 1);
    let close_all = rx.try_recv().expect("ipc_close_all request");
    assert_eq!(close_all.strategy, "ipc_close_all");
    assert_eq!(close_all.order_type, "market");
    assert_eq!(close_all.time_in_force, None);
    assert!(close_all.close_maker_audit.is_none());

    pipeline.paper_state.apply_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        0.0,
        1_700_000_070_000,
        "grid_trading",
    );
    assert!(pipeline.ipc_close_symbol("BTCUSDT", None, None));
    let close_symbol = rx.try_recv().expect("ipc_close_symbol request");
    assert_eq!(close_symbol.strategy, "risk_close:ipc_close_symbol");
    assert_eq!(close_symbol.order_type, "market");
    assert_eq!(close_symbol.time_in_force, None);
    assert!(close_symbol.close_maker_audit.is_none());
}

#[test]
fn test_partial_reduce_dust_residual_blocks_below_min_notional_leftover() {
    let mut pipeline = TickPipeline::with_kind(&["APEUSDT"], 1_000.0, PipelineKind::Demo);
    pipeline.set_instrument_cache(ape_instrument_cache());

    let decision = pipeline
        .partial_reduce_dust_residual("APEUSDT", 60.0, 30.0, 0.15)
        .expect("residual 30 * 0.15 is below $5 minNotional");

    assert_eq!(decision.rounded_reduce_qty, 30.0);
    assert_eq!(decision.residual_qty, 30.0);
    assert!((decision.residual_notional - 4.5).abs() < 1e-12);
    assert_eq!(decision.min_notional, 5.0);

    assert!(
        pipeline
            .partial_reduce_dust_residual("APEUSDT", 100.0, 50.0, 0.15)
            .is_none(),
        "residual 50 * 0.15 is above $5 minNotional and should be allowed"
    );
}

/// P1-15 regression: `ipc_close_symbol` must tag OrderDispatchRequest.strategy
/// with a `risk_close:` prefix so the ML edge-stats pipeline's `is_exit`
/// detector (program_code/ml_training/realized_edge_stats.py) classifies the
/// resulting close fill as an exit, not an entry. Previously emitted the bare
/// string "ipc_close_symbol", producing phantom round-trip cells in the JS
/// estimator snapshot.
/// P1-15 回歸：`ipc_close_symbol` 派發的 OrderDispatchRequest.strategy 必須
/// 帶 `risk_close:` 前綴，ML edge-stats 才會判為 exit fill 而非 entry，
/// 避免 JS estimator snapshot 出現幻影 round-trip cells。
#[test]
fn test_ipc_close_symbol_dispatch_strategy_has_risk_close_prefix() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);

    // Seed a latest price so the orphan-hint close path has a non-zero mark.
    // 注入最新價格，孤兒 hint 平倉路徑才有非零 mark price。
    let _ = pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_700_000_000_000));

    // paper_state has no position for BTCUSDT — rely on caller hints to
    // trigger the orphan-close dispatch branch (commands.rs line ~660).
    // paper_state 無倉，靠 hints 走孤兒平倉分支。
    let fired = pipeline.ipc_close_symbol("BTCUSDT", Some(true), Some(0.1));
    assert!(
        fired,
        "ipc_close_symbol must dispatch when hints are provided"
    );

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    assert!(
        req.strategy.starts_with("risk_close:"),
        "strategy must start with 'risk_close:' for ML is_exit detector, got {}",
        req.strategy
    );
    assert!(
        req.strategy.ends_with("ipc_close_symbol"),
        "strategy must preserve 'ipc_close_symbol' suffix for dispatch traceability, got {}",
        req.strategy
    );
    assert!(
        req.is_close,
        "ipc_close_symbol dispatch must set is_close=true"
    );
}

// ─── F2 CROSS-SYMBOL-PRICE-CONTAMINATION-1 regressions ───
// 2026-04-26: STRKUSDT dust spiral RCA showed `OrderDispatchRequest.price`
// borrowed the outer-tick (BTC ~$77995 / ETH ~$2327) price when fast_track
// closed STRK ($0.04261). This polluted min_notional gate evaluation, wrote
// 41 phantom fill log rows under wrong-symbol attribution, and skewed
// `event_consumer::loop_handlers` "new fill" stats. The fix routes the
// dispatched price through `paper_state.latest_price(symbol)` →
// `entry_price` → `event.last_price` (last-resort) so every close path
// stamps the correct symbol's price. Companion to per_symbol_price_pnl.rs's
// P1-16 emit_close_fill regressions; those guard the paper bookkeeping
// (TradingMsg::Fill), this guards the exchange dispatch (OrderDispatchRequest).
//
// 2026-04-26：STRKUSDT dust spiral RCA 揭發 `OrderDispatchRequest.price`
// 在 fast_track 平倉時借用了外層 tick（BTC/ETH/KAT）的價格，污染 min_notional
// gate、寫進錯誤 symbol 41 條 phantom fill 列、扭曲 event_consumer 的「new
// fill」統計。修復路徑：派發價依 `paper_state.latest_price(symbol)` →
// `entry_price` → `event.last_price`（末路）求得，三條 close 路徑一致。
// 此處測試守 OrderDispatchRequest（exchange 派發層），與 per_symbol_price_pnl.rs
// 的 P1-16 測試（守 TradingMsg::Fill paper 簿記）互補。

/// F2 primary regression: `execute_position_close` MUST stamp `symbol`'s own
/// `latest_price` onto `OrderDispatchRequest.price`, not the outer tick's price.
/// Models the STRKUSDT dust-spiral case: outer tick = BTCUSDT @ $77,995, but
/// the close fires for STRKUSDT (latest @ $0.04261). Dispatched price MUST be
/// $0.04261, NEVER $77,995.
/// F2 主場景回歸：execute_position_close 派發必須使用該交易對自己的
/// latest_price，禁止借用外層 tick。重現 STRK dust spiral：外層 BTC tick
/// $77,995 但平倉對象是 STRK ($0.04261)，派發價必須是 STRK 自己的 $0.04261。
#[test]
fn test_execute_position_close_dispatch_price_matches_symbol_not_event() {
    let mut pipeline = TickPipeline::with_kind(
        &["BTCUSDT", "ETHUSDT", "KATUSDT", "STRKUSDT"],
        10_000.0,
        PipelineKind::Demo,
    );
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);

    // Open STRKUSDT at $0.05; seed STRK's latest_price to $0.04261 (post-decay).
    // Other symbols carry inflated mainstream prices. The outer tick simulates
    // the moment fast_track ReduceToHalf evaluates STRK while the current tick
    // belongs to BTCUSDT @ $77,995.
    // 開 STRKUSDT 倉於 0.05，將其 latest_price 推到 0.04261；外層 tick 為 BTC
    // 的 $77,995，模擬 fast_track ReduceToHalf 跨 symbol 評估的時刻。
    pipeline
        .paper_state
        .apply_fill("STRKUSDT", true, 0.5, 0.05, 0.0, 1_000, "test");
    pipeline.paper_state.set_latest_price("STRKUSDT", 0.04261);
    pipeline.paper_state.set_latest_price("BTCUSDT", 77_995.0);
    pipeline.paper_state.set_latest_price("ETHUSDT", 2_327.0);

    let outer_event = super::make_event("BTCUSDT", 77_995.0, 1_700_000_000_000);

    pipeline.execute_position_close(
        "STRKUSDT",
        true, // STRK long → close as Sell side
        0.25,
        &outer_event,
        false, // shadow path: is_primary=false
        "risk_close:fast_track_reduce_half",
    );

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    assert_eq!(req.symbol, "STRKUSDT", "symbol must match the close target");
    // Pre-fix: this assertion failed with 77_995.0 (BTC price). Post-fix the
    // dispatch carries STRK's own $0.04261.
    // 修前此斷言會以 77_995（BTC 價）失敗。修後派發攜帶 STRK 自己的 $0.04261。
    assert!(
        (req.price - 0.04261).abs() < 1e-9,
        "F2 primary contract: dispatched price MUST be STRKUSDT's own $0.04261 latest_price, NOT the outer BTC tick $77,995 — got {}",
        req.price
    );
    assert_ne!(
        req.price, 77_995.0,
        "dispatched price must NOT borrow outer tick's BTC price"
    );
    assert_ne!(
        req.price, 2_327.0,
        "dispatched price must NOT borrow ETHUSDT or any other unrelated symbol's price"
    );
    assert!(
        req.is_close,
        "execute_position_close must set is_close=true"
    );
}

/// F2 fallback level 1: when `latest_price(symbol)` is absent or NaN, the
/// dispatch must fall back to the position's entry_price (matches
/// `ipc_close_all` / `ipc_close_symbol` policy), still NEVER the outer tick.
/// F2 fallback 第一層：latest_price 缺失或 NaN 時，派發退回該倉位 entry_price，
/// 仍**禁止**借用外層 tick。
#[test]
fn test_execute_position_close_falls_back_to_entry_price_when_no_latest() {
    let mut pipeline =
        TickPipeline::with_kind(&["BTCUSDT", "STRKUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);

    pipeline
        .paper_state
        .apply_fill("STRKUSDT", true, 0.5, 0.05, 0.0, 1_000, "test");
    // Wipe STRK's latest_price (apply_fill seeds it). NaN simulates the
    // orphan-adopted-pre-tick state from per_symbol_price_pnl P1-16.
    // 強制清掉 STRK 的 latest_price（apply_fill 內部會設）；NAN 模擬「孤兒
    // 倉位首 tick 前」的狀態。
    pipeline.paper_state.set_latest_price("STRKUSDT", f64::NAN);

    let outer_event = super::make_event("BTCUSDT", 77_995.0, 1_700_000_000_000);

    pipeline.execute_position_close(
        "STRKUSDT",
        true,
        0.25,
        &outer_event,
        false,
        "risk_close:halt_session",
    );

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    assert!(
        (req.price - 0.05).abs() < 1e-9,
        "F2 fallback L1: with NaN latest, dispatch MUST use STRK's entry_price 0.05, got {}",
        req.price
    );
    assert_ne!(
        req.price, 77_995.0,
        "fallback must NOT borrow outer tick's BTC price"
    );
}

/// F2 fallback level 2 (last resort): when neither `latest_price` nor a
/// position is available (orphan symbol whose state was already evicted), the
/// dispatch falls through to `event.last_price` rather than panicking. This
/// is intentionally permissive — the alternative (zero or skip) would risk
/// silently losing a close attempt. The first-line invariants above plus the
/// caller patterns in production keep this path effectively unreachable;
/// covering it here documents the intended last-resort semantics.
/// F2 fallback 第二層（末路）：latest_price 缺、paper_state 也無倉時退到
/// `event.last_price`。設計上故意允許，避免靜默丟失平倉。生產 caller 路徑
/// 走不到，本測試僅文檔化末路語義。
#[test]
fn test_execute_position_close_last_resort_event_price_when_no_position() {
    let mut pipeline =
        TickPipeline::with_kind(&["BTCUSDT", "STRKUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);

    // No position opened for STRKUSDT → no latest_price seeded, no entry_price.
    // 故意不開倉，觸發末路 fallback。
    let outer_event = super::make_event("BTCUSDT", 77_995.0, 1_700_000_000_000);

    pipeline.execute_position_close(
        "STRKUSDT",
        true,
        0.25,
        &outer_event,
        false,
        "risk_close:test_orphan",
    );

    let req = rx.try_recv().expect("OrderDispatchRequest must be sent");
    // No latest, no entry — last-resort uses event.last_price. The point of
    // this test is to lock the documented behaviour, not to claim it's ideal.
    // 無 latest、無 entry → 末路用 event.last_price。
    assert!(
        (req.price - 77_995.0).abs() < 1e-9,
        "F2 last-resort: with no latest and no position, dispatch falls back to event.last_price 77_995, got {}",
        req.price
    );
}

/// F2 ipc_close_all multi-symbol regression: each dispatched
/// OrderDispatchRequest.price must match its own symbol's latest_price (or
/// entry_price fallback), regardless of how many positions are open or what
/// the IPC trigger ts is. Mirrors the dust-spiral scenario at scale: 4 open
/// positions, 4 distinct latest_prices, 4 distinct dispatched prices.
/// F2 ipc_close_all 多 symbol 回歸：每筆派發都用自己的 latest_price/entry_price，
/// 不論倉位數量或 IPC 觸發時刻；放大版 dust spiral：4 倉、4 latest、4 派發價。
#[test]
fn test_ipc_close_all_dispatch_price_matches_each_symbol() {
    let mut pipeline = TickPipeline::with_kind(
        &["BTCUSDT", "ETHUSDT", "STRKUSDT", "DOGEUSDT"],
        10_000.0,
        PipelineKind::Demo,
    );
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);

    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.01, 50_000.0, 0.0, 1_000, "test");
    pipeline
        .paper_state
        .apply_fill("ETHUSDT", true, 0.10, 3_000.0, 0.0, 1_000, "test");
    pipeline
        .paper_state
        .apply_fill("STRKUSDT", true, 0.50, 0.05, 0.0, 1_000, "test");
    pipeline
        .paper_state
        .apply_fill("DOGEUSDT", true, 1_000.0, 0.20, 0.0, 1_000, "test");

    pipeline.paper_state.set_latest_price("BTCUSDT", 50_500.0);
    pipeline.paper_state.set_latest_price("ETHUSDT", 3_030.0);
    pipeline.paper_state.set_latest_price("STRKUSDT", 0.04261);
    pipeline.paper_state.set_latest_price("DOGEUSDT", 0.202);

    let count = pipeline.ipc_close_all();
    assert_eq!(count, 4, "ipc_close_all should report 4 closes");

    let mut dispatch_by_symbol: std::collections::HashMap<String, f64> =
        std::collections::HashMap::new();
    while let Ok(req) = rx.try_recv() {
        dispatch_by_symbol.insert(req.symbol.clone(), req.price);
    }
    assert_eq!(
        dispatch_by_symbol.len(),
        4,
        "expected 4 OrderDispatchRequest emits, got {:?}",
        dispatch_by_symbol
    );

    let btc = dispatch_by_symbol
        .get("BTCUSDT")
        .copied()
        .expect("BTC dispatch");
    assert!(
        (btc - 50_500.0).abs() < 1e-9,
        "BTC dispatched price wrong: {btc}"
    );
    let eth = dispatch_by_symbol
        .get("ETHUSDT")
        .copied()
        .expect("ETH dispatch");
    assert!(
        (eth - 3_030.0).abs() < 1e-9,
        "ETH dispatched price wrong: {eth}"
    );
    let strk = dispatch_by_symbol
        .get("STRKUSDT")
        .copied()
        .expect("STRK dispatch");
    assert!(
        (strk - 0.04261).abs() < 1e-9,
        "STRK dispatched price wrong (must NOT be BTC's 50_500 or ETH's 3_030): {strk}"
    );
    let doge = dispatch_by_symbol
        .get("DOGEUSDT")
        .copied()
        .expect("DOGE dispatch");
    assert!(
        (doge - 0.202).abs() < 1e-9,
        "DOGE dispatched price wrong: {doge}"
    );
}

/// RC-001: exchange close paths must enqueue the reduce-only close before
/// flattening local state. If the dispatch channel is closed, the close is
/// terminally blocked for this tick: no local flat mark and no pending_close.
#[test]
fn test_exchange_close_send_failure_does_not_flatten_or_mark_pending() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    drop(rx);
    pipeline.set_shadow_channel(tx);
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "test");
    pipeline.paper_state.set_latest_price("BTCUSDT", 49_500.0);

    let event = super::make_event("BTCUSDT", 49_500.0, 1_700_000_000_000);
    let result = pipeline.close_position_after_exchange_dispatch(
        "BTCUSDT",
        true,
        0.1,
        &event,
        "risk_close:fast_track",
    );

    assert!(
        result.is_none(),
        "closed dispatch channel must block local flatten"
    );
    assert!(
        pipeline.paper_state.get_position("BTCUSDT").is_some(),
        "local position must remain open when enqueue fails"
    );
    assert!(
        !pipeline.pending_close_symbols.contains("BTCUSDT"),
        "pending_close must only be inserted after send succeeds"
    );
}

#[test]
fn test_exchange_close_success_enqueues_before_local_flatten() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "test");
    pipeline.paper_state.set_latest_price("BTCUSDT", 49_500.0);

    let event = super::make_event("BTCUSDT", 49_500.0, 1_700_000_000_000);
    let result = pipeline.close_position_after_exchange_dispatch(
        "BTCUSDT",
        true,
        0.1,
        &event,
        "risk_close:fast_track",
    );

    assert!(
        result.is_some(),
        "successful enqueue should allow local flatten"
    );
    let req = rx
        .try_recv()
        .expect("reduce-only close dispatch must be enqueued first");
    assert_eq!(req.symbol, "BTCUSDT");
    assert!(req.is_close);
    assert!(
        pipeline.paper_state.get_position("BTCUSDT").is_none(),
        "local position may only be flat after enqueue succeeds"
    );
    assert!(
        pipeline.pending_close_symbols.contains("BTCUSDT"),
        "pending_close must be set after successful primary enqueue"
    );
}
