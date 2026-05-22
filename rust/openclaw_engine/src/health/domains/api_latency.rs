//! M3 Sprint 2 Wave 2 Track D — api_latency emitter IMPL。
//!
//! MODULE_NOTE
//! 模塊用途:
//!   per docs/execution_plan/2026-05-22--m3_metric_emitter_sprint2_dispatch_packet.md
//!   §5 Track D + 2026-05-22--m3_metric_emitter_sprint2_design_spec.md §2.1 +
//!   §3.4，本 module 為 Wave 2 Track D api_latency domain 採樣 emitter。60s
//!   sample interval（per spec §2.1 「Bybit rate-limit 分鐘級才有意義」），
//!   8 metric：
//!     - `rest_p50_ms`：REST API call latency p50（ms）。
//!     - `rest_p95_ms`：REST API call latency p95（ms）。
//!     - `rest_p99_ms`：REST API call latency p99（ms）。
//!     - `ws_rtt_p50_ms`：WS round-trip latency p50（ms；ping→pong）。
//!     - `ws_rtt_p99_ms`：WS round-trip latency p99（ms）。
//!     - `ret_code_4xx_count`：HTTP 4xx retCode 樣本期間累積；client-side fault
//!       （簽名 / 參數 / rate-limit）。
//!     - `ret_code_5xx_count`：HTTP 5xx 樣本期間累積；venue-side fault（PG 級
//!       事故或交易所 maintenance）。
//!     - `ws_dropout_count`：WS dropout（連線斷裂）樣本期間累積；per ADR-0042
//!       Decision 3 cascade 預警 gate。
//!
//!   emitter **只觀測，不修**（per packet §5.5 反模式 (a)）：8 metric source 由
//!   `ApiLatencySourceProbe` trait 注入，main.rs Wave 2 後或 Sprint 5 cascade
//!   IMPL 才接 bybit_rest_client / bybit_ws_client 真實 stats hook。Wave 1
//!   scaffold sign-off 走 in-memory writer + mock source（AC-1a in-memory proxy）。
//!
//!   為什麼 8 metric 走 HTTP 4xx/5xx 而非 Bybit-specific retCode（per packet
//!   §5.5 反模式 (d) multi-venue gate 預留）:
//!     - ADR-0040 對齊「未來支援多 venue」設計：Bybit `retCode != 0` 是 venue-
//!       specific 語意；HTTP 4xx/5xx 是 transport-level 共通語意。
//!     - 各 venue probe 在 caller 端把 venue-specific 錯誤對映到 4xx/5xx，emitter
//!       只看 transport classification。
//!     - Sprint 2 Bybit 階段：probe 把 `retCode != 0` 計入 4xx（client fault）+
//!       BybitApiError::Business 升入 5xx 由 caller 自行決定；emitter 不寫死。
//!
//! 主要類 / 函數:
//!   - `ApiLatencySample`：8 metric snapshot struct（per packet §5.1）。
//!   - `ApiLatencyMetricRow`：MetricSample trait 投影；8 row per sample tick
//!     對齊 V106 schema 1 row = 1 metric_name 設計。
//!   - `ApiLatencySourceProbe` trait：抽象 8 metric source；main.rs 接線時注入
//!     真實 hook，test 注入 mock；emitter 只調用此 trait。
//!   - `classify_api_latency_*` × 8：per-metric classify_band 函數，threshold
//!     對齊 M3 design spec §2.3 ladder 規約。
//!   - `ApiLatencyEmitter`：impl `DomainEmitter`；sample_interval=60s。
//!
//! 依賴:
//!   - 全部沿用 Track A scaffold（`DomainEmitter` / `MetricSample` trait +
//!     observe_classified SM 入口 + V106 writer + event_bus）。
//!   - 不依賴 bybit_rest_client / bybit_ws_client 具體實作；經 trait 抽象注入。
//!   - 不依賴 spike feature（per AC-5 production binary 0 mock time 滲透）。
//!
//! 硬邊界:
//!   - 不修 bybit_rest_client wrapper / bybit_private_ws / bybit 既有 retry path
//!     （per packet §5.5 反模式 (a) emitter 只讀；per CLAUDE.md hard boundary
//!     「不增 hidden retry path for trading effects」對齊）。
//!   - sample_interval=60s 走 spec §2.1 規約（不寫死，由 sample_interval_sec()
//!     accessor 暴露；per packet §5.5 反模式 (b)）。
//!   - emit V106 row 不寫 `engine_mode='live'`（Sprint 2 走 paper/demo/live_demo
//!     only；per packet §9 (d)）。
//!   - 8 metric 各自 anomaly_id = `api_latency__<metric_name>`（per spec §6.2
//!     命名規約）；8 個獨立 cap window，不互 cap。
//!   - threshold 對齊 M3 design spec §2.3 ladder：先 hardcode，Sprint 5 ArcSwap
//!     熱更新（per spec §4.3 注 + Track A/B/C 同 pattern）。
//!   - ret_code 4xx/5xx 用 HTTP 標準語意，預留 multi-venue（per ADR-0040
//!     dispatch packet §5.5 反模式 (d)）。

