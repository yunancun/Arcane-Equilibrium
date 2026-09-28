//! Dispatch retry policy tests.

use super::*;
use crate::bybit_rest_client::BybitApiError;
use crate::order_manager::TimeInForce;
use crate::tick_pipeline::{CloseMakerFillAudit, OrderDispatchRequest};
use serde_json::json;

/// Build a Business error helper for tests.
/// 測試輔助：構造 Business 錯誤。
fn biz(ret_code: i64, ret_msg: &str) -> BybitApiError {
    BybitApiError::Business {
        ret_code,
        ret_msg: ret_msg.to_string(),
        response: json!({"retCode": ret_code, "retMsg": ret_msg}),
    }
}

fn close_maker_dispatch_req(
    order_type: &str,
    time_in_force: Option<TimeInForce>,
    close_maker_audit: Option<CloseMakerFillAudit>,
) -> OrderDispatchRequest {
    OrderDispatchRequest {
        symbol: "BTCUSDT".into(),
        is_long: false,
        qty: 0.1,
        price: 50_000.0,
        strategy: "strategy_close:grid_close_long".into(),
        paper_fill_ts: 1_700_000_000_000,
        is_close: true,
        order_link_id: "oc_close_maker_preflight".into(),
        decision_lease_id: None,
        is_primary: true,
        stop_loss: None,
        take_profit: None,
        context_id: "ctx-close-maker".into(),
        order_type: order_type.to_string(),
        limit_price: Some(50_000.2).filter(|_| order_type == "limit"),
        time_in_force,
        maker_timeout_ms: time_in_force.and(Some(30_000)),
        close_maker_audit,
        reference_price: Some(50_000.0),
        reference_ts_ms: Some(1_700_000_000_000),
        reference_source: Some("dispatch_last_fallback".into()),
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
        // P2-ORDERS-INTENT-ID-WRITER-GAP-1（2026-05-19）：close-maker dispatch
        // 為 close path，無上游 strategy intent，保 None。
        intent_id: None,
        // MAKER-CLOSE-REPRICE-1：test fixture 預設未重掛。
        reprice_count: 0,
    }
}

#[test]
fn test_close_maker_preflight_failure_emits_dispatch_failed_event() {
    let (tx, mut rx) = mpsc::unbounded_channel::<PendingOrderEvent>();
    let req = close_maker_dispatch_req("limit", Some(TimeInForce::PostOnly), None);

    send_close_maker_dispatch_failed(&tx, &req, "Rejected", "dispatch_preflight_qty_zero");

    match rx.try_recv().expect("dispatch failed event") {
        PendingOrderEvent::DispatchFailed {
            order_link_id,
            symbol,
            order_type,
            time_in_force,
            close_maker_audit,
            reason,
            ..
        } => {
            assert_eq!(order_link_id, "oc_close_maker_preflight");
            assert_eq!(symbol, "BTCUSDT");
            assert_eq!(order_type, "limit");
            assert_eq!(time_in_force, Some(TimeInForce::PostOnly));
            assert_eq!(reason, "dispatch_preflight_qty_zero");
            let audit = close_maker_audit.expect("derived close-maker audit");
            assert_eq!(audit.eligible_reason, "grid_close_long");
            assert_eq!(audit.fallback_reason, None);
        }
        other => panic!("expected DispatchFailed, got {other:?}"),
    }
}

#[test]
fn test_close_maker_fallback_market_preflight_failure_emits_terminal_event() {
    let (tx, mut rx) = mpsc::unbounded_channel::<PendingOrderEvent>();
    let req = close_maker_dispatch_req(
        "market",
        None,
        Some(CloseMakerFillAudit {
            initial_limit_price: Some(50_000.2),
            eligible_reason: "grid_close_long".into(),
            fallback_reason: Some("postonly_reject".into()),
            rate_limit_scope: None,
        }),
    );

    send_close_maker_dispatch_failed(&tx, &req, "Rejected", "dispatch_preflight_min_notional");

    match rx.try_recv().expect("dispatch failed event") {
        PendingOrderEvent::DispatchFailed {
            order_type,
            time_in_force,
            close_maker_audit,
            reason,
            ..
        } => {
            assert_eq!(order_type, "market");
            assert_eq!(time_in_force, None);
            assert_eq!(reason, "dispatch_preflight_min_notional");
            let audit = close_maker_audit.expect("fallback market audit");
            assert_eq!(audit.fallback_reason.as_deref(), Some("postonly_reject"));
        }
        other => panic!("expected DispatchFailed, got {other:?}"),
    }
}

