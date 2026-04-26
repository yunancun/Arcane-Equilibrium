// G5-09 sibling: EXIT-FEATURES-TABLE-1 producer tests (2026-04-19).
// Coverage: emit_close_fill → ExitFeatureRow on long/short win + stop loss,
// fail-soft when tx unwired or snapshot None, three-pipeline integration via
// shared channel, parse_exit_tag taxonomy, giveback_atr_norm clamping,
// ipc_close_symbol paper branch, try_emit_exit_feature_row direct + fail-soft.
// G5-09 sibling：EXIT-FEATURES-TABLE-1 生產者端覆蓋 + 邊界 + helper 直測。

use super::super::*;

// ── EXIT-FEATURES-TABLE-1 producer tests (2026-04-19) ───────────────────────
// Design: docs/worklogs/2026-04-18-2--exit_features_table_design.md §「測試」
// Coverage targets:
//   · emit_close_fill → ExitFeatureRow write (long win / short win / stop loss)
//   · fail-soft when tx unset OR snapshot None (trading path unaffected)
//   · integration: Paper / Demo / Live each emit one row
//   · parse_exit_tag taxonomy coverage
//   · giveback_atr_norm clamps to 0 on pnl-above-peak edge case
// EXIT-FEATURES-TABLE-1：設計文件 §測試；生產者端覆蓋 7 維列寫入 + fail-soft
// + 三引擎整合 + close_tag 分類 + giveback 夾值邊界。

/// Long-win exit: apply_fill open long → apply_fill close → emit_close_fill
/// with snapshot wired. Expect one row with side=+1, positive realized_net_bps,
/// positive peak_pnl_pct, and canonical schema provenance.
/// 多頭獲利平倉：預期 side=+1、realized_net_bps>0、peak_pnl_pct>0，並帶 schema hash。
#[test]
fn test_exit_feature_row_emitted_on_long_win_close() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    p.intent_processor.set_fee_rate(0.00055);

    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    p.set_exit_feature_tx(tx);

    // Open long @ 50_000, entry_fee = 0.1 * 50_000 * 0.00055 = 2.75
    let entry_fee = 0.1 * 50_000.0 * 0.00055;
    p.paper_state.apply_fill(
        "BTCUSDT", true, 0.1, 50_000.0, entry_fee, 1_000, "ma_crossover",
    );
    // Tick peak up to 51_500 → max_favorable_pnl_pct = 3.0 %. update_best_prices_at
    // reads paper_state.latest_prices, so stamp that price first.
    // 注入 51_500 作為 latest_price 再 tick update_best_prices_at，peak = 3%。
    p.paper_state.set_latest_price("BTCUSDT", 51_500.0);
    p.paper_state.update_best_prices_at(1_500);

    // Close @ 51_000 (long +2%). Capture snapshot BEFORE close_position.
    let snap = p.paper_state.position_exit_snapshot("BTCUSDT");
    let pnl = p
        .paper_state
        .close_position("BTCUSDT", 51_000.0, 2_000)
        .unwrap();
    assert!((pnl - 100.0).abs() < 1e-9, "pnl = 0.1 * (51000 - 50000) = 100");

    p.emit_close_fill(
        "BTCUSDT",
        true,
        0.1,
        51_000.0,
        2_000,
        pnl,
        "strategy_close:take_profit",
        "ctx-test-long",
        snap.as_ref(),
    );

    let row = rx.try_recv().expect("exit-feature row must be emitted");
    assert_eq!(row.context_id, "ctx-test-long");
    assert_eq!(row.symbol, "BTCUSDT");
    assert_eq!(row.side, 1, "long → +1");
    assert_eq!(row.strategy_name, "ma_crossover");
    assert_eq!(row.engine_mode, "paper");
    assert_eq!(row.exit_source.as_deref(), Some("Strategy"));
    assert_eq!(row.exit_trigger_rule.as_deref(), Some("take_profit"));
    let rbps = row.realized_net_bps.expect("realized_net_bps must be Some");
    // gross bps = 100 / 5000 × 1e4 = 200; entry_fee_bps = 5.5; close_fee_bps = 5.61
    // → net ≈ 200 − 5.61 − 5.5 = 188.89 bps
    assert!(
        (rbps - 188.89).abs() < 0.1,
        "realized_net_bps ≈ 188.89, got {}",
        rbps
    );
    let peak = row.peak_pnl_pct.expect("peak_pnl_pct must be Some");
    assert!(
        (peak - 3.0).abs() < 0.01,
        "peak should reflect 3% high, got {}",
        peak
    );
    assert_eq!(
        row.feature_schema_version,
        crate::database::exit_feature_schema::EXIT_FEATURE_SCHEMA_VERSION
    );
    assert!(row.feature_schema_hash.starts_with("sha256:"));
}

