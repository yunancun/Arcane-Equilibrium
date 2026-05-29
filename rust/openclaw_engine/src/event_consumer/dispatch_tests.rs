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
    // P1-07（2026-05-29）：OPEN（create）重試已移除（RETRY_DELAY_MS 已刪）。
    // 唯一保留的重試預算是 CLOSE：2 次重試，100/400 ms（documented reduce-only 例外）。
    // 鎖定 close 預算。
    assert_eq!(CLOSE_RETRY_DELAY_MS, [100u64, 400]);
    assert_eq!(CLOSE_RETRY_DELAY_MS.len(), 2);
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
fn test_classify_110017_reduce_only_reject_is_noop() {
    // P1-110017-POSITION-DRIFT-CLOSE-LOOP：110017「current position is zero」
    // 由 Structural 改為 NoOp（同 110001/110009 平倉時倉位已不在族）。
    // 為什麼：舊 `_ => Structural` 使本地殘倉 + 交易所已平的漂移倉每 tick
    // 重發 reduce-only close → 110017 → 倉永不刪 → 自持迴圈。NoOp + 消費端
    // 收斂才能斷迴圈。
    let e = biz(110017, "current position is zero");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
}

#[test]
fn test_classify_110001_110009_unchanged_noop_no_regression() {
    // 回歸守衛：主修只動 110017，110001/110009 必須維持原 NoOp 分類。
    assert_eq!(
        classify_dispatch_error(&biz(110001, "order not exists")),
        DispatchOutcome::NoOp
    );
    assert_eq!(
        classify_dispatch_error(&biz(110009, "position idx not match")),
        DispatchOutcome::NoOp
    );
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
    // Helper-level test: 4 transient errors against an explicit 3-slot delay
    // schedule → exhaust (3 retries → 4 total attempts). The helper still
    // supports multi-retry for the CLOSE path; this verifies the helper itself,
    // not the OPEN production policy (which is now single-attempt, see
    // test_open_dispatch_uses_empty_retry_schedule).
    // TransientExhausted.last_error must be the FINAL attempt's error (#4).
    //
    // helper 級測試：對顯式 3 槽 delay schedule 餵 4 個 transient → 耗盡（3 重試
    // → 4 次嘗試）。helper 仍支援 CLOSE 路徑多重試；本測試驗 helper 本身，非 OPEN
    // 生產政策（後者現為單次嘗試，見 test_open_dispatch_uses_empty_retry_schedule）。
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

#[tokio::test]
async fn test_open_dispatch_uses_empty_retry_schedule_single_attempt() {
    use std::cell::RefCell;
    // P1-07（cold audit pkg B；STRICT FAIL-CLOSED）：OPEN（create）生產路徑傳空
    // delay slice → run_dispatch_retry 在 attempt(0) >= len(0) 時立即回
    // TransientExhausted（單次嘗試，0 重試）。timeout / parse / transport / nonzero
    // retCode 任一都 fail-closed，不發第二筆 create。本測試模擬生產的空 schedule，
    // 對單一 transport-class transient（10006 rate-limit）斷言：恰 1 次 place 呼叫、
    // attempts==1、回 TransientExhausted（→ 生產端以 LeaseOutcome::Failed 釋放 lease，
    // 非 Consumed，見 dispatch.rs TransientExhausted/Structural 分支）。
    let call_count = RefCell::new(0u32);
    let open_no_retry: [u64; 0] = [];
    let result = run_dispatch_retry::<(), _, _>(&open_no_retry, "BTCUSDT", "oLid-open", |_| {
        *call_count.borrow_mut() += 1;
        async move { Err::<(), BybitApiError>(biz(10006, "rate limit on create")) }
    })
    .await;
    match result {
        DispatchRetryResult::TransientExhausted { attempts, .. } => {
            assert_eq!(
                attempts, 1,
                "OPEN create must be a single attempt (P1-07 STRICT FAIL-CLOSED, 0 retries)"
            );
        }
        other => panic!("expected TransientExhausted (single attempt), got {:?}", other),
    }
    assert_eq!(
        *call_count.borrow(),
        1,
        "no second create may be sent on an ambiguous/transient OPEN failure"
    );
}

#[tokio::test]
async fn test_open_dispatch_structural_single_attempt_no_retry() {
    use std::cell::RefCell;
    // P1-07：即使是 structural 業務拒單，OPEN 路徑仍只試一次（structural 本就不重試，
    // 此處鎖定 empty-slice 不改變 structural 立即終止語意）。
    let call_count = RefCell::new(0u32);
    let open_no_retry: [u64; 0] = [];
    let result = run_dispatch_retry::<(), _, _>(&open_no_retry, "BTCUSDT", "oLid-open2", |_| {
        *call_count.borrow_mut() += 1;
        // 10001（非 "duplicate"）→ structural 在本分類下；確保不重試。
        async move { Err::<(), BybitApiError>(biz(110007, "insufficient balance")) }
    })
    .await;
    match result {
        DispatchRetryResult::Structural { attempts, .. } => {
            assert_eq!(attempts, 1, "structural OPEN failure = single attempt");
        }
        other => panic!("expected Structural, got {:?}", other),
    }
    assert_eq!(*call_count.borrow(), 1);
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
    // P1-07（2026-05-29）不變式：OPEN（create）已 0 重試（RETRY_DELAY_MS 已刪），
    // CLOSE 是唯一保留重試的路徑（documented reduce-only 例外）。close 預算非空但有界。
    assert!(
        !CLOSE_RETRY_DELAY_MS.is_empty(),
        "close retry budget is the sole retained retry path (P1-07 idempotent exception)"
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
    send_exchange_zero_close(&tx, &req, &biz(110009, "position idx not match"));
    assert!(
        rx.try_recv().is_err(),
        "110001/110009 must NOT emit ExchangeZeroClose (no regression on existing NoOp)"
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
