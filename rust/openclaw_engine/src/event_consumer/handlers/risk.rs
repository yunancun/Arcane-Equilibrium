//! Risk-domain IPC command handlers (risk runtime status, consecutive-loss
//! counters, risk config setters, governor manual overrides, reconciler-driven
//! escalate/de-escalate, dynamic-risk sizer toggle, open-position symbols).
//! Extracted from the legacy monolith as part of E5-P1-3.
//!
//! 風控域 IPC 命令處理器 — E5-P1-3 從 handlers.rs 拆出。
//!
//! MODULE_NOTE (EN): All numeric setters preserve the pre-split clamp ranges
//!   (I-09) and ordering. The governor 24h cooldown + CB/MR hard lock in
//!   ForceGovernorLooser are kept intact — this is an IPC-layer defence layer
//!   and must not be relaxed during mechanical refactor.
//! MODULE_NOTE (中): 所有數值 setter 維持拆分前的 I-09 鉗制範圍與順序；
//!   ForceGovernorLooser 的 24h 冷卻與 CB/MR 硬鎖在機械性重構中不得放鬆。

use crate::persistence::DualStateWriter;
use crate::tick_pipeline::TickPipeline;
use tracing::{info, warn};

/// ARCH-RC1 1C-3-B · EN: Serialise the risk runtime snapshot (pipeline
///   governance + engine clocks) into a JSON string and return it through
///   the response channel.
/// ARCH-RC1 1C-3-B · 中文：序列化風控執行時快照並透過 oneshot 回傳。
pub(super) fn handle_get_risk_runtime_status(
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let now_ms = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_millis() as u64)
        .unwrap_or(0);
    let snapshot = pipeline.risk_runtime_status_json(now_ms);
    let _ = response_tx.send(Ok(snapshot.to_string()));
}

/// ARCH-RC1 1C-3-B · EN: Clear all consecutive-loss counters (one entry per
///   symbol). Flushes the snapshot and reports the count cleared.
/// ARCH-RC1 1C-3-B · 中文：清空每個交易對的連虧計數器並回報清除數量。
pub(super) fn handle_clear_consecutive_losses(
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let cleared = pipeline.consecutive_losses.len();
    pipeline.consecutive_losses.clear();
    info!(
        cleared_symbols = cleared,
        "consecutive losses cleared via IPC / 連虧計數器已通過 IPC 清除"
    );
    snapshot_writer.force_write(&pipeline.snapshot());
    let _ = response_tx.send(Ok(format!("cleared {cleared} symbol(s)")));
}

/// ARCH-RC1 1C-3-B-2 · EN: Operator-driven governor escalation (strictly one
///   tier tighter). Rejects multi-step jumps and delegates to the SM
///   `escalate_to` with an `OperatorEscalation` event label.
/// ARCH-RC1 1C-3-B-2 · 中文：Operator 手動升級風控（一次一級），多級跳躍拒絕，
///   委派 SM escalate_to 並標記為 OperatorEscalation 事件。
pub(super) fn handle_force_governor_tighter(
    target_tier: String,
    reason: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let result = (|| -> Result<String, String> {
        let target = TickPipeline::parse_risk_level(&target_tier)?;
        let current = pipeline.governance.risk.snapshot_level();
        // Only one step at a time; only toward more restrictive
        // 一次只能往更嚴方向跳一級
        if (target.value() as i32) - (current.value() as i32) != 1 {
            return Err(format!(
                "tighter must be exactly one tier above current (current={}, target={})",
                current, target
            ));
        }
        pipeline
            .governance
            .risk
            .escalate_to(
                target,
                &format!("operator_ipc: {reason}"),
                openclaw_core::sm::risk_gov::RiskEvent::OperatorEscalation,
            )
            .map_err(|e| format!("escalate_to failed: {e}"))?;
        info!(from = %current, to = %target, reason = %reason,
            "operator-driven governor escalation via IPC");
        snapshot_writer.force_write(&pipeline.snapshot());
        Ok(format!(
            "{{\"from\":\"{current}\",\"to\":\"{target}\",\"reason\":\"{reason}\"}}"
        ))
    })();
    let _ = response_tx.send(result);
}

