//! ARCH-RC1 1C-3-F: SubmitOrder e2e tests via handle_paper_command + oneshot.
//! Drives the new external paper-side submit RPC end-to-end so the rewired
//! shadow_decision_builder + any future Layer 2 / operator entry has CI cover.
//! ARCH-RC1 1C-3-F：SubmitOrder e2e 測試（取代 paper_trading_engine.py 後的入口）。

use super::{
    authorize, make_test_pipeline, make_test_writer, run_submit, seed_indicators_with_atr,
};

#[test]
fn test_f_submit_order_happy_path() {
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    // PH5-WIRE-0: ATR=2000 to clear cost_gate with 0.2 cold-start dampening.
    // qty=0.001, notional=$50, k=2.0, fee=$0.055, need EV=2000×conf×0.001×0.2=$0.4×conf > $0.11 ✓
    seed_indicators_with_atr(&mut p, "BTCUSDT", 2000.0);
    // Authorise governance — process() requires it.
    // 授權治理層 — process() 第一道 gate 即檢查。
    authorize(&mut p);

    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Buy", 0.001);
    assert!(result.is_ok(), "submit failed: {result:?}");
    let envelope: serde_json::Value =
        serde_json::from_str(&result.unwrap()).expect("envelope is json");
    assert!(envelope["order_id"]
        .as_str()
        .unwrap()
        .starts_with("ext-BTCUSDT-"));
    assert!(envelope["fill_qty"].as_f64().unwrap() > 0.0);
    assert!(envelope["fill_price"].as_f64().unwrap() > 0.0);
    // Side-effects: position opened + stats incremented.
    // 副作用：倉位已開 + stats 已遞增。
    assert!(p.paper_state.get_position("BTCUSDT").is_some());
    assert_eq!(p.stats.total_fills, 1);
}

#[test]
fn test_f_submit_order_paused_rejected() {
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    seed_indicators_with_atr(&mut p, "BTCUSDT", 250.0);
    authorize(&mut p);
    p.paper_paused = true;

    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Buy", 0.001);
    assert!(result.is_err());
    assert_eq!(result.unwrap_err(), "paper_paused");
    assert!(p.paper_state.get_position("BTCUSDT").is_none());
}

#[test]
fn test_f_submit_order_no_price_rejected() {
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    authorize(&mut p);
    // No latest_price seeded — must reject before touching gates.
    // 未種價 — 必須在 gate 前先拒絕。
    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Buy", 0.001);
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("no latest price"));
}

#[test]
fn test_f_submit_order_rejected_on_live_pipeline() {
    // fail-closed 鎖死：external submit 在真錢 mainnet live 管線必拒。
    // 構造 Live + Mainnet → effective_engine_mode()=="live"；即使價/ATR/授權
    // 齊備（happy-path 條件）仍須在最前 reject，倉位零變動。
    use crate::bybit_rest_client::BybitEnvironment;
    use crate::tick_pipeline::{PipelineKind, TickPipeline};
    let mut p = TickPipeline::with_kind(&["BTCUSDT", "ETHUSDT"], 10_000.0, PipelineKind::Live);
    p.set_endpoint_env(BybitEnvironment::Mainnet);
    assert_eq!(p.effective_engine_mode(), "live");
    let mut w = make_test_writer();
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    seed_indicators_with_atr(&mut p, "BTCUSDT", 2000.0);
    authorize(&mut p);

    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Buy", 0.001);
    assert!(result.is_err());
    assert_eq!(
        result.unwrap_err(),
        "external_submit_blocked_on_live_pipeline"
    );
    // 副作用必須為零：倉位未開、fills 未增。
    assert!(p.paper_state.get_position("BTCUSDT").is_none());
    assert_eq!(p.stats.total_fills, 0);
}

#[test]
fn test_f_submit_order_invalid_side_rejected() {
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    seed_indicators_with_atr(&mut p, "BTCUSDT", 250.0);
    authorize(&mut p);

    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Diagonal", 0.001);
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("invalid side"));
}
