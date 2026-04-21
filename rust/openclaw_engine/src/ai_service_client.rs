//! Rust-side IPC client for Python AIService (JSON-RPC over Unix socket).
//! Rust 側 IPC 客戶端，連接 Python AIService（Unix socket 上的 JSON-RPC）。
//!
//! MODULE_NOTE (EN): AiServiceClient connects to ai_service.sock (Python side)
//!   using newline-delimited JSON-RPC 2.0. Two-tier timeout: 100ms socket connect
//!   + per-method handler TTL (strategist=15s, guardian=5s). Fail-closed: connect
//!   failure → return None, never block the engine. Cross-platform: socket path
//!   from env var OPENCLAW_AI_SERVICE_SOCKET or default /tmp/openclaw/ai_service.sock.
//! MODULE_NOTE (中): AiServiceClient 連接 ai_service.sock（Python 側），使用換行分隔
//!   JSON-RPC 2.0。雙層超時：100ms socket 連接 + 每方法 handler TTL（strategist=15s,
//!   guardian=5s）。Fail-closed：連接失敗 → 返回 None，不阻塞引擎。跨平台：socket
//!   路徑來自環境變量或默認 /tmp/openclaw/ai_service.sock。

use serde_json::Value;
use std::path::PathBuf;
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::Duration;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::net::UnixStream;
use tracing::{debug, warn};

/// Default socket directory (cross-platform: env override available).
/// 默認 socket 目錄（跨平台：可透過環境變量覆寫）。
const DEFAULT_SOCKET_DIR: &str = "/tmp/openclaw";
const DEFAULT_SOCKET_NAME: &str = "ai_service.sock";

/// Per-method handler TTL map.
/// 每方法 handler 超時對照表。
fn method_ttl(method: &str) -> Duration {
    match method {
        "strategist_evaluate" => Duration::from_secs(15),
        "guardian_check" => Duration::from_secs(5),
        "analyst_evaluate" => Duration::from_secs(30),
        "scout_scan" => Duration::from_secs(10),
        "conductor_evaluate" => Duration::from_secs(10),
        _ => Duration::from_secs(10), // safe default / 安全默認值
    }
}

/// Resolve socket path from explicit inputs.
///
/// Pure function: precedence is (1) explicit `sock` override, (2) `data_dir`
/// + default socket name, (3) hard-coded `DEFAULT_SOCKET_DIR` +
/// `DEFAULT_SOCKET_NAME`. No env or filesystem I/O — callers supply the
/// strings they want resolved. Exists as a separate fn so unit tests can
/// assert the precedence matrix without racing on process-global env vars
/// (AI-SERVICE-CLIENT-ENV-RACE-1, 2026-04-21).
///
/// 從顯式輸入解析 socket 路徑。純函數：優先序 (1) 顯式 sock 覆寫 → (2)
/// data_dir + 預設 socket 名 → (3) 硬編碼 DEFAULT_SOCKET_DIR + DEFAULT_SOCKET_NAME。
/// 無 env 或檔案 I/O — 呼叫端自行提供要解析的字串。拆出獨立 fn 供單元測試
/// 驗證優先序矩陣，避免並行測試在 process-global env var 上競爭
/// （AI-SERVICE-CLIENT-ENV-RACE-1，2026-04-21）。
fn resolve_socket_path_from(sock: Option<&str>, data_dir: Option<&str>) -> PathBuf {
    if let Some(p) = sock {
        return PathBuf::from(p);
    }
    if let Some(d) = data_dir {
        return PathBuf::from(d).join(DEFAULT_SOCKET_NAME);
    }
    PathBuf::from(DEFAULT_SOCKET_DIR).join(DEFAULT_SOCKET_NAME)
}