#[test]
fn test_110072_does_not_trigger_local_position_convergence() {
    // BB MANDATORY guard：110072 與 110017 不同，**不**觸發本地倉收斂。
    // 鎖定 noop_is_exchange_zero_position 對 110072 回 false（110072 絕不可
    // 加入收斂集；倉位真相由首次成功 attempt 的 WS fill/position update 回填）。
    assert!(
        !noop_is_exchange_zero_position(&biz(110072, "OrderLinkedID is duplicate")),
        "110072 must NOT trigger ExchangeZeroClose local convergence (only 110017 converges)"
    );
}

#[test]
fn test_10001_duplicate_does_not_trigger_local_position_convergence() {
    // 與 110072 一致：10001+duplicate **不**觸發本地倉收斂（只有 110017 收斂）。
    // 鎖定 noop_is_exchange_zero_position 對 10001 回 false。
    assert!(
        !noop_is_exchange_zero_position(&biz(10001, "duplicate order_link_id rejected")),
        "10001+duplicate must NOT trigger ExchangeZeroClose local convergence (only 110017 converges)"
    );
}

#[test]
fn test_open_retry_budget_unchanged_after_110072_change() {
    // 回歸錨點（BB guard 可追溯）：110072 改動不得碰 open retry 預算。
    // open/create 仍是空 slice（0 重試）；110072 的冪等 upgrade 是 NoOp-style
    // 成功收尾，**不**是 retry（NoOp ≠ retry）。亦由
    // test_dispatch_retry_delays_helper_open_is_empty_close_is_bounded 覆蓋，
    // 此處顯式重申以鎖定 BB OPEN_NO_RETRY 不變量。
    assert_eq!(
        dispatch_retry_delays_for_intent(false),
        OPEN_NO_RETRY.as_slice()
    );
    assert!(dispatch_retry_delays_for_intent(false).is_empty());
}

// -----------------------------------------------------------------
// P1-110017-POSITION-DRIFT-CLOSE-LOOP：send_exchange_zero_close guard tests
// 110017 reduce-only close → ExchangeZeroClose 收斂事件的觸發/抑制守衛
// -----------------------------------------------------------------

/// 構造一筆 reduce-only 平倉 OrderDispatchRequest（market），預設 is_primary。
/// `is_primary` / `is_close` / `qty` 由參數覆寫以驗 guard。
/// qty=0.0 = 全平 form（qty=0 + reduceOnly + closeOnTrigger）；qty>0 = partial
/// reduce-only close（用於 C-1 安全測試，BB 要求此情況收 110017 絕不收斂）。
fn close_dispatch_req_for_zero(is_primary: bool, is_close: bool, qty: f64) -> OrderDispatchRequest {
    OrderDispatchRequest {
        symbol: "TRXUSDT".into(),
        is_long: true,
        qty,
        price: 0.342,
        // RUST-DOUBLE-PREFIX-1：PHYS-LOCK reason 須經 build_risk_close_tag 構造，
        // 不可裸寫 "risk_close:phys_lock_" literal（guard test 強制）。
        strategy: crate::tick_pipeline::build_risk_close_tag("phys_lock_gate4_giveback"),
        paper_fill_ts: 1_700_000_000_000,
        is_close,
        order_link_id: "oc_risk_dm_zero".into(),
        decision_lease_id: None,
        is_primary,
        stop_loss: None,
        take_profit: None,
        context_id: "ctx-trx".into(),
        order_type: "market".into(),
        limit_price: None,
        time_in_force: None,
        maker_timeout_ms: None,
        close_maker_audit: None,
        reference_price: Some(0.342),
        reference_ts_ms: Some(1_700_000_000_000),
        reference_source: Some("dispatch_last_fallback".into()),
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
        intent_id: None,
        // MAKER-CLOSE-REPRICE-1：test fixture 預設未重掛。
        reprice_count: 0,
    }
}

#[test]
fn test_send_exchange_zero_close_emits_on_primary_close_110017() {
    // 主路徑：primary reduce-only close + 110017 → 發 ExchangeZeroClose，
    // 攜帶 symbol / is_long / strategy / order_link_id 供 consumer 本地收斂。
    let (tx, mut rx) = mpsc::unbounded_channel::<PendingOrderEvent>();
    let req = close_dispatch_req_for_zero(true, true, 0.0);
    let err = biz(110017, "current position is zero");
    send_exchange_zero_close(&tx, &req, &err);

    match rx.try_recv().expect("ExchangeZeroClose event") {
        PendingOrderEvent::ExchangeZeroClose {
            order_link_id,
            symbol,
            is_long,
            strategy,
            ..
        } => {
            assert_eq!(order_link_id, "oc_risk_dm_zero");
            assert_eq!(symbol, "TRXUSDT");
            assert!(is_long);
            assert_eq!(
                strategy,
                crate::tick_pipeline::build_risk_close_tag("phys_lock_gate4_giveback")
            );
        }
        other => panic!("expected ExchangeZeroClose, got {other:?}"),
    }
}

