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

        // LIVE-GUARD-1 gate #2: on Mainnet skip env-var credential fallback.
        // Closes the "any process with env access bypasses secret slot" attack.
        // LIVE-GUARD-1 門 #2：Mainnet 禁用 env var 憑證回退（封閉「能設 env 即繞 slot」攻擊）。
        let api_key = api_key
            .filter(|s| !s.is_empty())
            .or_else(|| {
                if is_mainnet {
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
                if is_mainnet {
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
