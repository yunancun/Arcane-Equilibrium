//! Risk-config IPC handlers: live hot-patch of 21 risk parameters, runtime
//! status snapshot, and the safe per-symbol consecutive-loss counter reset.
//!
//! MODULE_NOTE (EN): Split out of `handlers.rs` in E5-P1-3. These handlers are
//!   pure JSON parsers + `PipelineCommand` senders; all clamping / validation
//!   lives on the event-consumer side so a single source of truth governs the
//!   numeric bounds. `parse_opt_opt_f64` is a private helper used only by
//!   `handle_update_risk_config` and stays file-local.
//! MODULE_NOTE (中)：E5-P1-3 將 `handlers.rs` 按領域拆分後的「風控」桶。
//!   三個 handler 僅負責 JSON 解析與 PipelineCommand 發送；所有 clamp 與
//!   驗證邏輯均在事件消費者側，確保單一真理源。`parse_opt_opt_f64` 為
//!   `handle_update_risk_config` 獨用的檔案內私有輔助。
//!
//! E5-P1-5-FUP: second adopter of `super::super::param_extractor`.  The plain
//!   optional `as_f64()` / `as_u64()` / `as_bool()` single-value reads use the
//!   typed `optional_*` helpers.  The tri-state `parse_opt_opt_f64` (absent
//!   vs. explicit JSON `null` vs. number) is NOT migrated because
//!   `param_extractor` only exposes two-state optionals — keeping `parse_opt_opt_f64`
//!   local preserves the disable-via-null semantic that `trailing_stop_pct`
//!   and peers rely on.
//! E5-P1-5-FUP：本檔為 `super::super::param_extractor` 的第二個採用點。
//!   單值可選 `as_f64()` / `as_u64()` / `as_bool()` 直接改走 `optional_*`。
//!   三態 `parse_opt_opt_f64`（缺失 vs. JSON `null` vs. 數字）不改；
//!   `param_extractor` 只提供二態可選，保留本地 `parse_opt_opt_f64` 以
//!   維持 `trailing_stop_pct` 等「以 null 關閉」的語意。

use super::super::param_extractor::{optional_bool, optional_f64, optional_u64};
use super::super::*;
use crate::exit_features::ExitConfig;

/// Update risk config at runtime (GUI → Python → IPC → Rust engine).
/// 運行時更新風控配置。
/// Parse Option<Option<f64>> from JSON: absent=None, null=Some(None), number=Some(Some(x)).
/// 解析 JSON 中的 Option<Option<f64>>：不存在=None，null=Some(None)，數字=Some(Some(x))。
fn parse_opt_opt_f64(params: &serde_json::Value, key: &str) -> Option<Option<f64>> {
    match params.get(key) {
        None => None,                         // key absent = no change
        Some(v) if v.is_null() => Some(None), // key: null = disable
        Some(v) => v.as_f64().map(Some),      // key: 2.5 = enable with value
    }
}

