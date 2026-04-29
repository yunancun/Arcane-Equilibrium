//! Per-connection IPC plumbing — HMAC-SHA256 auth handshake (G-3 / SEC-08)
//! followed by a newline-delimited JSON-RPC dispatch loop.
//! 每連線 IPC 管線 — HMAC-SHA256 認證握手（G-3 / SEC-08）後跑換行分隔的
//! JSON-RPC 分派迴圈。
//!
//! MODULE_NOTE (EN): When `OPENCLAW_IPC_SECRET` is set, the first message
//!   from a client must be a JSON-RPC `__auth` request carrying a `(ts,
//!   token)` pair where `token = hex(HMAC-SHA256(secret, str(ts)))` and
//!   `|now - ts| ≤ 30s`. Verification uses constant-time slice compare
//!   (`hmac::Mac::verify_slice`) to defeat timing attacks. Any failure path
//!   writes a single `-32600` error frame and drops the connection
//!   (fail-closed). After auth succeeds (or env-var is absent — dev/test
//!   mode), the loop reads one line at a time, hands it to
//!   `dispatch_request`, and writes the serialised response back. The
//!   cancellation token shuts the loop down cooperatively.
//! MODULE_NOTE (中)：設了 `OPENCLAW_IPC_SECRET` 時，客戶端第一條訊息必須
//!   是 JSON-RPC `__auth` 請求，攜帶 `(ts, token)`；其中
//!   `token = hex(HMAC-SHA256(secret, str(ts)))` 且 `|now - ts| ≤ 30s`。
//!   驗證使用 `hmac::Mac::verify_slice` 常數時間比對，防止時序攻擊。任何
//!   失敗路徑都寫一條 `-32600` 錯誤框並斷線（fail-closed）。認證成功後
//!   （或 env 缺失即 dev/test 模式），迴圈逐行讀取交給 `dispatch_request`，
//!   寫回序列化回應。取消 token 提供協作式關閉。
//!
//! Split out of `ipc_server/mod.rs` as part of G5-FUP-IPC-MOD-SPLIT (2026-04-26)
//! together with `dispatch.rs`. Dispatch logic is in `dispatch.rs`; this
//! file owns only the per-connection lifecycle.
//! 於 G5-FUP-IPC-MOD-SPLIT（2026-04-26）連同 `dispatch.rs` 從
//! `ipc_server/mod.rs` 拆出。Dispatch 邏輯在 `dispatch.rs`；本檔僅持有
//! 每連線生命週期。

use super::dispatch::dispatch_request;
use super::engine_routing::EngineCommandChannels;
use super::slots::{BudgetTrackerSlot, CostEdgeAdvisorSlot, HStateCacheSlot, TeacherLoopSlot};
use super::PerEngineRiskStores;
use crate::config::{BudgetConfig, ConfigManager, ConfigStore, LearningConfig};
use crate::h_state_cache::poller::InvalidationSender;
use crate::secret_env;
use std::path::PathBuf;
use std::sync::Arc;
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio_util::sync::CancellationToken;
use tracing::{debug, info, warn};

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

    if secret.is_empty() {
        return false;
    }
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
pub(super) async fn handle_connection(
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
    h_state_cache: HStateCacheSlot,
    h_state_invalidation_tx: Option<InvalidationSender>,
    // F6 PH5-WIRE-1 RELOAD (2026-04-26): manual-trigger sender for the
    // edge estimates reloader daemon. Read from the slot once at accept
    // time; None when daemon was not spawned (env=0 or no pipelines).
    // F6：edge 重載 daemon 手動 trigger sender。Accept 時自 slot 讀一次；
    // daemon 未 spawn 時為 None。
    edge_reload_sender: Option<tokio::sync::mpsc::Sender<()>>,
    // G3-09 Phase A (2026-04-27): cost_edge_advisor slot. Connection-level
    // Arc clone; advisor late-injected by main_boot_tasks. None until
    // spawn_cost_edge_advisor_if_enabled wires it (env=0 keeps it None).
    // G3-09 Phase A：cost_edge_advisor slot；advisor 由 main_boot_tasks
    // 在 env-gate 通過後 late-inject。
    cost_edge_advisor_slot: CostEdgeAdvisorSlot,
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
    if let Some(secret) = secret_env::var_or_file("OPENCLAW_IPC_SECRET") {
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
                        let response = dispatch_request(&line, &config, &data_dir, &cmd_channels, &budget_slot, &teacher_slot, &risk_stores, &learning_store, &budget_store, &audit_pool, &scanner_registry, &strategist_counters, &live_auth_recheck_tx, &h_state_cache, &h_state_invalidation_tx, &edge_reload_sender, &cost_edge_advisor_slot).await;
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

#[cfg(test)]
mod tests {
    use super::verify_ipc_token;

    #[test]
    fn verify_ipc_token_accepts_correct_hmac() {
        use hmac::{Hmac, Mac};
        use sha2::Sha256;
        type HmacSha256 = Hmac<Sha256>;
        let secret = "test_secret_value";
        let ts: i64 = 1700000000;
        let mut mac = HmacSha256::new_from_slice(secret.as_bytes()).unwrap();
        mac.update(ts.to_string().as_bytes());
        let bytes = mac.finalize().into_bytes();
        let token = hex::encode(bytes);
        assert!(verify_ipc_token(secret, ts, &token));
    }

    #[test]
    fn verify_ipc_token_rejects_wrong_token() {
        // Wrong hex token / 錯誤 hex token
        assert!(!verify_ipc_token("secret", 1700000000, "deadbeef"));
    }

    #[test]
    fn verify_ipc_token_rejects_invalid_hex() {
        // Non-hex token / 非 hex token
        assert!(!verify_ipc_token("secret", 1700000000, "not-hex-zz"));
    }

    #[test]
    fn verify_ipc_token_rejects_wrong_secret() {
        use hmac::{Hmac, Mac};
        use sha2::Sha256;
        type HmacSha256 = Hmac<Sha256>;
        let ts: i64 = 1700000000;
        let mut mac = HmacSha256::new_from_slice(b"correct_secret").unwrap();
        mac.update(ts.to_string().as_bytes());
        let token = hex::encode(mac.finalize().into_bytes());
        // Verify with a different secret / 用不同 secret 驗證
        assert!(!verify_ipc_token("wrong_secret", ts, &token));
    }

    #[test]
    fn verify_ipc_token_rejects_empty_secret_even_with_matching_token() {
        use hmac::{Hmac, Mac};
        use sha2::Sha256;
        type HmacSha256 = Hmac<Sha256>;
        let ts: i64 = 1700000000;
        let mut mac = HmacSha256::new_from_slice(b"").unwrap();
        mac.update(ts.to_string().as_bytes());
        let token = hex::encode(mac.finalize().into_bytes());

        assert!(!verify_ipc_token("", ts, &token));
    }
}
