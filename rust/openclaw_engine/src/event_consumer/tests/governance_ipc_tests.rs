//! SM Option-2 收斂 step (i)（2026-06-02）：治理 lease + 唯讀投影 handler 測試。
//!
//! 真實驅動 `handle_paper_command` 的 7 個新治理變體 end-to-end（用 make_test_pipeline
//! 的真實 GovernanceCore），覆蓋：
//!   - acquire round-trip：Production（需先 authorize）回 Active + 真實 lease_id；
//!     非 Production（Exploration/Validation）回 Bypass（短路，不需 auth）。
//!   - acquire fail-closed：Production 未 authorize → AuthNotEffective Err；
//!     未知 profile → parse Err；ttl 超界 → InvalidTtl Err。
//!   - release round-trip：Consumed 成功 {ok:true}；未知 outcome → parse Err；
//!     未知 lease_id → LeaseNotFound Err（fail-closed）。
//!   - get round-trip：acquire 後可查回含 lease_id；未知 lease_id → Err（Python None）。
//!   - 唯讀投影：is_authorized / get_status / list_leases / get_risk_state 形狀。
//!
//! 這些測試是 4a 之外的 step (i) 回歸鎖：證明 dispatch arm 路由與 fail-closed
//! 路徑真實工作（而非靠 mock）。

use super::{authorize, make_test_pipeline, make_test_writer};
use crate::tick_pipeline::PipelineCommand;

/// 共用：驅動一個治理 PipelineCommand 並回 oneshot 結果。
fn run_governance_cmd(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::DualStateWriter,
    make_cmd: impl FnOnce(tokio::sync::oneshot::Sender<Result<String, String>>) -> PipelineCommand,
) -> Result<String, String> {
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::super::handlers::handle_paper_command(make_cmd(tx), pipeline, writer, &mut pending);
    rx.blocking_recv().expect("response sent")
}

fn acquire(
    p: &mut crate::tick_pipeline::TickPipeline,
    w: &mut crate::persistence::DualStateWriter,
    intent_id: &str,
    profile: &str,
    ttl_ms: u32,
) -> Result<String, String> {
    run_governance_cmd(p, w, |tx| PipelineCommand::AcquireLease {
        intent_id: intent_id.into(),
        scope: "TRADE_ENTRY".into(),
        ttl_ms,
        profile: profile.into(),
        source_stage: "test".into(),
        response_tx: tx,
    })
}

#[test]
fn test_acquire_production_after_authorize_returns_active() {
    // Production profile 需先有 effective auth；authorize() 後 acquire 走真實 SM
    // 路徑回 LeaseId::Active(真實 lease_id)。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    authorize(&mut p);
    let r = acquire(&mut p, &mut w, "intent_prod_1", "Production", 60_000);
    assert!(r.is_ok(), "acquire after authorize must succeed: {r:?}");
    let v: serde_json::Value = serde_json::from_str(&r.unwrap()).expect("json");
    assert_eq!(v["outcome"], "Active", "production → Active outcome");
    let lease_id = v["lease_id"].as_str().expect("lease_id str");
    assert!(
        lease_id.starts_with("lease:"),
        "real lease_id, got {lease_id}"
    );
    assert_ne!(lease_id, "bypass", "production must not bypass");
}

#[test]
fn test_acquire_production_without_auth_fails_closed() {
    // 硬 fail-closed：Production 無 effective auth → AuthNotEffective Err（不回 lease）。
    // 這是 5-gate live boundary 之一（GovernanceCore::is_authorized gate），不可放鬆。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    let r = acquire(&mut p, &mut w, "intent_prod_2", "Production", 60_000);
    assert!(r.is_err(), "production without auth must fail-closed");
    assert!(
        r.unwrap_err().contains("authorization not effective"),
        "error mentions auth gate"
    );
}

#[test]
fn test_acquire_exploration_bypass_no_auth_needed() {
    // 非 Production（Exploration）短路回 Bypass；不需 auth，as_str() = "bypass"。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    let r = acquire(&mut p, &mut w, "intent_explore_1", "Exploration", 60_000);
    assert!(r.is_ok(), "exploration bypass must succeed: {r:?}");
    let v: serde_json::Value = serde_json::from_str(&r.unwrap()).expect("json");
    assert_eq!(v["outcome"], "Bypass");
    assert_eq!(v["lease_id"], "bypass");
}

#[test]
fn test_acquire_unknown_profile_fails_closed() {
    // 未知 profile → parse Err（不默認 Production，也不默認 bypass）。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    authorize(&mut p);
    let r = acquire(&mut p, &mut w, "intent_bad_profile", "Garbage", 60_000);
    assert!(r.is_err(), "unknown profile must fail-closed");
    assert!(r.unwrap_err().contains("unknown governance profile"));
}

#[test]
fn test_acquire_invalid_ttl_fails_closed() {
    // ttl 超界（< 100ms）→ GovernanceCore::acquire_lease InvalidTtl Err。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    authorize(&mut p);
    let r = acquire(&mut p, &mut w, "intent_bad_ttl", "Production", 50);
    assert!(r.is_err(), "ttl < 100ms must fail-closed");
    assert!(r.unwrap_err().contains("invalid TTL"));
}

#[test]
fn test_release_consumed_round_trip() {
    // acquire(Production) → release(Consumed) → {ok:true}。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    authorize(&mut p);
    let acq = acquire(&mut p, &mut w, "intent_rel_1", "Production", 60_000).expect("acquire ok");
    let lease_id = serde_json::from_str::<serde_json::Value>(&acq).unwrap()["lease_id"]
        .as_str()
        .unwrap()
        .to_string();
    let r = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::ReleaseLease {
        lease_id: lease_id.clone(),
        outcome: "Consumed".into(),
        response_tx: tx,
    });
    assert!(r.is_ok(), "release must succeed: {r:?}");
    let v: serde_json::Value = serde_json::from_str(&r.unwrap()).expect("json");
    assert_eq!(v["ok"], true);
}

