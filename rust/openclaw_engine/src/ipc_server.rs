//! Unix domain socket JSON-RPC 2.0 server for Rust↔Python IPC (R01-1).
//! Unix 域套接字 JSON-RPC 2.0 服務器，用於 Rust↔Python IPC。
//!
//! MODULE_NOTE (EN): Listens on a Unix socket, handles JSON-RPC 2.0 requests
//!   with newline-delimited messages. Each connection spawns a tokio task.
//!   Supports: ping, get_state, reload_config, evaluate_strategy, get_risk_check.
//! MODULE_NOTE (中): 監聽 Unix 套接字，處理 JSON-RPC 2.0 請求（換行分隔消息）。
//!   每個連接生成一個 tokio 任務。支援：ping、get_state、reload_config、
//!   evaluate_strategy、get_risk_check。

use crate::config::ConfigManager;
use crate::tick_pipeline::PipelineSnapshot;
use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixListener;
use tokio_util::sync::CancellationToken;
use tracing::{debug, error, info, warn};

// ---------------------------------------------------------------------------
// AI Request TTL constants (seconds) / AI 請求 TTL 常量（秒）
// ---------------------------------------------------------------------------

/// Strategist AI request timeout / 策略師 AI 請求超時
pub const TTL_STRATEGIST_S: u64 = 15;
/// Analyst AI request timeout / 分析師 AI 請求超時
pub const TTL_ANALYST_S: u64 = 30;
/// Conductor AI request timeout / 指揮者 AI 請求超時
pub const TTL_CONDUCTOR_S: u64 = 10;

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
        Self { config, cancel, data_dir: Arc::new(PathBuf::from(data_dir.into())), paper_cmd_tx }
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

        info!(path = socket_path, "IPC server listening / IPC 服務器已啟動");

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
                            tokio::spawn(async move {
                                handle_connection(stream, config, cancel, data_dir, cmd_tx).await;
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
                        let response = dispatch_request(&line, &config, &data_dir, &paper_cmd_tx).await;
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
        "evaluate_strategy" => handle_evaluate_strategy(id, &req.params),
        "get_risk_check" => handle_get_risk_check(id, &req.params),
        "get_paper_state" => handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.paper_state)),
        "get_latest_prices" => handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.latest_prices)),
        "get_tick_stats" => handle_snapshot_field(id, data_dir, |s| serde_json::to_value(&s.stats)),
        // ── Paper session control commands / 紙盤 session 控制命令 ──
        "pause_paper" => handle_paper_cmd(id, paper_cmd_tx, PaperSessionCommand::Pause, "paused"),
        "resume_paper" => handle_paper_cmd(id, paper_cmd_tx, PaperSessionCommand::Resume, "resumed"),
        "close_all_positions" => handle_paper_cmd(id, paper_cmd_tx, PaperSessionCommand::CloseAll, "close_all_sent"),
        "reset_paper_state" => {
            let balance = req.params.get("new_balance")
                .and_then(|v| v.as_f64())
                .unwrap_or(10_000.0);
            handle_paper_cmd(id, paper_cmd_tx, PaperSessionCommand::Reset { new_balance: balance }, "reset_sent")
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
        "max_open_positions": cfg.max_open_positions,
        "max_total_exposure_pct": cfg.max_total_exposure_pct,
        "ws_url": cfg.ws_url,
        "config_path": config.file_path().display().to_string(),
    });
    JsonRpcResponse::success(id, state)
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

/// Evaluate strategy placeholder (stub — returns TTL info).
/// 策略評估佔位符（存根 — 返回 TTL 資訊）。
fn handle_evaluate_strategy(
    id: serde_json::Value,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let symbol = params
        .get("symbol")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown");
    let response = serde_json::json!({
        "status": "stub",
        "symbol": symbol,
        "message": "strategy evaluation not yet implemented",
        "ttl_strategist_s": TTL_STRATEGIST_S,
        "ttl_analyst_s": TTL_ANALYST_S,
        "ttl_conductor_s": TTL_CONDUCTOR_S,
    });
    JsonRpcResponse::success(id, response)
}

