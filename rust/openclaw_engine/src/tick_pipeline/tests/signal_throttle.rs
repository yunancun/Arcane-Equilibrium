// G5-09 sibling: signal-throttle (DBRUN-1) + DBRUN-2 context counter +
// DBRUN-3 close PnL stat path + position-snapshot pump (GAP-7) +
// strategy Close action paths + snapshot pipeline-kind shape.
// G5-09 sibling：signal throttle、context counter、position snapshot pump、
// strategy close 路徑與 snapshot 形狀測試。

use super::super::*;

#[test]
fn test_position_snapshot_emitted_every_1000_ticks() {
    // GAP-7 regression: PositionSnapshot must be emitted every 1000 ticks
    // for every open paper position when trading_tx is wired.
    // GAP-7 回歸：掛接 trading_tx 時每 1000 ticks 為每個持倉發射快照。
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8192);
    pipeline.set_trading_channel(tx);
    // Open a paper long position directly.
    // 直接建立紙盤多單持倉。
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 0, "test");
    // Pump exactly 1000 ticks. total_ticks becomes 1000 -> snapshot.
    // 打 1000 tick，total_ticks 達到 1000 觸發快照。
    for i in 0..1000 {
        pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, (i + 1) * 60_000));
    }
    // Drain channel; expect at least one PositionSnapshot for BTCUSDT.
    // 抽取通道；至少應有一條 BTCUSDT 的 PositionSnapshot。
    let mut found = false;
    while let Ok(msg) = rx.try_recv() {
        if let crate::database::TradingMsg::PositionSnapshot {
            symbol,
            side,
            qty,
            mark_price,
            unrealized_pnl,
            ..
        } = msg
        {
            if symbol == "BTCUSDT" {
                assert_eq!(side, "long");
                assert!((qty - 0.1).abs() < 1e-9);
                assert!((mark_price - 50_000.0).abs() < 1e-9);
                assert!(unrealized_pnl.abs() < 1e-6);
                found = true;
                break;
            }
        }
    }
    assert!(
        found,
        "expected a PositionSnapshot for BTCUSDT; positions={}",
        pipeline.paper_state.position_count()
    );
}

#[test]
fn test_position_snapshot_noop_without_channel() {
    // Without trading_tx wired, snapshot loop must be a no-op and never panic.
    // 未掛接 trading_tx 時快照循環必須無動作且不 panic。
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", false, 0.2, 50_000.0, 0.0, 0, "test");
    for i in 0..1000 {
        pipeline.on_tick(&super::make_event("BTCUSDT", 49_000.0, (i + 1) * 60_000));
    }
    assert_eq!(pipeline.stats.total_ticks, 1000);
}

#[test]
fn test_dbrun1_first_signal_persisted() {
    use openclaw_core::signals::SignalDirection;
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    assert!(p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
    assert_eq!(p.signals_throttled(), 0);
}

#[test]
fn test_dbrun1_unchanged_signal_throttled_within_heartbeat() {
    use openclaw_core::signals::SignalDirection;
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    p.set_signals_heartbeat_ms(60_000);
    assert!(p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
    // Same direction, +30s → throttled
    assert!(!p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Long, 31_000)));
    assert_eq!(p.signals_throttled(), 1);
}

#[test]
fn test_dbrun1_direction_change_breaks_throttle() {
    use openclaw_core::signals::SignalDirection;
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    p.set_signals_heartbeat_ms(60_000);
    assert!(p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
    // Direction flips → persist immediately even within heartbeat
    assert!(p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Short, 5_000)));
    assert_eq!(p.signals_throttled(), 0);
}

#[test]
fn test_dbrun1_heartbeat_elapsed_persists() {
    use openclaw_core::signals::SignalDirection;
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    p.set_signals_heartbeat_ms(60_000);
    assert!(p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
    // Same direction, 60s later → heartbeat fires
    assert!(p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Long, 61_000)));
    assert_eq!(p.signals_throttled(), 0);
}

#[test]
fn test_dbrun1_disable_throttle() {
    use openclaw_core::signals::SignalDirection;
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    p.set_signals_heartbeat_ms(0);
    // Every call persists, no dedupe state consulted
    for ts in [1, 2, 3, 4, 5] {
        assert!(p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Long, ts)));
    }
    assert_eq!(p.signals_throttled(), 0);
}

