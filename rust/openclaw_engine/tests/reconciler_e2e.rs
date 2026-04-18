//! 6-RC-7 + 6-04 + 6-05: End-to-end integration + stress tests for Reconciler auto-contraction.
//! Verifies the full chain: evaluate_actions() → IPC command → handler → governor state change.
//! 6-RC-7 + 6-04 + 6-05：對帳器自動降級端到端集成 + 壓力測試。驗證完整鏈路。
//!
//! Scenarios (6-RC-7 original):
//!   1. MajorDrift → ReconcilerEscalate → governor level rises to Cautious
//!   2. Persistent drift (3 cycles) → Defensive
//!   3. Burst (5+ simultaneous) → CircuitBreaker + CloseAll sent
//!   4. Recovery path: Cautious → Normal after clean cycles + wall-clock
//!   5. CB de-escalation blocked (operator only)
//!   6. REST failure streak → Cautious
//! Scenarios (6-04 integration):
//!   7. MinorDrift does NOT reset clean cycle counter
//!   8. SideFlip → Cautious (full handler chain)
//!   9. Ghost → Cautious (full handler chain)
//!  10. Per-symbol cooldown blocks repeat escalation
//!  11. Global cooldown limits rapid-fire escalation
//!  12. Multi-tier recovery Defensive → Reduced → Cautious → Normal
//!  13. REST failure progressive tiers (10→Cautious, 30→Reduced, 60→Defensive)
//!  14. Floor rule — recovery does not go below pre_escalation_level
//! Stress (6-05):
//!  S1. 100 cycles rapid drift/clean alternation — no panic, state consistent
//!  S2. 50 simultaneous symbols — burst→CB, no panic
//!  S3. 20 rapid handler escalate/de-escalate rounds — no deadlock
//!  S4. 1000 evaluate_actions calls performance < 100ms

use openclaw_core::sm::risk_gov::RiskLevel;
use openclaw_engine::event_consumer::PendingOrder;
use openclaw_engine::position_reconciler::{
    check_rest_failure_escalation, evaluate_actions, DriftVerdict, ReconcilerAction,
    ReconcilerState, GLOBAL_COOLDOWN_MS, PERSISTENT_DRIFT_CYCLES,
    RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL, RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS,
    REST_FAILURE_TIER1_COUNT, REST_FAILURE_TIER2_COUNT, REST_FAILURE_TIER3_COUNT, STARTUP_GRACE_MS,
};
use openclaw_engine::tick_pipeline::{PipelineCommand, TickPipeline};
use std::collections::HashMap;

// ═══════════════════════════════════════════════════════════════════════════
// Helpers / 輔助函數
// ═══════════════════════════════════════════════════════════════════════════

fn make_pipeline() -> TickPipeline {
    TickPipeline::with_balance(&["BTCUSDT", "ETHUSDT"], 10_000.0)
}

fn make_writer() -> openclaw_engine::persistence::DualStateWriter {
    use std::path::PathBuf;
    let mut p = std::env::temp_dir();
    // Use pid + thread id to avoid collisions in parallel test runs.
    // 使用 pid + 線程 id 避免並行測試時文件衝突。
    p.push(format!(
        "openclaw_reconciler_e2e_{}_{:?}.json",
        std::process::id(),
        std::thread::current().id()
    ));
    let primary = openclaw_engine::persistence::StateWriter::new(&p as &PathBuf, 5_000);
    openclaw_engine::persistence::DualStateWriter::new(primary, None)
}

