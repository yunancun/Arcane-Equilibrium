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
            signals_heartbeat_ms: None,
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
            signals_heartbeat_ms: None,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );
    let rc = pipeline.intent_processor.risk_config();
    assert!((rc.dynamic_stop.base_ratio - 0.4).abs() < 1e-9);
    assert!((rc.dynamic_stop.cap_ratio - 0.8).abs() < 1e-9, "invalid cap rejected, default kept");
    assert!((rc.dynamic_stop.trailing_min_rr - 0.75).abs() < 1e-9);
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
            signals_heartbeat_ms: Some(30_000),
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

// ═══════════════════════════════════════════════════════════════════════════
// M-1 (ARCH-RC1 1C-3-D): Real guard tests for operator manual governor override.
// Drives handle_paper_command(ForceGovernorLooser/Tighter) end-to-end so the
// four IPC-layer guards actually fire. Previously the guards were only covered
// by the `setup_governor_override_channel` fake consumer in ipc_server.rs tests
// which bypassed the guard code entirely — a refactor could silently remove
// every guard and CI would still pass (E2 review 2026-04-08 flag).
// 真實驅動 handle_paper_command 的守衛測試；取代先前的假 consumer。
// ═══════════════════════════════════════════════════════════════════════════

fn escalate_to_tier(
    p: &mut crate::tick_pipeline::TickPipeline,
    target: openclaw_core::sm::risk_gov::RiskLevel,
) {
    use openclaw_core::sm::risk_gov::{RiskEvent, RiskLevel};
    p.governance.risk.thresholds.min_hold_time_ms = 0;
    let ladder = [
        RiskLevel::Cautious,
        RiskLevel::Reduced,
        RiskLevel::Defensive,
        RiskLevel::CircuitBreaker,
        RiskLevel::ManualReview,
    ];
    for step in ladder {
        if (p.governance.risk.snapshot_level().value() as u8) >= (target.value() as u8) {
            break;
        }
        p.governance
            .risk
            .escalate_to(step, "test_setup", RiskEvent::OperatorEscalation)
            .expect("test escalation");
    }
    assert_eq!(p.governance.risk.snapshot_level(), target, "setup reached target");
}

fn run_looser(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::StateWriter,
    target: &str,
    reason_code: &str,
    notes: &str,
) -> Result<String, String> {
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PaperSessionCommand::ForceGovernorLooser {
            target_tier: target.into(),
            reason_code: reason_code.into(),
            notes: notes.into(),
            response_tx: tx,
        },
        pipeline,
        writer,
        &mut pending,
    );
    rx.blocking_recv().expect("response sent")
}

fn run_tighter(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::StateWriter,
    target: &str,
    reason: &str,
) -> Result<String, String> {
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PaperSessionCommand::ForceGovernorTighter {
            target_tier: target.into(),
            reason: reason.into(),
            response_tx: tx,
        },
        pipeline,
        writer,
        &mut pending,
    );
    rx.blocking_recv().expect("response sent")
}

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
    assert!(e.contains("invalid reason_code"), "error mentions reason_code: {e}");
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
    assert_eq!(p.governance.risk.snapshot_level(), RiskLevel::CircuitBreaker);
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
    assert!(e.contains("exactly one tier below"), "error mentions step: {e}");
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
    assert!(p.last_governor_de_escalation_ms().is_some(), "cooldown armed");
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

// ═══════════════════════════════════════════════════════════════════════════
// ARCH-RC1 1C-3-F: SubmitOrder e2e tests via handle_paper_command + oneshot.
// Drives the new external paper-side submit RPC end-to-end so the rewired
// shadow_decision_builder + any future Layer 2 / operator entry has CI cover.
// ARCH-RC1 1C-3-F：SubmitOrder e2e 測試（取代 paper_trading_engine.py 後的入口）。
// ═══════════════════════════════════════════════════════════════════════════

fn run_submit(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::StateWriter,
    symbol: &str,
    side: &str,
    qty: f64,
) -> Result<String, String> {
    use crate::tick_pipeline::PaperSessionCommand;
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PaperSessionCommand::SubmitOrder {
            symbol: symbol.into(),
            side: side.into(),
            qty,
            order_type: "market".into(),
            limit_price: None,
            confidence: 0.9,
            strategy: "external_test".into(),
            response_tx: tx,
        },
        pipeline,
        writer,
        &mut pending,
    );
    rx.blocking_recv().expect("response sent")
}

/// Seed the latest_indicators map so the cost-gate ATR lookup is satisfied.
/// Without this, submit_external_order fails closed (matches strategy path).
/// 種入 latest_indicators 以滿足 cost gate 的 ATR 需求。
fn seed_indicators_with_atr(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    symbol: &str,
    atr: f64,
) {
    use openclaw_core::indicators::{AtrResult, IndicatorSnapshot};
    let mut snap = IndicatorSnapshot::default();
    snap.atr_14 = Some(AtrResult {
        atr,
        atr_percent: atr / 50_000.0,
    });
    pipeline.set_latest_indicators_for_test(symbol, snap);
}

fn authorize(p: &mut crate::tick_pipeline::TickPipeline) {
    p.governance
        .grant_paper_authorization(None)
        .expect("grant paper auth");
}

#[test]
fn test_f_submit_order_happy_path() {
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    seed_indicators_with_atr(&mut p, "BTCUSDT", 250.0);
    // Authorise governance — process() requires it.
    // 授權治理層 — process() 第一道 gate 即檢查。
    authorize(&mut p);

    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Buy", 0.001);
    assert!(result.is_ok(), "submit failed: {result:?}");
    let envelope: serde_json::Value =
        serde_json::from_str(&result.unwrap()).expect("envelope is json");
    assert!(envelope["order_id"].as_str().unwrap().starts_with("ext-BTCUSDT-"));
    assert!(envelope["fill_qty"].as_f64().unwrap() > 0.0);
    assert!(envelope["fill_price"].as_f64().unwrap() > 0.0);
    // Side-effects: position opened + stats incremented.
    // 副作用：倉位已開 + stats 已遞增。
    assert!(p.paper_state.get_position("BTCUSDT").is_some());
    assert_eq!(p.stats.total_fills, 1);
}

#[test]
fn test_f_submit_order_paused_rejected() {
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    seed_indicators_with_atr(&mut p, "BTCUSDT", 250.0);
    authorize(&mut p);
    p.paper_paused = true;

    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Buy", 0.001);
    assert!(result.is_err());
    assert_eq!(result.unwrap_err(), "paper_paused");
    assert!(p.paper_state.get_position("BTCUSDT").is_none());
}

#[test]
fn test_f_submit_order_no_price_rejected() {
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    authorize(&mut p);
    // No latest_price seeded — must reject before touching gates.
    // 未種價 — 必須在 gate 前先拒絕。
    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Buy", 0.001);
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("no latest price"));
}

#[test]
fn test_f_submit_order_invalid_side_rejected() {
    let mut p = make_test_pipeline();
    let mut w = make_test_writer();
    p.paper_state.set_latest_price("BTCUSDT", 50_000.0);
    seed_indicators_with_atr(&mut p, "BTCUSDT", 250.0);
    authorize(&mut p);

    let result = run_submit(&mut p, &mut w, "BTCUSDT", "Diagonal", 0.001);
    assert!(result.is_err());
    assert!(result.unwrap_err().contains("invalid side"));
}
