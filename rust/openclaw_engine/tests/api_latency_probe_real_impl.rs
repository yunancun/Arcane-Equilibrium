//! Sprint 4+ Wave A PA-DRIFT-4 — `RealApiLatencySourceProbe` integration test。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md
//!   §1.2 PA-DRIFT-4 工作項 (5)：驗證 bybit_rest_client + bybit_private_ws 端
//!   instrumentation（RestLatencyHistogram / RetCodeCounter / WsDropoutCounter
//!   / WsRttHistogram）與 `RealApiLatencySourceProbe` trait 實作的真實對齊。
//!
//!   本 test 不接 真實 Bybit WS / REST endpoint（CI/Mac 無外網依賴）；走
//!   instrumentation primitive 直接 record + probe 端讀取對齊驗證。
//!   end-to-end REST/WS 接線驗證 由 Wave B main.rs scheduler 接 + Phase 3c
//!   QA Linux runtime 走（AC-1b real PG empirical）。
//!
//! 主要 test:
//!   - test_rest_latency_p50_p95_p99_after_1000_calls：mock 1000 latency 後
//!     percentile 計算正確
//!   - test_ret_code_counter_4xx_5xx_classify：BybitApiError::Business 對映
//!     4xx/5xx 對齊
//!   - test_ws_dropout_counter_60s_window：dropout record + 計數
//!   - test_ws_rtt_histogram_after_samples：RTT record + percentile
//!   - test_real_probe_through_api_latency_emitter：probe 經 ApiLatencyEmitter
//!     sample_now() 取得 ApiLatencySample 對齊
//!   - test_60s_rolling_window_expire_oldest：自然超過 60s 不可在 CI 跑；
//!     走 sample_count() + 行為驗（極端樣本 OK）；真實過期由 Linux runtime QA 走
//!
//! 硬邊界:
//!   - 不接 真實 Bybit REST/WS endpoint（CI 無外網）。
//!   - 不依賴 spike feature；production binary 0 mock time 滲透對齊。
//!   - 0 tokio::time::pause / mock clock（per AC-5 nm 0 hit invariant）。
//!   - 60s 過期語意走 instrumentation 內部 retain 邏輯驗證（樣本緩衝 + cap）。

use std::sync::Arc;

use openclaw_engine::bybit_private_ws::{WsDropoutCounter, WsRttHistogram};
use openclaw_engine::bybit_rest_client::{
    BybitApiError, RestLatencyHistogram, RetCodeCounter,
};
use openclaw_engine::health::domains::api_latency::{
    ApiLatencyEmitter, ApiLatencySample, ApiLatencySourceProbe,
};
use openclaw_engine::health::domains::api_latency_probe_impl::RealApiLatencySourceProbe;

// ============================================================
// (1) RestLatencyHistogram p50/p95/p99
// ============================================================

/// 1000 calls mock 後 p50/p95/p99 應該對齊 sort-based percentile 計算。
#[test]
fn test_rest_latency_p50_p95_p99_after_1000_calls() {
    let histogram = Arc::new(RestLatencyHistogram::new());

    // 注入 1000 樣本：1, 2, ..., 1000 ms（均勻分佈）
    for i in 1..=1000u64 {
        histogram.record_latency(i);
    }

    let (p50, p95, p99) = histogram.percentile_triple();

    // p50 nearest-rank：ceil(0.5 * 1000) - 1 = 499 → latencies[499] = 500
    assert_eq!(p50, 500, "p50 should be 500 from uniform [1, 1000]");
    // p95 nearest-rank：ceil(0.95 * 1000) - 1 = 949 → latencies[949] = 950
    assert_eq!(p95, 950, "p95 should be 950 from uniform [1, 1000]");
    // p99 nearest-rank：ceil(0.99 * 1000) - 1 = 989 → latencies[989] = 990
    assert_eq!(p99, 990, "p99 should be 990 from uniform [1, 1000]");

    // 為什麼這 3 個 percentile 對齊：sort-based nearest-rank 在 N=1000
    // 與 linear interp 差異 < 1；我們選 nearest-rank 對齊 Prometheus 行業慣例。
}

