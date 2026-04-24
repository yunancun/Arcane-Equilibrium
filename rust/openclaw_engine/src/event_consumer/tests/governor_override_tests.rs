//! M-1 (ARCH-RC1 1C-3-D): Real guard tests for operator manual governor override.
//! Drives handle_paper_command(ForceGovernorLooser/Tighter) end-to-end so the
//! four IPC-layer guards actually fire. Previously the guards were only covered
//! by the `setup_governor_override_channel` fake consumer in ipc_server.rs tests
//! which bypassed the guard code entirely — a refactor could silently remove
//! every guard and CI would still pass (E2 review 2026-04-08 flag).
//! 真實驅動 handle_paper_command 的守衛測試；取代先前的假 consumer。

use super::{escalate_to_tier, make_test_pipeline, make_test_writer, run_looser, run_tighter};

#[test]
fn test_m1_looser_bad_reason_code_rejected() {
    // Guard 1: reason_code must be in whitelist.
    // 守衛 1：reason_code 必須在白名單內。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    escalate_to_tier(&mut p, RiskLevel::Cautious);
    let r = run_looser(&mut p, &mut w, "Normal", "because_i_said_so", "");
    assert!(r.is_err(), "bad reason must be rejected");
    let e = r.unwrap_err();
    assert!(
        e.contains("invalid reason_code"),
        "error mentions reason_code: {e}"
    );
    // State unchanged + cooldown NOT armed on rejection.
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
    assert_eq!(p.last_governor_de_escalation_ms(), None);
}

#[test]
fn test_m1_looser_cb_locked_out_via_ipc() {
    // Guard 4: CircuitBreaker cannot be unlocked from IPC even with a valid
    // reason_code — the single `if current >= CircuitBreaker` line is the ONLY
    // real lockout (SM's lookup_rule accepts operator approval), so this test
    // is the last line of defense for the hard-lock contract.
    // 守衛 4：CB 層不可透過 IPC 解鎖；此測試是硬鎖契約的最後防線。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    escalate_to_tier(&mut p, RiskLevel::CircuitBreaker);
    let r = run_looser(&mut p, &mut w, "Defensive", "root_cause_fixed", "");
    assert!(r.is_err(), "CB unlock must be rejected");
    let e = r.unwrap_err();
    assert!(e.contains("cannot be unlocked"), "error mentions lock: {e}");
    assert_eq!(
        p.governance.risk.snapshot_level(),
        RiskLevel::CircuitBreaker
    );
}

#[test]
fn test_m1_looser_mr_locked_out_via_ipc() {
    // Guard 4: ManualReview (one level above CB) also locked out.
    // 守衛 4：MR 同樣鎖死。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    escalate_to_tier(&mut p, RiskLevel::ManualReview);
    let r = run_looser(&mut p, &mut w, "CircuitBreaker", "accept_risk", "");
    assert!(r.is_err());
    assert!(r.unwrap_err().contains("cannot be unlocked"));
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::ManualReview);
}

#[test]
fn test_m1_looser_multi_step_rejected() {
    // Guard 3: must be exactly one tier lower — jumps rejected.
    // 守衛 3：一次只能降一級，跳級拒絕。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    escalate_to_tier(&mut p, RiskLevel::Defensive);
    let r = run_looser(&mut p, &mut w, "Normal", "false_positive", "");
    assert!(r.is_err());
    let e = r.unwrap_err();
    assert!(
        e.contains("exactly one tier below"),
        "error mentions step: {e}"
    );
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Defensive);
}

#[test]
fn test_m1_looser_cooldown_enforced_when_recent() {
    // Guard 2: if last de-escalation is within 24h, reject. Use a large
    // "last" value close to system now to guarantee elapsed < 24h regardless
    // of test wall-clock.
    // 守衛 2：24h 內曾降級過 → 拒絕。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    escalate_to_tier(&mut p, RiskLevel::Cautious);
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    // 1 hour ago → well inside 24h window
    p.set_last_governor_de_escalation_ms(Some(now_ms.saturating_sub(60 * 60 * 1000)));
    let r = run_looser(&mut p, &mut w, "Normal", "false_positive", "");
    assert!(r.is_err());
    let e = r.unwrap_err();
    assert!(e.contains("cooldown"), "error mentions cooldown: {e}");
    // State unchanged.
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
}

#[test]
fn test_m1_looser_happy_path_arms_cooldown() {
    // Positive control: valid reason + one-step down + CB-clear + no prior
    // de-escalation → accepted AND cooldown field armed for next call.
    // 正面控制：全部守衛通過 → 狀態下降且 cooldown 被記錄。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    escalate_to_tier(&mut p, RiskLevel::Cautious);
    assert_eq!(p.last_governor_de_escalation_ms(), None);
    let r = run_looser(&mut p, &mut w, "Normal", "false_positive", "post-review ok");
    assert!(r.is_ok(), "happy path must succeed: {r:?}");
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);
    assert!(
        p.last_governor_de_escalation_ms().is_some(),
        "cooldown armed"
    );
    // Second immediate call must now hit the cooldown guard.
    // 第二次立刻呼叫應撞到冷卻守衛。
    escalate_to_tier(&mut p, RiskLevel::Cautious);
    let r2 = run_looser(&mut p, &mut w, "Normal", "false_positive", "");
    assert!(r2.is_err());
    assert!(r2.unwrap_err().contains("cooldown"));
}

#[test]
fn test_m1_tighter_multi_step_rejected() {
    // Tighter side: Normal → Defensive is delta=3, rejected.
    // 收緊方向：跳級拒絕。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);
    let r = run_tighter(&mut p, &mut w, "Defensive", "operator sees spike");
    assert!(r.is_err());
    assert!(r.unwrap_err().contains("exactly one tier above"));
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);
}

#[test]
fn test_m1_tighter_reverse_rejected() {
    // Tighter side: Cautious → Normal is the wrong direction (delta=-1), rejected.
    // 收緊方向：反向拒絕（方向算不上 tighter）。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    escalate_to_tier(&mut p, RiskLevel::Cautious);
    let r = run_tighter(&mut p, &mut w, "Normal", "wrong direction");
    assert!(r.is_err());
    assert!(r.unwrap_err().contains("exactly one tier above"));
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
}