/// ARCH-RC1 1C-3-B-2 · EN: Operator-driven governor de-escalation. Enforces
///   defence-in-depth checks before delegating to SM:
///     1. reason_code must be on the IPC whitelist
///     2. current level < CircuitBreaker (CB/MR cannot unlock via IPC —
///        deliberate friction: must edit TOML + restart)
///     3. exactly one tier lower (no jumps)
///     4. IPC-layer 24h cooldown since last manual de-escalation
///     5. SM's `de_escalate_to` enforces min_hold_time + lookup_rule
/// ARCH-RC1 1C-3-B-2 · 中文：Operator 手動降級 — IPC 層防線：reason_code 白名單、
///   CB/MR 不得解、僅降一級、24h 冷卻；最後委派 SM 再過一層。
pub(super) fn handle_force_governor_looser(
    target_tier: String,
    reason_code: String,
    notes: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let result = (|| -> Result<String, String> {
        use openclaw_core::sm::risk_gov::RiskLevel;
        // 1. Reason code whitelist (IPC layer enforcement)
        if !TickPipeline::VALID_DE_ESCALATION_REASONS.contains(&reason_code.as_str()) {
            return Err(format!(
                "invalid reason_code; must be one of {:?}",
                TickPipeline::VALID_DE_ESCALATION_REASONS
            ));
        }
        let target = TickPipeline::parse_risk_level(&target_tier)?;
        let current = pipeline.governance.risk.snapshot_level();

        // 2. Hard lock: cannot unlock CircuitBreaker / ManualReview from IPC.
        //    Operator must edit TOML + restart (deliberate friction).
        // 2. 硬鎖：CB / MR 不能透過 IPC 解開。Operator 必須改 TOML 後重啟。
        if current >= RiskLevel::CircuitBreaker {
            return Err(format!(
                "{current} cannot be unlocked via IPC; edit TOML + restart"
            ));
        }

        // 3. Exactly one step lower (no jumps)
        // 3. 一次只能降一級
        if (current.value() as i32) - (target.value() as i32) != 1 {
            return Err(format!(
                "looser must be exactly one tier below current (current={}, target={})",
                current, target
            ));
        }

        // 4. 24h IPC-layer cooldown
        // 4. IPC 層 24h 冷卻
        let now_ms = std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_millis() as u64)
            .unwrap_or(0);
        if let Some(last) = pipeline.last_governor_de_escalation_ms() {
            let elapsed = now_ms.saturating_sub(last);
            if elapsed < TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS {
                let remaining_ms =
                    TickPipeline::GOVERNOR_DE_ESCALATION_COOLDOWN_MS - elapsed;
                return Err(format!(
                    "24h cooldown active; {remaining_ms}ms remaining before next manual de-escalation"
                ));
            }
        }

        // 5. Delegate to SM (will also enforce its own min_hold_time
        //    + lookup_rule allow-list as defence in depth).
        // 5. 委派給 SM（會同時觸發 SM 內建的 hold_time + lookup_rule 防線）。
        let combined_reason = if notes.is_empty() {
            format!("operator_ipc:{reason_code}")
        } else {
            format!("operator_ipc:{reason_code}: {notes}")
        };
        pipeline
            .governance
            .risk
            .de_escalate_to(target, "operator_ipc", &combined_reason)
            .map_err(|e| format!("de_escalate_to failed: {e}"))?;

        pipeline.set_last_governor_de_escalation_ms(Some(now_ms));
        info!(from = %current, to = %target, reason_code = %reason_code,
            "operator-driven governor de-escalation via IPC");
        snapshot_writer.force_write(&pipeline.snapshot());
        Ok(format!(
            "{{\"from\":\"{current}\",\"to\":\"{target}\",\"reason_code\":\"{reason_code}\"}}"
        ))
    })();
    let _ = response_tx.send(result);
}