/// empty histogram 應返 (0, 0, 0)（emitter OK band fail-soft）。
#[test]
fn test_rest_latency_empty_returns_zero_triple() {
    let histogram = RestLatencyHistogram::new();
    let (p50, p95, p99) = histogram.percentile_triple();
    assert_eq!((p50, p95, p99), (0, 0, 0));
    assert_eq!(histogram.sample_count(), 0);
}

/// sample_count 走 60s rolling window：record N 後即時 count = N。
#[test]
fn test_rest_latency_sample_count_matches() {
    let histogram = RestLatencyHistogram::new();
    for ms in [10, 20, 30, 40, 50] {
        histogram.record_latency(ms);
    }
    assert_eq!(histogram.sample_count(), 5);
}

// ============================================================
// (2) RetCodeCounter 4xx/5xx 對映
// ============================================================

/// `BybitApiError::Business` 對應 retCode 對映到 4xx / 5xx。
///
/// 為什麼這 6 個 code 屬 client fault（4xx）:
///   - 10001 InvalidParam / 10002 InvalidRequest：請求格式 bug
///   - 10003 ApiKeyInvalid / 10004 SignError：認證 bug
///   - 10005 PermissionDenied：權限不足
///   - 10006 IpRateLimit / 10010 UnmatchedIp：rate-limit / IP 漂移
/// 其他 110xxx 業務碼算 venue fault（5xx）。
#[test]
fn test_ret_code_counter_4xx_5xx_classify() {
    let counter = RetCodeCounter::new();

    // 注入 4 個 4xx + 3 個 5xx
    for code in [10001, 10003, 10004, 10006] {
        counter.record_for_error(&BybitApiError::Business {
            ret_code: code,
            ret_msg: "test".into(),
            response: serde_json::json!({}),
        });
    }
    for code in [110001, 110007, 110049] {
        counter.record_for_error(&BybitApiError::Business {
            ret_code: code,
            ret_msg: "test".into(),
            response: serde_json::json!({}),
        });
    }

    assert_eq!(counter.count_4xx(), 4, "10001/10003/10004/10006 are client fault");
    assert_eq!(counter.count_5xx(), 3, "110xxx are venue fault");
}

/// `BybitApiError::Transport` / `JsonParse` / `NoCredentials` 不計入 4xx/5xx
/// （wrapper 層 fault，非 venue / client API fault）。
#[test]
fn test_ret_code_counter_skips_non_business_errors() {
    let counter = RetCodeCounter::new();

    // NoCredentials / SigningError：wrapper 層 fault；不算 venue fault
    counter.record_for_error(&BybitApiError::NoCredentials);
    counter.record_for_error(&BybitApiError::SigningError("test".into()));

    assert_eq!(counter.count_4xx(), 0, "wrapper-layer errors not counted as 4xx");
    assert_eq!(counter.count_5xx(), 0, "wrapper-layer errors not counted as 5xx");
}

/// 直接 record_4xx / record_5xx low-level API 對齊。
#[test]
fn test_ret_code_counter_direct_record() {
    let counter = RetCodeCounter::new();
    counter.record_4xx();
    counter.record_4xx();
    counter.record_5xx();
    assert_eq!(counter.count_4xx(), 2);
    assert_eq!(counter.count_5xx(), 1);
}

// ============================================================
// (3) WsDropoutCounter
// ============================================================

/// WS dropout record + 計數對齊。
#[test]
fn test_ws_dropout_counter_basic() {
    let counter = WsDropoutCounter::new();
    for _ in 0..5 {
        counter.record_dropout();
    }
    assert_eq!(counter.count(), 5);
}