/// H0 risk gate check placeholder (stub).
/// H0 風控門控檢查佔位符（存根）。
fn handle_get_risk_check(id: serde_json::Value, params: &serde_json::Value) -> JsonRpcResponse {
    let symbol = params
        .get("symbol")
        .and_then(|v| v.as_str())
        .unwrap_or("unknown");
    let response = serde_json::json!({
        "status": "stub",
        "symbol": symbol,
        "passed": true,
        "message": "risk check not yet implemented — default pass in demo mode",
    });
    JsonRpcResponse::success(id, response)
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
        None => return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured"),
    };

    let strategy_name = match params.get("strategy_name").and_then(|v| v.as_str()) {
        Some(s) => s.to_string(),
        None => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing strategy_name parameter"),
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
                        _ => return JsonRpcResponse::error(id, ERR_INVALID_REQUEST, "missing params_json parameter"),
                    }
                }
            };
            PaperSessionCommand::UpdateStrategyParams { strategy_name, params_json, response_tx: resp_tx }
        }
        StrategyParamOp::Get => {
            PaperSessionCommand::GetStrategyParams { strategy_name, response_tx: resp_tx }
        }
        StrategyParamOp::Ranges => {
            PaperSessionCommand::GetParamRanges { strategy_name, response_tx: resp_tx }
        }
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

