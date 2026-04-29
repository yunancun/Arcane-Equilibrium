//! T-P1-1: handle_paper_command coverage / 處理器覆蓋率
//!
//! Covers Pause / Resume / Reset / GetStrategyParams / UpdateRiskConfig variants
//! of `handle_paper_command`, including clamp behaviour, trailing_activation_pct
//! round-trips, PNL7 dynamic stop knobs, and Session-12 cost gate + cooldown wiring.
//! 涵蓋 `handle_paper_command` 的 Pause / Resume / Reset / GetStrategyParams /
//! UpdateRiskConfig 分支，包括 clamp、trailing_activation_pct 往返、PNL7 動態止損
//! 旋鈕、Session-12 cost gate + 冷卻接線。

use super::{make_test_pipeline, make_test_writer};

#[test]
fn test_handle_pause_sets_paused() {
    use crate::tick_pipeline::PipelineCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();
    pipeline.paper_paused = false;

    super::super::handlers::handle_paper_command(
        PipelineCommand::Pause,
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    assert!(pipeline.paper_paused);
}

#[test]
fn test_handle_resume_clears_paused_and_halt() {
    use crate::tick_pipeline::PipelineCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();
    pipeline.paper_paused = true;
    pipeline.session_halted = true;

    super::super::handlers::handle_paper_command(
        PipelineCommand::Resume,
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    assert!(!pipeline.paper_paused);
    assert!(!pipeline.session_halted);
}

#[test]
fn test_handle_reset_clears_state_and_pending() {
    use crate::tick_pipeline::PipelineCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();
    pending.insert(
        "stale_oc_1".into(),
        super::super::PendingOrder {
            order_link_id: "stale_oc_1".into(),
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.05,
            strategy: "ma".into(),
            sent_ts_ms: 0,
            cum_filled_qty: 0.0,
            is_close: false,
            // FILL-CONTEXT-LINKAGE-1: empty id preserves pre-fix behaviour.
            // FILL-CONTEXT-LINKAGE-1：空字串保持修前行為。
            context_id: String::new(),
            order_type: "market".into(),
            time_in_force: None,
            maker_timeout_ms: None,
            reference_price: None,
            reference_ts_ms: None,
            reference_source: None,
            cancel_requested_ts_ms: None,
        },
    );
    pipeline.paper_paused = true;
    pipeline.session_halted = true;
    pipeline.consecutive_losses.insert("BTCUSDT".into(), 3);

    super::super::handlers::handle_paper_command(
        PipelineCommand::Reset {
            new_balance: 5_000.0,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    assert_eq!(pipeline.paper_state.export_state().balance, 5_000.0);
    assert!(!pipeline.paper_paused);
    assert!(!pipeline.session_halted);
    assert!(pipeline.consecutive_losses.is_empty());
    assert!(pending.is_empty());
}

#[test]
fn test_handle_get_strategy_params_unknown_returns_err() {
    use crate::tick_pipeline::PipelineCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::super::handlers::handle_paper_command(
        PipelineCommand::GetStrategyParams {
            strategy_name: "no_such_strategy".into(),
            response_tx: tx,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    let result = rx.blocking_recv().expect("response sent");
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("not found"));
}

#[test]
fn test_handle_update_risk_config_clamps_values() {
    use crate::tick_pipeline::PipelineCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    // Push out-of-range values; clamp should bring them inside.
    super::super::handlers::handle_paper_command(
        PipelineCommand::UpdateRiskConfig {
            hard_stop_pct: Some(99.0), // → 0.5
            trailing_stop_pct: None,
            trailing_activation_pct: None,
            time_stop_hours: None,
            atr_multiplier: Some(Some(0.0)), // → 0.5
            take_profit_pct: None,
            max_leverage: Some(999.0), // → 100
            max_drawdown_pct: None,
            max_same_direction_positions: None,
            p1_risk_pct: Some(99.0), // → 0.10
            h0_shadow_mode: Some(true),
            dynamic_stop_base_ratio: None,
            dynamic_stop_cap_ratio: None,
            trailing_min_rr_ratio: None,
            cost_gate_min_confidence: None,
            cost_gate_k_base: None,
            cost_gate_k_medium: None,
            cost_gate_k_small: None,
            adx_trending_threshold: None,
            boot_cooldown_ms: None,
            signals_heartbeat_ms: None,
            exit_missing_edge_fallback_bps: None,
            exit_min_net_floor_bps: None,
            exit_min_hold_secs: None,
            exit_min_peak_atr_norm: None,
            exit_giveback_base: None,
            exit_giveback_slope: None,
            exit_giveback_floor: None,
            // EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): dim 5 of T1 calibrator.
            // EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：T1 calibrator 第 5 維度。
            exit_stale_peak_ms: None,
            response_tx: None,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    // Pipeline should not panic and clamped values should be applied.
    // 管線不應 panic 且鉗制後的值已套用。
    assert!(pipeline.intent_processor.guardian_config().max_leverage <= 100.0);
}

#[test]
fn test_handle_update_risk_config_sets_trailing_activation_pct() {
    // IPC round-trip: UpdateRiskConfig{trailing_activation_pct: Some(Some(3.0))}
    // must land in paper_state.stop_config.trailing_activation_pct as Some(3.0).
    // IPC 往返：trailing_activation_pct 應正確傳入 paper_state.stop_config。
    use crate::tick_pipeline::PipelineCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    assert!(
        pipeline
            .paper_state
            .stop_config()
            .trailing_activation_pct
            .is_none(),
        "default StopConfig has no activation threshold (falls back to trail_pct)"
    );

    // NOTE: outer clamp in handlers.rs is 0.0..=0.5 (fraction-based, same family
    // as hard/trailing stop — pre-existing latent bug tracked separately).
    // Values below 0.5 round-trip unchanged, which is what we assert here.
    // 注：handlers 外層 clamp 沿用 hard/trailing stop 的 0.0..=0.5 範圍（fraction 語意
    // 的既有缺陷，已另案追蹤）；此處用 < 0.5 的值驗證往返不被截斷。
    super::super::handlers::handle_paper_command(
        PipelineCommand::UpdateRiskConfig {
            hard_stop_pct: None,
            trailing_stop_pct: Some(Some(0.2)),
            trailing_activation_pct: Some(Some(0.3)),
            time_stop_hours: None,
            atr_multiplier: None,
            take_profit_pct: None,
            max_leverage: None,
            max_drawdown_pct: None,
            max_same_direction_positions: None,
            p1_risk_pct: None,
            h0_shadow_mode: None,
            dynamic_stop_base_ratio: None,
            dynamic_stop_cap_ratio: None,
            trailing_min_rr_ratio: None,
            cost_gate_min_confidence: None,
            cost_gate_k_base: None,
            cost_gate_k_medium: None,
            cost_gate_k_small: None,
            adx_trending_threshold: None,
            boot_cooldown_ms: None,
            signals_heartbeat_ms: None,
            exit_missing_edge_fallback_bps: None,
            exit_min_net_floor_bps: None,
            exit_min_hold_secs: None,
            exit_min_peak_atr_norm: None,
            exit_giveback_base: None,
            exit_giveback_slope: None,
            exit_giveback_floor: None,
            // EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): dim 5 of T1 calibrator.
            // EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：T1 calibrator 第 5 維度。
            exit_stale_peak_ms: None,
            response_tx: None,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );

    let sc = pipeline.paper_state.stop_config();
    assert_eq!(sc.trailing_stop_pct, Some(0.2));
    assert_eq!(sc.trailing_activation_pct, Some(0.3));

    // Explicit None-clear round-trip: Some(None) must wipe the field.
    // 顯式清除：Some(None) 應將欄位重置為 None。
    super::super::handlers::handle_paper_command(
        PipelineCommand::UpdateRiskConfig {
            hard_stop_pct: None,
            trailing_stop_pct: None,
            trailing_activation_pct: Some(None),
            time_stop_hours: None,
            atr_multiplier: None,
            take_profit_pct: None,
            max_leverage: None,
            max_drawdown_pct: None,
            max_same_direction_positions: None,
            p1_risk_pct: None,
            h0_shadow_mode: None,
            dynamic_stop_base_ratio: None,
            dynamic_stop_cap_ratio: None,
            trailing_min_rr_ratio: None,
            cost_gate_min_confidence: None,
            cost_gate_k_base: None,
            cost_gate_k_medium: None,
            cost_gate_k_small: None,
            adx_trending_threshold: None,
            boot_cooldown_ms: None,
            signals_heartbeat_ms: None,
            exit_missing_edge_fallback_bps: None,
            exit_min_net_floor_bps: None,
            exit_min_hold_secs: None,
            exit_min_peak_atr_norm: None,
            exit_giveback_base: None,
            exit_giveback_slope: None,
            exit_giveback_floor: None,
            // EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): dim 5 of T1 calibrator.
            // EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：T1 calibrator 第 5 維度。
            exit_stale_peak_ms: None,
            response_tx: None,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    assert!(pipeline
        .paper_state
        .stop_config()
        .trailing_activation_pct
        .is_none());
}

#[test]
fn test_pnl7_handle_dynamic_stop_knobs_apply_and_reject() {
    use crate::tick_pipeline::PipelineCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    // Apply valid + invalid mix; valid ones land, invalid ones rejected by patch fn.
    super::super::handlers::handle_paper_command(
        PipelineCommand::UpdateRiskConfig {
            hard_stop_pct: None,
            trailing_stop_pct: None,
            trailing_activation_pct: None,
            time_stop_hours: None,
            atr_multiplier: None,
            take_profit_pct: None,
            max_leverage: None,
            max_drawdown_pct: None,
            max_same_direction_positions: None,
            p1_risk_pct: None,
            h0_shadow_mode: None,
            dynamic_stop_base_ratio: Some(0.4), // valid
            dynamic_stop_cap_ratio: Some(5.0),  // invalid (> 1.0)
            trailing_min_rr_ratio: Some(0.75),  // valid
            cost_gate_min_confidence: None,
            cost_gate_k_base: None,
            cost_gate_k_medium: None,
            cost_gate_k_small: None,
            adx_trending_threshold: None,
            boot_cooldown_ms: None,
            signals_heartbeat_ms: None,
            exit_missing_edge_fallback_bps: None,
            exit_min_net_floor_bps: None,
            exit_min_hold_secs: None,
            exit_min_peak_atr_norm: None,
            exit_giveback_base: None,
            exit_giveback_slope: None,
            exit_giveback_floor: None,
            // EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): dim 5 of T1 calibrator.
            // EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：T1 calibrator 第 5 維度。
            exit_stale_peak_ms: None,
            response_tx: None,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    let rc = pipeline.intent_processor.risk_config();
    assert!((rc.dynamic_stop.base_ratio - 0.4).abs() < 1e-9);
    assert!(
        (rc.dynamic_stop.cap_ratio - 0.8).abs() < 1e-9,
        "invalid cap rejected, default kept"
    );
    assert!((rc.dynamic_stop.trailing_min_rr - 0.75).abs() < 1e-9);
}

#[test]
fn test_session12_handle_cost_gate_and_cooldown_via_ipc() {
    use crate::tick_pipeline::PipelineCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    super::super::handlers::handle_paper_command(
        PipelineCommand::UpdateRiskConfig {
            hard_stop_pct: None,
            trailing_stop_pct: None,
            trailing_activation_pct: None,
            time_stop_hours: None,
            atr_multiplier: None,
            take_profit_pct: None,
            max_leverage: None,
            max_drawdown_pct: None,
            max_same_direction_positions: None,
            p1_risk_pct: None,
            h0_shadow_mode: None,
            dynamic_stop_base_ratio: None,
            dynamic_stop_cap_ratio: None,
            trailing_min_rr_ratio: None,
            cost_gate_min_confidence: Some(0.25),
            cost_gate_k_base: Some(1.8),
            cost_gate_k_medium: Some(2.5),
            cost_gate_k_small: Some(4.0),
            adx_trending_threshold: Some(30.0),
            boot_cooldown_ms: Some(120_000),
            signals_heartbeat_ms: Some(30_000),
            exit_missing_edge_fallback_bps: None,
            exit_min_net_floor_bps: None,
            exit_min_hold_secs: None,
            exit_min_peak_atr_norm: None,
            exit_giveback_base: None,
            exit_giveback_slope: None,
            exit_giveback_floor: None,
            // EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): dim 5 of T1 calibrator.
            // EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：T1 calibrator 第 5 維度。
            exit_stale_peak_ms: None,
            response_tx: None,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    let rc = pipeline.intent_processor.risk_config();
    assert!((rc.cost_gate.min_confidence - 0.25).abs() < 1e-9);
    assert!((rc.cost_gate.k_base - 1.8).abs() < 1e-9);
    assert!((rc.cost_gate.k_medium - 2.5).abs() < 1e-9);
    assert!((rc.cost_gate.k_small - 4.0).abs() < 1e-9);
    assert!((rc.cost_gate.adx_trending - 30.0).abs() < 1e-9);
    assert_eq!(pipeline.boot_cooldown_ms(), 120_000);
    assert_eq!(pipeline.signals_heartbeat_ms(), 30_000);
}
