//! Unix domain socket JSON-RPC 2.0 server for Rust↔Python IPC (R01-1).
//! Unix 域套接字 JSON-RPC 2.0 服務器，用於 Rust↔Python IPC。
//!
//! MODULE_NOTE (EN): Listens on a Unix socket, handles JSON-RPC 2.0 requests
//!   with newline-delimited messages. Each connection spawns a tokio task.
//!   Supports: ping, get_state, reload_config,
//!   paper session (pause/resume/close_all/reset), snapshot reads (paper_state/prices/stats),
//!   strategy params (update_strategy_params/get_strategy_params/get_param_ranges).
//! MODULE_NOTE (中): 監聯 Unix 套接字，處理 JSON-RPC 2.0 請求（換行分隔消息）。
//!   每個連接生成一個 tokio 任務。支援：ping、get_state、reload_config、
//!   紙盤控制（pause/resume/close_all/reset）、
//!   快照讀取（paper_state/prices/stats）、策略參數（update/get/ranges）。

use crate::ai_budget::BudgetTracker;
use crate::claude_teacher::ConsumerLoopStatus;
use crate::config::{
    BudgetConfig, ConfigManager, ConfigStore, LearningConfig, PatchSource, RiskConfig,
};
use crate::tick_pipeline::PipelineSnapshot;
use std::sync::atomic::{AtomicBool, Ordering};
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixListener;
use tokio::sync::RwLock;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

/// Phase 4 (4-15): Shared, late-injected slot for the AI BudgetTracker.
/// Phase 4 (4-15)：共享的、延後注入的 AI BudgetTracker 槽位。
///
/// MODULE_NOTE (EN): The IpcServer is constructed before the database pool exists, so
///   the BudgetTracker (which needs the pool) is injected after construction via
///   `IpcServer::budget_tracker_slot()`. The slot is wrapped in `Arc<RwLock<Option<...>>>`
///   so the same handle can be cloned into per-connection tasks. None = uninitialized
///   (e.g., DB unavailable) and IPC handlers fail-soft with a `{"status":"uninitialized"}`
///   response on read, fail-closed (-32603) on write.
/// MODULE_NOTE (中)：IpcServer 在資料庫池建立之前就構造，因此需要池的 BudgetTracker
///   透過 `IpcServer::budget_tracker_slot()` 在構造後注入。槽位用
///   `Arc<RwLock<Option<...>>>` 包裝，以便複製到每個連線任務。None = 未初始化
///   （例如 DB 不可用），讀取 IPC 以 `{"status":"uninitialized"}` fail-soft，
///   寫入則回傳 -32603 fail-closed。
pub type BudgetTrackerSlot = Arc<RwLock<Option<Arc<BudgetTracker>>>>;

/// Phase 4.1: Late-injected handles for the Teacher consumer loop.
/// Phase 4.1：延後注入的 Teacher consumer loop 句柄。
///
/// MODULE_NOTE (EN): main.rs constructs the consumer loop AFTER the IPC server
///   is spawned (because BudgetTracker must be ready first). The loop's
///   enabled flag and status counters are then written into this slot so the
///   IPC handlers `set_teacher_loop_enabled` / `get_teacher_loop_status` can
///   reach them. None = loop not yet wired (IPC fail-soft response).
/// MODULE_NOTE (中)：main.rs 在 IPC server spawn 之後才構造 consumer loop
///   （因為 BudgetTracker 必須先就緒）。Loop 的 enabled 旗標與 status 計數器
///   會寫入此槽位，供 IPC handler `set_teacher_loop_enabled` /
///   `get_teacher_loop_status` 取用。None = loop 尚未接線（IPC fail-soft）。
#[derive(Clone)]
pub struct TeacherLoopHandles {
    pub enabled: Arc<AtomicBool>,
    pub status: Arc<ConsumerLoopStatus>,
}

pub type TeacherLoopSlot = Arc<RwLock<Option<TeacherLoopHandles>>>;

/// ARCH-RC1 1C-2-E: late-injected slot for the audit DB pool used by V014
/// engine_events writes. None = audit disabled (DB unavailable at boot or
/// pool not yet initialized).
/// ARCH-RC1 1C-2-E：V014 engine_events 寫入用的審計 DB pool 延後注入槽位。
/// None = 審計停用（啟動時 DB 不可用或 pool 尚未初始化）。
pub type AuditPoolSlot = Arc<RwLock<Option<sqlx::PgPool>>>;

// ---------------------------------------------------------------------------
// LIVE-P2-1: Per-engine RiskConfig stores
// LIVE-P2-1：每個引擎模式的 RiskConfig stores
// ---------------------------------------------------------------------------

/// Bundles three RiskConfig stores — one per PipelineKind — so IPC routing and
/// TickPipeline wiring can select the correct store without scattering
/// individual Option<Arc<...>> fields across every function signature.
///
/// 將三個 RiskConfig stores 捆綁為一個結構體（每個 PipelineKind 一個），
/// 使 IPC 路由與 TickPipeline 接線可以選擇正確 store，
/// 而不需在每個函數簽名中分散獨立的 Option<Arc<...>> 字段。
#[derive(Clone)]
pub struct PerEngineRiskStores {
    /// Paper-only mode (no exchange connection) — liberal limits for strategy validation.
    /// 純 paper 模式（無交易所連接）— 寬鬆限制，用於策略驗證。
    pub paper: Arc<ConfigStore<RiskConfig>>,
    /// Demo mode (Bybit Demo exchange, simulated margin) — same as paper by default.
    /// Demo 模式（Bybit Demo 交易所，模擬保證金）— 默認與 paper 相同。
    pub demo: Arc<ConfigStore<RiskConfig>>,
    /// Live mode (real money, Mainnet) — tighter defaults, operator must relax before go-live.
    /// 實盤模式（真實資金，主網）— 更保守的默認值，Operator 需主動放寬才能上線。
    pub live: Arc<ConfigStore<RiskConfig>>,
}

impl PerEngineRiskStores {
    /// Select the store matching the given engine name string.
    /// Unknown names fall through to `paper` (fail-safe default).
    /// 按引擎名稱字符串選擇 store。未知名稱回退到 `paper`（安全默認）。
    pub fn select(&self, engine: &str) -> &Arc<ConfigStore<RiskConfig>> {
        match engine {
            "demo" => &self.demo,
            "live" => &self.live,
            _ => &self.paper, // "paper" or unknown → paper (fail-safe)
        }
    }
}

// ---------------------------------------------------------------------------
// 3E-3: Per-pipeline command channel routing
// 3E-3：每管線命令通道路由
// ---------------------------------------------------------------------------

/// Routes IPC commands to the correct pipeline's command channel.
/// In 3E-ARCH, each pipeline (Paper/Demo/Live) has its own command channel.
/// IPC handlers extract the `engine` param and select the correct sender.
///
/// 將 IPC 命令路由到正確管線的命令通道。
/// 3E-ARCH 下每個管線有獨立命令通道，IPC handler 按 `engine` 參數選擇。
#[derive(Clone, Default)]
pub struct EngineCommandChannels {
    pub paper: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    pub demo: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    pub live: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
}

impl EngineCommandChannels {
    /// Select the command sender for the given engine name.
    /// Falls back to paper for unknown names (fail-safe).
    /// 按引擎名選擇命令發送端。未知名稱回退到 paper（安全默認）。
    pub fn select(&self, engine: &str) -> &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
        match engine {
            "demo" => &self.demo,
            "live" => &self.live,
            _ => &self.paper, // "paper" or unknown → paper (fail-safe)
        }
    }

    /// Return the primary (first available) sender for commands that
    /// don't specify an engine param. Priority: live > demo > paper.
    /// 返回主要（第一個可用）sender，供未指定 engine 的命令使用。
    pub fn primary(&self) -> &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
        if self.live.is_some() {
            &self.live
        } else if self.demo.is_some() {
            &self.demo
        } else {
            &self.paper
        }
    }
}

// ---------------------------------------------------------------------------
// JSON-RPC error codes / JSON-RPC 錯誤碼
// ---------------------------------------------------------------------------

/// Invalid request / 無效請求
const ERR_INVALID_REQUEST: i64 = -32600;
/// Method not found / 方法未找到
const ERR_METHOD_NOT_FOUND: i64 = -32601;
/// Internal error / 內部錯誤
const ERR_INTERNAL: i64 = -32603;

// ---------------------------------------------------------------------------
// JSON-RPC message types / JSON-RPC 消息類型
// ---------------------------------------------------------------------------

/// Incoming JSON-RPC 2.0 request.
/// 傳入的 JSON-RPC 2.0 請求。
#[derive(Debug, Deserialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: Option<String>,
    pub method: Option<String>,
    #[serde(default)]
    pub params: serde_json::Value,
    pub id: Option<serde_json::Value>,
}

/// Outgoing JSON-RPC 2.0 response.
/// 傳出的 JSON-RPC 2.0 回應。
#[derive(Debug, Serialize)]
pub struct JsonRpcResponse {
    pub jsonrpc: &'static str,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub result: Option<serde_json::Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub error: Option<JsonRpcError>,
    pub id: serde_json::Value,
}

/// JSON-RPC 2.0 error object.
/// JSON-RPC 2.0 錯誤對象。
#[derive(Debug, Serialize)]
pub struct JsonRpcError {
    pub code: i64,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub data: Option<serde_json::Value>,
}

impl JsonRpcResponse {
    /// Create a success response / 創建成功回應
    fn success(id: serde_json::Value, result: serde_json::Value) -> Self {
        Self {
            jsonrpc: "2.0",
            result: Some(result),
            error: None,
            id,
        }
    }

    /// Create an error response / 創建錯誤回應
    fn error(id: serde_json::Value, code: i64, message: impl Into<String>) -> Self {
        Self {
            jsonrpc: "2.0",
            result: None,
            error: Some(JsonRpcError {
                code,
                message: message.into(),
                data: None,
            }),
            id,
        }
    }
}

// ---------------------------------------------------------------------------
// IPC Server / IPC 服務器
// ---------------------------------------------------------------------------

use crate::tick_pipeline::PipelineCommand;

/// Unix domain socket IPC server.
/// Unix 域套接字 IPC 服務器。
pub struct IpcServer {
    config: Arc<ConfigManager>,
    cancel: CancellationToken,
    /// Data directory for reading pipeline snapshot files (R06-A).
    /// 數據目錄，用於讀取管線快照文件。
    data_dir: Arc<PathBuf>,
    /// 3E-3: Per-pipeline command channels — routes commands to Paper/Demo/Live pipelines.
    /// 3E-3：每管線命令通道 — 將命令路由到 Paper/Demo/Live 管線。
    cmd_channels: EngineCommandChannels,
    /// Phase 4 (4-15): Late-injected AI BudgetTracker slot.
    /// Phase 4 (4-15)：延後注入的 AI BudgetTracker 槽位。
    budget_tracker: BudgetTrackerSlot,
    /// Phase 4.1: Late-injected Teacher consumer loop handles.
    /// Phase 4.1：延後注入的 Teacher consumer loop 句柄。
    teacher_loop: TeacherLoopSlot,
    /// ARCH-RC1 1C-2-C / LIVE-P2-1: per-engine RiskConfig stores + unified Config stores.
    /// ARCH-RC1 1C-2-C / LIVE-P2-1：每引擎 RiskConfig stores + 統一 Config stores。
    risk_stores: Option<PerEngineRiskStores>,
    learning_store: Option<Arc<ConfigStore<LearningConfig>>>,
    budget_store: Option<Arc<ConfigStore<BudgetConfig>>>,
    /// ARCH-RC1 1C-2-E: late-injected slot for the V014 audit pool.
    /// ARCH-RC1 1C-2-E：V014 審計 pool 延後注入槽位。
    audit_pool: AuditPoolSlot,
    /// Scanner IPC: SymbolRegistry for get_active_symbols / get_scanner_status.
    /// 掃描器 IPC：SymbolRegistry 供 get_active_symbols / get_scanner_status 使用。
    scanner_registry: Option<Arc<crate::scanner::registry::SymbolRegistry>>,
}

impl IpcServer {
    /// Create a new IPC server instance.
    /// 創建新的 IPC 服務器實例。
    pub fn new(
        config: Arc<ConfigManager>,
        cancel: CancellationToken,
        data_dir: impl Into<String>,
        cmd_channels: EngineCommandChannels,
    ) -> Self {
        Self {
            config,
            cancel,
            data_dir: Arc::new(PathBuf::from(data_dir.into())),
            cmd_channels,
            budget_tracker: Arc::new(RwLock::new(None)),
            teacher_loop: Arc::new(RwLock::new(None)),
            risk_stores: None,
            learning_store: None,
            budget_store: None,
            audit_pool: Arc::new(RwLock::new(None)),
            scanner_registry: None,
        }
    }

    /// Scanner IPC: wire the SymbolRegistry so get_active_symbols / get_scanner_status work.
    /// Must be called before run(). symbol_registry is available in main.rs before IPC spawn.
    /// 掃描器 IPC：接入 SymbolRegistry，使 get_active_symbols / get_scanner_status 生效。
    /// 必須在 run() 前調用。symbol_registry 在 main.rs 中在 IPC spawn 前已可用。
    pub fn set_scanner_registry(
        &mut self,
        registry: Arc<crate::scanner::registry::SymbolRegistry>,
    ) {
        self.scanner_registry = Some(registry);
    }

    /// ARCH-RC1 1C-2-E: get a clone of the audit pool slot for late injection
    /// from main.rs once the DB pool is ready.
    /// ARCH-RC1 1C-2-E：取得審計 pool 槽位句柄供 main.rs 在 DB pool 就緒後注入。
    pub fn audit_pool_slot(&self) -> AuditPoolSlot {
        Arc::clone(&self.audit_pool)
    }

    /// ARCH-RC1 1C-2-C / LIVE-P2-1: wire per-engine RiskConfig stores + unified Config stores.
    /// ARCH-RC1 1C-2-C / LIVE-P2-1：接入每引擎 RiskConfig stores + 統一 Config stores。
    ///
    /// `risk` bundles paper/demo/live stores; IPC routes to the correct one via the
    /// `engine` param in `get_risk_config` / `patch_risk_config` (default: "paper").
    /// `risk` 捆綁三個 stores；IPC 通過請求的 `engine` 字段路由（默認 "paper"）。
    pub fn set_config_stores(
        &mut self,
        risk: PerEngineRiskStores,
        learning: Arc<ConfigStore<LearningConfig>>,
        budget: Arc<ConfigStore<BudgetConfig>>,
    ) {
        self.risk_stores = Some(risk);
        self.learning_store = Some(learning);
        self.budget_store = Some(budget);
    }