/// Read pipeline_snapshot.json and extract a field (R06-A helper — DRY for 3 handlers).
/// 讀取 pipeline_snapshot.json 並提取欄位（R06-A 輔助函數 — 三個 handler 共用）。
fn handle_snapshot_field<F>(
    id: serde_json::Value,
    data_dir: &Path,
    extract: F,
) -> JsonRpcResponse
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
            latest_prices: HashMap::from([
                ("BTCUSDT".into(), 66000.0),
                ("ETHUSDT".into(), 3200.0),
            ]),
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
        };
        let json = serde_json::to_string_pretty(&snapshot).unwrap();
        std::fs::write(dir.path().join("pipeline_snapshot.json"), &json).unwrap();
        (Arc::new(dir.path().to_path_buf()), dir)
    }

    #[tokio::test]
    async fn test_dispatch_ping() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
        assert!(resp.error.is_none());
        assert_eq!(resp.result.unwrap(), serde_json::Value::String("pong".into()));
        assert_eq!(resp.id, serde_json::json!(1));
    }

    #[tokio::test]
    async fn test_dispatch_get_state() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "get_state", "params": {}, "id": 2}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
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
        let resp = dispatch_request(req, &config, &dd, &None).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_METHOD_NOT_FOUND);
    }

    #[tokio::test]
    async fn test_dispatch_invalid_json() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = "not valid json";
        let resp = dispatch_request(req, &config, &dd, &None).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_missing_version() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"method": "ping", "params": {}, "id": 4}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_missing_method() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "params": {}, "id": 5}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[tokio::test]
    async fn test_dispatch_evaluate_strategy_stub() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "evaluate_strategy", "params": {"symbol": "BTCUSDT"}, "id": 6}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["status"], "stub");
        assert_eq!(result["symbol"], "BTCUSDT");
    }

    #[tokio::test]
    async fn test_dispatch_get_risk_check_stub() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "get_risk_check", "params": {"symbol": "ETHUSDT"}, "id": 7}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["passed"], true);
    }

    #[tokio::test]
    async fn test_dispatch_reload_config() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let req = r#"{"jsonrpc": "2.0", "method": "reload_config", "params": {}, "id": 8}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
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

    #[test]
    fn test_ttl_constants() {
        assert_eq!(TTL_STRATEGIST_S, 15);
        assert_eq!(TTL_ANALYST_S, 30);
        assert_eq!(TTL_CONDUCTOR_S, 10);
    }

    // ───────────────────────────────────────────────────────────────────────
    // R06-A: Snapshot file-read IPC tests / 快照文件讀取 IPC 測試
    // ───────────────────────────────────────────────────────────────────────

    #[tokio::test]
    async fn test_get_paper_state_no_file() {
        let config = make_test_config();
        let dd = make_test_data_dir(); // nonexistent dir
        let req = r#"{"jsonrpc": "2.0", "method": "get_paper_state", "params": {}, "id": 20}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
        assert!(resp.error.is_some(), "should error when snapshot file missing");
    }

    #[tokio::test]
    async fn test_get_paper_state_with_snapshot() {
        let config = make_test_config();
        let (dd, _dir) = write_test_snapshot();
        let req = r#"{"jsonrpc": "2.0", "method": "get_paper_state", "params": {}, "id": 21}"#;
        let resp = dispatch_request(req, &config, &dd, &None).await;
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
        let resp = dispatch_request(req, &config, &dd, &None).await;
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
        let resp = dispatch_request(req, &config, &dd, &None).await;
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
            use crate::strategies::{Strategy, ma_crossover::MaCrossover};
            let mut strategy: Box<dyn Strategy> = Box::new(MaCrossover::new());
            while let Some(cmd) = rx.recv().await {
                match cmd {
                    PaperSessionCommand::UpdateStrategyParams { strategy_name, params_json, response_tx } => {
                        let result = if strategy.name().eq_ignore_ascii_case(&strategy_name) {
                            strategy.update_params_json(&params_json).map(|()| format!("params updated for {}", strategy_name))
                        } else {
                            Err(format!("strategy not found: {strategy_name}"))
                        };
                        let _ = response_tx.send(result);
                    }
                    PaperSessionCommand::GetStrategyParams { strategy_name, response_tx } => {
                        let result = if strategy.name().eq_ignore_ascii_case(&strategy_name) {
                            Ok(strategy.get_params_json())
                        } else {
                            Err(format!("strategy not found: {strategy_name}"))
                        };
                        let _ = response_tx.send(result);
                    }
                    PaperSessionCommand::GetParamRanges { strategy_name, response_tx } => {
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
        let resp = dispatch_request(req, &config, &dd, &Some(tx)).await;
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
        let resp = dispatch_request(req, &config, &dd, &Some(tx)).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
        let result = resp.result.unwrap();
        let params_str = result["result"].as_str().unwrap();
        let params: serde_json::Value = serde_json::from_str(params_str).unwrap();
        assert!(params.get("cooldown_ms").is_some(), "should contain cooldown_ms");
    }

    #[tokio::test]
    async fn test_update_strategy_params_via_ipc() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "ma_crossover", "params_json": "{\"cooldown_ms\":600000,\"adx_threshold\":30.0,\"default_qty\":0.02,\"regime_filter_enabled\":true,\"higher_tf_alpha\":0.08}"}, "id": 32}"#;
        let resp = dispatch_request(req, &config, &dd, &Some(tx)).await;
        assert!(resp.error.is_none(), "error: {:?}", resp.error);
    }

    #[tokio::test]
    async fn test_update_strategy_params_nonexistent() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "nonexistent_strategy", "params_json": "{}"}, "id": 33}"#;
        let resp = dispatch_request(req, &config, &dd, &Some(tx)).await;
        assert!(resp.error.is_some(), "should error for nonexistent strategy");
    }

    #[tokio::test]
    async fn test_update_strategy_params_missing_params() {
        let config = make_test_config();
        let dd = make_test_data_dir();
        let tx = setup_strategy_param_channel();
        let req = r#"{"jsonrpc": "2.0", "method": "update_strategy_params", "params": {"strategy_name": "ma_crossover"}, "id": 34}"#;
        let resp = dispatch_request(req, &config, &dd, &Some(tx)).await;
        assert!(resp.error.is_some(), "should error when params_json missing");
    }
}