#[test]
fn test_release_unknown_outcome_fails_closed() {
    // 未知 outcome → parse Err（不默認 Consumed）。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    let r = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::ReleaseLease {
        lease_id: "lease:abc".into(),
        outcome: "Whatever".into(),
        response_tx: tx,
    });
    assert!(r.is_err(), "unknown outcome must fail-closed");
    assert!(r.unwrap_err().contains("unknown lease outcome"));
}

#[test]
fn test_release_unknown_lease_id_fails_closed() {
    // 未知 lease_id（反查表無）→ LeaseNotFound Err（Python release → False）。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    let r = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::ReleaseLease {
        lease_id: "lease:doesnotexist".into(),
        outcome: "Consumed".into(),
        response_tx: tx,
    });
    assert!(r.is_err(), "unknown lease_id must fail-closed");
    assert!(r.unwrap_err().contains("release_lease failed"));
}

#[test]
fn test_get_lease_round_trip_and_not_found() {
    // acquire 後 get 可查回含 lease_id 的 LeaseObject；未知 lease_id → Err（None）。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    authorize(&mut p);
    let acq = acquire(&mut p, &mut w, "intent_get_1", "Production", 60_000).expect("acquire ok");
    let lease_id = serde_json::from_str::<serde_json::Value>(&acq).unwrap()["lease_id"]
        .as_str()
        .unwrap()
        .to_string();
    let got = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::GetLease {
        lease_id: lease_id.clone(),
        response_tx: tx,
    });
    assert!(got.is_ok(), "get_lease must succeed: {got:?}");
    let v: serde_json::Value = serde_json::from_str(&got.unwrap()).expect("json");
    // LeaseObject serde 必含 lease_id（Python parse_get_response 據此判 found）。
    assert_eq!(v["lease_id"].as_str().unwrap(), lease_id);
    assert!(v.get("state").is_some(), "LeaseObject has state field");

    // not found → Err。
    let miss = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::GetLease {
        lease_id: "lease:missing".into(),
        response_tx: tx,
    });
    assert!(miss.is_err(), "missing lease → fail-closed Err");
}

#[test]
fn test_is_authorized_projection() {
    // 未 authorize → authorized=false（fail-closed 語意）；authorize 後 → true。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    let before = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::IsAuthorized {
        response_tx: tx,
    })
    .expect("ok");
    let vb: serde_json::Value = serde_json::from_str(&before).unwrap();
    assert_eq!(vb["authorized"], false, "no auth → false");

    authorize(&mut p);
    let after = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::IsAuthorized {
        response_tx: tx,
    })
    .expect("ok");
    let va: serde_json::Value = serde_json::from_str(&after).unwrap();
    assert_eq!(va["authorized"], true, "after authorize → true");
}

#[test]
fn test_get_status_projection_shape() {
    // get_status 形狀：含 enabled/mode/risk_level/auth_effective_count/
    // auth_pending_approval/lease_live_count/oms_active_count。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    authorize(&mut p);
    let r = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::GetGovStatus {
        response_tx: tx,
    })
    .expect("ok");
    let v: serde_json::Value = serde_json::from_str(&r).expect("json");
    assert!(v.get("enabled").is_some());
    assert!(v.get("mode").is_some());
    assert!(v.get("risk_level").is_some());
    assert!(
        v.get("auth_pending_approval").is_some(),
        "auth_pending_approval present (Python approve queue)"
    );
    assert!(v["auth_effective_count"].as_u64().unwrap() >= 1, "auth granted");
}

#[test]
fn test_list_leases_projection() {
    // 空時回 []；acquire 1 production lease 後含 1 live lease 含 lease_id。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    let empty = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::ListLeases {
        response_tx: tx,
    })
    .expect("ok");
    let ve: serde_json::Value = serde_json::from_str(&empty).expect("json");
    assert_eq!(ve.as_array().unwrap().len(), 0, "no leases → []");

    authorize(&mut p);
    acquire(&mut p, &mut w, "intent_list_1", "Production", 60_000).expect("acquire ok");
    let r = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::ListLeases {
        response_tx: tx,
    })
    .expect("ok");
    let v: serde_json::Value = serde_json::from_str(&r).expect("json");
    let arr = v.as_array().expect("array");
    assert_eq!(arr.len(), 1, "one live lease");
    assert!(arr[0].get("lease_id").is_some());
}

#[test]
fn test_get_risk_state_projection_shape() {
    // get_risk_state 形狀：level/level_value/level_entered_at_ms/held_ms/
    // constraints/transitions_tail；預設 Normal。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    let r = run_governance_cmd(&mut p, &mut w, |tx| PipelineCommand::GetRiskState {
        response_tx: tx,
    })
    .expect("ok");
    let v: serde_json::Value = serde_json::from_str(&r).expect("json");
    assert_eq!(v["level"], "NORMAL", "default level NORMAL");
    assert_eq!(v["level_value"], 0);
    assert!(v.get("held_ms").is_some());
    assert!(
        v["constraints"]["new_entries_allowed"].as_bool().unwrap(),
        "Normal allows entries"
    );
    assert!(
        v.get("transitions_tail").map(|t| t.is_array()).unwrap_or(false),
        "transitions_tail is array"
    );
}
