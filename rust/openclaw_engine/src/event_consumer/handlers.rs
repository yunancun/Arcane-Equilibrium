//! Event consumer command handlers — extracted from `mod.rs` to keep the
//! main loop file under the 800-line warning threshold.
//! 事件消費者命令處理器 — 從 mod.rs 提取，以保持主循環檔案在 800 行警告線下。
//!
//! MODULE_NOTE (EN): These free functions take whatever subset of pipeline /
//!   bookkeeping state they need by mutable reference and execute one IPC
//!   command. They contain no async work — the parent `tokio::select!` arm
//!   simply forwards the parsed enum here. Splitting them out keeps the loop
//!   readable without restructuring loop state into a struct.
//! MODULE_NOTE (中): 這些自由函式接受所需的 pipeline / bookkeeping 狀態
//!   作為可變引用，執行單一 IPC 命令。父級 `tokio::select!` 分支將解析後的
//!   enum 轉發過來。

use super::types::PendingOrder;
use crate::persistence::DualStateWriter;
use crate::tick_pipeline::{PipelineCommand, TickPipeline};
use std::collections::HashMap;
use tracing::info;

/// EDGE-P3-1 Step 7e · Shared kill-switch body. Extracted so both the
/// production event_consumer/mod.rs interception path AND the in-process
/// `handle_paper_command` direct-dispatch path (used by unit tests) execute
/// the same logic without duplication.
/// EDGE-P3-1 Step 7e：共用 kill-switch 實作。mod.rs 攔截路徑與 handle_paper_command
/// 直分派路徑（單元測試用）共用同一份邏輯。
fn disable_edge_predictor_all_impl(
    operator_token: &str,
    reason: &str,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
) {
    // FIXME(Step 7e): Full two-phase commit (TOML fsync → ArcSwap → clear_all)
    // + observability.engine_events audit row not yet wired. Current handler
    // matches pre-7e behaviour (in-memory clear only) plus a length-validated
    // token check. See tick_pipeline/mod.rs docstring.
    if operator_token.len() < 32 {
        let _ = response_tx.send(Err(
            "operator_token too short (need >=32 chars) / operator_token 過短".into(),
        ));
        return;
    }
    let result = match pipeline.edge_predictor_store() {
        Some(store) => {
            let n = store.clear_all();
            info!(
                cleared = n,
                reason = %reason,
                "EdgePredictor DisableAll / 已禁用所有預測器"
            );
            Ok(format!("cleared {} predictor slots", n))
        }
        None => Err(
            "EdgePredictorStore not wired on this engine / 此引擎尚未注入 store".into(),
        ),
    };
    let _ = response_tx.send(result);
}

