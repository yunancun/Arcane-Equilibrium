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
use crate::config::ConfigManager;
use crate::tick_pipeline::PipelineSnapshot;
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

use crate::tick_pipeline::PaperSessionCommand;

/// Unix domain socket IPC server.
/// Unix 域套接字 IPC 服務器。
pub struct IpcServer {
    config: Arc<ConfigManager>,
    cancel: CancellationToken,
    /// Data directory for reading pipeline snapshot files (R06-A).
    /// 數據目錄，用於讀取管線快照文件。
    data_dir: Arc<PathBuf>,
    /// Paper session command sender — dispatches Pause/Resume/CloseAll/Reset to event consumer.
    /// 紙盤 session 命令發送端 — 派發 Pause/Resume/CloseAll/Reset 到事件消費者。
    paper_cmd_tx: Option<tokio::sync::mpsc::UnboundedSender<PaperSessionCommand>>,
    /// Phase 4 (4-15): Late-injected AI BudgetTracker slot.
    /// Phase 4 (4-15)：延後注入的 AI BudgetTracker 槽位。
    budget_tracker: BudgetTrackerSlot,
}

impl IpcServer {
    /// Create a new IPC server instance.
    /// 創建新的 IPC 服務器實例。
    pub fn new(
        config: Arc<ConfigManager>,
        cancel: CancellationToken,
        data_dir: impl Into<String>,
        paper_cmd_tx: Option<tokio::sync::mpsc::UnboundedSender<PaperSessionCommand>>,
    ) -> Self {
        Self {
            config,
            cancel,
            data_dir: Arc::new(PathBuf::from(data_dir.into())),
            paper_cmd_tx,
            budget_tracker: Arc::new(RwLock::new(None)),
        }
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
                            let cmd_tx = self.paper_cmd_tx.clone();
                            let budget_slot = Arc::clone(&self.budget_tracker);
                            tokio::spawn(async move {
                                handle_connection(stream, config, cancel, data_dir, cmd_tx, budget_slot).await;
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

/// Handle a single client connection.
/// 處理單個客戶端連接。
async fn handle_connection(
    stream: tokio::net::UnixStream,
    config: Arc<ConfigManager>,
    cancel: CancellationToken,
    data_dir: Arc<PathBuf>,
    paper_cmd_tx: Option<tokio::sync::mpsc::UnboundedSender<PaperSessionCommand>>,
    budget_slot: BudgetTrackerSlot,
) {
    let peer = format!("{:?}", stream.peer_addr());
    info!(peer = %peer, "client connected / 客戶端已連接");

    let (reader, mut writer) = stream.into_split();
    let mut lines = BufReader::new(reader).lines();

    loop {
        tokio::select! {
            _ = cancel.cancelled() => {
                debug!(peer = %peer, "connection cancelled / 連接已取消");
                break;
            }
            line_result = lines.next_line() => {
                match line_result {
                    Ok(Some(line)) => {
                        let response = dispatch_request(&line, &config, &data_dir, &paper_cmd_tx, &budget_slot).await;
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
async fn dispatch_request(
    line: &str,
    config: &Arc<ConfigManager>,
    data_dir: &Arc<PathBuf>,
    paper_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PaperSessionCommand>>,
    budget_slot: &BudgetTrackerSlot,
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

    match method {
        "ping" => handle_ping(id),
        "get_state" => handle_get_state(id, config),
        "reload_config" => handle_reload_config(id, config),
        "get_paper_state" => {
            handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.paper_state))
        }
        "get_latest_prices" => {
            handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.latest_prices))
        }
        "get_tick_stats" => handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.stats)),
        // ── Paper session control commands / 紙盤 session 控制命令 ──
        "pause_paper" => handle_paper_cmd(id, paper_cmd_tx, PaperSessionCommand::Pause, "paused"),
        "resume_paper" => {
            handle_paper_cmd(id, paper_cmd_tx, PaperSessionCommand::Resume, "resumed")
        }
        "close_all_positions" => handle_paper_cmd(
            id,
            paper_cmd_tx,
            PaperSessionCommand::CloseAll,
            "close_all_sent",
        ),
        "reset_paper_state" => {
            let balance = req
                .params
                .get("new_balance")
                .and_then(|v| v.as_f64())
                .unwrap_or(10_000.0);
            handle_paper_cmd(
                id,
                paper_cmd_tx,
                PaperSessionCommand::Reset {
                    new_balance: balance,
                },
                "reset_sent",
            )
        }
        // ── Phase 3b: Strategy parameter commands (Optuna → Rust) / 策略參數命令 ──
        "update_strategy_params" => {
            handle_strategy_param_cmd(id, paper_cmd_tx, &req.params, StrategyParamOp::Update).await
        }
        "get_strategy_params" => {
            handle_strategy_param_cmd(id, paper_cmd_tx, &req.params, StrategyParamOp::Get).await
        }
        "get_param_ranges" => {
            handle_strategy_param_cmd(id, paper_cmd_tx, &req.params, StrategyParamOp::Ranges).await
        }
        "update_risk_config" => handle_update_risk_config(id, paper_cmd_tx, &req.params).await,
        // RRC-1-E2: Strategy activate/pause / 策略啟停
        "set_strategy_active" => handle_set_strategy_active(id, paper_cmd_tx, &req.params).await,
        // Phase 4 (4-00): Dashboard skeleton status aggregation / 儀表板骨架狀態聚合
        "get_phase4_status" => handle_get_phase4_status(id),
        // Phase 4 (4-15): AI budget status / config / AI 預算狀態與配置
        "get_ai_budget_status" => handle_get_ai_budget_status(id, budget_slot).await,
        "update_ai_budget_config" => {
            handle_update_ai_budget_config(id, &req.params, budget_slot).await
        }
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

/// Handle paper session command — send to event consumer via channel.
/// 處理紙盤 session 命令 — 通過通道發送到事件消費者。
fn handle_paper_cmd(
    id: serde_json::Value,
    tx: &Option<tokio::sync::mpsc::UnboundedSender<PaperSessionCommand>>,
    cmd: PaperSessionCommand,
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

/// Get current engine state summary (stub).
/// 獲取當前引擎狀態摘要（存根）。
fn handle_get_state(id: serde_json::Value, config: &Arc<ConfigManager>) -> JsonRpcResponse {
    let cfg = config.get();
    let state = serde_json::json!({
        "status": "running",
        "system_mode": "demo_only",
        "trading_mode": cfg.trading_mode.to_string(),
        "max_open_positions": cfg.max_open_positions,
        "max_total_exposure_pct": cfg.max_total_exposure_pct,
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
    tx: &Option<tokio::sync::mpsc::UnboundedSender<PaperSessionCommand>>,
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
            PaperSessionCommand::UpdateStrategyParams {
                strategy_name,
                params_json,
                response_tx: resp_tx,
            }
        }
        StrategyParamOp::Get => PaperSessionCommand::GetStrategyParams {
            strategy_name,
            response_tx: resp_tx,
        },
        StrategyParamOp::Ranges => PaperSessionCommand::GetParamRanges {
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
    paper_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PaperSessionCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match paper_cmd_tx {
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

    let _ = tx.send(PaperSessionCommand::UpdateRiskConfig {
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

/// RRC-1-E2: Set strategy active/paused via IPC / 通過 IPC 設置策略啟停。
async fn handle_set_strategy_active(
    id: serde_json::Value,
    paper_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PaperSessionCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match paper_cmd_tx {
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
    let _ = tx.send(PaperSessionCommand::SetStrategyActive {
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

    /// Write a test snapshot file to a temp dir, return the dir path.
    /// 寫入測試快照文件到臨時目錄，返回目錄路徑。
    fn write_test_snapshot() -> (Arc<PathBuf>, tempfile::TempDir) {
        let dir = tempfile::tempdir().unwrap();
        let snapshot = PipelineSnapshot {
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
            trading_mode: crate::config::TradingMode::PaperOnly,
            h0_gate_stats: None,
            stop_config: None,
            guardian_config: None,
            risk_manager_config: None,
            consecutive_losses: HashMap::new(),
            session_halted: false,
            daily_loss_pct: 0.0,
            session_drawdown_pct: 0.0,
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["status"], "running");
        assert_eq!(result["system_mode"], "demo_only");
    }

    #[tokio::test]
    async fn test_dispatch_method_not_found() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": 3}"#;
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_METHOD_NOT_FOUND);
    }

    #[tokio::test]
    async fn test_dispatch_invalid_json() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = "not valid json";
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_missing_version() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"method": "ping", "params": {}, "id": 4}"#;
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_missing_method() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "params": {}, "id": 5}"#;
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_reload_config() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "reload_config", "params": {}, "id": 8}"#;
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
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
    fn setup_strategy_param_channel() -> tokio::sync::mpsc::UnboundedSender<PaperSessionCommand> {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PaperSessionCommand>();
        tokio::spawn(async move {
            use crate::strategies::{ma_crossover::MaCrossover, Strategy};
            let mut strategy: Box<dyn Strategy> = Box::new(MaCrossover::new());
            while let Some(cmd) = rx.recv().await {
                match cmd {
                    PaperSessionCommand::UpdateStrategyParams {
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
                    PaperSessionCommand::GetStrategyParams {
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
                    PaperSessionCommand::GetParamRanges {
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

    #[tokio::test]
    async fn test_get_param_ranges_via_ipc() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "get_param_ranges", "params": {"strategy_name": "ma_crossover"}, "id": 30}"#;
        let resp = dispatch_request(req, &config, &dd, &Some(tx), &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &Some(tx), &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &Some(tx), &empty_budget_slot()).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
    }

    #[tokio::test]
    async fn test_update_strategy_params_nonexistent() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "nonexistent_strategy", "params_json": "{}"}, "id": 33}"#;
        let resp = dispatch_request(req, &config, &dd, &Some(tx), &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &Some(tx), &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
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
        let resp = dispatch_request(req, &config, &dd, &None, &empty_budget_slot()).await;
        assert_eq!(resp.id, serde_json::json!(4002));
        assert!(resp.error.is_none());
        assert!(resp.result.is_some());
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
}
