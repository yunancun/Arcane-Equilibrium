use super::*;
use crate::position_manager::PositionInfo;
use std::collections::HashMap;
use std::sync::Arc;

fn pv(symbol: &str, side: &str, qty: f64) -> PositionView {
    PositionView {
        symbol: symbol.to_string(),
        side: side.to_string(),
        qty,
    }
}

#[test]
fn match_when_both_none() {
    assert_eq!(classify(None, None, 0.05), DriftVerdict::Match);
}

#[test]
fn orphan_when_only_current() {
    let cur = pv("BTCUSDT", "Buy", 0.1);
    assert_eq!(classify(None, Some(&cur), 0.05), DriftVerdict::Orphan);
}

#[test]
fn ghost_when_only_baseline() {
    let base = pv("BTCUSDT", "Buy", 0.1);
    assert_eq!(classify(Some(&base), None, 0.05), DriftVerdict::Ghost);
}

#[test]
fn match_when_qty_equal() {
    let a = pv("BTCUSDT", "Buy", 0.1);
    let b = pv("BTCUSDT", "Buy", 0.1);
    assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::Match);
}

#[test]
fn minor_drift_below_threshold() {
    let a = pv("BTCUSDT", "Buy", 1.000);
    let b = pv("BTCUSDT", "Buy", 1.020); // 2% change
    assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::MinorDrift);
}

#[test]
fn major_drift_above_threshold() {
    // 1.06 vs 1.0: delta_ratio = 0.06 / 1.06 = 5.66% > 5% → MajorDrift.
    // 1.06 對 1.0：delta_ratio = 5.66%，超過 5% 閾值。
    let a = pv("BTCUSDT", "Buy", 1.000);
    let b = pv("BTCUSDT", "Buy", 1.060);
    assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::MajorDrift);
}

#[test]
fn side_flip_on_direction_change() {
    let a = pv("BTCUSDT", "Buy", 0.1);
    let b = pv("BTCUSDT", "Sell", 0.1);
    assert_eq!(classify(Some(&a), Some(&b), 0.05), DriftVerdict::SideFlip);
}

#[test]
fn build_view_map_skips_empty() {
    let positions = vec![
        PositionInfo {
            symbol: "BTCUSDT".into(),
            side: "Buy".into(),
            size: 0.5,
            avg_price: 50000.0,
            mark_price: 50100.0,
            unrealised_pnl: 50.0,
            leverage: 1.0,
            liq_price: 0.0,
            take_profit: 0.0,
            stop_loss: 0.0,
            position_idx: 0,
            trailing_stop: 0.0,
            position_value: 25000.0,
            cum_realised_pnl: 0.0,
            created_time: "".into(),
            updated_time: "".into(),
        },
        PositionInfo {
            symbol: "ETHUSDT".into(),
            side: "None".into(),
            size: 0.0,
            avg_price: 0.0,
            mark_price: 0.0,
            unrealised_pnl: 0.0,
            leverage: 0.0,
            liq_price: 0.0,
            take_profit: 0.0,
            stop_loss: 0.0,
            position_idx: 0,
            trailing_stop: 0.0,
            position_value: 0.0,
            cum_realised_pnl: 0.0,
            created_time: "".into(),
            updated_time: "".into(),
        },
    ];
    let map = build_view_map(&positions);
    assert_eq!(map.len(), 1);
    assert!(map.contains_key("BTCUSDT|Buy"));
}

#[test]
fn is_drift_classification() {
    assert!(!DriftVerdict::Match.is_drift());
    assert!(DriftVerdict::MinorDrift.is_drift());
    assert!(DriftVerdict::MajorDrift.is_drift());
    assert!(DriftVerdict::SideFlip.is_drift());
    assert!(DriftVerdict::Orphan.is_drift());
    assert!(DriftVerdict::Ghost.is_drift());
}

// ── Phase 6: evaluate_actions tests ──

fn make_state() -> ReconcilerState {
    ReconcilerState::new()
}

#[test]
fn phase6_single_major_drift_escalates_to_cautious() {
    let mut state = make_state();
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::Escalate {
            target: RiskLevel::Cautious,
            ..
        }
    ));
}

#[test]
fn phase6_single_ghost_escalates_to_cautious() {
    let mut state = make_state();
    let drifts = vec![("ETHUSDT|Buy".into(), DriftVerdict::Ghost)];
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::Escalate {
            target: RiskLevel::Cautious,
            ..
        }
    ));
}

#[test]
fn phase6_single_orphan_escalates_to_cautious() {
    let mut state = make_state();
    let drifts = vec![("XRPUSDT|Sell".into(), DriftVerdict::Orphan)];
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::Escalate {
            target: RiskLevel::Cautious,
            ..
        }
    ));
}

#[test]
fn phase6_minor_drift_no_action() {
    let mut state = make_state();
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MinorDrift)];
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert!(actions.is_empty());
}

#[test]
fn phase6_minor_drift_does_not_reset_clean_counter() {
    let mut state = make_state();
    state.clean_cycles_since_last_drift = 10;
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MinorDrift)];
    evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    // MinorDrift should increment clean counter (it's not actionable)
    assert_eq!(state.clean_cycles_since_last_drift, 11);
}

#[test]
fn phase6_persistent_drift_3_cycles_to_defensive() {
    let mut state = make_state();
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    let t0 = 100_000_000u64; // large enough base to avoid cooldown from epoch
                             // Cycle 1: escalate to Cautious
    let a1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    assert!(matches!(
        &a1[0],
        ReconcilerAction::Escalate {
            target: RiskLevel::Cautious,
            ..
        }
    ));
    // Cycle 2: streak=2 < 3, Cautious→Cautious is no-op
    let a2 = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, t0 + 30_000);
    assert!(a2.is_empty());
    // Cycle 3: streak=3 → Defensive. Persistent drift (≥3 cycles) bypasses
    // per-symbol cooldown (QC audit fix), only needs global 5min cooldown.
    // Use t0 + GLOBAL_COOLDOWN_MS + 1 (not the 30min per-symbol cooldown).
    let a3 = evaluate_actions(
        &mut state,
        RiskLevel::Cautious,
        &drifts,
        t0 + GLOBAL_COOLDOWN_MS + 1,
    );
    assert_eq!(a3.len(), 1);
    assert!(matches!(
        &a3[0],
        ReconcilerAction::Escalate {
            target: RiskLevel::Defensive,
            ..
        }
    ));
}