#[test]
fn test_dbrun2_context_counter_starts_zero() {
    let p = TickPipeline::new(&["BTCUSDT"]);
    assert_eq!(p.context_throttled(), 0);
    assert_eq!(p.signals_throttled(), 0);
}

#[test]
fn test_dbrun1_per_symbol_strategy_isolation() {
    use openclaw_core::signals::SignalDirection;
    let mut p = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
    p.set_signals_heartbeat_ms(60_000);
    assert!(p.should_persist_signal(&super::make_signal("BTCUSDT", SignalDirection::Long, 1_000)));
    // Different symbol, same strategy → independent key, persists
    assert!(p.should_persist_signal(&super::make_signal("ETHUSDT", SignalDirection::Long, 1_000)));
    assert_eq!(p.signals_throttled(), 0);
}

#[test]
fn test_strategy_close_action_closes_position() {
    // Integration test: open a paper position, then simulate the strategy Close
    // deferred execution path, verify position is closed and fills/stats updated.
    // 集成測試：建立紙盤倉位，模擬策略 Close 延遲執行路徑，驗證倉位已平且成交/統計已更新。
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.grant_paper_auth().unwrap();

    // Open a long position directly via paper_state
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 5.5, 1000, "test");
    assert_eq!(pipeline.paper_state.position_count(), 1);
    let balance_before = pipeline.paper_state.balance();

    // Simulate the deferred close: close_position + record_trade + recent_fills
    // (This is exactly what the deferred close loop does for paper mode.)
    let close_price = 51_000.0;
    let close_ts = 2000_u64;
    let pos = pipeline.paper_state.get_position("BTCUSDT").unwrap();
    let is_long = pos.is_long;
    let qty = pos.qty;
    assert!(is_long);
    assert!((qty - 0.1).abs() < 1e-9);

    let pnl = pipeline
        .paper_state
        .close_position("BTCUSDT", close_price, close_ts);
    assert!(pnl.is_some(), "close_position should return pnl");
    let pnl = pnl.unwrap();
    assert!(
        pnl > 0.0,
        "long closed at higher price should be profitable"
    );

    // Kelly stats update
    pipeline.intent_processor.record_trade("BTCUSDT", pnl);

    // Position should be gone
    assert_eq!(pipeline.paper_state.position_count(), 0);
    assert!(pipeline.paper_state.get_position("BTCUSDT").is_none());

    // Balance should have increased (profit minus fees)
    assert!(pipeline.paper_state.balance() > balance_before);
}

#[test]
fn test_strategy_close_no_position_is_noop() {
    // Close when no position exists must be a safe no-op.
    // 無倉位時 Close 必須安全無動作。
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    let result = pipeline
        .paper_state
        .close_position("BTCUSDT", 50_000.0, 1000);
    assert!(
        result.is_none(),
        "close_position on empty should return None"
    );
    assert_eq!(pipeline.paper_state.position_count(), 0);
}

// ═══════════════════════════════════════════════════════════════
// Phase 3: set_trading_mode state swap tests / 模式切換狀態交換測試
// ═══════════════════════════════════════════════════════════════

// 3E-4: set_trading_mode / add_mode / mode_snapshot tests REMOVED.
// Pipeline identity is now immutable (PipelineKind set at construction).
// Mode state swap tests replaced by per-pipeline independence tests (3E e2e).
// 3E-4：模式切換/添加/快照測試已移除。管線身份不可變。

#[test]
fn test_snapshot_contains_pipeline_kind_mode_snapshot() {
    let pipeline = TickPipeline::with_balance(&["BTCUSDT"], 8_000.0);
    let snap = pipeline.snapshot();
    // mode_snapshots should contain exactly the pipeline's own kind.
    // mode_snapshots 應包含管線自身 kind。
    assert!(snap.mode_snapshots.contains_key("paper"));
    assert_eq!(snap.mode_snapshots.len(), 1);
    assert_eq!(snap.mode_snapshots["paper"].paper_state.balance, 8_000.0);
}
