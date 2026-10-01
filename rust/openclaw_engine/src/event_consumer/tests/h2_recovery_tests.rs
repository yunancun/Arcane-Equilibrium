// H2 tests use a dedicated temporary PostgreSQL cluster, never ambient DATABASE_URL.
use super::super::execution_recovery::ExecutionRecovery;
use super::super::loop_handlers::LoopState;

fn h2_request(po: &PendingOrder) -> crate::order_manager::CreateOrderRequest {
    use crate::order_manager::*;
    CreateOrderRequest {
        category: OrderCategory::Linear,
        symbol: po.symbol.clone(),
        side: if po.is_long {
            OrderSide::Buy
        } else {
            OrderSide::Sell
        },
        order_type: OrderType::Market,
        qty: po.qty,
        price: po.limit_price,
        time_in_force: po.time_in_force,
        reduce_only: Some(po.is_close),
        close_on_trigger: None,
        order_link_id: Some(po.order_link_id.clone()),
        trigger_price: None,
        trigger_direction: None,
        take_profit: None,
        stop_loss: None,
        tp_trigger_by: None,
        sl_trigger_by: None,
    }
}
const H2_SCHEMA: &str = r#"
CREATE SCHEMA trading;
CREATE TABLE trading.orders(ts timestamptz,order_id text,symbol text,side text,order_type text,time_in_force text,qty real,strategy_name text,category text,is_paper boolean,status text,engine_mode text,intent_id text,price real,context_id text,details jsonb,PRIMARY KEY(order_id,ts));
CREATE TABLE trading.order_state_changes(ts timestamptz,order_id text,from_status text,to_status text,filled_qty real,avg_price real,reason text,engine_mode text,PRIMARY KEY(order_id,ts,to_status));
CREATE TABLE trading.fills(ts timestamptz,fill_id text,order_id text,symbol text,side text,qty real,price real,fee real,fee_rate real,reference_price double precision,reference_ts_ms bigint,reference_source text,slippage_bps double precision,liquidity_role text,fill_latency_ms bigint,realized_pnl real,is_paper boolean,strategy_name text,context_id text,entry_context_id text,engine_mode text,exit_source text,exit_reason text,details jsonb,close_maker_attempt boolean,close_maker_fallback_reason text,maker_markout_bps double precision,PRIMARY KEY(fill_id,ts));
CREATE TABLE trading.funding_settlements(ts timestamptz,settlement_id text,exec_id text,symbol text,side text,amount double precision,fee_currency text,exec_value double precision,exec_price double precision,exec_qty double precision,strategy_name text,engine_mode text,raw jsonb,PRIMARY KEY(settlement_id,ts));
"#;
const H2_MIGRATION: &str =
    include_str!("../../../../../sql/migrations/V162__bybit_execution_recovery.sql");
