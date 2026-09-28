// Included beside the pending-registration fixtures; exercises real sweep/WS paths.
#[tokio::test]
async fn h1_reconciliation_slow_order_does_not_block_another_order() {
    use std::sync::Arc;
    let slow_release = Arc::new(tokio::sync::Notify::new());
    let (started_tx, mut started_rx) = tokio::sync::mpsc::unbounded_channel();
    let release = slow_release.clone();
    let (reconciler, mut rx) = super::super::dcp_reconciliation::DcpReconciler::fixture_with_fetch(
        Arc::new(move |_, params| {
            let id = params
                .iter()
                .find(|(k, _)| k == "orderLinkId")
                .unwrap()
                .1
                .clone();
            let release = release.clone();
            let started = started_tx.clone();
            Box::pin(async move {
                started.send(id.clone()).unwrap();
                if id == "slow" {
                    release.notified().await;
                }
                Ok(
                    serde_json::json!({"list":[{"orderId":format!("venue-{id}"),"orderLinkId":id,"symbol":"BTCUSDT","side":"Buy","orderStatus":"Cancelled","cumExecQty":"0"}]}),
                )
            })
        }),
    );
    let mut slow = baseline_pending_order("market", None);
    slow.order_link_id = "slow".into();
    let mut fast = slow.clone();
    fast.order_link_id = "fast".into();
    reconciler.schedule(&[slow, fast]);
    let _ = tokio::time::timeout(std::time::Duration::from_secs(1), started_rx.recv())
        .await
        .unwrap();
    let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
        .await
        .expect("fast order must reconcile while the first REST read is blocked")
        .unwrap();
    assert!(matches!(event, ExchangeEvent::OrderUpdate(o) if o.order_link_id == "fast"));
    slow_release.notify_one();
    let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
        .await
        .unwrap()
        .unwrap();
    assert!(matches!(event, ExchangeEvent::OrderUpdate(o) if o.order_link_id == "slow"));
}

#[tokio::test]
async fn h1_reconciliation_concurrency_is_bounded_across_schedule_calls() {
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    let release = Arc::new(tokio::sync::Semaphore::new(0));
    let running = Arc::new(AtomicUsize::new(0));
    let maximum = Arc::new(AtomicUsize::new(0));
    let (started_tx, mut started_rx) = tokio::sync::mpsc::unbounded_channel();
    let gate = release.clone();
    let active = running.clone();
    let high = maximum.clone();
    let (reconciler, mut rx) = super::super::dcp_reconciliation::DcpReconciler::fixture_with_fetch(
        Arc::new(move |_, params| {
            let id = params
                .iter()
                .find(|(k, _)| k == "orderLinkId")
                .unwrap()
                .1
                .clone();
            let gate = gate.clone();
            let active = active.clone();
            let high = high.clone();
            let started = started_tx.clone();
            Box::pin(async move {
                let n = active.fetch_add(1, Ordering::SeqCst) + 1;
                high.fetch_max(n, Ordering::SeqCst);
                started.send(id.clone()).unwrap();
                gate.acquire().await.unwrap().forget();
                active.fetch_sub(1, Ordering::SeqCst);
                Ok(
                    serde_json::json!({"list":[{"orderId":format!("venue-{id}"),"orderLinkId":id,"symbol":"BTCUSDT","side":"Buy","orderStatus":"Cancelled","cumExecQty":"0"}]}),
                )
            })
        }),
    );
    let orders: Vec<_> = (0..8)
        .map(|i| {
            let mut po = baseline_pending_order("market", None);
            po.order_link_id = format!("bounded-{i}");
            po
        })
        .collect();
    reconciler.schedule(&orders[..4]);
    reconciler.schedule(&orders); // Repeated IDs must not create duplicate work.
    for _ in 0..4 {
        tokio::time::timeout(std::time::Duration::from_secs(1), started_rx.recv())
            .await
            .expect("four orders should make progress concurrently")
            .unwrap();
    }
    assert!(
        tokio::time::timeout(std::time::Duration::from_millis(50), started_rx.recv())
            .await
            .is_err(),
        "multiple schedule calls must share the four-order cap"
    );
    assert_eq!(maximum.load(Ordering::SeqCst), 4);
    release.add_permits(8);
    let mut completed = std::collections::HashSet::new();
    for _ in 0..8 {
        let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
            .await
            .unwrap()
            .unwrap();
        let ExchangeEvent::OrderUpdate(order) = event else {
            panic!("expected terminal order evidence")
        };
        assert!(
            completed.insert(order.order_link_id),
            "one completion per order"
        );
    }
    assert_eq!(maximum.load(Ordering::SeqCst), 4);
    assert_eq!(running.load(Ordering::SeqCst), 0);
    assert!(reconciler.is_idle());
}

