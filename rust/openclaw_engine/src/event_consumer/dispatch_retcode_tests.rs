//! Dispatch retcode 分類 + 重試迴圈測試（自 dispatch_tests.rs 拆出，
//! EVENT-CONSUMER-SPLIT-2，2026-07-03）。mount 於 dispatch_retcode.rs。

use super::*;
use crate::bybit_rest_client::BybitApiError;
use serde_json::json;

/// Build a Business error helper for tests.
/// 測試輔助：構造 Business 錯誤。（與 dispatch_tests.rs 的 biz() 同文複製 —
/// 兩測試模組樹各自私有，跨模組共享 test fixture 的 visibility 成本高於 9 行複製。）
fn biz(ret_code: i64, ret_msg: &str) -> BybitApiError {
    BybitApiError::Business {
        ret_code,
        ret_msg: ret_msg.to_string(),
        response: json!({"retCode": ret_code, "retMsg": ret_msg}),
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
fn test_dispatch_retry_delays_helper_open_is_empty_close_is_bounded() {
    // P1-07 hardening：production call-site 透過 helper 選 retry budget。
    // open/create 必須永遠是空 slice（0 重試）；close 才能使用 reduce-only
    // 生存例外的有界重試表。
    assert!(
        dispatch_retry_delays_for_intent(false).is_empty(),
        "open/create dispatch 必須保持 0 重試預算"
    );
    assert_eq!(
        dispatch_retry_delays_for_intent(true),
        CLOSE_RETRY_DELAY_MS.as_slice(),
        "close dispatch 才是唯一保留的重試預算"
    );
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
fn test_classify_client_side_invariant_error() {
    let e = BybitApiError::Other("pagination cursor did not advance".into());
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_ip_rate_limit_is_transient() {
    let e = biz(10006, "Too many requests");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Transient);
}

#[test]
fn test_classify_duplicate_order_link_id_10001_is_structural() {
    // P2-ORDERLINKID-110072 follow-up（2026-06-07，E2/BB flag）：10001+duplicate
    // 的 classify 行為由 NoOp **改為 Structural**，與 110072 arm 對齊。
    // 為什麼改：原無條件 NoOp 把 open 與 close 都當成功；open 撞重複 order_link_id
    // 只可能是 id 撞歷史 = 開倉未成功，silent-success 是 fail-open 漏洞。
    // close 的冪等成功 upgrade 下移到 consumption Structural 分支
    // （close_dup_is_idempotent_success）——對 close 是同一 observable 成功結果。
    // 大小寫不敏感（classify 用 to_ascii_lowercase）：lowercase 與 uppercase 同歸
    // Structural（duplicate 偵測本身的 case 處理由 close_dup helper 測試覆蓋）。
    let lower = biz(10001, "duplicate order_link_id rejected");
    assert_eq!(classify_dispatch_error(&lower), DispatchOutcome::Structural);
    let upper = biz(10001, "Duplicate orderLinkId rejected");
    assert_eq!(classify_dispatch_error(&upper), DispatchOutcome::Structural);
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
fn test_classify_stop_order_limit_exceeded_is_structural() {
    let e = biz(
        110009,
        "The number of stop orders exceeds the maximum allowable limit",
    );
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
}

#[test]
fn test_classify_110017_reduce_only_reject_is_noop() {
    // P1-110017-POSITION-DRIFT-CLOSE-LOOP：110017「current position is zero」
    // 由 Structural 改為 NoOp（同 110001 平倉時訂單已不在族；110009 非此族）。
    // 為什麼：舊 `_ => Structural` 使本地殘倉 + 交易所已平的漂移倉每 tick
    // 重發 reduce-only close → 110017 → 倉永不刪 → 自持迴圈。NoOp + 消費端
    // 收斂才能斷迴圈。
    let e = biz(110017, "current position is zero");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::NoOp);
}

#[test]
fn test_classify_110001_noop_110009_structural_no_regression() {
    // 回歸守衛：110001 維持 NoOp；110009 按官方 stop-order limit 語意
    // fail-closed，不可再回到 close-equivalent success。
    assert_eq!(
        classify_dispatch_error(&biz(110001, "order not exists")),
        DispatchOutcome::NoOp
    );
    assert_eq!(
        classify_dispatch_error(&biz(
            110009,
            "The number of stop orders exceeds the maximum allowable limit",
        )),
        DispatchOutcome::Structural
    );
}

#[test]
fn test_classify_110072_duplicate_order_link_id_is_structural() {
    // P2-ORDERLINKID-110072：classify 層維持 Structural（fail-closed）保護
    // OPEN path——open 撞 110072 = id 撞歷史 = 開倉未成功，絕不可當成功。
    // close retry 的冪等成功 upgrade 在 consumption Structural 分支以 is_close
    // guard 處理（見 close_dup_is_idempotent_success），不在 classify 層。
    // 此測試錨定顯式 110072 arm（防回退到 `_ => Structural` 後失去可發現性）。
    let e = biz(110072, "OrderLinkedID is duplicate");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
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
    // 非-duplicate 的 10001（"invalid order_link_id format"，client 側格式錯）
    // 為真結構性錯誤 → Structural。此分支 follow-up 後不變。
    let e = biz(10001, "invalid order_link_id format");
    assert_eq!(classify_dispatch_error(&e), DispatchOutcome::Structural);
    // P2-ORDERLINKID-110072 follow-up（2026-06-07）：原本此處斷言大寫
    // "DUPLICATE order_link_id" → NoOp（10001+duplicate 舊行為）。follow-up 後
    // 10001+duplicate（含大小寫變體）改為 **Structural**（與 110072 對齊；open
    // fail-closed，close 冪等 upgrade 下移到 consumption 層）。誠實改斷言為
    // Structural，反映 classify 層 duplicate 與非-duplicate 的 10001 同歸 Structural。
    let e_upper = biz(10001, "DUPLICATE order_link_id");
    assert_eq!(classify_dispatch_error(&e_upper), DispatchOutcome::Structural);
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
    // 序列：transient → NoOp（110001 order-not-found）。NoOp 必須中斷重試迴圈，
    // 不再消耗後續嘗試。
    //
    // 註（2026-06-07）：本測試驗 run_dispatch_retry helper 的「NoOp 中斷重試」
    // 路徑（與 Structural 中斷由 test_run_dispatch_retry_structural_breaks_without_retry
    // 各自覆蓋）。原以 10001+duplicate 作 NoOp 觸發碼，但 follow-up 已把
    // 10001+duplicate 改為 Structural；改用 110001（穩定 NoOp 碼）保留本測試
    // 對 NoOp 路徑的覆蓋意圖不變。
    let results: RefCell<Vec<Result<(), BybitApiError>>> = RefCell::new(vec![
        Err(biz(10006, "rate limit")),
        Err(biz(110001, "order not exists")),
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
                BybitApiError::Business { ret_code, .. } => {
                    assert_eq!(
                        ret_code, 110001,
                        "last_error should be the NoOp-triggering order-not-found code"
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
        other => panic!(
            "expected TransientExhausted (single attempt), got {:?}",
            other
        ),
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