/// Drive a ReconcilerEscalate command through the handler and return result.
/// 驅動 ReconcilerEscalate 命令通過 handler 並返回結果。
fn drive_escalate(
    pipeline: &mut TickPipeline,
    writer: &mut openclaw_engine::persistence::DualStateWriter,
    target: &str,
    reason: &str,
) -> Result<String, String> {
    let mut pending: HashMap<String, PendingOrder> = HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    openclaw_engine::event_consumer::handlers::handle_paper_command(
        PipelineCommand::ReconcilerEscalate {
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
    writer: &mut openclaw_engine::persistence::DualStateWriter,
    target: &str,
    reason: &str,
) -> Result<String, String> {
    let mut pending: HashMap<String, PendingOrder> = HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    openclaw_engine::event_consumer::handlers::handle_paper_command(
        PipelineCommand::ReconcilerDeEscalate {
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
    assert!(
        matches!(&actions[0], ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Cautious)
    );

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
/// FIX-B: Two consecutive burst cycles are now required to reach CB.
/// First cycle → Defensive (warning shot); second consecutive → CB + CloseAll.
/// FIX-B：現在需要兩次連續 burst 週期才能達到 CB。第一次 → Defensive；連續第二次 → CB。
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

    // First burst cycle: must escalate to Defensive (not CB yet)
    let actions1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    let has_defensive = actions1.iter().any(|a| {
        matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Defensive)
    });
    assert!(
        has_defensive,
        "first burst cycle must escalate to Defensive, not CB"
    );
    assert_eq!(state.burst_drift_streak, 1);

    // Second consecutive burst cycle (far-future ts to bypass cooldown): must reach CB
    let actions2 = evaluate_actions(&mut state, RiskLevel::Defensive, &drifts, 999_999_999);
    let has_cb = actions2.iter().any(|a| {
        matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::CircuitBreaker)
    });
    let has_close_all = actions2
        .iter()
        .any(|a| matches!(a, ReconcilerAction::CloseAll { .. }));

    assert!(
        has_cb,
        "second consecutive burst cycle must trigger CircuitBreaker escalation"
    );
    assert!(
        has_close_all,
        "second consecutive burst cycle must trigger CloseAll"
    );

    // Drive CB through handler
    let mut p = make_pipeline();
    let mut w = make_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;

    let r = drive_escalate(
        &mut p,
        &mut w,
        "CircuitBreaker",
        "5 simultaneous drifts (burst, streak=2)",
    );
    assert!(r.is_ok());
    assert_eq!(
        p.governance.risk.snapshot_level(),
        RiskLevel::CircuitBreaker
    );
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
    let actions = evaluate_actions(
        &mut state,
        RiskLevel::Cautious,
        &empty_drifts,
        recovery_time,
    );

    let has_recovery = actions.iter().any(|a| {
        matches!(a, ReconcilerAction::DeEscalate { target, .. } if *target == RiskLevel::Normal)
    });
    assert!(
        has_recovery,
        "should recover to Normal after 30 cycles + 15min"
    );

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
    let actions = evaluate_actions(&mut state, RiskLevel::CircuitBreaker, &[], 100_000_000);
    let has_de_escalate = actions
        .iter()
        .any(|a| matches!(a, ReconcilerAction::DeEscalate { .. }));
    assert!(
        !has_de_escalate,
        "evaluate_actions must never propose CB de-escalation"
    );
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
    assert!(
        action.is_some(),
        "10 REST failures should produce escalation"
    );
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
// 6-04 Scenario 7: MinorDrift does NOT reset clean cycle counter
// 6-04 場景 7：MinorDrift 不重設乾淨週期計數器
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_minor_drift_does_not_reset_clean_cycles() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    // First: escalate to Cautious via MajorDrift so we have something to recover from
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    state.pre_escalation_level = Some(RiskLevel::Normal);

    // Accumulate 20 clean cycles with 1ms spacing (wall-clock << 15min,
    // so recovery doesn't fire prematurely inside the loop)
    let empty: Vec<(String, DriftVerdict)> = vec![];
    for c in 0..20u64 {
        evaluate_actions(&mut state, RiskLevel::Cautious, &empty, t0 + 1 + c);
    }
    assert_eq!(state.clean_cycles_since_last_drift, 20);

    // Inject a MinorDrift — must NOT reset counter (MinorDrift is not action-triggering)
    let minor = vec![("BTCUSDT|Buy".into(), DriftVerdict::MinorDrift)];
    evaluate_actions(&mut state, RiskLevel::Cautious, &minor, t0 + 21);
    assert_eq!(
        state.clean_cycles_since_last_drift, 21,
        "MinorDrift must not reset clean cycle counter"
    );

    // Contrast: MajorDrift DOES reset counter
    let major = vec![("ETHUSDT|Sell".into(), DriftVerdict::MajorDrift)];
    evaluate_actions(&mut state, RiskLevel::Cautious, &major, t0 + 22);
    assert_eq!(
        state.clean_cycles_since_last_drift, 0,
        "MajorDrift must reset clean cycle counter"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// 6-04 Scenario 8: SideFlip triggers Cautious escalation
// 6-04 場景 8：SideFlip 觸發 Cautious 升級
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_sideflip_escalates_to_cautious() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::SideFlip)];

    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Cautious
    ));

    // Drive through handler
    let mut p = make_pipeline();
    let mut w = make_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    let r = drive_escalate(&mut p, &mut w, "Cautious", "side_flip BTCUSDT");
    assert!(r.is_ok());
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
}