/// Resolve socket path from env or default. Thin wrapper around
/// `resolve_socket_path_from` that reads the two override env vars.
/// 從環境變量或默認值解析 socket 路徑。此為 `resolve_socket_path_from` 的
/// 薄包裝，讀取兩個覆寫 env var。
fn resolve_socket_path() -> PathBuf {
    let sock = std::env::var("OPENCLAW_AI_SERVICE_SOCKET").ok();
    let data_dir = std::env::var("OPENCLAW_DATA_DIR").ok();
    resolve_socket_path_from(sock.as_deref(), data_dir.as_deref())
}

/// IPC client for Python AIService. Thread-safe, cloneable via Arc.
/// Python AIService 的 IPC 客戶端。線程安全，可透過 Arc 克隆。
pub struct AiServiceClient {
    /// Resolved socket path / 解析後的 socket 路徑
    socket_path: PathBuf,
    /// Socket connect timeout (100ms — connect only, not full request).
    /// Socket 連接超時（100ms — 僅連接，非完整請求）。
    connect_timeout: Duration,
    /// Monotonic request ID counter / 單調遞增請求 ID 計數器
    next_id: AtomicU64,
}

impl AiServiceClient {
    /// Create a new client with default socket path and 100ms connect timeout.
    /// 創建新客戶端，使用默認 socket 路徑和 100ms 連接超時。
    pub fn new() -> Self {
        Self {
            socket_path: resolve_socket_path(),
            connect_timeout: Duration::from_millis(100),
            next_id: AtomicU64::new(1),
        }
    }

    /// Create with explicit socket path (for tests).
    /// 使用顯式 socket 路徑創建（測試用）。
    #[cfg(test)]
    pub fn with_path(path: PathBuf) -> Self {
        Self {
            socket_path: path,
            connect_timeout: Duration::from_millis(100),
            next_id: AtomicU64::new(1),
        }
    }

    /// Send a JSON-RPC request and await the response. Returns None on any failure.
    /// Fail-closed: connect timeout / handler timeout / parse error → None + log.
    /// 發送 JSON-RPC 請求並等待回應。任何失敗返回 None。
    /// Fail-closed：連接超時 / handler 超時 / 解析錯誤 → None + 日誌。
    pub async fn request(&self, method: &str, params: Value) -> Option<Value> {
        let id = self.next_id.fetch_add(1, Ordering::Relaxed);
        let ttl = method_ttl(method);

        // Phase 1: Connect with 100ms timeout / 階段 1：100ms 連接超時
        let stream = match tokio::time::timeout(
            self.connect_timeout,
            UnixStream::connect(&self.socket_path),
        )
        .await
        {
            Ok(Ok(s)) => s,
            Ok(Err(e)) => {
                warn!(
                    method,
                    error = %e,
                    path = %self.socket_path.display(),
                    "AI service connect failed (fail-closed) / AI 服務連接失敗"
                );
                return None;
            }
            Err(_) => {
                warn!(
                    method,
                    path = %self.socket_path.display(),
                    "AI service connect timeout 100ms (fail-closed) / AI 服務連接超時"
                );
                return None;
            }
        };

        // Phase 2: Send request + await response within handler TTL
        // 階段 2：在 handler TTL 內發送請求並等待回應
        match tokio::time::timeout(ttl, self.do_request(stream, id, method, params)).await {
            Ok(Ok(val)) => {
                debug!(method, id, "AI service response ok / AI 服務回應成功");
                Some(val)
            }
            Ok(Err(e)) => {
                warn!(
                    method, id,
                    error = %e,
                    "AI service request error (fail-closed) / AI 服務請求錯誤"
                );
                None
            }
            Err(_) => {
                warn!(
                    method,
                    id,
                    ttl_secs = ttl.as_secs(),
                    "AI service handler timeout (fail-closed) / AI 服務 handler 超時"
                );
                None
            }
        }
    }

