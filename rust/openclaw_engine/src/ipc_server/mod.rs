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

mod handlers;
mod handlers_config;
// E5-P1-5: JSON-RPC params extraction & validation helpers (orphan §九).
//         Exposed as a sibling module so existing handlers.rs can adopt
//         incrementally without requiring a coordinated migration PR.
// E5-P1-5：JSON-RPC 參數提取與驗證輔助（§九 孤兒抽取）。
//         以兄弟模組暴露，讓現有 handlers.rs 可遞進採用，無需一次性大遷移。
pub(crate) mod param_extractor;
#[cfg(test)]
mod tests;

// Re-export handler functions so dispatch_request (in this file) and tests can use them.
// 重新導出 handler 函數，供 dispatch_request 和 tests 使用。
use handlers::*;
use handlers_config::*;

use crate::ai_budget::BudgetTracker;
use crate::claude_teacher::ConsumerLoopStatus;
use crate::config::{
    BudgetConfig, ConfigManager, ConfigStore, LearningConfig, PatchSource, RiskConfig,
};
use crate::tick_pipeline::PipelineSnapshot;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicBool, Ordering};
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

/// G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25): Late-injected slot
/// for the StrategistScheduler `CycleCounters` Arc.
///
/// MODULE_NOTE (EN): The IpcServer's `run()` future is detached BEFORE
///   `main_boot_tasks::spawn_strategist_scheduler` runs (scheduler depends
///   on db_pool readiness which is sequenced after IPC server detach in
///   main.rs). The slot is wrapped in `Arc<RwLock<Option<...>>>` so the
///   scheduler's counters Arc can be late-written without restarting IPC.
///   None = scheduler not yet spawned (Demo unbound) → IPC method returns
///   `{"status":"scheduler_unavailable"}` (fail-soft).
/// MODULE_NOTE (中)：IPC server `run()` 在 scheduler spawn 之前 detach；
///   slot 用 `Arc<RwLock<Option<...>>>` 讓 main.rs 在 scheduler spawn 後
///   late-inject。None = 未 spawn → IPC 回 scheduler_unavailable。
pub type StrategistCountersSlot =
    Arc<RwLock<Option<Arc<crate::strategist_scheduler::CycleCounters>>>>;

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