pub(in crate::ipc_server) async fn handle_update_risk_config(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
    params: &serde_json::Value,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "no paper command channel".to_string())
        }
    };

    // Parse all risk params / 解析所有風控參數
    // E5-P1-5-FUP: two-state optionals via `optional_*`; tri-state via
    //   the file-local `parse_opt_opt_f64` (null → explicit disable).
    // E5-P1-5-FUP：二態用 `optional_*`，三態仍走本地 `parse_opt_opt_f64`
    //   （null → 顯式關閉）。
    let hard_stop_pct = optional_f64(params, "hard_stop_pct");
    let p1_risk_pct = optional_f64(params, "p1_risk_pct");
    let trailing_stop_pct = parse_opt_opt_f64(params, "trailing_stop_pct");
    let trailing_activation_pct = parse_opt_opt_f64(params, "trailing_activation_pct");
    let time_stop_hours = parse_opt_opt_f64(params, "time_stop_hours");
    let atr_multiplier = parse_opt_opt_f64(params, "atr_multiplier");
    let take_profit_pct = parse_opt_opt_f64(params, "take_profit_pct");
    let max_leverage = optional_f64(params, "max_leverage");
    let max_drawdown_pct = optional_f64(params, "max_drawdown_pct");
    let max_same_direction_positions =
        optional_u64(params, "max_same_direction_positions").map(|v| v as usize);
    // RRC-1-A3: H0Gate shadow mode toggle / H0 門控影子模式切換
    let h0_shadow_mode = optional_bool(params, "h0_shadow_mode");
    // PNL-7: agent-tunable dynamic-stop knobs / PNL-7：Agent 可調動態止損參數
    let dynamic_stop_base_ratio = optional_f64(params, "dynamic_stop_base_ratio");
    let dynamic_stop_cap_ratio = optional_f64(params, "dynamic_stop_cap_ratio");
    let trailing_min_rr_ratio = optional_f64(params, "trailing_min_rr_ratio");
    // Session 12: cost-gate + regime + boot cooldown
    let cost_gate_min_confidence = optional_f64(params, "cost_gate_min_confidence");
    let cost_gate_k_base = optional_f64(params, "cost_gate_k_base");
    let cost_gate_k_medium = optional_f64(params, "cost_gate_k_medium");
    let cost_gate_k_small = optional_f64(params, "cost_gate_k_small");
    let adx_trending_threshold = optional_f64(params, "adx_trending_threshold");
    let boot_cooldown_ms = optional_u64(params, "boot_cooldown_ms");
    let signals_heartbeat_ms = optional_u64(params, "signals_heartbeat_ms");
    // EDGE-DIAG-1-FUP-IPC: ExitConfig hot-reload fields. Each field maps 1:1
    //   to `RiskConfig.exit.<name>` and is applied via ConfigStore::apply_patch
    //   on the event-consumer side (all-or-nothing validate()); the wire
    //   protocol here is a simple `exit_<name>` number → Option<f64>. Pre-FUP
    //   these were TOML-only and required an engine rebuild for any change.
    // EDGE-DIAG-1-FUP-IPC：ExitConfig 熱重載欄位。每個欄位 1:1 對應
    //   `RiskConfig.exit.<name>`，由 event-consumer 端透過 ConfigStore::apply_patch
    //   套用（validate() 全或無）；wire 協定為 `exit_<name>` 數值 → Option<f64>。
    //   本 FUP 前僅 TOML 可改且需引擎 rebuild 才生效。
    let exit_missing_edge_fallback_bps = optional_f64(params, "exit_missing_edge_fallback_bps");
    let exit_min_net_floor_bps = optional_f64(params, "exit_min_net_floor_bps");
    let exit_min_hold_secs = optional_f64(params, "exit_min_hold_secs");
    let exit_min_peak_atr_norm = optional_f64(params, "exit_min_peak_atr_norm");
    let exit_giveback_base = optional_f64(params, "exit_giveback_base");
    let exit_giveback_slope = optional_f64(params, "exit_giveback_slope");
    let exit_giveback_floor = optional_f64(params, "exit_giveback_floor");

    // At least one param must be provided / 至少需要一個參數
    let has_any = hard_stop_pct.is_some()
        || p1_risk_pct.is_some()
        || trailing_stop_pct.is_some()
        || trailing_activation_pct.is_some()
        || time_stop_hours.is_some()
        || atr_multiplier.is_some()
        || take_profit_pct.is_some()
        || max_leverage.is_some()
        || max_drawdown_pct.is_some()
        || max_same_direction_positions.is_some()
        || h0_shadow_mode.is_some()
        || dynamic_stop_base_ratio.is_some()
        || dynamic_stop_cap_ratio.is_some()
        || trailing_min_rr_ratio.is_some()
        || cost_gate_min_confidence.is_some()
        || cost_gate_k_base.is_some()
        || cost_gate_k_medium.is_some()
        || cost_gate_k_small.is_some()
        || adx_trending_threshold.is_some()
        || boot_cooldown_ms.is_some()
        || signals_heartbeat_ms.is_some()
        || exit_missing_edge_fallback_bps.is_some()
        || exit_min_net_floor_bps.is_some()
        || exit_min_hold_secs.is_some()
        || exit_min_peak_atr_norm.is_some()
        || exit_giveback_base.is_some()
        || exit_giveback_slope.is_some()
        || exit_giveback_floor.is_some();
    if !has_any {
        return JsonRpcResponse::error(
            id,
            ERR_INVALID_REQUEST,
            "need at least one risk parameter".to_string(),
        );
    }

    let _ = tx.send(PipelineCommand::UpdateRiskConfig {
        hard_stop_pct,
        trailing_stop_pct,
        trailing_activation_pct,
        time_stop_hours,
        atr_multiplier,
        take_profit_pct,
        max_leverage,
        max_drawdown_pct,
        max_same_direction_positions,
        p1_risk_pct,
        h0_shadow_mode,
        dynamic_stop_base_ratio,
        dynamic_stop_cap_ratio,
        trailing_min_rr_ratio,
        cost_gate_min_confidence,
        cost_gate_k_base,
        cost_gate_k_medium,
        cost_gate_k_small,
        adx_trending_threshold,
        boot_cooldown_ms,
        signals_heartbeat_ms,
        exit_missing_edge_fallback_bps,
        exit_min_net_floor_bps,
        exit_min_hold_secs,
        exit_min_peak_atr_norm,
        exit_giveback_base,
        exit_giveback_slope,
        exit_giveback_floor,
    });
    JsonRpcResponse::success(id, serde_json::json!({ "updated": true }))
}