/// EN: Apply a bulk risk-config patch through IPC. Every numeric setter is
///   clamped to sane ranges (I-09) before being applied to PaperState,
///   GuardianConfig, the dynamic-risk sizer, the H0 gate, cost-gate / regime
///   params, boot cooldown, and the signals heartbeat.
/// 中文: 透過 IPC 批次套用風控配置補丁；所有數值 setter 先鉗制（I-09），
///   再寫入 PaperState、Guardian、動態風險 sizer、H0 門控、cost-gate、
///   啟動冷卻、signals 心跳。
#[allow(clippy::too_many_arguments)]
pub(super) fn handle_update_risk_config(
    hard_stop_pct: Option<f64>,
    trailing_stop_pct: Option<Option<f64>>,
    trailing_activation_pct: Option<Option<f64>>,
    time_stop_hours: Option<Option<f64>>,
    atr_multiplier: Option<Option<f64>>,
    take_profit_pct: Option<Option<f64>>,
    max_leverage: Option<f64>,
    max_drawdown_pct: Option<f64>,
    max_same_direction_positions: Option<usize>,
    p1_risk_pct: Option<f64>,
    h0_shadow_mode: Option<bool>,
    dynamic_stop_base_ratio: Option<f64>,
    dynamic_stop_cap_ratio: Option<f64>,
    trailing_min_rr_ratio: Option<f64>,
    cost_gate_min_confidence: Option<f64>,
    cost_gate_k_base: Option<f64>,
    cost_gate_k_medium: Option<f64>,
    cost_gate_k_small: Option<f64>,
    adx_trending_threshold: Option<f64>,
    boot_cooldown_ms: Option<u64>,
    signals_heartbeat_ms: Option<u64>,
    // EDGE-DIAG-1-FUP-IPC: ExitConfig hot-reload fields — applied atomically
    //   via `risk_store.apply_patch()` with `RiskConfig::validate()`. Any
    //   invariant violation rolls back ALL exit mutations (all-or-nothing)
    //   and logs a warn; non-exit fields above are unaffected.
    // EDGE-DIAG-1-FUP-IPC：ExitConfig 熱重載欄位，透過
    //   `risk_store.apply_patch()` + `RiskConfig::validate()` 原子套用；
    //   違反任一不變量即回滾所有 exit 修改（全或無）並 warn，上方非 exit
    //   欄位不受影響。
    exit_missing_edge_fallback_bps: Option<f64>,
    exit_min_net_floor_bps: Option<f64>,
    exit_min_hold_secs: Option<f64>,
    exit_min_peak_atr_norm: Option<f64>,
    exit_giveback_base: Option<f64>,
    exit_giveback_slope: Option<f64>,
    exit_giveback_floor: Option<f64>,
    // EDGE-P1b-FUP-STALE-PEAK-IPC (2026-04-26): dim 5 of EDGE-P1b T1
    //   calibrator. Wire is `u64 ms` for parity with sibling *_ms fields;
    //   the closure below casts to `i64` (validate() rejects negative).
    // EDGE-P1b-FUP-STALE-PEAK-IPC（2026-04-26）：EDGE-P1b T1 calibrator
    //   第 5 維度。Wire 為 `u64 ms` 對齊同伴 *_ms 欄位；下方 closure
    //   cast 為 `i64`（validate() 拒負值）。
    exit_stale_peak_ms: Option<u64>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    // I-09: clamp all numeric setters to sane ranges before applying.
    // I-09：應用前將所有數值設定鉗制到合理範圍。
    // StopConfig fields / 止損配置
    if let Some(v) = hard_stop_pct {
        let v = v.clamp(0.0, 0.5);
        pipeline.paper_state.set_hard_stop_pct(v);
        info!(
            hard_stop_pct = format!("{:.1}%", v),
            "hard stop updated / 硬止損已更新"
        );
    }
    if let Some(v) = trailing_stop_pct {
        let v = v.map(|x| x.clamp(0.0, 0.5));
        pipeline.paper_state.set_trailing_stop_pct(v);
        info!(trailing = ?v, "trailing stop updated / 跟蹤止損已更新");
    }
    if let Some(v) = trailing_activation_pct {
        // Activation is an absolute % of entry price (same family as trail/hard stop).
        // 啟動閾值與 trail/hard stop 同族：entry 的絕對百分比。
        let v = v.map(|x| x.clamp(0.0, 0.5));
        pipeline.paper_state.set_trailing_activation_pct(v);
        info!(trailing_activation = ?v, "trailing activation threshold updated / 跟蹤啟動閾值已更新");
    }
    if let Some(v) = time_stop_hours {
        let v = v.map(|x| x.clamp(0.0, 24.0 * 30.0));
        pipeline.paper_state.set_time_stop_hours(v);
        info!(time_stop = ?v, "time stop updated / 超時止損已更新");
    }
    if let Some(v) = atr_multiplier {
        let v = v.map(|x| x.clamp(0.5, 10.0));
        pipeline.paper_state.set_atr_multiplier(v);
        info!(atr_mult = ?v, "ATR multiplier updated / ATR 乘數已更新");
    }
    if let Some(v) = take_profit_pct {
        let v = v.map(|x| x.clamp(0.0, 10.0));
        pipeline.paper_state.set_take_profit_pct(v);
        info!(take_profit = ?v, "take profit updated / 止盈已更新");
    }
    // GuardianConfig fields / 守護者配置
    let needs_guardian = max_leverage.is_some()
        || max_drawdown_pct.is_some()
        || max_same_direction_positions.is_some();
    if needs_guardian {
        let mut gc = pipeline.intent_processor.guardian_config().clone();
        if let Some(v) = max_leverage {
            gc.max_leverage = v.clamp(1.0, 100.0);
        }
        if let Some(v) = max_drawdown_pct {
            gc.max_drawdown_pct = v.clamp(0.0, 100.0);
        }
        if let Some(v) = max_same_direction_positions {
            gc.max_same_direction_positions = v.clamp(1, 100);
        }
        pipeline.intent_processor.update_guardian_config(gc);
        info!("guardian config updated via IPC / 守護者配置已通過 IPC 更新");
    }
    // P1 risk cap / P1 風險上限
    if let Some(v) = p1_risk_pct {
        let v = v.clamp(0.0, 0.10);
        pipeline.intent_processor.set_p1_risk_pct(v);
        // DYNAMIC-RISK-1 BUG-3: rebase sizer so the next maybe_update
        // does not revert operator intent. Without this, the sizer's
        // stale current_pct would publish the old cap on the next tick.
        // DYNAMIC-RISK-1 BUG-3：重錨 sizer，避免下次 maybe_update 用舊值
        // 覆蓋 operator 剛下達的指令。
        pipeline.dynamic_risk_sizer.rebase(v);
        info!(
            p1_risk_pct = format!("{:.2}%", v * 100.0),
            "P1 risk cap updated / P1 上限已更新"
        );
    }
    // RRC-1-A3: H0 Gate shadow mode toggle / H0 門控影子模式切換
    if let Some(v) = h0_shadow_mode {
        pipeline.h0_gate.set_shadow_mode(v);
        info!(
            shadow_mode = v,
            "H0 gate shadow mode updated / H0 門控影子模式已更新"
        );
    }
    // PNL-7: agent-tunable dynamic-stop knobs (validated in patch fn)
    // PNL-7：Agent 可調的動態止損參數
    let changed = pipeline.intent_processor.patch_dynamic_stop_params(
        dynamic_stop_base_ratio,
        dynamic_stop_cap_ratio,
        trailing_min_rr_ratio,
    );
    if changed > 0 {
        info!(
            changed,
            base_ratio = ?dynamic_stop_base_ratio,
            cap_ratio = ?dynamic_stop_cap_ratio,
            trailing_min_rr_ratio = ?trailing_min_rr_ratio,
            "dynamic-stop knobs updated / 動態止損參數已更新"
        );
    }
    // Session 12: cost-gate + regime tunables
    let cg_changed = pipeline.intent_processor.patch_cost_gate_params(
        cost_gate_min_confidence,
        cost_gate_k_base,
        cost_gate_k_medium,
        cost_gate_k_small,
        adx_trending_threshold,
    );
    if cg_changed > 0 {
        info!(
            cg_changed,
            min_conf = ?cost_gate_min_confidence,
            k_base = ?cost_gate_k_base,
            k_medium = ?cost_gate_k_medium,
            k_small = ?cost_gate_k_small,
            adx = ?adx_trending_threshold,
            "cost-gate / regime params updated"
        );
    }
    // Session 12: PNL-3 boot cooldown via IPC
    if let Some(v) = boot_cooldown_ms {
        let applied = pipeline.set_boot_cooldown_ms(v);
        info!(boot_cooldown_ms = applied, "boot cooldown updated");
    }
    // DB-RUN-1: signals heartbeat
    if let Some(v) = signals_heartbeat_ms {
        let applied = pipeline.set_signals_heartbeat_ms(v);
        info!(signals_heartbeat_ms = applied, "signals heartbeat updated");
    }
    // EDGE-DIAG-1-FUP-IPC: ExitConfig hot-reload path. All 7 exit.* fields are
    //   applied atomically via `risk_store.apply_patch()` so that a validate()
    //   failure rolls BOTH the ArcSwap AND any persisted TOML state back to
    //   the last-good config (all-or-nothing per ConfigStore::apply_patch
    //   contract). `apply_risk_snapshot` is invoked on the next tick via
    //   `sync_risk_config_if_changed` — the version bump here guarantees the
    //   pipeline picks up the new exit values on the next on_tick without
    //   any extra plumbing. When `risk_store` is unwired (unit test path),
    //   we warn + skip so the rest of the update_risk_config call still
    //   completes cleanly (fail-soft, matches the edge_predictor kill-switch
    //   degrade-to-memory-only pattern).
    // EDGE-DIAG-1-FUP-IPC：ExitConfig 熱重載路徑。全部 7 個 exit.* 欄位經
    //   `risk_store.apply_patch()` 原子套用 —— validate() 失敗同時回滾
    //   ArcSwap 與 TOML（ConfigStore::apply_patch 全或無契約）。
    //   `apply_risk_snapshot` 於下一 tick 由 `sync_risk_config_if_changed`
    //   觸發，版本號遞增即保證 pipeline 於下次 on_tick 取到新值，無需額外
    //   接線。`risk_store` 未接線時（單元測試路徑）warn + 跳過，讓其他
    //   update_risk_config 呼叫仍乾淨完成（fail-soft，與 edge_predictor
    //   kill-switch 的 degrade-to-memory-only 模式一致）。
    let has_exit_patch = exit_missing_edge_fallback_bps.is_some()
        || exit_min_net_floor_bps.is_some()
        || exit_min_hold_secs.is_some()
        || exit_min_peak_atr_norm.is_some()
        || exit_giveback_base.is_some()
        || exit_giveback_slope.is_some()
        || exit_giveback_floor.is_some()
        || exit_stale_peak_ms.is_some();
    if has_exit_patch {
        match pipeline.risk_store() {
            Some(risk_store) => {
                // Capture inputs by value before the move into the closure so
                // we can log them after apply_patch returns (the closure takes
                // ownership of the copies).
                // 關閉前複製輸入值以便 apply_patch 後記錄（closure 會移動副本）。
                let p_missing = exit_missing_edge_fallback_bps;
                let p_floor_bps = exit_min_net_floor_bps;
                let p_hold = exit_min_hold_secs;
                let p_peak = exit_min_peak_atr_norm;
                let p_gb_base = exit_giveback_base;
                let p_gb_slope = exit_giveback_slope;
                let p_gb_floor = exit_giveback_floor;
                // EDGE-P1b-FUP-STALE-PEAK-IPC: copy u64 wire value; closure
                //   below casts to schema i64. validate() rejects negative,
                //   so any value > i64::MAX would already be caller error.
                // EDGE-P1b-FUP-STALE-PEAK-IPC：複製 u64 wire 值；下方 closure
                //   cast 為 schema i64。validate() 拒負值，超過 i64::MAX 屬
                //   caller error。
                let p_stale_peak_ms = exit_stale_peak_ms;
                let outcome = risk_store.apply_patch(
                    crate::config::PatchSource::Operator,
                    |cfg| {
                        if let Some(v) = p_missing {
                            cfg.exit.missing_edge_fallback_bps = v;
                        }
                        if let Some(v) = p_floor_bps {
                            cfg.exit.min_net_floor_bps = v;
                        }
                        if let Some(v) = p_hold {
                            cfg.exit.min_hold_secs = v;
                        }
                        if let Some(v) = p_peak {
                            cfg.exit.min_peak_atr_norm = v;
                        }
                        if let Some(v) = p_gb_base {
                            cfg.exit.giveback_base = v;
                        }
                        if let Some(v) = p_gb_slope {
                            cfg.exit.giveback_slope = v;
                        }
                        if let Some(v) = p_gb_floor {
                            cfg.exit.giveback_floor = v;
                        }
                        // EDGE-P1b-FUP-STALE-PEAK-IPC: u64 ms → schema i64.
                        //   validate() (exit_features/v2.rs) rejects < 0;
                        //   any reasonable ms value is well within i64 range
                        //   (default 60_000; i64::MAX ≈ 9.2e18 ms ≈ 290M yrs).
                        // EDGE-P1b-FUP-STALE-PEAK-IPC：u64 ms → schema i64。
                        //   validate()（exit_features/v2.rs）拒 < 0；任何
                        //   合理 ms 值均遠小於 i64::MAX（預設 60_000；
                        //   i64::MAX ≈ 9.2e18 ms ≈ 2.9 億年）。
                        if let Some(v) = p_stale_peak_ms {
                            cfg.exit.stale_peak_ms = v as i64;
                        }
                    },
                    |cfg| cfg.validate(),
                );
                match outcome {
                    Ok(patch) => {
                        info!(
                            version = patch.version,
                            missing_edge_fallback_bps = ?exit_missing_edge_fallback_bps,
                            min_net_floor_bps = ?exit_min_net_floor_bps,
                            min_hold_secs = ?exit_min_hold_secs,
                            min_peak_atr_norm = ?exit_min_peak_atr_norm,
                            giveback_base = ?exit_giveback_base,
                            giveback_slope = ?exit_giveback_slope,
                            giveback_floor = ?exit_giveback_floor,
                            stale_peak_ms = ?exit_stale_peak_ms,
                            "exit config updated via IPC / exit 配置已通過 IPC 更新"
                        );
                    }
                    Err(e) => {
                        // Validation failure: apply_patch rolled back atomically
                        // (no partial mutation on the ArcSwap, no TOML write).
                        // 驗證失敗：apply_patch 已原子回滾（ArcSwap 無部分變更、TOML 未寫）。
                        warn!(
                            error = %e,
                            "exit config patch rejected by validate() / exit 配置補丁被 validate() 拒絕"
                        );
                    }
                }
            }
            None => {
                // Test / bootstrap path without a wired store.
                // 測試 / 啟動階段未接線 store 的路徑。
                warn!(
                    "risk_store not wired — exit config patch skipped (fail-soft) / risk_store 未接線，exit 配置補丁已跳過（fail-soft）"
                );
            }
        }
    }
    snapshot_writer.force_write(&pipeline.snapshot());
}

