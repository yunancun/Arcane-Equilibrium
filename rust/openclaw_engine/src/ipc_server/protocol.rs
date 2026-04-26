//! JSON-RPC 2.0 wire types + standard error codes used across the IPC server.
//! IPC 伺服器各處共用的 JSON-RPC 2.0 線上型別 + 標準錯誤碼。
//!
//! MODULE_NOTE (EN): The IPC server speaks newline-delimited JSON-RPC 2.0
//!   over a Unix domain socket. This file owns the small set of `Request` /
//!   `Response` / `Error` structs that every handler returns and the standard
//!   error code constants the dispatcher references when it has to short-
//!   circuit before a domain handler runs (parse error / missing method /
//!   internal serialisation failure).
//! MODULE_NOTE (中)：IPC 伺服器以 Unix 域套接字承載換行分隔的 JSON-RPC 2.0。
//!   本檔擁有所有 handler 共用的精簡 `Request` / `Response` / `Error` 結構，
//!   以及 dispatcher 在跑到 domain handler 前需要短路時引用的標準錯誤碼
//!   常量（parse 錯誤 / 找不到 method / 內部序列化失敗）。
//!
//! Split out of `ipc_server/mod.rs` as part of G5-FUP-IPC-MOD-SPLIT (2026-04-26).
//! 於 G5-FUP-IPC-MOD-SPLIT（2026-04-26）從 `ipc_server/mod.rs` 拆出。

use serde::{Deserialize, Serialize};

// ---------------------------------------------------------------------------
// JSON-RPC error codes / JSON-RPC 錯誤碼
// ---------------------------------------------------------------------------

/// Invalid request / 無效請求
pub(crate) const ERR_INVALID_REQUEST: i64 = -32600;
/// Method not found / 方法未找到
pub(crate) const ERR_METHOD_NOT_FOUND: i64 = -32601;
/// Internal error / 內部錯誤
pub(crate) const ERR_INTERNAL: i64 = -32603;

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
    pub(crate) fn success(id: serde_json::Value, result: serde_json::Value) -> Self {
        Self {
            jsonrpc: "2.0",
            result: Some(result),
            error: None,
            id,
        }
    }

    /// Create an error response / 創建錯誤回應
    pub(crate) fn error(id: serde_json::Value, code: i64, message: impl Into<String>) -> Self {
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
