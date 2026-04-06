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

use hmac::{Hmac, Mac};
use reqwest::Client;
use sha2::Sha256;
use std::sync::atomic::{AtomicI64, AtomicU64, Ordering};
use std::time::{Duration, SystemTime, UNIX_EPOCH};
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
}

impl BybitEnvironment {
    /// Get the base REST URL for this environment.
    /// 取得此環境的基礎 REST URL。
    pub fn rest_base_url(&self) -> &'static str {
        match self {
            Self::Demo => "https://api-demo.bybit.com",
            Self::Testnet => "https://api-testnet.bybit.com",
            Self::Mainnet => "https://api.bybit.com",
        }
    }

    /// Get the private WebSocket URL for this environment.
    /// 取得此環境的私有 WebSocket URL。
    pub fn private_ws_url(&self) -> &'static str {
        match self {
            Self::Demo => "wss://stream-demo.bybit.com/v5/private",
            Self::Testnet => "wss://stream-testnet.bybit.com/v5/private",
            Self::Mainnet => "wss://stream.bybit.com/v5/private",
        }
    }
}

impl Default for BybitEnvironment {
    fn default() -> Self {
        Self::Demo // Safe default — never accidentally hit mainnet
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
    pub fn from_path(path: &str) -> Self {
        if path.starts_with("/v5/order/") || path.starts_with("/v5/execution/") {
            Self::Order
        } else if path.starts_with("/v5/position/") {
            Self::Position
        } else if path.starts_with("/v5/account/") {
            Self::Account
        } else if path.starts_with("/v5/market/") || path.starts_with("/v5/spot-lever-token/") {
            Self::Market
        } else if path.starts_with("/v5/asset/") || path.starts_with("/v5/spot-margin") {
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
        }
    }
}

/// Well-known Bybit retCode values with semantic meaning.
/// 有語義含義的 Bybit retCode 常用值。
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
    /// Insufficient balance / 餘額不足
    InsufficientBalance = 110012,
    /// Leverage not modified (already set) / 槓桿未修改
    LeverageNotModified = 110043,
    /// Position not found / 持倉不存在
    PositionNotFound = 110009,
    /// Exceed max order qty / 超過最大下單數量
    ExceedMaxQty = 170210,
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
            110012 => Some(Self::InsufficientBalance),
            110043 => Some(Self::LeverageNotModified),
            110009 => Some(Self::PositionNotFound),
            170210 => Some(Self::ExceedMaxQty),
            _ => None,
        }
    }

    /// Whether this error is safe to retry (transient).
    /// 此錯誤是否可安全重試（暫時性）。
    pub fn is_retryable(&self) -> bool {
        matches!(self, Self::IpRateLimit)
    }

    /// Whether this is a "no-op" error (operation already done).
    /// 此錯誤是否為"無操作"錯誤（操作已完成）。
    pub fn is_noop(&self) -> bool {
        matches!(self, Self::LeverageNotModified | Self::OrderNotFound)
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
}

impl BybitRestClient {
    /// Create a new REST client.
    /// 創建新的 REST 客戶端。
    ///
    /// Reads API credentials from:
    ///   1. Explicit parameters (if non-empty)
    ///   2. Environment variables: BYBIT_API_KEY, BYBIT_API_SECRET
    ///   3. Secret files: ~/BybitOpenClaw/secrets/secret_files/bybit/demo/api_key
    ///
    /// 讀取 API 憑證順序：
    ///   1. 顯式參數（非空時）
    ///   2. 環境變量：BYBIT_API_KEY, BYBIT_API_SECRET
    ///   3. 秘密文件：~/BybitOpenClaw/secrets/secret_files/bybit/demo/api_key
    pub fn new(
        env: BybitEnvironment,
        api_key: Option<String>,
        api_secret: Option<String>,
    ) -> BybitResult<Self> {
        // SEC-5: Mainnet guard — require explicit env var to prevent accidental Live usage
        // SEC-5：主網防護 — 需要明確環境變量以防止意外使用 Live
        if matches!(env, BybitEnvironment::Mainnet) {
            if std::env::var("OPENCLAW_ALLOW_MAINNET").unwrap_or_default() != "1" {
                return Err(BybitApiError::Business {
                    ret_code: -1,
                    ret_msg: "Mainnet blocked: set OPENCLAW_ALLOW_MAINNET=1 to enable / 主網被阻止"
                        .into(),
                    response: serde_json::json!({"blocked": true}),
                });
            }
            tracing::warn!(
                "⚠ MAINNET mode enabled — real money at risk / 主網模式已啟用 — 真金白銀"
            );
        }
        let api_key = api_key
            .filter(|s| !s.is_empty())
            .or_else(|| {
                std::env::var("BYBIT_API_KEY")
                    .ok()
                    .filter(|s| !s.is_empty())
            })
            .or_else(|| read_secret_file("api_key"))
            .unwrap_or_default();

        let api_secret = api_secret
            .filter(|s| !s.is_empty())
            .or_else(|| {
                std::env::var("BYBIT_API_SECRET")
                    .ok()
                    .filter(|s| !s.is_empty())
            })
            .or_else(|| read_secret_file("api_secret"))
            .unwrap_or_default();

        if api_key.is_empty() || api_secret.is_empty() {
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
        })
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
    fn sign(&self, timestamp: &str, params: &str) -> BybitResult<String> {
        let sign_str = format!(
            "{}{}{}{}",
            timestamp, self.api_key, self.recv_window, params
        );

        let mut mac = Hmac::<Sha256>::new_from_slice(self.api_secret.as_bytes())
            .map_err(|e| BybitApiError::SigningError(e.to_string()))?;
        mac.update(sign_str.as_bytes());
        let result = mac.finalize();
        Ok(hex::encode(result.into_bytes()))
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

        self.wait_if_rate_limited().await;
        debug!(
            method = "GET",
            path = path,
            "Bybit API request / Bybit API 請求"
        );

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

        self.wait_if_rate_limited().await;
        debug!(
            method = "POST",
            path = path,
            "Bybit API request / Bybit API 請求"
        );

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
        Ok(parsed)
    }

