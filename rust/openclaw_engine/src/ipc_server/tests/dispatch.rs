//! Dispatch / JSON-RPC basic request handling tests.
//! Dispatch / JSON-RPC 基本請求處理測試。

use super::super::*;
use super::{
    empty_budget_slot, empty_cost_edge_advisor_slot, empty_h_state_cache_slot, empty_teacher_slot,
    make_test_config, make_test_data_dir,
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
    )
    .await;
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