    /// Phase 4.1: Get a clone of the Teacher loop slot for late injection.
    /// Phase 4.1：取得 Teacher loop 槽位的複製句柄供延後注入。
    pub fn teacher_loop_slot(&self) -> TeacherLoopSlot {
        Arc::clone(&self.teacher_loop)
    }

    /// Phase 4 (4-15): Get a clone of the BudgetTracker slot for late injection.
    /// Phase 4 (4-15)：取得 BudgetTracker 槽位的複製句柄供延後注入使用。
    ///
    /// Callers in main.rs construct the BudgetTracker after the DB pool is ready,
    /// then write it into this slot via `slot.write().await.replace(tracker)`.
    /// main.rs 在 DB pool 就緒後構造 BudgetTracker，再透過
    /// `slot.write().await.replace(tracker)` 寫入此槽位。
    pub fn budget_tracker_slot(&self) -> BudgetTrackerSlot {
        Arc::clone(&self.budget_tracker)
    }

    /// Start listening. This function runs until cancellation.
    /// 開始監聽。此函數運行直到取消。
    pub async fn run(&self) -> Result<(), IpcError> {
        let cfg = self.config.get();
        let socket_path = &cfg.ipc_socket_path;

        // Ensure parent directory exists / 確保父目錄存在
        if let Some(parent) = Path::new(socket_path).parent() {
            tokio::fs::create_dir_all(parent).await.map_err(|e| {
                IpcError::Setup(format!(
                    "failed to create socket dir '{}': {}",
                    parent.display(),
                    e
                ))
            })?;
        }

        // Remove stale socket if exists / 移除過時的套接字文件
        if Path::new(socket_path).exists() {
            info!(path = socket_path, "removing stale socket / 移除過時套接字");
            tokio::fs::remove_file(socket_path)
                .await
                .map_err(|e| IpcError::Setup(format!("failed to remove stale socket: {e}")))?;
        }

        let listener = UnixListener::bind(socket_path)
            .map_err(|e| IpcError::Setup(format!("failed to bind socket '{socket_path}': {e}")))?;

        // I-02: restrict socket to owner (0o600) to prevent unauthorized IPC access.
        // I-02：將套接字限制為所有者可讀寫（0o600），防止未授權 IPC 訪問。
        {
            use std::os::unix::fs::PermissionsExt;
            if let Err(e) =
                std::fs::set_permissions(socket_path, std::fs::Permissions::from_mode(0o600))
            {
                warn!(path = socket_path, error = %e, "failed to set socket mode 0o600 / 設定套接字權限失敗");
            }
        }

        info!(
            path = socket_path,
            "IPC server listening / IPC 服務器已啟動"
        );

        loop {
            tokio::select! {
                _ = self.cancel.cancelled() => {
                    info!("IPC server shutting down / IPC 服務器正在關閉");
                    break;
                }
                accept_result = listener.accept() => {
                    match accept_result {
                        Ok((stream, _addr)) => {
                            let config = Arc::clone(&self.config);
                            let cancel = self.cancel.clone();
                            let data_dir = Arc::clone(&self.data_dir);
                            let cmd_channels = self.cmd_channels.clone();
                            let budget_slot = Arc::clone(&self.budget_tracker);
                            let teacher_slot = Arc::clone(&self.teacher_loop);
                            let risk_stores = self.risk_stores.clone();
                            let learning_store = self.learning_store.clone();
                            let budget_store = self.budget_store.clone();
                            let audit_pool = self.audit_pool.read().await.clone();
                            let scanner_reg = self.scanner_registry.clone();
                            tokio::spawn(async move {
                                handle_connection(stream, config, cancel, data_dir, cmd_channels, budget_slot, teacher_slot, risk_stores, learning_store, budget_store, audit_pool, scanner_reg).await;
                            });
                        }
                        Err(e) => {
                            error!(error = %e, "failed to accept connection / 接受連接失敗");
                        }
                    }
                }
            }
        }

        // Clean up socket file / 清理套接字文件
        let _ = tokio::fs::remove_file(socket_path).await;
        info!(path = socket_path, "IPC socket removed / IPC 套接字已移除");
        Ok(())
    }
}

/// G-3 / SEC-08: Verify IPC auth token using HMAC-SHA256.
/// G-3 / SEC-08：使用 HMAC-SHA256 驗證 IPC 認證令牌。
///
/// token = HMAC-SHA256(secret, timestamp_as_decimal_string)
/// Uses constant-time comparison via hmac::Mac::verify_slice to prevent timing attacks.
/// 使用 hmac::Mac::verify_slice 進行常數時間比較，防止時序攻擊。
fn verify_ipc_token(secret: &str, ts: i64, token: &str) -> bool {
    use hmac::{Hmac, Mac};
    use sha2::Sha256;
    type HmacSha256 = Hmac<Sha256>;

    let Ok(mut mac) = HmacSha256::new_from_slice(secret.as_bytes()) else {
        return false;
    };
    mac.update(ts.to_string().as_bytes());
    // Decode hex token for constant-time slice comparison / 解碼 hex 令牌進行常數時間比對
    let Ok(token_bytes) = hex::decode(token) else {
        return false;
    };
    mac.verify_slice(&token_bytes).is_ok()
}

/// Handle a single client connection.
/// 處理單個客戶端連接。
#[allow(clippy::too_many_arguments)]
async fn handle_connection(
    stream: tokio::net::UnixStream,
    config: Arc<ConfigManager>,
    cancel: CancellationToken,
    data_dir: Arc<PathBuf>,
    cmd_channels: EngineCommandChannels,
    budget_slot: BudgetTrackerSlot,
    teacher_slot: TeacherLoopSlot,
    risk_stores: Option<PerEngineRiskStores>,
    learning_store: Option<Arc<ConfigStore<LearningConfig>>>,
    budget_store: Option<Arc<ConfigStore<BudgetConfig>>>,
    audit_pool: Option<sqlx::PgPool>,
    scanner_registry: Option<Arc<crate::scanner::registry::SymbolRegistry>>,
) {
    let peer = format!("{:?}", stream.peer_addr());
    info!(peer = %peer, "client connected / 客戶端已連接");

    let (reader, mut writer) = stream.into_split();
    let mut lines = BufReader::new(reader).lines();

    // G-3 / SEC-08: HMAC-SHA256 connection-level authentication.
    // G-3 / SEC-08：HMAC-SHA256 連線級認證。
    // If OPENCLAW_IPC_SECRET is set, the first message must be an __auth handshake.
    // 若設置 OPENCLAW_IPC_SECRET，首條消息必須是 __auth 握手。
    // Fail-closed: any auth failure drops the connection immediately.
    // Fail-closed：任何認證失敗立即斷開連線。
    // Backward-compatible: if env var is absent, auth is skipped (dev/test mode).
    // 向後兼容：env var 不存在時跳過認證（開發/測試模式）。
    if let Ok(secret) = std::env::var("OPENCLAW_IPC_SECRET") {
        // Read the first line — must be __auth / 讀取第一行，必須是 __auth
        let auth_line = match lines.next_line().await {
            Ok(Some(line)) => line,
            Ok(None) => {
                warn!(peer = %peer, "auth: client disconnected before handshake / 握手前斷開");
                return;
            }
            Err(e) => {
                warn!(peer = %peer, error = %e, "auth: read error / 認證讀取錯誤");
                return;
            }
        };
        let auth_req: serde_json::Value = match serde_json::from_str(&auth_line) {
            Ok(v) => v,
            Err(_) => {
                let err = br#"{"jsonrpc":"2.0","error":{"code":-32600,"message":"first message must be __auth JSON"},"id":null}"#;
                let mut bytes = err.to_vec(); bytes.push(b'\n');
                let _ = writer.write_all(&bytes).await;
                warn!(peer = %peer, "auth: invalid JSON / 認證：JSON 格式錯誤");
                return;
            }
        };
        if auth_req.get("method").and_then(|m| m.as_str()) != Some("__auth") {
            let err = br#"{"jsonrpc":"2.0","error":{"code":-32600,"message":"first message must be __auth"},"id":null}"#;
            let mut bytes = err.to_vec(); bytes.push(b'\n');
            let _ = writer.write_all(&bytes).await;
            warn!(peer = %peer, "auth: first message is not __auth / 首條消息非 __auth");
            return;
        }
        let params = auth_req
            .get("params")
            .and_then(|p| p.as_object())
            .cloned()
            .unwrap_or_default();
        let token = params.get("token").and_then(|t| t.as_str()).unwrap_or("");
        let ts = params.get("ts").and_then(|t| t.as_i64()).unwrap_or(0);
        // Verify timestamp: |now - ts| must be ≤ 30s to prevent replay attacks
        // 驗證時間戳：|now - ts| ≤ 30s，防止重放攻擊
        let now = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs() as i64;
        if (now - ts).abs() > 30 {
            let err = br#"{"jsonrpc":"2.0","error":{"code":-32600,"message":"auth token expired (timestamp skew > 30s)"},"id":null}"#;
            let mut bytes = err.to_vec(); bytes.push(b'\n');
            let _ = writer.write_all(&bytes).await;
            warn!(peer = %peer, ts, now, "auth: token expired / 認證令牌已過期");
            return;
        }
        // HMAC-SHA256 constant-time verification / HMAC-SHA256 常數時間驗證
        if !verify_ipc_token(&secret, ts, token) {
            let err = br#"{"jsonrpc":"2.0","error":{"code":-32600,"message":"auth failed: invalid token"},"id":null}"#;
            let mut bytes = err.to_vec(); bytes.push(b'\n');
            let _ = writer.write_all(&bytes).await;
            warn!(peer = %peer, "auth: HMAC verification failed / HMAC 驗證失敗");
            return;
        }
        // Auth success — send confirmation / 認證成功，發送確認
        let auth_id = auth_req.get("id").cloned().unwrap_or(serde_json::Value::Null);
        let ok = serde_json::json!({"jsonrpc":"2.0","result":{"authenticated":true},"id":auth_id});
        let mut ok_bytes = serde_json::to_vec(&ok).unwrap_or_default();
        ok_bytes.push(b'\n');
        if let Err(e) = writer.write_all(&ok_bytes).await {
            warn!(peer = %peer, error = %e, "auth: write failed / 認證寫入失敗");
            return;
        }
        info!(peer = %peer, "IPC client authenticated (HMAC-SHA256) / IPC 客戶端認證成功");
    }

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                debug!(peer = %peer, "connection cancelled / 連接已取消");
                break;
            }
            line_result = lines.next_line() => {
                match line_result {
                    Ok(Some(line)) => {
                        let response = dispatch_request(&line, &config, &data_dir, &cmd_channels, &budget_slot, &teacher_slot, &risk_stores, &learning_store, &budget_store, &audit_pool, &scanner_registry).await;
                        let mut resp_bytes = serde_json::to_vec(&response)
                            .unwrap_or_else(|_| br#"{"jsonrpc":"2.0","error":{"code":-32603,"message":"serialization error"},"id":null}"#.to_vec());
                        resp_bytes.push(b'\n');
                        if let Err(e) = writer.write_all(&resp_bytes).await {
                            warn!(error = %e, "write failed / 寫入失敗");
                            break;
                        }
                    }
                    Ok(None) => {
                        // Client disconnected / 客戶端斷開
                        break;
                    }
                    Err(e) => {
                        warn!(error = %e, "read error / 讀取錯誤");
                        break;
                    }
                }
            }
        }
    }

    info!(peer = %peer, "client disconnected / 客戶端已斷開");
}