/// FIX-B: First burst cycle → Defensive (not CB). Prevents single API-sync hiccup from
/// immediately tripping CB (e.g. IPC close_all + delayed Bybit REST response).
/// FIX-B：第一次 burst → Defensive（非 CB），防止 IPC close_all 後 REST 延遲誤觸 CB。
#[test]
fn phase6_burst_5_drifts_first_cycle_to_defensive_not_cb() {
    let mut state = make_state();
    let drifts = vec![
        ("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift),
        ("ETHUSDT|Buy".into(), DriftVerdict::Orphan),
        ("XRPUSDT|Sell".into(), DriftVerdict::Ghost),
        ("SOLUSDT|Buy".into(), DriftVerdict::MajorDrift),
        ("DOGEUSDT|Buy".into(), DriftVerdict::Orphan),
    ];
    // First cycle with 5 simultaneous drifts → Defensive (not CB)
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert_eq!(
        actions.len(),
        1,
        "first burst cycle must produce exactly 1 action (Escalate to Defensive)"
    );
    assert!(
        matches!(
            &actions[0],
            ReconcilerAction::Escalate {
                target: RiskLevel::Defensive,
                ..
            }
        ),
        "first burst must escalate to Defensive, got: {:?}",
        &actions[0]
    );
    assert_eq!(state.burst_drift_streak, 1);
}

/// FIX-B: Two consecutive burst cycles → CircuitBreaker + CloseAll.
/// FIX-B：連續兩個 burst 週期 → CircuitBreaker + 全平倉。
#[test]
fn phase6_burst_5_drifts_two_consecutive_cycles_to_circuit_breaker_and_close_all() {
    let mut state = make_state();
    let drifts = vec![
        ("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift),
        ("ETHUSDT|Buy".into(), DriftVerdict::Orphan),
        ("XRPUSDT|Sell".into(), DriftVerdict::Ghost),
        ("SOLUSDT|Buy".into(), DriftVerdict::MajorDrift),
        ("DOGEUSDT|Buy".into(), DriftVerdict::Orphan),
    ];
    // First cycle: Normal → Defensive (streak=1). Use far-future ts to bypass cooldowns.
    let actions1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert!(matches!(
        &actions1[0],
        ReconcilerAction::Escalate {
            target: RiskLevel::Defensive,
            ..
        }
    ));
    // Second consecutive cycle: Defensive → CircuitBreaker + CloseAll (streak=2)
    let actions2 = evaluate_actions(&mut state, RiskLevel::Defensive, &drifts, 999_999_999);
    assert_eq!(actions2.len(), 2);
    assert!(
        matches!(
            &actions2[0],
            ReconcilerAction::Escalate {
                target: RiskLevel::CircuitBreaker,
                ..
            }
        ),
        "second consecutive burst must escalate to CB"
    );
    assert!(matches!(&actions2[1], ReconcilerAction::CloseAll { .. }));
    assert_eq!(state.burst_drift_streak, 2);
}

#[test]
fn phase6_no_escalation_when_already_at_target() {
    let mut state = make_state();
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    // Already at Cautious — single drift targets Cautious, so no escalation
    let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, 1_000_000);
    assert!(actions.is_empty());
}

#[test]
fn phase6_per_symbol_cooldown_blocks_repeat() {
    let mut state = make_state();
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    // First escalation
    let a1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert_eq!(a1.len(), 1);
    // Second attempt within 30min cooldown — blocked (target Cautious == current Cautious anyway)
    // But even if we reset to Normal, the per-symbol cooldown should block
    let a2 = evaluate_actions(
        &mut state,
        RiskLevel::Normal,
        &drifts,
        1_000_000 + GLOBAL_COOLDOWN_MS + 1,
    );
    // per-symbol cooldown of 30min not met
    assert!(a2.is_empty());
}

#[test]
fn phase6_global_cooldown_blocks_rapid_fire() {
    let mut state = make_state();
    let drifts_a = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    let drifts_b = vec![("ETHUSDT|Buy".into(), DriftVerdict::Ghost)];
    // First escalation from drift A
    let a1 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts_a, 1_000_000);
    assert_eq!(a1.len(), 1);
    // Different symbol but within global 5min cooldown
    let a2 = evaluate_actions(&mut state, RiskLevel::Normal, &drifts_b, 1_000_000 + 1000);
    assert!(a2.is_empty());
}

#[test]
fn phase6_recovery_cautious_to_normal() {
    let mut state = make_state();
    state.pre_escalation_level = Some(RiskLevel::Normal);
    state.clean_cycles_since_last_drift = RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL;
    // Set last_drift_seen_ms so wall-clock requirement is met
    let now = 1_000_000 + RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS + 1;
    state.last_drift_seen_ms = 1_000_000;
    let drifts: Vec<(String, DriftVerdict)> = vec![];
    let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, now);
    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::DeEscalate {
            target: RiskLevel::Normal,
            ..
        }
    ));
    // Floor should be cleared since we reached it
    assert!(state.pre_escalation_level.is_none());
}

#[test]
fn phase6_recovery_wall_clock_not_met() {
    let mut state = make_state();
    state.pre_escalation_level = Some(RiskLevel::Normal);
    state.clean_cycles_since_last_drift = RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL;
    state.last_drift_seen_ms = 1_000_000;
    // Wall clock not met (only 5 min elapsed, need 15 min)
    let now = 1_000_000 + 5 * 60 * 1000;
    let drifts: Vec<(String, DriftVerdict)> = vec![];
    let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, now);
    assert!(actions.is_empty());
}

#[test]
fn phase6_recovery_floor_prevents_over_recovery() {
    let mut state = make_state();
    // Drawdown had already pushed to Cautious before reconciler escalated to Reduced
    state.pre_escalation_level = Some(RiskLevel::Cautious);
    state.clean_cycles_since_last_drift = RECOVERY_CYCLES_REDUCED_TO_CAUTIOUS;
    state.last_drift_seen_ms = 1_000_000;
    let now = 1_000_000 + RECOVERY_WALL_REDUCED_TO_CAUTIOUS_MS + 1;
    let drifts: Vec<(String, DriftVerdict)> = vec![];
    let actions = evaluate_actions(&mut state, RiskLevel::Reduced, &drifts, now);
    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::DeEscalate {
            target: RiskLevel::Cautious,
            ..
        }
    ));
    // Floor cleared — we've reached it
    assert!(state.pre_escalation_level.is_none());
}

#[test]
fn phase6_cb_no_auto_recovery() {
    let mut state = make_state();
    state.pre_escalation_level = Some(RiskLevel::Normal);
    state.clean_cycles_since_last_drift = 100;
    state.last_drift_seen_ms = 0;
    let drifts: Vec<(String, DriftVerdict)> = vec![];
    // CB should never auto-recover
    let actions = evaluate_actions(&mut state, RiskLevel::CircuitBreaker, &drifts, 999_999_999);
    assert!(actions.is_empty());
}

#[test]
fn phase6_rest_failure_tier1_escalation() {
    let mut state = make_state();
    state.consecutive_rest_failures = REST_FAILURE_TIER1_COUNT;
    let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
    assert!(action.is_some());
    assert!(matches!(
        action.unwrap(),
        ReconcilerAction::Escalate {
            target: RiskLevel::Cautious,
            ..
        }
    ));
}

