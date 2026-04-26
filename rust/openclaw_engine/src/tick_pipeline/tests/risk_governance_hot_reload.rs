// G5-09 sibling: PNL-3 / PNL-4 boot cooldown + regime derivation +
// 1C-3-B risk_runtime_status_json contract + 1C-3-B-2 RiskLevel SM helpers +
// ARCH-RC1 1C-4 hot-reload e2e (5-consumer propagation) +
// PNL-FIX-2 paper_state.charge_fee garbage rejection.
// G5-09 sibling：boot cooldown / regime / SM 升降級 / 5-consumer hot-reload。

use super::super::*;

#[test]
fn test_pnl3_boot_cooldown_stamps_first_tick() {
    // PNL-3: First tick stamps boot_ts_ms; subsequent ticks reuse it.
    // PNL-3：首個 tick 記錄 boot_ts_ms；後續 tick 沿用。
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    assert!(pipeline.boot_ts_ms.is_none());
    pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000_000));
    assert_eq!(pipeline.boot_ts_ms, Some(1_000_000));
    pipeline.on_tick(&super::make_event("BTCUSDT", 50_001.0, 1_010_000));
    assert_eq!(pipeline.boot_ts_ms, Some(1_000_000));
}

#[test]
fn test_pnl4_derive_regime_hurst_priority() {
    use openclaw_core::indicators::{HurstResult, IndicatorSnapshot};
    let pipeline = TickPipeline::new(&["BTCUSDT"]);
    let mut ind = IndicatorSnapshot::default();
    ind.hurst = Some(HurstResult {
        hurst: 0.7,
        regime: "trending".into(),
    });
    assert_eq!(pipeline.derive_regime(Some(&ind)), "trending");
    ind.hurst = Some(HurstResult {
        hurst: 0.3,
        regime: "mean_reverting".into(),
    });
    assert_eq!(pipeline.derive_regime(Some(&ind)), "ranging");
}

#[test]
fn test_pnl4_derive_regime_adx_fallback() {
    use openclaw_core::indicators::{AdxResult, HurstResult, IndicatorSnapshot};
    let pipeline = TickPipeline::new(&["BTCUSDT"]);
    let mut ind = IndicatorSnapshot::default();
    ind.hurst = Some(HurstResult {
        hurst: 0.5,
        regime: "random_walk".into(),
    });
    ind.adx = Some(AdxResult {
        adx: 30.0,
        plus_di: 25.0,
        minus_di: 10.0,
    });
    assert_eq!(pipeline.derive_regime(Some(&ind)), "trending");
    ind.adx = Some(AdxResult {
        adx: 15.0,
        plus_di: 10.0,
        minus_di: 12.0,
    });
    assert_eq!(pipeline.derive_regime(Some(&ind)), "ranging");
}

#[test]
fn test_pnl4_derive_regime_none_default() {
    let pipeline = TickPipeline::new(&["BTCUSDT"]);
    assert_eq!(pipeline.derive_regime(None), "ranging");
}

#[test]
fn test_rc1_risk_runtime_status_no_boot_ts() {
    // 1C-3-B: before first tick, boot_ts_ms is None → remaining = 0
    // 1C-3-B：第一個 tick 之前 boot_ts_ms 為 None → 剩餘 0
    let pipeline = TickPipeline::new(&["BTCUSDT"]);
    let snap = pipeline.risk_runtime_status_json(1_000_000);
    assert_eq!(snap["boot_cooldown_remaining_ms"], 0);
    assert_eq!(snap["paper_paused"], false);
    assert_eq!(snap["session_halted"], false);
    assert!(snap["governor_tier"].is_string());
    assert!(snap["consecutive_losses_by_symbol"].is_object());
}