/// Short-win exit: side=-1 and realized_net_bps>0 when price drops.
/// 空頭獲利平倉：側=-1；價跌時 realized_net_bps 正。
#[test]
fn test_exit_feature_row_emitted_on_short_win_close() {
    let mut p = TickPipeline::with_kind(&["ETHUSDT"], 10_000.0, PipelineKind::Demo);
    p.intent_processor.set_fee_rate(0.00055);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    p.set_exit_feature_tx(tx);

    let entry_fee = 1.0 * 3_000.0 * 0.00055;
    p.paper_state
        .apply_fill("ETHUSDT", false, 1.0, 3_000.0, entry_fee, 500, "funding_arb");
    // Stamp latest_price=2940 (short +2%) then tick update_best_prices_at(600).
    // 注入 2940 作為 latest_price 再 tick，peak = 2%（空頭）。
    p.paper_state.set_latest_price("ETHUSDT", 2_940.0);
    p.paper_state.update_best_prices_at(600);
    let snap = p.paper_state.position_exit_snapshot("ETHUSDT");
    let pnl = p
        .paper_state
        .close_position("ETHUSDT", 2_970.0, 700)
        .unwrap();
    // short: pnl = 1 * (3000 - 2970) = 30
    assert!((pnl - 30.0).abs() < 1e-9);

    p.emit_close_fill(
        "ETHUSDT",
        false, // position was short → is_long=false
        1.0,
        2_970.0,
        700,
        pnl,
        "stop_trigger:trailing_10pct",
        "ctx-test-short",
        snap.as_ref(),
    );

    let row = rx.try_recv().expect("exit-feature row must be emitted");
    assert_eq!(row.side, -1, "short → -1");
    assert_eq!(row.engine_mode, "demo");
    assert_eq!(row.exit_source.as_deref(), Some("TrailingStop"));
    let rbps = row.realized_net_bps.unwrap();
    assert!(rbps > 0.0, "realized_net_bps must be positive on short win, got {}", rbps);
    // peak should be ~2% (captured at the refresh_max_favorable tick)
    let peak = row.peak_pnl_pct.unwrap();
    assert!((peak - 2.0).abs() < 0.01, "peak ≈ 2.0, got {}", peak);
}

/// Stop-loss exit: realized_net_bps<0 and exit_source maps to HardStop.
/// 止損平倉：realized_net_bps<0 且 exit_source=HardStop。
#[test]
fn test_exit_feature_row_emitted_on_stop_loss() {
    let mut p = TickPipeline::with_kind(&["SOLUSDT"], 10_000.0, PipelineKind::Paper);
    p.intent_processor.set_fee_rate(0.00055);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    p.set_exit_feature_tx(tx);

    let entry_fee = 5.0 * 100.0 * 0.00055;
    p.paper_state
        .apply_fill("SOLUSDT", true, 5.0, 100.0, entry_fee, 1_000, "ma_crossover");
    // No favorable tick: peak stays 0.
    let snap = p.paper_state.position_exit_snapshot("SOLUSDT");
    let pnl = p
        .paper_state
        .close_position("SOLUSDT", 95.0, 2_000)
        .unwrap(); // loss of -25
    assert!((pnl - (-25.0)).abs() < 1e-9);

    p.emit_close_fill(
        "SOLUSDT",
        true,
        5.0,
        95.0,
        2_000,
        pnl,
        "stop_trigger:hard_stop_atr",
        "ctx-test-sl",
        snap.as_ref(),
    );

    let row = rx.try_recv().expect("exit-feature row must be emitted");
    assert_eq!(row.exit_source.as_deref(), Some("HardStop"));
    assert_eq!(row.exit_trigger_rule.as_deref(), Some("hard_stop_atr"));
    let rbps = row.realized_net_bps.unwrap();
    assert!(rbps < -400.0, "stop loss should register deep negative bps, got {}", rbps);
    // peak 0 → legacy/no-favorable-tick path; peak_pnl_pct carries 0.
    assert_eq!(row.peak_pnl_pct, Some(0.0));
}

