//! G3-09 cost_edge_advisor unit tests — 24+ cases covering every status
//! transition + edge case (None ratio / NaN / Inf / threshold boundary /
//! staleness / env-gate semantics / stress).
//! G3-09 cost_edge_advisor 單元測試 — 24+ 案例覆蓋全 status 轉換與邊界
//! （None / NaN / Inf / threshold 邊界 / stale / env-gate / 壓力）。
//!
//! MODULE_NOTE (EN): Tests directly drive `advisor::evaluate` (pure fn)
//!   without spawning the daemon — daemon-level concurrency is verified
//!   by the integration test placed alongside this module's `mod.rs`
//!   re-export contract. Forward-compat: if Phase B adds new variants
//!   (`Shadow` / `Gated`), the existing OK/Trigger boundary tests stay
//!   green because they only assert on `status` equality not exhaustivity.
//!
//! MODULE_NOTE (中)：直接測 `advisor::evaluate` 純 fn，daemon 並行語意由整合
//!   測試另驗。Forward-compat：Phase B 加新 variants 不破現有 OK/Trigger
//!   邊界測試（只用 status 相等性而非窮舉）。

use super::advisor::{evaluate, next_status};
use super::types::{CostEdgeAdvisorState, CostEdgeAdvisorStatus};
use super::{is_advisor_env_enabled, unix_now_ms, CostEdgeAdvisor, ENV_ADVISOR_FLAG};
use crate::config::CostEdgeConfig;
use crate::h_state_cache::types::{H5CostStats, HStateSnapshot};

// ---------------------------------------------------------------------------
// Builders / 構造輔助
// ---------------------------------------------------------------------------

/// Build a snapshot with given H5 fields, defaults elsewhere.
/// 建一個只填 H5 的 snapshot，其餘預設。
fn snap_with_h5(
    cost_edge_ratio: Option<f64>,
    data_days: u32,
    ai_spend: f64,
    paper_pnl: f64,
) -> HStateSnapshot {
    HStateSnapshot {
        version: 1,
        fetched_at_ms: 1_700_000_000_000,
        h5: H5CostStats {
            ai_spend_7d_usd: ai_spend,
            paper_pnl_7d_usd: paper_pnl,
            cost_edge_ratio,
            data_days,
        },
        ..Default::default()
    }
}

fn cfg(enabled: bool, threshold: f64) -> CostEdgeConfig {
    CostEdgeConfig {
        enabled,
        trigger_threshold: threshold,
    }
}

const NOW_MS: i64 = 1_700_000_010_000;

// ---------------------------------------------------------------------------
// Disabled status (cfg.enabled == false short-circuit)
// Disabled 狀態（cfg.enabled=false 短路）
// ---------------------------------------------------------------------------