use crate::tick_pipeline::PipelineCommand;

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
    pub fn select(
        &self,
        engine: &str,
    ) -> &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> {
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

    /// Return the label of the primary engine ("live" / "demo" / "paper").
    /// 返回主引擎的標籤。
    pub fn primary_label(&self) -> &'static str {
        if self.live.is_some() {
            "live"
        } else if self.demo.is_some() {
            "demo"
        } else {
            "paper"
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
    /// G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25): shared
    /// late-injected `CycleCounters` slot from `StrategistScheduler`.
    /// IPC server detaches before scheduler spawn → must be a slot type so
    /// `main.rs` can write the counters Arc post-detach via
    /// `IpcServer::strategist_counters_slot()`.
    /// G3-11：scheduler `CycleCounters` slot；IPC server detach 後由 main.rs 寫入。
    strategist_counters: StrategistCountersSlot,
    /// PIPELINE-SLOT-1 Phase 3: fast-path wake-up to the Live auth watcher.
    /// Set in main.rs via [`IpcServer::set_live_auth_recheck_sender`] after
    /// `LiveAuthWatcher::new` returns its trigger handle. `None` when the
    /// engine is running without a Live pipeline (paper/demo-only build).
    ///
    /// PIPELINE-SLOT-1 Phase 3：Live 授權 watcher 的快路徑喚醒端。於
    /// main.rs `LiveAuthWatcher::new` 回傳 handle 後透過
    /// [`IpcServer::set_live_auth_recheck_sender`] 設定。無 Live 管線時
    /// 為 `None`。
    live_auth_recheck_tx: Option<tokio::sync::mpsc::Sender<()>>,
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
            strategist_counters: Arc::new(RwLock::new(None)),
            live_auth_recheck_tx: None,
        }
    }

    /// G3-11: get a clone of the `CycleCounters` slot for late injection
    /// from main.rs once the StrategistScheduler is spawned. Mirrors the
    /// `budget_tracker_slot` / `teacher_loop_slot` / `audit_pool_slot`
    /// pattern. Caller does
    /// `slot.write().await.replace(scheduler.cycle_counters())`.
    /// G3-11：取得 CycleCounters slot handle 給 main.rs scheduler spawn 後注入。
    pub fn strategist_counters_slot(&self) -> StrategistCountersSlot {
        Arc::clone(&self.strategist_counters)
    }

    /// PIPELINE-SLOT-1 Phase 3: wire the Live auth watcher's trigger
    /// sender so the `trigger_live_auth_recheck` IPC method can wake the
    /// watcher for sub-5s respawn / teardown TTR on operator renew/revoke.
    ///
    /// Call after `LiveAuthWatcher::new(...)` returns in main.rs, before
    /// `ipc_server.run()` starts accepting connections. Absent wiring is
    /// not an error — the IPC method will respond with a structured
    /// `watcher_disabled` status.
    ///
    /// PIPELINE-SLOT-1 Phase 3：接入 Live 授權 watcher 的 trigger sender，
    /// 讓 `trigger_live_auth_recheck` IPC method 在 operator renew/revoke
    /// 時 sub-5s 喚醒 watcher 完成 respawn / teardown。
    ///
    /// main.rs 中 `LiveAuthWatcher::new(...)` 回傳後、`ipc_server.run()`
    /// 開始接受連線前呼叫。未接線非錯誤 — IPC method 會回結構化
    /// `watcher_disabled` 狀態。
    pub fn set_live_auth_recheck_sender(&mut self, tx: tokio::sync::mpsc::Sender<()>) {
        self.live_auth_recheck_tx = Some(tx);
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
                            // G3-11: read the slot once per connection — Arc clone is cheap;
                            // late-injected counters become visible automatically without
                            // requiring an IPC server restart.
                            // G3-11：每連線讀一次 slot；scheduler 後綁的 counters 自動可見，
                            // IPC server 不需重啟。
                            let strategist_counters =
                                self.strategist_counters.read().await.clone();
                            let live_auth_recheck_tx = self.live_auth_recheck_tx.clone();
                            tokio::spawn(async move {
                                handle_connection(stream, config, cancel, data_dir, cmd_channels, budget_slot, teacher_slot, risk_stores, learning_store, budget_store, audit_pool, scanner_reg, strategist_counters, live_auth_recheck_tx).await;
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
    strategist_counters: Option<Arc<crate::strategist_scheduler::CycleCounters>>,
    live_auth_recheck_tx: Option<tokio::sync::mpsc::Sender<()>>,
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
                let mut bytes = err.to_vec();
                bytes.push(b'\n');
                let _ = writer.write_all(&bytes).await;
                warn!(peer = %peer, "auth: invalid JSON / 認證：JSON 格式錯誤");
                return;
            }
        };
        if auth_req.get("method").and_then(|m| m.as_str()) != Some("__auth") {
            let err = br#"{"jsonrpc":"2.0","error":{"code":-32600,"message":"first message must be __auth"},"id":null}"#;
            let mut bytes = err.to_vec();
            bytes.push(b'\n');
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
            let mut bytes = err.to_vec();
            bytes.push(b'\n');
            let _ = writer.write_all(&bytes).await;
            warn!(peer = %peer, ts, now, "auth: token expired / 認證令牌已過期");
            return;
        }
        // HMAC-SHA256 constant-time verification / HMAC-SHA256 常數時間驗證
        if !verify_ipc_token(&secret, ts, token) {
            let err = br#"{"jsonrpc":"2.0","error":{"code":-32600,"message":"auth failed: invalid token"},"id":null}"#;
            let mut bytes = err.to_vec();
            bytes.push(b'\n');
            let _ = writer.write_all(&bytes).await;
            warn!(peer = %peer, "auth: HMAC verification failed / HMAC 驗證失敗");
            return;
        }
        // Auth success — send confirmation / 認證成功，發送確認
        let auth_id = auth_req
            .get("id")
            .cloned()
            .unwrap_or(serde_json::Value::Null);
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
                        let response = dispatch_request(&line, &config, &data_dir, &cmd_channels, &budget_slot, &teacher_slot, &risk_stores, &learning_store, &budget_store, &audit_pool, &scanner_registry, &strategist_counters, &live_auth_recheck_tx).await;
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
    strategist_counters: &Option<Arc<crate::strategist_scheduler::CycleCounters>>,
    live_auth_recheck_tx: &Option<tokio::sync::mpsc::Sender<()>>,
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
        let target_engine = req
            .params
            .get("engine")
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
        "get_build_capabilities" => handle_get_build_capabilities(id),
        "get_state" => handle_get_state(id, config, data_dir),
        "reload_config" => handle_reload_config(id, config),
        "get_paper_state" => {
            // Phase 4: optional `engine` param routes to per-mode snapshot.
            // Default "paper" for backward compatibility.
            // Phase 4：可選 `engine` 參數路由到每模式快照，默認 "paper" 向後兼容。
            let engine = req
                .params
                .get("engine")
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
            let engine = req
                .params
                .get("engine")
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
                return JsonRpcResponse::error(
                    id,
                    ERR_INVALID_REQUEST,
                    "missing required param: symbol",
                );
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
                PipelineCommand::CloseSymbol {
                    symbol,
                    hint_is_long,
                    hint_qty,
                },
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
        // P1-5 A2: operator-driven drawdown baseline reset — the in-memory
        // path + DB DELETE runs in event_consumer/mod.rs ResetDrawdownBaseline
        // interception. Python FastAPI route MUST front this with operator
        // auth + change_audit_log per Root Principle #8.
        // P1-5 A2：operator 手動重置 drawdown 基準。記憶體重置與 DB DELETE
        // 於 event_consumer/mod.rs 攔截執行；Python 路由須先驗 operator +
        // 寫 change_audit_log（根原則 #8）。
        "reset_drawdown_baseline" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_reset_drawdown_baseline(id, tx).await
        }
        // DYNAMIC-RISK-1: Per-engine Sharpe-aware sizer status + toggle.
        // DYNAMIC-RISK-1：按引擎動態風險調整器狀態與切換。
        "get_dynamic_risk_status" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_get_dynamic_risk_status(id, tx).await
        }
        "set_dynamic_risk_enabled" => {
            let tx = extract_engine_tx(&req.params, cmd_channels);
            handle_set_dynamic_risk_enabled(id, tx, &req.params).await
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
        // FIX-57: External AI usage recording (Python Layer2 → Rust sync)
        "record_ai_usage" => handle_record_ai_usage(id, &req.params, budget_slot).await,
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
            let engine = req
                .params
                .get("engine")
                .and_then(|v| v.as_str())
                .unwrap_or("paper");
            let store: Option<Arc<ConfigStore<RiskConfig>>> =
                risk_stores.as_ref().map(|s| Arc::clone(s.select(engine)));
            handle_get_config(id, &store, &format!("risk/{engine}"))
        }
        "get_learning_config" => handle_get_config(id, learning_store, "learning"),
        "get_budget_config" => handle_get_config(id, budget_store, "budget"),
        "patch_risk_config" => {
            let engine = req
                .params
                .get("engine")
                .and_then(|v| v.as_str())
                .unwrap_or("paper");
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
        // ── G3-11 STRATEGIST-CYCLE-OBSERVABILITY-1 (2026-04-25, MVP) ──
        // 取代 GUI footer engine.log tail-parse 的結構化拉取面。
        "get_strategist_cycle_metrics" => {
            handle_get_strategist_cycle_metrics(id, strategist_counters)
        }
        // ── PIPELINE-SLOT-1 Phase 3: Live auth watcher fast-path ──
        // PIPELINE-SLOT-1 Phase 3：Live 授權 watcher 快路徑喚醒
        "trigger_live_auth_recheck" => {
            handle_trigger_live_auth_recheck(id, live_auth_recheck_tx)
        }
        _ => JsonRpcResponse::error(
            id,
            ERR_METHOD_NOT_FOUND,
            format!("method not found: {method}"),
        ),
    }
}