// ═══════════════════════════════════════════════════════════════════════════
// 6-04 Scenario 9: Ghost escalates same as Orphan
// 6-04 場景 9：Ghost 與 Orphan 同級升級
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_ghost_escalates_to_cautious() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];

    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Cautious
    ));

    // Drive through handler to verify full chain (P0 E2 fix)
    // 驅動 handler 驗證完整鏈路（P0 E2 修復）
    let mut p = make_pipeline();
    let mut w = make_writer();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    let r = drive_escalate(&mut p, &mut w, "Cautious", "ghost BTCUSDT");
    assert!(r.is_ok());
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
}

// ═══════════════════════════════════════════════════════════════════════════
// 6-04 Scenario 10: Per-symbol cooldown blocks repeat escalation
// 6-04 場景 10：Per-symbol 冷卻阻止重複升級
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_per_symbol_cooldown_blocks_repeat() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];

    // First drift at t0 → escalation
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    assert!(!actions.is_empty());

    // Same symbol, same drift, within 30min cooldown → no action
    // (Already at Cautious, target would be Cautious, target <= current → skip)
    let actions2 = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, t0 + 60_000);
    let has_escalate = actions2
        .iter()
        .any(|a| matches!(a, ReconcilerAction::Escalate { .. }));
    assert!(
        !has_escalate,
        "per-symbol cooldown should prevent repeat escalation to same tier"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// 6-04 Scenario 11: Global cooldown limits rapid-fire escalation
// 6-04 場景 11：全局冷卻限制快速連續升級
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_global_cooldown_limits_rapid_fire() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    // First drift: BTCUSDT → Cautious
    let drifts1 = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts1, t0);
    assert!(!actions.is_empty());

    // Different symbol, persistent streak for 3 cycles → would target Defensive
    // But global cooldown (5min) blocks it if within window
    let drifts2 = vec![("ETHUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    // Force streak to 3 for ETHUSDT
    state.drift_streak.insert("ETHUSDT|Buy".into(), 2);
    let actions2 = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts2, t0 + 1000);
    let has_defensive = actions2.iter().any(|a| {
        matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Defensive)
    });
    assert!(
        !has_defensive,
        "global cooldown should block escalation within 5min"
    );

    // After global cooldown passes → should fire
    let actions3 = evaluate_actions(
        &mut state,
        RiskLevel::Cautious,
        &drifts2,
        t0 + GLOBAL_COOLDOWN_MS + 1,
    );
    let has_defensive3 = actions3.iter().any(|a| {
        matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Defensive)
    });
    assert!(
        has_defensive3,
        "should escalate after global cooldown expires"
    );
}

