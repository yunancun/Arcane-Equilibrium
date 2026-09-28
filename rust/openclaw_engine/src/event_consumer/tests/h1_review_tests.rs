// Included beside the pending-registration fixtures; exercises real sweep/WS paths.
#[tokio::test]
async fn h1_reprice_cancel_does_not_dispatch_an_extra_taker() {
    use crate::instrument_info::{InstrumentInfoCache, SymbolSpec};
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let cache = InstrumentInfoCache::new();
    cache.cache.write().insert(
        "BTCUSDT".into(),
        SymbolSpec {
            symbol: "BTCUSDT".into(),
            base_currency: "BTC".into(),
            quote_currency: "USDT".into(),
            contract_type: "LinearPerpetual".into(),
            qty_step: 0.001,
            min_qty: 0.001,
            max_qty: 1000.0,
            tick_size: 0.1,
            min_price: 0.1,
            max_price: 1_000_000.0,
            min_notional: 5.0,
            qty_decimals: 3,
            price_decimals: 1,
        },
    );
    pipeline.set_instrument_cache(std::sync::Arc::new(cache));
    let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    seed_long_position(&mut pipeline);
    pipeline
        .paper_state
        .set_latest_bbo("BTCUSDT", 50_000.3, 50_000.5);
    pipeline.paper_state.set_latest_price("BTCUSDT", 50_000.4);
    let mut state = make_loop_state();
    let mut po = close_maker_pending_order("h1-reprice-old");
    po.progress.status = super::super::order_lifecycle::OrderStatus::Working;
    let now = po.sent_ts_ms + 35_000;
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    super::super::loop_tick::sweep_pending_orders(&mut pipeline, &mut state, None, now);
    let replacement = rx.try_recv().expect("sweep queues replacement maker");
    assert_eq!(replacement.time_in_force, Some(TimeInForce::PostOnly));
    // The predecessor must also stay quiet while replacement registration is queued.
    super::super::loop_tick::sweep_pending_orders(&mut pipeline, &mut state, None, now + 60_000);
    assert!(
        rx.try_recv().is_err(),
        "predecessor grace must not dispatch taker"
    );
    assert!(pipeline.has_pending_close("BTCUSDT"));
    let mut successor = close_maker_pending_order(&replacement.order_link_id);
    successor.sent_ts_ms = now;
    state
        .pending_orders
        .insert(replacement.order_link_id.clone(), successor);
    let mut writer = super::make_test_writer();
    handle_exchange_event(
        Some(ExchangeEvent::Fill(h1_exec(
            &po.order_link_id,
            "predecessor-partial",
            "0.01",
            "Sell",
        ))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert!(
        pipeline.has_pending_close("BTCUSDT"),
        "late predecessor fill must preserve replacement guard"
    );
    let mut terminal = terminal_order_update(&po.order_link_id, "Cancelled", "EC_PerCancelRequest");
    terminal.cum_exec_qty = "0.01".into();
    handle_exchange_event(
        Some(ExchangeEvent::OrderUpdate(terminal)),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert!(
        rx.try_recv().is_err(),
        "reprice cancellation must not also dispatch taker"
    );
    assert!(state
        .pending_orders
        .contains_key(&replacement.order_link_id));
    assert!(!state.pending_orders.contains_key(&po.order_link_id));
    assert!(
        pipeline.has_pending_close("BTCUSDT"),
        "successor owns close guard"
    );
}

#[tokio::test]
async fn h1_dcp_reconciliation_resolves_cancel_without_ws_replay() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let mut state = make_loop_state();
    let mut po = baseline_pending_order("market", None);
    po.order_link_id = "h1-dcp-cancel".into();
    pipeline.exchange_submission_guard.track(&po.order_link_id);
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    let response = serde_json::json!({"list":[{
        "orderId":"venue-cancel", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Buy", "orderStatus":"Cancelled", "cumExecQty":"0"
    }]});
    let (reconciler, mut rx) =
        super::super::dcp_reconciliation::DcpReconciler::fixture(vec![response]);
    state.dcp_reconciler = Some(reconciler);
    let mut writer = super::make_test_writer();
    handle_exchange_event(
        Some(ExchangeEvent::DcpTriggered),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert!(pipeline.exchange_submission_guard.blocks_entry());
    let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
        .await
        .unwrap()
        .unwrap();
    handle_exchange_event(Some(event), &mut pipeline, &mut writer, &mut state, None).await;
    assert!(!pipeline.exchange_submission_guard.blocks_entry());
    assert!(state.pending_orders.is_empty());
}

#[tokio::test]
async fn h1_dcp_replays_missing_fills_before_terminal_cleanup() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let mut state = make_loop_state();
    let mut po = baseline_pending_order("market", None);
    po.order_link_id = "h1-dcp-partial".into();
    po.qty = 0.03;
    pipeline.exchange_submission_guard.track(&po.order_link_id);
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    let order = serde_json::json!({"list":[{"orderId":"venue-partial", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Buy", "orderStatus":"Cancelled", "cumExecQty":"0.01"}]});
    let executions = serde_json::json!({"list":[{"execId":"missed", "orderId":"venue-partial", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Buy", "execQty":"0.01", "execPrice":"50000", "execFee":"0.2",
        "execTime":"1700000000100", "execType":"Trade"}],"nextPageCursor":""});
    let (reconciler, mut rx) =
        super::super::dcp_reconciliation::DcpReconciler::fixture(vec![order, executions]);
    state.dcp_reconciler = Some(reconciler);
    let mut writer = super::make_test_writer();
    handle_exchange_event(
        Some(ExchangeEvent::DcpTriggered),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    let fill = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
        .await
        .unwrap()
        .unwrap();
    let ExchangeEvent::Fill(exec) = fill else {
        panic!("fill must precede terminal");
    };
    handle_exchange_event(
        Some(ExchangeEvent::Fill(exec.clone())),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    // The global FIFO may have evicted this execution before a REST/WS overlap.
    state.seen_exec_set.clear();
    handle_exchange_event(
        Some(ExchangeEvent::Fill(exec)),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert!((state.pending_orders[&po.order_link_id].cum_filled_qty - 0.01).abs() < 1e-10);
    let terminal = rx.recv().await.unwrap();
    handle_exchange_event(Some(terminal), &mut pipeline, &mut writer, &mut state, None).await;
    assert!(state.pending_orders.is_empty());
    assert!(!pipeline.exchange_submission_guard.blocks_entry());
    assert!((pipeline.paper_state.get_position("BTCUSDT").unwrap().qty - 0.01).abs() < 1e-10);
    assert_eq!(pipeline.stats.total_fills, 1);
}

#[tokio::test]
async fn h1_dcp_rejects_incomplete_or_mismatched_evidence() {
    let mut po = baseline_pending_order("market", None);
    po.order_link_id = "h1-dcp-negative".into();
    let order = serde_json::json!({"list":[{"orderId":"venue", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Buy", "orderStatus":"Cancelled", "cumExecQty":"0.01"}]});
    let execution = serde_json::json!({"execId":"e", "orderId":"venue", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Buy", "execQty":"0.01", "execPrice":"50000", "execTime":"100", "execType":"Trade"});
    for variant in [
        "wrong_order",
        "wrong_execution",
        "missing_fill",
        "repeated_cursor",
        "nonterminal",
        "filled_zero",
    ] {
        let mut o = order.clone();
        let mut e = execution.clone();
        let mut pages = Vec::new();
        match variant {
            "wrong_order" => o["list"][0]["orderLinkId"] = "different".into(),
            "wrong_execution" => e["orderId"] = "different".into(),
            "missing_fill" => e["execQty"] = "0.005".into(),
            "repeated_cursor" => {
                pages.push(serde_json::json!({"list":[e.clone()], "nextPageCursor":"same"}));
                pages.push(serde_json::json!({"list":[e.clone()], "nextPageCursor":"same"}));
            }
            "nonterminal" => o["list"][0]["orderStatus"] = "New".into(),
            "filled_zero" => {
                o["list"][0]["orderStatus"] = "Filled".into();
                o["list"][0]["cumExecQty"] = "0".into();
            }
            _ => unreachable!(),
        }
        if pages.is_empty() {
            pages.push(serde_json::json!({"list":[e]}));
        }
        let mut responses = vec![o];
        responses.extend(pages);
        let (reconciler, _) = super::super::dcp_reconciliation::DcpReconciler::fixture(responses);
        assert!(
            reconciler.reconcile_fixture(&po).await.is_err(),
            "{variant} must fail closed"
        );
    }
}

#[tokio::test]
async fn h1_dcp_history_pagination_and_replay_dedup() {
    let mut po = baseline_pending_order("market", None);
    po.order_link_id = "h1-dcp-history".into();
    po.cum_filled_qty = 0.01;
    po.progress.applied_execution_ids.insert("known".into());
    let order = serde_json::json!({"list":[{"orderId":"venue", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Buy", "orderStatus":"Cancelled", "cumExecQty":"0.02"}]});
    let fill = |id: &str, time: &str| {
        serde_json::json!({"execId":id, "orderId":"venue",
        "symbol":"BTCUSDT", "side":"Buy", "execQty":"0.01", "execPrice":"50000", "execTime":time, "execType":"Trade"})
    };
    let (reconciler, _) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        serde_json::json!({"list":[]}),
        order,
        serde_json::json!({"list":[fill("missing","200")], "nextPageCursor":"next"}),
        serde_json::json!({"list":[fill("known","100")], "nextPageCursor":""}),
    ]);
    let events = reconciler.reconcile_fixture(&po).await.unwrap();
    assert_eq!(events.len(), 2);
    assert!(
        matches!(&events[0], ExchangeEvent::Fill(e) if e.exec_id == "missing" && e.order_link_id == po.order_link_id)
    );
    assert!(matches!(&events[1], ExchangeEvent::OrderUpdate(o) if o.order_status == "Cancelled"));
}

#[tokio::test]
async fn h1_dcp_failed_reads_are_bounded_and_keep_unknown() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let mut state = make_loop_state();
    let po = baseline_pending_order("market", None);
    pipeline.exchange_submission_guard.track(&po.order_link_id);
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    let (reconciler, mut rx) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![]);
    state.dcp_reconciler = Some(reconciler);
    let mut writer = super::make_test_writer();
    handle_exchange_event(
        Some(ExchangeEvent::DcpTriggered),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    tokio::time::timeout(std::time::Duration::from_secs(3), async {
        while !state.dcp_reconciler.as_ref().unwrap().is_idle() {
            tokio::time::sleep(std::time::Duration::from_millis(25)).await;
        }
    })
    .await
    .unwrap();
    assert!(rx.try_recv().is_err());
    assert_eq!(
        state.pending_orders[&po.order_link_id].progress.status,
        super::super::order_lifecycle::OrderStatus::Unknown
    );
    assert!(pipeline.exchange_submission_guard.blocks_entry());
}
