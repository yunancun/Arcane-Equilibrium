// G5-09 sibling: emit_close_fill + apply_confirmed_fill regression tests.
// Covers engine_mode embedding (BUG-1/2/3 + LiveDemo upgrade), entry_context_id
// threading + signal-time linkage (FILL-CONTEXT-LINKAGE-1), exit-feature row
// emission via the WS-confirmed primary path (EXIT-FEATURES-TABLE-1 GAP-1),
// stat increments + recent_fills mirroring + close-fee charging (PNL-FIX-2).
// G5-09 sibling：emit_close_fill 與 apply_confirmed_fill 相關回歸測試。

use super::super::*;

/// 3E-ARCH regression: emit_close_fill must embed `effective_engine_mode()`
/// into fill_id / order_id / context_id so that Paper/Demo/Live records
/// sharing the same trading_tx channel never collide on `ON CONFLICT DO NOTHING`.
/// Locks the fix from commit d670759 (BUG-1/2/3) AND the endpoint-aware tag
/// upgrade: Live+LiveDemo now stamps "live_demo" (not misleading "live") when
/// the pipeline is pointed at api-demo.bybit.com.
/// 3E-ARCH 回歸：emit_close_fill 必須將 effective_engine_mode() 嵌入 fill_id /
/// order_id / context_id。鎖定 commit d670759（BUG-1/2/3）+ endpoint 感知升級
/// （Live+LiveDemo → "live_demo"）。
#[test]
fn test_emit_close_fill_embeds_engine_mode_per_kind() {
    use crate::bybit_rest_client::BybitEnvironment;
    let kinds: [(PipelineKind, Option<BybitEnvironment>, &str); 4] = [
        (PipelineKind::Paper, None, "paper"),
        (PipelineKind::Demo, Some(BybitEnvironment::Demo), "demo"),
        (PipelineKind::Live, Some(BybitEnvironment::Mainnet), "live"),
        (
            PipelineKind::Live,
            Some(BybitEnvironment::LiveDemo),
            "live_demo",
        ),
    ];
    for (kind, env, expected_em) in kinds {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, kind);
        if let Some(e) = env {
            pipeline.set_endpoint_env(e);
        }
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
        pipeline.set_trading_channel(tx);

        // Trigger the risk-close path. Direct call covers fill_id /
        // order_id / context_id / engine_mode embedding all at once.
        // 直接觸發 risk-close 路徑，一次覆蓋四個 ID 欄位。
        pipeline.emit_close_fill(
            "BTCUSDT",
            true,     // is_long
            0.1,      // qty
            50_000.0, // price
            123,      // ts_ms
            0.0,      // realized_pnl
            "risk_close:sl_hit",
            "",   // entry_context_id unused here (test focuses on engine_mode embed)
            None, // EXIT-FEATURES-TABLE-1: no snapshot; exit-feature row skipped (fail-soft)
        );

        let msg = rx
            .try_recv()
            .expect("emit_close_fill must enqueue a Fill message");
        match msg {
            crate::database::TradingMsg::Fill {
                fill_id,
                order_id,
                context_id,
                engine_mode,
                ..
            } => {
                assert_eq!(engine_mode, expected_em, "{:?}: engine_mode tag", kind);
                assert!(
                    fill_id.starts_with(&format!("close-{}-", expected_em)),
                    "{:?}: fill_id={} missing engine_mode",
                    kind,
                    fill_id
                );
                assert!(
                    order_id.starts_with(&format!("close_{}_", expected_em)),
                    "{:?}: order_id={} missing engine_mode",
                    kind,
                    order_id
                );
                assert!(
                    context_id.starts_with(&format!("ctx-{}-", expected_em)),
                    "{:?}: context_id={} missing engine_mode",
                    kind,
                    context_id
                );
            }
            other => panic!("{:?}: expected Fill, got {:?}", kind, other),
        }
    }
}