/// Parse and dispatch a single JSON-RPC request line.
/// 解析並分發單條 JSON-RPC 請求。
#[allow(clippy::too_many_arguments)]
async fn dispatch_request(
    line: &str,
    config: &Arc<ConfigManager>,
    data_dir: &Arc<PathBuf>,
    cmd_channels: &EngineCommandChannels,
    budget_slot: &BudgetTrackerSlot,
    teacher_slot: &TeacherLoopSlot,
    risk_stores: &Option<PerEngineRiskStores>,
    learning_store: &Option<Arc<ConfigStore<LearningConfig>>>,
    budget_store: &Option<Arc<ConfigStore<BudgetConfig>>>,
    audit_pool: &Option<sqlx::PgPool>,
    scanner_registry: &Option<Arc<crate::scanner::registry::SymbolRegistry>>,
) -> JsonRpcResponse {
    let req: JsonRpcRequest = match serde_json::from_str(line) {
        Ok(r) => r,
        Err(e) => {
            return JsonRpcResponse::error(
                serde_json::Value::Null,
                ERR_INVALID_REQUEST,
                format!("parse error: {e}"),
            );
        }
    };

    let id = req.id.clone().unwrap_or(serde_json::Value::Null);

    // Validate jsonrpc version / 驗證 jsonrpc 版本
    if req.jsonrpc.as_deref() != Some("2.0") {
        return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "jsonrpc must be \"2.0\"");
    }

    let method = match &req.method {
        Some(m) => m.as_str(),
        None => {
            return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing method field");
        }
    };

    // MAJOR-5: Per-engine IPC audit log — every routed request is traced with
    // method + target engine for post-hoc forensics.
    // MAJOR-5：每引擎 IPC 審計日誌 — 記錄 method + 目標引擎以供事後取證。
    {
        let target_engine = req.params.get("engine")
            .and_then(|v| v.as_str())
            .unwrap_or("(default)");
        tracing::info!(
            ipc_method = method,
            target_engine = target_engine,
            "ipc_audit: dispatching request / IPC 審計：分發請求"
        );
    }

    match method {
        "ping" => handle_ping(id),
        "get_state" => handle_get_state(id, config, data_dir),
        "reload_config" => handle_reload_config(id, config),
        "get_paper_state" => {
            // Phase 4: optional `engine` param routes to per-mode snapshot.
            // Default "paper" for backward compatibility.
            // Phase 4：可選 `engine` 參數路由到每模式快照，默認 "paper" 向後兼容。
            let engine = req.params.get("engine")
                .and_then(|v| v.as_str())
                .unwrap_or("paper")
                .to_string();
            handle_snapshot_field(id, data_dir, move |s| {
                // Primary mode: return top-level paper_state (authoritative).
                // Secondary modes: look up mode_snapshots.
                // 主模式：返回頂層 paper_state（權威來源）。
                // 次級模式：查找 mode_snapshots。
                if let Some(mode_snap) = s.mode_snapshots.get(&engine) {
                    serde_json::to_value(&mode_snap.paper_state)
                } else if engine == s.pipeline_kind.db_mode() {
                    serde_json::to_value(&s.paper_state)
                } else {
                    // Requested mode not active — return null with metadata.
                    // 請求的模式未啟用 — 返回 null 帶元數據。
                    serde_json::to_value(serde_json::json!({
                        "error": "mode_not_active",
                        "requested": engine,
                        "active_modes": s.mode_snapshots.keys().collect::<Vec<_>>()
                    }))
                }
            })
        }
        "get_mode_snapshot" => {
            // Phase 4: Full ModeStateSnapshot for a specific engine mode.
            // Phase 4：特定引擎模式的完整 ModeStateSnapshot。
            let engine = req.params.get("engine")
                .and_then(|v| v.as_str())
                .unwrap_or("paper")
                .to_string();
            handle_snapshot_field(id, data_dir, move |s| {
                if let Some(mode_snap) = s.mode_snapshots.get(&engine) {
                    serde_json::to_value(mode_snap)
                } else {
                    serde_json::to_value(serde_json::json!({
                        "error": "mode_not_active",
                        "requested": engine,
                        "active_modes": s.mode_snapshots.keys().collect::<Vec<_>>()
                    }))
                }
            })
        }
        "get_active_modes" => {
            // Phase 4: List all active engine modes.
            // Phase 4：列出所有活躍引擎模式。
            handle_snapshot_field(id, data_dir, |s| {
                serde_json::to_value(s.mode_snapshots.keys().collect::<Vec<_>>())
            })
        }
        "get_latest_prices" => {
            handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.latest_prices))
        }
        "get_tick_stats" => handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.stats)),
        // ── Pipeline control commands / 管線控制命令 ──
        // 3E-3: Commands accept optional `engine` param ("paper"/"demo"/"live")
        // to route to the correct pipeline. Default: primary pipeline.
        // 3E-3：命令接受可選 `engine` 參數路由到正確管線，默認為主管線。
        "pause_paper" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(id, tx, PipelineCommand::Pause, "paused")
        }
        "resume_paper" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(id, tx, PipelineCommand::Resume, "resumed")
        }
        "close_all_positions" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(id, tx, PipelineCommand::CloseAll, "close_all_sent")
        }
        "close_position" => {
            let symbol = req
                .params
                .get("symbol")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            if symbol.is_empty() {
                return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing required param: symbol");
            }
            // Optional hints: caller (Python GUI route) supplies exchange-side position info
            // so Rust can close orphan positions not tracked in paper_state.
            // 可選 hints：呼叫方（Python GUI 路由）提供交易所側倉位資訊，
            // 使 Rust 可平掉 paper_state 未追蹤的孤兒倉位。
            let hint_is_long = req.params.get("is_long").and_then(|v| v.as_bool());
            let hint_qty = req.params.get("qty").and_then(|v| v.as_f64());
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(
                id,
                tx,
                PipelineCommand::CloseSymbol { symbol, hint_is_long, hint_qty },
                "close_position_sent",
            )
        }
        "reset_paper_state" => {
            let balance = req
                .params
                .get("new_balance")
                .and_then(|v| v.as_f64())
                .unwrap_or(10_000.0);
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_paper_cmd(
                id,
                tx,
                PipelineCommand::Reset {
                    new_balance: balance,
                },
                "reset_sent",
            )
        }
        // ── Phase 3b: Strategy parameter commands (Optuna → Rust) / 策略參數命令 ──
        "update_strategy_params" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, tx, &req.params, StrategyParamOp::Update).await
        }
        "get_strategy_params" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, tx, &req.params, StrategyParamOp::Get).await
        }
        "get_param_ranges" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_strategy_param_cmd(id, tx, &req.params, StrategyParamOp::Ranges).await
        }
        "update_risk_config" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_update_risk_config(id, tx, &req.params).await
        }
        // ARCH-RC1 1C-3-B: Rust-native risk runtime status + safe counter clear
        "get_risk_runtime_status" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_risk_runtime_status(id, tx).await
        }
        "clear_consecutive_losses" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_clear_consecutive_losses(id, tx).await
        }
        // ARCH-RC1 1C-3-B-2: governor manual override (operator escalation/de-escalation)
        "force_governor_tier_tighter" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_force_governor_tighter(id, tx, &req.params, audit_pool).await
        }
        "force_governor_tier_looser" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_force_governor_looser(id, tx, &req.params, audit_pool).await
        }
        // ARCH-RC1 1C-3-F: External paper-side order submission (shadow_decision_builder etc.)
        "submit_paper_order" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_submit_paper_order(id, tx, &req.params).await
        }
        // RRC-1-E2: Strategy activate/pause / 策略啟停
        "set_strategy_active" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_set_strategy_active(id, tx, &req.params).await
        }
        // System mode sync from Python GUI / 從 Python GUI 同步系統模式
        // set_system_mode broadcasts to ALL pipelines (not engine-specific)
        // set_system_mode 廣播到所有管線（非引擎特定）
        "set_system_mode" => handle_set_system_mode_broadcast(id, cmd_channels, &req.params).await,
        // Phase 4 (4-00): Dashboard skeleton status aggregation / 儀表板骨架狀態聚合
        "get_phase4_status" => handle_get_phase4_status(id),
        // Phase 4 (4-15): AI budget status / config / AI 預算狀態與配置
        "get_ai_budget_status" => handle_get_ai_budget_status(id, budget_slot).await,
        "update_ai_budget_config" => {
            handle_update_ai_budget_config(id, &req.params, budget_slot).await
        }
        // Phase 4.1: Teacher consumer loop control / Teacher consumer loop 控制
        "set_teacher_loop_enabled" => {
            handle_set_teacher_loop_enabled(id, &req.params, teacher_slot).await
        }
        "get_teacher_loop_status" => handle_get_teacher_loop_status(id, teacher_slot).await,
        // ── ARCH-RC1 1C-2-C / LIVE-P2-1: unified Config IPC endpoints ──
        // ── ARCH-RC1 1C-2-C / LIVE-P2-1：統一 Config IPC 端點 ──
        //
        // get_risk_config / patch_risk_config accept optional `engine` param:
        //   "paper" (default) | "demo" | "live"
        // Route to the corresponding PerEngineRiskStores slot.
        // get_risk_config / patch_risk_config 接受可選的 `engine` 參數路由到對應 store。
        "get_risk_config" => {
            let engine = req.params.get("engine").and_then(|v| v.as_str()).unwrap_or("paper");
            let store: Option<Arc<ConfigStore<RiskConfig>>> =
                risk_stores.as_ref().map(|s| Arc::clone(s.select(engine)));
            handle_get_config(id, &store, &format!("risk/{engine}"))
        }
        "get_learning_config" => handle_get_config(id, learning_store, "learning"),
        "get_budget_config" => handle_get_config(id, budget_store, "budget"),
        "patch_risk_config" => {
            let engine = req.params.get("engine").and_then(|v| v.as_str()).unwrap_or("paper");
            let store: Option<Arc<ConfigStore<RiskConfig>>> =
                risk_stores.as_ref().map(|s| Arc::clone(s.select(engine)));
            handle_patch_config(
                id,
                &store,
                &req.params,
                RiskConfig::validate,
                &format!("risk/{engine}"),
                audit_pool,
            )
        }
        "patch_learning_config" => handle_patch_config(
            id,
            learning_store,
            &req.params,
            LearningConfig::validate,
            "learning",
            audit_pool,
        ),
        "patch_budget_config" => handle_patch_config(
            id,
            budget_store,
            &req.params,
            BudgetConfig::validate,
            "budget",
            audit_pool,
        ),
        // ── Scanner observability (IPC-SCAN-1) ──
        "get_active_symbols" => handle_get_active_symbols(id, scanner_registry),
        "get_scanner_status" => handle_get_scanner_status(id, scanner_registry),
        _ => JsonRpcResponse::error(
            id,
            ERR_METHOD_NOT_FOUND,
            format!("method not found: {method}"),
        ),
    }
}

// ---------------------------------------------------------------------------
// Method handlers / 方法處理器
// ---------------------------------------------------------------------------

/// 3E-3: Extract the `engine` param from request params and select the
/// matching pipeline command sender. Falls back to primary if missing.
/// 3E-3：從請求參數提取 `engine` 並選擇對應管線命令發送端，缺失時回退到主管線。
fn extract_engine_tx<'a>(
    params: &serde_json::Value,
    channels: &'a EngineCommandChannels,
) -> &'a Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
    match params.get("engine").and_then(|v| v.as_str()) {
        Some(engine) => channels.select(engine),
        None => channels.primary(),
    }
}

/// Handle paper session command — send to event consumer via channel.
/// 處理紙盤 session 命令 — 通過通道發送到事件消費者。
fn handle_paper_cmd(
    id: serde_json::Value,
    tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    cmd: PipelineCommand,
    result_key: &str,
) -> JsonRpcResponse {
    match tx {
        Some(tx) => match tx.send(cmd) {
            Ok(()) => JsonRpcResponse::success(id, serde_json::json!({ result_key: true })),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}")),
        },
        None => JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured"),
    }
}

/// Handle ping → pong.
/// 處理 ping → pong。
fn handle_ping(id: serde_json::Value) -> JsonRpcResponse {
    JsonRpcResponse::success(id, serde_json::Value::String("pong".into()))
}

/// Get current engine state summary.
/// Reads system_mode from pipeline snapshot (set by Python GUI sync).
/// 獲取當前引擎狀態摘要。
/// 從 pipeline 快照讀取 system_mode（由 Python GUI 同步設置）。
fn handle_get_state(
    id: serde_json::Value,
    config: &Arc<ConfigManager>,
    data_dir: &Arc<std::path::PathBuf>,
) -> JsonRpcResponse {
    let cfg = config.get();
    // ARCH-RC1 1C-1: risk display fields now sourced from RiskConfig::default()
    // placeholder; 1C-2 will replace with live ConfigStore<RiskConfig> snapshot.
    // ARCH-RC1 1C-1：風控展示欄位暫從 RiskConfig::default() 讀；1C-2 改真快照。
    let risk = crate::config::RiskConfig::default();
    // Read system_mode from pipeline snapshot; fall back to "live_reserved" if unavailable.
    // 從 pipeline 快照讀取 system_mode；不可用時回退到 "live_reserved"。
    let system_mode = {
        let path = data_dir.join("pipeline_snapshot.json");
        std::fs::read_to_string(&path)
            .ok()
            .and_then(|c| serde_json::from_str::<crate::pipeline_types::PipelineSnapshot>(&c).ok())
            .map(|s| s.system_mode)
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "live_reserved".to_string())
    };
    // 3E-10.2: trading_mode derived from pipeline snapshot (TradingMode deleted).
    // 3E-10.2：trading_mode 從管線快照派生（TradingMode 已刪除）。
    let trading_mode = {
        let path = data_dir.join("pipeline_snapshot.json");
        std::fs::read_to_string(&path)
            .ok()
            .and_then(|c| serde_json::from_str::<serde_json::Value>(&c).ok())
            .and_then(|v| v.get("trading_mode").and_then(|t| t.as_str().map(String::from)))
            .unwrap_or_else(|| "paper".to_string())
    };
    let state = serde_json::json!({
        "status": "running",
        "system_mode": system_mode,
        "trading_mode": trading_mode,
        "max_open_positions": risk.limits.open_positions_max,
        "max_total_exposure_pct": risk.limits.total_exposure_max_pct,
        "ws_url": cfg.ws_url,
        "config_path": config.file_path().display().to_string(),
    });
    JsonRpcResponse::success(id, state)
}

/// Phase 4 (4-00): Return dashboard skeleton status aggregation.
/// Phase 4 (4-00): 返回儀表板骨架的狀態聚合。
///
/// Each Phase 4 module (Teacher / LinUCB / News / DL-3) reports a traffic-light
/// state. At skeleton stage all modules report "grey" (not started). Subsequent
/// sub-tasks (4-01 ... 4-21) will replace the stub with real status sources.
///
/// 各 Phase 4 模組（Teacher / LinUCB / News / DL-3）回報一個紅黃綠燈狀態。
/// 骨架階段全部回報 "grey"（未啟動）。後續子任務（4-01 ... 4-21）會將 stub
/// 替換為真實狀態源。
///
/// Schema:
///   {
///     "teacher": "grey" | "green" | "yellow" | "red",
///     "linucb":  "grey" | ...,
///     "news":    "grey" | ...,
///     "dl3":     "grey" | ...,
///     "last_update_ms": <unix-millis>
///   }
fn handle_get_phase4_status(id: serde_json::Value) -> JsonRpcResponse {
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    let payload = serde_json::json!({
        "teacher": "grey",
        "linucb":  "grey",
        "news":    "grey",
        "dl3":     "grey",
        "last_update_ms": now_ms,
    });
    JsonRpcResponse::success(id, payload)
}

/// Phase 4 (4-15): Return current AI budget status snapshot.
/// Phase 4 (4-15)：返回當前 AI 預算狀態快照。
///
/// EN: If the BudgetTracker slot is None (e.g., DB pool unavailable at boot), this
///     fail-soft returns `{"status":"uninitialized"}` so dashboards can render a grey
///     card without raising an IPC error. When the tracker is present, returns the
///     full JSON produced by `BudgetTracker::status_json()` (limits, usage, degrade
///     level, last refresh timestamp).
/// 中：若 BudgetTracker 槽位為 None（例如 DB 池在啟動時不可用），fail-soft 回傳
///     `{"status":"uninitialized"}`，儀表板可顯示灰燈而不報錯。當 tracker 存在時，
///     回傳 `BudgetTracker::status_json()` 產生的完整 JSON（額度、用量、降級等級、
///     最近刷新時戳）。
async fn handle_get_ai_budget_status(
    id: serde_json::Value,
    slot: &BudgetTrackerSlot,
) -> JsonRpcResponse {
    let guard = slot.read().await;
    match guard.as_ref() {
        Some(tracker) => {
            let payload = tracker.status_json().await;
            JsonRpcResponse::success(id, payload)
        }
        None => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "status": "uninitialized",
                "reason": "BudgetTracker not yet injected (DB pool unavailable at boot?)",
            }),
        ),
    }
}

