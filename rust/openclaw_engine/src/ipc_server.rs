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
use serde::{Deserialize, Serialize};
use std::path::Path;
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

/// Unix domain socket IPC server.
/// Unix 域套接字 IPC 服務器。
pub struct IpcServer {
    config: Arc<ConfigManager>,
    cancel: CancellationToken,
}

impl IpcServer {
    /// Create a new IPC server instance.
    /// 創建新的 IPC 服務器實例。
    pub fn new(config: Arc<ConfigManager>, cancel: CancellationToken) -> Self {
        Self { config, cancel }
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
                            tokio::spawn(async move {
                                handle_connection(stream, config, cancel).await;
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
                        let response = dispatch_request(&line, &config);
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
fn dispatch_request(line: &str, config: &Arc<ConfigManager>) -> JsonRpcResponse {
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

    fn make_test_config() -> Arc<ConfigManager> {
        Arc::new(ConfigManager::load(Some("/tmp/nonexistent_openclaw_ipc_test.toml")).unwrap())
    }

    #[test]
    fn test_dispatch_ping() {
        let config = make_test_config();
        let req = r#"{"jsonrpc": "2.0", "method": "ping", "params": {}, "id": 1}"#;
        let resp = dispatch_request(req, &config);
        assert!(resp.error.is_none());
        assert_eq!(resp.result.unwrap(), serde_json::Value::String("pong".into()));
        assert_eq!(resp.id, serde_json::json!(1));
    }

    #[test]
    fn test_dispatch_get_state() {
        let config = make_test_config();
        let req = r#"{"jsonrpc": "2.0", "method": "get_state", "params": {}, "id": 2}"#;
        let resp = dispatch_request(req, &config);
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["status"], "running");
        assert_eq!(result["system_mode"], "demo_only");
    }

    #[test]
    fn test_dispatch_method_not_found() {
        let config = make_test_config();
        let req = r#"{"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": 3}"#;
        let resp = dispatch_request(req, &config);
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_METHOD_NOT_FOUND);
    }

    #[test]
    fn test_dispatch_invalid_json() {
        let config = make_test_config();
        let req = "not valid json";
        let resp = dispatch_request(req, &config);
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[test]
    fn test_dispatch_missing_version() {
        let config = make_test_config();
        let req = r#"{"method": "ping", "params": {}, "id": 4}"#;
        let resp = dispatch_request(req, &config);
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[test]
    fn test_dispatch_missing_method() {
        let config = make_test_config();
        let req = r#"{"jsonrpc": "2.0", "params": {}, "id": 5}"#;
        let resp = dispatch_request(req, &config);
        assert!(resp.error.is_some());
        assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
    }

    #[test]
    fn test_dispatch_evaluate_strategy_stub() {
        let config = make_test_config();
        let req = r#"{"jsonrpc": "2.0", "method": "evaluate_strategy", "params": {"symbol": "BTCUSDT"}, "id": 6}"#;
        let resp = dispatch_request(req, &config);
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["status"], "stub");
        assert_eq!(result["symbol"], "BTCUSDT");
    }

    #[test]
    fn test_dispatch_get_risk_check_stub() {
        let config = make_test_config();
        let req = r#"{"jsonrpc": "2.0", "method": "get_risk_check", "params": {"symbol": "ETHUSDT"}, "id": 7}"#;
        let resp = dispatch_request(req, &config);
        assert!(resp.error.is_none());
        let result = resp.result.unwrap();
        assert_eq!(result["passed"], true);
    }

    #[test]
    fn test_dispatch_reload_config() {
        let config = make_test_config();
        let req = r#"{"jsonrpc": "2.0", "method": "reload_config", "params": {}, "id": 8}"#;
        let resp = dispatch_request(req, &config);
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
        // error should be absent / error 應該不存在
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
}
