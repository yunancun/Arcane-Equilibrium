//! ARCH-RC1 1C-2-C / LIVE-P2-1: unified Config IPC endpoint tests.
//! ARCH-RC1 1C-2-C / LIVE-P2-1：統一 Config IPC 端點測試。

use super::super::*;
use super::{empty_budget_slot, empty_cost_edge_advisor_slot, empty_h_state_cache_slot, empty_teacher_slot, make_test_config, make_test_data_dir};

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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    let r2 = resp2.result.unwrap();
    assert_eq!(r2["version"], 0, "paper store should be at version 0");
}

// ────────────────────────────────────────────────────────────────────────
// G3-02 Phase A Part 2 (2026-04-25): ExecutorConfig is `RiskConfig.executor`
// (a sub-field, not a separate ConfigStore — same pattern as KellyTierConfig).
// The existing `patch_risk_config` IPC method already handles deep-JSON merge,
// so toggling executor.shadow_mode goes through the same channel without
// needing a dedicated `patch_executor_config` method (which the original RFC
// proposed before Phase A consolidated executor under RiskConfig).
//
// Trade-off: dedicated method would let us add a stricter auth gate for the
// shadow→live flip. Phase C will layer that auth check on top regardless of
// IPC entry point — the gate lives at the auth-actor level, not per-method.
// G3-02 Phase A Part 2：ExecutorConfig 是 RiskConfig.executor 子欄位，
// `patch_risk_config` 已可走 deep-JSON merge 切換 executor.shadow_mode；
// 無需另開 `patch_executor_config` 方法。Phase C 的更嚴 auth gate 在 actor
// 層加，與 IPC 入口無關。
// ────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_g3_02_a2_patch_executor_shadow_mode_via_patch_risk_config() {
    // Verify executor.shadow_mode can be flipped via the existing
    // patch_risk_config IPC. Default is true; patch flips to false.
    // 驗證 executor.shadow_mode 經 patch_risk_config 翻轉成 false。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    // Confirm default state.
    assert!(
        rs.as_ref().unwrap().paper.load().executor.shadow_mode,
        "default executor.shadow_mode must be true"
    );
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator","patch":{"executor":{"shadow_mode":false}}},"id":9101}"#;
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["ok"], true);
    assert_eq!(r["version"], 1);
    // Paper store mutated; executor.shadow_mode now false.
    let snap = rs.as_ref().unwrap().paper.load();
    assert!(
        !snap.executor.shadow_mode,
        "executor.shadow_mode must be false after patch"
    );
    // Other executor fields unchanged.
    assert!((snap.executor.max_position_pct - 0.05).abs() < 1e-12);
    // Other risk fields untouched (no cross-section bleed).
    assert!((snap.limits.leverage_max - 20.0).abs() < f64::EPSILON);
}

#[tokio::test]
async fn test_g3_02_a2_patch_executor_max_position_pct() {
    // Patch executor.max_position_pct only; shadow_mode stays default true.
    // 僅修改 max_position_pct；shadow_mode 保持預設 true。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator","patch":{"executor":{"max_position_pct":0.10}}},"id":9102}"#;
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let snap = rs.as_ref().unwrap().paper.load();
    assert!((snap.executor.max_position_pct - 0.10).abs() < 1e-12);
    assert!(
        snap.executor.shadow_mode,
        "shadow_mode must remain default true (not in patch)"
    );
}

#[tokio::test]
async fn test_g3_02_a2_patch_executor_invalid_max_position_pct_rolls_back() {
    // max_position_pct > 1.0 must reject and roll back the entire patch.
    // max_position_pct 越界必須拒絕並全 patch 回滾。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let original_version = rs.as_ref().unwrap().paper.version();
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"patch":{"executor":{"max_position_pct":1.5}}},"id":9103}"#;
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_some(), "expected validation error");
    // Paper store untouched.
    assert_eq!(rs.as_ref().unwrap().paper.version(), original_version);
    let snap = rs.as_ref().unwrap().paper.load();
    assert!((snap.executor.max_position_pct - 0.05).abs() < 1e-12);
}

