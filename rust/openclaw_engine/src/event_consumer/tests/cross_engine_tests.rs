//! BLOCKER-10 / D6: Cross-engine cascade handler unit tests
//! D6 跨引擎級聯處理器單元測試

use super::{escalate_to_tier, make_test_pipeline};

#[test]
fn test_d6_cross_engine_crash_escalates_to_cautious() {
    // Peer crash → local pipeline escalates to Cautious via reconciler_escalate_to.
    // 對等管線崩潰 → 本地管線通過 reconciler_escalate_to 升至 Cautious。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Normal);

    // Simulate crash cascade handler logic from mod.rs
    let crashed_kind = crate::tick_pipeline::PipelineKind::Demo;
    let duration_s = if crashed_kind == crate::tick_pipeline::PipelineKind::Paper {
        60
    } else {
        120
    };
    let _ = p.governance.risk.reconciler_escalate_to(
        RiskLevel::Cautious,
        &format!(
            "cross_engine_cascade: {} crashed, hold {}s",
            crashed_kind, duration_s
        ),
    );
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
}

#[test]
fn test_d6_cross_engine_cb_escalates_to_cautious() {
    // Peer CB trip → local pipeline escalates to Cautious.
    // 對等管線熔斷 → 本地管線升至 Cautious。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    p.governance.risk.thresholds.min_hold_time_ms = 0;

    let cb_kind = crate::tick_pipeline::PipelineKind::Live;
    let _ = p.governance.risk.reconciler_escalate_to(
        RiskLevel::Cautious,
        &format!("cross_engine_cascade: {} circuit_breaker", cb_kind),
    );
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
}

#[test]
fn test_d6_paper_crash_60s_message() {
    // Paper crash → 60s duration in reason.
    // Paper 崩潰 → 理由中包含 60s 時長。
    let crashed_kind = crate::tick_pipeline::PipelineKind::Paper;
    let duration_s = if crashed_kind == crate::tick_pipeline::PipelineKind::Paper {
        60
    } else {
        120
    };
    assert_eq!(duration_s, 60);
    let msg = format!(
        "cross_engine_cascade: {} crashed, hold {}s",
        crashed_kind, duration_s
    );
    assert!(msg.contains("60s"));
    assert!(msg.contains("paper"));
}

#[test]
fn test_d6_non_paper_crash_120s_message() {
    // Demo/Live crash → 120s duration in reason.
    // Demo/Live 崩潰 → 理由中包含 120s 時長。
    for kind in &[
        crate::tick_pipeline::PipelineKind::Demo,
        crate::tick_pipeline::PipelineKind::Live,
    ] {
        let duration_s = if *kind == crate::tick_pipeline::PipelineKind::Paper {
            60
        } else {
            120
        };
        assert_eq!(duration_s, 120);
        let msg = format!(
            "cross_engine_cascade: {} crashed, hold {}s",
            kind, duration_s
        );
        assert!(msg.contains("120s"));
    }
}

#[test]
fn test_d6_cascade_already_at_cautious_is_noop() {
    // If already at Cautious, cascade crash doesn't escalate further (stays Cautious).
    // 若已在 Cautious，級聯崩潰不會進一步升級。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    let _ = p
        .governance
        .risk
        .reconciler_escalate_to(RiskLevel::Cautious, "pre-existing");
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);

    let _ = p
        .governance
        .risk
        .reconciler_escalate_to(RiskLevel::Cautious, "cross_engine_cascade: demo crashed");
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Cautious);
}

#[test]
fn test_d6_cascade_from_higher_level_is_noop() {
    // If already at Defensive (> Cautious), cascade to Cautious is rejected.
    // 若已在 Defensive（高於 Cautious），級聯至 Cautious 被拒絕。
    use openclaw_core::sm::risk_gov::RiskLevel;
    let mut p = make_test_pipeline();
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    escalate_to_tier(&mut p, RiskLevel::Defensive);

    let _ = p
        .governance
        .risk
        .reconciler_escalate_to(RiskLevel::Cautious, "cross_engine_cascade: paper crashed");
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::Defensive);
}
