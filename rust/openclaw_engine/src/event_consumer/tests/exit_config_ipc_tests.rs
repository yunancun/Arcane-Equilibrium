//! EDGE-DIAG-1-FUP-IPC: ExitConfig IPC hot-reload regression tests.
//! EDGE-DIAG-1-FUP-IPC：ExitConfig IPC 熱重載回歸測試。

use super::{make_test_pipeline, make_test_writer};

/// EN: Round-trip proof that all 7 `exit_*` fields on `UpdateRiskConfig` land
///   atomically on `RiskConfig.exit` via `ConfigStore::apply_patch`, the
///   version counter bumps, and fields NOT in the patch (`shadow_enabled` and
///   `stale_peak_ms` — covered by the ExitConfig struct but outside the 7 IPC
///   fields) keep their prior value. This guards against regressions that
///   would silently drop some exit fields on the IPC → event_consumer hop,
///   which was the entire reason EDGE-DIAG-1-FUP-IPC exists: pre-fix there
///   was NO IPC path so ANY exit param change required TOML + rebuild.
/// 中文：往返驗證 — `UpdateRiskConfig` 的 7 個 `exit_*` 欄位透過
///   `ConfigStore::apply_patch` 原子落入 `RiskConfig.exit`；版本號遞增；
///   未在 patch 的欄位（`shadow_enabled` / `stale_peak_ms`）保持原值。
///   防止日後 IPC → event_consumer 跳時靜默丟某些 exit 欄位的 regression。
#[test]
fn test_ipc_risk_update_apply_exit_fields_round_trip() {
    use crate::config::{ConfigStore, RiskConfig};
    use crate::tick_pipeline::PipelineCommand;
    use std::sync::Arc;

    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    // Wire a live ConfigStore<RiskConfig> with default ExitConfig.
    // `shadow_enabled` stays default (false) throughout — it is outside the 7
    // IPC fields and must not be touched by any apply_patch mutation.
    // 接線 ConfigStore<RiskConfig>，ExitConfig 採預設；`shadow_enabled`
    // 不在 7 個 IPC 欄位內，任何 apply_patch 都不應觸碰。
    let base_cfg = RiskConfig::default();
    let base_shadow_enabled = base_cfg.exit.shadow_enabled;
    let base_stale_peak_ms = base_cfg.exit.stale_peak_ms;
    base_cfg.validate().expect("default cfg validates");
    let risk_store = Arc::new(ConfigStore::new(base_cfg));
    pipeline.set_risk_store(Arc::clone(&risk_store));
    let version_before = risk_store.version();

    // All 7 new fields set to non-default, mutually consistent values that
    // preserve `giveback_floor <= giveback_base` and other validate() checks.
    // 全部 7 個新欄位設為「非預設且彼此一致」的值，保留 validate() 不變量。
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
            cost_gate_min_confidence: None,
            cost_gate_k_base: None,
            cost_gate_k_medium: None,
            cost_gate_k_small: None,
            adx_trending_threshold: None,
            boot_cooldown_ms: None,
            signals_heartbeat_ms: None,
            exit_missing_edge_fallback_bps: Some(7.5),
            exit_min_net_floor_bps: Some(8.0),
            exit_min_hold_secs: Some(45.0),
            exit_min_peak_atr_norm: Some(0.75),
            exit_giveback_base: Some(1.2),
            exit_giveback_slope: Some(0.25),
            exit_giveback_floor: Some(0.4),
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );

    // Assert all 7 landed on the ArcSwap-backed config, plus version bump.
    // 驗證 7 個欄位皆已原子落入 ArcSwap 配置，且版本號遞增。
    let after = risk_store.load();
    assert_eq!(
        after.exit.missing_edge_fallback_bps, 7.5,
        "missing_edge_fallback_bps must round-trip"
    );
    assert_eq!(
        after.exit.min_net_floor_bps, 8.0,
        "min_net_floor_bps must round-trip"
    );
    assert_eq!(
        after.exit.min_hold_secs, 45.0,
        "min_hold_secs must round-trip"
    );
    assert_eq!(
        after.exit.min_peak_atr_norm, 0.75,
        "min_peak_atr_norm must round-trip"
    );
    assert_eq!(after.exit.giveback_base, 1.2, "giveback_base must round-trip");
    assert_eq!(
        after.exit.giveback_slope, 0.25,
        "giveback_slope must round-trip"
    );
    assert_eq!(
        after.exit.giveback_floor, 0.4,
        "giveback_floor must round-trip"
    );
    assert!(
        risk_store.version() > version_before,
        "ConfigStore version must bump on successful patch"
    );
    // Non-patched fields unchanged. / 未被 patch 的欄位保持原值。
    assert_eq!(
        after.exit.shadow_enabled, base_shadow_enabled,
        "shadow_enabled is outside the 7 IPC fields and must remain at prior value"
    );
    assert_eq!(
        after.exit.stale_peak_ms, base_stale_peak_ms,
        "stale_peak_ms is outside the 7 IPC fields and must remain at prior value"
    );
}