#[test]
fn test_rc1_risk_runtime_status_boot_cooldown_math() {
    // 1C-3-B: boot at t=1000, cooldown=60s, now=t=11000 → remaining 50s
    // 1C-3-B：boot 時間 1000、冷卻 60s、現在 11000 → 剩 50s
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.boot_ts_ms = Some(1_000);
    pipeline.boot_cooldown_ms = 60_000;
    let snap = pipeline.risk_runtime_status_json(11_000);
    assert_eq!(snap["boot_cooldown_remaining_ms"], 50_000);
    assert_eq!(snap["boot_cooldown_total_ms"], 60_000);
    // Past expiry → saturating to 0
    // 過期 → 飽和到 0
    let snap2 = pipeline.risk_runtime_status_json(999_999_999);
    assert_eq!(snap2["boot_cooldown_remaining_ms"], 0);
}

#[test]
fn test_rc1b2_parse_risk_level_aliases() {
    use openclaw_core::sm::risk_gov::RiskLevel;
    assert_eq!(
        TickPipeline::parse_risk_level("normal").unwrap(),
        RiskLevel::Normal
    );
    assert_eq!(
        TickPipeline::parse_risk_level("CAUTIOUS").unwrap(),
        RiskLevel::Cautious
    );
    assert_eq!(
        TickPipeline::parse_risk_level("circuit_breaker").unwrap(),
        RiskLevel::CircuitBreaker
    );
    assert_eq!(
        TickPipeline::parse_risk_level("CircuitBreaker").unwrap(),
        RiskLevel::CircuitBreaker
    );
    assert_eq!(
        TickPipeline::parse_risk_level("manual_review").unwrap(),
        RiskLevel::ManualReview
    );
    assert!(TickPipeline::parse_risk_level("foo").is_err());
}

#[test]
fn test_rc1b2_governor_cooldown_const_24h() {
    // 1C-3-B-2: 24h = 86_400_000 ms
    // 1C-3-B-2：24h = 86_400_000 ms
    assert_eq!(TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS, 86_400_000);
}

#[test]
fn test_rc1b2_de_escalation_reason_whitelist() {
    let valid = TickPipeline::VALID_DE_ESCALATION_REASONS;
    assert!(valid.contains(&"false_positive"));
    assert!(valid.contains(&"root_cause_fixed"));
    assert!(valid.contains(&"accept_risk"));
    assert!(!valid.contains(&"because_i_said_so"));
    assert_eq!(valid.len(), 3);
}

#[test]
fn test_rc1b2_cooldown_state_setter_and_getter() {
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    assert_eq!(pipeline.last_governor_de_escalation_ms(), None);
    pipeline.set_last_governor_de_escalation_ms(Some(12345));
    assert_eq!(pipeline.last_governor_de_escalation_ms(), Some(12345));
    pipeline.set_last_governor_de_escalation_ms(None);
    assert_eq!(pipeline.last_governor_de_escalation_ms(), None);
}

#[test]
fn test_rc1b2_sm_escalate_then_de_escalate_round_trip() {
    // End-to-end through pipeline.governance.risk: simulate operator
    // first making things tighter then relaxing them. Bypass min_hold_time
    // to keep the test fast.
    // 模擬 operator 先收緊再放鬆。繞過 min_hold_time 加速測試。
    use openclaw_core::sm::risk_gov::{RiskEvent, RiskLevel};
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    pipeline.governance.risk.thresholds.min_hold_time_ms = 0;
    // Tighter: Normal → Cautious
    pipeline
        .governance
        .risk
        .escalate_to(
            RiskLevel::Cautious,
            "operator_ipc: testing",
            RiskEvent::OperatorEscalation,
        )
        .unwrap();
    assert_eq!(
        pipeline.governance.risk.snapshot_level(),
        RiskLevel::Cautious
    );
    // Looser: Cautious → Normal
    pipeline
        .governance
        .risk
        .de_escalate_to(
            RiskLevel::Normal,
            "operator_ipc",
            "operator_ipc:false_positive",
        )
        .unwrap();
    assert_eq!(pipeline.governance.risk.snapshot_level(), RiskLevel::Normal);
}