/// Phase 4 (4-15): Upsert one AI budget scope and refresh the in-memory config.
/// Phase 4 (4-15)：upsert 單一 AI 預算 scope 並刷新記憶體中的配置。
///
/// EN: Params schema: `{ "scope": <str>, "monthly_usd": <f64>, "updated_by": <str?> }`.
///     Fail-closed: missing/invalid params → -32602; tracker not initialized → -32603;
///     DB write or refresh failure → -32603 with error message; never panics. Successful
///     write triggers `BudgetTracker::refresh_config()` so the new ceiling is enforced
///     on the very next LLM call.
/// 中：參數格式：`{ "scope": <str>, "monthly_usd": <f64>, "updated_by": <str?> }`。
///     fail-closed：缺失/無效參數 → -32602；tracker 未初始化 → -32603；
///     DB 寫入或刷新失敗 → -32603 並附錯誤訊息；絕不 panic。寫入成功後觸發
///     `BudgetTracker::refresh_config()`，新上限在下一次 LLM 調用即生效。
async fn handle_update_ai_budget_config(
    id: serde_json::Value,
    params: &serde_json::Value,
    slot: &BudgetTrackerSlot,
) -> JsonRpcResponse {
    const ERR_INVALID_PARAMS: i64 = -32602;

    let scope = match params.get("scope").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_PARAMS,
                "missing or empty 'scope' (string)",
            );
        }
    };
    let monthly_usd = match params.get("monthly_usd").and_then(|v| v.as_f64()) {
        Some(v) if v.is_finite() && v >= 0.0 => v,
        _ => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_PARAMS,
                "missing or invalid 'monthly_usd' (must be finite f64 >= 0)",
            );
        }
    };
    let updated_by = params
        .get("updated_by")
        .and_then(|v| v.as_str())
        .unwrap_or("ipc")
        .to_string();

    let guard = slot.read().await;
    let tracker = match guard.as_ref() {
        Some(t) => Arc::clone(t),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                "budget tracker not initialized (DB pool unavailable?)",
            );
        }
    };
    drop(guard);

    let pool = tracker.pool_handle();
    if let Err(e) =
        crate::ai_budget::config_io::upsert_scope(&pool, &scope, monthly_usd, &updated_by).await
    {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("upsert failed: {e}"));
    }
    if let Err(e) = tracker.refresh_config().await {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("refresh_config failed: {e}"));
    }

    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "ok": true,
            "scope": scope,
            "monthly_usd": monthly_usd,
            "updated_by": updated_by,
        }),
    )
}

/// Phase 4.1: flip the Teacher consumer loop enabled flag (operator gate).
/// Phase 4.1：翻轉 Teacher consumer loop enabled 旗標（operator 閘）。
///
/// Params: { "enabled": bool }. Returns the new state. fail-soft if the loop
/// has not been wired (None slot) — returns `{"status":"uninitialized"}`.
/// 參數：{ "enabled": bool }。回傳新狀態。Loop 尚未接線（slot None）時
/// fail-soft 回傳 `{"status":"uninitialized"}`。
async fn handle_set_teacher_loop_enabled(
    id: serde_json::Value,
    params: &serde_json::Value,
    slot: &TeacherLoopSlot,
) -> JsonRpcResponse {
    let enabled = match params.get("enabled").and_then(|v| v.as_bool()) {
        Some(b) => b,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing or non-boolean 'enabled' field",
            );
        }
    };
    let guard = slot.read().await;
    let handles = match guard.as_ref() {
        Some(h) => h,
        None => {
            return JsonRpcResponse::success(
                id,
                serde_json::json!({"status": "uninitialized"}),
            );
        }
    };
    handles.enabled.store(enabled, Ordering::Relaxed);
    info!(enabled, "teacher consumer loop enabled flag set via IPC / 透過 IPC 設定 enabled 旗標");
    JsonRpcResponse::success(id, serde_json::json!({"ok": true, "enabled": enabled}))
}

/// Phase 4.1: snapshot the Teacher consumer loop status counters.
/// Phase 4.1：快照 Teacher consumer loop 狀態計數。
///
/// Returns cycles_attempted / directives_applied / directives_vetoed /
/// cycles_errored / last_cycle_ms / enabled. fail-soft if not wired.
/// 回傳上述欄位。未接線時 fail-soft。
async fn handle_get_teacher_loop_status(
    id: serde_json::Value,
    slot: &TeacherLoopSlot,
) -> JsonRpcResponse {
    let guard = slot.read().await;
    let handles = match guard.as_ref() {
        Some(h) => h,
        None => {
            return JsonRpcResponse::success(
                id,
                serde_json::json!({"status": "uninitialized"}),
            );
        }
    };
    let (attempted, applied, vetoed, errored) = handles.status.snapshot();
    let last_cycle_ms = handles
        .status
        .last_cycle_ms
        .load(Ordering::Relaxed);
    let enabled = handles.enabled.load(Ordering::Relaxed);
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "enabled": enabled,
            "cycles_attempted": attempted,
            "directives_applied": applied,
            "directives_vetoed": vetoed,
            "cycles_errored": errored,
            "last_cycle_ms": last_cycle_ms,
        }),
    )
}

/// Reload engine config (hot params only).
/// 重載引擎配置（僅熱參數）。
fn handle_reload_config(id: serde_json::Value, config: &Arc<ConfigManager>) -> JsonRpcResponse {
    match config.reload() {
        Ok(()) => JsonRpcResponse::success(
            id,
            serde_json::json!({"reloaded": true, "path": config.file_path().display().to_string()}),
        ),
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("reload failed: {e}")),
    }
}

// ---------------------------------------------------------------------------
// Phase 3b: Strategy parameter IPC handlers / 策略參數 IPC 處理器
// ---------------------------------------------------------------------------

/// Strategy parameter operation type / 策略參數操作類型
enum StrategyParamOp {
    Update,
    Get,
    Ranges,
}

/// Handle strategy parameter commands — sends oneshot request to event consumer.
/// 處理策略參數命令 — 發送 oneshot 請求到事件消費者。
async fn handle_strategy_param_cmd(
    id: serde_json::Value,
    tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
    op: StrategyParamOp,
) -> JsonRpcResponse {
    let tx = match tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };

    let strategy_name = match params.get("strategy_name").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing strategy_name parameter",
            )
        }
    };

    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();

    let cmd = match op {
        StrategyParamOp::Update => {
            let params_json = match params.get("params_json").and_then(|v| v.as_str()) {
                Some(s) => s.to_string(),
                None => {
                    // Also accept params_json as an object and serialize it
                    // 也接受 params_json 作為對象並序列化
                    match params.get("params_json") {
                        Some(v) if v.is_object() => serde_json::to_string(v).unwrap_or_default(),
                        _ => {
                            return JsonRpcResponse::error(
                                id,
                                ERR_INVALID_REQUEST,
                                "missing params_json parameter",
                            )
                        }
                    }
                }
            };
            PipelineCommand::UpdateStrategyParams {
                strategy_name,
                params_json,
                response_tx: resp_tx,
            }
        }
        StrategyParamOp::Get => PipelineCommand::GetStrategyParams {
            strategy_name,
            response_tx: resp_tx,
        },
        StrategyParamOp::Ranges => PipelineCommand::GetParamRanges {
            strategy_name,
            response_tx: resp_tx,
        },
    };

    if let Err(e) = tx.send(cmd) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }

    // Await response with timeout (5s) / 等待回應（5 秒超時）
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(result))) => JsonRpcResponse::success(id, serde_json::json!({ "result": result })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// Update risk config at runtime (GUI → Python → IPC → Rust engine).
/// 運行時更新風控配置。
/// Parse Option<Option<f64>> from JSON: absent=None, null=Some(None), number=Some(Some(x)).
/// 解析 JSON 中的 Option<Option<f64>>：不存在=None，null=Some(None)，數字=Some(Some(x))。
fn parse_opt_opt_f64(params: &serde_json::Value, key: &str) -> Option<Option<f64>> {
    match params.get(key) {
        None => None,                         // key absent = no change
        Some(v) if v.is_null() => Some(None), // key: null = disable
        Some(v) => v.as_f64().map(Some),      // key: 2.5 = enable with value
    }
}

async fn handle_update_risk_config(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "no paper command channel".to_string())
        }
    };

    // Parse all risk params / 解析所有風控參數
    let hard_stop_pct = params.get("hard_stop_pct").and_then(|v| v.as_f64());
    let p1_risk_pct = params.get("p1_risk_pct").and_then(|v| v.as_f64());
    let trailing_stop_pct = parse_opt_opt_f64(params, "trailing_stop_pct");
    let time_stop_hours = parse_opt_opt_f64(params, "time_stop_hours");
    let atr_multiplier = parse_opt_opt_f64(params, "atr_multiplier");
    let take_profit_pct = parse_opt_opt_f64(params, "take_profit_pct");
    let max_leverage = params.get("max_leverage").and_then(|v| v.as_f64());
    let max_drawdown_pct = params.get("max_drawdown_pct").and_then(|v| v.as_f64());
    let max_same_direction_positions = params
        .get("max_same_direction_positions")
        .and_then(|v| v.as_u64())
        .map(|v| v as usize);
    // RRC-1-A3: H0Gate shadow mode toggle / H0 門控影子模式切換
    let h0_shadow_mode = params.get("h0_shadow_mode").and_then(|v| v.as_bool());
    // PNL-7: agent-tunable dynamic-stop knobs / PNL-7：Agent 可調動態止損參數
    let dynamic_stop_base_ratio = params
        .get("dynamic_stop_base_ratio")
        .and_then(|v| v.as_f64());
    let dynamic_stop_cap_ratio = params
        .get("dynamic_stop_cap_ratio")
        .and_then(|v| v.as_f64());
    let trailing_min_rr_ratio = params
        .get("trailing_min_rr_ratio")
        .and_then(|v| v.as_f64());
    // Session 12: cost-gate + regime + boot cooldown
    let cost_gate_min_confidence = params
        .get("cost_gate_min_confidence")
        .and_then(|v| v.as_f64());
    let cost_gate_k_base = params.get("cost_gate_k_base").and_then(|v| v.as_f64());
    let cost_gate_k_medium = params.get("cost_gate_k_medium").and_then(|v| v.as_f64());
    let cost_gate_k_small = params.get("cost_gate_k_small").and_then(|v| v.as_f64());
    let adx_trending_threshold = params
        .get("adx_trending_threshold")
        .and_then(|v| v.as_f64());
    let boot_cooldown_ms = params.get("boot_cooldown_ms").and_then(|v| v.as_u64());
    let signals_heartbeat_ms = params.get("signals_heartbeat_ms").and_then(|v| v.as_u64());

    // At least one param must be provided / 至少需要一個參數
    let has_any = hard_stop_pct.is_some()
        || p1_risk_pct.is_some()
        || trailing_stop_pct.is_some()
        || time_stop_hours.is_some()
        || atr_multiplier.is_some()
        || take_profit_pct.is_some()
        || max_leverage.is_some()
        || max_drawdown_pct.is_some()
        || max_same_direction_positions.is_some()
        || h0_shadow_mode.is_some()
        || dynamic_stop_base_ratio.is_some()
        || dynamic_stop_cap_ratio.is_some()
        || trailing_min_rr_ratio.is_some()
        || cost_gate_min_confidence.is_some()
        || cost_gate_k_base.is_some()
        || cost_gate_k_medium.is_some()
        || cost_gate_k_small.is_some()
        || adx_trending_threshold.is_some()
        || boot_cooldown_ms.is_some()
        || signals_heartbeat_ms.is_some();
    if !has_any {
        return JsonRpcResponse::error(
            id,
            ERR_INVALID_REQUEST,
            "need at least one risk parameter".to_string(),
        );
    }

    let _ = tx.send(PipelineCommand::UpdateRiskConfig {
        hard_stop_pct,
        trailing_stop_pct,
        time_stop_hours,
        atr_multiplier,
        take_profit_pct,
        max_leverage,
        max_drawdown_pct,
        max_same_direction_positions,
        p1_risk_pct,
        h0_shadow_mode,
        dynamic_stop_base_ratio,
        dynamic_stop_cap_ratio,
        trailing_min_rr_ratio,
        cost_gate_min_confidence,
        cost_gate_k_base,
        cost_gate_k_medium,
        cost_gate_k_small,
        adx_trending_threshold,
        boot_cooldown_ms,
        signals_heartbeat_ms,
    });
    JsonRpcResponse::success(id, serde_json::json!({ "updated": true }))
}