/// EN: Validation gate — when an exit patch violates `ExitConfig::validate()`
///   (here `min_hold_secs = -1.0`, which the validate() rule rejects for
///   being finite but negative), `ConfigStore::apply_patch` must roll back
///   ALL exit mutations atomically. No partial state lands; the prior config
///   remains the authoritative snapshot; the store version does NOT advance.
///   This preserves Rust's fail-closed invariant for risk config writes.
/// 中文：驗證閘 — 當 exit 補丁違反 `ExitConfig::validate()`（此處
///   `min_hold_secs = -1.0`，finite 但為負被拒絕），`ConfigStore::apply_patch`
///   必須原子回滾所有 exit 修改；沒有部分狀態落入；舊配置維持權威；版本號
///   不遞增。保留 Rust 風控寫入的 fail-closed 不變量。
#[test]
fn test_ipc_risk_update_exit_validation_rejects_invalid() {
    use crate::config::{ConfigStore, RiskConfig};
    use crate::tick_pipeline::PipelineCommand;
    use std::sync::Arc;

    let mut pipeline = make_test_pipeline();
    let mut writer = make_test_writer();
    let mut pending = std::collections::HashMap::new();

    let base_cfg = RiskConfig::default();
    let base_exit = base_cfg.exit.clone();
    base_cfg.validate().expect("default cfg validates");
    let risk_store = Arc::new(ConfigStore::new(base_cfg));
    pipeline.set_risk_store(Arc::clone(&risk_store));
    let version_before = risk_store.version();

    // Mix one valid-looking change (`giveback_base = 1.5`) with one invalid
    // one (`min_hold_secs = -1.0`) so we prove the all-or-nothing rollback:
    // the valid field MUST also revert because apply_patch is atomic on
    // validate() failure. Without atomicity we'd see giveback_base=1.5 leak.
    // 混入一個看似合法的 `giveback_base=1.5` 與違規的 `min_hold_secs=-1.0`，
    // 證實 apply_patch 在 validate() 失敗時對 ArcSwap 的全或無 rollback：
    // 合法欄位也必須回滾（若非原子即會看到 1.5 漏出）。
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
            cost_gate_min_confidence: None,
            cost_gate_k_base: None,
            cost_gate_k_medium: None,
            cost_gate_k_small: None,
            adx_trending_threshold: None,
            boot_cooldown_ms: None,
            signals_heartbeat_ms: None,
            exit_missing_edge_fallback_bps: None,
            exit_min_net_floor_bps: None,
            exit_min_hold_secs: Some(-1.0), // invariant violation
            exit_min_peak_atr_norm: None,
            exit_giveback_base: Some(1.5), // valid-looking but must roll back
            exit_giveback_slope: None,
            exit_giveback_floor: None,
        },
        &mut pipeline,
        &mut writer,
        &mut pending,
    );

    // Rollback proof: every exit field still equals the pre-patch baseline.
    // All-or-nothing guarantee — giveback_base must NOT leak 1.5.
    // 回滾驗證：所有 exit 欄位仍等於 pre-patch 基線；giveback_base 不得漏出 1.5。
    let after = risk_store.load();
    assert_eq!(
        after.exit.min_hold_secs, base_exit.min_hold_secs,
        "invalid min_hold_secs must be rejected"
    );
    assert_eq!(
        after.exit.giveback_base, base_exit.giveback_base,
        "all-or-nothing: even the valid giveback_base must roll back on validate() failure"
    );
    assert_eq!(
        after.exit.missing_edge_fallback_bps, base_exit.missing_edge_fallback_bps,
        "untouched missing_edge_fallback_bps must stay at baseline"
    );
    assert_eq!(
        risk_store.version(),
        version_before,
        "failed validate() must NOT bump ConfigStore version"
    );
}
