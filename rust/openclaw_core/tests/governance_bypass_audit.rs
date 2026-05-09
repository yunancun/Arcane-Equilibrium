//! Non-Production lease bypass audit coverage.
//!
//! Validation / Exploration profiles must not create real lease SM objects, but
//! the facade still emits one synthetic audit row so runtime healthchecks can
//! see that the lease facade path is alive.

use openclaw_core::governance_core::{
    GovernanceCore, GovernanceProfile, LeaseId, LeaseOutcome, LeaseTransitionMsg,
};

fn core_with_emit(
    profile: GovernanceProfile,
    engine_mode: &str,
) -> (
    GovernanceCore,
    std::sync::mpsc::Receiver<LeaseTransitionMsg>,
) {
    let mut core = GovernanceCore::new_with_profile(profile);
    let (tx, rx) = std::sync::mpsc::channel::<LeaseTransitionMsg>();
    core.set_lease_transition_tx(tx);
    core.set_engine_mode_tag(engine_mode.to_string());
    (core, rx)
}

#[test]
fn test_validation_bypass_emits_synthetic_audit_row_without_sm_object() {
    let (core, rx) = core_with_emit(GovernanceProfile::Validation, "live_demo");

    let lease = core
        .acquire_lease(
            "intent-validation-bypass-audit",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Validation,
            "facade_test",
        )
        .expect("Validation acquire returns Bypass Ok");

    assert_eq!(lease, LeaseId::Bypass);
    assert_eq!(
        core.lease.lock().len(),
        0,
        "Validation bypass must not create a lease SM object"
    );

    let msgs: Vec<_> = rx.try_iter().collect();
    assert_eq!(msgs.len(), 1, "bypass emits one synthetic audit row");
    let msg = &msgs[0];
    assert!(msg.transition_id.starts_with("tx:"));
    assert!(msg.lease_id.starts_with("bypass:"));
    assert_eq!(msg.from_state, None);
    assert_eq!(msg.to_state, "BYPASS");
    assert_eq!(msg.event, "non_production_bypass");
    assert_eq!(msg.initiator, "rust_facade::facade_test");
    assert_eq!(msg.profile, "Validation");
    assert_eq!(msg.engine_mode, "live_demo");
    assert_eq!(msg.context_id, "intent-validation-bypass-audit");
    assert!(msg.ts_ms > 0);
    assert!(msg
        .reason_codes
        .iter()
        .any(|reason| reason == "lease_sm_bypassed"));

    core.release_lease(&lease, LeaseOutcome::Consumed)
        .expect("release_lease(Bypass) remains a no-op");
    assert_eq!(
        rx.try_iter().count(),
        0,
        "release_lease(Bypass) must not emit a second synthetic row"
    );
}

#[test]
fn test_exploration_bypass_emits_profile_specific_audit_row() {
    let (core, rx) = core_with_emit(GovernanceProfile::Exploration, "demo");

    let lease = core
        .acquire_lease(
            "intent-exploration-bypass-audit",
            "TRADE_ENTRY",
            30_000,
            GovernanceProfile::Exploration,
            "router",
        )
        .expect("Exploration acquire returns Bypass Ok");

    assert_eq!(lease, LeaseId::Bypass);
    assert_eq!(core.lease.lock().len(), 0);

    let msg = rx
        .try_recv()
        .expect("Exploration bypass emits one synthetic audit row");
    assert_eq!(msg.to_state, "BYPASS");
    assert_eq!(msg.profile, "Exploration");
    assert_eq!(msg.engine_mode, "demo");
    assert_eq!(msg.context_id, "intent-exploration-bypass-audit");
    assert!(rx.try_recv().is_err(), "exactly one bypass audit row");
}