/// EDGE-P3-1 R2 regression: emit_close_fill must thread the caller-supplied
/// entry_context_id into the Fill row so training can JOIN fills → decision
/// snapshots via the open-time context id. Empty string → NULL at DB layer.
/// EDGE-P3-1 R2 回歸：emit_close_fill 必須將 caller 傳入的 entry_context_id
/// 寫入 Fill，使訓練端可用開倉時的 context id JOIN fills↔決策快照；空字串在 DB 層為 NULL。
#[test]
fn test_emit_close_fill_threads_entry_context_id() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
    pipeline.set_trading_channel(tx);

    pipeline.emit_close_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        999,
        25.0,
        "risk_close:test",
        "ctx-entry-xyz-789",
        None,
    );

    let msg = rx.try_recv().expect("Fill must be enqueued");
    match msg {
        crate::database::TradingMsg::Fill {
            entry_context_id, ..
        } => {
            assert_eq!(
                entry_context_id, "ctx-entry-xyz-789",
                "entry_context_id must thread verbatim from caller to Fill row"
            );
        }
        other => panic!("expected Fill, got {:?}", other),
    }
}

/// Empty entry_context_id (open fills, missing context) still produces a
/// valid Fill — DB writer treats empty as NULL to avoid label pollution.
/// 空 entry_context_id（開倉 Fill、或缺失）仍應產生有效 Fill — DB writer 將空視為 NULL 以免污染訓練標籤。
#[test]
fn test_emit_close_fill_accepts_empty_entry_context_id() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
    pipeline.set_trading_channel(tx);

    pipeline.emit_close_fill("BTCUSDT", false, 0.05, 3_000.0, 111, 0.0, "test", "", None);

    let msg = rx.try_recv().expect("Fill must be enqueued");
    match msg {
        crate::database::TradingMsg::Fill {
            entry_context_id, ..
        } => {
            assert_eq!(entry_context_id, "");
        }
        other => panic!("expected Fill, got {:?}", other),
    }
}

/// FILL-CONTEXT-LINKAGE-1 regression (2026-04-19): apply_confirmed_fill must
/// stamp `paper_state.entry_context_id` with the signal-time id threaded
/// through OrderDispatchRequest → PendingOrder — NOT regenerate it with WS
/// exec_ts. Before this fix, `signal_context_id` was recomputed inside
/// apply_confirmed_fill via `make_context_id(em, symbol, ts_ms)` where
/// `ts_ms` was the WS exec timestamp (100-500ms drift vs `event.ts_ms`),
/// producing a different context_id string than the one written to
/// `learning.decision_features.context_id`. Result: `trading.fills.entry_context_id`
/// JOIN to `learning.decision_features.context_id` yielded 0 overlap over
/// 3.36M rows. Locking the signal-time path ensures P1-7 C ML training label
/// backfill actually matches.
/// FILL-CONTEXT-LINKAGE-1 回歸（2026-04-19）：apply_confirmed_fill 必須把
/// OrderDispatchRequest → PendingOrder 傳來的訊號時刻 id 寫入 paper_state，
/// 不再用 WS exec_ts 重算。修前 3.36M rows 的 decision_features 與 3514
/// fills 的 entry_context_id 0 overlap，此測試鎖定訊號時刻 id 寫入路徑。
#[test]
fn apply_confirmed_fill_preserves_signal_context_id() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);

    // Seed a latest price so any resolver that wants one is happy.
    // 注入一個最新價，防止任何需要最新價的路徑卡住。
    let _ = pipeline.on_tick(&super::make_event("BTCUSDT", 100.0, 1_000));

    // Apply an open-side confirmed fill with a deliberately earlier
    // signal-time id (ts=1000) and a LATER exec ts_ms (ts=2000). If the
    // fix holds, paper_state.entry_context_id ends in "-1000" (signal),
    // not "-2000" (exec). A pre-fix pipeline would stamp "-2000".
    // 開倉模擬：訊號 id 指向 ts=1000，但 exec ts=2000；修後應保留 -1000。
    let signal_id = "ctx-demo-BTCUSDT-1000";
    pipeline.apply_confirmed_fill(
        "BTCUSDT",
        true,   // is_long
        1.0,    // qty
        100.0,  // fill_price
        0.1,    // fee
        2_000,  // exec ts_ms (later than signal ts=1000)
        "grid", // strategy
        signal_id,
        "oc_test_1",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    );

    // paper_state must show the signal-time id verbatim — not the exec-time
    // recompute "ctx-demo-BTCUSDT-2000" that the pre-fix code produced.
    // paper_state 必須顯示訊號時刻 id，而非修前用 exec_ts 重算的字串。
    let stamped = pipeline.paper_state.get_entry_context_id("BTCUSDT");
    assert_eq!(
        stamped,
        Some(signal_id),
        "entry_context_id must be the signal-time id threaded through \
         OrderDispatchRequest → PendingOrder, not recomputed from exec_ts"
    );

    // Sanity: the stale exec-time id MUST NOT appear on this symbol — a
    // regression would produce "ctx-demo-BTCUSDT-2000" (the rebuild bug).
    // 防呆：exec-time id 絕不應出現，否則回歸。
    assert_ne!(
        stamped,
        Some("ctx-demo-BTCUSDT-2000"),
        "regression: apply_confirmed_fill recomputed context_id from WS exec_ts"
    );
}

