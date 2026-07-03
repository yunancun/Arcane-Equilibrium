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
fn test_close_dup_is_idempotent_success_close_110072_true() {
    // close req（is_close=true）+ 110072 → 冪等成功（首次 close attempt 已達
    // Bybit、response 丟失，retry 重發同一 order_link_id 撞此碼）。
    let req = close_dispatch_req_for_zero(true, true, 0.0);
    let err = biz(110072, "OrderLinkedID is duplicate");
    assert!(
        close_dup_is_idempotent_success(&req, &err),
        "close + 110072 應判為冪等成功"
    );
}

#[test]
fn test_close_dup_is_idempotent_success_open_110072_false() {
    // BB MANDATORY guard 關鍵測試：open req（is_close=false）+ 110072 → false。
    // open 單次無重試（OPEN_NO_RETRY），撞 110072 只可能是 id 撞歷史 = 開倉
    // 未成功，絕不可當成功（會掩蓋未開倉的真相）。
    // 對抗驗證：若 close_dup_is_idempotent_success 拿掉 `req.is_close` guard，
    // 此測試應 FAIL（open 110072 會被誤判為成功）——證明 is_close guard 是
    // open path fail-closed 的有效屏障。
    let req = close_dispatch_req_for_zero(true, false, 0.0); // is_close=false (open)
    let err = biz(110072, "OrderLinkedID is duplicate");
    assert!(
        !close_dup_is_idempotent_success(&req, &err),
        "open + 110072 絕不可當成功（id 撞歷史 = 開倉未成功）"
    );
}

#[test]
fn test_close_dup_is_idempotent_success_other_retcode_false() {
    // close req + 其他業務碼（如 110001 或 110009）→ false。僅 110072 觸發此冪等路徑；
    // 110001 走既有 NoOp；110009 為 stop-order limit Structural，不走冪等 upgrade。
    let req = close_dispatch_req_for_zero(true, true, 0.0);
    assert!(
        !close_dup_is_idempotent_success(&req, &biz(110001, "order not exists")),
        "close + 110001 不是 110072 冪等成功"
    );
    assert!(
        !close_dup_is_idempotent_success(
            &req,
            &biz(
                110009,
                "The number of stop orders exceeds the maximum allowable limit"
            )
        ),
        "close + 110009 是 stop-order limit failure，不是 110072 冪等成功"
    );
    assert!(
        !close_dup_is_idempotent_success(&req, &biz(110012, "insufficient available balance")),
        "close + 110012 不是 110072 冪等成功"
    );
}

#[test]
fn test_close_dup_is_idempotent_success_non_business_error_false() {
    // close req + 非 Business err（如 NoCredentials / Other client-side fault）
    // → false。冪等 upgrade 僅認 Bybit Business retCode 110072；非交易所回應的
    // client 端錯誤（配置/分頁不變式違反）維持 fail-closed。
    let req = close_dispatch_req_for_zero(true, true, 0.0);
    assert!(
        !close_dup_is_idempotent_success(&req, &BybitApiError::NoCredentials),
        "close + NoCredentials 不是 110072 冪等成功"
    );
    assert!(
        !close_dup_is_idempotent_success(
            &req,
            &BybitApiError::Other("pagination cursor stalled".into())
        ),
        "close + Other(client-side) 不是 110072 冪等成功"
    );
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

// ── 2026-06-07 follow-up（E2/BB flag）：close_dup_is_idempotent_success 擴
// 涵蓋 10001+duplicate（與 110072 同類「重複 order_link_id」）──

#[test]
fn test_close_dup_is_idempotent_success_close_10001_duplicate_true() {
    // close req（is_close=true）+ 10001+"duplicate" → 冪等成功。與 110072 同類：
    // 首次 close attempt 已達 Bybit、response 丟失，retry 重發同一 id 撞此泛碼。
    let req = close_dispatch_req_for_zero(true, true, 0.0);
    let err = biz(10001, "duplicate order_link_id rejected");
    assert!(
        close_dup_is_idempotent_success(&req, &err),
        "close + 10001+duplicate 應判為冪等成功"
    );
    // 大小寫不敏感（helper 用 to_ascii_lowercase）：uppercase 變體同樣 true。
    let err_upper = biz(10001, "Duplicate orderLinkId rejected");
    assert!(
        close_dup_is_idempotent_success(&req, &err_upper),
        "close + 10001+Duplicate（大寫）應判為冪等成功"
    );
}

#[test]
fn test_close_dup_is_idempotent_success_open_10001_duplicate_false() {
    // **open path fail-closed 關鍵測試**：open req（is_close=false）+ 10001+duplicate
    // → false。open 單次無重試（OPEN_NO_RETRY），撞重複 order_link_id 只可能是
    // id 撞歷史 = 開倉未成功，絕不可當成功（這正是 follow-up 收斂的 silent-success
    // 漏洞）。對抗驗證：若 helper 拿掉 `req.is_close` guard，此測試應 FAIL。
    let req = close_dispatch_req_for_zero(true, false, 0.0); // is_close=false (open)
    let err = biz(10001, "duplicate order_link_id rejected");
    assert!(
        !close_dup_is_idempotent_success(&req, &err),
        "open + 10001+duplicate 絕不可當成功（id 撞歷史 = 開倉未成功）"
    );
}

#[test]
fn test_close_dup_is_idempotent_success_close_10001_non_duplicate_false() {
    // close req + 10001 但 retMsg **不含** "duplicate"（真結構性錯誤，如格式錯/
    // qty 非法）→ false。verifies helper 對 10001 仍需 retMsg 比對，不把所有
    // 10001 當冪等成功（否則會掩蓋真正壞掉的 close 請求）。
    let req = close_dispatch_req_for_zero(true, true, 0.0);
    assert!(
        !close_dup_is_idempotent_success(&req, &biz(10001, "invalid order_link_id format")),
        "close + 10001+非duplicate（格式錯）不是冪等成功"
    );
    assert!(
        !close_dup_is_idempotent_success(&req, &biz(10001, "invalid param: qty must be > 0")),
        "close + 10001+非duplicate（qty 非法）不是冪等成功"
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
    assert_eq!(dispatch_retry_delays_for_intent(false), OPEN_NO_RETRY.as_slice());
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