// ---------------------------------------------------------------------------
// Small utility handlers kept in mod.rs (used directly by dispatch_request)
// 保留在 mod.rs 的小型工具 handler（被 dispatch_request 直接使用）
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
        None => {
            tracing::debug!(
                "ipc: no 'engine' param — routing to primary pipeline \
                 (add explicit engine param for deterministic routing) \
                 / ipc：無 'engine' 參數 — 路由到主管線（建議加入明確 engine 參數）"
            );
            channels.primary()
        }
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

/// PIPELINE-SLOT-1 Phase 3: fast-path wake-up to the Live auth watcher.
///
/// Python's `/api/v1/live/auth/renew` (and revoke) routes call this
/// method fire-and-forget after `_write_signed_live_authorization()` /
/// `_delete_live_authorization_file()` so the watcher reacts in <100ms
/// rather than waiting up to 5s for the next poll tick.
///
/// Response shape (JSON object):
///   * `{"accepted": true}`  — wake-up accepted (watcher will recheck now)
///   * `{"accepted": false, "reason": "coalesced"}` — pending trigger
///     already queued; the existing wake-up will perform the recheck
///   * `{"accepted": false, "reason": "watcher_closed"}` — watcher
///     dropped its receiver (engine shutting down, or failed spawn); the
///     next full restart will rebind
///   * `{"accepted": false, "reason": "watcher_disabled"}` — engine
///     started without a Live pipeline (paper/demo-only build)
///
/// Never returns a JSON-RPC error: this is advisory, not authoritative.
/// The watcher's next poll still converges regardless.
///
/// PIPELINE-SLOT-1 Phase 3：Live 授權 watcher 快路徑喚醒。
///
/// Python `/api/v1/live/auth/renew`（與 revoke）路由於
/// `_write_signed_live_authorization()` /
/// `_delete_live_authorization_file()` 後 fire-and-forget 呼叫此 method，
/// 讓 watcher <100ms 反應，不必等最多 5s 下個 poll。
///
/// 回應（JSON object）：
///   * `{"accepted": true}` — 喚醒已接受，watcher 立刻 recheck
///   * `{"accepted": false, "reason": "coalesced"}` — 已有排隊 trigger
///   * `{"accepted": false, "reason": "watcher_closed"}` — watcher 已 drop receiver
///   * `{"accepted": false, "reason": "watcher_disabled"}` — 引擎無 Live 管線
///
/// 絕不回 JSON-RPC error：此為 advisory、非權威；watcher 下次 poll 仍會收斂。
fn handle_trigger_live_auth_recheck(
    id: serde_json::Value,
    live_auth_recheck_tx: &Option<tokio::sync::mpsc::Sender<()>>,
) -> JsonRpcResponse {
    let Some(tx) = live_auth_recheck_tx else {
        // No watcher wired (paper/demo-only engine) — return structured
        // "disabled" rather than an error, so Python callers can log-and-ignore.
        // 無 watcher 接線（僅 paper/demo 引擎）— 回結構化 disabled 而非錯誤，
        // 讓 Python 呼叫端 log-and-ignore。
        return JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "watcher_disabled"
            }),
        );
    };
    match tx.try_send(()) {
        Ok(()) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": true
            }),
        ),
        Err(tokio::sync::mpsc::error::TrySendError::Full(_)) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "coalesced"
            }),
        ),
        Err(tokio::sync::mpsc::error::TrySendError::Closed(_)) => JsonRpcResponse::success(
            id,
            serde_json::json!({
                "accepted": false,
                "reason": "watcher_closed"
            }),
        ),
    }
}

/// EDGE-P3-1 Step 7b: report compile-time build-feature flags to Python probes.
/// Python's `engine_capabilities` endpoint needs the live flag value rather
/// than a static declaration because the Rust engine and Python server are
/// built separately — without this, a production engine compiled with ort
/// would still show `reload_edge_predictor=false` at the probe layer.
///
/// EDGE-P3-1 Step 7b：回報 build-feature 旗標給 Python probe。Rust 引擎與
/// Python 服務器分別 build，故 Python 必須用實時值而非靜態宣告；否則 ort
/// build 也會在 probe 層顯示 `reload_edge_predictor=false`。
fn handle_get_build_capabilities(id: serde_json::Value) -> JsonRpcResponse {
    let edge_predictor_ort = cfg!(feature = "edge_predictor_ort");
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "edge_predictor_ort": edge_predictor_ort,
            "reload_edge_predictor": edge_predictor_ort,
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