/// FILL-CONTEXT-LINKAGE-1 fallback: when the signal-time id is empty (orphan
/// close, legacy pre-fix shadow channel), apply_confirmed_fill must fall back
/// to the exec-time recompute so callers that can't provide the id still
/// write a non-empty entry_context_id. Mirrors pre-fix behaviour for orphans.
/// FILL-CONTEXT-LINKAGE-1 fallback：呼叫方傳空字串時退回 exec-time 重算，
/// 維持舊孤兒/shadow 行為不回歸。
#[test]
fn apply_confirmed_fill_falls_back_when_signal_id_empty() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
    let _ = pipeline.on_tick(&super::make_event("BTCUSDT", 100.0, 1_000));

    pipeline.apply_confirmed_fill(
        "BTCUSDT",
        true,
        1.0,
        100.0,
        0.1,
        2_000,
        "grid",
        "",
        "oc_test_2",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    );

    // Fallback path recomputes with em="demo", symbol="BTCUSDT", ts_ms=2000.
    // Exec-time recompute 應寫出 ctx-demo-BTCUSDT-2000（fallback 正確）。
    let stamped = pipeline
        .paper_state
        .get_entry_context_id("BTCUSDT")
        .map(|s| s.to_string());
    assert_eq!(stamped.as_deref(), Some("ctx-demo-BTCUSDT-2000"));
}

#[test]
fn apply_confirmed_fill_uses_exchange_exec_id_as_fill_id() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
    pipeline.set_trading_channel(tx);

    pipeline.apply_confirmed_fill(
        "BTCUSDT",
        true,
        1.0,
        100.0,
        0.1,
        2_000,
        "grid",
        "ctx-demo-BTCUSDT-1000",
        "oc_test_exec_id",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        Some("exec-id-123"),
    );

    let msg = rx.try_recv().expect("confirmed fill must be enqueued");
    match msg {
        crate::database::TradingMsg::Fill { fill_id, .. } => {
            assert_eq!(
                fill_id, "bybit-exec-id-123",
                "exchange exec_id must drive fill_id to make replay idempotent"
            );
        }
        _ => panic!("expected Fill message"),
    }
}

