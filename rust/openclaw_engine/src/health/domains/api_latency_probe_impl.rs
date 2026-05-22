//! M3 Sprint 2 Wave 2 Track D — `ApiLatencySourceProbe` 真實實作。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md
//!   §1.2 PA-DRIFT-4 工作項 (4)：將 `bybit_rest_client` 端的
//!   `RestLatencyHistogram` + `RetCodeCounter` 與 `bybit_private_ws` 端的
//!   `WsDropoutCounter` + `WsRttHistogram` 經 trait 抽象注入到 emitter；
//!   main.rs Wave B 接 scheduler 時 construct `RealApiLatencySourceProbe`
//!   並注入 `Arc<dyn ApiLatencySourceProbe>` 給 `ApiLatencyEmitter`。
//!
//! 主要類 / 函數:
//!   - `RealApiLatencySourceProbe`：8 trait method 對應 client 端 instrumentation
//!     accessor；走 Arc clone 取 latency / counter / RTT 數據。
//!
//! 依賴:
//!   - `crate::bybit_rest_client::{RestLatencyHistogram, RetCodeCounter}`
//!   - `crate::bybit_private_ws::{WsDropoutCounter, WsRttHistogram}`
//!   - `crate::health::domains::api_latency::ApiLatencySourceProbe` trait
//!
//! 硬邊界:
//!   - 不修 bybit_rest_client / bybit_private_ws 既有邏輯（per packet §5.5
//!     反模式 (a) (b)）；只走 Arc accessor。
//!   - 跨平台原生支援（Mac+Linux）；無 platform-specific cfg。
//!   - 0 unsafe / 0 unwrap；trait method 失敗（Arc poisoned）返 0 fail-soft。

use std::sync::Arc;

use crate::bybit_private_ws::{WsDropoutCounter, WsRttHistogram};
use crate::bybit_rest_client::{RestLatencyHistogram, RetCodeCounter};
use crate::health::domains::api_latency::ApiLatencySourceProbe;

/// `ApiLatencySourceProbe` 真實實作；持有 4 個 instrumentation Arc。
///
/// 為什麼 4 個 Arc 而非 owning struct:
///   - `BybitRestClient` + `BybitPrivateWs` 是 trading hot path SSOT；probe 不能
///     擁有 client 所有權，只能借 Arc 拿 instrumentation handle。
///   - probe 跨 task 走 emitter scheduler（Arc<dyn ApiLatencySourceProbe>）；
///     4 個內部 Arc clone 0 cost。
///
/// 為什麼分 4 個 field 而非單 holder:
///   - REST latency / retCode / WS dropout / WS RTT 4 個獨立關注點；分離
///     測試（test 可注入 mock 4 field 之任一）。
///   - main.rs Wave B 接線時直接 4 個 handle Arc clone 構造，無多餘 wrapper。
pub struct RealApiLatencySourceProbe {
    rest_latency: Arc<RestLatencyHistogram>,
    ret_code_counter: Arc<RetCodeCounter>,
    ws_dropout: Arc<WsDropoutCounter>,
    ws_rtt: Arc<WsRttHistogram>,
}

impl RealApiLatencySourceProbe {
    /// 構造 probe；注入 4 個 instrumentation Arc。
    ///
    /// 使用範例（main.rs Wave B）：
    /// ```ignore
    /// let rest_client = Arc::new(BybitRestClient::new(...)?);
    /// let ws_client = BybitPrivateWs::new(...);
    /// let probe = RealApiLatencySourceProbe::new(
    ///     rest_client.latency_histogram_handle(),
    ///     rest_client.ret_code_counter_handle(),
    ///     ws_client.dropout_counter_handle(),
    ///     ws_client.rtt_histogram_handle(),
    /// );
    /// let emitter = ApiLatencyEmitter::new(probe);
    /// ```
    pub fn new(
        rest_latency: Arc<RestLatencyHistogram>,
        ret_code_counter: Arc<RetCodeCounter>,
        ws_dropout: Arc<WsDropoutCounter>,
        ws_rtt: Arc<WsRttHistogram>,
    ) -> Self {
        Self {
            rest_latency,
            ret_code_counter,
            ws_dropout,
            ws_rtt,
        }
    }
}

impl ApiLatencySourceProbe for RealApiLatencySourceProbe {
    /// REST API call latency p50（ms；過去 60s rolling window 內）。
    ///
    /// 為什麼三次呼 `percentile_triple` 而非 cache:
    ///   - emitter 每 60s sample 一次 8 metric；單 sample_now() 內三 method
    ///     連續呼 = 3 × sort 操作（共 < 300 μs for 6000 sample）；可接受。
    ///   - cache 加邏輯複雜度（TTL / invalidate）；本 round 走簡單 path；
    ///     未來若 hot path 需求升 cache 由 Sprint 5 cascade IMPL 決定。
    fn current_rest_p50_ms_60s_window(&self) -> u32 {
        let (p50, _, _) = self.rest_latency.percentile_triple();
        p50
    }