#[test]
fn evaluate_disabled_when_cfg_off_regardless_of_ratio() {
    let snap = snap_with_h5(Some(-2.0), 7, 5.0, -10.0);
    let state = evaluate(&snap, &cfg(false, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Disabled);
    // Threshold is echoed for audit completeness.
    // threshold 為 audit 完整性 echo。
    assert_eq!(state.threshold, -0.5);
    // Disabled state does not echo H5 (short-circuit before snapshot read).
    // Disabled 狀態不 echo H5（在 snapshot 讀前短路）。
    assert!(state.ratio.is_none());
}

#[test]
fn evaluate_disabled_short_circuits_even_when_stale() {
    // is_stale=true alone would normally produce Stale, but Disabled wins
    // because cfg.enabled gate runs first.
    // 單獨 stale=true 應為 Stale，但 Disabled 優先（cfg.enabled gate 先跑）。
    let snap = snap_with_h5(Some(-3.0), 5, 1.0, -3.0);
    let state = evaluate(&snap, &cfg(false, -0.5), true, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Disabled);
}

// ---------------------------------------------------------------------------
// Stale status (is_stale == true and enabled)
// Stale 狀態（is_stale=true 且 enabled）
// ---------------------------------------------------------------------------

#[test]
fn evaluate_stale_preserves_prev_ratio_in_echo() {
    let snap = snap_with_h5(Some(-0.7), 5, 2.0, -1.4);
    let state = evaluate(&snap, &cfg(true, -0.5), true, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Stale);
    // Stale must echo the (last-known) ratio for observability — even if it
    // would normally have triggered. healthcheck reports both the staleness
    // AND the last value.
    // Stale 必 echo（上次的）ratio 供觀察 — 即使該值正常會 Trigger，healthcheck
    // 同時報 staleness 與上次值。
    assert_eq!(state.ratio, Some(-0.7));
}

#[test]
fn evaluate_stale_when_ratio_none_still_stale() {
    let snap = snap_with_h5(None, 0, 0.0, 0.0);
    let state = evaluate(&snap, &cfg(true, -0.5), true, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Stale);
    assert!(state.ratio.is_none());
}

// ---------------------------------------------------------------------------
// WarmUp status (ratio == None, sample insufficient)
// WarmUp 狀態（ratio=None，樣本不足）
// ---------------------------------------------------------------------------

#[test]
fn evaluate_warm_up_when_ratio_none_with_low_data_days() {
    let snap = snap_with_h5(None, 1, 0.0, 0.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::WarmUp);
    assert_eq!(state.data_days, 1);
    assert!(state.ratio.is_none());
}

#[test]
fn evaluate_warm_up_when_ratio_none_with_zero_data_days() {
    let snap = snap_with_h5(None, 0, 0.0, 0.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::WarmUp);
    assert_eq!(state.data_days, 0);
}

// ---------------------------------------------------------------------------
// Anomaly status (ratio is NaN or Inf)
// Anomaly 狀態（ratio 為 NaN/Inf）
// ---------------------------------------------------------------------------

#[test]
fn evaluate_anomaly_on_nan_ratio() {
    let snap = snap_with_h5(Some(f64::NAN), 5, 1.0, 0.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Anomaly);
}

#[test]
fn evaluate_anomaly_on_positive_inf_ratio() {
    let snap = snap_with_h5(Some(f64::INFINITY), 5, 0.0, 1.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Anomaly);
}

#[test]
fn evaluate_anomaly_on_negative_inf_ratio() {
    let snap = snap_with_h5(Some(f64::NEG_INFINITY), 5, 0.0, -1.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Anomaly);
}

// ---------------------------------------------------------------------------
// Trigger status (ratio <= threshold)
// Trigger 狀態（ratio <= threshold）
// ---------------------------------------------------------------------------

#[test]
fn evaluate_trigger_when_ratio_below_threshold() {
    let snap = snap_with_h5(Some(-1.0), 7, 5.0, -5.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Trigger);
    assert_eq!(state.ratio, Some(-1.0));
    assert_eq!(state.threshold, -0.5);
    assert_eq!(state.data_days, 7);
    assert_eq!(state.ai_spend_7d_usd, 5.0);
    assert_eq!(state.paper_pnl_7d_usd, -5.0);
}

#[test]
fn evaluate_trigger_at_exact_threshold_boundary() {
    // ratio == threshold should trigger (per RFC §4.2 line 314 `<=`).
    // ratio == threshold 必 Trigger（RFC §4.2 line 314 `<=`）。
    let snap = snap_with_h5(Some(-0.5), 5, 1.0, -0.5);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Trigger);
}

#[test]
fn evaluate_trigger_with_extreme_negative_ratio() {
    let snap = snap_with_h5(Some(-100.0), 30, 0.01, -1.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Trigger);
}

// ---------------------------------------------------------------------------
// OK status (ratio > threshold)
// OK 狀態（ratio > threshold）
// ---------------------------------------------------------------------------

#[test]
fn evaluate_ok_when_ratio_above_threshold() {
    let snap = snap_with_h5(Some(0.5), 7, 4.0, 2.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Ok);
    assert_eq!(state.ratio, Some(0.5));
}

#[test]
fn evaluate_ok_just_above_threshold() {
    // Strictly above by ε — not Trigger.
    // 嚴格高於 ε — 非 Trigger。
    let snap = snap_with_h5(Some(-0.4999), 5, 1.0, -0.5);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Ok);
}

#[test]
fn evaluate_ok_with_positive_pnl() {
    let snap = snap_with_h5(Some(2.0), 14, 5.0, 10.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Ok);
    assert_eq!(state.ratio, Some(2.0));
    assert_eq!(state.paper_pnl_7d_usd, 10.0);
}

#[test]
fn evaluate_ok_when_ratio_zero_above_negative_threshold() {
    let snap = snap_with_h5(Some(0.0), 5, 5.0, 0.0);
    let state = evaluate(&snap, &cfg(true, -0.5), false, NOW_MS);
    assert_eq!(state.status, CostEdgeAdvisorStatus::Ok);
}

// ---------------------------------------------------------------------------
// Threshold direction sanity (per RFC §2.4 variant A — operator may flip
// to positive threshold; ratio <= threshold still applies)
// 方向 sanity（RFC §2.4 變體 A — operator 可調為正 threshold；ratio<=threshold 仍適用）
// ---------------------------------------------------------------------------