#[test]
fn phase6_rest_failure_tier2_escalation() {
    let mut state = make_state();
    state.consecutive_rest_failures = REST_FAILURE_TIER2_COUNT;
    let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
    assert!(action.is_some());
    assert!(matches!(
        action.unwrap(),
        ReconcilerAction::Escalate {
            target: RiskLevel::Reduced,
            ..
        }
    ));
}

#[test]
fn phase6_rest_failure_tier3_escalation() {
    let mut state = make_state();
    state.consecutive_rest_failures = REST_FAILURE_TIER3_COUNT;
    let action = check_rest_failure_escalation(&mut state, RiskLevel::Normal, 1_000_000);
    assert!(action.is_some());
    assert!(matches!(
        action.unwrap(),
        ReconcilerAction::Escalate {
            target: RiskLevel::Defensive,
            ..
        }
    ));
}

#[test]
fn phase6_rest_failure_no_escalation_when_at_target() {
    let mut state = make_state();
    state.consecutive_rest_failures = REST_FAILURE_TIER1_COUNT;
    let action = check_rest_failure_escalation(&mut state, RiskLevel::Cautious, 1_000_000);
    assert!(action.is_none());
    // Tier2 but already at Reduced → no action
    state.consecutive_rest_failures = REST_FAILURE_TIER2_COUNT;
    let action2 = check_rest_failure_escalation(&mut state, RiskLevel::Reduced, 2_000_000);
    assert!(action2.is_none());
}

#[test]
fn phase6_pre_escalation_level_not_set_by_evaluate_actions() {
    // After Finding 6 fix: evaluate_actions no longer sets pre_escalation_level.
    // The caller (main loop) sets it after successful dispatch.
    // Finding 6 修復：evaluate_actions 不再設置 pre_escalation_level，
    // 由調用方在成功分發後設置。
    let mut state = make_state();
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    assert!(state.pre_escalation_level.is_none());
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert!(!actions.is_empty()); // escalation was produced
    assert!(state.pre_escalation_level.is_none()); // but floor NOT set yet
}

#[test]
fn phase6_side_flip_escalates_to_cautious() {
    let mut state = make_state();
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::SideFlip)];
    let actions = evaluate_actions(&mut state, RiskLevel::Normal, &drifts, 1_000_000);
    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::Escalate {
            target: RiskLevel::Cautious,
            ..
        }
    ));
}

#[test]
fn phase6_side_flip_kind_str() {
    assert_eq!(DriftVerdict::SideFlip.kind_str(), "side_flip");
}

// ── QC audit fix tests ─────────────────────────────────────

#[test]
fn phase6_staleness_reseed_triggers_after_long_rest_outage() {
    // 6-RC-9 fix: after a long REST outage (>10min), the first successful
    // fetch should reseed baseline, not classify against stale data.
    // QC 審計修復：長時間 REST 中斷後首次成功應重播種。
    let mut state = make_state();
    // Simulate previous success 15 minutes ago
    let t_prev = 100_000_000u64;
    state.last_successful_fetch_ms = t_prev;
    // Current time is 15 minutes later (> STALENESS_THRESHOLD_MS = 10min)
    let now = t_prev + 15 * 60 * 1000;
    let prev_fetch = state.last_successful_fetch_ms;
    let stale = prev_fetch > 0 && now.saturating_sub(prev_fetch) > STALENESS_THRESHOLD_MS;
    assert!(
        stale,
        "baseline should be detected as stale after 15min gap"
    );
    // After updating, the new value prevents future false staleness
    state.last_successful_fetch_ms = now;
    let stale2 = now.saturating_sub(state.last_successful_fetch_ms) > STALENESS_THRESHOLD_MS;
    assert!(!stale2, "should not be stale immediately after update");
}

#[test]
fn phase6_empty_flat_cycle_is_clean_not_reseed() {
    assert!(
        !should_reseed_baseline_before_classify(false, true, true),
        "empty baseline + empty current must reach evaluate_actions so clean-cycle recovery can progress"
    );
}

#[test]
fn phase6_empty_baseline_with_positions_still_reseeds() {
    assert!(
        should_reseed_baseline_before_classify(false, true, false),
        "first non-empty current view against an empty baseline must still reseed to avoid cold-start orphans"
    );
}

#[test]
fn phase6_stale_baseline_reseeds_even_when_current_empty() {
    assert!(
        should_reseed_baseline_before_classify(true, true, true),
        "staleness policy remains authoritative even if both views are empty"
    );
}

#[test]
fn phase6_flat_empty_cycle_allows_cautious_recovery() {
    let mut state = make_state();
    state.pre_escalation_level = Some(RiskLevel::Normal);
    state.clean_cycles_since_last_drift = RECOVERY_CYCLES_CAUTIOUS_TO_NORMAL;
    state.last_drift_seen_ms = 1_000_000;
    let now = 1_000_000 + RECOVERY_WALL_CAUTIOUS_TO_NORMAL_MS + 1;

    assert!(!should_reseed_baseline_before_classify(false, true, true));
    let drifts: Vec<(String, DriftVerdict)> = vec![];
    let actions = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, now);

    assert_eq!(actions.len(), 1);
    assert!(matches!(
        &actions[0],
        ReconcilerAction::DeEscalate {
            target: RiskLevel::Normal,
            ..
        }
    ));
}

#[test]
fn phase6_persistent_drift_bypasses_per_symbol_cooldown() {
    // QC audit fix: persistent drift (streak ≥ 3) to Defensive should
    // bypass per-symbol 30min cooldown, only need global 5min cooldown.
    // QC 審計修復：持續漂移到 Defensive 繞過 per-symbol 冷卻。
    let mut state = make_state();
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)];
    let t0 = 100_000_000u64;
    // Cycle 1: escalate Normal → Cautious
    evaluate_actions(&mut state, RiskLevel::Normal, &drifts, t0);
    // Cycle 2: streak=2, no-op (target=Cautious = current)
    evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, t0 + 30_000);
    // Cycle 3: streak=3 → Defensive. Only 5min+1ms after cycle 1.
    // This is far less than PER_SYMBOL_COOLDOWN_MS (30min), proving bypass.
    let t3 = t0 + GLOBAL_COOLDOWN_MS + 1;
    assert!(
        t3 - t0 < PER_SYMBOL_COOLDOWN_MS,
        "must be within per-symbol cooldown window"
    );
    let a3 = evaluate_actions(&mut state, RiskLevel::Cautious, &drifts, t3);
    assert_eq!(a3.len(), 1);
    assert!(
        matches!(
            &a3[0],
            ReconcilerAction::Escalate {
                target: RiskLevel::Defensive,
                ..
            }
        ),
        "persistent drift should reach Defensive despite per-symbol cooldown"
    );
}

// ── ORPHAN-ADOPT-1 FUP: engine-owned suppression ───────────────────────────