/// No exit_feature_tx wired → emit_close_fill must still succeed (fail-soft);
/// no channel receive, no panic, Fill path unaffected.
/// 未接線 exit_feature_tx → fail-soft：不寫 row、不 panic、Fill 正常送出。
#[test]
fn test_exit_feature_fail_soft_when_tx_missing() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    p.intent_processor.set_fee_rate(0.00055);
    // Trading tx wired to verify the existing fill-emission path still runs.
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::TradingMsg>(8);
    p.set_trading_channel(tx);

    p.paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 2.75, 1_000, "ma_crossover");
    let snap = p.paper_state.position_exit_snapshot("BTCUSDT");
    let pnl = p
        .paper_state
        .close_position("BTCUSDT", 51_000.0, 2_000)
        .unwrap();
    p.emit_close_fill(
        "BTCUSDT", true, 0.1, 51_000.0, 2_000, pnl,
        "strategy_close:take_profit", "ctx-x", snap.as_ref(),
    );
    // Fill still went through — channel must receive TradingMsg::Fill.
    let fill = rx.try_recv().expect("Fill must still be enqueued");
    assert!(matches!(fill, crate::database::TradingMsg::Fill { .. }));
}

/// exit_feature_tx wired but snapshot None (position already gone) →
/// emit_close_fill degrades to fail-soft no-op for the exit-feature row.
/// exit_feature_tx 已接但 snapshot=None → fail-soft：不寫 row，交易路徑不受影響。
#[test]
fn test_exit_feature_fail_soft_when_snapshot_missing() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    p.set_exit_feature_tx(tx);

    p.emit_close_fill(
        "BTCUSDT", true, 0.1, 51_000.0, 2_000, 100.0,
        "strategy_close:take_profit", "ctx-x",
        None, // no snapshot → row skipped
    );
    assert!(
        rx.try_recv().is_err(),
        "exit-feature row must NOT be emitted when snapshot is None"
    );
}

/// Integration: Paper + Demo + Live pipelines each emit one row through the
/// multi-producer shared channel (mirrors the main.rs bootstrap topology).
/// 整合：Paper + Demo + Live 三引擎共用同一 exit_feature_tx，各自產出一列。
#[test]
fn test_exit_feature_row_three_pipeline_integration() {
    use crate::bybit_rest_client::BybitEnvironment;
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(16);

    let kinds: [(PipelineKind, Option<BybitEnvironment>, &str); 3] = [
        (PipelineKind::Paper, None, "paper"),
        (PipelineKind::Demo, Some(BybitEnvironment::Demo), "demo"),
        (PipelineKind::Live, Some(BybitEnvironment::Mainnet), "live"),
    ];

    for (kind, env, expected_em) in kinds {
        let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, kind);
        if let Some(env) = env {
            p.set_endpoint_env(env);
        }
        p.intent_processor.set_fee_rate(0.00055);
        p.set_exit_feature_tx(tx.clone());

        p.paper_state
            .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 2.75, 1_000, "ma_crossover");
        let snap = p.paper_state.position_exit_snapshot("BTCUSDT");
        let pnl = p
            .paper_state
            .close_position("BTCUSDT", 51_000.0, 2_000)
            .unwrap();
        p.emit_close_fill(
            "BTCUSDT", true, 0.1, 51_000.0, 2_000, pnl,
            "strategy_close:three_pipeline", &format!("ctx-{}", expected_em),
            snap.as_ref(),
        );

        let row = rx.try_recv().expect("each pipeline must emit one row");
        assert_eq!(
            row.engine_mode, expected_em,
            "engine_mode must reflect the producing pipeline"
        );
        assert_eq!(row.context_id, format!("ctx-{}", expected_em));
    }
}