// ═══════════════════════════════════════════════════════════════════════════
// 6-04 Scenario 12: Multi-tier recovery path Defensive → Reduced → Cautious → Normal
// 6-04 場景 12：多級恢復路徑 Defensive → Reduced → Cautious → Normal 全程
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_full_recovery_defensive_to_normal() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;
    let empty: Vec<(String, DriftVerdict)> = vec![];

    // Setup: escalate to Defensive via persistent drift
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    for cycle in 0..PERSISTENT_DRIFT_CYCLES {
        let t = t0 + (cycle as u64) * (GLOBAL_COOLDOWN_MS + 1);
        evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t);
    }
    state.pre_escalation_level = Some(RiskLevel::Normal);

    // Pipeline to drive handlers
    let mut pipeline = make_pipeline();
    let mut writer = make_writer();
    pipeline.governance.risk.thresholds.min_hold_time_ms = 0;
    setup_escalate_to(&mut pipeline, RiskLevel::Defensive);

    // Recovery helper: accumulate clean cycles at `level` until DeEscalate fires,
    // then drive the de-escalation through the handler. Wall-clock requirement is
    // satisfied by spacing each cycle by 30s (matching real reconciler interval).
    // 恢復輔助：在指定 level 累積乾淨週期直到 DeEscalate 觸發，然後驅動 handler。
    let base_drift_ts = state.last_drift_seen_ms;
    let mut t = base_drift_ts + 1;
    let max_cycles = 200u32; // safety limit

    // Phase 1: Defensive → Reduced (20 cycles + 10 min)
    let mut found = false;
    for _ in 0..max_cycles {
        t += 30_000;
        let actions = evaluate_actions(&mut state, RiskLevel::Defensive, &empty, t);
        if let Some(a) = actions
            .iter()
            .find(|a| matches!(a, ReconcilerAction::DeEscalate { .. }))
        {
            assert!(
                matches!(a, ReconcilerAction::DeEscalate { target, .. } if *target == RiskLevel::Reduced)
            );
            found = true;
            break;
        }
    }
    assert!(found, "Defensive → Reduced recovery must fire");
    drive_de_escalate(&mut pipeline, &mut writer, "Reduced", "recovery").unwrap();
    assert_eq!(
        pipeline.governance.risk.snapshot_level(),
        RiskLevel::Reduced
    );

    // Phase 2: Reduced → Cautious (20 cycles + 10 min)
    found = false;
    for _ in 0..max_cycles {
        t += 30_000;
        let actions = evaluate_actions(&mut state, RiskLevel::Reduced, &empty, t);
        if let Some(a) = actions
            .iter()
            .find(|a| matches!(a, ReconcilerAction::DeEscalate { .. }))
        {
            assert!(
                matches!(a, ReconcilerAction::DeEscalate { target, .. } if *target == RiskLevel::Cautious)
            );
            found = true;
            break;
        }
    }
    assert!(found, "Reduced → Cautious recovery must fire");
    drive_de_escalate(&mut pipeline, &mut writer, "Cautious", "recovery").unwrap();
    assert_eq!(
        pipeline.governance.risk.snapshot_level(),
        RiskLevel::Cautious
    );

    // Phase 3: Cautious → Normal (30 cycles + 15 min)
    found = false;
    for _ in 0..max_cycles {
        t += 30_000;
        let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &empty, t);
        if let Some(a) = actions
            .iter()
            .find(|a| matches!(a, ReconcilerAction::DeEscalate { .. }))
        {
            assert!(
                matches!(a, ReconcilerAction::DeEscalate { target, .. } if *target == RiskLevel::Normal)
            );
            found = true;
            break;
        }
    }
    assert!(found, "Cautious → Normal recovery must fire");
    drive_de_escalate(&mut pipeline, &mut writer, "Normal", "recovery").unwrap();

    assert_eq!(pipeline.governance.risk.snapshot_level(), RiskLevel::Normal);
}

// ═══════════════════════════════════════════════════════════════════════════
// 6-04 Scenario 13: REST failure progressive tiers (10→Cautious, 30→Reduced, 60→Defensive)
// 6-04 場景 13：REST 失敗漸進升級（10→Cautious, 30→Reduced, 60→Defensive）
// ═══════════════════════════════════════════════════════════════════════════