#[test]
fn test_rc1_risk_runtime_status_consecutive_losses_map() {
    // 1C-3-B: per-symbol map round-trips into JSON object
    // 1C-3-B：per-symbol map 序列化為 JSON object
    let mut pipeline = TickPipeline::new(&["BTCUSDT", "ETHUSDT"]);
    pipeline.consecutive_losses.insert("BTCUSDT".into(), 3);
    pipeline.consecutive_losses.insert("ETHUSDT".into(), 1);
    let snap = pipeline.risk_runtime_status_json(0);
    assert_eq!(snap["consecutive_losses_by_symbol"]["BTCUSDT"], 3);
    assert_eq!(snap["consecutive_losses_by_symbol"]["ETHUSDT"], 1);
}

#[test]
fn test_pnl3_boot_cooldown_default_60s() {
    // PNL-3: default cooldown is 60_000ms when env var not set.
    // PNL-3：未設環境變量時冷卻期默認 60_000ms。
    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
    // Force-set boot_ts_ms then check elapsed math via direct field.
    pipeline.boot_ts_ms = Some(0);
    assert_eq!(pipeline.boot_cooldown_ms, 60_000);
    // Tick at t=30s → still in cooldown
    let in_cd_30s: bool = (30_000u64).saturating_sub(0) < pipeline.boot_cooldown_ms;
    assert!(in_cd_30s);
    // Tick at t=61s → out of cooldown
    let in_cd_61s: bool = (61_000u64).saturating_sub(0) < pipeline.boot_cooldown_ms;
    assert!(!in_cd_61s);
}