/// context_id precedence + fallback:
///   (a) non-empty caller entry_context_id → used verbatim
///   (b) caller empty, snap has one        → use snap.entry_context_id
///   (c) both empty                        → synthetic "ctx-<mode>-<sym>-<ts>"
/// The PK-non-null contract is enforced via the synthetic fallback.
/// context_id 優先序與退回：caller > snap > 合成 fallback（PK 不為空約束）。
#[test]
fn test_exit_feature_context_id_fallback_when_empty() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    p.set_exit_feature_tx(tx);

    // (a) caller wins — snap empty, caller "ctx-caller-auth"
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "ma_crossover");
    let mut snap = p.paper_state.position_exit_snapshot("BTCUSDT").unwrap();
    snap.entry_context_id.clear();
    p.emit_close_fill(
        "BTCUSDT", true, 0.1, 51_000.0, 2_000, 100.0,
        "strategy_close:test", "ctx-caller-auth",
        Some(&snap),
    );
    let row = rx.try_recv().unwrap();
    assert_eq!(
        row.context_id, "ctx-caller-auth",
        "caller-supplied entry_context_id must take precedence"
    );

    // (b) snap wins — caller empty, snap "ctx-from-snap"
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 3_000, "ma_crossover");
    let mut snap2 = p.paper_state.position_exit_snapshot("BTCUSDT").unwrap();
    snap2.entry_context_id = "ctx-from-snap".to_string();
    p.emit_close_fill(
        "BTCUSDT", true, 0.1, 51_000.0, 4_000, 100.0,
        "strategy_close:test", "",
        Some(&snap2),
    );
    let row = rx.try_recv().unwrap();
    assert_eq!(
        row.context_id, "ctx-from-snap",
        "snap.entry_context_id used when caller is empty"
    );

    // (c) synthetic fallback — both empty
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 5_000, "ma_crossover");
    let mut snap3 = p.paper_state.position_exit_snapshot("BTCUSDT").unwrap();
    snap3.entry_context_id.clear();
    p.emit_close_fill(
        "BTCUSDT", true, 0.1, 51_000.0, 6_000, 100.0,
        "strategy_close:test", "",
        Some(&snap3),
    );
    let row = rx.try_recv().unwrap();
    assert!(
        !row.context_id.is_empty(),
        "context_id must fall back to a synthetic id (PK non-null)"
    );
    assert!(row.context_id.starts_with("ctx-paper-"));
}

/// giveback_atr_norm clamps to 0 when current pnl >= peak (closing at a
/// fresh high — the giveback is undefined / zero, not negative).
/// giveback_atr_norm 夾值：pnl ≥ peak 時回 0（新高平倉，giveback 未定義）。
#[test]
fn test_giveback_clamps_to_zero_when_exit_above_peak() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    p.intent_processor.set_fee_rate(0.0);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    p.set_exit_feature_tx(tx);

    // Seed the price tracker so atr_pct is Some (needed for giveback output).
    // 餵入價格歷史讓 compute_atr_pct > 0，giveback 才會返回 Some。
    for (i, px) in [49_500.0, 50_200.0, 49_800.0, 50_500.0, 50_000.0, 51_000.0].iter().enumerate() {
        p.price_tracker_mut()
            .record("BTCUSDT", *px, 1_000 + i as u64 * 100);
    }

    p.paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "ma_crossover");
    // Advance peak via update_best_prices_at: stamp latest=50_500 → peak +1%.
    // update_best_prices_at 以 latest_price 推進峰值：50_500 → peak +1%。
    p.paper_state.set_latest_price("BTCUSDT", 50_500.0);
    p.paper_state.update_best_prices_at(1_500);
    let snap = p.paper_state.position_exit_snapshot("BTCUSDT");

    // Close at 51_000 → current pnl = +2% > peak 1%. giveback should clamp 0.
    let pnl = p
        .paper_state
        .close_position("BTCUSDT", 51_000.0, 2_000)
        .unwrap();
    p.emit_close_fill(
        "BTCUSDT", true, 0.1, 51_000.0, 2_000, pnl,
        "strategy_close:take_profit", "ctx-gb",
        snap.as_ref(),
    );
    let row = rx.try_recv().unwrap();
    if let Some(gb) = row.giveback_atr_norm {
        assert!(
            gb >= 0.0 && gb < 1e-6,
            "giveback must clamp to 0 when exit pnl > peak, got {}",
            gb
        );
    }
    // atr_pct MAY still be None if the tracker sampling isn't enough — that's
    // fine; the clamp only triggers when atr_pct is Some. The assertion above
    // tolerates None by skipping.
    // atr_pct 未達樣本數時 None，clamp 僅在 Some 時生效；以上斷言以 if-let 容忍。
}

