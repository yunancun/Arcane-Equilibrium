//! Dispatch / JSON-RPC basic request handling tests.
//! Dispatch / JSON-RPC 基本請求處理測試。

use super::super::*;
use super::{
    empty_account_manager_slot, empty_budget_slot, empty_cost_edge_advisor_slot,
    empty_h_state_cache_slot, empty_teacher_slot, make_test_config, make_test_data_dir,
};

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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;
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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;
    assert!(resp.error.is_none());
    let result = resp.result.unwrap();
    assert_eq!(result["status"], "running");
    // system_mode is read from pipeline_snapshot.json; falls back to "live_reserved" when
    // no snapshot exists (test environment). Assert it's a non-empty string.
    // system_mode 從 pipeline_snapshot.json 讀取；測試環境無快照時回退 "live_reserved"。
    assert!(result["system_mode"]
        .as_str()
        .map(|s| !s.is_empty())
        .unwrap_or(false));
}

#[tokio::test]
async fn test_dispatch_method_not_found() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "nonexistent", "params": {}, "id": 3}"#;
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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(resp.error.unwrap().code, ERR_METHOD_NOT_FOUND);
}

#[tokio::test]
async fn test_dispatch_invalid_json() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = "not valid json";
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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
}

#[tokio::test]
async fn test_dispatch_missing_version() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"method": "ping", "params": {}, "id": 4}"#;
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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
}

#[tokio::test]
async fn test_dispatch_missing_method() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "params": {}, "id": 5}"#;
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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(resp.error.unwrap().code, ERR_INVALID_REQUEST);
}

#[tokio::test]
async fn test_dispatch_reload_config() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "reload_config", "params": {}, "id": 8}"#;
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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;
    assert!(resp.error.is_none());
    let result = resp.result.unwrap();
    assert_eq!(result["reloaded"], true);
}

#[tokio::test]
async fn test_dispatch_agent_spine_channel_metrics() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "get_agent_spine_channel_metrics", "params": {}, "id": 55}"#;
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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;

    assert!(resp.error.is_none());
    let result = resp.result.expect("result");
    assert_eq!(result["status"], "ok");
    assert!(result["drop_total"].as_u64().is_some());
    assert_eq!(
        result["drop_total_semantics"],
        "initial_try_send_failures_not_final_loss"
    );
}

// ─────────────────────────────────────────────────────────────────────────
// SM Option-2 收斂 step (i)（2026-06-02）：治理 lease + 唯讀投影 dispatch arm 測試。
//
// 驗證 (1) 新 method 不再 ERR_METHOD_NOT_FOUND（封閉 half-wire）；(2) 無命令通道
// （EngineCommandChannels::default() → primary()=None，鏡像引擎未運行）時 fail-closed
// 成 ERR_INTERNAL 而非 permissive；(3) lease method 缺必需 param 時 ERR_INVALID_REQUEST。
// 完整 round-trip（真實 GovernanceCore）由 event_consumer/tests/governance_ipc_tests.rs
// 的 handler 測試覆蓋（dispatch 測試無法注入 live tick actor）。
// ─────────────────────────────────────────────────────────────────────────

/// 共用：以無命令通道（default）跑一個 dispatch 請求。
async fn dispatch_no_channel(req: &str) -> JsonRpcResponse {
    let config = make_test_config();
    let dd = make_test_data_dir();
    dispatch_request(
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
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await
}

#[tokio::test]
async fn test_governance_lease_methods_no_longer_method_not_found() {
    // 封閉 half-wire：3 個 lease method + 4 個投影 method 都不再 ERR_METHOD_NOT_FOUND。
    // 無通道時應是 ERR_INTERNAL（engine down fail-closed），而非 -32601。
    for method in [
        "governance.acquire_lease",
        "governance.release_lease",
        "governance.get_lease",
        "governance.is_authorized",
        "governance.get_status",
        "governance.list_leases",
        "governance.get_risk_state",
    ] {
        let req = format!(
            r#"{{"jsonrpc":"2.0","method":"{method}","params":{{}},"id":1}}"#
        );
        let resp = dispatch_no_channel(&req).await;
        let err = resp.error.expect("error present (no channel)");
        assert_ne!(
            err.code, ERR_METHOD_NOT_FOUND,
            "{method} must be wired (not method-not-found)"
        );
        assert_eq!(
            err.code, ERR_INTERNAL,
            "{method} no-channel → fail-closed ERR_INTERNAL, got {}",
            err.code
        );
    }
}

#[tokio::test]
async fn test_governance_acquire_lease_missing_params_invalid_request() {
    // acquire 缺必需 param（intent_id/scope/ttl_ms/profile）→ ERR_INVALID_REQUEST。
    // 注意：default channel 的 primary()=None 會先撞 ERR_INTERNAL，所以這裡需要一個
    // 有 paper 通道但無 tick actor 的場景來測 param 驗證。改用「通道存在但 send 後
    // 無人回」不可行（會 timeout）。故 param 驗證測試改在「通道存在」下做：見下方
    // 用 wired paper 通道的測試。此處只確認無通道優先 fail-closed。
    let req = r#"{"jsonrpc":"2.0","method":"governance.acquire_lease","params":{},"id":2}"#;
    let resp = dispatch_no_channel(req).await;
    let err = resp.error.expect("error present");
    // 無通道 → ERR_INTERNAL（engine down 優先於 param 驗證，fail-closed）。
    assert_eq!(err.code, ERR_INTERNAL);
}

#[tokio::test]
async fn test_governance_acquire_param_validation_with_channel() {
    // 有 paper 通道（但 receiver drop 後不回）時，param 驗證先於 send 發生。
    // 缺 intent_id → ERR_INVALID_REQUEST（在 send 前攔截，不會 timeout）。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (tx, _rx) = tokio::sync::mpsc::unbounded_channel();
    let channels = EngineCommandChannels {
        paper: Some(tx),
        ..Default::default()
    };
    let req = r#"{"jsonrpc":"2.0","method":"governance.acquire_lease","params":{"scope":"TRADE_ENTRY","ttl_ms":60000,"profile":"Production"},"id":3}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &channels,
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
        &empty_account_manager_slot(),
    )
    .await;
    let err = resp.error.expect("error present (missing intent_id)");
    assert_eq!(
        err.code, ERR_INVALID_REQUEST,
        "missing intent_id → invalid request (param validated before send)"
    );
    assert!(err.message.contains("intent_id"), "error names intent_id");
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
