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
fn test_retry_delay_constants() {
    // Lock in the retry budget: 3 retries with exponential backoff 200/800/3200 ms.
    // 鎖定重試預算：3 次重試，指數退避 200/800/3200 ms。
    assert_eq!(RETRY_DELAY_MS, [200u64, 800, 3200]);
    assert_eq!(RETRY_DELAY_MS.len(), 3);
}

#[test]
fn test_classify_transport_error() {
    // Deterministic construction of a reqwest::Error without real network I/O:
    // issue a `send()` with a 1 ns timeout against localhost; it reliably errors
    // out via the reqwest timeout/builder pipeline. We use a dedicated
    // current-thread runtime so the test remains synchronous.
    //
    // 不走真實網路的確定性 reqwest::Error 構造：對 localhost 用 1 ns timeout 的
    // send() — 可靠觸發 reqwest timeout/builder 錯誤。使用專用 current-thread
    // runtime 使測試保持同步。
    let rt = tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .unwrap();
    let result = rt.block_on(async {
        reqwest::Client::builder()
            .timeout(Duration::from_nanos(1))
            .build()
            .unwrap()
            .get("http://127.0.0.1:1/")
            .send()
            .await
    });
    let err = result.expect_err("1 ns timeout must produce a reqwest::Error");
    let api_err: BybitApiError = BybitApiError::Transport(err);
    assert_eq!(
        classify_dispatch_error(&api_err),
        DispatchOutcome::Transient
    );
}

#[test]
fn test_classify_json_parse_error() {
    let parse_err: serde_json::Error = serde_json::from_str::<serde_json::Value>("not-json")
        .err()
        .unwrap();
    let api_err: BybitApiError = BybitApiError::JsonParse(parse_err);
    assert_eq!(
        classify_dispatch_error(&api_err),
        DispatchOutcome::Transient
    );
}