/// EN: Collect the set of symbols that currently have an active position,
///   used by the scanner to defer removal until positions close.
/// 中文: 收集當前有活躍持倉的交易對集合，供掃描器延遲移除。
pub(super) fn handle_get_open_position_symbols(
    response_tx: tokio::sync::oneshot::Sender<std::collections::HashSet<String>>,
    pipeline: &mut TickPipeline,
) {
    // Collect symbols with an active open position for scanner removal deferral.
    // 收集有活躍持倉的交易對，供掃描器移除延遲使用。
    let open_symbols: std::collections::HashSet<String> = pipeline
        .paper_state
        .positions()
        .into_iter()
        .map(|pos| pos.symbol.clone())
        .collect();
    let _ = response_tx.send(open_symbols);
}

/// Phase 6 · EN: Reconciler-driven risk-level auto-escalation when position
///   drift is detected. Goes through the dedicated `reconciler_escalate_to`
///   SM path (distinct from operator escalation).
/// Phase 6 · 中文：對帳器偵測到漂移時自動升級，走專用 SM 通道。
pub(super) fn handle_reconciler_escalate(
    target_tier: String,
    reason: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let result = (|| -> Result<String, String> {
        let target = TickPipeline::parse_risk_level(&target_tier)?;
        let current = pipeline.governance.risk.snapshot_level();
        pipeline
            .governance
            .risk
            .reconciler_escalate_to(target, &reason)
            .map_err(|e| format!("reconciler_escalate_to failed: {e}"))?;
        info!(from = %current, to = %target, reason = %reason,
            "reconciler auto-escalation (drift detected) / 對帳器自動升級（偵測到漂移）");
        snapshot_writer.force_write(&pipeline.snapshot());
        Ok(format!(
            "{{\"from\":\"{current}\",\"to\":\"{target}\",\"reason\":\"{reason}\"}}"
        ))
    })();
    let _ = response_tx.send(result);
}