/// EXIT-FEATURES-TABLE-1 Phase 1b GAP-1 regression (2026-04-19):
/// `apply_confirmed_fill` (Demo/Live WS-confirmed close primary path) must
/// emit an ExitFeatureRow on every close fill (realized_pnl != 0). Before
/// this fix, only `emit_close_fill`, `process_external_fill`, and
/// `ipc_close_symbol` paper branch emitted rows — the main WS-confirmed
/// path was silently unwired. Once PAPER-DISABLE-1 disabled paper by
/// default, this gap caused ~95% of demo exits to produce no exit feature
/// row (2 vs 89 fills in post-redeploy observation window), which would
/// starve DUAL-TRACK Phase 1b W24 threshold calibration of training data.
/// The fix captures `pre_close_snapshot` BEFORE `apply_fill` and calls
/// `try_emit_exit_feature_row` after the trading_tx Fill emission.
/// EXIT-FEATURES-TABLE-1 Phase 1b GAP-1 回歸（2026-04-19）：
/// apply_confirmed_fill（Demo/Live WS 確認平倉主路徑）平倉時必發送
/// ExitFeatureRow。修前僅 emit_close_fill / process_external_fill /
/// ipc_close_symbol paper 分支接線，WS 主路徑靜默漏寫；PAPER-DISABLE-1
/// 關閉 paper 後，demo 平倉約 95% 未產出 exit feature，將餓死
/// DUAL-TRACK Phase 1b W24 門檻校準。修復 = apply_fill 前快照、trading_tx
/// 後呼叫 try_emit_exit_feature_row。
#[test]
fn apply_confirmed_fill_emits_exit_feature_row_on_close() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    pipeline.intent_processor.set_fee_rate(0.00055);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    pipeline.set_exit_feature_tx(tx);

    // 1) Open long via apply_confirmed_fill (is_long=true buy side). realized_pnl=0,
    //    no exit feature row expected on the open.
    // 開倉（is_long=true），realized_pnl=0，開倉不應送出 exit feature。
    pipeline.apply_confirmed_fill(
        "BTCUSDT",
        true,     // is_long (buy opens long)
        0.1,      // qty
        50_000.0, // fill_price
        2.75,     // fee
        1_000,    // ts_ms (open)
        "ma_crossover",
        "ctx-demo-BTCUSDT-1000",
        "oc_open_1",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    );
    assert!(
        rx.try_recv().is_err(),
        "open fill (realized_pnl=0) must NOT emit exit-feature row"
    );

    // 2) Seed a favorable tick so peak_pnl_pct captures a non-zero high.
    // 注入 +2% 的最佳價，讓 peak_pnl_pct 非零。
    pipeline.paper_state.set_latest_price("BTCUSDT", 51_000.0);
    pipeline.paper_state.update_best_prices_at(1_500);

    // 3) Close at 51000 via apply_confirmed_fill (is_long=false sell side).
    //    realized_pnl = 0.1 * (51000 - 50000) = 100 (long win).
    // 平倉（sell 側），realized_pnl = +100，應送出 exit feature。
    pipeline.apply_confirmed_fill(
        "BTCUSDT",
        false,    // is_long=false (sell closes long)
        0.1,      // qty
        51_000.0, // fill_price
        2.81,     // fee (close)
        2_000,    // ts_ms (close)
        "strategy_close:take_profit",
        "", // close fill: signal id not threaded; exec-time fallback OK
        "oc_close_1",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    );

    let row = rx
        .try_recv()
        .expect("close fill via apply_confirmed_fill MUST emit exit-feature row");
    assert_eq!(row.engine_mode, "demo", "engine_mode must be 'demo'");
    assert_eq!(row.side, 1, "long position close → side=1");
    let rbps = row
        .realized_net_bps
        .expect("realized_net_bps must be Some on a real close");
    assert!(
        rbps > 0.0,
        "long win close must register positive realized_net_bps, got {}",
        rbps
    );
    let peak = row
        .peak_pnl_pct
        .expect("peak_pnl_pct must be Some (captured at the +2% tick)");
    assert!(
        (peak - 2.0).abs() < 0.01,
        "peak_pnl_pct should reflect the +2% favorable tick, got {}",
        peak
    );
}