#[test]
fn e2e_rest_failure_progressive_tiers() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    // Tier 1: 10 failures → Cautious
    state.consecutive_rest_failures = REST_FAILURE_TIER1_COUNT;
    let a1 = check_rest_failure_escalation(&mut state, RiskLevel::Normal, t0);
    assert!(
        matches!(a1, Some(ReconcilerAction::Escalate { target, .. }) if target == RiskLevel::Cautious)
    );

    // Tier 2: 30 failures → Reduced (from Cautious)
    state.consecutive_rest_failures = REST_FAILURE_TIER2_COUNT;
    let a2 =
        check_rest_failure_escalation(&mut state, RiskLevel::Cautious, t0 + GLOBAL_COOLDOWN_MS + 1);
    assert!(
        matches!(a2, Some(ReconcilerAction::Escalate { target, .. }) if target == RiskLevel::Reduced)
    );

    // Tier 3: 60 failures → Defensive (from Reduced)
    state.consecutive_rest_failures = REST_FAILURE_TIER3_COUNT;
    let a3 = check_rest_failure_escalation(
        &mut state,
        RiskLevel::Reduced,
        t0 + 2 * (GLOBAL_COOLDOWN_MS + 1),
    );
    assert!(
        matches!(a3, Some(ReconcilerAction::Escalate { target, .. }) if target == RiskLevel::Defensive)
    );

    // Already at target → no action
    state.consecutive_rest_failures = REST_FAILURE_TIER3_COUNT;
    let a4 = check_rest_failure_escalation(
        &mut state,
        RiskLevel::Defensive,
        t0 + 3 * (GLOBAL_COOLDOWN_MS + 1),
    );
    assert!(a4.is_none(), "should not escalate when already at target");
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario 14: Floor rule — recovery does not go below pre_escalation_level
// 場景 14：Floor rule — 恢復不會低於 pre_escalation_level
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
        let actions = evaluate_actions(&mut state, RiskLevel::Reduced, &empty, t);
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

// ═══════════════════════════════════════════════════════════════════════════
// 6-05 Stress Tests / 壓力測試
// ═══════════════════════════════════════════════════════════════════════════

/// 6-05-S1: 100 rapid cycles of alternating drift/clean — no panic, state consistent.
/// 6-05-S1：100 輪快速漂移/清除交替 — 不 panic，狀態一致。
#[test]
fn stress_100_cycles_rapid_drift_clean_alternation() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    let empty: Vec<(String, DriftVerdict)> = vec![];

    // Alternate drift/clean every cycle for 100 iterations.
    // Space each cycle by global cooldown + 1 to allow escalations.
    let mut current_level = RiskLevel::Normal;
    let cycle_gap = GLOBAL_COOLDOWN_MS + 1;

    for cycle in 0..100u64 {
        let t = t0 + cycle * cycle_gap;
        let input = if cycle % 2 == 0 { &drifts } else { &empty };
        let actions = evaluate_actions(&mut state, current_level, input, t);

        // Track level changes (simulate caller behavior)
        for action in &actions {
            match action {
                ReconcilerAction::Escalate { target, .. } => {
                    if *target > current_level {
                        if state.pre_escalation_level.is_none() {
                            state.pre_escalation_level = Some(current_level);
                        }
                        current_level = *target;
                    }
                }
                ReconcilerAction::DeEscalate { target, .. } => {
                    current_level = *target;
                }
                ReconcilerAction::CloseAll { .. } => {}
            }
        }
    }

    // Verify state invariants
    assert!(
        current_level <= RiskLevel::CircuitBreaker,
        "level must be a valid tier"
    );
    // Alternating drift/clean means streak never reaches 3 (persistent threshold),
    // so max level should not exceed Cautious.
    assert!(
        current_level <= RiskLevel::Cautious,
        "alternating drift/clean should never exceed Cautious, got {:?}",
        current_level
    );
}

/// 6-05-S2: 50 simultaneous symbols drifting — two consecutive burst cycles → CB, no panic.
/// FIX-B: first cycle → Defensive, second consecutive → CB + CloseAll.
/// 6-05-S2：50 個 symbol 同時漂移 — 兩次連續 burst → CB，不 panic。
#[test]
fn stress_50_symbols_simultaneous_drift() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    // Build 50 simultaneous drifts
    let drifts: Vec<(String, DriftVerdict)> = (0..50)
        .map(|i| (format!("SYM{i}USDT|Buy"), DriftVerdict::MajorDrift))
        .collect();

    // First burst cycle → Defensive (FIX-B: not CB on first burst)
    let actions1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    let has_defensive = actions1.iter().any(|a| {
        matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::Defensive)
    });
    assert!(
        has_defensive,
        "50 symbols first burst cycle must escalate to Defensive"
    );

    // Second consecutive burst cycle → CB + CloseAll
    let actions2 = evaluate_actions(&mut state, RiskLevel::Defensive, &drifts, 999_999_999);
    let has_cb = actions2.iter().any(|a| {
        matches!(a, ReconcilerAction::Escalate { target, .. } if *target == RiskLevel::CircuitBreaker)
    });
    let has_close_all = actions2
        .iter()
        .any(|a| matches!(a, ReconcilerAction::CloseAll { .. }));
    assert!(
        has_cb,
        "50 symbols must trigger CB on second consecutive burst"
    );
    assert!(
        has_close_all,
        "50 symbols must trigger CloseAll on second consecutive burst"
    );

    // State should have 50 drift streaks tracked
    assert_eq!(state.drift_streak.len(), 50);
}