/// Build a minimal `OrphanHandlerConfig` with `BTCUSDT` in the active universe
/// and a caller-supplied positions_mirror. Kept local to these two tests so the
/// intent stays obvious.
/// 構建最小 OrphanHandlerConfig，BTCUSDT 活躍、鏡像由呼叫方提供。
fn build_orphan_cfg_for_test(
    mirror: Arc<parking_lot::RwLock<HashMap<String, bool>>>,
) -> OrphanHandlerConfig {
    use crate::edge_estimates::EdgeEstimates;
    use crate::scanner::registry::SymbolRegistry;
    OrphanHandlerConfig {
        symbol_registry: Arc::new(SymbolRegistry::new(
            vec!["BTCUSDT".into()],
            vec!["BTCUSDT".into()],
        )),
        edge_estimates: Arc::new(parking_lot::RwLock::new(EdgeEstimates::default())),
        get_max_notional: Arc::new(|| 1_000_000.0),
        engine_positions_mirror: mirror,
    }
}

fn pi(symbol: &str, side: &str) -> PositionInfo {
    PositionInfo {
        symbol: symbol.into(),
        side: side.into(),
        size: 0.01,
        avg_price: 50_000.0,
        mark_price: 50_100.0,
        unrealised_pnl: 0.0,
        leverage: 1.0,
        liq_price: 0.0,
        take_profit: 0.0,
        stop_loss: 0.0,
        position_idx: 0,
        trailing_stop: 0.0,
        position_value: 501.0,
        cum_realised_pnl: 0.0,
        created_time: String::new(),
        updated_time: String::new(),
    }
}

#[test]
fn orphan_suppressed_when_engine_owns_position() {
    // ORPHAN-ADOPT-1 FUP: reconciler's 30s baseline lags fresh strategy fills.
    // When the engine has just opened BTCUSDT long, the next REST snapshot
    // still shows it as an Orphan against the pre-fill baseline. Suppression:
    // if `(symbol, is_long)` is in the engine's mirror, drop the Orphan —
    // no close dispatched, no dedup stamp, no evidence to evaluate_actions.
    // 驗證：鏡像命中則 Orphan 直接捨棄，不平倉、不去重戳記、不升級。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true);
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));

    let raw_positions = vec![pi("BTCUSDT", "Buy")];
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Orphan)];
    let mut state = make_state();
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    let kept = process_orphans(
        drifts,
        &raw_positions,
        &oh_cfg,
        RiskLevel::Normal,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        1_000_000,
    );

    assert!(
        kept.is_empty(),
        "suppressed orphan must not be kept for evaluate_actions"
    );
    assert!(
        rx.try_recv().is_err(),
        "no PipelineCommand should be dispatched"
    );
    assert!(
        state.pending_orphan_closes.is_empty(),
        "suppression fires before dedup stamp — pending_orphan_closes must stay empty"
    );
}

#[test]
fn orphan_dispatched_when_engine_side_mismatches() {
    // Sanity / inverse of the above: mirror holds BTCUSDT LONG, but Bybit
    // reports a SHORT. Directions differ → this is NOT the engine's own
    // fill, suppression must NOT fire, and the normal handler path runs
    // (Stage C → SoftConservative close → CloseSymbol dispatched).
    // 反向驗證：鏡像為多單、Bybit 為空單，不觸發抑制，走正常平倉路徑。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true);
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));

    let raw_positions = vec![pi("BTCUSDT", "Sell")];
    let drifts = vec![("BTCUSDT|Sell".into(), DriftVerdict::Orphan)];
    let mut state = make_state();
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    let _ = process_orphans(
        drifts,
        &raw_positions,
        &oh_cfg,
        RiskLevel::Normal,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        1_000_000,
    );

    let cmd = rx
        .try_recv()
        .expect("orphan must be dispatched when engine doesn't own the same direction");
    match cmd {
        crate::tick_pipeline::PipelineCommand::CloseSymbol {
            symbol,
            hint_is_long,
            ..
        } => {
            assert_eq!(symbol, "BTCUSDT");
            assert_eq!(hint_is_long, Some(false), "side=Sell → hint_is_long=false");
        }
        other => panic!("expected CloseSymbol, got {:?}", other),
    }
}

// ── P2-110017-D2-RECONCILE: process_ghosts converge tests ───────────────────
//
// 安全核心：Ghost 收斂 = 跨「本地 truth ↔ exchange truth」刪本地倉。誤刪真倉
// = 災難（Root Principle 5）。下列測試對抗性覆蓋收斂 AND 條件 S-1..S-5。

/// Helper: pre-seed `state.last_ghost_keys` so the 2-cycle streak (S-5) is met,
/// and seed `state.baseline` so the audit baseline_qty is non-zero.
/// 預植 last_ghost_keys 滿足 2-cycle streak + baseline 供 audit qty。
fn make_ghost_state_streak_met(key: &str) -> ReconcilerState {
    let mut state = make_state();
    state.last_ghost_keys.insert(key.to_string());
    state
        .baseline
        .insert(key.to_string(), pv("BTCUSDT", "Buy", 0.05));
    state
}

/// round 2 mock 點查驗證器工廠：對任一 symbol 恆回固定 `GhostPointQuery`。
/// 用於三分支對抗性驗證 S-6 gate；不需真實 PositionManager / BybitRestClient。
fn pq_const(result: GhostPointQuery) -> impl Fn(String) -> std::future::Ready<GhostPointQuery> {
    move |_symbol: String| std::future::ready(result)
}

#[tokio::test]
async fn ghost_converged_happy_path_dispatches_converge_exchange_zero() {
    // S-1 mirror 有倉（提供 is_long）+ S-2/S-3/S-4 由 Ghost verdict 表達（本函數
    // 只在 Ok-fetch arm 被呼叫，Ghost = Bybit 確認 size==0）+ S-5 streak 已滿
    // → 派 ConvergeExchangeZero，Ghost 從 kept 移除。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true); // 本地多單
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_ghost_state_streak_met("BTCUSDT|Buy");
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    // S-6 點查回 ConfirmedZero（真 Ghost）→ happy path 收斂。
    let kept = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;

    assert!(
        kept.is_empty(),
        "converged ghost must be removed from drifts (no double escalation)"
    );
    let cmd = rx
        .try_recv()
        .expect("ConvergeExchangeZero must be dispatched on happy path");
    match cmd {
        crate::tick_pipeline::PipelineCommand::ConvergeExchangeZero {
            symbol, is_long, ..
        } => {
            assert_eq!(symbol, "BTCUSDT");
            assert!(is_long, "is_long must come from engine mirror (Buy=true)");
        }
        other => panic!("expected ConvergeExchangeZero, got {:?}", other),
    }
}