#[tokio::test]
async fn test_g3_02_a2_patch_executor_routes_to_demo_engine() {
    // Verify engine="demo" param routes the executor patch to demo store
    // (paper untouched). Mirrors the LIVE-P2-1 per-engine routing test.
    // 驗證 engine="demo" 參數路由 executor patch 至 demo store；paper 不動。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"demo","source":"operator","patch":{"executor":{"shadow_mode":false}}},"id":9104}"#;
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    // Demo store mutated; paper still default.
    let demo_snap = rs.as_ref().unwrap().demo.load();
    assert!(!demo_snap.executor.shadow_mode);
    let paper_snap = rs.as_ref().unwrap().paper.load();
    assert!(
        paper_snap.executor.shadow_mode,
        "paper store must remain default true"
    );
}

// ────────────────────────────────────────────────────────────────────────
// G3-05 EDGE-DIAG-1-FUP-SHADOW-ENABLED-IPC (2026-04-25):
// Regression coverage for `RiskConfig.exit.shadow_enabled` IPC hot-reload.
// Combine Layer Shadow exit observation pipeline (INFRA-PREBUILD-1 Part A,
// commits 6226b38..74b678a, 2026-04-23) is gated by this flag. EDGE-P2
// Phase 2+ shadow flip needs to be IPC-flippable without engine restart;
// these tests prove the existing `patch_risk_config` deep-merge already
// covers the exit.shadow_enabled field surface — no new IPC method or
// handler required, just like G3-02 Phase A2 demonstrated for executor.*.
// G3-05：exit.shadow_enabled IPC 熱重載 regression coverage；
// patch_risk_config deep-merge 已涵蓋此欄位，無需新方法。
// ────────────────────────────────────────────────────────────────────────

#[tokio::test]
async fn test_g3_05_patch_exit_shadow_enabled_via_patch_risk_config() {
    // Default false → patch true → confirm read-back + version bump.
    // 預設 false → patch true → 確認讀回 + version 升。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    assert!(
        !rs.as_ref().unwrap().paper.load().exit.shadow_enabled,
        "default exit.shadow_enabled must be false"
    );
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"source":"operator","patch":{"exit":{"shadow_enabled":true}}},"id":9201}"#;
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let r = resp.result.unwrap();
    assert_eq!(r["ok"], true);
    assert_eq!(r["version"], 1);
    let snap = rs.as_ref().unwrap().paper.load();
    assert!(
        snap.exit.shadow_enabled,
        "exit.shadow_enabled must be true after patch"
    );
}

#[tokio::test]
async fn test_g3_05_patch_exit_shadow_enabled_per_engine_routing() {
    // engine="demo" routes to demo store only; paper untouched.
    // engine="demo" 路由 demo 專屬；paper 不動。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"engine":"demo","source":"operator","patch":{"exit":{"shadow_enabled":true}}},"id":9202}"#;
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_none(), "expected success: {resp:?}");
    let demo_snap = rs.as_ref().unwrap().demo.load();
    assert!(demo_snap.exit.shadow_enabled, "demo flipped to true");
    let paper_snap = rs.as_ref().unwrap().paper.load();
    assert!(
        !paper_snap.exit.shadow_enabled,
        "paper store must remain default false"
    );
}

#[tokio::test]
async fn test_g3_05_patch_exit_shadow_enabled_invalid_type_rejected() {
    // Non-bool (string "true") must reject → no version bump.
    // 非 bool（字串 "true"）必拒，version 不升。
    let config = make_test_config();
    let dd = make_test_data_dir();
    let (rs, ls, bs) = rc1_stores();
    let original_version = rs.as_ref().unwrap().paper.version();
    let req = r#"{"jsonrpc":"2.0","method":"patch_risk_config","params":{"patch":{"exit":{"shadow_enabled":"true"}}},"id":9203}"#;
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
        &None,
        &empty_h_state_cache_slot(),
        &None,
        &None,
        &empty_cost_edge_advisor_slot(),
    )
    .await;
    assert!(resp.error.is_some(), "non-bool must reject");
    assert_eq!(rs.as_ref().unwrap().paper.version(), original_version);
    let snap = rs.as_ref().unwrap().paper.load();
    assert!(
        !snap.exit.shadow_enabled,
        "exit.shadow_enabled must remain default false"
    );
}