    /// Internal: send JSON-RPC request and read response on an established connection.
    /// 內部：在已建立的連接上發送 JSON-RPC 請求並讀取回應。
    async fn do_request(
        &self,
        stream: UnixStream,
        id: u64,
        method: &str,
        params: Value,
    ) -> Result<Value, Box<dyn std::error::Error + Send + Sync>> {
        let request = serde_json::json!({
            "jsonrpc": "2.0",
            "id": id,
            "method": method,
            "params": params,
        });

        let mut payload = serde_json::to_string(&request)?;
        payload.push('\n');

        let (reader_half, mut writer_half) = stream.into_split();
        writer_half.write_all(payload.as_bytes()).await?;
        writer_half.flush().await?;

        // Read one newline-delimited response line / 讀取一行換行分隔的回應
        let mut buf_reader = BufReader::new(reader_half);
        let mut line = String::new();
        let n = buf_reader.read_line(&mut line).await?;
        if n == 0 {
            return Err("AI service closed connection before response / 回應前連接關閉".into());
        }

        let response: Value = serde_json::from_str(line.trim())?;

        // Check for JSON-RPC error / 檢查 JSON-RPC 錯誤
        if let Some(err) = response.get("error") {
            let msg = err["message"].as_str().unwrap_or("unknown");
            return Err(format!("JSON-RPC error: {msg}").into());
        }

        // Return the result field / 返回 result 字段
        Ok(response.get("result").cloned().unwrap_or(Value::Null))
    }

    /// Get the resolved socket path (for diagnostics).
    /// 獲取解析後的 socket 路徑（用於診斷）。
    pub fn socket_path(&self) -> &std::path::Path {
        &self.socket_path
    }
}

impl Default for AiServiceClient {
    fn default() -> Self {
        Self::new()
    }
}