async fn h2_pool() -> sqlx::PgPool {
    use std::str::FromStr;
    let url =
        std::env::var("H2_TEST_DATABASE_URL").expect("explicit isolated H2 fixture URL required");
    assert!(url.starts_with(
        "postgresql://h2_test@localhost:55439/postgres?host=/private/tmp/bybit-h2-pg-"
    ));
    let options = sqlx::postgres::PgConnectOptions::from_str(&url).unwrap();
    let admin = sqlx::PgPool::connect_with(options.clone()).await.unwrap();
    let db = format!("h2_{}", uuid::Uuid::new_v4().simple());
    sqlx::query(&format!("CREATE DATABASE {db}"))
        .execute(&admin)
        .await
        .unwrap();
    admin.close().await;
    let pool = sqlx::PgPool::connect_with(options.database(&db))
        .await
        .unwrap();
    sqlx::raw_sql(H2_SCHEMA).execute(&pool).await.unwrap();
    for _ in 0..2 {
        sqlx::raw_sql(H2_MIGRATION).execute(&pool).await.unwrap();
    }
    pool
}
async fn h2_start(
    pool: &sqlx::PgPool,
) -> (
    ExecutionRecovery,
    TickPipeline,
    LoopState,
    crate::persistence::DualStateWriter,
) {
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
    let mut s = make_loop_state();
    let mut w = super::make_test_writer();
    let mut r = ExecutionRecovery::open(pool, "demo", "fixture-account", &mut p, &mut s)
        .await
        .unwrap();
    r.recover(&mut p, &mut s, &mut w, None).await.unwrap();
    h2_confirm_account(&mut r, &p, &mut s).await;
    (r, p, s, w)
}
async fn h2_register(
    r: &mut ExecutionRecovery,
    p: &mut TickPipeline,
    s: &mut LoopState,
    id: &str,
    qty: f64,
    is_close: bool,
) -> PendingOrder {
    let mut po = baseline_pending_order("market", None);
    po.order_link_id = id.into();
    po.qty = qty;
    po.is_close = is_close;
    po.is_long = !is_close;
    let (ready, rx) = tokio::sync::oneshot::channel();
    r.registration(
        Some(PendingOrderEvent::RegisterBeforeSubmit {
            request: h2_request(&po),
            order: po.clone(),
            ready,
        }),
        p,
        s,
        None,
    )
    .await;
    rx.await
        .expect("durable registration permits first submission");
    po
}
async fn h2_count(pool: &sqlx::PgPool, table: &str) -> i64 {
    sqlx::query_scalar(&format!("SELECT COUNT(*) FROM trading.{table}"))
        .fetch_one(pool)
        .await
        .unwrap()
}
fn h2_accounting(p: &TickPipeline, qty: f64, fees: f64, pnl: f64) {
    let snapshot = p.paper_state.export_state();
    assert!(
        (snapshot
            .positions
            .iter()
            .map(|p| p.position.qty)
            .sum::<f64>()
            - qty)
            .abs()
            < 1e-9
    );
    assert!(
        (snapshot.total_fees - fees).abs() < 1e-9,
        "fees: {} != {fees}",
        snapshot.total_fees
    );
    assert!(
        (snapshot.total_realized_pnl - pnl).abs() < 1e-9,
        "pnl: {} != {pnl}",
        snapshot.total_realized_pnl
    );
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_restart_execution_contributes_once() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    let po = h2_register(&mut r, &mut p, &mut s, "restart", 0.02, false).await;
    let first = h1_exec(&po.order_link_id, "restart-exec", "0.01", "Buy");
    r.exchange(
        Some(ExchangeEvent::Fill(first.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.01, 0.01, 0.0);
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    assert!(p.exchange_submission_guard.blocks_entry());
    h2_accounting(&p, 0.01, 0.01, 0.0);
    r.exchange(
        Some(ExchangeEvent::Fill(first.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.01, 0.01, 0.0);
    let second = h1_exec(&po.order_link_id, "restart-exec-2", "0.01", "Buy");
    r.exchange(
        Some(ExchangeEvent::Fill(second)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.02, 0.02, 0.0);
    h2_confirm_account(&mut r, &p, &mut s).await;
    assert!(!p.exchange_submission_guard.blocks_entry());
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    r.exchange(
        Some(ExchangeEvent::Fill(first)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.02, 0.02, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 2);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_old_execution_after_502_fills_and_restart() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "many", 5.02, false).await;
    for i in 0..502 {
        r.exchange(
            Some(ExchangeEvent::Fill(h1_exec(
                "many",
                &format!("e{i}"),
                "0.01",
                "Buy",
            ))),
            &mut p,
            &mut s,
            &mut w,
            None,
        )
        .await;
    }
    assert_eq!(h2_count(&pool, "fills").await, 502);
    h2_accounting(&p, 5.02, 5.02, 0.0);
    assert!(!s.seen_exec_set.contains("e0"));
    r.exchange(
        Some(ExchangeEvent::Fill(h1_exec("many", "e0", "0.01", "Buy"))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 5.02, 5.02, 0.0);
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    r.exchange(
        Some(ExchangeEvent::Fill(h1_exec("many", "e0", "0.01", "Buy"))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 5.02, 5.02, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 502);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_crash_before_submit_keeps_intent_and_incomplete_reconciliation_blocks_entry() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, _w) = h2_start(&pool).await;
    let po = h2_register(&mut r, &mut p, &mut s, "no-ack", 0.1, false).await;
    drop(r);
    let (_r, p, mut s, _w) = h2_start(&pool).await;
    let (reconciler, _rx) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        serde_json::json!({"list":[]}),
        serde_json::json!({"list":[]}),
    ]);
    assert!(reconciler.reconcile_fixture(&po).await.is_err());
    assert_eq!(s.pending_orders.len(), 1);
    assert!(!p
        .exchange_submission_guard
        .reserve_queued("new-risk", false));
    assert_eq!(h2_count(&pool, "bybit_order_intents").await, 1);
    // Runtime reset cannot clear the durable-storage failure latch.
    p.exchange_submission_guard.block_storage(true);
    p.exchange_submission_guard.clear();
    assert!(p.exchange_submission_guard.blocks_entry());
    s.pending_orders.clear();
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_commit_failure_rolls_back_fill_and_progress_then_inbox_replays_once() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "rollback", 0.02, false).await;
    sqlx::raw_sql("CREATE FUNCTION h2_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'injected after fill insert before projection commit'; END $$; CREATE TRIGGER fail_checkpoint BEFORE UPDATE ON trading.bybit_recovery FOR EACH ROW EXECUTE FUNCTION h2_fail();").execute(&pool).await.unwrap();
    let e = h1_exec("rollback", "rollback-exec", "0.01", "Buy");
    r.exchange(
        Some(ExchangeEvent::Fill(e.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert!(p.exchange_submission_guard.blocks_entry());
    assert!(!p
        .exchange_submission_guard
        .reserve_queued("protective", true));
    h2_accounting(&p, 0.0, 0.0, 0.0);
    assert!(
        p.snapshot().recent_fills.is_empty(),
        "failed transaction must not publish a provisional fill"
    );
    assert_eq!(h2_count(&pool, "fills").await, 0);
    let applied: bool = sqlx::query_scalar("SELECT applied FROM trading.bybit_execution_inbox")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert!(!applied);
    drop(r);
    sqlx::raw_sql("DROP TRIGGER fail_checkpoint ON trading.bybit_recovery")
        .execute(&pool)
        .await
        .unwrap();
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_accounting(&p, 0.01, 0.01, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 1);
    r.exchange(Some(ExchangeEvent::Fill(e)), &mut p, &mut s, &mut w, None)
        .await;
    h2_accounting(&p, 0.01, 0.01, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 1);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_cancel_then_late_close_fill_recovers_attribution_and_pnl() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "open", 0.1, false).await;
    r.exchange(
        Some(ExchangeEvent::Fill(h1_exec(
            "open",
            "open-exec",
            "0.1",
            "Buy",
        ))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_register(&mut r, &mut p, &mut s, "close", 0.1, true).await;
    let mut cancel = terminal_order_update("close", "Cancelled", "");
    cancel.order_type = "Market".into();
    r.exchange(
        Some(ExchangeEvent::OrderUpdate(cancel)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert!(
        s.pending_orders.contains_key("close"),
        "terminal WS is not full REST proof"
    );
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    let mut e = h1_exec("close", "close-exec", "0.1", "Sell");
    e.exec_price = "60000".into();
    e.order_link_id.clear();
    r.exchange(
        Some(ExchangeEvent::Fill(e.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.0, 0.02, 1000.0);
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    r.exchange(Some(ExchangeEvent::Fill(e)), &mut p, &mut s, &mut w, None)
        .await;
    h2_accounting(&p, 0.0, 0.02, 1000.0);
    assert_eq!(h2_count(&pool, "fills").await, 2);
}

async fn h2_confirm_account(r: &mut ExecutionRecovery, p: &TickPipeline, s: &mut LoopState) {
    let positions:Vec<_>=p.paper_state.export_state().positions.iter().map(|row|{
        let pos=&row.position;serde_json::json!({"positionIdx":0,"symbol":pos.symbol,"side":if pos.is_long{"Buy"}else{"Sell"},"size":pos.qty.to_string(),"avgPrice":pos.entry_price.to_string()})
    }).collect();
    let (reconciler, _) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        serde_json::json!({"list":[],"nextPageCursor":""}),
        serde_json::json!({"list":positions,"nextPageCursor":""}),
    ]);
    s.dcp_reconciler = Some(reconciler);
    let now = openclaw_core::now_ms() + 60_000;
    r.reconcile_startup(p, s, now);
    for _ in 0..10 {
        tokio::task::yield_now().await;
        r.reconcile_startup(p, s, now);
    }
    s.dcp_reconciler = None;
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_inbox_commit_before_projection_replays_and_registration_failure_never_signals_ready() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, _w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "inbox", 0.01, false).await;
    // Crash after durable reception, before any accounting projection.
    assert!(r
        .store
        .receive(&h1_exec("inbox", "received", "0.01", "Buy"))
        .await
        .unwrap());
    h2_accounting(&p, 0.0, 0.0, 0.0);
    drop(r);
    let (mut r, mut p, mut s, _w) = h2_start(&pool).await;
    h2_accounting(&p, 0.01, 0.01, 0.0);
    // Immutable terminal IDs still cannot be resubmitted after restart.
    let mut po = baseline_pending_order("market", None);
    po.order_link_id = "inbox".into();
    let (ready, rx) = tokio::sync::oneshot::channel();
    r.registration(
        Some(PendingOrderEvent::RegisterBeforeSubmit {
            request: h2_request(&po),
            order: po,
            ready,
        }),
        &mut p,
        &mut s,
        None,
    )
    .await;
    assert!(rx.await.is_err());
    assert!(p.exchange_submission_guard.blocks_entry());
    assert_eq!(h2_count(&pool, "bybit_order_intents").await, 1);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_owner_account_and_execution_conflicts_fail_closed() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    let mut other = TickPipeline::with_kind(&["BTCUSDT"], 10000.0, PipelineKind::Demo);
    let mut state = make_loop_state();
    assert!(
        ExecutionRecovery::open(&pool, "demo", "fixture-account", &mut other, &mut state)
            .await
            .is_err()
    );
    assert!(other.exchange_submission_guard.blocks_entry());
    h2_register(&mut r, &mut p, &mut s, "conflict", 0.02, false).await;
    let e = h1_exec("conflict", "conflicting-exec", "0.01", "Buy");
    r.exchange(Some(ExchangeEvent::Fill(e)), &mut p, &mut s, &mut w, None)
        .await;
    let changed = h1_exec("conflict", "conflicting-exec", "0.02", "Buy");
    r.exchange(
        Some(ExchangeEvent::Fill(changed)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.01, 0.01, 0.0);
    assert!(p.exchange_submission_guard.blocks_entry());
    drop(r);
    assert!(
        ExecutionRecovery::open(&pool, "demo", "different-account", &mut other, &mut state)
            .await
            .is_err()
    );
}

#[tokio::test]
async fn h2_account_barrier_uses_valid_endpoint_limits() {
    use std::{future::Future, pin::Pin, sync::Arc};
    let calls = Arc::new(parking_lot::Mutex::new(Vec::new()));
    let observed = calls.clone();
    let fetch = Arc::new(move |path: &'static str, params: Vec<(String, String)>| {
        let maximum = match path {
            "/v5/order/realtime" => 50,
            "/v5/position/list" => 200,
            _ => panic!("unexpected account reconciliation endpoint"),
        };
        let limit = params
            .iter()
            .find(|(key, _)| key == "limit")
            .and_then(|(_, value)| value.parse::<u32>().ok());
        observed.lock().push(path);
        let result = if limit.is_some_and(|limit| (1..=maximum).contains(&limit)) {
            Ok(serde_json::json!({"list":[],"nextPageCursor":""}))
        } else {
            Err("Bybit query limit exceeds endpoint contract".into())
        };
        let response: Pin<Box<dyn Future<Output = Result<serde_json::Value, String>> + Send>> =
            Box::pin(std::future::ready(result));
        response
    });
    let (checker, _) = super::super::dcp_reconciliation::DcpReconciler::fixture_with_fetch(fetch);
    let p = TickPipeline::with_kind(&["BTCUSDT"], 10000.0, PipelineKind::Demo);
    assert!(
        checker
            .account_matches(&p.paper_state.export_state())
            .await
            .is_ok(),
        "an empty, reconciled account must clear the startup barrier"
    );
    assert_eq!(
        *calls.lock(),
        vec!["/v5/order/realtime", "/v5/position/list"]
    );
}

#[tokio::test]
async fn h2_account_barrier_requires_complete_matching_pages() {
    let p = TickPipeline::with_kind(&["BTCUSDT"], 10000.0, PipelineKind::Demo);
    let empty = serde_json::json!({"list":[],"nextPageCursor":""});
    let (valid, _) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        empty.clone(),
        empty.clone(),
    ]);
    assert!(valid
        .account_matches(&p.paper_state.export_state())
        .await
        .is_ok());
    for responses in [
        vec![serde_json::json!({"list":[]})],
        vec![serde_json::json!({"list":[{"orderId":"unowned"}],"nextPageCursor":""})],
        vec![empty.clone(), serde_json::json!({"list":[]})],
        vec![
            empty.clone(),
            serde_json::json!({"list":[{"positionIdx":0,"symbol":"BTCUSDT","side":"Buy","size":"0.1","avgPrice":"50000"}],"nextPageCursor":""}),
        ],
        vec![
            empty.clone(),
            serde_json::json!({"list":[],"nextPageCursor":"again"}),
            serde_json::json!({"list":[],"nextPageCursor":"again"}),
        ],
    ] {
        let (fixture, _) = super::super::dcp_reconciliation::DcpReconciler::fixture(responses);
        assert!(fixture
            .account_matches(&p.paper_state.export_state())
            .await
            .is_err());
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_cold_legacy_lane_is_not_silently_adopted() {
    let pool = h2_pool().await;
    sqlx::query(
        "INSERT INTO trading.orders(ts,order_id,engine_mode) VALUES(NOW(),'legacy','demo')",
    )
    .execute(&pool)
    .await
    .unwrap();
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10000.0, PipelineKind::Demo);
    let mut s = make_loop_state();
    assert!(
        ExecutionRecovery::open(&pool, "demo", "fixture-account", &mut p, &mut s)
            .await
            .is_err()
    );
    assert!(!p.exchange_submission_guard.reserve_queued("risk", false));
    assert_eq!(h2_count(&pool, "bybit_recovery").await, 0);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_malformed_intent_never_releases_submit_handshake() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, _w) = h2_start(&pool).await;
    let po = baseline_pending_order("market", None);
    let mut request = h2_request(&po);
    request.qty = po.qty * 2.0;
    let (ready, rx) = tokio::sync::oneshot::channel();
    r.registration(
        Some(PendingOrderEvent::RegisterBeforeSubmit {
            request,
            order: po,
            ready,
        }),
        &mut p,
        &mut s,
        None,
    )
    .await;
    assert!(
        rx.await.is_err(),
        "durable tracker must describe the exact venue request"
    );
    assert_eq!(h2_count(&pool, "bybit_order_intents").await, 0);
    assert!(p.exchange_submission_guard.blocks_entry());
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_unknown_venue_id_is_not_guessed_from_a_single_pending_symbol() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "known-intent", 0.02, false).await;
    let mut execution = h1_exec("", "unknown-venue-exec", "0.01", "Buy");
    execution.order_id = "unrelated-venue-id".into();
    r.exchange(
        Some(ExchangeEvent::Fill(execution)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.0, 0.0, 0.0);
    assert!(p.exchange_submission_guard.storage_blocked());
    assert_eq!(h2_count(&pool, "fills").await, 0);
    let applied: bool = sqlx::query_scalar("SELECT applied FROM trading.bybit_execution_inbox")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert!(!applied);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_funding_settlement_is_projected_once_across_restart() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    let mut funding = h1_exec("", "funding-restart", "0", "Buy");
    funding.order_id.clear();
    funding.exec_type = "Funding".into();
    funding.exec_fee = "-2.5".into();
    r.exchange(
        Some(ExchangeEvent::Fill(funding.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert_eq!(p.paper_state.export_state().total_funding_pnl, -2.5);
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    r.exchange(
        Some(ExchangeEvent::Fill(funding)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert_eq!(p.paper_state.export_state().total_funding_pnl, -2.5);
    assert_eq!(p.paper_state.export_state().balance, 9997.5);
    assert_eq!(h2_count(&pool, "funding_settlements").await, 1);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_transaction_cutpoints_and_backend_death_preserve_unapplied_receipt() {
    // Real SQL faults after provisional accounting, canonical row insert, and
    // consumption update; terminate the actual PG owner session before COMMIT.
    for (table, operation, kill_session) in [
        ("fills", "INSERT", false),
        ("bybit_execution_inbox", "UPDATE", false),
        ("bybit_recovery", "UPDATE", false),
        ("bybit_recovery", "UPDATE", true),
    ] {
        let pool = h2_pool().await;
        let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
        h2_register(&mut r, &mut p, &mut s, "cutpoint", 0.02, false).await;
        let body = if kill_session {
            "PERFORM pg_terminate_backend(pg_backend_pid()); RETURN NEW;"
        } else {
            "RAISE EXCEPTION 'injected crash cutpoint';"
        };
        sqlx::raw_sql(&format!("CREATE FUNCTION h2_cut() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN {body} END $$; CREATE TRIGGER cut BEFORE {operation} ON trading.{table} FOR EACH ROW EXECUTE FUNCTION h2_cut();")).execute(&pool).await.unwrap();
        let execution = h1_exec("cutpoint", "cutpoint-execution", "0.01", "Buy");
        r.exchange(
            Some(ExchangeEvent::Fill(execution.clone())),
            &mut p,
            &mut s,
            &mut w,
            None,
        )
        .await;
        h2_accounting(&p, 0.0, 0.0, 0.0);
        assert_eq!(h2_count(&pool, "fills").await, 0);
        assert!(p.snapshot().recent_fills.is_empty());
        assert!(!p
            .exchange_submission_guard
            .reserve_queued("unsafe-open", false));
        drop(r);
        sqlx::raw_sql(&format!("DROP TRIGGER cut ON trading.{table}"))
            .execute(&pool)
            .await
            .unwrap();
        let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
        h2_accounting(&p, 0.01, 0.01, 0.0);
        r.exchange(
            Some(ExchangeEvent::Fill(execution)),
            &mut p,
            &mut s,
            &mut w,
            None,
        )
        .await;
        h2_accounting(&p, 0.01, 0.01, 0.0);
        assert_eq!(h2_count(&pool, "fills").await, 1);
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_intent_commit_failure_does_not_allow_a_venue_call() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, _w) = h2_start(&pool).await;
    sqlx::raw_sql("CREATE FUNCTION fail_intent() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'crash before durable intent'; END $$; CREATE TRIGGER cut BEFORE INSERT ON trading.bybit_order_intents FOR EACH ROW EXECUTE FUNCTION fail_intent();").execute(&pool).await.unwrap();
    let po = baseline_pending_order("market", None);
    let (ready, rx) = tokio::sync::oneshot::channel();
    r.registration(
        Some(PendingOrderEvent::RegisterBeforeSubmit {
            request: h2_request(&po),
            order: po,
            ready,
        }),
        &mut p,
        &mut s,
        None,
    )
    .await;
    assert!(rx.await.is_err());
    assert_eq!(h2_count(&pool, "bybit_order_intents").await, 0);
    assert_eq!(h2_count(&pool, "orders").await, 0);
    drop(r);
    sqlx::raw_sql("DROP TRIGGER cut ON trading.bybit_order_intents")
        .execute(&pool)
        .await
        .unwrap();
    let (_r, p, s, _w) = h2_start(&pool).await;
    assert!(s.pending_orders.is_empty());
    h2_accounting(&p, 0.0, 0.0, 0.0);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_venue_received_before_ack_and_partial_cancel_restart() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, _w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "pre-ack", 0.02, false).await;
    r.registration(
        Some(PendingOrderEvent::SubmissionStarted {
            order_link_id: "pre-ack".into(),
            ts_ms: 200,
        }),
        &mut p,
        &mut s,
        None,
    )
    .await;
    // Venue accepted and filled; local process died before ACK or WS receipt.
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    let pending = s.pending_orders["pre-ack"].clone();
    let execution = h1_exec("pre-ack", "ack-lost-fill", "0.01", "Buy");
    let mut terminal = terminal_order_update("pre-ack", "PartiallyFilledCanceled", "");
    terminal.cum_exec_qty = "0.01".into();
    terminal.order_type = "Market".into();
    terminal.side = "Buy".into();
    terminal.qty = "0.02".into();
    let (reconciler, _) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        serde_json::json!({"list":[terminal],"nextPageCursor":""}),
        serde_json::json!({"list":[execution.clone()],"nextPageCursor":""}),
    ]);
    reconciler.enable_recovery_events();
    let events = reconciler.reconcile_fixture(&pending).await.unwrap();
    for event in events {
        r.exchange(Some(event), &mut p, &mut s, &mut w, None).await;
    }
    h2_accounting(&p, 0.01, 0.01, 0.0);
    assert!(s.pending_orders.is_empty());
    assert!(
        p.exchange_submission_guard.blocks_entry(),
        "account barrier precedes new risk"
    );
    h2_confirm_account(&mut r, &p, &mut s).await;
    assert!(!p.exchange_submission_guard.blocks_entry());
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    r.exchange(
        Some(ExchangeEvent::Fill(execution)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.01, 0.01, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 1);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_commit_survives_snapshot_publication_failure() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, _w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "no-snapshot", 0.01, false).await;
    let temp = tempfile::tempdir().unwrap();
    let blocked = temp.path().join("file");
    std::fs::write(&blocked, "not a directory").unwrap();
    let mut writer = crate::persistence::DualStateWriter::new(
        crate::persistence::StateWriter::new(&blocked.join("snapshot.json"), 0),
        None,
    );
    let execution = h1_exec("no-snapshot", "durable-fill", "0.01", "Buy");
    r.exchange(
        Some(ExchangeEvent::Fill(execution.clone())),
        &mut p,
        &mut s,
        &mut writer,
        None,
    )
    .await;
    assert_eq!(h2_count(&pool, "fills").await, 1);
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    r.exchange(
        Some(ExchangeEvent::Fill(execution)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_accounting(&p, 0.01, 0.01, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 1);
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_migration_rejects_missing_unique_venue_binding() {
    let pool = h2_pool().await;
    sqlx::raw_sql("ALTER TABLE trading.bybit_order_intents DROP CONSTRAINT bybit_order_intents_engine_mode_venue_order_id_key").execute(&pool).await.unwrap();
    let error = sqlx::raw_sql(H2_MIGRATION)
        .execute(&pool)
        .await
        .unwrap_err();
    assert!(error
        .to_string()
        .contains("V162 Guard A: missing unique venue identity"));
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_slow_account_probe_keeps_event_owner_available_and_stale_success_fenced() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    r.exchange(
        Some(ExchangeEvent::Disconnected),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    let gate = std::sync::Arc::new(tokio::sync::Notify::new());
    let calls = std::sync::Arc::new(std::sync::atomic::AtomicUsize::new(0));
    let fetch = {
        let gate = gate.clone();
        let calls = calls.clone();
        std::sync::Arc::new(move |_, _| {
            let gate = gate.clone();
            let number = calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
            let result: std::pin::Pin<
                Box<dyn std::future::Future<Output = Result<serde_json::Value, String>> + Send>,
            > = Box::pin(async move {
                if number == 0 {
                    gate.notified().await;
                }
                Ok(serde_json::json!({"list":[],"nextPageCursor":""}))
            });
            result
        })
    };
    let (checker, _) = super::super::dcp_reconciliation::DcpReconciler::fixture_with_fetch(fetch);
    s.dcp_reconciler = Some(checker);
    let now = openclaw_core::now_ms() + 60_000;
    let started = std::time::Instant::now();
    r.reconcile_startup(&p, &s, now);
    assert!(started.elapsed() < std::time::Duration::from_millis(100));
    // The owner handles an event while REST is stalled; that commit invalidates
    // the older account observation even if the network result later succeeds.
    r.checkpoint_control(&mut p, &mut s, true).await;
    gate.notify_one();
    for _ in 0..10 {
        tokio::task::yield_now().await;
        r.reconcile_startup(&p, &s, now);
    }
    assert!(p.exchange_submission_guard.blocks_entry());
}

#[test]
fn h2_review_queued_fence_rejection_releases_only_unclaimed_request() {
    let guard = super::super::order_lifecycle::SubmissionGuard::default();
    assert!(guard.reserve_queued("queued", false));
    guard.block_reconciliation(true);
    assert!(!guard.reserve("queued", false));
    assert!(!guard.contains("queued"));
    guard.block_reconciliation(false);
    assert!(guard.reserve_queued("next", false));
    assert!(guard.reserve("next", false));
    guard.block_storage(true);
    assert!(!guard.reserve("next", false));
    assert!(guard.contains("next"), "claimed intent cannot be discarded");
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_review_fast_rest_type_enrichment_preserves_identity_and_accounting() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "fast", 0.01, false).await;
    let mut fast = h1_exec("fast", "fast-exec", "0.01", "Buy");
    fast.exec_type.clear();
    r.exchange(
        Some(ExchangeEvent::Fill(fast.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    let mut rest = fast.clone();
    rest.exec_type = "Trade".into();
    r.exchange(
        Some(ExchangeEvent::Fill(rest.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert!(!p.exchange_submission_guard.storage_blocked());
    h2_accounting(&p, 0.01, 0.01, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 1);
    assert!(!r.store.receive(&fast).await.unwrap());
    rest.exec_type = "Funding".into();
    assert!(
        r.store.receive(&rest).await.is_err(),
        "different known types conflict after enrichment"
    );
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_review_unknown_order_update_fences_without_mutating_accounting() {
    for link in ["", "foreign"] {
        let pool = h2_pool().await;
        let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
        let update = terminal_order_update(link, "New", "");
        r.exchange(
            Some(ExchangeEvent::OrderUpdate(update)),
            &mut p,
            &mut s,
            &mut w,
            None,
        )
        .await;
        assert!(
            p.exchange_submission_guard.storage_blocked(),
            "unknown live order must fence submission"
        );
        assert_eq!(h2_count(&pool, "bybit_order_intents").await, 0);
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_review_migration_rejects_incompatible_unapplied_indexes() {
    let pool = h2_pool().await;
    for definition in [
        "ON trading.bybit_execution_inbox(receive_seq,engine_mode) WHERE NOT applied",
        "ON trading.bybit_execution_inbox(engine_mode,receive_seq DESC) WHERE NOT applied",
        "ON trading.bybit_execution_inbox(engine_mode,receive_seq) WHERE applied",
        "ON trading.bybit_order_intents(engine_mode,order_link_id)",
    ] {
        sqlx::raw_sql(&format!("DROP INDEX trading.bybit_execution_unapplied; CREATE INDEX bybit_execution_unapplied {definition}"))
            .execute(&pool).await.unwrap();
        let error = sqlx::raw_sql(H2_MIGRATION)
            .execute(&pool)
            .await
            .unwrap_err();
        assert!(error.to_string().contains("V162 Guard C"), "{error}");
    }
    sqlx::raw_sql("DROP INDEX trading.bybit_execution_unapplied")
        .execute(&pool)
        .await
        .unwrap();
    for _ in 0..2 {
        sqlx::raw_sql(H2_MIGRATION).execute(&pool).await.unwrap();
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_review_retired_cancel_reconciles_rest_fill_after_later_checkpoint() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "opened", 0.1, false).await;
    r.exchange(
        Some(ExchangeEvent::Fill(h1_exec(
            "opened",
            "opened-exec",
            "0.1",
            "Buy",
        ))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_register(&mut r, &mut p, &mut s, "retired", 0.1, true).await;
    let mut cancel = terminal_order_update("retired", "Cancelled", "");
    cancel.order_type = "Market".into();
    r.exchange(
        Some(ExchangeEvent::OrderUpdate(cancel.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    r.checkpoint_control(&mut p, &mut s, true).await;
    drop(r);
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    assert!(
        s.pending_orders.contains_key("retired"),
        "durable terminal intent needs REST confirmation after restart"
    );
    assert!(p.exchange_submission_guard.blocks_entry());
    cancel.cum_exec_qty = "0.1".into();
    let execution = h1_exec("retired", "offline-close", "0.1", "Sell");
    let (checker, mut events) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        serde_json::json!({"list":[cancel],"nextPageCursor":""}),
        serde_json::json!({"list":[execution],"nextPageCursor":""}),
    ]);
    checker.enable_recovery_events();
    s.dcp_reconciler = Some(checker);
    super::super::loop_tick::schedule_pending_reconciliation(
        &mut s,
        openclaw_core::now_ms() + 60_000,
    );
    for _ in 0..3 {
        let event = tokio::time::timeout(std::time::Duration::from_secs(1), events.recv())
            .await
            .unwrap()
            .unwrap();
        r.exchange(Some(event), &mut p, &mut s, &mut w, None).await;
    }
    h2_confirm_account(&mut r, &p, &mut s).await;
    h2_accounting(&p, 0.0, 0.02, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 2);
    assert!(!p.exchange_submission_guard.blocks_entry());
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_review_failed_close_does_not_publish_features_lineage_or_release_lease() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "side-open", 0.1, false).await;
    r.exchange(
        Some(ExchangeEvent::Fill(h1_exec(
            "side-open",
            "side-open-exec",
            "0.1",
            "Buy",
        ))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_register(&mut r, &mut p, &mut s, "side-close", 0.1, true).await;
    p.governance.grant_paper_authorization(None).unwrap();
    let lease = p
        .governance
        .acquire_lease(
            "intent:h2-close",
            "TRADE_ENTRY",
            60_000,
            GovernanceProfile::Production,
            "h2_fixture",
        )
        .unwrap();
    let LeaseId::Active(id) = lease else {
        panic!("active fixture lease required");
    };
    let po = s.pending_orders.get_mut("side-close").unwrap();
    po.decision_lease_id = Some(id.clone());
    po.spine_order_plan_id = Some("h2-plan".into());
    po.spine_decision_id = Some("h2-decision".into());
    po.spine_stub_report_id = Some("h2-stub".into());
    r.checkpoint_control(&mut p, &mut s, true).await;
    let (exit_tx, mut exits) = tokio::sync::mpsc::channel(16);
    p.set_exit_feature_tx(exit_tx);
    let (spine_tx, mut spine) = tokio::sync::mpsc::channel(16);
    p.set_agent_spine_runtime(
        Some(spine_tx),
        crate::agent_spine::config::AgentSpineMode::Shadow,
    );
    sqlx::raw_sql("CREATE FUNCTION h2_side_fail() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'close commit failure'; END $$; CREATE TRIGGER side_fail BEFORE UPDATE ON trading.bybit_recovery FOR EACH ROW EXECUTE FUNCTION h2_side_fail();").execute(&pool).await.unwrap();
    let mut close = h1_exec("side-close", "side-close-exec", "0.1", "Sell");
    close.exec_price = "60000".into();
    r.exchange(
        Some(ExchangeEvent::Fill(close.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert!(exits.try_recv().is_err(), "no provisional exit label");
    assert!(spine.try_recv().is_err(), "no provisional fill lineage");
    assert!(
        p.governance.get_lease_by_id(&id).is_ok(),
        "failed commit retains decision lease"
    );
    h2_accounting(&p, 0.1, 0.01, 0.0);
    assert_eq!(h2_count(&pool, "fills").await, 1);
    drop(r);
    sqlx::raw_sql("DROP TRIGGER side_fail ON trading.bybit_recovery")
        .execute(&pool)
        .await
        .unwrap();
    let mut r = ExecutionRecovery::open(&pool, "demo", "fixture-account", &mut p, &mut s)
        .await
        .unwrap();
    r.recover(&mut p, &mut s, &mut w, None).await.unwrap();
    h2_accounting(&p, 0.0, 0.02, 1000.0);
    assert_eq!(h2_count(&pool, "fills").await, 2);
    assert!(exits.try_recv().is_ok(), "committed replay publishes label");
    assert!(
        spine.try_recv().is_ok(),
        "committed replay publishes lineage"
    );
    assert!(
        p.governance.get_lease_by_id(&id).is_err(),
        "committed replay settles lease"
    );
    while spine.try_recv().is_ok() {}
    r.exchange(
        Some(ExchangeEvent::Fill(close)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert!(exits.try_recv().is_err());
    assert!(spine.try_recv().is_err());
    assert_eq!(h2_count(&pool, "fills").await, 2);
}

#[test]
fn h2_followup_final_handoff_rechecks_both_fences() {
    let guard = super::super::order_lifecycle::SubmissionGuard::default();
    assert!(guard.reserve_queued("late-fence", false));
    assert!(guard.reserve("late-fence", false));
    guard.block_reconciliation(true);
    assert!(!guard.claim_venue_handoff("late-fence", false));
    assert!(
        guard.contains("late-fence"),
        "durable ambiguous intent stays unresolved"
    );
    assert!(guard.reserve("protect", true));
    assert!(guard.claim_venue_handoff("protect", true));
    assert!(
        !guard.claim_venue_handoff("protect", true),
        "first handoff cannot be duplicated"
    );
    guard.block_storage(true);
    assert!(!guard.claim_venue_handoff("protect", true));
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_followup_applied_default_requires_false() {
    for replacement in ["SET DEFAULT TRUE", "DROP DEFAULT"] {
        let pool = h2_pool().await;
        sqlx::raw_sql(&format!(
            "ALTER TABLE trading.bybit_execution_inbox ALTER COLUMN applied {replacement}"
        ))
        .execute(&pool)
        .await
        .unwrap();
        let error = sqlx::raw_sql(H2_MIGRATION)
            .execute(&pool)
            .await
            .expect_err("unsafe default must be rejected");
        assert!(error.to_string().contains("Guard A"));
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_followup_legacy_accounting_requires_baseline() {
    for insert in [
        "INSERT INTO trading.fills(ts,fill_id,engine_mode) VALUES(now(),'legacy','demo')",
        "INSERT INTO trading.funding_settlements(ts,settlement_id,engine_mode) VALUES(now(),'legacy','demo')",
        "INSERT INTO trading.order_state_changes(ts,order_id,to_status,engine_mode) VALUES(now(),'legacy','Filled','demo')",
    ] {
        let pool = h2_pool().await;
        sqlx::raw_sql(insert).execute(&pool).await.unwrap();
        let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10_000.0, PipelineKind::Demo);
        let mut s = make_loop_state();
        assert!(ExecutionRecovery::open(&pool,"demo","fixture-account",&mut p,&mut s).await.is_err(),
            "legacy accounting cannot seed an unverified ledger");
        assert_eq!(h2_count(&pool,"bybit_recovery").await,0);
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_followup_closed_channels_never_checkpoint() {
    for registration in [false, true] {
        let pool = h2_pool().await;
        let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
        let generation = r.store.generation();
        for _ in 0..2 {
            if registration {
                r.registration(None, &mut p, &mut s, None).await;
            } else {
                r.exchange(None, &mut p, &mut s, &mut w, None).await;
            }
        }
        assert_eq!(
            r.store.generation(),
            generation,
            "closed channel cannot advance accounting"
        );
        assert!(p.exchange_submission_guard.storage_blocked());
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_followup_rest_terminal_completion_survives_restart() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    let po = h2_register(&mut r, &mut p, &mut s, "confirmed-cancel", 0.1, true).await;
    let cancel = terminal_order_update("confirmed-cancel", "Cancelled", "");
    let (checker, _) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        serde_json::json!({"list":[cancel],"nextPageCursor":""}),
    ]);
    checker.enable_recovery_events();
    let events = checker.reconcile_fixture(&po).await.unwrap();
    for event in events {
        r.exchange(Some(event), &mut p, &mut s, &mut w, None).await;
    }
    r.checkpoint_control(&mut p, &mut s, true).await;
    // Completed lifetime cancellations must not consume the unresolved startup budget.
    sqlx::query("INSERT INTO trading.bybit_order_intents SELECT engine_mode,'archive-'||n,request_hash,request,pending,jsonb_set(progress,'{order_link_id}',to_jsonb('archive-'||n)),'venue-archive-'||n FROM trading.bybit_order_intents CROSS JOIN generate_series(1,4097) n WHERE order_link_id='confirmed-cancel'")
        .execute(&pool).await.unwrap();
    let mut conn = pool.acquire().await.unwrap();
    sqlx::query("SET enable_seqscan=off")
        .execute(&mut *conn)
        .await
        .unwrap();
    let plan: Vec<String> = sqlx::query_scalar(&format!(
        "EXPLAIN (COSTS OFF) {}",
        super::super::recovery_store::TERMINAL_QUERY
    ))
    .bind("demo")
    .fetch_all(&mut *conn)
    .await
    .unwrap();
    assert!(
        plan.join("\n").contains("bybit_terminal_unconfirmed"),
        "{plan:?}"
    );
    drop(conn);
    drop(r);
    let (_, _, s, _) = h2_start(&pool).await;
    assert!(
        !s.pending_orders.contains_key("confirmed-cancel"),
        "complete zero-fill cancel is not an unresolved backlog"
    );
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_followup_completion_commit_failure_requires_reconciliation() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    let po = h2_register(&mut r, &mut p, &mut s, "proof-failure", 0.1, true).await;
    r.exchange(
        Some(ExchangeEvent::OrderUpdate(terminal_order_update(
            "proof-failure",
            "Cancelled",
            "",
        ))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    sqlx::raw_sql("CREATE FUNCTION fail_proof() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture proof cutpoint'; END $$; CREATE TRIGGER fail_proof BEFORE UPDATE ON trading.bybit_recovery FOR EACH ROW EXECUTE FUNCTION fail_proof();").execute(&pool).await.unwrap();
    let generation = r.store.generation();
    r.exchange(
        Some(ExchangeEvent::ReconciliationCompleted {
            order_link_id: po.order_link_id.clone(),
            order_id: "bybit-proof-failure".into(),
            sent_ts_ms: po.sent_ts_ms,
            filled_qty: 0.0,
        }),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert_eq!(r.store.generation(), generation);
    assert!(p.exchange_submission_guard.storage_blocked());
    sqlx::raw_sql("DROP TRIGGER fail_proof ON trading.bybit_recovery")
        .execute(&pool)
        .await
        .unwrap();
    drop(r);
    let (_, _, s, _) = h2_start(&pool).await;
    assert!(s.pending_orders.contains_key("proof-failure"));
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_followup_stale_completion_retains_pending_guard() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    let po = h2_register(&mut r, &mut p, &mut s, "proof-stale", 0.1, false).await;
    let mut cancel = terminal_order_update("proof-stale", "Cancelled", "");
    cancel.side = "Buy".into();
    cancel.cum_exec_qty = "0.02".into();
    r.exchange(
        Some(ExchangeEvent::OrderUpdate(cancel)),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    r.exchange(
        Some(ExchangeEvent::ReconciliationCompleted {
            order_link_id: po.order_link_id.clone(),
            order_id: "bybit-proof-stale".into(),
            sent_ts_ms: po.sent_ts_ms,
            filled_qty: 0.0,
        }),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert!(p.exchange_submission_guard.blocks_entry());
    assert!(
        !s.pending_orders["proof-stale"]
            .progress
            .terminal_reconciliation_complete
    );
    drop(r);
    let (_, p, s, _) = h2_start(&pool).await;
    assert!(s.pending_orders.contains_key("proof-stale"));
    assert!(p.exchange_submission_guard.blocks_entry());
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_lastreview_runtime_cancel_keeps_rest_confirmation() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "runtime-cancel", 0.1, false).await;
    let mut cancel = terminal_order_update("runtime-cancel", "Cancelled", "");
    cancel.side = "Buy".into();
    r.exchange(
        Some(ExchangeEvent::OrderUpdate(cancel.clone())),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert!(
        s.pending_orders.contains_key("runtime-cancel"),
        "ordinary cancel must reach runtime REST scheduler"
    );
    let (checker, mut events) = super::super::dcp_reconciliation::DcpReconciler::fixture(vec![
        serde_json::json!({"list":[cancel],"nextPageCursor":""}),
    ]);
    checker.enable_recovery_events();
    s.dcp_reconciler = Some(checker);
    super::super::loop_tick::schedule_pending_reconciliation(
        &mut s,
        openclaw_core::now_ms() + 60000,
    );
    for _ in 0..2 {
        let event = tokio::time::timeout(std::time::Duration::from_secs(1), events.recv())
            .await
            .unwrap()
            .unwrap();
        r.exchange(Some(event), &mut p, &mut s, &mut w, None).await;
    }
    assert!(!s.pending_orders.contains_key("runtime-cancel"));
    let complete:bool=sqlx::query_scalar("SELECT (progress->'progress'->>'terminal_reconciliation_complete')::boolean FROM trading.bybit_order_intents WHERE order_link_id='runtime-cancel'").fetch_one(&pool).await.unwrap();
    assert!(complete);
    drop(r);
    let (_, _, s, _) = h2_start(&pool).await;
    assert!(!s.pending_orders.contains_key("runtime-cancel"));
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_lastreview_registration_failure_restores_projection_and_lease() {
    for lease_event in [false, true] {
        let pool = h2_pool().await;
        let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
        h2_register(&mut r, &mut p, &mut s, "reg-open", 0.1, false).await;
        r.exchange(
            Some(ExchangeEvent::Fill(h1_exec(
                "reg-open",
                "reg-open-exec",
                "0.1",
                "Buy",
            ))),
            &mut p,
            &mut s,
            &mut w,
            None,
        )
        .await;
        h2_register(&mut r, &mut p, &mut s, "reg-close", 0.1, true).await;
        p.governance.grant_paper_authorization(None).unwrap();
        let lease = p
            .governance
            .acquire_lease(
                "intent:reg-failure",
                "TRADE_ENTRY",
                60_000,
                GovernanceProfile::Production,
                "h2_fixture",
            )
            .unwrap();
        let LeaseId::Active(id) = lease else {
            panic!("fixture must have active lease")
        };
        sqlx::raw_sql("CREATE FUNCTION fail_reg() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture registration cutpoint'; END $$; CREATE TRIGGER fail_reg BEFORE UPDATE ON trading.bybit_recovery FOR EACH ROW EXECUTE FUNCTION fail_reg();").execute(&pool).await.unwrap();
        let event = if lease_event {
            PendingOrderEvent::ReleaseDecisionLease {
                order_link_id: "reg-close".into(),
                decision_lease_id: Some(id.clone()),
                outcome: openclaw_core::governance_core::LeaseOutcome::Consumed,
                reason: "fixture".into(),
                ts_ms: openclaw_core::now_ms(),
            }
        } else {
            PendingOrderEvent::ExchangeZeroClose {
                order_link_id: "reg-close".into(),
                symbol: "BTCUSDT".into(),
                is_long: true,
                strategy: "fixture".into(),
                ts_ms: openclaw_core::now_ms(),
            }
        };
        r.registration(Some(event), &mut p, &mut s, None).await;
        h2_accounting(&p, 0.1, 0.01, 0.0);
        assert!(s.pending_orders.contains_key("reg-close"));
        assert!(p.governance.get_lease_by_id(&id).is_ok());
        assert!(p.exchange_submission_guard.storage_blocked());
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_lastreview_unconfirmed_terminal_index_is_guarded() {
    let pool = h2_pool().await;
    let exists: bool =
        sqlx::query_scalar("SELECT to_regclass('trading.bybit_terminal_unconfirmed') IS NOT NULL")
            .fetch_one(&pool)
            .await
            .unwrap();
    assert!(
        exists,
        "unbounded history needs indexed unresolved predicate"
    );
    sqlx::raw_sql("DROP INDEX trading.bybit_terminal_unconfirmed; CREATE INDEX bybit_terminal_unconfirmed ON trading.bybit_order_intents(engine_mode,order_link_id);").execute(&pool).await.unwrap();
    let error = sqlx::raw_sql(H2_MIGRATION)
        .execute(&pool)
        .await
        .expect_err("wrong terminal predicate must fail");
    assert!(error.to_string().contains("Guard D"));
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_lastreview_failed_protective_delivery_replays_before_first_submit() {
    for channel_failed in [false, true] {
        let pool = h2_pool().await;
        let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
        h2_register(&mut r, &mut p, &mut s, "outbox-open", 0.1, false).await;
        r.exchange(
            Some(ExchangeEvent::Fill(h1_exec(
                "outbox-open",
                "outbox-open-exec",
                "0.1",
                "Buy",
            ))),
            &mut p,
            &mut s,
            &mut w,
            None,
        )
        .await;
        let mut po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
        po.order_link_id = "outbox-parent".into();
        po.is_close = true;
        po.is_long = false;
        po.qty = 0.1;
        po.limit_price = Some(50000.0);
        po.close_maker_audit = Some(CloseMakerFillAudit {
            initial_limit_price: Some(50000.0),
            eligible_reason: "fixture-close".into(),
            fallback_reason: None,
            rate_limit_scope: None,
        });
        let (ready, rx) = tokio::sync::oneshot::channel();
        r.registration(
            Some(PendingOrderEvent::RegisterBeforeSubmit {
                request: {
                    let mut request = h2_request(&po);
                    request.order_type = crate::order_manager::OrderType::Limit;
                    request.price = Some(50000.0);
                    request
                },
                order: po.clone(),
                ready,
            }),
            &mut p,
            &mut s,
            None,
        )
        .await;
        rx.await.unwrap();
        let (closed_tx, mut closed_rx) = tokio::sync::mpsc::unbounded_channel();
        if channel_failed {
            closed_rx.close();
        }
        p.set_shadow_channel(closed_tx);
        r.exchange(
            Some(ExchangeEvent::OrderUpdate(terminal_order_update(
                "outbox-parent",
                "Cancelled",
                "",
            ))),
            &mut p,
            &mut s,
            &mut w,
            None,
        )
        .await;
        assert_eq!(
            p.exchange_submission_guard.storage_blocked(),
            channel_failed
        );
        let original_id = if channel_failed {
            None
        } else {
            Some(closed_rx.try_recv().unwrap().order_link_id)
        };
        drop(r);
        let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10000.0, PipelineKind::Demo);
        let mut s = make_loop_state();
        let mut w = super::make_test_writer();
        let (tx, mut requests) = tokio::sync::mpsc::unbounded_channel();
        p.set_shadow_channel(tx);
        let mut r = ExecutionRecovery::open(&pool, "demo", "fixture-account", &mut p, &mut s)
            .await
            .unwrap();
        r.recover(&mut p, &mut s, &mut w, None).await.unwrap();
        let req = tokio::time::timeout(std::time::Duration::from_millis(100), requests.recv())
            .await
            .expect("committed protective request must survive failed channel delivery")
            .unwrap();
        if let Some(id) = original_id {
            assert_eq!(
                req.order_link_id, id,
                "restart retains the exact unsent intent identity"
            );
        }
        assert!(req.is_close && req.is_primary);
        assert_eq!(req.qty, 0.1);
        assert!(req
            .close_maker_audit
            .as_ref()
            .unwrap()
            .fallback_reason
            .is_some());
        po.order_link_id = req.order_link_id.clone();
        po.sent_ts_ms = req.paper_fill_ts;
        po.order_type = "market".into();
        po.time_in_force = None;
        po.limit_price = None;
        po.close_maker_audit = req.close_maker_audit.clone();
        let (ready, rx) = tokio::sync::oneshot::channel();
        r.registration(
            Some(PendingOrderEvent::RegisterBeforeSubmit {
                request: h2_request(&po),
                order: po,
                ready,
            }),
            &mut p,
            &mut s,
            None,
        )
        .await;
        rx.await.unwrap();
        drop(r);
        let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10000.0, PipelineKind::Demo);
        let mut s = make_loop_state();
        let (tx, mut requests) = tokio::sync::mpsc::unbounded_channel();
        p.set_shadow_channel(tx);
        let mut r = ExecutionRecovery::open(&pool, "demo", "fixture-account", &mut p, &mut s)
            .await
            .unwrap();
        r.recover(&mut p, &mut s, &mut w, None).await.unwrap();
        assert!(
            requests.try_recv().is_err(),
            "registered immutable intent cannot be resubmitted"
        );
    }
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_lastreview_zero_position_receipt_keeps_execution_accounting() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "zero-open", 0.1, false).await;
    r.exchange(
        Some(ExchangeEvent::Fill(h1_exec(
            "zero-open",
            "zero-open-exec",
            "0.1",
            "Buy",
        ))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    h2_register(&mut r, &mut p, &mut s, "zero-close", 0.1, true).await;
    r.registration(
        Some(PendingOrderEvent::ExchangeZeroClose {
            order_link_id: "zero-close".into(),
            symbol: "BTCUSDT".into(),
            is_long: true,
            strategy: "fixture".into(),
            ts_ms: openclaw_core::now_ms(),
        }),
        &mut p,
        &mut s,
        None,
    )
    .await;
    h2_accounting(&p, 0.1, 0.01, 0.0);
    assert!(s.pending_orders.contains_key("zero-close"));
    assert!(p.exchange_submission_guard.blocks_entry());
    drop(r);
    let (_, p, s, _) = h2_start(&pool).await;
    h2_accounting(&p, 0.1, 0.01, 0.0);
    assert!(s.pending_orders.contains_key("zero-close"));
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_lastreview_failed_fallback_commit_discards_outbox_reservation() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "failed-outbox-open", 0.1, false).await;
    r.exchange(
        Some(ExchangeEvent::Fill(h1_exec(
            "failed-outbox-open",
            "failed-outbox-open-exec",
            "0.1",
            "Buy",
        ))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    let mut po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    po.order_link_id = "failed-outbox-parent".into();
    po.is_close = true;
    po.is_long = false;
    po.qty = 0.1;
    po.limit_price = Some(50000.0);
    po.close_maker_audit = Some(CloseMakerFillAudit {
        initial_limit_price: Some(50000.0),
        eligible_reason: "fixture-close".into(),
        fallback_reason: None,
        rate_limit_scope: None,
    });
    let mut request = h2_request(&po);
    request.order_type = crate::order_manager::OrderType::Limit;
    request.price = Some(50000.0);
    let (ready, rx) = tokio::sync::oneshot::channel();
    r.registration(
        Some(PendingOrderEvent::RegisterBeforeSubmit {
            request,
            order: po,
            ready,
        }),
        &mut p,
        &mut s,
        None,
    )
    .await;
    rx.await.unwrap();
    let (tx, mut requests) = tokio::sync::mpsc::unbounded_channel();
    p.set_shadow_channel(tx);
    sqlx::raw_sql("CREATE FUNCTION fail_outbox() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN RAISE EXCEPTION 'fixture outbox cutpoint'; END $$; CREATE TRIGGER fail_outbox BEFORE UPDATE ON trading.bybit_recovery FOR EACH ROW EXECUTE FUNCTION fail_outbox();").execute(&pool).await.unwrap();
    r.exchange(
        Some(ExchangeEvent::OrderUpdate(terminal_order_update(
            "failed-outbox-parent",
            "Cancelled",
            "",
        ))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    assert!(requests.try_recv().is_err());
    assert!(p.recovery_dispatch_outbox.is_empty());
    assert!(!s
        .close_maker_fallback_dispatched
        .contains("failed-outbox-parent"));
    assert!(s.pending_orders.contains_key("failed-outbox-parent"));
    assert!(p.exchange_submission_guard.storage_blocked());
    p.exchange_submission_guard.block_storage(false);
    p.exchange_submission_guard.resolve("failed-outbox-parent");
    assert!(
        !p.exchange_submission_guard.blocks_entry(),
        "rolled-back request cannot leak a queued reservation"
    );
    let checkpoint: serde_json::Value = sqlx::query_scalar(
        "SELECT checkpoint FROM trading.bybit_recovery WHERE engine_mode='demo'",
    )
    .fetch_one(&pool)
    .await
    .unwrap();
    assert!(checkpoint["dispatch_outbox"]
        .as_object()
        .unwrap()
        .is_empty());
}

#[tokio::test]
#[ignore = "requires explicit isolated PostgreSQL fixture"]
async fn h2_lastreview_timer_fallback_uses_same_durable_boundary() {
    let pool = h2_pool().await;
    let (mut r, mut p, mut s, mut w) = h2_start(&pool).await;
    h2_register(&mut r, &mut p, &mut s, "timer-outbox-open", 0.1, false).await;
    r.exchange(
        Some(ExchangeEvent::Fill(h1_exec(
            "timer-outbox-open",
            "timer-outbox-open-exec",
            "0.1",
            "Buy",
        ))),
        &mut p,
        &mut s,
        &mut w,
        None,
    )
    .await;
    let mut po = baseline_pending_order("limit", Some(TimeInForce::PostOnly));
    po.order_link_id = "timer-outbox-parent".into();
    po.is_close = true;
    po.is_long = false;
    po.qty = 0.1;
    po.limit_price = Some(50000.0);
    po.close_maker_audit = Some(CloseMakerFillAudit {
        initial_limit_price: Some(50000.0),
        eligible_reason: "fixture-close".into(),
        fallback_reason: None,
        rate_limit_scope: None,
    });
    let mut request = h2_request(&po);
    request.order_type = crate::order_manager::OrderType::Limit;
    request.price = Some(50000.0);
    let (ready, rx) = tokio::sync::oneshot::channel();
    r.registration(
        Some(PendingOrderEvent::RegisterBeforeSubmit {
            request,
            order: po.clone(),
            ready,
        }),
        &mut p,
        &mut s,
        None,
    )
    .await;
    rx.await.unwrap();
    let (tx, requests) = tokio::sync::mpsc::unbounded_channel();
    p.set_shadow_channel(tx);
    let _ = r
        .control_event(&mut p, &mut s, move |p, s| {
            assert!(
                super::super::loop_handlers::dispatch_close_maker_fallback_from_pending(
                    s,
                    p,
                    &po,
                    crate::strategies::maker_rejection::CloseMakerFallbackReason::TimeoutTaker,
                    None,
                    "confirmation_timer"
                )
            );
            drop(requests);
        })
        .await;
    drop(r);
    let mut p = TickPipeline::with_kind(&["BTCUSDT"], 10000.0, PipelineKind::Demo);
    let mut s = make_loop_state();
    let (tx, mut requests) = tokio::sync::mpsc::unbounded_channel();
    p.set_shadow_channel(tx);
    let mut r = ExecutionRecovery::open(&pool, "demo", "fixture-account", &mut p, &mut s)
        .await
        .unwrap();
    r.recover(&mut p, &mut s, &mut w, None).await.unwrap();
    assert!(
        requests.try_recv().is_ok(),
        "timer path must persist protective request before its marker"
    );
}