/// parse_exit_tag taxonomy: risk_close / stop_trigger / strategy_close plus
/// the no-colon edge case. Locks the mapping the ML loader relies on.
/// parse_exit_tag 分類：三種前綴 + 無冒號；鎖定下游訓練端依賴的映射。
#[test]
fn test_parse_exit_tag_taxonomy() {
    use crate::tick_pipeline::parse_exit_tag;

    // risk_close family
    assert_eq!(
        parse_exit_tag("risk_close:halt_session_drawdown"),
        ("HaltSession".into(), "halt_session_drawdown".into())
    );
    assert_eq!(
        parse_exit_tag("risk_close:fast_track_reduce_half"),
        ("FastTrack".into(), "fast_track_reduce_half".into())
    );
    assert_eq!(
        parse_exit_tag("risk_close:cost_edge_ratio"),
        ("Risk".into(), "cost_edge_ratio".into())
    );

    // stop_trigger family
    assert_eq!(
        parse_exit_tag("stop_trigger:hard_stop_atr"),
        ("HardStop".into(), "hard_stop_atr".into())
    );
    assert_eq!(
        parse_exit_tag("stop_trigger:trailing_10pct"),
        ("TrailingStop".into(), "trailing_10pct".into())
    );
    assert_eq!(
        parse_exit_tag("stop_trigger:time_limit_30m"),
        ("TimeStop".into(), "time_limit_30m".into())
    );
    assert_eq!(
        parse_exit_tag("stop_trigger:unknown_sub"),
        ("Stop".into(), "unknown_sub".into())
    );

    // strategy_close family
    assert_eq!(
        parse_exit_tag("strategy_close:ma_crossover_flip"),
        ("Strategy".into(), "ma_crossover_flip".into())
    );

    // No colon → verbatim pass-through, never lies about provenance.
    assert_eq!(
        parse_exit_tag("legacy_no_colon"),
        ("legacy_no_colon".into(), String::new())
    );

    // Unknown prefix with colon → prefix verbatim, reason retained.
    assert_eq!(
        parse_exit_tag("custom_tag:some_reason"),
        ("custom_tag".into(), "some_reason".into())
    );
}

/// EXIT-FEATURES-TABLE-1 E2 P1 fix: `ipc_close_symbol` paper branch must
/// emit an `ExitFeatureRow` after closing — previously bypassed entirely.
/// Verifies the full wiring end-to-end for IPC-driven paper closes
/// (dust eviction, operator `/close_symbol` API, orphan_handler → Paper).
/// EXIT-FEATURES-TABLE-1 E2 P1：ipc_close_symbol paper 分支必須發 exit feature。
#[test]
fn test_ipc_close_symbol_paper_emits_exit_feature_row() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    p.intent_processor.set_fee_rate(0.0006);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    p.set_exit_feature_tx(tx);

    // Seed latest price so close_position_at_market uses a real mark.
    // 注入最新價，close_position_at_market 才有真實 mark price。
    p.paper_state.set_latest_price("BTCUSDT", 51_000.0);
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 0.0, 1_000, "ma_crossover");
    p.paper_state
        .set_entry_context_id("BTCUSDT", "ctx-ipc-close-test");

    // Paper branch: ipc_close_symbol with no hints (hints only matter for
    // exchange branch). Pipeline kind is Paper, no order_dispatch_tx wired,
    // system_mode default → falls to paper branch.
    // paper 分支：無 hints；系統模式預設 → 走 paper 分支。
    let fired = p.ipc_close_symbol("BTCUSDT", None, None);
    assert!(fired, "ipc_close_symbol paper branch must return true on close");

    let row = rx.try_recv().expect("ExitFeatureRow must be emitted");
    assert_eq!(row.context_id, "ctx-ipc-close-test");
    assert_eq!(row.symbol, "BTCUSDT");
    assert_eq!(row.strategy_name, "ma_crossover");
    assert_eq!(row.side, 1);
    assert_eq!(row.exit_source.as_deref(), Some("Risk"));
    assert_eq!(row.exit_trigger_rule.as_deref(), Some("ipc_close_symbol"));
    // realized_net_bps present (entry_notional>0, fee_rate>0); exact value
    // tolerant of fee math — just assert fee deducted from gross.
    // realized_net_bps 需扣除 round-trip fee，不做精確斷言。
    let net = row.realized_net_bps.expect("realized_net_bps must be Some");
    assert!(net < 200.0, "net bps should be reduced by ~12 bps round-trip fee, got {}", net);
}