/// 6-05-S3: Rapid escalation/de-escalation through full handler chain — no deadlock.
/// 6-05-S3：通過完整 handler 鏈快速升降 — 不死鎖。
#[test]
fn stress_rapid_handler_escalate_deescalate() {
    let mut pipeline = make_pipeline();
    let mut writer = make_writer();
    pipeline.governance.risk.thresholds.min_hold_time_ms = 0;

    // 20 rounds: escalate to Cautious, de-escalate to Normal
    for _ in 0..20 {
        let r = drive_escalate(&mut pipeline, &mut writer, "Cautious", "stress test drift");
        assert!(r.is_ok(), "escalate failed: {r:?}");
        assert_eq!(
            pipeline.governance.risk.snapshot_level(),
            RiskLevel::Cautious
        );

        let r = drive_de_escalate(&mut pipeline, &mut writer, "Normal", "stress test recovery");
        assert!(r.is_ok(), "de-escalate failed: {r:?}");
        assert_eq!(pipeline.governance.risk.snapshot_level(), RiskLevel::Normal);
    }
}

/// 6-05-S4: evaluate_actions performance — 1000 cycles with 10 symbols, must complete in <100ms.
/// 6-05-S4：evaluate_actions 性能 — 1000 輪 10 symbols，必須 <100ms 完成。
#[test]
fn stress_evaluate_actions_performance() {
    let mut state = ReconcilerState::new();
    let t0 = 100_000_000u64;

    let drifts: Vec<(String, DriftVerdict)> = (0..10)
        .map(|i| {
            let verdict = match i % 4 {
                0 => DriftVerdict::MajorDrift,
                1 => DriftVerdict::Orphan,
                2 => DriftVerdict::Ghost,
                _ => DriftVerdict::MinorDrift,
            };
            (format!("SYM{i}USDT|Buy"), verdict)
        })
        .collect();

    let start = std::time::Instant::now();
    for cycle in 0..1000u64 {
        let t = t0 + cycle * 30_000;
        let _ = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t);
    }
    let elapsed = start.elapsed();
    assert!(
        elapsed.as_millis() < 100,
        "1000 evaluate_actions calls took {}ms (limit: 100ms)",
        elapsed.as_millis()
    );
}

