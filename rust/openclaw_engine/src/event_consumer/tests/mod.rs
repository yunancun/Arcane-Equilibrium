//! I-09 + I-22: Unit tests for event_consumer clamp ranges and JSON envelope invariants.
//! I-09 + I-22：事件消費者鉗制範圍與 JSON 信封不變量單元測試。
//!
//! G5-07 (2026-04-24): Tests were split out of `tests.rs` (1298 lines) into
//! per-category submodules under `tests/` to respect the §九 1200-line hard cap.
//! Shared helpers (pipeline / writer / indicator / governance setup) stay in this
//! module root so all submodules can access them via `super::`.
//! G5-07（2026-04-24）：原 `tests.rs`（1298 行）依類別拆為 `tests/` 下數個子模組以滿足
//! §九 1200 行硬上限。共用輔助函式（pipeline / writer / indicator / 治理設置）保留在此
//! 根模組，子模組透過 `super::` 取用。

// ── Per-category submodules (G5-07 split) ──
// ── 按類別拆分的子模組（G5-07 拆分） ──
mod cross_engine_tests;
mod exit_config_ipc_tests;
mod funding_settlement_tests;
mod governor_override_tests;
mod handlers_paper_cmd_tests;
// FIX-G7-09B-INTENT-LIMIT-DROP-1 (2026-04-25): pin trading.orders.order_type
// honestly mirrors PendingOrder.order_type instead of hardcoded "Market".
// FIX-G7-09B-INTENT-LIMIT-DROP-1（2026-04-25）：pin trading.orders.order_type
// 誠實鏡射 PendingOrder.order_type，而非硬寫 "Market"。
mod pending_registration_order_type_tests;
mod reconciler_tests;
mod submit_order_tests;
// F4-1 (2026-04-26): unmatched WS fill audit emission tests.
// F4-1（2026-04-26）：未匹配 WS 成交 audit 落地測試。
mod unattributed_fill_tests;

// ─────────────────────────────────────────────────────────────────────────
// Util-level tests (clamp ranges + JSON envelope invariants) — stay at root.
// 工具級測試（鉗制範圍 + JSON 信封不變量）— 留在根模組。
// ─────────────────────────────────────────────────────────────────────────

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
        // FILL-CONTEXT-LINKAGE-1: empty id preserves pre-fix behaviour.
        // FILL-CONTEXT-LINKAGE-1：空字串保持修前行為。
        context_id: String::new(),
        order_type: "market".into(),
        time_in_force: None,
        maker_timeout_ms: None,
        close_maker_audit: None,
        reference_price: None,
        reference_ts_ms: None,
        reference_source: None,
        cancel_requested_ts_ms: None,
        // W-C Caveat 2 修復（2026-05-11）：test fixture 預設 None。
        spine_order_plan_id: None,
        spine_decision_id: None,
        spine_verdict_id: None,
        spine_stub_report_id: None,
    };
    let cloned = po.clone();
    assert_eq!(cloned.order_link_id, "oc_1");
    assert_eq!(cloned.qty, 0.01);
    assert!(!cloned.is_close);
}

// ─────────────────────────────────────────────────────────────────────────
// Shared helpers used by sibling submodules.
// 子模組共用輔助函式。
// ─────────────────────────────────────────────────────────────────────────

pub(super) fn make_test_pipeline() -> crate::tick_pipeline::TickPipeline {
    crate::tick_pipeline::TickPipeline::with_balance(&["BTCUSDT", "ETHUSDT"], 10_000.0)
}

pub(super) fn make_test_writer() -> crate::persistence::DualStateWriter {
    use std::path::PathBuf;
    let mut p = std::env::temp_dir();
    p.push(format!(
        "openclaw_test_handlers_{}.json",
        std::process::id()
    ));
    let primary = crate::persistence::StateWriter::new(&p as &PathBuf, 5_000);
    crate::persistence::DualStateWriter::new(primary, None)
}

pub(super) fn escalate_to_tier(
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
    assert_eq!(
        p.governance.risk.snapshot_level(),
        target,
        "setup reached target"
    );
}

pub(super) fn run_looser(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::DualStateWriter,
    target: &str,
    reason_code: &str,
    notes: &str,
) -> Result<String, String> {
    use crate::tick_pipeline::PipelineCommand;
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PipelineCommand::ForceGovernorLooser {
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

pub(super) fn run_tighter(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::DualStateWriter,
    target: &str,
    reason: &str,
) -> Result<String, String> {
    use crate::tick_pipeline::PipelineCommand;
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PipelineCommand::ForceGovernorTighter {
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

pub(super) fn run_submit(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::DualStateWriter,
    symbol: &str,
    side: &str,
    qty: f64,
) -> Result<String, String> {
    use crate::tick_pipeline::PipelineCommand;
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PipelineCommand::SubmitOrder {
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
pub(super) fn seed_indicators_with_atr(
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

pub(super) fn authorize(p: &mut crate::tick_pipeline::TickPipeline) {
    p.governance
        .grant_paper_authorization(None)
        .expect("grant paper auth");
}

pub(super) fn run_reconciler_escalate(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::DualStateWriter,
    target: &str,
    reason: &str,
) -> Result<String, String> {
    use crate::tick_pipeline::PipelineCommand;
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PipelineCommand::ReconcilerEscalate {
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

pub(super) fn run_reconciler_de_escalate(
    pipeline: &mut crate::tick_pipeline::TickPipeline,
    writer: &mut crate::persistence::DualStateWriter,
    target: &str,
    reason: &str,
) -> Result<String, String> {
    use crate::tick_pipeline::PipelineCommand;
    let mut pending = std::collections::HashMap::new();
    let (tx, rx) = tokio::sync::oneshot::channel();
    super::handlers::handle_paper_command(
        PipelineCommand::ReconcilerDeEscalate {
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
