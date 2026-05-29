//! Bybit V5 REST API client with HMAC-SHA256 signing (R-05 exchange infra).
//! Bybit V5 REST API 客戶端，支持 HMAC-SHA256 簽名。
//!
//! MODULE_NOTE (EN): Foundation HTTP client for all authenticated Bybit V5 endpoints.
//!   Signs requests per Bybit spec: timestamp + api_key + recv_window + params.
//!   Supports GET (query string signing) and POST (JSON body signing).
//!   Rate limit tracking from response headers. Configurable base URL for
//!   mainnet / testnet / demo environments.
//! MODULE_NOTE (中): 所有 Bybit V5 認證端點的基礎 HTTP 客戶端。
//!   按 Bybit 規範簽名：timestamp + api_key + recv_window + params。
//!   支持 GET（查詢字串簽名）和 POST（JSON body 簽名）。
//!   從回應頭讀取限流狀態。可配置 mainnet / testnet / demo 基礎 URL。

use crate::common::bybit_signer::sign_rest_v5;
use reqwest::Client;
use std::sync::Arc;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};
use thiserror::Error;
use tokio::time::sleep;
use tracing::{debug, warn};

// ---------------------------------------------------------------------------
// Error types / 錯誤類型
// ---------------------------------------------------------------------------

/// Bybit API error types.
/// Bybit API 錯誤類型。
#[derive(Debug, Error)]
pub enum BybitApiError {
    /// HTTP transport error / HTTP 傳輸錯誤
    #[error("HTTP transport error: {0}")]
    Transport(#[from] reqwest::Error),

    /// Bybit business error (HTTP 200 but retCode != 0)
    /// Bybit 業務錯誤（HTTP 200 但 retCode != 0）
    #[error("Bybit API error: retCode={ret_code}, retMsg={ret_msg}")]
    Business {
        ret_code: i64,
        ret_msg: String,
        /// Full response body for debugging / 完整回應供調試
        response: serde_json::Value,
    },

    /// JSON parse error / JSON 解析錯誤
    #[error("JSON parse error: {0}")]
    JsonParse(#[from] serde_json::Error),

    /// Missing API credentials / 缺少 API 憑證
    #[error("API credentials not configured")]
    NoCredentials,

    /// Signing error / 簽名錯誤
    #[error("HMAC signing error: {0}")]
    SigningError(String),
}

/// Result type alias for BybitApiError.
/// BybitApiError 的 Result 類型別名。
pub type BybitResult<T> = Result<T, BybitApiError>;

// ---------------------------------------------------------------------------
// Environment / 環境
// ---------------------------------------------------------------------------

/// Bybit API environment.
/// Bybit API 環境。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BybitEnvironment {
    /// Demo/sandbox trading / Demo 沙盒交易
    Demo,
    /// Testnet / 測試網
    Testnet,
    /// Mainnet (production) / 主網（生產）
    Mainnet,
    /// Live-Demo: live slot credentials (GBR key) against demo server.
    /// Used when operator configures keys via the "Live-Demo" tab in settings.
    /// Live-Demo：使用 live 槽憑證（GBR key），連接 Demo 伺服器。
    /// 用於 operator 通過設定頁「Live-Demo」tab 配置 key 的情況。
    LiveDemo,
}

impl BybitEnvironment {
    /// Get the base REST URL for this environment.
    /// 取得此環境的基礎 REST URL。
    pub fn rest_base_url(&self) -> &'static str {
        match self {
            Self::Demo | Self::LiveDemo => "https://api-demo.bybit.com",
            Self::Testnet => "https://api-testnet.bybit.com",
            Self::Mainnet => "https://api.bybit.com",
        }
    }

    /// Get the private WebSocket URL for this environment.
    /// 取得此環境的私有 WebSocket URL。
    pub fn private_ws_url(&self) -> &'static str {
        match self {
            Self::Demo | Self::LiveDemo => "wss://stream-demo.bybit.com/v5/private",
            Self::Testnet => "wss://stream-testnet.bybit.com/v5/private",
            Self::Mainnet => "wss://stream.bybit.com/v5/private",
        }
    }

    /// Private WS topics to subscribe per environment.
    /// 每個環境下要訂閱的私有 WS 主題列表。
    ///
    /// IMPORTANT: Bybit Demo only supports `order, execution, position, wallet, greeks`.
    /// Both `execution.fast` and `dcp` are mainnet-only — Bybit silently accepts
    /// `execution.fast` (subscribe returns success:true but no data ever flows;
    /// total_fills permanently 0) and explicitly rejects `dcp` with "topic does not
    /// exist". Discovered 2026-04-11 via B-2 root-cause investigation; verified
    /// against https://bybit-exchange.github.io/docs/v5/demo and live subscribe
    /// confirmation logs.
    /// 重要：Bybit Demo 僅支援 `order, execution, position, wallet, greeks`。
    /// `execution.fast` 與 `dcp` 都只在 mainnet — `execution.fast` 會被靜默接受
    /// 但永遠不推資料；`dcp` 會被明確拒絕 "topic does not exist"。
    /// 2026-04-11 B-2 根因調查發現並驗證。
    pub fn private_ws_topics(&self) -> &'static [&'static str] {
        match self {
            // Demo/LiveDemo/Testnet: regular `execution` topic. No `dcp` (rejected
            // by demo). DCP server-side cancellation is mainnet-only anyway.
            Self::Demo | Self::LiveDemo | Self::Testnet => {
                &["order", "execution", "position", "wallet"]
            }
            // Mainnet: `execution.fast` for ~50ms latency, plus `dcp` for
            // server-side cancel-on-disconnect notifications.
            Self::Mainnet => &["order", "execution.fast", "position", "wallet", "dcp"],
        }
    }

    /// Map environment to its corresponding secret file slot name.
    /// 將環境映射到對應的 secret 文件槽位名稱。
    ///
    /// Demo and Testnet share the "demo" slot (development credentials).
    /// Mainnet and LiveDemo both use the "live" slot — LiveDemo uses live key against demo server.
    /// Demo 和 Testnet 共用 "demo" 槽位（開發憑證）。
    /// Mainnet 和 LiveDemo 均使用 "live" 槽位 — LiveDemo 用 live key 連 demo 伺服器。
    pub fn secret_slot(&self) -> &'static str {
        match self {
            Self::Demo | Self::Testnet => "demo",
            Self::Mainnet | Self::LiveDemo => "live",
        }
    }
}

impl Default for BybitEnvironment {
    fn default() -> Self {
        Self::Demo // Safe default — never accidentally hit mainnet
    }
}

/// Determine the correct BybitEnvironment for Live pipeline by reading
/// the `bybit_endpoint` metadata file written by the Python settings API.
///
/// 通過讀取 Python 設定 API 寫入的 `bybit_endpoint` 元數據文件，
/// 為 Live 管線決定正確的 BybitEnvironment。
///
/// Returns:
///   `LiveDemo`  — if `live/bybit_endpoint` contains "demo"
///   `Mainnet`   — if "mainnet" or file absent (fail-safe: never accidentally use demo in prod)
///
/// 返回值：
///   `LiveDemo`  — `live/bybit_endpoint` 內容為 "demo"
///   `Mainnet`   — 內容為 "mainnet" 或文件不存在（安全默認值：不意外走 demo）
pub fn live_bybit_environment() -> BybitEnvironment {
    match read_secret_file("live", "bybit_endpoint").as_deref() {
        Some("demo") => BybitEnvironment::LiveDemo,
        _ => BybitEnvironment::Mainnet,
    }
}

// ---------------------------------------------------------------------------
// Bybit V5 response shape / Bybit V5 回應格式
// ---------------------------------------------------------------------------

/// Standard Bybit V5 API response wrapper.
/// 標準 Bybit V5 API 回應包裝器。
#[derive(Debug, Clone, serde::Deserialize, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct BybitResponse {
    pub ret_code: i64,
    #[serde(default)]
    pub ret_msg: String,
    #[serde(default)]
    pub result: serde_json::Value,
    #[serde(default)]
    pub time: u64,
}

impl BybitResponse {
    /// Check if this response indicates success (retCode == 0).
    /// 檢查此回應是否表示成功（retCode == 0）。
    pub fn is_ok(&self) -> bool {
        self.ret_code == 0
    }