/// EDGE-P3-1 Step 7e · Production entry point for the operator kill-switch,
/// called from `event_consumer::mod.rs` after intercepting the variant. Accepts
/// `db_mode` + `audit_pool` so the forthcoming two-phase commit + engine_events
/// audit row have a home without another signature churn.
/// EDGE-P3-1 Step 7e：mod.rs 攔截後的生產入口，預留 db_mode + audit_pool 以便
/// 未來兩階段提交與 engine_events 審計行接入時無須再改簽名。
pub fn handle_disable_edge_predictor_all(
    operator_token: String,
    reason: String,
    response_tx: tokio::sync::oneshot::Sender<Result<String, String>>,
    pipeline: &mut TickPipeline,
    _db_mode: &'static str,
    _audit_pool: Option<&sqlx::PgPool>,
) {
    // FIXME(Step 7e): _db_mode + _audit_pool will carry the audit writeback;
    // today we delegate to the in-memory clear impl.
    disable_edge_predictor_all_impl(&operator_token, &reason, response_tx, pipeline);
}

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
        PipelineCommand::Pause => {
            pipeline.paper_paused = true;
            info!("paper trading PAUSED via IPC / 紙盤交易已通過 IPC 暫停");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::Resume => {
            pipeline.paper_paused = false;
            // F2 fix: clear session_halted on Resume / 恢復時清除會話暫停標誌
            pipeline.session_halted = false;
            info!("paper trading RESUMED via IPC / 紙盤交易已通過 IPC 恢復");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::CloseAll => {
            // Exchange mode (Demo/Live): dispatch reduce_only market orders via shadow channel.
            // Paper mode: clear paper_state directly.
            // 交易所模式（Demo/Live）：通過 shadow 通道發 reduce_only 市價單。
            // 紙盤模式：直接清除 paper_state。
            let count = pipeline.ipc_close_all();
            info!(count, "IPC close_all_positions / IPC 全部平倉");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::CloseSymbol { symbol, hint_is_long, hint_qty } => {
            // Exchange mode (Demo/Live): dispatch reduce_only market order via shadow channel.
            // Paper mode: close_position_at_market directly.
            // hint_is_long/hint_qty allow closing orphan exchange positions not in paper_state.
            // 交易所模式：發 reduce_only 市價單；紙盤模式：直接平倉。
            // hint 參數允許平掉 paper_state 沒有追蹤的交易所孤兒倉位。
            let found = pipeline.ipc_close_symbol(&symbol, hint_is_long, hint_qty);
            info!(symbol = symbol.as_str(), found, "IPC close_position / IPC 單倉平倉");
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::Reset { new_balance } => {
            // ORPHAN-ADOPT-1 FUP: preserve the shared positions_mirror handle
            // across reset so the reconciler keeps observing the same Arc.
            // set_positions_mirror clears + rehydrates the shared map from the
            // (empty) positions of the freshly-constructed PaperState.
            // ORPHAN-ADOPT-1 FUP：reset 保留共享 positions_mirror handle，
            // 避免對帳器看到的 Arc 與引擎側分離。
            let shared_mirror = pipeline.paper_state.positions_mirror();
            pipeline.paper_state = crate::paper_state::PaperState::new(new_balance);
            pipeline.paper_state.set_positions_mirror(shared_mirror);
            pipeline.stats = crate::tick_pipeline::TickStats::default();
            pipeline.paper_paused = false;
            // F2+F3 fix: clear halt + loss counters on reset / 重置時清除暫停+虧損計數
            pipeline.session_halted = false;
            pipeline.consecutive_losses.clear();
            // P2-4 fix: Clear pending_close_symbols on reset
            pipeline.clear_all_pending_close();
            pending_orders.clear();
            info!(
                balance = format!("{:.2}", new_balance),
                "IPC reset paper state / IPC 重置紙盤狀態"
            );
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        // ── Phase 3b: Strategy parameter IPC commands / 策略參數 IPC 命令 ──
        PipelineCommand::UpdateStrategyParams {
            strategy_name,
            params_json,
            response_tx,
        } => {
            // CONF-D: pre-process params JSON — strip optional "conf_scale" key and
            // apply via Strategy::set_conf_scale, then forward the remaining JSON to
            // the strategy's typed update_params_json. If only conf_scale was sent,
            // skip the typed update entirely (empty object).
            // CONF-D：預處理 — 抽出 conf_scale 套用後再轉發剩餘 JSON。
            let (effective_json, conf_scale_opt): (String, Option<f64>) = match
                serde_json::from_str::<serde_json::Value>(&params_json)
            {
                Ok(serde_json::Value::Object(mut map)) => {
                    let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                    let stripped = serde_json::Value::Object(map);
                    (stripped.to_string(), cs)
                }
                _ => (params_json.clone(), None),
            };

            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => {
                    if let Some(scale) = conf_scale_opt {
                        strategy.set_conf_scale(scale);
                    }
                    // If the stripped JSON is just "{}" and we did set conf_scale,
                    // skip the typed update to avoid unnecessary churn / parse errors.
                    let need_typed_update = effective_json != "{}" || conf_scale_opt.is_none();
                    if need_typed_update {
                        match strategy.update_params_json(&effective_json) {
                            Ok(()) => {
                                info!(
                                    strategy = %strategy_name,
                                    conf_scale = ?conf_scale_opt,
                                    "strategy params updated via IPC / 策略參數已通過 IPC 更新"
                                );
                                snapshot_writer.force_write(&pipeline.snapshot());
                                Ok(format!("params updated for {}", strategy_name))
                            }
                            Err(e) => Err(format!("validation failed: {e}")),
                        }
                    } else {
                        info!(
                            strategy = %strategy_name,
                            conf_scale = ?conf_scale_opt,
                            "strategy conf_scale updated via IPC / 策略 conf_scale 已通過 IPC 更新"
                        );
                        snapshot_writer.force_write(&pipeline.snapshot());
                        Ok(format!("conf_scale updated for {}", strategy_name))
                    }
                }
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        PipelineCommand::GetStrategyParams {
            strategy_name,
            response_tx,
        } => {
            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => Ok(strategy.get_params_json()),
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        PipelineCommand::GetParamRanges {
            strategy_name,
            response_tx,
        } => {
            let result = match pipeline.orchestrator.find_strategy_mut(&strategy_name) {
                Some(strategy) => Ok(strategy.param_ranges_json()),
                None => Err(format!("strategy not found: {strategy_name}")),
            };
            let _ = response_tx.send(result);
        }
        // ── ARCH-RC1 1C-3-B: Risk runtime status + safe counter clear ──
        PipelineCommand::GetRiskRuntimeStatus { response_tx } => {
            let now_ms = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .map(|d| d.as_millis() as u64)
                .unwrap_or(0);
            let snapshot = pipeline.risk_runtime_status_json(now_ms);
            let _ = response_tx.send(Ok(snapshot.to_string()));
        }
        PipelineCommand::ClearConsecutiveLosses { response_tx } => {
            let cleared = pipeline.consecutive_losses.len();
            pipeline.consecutive_losses.clear();
            info!(
                cleared_symbols = cleared,
                "consecutive losses cleared via IPC / 連虧計數器已通過 IPC 清除"
            );
            snapshot_writer.force_write(&pipeline.snapshot());
            let _ = response_tx.send(Ok(format!("cleared {cleared} symbol(s)")));
        }
        // ── ARCH-RC1 1C-3-B-2: Governor manual override (operator escalation) ──
        PipelineCommand::ForceGovernorTighter {
            target_tier,
            reason,
            response_tx,
        } => {
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
        // ── ARCH-RC1 1C-3-B-2: Governor manual override (operator de-escalation) ──
        PipelineCommand::ForceGovernorLooser {
            target_tier,
            reason_code,
            notes,
            response_tx,
        } => {
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
        } => {
            let result = (|| -> Result<String, String> {
                let is_long = match side.as_str() {
                    "Buy" | "buy" | "long" | "LONG" => true,
                    "Sell" | "sell" | "short" | "SHORT" => false,
                    other => return Err(format!("invalid side: {other}")),
                };
                let conf = if confidence > 0.0 { confidence } else { 1.0 };
                pipeline.submit_external_order(
                    &symbol,
                    is_long,
                    qty,
                    &order_type,
                    limit_price,
                    conf,
                    &strategy,
                )
            })();
            if result.is_ok() {
                snapshot_writer.force_write(&pipeline.snapshot());
            }
            let _ = response_tx.send(result);
        }
        // RRC-1-E2: Strategy activate/pause / 策略啟停
        PipelineCommand::SetStrategyActive {
            strategy_name,
            active,
            response_tx,
        } => {
            let result = pipeline
                .orchestrator
                .set_strategy_active(&strategy_name, active);
            if result.is_ok() {
                let state = if active { "ACTIVATED" } else { "PAUSED" };
                info!(
                    strategy = %strategy_name, state,
                    "strategy state changed via IPC / 策略狀態已通過 IPC 更改"
                );
                snapshot_writer.force_write(&pipeline.snapshot());
            }
            let _ = response_tx.send(result.map(|was| format!("was_active={was}")));
        }
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
        } => {
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
            snapshot_writer.force_write(&pipeline.snapshot());
        }
        PipelineCommand::GetOpenPositionSymbols { response_tx } => {
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
        // 3E-3: AddMode and SwitchMode REMOVED — pipelines spawned at startup
        // with fixed PipelineKind. See EngineCommandChannels for per-pipeline routing.
        // 3E-3：AddMode 和 SwitchMode 已移除 — 管線啟動時固定 PipelineKind。
        // ── Phase 6: Reconciler auto-contraction ──
        PipelineCommand::ReconcilerEscalate {
            target_tier,
            reason,
            response_tx,
        } => {
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
        PipelineCommand::ReconcilerDeEscalate {
            target_tier,
            reason,
            response_tx,
        } => {
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
        // Sync global system mode from Python GUI → engine.
        // 從 Python GUI 同步全局系統模式到引擎。
        PipelineCommand::SetSystemMode { mode, response_tx } => {
            let result = pipeline.set_system_mode(&mode);
            if result.is_ok() {
                snapshot_writer.force_write(&pipeline.snapshot());
            }
            let _ = response_tx.send(result);
        }
        // EDGE-P3-1 Stage 0 · Hot-swap a predictor for a single strategy.
        // Fails fast if no EdgePredictorStore has been wired onto the pipeline
        // yet — ML-MIT must not silently no-op on an uninitialised engine.
        // EDGE-P3-1 Stage 0 · 熱換單一策略的 predictor；未注入 store 時立即失敗，
        // 避免 ML-MIT 誤以為寫入了未初始化的引擎。
        PipelineCommand::SetEdgePredictorShadow {
            strategy,
            predictor,
            response_tx,
        } => {
            let result = match pipeline.edge_predictor_store() {
                Some(store) => {
                    store.swap(&strategy, predictor.into_arc());
                    info!(strategy = %strategy,
                        "EdgePredictor swapped / 已熱換預測器");
                    Ok(format!("swapped predictor for {}", strategy))
                }
                None => Err(
                    "EdgePredictorStore not wired on this engine — check main.rs \
                     set_edge_predictor_store() / 此引擎尚未注入 EdgePredictorStore".into(),
                ),
            };
            let _ = response_tx.send(result);
        }
        // EDGE-P3-1 Stage 0 · Operator kill-switch: clear every loaded model
        // so the cost gate immediately falls back to the JS shrinkage path.
        // EDGE-P3-1 Stage 0 · Operator kill-switch：清空所有已載入模型，cost gate
        // 立即回落 JS shrinkage。
        PipelineCommand::DisableEdgePredictorAll {
            operator_token,
            reason,
            response_tx,
        } => {
            // Production flow intercepts this variant in event_consumer/mod.rs and
            // calls handle_disable_edge_predictor_all directly. This arm stays
            // reachable only for unit-test direct dispatch; logic is shared.
            // 生產路徑在 event_consumer/mod.rs 攔截此變體，直接呼叫
            // handle_disable_edge_predictor_all；此分支僅供單元測試直接分派。
            disable_edge_predictor_all_impl(&operator_token, &reason, response_tx, pipeline);
        }
        // EDGE-P3-1 Stage 0 · ε-greedy shadow-fill passthrough. DB write is
        // Step 7c (pending — same Option-B pattern as Step 7a). Today this
        // handler only logs; the cost gate producer (A3/A4) is wired.
        // EDGE-P3-1 Stage 0 · ε-greedy shadow-fill 轉發。DB 寫入屬 Step 7c（待做，
        // 同 Step 7a 的 Option-B 模式）；目前僅 log，producer（A3/A4）已接。
        PipelineCommand::EmitShadowFill {
            context_id,
            strategy,
            symbol,
            features_jsonb: _,
            prediction_q10,
            prediction_q50,
            prediction_q90,
            cost_bps,
            ts_ms,
        } => {
            info!(
                context_id = %context_id,
                strategy = %strategy,
                symbol = %symbol,
                q10 = prediction_q10,
                q50 = prediction_q50,
                q90 = prediction_q90,
                cost_bps = cost_bps,
                ts_ms = ts_ms,
                "EdgePredictor shadow_fill queued (Stage 0 stub — Step 7c will wire writer) \
                 / 預測器 shadow_fill 排隊（Stage 0 stub，Step 7c 將接 writer）",
            );
        }
        // EDGE-P3-1 Step 7a · Passthrough IPC → decision_feature writer channel.
        // External callers (Python backfill/replay tooling) inject training-
        // store rows through the same Rust-direct writer the IntentProcessor
        // producer uses. When the tx is not yet wired (bootstrap race or
        // intentional disable) we log-skip — fail-soft, no panic.
        // `try_send` keeps this off the hot path; Full/Closed drops count as
        // best-effort losses, matching the writer's own backpressure policy.
        // EDGE-P3-1 Step 7a · Passthrough IPC → decision_feature writer 通道。
        // 外部呼叫方走與 IntentProcessor producer 相同的 Rust 直寫路徑。tx 未接線時
        // log 跳過（fail-soft）；try_send 不阻塞熱路徑，Full/Closed drop 計為 best-effort。
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
        } => {
            match pipeline.decision_feature_tx() {
                Some(tx) => {
                    let msg = crate::database::DecisionFeatureMsg {
                        context_id: context_id.clone(),
                        ts_ms,
                        engine_mode,
                        strategy_name: strategy,
                        symbol: symbol.clone(),
                        side,
                        feature_schema_version,
                        feature_schema_hash,
                        feature_definition_hash,
                        features_jsonb,
                    };
                    if let Err(e) = tx.try_send(msg) {
                        tracing::warn!(
                            ctx_id = %context_id, symbol = %symbol, error = %e,
                            "decision_feature IPC drop — writer channel full/closed \
                             / 決策特徵 IPC 丟棄，writer 通道已滿/關閉"
                        );
                    }
                }
                None => {
                    info!(
                        ctx_id = %context_id, symbol = %symbol,
                        "decision_feature IPC received but writer not wired (fail-soft skip) \
                         / 決策特徵 IPC 收到但 writer 未接線（fail-soft 跳過）"
                    );
                }
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::persistence::StateWriter;
    use crate::tick_pipeline::TickPipeline;

    /// EN: Helper — build a DualStateWriter pointing at a temp directory.
    /// 中文: 輔助函式 — 建構指向暫存目錄的 DualStateWriter。
    fn make_writer(dir: &std::path::Path) -> DualStateWriter {
        let path = dir.join("test_snapshot.json");
        let primary = StateWriter::new(&path, 0); // interval=0 → always write
        DualStateWriter::new(primary, None)
    }

    // ── Pause / Resume / Reset ──

    /// EN: Pause sets paper_paused=true.
    /// 中文: Pause 設定 paper_paused=true。
    #[test]
    fn test_pause_sets_flag() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        assert!(!pipeline.paper_paused);
        handle_paper_command(PipelineCommand::Pause, &mut pipeline, &mut writer, &mut pending);
        assert!(pipeline.paper_paused);
    }

    /// EN: Resume clears both paper_paused and session_halted.
    /// 中文: Resume 同時清除 paper_paused 和 session_halted。
    #[test]
    fn test_resume_clears_pause_and_halt() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.paper_paused = true;
        pipeline.session_halted = true;
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        handle_paper_command(PipelineCommand::Resume, &mut pipeline, &mut writer, &mut pending);
        assert!(!pipeline.paper_paused);
        assert!(!pipeline.session_halted);
    }

    /// EN: Reset restores balance, clears paused+halted+consecutive_losses+pending.
    /// 中文: Reset 恢復餘額、清除暫停+中止+連虧+掛單。
    #[test]
    fn test_reset_clears_all_state() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.paper_paused = true;
        pipeline.session_halted = true;
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        pending.insert("order1".to_string(), PendingOrder {
            order_link_id: "order1".into(),
            symbol: "BTCUSDT".into(),
            is_long: true,
            qty: 0.01,
            strategy: "test".into(),
            sent_ts_ms: 1000,
            cum_filled_qty: 0.0,
            is_close: false,
        });
        handle_paper_command(
            PipelineCommand::Reset { new_balance: 5000.0 },
            &mut pipeline, &mut writer, &mut pending,
        );
        assert!(!pipeline.paper_paused);
        assert!(!pipeline.session_halted);
        assert!(pending.is_empty());
        assert!((pipeline.paper_state.balance() - 5000.0).abs() < 1e-9);
    }

    // ── ClearConsecutiveLosses ──

    /// EN: ClearConsecutiveLosses empties the map and responds with count.
    /// 中文: ClearConsecutiveLosses 清空映射並回應清除數量。
    #[test]
    fn test_clear_consecutive_losses() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        pipeline.consecutive_losses.insert("BTCUSDT".to_string(), 3);
        pipeline.consecutive_losses.insert("ETHUSDT".to_string(), 5);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        let (tx, rx) = tokio::sync::oneshot::channel();
        handle_paper_command(
            PipelineCommand::ClearConsecutiveLosses { response_tx: tx },
            &mut pipeline, &mut writer, &mut pending,
        );
        assert!(pipeline.consecutive_losses.is_empty());
        let resp = rx.blocking_recv().unwrap();
        assert!(resp.unwrap().contains("2 symbol"));
    }

    // ── GetOpenPositionSymbols ──

    /// EN: GetOpenPositionSymbols returns empty set when no positions.
    /// 中文: 無持倉時返回空集合。
    #[test]
    fn test_get_open_position_symbols_empty() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        let (tx, rx) = tokio::sync::oneshot::channel();
        handle_paper_command(
            PipelineCommand::GetOpenPositionSymbols { response_tx: tx },
            &mut pipeline, &mut writer, &mut pending,
        );
        let symbols = rx.blocking_recv().unwrap();
        assert!(symbols.is_empty());
    }

    // ── UpdateStrategyParams: conf_scale extraction ──

    /// EN: UpdateStrategyParams with only conf_scale skips typed update.
    /// 中文: 僅含 conf_scale 時跳過類型化更新。
    #[test]
    fn test_conf_scale_extraction_logic() {
        // Test the JSON parsing logic directly (same as handler lines 89-98)
        let params_json = r#"{"conf_scale": 1.5}"#;
        let (effective_json, conf_scale_opt): (String, Option<f64>) = match
            serde_json::from_str::<serde_json::Value>(params_json)
        {
            Ok(serde_json::Value::Object(mut map)) => {
                let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                let stripped = serde_json::Value::Object(map);
                (stripped.to_string(), cs)
            }
            _ => (params_json.to_string(), None),
        };
        assert_eq!(effective_json, "{}");
        assert_eq!(conf_scale_opt, Some(1.5));
    }

    /// EN: UpdateStrategyParams with conf_scale + other fields preserves both.
    /// 中文: conf_scale + 其他欄位時兩者皆保留。
    #[test]
    fn test_conf_scale_mixed_with_other_params() {
        let params_json = r#"{"conf_scale": 2.0, "fast_period": 10}"#;
        let (effective_json, conf_scale_opt): (String, Option<f64>) = match
            serde_json::from_str::<serde_json::Value>(params_json)
        {
            Ok(serde_json::Value::Object(mut map)) => {
                let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                let stripped = serde_json::Value::Object(map);
                (stripped.to_string(), cs)
            }
            _ => (params_json.to_string(), None),
        };
        assert_eq!(conf_scale_opt, Some(2.0));
        let parsed: serde_json::Value = serde_json::from_str(&effective_json).unwrap();
        assert_eq!(parsed["fast_period"], 10);
        // conf_scale should be stripped
        assert!(parsed.get("conf_scale").is_none());
    }

    /// EN: Invalid JSON falls back to original string with None conf_scale.
    /// 中文: 無效 JSON 回退為原始字串，conf_scale 為 None。
    #[test]
    fn test_conf_scale_invalid_json_fallback() {
        let params_json = "not-json";
        let (effective_json, conf_scale_opt): (String, Option<f64>) = match
            serde_json::from_str::<serde_json::Value>(params_json)
        {
            Ok(serde_json::Value::Object(mut map)) => {
                let cs = map.remove("conf_scale").and_then(|v| v.as_f64());
                let stripped = serde_json::Value::Object(map);
                (stripped.to_string(), cs)
            }
            _ => (params_json.to_string(), None),
        };
        assert_eq!(effective_json, "not-json");
        assert!(conf_scale_opt.is_none());
    }

    // ── EDGE-P3-1 Stage 0 handlers ─────────────────────────────────────

    /// EN: SetEdgePredictorShadow returns Err when no store is wired.
    /// Protects ML-MIT from silently no-oping on an uninitialised engine.
    /// 中文: 未注入 store 時 SetEdgePredictorShadow 回 Err；避免 ML-MIT
    /// 以為熱換成功但其實無人接收。
    #[test]
    fn test_set_edge_predictor_shadow_fails_without_store() {
        use crate::edge_predictor::{BoxedEdgePredictor, null_backend::NullPredictor};

        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();

        let (tx, rx) = tokio::sync::oneshot::channel();
        let predictor: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
            std::sync::Arc::new(NullPredictor::new());
        handle_paper_command(
            PipelineCommand::SetEdgePredictorShadow {
                strategy: "ma_crossover".into(),
                predictor: BoxedEdgePredictor::new(predictor),
                response_tx: tx,
            },
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_err(), "expected Err without wired store, got Ok");
        let msg = result.unwrap_err();
        assert!(msg.contains("not wired"), "err should mention not-wired: {}", msg);
    }

    /// EN: SetEdgePredictorShadow succeeds after store is wired; load_for
    /// returns the swapped predictor.
    /// 中文: 注入 store 後 SetEdgePredictorShadow 成功；load_for 返回剛熱換的 predictor。
    #[test]
    fn test_set_edge_predictor_shadow_succeeds_after_wire() {
        use crate::edge_predictor::{
            BoxedEdgePredictor, EdgePredictorStore, null_backend::NullPredictor,
        };

        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let store = std::sync::Arc::new(EdgePredictorStore::new());
        pipeline.set_edge_predictor_store(std::sync::Arc::clone(&store));
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();

        let (tx, rx) = tokio::sync::oneshot::channel();
        let predictor: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
            std::sync::Arc::new(NullPredictor::new());
        handle_paper_command(
            PipelineCommand::SetEdgePredictorShadow {
                strategy: "ma_crossover".into(),
                predictor: BoxedEdgePredictor::new(predictor),
                response_tx: tx,
            },
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_ok(), "expected Ok, got {:?}", result);
        assert!(store.load_for("ma_crossover").is_some(),
            "predictor should be loaded after swap");
    }

    /// EN: DisableEdgePredictorAll clears every registered slot.
    /// 中文: DisableEdgePredictorAll 清空所有已註冊槽位。
    #[test]
    fn test_disable_edge_predictor_all_clears_slots() {
        use crate::edge_predictor::{EdgePredictorStore, null_backend::NullPredictor};

        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let store = std::sync::Arc::new(EdgePredictorStore::new());
        // Seed 3 strategies with live predictors / 預先載入 3 個策略。
        for s in ["ma_crossover", "bb_reversion", "grid_trading"] {
            let p: std::sync::Arc<dyn crate::edge_predictor::EdgePredictor + Send + Sync> =
                std::sync::Arc::new(NullPredictor::new());
            store.swap(s, p);
        }
        pipeline.set_edge_predictor_store(std::sync::Arc::clone(&store));
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();

        let (tx, rx) = tokio::sync::oneshot::channel();
        handle_paper_command(
            PipelineCommand::DisableEdgePredictorAll {
                operator_token: "test-token-12345678901234567890abcdef".into(),
                reason: "unit test".into(),
                response_tx: tx,
            },
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        let result = rx.blocking_recv().unwrap();
        assert!(result.is_ok());
        let msg = result.unwrap();
        assert!(msg.contains("cleared 3"), "msg should report cleared count: {}", msg);
        // All slots now return None on load_for / 所有槽位 load_for 返回 None。
        for s in ["ma_crossover", "bb_reversion", "grid_trading"] {
            assert!(store.load_for(s).is_none(), "slot {} still loaded", s);
        }
    }

    // ═══════════════════════════════════════════════════════════════════
    // EDGE-P3-1 Step 7a: DecisionFeatureSnapshot passthrough tests.
    // EDGE-P3-1 Step 7a：決策特徵快照 IPC 透傳測試。
    // ═══════════════════════════════════════════════════════════════════

    fn make_decision_feature_cmd(ctx_id: &str) -> PipelineCommand {
        PipelineCommand::DecisionFeatureSnapshot {
            context_id: ctx_id.into(),
            ts_ms: 1_700_000_000_000,
            engine_mode: "paper".into(),
            strategy: "ma_crossover".into(),
            symbol: "BTCUSDT".into(),
            side: 1,
            feature_schema_version: "v1".into(),
            feature_schema_hash: "sha256:0011223344556677".into(),
            feature_definition_hash: "sha256:0011223344556677".into(),
            features_jsonb: r#"{"adx_1h":25.0,"side":1}"#.into(),
        }
    }

    /// EN: DecisionFeatureSnapshot with no writer wired is a silent fail-soft
    ///   skip — must not panic and leave the pipeline in a consistent state.
    /// 中文: writer 未接線時 DecisionFeatureSnapshot 必須 fail-soft 跳過，不 panic。
    #[test]
    fn test_decision_feature_snapshot_no_tx_is_nop() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        // No decision_feature_tx wired — skip path.
        assert!(pipeline.decision_feature_tx().is_none());
        handle_paper_command(
            make_decision_feature_cmd("ctx-nowire"),
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        // Still no tx; still no panic.
        assert!(pipeline.decision_feature_tx().is_none());
    }

    /// EN: IPC passthrough forwards the payload verbatim into the writer channel.
    /// 中文: IPC 透傳原樣將載荷送入 writer 通道。
    #[test]
    fn test_decision_feature_snapshot_forwards_to_tx() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        let (tx, mut rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(16);
        pipeline.set_decision_feature_tx(tx);

        handle_paper_command(
            make_decision_feature_cmd("ctx-fwd-1"),
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        let msg = rx.try_recv().expect("writer should have received the forwarded msg");
        assert_eq!(msg.context_id, "ctx-fwd-1");
        assert_eq!(msg.strategy_name, "ma_crossover");
        assert_eq!(msg.symbol, "BTCUSDT");
        assert_eq!(msg.side, 1);
        assert_eq!(msg.engine_mode, "paper");
        assert_eq!(msg.feature_schema_version, "v1");
        assert!(msg.features_jsonb.contains("adx_1h"));
    }

    /// EN: Full writer-channel produces a best-effort drop (warn), not a panic.
    /// 中文: writer 通道滿時 best-effort drop（warn），不 panic。
    #[test]
    fn test_decision_feature_snapshot_full_channel_drops() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();
        let (tx, rx) = tokio::sync::mpsc::channel::<crate::database::DecisionFeatureMsg>(1);
        // Keep rx alive so Closed isn't hit; fill the one slot.
        let _held_rx = rx;
        // First send fills the channel.
        tx.try_send(crate::database::DecisionFeatureMsg {
            context_id: "filler".into(),
            ts_ms: 1,
            engine_mode: "paper".into(),
            strategy_name: "x".into(),
            symbol: "Y".into(),
            side: 1,
            feature_schema_version: "v1".into(),
            feature_schema_hash: "h".into(),
            feature_definition_hash: "h".into(),
            features_jsonb: "{}".into(),
        })
        .unwrap();
        pipeline.set_decision_feature_tx(tx);

        // Full channel must not panic — handler warns + drops.
        handle_paper_command(
            make_decision_feature_cmd("ctx-drop"),
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
    }

    /// EN: EmitShadowFill is pure logging today — ensure it doesn't panic.
    /// 中文: EmitShadowFill 目前僅 log，確保不 panic（Stage 0 stub）。
    #[test]
    fn test_emit_shadow_fill_does_not_panic() {
        let dir = tempfile::tempdir().unwrap();
        let mut pipeline = TickPipeline::new(&["BTCUSDT"]);
        let mut writer = make_writer(dir.path());
        let mut pending = HashMap::new();

        handle_paper_command(
            PipelineCommand::EmitShadowFill {
                context_id: "ctx-1".into(),
                strategy: "ma_crossover".into(),
                symbol: "BTCUSDT".into(),
                features_jsonb: "{}".into(),
                prediction_q10: -1.0,
                prediction_q50: 0.5,
                prediction_q90: 2.0,
                cost_bps: 5.5,
                ts_ms: 1_700_000_000_000,
            },
            &mut pipeline,
            &mut writer,
            &mut pending,
        );
        // no assertion beyond no-panic; real Python consumer lands later.
    }
}