    /// Signed GET that automatically checks retCode and returns Result.
    /// 簽名 GET，自動檢查 retCode 並返回 Result。
    pub async fn get_checked(
        &self,
        path: &str,
        params: &[(&str, &str)],
    ) -> BybitResult<BybitResponse> {
        self.get(path, params).await?.into_result()
    }

    /// Signed POST that automatically checks retCode and returns Result.
    /// 簽名 POST，自動檢查 retCode 並返回 Result。
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

    /// Proactively wait if global rate limit is nearly exhausted.
    /// 若全局限流接近耗盡，主動等待至重置時間（上限 2 秒）。
    ///
    /// Called before every GET/POST to avoid sending into a 429.
    /// Waits until `reset_ms` + 50ms buffer, capped at 2 000ms.
    /// No-op when reset_ms is unknown (0) or already in the past.
    /// 每次 GET/POST 前調用以避免觸發 429。
    /// 等待至 reset_ms + 50ms 緩衝，最多 2 秒。reset_ms 未知（0）或已過期時跳過。
    async fn wait_if_rate_limited(&self) {
        const THRESHOLD: i64 = 10;
        const MAX_WAIT_MS: u64 = 2_000;
        const BUFFER_MS: u64 = 50;

        if !self.is_near_rate_limit(THRESHOLD) {
            return;
        }

        let reset_ms = self.rate_limit.reset_ms.load(Ordering::Relaxed);
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
        warn!(
            remaining = remaining,
            wait_ms = wait_ms,
            "Rate limit near threshold — backing off / 接近限流閾值，主動退讓"
        );
        sleep(Duration::from_millis(wait_ms)).await;
    }

    /// Update per-group rate limit from the last request.
    /// 根據最近的請求更新分組限流。
    fn update_group_rate_limit(&self, path: &str, resp: &reqwest::Response) {
        if let Some(remaining) = resp
            .headers()
            .get("x-bapi-limit-status")
            .and_then(|v| v.to_str().ok())
            .and_then(|s| s.parse::<i64>().ok())
        {
            let group = RateLimitGroup::from_path(path);
            let idx = group as usize;
            self.rate_limit.group_remaining[idx].store(remaining, Ordering::Relaxed);
        }
    }
}

// ---------------------------------------------------------------------------
// Helpers / 輔助函數
// ---------------------------------------------------------------------------

