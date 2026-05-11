//! R06-A: Snapshot file-read IPC tests.
//! R06-A：快照文件讀取 IPC 測試。

use super::super::*;
use super::{
    empty_budget_slot, empty_cost_edge_advisor_slot, empty_account_manager_slot, empty_h_state_cache_slot, empty_teacher_slot,
    make_test_config, make_test_data_dir, write_test_snapshot,
};

#[tokio::test]
async fn test_get_paper_state_no_file() {
    let config = make_test_config();
    let dd = make_test_data_dir(); // nonexistent dir
    let req = r#"{"jsonrpc": "2.0", "method": "get_paper_state", "params": {}, "id": 20}"#;
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
    assert!(resp.error.is_none(), "error: {:?}", resp.error);
    let result = resp.result.unwrap();
    assert_eq!(result["total_ticks"], 5000);
    assert_eq!(result["total_fills"], 3);
    assert_eq!(result["total_stops"], 1);
}
