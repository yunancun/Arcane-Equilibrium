//! Event-consumer IPC command dispatch facade. The monolithic `handlers.rs`
//! was split by domain as part of E5-P1-3 to keep each file under the §九
//! 800-line warning threshold. This module:
//!   - defines the public `handle_paper_command` dispatch function
//!   - re-exports `handle_disable_edge_predictor_all` for the mod.rs
//!     interception path and `handle_reload_edge_predictor` for tests
//!   - hosts the test module under `#[cfg(test)]`
//!
//! 事件消費者 IPC 命令分派 facade — E5-P1-3 將舊 handlers.rs 按領域拆分為
//! 多個子模組後，本檔僅負責 (1) 匹配 PipelineCommand 各變體 (2) 將 arm
//! 主體轉發到 domain 子模組的 helper。
//!
//! MODULE_NOTE (EN): Dispatch is preserved 1:1 with the pre-split match so
//!   behaviour is bit-for-bit identical. All domain helpers live in the
//!   sibling submodules `lifecycle`, `strategy_params`, `risk`, and
//!   `edge_predictor`.
//! MODULE_NOTE (中): 分派與拆分前 match 完全 1:1，行為按位元一致；domain
//!   helper 分別位於 lifecycle / strategy_params / risk / edge_predictor。

use super::types::PendingOrder;
use crate::persistence::DualStateWriter;
use crate::tick_pipeline::{PipelineCommand, TickPipeline};
use std::collections::HashMap;

pub(crate) mod edge_estimates;
pub(crate) mod edge_predictor;
mod lifecycle;
mod risk;
mod strategy_params;

// Re-exports for external callers (event_consumer/mod.rs and tests).
// 對外再出口：event_consumer/mod.rs 攔截路徑 + tests.rs 直接呼叫。
pub use edge_predictor::handle_disable_edge_predictor_all;
// `handle_reload_edge_predictor` is pub(crate) for tests only — keep the
// parent-module visibility path `handlers::handle_reload_edge_predictor`
// intact so unit tests can call it as `super::handle_reload_edge_predictor`.
// handle_reload_edge_predictor 僅供測試使用，透過本 mod 再出口維持舊呼叫路徑。
#[cfg(test)]
pub(crate) use edge_predictor::handle_reload_edge_predictor;