/// Phase 6 · EN: Reconciler-driven risk-level auto-recovery after clean
///   cycles. Goes through the dedicated `reconciler_de_escalate_to` SM
///   path (distinct from operator de-escalation).
/// Phase 6 · 中文：對帳器累積乾淨週期後自動恢復，走專用 SM 通道。
pub(super) fn handle_reconciler_de_escalate(
    target_tier: String,
    reason: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    snapshot_writer: &mut DualStateWriter,
) {
    let result = (|| -> Result<String, String> {
        let target = TickPipeline::parse_risk_level(&target_tier)?;
        let current = pipeline.governance.risk.snapshot_level();
        pipeline
            .governance
            .risk
            .reconciler_de_escalate_to(target, &reason)
            .map_err(|e| format!("reconciler_de_escalate_to failed: {e}"))?;
        info!(from = %current, to = %target, reason = %reason,
            "reconciler auto-recovery (clean cycles met) / 對帳器自動恢復（乾淨週期達標）");
        snapshot_writer.force_write(&pipeline.snapshot());
        Ok(format!(
            "{{\"from\":\"{current}\",\"to\":\"{target}\",\"reason\":\"{reason}\"}}"
        ))
    })();
    let _ = response_tx.send(result);
}

/// DYNAMIC-RISK-1 · EN: Return the Sharpe-aware sizer's current status
///   (enabled flag, current_pct, target_pct, last update ts, etc.) as JSON.
/// DYNAMIC-RISK-1 · 中文：回傳 Sharpe-aware sizer 當前狀態 JSON。
pub(super) fn handle_get_dynamic_risk_status(
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    let status = pipeline.dynamic_risk_sizer.status();
    let result =
        serde_json::to_string(&status).map_err(|e| format!("serialize sizer status: {e}"));
    let _ = response_tx.send(result);
}

/// DYNAMIC-RISK-1 · EN: Toggle the Sharpe-aware sizer on / off via IPC.
/// DYNAMIC-RISK-1 · 中文：透過 IPC 切換 Sharpe-aware sizer 啟停。
pub(super) fn handle_set_dynamic_risk_enabled(
    enabled: bool,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    pipeline.dynamic_risk_sizer.set_enabled(enabled);
    info!(
        enabled,
        "IPC dynamic_risk_sizer toggled / IPC 動態風險調整器切換"
    );
    let _ = response_tx.send(Ok(format!("dynamic_risk_sizer enabled={enabled}")));
}