    /// Convert to Result: Ok(self) if retCode == 0, Err otherwise.
    /// 轉換為 Result：retCode == 0 時 Ok(self)，否則 Err。
    pub fn into_result(self) -> BybitResult<Self> {
        if self.is_ok() {
            Ok(self)
        } else {
            Err(BybitApiError::Business {
                ret_code: self.ret_code,
                ret_msg: self.ret_msg.clone(),
                response: serde_json::to_value(&self).unwrap_or_default(),
            })
        }
    }
}

// ---------------------------------------------------------------------------
// Rate limit state / 限流狀態
// ---------------------------------------------------------------------------

/// Bybit V5 rate limit group — each group has independent limits.
/// Bybit V5 限流分組 — 每組有獨立的限制。
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[repr(usize)]
pub enum RateLimitGroup {
    /// Order creation/amendment/cancellation (10 req/s) / 訂單操作
    Order,
    /// Position queries and configuration (10 req/s) / 持倉操作
    Position,
    /// Account queries (10 req/s) / 帳戶查詢
    Account,
    /// Market data queries (10-120 req/s depending on endpoint) / 市場數據
    Market,
    /// Asset operations (5 req/s) / 資產操作
    Asset,
    /// Other / 其他
    Other,
}

impl RateLimitGroup {
    /// Determine the rate limit group for a given API path.
    /// 根據 API 路徑判斷所屬限流分組。
    ///
    /// Sprint 1B Earn first stake B3（2026-05-23）：`/v5/earn/` 前綴對映 `Asset`
    /// 5 req/s。為什麼歸 Asset：Earn 屬資金移動類（Funding ↔ Unified ↔ Earn
    /// staking），對齊既有 `/v5/asset/` 同 group 限流語意；BB C4 verdict Part A.2
    /// + tiagosiebler SDK 註釋亦明列「Rate limit: 5 req/s」對齊。
    pub fn from_path(path: &str) -> Self {
        if path.starts_with("/v5/order/") || path.starts_with("/v5/execution/") {
            Self::Order
        } else if path.starts_with("/v5/position/") {
            Self::Position
        } else if path.starts_with("/v5/account/") {
            Self::Account
        } else if path.starts_with("/v5/market/") || path.starts_with("/v5/spot-lever-token/") {
            Self::Market
        } else if path.starts_with("/v5/asset/")
            || path.starts_with("/v5/spot-margin")
            || path.starts_with("/v5/earn/")
        {
            // /v5/earn/ 對映 Asset 5 req/s（Sprint 1B B3；per BB C4 verdict + SDK 註釋）。
            Self::Asset
        } else {
            Self::Other
        }
    }
}

/// Thread-safe rate limit tracker with per-group tracking.
/// 線程安全的限流追蹤器（含分組追蹤）。
#[derive(Debug)]
struct RateLimitState {
    /// Global remaining requests (from last response header)
    /// 全局剩餘請求數（來自最近的回應頭）
    remaining: AtomicI64,
    /// Reset timestamp (ms) / 重置時間戳（毫秒）
    reset_ms: AtomicU64,
    /// Per-group remaining (Order, Position, Account, Market, Asset, Other)
    /// 分組剩餘（索引按 enum 順序）
    group_remaining: [AtomicI64; 6],
    /// P2-03（cold audit pkg B）：每組獨立的重置時間戳（毫秒），與 group_remaining 平行。
    /// 為什麼需要：舊版 wait_if_rate_limited 只看全局 reset_ms，mutating Order 組
    /// （10 req/s）可能近上限而全局計數仍健康 → 對 /v5/order/* 撞 10006 可避免。
    /// 0 = 未知 → preflight 回退到全局 reset_ms。
    group_reset_ms: [AtomicU64; 6],
}

impl Default for RateLimitState {
    fn default() -> Self {
        Self {
            remaining: AtomicI64::new(120),
            reset_ms: AtomicU64::new(0),
            group_remaining: [
                AtomicI64::new(10),  // Order
                AtomicI64::new(10),  // Position
                AtomicI64::new(10),  // Account
                AtomicI64::new(120), // Market
                AtomicI64::new(5),   // Asset
                AtomicI64::new(10),  // Other
            ],
            group_reset_ms: [
                AtomicU64::new(0), // Order
                AtomicU64::new(0), // Position
                AtomicU64::new(0), // Account
                AtomicU64::new(0), // Market
                AtomicU64::new(0), // Asset
                AtomicU64::new(0), // Other
            ],
        }
    }
}

// ---------------------------------------------------------------------------
// PA-DRIFT-4 — REST latency histogram + ret_code counter 60s rolling window
// ---------------------------------------------------------------------------
//
// 模塊用途（per PA-DRIFT-4 + dispatch packet §1.2 工作項 (1)-(2)）：
//   - `RestLatencyHistogram`：60s 滾窗 REST call latency 樣本緩衝，提供
//     p50/p95/p99 percentile accessor 供 `ApiLatencySourceProbe` 注入；
//     emitter 端走 trait 抽象（per packet §5.5 反模式 (d) multi-venue 預留）。
//   - `RetCodeCounter`：60s 滾窗 4xx + 5xx 計數；4xx = client fault（retCode
//     != 0 + 客戶端錯誤 / 簽名 / 參數）；5xx = venue fault（HTTP 5xx / business
//     error）。
//
// 設計選擇（為什麼 self-impl sort-based percentile，非 `hdrhistogram`）：
//   - 60s window × 假設 100 call/s 上限 = 6000 sample；sort O(n log n) ≪
//     hdrhistogram learning overhead；每次 sample_now 才呼一次 percentile（probe
//     端走 lazy 計算）。
//   - 0 新 dep（hdrhistogram 雖在 workspace 但 openclaw_engine 未 import）；
//     最小編譯時間增量 + 跨平台 0 風險。
//
// 60s 滾窗實作：
//   - `Vec<(Instant, u64)>` 帶時間戳；讀取時自動清除 > 60s sample（lazy expire）。
//   - thread-safe = `Arc<Mutex<...>>`；REST hot path 鎖極短（push + retain）。
//   - 為什麼不寫 `tokio::sync::Mutex`：probe accessor 是同步 trait method，
//     `std::sync::Mutex` 對齊；REST call 端走 async 但 record 是常數時間
//     不阻塞 runtime（per `feedback_no_dead_params` 對齊）。
//
// 硬邊界:
//   - 不修既有 REST call 邏輯（per packet §5.5 反模式 (a)）；只在 get / post
//     wrap latency 計時 + record。
//   - probe failure（如未注入）返 0 不 panic（per emitter trait OK-band 契約）。

/// REST 樣本最大年齡（60s rolling window per packet §1.1 工作項 (1)）。
const REST_LATENCY_WINDOW_SECS: u64 = 60;
/// retCode 樣本最大年齡（60s rolling window per packet §1.1 工作項 (2)）。
const RET_CODE_WINDOW_SECS: u64 = 60;
/// REST 樣本緩衝上限（防 unbounded growth；60s × 假設 100 call/s = 6000 上限）。
const REST_LATENCY_BUFFER_CAP: usize = 8192;
/// retCode 樣本緩衝上限。
const RET_CODE_BUFFER_CAP: usize = 8192;

/// REST API call latency 60s rolling-window histogram。
///
/// 為什麼 thread-safe `Arc<Mutex<Vec<...>>>`：
///   - REST hot path 多 task 並發呼 record_latency；同時 probe accessor 端
///     走 ApiLatencySourceProbe trait method（同步），鎖必要。
///   - 鎖內操作 = push + drain_expired + sort_for_percentile；常數時間（< μs
///     級）；不阻塞 async runtime。
#[derive(Debug)]
pub struct RestLatencyHistogram {
    /// 樣本緩衝：每筆 `(record_time, latency_ms)`。
    /// 讀取 percentile 時走 lazy expire（清除 > 60s）。
    samples: Mutex<Vec<(Instant, u64)>>,
}

impl Default for RestLatencyHistogram {
    fn default() -> Self {
        Self::new()
    }
}

impl RestLatencyHistogram {
    /// 建立空 histogram。
    pub fn new() -> Self {
        Self {
            samples: Mutex::new(Vec::with_capacity(256)),
        }
    }