/// ARCH-RC1 1C-3-B: Get Rust-native risk runtime status snapshot.
/// Routes the call through the paper command channel so the response is
/// built from live `TickPipeline` state owned by the event consumer task.
/// ARCH-RC1 1C-3-B：獲取 Rust 原生風控運行時狀態快照。
pub(in crate::ipc_server) async fn handle_risk_runtime_status(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::GetRiskRuntimeStatus {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(json_str))) => match serde_json::from_str::<serde_json::Value>(&json_str) {
            Ok(v) => JsonRpcResponse::success(id, v),
            Err(e) => JsonRpcResponse::error(id, ERR_INTERNAL, format!("parse status: {e}")),
        },
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// ARCH-RC1 1C-3-B: Clear per-symbol consecutive-loss counters (safe reset,
/// does NOT touch RiskGovernor tier — for governor override see 1C-3-B-2).
/// ARCH-RC1 1C-3-B：清除 per-symbol 連虧計數器（安全重置，不影響 governor tier）。
pub(in crate::ipc_server) async fn handle_clear_consecutive_losses(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ClearConsecutiveLosses {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(msg))) => JsonRpcResponse::success(id, serde_json::json!({ "result": msg })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

/// P1-5 A2: operator-driven drawdown baseline reset. Sends
/// `PipelineCommand::ResetDrawdownBaseline` to the per-engine consumer and
/// awaits the oneshot reply (fires AFTER the in-memory reset + DB
/// `paper_state_checkpoint` DELETE). Timeout matches the other risk IPC
/// handlers (5s) so a stuck event loop surfaces as an explicit IPC error
/// instead of a silently-hung HTTP request.
///
/// Per Root Principle #5 (生存>利潤): this IPC is the ONLY legitimate way to
/// lower `peak_balance` at runtime; the Python FastAPI route fronting it MUST
/// attach operator auth + a `change_audit_log` row (Root Principle #8).
///
/// P1-5 A2：operator 手動重置 drawdown 基準。發送 ResetDrawdownBaseline、
/// 等待 oneshot 回覆（於記憶體重置 + DB DELETE 完成後觸發），5s 超時與其他
/// 風控 IPC 對齊。根原則 #5：此 IPC 是 runtime 唯一合法降低 peak_balance
/// 的路徑；Python 路由須附加 operator 授權 + change_audit_log（根原則 #8）。
pub(in crate::ipc_server) async fn handle_reset_drawdown_baseline(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => {
            return JsonRpcResponse::error(id, ERR_INTERNAL, "paper command channel not configured")
        }
    };
    let (resp_tx, resp_rx) = tokio::sync::oneshot::channel();
    if let Err(e) = tx.send(PipelineCommand::ResetDrawdownBaseline {
        response_tx: resp_tx,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }
    match tokio::time::timeout(std::time::Duration::from_secs(5), resp_rx).await {
        Ok(Ok(Ok(msg))) => JsonRpcResponse::success(id, serde_json::json!({ "result": msg })),
        Ok(Ok(Err(e))) => JsonRpcResponse::error(id, ERR_INTERNAL, e),
        Ok(Err(_)) => JsonRpcResponse::error(id, ERR_INTERNAL, "response channel dropped"),
        Err(_) => JsonRpcResponse::error(id, ERR_INTERNAL, "timeout waiting for event consumer"),
    }
}

// ─────────────────────────────────────────────────────────────────────────
// EDGE-P1b T3 (2026-04-26): IPC method `restore_exit_config_defaults`.
// EDGE-P1b T3：IPC method `restore_exit_config_defaults` — 緊急回滾路徑。
// ─────────────────────────────────────────────────────────────────────────

/// EDGE-P1b T3: Restore the IPC-writable subset of `ExitConfig` to the
/// hardcoded baseline. Provides an emergency rollback path after a
/// calibrator bind goes wrong (e.g. percentile drift locking the
/// pipeline into too-tight thresholds with no operator-friendly path
/// back). Sends `PipelineCommand::UpdateRiskConfig` with all 7
/// IPC-writable `exit_*` fields set to `ExitConfig::default()` values;
/// the consumer-side path is `risk_store.apply_patch()` with
/// `RiskConfig::validate()` (atomic all-or-nothing — same contract as
/// any other operator-driven exit hot-reload).
///
/// **Caveat — TOML-only fields**: `stale_peak_ms` and `shadow_enabled`
/// are not IPC-wired (per `update_risk_config` 7-field shape). Restoring
/// those requires a TOML edit on `risk_config_<engine>.toml` followed
/// by a `reload_risk_config` IPC call. The response payload exposes
/// this via the `toml_only_fields_skipped` array so the operator CLI /
/// FastAPI route fronting this method can surface the asymmetry.
///
/// **Why a new IPC method, not just `update_risk_config(7 default values)`**:
/// (a) clarity at audit time (operator intent = "restore", not "patch");
/// (b) avoids accidental mid-bind cancellation if calibrator is
/// concurrently emitting a partial patch (this method always sends
/// the full set);
/// (c) future Phase B automation can wrap this method with extra
/// audit hooks (change_audit_log entry per Root Principle #8).
///
/// EDGE-P1b T3：將 `ExitConfig` 的 IPC 可寫子集恢復為硬編碼 baseline，提供
/// calibrator 後緊急回滾路徑（避免百分位漂移將管線鎖在過緊閾值且 operator
/// 無 friendly 退路）。發送 `PipelineCommand::UpdateRiskConfig`，把 7 個 IPC
/// 可寫的 `exit_*` 欄位設為 `ExitConfig::default()` 值；consumer 端走
/// `risk_store.apply_patch()` + `RiskConfig::validate()`（原子全或無契約，
/// 與其他 operator 驅動的 exit 熱重載一致）。
///
/// 注意（TOML-only 欄位）：`stale_peak_ms` / `shadow_enabled` 不在 IPC
/// （per `update_risk_config` 7 欄位形狀），其恢復需編輯
/// `risk_config_<engine>.toml` 並呼叫 `reload_risk_config` IPC；本回應在
/// `toml_only_fields_skipped` 陣列暴露此差異，讓上游 operator CLI / FastAPI
/// 路由能告知不對稱性。
///
/// 為何另開新 IPC method 而非 `update_risk_config(7 default values)`：
///   (a) audit 時意圖明確（operator = "restore"，非 "patch"）
///   (b) 若 calibrator 同時發部分 patch，本 method 一律發完整集合避免半套狀態
///   (c) Phase B 自動化可在此 method 包額外 audit hook（按根原則 #8 寫
///       change_audit_log）
pub(in crate::ipc_server) async fn handle_restore_exit_config_defaults(
    id: serde_json::Value,
    pipeline_cmd_tx: &Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>>,
) -> JsonRpcResponse {
    let tx = match pipeline_cmd_tx {
        Some(tx) => tx,
        None => return JsonRpcResponse::error(id, ERR_INTERNAL, "no paper command channel"),
    };

    // Load the hardcoded baseline. Using `ExitConfig::default()` keeps the
    // baseline in sync with ExitConfig schema — if a future Default tweak
    // lands, restore reflects it without touching this handler.
    // 從 `ExitConfig::default()` 取 baseline，確保 schema 演進時自動同步。
    let baseline = ExitConfig::default();

    // 7 IPC-wired fields → wrapped in Option<f64> for UpdateRiskConfig wire.
    // The dispatch in `event_consumer/handlers/risk.rs` writes only the
    // fields wrapped in Some(_), so other risk params remain untouched.
    // 7 個 IPC 可寫欄位包成 Option<f64>；dispatch 端只寫 Some(_) 包裝者，
    // 其他風控參數不動。
    let exit_missing_edge_fallback_bps = Some(baseline.missing_edge_fallback_bps);
    let exit_min_net_floor_bps = Some(baseline.min_net_floor_bps);
    let exit_min_hold_secs = Some(baseline.min_hold_secs);
    let exit_min_peak_atr_norm = Some(baseline.min_peak_atr_norm);
    let exit_giveback_base = Some(baseline.giveback_base);
    let exit_giveback_slope = Some(baseline.giveback_slope);
    let exit_giveback_floor = Some(baseline.giveback_floor);

    // Send a fully-Some `UpdateRiskConfig` with non-exit risk fields all
    // None. This relies on the `has_exit_patch` branch in event_consumer/
    // handlers/risk.rs::handle_update_risk_config taking the
    // `risk_store.apply_patch()` path, leaving non-exit settings untouched.
    // 發送只填 exit 欄位、其他全 None 的 `UpdateRiskConfig`；event_consumer 端
    // `has_exit_patch` 分支進 `risk_store.apply_patch()`，其他風控設定不變。
    if let Err(e) = tx.send(PipelineCommand::UpdateRiskConfig {
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
        exit_missing_edge_fallback_bps,
        exit_min_net_floor_bps,
        exit_min_hold_secs,
        exit_min_peak_atr_norm,
        exit_giveback_base,
        exit_giveback_slope,
        exit_giveback_floor,
    }) {
        return JsonRpcResponse::error(id, ERR_INTERNAL, format!("channel send failed: {e}"));
    }

    // Response: surface the baseline that was restored + the TOML-only
    // skipped fields, so the caller can render an operator-friendly diff.
    // The `before` snapshot is intentionally not provided here — the
    // `apply_patch` path on the consumer logs version + before/after at
    // info level, and we keep this response small + side-effect-free.
    // 回應：暴露已 restore 的 baseline + 跳過的 TOML-only 欄位，
    // caller 可渲染 operator 友善 diff；`before` 不提供（consumer 端
    // `apply_patch` 已 info-log version + before/after），保持本回應精簡。
    JsonRpcResponse::success(
        id,
        serde_json::json!({
            "restored": true,
            "fields_restored": [
                "missing_edge_fallback_bps",
                "min_net_floor_bps",
                "min_hold_secs",
                "min_peak_atr_norm",
                "giveback_base",
                "giveback_slope",
                "giveback_floor",
            ],
            "baseline_values": {
                "missing_edge_fallback_bps": baseline.missing_edge_fallback_bps,
                "min_net_floor_bps": baseline.min_net_floor_bps,
                "min_hold_secs": baseline.min_hold_secs,
                "min_peak_atr_norm": baseline.min_peak_atr_norm,
                "giveback_base": baseline.giveback_base,
                "giveback_slope": baseline.giveback_slope,
                "giveback_floor": baseline.giveback_floor,
            },
            "toml_only_fields_skipped": [
                {
                    "field": "stale_peak_ms",
                    "baseline_value": baseline.stale_peak_ms,
                    "reason": "not in update_risk_config IPC; edit risk_config_<engine>.toml + reload_risk_config",
                },
                {
                    "field": "shadow_enabled",
                    "baseline_value": baseline.shadow_enabled,
                    "reason": "binary toggle, not part of bind percentile path",
                },
            ],
        }),
    )
}

// ─────────────────────────────────────────────────────────────────────────
// EDGE-P1b T3 unit tests.
// EDGE-P1b T3 單元測試。
// ─────────────────────────────────────────────────────────────────────────

#[cfg(test)]
mod restore_exit_config_defaults_tests {
    use super::*;

    /// Helper: fake pipeline consumer that captures the latest
    /// `UpdateRiskConfig` send on a oneshot for assertions.
    /// 輔助：fake pipeline consumer，把最新 `UpdateRiskConfig` 透過
    /// oneshot 通道捕獲供斷言。
    fn setup_capturing_channel() -> (
        tokio::sync::mpsc::UnboundedSender<PipelineCommand>,
        tokio::sync::oneshot::Receiver<PipelineCommand>,
    ) {
        let (tx, mut rx) = tokio::sync::mpsc::unbounded_channel::<PipelineCommand>();
        let (capture_tx, capture_rx) = tokio::sync::oneshot::channel::<PipelineCommand>();
        tokio::spawn(async move {
            // Capture only the first command; subsequent commands drained.
            // 只捕獲第一個命令，後續命令 drain。
            let mut capture_tx_opt = Some(capture_tx);
            while let Some(cmd) = rx.recv().await {
                if let Some(slot) = capture_tx_opt.take() {
                    let _ = slot.send(cmd);
                }
            }
        });
        (tx, capture_rx)
    }

    /// Happy path: restore against a hot-patched ExitConfig should
    /// route a full default-valued `UpdateRiskConfig` through the channel
    /// and respond `{ "restored": true, ... }`.
    /// Happy 路徑：restore 對 hot-patched ExitConfig 應透過通道發完整 default
    /// 值的 `UpdateRiskConfig` 並回 `{ "restored": true, ... }`。
    #[tokio::test]
    async fn test_restore_exit_config_defaults_sends_baseline_and_returns_restored_true() {
        let (tx, capture_rx) = setup_capturing_channel();
        let tx_opt = Some(tx);
        let resp = handle_restore_exit_config_defaults(serde_json::json!(20001), &tx_opt).await;

        // Assert response shape.
        // 斷言回應形狀。
        assert!(
            resp.error.is_none(),
            "happy path must not error: {:?}",
            resp.error
        );
        let result = resp.result.expect("result must be present");
        assert_eq!(result.get("restored"), Some(&serde_json::json!(true)));
        let fields_restored = result
            .get("fields_restored")
            .expect("fields_restored must be in response");
        assert_eq!(
            fields_restored.as_array().map(|a| a.len()),
            Some(7),
            "must restore exactly 7 IPC-wired fields"
        );

        // Capture and inspect the actual UpdateRiskConfig sent.
        // 捕獲並檢查實際發送的 UpdateRiskConfig。
        let cmd = capture_rx
            .await
            .expect("UpdateRiskConfig must reach the channel");
        let baseline = ExitConfig::default();
        match cmd {
            PipelineCommand::UpdateRiskConfig {
                exit_missing_edge_fallback_bps,
                exit_min_net_floor_bps,
                exit_min_hold_secs,
                exit_min_peak_atr_norm,
                exit_giveback_base,
                exit_giveback_slope,
                exit_giveback_floor,
                hard_stop_pct,
                trailing_stop_pct,
                ..
            } => {
                // 7 exit fields must be Some(baseline_value) — bit-exact.
                // 7 個 exit 欄位必為 Some(baseline)；逐位元比對。
                assert_eq!(
                    exit_missing_edge_fallback_bps,
                    Some(baseline.missing_edge_fallback_bps)
                );
                assert_eq!(exit_min_net_floor_bps, Some(baseline.min_net_floor_bps));
                assert_eq!(exit_min_hold_secs, Some(baseline.min_hold_secs));
                assert_eq!(exit_min_peak_atr_norm, Some(baseline.min_peak_atr_norm));
                assert_eq!(exit_giveback_base, Some(baseline.giveback_base));
                assert_eq!(exit_giveback_slope, Some(baseline.giveback_slope));
                assert_eq!(exit_giveback_floor, Some(baseline.giveback_floor));

                // Non-exit fields must be None (no spillover into other
                // risk subsystems).
                // 非 exit 欄位必為 None（不波及其他風控子系統）。
                assert_eq!(hard_stop_pct, None);
                assert_eq!(trailing_stop_pct, None);
            }
            other => panic!("expected UpdateRiskConfig variant, got {:?}", other),
        }

        // Ensure the response carries the TOML-only-fields-skipped notice.
        // 確認回應帶 TOML-only 欄位跳過的告知。
        let toml_skipped = result
            .get("toml_only_fields_skipped")
            .and_then(|v| v.as_array())
            .expect("toml_only_fields_skipped must be a JSON array");
        assert_eq!(
            toml_skipped.len(),
            2,
            "must surface stale_peak_ms + shadow_enabled as skipped"
        );

        assert_eq!(resp.id, serde_json::json!(20001));
    }

    /// Error path: missing channel → ERR_INTERNAL "no paper command channel".
    /// 錯誤路徑：缺通道 → ERR_INTERNAL "no paper command channel"。
    #[tokio::test]
    async fn test_restore_exit_config_defaults_no_channel_returns_internal_error() {
        let tx_opt: Option<tokio::sync::mpsc::UnboundedSender<PipelineCommand>> = None;
        let resp = handle_restore_exit_config_defaults(serde_json::json!(20002), &tx_opt).await;
        let err = resp
            .error
            .expect("missing channel must produce ERR_INTERNAL");
        assert_eq!(err.code, ERR_INTERNAL);
        assert_eq!(err.message, "no paper command channel");
        assert_eq!(resp.id, serde_json::json!(20002));
    }

    /// Restore-after-hotpatch simulation: the test does not actually mutate
    /// any ConfigStore (handler-level only — ConfigStore is in TickPipeline,
    /// integration test path). Instead we verify the *intent* is conveyed
    /// faithfully: the values sent over the channel match
    /// `ExitConfig::default()` regardless of any prior patch state. This
    /// is the value the consumer will pass through to
    /// `risk_store.apply_patch()`, which is independently tested in
    /// `event_consumer/tests/exit_config_ipc_tests.rs` for atomic
    /// validate() rollback.
    /// Restore-after-hotpatch 模擬：本測試不真改 ConfigStore（handler 層僅；
    /// 真正 ConfigStore 整合測試另在 event_consumer/tests）。本測證「意圖
    /// 正確送達」 — 通道上的值無論之前 patch 狀態都等於 `ExitConfig::default()`，
    /// 此值由 consumer 傳給 `risk_store.apply_patch()`，後者的原子 validate
    /// 回滾另在 `event_consumer/tests/exit_config_ipc_tests.rs` 驗。
    #[tokio::test]
    async fn test_restore_exit_config_defaults_value_equals_exit_config_default() {
        let (tx, capture_rx) = setup_capturing_channel();
        let tx_opt = Some(tx);
        let _resp = handle_restore_exit_config_defaults(serde_json::json!(20003), &tx_opt).await;
        let cmd = capture_rx.await.expect("command must be sent");
        let baseline = ExitConfig::default();
        match cmd {
            PipelineCommand::UpdateRiskConfig {
                exit_min_net_floor_bps,
                exit_giveback_base,
                exit_giveback_floor,
                ..
            } => {
                // Spot-check 3 representative values bit-exact against default fns.
                // 抽 3 個代表值與 default fns 逐位元比對。
                assert!((exit_min_net_floor_bps.unwrap() - baseline.min_net_floor_bps).abs() < f64::EPSILON);
                assert!((exit_giveback_base.unwrap() - baseline.giveback_base).abs() < f64::EPSILON);
                assert!((exit_giveback_floor.unwrap() - baseline.giveback_floor).abs() < f64::EPSILON);
            }
            other => panic!("expected UpdateRiskConfig, got {:?}", other),
        }
    }
}