#[test]
fn test_send_exchange_zero_close_suppressed_for_110001() {
    // 回歸守衛：110001（order not exists）雖也是 NoOp，但不觸發本地收斂事件
    // （只有 110017 = exchange position zero 才收斂）。
    let (tx, mut rx) = mpsc::unbounded_channel::<PendingOrderEvent>();
    let req = close_dispatch_req_for_zero(true, true, 0.0);
    send_exchange_zero_close(&tx, &req, &biz(110001, "order not exists"));
    assert!(
        rx.try_recv().is_err(),
        "110001 must NOT emit ExchangeZeroClose (only 110017 converges)"
    );
}

#[test]
fn test_send_exchange_zero_close_suppressed_for_non_primary() {
    // 安全 guard：paper shadow（is_primary=false）即使收 110017 也不收斂
    // 真倉（shadow 路徑 fire-and-forget，無交易所倉位）。
    let (tx, mut rx) = mpsc::unbounded_channel::<PendingOrderEvent>();
    let req = close_dispatch_req_for_zero(false, true, 0.0);
    send_exchange_zero_close(&tx, &req, &biz(110017, "current position is zero"));
    assert!(
        rx.try_recv().is_err(),
        "non-primary (paper shadow) must NOT emit ExchangeZeroClose"
    );
}

#[test]
fn test_send_exchange_zero_close_suppressed_for_non_close() {
    // 安全 guard：非 close（open）方向即使理論上收 110017 也不收斂 —— 收斂
    // 僅限 reduce-only close 路徑（誤刪真倉是災難，保守 fail-closed）。
    let (tx, mut rx) = mpsc::unbounded_channel::<PendingOrderEvent>();
    let req = close_dispatch_req_for_zero(true, false, 0.0);
    send_exchange_zero_close(&tx, &req, &biz(110017, "current position is zero"));
    assert!(
        rx.try_recv().is_err(),
        "non-close intent must NOT emit ExchangeZeroClose"
    );
}

#[test]
fn test_send_exchange_zero_close_suppressed_for_qty_gt_zero_partial_close() {
    // BB MANDATORY GUARD C-1 安全測試（最關鍵）：partial reduce-only close
    // （qty>0 但 > 實際倉量）收到 110017 時，交易所端倉**可能仍在**——110017
    // 此情況是 (c) qty>position size 觸發，不是「無倉」。若收斂 = 誤刪真倉
    // （災難）。故 qty>0 的 primary reduce-only close + 110017 必須 **不** 發
    // ExchangeZeroClose（本地倉保留，維持 NoOp/no-retry 即可）。
    //
    // 對抗驗證：若 send_exchange_zero_close 拿掉 `is_qty_zero_full_close` guard，
    // 此測試應 FAIL（會誤發收斂事件）——證明 qty==0 guard 是有效防誤刪屏障。
    let (tx, mut rx) = mpsc::unbounded_channel::<PendingOrderEvent>();
    let req = close_dispatch_req_for_zero(true, true, 5.0); // qty>0 partial close
    send_exchange_zero_close(&tx, &req, &biz(110017, "current position is zero"));
    assert!(
        rx.try_recv().is_err(),
        "qty>0 partial reduce-only close + 110017 must NOT converge (position may still exist; C-1 anti-mis-delete guard)"
    );
}

#[test]
fn test_send_exchange_zero_close_emits_only_on_qty_zero_full_close() {
    // 正反對照：同為 primary reduce-only close + 110017，qty==0 全平 form 收斂、
    // qty>0 partial close 不收斂。鎖定「qty==0 form 是收斂的 mandatory 前提」。
    let err = biz(110017, "current position is zero");

    let (tx0, mut rx0) = mpsc::unbounded_channel::<PendingOrderEvent>();
    send_exchange_zero_close(&tx0, &close_dispatch_req_for_zero(true, true, 0.0), &err);
    assert!(
        rx0.try_recv().is_ok(),
        "qty==0 full-close form must converge"
    );

    let (tx1, mut rx1) = mpsc::unbounded_channel::<PendingOrderEvent>();
    send_exchange_zero_close(&tx1, &close_dispatch_req_for_zero(true, true, 5.0), &err);
    assert!(
        rx1.try_recv().is_err(),
        "qty>0 partial close must NOT converge"
    );
}