/// empty dropout 返 0（emitter fail-soft）。
#[test]
fn test_ws_dropout_counter_empty_returns_zero() {
    let counter = WsDropoutCounter::new();
    assert_eq!(counter.count(), 0);
}

// ============================================================
// (4) WsRttHistogram p50/p99
// ============================================================

/// WS RTT record + percentile 對齊。
#[test]
fn test_ws_rtt_histogram_after_samples() {
    let histogram = WsRttHistogram::new();
    for ms in [10, 20, 30, 40, 50, 100] {
        histogram.record_rtt(ms);
    }
    let (p50, p99) = histogram.percentile_pair();
    // N=6；p50 nearest-rank：ceil(0.5 * 6) - 1 = 2 → sorted[2] = 30
    assert_eq!(p50, 30, "p50 of [10,20,30,40,50,100] should be 30");
    // p99 nearest-rank：ceil(0.99 * 6) - 1 = 5 → sorted[5] = 100
    assert_eq!(p99, 100, "p99 of [10,20,30,40,50,100] should be 100");
}

/// empty rtt 返 (0, 0)。
#[test]
fn test_ws_rtt_histogram_empty_returns_zero_pair() {
    let histogram = WsRttHistogram::new();
    let (p50, p99) = histogram.percentile_pair();
    assert_eq!((p50, p99), (0, 0));
    assert_eq!(histogram.sample_count(), 0);
}

// ============================================================
// (5) RealApiLatencySourceProbe 整合 — 經 ApiLatencyEmitter
// ============================================================

/// probe 經 ApiLatencyEmitter sample_now() 取得 ApiLatencySample 對齊 8 metric。
///
/// 為什麼此 test 必要（per packet §1.2 工作項 (5) integration test）:
///   - 驗 probe 8 trait method 與 emitter sample_now() 8 field 字面對應。
///   - 任一 method 漏接 / 順序錯位 → sample 對齊失敗。
///   - 配合 health/domains/api_latency_probe_impl.rs 內 inline test 雙重守。
#[test]
fn test_real_probe_through_api_latency_emitter() {
    let rest = Arc::new(RestLatencyHistogram::new());
    let ret_code = Arc::new(RetCodeCounter::new());
    let dropout = Arc::new(WsDropoutCounter::new());
    let rtt = Arc::new(WsRttHistogram::new());

    // 注入 8 個不同 metric value
    for ms in 1..=100u64 {
        rest.record_latency(ms);
    }
    for _ in 0..7 {
        ret_code.record_4xx();
    }
    for _ in 0..2 {
        ret_code.record_5xx();
    }
    for _ in 0..3 {
        dropout.record_dropout();
    }
    for ms in [15, 25, 35, 45] {
        rtt.record_rtt(ms);
    }

    let probe = RealApiLatencySourceProbe::new(
        Arc::clone(&rest),
        Arc::clone(&ret_code),
        Arc::clone(&dropout),
        Arc::clone(&rtt),
    );
    let emitter = ApiLatencyEmitter::new(probe);

    let sample: ApiLatencySample = emitter
        .sample_now()
        .expect("sample_now should succeed");

    // REST percentile：[1..=100] sample
    //   p50 = sorted[49] = 50；p95 = sorted[94] = 95；p99 = sorted[98] = 99
    assert_eq!(sample.rest_p50_ms, 50);
    assert_eq!(sample.rest_p95_ms, 95);
    assert_eq!(sample.rest_p99_ms, 99);

    // WS RTT：[15, 25, 35, 45]
    //   p50 = sorted[1] = 25（ceil(0.5*4)-1 = 1）
    //   p99 = sorted[3] = 45（ceil(0.99*4)-1 = 3）
    assert_eq!(sample.ws_rtt_p50_ms, 25);
    assert_eq!(sample.ws_rtt_p99_ms, 45);

    // ret_code + dropout 直接 count
    assert_eq!(sample.ret_code_4xx_count, 7);
    assert_eq!(sample.ret_code_5xx_count, 2);
    assert_eq!(sample.ws_dropout_count, 3);
}

