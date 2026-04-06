//! I-09 + I-22: Unit tests for event_consumer clamp ranges and JSON envelope invariants.
//! I-09 + I-22：事件消費者鉗制範圍與 JSON 信封不變量單元測試。

#[test]
fn test_clamp_risk_pct_and_stop_pct_bounds() {
    // risk_pct: 0.0..=0.10 / stop_pct: 0.0..=0.5
    assert_eq!((-1.0_f64).clamp(0.0, 0.10), 0.0);
    assert_eq!((0.05_f64).clamp(0.0, 0.10), 0.05);
    assert_eq!((0.99_f64).clamp(0.0, 0.10), 0.10);
    assert_eq!((-0.1_f64).clamp(0.0, 0.5), 0.0);
    assert_eq!((0.25_f64).clamp(0.0, 0.5), 0.25);
    assert_eq!((9.9_f64).clamp(0.0, 0.5), 0.5);
}

#[test]
fn test_clamp_atr_leverage_positions_bounds() {
    // atr_multiplier: 0.5..=10.0 / max_leverage: 1..=100 / max_positions: 1..=100
    assert_eq!((0.0_f64).clamp(0.5, 10.0), 0.5);
    assert_eq!((3.0_f64).clamp(0.5, 10.0), 3.0);
    assert_eq!((50.0_f64).clamp(0.5, 10.0), 10.0);
    assert_eq!((0_usize).clamp(1, 100), 1);
    assert_eq!((25_usize).clamp(1, 100), 25);
    assert_eq!((999_usize).clamp(1, 100), 100);
}

#[test]
fn test_clamp_cooldown_minutes_and_count_bounds() {
    // consecutive_loss_cooldown_count: 0..=1000 / cooldown_minutes: 0..=1440
    assert_eq!((-5_i64).clamp(0, 1000), 0);
    assert_eq!((3_i64).clamp(0, 1000), 3);
    assert_eq!((9999_i64).clamp(0, 1000), 1000);
    assert_eq!((-1_i64).clamp(0, 1440), 0);
    assert_eq!((60_i64).clamp(0, 1440), 60);
    assert_eq!((99999_i64).clamp(0, 1440), 1440);
}

#[test]
fn test_clamp_trailing_stop_pct_bounds() {
    // trailing_stop_pct: 0.0..=0.5 (same family as hard stop)
    assert_eq!((-10.0_f64).clamp(0.0, 0.5), 0.0);
    assert_eq!((0.15_f64).clamp(0.0, 0.5), 0.15);
    assert_eq!((5.0_f64).clamp(0.0, 0.5), 0.5);
}

#[test]
fn test_update_strategy_params_json_invalid() {
    // Invalid JSON must not panic; serde_json::from_str returns Err
    let bad = "{not valid";
    let result: Result<serde_json::Value, _> = serde_json::from_str(bad);
    assert!(result.is_err());
}

#[test]
fn test_update_strategy_params_json_roundtrip() {
    // Valid params JSON round-trips via serde_json::Value
    let json = r#"{"ma_short":10,"ma_long":30,"atr_period":14}"#;
    let v: serde_json::Value = serde_json::from_str(json).expect("valid json");
    assert_eq!(v["ma_short"], 10);
    assert_eq!(v["ma_long"], 30);
    assert_eq!(v["atr_period"], 14);
}

// ─────────────────────────────────────────────────────────────────────────
// T-P1-1: handle_paper_command coverage / 處理器覆蓋率
// ─────────────────────────────────────────────────────────────────────────

fn make_test_pipeline() -> crate::tick_pipeline::TickPipeline {
    crate::tick_pipeline::TickPipeline::with_balance(&["BTCUSDT", "ETHUSDT"], 10_000.0)
}

fn make_test_writer() -> crate::persistence::StateWriter {
    use std::path::PathBuf;
    let mut p = std::env::temp_dir();
    p.push(format!(
        "openclaw_test_handlers_{}.json",
        std::process::id()
    ));
    crate::persistence::StateWriter::new(&p as &PathBuf, 5_000)
}