#[tokio::test]
async fn h1_fill_carries_registration_identity_despite_venue_clock_skew() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, mut rx) = tokio::sync::mpsc::channel::<TradingMsg>(8);
    pipeline.set_trading_channel(tx);
    let mut state = make_loop_state();
    let mut po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    po.order_link_id = "h1-clock-skew-fill".into();
    po.sent_ts_ms = 1_700_000_100_000;
    po.qty = 0.03;
    let mut exec = h1_exec(&po.order_link_id, "clock-skew-exec", "0.01", "Buy");
    exec.exec_time = (po.sent_ts_ms - 60_000).to_string();
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    let mut writer = super::make_test_writer();
    handle_exchange_event(
        Some(ExchangeEvent::Fill(exec)),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    let mut second = h1_exec(&po.order_link_id, "clock-skew-exec-2", "0.01", "Buy");
    second.exec_time = (po.sent_ts_ms - 30_000).to_string();
    handle_exchange_event(
        Some(ExchangeEvent::Fill(second)),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    let mut observed = 0;
    while let Ok(msg) = rx.try_recv() {
        if let TradingMsg::Fill { details, ts_ms, .. } = msg {
            assert!(ts_ms < po.sent_ts_ms);
            assert_eq!(
                details
                    .as_ref()
                    .and_then(|d| d["order_registered_ts_ms"].as_u64()),
                Some(po.sent_ts_ms)
            );
            observed += 1;
        }
    }
    assert_eq!(
        observed, 2,
        "both partial fills retain the same registration identity"
    );
    assert_eq!(
        state.pending_orders[&po.order_link_id].sent_ts_ms,
        po.sent_ts_ms
    );
}

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
            pages.push(serde_json::json!({"list":[e], "nextPageCursor":""}));
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

#[tokio::test]
async fn h1_fallback_guard_survives_late_predecessor_fill() {
    for successor_finishes_first in [false, true] {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
        let (tx, mut dispatch_rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
        pipeline.set_shadow_channel(tx);
        seed_long_position(&mut pipeline);
        let mut state = make_loop_state();
        let po = close_maker_pending_order("h1-fallback-predecessor");
        pipeline.exchange_submission_guard.track(&po.order_link_id);
        pipeline.retain_pending_close(&po.symbol);
        state
            .pending_orders
            .insert(po.order_link_id.clone(), po.clone());
        let mut writer = super::make_test_writer();
        handle_exchange_event(
            Some(ExchangeEvent::DcpTriggered),
            &mut pipeline,
            &mut writer,
            &mut state,
            None,
        )
        .await;
        let fallback = dispatch_rx
            .try_recv()
            .expect("DCP queues protective fallback");
        assert_eq!(fallback.order_type, "market");
        let mut successor = close_maker_pending_order(&fallback.order_link_id);
        successor.order_type = "market".into();
        successor.time_in_force = None;
        successor.close_maker_audit = fallback.close_maker_audit.clone();
        pipeline
            .exchange_submission_guard
            .track(&successor.order_link_id);
        state
            .pending_orders
            .insert(successor.order_link_id.clone(), successor.clone());
        if successor_finishes_first {
            handle_exchange_event(
                Some(ExchangeEvent::OrderUpdate(terminal_order_update(
                    &successor.order_link_id,
                    "Cancelled",
                    "EC_PerCancelRequest",
                ))),
                &mut pipeline,
                &mut writer,
                &mut state,
                None,
            )
            .await;
            assert!(!pipeline.has_pending_close("BTCUSDT"));
        }
        handle_exchange_event(
            Some(ExchangeEvent::Fill(h1_exec(
                &po.order_link_id,
                "late-fallback-fill",
                "0.01",
                "Sell",
            ))),
            &mut pipeline,
            &mut writer,
            &mut state,
            None,
        )
        .await;
        assert_eq!(
            pipeline.has_pending_close("BTCUSDT"),
            !successor_finishes_first,
            "late predecessor fill must preserve only a still-active successor guard"
        );
        let mut terminal =
            terminal_order_update(&po.order_link_id, "Cancelled", "EC_PerCancelRequest");
        terminal.cum_exec_qty = "0.01".into();
        handle_exchange_event(
            Some(ExchangeEvent::OrderUpdate(terminal)),
            &mut pipeline,
            &mut writer,
            &mut state,
            None,
        )
        .await;
        assert_eq!(
            pipeline.has_pending_close("BTCUSDT"),
            !successor_finishes_first
        );
        if !successor_finishes_first {
            handle_exchange_event(
                Some(ExchangeEvent::OrderUpdate(terminal_order_update(
                    &successor.order_link_id,
                    "Cancelled",
                    "EC_PerCancelRequest",
                ))),
                &mut pipeline,
                &mut writer,
                &mut state,
                None,
            )
            .await;
        }
        assert!(!pipeline.has_pending_close("BTCUSDT"));
        assert!(!pipeline.exchange_submission_guard.blocks_entry());
        assert!(state.pending_orders.is_empty());
        assert!(dispatch_rx.try_recv().is_err(), "no second fallback");
    }
}

#[tokio::test]
async fn h1_reprice_lost_cancel_ack_reconciles_after_grace() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, mut dispatch_rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    let mut state = make_loop_state();
    let mut po = close_maker_pending_order("h1-reprice-lost-ack");
    po.progress.status = super::super::order_lifecycle::OrderStatus::Unknown;
    po.progress.replacement_order_link_id = Some("h1-reprice-successor".into());
    po.cancel_requested_ts_ms = Some(po.sent_ts_ms);
    pipeline.exchange_submission_guard.track(&po.order_link_id);
    pipeline.retain_pending_close(&po.symbol);
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    let mut successor = close_maker_pending_order("h1-reprice-successor");
    successor.order_type = "market".into();
    successor.time_in_force = None;
    successor.close_maker_audit = None;
    pipeline
        .exchange_submission_guard
        .track(&successor.order_link_id);
    state
        .pending_orders
        .insert(successor.order_link_id.clone(), successor.clone());
    let order = serde_json::json!({"list":[{"orderId":"venue-old", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Sell", "orderStatus":"Cancelled", "cumExecQty":"0"}]});
    let (reconciler, mut rx) =
        super::super::dcp_reconciliation::DcpReconciler::fixture(vec![order]);
    state.dcp_reconciler = Some(reconciler);
    let mut writer = super::make_test_writer();
    handle_exchange_event(
        Some(ExchangeEvent::OrderUpdate(terminal_order_update(
            &successor.order_link_id,
            "Cancelled",
            "EC_PerCancelRequest",
        ))),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert!(
        pipeline.exchange_submission_guard.blocks_entry(),
        "predecessor still unresolved"
    );
    let grace = super::super::pending_sweep::CLOSE_MAKER_CANCEL_ACK_GRACE_MS;
    super::super::loop_tick::sweep_pending_orders(
        &mut pipeline,
        &mut state,
        None,
        po.sent_ts_ms + grace - 1,
    );
    assert!(state.dcp_reconciler.as_ref().unwrap().is_idle());
    super::super::loop_tick::sweep_pending_orders(
        &mut pipeline,
        &mut state,
        None,
        po.sent_ts_ms + grace,
    );
    let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
        .await
        .expect("reprice predecessor must receive authoritative reconciliation")
        .unwrap();
    handle_exchange_event(Some(event), &mut pipeline, &mut writer, &mut state, None).await;
    super::super::loop_tick::sweep_pending_orders(
        &mut pipeline,
        &mut state,
        None,
        po.sent_ts_ms + grace + 60_000,
    );
    assert!(state.pending_orders.is_empty());
    assert!(!pipeline.exchange_submission_guard.blocks_entry());
    assert!(!pipeline.has_pending_close("BTCUSDT"));
    assert!(
        dispatch_rx.try_recv().is_err(),
        "reconciliation cannot place extra orders"
    );
}

#[tokio::test]
async fn h1_reprice_nonterminal_reconciliation_retries_after_cooldown() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, mut dispatch_rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    let mut state = make_loop_state();
    let mut po = close_maker_pending_order("h1-reprice-retry");
    po.progress.status = super::super::order_lifecycle::OrderStatus::Unknown;
    po.progress.replacement_order_link_id = Some("successor".into());
    po.cancel_requested_ts_ms = Some(po.sent_ts_ms);
    pipeline.exchange_submission_guard.track(&po.order_link_id);
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    let active = serde_json::json!({"list":[{"orderId":"venue", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Sell", "orderStatus":"New", "cumExecQty":"0"}]});
    let mut terminal = active.clone();
    terminal["list"][0]["orderStatus"] = "Cancelled".into();
    let (reconciler, mut rx) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        active.clone(),
        active.clone(),
        active,
        terminal,
    ]);
    state.dcp_reconciler = Some(reconciler);
    let now = po.sent_ts_ms + 60_000;
    super::super::loop_tick::sweep_pending_orders(&mut pipeline, &mut state, None, now);
    assert!(!state.dcp_reconciler.as_ref().unwrap().is_idle());
    tokio::time::timeout(std::time::Duration::from_secs(3), async {
        while !state.dcp_reconciler.as_ref().unwrap().is_idle() {
            tokio::time::sleep(std::time::Duration::from_millis(25)).await;
        }
    })
    .await
    .unwrap();
    assert!(rx.try_recv().is_err());
    assert!(pipeline.exchange_submission_guard.blocks_entry());
    for elapsed in [1, 1000, 29_999] {
        super::super::loop_tick::sweep_pending_orders(
            &mut pipeline,
            &mut state,
            None,
            now + elapsed,
        );
        assert!(
            state.dcp_reconciler.as_ref().unwrap().is_idle(),
            "no retry before cooldown"
        );
    }
    // The standalone timer callback also retries without a public price tick.
    super::super::loop_tick::schedule_pending_reconciliation(&mut state, now + 30_000);
    let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
        .await
        .expect("nonterminal read must not permanently disable reconciliation")
        .unwrap();
    let mut writer = super::make_test_writer();
    handle_exchange_event(Some(event), &mut pipeline, &mut writer, &mut state, None).await;
    assert!(state.pending_orders.is_empty());
    assert!(!pipeline.exchange_submission_guard.blocks_entry());
    assert!(
        dispatch_rx.try_recv().is_err(),
        "read retries cannot create orders"
    );
}

#[tokio::test]
async fn h1_execution_cursor_requires_explicit_string() {
    let mut po = baseline_pending_order("market", None);
    po.order_link_id = "h1-invalid-cursor".into();
    let order = serde_json::json!({"list":[{"orderId":"venue", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Buy", "orderStatus":"Cancelled", "cumExecQty":"0.01"}]});
    let page = serde_json::json!({"list":[{"execId":"e", "orderId":"venue", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Buy", "execQty":"0.01", "execPrice":"50000", "execTime":"100", "execType":"Trade"}]});
    for cursor in [
        None,
        Some(serde_json::Value::Null),
        Some(serde_json::json!(123)),
        Some(serde_json::json!({})),
    ] {
        let mut response = page.clone();
        if let Some(value) = cursor {
            response["nextPageCursor"] = value;
        }
        let (reconciler, _) =
            super::super::dcp_reconciliation::DcpReconciler::fixture(vec![order.clone(), response]);
        let error = reconciler
            .reconcile_fixture(&po)
            .await
            .err()
            .expect("quantity agreement cannot replace pagination completeness");
        assert!(error.contains("cursor"));
    }
    let mut complete = page;
    complete["nextPageCursor"] = "".into();
    let (reconciler, _) =
        super::super::dcp_reconciliation::DcpReconciler::fixture(vec![order, complete]);
    assert_eq!(reconciler.reconcile_fixture(&po).await.unwrap().len(), 2);
}

#[tokio::test]
async fn h1_timer_reconciles_aged_nonterminal_orders_without_ticks() {
    use super::super::order_lifecycle::OrderStatus;
    for status in [
        OrderStatus::Submitted,
        OrderStatus::Acknowledged,
        OrderStatus::Working,
        OrderStatus::PartiallyFilled,
    ] {
        for maker in [false, true] {
            let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
            let (tx, mut dispatch_rx) = tokio::sync::mpsc::unbounded_channel();
            pipeline.set_shadow_channel(tx);
            let mut state = make_loop_state();
            let mut po = baseline_pending_order("market", None);
            po.order_link_id = format!("h1-stalled-feed-{status:?}-{maker}");
            po.progress.status = status;
            if maker {
                po.time_in_force = Some(crate::order_manager::TimeInForce::PostOnly);
                po.maker_timeout_ms = Some(45_000);
            }
            pipeline.exchange_submission_guard.track(&po.order_link_id);
            state
                .pending_orders
                .insert(po.order_link_id.clone(), po.clone());
            let terminal = serde_json::json!({"list":[{"orderId":"venue", "orderLinkId":po.order_link_id,
                "symbol":"BTCUSDT", "side":"Buy", "orderStatus":"Cancelled", "cumExecQty":"0"}]});
            let (reconciler, mut rx) =
                super::super::dcp_reconciliation::DcpReconciler::fixture(vec![terminal]);
            state.dcp_reconciler = Some(reconciler);
            // Call only the production independent-timer callback, never a tick/sweep.
            let timeout = if maker { 45_000 } else { 60_001 };
            super::super::loop_tick::schedule_pending_reconciliation(
                &mut state,
                po.sent_ts_ms + timeout - 1,
            );
            assert!(state.dcp_reconciler.as_ref().unwrap().is_idle());
            super::super::loop_tick::schedule_pending_reconciliation(
                &mut state,
                po.sent_ts_ms + timeout,
            );
            let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
                .await
                .expect("stalled public feed must not stall confirmation")
                .unwrap();
            let mut writer = super::make_test_writer();
            handle_exchange_event(Some(event), &mut pipeline, &mut writer, &mut state, None).await;
            assert!(state.pending_orders.is_empty());
            assert!(!pipeline.exchange_submission_guard.blocks_entry());
            assert!(
                dispatch_rx.try_recv().is_err(),
                "timer reads cannot place/cancel orders"
            );
        }
    }
}

#[tokio::test]
async fn h1_reprice_terminal_predecessor_recovers_missing_execution() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    seed_long_position(&mut pipeline);
    let mut state = make_loop_state();
    let mut po = close_maker_pending_order("h1-reprice-missing-execution");
    po.progress.status = super::super::order_lifecycle::OrderStatus::Cancelled;
    po.progress.venue_filled_qty = Some(0.01);
    po.progress.replacement_order_link_id = Some("already-completed-successor".into());
    po.cancel_requested_ts_ms = Some(po.sent_ts_ms);
    pipeline.exchange_submission_guard.track(&po.order_link_id);
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    let order = serde_json::json!({"list":[{"orderId":"venue", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Sell", "orderStatus":"Cancelled", "cumExecQty":"0.01"}]});
    let page = serde_json::json!({"list":[{"execId":"missing", "orderId":"venue", "orderLinkId":po.order_link_id,
        "symbol":"BTCUSDT", "side":"Sell", "execQty":"0.01", "execPrice":"50000", "execTime":"1700000000100", "execType":"Trade"}], "nextPageCursor":""});
    let (reconciler, mut rx) =
        super::super::dcp_reconciliation::DcpReconciler::fixture(vec![order, page]);
    state.dcp_reconciler = Some(reconciler);
    super::super::loop_tick::sweep_pending_orders(
        &mut pipeline,
        &mut state,
        None,
        po.sent_ts_ms + 60_000,
    );
    let mut writer = super::make_test_writer();
    for _ in 0..2 {
        let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
            .await
            .unwrap()
            .unwrap();
        handle_exchange_event(Some(event), &mut pipeline, &mut writer, &mut state, None).await;
    }
    assert!(state.pending_orders.is_empty());
    assert!(!pipeline.exchange_submission_guard.blocks_entry());
    assert!(
        !pipeline.has_pending_close("BTCUSDT"),
        "completed successor guard cannot be resurrected"
    );
    assert_eq!(pipeline.stats.total_fills, 1);
}

#[tokio::test]
async fn h1_invalid_ws_execution_does_not_poison_rest_replay() {
    for (field, value) in [
        ("qty", ""),
        ("qty", "NaN"),
        ("qty", "-1"),
        ("price", ""),
        ("price", "0"),
        ("price", "inf"),
        ("time", ""),
        ("time", "bad"),
        ("time", "0"),
    ] {
        let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
        let mut state = make_loop_state();
        let mut po = baseline_pending_order("market", None);
        po.order_link_id = "h1-malformed-ws".into();
        po.qty = 0.03;
        pipeline.exchange_submission_guard.track(&po.order_link_id);
        state
            .pending_orders
            .insert(po.order_link_id.clone(), po.clone());
        let mut bad = h1_exec(&po.order_link_id, "recoverable", "0.01", "Buy");
        match field {
            "qty" => bad.exec_qty = value.into(),
            "price" => bad.exec_price = value.into(),
            "time" => bad.exec_time = value.into(),
            _ => unreachable!(),
        }
        let mut writer = super::make_test_writer();
        handle_exchange_event(
            Some(ExchangeEvent::Fill(bad)),
            &mut pipeline,
            &mut writer,
            &mut state,
            None,
        )
        .await;
        let observed = state.pending_orders[&po.order_link_id].clone();
        assert!(
            observed.progress.applied_execution_ids.is_empty(),
            "{field}={value} must not poison persistent dedup"
        );
        assert!(!state.seen_exec_set.contains("recoverable"));
        assert_eq!(observed.cum_filled_qty, 0.0);
        assert_eq!(pipeline.stats.total_fills, 0);
        let order = serde_json::json!({"list":[{"orderId":"venue", "orderLinkId":po.order_link_id, "symbol":"BTCUSDT", "side":"Buy", "orderStatus":"Cancelled", "cumExecQty":"0.01"}]});
        let page = serde_json::json!({"list":[{"execId":"recoverable", "orderId":"venue", "orderLinkId":po.order_link_id, "symbol":"BTCUSDT", "side":"Buy", "execQty":"0.01", "execPrice":"50000", "execTime":"1700000000100", "execType":"Trade"}], "nextPageCursor":""});
        let (reconciler, _) =
            super::super::dcp_reconciliation::DcpReconciler::fixture(vec![order, page]);
        let events = reconciler.reconcile_fixture(&observed).await.unwrap();
        assert_eq!(
            events.len(),
            2,
            "valid REST execution must remain replayable"
        );
        for event in events {
            handle_exchange_event(Some(event), &mut pipeline, &mut writer, &mut state, None).await;
        }
        assert_eq!(pipeline.stats.total_fills, 1);
        assert!(!pipeline.exchange_submission_guard.blocks_entry());
        assert!(state.pending_orders.is_empty());
    }
}

#[tokio::test]
async fn h1_ordinary_disconnect_reconciles_without_dcp() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let (tx, mut dispatch_rx) = tokio::sync::mpsc::unbounded_channel::<OrderDispatchRequest>();
    pipeline.set_shadow_channel(tx);
    let mut state = make_loop_state();
    let mut po = baseline_pending_order("market", None);
    po.order_link_id = "h1-disconnect".into();
    po.progress.status = super::super::order_lifecycle::OrderStatus::Working;
    pipeline.exchange_submission_guard.track(&po.order_link_id);
    state
        .pending_orders
        .insert(po.order_link_id.clone(), po.clone());
    let order = serde_json::json!({"list":[{"orderId":"venue", "orderLinkId":po.order_link_id, "symbol":"BTCUSDT", "side":"Buy", "orderStatus":"Cancelled", "cumExecQty":"0"}]});
    let (reconciler, mut rx) =
        super::super::dcp_reconciliation::DcpReconciler::fixture(vec![order]);
    state.dcp_reconciler = Some(reconciler);
    let mut writer = super::make_test_writer();
    handle_exchange_event(
        Some(ExchangeEvent::Disconnected),
        &mut pipeline,
        &mut writer,
        &mut state,
        None,
    )
    .await;
    assert!(pipeline.exchange_submission_guard.blocks_entry());
    let event = tokio::time::timeout(std::time::Duration::from_secs(1), rx.recv())
        .await
        .expect("ordinary disconnect must schedule authoritative reads")
        .unwrap();
    handle_exchange_event(Some(event), &mut pipeline, &mut writer, &mut state, None).await;
    assert!(state.pending_orders.is_empty());
    assert!(!pipeline.exchange_submission_guard.blocks_entry());
    assert!(dispatch_rx.try_recv().is_err());
}