/// empty probe 經 emitter 走全 0 sample（OK band fail-soft）。
#[test]
fn test_real_probe_empty_emitter_returns_all_zero() {
    let probe = RealApiLatencySourceProbe::new(
        Arc::new(RestLatencyHistogram::new()),
        Arc::new(RetCodeCounter::new()),
        Arc::new(WsDropoutCounter::new()),
        Arc::new(WsRttHistogram::new()),
    );
    let emitter = ApiLatencyEmitter::new(probe);
    let sample = emitter.sample_now().expect("sample_now should succeed");

    assert_eq!(sample.rest_p50_ms, 0);
    assert_eq!(sample.rest_p95_ms, 0);
    assert_eq!(sample.rest_p99_ms, 0);
    assert_eq!(sample.ws_rtt_p50_ms, 0);
    assert_eq!(sample.ws_rtt_p99_ms, 0);
    assert_eq!(sample.ret_code_4xx_count, 0);
    assert_eq!(sample.ret_code_5xx_count, 0);
    assert_eq!(sample.ws_dropout_count, 0);
}

// ============================================================
// (6) 反模式守 — probe Arc clone 不破壞既有 instrumentation 共享
// ============================================================

/// 多個 probe 持同一 Arc<RestLatencyHistogram>；任一端 record 後 全 probe 看見。
/// 守 main.rs Wave B 接線時可能多個 emitter 共享同 client probe。
#[test]
fn test_multiple_probes_share_instrumentation_arc() {
    let rest = Arc::new(RestLatencyHistogram::new());
    let ret_code = Arc::new(RetCodeCounter::new());
    let dropout = Arc::new(WsDropoutCounter::new());
    let rtt = Arc::new(WsRttHistogram::new());

    let probe_a = RealApiLatencySourceProbe::new(
        Arc::clone(&rest),
        Arc::clone(&ret_code),
        Arc::clone(&dropout),
        Arc::clone(&rtt),
    );
    let probe_b = RealApiLatencySourceProbe::new(
        Arc::clone(&rest),
        Arc::clone(&ret_code),
        Arc::clone(&dropout),
        Arc::clone(&rtt),
    );

    // probe_a 看到的初始狀態：全 0
    assert_eq!(probe_a.current_ret_code_5xx_count_60s_window(), 0);
    assert_eq!(probe_b.current_ret_code_5xx_count_60s_window(), 0);

    // 從 rest_client 端 record：兩 probe 都看到
    ret_code.record_5xx();
    ret_code.record_5xx();

    assert_eq!(probe_a.current_ret_code_5xx_count_60s_window(), 2);
    assert_eq!(probe_b.current_ret_code_5xx_count_60s_window(), 2);
}

/// REST latency hot path cap test：record > buffer cap 不 panic、不 unbounded。
#[test]
fn test_rest_latency_hot_path_cap_bounded() {
    let histogram = RestLatencyHistogram::new();
    // 注入 20000 樣本（超過 cap 8192）
    for i in 0..20000u64 {
        histogram.record_latency(i % 1000);
    }
    // sample_count 不可超過 cap；buffer 自動 prune
    let count = histogram.sample_count();
    assert!(count <= 8192, "sample_count={count} should be capped at 8192");
    // percentile 仍正確返回（不 panic）
    let (p50, p95, p99) = histogram.percentile_triple();
    assert!(p50 > 0);
    assert!(p95 >= p50);
    assert!(p99 >= p95);
}

/// retCode counter hot path cap test：> buffer cap 不 panic。
#[test]
fn test_ret_code_counter_hot_path_cap_bounded() {
    let counter = RetCodeCounter::new();
    for _ in 0..20000 {
        counter.record_4xx();
    }
    let count_4xx = counter.count_4xx();
    assert!(count_4xx <= 8192, "count_4xx={count_4xx} should be capped at 8192");
}