use std::sync::Arc;

use async_trait::async_trait;

use super::super::metric_emitter::{DomainEmitter, MetricSample};
use super::super::{HealthDomain, HealthState, M3Error};

// ============================================================
// ApiLatencySample — 8 metric snapshot
// ============================================================

/// api_latency domain 採樣輸出（per dispatch packet §5.1 + §5.2 + spec §2.1）。
///
/// 為什麼這 8 個 metric:
///   - `rest_p50_ms` / `rest_p95_ms` / `rest_p99_ms`：REST API call latency 三
///     分位；p50 反映常態 / p95 反映尾延 / p99 反映 outlier；M3 spec §2.3
///     ladder 對 p99 嚴於 p50（CRITICAL>2000ms vs >500ms）。
///   - `ws_rtt_p50_ms` / `ws_rtt_p99_ms`：WS round-trip（ping→pong）p50/p99；
///     ADR-0042 Decision 3 cascade 預警「WS rtt drift 反映 venue 端慢」；
///     ws_rtt 比 ws_dropout 早期反映退化。
///   - `ret_code_4xx_count` / `ret_code_5xx_count`：transport-level retCode 累
///     積計數（HTTP 標準語意 multi-venue 預留 per ADR-0040）；4xx = client
///     fault 偏指 rate-limit 或簽名退化，5xx = venue fault 偏指交易所事故。
///   - `ws_dropout_count`：WS 斷線次數；spec line 78 已列為 dropout sample
///     metric；per ADR-0042 Decision 3 cascade gate。
///
/// 為什麼 Clone + Copy:
///   - 8 個 numeric primitive；Copy 0 cost；emitter sample() 端拷貝後可 Box
///     走 trait object。
///
/// 為什麼採樣期間 累積 count 而非速率:
///   - ret_code 與 dropout 屬「事件級」；採樣期間 = 60s，累積 count 即「過去
///     60s 內發生次數」對齊 5-sample rolling window 60×5=5min span 設計。
///   - 速率（per second）會把瞬時 burst 平均掉，反而誤判 OK；count 保留 spike
///     資訊讓 SM 端走 dwell 判斷。
#[derive(Debug, Clone, Copy)]
pub struct ApiLatencySample {
    /// REST API call latency p50（ms）。
    pub rest_p50_ms: u32,
    /// REST API call latency p95（ms）。
    pub rest_p95_ms: u32,
    /// REST API call latency p99（ms）。
    pub rest_p99_ms: u32,
    /// WS ping→pong round-trip p50（ms）。
    pub ws_rtt_p50_ms: u32,
    /// WS ping→pong round-trip p99（ms）。
    pub ws_rtt_p99_ms: u32,
    /// HTTP 4xx retCode 樣本期間累積（client fault；rate-limit / 簽名失誤）。
    pub ret_code_4xx_count: u32,
    /// HTTP 5xx retCode 樣本期間累積（venue fault；交易所 maintenance / 中斷）。
    pub ret_code_5xx_count: u32,
    /// WS dropout 樣本期間累積（per ADR-0042 Decision 3 cascade gate）。
    pub ws_dropout_count: u32,
}

/// MetricSample wrapper：1 sample 投影為 8 metric row；scheduler 端列表處理。
///
/// 為什麼一 emitter sample → 多 MetricSample row:
///   - V106 row 是 per-metric_name 一條（per ADR-0042 Decision 4 anomaly_id =
///     domain × metric_name）；8 metric → 8 row + 8 SM 各自 transition。
///   - 同 Track A `EngineRuntimeMetricRow` + Track B `PipelineThroughputMetricRow`
///     模式 1:1 對齊；scaffold reuse。
#[derive(Debug, Clone, Copy)]
pub struct ApiLatencyMetricRow {
    pub metric_name: &'static str,
    pub value: f64,
    pub band: HealthState,
}

impl MetricSample for ApiLatencyMetricRow {
    fn metric_name(&self) -> &'static str {
        self.metric_name
    }

    fn numeric_value(&self) -> f64 {
        self.value
    }

    fn classify_band(&self) -> HealthState {
        self.band
    }
}