/// EXIT-FEATURES-TABLE-1 Phase 1b GAP-1 fail-soft: when `exit_feature_tx` is
/// unwired, `apply_confirmed_fill` must NOT panic and must still emit the
/// Fill on `trading_tx`. Trading path survives any label-collection outage.
/// fail-soft：tx 未接線時 apply_confirmed_fill 不 panic，Fill 正常送出。
#[test]
fn apply_confirmed_fill_exit_feature_fail_soft_when_tx_missing() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    pipeline.intent_processor.set_fee_rate(0.00055);
    // Wire trading_tx only — exit_feature_tx deliberately absent.
    // 只接 trading_tx，不接 exit_feature_tx。
    let (ttx, mut trx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(16);
    pipeline.set_trading_channel(ttx);

    pipeline.apply_confirmed_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        2.75,
        1_000,
        "ma_crossover",
        "ctx-demo-BTCUSDT-1000",
        "oc_open_2",
        Some(0.0002),
        Some(50_001.0),
        Some(990),
        Some("bbo_same_side"),
        Some(-0.2),
        Some("taker"),
        Some(10),
        None,
    );
    pipeline.apply_confirmed_fill(
        "BTCUSDT",
        false,
        0.1,
        51_000.0,
        2.81,
        2_000,
        "strategy_close:take_profit",
        "",
        "oc_close_2",
        None,
        None,
        None,
        None,
        None,
        None,
        None,
        None,
    );

    // Both Fills still flow through trading_tx (open + close).
    // 開倉與平倉 Fill 都應正常寫入 trading_tx。
    let open_fill = trx.try_recv().expect("open Fill must be enqueued");
    match open_fill {
        crate::database::TradingMsg::Fill {
            fee_rate,
            reference_price,
            reference_ts_ms,
            reference_source,
            slippage_bps,
            liquidity_role,
            fill_latency_ms,
            ..
        } => {
            assert!((fee_rate - 0.0002).abs() < 1e-12);
            assert_eq!(reference_price, Some(50_001.0));
            assert_eq!(reference_ts_ms, Some(990));
            assert_eq!(reference_source.as_deref(), Some("bbo_same_side"));
            assert_eq!(slippage_bps, Some(-0.2));
            assert_eq!(liquidity_role.as_deref(), Some("taker"));
            assert_eq!(fill_latency_ms, Some(10));
        }
        _ => panic!("open Fill must be enqueued"),
    }
    let close_fill = trx.try_recv().expect("close Fill must be enqueued");
    assert!(matches!(
        close_fill,
        crate::database::TradingMsg::Fill { .. }
    ));
}

#[test]
fn test_dbrun3_close_position_returns_pnl() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    // Open long at 50k, close at 51k → +0.1 * 1000 = +$100 realized
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 0, "test");
    let pnl = p.paper_state.close_position("BTCUSDT", 51_000.0, 1_000);
    assert_eq!(pnl, Some(100.0));
    // Subsequent close on same symbol → None
    let none = p.paper_state.close_position("BTCUSDT", 52_000.0, 2_000);
    assert!(none.is_none());
}

#[test]
fn test_dbrun3_emit_close_fill_increments_stats() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    let before = p.stats.total_fills;
    p.emit_close_fill(
        "BTCUSDT",
        true,
        0.1,
        51_000.0,
        1_000,
        100.0,
        "risk_close:test",
        "",
        None,
    );
    assert_eq!(p.stats.total_fills, before + 1);
}