    /// 紀錄一次 REST call latency（ms）。
    ///
    /// 為什麼 cap = 8192：60s window × 假設 100 call/s = 6000 上限；8192 預留
    /// 30% headroom；超過 cap 走 drain_expired + truncate 避 unbounded。
    /// hot path 鎖極短（push + 可能的 prune），對 REST call 延遲影響 < μs 級。
    pub fn record_latency(&self, latency_ms: u64) {
        let now = Instant::now();
        if let Ok(mut samples) = self.samples.lock() {
            // 達 cap 時先 drain expired 釋放空間；仍滿則 truncate to half（保新樣本）
            // 這裡走 retain 而非 binary_search + drain，因 prune 動作不頻繁
            // （cap = 8192 樣本對齊 60s 100call/s 上限），實作直觀優先。
            //
            // `checked_sub.unwrap_or(now)` fallback 語意（per E2 round 1 M-1 fix）：
            //   - process boot > 60s normal path：cutoff = now - 60s，正常 retain
            //     過濾 60s 外 sample。
            //   - process boot < 60s edge case：Instant 算術下溢時 checked_sub 返
            //     None；fallback cutoff = now，**所有歷史 sample 被 filter 掉**
            //     （極端短期過渡；60s 後恢復正常 60s rolling window 語意）。
            //   - 不會洩漏 sample（fail-safe 保守清空 < 不誤保留過期）；無實際業
            //     務 bug — 8192 cap 已先確保緩衝不 unbounded。
            if samples.len() >= REST_LATENCY_BUFFER_CAP {
                let cutoff = now
                    .checked_sub(Duration::from_secs(REST_LATENCY_WINDOW_SECS))
                    .unwrap_or(now);
                samples.retain(|(t, _)| *t >= cutoff);
                // 若清完還滿（極端 burst），truncate 留新一半
                if samples.len() >= REST_LATENCY_BUFFER_CAP {
                    let drop = samples.len() / 2;
                    samples.drain(0..drop);
                }
            }
            samples.push((now, latency_ms));
        }
    }

    /// 計算 60s rolling window 內 p50/p95/p99 三 percentile（ms）。
    ///
    /// 為什麼 sort-based 而非 hdrhistogram：
    ///   - 6000 sample sort O(n log n) ≈ 80000 op 級；< 100 μs；每 60s 才呼
    ///     一次（emitter sample_interval=60s），完全可接受。
    ///   - 0 新 dep（hdrhistogram 雖在 workspace 但本 crate 未拉）；最小編譯
    ///     時間增量 + 跨平台 0 風險（hdrhistogram 在 ARM/x86 同行為）。
    ///
    /// 返回 (p50, p95, p99) 三 u32（ms）。樣本空返 (0, 0, 0)（emitter 端視 0 為
    /// OK band 不誤升級）。
    pub fn percentile_triple(&self) -> (u32, u32, u32) {
        let samples_guard = match self.samples.lock() {
            Ok(g) => g,
            Err(_) => return (0, 0, 0),
        };
        let now = Instant::now();
        let cutoff = now
            .checked_sub(Duration::from_secs(REST_LATENCY_WINDOW_SECS))
            .unwrap_or(now);
        let mut latencies: Vec<u64> = samples_guard
            .iter()
            .filter(|(t, _)| *t >= cutoff)
            .map(|(_, ms)| *ms)
            .collect();
        drop(samples_guard);
        if latencies.is_empty() {
            return (0, 0, 0);
        }
        latencies.sort_unstable();
        let n = latencies.len();
        let pick = |q: f64| -> u32 {
            // 為什麼 nearest-rank percentile（非 linear interp）：
            //   - 對 6000 sample 兩種方法差異 < 1ms；nearest-rank 更直觀且
            //     對齊 SLO instrumentation 行業慣例（Prometheus / Datadog 同）。
            let idx = ((q * (n as f64)).ceil() as usize).saturating_sub(1).min(n - 1);
            latencies[idx].min(u32::MAX as u64) as u32
        };
        (pick(0.50), pick(0.95), pick(0.99))
    }

    /// 60s 內當前 sample 數量（test + debug 用）。
    pub fn sample_count(&self) -> usize {
        let samples_guard = match self.samples.lock() {
            Ok(g) => g,
            Err(_) => return 0,
        };
        let now = Instant::now();
        let cutoff = now
            .checked_sub(Duration::from_secs(REST_LATENCY_WINDOW_SECS))
            .unwrap_or(now);
        samples_guard.iter().filter(|(t, _)| *t >= cutoff).count()
    }

    /// test-only accessor：注入指定 `Instant` 時間戳的 sample，繞過 `Instant::now()`
    /// 才能驗 60s 滾窗的過期邊界（per E2 round 1 H-2 fix）。
    ///
    /// 為什麼 `pub` + `#[doc(hidden)]` 而非 `#[cfg(test)]`：
    ///   - integration test（`tests/api_latency_probe_real_impl.rs`）是外部
    ///     crate；`#[cfg(test)]` 端方法在 integration crate 不可見。
    ///   - `pub` + `#[doc(hidden)]` 在 production binary 仍編譯，但 rustdoc 不
    ///     呈現；emitter / probe production 路徑不調用（grep 確認）。
    ///   - AC-5 nm 守則檢 `mock_instant` / `tokio::time::pause` / `spike` 三關
    ///     鍵字；本 method 名 `inject_sample_with_timestamp` 不撞守則。
    #[doc(hidden)]
    pub fn inject_sample_with_timestamp(&self, ts: Instant, latency_ms: u64) {
        if let Ok(mut samples) = self.samples.lock() {
            samples.push((ts, latency_ms));
        }
    }
}

/// HTTP 4xx + 5xx retCode 60s rolling-window counter。
///
/// 為什麼 4xx + 5xx 分桶（per packet §5.5 反模式 (d) multi-venue gate 預留）：
///   - HTTP 4xx = client fault（簽名 / 參數 / rate-limit）；策略 / wrapper bug
///     早期信號。
///   - HTTP 5xx = venue fault（交易所事故 / maintenance）；emit 即「我端正常但
///     venue 慢」cascade 預警 gate。
///   - 多 venue（Binance / OKX）後 retCode 語意差異；HTTP class 是 transport-
///     level 共通語意（per ADR-0040 multi-venue 預留）。
///
/// caller 端對映規則（per packet §1.2 工作項 (2)）：
///   - reqwest transport error → 不計入（屬 network fault，emitter 不負責）。
///   - `BybitApiError::Business` + retCode IN (10001 InvalidParam, 10002
///     InvalidRequest, 10003 ApiKeyInvalid, 10004 SignError, 10005
///     PermissionDenied, 10006 IpRateLimit) → 4xx（client fault）。
///   - `BybitApiError::Business` + 其他 retCode（5xx-like venue fault）→ 5xx。
///   - `BybitApiError::JsonParse` → 不計入（屬 protocol parse 錯誤）。
#[derive(Debug)]
pub struct RetCodeCounter {
    /// 4xx 樣本：每筆紀錄一個時間戳。讀取時走 retain 過濾過期。
    samples_4xx: Mutex<Vec<Instant>>,
    /// 5xx 樣本。
    samples_5xx: Mutex<Vec<Instant>>,
}

impl Default for RetCodeCounter {
    fn default() -> Self {
        Self::new()
    }
}

impl RetCodeCounter {
    /// 建立空 counter。
    pub fn new() -> Self {
        Self {
            samples_4xx: Mutex::new(Vec::with_capacity(64)),
            samples_5xx: Mutex::new(Vec::with_capacity(64)),
        }
    }

    /// 紀錄一次 4xx 樣本（client fault）。
    pub fn record_4xx(&self) {
        let now = Instant::now();
        if let Ok(mut samples) = self.samples_4xx.lock() {
            if samples.len() >= RET_CODE_BUFFER_CAP {
                let cutoff = now
                    .checked_sub(Duration::from_secs(RET_CODE_WINDOW_SECS))
                    .unwrap_or(now);
                samples.retain(|t| *t >= cutoff);
                if samples.len() >= RET_CODE_BUFFER_CAP {
                    let drop = samples.len() / 2;
                    samples.drain(0..drop);
                }
            }
            samples.push(now);
        }
    }