// ─── ARCH-RC1 1C-4 hot-reload e2e ───────────────────────────────────
// 驗證 IPC patch_risk_config 後的下一個 tick：5 個下游消費者全部
// 同步看到新值（intent_processor / guardian / paper_state / h0_gate /
// governance.risk.thresholds）。這份硬證據是 1C-4 wrap 的關鍵。
// E2E proof: after a ConfigStore.replace() that simulates an IPC
// patch_risk_config, driving a single on_tick must propagate the new
// RiskConfig snapshot into ALL 5 owned-copy consumers via
// sync_risk_config_if_changed → apply_risk_snapshot.
#[test]
fn test_arch_rc1_hot_reload_e2e_propagates_to_all_5_consumers() {
    use crate::config::{ConfigStore, PatchSource, RiskConfig};
    use std::sync::Arc;

    let mut pipeline = TickPipeline::new(&["BTCUSDT"]);

    // Build a baseline RiskConfig (defaults) and wire it as the live store.
    // 建立預設 RiskConfig 並以 live store 接線。
    let initial = RiskConfig::default();
    let store = Arc::new(ConfigStore::new(initial.clone()));
    pipeline.set_risk_store(Arc::clone(&store));

    // Sanity: initial seed must already be visible across all 5 consumers.
    // 初始 seed 應已同步至 5 個下游。
    assert_eq!(
        pipeline.intent_processor.risk_config().limits.leverage_max,
        initial.limits.leverage_max
    );
    assert_eq!(
        pipeline.intent_processor.guardian_config().max_leverage,
        initial.limits.leverage_max
    );
    assert_eq!(
        pipeline.h0_gate.config().max_open_positions,
        initial.limits.open_positions_max
    );
    assert_eq!(
        pipeline.paper_state.stop_config().hard_stop_pct,
        initial.limits.stop_loss_max_pct
    );
    assert_eq!(
        pipeline.governance.risk.thresholds.drawdown_cautious_pct,
        initial.cascade.drawdown_cautious_pct
    );
    let v0 = store.version();

    // Build a mutated config that differs in fields touched by all 5
    // downstream paths inside apply_risk_snapshot, then atomically
    // replace() — this is exactly what handle_patch_config does after
    // a successful patch_risk_config IPC call.
    // 修改一份新 config（覆蓋 5 條下游路徑各自讀的欄位），用 replace()
    // 原子寫入 — 這正是 IPC patch_risk_config 成功後的行為。
    let mut next = initial.clone();
    next.limits.leverage_max = initial.limits.leverage_max + 1.0;
    next.limits.open_positions_max = initial.limits.open_positions_max + 1;
    next.limits.stop_loss_max_pct = initial.limits.stop_loss_max_pct + 0.5;
    next.anti_cluster.max_same_direction = initial.anti_cluster.max_same_direction + 1;
    next.cascade.drawdown_cautious_pct = initial.cascade.drawdown_cautious_pct + 0.001;
    // Validate the mutated config to make sure we don't accidentally
    // craft an invalid one (defaults + tiny bumps should always pass).
    next.validate().expect("mutated test config must be valid");

    store
        .replace(next.clone(), PatchSource::Operator)
        .expect("replace must succeed");
    assert_eq!(store.version(), v0 + 1);

    // Drive a single tick — sync_risk_config_if_changed runs at the top
    // of on_tick and must apply_risk_snapshot to all 5 consumers.
    // 打一個 tick — sync_risk_config_if_changed 會在 on_tick 頂部執行
    // 並把新快照推到 5 個下游。
    pipeline.on_tick(&super::make_event("BTCUSDT", 50_000.0, 1_000));

    // 1) intent_processor's owned RiskConfig (Gate 0 / cost-edge / dynamic_stop)
    assert_eq!(
        pipeline.intent_processor.risk_config().limits.leverage_max,
        next.limits.leverage_max,
        "consumer #1: intent_processor.risk_config NOT hot-reloaded"
    );
    // 2) Guardian (P0 trade intent veto path)
    let g = pipeline.intent_processor.guardian_config();
    assert_eq!(
        g.max_leverage, next.limits.leverage_max,
        "consumer #2: guardian.max_leverage NOT hot-reloaded"
    );
    assert_eq!(
        g.max_same_direction_positions, next.anti_cluster.max_same_direction as usize,
        "consumer #2: guardian.max_same_direction_positions NOT hot-reloaded"
    );
    // 3) H0Gate (risk-level fields RMW)
    assert_eq!(
        pipeline.h0_gate.config().max_open_positions,
        next.limits.open_positions_max,
        "consumer #3: h0_gate.max_open_positions NOT hot-reloaded"
    );
    // 4) paper_state.stop_config (H0-blocked / paused fallback stops)
    assert!(
        (pipeline.paper_state.stop_config().hard_stop_pct - next.limits.stop_loss_max_pct).abs()
            < 1e-9,
        "consumer #4: paper_state.stop_config.hard_stop_pct NOT hot-reloaded"
    );
    // 5) GovernanceCore.risk.thresholds (6-tier cascade SM)
    assert!(
        (pipeline.governance.risk.thresholds.drawdown_cautious_pct
            - next.cascade.drawdown_cautious_pct)
            .abs()
            < 1e-9,
        "consumer #5: governance.risk.thresholds NOT hot-reloaded"
    );

    // The pipeline must remember the new version so the NEXT tick is a
    // no-op (cheap atomic load + equality, no re-apply).
    // 紀錄版本號避免下個 tick 重複套用。
    assert_eq!(pipeline.risk_config_version_seen, store.version());
}

/// PNL-FIX-2: charge_fee() helper rejects non-positive / non-finite inputs
/// so a malformed fee_rate cannot corrupt balance. Locks the safety guard.
/// PNL-FIX-2：charge_fee 必須拒絕非正或非有限值，避免費率異常污染餘額。
#[test]
fn test_paper_state_charge_fee_rejects_garbage() {
    let mut pipeline = TickPipeline::with_kind(&["BTCUSDT"], 1_000.0, PipelineKind::Paper);
    let bal0 = pipeline.paper_state.balance();
    pipeline.paper_state.charge_fee(0.0);
    pipeline.paper_state.charge_fee(-5.0);
    pipeline.paper_state.charge_fee(f64::NAN);
    pipeline.paper_state.charge_fee(f64::INFINITY);
    assert!(
        (pipeline.paper_state.balance() - bal0).abs() < 1e-9,
        "garbage fees must not move balance"
    );
    // A real fee must still apply.
    // 真實費用仍應扣除。
    pipeline.paper_state.charge_fee(1.50);
    assert!((bal0 - pipeline.paper_state.balance() - 1.50).abs() < 1e-9);
}