#[tokio::test]
async fn ghost_not_converged_when_streak_not_met_first_cycle() {
    // 誤刪防護（S-5）：本輪首見 Ghost（last_ghost_keys 不含此 key）→ 不收斂。
    // C-3 結算 race：cycle N+1 Bybit 短暫不回某 symbol 不可立即誤刪真倉。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true);
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_state(); // last_ghost_keys 空 = streak 未滿
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    // streak 未滿在點查前先擋；即使點查回 ConfirmedZero 也不得收斂。
    let kept = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;

    assert_eq!(
        kept.len(),
        1,
        "first-cycle ghost must be kept (deferred), not converged"
    );
    assert!(
        rx.try_recv().is_err(),
        "no converge command must be dispatched on first cycle (streak unmet)"
    );
    assert!(
        state.last_ghost_keys.contains("BTCUSDT|Buy"),
        "this cycle's ghost key must be recorded so the next cycle can meet streak"
    );
}

#[tokio::test]
async fn ghost_not_converged_when_engine_mirror_has_no_position() {
    // 誤刪防護（S-1）：mirror 不含該 symbol（引擎本地無倉/無方向）→ 不收斂。
    // 對應「Bybit 回 size>0 但引擎不真持有」的不確定情境：無本地 truth 不刪。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new())); // 空鏡像
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_ghost_state_streak_met("BTCUSDT|Buy"); // streak 即使滿
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    // mirror 無方向在點查前先擋；即使點查回 ConfirmedZero 也不得收斂。
    let kept = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;

    assert_eq!(
        kept.len(),
        1,
        "ghost without engine-mirror direction must be kept, not converged"
    );
    assert!(
        rx.try_recv().is_err(),
        "no converge command when engine has no local position (S-1 fail-closed)"
    );
}

#[tokio::test]
async fn ghost_converge_never_dispatches_close_symbol() {
    // 反模式守衛：D2 路徑絕不發 CloseSymbol（避免 reduce-only re-dispatch 再撞
    // 110017 重入迴圈）。Drain channel 確認唯一命令是 ConvergeExchangeZero。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true);
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_ghost_state_streak_met("BTCUSDT|Buy");
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    let _ = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;

    while let Ok(cmd) = rx.try_recv() {
        if let crate::tick_pipeline::PipelineCommand::CloseSymbol { .. } = cmd {
            panic!("D2 ghost converge MUST NOT dispatch CloseSymbol (re-enter loop risk)");
        }
    }
}

#[tokio::test]
async fn ghost_process_passes_through_non_ghost_drifts() {
    // 非 Ghost drift（MajorDrift / Orphan / SideFlip）必須原樣穿過，由既有
    // process_orphans / evaluate_actions 處理；process_ghosts 不得吞掉。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true);
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_state();
    let drifts = vec![
        ("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift),
        ("ETHUSDT|Sell".into(), DriftVerdict::Orphan),
    ];
    let (tx, _rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    let kept = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;

    assert_eq!(kept.len(), 2, "non-ghost drifts must pass through untouched");
}

#[tokio::test]
async fn ghost_streak_self_clears_when_ghost_disappears() {
    // last_ghost_keys 整體覆蓋語意：上輪有 Ghost，本輪無 Ghost（drift 為非 Ghost）
    // → last_ghost_keys 自動清空。下次同 symbol 再判 Ghost 須重新累積 streak
    // （防 stale streak 殘留導致過早收斂）。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true);
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_state();
    state.last_ghost_keys.insert("BTCUSDT|Buy".into()); // 上輪 Ghost
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::MajorDrift)]; // 本輪非 Ghost
    let (tx, _rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    let _ = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;

    assert!(
        state.last_ghost_keys.is_empty(),
        "last_ghost_keys must clear when no ghost seen this cycle"
    );
}

// ── P2-110017-D2-RECONCILE round 2: S-6 單 symbol 點查 gate（BB CRITICAL 修法 A）──
//
// 核心：主 fetch get_positions(None) 受 Bybit V5 limit=20 + 分頁截斷。持倉 > 20 時
// 第 21+ 真倉「不在回應頁」→ 初判 Ghost。S-6 收斂前發單 symbol 點查（不受分頁截斷）
// 作為權威 gate。下列三分支 + 對抗驗證直接覆蓋 BB CRITICAL regression。

#[tokio::test]
async fn ghost_pagination_truncation_false_ghost_not_converged() {
    // ★ BB CRITICAL 直接 regression：模擬「mirror 有倉 BTCUSDT + 主 fetch（截斷）
    // current map 無 BTCUSDT（→ 初判 Ghost）+ streak 已滿 + 單 symbol 點查回 size>0
    // （真倉）」→ 斷言不收斂（真倉保留 + log pagination_false_ghost），無 converge 命令。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true); // 引擎本地確實有倉（S-1 滿）
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_ghost_state_streak_met("BTCUSDT|Buy"); // S-5 streak 已滿
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    // 點查回 StillHasPosition = 分頁截斷假 Ghost（交易所仍有真倉）。
    let kept = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::StillHasPosition),
    )
    .await;

    assert_eq!(
        kept.len(),
        1,
        "pagination-truncated false ghost (point-query size>0) MUST be kept, not converged \
         — deleting a real live position is the BB CRITICAL defect"
    );
    assert!(
        rx.try_recv().is_err(),
        "no ConvergeExchangeZero may be dispatched when point-query confirms a real position"
    );
}

#[tokio::test]
async fn ghost_point_query_confirmed_zero_converges() {
    // happy path 保留：點查回 ConfirmedZero（真 Ghost）+ S-1/S-5 滿 → 正常收斂。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true);
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_ghost_state_streak_met("BTCUSDT|Buy");
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    let kept = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;

    assert!(
        kept.is_empty(),
        "confirmed-zero ghost must be converged and removed from drifts"
    );
    assert!(
        matches!(
            rx.try_recv()
                .expect("ConvergeExchangeZero must be dispatched when point-query confirms size==0"),
            crate::tick_pipeline::PipelineCommand::ConvergeExchangeZero { .. }
        ),
        "dispatched command must be ConvergeExchangeZero on confirmed-zero point-query"
    );
}

#[tokio::test]
async fn ghost_point_query_failed_fail_closed_not_converged() {
    // fail-closed：點查失敗 / timeout → 查不到不刪（Root Principle 6），不收斂。
    let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
    mirror.write().insert("BTCUSDT".into(), true);
    let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
    let mut state = make_ghost_state_streak_met("BTCUSDT|Buy");
    let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];
    let (tx, mut rx) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let audit_pool: Option<sqlx::PgPool> = None;

    let kept = process_ghosts(
        drifts,
        &oh_cfg,
        &tx,
        &audit_pool,
        "test",
        &mut state,
        pq_const(GhostPointQuery::QueryFailed),
    )
    .await;

    assert_eq!(
        kept.len(),
        1,
        "ghost with failed point-query must be kept (fail-closed), not converged"
    );
    assert!(
        rx.try_recv().is_err(),
        "no converge command when point-query fails (cannot rule out a real position)"
    );
}