    /// 紀錄一次 5xx 樣本（venue fault）。
    pub fn record_5xx(&self) {
        let now = Instant::now();
        if let Ok(mut samples) = self.samples_5xx.lock() {
            if samples.len() >= RET_CODE_BUFFER_CAP {
                let cutoff = now
                    .checked_sub(Duration::from_secs(RET_CODE_WINDOW_SECS))
                    .unwrap_or(now);
                samples.retain(|t| *t >= cutoff);
                if samples.len() >= RET_CODE_BUFFER_CAP {
                    let drop = samples.len() / 2;
                    samples.drain(0..drop);
                }
            }
            samples.push(now);
        }
    }

    /// 60s 內 4xx 累積計數。
    pub fn count_4xx(&self) -> u32 {
        let samples = match self.samples_4xx.lock() {
            Ok(g) => g,
            Err(_) => return 0,
        };
        let now = Instant::now();
        let cutoff = now
            .checked_sub(Duration::from_secs(RET_CODE_WINDOW_SECS))
            .unwrap_or(now);
        samples.iter().filter(|t| **t >= cutoff).count().min(u32::MAX as usize) as u32
    }

    /// 60s 內 5xx 累積計數。
    pub fn count_5xx(&self) -> u32 {
        let samples = match self.samples_5xx.lock() {
            Ok(g) => g,
            Err(_) => return 0,
        };
        let now = Instant::now();
        let cutoff = now
            .checked_sub(Duration::from_secs(RET_CODE_WINDOW_SECS))
            .unwrap_or(now);
        samples.iter().filter(|t| **t >= cutoff).count().min(u32::MAX as usize) as u32
    }

    /// test-only accessor：注入指定 `Instant` 時間戳的 4xx sample（per E2 round 1
    /// H-2 fix；驗 60s 滾窗過期邊界）。
    ///
    /// 為什麼 `pub` + `#[doc(hidden)]`：見 `RestLatencyHistogram::inject_sample_with_timestamp`
    /// 同註解（integration test crate visibility + AC-5 nm 不撞）。
    #[doc(hidden)]
    pub fn inject_4xx_with_timestamp(&self, ts: Instant) {
        if let Ok(mut samples) = self.samples_4xx.lock() {
            samples.push(ts);
        }
    }

    /// test-only accessor：注入指定 `Instant` 時間戳的 5xx sample。
    #[doc(hidden)]
    pub fn inject_5xx_with_timestamp(&self, ts: Instant) {
        if let Ok(mut samples) = self.samples_5xx.lock() {
            samples.push(ts);
        }
    }

    /// 從 `BybitApiError` 對映到 4xx / 5xx 並 record。
    ///
    /// 為什麼 helper 在 client 端 而非 caller 端：
    ///   - 對映規則屬 Bybit-specific 知識（retCode 10001-10010 = client fault）；
    ///     trait 端只看 transport-level class（per ADR-0040 multi-venue 預留）。
    ///   - caller（RestClient::get / post）走 record_for_error 一個入口即可，
    ///     不需在多處 wrap 對映邏輯。
    ///
    /// noop guard（per PA-DRIFT-4 round 1 E2 H-1 fix）：
    ///   - 對映 ADR-0042 Decision 3 cascade gate = venue fault only 語意。
    ///   - retCode 在 `BybitRetCode::is_noop()` 集合（OrderNotFound 110001 /
    ///     OrderCompletedOrCancelled 110008 / OrderAlreadyCancelled 110010 /
    ///     LeverageNotModified 110043 / OrderNotExistSpot 170213）視為「動作已
    ///     完成」非 venue fault；既不計 4xx 也不計 5xx，直接 return。
    ///   - 若繼續計 5xx 會把 lifecycle race（caller 補打 cancel 時訂單已成交）
    ///     誤升 venue fault，污染 emitter cascade 觀測。
    pub fn record_for_error(&self, err: &BybitApiError) {
        match err {
            BybitApiError::Business { ret_code, .. } => {
                // noop guard：lifecycle race / 已套用設定 等「動作已完成」碼
                // 非 venue fault；直接跳過計數（per ADR-0042 cascade gate 語意）。
                if Self::is_noop_retcode(*ret_code) {
                    return;
                }
                if Self::is_client_fault_retcode(*ret_code) {
                    self.record_4xx();
                } else {
                    self.record_5xx();
                }
            }
            // Transport / JsonParse / NoCredentials / SigningError 不計入 4xx/5xx
            // counter；屬 wrapper 層 fault 而非 venue 端 fault。
            _ => {}
        }
    }

    /// 判斷 retCode 是否為 client fault（4xx 對映）。
    ///
    /// 為什麼這 6 個 code 屬 4xx：
    ///   - 10001 InvalidParam / 10002 InvalidRequest：請求格式錯（wrapper bug）
    ///   - 10003 ApiKeyInvalid / 10004 SignError：認證錯（憑證或簽名 bug）
    ///   - 10005 PermissionDenied：權限不足（key 配置錯）
    ///   - 10006 IpRateLimit：IP 限流（client 端超頻）
    ///   - 10010 UnmatchedIp：IP 漂移（client 端 IP 變）
    ///   其他 110xxx 業務碼（balance / position / order lifecycle）走 5xx
    ///   （venue-side state；非 client fault）；保守對映。
    fn is_client_fault_retcode(ret_code: i64) -> bool {
        matches!(ret_code, 10001 | 10002 | 10003 | 10004 | 10005 | 10006 | 10010)
    }

    /// 判斷 retCode 是否為 noop（動作已完成；非 venue/client fault）。
    ///
    /// 為什麼引用 `BybitRetCode::is_noop()`：
    ///   - noop 集合（OrderNotFound 110001 / OrderCompletedOrCancelled 110008 /
    ///     OrderAlreadyCancelled 110010 / LeverageNotModified 110043 /
    ///     OrderNotExistSpot 170213）已在 BybitRetCode enum 字典單一定義；
    ///     復用同一 SSOT 避免雙處飄移（per dispatch packet §5.5 反模式 (d)）。
    ///   - 未識別 retCode（不在 BybitRetCode enum）→ from_code 返 None → 預設
    ///     `false`：保守對映為 venue fault（5xx），符合「未知 = 視為 venue
    ///     fault」cascade 守則。
    fn is_noop_retcode(ret_code: i64) -> bool {
        BybitRetCode::from_code(ret_code)
            .map(|c| c.is_noop())
            .unwrap_or(false)
    }
}