#[test]
fn evaluate_threshold_positive_value_works_correctly() {
    // Operator sets threshold=0.8 (interpreting CLAUDE.md literal): ratio
    // 0.5 should trigger, 1.0 should not.
    // Operator 設 threshold=0.8（採 CLAUDE.md 字面解）：ratio 0.5 Trigger，
    // 1.0 不 Trigger。
    let cfg_positive = cfg(true, 0.8);
    let snap_low = snap_with_h5(Some(0.5), 7, 5.0, 2.5);
    let snap_high = snap_with_h5(Some(1.0), 7, 5.0, 5.0);

    assert_eq!(
        evaluate(&snap_low, &cfg_positive, false, NOW_MS).status,
        CostEdgeAdvisorStatus::Trigger
    );
    assert_eq!(
        evaluate(&snap_high, &cfg_positive, false, NOW_MS).status,
        CostEdgeAdvisorStatus::Ok
    );
}

// ---------------------------------------------------------------------------
// next_status helper parity with evaluate() status
// next_status 與 evaluate() status 一致性
// ---------------------------------------------------------------------------

#[test]
fn next_status_matches_evaluate_status_across_all_paths() {
    let cases: Vec<(HStateSnapshot, bool)> = vec![
        (snap_with_h5(Some(-1.0), 7, 5.0, -5.0), false), // Trigger
        (snap_with_h5(Some(0.5), 7, 5.0, 2.5), false),   // Ok
        (snap_with_h5(None, 0, 0.0, 0.0), false),        // WarmUp
        (snap_with_h5(Some(f64::NAN), 5, 1.0, 0.0), false), // Anomaly
        (snap_with_h5(Some(-2.0), 5, 1.0, -2.0), true),  // Stale
    ];
    let c = cfg(true, -0.5);
    for (snap, stale) in cases {
        let full = evaluate(&snap, &c, stale, NOW_MS);
        let next = next_status(&snap, &c, stale);
        assert_eq!(
            full.status, next,
            "status mismatch: snap.h5={:?} stale={}",
            snap.h5, stale
        );
    }
    // Disabled path
    // Disabled 路徑
    let snap = snap_with_h5(Some(-1.0), 5, 1.0, -1.0);
    let c_off = cfg(false, -0.5);
    assert_eq!(
        evaluate(&snap, &c_off, false, NOW_MS).status,
        next_status(&snap, &c_off, false)
    );
}

// ---------------------------------------------------------------------------
// Status string stability (audit log byte-stability)
// Status 字串穩定性（audit log byte 穩定）
// ---------------------------------------------------------------------------

#[test]
fn status_as_str_is_byte_stable() {
    assert_eq!(CostEdgeAdvisorStatus::Uninitialized.as_str(), "Uninitialized");
    assert_eq!(CostEdgeAdvisorStatus::Disabled.as_str(), "Disabled");
    assert_eq!(CostEdgeAdvisorStatus::WarmUp.as_str(), "WarmUp");
    assert_eq!(CostEdgeAdvisorStatus::Ok.as_str(), "OK");
    assert_eq!(CostEdgeAdvisorStatus::Trigger.as_str(), "Trigger");
    assert_eq!(CostEdgeAdvisorStatus::Stale.as_str(), "Stale");
    assert_eq!(CostEdgeAdvisorStatus::Anomaly.as_str(), "Anomaly");
}

// ---------------------------------------------------------------------------
// CostEdgeAdvisor wrapper: state R/W lock semantics
// CostEdgeAdvisor wrapper：state R/W lock 語意
// ---------------------------------------------------------------------------

#[test]
fn advisor_starts_uninitialized() {
    let a = CostEdgeAdvisor::new();
    let s = a.state();
    assert_eq!(s.status, CostEdgeAdvisorStatus::Uninitialized);
    assert!(s.ratio.is_none());
}

#[test]
fn advisor_store_state_round_trips() {
    let a = CostEdgeAdvisor::new();
    let new_state = CostEdgeAdvisorState::ok(0.7, -0.5, 7, 5.0, 3.5, NOW_MS);
    a.store_state(new_state.clone());
    let read = a.state();
    assert_eq!(read.status, CostEdgeAdvisorStatus::Ok);
    assert_eq!(read.ratio, Some(0.7));
    assert_eq!(read.last_eval_ms, NOW_MS);
}