/// P0-0 RECONCILER-BURST-FIX end-to-end:
/// Simulate the 2026-04-15 incident — engine restart, warmup baseline vs stale
/// paper_state produces an "orphan storm" on first real tick (6 Ghost + 4 Orphan,
/// well beyond BURST_DRIFT_COUNT=5). Without the grace fix this escalates to
/// Defensive + CircuitBreaker. With the fix the reconciler stays silent for the
/// grace window, then after the window clean ticks keep governance at Normal.
///
/// P0-0 RECONCILER-BURST-FIX 端到端：復現 2026-04-15 事故 — 引擎重啟後首個真正
/// tick 觀察到 warmup baseline vs stale paper_state 帶來的「orphan storm」
/// (6 Ghost + 4 Orphan，遠超 BURST_DRIFT_COUNT=5)。無 grace 修復會升 Defensive +
/// CircuitBreaker；有 grace 修復則寬限期內 reconciler 靜默，窗口後 clean tick
/// 繼續讓治理保持 Normal。
#[test]
fn e2e_startup_grace_window_ignores_orphan_storm() {
    let mut state = ReconcilerState::new();
    let startup = 1_700_000_000_000u64;
    state.startup_ms = startup;

    // Orphan storm: 6 Ghost + 4 Orphan = 10 actionable drifts, far exceeds
    // BURST_DRIFT_COUNT=5.
    // Orphan 風暴：6 Ghost + 4 Orphan = 10 個 actionable drift，遠超 BURST_DRIFT_COUNT=5。
    let mut drifts: Vec<(String, DriftVerdict)> = (0..6)
        .map(|i| (format!("GHOST{i}USDT|Buy"), DriftVerdict::Ghost))
        .collect();
    drifts.extend((0..4).map(|i| (format!("ORPH{i}USDT|Sell"), DriftVerdict::Orphan)));

    // ── Inside grace window: storm must be suppressed, state must not advance.
    // ── 寬限期內：storm 必須被抑制，state 不可推進。
    for cycle in 0..10u64 {
        let now = startup + cycle * 30_000; // 0s..270s (< 5min)
        let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, now);
        assert!(
            actions.is_empty(),
            "cycle {cycle}: grace window must suppress all actions, got {:?}",
            actions
        );
    }
    assert!(
        state.drift_streak.is_empty(),
        "drift_streak must not advance during grace"
    );
    assert_eq!(
        state.burst_drift_streak, 0,
        "burst_drift_streak must not advance during grace"
    );
    assert_eq!(
        state.clean_cycles_since_last_drift, 0,
        "clean_cycles must not advance during grace"
    );

    // ── Boundary: within `STARTUP_GRACE_MS` still suppressed; just after,
    //    clean drifts (all MinorDrift) produce no escalation either, and the
    //    state transitions from "grace" → "post-grace normal operation".
    // ── 邊界：仍在 STARTUP_GRACE_MS 內被抑制；剛過寬限期後，clean drift (全 MinorDrift)
    //    也不會升級，state 從「寬限期」→「正常運作」平滑過渡。
    let within = startup + STARTUP_GRACE_MS - 1;
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, within);
    assert!(actions.is_empty(), "last-ms-in-grace must still suppress");

    // After the window, incident-style orphan storm would escalate; but a
    // realistic post-grace state has only MinorDrift (baseline reseed already
    // absorbed the residuals), so no escalation.
    // 寬限期結束後，事故式 orphan storm 會升級；但正常情境下寬限期結束時，baseline
    // reseed 已吸收殘留，只剩 MinorDrift，因此不升級。
    let post = startup + STARTUP_GRACE_MS + 30_000;
    let clean_minor: Vec<(String, DriftVerdict)> =
        vec![("BTCUSDT|Buy".into(), DriftVerdict::MinorDrift)];
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &clean_minor, post);
    assert!(
        actions.is_empty(),
        "post-grace MinorDrift must not escalate, got {:?}",
        actions
    );

    // ── REST failure escalation path must also be suppressed during grace.
    // ── REST failure 升級路徑也必須在寬限期內被抑制。
    let mut state2 = ReconcilerState::new();
    state2.startup_ms = startup;
    state2.consecutive_rest_failures = REST_FAILURE_TIER1_COUNT;
    let decision = check_rest_failure_escalation(&mut state2, RiskLevel::Normal, startup + 60_000);
    assert!(
        decision.is_none(),
        "REST tier-1 inside grace must not escalate, got {:?}",
        decision
    );

    // ── Legacy caller without startup_ms stamp keeps pre-P0-0 behaviour:
    //    orphan storm does escalate.
    // ── 舊調用方未設 startup_ms 保留 P0-0 前行為：orphan storm 照常升級。
    let mut legacy = ReconcilerState::new();
    assert_eq!(legacy.startup_ms, 0);
    let actions = evaluate_actions(&mut legacy, RiskLevel::Normal, &drifts, startup + 60_000);
    assert!(
        !actions.is_empty(),
        "legacy caller (startup_ms=0) must preserve pre-fix escalation"
    );
    assert!(
        actions
            .iter()
            .any(|a| matches!(a, ReconcilerAction::Escalate { .. })
                || matches!(a, ReconcilerAction::CloseAll { .. })),
        "legacy caller must still raise an Escalate / CloseAll action"
    );
}