/// Apply one PipelineCommand variant to the pipeline. Returns nothing —
/// command outcomes are reported via the optional response_tx oneshot inside
/// each variant.
/// 將一個 PipelineCommand 變體應用到管線；結果通過 oneshot 返回。
pub fn handle_paper_command(
    cmd: PipelineCommand,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
    pending_orders: &mut HashMap<String, PendingOrder>,
) {
    match cmd {
        PipelineCommand::Pause => lifecycle::handle_pause(pipeline, snapshot_writer),
        PipelineCommand::Resume => lifecycle::handle_resume(pipeline, snapshot_writer),
        PipelineCommand::CloseAll => lifecycle::handle_close_all(pipeline, snapshot_writer),
        PipelineCommand::CloseSymbol {
            symbol,
            hint_is_long,
            hint_qty,
        } => lifecycle::handle_close_symbol(
            symbol,
            hint_is_long,
            hint_qty,
            pipeline,
            snapshot_writer,
        ),
        PipelineCommand::Reset { new_balance } => {
            lifecycle::handle_reset(new_balance, pipeline, snapshot_writer, pending_orders)
        }
        // P1-5 A2 · Test-only stub. Production path intercepts this variant
        // in event_consumer/mod.rs to run the DB DELETE too.
        // P1-5 A2：測試專用 stub；生產路徑在 mod.rs 攔截並跑 DB DELETE。
        PipelineCommand::ResetDrawdownBaseline { response_tx } => {
            lifecycle::handle_reset_drawdown_baseline_local(
                response_tx,
                pipeline,
                snapshot_writer,
            )
        }
        // ── Phase 3b: Strategy parameter IPC commands / 策略參數 IPC 命令 ──
        PipelineCommand::UpdateStrategyParams {
            strategy_name,
            params_json,
            response_tx,
        } => strategy_params::handle_update_strategy_params(
            strategy_name,
            params_json,
            response_tx,
            pipeline,
            snapshot_writer,
        ),
        PipelineCommand::GetStrategyParams {
            strategy_name,
            response_tx,
        } => strategy_params::handle_get_strategy_params(strategy_name, response_tx, pipeline),
        PipelineCommand::GetParamRanges {
            strategy_name,
            response_tx,
        } => strategy_params::handle_get_param_ranges(strategy_name, response_tx, pipeline),
        // ── ARCH-RC1 1C-3-B: Risk runtime status + safe counter clear ──
        PipelineCommand::GetRiskRuntimeStatus { response_tx } => {
            risk::handle_get_risk_runtime_status(response_tx, pipeline)
        }
        PipelineCommand::ClearConsecutiveLosses { response_tx } => {
            risk::handle_clear_consecutive_losses(response_tx, pipeline, snapshot_writer)
        }
        // ── ARCH-RC1 1C-3-B-2: Governor manual override (operator escalation) ──
        PipelineCommand::ForceGovernorTighter {
            target_tier,
            reason,
            response_tx,
        } => risk::handle_force_governor_tighter(
            target_tier,
            reason,
            response_tx,
            pipeline,
            snapshot_writer,
        ),
        // ── ARCH-RC1 1C-3-B-2: Governor manual override (operator de-escalation) ──
        PipelineCommand::ForceGovernorLooser {
            target_tier,
            reason_code,
            notes,
            response_tx,
        } => risk::handle_force_governor_looser(
            target_tier,
            reason_code,
            notes,
            response_tx,
            pipeline,
            snapshot_writer,
        ),
        // ── ARCH-RC1 1C-3-F: External paper-side order submission ──
        PipelineCommand::SubmitOrder {
            symbol,
            side,
            qty,
            order_type,
            limit_price,
            confidence,
            strategy,
            response_tx,
        } => lifecycle::handle_submit_order(
            symbol,
            side,
            qty,
            order_type,
            limit_price,
            confidence,
            strategy,
            response_tx,
            pipeline,
            snapshot_writer,
        ),
        // RRC-1-E2: Strategy activate/pause / 策略啟停
        PipelineCommand::SetStrategyActive {
            strategy_name,
            active,
            response_tx,
        } => lifecycle::handle_set_strategy_active(
            strategy_name,
            active,
            response_tx,
            pipeline,
            snapshot_writer,
        ),
        PipelineCommand::UpdateRiskConfig {
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
            // EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): destructure dim 5
            //   of EDGE-P1b T1 calibrator added by this FUP; forwarded to
            //   handle_update_risk_config below.
            // EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：解構本 FUP 新加的
            //   EDGE-P1b T1 calibrator 第 5 維度，forward 給下方
            //   handle_update_risk_config。
            exit_stale_peak_ms,
        } => risk::handle_update_risk_config(
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
            // EDGE-P1b-FUP-STALE-PEAK-IPC: pass through u64 ms wire to
            //   handle_update_risk_config (cast to i64 inside closure).
            // EDGE-P1b-FUP-STALE-PEAK-IPC：把 u64 ms wire 傳給
            //   handle_update_risk_config（closure 內 cast 為 i64）。
            exit_stale_peak_ms,
            pipeline,
            snapshot_writer,
        ),
        PipelineCommand::GetOpenPositionSymbols { response_tx } => {
            risk::handle_get_open_position_symbols(response_tx, pipeline)
        }
        // 3E-3: AddMode and SwitchMode REMOVED — pipelines spawned at startup
        // with fixed PipelineKind. See EngineCommandChannels for per-pipeline routing.
        // 3E-3：AddMode 和 SwitchMode 已移除 — 管線啟動時固定 PipelineKind。
        // ── Phase 6: Reconciler auto-contraction ──
        PipelineCommand::ReconcilerEscalate {
            target_tier,
            reason,
            response_tx,
        } => risk::handle_reconciler_escalate(
            target_tier,
            reason,
            response_tx,
            pipeline,
            snapshot_writer,
        ),
        PipelineCommand::ReconcilerDeEscalate {
            target_tier,
            reason,
            response_tx,
        } => risk::handle_reconciler_de_escalate(
            target_tier,
            reason,
            response_tx,
            pipeline,
            snapshot_writer,
        ),
        // Sync global system mode from Python GUI → engine.
        // 從 Python GUI 同步全局系統模式到引擎。
        PipelineCommand::SetSystemMode { mode, response_tx } => {
            lifecycle::handle_set_system_mode(mode, response_tx, pipeline, snapshot_writer)
        }
        // EDGE-P3-1 Stage 0 · Hot-swap a predictor for a single strategy.
        PipelineCommand::SetEdgePredictorShadow {
            strategy,
            predictor,
            response_tx,
        } => edge_predictor::handle_set_edge_predictor_shadow(
            strategy,
            predictor,
            response_tx,
            pipeline,
        ),
        // EDGE-P3-1 Step 7b · Reload a predictor from an on-disk ONNX artifact.
        PipelineCommand::ReloadEdgePredictor {
            engine,
            strategy,
            path,
            response_tx,
        } => {
            let result = edge_predictor::handle_reload_edge_predictor(
                &engine, &strategy, &path, pipeline,
            );
            let _ = response_tx.send(result);
        }
        // EDGE-P3-1 Stage 0 · Operator kill-switch local dispatch (tests only).
        // Production flow intercepts this variant in event_consumer/mod.rs
        // and calls `handle_disable_edge_predictor_all` with real db_mode +
        // audit_pool. This arm only runs on the in-process test path.
        // EDGE-P3-1 Stage 0 · Operator kill-switch 測試路徑；生產在 mod.rs 攔截。
        PipelineCommand::DisableEdgePredictorAll {
            operator_token,
            reason,
            response_tx,
        } => edge_predictor::handle_disable_edge_predictor_all_local(
            operator_token,
            reason,
            response_tx,
            pipeline,
        ),
        // EDGE-P3-1 Step 7c · ε-greedy shadow-fill passthrough.
        PipelineCommand::EmitShadowFill {
            context_id,
            strategy,
            symbol,
            side,
            features_jsonb,
            prediction_q10,
            prediction_q50,
            prediction_q90,
            cost_bps,
            ts_ms,
        } => edge_predictor::handle_emit_shadow_fill(
            context_id,
            strategy,
            symbol,
            side,
            features_jsonb,
            prediction_q10,
            prediction_q50,
            prediction_q90,
            cost_bps,
            ts_ms,
            pipeline,
        ),
        // EDGE-P3-1 Step 7a · decision_feature writer passthrough.
        PipelineCommand::DecisionFeatureSnapshot {
            context_id,
            ts_ms,
            engine_mode,
            strategy,
            symbol,
            side,
            feature_schema_version,
            feature_schema_hash,
            feature_definition_hash,
            features_jsonb,
        } => edge_predictor::handle_decision_feature_snapshot(
            context_id,
            ts_ms,
            engine_mode,
            strategy,
            symbol,
            side,
            feature_schema_version,
            feature_schema_hash,
            feature_definition_hash,
            features_jsonb,
            pipeline,
        ),
        // ORPHAN-ADOPT-1 Phase 2A · Adopt an exchange-reported orphan.
        PipelineCommand::AdoptOrphan {
            symbol,
            is_long,
            qty,
            entry_price,
            ts_ms,
            owner_strategy,
        } => lifecycle::handle_adopt_orphan(
            symbol,
            is_long,
            qty,
            entry_price,
            ts_ms,
            owner_strategy,
            pipeline,
            snapshot_writer,
        ),
        // ── DYNAMIC-RISK-1: Sharpe-aware sizer status + toggle ──
        PipelineCommand::GetDynamicRiskStatus { response_tx } => {
            risk::handle_get_dynamic_risk_status(response_tx, pipeline)
        }
        PipelineCommand::SetDynamicRiskEnabled {
            enabled,
            response_tx,
        } => risk::handle_set_dynamic_risk_enabled(enabled, response_tx, pipeline),
        // ── F6 PH5-WIRE-1 RELOAD (2026-04-26): re-load edge estimates ──
        // Fire-and-forget; loader is mode-aware (paper / demo / live each read
        // their own JSON), fail-soft on missing/corrupt, no engine fail-close.
        // Fire-and-forget；loader 依模式讀對應 JSON，缺失/損毀走 fail-soft，
        // 引擎絕不 fail-close。
        PipelineCommand::ReloadEdgeEstimates => {
            let _ = edge_estimates::handle_reload_edge_estimates(pipeline);
        }
    }
}

#[cfg(test)]
mod tests;