#[test]
fn advisor_arc_share_is_safe() {
    let a = CostEdgeAdvisor::new_arc();
    let a2 = std::sync::Arc::clone(&a);
    a.store_state(CostEdgeAdvisorState::warm_up(-0.5, 2, NOW_MS));
    let s = a2.state();
    assert_eq!(s.status, CostEdgeAdvisorStatus::WarmUp);
    assert_eq!(s.data_days, 2);
}

// ---------------------------------------------------------------------------
// Env-gate semantics (strict "1" comparison)
// Env-gate 語意（嚴格 `"1"` 比較）
// ---------------------------------------------------------------------------

/// Serialised env-gate test (cargo runs tests in parallel by default; env
/// var mutations race across tests if separated). Combines unset / set=1 /
/// truthy-alias checks into one body that holds the lock for the whole
/// duration. Mutex pattern avoids `#[serial_test]` external dep.
/// 序列化 env-gate 測試（cargo 預設並行跑，env 寫入會 race）。Mutex pattern
/// 避免新加 `serial_test` 依賴。
#[test]
fn env_gate_strict_one_semantics_serialised() {
    use std::sync::Mutex;
    static ENV_LOCK: Mutex<()> = Mutex::new(());
    let _g = ENV_LOCK.lock().unwrap_or_else(|p| p.into_inner());

    // (a) unset → false
    // (a) 未設 → false
    std::env::remove_var(ENV_ADVISOR_FLAG);
    assert!(!is_advisor_env_enabled(), "unset should be disabled");

    // (b) "1" → true
    // (b) "1" → true
    std::env::set_var(ENV_ADVISOR_FLAG, "1");
    assert!(
        is_advisor_env_enabled(),
        r#"strict "1" should enable advisor"#
    );

    // (c) truthy aliases → false (strict-equality semantics)
    // (c) truthy aliases → false（嚴格相等語意）
    for v in &["true", "yes", "TRUE", "0", "", "on"] {
        std::env::set_var(ENV_ADVISOR_FLAG, v);
        assert!(
            !is_advisor_env_enabled(),
            "env value {v:?} should NOT enable advisor"
        );
    }

    // Cleanup so other tests in the crate (which may sample env vars) see
    // the expected default-unset state.
    // 清理：其他 test 可能讀 env，恢復預設未設狀態。
    std::env::remove_var(ENV_ADVISOR_FLAG);
}

// ---------------------------------------------------------------------------
// State factory accuracy
// State 工廠精確性
// ---------------------------------------------------------------------------

#[test]
fn state_uninitialized_factory_zeroes_all_fields() {
    let s = CostEdgeAdvisorState::uninitialized();
    assert_eq!(s.status, CostEdgeAdvisorStatus::Uninitialized);
    assert!(s.ratio.is_none());
    assert_eq!(s.threshold, 0.0);
    assert_eq!(s.data_days, 0);
    assert_eq!(s.ai_spend_7d_usd, 0.0);
    assert_eq!(s.paper_pnl_7d_usd, 0.0);
    assert_eq!(s.last_eval_ms, 0);
    assert_eq!(s.triggered_at_ms, 0);
}

#[test]
fn state_default_equals_uninitialized() {
    let d = CostEdgeAdvisorState::default();
    let u = CostEdgeAdvisorState::uninitialized();
    assert_eq!(d.status, u.status);
}

#[test]
fn state_trigger_factory_sets_triggered_at_ms() {
    let s = CostEdgeAdvisorState::trigger(-1.5, -0.5, 7, 5.0, -7.5, NOW_MS, NOW_MS - 1000);
    assert_eq!(s.status, CostEdgeAdvisorStatus::Trigger);
    assert_eq!(s.triggered_at_ms, NOW_MS - 1000);
    assert_eq!(s.last_eval_ms, NOW_MS);
}

// ---------------------------------------------------------------------------
// unix_now_ms basic monotonicity sanity (not a strict guarantee — just that
// helper does not panic and produces a positive value within reasonable era).
// unix_now_ms 基本單調性 sanity（不嚴格保證 — 只確認不 panic 且回合理紀元）。
// ---------------------------------------------------------------------------

#[test]
fn unix_now_ms_returns_recent_epoch_ms() {
    let t = unix_now_ms();
    // Above year 2020 ms epoch; below year 2100 ms epoch (sanity bound).
    // 2020 年後 / 2100 年前（合理範圍）。
    assert!(t > 1_577_836_800_000); // 2020-01-01
    assert!(t < 4_102_444_800_000); // 2100-01-01
}