#[test]
fn test_classify_no_credentials() {
    let e = BybitApiError::NoCredentials;
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_signing_error() {
    let e = BybitApiError::SigningError("bad HMAC".into());
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_ip_rate_limit_is_transient() {
    let e = biz(10006, "Too many requests");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Transient);
}

#[test]
fn test_classify_duplicate_order_link_id_is_noop() {
    let e = biz(10001, "duplicate order_link_id rejected");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
}

#[test]
fn test_classify_invalid_param_is_structural() {
    let e = biz(10001, "invalid param: qty must be > 0");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_api_key_invalid_is_structural() {
    let e = biz(10003, "api key invalid");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_order_not_found_is_noop() {
    let e = biz(110001, "order not exists");
    // NoOp — retry cannot resurrect a missing order identity, and on close
    // attempts the position is effectively already gone. Classifier is
    // direction-symmetric (DISPATCH-RETRY-1 Q3 2026-04-19).
    //
    // NoOp — 重試無法救回已消失的訂單識別，且關倉時倉位實際已消失。
    // 分類器在方向上對稱（DISPATCH-RETRY-1 Q3 2026-04-19）。
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
}

#[test]
fn test_classify_position_not_found_is_noop() {
    let e = biz(110009, "position idx not match");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
}

#[test]
fn test_classify_insufficient_balance_is_structural() {
    let e = biz(110012, "insufficient available balance");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_leverage_not_modified_is_noop() {
    let e = biz(110043, "leverage not modified");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
}

#[test]
fn test_classify_dust_min_qty_is_structural() {
    let e = biz(170124, "order qty below min");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_bybit_server_busy_is_transient() {
    let e = biz(10016, "server busy");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Transient);
    // Sibling codes in the same transient family / 同族暫時性碼
    assert_eq!(
        classify_dispatch_error(&biz(10017, "gateway timeout")),
        DispatchOutcome::Transient
    );
    assert_eq!(
        classify_dispatch_error(&biz(10018, "service unavailable")),
        DispatchOutcome::Transient
    );
    assert_eq!(
        classify_dispatch_error(&biz(10019, "request timeout")),
        DispatchOutcome::Transient
    );
}

#[test]
fn test_classify_unknown_retcode_is_structural() {
    // Conservative default — unknown codes must NOT retry to avoid amplifying
    // unmodeled error shapes against the exchange.
    // 保守預設 — 未知碼禁止重試，避免對交易所放大未建模錯誤。
    let e = biz(99999, "mystery error");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_exceed_max_qty_is_structural() {
    let e = biz(170210, "order qty exceeds max");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_sign_error_is_structural() {
    let e = biz(10004, "sign not match");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_unmatched_ip_is_structural() {
    let e = biz(10010, "unmatched ip");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

// -----------------------------------------------------------------
// DISPATCH-RETRY-1 E2 follow-up tests (2026-04-19)
// 分類收窄 + 迴圈級行為
// -----------------------------------------------------------------

#[test]
fn test_classify_10001_invalid_order_link_id_format_is_structural() {
    // E2 review 2026-04-19: substring match narrowed from
    // {"duplicate", "order_link_id"} to {"duplicate"} only. Previously a
    // retMsg like "invalid order_link_id format" would fall through the
    // `order_link_id` substring arm → NoOp, silently success-equivalent
    // for a genuinely structural client-side bug. Now correctly Structural.
    //
    // E2 審查 2026-04-19：子串收窄為僅 {"duplicate"}。之前 "invalid
    // order_link_id format" 會誤判為 NoOp（靜默回報成功，實為 client 側
    // 結構性錯誤），現正確歸為 Structural。
    let e = biz(10001, "invalid order_link_id format");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
    // Additional narrow check: case-insensitive "DUPLICATE" still matches.
    // 補充：大寫 "DUPLICATE" 仍匹配（子串比對前 to_ascii_lowercase）。
    let e_upper = biz(10001, "DUPLICATE order_link_id");
    assert_eq!(classify_dispatch_error(&e_upper), DispatchOutcome::NoOp);
}

#[test]
fn test_classify_10002_recv_window_drift_is_transient() {
    // Bybit uses 10002 both for malformed requests (Structural) and for
    // client timestamp drift outside recvWindow (Transient — NTP skew;
    // next retry with fresh ts will pass). Substring match discriminates.
    //
    // Bybit 對 10002 兼作請求格式錯誤（Structural）與 client timestamp
    // 超出 recvWindow（Transient — NTP 偏差；下次 ts 更新後重試可通過）。
    // 子串匹配區分兩種情況。
    assert_eq!(
        classify_dispatch_error(&biz(10002, "invalid recv_window")),
        DispatchOutcome::Transient
    );
    assert_eq!(
        classify_dispatch_error(&biz(
            10002,
            "timestamp for this request is outside of recvWindow"
        )),
        DispatchOutcome::Transient
    );
}

#[test]
fn test_classify_10002_generic_is_structural() {
    // Without drift keywords, 10002 stays Structural (deployment bug).
    // 無漂移關鍵字時 10002 保持 Structural（部署/參數錯誤）。
    assert_eq!(
        classify_dispatch_error(&biz(10002, "generic invalid request")),
        DispatchOutcome::Structural
    );
}

// Loop-level tests (E2 follow-up): inject scripted Result sequences via
// RefCell to verify run_dispatch_retry control flow deterministically.
//
// 迴圈級測試（E2 後續）：透過 RefCell 注入受控 Result 序列，確定性地
// 驗證 run_dispatch_retry 的控制流。

#[tokio::test]
async fn test_run_dispatch_retry_ok_first_try_attempts_1() {
    use std::cell::RefCell;
    let call_count = RefCell::new(0u32);
    let result =
        run_dispatch_retry::<i32, _, _>(&[10, 10, 10], "BTCUSDT", "oLidTest", |_attempt| {
            *call_count.borrow_mut() += 1;
            async move { Ok::<i32, BybitApiError>(42) }
        })
        .await;
    match result {
        DispatchRetryResult::Ok { value, attempts } => {
            assert_eq!(value, 42);
            assert_eq!(attempts, 1, "first-try success must record attempts=1");
        }
        other => panic!("expected Ok, got {:?}", other),
    }
    assert_eq!(*call_count.borrow(), 1);
}

#[tokio::test]
async fn test_run_dispatch_retry_ok_on_third_attempt_records_attempts_3() {
    use std::cell::RefCell;
    let results: RefCell<Vec<Result<i32, BybitApiError>>> = RefCell::new(vec![
        Err(biz(10006, "transient 1")),
        Err(biz(10006, "transient 2")),
        Ok(99),
    ]);
    let result = run_dispatch_retry::<i32, _, _>(&[5, 5, 5], "BTCUSDT", "oLid", |_| {
        let r = results.borrow_mut().remove(0);
        async move { r }
    })
    .await;
    match result {
        DispatchRetryResult::Ok { value, attempts } => {
            assert_eq!(value, 99);
            assert_eq!(
                attempts, 3,
                "Ok after 2 transient retries must record attempts=3"
            );
        }
        other => panic!("expected Ok, got {:?}", other),
    }
}

#[tokio::test]
async fn test_run_dispatch_retry_structural_breaks_without_retry() {
    use std::cell::RefCell;
    let call_count = RefCell::new(0u32);
    let result = run_dispatch_retry::<(), _, _>(&[5, 5, 5], "BTCUSDT", "oLid", |_| {
        *call_count.borrow_mut() += 1;
        async move { Err::<(), BybitApiError>(biz(110012, "insufficient balance")) }
    })
    .await;
    match result {
        DispatchRetryResult::Structural { attempts, .. } => {
            assert_eq!(
                attempts, 1,
                "structural on first try must break immediately"
            );
        }
        other => panic!("expected Structural, got {:?}", other),
    }
    assert_eq!(
        *call_count.borrow(),
        1,
        "structural outcome must NOT trigger any retry"
    );
}

#[tokio::test]
async fn test_run_dispatch_retry_noop_on_second_attempt_records_attempts_2() {
    use std::cell::RefCell;
    // Sequence: transient → NoOp (duplicate). Noop must break retry loop
    // without consuming further attempts.
    //
    // 序列：transient → NoOp（duplicate）。NoOp 必須中斷重試迴圈，不再消耗
    // 後續嘗試。
    let results: RefCell<Vec<Result<(), BybitApiError>>> = RefCell::new(vec![
        Err(biz(10006, "rate limit")),
        Err(biz(10001, "duplicate order_link_id rejected")),
        Err(biz(99999, "should_not_be_reached")), // guard — NoOp must stop here
    ]);
    let result = run_dispatch_retry::<(), _, _>(&[5, 5, 5], "BTCUSDT", "oLid", |_| {
        let r = results.borrow_mut().remove(0);
        async move { r }
    })
    .await;
    match result {
        DispatchRetryResult::NoOp {
            last_error,
            attempts,
        } => {
            assert_eq!(attempts, 2, "NoOp on 2nd attempt must record attempts=2");
            match last_error {
                BybitApiError::Business { ret_msg, .. } => {
                    assert!(
                        ret_msg.to_ascii_lowercase().contains("duplicate"),
                        "last_error should be the NoOp-triggering duplicate"
                    );
                }
                _ => panic!("expected Business error"),
            }
        }
        other => panic!("expected NoOp, got {:?}", other),
    }
    // Guard row should still be in the stack.
    // 守衛列應仍在 stack 中（確認 NoOp 已中斷）。
    assert_eq!(results.borrow().len(), 1);
}

#[tokio::test]
async fn test_run_dispatch_retry_transient_exhaustion_returns_last_error() {
    use std::cell::RefCell;
    // 4 transient errors → exhaust RETRY_DELAY_MS (3 retries → 4 total
    // attempts). TransientExhausted.last_error must be the FINAL attempt's
    // error (#4), not the first.
    //
    // 4 個 transient 錯誤 → 耗盡 RETRY_DELAY_MS（3 次重試 → 4 次總嘗試）。
    // TransientExhausted.last_error 必須是最終嘗試的錯誤（#4），非首次。
    let results: RefCell<Vec<Result<(), BybitApiError>>> = RefCell::new(vec![
        Err(biz(10006, "rate limit #1")),
        Err(biz(10006, "rate limit #2")),
        Err(biz(10006, "rate limit #3")),
        Err(biz(10006, "rate limit #4-final")),
    ]);
    // Use tiny delays for fast test (schedule length equivalent to
    // RETRY_DELAY_MS = 3 retries).
    // 測試用極短延遲（表長等於 RETRY_DELAY_MS = 3 次重試）。
    let result = run_dispatch_retry::<(), _, _>(&[1, 1, 1], "BTCUSDT", "oLid", |_| {
        let r = results.borrow_mut().remove(0);
        async move { r }
    })
    .await;
    match result {
        DispatchRetryResult::TransientExhausted {
            last_error,
            attempts,
        } => {
            assert_eq!(
                attempts, 4,
                "3 retries + 1 initial = 4 total attempts on exhaustion"
            );
            match last_error {
                BybitApiError::Business { ret_msg, .. } => {
                    assert_eq!(
                        ret_msg, "rate limit #4-final",
                        "TransientExhausted.last_error must be the FINAL error, not the first"
                    );
                }
                _ => panic!("expected Business error"),
            }
        }
        other => panic!("expected TransientExhausted, got {:?}", other),
    }
    assert_eq!(results.borrow().len(), 0, "all 4 scripted results consumed");
}

#[tokio::test]
async fn test_run_dispatch_retry_close_budget_caps_at_3_attempts() {
    use std::cell::RefCell;
    // CLOSE_RETRY_DELAY_MS has length 2 → total attempts = 3 (1 initial +
    // 2 retries). Proves Q2 budget divergence: close paths exhaust faster.
    //
    // CLOSE_RETRY_DELAY_MS 長度為 2 → 總嘗試數 3（1 初始 + 2 重試）。
    // 驗證 Q2 預算差異：close 路徑更快耗盡。
    assert_eq!(CLOSE_RETRY_DELAY_MS.len(), 2);
    let call_count = RefCell::new(0u32);
    let result =
        run_dispatch_retry::<(), _, _>(&CLOSE_RETRY_DELAY_MS, "BTCUSDT", "oLid-close", |_| {
            *call_count.borrow_mut() += 1;
            async move { Err::<(), BybitApiError>(biz(10006, "rate limit")) }
        })
        .await;
    match result {
        DispatchRetryResult::TransientExhausted { attempts, .. } => {
            assert_eq!(
                attempts, 3,
                "close budget = 1 initial + 2 retries (Q2 E2 fix)"
            );
        }
        other => panic!("expected TransientExhausted, got {:?}", other),
    }
    assert_eq!(*call_count.borrow(), 3);
}

#[test]
fn test_close_retry_delay_constants() {
    // Q2 (E2 review 2026-04-19): close retries use [100, 400] = 500 ms
    // total sleep, 2 retries max. Pinned to catch unintended widening.
    //
    // Q2（E2 審查 2026-04-19）：關倉重試用 [100, 400] = 500ms 總睡眠，最多
    // 2 次重試。鎖定常數以偵測意外放寬。
    assert_eq!(CLOSE_RETRY_DELAY_MS, [100u64, 400]);
    assert_eq!(CLOSE_RETRY_DELAY_MS.len(), 2);
    // Invariant: close budget must be strictly smaller than open budget
    // 不變式：關倉預算必須嚴格小於開倉預算
    assert!(CLOSE_RETRY_DELAY_MS.len() < RETRY_DELAY_MS.len());
    let close_total: u64 = CLOSE_RETRY_DELAY_MS.iter().sum();
    let open_total: u64 = RETRY_DELAY_MS.iter().sum();
    assert!(
        close_total < open_total,
        "close retry sleep total must be < open retry sleep total (Q2 invariant)"
    );
}

#[test]
fn test_close_attempt_timeout_constant_is_500ms() {
    assert_eq!(CLOSE_ATTEMPT_TIMEOUT_MS, 500);
}

#[test]
fn test_close_dispatch_timeout_error_is_transient() {
    let e = close_dispatch_timeout_error(CLOSE_ATTEMPT_TIMEOUT_MS);
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Transient);
}