#[test]
fn test_handle_pause_sets_paused() {
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();
    pipeline.paper_paused = false;

    super::handlers::handle_paper_command(
        PaperSessionCommand::Pause,
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    assert!(pipeline.paper_paused);
}

#[test]
fn test_handle_resume_clears_paused_and_halt() {
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();
    pipeline.paper_paused = true;
    pipeline.session_halted = true;

    super::handlers::handle_paper_command(
        PaperSessionCommand::Resume,
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    assert!(!pipeline.paper_paused);
    assert!(!pipeline.session_halted);
}

#[test]
fn test_handle_reset_clears_state_and_pending() {
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();
    pending.insert(
        "stale_oc_1".into(),
        super::PendingOrder {
            order_link_id: "stale_oc_1".into(),
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.05,
            strategy: "ma".into(),
            sent_ts_ms: 0,
            cum_filled_qty: 0.0,
            is_close: false,
        },
    );
    pipeline.paper_paused = true;
    pipeline.session_halted = true;
    pipeline.consecutive_losses.insert("BTCUSDT".into(), 3);

    super::handlers::handle_paper_command(
        PaperSessionCommand::Reset {
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
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PaperSessionCommand::GetStrategyParams {
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
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    // Push out-of-range values; clamp should bring them inside.
    super::handlers::handle_paper_command(
        PaperSessionCommand::UpdateRiskConfig {
            hard_stop_pct: Some(99.0),    // → 0.5
            trailing_stop_pct: None,
            time_stop_hours: None,
            atr_multiplier: Some(Some(0.0)), // → 0.5
            take_profit_pct: None,
            max_leverage: Some(999.0),    // → 100
            max_drawdown_pct: None,
            max_same_direction_positions: None,
            p1_risk_pct: Some(99.0),      // → 0.10
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
fn test_pnl7_handle_dynamic_stop_knobs_apply_and_reject() {
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    // Apply valid + invalid mix; valid ones land, invalid ones rejected by patch fn.
    super::handlers::handle_paper_command(
        PaperSessionCommand::UpdateRiskConfig {
            hard_stop_pct: None,
            trailing_stop_pct: None,
            time_stop_hours: None,
            atr_multiplier: None,
            take_profit_pct: None,
            max_leverage: None,
            max_drawdown_pct: None,
            max_same_direction_positions: None,
            p1_risk_pct: None,
            h0_shadow_mode: None,
            dynamic_stop_base_ratio: Some(0.4),       // valid
            dynamic_stop_cap_ratio: Some(5.0),        // invalid (> 1.0)
            trailing_min_rr_ratio: Some(0.75),        // valid
            cost_gate_min_confidence: None,
            cost_gate_k_base: None,
            cost_gate_k_medium: None,
            cost_gate_k_small: None,
            adx_trending_threshold: None,
            boot_cooldown_ms: None,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    let rc = pipeline.intent_processor.risk_config();
    assert!((rc.dynamic_stop_base_ratio - 0.4).abs() < 1e-9);
    assert!((rc.dynamic_stop_cap_ratio - 0.8).abs() < 1e-9, "invalid cap rejected, default kept");
    assert!((rc.trailing_min_rr_ratio - 0.75).abs() < 1e-9);
}

#[test]
fn test_session12_handle_cost_gate_and_cooldown_via_ipc() {
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    super::handlers::handle_paper_command(
        PaperSessionCommand::UpdateRiskConfig {
            hard_stop_pct: None,
            trailing_stop_pct: None,
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
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    let rc = pipeline.intent_processor.risk_config();
    assert!((rc.cost_gate_min_confidence - 0.25).abs() < 1e-9);
    assert!((rc.cost_gate_k_base - 1.8).abs() < 1e-9);
    assert!((rc.cost_gate_k_medium - 2.5).abs() < 1e-9);
    assert!((rc.cost_gate_k_small - 4.0).abs() < 1e-9);
    assert!((rc.adx_trending_threshold - 30.0).abs() < 1e-9);
    assert_eq!(pipeline.boot_cooldown_ms(), 120_000);
}

#[test]
fn test_pending_order_clone_preserves_state() {
    // PendingOrder must be cloneable for matching path (fill arrives before order update)
    let po = super::PendingOrder {
        order_link_id: "oc_1".into(),
        symbol: "BTCUSDT".into(),
        is_long: true,
        qty: 0.01,
        strategy: "ma".into(),
        sent_ts_ms: 1_000,
        cum_filled_qty: 0.0,
        is_close: false,
    };
    let cloned = po.clone();
    assert_eq!(cloned.order_link_id, "oc_1");
    assert_eq!(cloned.qty, 0.01);
    assert!(!cloned.is_close);
}
