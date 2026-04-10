//! 6-RC-7: End-to-end integration tests for Reconciler auto-contraction.
//! Verifies the full chain: evaluate_actions() → IPC command → handler → governor state change.
//! 6-RC-7：對帳器自動降級端到端集成測試。驗證完整鏈路。
//!
//! Scenarios:
//!   1. MajorDrift → ReconcilerEscalate → governor level rises to Cautious
//!   2. Persistent drift (3 cycles) → Defensive
//!   3. Burst (5+ simultaneous) → CircuitBreaker + CloseAll sent
//!   4. Recovery path: Cautious → Normal after clean cycles + wall-clock
//!   5. CB de-escalation blocked (operator only)
//!   6. REST failure streak → Cautious

use openclaw_engine::position_reconciler::{
    evaluate_actions, check_rest_failure_escalation, DriftVerdict, ReconcilerAction,
    ReconcilerState, PERSISTENT_DRIFT_CYCLES, RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL,
    RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS, PER_SYMBOL_COOLDOWN_MS,
    GLOBAL_COOLDOWN_MS, REST_FAILURE_TIER1_COUNT, REST_FAILURE_TIER2_COUNT,
};
use openclaw_engine::tick_pipeline::{PaperSessionCommand, TickPipeline};
use openclaw_engine::event_consumer::PendingOrder;
use openclaw_core::sm::risk_gov::RiskLevel;
use std::collections::HashMap;

// ═══════════════════════════════════════════════════════════════════════════
// Helpers / 輔助函數
// ═══════════════════════════════════════════════════════════════════════════

fn make_pipeline() -> TickPipeline {
    TickPipeline::with_balance(&["BTCUSDT", "ETHUSDT"], 10_000.0)
}

fn make_writer() -> openclaw_engine::persistence::StateWriter {
    use std::path::PathBuf;
    let mut p = std::env::temp_dir();
    p.push(format!("openclaw_reconciler_e2e_{}.json", std::process::id()));
    openclaw_engine::persistence::StateWriter::new(&p as &PathBuf, 5_000)
}

/// Drive a ReconcilerEscalate command through the handler and return result.
/// 驅動 ReconcilerEscalate 命令通過 handler 並返回結果。
fn drive_escalate(
    pipeline: &mut TickPipeline,
    writer: &mut openclaw_engine::persistence::StateWriter,
    target: &str,
    reason: &str,
) -> Result<String, String> {
    let mut pending: HashMap<String, PendingOrder> = HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    openclaw_engine::event_consumer::handlers::handle_paper_command(
        PaperSessionCommand::ReconcilerEscalate {
            target_tier: target.into(),
            reason: reason.into(),
            response_tx: tx,
        },
        pipeline,
        writer,
        &mut pending,
    );
    rx.blocking_recv().expect("response channel")
}

/// Drive a ReconcilerDeEscalate command through the handler and return result.
/// 驅動 ReconcilerDeEscalate 命令通過 handler 並返回結果。
fn drive_de_escalate(
    pipeline: &mut TickPipeline,
    writer: &mut openclaw_engine::persistence::StateWriter,
    target: &str,
    reason: &str,
) -> Result<String, String> {
    let mut pending: HashMap<String, PendingOrder> = HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    openclaw_engine::event_consumer::handlers::handle_paper_command(
        PaperSessionCommand::ReconcilerDeEscalate {
            target_tier: target.into(),
            reason: reason.into(),
            response_tx: tx,
        },
        pipeline,
        writer,
        &mut pending,
    );
    rx.blocking_recv().expect("response channel")
}

