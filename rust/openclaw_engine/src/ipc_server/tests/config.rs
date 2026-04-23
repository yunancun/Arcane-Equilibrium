//! ARCH-RC1 1C-2-C / LIVE-P2-1: unified Config IPC endpoint tests.
//! ARCH-RC1 1C-2-C / LIVE-P2-1：統一 Config IPC 端點測試。

use super::super::*;
use super::{empty_budget_slot, empty_teacher_slot, make_test_config, make_test_data_dir};

/// Build test stores: all three risk engines + learning + budget.
/// 構建測試 stores：三個風控引擎 + learning + budget。
fn rc1_stores() -> (
    Option<PerEngineRiskStores>,
    Option<Arc<ConfigStore<LearningConfig>>>,
    Option<Arc<ConfigStore<BudgetConfig>>>,
) {
    let rs = PerEngineRiskStores {
        paper: Arc::new(ConfigStore::new(RiskConfig::default())),
        demo: Arc::new(ConfigStore::new(RiskConfig::default())),
        live: Arc::new(ConfigStore::new(RiskConfig::default())),
    };
    (
        Some(rs),
        Some(Arc::new(ConfigStore::new(LearningConfig::default()))),
        Some(Arc::new(ConfigStore::new(BudgetConfig::default()))),
    )
}

#[tokio::test]
async fn test_rc1_get_risk_config_returns_snapshot_and_version() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let req = r#"{"jsonrpc": "2.0", "method": "get_risk_config", "params": {}, "id": 9001}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["version"], 0);
    assert!(r["config"]["limits"].is_object(), "config payload missing");
}

#[tokio::test]
async fn test_rc1_patch_risk_config_bumps_version_and_updates() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Patch a single nested field via deep merge.
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator","patch":{"limits":{"leverage_max":7.0}}},"id":9002}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["ok"], true);
    assert_eq!(r["version"], 1);
    assert_eq!(r["source"], "operator");
    // Verify paper store mutated (no engine param → default paper).
    // 確認 paper store 已更新（無 engine 參數 → 默認 paper）。
    let snap = rs.as_ref().unwrap().paper.load();
    assert!((snap.limits.leverage_max - 7.0).abs() < f64::EPSILON);
}

#[tokio::test]
async fn test_rc1_patch_risk_config_validation_failure_rolls_back() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let original_lev = rs.as_ref().unwrap().paper.load().limits.leverage_max;
    // Negative leverage is invalid.
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"patch":{"limits":{"leverage_max":-1.0}}},"id":9003}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_some(), "expected validation error");
    // Paper store untouched (rollback).
    // paper store 未改動（回滾）。
    assert_eq!(rs.as_ref().unwrap().paper.version(), 0);
    let snap = rs.as_ref().unwrap().paper.load();
    assert!((snap.limits.leverage_max - original_lev).abs() < f64::EPSILON);
}

#[tokio::test]
async fn test_rc1_patch_missing_patch_field_errors() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator"},"id":9004}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_some());
    assert_eq!(rs.as_ref().unwrap().paper.version(), 0);
}

#[tokio::test]
async fn test_rc1_patch_learning_and_budget_configs_round_trip() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Patch learning + then read back via get_learning_config.
    let patch_req = r#"{"jsonrpc":"2.0","method":"patch_learning_config","params":{"patch":{"news_pipeline_enabled":true}},"id":9005}"#;
    let resp = dispatch_request(
        patch_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "patch_learning_config: {resp:?}");
    let get_req = r#"{"jsonrpc":"2.0","method":"get_learning_config","params":{},"id":9006}"#;
    let resp = dispatch_request(
        get_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none());
    let r = resp.result.unwrap();
    assert_eq!(r["version"], 1);
    // Patch budget too — exercises the third branch.
    let bud_req = r#"{"jsonrpc":"2.0","method":"patch_budget_config","params":{"source":"agent","patch":{"daily_usd_max":50.0}},"id":9007}"#;
    let resp = dispatch_request(
        bud_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "patch_budget_config: {resp:?}");
    assert_eq!(resp.result.unwrap()["source"], "agent");
}

#[tokio::test]
async fn test_rc1_get_config_without_store_errors() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let req = r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{},"id":9008}"#;
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
    assert!(resp.error.is_some());
    assert!(resp.error.unwrap().message.contains("not configured"));
}

/// LIVE-P2-1: patch_risk_config with engine="live" routes to live store,
/// not to paper store. paper store must remain at version 0.
/// LIVE-P2-1：engine="live" 的 patch_risk_config 應路由到 live store，
/// paper store 版本應維持 0。
#[tokio::test]
async fn test_p2_patch_risk_config_engine_routing() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Patch live engine only.
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"live","source":"operator","patch":{"limits":{"leverage_max":5.0}}},"id":9020}"#;
    let resp = dispatch_request(
        req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["ok"], true);
    assert_eq!(r["version"], 1);
    // live store mutated.
    let live_snap = rs.as_ref().unwrap().live.load();
    assert!(
        (live_snap.limits.leverage_max - 5.0).abs() < f64::EPSILON,
        "live store not updated"
    );
    // paper store untouched.
    assert_eq!(
        rs.as_ref().unwrap().paper.version(),
        0,
        "paper store should be untouched"
    );
    // demo store untouched.
    assert_eq!(
        rs.as_ref().unwrap().demo.version(),
        0,
        "demo store should be untouched"
    );
}

/// LIVE-P2-1: get_risk_config with engine="demo" returns demo store snapshot.
/// LIVE-P2-1：engine="demo" 的 get_risk_config 返回 demo store 快照。
#[tokio::test]
async fn test_p2_get_risk_config_engine_selection() {
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Pre-patch demo store so it has a distinct version.
    let patch_req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"demo","patch":{"limits":{"open_positions_max":7}}},"id":9021}"#;
    dispatch_request(
        patch_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    // Now GET demo config — should show version=1.
    let get_req =
        r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{"engine":"demo"},"id":9022}"#;
    let resp = dispatch_request(
        get_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["version"], 1, "demo store should be at version 1");
    // Paper store should still be at version 0.
    let paper_req = r#"{"jsonrpc":"2.0","method":"get_risk_config","params":{},"id":9023}"#;
    let resp2 = dispatch_request(
        paper_req,
        &config,
        &dd,
        &EngineCommandChannels::default(),
        &empty_budget_slot(),
        &empty_teacher_slot(),
        &rs,
        &ls,
        &bs,
        &None,
        &None,
        &None,
    )
    .await;
    let r2 = resp2.result.unwrap();
    assert_eq!(r2["version"], 0, "paper store should be at version 0");
}