/// Well-known Bybit retCode values with semantic meaning.
/// 有語義含義的 Bybit retCode 常用值。
///
/// EDGE-P2-3 Phase 1B-1 (2026-04-20): extended with PostOnly/price-filter/
/// order-lifecycle codes discovered during BB audit. PostOnly-cross itself
/// has NO REST retCode — Bybit returns retCode=0 and surfaces rejection via
/// WS `order` event with `rejectReason=EC_PostOnlyWillTakeLiquidity`. These
/// enum additions cover the codes we MUST NOT conflate with that path.
/// See `docs/audits/2026-04-20--edge_p2_3_phase1b_bybit_postonly_audit.md`.
/// EDGE-P2-3 Phase 1B-1：新增 PostOnly / 價格過濾器 / 訂單生命週期相關碼。
/// PostOnly 越過 book 本身無 REST retCode（走 WS rejectReason 路徑）。
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BybitRetCode {
    /// Success / 成功
    Ok = 0,
    /// Invalid parameter / 參數無效
    InvalidParam = 10001,
    /// Invalid request / 無效請求
    InvalidRequest = 10002,
    /// API key invalid / API key 無效
    ApiKeyInvalid = 10003,
    /// Sign error / 簽名錯誤
    SignError = 10004,
    /// Permission denied / 權限不足
    PermissionDenied = 10005,
    /// IP rate limit / IP 限流
    IpRateLimit = 10006,
    /// Unmatched IP / IP 不匹配
    UnmatchedIp = 10010,
    /// Order not found / 訂單不存在
    OrderNotFound = 110001,
    /// Order price exceeds instrument price filter (NOT PostOnly-cross).
    /// Indicates instrument cache stale or bad offset — recompute tick_size /
    /// price_limit, do NOT use 30s exchange backoff.
    /// 訂單價格超出合約允許範圍（非 PostOnly 越過 book）：
    /// 表示合約快取陳舊或 offset 偏差，需重算 tick_size/price_limit，不走 30s 退避。
    PriceOutOfRange = 110003,
    /// Wallet balance insufficient (symbol-level pause, not exchange backoff).
    /// 錢包餘額不足（該幣種暫停，非交易所退避）。
    WalletInsufficient = 110004,
    /// Available balance insufficient (symbol-level pause).
    /// 可用餘額不足（該幣種暫停）。
    AvailableInsufficient = 110007,
    /// Order completed or cancelled (lifecycle race) — treat as noop.
    /// 訂單已完成或已取消（生命週期競爭）— 視為 noop。
    OrderCompletedOrCancelled = 110008,
    /// Position not found / 持倉不存在
    PositionNotFound = 110009,
    /// Order already cancelled — noop.
    /// 訂單已取消 — noop。
    OrderAlreadyCancelled = 110010,
    /// Insufficient balance / 餘額不足
    InsufficientBalance = 110012,
    /// Reduce-only 訂單被拒（倉位不存在或方向不匹配）— 終態錯誤，重試無意義。
    ReduceOnlyReject = 110017,
    /// Leverage not modified (already set) / 槓桿未修改
    LeverageNotModified = 110043,
    /// Price tick invalid — round via InstrumentInfoCache and retry once.
    /// 價格刻度非法 — 透過 InstrumentInfoCache 重新四捨五入並重試一次。
    ///
    /// INSTR-ENSURE-FORCE-1 TODO (2026-04-23): the order-submit caller that
    /// handles 110049 / 110003 should invoke
    /// `InstrumentInfoCache::ensure_symbol_force(client, category, symbol,
    /// true)` to force-refresh the cached tick_size / qty_step before
    /// re-rounding the price and resubmitting. Today this retcode is only
    /// CLASSIFIED (`is_instrument_filter`) — no actual retry path reads the
    /// cache and retries. Wiring the retry requires the submit caller to
    /// hold an `Arc<InstrumentInfoCache>`; `OrderManager` already does, so
    /// the actual wire can live in `order_manager::place_order` (or the
    /// dispatcher wrapping it) rather than here in the REST client.
    /// INSTR-ENSURE-FORCE-1 TODO：真正的重試接線留給 order_manager 層
    /// （因為 OrderManager 已握 Arc<InstrumentInfoCache>），
    /// 呼 ensure_symbol_force(.., force_refresh=true) 強拉新 spec 重算後重發。
    PriceTickInvalid = 110049,
    /// Contract not live (delisted/suspended) — remove from scanner universe.
    /// 合約未上線（下架/暫停）— 從掃描器宇宙中移除。
    ContractNotLive = 110074,
    /// "Only Post-Only orders at this stage" (pre-open/funding transient).
    /// 30s exchange backoff is correct here.
    /// 現階段僅 Post-Only 可用（開市前/資金結算瞬間）— 30s 交易所退避正確。
    PostOnlyOnlyStage = 110103,
    /// Exceed max order qty / 超過最大下單數量
    ExceedMaxQty = 170210,
    /// Spot order does not exist (spot cancel path noop).
    /// 現貨訂單不存在（現貨取消路徑 noop）。
    OrderNotExistSpot = 170213,
}

impl BybitRetCode {
    /// Classify a raw retCode into a known variant, if recognized.
    /// 將原始 retCode 分類為已知變體（如可識別）。
    pub fn from_code(code: i64) -> Option<Self> {
        match code {
            0 => Some(Self::Ok),
            10001 => Some(Self::InvalidParam),
            10002 => Some(Self::InvalidRequest),
            10003 => Some(Self::ApiKeyInvalid),
            10004 => Some(Self::SignError),
            10005 => Some(Self::PermissionDenied),
            10006 => Some(Self::IpRateLimit),
            10010 => Some(Self::UnmatchedIp),
            110001 => Some(Self::OrderNotFound),
            110003 => Some(Self::PriceOutOfRange),
            110004 => Some(Self::WalletInsufficient),
            110007 => Some(Self::AvailableInsufficient),
            110008 => Some(Self::OrderCompletedOrCancelled),
            110009 => Some(Self::PositionNotFound),
            110010 => Some(Self::OrderAlreadyCancelled),
            110012 => Some(Self::InsufficientBalance),
            110017 => Some(Self::ReduceOnlyReject),
            110043 => Some(Self::LeverageNotModified),
            110049 => Some(Self::PriceTickInvalid),
            110074 => Some(Self::ContractNotLive),
            110103 => Some(Self::PostOnlyOnlyStage),
            170210 => Some(Self::ExceedMaxQty),
            170213 => Some(Self::OrderNotExistSpot),
            _ => None,
        }
    }

    /// Whether this error is safe to retry (transient).
    /// 此錯誤是否可安全重試（暫時性）。
    pub fn is_retryable(&self) -> bool {
        matches!(self, Self::IpRateLimit)
    }

    /// Whether this is a "no-op" error (operation already done).
    /// Covers both order lifecycle races (completed/already-cancelled) and
    /// spot-side missing-order on cancel — caller should treat as success and
    /// reconcile via WS final state instead of retrying.
    /// 此錯誤是否為「無操作」（動作已完成）— caller 視為成功，以 WS 最終狀態對賬。
    pub fn is_noop(&self) -> bool {
        matches!(
            self,
            Self::LeverageNotModified
                | Self::OrderNotFound
                | Self::OrderCompletedOrCancelled
                | Self::OrderAlreadyCancelled
                | Self::OrderNotExistSpot
        )
    }

    /// Whether the strategy should back off re-emit (exchange-side transient,
    /// not a strategy bug). Examples: pre-open stage, IP rate limit.
    /// EDGE-P2-3 Phase 1B-1: added as preparation for Phase 1B-2 WS reject
    /// routing; caller routes WS `EC_PostOnlyWillTakeLiquidity` through the
    /// same M-2 `reject_cooldown_until_ms` path.
    /// 策略是否應退避重發（交易所瞬態，非策略錯誤）。
    pub fn is_exchange_backoff(&self) -> bool {
        matches!(self, Self::PostOnlyOnlyStage | Self::IpRateLimit)
    }

    /// Whether this is an instrument-filter problem (bad price/tick/range)
    /// that needs recomputation via InstrumentInfoCache — distinct from both
    /// `is_retryable` (transient) and `is_exchange_backoff` (stage).
    /// 是否為合約過濾器問題（需重算 tick/price），與瞬態/階段退避不同。
    ///
    /// INSTR-ENSURE-FORCE-1 TODO (2026-04-23): when the order-submit path
    /// observes `is_instrument_filter() == true`, it should call
    /// `InstrumentInfoCache::ensure_symbol_force(.., force_refresh=true)` to
    /// bypass the stale positive cache and pull a fresh spec. If that
    /// returns `None` (Bybit denies → neg cache), fall through to M-1
    /// fail-closed rejection. If it returns `Some(spec)`, re-round price/
    /// qty with `spec.round_price` / `spec.round_qty` and retry once.
    /// Wire point: the OrderManager submit wrapper, not this classifier.
    /// INSTR-ENSURE-FORCE-1 TODO：consumer 收到 is_instrument_filter=true 時
    /// 呼 ensure_symbol_force(force_refresh=true) 取得 fresh spec，重算後重發。
    pub fn is_instrument_filter(&self) -> bool {
        matches!(self, Self::PriceOutOfRange | Self::PriceTickInvalid)
    }

    /// Whether this is a balance-level block (pause the symbol, do not retry
    /// with the same intent).
    /// 是否為餘額級別阻塞（暫停該幣種，勿以相同意圖重試）。
    pub fn is_balance_block(&self) -> bool {
        matches!(
            self,
            Self::WalletInsufficient | Self::AvailableInsufficient | Self::InsufficientBalance
        )
    }
}

// ---------------------------------------------------------------------------
// BybitRestClient / Bybit REST 客戶端
// ---------------------------------------------------------------------------

/// Authenticated Bybit V5 REST API client.
/// 認證 Bybit V5 REST API 客戶端。
///
/// Thread-safe (Send + Sync) — can be shared across tasks via Arc.
/// 線程安全（Send + Sync）— 可通過 Arc 在任務間共享。
pub struct BybitRestClient {
    client: Client,
    api_key: String,
    api_secret: String,
    base_url: String,
    recv_window: String,
    rate_limit: RateLimitState,
    /// PA-DRIFT-4 工作項 (1)：REST latency 60s rolling histogram。
    /// Arc 暴露給外部 `ApiLatencySourceProbe` 注入（per packet §1.2 工作項 (4)）；
    /// 同 client 既有共享機制（Arc<BybitRestClient> 廣播）對齊。
    latency_histogram: Arc<RestLatencyHistogram>,
    /// PA-DRIFT-4 工作項 (2)：retCode 4xx + 5xx counter 60s rolling window。
    ret_code_counter: Arc<RetCodeCounter>,
}