#[tokio::test]
async fn h1_open_timeout_is_one_attempt_and_emits_only_unknown() {
    let mut req = close_maker_dispatch_req("market", None, None);
    req.is_close = false;
    let (tx, mut rx) = mpsc::unbounded_channel();
    let mut calls = 0;
    let result: DispatchRetryResult<()> = run_dispatch_retry(
        dispatch_retry_delays_for_intent(false),
        &req.symbol,
        &req.order_link_id,
        |_| {
            calls += 1;
            std::future::ready(Err(close_dispatch_timeout_error(500)))
        },
    )
    .await;
    let DispatchRetryResult::TransientExhausted { attempts, .. } = result else {
        panic!("must stay unresolved");
    };
    assert_eq!((calls, attempts), (1, 1));
    send_submission_unknown(&tx, &req, "dispatch_transient_exhausted".into());
    assert!(matches!(
        rx.try_recv(),
        Ok(PendingOrderEvent::SubmissionUnknown { .. })
    ));
    assert!(
        rx.try_recv().is_err(),
        "no terminal failure or lease release"
    );
}

#[tokio::test]
async fn h1_close_timeout_has_only_three_attempts() {
    let mut calls = 0;
    let result: DispatchRetryResult<()> = run_dispatch_retry(
        dispatch_retry_delays_for_intent(true),
        "BTCUSDT",
        "same-close-id",
        |_| {
            calls += 1;
            std::future::ready(Err(close_dispatch_timeout_error(500)))
        },
    )
    .await;
    assert!(matches!(
        result,
        DispatchRetryResult::TransientExhausted { attempts: 3, .. }
    ));
    assert_eq!(calls, 3);
}

#[tokio::test]
async fn h1_duplicate_requires_prior_transport_ambiguity() {
    for (code, message) in [(110072, "duplicate"), (10001, "duplicate orderLinkId")] {
        for prior_unknown in [false, true] {
            let mut calls = 0;
            let result =
                run_dispatch_retry::<(), _, _>(&[0, 0], "BTCUSDT", "duplicate-close", |_| {
                    calls += 1;
                    std::future::ready(Err(if prior_unknown && calls == 1 {
                        close_dispatch_timeout_error(500)
                    } else {
                        biz(code, message)
                    }))
                })
                .await;
            let DispatchRetryResult::Structural {
                outcome_unknown,
                attempts,
                last_error,
            } = result
            else {
                panic!("duplicate must be structural");
            };
            assert_eq!(outcome_unknown, prior_unknown);
            assert_eq!(attempts, if prior_unknown { 2 } else { 1 });
            if !outcome_unknown {
                let req = close_dispatch_req_for_zero(true, true, 0.01);
                let (tx, mut rx) = mpsc::unbounded_channel();
                send_definitive_dispatch_rejection(&tx, &req, &last_error, attempts);
                assert!(
                    matches!(rx.try_recv(), Ok(PendingOrderEvent::DispatchFailed { terminal_status, .. }) if terminal_status == "Rejected")
                );
            }
        }
    }
}

#[test]
fn h1_definitive_rejection_emits_terminal_and_failed_lease() {
    for (is_close, code) in [(false, 10006), (false, 110072), (true, 110017)] {
        let mut req = close_dispatch_req_for_zero(true, is_close, 0.01);
        req.decision_lease_id = Some("h1-rejected-lease".into());
        let (tx, mut rx) = mpsc::unbounded_channel();
        send_definitive_dispatch_rejection(&tx, &req, &biz(code, "rejected"), 1);
        assert!(matches!(
            rx.try_recv(),
            Ok(PendingOrderEvent::DispatchFailed { terminal_status, .. })
                if terminal_status == "Rejected"
        ));
        assert!(matches!(
            rx.try_recv(),
            Ok(PendingOrderEvent::ReleaseDecisionLease {
                outcome: LeaseOutcome::Failed,
                ..
            })
        ));
        assert!(
            rx.try_recv().is_err(),
            "definitive refusal must not emit Unknown"
        );
    }
}

#[tokio::test]
async fn h1_definitive_rate_limit_is_not_submission_ambiguity() {
    for delays in [&OPEN_NO_RETRY[..], &[0, 0][..]] {
        let result = run_dispatch_retry::<(), _, _>(delays, "BTCUSDT", "h1-rate", |_| {
            std::future::ready(Err(BybitApiError::Business {
                ret_code: 10006,
                ret_msg: "rate limited".into(),
                response: serde_json::json!({}),
            }))
        })
        .await;
        assert!(matches!(
            result,
            DispatchRetryResult::TransientExhausted {
                outcome_unknown: false,
                ..
            }
        ));
    }
    let result = run_dispatch_retry::<(), _, _>(&[0], "BTCUSDT", "h1-mixed", |attempt| {
        std::future::ready(Err(if attempt == 0 {
            close_dispatch_timeout_error(500)
        } else {
            BybitApiError::Business {
                ret_code: 10006,
                ret_msg: "rate limited".into(),
                response: serde_json::json!({}),
            }
        }))
    })
    .await;
    assert!(matches!(
        result,
        DispatchRetryResult::TransientExhausted {
            outcome_unknown: true,
            ..
        }
    ));
}