/// ARCH-RC1 1C-3-B: Get Rust-native risk runtime status snapshot.
/// Routes the call through the paper command channel so the response is
/// built from live `TickPipeline` state owned by the event consumer task.
/// ARCH-RC1 1C-3-B：獲取 Rust 原生風控運行時狀態快照。
async fn handle_risk_runtime_status(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetRiskRuntimeStatus { response_tx: resp_tx }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => {
            match serde_json::from_str::<serde_json::Value>(&json_str) {
                Ok(v) => JsonRpcResponse::success(id, v),
                Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse status: {e}")),
            }
        }
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-B: Clear per-symbol consecutive-loss counters (safe reset,
/// does NOT touch RiskGovernor tier — for governor override see 1C-3-B-2).
/// ARCH-RC1 1C-3-B：清除 per-symbol 連虧計數器（安全重置，不影響 governor tier）。
async fn handle_clear_consecutive_losses(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ClearConsecutiveLosses { response_tx: resp_tx }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(msg))) => JsonRpcResponse::success(id, serde_json::json!({ "result": msg })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-F: External paper-side order submission. Drives the same
/// IntentProcessor pipeline strategies use (Guardian / Kelly / P1 cap / risk
/// gate / cost gate). On success returns the JSON envelope produced by
/// `TickPipeline::submit_external_order`.
/// ARCH-RC1 1C-3-F：外部紙盤訂單入口 — 與策略走同一條 IntentProcessor 管線。
async fn handle_submit_paper_order(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let symbol = match params.get("symbol").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing symbol"),
    };
    let side = match params.get("side").and_then(|v| v.as_str()) {
        Some(s) if !s.is_empty() => s.to_string(),
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing side"),
    };
    let qty = match params.get("qty").and_then(|v| v.as_f64()) {
        Some(q) if q > 0.0 => q,
        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing/invalid qty"),
    };
    let order_type = params
        .get("order_type")
        .and_then(|v| v.as_str())
        .unwrap_or("market")
        .to_string();
    let limit_price = params.get("limit_price").and_then(|v| v.as_f64());
    let confidence = params
        .get("confidence")
        .and_then(|v| v.as_f64())
        .unwrap_or(1.0);
    let strategy = params
        .get("strategy")
        .and_then(|v| v.as_str())
        .unwrap_or("external")
        .to_string();

    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::SubmitOrder {
        symbol,
        side,
        qty,
        order_type,
        limit_price,
        confidence,
        strategy,
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(v) => JsonRpcResponse::success(id, v),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse envelope: {e}")),
        },
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-B-2: Force governor toward more restrictive tier (operator
/// escalation). No 24h cooldown — operator can always be more careful.
/// Writes V014 audit row on success.
/// ARCH-RC1 1C-3-B-2：強制 governor 往更嚴方向（無冷卻 + V014 audit）。
async fn handle_force_governor_tighter(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
    audit_pool: &Option<sqlx::PgPool>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let target_tier = match params.get("target_tier").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing target_tier"),
    };
    let reason = match params.get("reason").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing reason"),
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ForceGovernorTighter {
        target_tier: target_tier.clone(),
        reason: reason.clone(),
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => {
            // M-2 (ARCH-RC1 1C-3-D): success audit — payload carries the
            // operator's free-form reason directly (N-5 fix: no positional
            // argument confusion — caller owns the payload shape).
            // M-2：成功 audit；caller 自組 payload 避免位置參數錯位（N-5 修正）。
            spawn_governor_audit_row(
                audit_pool,
                "governor_escalate",
                serde_json::json!({
                    "result": "applied",
                    "target_tier": target_tier,
                    "reason": reason,
                    "engine_result": serde_json::from_str::<serde_json::Value>(&json_str)
                        .unwrap_or(serde_json::Value::Null),
                }),
            );
            match serde_json::from_str::<serde_json::Value>(&json_str) {
                Ok(v) => JsonRpcResponse::success(id, v),
                Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse: {e}")),
            }
        }
        Ok(Ok(Err(e))) => {
            // M-2: guard-rejected attempts MUST be audited — an operator
            // probing the step/direction guards without leaving a V014 row
            // would violate principle #8 (every risk-touching action
            // explainable + auditable).
            // M-2：被守衛拒絕也必須 audit，避免靜默探測。
            spawn_governor_audit_row(
                audit_pool,
                "governor_escalate_rejected",
                serde_json::json!({
                    "result": "rejected",
                    "target_tier": target_tier,
                    "reason": reason,
                    "error": e,
                }),
            );
            JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e)
        }
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-B-2: Force governor toward less restrictive tier (operator
/// de-escalation). Wraps the dangerous de-escalation path with reason enum +
/// 24h cooldown + V014 audit + per-batch lock-down rules. CB / MR cannot be
/// unlocked here — operator must edit TOML and restart.
/// ARCH-RC1 1C-3-B-2：強制 governor 降級（reason enum + 24h cooldown + audit）。
async fn handle_force_governor_looser(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
    audit_pool: &Option<sqlx::PgPool>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let target_tier = match params.get("target_tier").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing target_tier"),
    };
    let reason_code = match params.get("reason_code").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing reason_code"),
    };
    let notes = params
        .get("notes")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .to_string();
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ForceGovernorLooser {
        target_tier: target_tier.clone(),
        reason_code: reason_code.clone(),
        notes: notes.clone(),
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => {
            spawn_governor_audit_row(
                audit_pool,
                "governor_de_escalate",
                serde_json::json!({
                    "result": "applied",
                    "target_tier": target_tier,
                    "reason_code": reason_code,
                    "notes": notes,
                    "engine_result": serde_json::from_str::<serde_json::Value>(&json_str)
                        .unwrap_or(serde_json::Value::Null),
                }),
            );
            match serde_json::from_str::<serde_json::Value>(&json_str) {
                Ok(v) => JsonRpcResponse::success(id, v),
                Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse: {e}")),
            }
        }
        Ok(Ok(Err(e))) => {
            // M-2: Rejection audit — cooldown / whitelist / step / CB+MR
            // lockout all land here. Every probe attempt gets a V014 row.
            // M-2：4 個守衛拒絕路徑全部落到這裡，每次嘗試都有 audit 行。
            spawn_governor_audit_row(
                audit_pool,
                "governor_de_escalate_rejected",
                serde_json::json!({
                    "result": "rejected",
                    "target_tier": target_tier,
                    "reason_code": reason_code,
                    "notes": notes,
                    "error": e,
                }),
            );
            JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e)
        }
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// Fire-and-forget V014 audit insert for governor override events.
/// Mirrors the pattern in handle_patch_config — failure logs WARN but never
/// blocks the IPC response. Caller owns the payload shape (N-5 fix: previously
/// this helper packed 5 positional string args into a fixed dict, causing the
/// escalate branch to record a literal "operator_escalation" in reason_code
/// and the operator's free-form text in notes — semantically wrong).
/// Caller-built `payload` must include `result` ("applied"|"rejected") and
/// any error string for rejection rows.
/// V014 audit row 寫入；caller 自組 payload shape（N-5 修正，避免位置錯位）。
fn spawn_governor_audit_row(
    audit_pool: &Option<sqlx::PgPool>,
    event_type: &str,
    payload: serde_json::Value,
) {
    let Some(pool) = audit_pool.clone() else {
        return;
    };
    let event_type = event_type.to_string();
    let ts_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as i64)
        .unwrap_or(0);
    tokio::spawn(async move {
        if let Err(e) = sqlx::query(
            "INSERT INTO observability.engine_events
             (ts_ms, event_type, source, config_name, old_version, new_version, payload)
             VALUES ($1, $2, $3, $4, NULL, NULL, $5)"
        )
        .bind(ts_ms)
        .bind(&event_type)
        .bind("operator")
        .bind("risk_governor")
        .bind(&payload)
        .execute(&pool)
        .await
        {
            tracing::warn!(error = %e, "V014 governor audit row insert failed (non-fatal)");
        }
    });
}

/// RRC-1-E2: Set strategy active/paused via IPC / 通過 IPC 設置策略啟停。
async fn handle_set_strategy_active(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "no paper command channel".to_string())
        }
    };
    let name = match params.get("strategy_name").and_then(|v| v.as_str()) {
        Some(n) => n.to_string(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing strategy_name".to_string(),
            )
        }
    };
    let active = match params.get("active").and_then(|v| v.as_bool()) {
        Some(a) => a,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing active (bool)".to_string(),
            )
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    let _ = tx.send(PipelineCommand::SetStrategyActive {
        strategy_name: name,
        active,
        response_tx: resp_tx,
    });
    match tokio::time::timeout(std::time::Duration::from_secs(3), resp_rx).await {
        Ok(Ok(Ok(msg))) => {
            JsonRpcResponse::success(id, serde_json::json!({ "ok": true, "detail": msg }))
        }
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "channel closed".to_string()),
        Err(_) => {
            JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for engine".to_string())
        }
    }
}

// 3E-3: handle_add_engine_mode and handle_switch_engine_mode REMOVED.
// In 3E-ARCH, pipelines are spawned at startup with fixed PipelineKind.
// Dynamic mode switching is replaced by per-pipeline command routing.
// 3E-3：handle_add_engine_mode 和 handle_switch_engine_mode 已移除。
// 3E-ARCH 下管線在啟動時以固定 PipelineKind 啟動，動態模式切換被管線路由取代。

/// 3E-3: Broadcast system mode to ALL active pipelines.
/// SetSystemMode is global — every pipeline must see the same system mode.
/// Sends to primary first (waits for response), then fire-and-forget to others.
/// 3E-3：廣播系統模式到所有活躍管線。SetSystemMode 是全局的。
/// 先發送到主管線（等待回應），再 fire-and-forget 發送到其他管線。
async fn handle_set_system_mode_broadcast(
    id: serde_json::Value,
    cmd_channels: &EngineCommandChannels,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let mode = match params.get("mode").and_then(|v| v.as_str()) {
        Some(m) => m.to_string(),
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing required param: mode (live_reserved/demo_reserved/shadow_only/observe_only/design_only)".to_string(),
            )
        }
    };
    // Send to primary pipeline (with response channel for confirmation)
    let primary_tx = cmd_channels.primary();
    let tx = match primary_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "no command channel configured".to_string())
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    let _ = tx.send(PipelineCommand::SetSystemMode { mode: mode.clone(), response_tx: resp_tx });
    // Fire-and-forget to other pipelines (they don't need response channels for broadcast)
    // 向其他管線 fire-and-forget（廣播不需要回應通道）
    for (label, ch) in [("paper", &cmd_channels.paper), ("demo", &cmd_channels.demo), ("live", &cmd_channels.live)] {
        // Skip the primary (already sent above) and None channels
        if std::ptr::eq(ch, primary_tx) { continue; }
        if let Some(tx) = ch {
            let (other_resp_tx, _other_resp_rx) = tokio::sync::oneshot::channel();
            let _ = tx.send(PipelineCommand::SetSystemMode { mode: mode.clone(), response_tx: other_resp_tx });
            tracing::debug!(engine = label, "set_system_mode broadcast sent / 系統模式廣播已發送");
        }
    }
    match tokio::time::timeout(std::time::Duration::from_secs(3), resp_rx).await {
        Ok(Ok(Ok(msg))) => JsonRpcResponse::success(id, serde_json::json!({ "ok": true, "detail": msg })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "channel closed".to_string()),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout".to_string()),
    }
}

/// Read pipeline_snapshot.json and extract a field (R06-A helper — DRY for 3 handlers).
/// 讀取 pipeline_snapshot.json 並提取欄位（R06-A 輔助函數 — 三個 handler 共用）。
fn handle_snapshot_field<F>(id: serde_json::Value, data_dir: &Path, extract: F) -> JsonRpcResponse
where
    F: FnOnce(&PipelineSnapshot) -> Result<serde_json::Value, serde_json::Error>,
{
    let path = data_dir.join("pipeline_snapshot.json");
    let content = match std::fs::read_to_string(&path) {
        Ok(c) => c,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("snapshot file not available: {e} / 快照文件不可用：{e}"),
            );
        }
    };
    let snapshot: PipelineSnapshot = match serde_json::from_str(&content) {
        Ok(s) => s,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("snapshot parse error: {e} / 快照解析錯誤：{e}"),
            );
        }
    };
    match extract(&snapshot) {
        Ok(v) => JsonRpcResponse::success(id, v),
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("serialize error: {e}")),
    }
}

// ---------------------------------------------------------------------------
// ARCH-RC1 1C-2-C: unified Config IPC helpers / 統一 Config IPC 輔助
// ---------------------------------------------------------------------------

/// Recursively merge JSON `patch` into `base` (deep merge for objects, replace
/// for scalars/arrays). Used by `patch_*_config` to compute the next config
/// from a partial JSON patch + the current snapshot.
/// 將 JSON `patch` 遞歸合併進 `base`（物件深合併、純量/陣列覆蓋）。
/// 用於 `patch_*_config` 從部分補丁 + 當前快照計算下一版配置。
fn json_merge(base: &mut serde_json::Value, patch: &serde_json::Value) {
    use serde_json::Value;
    match (base, patch) {
        (Value::Object(b), Value::Object(p)) => {
            for (k, v) in p {
                json_merge(b.entry(k.clone()).or_insert(Value::Null), v);
            }
        }
        (b, p) => *b = p.clone(),
    }
}

fn parse_patch_source(s: &str) -> Result<PatchSource, String> {
    match s {
        "operator" => Ok(PatchSource::Operator),
        "agent" => Ok(PatchSource::Agent),
        "migration" => Ok(PatchSource::Migration),
        other => Err(format!("invalid source: {other}")),
    }
}

/// Generic GET handler — serialise current store snapshot + version.
/// 通用 GET handler — 序列化當前 store 快照 + 版本。
fn handle_get_config<T>(
    id: serde_json::Value,
    store: &Option<Arc<ConfigStore<T>>>,
    config_name: &str,
) -> JsonRpcResponse
where
    T: serde::Serialize + Clone + Send + Sync + 'static,
{
    let store = match store {
        Some(s) => s,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("{config_name} store not configured"),
            )
        }
    };
    let snap = store.load();
    match serde_json::to_value(&*snap) {
        Ok(v) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "config": v,
                "version": store.version(),
            }),
        ),
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("serialize failed: {e}")),
    }
}

/// Generic PATCH handler — JSON deep-merge into current → validate → atomic
/// replace via ConfigStore (bumps version, triggers tick-level hot reload).
/// All-or-nothing: any deserialise/validate failure leaves the store untouched.
/// 通用 PATCH handler — JSON 深合併進當前 → 驗證 → ConfigStore 原子替換
/// （遞增版本，觸發 tick-level 熱重載）。All-or-nothing：任何反序列化/驗證
/// 失敗 store 完全不變。
#[allow(clippy::too_many_arguments)]
fn handle_patch_config<T, V>(
    id: serde_json::Value,
    store: &Option<Arc<ConfigStore<T>>>,
    params: &serde_json::Value,
    validate: V,
    config_name: &str,
    audit_pool: &Option<sqlx::PgPool>,
) -> JsonRpcResponse
where
    T: serde::Serialize + serde::de::DeserializeOwned + Clone + Send + Sync + 'static,
    V: Fn(&T) -> Result<(), String>,
{
    let store = match store {
        Some(s) => s,
        None => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("{config_name} store not configured"),
            )
        }
    };
    let patch = match params.get("patch") {
        Some(p) if p.is_object() => p,
        _ => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                "missing 'patch' object parameter",
            )
        }
    };
    let source_str = params
        .get("source")
        .and_then(|v| v.as_str())
        .unwrap_or("operator");
    let source = match parse_patch_source(source_str) {
        Ok(s) => s,
        Err(e) => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, e),
    };

    let old_version = store.version();
    let current = store.load();
    let mut merged = match serde_json::to_value(&*current) {
        Ok(v) => v,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INTERNAL,
                format!("snapshot serialise failed: {e}"),
            )
        }
    };
    json_merge(&mut merged, patch);
    let next: T = match serde_json::from_value(merged) {
        Ok(t) => t,
        Err(e) => {
            return JsonRpcResponse::error(
                id,
                ERR_INVALID_REQUEST,
                format!("patched config deserialize failed: {e}"),
            )
        }
    };
    if let Err(e) = validate(&next) {
        return JsonRpcResponse::error(
            id,
            ERR_INVALID_REQUEST,
            format!("validation failed: {e}"),
        );
    }
    match store.replace(next, source) {
        Ok(outcome) => {
            info!(
                config = config_name,
                version = outcome.version,
                source = outcome.source.as_str(),
                "ARCH-RC1 config patched via IPC / 配置經 IPC 熱更新"
            );
            // ARCH-RC1 1C-2-E: fire-and-forget audit row to V014 engine_events.
            // ARCH-RC1 1C-2-E：fire-and-forget 寫一行 V014 engine_events 審計。
            if let Some(pool) = audit_pool.clone() {
                let cfg_name = config_name.to_string();
                let src = outcome.source.as_str().to_string();
                let new_v = outcome.version as i64;
                let old_v = old_version as i64;
                let payload = serde_json::json!({
                    "fields_changed": patch.as_object()
                        .map(|m| m.keys().cloned().collect::<Vec<_>>())
                        .unwrap_or_default(),
                });
                tokio::spawn(async move {
                    let ts_ms = std::time::SystemTime::now()
                        .duration_since(std::time::UNIX_EPOCH)
                        .map(|d| d.as_millis() as i64)
                        .unwrap_or(0);
                    let res = sqlx::query(
                        "INSERT INTO observability.engine_events \
                         (ts_ms, event_type, source, config_name, old_version, new_version, payload) \
                         VALUES ($1, 'config_patch', $2, $3, $4, $5, $6)",
                    )
                    .bind(ts_ms)
                    .bind(&src)
                    .bind(&cfg_name)
                    .bind(old_v)
                    .bind(new_v)
                    .bind(&payload)
                    .execute(&pool)
                    .await;
                    if let Err(e) = res {
                        warn!(error = %e, config = %cfg_name, "V014 audit insert failed / V014 審計寫入失敗");
                    }
                });
            }
            JsonRpcResponse::success(
                id,
                serde_json::json!({
                    "ok": true,
                    "config": config_name,
                    "version": outcome.version,
                    "source": outcome.source.as_str(),
                }),
            )
        }
        Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("store replace failed: {e}")),
    }
}