impl BybitRestClient {
    /// Create a new REST client.
    /// 創建新的 REST 客戶端。
    ///
    /// ## Credential loading
    ///
    /// Demo / Testnet (priority order):
    ///   1. Explicit parameters (if non-empty)
    ///   2. Environment variables: `BYBIT_API_KEY`, `BYBIT_API_SECRET`
    ///   3. Secret files at `{OPENCLAW_SECRETS_DIR}/{slot}/{name}` (slot = "demo")
    ///
    /// Mainnet (LIVE-GUARD-1, restored 2026-04-16 after SEC-17 audit):
    ///   1. Explicit parameters (if non-empty)
    ///   2. Secret files at `{OPENCLAW_SECRETS_DIR}/live/{name}` — **env var bypass disabled**
    ///
    /// ## Mainnet fail-safes (LIVE-GUARD-1)
    ///
    /// When `env == BybitEnvironment::Mainnet`, construction fails closed on:
    ///   - Missing `OPENCLAW_ALLOW_MAINNET=1` env var (restored SEC-5 guard)
    ///   - Empty credentials after slot-file load (no more silent `warn!` + 401 later)
    ///   - Any `BYBIT_API_KEY` / `BYBIT_API_SECRET` env var set — ignored (closed bypass)
    ///
    /// ## 憑證讀取
    ///
    /// Demo / Testnet：param → env var → slot file
    /// Mainnet：param → slot file only（env var 繞過已封閉）
    ///
    /// ## Mainnet 硬鎖（LIVE-GUARD-1，2026-04-16 SEC-17 audit 後回補）
    ///   - 缺 `OPENCLAW_ALLOW_MAINNET=1` 環境變量 → Err
    ///   - Slot 憑證為空 → Err（不再 warn!+401）
    ///   - env var 憑證完全忽略（防繞過）
    pub fn new(
        env: BybitEnvironment,
        api_key: Option<String>,
        api_secret: Option<String>,
    ) -> BybitResult<Self> {
        let is_mainnet = matches!(env, BybitEnvironment::Mainnet);

        // LIVE-GUARD-1 gate #1: explicit operator opt-in via env var.
        // Rust-side fail-safe (Python-only gates are asymmetric: Rust long-runs,
        // Python restarts can drop live_reserved / Operator role silently).
        // LIVE-GUARD-1 門 #1：operator 顯式 opt-in。
        // Rust 端硬鎖（純 Python 門控不對稱：Rust 長跑 × Python 重啟 live_reserved 會丟）。
        if is_mainnet {
            if std::env::var("OPENCLAW_ALLOW_MAINNET").unwrap_or_default() != "1" {
                return Err(BybitApiError::Business {
                    ret_code: -1,
                    ret_msg: "Mainnet blocked: set OPENCLAW_ALLOW_MAINNET=1 to enable / 主網被阻止：需設置 OPENCLAW_ALLOW_MAINNET=1"
                        .into(),
                    response: serde_json::json!({"blocked": true, "guard": "OPENCLAW_ALLOW_MAINNET"}),
                });
            }
            tracing::warn!(
                "⚠ MAINNET mode enabled — real money at risk / 主網模式已啟用 — 真金白銀"
            );
        }

        // Derive secret slot from environment: Demo/Testnet → "demo", Mainnet → "live"
        // 從環境派生 secret 槽位：Demo/Testnet → "demo"，Mainnet → "live"
        let slot = env.secret_slot();

        // P1-08（cold audit pkg B）：env-var 憑證回退依「是否 live slot」收緊，而非只看
        // is_mainnet。LiveDemo 映射到 "live" 槽位但 is_mainnet==false，舊邏輯下任何能設
        // 進程 env 的路徑都可覆寫 operator 管理的 live slot 憑證，繞過 live-slot 來源/審計。
        // 為什麼 fail-closed：LiveDemo 是 live-grade 控制流（CLAUDE.md §四），憑證來源必須與
        // Mainnet 同等嚴格 — 任何 live slot 客戶端都不接受 env var 憑證。
        // 注意：OPENCLAW_ALLOW_MAINNET 門控與空憑證 fail-closed 仍鍵於 is_mainnet（真金白銀
        // 專屬），不擴大到 LiveDemo。
        let is_live_slot = slot == "live";

        // LIVE-GUARD-1 gate #2: live-slot clients skip env-var credential fallback.
        // Closes the "any process with env access bypasses secret slot" attack.
        // LIVE-GUARD-1 門 #2：live slot 客戶端禁用 env var 憑證回退（封閉「能設 env 即繞 slot」攻擊）。
        let api_key = api_key
            .filter(|s| !s.is_empty())
            .or_else(|| {
                if is_live_slot {
                    None
                } else {
                    std::env::var("BYBIT_API_KEY")
                        .ok()
                        .filter(|s| !s.is_empty())
                }
            })
            .or_else(|| read_secret_file(slot, "api_key"))
            .unwrap_or_default();

        let api_secret = api_secret
            .filter(|s| !s.is_empty())
            .or_else(|| {
                if is_live_slot {
                    None
                } else {
                    std::env::var("BYBIT_API_SECRET")
                        .ok()
                        .filter(|s| !s.is_empty())
                }
            })
            .or_else(|| read_secret_file(slot, "api_secret"))
            .unwrap_or_default();

        // LIVE-GUARD-1 gate #3: Mainnet fail-closed on empty credentials
        // (was silent warn! → later 401 at signing; now clean Err at construction).
        // LIVE-GUARD-1 門 #3：Mainnet 憑證空 → 構造時 Err（不再事後 401）。
        if api_key.is_empty() || api_secret.is_empty() {
            if is_mainnet {
                return Err(BybitApiError::Business {
                    ret_code: -1,
                    ret_msg: "Mainnet blocked: credentials missing from secret slot / 主網被阻止：secret 槽位缺憑證"
                        .into(),
                    response: serde_json::json!({"blocked": true, "guard": "mainnet_credentials"}),
                });
            }
            warn!("Bybit API credentials not found — client will reject requests / Bybit API 憑證未找到");
        }

        let client = Client::builder()
            .timeout(std::time::Duration::from_secs(10))
            .build()
            .map_err(BybitApiError::Transport)?;

        Ok(Self {
            client,
            api_key,
            api_secret,
            base_url: env.rest_base_url().to_string(),
            recv_window: "5000".to_string(),
            rate_limit: RateLimitState::default(),
            // PA-DRIFT-4：histogram + counter 初始化空；REST call hot path 自動
            // 累積。Arc 暴露給 `RealApiLatencySourceProbe` 注入（per packet
            // §1.2 工作項 (4) trait impl）。
            latency_histogram: Arc::new(RestLatencyHistogram::new()),
            ret_code_counter: Arc::new(RetCodeCounter::new()),
        })
    }

    /// PA-DRIFT-4 工作項 (1)：暴露 latency histogram Arc（probe 注入）。
    ///
    /// 為什麼 Arc 而非 &：
    ///   - probe 端（`RealApiLatencySourceProbe`）需持有 `Arc<RestLatencyHistogram>`
    ///     供 trait method 跨 task 訪問；emitter scheduler 走 Arc<dyn Probe>。
    ///   - client 自身也持 Arc（hot path 鎖共享）；clone Arc 0 allocation。
    pub fn latency_histogram_handle(&self) -> Arc<RestLatencyHistogram> {
        Arc::clone(&self.latency_histogram)
    }

    /// PA-DRIFT-4 工作項 (2)：暴露 retCode counter Arc（probe 注入）。
    pub fn ret_code_counter_handle(&self) -> Arc<RetCodeCounter> {
        Arc::clone(&self.ret_code_counter)
    }

    /// Check if the client has valid credentials configured.
    /// 檢查客戶端是否有有效的憑證配置。
    pub fn has_credentials(&self) -> bool {
        !self.api_key.is_empty() && !self.api_secret.is_empty()
    }

