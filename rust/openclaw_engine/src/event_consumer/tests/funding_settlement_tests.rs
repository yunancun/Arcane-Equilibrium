//! Funding settlement regression tests.
//! 資金費結算回歸測試。

use crate::bybit_private_ws::ExecutionUpdate;
use crate::database::TradingMsg;
use crate::event_consumer::types::ExchangeEvent;
use crate::tick_pipeline::{PipelineKind, TickPipeline};
use tokio::sync::mpsc;

use super::super::loop_handlers::{handle_exchange_event, LoopState};
use super::make_test_writer;

fn make_funding_exec(exec_id: &str, amount: &str) -> ExecutionUpdate {
    ExecutionUpdate {
        exec_id: exec_id.to_string(),
        order_id: String::new(),
        symbol: "BTCUSDT".to_string(),
        side: "Sell".to_string(),
        exec_price: "100.0".to_string(),
        exec_qty: "1.0".to_string(),
        exec_fee: amount.to_string(),
        exec_value: "100.0".to_string(),
        fee_rate: String::new(),
        fee_currency: "USDT".to_string(),
        closed_size: String::new(),
        exec_type: "Funding".to_string(),
        exec_time: "1700000000000".to_string(),
        raw: serde_json::json!({
            "execId": exec_id,
            "execType": "Funding",
            "execFee": amount,
            "feeCurrency": "USDT"
        }),
        ..Default::default()
    }
}

#[tokio::test]
async fn test_funding_execution_emits_settlement_not_unattributed_fill() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
    pipeline
        .paper_state
        .apply_fill("BTCUSDT", false, 1.0, 100.0, 0.0, 1, "funding_arb");
    let mut writer = make_test_writer();
    let mut state = LoopState::new(std::collections::HashSet::new());
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);

    handle_exchange_event(
        Some(ExchangeEvent::Fill(make_funding_exec("fund-1", "1.25"))),
        &mut pipeline,
        &mut writer,
        &mut state,
        Some(&tx),
    )
    .await;

    assert!((pipeline.paper_state.balance() - 1_001.25).abs() < 1e-9);
    assert!((pipeline.paper_state.total_funding_pnl() - 1.25).abs() < 1e-9);
    assert_eq!(pipeline.paper_state.trade_count(), 0);

    match rx.try_recv().expect("funding ledger message") {
        TradingMsg::FundingSettlement {
            settlement_id,
            exec_id,
            symbol,
            amount,
            strategy_name,
            engine_mode,
            ..
        } => {
            assert_eq!(settlement_id, "funding-fund-1");
            assert_eq!(exec_id, "fund-1");
            assert_eq!(symbol, "BTCUSDT");
            assert!((amount - 1.25).abs() < 1e-9);
            assert_eq!(strategy_name, "funding_arb");
            assert_eq!(engine_mode, "demo");
        }
        other => panic!("expected FundingSettlement, got {other:?}"),
    }
    assert!(rx.try_recv().is_err(), "funding must not also emit Fill");
}

#[tokio::test]
async fn test_funding_execution_dedup_uses_exec_id() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Demo);
    let mut writer = make_test_writer();
    let mut state = LoopState::new(std::collections::HashSet::new());
    let (tx, mut rx) = mpsc::channel::<TradingMsg>(8);
    let exec = make_funding_exec("fund-dupe", "-0.50");

    handle_exchange_event(
        Some(ExchangeEvent::Fill(exec.clone())),
        &mut pipeline,
        &mut writer,
        &mut state,
        Some(&tx),
    )
    .await;
    handle_exchange_event(
        Some(ExchangeEvent::Fill(exec)),
        &mut pipeline,
        &mut writer,
        &mut state,
        Some(&tx),
    )
    .await;

    assert!((pipeline.paper_state.balance() - 999.50).abs() < 1e-9);
    assert!((pipeline.paper_state.total_funding_pnl() - (-0.50)).abs() < 1e-9);
    assert!(matches!(
        rx.try_recv().expect("first settlement"),
        TradingMsg::FundingSettlement { .. }
    ));
    assert!(
        rx.try_recv().is_err(),
        "duplicate exec_id must not emit again"
    );
}