/// Regression: emit_close_fill must mirror the fill into `recent_fills`
/// so the pipeline_snapshot view surfaces close fills to the GUI.
/// Previously it only incremented stats, causing snapshot `recent_fills`
/// to stay empty while DB accumulated closes every second.
/// 回歸：emit_close_fill 必須把平倉 fill 鏡像到 recent_fills，讓 GUI 快照能看見。
#[test]
fn test_emit_close_fill_pushes_to_recent_fills() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    assert_eq!(p.recent_fills.len(), 0);
    // Close a long position → fill side should be short (is_long = false).
    // 平多倉 → fill 方向為空（is_long = false）。
    p.emit_close_fill(
        "BTCUSDT",
        true,
        0.1,
        51_000.0,
        1_234,
        100.0,
        "stop_trigger:hard_stop",
        "",
        None,
    );
    assert_eq!(p.recent_fills.len(), 1);
    let fill = &p.recent_fills[0];
    assert_eq!(fill.symbol, "BTCUSDT");
    assert_eq!(
        fill.is_long, false,
        "close of long position → short fill side"
    );
    assert_eq!(fill.qty, 0.1);
    assert_eq!(fill.price, 51_000.0);
    assert_eq!(fill.timestamp_ms, 1_234);
    assert_eq!(fill.strategy, "stop_trigger:hard_stop");
    // fee is the computed close fee (qty * price * fee_rate), not the raw 0.
    // fee 是計算出的平倉費，而非原始 0。
    assert!(fill.fee > 0.0, "close fee must be charged, not zero");
}

/// Close of a short position produces a long-side fill in recent_fills.
/// 平空倉 → fill 方向為多。
#[test]
fn test_emit_close_fill_inverts_is_long_for_short_close() {
    let mut p = TickPipeline::new(&["BTCUSDT"]);
    p.emit_close_fill(
        "BTCUSDT",
        false,
        0.05,
        50_000.0,
        2_000,
        -50.0,
        "risk_close:fast_track",
        "",
        None,
    );
    assert_eq!(p.recent_fills.len(), 1);
    assert_eq!(
        p.recent_fills[0].is_long, true,
        "close of short → long fill side"
    );
}

/// PNL-FIX-2: emit_close_fill must (a) charge the close-side taker fee
/// against paper_state.balance / total_fees, AND (b) write that same fee
/// into the DB Fill row. Locks the 2026-04-12 fix where every risk_close
/// row had fee=$0 and the comment lied about "accrued separately".
/// PNL-FIX-2：emit_close_fill 必須對 paper_state 計入平倉費，並寫入 DB 行。
#[test]
fn test_emit_close_fill_charges_real_close_fee() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    // Pin a known taker rate so the math is reproducible (5.5 bps = 0.00055).
    // 鎖定一個已知 taker 費率讓計算可預期。
    pipeline.intent_processor.set_fee_rate(0.00055);

    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
    pipeline.set_trading_channel(tx);

    let bal_before = pipeline.paper_state.balance();
    let fees_before = pipeline.paper_state.total_fees();

    // qty=0.1 @ price=50_000 → notional=5_000 → fee=5_000 × 0.00055 = 2.75
    pipeline.emit_close_fill(
        "BTCUSDT",
        true,
        0.1,
        50_000.0,
        1_000,
        0.0,
        "risk_close:sl_hit",
        "",
        None,
    );

    // (a) paper_state must show the fee charge.
    let bal_after = pipeline.paper_state.balance();
    let fees_after = pipeline.paper_state.total_fees();
    assert!(
        (bal_before - bal_after - 2.75).abs() < 1e-9,
        "balance should drop by close fee 2.75, got drop {}",
        bal_before - bal_after
    );
    assert!(
        (fees_after - fees_before - 2.75).abs() < 1e-9,
        "total_fees should rise by 2.75, got rise {}",
        fees_after - fees_before
    );

    // (b) DB Fill row must carry the real fee value, NOT 0.0.
    let msg = rx
        .try_recv()
        .expect("emit_close_fill must enqueue a Fill message");
    match msg {
        crate::database::TradingMsg::Fill { fee, fee_rate, .. } => {
            assert!(
                (fee - 2.75).abs() < 1e-9,
                "DB fee must equal close fee 2.75, got {fee}"
            );
            assert!(
                (fee_rate - 0.00055).abs() < 1e-9,
                "DB fee_rate must equal taker rate, got {fee_rate}"
            );
        }
        other => panic!("expected Fill, got {other:?}"),
    }
}