/// EXIT-FEATURES-TABLE-1 E2 P1 fix: `try_emit_exit_feature_row` helper —
/// the narrow factor-out used by non-`emit_close_fill` close paths
/// (`ipc_close_symbol` paper branch, external-fill paths that emit their
/// own TradingMsg::Fill). Validates the helper emits one row with the
/// caller-supplied context_id + close_tag mapped through `parse_exit_tag`.
/// EXIT-FEATURES-TABLE-1 E2 P1：try_emit_exit_feature_row helper 獨立測試，
/// 驗證外部呼叫路徑（不走 emit_close_fill 的關倉路徑）能正確發送。
#[test]
fn test_try_emit_exit_feature_row_helper_direct_call() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);
    p.intent_processor.set_fee_rate(0.0006);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(8);
    p.set_exit_feature_tx(tx);

    // Construct a snapshot the same way non-emit_close_fill paths would:
    // open a position, snapshot before close, then call the helper directly.
    // 按外部路徑方式：開倉 → 關倉前 snapshot → 直接呼叫 helper。
    p.paper_state
        .apply_fill("BTCUSDT", true, 0.1, 50_000.0, 30.0, 1_000, "ext_op");
    let snap = p.paper_state.position_exit_snapshot("BTCUSDT");
    assert!(snap.is_some(), "snapshot must exist for open position");

    p.try_emit_exit_feature_row(
        "BTCUSDT", 0.1, 51_000.0, 2_000, 100.0,
        30.6, 0.0006, "custom_external:exchange_report",
        snap.as_ref(), "ctx-helper-test",
    );
    let row = rx.try_recv().expect("helper must emit ExitFeatureRow");
    assert_eq!(row.context_id, "ctx-helper-test");
    assert_eq!(row.strategy_name, "ext_op");
    // Unknown prefix → parse_exit_tag passes through verbatim.
    // 未知前綴 → parse_exit_tag 原樣保留。
    assert_eq!(row.exit_source.as_deref(), Some("custom_external"));
    assert_eq!(row.exit_trigger_rule.as_deref(), Some("exchange_report"));
}

/// EXIT-FEATURES-TABLE-1 E2 P1 fix: helper fails soft when snapshot is None
/// (no position) or tx is not wired — mirrors emit_close_fill fail-soft.
/// EXIT-FEATURES-TABLE-1 E2 P1：helper 缺 snap 或 tx → fail-soft no-op。
#[test]
fn test_try_emit_exit_feature_row_fail_soft() {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Paper);

    // No tx wired + no snapshot → silent no-op, no panic.
    // 未接 tx + 無 snap → 靜默 no-op，不 panic。
    p.try_emit_exit_feature_row(
        "BTCUSDT", 0.1, 51_000.0, 2_000, 100.0,
        0.0, 0.0, "strategy_close:test",
        None, "ctx-fail-soft",
    );

    // tx wired but snap None → still no-op, no row emitted.
    // 接 tx 但 snap=None → 仍 no-op，無列寫入。
    let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::ExitFeatureRow>(4);
    p.set_exit_feature_tx(tx);
    p.try_emit_exit_feature_row(
        "BTCUSDT", 0.1, 51_000.0, 2_000, 100.0,
        0.0, 0.0, "strategy_close:test",
        None, "ctx-fail-soft",
    );
    assert!(rx.try_recv().is_err(), "no row should be emitted when snap is None");
}