/// Escalate pipeline to a given level via operator path (test setup helper).
/// 通過 operator 路徑將 pipeline 升至指定級別（測試設置輔助）。
fn setup_escalate_to(pipeline: &mut TickPipeline, target: RiskLevel) {
    use openclaw_core::sm::risk_gov::RiskEvent;
    pipeline.governance.risk.thresholds.min_hold_time_ms = 0;
    let ladder = [
        RiskLevel::Cautious,
        RiskLevel::Reduced,
        RiskLevel::Defensive,
        RiskLevel::CircuitBreaker,
        RiskLevel::ManualReview,
    ];
    for step in ladder {
        if pipeline.governance.risk.snapshot_level() >= target {
            break;
        }
        pipeline
            .governance
            .risk
            .escalate_to(step, "e2e_setup", RiskEvent::OperatorEscalation)
            .expect("test escalation");
    }
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario 1: MajorDrift → Cautious (full chain)
// 場景 1：MajorDrift → Cautious（完整鏈路）
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_major_drift_escalates_to_cautious() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];

    // Phase 1: evaluate_actions produces Escalate → Cautious
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    assert_eq!(actions.len(), 1);
    assert!(matches!(&actions[0], ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Cautious));

    // Phase 2: Drive through handler — governor level actually changes
    let mut p = make_pipeline();
    let mut w = make_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);

    let r = drive_escalate(&mut p, &mut w, "Cautious", "major_drift BTCUSDT");
    assert!(r.is_ok(), "escalate failed: {r:?}");
    assert_eq!(
        p.governance.risk.snapshot_level(),
        RiskLevel::Cautious,
        "governor must be at Cautious after major drift"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario 2: Persistent drift (3 cycles) → Defensive
// 場景 2：持續漂移（3 週期）→ Defensive
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_persistent_drift_escalates_to_defensive() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];

    // Simulate 3 cycles of the same drift.
    // Cycle 1: Normal → Cautious (single drift).
    // Cycle 2: streak=2, target=Cautious, but already at Cautious → skip (target not > current).
    // Cycle 3: streak=3 → persistent → target=Defensive, bypasses per-symbol cooldown
    //          (QC audit fix), only needs global 5min cooldown.
    let mut current_level = RiskLevel::Normal;
    let mut pipeline = make_pipeline();
    let mut writer = make_writer();
    pipeline.governance.risk.thresholds.min_hold_time_ms = 0;

    for cycle in 0..PERSISTENT_DRIFT_CYCLES {
        // Space cycles by global cooldown only (not per-symbol 30min).
        // Persistent drift (≥3 cycles) bypasses per-symbol cooldown.
        let t = t0 + (cycle as u64) * (GLOBAL_COOLDOWN_MS + 1);
        let actions = evaluate_actions(&mut state, current_level, &drifts, t);

        for action in &actions {
            if let ReconcilerAction::Escalate { target, reason } = action {
                let r = drive_escalate(&mut pipeline, &mut writer, &target.as_str(), reason);
                assert!(r.is_ok(), "escalate failed at cycle {cycle}: {r:?}");
                current_level = pipeline.governance.risk.snapshot_level();
            }
        }
    }

    // After 3 cycles: cycle 1 → Cautious, cycle 3 → Defensive
    assert_eq!(
        pipeline.governance.risk.snapshot_level(),
        RiskLevel::Defensive,
        "3 cycles of persistent drift must reach Defensive"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario 3: Burst (5+ simultaneous drifts) → CircuitBreaker + CloseAll
// 場景 3：爆發（5+ 同時漂移）→ CB + CloseAll
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_burst_triggers_circuit_breaker_and_close_all() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    // 5 simultaneous drifts across different symbols
    let drifts: Vec<(String, DriftVerdict)> = vec![
        ("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift),
        ("ETHUSDT|Buy".into(), DriftVerdict::Orphan),
        ("SOLUSDT|Sell".into(), DriftVerdict::Ghost),
        ("XRPUSDT|Buy".into(), DriftVerdict::MajorDrift),
        ("DOGEUSDT|Buy".into(), DriftVerdict::Orphan),
    ];

    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);

    // Must contain both Escalate(CB) and CloseAll
    let has_cb = actions.iter().any(|a| {
        matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::CircuitBreaker)
    });
    let has_close_all = actions.iter().any(|a| matches!(a, ReconcilerAction::CloseAll { .. }));

    assert!(has_cb, "burst must trigger CircuitBreaker escalation");
    assert!(has_close_all, "burst must trigger CloseAll");

    // Drive CB through handler
    let mut p = make_pipeline();
    let mut w = make_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;

    let r = drive_escalate(&mut p, &mut w, "CircuitBreaker", "5 simultaneous drifts (burst)");
    assert!(r.is_ok());
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::CircuitBreaker);
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario 4: Recovery path — Cautious → Normal after clean cycles + wall-clock
// 場景 4：恢復路徑 — Cautious → Normal（乾淨週期 + 牆鐘）
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_recovery_cautious_to_normal() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    // Step 1: Escalate to Cautious via drift
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    assert!(!actions.is_empty(), "should escalate");

    // Simulate main-loop behavior: set pre_escalation_level after successful dispatch
    // (Finding 6 fix: evaluate_actions no longer sets this directly)
    state.pre_escalation_level = Some(RiskLevel::Normal);

    // Apply through handler
    let mut p = make_pipeline();
    let mut w = make_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    let r = drive_escalate(&mut p, &mut w, "Cautious", "major_drift test");
    assert!(r.is_ok());
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);

    // Step 2: Simulate clean cycles + wall-clock
    let empty_drifts: Vec<(String, DriftVerdict)> = vec![];
    let recovery_time = t0 + RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS + 1;

    for cycle in 0..RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL {
        let t = t0 + 1 + (cycle as u64) * 30_000;
        evaluate_actions(&mut state, RiskLevel::Cautious, &empty_drifts, t);
    }
    // Final evaluation at sufficient wall-clock time
    let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &empty_drifts, recovery_time);

    let has_recovery = actions.iter().any(|a| {
        matches!(a, ReconcilerAction::DeEscalate { target, .. } if *target == RiskLevel::Normal)
    });
    assert!(has_recovery, "should recover to Normal after 30 cycles + 15min");

    // Drive recovery through handler
    let r = drive_de_escalate(&mut p, &mut w, "Normal", "auto-recovery test");
    assert!(r.is_ok());
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario 5: CB de-escalation blocked (operator only)
// 場景 5：CB 降級被阻止（僅限 operator）
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_cb_de_escalation_blocked() {
    let mut p = make_pipeline();
    let mut w = make_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    setup_escalate_to(&mut p, RiskLevel::CircuitBreaker);

    // Reconciler attempts to de-escalate CB → Defensive
    let r = drive_de_escalate(&mut p, &mut w, "Defensive", "clean cycles met");
    assert!(r.is_err(), "CB de-escalation by reconciler must be blocked");
    assert_eq!(
        p.governance.risk.snapshot_level(),
        RiskLevel::CircuitBreaker,
        "level must remain at CB"
    );

    // Also verify evaluate_actions never proposes CB recovery
    let mut state = ReconcilerState::new();
    state.pre_escalation_level = Some(RiskLevel::Normal);
    state.clean_cycles_since_last_drift = 999;
    state.last_drift_seen_ms = 0;
    let actions = evaluate_actions(
        &mut state,
        RiskLevel::CircuitBreaker,
        &[],
        100_000_000,
    );
    let has_de_escalate = actions.iter().any(|a| matches!(a, ReconcilerAction::DeEscalate { .. }));
    assert!(!has_de_escalate, "evaluate_actions must never propose CB de-escalation");
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario 6: REST failure streak → Cautious (6-RC-10)
// 場景 6：REST 失敗連續 → Cautious（6-RC-10）
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_rest_failure_streak_escalates() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    // Simulate 10 consecutive REST failures
    state.consecutive_rest_failures = REST_FAILURE_TIER1_COUNT;

    let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, t0);
    assert!(action.is_some(), "10 REST failures should produce escalation");
    let action = action.unwrap();
    assert!(matches!(
        action,
        ReconcilerAction::Escalate { target, .. } if target == RiskLevel::Cautious
    ));

    // Drive through handler
    let mut p = make_pipeline();
    let mut w = make_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;

    let r = drive_escalate(&mut p, &mut w, "Cautious", "10 consecutive REST failures");
    assert!(r.is_ok());
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario 7: Floor rule — recovery does not go below pre_escalation_level
// 場景 7：Floor rule — 恢復不會低於 pre_escalation_level
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_floor_rule_prevents_over_recovery() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    // Simulate: drawdown already pushed us to Cautious, then reconciler escalated to Reduced.
    // pre_escalation_level = Cautious (the floor).
    state.pre_escalation_level = Some(RiskLevel::Cautious);
    state.last_drift_seen_ms = t0;
    state.clean_cycles_since_last_drift = 0;

    // Accumulate clean cycles. Recovery fires when cycles ≥ 20 AND wall ≥ 10min.
    // Track actions produced to detect when recovery fires.
    let empty: Vec<(String, DriftVerdict)> = vec![];
    let mut recovery_found = false;
    for c in 0..25 {
        let t = t0 + 1 + (c as u64) * 30_000;
        let actions = evaluate_actions(
            &mut state,
            RiskLevel::Reduced,
            &empty,
            t,
        );
        if actions.iter().any(|a| {
            matches!(a, ReconcilerAction::DeEscalate { target, .. } if *target == RiskLevel::Cautious)
        }) {
            recovery_found = true;
            break;
        }
    }
    assert!(recovery_found, "should recover Reduced → Cautious (floor)");

    // After hitting floor, pre_escalation_level should be cleared.
    assert!(
        state.pre_escalation_level.is_none(),
        "pre_escalation_level must be cleared after reaching floor"
    );

    // Further clean cycles at Cautious should NOT produce Normal recovery
    // because pre_escalation_level is None (reconciler has no floor context).
    for c in 0..35 {
        let actions = evaluate_actions(
            &mut state,
            RiskLevel::Cautious,
            &empty,
            t0 + 25 * 60 * 1000 + (c as u64) * 30_000,
        );
        let has_normal = actions.iter().any(|a| {
            matches!(a, ReconcilerAction::DeEscalate { target, .. } if *target == RiskLevel::Normal)
        });
        assert!(
            !has_normal,
            "after floor cleared, reconciler must not propose further recovery"
        );
    }
}