// ═══════════════════════════════════════════════════════════════════════════════
// Tests / 測試
// ═══════════════════════════════════════════════════════════════════════════════

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_method_ttl_known_methods() {
        assert_eq!(method_ttl("strategist_evaluate"), Duration::from_secs(15));
        assert_eq!(method_ttl("guardian_check"), Duration::from_secs(5));
        assert_eq!(method_ttl("analyst_evaluate"), Duration::from_secs(30));
    }

    #[test]
    fn test_method_ttl_unknown_defaults_10s() {
        assert_eq!(method_ttl("nonexistent"), Duration::from_secs(10));
    }

    // AI-SERVICE-CLIENT-ENV-RACE-1 (2026-04-21): these three tests used to
    // mutate process-global env vars (`OPENCLAW_AI_SERVICE_SOCKET` /
    // `OPENCLAW_DATA_DIR`) to probe `resolve_socket_path`. Under parallel
    // cargo-test execution (Mac dev env sets `OPENCLAW_DATA_DIR`) the setvar /
    // removevar pairs raced with other tests reading the same keys, producing
    // flakes (~1 / 1839 runs). Refactored `resolve_socket_path_from(sock,
    // data_dir)` as the pure precedence fn so tests inject inputs directly —
    // no env mutation, no race.
    //
    // AI-SERVICE-CLIENT-ENV-RACE-1（2026-04-21）：下列三個測試原以 set/remove
    // `OPENCLAW_AI_SERVICE_SOCKET` / `OPENCLAW_DATA_DIR` 探 `resolve_socket_path`
    // 優先序。並行 cargo test（Mac 本地有設 OPENCLAW_DATA_DIR）下與其他讀
    // 同 key 的測試競爭，出現偶發 flake（約 1/1839）。重構為 pure fn
    // `resolve_socket_path_from(sock, data_dir)` 直接注入輸入，不動 env，零 race。

    #[test]
    fn test_default_socket_path() {
        // No sock override, no data_dir → hard-coded default.
        // 無 sock 覆寫、無 data_dir → 使用硬編碼 default。
        let path = resolve_socket_path_from(None, None);
        assert_eq!(path, PathBuf::from("/tmp/openclaw/ai_service.sock"));
    }

    #[test]
    fn test_env_override_socket_path() {
        // Sock override wins over data_dir + default-name fallback.
        // sock 覆寫優先於 data_dir + 預設名 fallback。
        let path = resolve_socket_path_from(Some("/custom/path.sock"), None);
        assert_eq!(path, PathBuf::from("/custom/path.sock"));
    }

    #[test]
    fn test_data_dir_fallback() {
        // data_dir set (no sock override) → data_dir + default-name join.
        // 設 data_dir（無 sock 覆寫）→ data_dir + 預設名組合。
        let path = resolve_socket_path_from(None, Some("/custom/data"));
        assert_eq!(path, PathBuf::from("/custom/data/ai_service.sock"));
    }

    /// Sock override takes precedence even when data_dir is also set — the
    /// precedence contract encoded in `resolve_socket_path_from`'s if-chain.
    /// 同時給 sock + data_dir → sock 勝，驗證 `resolve_socket_path_from` 優先序。
    #[test]
    fn test_sock_override_beats_data_dir() {
        let path = resolve_socket_path_from(Some("/explicit.sock"), Some("/ignored/dir"));
        assert_eq!(path, PathBuf::from("/explicit.sock"));
    }

    #[tokio::test]
    async fn test_connect_to_missing_socket_returns_none() {
        let client = AiServiceClient::with_path(PathBuf::from("/tmp/nonexistent_test.sock"));
        let result = client
            .request("strategist_evaluate", serde_json::json!({}))
            .await;
        assert!(result.is_none(), "expected None for missing socket");
    }

    #[tokio::test]
    async fn test_request_id_increments() {
        let client = AiServiceClient::new();
        assert_eq!(client.next_id.load(Ordering::Relaxed), 1);
        // Request will fail (no socket) but ID should still increment
        let _ = client.request("test", serde_json::json!({})).await;
        assert_eq!(client.next_id.load(Ordering::Relaxed), 2);
    }

    #[tokio::test]
    async fn test_roundtrip_with_mock_server() {
        use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
        use tokio::net::UnixListener;

        let dir = std::env::temp_dir().join(format!("oc_test_ai_client_{}", std::process::id()));
        let _ = std::fs::create_dir_all(&dir);
        let sock_path = dir.join("test_ai.sock");
        let _ = std::fs::remove_file(&sock_path);

        // Spawn mock Python AI service / 啟動模擬 Python AI 服務
        let listener = UnixListener::bind(&sock_path).unwrap();
        let server_handle = tokio::spawn(async move {
            let (stream, _) = listener.accept().await.unwrap();
            let (reader, mut writer) = stream.into_split();
            let mut buf = BufReader::new(reader);
            let mut line = String::new();
            buf.read_line(&mut line).await.unwrap();

            let req: Value = serde_json::from_str(line.trim()).unwrap();
            let id = req["id"].as_u64().unwrap();

            let resp = serde_json::json!({
                "jsonrpc": "2.0",
                "id": id,
                "result": {"action": "hold", "confidence": 0.75}
            });
            let mut resp_str = serde_json::to_string(&resp).unwrap();
            resp_str.push('\n');
            writer.write_all(resp_str.as_bytes()).await.unwrap();
            writer.flush().await.unwrap();
        });

        // Give server time to bind / 等待服務器綁定
        tokio::time::sleep(Duration::from_millis(10)).await;

        let client = AiServiceClient::with_path(sock_path.clone());
        let result = client
            .request("strategist_evaluate", serde_json::json!({"symbol": "BTC"}))
            .await;

        assert!(result.is_some(), "expected Some from mock server");
        let val = result.unwrap();
        assert_eq!(val["action"].as_str(), Some("hold"));
        assert_eq!(val["confidence"].as_f64(), Some(0.75));

        server_handle.await.unwrap();

        // Cleanup / 清理
        let _ = std::fs::remove_file(&sock_path);
        let _ = std::fs::remove_dir(&dir);
    }
}
