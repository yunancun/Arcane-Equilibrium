//! Phase 6: ReconcilerEscalate / ReconcilerDeEscalate handler tests.
//! Drives handle_paper_command for the two new reconciler IPC commands.
//! Phase 6：對帳器自動降級/恢復 handler 測試。

use super::{
    escalate_to_tier, make_test_pipeline, make_test_writer, run_reconciler_de_escalate,
    run_reconciler_escalate,
};

#[test]
fn test_phase6_reconciler_escalate_normal_to_cautious() {
    // Reconciler escalation: Normal → Cautious on drift detection.
    // 對帳器升級：Normal → Cautious（漂移觸發）。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);

    let r = run_reconciler_escalate(&mut p, &mut w, "Cautious", "major_drift BTCUSDT");
    assert!(r.is_ok(), "escalate failed: {r:?}");
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
    // Verify JSON response.
    let json: serde_json::Value = serde_json::from_str(&r.unwrap()).expect("valid json");
    assert_eq!(json["from"].as_str().unwrap(), "NORMAL");
    assert_eq!(json["to"].as_str().unwrap(), "CAUTIOUS");
}

#[test]
fn test_phase6_reconciler_escalate_invalid_tier_rejected() {
    // Bad tier string must return Err, not panic.
    // 無效的級別字串必須返回 Err。
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    let r = run_reconciler_escalate(&mut p, &mut w, "SuperMax", "test");
    assert!(r.is_err());
}

#[test]
fn test_phase6_reconciler_de_escalate_cautious_to_normal() {
    // Reconciler recovery: Cautious → Normal after clean cycles met.
    // 對帳器恢復：Cautious → Normal（乾淨週期達標）。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    // First escalate to Cautious.
    escalate_to_tier(&mut p, RiskLevel::Cautious);

    let r = run_reconciler_de_escalate(&mut p, &mut w, "Normal", "30 clean cycles + 15min elapsed");
    assert!(r.is_ok(), "de-escalate failed: {r:?}");
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);
}

#[test]
fn test_phase6_reconciler_de_escalate_cb_blocked() {
    // CB cannot be de-escalated by reconciler — operator only.
    // CB 不可由對帳器自動恢復 — 僅限 operator。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    escalate_to_tier(&mut p, RiskLevel::CircuitBreaker);

    let r = run_reconciler_de_escalate(&mut p, &mut w, "Defensive", "test recovery attempt");
    assert!(r.is_err(), "CB de-escalation must be blocked");
    assert_eq!(
        p.governance.risk.snapshot_level(),
        RiskLevel::CircuitBreaker
    );
}

#[test]
fn test_phase6_reconciler_escalate_to_defensive() {
    // Multi-step escalation via reconciler: Normal → Cautious → Reduced → Defensive.
    // 對帳器多步升級：Normal → Cautious → Reduced → Defensive（持續漂移觸發）。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;

    let r1 = run_reconciler_escalate(&mut p, &mut w, "Cautious", "drift cycle 1");
    assert!(r1.is_ok());
    let r2 = run_reconciler_escalate(&mut p, &mut w, "Reduced", "drift cycle 2");
    assert!(r2.is_ok());
    let r3 = run_reconciler_escalate(&mut p, &mut w, "Defensive", "persistent drift ≥3 cycles");
    assert!(r3.is_ok());
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Defensive);
}