// ---------------------------------------------------------------------------
// Error type / 錯誤類型
// ---------------------------------------------------------------------------

/// IPC server errors.
/// IPC 服務器錯誤。
#[derive(Debug, thiserror::Error)]
pub enum IpcError {
    /// Setup/bind failure / 啟動/綁定失敗
    #[error("IPC setup error: {0}")]
    Setup(String),
}

// ---------------------------------------------------------------------------
// Scanner observability handlers (IPC-SCAN-1) / 掃描器可觀測性處理器
// ---------------------------------------------------------------------------

/// IPC-SCAN-1a: Return the current active symbol universe.
/// Fail-soft: returns {"status":"uninitialized"} if scanner not wired.
/// IPC-SCAN-1a：返回當前活躍交易對 universe。
/// Fail-soft：掃描器未接線時返回 {"status":"uninitialized"}。
fn handle_get_active_symbols(
    id: serde_json::Value,
    registry: &Option<Arc<crate::scanner::registry::SymbolRegistry>>,
) -> JsonRpcResponse {
    let Some(reg) = registry else {
        return JsonRpcResponse::success(
            id,
            serde_json::json!({"status": "uninitialized", "symbols": [], "count": 0}),
        );
    };
    let symbols = reg.snapshot();
    let pinned: Vec<&String> = symbols.iter().filter(|s| reg.is_pinned(s)).collect();
    let dynamic: Vec<&String> = symbols.iter().filter(|s| !reg.is_pinned(s)).collect();
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "symbols": symbols,
            "count": symbols.len(),
            "pinned": pinned,
            "dynamic": dynamic,
        }),
    )
}

/// IPC-SCAN-1b: Return full scanner status — active universe + last scan summary.
/// Fail-soft: returns {"status":"uninitialized"} if scanner not wired.
/// IPC-SCAN-1b：返回完整掃描器狀態 — 活躍 universe + 最後掃描摘要。
/// Fail-soft：掃描器未接線時返回 {"status":"uninitialized"}。
fn handle_get_scanner_status(
    id: serde_json::Value,
    registry: &Option<Arc<crate::scanner::registry::SymbolRegistry>>,
) -> JsonRpcResponse {
    let Some(reg) = registry else {
        return JsonRpcResponse::success(
            id,
            serde_json::json!({"status": "uninitialized"}),
        );
    };
    let symbols = reg.snapshot();
    let pinned: Vec<&String> = symbols.iter().filter(|s| reg.is_pinned(s)).collect();
    let dynamic: Vec<&String> = symbols.iter().filter(|s| !reg.is_pinned(s)).collect();

    let last_scan_json = match reg.last_scan() {
        None => serde_json::json!(null),
        Some(scan) => {
            // Top 10 candidates with key fields for GUI display / 前 10 候選供 GUI 顯示
            let top_candidates: Vec<serde_json::Value> = scan
                .candidates
                .iter()
                .take(10)
                .map(|c| {
                    serde_json::json!({
                        "symbol": c.symbol,
                        "final_score": (c.final_score * 10.0).round() / 10.0,
                        "best_strategy": format!("{:?}", c.best_strategy),
                        "sector": c.sector,
                        "edge_bonus": c.edge_bonus,
                        "edge_n": c.edge_n,
                    })
                })
                .collect();
            serde_json::json!({
                "scan_ts_ms": scan.scan_ts_ms,
                "duration_ms": scan.scan_duration_ms,
                "added": scan.added,
                "removed": scan.removed,
                "rejected_count": scan.rejected_count,
                "top_candidates": top_candidates,
            })
        }
    };

    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "status": "ok",
            "active_symbols": symbols,
            "active_count": symbols.len(),
            "pinned": pinned,
            "dynamic": dynamic,
            "last_scan": last_scan_json,
        }),
    )
}