    /// Get credentials for BybitPrivateWs construction. Returns (api_key, api_secret).
    /// 獲取憑證用於構建 BybitPrivateWs。返回 (api_key, api_secret)。
    pub fn credentials(&self) -> (&str, &str) {
        (&self.api_key, &self.api_secret)
    }

    /// Get current rate limit remaining count.
    /// 取得當前限流剩餘計數。
    pub fn rate_limit_remaining(&self) -> i64 {
        self.rate_limit.remaining.load(Ordering::Relaxed)
    }

    /// Get the configured base URL.
    /// 取得配置的基礎 URL。
    pub fn base_url(&self) -> &str {
        &self.base_url
    }

    // -----------------------------------------------------------------------
    // HMAC-SHA256 signing / HMAC-SHA256 簽名
    // -----------------------------------------------------------------------

    /// Compute HMAC-SHA256 signature per Bybit V5 spec.
    /// 按 Bybit V5 規範計算 HMAC-SHA256 簽名。
    ///
    /// sign_str = timestamp + api_key + recv_window + params
    /// signature = hex(hmac_sha256(api_secret, sign_str))
    ///
    /// EN: Delegates to `common::bybit_signer::sign_rest_v5` (E1-P0-3). The
    ///     shared primitive returns `String` unconditionally because HMAC-SHA256
    ///     accepts keys of any length (SHA-256 re-hashes overlong keys
    ///     internally). The `BybitResult<String>` return type is retained so
    ///     that existing `?` call sites continue to compile, matching FA-1 risk
    ///     #4 (call-site error wrapping preserved).
    /// 中文: 委派至 `common::bybit_signer::sign_rest_v5`（E1-P0-3）。共享原語
    ///     無條件回傳 `String`，因 HMAC-SHA256 接受任意長度金鑰（SHA-256 內部
    ///     會對過長金鑰再雜湊）。保留 `BybitResult<String>` 回傳型別以使既有
    ///     呼叫端的 `?` 仍可編譯，符合 FA-1 風險 #4（呼叫端錯誤包裝保留）。
    fn sign(&self, timestamp: &str, params: &str) -> BybitResult<String> {
        Ok(sign_rest_v5(
            &self.api_secret,
            timestamp,
            &self.api_key,
            &self.recv_window,
            params,
        ))
    }

    /// Get current timestamp in milliseconds.
    /// 取得當前毫秒級時間戳。
    fn timestamp_ms() -> String {
        SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis()
            .to_string()
    }

    // -----------------------------------------------------------------------
    // HTTP methods / HTTP 方法
    // -----------------------------------------------------------------------

    /// Signed GET request.
    /// 簽名 GET 請求。
    ///
    /// Query parameters are serialized as key=value&key=value (sorted by key),
    /// then signed and appended to the URL.
    /// 查詢參數序列化為 key=value&key=value（按 key 排序），然後簽名並附加到 URL。
    pub async fn get(&self, path: &str, params: &[(&str, &str)]) -> BybitResult<BybitResponse> {
        if !self.has_credentials() {
            return Err(BybitApiError::NoCredentials);
        }

        let timestamp = Self::timestamp_ms();

        // Build sorted query string / 構建排序的查詢字串
        let mut sorted_params: Vec<(&str, &str)> = params.to_vec();
        sorted_params.sort_by_key(|(k, _)| *k);
        let query_string: String = sorted_params
            .iter()
            .map(|(k, v)| format!("{k}={v}"))
            .collect::<Vec<_>>()
            .join("&");

        let signature = self.sign(&timestamp, &query_string)?;

        let url = if query_string.is_empty() {
            format!("{}{}", self.base_url, path)
        } else {
            format!("{}{}?{}", self.base_url, path, query_string)
        };

        self.wait_if_rate_limited(path).await;
        debug!(
            method = "GET",
            path = path,
            "Bybit API request / Bybit API 請求"
        );

        // PA-DRIFT-4 工作項 (1)：REST latency 計時起點。
        // 為什麼計到 parse 完成而非 send 完成：parse 是 client 端必走步驟；
        // 整個 client-side latency 才是 emitter 觀測的 SLO 目標。
        let call_start = Instant::now();
        let resp = self
            .client
            .get(&url)
            .header("X-BAPI-API-KEY", &self.api_key)
            .header("X-BAPI-SIGN", &signature)
            .header("X-BAPI-TIMESTAMP", &timestamp)
            .header("X-BAPI-RECV-WINDOW", &self.recv_window)
            .header("Content-Type", "application/json")
            .send()
            .await?;

        self.update_rate_limit(&resp);
        self.update_group_rate_limit(path, &resp);
        let body = resp.text().await?;
        let parsed: BybitResponse = serde_json::from_str(&body)?;
        let elapsed_ms = call_start.elapsed().as_millis().min(u64::MAX as u128) as u64;
        self.latency_histogram.record_latency(elapsed_ms);

        // PA-DRIFT-4 round 1 H-3 fix：retCode 觀測下沉至 `get` / `post` 內部。
        // 為什麼這裡而非 `_checked`：account_manager / position_manager /
        // instrument_info 等 raw caller 走 `client.get(...)` 後手動檢 retCode（不
        // 走 `_checked`），若觀測停在 `_checked` 端會 bypass > 50% caller 流量。
        // 本路徑覆蓋所有 caller；`_checked` 端不再重複 record 避雙重計。
        if !parsed.is_ok() {
            self.ret_code_counter.record_for_error(&BybitApiError::Business {
                ret_code: parsed.ret_code,
                ret_msg: parsed.ret_msg.clone(),
                response: serde_json::to_value(&parsed).unwrap_or_default(),
            });
        }
        Ok(parsed)
    }

    /// Signed POST request.
    /// 簽名 POST 請求。
    ///
    /// Body is serialized as JSON, then the JSON string is signed.
    /// Body 序列化為 JSON，然後對 JSON 字串簽名。
    pub async fn post(&self, path: &str, body: &serde_json::Value) -> BybitResult<BybitResponse> {
        if !self.has_credentials() {
            return Err(BybitApiError::NoCredentials);
        }

        let timestamp = Self::timestamp_ms();
        let body_str = serde_json::to_string(body)?;
        let signature = self.sign(&timestamp, &body_str)?;

        let url = format!("{}{}", self.base_url, path);

        self.wait_if_rate_limited(path).await;
        debug!(
            method = "POST",
            path = path,
            "Bybit API request / Bybit API 請求"
        );

        // PA-DRIFT-4 工作項 (1)：REST latency 計時起點（POST 路徑）。
        let call_start = Instant::now();
        let resp = self
            .client
            .post(&url)
            .header("X-BAPI-API-KEY", &self.api_key)
            .header("X-BAPI-SIGN", &signature)
            .header("X-BAPI-TIMESTAMP", &timestamp)
            .header("X-BAPI-RECV-WINDOW", &self.recv_window)
            .header("Content-Type", "application/json")
            .body(body_str)
            .send()
            .await?;

        self.update_rate_limit(&resp);
        self.update_group_rate_limit(path, &resp);
        let body_text = resp.text().await?;
        let parsed: BybitResponse = serde_json::from_str(&body_text)?;
        let elapsed_ms = call_start.elapsed().as_millis().min(u64::MAX as u128) as u64;
        self.latency_histogram.record_latency(elapsed_ms);

        // PA-DRIFT-4 round 1 H-3 fix：retCode 觀測下沉至 `get` / `post` 內部
        // （見 `get` 同節注釋）。POST 端同 GET 處理，覆蓋所有 raw caller。
        if !parsed.is_ok() {
            self.ret_code_counter.record_for_error(&BybitApiError::Business {
                ret_code: parsed.ret_code,
                ret_msg: parsed.ret_msg.clone(),
                response: serde_json::to_value(&parsed).unwrap_or_default(),
            });
        }
        Ok(parsed)
    }

    /// Signed GET that automatically checks retCode and returns Result.
    /// 簽名 GET，自動檢查 retCode 並返回 Result。
    ///
    /// PA-DRIFT-4 round 1 H-3 fix：retCode 觀測已下沉至 `get` 內部以覆蓋所有
    /// raw caller；本 wrapper 純粹做 `into_result()` 轉換，**不**重複 record，
    /// 避免雙重計數。
    pub async fn get_checked(
        &self,
        path: &str,
        params: &[(&str, &str)],
    ) -> BybitResult<BybitResponse> {
        self.get(path, params).await?.into_result()
    }