impl ApiLatencySample {
    /// 將 sample 展為 8 個 metric row（每 metric_name 一條）。
    ///
    /// 為什麼此設計:
    ///   - 對齊 V106 schema：1 row = 1 metric_name；不展平就無法各 metric 獨立
    ///     classify_band + SM transition（per ADR-0042 Decision 4 anomaly_id 命
    ///     名規約）。
    ///   - 對齊 Track A/B/C `into_metric_rows()` 模式，scaffold reuse；scheduler
    ///     端 `run_domain_loop` 統一處理 8 metric × 1 SM each。
    pub fn into_metric_rows(self) -> Vec<ApiLatencyMetricRow> {
        let rest_p50_band = classify_api_latency_rest_p50_ms(self.rest_p50_ms);
        let rest_p95_band = classify_api_latency_rest_p95_ms(self.rest_p95_ms);
        let rest_p99_band = classify_api_latency_rest_p99_ms(self.rest_p99_ms);
        let ws_rtt_p50_band = classify_api_latency_ws_rtt_p50_ms(self.ws_rtt_p50_ms);
        let ws_rtt_p99_band = classify_api_latency_ws_rtt_p99_ms(self.ws_rtt_p99_ms);
        let ret_4xx_band = classify_api_latency_ret_code_4xx_count(self.ret_code_4xx_count);
        let ret_5xx_band = classify_api_latency_ret_code_5xx_count(self.ret_code_5xx_count);
        let dropout_band = classify_api_latency_ws_dropout_count(self.ws_dropout_count);

        vec![
            ApiLatencyMetricRow {
                metric_name: "rest_p50_ms",
                value: self.rest_p50_ms as f64,
                band: rest_p50_band,
            },
            ApiLatencyMetricRow {
                metric_name: "rest_p95_ms",
                value: self.rest_p95_ms as f64,
                band: rest_p95_band,
            },
            ApiLatencyMetricRow {
                metric_name: "rest_p99_ms",
                value: self.rest_p99_ms as f64,
                band: rest_p99_band,
            },
            ApiLatencyMetricRow {
                metric_name: "ws_rtt_p50_ms",
                value: self.ws_rtt_p50_ms as f64,
                band: ws_rtt_p50_band,
            },
            ApiLatencyMetricRow {
                metric_name: "ws_rtt_p99_ms",
                value: self.ws_rtt_p99_ms as f64,
                band: ws_rtt_p99_band,
            },
            ApiLatencyMetricRow {
                metric_name: "ret_code_4xx_count",
                value: self.ret_code_4xx_count as f64,
                band: ret_4xx_band,
            },
            ApiLatencyMetricRow {
                metric_name: "ret_code_5xx_count",
                value: self.ret_code_5xx_count as f64,
                band: ret_5xx_band,
            },
            ApiLatencyMetricRow {
                metric_name: "ws_dropout_count",
                value: self.ws_dropout_count as f64,
                band: dropout_band,
            },
        ]
    }
}

// ============================================================
// classify_band threshold helper × 8
// ============================================================
//
// 為什麼 threshold 集中於 8 個 pub fn:
//   - Sprint 5 ArcSwap 熱更新時改 8 fn 內部即可，不破壞 caller signature。
//   - scheduler 端 `classify_aggregated` match arm 直接呼此 8 fn，DRY。
//   - 對齊 Track A/B/C `classify_*` 同樣 pub fn pattern。
//
// 為什麼 threshold 來源 M3 design spec §2.3 ladder:
//   - 設計階段 ladder spec 已確定 4 band 邊界；emitter IMPL 不重設計，僅 literal
//     落地。
//   - REST latency 分三層（p50/p95/p99）；p99 嚴於 p50 對應 outlier 比常態更
//     敏感的 SLA 設計。