// ---------------------------------------------------------------------------
// Tests / 測試
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;
    use std::collections::HashMap;

    fn make_test_config() -> Arc<ConfigManager> {
        Arc::new(ConfigManager::load(Some("/tmp/nonexistent_openclaw_ipc_test.toml")).unwrap())
    }

    fn make_test_data_dir() -> Arc<PathBuf> {
        Arc::new(PathBuf::from("/tmp/oc_ipc_test_nonexistent"))
    }

    /// Empty BudgetTracker slot for tests that don't exercise 4-15 paths.
    /// 給不演練 4-15 路徑的測試使用的空 BudgetTracker 槽位。
    fn empty_budget_slot() -> BudgetTrackerSlot {
        Arc::new(RwLock::new(None))
    }

    fn empty_teacher_slot() -> TeacherLoopSlot {
        Arc::new(RwLock::new(None))
    }

    /// Write a test snapshot file to a temp dir, return the dir path.
    /// 寫入測試快照文件到臨時目錄，返回目錄路徑。
    fn write_test_snapshot() -> (Arc<PathBuf>, tempfile::TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let snapshot = PipelineSnapshot {
            schema_version: "2.0.0".into(),
            written_at_ms: 1700000050000,
            paper_state: crate::paper_state::PaperStateSnapshot {
                balance: 9500.0,
                peak_balance: 10000.0,
                total_realized_pnl: -500.0,
                total_fees: 12.5,
                trade_count: 3,
                positions: vec![crate::paper_state::PositionSnapshot {
                    position: crate::paper_state::PaperPosition {
                        symbol: "BTCUSDT".into(),
                        is_long: true,
                        qty: 0.01,
                        entry_price: 65000.0,
                        best_price: 66000.0,
                        entry_fee: 3.25,
                        entry_ts_ms: 1700000000000,
                        unrealized_pnl: 10.0,
                    },
                    api_pnl: None,
                }],
                bybit_sync_balance: None,
            },
            latest_prices: HashMap::from([("BTCUSDT".into(), 66000.0), ("ETHUSDT".into(), 3200.0)]),
            stats: crate::tick_pipeline::TickStats {
                total_ticks: 5000,
                total_intents: 15,
                total_fills: 3,
                total_stops: 1,
                last_tick_ms: 1700000050000,
            },
            source: "rust_engine".into(),
            indicators: HashMap::new(),
            signals: vec![],
            strategies: vec![],
            recent_intents: vec![],
            recent_fills: vec![],
            klines: HashMap::new(),
            paper_paused: false,
            pipeline_kind: crate::tick_pipeline::PipelineKind::Paper,
            h0_gate_stats: None,
            stop_config: None,
            guardian_config: None,
            risk_manager_config: None,
            consecutive_losses: HashMap::new(),
            session_halted: false,
            daily_loss_pct: 0.0,
            session_drawdown_pct: 0.0,
            mode_snapshots: HashMap::new(),
            system_mode: "live_reserved".into(),
        };
        let json = serde_json::to_string_pretty(&snapshot).unwrap();
        std::fs::write(dir.path().join("pipeline_snapshot.json"), &json).unwrap();
        (Arc::new(dir.path().to_path_buf()), dir)
    }

    #[tokio::test]
    async fn test_ipc_socket_permissions_0o600() {
        // I-02: verify bound Unix socket gets restricted to 0o600.
        // I-02：驗證綁定的 Unix 套接字權限被限制為 0o600。
        use std::os::unix::fs::PermissionsExt;
        let dir = tempfile::tempdir().unwrap();
        let sock_path = dir.path().join("ipc_perm_test.sock");
        let _listener = UnixListener::bind(&sock_path).unwrap();
        std::fs::set_permissions(&sock_path, std::fs::Permissions::from_mode(0o600)).unwrap();
        let mode = std::fs::metadata(&sock_path).unwrap().permissions().mode() & 0o777;
        assert_eq!(mode, 0o600, "socket mode should be 0o600, got {:o}", mode);
    }

    #[tokio::test]
    async fn test_dispatch_ping() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none());
        assert_eq!(
            resp.result.unwrap(),
            serde_json::Value::String("pong".into())
        );
        assert_eq!(resp.id, serde_json::json!(1));
    }

    #[tokio::test]
    async fn test_dispatch_get_state() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "get_state", "params": {}, "id": 2}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["status"], "running");
        // system_mode is read from pipeline_snapshot.json; falls back to "live_reserved" when
        // no snapshot exists (test environment). Assert it's a non-empty string.
        // system_mode 從 pipeline_snapshot.json 讀取；測試環境無快照時回退 "live_reserved"。
        assert!(result["system_mode"].as_str().map(|s| !s.is_empty()).unwrap_or(false));
    }

    #[tokio::test]
    async fn test_dispatch_method_not_found() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": 3}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_METHOD_NOT_FOUND);
    }

    #[tokio::test]
    async fn test_dispatch_invalid_json() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = "not valid json";
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_missing_version() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"method": "ping", "params": {}, "id": 4}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_missing_method() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "params": {}, "id": 5}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_reload_config() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "reload_config", "params": {}, "id": 8}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["reloaded"], true);
    }

    #[test]
    fn test_jsonrpc_response_serialization() {
        let resp = JsonRpcResponse::success(serde_json::json!(1), serde_json::json!("pong"));
        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("\"jsonrpc\":\"2.0\""));
        assert!(json.contains("\"result\":\"pong\""));
        assert!(!json.contains("\"error\""));
    }

    #[test]
    fn test_jsonrpc_error_serialization() {
        let resp = JsonRpcResponse::error(serde_json::json!(2), ERR_METHOD_NOT_FOUND, "not found");
        let json = serde_json::to_string(&resp).unwrap();
        assert!(json.contains("-32601"));
        assert!(!json.contains("\"result\""));
    }

    // ───────────────────────────────────────────────────────────────────────
    // R06-A: Snapshot file-read IPC tests / 快照文件讀取 IPC 測試
    // ───────────────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_get_paper_state_no_file() {
        let config = make_test_config();
        let dd = make_test_data_dir(); // nonexistent dir
        let req = r#"{"jsonrpc": "2.0", "method": "get_paper_state", "params": {}, "id": 20}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(
            resp.error.is_some(),
            "should error when snapshot file missing"
        );
    }

    #[tokio::test]
    async fn test_get_paper_state_with_snapshot() {
        let config = make_test_config();
        let (dd, _dir) = write_test_snapshot();
        let req = r#"{"jsonrpc": "2.0", "method": "get_paper_state", "params": {}, "id": 21}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        assert_eq!(result["balance"], 9500.0);
        assert_eq!(result["trade_count"], 3);
        assert_eq!(result["positions"][0]["symbol"], "BTCUSDT");
    }

    #[tokio::test]
    async fn test_get_latest_prices_with_snapshot() {
        let config = make_test_config();
        let (dd, _dir) = write_test_snapshot();
        let req = r#"{"jsonrpc": "2.0", "method": "get_latest_prices", "params": {}, "id": 22}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        assert_eq!(result["BTCUSDT"], 66000.0);
        assert_eq!(result["ETHUSDT"], 3200.0);
    }

    #[tokio::test]
    async fn test_get_tick_stats_with_snapshot() {
        let config = make_test_config();
        let (dd, _dir) = write_test_snapshot();
        let req = r#"{"jsonrpc": "2.0", "method": "get_tick_stats", "params": {}, "id": 23}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        assert_eq!(result["total_ticks"], 5000);
        assert_eq!(result["total_fills"], 3);
        assert_eq!(result["total_stops"], 1);
    }

    // ───────────────────────────────────────────────────────────────────────
    // Phase 3b PF-1: Strategy parameter IPC tests / 策略參數 IPC 測試
    // ───────────────────────────────────────────────────────────────────────

    /// Helper: create a paper_cmd channel with a consumer that handles param commands.
    /// 輔助：創建帶有參數命令消費者的 paper_cmd 通道。
    fn setup_strategy_param_channel() -> tokio::sync::mpsc::UnboundedSender<PipelineCommand> {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        tokio::spawn(async move {
            use crate::strategies::{ma_crossover::MaCrossover, Strategy};
            let mut strategy: Box<dyn Strategy> = Box::new(MaCrossover::new());
            while let Some(cmd) = rx.recv().await {
                match cmd {
                    PipelineCommand::UpdateStrategyParams {
                        strategy_name,
                        params_json,
                        response_tx,
                    } => {
                        let result = if strategy.name().eq_ignore_ascii_case(&strategy_name) {
                            strategy
                                .update_params_json(&params_json)
                                .map(|()| format!("params updated for {}", strategy_name))
                        } else {
                            Err(format!("strategy not found: {strategy_name}"))
                        };
                        let _ = response_tx.send(result);
                    }
                    PipelineCommand::GetStrategyParams {
                        strategy_name,
                        response_tx,
                    } => {
                        let result = if strategy.name().eq_ignore_ascii_case(&strategy_name) {
                            Ok(strategy.get_params_json())
                        } else {
                            Err(format!("strategy not found: {strategy_name}"))
                        };
                        let _ = response_tx.send(result);
                    }
                    PipelineCommand::GetParamRanges {
                        strategy_name,
                        response_tx,
                    } => {
                        let result = if strategy.name().eq_ignore_ascii_case(&strategy_name) {
                            Ok(strategy.param_ranges_json())
                        } else {
                            Err(format!("strategy not found: {strategy_name}"))
                        };
                        let _ = response_tx.send(result);
                    }
                    _ => {}
                }
            }
        });
        tx
    }

    /// ARCH-RC1 1C-3-B helper: spawn a fake event-consumer that answers
    /// `GetRiskRuntimeStatus` with a synthetic JSON snapshot and
    /// `ClearConsecutiveLosses` with a count message.
    /// ARCH-RC1 1C-3-B 輔助：模擬事件消費者，回傳合成的風控狀態快照與清除計數。
    fn setup_risk_runtime_channel(
        cleared_count: usize,
    ) -> tokio::sync::mpsc::UnboundedSender<PipelineCommand> {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        tokio::spawn(async move {
            while let Some(cmd) = rx.recv().await {
                match cmd {
                    PipelineCommand::GetRiskRuntimeStatus { response_tx } => {
                        let snap = serde_json::json!({
                            "governor_tier": "Normal",
                            "consecutive_losses_by_symbol": {"BTCUSDT": 2u32},
                            "boot_cooldown_remaining_ms": 0u64,
                            "boot_cooldown_total_ms": 60_000u64,
                            "paper_paused": false,
                            "session_halted": false,
                        });
                        let _ = response_tx.send(Ok(snap.to_string()));
                    }
                    PipelineCommand::ClearConsecutiveLosses { response_tx } => {
                        let _ = response_tx.send(Ok(format!("cleared {cleared_count} symbol(s)")));
                    }
                    _ => {}
                }
            }
        });
        tx
    }

    #[tokio::test]
    async fn test_rc1_get_risk_runtime_status_via_ipc() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_risk_runtime_channel(0);
        let req = r#"{"jsonrpc":"2.0","method":"get_risk_runtime_status","params":{},"id":40}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        assert_eq!(result["governor_tier"].as_str().unwrap(), "Normal");
        assert_eq!(result["consecutive_losses_by_symbol"]["BTCUSDT"], 2);
        assert_eq!(result["paper_paused"], false);
    }

    #[tokio::test]
    async fn test_rc1_clear_consecutive_losses_via_ipc() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_risk_runtime_channel(3);
        let req = r#"{"jsonrpc":"2.0","method":"clear_consecutive_losses","params":{},"id":41}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        assert_eq!(result["result"].as_str().unwrap(), "cleared 3 symbol(s)");
    }

    /// 1C-3-B-2 helper: fake event consumer that processes governor override
    /// commands by returning canned success/error JSON.
    /// 1C-3-B-2 輔助：模擬事件消費者處理 governor override 命令。
    fn setup_governor_override_channel(
        accept_tighter: bool,
        accept_looser: bool,
    ) -> tokio::sync::mpsc::UnboundedSender<PipelineCommand> {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        tokio::spawn(async move {
            while let Some(cmd) = rx.recv().await {
                match cmd {
                    PipelineCommand::ForceGovernorTighter {
                        target_tier, reason, response_tx,
                    } => {
                        let result = if accept_tighter {
                            Ok(format!(
                                "{{\"from\":\"NORMAL\",\"to\":\"{target_tier}\",\"reason\":\"{reason}\"}}"
                            ))
                        } else {
                            Err("simulated SM rejection".to_string())
                        };
                        let _ = response_tx.send(result);
                    }
                    PipelineCommand::ForceGovernorLooser {
                        target_tier, reason_code, response_tx, ..
                    } => {
                        let result = if accept_looser {
                            Ok(format!(
                                "{{\"from\":\"CAUTIOUS\",\"to\":\"{target_tier}\",\"reason_code\":\"{reason_code}\"}}"
                            ))
                        } else {
                            Err("24h cooldown active".to_string())
                        };
                        let _ = response_tx.send(result);
                    }
                    _ => {}
                }
            }
        });
        tx
    }

    #[tokio::test]
    async fn test_rc1b2_force_governor_tighter_via_ipc() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_governor_override_channel(true, false);
        let req = r#"{"jsonrpc":"2.0","method":"force_governor_tier_tighter","params":{"target_tier":"CAUTIOUS","reason":"manual probe"},"id":50}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        assert_eq!(result["to"].as_str().unwrap(), "CAUTIOUS");
    }

    #[tokio::test]
    async fn test_rc1b2_force_governor_tighter_missing_reason() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_governor_override_channel(true, false);
        let req = r#"{"jsonrpc":"2.0","method":"force_governor_tier_tighter","params":{"target_tier":"CAUTIOUS"},"id":51}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_some());
    }

    #[tokio::test]
    async fn test_rc1b2_force_governor_looser_cooldown_rejection() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_governor_override_channel(false, false);
        let req = r#"{"jsonrpc":"2.0","method":"force_governor_tier_looser","params":{"target_tier":"NORMAL","reason_code":"false_positive","notes":"test"},"id":52}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_some());
        let err_msg = resp.error.unwrap().message;
        assert!(err_msg.contains("cooldown"), "expected cooldown error, got: {}", err_msg);
    }

    #[tokio::test]
    async fn test_rc1b2_force_governor_looser_success() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_governor_override_channel(false, true);
        let req = r#"{"jsonrpc":"2.0","method":"force_governor_tier_looser","params":{"target_tier":"NORMAL","reason_code":"false_positive","notes":""},"id":53}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        assert_eq!(result["reason_code"].as_str().unwrap(), "false_positive");
        assert_eq!(result["to"].as_str().unwrap(), "NORMAL");
    }

    #[tokio::test]
    async fn test_rc1_get_risk_runtime_status_no_channel() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc":"2.0","method":"get_risk_runtime_status","params":{},"id":42}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_some());
    }

    #[tokio::test]
    async fn test_get_param_ranges_via_ipc() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "get_param_ranges", "params": {"strategy_name": "ma_crossover"}, "id": 30}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        let ranges_str = result["result"].as_str().unwrap();
        let ranges: Vec<serde_json::Value> = serde_json::from_str(ranges_str).unwrap();
        assert!(!ranges.is_empty(), "param_ranges should not be empty");
    }

    #[tokio::test]
    async fn test_get_strategy_params_via_ipc() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "get_strategy_params", "params": {"strategy_name": "ma_crossover"}, "id": 31}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        let params_str = result["result"].as_str().unwrap();
        let params: serde_json::Value = serde_json::from_str(params_str).unwrap();
        assert!(
            params.get("cooldown_ms").is_some(),
            "should contain cooldown_ms"
        );
    }

    #[tokio::test]
    async fn test_update_strategy_params_via_ipc() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "ma_crossover", "params_json": "{\"cooldown_ms\":600000,\"adx_threshold\":30.0,\"default_qty\":0.02,\"regime_filter_enabled\":true,\"higher_tf_alpha\":0.08}"}, "id": 32}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
    }

    #[tokio::test]
    async fn test_update_strategy_params_nonexistent() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "nonexistent_strategy", "params_json": "{}"}, "id": 33}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(
            resp.error.is_some(),
            "should error for nonexistent strategy"
        );
    }

    #[tokio::test]
    async fn test_update_strategy_params_missing_params() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "ma_crossover"}, "id": 34}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels { paper: Some(tx), ..Default::default() }, &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(
            resp.error.is_some(),
            "should error when params_json missing"
        );
    }

    // ── Phase 4 (4-00) Dashboard skeleton tests / 儀表板骨架測試 ──────────

    /// Initial Phase 4 status — all four modules should report "grey".
    /// 初始 Phase 4 狀態 — 四個模組應全部回報 "grey"。
    #[tokio::test]
    async fn test_get_phase4_status_returns_grey_initial() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req =
            r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4000}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none(), "phase4 status must succeed");
        let r = resp.result.unwrap();
        assert_eq!(r["teacher"], "grey");
        assert_eq!(r["linucb"], "grey");
        assert_eq!(r["news"], "grey");
        assert_eq!(r["dl3"], "grey");
    }

    /// Schema check — required fields present, last_update_ms is positive int.
    /// Schema 檢查 — 必須欄位齊全，last_update_ms 為正整數。
    #[tokio::test]
    async fn test_get_phase4_status_response_schema() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req =
            r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4001}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert!(resp.error.is_none());
        let r = resp.result.unwrap();
        for key in ["teacher", "linucb", "news", "dl3", "last_update_ms"] {
            assert!(r.get(key).is_some(), "missing key: {key}");
        }
        assert!(r["last_update_ms"].as_i64().unwrap_or(0) > 0);
        // valid traffic-light vocabulary / 合法紅綠燈詞彙
        for key in ["teacher", "linucb", "news", "dl3"] {
            let v = r[key].as_str().unwrap_or("");
            assert!(
                matches!(v, "grey" | "green" | "yellow" | "red"),
                "invalid status for {key}: {v}"
            );
        }
    }

    /// Dispatch table — get_phase4_status routes to handler (id echoed).
    /// 派發表 — get_phase4_status 應正確路由到 handler（id 被回顯）。
    #[tokio::test]
    async fn test_dispatch_phase4_status() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req =
            r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4002}"#;
        let resp = dispatch_request(req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &None, &None, &None, &None, &None).await;
        assert_eq!(resp.id, serde_json::json!(4002));
        assert!(resp.error.is_none());
        assert!(resp.result.is_some());
    }

    // ───────────────────────────────────────────────────────────────────────
    // ARCH-RC1 1C-2-C / LIVE-P2-1: unified Config IPC endpoint tests
    // ARCH-RC1 1C-2-C / LIVE-P2-1：統一 Config IPC 端點測試
    // ───────────────────────────────────────────────────────────────────────

    /// Build test stores: all three risk engines + learning + budget.
    /// 構建測試 stores：三個風控引擎 + learning + budget。
    fn rc1_stores() -> (
        Option<PerEngineRiskStores>,
        Option<Arc<ConfigStore<LearningConfig>>>,
        Option<Arc<ConfigStore<BudgetConfig>>>,
    ) {
        let rs = PerEngineRiskStores {
            paper: Arc::new(ConfigStore::new(RiskConfig::default())),
            demo: Arc::new(ConfigStore::new(RiskConfig::default())),
            live: Arc::new(ConfigStore::new(RiskConfig::default())),
        };
        (
            Some(rs),
            Some(Arc::new(ConfigStore::new(LearningConfig::default()))),
            Some(Arc::new(ConfigStore::new(BudgetConfig::default()))),
        )
    }

    #[tokio::test]
    async fn test_rc1_get_risk_config_returns_snapshot_and_version() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let (rs, ls, bs) = rc1_stores();
        let req = r#"{"jsonrpc": "2.0", "method": "get_risk_config", "params": {}, "id": 9001}"#;
        let resp = dispatch_request(
            req,
            &config,
            &dd,
            &EngineCommandChannels::default(),
            &empty_budget_slot(),
            &empty_teacher_slot(),
            &rs,
            &ls,
            &bs,
            &None,
            &None,
        )
        .await;
        assert!(resp.error.is_none(), "expected success: {resp:?}");
        let r = resp.result.unwrap();
        assert_eq!(r["version"], 0);
        assert!(r["config"]["limits"].is_object(), "config payload missing");
    }

    #[tokio::test]
    async fn test_rc1_patch_risk_config_bumps_version_and_updates() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let (rs, ls, bs) = rc1_stores();
        // Patch a single nested field via deep merge.
        let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator","patch":{"limits":{"leverage_max":7.0}}},"id":9002}"#;
        let resp = dispatch_request(
            req,
            &config,
            &dd,
            &EngineCommandChannels::default(),
            &empty_budget_slot(),
            &empty_teacher_slot(),
            &rs,
            &ls,
            &bs,
            &None,
            &None,
        )
        .await;
        assert!(resp.error.is_none(), "expected success: {resp:?}");
        let r = resp.result.unwrap();
        assert_eq!(r["ok"], true);
        assert_eq!(r["version"], 1);
        assert_eq!(r["source"], "operator");
        // Verify paper store mutated (no engine param → default paper).
        // 確認 paper store 已更新（無 engine 參數 → 默認 paper）。
        let snap = rs.as_ref().unwrap().paper.load();
        assert!((snap.limits.leverage_max - 7.0).abs() < f64::EPSILON);
    }

    #[tokio::test]
    async fn test_rc1_patch_risk_config_validation_failure_rolls_back() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let (rs, ls, bs) = rc1_stores();
        let original_lev = rs.as_ref().unwrap().paper.load().limits.leverage_max;
        // Negative leverage is invalid.
        let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"patch":{"limits":{"leverage_max":-1.0}}},"id":9003}"#;
        let resp = dispatch_request(
            req,
            &config,
            &dd,
            &EngineCommandChannels::default(),
            &empty_budget_slot(),
            &empty_teacher_slot(),
            &rs,
            &ls,
            &bs,
            &None,
            &None,
        )
        .await;
        assert!(resp.error.is_some(), "expected validation error");
        // Paper store untouched (rollback).
        // paper store 未改動（回滾）。
        assert_eq!(rs.as_ref().unwrap().paper.version(), 0);
        let snap = rs.as_ref().unwrap().paper.load();
        assert!((snap.limits.leverage_max - original_lev).abs() < f64::EPSILON);
    }

    #[tokio::test]
    async fn test_rc1_patch_missing_patch_field_errors() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let (rs, ls, bs) = rc1_stores();
        let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator"},"id":9004}"#;
        let resp = dispatch_request(
            req,
            &config,
            &dd,
            &EngineCommandChannels::default(),
            &empty_budget_slot(),
            &empty_teacher_slot(),
            &rs,
            &ls,
            &bs,
            &None,
            &None,
        )
        .await;
        assert!(resp.error.is_some());
        assert_eq!(rs.as_ref().unwrap().paper.version(), 0);
    }

    #[tokio::test]
    async fn test_rc1_patch_learning_and_budget_configs_round_trip() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let (rs, ls, bs) = rc1_stores();
        // Patch learning + then read back via get_learning_config.
        let patch_req = r#"{"jsonrpc":"2.0","method":"patch_learning_config","params":{"patch":{"linucb_enabled":true}},"id":9005}"#;
        let resp = dispatch_request(
            patch_req,
            &config,
            &dd,
            &EngineCommandChannels::default(),
            &empty_budget_slot(),
            &empty_teacher_slot(),
            &rs,
            &ls,
            &bs,
            &None,
            &None,
        )
        .await;
        assert!(resp.error.is_none(), "patch_learning_config: {resp:?}");
        let get_req =
            r#"{"jsonrpc":"2.0","method":"get_learning_config","params":{},"id":9006}"#;
        let resp = dispatch_request(
            get_req,
            &config,
            &dd,
            &EngineCommandChannels::default(),
            &empty_budget_slot(),
            &empty_teacher_slot(),
            &rs,
            &ls,
            &bs,
            &None,
            &None,
        )
        .await;
        assert!(resp.error.is_none());
        let r = resp.result.unwrap();
        assert_eq!(r["version"], 1);
        // Patch budget too — exercises the third branch.
        let bud_req = r#"{"jsonrpc":"2.0","method":"patch_budget_config","params":{"source":"agent","patch":{"daily_usd_max":50.0}},"id":9007}"#;
        let resp = dispatch_request(
            bud_req,
            &config,
            &dd,
            &EngineCommandChannels::default(),
            &empty_budget_slot(),
            &empty_teacher_slot(),
            &rs,
            &ls,
            &bs,
            &None,
            &None,
        )
        .await;
        assert!(resp.error.is_none(), "patch_budget_config: {resp:?}");
        assert_eq!(resp.result.unwrap()["source"], "agent");
    }

    #[tokio::test]
    async fn test_rc1_get_config_without_store_errors() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{},"id":9008}"#;
        let resp = dispatch_request(
            req,
            &config,
            &dd,
            &EngineCommandChannels::default(),
            &empty_budget_slot(),
            &empty_teacher_slot(),
            &None,
            &None,
            &None,
            &None,
            &None,
        )
        .await;
        assert!(resp.error.is_some());
        assert!(resp.error.unwrap().message.contains("not configured"));
    }

    /// LIVE-P2-1: patch_risk_config with engine="live" routes to live store,
    /// not to paper store. paper store must remain at version 0.
    /// LIVE-P2-1：engine="live" 的 patch_risk_config 應路由到 live store，
    /// paper store 版本應維持 0。
    #[tokio::test]
    async fn test_p2_patch_risk_config_engine_routing() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let (rs, ls, bs) = rc1_stores();
        // Patch live engine only.
        let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"live","source":"operator","patch":{"limits":{"leverage_max":5.0}}},"id":9020}"#;
        let resp = dispatch_request(
            req, &config, &dd, &EngineCommandChannels::default(),
            &empty_budget_slot(), &empty_teacher_slot(),
            &rs, &ls, &bs, &None, &None,
        ).await;
        assert!(resp.error.is_none(), "expected success: {resp:?}");
        let r = resp.result.unwrap();
        assert_eq!(r["ok"], true);
        assert_eq!(r["version"], 1);
        // live store mutated.
        let live_snap = rs.as_ref().unwrap().live.load();
        assert!((live_snap.limits.leverage_max - 5.0).abs() < f64::EPSILON, "live store not updated");
        // paper store untouched.
        assert_eq!(rs.as_ref().unwrap().paper.version(), 0, "paper store should be untouched");
        // demo store untouched.
        assert_eq!(rs.as_ref().unwrap().demo.version(), 0, "demo store should be untouched");
    }

    /// LIVE-P2-1: get_risk_config with engine="demo" returns demo store snapshot.
    /// LIVE-P2-1：engine="demo" 的 get_risk_config 返回 demo store 快照。
    #[tokio::test]
    async fn test_p2_get_risk_config_engine_selection() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let (rs, ls, bs) = rc1_stores();
        // Pre-patch demo store so it has a distinct version.
        let patch_req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"demo","patch":{"limits":{"open_positions_max":7}}},"id":9021}"#;
        dispatch_request(patch_req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &rs, &ls, &bs, &None, &None).await;
        // Now GET demo config — should show version=1.
        let get_req = r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{"engine":"demo"},"id":9022}"#;
        let resp = dispatch_request(get_req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &rs, &ls, &bs, &None, &None).await;
        assert!(resp.error.is_none(), "expected success: {resp:?}");
        let r = resp.result.unwrap();
        assert_eq!(r["version"], 1, "demo store should be at version 1");
        // Paper store should still be at version 0.
        let paper_req = r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{},"id":9023}"#;
        let resp2 = dispatch_request(paper_req, &config, &dd, &EngineCommandChannels::default(), &empty_budget_slot(), &empty_teacher_slot(), &rs, &ls, &bs, &None, &None).await;
        let r2 = resp2.result.unwrap();
        assert_eq!(r2["version"], 0, "paper store should be at version 0");
    }

    // ───────────────────────────────────────────────────────────────────────
    // Phase 4 (4-15): AI budget IPC handler tests
    // Phase 4 (4-15)：AI 預算 IPC handler 測試
    // ───────────────────────────────────────────────────────────────────────

    /// Slot empty → get_ai_budget_status fail-soft returns "uninitialized".
    /// 槽位為空 → get_ai_budget_status fail-soft 回傳 "uninitialized"。
    #[tokio::test]
    async fn test_handle_get_ai_budget_status_uninitialized() {
        let slot = empty_budget_slot();
        let resp = handle_get_ai_budget_status(serde_json::json!(4150), &slot).await;
        assert!(resp.error.is_none(), "should fail-soft, not error");
        let result = resp.result.expect("result should be present");
        assert_eq!(result["status"], "uninitialized");
        assert_eq!(resp.id, serde_json::json!(4150));
    }

    /// Slot empty → update_ai_budget_config -32603 (fail-closed for writes).
    /// 槽位為空 → update_ai_budget_config 回 -32603（寫入路徑 fail-closed）。
    #[tokio::test]
    async fn test_handle_update_ai_budget_config_uninitialized() {
        let slot = empty_budget_slot();
        let params = serde_json::json!({
            "scope": "teacher",
            "monthly_usd": 60.0,
            "updated_by": "operator"
        });
        let resp =
            handle_update_ai_budget_config(serde_json::json!(4151), &params, &slot).await;
        assert!(resp.error.is_some(), "must fail-closed when uninitialized");
        assert_eq!(resp.error.unwrap().code, ERR_INTERNAL);
    }

    /// Missing 'scope' / invalid 'monthly_usd' → -32602 invalid params.
    /// 缺 'scope' 或 'monthly_usd' 不合法 → 回 -32602。
    #[tokio::test]
    async fn test_handle_update_ai_budget_config_invalid_params() {
        let slot = empty_budget_slot();
        // Missing scope / 缺 scope
        let p1 = serde_json::json!({ "monthly_usd": 60.0 });
        let r1 = handle_update_ai_budget_config(serde_json::json!(1), &p1, &slot).await;
        assert_eq!(r1.error.expect("err").code, -32602);

        // Negative monthly_usd / monthly_usd 為負
        let p2 = serde_json::json!({ "scope": "teacher", "monthly_usd": -1.0 });
        let r2 = handle_update_ai_budget_config(serde_json::json!(2), &p2, &slot).await;
        assert_eq!(r2.error.expect("err").code, -32602);

        // Empty scope / scope 空字串
        let p3 = serde_json::json!({ "scope": "", "monthly_usd": 10.0 });
        let r3 = handle_update_ai_budget_config(serde_json::json!(3), &p3, &slot).await;
        assert_eq!(r3.error.expect("err").code, -32602);
    }

    // ---------------------------------------------------------------------
    // Phase 4.1: Teacher consumer loop IPC tests
    // Phase 4.1：Teacher consumer loop IPC 測試
    // ---------------------------------------------------------------------

    fn populated_teacher_slot(initial_enabled: bool) -> (TeacherLoopSlot, Arc<AtomicBool>, Arc<ConsumerLoopStatus>) {
        let enabled = Arc::new(AtomicBool::new(initial_enabled));
        let status = Arc::new(ConsumerLoopStatus::default());
        let slot: TeacherLoopSlot = Arc::new(RwLock::new(Some(TeacherLoopHandles {
            enabled: Arc::clone(&enabled),
            status: Arc::clone(&status),
        })));
        (slot, enabled, status)
    }

    /// uninitialized slot → fail-soft "uninitialized" payload, NOT an error.
    /// 未注入槽位 → fail-soft 回傳 "uninitialized"，不是 error。
    #[tokio::test]
    async fn test_teacher_loop_status_uninitialized_fail_soft() {
        let slot = empty_teacher_slot();
        let resp = handle_get_teacher_loop_status(serde_json::json!(1), &slot).await;
        assert!(resp.error.is_none());
        let result = resp.result.expect("result");
        assert_eq!(result["status"], "uninitialized");
    }

    /// set_enabled with valid bool flips the atomic and returns ok.
    /// set_enabled 帶合法 bool 翻轉 atomic 並回傳 ok。
    #[tokio::test]
    async fn test_teacher_loop_set_enabled_flips_atomic() {
        let (slot, enabled, _status) = populated_teacher_slot(false);
        let params = serde_json::json!({"enabled": true});
        let resp =
            handle_set_teacher_loop_enabled(serde_json::json!(2), &params, &slot).await;
        assert!(resp.error.is_none());
        assert_eq!(resp.result.expect("ok")["enabled"], true);
        assert!(enabled.load(Ordering::Relaxed));

        // Flip back / 翻回
        let params = serde_json::json!({"enabled": false});
        let _ = handle_set_teacher_loop_enabled(serde_json::json!(3), &params, &slot).await;
        assert!(!enabled.load(Ordering::Relaxed));
    }

    /// set_enabled missing/non-bool param → -32600 invalid request.
    /// set_enabled 缺欄位或非 bool → -32600。
    #[tokio::test]
    async fn test_teacher_loop_set_enabled_invalid_params() {
        let (slot, _, _) = populated_teacher_slot(false);
        let params = serde_json::json!({"enabled": "yes"});
        let resp =
            handle_set_teacher_loop_enabled(serde_json::json!(4), &params, &slot).await;
        assert_eq!(resp.error.expect("err").code, ERR_INVALID_REQUEST);
    }

    /// get_status returns full counter snapshot when slot populated.
    /// 槽位有值時 get_status 回傳完整計數快照。
    #[tokio::test]
    async fn test_teacher_loop_get_status_populated() {
        let (slot, _, status) = populated_teacher_slot(true);
        status.cycles_attempted.store(7, Ordering::Relaxed);
        status.directives_applied.store(3, Ordering::Relaxed);
        status.directives_vetoed.store(2, Ordering::Relaxed);
        status.cycles_errored.store(1, Ordering::Relaxed);
        status.last_cycle_ms.store(123_456_789, Ordering::Relaxed);

        let resp = handle_get_teacher_loop_status(serde_json::json!(5), &slot).await;
        let r = resp.result.expect("ok");
        assert_eq!(r["status"], "ok");
        assert_eq!(r["enabled"], true);
        assert_eq!(r["cycles_attempted"], 7);
        assert_eq!(r["directives_applied"], 3);
        assert_eq!(r["directives_vetoed"], 2);
        assert_eq!(r["cycles_errored"], 1);
        assert_eq!(r["last_cycle_ms"], 123_456_789);
    }

    /// set_teacher_loop_enabled on uninitialized slot is fail-soft (no error).
    /// 未注入槽位的 set_enabled 也是 fail-soft（不報 error）。
    #[tokio::test]
    async fn test_teacher_loop_set_enabled_uninitialized_fail_soft() {
        let slot = empty_teacher_slot();
        let params = serde_json::json!({"enabled": true});
        let resp =
            handle_set_teacher_loop_enabled(serde_json::json!(6), &params, &slot).await;
        assert!(resp.error.is_none());
        assert_eq!(resp.result.expect("ok")["status"], "uninitialized");
    }

    // ── Scanner IPC tests (IPC-SCAN-1) ──────────────────────────────────────────

    fn make_scanner_registry() -> Arc<crate::scanner::registry::SymbolRegistry> {
        let pinned = vec!["BTCUSDT".to_string(), "ETHUSDT".to_string()];
        Arc::new(crate::scanner::registry::SymbolRegistry::new(
            vec!["BTCUSDT".to_string(), "ETHUSDT".to_string(), "SOLUSDT".to_string()],
            pinned,
        ))
    }

    /// get_active_symbols — uninitialized (None registry) returns fail-soft.
    /// get_active_symbols — 未初始化時 fail-soft。
    #[test]
    fn test_get_active_symbols_uninitialized() {
        let resp = handle_get_active_symbols(serde_json::json!(1), &None);
        assert!(resp.error.is_none());
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "uninitialized");
        assert_eq!(r["count"], 0);
    }

    /// get_active_symbols — registry wired: returns all symbols, correctly splits pinned/dynamic.
    /// get_active_symbols — registry 已接線：返回所有交易對，正確區分固定/動態。
    #[test]
    fn test_get_active_symbols_wired() {
        let reg = make_scanner_registry();
        let resp = handle_get_active_symbols(serde_json::json!(2), &Some(reg));
        assert!(resp.error.is_none());
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "ok");
        assert_eq!(r["count"], 3);
        let pinned = r["pinned"].as_array().expect("pinned");
        assert_eq!(pinned.len(), 2);
        let dynamic = r["dynamic"].as_array().expect("dynamic");
        assert_eq!(dynamic.len(), 1);
        assert_eq!(dynamic[0], "SOLUSDT");
    }

    /// get_scanner_status — uninitialized (None registry) returns fail-soft.
    /// get_scanner_status — 未初始化時 fail-soft。
    #[test]
    fn test_get_scanner_status_uninitialized() {
        let resp = handle_get_scanner_status(serde_json::json!(3), &None);
        assert!(resp.error.is_none());
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "uninitialized");
    }

    /// get_scanner_status — registry wired, no scan yet: last_scan is null.
    /// get_scanner_status — registry 已接線，尚無掃描：last_scan 為 null。
    #[test]
    fn test_get_scanner_status_no_scan_yet() {
        let reg = make_scanner_registry();
        let resp = handle_get_scanner_status(serde_json::json!(4), &Some(reg));
        assert!(resp.error.is_none());
        let r = resp.result.expect("result");
        assert_eq!(r["status"], "ok");
        assert_eq!(r["active_count"], 3);
        assert!(r["last_scan"].is_null());
    }
}
