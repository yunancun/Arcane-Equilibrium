// G5-09 sibling: I-08 Dual-Rail Stop tests + execute_position_close /
// ipc_close_symbol dispatch contracts.
// 雙軌止損測試：驗證 broker-side SL 只在 primary exchange mode 開倉時啟用，
// 並測 close 路徑的 strategy 標記契約。

use super::super::*;

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
    assert!(fired, "ipc_close_symbol must dispatch when hints are provided");

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
    assert!(req.is_close, "ipc_close_symbol dispatch must set is_close=true");
}