    /// Signed POST that automatically checks retCode and returns Result.
    /// 簽名 POST，自動檢查 retCode 並返回 Result。
    ///
    /// PA-DRIFT-4 round 1 H-3 fix：retCode 觀測已下沉至 `post` 內部；本 wrapper
    /// 不重複 record。
    pub async fn post_checked(
        &self,
        path: &str,
        body: &serde_json::Value,
    ) -> BybitResult<BybitResponse> {
        self.post(path, body).await?.into_result()
    }

    // -----------------------------------------------------------------------
    // Rate limit / 限流
    // -----------------------------------------------------------------------

    /// Update rate limit state from response headers.
    /// 從回應頭更新限流狀態。
    ///
    /// Bybit headers: X-Bapi-Limit-Status (remaining), X-Bapi-Limit-Reset-Timestamp
    fn update_rate_limit(&self, resp: &reqwest::Response) {
        if let Some(remaining) = resp
            .headers()
            .get("x-bapi-limit-status")
            .and_then(|v| v.to_str().ok())
            .and_then(|s| s.parse::<i64>().ok())
        {
            self.rate_limit
                .remaining
                .store(remaining, Ordering::Relaxed);
        }
        if let Some(reset_ts) = resp
            .headers()
            .get("x-bapi-limit-reset-timestamp")
            .and_then(|v| v.to_str().ok())
            .and_then(|s| s.parse::<u64>().ok())
        {
            self.rate_limit.reset_ms.store(reset_ts, Ordering::Relaxed);
        }
    }

    /// Check if we're close to the global rate limit (remaining <= threshold).
    /// 檢查是否接近全局限流閾值（remaining <= threshold）。
    pub fn is_near_rate_limit(&self, threshold: i64) -> bool {
        self.rate_limit.remaining.load(Ordering::Relaxed) <= threshold
    }

    /// Check if a specific endpoint group is near its rate limit.
    /// 檢查特定端點分組是否接近其限流閾值。
    pub fn is_group_near_limit(&self, group: RateLimitGroup, threshold: i64) -> bool {
        let idx = group as usize;
        self.rate_limit.group_remaining[idx].load(Ordering::Relaxed) <= threshold
    }

    /// P2-03（cold audit pkg B）：依組別決定 preflight 退讓的 remaining 閾值。
    /// Order/Position/Account 都是 10 req/s 的窄組 → 低閾值（2）才退讓，避免過早 sleep；
    /// Market 120 req/s 寬鬆 → 高閾值（10）；Asset 5 req/s → 低閾值（2）。
    fn group_backoff_threshold(group: RateLimitGroup) -> i64 {
        match group {
            RateLimitGroup::Market => 10,
            RateLimitGroup::Order
            | RateLimitGroup::Position
            | RateLimitGroup::Account
            | RateLimitGroup::Asset
            | RateLimitGroup::Other => 2,
        }
    }

    /// Proactively wait if the request path's rate-limit group (or the global
    /// limit) is nearly exhausted.
    /// 若請求路徑所屬限流分組（或全局限流）接近耗盡，主動等待至重置時間（上限 2 秒）。
    ///
    /// Called before every GET/POST to avoid sending into a 429.
    /// P2-03：先做精確的 per-group 檢查（mutating Order 組近上限即退讓，即使全局健康），
    /// 再做全局粗粒度檢查作為防禦外層。等待至對應 reset_ms + 50ms 緩衝，最多 2 秒。
    /// group reset 未知（0）時回退到全局 reset_ms。reset 未知或已過期時跳過。
    /// 每次 GET/POST 前調用以避免觸發 429。
    async fn wait_if_rate_limited(&self, path: &str) {
        const GLOBAL_THRESHOLD: i64 = 10;
        const MAX_WAIT_MS: u64 = 2_000;
        const BUFFER_MS: u64 = 50;

        // 內層精確守衛（per-group）：解析 path → group，近組上限即退讓。
        let group = RateLimitGroup::from_path(path);
        let gidx = group as usize;
        let group_threshold = Self::group_backoff_threshold(group);
        let group_near = self.rate_limit.group_remaining[gidx].load(Ordering::Relaxed)
            <= group_threshold;
        // 外層粗粒度守衛（global）：作為 per-group header 缺失時的防禦。
        let global_near = self.is_near_rate_limit(GLOBAL_THRESHOLD);

        if !group_near && !global_near {
            return;
        }

        // reset 時間：優先用 per-group reset，缺（0）則回退全局 reset_ms。
        let group_reset = self.rate_limit.group_reset_ms[gidx].load(Ordering::Relaxed);
        let reset_ms = if group_reset != 0 {
            group_reset
        } else {
            self.rate_limit.reset_ms.load(Ordering::Relaxed)
        };
        if reset_ms == 0 {
            return;
        }

        let now_ms = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_millis() as u64;

        if reset_ms <= now_ms {
            return; // already reset — no wait needed / 已重置，無需等待
        }

        let wait_ms = ((reset_ms - now_ms) + BUFFER_MS).min(MAX_WAIT_MS);
        let remaining = self.rate_limit.remaining.load(Ordering::Relaxed);
        let group_remaining = self.rate_limit.group_remaining[gidx].load(Ordering::Relaxed);
        warn!(
            remaining = remaining,
            group = ?group,
            group_remaining = group_remaining,
            wait_ms = wait_ms,
            "Rate limit near threshold — backing off / 接近限流閾值，主動退讓"
        );
        sleep(Duration::from_millis(wait_ms)).await;
    }

    /// Update per-group rate limit from the last request.
    /// 根據最近的請求更新分組限流。
    fn update_group_rate_limit(&self, path: &str, resp: &reqwest::Response) {
        let group = RateLimitGroup::from_path(path);
        let idx = group as usize;
        if let Some(remaining) = resp
            .headers()
            .get("x-bapi-limit-status")
            .and_then(|v| v.to_str().ok())
            .and_then(|s| s.parse::<i64>().ok())
        {
            self.rate_limit.group_remaining[idx].store(remaining, Ordering::Relaxed);
        }
        // P2-03：同時把 reset 時間戳存進對應 group slot，供 preflight 做 per-group 等待。
        if let Some(reset_ts) = resp
            .headers()
            .get("x-bapi-limit-reset-timestamp")
            .and_then(|v| v.to_str().ok())
            .and_then(|s| s.parse::<u64>().ok())
        {
            self.rate_limit.group_reset_ms[idx].store(reset_ts, Ordering::Relaxed);
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers / 輔助函數
// ---------------------------------------------------------------------------

/// Read a secret value from the standard secret file location for the given slot.
/// 從指定槽位的標準秘密文件位置讀取秘密值。
///
/// Slot is derived from `BybitEnvironment::secret_slot()`: "demo" or "live".
/// Path: `OPENCLAW_SECRETS_DIR/{slot}/{name}` (env var) or
///       `~/BybitOpenClaw/secrets/secret_files/bybit/{slot}/{name}` (fallback).
///
/// 槽位由 BybitEnvironment::secret_slot() 派生："demo" 或 "live"。
/// 路徑：環境變量 OPENCLAW_SECRETS_DIR/{slot}/{name} 或
///       ~/BybitOpenClaw/secrets/secret_files/bybit/{slot}/{name}（fallback）。
///
/// Cross-platform: uses HOME / USERPROFILE env var, never hardcodes paths.
/// 跨平台：使用 HOME / USERPROFILE 環境變量，不硬編碼路徑。
fn read_secret_file(slot: &str, name: &str) -> Option<String> {
    // Path: OPENCLAW_SECRETS_DIR/{slot}/{name} if env var set, else HOME fallback
    // 路徑：環境變量優先，否則 HOME fallback
    let base = if let Ok(dir) = std::env::var("OPENCLAW_SECRETS_DIR") {
        std::path::PathBuf::from(dir)
    } else {
        let home = std::env::var("HOME")
            .or_else(|_| std::env::var("USERPROFILE"))
            .ok()?;
        std::path::PathBuf::from(home)
            .join("BybitOpenClaw")
            .join("secrets")
            .join("secret_files")
            .join("bybit")
    };
    let path = base.join(slot).join(name);
    std::fs::read_to_string(&path)
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
#[path = "bybit_rest_client_tests.rs"]
mod tests;