    fn current_rest_p95_ms_60s_window(&self) -> u32 {
        let (_, p95, _) = self.rest_latency.percentile_triple();
        p95
    }

    fn current_rest_p99_ms_60s_window(&self) -> u32 {
        let (_, _, p99) = self.rest_latency.percentile_triple();
        p99
    }

    fn current_ws_rtt_p50_ms_60s_window(&self) -> u32 {
        let (p50, _) = self.ws_rtt.percentile_pair();
        p50
    }

    fn current_ws_rtt_p99_ms_60s_window(&self) -> u32 {
        let (_, p99) = self.ws_rtt.percentile_pair();
        p99
    }

    fn current_ret_code_4xx_count_60s_window(&self) -> u32 {
        self.ret_code_counter.count_4xx()
    }

    fn current_ret_code_5xx_count_60s_window(&self) -> u32 {
        self.ret_code_counter.count_5xx()
    }

    fn current_ws_dropout_count_60s_window(&self) -> u32 {
        self.ws_dropout.count()
    }
}

// ============================================================
// Tests / 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// 驗 probe 8 trait method 走實際 instrumentation 累積後的數據。
    #[test]
    fn test_probe_reflects_instrumentation_state() {
        let rest = Arc::new(RestLatencyHistogram::new());
        let ret_code = Arc::new(RetCodeCounter::new());
        let dropout = Arc::new(WsDropoutCounter::new());
        let rtt = Arc::new(WsRttHistogram::new());

        // 注入樣本
        for ms in [10, 20, 30, 40, 50, 100, 200, 500, 1000, 2000] {
            rest.record_latency(ms);
        }
        ret_code.record_4xx();
        ret_code.record_4xx();
        ret_code.record_5xx();
        dropout.record_dropout();
        dropout.record_dropout();
        dropout.record_dropout();
        rtt.record_rtt(15);
        rtt.record_rtt(25);

        let probe = RealApiLatencySourceProbe::new(rest, ret_code, dropout, rtt);

        // p50 應在 [10, 2000] 範圍內
        let p50 = probe.current_rest_p50_ms_60s_window();
        assert!(p50 > 0 && p50 <= 2000, "p50={p50}");

        // p95 應 >= p50
        let p95 = probe.current_rest_p95_ms_60s_window();
        assert!(p95 >= p50, "p95={p95} should be >= p50={p50}");

        // p99 應 >= p95
        let p99 = probe.current_rest_p99_ms_60s_window();
        assert!(p99 >= p95, "p99={p99} should be >= p95={p95}");

        // retCode counter
        assert_eq!(probe.current_ret_code_4xx_count_60s_window(), 2);
        assert_eq!(probe.current_ret_code_5xx_count_60s_window(), 1);

        // dropout
        assert_eq!(probe.current_ws_dropout_count_60s_window(), 3);

        // RTT p50 / p99
        let rtt_p50 = probe.current_ws_rtt_p50_ms_60s_window();
        let rtt_p99 = probe.current_ws_rtt_p99_ms_60s_window();
        assert!(rtt_p50 > 0 && rtt_p50 <= 25, "rtt_p50={rtt_p50}");
        assert!(rtt_p99 >= rtt_p50, "rtt_p99={rtt_p99} >= rtt_p50={rtt_p50}");
    }

    /// 驗 empty probe 全返 0（fail-soft per emitter OK band 契約）。
    #[test]
    fn test_probe_empty_returns_zero() {
        let probe = RealApiLatencySourceProbe::new(
            Arc::new(RestLatencyHistogram::new()),
            Arc::new(RetCodeCounter::new()),
            Arc::new(WsDropoutCounter::new()),
            Arc::new(WsRttHistogram::new()),
        );

        assert_eq!(probe.current_rest_p50_ms_60s_window(), 0);
        assert_eq!(probe.current_rest_p95_ms_60s_window(), 0);
        assert_eq!(probe.current_rest_p99_ms_60s_window(), 0);
        assert_eq!(probe.current_ws_rtt_p50_ms_60s_window(), 0);
        assert_eq!(probe.current_ws_rtt_p99_ms_60s_window(), 0);
        assert_eq!(probe.current_ret_code_4xx_count_60s_window(), 0);
        assert_eq!(probe.current_ret_code_5xx_count_60s_window(), 0);
        assert_eq!(probe.current_ws_dropout_count_60s_window(), 0);
    }
}