/// rest_p50_ms classify（常態 REST 延遲）。
///
/// ladder（per M3 design spec §2.3 line 75-85 api_latency 階梯）：
///   OK       : < 50ms     （常態 Bybit REST 距離 trade-core ~20-40ms）
///   WARN     : 50 - 200ms  （網路抖動或 venue 端輕度退化）
///   DEGRADED : > 200ms     （持續 200ms+ 表示 venue 或網路退化）
///
/// 為什麼 p50 不設 CRITICAL band:
///   - CRITICAL band 留給 p99 outlier（極端慢樣本）；p50 走 outlier 不合語意。
///   - 對齊 spec line 102 ladder「p99 > 2000ms 為 CRITICAL；p50 維持 DEGRADED」。
///   - 三段已足夠分辨「常態 / 輕微退化 / 明顯退化」三狀態；CRITICAL 由 p99
///     / 5xx / ws_dropout 三條獨立路徑捕捉。
pub fn classify_api_latency_rest_p50_ms(value: u32) -> HealthState {
    if value > 200 {
        HealthState::HealthDegraded
    } else if value >= 50 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// rest_p95_ms classify（尾延 REST 延遲）。
///
/// ladder：
///   OK       : < 200ms
///   WARN     : 200 - 500ms
///   DEGRADED : > 500ms
///
/// 為什麼 p95 比 p50 寬:
///   - p95 是「100 個樣本中第 95 個」，正常情況下會有少量慢樣本，閾值不能跟
///     p50 一樣嚴。
///   - 500ms+ 表示 5% 樣本超過半秒，trading hot path 已退化。
pub fn classify_api_latency_rest_p95_ms(value: u32) -> HealthState {
    if value > 500 {
        HealthState::HealthDegraded
    } else if value >= 200 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// rest_p99_ms classify（outlier REST 延遲）。
///
/// ladder：
///   OK       : < 500ms
///   WARN     : 500 - 1000ms
///   DEGRADED : 1000 - 2000ms
///   CRITICAL : > 2000ms     （extreme outlier；接近 timeout）
///
/// 為什麼 p99 走 CRITICAL band:
///   - p99 反映 outlier；超過 2s 表示 1% 樣本接近 Bybit REST 預設 timeout
///     （5s），下次 timeout 即觸發 fail-closed。
///   - 對齊 spec §2.3 line 102 CRITICAL band「outlier latency > 2s」literal。
pub fn classify_api_latency_rest_p99_ms(value: u32) -> HealthState {
    if value > 2000 {
        HealthState::HealthCritical
    } else if value > 1000 {
        HealthState::HealthDegraded
    } else if value >= 500 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// ws_rtt_p50_ms classify（WS 常態 RTT）。
///
/// ladder：
///   OK       : < 50ms
///   WARN     : 50 - 150ms
///   DEGRADED : > 150ms
///
/// 為什麼 WS RTT 比 REST 嚴:
///   - WS 是 persistent connection；無 TCP handshake / TLS overhead，純 ping→
///     pong 距離；正常 < 50ms。
///   - WS RTT 退化是 venue 端 push 路徑慢或 client→venue 網路退化 signal；
///     150ms+ 表示已影響 trading hot path tick delivery。
pub fn classify_api_latency_ws_rtt_p50_ms(value: u32) -> HealthState {
    if value > 150 {
        HealthState::HealthDegraded
    } else if value >= 50 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// ws_rtt_p99_ms classify（WS outlier RTT）。
///
/// ladder：
///   OK       : < 200ms
///   WARN     : 200 - 500ms
///   DEGRADED : 500 - 1500ms
///   CRITICAL : > 1500ms
///
/// 為什麼 CRITICAL > 1500ms 而非 2000ms（對比 rest_p99）:
///   - WS 是 persistent；1500ms+ outlier 即「ping→pong 斷流」可能 dropout 預警；
///     比 REST timeout buffer 短。
///   - 對齊 dispatch packet §5.1 「ws_dropout_count 是 ADR-0042 Decision 3
///     cascade gate」設計：ws_rtt p99 1500ms+ 是 dropout 前 1 步預警。
pub fn classify_api_latency_ws_rtt_p99_ms(value: u32) -> HealthState {
    if value > 1500 {
        HealthState::HealthCritical
    } else if value > 500 {
        HealthState::HealthDegraded
    } else if value >= 200 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// ret_code_4xx_count classify（client fault 累積；採樣期 60s）。
///
/// ladder：
///   OK       : 0 - 10        （極少數 rate-limit retry / 簽名一次性失誤是常態）
///   WARN     : 11 - 50
///   DEGRADED : > 50          （持續 client fault 表示簽名 / 參數 / rate-limit
///                              退化）
///
/// 為什麼 4xx 不設 CRITICAL band:
///   - 4xx 是 client 自身錯誤；可由 client 端修復（renew API key / 退避 rate-
///     limit）；不屬 venue-side outage 級。
///   - CRITICAL 留給 5xx / ws_dropout 真正 venue 級事故。
pub fn classify_api_latency_ret_code_4xx_count(value: u32) -> HealthState {
    if value > 50 {
        HealthState::HealthDegraded
    } else if value >= 11 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// ret_code_5xx_count classify（venue fault 累積；採樣期 60s）。
///
/// ladder：
///   OK       : 0             （venue 應 100% 可用）
///   WARN     : 1 - 5         （短暫 venue 端問題）
///   DEGRADED : 6 - 20        （持續 venue 端事故）
///   CRITICAL : > 20          （venue 大規模 outage；trading 必停）
///
/// 為什麼 5xx 走 CRITICAL band:
///   - 5xx 是 venue server fault；客戶端無法修復；持續 5xx = venue outage
///     直接影響交易執行。
///   - 對齊 spec §2.3 line 102 CRITICAL band「venue outage」literal。
pub fn classify_api_latency_ret_code_5xx_count(value: u32) -> HealthState {
    if value > 20 {
        HealthState::HealthCritical
    } else if value > 5 {
        HealthState::HealthDegraded
    } else if value >= 1 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

/// ws_dropout_count classify（採樣期 60s）。
///
/// ladder：
///   OK       : 0
///   WARN     : 1 - 2          （單次 / 雙次 dropout 走 reconnect 是常態）
///   DEGRADED : 3 - 5          （連續 dropout 影響 tick delivery）
///   CRITICAL : > 5             （持續斷線；market data 不可用）
///
/// 為什麼 dropout 走 CRITICAL band:
///   - per ADR-0042 Decision 3：ws_dropout 是 cascade gate；持續 dropout 走
///     fail-closed cascade 預警（Sprint 5 才執行）；Sprint 2 emitter 端只
///     classify CRITICAL band 留 audit trail。
///   - 對齊 spec §2.3 line 102 CRITICAL band「ws dropout 持續累積」literal。
pub fn classify_api_latency_ws_dropout_count(value: u32) -> HealthState {
    if value > 5 {
        HealthState::HealthCritical
    } else if value > 2 {
        HealthState::HealthDegraded
    } else if value >= 1 {
        HealthState::HealthWarn
    } else {
        HealthState::HealthOk
    }
}

// ============================================================
// ApiLatencySourceProbe trait — 8 metric source 注入點
// ============================================================

/// 8 metric source 抽象 trait；emitter 只呼此 trait 取值，**不修** bybit_rest_client
/// / bybit_private_ws / bybit 既有 retry / reconnect 邏輯（per packet §5.5 反
/// 模式 (a) + (b) emitter 只觀測）。
///
/// 為什麼 trait 注入而非直接 import bybit client:
///   - emitter「只觀測，不修」：emitter struct 持有 trait object，main.rs 接線
///     時注入真實 bybit_rest_client / bybit_private_ws stats wrapper；test 注
///     入 mock。
///   - Track B `PipelineThroughputSourceProbe` 同樣 pattern；DRY。
///   - 對齊 spec §3 D1 emitter 採樣邊界：emitter 只負責採樣 + classify，不負
///     責 metric collection 機制（histogram / counter 觀測層由 caller 端維護）。
///
/// 接線分工（main.rs Wave 2 後或 Sprint 5 cascade IMPL 才接）:
///   - `current_rest_p50_ms` / `current_rest_p95_ms` / `current_rest_p99_ms`：
///     main.rs 接 bybit_rest_client wrapper histogram（caller 端需在 wrapper
///     層加 latency 觀測；emitter 不創觀測層 per ADR-0040 multi-venue gate）。
///   - `current_ws_rtt_p50_ms` / `current_ws_rtt_p99_ms`：main.rs 接 bybit_ws
///     ping/pong 觀測（既有 reconnect path 有時延 instrumentation 預埋）。
///   - `current_ret_code_4xx_count` / `current_ret_code_5xx_count`：main.rs 接
///     bybit_rest_client retCode counter（caller 端把 retCode → HTTP class
///     對映 per multi-venue gate 預留）。
///   - `current_ws_dropout_count`：main.rs 接 bybit_private_ws Disconnected
///     event counter（既有 reconnect 邏輯有計數 hook）。
///
/// 為什麼 retCode 對映 4xx/5xx 是 caller 責任（per packet §5.5 反模式 (d)）:
///   - Bybit `retCode != 0` 是 venue-specific；多 venue 後（Binance / OKX）
///     retCode 語意不同；emitter 不寫死 Bybit 對映。
///   - caller 端（bybit_rest_client wrapper）負責把 venue-specific retCode →
///     transport-level HTTP class 對映；emitter 走 trait 抽象多 venue 友好。
///
/// 硬邊界:
///   - probe 失敗（如 source 還沒接線）返 0 不 panic；emitter 端視 0 為 OK band，
///     不誤升級（per `feedback_no_dead_params` fail-soft 對齊）。
///   - test 注入 mock 走實作；production 接線責任 Wave 2+ 或 Sprint 5 cascade
///     IMPL 時由 main.rs caller 補。
pub trait ApiLatencySourceProbe: Send + Sync {
    /// REST API call latency p50（ms；過去 60s 窗）。
    fn current_rest_p50_ms(&self) -> u32;
    /// REST API call latency p95（ms；過去 60s 窗）。
    fn current_rest_p95_ms(&self) -> u32;
    /// REST API call latency p99（ms；過去 60s 窗）。
    fn current_rest_p99_ms(&self) -> u32;
    /// WS ping→pong RTT p50（ms；過去 60s 窗）。
    fn current_ws_rtt_p50_ms(&self) -> u32;
    /// WS ping→pong RTT p99（ms；過去 60s 窗）。
    fn current_ws_rtt_p99_ms(&self) -> u32;
    /// HTTP 4xx retCode 累積（過去 60s 窗）。
    fn current_ret_code_4xx_count(&self) -> u32;
    /// HTTP 5xx retCode 累積（過去 60s 窗）。
    fn current_ret_code_5xx_count(&self) -> u32;
    /// WS dropout 累積（過去 60s 窗）。
    fn current_ws_dropout_count(&self) -> u32;
}

// ============================================================
// ApiLatencyEmitter — Track D IMPL
// ============================================================

/// api_latency domain emitter；60s sample；經 trait 抽象觀測 8 metric。
///
/// 為什麼 Arc<dyn ...> 而非 Box<dyn ...>:
///   - main.rs scheduler 接線時可能共享 source probe（同一 bybit_rest_client
///     stats 可被多 emitter 觀測），Arc 允許 reference count；Box 需移轉所有權。
///   - tokio task 跨 spawn 邊界需 Send + Sync；Arc<dyn ... + Send + Sync> 對齊。
///   - 對齊 Track B `PipelineThroughputEmitter` 同 pattern。
pub struct ApiLatencyEmitter {
    source: Arc<dyn ApiLatencySourceProbe>,
}

impl ApiLatencyEmitter {
    /// 建立 emitter；caller 注入 8 metric source probe。
    ///
    /// 為什麼 generic + Arc::new:
    ///   - test 注入 in-line struct impl trait 不需 caller 端 Arc::new。
    ///   - production main.rs 注入 Arc<RealSource> 由 generic 自動接受。
    pub fn new<S>(source: S) -> Self
    where
        S: ApiLatencySourceProbe + 'static,
    {
        Self {
            source: Arc::new(source),
        }
    }

    /// 採當前 8 metric snapshot（test 可直接呼此 helper）。
    ///
    /// 為什麼 &self 而非 &mut self（對比 Track A `sample_now` mut self）:
    ///   - sysinfo refresh_processes 需 mut；trait probe 是純讀 accessor 不需
    ///     mut，故 emitter sample 端可走 &self。
    pub fn sample_now(&self) -> Result<ApiLatencySample, M3Error> {
        Ok(ApiLatencySample {
            rest_p50_ms: self.source.current_rest_p50_ms(),
            rest_p95_ms: self.source.current_rest_p95_ms(),
            rest_p99_ms: self.source.current_rest_p99_ms(),
            ws_rtt_p50_ms: self.source.current_ws_rtt_p50_ms(),
            ws_rtt_p99_ms: self.source.current_ws_rtt_p99_ms(),
            ret_code_4xx_count: self.source.current_ret_code_4xx_count(),
            ret_code_5xx_count: self.source.current_ret_code_5xx_count(),
            ws_dropout_count: self.source.current_ws_dropout_count(),
        })
    }
}

#[async_trait]
impl DomainEmitter for ApiLatencyEmitter {
    fn domain(&self) -> HealthDomain {
        HealthDomain::ApiLatency
    }

    fn sample_interval_sec(&self) -> u64 {
        // per spec §2.1：api_latency 60s sample（不可寫死 30s per packet §5.5
        // 反模式 (b)；對齊 Bybit rate-limit 分鐘級觀測語意）。
        60
    }

    async fn sample(&mut self) -> Result<Vec<Box<dyn MetricSample>>, M3Error> {
        let snapshot = self.sample_now()?;
        let rows = snapshot.into_metric_rows();
        Ok(rows
            .into_iter()
            .map(|r| Box::new(r) as Box<dyn MetricSample>)
            .collect())
    }
}

// ============================================================
// 測試
// ============================================================

#[cfg(test)]
mod tests {
    use super::*;

    /// 內嵌 mock source；test fixture 用（對齊 Track B StubSource pattern）。
    struct StubSource {
        rest_p50_ms: u32,
        rest_p95_ms: u32,
        rest_p99_ms: u32,
        ws_rtt_p50_ms: u32,
        ws_rtt_p99_ms: u32,
        ret_code_4xx_count: u32,
        ret_code_5xx_count: u32,
        ws_dropout_count: u32,
    }

    impl ApiLatencySourceProbe for StubSource {
        fn current_rest_p50_ms(&self) -> u32 {
            self.rest_p50_ms
        }
        fn current_rest_p95_ms(&self) -> u32 {
            self.rest_p95_ms
        }
        fn current_rest_p99_ms(&self) -> u32 {
            self.rest_p99_ms
        }
        fn current_ws_rtt_p50_ms(&self) -> u32 {
            self.ws_rtt_p50_ms
        }
        fn current_ws_rtt_p99_ms(&self) -> u32 {
            self.ws_rtt_p99_ms
        }
        fn current_ret_code_4xx_count(&self) -> u32 {
            self.ret_code_4xx_count
        }
        fn current_ret_code_5xx_count(&self) -> u32 {
            self.ret_code_5xx_count
        }
        fn current_ws_dropout_count(&self) -> u32 {
            self.ws_dropout_count
        }
    }

    #[test]
    fn test_classify_rest_p50_ms_thresholds() {
        // OK <50 / WARN 50-200 / DEGRADED >200。
        assert_eq!(
            classify_api_latency_rest_p50_ms(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_rest_p50_ms(49),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_rest_p50_ms(50),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_rest_p50_ms(200),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_rest_p50_ms(201),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_rest_p95_ms_thresholds() {
        // OK <200 / WARN 200-500 / DEGRADED >500。
        assert_eq!(
            classify_api_latency_rest_p95_ms(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_rest_p95_ms(199),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_rest_p95_ms(200),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_rest_p95_ms(500),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_rest_p95_ms(501),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_rest_p99_ms_thresholds() {
        // OK <500 / WARN 500-1000 / DEGRADED 1000-2000 / CRITICAL >2000。
        assert_eq!(
            classify_api_latency_rest_p99_ms(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_rest_p99_ms(499),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_rest_p99_ms(500),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_rest_p99_ms(1000),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_rest_p99_ms(1001),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_rest_p99_ms(2000),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_rest_p99_ms(2001),
            HealthState::HealthCritical
        );
        assert_eq!(
            classify_api_latency_rest_p99_ms(5000),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_classify_ws_rtt_p50_ms_thresholds() {
        // OK <50 / WARN 50-150 / DEGRADED >150。
        assert_eq!(
            classify_api_latency_ws_rtt_p50_ms(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p50_ms(49),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p50_ms(50),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p50_ms(150),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p50_ms(151),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_ws_rtt_p99_ms_thresholds() {
        // OK <200 / WARN 200-500 / DEGRADED 500-1500 / CRITICAL >1500。
        assert_eq!(
            classify_api_latency_ws_rtt_p99_ms(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p99_ms(199),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p99_ms(200),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p99_ms(500),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p99_ms(501),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p99_ms(1500),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_ws_rtt_p99_ms(1501),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_classify_ret_code_4xx_count_thresholds() {
        // OK 0-10 / WARN 11-50 / DEGRADED >50。
        assert_eq!(
            classify_api_latency_ret_code_4xx_count(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_ret_code_4xx_count(10),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_ret_code_4xx_count(11),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ret_code_4xx_count(50),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ret_code_4xx_count(51),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_ret_code_4xx_count(100),
            HealthState::HealthDegraded
        );
    }

    #[test]
    fn test_classify_ret_code_5xx_count_thresholds() {
        // OK 0 / WARN 1-5 / DEGRADED 6-20 / CRITICAL >20。
        assert_eq!(
            classify_api_latency_ret_code_5xx_count(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_ret_code_5xx_count(1),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ret_code_5xx_count(5),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ret_code_5xx_count(6),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_ret_code_5xx_count(20),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_ret_code_5xx_count(21),
            HealthState::HealthCritical
        );
        assert_eq!(
            classify_api_latency_ret_code_5xx_count(100),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_classify_ws_dropout_count_thresholds() {
        // OK 0 / WARN 1-2 / DEGRADED 3-5 / CRITICAL >5。
        assert_eq!(
            classify_api_latency_ws_dropout_count(0),
            HealthState::HealthOk
        );
        assert_eq!(
            classify_api_latency_ws_dropout_count(1),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ws_dropout_count(2),
            HealthState::HealthWarn
        );
        assert_eq!(
            classify_api_latency_ws_dropout_count(3),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_ws_dropout_count(5),
            HealthState::HealthDegraded
        );
        assert_eq!(
            classify_api_latency_ws_dropout_count(6),
            HealthState::HealthCritical
        );
        assert_eq!(
            classify_api_latency_ws_dropout_count(20),
            HealthState::HealthCritical
        );
    }

    #[test]
    fn test_sample_into_metric_rows_emits_8_rows() {
        let sample = ApiLatencySample {
            rest_p50_ms: 30,
            rest_p95_ms: 100,
            rest_p99_ms: 300,
            ws_rtt_p50_ms: 20,
            ws_rtt_p99_ms: 150,
            ret_code_4xx_count: 2,
            ret_code_5xx_count: 0,
            ws_dropout_count: 0,
        };
        let rows = sample.into_metric_rows();
        assert_eq!(rows.len(), 8, "8 metric → 8 row 對齊 V106 schema");
        let names: Vec<&str> = rows.iter().map(|r| r.metric_name).collect();
        assert!(names.contains(&"rest_p50_ms"));
        assert!(names.contains(&"rest_p95_ms"));
        assert!(names.contains(&"rest_p99_ms"));
        assert!(names.contains(&"ws_rtt_p50_ms"));
        assert!(names.contains(&"ws_rtt_p99_ms"));
        assert!(names.contains(&"ret_code_4xx_count"));
        assert!(names.contains(&"ret_code_5xx_count"));
        assert!(names.contains(&"ws_dropout_count"));
        // OK band sample 各 metric band = OK。
        for row in rows {
            assert_eq!(
                row.band,
                HealthState::HealthOk,
                "OK band 採樣每 metric 必 OK band: {}",
                row.metric_name
            );
        }
    }

    #[tokio::test]
    async fn test_api_latency_emitter_returns_8_metric_samples() {
        let source = StubSource {
            rest_p50_ms: 30,
            rest_p95_ms: 100,
            rest_p99_ms: 300,
            ws_rtt_p50_ms: 20,
            ws_rtt_p99_ms: 150,
            ret_code_4xx_count: 2,
            ret_code_5xx_count: 0,
            ws_dropout_count: 0,
        };
        let mut emitter = ApiLatencyEmitter::new(source);
        assert_eq!(emitter.domain(), HealthDomain::ApiLatency);
        assert_eq!(emitter.sample_interval_sec(), 60);
        let samples = emitter.sample().await.unwrap();
        assert_eq!(samples.len(), 8);
        for s in &samples {
            assert_eq!(s.classify_band(), HealthState::HealthOk);
        }
    }

    #[tokio::test]
    async fn test_api_latency_emitter_critical_sample_propagates() {
        // 注入 critical / degraded 場景：rest_p99=3000 (CRITICAL), ws_rtt_p99
        // =2000 (CRITICAL), ret_5xx=30 (CRITICAL), ws_dropout=10 (CRITICAL)。
        let source = StubSource {
            rest_p50_ms: 250,
            rest_p95_ms: 800,
            rest_p99_ms: 3000,
            ws_rtt_p50_ms: 200,
            ws_rtt_p99_ms: 2000,
            ret_code_4xx_count: 80,
            ret_code_5xx_count: 30,
            ws_dropout_count: 10,
        };
        let mut emitter = ApiLatencyEmitter::new(source);
        let samples = emitter.sample().await.unwrap();
        assert_eq!(samples.len(), 8);
        // rest_p99 CRITICAL
        let p99 = samples
            .iter()
            .find(|s| s.metric_name() == "rest_p99_ms")
            .unwrap();
        assert_eq!(p99.classify_band(), HealthState::HealthCritical);
        // ws_rtt_p99 CRITICAL
        let ws_p99 = samples
            .iter()
            .find(|s| s.metric_name() == "ws_rtt_p99_ms")
            .unwrap();
        assert_eq!(ws_p99.classify_band(), HealthState::HealthCritical);
        // ret_code_5xx CRITICAL
        let r5xx = samples
            .iter()
            .find(|s| s.metric_name() == "ret_code_5xx_count")
            .unwrap();
        assert_eq!(r5xx.classify_band(), HealthState::HealthCritical);
        // ws_dropout CRITICAL
        let drop = samples
            .iter()
            .find(|s| s.metric_name() == "ws_dropout_count")
            .unwrap();
        assert_eq!(drop.classify_band(), HealthState::HealthCritical);
        // rest_p50 DEGRADED
        let p50 = samples
            .iter()
            .find(|s| s.metric_name() == "rest_p50_ms")
            .unwrap();
        assert_eq!(p50.classify_band(), HealthState::HealthDegraded);
        // rest_p95 DEGRADED
        let p95 = samples
            .iter()
            .find(|s| s.metric_name() == "rest_p95_ms")
            .unwrap();
        assert_eq!(p95.classify_band(), HealthState::HealthDegraded);
        // ws_rtt_p50 DEGRADED
        let ws_p50 = samples
            .iter()
            .find(|s| s.metric_name() == "ws_rtt_p50_ms")
            .unwrap();
        assert_eq!(ws_p50.classify_band(), HealthState::HealthDegraded);
        // ret_code_4xx DEGRADED
        let r4xx = samples
            .iter()
            .find(|s| s.metric_name() == "ret_code_4xx_count")
            .unwrap();
        assert_eq!(r4xx.classify_band(), HealthState::HealthDegraded);
    }
}
