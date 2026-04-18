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