/// Read a secret value from the standard secret file location.
/// 從標準秘密文件位置讀取秘密值。
///
/// Cross-platform: uses HOME env var, never hardcodes paths.
/// 跨平台：使用 HOME 環境變量，不硬編碼路徑。
fn read_secret_file(name: &str) -> Option<String> {
    let home = std::env::var("HOME")
        .or_else(|_| std::env::var("USERPROFILE"))
        .ok()?;
    let path = std::path::PathBuf::from(home)
        .join("BybitOpenClaw/secrets/secret_files/bybit/demo")
        .join(name);
    std::fs::read_to_string(&path)
        .ok()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty())
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    /// Test HMAC-SHA256 signing matches expected output.
    /// 測試 HMAC-SHA256 簽名匹配預期輸出。
    #[test]
    fn test_sign_known_vector() {
        // Create client with known key/secret for deterministic test
        // 使用已知 key/secret 創建客戶端進行確定性測試
        let client = BybitRestClient {
            client: Client::new(),
            api_key: "TESTKEY123".to_string(),
            api_secret: "TESTSECRET456".to_string(),
            base_url: "https://api-demo.bybit.com".to_string(),
            recv_window: "5000".to_string(),
            rate_limit: RateLimitState::default(),
        };

        let timestamp = "1700000000000";
        let params = "category=linear&symbol=BTCUSDT";

        // sign_str = "1700000000000TESTKEY1235000category=linear&symbol=BTCUSDT"
        let sign_str = format!(
            "{}{}{}{}",
            timestamp, client.api_key, client.recv_window, params
        );

        // Compute expected HMAC manually / 手動計算預期 HMAC
        let mut mac = Hmac::<Sha256>::new_from_slice(b"TESTSECRET456").unwrap();
        mac.update(sign_str.as_bytes());
        let expected = hex::encode(mac.finalize().into_bytes());

        let actual = client.sign(timestamp, params).unwrap();
        assert_eq!(actual, expected);
    }

    /// Test sign with empty params (for GET with no query).
    /// 測試空參數簽名（無查詢的 GET）。
    #[test]
    fn test_sign_empty_params() {
        let client = BybitRestClient {
            client: Client::new(),
            api_key: "KEY".to_string(),
            api_secret: "SECRET".to_string(),
            base_url: "https://api-demo.bybit.com".to_string(),
            recv_window: "5000".to_string(),
            rate_limit: RateLimitState::default(),
        };

        // Should not panic / 不應 panic
        let sig = client.sign("1700000000000", "").unwrap();
        assert!(!sig.is_empty());
        assert_eq!(sig.len(), 64); // SHA256 hex = 64 chars
    }

    /// Test BybitEnvironment URLs.
    /// 測試 BybitEnvironment URL。
    #[test]
    fn test_environment_urls() {
        assert_eq!(
            BybitEnvironment::Demo.rest_base_url(),
            "https://api-demo.bybit.com"
        );
        assert_eq!(
            BybitEnvironment::Testnet.rest_base_url(),
            "https://api-testnet.bybit.com"
        );
        assert_eq!(
            BybitEnvironment::Mainnet.rest_base_url(),
            "https://api.bybit.com"
        );
        assert_eq!(BybitEnvironment::default(), BybitEnvironment::Demo);
    }

    /// Test BybitResponse is_ok / into_result.
    /// 測試 BybitResponse is_ok / into_result。
    #[test]
    fn test_bybit_response_success() {
        let resp = BybitResponse {
            ret_code: 0,
            ret_msg: "OK".to_string(),
            result: serde_json::json!({"list": []}),
            time: 1700000000000,
        };
        assert!(resp.is_ok());
        assert!(resp.into_result().is_ok());
    }

    #[test]
    fn test_bybit_response_error() {
        let resp = BybitResponse {
            ret_code: 10001,
            ret_msg: "Invalid parameter".to_string(),
            result: serde_json::json!(null),
            time: 1700000000000,
        };
        assert!(!resp.is_ok());
        let err = resp.into_result().unwrap_err();
        match err {
            BybitApiError::Business { ret_code, .. } => assert_eq!(ret_code, 10001),
            _ => panic!("Expected Business error"),
        }
    }

    /// Test response deserialization from real Bybit JSON.
    /// 測試從真實 Bybit JSON 反序列化回應。
    #[test]
    fn test_deserialize_bybit_response() {
        let json = r#"{
            "retCode": 0,
            "retMsg": "OK",
            "result": {
                "list": [
                    {"symbol": "BTCUSDT", "lastPrice": "65000.50"}
                ]
            },
            "time": 1700000000000
        }"#;
        let resp: BybitResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.ret_code, 0);
        assert!(resp.result["list"].is_array());
    }

    /// Test deserialize error response.
    /// 測試反序列化錯誤回應。
    #[test]
    fn test_deserialize_error_response() {
        let json = r#"{
            "retCode": 10001,
            "retMsg": "params error",
            "result": {},
            "time": 1700000000000
        }"#;
        let resp: BybitResponse = serde_json::from_str(json).unwrap();
        assert_eq!(resp.ret_code, 10001);
        assert_eq!(resp.ret_msg, "params error");
    }

    /// Test has_credentials.
    /// 測試 has_credentials。
    #[test]
    fn test_has_credentials() {
        let client_with = BybitRestClient {
            client: Client::new(),
            api_key: "key".to_string(),
            api_secret: "secret".to_string(),
            base_url: "https://api-demo.bybit.com".to_string(),
            recv_window: "5000".to_string(),
            rate_limit: RateLimitState::default(),
        };
        assert!(client_with.has_credentials());

        let client_without = BybitRestClient {
            client: Client::new(),
            api_key: String::new(),
            api_secret: String::new(),
            base_url: "https://api-demo.bybit.com".to_string(),
            recv_window: "5000".to_string(),
            rate_limit: RateLimitState::default(),
        };
        assert!(!client_without.has_credentials());
    }

    /// Test rate limit initial state.
    /// 測試限流初始狀態。
    #[test]
    fn test_rate_limit_defaults() {
        let state = RateLimitState::default();
        assert_eq!(state.remaining.load(Ordering::Relaxed), 120);
        assert_eq!(state.reset_ms.load(Ordering::Relaxed), 0);
    }

    /// Test is_near_rate_limit.
    /// 測試 is_near_rate_limit。
    #[test]
    fn test_near_rate_limit() {
        let client = BybitRestClient {
            client: Client::new(),
            api_key: "key".to_string(),
            api_secret: "secret".to_string(),
            base_url: "https://api-demo.bybit.com".to_string(),
            recv_window: "5000".to_string(),
            rate_limit: RateLimitState::default(),
        };
        // Default remaining = 120, threshold 5 → not near
        assert!(!client.is_near_rate_limit(5));
        // Set remaining to 2
        client.rate_limit.remaining.store(2, Ordering::Relaxed);
        assert!(client.is_near_rate_limit(5));
    }

    /// Test query string construction with sorting.
    /// 測試查詢字串構建（含排序）。
    #[test]
    fn test_query_string_sorting() {
        let mut params: Vec<(&str, &str)> = vec![
            ("symbol", "BTCUSDT"),
            ("category", "linear"),
            ("limit", "50"),
        ];
        params.sort_by_key(|(k, _)| *k);
        let qs: String = params
            .iter()
            .map(|(k, v)| format!("{k}={v}"))
            .collect::<Vec<_>>()
            .join("&");
        assert_eq!(qs, "category=linear&limit=50&symbol=BTCUSDT");
    }

    /// Test RateLimitGroup classification.
    /// 測試限流分組分類。
    #[test]
    fn test_rate_limit_group_from_path() {
        assert_eq!(
            RateLimitGroup::from_path("/v5/order/create"),
            RateLimitGroup::Order
        );
        assert_eq!(
            RateLimitGroup::from_path("/v5/order/cancel"),
            RateLimitGroup::Order
        );
        assert_eq!(
            RateLimitGroup::from_path("/v5/execution/list"),
            RateLimitGroup::Order
        );
        assert_eq!(
            RateLimitGroup::from_path("/v5/position/list"),
            RateLimitGroup::Position
        );
        assert_eq!(
            RateLimitGroup::from_path("/v5/account/wallet-balance"),
            RateLimitGroup::Account
        );
        assert_eq!(
            RateLimitGroup::from_path("/v5/market/kline"),
            RateLimitGroup::Market
        );
        assert_eq!(
            RateLimitGroup::from_path("/v5/asset/transfer/inter-transfer"),
            RateLimitGroup::Asset
        );
        assert_eq!(
            RateLimitGroup::from_path("/v5/spot-margin-uta/status"),
            RateLimitGroup::Asset
        );
        assert_eq!(
            RateLimitGroup::from_path("/v5/unknown"),
            RateLimitGroup::Other
        );
    }

    /// Test BybitRetCode classification.
    /// 測試 retCode 分類。
    #[test]
    fn test_bybit_ret_code() {
        assert_eq!(BybitRetCode::from_code(0), Some(BybitRetCode::Ok));
        assert_eq!(
            BybitRetCode::from_code(110001),
            Some(BybitRetCode::OrderNotFound)
        );
        assert_eq!(
            BybitRetCode::from_code(110012),
            Some(BybitRetCode::InsufficientBalance)
        );
        assert_eq!(
            BybitRetCode::from_code(110043),
            Some(BybitRetCode::LeverageNotModified)
        );
        assert_eq!(BybitRetCode::from_code(99999), None);

        assert!(BybitRetCode::IpRateLimit.is_retryable());
        assert!(!BybitRetCode::InsufficientBalance.is_retryable());
        assert!(BybitRetCode::LeverageNotModified.is_noop());
        assert!(!BybitRetCode::InsufficientBalance.is_noop());
    }

    /// Test BybitApiError Display formatting.
    /// 測試 BybitApiError Display 格式化。
    #[test]
    fn test_error_display() {
        let err = BybitApiError::NoCredentials;
        assert_eq!(format!("{err}"), "API credentials not configured");

        let err = BybitApiError::Business {
            ret_code: 10001,
            ret_msg: "bad param".to_string(),
            response: serde_json::json!({}),
        };
        let s = format!("{err}");
        assert!(s.contains("10001"));
        assert!(s.contains("bad param"));
    }
}