#[tokio::test]
async fn ghost_point_query_gate_is_load_bearing() {
    // 對抗驗證：證明 S-6 點查 gate 是 load-bearing。同一個分頁截斷情境（真倉，
    // 點查回 size>0），若 gate 「形同虛設」（用 ConfirmedZero 模擬拿掉 gate）就會
    // 誤刪真倉 → 收斂並發 ConvergeExchangeZero。對照 StillHasPosition 必不收斂。
    // 這刻意對比兩個 point_query 結果，鎖住「gate 必須能改變收斂結果」這條不變量。
    let build = || {
        let mirror = Arc::new(parking_lot::RwLock::new(HashMap::new()));
        mirror.write().insert("BTCUSDT".into(), true);
        let oh_cfg = build_orphan_cfg_for_test(Arc::clone(&mirror));
        let state = make_ghost_state_streak_met("BTCUSDT|Buy");
        let drifts = vec![("BTCUSDT|Buy".into(), DriftVerdict::Ghost)];
        (oh_cfg, state, drifts)
    };

    // 拿掉 gate（=點查恆 ConfirmedZero）→ 截斷真倉被誤刪：收斂 + 發命令。
    let (oh_cfg_a, mut state_a, drifts_a) = build();
    let (tx_a, mut rx_a) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let pool: Option<sqlx::PgPool> = None;
    let kept_a = process_ghosts(
        drifts_a,
        &oh_cfg_a,
        &tx_a,
        &pool,
        "test",
        &mut state_a,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;
    assert!(
        kept_a.is_empty() && rx_a.try_recv().is_ok(),
        "without an effective point-query gate, a pagination-truncated real position would be \
         wrongly converged (this is exactly the BB CRITICAL defect)"
    );

    // gate 生效（點查回 StillHasPosition）→ 同情境真倉保留：不收斂、無命令。
    let (oh_cfg_b, mut state_b, drifts_b) = build();
    let (tx_b, mut rx_b) =
        tokio::sync::mpsc::unbounded_channel::<crate::tick_pipeline::PipelineCommand>();
    let kept_b = process_ghosts(
        drifts_b,
        &oh_cfg_b,
        &tx_b,
        &pool,
        "test",
        &mut state_b,
        pq_const(GhostPointQuery::StillHasPosition),
    )
    .await;
    assert!(
        kept_b.len() == 1 && rx_b.try_recv().is_err(),
        "point-query gate MUST flip the outcome to no-converge for the same truncated scenario"
    );
}

// ───────────────────────────────────────────────────────────────────────────
// PHANTOM-FILL-FIX-1（2026-06-07，PA Option A · golden #2）：
//   orphan-adopt 自癒回歸 —— Option A 把「PositionUpdate 兜底 upsert」移除後，
//   missed-fill（Bybit 有倉 / 本地 flat）仍能經 reconciler orphan 軸 `Adopt` 把真倉
//   注入 paper_state（非只 Close），確認自癒未失，且 latency ≤ 一個 reconcile cycle
//   （= 一次 AdoptOrphan 指令 round-trip）。
//
//   背景：拆分前 WS `PositionUpdate(size>0)` 會 `upsert_position_from_exchange` 把
//   交易所倉位主動補進本地帳（這是 fill 漏接時的「兜底補倉」隱式路徑之一）。
//   Option A 降 PositionUpdate 為 advisory 後，size>0/本地無倉只 WARN 不 mutate，
//   收斂明確交給 reconciler orphan 軸。本 golden 證明該軸真的把倉補回來。
// ───────────────────────────────────────────────────────────────────────────

/// 構建一個 Bybit-truth `PositionInfo`（reconciler `fetch_current_view` 的原始型別）。
fn orphan_pos_info(symbol: &str, side: &str, size: f64, avg: f64, mark: f64) -> PositionInfo {
    PositionInfo {
        symbol: symbol.into(),
        side: side.into(),
        size,
        avg_price: avg,
        mark_price: mark,
        unrealised_pnl: 0.0,
        leverage: 10.0,
        liq_price: 0.0, // 0 → Stage A1 liq 檢查跳過（安全遠離）
        take_profit: 0.0,
        stop_loss: 0.0,
        position_idx: 0,
        trailing_stop: 0.0,
        position_value: size * mark,
        cum_realised_pnl: 0.0,
        created_time: String::new(),
        updated_time: String::new(),
    }
}

/// 最小 DualStateWriter（temp 檔），供 handle_paper_command 接收快照寫入。
fn make_reconciler_test_writer() -> crate::persistence::DualStateWriter {
    use std::path::PathBuf;
    let mut p = std::env::temp_dir();
    p.push(format!(
        "openclaw_reconciler_adopt_test_{}_{}.json",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    let primary = crate::persistence::StateWriter::new(&p as &PathBuf, 5_000);
    crate::persistence::DualStateWriter::new(primary, None)
}

/// golden #2：missed-fill → orphan-adopt 端到端自癒。
///
/// 序列（重現 Option A 移除兜底後的自癒路徑）：
///   1. Bybit 報告 BTCUSDT short 0.5 @ 50000（真倉），但本地 paper_state **flat**
///      （fill 漏接 / restart 後遺留——這正是過去靠 PositionUpdate upsert 兜底的場景）。
///   2. 該 symbol 有正 shrunk edge 的已知策略（ma_crossover）→ reconciler orphan 軸
///      `handle_orphan` 判 `Adopt`（非 Close）。
///   3. `dispatch_orphan_adopt` 發 `AdoptOrphan` 指令（一次 cycle 的 round-trip）。
///   4. `handle_paper_command` 套用該指令 → `adopt_orphan` 把真倉注入 paper_state。
///   5. 斷言：本地現在持有 BTCUSDT short 0.5 @ 50000（自癒成功），owner_strategy=
///      合成 orphan_adopted 標籤（不污染策略 edge 掃描）。
///
/// 這證明 Option A 把 PositionUpdate 降 advisory 後，missed-fill 的收斂責任落到
/// orphan 軸且確實生效，自癒 latency = 一個 reconcile cycle（一次指令）。
///
/// // BITE-A：把 dispatch_orphan_adopt 對 Adopt 的 cmd_tx.send 短路（不發指令）→
/// //   無 AdoptOrphan 指令 → paper_state 仍 flat → 末段「self-heal 注入」斷言 FAIL。
/// // BITE-B：把 handle_orphan 的 B2 Adopt 分支降級為 Close（回退 Phase 1 語意）→
/// //   收到 Close 決策 → dispatch_orphan_adopt 路由不符回 false / 不注入 → FAIL。
/// // 兩條夾住「Adopt 決策 + 注入」這條自癒鏈的 load-bearing 性。
#[tokio::test]
async fn phantom_fix_orphan_adopt_self_heals_missed_fill_into_paper_state() {
    use crate::edge_estimates::EdgeEstimates;
    use crate::position_reconciler::orphan_handler::{
        dispatch_orphan_adopt, handle_orphan, OrphanContext, OrphanDecision, ORPHAN_ADOPTED_STRATEGY,
    };
    use crate::tick_pipeline::{PipelineCommand, PipelineKind, TickPipeline};

    let symbol = "BTCUSDT";

    // 1) 本地 demo pipeline，paper_state 起始 flat（模擬 missed-fill / restart 遺留）。
    let mut pipeline = TickPipeline::with_kind(&[symbol], 10_000.0, PipelineKind::Demo);
    pipeline.set_endpoint_env(crate::bybit_rest_client::BybitEnvironment::Demo);
    assert_eq!(
        pipeline.paper_state.position_count(),
        0,
        "setup：本地起始必 flat（missed-fill 場景）"
    );

    // Bybit truth：該 symbol 有 short 0.5 @ 50000。
    let pos = orphan_pos_info(symbol, "Sell", 0.5, 50_000.0, 50_000.0);

    // 2) 正 edge → handle_orphan 判 Adopt（非 Close）。
    let json = r#"{
        "_meta": {"grand_mean_bps": 0.0},
        "ma_crossover::BTCUSDT": {"shrunk_bps": 6.0, "n": 120}
    }"#;
    let ee = EdgeEstimates::load_from_str(json).unwrap();
    let active: Vec<String> = vec![symbol.into()];
    let ctx = OrphanContext {
        pos_info: &pos,
        current_level: RiskLevel::Normal,
        max_order_notional_usdt: 0.0, // 0 = 不檢查名目上限（避免 A3 提前 Close）
        active_symbols: &active,
        edge_estimates: &ee,
    };
    let decision = handle_orphan(&ctx);
    let triggering = match &decision {
        OrphanDecision::Adopt {
            triggering_strategy,
            ..
        } => {
            assert_eq!(
                triggering_strategy, "ma_crossover",
                "正 edge 策略應為 ma_crossover"
            );
            triggering_strategy.clone()
        }
        other => panic!("missed-fill + 正 edge 應判 Adopt（自癒注入），got {other:?}"),
    };

    // 3) dispatch_orphan_adopt 發 AdoptOrphan 指令（reconciler → event_consumer 的一次
    //    cycle round-trip）。
    let (cmd_tx, mut cmd_rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
    let sent = dispatch_orphan_adopt(&decision, &pos, &cmd_tx);
    assert!(sent, "Adopt 決策必須成功派發 AdoptOrphan 指令");

    let cmd = cmd_rx
        .try_recv()
        .expect("reconciler 應發出一條 AdoptOrphan 指令（self-heal）");
    match &cmd {
        PipelineCommand::AdoptOrphan {
            symbol: s,
            is_long,
            qty,
            entry_price,
            owner_strategy,
            ..
        } => {
            assert_eq!(s, symbol);
            assert!(!is_long, "Bybit side=Sell → 注入 short（保留交易所方向）");
            assert!((qty - 0.5).abs() < 1e-12, "注入量 = Bybit size 0.5");
            assert!(
                (entry_price - 50_000.0).abs() < 1e-9,
                "注入 entry = Bybit avg_price 50000（不捏造合成價）"
            );
            assert_eq!(
                owner_strategy.as_deref(),
                Some(triggering.as_str()),
                "AdoptOrphan 帶觸發策略名供下游 PnL 歸因"
            );
        }
        other => panic!("expected AdoptOrphan command, got {other:?}"),
    }

    // 4) event_consumer 套用指令 → 注入 paper_state（自癒落地）。
    let mut writer = make_reconciler_test_writer();
    let mut pending: HashMap<String, crate::event_consumer::PendingOrder> = HashMap::new();
    crate::event_consumer::handlers::handle_paper_command(cmd, &mut pipeline, &mut writer, &mut pending);

    // 5) ── 核心自癒斷言：本地現已持有真倉（Option A 移除兜底後仍自癒）──
    let healed = pipeline
        .paper_state
        .get_position(symbol)
        .expect("orphan-adopt 自癒：真倉必已注入 paper_state（latency = 1 cycle）");
    assert!(!healed.is_long, "自癒注入方向 = Bybit short");
    assert!(
        (healed.qty - 0.5).abs() < 1e-12,
        "自癒注入量 = 0.5，got {}",
        healed.qty
    );
    assert!(
        (healed.entry_price - 50_000.0).abs() < 1e-9,
        "自癒注入 entry = 50000"
    );
    // adopt 的 owner_strategy 是 triggering 策略名（dispatch 帶過去），非合成佔位——
    // 但無論何者都不得是空（owner attribution 必填）。記錄合成標籤常數以防未來語意漂移。
    assert!(
        !healed.owner_strategy.is_empty()
            && (healed.owner_strategy == triggering
                || healed.owner_strategy == ORPHAN_ADOPTED_STRATEGY),
        "owner_strategy 必為觸發策略或合成 orphan_adopted 標籤，got {:?}",
        healed.owner_strategy
    );
}

/// golden #2b：對照 —— 本地**已有同向倉**時 adopt 冪等 no-op（自癒不重複注入 / 不翻倍）。
/// 證明 orphan-adopt 自癒在「其實沒漏倉」時不會把倉量翻倍（reconciler 重入安全）。
///
/// // BITE：把 adopt_orphan 的 `existing.is_long == is_long → return false` 冪等 guard
/// // 移除 → 第二次注入會覆蓋/疊加 → 本測試 qty 斷言 FAIL。
#[tokio::test]
async fn phantom_fix_orphan_adopt_idempotent_when_already_owned() {
    use crate::tick_pipeline::{PipelineKind, TickPipeline};

    let symbol = "BTCUSDT";
    let mut pipeline = TickPipeline::with_kind(&[symbol], 10_000.0, PipelineKind::Demo);
    pipeline.set_endpoint_env(crate::bybit_rest_client::BybitEnvironment::Demo);

    // 第一次 adopt：注入 short 0.5。
    let first = pipeline
        .paper_state
        .adopt_orphan(symbol, false, 0.5, 50_000.0, 1_000, Some("ma_crossover"));
    assert!(first, "首次 adopt 應注入");
    assert_eq!(pipeline.paper_state.position_count(), 1);

    // 第二次 adopt 同向（reconciler 下一 cycle 重入，倉其實沒漏）→ 冪等 no-op。
    let second = pipeline
        .paper_state
        .adopt_orphan(symbol, false, 0.5, 49_000.0, 2_000, Some("ma_crossover"));
    assert!(!second, "同向倉已存在 → adopt 冪等回 false（不重複注入）");
    let pos = pipeline.paper_state.get_position(symbol).unwrap();
    assert!(
        (pos.qty - 0.5).abs() < 1e-12,
        "冪等：倉量不得翻倍，仍為 0.5，got {}",
        pos.qty
    );
    assert!(
        (pos.entry_price - 50_000.0).abs() < 1e-9,
        "冪等：保留首次 entry，不被第二次覆蓋"
    );
}

// ── PHANTOM-FILL-FIX-1（2026-06-07，PA T5）：process_phantoms 本地幻影偵測軸 ──
//
// 安全核心：本軸只告警不收斂（不送任何 mutating PipelineCommand）。對抗性覆蓋
// streak 防抖（S-streak）+ 點查 gate（S-point-query）+ absent/side_mismatch 分類。
// 告警的可觀測終態 = canary_events.jsonl 寫入（DB pool=None 時 audit skip，不影響）。

/// 在 env-locked tempdir 下跑 process_phantoms，回傳 canary_events.jsonl 內容
/// （不存在則空字串）。OPENCLAW_DATA_DIR 由 env_lock 串行隔離，避免並行 race。
async fn run_phantoms_capture_canary<F, Fut>(
    mirror_pairs: &[(&str, bool)],
    current: &HashMap<String, PositionView>,
    state: &mut ReconcilerState,
    point_query: F,
) -> String
where
    F: Fn(String) -> Fut,
    Fut: std::future::Future<Output = GhostPointQuery>,
{
    use crate::test_env_lock::guard as env_lock;
    let _g = env_lock();
    let tmp = std::env::temp_dir().join(format!(
        "phantom_canary_test_{}_{}",
        std::process::id(),
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_nanos())
            .unwrap_or(0)
    ));
    let _ = std::fs::remove_dir_all(&tmp);
    // SAFETY: env_lock 已序列化所有改 OPENCLAW_DATA_DIR 的測試。
    unsafe {
        std::env::set_var("OPENCLAW_DATA_DIR", &tmp);
    }
    let mirror: HashMap<String, bool> = mirror_pairs
        .iter()
        .map(|(s, l)| (s.to_string(), *l))
        .collect();
    let pool: Option<sqlx::PgPool> = None;
    process_phantoms(&mirror, current, &pool, "test", state, point_query).await;
    let canary_path = tmp.join("canary_events.jsonl");
    let content = std::fs::read_to_string(&canary_path).unwrap_or_default();
    let _ = std::fs::remove_dir_all(&tmp);
    unsafe {
        std::env::remove_var("OPENCLAW_DATA_DIR");
    }
    content
}

#[tokio::test]
async fn phantom_alerts_on_absent_after_streak_and_confirmed_zero() {
    // 本地 mirror 有 TONUSDT long、Bybit current 全空（absent）+ streak 已滿
    // （last_phantom_keys 含 TONUSDT）+ 點查回 ConfirmedZero → 告警寫 canary。
    let current: HashMap<String, PositionView> = HashMap::new(); // Bybit flat
    let mut state = make_state();
    state.last_phantom_keys.insert("TONUSDT".to_string()); // 上輪已見 → streak 滿
    let content = run_phantoms_capture_canary(
        &[("TONUSDT", true)],
        &current,
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;
    assert!(
        content.contains("PHANTOM_POSITION_DETECTED") && content.contains("TONUSDT"),
        "absent 幻影 streak+ConfirmedZero 必告警，canary 內容：{content:?}"
    );
    assert!(
        content.contains("\"kind\":\"absent\""),
        "kind 應為 absent"
    );
    assert!(
        state.last_phantom_keys.contains("TONUSDT"),
        "本輪幻影 key 必記錄以維持下輪 streak"
    );
}

#[tokio::test]
async fn phantom_not_alerted_first_cycle_streak_unmet() {
    // S-streak：本輪首見（last_phantom_keys 空）→ 不告警，但記錄 key 供下輪。
    let current: HashMap<String, PositionView> = HashMap::new();
    let mut state = make_state(); // last_phantom_keys 空
    let content = run_phantoms_capture_canary(
        &[("TONUSDT", true)],
        &current,
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero), // 即使點查 confirmed 也不得告警
    )
    .await;
    assert!(
        content.is_empty(),
        "首輪 streak 未滿不得告警，canary 應空，got：{content:?}"
    );
    assert!(
        state.last_phantom_keys.contains("TONUSDT"),
        "首輪須記錄 key，下輪才能滿 streak"
    );
}

#[tokio::test]
async fn phantom_not_alerted_when_point_query_still_has_position() {
    // S-point-query：streak 滿，但點查回 StillHasPosition（主 fetch 分頁截斷的
    // 假幻影 / 交易所仍有真倉）→ 不告警（防誤報）。
    let current: HashMap<String, PositionView> = HashMap::new();
    let mut state = make_state();
    state.last_phantom_keys.insert("TONUSDT".to_string());
    let content = run_phantoms_capture_canary(
        &[("TONUSDT", true)],
        &current,
        &mut state,
        pq_const(GhostPointQuery::StillHasPosition),
    )
    .await;
    assert!(
        content.is_empty(),
        "點查 StillHasPosition 必擋告警（防分頁截斷假幻影），got：{content:?}"
    );
}

#[tokio::test]
async fn phantom_not_alerted_when_direction_matches_bybit() {
    // 方向相符視為一致（非幻影）：本地 long + Bybit 也 Buy → 不告警。
    let mut current: HashMap<String, PositionView> = HashMap::new();
    current.insert("TONUSDT|Buy".into(), pv("TONUSDT", "Buy", 437.3));
    let mut state = make_state();
    state.last_phantom_keys.insert("TONUSDT".to_string());
    let content = run_phantoms_capture_canary(
        &[("TONUSDT", true)],
        &current,
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;
    assert!(
        content.is_empty(),
        "方向相符不是幻影，不得告警，got：{content:?}"
    );
    assert!(
        !state.last_phantom_keys.contains("TONUSDT"),
        "方向相符不應記入幻影集合"
    );
}

#[tokio::test]
async fn phantom_alerts_on_side_mismatch_after_streak() {
    // side_mismatch：本地 long、Bybit 該 symbol 為 Sell（方向背離）+ streak 滿 +
    // 點查 ConfirmedZero（交易所確無本地方向倉）→ 告警 kind=side_mismatch。
    let mut current: HashMap<String, PositionView> = HashMap::new();
    current.insert("TONUSDT|Sell".into(), pv("TONUSDT", "Sell", 100.0));
    let mut state = make_state();
    state.last_phantom_keys.insert("TONUSDT".to_string());
    let content = run_phantoms_capture_canary(
        &[("TONUSDT", true)], // 本地 long
        &current,
        &mut state,
        pq_const(GhostPointQuery::ConfirmedZero),
    )
    .await;
    assert!(
        content.contains("PHANTOM_POSITION_DETECTED")
            && content.contains("\"kind\":\"side_mismatch\""),
        "方向背離 streak+ConfirmedZero 必告警 kind=side_mismatch，got：{content:?}"
    );
}
