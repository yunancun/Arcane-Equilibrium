//! Phase 4 (4-00) Dashboard skeleton tests.
//! Phase 4 (4-00) 儀表板骨架測試。

use super::super::*;
use super::{empty_budget_slot, empty_teacher_slot, make_test_config, make_test_data_dir};

/// Initial Phase 4 status — all four modules should report "grey".
/// 初始 Phase 4 狀態 — 四個模組應全部回報 "grey"。
#[tokio::test]
async fn test_get_phase4_status_returns_grey_initial() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4000}"#;
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
    )
    .await;
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
    let req = r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4001}"#;
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
    )
    .await;
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
    let req = r#"{"jsonrpc": "2.0", "method": "get_phase4_status", "params": {}, "id": 4002}"#;
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
    )
    .await;
    assert_eq!(resp.id, serde_json::json!(4002));
    assert!(resp.error.is_none());
    assert!(resp.result.is_some());
}
